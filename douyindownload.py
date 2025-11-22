import os
import aiohttp
import random
from astrbot.api import logger

class SmartDownloader:
    @staticmethod
    async def download(url: str, save_path: str, cookie: str = None, referer: str = None) -> bool:
        """
        智能下载器 v3.0.0：通用版，支持自定义Referer
        """
        if not url: return False

        # 1. 检查缓存
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            return True

        # 默认 Referer
        if not referer:
            # 如果没传，根据 URL 简单猜测，或者留空
            if "douyin" in url: referer = "https://www.douyin.com/"
            elif "bili" in url: referer = "https://www.bilibili.com/"
            elif "xiaohongshu" in url: referer = "https://www.xiaohongshu.com/"
            else: referer = ""

        # 2. 定义策略池
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
                "name": "无Referer模式", # 专门解决防盗链
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    # 不带 Referer
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

        # 3. 循环尝试
        for i, strategy in enumerate(strategies):
            name = strategy["name"]
            headers = strategy["headers"].copy()
            
            # 注入 Cookie
            if cookie and strategy["use_cookie"]:
                headers["Cookie"] = cookie

            # 清理空的 Referer (防止 requests 报错或特征被识别)
            if "Referer" in headers and not headers["Referer"]:
                del headers["Referer"]

            try:
                async with aiohttp.ClientSession() as session:
                    timeout = aiohttp.ClientTimeout(total=60, connect=15)
                    async with session.get(url, headers=headers, timeout=timeout) as resp:
                        
                        if resp.status == 200:
                            content = await resp.read()
                            if len(content) > 1000: 
                                with open(save_path, 'wb') as f:
                                    f.write(content)
                                # logger.info(f"下载成功 ({name}): {os.path.basename(save_path)}")
                                return True
                            else:
                                pass # 文件太小
                        elif resp.status == 403:
                            pass # 403 Forbidden
                        
            except Exception as e:
                # logger.warning(f"[{name}] 下载异常: {e}")
                pass

        logger.error(f"❌ 下载失败，所有策略均无效: {url}")
        return False