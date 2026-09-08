#!/usr/bin/env python
"""Read LEAN's on-disk daily bars back into a pandas frame of adjusted closes.

The point is to be able to reason about a signal outside the engine - sweeps, plots,
reconciliation against what the IBKR runner sees - while consuming exactly the bytes
LEAN consumes. The adjustment applied here mirrors LEAN's DataNormalizationMode.ADJUSTED:
multiply the raw close by the price factor whose row is the first with date >= the bar
date (see the factor-file contract documented in scripts/fetch_data.py).

    from lean_prices import load_closes
    px = load_closes(["SPY", "QQQ"], start="2012-01-01")
"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
LEAN_DATA = Path(os.environ.get("LEAN_DATA", REPO.parent / "Lean" / "Data"))
EQUITY = LEAN_DATA / "equity" / "usa"
SCALE = 10000


def _raw_closes(ticker: str) -> pd.Series:
    path = EQUITY / "daily" / f"{ticker.lower()}.zip"
    if not path.exists():
        raise FileNotFoundError(f"no LEAN daily file for {ticker}: {path}")
    with zipfile.ZipFile(path) as zf:
        text = zf.read(zf.namelist()[0]).decode()
    rows = [line.split(",") for line in text.strip().splitlines()]
    index = pd.to_datetime([r[0][:8] for r in rows], format="%Y%m%d")
    return pd.Series([float(r[4]) / SCALE for r in rows], index=index, name=ticker)


def _price_factors(ticker: str, index: pd.DatetimeIndex) -> pd.Series:
    path = EQUITY / "factor_files" / f"{ticker.lower()}.csv"
    if not path.exists():
        return pd.Series(1.0, index=index)
    rows = [line.split(",") for line in path.read_text().strip().splitlines()]
    dates = pd.to_datetime([r[0] for r in rows], format="%Y%m%d")
    factors = pd.Series([float(r[1]) for r in rows], index=dates).sort_index()
    # A row applies to every bar on or before its date, hence backfill onto the bar dates.
    return factors.reindex(factors.index.union(index)).bfill().reindex(index).fillna(1.0)


def load_closes(tickers, start=None, end=None) -> pd.DataFrame:
    """Adjusted closes as a date-by-ticker DataFrame; missing tickers raise."""
    series = {}
    for ticker in tickers:
        closes = _raw_closes(ticker)
        series[ticker] = closes * _price_factors(ticker, closes.index)
    frame = pd.DataFrame(series).sort_index()
    return frame.loc[start:end]


if __name__ == "__main__":
    import sys

    frame = load_closes(sys.argv[1:] or ["SPY", "QQQ", "TQQQ"], start="2012-01-01")
    print(frame.tail())
    print(f"\n{frame.shape[0]} bars, {frame.index[0].date()} .. {frame.index[-1].date()}")
