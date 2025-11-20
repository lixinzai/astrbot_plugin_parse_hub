from astrbot.api.all import *
from .adapter import run_parse_task
# 引入刚才修改的配置对象
from .config.config import bot_cfg 

@register(
    plugin_name="astrbot_plugin_parse_hub",
    author="z-mio",
    version="1.0.3",
    desc="ParseHub 链接解析 (AstrBot适配版)"
)
class ParseHubPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 【新增】将 AstrBot 的配置加载到原项目的 bot_cfg 中
        # self.config 是 AstrBot 自动读取 _conf_schema.json 后的字典
        bot_cfg.reload_from_astrbot(self.config)
        print(f"[ParseHub] Config loaded. Proxy: {bot_cfg.parser_proxy}")

    # ... 下面是之前的 cmd_jx 和 on_message 代码 ...