import os
import tempfile
import httpx
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import MessageSegment

@register("xhs_downloader", "YourName", "小红书下载插件，支持多图多视频和进度提示", "1.0.2")
class XHSDownloaderPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """插件初始化"""
        logger.info("XHSDownloaderPlugin 初始化完成")

    @filter.command("xhs")
    async def download_handler(self, event: AstrMessageEvent):
        """小红书下载指令 /xhs <作品链接>"""
        text = event.message_str.strip()
        if not text:
            yield event.plain_result("请提供小红书作品链接，例如：/xhs https://www.xiaohongshu.com/xxxx")
            return

        link = text.split()[0]

        # 从插件配置获取 Docker 服务 URL
        docker_url = self.context.get_config("XHS_DOWNLOADER_URL") or "http://localhost:5000/download"

        progress_msg = await event.reply("正在解析并下载，请稍等...")

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(docker_url, params={"url": link})
                if resp.status_code != 200:
                    await progress_msg.edit(f"下载服务返回错误: {resp.status_code}")
                    return

                result = resp.json()

            # 临时目录
            with tempfile.TemporaryDirectory() as tmpdir:
                messages = []
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
                        await self.download_file(vurl, fname, progress_msg, downloaded, total_items)
                        messages.append(MessageSegment.video(fname))
                        downloaded += 1

                # 下载图片
                if "images" in result and result["images"]:
                    for idx, iurl in enumerate(result["images"]):
                        fname = os.path.join(tmpdir, f"image_{idx}.jpg")
                        await self.download_file(iurl, fname, progress_msg, downloaded, total_items)
                        messages.append(MessageSegment.image(fname))
                        downloaded += 1

                if messages:
                    await progress_msg.edit("下载完成，正在发送...")
                    for msg in messages:
                        await event.reply(msg)
                    await progress_msg.delete()
                else:
                    await progress_msg.edit("下载完成，但未找到可用资源。")

        except Exception as e:
            logger.error(f"插件异常: {e}")
            await progress_msg.edit(f"插件异常: {e}")

    async def download_file(self, url, path, progress_msg=None, downloaded=0, total=1):
        """异步下载文件，并更新进度"""
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.get(url)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)

        if progress_msg and total > 1:
            percent = int((downloaded + 1) / total * 100)
            await progress_msg.edit(f"下载进度: {downloaded + 1}/{total} ({percent}%)")

    async def terminate(self):
        """插件被卸载/停用时调用"""
        logger.info("XHSDownloaderPlugin 已卸载")
