# AstrBot 全能聚合解析插件
<div align="center">

![访问次数](https://count.getloli.com/@astrbot_plugin_parse_hub?name=astrbot_plugin_parse_hub&theme=booru-lisu&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

</div>

一个功能强大的 AstrBot 插件，用于解析多平台内容。仅测试telegram-bot。

## ✨ 主要功能

*   **多平台支持**：
    *   **抖音 (Douyin)**：支持视频和图文解析。内置本地爬虫核心，**无需配置 API**，无需额外部署。支持 Cookie 抗风控。
    *   **小红书 (Xiaohongshu)**：对接 `XHS-Downloader` 服务，支持去水印高清图文/视频。
    *   **哔哩哔哩 (Bilibili)**：支持解析视频信息、获取直链。支持 **登录扫码** 下载 1080P+ 高清视频（自动合并音视频）。
*   **稳定发送**：
    *   **强制文件模式**：所有视频和图片均以“文件”形式发送，保证画质无损，规避 Telegram 的压缩和限制。
    *   **抗超时机制**：上传大文件时如果遇到网络超时，插件会自动捕获并重试，保证任务不中断。
*   **自动解析**：开启后，只需发送链接，机器人自动识别并处理。


## ⚙️ 配置说明

在 AstrBot 管理后台配置以下选项：

*   **`api_url`**: 小红书解析服务的 API 地址 (例如 `http://127.0.0.1:5556/xhs/`)。
*   **`auto_parse_enabled`**: 是否开启自动解析 (默认开启)。关闭后需使用 `/jx <链接>` 指令。
*   **`bili_download_video`**: B站解析是否下载视频 (默认关闭，仅发直链)。开启后会消耗服务器带宽和时间。
*   **`bili_use_login`**: 是否使用 B 站登录 (默认关闭)。开启后首次下载会弹出二维码，扫码登录后可下载高清视频。
*   **`douyin_cookie`**: 抖音 Cookie (可选)。如果解析失败或为空，请填入浏览器抓取的 Cookie。

## 🙏 声明
本项目的小红书解析功能基于以下开源项目：

**[JoeanAmier/XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader)**
- 提供了完整的解析方案
- 请自行部署使用

本项目的抖音解析功能基于以下开源项目：

**[Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)**
- 提供了完整的抖音视频解析方案
- 贡献了核心的加密算法和请求处理逻辑
- 感谢 [@Evil0ctal](https://github.com/Evil0ctal) 及所有贡献者的辛勤工作

本插件基于以下开源项目修改：
**[astrbot_plugin_videos_analysis](github.com/miaoxutao123/astrbot_plugin_videos_analysis)**

如果觉得本插件好用，请考虑为原项目点个 ⭐ Star！

## 📄 许可证

本项目基于 [GNU Affero General Public License v3.0](LICENSE) 开源许可证。

---

<div align="center">

**如果这个项目对你有帮助，请给个 ⭐ Star 支持一下！**

</div>