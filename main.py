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

    def __init__(self, context: Context, config=None, *args, **kwargs):
        super().__init__(context)
        self.context = context
        self.config = config or {}

        # 这里不要访问 context.conf，会导致加载失败

    def get_conf(self, key: str, default=None):
        # 优先使用插件配置文件传入值
        if key in self.config:
            return self.config[key]

        # 兼容 context.conf 存在但空的情况
        context_conf = getattr(self.context, "conf", {})
        if context_conf and key in context_conf:
            return context_conf[key]

        return default

    @event_message()
    async def download_handler(self, event: Event):
        msg = event.text
        if not msg:
            return

        match = re.search(XHS_REGEX, msg)
        if not match:
            return

        xhs_url = match.group(0)

        # 动态读取配置（确保 config 已注入）
        docker_url = self.get_conf("XHS_DOWNLOADER_URL", "http://127.0.0.1:5556/xhs/")
        docker_url = docker_url.rstrip("/") + "/"

        await event.reply(f"🔍 正在解析...\n{xhs_url}")

        try:
            async with httpx.AsyncClient(timeout=35) as client:
                resp = await client.post(docker_url, json={"url": xhs_url})
                data = resp.json()

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
