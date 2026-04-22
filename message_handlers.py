"""
Message Handlers
Processes All Non-Command Messages Based On User State
Handles Text Inputs For Admin Flows (Edit Data, Create Category, Add Stock, Etc.)
"""

import logging
import os
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import config
import database as db
import keyboards as kb
from keyboards import (
    BTN_BUY, BTN_PROFILE, BTN_AVAILABILITY, BTN_SUPPORT, BTN_FAQ,
    BTN_MANAGE_ITEMS, BTN_STATISTICS, BTN_SETTINGS, BTN_GENERAL_FUNCS, BTN_PAYMENT_SYSTEMS,
    is_admin,
)
from utils import generate_receipt, now_str, host_text, send_discord, fmt_money
from payments import create_payment_url
from bot import STATE, set_state, get_state, clear_state

log = logging.getLogger(__name__)


async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main Text/Media Message Router"""
    msg = update.message
    if not msg:
        return
    user = update.effective_user
    uid = user.id
    text = (msg.text or "").strip()

    # Register Every User We See
    db.register_user(uid, user.username, user.first_name)

    # Check Banned
    u = db.get_user(uid)
    if u and u.get("banned"):
        return

    # ============== Menu Button Override ==============
    # If User Clicks A Reply Keyboard Button, Always Cancel Any Pending State
    # This Prevents Bugs Where User Gets Stuck In "Invalid Quantity" Etc.
    MENU_BUTTONS = {
        BTN_BUY, BTN_PROFILE, BTN_AVAILABILITY, BTN_SUPPORT, BTN_FAQ,
        BTN_MANAGE_ITEMS, BTN_STATISTICS, BTN_SETTINGS, BTN_GENERAL_FUNCS, BTN_PAYMENT_SYSTEMS,
    }
    if text in MENU_BUTTONS:
        # Clear Any Previous State — User Is Switching Action
        clear_state(uid)

    # ============== State-Based Handling ==============
    state = get_state(uid)
    if state:
        action = state["action"]
        data = state["data"]

        # ---------- Find User ----------
        if action == "find_user":
            clear_state(uid)
            try:
                u = db.find_user(text)
            except Exception as e:
                log.error(f"Find User Error: {e}")
                return await msg.reply_text(f"❌ Error Searching: {e}")

            if not u:
                return await msg.reply_text(
                    "❌ <b>User Not Joined Yet</b>\n\n"
                    "This User Has Not Started The Bot Yet.\n\n"
                    "Make Sure:\n"
                    "▪️ The User Has Used The Bot At Least Once (Sent /start)\n"
                    "▪️ You Entered The Correct ID, Username, Name Or Receipt\n"
                    "▪️ Try Without @ Prefix For Usernames",
                    parse_mode=ParseMode.HTML,
                )
            try:
                from handlers import show_user_profile_admin
                await show_user_profile_admin(update, context, u, via_message=True)
            except Exception as e:
                log.error(f"Show Profile Error: {e}")
                await msg.reply_text(f"❌ Error Showing Profile: {e}")
            return

        # ---------- Mailing ----------
        if action == "mail_wait_content":
            user_count = db.get_user_count()
            set_state(uid, "mail_confirm", msg_chat_id=msg.chat_id, msg_id=msg.message_id)
            await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat_id, message_id=msg.message_id)
            await msg.reply_text(
                f"📢 *Send This Post To {user_count} Users?*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb.mail_confirm_inline(),
            )
            return

        # ---------- User Balance / SMS ----------
        if action == "user_set_balance":
            try:
                amt = float(text)
            except ValueError:
                return await msg.reply_text("❌ Invalid Amount.")
            target = data["target"]
            target_user = db.get_user(target)
            if not target_user:
                clear_state(uid)
                return await msg.reply_text("❌ User Not Found.")
            old_balance = float(target_user.get("balance", 0))
            db.update_balance(target, amt)
            clear_state(uid)

            import html as _html
            # User's Name Link (Shown To Admin)
            target_name = _html.escape(target_user.get("first_name") or "—")
            target_link = f'<a href="tg://user?id={target}">{target_name}</a>'
            # Admin's Name Link (Shown To User)
            admin_name = _html.escape(user.first_name or "Admin")
            admin_link = f'<a href="tg://user?id={uid}">{admin_name}</a>'

            # Admin Sees User's Name
            admin_msg = (
                f"👤 User: {target_link}\n"
                f"💰 Balance Set: {fmt_money(amt)} | {fmt_money(old_balance)} -> {fmt_money(amt)}"
            )
            # User Sees Admin's Name
            user_msg = (
                f"👤 Admin: {admin_link}\n"
                f"💰 Balance Set: {fmt_money(amt)} | {fmt_money(old_balance)} -> {fmt_money(amt)}"
            )
            await msg.reply_text(admin_msg, parse_mode=ParseMode.HTML)
            try:
                await context.bot.send_message(target, user_msg, parse_mode=ParseMode.HTML)
            except Exception:
                pass
            try:
                from handlers import show_user_profile_admin
                refreshed = db.get_user(target)
                if refreshed:
                    await show_user_profile_admin(update, context, refreshed, via_message=True)
            except Exception:
                pass
            return

        if action == "user_add_balance":
            try:
                amt = float(text)
            except ValueError:
                return await msg.reply_text("❌ Invalid Amount.")
            target = data["target"]
            target_user = db.get_user(target)
            if not target_user:
                clear_state(uid)
                return await msg.reply_text("❌ User Not Found.")
            old_balance = float(target_user.get("balance", 0))
            db.add_balance(target, amt, from_admin=True)
            clear_state(uid)
            new_balance = old_balance + amt

            import html as _html
            target_name = _html.escape(target_user.get("first_name") or "—")
            target_link = f'<a href="tg://user?id={target}">{target_name}</a>'
            admin_name = _html.escape(user.first_name or "Admin")
            admin_link = f'<a href="tg://user?id={uid}">{admin_name}</a>'

            admin_msg = (
                f"👤 User: {target_link}\n"
                f"💰 Balance Add: {fmt_money(amt)} | {fmt_money(old_balance)} -> {fmt_money(new_balance)}"
            )
            user_msg = (
                f"👤 Admin: {admin_link}\n"
                f"💰 Balance Add: {fmt_money(amt)} | {fmt_money(old_balance)} -> {fmt_money(new_balance)}"
            )
            await msg.reply_text(admin_msg, parse_mode=ParseMode.HTML)
            try:
                await context.bot.send_message(target, user_msg, parse_mode=ParseMode.HTML)
            except Exception:
                pass
            try:
                from handlers import show_user_profile_admin
                refreshed = db.get_user(target)
                if refreshed:
                    await show_user_profile_admin(update, context, refreshed, via_message=True)
            except Exception:
                pass
            return

        if action == "user_cut_balance":
            try:
                amt = float(text)
            except ValueError:
                return await msg.reply_text("❌ Invalid Amount.")
            target = data["target"]
            target_user = db.get_user(target)
            if not target_user:
                clear_state(uid)
                return await msg.reply_text("❌ User Not Found.")
            old_balance = float(target_user.get("balance", 0))
            db.cut_balance(target, amt)
            clear_state(uid)
            new_balance = old_balance - amt

            import html as _html
            target_name = _html.escape(target_user.get("first_name") or "—")
            target_link = f'<a href="tg://user?id={target}">{target_name}</a>'
            admin_name = _html.escape(user.first_name or "Admin")
            admin_link = f'<a href="tg://user?id={uid}">{admin_name}</a>'

            admin_msg = (
                f"👤 User: {target_link}\n"
                f"💰 Balance Cut: {fmt_money(amt)} | {fmt_money(old_balance)} -> {fmt_money(new_balance)}"
            )
            user_msg = (
                f"👤 Admin: {admin_link}\n"
                f"💰 Balance Cut: {fmt_money(amt)} | {fmt_money(old_balance)} -> {fmt_money(new_balance)}"
            )
            await msg.reply_text(admin_msg, parse_mode=ParseMode.HTML)
            try:
                await context.bot.send_message(target, user_msg, parse_mode=ParseMode.HTML)
            except Exception:
                pass
            try:
                from handlers import show_user_profile_admin
                refreshed = db.get_user(target)
                if refreshed:
                    await show_user_profile_admin(update, context, refreshed, via_message=True)
            except Exception:
                pass
            return

        if action == "user_sms":
            target = data["target"]
            clear_state(uid)
            try:
                await context.bot.send_message(target, f"💌 <b>Message From Admin:</b>\n\n{text}", parse_mode=ParseMode.HTML)
                await msg.reply_text("✅ Message Sent.")
            except Exception as e:
                await msg.reply_text(f"❌ Failed: {e}")
            return

        # ---------- Custom Quantity For Buy ----------
        if action == "buy_custom_qty":
            try:
                qty = int(text)
                if qty <= 0:
                    raise ValueError()
            except ValueError:
                return await msg.reply_text("❌ Invalid Quantity. Enter A Positive Number.")
            pid = data["pid"]
            pos = db.get_position(pid)
            if not pos:
                clear_state(uid)
                return await msg.reply_text("❌ Position Not Found.")
            stock = db.position_stock_count(pid)
            if qty > stock:
                return await msg.reply_text(f"❌ Only {stock} Pcs Available. Try A Smaller Number.")
            target_user = db.get_user(uid)
            total_price = pos["price"] * qty
            if target_user["balance"] < total_price:
                need = total_price - target_user["balance"]
                clear_state(uid)
                return await msg.reply_text(
                    f"❌ Insufficient Balance.\n\nTotal Cost: {fmt_money(total_price)}\n"
                    f"Your Balance: {fmt_money(target_user['balance'])}\n"
                    f"You Need {fmt_money(need)} More. Please Top-Up."
                )
            clear_state(uid)

            # Execute Purchase (Same Logic As buy_execute But Via Message)
            items = db.reserve_stock(pid, qty)
            if not items or len(items) < qty:
                return await msg.reply_text("📭 Not Enough Stock.")

            cat = db.get_category(pos["category_id"])
            cat_name = cat["name"] if cat else "—"
            data_text = "\n".join(i["data"] for i in items)
            from utils import generate_receipt as _genrec, host_text as _host, now_str as _now, send_discord as _disc
            receipt = _genrec()
            link = await _host(f"{pos['name']} — Purchase", data_text) or ""

            db.record_purchase(
                uid, pid, pos["category_id"], pos["name"], cat_name,
                qty, total_price, receipt, data_text, link,
            )

            import html as _html
            username = user.username or "—"
            name = _html.escape(user.first_name or "—")
            link_html = f'<a href="{link}">Clickable</a>' if link else "❌ No Link"

            # Step A: Send Product Data Directly To Buyer As Numbered List
            numbered_lines = []
            for idx, item in enumerate(items, start=1):
                numbered_lines.append(f"{idx}. {_html.escape(item['data'])}")
            numbered_text = "\n".join(numbered_lines)

            if len(numbered_text) > 3800:
                numbered_text = numbered_text[:3800] + "\n\n[Truncated — See Full Data Via Link]"

            buyer_data_msg = (
                f"🎁 <b>{_html.escape(pos['name'])}</b>\n"
                f"➖➖➖➖➖➖\n\n"
                f"{numbered_text}"
            )
            await msg.reply_text(buyer_data_msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

            # Step B: Send Purchase Receipt To Buyer
            buyer_receipt = (
                "✅ <b>You Have Successfully Purchased The Item(s)</b>\n"
                "➖➖➖➖➖➖\n"
                f"▪️ Receipt: <code>{receipt}</code>\n"
                f"▪️ Product: {cat_name} | {pos['name']} | {qty}pcs | {fmt_money(total_price)}\n"
                f"▪️ Products Data: {link_html}\n"
                f"▪️ Date Of Purchase: {_now()}"
            )
            await msg.reply_text(buyer_receipt, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

            # Step C: Send Admin Notification
            admin_text = (
                "🎁 <b>New Purchase</b>\n"
                "➖➖➖➖➖➖\n"
                f"▪️ User: @{username} | {name} | <code>{uid}</code>\n"
                f"▪️ Receipt: <code>{receipt}</code>\n"
                f"▪️ Product: {cat_name} | {pos['name']} | {qty}pcs | {fmt_money(total_price)}\n"
                f"▪️ Products Data: {link_html}\n"
                f"▪️ Date Of Purchase: {_now()}"
            )
            import config as _cfg
            for admin_id in _cfg.ADMIN_IDS:
                try:
                    await context.bot.send_message(admin_id, admin_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                except Exception:
                    pass
            await _disc(
                f"🎁 New Purchase\nUser: @{username} | {uid}\n"
                f"Receipt: {receipt}\nProduct: {cat_name} | {pos['name']} | {qty}pcs | {fmt_money(total_price)}\n"
                f"Link: {link}\nDate: {_now()}"
            )
            return

        # ---------- Top-Up Amount ----------
        if action == "topup_amount":
            try:
                amount = float(text)
                if amount <= 0:
                    raise ValueError()
            except ValueError:
                return await msg.reply_text("❌ Invalid Amount.")
            gateway = data["gateway"]
            order_id = f"topup_{uid}_{int(__import__('time').time())}"
            clear_state(uid)
            url, err = await create_payment_url(gateway, uid, amount, order_id)
            if err:
                return await msg.reply_text(f"❌ {err}")

            db.record_topup(uid, amount, gateway, "USDT", order_id, status="pending")

            # Special Handling For Binance Manual Payment
            if url and url.startswith("MANUAL_BINANCE|"):
                _, pay_id, user_id_str, amt_str = url.split("|")
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                check_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Check Payment", callback_data=f"bnb_check:{order_id}")]
                ])
                text_out = (
                    "💰 <b>Top-Up: Binance</b>\n"
                    "➖➖➖➖➖➖\n"
                    f"▪️ Binance Pay ID: <code>{pay_id}</code>\n"
                    f"▪️ Transfer Amount: {fmt_money(amount)}\n"
                    f"▪️ In Note: <code>{user_id_str}</code>\n\n"
                    "‼️ <b>IMPORTANT</b>\n"
                    "▪️ Please Transfer This Exact Amount To The Following Binance Pay ID.\n"
                    "▪️ You <b>MUST</b> Include Your Telegram User ID In The <b>Note</b> (Memo/Note) Field During The Transfer.\n"
                    "➖➖➖➖➖➖\n"
                    "❗ After Payment, Click On Check Payment"
                )
                return await msg.reply_text(
                    text_out, reply_markup=check_kb, parse_mode=ParseMode.HTML,
                )

            # Normal Flow For Cryptomus / CryptoBot
            await msg.reply_text(
                f"💰 <b>Pay {fmt_money(amount)} Via {gateway}</b>\n\n"
                f'<a href="{url}">Click Here To Pay</a>\n\n'
                "After Payment Your Balance Will Be Updated Automatically.",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return

        # ---------- Payment System Edit ----------
        if action == "ps_edit_token":
            db.update_payment_system("CryptoBot", api_key=text)
            clear_state(uid)
            return await msg.reply_text("✅ CryptoBot Token Updated.")
        if action == "ps_edit_merchant":
            set_state(uid, "ps_edit_cryptomus_api", merchant=text)
            return await msg.reply_text("▪️ Now Send Your Cryptomus API Key:")
        if action == "ps_edit_cryptomus_api":
            db.update_payment_system("Cryptomus", merchant_id=data["merchant"], api_key=text)
            clear_state(uid)
            return await msg.reply_text("✅ Cryptomus Credentials Updated.")
        if action == "ps_edit_bnb_uid":
            if not text.isdigit():
                return await msg.reply_text("❌ UID Must Be A Number. Try Again:")
            set_state(uid, "ps_edit_bnb_api", pay_uid=text)
            return await msg.reply_text(
                "▪️ Now Send Your Binance API Key\n"
                "(Create In Binance → API Management → Create API)\n\n"
                "Send '-' To Skip (Then Admin Must Manually Verify Payments)"
            )
        if action == "ps_edit_bnb_api":
            if text == "-":
                db.update_payment_system("Binance", merchant_id=data["pay_uid"], api_key="", secret_key="")
                clear_state(uid)
                return await msg.reply_text(
                    "✅ Binance Pay UID Set.\n\n"
                    "⚠️ Without API Keys, Payments Can't Be Auto-Verified.\n"
                    "Admin Will Receive A Notification When User Clicks Check Payment."
                )
            set_state(uid, "ps_edit_bnb_secret", pay_uid=data["pay_uid"], api=text)
            return await msg.reply_text("▪️ Now Send Your Binance API Secret Key:")
        if action == "ps_edit_bnb_secret":
            # Verify Keys By Calling Binance Account API
            from payments import Binance
            ok, result = await Binance.verify_keys(data["api"], text)
            if not ok:
                clear_state(uid)
                return await msg.reply_text(
                    f"❌ Binance Keys Verification Failed:\n<code>{result}</code>\n\n"
                    f"Check Your API Key And Secret, Then Try Again.",
                    parse_mode=ParseMode.HTML,
                )
            db.update_payment_system("Binance", merchant_id=data["pay_uid"], api_key=data["api"], secret_key=text)
            clear_state(uid)
            return await msg.reply_text(
                f"✅ <b>Binance Wallet Is Fully Functional</b>\n"
                f"➖➖➖➖➖➖\n"
                f"▪️ Binance UID: <code>{data['pay_uid']}</code>\n"
                f"▪️ Account UID: <code>{result}</code>\n"
                f"▪️ API Key: <code>{data['api'][:8]}...</code>\n"
                f"▪️ Secret: <code>{text[:8]}...</code>\n\n"
                f"Payments Will Auto-Verify When User Clicks Check Payment.",
                parse_mode=ParseMode.HTML,
            )

        # ---------- Settings Edit ----------
        if action == "edit_faq":
            db.set_setting("faq_text", msg.text_html or text)
            clear_state(uid)
            return await msg.reply_text("✅ FAQ Updated.")
        if action == "edit_support":
            db.set_setting("support_username", text.lstrip("@"))
            clear_state(uid)
            return await msg.reply_text(f"✅ Support Username Set To @{text.lstrip('@')}")
        if action == "edit_discord":
            val = "" if text == "-" else text
            db.set_setting("discord_webhook", val)
            clear_state(uid)
            return await msg.reply_text("✅ Discord Webhook Updated.")
        if action == "edit_pastebin":
            val = "" if text == "-" else text.strip()
            db.set_setting("pastebin_api_key", val)
            clear_state(uid)
            if val:
                return await msg.reply_text("✅ Pastebin API Key Set. Product Data Links Will Now Use Pastebin.com.")
            return await msg.reply_text("✅ Pastebin API Key Removed. Bot Will Use Anonymous Paste.")

        # ---------- Manage Items Flows ----------
        if action == "create_cat_name":
            cid = db.create_category(text)
            clear_state(uid)
            await msg.reply_text(f"✅ Category *{text}* Created.", parse_mode=ParseMode.MARKDOWN)
            # Auto-Open Edit Category
            from handlers import show_edit_category
            # Create A Fake Query-Like Object To Reuse Logic
            fake = type("F", (), {"callback_query": type("Q", (), {"message": msg, "edit_message_text": msg.reply_text})()})
            # Simpler: Just Send A New Edit Category Display
            cat = db.get_category(cid)
            positions = db.get_positions(cid)
            text_out = (
                f"🗃️ *Edit Category*\n➖➖➖➖➖➖\n"
                f"▪️ Category Name: {cat['name']}\n"
                f"▪️ Quantity Positions: 0pcs\n"
                f"▪️ Quantity Goods: 0pcs\n"
                f"▪️ Date Of Creation: {cat['created_at']}\n\n"
                f"🎊 Sales Per Day: 0pcs - 0$\n"
                f"🎊 Sales Per Week: 0pcs - 0$\n"
                f"🎊 Sales Per Month: 0pcs - 0$\n"
                f"🎊 Sales For All Time: 0pcs - 0$"
            )
            await msg.reply_text(text_out, reply_markup=kb.edit_category_inline(cid), parse_mode=ParseMode.MARKDOWN)
            return

        if action == "create_pos_name":
            set_state(uid, "create_pos_price", category_id=data["category_id"], pos_name=text)
            return await msg.reply_text("📁 *Enter The Price For The Position*", parse_mode=ParseMode.MARKDOWN)

        if action == "create_pos_price":
            try:
                price = float(text)
            except ValueError:
                return await msg.reply_text("❌ Invalid Price.")
            pid = db.create_position(data["category_id"], data["pos_name"], price)
            clear_state(uid)
            # Show Edit Position
            pos = db.get_position(pid)
            cat = db.get_category(pos["category_id"])
            text_out = (
                f"📁 *Edit Position*\n➖➖➖➖➖➖\n"
                f"▪️ Category Name: {cat['name']}\n"
                f"▪️ Position Name: {pos['name']}\n"
                f"▪️ Price: {fmt_money(pos['price'])}\n"
                f"▪️ Quantity: 0pcs\n"
                f"▪️ Photo: Absent ❌\n"
                f"▪️ Date Of Creation: {pos['created_at']}\n"
                f"▪️ Desc: Absent ❌\n\n"
                f"🎊 Sales Per Day: 0pcs - 0$\n"
                f"🎊 Sales Per Week: 0pcs - 0$\n"
                f"🎊 Sales Per Month: 0pcs - 0$\n"
                f"🎊 Sales For All Time: 0pcs - 0$"
            )
            await msg.reply_text(text_out, reply_markup=kb.edit_position_inline(pid), parse_mode=ParseMode.MARKDOWN)
            return

        if action == "ep_edit_name":
            db.update_position(data["pid"], name=text)
            clear_state(uid)
            return await msg.reply_text("✅ Name Updated.")
        if action == "ep_edit_price":
            try:
                price = float(text)
            except ValueError:
                return await msg.reply_text("❌ Invalid Price.")
            db.update_position(data["pid"], price=price)
            clear_state(uid)
            return await msg.reply_text("✅ Price Updated.")
        if action == "ep_edit_desc":
            db.update_position(data["pid"], description=text)
            clear_state(uid)
            return await msg.reply_text("✅ Description Updated.")
        if action == "ep_edit_photo":
            if msg.photo:
                file_id = msg.photo[-1].file_id
                db.update_position(data["pid"], photo=file_id)
                clear_state(uid)
                return await msg.reply_text("✅ Photo Updated.")
            return await msg.reply_text("❌ Send A Photo (Not Text).")
        if action == "ep_add_stock":
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            pid = data["pid"]
            products = []
            raw_content = ""

            # Handle .txt File
            if msg.document:
                doc = msg.document
                f = await doc.get_file()
                path = f"/tmp/{doc.file_name}"
                await f.download_to_drive(path)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fp:
                        raw_content = fp.read()
                except Exception as e:
                    return await msg.reply_text(f"❌ Could Not Read File: {e}")
                try:
                    os.remove(path)
                except Exception:
                    pass
            elif text:
                raw_content = text

            if not raw_content.strip():
                return await msg.reply_text("❌ Send Text Or A .txt File.")

            # Split Products By Blank Line (One Blank Line = New Product)
            # Each Product Can Span Multiple Lines (All Lines Between Blank Lines = 1 Product)
            import re
            # Normalize Line Endings
            normalized = raw_content.replace("\r\n", "\n").replace("\r", "\n")
            # Split By Blank Line(s)
            blocks = re.split(r"\n\s*\n", normalized.strip())
            for block in blocks:
                block = block.strip()
                if block:
                    products.append(block)

            if not products:
                return await msg.reply_text("❌ No Valid Products Found.")

            db.add_stock(pid, products)

            # Keep State Alive — Allow More Uploads
            current_total = data.get("added", 0) + len(products)
            set_state(uid, "ep_add_stock", pid=pid, added=current_total)

            finish_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Finish Loading", callback_data=f"ep:finish_load:{pid}")]
            ])
            await msg.reply_text(
                f"✅ Added {len(products)} Item(s). Total Added This Session: {current_total}\n"
                "📦 Send More Products Or Tap *✅ Finish Loading* When Done.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=finish_kb,
            )
            return

        if action == "ec_edit_name":
            db.update_category(data["cid"], text)
            clear_state(uid)
            return await msg.reply_text("✅ Category Name Updated.")

        if action == "ec_edit_photo":
            if not msg.photo:
                return await msg.reply_text("❌ Please Send An Image (Not Text).")
            file_id = msg.photo[-1].file_id
            db.update_category(data["cid"], photo=file_id)
            clear_state(uid)
            return await msg.reply_text("✅ Category Photo Updated.")

    # ============== Reply Keyboard Buttons ==============
    if text == BTN_BUY:
        from bot import show_buy
        return await show_buy(update, context)
    if text == BTN_PROFILE:
        from bot import show_profile
        return await show_profile(update, context)
    if text == BTN_AVAILABILITY:
        from bot import show_availability
        return await show_availability(update, context)
    if text == BTN_SUPPORT:
        from bot import show_support
        return await show_support(update, context)
    if text == BTN_FAQ:
        from bot import show_faq
        return await show_faq(update, context)

    # ============== Admin-Only Buttons ==============
    if is_admin(uid):
        if text == BTN_MANAGE_ITEMS:
            return await msg.reply_text("🎁 *Manage Items*", reply_markup=kb.manage_items_inline(), parse_mode=ParseMode.MARKDOWN)
        if text == BTN_STATISTICS:
            from admin_ext import send_statistics
            return await send_statistics(context.bot, uid)
        if text == BTN_SETTINGS:
            return await msg.reply_text("⚙️ *General Settings*", reply_markup=kb.settings_main_inline(), parse_mode=ParseMode.MARKDOWN)
        if text == BTN_GENERAL_FUNCS:
            return await msg.reply_text("🔆 *General Functions*", reply_markup=kb.general_functions_inline(), parse_mode=ParseMode.MARKDOWN)
        if text == BTN_PAYMENT_SYSTEMS:
            return await msg.reply_text("🔑 *Payment Systems Management*", reply_markup=kb.payment_systems_main_inline(), parse_mode=ParseMode.MARKDOWN)
