import os
import html
import logging
import datetime
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto

from services.database import DatabaseService, User, PointLog
from services.notification import NotificationService

router = Router()

BANNER_PHOTO_ID = os.getenv("BANNER_PHOTO_ID", "AgACAgUAAxkBAAIKUmm-3V96dh0wXlEwKgR9cZYxQJ7IAAJWEWsb5Sz5VRdAhJBTFWieAQADAgADeAADOgQ")

# ==========================================
# 1. MESIN UTAMA PENAMPIL PROFIL (Universal)
# ==========================================
async def process_profile_preview(message: types.Message, bot: Bot, db: DatabaseService, viewer_id: int, target_id: int, context_source: str):
    
    viewer = await db.get_user(viewer_id)
    target = await db.get_user(target_id)
    notif_service = NotificationService(bot, db)

    if not target:
        return await message.answer("❌ Profil tidak ditemukan atau user telah menghapus akunnya.")
    if viewer_id == target_id:
        return await message.answer("👋 Ini adalah link profil kamu sendiri. Gunakan tombol 'Profil Saya' di Dashboard.")

    is_sultan = (viewer.is_vip or viewer.is_vip_plus)
    is_unmasked_anon = False

    # --- MATIKAN COUNTER (N) KARENA PROFIL SUDAH DILIHAT ---
    mapping_db = {"like": "LIKE", "view": "VIEW", "unmask": "UNMASK_CHAT", "inbox": "CHAT", "match": "MATCH"}
    db_type = mapping_db.get(context_source)
    if db_type:
        await getattr(db, 'mark_notif_read', lambda u, s, t: None)(viewer_id, target_id, db_type)

    # --- PENGECEKAN ANTI-FARMING (SESI AKTIF 48 JAM) ---
    has_active_session = False
    active_expiry = await getattr(db, 'get_active_chat_session', lambda u, t: None)(viewer_id, target_id)
    if active_expiry and active_expiry > datetime.datetime.now().timestamp():
        has_active_session = True

    # ---------------------------------------------------
    # KONDISI A: DARI FEED ANONIM (UNMASK)
    # ---------------------------------------------------
    if context_source == "anon":
        if not viewer.is_vip_plus:
            return await show_locked_anon_profile(message, target)
        
        if has_active_session:
            is_unmasked_anon = True
        else:
            quota_unmask = getattr(viewer, 'daily_unmask_quota', 0)
            if quota_unmask is None: quota_unmask = 0
            if quota_unmask <= 0:
                async with db.session_factory() as session:
                    v_db = await session.get(User, viewer_id)
                    v_db.daily_unmask_quota = 10
                    await session.commit()
                viewer.daily_unmask_quota = 10

            success = await db.use_unmask_anon_quota(viewer_id)
            if not success:
                return await message.answer("❌ Kuota Harian 'Bongkar Anonim' kamu sudah habis! Tunggu reset besok.")
            
            expiry_48h = int((datetime.datetime.now() + datetime.timedelta(hours=48)).timestamp())
            await getattr(db, 'upsert_chat_session', lambda u, t, e: None)(viewer_id, target_id, expiry_48h)
            await db.add_points_with_log(target_id, 500, f"Unmask_Kompensasi_Awal_{viewer_id}_{target_id}_{expiry_48h}")
            await notif_service.trigger_unmask(target_id, viewer_id)
            is_unmasked_anon = True

    # ---------------------------------------------------
    # KONDISI B: DARI FEED PUBLIK (LIHAT PROFIL BIASA)
    # ---------------------------------------------------
    elif context_source == "public":
        if not is_sultan:
            return await show_upgrade_block(message, target.full_name)
        
        if has_active_session:
            pass
        else:
            quota_open = getattr(viewer, 'daily_open_profile_quota', 0)
            if quota_open is None: quota_open = 0
            if is_sultan and quota_open <= 0:
                async with db.session_factory() as session:
                    v_db = await session.get(User, viewer_id)
                    v_db.daily_open_profile_quota = 10
                    await session.commit()
                viewer.daily_open_profile_quota = 10

            is_new_view = await db.log_and_check_daily_reward(viewer_id, target_id, "VIEW_PROFILE")
            if is_new_view:
                success = await db.use_unmask_quota(viewer_id) 
                if not success:
                    return await message.answer("❌ Kuota Harian 'Buka Profil' kamu sudah habis! Tunggu reset besok.")
                
                async with db.session_factory() as session:
                    t_db = await session.get(User, target_id)
                    if t_db:
                        t_db.poin_balance += 100
                        session.add(PointLog(user_id=target_id, amount=100, source="Profil Diintip (Feed)"))
                        await session.commit()
                
                await notif_service.trigger_view(target_id, viewer_id)

    # ---------------------------------------------------
    # KONDISI C: DARI NOTIFIKASI
    # ---------------------------------------------------
    elif context_source in ["like", "view", "notif"]:
        if not is_sultan:
            return await show_upgrade_block(message, target.full_name)
        else:
            if context_source in ["view", "notif"] and not has_active_session:
                await notif_service.trigger_view(target_id, viewer_id)

    # ---------------------------------------------------
    # KONDISI D: DARI INBOX / MATCH / UNMASK
    # ---------------------------------------------------
    elif context_source in ["match", "unmask", "inbox"]:
        pass 
        
    else:
        return await message.answer("❌ Akses tidak valid.")

    # ==========================================
    # RENDER UI PROFIL LENGKAP
    # ==========================================
    target_kasta = "💎 VIP+" if target.is_vip_plus else "🌟 VIP" if target.is_vip else "🎭 TALENT" if target.is_premium else "👤 FREE"
    
    from handlers.start import get_readable_interests 
    minat = get_readable_interests(target.interests) if hasattr(target, 'interests') else "-"

    target_name = html.escape(target.full_name) if target.full_name else "Anonim"
    target_loc = html.escape(target.location_name) if target.location_name else "-"
    target_bio = html.escape(target.bio) if target.bio else "-"

    text_full = (
        f"👤 <b>PROFIL: {target_name.upper()}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"👑 <b>Status:</b> {target_kasta}\n"
        f"🎂 <b>Usia:</b> {target.age} Tahun\n"
        f"👫 <b>Gender:</b> {target.gender.title()}\n"
        f"📍 <b>Kota:</b> {target_loc}\n"
        f"🔥 <b>Minat:</b> {minat}\n"
        f"📝 <b>Bio:</b>\n<i>{target_bio}</i>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>"
    )

    if is_unmasked_anon:
        text_full = f"🔓 <b>IDENTITAS BERHASIL DIBONGKAR!</b>\n\n" + text_full + f"\n\n<i>💰 Sesi chat gratis 48 jam terbuka untuk kalian berdua! Target mendapatkan 500 Poin tambahan saat membalas.</i>"
    elif context_source == "unmask":
        text_full = f"🔓 <b>IDENTITASMU TELAH DIBONGKAR!</b>\n\n" + text_full + f"\n\n<i>💰 Sesi chat gratis 48 jam terbuka. Balas pesannya untuk mendapatkan 500 Poin!</i>"
    elif context_source == "inbox":
        text_full = f"📥 <b>PENGIRIM PESAN INBOX</b>\n\n" + text_full
    elif context_source == "match":
        text_full = f"🔥 <b>MATCH! KALIAN SALING SUKA</b>\n\n" + text_full
    elif context_source == "like":
        text_full = f"❤️ <b>SESEORANG MENYUKAIMU!</b>\n\n" + text_full

    kb_buttons = []
    
    # --- PERBAIKAN PEMISAHAN TOMBOL INITIATOR & TARGET ---
        # GANTI BLOK INI:
    if is_unmasked_anon:
        kb_buttons.append([InlineKeyboardButton(text="✍️ KIRIM PESAN", callback_data=f"unmaskchat_{target_id}_initiator")])
    elif context_source == "unmask":
        kb_buttons.append([InlineKeyboardButton(text="✍️ BALAS PESAN (+500 Poin)", callback_data=f"unmaskchat_{target_id}_target")])
    elif context_source == "inbox":
        kb_buttons.append([InlineKeyboardButton(text="💬 BALAS PESAN (+200 Poin)", callback_data=f"chat_{target_id}_inbox")])
    elif context_source == "match":
        kb_buttons.append([InlineKeyboardButton(text="💬 KIRIM PESAN GRATIS", callback_data=f"chat_{target_id}_match")])
    elif context_source == "like":
        kb_buttons.append([
            InlineKeyboardButton(text="❤️ SUKA/LIKE", callback_data=f"action_like_{target_id}"),
            InlineKeyboardButton(text="👎 TIDAK SUKA", callback_data=f"action_dislike_{target_id}")
        ])
    else:
        if is_sultan:
            kb_buttons.append([InlineKeyboardButton(text="💌 KIRIM PESAN", callback_data=f"chat_{target_id}_public")])
        else:
            kb_buttons.append([InlineKeyboardButton(text="💎 UPGRADE UNTUK CHAT", callback_data="menu_pricing")])
            
    back_btn = "menu_feed" if context_source in ["public", "anon"] else "menu_notifications"
    kb_buttons.append([InlineKeyboardButton(text="🔙 KEMBALI", callback_data=back_btn)])
    kb_buttons.append([InlineKeyboardButton(text="🏠 DASHBOARD SAYA", callback_data="back_to_dashboard")])

    try: 
        await message.answer_photo(photo=target.photo_id, caption=text_full, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons), parse_mode="HTML")
    except Exception: 
        await message.answer(text_full, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons), parse_mode="HTML")


# ==========================================
# 2. FUNGSI BLOKIR SAJA
# ==========================================
async def show_upgrade_block(message: types.Message, target_name: str):
    name_safe = html.escape(target_name[:3]) if target_name else "Ano"
    text_lock = (
        f"🔒 <b>PROFIL TERKUNCI</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"Profil <b>{name_safe}***</b> hanya bisa dilihat oleh Member <b>VIP / VIP+</b>.\n\n"
        f"<i>Upgrade akunmu sekarang untuk bisa melihat profil lengkap, membuka fitur chat, dan bebas kuota preview!</i>"
    )
    kb_lock = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 UPGRADE VIP SEKARANG", callback_data="menu_pricing")],
        [InlineKeyboardButton(text="🏠 DASHBOARD", callback_data="back_to_dashboard")]
    ])
    await message.answer_photo(photo=BANNER_PHOTO_ID, caption=text_lock, reply_markup=kb_lock, parse_mode="HTML")

async def show_locked_anon_profile(message: types.Message, target: User):
    loc_safe = html.escape(target.location_name) if target.location_name else "Suatu Tempat"
    text_anon = (
        f"🎭 <b>POSTINGAN ANONIM</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"Seseorang di <b>{loc_safe}</b> memposting ini.\n"
        f"Identitasnya disembunyikan dan hanya bisa dibongkar oleh Sultan <b>VIP+</b>."
    )
    
    kb_anon = [
        [InlineKeyboardButton(text="💎 UPGRADE VIP+ UNTUK BONGKAR", callback_data="menu_pricing")],
        [InlineKeyboardButton(text="🔙 KEMBALI KE FEED", callback_data="menu_feed")]
    ]
    await message.answer_photo(photo=BANNER_PHOTO_ID, caption=text_anon, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_anon), parse_mode="HTML")


# ==========================================
# 3. HANDLER AKSI (LIKE & DISLIKE DARI PREVIEW)
# ==========================================
@router.callback_query(F.data.startswith("action_like_"))
async def handle_notif_like(callback: types.CallbackQuery, db: DatabaseService, bot: Bot):
    target_id = int(callback.data.split("_")[2])
    viewer_id = callback.from_user.id
    notif_service = NotificationService(bot, db)
    
    is_match = await db.process_match_logic(viewer_id, target_id)
    if is_match:
        await bot.send_message(viewer_id, "🔥 <b>CONGRATS!</b> Kalian saling menyukai. Cek menu Match untuk chat gratis!")
        try: await bot.send_message(target_id, "🔥 <b>CONGRATS!</b> Seseorang menyukai balik profilmu. Cek menu Match!")
        except: pass
    else:
        await notif_service.trigger_like(target_id, viewer_id)
        
    await callback.answer("❤️ Berhasil menyukai!", show_alert=True)
    try: await callback.message.delete()
    except: pass

@router.callback_query(F.data.startswith("action_dislike_"))
async def handle_notif_dislike(callback: types.CallbackQuery, db: DatabaseService):
    target_id = int(callback.data.split("_")[2])
    viewer_id = callback.from_user.id
    
    await db.remove_interaction(viewer_id, target_id, "LIKE")
    await callback.answer("👎 Profil dihapus dari daftar.", show_alert=True)
    try: await callback.message.delete()
    except: pass
    
