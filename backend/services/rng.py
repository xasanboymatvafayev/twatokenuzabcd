import random
import math
import json
from typing import List, Tuple

# ============= AVIATOR RNG =============
def generate_aviator_crash_point(house_edge: float = 0.05) -> float:
    """
    Generates crash point for Aviator game.
    Uses inverse transform sampling with house edge.
    """
    r = random.random()
    if r < house_edge:
        return 1.0  # Instant crash (house wins)
    
    # Distribution: P(X > x) = (1-h) / x for x >= 1
    crash = (1 - house_edge) / (1 - r)
    return round(max(1.0, min(crash, 100.0)), 2)

def get_aviator_multiplier_sequence(crash_point: float) -> List[float]:
    """Generate smooth multiplier increase sequence"""
    multipliers = []
    current = 1.0
    tick = 0
    
    while current < crash_point:
        multipliers.append(round(current, 2))
        # Accelerating growth
        speed = 1 + (tick * 0.001)
        current *= (1 + 0.01 * speed)
        tick += 1
        if len(multipliers) > 10000:
            break
    
    return multipliers

# ============= MINES RNG =============
def generate_mines_board(size: int = 25, mine_count: int = 5) -> List[int]:
    """Returns list of mine positions (0-indexed)"""
    positions = list(range(size))
    random.shuffle(positions)
    return positions[:mine_count]

def calculate_mines_multiplier(revealed: int, total_cells: int, mine_count: int) -> float:
    """
    Calculate multiplier for Mines game.
    Uses combinatorial probability.
    """
    safe_cells = total_cells - mine_count
    if revealed == 0:
        return 1.0
    
    # Probability of surviving revealed picks
    prob = 1.0
    for i in range(revealed):
        prob *= (safe_cells - i) / (total_cells - i)
    
    # Multiplier with house edge (5%)
    multiplier = (0.95 / prob)
    return round(max(1.0, multiplier), 2)

# ============= APPLE OF FORTUNE RNG =============
def generate_apple_board(rows: int = 5, cols: int = 3, bad_per_row: int = 1) -> List[List[bool]]:
    """
    Returns 2D board where True = safe (green), False = bad (red).
    Each row has exactly `bad_per_row` red apple(s).
    """
    board = []
    for _ in range(rows):
        row = [True] * cols
        bad_positions = random.sample(range(cols), bad_per_row)
        for pos in bad_positions:
            row[pos] = False
        board.append(row)
    return board

def calculate_apple_multiplier(row: int, cols: int = 3, bad_per_row: int = 1) -> float:
    """Multiplier increases each successful row"""
    safe_prob = (cols - bad_per_row) / cols
    multiplier = (1.0 / (safe_prob ** row)) * 0.95  # 5% house edge
    return round(max(1.0, multiplier), 2)

# ============= PAYOUT CALCULATOR =============
def calculate_payout(bet: float, multiplier: float) -> float:
    return round(bet * multiplier, 2)
