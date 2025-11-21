import re
import aiohttp
import json
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Video

@register("xhs_parse_hub", "YourName", "小红书去水印解析插件", "1.0.1")
class XhsParseHub(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url = config.get("api_url", "http://127.0.0.1:5556/xhs/")

    async def initialize(self):
        logger.info(f"小红书解析插件已加载，API地址: {self.api_url}")

    def extract_url(self, text: str):
        pattern = r'(https?://[^\s]+)'
        match = re.search(pattern, text)
        if match:
            return match.group(0)
        return None

    @filter.command("xhs")
    async def xhs_parse(self, event: AstrMessageEvent):
        """
        小红书解析指令。用法: /xhs <链接>
        """
        message_str = event.message_str
        target_url = self.extract_url(message_str)
        
        if not target_url:
            if "http" in message_str:
                target_url = message_str.strip()
            else:
                yield event.plain_result("⚠️ 请提供包含小红书链接的消息。")
                return

        yield event.plain_result("🔍 正在解析，请稍候...")

        # --- 1. 调用 API ---
        res_json = None
        try:
            async with aiohttp.ClientSession() as session:
                # 设置较长的超时时间，防止服务端解析慢
                timeout = aiohttp.ClientTimeout(total=60)
                async with session.post(self.api_url, json={"url": target_url}, timeout=timeout) as resp:
                    if resp.status != 200:
                        yield event.plain_result(f"❌ 解析请求失败: {resp.status}")
                        return
                    res_json = await resp.json()
        except Exception as e:
            logger.error(f"API请求异常: {e}")
            yield event.plain_result(f"❌ 连接解析服务超时或错误: {e}")
            return

        # --- 2. 数据提取 ---
        data = res_json.get("data")
        if not data:
            msg = res_json.get("message", "未知错误")
            yield event.plain_result(f"❌ 解析失败: {msg}")
            return

        title = data.get("作品标题", "无标题")
        author = data.get("作者昵称", "未知作者")
        desc = data.get("作品描述", "")
        work_type = data.get("作品类型", "")
        download_urls = data.get("下载地址", [])

        # --- 3. 分步发送策略 (关键修改) ---

        # [第一步] 发送文本信息
        info_text = f"【标题】{title}\n【作者】{author}\n\n{desc}"
        if len(info_text) > 300:
            info_text = info_text[:300] + "...\n(文案过长已折叠)"
        
        # 先把文字发出去，确保用户看到了结果
        yield event.plain_result(info_text)

        # [第二步] 发送媒体资源
        if not download_urls:
            yield event.plain_result("⚠️ 未找到下载地址。")
            return

        if work_type == "视频":
            video_url = download_urls[0]
            yield event.plain_result("🎬 正在发送视频(文件较大请耐心等待)...")
            
            # 尝试发送视频对象
            try:
                yield event.chain_result([Video.fromURL(video_url)])
            except Exception as e:
                # 如果视频太大发不出去，直接把直链发给用户
                logger.error(f"视频发送失败: {e}")
                yield event.plain_result(f"⚠️ 视频发送超时，请点击直链观看：\n{video_url}")

        elif work_type == "图文":
            yield event.plain_result(f"🖼️ 检测到 {len(download_urls)} 张图片，开始逐张发送...")
            
            # 逐张发送图片，避免打包发送导致超时
            for i, img_url in enumerate(download_urls):
                try:
                    # 每一张图作为一个独立的消息发送
                    yield event.chain_result([Image.fromURL(img_url)])
                except Exception as e:
                    logger.error(f"第 {i+1} 张图片发送失败: {e}")
                    yield event.plain_result(f"⚠️ 第 {i+1} 张图片发送失败 (可能过大)")
        
        else:
            # 未知类型
            yield event.plain_result(f"⚠️ 未知类型 [{work_type}]，尝试作为图片发送...")
            for url in download_urls:
                yield event.chain_result([Image.fromURL(url)])