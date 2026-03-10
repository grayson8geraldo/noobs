"""
Risk management & position sizing for small-deposit futures trading.

Key principles
--------------
* Never risk more than a fixed % of equity per trade.
* Leverage is derived from position size and stop-loss distance, NOT chosen
  first.  We size the position so that if the stop is hit the loss equals
  the allowed risk amount.
* Hard cap on leverage to prevent liquidation surprises.
* Risk profiles scale aggression for different deposit sizes and goals.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskProfile:
    """Pre-configured risk parameters."""
    name: str
    risk_pct: float       # % of equity risked per trade
    max_leverage: float   # hard leverage cap
    min_rr: float         # minimum risk:reward to take a trade
    description: str


# ── Risk profiles ────────────────────────────────────────────────────────
# For growing $150 → $1000, "aggressive" or "turbo" are designed.
#
# Math for "aggressive" (10% risk, avg R:R 3):
#   Win $150 * 10% * 3 = $45 profit per winning trade
#   ~20 winning trades to reach $1000 (with compounding, fewer)
#   At 60% win rate over 30 days → very achievable
#
# Math for "turbo" (15% risk, avg R:R 3):
#   Win $150 * 15% * 3 = $67.5 profit per winning trade
#   ~12-15 winning trades to reach $1000
#   Higher risk of drawdown but faster acceleration

PROFILES = {
    "conservative": RiskProfile(
        name="conservative",
        risk_pct=1.5,
        max_leverage=3.0,
        min_rr=2.0,
        description="Low risk, slow growth. Good for large accounts.",
    ),
    "normal": RiskProfile(
        name="normal",
        risk_pct=3.0,
        max_leverage=7.0,
        min_rr=1.8,
        description="Balanced risk/reward. Steady compounding.",
    ),
    "aggressive": RiskProfile(
        name="aggressive",
        risk_pct=5.0,
        max_leverage=12.0,
        min_rr=1.5,
        description="High risk for small deposit acceleration. $150→$1000 target.",
    ),
    "turbo": RiskProfile(
        name="turbo",
        risk_pct=8.0,
        max_leverage=18.0,
        min_rr=1.5,
        description="Maximum aggression. Fast acceleration or fast blowup.",
    ),
}

DEFAULT_PROFILE = "aggressive"


def get_profile(name: str) -> RiskProfile:
    if name not in PROFILES:
        raise ValueError(f"Unknown profile '{name}'. Options: {', '.join(PROFILES)}")
    return PROFILES[name]


@dataclass
class PositionPlan:
    side: str               # "long" or "short"
    entry: float
    stop_loss: float
    take_profit: float
    risk_amount: float       # dollars risked
    position_size_usd: float # notional value
    quantity: float          # contracts / coins
    leverage: float
    risk_reward: float


def size_position(
    equity: float,
    entry: float,
    stop_loss: float,
    take_profit: float,
    risk_pct: float = 10.0,
    max_leverage: float = 20.0,
    fee_pct: float = 0.06,
) -> PositionPlan:
    """Calculate position size so that a stop-loss hit = *risk_pct* % of equity.

    Parameters
    ----------
    equity : float
        Current account balance (USDT).
    entry : float
        Planned entry price.
    stop_loss : float
        Stop-loss price.
    take_profit : float
        Take-profit price.
    risk_pct : float
        Max percentage of equity to risk on this trade.
    max_leverage : float
        Hard leverage cap.
    fee_pct : float
        One-way trading fee in percent (taker).
    """
    side = "long" if take_profit > entry else "short"

    sl_distance = abs(entry - stop_loss)
    if sl_distance == 0:
        raise ValueError("Stop-loss cannot equal entry price")

    sl_pct = sl_distance / entry  # fractional
    total_fee_pct = fee_pct * 2 / 100  # entry + exit
    effective_sl_pct = sl_pct + total_fee_pct

    risk_amount = equity * risk_pct / 100
    position_size_usd = risk_amount / effective_sl_pct
    leverage = position_size_usd / equity

    # clamp leverage
    if leverage > max_leverage:
        leverage = max_leverage
        position_size_usd = equity * leverage
        risk_amount = position_size_usd * effective_sl_pct

    quantity = position_size_usd / entry

    tp_distance = abs(take_profit - entry)
    risk_reward = tp_distance / sl_distance if sl_distance else 0.0

    return PositionPlan(
        side=side,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_amount=round(risk_amount, 2),
        position_size_usd=round(position_size_usd, 2),
        quantity=round(quantity, 6),
        leverage=round(leverage, 2),
        risk_reward=round(risk_reward, 2),
    )
