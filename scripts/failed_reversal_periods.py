"""Phases 3, 4, 8, 9: period replication, the honest holdout, regimes and session buckets.

THE DIAGNOSTIC THIS PHASE EXISTS FOR
--------------------------------------
Cross-instrument replication produced a contradiction that has to be resolved before anything
else means anything:

    MNQ  (Nasdaq futures, 2025-2026, 343 entries)   +3.203 at 1 bar, control percentile 99.0%
    QQQ  (Nasdaq ETF,     2016-2026, 4,124 entries) -0.668 at 1 bar, control percentile  0.5%

Same underlying index. Twelve times the entries. **Opposite sign, both significant.**

There are only two explanations and this module separates them:

    (a) A PERIOD effect. The mechanism is real in 2025-2026 and absent or inverted before it.
        Then QQQ restricted to 2025-2026 should agree with MNQ.
    (b) An INSTRUMENT or SAMPLE artifact. The MNQ result is a property of 343 entries over 71
        sessions and does not describe the Nasdaq at all. Then QQQ in 2025-2026 should still
        disagree, and the MNQ result is noise.

This is the single most informative test available and it is cheap, because the ETF panel
already spans both eras.

THE HOLDOUT, AND THE CONTAMINATION THAT IS NOT PRETENDED AWAY
---------------------------------------------------------------
The brief asks for discovery through 2023, replication 2024-2025, holdout 2026 YTD, and says
that if the genealogy has already contaminated 2024-2026 then to report that rather than
pretend.

It has. The futures window 2025-06 to 2026-09 has been inspected in five prior phases,
including the phase that produced this very hypothesis. It is **not** a holdout and is not
described as one.

What IS clean: ETF calendar years **2016 through 2023** have never been touched for this
mechanism. Those eight years are the legitimate holdout, and because the hypothesis was
generated on 2025-2026 futures they are genuinely out of sample in the only sense that
matters - they could not have influenced the rule.

So the split used is the reverse of the brief's suggested one, and deliberately:

    HYPOTHESIS-GENERATING (contaminated) : futures 2025-06 .. 2026-09
    LEGITIMATE HOLDOUT (never inspected) : ETF 2016-01 .. 2023-12
    PARTIALLY TOUCHED                    : ETF 2024-01 .. 2026-09 (one preregistered bucket
                                           test in an earlier phase, different question)

REGIMES AND BUCKETS ARE DESCRIPTIVE ONLY
------------------------------------------
Phases 8 and 9 are explicitly not a filter search. Three volatility terciles from the
established trailing definition, and coarse session buckets declared in advance. The question
is only whether the effect is broad or concentrated in one narrow slice - a fragility check,
not a conditioning opportunity. No filter is introduced.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from failed_reversal_replication import (HORIZONS, MIN_ENTRIES, TRAIN_FRACTION,  # noqa: E402
                                         build, calibrate_thresholds, classify,
                                         collect, etf_sessions, futures_sessions,
                                         matched_control, summarise)
from failed_reversal_spec import rule_hash  # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst  # noqa: E402

ETF_MULT = 100.0

#: Declared before running. Coarse, and chosen to be interpretable rather than fine.
SESSION_BUCKETS = (("10:15-11:00", 45, 90), ("11:00-12:30", 90, 180),
                   ("12:30-14:00", 180, 270), ("14:00-16:00", 270, 391))


def main() -> int:
    rng = np.random.default_rng(31415)
    print("=" * 112)
    print(f"PERIOD REPLICATION AND ROBUSTNESS   rule hash {rule_hash()}")
    print("=" * 112)

    panels = {}
    for sym in ("SPY", "QQQ", "IWM", "DIA"):
        sess = etf_sessions(sym)
        feats = build(sess)
        hi, lo = calibrate_thresholds(feats, int(len(sess) * TRAIN_FRACTION))
        recs, per_sess = collect(sess, feats, hi, lo, ETF_MULT)
        panels[("etf", sym)] = (recs, per_sess, sess, ETF_MULT)
    for sym in ("MNQ", "NQ", "MES", "ES"):
        sess = futures_sessions(sym)
        feats = build(sess)
        hi, lo = calibrate_thresholds(feats, int(len(sess) * TRAIN_FRACTION))
        mult = inst.get(sym).spec.multiplier
        recs, per_sess = collect(sess, feats, hi, lo, mult)
        panels[("futures", sym)] = (recs, per_sess, sess, mult)

    # ---------------- Phase 3: calendar periods -------------------------------------------
    rows = []
    print("\n" + "=" * 112)
    print("PHASE 3 - CALENDAR-PERIOD REPLICATION")
    print("=" * 112)
    print("  futures 2018-2024 are IMPOSSIBLE: the store begins 2025-06-08.\n")
    print(f"  {'panel':8} {'sym':5} {'year':6} {'n':>6} {'1b':>9} {'t':>6} {'3b':>9} "
          f"{'5b':>9} {'ctl%1b':>8}  verdict")
    for (panel, sym), (recs, per_sess, sess, mult) in panels.items():
        if not len(recs):
            continue
        r = recs.copy()
        r["year"] = pd.to_datetime(r["session"]).dt.year
        for yr, g in r.groupby("year"):
            if len(g) < 30:
                rows.append({"panel": panel, "symbol": sym, "period": str(yr),
                             "entries": len(g), "verdict": "INSUFFICIENT"})
                print(f"  {panel:8} {sym:5} {yr:6d} {len(g):6d} "
                      + " " * 44 + "INSUFFICIENT")
                continue
            ctrl = matched_control(g, per_sess, mult, rng, n_reps=100)
            row = summarise(g, ctrl, rng, str(yr), sym, panel)
            row["verdict"] = classify(row)
            rows.append(row)
            print(f"  {panel:8} {sym:5} {yr:6d} {int(row['entries']):6d} "
                  f"{row['mean_1']:9.3f} {row['t_1']:6.2f} {row['mean_3']:9.3f} "
                  f"{row['mean_5']:9.3f} {row['ctrl_pctile_1']:8.1%}  {row['verdict']}")
    pd.DataFrame(rows).to_csv(REPO / "research" / "fr_replication_periods.csv", index=False)

    # ---------------- Phase 4: the decisive era test ---------------------------------------
    print("\n" + "=" * 112)
    print("PHASE 4 - THE DECISIVE TEST: is the MNQ result a PERIOD effect or an ARTIFACT?")
    print("=" * 112)
    print("  If the mechanism is real in 2025-2026, QQQ restricted to those dates must agree")
    print("  with MNQ. If it still disagrees, the MNQ result does not describe the Nasdaq.\n")
    print(f"  {'series':38} {'n':>6} {'1b':>9} {'t':>6} {'3b':>9} {'5b':>9} {'ctl%1b':>8}")
    era_rows = []
    for (panel, sym), (recs, per_sess, sess, mult) in panels.items():
        if sym not in ("QQQ", "SPY", "MNQ", "NQ", "MES", "ES") or not len(recs):
            continue
        r = recs.copy()
        r["d"] = pd.to_datetime(r["session"])
        segs = [("2016-2023 (clean holdout)", r[r.d < "2024-01-01"]),
                ("2024-2026", r[r.d >= "2024-01-01"]),
                ("2025-06..2026-09 (futures era)",
                 r[(r.d >= "2025-06-08") & (r.d <= "2026-09-10")])]
        for label, g in segs:
            if len(g) < MIN_ENTRIES:
                continue
            ctrl = matched_control(g, per_sess, mult, rng, n_reps=150)
            row = summarise(g, ctrl, rng, label, sym, panel)
            row["verdict"] = classify(row)
            era_rows.append(row)
            print(f"  {sym + ' ' + label:38} {int(row['entries']):6d} {row['mean_1']:9.3f} "
                  f"{row['t_1']:6.2f} {row['mean_3']:9.3f} {row['mean_5']:9.3f} "
                  f"{row['ctrl_pctile_1']:8.1%}")
    pd.DataFrame(era_rows).to_csv(REPO / "research" / "fr_replication_eras.csv", index=False)

    # ---------------- Phase 8: volatility regimes -------------------------------------------
    print("\n" + "=" * 112)
    print("PHASE 8 - VOLATILITY REGIME (descriptive; no filter is introduced)")
    print("=" * 112)
    reg_rows = []
    print(f"  {'panel':8} {'sym':5} {'regime':8} {'n':>6} {'1b':>9} {'t':>6} {'5b':>9}")
    for (panel, sym), (recs, per_sess, sess, mult) in panels.items():
        if not len(recs):
            continue
        rng_by_day = {}
        for g in sess:
            c = g["c"].to_numpy(dtype=float)
            rng_by_day[g["day"].iloc[0] if "day" in g.columns else g["t"].iloc[0].date()] = (
                float(np.abs(np.diff(c)).sum()) / c[0] * 100.0 if c[0] else np.nan)
        ser = pd.Series(rng_by_day).sort_index()
        trail = ser.shift(1).rolling(20).mean()
        q1, q2 = trail.quantile(1 / 3), trail.quantile(2 / 3)
        lab = pd.Series(np.where(trail <= q1, "LOW",
                                 np.where(trail >= q2, "HIGH", "MID")), index=ser.index)
        r = recs.copy()
        r["regime"] = r["session"].map(lab)
        for reg in ("LOW", "MID", "HIGH"):
            g = r[r.regime == reg]
            if len(g) < 50:
                continue
            v = g["fwd_1"].to_numpy(dtype=float)
            v = v[np.isfinite(v)]
            t = (v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))) if v.std(ddof=1) > 0 else np.nan
            reg_rows.append({"panel": panel, "symbol": sym, "regime": reg, "n": len(g),
                             "mean_1": float(v.mean()), "t_1": float(t),
                             "mean_5": float(g["fwd_5"].mean())})
            print(f"  {panel:8} {sym:5} {reg:8} {len(g):6d} {v.mean():9.3f} {t:6.2f} "
                  f"{g['fwd_5'].mean():9.3f}")
    pd.DataFrame(reg_rows).to_csv(REPO / "research" / "fr_replication_regimes.csv",
                                  index=False)

    # ---------------- Phase 9: session buckets ----------------------------------------------
    print("\n" + "=" * 112)
    print("PHASE 9 - SESSION BUCKET (declared coarse buckets; fragility check only)")
    print("=" * 112)
    buck_rows = []
    print(f"  {'panel':8} {'sym':5} {'bucket':12} {'n':>6} {'1b':>9} {'t':>6}")
    for (panel, sym), (recs, per_sess, sess, mult) in panels.items():
        if not len(recs):
            continue
        for name, a, b in SESSION_BUCKETS:
            g = recs[(recs.bar >= a) & (recs.bar < b)]
            if len(g) < 50:
                continue
            v = g["fwd_1"].to_numpy(dtype=float)
            v = v[np.isfinite(v)]
            t = (v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))) if v.std(ddof=1) > 0 else np.nan
            buck_rows.append({"panel": panel, "symbol": sym, "bucket": name, "n": len(g),
                              "mean_1": float(v.mean()), "t_1": float(t)})
            print(f"  {panel:8} {sym:5} {name:12} {len(g):6d} {v.mean():9.3f} {t:6.2f}")
    pd.DataFrame(buck_rows).to_csv(REPO / "research" / "fr_replication_buckets.csv",
                                   index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
