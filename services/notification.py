import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services.database import DatabaseService, UserNotification

class NotificationService:
    def __init__(self, bot: Bot, db: DatabaseService = None):
        self.bot = bot
        self.db = db

    async def _silent_log(self, user_id: int, notif_type: str, sender_id: int = None, content: str = ""):
        if not self.db: return logging.error("DatabaseService tidak dikirim ke NotificationService!")
        
        async with self.db.session_factory() as session:
            session.add(UserNotification(
                user_id=user_id, 
                type=notif_type, 
                sender_id=sender_id,
                content=content, 
                is_read=False
            ))
            await session.commit()

    # --- 1. NOTIFIKASI UNMASK ---
    async def trigger_unmask(self, target_id: int, sender_id: int):
        await self._silent_log(target_id, "UNMASK_CHAT", sender_id, "Seseorang Unmask profilmu")
        
        text = "🔓 <b>Seorang Unmask profilmu</b>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔓 Unmask", callback_data="notif_list_unmask")],
            [InlineKeyboardButton(text="🔔 Notifikasi", callback_data="menu_notifications")],
            [InlineKeyboardButton(text="🏠 Dashboard", callback_data="back_to_dashboard")]
        ])
        try: await self.bot.send_message(target_id, text, reply_markup=kb, parse_mode="HTML")
        except: pass

    # --- 2. NOTIFIKASI INBOX PESAN & BALASAN ---
    async def trigger_new_message(self, target_id: int, sender_id: int, sender_name: str, is_reply: bool = False):
        await self._silent_log(target_id, "CHAT", sender_id, f"Pesan dari {sender_name}")
        
        unreads = await self.db.get_all_unread_counts(target_id)
        count_n = unreads.get('inbox', 0)
        
        if is_reply:
            text = f"💬 <b>{sender_name}, mengirimimu pesan</b>"
            btn_text = "📥 Buka Pesan"
        else:
            text = f"📩 <b>Kamu menerima ({count_n}) pesan baru</b>"
            btn_text = "📥 Inbox"
            
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, callback_data="notif_list_inbox")],
            [InlineKeyboardButton(text="🔔 Notifikasi", callback_data="menu_notifications")],
            [InlineKeyboardButton(text="🏠 Dashboard", callback_data="back_to_dashboard")]
        ])
        try: await self.bot.send_message(target_id, text, reply_markup=kb, parse_mode="HTML")
        except: pass

    # --- 3. NOTIFIKASI SUKA / LIKE ---
    async def trigger_like(self, target_id: int, sender_id: int):
        await self._silent_log(target_id, "LIKE", sender_id, "Seseorang telah menyukaimu")
        text = "❤️ <b>Seseorang telah menyukaimu</b>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❤️ Lihat siapa suka", callback_data="notif_list_like")],
            [InlineKeyboardButton(text="🔔 Notifikasi", callback_data="menu_notifications")],
            [InlineKeyboardButton(text="🏠 Dashboard", callback_data="back_to_dashboard")]
        ])
        try: await self.bot.send_message(target_id, text, reply_markup=kb, parse_mode="HTML")
        except: pass

    # --- 4. NOTIFIKASI MELIHAT PROFIL ---
    async def trigger_view(self, target_id: int, sender_id: int):
        await self._silent_log(target_id, "VIEW", sender_id, "Seseorang telah melihat profilmu")
        text = "👀 <b>Seseorang telah melihat profilmu</b>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Lihat Profil", callback_data="notif_list_view")],
            [InlineKeyboardButton(text="🔔 Notifikasi", callback_data="menu_notifications")],
            [InlineKeyboardButton(text="🏠 Dashboard", callback_data="back_to_dashboard")]
        ])
        try: await self.bot.send_message(target_id, text, reply_markup=kb, parse_mode="HTML")
        except: pass
        
