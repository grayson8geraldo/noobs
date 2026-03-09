"""
Risk management & position sizing for small-deposit futures trading.

Key principles
--------------
* Never risk more than a fixed % of equity per trade.
* Leverage is derived from position size and stop-loss distance, NOT chosen
  first.  We size the position so that if the stop is hit the loss equals
  the allowed risk amount.
* Hard cap on leverage to prevent liquidation surprises.
"""

from __future__ import annotations

from dataclasses import dataclass


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
    risk_pct: float = 2.0,
    max_leverage: float = 10.0,
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
