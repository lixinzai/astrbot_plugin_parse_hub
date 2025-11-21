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
from astrbot.api.message_components import Plain, Image, Video, File

@register("xhs_parse_hub", "YourName", "小红书去水印解析插件", "1.2.4")
class XhsParseHub(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url = config.get("api_url", "http://127.0.0.1:5556/xhs/")
        self.enable_cache = config.get("enable_download_cache", True)
        
        current_plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = os.path.join(current_plugin_dir, "xhs_cache")
        
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            
        self.cleanup_task = None

    async def initialize(self):
        logger.info(f"========== 小红书插件启动 (v1.2.4) ==========")
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
                            try: os.remove(file_path)
                            except: pass
            except asyncio.CancelledError: break
            except Exception: await asyncio.sleep(60)

    def extract_url(self, text: str):
        pattern = r'(https?://[^\s]+)'
        match = re.search(pattern, text)
        if match: return match.group(0)
        return None

    def clean_filename(self, title: str) -> str:
        # 替换非法字符，防止保存或发送时报错
        return re.sub(r'[\\/*?:"<>|]', "", title).strip()[:50]

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
                        logger.error(f"下载失败 {resp.status}: {url}")
                        return None
        except Exception as e:
            logger.error(f"下载异常: {e}")
            return None

    @filter.command("xhs")
    async def xhs_parse(self, event: AstrMessageEvent):
        message_str = event.message_str
        target_url = self.extract_url(message_str)
        
        if not target_url:
            if "http" in message_str: target_url = message_str.strip()
            else:
                yield event.plain_result("⚠️ 请提供链接。")
                return

        yield event.plain_result("🔍 正在解析...")

        # --- 1. 请求 API ---
        res_json = None
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=15)
                async with session.post(self.api_url, json={"url": target_url}, timeout=timeout) as resp:
                    if resp.status != 200:
                        yield event.plain_result(f"❌ 解析请求失败: {resp.status}")
                        return
                    res_json = await resp.json()
        except Exception as e:
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
        
        clean_title = self.clean_filename(title)

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
            yield event.plain_result("⚠️ 未找到资源。")
            return

        if self.enable_cache:
            # ====== 缓存模式 ======
            if work_type == "视频" and video_direct_link:
                yield event.plain_result("📥 正在下载视频...")
                local_path = await self.download_file(video_direct_link, suffix=".mp4")
                
                if local_path:
                    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
                    if file_size_mb > 49:
                        yield event.plain_result(f"⚠️ 视频过大 ({file_size_mb:.1f}MB)，请直接使用上方直链。")
                    else:
                        yield event.plain_result(f"📤 下载完成，正在发送文件({file_size_mb:.1f}MB)...")
                        try:
                            # [回归] 强制使用 File 发送视频
                            final_filename = f"{clean_title}.mp4"
                            yield event.chain_result([File(name=final_filename, file=local_path)])
                        except Exception as e:
                            logger.error(f"视频文件发送失败: {e}")
                            yield event.plain_result("⚠️ 发送失败，请使用直链。")
                else:
                    yield event.plain_result("❌ 下载失败。")

            else: # 图文
                count = len(download_urls)
                yield event.plain_result(f"📥 正在下载 {count} 张图片...")
                
                local_paths = []
                for i, url in enumerate(download_urls):
                    path = await self.download_file(url, suffix=".jpg")
                    if path: local_paths.append(path)

                if local_paths:
                    yield event.plain_result(f"📤 下载完成，正在发送...")
                    for i, path in enumerate(local_paths):
                        if i > 0: await asyncio.sleep(2) # 间隔防止超时
                        
                        try:
                            file_size = os.path.getsize(path)
                            final_filename = f"{clean_title}_{i+1}.jpg"
                            
                            # [修改] 阈值提升到 20MB
                            if file_size >= 20 * 1024 * 1024:
                                logger.info(f"图片过大(>20MB)，转文件: {final_filename}")
                                yield event.chain_result([File(name=final_filename, file=path)])
                            else:
                                # [兜底] 尝试发图片，如果因为 >10MB 报错，则转文件
                                try:
                                    yield event.chain_result([Image.fromFileSystem(path)])
                                except Exception as img_err:
                                    logger.warning(f"图片模式发送失败(可能是10-20MB限制)，尝试转文件发送: {img_err}")
                                    yield event.chain_result([File(name=final_filename, file=path)])
                                    
                        except Exception as e:
                            logger.error(f"发送失败: {e}")
                            # 最终兜底
                            try:
                                final_filename = f"{clean_title}_{i+1}.jpg"
                                yield event.chain_result([File(name=final_filename, file=path)])
                            except: pass
                else:
                    yield event.plain_result("❌ 下载失败。")
        else:
            # ====== 无缓存模式 ======
            if work_type == "视频":
                yield event.plain_result("🎬 正在发送视频...")
                try:
                    yield event.chain_result([Video.fromURL(video_direct_link)])
                except: yield event.plain_result("⚠️ 发送失败。")
            else:
                yield event.plain_result(f"🖼️ 正在发送图片...")
                for url in download_urls:
                    try:
                        yield event.chain_result([Image.fromURL(url)])
                    except: pass