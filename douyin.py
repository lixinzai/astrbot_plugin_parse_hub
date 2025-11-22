import re
import os
import sys
import json
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
            logger.warning(f"标准导入失败 ({e})，尝试修补 sys.path...")
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
        if match:
            return match.group(0)
        return None

    def _find_value(self, data, key_name):
        """递归查找字典中的某个key"""
        if isinstance(data, dict):
            for k, v in data.items():
                if k == key_name:
                    return v
                res = self._find_value(v, key_name)
                if res: return res
        elif isinstance(data, list):
            for item in data:
                res = self._find_value(item, key_name)
                if res: return res
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
                result["msg"] = "解析结果为空 (Cookie无效/风控/链接错误)"
                return result
            
            # [调试日志] 打印返回数据的顶级Keys，帮助定位结构
            try:
                if isinstance(data, dict):
                    logger.info(f"[数据结构] Keys: {list(data.keys())}")
                    # 如果有 aweme_detail，打印它的下一级
                    if "aweme_detail" in data:
                        logger.info(f"[数据结构] aweme_detail Keys: {list(data['aweme_detail'].keys())}")
                else:
                    logger.info(f"[数据结构] 返回类型: {type(data)}")
            except: pass

            # --- 数据清洗 ---
            
            # 1. 确定数据源 root
            # 很多解析器会把核心数据放在 'aweme_detail' 下，或者直接在根目录
            root = data.get("aweme_detail") or data
            
            result["success"] = True
            result["desc"] = root.get("desc", "")
            result["title"] = result["desc"][:50]
            result["author"] = root.get("author", {}).get("nickname", "未知作者")
            
            # 判断类型
            # aweme_type: 0(视频), 68(图文), 2(图文旧版)
            aweme_type = root.get("aweme_type", -1)
            media_type = data.get("media_type") # 兼容旧字段
            
            is_video = True
            if aweme_type == 68 or aweme_type == 2 or media_type == 2 or data.get("type") == "image":
                is_video = False
                result["type"] = "image"

            # === 视频处理 ===
            if is_video:
                result["type"] = "video"
                video_url = None
                
                # 路径 A: video_data -> nwm_video_url (Evil0ctal 风格)
                video_data = data.get("video_data", {})
                if video_data:
                    video_url = video_data.get("nwm_video_url") or video_data.get("nwm_video_url_HQ")
                
                # 路径 B: aweme_detail -> video -> play_addr -> url_list
                if not video_url:
                    video_info = root.get("video", {})
                    # 优先找 bit_rate (高清)
                    bit_rate = video_info.get("bit_rate", [])
                    for br in bit_rate:
                        play_addr = br.get("play_addr", {})
                        urls = play_addr.get("url_list", [])
                        for u in urls:
                            if "playwm" not in u: # 无水印
                                video_url = u
                                break
                        if video_url: break
                    
                    # 其次找 play_addr
                    if not video_url:
                        urls = video_info.get("play_addr", {}).get("url_list", [])
                        for u in urls:
                            if "playwm" not in u:
                                video_url = u
                                break
                        # 如果只有水印链接，尝试替换
                        if not video_url and urls:
                            video_url = urls[0].replace("playwm", "play")

                # 路径 C: 递归查找 play_addr (终极兜底)
                if not video_url:
                    logger.info("尝试递归查找视频链接...")
                    play_addr = self._find_value(data, "play_addr")
                    if play_addr and isinstance(play_addr, dict):
                        urls = play_addr.get("url_list", [])
                        if urls: video_url = urls[0]

                if video_url:
                    result["video_url"] = video_url
                    # 封面
                    cover = root.get("video", {}).get("cover", {}).get("url_list", [""])[0]
                    if cover: result["download_urls"] = [cover]
                else:
                    result["success"] = False
                    result["msg"] = "未找到视频链接 (结构不匹配)"

            # === 图文处理 ===
            else:
                images = []
                # 路径 A: image_data
                img_data = data.get("image_data", {}).get("no_watermark_image_list", [])
                if img_data: images = img_data
                
                # 路径 B: aweme_detail -> images
                if not images:
                    raw_images = root.get("images", [])
                    for img in raw_images:
                        urls = img.get("url_list", [])
                        if urls: images.append(urls[-1])
                
                if images:
                    result["download_urls"] = images
                else:
                    result["success"] = False
                    result["msg"] = "未找到图片列表"

        except Exception as e:
            logger.error(f"DouyinParser 执行错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result["success"] = False
            result["msg"] = f"解析内部错误: {e}"

        return result