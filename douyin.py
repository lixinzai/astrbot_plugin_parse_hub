import re
from astrbot.api import logger

# [关键] 导入 douyin_scraper 里的解析器
# 注意：根据你提供的目录结构，路径应该是这样的
try:
    from .douyin_scraper.crawlers.douyin.web.douyin_parser import DouyinParser
except ImportError as e:
    logger.error(f"导入 DouyinParser 失败，请检查 douyin_scraper 文件夹是否完整: {e}")

class DouyinHandler:
    def __init__(self, cookie: str = None):
        # 如果没有配置 cookie，这里传 None，DouyinParser 内部可能以此判断是否使用 config.yaml 或默认值
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
        调用 douyin_scraper 进行解析，并转换结果格式
        """
        # 标准化返回结构 (main.py 需要这个格式)
        result = {
            "success": False, "msg": "", "type": "video",
            "title": "", "author": "", "desc": "",
            "download_urls": [], "dynamic_urls": [], "video_url": None
        }

        try:
            # 1. 初始化解析器
            # 根据那个项目的逻辑，kwargs 里的 cookie 会被优先使用
            parser = DouyinParser(cookie=self.cookie)
            
            # 2. 执行解析
            # parser.parse 返回的是一个特定结构的字典
            data = await parser.parse(target_url)
            
            # 3. 检查解析结果
            # 假设 parser 返回 None 或空字典表示失败
            if not data:
                result["msg"] = "解析器返回为空 (可能被风控或链接无效)"
                return result
            
            # 如果那个项目有 status 字段
            # if data.get("status") == "failed": ... (视具体返回结构而定)

            # --- 4. 数据清洗 (Map to our format) ---
            
            # 提取基本信息
            result["success"] = True
            result["title"] = data.get("title") or data.get("desc") or "抖音作品"
            result["desc"] = data.get("desc") or ""
            result["author"] = data.get("author", {}).get("nickname") or "未知作者"
            
            # 判断类型
            # 那个项目通常返回 media_type: 2(图文) / 4(视频)
            media_type = data.get("media_type") 
            # 或者它可能直接返回 type="video"/"image"
            raw_type = data.get("type")

            # === 视频处理 ===
            if media_type == 4 or raw_type == "video":
                result["type"] = "video"
                
                # 尝试提取无水印地址
                # 那个项目的结构通常是 video_data -> nwm_video_url
                video_url = (
                    data.get("video_data", {}).get("nwm_video_url") or # 无水印优先
                    data.get("video_data", {}).get("nwm_video_url_HQ") or 
                    data.get("video_url") # 备用
                )
                
                if video_url:
                    result["video_url"] = video_url
                    # 封面图
                    cover = data.get("cover_data", {}).get("cover", {}).get("url_list", [""])[0]
                    result["download_urls"] = [cover]
                else:
                    result["success"] = False
                    result["msg"] = "未找到无水印视频链接"

            # === 图文处理 ===
            elif media_type == 2 or raw_type == "image":
                result["type"] = "image"
                # 那个项目通常把图放在 image_data -> no_watermark_image_list
                images = data.get("image_data", {}).get("no_watermark_image_list") or []
                
                if images:
                    result["download_urls"] = images
                else:
                    result["success"] = False
                    result["msg"] = "未找到图片列表"
            
            else:
                # 未知类型，尝试作为视频处理兜底
                if data.get("video_data"):
                    result["type"] = "video"
                    result["video_url"] = data.get("video_data", {}).get("nwm_video_url")
                else:
                    result["success"] = False
                    result["msg"] = f"未知的媒体类型: {media_type}"

        except Exception as e:
            logger.error(f"DouyinParser 内部错误: {e}")
            result["success"] = False
            result["msg"] = f"内部解析错误: {e}"

        return result