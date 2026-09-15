"""The one source of truth. Fills, positions, equity and account events, produced once.

WHY THIS EXISTS
---------------
The runner used to compute trade P&L and throw the intraday path away, keeping only each
session's total. Anything that needed the path - the Topstep twin above all - had to rebuild
it from a second walk over the bars. Two walks are two chances to disagree, and the one that
matters is silent: a P&L number and an account verdict that were computed from different
histories of the same day still both look plausible.

So the execution simulator emits ONE ledger and everything downstream reads it:

    strategy -> signals -> execution simulator -> CANONICAL LEDGER
                                                        |
                              +-------------------------+-------------------------+
                              |                         |                         |
                        P&L analytics           Topstep digital twin      monthly / payout

There is no second simulated stream anywhere in that diagram. `trade_frame()`, `daily()`,
`equity_curve()` and `twin_days()` are all VIEWS of the same fills; none of them recomputes a
fill, a price, or a cost.

THE EQUITY PATH IS MODE-DEPENDENT, AND THE MODE IS PART OF THE RESULT
----------------------------------------------------------------------
A one-minute bar hides everything that happened inside it. The close is where the money is at
the end of the bar; it is NOT where the account was marked at the worst moment during it, and
Topstep liquidates on the touch. Three readings of the same bars are supported, ordered from
the one every historical number in this repository used to the most conservative defensible:

    CLOSE_ONLY              mark each held bar at its close. What the repo has always done,
                            kept so old results stay reproducible. Optimistic: measured on
                            310 ES sessions it hides a median $75 of depth and calls 8 of
                            them survivors that the bar lows say breached.

    INTRABAR_CONSERVATIVE   additionally mark each held bar at the extreme that hurts the
                            position - the low for a long, the high for a short. On the
                            bar a price-triggered stop fires, the stop level IS the floor,
                            because the position was closed there.

    STRESS                  as above, but the exit bar is marked at its full extreme even
                            when a stop fired, i.e. the account is assumed to have been
                            marked at the worst tick of the bar before the flatten
                            registered. The most conservative reading OHLCV supports.

The three differ ONLY in the path. Every fill, every price and every settled P&L is identical
across them - asserted, not asserted-by-comment. So a mode change can move an account verdict
and can never move a profit figure.

`docs/INTRABAR_FORENSICS.md` states what OHLCV knows, what it cannot know, and the bounds.
"""
from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_brain.markets.futures_cme.twin import TwinDay
from quant_brain.research import exits as X


class ExecutionPathMode(str, enum.Enum):
    """How the within-bar equity path is read off OHLCV. Never defaulted silently."""

    CLOSE_ONLY = "CLOSE_ONLY"
    INTRABAR_CONSERVATIVE = "INTRABAR_CONSERVATIVE"
    STRESS = "STRESS"


#: Exit reasons whose fill price is itself the adverse extreme of the exit bar: the position
#: was closed AT that level, so under INTRABAR_CONSERVATIVE the bar cannot mark the account
#: below it. STRESS drops this protection deliberately.
PRICE_TRIGGERED_EXITS = (X.STOP, X.TRAIL)

#: The largest end-of-path drift attributable to float association order. A run with 340
#: trades drifts about 3e-13; a cent is four orders of magnitude of headroom and still far
#: below anything a real accounting error could be.
_MARK_SNAP_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Fill:
    """One execution. The atom of the ledger; nothing downstream invents another."""

    session: dt.date
    bar: int
    timestamp: pd.Timestamp
    kind: str                 # "ENTRY" | "EXIT"
    signed_quantity: float    # +n opens/adds long, -n opens/adds short
    price: float
    reason: str
    cost: float               # the leg's share of the round turn, charged at this bar


@dataclass(frozen=True)
class LedgerTrade:
    """One round trip, derived from exactly two fills."""

    trade_id: int
    session: dt.date
    direction: int
    quantity: int
    entry_bar: int
    exit_bar: int
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    gross_pnl: float
    commission_and_spread: float
    slippage: float
    net_pnl: float
    mae: float
    mfe: float
    r_multiple: float
    exit_reason: str
    holding_minutes: int
    ambiguous_bar: bool

    @property
    def forced_flatten(self) -> bool:
        """Closed by the bell rather than by a rule of the strategy's own.

        Compared against `exits.FLATTEN` rather than a string literal: the constant is
        "forced_flatten", and a literal "flatten" here silently reported every bell-closed
        trade as a normal exit.
        """
        return self.exit_reason == X.FLATTEN


@dataclass(frozen=True)
class SessionLedger:
    """One session: its fills, its trades, and the equity path they imply under one mode."""

    day: dt.date
    bars: int
    open_time: pd.Timestamp
    close_time: pd.Timestamp
    fills: tuple[Fill, ...]
    trades: tuple[LedgerTrade, ...]
    #: Equity relative to the session's opening balance, at every mark the mode produces.
    #: ALWAYS ends on `realized_net`, so the settled P&L and the path cannot disagree.
    marks: tuple[float, ...]
    realized_gross: float
    realized_net: float
    cost: float
    forced_flatten: bool
    ends_flat: bool

    @property
    def worst_mark(self) -> float:
        return min(self.marks) if self.marks else 0.0

    @property
    def best_mark(self) -> float:
        return max(self.marks) if self.marks else 0.0

    @property
    def max_intraday_drawdown(self) -> float:
        """Deepest fall from a running high WITHIN the session, in dollars (<= 0)."""
        if not self.marks:
            return 0.0
        a = np.asarray((0.0, *self.marks), dtype=float)
        return float((a - np.maximum.accumulate(a)).min())

    @property
    def traded(self) -> bool:
        return bool(self.trades)


@dataclass(frozen=True)
class CanonicalLedger:
    """Every session of one run, under one execution scenario and one path mode."""

    spec_hash: str
    strategy: str
    instrument: str
    multiplier: float
    tick_value: float
    contracts: int
    mode: ExecutionPathMode
    slippage_ticks: float
    scenario: str
    round_turn_cost: float
    sessions: tuple[SessionLedger, ...] = field(default_factory=tuple)

    # -- views. None of these recomputes a fill. ------------------------------------------

    def trade_frame(self) -> pd.DataFrame:
        rows = []
        for s in self.sessions:
            for t in s.trades:
                rows.append({
                    "trade_id": t.trade_id, "strategy": self.strategy,
                    "instrument": self.instrument, "session": t.session,
                    "direction": t.direction, "quantity": t.quantity,
                    "entry_bar": t.entry_bar, "exit_bar": t.exit_bar,
                    "entry_time": t.entry_time, "exit_time": t.exit_time,
                    "entry_price": t.entry_price, "exit_price": t.exit_price,
                    "gross_pnl": t.gross_pnl,
                    "commission_and_spread": t.commission_and_spread,
                    "slippage": t.slippage, "net_pnl": t.net_pnl,
                    "mae": t.mae, "mfe": t.mfe, "r_multiple": t.r_multiple,
                    "exit_reason": t.exit_reason, "holding_minutes": t.holding_minutes,
                    "ambiguous_bar": t.ambiguous_bar,
                    "forced_flatten": t.forced_flatten,
                    "day_of_week": pd.Timestamp(t.session).day_name(),
                    "month": str(pd.Timestamp(t.session).to_period("M")),
                    "execution_path_mode": self.mode.value,
                })
        return pd.DataFrame(rows)

    def fill_frame(self) -> pd.DataFrame:
        rows = [{"session": f.session, "bar": f.bar, "timestamp": f.timestamp,
                 "kind": f.kind, "signed_quantity": f.signed_quantity, "price": f.price,
                 "reason": f.reason, "cost": f.cost}
                for s in self.sessions for f in s.fills]
        return pd.DataFrame(rows)

    def daily(self) -> pd.Series:
        return pd.Series([s.realized_net for s in self.sessions],
                         index=[s.day for s in self.sessions], dtype=float)

    def equity_curve(self) -> np.ndarray:
        return np.cumsum(np.asarray([s.realized_net for s in self.sessions], dtype=float))

    def intraday_equity(self) -> np.ndarray:
        """Every mark of every session, concatenated onto a running account equity.

        This is the series the maximum intraday drawdown is measured on, and it is the same
        series the twin walks. Session `k` starts from the cumulative realised total of
        sessions 0..k-1, which is what the account balance actually is at that point.
        """
        out: list[float] = []
        running = 0.0
        for s in self.sessions:
            out.extend(running + m for m in s.marks)
            running += s.realized_net
        return np.asarray(out, dtype=float)

    def twin_days(self) -> list[TwinDay]:
        """The account simulator's input, built from the SAME marks and nothing else."""
        return [TwinDay(day=s.day, pnl=s.realized_net, path=s.marks, traded=s.traded)
                for s in self.sessions]

    @property
    def total_trades(self) -> int:
        return sum(len(s.trades) for s in self.sessions)

    @property
    def days_traded(self) -> int:
        return sum(1 for s in self.sessions if s.traded)


# ======================================================================================
# BUILDING THE PATH
# ======================================================================================

def _adverse_price(direction: int, high: float, low: float) -> float:
    """The extreme of a bar that hurts the position held through it."""
    return low if direction > 0 else high


def session_marks(trades, closes, highs, lows, *, mode: ExecutionPathMode,
                  multiplier: float, contracts: int, half_cost: float) -> tuple[float, ...]:
    """The intraday equity path implied by a session's trades, under one path mode.

    The contract this function has to honour, and which `test_canonical_ledger.py` enforces:

        1. the LAST mark equals the session's realised net P&L, exactly
        2. the marks are identical across modes wherever the modes agree on the bars
        3. a mode can only ever ADD marks, so `min(marks)` is monotone non-increasing
           from CLOSE_ONLY to INTRABAR_CONSERVATIVE to STRESS

    Cost is charged at the bar the leg trades - half a round turn in, half out - because the
    twin reads this path and cost not yet charged is equity the account does not have.
    """
    marks: list[float] = []
    running = 0.0
    scale = multiplier * contracts

    for t in trades:
        d = t.direction
        entry = t.entry_price
        running -= half_cost                      # the entry leg pays here
        marks.append(running)                     # position just opened: nothing unrealised

        for i in range(t.entry_bar + 1, t.exit_bar):
            if mode is not ExecutionPathMode.CLOSE_ONLY:
                adverse = (_adverse_price(d, highs[i], lows[i]) - entry) * d * scale
                marks.append(running + adverse)
            marks.append(running + (closes[i] - entry) * d * scale)

        exit_value = (t.exit_price - entry) * d * scale
        if mode is not ExecutionPathMode.CLOSE_ONLY and t.exit_bar > t.entry_bar:
            bar_extreme = (_adverse_price(d, highs[t.exit_bar], lows[t.exit_bar])
                           - entry) * d * scale
            if mode is ExecutionPathMode.STRESS:
                # The flatten is assumed not to have registered before the worst tick.
                adverse = bar_extreme
            elif t.exit_reason in PRICE_TRIGGERED_EXITS:
                # The stop closed the position AT its level; the account cannot be marked
                # below a level it was flattened at.
                adverse = exit_value
            else:
                adverse = bar_extreme
            if adverse < exit_value:
                marks.append(running + adverse)

        running += exit_value - half_cost         # the exit leg pays here
        marks.append(running)

    if not marks:
        return (0.0,)
    return tuple(marks)


def build_session_ledger(day, times, closes, highs, lows, trades, *,
                         mode: ExecutionPathMode, multiplier: float, contracts: int,
                         base_cost: float, slip_cost: float) -> SessionLedger:
    """Assemble one session's fills, trades and marks. `trades` are already simulated."""
    total_cost = base_cost + slip_cost
    half = total_cost / 2.0
    fills: list[Fill] = []
    for t in trades:
        fills.append(Fill(session=day, bar=t.entry_bar, timestamp=t.entry_time,
                          kind="ENTRY", signed_quantity=float(t.direction * t.quantity),
                          price=t.entry_price, reason="signal", cost=half))
        fills.append(Fill(session=day, bar=t.exit_bar, timestamp=t.exit_time,
                          kind="EXIT", signed_quantity=float(-t.direction * t.quantity),
                          price=t.exit_price, reason=t.exit_reason, cost=half))

    marks = session_marks(trades, closes, highs, lows, mode=mode, multiplier=multiplier,
                          contracts=contracts, half_cost=half)
    realized_gross = float(sum(t.gross_pnl for t in trades))
    realized_net = float(sum(t.net_pnl for t in trades))

    # The path accumulates `-half, +value-half` per trade while `realized_net` sums
    # `gross - cost` per trade. Identical arithmetic, different association order, so the
    # two can end a few times 1e-13 apart. `TwinDay` requires the path to END on the
    # settled P&L, so the last mark is snapped - but ONLY within a tolerance that no real
    # discrepancy could hide inside. A larger gap is a bug in the fill accounting and is
    # raised rather than absorbed, because a snap that silently repairs is exactly the
    # failure this engine is built to refuse.
    if marks:
        drift = marks[-1] - realized_net
        if abs(drift) > _MARK_SNAP_TOLERANCE:
            raise AssertionError(
                f"{day}: the intraday path ends at {marks[-1]:,.6f} but the trades settle "
                f"at {realized_net:,.6f}, a gap of {drift:,.6f}. That is far larger than "
                f"floating-point association error, so the fills and the path disagree "
                f"about what happened. Refusing to snap it away.")
        marks = (*marks[:-1], realized_net)
    net_qty = sum(f.signed_quantity for f in fills)
    return SessionLedger(
        day=day, bars=len(closes), open_time=times[0], close_time=times[-1],
        fills=tuple(fills), trades=tuple(trades), marks=marks,
        realized_gross=realized_gross, realized_net=realized_net,
        cost=float(total_cost * len(trades)),
        forced_flatten=any(t.forced_flatten for t in trades),
        ends_flat=abs(net_qty) < 1e-12)


__all__ = ["PRICE_TRIGGERED_EXITS", "CanonicalLedger", "ExecutionPathMode", "Fill",
           "LedgerTrade", "SessionLedger", "build_session_ledger", "session_marks"]
