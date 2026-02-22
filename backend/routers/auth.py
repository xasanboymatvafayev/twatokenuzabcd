from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime

from core.database import get_db
from core.security import hash_password, verify_password, create_access_token, generate_username, generate_password
from models.models import User

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class TelegramRegisterRequest(BaseModel):
    telegram_id: str
    secret: str  # Bot shared secret

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
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    if user.status.value == "blocked":
        raise HTTPException(status_code=403, detail="Account has been blocked")
    
    user.last_login = datetime.utcnow()
    await db.commit()
    
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
        balance=user.balance
    )

@router.post("/telegram-register")
async def telegram_register(request: TelegramRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Called by bot to register/login user"""
    from core.config import settings
    if request.secret != settings.SECRET_KEY[:20]:
        raise HTTPException(status_code=403, detail="Invalid secret")
    
    result = await db.execute(select(User).where(User.telegram_id == request.telegram_id))
    user = result.scalar_one_or_none()
    
    if user:
        # Existing user - return their info
        return {
            "exists": True,
            "username": user.username,
            "balance": user.balance,
            "status": user.status.value
        }
    
    # New user - create account
    username = generate_username(request.telegram_id)
    password = generate_password(12)
    
    new_user = User(
        telegram_id=request.telegram_id,
        username=username,
        password_hash=hash_password(password),
        balance=0.0
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    return {
        "exists": False,
        "username": username,
        "password": password,
        "user_id": new_user.id
    }
