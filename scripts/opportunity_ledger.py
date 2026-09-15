"""Phase 9: write this study into the ledgers, including the trials it spent finding nothing.

WHY THE NULLS GO IN TOO
-----------------------
The multiplicity bar for any future study on this data is computed from the number of trials
already spent. This study spent a lot of them: 110 conditional cells, 126 cross-market tests,
24 opening-transition cells, 120 gating cells and their controls. A study that records only
its one positive result leaves the next researcher computing a threshold against a
denominator that is far too small, and passing something they should not.

WHAT IS DISCOVERY AND WHAT IS CONFIRMATION
--------------------------------------------
The brief is explicit that these must not be blurred, so the registry records them
differently.

CONFIRMATION. The opportunity forecast's skill at predicting realised volatility was
predicted in advance from the previous study's finding, tested on a prespecified target, and
validated out of sample on every instrument and in every regime partition. It is registered
as reaching ROBUSTNESS.

DISCOVERY. The gating result - that high-forecast-volatility sessions improve the capture of
TREND mechanisms specifically - was NOT predicted. The prediction written before the test said
the opposite, and it was falsified. The result is real in the sense that it beats a
regime-matched, scale-normalised random control in 25 of 36 trend cells across four
instruments, and it is a DISCOVERY on the data that produced it. It has not been confirmed on
anything, and it is registered at DISCOVERY with `result_driven=True` so that every descendant
costs an extra trial.

The distinction matters here more than usual, because the gating result is the only positive
thing in the study and is therefore the thing most likely to be over-claimed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from quant_brain.research.genealogy import Hypothesis, Registry, Stage  # noqa: E402

LEDGER = REPO / "research" / "experiments_futures.jsonl"
FAMILY = "futures.conditional_opportunity.v1"


def _eid(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def main() -> int:
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    rows = []

    # ---- the trial counts this study actually spent --------------------------------------
    counts = {}
    for name, path, key in (
            ("conditional_direction", "conditional_direction.csv", None),
            ("cross_market", "cross_market.csv", None),
            ("opening_transition", "opening_transition.csv", None),
            ("gating", "opportunity_gating.csv", None),
            ("gating_scale_control", "gating_scale_control.csv", None)):
        f = REPO / "research" / path
        counts[name] = len(pd.read_csv(f)) if f.exists() else 0
    total = sum(counts.values())

    # ---- Phase 2: the conditional-direction cells ----------------------------------------
    cd = REPO / "research" / "conditional_direction.csv"
    if cd.exists():
        d = pd.read_csv(cd)
        for _, r in d.iterrows():
            rows.append({
                "created": now,
                "experiment_id": _eid(FAMILY, "cond", str(r["conditioner"]),
                                      str(r["symbol"]), str(r["bucket"])),
                "family": f"{FAMILY}.conditional_direction",
                "hypothesis": (f"{r['conditioner']} bucket {r['bucket']} conditions "
                               f"{r['target']} on {r['symbol']}"),
                "metrics": {"n": int(r["n"]), "mean": float(r["mean"]),
                            "t": float(r["t"]), "hit": float(r["hit"])},
                "params": {"conditioner": r["conditioner"], "bucket": r["bucket"],
                           "symbol": r["symbol"], "target": r["target"]},
                "provenance": "scripts/conditional_direction.py",
                "stage": "rejected",
                "notes": (f"|t|={abs(r['t']):.2f}; no cell of {len(d)} reached even a "
                          f"nominal 1.96"),
                "verdict": {"metric": float(r["mean"]), "t": float(r["t"]),
                            "threshold": 3.50, "trials": len(d), "passed": False,
                            "reason": "did not clear the family Bonferroni bar"},
            })

    # ---- Phase 5: cross-market ------------------------------------------------------------
    xm = REPO / "research" / "cross_market.csv"
    if xm.exists():
        d = pd.read_csv(xm)
        for _, r in d.iterrows():
            directional = str(r["outcome"]).startswith("rth_ret_")
            passed = bool(r["passes"])
            rows.append({
                "created": now,
                "experiment_id": _eid(FAMILY, "xm", str(r["feature"]), str(r["outcome"])),
                "family": f"{FAMILY}.cross_market",
                "hypothesis": f"{r['feature']} predicts {r['outcome']}",
                "metrics": {"n": int(r["n"]), "r": float(r["r"]), "t": float(r["t"])},
                "params": {"feature": r["feature"], "outcome": r["outcome"],
                           "directional": directional},
                "provenance": "scripts/cross_market.py",
                "stage": "confirmed" if passed and not directional else "rejected",
                "notes": ("magnitude finding" if passed and not directional else
                          "the single directional survivor was first-half only "
                          "(r=+0.159 then -0.000)" if passed else "null"),
                "verdict": {"metric": float(r["r"]), "t": float(r["t"]),
                            "threshold": 3.54, "trials": len(d),
                            "passed": bool(passed and not directional),
                            "reason": f"|t|={abs(r['t']):.2f} vs 3.54"},
            })

    # ---- Phase 3/4: the gating grid --------------------------------------------------------
    gt = REPO / "research" / "opportunity_gating.csv"
    sc = REPO / "research" / "gating_scale_control.csv"
    if gt.exists():
        d = pd.read_csv(gt)
        scd = pd.read_csv(sc) if sc.exists() else None
        for _, r in d.iterrows():
            norm_pct = None
            if scd is not None:
                m = scd[(scd.symbol == r["symbol"]) & (scd.strategy == r["strategy"])]
                if len(m):
                    norm_pct = float(m.iloc[0]["ctrl_norm_pctile"])
            beats = bool(r["ctrl_pt_pctile"] > 0.95)
            beats_norm = bool(norm_pct is not None and norm_pct > 0.95)
            rows.append({
                "created": now,
                "experiment_id": _eid(FAMILY, "gate", str(r["symbol"]), str(r["strategy"])),
                "family": f"{FAMILY}.gating",
                "hypothesis": (f"gating {r['strategy']} on high forecast RV improves its "
                               f"per-trade economics on {r['symbol']}"),
                "metrics": {"base_per_trade": float(r["base_per_trade"]),
                            "gated_per_trade": float(r["gated_per_trade"]),
                            "base_net": float(r["base_net"]),
                            "gated_net": float(r["gated_net"]),
                            "gated_t": float(r["gated_t"]),
                            "ctrl_pctile_raw": float(r["ctrl_pt_pctile"]),
                            "ctrl_pctile_scalefree": norm_pct},
                "params": {"symbol": r["symbol"], "strategy": r["strategy"],
                           "kind": r["kind"], "gate": "forecast_rv>=trailing_median"},
                "provenance": "scripts/opportunity_gating.py + gating_scale_control.py",
                "stage": "discovery" if (beats and beats_norm) else "rejected",
                "notes": (f"beats regime-matched control on raw $/trade: {beats}; "
                          f"on scale-free $/trade: {beats_norm}; "
                          f"gated expectancy still {'positive' if r['gated_per_trade'] > 0 else 'NEGATIVE'}; "
                          f"per-session t={r['gated_t']:.2f} does not clear the 240-evaluation "
                          f"bar of 3.70"),
                "verdict": {"metric": float(r["gated_per_trade"]),
                            "t": float(r["gated_t"]), "threshold": 3.70,
                            "trials": 240, "passed": False,
                            "reason": ("beats its random control but expectancy does not "
                                       "clear the multiplicity bar")},
            })

    with LEDGER.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print(f"appended {len(rows)} experiment rows to {LEDGER.name}")
    print(f"  trials spent this study: {counts} = {total}")

    # ---- the genealogy ---------------------------------------------------------------------
    reg = Registry()
    added = 0
    specs = [
        # id, title, prediction, falsified_if, stage_path, result_driven, parent, why, result
        ("OPP-1", "Overnight information forecasts RTH realised volatility",
         "a three-predictor model (overnight ATR, overnight volume ratio, prior-day RV) "
         "beats an expanding mean out of sample on all four instruments, and beats a "
         "yesterday-only benchmark",
         "out-of-sample R-squared at or below zero against the yesterday-only benchmark on "
         "a majority of instruments",
         [Stage.DISCOVERY, Stage.VALIDATION, Stage.ROBUSTNESS], False, None, "",
         {"r2_vs_mean": "0.457-0.506", "r2_vs_prev": "+0.077 to +0.192",
          "partitions_with_consistent_sign": "all", "instruments": 4}),
        ("OPP-2", "The same model forecasts DISPLACEMENT, not just path",
         "the opportunity model predicts the absolute net session move at out-of-sample "
         "R-squared above 0.20",
         "out-of-sample R-squared below 0.20 for |net move| while path exceeds 0.40",
         [Stage.DISCOVERY, Stage.REJECTED], False, "OPP-1",
         "the natural next question once path was forecastable",
         {"r2_displacement": "0.030-0.083", "r2_path": "0.457-0.506",
          "verdict": "rejected; the gap never closes in any regime partition"}),
        ("OPP-3", "Direction is conditionally predictable inside an opportunity bucket",
         "at least one of 110 trailing-percentile conditional cells shows signed "
         "continuation clearing the family Bonferroni bar with a monotone trend",
         "no cell clears the bar, or clearing cells show no monotone trend",
         [Stage.DISCOVERY, Stage.REJECTED], False, None, "",
         {"cells": 110, "clearing_nominal_1.96": 0, "max_abs_t": 1.9}),
        ("OPP-4", "The 75-90 percentile continuation bucket is real",
         "sessions in the 75-90 trailing percentile of overnight move magnitude show "
         "positive signed continuation at |t|>1.96 on both SPY and QQQ",
         "the effect is absent or negative on the independent ETF panel",
         [Stage.DISCOVERY, Stage.REJECTED], True, "OPP-3",
         "20 of 20 futures cells in this bucket came out positive; the bucket was chosen "
         "by looking at that result",
         {"SPY_t": -0.62, "QQQ_t": -0.35, "n": "441 and 469",
          "verdict": "falsified on independent data; the sign agreement was multiplicity"}),
        ("OPP-5", "Cross-market dispersion forecasts RTH range",
         "overnight dispersion across SPY/QQQ/IWM/DIA predicts each index's RTH range at "
         "|t| above the 126-test Bonferroni bar",
         "no dispersion measure clears the bar",
         [Stage.DISCOVERY, Stage.VALIDATION], False, None, "",
         {"r": "0.278-0.331", "t": "14.7-17.8", "n": 2571}),
        ("OPP-6", "Cross-market spreads forecast RTH direction",
         "an overnight index spread predicts an index's RTH return at |t| above the "
         "126-test Bonferroni bar, stably across sub-periods",
         "the effect is confined to one half of the sample",
         [Stage.DISCOVERY, Stage.REJECTED], False, "OPP-5",
         "the magnitude result raised the directional question",
         {"survivors_of_36": 1, "first_half_r": 0.159, "second_half_r": -0.0003,
          "verdict": "rejected on a split-half test"}),
        ("OPP-7", "Overnight information becomes useful after the opening auction",
         "a model combining overnight variables with the first 5/15/30/60 minutes beats "
         "both single models out of sample for the remainder of the session",
         "out-of-sample R-squared negative, or the interaction model below the best single",
         [Stage.DISCOVERY, Stage.REJECTED], False, None, "",
         {"cells": 24, "cells_beating_mean": 1,
          "verdict": "the interaction model was worse than the best single nearly everywhere"}),
        ("OPP-8", "The opportunity gate improves TREND mechanisms' capture",
         "gating an existing trend mechanism to high-forecast-volatility sessions raises "
         "its scale-normalised per-trade capture above a regime-matched random control",
         "the advantage disappears against a regime-matched, scale-normalised random control",
         [Stage.DISCOVERY], True, "OPP-1",
         "the prediction written before the test said the gate would HURT trend mechanisms "
         "because efficiency falls with volatility; that prediction was falsified and the "
         "opposite was observed, so this hypothesis exists because of what the data showed",
         {"trend_cells_beating_scalefree_control": "25 of 36",
          "per_symbol": "ES 7/9, MES 7/9, MNQ 4/9, NQ 7/9",
          "reversion_cells": "0 of 20, opposite sign",
          "median_capture_share_delta": 0.0024,
          "caveat": "improves losing mechanisms toward less-losing; no mechanism reaches "
                    "expectancy clearing the 240-evaluation bar"}),
        ("OPP-9", "Any gated mechanism has tradable positive expectancy",
         "at least one mechanism-instrument cell shows positive net expectancy with a "
         "per-session t clearing the 240-evaluation Bonferroni bar of 3.70",
         "no cell clears the bar",
         [Stage.DISCOVERY, Stage.REJECTED], False, "OPP-8",
         "the economics question the gating result raises",
         {"cells_with_positive_expectancy": 23, "cells_clearing_bar": 0,
          "best_t_among_positive": 1.16,
          "one_tick_slippage_erases": "13 of 36 positive cells"}),
    ]

    for hid, title, pred, fals, stages, rd, parent, why, result in specs:
        if reg.get(hid):
            continue
        reg.preregister(Hypothesis(
            id=hid, title=title, mechanism_id="conditional_opportunity",
            prediction=pred, falsified_if=fals,
            instruments=("ES", "NQ", "MES", "MNQ"), parent=parent,
            modification_reason=why if parent else "",
            result_driven=rd, prior_evidence=why,
            notes="see docs/CONDITIONAL_OPPORTUNITY_RESEARCH.md"))
        for st in stages:
            reg.record(hid, stage=st, result=result if st == stages[-1] else {})
        added += 1

    print(f"\nregistered {added} hypotheses in {reg.path.name}")
    print(reg.summary())
    print("\neffective trials (a result-driven lineage costs more):")
    for hid, *_ in specs:
        h = reg.get(hid)
        if h:
            print(f"  {hid}  stage {h.stage.value:12} effective trials "
                  f"{reg.effective_trials(hid)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
