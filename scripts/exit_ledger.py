"""Phase 10: record the exit study, including every architecture tested.

41 architectures x 2 halves is 82 evaluations, plus 6 entry-gate tests and 4 controls. All of
it goes in: a study that records only its shortlist leaves the next one computing a
multiplicity bar against a denominator that is far too small.
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
FAMILY = "futures.exit_architecture.v1"


def _eid(*p: str) -> str:
    return hashlib.sha256("|".join(p).encode()).hexdigest()[:16]


def main() -> int:
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    g = pd.read_csv(REPO / "research" / "exit_grid.csv")
    e = pd.read_csv(REPO / "research" / "exit_entry_information.csv")
    rows = []
    for _, r in g.iterrows():
        rows.append({
            "created": now,
            "experiment_id": _eid(FAMILY, "arch", str(r["arch"])),
            "family": f"{FAMILY}.grid",
            "hypothesis": (f"exit architecture {r['arch']} improves "
                           f"breakout.failed_reversal MNQ"),
            "metrics": {"is_per_trade": float(r.is_per_trade),
                        "oos_per_trade": float(r.oos_per_trade),
                        "is_trades": int(r.is_trades), "oos_trades": int(r.oos_trades),
                        "is_pf": (float(r.is_profit_factor)
                                  if np.isfinite(r.is_profit_factor) else None),
                        "oos_pf": (float(r.oos_profit_factor)
                                   if np.isfinite(r.oos_profit_factor) else None),
                        "oos_max_dd": float(r.oos_max_dd)},
            "params": {"architecture": r["arch"], "describe": r["describe"],
                       "entry": "breakout.failed_reversal", "symbol": "MNQ",
                       "entry_frozen": True},
            "provenance": "scripts/exit_architecture_research.py",
            "stage": "rejected",
            "notes": (f"IS ${r.is_per_trade:.2f}/trade -> OOS ${r.oos_per_trade:.2f}; "
                      f"grid IS-OOS correlation -0.002"),
            "verdict": {"metric": float(r.oos_per_trade), "t": None, "threshold": None,
                        "trials": len(g), "passed": False,
                        "reason": "no architecture beats the existing one out of sample"},
        })
    for _, r in e.iterrows():
        rows.append({
            "created": now,
            "experiment_id": _eid(FAMILY, "entry", str(r.strategy), str(r.symbol)),
            "family": f"{FAMILY}.entry_gate",
            "hypothesis": f"{r.strategy} on {r.symbol} carries forward information",
            "metrics": {f"pctile_{h}b": (float(r[f"ctrl_{h}_pctile"])
                                         if f"ctrl_{h}_pctile" in r else None)
                        for h in (1, 3, 5, 10, 20, 30, 60)},
            "params": {"strategy": r.strategy, "symbol": r.symbol,
                       "control": "matched on bar-of-session and direction, 200 reps"},
            "provenance": "scripts/exit_entry_information.py",
            "stage": "discovery" if r.strategy == "breakout.failed_reversal" else "rejected",
            "notes": f"{int(r.n_entries)} entries",
            "verdict": {"metric": None, "t": None, "threshold": 0.95, "trials": len(e),
                        "passed": r.strategy == "breakout.failed_reversal",
                        "reason": "beats matched control p95 at 2+ horizons"},
        })
    with LEDGER.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    print(f"appended {len(rows)} rows to {LEDGER.name}")

    reg = Registry()
    specs = [
        ("EXIT-1", "The library has good entries ruined by bad exit structure",
         "at least one candidate entry beats a matched control at 2+ horizons AND an exit "
         "architecture improves its out-of-sample economics",
         "entries fail the information gate, or no architecture improves the passing one",
         [Stage.DISCOVERY, Stage.REJECTED], False, None, "",
         {"candidates": 6, "passing_entry_gate": 1, "architectures_tested": 41,
          "is_oos_correlation": -0.002,
          "verdict": "BAD ENTRIES - 5 of 6 carry no forward information; the sixth is "
                     "borderline and its existing exit is already optimal"}),
        ("EXIT-2", "breakout.failed_reversal MNQ has a real one-bar entry edge",
         "signed forward excursion beats a bar-of-session-and-direction-matched control at "
         "the 95th percentile at 2+ short horizons",
         "fails the control, or the edge is not at a mechanism-consistent horizon",
         [Stage.DISCOVERY], True, "EXIT-1",
         "the only candidate to clear the gate; registered as result-driven because the "
         "1-5 bar horizon was confirmed rather than independently predicted",
         {"horizons_beaten": "1b (99.0%), 3b (97.5%), 5b (97.5%)",
          "t": "2.48 / 1.93 / 2.14", "decays_by": "bar 10",
          "bar_matched_control": "99.0 percentile",
          "random_entry_control": "93.0 percentile - BELOW the 95% bar",
          "caveat": "borderline; 343 trades; OOS $0.50/trade dies at exactly 1.00 tick"}),
        ("EXIT-3", "A trend entry with slow information is destroyed by a fast exit",
         "lengthening trend.ret_30.q80's holding period to match its 60-bar edge produces "
         "positive out-of-sample expectancy",
         "longer holds are positive in-sample and negative out of sample",
         [Stage.DISCOVERY, Stage.REJECTED], True, "EXIT-1",
         "its only control-beating horizon (60b) IS mechanism-consistent for trend and it "
         "turns over 5,511 times while losing money - the classic slow/fast mismatch shape",
         {"time20b": "IS +1.42 -> OOS -4.71", "time30b": "IS +3.56 -> OOS -4.44",
          "time120b": "IS +3.51 -> OOS -14.29",
          "verdict": "same overfit signature as the main grid"}),
        ("EXIT-4", "added.donchian_breakout is a distinct mechanism from ORB q95",
         "the Donchian implementation produces materially different trades from "
         "breakout.opening_range.q95",
         "the two produce identical results",
         [Stage.DISCOVERY, Stage.REJECTED], True, None,
         "observed while selecting candidates: both report 496 trades and -$5.80/trade on "
         "MES, identical to the cent",
         {"verdict": "NOT distinct - the Donchian added in the lab phase reuses "
                     "opening_range_pos at the same quantile. Logged, not silently fixed."}),
    ]
    added = 0
    for hid, title, pred, fals, stages, rd, parent, why, result in specs:
        if reg.get(hid):
            continue
        reg.preregister(Hypothesis(
            id=hid, title=title, mechanism_id="exit_architecture", prediction=pred,
            falsified_if=fals, instruments=("MNQ", "NQ"), parent=parent,
            modification_reason=why if parent else "", result_driven=rd,
            prior_evidence=why, notes="see docs/EXIT_RISK_RESEARCH.md"))
        for st in stages:
            reg.record(hid, stage=st, result=result if st == stages[-1] else {})
        added += 1
    print(f"registered {added} hypotheses")
    print(reg.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
