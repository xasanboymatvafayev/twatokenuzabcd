from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from core.database import get_db
from core.security import get_current_user, get_admin_user
from models.models import User, PromoCode, PromoCodeUsage, Transaction, TransactionType

router = APIRouter()

class PromoCodeCreate(BaseModel):
    code: str
    bonus_percent: float = 0
    bonus_fixed: float = 0
    max_uses: Optional[int] = None
    expires_at: Optional[datetime] = None

class PromoCodeApply(BaseModel):
    code: str
    deposit_amount: float = 0  # For percent bonus

@router.post("/admin/create")
async def create_promo(
    request: PromoCodeCreate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    promo = PromoCode(
        code=request.code.upper(),
        bonus_percent=request.bonus_percent,
        bonus_fixed=request.bonus_fixed,
        max_uses=request.max_uses,
        expires_at=request.expires_at
    )
    db.add(promo)
    await db.commit()
    await db.refresh(promo)
    return {"id": promo.id, "code": promo.code, "created": True}

@router.post("/apply")
async def apply_promo(
    request: PromoCodeApply,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PromoCode).where(PromoCode.code == request.code.upper())
    )
    promo = result.scalar_one_or_none()
    
    if not promo or not promo.is_active:
        raise HTTPException(status_code=404, detail="Invalid promo code")
    
    if promo.expires_at and datetime.utcnow() > promo.expires_at:
        raise HTTPException(status_code=400, detail="Promo code expired")
    
    if promo.max_uses and promo.used_count >= promo.max_uses:
        raise HTTPException(status_code=400, detail="Promo code usage limit reached")
    
    # Check if user already used this code
    usage_result = await db.execute(
        select(PromoCodeUsage).where(
            PromoCodeUsage.user_id == current_user.id,
            PromoCodeUsage.promo_code_id == promo.id
        )
    )
    if usage_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You already used this promo code")
    
    # Calculate bonus
    bonus = promo.bonus_fixed
    if promo.bonus_percent > 0 and request.deposit_amount > 0:
        bonus += request.deposit_amount * (promo.bonus_percent / 100)
    
    if bonus <= 0:
        raise HTTPException(status_code=400, detail="No bonus applicable")
    
    # Apply bonus
    balance_before = current_user.balance
    current_user.balance += bonus
    
    tx = Transaction(
        user_id=current_user.id,
        type=TransactionType.bonus,
        amount=bonus,
        balance_before=balance_before,
        balance_after=current_user.balance,
        status="approved",
        note=f"Promo: {promo.code}"
    )
    db.add(tx)
    
    usage = PromoCodeUsage(
        promo_code_id=promo.id,
        user_id=current_user.id,
        bonus_received=bonus
    )
    db.add(usage)
    
    promo.used_count += 1
    await db.commit()
    
    return {
        "success": True,
        "bonus_received": bonus,
        "new_balance": current_user.balance
    }

@router.get("/admin/list")
async def list_promos(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(PromoCode))
    promos = result.scalars().all()
    return [
        {
            "id": p.id, "code": p.code,
            "bonus_percent": p.bonus_percent,
            "bonus_fixed": p.bonus_fixed,
            "used_count": p.used_count,
            "max_uses": p.max_uses,
            "is_active": p.is_active,
            "expires_at": p.expires_at
        }
        for p in promos
    ]
