import re
import httpx
from astrbot.api import Plugin, Context, Event
from astrbot.api.star import register, event_message

XHS_REGEX = r"(http[s]?://[^\s]+xhs[^\s]+|xhslink\.com/\S+)"

@register
class XHSDownloaderPlugin(Plugin):
    slug = "astrbot_plugin_parse_hub"
    name = "小红书作品解析下载插件"
    desc = "自动解析小红书作品并发送图片/视频资源"

    def __init__(self, context: Context, config=None, *args, **kwargs):
        super().__init__(context)
        self.context = context

        # 从 config 读取，而不是 context.get_plugin_conf()
        if config is None:
            config = {}

        self.docker_url = config.get(
            "XHS_DOWNLOADER_URL",
            "http://127.0.0.1:5556/xhs/"
        ).rstrip("/") + "/"

        self.logger.info(f"[XHS Plugin] 服务地址: {self.docker_url}")

    @event_message()
    async def download_handler(self, event: Event):
        message = event.text or ""
        match = re.search(XHS_REGEX, message)
        if not match:
            return

        xhs_url = match.group(0)
        await event.reply(f"🔍 正在解析...\n{ xhs_url }")

        try:
            async with httpx.AsyncClient(timeout=40) as client:
                r = await client.post(self.docker_url, json={"url": xhs_url})
                data = r.json()

            self.logger.info(f"[XHS Plugin] Response: {data}")

            if not data or "error" in data:
                await event.reply("❌ 解析失败：" + data.get("error", "未知错误"))
                return

            if title := data.get("title"):
                await event.reply("📌 " + title)

            for img in data.get("images", []):
                await event.reply_image(img)

            for video in data.get("videos", []):
                await event.reply_video(video)

            await event.reply("🎉 下载完成！")

        except Exception as e:
            self.logger.error(f"请求失败: {e}")
            await event.reply(f"⚠️ 请求失败：{str(e)}")
