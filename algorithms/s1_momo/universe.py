"""D-3: point-in-time universe membership from trailing dollar volume.

Why this exists
---------------
S-7 measured a momentum strategy on the 50 megacaps that `scripts/fetch_data.py`
downloaded, and it printed CAR 43.9% / Sharpe 1.19. The number is not real: that list is
the megacap list *as of 2026*, so ranking it back to 2012 already knows which fifty
companies were going to win. The control run in `--mode s7bias` settles it - simply
holding that same list equal-weighted, with no skill at all, compounds at 22.8% against
SPY's 15.0%.

The fix is to decide membership from information that existed on the rebalance date.
Ranking by trailing dollar volume does that with no new data source: `close * volume` is
in every LEAN daily bar already on disk, and liquidity is also the property the mandate
actually cares about ("highly liquid", AGENTS.md) rather than a proxy for it.

    members, diag = select(prices, volumes, candidates, size)

`prices`  : date-by-ticker adjusted closes (same frame the signal ranks).
`volumes` : date-by-ticker share volume, same index and columns. Missing columns are
            simply not selectable.
returns   : (list of tickers, ordered most liquid first; diagnostics dict).

What this fixes, and what it does not
-------------------------------------
Fixed: *timing*. A name enters the sleeve only once it has traded enough for long enough
as of that date, and leaves when it stops being liquid, so the 2012 ranking cannot see
2026's winners.

**Not fixed: the file itself is a survivor list.** `fetch_data.py` downloaded 69 tickers
that exist in 2026, so a name that was liquid in 2012 and has since been acquired or
delisted (think DELL, EMC, YHOO, TWX, MON) is not on disk and can never be selected. The
honest fix is delisted-inclusive history, which is a paid data set and a human decision.
The size of what remains is measurable rather than assumed - `scripts/sweep_s1.py
--mode d3` reports how much the selected membership actually churns over the sample. If
membership barely moves, this module has relabeled the bias rather than removed it, and
any result on the single-name sleeve is still an upper bound.

Adjusted vs raw prices
----------------------
Callers pass dividend-adjusted closes (LEAN `DataNormalizationMode.ADJUSTED`), so old
dollar-volume values are deflated by the cumulative dividend factor. Splits do not matter
- `fetch_data.py` writes split factor 1 and Yahoo's volume is split-adjusted like its
prices, so `close * volume` is split-invariant. The dividend deflation is a level effect
of a few percent per decade that varies by yield; it can shuffle names that are already
adjacent in liquidity, and it cannot promote a small name over a large one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

#: trailing sessions of dollar volume that decide membership
DV_WINDOW = 60

#: sessions of price history a name must have before it can be selected. One year, which
#: is also more than the longest momentum lookback (120), so a selected name always has a
#: computable score. This is the rule that keeps a fresh IPO out of the sleeve.
MIN_HISTORY = 252


def dollar_volume(prices: pd.DataFrame, volumes: pd.DataFrame, window: int = DV_WINDOW) -> pd.Series:
    """Median daily dollar volume over the trailing `window` sessions, per ticker.

    Median, not mean: a single earnings day or index-rebalance print can be ten times a
    name's normal turnover, and a mean lets one such day buy a seat in the sleeve for
    three months. The median asks whether the name is *habitually* liquid, which is the
    property that makes a position exitable.
    """
    cols = [c for c in prices.columns if c in volumes.columns]
    if not cols or len(prices) == 0:
        return pd.Series(dtype=float)
    px = prices[cols].iloc[-window:]
    vol = volumes[cols].reindex(px.index)
    dv = (px * vol).replace([np.inf, -np.inf], np.nan)
    # Require at least half the window to have traded, so a name that was halted or is
    # newly listed does not qualify on three good days.
    enough = dv.notna().sum() >= max(5, window // 2)
    return dv.median().where(enough)


def select(prices: pd.DataFrame, volumes: pd.DataFrame, candidates, size: int,
           window: int = DV_WINDOW, min_history: int = MIN_HISTORY) -> tuple[list, dict]:
    """The `size` most liquid candidates as of the last bar in `prices`.

    A candidate qualifies when it has `min_history` consecutive priced sessions ending at
    the last bar and a computable trailing dollar volume. Ties break on ticker so a run is
    reproducible.
    """
    diag = {"universe_window": window, "universe_size": size}
    usable = [t for t in candidates if t in prices.columns]
    if not usable or size <= 0:
        diag["universe_reason"] = "no candidates on disk" if not usable else "size<=0"
        return list(usable), diag

    # Vectorized on purpose: this runs once per ticker per rebalance day, so a per-column
    # `.iloc` loop here costs minutes across a 14-year sweep.
    tail = prices[usable].iloc[-min_history:]
    complete = tail.notna().all() if len(prices) >= min_history else pd.Series(False, index=usable)
    history_ok = [t for t in usable if bool(complete[t])]
    diag["n_candidates"] = len(usable)
    diag["n_history_ok"] = len(history_ok)
    if not history_ok:
        diag["universe_reason"] = f"no candidate has {min_history} bars"
        return [], diag

    dv = dollar_volume(prices[history_ok], volumes, window).dropna()
    if dv.empty:
        diag["universe_reason"] = "no computable dollar volume"
        return [], diag

    ordered = sorted(dv.index, key=lambda t: (-float(dv[t]), t))
    members = ordered[:size]
    diag["universe_reason"] = "dollar-volume rank"
    diag["universe_members"] = list(members)
    diag["universe_min_dv"] = round(float(dv[members[-1]]) / 1e6, 1) if members else None
    return members, diag


def membership_history(prices: pd.DataFrame, volumes: pd.DataFrame, candidates, size: int,
                       start=None, window: int = DV_WINDOW,
                       min_history: int = MIN_HISTORY) -> pd.DataFrame:
    """Boolean date-by-ticker membership, one row per session from `start`.

    Only used by the sweeps and the journal: this is how the churn of the selected sleeve
    gets measured, which is the evidence for whether D-3 removed the S-7 bias or merely
    renamed it.
    """
    index = prices.index
    i0 = 0 if start is None else int(index.searchsorted(pd.Timestamp(start)))
    depth = max(min_history, window)          # select never looks further back than this
    rows, dates = [], []
    for i in range(i0, len(index)):
        lo = max(0, i + 1 - depth)
        members, _ = select(prices.iloc[lo:i + 1], volumes.iloc[lo:i + 1], candidates, size,
                            window, min_history)
        rows.append({t: True for t in members})
        dates.append(index[i])
    frame = pd.DataFrame(rows, index=dates).reindex(
        columns=[c for c in candidates if c in prices.columns])
    return frame.notna() & frame.fillna(False).astype(bool)
