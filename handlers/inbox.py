import os
import html
import datetime
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from services.database import DatabaseService

router = Router()

BANNER_PHOTO_ID = os.getenv("BANNER_PHOTO_ID", "AgACAgUAAxkBAAIKUmm-3V96dh0wXlEwKgR9cZYxQJ7IAAJWEWsb5Sz5VRdAhJBTFWieAQADAgADeAADOgQ")

@router.callback_query(F.data == "menu_inbox")
async def show_inbox(callback: types.CallbackQuery, db: DatabaseService, bot: Bot):
    user_id = callback.from_user.id
    
    # Ambil SEMUA sesi dari database (Aktif maupun Terkunci)
    sessions = await db.get_inbox_sessions(user_id)

    text_content = "<b>📥 INBOX PESAN & HISTORI</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"

    if not sessions:
        text_content += "<i>Belum ada riwayat percakapan. Mulai sapa seseorang di Discovery!</i>"
        kb_nav = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 KEMBALI KE DASHBOARD", callback_data="back_to_dashboard")]])
    else:
        kb_buttons = []
        now = int(datetime.datetime.now().timestamp())
        
        for i, sess in enumerate(sessions, 1):
            counterpart_id = sess.target_id if sess.user_id == user_id else sess.user_id
            counterpart = await db.get_user(counterpart_id)
            if not counterpart: continue
            
            name = counterpart.full_name
            is_active = sess.expires_at > now
            
            # Cuplikan pesan
            snippet = sess.last_message[:20] + "..." if sess.last_message else "Belum ada pesan."
            snippet = html.escape(snippet)
            
            if is_active:
                exp_date = datetime.datetime.fromtimestamp(sess.expires_at).strftime("%d/%m %H:%M")
                text_content += f"{i}. 🟢 <b>{name}</b> (Aktif s/d {exp_date})\n<i>\"{snippet}\"</i>\n\n"
                kb_buttons.append([InlineKeyboardButton(text=f"💬 Buka Obrolan dgn {name}", callback_data=f"chat_{counterpart_id}_inbox")])
            else:
                text_content += f"{i}. 🔴 <b>{name}</b> (Terkunci)\n<i>\"{snippet}\"</i>\n\n"
                kb_buttons.append([InlineKeyboardButton(text=f"🔒 Perpanjang & Buka dgn {name}", callback_data=f"chat_{counterpart_id}_extend")])
                
        text_content += "<i>Obrolan yang terkunci (🔴) membutuhkan 1 Kuota Pesan untuk dibuka kembali selama 24 Jam.</i>"
        kb_buttons.append([InlineKeyboardButton(text="🏠 DASHBOARD", callback_data="back_to_dashboard")])
        kb_nav = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    media = InputMediaPhoto(media=BANNER_PHOTO_ID, caption=text_content, parse_mode="HTML")
    try: await callback.message.edit_media(media=media, reply_markup=kb_nav)
    except: 
        try: await callback.message.delete()
        except: pass
        await callback.message.answer_photo(photo=BANNER_PHOTO_ID, caption=text_content, reply_markup=kb_nav, parse_mode="HTML")
    await callback.answer()
