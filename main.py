from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import httpx
import asyncio

@register("xhs_downloader", "August", "小红书解析下载插件", "1.0.0")
class XHSDownloaderPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 从插件配置读取 Docker URL
        self.docker_url = self.context.plugin_data.get("XHS_DOWNLOADER_URL") or "http://127.0.0.1:5556/xhs/"

    async def initialize(self):
        """插件初始化"""
        logger.info(f"[XHSDownloaderPlugin] 使用 Docker URL: {self.docker_url}")

    @filter.command("xhs")
    async def download_handler(self, event: AstrMessageEvent):
        """下载小红书作品"""
        user_name = event.get_sender_name()
        message_str = event.message_str.strip()

        if not message_str.startswith("http"):
            return MessageEventResult(f"错误: URL 必须以 http:// 或 https:// 开头。")

        payload = {"url": message_str, "download": False}

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                r = await client.post(self.docker_url, json=payload)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                logger.exception("XHS 下载请求失败")
                return MessageEventResult(f"请求失败: {str(e)}")

        result_msg = f"[{user_name}] 解析成功:\n作品标题: {data['data'].get('作品标题','未知')}\n作者: {data['data'].get('作者昵称','未知')}\n点赞: {data['data'].get('点赞数量','0')}\n评论: {data['data'].get('评论数量','0')}"
        return MessageEventResult(result_msg)

    async def terminate(self):
        """插件卸载/停用"""
        logger.info("[XHSDownloaderPlugin] 卸载完成")
