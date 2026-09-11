#!/usr/bin/env python
"""S-14: does the momentum rotation get better when it has more candidates to rank?

The LEAN runs answer "what would the book have earned"; this script answers *why*, and it
does it with the leverage, the vol target, the margin budget and the drawdown overlay all
switched off, so nothing but the choice of names can move the number.

    python scripts/sweep_s14.py --mode select     # the decomposition (default)
    python scripts/sweep_s14.py --mode compose    # what each sleeve actually holds

The decomposition
-----------------
Each session the signal picks `top_n` names out of a pool. The return of what it picked,
measured on the *unlevered* names at gross 1.0, splits into two pieces that answer
different questions:

    selected = pool_mean + spread

`pool_mean` is what an equal-weighted basket of every rankable candidate earned that day -
the quality of the menu, which has nothing to do with the signal. `spread` is what ranking
bought on top of it - the only part momentum is responsible for. Widening the sleeve moves
both, and in opposite directions if the added names are worse assets that momentum
occasionally still prefers, so a verdict that looks at the book alone cannot tell an
allocation failure from a selection failure.

Everything here is causal in the same sense the strategy is: weights decided on bar i are
earned over bar i+1, and a name enters the pool only once it has a full lookback of priced
bars (XLRE lists 2015-10, XLC 2018-06).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                     # noqa: E402
from lean_prices import load_frames       # noqa: E402

START = "2012-01-03"
IS_END = "2019-12-31"
OOS_START = "2020-01-01"

#: Nested supersets. The only difference between them is how many names momentum ranks.
SLEEVES = {
    "etf9": list(sig.RANK_UNIVERSE),
    "sector17": list(sig.RANK_UNIVERSE) + list(sig.SECTOR_SLEEVE),
    "broad22": list(sig.RANK_UNIVERSE) + list(sig.SECTOR_SLEEVE) + list(sig.MACRO_SLEEVE),
}


def rankable(window: pd.DataFrame, pool, max_lb: int) -> list:
    """The pool members the signal is allowed to rank on this bar - its own gate."""
    return [t for t in pool if t in window.columns
            and window[t].iloc[-max_lb - 1:].notna().all()]


def walk(prices: pd.DataFrame, pool, top_n: int):
    """One pass over the sample. Returns a frame indexed by the day the return is earned.

    The drawdown overlay is switched off (empty equity curve), so the walk is a pure
    function of prices: two sleeves are compared on the same days with no path history
    between them.
    """
    params = replace(sig.DEFAULTS, rank_universe=tuple(pool), top_n=top_n)
    max_lb = max(params.mom_lookbacks) + (
        params.mom_skip if max(params.mom_lookbacks) >= params.mom_skip_min_lookback else 0)

    index = prices.index
    i0 = int(index.searchsorted(pd.Timestamp(START)))
    rows, prev = [], set()
    for i in range(i0, len(index) - 1):
        lo = max(0, i - params.history_bars + 1)
        window = prices.iloc[lo:i + 1]
        _, diag = sig.target_weights(window, (), params, {})
        winners = list(diag.get("winners") or [])
        step = prices.iloc[i + 1] / prices.iloc[i] - 1.0

        members = [t for t in rankable(window, pool, max_lb) if np.isfinite(step.get(t, np.nan))]
        pool_mean = float(np.mean([step[t] for t in members])) if members else np.nan

        vols = diag.get("alloc_vols") or {}
        funded = [t for t in winners if np.isfinite(step.get(t, np.nan))]
        if funded:
            raw = np.array([1.0 / vols[t] if vols.get(t, 0) else 1.0 for t in funded])
            weights = raw / raw.sum()
            selected = float(np.dot(weights, [step[t] for t in funded]))
        else:                                  # risk-off or nothing clears the entry gate
            selected = 0.0

        rows.append({
            "date": index[i + 1],
            "selected": selected,
            "pool_mean": pool_mean,
            "n_pool": len(members),
            "invested": bool(funded),
            "churn": len(set(winners) - prev),
            "winners": " ".join(winners),
        })
        prev = set(winners)
    return pd.DataFrame(rows).set_index("date")


def stats(frame: pd.DataFrame, label: str) -> dict:
    """Annualized picture of the unlevered selected basket, and the spread that made it."""
    sel, pool = frame["selected"], frame["pool_mean"]
    # The spread is only defined on days the book is invested; on risk-off days the signal
    # is not choosing anything, and averaging a zero against the pool would credit it for
    # sitting out - a separate effect, reported as `invested` instead.
    on = frame["invested"] & pool.notna()
    spread = (sel - pool)[on]
    years = (frame.index[-1] - frame.index[0]).days / 365.25
    curve = (1.0 + sel).cumprod()
    out = {
        "label": label,
        "days": len(frame),
        "CAR": curve.iloc[-1] ** (1 / years) - 1 if years > 0 else np.nan,
        "Sharpe": sel.mean() / sel.std() * np.sqrt(sig.TRADING_DAYS) if sel.std() > 0 else np.nan,
        "Vol": sel.std() * np.sqrt(sig.TRADING_DAYS),
        "MaxDD": float((1 - curve / curve.cummax()).max()),
        "sel_bps": sel[on].mean() * 1e4,
        "pool_bps": pool[on].mean() * 1e4,
        "spread_bps": spread.mean() * 1e4,
        "spread_t": spread.mean() / spread.std() * np.sqrt(len(spread)) if spread.std() > 0 else np.nan,
        "n_pool": frame["n_pool"].mean(),
        "invested": frame["invested"].mean(),
        "churn": frame["churn"].mean(),
    }
    return out


def print_table(rows):
    head = (f"{'cell':<26}{'CAR':>8}{'Sharpe':>8}{'Vol':>7}{'MaxDD':>8}"
            f"{'sel bps':>9}{'pool bps':>10}{'spread':>8}{'t':>7}{'pool n':>8}{'inv':>7}{'churn':>7}")
    print(head)
    print("-" * len(head))
    for m in rows:
        print(f"{m['label']:<26}{m['CAR']:>7.1%}{m['Sharpe']:>8.2f}{m['Vol']:>7.1%}"
              f"{m['MaxDD']:>8.1%}{m['sel_bps']:>9.2f}{m['pool_bps']:>10.2f}"
              f"{m['spread_bps']:>8.2f}{m['spread_t']:>7.2f}{m['n_pool']:>8.1f}"
              f"{m['invested']:>7.1%}{m['churn']:>7.2f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="select", choices=["select", "compose"])
    ap.add_argument("--top-n", type=int, default=3)
    args = ap.parse_args()

    tickers = sorted(set(SLEEVES["broad22"]) | {t for t, _ in sig.LEVERED_PROXY.values()}
                     | {sig.REGIME_TICKER})
    prices, _ = load_frames(tickers)
    print(f"[s14] {len(tickers)} tickers, {prices.index[0].date()} .. {prices.index[-1].date()}")

    walks = {}
    for name, pool in SLEEVES.items():
        walks[name] = walk(prices, pool, args.top_n)
        print(f"[s14] {name}: {len(walks[name])} sessions, pool {len(pool)} names")

    if args.mode == "select":
        print("\n=== unlevered top-%d basket, no vol target, no leverage, no overlay ===" % args.top_n)
        for period, lo, hi in [("full 2012-2026", None, None),
                               ("IS   2012-2019", None, IS_END),
                               ("OOS  2020-2026", OOS_START, None)]:
            rows = [stats(f.loc[lo:hi], f"{name}  {period}") for name, f in walks.items()]
            print_table(rows)
            print()

        print("=== paired difference against etf9, invested days only (daily bps) ===")
        base = walks["etf9"]
        for name in ["sector17", "broad22"]:
            other = walks[name]
            on = base["invested"] & other["invested"]
            diff = (other["selected"] - base["selected"])[on]
            t = diff.mean() / diff.std() * np.sqrt(len(diff)) if diff.std() > 0 else np.nan
            print(f"  {name} - etf9: {diff.mean() * 1e4:+7.2f} bps/day  t {t:+6.2f}  "
                  f"on {len(diff)} common invested days")
        return 0

    # compose: what the wider sleeves actually put in the book
    print("\n=== share of invested sessions each name is funded ===")
    added = set(sig.SECTOR_SLEEVE) | set(sig.MACRO_SLEEVE)
    for name, frame in walks.items():
        on = frame[frame["invested"]]
        counts = {}
        for row in on["winners"]:
            for t in row.split():
                counts[t] = counts.get(t, 0) + 1
        total = len(on)
        top = sorted(counts.items(), key=lambda kv: -kv[1])
        share_added = sum(v for k, v in counts.items() if k in added) / max(1, sum(counts.values()))
        levered = sum(v for k, v in counts.items() if k in sig.LEVERED_PROXY) / max(1, sum(counts.values()))
        print(f"\n  {name}: {total} invested sessions, "
              f"{share_added:.1%} of funded slots in names the shipped sleeve does not have, "
              f"{levered:.1%} in names that carry a 3x proxy")
        print("   " + "  ".join(f"{k} {v / total:.0%}" for k, v in top[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
