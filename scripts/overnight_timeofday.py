"""Sections 7 and 10: where in the session does anything happen, and does it hold up by regime?

TIME OF DAY
-----------
Every result so far has treated the regular session as one number. That hides the possibility
that overnight information predicts a PART of the session even though it says nothing about
the whole: the opening auction is where overnight order flow actually lands, and an effect
that lives in the first thirty minutes and reverses by lunch would show up as zero in a
09:30-16:00 return.

So the session is cut into blocks and each is tested separately. This multiplies the number
of tests, and the Bonferroni denominator here counts every block as its own trial - otherwise
cutting the session finely enough would guarantee a "discovery" somewhere in it.

The blocks run to 16:00 ET, ten minutes inside the 16:10 ET flatten (15:10 CT), so every one
of them is tradable under the Combine rules. The last block, 15:10-16:00, is the one the
earlier research on this repository discarded, and it carries the heaviest volume of the day.

REGIME ROBUSTNESS
-----------------
A result that holds in one volatility regime and reverses in another is not robust, and the
average across both is meaningless. The regime label is assigned from a TRAILING realised
volatility so that the classification uses no future information - a regime split computed
from the full sample would leak, and the leak flatters exactly the effects one is hoping for.

The test that matters is not whether the effect is significant in each regime, which it will
not be at these sample sizes. It is whether the effect has the SAME SIGN in each regime. An
effect that flips sign across regimes is either regime-dependent, which needs a mechanism, or
noise, which needs nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

#: Every block ends at or before 16:00 ET, so all are inside the eligible window.
BLOCKS = (("09:30", "10:00", "open 30m"), ("10:00", "11:00", "10-11"),
          ("11:00", "12:00", "11-12"), ("12:00", "13:00", "12-13"),
          ("13:00", "14:00", "13-14"), ("14:00", "15:10", "14-1510"),
          ("15:10", "16:00", "1510-1600"))


def block_returns(symbol: str) -> pd.DataFrame:
    """Per trade date, the return of each block, in percent of the RTH open."""
    from overnight_panel import load_full_session
    df = load_full_session(symbol)
    rows = []
    for tdate, g in df.groupby("tdate"):
        rth = g[(g["hm"] >= "09:30") & (g["hm"] <= "16:00")]
        if len(rth) < 300:
            continue
        px = float(rth["c"].to_numpy(dtype=float)[0])
        r = {"tdate": tdate, "symbol": symbol}
        for lo, hi, name in BLOCKS:
            seg = rth[(rth["hm"] >= lo) & (rth["hm"] < hi)] if hi != "16:00" else \
                rth[(rth["hm"] >= lo) & (rth["hm"] <= hi)]
            c = seg["c"].to_numpy(dtype=float)
            r[name] = (c[-1] - c[0]) / px * 100.0 if len(c) > 1 else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def main() -> int:
    from overnight_hypotheses import futures_features, test_one

    fut = futures_features(pd.read_parquet(REPO / "research" / "overnight_panel.parquet"))
    blocks = pd.concat([block_returns(s) for s in ["ES", "NQ", "MES", "MNQ"]],
                       ignore_index=True)
    panel = fut.merge(blocks, on=["tdate", "symbol"], how="inner")

    names = [n for _, _, n in BLOCKS]

    print("=" * 94)
    print("1. UNCONDITIONAL DRIFT BY BLOCK  (is any part of the session reliably directional?)")
    print("=" * 94)
    print(f"{'sym':5} " + "".join(f"{n:>12}" for n in names))
    for sym, g in panel.groupby("symbol"):
        cells = []
        for n in names:
            v = g[n].dropna().to_numpy()
            t = np.mean(v) / (np.std(v, ddof=1) / np.sqrt(len(v)))
            cells.append(f"{np.mean(v):+.4f}({t:+.1f})")
        print(f"{sym:5} " + "".join(f"{c:>12}" for c in cells))
    print("\n  cell is mean % (t). Bonferroni over 28 cells needs |t| > 3.1")

    print("\n" + "=" * 94)
    print("2. DOES OVERNIGHT RETURN PREDICT ANY SINGLE BLOCK?")
    print("=" * 94)
    n_tests = len(names) * panel["symbol"].nunique()
    t_bonf = 3.1
    print(f"{'sym':5} " + "".join(f"{n:>12}" for n in names))
    hits = []
    for sym, g in panel.groupby("symbol"):
        cells = []
        for n in names:
            res = test_one(g["on_ret_pct"].to_numpy(float), g[n].to_numpy(float), +1)
            cells.append(f"{res['r']:+.3f}({res['t']:+.1f})")
            if abs(res["t"]) > t_bonf:
                hits.append((sym, n, res))
        print(f"{sym:5} " + "".join(f"{c:>12}" for c in cells))
    print(f"\n  cell is Pearson r (t). {n_tests} tests, Bonferroni needs |t| > {t_bonf}")
    print(f"  cells clearing it: {len(hits)}")
    for sym, n, res in hits:
        print(f"    {sym} {n}: r={res['r']:+.3f} t={res['t']:+.2f}")

    print("\n" + "=" * 94)
    print("3. DOES OVERNIGHT RANGE PREDICT BLOCK VOLATILITY?  (the surviving finding, by block)")
    print("=" * 94)
    print(f"{'sym':5} " + "".join(f"{n:>12}" for n in names))
    for sym, g in panel.groupby("symbol"):
        cells = []
        for n in names:
            res = test_one(g["on_range_pct"].to_numpy(float),
                           g[n].abs().to_numpy(float), +1)
            cells.append(f"{res['r']:+.3f}({res['t']:+.1f})")
        print(f"{sym:5} " + "".join(f"{c:>12}" for c in cells))
    print("\n  target is |block return|. This is the range finding localised in time.")

    print("\n" + "=" * 94)
    print("4. REGIME ROBUSTNESS: trailing 20-day realised vol, terciles, causal")
    print("=" * 94)
    panel = panel.sort_values(["symbol", "tdate"])
    panel["trail_vol"] = (panel.groupby("symbol")["rth_ret_pct"]
                          .transform(lambda s: s.shift(1).rolling(20).std()))
    q = panel.groupby("symbol")["trail_vol"]
    panel["regime"] = np.select(
        [panel["trail_vol"] <= q.transform(lambda s: s.expanding(60).quantile(0.33).shift(1)),
         panel["trail_vol"] >= q.transform(lambda s: s.expanding(60).quantile(0.67).shift(1))],
        ["LOW", "HIGH"], default="MID")

    print("\nthe surviving finding (overnight range -> RTH range) by regime:")
    print(f"{'sym':5} {'regime':7} {'n':>5} {'r':>8} {'t':>7}")
    for sym, g in panel.groupby("symbol"):
        for reg in ["LOW", "MID", "HIGH"]:
            s = g[g.regime == reg]
            res = test_one(s["on_range_pct"].to_numpy(float),
                           s["rth_range_pct"].to_numpy(float), +1)
            print(f"{sym:5} {reg:7} {res['n']:5d} {res['r']:+8.3f} {res['t']:+7.2f}")
        print()

    print("the DIRECTIONAL question by regime (overnight return -> RTH return):")
    print(f"{'sym':5} {'regime':7} {'n':>5} {'r':>8} {'t':>7}  sign")
    for sym, g in panel.groupby("symbol"):
        signs = []
        for reg in ["LOW", "MID", "HIGH"]:
            s = g[g.regime == reg]
            res = test_one(s["on_ret_pct"].to_numpy(float),
                           s["rth_ret_pct"].to_numpy(float), +1)
            signs.append(np.sign(res["r"]))
            print(f"{sym:5} {reg:7} {res['n']:5d} {res['r']:+8.3f} {res['t']:+7.2f}  "
                  f"{'+' if res['r'] > 0 else '-'}")
        print(f"      -> signs {'AGREE' if len(set(signs)) == 1 else 'DISAGREE across regimes'}\n")

    print("=" * 94)
    print("5. GROSS EDGE vs COST AS VOLATILITY RISES")
    print("=" * 94)
    print("The brief asks whether gross edge scales faster than cost in higher volatility.")
    print("Cost is fixed per round turn, so if the typical move grows with volatility the")
    print("ratio must improve - the question is whether it improves ENOUGH to matter.\n")
    rt = {"ES": 3.78, "NQ": 3.78, "MES": 1.22, "MNQ": 1.22}
    pv = {"ES": 50.0, "NQ": 20.0, "MES": 5.0, "MNQ": 2.0}
    print(f"{'sym':5} {'regime':7} {'n':>5} {'med |RTH move| $':>17} {'round turn $':>13} "
          f"{'ratio':>7} {'break-even hit%':>16}")
    for sym, g in panel.groupby("symbol"):
        for reg in ["LOW", "MID", "HIGH"]:
            s = g[g.regime == reg]
            if len(s) < 20:
                continue
            move = float(np.nanmedian(s["rth_ret_pts"].abs())) * pv[sym]
            ratio = move / rt[sym]
            be = 0.5 + rt[sym] / (2 * move) if move > 0 else np.nan
            print(f"{sym:5} {reg:7} {len(s):5d} {move:17,.2f} {rt[sym]:13.2f} "
                  f"{ratio:7.1f} {be:15.1%}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
