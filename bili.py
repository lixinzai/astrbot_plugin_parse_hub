import os
import re
import json
import time
import base64
import asyncio
import aiohttp
import aiofiles
import qrcode
from io import BytesIO
from urllib.parse import unquote
from astrbot.api import logger

class BiliHandler:
    def __init__(self, cache_dir: str, use_login: bool = False):
        self.cache_dir = cache_dir
        self.use_login = use_login
        self.cookie_file = os.path.join(cache_dir, "bili_cookies.json")
        
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

        self.REG_B23 = re.compile(r'(b23\.tv|bili2233\.cn)\/[\w]+')
        self.REG_BV = re.compile(r'BV1\w{9}')
        self.REG_AV = re.compile(r'av\d+', re.I)

    def extract_url(self, text: str):
        match = self.REG_B23.search(text)
        if match: return f"https://{match.group()}"
        match = self.REG_BV.search(text)
        if match: return match.group()
        match = self.REG_AV.search(text)
        if match: return match.group()
        return None

    async def _request(self, url, headers=None, return_json=True):
        default_headers = {
            "referer": "https://www.bilibili.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        if headers: default_headers.update(headers)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=default_headers, timeout=30) as resp:
                    if return_json: return await resp.json()
                    return await resp.read()
        except Exception as e:
            logger.error(f"Bili Request Error: {e}")
            return None

    async def load_cookies(self):
        if not os.path.exists(self.cookie_file): return None
        try:
            async with aiofiles.open(self.cookie_file, "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content) if content else None
        except: return None

    async def save_cookies(self, cookies):
        async with aiofiles.open(self.cookie_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(cookies, indent=2))

    async def check_cookie_valid(self):
        cookies = await self.load_cookies()
        if not cookies: return False
        url = "https://api.bilibili.com/x/member/web/account"
        headers = {"Cookie": "; ".join([f"{k}={v}" for k, v in cookies.items()])}
        data = await self._request(url, headers)
        return data and data.get("code") == 0

    async def get_login_qr(self):
        url = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
        data = await self._request(url)
        if not data or data.get("code") != 0: return None
        qr_url = data["data"]["url"]
        qrcode_key = data["data"]["qrcode_key"]
        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(qr_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        qr_path = os.path.join(self.cache_dir, "bili_qr.png")
        img.save(qr_path)
        return {"key": qrcode_key, "img_path": qr_path, "url": qr_url}

    async def poll_login(self, qrcode_key):
        url = f"https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={qrcode_key}"
        data = await self._request(url)
        if data and data.get("code") == 0:
            if data["data"]["code"] == 0:
                url_param = data["data"]["url"]
                cookies = {}
                if "?" in url_param:
                    for param in url_param.split("?")[1].split("&"):
                        k, v = param.split("=", 1)
                        cookies[k] = unquote(v)
                await self.save_cookies(cookies)
                return True
            elif data["data"]["code"] == 86038: return False
        return None

    async def parse(self, raw_url: str):
        result = {"success": False, "msg": "", "type": "video", "bvid": "", "title": ""}
        bvid = None
        if "b23.tv" in raw_url or "bili2233" in raw_url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.head(raw_url, allow_redirects=True) as resp:
                        raw_url = str(resp.url)
            except: pass
        match = self.REG_BV.search(raw_url)
        if match: bvid = match.group()
        else:
            result["msg"] = "未找到BV号"
            return result

        info_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        info = await self._request(info_url)
        if not info or info.get("code") != 0:
            result["msg"] = f"获取信息失败: {info.get('message') if info else 'Network Error'}"
            return result
        
        v_data = info["data"]
        result["success"] = True
        result["title"] = v_data["title"]
        result["author"] = v_data["owner"]["name"]
        result["desc"] = v_data["desc"]
        result["bvid"] = bvid
        result["cid"] = v_data["cid"]
        result["aid"] = v_data["aid"]
        result["download_urls"] = [v_data["pic"]] 
        return result

    # [新增] 仅获取直链
    async def get_stream_url(self, parse_result):
        bvid = parse_result["bvid"]
        cid = parse_result["cid"]
        aid = parse_result["aid"]
        
        headers = {"Referer": "https://www.bilibili.com/"}
        if self.use_login:
            cookies = await self.load_cookies()
            if cookies: headers["Cookie"] = "; ".join([f"{k}={v}" for k, v in cookies.items()])

        # fnval=16 (DASH) or 1 (mp4)
        play_url = f"https://api.bilibili.com/x/player/playurl?avid={aid}&cid={cid}&qn=64&fnval=1&platform=html5"
        data = await self._request(play_url, headers)
        
        if data and data.get("code") == 0:
            durl = data["data"].get("durl")
            if durl: return durl[0]["url"]
        return "获取失败"

    async def download_bili_video(self, parse_result):
        bvid = parse_result["bvid"]
        cid = parse_result["cid"]
        aid = parse_result["aid"]
        
        final_path = os.path.join(self.cache_dir, f"{bvid}.mp4")
        if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
            return final_path

        headers = {"Referer": "https://www.bilibili.com/", "User-Agent": "Mozilla/5.0"}
        if self.use_login:
            cookies = await self.load_cookies()
            if cookies: headers["Cookie"] = "; ".join([f"{k}={v}" for k, v in cookies.items()])

        play_url = f"https://api.bilibili.com/x/player/playurl?avid={aid}&cid={cid}&qn=80&fnval=16&fourk=1"
        data = await self._request(play_url, headers)
        
        if not data or data.get("code") != 0: return None
        
        try:
            dash = data["data"]["dash"]
            v_url = dash["video"][0]["baseUrl"]
            a_url = dash["audio"][0]["baseUrl"]
        except:
            try:
                durl = data["data"]["durl"]
                v_url = durl[0]["url"]
                a_url = None
            except: return None

        v_path = os.path.join(self.cache_dir, f"{bvid}_v.m4s")
        a_path = os.path.join(self.cache_dir, f"{bvid}_a.m4s")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(v_url, headers=headers) as resp:
                    if resp.status != 200: return None
                    with open(v_path, "wb") as f: f.write(await resp.read())
            
            if a_url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(a_url, headers=headers) as resp:
                        if resp.status != 200: return None
                        with open(a_path, "wb") as f: f.write(await resp.read())
            
            if a_url:
                cmd = f'ffmpeg -y -i "{v_path}" -i "{a_path}" -c:v copy -c:a copy "{final_path}" -loglevel quiet'
            else:
                cmd = f'ffmpeg -y -i "{v_path}" -c copy "{final_path}" -loglevel quiet'
            
            proc = await asyncio.create_subprocess_shell(cmd)
            await proc.communicate()
            
            if os.path.exists(v_path): os.remove(v_path)
            if os.path.exists(a_path): os.remove(a_path)
            
            if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
                return final_path
            return None

        except Exception as e:
            logger.error(f"B站下载合并失败: {e}")
            return None