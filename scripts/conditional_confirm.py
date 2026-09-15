"""The one pattern Phase 2 threw up, taken to independent data before anyone believes it.

WHAT WAS SEEN
-------------
Across 110 conditional cells on the futures panel, not one cleared even a nominal |t| > 1.96.
That is a null, and it is the headline.

But the 75-90 percentile bucket came out POSITIVE in all twenty of its cells - five
conditioning variables times four instruments - with t between 1.2 and 1.9. Twenty of twenty
is not something to wave away, and it is not something to believe either.

WHY IT CANNOT BE JUDGED WHERE IT WAS FOUND
--------------------------------------------
The twenty cells are nowhere near independent. The five conditioners are strongly correlated
with each other (overnight range, overnight volume, overnight move magnitude and normalised
move all rise together on a busy night). The four instruments are two pairs: ES and MES track
the same index, NQ and MNQ likewise, so there are at most two independent markets here. The
effective number of independent tests is perhaps four, not twenty, and four coin flips
landing the same way happens one time in eight.

Worse, the bucket was chosen BY LOOKING AT THE RESULT. Testing it again on the same 312
sessions would be circular no matter how the arithmetic is dressed up.

THE CONFIRMATION TEST
---------------------
SPY and QQQ, 2016-2026, 2,662 sessions from a different vendor and venue - data that had no
hand in generating the hypothesis. The ETF store holds only the close-to-open return, so only
the magnitude conditioner (E) transfers, which is fine: E is the one with a mechanism behind
it worth stating, and a single preregistered test on independent data is worth more than five
correlated ones on the data that suggested it.

The prediction, fixed before the test runs: sessions whose overnight move sits in the 75th to
90th trailing percentile show POSITIVE signed continuation, at |t| > 1.96, on both ETFs.

If it fails, it was multiplicity, and it gets recorded as such.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from conditional_direction import (EDGES, LABELS, bucketise,  # noqa: E402
                                   cell_stats, trailing_pctile)


def main() -> int:
    etf = pd.read_parquet(REPO / "research" / "etf_overnight_panel.parquet")
    etf = etf.sort_values(["symbol", "tdate"]).reset_index(drop=True)
    etf["on_absret_pct"] = etf["on_ret_pct"].abs()
    etf["signed_cont"] = np.sign(etf["on_ret_pct"]) * etf["rth_ret_pct"]

    print("=" * 100)
    print("CONFIRMATION TEST ON INDEPENDENT DATA")
    print("preregistered prediction: the 75-90 bucket shows POSITIVE signed continuation")
    print("at |t| > 1.96 on both SPY and QQQ, 2016-2026")
    print("=" * 100)
    print(f"\n{'sym':5} {'bucket':9} {'n':>6} {'mean %':>10} {'t':>8} {'hit':>7}  "
          f"{'prediction':>12}")

    verdicts = {}
    for sym, g in etf.groupby("symbol"):
        g = g.reset_index(drop=True)
        b = bucketise(trailing_pctile(g["on_absret_pct"]))
        y = g["signed_cont"].to_numpy(dtype=float)
        for lab in LABELS:
            st = cell_stats(y[b == lab])
            if not np.isfinite(st["t"]):
                continue
            tag = "<== TESTED" if lab == "75-90" else ""
            print(f"{sym:5} {lab:9} {st['n']:6d} {st['mean']:+10.4f} {st['t']:+8.2f} "
                  f"{st['hit']:7.3f}  {tag:>12}")
            if lab == "75-90":
                verdicts[sym] = st
        print()

    print("=" * 100)
    print("VERDICT")
    print("=" * 100)
    ok = all(v["t"] > 1.96 for v in verdicts.values())
    for sym, v in verdicts.items():
        passed = v["t"] > 1.96
        print(f"  {sym}: n={v['n']}, mean={v['mean']:+.4f}%, t={v['t']:+.2f} -> "
              f"{'CONFIRMED' if passed else 'NOT CONFIRMED'}")
    print(f"\n  Preregistered prediction {'HOLDS' if ok else 'FAILS'}.")
    if not ok:
        print("  The 20-of-20 sign agreement on the futures panel was multiplicity across")
        print("  correlated cells, not a conditional effect. Recorded as a negative result.")

    # The whole-panel monotonicity, for completeness: does continuation trend across buckets
    # anywhere in ten years of data?
    print("\n" + "=" * 100)
    print("AND THE TREND ACROSS ALL BUCKETS, ON TEN YEARS")
    print("=" * 100)
    for sym, g in etf.groupby("symbol"):
        g = g.reset_index(drop=True)
        b = bucketise(trailing_pctile(g["on_absret_pct"]))
        y = g["signed_cont"].to_numpy(dtype=float)
        idx = np.array([LABELS.index(x) if x in LABELS else np.nan for x in b], dtype=float)
        m = np.isfinite(idx) & np.isfinite(y)
        r = float(np.corrcoef(idx[m], y[m])[0, 1])
        n = int(m.sum())
        t = r * np.sqrt((n - 2) / max(1e-12, 1 - r * r))
        print(f"  {sym}: n={n}, trend r={r:+.4f}, t={t:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
