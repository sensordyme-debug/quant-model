#!/usr/bin/env python
"""USD benchmark rate history, and IBKR's tiered margin/credit schedule on top of it.

S-21. LEAN charges **no** financing: `DefaultBrokerageModel.GetMarginInterestRateModel`
returns `MarginInterestRateModel.Null` (a no-op `ApplyMarginInterestRate`) and
`InteractiveBrokersBrokerageModel` does not override it, so a backtested book that runs
1.50x gross borrows half its equity for free and a book sitting in cash earns nothing on
it. Both sides are real money at a broker, and the sign of the correction depends on the
regime: rates were ~0.1% for most of 2012-2021 and 4-5% from 2023.

    python scripts/rates.py              # refresh data/rates/usd_benchmark.csv from FRED
    python scripts/rates.py --show       # print the annual means actually stored

The benchmark
-------------
IBKR's USD "BM" is the effective federal funds rate, which is FRED series **DFF** (daily,
1954-, published for every calendar day - weekends carry the previous business day's rate,
which is exactly the convention an actual/360 accrual needs). No API key.

The schedule (IBKR Pro, USD, published rates as of 2026)
--------------------------------------------------------
Margin loan, charged on the debit balance, blended per tranche:

    tranche                          spread over BM
    0            -  100,000          +1.5%
    100,000      -  1,000,000        +1.0%
    1,000,000    - 50,000,000        +0.75%
    above                            +0.50%

Credit interest, paid on the *settled cash* balance above $10,000:

    BM - 0.5%, floored at zero.

Both are accrued actual/360 on calendar days, so a weekend costs three days of interest.
The tier spreads are constants here rather than a fitted input; `--spread-shift` on the
sweep moves all of them together so the answer can be read as a function of the schedule
instead of resting on one broker's price list.
"""
from __future__ import annotations

import argparse
import io
import urllib.request
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RATE_CSV = REPO / "data" / "rates" / "usd_benchmark.csv"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF"

#: (upper bound of the tranche in USD, spread over the benchmark in percentage points)
DEBIT_TIERS = ((100_000, 1.50), (1_000_000, 1.00), (50_000_000, 0.75), (float("inf"), 0.50))
CREDIT_SPREAD = 0.50        # paid at BM - this
CREDIT_MIN = 10_000.0       # no credit interest on the first $10k
DAY_COUNT = 360.0


def fetch(out: Path = RATE_CSV) -> pd.DataFrame:
    """Download DFF and write `date,rate_pct` (calendar-daily, forward-filled)."""
    raw = urllib.request.urlopen(FRED_URL, timeout=60).read().decode()
    df = pd.read_csv(io.StringIO(raw))
    df.columns = ["date", "rate_pct"]
    df["date"] = pd.to_datetime(df["date"])
    df["rate_pct"] = pd.to_numeric(df["rate_pct"], errors="coerce")
    df = df.dropna().sort_values("date")
    # FRED publishes DFF for every calendar day already, but reindex defensively so a
    # missing holiday can never make the algorithm silently skip an accrual.
    full = pd.DataFrame({"date": pd.date_range(df["date"].iloc[0], df["date"].iloc[-1])})
    df = full.merge(df, on="date", how="left").ffill()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, date_format="%Y-%m-%d")
    return df


def load(path: Path = RATE_CSV) -> dict:
    """`{date string 'YYYY-MM-DD' -> benchmark rate in percent}`.

    A plain dict rather than a frame because the consumer is `main.py` inside LEAN, which
    looks one date up per session and must not carry pandas state across the algorithm's
    own warm-up.
    """
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    return dict(zip(df["date"].astype(str), df["rate_pct"].astype(float)))


def debit_rate(balance: float, benchmark_pct: float, spread_shift: float = 0.0) -> float:
    """Blended annual rate (percent) charged on a debit balance of `balance` dollars.

    Blended per tranche, which is what IBKR actually does - a $600k loan pays +1.5% on its
    first $100k and +1.0% on the rest, not +1.0% on all of it.
    """
    balance = abs(balance)
    if balance <= 0:
        return 0.0
    charged, lower, cost = 0.0, 0.0, 0.0
    for upper, spread in DEBIT_TIERS:
        slice_ = max(0.0, min(balance, upper) - lower)
        if slice_ <= 0:
            break
        cost += slice_ * (benchmark_pct + spread + spread_shift)
        charged += slice_
        lower = upper
    return cost / charged if charged else 0.0


def credit_rate(benchmark_pct: float, spread_shift: float = 0.0) -> float:
    """Annual rate (percent) paid on the qualifying part of a credit balance."""
    return max(0.0, benchmark_pct - CREDIT_SPREAD - spread_shift)


def accrual(cash: float, benchmark_pct: float, days: int, spread_shift: float = 0.0) -> float:
    """Signed interest in dollars for `days` calendar days on a settled balance of `cash`.

    Negative is a charge. Cash below zero is a margin loan; cash above `CREDIT_MIN` earns
    on the excess only.
    """
    if days <= 0:
        return 0.0
    frac = days / DAY_COUNT
    if cash < 0:
        return -abs(cash) * debit_rate(cash, benchmark_pct, spread_shift) / 100.0 * frac
    earning = max(0.0, cash - CREDIT_MIN)
    return earning * credit_rate(benchmark_pct, spread_shift) / 100.0 * frac


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true", help="print annual means, do not fetch")
    args = ap.parse_args()

    if args.show:
        df = pd.read_csv(RATE_CSV, parse_dates=["date"])
    else:
        df = fetch()
        print(f"wrote {RATE_CSV}: {len(df):,} calendar days "
              f"{df['date'].iloc[0].date()}..{df['date'].iloc[-1].date()}")
    annual = df[df["date"] >= "2012-01-01"].groupby(df["date"].dt.year)["rate_pct"].mean()
    print("\nbenchmark (effective fed funds), annual mean %:")
    for year, rate in annual.items():
        loan = debit_rate(500_000, rate)
        print(f"  {year}  BM {rate:5.2f}   loan on $500k {loan:5.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
