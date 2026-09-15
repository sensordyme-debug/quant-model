"""Phases 3 and 4: hunt a second variable for directional efficiency, and test its interactions.

WHAT PHASE 2 ALREADY TOLD US, AND WHY THIS STILL RUNS
-------------------------------------------------------
Phase 2 found no mixture. The standard deviation of efficiency is flat across every
forecast-volatility quintile on all eight instruments, the interquartile range is flat, and
the bimodality statistic sits where a unimodal reference puts it. High-volatility sessions are
not a blend of trend days and chop days; they are the same distribution shifted a hair.

That is evidence against finding a separator, not proof. A second variable could still predict
the LEVEL of efficiency without there being a mixture inside the volatility state, and the
brief asks for the search explicitly. So it runs - but the prior is now negative, and that is
recorded here rather than discovered as a surprise later.

THE GRID, AND WHAT IT COSTS
-----------------------------
Roughly thirty candidate predictors, five targets, eight instruments, plus the same list again
as interactions with the volatility forecast. That is a large multiple-testing burden and it
must be paid for honestly rather than argued away.

Two defences, applied together:

  1. A TEMPORAL SPLIT. Everything is searched on the first 70% of each instrument's history
     and the survivors are re-tested on the last 30%, which the search never touches. A
     predictor that only exists in the search window is multiplicity, and the holdout says so
     without any correction needing to be argued about.

  2. A BONFERRONI BAR over the whole grid, printed next to the results.

The holdout is the stronger of the two, because a correction can be quibbled with and an
out-of-sample failure cannot.

A NOTE ON THE HOLDOUT'S STATUS
-------------------------------
The ETF panel has been touched once before, by a single preregistered bucket test in the
previous study. It is therefore not pristine. The split used here is nonetheless the best
available discipline, and any survivor is labelled VALIDATION rather than CONFIRMATION for
exactly that reason.

WHY cost_opp_usd IS REPORTED BUT NOT BELIEVED
-----------------------------------------------
`cost_opp_usd` is the maximum favourable excursion in dollars, minus a round turn. It is not
scale-free: it grows with the size of the day whatever the session's shape. So the volatility
forecast predicts it at rho near 0.6 with a t near 38, which looks spectacular and means only
that big days are big. It is kept in the table because the brief asked for it, and it is
flagged everywhere it appears so that nobody quotes it as an efficiency result.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from efficiency_volatility import prepare, spearman  # noqa: E402

SPLIT = 0.70

#: Scale-free efficiency targets. cost_opp_usd is carried separately and flagged.
TARGETS = ("eff_range", "eff_mfe")
SCALED_TARGET = "cost_opp_usd"

COMMON = ("gap_pct", "abs_gap_pct", "prev_ret_pct", "prev_range_pct", "prev_rv_pct",
          "prev_eff_range", "prev_eff_vol", "prev_closeloc", "prev_n_turns",
          "prev_streak", "trail_eff_5", "trail_eff_20", "eff_state", "trail_rv_5",
          "trail_rv_20", "vol_state", "fc_vol")

FUTURES_ONLY = ("on_ret_pct", "on_abs_ret_pct", "on_range_pct", "on_atr_pct", "on_rv_pct",
                "on_closeloc", "on_upper_wick", "on_lower_wick", "on_eff",
                "on_range_over_prev", "on_vol_ratio")

OPENING = tuple(f"open{w}_{k}" for w in (1, 5, 15, 30)
                for k in ("ret_pct", "absret_pct", "range_pct", "closeloc", "vol_share"))


def add_derived(p: pd.DataFrame, which: str) -> pd.DataFrame:
    out = []
    for _, g in p.groupby("symbol", sort=False):
        g = g.sort_values("tdate").reset_index(drop=True).copy()
        g["abs_gap_pct"] = g["gap_pct"].abs()
        if which == "futures":
            g["on_abs_ret_pct"] = g["on_ret_pct"].abs()
            g["on_range_over_prev"] = g["on_range_pct"] / g["prev_range_pct"]
        out.append(g)
    return pd.concat(out, ignore_index=True)


def erfinv(y: float) -> float:
    a = 0.147
    ln = np.log(1 - y * y)
    term = 2 / (np.pi * a) + ln / 2
    return float(np.sign(y) * np.sqrt(np.sqrt(term * term - ln / a) - term))


def bonf(n: int, alpha: float = 0.05) -> float:
    return float(np.sqrt(2) * erfinv(1 - alpha / max(1, n)))


def run_panel(p: pd.DataFrame, preds: tuple[str, ...], label: str,
              min_n: int = 120) -> pd.DataFrame:
    """Search on the first 70%, re-test survivors on the last 30%."""
    rows = []
    for sym, g in p.groupby("symbol"):
        g = g.sort_values("tdate").reset_index(drop=True)
        cut = int(len(g) * SPLIT)
        search, hold = g.iloc[:cut], g.iloc[cut:]
        for pred in preds:
            if pred not in g.columns:
                continue
            for tgt in (*TARGETS, SCALED_TARGET):
                if tgt not in g.columns:
                    continue
                rs, ts, ns = spearman(search[pred].to_numpy(dtype=float),
                                      search[tgt].to_numpy(dtype=float))
                rh, th, nh = spearman(hold[pred].to_numpy(dtype=float),
                                      hold[tgt].to_numpy(dtype=float))
                if ns < min_n:
                    continue
                rows.append({"panel": label, "symbol": sym, "predictor": pred,
                             "target": tgt, "kind": "main",
                             "rho_search": rs, "t_search": ts, "n_search": ns,
                             "rho_hold": rh, "t_hold": th, "n_hold": nh,
                             "scale_free": tgt != SCALED_TARGET})
                # ---- the interaction the brief asks for -----------------------------------
                if pred == "fc_vol" or "fc_vol" not in g.columns:
                    continue
                ix_s = (search[pred] * search["fc_vol"]).to_numpy(dtype=float)
                ix_h = (hold[pred] * hold["fc_vol"]).to_numpy(dtype=float)
                ris, tis, nis = spearman(ix_s, search[tgt].to_numpy(dtype=float))
                rih, tih, nih = spearman(ix_h, hold[tgt].to_numpy(dtype=float))
                rows.append({"panel": label, "symbol": sym,
                             "predictor": f"fc_vol x {pred}", "target": tgt,
                             "kind": "interaction",
                             "rho_search": ris, "t_search": tis, "n_search": nis,
                             "rho_hold": rih, "t_hold": tih, "n_hold": nih,
                             "scale_free": tgt != SCALED_TARGET})
    return pd.DataFrame(rows)


def main() -> int:
    etf = add_derived(
        prepare(pd.read_parquet(REPO / "research" / "efficiency_etf.parquet"), "etf"), "etf")
    fut = add_derived(
        prepare(pd.read_parquet(REPO / "research" / "efficiency_futures.parquet"),
                "futures"), "futures")

    a = run_panel(etf, COMMON + OPENING, "ETF")
    b = run_panel(fut, COMMON + FUTURES_ONLY + OPENING, "FUTURES", min_n=100)
    out = pd.concat([a, b], ignore_index=True).dropna(subset=["t_search"])
    out.to_csv(REPO / "research" / "efficiency_search.csv", index=False)

    n_tests = len(out)
    t_bar = bonf(n_tests)

    print("=" * 106)
    print("PHASES 3 AND 4 - SECOND-VARIABLE SEARCH AND INTERACTIONS")
    print(f"{n_tests} tests. Bonferroni bar |t| > {t_bar:.2f}. "
          f"Search = first {SPLIT:.0%}, holdout = last {1 - SPLIT:.0%}.")
    print("=" * 106)

    sf = out[out.scale_free]
    print(f"\nScale-free targets only ({len(sf)} tests):")
    print(f"  clearing nominal |t| > 1.96 in SEARCH   {int((sf.t_search.abs() > 1.96).sum())} "
          f"(expected by chance {len(sf) * 0.05:.0f})")
    print(f"  clearing Bonferroni in SEARCH           "
          f"{int((sf.t_search.abs() > t_bar).sum())}")
    surv = sf[(sf.t_search.abs() > t_bar)]
    print(f"  of those, SAME SIGN and |t|>1.96 in HOLDOUT   "
          f"{int(((np.sign(surv.rho_hold) == np.sign(surv.rho_search)) & (surv.t_hold.abs() > 1.96)).sum())}")

    print("\n--- STRONGEST SCALE-FREE CANDIDATES BY SEARCH |t| " + "-" * 54)
    print(f"{'panel':8} {'sym':5} {'predictor':28} {'target':10} {'kind':11} "
          f"{'rho_s':>7} {'t_s':>7} {'rho_h':>7} {'t_h':>7}  holdout")
    top = sf.reindex(sf.t_search.abs().sort_values(ascending=False).index).head(22)
    for _, r in top.iterrows():
        same = np.sign(r.rho_hold) == np.sign(r.rho_search)
        verdict = ("REPLICATES" if same and abs(r.t_hold) > 1.96
                   else "same sign, weak" if same else "SIGN FLIPS")
        print(f"{r['panel']:8} {r['symbol']:5} {r['predictor'][:28]:28} {r['target']:10} "
              f"{r['kind']:11} {r['rho_search']:+7.3f} {r['t_search']:+7.2f} "
              f"{r['rho_hold']:+7.3f} {r['t_hold']:+7.2f}  {verdict}")

    print("\n--- DOES CONDITIONING ON VOLATILITY RESCUE A WEAK VARIABLE? " + "-" * 44)
    print("  (the Phase 4 question: interaction stronger than the main effect?)")
    piv = sf.pivot_table(index=["panel", "symbol", "target"], columns="kind",
                         values="t_search", aggfunc=lambda s: s.abs().max())
    if {"main", "interaction"}.issubset(piv.columns):
        piv = piv.dropna()
        better = int((piv["interaction"] > piv["main"]).sum())
        print(f"  cells where the best interaction beats the best main effect: "
              f"{better} of {len(piv)}")
        print(f"  median best |t|: main {piv['main'].median():.2f}, "
              f"interaction {piv['interaction'].median():.2f}")

    print("\n--- THE SCALED TARGET, FOR COMPLETENESS AND WITH A WARNING " + "-" * 45)
    sc = out[~out.scale_free]
    strongest = sc.reindex(sc.t_search.abs().sort_values(ascending=False).index).head(5)
    print("  cost_opp_usd is NOT scale-free: it grows with the size of the day.")
    print(f"{'panel':8} {'sym':5} {'predictor':28} {'rho_s':>7} {'t_s':>7}")
    for _, r in strongest.iterrows():
        print(f"{r['panel']:8} {r['symbol']:5} {r['predictor'][:28]:28} "
              f"{r['rho_search']:+7.3f} {r['t_search']:+7.2f}")
    print("  These reflect day SIZE, not directional quality. Not evidence of an edge.")

    print("\n--- REPLICATION SUMMARY BY PREDICTOR FAMILY " + "-" * 60)
    def fam(name: str) -> str:
        base = name.replace("fc_vol x ", "")
        if base.startswith("on_"):
            return "overnight"
        if base.startswith("open"):
            return "opening"
        if base.startswith(("prev_", "trail_", "eff_state", "vol_state")):
            return "prior RTH"
        return "other"
    sf2 = sf.assign(family=sf.predictor.map(fam))
    print(f"  {'family':12} {'tests':>6} {'|t_s|>1.96':>11} {'|t_h|>1.96 same sign':>22} "
          f"{'median |rho_s|':>15}")
    for f, g in sf2.groupby("family"):
        same = (np.sign(g.rho_hold) == np.sign(g.rho_search)) & (g.t_hold.abs() > 1.96)
        print(f"  {f:12} {len(g):6d} {int((g.t_search.abs() > 1.96).sum()):11d} "
              f"{int(same.sum()):22d} {g.rho_search.abs().median():15.3f}")

    print(f"\nwrote {REPO / 'research' / 'efficiency_search.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
