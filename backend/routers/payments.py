from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from datetime import datetime

from core.database import get_db
from core.security import get_current_user, get_admin_user
from models.models import User, Transaction, TransactionType

router = APIRouter()

class DepositRequest(BaseModel):
    amount: float
    payment_method: str = "manual"
    note: str = ""

class WithdrawalRequest(BaseModel):
    amount: float
    wallet_address: str
    note: str = ""

class ApproveRequest(BaseModel):
    transaction_id: int
    action: str  # "approve" or "reject"
    admin_note: str = ""

@router.post("/deposit/request")
async def request_deposit(
    request: DepositRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """User requests a deposit - admin must approve"""
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    
    tx = Transaction(
        user_id=current_user.id,
        type=TransactionType.deposit,
        amount=request.amount,
        balance_before=current_user.balance,
        balance_after=current_user.balance,  # Will update on approval
        status="pending",
        note=f"Method: {request.payment_method}. {request.note}"
    )
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    
    return {
        "transaction_id": tx.id,
        "amount": request.amount,
        "status": "pending",
        "message": "Deposit request submitted. Waiting for admin approval."
    }

@router.post("/withdrawal/request")
async def request_withdrawal(
    request: WithdrawalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    if current_user.balance < request.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    
    # Freeze amount
    current_user.balance -= request.amount
    
    tx = Transaction(
        user_id=current_user.id,
        type=TransactionType.withdrawal,
        amount=request.amount,
        balance_before=current_user.balance + request.amount,
        balance_after=current_user.balance,
        status="pending",
        note=f"Wallet: {request.wallet_address}. {request.note}"
    )
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    
    return {
        "transaction_id": tx.id,
        "amount": request.amount,
        "status": "pending",
        "new_balance": current_user.balance,
        "message": "Withdrawal request submitted. Waiting for admin approval."
    }

@router.post("/admin/approve")
async def approve_transaction(
    request: ApproveRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Transaction).where(Transaction.id == request.transaction_id))
    tx = result.scalar_one_or_none()
    
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if tx.status != "pending":
        raise HTTPException(status_code=400, detail="Transaction already processed")
    
    user_result = await db.execute(select(User).where(User.id == tx.user_id))
    user = user_result.scalar_one_or_none()
    
    if request.action == "approve":
        if tx.type == TransactionType.deposit:
            balance_before = user.balance
            user.balance += tx.amount
            tx.balance_after = user.balance
        # For withdrawal, balance already deducted on request
        
        tx.status = "approved"
        tx.approved_at = datetime.utcnow()
        tx.approved_by = admin.id
        if request.admin_note:
            tx.note = (tx.note or "") + f" | Admin: {request.admin_note}"
        
        await db.commit()
        return {"status": "approved", "new_balance": user.balance}
    
    elif request.action == "reject":
        if tx.type == TransactionType.withdrawal:
            # Refund the frozen amount
            user.balance += tx.amount
        
        tx.status = "rejected"
        tx.approved_at = datetime.utcnow()
        tx.approved_by = admin.id
        tx.note = (tx.note or "") + f" | Rejected: {request.admin_note}"
        
        await db.commit()
        return {"status": "rejected", "balance_restored": tx.type == TransactionType.withdrawal}

@router.get("/pending")
async def get_pending_transactions(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Transaction, User)
        .join(User, Transaction.user_id == User.id)
        .where(Transaction.status == "pending")
        .order_by(desc(Transaction.created_at))
    )
    rows = result.all()
    
    return [
        {
            "transaction_id": tx.id,
            "user_id": tx.user_id,
            "username": user.username,
            "type": tx.type.value,
            "amount": tx.amount,
            "note": tx.note,
            "created_at": tx.created_at
        }
        for tx, user in rows
    ]


@router.post("/admin/add-balance")
async def admin_add_balance(
    request: dict,
    db: AsyncSession = Depends(get_db)
):
    """Bot admin tomonidan chaqiriladi - balans qo'shish"""
    from core.config import settings
    if request.get("secret") != settings.SECRET_KEY[:20]:
        raise HTTPException(status_code=403, detail="Invalid secret")
    
    telegram_id = str(request.get("telegram_id"))
    amount = float(request.get("amount", 0))
    
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    balance_before = user.balance
    user.balance += amount
    
    tx = Transaction(
        user_id=user.id,
        type=TransactionType.deposit,
        amount=amount,
        balance_before=balance_before,
        balance_after=user.balance,
        status="approved",
        note="Bot orqali admin tasdiqlagan"
    )
    db.add(tx)
    await db.commit()
    return {"success": True, "new_balance": user.balance}
