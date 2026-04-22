"""
Main Bot Handlers
Telegram Shop Bot — Full Implementation
All Wording Is In Title Case (First Letter Of Every Word Capital)
Users See Only User Buttons, Admins See All
"""

import logging
import asyncio
import os
import time
from datetime import datetime
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, BotCommandScopeChat,
    BotCommandScopeDefault, InputFile,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)
from telegram.error import Forbidden, BadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import database as db
import keyboards as kb
from keyboards import (
    BTN_BUY, BTN_PROFILE, BTN_AVAILABILITY, BTN_SUPPORT, BTN_FAQ,
    BTN_MANAGE_ITEMS, BTN_STATISTICS, BTN_SETTINGS, BTN_GENERAL_FUNCS, BTN_PAYMENT_SYSTEMS,
    is_admin,
)
from utils import (
    generate_receipt, now_str, today_date, today_week, today_month,
    days_since, host_text, send_discord, fmt_money,
)
from payments import create_payment_url, get_gateway_balance, Cryptomus, CryptoBot, Binance

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler(config.LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)


# ============== State Tracking ==============
# Simple In-Memory State: {user_id: {"action": "...", "data": {...}}}
STATE = {}


def set_state(uid, action, **data):
    STATE[uid] = {"action": action, "data": data}


def get_state(uid):
    return STATE.get(uid)


def clear_state(uid):
    STATE.pop(uid, None)


# ============== Start Command + Deep Link ==============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.username, user.first_name)

    # Check For Deep Link Parameter (Copy Link Feature)
    args = context.args if context.args else []
    if args:
        arg = args[0]
        if arg.startswith("p_"):
            try:
                pid = int(arg[2:])
                return await open_position_for_user(update, context, pid)
            except Exception:
                pass
        if arg.startswith("c_"):
            try:
                cid = int(arg[2:])
                return await open_category_for_user(update, context, cid)
            except Exception:
                pass

    # Maintenance Check (Users Only, Not Admin)
    if not is_admin(user.id) and db.get_setting("maintenance") == "1":
        await update.message.reply_text(
            "🛠️ Store Is Under Maintenance, Please Check Back Later."
        )
        return

    text = (
        "🔸 The Bot Is Ready To Be Used.\n"
        "🔸 If No Auxiliary Buttons Appear\n"
        "🔸 Enter /start"
    )
    await update.message.reply_text(text, reply_markup=kb.main_menu_keyboard(user.id))


async def set_bot_commands(app: Application):
    """Sets Side Menu Commands — Different For Admins And Users"""
    user_cmds = [
        BotCommand("start", "♻️ Restart Bot"),
        BotCommand("support", "☎️ Support"),
        BotCommand("faq", "❓ FAQ"),
    ]
    admin_cmds = user_cmds + [
        BotCommand("db", "📦 Get Database"),
        BotCommand("log", "🖨️ Get Logs"),
    ]
    await app.bot.set_my_commands(user_cmds, scope=BotCommandScopeDefault())
    for admin_id in config.ADMIN_IDS:
        try:
            await app.bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(admin_id))
        except Exception as e:
            log.warning(f"Could Not Set Admin Commands For {admin_id}: {e}")


# ============== Profile ==============
async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = db.get_user(uid)
    if not u:
        db.register_user(uid, update.effective_user.username, update.effective_user.first_name)
        u = db.get_user(uid)

    days = days_since(u["registration"]) if u.get("registration") else 0
    reg_date = u["registration"].split(" ")[0] if u.get("registration") else "—"

    text = (
        "👤 *Your Profile*\n"
        "➖➖➖➖➖➖\n"
        f"🆔 ID: `{u['user_id']}`\n"
        f"💰 Balance: {fmt_money(u['balance'])}\n"
        f"🎁 Purchased Goods: {u['purchased']}pcs\n"
        f"🕰️ Registration: {reg_date} ({days} Days)"
    )
    await update.message.reply_text(
        text, reply_markup=kb.profile_inline(), parse_mode=ParseMode.MARKDOWN
    )


# ============== Availability Of Goods ==============
async def show_availability(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hide_cats = db.get_setting("hide_empty_categories") == "1"
    hide_pos = db.get_setting("hide_empty_positions") == "1"

    cats = db.get_categories(hide_empty=hide_cats)
    if not cats:
        await update.message.reply_text("📭 No Goods Available At The Moment.")
        return

    lines = []
    for cat in cats:
        positions = db.get_positions(cat["id"], hide_empty=hide_pos)
        if not positions and hide_pos:
            continue
        lines.append(f"— — — *{cat['name']}* — — —")
        for pos in positions:
            stock = db.position_stock_count(pos["id"])
            lines.append(f"{pos['name']} | {fmt_money(pos['price'])} | In Stock {stock} Pcs")
        lines.append("")

    text = "\n".join(lines) if lines else "📭 No Goods Available."
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ============== Support ==============
async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = db.get_setting("support_username", "admin")
    text = "☎️ *Click The Button Below To Contact The Administrator*"
    await update.message.reply_text(
        text, reply_markup=kb.support_inline(username), parse_mode=ParseMode.MARKDOWN
    )


# ============== FAQ ==============
async def show_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = db.get_setting("faq_text", "⚠️ *Store Rules – Read Before Buying!* ⚠️")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ============== Buy Flow ==============
async def show_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check Purchases Switch
    if db.get_setting("purchases_on") != "1" and not is_admin(update.effective_user.id):
        await update.message.reply_text("🛠️ Purchases Are Temporarily Disabled.")
        return

    hide_cats = db.get_setting("hide_empty_categories") == "1"
    cats = db.get_categories(hide_empty=hide_cats)
    if not cats:
        await update.message.reply_text("📭 No Categories Available.")
        return
    await update.message.reply_text(
        "🎁 *Select A Category*", reply_markup=kb.buy_categories_inline(cats), parse_mode=ParseMode.MARKDOWN
    )


async def open_category_for_user(update, context, cid):
    """Opens Category Via Deep Link — Shows Photo + Info + Positions"""
    import html as _html
    cat = db.get_category(cid)
    if not cat:
        await update.message.reply_text("❌ Category Not Found.")
        return
    hide_pos = db.get_setting("hide_empty_positions") == "1"
    positions = db.get_positions(cid, hide_empty=hide_pos)

    cat_name_html = _html.escape(cat["name"])
    if not positions:
        body = "📭 No Products Available In This Category."
    else:
        position_lines = []
        for p in positions:
            stock = db.position_stock_count(p["id"])
            from utils import fmt_money
            position_lines.append(f"▪️ {p['name']} | {fmt_money(p['price'])} | In Stock {stock} Pcs")
        body = "\n".join(position_lines)

    caption = (
        f"🗃️ <b>{cat_name_html}</b>\n"
        f"➖➖➖➖➖➖\n"
        f"{body}\n\n"
        f"Choose A Position To Buy:"
    )
    reply_markup = kb.buy_positions_inline(positions) if positions else None

    photo_id = cat.get("photo")
    if photo_id:
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo_id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
            return
        except Exception:
            pass
    await update.message.reply_text(
        caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML,
    )


async def open_position_for_user(update, context, pid):
    """Opens Position Via Deep Link"""
    pos = db.get_position(pid)
    if not pos:
        await update.message.reply_text("❌ Position Not Found.")
        return
    cat = db.get_category(pos["category_id"])
    stock = db.position_stock_count(pid)
    cat_name = cat["name"] if cat else "—"
    text = (
        f"🎁 *{pos['name']}*\n"
        f"➖➖➖➖➖➖\n"
        f"🗃️ Category: {cat_name}\n"
        f"💵 Price: {fmt_money(pos['price'])}\n"
        f"📦 In Stock: {stock} Pcs\n"
    )
    if pos.get("description"):
        text += f"\n📝 {pos['description']}"
    await update.message.reply_text(
        text, reply_markup=kb.buy_position_inline(pid, stock), parse_mode=ParseMode.MARKDOWN
    )
