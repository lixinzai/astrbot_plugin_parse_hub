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

@register("xhs_parse_hub", "YourName", "小红书去水印解析插件", "1.0.0")
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
        logger.info(f"========== 小红书插件启动 (v1.0.0) ==========")
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

    # 尝试撤回/删除消息
    async def try_delete(self, message_obj):
        if not message_obj: return
        try:
            if hasattr(message_obj, "delete"):
                await message_obj.delete()
            elif hasattr(message_obj, "recall"):
                await message_obj.recall()
        except: pass

    def extract_url(self, text: str):
        pattern = r'(https?://[^\s]+)'
        match = re.search(pattern, text)
        if match: return match.group(0)
        return None

    def clean_filename(self, title: str) -> str:
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

        # 1. 发送提示 -> 解析 -> 删除提示
        parsing_msg = await event.send(Plain("🔍 正在解析中..."))
        
        res_json = None
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=15)
                async with session.post(self.api_url, json={"url": target_url}, timeout=timeout) as resp:
                    await self.try_delete(parsing_msg) # 删除"正在解析"
                    
                    if resp.status != 200:
                        yield event.plain_result(f"❌ 解析请求失败: {resp.status}")
                        return
                    res_json = await resp.json()
        except Exception as e:
            await self.try_delete(parsing_msg)
            yield event.plain_result(f"❌ 连接错误: {e}")
            return

        # 2. 提取数据
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

        # 3. 发送文案
        info_text = f"【标题】{title}\n【作者】{author}\n\n{desc}"
        if len(info_text) > 250:
            info_text = info_text[:250] + "...\n(文案过长已折叠)"

        video_direct_link = None
        if work_type == "视频" and download_urls:
            video_direct_link = download_urls[0]
            info_text += f"\n\n🔗 视频直链:\n{video_direct_link}"
            
        yield event.plain_result(info_text)

        # 4. 处理媒体
        if not download_urls:
            yield event.plain_result("⚠️ 未找到资源。")
            return

        if self.enable_cache:
            # --- 阶段 A: 下载 ---
            msg_text = "📥 正在下载视频..." if work_type == "视频" else f"📥 正在下载 {len(download_urls)} 张图片..."
            download_msg = await event.send(Plain(msg_text))

            local_paths = []
            if work_type == "视频" and video_direct_link:
                path = await self.download_file(video_direct_link, suffix=".mp4")
                if path: local_paths.append(path)
            else:
                for url in download_urls:
                    path = await self.download_file(url, suffix=".jpg")
                    if path: local_paths.append(path)

            await self.try_delete(download_msg) # 删除"正在下载"

            if not local_paths:
                yield event.plain_result("❌ 下载失败，无法发送。")
                return

            # --- 阶段 B: 上传 ---
            sending_msg = await event.send(Plain(f"📤 下载完成，正在上传 {len(local_paths)} 个文件..."))

            # 视频模式 (强制文件)
            if work_type == "视频":
                local_path = local_paths[0]
                try:
                    final_filename = f"{clean_title}.mp4"
                    yield event.chain_result([File(name=final_filename, file=local_path)])
                except Exception as e:
                    logger.error(f"视频发送失败: {e}")
                    yield event.plain_result("⚠️ 视频上传失败，请使用直链。")
            
            # 图文模式 (强制文件 + 动图说明)
            else: 
                for i, path in enumerate(local_paths):
                    if i > 0: await asyncio.sleep(2) # 间隔
                    
                    try:
                        final_filename = f"{clean_title}_{i+1}.jpg"
                        chain = [File(name=final_filename, file=path)]
                        
                        # 检查是否有动图
                        if dynamic_urls and i < len(dynamic_urls):
                            live_url = dynamic_urls[i]
                            if live_url:
                                chain.append(Plain(f"\n🎞️ 此图含 LivePhoto: {live_url}"))
                        
                        yield event.chain_result(chain)
                    except Exception as e:
                        logger.error(f"文件发送失败: {e}")
                        yield event.plain_result(f"⚠️ 第 {i+1} 张发送失败。")

            await self.try_delete(sending_msg) # 删除"正在上传"

        else:
            # 无缓存模式
            status_msg = await event.send(Plain("🚀 正在通过网络直发..."))
            if work_type == "视频":
                try:
                    yield event.chain_result([Video.fromURL(video_direct_link)])
                except: yield event.plain_result("⚠️ 发送失败。")
            else:
                for url in download_urls:
                    try:
                        yield event.chain_result([Image.fromURL(url)])
                    except: pass
            await self.try_delete(status_msg)