import os
import aiohttp
import random
from astrbot.api import logger

class SmartDownloader:
    @staticmethod
    async def download(url: str, save_path: str, cookie: str = None) -> bool:
        """
        智能下载器：支持断点续传(伪)、403重试、自动切换User-Agent
        """
        if not url: return False

        # 1. 检查缓存
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            # 简单的缓存检查：文件存在且大小大于0，认为已下载
            # 为了防止文件损坏，可以在外部通过 modify time 定期清理
            return True

        # 2. 准备策略 (桌面端 + 移动端)
        headers_list = [
            { # 策略A: 桌面端 Chrome
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.douyin.com/"
            },
            { # 策略B: 移动端 Safari (解决部分 403 问题)
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                "Referer": "https://www.douyin.com/"
            },
            { # 策略C: 移动端 Android
                "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
                "Referer": "https://www.douyin.com/"
            }
        ]

        # 注入 Cookie (如果有)
        if cookie:
            for h in headers_list:
                h["Cookie"] = cookie

        # 3. 循环尝试下载
        for attempt, headers in enumerate(headers_list):
            try:
                async with aiohttp.ClientSession() as session:
                    # 设置较长的超时，防止大视频断连
                    timeout = aiohttp.ClientTimeout(total=60, connect=10)
                    async with session.get(url, headers=headers, timeout=timeout) as resp:
                        
                        if resp.status == 200:
                            content = await resp.read()
                            # 简单的校验：文件太小可能是错误页
                            if len(content) > 1000: 
                                with open(save_path, 'wb') as f:
                                    f.write(content)
                                logger.info(f"下载成功 (策略 {attempt+1}): {os.path.basename(save_path)}")
                                return True
                            else:
                                logger.warning(f"下载文件过小 ({len(content)} bytes)，可能无效，重试中...")
                        
                        elif resp.status == 403:
                            logger.warning(f"下载遇到 403 Forbidden (策略 {attempt+1})，切换 Header 重试...")
                            continue # 换下一个 Header
                        
                        else:
                            logger.error(f"下载返回异常状态码: {resp.status}")

            except Exception as e:
                logger.error(f"下载过程出错 (策略 {attempt+1}): {e}")
                # 继续尝试下一个策略

        logger.error(f"所有下载策略均失败: {url}")
        return False