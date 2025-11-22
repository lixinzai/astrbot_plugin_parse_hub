import re
import os
import time
import json
import hashlib
import asyncio
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Video, File

# 引入各个模块
from .xhs import XhsHandler
from .douyin import DouyinHandler
from .douyindownload import SmartDownloader # [新增] 引入下载器

@register("xhs_parse_hub", "YourName", "聚合解析插件", "2.1.0")
class ParseHub(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        
        self.enable_cache = config.get("enable_download_cache", True)
        self.show_all_tips = config.get("show_all_progress_tips", False)
        
        # 处理器初始化
        xhs_api = config.get("api_url", "http://127.0.0.1:5556/xhs/")
        self.xhs_handler = XhsHandler(xhs_api)
        
        dy_cookie = config.get("douyin_cookie", "")
        self.douyin_handler = DouyinHandler(cookie=dy_cookie)
        
        # 缓存目录
        current_plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = os.path.join(current_plugin_dir, "xhs_cache")
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            
        self.cleanup_task = None

    async def initialize(self):
        logger.info(f"========== 聚合解析插件启动 (v2.1.0 结构优化版) ==========")
        if self.enable_cache:
            self.cleanup_task = asyncio.create_task(self._auto_cleanup_loop())

    async def terminate(self):
        if self.cleanup_task:
            self.cleanup_task.cancel()

    async def _auto_cleanup_loop(self):
        """每小时清理一次超过1小时的缓存文件"""
        while True:
            try:
                await asyncio.sleep(3600)
                if os.path.exists(self.cache_dir):
                    now = time.time()
                    for filename in os.listdir(self.cache_dir):
                        path = os.path.join(self.cache_dir, filename)
                        if os.path.isfile(path) and now - os.path.getmtime(path) > 3600:
                            try: os.remove(path)
                            except: pass
            except asyncio.CancelledError: break
            except Exception: await asyncio.sleep(60)

    async def try_delete(self, message_obj):
        """安全删除消息"""
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
        except: pass

    def clean_filename(self, title: str) -> str:
        if not title: return "unknown"
        return re.sub(r'[\\/*?:"<>|]', "", title).strip()[:50]

    # [改动] 现在调用外部模块进行下载
    async def download_file(self, url: str, suffix: str = "") -> str:
        if not url: return None
        
        # 计算文件路径
        file_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
        filename = f"{file_hash}{suffix}"
        file_path = os.path.join(self.cache_dir, filename)

        # 获取 Cookie (如果是下载抖音视频)
        # 简单判断：如果 URL 包含 douyin 或者当前是 douyin_handler 调用
        # 这里直接把配置里的 cookie 传进去，SmartDownloader 会自己判断要不要用
        cookie = self.douyin_handler.cookie

        # 调用下载模块
        success = await SmartDownloader.download(url, file_path, cookie)
        
        return file_path if success else None

    # --- 通用业务逻辑 ---
    async def process_parse_result(self, event, result, platform_name):
        if not result["success"]:
            yield event.plain_result(f"❌ {platform_name}解析失败: {result['msg']}")
            return

        title = result.get("title", "")
        author = result.get("author", "")
        desc = result.get("desc", "")
        work_type = result["type"]
        download_urls = result["download_urls"]
        dynamic_urls = result.get("dynamic_urls", [])
        video_url = result.get("video_url")
        
        clean_title = self.clean_filename(title)

        info_text = f"【标题】{title}\n【作者】{author}\n\n{desc}"
        if len(info_text) > 250:
            info_text = info_text[:250] + "...\n(文案过长已折叠)"

        if work_type == "video" and video_url:
            info_text += f"\n\n🔗 视频直链:\n{video_url}"
            
        yield event.plain_result(info_text)

        if not download_urls and not video_url:
            yield event.plain_result("⚠️ 未找到资源。")
            return

        if self.enable_cache:
            msg_text = "📥 正在下载视频..." if work_type == "video" else f"📥 正在下载 {len(download_urls)} 张图片..."
            download_msg = None
            if self.show_all_tips:
                download_msg = await event.send(event.plain_result(msg_text))
            else:
                logger.info(f"[后台] {msg_text}")

            # 执行下载
            local_paths = []
            if work_type == "video" and video_url:
                path = await self.download_file(video_url, suffix=".mp4")
                if path: local_paths.append(path)
            elif download_urls:
                for url in download_urls:
                    path = await self.download_file(url, suffix=".jpg")
                    if path: local_paths.append(path)

            await self.try_delete(download_msg)

            if not local_paths:
                yield event.plain_result("❌ 下载失败，无法发送。")
                return

            # 发送
            sending_msg = None
            upload_text = f"📤 下载完成，正在上传 {len(local_paths)} 个文件..."
            if self.show_all_tips:
                sending_msg = await event.send(event.plain_result(upload_text))
            else:
                logger.info(f"[后台] {upload_text}")

            if work_type == "video":
                try:
                    final_filename = f"{clean_title}.mp4"
                    # 强制使用 File 发送，最稳
                    payload = event.chain_result([File(name=final_filename, file=local_paths[0])])
                    await event.send(payload)
                except Exception as e:
                    if "Timed out" in str(e): logger.warning("视频上传超时")
                    else:
                        logger.error(f"发送失败: {e}")
                        yield event.plain_result("⚠️ 视频上传失败，请使用直链。")
            else:
                for i, path in enumerate(local_paths):
                    if i > 0: await asyncio.sleep(3)
                    try:
                        final_filename = f"{clean_title}_{i+1}.jpg"
                        chain = [File(name=final_filename, file=path)]
                        
                        if dynamic_urls and i < len(dynamic_urls) and dynamic_urls[i]:
                            chain.append(Plain(f"\n🎞️ LivePhoto: {dynamic_urls[i]}"))
                        
                        payload = event.chain_result(chain)
                        await event.send(payload)
                    except Exception as e:
                        if "Timed out" in str(e): logger.warning(f"图 {i+1} 上传超时")
                        else:
                            logger.error(f"发送失败: {e}")
                            yield event.plain_result(f"⚠️ 第 {i+1} 张发送失败。")

            await self.try_delete(sending_msg)

        else:
            # 无缓存模式 (仅发直链)
            status_msg = await event.send(event.plain_result("🚀 正在网络直发...")) if self.show_all_tips else None
            if work_type == "video":
                try: yield event.chain_result([Video.fromURL(video_url)])
                except: yield event.plain_result("⚠️ 发送失败。")
            else:
                for url in download_urls:
                    try: yield event.chain_result([Image.fromURL(url)])
                    except: pass
            await self.try_delete(status_msg)

    # --- 指令注册 ---
    @filter.command("xhs")
    async def xhs_parse(self, event: AstrMessageEvent):
        url = self.xhs_handler.extract_url(event.message_str)
        if not url:
            yield event.plain_result("⚠️ 请提供小红书链接。")
            return
        
        parsing_msg = await event.send(event.plain_result("🔍 正在解析小红书..."))
        result = await self.xhs_handler.parse(url)
        await self.try_delete(parsing_msg)
        
        async for msg in self.process_parse_result(event, result, "小红书"):
            yield msg

    @filter.command("dy")
    async def douyin_parse(self, event: AstrMessageEvent):
        url = self.douyin_handler.extract_url(event.message_str)
        if not url:
            yield event.plain_result("⚠️ 请提供抖音链接。")
            return
            
        parsing_msg = await event.send(event.plain_result("🔍 正在解析抖音..."))
        # 调用 douyin.py，它内部会调用 douyin_scraper
        result = await self.douyin_handler.parse(url)
        await self.try_delete(parsing_msg)
        
        async for msg in self.process_parse_result(event, result, "抖音"):
            yield msg