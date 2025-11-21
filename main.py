import re
import httpx
from astrbot.api import Plugin, Context, Event
from astrbot.api.star import register, event_message, Handler

XHS_REGEX = r"(http[s]?://[^\s]+xhs[^\s]+|xhslink\.com/\S+)"

@register
class XHSDownloaderPlugin(Plugin):
    def __init__(self, context: Context, *args, **kwargs):
        super().__init__(context)
        self.name = "小红书作品解析下载插件"
        self.desc = "自动解析小红书作品，图片/视频自动发送"

        self.context = context
        
        # 兼容不同 AstrBot 版本的配置获取方式
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
        await event.reply(f"🔍 正在解析小红书作品…\n{ xhs_url }")

        payload = {"url": xhs_url}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(self.docker_url, json=payload)
                data = r.json()

            if "error" in data:
                await event.reply(f"❌ 解析失败：{data['error']}")
                return

            # 标题
            if title := data.get("title"):
                await event.reply(f"📌 {title}")

            # 发送图片
            for img in data.get("images", []):
                await event.reply_image(img)

            # 发送视频
            for video in data.get("videos", []):
                await event.reply_video(video)

            await event.reply("🎉 下载完成！")

        except Exception as e:
            await event.reply(f"⚠️ 解析失败：{str(e)}")
