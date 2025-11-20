import os
import shutil
from pathlib import Path
from urllib.parse import urlparse
from parsehub.config import GlobalConfig

# 确定 temp 文件夹位置 (在插件目录下)
# __file__ 是 config/config.py -> parent 是 config/ -> parent 是 插件根目录
PLUGIN_DIR = Path(__file__).parent.parent
TEMP_DIR = PLUGIN_DIR / "temp"

# 初始化临时目录
if TEMP_DIR.exists():
    try:
        shutil.rmtree(str(TEMP_DIR), ignore_errors=True)
    except Exception:
        pass
TEMP_DIR.mkdir(exist_ok=True, parents=True)


class BotConfig:
    def __init__(self):
        # 默认值
        self.parser_proxy: str | None = None
        self.downloader_proxy: str | None = None
        self.cache_time = 24 * 60 * 60  # 24小时
        self.ai_summary = False
        self.douyin_api: str | None = None
        self.debug = False
        
        # 原项目有的字段，保留以防止报错，但设为 None
        self.bot_token = None
        self.api_id = None
        self.api_hash = None
        self.bot_proxy = None

    class _Proxy:
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
        从 AstrBot 的配置字典加载设置
        """
        self.parser_proxy = cfg.get("parser_proxy") or None
        self.downloader_proxy = cfg.get("downloader_proxy") or None
        self.douyin_api = cfg.get("douyin_api") or None
        self.ai_summary = cfg.get("ai_summary", False)
        self.debug = cfg.get("debug", False)
        
        # 更新 GlobalConfig (这是 parsehub 库的全局配置)
        if self.douyin_api:
            GlobalConfig.douyin_api = self.douyin_api
        GlobalConfig.duration_limit = 0


# 全局单例
bot_cfg = BotConfig()

# WatchdogSettings 在 AstrBot 中不需要，保留一个空壳防止 import 报错
class WatchdogSettings:
    def __init__(self):
        self.is_running = True

ws = WatchdogSettings()