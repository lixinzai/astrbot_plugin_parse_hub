import sys
import os
from pathlib import Path

# ========================================================
# 【核心修复】将插件根目录加入 sys.path
# 这样原来的代码里写 "from parsehub import ..." 才能找到文件
# ========================================================
current_path = Path(__file__).parent.absolute()
if str(current_path) not in sys.path:
    sys.path.insert(0, str(current_path))

# ========================================================

import re
from astrbot.api.all import *
# 此时再导入 adapter，它引用的原项目代码就能找到依赖了
from .adapter import run_parse_task
from .config.config import bot_cfg

@register(
    plugin_name="astrbot_plugin_parse_hub",
    author="z-mio",
    version="1.0.4",
    desc="ParseHub 链接解析 (AstrBot适配版)"
)
class ParseHubPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 加载配置
        bot_cfg.reload_from_astrbot(self.config)
        if bot_cfg.debug:
            print(f"[ParseHub] 插件加载成功，路径已注入: {current_path}")

    # /jx <url> 指令
    @filter.command("jx")
    async def cmd_jx(self, event: AstrMessageEvent, url: str = None):
        if not url:
            yield event.plain_result("❌ 请输入链接，例如 /jx https://...")
            return
        await self._handle(event, url)

    # 自动监听 URL
    @event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        if event.message_obj.sender.user_id == self.context.robot_id:
            return
        
        text = event.message_str
        # 简单的 URL 提取正则
        urls = re.findall(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*', text)
        if urls:
            # 可以在这里加白名单判断
            await self._handle(event, urls[0])

    async def _handle(self, event: AstrMessageEvent, url: str):
        yield event.plain_result("🔍 正在解析...")
        try:
            # 调用 adapter
            chain = await run_parse_task(url)
            if chain:
                yield event.chain_result(chain)
            else:
                # 可能任务已存在
                pass
        except Exception as e:
            yield event.plain_result(f"❌ 出错: {e}")