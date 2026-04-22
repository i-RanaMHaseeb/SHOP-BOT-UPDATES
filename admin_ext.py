"""
Admin Extensions
Statistics Report, Database Send, Log Send, Scheduled Daily Jobs.
(Payment Verification Is Handled By Polling In payments.py — No Webhooks)
"""

import logging
import os
from datetime import datetime
from telegram import InputFile
from telegram.constants import ParseMode

import config
import database as db
from utils import fmt_money, today_date, today_week, today_month

log = logging.getLogger(__name__)


# ============== Statistics ==============
def build_statistics_text():
    s = db.get_statistics()
    gw_lines = []
    for gw in ["CryptoBot", "Cryptomus", "Binance"]:
        cnt, total = s["gateways"].get(gw, (0, 0))
        gw_lines.append(f"├ {gw}: {cnt}pcs - {fmt_money(total)}")
    gw_text = "\n".join(gw_lines) if gw_lines else "├ None"

    text = (
        "📊 *BOT STATISTICS*\n"
        "➖➖➖➖➖➖\n"
        "👤 *Users*\n"
        f"├ Users Per Day: {s['users']['day']}\n"
        f"├ Users Per Week: {s['users']['week']}\n"
        f"├ Users Per Month: {s['users']['month']}\n"
        f"└ Users For All Time: {s['users']['all']}\n\n"
        "💰 *Funds*\n"
        "├— Sales (Pcs, Amount)\n"
        f"├ Per Day: {s['sales']['day'][0]}pcs - {fmt_money(s['sales']['day'][1])}\n"
        f"├ Per Week: {s['sales']['week'][0]}pcs - {fmt_money(s['sales']['week'][1])}\n"
        f"├ Per Month: {s['sales']['month'][0]}pcs - {fmt_money(s['sales']['month'][1])}\n"
        f"├ For All Time: {s['sales']['all'][0]}pcs - {fmt_money(s['sales']['all'][1])}\n"
        "|\n"
        "├— Top-Up (Pcs, Amount)\n"
        f"├ Per Day: {s['topups']['day'][0]}pcs - {fmt_money(s['topups']['day'][1])}\n"
        f"├ Per Week: {s['topups']['week'][0]}pcs - {fmt_money(s['topups']['week'][1])}\n"
        f"├ Per Month: {s['topups']['month'][0]}pcs - {fmt_money(s['topups']['month'][1])}\n"
        f"├ For All Time: {s['topups']['all'][0]}pcs - {fmt_money(s['topups']['all'][1])}\n"
        "|\n"
        "├— Payment Systems (All)\n"
        f"{gw_text}\n"
        "|\n"
        "├— Other\n"
        f"├ Total Funds Gives: {fmt_money(s['total_given'])}\n"
        f"└ Total Funds In System: {fmt_money(s['total_in_system'])}\n\n"
        "🎁 *Products*\n"
        f"├ Items: {s['items']}pcs\n"
        f"├ Positions: {s['positions']}pcs\n"
        f"└ Categories: {s['categories']}pcs\n\n"
        "🕰️ *Dates Of Statistics*\n"
        f"├ For A Day: {today_date()}\n"
        f"├ For A Week: {today_week()}\n"
        f"└ For A Month: {today_month()}"
    )
    return text


async def send_statistics(bot, chat_id):
    await bot.send_message(chat_id, build_statistics_text(), parse_mode=ParseMode.MARKDOWN)


# ============== Database & Log Send ==============
async def send_database(bot, chat_id):
    if not os.path.exists(config.DB_FILE):
        await bot.send_message(chat_id, "❌ Database File Not Found.")
        return
    try:
        with open(config.DB_FILE, "rb") as f:
            await bot.send_document(chat_id, InputFile(f, filename=f"shop_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"))
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Failed To Send Database: {e}")


async def send_logs(bot, chat_id):
    if not os.path.exists(config.LOG_FILE):
        await bot.send_message(chat_id, "❌ Log File Not Found.")
        return
    try:
        with open(config.LOG_FILE, "rb") as f:
            await bot.send_document(chat_id, InputFile(f, filename=f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"))
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Failed To Send Logs: {e}")


# ============== Scheduled Daily Job ==============
async def daily_report_job(bot):
    """Runs Every Day At Configured Hour — Sends Database + Statistics To All Admins"""
    log.info("Running Daily Report Job")
    for admin_id in config.ADMIN_IDS:
        try:
            await send_statistics(bot, admin_id)
            await send_database(bot, admin_id)
        except Exception as e:
            log.warning(f"Daily Report Failed For {admin_id}: {e}")


