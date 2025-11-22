import os
import aiohttp
import random
from astrbot.api import logger

class SmartDownloader:
    @staticmethod
    async def download(url: str, save_path: str, cookie: str = None) -> bool:
        """
        智能下载器 v2.3.0：复刻自参考项目的5种抗403策略
        """
        if not url: return False

        # 1. 检查缓存
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            return True

        # 2. 定义5种策略 (直接来自参考项目)
        strategies = [
            {
                "name": "桌面端",
                "headers": {
                    'Accept': 'image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Referer': 'https://www.douyin.com/',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                },
                "use_cookie": True
            },
            {
                "name": "iPhone",
                "headers": {
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh-Hans;q=0.9',
                    'Connection': 'keep-alive',
                    'Referer': 'https://www.douyin.com/',
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
                },
                "use_cookie": True
            },
            {
                "name": "Android",
                "headers": {
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Connection': 'keep-alive',
                    'Referer': 'https://www.douyin.com/',
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36'
                },
                "use_cookie": True
            },
            {
                "name": "抖音APP (强力抗403)",
                "headers": {
                    'Accept': '*/*',
                    'Connection': 'keep-alive',
                    'User-Agent': 'com.ss.android.ugc.aweme/180400 (Linux; U; Android 11; zh_CN; SM-G973F; Build/RP1A.200720.012)',
                    'X-Requested-With': 'com.ss.android.ugc.aweme'
                },
                "use_cookie": False # 关键：APP策略不带 Web Cookie
            },
            {
                "name": "爬虫模式",
                "headers": {
                    'User-Agent': 'Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)',
                    'Accept': '*/*'
                },
                "use_cookie": False
            }
        ]

        # 3. 循环尝试
        for i, strategy in enumerate(strategies):
            name = strategy["name"]
            headers = strategy["headers"].copy()
            
            # 注入 Cookie (仅针对允许 Cookie 的策略)
            if cookie and strategy["use_cookie"]:
                headers["Cookie"] = cookie

            try:
                async with aiohttp.ClientSession() as session:
                    # 缩短单次连接超时，加快轮询速度
                    timeout = aiohttp.ClientTimeout(total=30, connect=10)
                    async with session.get(url, headers=headers, timeout=timeout) as resp:
                        
                        if resp.status == 200:
                            content = await resp.read()
                            if len(content) > 1000: 
                                with open(save_path, 'wb') as f:
                                    f.write(content)
                                logger.info(f"下载成功 (策略: {name}): {os.path.basename(save_path)}")
                                return True
                            else:
                                logger.warning(f"[{name}] 文件过小 ({len(content)}b)，重试...")
                        
                        elif resp.status == 403:
                            # 403 是正常的，静默跳过即可，不用刷屏警告
                            # logger.debug(f"[{name}] 遇到 403，尝试下一策略...")
                            continue
                        
                        else:
                            logger.warning(f"[{name}] HTTP {resp.status}")

            except Exception as e:
                logger.warning(f"[{name}] 下载异常: {e}")

        logger.error(f"❌ 所有 {len(strategies)} 种策略均失败，无法下载: {url}")
        return False