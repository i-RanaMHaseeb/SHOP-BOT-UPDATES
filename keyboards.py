"""
Keyboards Module
All Reply Keyboards And Inline Keyboards
Title Case Wording Used Everywhere
"""

from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN_IDS


# ============== Button Labels (Title Case) ==============
# User Buttons
BTN_BUY              = "🎁 Buy"
BTN_PROFILE          = "👤 Profile"
BTN_AVAILABILITY     = "🧮 Availability Of Goods"
BTN_SUPPORT          = "☎️ Support"
BTN_FAQ              = "❓ FAQ"

# Admin-Only Buttons
BTN_MANAGE_ITEMS     = "🎁 Manage Items"
BTN_STATISTICS       = "📊 Statistics"
BTN_SETTINGS         = "⚙️ Settings"
BTN_GENERAL_FUNCS    = "🔆 General Functions"
BTN_PAYMENT_SYSTEMS  = "🔑 Payment Systems"


def is_admin(user_id):
    return user_id in ADMIN_IDS


# ============== Main Menu ==============
def main_menu_keyboard(user_id):
    """
    User Sees Only User Buttons
    Admin Sees All Buttons (User + Admin)
    """
    if is_admin(user_id):
        keyboard = [
            [KeyboardButton(BTN_BUY), KeyboardButton(BTN_PROFILE), KeyboardButton(BTN_AVAILABILITY)],
            [KeyboardButton(BTN_SUPPORT), KeyboardButton(BTN_FAQ)],
            [KeyboardButton(BTN_MANAGE_ITEMS), KeyboardButton(BTN_STATISTICS)],
            [KeyboardButton(BTN_SETTINGS), KeyboardButton(BTN_GENERAL_FUNCS), KeyboardButton(BTN_PAYMENT_SYSTEMS)],
        ]
    else:
        keyboard = [
            [KeyboardButton(BTN_BUY), KeyboardButton(BTN_PROFILE), KeyboardButton(BTN_AVAILABILITY)],
            [KeyboardButton(BTN_SUPPORT), KeyboardButton(BTN_FAQ)],
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)


# ============== Profile Inline ==============
def profile_inline():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 Top-Up", callback_data="topup"),
            InlineKeyboardButton("🎁 My Purchases", callback_data="my_purchases"),
        ]
    ])


# ============== Support Inline ==============
def support_inline(support_username):
    url = f"https://t.me/{support_username.lstrip('@')}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💌 Write To Support", url=url)]
    ])


# ============== Top-Up Gateway Selection ==============
def topup_gateways_inline(gateways):
    rows, row = [], []
    for g in gateways:
        row.append(InlineKeyboardButton(f"{_gateway_emoji(g)} {g}", callback_data=f"pay_gateway:{g}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def _gateway_emoji(name):
    return {"CryptoBot": "🔷", "Cryptomus": "⬛", "Binance": "🔆"}.get(name, "💳")


# ============== Payment Systems (Admin) ==============
def payment_systems_main_inline():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔷 CryptoBot", callback_data="ps:CryptoBot"),
            InlineKeyboardButton("⬛ Cryptomus", callback_data="ps:Cryptomus"),
            InlineKeyboardButton("🔆 Binance", callback_data="ps:Binance"),
        ],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="back_main")],
    ])


def payment_manage_inline(name, status):
    status_text = "Status: On ✅" if status else "Status: Off ❌"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Information ♻️", callback_data=f"ps_info:{name}")],
        [InlineKeyboardButton("Balance 💰", callback_data=f"ps_balance:{name}")],
        [InlineKeyboardButton("Edit 🖍️", callback_data=f"ps_edit:{name}")],
        [InlineKeyboardButton(f"➕ | {status_text}", callback_data=f"ps_toggle:{name}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="ps_back")],
    ])


# ============== General Functions (Admin) ==============
def general_functions_inline():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 Find", callback_data="gf_find"),
            InlineKeyboardButton("📢 Mail", callback_data="gf_mail"),
        ],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="back_main")],
    ])


def user_profile_admin_inline(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 Set Balance", callback_data=f"u_setbal:{user_id}"),
            InlineKeyboardButton("💰 Add Balance", callback_data=f"u_addbal:{user_id}"),
            InlineKeyboardButton("➖ Cut Balance", callback_data=f"u_cutbal:{user_id}"),
        ],
        [
            InlineKeyboardButton("🎁 Purchases", callback_data=f"u_purchases:{user_id}"),
            InlineKeyboardButton("💌 Send SMS", callback_data=f"u_sms:{user_id}"),
            InlineKeyboardButton("🚫 Remove User", callback_data=f"u_remove:{user_id}"),
        ],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"u_refresh:{user_id}")],
    ])


def mail_confirm_inline():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Send", callback_data="mail_send"),
            InlineKeyboardButton("❌ Cancel", callback_data="mail_cancel"),
        ]
    ])


# ============== Settings (Admin) ==============
def settings_main_inline():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🖍️ Edit Data", callback_data="settings_edit"),
            InlineKeyboardButton("🕹️ Switches", callback_data="settings_switches"),
        ],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="back_main")],
    ])


def settings_edit_inline(s):
    """
    s Is A Dict Of All Settings Values
    """
    faq_val = "⚠️ Store Rules ... ✅" if s.get("faq_text") else "Not Set ❌"
    support_val = f"@{s.get('support_username', '').lstrip('@')} ✅" if s.get("support_username") else "Not Set ❌"
    discord_val = "Established ✅" if s.get("discord_webhook") else "Not Established ❌"
    pastebin_val = "Set ✅" if s.get("pastebin_api_key") else "Not Set (Anonymous) ⚠️"
    cat_hide = "Hide" if s.get("hide_empty_categories") == "1" else "Show"
    pos_hide = "Hide" if s.get("hide_empty_positions") == "1" else "Show"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("❓ FAQ", callback_data="ed:faq"),
            InlineKeyboardButton(faq_val, callback_data="ed:faq"),
        ],
        [
            InlineKeyboardButton("☎️ Support", callback_data="ed:support"),
            InlineKeyboardButton(support_val, callback_data="ed:support"),
        ],
        [
            InlineKeyboardButton("🔵 Discord Webhook ↗", callback_data="ed:discord"),
            InlineKeyboardButton(discord_val, callback_data="ed:discord"),
        ],
        [
            InlineKeyboardButton("📋 Pastebin API Key", callback_data="ed:pastebin"),
            InlineKeyboardButton(pastebin_val, callback_data="ed:pastebin"),
        ],
        [
            InlineKeyboardButton("🎁 Categories Without Stock", callback_data="ed:cat_hide"),
            InlineKeyboardButton(cat_hide, callback_data="ed:cat_hide"),
        ],
        [
            InlineKeyboardButton("🎁 Positions Without Items", callback_data="ed:pos_hide"),
            InlineKeyboardButton(pos_hide, callback_data="ed:pos_hide"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="settings_back")],
    ])


def settings_switches_inline(maintenance, refills, purchases):
    m = "Off ❌" if maintenance == "0" else "On ✅"
    r = "On ✅" if refills == "1" else "Off ❌"
    p = "On ✅" if purchases == "1" else "Off ❌"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⛔ Maintenance", callback_data="sw:maint"),
            InlineKeyboardButton(m, callback_data="sw:maint"),
        ],
        [
            InlineKeyboardButton("💰 Refills", callback_data="sw:refill"),
            InlineKeyboardButton(r, callback_data="sw:refill"),
        ],
        [
            InlineKeyboardButton("🎁 Purchases", callback_data="sw:purch"),
            InlineKeyboardButton(p, callback_data="sw:purch"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="settings_back")],
    ])


# ============== Manage Items (Admin) ==============
def manage_items_inline():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📁 Create Position ➕", callback_data="mi:create_pos"),
            InlineKeyboardButton("🗃️ Create Category ➕", callback_data="mi:create_cat"),
        ],
        [
            InlineKeyboardButton("📁 Edit Position 🖍️", callback_data="mi:edit_pos"),
            InlineKeyboardButton("🗃️ Edit Category 🖍️", callback_data="mi:edit_cat"),
        ],
        [
            InlineKeyboardButton("⬅️ Main Menu", callback_data="back_main"),
            InlineKeyboardButton("🎁 Add Items ➕", callback_data="mi:add_items"),
            InlineKeyboardButton("❌ Destroyer", callback_data="mi:destroyer"),
        ],
    ])


def categories_list_inline(categories, action_prefix, add_back=True):
    """
    Generic List Of Categories As Inline Buttons
    Action_Prefix Example: 'pick_cat_for_pos', 'edit_cat', 'pick_cat_for_addstock'
    """
    rows = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(cat["name"], callback_data=f"{action_prefix}:{cat['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if add_back:
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="mi_back")])
    return InlineKeyboardMarkup(rows)


def positions_list_inline(positions, action_prefix, add_back=True):
    rows = []
    row = []
    for pos in positions:
        row.append(InlineKeyboardButton(pos["name"], callback_data=f"{action_prefix}:{pos['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if add_back:
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="mi_back")])
    return InlineKeyboardMarkup(rows)


def edit_position_inline(pid):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▪️ Edit Name", callback_data=f"ep:name:{pid}"),
            InlineKeyboardButton("▪️ Edit Price", callback_data=f"ep:price:{pid}"),
        ],
        [
            InlineKeyboardButton("▪️ Edit Desc", callback_data=f"ep:desc:{pid}"),
            InlineKeyboardButton("▪️ Edit Photo", callback_data=f"ep:photo:{pid}"),
        ],
        [
            InlineKeyboardButton("▪️ Add Products", callback_data=f"ep:add:{pid}"),
            InlineKeyboardButton("▪️ Show Products", callback_data=f"ep:show:{pid}"),
        ],
        [
            InlineKeyboardButton("▪️ Clear Products", callback_data=f"ep:clear:{pid}"),
            InlineKeyboardButton("▪️ Delete Products", callback_data=f"ep:delete_items:{pid}"),
        ],
        [
            InlineKeyboardButton("📋 Copy Link", callback_data=f"ep:link:{pid}"),
            InlineKeyboardButton("▪️ Delete Position", callback_data=f"ep:delete:{pid}"),
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data="mi_back"),
            InlineKeyboardButton("▪️ Refresh", callback_data=f"ep:refresh:{pid}"),
        ],
    ])


def edit_category_inline(cid):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▪️ Edit Name", callback_data=f"ec:name:{cid}"),
            InlineKeyboardButton("▪️ Edit Photo", callback_data=f"ec:photo:{cid}"),
        ],
        [
            InlineKeyboardButton("▪️ Add Position", callback_data=f"ec:addpos:{cid}"),
            InlineKeyboardButton("📋 Copy Link", callback_data=f"ec:link:{cid}"),
        ],
        [
            InlineKeyboardButton("▪️ Delete", callback_data=f"ec:delete:{cid}"),
            InlineKeyboardButton("▪️ Refresh", callback_data=f"ec:refresh:{cid}"),
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data="mi_back"),
        ],
    ])


def yes_no_inline(yes_cb, no_cb):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes", callback_data=yes_cb),
            InlineKeyboardButton("❌ No", callback_data=no_cb),
        ]
    ])


def close_inline(cb="close_msg"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Close", callback_data=cb)]])


def stock_items_inline(items, pid):
    """Shows Stock Items As Buttons (For Delete Products)"""
    rows = []
    for item in items:
        preview = item["data"][:25] + "..." if len(item["data"]) > 25 else item["data"]
        rows.append([InlineKeyboardButton(f"🗑️ {preview}", callback_data=f"del_stock:{item['id']}:{pid}")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data=f"ep:refresh:{pid}")])
    return InlineKeyboardMarkup(rows)


# ============== Buy Flow (User) ==============
def buy_categories_inline(categories):
    rows = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(cat["name"], callback_data=f"buy_cat:{cat['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def buy_positions_inline(positions):
    rows = []
    for pos in positions:
        rows.append([InlineKeyboardButton(pos["name"], callback_data=f"buy_pos:{pos['id']}")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="buy_back_cats")])
    return InlineKeyboardMarkup(rows)


def buy_position_inline(pid, stock_count):
    rows = []
    if stock_count > 0:
        rows.append([InlineKeyboardButton("🛒 Buy Now", callback_data=f"buy_now:{pid}")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data=f"buy_pos_back:{pid}")])
    return InlineKeyboardMarkup(rows)


def buy_qty_inline(pid, stock_count, max_row=5):
    """Quantity Selector: 1, 2, 3, ... Up To Stock Count"""
    rows = []
    row = []
    # Cap At 10 Per Purchase For UI Simplicity (Can Still Buy More In Batches)
    cap = min(stock_count, 10)
    for i in range(1, cap + 1):
        row.append(InlineKeyboardButton(str(i), callback_data=f"buy_qty:{pid}:{i}"))
        if len(row) == max_row:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    # If Stock > 10, Add A "Custom Amount" Option
    if stock_count > 10:
        rows.append([InlineKeyboardButton("🔢 Custom Amount", callback_data=f"buy_qty_custom:{pid}")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data=f"buy_pos:{pid}")])
    return InlineKeyboardMarkup(rows)
