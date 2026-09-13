#!/usr/bin/env python
"""A-20: what does a size-scaled book actually HOLD, and does that explain A-18's rounding gap?

    py -3.14 scripts/sweep_a20.py --arms none            # ~15 min, 10 yearly jobs
    py -3.14 scripts/sweep_a20.py --arms const
    py -3.14 scripts/sweep_a20.py --arms sleeve
    py -3.14 scripts/sweep_a20.py --combine [--record]

THE ITEM
--------
A-18 split its harness-vs-linear gap into two channels and found the larger one - **+$69.35/day
(CONST) and +$41.19/day (SLEEVE)** - in the "share rounding + no-trade band" bucket. It then
INFERRED the mechanism: `floor()` makes a scaled book carry systematically less than k x its
target, because half a share is a larger fraction of a smaller position, and on a book that loses
money holding less is worth real dollars. The inference was forced, because `summarize()` reported
turnover and never exposure, so the one number that could confirm or refute it did not exist.

It also left A-17's control unverified in the same place. A-17 matched CONST and SLEEVE at the same
**intended** mean exposure M = 0.7702868307382554. If the two arms round away DIFFERENT amounts,
they are matched in intent and not in fact, and every "at the same average exposure" sentence
written about this sleeve needs the realized number beside it.

This item measures both. `scripts/intraday_backtest.py` now accumulates, per session:
    gross      mean realized |position| notional / equity over every marked bar
    gross_dec  the same, restricted to bars where the strategy was allowed to decide
    intent_dec mean `intended_gross(targets)` over those same bars - the gross the sizing step
               ASKED for, after the gross and per-symbol caps and before whole-share rounding
so realized and intended are averaged over the identical bar set and their ratio is the shortfall.

THE PRE-REGISTERED DESIGN, IN FULL, BEFORE ANY RUN
--------------------------------------------------
 0. NOTHING SHIPS. `live/intraday_config.json`, `live/APPROVED_PAPER.md`, `live/HALT*` and the
    scheduled tasks are not read or written. With --record this appends DIAGNOSTIC ledger rows.

 1. THE ARMS are A-18's, unchanged and re-run only because the exposure columns did not exist when
    A-18 ran: the deployed config on the Alpaca store, 2017..2026, each calendar year a fresh
    $1,000,000 book, differing only in the size schedule (`none` k=1.0; `const` k=M; `sleeve` k =
    A-17's SW_SLEEVE exposure), M and the 2,355-session scored window read from
    `results/a17/exposures.csv` and never recomputed. Output goes to `results/a20/`, so A-18's
    artefacts are left intact and the two are comparable file by file.

 2. IDENTITY, and it is the first thing that can void the run. A-20 added accumulation inside the
    bar loop. If it is inert, today's `none` arm reproduces `results/a18/daily_none.csv` on `pnl`,
    `ret`, `equity`, `low`, `trades` and `stopped` EXACTLY on all 2,434 sessions. Any difference
    means the instrumentation changed a decision and the run is void - reported, not explained away.

 3. THE HOLDING (the item's first deliverable). Per arm, bar-weighted over the 2,355 scored
    sessions: realized gross, intended gross, shortfall % = 100 x (1 - realized/intended), and the
    same by year. `none` is the k=1.0 reference the other two are measured against.

 4. IS THE MATCH REAL? (A-20 question (b).) A-17's control is matched on INTENT. Two readings:
      (i)  shortfall_CONST vs shortfall_SLEEVE, paired per session, mean difference with its t;
      (ii) the realized exposure RATIO r_arm = gross_dec_arm / gross_dec_none against k = M.
    Pre-registered: the control is NOT MATCHED IN FACT if |shortfall_CONST - shortfall_SLEEVE|
    >= 1.0 percentage point of intended gross, or the paired |t| >= 2.0 on a difference that also
    clears 0.25 points (a t alone on 2,355 sessions can resolve an economically dead number).

 5. DOES THE SHORTFALL EXPLAIN THE GAP? (A-20 question (a).) The linear scoring assumes the scaled
    book carries exactly k_t x what the unscaled book carries, i.e. r_t = k_t. It really carries
    r_t. P&L is first-order proportional to exposure, so
        gap_pred_t = (r_t - k_t) * pnl_none_t
    is the dollars per session that the exposure miss alone predicts. Compared against A-18's
    measured gap on A-18's OWN split - the "rounding + no-trade band" subset, i.e. every session
    EXCEPT one where the scaled book hit the daily loss limit and the linear scoring did not -
    reported as: mean actual, mean predicted, share explained, and an OLS of actual on predicted
    (slope, its t, R^2). The prediction is first-order and is not expected to be exact; the
    question is whether it carries the sign and the order of magnitude.

 6. VERDICT VOCABULARY, fixed in advance, two independent verdicts.
    On clause 5, over BOTH arms:
        EXPLAINED   predicted mean has the same sign as actual and covers >= 50% of it in both
        PARTIAL     same sign in both, < 50% in either
        REFUTED     opposite sign in either arm
    On clause 4:
        MATCHED-IN-FACT / NOT-MATCHED-IN-FACT by the clause 4 rule.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
# Must be set before intraday_common is imported (it reads the env var at import time) and it is
# inherited by the spawned workers, so every process in this sweep reads the same store.
os.environ.setdefault("INTRADAY_DATA_DIR", str(REPO_DIR / "data" / "minute_alpaca"))

import argparse  # noqa: E402
import datetime as dt  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import intraday_backtest as ib  # noqa: E402
from intraday_common import DATA_DIR, REPO, UNIVERSE, load_universe  # noqa: E402
from sweep_a12 import DEPLOYED  # noqa: E402
from sweep_a17 import EQUITY, REGIMES, table, tstat  # noqa: E402
from sweep_a18 import ARMS, YEARS, schedules  # noqa: E402

A18 = REPO / "results" / "a18"
OUT = REPO / "results" / "a20"
EXPERIMENTS = REPO / "research" / "experiments.jsonl"

#: A-18's measured gap on the rounding channel, $/day, for the record. Recomputed here from
#: A-18's own persisted series, never taken on trust.
A18_ROUNDING_GAP = {"const": 69.35, "sleeve": 41.19}
#: clause 4 thresholds
MATCH_PTS = 1.0
MATCH_PTS_MIN = 0.25
MATCH_T = 2.0
#: clause 6 threshold
EXPLAIN_SHARE = 50.0


# --------------------------------------------------------------------------------- worker
def _job(spec):
    """One (year, arm): load the year once and run the deployed config under its schedule."""
    year, arm, sched = spec
    lo, hi = dt.date(year, 1, 1), dt.date(year, 12, 31)
    bars = load_universe(UNIVERSE, lo, hi)
    if not bars:
        return year, arm, None
    sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
    from base import features
    feats = {s: features(df) for s, df in bars.items()}
    strat = ib.load_strategy("active")
    params = {**strat.PARAMS, **DEPLOYED}
    s = ib.run(strat, bars, EQUITY, params, lo, hi, False, feats_all=feats,
               size_schedule=sched, size_default=1.0)
    d = s.pop("daily")
    meta = {k: v for k, v in s.items() if k not in ("daily", "trades_log")}
    return year, arm, {"daily": d, "meta": meta}


def run_arms(arms: list[str], workers: int) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sched, m, days = schedules()
    print(f"store: {DATA_DIR}")
    print(f"arms: {arms}   matched exposure M = {m:.10f}   scored window "
          f"{days[0]} .. {days[-1]} ({len(days)} sessions)")
    jobs = [(y, a, sched[a]) for a in arms for y in YEARS]
    got: dict[str, dict[int, dict]] = {a: {} for a in arms}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for year, arm, out in ex.map(_job, jobs):
            if out is None:
                print(f"  {year} {arm}: no bars", flush=True)
                continue
            got[arm][year] = out
            d, mt = out["daily"], out["meta"]
            print(f"  {year} {arm:6s}: {len(d):3d} sessions  $/day {d['pnl'].mean():>8,.0f}  "
                  f"gross {mt['gross_realized_x']:.4f} / intent {mt['gross_intended_x']:.4f}  "
                  f"shortfall {mt['gross_shortfall_pct']:5.2f}%", flush=True)
    for arm in arms:
        if not got[arm]:
            sys.exit(f"no results for arm {arm}")
        d = pd.concat([got[arm][y]["daily"] for y in sorted(got[arm])],
                      ignore_index=True).sort_values("day").reset_index(drop=True)
        d.to_csv(OUT / f"daily_{arm}.csv", index=False)
        meta = {str(y): got[arm][y]["meta"] for y in sorted(got[arm])}
        (OUT / f"meta_{arm}.json").write_text(json.dumps(meta, indent=1, default=str),
                                              encoding="utf-8")
        print(f"[out] {OUT / f'daily_{arm}.csv'}  {len(d)} sessions")
    return 0


# --------------------------------------------------------------------------------- analysis
def load_arm(arm: str, where: Path = OUT) -> pd.DataFrame:
    f = where / f"daily_{arm}.csv"
    if not f.exists():
        sys.exit(f"missing {f} - run `py -3.14 scripts/sweep_a20.py --arms {arm}` first")
    d = pd.read_csv(f)
    d["day"] = pd.to_datetime(d["day"]).dt.date
    return d.sort_values("day").reset_index(drop=True)


def pooled(d: pd.DataFrame) -> dict:
    """Bar-weighted exposure over a set of sessions, the same weighting `summarize` uses."""
    nb, nd = d["bars"].sum(), d["dec_bars"].sum()
    real = float((d["gross"] * d["bars"]).sum() / nb) if nb else float("nan")
    rdec = float((d["gross_dec"] * d["dec_bars"]).sum() / nd) if nd else float("nan")
    intent = float((d["intent_dec"] * d["dec_bars"]).sum() / nd) if nd else float("nan")
    return {"gross_held_x": real, "gross_held_decision_x": rdec, "gross_intended_x": intent,
            "shortfall_%": 100.0 * (1.0 - rdec / intent) if intent else float("nan")}


def combine(args) -> int:
    sched, m, days = schedules()
    dayset = set(days)
    arms = {a: load_arm(a) for a in ARMS}

    # -------------------------------------------------- clause 2: identity against A-18's arms
    id_rows = []
    for a in ARMS:
        old = load_arm(a, A18)
        j = arms[a].merge(old, on="day", how="inner", suffixes=("_new", "_old"))
        row = {"arm": a, "shared_sessions": len(j)}
        bad = 0
        for c in ("pnl", "ret", "equity", "low", "trades"):
            dv = (j[f"{c}_new"].astype(float) - j[f"{c}_old"].astype(float)).abs()
            row[f"max_abs_d_{c}"] = float(dv.max())
            bad += int((dv > 0).sum())
        row["stopped_differing"] = int((j["stopped_new"].astype(bool)
                                        != j["stopped_old"].astype(bool)).sum())
        row["cells_differing"] = bad + row["stopped_differing"]
        id_rows.append(row)
    ids = table(id_rows, "CLAUSE 2 - IDENTITY: A-20's instrumented harness against A-18's arms",
                "the exposure columns must be pure accumulation; any non-zero cell voids the run")
    ids.to_csv(OUT / "identity.csv", index=False)
    void = int(ids["cells_differing"].sum())
    if void:
        print(f"\n*** RUN VOID: {void} differing cells. The A-20 accumulation changed a decision; "
              f"nothing below is a measurement of A-18's book. ***")

    # ------------------------------------------------------------------- align the scored window
    for a in ARMS:
        d = arms[a]
        arms[a] = d[d["day"].isin(dayset)].reset_index(drop=True)
    base = arms["none"]
    if len(base) != len(days):
        sys.exit(f"scored window mismatch: harness has {len(base)} of {len(days)} sessions")
    for a in ARMS:
        if not (arms[a]["day"].to_numpy() == base["day"].to_numpy()).all():
            sys.exit(f"arm {a} does not cover the same sessions as `none`")
    k = {a: np.array([sched[a][d] for d in base["day"]]) for a in ARMS}
    years = np.array([d.year for d in base["day"]])
    pnl0 = base["pnl"].to_numpy()

    # ---------------------------------------------------------------- clause 3: THE HOLDING
    hold_rows = []
    for a in ARMS:
        r = {"arm": a, "mean_k": float(k[a].mean()), **pooled(arms[a])}
        r["held_vs_none_ratio"] = (pooled(arms[a])["gross_held_decision_x"]
                                   / pooled(base)["gross_held_decision_x"])
        r["ratio_minus_k"] = r["held_vs_none_ratio"] - r["mean_k"]
        hold_rows.append(r)
    holds = table(hold_rows, "CLAUSE 3 - what each arm actually HOLDS, bar-weighted, 2,355 sessions",
                  "held_vs_none_ratio is the realized exposure the linear scoring assumes equals k")
    holds.to_csv(OUT / "holding.csv", index=False)

    yr_rows = []
    for y in sorted(set(years.tolist())):
        sel = years == y
        if sel.sum() < 60:
            continue
        row = {"year": int(y), "n": int(sel.sum())}
        for a in ARMS:
            row[f"{a}_shortfall_%"] = pooled(arms[a][sel])["shortfall_%"]
        yr_rows.append(row)
    yrs = table(yr_rows, "CLAUSE 3 - rounding shortfall by year, all three arms (descriptive)")
    yrs.to_csv(OUT / "shortfall_years.csv", index=False)

    # ---------------------------------------------------------------- clause 4: is the match real?
    sf = {a: (1.0 - arms[a]["gross_dec"] / arms[a]["intent_dec"]).to_numpy() * 100.0 for a in ARMS}
    dsf = sf["const"] - sf["sleeve"]
    mu_d, se_d, t_d = tstat(dsf[np.isfinite(dsf)])
    pooled_d = pooled(arms["const"])["shortfall_%"] - pooled(arms["sleeve"])["shortfall_%"]
    match_rows = [{"reading": "shortfall CONST - SLEEVE (pooled, bar-weighted)", "value_pts": pooled_d,
                   "se": float("nan"), "t": float("nan")},
                  {"reading": "shortfall CONST - SLEEVE (paired per session)", "value_pts": mu_d,
                   "se": se_d, "t": t_d}]
    for a in ("const", "sleeve"):
        h = [r for r in hold_rows if r["arm"] == a][0]
        match_rows.append({"reading": f"realized exposure ratio {a} minus k",
                           "value_pts": 100.0 * h["ratio_minus_k"], "se": float("nan"),
                           "t": float("nan")})
    matches = table(match_rows, "CLAUSE 4 - is A-17's matched-exposure control matched IN FACT?",
                    f"NOT MATCHED if |pooled diff| >= {MATCH_PTS} pts, or |t| >= {MATCH_T} with "
                    f"|diff| >= {MATCH_PTS_MIN} pts")
    matches.to_csv(OUT / "match.csv", index=False)
    not_matched = (abs(pooled_d) >= MATCH_PTS
                   or (abs(t_d) >= MATCH_T and abs(mu_d) >= MATCH_PTS_MIN))
    match_verdict = "NOT-MATCHED-IN-FACT" if not_matched else "MATCHED-IN-FACT"

    # ------------------------------------------- clause 5: does the shortfall explain A-18's gap?
    # A-18's channel split, reproduced here from these arms: a session where the SCALED book
    # stopped and the linear scoring (k x the unscaled book's own low) did not is the loss-limit
    # channel; every other session is the rounding + no-trade-band channel.
    eqo = base["equity"].to_numpy() - base["pnl"].to_numpy()
    low0 = base["low"].to_numpy() / eqo - 1.0
    g0 = base["gross_dec"].to_numpy()
    exp_rows = []
    for a in ("const", "sleeve"):
        gap = (arms[a]["ret"].to_numpy() - k[a] * base["ret"].to_numpy()) * eqo
        st = arms[a]["stopped"].astype(bool).to_numpy()
        lin_st = (k[a] * low0) <= -0.025
        sel = ~(st & ~lin_st)                       # A-18's rounding + no-trade-band subset
        r = np.where(g0 > 0, arms[a]["gross_dec"].to_numpy() / np.where(g0 > 0, g0, 1.0), np.nan)
        pred = (r - k[a]) * pnl0
        ok = sel & np.isfinite(pred)
        act_mu = float(gap[sel].sum() / len(gap))         # contribution to the arm's mean $/day
        pred_mu = float(np.nan_to_num(pred[ok]).sum() / len(gap))
        x, y = pred[ok], gap[ok]
        xc = x - x.mean()
        slope = float((xc * (y - y.mean())).sum() / (xc * xc).sum()) if (xc * xc).sum() else np.nan
        resid = y - (y.mean() + slope * xc)
        se_b = float(np.sqrt((resid ** 2).sum() / (len(x) - 2) / (xc * xc).sum()))
        r2 = float(1.0 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum())
        exp_rows.append({"arm": a, "n_rounding_sessions": int(ok.sum()),
                         "mean_realized_ratio_r": float(np.nanmean(r[ok])),
                         "k": float(k[a].mean()),
                         "actual_gap_$/day": act_mu, "predicted_gap_$/day": pred_mu,
                         "share_explained_%": 100.0 * pred_mu / act_mu if act_mu else np.nan,
                         "ols_slope": slope, "ols_t": slope / se_b if se_b else np.nan, "r2": r2,
                         "a18_published_$/day": A18_ROUNDING_GAP[a]})
    exps = table(exp_rows, "CLAUSE 5 - does the exposure shortfall explain A-18's rounding gap?",
                 "predicted_t = (realized ratio - k) x the unscaled book's P&L; first order only")
    exps.to_csv(OUT / "explained.csv", index=False)

    reg_rows = []
    for name, lo, hi in REGIMES:
        sel = (years >= lo) & (years <= hi)
        if sel.sum() < 100:
            continue
        row = {"regime": name, "n": int(sel.sum())}
        for a in ARMS:
            row[f"{a}_shortfall_%"] = pooled(arms[a][sel])["shortfall_%"]
        reg_rows.append(row)
    regs = table(reg_rows, "CLAUSE 5 - shortfall by regime (context for the two-of-three rule)")
    regs.to_csv(OUT / "shortfall_regimes.csv", index=False)

    # ---------------------------------------------------------------- clause 6: the verdicts
    signs_ok = all((r["actual_gap_$/day"] > 0) == (r["predicted_gap_$/day"] > 0) for r in exp_rows)
    shares = [r["share_explained_%"] for r in exp_rows]
    if not signs_ok:
        verdict = "REFUTED"
    elif all(s >= EXPLAIN_SHARE for s in shares):
        verdict = "EXPLAINED"
    else:
        verdict = "PARTIAL"
    if void:
        verdict, match_verdict = "VOID", "VOID"
    print("\n=== VERDICT (clause 6 vocabulary)")
    for r in exp_rows:
        print(f"  {r['arm']:6s} actual {r['actual_gap_$/day']:+8.2f} $/day   "
              f"predicted {r['predicted_gap_$/day']:+8.2f}   "
              f"share {r['share_explained_%']:+7.1f}%   slope {r['ols_slope']:+.3f} "
              f"(t {r['ols_t']:+.1f}, R2 {r['r2']:.3f})")
    print(f"  mechanism: {verdict}")
    print(f"  A-17 control: {match_verdict}  (pooled diff {pooled_d:+.3f} pts, "
          f"paired {mu_d:+.3f} pts at t {t_d:+.2f})")
    out = {"verdict": verdict, "match_verdict": match_verdict, "identity_cells_differing": void,
           "holding": hold_rows, "explained": exp_rows,
           "match": {"pooled_diff_pts": pooled_d, "paired_pts": mu_d, "paired_t": t_d}}
    (OUT / "verdict.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")

    if args.record:
        record(hold_rows, exp_rows, verdict, match_verdict)
    print(f"\n[out] {OUT}")
    return 0


def record(hold_rows: list, exp_rows: list, verdict: str, match_verdict: str) -> None:
    """DIAGNOSTIC ledger rows. This study measures a harness column; it promotes nothing."""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=REPO,
                                capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        commit = ""
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    exp = {r["arm"]: r for r in exp_rows}
    lines = []
    for h in hold_rows:
        e = exp.get(h["arm"], {})
        lines.append({
            "ts": ts, "algorithm": "intraday/a20_exposure", "class": "intraday",
            "tag": f"A-20 realized vs intended gross, {h['arm']} arm - {verdict} (DIAGNOSTIC)",
            "commit": commit, "run_dir": str(OUT.relative_to(REPO)), "track": "intraday",
            "params": {"arm": h["arm"], "mean_k": round(float(h["mean_k"]), 6),
                       "size_schedule": "results/a17/exposures.csv"},
            "start": "2017-04-27", "end": "2026-09-09",
            "stats": {"Sessions": "2355",
                      "Gross Held X": f"{h['gross_held_x']:.4f}",
                      "Gross Intended X": f"{h['gross_intended_x']:.4f}",
                      "Rounding Shortfall Pct": f"{h['shortfall_%']:.3f}",
                      "Held Vs None Ratio": f"{h['held_vs_none_ratio']:.4f}",
                      "Ratio Minus K": f"{h['ratio_minus_k']:.4f}",
                      "Actual Gap USD Day": ("" if not e else f"{e['actual_gap_$/day']:.2f}"),
                      "Predicted Gap USD Day": ("" if not e else f"{e['predicted_gap_$/day']:.2f}"),
                      "Share Explained Pct": ("" if not e else f"{e['share_explained_%']:.1f}"),
                      "Verdict": verdict, "Control Verdict": match_verdict,
                      "Diagnostic": "true"}})
    with EXPERIMENTS.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, default=str) + "\n")
    print(f"[ledger] {len(lines)} DIAGNOSTIC rows -> {EXPERIMENTS}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arms", nargs="*", choices=ARMS, help="run these arms and persist them")
    ap.add_argument("--combine", action="store_true", help="analyse the three persisted arms")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC ledger rows")
    args = ap.parse_args()
    if args.arms:
        return run_arms(list(dict.fromkeys(args.arms)), args.workers)
    if args.combine:
        return combine(args)
    ap.error("pass --arms or --combine")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
