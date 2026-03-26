import os
import logging
from aiogram import Router, F, types, Bot
from aiogram.filters import Command 
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from services.database import DatabaseService

router = Router()

# --- 1. CONFIGURATION ---
FINANCE_GROUP_ID = os.getenv("FINANCE_GROUP_ID") 
CATALOG_PHOTO_ID = "AgACAgUAAxkBAAICm2m98Ci5YD2pZTbqYoJrShVgWSq9AAJvDGsbPyfwVfA9zs-0TS-oAQADAgADeQADOgQ" 

# ==========================================
# 2. HELPER FUNCTION: KONTEN TOKO
# ==========================================
def get_store_content():
    """Menyediakan teks dan keyboard katalog agar tidak perlu diketik berulang"""
    text = (
        "🛒 <b>PICKME STORE - KATALOG RESMI</b>\n"
        f"<code>{'—' * 22}</code>\n"
        "Buka fitur sakti dan jadilah Sultan di PickMe!\n\n"
        "💡 <b>TRIAL GRATIS TERSEDIA:</b>\n"
        "Selama masa integrasi Midtrans, semua paket di bawah ini bisa kamu coba secara <b>GRATIS selama 7 Hari</b>!\n\n"
        "<i>Silakan pilih paket untuk melihat detail fitur.</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌟 PAKET VIP", callback_data="p_info_vip")],
        [InlineKeyboardButton(text="💎 PAKET VIP+ (Sultan Eksklusif)", callback_data="p_info_vipplus")],
        [
            InlineKeyboardButton(text="🎭 TALENT", callback_data="p_info_talent"),
            InlineKeyboardButton(text="🚀 BOOST", callback_data="p_info_boost")
        ],
        [InlineKeyboardButton(text="🏠 KEMBALI KE DASHBOARD", callback_data="back_to_dashboard")]
    ])
    
    return text, kb

# ==========================================
# 3. HANDLER PERINTAH /pricing (DARI MENU KOTAK BIRU)
# ==========================================
@router.message(Command("pricing"))
async def pricing_command_handler(message: types.Message, bot: Bot):
    text, kb = get_store_content()
    
    # Hapus pesan perintah "/pricing" dari user agar obrolan rapi
    try: await message.delete()
    except: pass
    
    await message.answer_photo(photo=CATALOG_PHOTO_ID, caption=text, reply_markup=kb, parse_mode="HTML")

# ==========================================
# 4. HANDLER CALLBACK (DARI DASHBOARD SULTAN UX)
# ==========================================
@router.callback_query(F.data == "menu_pricing")
async def show_pricing_store(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    text, kb = get_store_content()
    
    # SULTAN UX: Ubah foto profil menjadi foto katalog secara instan (Seamless Media Swap)
    media = InputMediaPhoto(media=CATALOG_PHOTO_ID, caption=text, parse_mode="HTML")
    try:
        await callback.message.edit_media(media=media, reply_markup=kb)
    except Exception:
        # Fallback jika terjadi error
        try: await callback.message.delete()
        except: pass
        await callback.message.answer_photo(photo=CATALOG_PHOTO_ID, caption=text, reply_markup=kb, parse_mode="HTML")
        
    await callback.answer()

# ==========================================
# 5. POP-UP INFO JACKPOT TRIAL
# ==========================================
@router.callback_query(F.data.startswith("p_info_"))
async def show_trial_offer(callback: types.CallbackQuery):
    text = (
        "💎 <b>PROGRAM VIP+ JACKPOT (TRIAL)</b>\n"
        f"<code>{'—' * 22}</code>\n"
        "Kabar gembira! Kami memberikan akses <b>VIP+ EKSKLUSIF</b> secara gratis untuk setiap pengajuan uji coba.\n\n"
        "🔥 <b>Fitur VIP+ yang akan kamu dapatkan:</b>\n"
        "• 🔓 <b>Unmask Aktif:</b> Bongkar semua identitas anonim.\n"
        "• 💬 <b>Chat Maksimal:</b> Kuota kirim pesan paling tinggi.\n"
        "• ⚡ <b>Prioritas:</b> Profilmu muncul paling depan di Discovery.\n\n"
        "🎁 <b>Ajukan akses VIP+ 7 Hari sekarang juga!</b>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 AJUKAN TRIAL VIP+ (GRATIS)", callback_data="req_trial_vipplus_trial")],
        [InlineKeyboardButton(text="🔙 KEMBALI KE TOKO", callback_data="menu_pricing")]
    ])
    
    # SULTAN UX: Edit caption, biarkan gambar katalog tetap di atas
    try:
        await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    except:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# ==========================================
# 6. KIRIM PENGAJUAN KE GRUP ADMIN FINANCE
# ==========================================
@router.callback_query(F.data.startswith("req_trial_"))
async def send_to_admin_group(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    username = f"@{callback.from_user.username}" if callback.from_user.username else "No Username"
    
    text_success = (
        "✅ <b>PENGAJUAN BERHASIL!</b>\n\n"
        "Permintaan akses <b>VIP+ Trial</b> kamu sudah masuk ke tim Finance.\n"
        "Mohon tunggu notifikasi selanjutnya. Akunmu akan aktif otomatis jika disetujui Admin."
    )
    kb_success = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 KEMBALI", callback_data="back_to_dashboard")]])
    
    # Hapus gambar katalog untuk menampilkan struk sukses yang rapi
    try:
        await callback.message.delete()
        await callback.message.answer(text_success, reply_markup=kb_success, parse_mode="HTML")
    except: pass

    admin_text = (
        f"🎁 <b>REQUEST TRIAL VIP+ (BETA)</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"User: <b>{callback.from_user.full_name}</b>\n"
        f"ID: <code>{user_id}</code>\n"
        f"Username: {username}\n"
        f"Paket: <b>VIP+ (7 HARI TRIAL)</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"👇 Admin silakan berikan akses Sultan:"
    )

    kb_admin = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ SETUJUI VIP+ (7 HARI)", callback_data=f"trial_apv_{user_id}_vipplus")],
        [InlineKeyboardButton(text="❌ TOLAK", callback_data=f"trial_rej_{user_id}")]
    ])

    if FINANCE_GROUP_ID:
        try:
            await bot.send_message(FINANCE_GROUP_ID, admin_text, reply_markup=kb_admin, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Gagal kirim ke grup finance: {e}")
            
    await callback.answer("Pengajuan Terkirim!", show_alert=True)
