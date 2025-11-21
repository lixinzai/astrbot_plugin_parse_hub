import re
import httpx
from astrbot.api import Plugin, Context, Event
from astrbot.api.star import register, event_message

XHS_REGEX = r"(http[s]?://[^\s]+xhs[^\s]+|xhslink\.com/\S+)"

@register
class XHSDownloaderPlugin(Plugin):
    slug = "astrbot_plugin_parse_hub"
    name = "小红书作品解析下载插件"
    desc = "自动解析小红书作品并发送图片和视频资源"

    def __init__(self, context: Context, *args, **kwargs):
        super().__init__(context)
        # ⚠️ 不要访问 self.context.plugin_conf 或 self.context.conf
        # 这里只定义属性即可

    @event_message()
    async def download_handler(self, event: Event):
        msg = event.text
        if not msg:
            return

        match = re.search(XHS_REGEX, msg)
        if not match:
            return

        xhs_url = match.group(0)
        await event.reply(f"🔍 正在解析...\n{xhs_url}")

        # 动态读取配置
        docker_url = getattr(self.context, "get_conf", lambda k, d=None: d)("XHS_DOWNLOADER_URL", "http://127.0.0.1:5556/xhs/")
        docker_url = docker_url.rstrip("/") + "/"

        payload = {"url": xhs_url}

        try:
            async with httpx.AsyncClient(timeout=35) as client:
                r = await client.post(docker_url, json=payload)
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

            await event.reply("🎉 完成！")

        except Exception as e:
            await event.reply(f"⚠️ 请求失败：{e}")
