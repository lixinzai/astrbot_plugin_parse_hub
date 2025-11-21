import re
import aiohttp
import json
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image, Video

@register("xhs_parse_hub", "YourName", "小红书去水印解析插件", "1.0.0")
class XhsParseHub(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        # 从配置中读取 api_url，如果没有配置则使用默认值
        self.api_url = config.get("api_url", "http://127.0.0.1:5556/xhs/")

    async def initialize(self):
        logger.info(f"小红书解析插件已加载，API地址: {self.api_url}")

    def extract_url(self, text: str):
        """从杂乱文本中提取 http/https 链接"""
        pattern = r'(https?://[^\s]+)'
        match = re.search(pattern, text)
        if match:
            return match.group(0)
        return None

    @filter.command("xhs")
    async def xhs_parse(self, event: AstrMessageEvent):
        """
        小红书解析指令。
        用法: /xhs <链接>
        """
        message_str = event.message_str
        
        # 1. 提取链接
        target_url = self.extract_url(message_str)
        
        # 如果没提取到，且用户发送的内容本身看起来像链接，就直接用
        if not target_url:
            if "http" in message_str:
                target_url = message_str.strip()
            else:
                yield event.plain_result("⚠️ 未检测到链接，请发送包含小红书链接的消息。")
                return

        yield event.plain_result("🔍 正在请求解析，请稍候...")

        # 2. 调用解析服务
        res_json = None
        try:
            async with aiohttp.ClientSession() as session:
                # 构造请求体
                payload = {"url": target_url}
                
                # 设置超时时间（防止服务端卡死出现 Empty reply）
                timeout = aiohttp.ClientTimeout(total=60) 
                
                async with session.post(self.api_url, json=payload, timeout=timeout) as resp:
                    if resp.status != 200:
                        yield event.plain_result(f"❌ 服务器返回错误码: {resp.status}")
                        return
                    
                    res_json = await resp.json()
                    # 调试日志：打印服务器返回的完整数据
                    logger.debug(f"XHS API Response: {json.dumps(res_json, ensure_ascii=False)}")

        except Exception as e:
            logger.error(f"解析请求异常: {e}")
            yield event.plain_result(f"❌ 连接解析服务失败: {e}")
            return

        # 3. 解析数据 (针对你提供的 JSON 结构)
        # API 返回结构: { "message": "...", "data": { ... } }
        data = res_json.get("data")
        
        if not data:
            msg = res_json.get("message", "未知错误")
            yield event.plain_result(f"❌ 解析失败，服务端未返回数据: {msg}")
            return

        # --- 使用中文 Key 提取信息 ---
        title = data.get("作品标题", "无标题")
        author = data.get("作者昵称", "未知作者")
        desc = data.get("作品描述", "")
        work_type = data.get("作品类型", "")  # "图文" 或 "视频"
        download_urls = data.get("下载地址", []) # 这是一个列表

        # 4. 构建消息链
        chain = []
        
        # (A) 文本部分
        info_text = f"【标题】{title}\n【作者】{author}\n\n{desc}"
        # 防止文案太长刷屏，限制为 200 字
        if len(info_text) > 200:
            info_text = info_text[:200] + "...\n(文案过长已折叠)"
        chain.append(Plain(info_text))

        # (B) 媒体部分
        if not download_urls:
            chain.append(Plain("\n\n⚠️ 未找到下载地址。"))
        
        elif work_type == "视频":
            # 视频类型，取列表第一个地址
            video_url = download_urls[0]
            chain.append(Plain("\n\n🎬 正在发送视频..."))
            chain.append(Video.fromURL(video_url))
            
        elif work_type == "图文":
            # 图文类型，遍历列表发送图片
            chain.append(Plain(f"\n\n🖼️ 检测到 {len(download_urls)} 张图片，正在发送..."))
            for img_url in download_urls:
                chain.append(Image.fromURL(img_url))
                
        else:
            # 未知类型，尝试当作图片处理
            chain.append(Plain(f"\n\n⚠️ 未知类型 [{work_type}]，尝试发送资源..."))
            for url in download_urls:
                chain.append(Image.fromURL(url))

        # 5. 发送结果
        try:
            yield event.chain_result(chain)
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            yield event.plain_result(f"❌ 解析成功，但发送给客户端失败: {e}")