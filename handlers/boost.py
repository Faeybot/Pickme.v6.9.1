import asyncio
import datetime
import os
import html
import logging
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from services.database import DatabaseService, User

router = Router()

# --- HELPER: BACKGROUND TASK AUTO-SUNDUL ---
async def execute_repost_logic(bot: Bot, user_id: int, count: int, interval_hours: int, label: str, db: DatabaseService):
    """
    SISTEM AUTO-SUNDUL (Berjalan di Background)
    Melakukan repost otomatis ke channel Feed sesuai paket yang dipilih.
    """
    channel_id = os.getenv("FEED_CHANNEL_ID")
    bot_info = await bot.get_me()
    
    for i in range(count):
        try:
            # Ambil data user fresh dari DB setiap kali mau posting
            # (Siapa tahu user ganti foto/bio saat proses boost masih berjalan)
            user = await db.get_user(user_id)
            if not user:
                break
                
            display_name = user.full_name
            link_profile = f"https://t.me/{bot_info.username}?start=view_{user.id}"
            
            # Format visual sinkron dengan Feed.py
            header = f"🚀 <b>[{label}]</b>\n👤 <b>{display_name.upper()}</b> | <a href='{link_profile}'>VIEW PROFILE</a>"
            isi_feed = f"<blockquote>{html.escape(user.bio or 'Cek profilku yuk! Mari berkenalan.')}</blockquote>"
            full_text = f"{header}\n<code>{'—' * 20}</code>\n{isi_feed}\n\n📍 {user.city_hashtag} #{user.gender.upper()} #PickMeBoost"

            if user.photo_id:
                await bot.send_photo(channel_id, photo=user.photo_id, caption=full_text, parse_mode="HTML")
            else:
                await bot.send_message(channel_id, full_text, parse_mode="HTML")
            
            # Jika masih ada sisa antrean repost, tunggu sesuai interval (jam -> detik)
            if i < count - 1:
                await asyncio.sleep(interval_hours * 3600) 
                
        except Exception as e:
            logging.error(f"Error pada siklus Boost Loop ke-{i+1} untuk User {user_id}: {e}")
            break

# --- 1. MENU BOOST ---
@router.callback_query(F.data == "menu_boost")
async def show_boost_menu(callback: types.CallbackQuery, db: DatabaseService):
    user = await db.get_user(callback.from_user.id)
    total_boost = user.paid_boost_balance + user.weekly_free_boost
    
    text = (
        "🚀 <b>PUSAT KENDALI BOOST</b>\n"
        f"<code>{'—' * 20}</code>\n"
        "Boost adalah fitur untuk <b>menyundul profilmu</b> secara otomatis agar selalu berada di puncak Channel Feed.\n\n"
        "<b>📊 PILIHAN PAKET:</b>\n"
        "• <b>1 Tiket:</b> Tampil 3x (Jeda 3 jam)\n"
        "• <b>3 Tiket:</b> Tampil 6x (Jeda 2 jam)\n"
        "• <b>5 Tiket:</b> Tampil 12x (Jeda 1 jam)\n\n"
        "⚠️ <i>Aturan: Demi kenyamanan bersama, Boost hanya bisa diaktifkan <b>1x Sehari</b>.</i>\n\n"
        f"💳 Saldo Tiket Anda: <b>{total_boost} Tiket</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Pakai 1 Tiket (3x Post)", callback_data="boost_plan_1")],
        [InlineKeyboardButton(text="🚀 Pakai 3 Tiket (6x Post)", callback_data="boost_plan_3")],
        [InlineKeyboardButton(text="🔥 Pakai 5 Tiket (12x Post)", callback_data="boost_plan_5")],
        [InlineKeyboardButton(text="🛒 BELI TIKET BOOST", callback_data="menu_pricing")],
        [InlineKeyboardButton(text="🏠 KEMBALI KE DASHBOARD", callback_data="back_to_dashboard")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

# --- 2. EKSEKUSI BOOST ---
@router.callback_query(F.data.startswith("boost_plan_"))
async def process_boost_plan(callback: types.CallbackQuery, db: DatabaseService, bot: Bot):
    plan = int(callback.data.split("_")[2]) # Mendapatkan angka 1, 3, atau 5
    user_id = callback.from_user.id
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    async with db.session_factory() as session:
        user = await session.get(User, user_id)
        
        # 1. PROTEKSI ANTI-SPAM (1x Sehari)
        if user.last_boost_date == today:
            return await callback.answer("⚠️ Anda sudah melakukan Boost hari ini. Gunakan kembali besok!", show_alert=True)

        # 2. VALIDASI SALDO TIKET
        total_boost = user.paid_boost_balance + user.weekly_free_boost
        if total_boost < plan:
            return await callback.answer(f"❌ Saldo tidak cukup! Anda butuh {plan} tiket.", show_alert=True)

        # 3. SETTING PARAMETER
        if plan == 1:
            repost_count, interval, label = 3, 3, "BOOST 1x"
        elif plan == 3:
            repost_count, interval, label = 6, 2, "BOOST 3x"
        else: # plan 5
            repost_count, interval, label = 12, 1, "BOOST 5x"

        # 4. POTONG SALDO (Prioritas: Tiket Gratis Mingguan dulu, baru Tiket Beli)
        remaining_to_deduct = plan
        if user.weekly_free_boost >= remaining_to_deduct:
            user.weekly_free_boost -= remaining_to_deduct
        else:
            remaining_to_deduct -= user.weekly_free_boost
            user.weekly_free_boost = 0
            user.paid_boost_balance -= remaining_to_deduct
        
        # Catat tanggal hari ini agar besok baru bisa boost lagi
        user.last_boost_date = today
        await session.commit()

    # --- 5. AKTIVASI & JALANKAN BACKGROUND TASK ---
    kb_success = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 DASHBOARD", callback_data="back_to_dashboard")]
    ])
    
    await callback.message.edit_text(
        f"✅ <b>BOOST BERHASIL DIAKTIFKAN!</b>\n"
        f"<code>{'—' * 20}</code>\n"
        f"Profil Anda akan disundul ke Channel sebanyak <b>{repost_count}x</b> secara otomatis.\n"
        f"Bot akan menangani ini di latar belakang. Anda bisa menutup menu ini.",
        reply_markup=kb_success,
        parse_mode="HTML"
    )
    
    # Jalankan proses loop di background tanpa membuat bot berhenti merespons user
    asyncio.create_task(execute_repost_logic(bot, user_id, repost_count, interval, label, db))
