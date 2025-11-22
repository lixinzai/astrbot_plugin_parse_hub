import re
import os
import sys
from astrbot.api import logger

# ================= 1. 动态加载 douyin_scraper =================
DouyinParser = None

try:
    # 获取插件根目录 (例如 /AstrBot/data/plugins/astrbot_plugin_parse_hub)
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    
    # [关键修正 1] 将插件根目录加入 sys.path
    # 这样 Python 才能识别 douyin_scraper 是一个包，从而允许内部的相对导入
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    # 检查目录是否存在
    scraper_root = os.path.join(current_dir, "douyin_scraper")
    if not os.path.exists(scraper_root):
        logger.error(f"❌ 找不到文件夹: {scraper_root}")
    else:
        # 自动补全 __init__.py (防止包识别失败)
        if not os.path.exists(os.path.join(scraper_root, "__init__.py")):
             with open(os.path.join(scraper_root, "__init__.py"), 'w') as f: pass

        # [关键修正 2] 作为包进行导入
        # 这相当于: from astrbot_plugin_parse_hub.douyin_scraper.douyin_parser import DouyinParser
        # 但由于我们把 current_dir 加到了 path，所以直接从 douyin_scraper 开始
        logger.info("[DouyinHandler] 正在以 Package 模式导入 DouyinParser...")
        
        try:
            from douyin_scraper.douyin_parser import DouyinParser
            logger.info("[DouyinHandler] ✅ 导入成功！")
        except ImportError as e:
            # 尝试备选路径 (有时候 utils 路径会有问题)
            logger.warning(f"标准导入失败 ({e})，尝试修补 sys.path...")
            # 把 crawlers 也加进去，防止它内部引用错乱
            crawlers_path = os.path.join(scraper_root, "crawlers")
            if crawlers_path not in sys.path:
                sys.path.insert(0, crawlers_path)
            
            from douyin_scraper.douyin_parser import DouyinParser
            logger.info("[DouyinHandler] ✅ 备选导入成功！")

except Exception as e:
    logger.error(f"[DouyinHandler] 导入严重错误: {e}")
    # 打印更多信息方便调试
    import traceback
    logger.error(traceback.format_exc())

# 兜底
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
            if DouyinParser is None:
                result["msg"] = "解析引擎加载失败，请查看后台报错日志"
                return result

            parser = DouyinParser(cookie=self.cookie)
            logger.info(f"正在调用 DouyinParser 解析: {target_url}")
            
            data = await parser.parse(target_url)
            
            if not data:
                result["msg"] = "解析结果为空 (Cookie无效/风控/链接错误)"
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
                video_data = data.get("video_data", {})
                video_url = (
                    video_data.get("nwm_video_url") or 
                    video_data.get("nwm_video_url_HQ") or 
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
                image_data = data.get("image_data", {})
                images = image_data.get("no_watermark_image_list") or []
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
            logger.error(f"DouyinParser 执行错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result["success"] = False
            result["msg"] = f"解析内部错误: {e}"

        return result