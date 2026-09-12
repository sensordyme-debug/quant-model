"""Forward-return labels that know the difference between rows and time.

WHY THIS EXISTS: AUD-20
------------------------
`df.shift(-k)` moves k ROWS. A label built that way is only a k-period forward return if the
index is a regular grid with no gaps. Where a bar is missing, the shift silently pairs an
entry with an exit that is further away in time than the label claims, and the row is then
trained on and evaluated as though it were the intended horizon.

`sweep_f1.py` guards the obvious half of this - it nulls any forward return whose exit lands
on a different DAY (`fwd.where(exit_day == same_day)`). It does not guard within-day gaps,
because on the IBKR store there are none. Measured:

    IBKR   data/minute        20,399 five-minute rows over   263 sessions: 0 within-day gaps
    Alpaca data/minute_alpaca 209,184 rows over 2,686 sessions: 73 gaps of 10-45 minutes,
           and 163 of 190,394 same-day HOLD windows (0.09%) whose true span is not 30
           minutes. The worst spans 2h10m while being labelled a 30-minute return.

So the defect is real, currently latent on the execution-matched store, and live on the store
`AGENTS.md` recommends for statistical power ("run any intraday harness on it with
INTRADAY_DATA_DIR=data/minute_alpaca"). 0.09% is small; it is also exactly the kind of small
that a fat-tailed 4x-horizon observation exploits, and it costs nothing to remove.

THE FIX
-------
Check the elapsed TIME of the window, not just the day. `forward_span_mask` returns True only
where shifting k rows moved exactly the intended duration, so a label either means what it
says or is dropped.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def forward_span_mask(index, steps: int, expected, *, same_day: bool = True):
    """True where shifting forward by `steps` rows spans exactly `expected` time.

    Args:
        index:    a DatetimeIndex, the bar timestamps.
        steps:    how many rows the label shifts forward (entry offset to exit offset).
        expected: the duration those steps should represent (a Timedelta or minutes).
        same_day: also require entry and exit to be on the same calendar day. Kept as an
                  option rather than assumed, because an overnight-holding label legitimately
                  crosses the boundary and would be wrongly dropped.

    Returns a boolean Series aligned to `index`. Rows near the end, where the shift runs off
    the end of the series, are False - the window does not exist rather than being incomplete.
    """
    idx = pd.DatetimeIndex(index)
    if isinstance(expected, (int, float)):
        expected = pd.Timedelta(minutes=float(expected))
    s = pd.Series(idx, index=idx)
    span = s.shift(-steps) - s
    ok = span == expected
    if same_day:
        day = idx.to_series().dt.date
        ok = ok & (day.shift(-steps) == day)
    return pd.Series(ok, index=idx).fillna(False)


def forward_return(open_px, *, entry_offset: int, hold: int, bar_minutes: float,
                   same_day: bool = True):
    """log(open[t + entry_offset + hold] / open[t + entry_offset]), or NaN where the window
    does not span the time it claims.

    This is `sweep_f1`'s label with the missing guard added. On a gapless grid it is
    identical to the row-shift version, which is why the IBKR-store numbers do not move.
    """
    px = pd.Series(open_px)
    entry = px.shift(-entry_offset)
    exit_ = px.shift(-(entry_offset + hold))
    out = np.log(exit_ / entry)
    ok = forward_span_mask(px.index, entry_offset + hold, bar_minutes * (entry_offset + hold),
                           same_day=same_day)
    entry_ok = forward_span_mask(px.index, entry_offset, bar_minutes * entry_offset,
                                 same_day=same_day) if entry_offset else True
    return out.where(ok & entry_ok)


def overlap(horizon: int, step: int = 1) -> int:
    """How many periods consecutive labels share. 0 means non-overlapping.

    `sweep_f1` samples every 6 bars and holds 6 bars, so overlap is 0 and its naive t is
    defensible. `sweep_f3` samples every session and holds 5 or 21, so overlap is 4 or 20 and
    it is not. This makes that difference computable rather than something to re-derive.
    """
    return max(0, int(horizon) - int(step))


def grid_report(index, *, bar_minutes: float) -> dict:
    """Describe how regular a bar grid actually is. Diagnostic, for a store audit.

    Returns counts rather than a verdict: whether 73 gaps in 209,184 rows matters depends on
    what is being measured, and that is the caller's judgement.
    """
    idx = pd.DatetimeIndex(index)
    if len(idx) < 2:
        return {"rows": len(idx), "sessions": 0, "within_day_gaps": 0, "gap_minutes": []}
    day = idx.to_series().dt.date.reset_index(drop=True)
    delta = pd.Series(idx).diff()
    same = day.eq(day.shift(1)).fillna(False)
    inday = pd.Series(delta[same.to_numpy()]).dropna()
    step = pd.Timedelta(minutes=float(bar_minutes))
    bad = inday[inday != step]
    return {
        "rows": len(idx),
        "sessions": int(day.nunique()),
        "within_day_gaps": int(len(bad)),
        "gap_minutes": sorted({int(x.total_seconds() // 60) for x in bad})[:20],
    }
