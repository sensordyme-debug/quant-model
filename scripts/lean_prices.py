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


def _raw_bars(ticker: str) -> pd.DataFrame:
    """Raw OHLC and share volume for one ticker, indexed by bar date.

    The LEAN daily line is `date,open,high,low,close,volume` with prices in deci-cents.
    `close` and `volume` are what `load_frames` has always returned; the other three legs
    are carried too so a caller that needs a true range or a fill at the next open (F-3)
    does not have to re-open the zip.
    """
    path = EQUITY / "daily" / f"{ticker.lower()}.zip"
    if not path.exists():
        raise FileNotFoundError(f"no LEAN daily file for {ticker}: {path}")
    with zipfile.ZipFile(path) as zf:
        text = zf.read(zf.namelist()[0]).decode()
    rows = [line.split(",") for line in text.strip().splitlines()]
    index = pd.to_datetime([r[0][:8] for r in rows], format="%Y%m%d")
    return pd.DataFrame({"open": [float(r[1]) / SCALE for r in rows],
                         "high": [float(r[2]) / SCALE for r in rows],
                         "low": [float(r[3]) / SCALE for r in rows],
                         "close": [float(r[4]) / SCALE for r in rows],
                         "volume": [float(r[5]) for r in rows]}, index=index)


def _raw_closes(ticker: str) -> pd.Series:
    return _raw_bars(ticker)["close"].rename(ticker)


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
    return load_frames(tickers, start, end)[0]


def load_frames(tickers, start=None, end=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`(adjusted closes, share volume)`, both date-by-ticker on the same index.

    Volume is returned raw, exactly as written to the daily file. It needs no adjustment:
    `fetch_data.py` writes split factor 1 for every symbol and Yahoo's volume is already
    split-adjusted like its prices, so `close * volume` is the same dollar figure either
    way. The D-3 universe module consumes this pair.
    """
    closes, volumes = {}, {}
    for ticker in tickers:
        bars = _raw_bars(ticker)
        closes[ticker] = bars["close"] * _price_factors(ticker, bars.index)
        volumes[ticker] = bars["volume"]
    px = pd.DataFrame(closes).sort_index()
    vol = pd.DataFrame(volumes).sort_index().reindex(px.index)
    return px.loc[start:end], vol.loc[start:end]


def load_ohlcv(tickers, start=None, end=None) -> dict[str, pd.DataFrame]:
    """`{field: date-by-ticker frame}` for open/high/low/close/volume.

    Every price leg carries the same dividend adjustment `load_frames` applies to the
    close, so ratios within a bar (a true range against its close) and across bars (an
    open-to-open return) are both consistent. Volume is raw, as in `load_frames`.
    """
    fields = ["open", "high", "low", "close", "volume"]
    out: dict[str, dict[str, pd.Series]] = {f: {} for f in fields}
    for ticker in tickers:
        bars = _raw_bars(ticker)
        factor = _price_factors(ticker, bars.index)
        for f in fields:
            out[f][ticker] = bars[f] * (1.0 if f == "volume" else factor)
    frames = {f: pd.DataFrame(out[f]).sort_index() for f in fields}
    index = frames["close"].index
    return {f: frames[f].reindex(index).loc[start:end] for f in fields}


if __name__ == "__main__":
    import sys

    frame = load_closes(sys.argv[1:] or ["SPY", "QQQ", "TQQQ"], start="2012-01-01")
    print(frame.tail())
    print(f"\n{frame.shape[0]} bars, {frame.index[0].date()} .. {frame.index[-1].date()}")
