import os
import html
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto

from services.database import DatabaseService

router = Router()

BANNER_PHOTO_ID = os.getenv("BANNER_PHOTO_ID", "AgACAgUAAxkBAAIKUmm-3V96dh0wXlEwKgR9cZYxQJ7IAAJWEWsb5Sz5VRdAhJBTFWieAQADAgADeAADOgQ")

# ==========================================
# 1. MENU UTAMA NOTIFIKASI (Pusat Komando)
# ==========================================
@router.callback_query(F.data == "menu_notifications")
async def show_notification_menu(callback: types.CallbackQuery, db: DatabaseService):
    user_id = callback.from_user.id
    unreads = await db.get_all_unread_counts(user_id)

    text = (
        "🔔 <b>PUSAT NOTIFIKASI & REWARD</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
        "<i>Periksa interaksi barumu. Balas pesan Sultan atau Inbox untuk mendapatkan Bonus Poin!</i>"
    )

    # TOMBOL "LIKE" SUDAH DIHAPUS DARI SINI
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔓 SIAPA UNMASK SAYA ({unreads.get('unmask', 0)})", callback_data="notif_list_unmask")],
        [InlineKeyboardButton(text=f"📥 INBOX PESAN ({unreads.get('inbox', 0)})", callback_data="notif_list_inbox")],
        [InlineKeyboardButton(text=f"👀 SIAPA MELIHAT PROFIL ({unreads.get('view', 0)})", callback_data="notif_list_view")],
        [InlineKeyboardButton(text="🏠 KEMBALI KE DASHBOARD", callback_data="back_to_dashboard")]
    ])
    
    media = InputMediaPhoto(media=BANNER_PHOTO_ID, caption=text, parse_mode="HTML")
    try: 
        await callback.message.edit_media(media=media, reply_markup=kb)
    except Exception:
        try: await callback.message.delete()
        except: pass
        await callback.message.answer_photo(photo=BANNER_PHOTO_ID, caption=text, reply_markup=kb, parse_mode="HTML")
    
    await callback.answer()

# ==========================================
# 2. HANDLER LIST (Universal, Tanpa "Like")
# ==========================================
@router.callback_query(F.data.startswith("notif_list_"))
async def view_unified_list(callback: types.CallbackQuery, db: DatabaseService, bot: Bot):
    user_id = callback.from_user.id
    menu_type = callback.data.split("_")[2] 
    current_user = await db.get_user(user_id)
    
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    # KONFIGURASI "LIKE" SUDAH DIHAPUS DARI SINI
    config = {
        "unmask": {"db": "UNMASK_CHAT", "title": "🔓 DAFTAR UNMASK SULTAN", "ctx": "unmask"},
        "inbox":  {"db": "CHAT", "title": "📥 INBOX PESAN AKTIF", "ctx": "inbox"},
        "view":   {"db": "VIEW", "title": "👀 PENGUNJUNG PROFIL", "ctx": "view"}
    }
    
    if menu_type not in config:
        return await callback.answer("Menu tidak valid.", show_alert=True)
        
    cfg = config[menu_type]
    interactors = await db.get_interaction_list(user_id, cfg["db"])

    text_content = f"<b>{cfg['title']}</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"

    if not interactors:
        if menu_type == "unmask": text_content += "<i>Belum ada Sultan VIP+ yang membongkar identitasmu.</i>"
        elif menu_type == "inbox": text_content += "<i>Belum ada pesan masuk. Mulai chat duluan!</i>"
        elif menu_type == "match": text_content += "<i>Belum ada matching baru. Terus swipe profil!</i>"
        else: text_content += "<i>Belum ada pengunjung profil baru.</i>"
    else:
        for i, person in enumerate(interactors, 1):
            # Kunci sensor nama hanya berlaku untuk View Profil sekarang
            is_locked = (menu_type == "view") and not (current_user.is_vip or current_user.is_vip_plus)
            name = f"{person.full_name[:3]}***" if is_locked else person.full_name
            age = person.age
            city = html.escape(person.location_name) if person.location_name else "Lokasi Tidak Diketahui"
            
            # Deep link URL (Penting: Parameter unmask tidak berubah)
            if menu_type == "unmask":
                url = f"https://t.me/{bot_username}?start=view_{person.id}_unmask"
            else:
                url = f"https://t.me/{bot_username}?start=view_{person.id}_{cfg['ctx']}"
                
            url_lock = f"https://t.me/{bot_username}?start=pricing"
            
            has_date = hasattr(person, 'notif_date') and person.notif_date

            if menu_type == "unmask":
                text_content += f"{i}. <b>{name}</b>, {age}th, {city}, jatuh cinta padamu. <a href='{url}'>[Lihat Profil & Balas]</a>\n\n"
            elif menu_type == "inbox":
                expiry_hours = 48 if current_user.is_vip_plus else 24
                exp_date = (person.notif_date + timedelta(hours=expiry_hours)).strftime("%H:%M %d/%m/%Y") if has_date else "Segera"
                text_content += f"{i}. <b>{name}</b>, {age}th, {city}. (Hilang {exp_date}) <a href='{url}'>[Balas Pesan]</a>\n\n"
            elif menu_type == "match":
                text_content += f"{i}. <b>{name}</b>, {age}th, {city}. <a href='{url}'>[Lihat Profil & Chat]</a>\n\n"
            else: # Menu VIEW
                if is_locked:
                    text_content += f"{i}. <b>{name}</b>, {age}th, {city}. <a href='{url_lock}'>[🔒 Upgrade VIP]</a>\n"
                else:
                    text_content += f"{i}. <b>{name}</b>, {age}th, {city}. <a href='{url}'>[Lihat Profil]</a>\n"

    kb_nav = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 KEMBALI", callback_data="menu_notifications")],
        [InlineKeyboardButton(text="🏠 DASHBOARD", callback_data="back_to_dashboard")]
    ])

    media = InputMediaPhoto(media=BANNER_PHOTO_ID, caption=text_content, parse_mode="HTML")
    try: await callback.message.edit_media(media=media, reply_markup=kb_nav)
    except Exception: 
        try: await callback.message.answer_photo(photo=BANNER_PHOTO_ID, caption=text_content, reply_markup=kb_nav, parse_mode="HTML")
        except: pass
    await callback.answer()
  
