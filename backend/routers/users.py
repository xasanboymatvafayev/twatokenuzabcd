from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel

from core.database import get_db
from core.security import get_current_user
from models.models import User, Transaction, GameSession

router = APIRouter()

@router.get("/me")
async def get_profile(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "telegram_id": current_user.telegram_id,
        "username": current_user.username,
        "balance": current_user.balance,
        "total_wins": current_user.total_wins,
        "total_losses": current_user.total_losses,
        "status": current_user.status.value,
        "created_at": current_user.created_at,
        "last_login": current_user.last_login
    }

@router.get("/transactions")
async def get_transactions(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == current_user.id)
        .order_by(desc(Transaction.created_at))
        .limit(limit).offset(offset)
    )
    transactions = result.scalars().all()
    return [
        {
            "id": t.id,
            "type": t.type.value,
            "amount": t.amount,
            "balance_before": t.balance_before,
            "balance_after": t.balance_after,
            "status": t.status,
            "created_at": t.created_at
        }
        for t in transactions
    ]

@router.get("/game-history")
async def get_game_history(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(GameSession)
        .where(GameSession.user_id == current_user.id)
        .order_by(desc(GameSession.created_at))
        .limit(limit)
    )
    sessions = result.scalars().all()
    return [
        {
            "id": s.id,
            "game_type": s.game_type.value,
            "bet_amount": s.bet_amount,
            "win_amount": s.win_amount,
            "multiplier": s.multiplier,
            "result": s.result,
            "created_at": s.created_at
        }
        for s in sessions
    ]

from core.security import verify_password, hash_password
from pydantic import BaseModel

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Joriy parol noto'g'ri!")
    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="Parol kamida 8 belgi bo'lsin!")
    current_user.password_hash = hash_password(request.new_password)
    await db.commit()
    return {"success": True, "message": "Parol muvaffaqiyatli yangilandi!"}
