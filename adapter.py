import os
import asyncio
from astrbot.api.all import *
from .log import logger

# 导入原项目的核心类
from .methods.tg_parse_hub import TgParseHub

# =============================================
# 1. Mock 对象
# 用来欺骗 download 方法中的 callback 和 msg.edit_text
# =============================================
class MockMessage:
    """模拟 Pyrogram Message 对象，防止 download 里的进度条报错"""
    def __init__(self):
        self.text = ""
    
    async def edit_text(self, text, **kwargs):
        # 你可以在这里用 print 调试进度
        # print(f"[ParseHub Progress] {text}")
        pass
    
    async def delete(self):
        pass

async def mock_callback(current, total, status: str, msg):
    """模拟下载进度回调"""
    pass

# =============================================
# 2. 核心任务函数
# =============================================
async def run_parse_task(url: str) -> list:
    """
    执行解析 -> 下载 -> 提取文件 -> 返回 AstrBot 组件链
    """
    tph = TgParseHub()
    
    # 1. 初始化解析器
    try:
        # 初始化 (内部会调用 select_parser)
        await tph.init_parser(url)
        
        # 检查是否已经在运行 (复用原逻辑)
        if await tph.get_parse_task(url):
             return [Plain("⚠️ 该链接正在解析中，请稍候...")]
             
        # 添加任务锁
        await tph._add_parse_task()
        
    except Exception as e:
        return [Plain(f"❌ 初始化失败: {e}")]

    # 2. 执行解析 (Parse)
    try:
        # 调用父类的 parse 获取结果
        # 注意：原 TgParseHub.parse 里面有很多缓存逻辑和 operate 选择逻辑
        # 我们直接复用它的 parse 方法
        await tph.parse(url)
        
        # 解析完成后，tph.operate 应该已经被赋值了 (Image/Video/MultimediaOperate)
        if not tph.operate:
            return [Plain("❌ 解析失败: 未能获取操作对象")]

    except Exception as e:
        await tph._del_parse_task()
        return [Plain(f"❌ 解析出错: {e}")]

    # 3. 执行下载 (Download)
    # 我们不调用 chat_upload，而是手动调用 download
    mock_msg = MockMessage()
    try:
        # download 内部会将结果存入 tph.operate.download_result
        await tph.download(callback=mock_callback, callback_args=(mock_msg,))
    except Exception as e:
        await tph._del_parse_task()
        return [Plain(f"❌ 下载出错: {e}")]
    
    # 4. 提取结果并转换为 AstrBot 消息链
    chain = []
    
    try:
        # 4.1 获取文本 (标题 + 链接)
        # 根据你的代码，content_and_url 属性包含了格式化好的文本
        text_content = tph.operate.content_and_url
        if text_content:
            # 移除 HTML 标签 (因为 AstrBot 目前主要支持纯文本，或者你需要转 Markdown)
            # 简单处理：直接发，AstrBot 会尝试处理
            chain.append(Plain(text_content + "\n"))

        # 4.2 获取媒体文件
        # 你的代码显示结果在 tph.operate.download_result.media 中
        download_result = tph.operate.download_result
        if download_result and download_result.media:
            media_list = download_result.media
            # 确保它是列表
            if not isinstance(media_list, list):
                media_list = [media_list]

            for media_item in media_list:
                # 你的代码中，媒体对象(Image/Video)都有 .path 属性
                file_path = getattr(media_item, "path", None)
                
                if file_path and os.path.exists(file_path):
                    # 判断文件类型
                    ext = os.path.splitext(file_path)[1].lower()
                    
                    if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic']:
                        chain.append(Image.fromLocal(file_path))
                    elif ext in ['.mp4', '.mov', '.mkv', '.avi', '.webm']:
                        chain.append(Video.fromLocal(file_path))
                    else:
                        chain.append(Plain(f"[文件] {os.path.basename(file_path)}"))
        
        # 4.3 清理任务锁
        await tph._del_parse_task()
        
        if len(chain) == 0:
             return [Plain("✅ 解析完成，但未发现可发送的内容。")]
             
        return chain

    except Exception as e:
        logger.exception(e)
        await tph._del_parse_task()
        return [Plain(f"❌ 数据处理出错: {e}")]