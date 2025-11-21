import os
import tempfile
import httpx
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("xhs_downloader", "YourName", "小红书下载插件，支持多图多视频和进度提示", "1.1.0")
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
            return event.plain_result("请提供小红书作品链接，例如：/xhs https://www.xiaohongshu.com/xxxx")

        link = text.split()[0].strip()
        # 自动补全用户输入链接协议
        if not link.startswith("http://") and not link.startswith("https://"):
            link = "http://" + link

        # 从插件配置获取 Docker URL
        docker_url = self.context.get_conf("XHS_DOWNLOADER_URL")
        if not docker_url:
            return event.plain_result("插件配置错误，请检查 XHS_DOWNLOADER_URL")
        docker_url = docker_url.rstrip("/") + "/xhs/"

        event.plain_result("正在解析并下载，请稍等...")

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(docker_url, json={"url": link, "download": True})
                resp.raise_for_status()
                result = resp.json()

            with tempfile.TemporaryDirectory() as tmpdir:
                total_items = 0
                if "video" in result.get("data", {}) and result["data"]["video"]:
                    total_items += len(result["data"]["video"])
                if "images" in result.get("data", {}) and result["data"]["images"]:
                    total_items += len(result["data"]["images"])

                downloaded = 0

                # 下载视频
                for idx, vurl in enumerate(result.get("data", {}).get("video", [])):
                    fname = os.path.join(tmpdir, f"video_{idx}.mp4")
                    await self.download_file(vurl, fname)
                    event.video_result(fname)
                    downloaded += 1
                    event.plain_result(f"下载进度: {downloaded}/{total_items}")

                # 下载图片
                for idx, iurl in enumerate(result.get("data", {}).get("images", [])):
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
