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

    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context

        # ★ 兼容 AstrBot v4.6.0 的配置访问方式
        conf = getattr(context, "conf", {}) or {}
        self.docker_url = conf.get(
            "XHS_DOWNLOADER_URL",
            "http://127.0.0.1:5556/xhs/"
        ).rstrip("/") + "/"

        self.logger.info(f"[XHS Plugin] Docker 服务: {self.docker_url}")

    @event_message()
    async def download_handler(self, event: Event):
        if not (message := event.text):
            return

        match = re.search(XHS_REGEX, message)
        if not match:
            return

        xhs_url = match.group(0)
        await event.reply(f"🔍 正在解析...\n{xhs_url}")

        try:
            async with httpx.AsyncClient(timeout=40) as client:
                response = await client.post(self.docker_url, json={"url": xhs_url})
                data = response.json()

            self.logger.info(f"[XHS Plugin] Response: {data}")

            if "error" in data:
                await event.reply("❌ 解析失败：" + data["error"])
                return

            if title := data.get("title"):
                await event.reply("📌 " + title)

            for img in data.get("images", []):
                await event.reply_image(img)

            for vid in data.get("videos", []):
                await event.reply_video(vid)

            await event.reply("🎉 下载完成！")

        except Exception as e:
            self.logger.error(f"请求异常: {e}")
            await event.reply(f"⚠️ 请求失败：{e}")
