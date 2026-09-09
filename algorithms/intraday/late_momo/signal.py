"""Late-day momentum: in the last hour, lean with the day's direction.

Hypothesis: on days with a decisive move by 15:00 ET, the final hour tends to extend it
(index rebalancing, trend-following flows, short covering). Positions are opened at 15:00
and handed to the framework's end-of-day flatten (15:38), so every trade is a ~35-minute hold.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from base import is_new_session  # noqa: E402

NAME = "late_momo"
PARAMS = {
    "weight": 0.10,
    "entry_minute": 330,     # 15:00 ET
    "min_move": 0.006,       # |day return| at 15:00 must exceed 60 bps
    "max_names": 6,          # strongest movers only
}


def decide(now, feats, book, equity, state, params):
    p = {**PARAMS, **(params or {})}
    is_new_session(state, now)
    chosen = state.get("chosen")
    m = None
    for sym, f in feats.items():
        if len(f):
            m = int(f.iloc[-1]["minute"])
            break
    if m is None or m < p["entry_minute"]:
        return {}
    if chosen is None:
        moves = {}
        for sym, f in feats.items():
            r = float(f.iloc[-1]["day_ret"])
            if r == r and abs(r) >= p["min_move"]:
                moves[sym] = r
        top = sorted(moves.items(), key=lambda kv: -abs(kv[1]))[: p["max_names"]]
        chosen = {s: (1.0 if r > 0 else -1.0) for s, r in top}
        state["chosen"] = chosen
    return {s: side * p["weight"] for s, side in chosen.items()}
