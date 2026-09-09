"""VWAP trend: ride intraday momentum on the side of VWAP, flip on a confirmed cross.

Hypothesis: on liquid, high-beta names, price staying on one side of VWAP with positive
short-horizon momentum continues more often than it reverts, and the cost of a flip is
small relative to the size of the trends. This is the turnover engine of the sleeve: it
re-evaluates every minute and can flip several times per name per day.
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
}


def decide(now, feats, book, equity, state, params):
    p = {**PARAMS, **(params or {})}
    is_new_session(state, now)
    side_state = state.setdefault("side", {})  # symbol -> +1/-1
    targets = {}
    band, xband = p["band_bps"] / 1e4, p["exit_band_bps"] / 1e4
    for sym, f in feats.items():
        if len(f) < p["mom_bars"] + 2:
            continue
        row = f.iloc[-1]
        m = int(row["minute"])
        vwap = row["vwap"]
        if vwap != vwap or row["vol30"] != row["vol30"]:
            continue
        c = row["c"]
        dev = c / vwap - 1.0
        mom = c / f["c"].iloc[-1 - p["mom_bars"]] - 1.0
        cur = side_state.get(sym, 0)
        if cur > 0:
            if dev < -xband:
                cur = 0
        elif cur < 0:
            if dev > xband:
                cur = 0
        if cur == 0 and p["start_minute"] <= m <= p["stop_minute"] and row["vol30"] >= p["vol_floor"]:
            if dev > band and mom > p["mom_min"]:
                cur = 1
            elif dev < -band and mom < -p["mom_min"]:
                cur = -1
        side_state[sym] = cur
        if cur:
            targets[sym] = cur * p["weight"] * (1 if p["direction"] >= 0 else -1)
    return targets
