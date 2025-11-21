from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import httpx
import asyncio

@register("xhs_downloader", "August", "小红书解析与下载插件", "1.0.0")
class XHSDownloaderPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 获取插件配置
        self.docker_url = context.plugin_conf.get("XHS_DOWNLOADER_URL", "http://127.0.0.1:5556/xhs/")
        if not self.docker_url.startswith("http"):
            self.docker_url = "http://" + self.docker_url.strip().rstrip("/") + "/xhs/"
        else:
            self.docker_url = self.docker_url.strip().rstrip("/") + "/xhs/"

    async def initialize(self):
        """初始化插件"""
        logger.info(f"XHS Downloader initialized. Docker URL: {self.docker_url}")

    @filter.command("xhs")
    async def download_handler(self, event: AstrMessageEvent):
        """小红书下载指令"""
        try:
            message_str = event.message_str.strip()
            if not message_str.startswith("http"):
                message_str = "http://" + message_str  # 自动补全协议
            payload = {"url": message_str, "download": True}

            logger.info(f"Sending request to Docker: {self.docker_url} with payload: {payload}")

            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(self.docker_url, json=payload)
                response.raise_for_status()
                data = response.json()
                logger.info(f"Received data: {data}")

            # 发送结果消息
            msg = f"作品标题: {data.get('data', {}).get('作品标题', '未知')}\n" \
                  f"作者: {data.get('data', {}).get('作者昵称', '未知')}\n" \
                  f"下载地址: {data.get('data', {}).get('下载地址', [])}"
            return event.plain_result(msg)

        except Exception as e:
            logger.error(f"XHS Downloader plugin error: {e}")
            return event.plain_result(f"插件异常: {e}")

    async def terminate(self):
        """插件卸载/停用时调用"""
        logger.info("XHS Downloader plugin terminated.")
