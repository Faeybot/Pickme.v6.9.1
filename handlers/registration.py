import re
import asyncio
import os
import html
import logging
import datetime
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, 
    InlineKeyboardMarkup, InlineKeyboardButton
)
from geopy.geocoders import Nominatim
from services.database import DatabaseService, User, PointLog, ReferralTracking

router = Router()
geolocator = Nominatim(user_agent="pickme_bot_v6_final")

# --- 1. CONFIGURATION & ID CLEANING ---
def get_clean_id(key: str):
    val = os.getenv(key)
    if not val:
        logging.error(f"⚠️ Variabel {key} KOSONG di Railway!")
        return None
    val = str(val).strip().replace("'", "").replace('"', '')
    if val.startswith("-") or val.isdigit():
        try: return int(val)
        except: return val
    if not val.startswith("@"): return f"@{val}"
    return val

ADMIN_LOG_CHANNEL = get_clean_id("ADMIN_LOG_CHANNEL") 
REG_MODERATION_GROUP = get_clean_id("REG_MODERATION_GROUP") # Grup khusus klik Approve/Reject
GROUP_ID = get_clean_id("GROUP_ID")
CHANNEL_ID = get_clean_id("CHANNEL_ID")

GROUP_LINK = os.getenv("GROUP_LINK", "").replace("@", "").replace("https://t.me/", "")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "").replace("@", "").replace("https://t.me/", "")
BANNER_PHOTO_ID = os.getenv("BANNER_PHOTO_ID", "AgACAgUAAxkBAAIKUmm-3V96dh0wXlEwKgR9cZYxQJ7IAAJWEWsb5Sz5VRdAhJBTFWieAQADAgADeAADOgQ")
DEFAULT_ANON_PHOTO_ID = os.getenv("DEFAULT_ANON_PHOTO_ID", BANNER_PHOTO_ID) # Nanti isi dengan ID Foto Logo Anonim PickMe

# --- DAFTAR 15 KOTA BARU ---
CITY_DATA = {
    "city_medan": {"name": "Medan", "lat": 3.5952, "lng": 98.6722, "tag": "MEDAN"},
    "city_plm": {"name": "Palembang", "lat": -2.9761, "lng": 104.7754, "tag": "PALEMBANG"},
    "city_lamp": {"name": "Lampung", "lat": -5.3971, "lng": 105.2668, "tag": "LAMPUNG"},
    "city_btm": {"name": "Batam", "lat": 1.1301, "lng": 104.0529, "tag": "BATAM"},
    "city_jkt": {"name": "Jakarta", "lat": -6.2088, "lng": 106.8456, "tag": "JAKARTA"},
    "city_bks": {"name": "Bekasi", "lat": -6.2383, "lng": 106.9756, "tag": "BEKASI"},
    "city_bgr": {"name": "Bogor", "lat": -6.5971, "lng": 106.8060, "tag": "BOGOR"},
    "city_bdg": {"name": "Bandung", "lat": -6.9175, "lng": 107.6191, "tag": "BANDUNG"},
    "city_jgj": {"name": "Jogja", "lat": -7.7956, "lng": 110.3695, "tag": "JOGJA"},
    "city_smr": {"name": "Semarang", "lat": -6.9667, "lng": 110.4167, "tag": "SEMARANG"},
    "city_slo": {"name": "Solo", "lat": -7.5707, "lng": 110.8214, "tag": "SOLO"},
    "city_sby": {"name": "Surabaya", "lat": -7.2575, "lng": 112.7521, "tag": "SURABAYA"},
    "city_mlg": {"name": "Malang", "lat": -7.9666, "lng": 112.6326, "tag": "MALANG"},
    "city_dps": {"name": "Denpasar", "lat": -8.6705, "lng": 115.2126, "tag": "BALI"},
    "city_lmbk": {"name": "Lombok", "lat": -8.5833, "lng": 116.1167, "tag": "LOMBOK"},
}

class RegState(StatesGroup):
    waiting_rules = State()
    waiting_nickname = State()
    waiting_birth_month = State()
    waiting_birth_day = State()
    waiting_birth_year = State()
    waiting_gender = State()
    waiting_interests = State() 
    waiting_location = State()
    waiting_photo_1 = State()
    waiting_photo_2 = State()
    waiting_photo_3 = State()
    waiting_about = State()

# --- HELPER: KEYBOARD TANGGAL LAHIR ---
def get_month_kb():
    months = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agt", "Sep", "Okt", "Nov", "Des"]
    kb, row = [], []
    for i in range(12):
        row.append(InlineKeyboardButton(text=months[i], callback_data=f"reg_month_{i+1}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_day_kb(month: int):
    days_in_month = 31
    if month == 2: days_in_month = 29
    elif month in [4, 6, 9, 11]: days_in_month = 30

    kb, row = [], []
    for d in range(1, days_in_month + 1):
        row.append(InlineKeyboardButton(text=str(d), callback_data=f"reg_day_{d}"))
        if len(row) == 5:
            kb.append(row)
            row = []
    if row: kb.append(row)
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- 2. HELPER: CEK MEMBERSHIP ---
async def check_membership(bot: Bot, user_id: int):
    try:
        member_ch = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        stat_ch = getattr(member_ch.status, "value", str(member_ch.status)).lower()
        if stat_ch in ['left', 'kicked', 'banned']: return False

        member_gr = await bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        stat_gr = getattr(member_gr.status, "value", str(member_gr.status)).lower()
        if stat_gr in ['left', 'kicked', 'banned']: return False

        return True
    except Exception as e:
        logging.error(f"❌ Error check_membership: {e}")
        return False

# --- 3. START & AUTOMATIC BYPASS ---
@router.message(F.text.startswith("/start"))
async def cmd_start(message: types.Message, bot: Bot, db: DatabaseService, state: FSMContext):
    await state.clear()
    
    args = message.text.split()[1] if len(message.text.split()) > 1 else None
    if args and args.startswith("ref_"):
        try: 
            ref_id = int(args.split("_")[1])
            await state.update_data(referrer_id=ref_id)
        except: pass

    user = await db.get_user(message.from_user.id)
    if user:
        from handlers.start import command_start_handler
        from collections import namedtuple
        DummyCommand = namedtuple('CommandObject', ['args'])
        return await command_start_handler(message, DummyCommand(args=args), db, bot, state)

    is_joined = await check_membership(bot, message.from_user.id)
    if not is_joined:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Join Channel Feed PickMe", url=f"https://t.me/{CHANNEL_LINK}")],
            [InlineKeyboardButton(text="👥 Join Grup PickMe", url=f"https://t.me/{GROUP_LINK}")],
            [InlineKeyboardButton(text="✅ SAYA SUDAH JOIN", callback_data="check_join_reg")]
        ])
        text = "<b>STOP! Join dulu ya Guys!!!</b> ✋\n\nSilakan bergabung di Channel dan Grup untuk mendaftar di PickMe."
        return await message.answer_photo(photo=BANNER_PHOTO_ID, caption=text, reply_markup=kb, parse_mode="HTML")

    await show_rules_handler(message)
    await state.set_state(RegState.waiting_rules)

async def show_rules_handler(message: types.Message):
    text_rules = (
        "📜 <b>PICKME COMMUNITY RULES</b>\n"
        f"<code>{'—' * 20}</code>\n"
        "1. Minimal usia pendaftaran adalah <b>18 Tahun</b>.\n"
        "2. Dilarang melakukan penipuan, spam, atau SARA.\n"
        "3. Konten 18+ 🔞 DIPERBOLEHKAN selama berlabel dan konsensual.\n"
        "4. PickMe tidak bertanggung jawab atas transaksi di luar bot.\n"
        "5. Pelanggaran aturan berakibat <b>Banned Permanen</b>.\n\n"
        "<b>DISCLAIMER:</b> Dengan melanjutkan, Anda menyatakan telah dewasa (18+)."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ SAYA SETUJU & LANJUT", callback_data="accept_rules")]])
    try: await message.answer_photo(photo=BANNER_PHOTO_ID, caption=text_rules, reply_markup=kb, parse_mode="HTML")
    except: await message.answer(text_rules, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "check_join_reg")
async def verify_join_reg(callback: types.CallbackQuery, bot: Bot, db: DatabaseService, state: FSMContext):
    if await check_membership(bot, callback.from_user.id):
        user = await db.get_user(callback.from_user.id)
        if user:
            from handlers.start import command_start_handler
            from collections import namedtuple
            DummyCommand = namedtuple('CommandObject', ['args'])
            await callback.message.delete()
            return await command_start_handler(callback.message, DummyCommand(args=None), db, bot, state)
        
        await callback.message.delete()
        await show_rules_handler(callback.message)
        await state.set_state(RegState.waiting_rules)
    else:
        await callback.answer("❌ Kamu belum join Channel/Grup!", show_alert=True)

# --- 4. ALUR BIODATA & KALENDER USIA ---
@router.callback_query(F.data == "accept_rules", RegState.waiting_rules)
async def rules_accepted(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Siapa <b>nama panggilanmu (Username)</b>? (3-15 karakter)", parse_mode="HTML")
    await state.set_state(RegState.waiting_nickname)

@router.message(RegState.waiting_nickname)
async def process_name(message: types.Message, state: FSMContext):
    if not message.text or not (3 <= len(message.text) <= 15): return await message.answer("⚠️ Nama 3-15 karakter.")
    await state.update_data(nickname=message.text)
    
    text = f"Halo {message.text}! Silakan pilih <b>Bulan Lahirmu</b>:\n\n<i>Info: Data ulang tahun tidak akan ditampilkan ke publik, ini hanya digunakan untuk menghitung usiamu.</i>"
    await message.answer(text, reply_markup=get_month_kb(), parse_mode="HTML")
    await state.set_state(RegState.waiting_birth_month)

@router.callback_query(F.data.startswith("reg_month_"), RegState.waiting_birth_month)
async def process_month(callback: types.CallbackQuery, state: FSMContext):
    month = int(callback.data.split("_")[2])
    await state.update_data(birth_month=month)
    await callback.message.edit_text("Pilih <b>Tanggal Lahirmu</b>:", reply_markup=get_day_kb(month), parse_mode="HTML")
    await state.set_state(RegState.waiting_birth_day)

@router.callback_query(F.data.startswith("reg_day_"), RegState.waiting_birth_day)
async def process_day(callback: types.CallbackQuery, state: FSMContext):
    day = int(callback.data.split("_")[2])
    await state.update_data(birth_day=day)
    await callback.message.edit_text("Terakhir, balas pesan ini dengan <b>Tahun Lahirmu</b> (4 angka).\nContoh: <code>2002</code>", parse_mode="HTML")
    await state.set_state(RegState.waiting_birth_year)

@router.message(RegState.waiting_birth_year)
async def process_year(message: types.Message, state: FSMContext):
    year_str = message.text.strip()
    if not year_str.isdigit() or len(year_str) != 4:
        return await message.answer("⚠️ Masukkan 4 angka tahun lahir. Contoh: 2002")
    
    year = int(year_str)
    data = await state.get_data()
    month, day = data['birth_month'], data['birth_day']

    try:
        dob = datetime.date(year, month, day)
    except ValueError:
        return await message.answer("⚠️ Tanggal lahir tidak valid (misal: 29 Februari di tahun yang salah). Silakan tekan /start untuk mengulang.")

    today = datetime.date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    if age < 18:
        await state.clear()
        return await message.answer("❌ Maaf, PickMe hanya untuk user berusia 18 tahun ke atas.")
    if age > 60:
        await state.clear()
        return await message.answer("⚠️ Usia maksimal pendaftaran adalah 60 tahun.")

    await state.update_data(age=age, dob_str=dob.strftime("%Y-%m-%d"))
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Pria"), KeyboardButton(text="Wanita")]], resize_keyboard=True, one_time_keyboard=True)
    await message.answer(f"✅ Usiamu tercatat: <b>{age} Tahun</b>.\n\nApa jenis kelaminmu?", reply_markup=kb, parse_mode="HTML")
    await state.set_state(RegState.waiting_gender)

@router.message(RegState.waiting_gender, F.text.in_(["Pria", "Wanita"]))
async def process_gender(message: types.Message, state: FSMContext):
    await state.update_data(gender=message.text, selected_interests=[])
    await show_interest_keyboard(message, [])
    await state.set_state(RegState.waiting_interests)

async def show_interest_keyboard(message: types.Message, selected: list, edit=False):
    interests = [
        ("🔞 Adult Content", "int_adult"), ("🔥 Flirt & Dirty Talk", "int_flirt"),
        ("❤️ Relationship", "int_rel"), ("🤝 Networking", "int_net"),
        ("🎮 Gaming", "int_game"), ("✈️ Traveling", "int_travel"), ("☕ Coffee & Chill", "int_coffee")
    ]
    kb_list = []
    for text, code in interests:
        prefix = "✅ " if code in selected else ""
        kb_list.append([InlineKeyboardButton(text=f"{prefix}{text}", callback_data=code)])
    
    if len(selected) > 0:
        kb_list.append([InlineKeyboardButton(text="➡️ SIMPAN & LANJUT", callback_data="save_interests")])
    
    text = "Pilih <b>Minat & Keinginanmu</b> (Maksimal 3):"
    if edit: await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list), parse_mode="HTML")
    else: await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list), parse_mode="HTML")

@router.callback_query(F.data.startswith("int_"), RegState.waiting_interests)
async def handle_interest_click(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_interests", [])
    code = callback.data
    
    if code in selected: selected.remove(code)
    elif len(selected) < 3: selected.append(code)
    else: return await callback.answer("Maksimal 3 pilihan!", show_alert=True)
    
    await state.update_data(selected_interests=selected)
    await show_interest_keyboard(callback.message, selected, edit=True)
    await callback.answer()

@router.callback_query(F.data == "save_interests", RegState.waiting_interests)
async def save_interests(callback: types.CallbackQuery, state: FSMContext):
    inline_kb_list, temp_row = [], []
    for code, info in CITY_DATA.items():
        temp_row.append(InlineKeyboardButton(text=info["name"], callback_data=code))
        if len(temp_row) == 3: 
            inline_kb_list.append(temp_row)
            temp_row = []
    if temp_row: inline_kb_list.append(temp_row)
    
    reply_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📍 Kirim Lokasi (GPS)", request_location=True)]], resize_keyboard=True)
    text = "📍 <b>PENGATURAN LOKASI</b>\nPilih kota domisilimu dari menu, atau gunakan deteksi GPS otomatis."
    await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kb_list), parse_mode="HTML")
    await callback.message.answer("Gunakan tombol ini untuk GPS otomatis:", reply_markup=reply_kb)
    await state.set_state(RegState.waiting_location)

@router.callback_query(F.data.startswith("city_"), RegState.waiting_location)
async def handle_manual_city(callback: types.CallbackQuery, state: FSMContext):
    city_info = CITY_DATA.get(callback.data)
    if city_info:
        await state.update_data(latitude=city_info["lat"], longitude=city_info["lng"], city=city_info["name"], city_hashtag=f"#{city_info['tag']}")
        await callback.message.answer(f"✅ Lokasi: <b>{city_info['name']}</b>\nKirim <b>Foto Utama</b>:", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
        await state.set_state(RegState.waiting_photo_1)

@router.message(RegState.waiting_location, F.location)
async def process_location(message: types.Message, state: FSMContext):
    lat, lon = message.location.latitude, message.location.longitude
    try:
        loop = asyncio.get_event_loop()
        loc = await loop.run_in_executor(None, lambda: geolocator.reverse((lat, lon), timeout=10))
        city = loc.raw['address'].get('city') or loc.raw['address'].get('town') or "Unknown"
    except: city = "Unknown"
    await state.update_data(latitude=lat, longitude=lon, city=city, city_hashtag=f"#{city.replace(' ','').upper()}")
    await message.answer(f"📍 Kota: {city}\nKirim <b>Foto Utama</b>:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(RegState.waiting_photo_1)

@router.message(RegState.waiting_photo_1, F.photo)
async def handle_photo_1(message: types.Message, state: FSMContext):
    await state.update_data(photo_1=message.photo[-1].file_id)
    await message.answer("📸 Foto disimpan! Kirim Foto ke-2 (Opsional) atau /skip:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Skip", callback_data="skip_photo")]]))
    await state.set_state(RegState.waiting_photo_2)

@router.message(RegState.waiting_photo_2, F.photo)
async def handle_photo_2(message: types.Message, state: FSMContext):
    await state.update_data(photo_2=message.photo[-1].file_id)
    await message.answer("📸 Foto ke-2 disimpan! Kirim Foto ke-3 atau /skip:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Skip", callback_data="skip_photo")]]))
    await state.set_state(RegState.waiting_photo_3)

@router.message(RegState.waiting_photo_3, F.photo)
async def handle_photo_3(message: types.Message, state: FSMContext):
    await state.update_data(photo_3=message.photo[-1].file_id)
    await message.answer("✅ Selesai! Sekarang tulis <b>Bio singkatmu</b>:")
    await state.set_state(RegState.waiting_about)

@router.callback_query(F.data == "skip_photo")
async def skip_photo(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Tulis <b>Bio singkatmu</b>:")
    await state.set_state(RegState.waiting_about)

# --- 7. FINISH & SAVE (TERMASUK BONUS REFERRAL) ---
@router.message(RegState.waiting_about)
async def finish_reg(message: types.Message, state: FSMContext, db: DatabaseService, bot: Bot):
    if not message.text or len(message.text) < 10: return await message.answer("⚠️ Bio minimal 10 karakter.")
    data = await state.get_data()
    user_id = message.from_user.id
    
    interests_str = ",".join(data['selected_interests'])
    extra_photos = [data[k] for k in ['photo_2', 'photo_3'] if k in data]
    referrer_id = data.get('referrer_id')
    poin_awal = 1000 if referrer_id else 0

    # Ekstraksi DOB untuk database
    try: dob_db = datetime.datetime.strptime(data['dob_str'], "%Y-%m-%d")
    except: dob_db = None

    try:
        async with db.session_factory() as session:
            new_user = User(
                id=user_id, full_name=data['nickname'], age=data['age'],
                gender=data['gender'], interests=interests_str, 
                latitude=data['latitude'], longitude=data['longitude'],
                location_name=data['city'], city_hashtag=data['city_hashtag'],
                bio=message.text, photo_id=data['photo_1'], extra_photos=extra_photos,
                daily_feed_text_quota=3, daily_feed_photo_quota=1, poin_balance=poin_awal
            )
            # Nanti setelah update database, kita tambahkan birth_date=dob_db ke atas
            session.add(new_user)
            
            if referrer_id:
                referrer = await session.get(User, referrer_id)
                if referrer:
                    referrer.poin_balance += 1000
                    session.add(PointLog(user_id=referrer.id, amount=1000, source=f"Referral Bonus (from {user_id})"))
                    session.add(PointLog(user_id=user_id, amount=1000, source=f"Welcome Bonus (referred by {referrer.id})"))
                    session.add(ReferralTracking(referrer_id=referrer.id, referred_id=user_id))
                    try: await bot.send_message(referrer.id, f"🎉 <b>TEMAN BARU BERGABUNG!</b>\n\n💰 Kamu dapat: <b>+1.000 Poin!</b>\n", parse_mode="HTML")
                    except: pass

            await session.commit()

        # JALUR 1: LOG KE CHANNEL ADMIN (ARSIP)
        try:
            if ADMIN_LOG_CHANNEL:
                log_txt = f"🆕 <b>USER BARU</b>\n👤 {data['nickname']} ({data['age']})\n👫 {data['gender']}\n🔥 {interests_str}"
                await bot.send_photo(ADMIN_LOG_CHANNEL, data['photo_1'], caption=log_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 PESAN", url=f"tg://user?id={user_id}")]]), parse_mode="HTML")
        except: pass

        # JALUR 2: LOG KE GRUP MODERASI (AKTIF)
        try:
            if REG_MODERATION_GROUP:
                mod_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ APPROVE", callback_data=f"mod_approve_{user_id}"),
                     InlineKeyboardButton(text="❌ REJECT PHOTO", callback_data=f"mod_reject_{user_id}")]
                ])
                mod_txt = f"🛡️ <b>MODERASI BARU</b>\n👤 {data['nickname']} ({data['age']})\n👫 {data['gender']}\n📝 {message.text[:50]}...\n\n<i>Mohon cek kelayakan foto profil ini.</i>"
                await bot.send_photo(REG_MODERATION_GROUP, data['photo_1'], caption=mod_txt, reply_markup=mod_kb, parse_mode="HTML")
        except: pass

        await state.clear()
        from handlers.start import command_start_handler, get_main_menu
        from collections import namedtuple
        await message.answer("🎉 Pendaftaran Berhasil!", reply_markup=get_main_menu())
        await command_start_handler(message, namedtuple('CommandObject',['args'])(args=None), db, bot, state)

    except Exception as e:
        logging.error(f"❌ DB Error: {e}")
        await message.answer("⚠️ Gagal menyimpan data pendaftaran.")

# ==========================================
# 8. HANDLER TOMBOL MODERASI GRUP
# ==========================================
@router.callback_query(F.data.startswith("mod_approve_"))
async def handle_mod_approve(callback: types.CallbackQuery):
    # Ubah pesan untuk menghapus tombol dan beri tanda approved
    admin_name = callback.from_user.first_name
    new_caption = f"{callback.message.caption}\n\n✅ <b>APPROVED</b> oleh {admin_name}"
    await callback.message.edit_caption(caption=new_caption, parse_mode="HTML")
    await callback.answer("Foto disetujui!", show_alert=False)

@router.callback_query(F.data.startswith("mod_reject_"))
async def handle_mod_reject(callback: types.CallbackQuery, db: DatabaseService, bot: Bot):
    user_id = int(callback.data.split("_")[2])
    admin_name = callback.from_user.first_name
    
    # 1. Reset foto ke default anonim di Database
    async with db.session_factory() as session:
        user = await session.get(User, user_id)
        if user:
            user.photo_id = DEFAULT_ANON_PHOTO_ID
            await session.commit()
            
    # 2. Kirim pesan peringatan ke user
    warn_msg = (
        "⚠️ <b>PERINGATAN KOMUNITAS</b>\n\n"
        "Foto profil kamu telah <b>ditolak/dihapus</b> oleh Admin karena melanggar aturan "
        "(Tampil vulgar, memakai seragam sekolah, atau pose tidak pantas).\n\n"
        "Profilmu saat ini direset menggunakan logo anonim. Silakan perbarui fotomu "
        "melalui menu <b>Profil Saya</b>."
    )
    try: await bot.send_message(user_id, warn_msg, parse_mode="HTML")
    except: pass

    # 3. Update pesan di grup moderasi
    new_caption = f"{callback.message.caption}\n\n❌ <b>REJECTED & RESET</b> oleh {admin_name}"
    await callback.message.edit_caption(caption=new_caption, parse_mode="HTML")
    await callback.answer("Foto ditolak dan profil direset!", show_alert=True)
