import shutil
from pathlib import Path
from urllib.parse import urlparse

# 使用相对引用导入 parsehub 的全局配置
# 确保你的目录结构是 astrbot_plugin_parse_hub/parsehub/config.py
try:
    from ..parsehub.config import GlobalConfig
except ImportError:
    # 兜底：如果相对导入失败，尝试直接导入（取决于 sys.path）
    from parsehub.config import GlobalConfig

# 1. 设定临时文件夹路径 (在插件目录下)
# __file__ 是 config/config.py -> parent 是 config/ -> parent.parent 是插件根目录
PLUGIN_DIR = Path(__file__).parent.parent
TEMP_DIR = PLUGIN_DIR / "temp"

# 2. 初始化临时目录
if TEMP_DIR.exists():
    try:
        shutil.rmtree(str(TEMP_DIR), ignore_errors=True)
    except Exception:
        pass
TEMP_DIR.mkdir(exist_ok=True, parents=True)


class BotConfig:
    def __init__(self):
        # === 原项目字段 (保留以防止 AttributeError) ===
        self.bot_token = None
        self.api_id = None
        self.api_hash = None
        self.bot_proxy = None

        # === 可配置字段 (默认值) ===
        self.parser_proxy: str | None = None
        self.downloader_proxy: str | None = None
        # 默认缓存时间 24 小时
        self.cache_time = 24 * 60 * 60
        self.ai_summary = False
        self.douyin_api: str | None = None
        self.debug = False

    class _Proxy:
        """代理辅助类，用于解析 URL"""
        def __init__(self, url: str):
            self._url = urlparse(url) if url else None
            self.url = self._url.geturl() if self._url else None

        @property
        def dict_format(self):
            if not self._url:
                return None
            return {
                "scheme": self._url.scheme,
                "hostname": self._url.hostname,
                "port": self._url.port,
                "username": self._url.username,
                "password": self._url.password,
            }

    def reload_from_astrbot(self, cfg: dict):
        """
        从 AstrBot 的配置字典加载设置 (由 main.py 调用)
        """
        # 读取配置，如果没有则使用 None 或默认值
        self.parser_proxy = cfg.get("parser_proxy") or None
        self.downloader_proxy = cfg.get("downloader_proxy") or None
        self.douyin_api = cfg.get("douyin_api") or None
        self.ai_summary = cfg.get("ai_summary", False)
        self.debug = cfg.get("debug", False)
        
        # 同步更新到 parsehub 库的 GlobalConfig
        if self.douyin_api:
            GlobalConfig.douyin_api = self.douyin_api
        GlobalConfig.duration_limit = 0  # 不限制时长
        
        if self.debug:
            print(f"[ParseHub] 配置已加载: Proxy={self.parser_proxy}")


# === WatchdogSettings 桩代码 ===
# 原项目用于管理重启，AstrBot 不需要这个，
# 但为了防止 methods/tg_parse_hub.py 引用 ws 报错，保留一个空壳。
class WatchdogSettings:
    def __init__(self):
        self.is_running = True
        self.restart_count = 0
        self.disconnect_count = 0
    
    def update_bot_restart_count(self): pass
    def reset_bot_restart_count(self): pass
    def update_bot_disconnect_count(self): pass
    def reset_bot_disconnect_count(self): pass


# === 全局单例 ===
bot_cfg = BotConfig()
ws = WatchdogSettings()