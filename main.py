import re
import httpx
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import AstrMessageEvent

XHS_REGEX = r"(http[s]?://[^\s]+xhs[^\s]+|xhslink\.com/\S+)"

@register("astrbot_plugin_parse_hub", "YourName", "解析小红书作品并发送图片/视频资源", "1.0.0")
class XHSDownloaderPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # ⚠️ 这里不要访问 context 的配置
        self.slug = "astrbot_plugin_parse_hub"

    async def initialize(self):
        """插件异步初始化，可选"""
        logger.info("XHSDownloaderPlugin 初始化完成")

    @filter.command("xhsparse")
    async def download_handler(self, event: AstrMessageEvent):
        """解析小红书作品并发送图片/视频"""
        message = event.message_str or ""
        match = re.search(XHS_REGEX, message)
        if not match:
            return

        xhs_url = match.group(0)
        await event.plain_result(f"🔍 正在解析...\n{xhs_url}")

        # 获取配置
        try:
            docker_url = self.context.get_conf("XHS_DOWNLOADER_URL")
        except Exception:
            docker_url = "http://127.0.0.1:5556/xhs/"
        docker_url = docker_url.rstrip("/") + "/"

        payload = {"url": xhs_url}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(docker_url, json=payload)
                data = r.json()

            if "error" in data:
                await event.plain_result("❌ 解析失败：" + data["error"])
                return

            if title := data.get("title"):
                await event.plain_result("📌 " + title)

            for img in data.get("images", []):
                await event.plain_result(f"[图片] {img}")  # 根据实际组件，可换 event.send_image()

            for video in data.get("videos", []):
                await event.plain_result(f"[视频] {video}")  # 根据实际组件，可换 event.send_video()

            await event.plain_result("🎉 下载完成！")

        except Exception as e:
            await event.plain_result(f"⚠️ 请求失败：{e}")

    async def terminate(self):
        """插件卸载/停用时调用"""
        logger.info("XHSDownloaderPlugin 已卸载")
