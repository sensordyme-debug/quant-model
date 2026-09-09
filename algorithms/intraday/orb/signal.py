"""ORB: opening-range breakout with a configurable stop, optional scale-out and a time stop.

Hypothesis: the first 15 minutes set a range that, when broken on above-average volume,
tends to continue for the next hour or two on the most liquid names. Short side is taken
symmetrically. One entry per side per session, re-entry allowed once after a stop.

A-2 adds tail control on top of that, all defaulted to the A-6 deployed behaviour:
  * `stop`: "mid" (exit when the close crosses the range midpoint, the shipped rule) or
    "atr" (exit at `stop_atr` x ATR14 from the entry close, a tighter and range-independent
    risk unit);
  * `range_minutes`: length of the opening range; 15 reads the columns `base.features`
    already computes, anything else is measured from the session view;
  * `scale_out`: fraction of the position released once price reaches `scale_r` x the entry
    risk, optionally moving the stop to breakeven for the remainder.
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
    "stop": "mid",           # "mid": exit when close crosses the range midpoint; "atr": ATR14 stop
    "stop_atr": 1.25,        # ATR14 multiples from the entry close, used when stop == "atr"
    "range_minutes": 15,     # opening-range length in minutes
    "scale_out": 0.0,        # fraction of the position released at scale_r (0 = off)
    "scale_r": 1.5,          # R multiple at which the scale-out fires
    "scale_breakeven": True, # after scaling out, move the stop to the entry price
    "disaster_atr": 0.0,     # extra backstop with stop == "mid": exit at this many ATR14 against
                             # the entry, whichever of the two triggers first (0 = off)
}


def _range(f, sym, state, rng_minutes):
    """Opening range [high, low] for this session, computed once and cached in `state`."""
    cache = state.setdefault("rng", {})
    hit = cache.get(sym)
    if hit is not None:
        return hit
    row = f.iloc[-1]
    if int(row["minute"]) < rng_minutes:
        return None
    if rng_minutes == 15:
        hi, lo = float(row["or_high"]), float(row["or_low"])
    else:
        mask = f["minute"].values < rng_minutes
        if not mask.any():
            return None
        hi, lo = float(f["h"].values[mask].max()), float(f["l"].values[mask].min())
    if hi != hi or lo != lo or hi <= lo:
        return None
    cache[sym] = [hi, lo]
    return cache[sym]


def decide(now, feats, book, equity, state, params):
    p = {**PARAMS, **(params or {})}
    is_new_session(state, now)
    pos = state.setdefault("pos", {})          # symbol -> {"side", "entry", "stop", "risk", "w", "scaled"}
    entries = state.setdefault("entries", {})  # symbol -> {"long": n, "short": n}
    rng_minutes = int(p["range_minutes"])
    scale_out = float(p["scale_out"])
    targets = {}
    for sym, f in feats.items():
        if len(f) < rng_minutes + 1:
            continue
        row = f.iloc[-1]
        rng = _range(f, sym, state, rng_minutes)
        if rng is None:
            continue
        hi, lo = float(rng[0]), float(rng[1])
        mid = (hi + lo) / 2.0
        m = int(row["minute"])
        c = float(row["c"])
        held = pos.get(sym)
        if held:
            side = int(held["side"])
            stop = float(held["stop"])
            if (side > 0 and c < stop) or (side < 0 and c > stop) or m >= p["time_stop"]:
                pos.pop(sym, None)
                continue
            if scale_out > 0 and not held.get("scaled") and held["risk"] > 0:
                target_px = held["entry"] + side * float(p["scale_r"]) * held["risk"]
                if (side > 0 and c >= target_px) or (side < 0 and c <= target_px):
                    held["scaled"] = True
                    held["w"] = held["w"] * (1.0 - scale_out)
                    if p["scale_breakeven"]:
                        held["stop"] = held["entry"]
            targets[sym] = side * held["w"]
            continue
        if m < max(int(p["entry_after"]), rng_minutes) or m > p["entry_before"]:
            continue
        e = entries.setdefault(sym, {"long": 0, "short": 0})
        strong_vol = float(row["vol_ratio"]) >= p["vol_ratio_min"] if row["vol_ratio"] == row["vol_ratio"] else False
        if not strong_vol:
            continue
        if c > hi and e["long"] < p["max_entries"]:
            side, key = 1, "long"
        elif c < lo and e["short"] < p["max_entries"]:
            side, key = -1, "short"
        else:
            continue
        atr = float(row["atr14"]) if row["atr14"] == row["atr14"] else 0.0
        if p["stop"] == "atr" and atr > 0:
            stop_px = c - side * float(p["stop_atr"]) * atr
        else:
            stop_px = mid
            if float(p["disaster_atr"]) > 0 and atr > 0:
                backstop = c - side * float(p["disaster_atr"]) * atr
                stop_px = max(stop_px, backstop) if side > 0 else min(stop_px, backstop)
        risk = abs(c - stop_px)
        if risk <= 0:
            continue
        pos[sym] = {"side": side, "entry": c, "stop": stop_px, "risk": risk,
                    "w": float(p["weight"]), "scaled": False}
        e[key] += 1
        targets[sym] = side * float(p["weight"])
    return targets
