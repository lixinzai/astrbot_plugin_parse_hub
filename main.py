import sys
import os
from astrbot.api.all import *

# ==========================================
# 1. 环境路径配置
# ==========================================
# 获取当前文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 定位到 ParseHub 项目根目录
parsehub_root = os.path.join(current_dir, "ParseHub")

# 将 ParseHub 根目录加入系统路径，这样才能使用 'from src.parsehub...'
if parsehub_root not in sys.path:
    sys.path.insert(0, parsehub_root)

# ==========================================
# 2. 尝试导入核心模块
# ==========================================
try:
    from src.parsehub.main import ParseHub
    from src.parsehub.config import ParseConfig
    PARSER_AVAILABLE = True
except ImportError as e:
    print(f"❌ ParseHub 导入失败: {e}")
    print(f"请确保已进入 {parsehub_root} 并在该目录下执行了 'pip install .'")
    PARSER_AVAILABLE = False

@register("parsehub_plugin", "z-mio", "全网视频解析插件", "1.0.0")
class ParseHubPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        if PARSER_AVAILABLE:
            # 初始化配置，默认不带 Cookie，如果需要更高成功率可以在这里填入
            config = ParseConfig(
                cookie="", 
                # proxy="http://127.0.0.1:7890" # 如果需要代理，取消注释并修改
            )
            self.parser = ParseHub(config)
            print("✅ ParseHub 核心加载成功")
        else:
            self.parser = None

    @filter.command("parse")
    async def parse_video(self, event: AstrMessageEvent, url: str):
        '''解析视频/图集链接。使用方法：/parse <链接>'''
        
        if not self.parser:
            yield event.plain_result("❌ 插件核心未加载，请检查依赖安装。")
            return

        if not url:
            yield event.plain_result("⚠️ 请提供链接，例如：/parse https://v.douyin.com/...")
            return

        # 发送“正在解析”提示
        yield event.plain_result("🔍 正在解析资源，请稍候...")

        try:
            # 调用 ParseHub 的异步解析方法
            result = await self.parser.parse(url)
            
            if not result:
                yield event.plain_result("❌ 解析返回为空。")
                return

            # 获取 media 对象
            media = getattr(result, "media", None)
            if not media:
                yield event.plain_result("❌ 解析成功但未找到媒体信息。")
                return

            # ==========================================
            # 3. 构建消息链 (根据 media 对象属性)
            # ==========================================
            chain = []

            # --- 标题 ---
            # 尝试从 media 对象中获取 title，如果属性不存在则尝试字典获取
            title = getattr(media, "title", None) or getattr(media, "desc", "无标题")
            chain.append(Plain(f"🎬 {title}\n"))

            # --- 视频处理 ---
            # 常见的字段可能是 video_url, url, play_addr (需根据实际运行推断，优先尝试 video_url)
            video_url = getattr(media, "video_url", None) or getattr(media, "url", None)
            
            # --- 图集处理 ---
            images = getattr(media, "images", []) or getattr(media, "image_list", [])

            # --- 封面处理 (可选) ---
            cover = getattr(media, "cover", None)

            has_content = False

            # 优先发送视频
            if video_url:
                chain.append(Video.fromURL(video_url))
                has_content = True
            
            # 如果是图集
            elif images and isinstance(images, list):
                chain.append(Plain(f"📷 检测到 {len(images)} 张图片：\n"))
                # 限制图片数量防止消息过长（可选，这里限制前9张）
                for img_url in images[:9]: 
                    chain.append(Image.fromURL(img_url))
                has_content = True
            
            # 如果没有视频也没有图集，但在有封面时发送封面（比如纯文案）
            elif cover:
                chain.append(Plain("🖼️ 封面预览："))
                chain.append(Image.fromURL(cover))
                has_content = True

            if not has_content:
                # 如果实在找不到媒体链接，把 raw data 打印出来方便调试
                chain.append(Plain(f"⚠️ 未找到可直接发送的媒体流。\n解析数据: {str(media)[:200]}"))

            yield event.chain_result(chain)

        except Exception as e:
            # 打印错误堆栈到控制台以便排查
            import traceback
            traceback.print_exc()
            yield event.plain_result(f"❌ 解析出错: {str(e)}")