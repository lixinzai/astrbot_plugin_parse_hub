import httpx
import os
import tempfile
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("xhs_downloader", "AstrBot臣", "小红书作品下载插件", "1.0.0")
class XHSDownloaderPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """插件初始化方法"""
        logger.info("XHSDownloaderPlugin 初始化完成")

    @filter.command("xhs")
    async def download_handler(self, event: AstrMessageEvent):
        """下载小红书作品"""
        text = event.message_str.strip()
        if not text:
            return event.plain_result(
                "请提供小红书作品链接，例如：/xhs https://www.xiaohongshu.com/xxxx"
            )

        link = text.split()[0].strip()
        if not link.startswith("http://") and not link.startswith("https://"):
            link = "http://" + link

        # 获取 Docker URL 配置
        docker_url = self.context.get_config("XHS_DOWNLOADER_URL")
        if not docker_url:
            docker_url = "http://127.0.0.1:5556/xhs/"
        docker_url = docker_url.strip().rstrip("/") + "/xhs/"

        await event.plain_result("正在解析并下载，请稍等...")

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(docker_url, json={"url": link, "download": True})
                resp.raise_for_status()
                result = resp.json()

            data = result.get("data", {})
            files = data.get("下载地址", [])
            if not files:
                return await event.plain_result("未找到可下载内容")

            for url in files:
                if not url:
                    continue
                filename = url.split("/")[-1].split("?")[0]
                # 下载到临时文件
                tmp_path = os.path.join(tempfile.gettempdir(), filename)
                async with httpx.AsyncClient(timeout=120) as client:
                    r = await client.get(url)
                    r.raise_for_status()
                    with open(tmp_path, "wb") as f:
                        f.write(r.content)
                await event.send_file(tmp_path)

        except Exception as e:
            logger.error(f"XHSDownloaderPlugin 异常: {e}")
            await event.plain_result(f"插件异常: {e}")

    async def terminate(self):
        """插件销毁方法"""
        logger.info("XHSDownloaderPlugin 已被卸载")
