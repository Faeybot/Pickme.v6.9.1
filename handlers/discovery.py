import os
import math
import logging
import asyncio
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputMediaPhoto
from sqlalchemy import select, and_, not_, desc

from services.database import DatabaseService, User as UserTable, SwipeHistory
from services.notification import NotificationService

router = Router()
BANNER_PHOTO_ID = os.getenv("BANNER_PHOTO_ID", "AgACAgUAAxkBAAIKUmm-3V96dh0wXlEwKgR9cZYxQJ7IAAJWEWsb5Sz5VRdAhJBTFWieAQADAgADeAADOgQ")

CITY_DATA_DISC = {
    "city_disc_medan": {"name": "Medan", "lat": 3.5952, "lng": 98.6722, "tag": "MEDAN"},
    "city_disc_plm": {"name": "Palembang", "lat": -2.9761, "lng": 104.7754, "tag": "PALEMBANG"},
    "city_disc_lamp": {"name": "Lampung", "lat": -5.3971, "lng": 105.2668, "tag": "LAMPUNG"},
    "city_disc_btm": {"name": "Batam", "lat": 1.1301, "lng": 104.0529, "tag": "BATAM"},
    "city_disc_jkt": {"name": "Jakarta", "lat": -6.2088, "lng": 106.8456, "tag": "JAKARTA"},
    "city_disc_bks": {"name": "Bekasi", "lat": -6.2383, "lng": 106.9756, "tag": "BEKASI"},
    "city_disc_bgr": {"name": "Bogor", "lat": -6.5971, "lng": 106.8060, "tag": "BOGOR"},
    "city_disc_bdg": {"name": "Bandung", "lat": -6.9175, "lng": 107.6191, "tag": "BANDUNG"},
    "city_disc_jgj": {"name": "Jogja", "lat": -7.7956, "lng": 110.3695, "tag": "JOGJA"},
    "city_disc_smr": {"name": "Semarang", "lat": -6.9667, "lng": 110.4167, "tag": "SEMARANG"},
    "city_disc_slo": {"name": "Solo", "lat": -7.5707, "lng": 110.8214, "tag": "SOLO"},
    "city_disc_sby": {"name": "Surabaya", "lat": -7.2575, "lng": 112.7521, "tag": "SURABAYA"},
    "city_disc_mlg": {"name": "Malang", "lat": -7.9666, "lng": 112.6326, "tag": "MALANG"},
    "city_disc_dps": {"name": "Denpasar", "lat": -8.6705, "lng": 115.2126, "tag": "BALI"},
    "city_disc_lmbk": {"name": "Lombok", "lat": -8.5833, "lng": 116.1167, "tag": "LOMBOK"},
}

class DiscoveryState(StatesGroup):
    in_lobby = State()
    setting_age_min = State()
    setting_age_max = State()
    swiping = State()

def calculate_distance(lat1, lon1, lat2, lon2):
    if not all([lat1, lon1, lat2, lon2]): return 0.0
    R = 6371 
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def get_age_keyboard():
    kb = []
    row = []
    for age in range(18, 42):
        label = f"{age}" if age < 41 else "41+"
        row.append(InlineKeyboardButton(text=label, callback_data=f"age_select_{age}"))
        if len(row) == 5:
            kb.append(row)
            row = []
    if row: kb.append(row)
    kb.append([InlineKeyboardButton(text="❌ BATAL", callback_data="menu_discovery")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ==========================================
# 2. MENU LOBI DISCOVERY (Banner PickMe)
# ==========================================
@router.callback_query(F.data == "menu_discovery")
async def show_discovery_lobby(callback: types.CallbackQuery, db: DatabaseService, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    if not user: return await callback.answer("❌ Profil tidak ditemukan.", show_alert=True)

    # Mengambil notifikasi count untuk Like dan Match
    unreads = await db.get_all_unread_counts(user_id)
    count_like = unreads.get('like', 0)
    count_match = unreads.get('match', 0)

    limit = 50 if user.is_vip_plus else 30 if user.is_vip else 20
    sisa = max(0, limit - user.daily_swipe_count)
    target_gender = "Wanita" if user.gender.lower() == "pria" else "Pria"

    text = (
        f"🔍 <b>LOBI DISCOVERY</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"👤 <b>Profil:</b> {user.full_name.upper()}\n"
        f"🎫 <b>Jatah Swipe:</b> <b>{sisa} / {limit}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"🎯 <b>FILTER AKTIF:</b>\n"
        f"• Mencari: <b>{target_gender}</b>\n"
        f"• Usia: <b>{user.filter_age_min} - {user.filter_age_max} Tahun</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 MULAI MENCARI", callback_data="disc_start_search")],
        [InlineKeyboardButton(text=f"❤️ SIAPA SUKA SAYA ({count_like})", callback_data="list_who_like_me")],
        [InlineKeyboardButton(text=f"🔥 DAFTAR MATCH ({count_match})", callback_data="list_my_matches")],
        [InlineKeyboardButton(text="⚙️ UBAH FILTER USIA", callback_data="disc_set_age")],
        [InlineKeyboardButton(text="📍 UPDATE LOKASI", callback_data="disc_update_location")],
        [InlineKeyboardButton(text="🏠 DASHBOARD SAYA", callback_data="back_to_dashboard")]
    ])

    media = InputMediaPhoto(media=BANNER_PHOTO_ID, caption=text, parse_mode="HTML")
    try: 
        await callback.message.edit_media(media=media, reply_markup=kb)
    except:
        try: await callback.message.delete()
        except: pass
        await callback.message.answer_photo(photo=BANNER_PHOTO_ID, caption=text, reply_markup=kb, parse_mode="HTML")
        
    await state.set_state(DiscoveryState.in_lobby)

# ==========================================
# 3. PENGATURAN FILTER USIA (2-TAP UX)
# ==========================================
@router.callback_query(F.data == "disc_set_age", DiscoveryState.in_lobby)
async def ask_filter_age_min(callback: types.CallbackQuery, state: FSMContext):
    text = "⚙️ <b>PENGATURAN RENTANG USIA</b>\n\nSilakan tap <b>Usia Minimal</b> target yang kamu cari:"
    kb = get_age_keyboard()
    await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(DiscoveryState.setting_age_min)

@router.callback_query(F.data.startswith("age_select_"), DiscoveryState.setting_age_min)
async def ask_filter_age_max(callback: types.CallbackQuery, state: FSMContext):
    age_min = int(callback.data.split("_")[2])
    await state.update_data(temp_age_min=age_min)

    text = f"⚙️ <b>PENGATURAN RENTANG USIA</b>\n\nUsia Minimal: <b>{age_min}</b>\nSekarang tap <b>Usia Maksimal</b> target yang kamu cari:"
    kb = get_age_keyboard()
    await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(DiscoveryState.setting_age_max)

@router.callback_query(F.data.startswith("age_select_"), DiscoveryState.setting_age_max)
async def save_filter_age(callback: types.CallbackQuery, state: FSMContext, db: DatabaseService):
    data = await state.get_data()
    age_min = data.get("temp_age_min", 18)
    age_max = int(callback.data.split("_")[2])

    if age_max == 41: age_max = 60
    if age_min > age_max: age_min, age_max = age_max, age_min 

    async with db.session_factory() as session:
        user = await session.get(UserTable, callback.from_user.id)
        if user:
            user.filter_age_min = age_min
            user.filter_age_max = age_max
            await session.commit()

    await callback.answer(f"✅ Filter usia diubah menjadi {age_min} - {age_max} Tahun!", show_alert=True)
    await show_discovery_lobby(callback, db, state)

# ==========================================
# 4. MESIN SWIPER (Logika Utama Loop Profil)
# ==========================================
@router.callback_query(F.data == "disc_start_search", DiscoveryState.in_lobby)
async def start_swiping(callback: types.CallbackQuery, db: DatabaseService, state: FSMContext):
    user = await db.get_user(callback.from_user.id)
    limit = 50 if user.is_vip_plus else 30 if user.is_vip else 20
    if user.daily_swipe_count >= limit: 
        return await callback.answer("❌ Jatah pencarian harian Anda sudah habis!", show_alert=True)

    async with db.session_factory() as session:
        swiped_query = await session.execute(select(SwipeHistory.target_id).where(SwipeHistory.user_id == user.id))
        swiped_ids = [r[0] for r in swiped_query.fetchall()]
        target_gender = "Wanita" if user.gender.lower() == "pria" else "Pria"
        
        query = select(UserTable).where(
            and_(
                UserTable.id != user.id,
                not_(UserTable.id.in_(swiped_ids)),
                UserTable.gender.ilike(target_gender), 
                UserTable.age >= user.filter_age_min,              
                UserTable.age <= user.filter_age_max               
            )
        ).order_by(UserTable.is_vip_plus.desc(), UserTable.is_vip.desc()).limit(20) 
        
        targets = (await session.execute(query)).scalars().all()

    if not targets: return await callback.answer("😔 Tidak ada profil baru yang sesuai filter di sekitarmu.", show_alert=True)
    
    await state.update_data(queue=[t.id for t in targets], current_index=0)
    await show_next_profile(callback, state, db)

async def show_next_profile(callback: types.CallbackQuery, state: FSMContext, db: DatabaseService):
    data = await state.get_data()
    index, queue = data.get('current_index', 0), data.get('queue', [])

    if index >= len(queue):
        await callback.answer("Semua profil telah dilihat. Kembali ke Lobi...", show_alert=True)
        return await show_discovery_lobby(callback, db, state)

    target = await db.get_user(queue[index])
    me = await db.get_user(callback.from_user.id)
    jarak = calculate_distance(me.latitude, me.longitude, target.latitude, target.longitude)

    text = (
        f"🔍 <b>DISCOVERY MODE</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"👤 <b>{target.full_name.upper()}, {target.age}</b>\n"
        f"📍 {target.location_name} (±{jarak:.1f} km)\n"
        f"🔥 <b>Minat:</b> {target.interests or '-'}\n"
        f"📝 <blockquote>{target.bio or 'Tidak ada bio.'}</blockquote>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"<i>{index+1} dari {len(queue)} profil</i>"
    )

    kb_buttons = [
        [
            InlineKeyboardButton(text="❤️ LIKE", callback_data="swipe_like"),
            InlineKeyboardButton(text="💬 PESAN", callback_data=f"chat_{target.id}_free"),
            InlineKeyboardButton(text="❌ DISLIKE", callback_data="swipe_skip")
        ]
    ]
    
    nav_row = [InlineKeyboardButton(text="🔙 BACK", callback_data="menu_discovery")]
    if me.is_vip_plus:
        nav_row.append(InlineKeyboardButton(text="↩️ CALLBACK", callback_data="swipe_callback"))
        
    nav_row.append(InlineKeyboardButton(text="🏠 DASHBOARD", callback_data="back_to_dashboard"))
    kb_buttons.append(nav_row)

    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    media = InputMediaPhoto(media=target.photo_id, caption=text, parse_mode="HTML")
    
    try: await callback.message.edit_media(media=media, reply_markup=kb)
    except:
        try: await callback.message.delete()
        except: pass
        await callback.message.answer_photo(photo=target.photo_id, caption=text, reply_markup=kb, parse_mode="HTML")
    
    await state.set_state(DiscoveryState.swiping)

# ==========================================
# 5. AKSI TOMBOL SWIPING
# ==========================================
@router.callback_query(F.data.in_(["swipe_like", "swipe_skip"]), DiscoveryState.swiping)
async def handle_swipe(callback: types.CallbackQuery, state: FSMContext, db: DatabaseService, bot: Bot):
    await callback.answer() 
    data = await state.get_data()
    user_id, queue, index = callback.from_user.id, data.get('queue', []), data.get('current_index', 0)
    
    if index >= len(queue): return
    target_id = queue[index]
    action = callback.data.split("_")[1] 
    
    try: await db.record_swipe(user_id, target_id, action)
    except: pass
    
    is_match = False
    async with db.session_factory() as session:
        if action == "like":
            check_match = await session.execute(select(SwipeHistory).where(and_(SwipeHistory.user_id == target_id, SwipeHistory.target_id == user_id, SwipeHistory.action == "like")))
            if check_match.scalar_one_or_none():
                is_match = True
            else:
                try: await NotificationService(bot, db).send_push_alert(target_id, "LIKE") 
                except: pass

    if is_match:
        user_a, user_b = await db.get_user(user_id), await db.get_user(target_id)
        try: await bot.send_message(target_id, f"🎉 <b>IT'S A MATCH!</b>\nKamu saling suka dengan <b>{user_a.full_name.upper()}</b>!\nSilakan cek menu <b>Notifikasi > Match</b> untuk mulai mengobrol gratis.", parse_mode="HTML")
        except: pass
        try: await bot.send_message(user_id, f"🎉 <b>IT'S A MATCH!</b>\nKamu saling suka dengan <b>{user_b.full_name.upper()}</b>!\nSilakan cek menu <b>Notifikasi > Match</b> untuk mulai mengobrol gratis.", parse_mode="HTML")
        except: pass
        await callback.answer("🎉 IT'S A MATCH! Cek menu Notifikasi!", show_alert=True)

    await state.update_data(current_index=index + 1)
    await show_next_profile(callback, state, db)

@router.callback_query(F.data == "swipe_callback", DiscoveryState.swiping)
async def handle_callback_vip(callback: types.CallbackQuery, state: FSMContext, db: DatabaseService):
    user = await db.get_user(callback.from_user.id)
    if not user.is_vip_plus: return await callback.answer("🔒 Fitur 'Call Back' eksklusif untuk VIP+!", show_alert=True)
    
    index = (await state.get_data()).get('current_index', 0)
    if index <= 0: return await callback.answer("Tidak ada profil sebelumnya.", show_alert=True)
    
    await state.update_data(current_index=index - 1)
    await show_next_profile(callback, state, db)

# ==========================================
# 6. UPDATE LOKASI PENCARIAN
# ==========================================
@router.callback_query(F.data == "disc_update_location", DiscoveryState.in_lobby)
async def ask_location(callback: types.CallbackQuery, state: FSMContext):
    inline_kb_list, temp_row = [], []
    for code, info in CITY_DATA_DISC.items():
        temp_row.append(InlineKeyboardButton(text=info["name"], callback_data=code))
        if len(temp_row) == 3: 
            inline_kb_list.append(temp_row)
            temp_row = []
    if temp_row: inline_kb_list.append(temp_row)
    inline_kb_list.append([InlineKeyboardButton(text="🔙 BATAL", callback_data="cancel_loc_disc")])

    text = "📍 <b>UPDATE LOKASI PENCARIAN</b>\n\nPilih kota besarmu atau kirim koordinat GPS untuk memudahkan pencarian teman di sekitarmu."
    await callback.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kb_list), parse_mode="HTML")
    
    msg_gps = await callback.message.answer("Atau gunakan GPS otomatis dengan menekan tombol di bawah:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📍 KIRIM KOORDINAT GPS", request_location=True)]], resize_keyboard=True, one_time_keyboard=True))
    
    await state.update_data(gps_msg_id=msg_gps.message_id)
    await callback.answer()

@router.callback_query(F.data == "cancel_loc_disc")
async def cancel_loc_disc(callback: types.CallbackQuery, state: FSMContext, db: DatabaseService):
    data = await state.get_data()
    try: await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=data.get('gps_msg_id'))
    except: pass
    await show_discovery_lobby(callback, db, state)

@router.callback_query(F.data.startswith("city_disc_"), DiscoveryState.in_lobby)
async def handle_manual_location_update(callback: types.CallbackQuery, db: DatabaseService, state: FSMContext):
    city_info = CITY_DATA_DISC.get(callback.data)
    if city_info:
        await db.update_user_location(callback.from_user.id, city_info["lat"], city_info["lng"], city_info["name"], f"#{city_info['tag']}")
        
        data = await state.get_data()
        try: await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=data.get('gps_msg_id'))
        except: pass
        
        await callback.answer(f"Lokasi diperbarui ke {city_info['name']}!", show_alert=True)
        await show_discovery_lobby(callback, db, state)

@router.message(F.location, DiscoveryState.in_lobby)
async def handle_location_update(message: types.Message, db: DatabaseService, state: FSMContext):
    try: await message.delete()
    except: pass

    async with db.session_factory() as session:
        user = await session.get(UserTable, message.from_user.id)
        if user:
            user.latitude, user.longitude, user.location_name = message.location.latitude, message.location.longitude, "GPS Location"
            await session.commit()
            
    data = await state.get_data()
    try: await message.bot.delete_message(chat_id=message.chat.id, message_id=data.get('gps_msg_id'))
    except: pass

    from collections import namedtuple
    Dummy = namedtuple('CallbackQuery', ['from_user', 'message', 'answer', 'bot'])
    msg_sementara = await message.answer("Lokasi Tersimpan!", reply_markup=ReplyKeyboardRemove())
    await show_discovery_lobby(Dummy(from_user=message.from_user, message=msg_sementara, bot=message.bot, answer=lambda *a, **k: asyncio.sleep(0)), db, state)
    
    try: await msg_sementara.delete()
    except: pass
