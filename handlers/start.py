import os
import html
import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto

from services.database import DatabaseService, User

router = Router()

BANNER_PHOTO_ID = os.getenv("BANNER_PHOTO_ID", "AgACAgUAAxkBAAIKUmm-3V96dh0wXlEwKgR9cZYxQJ7IAAJWEWsb5Sz5VRdAhJBTFWieAQADAgADeAADOgQ")

# ==========================================
# 0. HELPER MINAT (DIKEMBALIKAN UNTUK PREVIEW.PY)
# ==========================================
INTEREST_LABELS = {
    "int_adult": "🔞 Adult Content", "int_flirt": "🔥 Flirt & Dirty Talk", "int_rel": "❤️ Relationship",
    "int_net": "🤝 Networking", "int_game": "🎮 Gaming", "int_travel": "✈️ Traveling", "int_coffee": "☕ Coffee & Chill"
}

def get_readable_interests(interests_str: str) -> str:
    """Mengubah kode minat menjadi teks yang cantik untuk ditampilkan"""
    if not interests_str: return "Belum memilih minat."
    return ", ".join([INTEREST_LABELS.get(code.strip(), code.strip()) for code in interests_str.split(",")])

# ==========================================
# 1. KONFIGURASI MENU & KEYBOARD UTAMA
# ==========================================
def get_main_menu():
    kb = [[KeyboardButton(text="📱 DASHBOARD UTAMA")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, is_persistent=True)

def get_dashboard_kb(inbox_count=0, notif_count=0):
    """Fungsi yang sudah di-upgrade untuk menerima angka notifikasi dinamis"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌎 DISCOVERY", callback_data="menu_discovery"),
         InlineKeyboardButton(text="🎭 FEED ANONIM", callback_data="menu_feed")],
         
        # --- MENU PESAN (INBOX) & NOTIFIKASI SUDAH DIPISAH ---
        [InlineKeyboardButton(text=f"📥 PESAN ({inbox_count})", callback_data="menu_inbox"), 
         InlineKeyboardButton(text=f"🔔 NOTIFIKASI ({notif_count})", callback_data="menu_notifications")],
         
        [InlineKeyboardButton(text="⚙️ PROFIL SAYA", callback_data="menu_profile"),
         InlineKeyboardButton(text="🛒 TOP UP & UPGRADE", callback_data="menu_pricing")],
         
        [InlineKeyboardButton(text="🎁 UNDANG TEMAN", callback_data="menu_referral"),
         InlineKeyboardButton(text="📊 STATUS & KUOTA", callback_data="menu_status")],
         
        [InlineKeyboardButton(text="💰 WITHDRAW", callback_data="menu_withdraw")]
    ])

# ==========================================
# 2. HANDLER UTAMA (/start & Tombol Dashboard)
# ==========================================
@router.message(CommandStart())
@router.message(F.text == "📱 DASHBOARD UTAMA")
@router.message(F.text == "📱 HOME PickMe")
async def command_start_handler(message: types.Message, command: CommandObject = None, db: DatabaseService = None, bot: Bot = None, state: FSMContext = None):
    if state:
        await state.clear()
        
    args = command.args if command else None 
    user_id = message.from_user.id 

    # --- A. GATEKEEPER ASLI V5 (Pengecekan Channel & Grup) ---
    from handlers.registration import check_membership, CHANNEL_LINK, GROUP_LINK
    
    is_joined = await check_membership(bot, user_id)
    if not is_joined:
        kb_join = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Join Channel Feed PickMe", url=f"https://t.me/{CHANNEL_LINK}")],
            [InlineKeyboardButton(text="👥 Join Grup PickMe", url=f"https://t.me/{GROUP_LINK}")],
            [InlineKeyboardButton(text="✅ SAYA SUDAH JOIN", callback_data="check_join_start")]
        ])
        
        text_stop = (
            "<b>STOP! Join Dulu ya Guys!!!</b> ✋\n\n"
            "Untuk menjaga kualitas komunitas, kamu wajib bergabung di Channel dan Grup kami "
            "sebelum bisa beraksi di PickMe.\n\n"
            "<i>Silakan bergabung kembali melalui tombol di bawah:</i>"
        )
        return await message.answer_photo(photo=BANNER_PHOTO_ID, caption=text_stop, reply_markup=kb_join, parse_mode="HTML")

    user = await db.get_user(user_id)
    
    # --- B. USER BARU: Arahkan ke Registrasi ---
    if not user:
        from handlers.registration import RegState
        text_new = (
            "👋 <b>Selamat Datang di PickMe Bot!</b>\n\n"
            "Mari buat profil singkatmu sekarang!\n"
            "Siapa <b>nama panggilanmu(username)</b>? (3-15 karakter)"
        )
        await message.answer(text_new, parse_mode="HTML")
        return await state.set_state(RegState.waiting_nickname)

    # --- C. ROUTER DEEP LINK ---
    if args and args.startswith("view_"):
        parts = args.split("_")
        try: 
            target_id = int(parts[1])
            origin_type = parts[2] if len(parts) >= 3 else "public" 
            from handlers.preview import process_profile_preview
            return await process_profile_preview(message, bot, db, viewer_id=user_id, target_id=target_id, context_source=origin_type)
        except Exception as e:
            logging.error(f"Error Deep Link Routing: {e}")
            return await message.answer("⚠️ Gagal memuat profil. Format link tidak valid atau ada kendala sistem.")

    # --- D. TAMPILKAN DASHBOARD UTAMA ---
    kasta = "💎 VIP+" if user.is_vip_plus else "🌟 VIP" if user.is_vip else "🎭 TALENT" if user.is_premium else "👤 FREE"
    
    dashboard_text = (
        f"👋 Halo, <b>{user.full_name.upper()}</b>!\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"👑 Status: <b>{kasta}</b>\n"
        f"💰 Saldo: <b>{user.poin_balance:,} Poin</b>\n"
        f"📍 Lokasi: <b>{user.location_name}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>"
    )

    # Mengambil angka notifikasi dari database sebelum merender keyboard
    unreads = await db.get_all_unread_counts(user_id)
    count_inbox = unreads.get('inbox', 0)
    count_notif = unreads.get('unmask', 0) + unreads.get('view', 0)

    try:
        await message.answer_photo(photo=BANNER_PHOTO_ID, caption=dashboard_text, reply_markup=get_dashboard_kb(count_inbox, count_notif), parse_mode="HTML")
    except Exception as e:
        logging.error(f"Gagal kirim foto dashboard: {e}")
        await message.answer(dashboard_text, reply_markup=get_dashboard_kb(count_inbox, count_notif), parse_mode="HTML")

# ==========================================
# 3. HANDLER CALLBACK (Navigasi Mulus)
# ==========================================
@router.callback_query(F.data == "check_join_start")
async def verify_join_start(callback: types.CallbackQuery, bot: Bot, db: DatabaseService, state: FSMContext):
    from handlers.registration import check_membership
    if await check_membership(bot, callback.from_user.id):
        try: await callback.message.delete()
        except: pass
        from collections import namedtuple
        DummyCommand = namedtuple('CommandObject', ['args'])
        return await command_start_handler(callback.message, DummyCommand(args=None), db, bot, state)
    else:
        await callback.answer("❌ Kamu belum join Channel/Grup!", show_alert=True)

@router.callback_query(F.data == "back_to_dashboard")
async def back_to_dashboard(callback: types.CallbackQuery, db: DatabaseService, bot: Bot, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        return await callback.answer("❌ Sesi berakhir. Ketik /start kembali.", show_alert=True)

    kasta = "💎 VIP+" if user.is_vip_plus else "🌟 VIP" if user.is_vip else "🎭 TALENT" if user.is_premium else "👤 FREE"
    dashboard_text = (
        f"👋 Halo, <b>{user.full_name.upper()}</b>!\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"👑 Status: <b>{kasta}</b>\n"
        f"💰 Saldo: <b>{user.poin_balance:,} Poin</b>\n"
        f"📍 Lokasi: <b>{user.location_name}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>"
    )

    # Mengambil angka notifikasi dari database sebelum merender keyboard
    unreads = await db.get_all_unread_counts(user_id)
    count_inbox = unreads.get('inbox', 0)
    count_notif = unreads.get('unmask', 0) + unreads.get('view', 0)

    media = InputMediaPhoto(media=BANNER_PHOTO_ID, caption=dashboard_text, parse_mode="HTML")
    
    try:
        await callback.message.edit_media(media=media, reply_markup=get_dashboard_kb(count_inbox, count_notif))
    except Exception as e:
        try: await callback.message.delete()
        except: pass
        await bot.send_photo(chat_id=user_id, photo=BANNER_PHOTO_ID, caption=dashboard_text, reply_markup=get_dashboard_kb(count_inbox, count_notif), parse_mode="HTML")
    
    await callback.answer()
