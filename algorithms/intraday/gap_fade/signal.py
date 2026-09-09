"""Gap fade: fade large overnight gaps during the first hour.

Hypothesis: on liquid names, an opening gap beyond a threshold partially fills in the first
hour more often than it extends (overnight news is over-reacted to by the open). Enter at
the end of the opening range (09:45) against the gap, exit when the gap has half-filled, when
price moves further against by an ATR multiple, or at the time stop.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from base import is_new_session  # noqa: E402

NAME = "gap_fade"
PARAMS = {
    "weight": 0.12,
    "min_gap": 0.012,        # |open / prev_close - 1| >= 1.2%
    "max_gap": 0.08,         # ignore halts / news bombs
    "entry_minute": 15,      # after the opening range
    "time_stop": 90,         # 11:00 ET
    "target_fill": 0.5,      # exit when half the gap has filled
    "stop_atr": 2.0,         # exit if price extends the gap by 2 x ATR(14) beyond entry
    "max_names": 6,
}


def decide(now, feats, book, equity, state, params):
    p = {**PARAMS, **(params or {})}
    is_new_session(state, now)
    pos = state.setdefault("pos", {})     # sym -> {"side", "entry", "target", "stop"}
    done = state.setdefault("done", [])
    targets = {}
    m = None
    for sym, f in feats.items():
        if not len(f):
            continue
        row = f.iloc[-1]
        m = int(row["minute"])
        if sym in pos:
            d = pos[sym]
            c = float(row["c"])
            exit_ = (d["side"] > 0 and (c >= d["target"] or c <= d["stop"])) or \
                    (d["side"] < 0 and (c <= d["target"] or c >= d["stop"])) or m >= p["time_stop"]
            if exit_:
                pos.pop(sym, None)
                done.append(sym)
                continue
            targets[sym] = d["side"] * p["weight"]
            continue
        if m != p["entry_minute"] or sym in done or len(pos) >= p["max_names"]:
            continue
        prev, open_ = row["prev_close"], row["sess_open"]
        if prev != prev or not prev or open_ != open_:
            continue
        gap = open_ / prev - 1.0
        if abs(gap) < p["min_gap"] or abs(gap) > p["max_gap"]:
            continue
        atr = float(row["atr14"]) if row["atr14"] == row["atr14"] else abs(open_ - prev) * 0.1
        c = float(row["c"])
        side = -1 if gap > 0 else 1                      # fade the gap
        target = c - side * 0  # placeholder replaced below
        fill_level = prev + (open_ - prev) * (1 - p["target_fill"])   # half-way back to prev close
        stop = c - side * p["stop_atr"] * atr
        pos[sym] = {"side": side, "entry": c, "target": fill_level, "stop": stop}
        targets[sym] = side * p["weight"]
    return targets
