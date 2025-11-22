import re
import os
import sys
import importlib.util
from astrbot.api import logger

# ================= 1. 动态加载 douyin_scraper =================
DouyinParser = None

try:
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    scraper_root = os.path.join(current_dir, "douyin_scraper")
    if not os.path.exists(scraper_root):
        logger.error(f"❌ 找不到文件夹: {scraper_root}")
    else:
        if not os.path.exists(os.path.join(scraper_root, "__init__.py")):
             with open(os.path.join(scraper_root, "__init__.py"), 'w') as f: pass

        logger.info("[DouyinHandler] 正在导入 DouyinParser...")
        try:
            from douyin_scraper.douyin_parser import DouyinParser
            logger.info("[DouyinHandler] ✅ 导入成功！")
        except ImportError as e:
            crawlers_path = os.path.join(scraper_root, "crawlers")
            if crawlers_path not in sys.path:
                sys.path.insert(0, crawlers_path)
            from douyin_scraper.douyin_parser import DouyinParser
            logger.info("[DouyinHandler] ✅ 备选导入成功！")

except Exception as e:
    logger.error(f"[DouyinHandler] 导入严重错误: {e}")

if DouyinParser is None:
    class DouyinParser:
        def __init__(self, **kwargs): pass
        async def parse(self, url): return None

# ================= 2. 处理器类 =================

class DouyinHandler:
    def __init__(self, cookie: str = None):
        self.cookie = cookie if cookie and len(cookie) > 20 else None

    def extract_url(self, text: str):
        pattern = r'(https?://[^\s]+)'
        match = re.search(pattern, text)
        if match: return match.group(0)
        return None

    async def parse(self, target_url: str) -> dict:
        result = {
            "success": False, "msg": "", "type": "video",
            "title": "", "author": "", "desc": "",
            "download_urls": [], "dynamic_urls": [], "video_url": None
        }

        try:
            if DouyinParser is None:
                result["msg"] = "解析引擎加载失败"
                return result

            parser = DouyinParser(cookie=self.cookie)
            logger.info(f"正在调用 DouyinParser 解析: {target_url}")
            
            data = await parser.parse(target_url)
            
            if not data:
                result["msg"] = "解析结果为空 (Cookie无效/风控)"
                return result
            
            # [新增调试] 确认数据结构
            try:
                if isinstance(data, dict):
                    logger.info(f"[DouyinHandler] Keys: {list(data.keys())}")
            except: pass

            # --- 数据清洗 (适配精简结构) ---
            
            # 1. 基础信息
            # 适配 'desc' 和 'author_nickname'
            result["success"] = True
            result["desc"] = data.get("desc", "")
            result["title"] = result["desc"][:50]
            result["author"] = data.get("author_nickname") or data.get("author", {}).get("nickname", "未知作者")
            
            # 2. 获取媒体列表
            # 这是关键：你的日志显示数据在 media_urls 里
            media_urls = data.get("media_urls", [])
            
            # 3. 判断类型
            raw_type = data.get("type", "video")
            
            # === 视频处理 ===
            if raw_type == "video":
                result["type"] = "video"
                if media_urls:
                    # 视频列表的第一个通常是无水印视频
                    result["video_url"] = media_urls[0]
                    # 尝试找封面，如果没有封面就用视频链接占位(防止报错)，或者留空
                    # 你的日志里没有 cover 字段，所以这里暂时不填 download_urls
                else:
                    # 尝试回退到旧结构查找 (以防万一)
                    video_data = data.get("video_data", {})
                    v_url = video_data.get("nwm_video_url") or data.get("url")
                    if v_url:
                        result["video_url"] = v_url
                    else:
                        result["success"] = False
                        result["msg"] = "未找到视频链接 (media_urls 为空)"

            # === 图文处理 ===
            elif raw_type == "image":
                result["type"] = "image"
                if media_urls:
                    result["download_urls"] = media_urls
                else:
                    # 尝试回退到旧结构
                    images = data.get("image_data", {}).get("no_watermark_image_list", [])
                    if images:
                        result["download_urls"] = images
                    else:
                        result["success"] = False
                        result["msg"] = "未找到图片列表"
            
            else:
                # 未知类型，尝试根据 media_urls 猜测
                if media_urls:
                    # 如果只有一个链接且是 mp4，当视频
                    if len(media_urls) == 1 and ".mp4" in media_urls[0]:
                        result["type"] = "video"
                        result["video_url"] = media_urls[0]
                    else:
                        # 否则当图片
                        result["type"] = "image"
                        result["download_urls"] = media_urls
                else:
                    result["success"] = False
                    result["msg"] = f"未知类型且无媒体数据: {raw_type}"

        except Exception as e:
            logger.error(f"DouyinParser 执行错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result["success"] = False
            result["msg"] = f"解析内部错误: {e}"

        return result