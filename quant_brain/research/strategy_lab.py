"""The standardised evaluation interface every strategy is judged through.

WHY THIS EXISTS
---------------
The repository already has a strategy library and an evaluator, and the evaluator answers a
narrow question well: what did this position series earn per session, net of commission. That
was the right instrument for the discovery phases. It is the wrong one for a selection lab,
because it cannot say what a TRADE was - when it opened, when it closed, why it closed, how
far it went against you before it worked.

Without trade-level records there is no maximum adverse excursion, no exit-reason breakdown,
no holding-time distribution, and no honest way to compare a mechanism that turns over twice a
session against one that turns over forty times. Those are exactly the quantities that
separate a strategy worth paper-trading from one that merely has a positive sum.

THE STRUCTURAL GAP THIS INTERFACE HAS TO WORK AROUND
------------------------------------------------------
Every strategy in `scripts/strategy_tournament.py` is a stateless per-bar signal: it maps a
feature frame to a position in {-1, 0, +1} and nothing else. **None of them has a stop, a
target, or an exit rule.** A position ends when the signal says something different, or when
the session ends.

That is a real limitation and it is not papered over here. It has three consequences that are
reported rather than hidden:

  1. Exit reasons can only be `signal_flip`, `signal_flat` or `forced_flatten`. There is no
     `stop_hit` or `target_hit` because there is no stop and no target.
  2. The R multiple has no natural denominator. A trade's risk is normally the distance to its
     stop; with no stop there is none. This module defines R against the ATR of the entry
     session, states that everywhere it is used, and never lets it masquerade as a
     stop-based R.
  3. Maximum adverse excursion is measured but never acted on, so MAE distributions here
     describe how much pain the mechanism ASKS you to take, not how much it was allowed to.

Adding brackets would fix all three and would also add two parameters per strategy. The brief
is explicit that the baseline runs on canonical parameters, so brackets belong in the
parameter phase for surviving candidates only, not here.

FAIR COMPARISON IS THE WHOLE POINT
------------------------------------
Every strategy runs through the same function, on the same sessions, with the same cost model,
the same session window and the same flatten rule. A strategy cannot report its own numbers
its own way. Where a metric is undefined for a mechanism (profit factor with no losses, for
instance) it comes back as a sentinel rather than a flattering default.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

#: Exit reasons this interface can distinguish. Deliberately short - see the module docstring.
EXIT_SIGNAL_FLIP = "signal_flip"
EXIT_SIGNAL_FLAT = "signal_flat"
EXIT_FORCED_FLATTEN = "forced_flatten"


@dataclass(frozen=True)
class CostModel:
    """Everything charged against a round turn, per contract.

    `slippage_ticks` is the round-turn total, not per leg. Keeping it as one number avoids the
    commonest arithmetic slip in this kind of harness, which is charging half a tick twice and
    calling it a tick.
    """

    round_turn_commission: float
    tick_value: float
    slippage_ticks: float = 0.0

    def per_round_turn(self, contracts: int) -> float:
        return (self.round_turn_commission
                + self.slippage_ticks * self.tick_value) * contracts


@dataclass(frozen=True)
class Trade:
    """One position, open to close."""

    strategy: str
    symbol: str
    entry_time: dt.datetime
    exit_time: dt.datetime
    entry_bar: int
    exit_bar: int
    direction: int                 # +1 long, -1 short
    contracts: int
    entry_price: float
    exit_price: float
    gross_pnl: float
    commission: float
    slippage: float
    net_pnl: float
    mae: float                     # worst mark-to-market during the trade, in dollars
    mfe: float                     # best mark-to-market during the trade, in dollars
    r_multiple: float              # net P&L over the ATR-based risk unit; see docstring
    exit_reason: str
    holding_minutes: int
    session: dt.date


@dataclass(frozen=True)
class SessionResult:
    """One trading day."""

    session: dt.date
    symbol: str
    strategy: str
    n_trades: int
    gross_pnl: float
    costs: float
    net_pnl: float
    max_intraday_dd: float
    max_favorable: float
    max_adverse: float
    end_position: int
    forced_flatten: bool
    time_in_market: float          # share of session bars holding a position
    path: tuple[float, ...]        # equity path in dollars, for the Topstep twin


@dataclass
class Portfolio:
    """Everything a scorecard needs, computed one way for every strategy."""

    strategy: str
    symbol: str
    n_sessions: int = 0
    n_trades: int = 0
    gross_pnl: float = 0.0
    costs: float = 0.0
    net_pnl: float = 0.0
    expectancy_per_trade: float = 0.0
    expectancy_per_session: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    payoff_ratio: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    max_dd_duration: int = 0
    sharpe: float = 0.0
    sortino: float = 0.0
    t_stat: float = 0.0
    consec_losing_days: int = 0
    time_in_market: float = 0.0
    exposure: float = 0.0
    return_vol: float = 0.0
    trades_per_session: float = 0.0
    median_holding_minutes: float = 0.0
    mean_mae: float = 0.0
    mean_mfe: float = 0.0
    exit_reason_mix: dict = field(default_factory=dict)
    by_year: dict = field(default_factory=dict)
    by_month: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        d = dataclasses.asdict(self)
        d["exit_reason_mix"] = "|".join(f"{k}:{v}" for k, v in
                                        sorted(self.exit_reason_mix.items()))
        d.pop("by_year", None)
        d.pop("by_month", None)
        return d


def extract_trades(pos: np.ndarray, closes: np.ndarray, times: pd.Series,
                   *, strategy: str, symbol: str, session: dt.date,
                   multiplier: float, contracts: int, cost: CostModel,
                   atr_dollars: float) -> tuple[list[Trade], np.ndarray]:
    """Turn a per-bar position series into discrete trades and a dollar equity path.

    THE FILL CONVENTION, STATED
    A position recorded at bar i is assumed filled at bar i's CLOSE and to earn the move from
    bar i's close to bar i+1's close. That is the convention the existing evaluator uses and
    it is preserved so that this interface's numbers reconcile with the tournament's. It is
    also the optimistic one on a book with bid-ask bounce, which is why the cost model carries
    an explicit slippage term rather than assuming zero.

    THE COST CHARGE
    One round turn per completed trade, charged at the exit. A position that reverses directly
    from long to short is two round turns, because it is two trades.
    """
    n = len(closes)
    pos = np.nan_to_num(np.asarray(pos, dtype=float), nan=0.0)[:n]
    # mark-to-market increment earned by the position held at bar i
    step = np.zeros(n, dtype=float)
    if n > 1:
        step[:-1] = pos[:-1] * np.diff(closes) * multiplier * contracts

    trades: list[Trade] = []
    equity = np.zeros(n, dtype=float)
    running = 0.0
    open_dir = 0
    open_bar = 0
    open_equity = 0.0
    open_price = 0.0
    peak = trough = 0.0
    rt = cost.per_round_turn(contracts)
    comm = cost.round_turn_commission * contracts
    slip = cost.slippage_ticks * cost.tick_value * contracts

    def close_trade(bar: int, reason: str) -> None:
        nonlocal open_dir, running
        gross = running - open_equity
        net = gross - rt
        trades.append(Trade(
            strategy=strategy, symbol=symbol,
            entry_time=times.iloc[open_bar], exit_time=times.iloc[bar],
            entry_bar=open_bar, exit_bar=bar, direction=open_dir, contracts=contracts,
            entry_price=float(open_price), exit_price=float(closes[bar]),
            gross_pnl=float(gross), commission=float(comm), slippage=float(slip),
            net_pnl=float(net),
            mae=float(trough - open_equity), mfe=float(peak - open_equity),
            r_multiple=float(net / atr_dollars) if atr_dollars > 0 else float("nan"),
            exit_reason=reason, holding_minutes=int(bar - open_bar), session=session))
        open_dir = 0

    for i in range(n):
        p = pos[i]
        if open_dir != 0 and p != open_dir:
            close_trade(i, EXIT_SIGNAL_FLAT if p == 0 else EXIT_SIGNAL_FLIP)
        if open_dir == 0 and p != 0:
            open_dir = int(np.sign(p))
            open_bar = i
            open_equity = running
            open_price = float(closes[i])
            peak = trough = running
        running += step[i]
        equity[i] = running
        if open_dir != 0:
            peak = max(peak, running)
            trough = min(trough, running)
    if open_dir != 0:
        close_trade(n - 1, EXIT_FORCED_FLATTEN)

    # costs are realised at each exit; subtract them from the equity path so the path the
    # Topstep twin sees is NET, which is what the MLL is actually tested against
    for t in trades:
        equity[t.exit_bar:] -= rt
    return trades, equity


def summarise_session(trades: list[Trade], equity: np.ndarray, pos: np.ndarray,
                      *, session: dt.date, symbol: str, strategy: str,
                      cost_per_rt: float) -> SessionResult:
    peak = np.maximum.accumulate(equity) if len(equity) else np.array([0.0])
    return SessionResult(
        session=session, symbol=symbol, strategy=strategy, n_trades=len(trades),
        gross_pnl=float(sum(t.gross_pnl for t in trades)),
        costs=float(len(trades) * cost_per_rt),
        net_pnl=float(equity[-1]) if len(equity) else 0.0,
        max_intraday_dd=float((equity - peak).min()) if len(equity) else 0.0,
        max_favorable=float(equity.max()) if len(equity) else 0.0,
        max_adverse=float(equity.min()) if len(equity) else 0.0,
        end_position=int(pos[-1]) if len(pos) else 0,
        forced_flatten=bool(trades and trades[-1].exit_reason == EXIT_FORCED_FLATTEN),
        time_in_market=float(np.mean(np.asarray(pos) != 0)) if len(pos) else 0.0,
        path=tuple(float(x) for x in equity))


def _drawdown(equity: np.ndarray) -> tuple[float, int]:
    if not len(equity):
        return 0.0, 0
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    worst = float(dd.min())
    longest = cur = 0
    for x in dd:
        cur = cur + 1 if x < 0 else 0
        longest = max(longest, cur)
    return worst, longest


def summarise_portfolio(trades: list[Trade], sessions: list[SessionResult],
                        *, strategy: str, symbol: str,
                        ann: int = 252) -> Portfolio:
    """Every portfolio metric, computed identically for every strategy."""
    p = Portfolio(strategy=strategy, symbol=symbol)
    if not sessions:
        return p
    daily = np.array([s.net_pnl for s in sessions], dtype=float)
    equity = np.cumsum(daily)
    p.n_sessions = len(sessions)
    p.n_trades = len(trades)
    p.gross_pnl = float(sum(s.gross_pnl for s in sessions))
    p.costs = float(sum(s.costs for s in sessions))
    p.net_pnl = float(daily.sum())
    p.expectancy_per_session = float(daily.mean())
    p.trades_per_session = len(trades) / len(sessions)
    p.time_in_market = float(np.mean([s.time_in_market for s in sessions]))
    p.exposure = p.time_in_market

    sd = float(daily.std(ddof=1)) if len(daily) > 1 else 0.0
    p.return_vol = sd
    p.t_stat = float(daily.mean() / (sd / np.sqrt(len(daily)))) if sd > 0 else 0.0
    p.sharpe = float(daily.mean() / sd * np.sqrt(ann)) if sd > 0 else 0.0
    downside = daily[daily < 0]
    dsd = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    p.sortino = float(daily.mean() / dsd * np.sqrt(ann)) if dsd > 0 else 0.0
    p.max_drawdown, p.max_dd_duration = _drawdown(equity)

    run = best = 0
    for v in daily:
        run = run + 1 if v < 0 else 0
        best = max(best, run)
    p.consec_losing_days = best

    if trades:
        net = np.array([t.net_pnl for t in trades], dtype=float)
        wins, losses = net[net > 0], net[net < 0]
        p.expectancy_per_trade = float(net.mean())
        p.win_rate = float((net > 0).mean())
        p.avg_win = float(wins.mean()) if len(wins) else 0.0
        p.avg_loss = float(losses.mean()) if len(losses) else 0.0
        p.payoff_ratio = float(abs(p.avg_win / p.avg_loss)) if p.avg_loss else float("nan")
        gp, gl = float(wins.sum()), float(-losses.sum())
        # A sentinel rather than a flattering default: a strategy with no losing trade has an
        # undefined profit factor, and printing "inf" beside a real one invites a bad ranking.
        p.profit_factor = float(gp / gl) if gl > 0 else float("nan")
        p.median_holding_minutes = float(np.median([t.holding_minutes for t in trades]))
        p.mean_mae = float(np.mean([t.mae for t in trades]))
        p.mean_mfe = float(np.mean([t.mfe for t in trades]))
        mix: dict[str, int] = {}
        for t in trades:
            mix[t.exit_reason] = mix.get(t.exit_reason, 0) + 1
        p.exit_reason_mix = mix

    df = pd.DataFrame({"d": [s.session for s in sessions], "pnl": daily})
    df["d"] = pd.to_datetime(df["d"])
    p.by_year = {int(k): float(v) for k, v in df.groupby(df.d.dt.year)["pnl"].sum().items()}
    p.by_month = {str(k): float(v) for k, v in
                  df.groupby(df.d.dt.to_period("M"))["pnl"].sum().items()}
    return p


__all__ = ["CostModel", "EXIT_FORCED_FLATTEN", "EXIT_SIGNAL_FLAT", "EXIT_SIGNAL_FLIP",
           "Portfolio", "SessionResult", "Trade", "extract_trades",
           "summarise_portfolio", "summarise_session"]
