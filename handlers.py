"""
Callback Query Handlers
Handles All Inline Button Clicks For Both Users And Admins
"""

import logging
import asyncio
import os
import time
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import Forbidden, BadRequest

import config
import database as db
import keyboards as kb
from keyboards import is_admin
from utils import (
    generate_receipt, now_str, days_since, host_text, send_discord, fmt_money,
)
from payments import create_payment_url, get_gateway_balance

log = logging.getLogger(__name__)

# Shared State From bot.py
from bot import STATE, set_state, get_state, clear_state


async def safe_edit(query, text=None, reply_markup=None, parse_mode=ParseMode.MARKDOWN):
    # Check If The Current Message Is A Photo — Can't Edit Text Of A Photo Message
    is_photo_message = bool(query.message.photo)

    if is_photo_message and text is not None:
        # Delete The Photo Message And Send A New Text Message
        try:
            await query.message.delete()
        except Exception:
            pass
        try:
            await query.message.chat.send_message(
                text=text, reply_markup=reply_markup, parse_mode=parse_mode,
            )
        except BadRequest as e:
            if "Can't parse entities" in str(e) or "can't find end" in str(e):
                await query.message.chat.send_message(
                    text=text, reply_markup=reply_markup, parse_mode=None,
                )
            else:
                log.warning(f"Send After Photo Delete Failed: {e}")
        return

    try:
        if text is not None:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        elif reply_markup is not None:
            await query.edit_message_reply_markup(reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return
        if "Can't parse entities" in str(e) or "can't find end" in str(e):
            try:
                if text is not None:
                    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)
                return
            except Exception as e2:
                log.warning(f"Plain Edit Also Failed: {e2}")
        # If We Can't Edit (Message Is Photo Or Too Old), Send New Message Instead
        if "no text in the message to edit" in str(e) or "message can't be edited" in str(e):
            try:
                await query.message.delete()
            except Exception:
                pass
            try:
                await query.message.chat.send_message(
                    text=text, reply_markup=reply_markup, parse_mode=parse_mode,
                )
            except Exception as e3:
                log.warning(f"Fallback Send Failed: {e3}")
            return
        log.warning(f"Edit Failed: {e}")


# ============== Main Callback Router ==============
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    uid = query.from_user.id

    # ============== Clear Stuck States ==============
    # If User Had A Pending "Send Amount" Or Similar State, Cancel It —
    # Because Clicking Any Inline Button Means They Want A New Action.
    # EXCEPTION: Buy Custom Qty Is Kept Because It's Set By buy_now Which Is A Button.
    state = get_state(uid)
    if state and state["action"] not in ("ep_add_stock",):
        # Clear Previous State So User Doesn't Get Stuck
        # (ep_add_stock Is Kept Because It Allows Multi-Batch Uploads With Finish Button)
        clear_state(uid)

    # ============== Common ==============
    if data == "back_main":
        await query.message.delete()
        return
    if data == "close_msg":
        await query.message.delete()
        return

    # ============== User: Profile ==============
    if data == "topup":
        return await handle_topup_start(update, context)
    if data == "my_purchases":
        return await show_my_purchases(update, context)

    # ============== User: Binance Check Payment ==============
    if data.startswith("bnb_check:"):
        return await handle_binance_check(update, context, data.split(":", 1)[1])

    # ============== User: Buy ==============
    if data.startswith("buy_cat:"):
        return await buy_show_category(update, context, int(data.split(":")[1]))
    if data == "buy_back_cats":
        return await buy_back_to_cats(update, context)
    if data.startswith("buy_pos:"):
        return await buy_show_position(update, context, int(data.split(":")[1]))
    if data.startswith("buy_pos_back:"):
        pid = int(data.split(":")[1])
        pos = db.get_position(pid)
        if pos:
            return await buy_show_category(update, context, pos["category_id"])
        return
    if data.startswith("buy_now:"):
        return await buy_now(update, context, int(data.split(":")[1]))
    if data.startswith("buy_qty:"):
        parts = data.split(":")
        return await buy_execute(update, context, int(parts[1]), int(parts[2]))
    if data.startswith("buy_qty_custom:"):
        return await buy_qty_custom(update, context, int(data.split(":")[1]))

    # ============== User: Top-Up Gateway ==============
    if data.startswith("pay_gateway:"):
        return await handle_topup_gateway_selection(update, context, data.split(":")[1])

    # ============== Admin-Only From Here ==============
    if not is_admin(uid):
        return

    # ============== General Functions ==============
    if data == "gf_find":
        set_state(uid, "find_user")
        return await safe_edit(
            query,
            "🔍 *Send User Id/Login Or Receipt Number*",
        )
    if data == "gf_mail":
        set_state(uid, "mail_wait_content")
        return await safe_edit(
            query,
            "📢 *Send Out A Post To Be Distributed To Users*\n"
            "❗ Posts With Any Media Files Are Supported",
        )
    if data == "mail_send":
        return await do_mailing(update, context)
    if data == "mail_cancel":
        clear_state(uid)
        return await safe_edit(query, "❌ Mailing Cancelled.")

    if data.startswith("u_setbal:"):
        target = int(data.split(":")[1])
        set_state(uid, "user_set_balance", target=target)
        return await safe_edit(query, f"💰 Send New Balance Amount For User {target}:")
    if data.startswith("u_addbal:"):
        target = int(data.split(":")[1])
        set_state(uid, "user_add_balance", target=target)
        return await safe_edit(query, f"💰 Send Amount To Add To User {target}:")
    if data.startswith("u_cutbal:"):
        target = int(data.split(":")[1])
        set_state(uid, "user_cut_balance", target=target)
        return await safe_edit(query, f"➖ Send Amount To Cut From User {target}:")
    if data.startswith("u_purchases:"):
        return await show_user_purchases_admin(update, context, int(data.split(":")[1]))
    if data.startswith("u_sms:"):
        target = int(data.split(":")[1])
        set_state(uid, "user_sms", target=target)
        return await safe_edit(query, f"💌 Send The Message To Be Sent To User {target}:")
    if data.startswith("u_remove:"):
        target = int(data.split(":")[1])
        return await safe_edit(
            query,
            f"🚫 Remove User {target}?",
            reply_markup=kb.yes_no_inline(f"u_remove_yes:{target}", "u_remove_no"),
        )
    if data.startswith("u_remove_yes:"):
        target = int(data.split(":")[1])
        db.ban_user(target)
        return await safe_edit(query, f"✅ User {target} Has Been Removed.")
    if data == "u_remove_no":
        return await safe_edit(query, "❌ Cancelled.")
    if data.startswith("u_refresh:"):
        return await refresh_user_profile(update, context, int(data.split(":")[1]))

    # ============== Payment Systems ==============
    if data.startswith("ps:"):
        return await show_payment_manage(update, context, data.split(":")[1])
    if data == "ps_back":
        return await safe_edit(
            query, "🔑 *Payment Systems Management*", reply_markup=kb.payment_systems_main_inline()
        )
    if data.startswith("ps_info:"):
        return await show_payment_info(update, context, data.split(":")[1])
    if data.startswith("ps_balance:"):
        return await show_payment_balance(update, context, data.split(":")[1])
    if data.startswith("ps_edit:"):
        return await start_payment_edit(update, context, data.split(":")[1])
    if data.startswith("ps_toggle:"):
        name = data.split(":")[1]
        new = db.toggle_payment_system(name)
        return await show_payment_manage(update, context, name)

    # ============== Settings ==============
    if data == "settings_edit":
        return await show_settings_edit(update, context)
    if data == "settings_switches":
        return await show_settings_switches(update, context)
    if data == "settings_back":
        return await safe_edit(
            query, "⚙️ *General Settings*", reply_markup=kb.settings_main_inline()
        )
    if data.startswith("ed:"):
        return await handle_edit_data(update, context, data.split(":")[1])
    if data.startswith("sw:"):
        return await toggle_switch(update, context, data.split(":")[1])

    # ============== Manage Items ==============
    if data == "mi_back":
        return await safe_edit(query, "🎁 *Manage Items*", reply_markup=kb.manage_items_inline())
    if data.startswith("mi:"):
        return await handle_manage_items_action(update, context, data.split(":")[1])
    if data.startswith("pick_cat_for_pos:"):
        cid = int(data.split(":")[1])
        set_state(uid, "create_pos_name", category_id=cid)
        return await safe_edit(query, "📁 *Enter A Name For The Position*")
    if data.startswith("pick_cat_to_edit:"):
        cid = int(data.split(":")[1])
        return await show_edit_category(update, context, cid)
    if data.startswith("pick_pos_to_edit:"):
        pid = int(data.split(":")[1])
        return await show_edit_position(update, context, pid)
    if data.startswith("pick_cat_pos:"):
        cid = int(data.split(":")[1])
        positions = db.get_positions(cid)
        if not positions:
            return await safe_edit(query, "📭 No Positions In This Category.")
        return await safe_edit(
            query, f"📁 *Select A Position*",
            reply_markup=kb.positions_list_inline(positions, "pick_pos_to_edit"),
        )

    # ============== Edit Position Actions ==============
    if data.startswith("ep:"):
        parts = data.split(":")
        action = parts[1]
        pid = int(parts[2]) if len(parts) > 2 else None
        return await handle_edit_position_action(update, context, action, pid)

    # ============== Edit Category Actions ==============
    if data.startswith("ec:"):
        parts = data.split(":")
        action = parts[1]
        cid = int(parts[2]) if len(parts) > 2 else None
        return await handle_edit_category_action(update, context, action, cid)

    # ============== Delete Stock Item ==============
    if data.startswith("del_stock:"):
        parts = data.split(":")
        stock_id = int(parts[1])
        pid = int(parts[2])
        db.delete_stock_item(stock_id)
        await query.answer("✅ Item Removed")
        return await show_edit_position(update, context, pid)

    # ============== Destroyer ==============
    if data == "destroyer_yes":
        db.destroy_all()
        return await safe_edit(query, "💥 All Categories, Positions And Stock Have Been Destroyed.")
    if data == "destroyer_no":
        return await safe_edit(query, "❌ Cancelled.")


# ============== User Buy Flow ==============
async def buy_show_category(update, context, cid):
    query = update.callback_query
    cat = db.get_category(cid)
    if not cat:
        return
    hide_pos = db.get_setting("hide_empty_positions") == "1"
    positions = db.get_positions(cid, hide_empty=hide_pos)

    import html as _html
    cat_name_html = _html.escape(cat["name"])

    if not positions:
        caption = (
            f"➖➖➖ <b>{cat_name_html}</b> ➖➖➖\n\n"
            f"📭 No Products Available In This Category."
        )
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back", callback_data="buy_back_cats")]]
        )
    else:
        caption = (
            f"➖➖➖ <b>{cat_name_html}</b> ➖➖➖\n\n"
            f"Choose A Position To Buy:"
        )
        reply_markup = kb.buy_positions_inline(positions)

    photo_id = cat.get("photo")
    if photo_id:
        # Send A New Photo Message (Delete Old Text Message)
        try:
            await query.message.delete()
        except Exception:
            pass
        try:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo_id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
            return
        except Exception as e:
            log.warning(f"Send Photo Failed, Falling Back To Text: {e}")

    # No Photo — Just Edit The Text Message
    try:
        await query.edit_message_text(caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return
        # Original Was A Photo Message — Can't Edit, Send New Text Message Instead
        try:
            await query.message.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )


async def buy_back_to_cats(update, context):
    hide_cats = db.get_setting("hide_empty_categories") == "1"
    cats = db.get_categories(hide_empty=hide_cats)
    await safe_edit(
        update.callback_query, "🎁 *Select A Category*",
        reply_markup=kb.buy_categories_inline(cats),
    )


async def buy_show_position(update, context, pid):
    pos = db.get_position(pid)
    if not pos:
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
    await safe_edit(update.callback_query, text, reply_markup=kb.buy_position_inline(pid, stock))


async def buy_now(update, context, pid):
    """Step 1: Show Product Info + Balance + Ask User To Type Quantity"""
    query = update.callback_query
    uid = query.from_user.id
    pos = db.get_position(pid)
    if not pos:
        return await safe_edit(query, "❌ Position Not Found.")
    stock = db.position_stock_count(pid)
    if stock < 1:
        return await safe_edit(query, "📭 Out Of Stock.")
    cat = db.get_category(pos["category_id"])
    cat_name = cat["name"] if cat else "—"
    user = db.get_user(uid)
    balance = float(user["balance"]) if user else 0.0

    set_state(uid, "buy_custom_qty", pid=pid)

    text = (
        f"🎁 <b>Enter The Number Of Items To Purchase</b>\n"
        f"❗ 1 To {stock}\n"
        f"➖➖➖➖➖➖\n"
        f"▪️ Category: {cat_name}\n"
        f"▪️ Product: {pos['name']}\n"
        f"▪️ Price Per Item: {fmt_money(pos['price'])}\n"
        f"▪️ In Stock: {stock} Pcs\n"
        f"▪️ Your Balance: {fmt_money(balance)}"
    )
    back_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back", callback_data=f"buy_pos:{pid}")]
    ])
    await safe_edit(query, text, reply_markup=back_kb, parse_mode=ParseMode.HTML)


async def buy_qty_custom(update, context, pid):
    """Legacy Handler - Same As buy_now Now"""
    await buy_now(update, context, pid)


async def buy_execute(update, context, pid, qty):
    """Step 2: Execute The Actual Purchase — Sends Product Data To User And Receipt"""
    query = update.callback_query
    uid = query.from_user.id
    pos = db.get_position(pid)
    if not pos:
        return await safe_edit(query, "❌ Position Not Found.")
    stock = db.position_stock_count(pid)
    if stock < qty:
        return await safe_edit(query, f"📭 Only {stock} Pcs Available.")
    user = db.get_user(uid)
    total_price = pos["price"] * qty
    if user["balance"] < total_price:
        need = total_price - user["balance"]
        return await safe_edit(
            query,
            f"❌ Insufficient Balance.\n\nTotal Cost: {fmt_money(total_price)}\n"
            f"Your Balance: {fmt_money(user['balance'])}\n"
            f"You Need {fmt_money(need)} More.\nPlease Top-Up Your Balance.",
        )

    items = db.reserve_stock(pid, qty)
    if not items or len(items) < qty:
        return await safe_edit(query, "📭 Not Enough Stock.")

    cat = db.get_category(pos["category_id"])
    cat_name = cat["name"] if cat else "—"
    data_text = "\n".join(i["data"] for i in items)
    receipt = generate_receipt()
    link = await host_text(f"{pos['name']} — Purchase", data_text) or ""

    db.record_purchase(
        uid, pid, pos["category_id"], pos["name"], cat_name,
        qty, total_price, receipt, data_text, link,
    )

    import html as _html
    username = query.from_user.username or "—"
    name = _html.escape(query.from_user.first_name or "—")
    link_html = f'<a href="{link}">Clickable</a>' if link else "❌ No Link"

    # Step A: Send The Actual Product Data To The Buyer As Numbered List
    numbered_lines = []
    for idx, item in enumerate(items, start=1):
        numbered_lines.append(f"{idx}. {_html.escape(item['data'])}")
    numbered_text = "\n".join(numbered_lines)

    # Telegram Has A 4096 Char Limit — Truncate If Needed
    if len(numbered_text) > 3800:
        numbered_text = numbered_text[:3800] + "\n\n[Truncated — See Full Data Via Link]"

    buyer_data_msg = (
        f"🎁 <b>{_html.escape(pos['name'])}</b>\n"
        f"➖➖➖➖➖➖\n\n"
        f"{numbered_text}"
    )
    await query.message.reply_text(buyer_data_msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    # Step B: Send Purchase Confirmation Receipt To Buyer (With Clickable Link)
    buyer_receipt = (
        "✅ <b>You Have Successfully Purchased The Item(s)</b>\n"
        "➖➖➖➖➖➖\n"
        f"▪️ Receipt: <code>{receipt}</code>\n"
        f"▪️ Product: {cat_name} | {pos['name']} | {qty}pcs | {fmt_money(total_price)}\n"
        f"▪️ Products Data: {link_html}\n"
        f"▪️ Date Of Purchase: {now_str()}"
    )
    await query.message.reply_text(buyer_receipt, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    # Step C: Send Admin Notification (With Full Info + Link)
    admin_text = (
        "🎁 <b>New Purchase</b>\n"
        "➖➖➖➖➖➖\n"
        f"▪️ User: @{username} | {name} | <code>{uid}</code>\n"
        f"▪️ Receipt: <code>{receipt}</code>\n"
        f"▪️ Product: {cat_name} | {pos['name']} | {qty}pcs | {fmt_money(total_price)}\n"
        f"▪️ Products Data: {link_html}\n"
        f"▪️ Date Of Purchase: {now_str()}"
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, admin_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception:
            pass

    # Step D: Discord Notification
    await send_discord(
        f"🎁 New Purchase\nUser: @{username} | {uid}\n"
        f"Receipt: {receipt}\nProduct: {cat_name} | {pos['name']} | {qty}pcs | {fmt_money(total_price)}\n"
        f"Link: {link}\nDate: {now_str()}"
    )

    try:
        await query.message.delete()
    except Exception:
        pass


# ============== Top-Up Flow ==============
async def handle_topup_start(update, context):
    query = update.callback_query
    if db.get_setting("refills_on") != "1":
        return await safe_edit(query, "🛠️ Top-Ups Are Temporarily Disabled.")
    gateways = [ps for ps in db.get_all_payment_systems() if ps["enabled"]]
    if not gateways:
        return await safe_edit(query, "❌ No Payment Systems Are Currently Available.")
    names = [g["name"] for g in gateways]
    await safe_edit(query, "💰 *Select Payment System*", reply_markup=kb.topup_gateways_inline(names))


async def handle_topup_gateway_selection(update, context, gateway):
    query = update.callback_query
    uid = query.from_user.id
    set_state(uid, "topup_amount", gateway=gateway)
    await safe_edit(query, f"💵 Send The Amount To Top-Up Via *{gateway}* (In USD):")


async def handle_binance_check(update, context, order_id):
    """Called When User Clicks '🔄 Check Payment' On A Manual Binance Top-Up"""
    query = update.callback_query
    uid = query.from_user.id

    # Find The Pending Topup In Database
    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM topups WHERE receipt=? AND user_id=?", (order_id, uid))
    row = c.fetchone()
    conn.close()

    if not row:
        return await query.answer("❌ Top-Up Not Found", show_alert=True)
    topup = dict(row)
    if topup["status"] == "completed":
        return await query.answer("✅ Already Credited!", show_alert=True)
    if topup["status"] == "cancelled":
        return await query.answer("❌ This Top-Up Was Cancelled", show_alert=True)

    from payments import Binance, _credit_topup
    from datetime import datetime
    amount = float(topup["amount"])

    # Show "Checking..." Feedback
    await query.answer("🔄 Checking Payment...")

    ps = db.get_payment_system("Binance")
    if not ps or not ps["api_key"] or not ps["secret_key"]:
        # No API Keys — Notify Admin To Manually Verify
        from utils import fmt_money
        import config as cfg
        for admin_id in cfg.ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"⚠️ <b>Manual Binance Verification Needed</b>\n"
                    f"User: <code>{uid}</code>\n"
                    f"Amount: {fmt_money(amount)}\n"
                    f"Pay UID: <code>{ps['merchant_id'] if ps else '—'}</code>\n"
                    f"Order: <code>{order_id}</code>\n\n"
                    f"Check Binance App For Transfer With Note: <code>{uid}</code>\n"
                    f"If Received, Use Find → Add Balance To Credit User.",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
        return await query.message.reply_text(
            "⏳ Payment Check Request Sent To Admin.\n"
            "You Will Be Notified Once Verified."
        )

    # Compute Bill Creation Unix Time From The Order ID (topup_<uid>_<unix>)
    bill_unix_ms = None
    try:
        parts = order_id.split("_")
        if len(parts) >= 3:
            bill_unix_ms = int(parts[2]) * 1000
    except Exception:
        pass

    found, bnb_order_id = await Binance.check_payment(uid, amount, bill_unix_ms)
    if found:
        # Save Binance Order ID As Receipt Reference
        conn = db.get_connection()
        conn.execute("UPDATE topups SET receipt=? WHERE id=?", (bnb_order_id or order_id, topup["id"]))
        conn.commit()
        conn.close()
        topup["receipt"] = bnb_order_id or order_id
        await _credit_topup(context.bot, topup)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
    else:
        await query.message.reply_text(
            "⏳ Payment Not Yet Received.\n\n"
            "Please Make Sure:\n"
            "▪️ You Sent The Exact Amount In USDT\n"
            "▪️ You Included Your Telegram ID In The Note\n"
            "▪️ Wait A Few Minutes After Paying Before Checking\n\n"
            "Then Click 'Check Payment' Again."
        )


async def show_my_purchases(update, context):
    query = update.callback_query
    uid = query.from_user.id
    rows = db.get_user_purchases(uid)
    if not rows:
        return await safe_edit(query, "📭 You Have No Purchases Yet.")
    lines = ["🎁 *My Purchases*", "➖➖➖➖➖➖"]
    for r in rows[:20]:
        lines.append(f"• {r['category_name']} | {r['product_name']} | {fmt_money(r['price'])} | {r['purchased_at']}")
        if r.get("link"):
            lines.append(f"  📎 [Clickable]({r['link']})")
    await safe_edit(query, "\n".join(lines))


# ============== Find User ==============
async def show_user_profile_admin(update_or_query, context, user_row, via_message=False):
    import html
    u = user_row
    days = days_since(u["registration"]) if u.get("registration") else 0
    reg_date = u["registration"].split(" ")[0] if u.get("registration") else "—"
    name = u.get("first_name") or "—"
    uname = u.get("username") or ""
    user_id = u["user_id"]

    # Escape For HTML
    name_html = html.escape(name)
    uname_html = html.escape(uname) if uname else ""

    # Clickable Name Link (Opens User's Telegram Profile)
    name_link = f'<a href="tg://user?id={user_id}">{name_html}</a>'
    # Clickable Username Link
    uname_display = f'<a href="https://t.me/{uname_html}">@{uname_html}</a>' if uname else "—"

    text = (
        f"👤 <b>User Profile:</b> {name_link}\n"
        f"➖➖➖➖➖➖\n"
        f"▪️ ID: <code>{user_id}</code>\n"
        f"▪️ Username: {uname_display}\n"
        f"▪️ Name: {name_link}\n"
        f"▪️ Registration: {reg_date} ({days} Days)\n\n"
        f"▪️ Balance: {fmt_money(u['balance'])}\n"
        f"▪️ Total Funds Gives: {fmt_money(u['total_given'])}\n"
        f"▪️ Total Replenishment Of Funds: {fmt_money(u['total_topup'])}\n"
        f"▪️ Purchased Goods: {u['purchased']}pcs"
    )
    kb_mark = kb.user_profile_admin_inline(user_id)
    if via_message:
        await update_or_query.message.reply_text(
            text, reply_markup=kb_mark, parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    else:
        try:
            await update_or_query.edit_message_text(
                text, reply_markup=kb_mark, parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                log.warning(f"Edit Failed: {e}")


async def refresh_user_profile(update, context, target_id):
    u = db.get_user(target_id)
    if u:
        await show_user_profile_admin(update.callback_query, context, u)


async def show_user_purchases_admin(update, context, target_id):
    query = update.callback_query
    rows = db.get_user_purchases(target_id)
    if not rows:
        return await safe_edit(query, "📭 This User Has No Purchases.")
    lines = [f"🎁 *Purchases For User* `{target_id}`", "➖➖➖➖➖➖"]
    for r in rows[:30]:
        lines.append(
            f"• {r['category_name']} | {r['product_name']} | {fmt_money(r['price'])} | {r['purchased_at']}"
        )
    await safe_edit(query, "\n".join(lines))


# ============== Mailing ==============
async def do_mailing(update, context):
    query = update.callback_query
    uid = query.from_user.id
    state = get_state(uid)
    if not state or "msg_chat_id" not in state["data"]:
        return await safe_edit(query, "❌ No Message To Send.")

    src_chat = state["data"]["msg_chat_id"]
    src_msg = state["data"]["msg_id"]
    clear_state(uid)

    all_ids = db.get_all_user_ids()
    total = len(all_ids)
    progress_msg = await query.message.reply_text(f"📢 The Mailing Has Begun... (0/{total})")

    sent, failed = 0, 0
    start = time.time()
    for i, recipient in enumerate(all_ids, 1):
        try:
            await context.bot.copy_message(chat_id=recipient, from_chat_id=src_chat, message_id=src_msg)
            sent += 1
        except (Forbidden, BadRequest):
            failed += 1
        except Exception as e:
            log.warning(f"Mail Failed For {recipient}: {e}")
            failed += 1
        if i % config.BROADCAST_PROGRESS_STEP == 0:
            try:
                await progress_msg.edit_text(f"📢 The Mailing Has Begun... ({i}/{total})")
            except Exception:
                pass
        await asyncio.sleep(config.BROADCAST_DELAY)

    elapsed = int(time.time() - start)
    mins, secs = divmod(elapsed, 60)
    final = (
        "✅ *Mailing Completed!*\n"
        "➖➖➖➖➖➖\n"
        f"📬 Delivered: {sent} Users\n"
        f"❌ Failed: {failed} Users\n"
        f"🕒 Time Taken: {mins}m {secs}s"
    )
    await progress_msg.edit_text(final, parse_mode=ParseMode.MARKDOWN)


# ============== Payment Systems Admin ==============
async def show_payment_manage(update, context, name):
    ps = db.get_payment_system(name)
    if not ps:
        return
    emoji = {"CryptoBot": "🔷", "Cryptomus": "⬛", "Binance": "🔆"}.get(name, "💳")
    await safe_edit(
        update.callback_query,
        f"{emoji} *Manage - {name}*",
        reply_markup=kb.payment_manage_inline(name, ps["enabled"]),
    )


async def show_payment_info(update, context, name):
    ps = db.get_payment_system(name)
    if not ps:
        return
    api = ps["api_key"][:6] + "..." if ps["api_key"] else "Not Set"
    sec = ps["secret_key"][:6] + "..." if ps["secret_key"] else "Not Set"
    mer = ps["merchant_id"][:6] + "..." if ps["merchant_id"] else "Not Set"
    status = "On ✅" if ps["enabled"] else "Off ❌"
    text = (
        f"♻️ *{name} Information*\n"
        "➖➖➖➖➖➖\n"
        f"▪️ API Key: `{api}`\n"
        f"▪️ Secret Key: `{sec}`\n"
        f"▪️ Merchant ID: `{mer}`\n"
        f"▪️ Status: {status}"
    )
    await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def show_payment_balance(update, context, name):
    bal = await get_gateway_balance(name)
    msg = f"💰 *{name} Balance*\n\n{bal if bal else '❌ Unable To Fetch Balance'}"
    await update.callback_query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def start_payment_edit(update, context, name):
    uid = update.callback_query.from_user.id
    if name == "CryptoBot":
        set_state(uid, "ps_edit_token", ps=name)
        await safe_edit(
            update.callback_query,
            f"🔷 *Changing CryptoBot*\n➖➖➖➖➖➖\n▪️ Send Your API Token",
        )
    elif name == "Cryptomus":
        set_state(uid, "ps_edit_merchant", ps=name)
        await safe_edit(
            update.callback_query,
            f"⬛ *Changing Cryptomus Wallet*\n➖➖➖➖➖➖\n▪️ Send Your Merchant UUID",
        )
    elif name == "Binance":
        set_state(uid, "ps_edit_bnb_uid", ps=name)
        await safe_edit(
            update.callback_query,
            f"🔆 *Changing Binance*\n➖➖➖➖➖➖\n"
            f"▪️ Send Your Binance Pay UID\n"
            f"(Shown In Binance App → Pay → Your Pay ID, e.g., 358985073)",
        )


# ============== Settings ==============
async def show_settings_edit(update, context):
    s = {
        "faq_text": db.get_setting("faq_text"),
        "support_username": db.get_setting("support_username"),
        "discord_webhook": db.get_setting("discord_webhook"),
        "pastebin_api_key": db.get_setting("pastebin_api_key"),
        "hide_empty_categories": db.get_setting("hide_empty_categories"),
        "hide_empty_positions": db.get_setting("hide_empty_positions"),
    }
    await safe_edit(
        update.callback_query, "🖍️ *Changing Bot Data*",
        reply_markup=kb.settings_edit_inline(s),
    )


async def show_settings_switches(update, context):
    await safe_edit(
        update.callback_query,
        "🕹️ *Activating And Deactivating Basic Functions*",
        reply_markup=kb.settings_switches_inline(
            db.get_setting("maintenance"),
            db.get_setting("refills_on"),
            db.get_setting("purchases_on"),
        ),
    )


async def handle_edit_data(update, context, field):
    uid = update.callback_query.from_user.id
    query = update.callback_query
    if field == "faq":
        set_state(uid, "edit_faq")
        await safe_edit(query, "❓ Send The New FAQ Text:")
    elif field == "support":
        set_state(uid, "edit_support")
        await safe_edit(query, "☎️ Send The Support Username (Without @):")
    elif field == "discord":
        set_state(uid, "edit_discord")
        await safe_edit(query, "🔵 Send The Discord Webhook URL (Send '-' To Remove):")
    elif field == "pastebin":
        set_state(uid, "edit_pastebin")
        await safe_edit(
            query,
            "📋 Send Your Pastebin API Key\n"
            "(Free From https://pastebin.com/doc_api — Look For 'Your Unique Developer API Key')\n\n"
            "Send '-' To Remove (Bot Will Use Anonymous Paste)",
        )
    elif field == "cat_hide":
        current = db.get_setting("hide_empty_categories")
        db.set_setting("hide_empty_categories", "0" if current == "1" else "1")
        await show_settings_edit(update, context)
    elif field == "pos_hide":
        current = db.get_setting("hide_empty_positions")
        db.set_setting("hide_empty_positions", "0" if current == "1" else "1")
        await show_settings_edit(update, context)


async def toggle_switch(update, context, switch):
    if switch == "maint":
        current = db.get_setting("maintenance")
        db.set_setting("maintenance", "0" if current == "1" else "1")
    elif switch == "refill":
        current = db.get_setting("refills_on")
        db.set_setting("refills_on", "0" if current == "1" else "1")
    elif switch == "purch":
        current = db.get_setting("purchases_on")
        db.set_setting("purchases_on", "0" if current == "1" else "1")
    await show_settings_switches(update, context)


# ============== Manage Items ==============
async def handle_manage_items_action(update, context, action):
    query = update.callback_query
    uid = query.from_user.id
    if action == "create_cat":
        set_state(uid, "create_cat_name")
        return await safe_edit(query, "🗃️ *Enter A Name For The Category*")
    if action == "create_pos":
        cats = db.get_categories()
        if not cats:
            return await safe_edit(query, "❌ Create A Category First.")
        return await safe_edit(
            query, "📁 *Select A Category For The Position*",
            reply_markup=kb.categories_list_inline(cats, "pick_cat_for_pos"),
        )
    if action == "edit_cat":
        cats = db.get_categories()
        if not cats:
            return await safe_edit(query, "❌ No Categories.")
        return await safe_edit(
            query, "🗃️ *Select A Category To Edit*",
            reply_markup=kb.categories_list_inline(cats, "pick_cat_to_edit"),
        )
    if action == "edit_pos":
        cats = db.get_categories()
        if not cats:
            return await safe_edit(query, "❌ No Categories.")
        return await safe_edit(
            query, "📁 *Select A Category*",
            reply_markup=kb.categories_list_inline(cats, "pick_cat_pos"),
        )
    if action == "add_items":
        cats = db.get_categories()
        if not cats:
            return await safe_edit(query, "❌ Create A Category First.")
        return await safe_edit(
            query, "🎁 *Select A Category*",
            reply_markup=kb.categories_list_inline(cats, "pick_cat_pos"),
        )
    if action == "destroyer":
        return await safe_edit(
            query, "❌ *Destroyer*\n\nThis Will Delete All Categories, Positions And Stock!\n\nAre You Sure?",
            reply_markup=kb.yes_no_inline("destroyer_yes", "destroyer_no"),
        )


async def show_edit_position(update, context, pid):
    pos = db.get_position(pid)
    if not pos:
        return await safe_edit(update.callback_query, "❌ Position Not Found.")
    cat = db.get_category(pos["category_id"])
    cat_name = cat["name"] if cat else "—"
    stock = db.position_stock_count(pid)
    photo = "Present ✅" if pos.get("photo") else "Absent ❌"
    desc = pos.get("description") or "Absent ❌"
    from database import get_position_sales
    sales = get_position_sales(pid)

    text = (
        f"📁 *Edit Position*\n"
        "➖➖➖➖➖➖\n"
        f"▪️ Category Name: {cat_name}\n"
        f"▪️ Position Name: {pos['name']}\n"
        f"▪️ Price: {fmt_money(pos['price'])}\n"
        f"▪️ Quantity: {stock}pcs\n"
        f"▪️ Photo: {photo}\n"
        f"▪️ Date Of Creation: {pos.get('created_at', '—')}\n"
        f"▪️ Desc: {desc}\n\n"
        f"🎊 Sales Per Day: {sales['day'][0]}pcs - {fmt_money(sales['day'][1])}\n"
        f"🎊 Sales Per Week: {sales['week'][0]}pcs - {fmt_money(sales['week'][1])}\n"
        f"🎊 Sales Per Month: {sales['month'][0]}pcs - {fmt_money(sales['month'][1])}\n"
        f"🎊 Sales For All Time: {sales['all'][0]}pcs - {fmt_money(sales['all'][1])}"
    )
    await safe_edit(update.callback_query, text, reply_markup=kb.edit_position_inline(pid))


async def show_edit_category(update, context, cid):
    cat = db.get_category(cid)
    if not cat:
        return await safe_edit(update.callback_query, "❌ Category Not Found.")
    positions = db.get_positions(cid)
    qty_pos = len(positions)
    qty_goods = sum(db.position_stock_count(p["id"]) for p in positions)
    from database import get_category_sales
    sales = get_category_sales(cid)
    photo_status = "Present ✅" if cat.get("photo") else "Absent ❌"
    text = (
        f"🗃️ *Edit Category*\n"
        "➖➖➖➖➖➖\n"
        f"▪️ Category Name: {cat['name']}\n"
        f"▪️ Photo: {photo_status}\n"
        f"▪️ Quantity Positions: {qty_pos}pcs\n"
        f"▪️ Quantity Goods: {qty_goods}pcs\n"
        f"▪️ Date Of Creation: {cat.get('created_at', '—')}\n\n"
        f"🎊 Sales Per Day: {sales['day'][0]}pcs - {fmt_money(sales['day'][1])}\n"
        f"🎊 Sales Per Week: {sales['week'][0]}pcs - {fmt_money(sales['week'][1])}\n"
        f"🎊 Sales Per Month: {sales['month'][0]}pcs - {fmt_money(sales['month'][1])}\n"
        f"🎊 Sales For All Time: {sales['all'][0]}pcs - {fmt_money(sales['all'][1])}"
    )
    await safe_edit(update.callback_query, text, reply_markup=kb.edit_category_inline(cid))


async def handle_edit_position_action(update, context, action, pid):
    query = update.callback_query
    uid = query.from_user.id
    if action == "refresh":
        return await show_edit_position(update, context, pid)
    if action == "name":
        set_state(uid, "ep_edit_name", pid=pid)
        return await safe_edit(query, "📝 Send The New Name:")
    if action == "price":
        set_state(uid, "ep_edit_price", pid=pid)
        return await safe_edit(query, "💵 Send The New Price:")
    if action == "desc":
        set_state(uid, "ep_edit_desc", pid=pid)
        return await safe_edit(query, "📝 Send The New Description:")
    if action == "photo":
        set_state(uid, "ep_edit_photo", pid=pid)
        return await safe_edit(query, "📷 Send The New Photo:")
    if action == "add":
        set_state(uid, "ep_add_stock", pid=pid, added=0)
        finish_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Finish Loading", callback_data=f"ep:finish_load:{pid}")]
        ])
        return await safe_edit(
            query,
            "🎁 *Submit Product Data*\n"
            "❗ Products Are Separated By A Single Blank Line. Example:\n"
            "Goods Data...\n\n"
            "Product Data...\n\n"
            "Product Data...",
            reply_markup=finish_kb,
        )
    if action == "finish_load":
        state = get_state(uid)
        added = state["data"].get("added", 0) if state else 0
        clear_state(uid)
        await query.answer(f"✅ Finished. {added} Items Added.", show_alert=True)
        return await show_edit_position(update, context, pid)
    if action == "show":
        return await show_position_stock(update, context, pid)
    if action == "clear":
        return await safe_edit(
            query, "🧹 Clear All Stock For This Position?",
            reply_markup=kb.yes_no_inline(f"ep_clear_yes:{pid}", f"ep:refresh:{pid}"),
        )
    if action == "clear_yes":
        db.clear_stock(pid)
        return await show_edit_position(update, context, pid)
    if action == "delete_items":
        items = db.get_stock_items(pid)
        if not items:
            return await safe_edit(query, "📭 No Items To Delete.")
        return await safe_edit(
            query, "🎁 *Select An Item To Remove*",
            reply_markup=kb.stock_items_inline(items, pid),
        )
    if action == "link":
        bot_username = context.bot.username
        link = f"https://t.me/{bot_username}?start=p_{pid}"
        return await query.message.reply_text(f"📋 Copy Link:\n`{link}`", parse_mode=ParseMode.MARKDOWN)
    if action == "delete":
        return await safe_edit(
            query, "🗑️ Delete This Position?",
            reply_markup=kb.yes_no_inline(f"ep_del_yes:{pid}", f"ep:refresh:{pid}"),
        )
    if action == "del_yes":
        db.delete_position(pid)
        return await safe_edit(query, "✅ Position Deleted.")


async def show_position_stock(update, context, pid):
    query = update.callback_query
    pos = db.get_position(pid)
    items = db.get_stock_items(pid)
    if not items:
        return await safe_edit(query, "📭 No Products In Stock.")
    data_text = "\n".join(i["data"] for i in items)
    link = await host_text(f"{pos['name']} — Stock", data_text) or ""
    preview = " | ".join(i["data"][:30] for i in items[:3])
    text = (
        f"🎁 *All Products Of The Position:* {pos['name']}\n"
        f"➖➖➖➖➖➖\n"
        f"| {preview} ...\n\n"
        f"📎 Link: [Clickable]({link})"
    )
    await query.message.reply_text(
        text, reply_markup=kb.close_inline(),
        parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True,
    )


async def handle_edit_category_action(update, context, action, cid):
    query = update.callback_query
    uid = query.from_user.id
    if action == "refresh":
        return await show_edit_category(update, context, cid)
    if action == "name":
        set_state(uid, "ec_edit_name", cid=cid)
        return await safe_edit(query, "📝 Send The New Category Name:")
    if action == "photo":
        set_state(uid, "ec_edit_photo", cid=cid)
        return await safe_edit(query, "📷 Send The New Category Photo (As An Image):")
    if action == "addpos":
        set_state(uid, "create_pos_name", category_id=cid)
        return await safe_edit(query, "📁 *Enter A Name For The Position*")
    if action == "link":
        bot_username = context.bot.username
        link = f"https://t.me/{bot_username}?start=c_{cid}"
        return await query.message.reply_text(f"📋 Copy Link:\n`{link}`", parse_mode=ParseMode.MARKDOWN)
    if action == "delete":
        return await safe_edit(
            query, "🗑️ Delete This Category (And All Its Positions)?",
            reply_markup=kb.yes_no_inline(f"ec_del_yes:{cid}", f"ec:refresh:{cid}"),
        )
    if action == "del_yes":
        db.delete_category(cid)
        return await safe_edit(query, "✅ Category Deleted.")


# Handle Nested Yes/No Callbacks That Don't Match The Pattern Above
async def extra_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Dynamic Confirm Callbacks Like ep_clear_yes, ep_del_yes, ec_del_yes"""
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    uid = query.from_user.id
    if not is_admin(uid):
        return
    if data.startswith("ep_clear_yes:"):
        pid = int(data.split(":")[1])
        db.clear_stock(pid)
        return await show_edit_position(update, context, pid)
    if data.startswith("ep_del_yes:"):
        pid = int(data.split(":")[1])
        db.delete_position(pid)
        return await safe_edit(query, "✅ Position Deleted.")
    if data.startswith("ec_del_yes:"):
        cid = int(data.split(":")[1])
        db.delete_category(cid)
        return await safe_edit(query, "✅ Category Deleted.")
