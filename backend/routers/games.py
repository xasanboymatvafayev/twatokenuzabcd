from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import json
import asyncio

from core.database import get_db
from core.security import get_current_user
from models.models import User, GameSession, ActiveGame, GameType, Transaction, TransactionType, UserStatus
from services.rng import (
    generate_aviator_crash_point, calculate_mines_multiplier,
    generate_mines_board, generate_apple_board, calculate_apple_multiplier,
    calculate_payout
)

router = APIRouter()

# ============= BALANCE HELPER =============
async def deduct_bet(user: User, amount: float, db: AsyncSession):
    if user.status == UserStatus.frozen:
        raise HTTPException(status_code=403, detail="Balance frozen")
    if user.games_banned_until and datetime.utcnow() < user.games_banned_until:
        raise HTTPException(status_code=403, detail="Temporarily banned from games")
    if user.balance < amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    
    balance_before = user.balance
    user.balance -= amount
    user.total_losses += amount
    
    tx = Transaction(
        user_id=user.id, type=TransactionType.game_loss,
        amount=amount, balance_before=balance_before,
        balance_after=user.balance, status="approved"
    )
    db.add(tx)
    await db.commit()

async def add_winnings(user: User, amount: float, db: AsyncSession):
    balance_before = user.balance
    user.balance += amount
    user.total_wins += amount
    
    tx = Transaction(
        user_id=user.id, type=TransactionType.game_win,
        amount=amount, balance_before=balance_before,
        balance_after=user.balance, status="approved"
    )
    db.add(tx)
    await db.commit()

# ============= AVIATOR =============
class AviatorStartRequest(BaseModel):
    bet_amount: float
    auto_cashout: Optional[float] = None

class AviatorCashoutRequest(BaseModel):
    session_id: int

@router.post("/aviator/start")
async def aviator_start(
    request: AviatorStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if request.bet_amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid bet amount")
    
    # Check no active game
    result = await db.execute(select(ActiveGame).where(ActiveGame.user_id == current_user.id))
    active = result.scalar_one_or_none()
    if active:
        raise HTTPException(status_code=400, detail="You already have an active game")
    
    await deduct_bet(current_user, request.bet_amount, db)
    
    crash_point = generate_aviator_crash_point()
    
    game_state = {
        "crash_point": crash_point,
        "auto_cashout": request.auto_cashout,
        "cashed_out": False,
        "current_multiplier": 1.0
    }
    
    active_game = ActiveGame(
        user_id=current_user.id,
        game_type=GameType.aviator,
        bet_amount=request.bet_amount,
        game_state=json.dumps(game_state)
    )
    db.add(active_game)
    
    session = GameSession(
        user_id=current_user.id,
        game_type=GameType.aviator,
        bet_amount=request.bet_amount,
        result="pending"
    )
    db.add(session)
    await db.commit()
    await db.refresh(active_game)
    await db.refresh(session)
    
    return {
        "game_id": active_game.id,
        "session_id": session.id,
        "bet_amount": request.bet_amount,
        "crash_point": crash_point,  # In production: hide this, reveal on crash
        "message": "Game started! Watch the multiplier!"
    }

@router.post("/aviator/cashout")
async def aviator_cashout(
    request: AviatorCashoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ActiveGame).where(ActiveGame.user_id == current_user.id))
    active = result.scalar_one_or_none()
    
    if not active or active.game_type != GameType.aviator:
        raise HTTPException(status_code=400, detail="No active Aviator game")
    
    state = json.loads(active.game_state)
    if state["cashed_out"]:
        raise HTTPException(status_code=400, detail="Already cashed out")
    
    current_multiplier = state.get("current_multiplier", 1.0)
    crash_point = state["crash_point"]
    
    if current_multiplier >= crash_point:
        # Too late - already crashed
        raise HTTPException(status_code=400, detail="Plane already crashed!")
    
    winnings = calculate_payout(active.bet_amount, current_multiplier)
    await add_winnings(current_user, winnings, db)
    
    # Update session
    session_result = await db.execute(
        select(GameSession).where(
            GameSession.user_id == current_user.id,
            GameSession.result == "pending"
        )
    )
    session = session_result.scalar_one_or_none()
    if session:
        session.win_amount = winnings
        session.multiplier = current_multiplier
        session.result = "win"
        session.finished_at = datetime.utcnow()
    
    await db.delete(active)
    await db.commit()
    
    return {
        "multiplier": current_multiplier,
        "win_amount": winnings,
        "new_balance": current_user.balance
    }

@router.post("/aviator/update-multiplier/{game_id}")
async def update_aviator_multiplier(
    game_id: int,
    multiplier: float,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Client reports current multiplier; server checks if crashed"""
    result = await db.execute(select(ActiveGame).where(
        ActiveGame.id == game_id,
        ActiveGame.user_id == current_user.id
    ))
    active = result.scalar_one_or_none()
    if not active:
        return {"crashed": True, "crash_point": 0}
    
    state = json.loads(active.game_state)
    crash_point = state["crash_point"]
    
    # Update current multiplier
    state["current_multiplier"] = multiplier
    active.game_state = json.dumps(state)
    await db.commit()
    
    if multiplier >= crash_point:
        # Game crashed
        session_result = await db.execute(
            select(GameSession).where(
                GameSession.user_id == current_user.id,
                GameSession.result == "pending"
            )
        )
        session = session_result.scalar_one_or_none()
        if session:
            session.result = "loss"
            session.finished_at = datetime.utcnow()
        
        await db.delete(active)
        await db.commit()
        return {"crashed": True, "crash_point": crash_point}
    
    # Auto cashout check
    if state.get("auto_cashout") and multiplier >= state["auto_cashout"]:
        winnings = calculate_payout(active.bet_amount, state["auto_cashout"])
        await add_winnings(current_user, winnings, db)
        
        if session_result and session:
            session.win_amount = winnings
            session.multiplier = state["auto_cashout"]
            session.result = "win"
            session.finished_at = datetime.utcnow()
        
        await db.delete(active)
        await db.commit()
        return {"auto_cashed_out": True, "multiplier": state["auto_cashout"], "win_amount": winnings}
    
    return {"crashed": False, "crash_point": None}

# ============= MINES =============
class MinesStartRequest(BaseModel):
    bet_amount: float
    mine_count: int = 5

class MinesRevealRequest(BaseModel):
    cell_index: int

@router.post("/mines/start")
async def mines_start(
    request: MinesStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not 1 <= request.mine_count <= 24:
        raise HTTPException(status_code=400, detail="Mine count must be 1-24")
    if request.bet_amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid bet")
    
    result = await db.execute(select(ActiveGame).where(ActiveGame.user_id == current_user.id))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already have an active game")
    
    await deduct_bet(current_user, request.bet_amount, db)
    
    mines = generate_mines_board(25, request.mine_count)
    
    game_state = {
        "mines": mines,
        "mine_count": request.mine_count,
        "revealed": [],
        "safe_revealed": 0
    }
    
    active_game = ActiveGame(
        user_id=current_user.id,
        game_type=GameType.mines,
        bet_amount=request.bet_amount,
        game_state=json.dumps(game_state)
    )
    db.add(active_game)
    
    session = GameSession(
        user_id=current_user.id,
        game_type=GameType.mines,
        bet_amount=request.bet_amount,
        result="pending"
    )
    db.add(session)
    await db.commit()
    await db.refresh(active_game)
    
    return {
        "game_id": active_game.id,
        "mine_count": request.mine_count,
        "bet_amount": request.bet_amount,
        "current_multiplier": 1.0
    }

@router.post("/mines/reveal")
async def mines_reveal(
    request: MinesRevealRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ActiveGame).where(
        ActiveGame.user_id == current_user.id,
        ActiveGame.game_type == GameType.mines
    ))
    active = result.scalar_one_or_none()
    if not active:
        raise HTTPException(status_code=400, detail="No active Mines game")
    
    state = json.loads(active.game_state)
    
    if request.cell_index in state["revealed"]:
        raise HTTPException(status_code=400, detail="Cell already revealed")
    
    state["revealed"].append(request.cell_index)
    is_mine = request.cell_index in state["mines"]
    
    if is_mine:
        # Game over
        session_result = await db.execute(
            select(GameSession).where(
                GameSession.user_id == current_user.id,
                GameSession.result == "pending"
            )
        )
        session = session_result.scalar_one_or_none()
        if session:
            session.result = "loss"
            session.finished_at = datetime.utcnow()
        
        await db.delete(active)
        await db.commit()
        
        return {
            "hit_mine": True,
            "mines": state["mines"],
            "balance": current_user.balance
        }
    
    state["safe_revealed"] += 1
    active.game_state = json.dumps(state)
    
    multiplier = calculate_mines_multiplier(state["safe_revealed"], 25, state["mine_count"])
    potential_win = calculate_payout(active.bet_amount, multiplier)
    
    await db.commit()
    
    return {
        "hit_mine": False,
        "cell_index": request.cell_index,
        "safe_revealed": state["safe_revealed"],
        "multiplier": multiplier,
        "potential_win": potential_win
    }

@router.post("/mines/cashout")
async def mines_cashout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ActiveGame).where(
        ActiveGame.user_id == current_user.id,
        ActiveGame.game_type == GameType.mines
    ))
    active = result.scalar_one_or_none()
    if not active:
        raise HTTPException(status_code=400, detail="No active Mines game")
    
    state = json.loads(active.game_state)
    if state["safe_revealed"] == 0:
        raise HTTPException(status_code=400, detail="Must reveal at least one cell")
    
    multiplier = calculate_mines_multiplier(state["safe_revealed"], 25, state["mine_count"])
    winnings = calculate_payout(active.bet_amount, multiplier)
    
    await add_winnings(current_user, winnings, db)
    
    session_result = await db.execute(
        select(GameSession).where(
            GameSession.user_id == current_user.id,
            GameSession.result == "pending"
        )
    )
    session = session_result.scalar_one_or_none()
    if session:
        session.win_amount = winnings
        session.multiplier = multiplier
        session.result = "win"
        session.finished_at = datetime.utcnow()
    
    await db.delete(active)
    await db.commit()
    
    return {
        "multiplier": multiplier,
        "win_amount": winnings,
        "new_balance": current_user.balance
    }

# ============= APPLE OF FORTUNE =============
class AppleStartRequest(BaseModel):
    bet_amount: float

class AppleChooseRequest(BaseModel):
    row: int
    col: int

@router.post("/apple/start")
async def apple_start(
    request: AppleStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if request.bet_amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid bet")
    
    result = await db.execute(select(ActiveGame).where(ActiveGame.user_id == current_user.id))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already have an active game")
    
    await deduct_bet(current_user, request.bet_amount, db)
    
    board = generate_apple_board(rows=5, cols=3, bad_per_row=1)
    
    game_state = {
        "board": board,
        "current_row": 0,
        "rows": 5,
        "cols": 3
    }
    
    active_game = ActiveGame(
        user_id=current_user.id,
        game_type=GameType.apple_fortune,
        bet_amount=request.bet_amount,
        game_state=json.dumps(game_state)
    )
    db.add(active_game)
    
    session = GameSession(
        user_id=current_user.id,
        game_type=GameType.apple_fortune,
        bet_amount=request.bet_amount,
        result="pending"
    )
    db.add(session)
    await db.commit()
    await db.refresh(active_game)
    
    return {
        "game_id": active_game.id,
        "rows": 5,
        "cols": 3,
        "current_row": 0,
        "multiplier": 1.0,
        "bet_amount": request.bet_amount
    }

@router.post("/apple/choose")
async def apple_choose(
    request: AppleChooseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ActiveGame).where(
        ActiveGame.user_id == current_user.id,
        ActiveGame.game_type == GameType.apple_fortune
    ))
    active = result.scalar_one_or_none()
    if not active:
        raise HTTPException(status_code=400, detail="No active Apple game")
    
    state = json.loads(active.game_state)
    current_row = state["current_row"]
    
    if request.row != current_row:
        raise HTTPException(status_code=400, detail="Invalid row")
    if request.col < 0 or request.col >= state["cols"]:
        raise HTTPException(status_code=400, detail="Invalid column")
    
    is_safe = state["board"][current_row][request.col]
    row_result = state["board"][current_row]
    
    if not is_safe:
        # Bad apple - game over
        session_result = await db.execute(
            select(GameSession).where(
                GameSession.user_id == current_user.id,
                GameSession.result == "pending"
            )
        )
        session = session_result.scalar_one_or_none()
        if session:
            session.result = "loss"
            session.finished_at = datetime.utcnow()
        
        await db.delete(active)
        await db.commit()
        
        return {
            "is_safe": False,
            "row_result": row_result,
            "game_over": True,
            "balance": current_user.balance
        }
    
    next_row = current_row + 1
    state["current_row"] = next_row
    active.game_state = json.dumps(state)
    
    multiplier = calculate_apple_multiplier(next_row, state["cols"])
    potential_win = calculate_payout(active.bet_amount, multiplier)
    
    game_complete = next_row >= state["rows"]
    
    if game_complete:
        # Won all rows!
        await add_winnings(current_user, potential_win, db)
        
        session_result = await db.execute(
            select(GameSession).where(
                GameSession.user_id == current_user.id,
                GameSession.result == "pending"
            )
        )
        session = session_result.scalar_one_or_none()
        if session:
            session.win_amount = potential_win
            session.multiplier = multiplier
            session.result = "win"
            session.finished_at = datetime.utcnow()
        
        await db.delete(active)
        await db.commit()
        
        return {
            "is_safe": True,
            "row_result": row_result,
            "next_row": next_row,
            "multiplier": multiplier,
            "potential_win": potential_win,
            "game_complete": True,
            "win_amount": potential_win
        }
    
    await db.commit()
    
    return {
        "is_safe": True,
        "row_result": row_result,
        "next_row": next_row,
        "multiplier": multiplier,
        "potential_win": potential_win,
        "game_complete": False
    }

@router.post("/apple/cashout")
async def apple_cashout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ActiveGame).where(
        ActiveGame.user_id == current_user.id,
        ActiveGame.game_type == GameType.apple_fortune
    ))
    active = result.scalar_one_or_none()
    if not active:
        raise HTTPException(status_code=400, detail="No active Apple game")
    
    state = json.loads(active.game_state)
    current_row = state["current_row"]
    
    if current_row == 0:
        raise HTTPException(status_code=400, detail="Must complete at least one row")
    
    multiplier = calculate_apple_multiplier(current_row, state["cols"])
    winnings = calculate_payout(active.bet_amount, multiplier)
    
    await add_winnings(current_user, winnings, db)
    
    session_result = await db.execute(
        select(GameSession).where(
            GameSession.user_id == current_user.id,
            GameSession.result == "pending"
        )
    )
    session = session_result.scalar_one_or_none()
    if session:
        session.win_amount = winnings
        session.multiplier = multiplier
        session.result = "win"
        session.finished_at = datetime.utcnow()
    
    await db.delete(active)
    await db.commit()
    
    return {
        "multiplier": multiplier,
        "win_amount": winnings,
        "new_balance": current_user.balance
    }
