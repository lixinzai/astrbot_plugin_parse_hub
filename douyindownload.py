import os
import aiohttp
import random
from astrbot.api import logger

class SmartDownloader:
    @staticmethod
    async def download(url: str, save_path: str, cookie: str = None, referer: str = None) -> bool:
        if not url: return False
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0: return True

        if not referer:
            if "douyin" in url: referer = "https://www.douyin.com/"
            elif "bili" in url: referer = "https://www.bilibili.com/"
            elif "xiaohongshu" in url: referer = "https://www.xiaohongshu.com/"
            else: referer = ""

        strategies = [
            {
                "name": "标准桌面端",
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": referer
                },
                "use_cookie": True
            },
            {
                "name": "移动端",
                "headers": {
                    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                    "Referer": referer
                },
                "use_cookie": True
            },
            {
                "name": "无Referer模式",
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
                "use_cookie": False 
            },
            {
                "name": "APP仿真模式",
                "headers": {
                    "User-Agent": "com.ss.android.ugc.aweme/180400 (Linux; U; Android 11; zh_CN; SM-G973F; Build/RP1A.200720.012)",
                    "X-Requested-With": "com.ss.android.ugc.aweme"
                },
                "use_cookie": False
            }
        ]

        for i, strategy in enumerate(strategies):
            name = strategy["name"]
            headers = strategy["headers"].copy()
            if cookie and strategy["use_cookie"]: headers["Cookie"] = cookie
            if "Referer" in headers and not headers["Referer"]: del headers["Referer"]

            try:
                async with aiohttp.ClientSession() as session:
                    timeout = aiohttp.ClientTimeout(total=60, connect=15)
                    async with session.get(url, headers=headers, timeout=timeout) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            if len(content) > 1000: 
                                with open(save_path, 'wb') as f: f.write(content)
                                return True
                        elif resp.status == 403: continue
            except Exception: pass

        logger.error(f"❌ 下载失败: {url}")
        return False