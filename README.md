# Telegram Shop Bot

A Full-Featured Telegram Shop Bot With Admin Panel, Payment Integrations (Cryptomus, CryptoBot, Binance Pay), Statistics, Mailing, Product Management And More.

All Wording Is In **Title Case** (First Letter Of Every Word Capital).
Users See Only User Buttons — Admin Panel Is Hidden From Regular Users.

---

## Features

### User Side
- **🎁 Buy** — Browse Categories & Products, Purchase With Balance
- **👤 Profile** — View Balance, Purchase History, Top-Up
- **🧮 Availability Of Goods** — See All Categories & Stock Counts
- **☎️ Support** — Contact Admin Button
- **❓ FAQ** — Store Rules

### Admin Side (Hidden From Users)
- **🎁 Manage Items** — Create/Edit Categories & Positions, Add Stock (Text Or .txt File)
- **📊 Statistics** — Users, Sales, Top-Ups, Payment Gateways Breakdown
- **⚙️ Settings** — Edit FAQ, Support Username, Discord Webhook, Text Hosting, Toggles
- **🔆 General Functions** — Find Users, Mass Mailing With Progress Bar
- **🔑 Payment Systems** — Manage Cryptomus/CryptoBot/Binance API Keys From Mobile

### Extra
- **Deep Links** (`?start=p_123` / `?start=c_45`) — Share Any Category Or Position As A Link
- **Auto Daily Report** — DB File + Statistics Sent To Admin Every Night At 2 AM
- **Text Hosting** — Product Data Uploaded To Pastie.Org / Telegra.Ph (Clickable Links)
- **Discord Webhook** — Optional Mirror Of Purchases & Top-Ups To A Discord Channel
- **Maintenance Mode** — Disable Store For Users With One Click

---

## Installation

### 1. Install Python 3.10+
### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure `config.py`
```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"        # From @BotFather
ADMIN_IDS = [YOUR_TELEGRAM_ID]           # From @userinfobot
WEBHOOK_BASE_URL = "https://yourdomain.com"   # Your DigitalOcean Server URL
WEBHOOK_PORT = 8080                      # Port For Payment Webhooks
```

### 4. Run The Bot
```bash
python main.py
```

---

## Setup On DigitalOcean Amsterdam Server

### 1. Point A Domain Or Use Your Droplet IP
Ensure Port `8080` Is Open In The Firewall:
```bash
ufw allow 8080
```

### 2. Use A Reverse Proxy With HTTPS (Recommended)
Install Nginx And Certbot:
```bash
apt install nginx certbot python3-certbot-nginx
```

Add Nginx Config:
```nginx
server {
    server_name yourdomain.com;

    location /cryptomus_webhook { proxy_pass http://127.0.0.1:8080; }
    location /cryptobot_webhook { proxy_pass http://127.0.0.1:8080; }
    location /binance_webhook   { proxy_pass http://127.0.0.1:8080; }
}
```

Enable HTTPS:
```bash
certbot --nginx -d yourdomain.com
```

### 3. Run With Systemd
Create `/etc/systemd/system/shopbot.service`:
```ini
[Unit]
Description=Telegram Shop Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/telegram_shop_bot
ExecStart=/usr/bin/python3 /root/telegram_shop_bot/main.py
Restart=always

[Install]
WantedBy=multi-user.target
```
Enable:
```bash
systemctl enable shopbot
systemctl start shopbot
```

---

## Adding Payment Gateways (From Mobile)

1. Open The Bot In Telegram As Admin
2. Tap **🔑 Payment Systems**
3. Pick A Gateway (CryptoBot / Cryptomus / Binance)
4. Tap **Edit 🖍️**
5. Send The Requested API Key / Merchant UUID / Secret Key
6. Tap The Status Button To Turn It On ✅

**Webhook URLs To Set In Each Gateway Dashboard:**
- Cryptomus: `https://yourdomain.com/cryptomus_webhook`
- CryptoBot: `https://yourdomain.com/cryptobot_webhook`
- Binance Pay: `https://yourdomain.com/binance_webhook`

---

## Managing Products (From Mobile)

1. Tap **🎁 Manage Items**
2. Tap **🗃️ Create Category ➕** → Type Name
3. Tap **📁 Create Position ➕** → Pick Category → Type Name → Type Price
4. In The Created Position Tap **Add Products** → Send Product Data:
   - **Text Message**: One Product Per Line (Multiple Items In One Message)
   - **.txt File**: Upload A Text File, Each Line = One Stock Item

---

## File Structure
```
telegram_shop_bot/
├── main.py              # Entry Point
├── config.py            # Bot Token, Admin IDs, Settings
├── database.py          # SQLite Operations
├── bot.py               # /start, Core User Flows
├── handlers.py          # Inline Callback Handlers
├── message_handlers.py  # Text/Media Message Router
├── admin_ext.py         # Statistics, DB Send, Webhooks, Scheduler
├── keyboards.py         # All Reply + Inline Keyboards
├── payments.py          # Cryptomus, CryptoBot, Binance Integrations
├── utils.py             # Helpers (Receipts, Pastie, Discord, Formatting)
├── requirements.txt
├── shop.db              # Auto-Generated SQLite Database
└── bot.log              # Auto-Generated Log File
```
