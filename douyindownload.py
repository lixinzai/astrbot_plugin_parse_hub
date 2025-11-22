import os
import aiohttp
import random
from astrbot.api import logger

class SmartDownloader:
    @staticmethod
    async def download(url: str, save_path: str, cookie: str = None) -> bool:
        """
        智能下载器：支持自动切换UA、移除Referer以绕过403防盗链
        """
        if not url: return False

        # 1. 检查缓存
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            return True

        # 2. 准备策略池
        # 关键修改：增加了 "无 Referer" 的策略 (Strategy 3 & 4)
        # 很多图床(douyinpic)带了 Referer 反而会报 403
        strategies = [
            {   # 策略1: 桌面端 + 抖音Referer (标准)
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.douyin.com/"
                },
                "desc": "桌面端+Referer"
            },
            {   # 策略2: 移动端 + 抖音Referer
                "headers": {
                    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                    "Referer": "https://www.douyin.com/"
                },
                "desc": "移动端+Referer"
            },
            {   # 策略3: 桌面端 + 无Referer (修复图片403的关键)
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    #以此模拟直接访问链接
                },
                "desc": "桌面端(无Referer)"
            },
            {   # 策略4: 纯净模式 (模拟Wget/Curl)
                "headers": {
                    "User-Agent": "Wget/1.21.2",
                    "Accept": "*/*"
                },
                "desc": "Wget模式"
            }
        ]

        # 注入 Cookie (如果有)，但仅对前两个策略注入
        # 有些CDN带了错误的Cookie也会403，所以策略3/4保持纯净
        if cookie:
            for i in range(2):
                strategies[i]["headers"]["Cookie"] = cookie

        # 3. 循环尝试下载
        for i, strategy in enumerate(strategies):
            headers = strategy["headers"]
            desc = strategy["desc"]
            
            try:
                async with aiohttp.ClientSession() as session:
                    timeout = aiohttp.ClientTimeout(total=60, connect=15)
                    async with session.get(url, headers=headers, timeout=timeout) as resp:
                        
                        if resp.status == 200:
                            content = await resp.read()
                            if len(content) > 1000: 
                                with open(save_path, 'wb') as f:
                                    f.write(content)
                                logger.info(f"下载成功 (策略{i+1}-{desc}): {os.path.basename(save_path)}")
                                return True
                            else:
                                logger.warning(f"策略{i+1} 下载文件过小 ({len(content)}b)，重试...")
                        
                        elif resp.status == 403:
                            logger.warning(f"下载遇到 403 (策略{i+1}-{desc})，尝试下一策略...")
                            continue
                        
                        else:
                            logger.error(f"下载失败 (策略{i+1}): HTTP {resp.status}")

            except Exception as e:
                logger.error(f"下载出错 (策略{i+1}): {e}")

        logger.error(f"❌ 所有下载策略均失败: {url}")
        return False