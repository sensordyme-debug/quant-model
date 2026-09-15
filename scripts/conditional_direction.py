"""Phase 2: does direction behave differently once you condition on the opportunity state?

THE PREMISE, AND WHY IT IS WORTH ONE MORE LOOK
------------------------------------------------
Eight unconditional directional hypotheses failed in the previous study. That does not settle
the conditional question, because an effect that is positive in one state and negative in
another averages to nothing, and an unconditional test is exactly the instrument that cannot
see it.

So this is a legitimate second look rather than a fishing trip - but only if the multiplicity
is counted honestly, because conditioning is the easiest way in the world to manufacture a
result. Six buckets times five conditioning variables times four instruments is 120 cells,
and at that count roughly six will clear a nominal 0.05 by construction.

THE DISCIPLINE APPLIED HERE
---------------------------
1. The bucket edges are DECLARED: the brief's own deciles (0-10, 10-25, 25-50, 50-75, 75-90,
   90-100). Nothing is tuned.
2. Every conditioning variable is computed from a TRAILING expanding distribution, so a
   session's bucket is decided from history and never from the full sample. A decile computed
   over the whole sample tells you where today sits among days that have not happened yet.
3. The Bonferroni bar counts every cell in the family, and is printed next to the results.
4. A monotonicity check is reported alongside the per-cell tests, because a real conditional
   effect should trend across adjacent buckets rather than appear in one and vanish either
   side of it. An isolated significant bucket surrounded by noise is the signature of
   multiplicity, and the monotonic trend statistic is the thing multiplicity cannot fake.

WHAT WOULD COUNT AS A FINDING
------------------------------
A bucket cell clearing the family Bonferroni bar AND a monotone trend across buckets in the
same direction AND the same sign on a majority of instruments. Any one of the three alone is
not enough, and saying so in advance is what stops the third from being negotiated away later.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

#: The brief's buckets, declared before the data is read.
EDGES = (0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0)
LABELS = ("0-10", "10-25", "25-50", "50-75", "75-90", "90-100")

#: The conditioning variables, and how the direction question is posed inside each bucket.
CONDITIONERS = (
    ("on_range_pct", "A. overnight range"),
    ("on_vol_ratio", "B. overnight volume ratio"),
    ("on_close_loc", "C. overnight close location"),
    ("on_ret_over_vol", "D. normalised overnight move"),
    ("on_absret_pct", "E. overnight move magnitude (exhaustion)"),
)

MIN_HISTORY = 60
MIN_CELL = 15


def trailing_pctile(s: pd.Series, min_history: int = MIN_HISTORY) -> np.ndarray:
    """Where today's value sits among the values seen BEFORE today. NaN during warm-up."""
    v = s.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    for i in range(min_history, len(v)):
        past = v[:i]
        past = past[np.isfinite(past)]
        if len(past) >= min_history and np.isfinite(v[i]):
            out[i] = float((past < v[i]).mean())
    return out


def bucketise(pct: np.ndarray) -> np.ndarray:
    out = np.full(len(pct), "", dtype=object)
    for i, p in enumerate(pct):
        if not np.isfinite(p):
            continue
        for j in range(len(EDGES) - 1):
            if EDGES[j] <= p < EDGES[j + 1] or (j == len(EDGES) - 2 and p == 1.0):
                out[i] = LABELS[j]
                break
    return out


def cell_stats(y: np.ndarray) -> dict:
    y = y[np.isfinite(y)]
    n = len(y)
    if n < MIN_CELL:
        return {"n": n, "mean": np.nan, "t": np.nan, "hit": np.nan}
    sd = float(np.std(y, ddof=1))
    return {"n": n, "mean": float(np.mean(y)),
            "t": float(np.mean(y) / (sd / np.sqrt(n))) if sd > 0 else np.nan,
            "hit": float(np.mean(y > 0))}


def trend_t(buckets: np.ndarray, y: np.ndarray) -> float:
    """Slope of the outcome across bucket INDEX, as a t. The monotonicity check.

    Using the bucket index rather than the raw conditioner is deliberate: it asks whether the
    effect marches across the declared buckets, which is what a real conditional relationship
    does, rather than whether a single extreme observation drags a regression line.
    """
    idx = np.array([LABELS.index(b) if b in LABELS else np.nan for b in buckets],
                   dtype=float)
    m = np.isfinite(idx) & np.isfinite(y)
    if m.sum() < 40:
        return np.nan
    x, yy = idx[m], y[m]
    if np.std(x) == 0:
        return np.nan
    r = float(np.corrcoef(x, yy)[0, 1])
    n = int(m.sum())
    return float(r * np.sqrt((n - 2) / max(1e-12, 1 - r * r)))


def main() -> int:
    p = pd.read_parquet(REPO / "research" / "opportunity_panel.parquet")
    p = p.sort_values(["symbol", "tdate"]).reset_index(drop=True)

    # Signed continuation target: did the RTH session move WITH the overnight move?
    # Posed this way so the same column answers "continuation" and "reversal" by its sign,
    # rather than needing two separate families of tests.
    p["signed_cont"] = np.sign(p["on_ret_pct"]) * p["rth_ret_pct"]

    rows = []
    n_cells = 0
    for var, _ in CONDITIONERS:
        for sym, g in p.groupby("symbol"):
            pct = trailing_pctile(g[var])
            b = bucketise(pct)
            for lab in LABELS:
                if (b == lab).sum() >= MIN_CELL:
                    n_cells += 1
    t_bonf = float(np.sqrt(2) * _erfinv(1 - 0.05 / max(1, n_cells)))

    print("=" * 104)
    print("PHASE 2 - CONDITIONAL DIRECTION")
    print(f"{n_cells} cells with at least {MIN_CELL} sessions. "
          f"Bonferroni bar for family-wise 0.05: |t| > {t_bonf:.2f}")
    print("=" * 104)

    for var, title in CONDITIONERS:
        print(f"\n{title}   (buckets are TRAILING percentiles of {var})")
        # Close location is a level, not a magnitude, so the natural target is the raw RTH
        # return; everything else conditions the CONTINUATION of the overnight move.
        target = "rth_ret_pct" if var == "on_close_loc" else "signed_cont"
        tname = "RTH ret %" if var == "on_close_loc" else "signed continuation %"
        print(f"   target: {tname}")
        print(f"   {'sym':5} " + "".join(f"{lab:>15}" for lab in LABELS) + f"{'trend t':>10}")
        for sym, g in p.groupby("symbol"):
            g = g.reset_index(drop=True)
            b = bucketise(trailing_pctile(g[var]))
            y = g[target].to_numpy(dtype=float)
            cells = []
            for lab in LABELS:
                st = cell_stats(y[b == lab])
                if not np.isfinite(st["t"]):
                    cells.append("     -")
                else:
                    star = "*" if abs(st["t"]) > t_bonf else " "
                    cells.append(f"{st['mean']:+.3f}({st['t']:+.1f}){star}")
                    rows.append({"conditioner": var, "symbol": sym, "bucket": lab,
                                 "target": target, **st,
                                 "passes_bonf": bool(abs(st["t"]) > t_bonf)})
            tt = trend_t(b, y)
            print(f"   {sym:5} " + "".join(f"{c:>15}" for c in cells)
                  + f"{tt:10.2f}" if np.isfinite(tt) else
                  f"   {sym:5} " + "".join(f"{c:>15}" for c in cells) + f"{'-':>10}")

    out = pd.DataFrame(rows)
    out.to_csv(REPO / "research" / "conditional_direction.csv", index=False)

    print("\n" + "=" * 104)
    print("SUMMARY")
    print("=" * 104)
    hits = out[out["passes_bonf"]]
    print(f"  cells tested                        {len(out)}")
    print(f"  clearing nominal |t| > 1.96         {int((out['t'].abs() > 1.96).sum())}")
    print(f"  expected by chance at 0.05          {len(out) * 0.05:.1f}")
    print(f"  clearing Bonferroni |t| > {t_bonf:.2f}      {len(hits)}")
    if len(hits):
        print("\n  cells clearing the bar:")
        for _, r in hits.iterrows():
            print(f"    {r['conditioner']:18} {r['symbol']:5} {r['bucket']:8} "
                  f"n={int(r['n']):3d} mean={r['mean']:+.3f} t={r['t']:+.2f}")
        print("\n  A cell clearing the bar is NOT a finding unless the trend statistic for")
        print("  the same conditioner also runs the same way and the sign repeats across")
        print("  instruments. Check the trend column above before believing any of these.")
    print(f"\nwrote {REPO / 'research' / 'conditional_direction.csv'}")
    return 0


def _erfinv(y: float) -> float:
    """Inverse error function; the LEAN interpreter has no scipy."""
    a = 0.147
    ln = np.log(1 - y * y)
    term = 2 / (np.pi * a) + ln / 2
    return float(np.sign(y) * np.sqrt(np.sqrt(term * term - ln / a) - term))


if __name__ == "__main__":
    raise SystemExit(main())
