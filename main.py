"""
Main Entry Point
Starts The Telegram Bot, The Scheduler (Daily DB + Stats), And The Payment Polling Loop.
No Domain / Webhook Server Required.
"""

import logging
import asyncio
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
import database as db
from bot import start, set_bot_commands
from handlers import callback_handler, extra_callback_handler
from message_handlers import message_router
from admin_ext import send_statistics, send_database, send_logs, daily_report_job
from keyboards import is_admin

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler(config.LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)


# ============== Admin Commands ==============
async def cmd_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from bot import show_support
    await show_support(update, context)


async def cmd_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from bot import show_faq
    await show_faq(update, context)


async def cmd_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    await send_database(context.bot, uid)


async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    await send_logs(context.bot, uid)


# ============== Startup Hooks ==============
async def post_init(app: Application):
    db.init_db()
    await set_bot_commands(app)
    # Scheduler — Daily At Configured Time
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        daily_report_job, CronTrigger(hour=config.DAILY_REPORT_HOUR, minute=config.DAILY_REPORT_MINUTE),
        args=[app.bot],
        id="daily_report",
    )
    scheduler.start()
    app.bot_data["scheduler"] = scheduler
    log.info(f"Scheduler Started — Daily Report At {config.DAILY_REPORT_HOUR:02d}:{config.DAILY_REPORT_MINUTE:02d}")

    # Start Payment Polling Loop In Background (Replaces Webhook Server)
    from payments import payment_polling_loop
    polling_task = asyncio.create_task(payment_polling_loop(app.bot))
    app.bot_data["polling_task"] = polling_task
    log.info("💰 Payment Polling Started (No Domain Needed)")


async def post_shutdown(app: Application):
    sched = app.bot_data.get("scheduler")
    if sched:
        sched.shutdown(wait=False)
    task = app.bot_data.get("polling_task")
    if task:
        task.cancel()


# ============== Main ==============
def main():
    if config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Please Set Your BOT_TOKEN In config.py Before Running.")
        return
    if config.ADMIN_IDS == [123456789]:
        print("⚠️ Warning: Please Set Your Admin IDs In config.py (Replace 123456789 With Your Telegram ID).")

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Command Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("support", cmd_support))
    app.add_handler(CommandHandler("faq", cmd_faq))
    app.add_handler(CommandHandler("db", cmd_db))
    app.add_handler(CommandHandler("log", cmd_log))

    # Callback Query Handlers
    # Primary Handler
    app.add_handler(CallbackQueryHandler(callback_handler, pattern=r"^(?!ep_clear_yes|ep_del_yes|ec_del_yes).*"))
    # Extra Handler For Dynamic Confirm Callbacks
    app.add_handler(CallbackQueryHandler(extra_callback_handler, pattern=r"^(ep_clear_yes|ep_del_yes|ec_del_yes):"))

    # Message Handler (Must Be Last)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_router))

    log.info("🤖 Bot Starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
