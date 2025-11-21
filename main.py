import re
import httpx
from astrbot.api import Plugin, Context, Event
from astrbot.api.star import register, event_message

XHS_REGEX = r"(http[s]?://[^\s]+xhs[^\s]+|xhslink\.com/\S+)"

@register
class XHSDownloaderPlugin(Plugin):

    # 接受 config 避免参数报错
    def __init__(self, context: Context, config=None, *args, **kwargs):
        super().__init__(context)
        self.context = context

        self.name = "小红书作品解析下载插件"
        self.desc = "自动解析小红书作品，发送图片视频"

        # 使用 AstrBot 官方 API 获取配置值
        try:
            self.docker_url = context.get_conf("XHS_DOWNLOADER_URL")
        except Exception:
            self.docker_url = None

        if not self.docker_url:
            self.docker_url = "http://127.0.0.1:5556/xhs/"

        self.docker_url = self.docker_url.rstrip("/") + "/"

    @event_message()
    async def download_handler(self, event: Event):
        message = event.text or ""
        match = re.search(XHS_REGEX, message)
        if not match:
            return

        xhs_url = match.group(0)
        await event.reply(f"🔍 正在解析...\n{ xhs_url }")

        payload = {"url": xhs_url}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(self.docker_url, json=payload)
                data = r.json()

            if "error" in data:
                await event.reply("❌ 解析失败：" + data["error"])
                return

            if title := data.get("title"):
                await event.reply("📌 " + title)

            for img in data.get("images", []):
                await event.reply_image(img)

            for video in data.get("videos", []):
                await event.reply_video(video)

            await event.reply("🎉 下载完成！")

        except Exception as e:
            await event.reply("⚠️ 请求失败：" + str(e))
