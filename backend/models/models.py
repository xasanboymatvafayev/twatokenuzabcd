from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
import enum

class UserStatus(str, enum.Enum):
    active = "active"
    blocked = "blocked"
    frozen = "frozen"

class TransactionType(str, enum.Enum):
    deposit = "deposit"
    withdrawal = "withdrawal"
    game_win = "game_win"
    game_loss = "game_loss"
    bonus = "bonus"

class GameType(str, enum.Enum):
    aviator = "aviator"
    apple_fortune = "apple_fortune"
    mines = "mines"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    balance = Column(Float, default=0.0)
    total_wins = Column(Float, default=0.0)
    total_losses = Column(Float, default=0.0)
    status = Column(Enum(UserStatus), default=UserStatus.active)
    games_banned_until = Column(DateTime, nullable=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    last_login = Column(DateTime, nullable=True)
    
    transactions = relationship("Transaction", back_populates="user")
    game_sessions = relationship("GameSession", back_populates="user")

class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(Enum(TransactionType), nullable=False)
    amount = Column(Float, nullable=False)
    balance_before = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    status = Column(String, default="pending")  # pending, approved, rejected
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(Integer, nullable=True)
    
    user = relationship("User", back_populates="transactions")

class GameSession(Base):
    __tablename__ = "game_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    game_type = Column(Enum(GameType), nullable=False)
    bet_amount = Column(Float, nullable=False)
    win_amount = Column(Float, default=0.0)
    multiplier = Column(Float, default=1.0)
    result = Column(String)  # win, loss
    game_data = Column(Text, nullable=True)  # JSON
    created_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="game_sessions")

class PromoCode(Base):
    __tablename__ = "promo_codes"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    bonus_percent = Column(Float, nullable=False)  # e.g. 50 = 50%
    bonus_fixed = Column(Float, default=0.0)  # fixed amount
    max_uses = Column(Integer, nullable=True)  # None = unlimited
    used_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    
    usages = relationship("PromoCodeUsage", back_populates="promo_code")

class PromoCodeUsage(Base):
    __tablename__ = "promo_code_usages"
    
    id = Column(Integer, primary_key=True, index=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    used_at = Column(DateTime, server_default=func.now())
    bonus_received = Column(Float, nullable=False)
    
    promo_code = relationship("PromoCode", back_populates="usages")

class Advertisement(Base):
    __tablename__ = "advertisements"
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String)  # banner, popup, bot_message
    title = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    image_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

class ActiveGame(Base):
    __tablename__ = "active_games"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    game_type = Column(Enum(GameType), nullable=False)
    bet_amount = Column(Float, nullable=False)
    game_state = Column(Text, nullable=False)  # JSON game state
    started_at = Column(DateTime, server_default=func.now())
