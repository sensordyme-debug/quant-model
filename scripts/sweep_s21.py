#!/usr/bin/env python
"""S-21: price the financing LEAN has never charged, and split it by rate regime.

    python scripts/sweep_s21.py --probe     # the debit-balance state, year by year
    python scripts/sweep_s21.py --report    # read the LEAN cells written by _s21_runs.sh
    python scripts/sweep_s21.py --schedule  # the drag as a function of the price list

The defect (engine source, same method as S-17's slippage finding)
------------------------------------------------------------------
`Common/Brokerages/DefaultBrokerageModel.cs:368` returns `MarginInterestRateModel.Null`,
whose `ApplyMarginInterestRate` is an empty method body, and
`InteractiveBrokersBrokerageModel` does not override it. LEAN charges no interest on a
debit balance and pays none on a credit balance. The shipped champion runs 1.50x gross
against 1.00x of equity - a debit of about half its equity on every invested day - and it
has been borrowing that for free for twenty-one iterations.

Why a probe is needed and the LEAN summary line is not enough
------------------------------------------------------------
`main.py` reports one total at the end of the run. The interesting structure is in the
calendar: the benchmark was ~0.1% for most of 2012-2021 and 4-5% from 2023, so a single
full-period number hides the fact that the correction lands almost entirely on the
out-of-sample half - the half every recent promotion leaned on. `--probe` walks the shipped
signal through the same share-level book S-19 validated against LEAN's own equity curve
(corr 0.99650), records the cash balance every session, and accrues the IBKR schedule on it
year by year. Its full-period total is then a second, independent implementation of the
same arithmetic and must agree with LEAN's to within the book's own tracking error - that
agreement is what makes the LEAN cells believable rather than merely produced.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                          # noqa: E402
import rates as rt                             # noqa: E402
from lean_prices import load_ohlcv             # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
START, END = "2012-01-03", "2026-09-04"
START_EQUITY = 100_000.0
MIN_ORDER_VALUE = 0.01


# --------------------------------------------------------------------------- ledger
def ledger_rows(track: str) -> list[dict]:
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").strip().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("tag", "").startswith(track):
            rows.append(row)
    return rows


def _num(stats: dict, key: str) -> float:
    raw = str(stats.get(key, "")).replace("%", "").replace("$", "").replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return float("nan")


# --------------------------------------------------------------------------- the book
#: S-44: this file used to define its own `commission` - IBKR's **tiered** schedule, 0.0035
#: per share with a $0.35 minimum and a 1% cap - under a docstring that called it "the same
#: model `scripts/sweep_s19.py` uses". It was not: LEAN charges the **fixed** schedule
#: (`InteractiveBrokersFeeModel.cs:150`, 0.005 / $1 / 0.5%), and on the champion's 5,128 fills
#: the tiered form undercharged by $8,916.45, 32.78% of the fee line, on every single fill.
#: The claim is now true by construction rather than by assertion: importing the one function
#: makes `walk` reproduce `sweep_s19.simulate(..., fill="open")` to 9.3e-10 on all 3,689
#: sessions, where the two books used to end $52,442.77 apart. See `scripts/sweep_s44.py`.
from sweep_s19 import commission               # noqa: E402,F401


def commission_tiered_legacy(shares: float, price: float) -> float:
    """The pre-S-44 form, verbatim, so every row written under it stays reproducible.

    IBKR's *tiered* US-equity schedule. It is a real schedule - it is simply not the one the
    engine charges, so a book using it cannot be compared with a LEAN row or with any other
    file on this track.
    """
    per_share = 0.0035 * abs(shares)
    return float(min(max(per_share, 0.35), 0.01 * abs(shares) * price))


def walk(params, start: str = START, end: str = END) -> pd.DataFrame:
    """Run the shipped signal and record equity **and the cash balance** every session.

    Deliberately the S-19 convention (decide on the previous close, fill at the open, size
    off the close the decision saw), because that is the convention the LEAN cells use and
    the one that harness was validated on. Financing is *not* charged inside the walk: the
    point of the probe is to measure the balance the charge would apply to, so that the
    accrual can be decomposed afterwards without re-running anything.
    """
    frames = load_ohlcv(sig.traded_universe(params))
    closes, opens = frames["close"], frames["open"]
    tickers = [t for t in sig.traded_universe(params) if t in closes.columns]
    index = closes.index
    i0 = max(index.searchsorted(pd.Timestamp(start)) + 1, params.history_bars)
    i1 = min(index.searchsorted(pd.Timestamp(end), side="right"), len(index))

    equity, cash = START_EQUITY, START_EQUITY
    positions: dict[str, int] = {}
    equity_curve, state, rows = [START_EQUITY], {}, []

    for i in range(i0, i1):
        window = closes.iloc[max(0, i - params.history_bars):i]
        targets, diag = sig.target_weights(window, equity_curve, params, state)
        state = diag.get("state", {})

        ref = {t: float(closes[t].iloc[i - 1]) for t in tickers
               if pd.notna(closes[t].iloc[i - 1])}
        fill_row = opens.iloc[i]
        for t in tickers:
            p = ref.get(t, 0.0)
            held = int(positions.get(t, 0))
            target = 0 if p <= 0 else int(targets.get(t, 0.0) * equity / p)
            if abs(target - held) * max(p, 0.01) < MIN_ORDER_VALUE * equity:
                continue
            d = target - held
            px = float(fill_row.get(t, np.nan))
            if not np.isfinite(px) or px <= 0:
                continue
            cash -= d * px + commission(d, px)
            positions[t] = held + d

        mark = closes.iloc[i]
        holdings = sum(n * float(mark[t]) for t, n in positions.items()
                       if t in mark.index and pd.notna(mark[t]))
        value = cash + holdings
        rows.append({"date": index[i], "equity": value, "cash": cash,
                     "gross": holdings / value if value else 0.0})
        equity = value
        equity_curve.append(value)

    return pd.DataFrame(rows).set_index("date")


CACHE = REPO / "data" / "rates" / "_s21_book.csv"


def cached_walk() -> pd.DataFrame:
    """The probe's book, computed once. The walk is ~3,700 calls to the shipped signal;
    every schedule below is then a cheap re-accrual on the same cash path, which is the
    whole point of separating the two - the balance is a fact about the strategy, the rate
    charged on it is a fact about the broker."""
    if CACHE.exists():
        return pd.read_csv(CACHE, parse_dates=["date"]).set_index("date")
    book = walk(sig.DEFAULTS)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    book.to_csv(CACHE)
    return book


def probe(spread_shift: float = 0.0, tiers=None) -> pd.DataFrame:
    book = cached_walk()
    saved = rt.DEBIT_TIERS
    if tiers is not None:
        rt.DEBIT_TIERS = tiers
    bm = pd.read_csv(rt.RATE_CSV, parse_dates=["date"]).set_index("date")["rate_pct"]
    bm = bm.reindex(pd.date_range(bm.index[0], max(bm.index[-1], book.index[-1]))).ffill()

    days = book.index.to_series().diff().dt.days.fillna(1).clip(lower=0).astype(int)
    out = []
    for date, row in book.iterrows():
        n = int(days.loc[date])
        rate = float(bm.loc[min(date, bm.index[-1])])
        out.append(rt.accrual(row["cash"], rate, n, spread_shift))
    book = book.copy()
    book["days"] = days
    book["bm"] = [float(bm.loc[min(d, bm.index[-1])]) for d in book.index]
    book["interest"] = out
    book["drag_bps"] = -book["interest"] / book["equity"] * 1e4
    rt.DEBIT_TIERS = saved
    return book


def probe_report(spread_shift: float = 0.0) -> None:
    book = probe(spread_shift)
    print(f"the debit balance the champion actually carries "
          f"({book.index[0].date()}..{book.index[-1].date()}, {len(book):,} sessions)\n")
    invested = book[book["cash"] < 0]
    print(f"  sessions with a debit balance   {len(invested):,} of {len(book):,} "
          f"({len(invested) / len(book):.1%})")
    print(f"  mean gross exposure             {book['gross'].mean():.3f}x")
    print(f"  mean debit / equity (all)       {(-book['cash'] / book['equity']).clip(lower=0).mean():.3f}x")
    print(f"  mean debit / equity (debit days){(-invested['cash'] / invested['equity']).mean():.3f}x")
    print(f"  sessions in credit              {len(book) - len(invested):,}")

    print(f"\n{'year':>6} {'sessions':>9} {'mean BM':>8} {'debit/eq':>9} {'loan rate':>10} "
          f"{'$ interest':>12} {'bps/day':>9} {'CAR pts':>8}")
    for year, g in book.groupby(book.index.year):
        debit = (-g["cash"] / g["equity"]).clip(lower=0).mean()
        loan = np.mean([rt.debit_rate(c, b, spread_shift) for c, b in zip(g["cash"], g["bm"])
                        if c < 0]) if (g["cash"] < 0).any() else 0.0
        drag = g["drag_bps"].mean()
        print(f"{year:>6} {len(g):>9,} {g['bm'].mean():>7.2f}% {debit:>9.3f} {loan:>9.2f}% "
              f"{-g['interest'].sum():>11,.0f} {drag:>9.3f} {drag * 252 / 100:>8.3f}")

    total = -book["interest"].sum()
    print(f"\n  total interest over the sample  ${total:,.0f} "
          f"(paid ${-book.loc[book['interest'] < 0, 'interest'].sum():,.0f}, "
          f"earned ${book.loc[book['interest'] > 0, 'interest'].sum():,.0f})")
    print(f"  mean drag                       {book['drag_bps'].mean():.3f} bps/day "
          f"= {book['drag_bps'].mean() * 252 / 100:.3f} CAR points at constant equity")
    print("\n  NOTE: the CAR-points column is the *simple* drag on an unchanged book. The LEAN\n"
          "  cells charge it to the cash book, so it compounds against the equity the next\n"
          "  day is sized from; --report is the number to quote.")


# --------------------------------------------------------------------------- report
def report() -> None:
    rows = ledger_rows("S-21")
    rows = [r for r in rows if "smoke" not in r["tag"]]
    if not rows:
        print("no S-21 rows in the ledger; run bash scripts/_s21_runs.sh first")
        return

    print(f"{'cell':<52} {'orders':>7} {'CAR':>8} {'Sharpe':>7} {'MaxDD':>7} "
          f"{'std':>6} {'PSR':>7} {'fees':>10}")
    control = None
    for r in rows:
        s = r["stats"]
        label = r["tag"][len("S-21 "):] if r["tag"].startswith("S-21 ") else r["tag"]
        print(f"{label:<52} {s.get('Total Orders', ''):>7} "
              f"{_num(s, 'Compounding Annual Return'):>7.3f}% {_num(s, 'Sharpe Ratio'):>7.3f} "
              f"{_num(s, 'Drawdown'):>6.1f}% {_num(s, 'Annual Standard Deviation'):>6.3f} "
              f"{_num(s, 'Probabilistic Sharpe Ratio'):>6.1f}% ${_num(s, 'Total Fees'):>9,.0f}")
        if label.startswith("control:"):
            control = r

    if control is None:
        return
    base = _num(control["stats"], "Compounding Annual Return")
    base_std = _num(control["stats"], "Annual Standard Deviation")
    print(f"\ncost of financing, against the control's {base:.3f}%:")
    for r in rows:
        if r is control:
            continue
        s = r["stats"]
        car = _num(s, "Compounding Annual Return")
        label = r["tag"][len("S-21 "):]
        ref = base
        # A cell that moved the window or the budget has its own baseline in the ledger;
        # those are printed by --frontier / --halves rather than differenced against the
        # full-period control, which would be comparing two different books (S-18's rule).
        if "IS 2012" in label or "OOS 2020" in label or "margin_budget" in label or "2 bp" in label:
            continue
        print(f"  {label:<52} {car:>7.3f}%  {car - ref:>+7.3f} CAR")

    # S-20 made this column compulsory on this sleeve. It is reported here for completeness
    # and it is NOT the decisive read: financing does not change the book's risk, it removes
    # money from it, so the correct comparison is like-for-like, not vol-matched.
    print("\nvol-matched (reported because S-20 requires the column; see the note):")
    for r in rows:
        if r is control or "IS 2012" in r["tag"] or "OOS 2020" in r["tag"]:
            continue
        s = r["stats"]
        std, car = _num(s, "Annual Standard Deviation"), _num(s, "Compounding Annual Return")
        print(f"  {r['tag'][len('S-21 '):]:<52} {std:>6.3f} {car:>7.3f}% "
              f"{base * std / base_std:>8.3f}% {car - base * std / base_std:>+7.3f}")
    print("  note: the two books hold the same positions on the same days, so std barely\n"
          "  moves and the vol-matched column adds nothing here. Charging a cost is not a\n"
          "  size decision - which is exactly why S-21 is a measurement and not a candidate.")


ZERO_TIERS = ((float("inf"), 0.0),)


def schedule_table() -> None:
    """The drag as a function of the price list, so the answer does not rest on one broker.

    The `benchmark only` row is the one that is arithmetic rather than a price list: no
    broker can lend below its own cost of funds, so that row is the irreducible part of the
    correction. It is NOT the same as the LEAN `floor` cell, which shifts every tier down by
    1.50pp and therefore charges the tranches above $100k *below* the benchmark - a lower
    bound on the lower bound, and labelled as such in the write-up.
    """
    cells = [("benchmark only (tier spreads = 0)", 0.0, ZERO_TIERS),
             ("IBKR tiers shifted -1.50pp (the LEAN floor cell)", -1.50, None),
             ("IBKR tiers shifted -1.00pp", -1.00, None),
             ("IBKR tiers shifted -0.50pp", -0.50, None),
             ("IBKR Pro published tiers (the primary)", 0.0, None),
             ("IBKR tiers shifted +0.50pp", 0.50, None)]
    print("drag as a function of the schedule (probe arithmetic, simple CAR points,\n"
          "same cash path in every row - only the rate charged on it moves):\n")
    print(f"  {'schedule':<48} {'$ interest':>12} {'bps/day':>9} {'CAR pts':>9}")
    for label, shift, tiers in cells:
        book = probe(shift, tiers)
        drag = book["drag_bps"].mean()
        print(f"  {label:<48} {-book['interest'].sum():>11,.0f} {drag:>9.3f} "
              f"{drag * 252 / 100:>9.3f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--schedule", action="store_true")
    ap.add_argument("--spread-shift", type=float, default=0.0)
    args = ap.parse_args()

    if args.probe:
        probe_report(args.spread_shift)
    if args.schedule:
        schedule_table()
    if args.report:
        report()
    if not (args.probe or args.report or args.schedule):
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
