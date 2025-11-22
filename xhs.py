import aiohttp
import re
import json
from astrbot.api import logger

class XhsHandler:
    def __init__(self, api_url: str):
        self.api_url = api_url

    def extract_url(self, text: str):
        pattern = r'(https?://[^\s]+)'
        match = re.search(pattern, text)
        if match: return match.group(0)
        return None

    async def parse(self, target_url: str) -> dict:
        result = {
            "success": False, "msg": "", "type": "unknown",
            "title": "", "author": "", "desc": "",
            "download_urls": [], "dynamic_urls": [], "video_url": None
        }

        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=15)
                async with session.post(self.api_url, json={"url": target_url}, timeout=timeout) as resp:
                    if resp.status != 200:
                        result["msg"] = f"API请求失败，状态码: {resp.status}"
                        return result
                    res_json = await resp.json()
        except Exception as e:
            result["msg"] = f"连接解析服务出错: {e}"
            return result

        data = res_json.get("data")
        if not data:
            result["msg"] = res_json.get("message", "解析服务返回未知错误")
            return result

        result["success"] = True
        result["title"] = data.get("作品标题", "无标题")
        result["author"] = data.get("作者昵称", "未知作者")
        result["desc"] = data.get("作品描述", "")
        raw_type = data.get("作品类型", "")
        result["download_urls"] = data.get("下载地址", [])
        result["dynamic_urls"] = data.get("动图地址", [])

        if raw_type == "视频":
            result["type"] = "video"
            if result["download_urls"]: result["video_url"] = result["download_urls"][0]
        elif raw_type == "图文":
            result["type"] = "image"
        else:
            result["type"] = "unknown"

        return result