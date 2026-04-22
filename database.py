"""
Database Module
Handles All SQLite Operations For The Shop Bot
"""

import sqlite3
import os
from datetime import datetime, timedelta
from config import DB_FILE


def get_connection():
    """Returns A New Database Connection"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Creates All Tables If They Do Not Exist"""
    conn = get_connection()
    c = conn.cursor()

    # Users Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY,
            username      TEXT,
            first_name    TEXT,
            balance       REAL DEFAULT 0,
            total_given   REAL DEFAULT 0,
            total_topup   REAL DEFAULT 0,
            purchased     INTEGER DEFAULT 0,
            registration  TEXT,
            banned        INTEGER DEFAULT 0
        )
    """)

    # Categories Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            photo       TEXT,
            created_at  TEXT
        )
    """)
    # Safe Migration: Add Photo Column If Missing (For Older DBs)
    try:
        c.execute("ALTER TABLE categories ADD COLUMN photo TEXT")
    except sqlite3.OperationalError:
        pass  # Column Already Exists

    # Positions Table (Products)
    c.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id  INTEGER,
            name         TEXT NOT NULL,
            description  TEXT,
            price        REAL NOT NULL,
            photo        TEXT,
            created_at   TEXT,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
        )
    """)

    # Stock Items (Product Data That Users Receive After Purchase)
    c.execute("""
        CREATE TABLE IF NOT EXISTS stock (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER,
            data        TEXT NOT NULL,
            sold        INTEGER DEFAULT 0,
            created_at  TEXT,
            FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE
        )
    """)

    # Purchases Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER,
            position_id  INTEGER,
            category_id  INTEGER,
            product_name TEXT,
            category_name TEXT,
            qty          INTEGER,
            price        REAL,
            receipt      TEXT,
            data         TEXT,
            link         TEXT,
            purchased_at TEXT
        )
    """)

    # Top-Ups Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS topups (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            amount     REAL,
            gateway    TEXT,
            coin       TEXT,
            receipt    TEXT,
            status     TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)

    # Settings Table (Key-Value Config)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Payment Systems Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS payment_systems (
            name        TEXT PRIMARY KEY,
            api_key     TEXT,
            secret_key  TEXT,
            merchant_id TEXT,
            enabled     INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    _seed_defaults(conn)
    conn.close()


def _seed_defaults(conn):
    """Seeds Default Settings And Payment Systems On First Run"""
    c = conn.cursor()

    default_settings = {
        "faq_text": "⚠️ *Store Rules – Read Before Buying!* ⚠️\n\n▪️ All Sales Are Final\n▪️ Check Products Before Buying\n▪️ Contact Support For Any Issue",
        "support_username": "RanaMHaseeb",
        "discord_webhook": "",
        "pastebin_api_key": "",
        "text_hosting": "pastie",
        "hide_empty_categories": "1",
        "hide_empty_positions": "1",
        "maintenance": "0",
        "refills_on": "1",
        "purchases_on": "1",
    }
    for k, v in default_settings.items():
        c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))

    default_gateways = ["CryptoBot", "Cryptomus", "Binance"]
    for g in default_gateways:
        c.execute(
            "INSERT OR IGNORE INTO payment_systems(name, api_key, secret_key, merchant_id, enabled) VALUES (?, '', '', '', 0)",
            (g,),
        )

    conn.commit()


# ---------- Settings Helpers ----------
def get_setting(key, default=""):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


# ---------- User Helpers ----------
def register_user(user_id, username, first_name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not c.fetchone():
        c.execute(
            "INSERT INTO users(user_id, username, first_name, registration) VALUES (?, ?, ?, ?)",
            (user_id, username or "", first_name or "", datetime.now().strftime("%d.%m.%Y %H:%M:%S")),
        )
        conn.commit()
    else:
        c.execute(
            "UPDATE users SET username=?, first_name=? WHERE user_id=?",
            (username or "", first_name or "", user_id),
        )
        conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def find_user(query):
    """Find User By ID, Username (With Or Without @), Name, Or Receipt"""
    conn = get_connection()
    c = conn.cursor()
    raw = query.strip()
    # Clean Prefixes
    clean = raw.lstrip("@").lstrip("#").strip()

    # Try User ID (Numeric)
    if clean.isdigit():
        c.execute("SELECT * FROM users WHERE user_id=?", (int(clean),))
        row = c.fetchone()
        if row:
            conn.close()
            return dict(row)

    # Try Exact Username (Case-Insensitive)
    c.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)", (clean,))
    row = c.fetchone()
    if row:
        conn.close()
        return dict(row)

    # Try Partial Username Match
    c.execute("SELECT * FROM users WHERE LOWER(username) LIKE LOWER(?)", (f"%{clean}%",))
    row = c.fetchone()
    if row:
        conn.close()
        return dict(row)

    # Try First Name Match (Exact Or Partial)
    c.execute("SELECT * FROM users WHERE LOWER(first_name)=LOWER(?)", (clean,))
    row = c.fetchone()
    if row:
        conn.close()
        return dict(row)

    c.execute("SELECT * FROM users WHERE LOWER(first_name) LIKE LOWER(?)", (f"%{clean}%",))
    row = c.fetchone()
    if row:
        conn.close()
        return dict(row)

    # Try Receipt — With Or Without # Prefix
    receipts_to_try = [raw, clean, f"#{clean}"]
    for r_try in receipts_to_try:
        c.execute("SELECT user_id FROM purchases WHERE receipt=?", (r_try,))
        row = c.fetchone()
        if row:
            c.execute("SELECT * FROM users WHERE user_id=?", (row["user_id"],))
            r = c.fetchone()
            conn.close()
            return dict(r) if r else None

        c.execute("SELECT user_id FROM topups WHERE receipt=?", (r_try,))
        row = c.fetchone()
        if row:
            c.execute("SELECT * FROM users WHERE user_id=?", (row["user_id"],))
            r = c.fetchone()
            conn.close()
            return dict(r) if r else None

    conn.close()
    return None


def update_balance(user_id, new_balance):
    conn = get_connection()
    conn.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user_id))
    conn.commit()
    conn.close()


def add_balance(user_id, amount, from_admin=False):
    conn = get_connection()
    if from_admin:
        conn.execute(
            "UPDATE users SET balance=balance+?, total_given=total_given+? WHERE user_id=?",
            (amount, amount, user_id),
        )
    else:
        conn.execute(
            "UPDATE users SET balance=balance+?, total_topup=total_topup+? WHERE user_id=?",
            (amount, amount, user_id),
        )
    conn.commit()
    conn.close()


def cut_balance(user_id, amount):
    conn = get_connection()
    conn.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()


def ban_user(user_id):
    conn = get_connection()
    conn.execute("UPDATE users SET banned=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def get_all_user_ids():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE banned=0")
    ids = [r["user_id"] for r in c.fetchall()]
    conn.close()
    return ids


def get_user_count():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM users WHERE banned=0")
    cnt = c.fetchone()["cnt"]
    conn.close()
    return cnt


# ---------- Category Helpers ----------
def create_category(name):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO categories(name, created_at) VALUES (?, ?)",
        (name, datetime.now().strftime("%d.%m.%Y %H:%M:%S")),
    )
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return cid


def get_categories(hide_empty=False):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM categories ORDER BY name")
    cats = [dict(r) for r in c.fetchall()]
    if hide_empty:
        cats = [x for x in cats if _category_stock(conn, x["id"]) > 0]
    conn.close()
    return cats


def _category_stock(conn, category_id):
    c = conn.cursor()
    c.execute(
        """SELECT COUNT(*) as cnt FROM stock s
           JOIN positions p ON p.id = s.position_id
           WHERE p.category_id=? AND s.sold=0""",
        (category_id,),
    )
    return c.fetchone()["cnt"]


def get_category(cid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM categories WHERE id=?", (cid,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def update_category(cid, name=None, **fields):
    """Updates Category Fields. Accepts `name` Positionally Or Any Field As Keyword."""
    if name is not None:
        fields["name"] = name
    if not fields:
        return
    cols = ", ".join([f"{k}=?" for k in fields])
    vals = list(fields.values()) + [cid]
    conn = get_connection()
    conn.execute(f"UPDATE categories SET {cols} WHERE id=?", vals)
    conn.commit()
    conn.close()


def delete_category(cid):
    conn = get_connection()
    conn.execute("DELETE FROM categories WHERE id=?", (cid,))
    conn.commit()
    conn.close()


# ---------- Position Helpers ----------
def create_position(category_id, name, price):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO positions(category_id, name, price, created_at) VALUES (?, ?, ?, ?)",
        (category_id, name, price, datetime.now().strftime("%d.%m.%Y %H:%M:%S")),
    )
    pid = c.lastrowid
    conn.commit()
    conn.close()
    return pid


def get_positions(category_id=None, hide_empty=False):
    conn = get_connection()
    c = conn.cursor()
    if category_id:
        c.execute("SELECT * FROM positions WHERE category_id=? ORDER BY name", (category_id,))
    else:
        c.execute("SELECT * FROM positions ORDER BY name")
    rows = [dict(r) for r in c.fetchall()]
    if hide_empty:
        rows = [x for x in rows if position_stock_count(x["id"]) > 0]
    conn.close()
    return rows


def get_position(pid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM positions WHERE id=?", (pid,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def update_position(pid, **fields):
    if not fields:
        return
    cols = ", ".join([f"{k}=?" for k in fields])
    vals = list(fields.values()) + [pid]
    conn = get_connection()
    conn.execute(f"UPDATE positions SET {cols} WHERE id=?", vals)
    conn.commit()
    conn.close()


def delete_position(pid):
    conn = get_connection()
    conn.execute("DELETE FROM positions WHERE id=?", (pid,))
    conn.commit()
    conn.close()


# ---------- Stock Helpers ----------
def add_stock(position_id, lines):
    """Adds Product Data Lines To Position Stock"""
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()
    for line in lines:
        line = line.strip()
        if line:
            c.execute(
                "INSERT INTO stock(position_id, data, created_at) VALUES (?, ?, ?)",
                (position_id, line, now),
            )
    conn.commit()
    conn.close()


def position_stock_count(position_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) as cnt FROM stock WHERE position_id=? AND sold=0",
        (position_id,),
    )
    cnt = c.fetchone()["cnt"]
    conn.close()
    return cnt


def get_stock_items(position_id, only_unsold=True):
    conn = get_connection()
    c = conn.cursor()
    if only_unsold:
        c.execute(
            "SELECT * FROM stock WHERE position_id=? AND sold=0 ORDER BY id",
            (position_id,),
        )
    else:
        c.execute("SELECT * FROM stock WHERE position_id=? ORDER BY id", (position_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def delete_stock_item(stock_id):
    conn = get_connection()
    conn.execute("DELETE FROM stock WHERE id=?", (stock_id,))
    conn.commit()
    conn.close()


def clear_stock(position_id):
    conn = get_connection()
    conn.execute("DELETE FROM stock WHERE position_id=?", (position_id,))
    conn.commit()
    conn.close()


def reserve_stock(position_id, qty):
    """Reserves And Returns N Stock Items (Marking Them As Sold)"""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM stock WHERE position_id=? AND sold=0 ORDER BY id LIMIT ?",
        (position_id, qty),
    )
    rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        c.execute("UPDATE stock SET sold=1 WHERE id=?", (r["id"],))
    conn.commit()
    conn.close()
    return rows


# ---------- Purchase / Topup Helpers ----------
def record_purchase(user_id, position_id, category_id, product_name, category_name,
                    qty, price, receipt, data, link):
    conn = get_connection()
    conn.execute(
        """INSERT INTO purchases(user_id, position_id, category_id, product_name, category_name,
           qty, price, receipt, data, link, purchased_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, position_id, category_id, product_name, category_name, qty, price,
         receipt, data, link, datetime.now().strftime("%d.%m.%Y %H:%M:%S")),
    )
    conn.execute(
        "UPDATE users SET purchased=purchased+?, balance=balance-? WHERE user_id=?",
        (qty, price, user_id),
    )
    conn.commit()
    conn.close()


def record_topup(user_id, amount, gateway, coin, receipt, status="completed"):
    conn = get_connection()
    conn.execute(
        """INSERT INTO topups(user_id, amount, gateway, coin, receipt, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, amount, gateway, coin, receipt, status, datetime.now().strftime("%d.%m.%Y %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def get_user_purchases(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM purchases WHERE user_id=? ORDER BY id DESC", (user_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ---------- Statistics Helpers ----------
def _count_between(conn, table, col_amount, col_qty, since):
    c = conn.cursor()
    q = f"SELECT COUNT(*) as cnt, COALESCE(SUM({col_amount}), 0) as total"
    if col_qty:
        q = f"SELECT COALESCE(SUM({col_qty}), 0) as cnt, COALESCE(SUM({col_amount}), 0) as total"
    q += f" FROM {table} WHERE "
    q += "purchased_at >= ?" if table == "purchases" else "created_at >= ?"
    c.execute(q, (since,))
    r = c.fetchone()
    return r["cnt"], r["total"]


def get_statistics():
    now = datetime.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%d.%m.%Y %H:%M:%S")
    week_start = (now - timedelta(days=7)).strftime("%d.%m.%Y %H:%M:%S")
    month_start = (now - timedelta(days=30)).strftime("%d.%m.%Y %H:%M:%S")

    conn = get_connection()
    c = conn.cursor()

    # Users (Using Registration Field — Simple String Compare Works Because Format Is Consistent)
    c.execute("SELECT COUNT(*) as cnt FROM users")
    users_all = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM users WHERE registration >= ?", (day_start,))
    users_day = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM users WHERE registration >= ?", (week_start,))
    users_week = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM users WHERE registration >= ?", (month_start,))
    users_month = c.fetchone()["cnt"]

    # Sales
    s_day = _count_between(conn, "purchases", "price", "qty", day_start)
    s_week = _count_between(conn, "purchases", "price", "qty", week_start)
    s_month = _count_between(conn, "purchases", "price", "qty", month_start)
    c.execute("SELECT COALESCE(SUM(qty),0) as cnt, COALESCE(SUM(price),0) as total FROM purchases")
    r = c.fetchone()
    s_all = (r["cnt"], r["total"])

    # Top-Ups
    t_day = _count_between(conn, "topups", "amount", None, day_start)
    t_week = _count_between(conn, "topups", "amount", None, week_start)
    t_month = _count_between(conn, "topups", "amount", None, month_start)
    c.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(amount),0) as total FROM topups WHERE status='completed'")
    r = c.fetchone()
    t_all = (r["cnt"], r["total"])

    # Payment Systems Breakdown
    c.execute(
        """SELECT gateway, COUNT(*) as cnt, COALESCE(SUM(amount),0) as total
           FROM topups WHERE status='completed' GROUP BY gateway"""
    )
    gateways = {r["gateway"]: (r["cnt"], r["total"]) for r in c.fetchall()}

    # Totals
    c.execute("SELECT COALESCE(SUM(total_given),0) as g, COALESCE(SUM(balance),0) as b FROM users")
    r = c.fetchone()
    total_given = r["g"]
    total_balance = r["b"]

    # Products
    c.execute("SELECT COUNT(*) as cnt FROM stock WHERE sold=0")
    items = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM positions")
    positions = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM categories")
    categories = c.fetchone()["cnt"]

    conn.close()
    return {
        "users": {"day": users_day, "week": users_week, "month": users_month, "all": users_all},
        "sales": {"day": s_day, "week": s_week, "month": s_month, "all": s_all},
        "topups": {"day": t_day, "week": t_week, "month": t_month, "all": t_all},
        "gateways": gateways,
        "total_given": total_given,
        "total_in_system": total_balance,
        "items": items,
        "positions": positions,
        "categories": categories,
    }


def get_position_sales(position_id):
    now = datetime.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%d.%m.%Y %H:%M:%S")
    week_start = (now - timedelta(days=7)).strftime("%d.%m.%Y %H:%M:%S")
    month_start = (now - timedelta(days=30)).strftime("%d.%m.%Y %H:%M:%S")

    conn = get_connection()
    c = conn.cursor()

    def q(since=None):
        if since:
            c.execute(
                "SELECT COALESCE(SUM(qty),0) as cnt, COALESCE(SUM(price),0) as total FROM purchases WHERE position_id=? AND purchased_at >= ?",
                (position_id, since),
            )
        else:
            c.execute(
                "SELECT COALESCE(SUM(qty),0) as cnt, COALESCE(SUM(price),0) as total FROM purchases WHERE position_id=?",
                (position_id,),
            )
        r = c.fetchone()
        return r["cnt"], r["total"]

    out = {"day": q(day_start), "week": q(week_start), "month": q(month_start), "all": q()}
    conn.close()
    return out


def get_category_sales(category_id):
    now = datetime.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%d.%m.%Y %H:%M:%S")
    week_start = (now - timedelta(days=7)).strftime("%d.%m.%Y %H:%M:%S")
    month_start = (now - timedelta(days=30)).strftime("%d.%m.%Y %H:%M:%S")

    conn = get_connection()
    c = conn.cursor()

    def q(since=None):
        if since:
            c.execute(
                "SELECT COALESCE(SUM(qty),0) as cnt, COALESCE(SUM(price),0) as total FROM purchases WHERE category_id=? AND purchased_at >= ?",
                (category_id, since),
            )
        else:
            c.execute(
                "SELECT COALESCE(SUM(qty),0) as cnt, COALESCE(SUM(price),0) as total FROM purchases WHERE category_id=?",
                (category_id,),
            )
        r = c.fetchone()
        return r["cnt"], r["total"]

    out = {"day": q(day_start), "week": q(week_start), "month": q(month_start), "all": q()}
    conn.close()
    return out


# ---------- Payment Systems ----------
def get_payment_system(name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM payment_systems WHERE name=?", (name,))
    r = c.fetchone()
    conn.close()
    return dict(r) if r else None


def get_all_payment_systems():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM payment_systems")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def update_payment_system(name, **fields):
    if not fields:
        return
    cols = ", ".join([f"{k}=?" for k in fields])
    vals = list(fields.values()) + [name]
    conn = get_connection()
    conn.execute(f"UPDATE payment_systems SET {cols} WHERE name=?", vals)
    conn.commit()
    conn.close()


def toggle_payment_system(name):
    ps = get_payment_system(name)
    if ps:
        new = 0 if ps["enabled"] else 1
        update_payment_system(name, enabled=new)
        return new
    return 0


# ---------- Destroyer ----------
def destroy_all():
    """Deletes All Categories, Positions And Stock"""
    conn = get_connection()
    conn.execute("DELETE FROM stock")
    conn.execute("DELETE FROM positions")
    conn.execute("DELETE FROM categories")
    conn.commit()
    conn.close()
