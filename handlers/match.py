import os
import html
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from services.database import DatabaseService

router = Router()

BANNER_PHOTO_ID = os.getenv("BANNER_PHOTO_ID", "AgACAgUAAxkBAAIKUmm-3V96dh0wXlEwKgR9cZYxQJ7IAAJWEWsb5Sz5VRdAhJBTFWieAQADAgADeAADOgQ")

@router.callback_query(F.data == "list_my_matches")
async def view_my_matches(callback: types.CallbackQuery, db: DatabaseService, bot: Bot):
    user_id = callback.from_user.id
    
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    # Ambil daftar MATCH dari database
    interactors = await db.get_interaction_list(user_id, "MATCH")

    text_content = "<b>🔥 DAFTAR MATCHING KAMU</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"

    if not interactors:
        text_content += "<i>Belum ada matching baru. Terus swipe profil di Discovery!</i>"
    else:
        for i, person in enumerate(interactors, 1):
            # Match tidak perlu disensor namanya karena sudah saling suka
            name = person.full_name
            age = person.age
            city = html.escape(person.location_name) if person.location_name else "Lokasi Tidak Diketahui"
            
            # Deep link membuka profil target dalam mode Match
            url = f"https://t.me/{bot_username}?start=view_{person.id}_match"
            
            text_content += f"{i}. <b>{name}</b>, {age}th, {city}. <a href='{url}'>[Lihat & Chat]</a>\n\n"

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
      
