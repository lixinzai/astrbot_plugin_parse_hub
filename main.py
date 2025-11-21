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

        # 读取插件配置
        conf = context.get_plugin_conf(self.slug)
        if conf is None:
            conf = {}

        self.docker_url = conf.get(
            "XHS_DOWNLOADER_URL",
            "http://127.0.0.1:5556/xhs/"
        ).rstrip("/") + "/"

        self.logger.info(f"[XHS Plugin] 小红书服务地址: {self.docker_url}")

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
            async with httpx.AsyncClient(timeout=40) as client:
                r = await client.post(self.docker_url, json=payload)
                data = r.json()

            self.logger.info(f"[XHS Plugin] 响应内容: {data}")

            if not data or "error" in data:
                await event.reply("❌ 解析失败：" + data.get("error", "未知错误"))
                return

            # 标题先发
            if title := data.get("title"):
                await event.reply("📌 " + title)

            # 发送图片
            images = data.get("images") or []
            for img in images:
                await event.reply_image(img)

            # 发送视频
            videos = data.get("videos") or []
            for video in videos:
                await event.reply_video(video)

            await event.reply(f"🎉 下载完成！共 {len(images)} 图 {len(videos)} 视频")

        except Exception as e:
            self.logger.error(f"[XHS Plugin] 请求失败: {e}")
            await event.reply(f"⚠️ 请求失败：{str(e)}")
