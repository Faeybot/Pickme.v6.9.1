import os
import logging
import json
import datetime
from sqlalchemy import (
    Column, Integer, String, BigInteger, Boolean, DateTime, ForeignKey, 
    Float, JSON, Text, select, update, and_, or_, not_, delete, text, func
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

Base = declarative_base()

# ==========================================
# 1. MODEL TABEL DATABASE
# ==========================================

class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)
    full_name = Column(String)
    age = Column(Integer)
    birth_date = Column(DateTime, nullable=True) 
    gender = Column(String)
    bio = Column(Text)
    interests = Column(String, nullable=True) 
    photo_id = Column(String)
    extra_photos = Column(JSON, default=[]) 
    latitude = Column(Float)
    longitude = Column(Float)
    location_name = Column(String)
    city_hashtag = Column(String)
    filter_age_min = Column(Integer, default=18)
    filter_age_max = Column(Integer, default=60)
    
    is_premium = Column(Boolean, default=False) 
    is_vip = Column(Boolean, default=False)      
    is_vip_plus = Column(Boolean, default=False) 
    vip_expires_at = Column(DateTime, nullable=True) 
    
    poin_balance = Column(BigInteger, default=0) 
    has_withdrawn_before = Column(Boolean, default=False) 
    last_active_at = Column(DateTime, nullable=True) 
    
    daily_feed_text_quota = Column(Integer, default=3)
    daily_feed_photo_quota = Column(Integer, default=1)
    daily_open_profile_quota = Column(Integer, default=0) 
    daily_unmask_quota = Column(Integer, default=0)       
    daily_message_quota = Column(Integer, default=0)      
    daily_swipe_count = Column(Integer, default=0)
    
    extra_feed_text_quota = Column(Integer, default=0)
    extra_feed_photo_quota = Column(Integer, default=0)
    extra_message_quota = Column(Integer, default=0)
    
    last_swipe_at = Column(DateTime, default=datetime.datetime.utcnow)
    weekly_free_boost = Column(Integer, default=0) 
    paid_boost_balance = Column(Integer, default=0) 
    last_boost_date = Column(String, nullable=True) 

class PointLog(Base):
    __tablename__ = "point_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    amount = Column(Integer)
    source = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class UserNotification(Base):
    __tablename__ = "user_notifications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    type = Column(String) 
    sender_id = Column(BigInteger, nullable=True)
    content = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class SwipeHistory(Base):
    __tablename__ = "swipe_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    target_id = Column(BigInteger)
    action = Column(String) 
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class ReferralTracking(Base):
    __tablename__ = "referral_tracking"
    id = Column(Integer, primary_key=True, autoincrement=True)
    referrer_id = Column(BigInteger, ForeignKey("users.id"))
    referred_id = Column(BigInteger, ForeignKey("users.id"))
    is_active = Column(Boolean, default=True)
    is_completed = Column(Boolean, default=False)
    week_1_done = Column(Boolean, default=False)
    week_2_done = Column(Boolean, default=False)
    week_3_done = Column(Boolean, default=False)
    week_4_done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class WithdrawRequest(Base):
    __tablename__ = "withdraw_requests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    amount_poin = Column(Integer)
    amount_rp = Column(Integer)
    wallet_type = Column(String)
    wallet_number = Column(String)
    wallet_name = Column(String)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class DailyInteraction(Base):
    __tablename__ = "daily_interactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    target_id = Column(BigInteger)
    action = Column(String) 
    date_str = Column(String) 

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    target_id = Column(BigInteger)
    expires_at = Column(BigInteger) 

# ==========================================
# 2. DATABASE SERVICE (EKSEKUTOR QUERY)
# ==========================================
class DatabaseService:
    def __init__(self, url: str):
        if url.startswith("postgres://"): 
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url: 
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            
        self.engine = create_async_engine(url, echo=False, pool_pre_ping=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    async def create_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            if "postgres" in str(self.engine.url):
                queries = [
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date TIMESTAMP;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_feed_text_quota INTEGER DEFAULT 3;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_feed_photo_quota INTEGER DEFAULT 1;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_open_profile_quota INTEGER DEFAULT 0;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_unmask_quota INTEGER DEFAULT 0;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_message_quota INTEGER DEFAULT 0;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_swipe_count INTEGER DEFAULT 0;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_feed_text_quota INTEGER DEFAULT 0;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_feed_photo_quota INTEGER DEFAULT 0;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_message_quota INTEGER DEFAULT 0;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_swipe_at TIMESTAMP;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_free_boost INTEGER DEFAULT 0;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS paid_boost_balance INTEGER DEFAULT 0;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_boost_date VARCHAR;"
                ]
                for q in queries:
                    try: await conn.execute(text(q))
                    except Exception: pass

    async def get_user(self, user_id: int):
        async with self.session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            return result.scalar_one_or_none()

    async def update_user_location(self, user_id: int, lat: float, lng: float, loc_name: str, hashtag: str):
        async with self.session_factory() as session:
            user = await session.get(User, user_id)
            if user:
                user.latitude, user.longitude = lat, lng
                user.location_name, user.city_hashtag = loc_name, hashtag
                await session.commit()

    async def update_main_photo(self, user_id: int, photo_id: str):
        async with self.session_factory() as session:
            user = await session.get(User, user_id)
            if user:
                user.photo_id = photo_id
                await session.commit()

    async def manage_extra_photo(self, user_id: int, photo_id: str, action: str):
        async with self.session_factory() as session:
            user = await session.get(User, user_id)
            if user:
                current_photos = list(user.extra_photos) if user.extra_photos else []
                if action == 'add' and len(current_photos) < 2: current_photos.append(photo_id)
                elif action == 'remove' and photo_id in current_photos: current_photos.remove(photo_id)
                user.extra_photos = current_photos
                await session.commit()

    async def reset_daily_quotas(self):
        async with self.session_factory() as session:
            await session.execute(update(User).where(User.is_vip_plus == True).values(daily_feed_text_quota=10, daily_feed_photo_quota=5, daily_message_quota=10, daily_open_profile_quota=10, daily_unmask_quota=10, daily_swipe_count=0))
            await session.execute(update(User).where(and_(User.is_vip == True, User.is_vip_plus == False)).values(daily_feed_text_quota=10, daily_feed_photo_quota=5, daily_message_quota=10, daily_open_profile_quota=10, daily_unmask_quota=0, daily_swipe_count=0))
            await session.execute(update(User).where(and_(User.is_vip == False, User.is_vip_plus == False)).values(daily_feed_text_quota=3, daily_feed_photo_quota=1, daily_message_quota=0, daily_open_profile_quota=0, daily_unmask_quota=0, daily_swipe_count=0))
            await session.commit()

    async def reset_weekly_quotas(self):
        async with self.session_factory() as session:
            await session.execute(update(User).where(User.is_vip_plus == True).values(weekly_free_boost=1))
            await session.commit()

    async def check_expired_vip(self):
        async with self.session_factory() as session:
            now = datetime.datetime.utcnow()
            await session.execute(update(User).where(and_(User.vip_expires_at != None, User.vip_expires_at < now)).values(is_vip=False, is_vip_plus=False, vip_expires_at=None))
            await session.commit()

    async def use_message_quota(self, user_id: int) -> bool:
        async with self.session_factory() as session:
            user = await session.get(User, user_id)
            if not user: return False
            if user.daily_message_quota > 0: user.daily_message_quota -= 1
            elif user.extra_message_quota > 0: user.extra_message_quota -= 1
            else: return False
            await session.commit()
            return True

    async def use_unmask_quota(self, user_id: int) -> bool:
        async with self.session_factory() as session:
            user = await session.get(User, user_id)
            if user and (user.is_vip or user.is_vip_plus) and user.daily_open_profile_quota > 0:
                user.daily_open_profile_quota -= 1
                await session.commit()
                return True
            return False

    async def use_unmask_anon_quota(self, user_id: int) -> bool:
        async with self.session_factory() as session:
            user = await session.get(User, user_id)
            if user and user.is_vip_plus and user.daily_unmask_quota > 0:
                user.daily_unmask_quota -= 1
                await session.commit()
                return True
            return False

    async def add_points_with_log(self, user_id: int, amount: int, source: str) -> bool:
        async with self.session_factory() as session:
            user = await session.get(User, user_id)
            if not user: return False
            user.poin_balance += amount
            session.add(PointLog(user_id=user_id, amount=amount, source=source))
            await session.commit()
            return True

    async def check_bonus_exists(self, source_key: str) -> bool:
        async with self.session_factory() as session:
            res = await session.execute(select(PointLog).where(PointLog.source == source_key))
            return res.scalar_one_or_none() is not None

    async def log_and_check_daily_reward(self, user_id: int, target_id: int, action: str) -> bool:
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        async with self.session_factory() as session:
            res = await session.execute(select(DailyInteraction).where(and_(DailyInteraction.user_id == user_id, DailyInteraction.target_id == target_id, DailyInteraction.action == action, DailyInteraction.date_str == today_str)))
            if res.scalar_one_or_none(): return False 
            session.add(DailyInteraction(user_id=user_id, target_id=target_id, action=action, date_str=today_str))
            await session.commit()
            return True

    async def get_active_chat_session(self, user_id: int, target_id: int):
        async with self.session_factory() as session:
            res = await session.execute(select(ChatSession).where(( (ChatSession.user_id == user_id) & (ChatSession.target_id == target_id) ) | ( (ChatSession.user_id == target_id) & (ChatSession.target_id == user_id) )))
            session_data = res.scalar_one_or_none()
            return session_data.expires_at if session_data else None

    async def upsert_chat_session(self, user_id: int, target_id: int, expires_at: int):
        async with self.session_factory() as session:
            res = await session.execute(select(ChatSession).where(( (ChatSession.user_id == user_id) & (ChatSession.target_id == target_id) ) | ( (ChatSession.user_id == target_id) & (ChatSession.target_id == user_id) )))
            session_data = res.scalar_one_or_none()
            if session_data: session_data.expires_at = expires_at
            else: session.add(ChatSession(user_id=user_id, target_id=target_id, expires_at=expires_at))
            await session.commit()

    async def record_swipe(self, user_id: int, target_id: int, action: str):
        async with self.session_factory() as session:
            user = await session.get(User, user_id)
            if user:
                user.daily_swipe_count += 1
                session.add(SwipeHistory(user_id=user_id, target_id=target_id, action=action))
                await session.commit()

    # --- PUSAT NOTIFIKASI & LOGIKA ---
    async def get_all_unread_counts(self, user_id: int) -> dict:
        async with self.session_factory() as session:
            query = select(UserNotification.type, func.count(UserNotification.id)).where(
                and_(UserNotification.user_id == user_id, UserNotification.is_read == False)
            ).group_by(UserNotification.type)
            
            result = await session.execute(query)
            counts = {'unmask': 0, 'inbox': 0, 'match': 0, 'like': 0, 'view': 0}
            
            for row in result.all():
                notif_type = row[0].upper()
                count_val = row[1]
                if notif_type == 'UNMASK_CHAT': counts['unmask'] = count_val
                elif notif_type == 'CHAT': counts['inbox'] = count_val
                elif notif_type == 'MATCH': counts['match'] = count_val
                elif notif_type == 'LIKE': counts['like'] = count_val
                elif notif_type == 'VIEW': counts['view'] = count_val
                
            return counts

    async def get_interaction_list(self, user_id: int, notif_type: str, limit=10):
        async with self.session_factory() as session:
            user_db = await session.get(User, user_id)
            expiry_hours = 48 if (user_db and user_db.is_vip_plus) else 24
            time_limit = datetime.datetime.utcnow() - datetime.timedelta(hours=expiry_hours)
            
            if notif_type == "CHAT":
                type_filter = UserNotification.type == "CHAT"
            elif notif_type == "UNMASK_CHAT":
                type_filter = UserNotification.type == "UNMASK_CHAT"
            else:
                type_filter = UserNotification.type.ilike(f"%{notif_type}%")

            query = select(User, UserNotification.created_at).join(
                UserNotification, UserNotification.sender_id == User.id
            ).where(
                and_(
                    UserNotification.user_id == user_id,
                    type_filter,
                    or_(
                        not_(UserNotification.type.in_(["CHAT", "UNMASK_CHAT"])),
                        UserNotification.created_at > time_limit
                    )
                )
            ).order_by(UserNotification.created_at.desc())
            
            result = await session.execute(query)
            unique_users = []
            seen_ids = set()
            for row in result.all():
                u = row[0]
                if u.id not in seen_ids:
                    seen_ids.add(u.id)
                    u.notif_date = row[1] 
                    unique_users.append(u)
                    if len(unique_users) >= limit: break
            
            # KITA HAPUS AUTO-READ DI SINI. Angka tidak akan hilang sebelum pesan benar-benar dibuka.
            return unique_users

    # --- FUNGSI BARU UNTUK MENGHILANGKAN ANGKA (N) SETELAH DIBUKA ---
    async def mark_notif_read(self, user_id: int, sender_id: int, notif_type: str):
        async with self.session_factory() as session:
            await session.execute(
                update(UserNotification).where(
                    and_(
                        UserNotification.user_id == user_id,
                        UserNotification.sender_id == sender_id,
                        UserNotification.type == notif_type
                    )
                ).values(is_read=True)
            )
            await session.commit()

    async def process_match_logic(self, user_id: int, target_id: int):
        async with self.session_factory() as session:
            check = await session.execute(
                select(UserNotification).where(
                    and_(
                        UserNotification.user_id == user_id,
                        UserNotification.sender_id == target_id,
                        UserNotification.type == "LIKE"
                    )
                )
            )
            like_entry = check.scalar_one_or_none()
            
            if like_entry:
                await session.delete(like_entry)
                session.add(UserNotification(user_id=user_id, sender_id=target_id, type="MATCH"))
                session.add(UserNotification(user_id=target_id, sender_id=user_id, type="MATCH"))
                await session.commit()
                return True
            return False

    async def remove_interaction(self, user_id: int, target_id: int, notif_type: str):
        async with self.session_factory() as session:
            await session.execute(
                delete(UserNotification).where(
                    and_(
                        UserNotification.user_id == user_id,
                        UserNotification.sender_id == target_id,
                        UserNotification.type.ilike(f"%{notif_type}%")
                    )
                )
            )
            await session.commit()
        
    async def award_reply_points(self, user_id: int, target_id: int, context: str):
        amount = 500 if context == "unmask" else 200
        bonus_key = f"REWARD_{context.upper()}_{target_id}"
        
        async with self.session_factory() as session:
            check = await session.execute(select(PointLog).where(and_(PointLog.user_id == user_id, PointLog.source == bonus_key)))
            if not check.scalar_one_or_none():
                user_db = await session.get(User, user_id)
                user_db.poin_balance += amount
                session.add(PointLog(user_id=user_id, amount=amount, source=bonus_key))
                await session.commit()
                return amount
        return 0
