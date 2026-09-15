"""Phase 2: inside a high forecast-volatility day, is there a mixture worth separating?

THE QUESTION, PRECISELY
-----------------------
The volatility forecast predicts path and not displacement. There are two very different
reasons that could be true, and they have opposite implications.

    ONE DISTRIBUTION. High-volatility sessions are uniformly a bit choppier than low ones.
    Efficiency shifts down slightly and its spread is unchanged. Nothing to separate; the
    volatility model is a risk input and the story ends.

    A MIXTURE. High-volatility sessions are bimodal - some are clean trends, some are violent
    chop - and the average hides it. Then a second variable that sorts the two would turn the
    volatility forecast into something tradable, and finding that variable is the whole point
    of this phase.

The distinction is testable before any predictor is hunted, and it should be, because hunting
a predictor for a mixture that does not exist is how a research programme burns a month.

HOW A MIXTURE WOULD SHOW
------------------------
Not in the mean. In the SPREAD and the SHAPE. Specifically:

    - the standard deviation of efficiency rising with forecast volatility
    - the interquartile range widening
    - bimodality: a dip in the middle of the efficiency histogram
    - the tails growing faster than the centre - more very-efficient AND more very-choppy days

A mixture of two well-separated components has a higher variance than either component and
usually a visible dip. If the variance is flat or falling across forecast-volatility deciles,
there is no mixture to find, and that is a clean negative that saves Phases 3 and 4.

THE DIP STATISTIC
-----------------
Bimodality is tested with a simple, assumption-light statistic rather than a mixture model:
the ratio of the density at the histogram's central trough to the mean of its two modal peaks.
A unimodal distribution scores near 1; a clearly bimodal one scores well below. It is compared
against the same statistic computed on a matched unimodal reference (a normal with the same
mean and variance), so the number has something to be judged against.

CONTINUOUS FIRST, BUCKETS SECOND
----------------------------------
The brief asks for continuous or quantile analysis rather than arbitrary thresholds, so the
primary result is a rank correlation between the forecast and each efficiency target across
all sessions. Deciles are shown afterwards for legibility, not as the test.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from quant_brain.research import opportunity as opp  # noqa: E402

#: The validated futures forecast, and the closest ETF analogue the RTH-only store allows.
FUT_FEATURES = ("on_atr_pct", "on_vol_ratio", "prev_rth_rv_pct")
ETF_FEATURES = ("abs_gap_pct", "prev_range_pct", "trail_rv_20")

TARGETS = ("eff_range", "eff_path", "eff_vol", "eff_mfe", "cost_opp_usd")


def prepare(panel: pd.DataFrame, which: str) -> pd.DataFrame:
    """Attach the causal volatility forecast for the session's realised path."""
    out = []
    for _, g in panel.groupby("symbol", sort=False):
        g = g.sort_values("tdate").reset_index(drop=True).copy()
        if which == "futures":
            g["on_vol_ratio"] = g["on_volume"] / g["on_volume"].shift(1).rolling(20).mean()
            g["prev_rth_rv_pct"] = g["prev_rv_pct"]
            feats = FUT_FEATURES
        else:
            g["abs_gap_pct"] = g["gap_pct"].abs()
            feats = ETF_FEATURES
        # target of the forecast is the session's realised path, expressed as a percent
        g["rv_target"] = g["path_pts"] / g["rth_open"] * 100.0
        x = g[list(feats)].to_numpy(dtype=float)
        y = g["rv_target"].to_numpy(dtype=float)
        g["fc_vol"] = opp.walk_forward(x, y)
        g["fc_mean"] = opp.expanding_mean(y)
        out.append(g)
    return pd.concat(out, ignore_index=True)


def spearman(a: np.ndarray, b: np.ndarray) -> tuple[float, float, int]:
    m = np.isfinite(a) & np.isfinite(b)
    n = int(m.sum())
    if n < 50:
        return np.nan, np.nan, n
    r = float(np.corrcoef(pd.Series(a[m]).rank(), pd.Series(b[m]).rank())[0, 1])
    return r, float(r * np.sqrt((n - 2) / max(1e-12, 1 - r * r))), n


def dip_ratio(x: np.ndarray, bins: int = 24) -> float:
    """Trough-to-peak ratio. Near 1 means unimodal; well below means a dip in the middle."""
    x = x[np.isfinite(x)]
    if len(x) < 200:
        return np.nan
    lo, hi = np.percentile(x, 1), np.percentile(x, 99)
    h, _ = np.histogram(x[(x >= lo) & (x <= hi)], bins=bins)
    if h.sum() == 0:
        return np.nan
    h = h.astype(float)
    mid = len(h) // 2
    left_peak, right_peak = h[:mid].max(), h[mid:].max()
    trough = h[max(1, mid - bins // 6):min(len(h) - 1, mid + bins // 6)].min()
    denom = 0.5 * (left_peak + right_peak)
    return float(trough / denom) if denom > 0 else np.nan


def main() -> int:
    panels = {
        "ETF": prepare(pd.read_parquet(REPO / "research" / "efficiency_etf.parquet"), "etf"),
        "FUTURES": prepare(
            pd.read_parquet(REPO / "research" / "efficiency_futures.parquet"), "futures"),
    }

    print("=" * 104)
    print("PHASE 2 - IS HIGH FORECAST VOLATILITY A MIXTURE?")
    print("=" * 104)

    print("\n--- 0. the forecast works on both panels (sanity, not the result) " + "-" * 36)
    print(f"{'panel':8} {'sym':5} {'n':>5} {'OOS R2 path':>12}")
    for name, p in panels.items():
        for sym, g in p.groupby("symbol"):
            r2, n = opp.oos_r2(g["rv_target"].to_numpy(dtype=float),
                               g["fc_vol"].to_numpy(dtype=float),
                               g["fc_mean"].to_numpy(dtype=float))
            print(f"{name:8} {sym:5} {n:5d} {r2:12.3f}")

    print("\n--- 1. CONTINUOUS: does the forecast rank-predict efficiency at all? " + "-" * 33)
    print("    (the primary test; a strong negative here means high vol = more chop)")
    rows = []
    print(f"{'panel':8} {'sym':5} " + "".join(f"{t:>18}" for t in TARGETS))
    for name, p in panels.items():
        for sym, g in p.groupby("symbol"):
            cells = []
            for t in TARGETS:
                r, tt, n = spearman(g["fc_vol"].to_numpy(dtype=float),
                                    g[t].to_numpy(dtype=float))
                cells.append(f"{r:+.3f}({tt:+.1f})")
                rows.append({"panel": name, "symbol": sym, "target": t, "rho": r,
                             "t": tt, "n": n})
            print(f"{name:8} {sym:5} " + "".join(f"{c:>18}" for c in cells))

    print("\n--- 2. THE MIXTURE TEST: does the SPREAD of efficiency widen with forecast vol? "
          + "-" * 22)
    print("    A mixture of trend days and chop days must show a rising standard deviation.")
    spread_rows = []
    for name, p in panels.items():
        print(f"\n  {name}")
        print(f"  {'sym':5} {'decile':7} {'n':>5} {'eff_range mean':>15} {'sd':>8} "
              f"{'IQR':>8} {'dip ratio':>10}")
        for sym, g in p.groupby("symbol"):
            g = g.dropna(subset=["fc_vol", "eff_range"])
            if len(g) < 140:
                continue
            q = pd.qcut(g["fc_vol"], 5, labels=False, duplicates="drop")
            for d in sorted(set(q.dropna())):
                s = g[q == d]["eff_range"]
                print(f"  {sym:5} {int(d) + 1:7d} {len(s):5d} {s.mean():15.3f} "
                      f"{s.std():8.3f} {s.quantile(.75) - s.quantile(.25):8.3f} "
                      f"{dip_ratio(s.to_numpy()):10.3f}")
                spread_rows.append({"panel": name, "symbol": sym, "quintile": int(d) + 1,
                                    "n": len(s), "mean": float(s.mean()),
                                    "sd": float(s.std()),
                                    "iqr": float(s.quantile(.75) - s.quantile(.25)),
                                    "dip": dip_ratio(s.to_numpy())})

    sp = pd.DataFrame(spread_rows)
    print("\n--- 3. VERDICT ON THE MIXTURE " + "-" * 71)
    print(f"  {'panel':8} {'sym':5} {'sd Q1':>8} {'sd Q5':>8} {'sd trend':>9} "
          f"{'mean Q1':>9} {'mean Q5':>9}  reading")
    for (name, sym), g in sp.groupby(["panel", "symbol"]):
        g = g.sort_values("quintile")
        sd1, sd5 = g.iloc[0]["sd"], g.iloc[-1]["sd"]
        m1, m5 = g.iloc[0]["mean"], g.iloc[-1]["mean"]
        corr = float(np.corrcoef(g["quintile"], g["sd"])[0, 1]) if len(g) > 2 else np.nan
        reading = ("SPREAD WIDENS - possible mixture" if corr > 0.5 and sd5 > sd1 * 1.05
                   else "spread flat or narrowing - no mixture")
        print(f"  {name:8} {sym:5} {sd1:8.3f} {sd5:8.3f} {corr:9.2f} {m1:9.3f} {m5:9.3f}"
              f"  {reading}")

    print("\n--- 4. A UNIMODAL REFERENCE, so the dip ratio has something to beat " + "-" * 34)
    rng = np.random.default_rng(4242)
    ref = [dip_ratio(rng.normal(0.47, 0.25, 520)) for _ in range(200)]
    print(f"  dip ratio of a matched NORMAL sample (n=520): "
          f"median {np.median(ref):.3f}, 5th pct {np.percentile(ref, 5):.3f}")
    obs = sp["dip"].dropna()
    print(f"  observed dip ratios across all quintile cells: "
          f"median {obs.median():.3f}, min {obs.min():.3f}")
    print(f"  cells below the unimodal 5th percentile: "
          f"{int((obs < np.percentile(ref, 5)).sum())} of {len(obs)}")

    pd.DataFrame(rows).to_csv(REPO / "research" / "efficiency_volatility.csv", index=False)
    sp.to_csv(REPO / "research" / "efficiency_spread.csv", index=False)
    print(f"\nwrote research/efficiency_volatility.csv and efficiency_spread.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
