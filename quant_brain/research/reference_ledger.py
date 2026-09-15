"""An INDEPENDENT reference implementation of futures position accounting.

WHY THIS EXISTS AND WHY IT IS DELIBERATELY SLOW
-------------------------------------------------
The repository's P&L runs through vectorised numpy: `session_accounting` computes an equity
path with `cumsum(pos[:-1] * step[1:])` and charges cost through `cumsum(legs) * rt/2`. That
is correct as far as anyone has checked, but "as far as anyone has checked" has so far meant
testing the engine against itself. A test that calls the same `np.diff` the engine calls
cannot catch an error in what `np.diff` was supposed to mean.

So this module recomputes the same quantities a completely different way:

    - plain Python loops, one bar at a time, no numpy
    - an explicit position/cash ledger rather than a cumulative-sum identity
    - cost charged at the moment a contract changes hands, tracked as its own running total
    - realised and unrealised P&L kept separate and reconciled at the end

It shares NO code with the engine. It imports nothing from `futures_discover`,
`strategy_lab` or `exits`. When the two agree to the cent on a hand-built case, that
agreement means something. When they disagree, one of them is wrong and the disagreement is
the finding.

THE ACCOUNTING MODEL, WRITTEN OUT
-----------------------------------
A futures position has no cost basis in the equity sense - there is no cash outlay - so the
ledger tracks:

    position      signed contracts held
    avg_price     volume-weighted average entry of the CURRENT position
    realised      cash locked in by closed contracts, net of their cost
    fees_paid     running total of commission-plus-spread actually charged
    mark          unrealised P&L of the open position at the current close

Equity at any bar is `realised + mark`. That is the number the Topstep trailing limit tests,
and it is why the reference computes it explicitly rather than deriving it.

WHEN COST IS CHARGED
--------------------
Per CONTRACT that changes hands, at the moment it changes hands, at half a round turn per
leg. Opening one contract costs half a round turn; closing it costs the other half. A
reversal from +1 to -1 moves two contracts and therefore pays two half-turns in the same
instant - one closing the long, one opening the short.

That is the same convention `session_accounting` uses. It is written out here in a form that
can be read and checked by hand, which is the point.

FILL CONVENTION
---------------
Position recorded at bar i is filled at bar i's close and earns the move from bar i's close to
bar i+1's close. A position that is still open on the last bar is flattened at that bar's
close and pays its closing leg. Both conventions are the engine's; the reference exists to
verify the ARITHMETIC, not to relitigate the semantics.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RefTrade:
    """One completed round turn, as the reference sees it."""

    entry_bar: int
    exit_bar: int
    direction: int
    quantity: int
    entry_price: float
    exit_price: float
    gross_pnl: float
    cost: float
    net_pnl: float
    reason: str


@dataclass
class RefResult:
    equity_path: list[float] = field(default_factory=list)
    realised: float = 0.0
    fees_paid: float = 0.0
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    round_turns: float = 0.0
    contracts_traded: int = 0
    trades: list[RefTrade] = field(default_factory=list)
    final_position: int = 0


def run_reference(positions: list[float], closes: list[float], *,
                  multiplier: float, contracts: int,
                  round_turn_cost: float,
                  flatten_at_end: bool = True,
                  last_entry_bar: int | None = None) -> RefResult:
    """Recompute a session's accounting with explicit loops and an explicit ledger.

    `positions[i]` is the signed position (in units of `contracts`) held from bar i's close.
    `round_turn_cost` is the FULL round-turn cost for `contracts` contracts; half is charged
    on each leg, pro-rated by how many contracts actually moved.

    `last_entry_bar` is the last index at which a NEW position may be opened; positions after
    it are forced flat. Default `n - 2`, which forbids opening on the session's final bar.

    THE RULE THIS PARAMETER MAKES EXPLICIT
    A position opened on the last bar cannot be held - the session ends flat - so it is
    entered and closed at the same price and can only lose a round turn. The runner always
    refused those entries; the reference did not, and the two disagreed by exactly one round
    turn on any session whose signal fired on the final bar. That was a HIDDEN ASSUMPTION in
    the runner rather than an arithmetic error in either, and it is now a named parameter on
    both sides.
    """
    n = len(closes)
    if n < 2:
        return RefResult(equity_path=[0.0])
    cutoff = (n - 2) if last_entry_bar is None else int(last_entry_bar)
    positions = list(positions)
    held = 0.0
    for i in range(n):
        tgt = 0.0 if positions[i] is None else float(positions[i])
        if tgt != tgt:
            tgt = 0.0
        # a NEW position may not be opened past the cutoff; an existing one may still close
        if i > cutoff and abs(tgt) > abs(held):
            tgt = held
        positions[i] = tgt
        held = tgt

    half_turn_per_contract = (round_turn_cost / 2.0) / max(1, contracts)

    pos_units = 0.0          # signed, in units of `contracts`
    avg_price = 0.0
    #: GROSS realised P&L. Costs are tracked separately in `fees` and subtracted once, at the
    #: point equity is formed. An earlier version of this reference deducted only the CLOSING
    #: leg's cost from realised and left the opening leg in `fees` alone, so every net figure
    #: was light by half a round turn per trade. The engine was right and the reference was
    #: wrong; the disagreement is what found it.
    realised_gross = 0.0
    fees = 0.0
    contracts_moved = 0.0
    trades: list[RefTrade] = []
    open_bar = 0
    equity_path: list[float] = []

    def charge(units_moved: float) -> float:
        """Cost for moving `units_moved` units of `contracts` contracts, one leg."""
        nonlocal fees, contracts_moved
        c = abs(units_moved) * contracts * half_turn_per_contract
        fees += c
        contracts_moved += abs(units_moved) * contracts
        return c

    for i in range(n):
        target = 0.0 if positions[i] is None else float(positions[i])
        if target != target:                       # NaN
            target = 0.0
        px = float(closes[i])

        if target != pos_units:
            # --- closing or reducing ------------------------------------------------------
            if pos_units != 0.0 and (target == 0.0 or (target * pos_units) < 0
                                     or abs(target) < abs(pos_units)):
                closing = (abs(pos_units) if (target == 0.0 or target * pos_units < 0)
                           else abs(pos_units) - abs(target))
                sign = 1.0 if pos_units > 0 else -1.0
                gross = (px - avg_price) * sign * closing * multiplier * contracts
                cost = charge(closing)
                realised_gross += gross
                trades.append(RefTrade(
                    entry_bar=open_bar, exit_bar=i, direction=int(sign),
                    quantity=int(round(closing * contracts)),
                    entry_price=avg_price, exit_price=px,
                    gross_pnl=gross, cost=cost, net_pnl=gross - cost,
                    reason="flatten" if (i == n - 1 and target == 0.0) else "signal"))
                pos_units = pos_units - sign * closing
                if abs(pos_units) < 1e-12:
                    pos_units = 0.0
            # --- opening or adding ---------------------------------------------------------
            if target != pos_units:
                opening = abs(target - pos_units)
                if pos_units == 0.0:
                    avg_price = px
                    open_bar = i
                else:
                    total = abs(pos_units) + opening
                    avg_price = (avg_price * abs(pos_units) + px * opening) / total
                charge(opening)
                pos_units = target

        mark = ((px - avg_price) * (1.0 if pos_units > 0 else -1.0)
                * abs(pos_units) * multiplier * contracts) if pos_units != 0.0 else 0.0
        equity_path.append(realised_gross - fees + mark)

    if flatten_at_end and pos_units != 0.0:
        px = float(closes[-1])
        sign = 1.0 if pos_units > 0 else -1.0
        closing = abs(pos_units)
        gross = (px - avg_price) * sign * closing * multiplier * contracts
        cost = charge(closing)
        realised_gross += gross
        trades.append(RefTrade(entry_bar=open_bar, exit_bar=n - 1, direction=int(sign),
                               quantity=int(round(closing * contracts)),
                               entry_price=avg_price, exit_price=px, gross_pnl=gross,
                               cost=cost, net_pnl=gross - cost, reason="flatten"))
        pos_units = 0.0
        equity_path[-1] = realised_gross - fees

    gross_total = sum(t.gross_pnl for t in trades)
    return RefResult(
        equity_path=equity_path, realised=realised_gross, fees_paid=fees,
        gross_pnl=gross_total, net_pnl=realised_gross - fees,
        round_turns=contracts_moved / (2.0 * max(1, contracts)),
        contracts_traded=int(round(contracts_moved)),
        trades=trades, final_position=int(round(pos_units * contracts)))


def reference_pnl_one_trade(entry: float, exit_: float, direction: int, quantity: int,
                            multiplier: float, round_turn_cost_per_contract: float
                            ) -> tuple[float, float, float]:
    """The simplest possible check: one trade, arithmetic written out longhand.

    Returns (gross, cost, net). Used by the contract-math known-answer tests, where the
    expected values are computed by hand in the test rather than by any engine code.
    """
    gross = (exit_ - entry) * direction * quantity * multiplier
    cost = round_turn_cost_per_contract * quantity
    return gross, cost, gross - cost


def reference_drawdown(equity: list[float]) -> tuple[float, int, int]:
    """Path-dependent maximum drawdown, by explicit loop.

    Returns (max_drawdown, peak_index, trough_index). Deliberately not `np.maximum.accumulate`
    so that a defect in the vectorised version has something independent to fail against.
    """
    if not equity:
        return 0.0, 0, 0
    peak = equity[0]
    peak_i = 0
    worst = 0.0
    worst_peak = worst_trough = 0
    for i, v in enumerate(equity):
        if v > peak:
            peak, peak_i = v, i
        dd = v - peak
        if dd < worst:
            worst, worst_peak, worst_trough = dd, peak_i, i
    return worst, worst_peak, worst_trough


__all__ = ["RefResult", "RefTrade", "reference_drawdown", "reference_pnl_one_trade",
           "run_reference"]
