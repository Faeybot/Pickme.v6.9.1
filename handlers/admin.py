import os
import html
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.database import DatabaseService, User, PointLog

router = Router()

# ==========================================
# KONFIGURASI ID & HAK AKSES ADMIN
# ==========================================
def get_int_id(key: str, default=0):
    val = os.getenv(key)
    if not val: return default
    val = str(val).strip().replace("'", "").replace('"', '')
    if val.startswith("-") or val.isdigit():
        try: return int(val)
        except: return val
    return default

def get_list_ids(key: str):
    val = os.getenv(key, "")
    return [int(x) for x in val.split(",") if x.strip().lstrip('-').isdigit()]

# 1. ID Publik, Log & Grup Approval
FEED_CHANNEL_ID = get_int_id("FEED_CHANNEL_ID")
FINANCE_CHANNEL_ID = get_int_id("FINANCE_CHANNEL_ID") # Buku Besar (Log)
FINANCE_GROUP_ID = get_int_id("FINANCE_GROUP_ID")     # Tempat Klik Approve

# 2. Hak Akses
OWNER_ID = get_int_id("OWNER_ID")
ADMIN_FINANCE_IDS = get_list_ids("ADMIN_FINANCE_IDS")
ADMIN_MODERATOR_IDS = get_list_ids("ADMIN_MODERATOR_IDS")

ALL_FINANCE_ADMINS = [OWNER_ID] + ADMIN_FINANCE_IDS
ALL_MODERATORS = [OWNER_ID] + ADMIN_MODERATOR_IDS

class ChatAdminState(StatesGroup):
    waiting_admin_msg = State()

# ==========================================
# DIVISI KEUANGAN (WD & TRIAL APPROVAL)
# ==========================================

# --- 1. KONFIRMASI WD (SUKSES) ---
@router.callback_query(F.data.startswith("wd_confirm_"))
async def admin_confirm_wd(callback: types.CallbackQuery, db: DatabaseService, bot: Bot):
    if callback.from_user.id not in ALL_FINANCE_ADMINS:
        return await callback.answer("🚫 Akses Ditolak!", show_alert=True)

    parts = callback.data.split("_")
    user_id = int(parts[2])
    trx_id = parts[3]

    async with db.session_factory() as session:
        # Langsung update status di database jika ada tabel WithdrawRequest
        # Jika tidak ada, kita asumsikan poin sudah dipotong di awal (withdraw.py)
        user = await session.get(User, user_id)
        if user:
            user.has_withdrawn_before = True
        await session.commit()

    # Update UI di Grup Finance (Tempat Approve)
    old_text = callback.message.text
    new_text = f"{old_text}\n\n✅ <b>LUNAS (DITRANSFER)</b>\nOleh: {callback.from_user.first_name}"
    await callback.message.edit_text(new_text, reply_markup=None, parse_mode="HTML")

    # Kirim ke Buku Besar (Channel Finance)
    if FINANCE_CHANNEL_ID:
        log_text = (
            f"🧾 <b>LAPORAN KAS KELUAR (WD)</b>\n"
            f"ID TRX: <code>{trx_id}</code>\n"
            f"Penerima: <code>{user_id}</code>\n"
            f"Status: ✅ SUKSES DITRANSFER"
        )
        try: await bot.send_message(FINANCE_CHANNEL_ID, log_text, parse_mode="HTML")
        except: pass

    # Notif ke User
    try:
        await bot.send_message(user_id, "🎊 <b>WITHDRAW BERHASIL!</b>\nDana telah dikirim ke rekening/e-wallet Anda. Silakan cek saldo!", parse_mode="HTML")
    except: pass
    await callback.answer("Withdraw Selesai!")

# --- 2. APPROVAL TRIAL (STRATEGI JACKPOT VIP+ 7 HARI) ---
@router.callback_query(F.data.startswith("trial_apv_"))
async def admin_approve_trial_jackpot(callback: types.CallbackQuery, db: DatabaseService, bot: Bot):
    if callback.from_user.id not in ALL_FINANCE_ADMINS:
        return await callback.answer("🚫 Akses Ditolak!", show_alert=True)

    parts = callback.data.split("_")
    user_id = int(parts[2])
    # item_type diabaikan karena semua jadi VIP+
    
    expiry_date = datetime.now() + timedelta(days=7)
    
    async with db.session_factory() as session:
        user = await session.get(User, user_id)
        if not user: return await callback.answer("User tidak ditemukan")

        # LOGIKA JACKPOT: Apapun yang diminta, kasih VIP+ (Bait Premium)
        user.is_vip_plus = True
        user.is_vip = False
        user.is_premium = False # JANGAN dikasi Talent agar tidak bisa WD (Celah Keamanan)
        user.vip_expiry_at = expiry_date # Pastikan kolom ini ada di DB
        
        # Berikan Kuota Sultan agar user betah
        user.daily_feed_text_quota = 10
        user.daily_feed_photo_quota = 5
        user.daily_message_quota = 10
        user.daily_open_profile_quota = 10
        
        await session.commit()

    # Update UI Grup Admin
    old_text = callback.message.text
    await callback.message.edit_text(f"{old_text}\n\n✅ <b>VIP+ AKTIF (7 HARI)</b>\nApproved by: {callback.from_user.first_name}", reply_markup=None)

    # Kirim ke Buku Besar (Channel Finance)
    if FINANCE_CHANNEL_ID:
        log_trial = (
            f"🎁 <b>LOG TRIAL PREMIUM</b>\n"
            f"User ID: <code>{user_id}</code>\n"
            f"Kasta: 💎 VIP+ (JACKPOT)\n"
            f"Durasi: 7 Hari"
        )
        try: await bot.send_message(FINANCE_CHANNEL_ID, log_trial, parse_mode="HTML")
        except: pass

    # Notif ke User (Pesan Sesuai Instruksi Kamu)
    msg_user = (
        "🎉 <b>SELAMAT! PENGAJUAN DISETUJUI</b>\n\n"
        "Akunmu telah ditingkatkan menjadi <b>VIP+</b> selama <b>7 hari masa trial</b>.\n\n"
        "Nikmati fitur bongkar anonim, chat sepuasnya, dan prioritas discovery sekarang juga!"
    )
    try:
        await bot.send_message(user_id, msg_user, parse_mode="HTML")
    except: pass
    await callback.answer("Trial VIP+ Aktif!")

# --- 3. REJECT TRIAL ---
@router.callback_query(F.data.startswith("trial_rej_"))
async def admin_reject_trial(callback: types.CallbackQuery, bot: Bot):
    user_id = int(callback.data.split("_")[2])
    await callback.message.edit_text(f"{callback.message.text}\n\n❌ <b>DITOLAK</b>", reply_markup=None)
    try:
        await bot.send_message(user_id, "❌ <b>PENGAJUAN DITOLAK</b>\nMaaf, permintaan trial Anda belum dapat disetujui saat ini.", parse_mode="HTML")
    except: pass
    await callback.answer("Ditolak.")

# ==========================================
# DIVISI MODERASI (FEED)
# ==========================================

@router.callback_query(F.data.startswith("apv_f_"))
async def admin_approve_feed(callback: types.CallbackQuery, db: DatabaseService, bot: Bot):
    if callback.from_user.id not in ALL_MODERATORS:
        return await callback.answer("🚫 Moderator Only!", show_alert=True)

    parts = callback.data.split("_")
    target_id = int(parts[2])
    is_anon = parts[3] == "1"
    
    user = await db.get_user(target_id)
    bot_info = await bot.get_me()

    # Ambil Caption Asli
    raw_caption = callback.message.caption or ""
    original_caption = raw_caption.split("Caption:")[1].strip() if "Caption:" in raw_caption else ""
    
    # Format Posting Channel
    name_header = "🎭 <b>ANONIM</b>" if is_anon else f"👤 <b>{user.full_name.upper()}</b>"
    link_profile = f"https://t.me/{bot_info.username}?start=view_{user.id}"
    
    city_tag = f"#{user.location_name.replace(' ', '').title()}" if user.location_name else "#Indonesia"
    gender_tag = f"#{user.gender.title()}" if user.gender else ""

    final_post = (
        f"{name_header} | <a href='{link_profile}'>VIEW PROFILE</a>\n"
        f"<code>{'—' * 20}</code>\n"
        f"<blockquote><i>{html.escape(original_caption)}</i></blockquote>\n\n"
        f"📍 {city_tag} {gender_tag}"
    )
    
    try:
        await bot.send_photo(FEED_CHANNEL_ID, photo=callback.message.photo[-1].file_id, caption=final_post, parse_mode="HTML")
        await callback.message.edit_caption(caption=f"{raw_caption}\n\n✅ <b>APPROVED</b>", reply_markup=None)
        await bot.send_message(target_id, "🎉 <b>POSTINGAN DITERIMA!</b>\nFoto Anda telah tayang di Channel Feed.", parse_mode="HTML")
    except Exception as e:
        logging.error(f"Error Feed: {e}")
        await callback.answer("Gagal kirim ke Channel.")

# ==========================================
# FITUR UTAMA ADMIN (CHAT & VIEW)
# ==========================================

@router.callback_query(F.data.startswith("admin_msg_"))
async def admin_chat_start(callback: types.CallbackQuery, state: FSMContext):
    target_id = int(callback.data.split("_")[2])
    await state.update_data(chat_target_id=target_id)
    await state.set_state(ChatAdminState.waiting_admin_msg)
    await callback.message.answer(f"💬 Ketik pesan untuk User <code>{target_id}</code>:", parse_mode="HTML")
    await callback.answer()

@router.message(ChatAdminState.waiting_admin_msg)
async def admin_chat_send(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target_id = data.get("chat_target_id")
    
    text = f"📩 <b>PESAN ADMIN PICKME</b>\n<code>{'—' * 20}</code>\n{html.escape(message.text)}"
    try:
        await bot.send_message(target_id, text, parse_mode="HTML")
        await message.answer("✅ Pesan terkirim.")
    except:
        await message.answer("❌ Gagal kirim.")
    await state.clear()

@router.callback_query(F.data.startswith("admin_view_"))
async def admin_view_profile(callback: types.CallbackQuery, db: DatabaseService):
    target_id = int(callback.data.split("_")[2])
    user = await db.get_user(target_id)
    
    status = "💎 VIP+" if user.is_vip_plus else "🌟 VIP" if user.is_vip else "🎭 TALENT" if user.is_premium else "👤 FREE"
    
    info = (
        f"👤 <b>ADMIN VIEW: {user.full_name}</b>\n"
        f"Kasta: {status}\n"
        f"Saldo: {user.poin_balance:,} Poin\n"
        f"ID: <code>{user.id}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Chat", callback_data=f"admin_msg_{user.id}")],
        [InlineKeyboardButton(text="❌ Tutup", callback_data="close_admin_view")]
    ])
    await callback.message.answer_photo(photo=user.photo_id, caption=info, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "close_admin_view")
async def close_view(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
