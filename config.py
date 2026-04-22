"""
Configuration File
Edit These Values Before Running The Bot
"""

# ============== Bot Configuration ==============
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"   # Get From @BotFather

# Admin Telegram User IDs (Get Your ID From @userinfobot)
ADMIN_IDS = [123456789]             # Add All Admin IDs Here

# Database File Name
DB_FILE = "shop.db"

# Log File
LOG_FILE = "bot.log"

# ============== Scheduler ==============
# Daily Database + Statistics Send Time (24-Hour Format)
# 2:00 AM Night As You Requested
DAILY_REPORT_HOUR = 2
DAILY_REPORT_MINUTE = 0

# ============== Payment Polling ==============
# Cryptomus + CryptoBot Are Verified By Polling Their APIs Every 30 Seconds
# Binance Is Verified Manually Via Pay ID + User ID In Note
# No Domain / Webhook / HTTPS Needed

# ============== Text Hosting ==============
# Used For "Clickable" Links When Showing Product Data
# Options: "telegraph" Or "pastie"
DEFAULT_TEXT_HOSTING = "pastie"

# ============== Mailing ==============
# Delay Between Broadcast Messages (Seconds) To Avoid Telegram Rate Limit
BROADCAST_DELAY = 0.05
# Edit Progress Message Every N Users
BROADCAST_PROGRESS_STEP = 20
