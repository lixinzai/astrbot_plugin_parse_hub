import re
import os
import time
import aiohttp
import json
import hashlib
import asyncio
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Video

@register("xhs_parse_hub", "YourName", "小红书去水印解析插件", "1.1.2")
class XhsParseHub(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url = config.get("api_url", "http://127.0.0.1:5556/xhs/")
        self.enable_cache = config.get("enable_download_cache", True)
        
        # [修改点] 获取当前文件(main.py)所在的目录
        current_plugin_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 在本插件目录下创建 xhs_cache 文件夹
        self.cache_dir = os.path.join(current_plugin_dir, "xhs_cache")
        
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            
        # 用于存储定时任务的句柄
        self.cleanup_task = None

    async def initialize(self):
        logger.info(f"小红书解析插件加载成功。API: {self.api_url}")
        logger.info(f"本地缓存: {'开启' if self.enable_cache else '关闭'}, 缓存路径: {self.cache_dir}")
        
        # 启动自动清理任务
        if self.enable_cache:
            self.cleanup_task = asyncio.create_task(self._auto_cleanup_loop())
            logger.info("✅ 已启动缓存自动清理任务 (每1小时清理一次过期文件)")

    async def terminate(self):
        """插件卸载或机器人关闭时调用"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            logger.info("🛑 缓存自动清理任务已停止")

    async def _auto_cleanup_loop(self):
        """后台循环任务：每隔1小时清理超过1小时未修改的文件"""
        while True:
            try:
                # 先等待1小时再清理
                await asyncio.sleep(3600)
                
                logger.info("🧹 开始执行缓存清理...")
                count = 0
                now = time.time()
                # 遍历目录
                if os.path.exists(self.cache_dir):
                    for filename in os.listdir(self.cache_dir):
                        file_path = os.path.join(self.cache_dir, filename)
                        # 跳过文件夹
                        if not os.path.isfile(file_path):
                            continue
                            
                        # 获取文件最后修改时间
                        file_mtime = os.path.getmtime(file_path)
                        
                        # 如果文件超过 1 小时 (3600秒) 未被修改，则删除
                        if now - file_mtime > 3600:
                            try:
                                os.remove(file_path)
                                count += 1
                            except Exception as e:
                                logger.error(f"删除文件失败 {filename}: {e}")
                            
                if count > 0:
                    logger.info(f"🧹 缓存清理完成，共释放 {count} 个文件。")
                else:
                    logger.info("🧹 缓存清理完成，没有需要删除的文件。")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"缓存清理任务出错: {e}")
                await asyncio.sleep(60)

    def extract_url(self, text: str):
        pattern = r'(https?://[^\s]+)'
        match = re.search(pattern, text)
        if match:
            return match.group(0)
        return None

    async def download_file(self, url: str, suffix: str = "") -> str:
        """下载文件到本地缓存"""
        if not url: return None
        try:
            file_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
            filename = f"{file_hash}{suffix}"
            file_path = os.path.join(self.cache_dir, filename)

            # 缓存命中
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                os.utime(file_path, None) # 刷新修改时间
                return file_path

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        with open(file_path, 'wb') as f:
                            f.write(content)
                        return file_path
                    else:
                        logger.error(f"下载失败 {resp.status}: {url}")
                        return None
        except Exception as e:
            logger.error(f"下载异常: {e}")
            return None

    @filter.command("xhs")
    async def xhs_parse(self, event: AstrMessageEvent):
        """小红书解析指令"""
        message_str = event.message_str
        target_url = self.extract_url(message_str)
        
        if not target_url:
            if "http" in message_str:
                target_url = message_str.strip()
            else:
                yield event.plain_result("⚠️ 请提供包含小红书链接的消息。")
                return

        yield event.plain_result("🔍 正在解析，请稍候...")

        # --- 1. 请求 API ---
        res_json = None
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=60)
                async with session.post(self.api_url, json={"url": target_url}, timeout=timeout) as resp:
                    if resp.status != 200:
                        yield event.plain_result(f"❌ 解析请求失败: {resp.status}")
                        return
                    res_json = await resp.json()
        except Exception as e:
            logger.error(f"API请求异常: {e}")
            yield event.plain_result(f"❌ 连接解析服务超时或错误: {e}")
            return

        # --- 2. 提取数据 ---
        data = res_json.get("data")
        if not data:
            msg = res_json.get("message", "未知错误")
            yield event.plain_result(f"❌ 解析失败: {msg}")
            return

        title = data.get("作品标题", "无标题")
        author = data.get("作者昵称", "未知作者")
        desc = data.get("作品描述", "")
        work_type = data.get("作品类型", "")
        
        download_urls = data.get("下载地址", [])
        dynamic_urls = data.get("动图地址", [])

        # --- 3. 构建文本 (包含直链) ---
        info_text = f"【标题】{title}\n【作者】{author}\n\n{desc}"
        if len(info_text) > 250:
            info_text = info_text[:250] + "...\n(文案过长已折叠)"

        # 视频直链
        video_direct_link = None
        if work_type == "视频" and download_urls:
            video_direct_link = download_urls