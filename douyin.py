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
    
    # 根据实际结构定位解析器文件
    parser_file_path = os.path.join(scraper_root, "douyin_parser.py")
    
    if not os.path.exists(parser_file_path):
        logger.error(f"❌ 找不到解析器文件: {parser_file_path}")
    else:
        # 补全 __init__.py
        for root, dirs, files in os.walk(scraper_root):
            if "__init__.py" not in files:
                try:
                    with open(os.path.join(root, "__init__.py"), 'w') as f: pass
                except: pass

        # 尝试导入
        logger.info("[DouyinHandler] 正在导入 DouyinParser...")
        try:
            from douyin_scraper.douyin_parser import DouyinParser
            logger.info("[DouyinHandler] ✅ 导入成功！")
        except ImportError as e:
            # 尝试将 crawlers 子目录也加入路径
            crawlers_path = os.path.join(scraper_root, "crawlers")
            if crawlers_path not in sys.path:
                sys.path.insert(0, crawlers_path)
            try:
                from douyin_scraper.douyin_parser import DouyinParser
                logger.info("[DouyinHandler] ✅ 备选导入成功！")
            except ImportError:
                logger.error(f"❌ 无法加载 DouyinParser: {e}")

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
            data = await parser.parse(target_url)
            
            if not data:
                result["msg"] = "解析结果为空 (Cookie无效/风控)"
                return result
            
            # 数据清洗
            result["success"] = True
            result["title"] = data.get("title") or data.get("desc") or "抖音作品"
            result["desc"] = data.get("desc") or ""
            result["author"] = data.get("author_nickname") or data.get("author", {}).get("nickname", "未知作者")
            
            media_type = data.get("media_type") 
            raw_type = data.get("type", "video")
            media_urls = data.get("media_urls", [])

            # 视频
            if raw_type == "video":
                result["type"] = "video"
                if media_urls:
                    result["video_url"] = media_urls[0]
                else:
                    # 备用路径
                    video_data = data.get("video_data", {})
                    v_url = video_data.get("nwm_video_url") or data.get("url")
                    if v_url:
                        result["video_url"] = v_url
                    else:
                        result["success"] = False
                        result["msg"] = "未找到视频链接"

            # 图文
            elif raw_type == "image":
                result["type"] = "image"
                if media_urls:
                    result["download_urls"] = media_urls
                else:
                    # 备用路径
                    images = data.get("image_data", {}).get("no_watermark_image_list", [])
                    if images:
                        result["download_urls"] = images
                    else:
                        result["success"] = False
                        result["msg"] = "未找到图片列表"
            else:
                # 尝试推断
                if media_urls and len(media_urls) == 1 and ".mp4" in media_urls[0]:
                    result["type"] = "video"
                    result["video_url"] = media_urls[0]
                elif media_urls:
                    result["type"] = "image"
                    result["download_urls"] = media_urls
                else:
                    result["success"] = False
                    result["msg"] = f"未知数据类型: {raw_type}"

        except Exception as e:
            logger.error(f"DouyinParser 执行错误: {e}")
            result["success"] = False
            result["msg"] = f"解析内部错误: {e}"

        return result