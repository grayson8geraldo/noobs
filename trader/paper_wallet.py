"""
Paper Wallet — virtual balance tracker for paper trading.

Tracks equity, open positions, closed trades, and P&L using real market prices
but without placing any real orders. Persists state to a JSON file so sessions
can be resumed.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import List

log = logging.getLogger("paper")

SECONDS_IN_DAY = 86400


@dataclass
class PaperTrade:
    id: int
    symbol: str
    side: str                # "long" or "short"
    entry_price: float
    quantity: float
    leverage: float
    stop_loss: float
    take_profit: float
    entry_time: str
    exit_price: float | None = None
    exit_time: str | None = None
    pnl: float = 0.0
    fee: float = 0.0
    status: str = "open"     # "open" or "closed"


@dataclass
class PaperWallet:
    initial_balance: float = 150.0
    balance: float = 150.0
    target: float = 1000.0
    target_days: int = 30
    start_time: str = ""
    trades: List[PaperTrade] = field(default_factory=list)
    _next_id: int = 1
    _state_file: str = "paper_state.json"

    def __post_init__(self):
        if not self.start_time:
            self.start_time = datetime.utcnow().isoformat()

    # ── persistence ──────────────────────────────────────────────────────

    def save(self) -> None:
        data = {
            "initial_balance": self.initial_balance,
            "balance": self.balance,
            "target": self.target,
            "target_days": self.target_days,
            "start_time": self.start_time,
            "_next_id": self._next_id,
            "trades": [asdict(t) for t in self.trades],
        }
        with open(self._state_file, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str = "paper_state.json") -> "PaperWallet":
        if not os.path.exists(path):
            wallet = cls(_state_file=path)
            wallet.save()
            return wallet
        with open(path) as f:
            data = json.load(f)
        trades = [PaperTrade(**t) for t in data.get("trades", [])]
        wallet = cls(
            initial_balance=data["initial_balance"],
            balance=data["balance"],
            target=data["target"],
            target_days=data["target_days"],
            start_time=data["start_time"],
            trades=trades,
            _next_id=data.get("_next_id", len(trades) + 1),
            _state_file=path,
        )
        return wallet

    # ── trading ──────────────────────────────────────────────────────────

    @property
    def open_positions(self) -> List[PaperTrade]:
        return [t for t in self.trades if t.status == "open"]

    @property
    def closed_trades(self) -> List[PaperTrade]:
        return [t for t in self.trades if t.status == "closed"]

    @property
    def has_open_position(self) -> bool:
        return len(self.open_positions) > 0

    def open_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        leverage: float,
        stop_loss: float,
        take_profit: float,
        fee_pct: float = 0.06,
    ) -> PaperTrade:
        notional = quantity * entry_price
        fee = notional * fee_pct / 100

        trade = PaperTrade(
            id=self._next_id,
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=datetime.utcnow().isoformat(),
            fee=round(fee, 4),
        )
        self._next_id += 1
        self.balance -= fee  # entry fee
        self.trades.append(trade)
        self.save()

        log.info(
            "PAPER OPEN #%d | %s %s %.6f @ %.2f | SL=%.2f TP=%.2f | fee=$%.4f",
            trade.id, side.upper(), symbol, quantity, entry_price,
            stop_loss, take_profit, fee,
        )
        return trade

    def check_and_close(self, current_price: float, fee_pct: float = 0.06) -> List[PaperTrade]:
        """Check open positions against current price for SL/TP hits."""
        closed: List[PaperTrade] = []

        for trade in self.open_positions:
            hit = None

            if trade.side == "long":
                if current_price <= trade.stop_loss:
                    hit = trade.stop_loss
                elif current_price >= trade.take_profit:
                    hit = trade.take_profit
            else:  # short
                if current_price >= trade.stop_loss:
                    hit = trade.stop_loss
                elif current_price <= trade.take_profit:
                    hit = trade.take_profit

            if hit is not None:
                self._close_trade(trade, hit, fee_pct)
                closed.append(trade)

        if closed:
            self.save()
        return closed

    def force_close(self, trade_id: int, exit_price: float, fee_pct: float = 0.06) -> PaperTrade | None:
        for trade in self.open_positions:
            if trade.id == trade_id:
                self._close_trade(trade, exit_price, fee_pct)
                self.save()
                return trade
        return None

    def _close_trade(self, trade: PaperTrade, exit_price: float, fee_pct: float) -> None:
        notional = trade.quantity * exit_price
        exit_fee = notional * fee_pct / 100

        if trade.side == "long":
            raw_pnl = (exit_price - trade.entry_price) * trade.quantity
        else:
            raw_pnl = (trade.entry_price - exit_price) * trade.quantity

        net_pnl = raw_pnl - exit_fee
        trade.exit_price = exit_price
        trade.exit_time = datetime.utcnow().isoformat()
        trade.pnl = round(net_pnl, 4)
        trade.fee = round(trade.fee + exit_fee, 4)
        trade.status = "closed"
        self.balance = round(self.balance + net_pnl, 4)

        result = "WIN" if net_pnl > 0 else "LOSS"
        log.info(
            "PAPER CLOSE #%d | %s | exit=%.2f | pnl=$%.4f | balance=$%.2f",
            trade.id, result, exit_price, net_pnl, self.balance,
        )

    # ── statistics ───────────────────────────────────────────────────────

    def stats(self) -> dict:
        closed = self.closed_trades
        wins = [t for t in closed if t.pnl > 0]
        losses = [t for t in closed if t.pnl <= 0]
        total_pnl = sum(t.pnl for t in closed)
        total_fees = sum(t.fee for t in closed)

        start = datetime.fromisoformat(self.start_time)
        elapsed = datetime.utcnow() - start
        days_elapsed = max(elapsed.total_seconds() / SECONDS_IN_DAY, 0.01)
        days_remaining = max(self.target_days - days_elapsed, 0)

        growth_pct = ((self.balance / self.initial_balance) - 1) * 100
        daily_growth = growth_pct / days_elapsed if days_elapsed > 0 else 0

        # required daily growth to hit target
        remaining_growth = ((self.target / self.balance) - 1) * 100 if self.balance > 0 else float("inf")
        required_daily = remaining_growth / days_remaining if days_remaining > 0 else float("inf")

        return {
            "balance": round(self.balance, 2),
            "initial_balance": self.initial_balance,
            "target": self.target,
            "growth_pct": round(growth_pct, 2),
            "daily_growth_pct": round(daily_growth, 2),
            "required_daily_pct": round(required_daily, 2),
            "total_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0,
            "total_pnl": round(total_pnl, 2),
            "total_fees": round(total_fees, 2),
            "best_trade": round(max((t.pnl for t in closed), default=0), 2),
            "worst_trade": round(min((t.pnl for t in closed), default=0), 2),
            "open_positions": len(self.open_positions),
            "days_elapsed": round(days_elapsed, 1),
            "days_remaining": round(days_remaining, 1),
            "on_track": daily_growth >= required_daily if days_remaining > 0 else self.balance >= self.target,
        }

    def print_dashboard(self) -> None:
        s = self.stats()
        track_status = "ON TRACK" if s["on_track"] else "BEHIND"

        print("\n" + "=" * 60)
        print(f"  PAPER TRADING DASHBOARD")
        print("=" * 60)
        print(f"  Balance  : ${s['balance']:.2f}  (start: ${s['initial_balance']:.2f})")
        print(f"  Target   : ${s['target']:.2f}  [{track_status}]")
        print(f"  Growth   : {s['growth_pct']:+.2f}%  ({s['daily_growth_pct']:+.2f}%/day)")
        print(f"  Required : {s['required_daily_pct']:.2f}%/day to reach target")
        print("-" * 60)
        print(f"  Trades   : {s['total_trades']}  (W:{s['wins']} / L:{s['losses']})  WR: {s['win_rate']}%")
        print(f"  Total P&L: ${s['total_pnl']:+.2f}  (fees: ${s['total_fees']:.2f})")
        print(f"  Best     : ${s['best_trade']:+.2f}  |  Worst: ${s['worst_trade']:+.2f}")
        print(f"  Open pos : {s['open_positions']}")
        print("-" * 60)
        print(f"  Day {s['days_elapsed']:.0f} / {s['target_days']}  |  {s['days_remaining']:.0f} days left")
        print("=" * 60 + "\n")
