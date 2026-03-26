import asyncio
import os
import time
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types 
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault 

# --- 1. IMPORT SERVICES ---
from services.database import DatabaseService
from services.payment import PaymentService
from services.notification import NotificationService

# --- 2. IMPORT HANDLERS ---
from handlers import (
    admin, start, feed, discovery, profile, 
    pricing, boost, registration, status,
    withdraw, chat, inbox, unmask, notification as notifications_handler,
    referrals, who_like_me, match
)
from handlers.referrals import schedule_referral_evaluation

# ==========================================
# SETTING ZONA WAKTU KE ASIA/JAKARTA (UTC+7)
# ==========================================
os.environ['TZ'] = 'Asia/Jakarta'
try:
    if hasattr(time, 'tzset'):
        time.tzset() 
except Exception:
    pass 

load_dotenv()

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="🏠 Dashboard Utama"),
        BotCommand(command="pricing", description="🛒 Top Up & Upgrade"),
        BotCommand(command="help", description="💡 Panduan & Bantuan")
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

async def schedule_daily_reset(db: DatabaseService):
    tz = ZoneInfo("Asia/Jakarta")
    while True:
        now = datetime.now(tz)
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        wait_seconds = (next_midnight - now).total_seconds()
        
        logging.info(f"⏰ [SCHEDULER] Menunggu {wait_seconds / 3600:.2f} Jam menuju Maintenance.")
        await asyncio.sleep(wait_seconds)
        
        try:
            await db.check_expired_vip()
            await db.reset_daily_quotas()
            if datetime.now(tz).weekday() == 0:
                await db.reset_weekly_quotas()
            logging.info("✅ MAINTENANCE BERHASIL!")
        except Exception as e:
            logging.error(f"❌ Maintenance Error: {e}")

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # --- 3. NORMALISASI URL DATABASE ---
    raw_db_url = os.getenv("DATABASE_URL")
    if raw_db_url:
        if raw_db_url.startswith("postgres://"):
            db_url = raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif raw_db_url.startswith("postgresql://") and "+asyncpg" not in raw_db_url:
            db_url = raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        else:
            db_url = raw_db_url
    else:
        db_url = "sqlite+aiosqlite:///pickme.db"

    # --- 4. INISIALISASI BOT & SERVICES ---
    bot = Bot(
        token=os.getenv("BOT_TOKEN"),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    db = DatabaseService(db_url)
    await db.create_tables()
    payment = PaymentService(db)
    notif_service = NotificationService(bot, db)

    # --- 5. DEPENDENCY INJECTION ---
    dp["db"] = db
    dp["payment"] = payment
    dp["notif"] = notif_service 

    # --- 6. REGISTRASI ROUTER ---
    dp.include_router(registration.router)
    dp.include_router(start.router)
    dp.include_router(referrals.router)
    dp.include_router(admin.router)
    dp.include_router(feed.router)
    dp.include_router(discovery.router)
    dp.include_router(who_like_me.router)
    dp.include_router(match.router)
    dp.include_router(chat.router)
    dp.include_router(inbox.router)
    dp.include_router(unmask.router)
    dp.include_router(profile.router)
    dp.include_router(pricing.router)
    dp.include_router(boost.router)
    dp.include_router(withdraw.router)
    dp.include_router(status.router)
    dp.include_router(notifications_handler.router)

    # --- 🛡️ GLOBAL ERROR HANDLER ---
    @dp.error()
    async def global_error_handler(event: types.ErrorEvent):
        logging.error(f"⚠️ [CRITICAL ERROR]: {event.exception}")
        return True 

    # 🛠️ VARIABEL TASK (GARBAGE COLLECTOR SAFETY)
    daily_task = None
    referral_task = None

    try:
        # --- 7. SET COMMAND MENU ---
        await set_bot_commands(bot)
        logging.info("✔️ Tombol Menu Berhasil Dipasang.")

        # --- 8. JALANKAN SCHEDULER ---
        referral_task = asyncio.create_task(schedule_referral_evaluation(bot, db))
        daily_task = asyncio.create_task(schedule_daily_reset(db))

        await bot.delete_webhook(drop_pending_updates=True)
        print("🚀 Bot PickMe Aktif & Tahan Banting (WIB)!")
        await dp.start_polling(bot)

    except Exception as e:
        logging.error(f"❌ Error Saat Menjalankan Bot: {e}")

    finally:
        # Bersihkan task saat shutdown
        if daily_task:
            daily_task.cancel()
        if referral_task:
            referral_task.cancel()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot Berhenti Secara Aman.")
