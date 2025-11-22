import aiohttp
import re
import random
from astrbot.api import logger

class DouyinHandler:
    def __init__(self, cookie: str = None):
        # 如果用户没填(None)或者填了空字符串，使用默认的游客Cookie兜底
        default_cookie = "s_v_web_id=verify_leytkxgn_kvO5kOmO_SdMs_4t1o_B5ml_BUqt5v66Lq5P;"
        self.cookie = cookie if cookie and len(cookie) > 10 else default_cookie
        
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
        ]

    def _get_headers(self):
        """动态生成 Header"""
        return {
            "User-Agent": random.choice(self.user_agents),
            "Referer": "https://www.douyin.com/",
            # 使用配置的 Cookie
            "Cookie": self.cookie
        }

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
            async with aiohttp.ClientSession() as session:
                # 1. 获取重定向后的长链接 (获取 Video ID)
                try:
                    async with session.get(target_url, headers=self._get_headers(), allow_redirects=True) as resp:
                        long_url = str(resp.url)
                        # 匹配 /video/xxx 或 /note/xxx 或 ?modal_id=xxx
                        id_match = re.search(r'/(video|note)/(\d+)', long_url)
                        if not id_match:
                            id_match = re.search(r'modal_id=(\d+)', long_url)
                        
                        if not id_match:
                            result["msg"] = "无法提取视频ID，链接可能无效或Cookie已过期"
                            return result
                        
                        item_id = id_match.group(2) if len(id_match.groups()) >= 2 else id_match.group(1)
                except Exception as e:
                    result["msg"] = f"链接访问失败: {e}"
                    return result

                # 2. 请求 V2 接口
                api_url = f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={item_id}"
                
                async with session.get(api_url, headers=self._get_headers()) as resp:
                    if resp.status != 200:
                        result["msg"] = f"接口请求失败: {resp.status}"
                        return result
                    
                    data = await resp.json()
                    item_list = data.get("item_list", [])
                    if not item_list:
                        result["msg"] = "解析内容为空 (可能被风控，请尝试更新Cookie)"
                        return result
                    item = item_list[0]

        except Exception as e:
            result["msg"] = f"解析异常: {e}"
            return result

        # --- 3. 提取数据 ---
        result["success"] = True
        result["desc"] = item.get("desc", "")
        result["title"] = result["desc"][:50]
        result["author"] = item.get("author", {}).get("nickname", "未知作者")

        images = item.get("images")
        
        if images:
            # === 图文 ===
            result["type"] = "image"
            for img in images:
                url_list = img.get("url_list", [])
                if url_list:
                    result["download_urls"].append(url_list[-1])
        else:
            # === 视频 ===
            result["type"] = "video"
            video_info = item.get("video", {})
            
            url_list = video_info.get("play_addr", {}).get("url_list", [])
            final_url = None
            
            for u in url_list:
                if "playwm" not in u:
                    final_url = u
                    break
            
            if not final_url and url_list:
                final_url = url_list[0].replace("playwm", "play")
            
            if final_url:
                result["video_url"] = final_url
                cover = video_info.get("cover", {}).get("url_list", [""])[0]
                result["download_urls"] = [cover]
            else:
                result["msg"] = "未找到视频地址"
                return result

        return result