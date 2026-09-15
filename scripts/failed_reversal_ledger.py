"""Phase 11: record the replication study in the ledgers."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))
from quant_brain.research.genealogy import Hypothesis, Registry, Stage  # noqa: E402
from failed_reversal_spec import rule_hash  # noqa: E402

LEDGER = REPO / "research" / "experiments_futures.jsonl"
FAMILY = "futures.failed_reversal_replication.v1"


def _eid(*p: str) -> str:
    return hashlib.sha256("|".join(p).encode()).hexdigest()[:16]


def main() -> int:
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    h = rule_hash()
    rows = []
    for name, path, kind in (("instruments", "fr_replication_instruments.csv", "confirmatory"),
                             ("periods", "fr_replication_periods.csv", "confirmatory"),
                             ("eras", "fr_replication_eras.csv", "confirmatory"),
                             ("regimes", "fr_replication_regimes.csv", "descriptive"),
                             ("buckets", "fr_replication_buckets.csv", "descriptive"),
                             ("friction", "fr_replication_friction.csv", "confirmatory")):
        f = REPO / "research" / path
        if not f.exists():
            continue
        d = pd.read_csv(f)
        for _, r in d.iterrows():
            rows.append({
                "created": now,
                "experiment_id": _eid(FAMILY, name, str(r.get("symbol")),
                                      str(r.get("period", r.get("regime",
                                                                r.get("bucket", "")))) ),
                "family": f"{FAMILY}.{name}",
                "hypothesis": (f"frozen failed_reversal (hash {h}) replicates on "
                               f"{r.get('panel','')} {r.get('symbol','')} "
                               f"{r.get('period', r.get('regime', r.get('bucket','')))}"),
                "metrics": {k: (float(v) if isinstance(v, (int, float, np.floating))
                                and np.isfinite(v) else None)
                            for k, v in r.items()
                            if k not in ("panel", "symbol", "period", "regime", "bucket",
                                         "verdict", "classification")},
                "params": {"rule_hash": h, "panel": r.get("panel"),
                           "symbol": r.get("symbol"), "test_kind": kind,
                           "no_optimization": True},
                "provenance": f"scripts/failed_reversal_{'replication' if name in ('instruments',) else 'periods' if name in ('periods','eras','regimes','buckets') else 'friction'}.py",
                "stage": "rejected",
                "notes": str(r.get("verdict", r.get("classification", ""))),
                "verdict": {"metric": float(r["mean_1"]) if "mean_1" in r
                            and np.isfinite(r.get("mean_1", np.nan)) else None,
                            "t": float(r["t_1"]) if "t_1" in r
                            and np.isfinite(r.get("t_1", np.nan)) else None,
                            "threshold": 0.95, "trials": len(d), "passed": False,
                            "reason": "FAILED_REVERSAL_REPLICATION = REJECT"},
            })
    with LEDGER.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    print(f"appended {len(rows)} rows to {LEDGER.name}")

    reg = Registry()
    specs = [
        ("FR-1", "The failed-reversal effect is a repeatable market phenomenon",
         "the frozen rule shows positive signed forward return at 1/3/5 bars beating a "
         "matched control on more than one independent instrument or period",
         "the sign inverts on an independent instrument tracking the same index, or fails "
         "the clean holdout",
         [Stage.DISCOVERY, Stage.VALIDATION, Stage.REJECTED], False, None, "",
         {"rule_hash": h, "instruments": 8, "entries": 21776,
          "MNQ_1b": "+3.203 (t=2.48, 99.0 pctile, 343 entries)",
          "QQQ_1b": "-0.668 (t=-2.2, 0.5 pctile, 4124 entries) - SAME INDEX",
          "QQQ_futures_era": "-0.799 at 1b, -3.040 at 3b, -3.786 at 5b over the EXACT "
                             "same dates as MNQ",
          "instrument_years_replicating": "2 of 44",
          "clean_holdout_2016_2023": "QQQ negative, IWM negative, SPY +0.378 (t=1.32)",
          "after_costs": "7 of 8 NEGATIVE at every slippage level",
          "verdict": "REJECT - instrument/sample artifact, not a period effect"}),
        ("FR-2", "The 1-3-5 bar rise decaying by 10 replicates",
         "the decay shape appears on a majority of instruments",
         "instruments tracking the same index show opposite shapes",
         [Stage.DISCOVERY, Stage.REJECTED], False, "FR-1",
         "the shape is the mechanism's signature and was tested separately from the sign",
         {"consistent": "MNQ, MES, QQQ(negative), IWM, DIA",
          "NOT_consistent": "NQ and ES rise monotonically to 30 bars; SPY flat",
          "verdict": "MNQ and NQ are the same index and show different shapes"}),
        ("FR-3", "The S&P complex is weakly positive where the Nasdaq is negative",
         "SPY/ES show positive short-horizon effect while QQQ/NQ show negative",
         "not preregistered - EXPLORATORY ONLY, cannot support promotion",
         [Stage.PROPOSED], True, "FR-1",
         "noticed FROM the replication results; SPY +0.378 (95.3 pctile) over the clean "
         "holdout against QQQ -0.331 (20.7 pctile). Needs its own preregistration and its "
         "own holdout; must not inherit this study's evidence.",
         {}),
    ]
    added = 0
    for hid, title, pred, fals, stages, rd, parent, why, result in specs:
        if reg.get(hid):
            continue
        reg.preregister(Hypothesis(
            id=hid, title=title, mechanism_id="breakout.failed_reversal",
            prediction=pred, falsified_if=fals,
            instruments=("MNQ", "NQ", "MES", "ES", "SPY", "QQQ", "IWM", "DIA"),
            parent=parent, modification_reason=why if parent else "",
            result_driven=rd, prior_evidence=why,
            notes=f"rule hash {h}; see docs/FAILED_REVERSAL_REPLICATION.md"))
        for st in stages:
            reg.record(hid, stage=st, result=result if st == stages[-1] else {})
        added += 1
    print(f"registered {added} hypotheses")
    print(reg.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
