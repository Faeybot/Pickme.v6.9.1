import os
import html
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from services.database import DatabaseService

router = Router()

BANNER_PHOTO_ID = os.getenv("BANNER_PHOTO_ID", "AgACAgUAAxkBAAIKUmm-3V96dh0wXlEwKgR9cZYxQJ7IAAJWEWsb5Sz5VRdAhJBTFWieAQADAgADeAADOgQ")

@router.callback_query(F.data == "list_who_like_me")
async def view_who_liked_me(callback: types.CallbackQuery, db: DatabaseService, bot: Bot):
    user_id = callback.from_user.id
    current_user = await db.get_user(user_id)
    
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    # Ambil daftar orang yang LIKE
    interactors = await db.get_interaction_list(user_id, "LIKE")

    text_content = "<b>❤️ PENGAGUM RAHASIAMU</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"

    if not interactors:
        text_content += "<i>Belum ada yang menyukaimu. Terus posting foto terbaikmu di Feed!</i>"
    else:
        for i, person in enumerate(interactors, 1):
            # KUNCI EKSKLUSIF: Hanya VIP+ yang bisa melihat profil orang yang nge-like!
            is_locked = not current_user.is_vip_plus 
            
            name = f"{person.full_name[:3]}***" if is_locked else person.full_name
            age = person.age
            city = html.escape(person.location_name) if person.location_name else "Lokasi Tidak Diketahui"
            
            url = f"https://t.me/{bot_username}?start=view_{person.id}_like"
            url_lock = f"https://t.me/{bot_username}?start=pricing"
            
            if is_locked:
                text_content += f"{i}. <b>{name}</b>, {age}th, {city}. <a href=\"{url_lock}\">[🔒 Upgrade VIP+]</a>\n\n"
            else:
                text_content += f"{i}. <b>{name}</b>, {age}th, {city}. <a href=\"{url}\">[Lihat Profil]</a>\n\n"

    kb_nav = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 KEMBALI KE DISCOVERY", callback_data="menu_discovery")],
        [InlineKeyboardButton(text="🏠 DASHBOARD", callback_data="back_to_dashboard")]
    ])

    media = InputMediaPhoto(media=BANNER_PHOTO_ID, caption=text_content, parse_mode="HTML")
    try:
        await callback.message.edit_media(media=media, reply_markup=kb_nav)
    except:
        await callback.message.answer_photo(photo=BANNER_PHOTO_ID, caption=text_content, reply_markup=kb_nav, parse_mode="HTML")
    
    await callback.answer()
  
