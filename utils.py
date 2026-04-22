"""
Utility Functions
Formatting, Receipts, Text Hosting, Discord Notifications
"""

import random
import string
import aiohttp
import logging
from datetime import datetime
from database import get_setting

log = logging.getLogger(__name__)


def generate_receipt():
    """Generate Random Receipt Number Like #821287352040XXXX"""
    return "#" + "".join(random.choices(string.digits, k=15))


def now_str():
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")


def today_date():
    return datetime.now().strftime("%d %B")


def today_week():
    return datetime.now().strftime("%d %B, %A")


def today_month():
    return datetime.now().strftime("%d %B, %Yг")


def days_since(date_str):
    """Returns Number Of Days Since A Date String (Format: DD.MM.YYYY HH:MM:SS)"""
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y %H:%M:%S")
        return (datetime.now() - dt).days
    except Exception:
        return 0


# ============== Text Hosting (Pastie / Telegraph) ==============
async def upload_to_pastebin(text):
    """
    Upload Text To Pastebin.Com (Primary Service).
    Uses Admin's API Key From Settings (Free Key From pastebin.com/api).
    Falls Back To Anonymous Guest Paste If No Key.
    """
    api_key = get_setting("pastebin_api_key", "")

    try:
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            if api_key:
                data.add_field("api_dev_key", api_key)
            else:
                # Anonymous/Guest Paste — No API Key (Limited But Works)
                data.add_field("api_dev_key", "")
            data.add_field("api_option", "paste")
            data.add_field("api_paste_code", text)
            data.add_field("api_paste_private", "1")        # 1 = Unlisted
            data.add_field("api_paste_expire_date", "1D")   # 1 Day Expiration
            data.add_field("api_paste_format", "text")
            data.add_field("api_paste_name", "Purchase Data")

            async with session.post(
                "https://pastebin.com/api/api_post.php",
                data=data,
                timeout=15,
            ) as r:
                body = (await r.text()).strip()
                # Pastebin Returns The URL On Success, Or "Bad API Request..." On Failure
                if body.startswith("https://pastebin.com/"):
                    return body
                if body.startswith("http://pastebin.com/"):
                    return body.replace("http://", "https://")
                log.warning(f"Pastebin Response: {body[:200]}")
    except Exception as e:
        log.warning(f"Pastebin Upload Failed: {e}")
    return None


async def upload_to_dpaste(text):
    """Upload Text To Dpaste.Com (Reliable Free Backup)"""
    try:
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field("content", text)
            data.add_field("syntax", "text")
            data.add_field("expiry_days", "7")
            async with session.post("https://dpaste.com/api/v2/", data=data, timeout=15) as r:
                if r.status in (200, 201):
                    body = (await r.text()).strip()
                    if body.startswith("http"):
                        return body
    except Exception as e:
        log.warning(f"Dpaste Upload Failed: {e}")
    return None


async def upload_to_hastebin(text):
    """Upload Text To Hastebin.Com"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://hastebin.com/documents",
                data=text.encode("utf-8"),
                timeout=15,
            ) as r:
                if r.status in (200, 201):
                    j = await r.json()
                    key = j.get("key")
                    if key:
                        return f"https://hastebin.com/{key}"
    except Exception as e:
        log.warning(f"Hastebin Upload Failed: {e}")
    return None


async def upload_to_pastie(text):
    """Upload Text To Pastie.Org (Last Resort)"""
    try:
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field("text", text)
            data.add_field("ttl", "86400")
            data.add_field("mode-id", "Plain Text")
            async with session.post(
                "https://pastie.org/pastes",
                data=data,
                timeout=15,
                allow_redirects=False,
            ) as r:
                loc = r.headers.get("Location", "")
                if loc:
                    if loc.startswith("http"):
                        return loc
                    return f"https://pastie.org{loc}"
                body = await r.text()
                import re
                m = re.search(r"pastie\.org/p/([A-Za-z0-9]+)", body)
                if m:
                    return f"https://pastie.org/p/{m.group(1)}"
    except Exception as e:
        log.warning(f"Pastie Upload Failed: {e}")
    return None


async def upload_to_telegraph(title, content):
    """Upload Text To Telegra.Ph And Return The URL"""
    try:
        async with aiohttp.ClientSession() as session:
            # Create Account
            async with session.get(
                "https://api.telegra.ph/createAccount",
                params={"short_name": "Shop", "author_name": "Shop"},
                timeout=15,
            ) as r:
                data = await r.json()
                token = data["result"]["access_token"]

            # Create Page
            import json as jsonlib
            nodes = [{"tag": "pre", "children": [content]}]
            async with session.get(
                "https://api.telegra.ph/createPage",
                params={
                    "access_token": token,
                    "title": title[:100] or "Product Data",
                    "content": jsonlib.dumps(nodes),
                    "return_content": "false",
                },
                timeout=15,
            ) as r:
                data = await r.json()
                if data.get("ok"):
                    return data["result"]["url"]
    except Exception as e:
        log.warning(f"Telegraph Upload Failed: {e}")
    return None


async def host_text(title, text):
    """Uploads Text To Hosting Service. Tries Multiple Sources Until One Works."""
    # Order: Pastebin.com First (As Required), Then Reliable Backups
    order = [
        ("pastebin", lambda: upload_to_pastebin(text)),
        ("dpaste", lambda: upload_to_dpaste(text)),
        ("hastebin", lambda: upload_to_hastebin(text)),
        ("pastie", lambda: upload_to_pastie(text)),
        ("telegraph", lambda: upload_to_telegraph(title, text)),
    ]
    for name, func in order:
        try:
            url = await func()
            if url:
                log.info(f"Hosted Via {name}: {url}")
                return url
        except Exception as e:
            log.warning(f"{name} Failed: {e}")
    log.error("All Text Hosting Services Failed!")
    return None


# ============== Discord Webhook ==============
async def send_discord(text):
    """Sends Message To Discord Webhook If Configured"""
    url = get_setting("discord_webhook", "")
    if not url:
        return
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url, json={"content": text}, timeout=10)
    except Exception as e:
        log.warning(f"Discord Webhook Failed: {e}")


# ============== Formatting Helpers ==============
def fmt_money(amount):
    return f"{round(float(amount), 2)}$"


def title_case(s):
    """Converts A String To Title Case (First Letter Of Every Word Capital)"""
    if not s:
        return s
    return " ".join(w.capitalize() for w in s.split())
