#!/usr/bin/env python
"""S-29: option-implied volatility levels for the daily sleeve's crisis switch.

    python scripts/regime_data.py                 # fetch/refresh data/regime/vix.csv
    python scripts/regime_data.py --report        # describe what is on disk

Why this exists
---------------
`signals.risk_on` steps the daily champion aside when SPY's trailing 20-session *realized*
volatility exceeds 1.5x its own one-year median. That is a backward-looking estimate of a
forward-looking quantity, and there is a market that quotes the forward-looking one directly.
S-29 prices the swap through the `S1_REGIME_SERIES` hook, which needs a plain one-column CSV
of levels; this module writes it.

Two series, deliberately independent of each other:

* **`vix.csv`** - CBOE VIX from Yahoo (`^VIX`), the 30-day option-implied volatility of the
  S&P 500, back to 2005. Free, unrevised, and it is *the* implied analogue of the realized
  number the switch uses today. Yahoo publishes the index level, not a tradable price, which
  is all the gate needs: `risk_on` compares the level to a multiple of its own trailing
  median, so the units cancel and no adjustment convention enters.
* **`spy_iv.csv`** - SPY's own 1-month at-the-money implied volatility, re-exported from the
  Theta Data store O-1 built (`data/options/iv_regime.csv`, 2017-2026). A second, shorter
  and completely separate implied series, so a result on VIX can be checked against an
  instrument that is not an index calculation.

Causality. Row `d` of either file is the level as of the close of session `d`, which is the
same information set the shipped realized estimate has at that moment; `regime_level` indexes
it at the last date of the decision window, so a decision made on the closes through `d-1`
reads the implied level of `d-1`. Nothing here can see forward.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "data" / "regime"
VIX_CSV = OUT_DIR / "vix.csv"
SPY_IV_CSV = OUT_DIR / "spy_iv.csv"
IV_REGIME_CSV = REPO / "data" / "options" / "iv_regime.csv"

#: Far enough before the book's 2012 start that the 300-bar decision window and the
#: 252-session median are always inside the file rather than on `regime_level`'s fallback.
VIX_START = "2005-01-01"


def fetch_vix(start: str = VIX_START) -> pd.Series:
    """Daily VIX closes from Yahoo, indexed by normalized date."""
    import yfinance as yf

    raw = yf.download("^VIX", start=start, progress=False, auto_adjust=False)
    if raw is None or len(raw) == 0:
        raise RuntimeError("yfinance returned no rows for ^VIX")
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):            # single-ticker column layout
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index).normalize()
    return close.dropna().sort_index().rename("vix")


def export_spy_iv() -> pd.Series | None:
    """SPY 1-month ATM implied vol out of the O-1 Theta store, if it is on disk."""
    if not IV_REGIME_CSV.exists():
        return None
    frame = pd.read_csv(IV_REGIME_CSV, index_col=0)
    frame.index = pd.to_datetime(frame.index).normalize()
    col = "iv_atm_1m" if "iv_atm_1m" in frame.columns else "iv_atm_1w"
    return frame[col].dropna().sort_index().rename("spy_iv")


def write(series: pd.Series, path: Path) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    series.to_frame().to_csv(path, index_label="date")


def load(path: Path = VIX_CSV) -> pd.Series:
    """Read one of the level files back as a dated Series."""
    frame = pd.read_csv(path, index_col=0)
    frame.index = pd.to_datetime(frame.index).normalize()
    return frame.iloc[:, 0].sort_index()


def describe(series: pd.Series, name: str) -> None:
    print(f"  {name:<10}{len(series):>7,} rows   {series.index[0].date()} .. "
          f"{series.index[-1].date()}   min {series.min():.4f}  median "
          f"{series.median():.4f}  max {series.max():.4f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true", help="only describe what is on disk")
    ap.add_argument("--start", default=VIX_START)
    args = ap.parse_args()

    if not args.report:
        vix = fetch_vix(args.start)
        write(vix, VIX_CSV)
        print(f"wrote {VIX_CSV.relative_to(REPO)}")
        spy_iv = export_spy_iv()
        if spy_iv is not None:
            write(spy_iv, SPY_IV_CSV)
            print(f"wrote {SPY_IV_CSV.relative_to(REPO)}")
        else:
            print(f"skipped {SPY_IV_CSV.name}: {IV_REGIME_CSV.relative_to(REPO)} not on disk")

    print("\non disk:")
    for path, name in ((VIX_CSV, "vix"), (SPY_IV_CSV, "spy_iv")):
        if path.exists():
            describe(load(path), name)
        else:
            print(f"  {name:<10}missing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
