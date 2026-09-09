"""Causal per-bar features for the intraday sleeve. Shared by backtest, replay and live.

`features(df)` takes a 1-minute bar frame (o,h,l,c,v, tz-aware ET index, possibly spanning
many sessions) and returns a frame aligned to it. Every column at row t uses bars <= t only,
and session-scoped columns (VWAP, opening range, session open, minute index) reset at 09:30.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

OR_MINUTES = 15          # opening range = first 15 one-minute bars (09:30-09:44)


def features(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    f = pd.DataFrame(index=df.index)
    f["o"], f["h"], f["l"], f["c"], f["v"] = df["o"], df["h"], df["l"], df["c"], df["v"]
    day = pd.Index(df.index.date)
    f["day"] = day
    minute = (df.index.hour - 9) * 60 + df.index.minute - 30          # 0 at 09:30
    f["minute"] = minute
    g = f.groupby(day, sort=False)
    # session-scoped
    pv = (df["c"] * df["v"])
    f["vwap"] = pv.groupby(day).cumsum() / df["v"].groupby(day).cumsum().replace(0, np.nan)
    f["sess_open"] = g["o"].transform("first")
    f["sess_high"] = g["h"].cummax()
    f["sess_low"] = g["l"].cummin()
    in_or = minute < OR_MINUTES
    f["or_high"] = df["h"].where(in_or).groupby(day).cummax().groupby(day).ffill()
    f["or_low"] = df["l"].where(in_or).groupby(day).cummin().groupby(day).ffill()
    f["or_done"] = minute >= OR_MINUTES
    # previous session close (for gap context)
    last_close = g["c"].last()
    prev_close = last_close.shift(1)
    f["prev_close"] = day.map(prev_close.to_dict()).astype(float)
    # rolling, within-session (reset by masking early bars)
    c = df["c"]
    f["ema20"] = c.groupby(day).transform(lambda s: s.ewm(span=20, adjust=False).mean())
    f["ret1"] = c.groupby(day).pct_change(1)
    f["ret5"] = c.groupby(day).pct_change(5)
    f["ret10"] = c.groupby(day).pct_change(10)
    f["ret30"] = c.groupby(day).pct_change(30)
    f["vol30"] = f["ret1"].groupby(day).transform(lambda s: s.rolling(30, min_periods=10).std())
    f["vol_ratio"] = df["v"] / df["v"].groupby(day).transform(lambda s: s.rolling(20, min_periods=5).mean())
    tr = pd.concat([df["h"] - df["l"], (df["h"] - c.shift(1)).abs(), (df["l"] - c.shift(1)).abs()], axis=1).max(axis=1)
    f["atr14"] = tr.groupby(day).transform(lambda s: s.rolling(14, min_periods=5).mean())
    f["day_ret"] = c / f["sess_open"] - 1.0
    return f


def is_new_session(state: dict, now: pd.Timestamp) -> bool:
    """Reset helper: returns True (and records the day) when `now` is the first bar of a session
    the state has not seen."""
    d = str(now.date())
    if state.get("session") != d:
        state.clear()
        state["session"] = d
        return True
    return False


def clamp_targets(targets: dict[str, float], per_symbol: float, gross: float) -> dict[str, float]:
    out = {s: max(-per_symbol, min(per_symbol, float(w))) for s, w in targets.items() if abs(float(w)) > 1e-6}
    total = sum(abs(w) for w in out.values())
    if total > gross and total > 0:
        out = {s: w * gross / total for s, w in out.items()}
    return out
