"""An INDEPENDENT reference for bracketed exits: stops, targets, trails, time stops.

WHY THIS EXISTS
---------------
`reference_ledger` independently verifies signal-driven positions, and the forensic audit
recorded that bracketed exits had no such check: the runner's validation gate skipped the
independent leg and said so. That was the single largest remaining gap in the engine's
credibility, because the bracket path is where an optimistic fill is easiest to hide and
hardest to notice.

HOW THIS IS INDEPENDENT
-----------------------
`exits.simulate_trade` walks bars forward and RETURNS EARLY from inside the loop the moment a
level is hit, with the checks in a fixed order. If that ordering is wrong, a test that
replicates the ordering will not notice.

This module is built the other way round. For each bar it first constructs an explicit,
order-free EVENT SET - every exit condition that the bar's data could have satisfied - and
only then resolves that set through a written-down precedence table. Nothing returns early
from inside a scan; the scan and the resolution are separate steps.

The two implementations therefore disagree if either the touch detection OR the precedence is
wrong, which is what makes the agreement worth something.

THE PRECEDENCE TABLE, WRITTEN DOWN
------------------------------------
When more than one condition fires on the same bar, resolution is by this order and no other:

    1. STOP            including a stop that has been trailed or moved to break-even
    2. TARGET
    3. TIME STOP
    4. SIGNAL INVALIDATION
    5. FORCED FLATTEN   (last bar only)

Stop before target is the conservative choice and it is the whole point: OHLCV cannot say
which came first inside a bar, so an engine that picked the better one would systematically
overstate every bracketed strategy. Ambiguity is recorded on the trade, never resolved toward
profit.

WHAT CANNOT BE KNOWN FROM OHLCV, STATED PLAINLY
-------------------------------------------------
Given only open/high/low/close, the path inside a bar is unknown. Specifically unknowable:

    - whether the high or the low came first
    - whether a level was touched once or many times
    - the price at any instant between the open and the close
    - whether a gap traded through a level or opened beyond it

This reference does not pretend otherwise. A level is "touched" when the bar's range contains
it; a gap beyond a level fills AT the level, not at the gap price, and that is documented as a
modelling choice rather than a fact about the tape.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: Precedence, most conservative first. Used by `_resolve`.
PRECEDENCE = ("stop", "target", "time_stop", "signal_invalidation", "forced_flatten")


@dataclass(frozen=True)
class RefBracket:
    """One completed bracketed trade, as the independent reference sees it."""

    entry_bar: int
    exit_bar: int
    direction: int
    quantity: int
    entry_price: float
    exit_price: float
    points: float
    gross: float
    cost: float
    net: float
    reason: str
    bars_held: int
    mfe_points: float
    mae_points: float
    ambiguous: bool
    events_at_exit: tuple[str, ...] = field(default_factory=tuple)


def _events_on_bar(hi: float, lo: float, cl: float, direction: int,
                   stop_px: float | None, target_px: float | None,
                   bars_held: int, time_stop: int | None,
                   signal_now: float, is_last: bool,
                   use_invalidation: bool) -> set[str]:
    """Every exit condition this bar's data could have satisfied. Order-free by construction.

    A set, deliberately: building it cannot encode a preference, so the precedence lives in
    exactly one place (`_resolve`) and can be audited there.
    """
    ev: set[str] = set()
    if stop_px is not None:
        touched = (lo <= stop_px) if direction > 0 else (hi >= stop_px)
        if touched:
            ev.add("stop")
    if target_px is not None:
        touched = (hi >= target_px) if direction > 0 else (lo <= target_px)
        if touched:
            ev.add("target")
    if time_stop is not None and bars_held >= time_stop:
        ev.add("time_stop")
    if use_invalidation and signal_now != direction:
        ev.add("signal_invalidation")
    if is_last:
        ev.add("forced_flatten")
    return ev


def _resolve(events: set[str]) -> str:
    """The written-down precedence. The ONLY place ordering is expressed."""
    for name in PRECEDENCE:
        if name in events:
            return name
    return ""


def simulate_bracket_reference(
    closes: list[float], highs: list[float], lows: list[float],
    signal: list[float], entry_bar: int, direction: int, *,
    atr: float,
    stop_atr: float | None = None,
    target_r: float | None = None,
    structural_stop: bool = False,
    trail_atr: float | None = None,
    breakeven_at_r: float | None = None,
    time_stop_bars: int | None = None,
    use_invalidation: bool = True,
    multiplier: float = 1.0,
    quantity: int = 1,
    round_turn_cost: float = 0.0,
) -> RefBracket:
    """Independently simulate one bracketed trade.

    Entry at `closes[entry_bar]`. The scan begins at the NEXT bar: a position filled at a
    bar's close cannot be stopped out by that same bar's low, which already happened.
    """
    n = len(closes)
    entry = float(closes[entry_bar])
    last_index = n - 1

    # ---- initial risk, from whichever stop definition the caller declared ------------------
    if structural_stop:
        risk = (entry - float(lows[entry_bar])) if direction > 0 \
            else (float(highs[entry_bar]) - entry)
        risk = max(risk, 1e-9)
        stop_px: float | None = entry - risk * direction
    elif stop_atr is not None:
        risk = max(stop_atr * atr, 1e-9)
        stop_px = entry - risk * direction
    else:
        risk = max(atr, 1e-9)          # nominal R for reporting only
        stop_px = None

    target_px = (entry + target_r * risk * direction) if target_r is not None else None

    best_favourable = entry           # running extreme in the trade's favour
    mfe = 0.0
    mae = 0.0
    breakeven_armed = False

    for i in range(entry_bar + 1, n):
        hi, lo, cl = float(highs[i]), float(lows[i]), float(closes[i])

        # excursions, measured before any exit resolution
        up = (hi - entry) if direction > 0 else (entry - lo)
        dn = (lo - entry) if direction > 0 else (entry - hi)
        mfe = max(mfe, up)
        mae = min(mae, dn)
        best_favourable = max(best_favourable, hi) if direction > 0 \
            else min(best_favourable, lo)

        # break-even arming happens before the touch test for this bar, matching the
        # production engine's stated behaviour
        if breakeven_at_r is not None and not breakeven_armed and mfe >= breakeven_at_r * risk:
            breakeven_armed = True
            stop_px = entry

        if trail_atr is not None:
            trailed = best_favourable - trail_atr * atr * direction
            stop_px = trailed if stop_px is None else (
                max(stop_px, trailed) if direction > 0 else min(stop_px, trailed))

        events = _events_on_bar(
            hi, lo, cl, direction, stop_px, target_px, i - entry_bar, time_stop_bars,
            float(signal[i]) if i < len(signal) else 0.0, i == last_index, use_invalidation)
        chosen = _resolve(events)
        if not chosen:
            continue

        ambiguous = ("stop" in events and "target" in events)
        if chosen == "stop":
            px = float(stop_px)
        elif chosen == "target":
            px = float(target_px)
        else:
            px = cl
        return _finish(entry_bar, i, direction, quantity, entry, px, chosen, mfe, mae,
                       multiplier, round_turn_cost, ambiguous, tuple(sorted(events)))

    return _finish(entry_bar, last_index, direction, quantity, entry,
                   float(closes[last_index]), "forced_flatten", mfe, mae,
                   multiplier, round_turn_cost, False, ("forced_flatten",))


def _finish(eb: int, xb: int, d: int, qty: int, entry: float, exit_px: float, reason: str,
            mfe: float, mae: float, mult: float, cost: float, ambiguous: bool,
            events: tuple[str, ...]) -> RefBracket:
    pts = (exit_px - entry) * d
    gross = pts * mult * qty
    return RefBracket(entry_bar=eb, exit_bar=xb, direction=d, quantity=qty,
                      entry_price=entry, exit_price=exit_px, points=pts, gross=gross,
                      cost=cost * qty, net=gross - cost * qty, reason=reason,
                      bars_held=xb - eb, mfe_points=mfe, mae_points=mae,
                      ambiguous=ambiguous, events_at_exit=events)


__all__ = ["PRECEDENCE", "RefBracket", "simulate_bracket_reference"]
