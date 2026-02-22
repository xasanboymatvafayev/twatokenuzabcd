from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime

from core.database import get_db
from core.security import hash_password, verify_password, create_access_token
from models.models import User
import random, string

router = APIRouter()

def generate_password(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

class LoginRequest(BaseModel):
    username: str
    password: str

class TelegramRegisterRequest(BaseModel):
    telegram_id: str
    secret: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    balance: float

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
async def telegram_register(request: TelegramRegisterRequest, db: AsyncSession = Depends(get_db)):
    from core.config import settings
    if request.secret != settings.SECRET_KEY[:20]:
        raise HTTPException(status_code=403, detail="Invalid secret")

    result = await db.execute(select(User).where(User.telegram_id == request.telegram_id))
    user = result.scalar_one_or_none()

    if user:
        return {
            "exists": True,
            "username": user.username,
            "balance": user.balance,
            "status": user.status.value,
            "created_at": str(user.created_at)
        }

    # Yangi foydalanuvchi
    username = f"user_{request.telegram_id}"
    password = generate_password(10)

    new_user = User(
        telegram_id=request.telegram_id,
        username=username,
        password_hash=hash_password(password),
        balance=0.0
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Parolni ochiq holda qaytaramiz (faqat bir marta ko'rsatiladi)
    return {
        "exists": False,
        "username": username,
        "password": password,
        "user_id": new_user.id
    }
