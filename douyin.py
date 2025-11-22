import re
import os
import sys
from astrbot.api import logger

# [核心修复] 动态添加路径到 sys.path
# 这样做的目的是让 Python 能找到 'crawlers' 模块，也能让 douyin_parser 内部的 import 正常工作
current_dir = os.path.dirname(os.path.abspath(__file__))
scraper_path = os.path.join(current_dir, "douyin_scraper")

if scraper_path not in sys.path:
    sys.path.insert(0, scraper_path)

# 尝试导入 DouyinParser
try:
    # 既然把 douyin_scraper 加到了环境变量，我们就可以直接从 crawlers 开始导入
    from crawlers.douyin.web.douyin_parser import DouyinParser
except ImportError as e:
    # 如果上面的失败了，尝试相对导入 (作为备选)
    try:
        from .douyin_scraper.crawlers.douyin.web.douyin_parser import DouyinParser
    except ImportError as e2:
        logger.error(f"严重错误: 无法导入 DouyinParser。请检查文件夹结构及是否缺少 __init__.py 文件。")
        logger.error(f"路径尝试1失败: {e}")
        logger.error(f"路径尝试2失败: {e2}")
        # 定义一个伪类，防止插件启动直接崩溃
        class DouyinParser:
            def __init__(self, **kwargs): pass
            async def parse(self, url): return None

class DouyinHandler:
    def __init__(self, cookie: str = None):
        # 如果没有配置 cookie，传 None
        self.cookie = cookie if cookie and len(cookie) > 20 else None

    def extract_url(self, text: str):
        """提取链接"""
        pattern = r'(https?://[^\s]+)'
        match = re.search(pattern, text)
        if match:
            return match.group(0)
        return None

    async def parse(self, target_url: str) -> dict:
        """
        调用 douyin_scraper 进行解析
        """
        result = {
            "success": False, "msg": "", "type": "video",
            "title": "", "author": "", "desc": "",
            "download_urls": [], "dynamic_urls": [], "video_url": None
        }

        try:
            # 1. 初始化解析器
            parser = DouyinParser(cookie=self.cookie)
            
            # 2. 执行解析
            logger.info(f"正在调用 DouyinParser 解析: {target_url}")
            data = await parser.parse(target_url)
            
            # 3. 检查结果
            if not data:
                result["msg"] = "解析器返回空 (可能Cookie无效或被风控)"
                return result
            
            # 打印一下原始数据结构，方便调试 (可选)
            # logger.debug(f"DouyinParser返回: {data}")

            # --- 4. 数据清洗 ---
            result["success"] = True
            result["title"] = data.get("title") or data.get("desc") or "抖音作品"
            result["desc"] = data.get("desc", "")
            result["author"] = data.get("author", {}).get("nickname", "未知作者")
            
            # 判断类型
            media_type = data.get("media_type") 
            raw_type = data.get("type")

            # === 视频处理 (type=4 或 video) ===
            if media_type == 4 or raw_type == "video":
                result["type"] = "video"
                
                # 优先找无水印链接
                video_data = data.get("video_data", {})
                video_url = (
                    video_data.get("nwm_video_url") or 
                    video_data.get("nwm_video_url_HQ") or 
                    data.get("video_url")
                )
                
                if video_url:
                    result["video_url"] = video_url
                    # 封面
                    cover = data.get("cover_data", {}).get("cover", {}).get("url_list", [""])[0]
                    if cover: result["download_urls"] = [cover]
                else:
                    result["success"] = False
                    result["msg"] = "未找到无水印视频链接"

            # === 图文处理 (type=2 或 image) ===
            elif media_type == 2 or raw_type == "image":
                result["type"] = "image"
                image_data = data.get("image_data", {})
                # 那个项目通常存在 no_watermark_image_list
                images = image_data.get("no_watermark_image_list", [])
                
                if images:
                    result["download_urls"] = images
                else:
                    result["success"] = False
                    result["msg"] = "未找到图片列表"
            
            else:
                # 兜底尝试
                if data.get("video_data"):
                    result["type"] = "video"
                    result["video_url"] = data.get("video_data", {}).get("nwm_video_url")
                else:
                    result["success"] = False
                    result["msg"] = f"未知类型: {media_type}/{raw_type}"

        except Exception as e:
            logger.error(f"解析过程发生错误: {e}")
            result["success"] = False
            result["msg"] = f"内部错误: {e}"

        return result