from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime
import random, string

from core.database import get_db
from core.security import hash_password, verify_password, create_access_token
from models.models import User

router = APIRouter()

def gen_pass():
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=8))

class LoginRequest(BaseModel):
    username: str
    password: str

class TelegramRequest(BaseModel):
    telegram_id: str
    secret: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    balance: float

def check_secret(secret: str):
    from core.config import settings
    if secret != settings.SECRET_KEY[:20]:
        raise HTTPException(status_code=403, detail="Invalid secret")

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == request.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Login yoki parol noto'g'ri")
    if user.status.value == "blocked":
        raise HTTPException(status_code=403, detail="Hisob bloklangan")
    user.last_login = datetime.utcnow()
    await db.commit()
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token, user_id=user.id, username=user.username, balance=user.balance)

@router.post("/telegram-register")
async def telegram_register(request: TelegramRequest, db: AsyncSession = Depends(get_db)):
    check_secret(request.secret)
    result = await db.execute(select(User).where(User.telegram_id == request.telegram_id))
    user = result.scalar_one_or_none()
    
    if user:
        # Eski user - parol o'zgarmaydi
        return {
            "exists": True,
            "username": user.username,
            "balance": user.balance,
            "status": user.status.value
        }
    
    # Yangi user - 1 marta parol
    username = request.telegram_id
    password = gen_pass()
    new_user = User(
        telegram_id=request.telegram_id,
        username=username,
        password_hash=hash_password(password),
        balance=0.0
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"exists": False, "username": username, "password": password, "user_id": new_user.id}

@router.post("/reset-password")
async def reset_password(request: TelegramRequest, db: AsyncSession = Depends(get_db)):
    check_secret(request.secret)
    result = await db.execute(select(User).where(User.telegram_id == request.telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        # User yo'q - yangi yaratamiz
        username = request.telegram_id
        password = gen_pass()
        new_user = User(
            telegram_id=request.telegram_id,
            username=username,
            password_hash=hash_password(password),
            balance=0.0
        )
        db.add(new_user)
        await db.commit()
        return {"username": username, "password": password, "balance": 0}
    
    # User bor - parolini yangilaymiz
    password = gen_pass()
    user.password_hash = hash_password(password)
    await db.commit()
    return {"username": user.username, "password": password, "balance": user.balance}
