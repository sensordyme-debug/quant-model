"""ORB: opening-range breakout with a midpoint stop and a time stop.

Hypothesis: the first 15 minutes set a range that, when broken on above-average volume,
tends to continue for the next hour or two on the most liquid names. Short side is taken
symmetrically. One entry per side per session, re-entry allowed once after a stop.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from base import is_new_session  # noqa: E402

NAME = "orb"
PARAMS = {
    "weight": 0.12,          # fraction of equity per position
    "vol_ratio_min": 1.2,    # breakout bar volume vs 20-bar average
    "entry_after": 15,       # minute index from which entries are allowed
    "entry_before": 150,     # no new entries after 12:00 ET
    "time_stop": 240,        # exit at 13:30 ET at the latest
    "max_entries": 2,        # per side per session
    "stop": "mid",           # exit when close crosses the range midpoint
}


def decide(now, feats, book, equity, state, params):
    p = {**PARAMS, **(params or {})}
    is_new_session(state, now)
    pos = state.setdefault("pos", {})          # symbol -> {"side": +1/-1}
    entries = state.setdefault("entries", {})  # symbol -> {"long": n, "short": n}
    targets = {}
    for sym, f in feats.items():
        if len(f) < 16:
            continue
        row = f.iloc[-1]
        if not bool(row["or_done"]) or row["or_high"] != row["or_high"]:
            continue
        m = int(row["minute"])
        mid = (row["or_high"] + row["or_low"]) / 2.0
        held = pos.get(sym)
        if held:
            side = held["side"]
            crossed = (side > 0 and row["c"] < mid) or (side < 0 and row["c"] > mid)
            if crossed or m >= p["time_stop"]:
                pos.pop(sym, None)
                continue
            targets[sym] = side * p["weight"]
            continue
        if m < p["entry_after"] or m > p["entry_before"]:
            continue
        e = entries.setdefault(sym, {"long": 0, "short": 0})
        strong_vol = float(row["vol_ratio"]) >= p["vol_ratio_min"] if row["vol_ratio"] == row["vol_ratio"] else False
        if row["c"] > row["or_high"] and strong_vol and e["long"] < p["max_entries"]:
            pos[sym] = {"side": 1}
            e["long"] += 1
            targets[sym] = p["weight"]
        elif row["c"] < row["or_low"] and strong_vol and e["short"] < p["max_entries"]:
            pos[sym] = {"side": -1}
            e["short"] += 1
            targets[sym] = -p["weight"]
    return targets
