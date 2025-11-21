import httpx
from astrbot.api.star import Star
from astrbot.api.event import Event
from astrbot.api.message.components import Text, Image, Video
from astrbot.api.plugin import register

@register
class XHSDownloaderPlugin(Star):
    def __init__(self, context):
        super().__init__(context)
        self.name = "小红书作品解析下载插件"
        self.desc = "支持小红书作品解析、图片与视频自动发送"
        self.context = context

        # 读取插件配置（来自 _conf_schema.json）
        self.docker_url = context.get_conf("XHS_DOWNLOADER_URL") or "http://127.0.0.1:5556/xhs/"

        # 规整 URL
        self.docker_url = self.docker_url.rstrip("/") + "/"

    async def on_message(self, event: Event):
        text = event.text_content.strip()

        # 自动触发：只要消息中包含小红书链接
        if "xhs" in text or "小红书" in text or "xhslink.com" in text:
            self.log.info(f"检测到小红书链接：{text}")
            await self.download_handler(event, text)

    async def download_handler(self, event: Event, url: str):
        await event.reply(Text("正在解析作品，请稍候... ⏳"))

        async with httpx.AsyncClient() as client:
            try:
                api_url = self.docker_url + "info"
                self.log.info(f"请求接口 -> {api_url}")

                res = await client.post(
                    api_url,
                    json={"url": url},
                    timeout=60
                )

                data = res.json()
                self.log.info(f"返回数据 -> {data}")

            except Exception as e:
                await event.reply(Text(f"解析失败 ❌\n错误：{str(e)}"))
                return

        # 如果解析失败，给出提示
        if not data.get("status"):
            await event.reply(Text("解析失败：未找到可下载资源 ❌"))
            return

        title = data.get("title") or "小红书作品"

        # 回复作品标题
        await event.reply(Text(f"📌 {title}"))

        images = data.get("images", [])
        videos = data.get("videos", [])

        # 处理图片
        for img_url in images:
            await event.reply(Image(url=img_url))

        # 处理视频
        for vid_url in videos:
            await event.reply(Video(url=vid_url))

        # 无资源情况
        if not images and not videos:
            await event.reply(Text("作品解析成功，但找不到资源可发送 ❗"))
        else:
            await event.reply(Text("已全部发送完毕 🎉"))
