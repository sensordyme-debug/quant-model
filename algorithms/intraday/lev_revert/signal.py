"""L-1: intraday mean reversion on leveraged (3x) index ETFs.

Hypothesis (backlog L-1). SOXL/SOXS/TQQQ/SQQQ/UPRO/SPXU move 3-6% a day, and their
daily-reset construction forces the issuer to rebalance notional in the direction of the day's
move at the close, which dealers pre-hedge intraday. If that flow pushes price away from the
session's volume-weighted average and it comes back, then fading a stretched deviation from
VWAP with a tight time stop is paid. The deviation is measured in units of the name's own
14-bar ATR so one threshold means the same thing on SOXL (6%/day) and on SPXU (3%/day) and in
2016 as in 2026.

Mechanics, all causal (`base.features` uses bars <= t only):

    z = (close / vwap - 1) / (atr14 / close)      # deviation in per-bar ATR units
    entry  |z| >= entry_z                          # position side = -sign(z) when direction=-1
    exit   sign(z at entry) * z <= exit_z          # the stretch has collapsed (0 = back to VWAP)
        or held >= max_hold bars                   # time stop: the reversion is a minutes-scale claim
        or adverse move >= stop_atr ATRs           # the stretch kept going
    then a `cooldown`-bar block on re-entering the same name

`direction = +1` inverts the entry into a breakout/continuation control, which is the sign check
that separates "reversion pays" from "this window happened to trend".

Sizing is one flat `weight` per open name; the framework applies the per-symbol cap, the gross
cap, the loss limit and the 15:38 flatten. NOTE the pair structure of the universe: TQQQ above
VWAP and SQQQ below VWAP are the same bet on QQQ, so trading both legs roughly doubles cost for
one position. `scripts/sweep_l1.py` runs the 3-name (long-leveraged only) and 6-name variants
separately for that reason.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from base import clamp_targets, is_new_session  # noqa: E402

NAME = "lev_revert"
PARAMS = {
    "weight": 0.15,          # |weight| per open name, fraction of sleeve equity
    "entry_z": 6.0,          # enter when |close/vwap - 1| >= entry_z * atr14/close
    "exit_z": 1.0,           # exit when the stretch has collapsed to this many ATRs (0 = VWAP)
    "stop_atr": 6.0,         # adverse move from the entry price, in ATRs, that stops the trade out
    "max_hold": 30,          # bars: time stop
    "cooldown": 10,          # bars after any exit before the same name may be re-entered
    "start_minute": 20,      # no entries before 09:50 (VWAP is one bar wide at the open)
    "stop_minute": 340,      # no entries after 15:10; the framework flattens at 15:38
    "direction": -1,         # -1 fade the deviation (the hypothesis), +1 follow it (the control)
    "per_symbol": 0.20,      # strategy-level caps, applied before the framework's
    "gross": 1.20,
}


def decide(now, feats, book, equity, state, params):
    p = {**PARAMS, **(params or {})}
    is_new_session(state, now)
    pos = state.setdefault("pos", {})        # sym -> [side, entry_minute, entry_px, dsign]
    cool = state.setdefault("cool", {})      # sym -> first minute an entry is allowed again
    targets = {}
    for sym, f in feats.items():
        if len(f) < 20:
            continue
        row = f.iloc[-1]
        m = int(row["minute"])
        c, vwap, atr = float(row["c"]), float(row["vwap"]), float(row["atr14"])
        if not (c > 0 and vwap > 0 and atr == atr and atr > 0):
            continue
        scale = atr / c                       # fractional ATR, i.e. one "z" unit
        z = (c / vwap - 1.0) / scale
        st = pos.get(sym)
        if st is not None:
            side, m0, px0, dsign = st
            adverse = side * (c / px0 - 1.0) / scale        # ATRs in favour (negative = against)
            collapsed = dsign * z <= p["exit_z"]
            if collapsed or (m - m0) >= p["max_hold"] or adverse <= -p["stop_atr"]:
                pos.pop(sym, None)
                cool[sym] = m + int(p["cooldown"])
                st = None
        if st is None and p["start_minute"] <= m <= p["stop_minute"] and m >= cool.get(sym, -1):
            if abs(z) >= p["entry_z"]:
                dsign = 1.0 if z > 0 else -1.0
                side = dsign * (1.0 if p["direction"] > 0 else -1.0)
                pos[sym] = [side, m, c, dsign]
                st = pos[sym]
        if st is not None:
            targets[sym] = st[0] * p["weight"]
    return clamp_targets(targets, p["per_symbol"], p["gross"])
