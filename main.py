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

# [新增] 引入同目录下的 xhs 模块
from .xhs import XhsHandler

@register("xhs_parse_hub", "YourName", "聚合解析插件", "1.4.0")
class ParseHub(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        
        # 通用配置
        self.enable_cache = config.get("enable_download_cache", True)
        self.show_all_tips = config.get("show_all_progress_tips", False)
        
        # [改动] 初始化 XHS 处理器
        xhs_api = config.get("api_url", "http://127.0.0.1:5556/xhs/")
        self.xhs_handler = XhsHandler(xhs_api)
        
        # 缓存目录设置
        current_plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = os.path.join(current_plugin_dir, "xhs_cache") # 文件夹名先不动，免得你得删缓存
        
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            
        self.cleanup_task = None

    async def initialize(self):
        logger.info(f"========== 聚合解析插件启动 (v1.4.0 多平台重构版) ==========")
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

    # --- 通用工具方法 ---

    async def try_delete(self, message_obj):
        if not message_obj: return
        if isinstance(message_obj, list):
            for m in message_obj: await self.try_delete(m)
            return
        try:
            if hasattr(message_obj, "delete"):
                if asyncio.iscoroutinefunction(message_obj.delete): await message_obj.delete()
                else: message_obj.delete()
            elif hasattr(message_obj, "recall"):
                if asyncio.iscoroutinefunction(message_obj.recall): await message_obj.recall()
                else: message_obj.recall()
        except Exception as e:
            if self.show_all_tips: logger.warning(f"删除消息失败: {e}")

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

    # --- 指令处理 ---

    @filter.command("xhs")
    async def xhs_parse(self, event: AstrMessageEvent):
        """小红书解析"""
        message_str = event.message_str
        
        # 1. 提取链接 (调用 xhs_handler 的逻辑)
        target_url = self.xhs_handler.extract_url(message_str)
        
        if not target_url:
            if "http" in message_str: target_url = message_str.strip()
            else:
                yield event.plain_result("⚠️ 请提供小红书链接。")
                return

        # 2. 发送提示
        parsing_msg = await event.send(event.plain_result("🔍 正在解析中..."))
        
        # 3. 调用 XHS 模块进行解析
        # [改动] 这里不再写一堆 API 请求代码，而是直接调用 xhs_handler.parse
        result = await self.xhs_handler.parse(target_url)
        
        # 删除解析提示
        await self.try_delete(parsing_msg)

        if not result["success"]:
            yield event.plain_result(f"❌ 解析失败: {result['msg']}")
            return

        # 4. 获取标准化数据
        title = result["title"]
        author = result["author"]
        desc = result["desc"]
        work_type = result["type"]
        download_urls = result["download_urls"]
        dynamic_urls = result["dynamic_urls"]
        
        clean_title = self.clean_filename(title)

        # 5. 发送文案
        info_text = f"【标题】{title}\n【作者】{author}\n\n{desc}"
        if len(info_text) > 250:
            info_text = info_text[:250] + "...\n(文案过长已折叠)"

        # 视频直链逻辑
        if work_type == "video" and result["video_url"]:
            info_text += f"\n\n🔗 视频直链:\n{result['video_url']}"
            
        yield event.plain_result(info_text)

        # 6. 处理媒体发送 (通用逻辑)
        if not download_urls:
            yield event.plain_result("⚠️ 未找到资源。")
            return

        if self.enable_cache:
            # --- 下载阶段 ---
            msg_text = "📥 正在下载视频..." if work_type == "video" else f"📥 正在下载 {len(download_urls)} 张图片..."
            
            download_msg = None
            if self.show_all_tips:
                download_msg = await event.send(event.plain_result(msg_text))
            else:
                logger.info(f"[后台处理] {msg_text}")

            local_paths = []
            if work_type == "video" and result["video_url"]:
                path = await self.download_file(result["video_url"], suffix=".mp4")
                if path: local_paths.append(path)
            else:
                for url in download_urls:
                    path = await self.download_file(url, suffix=".jpg")
                    if path: local_paths.append(path)

            await self.try_delete(download_msg)

            if not local_paths:
                yield event.plain_result("❌ 下载失败，无法发送。")
                return

            # --- 上传阶段 ---
            upload_text = f"📤 下载完成，正在上传 {len(local_paths)} 个文件..."
            sending_msg = None
            if self.show_all_tips:
                sending_msg = await event.send(event.plain_result(upload_text))
            else:
                logger.info(f"[后台处理] {upload_text}")

            # 视频发送
            if work_type == "video":
                local_path = local_paths[0]
                try:
                    final_filename = f"{clean_title}.mp4"
                    payload = event.chain_result([File(name=final_filename, file=local_path)])
                    await event.send(payload)
                except Exception as e:
                    if "Timed out" in str(e):
                        logger.warning("视频上传超时 (可能已成功)")
                    else:
                        logger.error(f"视频发送失败: {e}")
                        yield event.plain_result("⚠️ 视频上传失败，请使用直链。")
            
            # 图片发送
            else: 
                for i, path in enumerate(local_paths):
                    if i > 0: await asyncio.sleep(3) # 间隔3秒
                    
                    try:
                        final_filename = f"{clean_title}_{i+1}.jpg"
                        chain = [File(name=final_filename, file=path)]
                        
                        # 动图处理逻辑
                        if dynamic_urls and i < len(dynamic_urls):
                            live_url = dynamic_urls[i]
                            if live_url:
                                chain.append(Plain(f"\n🎞️ 此图含 LivePhoto: {live_url}"))
                        
                        payload = event.chain_result(chain)
                        await event.send(payload)

                    except Exception as e:
                        if "Timed out" in str(e):
                            logger.warning(f"第 {i+1} 张图片上传超时 (可能已成功)")
                        else:
                            logger.error(f"文件发送失败: {e}")
                            yield event.plain_result(f"⚠️ 第 {i+1} 张发送失败。")

            await self.try_delete(sending_msg)

        else:
            # 无缓存模式
            status_msg = None
            if self.show_all_tips:
                status_msg = await event.send(event.plain_result("🚀 正在通过网络直发..."))
                
            if work_type == "video":
                try:
                    yield event.chain_result([Video.fromURL(result["video_url"])])
                except: yield event.plain_result("⚠️ 发送失败。")
            else:
                for url in download_urls:
                    try:
                        yield event.chain_result([Image.fromURL(url)])
                    except: pass
            await self.try_delete(status_msg)