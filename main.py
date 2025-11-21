from astrbot.api.star import Context, Star, register
import re
import httpx

XHS_REGEX = r"(http[s]?://[^\s]+xhs[^\s]+|xhslink\.com/\S+)"

@register("xhs_downloader", "YourName", "小红书作品解析下载插件", "1.0.0")
class XHSDownloaderPlugin(Star):

    def __init__(self, context: Context):
        super().__init__(context)
        self.name = "小红书作品解析下载插件"
        self.desc = "自动解析小红书作品，发送图片和视频"
        self.docker_url = context.get_conf("XHS_DOWNLOADER_URL") or "http://127.0.0.1:5556/xhs/"
        self.docker_url = self.docker_url.rstrip("/") + "/"

    async def initialize(self):
        """异步初始化方法，可选"""
        pass

    @Star.event_message()
    async def download_handler(self, event):
        message = event.text or ""
        match = re.search(XHS_REGEX, message)
        if not match:
            return

        xhs_url = match.group(0)
        await event.reply(f"🔍 正在解析...\n{xhs_url}")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(self.docker_url, json={"url": xhs_url})
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

    async def terminate(self):
        """插件被卸载或停用时调用"""
        pass
