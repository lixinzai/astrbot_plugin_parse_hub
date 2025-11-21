import os
import tempfile
import httpx
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("xhs_downloader", "YourName", "小红书下载插件，支持多图多视频和进度提示", "1.0.7")
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
            event.plain_result("请提供小红书作品链接，例如：/xhs https://www.xiaohongshu.com/xxxx")
            return

        link = text.split()[0]

        # 保证 docker_url 为字符串
        docker_url = self.context.get_config("XHS_DOWNLOADER_URL")
        if not docker_url or not isinstance(docker_url, str):
            docker_url = "http://localhost:5000/download"

        # 初始化提示
        event.plain_result("正在解析并下载，请稍等...")

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(docker_url, params={"url": link})
                if resp.status_code != 200:
                    event.plain_result(f"下载服务返回错误: {resp.status_code}")
                    return
                result = resp.json()

            with tempfile.TemporaryDirectory() as tmpdir:
                total_items = 0
                if "video" in result and result["video"]:
                    total_items += len(result["video"])
                if "images" in result and result["images"]:
                    total_items += len(result["images"])
                downloaded = 0

                # 下载视频
                if "video" in result and result["video"]:
                    for idx, vurl in enumerate(result["video"]):
                        fname = os.path.join(tmpdir, f"video_{idx}.mp4")
                        await self.download_file(vurl, fname)
                        event.video_result(fname)
                        downloaded += 1
                        event.plain_result(f"下载进度: {downloaded}/{total_items}")

                # 下载图片
                if "images" in result and result["images"]:
                    for idx, iurl in enumerate(result["images"]):
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
        """异步下载文件"""
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.get(url)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)

    async def terminate(self):
        logger.info("XHSDownloaderPlugin 已卸载")
