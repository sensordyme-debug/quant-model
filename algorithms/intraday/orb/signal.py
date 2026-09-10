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

O-1 adds the options-implied day gate (`iv_gate`, default off). A-9 refused the opening range as
a within-session handle on the same mechanism; the untried one is a *forecast*, SPY's implied
volatility at yesterday's close, from `data/options/iv_regime.parquet`
(`scripts/iv_regime.py`). `iv_gate="high"` trades only sessions whose previous close read above
the trailing `iv_lookback`-day median of `iv_feature`, `"low"` only the ones below. The lookup is
by session date and both the value and its threshold are strictly prior-day, so nothing here is
contemporaneous; a session the store does not cover is **not traded** (fail closed), which is also
what a live run with a stale store must do. Live note: the store is EOD, so the deployed launcher
would have to refresh it before the open - the gate stays off until a study justifies it.

A-9 adds the width gate. A-4 measured that this sleeve's daily P&L correlates +0.538 (t=+10.25,
n=260) with the universe's same-day range: the payoff scales with the day's range, the cost
floor does not. A day-ahead gate is not available, but the opening range is closed before the
first entry, so its width divided by ATR14 at that moment is known at entry and causal.
`range_atr_min` / `range_atr_max` bound that ratio; both default to 0 (off), which reproduces
the deployed behaviour exactly. The ratio is snapshotted when the range closes, not re-read at
each bar, so a session's gate is one number per symbol. Only within-session quantities are used
- the live feed carries 3 days of bars, so anything needing a trailing multi-session baseline
would be NaN live and is deliberately not used here.
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
    "range_atr_min": 0.0,    # A-9: only take breakouts whose opening range is at least this many
                             # ATR14 wide, measured when the range closes (0 = off)
    "range_atr_max": 0.0,    # A-9: ...and at most this many (0 = off)
    "iv_gate": "",           # O-1: "high" / "low" / "" (off) - trade only sessions whose prior
                             # close read above / below the trailing median of `iv_feature`
    "iv_feature": "iv_atm_1w",
    "iv_lookback": 60,
}

_IV_CACHE: dict = {}


def _iv_pass(day, sign: str, feature: str, lookback: int) -> bool:
    """True if session `day` passes the prior-day implied-vol gate. Fails closed."""
    key = (feature, int(lookback))
    gate = _IV_CACHE.get(key)
    if gate is None:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
            import pandas as pd

            import iv_regime
            g = iv_regime.load_gate(feature, int(lookback))
            days = pd.to_datetime(pd.Series(list(g.index))).dt.date.values
            gate = {d: (float(v), float(m)) for d, v, m in
                    zip(days, g["value"].values, g["median"].values) if v == v and m == m}
        except Exception:  # noqa: BLE001 - no store, no gate, no trades
            gate = {}
        _IV_CACHE[key] = gate
    hit = gate.get(day)
    if hit is None:
        return False
    return hit[0] > hit[1] if sign == "high" else hit[0] < hit[1]


def _range(f, sym, state, rng_minutes):
    """Opening range [high, low, atr_at_close] for this session, computed once and cached in `state`.

    `atr_at_close` is ATR14 on the bar at which the range first closes, so the width/ATR ratio
    A-9 gates on is a single per-session number known before any entry is allowed.
    """
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
    atr_or = float(row["atr14"]) if row["atr14"] == row["atr14"] else 0.0
    cache[sym] = [hi, lo, atr_or]
    return cache[sym]


def decide(now, feats, book, equity, state, params):
    p = {**PARAMS, **(params or {})}
    is_new_session(state, now)
    pos = state.setdefault("pos", {})          # symbol -> {"side", "entry", "stop", "risk", "w", "scaled"}
    entries = state.setdefault("entries", {})  # symbol -> {"long": n, "short": n}
    rng_minutes = int(p["range_minutes"])
    scale_out = float(p["scale_out"])
    # O-1: one prior-day lookup per session, cached in `state` so it costs nothing per bar.
    # A blocked session still manages positions already open (there are none, since the gate is
    # decided before the first entry of the day) but takes no new entry.
    iv_sign = str(p.get("iv_gate") or "")
    if iv_sign:
        if "iv_ok" not in state:
            state["iv_ok"] = _iv_pass(now.date(), iv_sign, str(p["iv_feature"]), int(p["iv_lookback"]))
        if not state["iv_ok"]:
            return {}
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
        lo_gate, hi_gate = float(p["range_atr_min"]), float(p["range_atr_max"])
        if lo_gate > 0 or hi_gate > 0:
            atr_or = float(rng[2]) if len(rng) > 2 else 0.0
            width_atr = (hi - lo) / atr_or if atr_or > 0 else float("nan")
            if width_atr != width_atr:                       # no ATR at the range close: fail closed
                continue
            if lo_gate > 0 and width_atr < lo_gate:
                continue
            if hi_gate > 0 and width_atr > hi_gate:
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
