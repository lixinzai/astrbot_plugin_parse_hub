import re
import os
import sys
import importlib.util
from astrbot.api import logger

# ================= 1. 动态加载 douyin_scraper =================
DouyinParser = None

try:
    # 获取路径
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    scraper_root = os.path.join(current_dir, "douyin_scraper")
    
    # 目标解析器文件路径
    parser_file_path = os.path.join(scraper_root, "crawlers", "douyin", "web", "douyin_parser.py")
    
    if not os.path.exists(parser_file_path):
        logger.error(f"❌ 找不到解析器文件: {parser_file_path}")
        logger.error("请检查 douyin_scraper 文件夹是否完整！")
    else:
        # 将 scraper_root 加入环境变量 (修复 utils 导入问题)
        if scraper_root not in sys.path:
            sys.path.insert(0, scraper_root)
        
        # 补全缺失的 __init__.py
        for root, dirs, files in os.walk(scraper_root):
            if "__init__.py" not in files:
                try:
                    with open(os.path.join(root, "__init__.py"), 'w') as f: pass
                except: pass

        # 使用 importlib 直接加载文件 (解决路径迷宫)
        try:
            spec = importlib.util.spec_from_file_location("douyin_parser_module", parser_file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules["douyin_parser_module"] = module
                spec.loader.exec_module(module)
                
                if hasattr(module, "DouyinParser"):
                    DouyinParser = module.DouyinParser
                    logger.info("[DouyinHandler] ✅ 成功加载本地解析引擎 (DouyinParser)")
                else:
                    logger.error("❌ 加载成功但未找到 DouyinParser 类")
        except Exception as load_err:
            logger.error(f"❌ 动态加载失败: {load_err}")

except Exception as e:
    logger.error(f"[DouyinHandler] 初始化严重错误: {e}")

# 兜底防止崩溃
if DouyinParser is None:
    class DouyinParser:
        def __init__(self, **kwargs): pass
        async def parse(self, url): return None

# ================= 2. 处理器类 (供 main.py 调用) =================

class DouyinHandler:
    def __init__(self, cookie: str = None):
        # 如果配置为空，传 None，让 Parser 内部决定使用默认值或 config.yaml
        self.cookie = cookie if cookie and len(cookie) > 20 else None

    def extract_url(self, text: str):
        pattern = r'(https?://[^\s]+)'
        match = re.search(pattern, text)
        if match:
            return match.group(0)
        return None

    async def parse(self, target_url: str) -> dict:
        """
        调用 douyin_scraper 解析，并清洗数据格式
        """
        # 初始化返回结构
        result = {
            "success": False, "msg": "", "type": "video",
            "title": "", "author": "", "desc": "",
            "download_urls": [], "dynamic_urls": [], "video_url": None
        }

        try:
            if DouyinParser is None:
                result["msg"] = "解析引擎未加载"
                return result

            # 初始化
            parser = DouyinParser(cookie=self.cookie)
            logger.info(f"正在调用 DouyinParser 解析: {target_url}")
            
            # 执行解析
            data = await parser.parse(target_url)
            
            if not data:
                result["msg"] = "解析结果为空 (可能Cookie过期或被风控)"
                return result
            
            # --- 数据清洗 (适配 main.py 的通用格式) ---
            result["success"] = True
            result["title"] = data.get("title") or data.get("desc") or "抖音作品"
            result["desc"] = data.get("desc", "")
            result["author"] = data.get("author", {}).get("nickname") or "未知作者"
            
            media_type = data.get("media_type") 
            raw_type = data.get("type")

            # 视频处理
            if media_type == 4 or raw_type == "video":
                result["type"] = "video"
                # douyin_scraper 通常返回 video_data
                video_data = data.get("video_data", {})
                video_url = (
                    video_data.get("nwm_video_url") or 
                    video_data.get("nwm_video_url_HQ") or 
                    data.get("video_url")
                )
                
                if video_url:
                    result["video_url"] = video_url
                    # 提取封面
                    cover = data.get("cover_data", {}).get("cover", {}).get("url_list", [""])[0]
                    if cover: result["download_urls"] = [cover]
                else:
                    result["success"] = False
                    result["msg"] = "未找到无水印视频链接"

            # 图文处理
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
                # 兜底尝试
                if data.get("video_data"):
                    result["type"] = "video"
                    result["video_url"] = data.get("video_data", {}).get("nwm_video_url")
                else:
                    result["success"] = False
                    result["msg"] = f"未知媒体类型: {media_type}"

        except Exception as e:
            logger.error(f"DouyinParser 执行错误: {e}")
            result["success"] = False
            result["msg"] = f"解析内部错误: {e}"

        return result