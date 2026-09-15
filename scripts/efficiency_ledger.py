"""Phase 10: record this study, including the two artefacts, in the permanent ledgers.

WHY THE ARTEFACTS GET THEIR OWN ENTRIES
-----------------------------------------
Most of what this study spent was trials on nulls, and those go in for the usual reason: the
next study's multiplicity bar is computed from the denominator, and a denominator that only
counts successes is a lie.

But two entries here are a different kind of record. This study produced two results that
would have been reported as major discoveries - both replicated out of sample, on four
instruments, at t up to 20 - and both were artefacts of construction rather than of the
market. They are registered as REJECTED with the mechanism written into the notes, because
the specific danger with an artefact is that somebody rediscovers it, finds it replicates
beautifully, and believes it.

DISCOVERY vs VALIDATION vs CONFIRMATION
-----------------------------------------
Nothing in this study reaches VALIDATION. The one thing that gets a positive entry is the
structural fact - intraday sessions displace less than a random walk - and it is a
description of the data rather than a predictive claim, so it is recorded at ROBUSTNESS
(measured on eight instruments across two panels and eleven years) with no path upward.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from quant_brain.research.genealogy import Hypothesis, Registry, Stage  # noqa: E402

LEDGER = REPO / "research" / "experiments_futures.jsonl"
FAMILY = "futures.directional_efficiency.v1"


def _eid(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def main() -> int:
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    rows = []
    counts = {}

    # ---- the search grid, one row per test ------------------------------------------------
    f = REPO / "research" / "efficiency_search_clean.csv"
    if f.exists():
        d = pd.read_csv(f)
        counts["search_clean"] = len(d)
        from efficiency_search import bonf
        bar = bonf(len(d))
        rep = ((np.sign(d.rho_hold) == np.sign(d.rho_search))
               & (d.t_hold.abs() > 1.96) & (d.t_search.abs() > bar))
        d = d.assign(replicates=rep)
        for _, r in d.iterrows():
            rows.append({
                "created": now,
                "experiment_id": _eid(FAMILY, str(r["symbol"]), str(r["predictor"]),
                                      str(r["target"])),
                "family": f"{FAMILY}.search",
                "hypothesis": f"{r['predictor']} predicts {r['target']} on {r['symbol']}",
                "metrics": {"rho_search": float(r["rho_search"]),
                            "t_search": float(r["t_search"]),
                            "rho_hold": float(r["rho_hold"]),
                            "t_hold": float(r["t_hold"]),
                            "n_search": int(r["n_search"])},
                "params": {"panel": r["panel"], "symbol": r["symbol"],
                           "predictor": r["predictor"], "target": r["target"],
                           "kind": r["kind"], "window_matched": True},
                "provenance": "scripts/efficiency_search_clean.py",
                "stage": "rejected",
                "notes": (f"search |t|={abs(r['t_search']):.2f} vs Bonferroni {bar:.2f}; "
                          f"holdout |t|={abs(r['t_hold']):.2f}; "
                          f"{'replicates' if r['replicates'] else 'does not replicate'}"),
                "verdict": {"metric": float(r["rho_search"]), "t": float(r["t_search"]),
                            "threshold": bar, "trials": len(d),
                            "passed": bool(r["replicates"]),
                            "reason": "split-half replication required"},
            })

    for name, path in (("volatility", "efficiency_volatility.csv"),
                       ("spread", "efficiency_spread.csv"),
                       ("nonlinear", "efficiency_nonlinear.csv"),
                       ("pathshape", "efficiency_pathshape.csv"),
                       ("families", "efficiency_families.csv"),
                       ("costs", "efficiency_costs.csv")):
        p = REPO / "research" / path
        counts[name] = len(pd.read_csv(p)) if p.exists() else 0

    with LEDGER.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    total = sum(counts.values())
    print(f"appended {len(rows)} experiment rows to {LEDGER.name}")
    print(f"  trials/records this study: {counts} = {total}")

    # ---- genealogy -------------------------------------------------------------------------
    reg = Registry()
    specs = [
        ("EFF-1", "High forecast volatility is a MIXTURE of trend days and chop days",
         "the standard deviation and interquartile range of directional efficiency rise "
         "with the forecast-volatility quintile on a majority of instruments",
         "spread flat or narrowing across quintiles",
         [Stage.DISCOVERY, Stage.REJECTED], False, None, "",
         {"sd_Q1_to_Q5": "0.255-0.270, flat on all 8 instruments",
          "sd_trend_corr": "-0.62 to +0.08",
          "dip_ratio_cells_below_unimodal_5th_pct": "2 of 20",
          "verdict": "no mixture; there is nothing to separate"}),
        ("EFF-2", "A second variable predicts directional efficiency",
         "at least one window-matched predictor clears the family Bonferroni bar in a "
         "70% search window and replicates with the same sign at |t|>1.96 in the held-out 30%",
         "no predictor replicates",
         [Stage.DISCOVERY, Stage.REJECTED], False, "EFF-1",
         "the search the mixture question motivates, run regardless of EFF-1's result",
         {"tests": 4788, "clearing_bonferroni_in_search": 69,
          "replicating_out_of_sample": 0,
          "by_family": "opening 0/840, overnight 0/924, prior RTH 0/3024"}),
        ("EFF-3", "Conditioning on forecast volatility rescues a weak variable",
         "a predictor with |t|<1.96 as a main effect exceeds the Bonferroni bar as an "
         "interaction with the volatility forecast, and replicates",
         "no weak main effect is rescued by the interaction",
         [Stage.DISCOVERY, Stage.REJECTED], False, "EFF-2",
         "the Phase 4 question, which the main-effect null makes worth asking separately",
         {"rescued": 0, "interaction_beats_own_main_effect": "986 of 1928 (51%, chance)"}),
        ("EFF-4", "Efficiency is an inverted-U in forecast volatility",
         "quadratic curvature is negative and significant in both halves of the sample, "
         "with a stable peak, and beats a linear fit out of sample",
         "curvature flips sign across the split, or a line does as well out of sample",
         [Stage.DISCOVERY, Stage.REJECTED], True, "EFF-1",
         "the quintile table showed a rise-then-fall that a rank correlation cannot see; "
         "this hypothesis exists because of that observed shape",
         {"cells": 24, "negative_curvature_in_search": 18,
          "negative_in_both_halves": 3, "passing_all_three_criteria": 0,
          "verdict": "curvature flips sign out of sample in 15 of 18"}),
        ("EFF-5", "The opening move predicts the session's excursion efficiency",
         "open30 absolute return predicts eff_mfe at rho above 0.2 with out-of-sample "
         "replication on all four ETFs",
         "the relationship vanishes when the target excludes the predictor's own window",
         [Stage.DISCOVERY, Stage.REJECTED], True, "EFF-2",
         "observed at rho +0.235 to +0.357, t 12 to 20, replicating on all four ETFs; "
         "registered because it looked like the study's headline finding",
         {"whole_session_rho": "+0.235 to +0.357", "whole_session_t": "12.5 to 19.7",
          "remainder_only_rho": "-0.023 to +0.028", "remainder_only_t": "-1.18 to +1.47",
          "verdict": "ARTEFACT - accounting identity; the opening move is part of the "
                     "maximum favourable excursion it appears to predict"}),
        ("EFF-6", "Opening volume share predicts remainder-of-session efficiency",
         "the first W minutes' share of session volume predicts the remaining session's "
         "efficiency negatively, replicating on all four ETFs at every window",
         "the relationship vanishes when the denominator is made causal",
         [Stage.DISCOVERY, Stage.REJECTED], True, "EFF-2",
         "observed replicating on all four ETFs at all four windows, |t| up to 9.7",
         {"leaky_rho": "-0.116 to -0.185", "leaky_t": "-5.9 to -9.7",
          "causal_rho": "-0.022 to +0.011", "causal_t": "-1.13 to +0.55",
          "verdict": "ARTEFACT - look-ahead; share-of-day divides by total session volume, "
                     "unknown at minute W. Correlation of the leaky share with "
                     "rest-of-day volume is -0.249 (t=-13.3)"}),
        ("EFF-7", "Intraday index sessions displace less than a random walk",
         "median |net move| divided by the random-walk expectation sigma*sqrt(n) is below "
         "1.0 on every index instrument",
         "median eff_vol at or above 1.0 on a majority of instruments",
         [Stage.DISCOVERY, Stage.VALIDATION, Stage.ROBUSTNESS], False, None, "",
         {"median_eff_vol": "0.655 to 0.738 across 8 instruments",
          "panels": "ETF 2016-2026 (n~2600 each) and futures 2025-2026",
          "note": "descriptive, not predictive; the structural reason directional "
                  "mechanisms are hard on this asset class"}),
        ("EFF-8", "The volatility-plus-second-variable gate improves strategy economics",
         "gating a representative mechanism on forecast volatility AND the strongest "
         "second-variable candidate beats a regime-matched random control",
         "the conditioned arm does not beat its control more often than chance",
         [Stage.DISCOVERY, Stage.REJECTED], True, "EFF-2",
         "built from the candidate that led the SEARCH window (prev_rv_pct, t=+5.54) and "
         "failed the holdout (t=+0.19); run to show the null propagates to economics",
         {"cells": 12, "beating_control_p95": 1, "expected_by_chance": 0.6,
          "positive_per_trade": "6 of 12, none better than its own baseline consistently",
          "break_even_slippage_ES_MES": "0.37 to 0.40 ticks"}),
    ]

    added = 0
    for hid, title, pred, fals, stages, rd, parent, why, result in specs:
        if reg.get(hid):
            continue
        reg.preregister(Hypothesis(
            id=hid, title=title, mechanism_id="directional_efficiency",
            prediction=pred, falsified_if=fals,
            instruments=("ES", "NQ", "MES", "MNQ", "SPY", "QQQ", "IWM", "DIA"),
            parent=parent, modification_reason=why if parent else "",
            result_driven=rd, prior_evidence=why,
            notes="see docs/VOLATILITY_DIRECTIONAL_EFFICIENCY_RESEARCH.md"))
        for st in stages:
            reg.record(hid, stage=st, result=result if st == stages[-1] else {})
        added += 1

    print(f"\nregistered {added} hypotheses in {reg.path.name}")
    print(reg.summary())
    print("\neffective trials:")
    for hid, *_ in specs:
        h = reg.get(hid)
        if h:
            print(f"  {hid}  {h.stage.value:12} effective trials {reg.effective_trials(hid)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
