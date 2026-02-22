from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, update
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta

from core.database import get_db
from core.security import get_admin_user
from models.models import User, Transaction, GameSession, UserStatus, Advertisement

router = APIRouter()

class UserActionRequest(BaseModel):
    user_id: int
    action: str  # block, unblock, freeze, unfreeze
    duration_hours: Optional[int] = None
    reason: str = ""

class GameBanRequest(BaseModel):
    user_id: int
    hours: int

class AdvertisementCreate(BaseModel):
    type: str  # banner, popup, bot_message
    title: Optional[str] = None
    content: str
    image_url: Optional[str] = None

@router.get("/stats")
async def get_stats(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Total users
    total_users_result = await db.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar()
    
    # Total balance in system
    total_balance_result = await db.execute(select(func.sum(User.balance)))
    total_balance = total_balance_result.scalar() or 0
    
    # Today's deposits
    today_deposits_result = await db.execute(
        select(func.sum(Transaction.amount)).where(
            Transaction.type == "deposit",
            Transaction.status == "approved",
            Transaction.created_at >= today
        )
    )
    today_deposits = today_deposits_result.scalar() or 0
    
    # Today's withdrawals
    today_withdrawals_result = await db.execute(
        select(func.sum(Transaction.amount)).where(
            Transaction.type == "withdrawal",
            Transaction.status == "approved",
            Transaction.created_at >= today
        )
    )
    today_withdrawals = today_withdrawals_result.scalar() or 0
    
    # House profit (losses - wins)
    total_losses_result = await db.execute(select(func.sum(User.total_losses)))
    total_losses = total_losses_result.scalar() or 0
    
    total_wins_result = await db.execute(select(func.sum(User.total_wins)))
    total_wins_w = total_wins_result.scalar() or 0
    
    house_profit = total_losses - total_wins_w
    
    # Top winners
    top_winners_result = await db.execute(
        select(User).order_by(desc(User.total_wins)).limit(10)
    )
    top_winners = top_winners_result.scalars().all()
    
    # Top losers
    top_losers_result = await db.execute(
        select(User).order_by(desc(User.total_losses)).limit(10)
    )
    top_losers = top_losers_result.scalars().all()
    
    return {
        "total_users": total_users,
        "total_balance": round(total_balance, 2),
        "today_deposits": round(today_deposits, 2),
        "today_withdrawals": round(today_withdrawals, 2),
        "house_profit": round(house_profit, 2),
        "top_winners": [
            {"username": u.username, "total_wins": u.total_wins}
            for u in top_winners
        ],
        "top_losers": [
            {"username": u.username, "total_losses": u.total_losses}
            for u in top_losers
        ]
    }

@router.get("/users")
async def list_users(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(User).order_by(desc(User.created_at)).limit(limit).offset(offset)
    if search:
        query = query.where(User.username.ilike(f"%{search}%"))
    
    result = await db.execute(query)
    users = result.scalars().all()
    
    return [
        {
            "id": u.id,
            "telegram_id": u.telegram_id,
            "username": u.username,
            "balance": u.balance,
            "total_wins": u.total_wins,
            "total_losses": u.total_losses,
            "status": u.status.value,
            "created_at": u.created_at,
            "last_login": u.last_login
        }
        for u in users
    ]

@router.post("/user/action")
async def user_action(
    request: UserActionRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.id == request.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if request.action == "block":
        user.status = UserStatus.blocked
    elif request.action == "unblock":
        user.status = UserStatus.active
    elif request.action == "freeze":
        user.status = UserStatus.frozen
    elif request.action == "unfreeze":
        user.status = UserStatus.active
    elif request.action == "game_ban":
        hours = request.duration_hours or 24
        user.games_banned_until = datetime.utcnow() + timedelta(hours=hours)
    elif request.action == "game_unban":
        user.games_banned_until = None
    elif request.action == "add_balance":
        user.balance += request.duration_hours  # Reusing field for amount
    
    await db.commit()
    return {"success": True, "user_id": request.user_id, "action": request.action}

@router.post("/advertisement")
async def create_ad(
    request: AdvertisementCreate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    ad = Advertisement(
        type=request.type,
        title=request.title,
        content=request.content,
        image_url=request.image_url
    )
    db.add(ad)
    await db.commit()
    await db.refresh(ad)
    return {"id": ad.id, "type": ad.type, "created": True}

@router.get("/advertisements")
async def get_ads(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Advertisement).where(Advertisement.is_active == True))
    ads = result.scalars().all()
    return [{"id": a.id, "type": a.type, "title": a.title, "content": a.content, "image_url": a.image_url} for a in ads]

@router.get("/active-ads")
async def get_active_ads(db: AsyncSession = Depends(get_db)):
    """Public endpoint for webapp to get banners/popups"""
    result = await db.execute(select(Advertisement).where(Advertisement.is_active == True))
    ads = result.scalars().all()
    return [{"id": a.id, "type": a.type, "title": a.title, "content": a.content, "image_url": a.image_url} for a in ads]
