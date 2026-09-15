"""Phase 8: is the opportunity forecast stable, or does it live in one corner of the sample?

WHY THE SURVIVING RESULT GETS THE HARSHEST TREATMENT
------------------------------------------------------
The opportunity forecast is the only thing in this research programme that has survived
anything. Out of sample it explains roughly half the variation in regular-session realised
volatility, and it does so after yesterday's volatility is already in the model.

That makes it the single most likely place for a mistake to be hiding, because it is the only
result anybody would act on. Everything else in the programme is a null, and a null does not
need robustness testing - it needs power reporting, which it got.

So this module tries to break it, on the partitions the brief names: volatility regime, trend
regime, calendar year, instrument, and the two halves of the sample. The bar is not
"significant in every partition", which no result at these sample sizes could meet. The bar
is CONSISTENT SIGN AND SIMILAR MAGNITUDE - a forecast whose skill vanishes or inverts in a
regime is a regime-specific artefact wearing a general result's clothes.

THE SECOND TEST, WHICH MATTERS MORE
-------------------------------------
A forecast can be skilful and useless. The brief's real question is whether the forecast
improves an independent mechanism's economics, and Phase 3 answers that with a random
control. What this module adds is the intermediate quantity: does the forecast's skill at
predicting PATH translate into skill at predicting the thing a directional trader is paid
for, which is DISPLACEMENT?

The answer measured in Phase 1 was no - path R-squared near 0.5, displacement R-squared near
0.05. Here that gap is re-measured inside every partition, because if there is a regime where
the gap closes, that regime is where a gate could work, and it would be worth knowing.
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

MIN_PARTITION = 30


def forecast_panel() -> pd.DataFrame:
    """Attach the causal forecast and the partition labels to every session."""
    p = pd.read_parquet(REPO / "research" / "opportunity_panel.parquet")
    out = []
    for sym, g in p.groupby("symbol"):
        g = g.sort_values("tdate").reset_index(drop=True)
        g["fc_rv"] = opp.forecast_frame(g, "rth_rv_pct")
        g["fc_bench"] = opp.forecast_frame(g, "rth_rv_pct",
                                           features=opp.BENCHMARK_FEATURES)
        g["mean_rv"] = opp.expanding_mean(g["rth_rv_pct"].to_numpy(dtype=float))
        g["fc_disp"] = opp.forecast_frame(g, "rth_absret_pts")
        g["mean_disp"] = opp.expanding_mean(g["rth_absret_pts"].to_numpy(dtype=float))

        # partitions, all causal
        tv = g["prev_rth_rv_pct"].rolling(20).mean()
        q1 = tv.shift(1).expanding(40).quantile(1 / 3)
        q2 = tv.shift(1).expanding(40).quantile(2 / 3)
        g["vol_regime"] = np.where(tv <= q1, "LOW", np.where(tv >= q2, "HIGH", "MID"))
        # trend regime: sign of the trailing 20-session cumulative RTH return
        tr = g["rth_ret_pct"].shift(1).rolling(20).sum()
        g["trend_regime"] = np.where(tr > 0, "UP", "DOWN")
        g["year"] = pd.to_datetime(g["tdate"]).dt.year
        # overnight range / volume terciles, causal
        for src, name in (("on_range_pct", "on_range_regime"),
                          ("on_vol_ratio", "on_volume_regime")):
            a = g[src].shift(1).expanding(40).quantile(1 / 3)
            b = g[src].shift(1).expanding(40).quantile(2 / 3)
            g[name] = np.where(g[src] <= a, "LOW", np.where(g[src] >= b, "HIGH", "MID"))
        out.append(g)
    return pd.concat(out, ignore_index=True)


def r2_in(sub: pd.DataFrame, target: str, pred: str, bench: str) -> tuple[float, int]:
    y = sub[target].to_numpy(dtype=float)
    return opp.oos_r2(y, sub[pred].to_numpy(dtype=float), sub[bench].to_numpy(dtype=float))


def partition_table(panel: pd.DataFrame, by: str, title: str) -> None:
    print(f"\n--- {title} " + "-" * max(0, 88 - len(title)))
    print(f"{'sym':5} {'partition':10} {'n':>5} {'R2 path':>9} {'R2 path vs prev':>17} "
          f"{'R2 displace':>12}  verdict")
    for sym, g in panel.groupby("symbol"):
        vals = [v for v in sorted(set(g[by].dropna())) if v not in ("?", "nan")]
        signs = []
        for v in vals:
            sub = g[g[by] == v].dropna(subset=["fc_rv", "mean_rv", "rth_rv_pct"])
            if len(sub) < MIN_PARTITION:
                continue
            r_path, n = r2_in(sub, "rth_rv_pct", "fc_rv", "mean_rv")
            r_vs, _ = r2_in(sub, "rth_rv_pct", "fc_rv", "fc_bench")
            s2 = sub.dropna(subset=["fc_disp", "mean_disp"])
            r_disp, _ = (r2_in(s2, "rth_absret_pts", "fc_disp", "mean_disp")
                         if len(s2) >= MIN_PARTITION else (np.nan, 0))
            signs.append(np.sign(r_path))
            flag = "" if r_path > 0 else "  <-- SKILL GONE"
            print(f"{sym:5} {str(v):10} {n:5d} {r_path:9.3f} {r_vs:17.3f} "
                  f"{r_disp:12.3f}{flag}")
        if signs:
            agree = len(set(signs)) == 1
            print(f"      -> signs {'AGREE' if agree else 'DISAGREE'} across {by}")


def main() -> int:
    panel = forecast_panel()

    print("=" * 100)
    print("PHASE 8 - ROBUSTNESS OF THE OPPORTUNITY FORECAST")
    print("R2 path      = forecast RV vs the expanding mean  (does it forecast at all)")
    print("R2 path/prev = forecast RV vs the yesterday-only model  (does overnight add)")
    print("R2 displace  = the SAME model forecasting |net move|  (what a trade is paid for)")
    print("=" * 100)

    full = []
    for sym, g in panel.groupby("symbol"):
        s = g.dropna(subset=["fc_rv", "mean_rv"])
        r_path, n = r2_in(s, "rth_rv_pct", "fc_rv", "mean_rv")
        r_vs, _ = r2_in(s, "rth_rv_pct", "fc_rv", "fc_bench")
        s2 = g.dropna(subset=["fc_disp", "mean_disp"])
        r_disp, _ = r2_in(s2, "rth_absret_pts", "fc_disp", "mean_disp")
        full.append({"symbol": sym, "n": n, "r2_path": r_path, "r2_vs_prev": r_vs,
                     "r2_displacement": r_disp})
    print("\n--- WHOLE SAMPLE " + "-" * 74)
    print(f"{'sym':5} {'n':>5} {'R2 path':>9} {'R2 path vs prev':>17} {'R2 displace':>12}")
    for r in full:
        print(f"{r['symbol']:5} {r['n']:5d} {r['r2_path']:9.3f} {r['r2_vs_prev']:17.3f} "
              f"{r['r2_displacement']:12.3f}")

    partition_table(panel, "vol_regime", "BY TRAILING VOLATILITY REGIME")
    partition_table(panel, "trend_regime", "BY TREND REGIME (sign of trailing 20-day return)")
    partition_table(panel, "year", "BY CALENDAR YEAR")
    partition_table(panel, "on_range_regime", "BY OVERNIGHT RANGE TERCILE")
    partition_table(panel, "on_volume_regime", "BY OVERNIGHT VOLUME TERCILE")

    print("\n" + "=" * 100)
    print("BY HALF OF THE SAMPLE")
    print("=" * 100)
    print(f"{'sym':5} {'half':6} {'n':>5} {'R2 path':>9} {'R2 path vs prev':>17}")
    for sym, g in panel.groupby("symbol"):
        g = g.sort_values("tdate").dropna(subset=["fc_rv", "mean_rv"]).reset_index(drop=True)
        h = len(g) // 2
        for lbl, sub in (("first", g.iloc[:h]), ("second", g.iloc[h:])):
            if len(sub) < MIN_PARTITION:
                continue
            r_path, n = r2_in(sub, "rth_rv_pct", "fc_rv", "mean_rv")
            r_vs, _ = r2_in(sub, "rth_rv_pct", "fc_rv", "fc_bench")
            print(f"{sym:5} {lbl:6} {n:5d} {r_path:9.3f} {r_vs:17.3f}")

    pd.DataFrame(full).to_csv(REPO / "research" / "opportunity_robustness.csv", index=False)
    print(f"\nwrote {REPO / 'research' / 'opportunity_robustness.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
