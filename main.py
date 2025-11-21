import os
import tempfile
import httpx
import asyncio
from core.star import Star, filter
from core.types import MessageSegment

class XHSDownloaderPlugin(Star):
    """
    AstrBot 插件：调用 XHS-Downloader Docker 服务
    支持多图、多视频作品，下载到本地后发送给用户
    并显示下载进度
    """

    @filter.command("xhs")
    async def download_handler(self, event):
        """
        使用方式: /xhs <小红书作品链接>
        """
        text = event.content.strip()
        if not text:
            await event.finish("请提供小红书作品链接，例如：/xhs https://www.xiaohongshu.com/...")

        link = text.split()[0]
        docker_url = self.config.get("XHS_DOWNLOADER_URL", "http://localhost:5000/download")

        progress_msg = await event.reply("正在解析并下载，请稍等...")

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(docker_url, params={"url": link})
                if resp.status_code != 200:
                    await progress_msg.edit(f"下载服务返回错误: {resp.status_code}")
                    return

                result = resp.json()

            # 临时文件夹
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
            await progress_msg.edit(f"插件异常: {e}")

    async def download_file(self, url, path, progress_msg=None, downloaded=0, total=1):
        """
        异步下载文件到本地，并可更新下载进度
        """
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.get(url)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)

        if progress_msg and total > 1:
            percent = int((downloaded + 1) / total * 100)
            await progress_msg.edit(f"下载进度: {downloaded + 1}/{total} ({percent}%)")
