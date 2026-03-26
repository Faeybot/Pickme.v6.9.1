import os
import datetime
import html
import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from services.database import DatabaseService
from services.notification import NotificationService 

router = Router()

def get_int_id(key: str):
    val = os.getenv(key)
    if val:
        val = str(val).strip().replace("'", "").replace('"', '')
        if val.startswith("-") or val.isdigit():
            try: return int(val)
            except: return val
    return val

CHAT_LOG_CHANNEL_ID = get_int_id("CHAT_LOG_CHANNEL_ID")
CHAT_LOG_GROUP_ID = get_int_id("CHAT_LOG_GROUP_ID")

class ChatState(StatesGroup):
    in_chat_room = State() # STATE BARU: Mengunci user di ruang obrolan

# ==========================================
# 1. MASUK KE RUANG OBROLAN (GERBANG UTAMA)
# ==========================================
@router.callback_query(F.data.startswith("chat_"))
async def enter_chat_room(callback: types.CallbackQuery, state: FSMContext, db: DatabaseService):
    parts = callback.data.split("_")
    target_id = int(parts[1])
    origin = parts[2] if len(parts) >= 3 else "public"
    user_id = callback.from_user.id
    
    user = await db.get_user(user_id)
    target = await db.get_user(target_id)
    if not target: return await callback.answer("❌ Profil tidak ditemukan.", show_alert=True)

    # Cek Database Sesi
    session_data = await db.get_active_chat_session(user_id, target_id)
    now_ts = int(datetime.datetime.now().timestamp())
    
    is_active = session_data and session_data.expires_at > now_ts
    should_deduct = False
    
    # Logika Gerbang Kuota
    if not is_active:
        if origin in ["public", "extend"]:
            if not (user.is_vip or user.is_vip_plus):
                return await callback.answer("🔒 AKSES DITOLAK! Hanya VIP/VIP+ yang bisa memulai obrolan baru.", show_alert=True)
            should_deduct = True
        elif user.is_vip_plus and origin == "free":
            should_deduct = False
        elif origin in ["inbox", "match"]:
            should_deduct = False # Karena kompensasi atau sistem
        
        if should_deduct:
            if user.daily_message_quota <= 0 and user.extra_message_quota <= 0:
                return await callback.answer("❌ Kuota Pesan Anda habis! Silakan tunggu reset besok.", show_alert=True)
            
            sukses = await db.use_message_quota(user_id)
            if not sukses: return await callback.answer("Gagal memotong kuota.", show_alert=True)
            
            # Buat Sesi Baru / Perpanjang
            duration_hrs = 48 if user.is_vip_plus else 24
            new_expiry_ts = int((datetime.datetime.now() + datetime.timedelta(hours=duration_hrs)).timestamp())
            
            # Ambil thread lama jika ada
            old_thread = session_data.thread_id if session_data else None
            await db.upsert_chat_session(user_id, target_id, new_expiry_ts, thread_id=old_thread)
            session_data = await db.get_active_chat_session(user_id, target_id)

    # Hilangkan counter Notifikasi
    await getattr(db, 'mark_notif_read', lambda u, s, t: None)(user_id, target_id, "CHAT")
    
    # Ambil thread ID
    thread_id = session_data.thread_id if session_data else None

    # Kunci FSM
    await state.update_data(chat_target_id=target_id, thread_id=thread_id)
    await state.set_state(ChatState.in_chat_room)
    
    # Kirim Banner Ruang Obrolan
    reply_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ TUTUP OBROLAN")]], resize_keyboard=True)
    
    banner_text = (
        f"💬 <b>RUANG OBROLAN BERSAMA {target.full_name.upper()}</b>\n"
        f"<code>================================</code>\n"
        f"<i>Pintu terbuka. Semua yang kamu ketik di bawah ini akan langsung terkirim ke target. Riwayat percakapan tidak akan terhapus.</i>\n\n"
        f"⬇️ <b>Ketik pesanmu sekarang:</b>"
    )
    
    try: await callback.message.delete()
    except: pass
    await callback.message.answer(banner_text, reply_markup=reply_kb, parse_mode="HTML")

# ==========================================
# 2. MESIN RUANG OBROLAN (MENGETIK & LOGGING)
# ==========================================
@router.message(ChatState.in_chat_room)
async def process_chat_room_message(message: types.Message, state: FSMContext, db: DatabaseService, bot: Bot):
    if message.text == "❌ TUTUP OBROLAN" or message.text == "/exit":
        await state.clear()
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 BUKA INBOX", callback_data="menu_inbox")], [InlineKeyboardButton(text="🏠 DASHBOARD", callback_data="back_to_dashboard")]])
        return await message.answer("🚪 <b>Kamu telah keluar dari Ruang Obrolan.</b>", reply_markup=kb, parse_mode="HTML")

    if not message.text:
        return await message.answer("⚠️ Maaf, sistem ini hanya mendukung pesan teks.")

    data = await state.get_data()
    target_id = data.get('chat_target_id')
    thread_id = data.get('thread_id')
    
    sender_id = message.from_user.id
    sender = await db.get_user(sender_id)
    notif_service = NotificationService(bot, db)

    # 1. VALIDASI EXPIRY (Jaga-jaga kalau pas lagi ngetik waktunya habis)
    session_data = await db.get_active_chat_session(sender_id, target_id)
    now_ts = int(datetime.datetime.now().timestamp())
    if not session_data or session_data.expires_at < now_ts:
        await state.clear()
        return await message.answer("⏳ Waktu obrolan telah berakhir. Silakan masuk kembali dari Inbox untuk memperpanjang.", reply_markup=ReplyKeyboardRemove())

    # 2. LOGGING KE TELEGRAM CHANNEL & GRUP (SEBAGAI DATABASE PENYIMPANAN)
    if not thread_id and CHAT_LOG_CHANNEL_ID:
        try:
            msg_log = await bot.send_message(CHAT_LOG_CHANNEL_ID, f"🧵 <b>THREAD SESI CHAT</b>\nID: <code>{sender_id}</code> & <code>{target_id}</code>", parse_mode="HTML")
            thread_id = msg_log.message_id
            await state.update_data(thread_id=thread_id) # Update state
        except Exception as e:
            logging.error(f"Gagal Inisiasi Thread: {e}")
            
    if thread_id and CHAT_LOG_GROUP_ID:
        try:
            await bot.send_message(CHAT_LOG_GROUP_ID, f"💬 <b>{sender.full_name}:</b>\n{html.escape(message.text)}", reply_to_message_id=thread_id, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Gagal Simpan History ke Grup: {e}")

    # 3. UPDATE DATABASE SQL (Hanya Simpan Thread ID & Cuplikan Pesan)
    await db.upsert_chat_session(sender_id, target_id, session_data.expires_at, thread_id=thread_id, last_message=message.text)

    # 4. KIRIM PESAN KE TARGET (Sebagai Pesan Biasa, BUKAN FSM)
    kasta = "💎 VIP+" if sender.is_vip_plus else "🌟 VIP" if sender.is_vip else "👤 FREE"
    
    target_text = (
        f"💬 <b>PESAN BARU ({kasta})</b>\n"
        f"Dari: <b>{sender.full_name.upper()}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"<i>{html.escape(message.text)}</i>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>"
    )
    
    kb_target = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 BUKA RUANG OBROLAN", callback_data=f"chat_{sender_id}_inbox")]])
    
    try:
        await bot.send_message(target_id, target_text, reply_markup=kb_target, parse_mode="HTML")
        await notif_service.trigger_new_message(target_id, sender_id, sender.full_name, True)
    except Exception:
        return await message.answer("❌ Gagal mengirim pesan. Target mungkin telah memblokir bot.")
