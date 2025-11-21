import os
import tempfile
import httpx
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("xhs_downloader", "YourName", "小红书下载插件，支持多图多视频和进度提示", "1.5.1")
class XHSDownloaderPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        logger.info("XHSDownloaderPlugin 初始化完成")

    @filter.command("xhs")
    async def download_handler(self, event: AstrMessageEvent):
        """小红书下载指令 /xhs <作品链接>"""
        text = event.message_str.strip()
        if not text:
            return event.plain_result(
                "请提供小红书作品链接，例如：/xhs https://www.xiaohongshu.com/xxxx"
            )

        link = text.split()[0].strip()
        if not link.startswith("http://") and not link.startswith("https://"):
            link = "http://" + link

        # 通过 self.context.config 获取插件配置
        docker_url = self.context.config.get(
            "XHS_DOWNLOADER_URL", "http://192.168.2.99:5556/xhs/"
        )
        docker_url = docker_url.strip().rstrip("/") + "/xhs/"

        # 提示用户下载开始
        event.plain_result("正在解析并下载，请稍等...")

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(docker_url, json={"url": link, "download": True})
                resp.raise_for_status()
                result = resp.json()

            with tempfile.TemporaryDirectory() as tmpdir:
                total_items = 0
                videos = result.get("data", {}).get("下载地址", [])
                images = result.get("data", {}).get("动图地址", [])

                if videos:
                    total_items += len(videos)
                if images:
                    total_items += len([img for img in images if img])

                downloaded = 0

                # 下载视频
                for idx, vurl in enumerate(videos):
                    fname = os.path.join(tmpdir, f"video_{idx}.mp4")
                    await self.download_file(vurl, fname)
                    event.video_result(fname)
                    downloaded += 1
                    event.plain_result(f"下载进度: {downloaded}/{total_items}")

                # 下载图片
                for idx, iurl in enumerate(images):
                    if not iurl:
                        continue
                    fname = os.path.join(tmpdir, f"image_{idx}.jpg")
                    await self.download_file(iurl, fname)
                    event.image_result(fname)
                    downloaded += 1
                    event.plain_result(f"下载进度: {downloaded}/{total_items}")

            event.plain_result("下载完成！")

        except Exception as e:
            logger.error(f"插件异常: {e}")
            event.plain_result(f"插件异常: {e}")

    async def download_file(self, url, path):
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.get(url)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)

    async def terminate(self):
        logger.info("XHSDownloaderPlugin 已卸载")
