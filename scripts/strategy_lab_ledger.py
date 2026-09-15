"""Phase 11: record the lab in the permanent ledgers.

Every cell is a trial. 132 of them, plus the two cost regimes, plus the Topstep sweep. A
selection lab that records only its shortlist leaves the next study computing a multiplicity
bar against a denominator that is far too small.

The three added strategies are registered separately and flagged, because they had no prior
standing and their inclusion was a decision this phase made.
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
from quant_brain.research.genealogy import Hypothesis, Registry, Stage  # noqa: E402

LEDGER = REPO / "research" / "experiments_futures.jsonl"
FAMILY = "futures.strategy_lab.v1"


def _eid(*p: str) -> str:
    return hashlib.sha256("|".join(p).encode()).hexdigest()[:16]


def main() -> int:
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    cards = pd.read_csv(REPO / "research" / "lab_scorecards.csv")
    port = pd.read_csv(REPO / "research" / "lab_portfolio.csv")
    ts = pd.read_csv(REPO / "research" / "lab_topstep.csv")

    rows = []
    for _, r in cards.iterrows():
        rows.append({
            "created": now,
            "experiment_id": _eid(FAMILY, str(r.strategy), str(r.symbol)),
            "family": f"{FAMILY}.baseline",
            "hypothesis": f"{r.strategy} is tradable on {r.symbol} inside Topstep constraints",
            "metrics": {"trades": int(r.trades), "net_pnl": float(r.net_pnl),
                        "per_trade": float(r.expectancy_trade),
                        "stressed_per_trade": float(r.stressed_expectancy_trade),
                        "profit_factor": (float(r.profit_factor)
                                          if np.isfinite(r.profit_factor) else None),
                        "win_rate": float(r.win_rate), "max_dd": float(r.max_dd),
                        "dd_over_mll": float(r.dd_over_mll), "t": float(r.t_stat),
                        "median_hold_min": float(r.median_hold_min)},
            "params": {"strategy": r.strategy, "symbol": r.symbol, "family": r.family,
                       "contracts": 1, "window": "09:30-16:00 ET",
                       "newly_added": bool(r.newly_added)},
            "provenance": "scripts/strategy_lab_run.py + strategy_lab_topstep.py",
            "stage": {"REJECT": "rejected", "WATCH": "discovery",
                      "RESEARCH": "discovery"}.get(r.verdict, "rejected"),
            "notes": (f"verdict {r.verdict}; drawdown {r.dd_over_mll:.1f}x the $2,000 MLL; "
                      f"t={r.t_stat:.2f} vs 1.96 nominal and ~3.6 Bonferroni over "
                      f"{len(cards)} cells"),
            "verdict": {"metric": float(r.expectancy_trade), "t": float(r.t_stat),
                        "threshold": 3.6, "trials": len(cards),
                        "passed": False,
                        "reason": f"{r.verdict}: no cell clears barrier AND evidence"},
        })
    with LEDGER.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    print(f"appended {len(rows)} rows to {LEDGER.name}")

    reg = Registry()
    specs = [
        ("LAB-1", "Some existing strategy is tradable inside Topstep constraints",
         "at least one of 132 strategy-instrument cells shows positive stressed expectancy, "
         "a 1-contract max drawdown below the $2,000 MLL, and t >= 1.96",
         "no cell satisfies all three",
         [Stage.DISCOVERY, Stage.REJECTED], False, None, "",
         {"cells": 132, "verdicts": "130 REJECT / 1 RESEARCH / 1 WATCH",
          "under_mll": 8, "median_dd_over_mll": 7.9,
          "t_gt_196_and_positive": 0,
          "positive_normal": 12, "positive_stressed": 6}),
        ("LAB-2", "The library's drawdowns are compatible with a $2,000 trailing barrier",
         "a majority of cells have 1-contract max drawdown below $2,000",
         "fewer than half do",
         [Stage.DISCOVERY, Stage.REJECTED], False, "LAB-1",
         "the barrier test is prior to every other question and decides most of the field",
         {"under_mll": "8 of 132", "median_ratio": "7.9x", "leader_ratio": "20.0x",
          "mc_prob_dd_exceeds_mll": "100% for every ES and NQ cell at every size"}),
        ("LAB-3", "Bracketing the reversion family brings it inside the barrier",
         "adding a stop and target to a reversion mechanism keeps win rate above 65% while "
         "bringing 1-contract max drawdown below $2,000",
         "the bracketed version loses its win rate or keeps its drawdown",
         [Stage.PROPOSED], True, "LAB-1",
         "reversion holds 4 of the 8 sub-barrier cells and the only strong win rates "
         "(80.9%); its failure is drawdown SHAPE, which is what a stop addresses. This "
         "hypothesis exists because of the family breakdown this lab produced.",
         {}),
    ]
    added = 0
    for hid, title, pred, fals, stages, rd, parent, why, result in specs:
        if reg.get(hid):
            continue
        reg.preregister(Hypothesis(
            id=hid, title=title, mechanism_id="strategy_lab", prediction=pred,
            falsified_if=fals, instruments=("ES", "NQ", "MES", "MNQ"),
            parent=parent, modification_reason=why if parent else "",
            result_driven=rd, prior_evidence=why,
            notes="see docs/STRATEGY_BACKTEST_LAB.md"))
        for st in stages:
            reg.record(hid, stage=st, result=result if st == stages[-1] else {})
        added += 1
    print(f"registered {added} hypotheses")
    print(reg.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
