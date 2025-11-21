import re
import os
import time
import aiohttp
import json
import hashlib
import asyncio
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Video

@register("xhs_parse_hub", "YourName", "小红书去水印解析插件", "1.1.3")
class XhsParseHub(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        # 务必确保这里读取到的 config 是正确的
        self.api_url = config.get("api_url", "http://127.0.0.1:5556/xhs/")
        self.enable_cache = config.get("enable_download_cache", True)
        
        current_plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = os.path.join(current_plugin_dir, "xhs_cache")
        
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            
        self.cleanup_task = None

    async def initialize(self):
        # [调试日志] 启动时打印当前配置的 API 地址
        logger.info(f"========== 小红书插件启动 ==========")
        logger.info(f"解析服务 API 地址: {self.api_url}")
        logger.info(f"缓存目录: {self.cache_dir}")
        logger.info(f"===================================")
        
        if self.enable_cache:
            self.cleanup_task = asyncio.create_task(self._auto_cleanup_loop())

    async def terminate(self):
        if self.cleanup_task:
            self.cleanup_task.cancel()

    async def _auto_cleanup_loop(self):
        while True:
            try:
                await asyncio.sleep(3600)
                if os.path.exists(self.cache_dir):
                    now = time.time()
                    for filename in os.listdir(self.cache_dir):
                        file_path = os.path.join(self.cache_dir, filename)
                        if not os.path.isfile(file_path): continue
                        if now - os.path.getmtime(file_path) > 3600:
                            try:
                                os.remove(file_path)
                            except: pass
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(60)

    def extract_url(self, text: str):
        pattern = r'(https?://[^\s]+)'
        match = re.search(pattern, text)
        if match:
            return match.group(0)
        return None

    async def download_file(self, url: str, suffix: str = "") -> str:
        if not url: return None
        try:
            file_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
            filename = f"{file_hash}{suffix}"
            file_path = os.path.join(self.cache_dir, filename)

            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                os.utime(file_path, None)
                return file_path

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        with open(file_path, 'wb') as f:
                            f.write(content)
                        return file_path
                    else:
                        logger.error(f"下载文件失败 {resp.status}: {url}")
                        return None
        except Exception as e:
            logger.error(f"下载异常: {e}")
            return None

    @filter.command("xhs")
    async def xhs_parse(self, event: AstrMessageEvent):
        message_str = event.message_str
        target_url = self.extract_url(message_str)
        
        if not target_url:
            if "http" in message_str:
                target_url = message_str.strip()
            else:
                yield event.plain_result("⚠️ 请提供包含小红书链接的消息。")
                return

        yield event.plain_result("🔍 正在解析，请稍候...")

        # --- 1. 请求 API ---
        res_json = None
        try:
            # [调试日志] 打印正在请求的完整地址
            logger.info(f"[Debug] 正在向解析服务发送请求: {self.api_url} | 参数: {target_url}")
            
            async with aiohttp.ClientSession() as session:
                # 设置超时为 15秒，避免卡太久
                timeout = aiohttp.ClientTimeout(total=15)
                
                async with session.post(self.api_url, json={"url": target_url}, timeout=timeout) as resp:
                    if resp.status != 200:
                        # [调试日志]
                        logger.error(f"[Debug] 解析服务返回错误码: {resp.status}")
                        yield event.plain_result(f"❌ 解析请求失败，状态码: {resp.status}")
                        return
                    res_json = await resp.json()
                    logger.info(f"[Debug] 解析成功，获取到数据。")
                    
        except asyncio.TimeoutError:
            logger.error(f"[Debug] 请求超时。请检查 API 地址 {self.api_url} 是否可从机器人所在网络访问。")
            yield event.plain_result(f"❌ 连接解析服务超时 (15s)。\n当前配置地址: {self.api_url}\n请检查网络或配置 IP。")
            return
        except Exception as e:
            logger.error(f"[Debug] 请求发生异常: {e}")
            yield event.plain_result(f"❌ 连接错误: {e}")
            return

        # --- 2. 提取数据 ---
        data = res_json.get("data")
        if not data:
            msg = res_json.get("message", "未知错误")
            yield event.plain_result(f"❌ 解析失败: {msg}")
            return

        title = data.get("作品标题", "无标题")
        author = data.get("作者昵称", "未知作者")
        desc = data.get("作品描述", "")
        work_type = data.get("作品类型", "")
        
        download_urls = data.get("下载地址", [])
        dynamic_urls = data.get("动图地址", [])

        # --- 3. 构建文本 ---
        info_text = f"【标题】{title}\n【作者】{author}\n\n{desc}"
        if len(info_text) > 250:
            info_text = info_text[:250] + "...\n(文案过长已折叠)"

        video_direct_link = None
        if work_type == "视频" and download_urls:
            video_direct_link = download_urls[0]
            info_text += f"\n\n🔗 视频直链:\n{video_direct_link}"

        if work_type == "图文" and dynamic_urls:
            live_links = [url for url in dynamic_urls if url]
            if live_links:
                info_text += f"\n\n🎞️ 动图直链 ({len(live_links)}个):\n"
                for idx, link in enumerate(live_links, 1):
                    info_text += f"{idx}. {link}\n"

        yield event.plain_result(info_text)

        # --- 4. 发送媒体 ---
        if not download_urls:
            yield event.plain_result("⚠️ 未找到资源下载地址。")
            return

        if self.enable_cache:
            if work_type == "视频" and video_direct_link:
                yield event.plain_result("📥 正在下载视频到本地缓存...")
                local_path = await self.download_file(video_direct_link, suffix=".mp4")
                if local_path:
                    yield event.plain_result("📤 下载完成，正在发送...")
                    try:
                        yield event.chain_result([Video.fromFileSystem(local_path)])
                    except Exception as e:
                        logger.error(f"本地发送失败: {e}")
                        yield event.plain_result(f"⚠️ 发送失败，请使用上方直链。")
                else:
                    yield event.plain_result("❌ 下载失败，请使用直链。")

            else: # 图文
                count = len(download_urls)
                yield event.plain_result(f"📥 正在下载 {count} 张图片...")
                local_paths = []
                for i, url in enumerate(download_urls):
                    path = await self.download_file(url, suffix=".jpg")
                    if path: local_paths.append(path)
                
                if local_paths:
                    yield event.plain_result(f"📤 下载完成，正在发送...")
                    for path in local_paths:
                        try:
                            yield event.chain_result([Image.fromFileSystem(path)])
                        except: pass
                else:
                    yield event.plain_result("❌ 图片下载失败。")
        else:
            # 无缓存模式
            if work_type == "视频" and video_direct_link:
                yield event.plain_result("🎬 正在发送视频...")
                try:
                    yield event.chain_result([Video.fromURL(video_direct_link)])
                except: yield event.plain_result("⚠️ 发送失败。")
            else:
                yield event.plain_result(f"🖼️ 正在发送 {len(download_urls)} 张图片...")
                for url in download_urls:
                    try:
                        yield event.chain_result([Image.fromURL(url)])
                    except: pass