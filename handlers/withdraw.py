import os
import uuid
import html
import logging
import asyncio
from datetime import datetime
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from services.database import DatabaseService, User, PointLog

router = Router()

BANNER_PHOTO_ID = "AgACAgUAAxkBAAIKUmm-3V96dh0wXlEwKgR9cZYxQJ7IAAJWEWsb5Sz5VRdAhJBTFWieAQADAgADeAADOgQ"

# --- KONFIGURASI KURS (10 Poin = Rp 1) ---
POIN_TO_IDR_RATE = 0.1  # 1 Poin = Rp 0.1

def get_int_id(key: str):
    val = os.getenv(key)
    if val and (val.startswith("-") or val.isdigit()):
        try: return int(val)
        except: return val
    return val

FINANCE_GROUP_ID = get_int_id("FINANCE_GROUP_ID")

class WithdrawState(StatesGroup):
    waiting_amount = State()
    waiting_wallet_type = State()
    waiting_wallet_number = State()
    waiting_wallet_name = State()

# --- 1. DASHBOARD PENGHASILAN (SULTAN UX) ---
@router.callback_query(F.data == "menu_withdraw")
async def show_earnings_dashboard(callback: types.CallbackQuery, db: DatabaseService, state: FSMContext):
    await state.clear()
    user = await db.get_user(callback.from_user.id)
    
    saldo_rp = int(user.poin_balance * POIN_TO_IDR_RATE)
    min_wd_rp = 50000 if user.has_withdrawn_before else 20000
    min_wd_poin = int(min_wd_rp / POIN_TO_IDR_RATE)
    
    is_eligible_for_wd = user.is_premium

    text = (
        f"💰 <b>PUSAT PENGHASILAN TALENT</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"<b>💎 SALDO AKTIF ANDA:</b>\n"
        f"🪙 Poin: <b>{user.poin_balance:,} Poin</b>\n"
        f"💵 Estimasi: <b>Rp {saldo_rp:,}</b>\n\n"
        
        f"<b>📊 RINCIAN PENDAPATAN:</b>\n"
        f"• Profil Dilihat: <b>+100 Poin</b>\n"
        f"• Pesan Masuk: <b>+100 Poin</b>\n"
        f"🎁 <b>Bonus Balas Chat:</b> <b>+200 Poin</b>\n"
        f"• Unmask Profil: <b>+500 Poin</b>\n"
        f"🎁 <b>Bonus Balas Unmask:</b> <b>+500 Poin</b>\n\n"
        
        f"<b>🏧 ATURAN PENCAIRAN (WD):</b>\n"
        f"💸 Kurs: <b>10 Poin = Rp 1</b>\n"
        f"• Minimal WD: <b>Rp {min_wd_rp:,}</b> ({min_wd_poin:,} Poin)\n"
        f"• Estimasi Cair: 1x24 Jam Kerja\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
    )

    kb = []
    if is_eligible_for_wd:
        if user.poin_balance >= min_wd_poin:
            kb.append([InlineKeyboardButton(text="💸 TARIK SALDO SEKARANG", callback_data="wd_start")])
        else:
            text += f"⚠️ <i>Saldo belum mencapai minimal penarikan. Balas pesan Sultan untuk mengklaim bonus poin tambahan!</i>"
    else:
        text += "🔒 <b>AKSES TERKUNCI</b>\n<i>Hanya akun status Talent atau VIP yang dapat mencairkan poin menjadi uang tunai.</i>"
        kb.append([InlineKeyboardButton(text="💎 UPGRADE TALENT SEKARANG", callback_data="menu_pricing")])

    kb.append([InlineKeyboardButton(text="🏠 KEMBALI KE DASHBOARD", callback_data="back_to_dashboard")])

    # SULTAN UX: Seamless Transition
    try:
        await callback.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        try: await callback.message.delete()
        except: pass
        await callback.message.answer_photo(photo=BANNER_PHOTO_ID, caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
        
    await callback.answer()

# --- 2. MULAI PROSES WITHDRAW (INPUT POIN) ---
@router.callback_query(F.data == "wd_start")
async def start_withdraw(callback: types.CallbackQuery, db: DatabaseService, state: FSMContext):
    user = await db.get_user(callback.from_user.id)
    min_wd_rp = 50000 if user.has_withdrawn_before else 20000
    min_wd_poin = int(min_wd_rp / POIN_TO_IDR_RATE)

    text = (
        f"💸 <b>PENCAIRAN SALDO</b>\n\n"
        f"Saldo Aktif: <b>{user.poin_balance:,} Poin</b>\n"
        f"Minimal Tarik: <b>{min_wd_poin:,} Poin</b>\n\n"
        f"✍️ <i>Ketik nominal angka <b>POIN</b> yang ingin ditarik (tanpa titik/koma):</i>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ BATAL", callback_data="menu_withdraw")]])
    
    # SULTAN UX: Edit Caption
    try: await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    except: await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    
    await state.set_state(WithdrawState.waiting_amount)
    await callback.answer()

# --- 3. VALIDASI NOMINAL ---
@router.message(WithdrawState.waiting_amount)
async def process_wd_amount(message: types.Message, state: FSMContext, db: DatabaseService):
    if not message.text.isdigit():
        return await message.answer("⚠️ Format Salah! Masukkan angka poin saja tanpa titik/koma.")
        
    amount_poin = int(message.text)
    user = await db.get_user(message.from_user.id)
    
    min_wd_rp = 50000 if user.has_withdrawn_before else 20000
    min_wd_poin = int(min_wd_rp / POIN_TO_IDR_RATE)

    # Sapu pesan user agar chat bersih
    try: await message.delete()
    except: pass

    if amount_poin < min_wd_poin:
        return await message.answer(f"⚠️ Minimal penarikan adalah <b>{min_wd_poin:,} Poin</b>. Ketik ulang nominal yang benar:")
    if amount_poin > user.poin_balance:
        return await message.answer(f"⚠️ Saldo poin tidak mencukupi. Maksimal: <b>{user.poin_balance:,} Poin</b>. Ketik ulang:")

    amount_rp = int(amount_poin * POIN_TO_IDR_RATE)
    await state.update_data(wd_amount_poin=amount_poin, wd_amount_rp=amount_rp)
    
    kb = [
        [InlineKeyboardButton(text="🔵 DANA", callback_data="wd_wallet_DANA"), InlineKeyboardButton(text="🟢 GOPAY", callback_data="wd_wallet_GOPAY")],
        [InlineKeyboardButton(text="🟣 OVO", callback_data="wd_wallet_OVO"), InlineKeyboardButton(text="🟠 SHOPEEPAY", callback_data="wd_wallet_SHOPEEPAY")],
        [InlineKeyboardButton(text="🏦 TRANSFER BANK", callback_data="wd_wallet_BANK")],
        [InlineKeyboardButton(text="❌ BATAL", callback_data="menu_withdraw")]
    ]
    
    text = (
        f"✅ <b>KONFIRMASI NOMINAL</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"Poin Ditarik: <b>{amount_poin:,} Poin</b>\n"
        f"Uang Diterima: <b>Rp {amount_rp:,}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"
        f"👇 <i>Pilih tujuan bank/e-wallet pencairan dana Anda:</i>"
    )
    
    # Refresh dashboard dengan teks baru
    from collections import namedtuple
    Dummy = namedtuple('CallbackQuery', ['from_user', 'message', 'answer'])
    dummy_cb = Dummy(from_user=message.from_user, message=message, answer=lambda *a, **k: asyncio.sleep(0))
    await show_earnings_dashboard(dummy_cb, db, state) # Panggil menu utama untuk reset
    
    # Lalu kirim instruksi dompet (terpaksa kirim baru karena edit_caption di atas sudah hilang pesannya)
    await message.answer_photo(photo=BANNER_PHOTO_ID, caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await state.set_state(WithdrawState.waiting_wallet_type)

# --- 4. INPUT DETAIL REKENING ---
@router.callback_query(F.data.startswith("wd_wallet_"), WithdrawState.waiting_wallet_type)
async def process_wallet_type(callback: types.CallbackQuery, state: FSMContext):
    wallet_type = callback.data.split("_")[2]
    await state.update_data(wd_wallet_type=wallet_type)
    
    label = "Nama Bank & No Rekening" if wallet_type == "BANK" else "Nomor Handphone"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ BATAL", callback_data="menu_withdraw")]])
    
    text = f"💳 Metode Pencairan: <b>{wallet_type}</b>\n\n✍️ Ketik <b>{label}</b> Anda di bawah ini:"
    
    try: await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    except: pass
    
    await state.set_state(WithdrawState.waiting_wallet_number)
    await callback.answer()

@router.message(WithdrawState.waiting_wallet_number)
async def process_wallet_number(message: types.Message, state: FSMContext, db: DatabaseService):
    await state.update_data(wd_wallet_number=message.text)
    
    try: await message.delete()
    except: pass
    
    user = await db.get_user(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ BATAL", callback_data="menu_withdraw")]])
    text = "👤 Ketik <b>Nama Lengkap</b> Anda (Harus sesuai dengan nama di rekening/e-wallet agar tidak gagal transfer):"
    
    await message.answer_photo(photo=BANNER_PHOTO_ID, caption=text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(WithdrawState.waiting_wallet_name)

# --- 5. FINISH & NOTIF ADMIN ---
@router.message(WithdrawState.waiting_wallet_name)
async def process_wallet_name(message: types.Message, state: FSMContext, db: DatabaseService, bot: Bot):
    await state.update_data(wd_wallet_name=message.text)
    data = await state.get_data()
    
    try: await message.delete()
    except: pass
    
    user_id = message.from_user.id
    trx_id = f"WD-{uuid.uuid4().hex[:6].upper()}"
    user = await db.get_user(user_id)
    
    # 1. Simpan Request ke DB dan Potong Poin Langsung (Transaksional AMAN)
    async with db.session_factory() as session:
        u = await session.get(User, user_id)
        u.poin_balance -= data['wd_amount_poin']
        u.has_withdrawn_before = True 
        session.add(PointLog(user_id=user_id, amount=-data['wd_amount_poin'], source=f"Withdraw {trx_id}"))
        await session.commit()

    # 2. Kirim Struk ke Grup Admin Finance
    admin_text = (
        f"🟡 <b>REQ WITHDRAW BARU</b>\n"
        f"ID: <code>{trx_id}</code>\n"
        f"User: <code>{user_id}</code>\n"
        f"Nominal: <b>Rp {data['wd_amount_rp']:,}</b>\n"
        f"Poin Ditarik: {data['wd_amount_poin']:,}\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"💳 {data['wd_wallet_type']}: <code>{data['wd_wallet_number']}</code>\n"
        f"👤 A/N: {html.escape(data['wd_wallet_name'])}"
    )
    
    kb_admin = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ TANDAI SUDAH DITRANSFER", callback_data=f"wd_confirm_{user_id}_{trx_id}")],
        [InlineKeyboardButton(text="❌ TOLAK & REFUND POIN", callback_data=f"wd_deny_{user_id}_{trx_id}")]
    ])

    if FINANCE_GROUP_ID:
        try: await bot.send_message(FINANCE_GROUP_ID, admin_text, reply_markup=kb_admin, parse_mode="HTML")
        except: pass

    # 3. Kembalikan User ke Dashboard
    text_success = (
        f"✅ <b>PENARIKAN DANA BERHASIL DIAJUKAN!</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"ID Tiket: <code>{trx_id}</code>\n"
        f"Status: <b>Menunggu Transfer Admin</b>\n"
        f"Estimasi Cair: Maksimal 24 Jam Kerja.\n\n"
        f"<i>Poin Anda telah didebet. Terima kasih telah memeriahkan PickMe!</i>"
    )
    kb_success = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 KEMBALI KE DASHBOARD", callback_data="menu_withdraw")]])
    
    await message.answer_photo(photo=BANNER_PHOTO_ID, caption=text_success, reply_markup=kb_success, parse_mode="HTML")
    await state.clear()
