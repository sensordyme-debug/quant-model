"""Phases 3, 4 and 8, with the overlap defect fixed: predictors never touch their own target.

THE DEFECT THIS MODULE EXISTS TO AVOID
----------------------------------------
The first pass at this search produced what looked like the best result in the entire research
programme: the absolute return of the first thirty minutes predicted the session's
maximum-favourable-excursion efficiency at rho between +0.235 and +0.357, t between 12 and 20,
replicating on all four ETFs and in a held-out window.

It is an accounting identity. `eff_mfe` is measured over the WHOLE session, and the first
thirty minutes are part of the whole session. If the open runs 0.5% in one direction, then the
session high is already at least 0.5% above the open, so the numerator of MFE/range is
partly the predictor itself.

Measured on the session AFTER minute thirty, the same relationship is:

    SPY  +0.010 (t=+0.53)      IWM  -0.023 (t=-1.18)
    QQQ  +0.028 (t=+1.47)      DIA  +0.015 (t=+0.77)

Nothing. The quintile table shows the mechanism plainly: whole-session eff_mfe climbs from
0.748 to 0.883 across opening-move quintiles while remainder-of-session eff_mfe stays flat at
0.770 to 0.797.

This is not a subtle statistical point. It is the difference between a discovery and a
tautology, and it would have been the headline of this report.

THE RULE APPLIED HERE
---------------------
A predictor observed over [0, w) may only be scored against a target measured over [w, end].
Concretely:

    pre-open predictors    (overnight, gap, prior session, trailing states)
                           -> whole-session targets are fine; no overlap exists
    opening predictors     (open1, open5, open15, open30)
                           -> ONLY rest-of-session targets, matched window for window

The matching is enforced in code rather than left to the caller, and
`tests/test_efficiency.py` asserts that an opening predictor scored against a whole-session
target is rejected.

WHAT REMAINS TO BE FOUND
------------------------
With the identity removed, the honest question is whether the first w minutes say anything
about the REMAINING session's directional efficiency. That is a real question with a real
mechanism behind it - an opening drive that holds is different from one that fails - and it is
the last place in this brief where a directional signal could be hiding.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from efficiency_search import add_derived, bonf  # noqa: E402
from efficiency_volatility import prepare, spearman  # noqa: E402

SPLIT = 0.70
WINDOWS = (1, 5, 15, 30)

#: Predictors observed strictly before 09:30. Safe against whole-session targets.
PRE_OPEN = ("gap_pct", "abs_gap_pct", "prev_ret_pct", "prev_range_pct", "prev_rv_pct",
            "prev_eff_range", "prev_eff_vol", "prev_closeloc", "prev_n_turns",
            "prev_streak", "trail_eff_5", "trail_eff_20", "eff_state", "trail_rv_5",
            "trail_rv_20", "vol_state", "fc_vol")
FUTURES_PRE = ("on_ret_pct", "on_abs_ret_pct", "on_range_pct", "on_atr_pct", "on_rv_pct",
               "on_closeloc", "on_upper_wick", "on_lower_wick", "on_eff",
               "on_range_over_prev", "on_vol_ratio")

#: Observed during [0, w). Scored ONLY against rest-of-session targets.
#: `vol_share` is DELIBERATELY ABSENT. It divides by the day's total volume, which is not
#: known at minute w, and an earlier pass of this study produced a result that replicated on
#: all four ETFs at |t| up to 9.7 purely from that leak. `vol_rel` is the causal replacement:
#: the same window's volume against its own trailing 20-day mean.
OPENING_KEYS = ("ret_pct", "absret_pct", "range_pct", "closeloc", "vol_rel")

WHOLE_TARGETS = ("eff_range", "eff_mfe")
REST_TARGETS = ("eff_range", "eff_mfe", "eff_vol")


def overlaps(predictor: str, target: str) -> bool:
    """True when the predictor's window is inside the target's window.

    The guard the first pass lacked. An `openW_*` predictor overlaps any whole-session target
    and any `restV_*` target with V < W.
    """
    if not predictor.replace("fc_vol x ", "").startswith("open"):
        return False
    pw = int(predictor.replace("fc_vol x ", "")[4:].split("_")[0])
    if not target.startswith("rest"):
        return True
    tw = int(target[4:].split("_")[0])
    return tw < pw


def run(p: pd.DataFrame, pre: tuple[str, ...], label: str, min_n: int) -> pd.DataFrame:
    rows = []
    for sym, g in p.groupby("symbol"):
        g = g.sort_values("tdate").reset_index(drop=True)
        cut = int(len(g) * SPLIT)
        search, hold = g.iloc[:cut], g.iloc[cut:]

        pairs: list[tuple[str, str]] = []
        for pr in pre:
            if pr in g.columns:
                pairs += [(pr, t) for t in WHOLE_TARGETS if t in g.columns]
                # a pre-open predictor may also be scored against the remainder
                pairs += [(pr, f"rest{w}_{t}") for w in WINDOWS for t in REST_TARGETS
                          if f"rest{w}_{t}" in g.columns]
        for w in WINDOWS:
            for k in OPENING_KEYS:
                pr = f"open{w}_{k}"
                if pr not in g.columns:
                    continue
                pairs += [(pr, f"rest{w}_{t}") for t in REST_TARGETS
                          if f"rest{w}_{t}" in g.columns]

        for pr, tgt in pairs:
            assert not overlaps(pr, tgt), f"overlap slipped through: {pr} -> {tgt}"
            for kind, xs, xh in (
                    ("main", search[pr].to_numpy(dtype=float),
                     hold[pr].to_numpy(dtype=float)),
                    ("interaction",
                     (search[pr] * search["fc_vol"]).to_numpy(dtype=float),
                     (hold[pr] * hold["fc_vol"]).to_numpy(dtype=float))):
                if kind == "interaction" and pr == "fc_vol":
                    continue
                rs, ts, ns = spearman(xs, search[tgt].to_numpy(dtype=float))
                rh, th, nh = spearman(xh, hold[tgt].to_numpy(dtype=float))
                if ns < min_n:
                    continue
                rows.append({
                    "panel": label, "symbol": sym,
                    "predictor": pr if kind == "main" else f"fc_vol x {pr}",
                    "target": tgt, "kind": kind,
                    "pred_family": ("opening" if pr.startswith("open")
                                    else "overnight" if pr.startswith("on_")
                                    else "prior RTH"),
                    "rho_search": rs, "t_search": ts, "n_search": ns,
                    "rho_hold": rh, "t_hold": th, "n_hold": nh})
    return pd.DataFrame(rows)


def main() -> int:
    etf = add_derived(
        prepare(pd.read_parquet(REPO / "research" / "efficiency_etf.parquet"), "etf"), "etf")
    fut = add_derived(
        prepare(pd.read_parquet(REPO / "research" / "efficiency_futures.parquet"),
                "futures"), "futures")

    out = pd.concat([run(etf, PRE_OPEN, "ETF", 120),
                     run(fut, PRE_OPEN + FUTURES_PRE, "FUTURES", 100)],
                    ignore_index=True).dropna(subset=["t_search"])
    out.to_csv(REPO / "research" / "efficiency_search_clean.csv", index=False)

    n = len(out)
    t_bar = bonf(n)
    out["replicates"] = ((np.sign(out.rho_hold) == np.sign(out.rho_search))
                         & (out.t_hold.abs() > 1.96) & (out.t_search.abs() > t_bar))

    print("=" * 108)
    print("PHASES 3, 4 AND 8 - NON-OVERLAPPING SEARCH")
    print(f"{n} tests, all window-matched. Bonferroni |t| > {t_bar:.2f}. "
          f"Search first {SPLIT:.0%}, holdout last {1 - SPLIT:.0%}.")
    print("=" * 108)

    print(f"\n  clearing nominal |t| > 1.96 in search   {int((out.t_search.abs() > 1.96).sum())} "
          f"(expected by chance {n * 0.05:.0f})")
    print(f"  clearing Bonferroni in search           {int((out.t_search.abs() > t_bar).sum())}")
    print(f"  AND replicating in the holdout          {int(out.replicates.sum())}")

    print("\n--- STRONGEST CANDIDATES, WINDOW-MATCHED " + "-" * 63)
    print(f"{'panel':7} {'sym':5} {'predictor':26} {'target':18} {'kind':11} "
          f"{'rho_s':>7} {'t_s':>7} {'rho_h':>7} {'t_h':>7}  verdict")
    top = out.reindex(out.t_search.abs().sort_values(ascending=False).index).head(20)
    for _, r in top.iterrows():
        same = np.sign(r.rho_hold) == np.sign(r.rho_search)
        v = ("REPLICATES" if r.replicates else "same sign, weak" if same else "SIGN FLIPS")
        print(f"{r['panel']:7} {r['symbol']:5} {r['predictor'][:26]:26} {r['target'][:18]:18} "
              f"{r['kind']:11} {r['rho_search']:+7.3f} {r['t_search']:+7.2f} "
              f"{r['rho_hold']:+7.3f} {r['t_hold']:+7.2f}  {v}")

    print("\n--- BY PREDICTOR FAMILY " + "-" * 80)
    print(f"  {'family':12} {'tests':>6} {'|t_s|>1.96':>11} {'expected':>9} "
          f"{'Bonferroni':>11} {'replicating':>12} {'median |rho|':>13}")
    for f, g in out.groupby("pred_family"):
        print(f"  {f:12} {len(g):6d} {int((g.t_search.abs() > 1.96).sum()):11d} "
              f"{len(g) * 0.05:9.0f} {int((g.t_search.abs() > t_bar).sum()):11d} "
              f"{int(g.replicates.sum()):12d} {g.rho_search.abs().median():13.3f}")

    print("\n--- THE PHASE 4 QUESTION: does conditioning on volatility rescue anything? "
          + "-" * 30)
    m = out[out.kind == "main"].set_index(["panel", "symbol", "predictor", "target"])
    i = out[out.kind == "interaction"]
    i = i.assign(base=i.predictor.str.replace("fc_vol x ", "", regex=False))
    joined = i.join(m["t_search"].rename("t_main"),
                    on=["panel", "symbol", "base", "target"])
    joined = joined.dropna(subset=["t_main"])
    better = (joined.t_search.abs() > joined.t_main.abs())
    print(f"  interaction beats its own main effect: {int(better.sum())} of {len(joined)} "
          f"({better.mean():.0%})")
    rescued = joined[(joined.t_main.abs() < 1.96) & (joined.t_search.abs() > t_bar)]
    print(f"  weak main effects RESCUED by conditioning (main <1.96, interaction >Bonferroni): "
          f"{len(rescued)}")
    if len(rescued):
        print(f"    of those, replicating in the holdout: {int(rescued.replicates.sum())}")
        for _, r in rescued[rescued.replicates].head(8).iterrows():
            print(f"      {r['panel']:7} {r['symbol']:5} {r['predictor'][:30]:30} "
                  f"-> {r['target'][:16]:16} t_s={r['t_search']:+.2f} t_h={r['t_hold']:+.2f}")

    print("\n--- REPLICATING CANDIDATES IN FULL " + "-" * 69)
    rep = out[out.replicates]
    if len(rep):
        for _, r in rep.sort_values("t_search", key=abs, ascending=False).iterrows():
            print(f"  {r['panel']:7} {r['symbol']:5} {r['predictor'][:30]:30} -> "
                  f"{r['target'][:18]:18} rho_s={r['rho_search']:+.3f} "
                  f"rho_h={r['rho_hold']:+.3f} t_h={r['t_hold']:+.2f}")
    else:
        print("  NONE. No window-matched predictor of directional efficiency clears the")
        print("  Bonferroni bar in the search window and replicates out of sample.")

    print(f"\nwrote {REPO / 'research' / 'efficiency_search_clean.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
