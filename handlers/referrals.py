import os
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, and_
from services.database import DatabaseService, User, PointLog
from services.database import ReferralTracking 

router = Router()

# ==========================================
# 1. MENU TAMPILAN REFERRAL
# ==========================================
@router.callback_query(F.data == "menu_referral")
async def show_referral_menu(callback: types.CallbackQuery, db: DatabaseService, bot: Bot):
    user_id = callback.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    
    async with db.session_factory() as session:
        total_query = await session.execute(select(ReferralTracking).where(ReferralTracking.referrer_id == user_id))
        total_invited = len(total_query.scalars().all())
        
        active_query = await session.execute(select(ReferralTracking).where(
            and_(ReferralTracking.referrer_id == user_id, ReferralTracking.is_active == True)
        ))
        active_users = len(active_query.scalars().all())

    text = (
        f"🎁 <b>PROGRAM REFERRAL SULTAN</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>\n"
        f"Ajak teman bergabung dan dapatkan <b>Gaji Mingguan Bersama!</b>\n"
        f"Syarat: Temanmu harus aktif klik bot & tidak keluar dari Grup.\n\n"
        f"💸 <b>Sama-sama Untung! Kalian BERDUA akan mendapat:</b>\n"
        f"• Join Awal: <b>Masing-masing +1.000 Poin</b>\n"
        f"• Aktif 7 Hari: <b>Masing-masing +1.000 Poin</b>\n"
        f"• Aktif 14 Hari: <b>Masing-masing +1.000 Poin</b>\n"
        f"• Aktif 21 Hari: <b>Masing-masing +1.000 Poin</b>\n"
        f"• Aktif 28 Hari: <b>Masing-masing +1.000 Poin</b>\n"
        f"Total Maksimal: <b>5.000 Poin per Orang!</b> 💰\n\n"
        f"📊 <b>Statistik Undanganku:</b>\n"
        f"Total Diundang: {total_invited} Orang\n"
        f"Masih Bertahan: {active_users} Orang\n\n"
        f"👇 <b>Link Sakti Kamu:</b> (Tekan untuk menyalin)\n"
        f"<code>{ref_link}</code>\n"
        f"<code>━━━━━━━━━━━━━━━━━━</code>"
    )
    
    BANNER_ID = "AgACAgUAAxkBAAIC..." # Opsional, sesuaikan
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 KEMBALI KE DASHBOARD", callback_data="back_to_dashboard")]])
    
    try: await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    except: 
        try: await callback.message.delete()
        except: pass
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    
    await callback.answer()


# ==========================================
# 2. ROBOT PENGECEK MINGGUAN (CRON JOB JAM 1 PAGI)
# ==========================================
async def check_user_membership(bot: Bot, user_id: int) -> bool:
    CHANNEL_ID = os.getenv("CHANNEL_ID", "-100...") 
    GROUP_ID = os.getenv("GROUP_ID", "-100...")
    
    try:
        member_ch = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member_ch.status in ['left', 'kicked', 'banned']: return False
        
        member_gr = await bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        if member_gr.status in ['left', 'kicked', 'banned']: return False
        
        return True
    except Exception as e:
        logging.error(f"Membership check failed for {user_id}: {e}")
        return False


async def schedule_referral_evaluation(bot: Bot, db: DatabaseService):
    tz = ZoneInfo("Asia/Jakarta")
    while True:
        now = datetime.now(tz)
        target_time = now.replace(hour=1, minute=0, second=0, microsecond=0)
        
        if now >= target_time:
            target_time += timedelta(days=1)
            
        wait_seconds = (target_time - now).total_seconds()
        logging.info(f"⏰ [REFERRAL CHECKER] Menunggu {wait_seconds / 3600:.2f} Jam menuju pukul 01:00 WIB.")
        
        await asyncio.sleep(wait_seconds)
        
        logging.info("🚀 Memulai Razia Referral Mingguan...")
        await process_referrals(bot, db)


async def process_referrals(bot: Bot, db: DatabaseService):
    async with db.session_factory() as session:
        active_refs_query = await session.execute(
            select(ReferralTracking).where(
                and_(ReferralTracking.is_active == True, ReferralTracking.is_completed == False)
            )
        )
        active_refs = active_refs_query.scalars().all()
        
        now_utc = datetime.utcnow()
        seven_days_ago = now_utc - timedelta(days=7)
        
        for ref in active_refs:
            days_passed = (now_utc - ref.created_at).days
            
            week_target = 0
            if days_passed >= 28 and not ref.week_4_done: week_target = 4
            elif days_passed >= 21 and not ref.week_3_done: week_target = 3
            elif days_passed >= 14 and not ref.week_2_done: week_target = 2
            elif days_passed >= 7 and not ref.week_1_done: week_target = 1
            else:
                continue 
                
            child = await session.get(User, ref.referred_id)
            referrer = await session.get(User, ref.referrer_id)
            
            if not child or not referrer: continue
            
            is_active_in_bot = (child.last_active_at and child.last_active_at >= seven_days_ago)
            is_still_member = await check_user_membership(bot, child.id)
            
            await asyncio.sleep(0.2) 
            
            if is_active_in_bot and is_still_member:
                # 🚀 LULUS RAZIA! BERI 1.000 POIN KE KEDUANYA
                referrer.poin_balance += 1000
                child.poin_balance += 1000
                session.add(PointLog(user_id=referrer.id, amount=1000, source=f"Referral Bonus W-{week_target} (ID: {child.id})"))
                session.add(PointLog(user_id=child.id, amount=1000, source=f"Retention Bonus W-{week_target} (from: {referrer.id})"))
                
                if week_target == 1: ref.week_1_done = True
                elif week_target == 2: ref.week_2_done = True
                elif week_target == 3: ref.week_3_done = True
                elif week_target == 4: 
                    ref.week_4_done = True
                    ref.is_completed = True
                
                # Notif ke Pengundang
                try:
                    await bot.send_message(
                        referrer.id, 
                        f"🎉 <b>GAJI REFERRAL MINGGU KE-{week_target} CAIR!</b>\n"
                        f"Temanmu (ID: <code>{child.id}</code>) berhasil menjaga keaktifannya.\n"
                        f"💰 Saldo kamu bertambah <b>+1.000 Poin</b>!",
                        parse_mode="HTML"
                    )
                except: pass
                
                # Notif ke Anak yang diundang
                try:
                    await bot.send_message(
                        child.id, 
                        f"🎉 <b>GAJI MINGGU KE-{week_target} CAIR!</b>\n"
                        f"Terima kasih telah aktif di PickMe minggu ini!\n"
                        f"💰 Saldo kamu bertambah <b>+1.000 Poin</b> dari program referral.",
                        parse_mode="HTML"
                    )
                except: pass
                
            else:
                # GAGAL RAZIA!
                ref.is_active = False 
                alasan = "tidak aktif menggunakan bot" if not is_active_in_bot else "keluar dari Grup/Channel"
                
                try:
                    await bot.send_message(
                        referrer.id, 
                        f"💔 <b>REFERRAL GAGAL/HANGUS</b>\n"
                        f"Teman yang kamu undang (ID: <code>{child.id}</code>) diketahui <b>{alasan}</b> dalam 7 hari terakhir.\n\n"
                        f"<i>Poin batal ditambahkan dan status referral dihentikan.</i>",
                        parse_mode="HTML"
                    )
                except: pass
                
        await session.commit()
