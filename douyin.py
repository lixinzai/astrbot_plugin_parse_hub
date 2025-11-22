import re
import os
import sys
from astrbot.api import logger

# ================= 动态导入逻辑 =================
try:
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    
    # [变量名] 定义 scraper_root
    scraper_root = os.path.join(current_dir, "douyin_scraper")
    
    logger.info(f"[DouyinHandler] 尝试加载 scraper: {scraper_root}")

    if not os.path.exists(scraper_root):
        logger.error(f"❌ 找不到文件夹: {scraper_root}")
    else:
        # 自动补全 __init__.py
        paths_to_check = [
            scraper_root,
            os.path.join(scraper_root, "crawlers"),
            os.path.join(scraper_root, "crawlers", "douyin"),
            os.path.join(scraper_root, "crawlers", "douyin", "web"),
            os.path.join(scraper_root, "crawlers", "utils")
        ]
        
        for p in paths_to_check:
            if os.path.exists(p):
                init_file = os.path.join(p, "__init__.py")
                if not os.path.exists(init_file):
                    try:
                        with open(init_file, 'w') as f: pass
                    except: pass

        # [关键修复] 确保这里使用 scraper_root
        if scraper_root not in sys.path:
            sys.path.insert(0, scraper_root) 
        
        logger.info("[DouyinHandler] 正在导入 DouyinParser...")
        from crawlers.douyin.web.douyin_parser import DouyinParser
        logger.info("[DouyinHandler] ✅ 导入成功！")

except ImportError as e:
    logger.error(f"[DouyinHandler] 导入失败: {e}")
    class DouyinParser:
        def __init__(self, **kwargs): pass
        async def parse(self, url): return None

except Exception as e:
    logger.error(f"[DouyinHandler] 初始化错误: {e}")
    class DouyinParser:
        def __init__(self, **kwargs): pass
        async def parse(self, url): return None
# =============================================

class DouyinHandler:
    def __init__(self, cookie: str = None):
        self.cookie = cookie if cookie and len(cookie) > 20 else None

    def extract_url(self, text: str):
        pattern = r'(https?://[^\s]+)'
        match = re.search(pattern, text)
        if match:
            return match.group(0)
        return None

    async def parse(self, target_url: str) -> dict:
        result = {
            "success": False, "msg": "", "type": "video",
            "title": "", "author": "", "desc": "",
            "download_urls": [], "dynamic_urls": [], "video_url": None
        }

        try:
            parser = DouyinParser(cookie=self.cookie)
            logger.info(f"正在调用 DouyinParser 解析: {target_url}")
            data = await parser.parse(target_url)
            
            if not data:
                result["msg"] = "解析器返回空 (可能Cookie无效)"
                return result
            
            # 数据清洗
            result["success"] = True
            result["title"] = data.get("title") or data.get("desc") or "抖音作品"
            result["desc"] = data.get("desc") or ""
            result["author"] = data.get("author", {}).get("nickname") or "未知作者"
            
            media_type = data.get("media_type") 
            raw_type = data.get("type")

            # 视频
            if media_type == 4 or raw_type == "video":
                result["type"] = "video"
                video_url = (
                    data.get("video_data", {}).get("nwm_video_url") or 
                    data.get("video_data", {}).get("nwm_video_url_HQ") or 
                    data.get("video_url")
                )
                if video_url:
                    result["video_url"] = video_url
                    cover = data.get("cover_data", {}).get("cover", {}).get("url_list", [""])[0]
                    if cover: result["download_urls"] = [cover]
                else:
                    result["success"] = False
                    result["msg"] = "未找到无水印视频链接"

            # 图文
            elif media_type == 2 or raw_type == "image":
                result["type"] = "image"
                images = data.get("image_data", {}).get("no_watermark_image_list") or []
                if images:
                    result["download_urls"] = images
                else:
                    result["success"] = False
                    result["msg"] = "未找到图片列表"
            else:
                if data.get("video_data"):
                    result["type"] = "video"
                    result["video_url"] = data.get("video_data", {}).get("nwm_video_url")
                else:
                    result["success"] = False
                    result["msg"] = f"未知类型: {media_type}"

        except Exception as e:
            logger.error(f"DouyinParser 内部错误: {e}")
            result["success"] = False
            result["msg"] = f"内部解析错误: {e}"

        return result