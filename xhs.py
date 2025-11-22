import aiohttp
import re
import json
from astrbot.api import logger

class XhsHandler
    def __init__(self, api_url str)
        self.api_url = api_url

    def extract_url(self, text str)
        从文本中提取 HTTP 链接
        pattern = r'(https[^s]+)'
        match = re.search(pattern, text)
        if match
            return match.group(0)
        return None

    async def parse(self, target_url str) - dict
        
        请求解析服务并返回标准化数据
        Returns
            dict {
                success bool,
                msg str, # 错误信息
                type video  image,
                title str,
                author str,
                desc str,
                download_urls list, # 图片列表 或 视频封面
                dynamic_urls list,  # 动图列表
                video_url str       # 视频直链 (如果是视频)
            }
        
        result = {
            success False,
            msg ,
            type unknown,
            title ,
            author ,
            desc ,
            download_urls [],
            dynamic_urls [],
            video_url None
        }

        try
            async with aiohttp.ClientSession() as session
                timeout = aiohttp.ClientTimeout(total=15)
                # 调用你的本地解析服务
                async with session.post(self.api_url, json={url target_url}, timeout=timeout) as resp
                    if resp.status != 200
                        result[msg] = fAPI请求失败，状态码 {resp.status}
                        return result
                    
                    res_json = await resp.json()
        except Exception as e
            result[msg] = f连接解析服务出错 {e}
            return result

        # 检查 API 返回的数据有效性
        data = res_json.get(data)
        if not data
            result[msg] = res_json.get(message, 解析服务返回未知错误)
            return result

        # --- 数据清洗与标准化 ---
        result[success] = True
        result[title] = data.get(作品标题, 无标题)
        result[author] = data.get(作者昵称, 未知作者)
        result[desc] = data.get(作品描述, )
        
        # 原始数据
        raw_type = data.get(作品类型, )
        download_urls = data.get(下载地址, [])
        dynamic_urls = data.get(动图地址, [])

        result[download_urls] = download_urls
        result[dynamic_urls] = dynamic_urls

        # 判断类型
        if raw_type == 视频
            result[type] = video
            if download_urls
                result[video_url] = download_urls[0]
        elif raw_type == 图文
            result[type] = image
        else
            result[type] = unknown

        return result