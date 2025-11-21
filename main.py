from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import httpx
import asyncio
import os
import tempfile

# 插件注册
@register("xhs_downloader", "August", "小红书作品下载插件", "1.0.0")
class XHSDownloaderPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 获取 Docker URL 配置
        docker_url = None
        if hasattr(self.context, "get_config"):
            docker_url = self.context.get_config("XHS_DOWNLOADER_URL")
        elif hasattr(self.context, "config"):
            docker_url = self.context.config.get("XHS_DOWNLOADER_URL")
        if not docker_url:
            docker_url = "http://127.0.0.1:5556/xhs/"
        self.docker_url = str(docker_url).strip().rstrip("/") + "/"

    async def initialize(self):
        """插件初始化"""
        logger.info(f"XHSDownloaderPlugin initialized with Docker URL: {self.docker_url}")

    @filter.command("xhs")
    async def download_handler(self, event: AstrMessageEvent):
        """下载小红书作品"""
        try:
            message_str = event.message_str.strip()
            if not message_str.startswith("http"):
                message_str = "http://" + message_str  # 自动补全协议
            async with httpx.AsyncClient(timeout=60) as client:
                payload = {"url": message_str, "download": True}
                r = await client.post(self.docker_url, json=payload)
                if r.status_code != 200:
                    yield event.plain_result(f"请求 Docker 服务失败，状态码: {r.status_code}")
                    return
                data = r.json()
                # 检查返回状态
                if "data" not in data:
                    yield event.plain_result(f"解析失败: {data.get('message')}")
                    return
                content_data = data["data"]
                files = content_data.get("下载地址", [])
                if not files:
                    yield event.plain_result("未找到可下载内容")
                    return

                # 下载并发送文件
                for file_url in files:
                    if not file_url:
                        continue
                    filename = file_url.split("/")[-1]
                    tmp_path = os.path.join(tempfile.gettempdir(), filename)
                    r_file = await client.get(file_url)
                    with open(tmp_path, "wb") as f:
                        f.write(r_file.content)
                    # 发送文件
                    yield event.file_result(tmp_path)

        except Exception as e:
            logger.exception(f"插件异常: {e}")
            yield event.plain_result(f"插件异常: {e}")

    async def terminate(self):
        """插件销毁"""
        logger.info("XHSDownloaderPlugin terminated")
