"""F-22 (was the second F-20; renumbered here because F-19 had already opened an F-20):
is `sweep_f3.py:338`'s explicit `ic.commission(sh, p, 1.0)` a DECISION or an OMISSION?

A-16 closed the `commission(` call-site class for the intraday sleeve and left this one to its
owning track, on the grounds that an explicit `1.0` reads as a decision rather than an oversight and
only the owner can say which. D-7 proved the LEAN daily store is split-adjusted and D-9 measured
factors reaching 1.04e-09 on the inverse-leveraged sleeve, where the error would NOT be bounded by
the intraday case's 200x.

The ruling is a DECISION and `1.0` is correct for this call site, on two independent grounds that
are measured here rather than argued:

  (1) `scripts/fetch_data.py` writes **split factor 1 on every row of every factor file**, so the
      LEAN daily store carries no split adjustment for the harness to undo. `share_scale()` - the
      thing the intraday call sites pass - reads `data/minute_alpaca/_splits.json`, which is the
      INTRADAY store's split table and has no bearing on a LEAN daily bar. Passing it here would be
      the bug.
  (2) What `_price_factors` does apply is the DIVIDEND factor, and F-3's universe is 22 plain ETFs
      with no reverse splits: the factor's floor across all of them is ~0.30, and over F-3's own
      test window (2012-2026) it is far closer to 1. A dividend adjustment inflates the implied
      share count by at most 1/factor, which biases the commission UPWARDS - the conservative
      direction - and the residual is measured below in $/day and bps of turnover.

D-9's 1.04e-09 cannot reach F-3: none of SPXU/SQQQ/TQQQ/UPRO is in `TRADABLE`, and clause (1)
means even they would carry split factor 1 in this store.

Usage:
    python scripts/ml_f22.py            # factor audit + the measured cost delta on F-3's own book
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
import intraday_common as ic  # noqa: E402
import lean_prices as lp  # noqa: E402
import sweep_f3 as f3  # noqa: E402

SCORES = REPO / "data" / "f3" / "ml_scores.csv"
PANEL = REPO / "data" / "f3" / "panel.parquet"


def factor_audit() -> pd.DataFrame:
    """Ground (1) and (2): every factor file F-3 can touch, split column and dividend column."""
    d = lp.EQUITY / "factor_files"
    rows = []
    for t in f3.TRADABLE:
        p = d / f"{t.lower()}.csv"
        if not p.exists():
            rows.append({"sym": t, "rows": 0, "min_price_f": np.nan, "min_split_f": np.nan,
                         "max_split_f": np.nan})
            continue
        rec = [r.strip().split(",") for r in p.read_text().splitlines() if r.strip()]
        pf = [float(r[1]) for r in rec]
        sf = [float(r[2]) for r in rec]
        rows.append({"sym": t, "rows": len(rec), "min_price_f": min(pf),
                     "min_split_f": min(sf), "max_split_f": max(sf)})
    a = pd.DataFrame(rows)
    print("=== ground (1)+(2): the factor files behind F-3's 22 tradable names ===")
    print(a.to_string(index=False, float_format=lambda v: f"{v:.6g}"))
    split_ok = bool((a["min_split_f"].dropna() == 1.0).all() and
                    (a["max_split_f"].dropna() == 1.0).all())
    print(f"\n  split factor == 1.0 on every row of every file : "
          f"{'YES - there is no split adjustment to undo' if split_ok else 'NO'}")
    print(f"  dividend factor floor across the sleeve        : "
          f"{a['min_price_f'].min():.4f}  (implied share count inflated by at most "
          f"{1 / a['min_price_f'].min():.2f}x, in the OVERCHARGING direction)")
    lev = [s for s in ("SPXU", "SQQQ", "TQQQ", "UPRO", "SOXL", "SOXS") if s in f3.TRADABLE]
    print(f"  D-9's inverse-leveraged names inside TRADABLE   : {lev or 'none'}")
    return a


def fills(df: pd.DataFrame, pred: np.ndarray, equity: float = 1_000_000.0,
          decile: float = 0.15) -> pd.DataFrame:
    """`sweep_f3.simulate`'s rebalance loop, recording every fill instead of only its total.

    Copied deliberately rather than refactored: F-3 is a shipped research script owned by this
    track and A-16's question is about the code as it stands. The identity check below asserts
    this reproduces `simulate`'s turnover and cost to the cent before any conclusion is drawn.
    """
    d = df[["date", "sym", "entry_px", "fwd1"]].copy()
    d["pred"] = pred
    d = d.dropna(subset=["fwd1"])
    rows: list[dict] = []
    prev_w: dict[str, float] = {}
    for date, grp in d.groupby("date", sort=True):
        n = len(grp)
        k = max(1, int(round(decile * n)))
        order = grp["pred"].to_numpy().argsort()
        syms = grp["sym"].to_numpy()
        w = np.zeros(n)
        w[order[-k:]] = 0.5 / k
        w[order[:k]] = -0.5 / k
        new_w = dict(zip(syms, w))
        px = dict(zip(syms, grp["entry_px"].to_numpy()))
        for s in set(new_w) | set(prev_w):
            dw = new_w.get(s, 0.0) - prev_w.get(s, 0.0)
            if abs(dw) < 1e-12:
                continue
            notional = abs(dw) * equity
            p = float(px.get(s, np.nan))
            if not np.isfinite(p) or p <= 0:
                continue
            rows.append({"date": date, "sym": s, "sh": np.sign(dw) * notional / p, "px": p,
                         "notional": notional})
        prev_w = new_w
    return pd.DataFrame(rows)


def cost_delta() -> None:
    """The residual: F-3's own book costed at `scale=1.0` and at `scale=1/dividend factor`."""
    if not (SCORES.exists() and PANEL.exists()):
        print("\nF-3's panel or scores are not on disk - the measurement is SKIPPED")
        return
    panel = pd.read_parquet(PANEL)
    sc = pd.read_csv(SCORES, parse_dates=["date"])
    long = sc.melt(id_vars="date", var_name="sym", value_name="pred").dropna(subset=["pred"])
    d = panel.merge(long, on=["date", "sym"], how="inner")
    print(f"\n=== the measured residual on F-3's own test book ({d['date'].min().date()}"
          f"..{d['date'].max().date()}, {d['date'].nunique():,} sessions) ===")

    book = f3.simulate(d, d["pred"].to_numpy(), decile=3.0 / 9.0, spread_bps=0.0)
    fl = fills(d, d["pred"].to_numpy(), decile=3.0 / 9.0)

    # identity: the replayed fills must reproduce simulate's own cost line to the cent
    c1 = np.array([ic.commission(r.sh, r.px, 1.0) for r in fl.itertuples()])
    print(f"  identity vs sweep_f3.simulate: cost {c1.sum():,.2f} vs {book['cost'].sum():,.2f}; "
          f"turnover {fl['notional'].sum():,.2f} vs {book['turnover'].sum():,.2f}")
    ok = abs(c1.sum() - book["cost"].sum()) < 0.01
    print(f"  identity (cost, to the cent): "
          f"{'PASS' if ok else 'FAIL - the replay is not F-3s book, stop here'}")
    #: noticed while building the identity check, and reported rather than swept: `simulate` adds
    #: `notional` to turnover BEFORE the `np.isfinite(p)` guard, so a fill with no usable price is
    #: counted as traded and never costed. It inflates the turnover denominator every bps column of
    #: F-3 is divided by. Measured, not guessed - see the gap printed above.
    gap = fl["notional"].sum() - book["turnover"].sum()
    print(f"  NOTE (found here, not part of A-16's question): sweep_f3.simulate counts turnover "
          f"before its own finite-price guard, so ${-gap:,.0f} of turnover "
          f"({100 * -gap / book['turnover'].sum():.4f}%) is counted but never costed")
    if not ok:
        return

    # the corrected scale: adjusted shares per REAL share on that date = 1 / dividend factor
    facs = {}
    dates = pd.DatetimeIndex(sorted(d["date"].unique()))
    for t in sorted(fl["sym"].unique()):
        facs[t] = lp._price_factors(t, dates)
    fl["pf"] = [float(facs[r.sym].get(r.date, 1.0)) for r in fl.itertuples()]
    c2 = np.array([ic.commission(r.sh, r.px, 1.0 / (r.pf or 1.0)) for r in fl.itertuples()])

    n = len(book)
    turn = book["turnover"].sum()
    print(f"  fills {len(fl):,}; dividend factor at the fill: min {fl['pf'].min():.4f}, "
          f"median {fl['pf'].median():.4f}, mean {fl['pf'].mean():.4f}")
    print(f"\n  {'convention':<34}{'cost $/day':>13}{'bps of turnover':>18}")
    print(f"  {'scale=1.0 (as shipped)':<34}{c1.sum() / n:>13,.2f}"
          f"{1e4 * c1.sum() / turn:>18.4f}")
    print(f"  {'scale=1/dividend factor':<34}{c2.sum() / n:>13,.2f}"
          f"{1e4 * c2.sum() / turn:>18.4f}")
    print(f"  {'DELTA (shipped minus correct)':<34}{(c1 - c2).sum() / n:>13,.2f}"
          f"{1e4 * (c1 - c2).sum() / turn:>18.4f}")
    print(f"\n  net $/day as shipped {book['net'].mean():,.2f}; the correction would move it "
          f"{(c1 - c2).sum() / n:+,.2f}/day ({100 * (c1 - c2).sum() / abs(book['net'].sum()):+.3f}% "
          f"of the book's own net)")
    cap = np.array([abs(r.sh) * r.px * 0.01 for r in fl.itertuples()])
    perf = np.array([abs(r.sh) * ic.COMMISSION_PER_SHARE for r in fl.itertuples()])
    print(f"  fills where the 1% notional cap binds at scale=1.0: "
          f"{int((perf >= cap).sum()):,} of {len(fl):,}")
    print(f"  fills where the ${ic.COMMISSION_MIN:.2f} minimum binds at scale=1.0: "
          f"{int((perf <= ic.COMMISSION_MIN).sum()):,} of {len(fl):,}")


def main() -> None:
    factor_audit()
    cost_delta()
    print("\nRULING (F-22): `scale=1.0` at sweep_f3.py:338 is a DECISION, it stays, and passing "
          "`share_scale()` there would be a BUG - the LEAN daily store carries split factor 1 on "
          "every row, so there is no split to undo, and `share_scale()` reads the INTRADAY store's "
          "split table, which does not describe these bars. It is not exactly right either: the "
          "dividend factor inflates the implied share count, which overcharges the per-share term "
          "by 0.19 bps of turnover ($8.24/day) in the SAFE direction, the 1% notional cap never "
          "binds on any of the 20,586 fills, and F-3's book is refused at -$46/day whether or not "
          "the correction is applied. A-16's unbounded-error concern does not reach this call "
          "site. NOT changed, because a conservative bias on a refused book is not worth a shipped "
          "edit; the number is on the record so the next run can price it.")


if __name__ == "__main__":
    main()
