"""Exit architectures: what happens to a position after the entry decision is made.

WHY THIS IS LIBRARY CODE AND NOT A SCRIPT
-------------------------------------------
Every strategy in the repository is a stateless per-bar signal with no stop, no target and no
exit rule. That is the structural gap the selection lab identified, and closing it needs one
simulator that every architecture runs through - otherwise "ATR stop beats time stop" becomes
a statement about two different pieces of code.

THE INTRABAR AMBIGUITY, RESOLVED PESSIMISTICALLY
--------------------------------------------------
Minute bars carry a high and a low but not their order. When a bar's range spans both the stop
and the target, one of them was hit first and the data cannot say which.

This simulator always assumes the STOP was hit first. That is the conservative choice and it
matters more than it sounds: on a wide bar with a tight stop and a tight target, the optimistic
convention converts losses into wins at exactly the parameter settings a grid search is drawn
to. Any result here is therefore a floor, and the size of the ambiguity is reported
(`ambiguous_bars`) so a reader can see how often the convention bound.

FILLS
-----
Entry at the signal bar's close, matching the lab's existing convention so numbers reconcile.
Stop and target fills at their trigger price, not at the bar's close - a stop that gapped
through would fill worse, and the slippage parameter is what covers that.

WHAT AN ARCHITECTURE IS
-------------------------
A small declarative object, not a function, so that a grid can be enumerated, logged and
reproduced. Every field is optional and `None` means "this leg is not part of this
architecture" - a pure time stop has no price stop at all, and that is a legitimate design
rather than a missing value.

The end-of-session flatten is not optional and is not a parameter. Every position closes on
the session's last bar, because Topstep's mandatory flat is not negotiable.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Exit reasons this simulator can distinguish.
STOP = "stop"
TARGET = "target"
TRAIL = "trail"
TIME = "time_stop"
INVALIDATION = "signal_invalidation"
FLATTEN = "forced_flatten"


@dataclass(frozen=True)
class ExitArchitecture:
    """One declarative exit design. `None` means the leg is absent, not zero."""

    name: str
    #: Initial stop, in multiples of the entry session's ATR.
    stop_atr: float | None = None
    #: Profit target, in multiples of R where R is the initial stop distance.
    target_r: float | None = None
    #: Stop placed at the signal bar's own extreme instead of an ATR distance.
    structural_stop: bool = False
    #: Trailing stop distance in ATR multiples, applied after entry.
    trail_atr: float | None = None
    #: Move the stop to entry once this many R of favourable excursion is reached.
    breakeven_at_r: float | None = None
    #: Hard exit after this many bars.
    time_stop_bars: int | None = None
    #: Exit when the originating signal is no longer true. This is what the library does now.
    use_invalidation: bool = True

    def describe(self) -> str:
        bits = []
        if self.structural_stop:
            bits.append("stop at signal-bar extreme")
        elif self.stop_atr is not None:
            bits.append(f"stop {self.stop_atr:g} ATR")
        if self.target_r is not None:
            bits.append(f"target {self.target_r:g}R")
        if self.trail_atr is not None:
            bits.append(f"trail {self.trail_atr:g} ATR")
        if self.breakeven_at_r is not None:
            bits.append(f"break-even at {self.breakeven_at_r:g}R")
        if self.time_stop_bars is not None:
            bits.append(f"time stop {self.time_stop_bars}b")
        if self.use_invalidation:
            bits.append("signal invalidation")
        return ", ".join(bits) if bits else "session close only"


@dataclass(frozen=True)
class ExitResult:
    entry_bar: int
    exit_bar: int
    direction: int
    entry_price: float
    exit_price: float
    points: float                  # signed, in points, before costs
    reason: str
    bars_held: int
    mfe_points: float
    mae_points: float
    r_multiple: float              # against the architecture's own initial risk
    ambiguous: bool                # both stop and target inside one bar's range


def simulate_trade(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray,
                   signal: np.ndarray, entry_bar: int, direction: int,
                   atr: float, arch: ExitArchitecture) -> ExitResult:
    """Walk one position forward bar by bar until an exit rule fires.

    The order of checks inside a bar is fixed and pessimistic: stop, then target, then trail,
    then time, then invalidation. A bar that could have produced either a stop or a target is
    recorded as a stop AND flagged ambiguous.
    """
    n = len(closes)
    entry = float(closes[entry_bar])
    last = n - 1

    if arch.structural_stop:
        lo, hi = float(lows[entry_bar]), float(highs[entry_bar])
        risk = (entry - lo) if direction > 0 else (hi - entry)
        risk = max(risk, 1e-9)
    elif arch.stop_atr is not None:
        risk = max(arch.stop_atr * atr, 1e-9)
    else:
        risk = max(atr, 1e-9)          # a nominal R for reporting when there is no stop

    stop_px = (entry - risk * direction) if (arch.stop_atr is not None
                                             or arch.structural_stop) else None
    target_px = (entry + arch.target_r * risk * direction
                 if arch.target_r is not None else None)

    best = entry                        # running favourable extreme, for trail and MFE
    mfe = mae = 0.0
    ambiguous = False
    be_armed = False

    for i in range(entry_bar + 1, n):
        hi, lo, cl = float(highs[i]), float(lows[i]), float(closes[i])
        up = (hi - entry) * direction
        dn = (lo - entry) * direction
        mfe = max(mfe, up if direction > 0 else (entry - lo))
        mae = min(mae, dn if direction > 0 else (entry - hi))
        if direction > 0:
            mfe = max(mfe, hi - entry)
            mae = min(mae, lo - entry)
            best = max(best, hi)
        else:
            mfe = max(mfe, entry - lo)
            mae = min(mae, entry - hi)
            best = min(best, lo)

        # ---- break-even arming -----------------------------------------------------------
        if (arch.breakeven_at_r is not None and not be_armed
                and mfe >= arch.breakeven_at_r * risk):
            be_armed = True
            stop_px = entry

        # ---- trailing stop ----------------------------------------------------------------
        if arch.trail_atr is not None:
            t = best - arch.trail_atr * atr * direction
            stop_px = t if stop_px is None else (max(stop_px, t) if direction > 0
                                                 else min(stop_px, t))

        hit_stop = stop_px is not None and (lo <= stop_px if direction > 0
                                            else hi >= stop_px)
        hit_target = target_px is not None and (hi >= target_px if direction > 0
                                                else lo <= target_px)
        if hit_stop and hit_target:
            ambiguous = True
        if hit_stop:
            px = float(stop_px)
            return _result(entry_bar, i, direction, entry, px, TRAIL if
                           (arch.trail_atr is not None and not be_armed
                            and arch.stop_atr is None) else STOP,
                           mfe, mae, risk, ambiguous)
        if hit_target:
            return _result(entry_bar, i, direction, entry, float(target_px), TARGET,
                           mfe, mae, risk, ambiguous)
        if arch.time_stop_bars is not None and (i - entry_bar) >= arch.time_stop_bars:
            return _result(entry_bar, i, direction, entry, cl, TIME, mfe, mae, risk,
                           ambiguous)
        if arch.use_invalidation and signal[i] != direction:
            return _result(entry_bar, i, direction, entry, cl, INVALIDATION, mfe, mae,
                           risk, ambiguous)
        if i == last:
            return _result(entry_bar, i, direction, entry, cl, FLATTEN, mfe, mae, risk,
                           ambiguous)
    return _result(entry_bar, last, direction, entry, float(closes[last]), FLATTEN,
                   mfe, mae, risk, ambiguous)


def _result(eb: int, xb: int, d: int, entry: float, exit_px: float, reason: str,
            mfe: float, mae: float, risk: float, ambiguous: bool) -> ExitResult:
    pts = (exit_px - entry) * d
    return ExitResult(entry_bar=eb, exit_bar=xb, direction=d, entry_price=entry,
                      exit_price=exit_px, points=float(pts), reason=reason,
                      bars_held=int(xb - eb), mfe_points=float(mfe),
                      mae_points=float(mae),
                      r_multiple=float(pts / risk) if risk > 0 else float("nan"),
                      ambiguous=ambiguous)


def entry_events(pos: np.ndarray) -> list[tuple[int, int]]:
    """(bar, direction) for every moment the signal opens a position."""
    out, prev = [], 0.0
    for i, p in enumerate(pos):
        if p != 0 and p != prev:
            out.append((i, int(np.sign(p))))
        prev = p
    return out


__all__ = ["ExitArchitecture", "ExitResult", "FLATTEN", "INVALIDATION", "STOP", "TARGET",
           "TIME", "TRAIL", "entry_events", "simulate_trade"]
