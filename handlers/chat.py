import os
import datetime
import html
import logging
import asyncio
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.database import DatabaseService, User, PointLog
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
    waiting_for_message = State()

# ==========================================
# 1. MEMULAI CHAT (Dari Feed Publik / Inbox)
# ==========================================
@router.callback_query(F.data.startswith("chat_"))
async def start_chat_from_button(callback: types.CallbackQuery, state: FSMContext, db: DatabaseService):
    parts = callback.data.split("_")
    if len(parts) < 2:
        return await callback.answer("Data tidak valid.", show_alert=True)
        
    target_id = int(parts[1])
    origin = parts[2] if len(parts) >= 3 else "public"
    user_id = callback.from_user.id
    
    user = await db.get_user(user_id)
    target = await db.get_user(target_id)
    
    if not target: return await callback.answer("❌ Profil user tidak ditemukan.", show_alert=True)

    # Hilangkan counter Notifikasi Inbox
    await getattr(db, 'mark_notif_read', lambda u, s, t: None)(user_id, target_id, "CHAT")

    if origin not in ["inbox", "match", "free"]:
        if not (user.is_vip or user.is_vip_plus):
            return await callback.answer("🔒 AKSES DITOLAK!\nHanya member VIP / VIP+ yang bisa memulai obrolan baru.", show_alert=True)

    active_expiry = await getattr(db, 'get_active_chat_session', lambda u, t: None)(user_id, target_id)
    
    should_deduct = True
    biaya_label = "1 Kuota Pesan"
    
    if active_expiry and active_expiry > datetime.datetime.now().timestamp():
        should_deduct = False
        biaya_label = "GRATIS (Melanjutkan Sesi Aktif)"
    elif origin in ["inbox", "match"]:
        should_deduct = False
        biaya_label = "GRATIS (Jalur Notifikasi)"
    elif user.is_vip_plus and origin == "free":
        should_deduct = False
        biaya_label = "GRATIS (VIP+ Privilege)"

    if should_deduct:
        if user.daily_message_quota <= 0 and user.extra_message_quota <= 0:
            return await callback.answer("❌ Kuota Pesan Anda habis! Silakan tunggu reset besok.", show_alert=True)

    await state.update_data(
        chat_target_id=target_id, 
        is_first_msg=True, 
        is_match_chat=(origin == "match"),
        origin_source=origin,
        thread_id=None, 
        expiry_ts=None
    )
    
    sesi_label = "48 Jam" if (user.is_vip_plus or origin == "match") else "24 Jam"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ BATALKAN", callback_data="cancel_chat")]])
    text_input = (
        f"✍️ <b>KIRIM PESAN</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"👤 Target: <b>{target.full_name.upper()}</b>\n"
        f"💰 Biaya: <i>{biaya_label}</i>\n"
        f"⏳ Durasi Sesi: <b>{sesi_label}</b>\n\n"
        f"<i>Ketik pesan pembuka Anda di bawah ini:</i>"
    )
    
    try: await callback.message.edit_caption(caption=text_input, reply_markup=kb, parse_mode="HTML")
    except: 
        try: await callback.message.delete()
        except: pass
        await callback.message.answer(text_input, reply_markup=kb, parse_mode="HTML")
        
    await state.set_state(ChatState.waiting_for_message)


# ==========================================
# 2. MEMULAI CHAT JALUR MATCH (GRATIS)
# ==========================================
@router.callback_query(F.data.startswith("matchchat_"))
async def start_match_chat(callback: types.CallbackQuery, state: FSMContext, db: DatabaseService):
    target_id = int(callback.data.split("_")[1])
    target = await db.get_user(target_id)
    if not target: return await callback.answer("❌ Profil tidak ditemukan.", show_alert=True)

    await state.update_data(
        chat_target_id=target_id, 
        is_first_msg=True, 
        is_match_chat=True, 
        origin_source="match",
        thread_id=None, 
        expiry_ts=None
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ BATALKAN", callback_data="cancel_chat")]])
    text_match = f"💘 <b>MATCH CHAT (GRATIS)</b>\n<code>━━━━━━━━━━━━━━━━━━</code>\nSilakan tulis pesan sapaan untuk <b>{target.full_name.upper()}</b>:\n<i>Sesi akan terbuka selama 48 Jam.</i>"
    
    try: await callback.message.edit_caption(caption=text_match, reply_markup=kb, parse_mode="HTML")
    except: await callback.message.answer(text_match, reply_markup=kb, parse_mode="HTML")
    await state.set_state(ChatState.waiting_for_message)


# ==========================================
# 3. MEMBALAS PESAN & LOGIKA PERPANJANGAN WAKTU
# ==========================================
@router.callback_query(F.data.startswith("reply_"))
async def handle_reply_logic(callback: types.CallbackQuery, state: FSMContext, db: DatabaseService):
    parts = callback.data.split("_")
    target_id = int(parts[1])
    thread_id = int(parts[2]) if parts[2] != "None" else None
    expiry_ts = int(parts[3])
    ext_count = int(parts[4])

    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    now_ts = datetime.datetime.now().timestamp()
    is_extension = False 
    
    await getattr(db, 'mark_notif_read', lambda u, s, t: None)(user_id, target_id, "CHAT")

    if now_ts > expiry_ts:
        if user.is_vip_plus:
            if ext_count == 0:
                is_extension = True
                await callback.answer("⏳ Waktu habis! Sebagai VIP+, perpanjangan pertamamu GRATIS.", show_alert=True)
            else:
                if user.daily_message_quota <= 0 and user.extra_message_quota <= 0:
                    return await callback.answer("❌ Kuota Pesan untuk perpanjangan habis!", show_alert=True)
                is_extension = True
                await callback.answer("⏳ Waktu habis! Membalas akan memotong 1 Kuota Pesan.", show_alert=True)
        else:
            if user.daily_message_quota <= 0 and user.extra_message_quota <= 0:
                return await callback.answer("⏳ WAKTU HABIS! Kuota Pesan Anda kosong. Silakan Top Up.", show_alert=True)
            is_extension = True
            await callback.answer("⏳ Waktu habis! Membalas akan memotong 1 Kuota Pesan.", show_alert=True)

    await state.update_data(
        chat_target_id=target_id, 
        is_first_msg=False, 
        is_match_chat=False,
        origin_source="inbox",
        is_extension=is_extension, 
        ext_count=ext_count, 
        thread_id=thread_id, 
        expiry_ts=expiry_ts
    )
    
    biaya_ext = "GRATIS (VIP+)" if (is_extension and user.is_vip_plus and ext_count == 0) else "1 Kuota Pesan"
    teks_judul = f"⏳ <b>PERPANJANG & BALAS</b>\nBiaya: <i>{biaya_ext}</i>" if is_extension else "✍️ <b>BALAS PESAN</b>"

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ BATAL", callback_data="cancel_chat")]])
    await callback.message.answer(f"{teks_judul}\n\nKetik balasan Anda:", reply_markup=kb, parse_mode="HTML")
    await state.set_state(ChatState.waiting_for_message)


# ==========================================
# 4. EKSEKUSI PENGIRIMAN PESAN & DISTRIBUSI POIN
# ==========================================
@router.message(ChatState.waiting_for_message)
async def process_chat_proxy(message: types.Message, state: FSMContext, db: DatabaseService, bot: Bot):
    if not message.text:
        msg = await message.answer("⚠️ Maaf, kirim pesan dalam bentuk teks saja.")
        await asyncio.sleep(2)
        try: await msg.delete()
        except: pass
        return

    data = await state.get_data()
    target_id = data.get('chat_target_id')
    is_first = data.get('is_first_msg')
    is_match = data.get('is_match_chat')
    origin = data.get('origin_source')
    is_ext = data.get('is_extension')
    ext_count = data.get('ext_count')
    thread_id = data.get('thread_id')
    
    sender_id = message.from_user.id
    sender = await db.get_user(sender_id)
    notif_service = NotificationService(bot, db) 

    # --- 1. PEMOTONGAN KUOTA PESAN ---
    deduct_now = False
    active_expiry = await getattr(db, 'get_active_chat_session', lambda u, t: None)(sender_id, target_id)
    has_active_session = active_expiry and active_expiry > datetime.datetime.now().timestamp()

    if (is_first and origin == "public" and not has_active_session) or is_ext:
        if sender.is_vip_plus:
            deduct_now = True if (is_first and origin == "public" and not has_active_session) or (is_ext and ext_count > 0) else False
        else:
            deduct_now = True

    if deduct_now:
        success_deduct = await db.use_message_quota(sender_id)
        if not success_deduct:
            await state.clear()
            return await message.answer("❌ Pengiriman dibatalkan: Kuota Pesan Anda sudah habis!")

    # --- 2. DISTRIBUSI BONUS POIN ---
    if origin == "inbox": 
        today_str = datetime.datetime.now().strftime("%Y%m%d")
        point_to_add = 200

        log_key = f"ChatBonus_{today_str}_{sender_id}_{target_id}_inbox"
        bonus_exists = await db.check_bonus_exists(log_key)
        
        if not bonus_exists:
            sukses_poin = await db.add_points_with_log(sender_id, point_to_add, log_key)
            if sukses_poin:
                try: await message.answer(f"🎉 <b>BALAS INBOX!</b>\nKamu mendapatkan <b>+{point_to_add} Poin</b> karena membalas pesan ini.", parse_mode="HTML")
                except: pass

    # --- 3. PUSH NOTIFIKASI UNIVERSAL ---
    kasta_sender = "💎 VIP+" if sender.is_vip_plus else "🌟 VIP" if sender.is_vip else "🎭 TALENT" if sender.is_premium else "👤 FREE"
    try: 
        is_reply = not is_first
        await notif_service.trigger_new_message(target_id, sender_id, sender.full_name, is_reply)
    except: pass

    # --- 4. LOGGING ADMIN KE TELEGRAM GROUP ---
    try:
        if is_first:
            jenis_sesi = "SESI MATCH" if is_match else "SESI CHAT BARU"
            log_text = f"🧵 <b>{jenis_sesi}</b>\nDari: <b>{sender.full_name}</b>\nKe: <code>{target_id}</code>\nIsi: <i>{html.escape(message.text)}</i>"
            if CHAT_LOG_CHANNEL_ID:
                msg_log = await bot.send_message(CHAT_LOG_CHANNEL_ID, log_text, parse_mode="HTML")
                thread_id = msg_log.message_id
        else:
            if CHAT_LOG_GROUP_ID and thread_id:
                tag_ext = "[EXT] " if is_ext else ""
                log_reply = f"💬 {tag_ext}<b>BALASAN</b>\nDari: <code>{sender_id}</code> ➡️ <code>{target_id}</code>\nIsi: <i>{html.escape(message.text)}</i>"
                await bot.send_message(CHAT_LOG_GROUP_ID, log_reply, reply_to_message_id=thread_id, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Gagal Logging Admin: {e}")

    # --- 5. PENGIRIMAN PESAN KE TARGET & REKAM SESI ---
    duration_hrs = 48 if (sender.is_vip_plus or is_match) else 24
    new_expiry_ts = int((datetime.datetime.now() + datetime.timedelta(hours=duration_hrs)).timestamp())
    waktu_fmt = datetime.datetime.fromtimestamp(new_expiry_ts).strftime("%H:%M")
    
    await getattr(db, 'upsert_chat_session', lambda u, t, e: None)(sender_id, target_id, new_expiry_ts)
    
    if is_ext and sender.is_vip_plus and ext_count == 0: ext_count = 1

    # --- HEADER PESAN STANDAR ---
    if is_first:
        header_msg = f"💌 PESAN BARU ({kasta_sender})"
        footer_msg = f"🎁 <b>BONUS KLAIM:</b> Balas pesan ini untuk mendapatkan <b>+200 POIN</b> ke saldomu!"
    else:
        header_msg = f"💬 BALASAN DARI {sender.full_name.upper()}"
        footer_msg = "<i>Gunakan tombol di bawah untuk terus mengobrol.</i>"

    target_text_full = (
        f"<b>{header_msg}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"<i>{html.escape(message.text)}</i>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"{footer_msg}\n\n"
        f"⏳ Sesi chat ditutup pada: <b>{waktu_fmt}</b>"
    )
    
    # Callback data reply sudah dibersihkan dari parameter u_flag_str
    kb_target = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 BALAS PESAN", callback_data=f"reply_{sender_id}_{thread_id}_{new_expiry_ts}_{ext_count}")],
        [InlineKeyboardButton(text="👤 LIHAT PROFIL", callback_data=f"view_{sender_id}_public")]
    ])

    try:
        await bot.send_message(target_id, target_text_full, reply_markup=kb_target, parse_mode="HTML")
        
        kb_success = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 KEMBALI KE NOTIFIKASI", callback_data="menu_notifications")],
            [InlineKeyboardButton(text="🏠 DASHBOARD", callback_data="back_to_dashboard")]
        ])
        await message.answer(f"✅ <b>Pesan berhasil terkirim!</b>\n⏳ Sesi aktif s/d: <b>{waktu_fmt}</b>", reply_markup=kb_success, parse_mode="HTML")
        
    except Exception as e:
        await message.answer("❌ Gagal mengirim pesan. Target mungkin telah memblokir bot.")

    await state.clear()

# ==========================================
# 5. PEMBATALAN CHAT
# ==========================================
@router.callback_query(F.data == "cancel_chat")
async def cancel_chat_action(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    kb_cancel = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 KEMBALI KE NOTIFIKASI", callback_data="menu_notifications")],
        [InlineKeyboardButton(text="🏠 DASHBOARD", callback_data="back_to_dashboard")]
    ])
    try: await callback.message.edit_caption(caption="❌ Penulisan pesan dibatalkan.", reply_markup=kb_cancel)
    except: 
        try: await callback.message.delete()
        except: pass
        await callback.message.answer("❌ Penulisan pesan dibatalkan.", reply_markup=kb_cancel)
    await callback.answer()
        
