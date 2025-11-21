import re
import aiohttp
import json
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Video

@register("xhs_parse_hub", "YourName", "小红书去水印解析插件", "1.0.4")
class XhsParseHub(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url = config.get("api_url", "http://127.0.0.1:5556/xhs/")

    async def initialize(self):
        logger.info(f"小红书解析插件已加载，API地址: {self.api_url}")

    def extract_url(self, text: str):
        """提取文本中的 http 链接"""
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

        # --- 1. 请求 API ---
        res_json = None
        try:
            async with aiohttp.ClientSession() as session:
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

        # --- 2. 提取数据 ---
        data = res_json.get("data")
        if not data:
            msg = res_json.get("message", "未知错误")
            yield event.plain_result(f"❌ 解析失败: {msg}")
            return

        title = data.get("作品标题", "无标题")
        author = data.get("作者昵称", "未知作者")
        desc = data.get("作品描述", "")
        work_type = data.get("作品类型", "") # "视频" 或 "图文"
        
        download_urls = data.get("下载地址", []) # 静态图/视频封面
        dynamic_urls = data.get("动图地址", [])  # LivePhoto 视频地址

        # --- 3. 构建文本消息 (含直链逻辑) ---
        
        info_text = f"【标题】{title}\n【作者】{author}\n\n{desc}"
        if len(info_text) > 250:
            info_text = info_text[:250] + "...\n(文案过长已折叠)"

        # A. 视频模式直链
        video_direct_link = None
        if work_type == "视频" and download_urls:
            video_direct_link = download_urls[0]
            info_text += f"\n\n🔗 视频直链:\n{video_direct_link}"

        # B. 图文模式动图直链 (新增逻辑)
        if work_type == "图文" and dynamic_urls:
            # 筛选出非空的动图地址
            live_links = [url for url in dynamic_urls if url]
            if live_links:
                info_text += f"\n\n🎞️ 检测到 {len(live_links)} 个动图(LivePhoto)，直链如下:\n"
                for idx, link in enumerate(live_links, 1):
                    info_text += f"{idx}. {link}\n"

        # 发送文本信息
        yield event.plain_result(info_text)

        # --- 4. 发送媒体文件 ---
        
        if not download_urls:
            yield event.plain_result("⚠️ 未找到资源下载地址。")
            return

        # === 场景: 视频 ===
        if work_type == "视频":
            if video_direct_link:
                yield event.plain_result("🎬 正在尝试上传视频文件...")
                try:
                    yield event.chain_result([Video.fromURL(video_direct_link)])
                except Exception as e:
                    logger.error(f"视频上传失败: {e}")
                    yield event.plain_result(f"⚠️ 视频上传失败，请使用上方链接观看。")

        # === 场景: 图文 (统一发送静态图) ===
        else:
            # 无论是普通图文还是含动图的图文
            # 既然直链已经发在文本里了，这里统一只发图片，保证速度和成功率
            count = len(download_urls)
            yield event.plain_result(f"🖼️ 正在发送 {count} 张图片...")
            
            for i, img_url in enumerate(download_urls):
                try:
                    yield event.chain_result([Image.fromURL(img_url)])
                except Exception as e:
                    logger.error(f"图片 {i+1} 发送失败: {e}")
                    yield event.plain_result(f"⚠️ 第 {i+1} 张图片发送失败。")