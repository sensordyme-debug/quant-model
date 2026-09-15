"""Write this study into the two ledgers, so the trials it spent are counted against future work.

WHY A NULL RESULT MUST BE LEDGERED
-----------------------------------
The multiplicity bar in `research/experiments_futures.jsonl` is computed from the number of
trials in a family. A study that runs 46 tests and finds nothing has still spent 46 looks at
the data, and if those looks are not recorded then the NEXT study on this data will compute
its threshold against a denominator that is too small and will pass something it should not.

Recording failures is therefore not bookkeeping. It is the thing that keeps the correction
honest, and it is the single easiest step to skip because nobody is excited about it.

TWO LEDGERS, TWO JOBS
---------------------
`experiments_futures.jsonl` records what was RUN: one row per test, with its metrics and its
verdict against the corrected threshold.

`research/hypotheses.jsonl`, via `quant_brain.research.genealogy`, records what was
BELIEVED and when. It carries the field the experiment ledger cannot: whether a hypothesis
was written before or after seeing the result it explains. The three second-generation
hypotheses from the failure analysis are registered as `result_driven=True`, which makes
every future descendant of them cost an extra trial - correctly, because they exist only
because of something this study saw.
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

FAMILY = "futures.overnight_rth.v1"
LEDGER = REPO / "research" / "experiments_futures.jsonl"


def _eid(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def main() -> int:
    from overnight_hypotheses import HYPOTHESES

    results = pd.read_csv(REPO / "research" / "overnight_hypotheses.csv")
    n_trials = len(results)
    # Bonferroni over the family, matching what the hypotheses module reported.
    t_bar = 3.40
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")

    rows = []
    for _, r in results.iterrows():
        h = next(x for x in HYPOTHESES if x.key == r["h"])
        passed = bool(abs(r["t"]) > t_bar and r["signed_ok"])
        rows.append({
            "created": now,
            "experiment_id": _eid(FAMILY, str(r["h"]), str(r["panel"]), str(r["sym"])),
            "family": FAMILY,
            "hypothesis": f"{r['h']}: {h.x} -> {h.y} on {r['sym']} "
                          f"({r['panel']}), predicted sign {'+' if h.sign > 0 else '-'}",
            "metrics": {
                "n": int(r["n"]), "pearson_r": float(r["r"]), "spearman_rho": float(r["rho"]),
                "ci_low": float(r["lo"]), "ci_high": float(r["hi"]),
                "sign_as_predicted": bool(r["signed_ok"]),
            },
            "params": {"x": h.x, "y": h.y, "panel": r["panel"], "symbol": r["sym"],
                       "predicted_sign": h.sign},
            "provenance": "scripts/overnight_hypotheses.py",
            "stage": "confirmed" if passed else "rejected",
            "notes": (f"|t|={abs(r['t']):.2f} vs Bonferroni {t_bar:.2f} over {n_trials} "
                      f"preregistered tests in family '{FAMILY}'. {h.mechanism}"),
            "verdict": {
                "metric": float(r["r"]), "t": float(r["t"]), "threshold": t_bar,
                "trials": n_trials, "passed": passed,
                "reason": (f"|t|={abs(r['t']):.2f} "
                           f"{'clears' if passed else 'does not clear'} {t_bar:.2f}"
                           + ("" if r["signed_ok"] else "; sign opposite to prediction")),
            },
        })

    with LEDGER.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print(f"appended {len(rows)} experiment rows to {LEDGER.name} (family {FAMILY})")
    print(f"  confirmed {sum(r['verdict']['passed'] for r in rows)}, "
          f"rejected {sum(not r['verdict']['passed'] for r in rows)}")

    # ---- the genealogy ------------------------------------------------------------------
    reg = Registry()
    added = 0
    for h in HYPOTHESES:
        hid = f"ON-{h.key}"
        if reg.get(hid):
            continue
        sub = results[results.h == h.key]
        best = sub.loc[sub["t"].abs().idxmax()] if len(sub) else None
        obj = Hypothesis(
            id=hid, title=h.title, mechanism_id=f"overnight.{h.key}",
            prediction=f"{h.x} predicts {h.y} with sign "
                       f"{'+' if h.sign > 0 else '-'} on ES/NQ/MES/MNQ",
            falsified_if=f"|t| below the family Bonferroni bar of {t_bar}, or the sign is "
                         f"opposite to the prediction, on a majority of instruments",
            instruments=("ES", "NQ", "MES", "MNQ"),
            prior_evidence=h.mechanism, result_driven=False,
            notes=f"tested on the {h.where} panel(s); see docs/OVERNIGHT_RTH_RESEARCH.md")
        reg.preregister(obj)
        if best is not None:
            passed = bool(abs(best["t"]) > t_bar and best["signed_ok"])
            reg.record(hid, stage=Stage.DISCOVERY,
                       result={"best_r": float(best["r"]), "best_t": float(best["t"]),
                               "symbol": str(best["sym"]), "panel": str(best["panel"]),
                               "passed_bonferroni": passed})
            if not passed:
                reg.record(hid, stage=Stage.REJECTED,
                           result={"reason": "did not clear the family Bonferroni bar"})
        added += 1

    # The second generation, from the failure analysis. These exist BECAUSE of what we saw,
    # so they are flagged and will cost their descendants an extra trial each.
    second = [
        ("ON-C2", "Volatility-scaled sizing beats fixed sizing at matched average exposure",
         "ON-C",
         "C and G forecast range at incremental out-of-sample R-squared 0.04-0.08 beyond "
         "yesterday, but the tercile GATE built on that forecast failed its matched-exposure "
         "control. Sizing is the other way to spend a range forecast and has not been tested.",
         "scaling contracts inversely to the forecast range produces a higher Combine pass "
         "rate than fixed sizing at the same average contract-days"),
        ("ON-S1", "The 15:10-16:00 settlement block has structure of its own",
         None,
         "It carries 10.58% of session volume, the heaviest quarter-hour of the day, it was "
         "excluded from all previous research on this repository, and overnight range "
         "predicts its magnitude at t=5.4. Nothing has characterised it directly.",
         "the 15:10-16:00 block has a directional or magnitude structure not explained by "
         "the rest of the session"),
        ("ON-P1", "Directional hypotheses should be screened on the ETF panel first",
         None,
         "The futures panel has a minimum detectable correlation of 0.111 at n=312; the ETF "
         "panel has 0.038 at n=2662 and is already local and free. Every directional null in "
         "this study is partly a power statement.",
         "a directional hypothesis rejected on the ETF panel at n=2662 will also be rejected "
         "on futures, making futures screening wasteful"),
    ]
    for hid, title, parent, why, prediction in second:
        if reg.get(hid):
            continue
        reg.preregister(Hypothesis(
            id=hid, title=title, mechanism_id="overnight.second_generation",
            prediction=prediction,
            falsified_if="the matched-exposure control is not cleared at the 95th percentile",
            instruments=("MES", "MNQ"), parent=parent,
            modification_reason=why if parent else "",
            result_driven=True, prior_evidence=why,
            notes="written after seeing this study's results; costs an extra trial"))
        added += 1

    print(f"\nregistered {added} hypotheses in {reg.path.name}")
    print(reg.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
