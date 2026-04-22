"""
Payment Gateway Integrations — No Domain Required
- Cryptomus: Auto-Polling (Check API Every 30s)
- CryptoBot: Auto-Polling (Check API Every 30s)
- Binance: Uses Binance Exchange API (api.binance.com) With HMAC-SHA256
           User Pays Manually → Bot Checks sapi/v1/pay/transactions → Auto-Credits
"""

import aiohttp
import hashlib
import hmac
import base64
import json
import time
import urllib.parse
import logging
import asyncio
from database import get_payment_system

log = logging.getLogger(__name__)


# ============== Cryptomus (Auto Polling) ==============
class Cryptomus:
    API = "https://api.cryptomus.com/v1"

    @staticmethod
    def _sign(payload_str, api_key):
        return hashlib.md5(
            (base64.b64encode(payload_str.encode()).decode() + api_key).encode()
        ).hexdigest()

    @staticmethod
    async def create_payment(user_id, amount, order_id):
        ps = get_payment_system("Cryptomus")
        if not ps or not ps["enabled"] or not ps["api_key"] or not ps["merchant_id"]:
            return None, "Cryptomus Is Not Configured Or Disabled"
        payload = {
            "amount": str(amount),
            "currency": "USD",
            "order_id": order_id,
        }
        payload_str = json.dumps(payload, separators=(",", ":"))
        sign = Cryptomus._sign(payload_str, ps["api_key"])
        headers = {
            "merchant": ps["merchant_id"],
            "sign": sign,
            "Content-Type": "application/json",
        }
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{Cryptomus.API}/payment", data=payload_str, headers=headers, timeout=20) as r:
                    data = await r.json()
                    if data.get("state") == 0 and data.get("result"):
                        return data["result"].get("url"), None
                    return None, data.get("message", "Cryptomus Error")
        except Exception as e:
            log.error(f"Cryptomus Error: {e}")
            return None, str(e)

    @staticmethod
    async def check_payment(order_id):
        ps = get_payment_system("Cryptomus")
        if not ps or not ps["api_key"] or not ps["merchant_id"]:
            return None
        payload = {"order_id": order_id}
        payload_str = json.dumps(payload, separators=(",", ":"))
        sign = Cryptomus._sign(payload_str, ps["api_key"])
        headers = {
            "merchant": ps["merchant_id"],
            "sign": sign,
            "Content-Type": "application/json",
        }
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{Cryptomus.API}/payment/info", data=payload_str, headers=headers, timeout=15) as r:
                    data = await r.json()
                    if data.get("state") == 0 and data.get("result"):
                        status = data["result"].get("status", "")
                        if status in ("paid", "paid_over"):
                            return "paid"
                        if status in ("cancel", "fail", "system_fail", "wrong_amount"):
                            return "cancel"
                        return "pending"
        except Exception as e:
            log.error(f"Cryptomus Check Error: {e}")
        return None

    @staticmethod
    async def get_balance():
        ps = get_payment_system("Cryptomus")
        if not ps or not ps["api_key"] or not ps["merchant_id"]:
            return None
        payload_str = json.dumps({}, separators=(",", ":"))
        sign = Cryptomus._sign(payload_str, ps["api_key"])
        headers = {"merchant": ps["merchant_id"], "sign": sign, "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{Cryptomus.API}/balance", data=payload_str, headers=headers, timeout=15) as r:
                    data = await r.json()
                    if data.get("state") == 0:
                        result = data.get("result", [{}])
                        if isinstance(result, list) and result:
                            merchant_balance = result[0].get("balance", {}).get("merchant", [])
                            if merchant_balance:
                                lines = [f"{b.get('currency_code')}: {b.get('balance')}" for b in merchant_balance[:5]]
                                return "\n".join(lines)
                        return "No Balance Data"
        except Exception as e:
            log.error(f"Cryptomus Balance Error: {e}")
        return None


# ============== CryptoBot (Auto Polling) ==============
class CryptoBot:
    API = "https://pay.crypt.bot/api"

    @staticmethod
    async def create_invoice(user_id, amount, order_id):
        ps = get_payment_system("CryptoBot")
        if not ps or not ps["enabled"] or not ps["api_key"]:
            return None, "CryptoBot Is Not Configured Or Disabled"
        headers = {"Crypto-Pay-API-Token": ps["api_key"]}
        payload = {
            "asset": "USDT",
            "amount": str(amount),
            "description": f"Top-Up For User {user_id}",
            "payload": order_id,
        }
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{CryptoBot.API}/createInvoice", json=payload, headers=headers, timeout=15) as r:
                    data = await r.json()
                    if data.get("ok") and data.get("result"):
                        return data["result"]["pay_url"], None
                    return None, data.get("error", {}).get("name", "CryptoBot Error")
        except Exception as e:
            log.error(f"CryptoBot Error: {e}")
            return None, str(e)

    @staticmethod
    async def check_payment(order_id):
        ps = get_payment_system("CryptoBot")
        if not ps or not ps["api_key"]:
            return None
        headers = {"Crypto-Pay-API-Token": ps["api_key"]}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{CryptoBot.API}/getInvoices", headers=headers, timeout=15) as r:
                    data = await r.json()
                    if data.get("ok"):
                        items = data.get("result", {}).get("items", [])
                        for inv in items:
                            if inv.get("payload") == order_id:
                                status = inv.get("status", "")
                                if status == "paid":
                                    return "paid"
                                if status == "expired":
                                    return "cancel"
                                return "pending"
        except Exception as e:
            log.error(f"CryptoBot Check Error: {e}")
        return None

    @staticmethod
    async def get_balance():
        ps = get_payment_system("CryptoBot")
        if not ps or not ps["api_key"]:
            return None
        headers = {"Crypto-Pay-API-Token": ps["api_key"]}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{CryptoBot.API}/getBalance", headers=headers, timeout=15) as r:
                    data = await r.json()
                    if data.get("ok"):
                        balances = data.get("result", [])
                        lines = [f"{b.get('currency_code')}: {b.get('available')}" for b in balances[:5]]
                        return "\n".join(lines) if lines else "No Balance"
        except Exception as e:
            log.error(f"CryptoBot Balance Error: {e}")
        return None


# ============== Binance (Exchange API With HMAC-SHA256) ==============
class Binance:
    """
    Uses Binance Exchange API (api.binance.com) With HMAC-SHA256 Signing.

    Admin Config:
    - merchant_id = Binance Pay UID (Shown In Binance App → Pay → Your Pay ID, e.g., 358985073)
    - api_key     = Binance API Key (Create In Binance → API Management)
    - secret_key  = Binance API Secret

    User Flow:
    1. User Picks Amount → Bot Shows Pay ID + Telegram ID As Note
    2. User Transfers In Binance App With Note = Their Telegram ID
    3. User Clicks "Check Payment" → Bot Calls sapi/v1/pay/transactions
    4. Bot Scans Transactions For: USDT + Matching Amount + Note Contains User ID + After Bill Unix
    5. If Match Found → Auto-Credits
    """
    BASE_URL = "https://api.binance.com"

    @staticmethod
    def _sign(query_string, api_secret):
        """HMAC-SHA256 Signature"""
        return hmac.new(
            api_secret.encode(),
            query_string.encode(),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    async def _request(endpoint, api_key=None, api_secret=None, params=None):
        """Signed GET Request To Binance Exchange API"""
        if api_key is None or api_secret is None:
            ps = get_payment_system("Binance")
            if not ps:
                return False, "Binance Not Configured"
            api_key = ps["api_key"]
            api_secret = ps["secret_key"]
            if not api_key or not api_secret:
                return False, "Binance API Keys Not Set"

        if params is None:
            params = {"timestamp": int(time.time() * 1000)}
        else:
            params["timestamp"] = int(time.time() * 1000)

        query_string = urllib.parse.urlencode(params)
        sign = Binance._sign(query_string, api_secret)
        url = f"{Binance.BASE_URL}/{endpoint}?{query_string}&signature={sign}"
        headers = {"X-MBX-APIKEY": api_key}

        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=headers, ssl=False, timeout=20) as r:
                    data = await r.json()
                    if r.status == 200:
                        return True, data
                    log.warning(f"Binance API Error {r.status}: {data}")
                    return False, data
        except Exception as e:
            log.error(f"Binance Request Error: {e}")
            return False, str(e)

    @staticmethod
    async def create_order(user_id, amount, order_id):
        """
        Does NOT Call Any API. Just Returns Manual Payment Instructions Marker.
        User Pays Directly To Admin's Binance Pay UID With Their Telegram ID In Note.
        """
        ps = get_payment_system("Binance")
        if not ps or not ps["enabled"]:
            return None, "Binance Is Not Configured Or Disabled"
        if not ps["merchant_id"]:
            return None, "Admin Has Not Set Binance Pay UID Yet"
        # Return A Special Marker So The Bot Knows To Show Manual Instructions
        return f"MANUAL_BINANCE|{ps['merchant_id']}|{user_id}|{amount}", None

    @staticmethod
    async def check_payment(user_id, amount, bill_unix_ms=None):
        """
        Checks Recent Binance Pay Transactions For A Matching Payment.
        Returns (True, order_id) If Found, (False, None) Otherwise.

        Matches:
        - Currency == USDT
        - Amount Equals Bill Amount
        - Note Contains User's Telegram ID
        - Transaction Time >= Bill Creation Time
        """
        if bill_unix_ms is None:
            # Default: Look Back 3 Days
            bill_unix_ms = int(time.time() * 1000) - (3 * 24 * 60 * 60 * 1000)

        status, response = await Binance._request("sapi/v1/pay/transactions")
        if not status:
            return False, None

        if response.get("message") != "success":
            return False, None

        target_amount = str(amount)
        target_id_str = str(user_id)

        for payment in response.get("data", []):
            pay_note = str(payment.get("note") or "")
            pay_order_id = payment.get("orderId", "")
            pay_amount = payment.get("amount", "")
            pay_currency = payment.get("currency", "")
            pay_unix = payment.get("transactionTime", 0)

            # Currency USDT
            if pay_currency != "USDT":
                continue
            # Transaction After Bill Creation
            if pay_unix < bill_unix_ms:
                continue
            # Amount Match (String Comparison To Avoid Float Issues)
            if str(pay_amount) != target_amount and abs(float(pay_amount) - float(amount)) > 0.01:
                continue
            # Note Contains User ID
            if pay_note != target_id_str and target_id_str not in pay_note:
                continue
            # Match Found
            return True, pay_order_id

        return False, None

    @staticmethod
    async def get_balance():
        """Get Binance Spot Account Balance"""
        ps = get_payment_system("Binance")
        if not ps or not ps["api_key"] or not ps["secret_key"]:
            if ps and ps["merchant_id"]:
                return f"Binance Pay UID: {ps['merchant_id']}\nAPI Keys Not Set — Check Balance In Binance App"
            return "Binance Not Configured"

        status, response = await Binance._request("api/v3/account")
        if not status:
            return f"❌ Error: {response}"

        # Sort Balances By Free Amount, Show Non-Zero
        balances = response.get("balances", [])
        non_zero = [b for b in balances if float(b.get("free", 0)) > 0]
        non_zero.sort(key=lambda b: float(b["free"]), reverse=True)

        if not non_zero:
            return "All Balances Are Zero"

        lines = [f"▪️ {b['asset']}: {b['free']}" for b in non_zero[:10]]
        return "\n".join(lines)

    @staticmethod
    async def verify_keys(api_key, api_secret):
        """Verify API Key + Secret By Calling api/v3/account. Returns (True, UID) Or (False, Reason)."""
        status, response = await Binance._request("api/v3/account", api_key=api_key, api_secret=api_secret)
        if status and isinstance(response, dict):
            return True, response.get("uid", "Unknown")
        return False, str(response)


# ============== Helpers ==============
async def create_payment_url(gateway, user_id, amount, order_id):
    if gateway == "Cryptomus":
        return await Cryptomus.create_payment(user_id, amount, order_id)
    if gateway == "CryptoBot":
        return await CryptoBot.create_invoice(user_id, amount, order_id)
    if gateway == "Binance":
        return await Binance.create_order(user_id, amount, order_id)
    return None, "Unknown Gateway"


async def get_gateway_balance(gateway):
    if gateway == "Cryptomus":
        return await Cryptomus.get_balance()
    if gateway == "CryptoBot":
        return await CryptoBot.get_balance()
    if gateway == "Binance":
        return await Binance.get_balance()
    return None


async def check_payment_status(gateway, order_id, user_id=None, amount=None, bill_unix_ms=None):
    if gateway == "Cryptomus":
        return await Cryptomus.check_payment(order_id)
    if gateway == "CryptoBot":
        return await CryptoBot.check_payment(order_id)
    if gateway == "Binance":
        if user_id is None or amount is None:
            return None
        found, _ = await Binance.check_payment(user_id, amount, bill_unix_ms)
        return "paid" if found else "pending"
    return None


# ============== Polling Loop (Auto — Cryptomus + CryptoBot) ==============
async def payment_polling_loop(bot):
    """Background Task: Auto-Checks Pending Cryptomus/CryptoBot Top-Ups Every 30s"""
    import database as db

    log.info("💰 Payment Polling Started (Auto-Check Every 30s For Cryptomus + CryptoBot)")
    while True:
        try:
            conn = db.get_connection()
            c = conn.cursor()
            c.execute(
                "SELECT * FROM topups WHERE status='pending' AND gateway IN ('Cryptomus', 'CryptoBot') ORDER BY id DESC LIMIT 50"
            )
            pending = [dict(r) for r in c.fetchall()]
            conn.close()

            for t in pending:
                order_id = t["receipt"]
                gateway = t["gateway"]
                status = await check_payment_status(gateway, order_id)

                if status == "paid":
                    await _credit_topup(bot, t)
                elif status == "cancel":
                    conn = db.get_connection()
                    conn.execute("UPDATE topups SET status='cancelled' WHERE id=?", (t["id"],))
                    conn.commit()
                    conn.close()

                await asyncio.sleep(0.5)
        except Exception as e:
            log.error(f"Polling Loop Error: {e}")
        await asyncio.sleep(30)


async def _credit_topup(bot, topup_row):
    """Credits A User's Balance And Sends Notifications"""
    import database as db
    from utils import fmt_money, send_discord
    import config
    from telegram.constants import ParseMode
    import html as html_lib

    t = topup_row
    user_id = t["user_id"]
    amount = float(t["amount"])
    gateway = t["gateway"]

    conn = db.get_connection()
    conn.execute("UPDATE topups SET status='completed' WHERE id=?", (t["id"],))
    conn.commit()
    conn.close()
    db.add_balance(user_id, amount, from_admin=False)

    u = db.get_user(user_id)
    uname = u.get("username") or "—"
    name = html_lib.escape(u.get("first_name") or "—")
    receipt = f"#{t['receipt']}"
    msg = (
        f"👤 User: @{uname} | {name} | <code>{user_id}</code>\n"
        f"💰 Top-Up Amount: {fmt_money(amount)} ({gateway} - USDT)\n"
        f"🧾 Receipt: <code>{receipt}</code>"
    )
    try:
        await bot.send_message(user_id, f"✅ Balance Topped-Up!\n\n{msg}", parse_mode=ParseMode.HTML)
    except Exception:
        pass
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, msg, parse_mode=ParseMode.HTML)
        except Exception:
            pass
    await send_discord(
        f"💰 Top-Up\nUser: @{uname} | {user_id}\n"
        f"Amount: {fmt_money(amount)} ({gateway} - USDT)\nReceipt: {receipt}"
    )
    log.info(f"✅ Top-Up Credited: {user_id} +{amount}$ ({gateway})")
