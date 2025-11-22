import re
import os
import time
import hashlib
import asyncio
import json
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Video, File

from .xhs import XhsHandler
from .douyin import DouyinHandler
from .bili import BiliHandler
from .douyindownload import SmartDownloader

@register("xhs_parse_hub", "YourName", "全能聚合解析插件", "4.0.3")
class ParseHub(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        
        self.enable_cache = config.get("enable_download_cache", True)
        self.show_all_tips = config.get("show_all_progress_tips", False)
        self.auto_parse = config.get("auto_parse_enabled", True)
        
        custom_cache = config.get("cache_dir", "")
        if custom_cache and os.path.exists(custom_cache):
            self.cache_dir = custom_cache
        else:
            current_plugin_dir = os.path.dirname(os.path.abspath(__file__))
            self.cache_dir = os.path.join(current_plugin_dir, "cache")
        if not os.path.exists(self.cache_dir): os.makedirs(self.cache_dir)

        self.cleanup_interval = config.get("cache_cleanup_interval", 3600)

        self.xhs_handler = XhsHandler(config.get("api_url", "http://127.0.0.1:5556/xhs/"))
        self.douyin_handler = DouyinHandler(cookie=config.get("douyin_cookie", ""))
        
        bili_use_login = config.get("bili_use_login", False)
        self.bili_download = config.get("bili_download_video", False)
        self.bili_handler = BiliHandler(self.cache_dir, bili_use_login)
        
        self.cleanup_task = None

        # [修复] 优化正则表达式，支持链接中包含 "/" 符号
        # 使用 [a-zA-Z0-9/_]+ 来匹配路径，或者直接使用 [^\s]+ 匹配非空字符
        self.regex_bili = [
            r'(b23\.tv|bili2233\.cn)/[a-zA-Z0-9]+',
            r'bilibili\.com/video/(av\d+|BV\w+)',
            r'bilibili\.com/opus/\d+',
            r't\.bilibili\.com/\d+'
        ]
        self.regex_douyin = [
            r'v\.douyin\.com/[a-zA-Z0-9/]+',
            r'douyin\.com/(video|note)/\d+'
        ]
        self.regex_xhs = [
            r'xhslink\.com/[a-zA-Z0-9/]+', # 修复：允许路径中包含斜杠
            r'xiaohongshu\.com/(explore|discovery/item)/[a-zA-Z0-9]+'
        ]

    async def initialize(self):
        logger.info(f"========== 聚合解析插件启动 (v4.0.3) ==========")
        logger.info(f"自动解析模式: {'开启' if self.auto_parse else '关闭 (需使用 /jx)'}")
        if self.enable_cache and self.cleanup_interval > 0:
            self.cleanup_task = asyncio.create_task(self._auto_cleanup_loop())

    async def terminate(self):
        if self.cleanup_task: self.cleanup_task.cancel()

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

        cookie = None
        referer = None
        if "douyin" in url:
            cookie = self.douyin_handler.cookie
            referer = "https://www.douyin.com/"
        elif "bili" in url or "hdslb" in url:
            referer = "https://www.bilibili.com/"
        elif "xiaohongshu" in url or "xhscdn" in url:
            referer = "https://www.xiaohongshu.com/"

        success = await SmartDownloader.download(url, file_path, cookie, referer)
        return file_path if success else None

    # --- 核心识别逻辑 ---
    def detect_resource(self, event: AstrMessageEvent):
        """检测消息中是否包含支持的链接"""
        text = event.message_str
        
        for pattern in self.regex_xhs:
            match = re.search(pattern, text)
            if match: return "xhs", f"https://{match.group()}"
        
        for pattern in self.regex_douyin:
            match = re.search(pattern, text)
            if match: return "dy", f"https://{match.group()}"
            
        for pattern in self.regex_bili:
            match = re.search(pattern, text)
            if match: return "bili", f"https://{match.group()}"

        try:
            raw_str = str(event.message_obj)
            if "qqdocurl" in raw_str and "bilibili" in raw_str:
                match = re.search(r'(http[s]?://[\w\./\?=&]+)', raw_str)
                if match and "bilibili" in match.group(1): return "bili", match.group(1)

            if "jumpUrl" in raw_str and "xiaohongshu" in raw_str:
                match = re.search(r'(http[s]?://[\w\./\?=&]+)', raw_str)
                if match and "xiaohongshu" in match.group(1): return "xhs", match.group(1)
        except: pass

        return None, None

    # --- 统一调度逻辑 ---
    async def dispatch_parsing(self, event: AstrMessageEvent, platform: str, url: str):
        logger.info(f"触发解析: 平台={platform}, URL={url}")
        
        parsing_msg = await event.send(event.plain_result(f"🔍 正在解析{platform}..."))
        
        result = None
        handler = None
        
        if platform == "xhs":
            handler = self.xhs_handler
            result = await handler.parse(url)
        elif platform == "dy":
            handler = self.douyin_handler
            result = await handler.parse(url)
        elif platform == "bili":
            handler = self.bili_handler
            result = await handler.parse(url)

        await self.try_delete(parsing_msg)

        if not result:
            yield event.plain_result("❌ 解析器未返回结果。")
            return

        # B站特殊逻辑
        if platform == "bili":
            if not result["success"]:
                yield event.plain_result(f"❌ 解析失败: {result['msg']}")
                return

            if not self.bili_download:
                stream_url = await handler.get_stream_url(result)
                if stream_url: result["video_url"] = stream_url
                async for m in self.process_parse_result(event, result, "B站", None): yield m
                return
            
            if handler.use_login:
                is_valid = await handler.check_cookie_valid()
                if not is_valid:
                    qr_data = await handler.get_login_qr()
                    if qr_data:
                        await event.send(event.chain_result([
                            Plain("⚠️ 需登录下载高清视频，请扫码:"),
                            Image.fromFileSystem(qr_data["img_path"])
                        ]))
                        success = False
                        for _ in range(15):
                            await asyncio.sleep(2)
                            if await handler.poll_login(qr_data["key"]):
                                success = True; await event.send(event.plain_result("✅ 登录成功！")); break
                        if not success:
                            yield event.plain_result("❌ 登录超时。"); return

            dl_msg = await event.send(event.plain_result("📥 正在下载并合并B站视频...")) if self.show_all_tips else None
                
            local_path = await handler.download_bili_video(result)
            await self.try_delete(dl_msg)

            if not local_path:
                yield event.plain_result("⚠️ 视频下载失败，仅发送封面。")
                async for m in self.process_parse_result(event, result, "B站", None): yield m
            else:
                async for m in self.process_parse_result(event, result, "B站", local_path): yield m
        
        else:
            display_name = "小红书" if platform == "xhs" else "抖音"
            async for m in self.process_parse_result(event, result, display_name): yield m

    # --- 指令入口 ---
    @filter.command("jx")
    async def jx_cmd(self, event: AstrMessageEvent):
        """手动解析指令"""
        platform, url = self.detect_resource(event)
        if not platform:
            yield event.plain_result("⚠️ 未检测到支持的链接 (抖音/小红书/B站)")
            return
        
        async for m in self.dispatch_parsing(event, platform, url): yield m

    # --- 自动解析监听器 ---
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """全局消息监听"""
        if not self.auto_parse: return
        if event.message_str.strip().startswith("/"): return

        platform, url = self.detect_resource(event)
        if platform:
            async for m in self.dispatch_parsing(event, platform, url): yield m

    # --- 发送逻辑 ---
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
        
        if work_type == "video" and video_url:
            info_text += f"\n\n🔗 视频直链:\n{video_url}"
            if platform_name == "B站" and not self.bili_download:
                info_text += "\n(注: B站直链有时效性且需Referer，建议复制到浏览器查看)"

        yield event.plain_result(info_text)

        if not self.enable_cache and not local_video_path:
             for url in download_urls:
                 try: 
                     yield event.chain_result([Image.fromURL(url)])
                 except: pass
             return

        if local_video_path and os.path.exists(local_video_path):
            send_msg = await event.send(event.plain_result("📤 视频准备就绪，正在上传...")) if self.show_all_tips else None
            try:
                final_filename = f"{clean_title}.mp4"
                yield event.chain_result([File(name=final_filename, file=local_video_path)])
            except Exception as e:
                logger.error(f"B站发送失败: {e}")
                yield event.plain_result("⚠️ 发送失败。")
            await self.try_delete(send_msg)
            return

        dl_msg = None
        if self.show_all_tips and (work_type == "video" or download_urls):
             dl_msg = await event.send(event.plain_result("📥 正在下载资源..."))

        local_paths = []
        if platform_name == "B站" and not self.bili_download:
             for url in download_urls:
                path = await self.download_file(url, suffix=".jpg")
                if path: local_paths.append(path)
        else:
            if work_type == "video" and video_url:
                path = await self.download_file(video_url, suffix=".mp4")
                if path: local_paths.append(path)
            elif download_urls:
                for url in download_urls:
                    path = await self.download_file(url, suffix=".jpg")
                    if path: local_paths.append(path)

        await self.try_delete(dl_msg)

        if not local_paths:
            if platform_name == "B站" and not self.bili_download: return
            yield event.plain_result("❌ 资源下载失败。")
            return

        send_msg = None
        if self.show_all_tips:
            send_msg = await event.send(event.plain_result(f"📤 正在上传 {len(local_paths)} 个文件..."))

        if work_type == "video" and (platform_name != "B站" or self.bili_download):
            try:
                final_filename = f"{clean_title}.mp4"
                yield event.chain_result([File(name=final_filename, file=local_paths[0])])
            except Exception as e:
                logger.error(f"发送失败: {e}")
                yield event.plain_result("⚠️ 视频发送失败。")
        else:
            for i, path in enumerate(local_paths):
                if i > 0: await asyncio.sleep(3)
                try:
                    final_filename = f"{clean_title}_{i+1}.jpg"
                    yield event.chain_result([File(name=final_filename, file=path)])
                except: pass
        
        await self.try_delete(send_msg)