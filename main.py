import re
import asyncio
from astrbot.api.all import *

# 引入原本的解析逻辑
# 确保 parse_hub_lib 文件夹下有 parsers.py，且里面有 parse_url 函数
from .parse_hub_lib.parsers import parse_url_logic

@register(
    plugin_name="astrbot_plugin_parse_hub",
    author="z-mio",
    version="1.0.0",
    desc="Parse Hub 链接解析插件 (Twitter/Ins/YouTube等)"
)
class ParseHubPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    # ==========================================
    # 指令触发: /parse <链接>
    # ==========================================
    @filter.command("parse")
    async def parse_cmd(self, event: AstrMessageEvent, url: str = None):
        """手动解析链接指令"""
        if not url:
            yield event.plain_result("❌ 请提供需要解析的链接。")
            return
        
        yield event.plain_result(f"🔍 正在解析: {url}")
        await self._execute_parsing(event, url)

    # ==========================================
    # 自动触发: 监听所有含有链接的消息
    # ==========================================
    @event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        # 忽略机器人自己的消息
        if event.message_obj.sender.user_id == self.context.robot_id:
            return

        msg_text = event.message_str
        # 提取 URL 的正则
        url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*'
        urls = re.findall(url_pattern, msg_text)

        if not urls:
            return

        target_url = urls[0]
        
        # 过滤：只解析特定域名的链接（防止所有链接都解析）
        # 如果你想解析所有，可以注释掉下面这几行
        supported_domains = ["twitter.com", "x.com", "instagram.com", "tiktok.com", "youtube.com", "youtu.be"]
        if not any(domain in target_url for domain in supported_domains):
            return

        # 提示开始解析 (可选，避免刷屏可注释)
        # yield event.plain_result("⚡ 检测到链接，正在解析...")
        
        await self._execute_parsing(event, target_url)

    # ==========================================
    # 通用执行逻辑
    # ==========================================
    async def _execute_parsing(self, event: AstrMessageEvent, url: str):
        try:
            # 在线程池中运行同步的爬虫代码，防止卡死 Bot
            # parse_url_logic 是我们在 parsers.py 中定义的纯函数
            result = await self.context.executor.run_in_thread(parse_url_logic, url)

            if not result:
                return # 解析失败或不支持

            chain = []

            # 1. 处理文本
            if "text" in result and result["text"]:
                chain.append(Plain(result["text"] + "\n"))

            # 2. 处理资源 (图片/视频)
            media_list = result.get("media", [])
            for media in media_list:
                media_url = media.get("url")
                media_type = media.get("type")

                if media_type == "image":
                    chain.append(Image.fromURL(media_url))
                elif media_type == "video":
                    # 尝试发送视频组件
                    chain.append(Video.fromURL(media_url))
            
            # 如果解析结果为空
            if not chain:
                chain.append(Plain("⚠️ 解析成功，但未发现可发送的媒体内容。"))

            yield event.chain_result(chain)

        except Exception as e:
            # 打印错误日志到控制台
            print(f"[ParseHub] Error: {e}")
            # 只有在显式调用指令时才报错，避免自动模式刷屏
            if event.message_str.startswith("/"):
                yield event.plain_result(f"❌ 解析出错: {str(e)}")
