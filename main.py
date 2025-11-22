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

from .xhs import XhsHandler
from .douyin import DouyinHandler
from .bili import BiliHandler
from .douyindownload import SmartDownloader

@register("xhs_parse_hub", "YourName", "聚合解析插件", "3.1.0")
class ParseHub(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        
        self.enable_cache = config.get("enable_download_cache", True)
        self.show_all_tips = config.get("show_all_progress_tips", False)
        
        # 缓存配置
        custom_cache = config.get("cache_dir", "")
        if custom_cache and os.path.exists(custom_cache):
            self.cache_dir = custom_cache
        else:
            current_plugin_dir = os.path.dirname(os.path.abspath(__file__))
            self.cache_dir = os.path.join(current_plugin_dir, "cache")
        
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

        self.cleanup_interval = config.get("cache_cleanup_interval", 3600)

        # Handlers
        xhs_api = config.get("api_url", "http://127.0.0.1:5556/xhs/")
        self.xhs_handler = XhsHandler(xhs_api)
        
        dy_cookie = config.get("douyin_cookie", "")
        self.douyin_handler = DouyinHandler(cookie=dy_cookie)
        
        # Bili 配置
        bili_use_login = config.get("bili_use_login", False)
        self.bili_download = config.get("bili_download_video", False) # [新增]
        self.bili_handler = BiliHandler(self.cache_dir, bili_use_login)
        
        self.cleanup_task = None

    async def initialize(self):
        logger.info(f"========== 聚合解析插件启动 (v3.1.0) ==========")
        logger.info(f"B站下载模式: {'开启' if self.bili_download else '关闭 (仅直链)'}")
        
        if self.enable_cache and self.cleanup_interval > 0:
            self.cleanup_task = asyncio.create_task(self._auto_cleanup_loop())

    async def terminate(self):
        if self.cleanup_task:
            self.cleanup_task.cancel()

    async def _auto_cleanup_loop(self):
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                if os.path.exists(self.cache_dir):
                    now = time.time()
                    for filename in os.listdir(self.cache_dir):
                        if "cookie" in filename or "session" in filename: continue
                        path = os.path.join(self.cache_dir, filename)
                        if os.path.isfile(path) and now - os.path.getmtime(path) > self.cleanup_interval:
                            try: os.remove(path)
                            except: pass
            except: break

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
        except: pass

    def clean_filename(self, title: str) -> str:
        if not title: return "unknown"
        return re.sub(r'[\\/*?:"<>|]', "", title).strip()[:50]

    async def download_file(self, url: str, suffix: str = "") -> str:
        if not url: return None
        file_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
        filename = f"{file_hash}{suffix}"
        file_path = os.path.join(self.cache_dir, filename)

        cookie = self.douyin_handler.cookie if "douyin" in url else None
        success = await SmartDownloader.download(url, file_path, cookie)
        return file_path if success else None

    # --- 统一发送 ---
    async def process_parse_result(self, event, result, platform_name, local_video_path=None):
        if not result.get("success", False):
            yield event.plain_result(f"❌ {platform_name}解析失败: {result.get('msg', '未知错误')}")
            return

        title = result.get("title", "")
        author = result.get("author", "")
        desc = result.get("desc", "")
        work_type = result.get("type", "video")
        download_urls = result.get("download_urls", [])
        video_url = result.get("video_url")
        
        clean_title = self.clean_filename(title)

        info_text = f"【标题】{title}\n【作者】{author}\n\n{desc}"
        if len(info_text) > 250: info_text = info_text[:250] + "...\n(文案过长已折叠)"
        
        # 直链显示逻辑
        if work_type == "video" and video_url:
            info_text += f"\n\n🔗 视频直链:\n{video_url}"
            if platform_name == "B站" and not self.bili_download:
                info_text += "\n(注: B站直链有时效性且需Referer，建议复制到浏览器查看)"

        yield event.plain_result(info_text)

        # 如果没开缓存下载，或者明确不下载视频，就到此为止(只发封面)
        # 这里对于B站: download_urls里是封面
        if not self.enable_cache and not local_video_path:
             # 无缓存模式兜底发封面
             for url in download_urls:
                 try: yield event.chain_result([Image.fromURL(url)])
                 except: pass
             return

        # 有本地文件 (B站下载模式)
        if local_video_path and os.path.exists(local_video_path):
            send_msg = None
            if self.show_all_tips:
                send_msg = await event.send(event.plain_result("📤 视频准备就绪，正在上传..."))
            
            try:
                final_filename = f"{clean_title}.mp4"
                yield event.chain_result([File(name=final_filename, file=local_video_path)])
            except Exception as e:
                logger.error(f"B站发送失败: {e}")
                yield event.plain_result("⚠️ 发送失败，文件可能过大。")
            
            await self.try_delete(send_msg)
            return

        # 通用下载逻辑 (XHS/Douyin/B站非下载模式发封面)
        dl_msg = None
        if self.show_all_tips and (work_type == "video" or download_urls):
             dl_msg = await event.send(event.plain_result("📥 正在下载资源..."))

        local_paths = []
        # 如果是B站且不下载视频，则跳过视频下载，只下载封面
        if platform_name == "B站" and not self.bili_download:
             # 只下载封面
             for url in download_urls:
                path = await self.download_file(url, suffix=".jpg")
                if path: local_paths.append(path)
        else:
            # 正常逻辑
            if work_type == "video" and video_url:
                path = await self.download_file(video_url, suffix=".mp4")
                if path: local_paths.append(path)
            elif download_urls:
                for url in download_urls:
                    path = await self.download_file(url, suffix=".jpg")
                    if path: local_paths.append(path)

        await self.try_delete(dl_msg)

        if not local_paths:
            if platform_name == "B站" and not self.bili_download:
                # 没下载到封面也无所谓
                return
            yield event.plain_result("❌ 资源下载失败。")
            return

        # 发送
        if self.show_all_tips:
            dl_msg = await event.send(event.plain_result(f"📤 正在上传 {len(local_paths)} 个文件..."))

        if work_type == "video" and (platform_name != "B站" or self.bili_download):
            try:
                final_filename = f"{clean_title}.mp4"
                yield event.chain_result([File(name=final_filename, file=local_paths[0])])
            except Exception as e:
                logger.error(f"发送失败: {e}")
                yield event.plain_result("⚠️ 视频发送失败。")
        else:
            # 发送图片(或封面)
            for i, path in enumerate(local_paths):
                if i > 0: await asyncio.sleep(3)
                try:
                    final_filename = f"{clean_title}_{i+1}.jpg"
                    yield event.chain_result([File(name=final_filename, file=path)])
                except: pass
        
        await self.try_delete(dl_msg)

    # --- 指令 ---

    @filter.command("xhs")
    async def xhs_parse(self, event: AstrMessageEvent):
        url = self.xhs_handler.extract_url(event.message_str)
        if not url: return
        
        msg = await event.send(event.plain_result("🔍 解析小红书..."))
        result = await self.xhs_handler.parse(url)
        await self.try_delete(msg)
        
        async for m in self.process_parse_result(event, result, "小红书"): yield m

    @filter.command("dy")
    async def douyin_parse(self, event: AstrMessageEvent):
        url = self.douyin_handler.extract_url(event.message_str)
        if not url: return
        
        msg = await event.send(event.plain_result("🔍 解析抖音..."))
        result = await self.douyin_handler.parse(url)
        await self.try_delete(msg)
        
        async for m in self.process_parse_result(event, result, "抖音"): yield m

    @filter.command("bili")
    async def bili_parse(self, event: AstrMessageEvent):
        url = self.bili_handler.extract_url(event.message_str)
        if not url:
            yield event.plain_result("⚠️ 请提供B站链接")
            return

        msg = await event.send(event.plain_result("🔍 解析B站中..."))
        
        # 1. 解析基础信息
        result = await self.bili_handler.parse(url)
        await self.try_delete(msg)
        
        if not result["success"]:
            yield event.plain_result(f"❌ 解析失败: {result['msg']}")
            return

        # 2. 如果不下载视频，直接获取直链并展示
        if not self.bili_download:
            # 尝试获取直链用于展示
            stream_url = await self.bili_handler.get_stream_url(result)
            if stream_url:
                result["video_url"] = stream_url # 放入结果中，process会显示它
            
            # 调用通用流程 (它会处理文案和封面的发送)
            async for m in self.process_parse_result(event, result, "B站", None): yield m
            return

        # 3. 如果开启下载，执行登录检查和下载流程
        if self.bili_handler.use_login:
            is_valid = await self.bili_handler.check_cookie_valid()
            if not is_valid:
                qr_data = await self.bili_handler.get_login_qr()
                if qr_data:
                    await event.send(event.chain_result([
                        Plain("⚠️ 需登录下载高清视频，请扫码:"),
                        Image.fromFileSystem(qr_data["img_path"])
                    ]))
                    login_success = False
                    for _ in range(15):
                        await asyncio.sleep(2)
                        if await self.bili_handler.poll_login(qr_data["key"]):
                            login_success = True
                            await event.send(event.plain_result("✅ 登录成功！"))
                            break
                    if not login_success:
                        yield event.plain_result("❌ 登录超时。")
                        return

        dl_msg = None
        if self.show_all_tips:
            dl_msg = await event.send(event.plain_result("📥 正在下载并合并B站视频..."))
        
        local_path = await self.bili_handler.download_bili_video(result)
        await self.try_delete(dl_msg)

        if not local_path:
            yield event.plain_result("⚠️ 视频下载失败，仅发送封面。")
            async for m in self.process_parse_result(event, result, "B站", None): yield m
        else:
            async for m in self.process_parse_result(event, result, "B站", local_path): yield m