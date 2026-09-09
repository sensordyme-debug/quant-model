"""VWAP trend: ride intraday momentum on the side of VWAP, flip on a confirmed cross.

Hypothesis: on liquid, high-beta names, price staying on one side of VWAP with positive
short-horizon momentum continues more often than it reverts, and the cost of a flip is
small relative to the size of the trends. This is the turnover engine of the sleeve: it
re-evaluates every minute and can flip several times per name per day.

`direction = -1` inverts it into the VWAP *fade* (A-0's variant), which is what the sleeve
ever ran. A-6 measured that fade at -56%/yr in-sample on the 9-month window, so A-1 added
the levers below - min hold, a midday skip, a session-trend filter, a range-expansion gate
and a coarser decision cadence - each defaulted to the shipped behaviour, to test whether
the module can pay for its ~98 trades/day. See research/journal.md, A-1.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from base import is_new_session  # noqa: E402

NAME = "vwap_trend"
PARAMS = {
    "weight": 0.10,
    "band_bps": 8.0,         # distance from VWAP required to enter, in basis points
    "exit_band_bps": 2.0,    # cross back through VWAP by this much to exit (hysteresis)
    "mom_bars": 10,          # short-horizon momentum lookback
    "mom_min": 0.0005,       # 5 bps over mom_bars
    "start_minute": 30,      # no entries before 10:00 ET
    "stop_minute": 360,      # no entries after 15:30 ET
    "vol_floor": 0.0004,     # skip names with 30-bar realized vol below 4 bps/min (dead tape)
    "direction": 1,          # +1 trend-following (ride the VWAP side), -1 reversal (fade the extension)
    # --- A-1 turnover levers, all defaulted off so the module reproduces A-6 exactly ---
    "min_hold": 0,           # bars a position must be held before an exit is allowed
    "skip_from": 0,          # no entries while skip_from <= minute < skip_to (skip_to <= skip_from = off)
    "skip_to": 0,
    "trend_align": 0,        # +1: only positions agreeing with the session's move, -1: only against it
    "trend_min": 0.0,        # |day_ret| floor below which trend_align refuses to trade at all
    "atr_expand_min": 0.0,   # require atr14 >= x * the session's mean atr14 so far (0 = off)
    "agg": 1,                # only re-evaluate entries and exits on bars where minute % agg == 0
}


def decide(now, feats, book, equity, state, params):
    p = {**PARAMS, **(params or {})}
    is_new_session(state, now)
    side_state = state.setdefault("side", {})  # symbol -> +1/-1
    held_since = state.setdefault("held_since", {})  # symbol -> minute the position was opened
    atr_acc = state.setdefault("atr_acc", {})  # symbol -> [sum, count, last minute counted]
    targets = {}
    band, xband = p["band_bps"] / 1e4, p["exit_band_bps"] / 1e4
    agg = max(1, int(p["agg"]))
    skip_on = p["skip_to"] > p["skip_from"]
    for sym, f in feats.items():
        if len(f) < p["mom_bars"] + 2:
            continue
        row = f.iloc[-1]
        m = int(row["minute"])
        vwap = row["vwap"]
        if vwap != vwap or row["vol30"] != row["vol30"]:
            continue
        # causal session-so-far mean ATR, accumulated one bar at a time (state resets at 09:30)
        atr = float(row["atr14"])
        if atr == atr:
            acc = atr_acc.setdefault(sym, [0.0, 0, -1])
            if m > acc[2]:
                acc[0] += atr
                acc[1] += 1
                acc[2] = m
        c = row["c"]
        dev = c / vwap - 1.0
        mom = c / f["c"].iloc[-1 - p["mom_bars"]] - 1.0
        cur = side_state.get(sym, 0)
        evaluate = (m % agg == 0)
        if cur and evaluate and m - held_since.get(sym, m) >= p["min_hold"]:
            if cur > 0 and dev < -xband:
                cur = 0
            elif cur < 0 and dev > xband:
                cur = 0
        if (cur == 0 and evaluate and p["start_minute"] <= m <= p["stop_minute"]
                and row["vol30"] >= p["vol_floor"] and not (skip_on and p["skip_from"] <= m < p["skip_to"])):
            want = 0
            if dev > band and mom > p["mom_min"]:
                want = 1
            elif dev < -band and mom < -p["mom_min"]:
                want = -1
            if want and p["atr_expand_min"] > 0:
                acc = atr_acc.get(sym)
                if not (acc and acc[1] >= 10 and atr == atr and atr >= p["atr_expand_min"] * acc[0] / acc[1]):
                    want = 0
            if want and p["trend_align"]:
                pos_sign = want * (1 if p["direction"] >= 0 else -1)
                day_ret = float(row["day_ret"])
                if day_ret != day_ret or abs(day_ret) < p["trend_min"] or day_ret == 0:
                    want = 0
                elif pos_sign * (1 if day_ret > 0 else -1) != (1 if p["trend_align"] > 0 else -1):
                    want = 0
            if want:
                cur = want
                held_since[sym] = m
        side_state[sym] = cur
        if cur:
            targets[sym] = cur * p["weight"] * (1 if p["direction"] >= 0 else -1)
    return targets
