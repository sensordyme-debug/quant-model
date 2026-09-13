#!/usr/bin/env python
"""A-18: what is a persisted-series SIZING result worth once the harness scores it?

    py -3.14 scripts/sweep_a18.py --arms none            # ~20 min, 10 yearly jobs
    py -3.14 scripts/sweep_a18.py --arms const
    py -3.14 scripts/sweep_a18.py --arms sleeve
    py -3.14 scripts/sweep_a18.py --combine [--record]

THE ITEM
--------
Every A-15/A-17 sizing conclusion on this sleeve was scored by multiplying a PERSISTED daily P&L
series by a per-session multiplier k_t. A-17 named the reason that is not good enough:

  * it is exact for costs      - slippage is bps of notional, commission is per share, both linear;
  * it is exact for the signal - k scales targets and changes no decision the strategy makes;
  * it is NOT exact for two things the harness owns:
        (i)  whole-share ROUNDING at the sizing step, together with the MIN_CHANGE no-trade band,
             which is the nonlinearity neither A-15 nor A-17 has ever priced, and
        (ii) the daily loss limit, which is a LEVEL and so stops a scaled book on a different set
             of sessions (A-17 priced this one and found it inert for its passing arm: 0 stopped
             sessions, limit-aware re-score bit-identical).

AGENTS.md rule (c) requires OOS improvement IN THE HARNESS before `live/intraday_config.json`
moves, so A-17's passing arm cannot ship until it is run through the harness. The work is the
`--size-schedule` option on `scripts/intraday_backtest.py` (added by this item, inert when absent)
plus this script, which runs A-17's arms end to end and prints THE GAP between the two scorings.
That gap is the number that says how much every prior sizing conclusion on this sleeve is worth.

THE PRE-REGISTERED DESIGN, IN FULL, BEFORE ANY RUN
--------------------------------------------------
 0. NOTHING SHIPS. `live/intraday_config.json` is not read or written; no runner-loaded or
    scheduled file is touched. This item measures a harness bias; it does not promote an arm.
    With --record the script appends DIAGNOSTIC ledger rows and nothing else.

 1. THE ARMS. Three harness runs of the DEPLOYED config on the Alpaca store, years 2017..2026,
    each calendar year a fresh $1,000,000 book (A-8's convention, so the series is comparable to
    `results/a8/daily_control.csv`), differing only in the size schedule:
        none    k_t = 1.0 on every session
        const   k_t = M on A-17's 2,355 OOS sessions, 1.0 before them   [the flat comparator]
        sleeve  k_t = A-17's SW_SLEEVE exposure on those sessions, 1.0 before them
    M = 0.7702868307382554 is A-17's matched average exposure, read from
    `results/a17/exposures.csv` and not recomputed. Sessions before 2017-04-27 run at k = 1.0 in
    all three arms, so the three books are identical up to that date and diverge only inside the
    scored window.

 2. IDENTITY, and what a failure means. `none` must reproduce `results/a8/daily_control.csv` on
    every shared session. Two things can break it and they are DIFFERENT findings:
      (a) the `--size-schedule` code is not inert at k = 1.0 -> a bug in this item, and the run is
          void. Ruled out separately and exactly on 61 sessions before this script was written
          (`results/a18/smoke.log`: identical `daily` frame, identical summary, 0 differing keys);
      (b) the HARNESS changed since 2026-09-12 19:00, when `daily_control.csv` was written -
          AUD-07's calendar trim landed on 2026-09-13. Then `daily_control.csv` is stale and the
          gap measured against it would be part code drift, which would wreck the measurement.
    So the base for every linear scoring below is the FRESH `none` series, never the stored CSV.
    The comparison against the stored CSV is reported as clause 2 and is a statement about the
    ledger's reproducibility, not an input to the verdict.

 3. THE GAP, which is the deliverable. For each of `const` and `sleeve`, per session:
        gap_t = ret_harness_t - k_t * ret_none_t
    Reported as mean $/day with its t, sd, the largest |gap| in bps, the share of sessions where
    the two differ at all, and the differences in trade count, cost and stopped-session count.
    A gap that is large in the MEAN would say the linear scoring is biased; a gap that is large
    only in the SD would say it is noisy. Both are reported because they have different
    consequences for A-15/A-17.

 4. THE HEADLINE, RE-SCORED. A-17's pass condition, recomputed both ways on the same 2,355
    sessions, `sleeve` against `const`:
        ES5 cut %, q05 cut %, mean $/day difference and its t, max drawdown points
    (a) LINEAR - k_t * ret_none_t, exactly A-17's arithmetic;
    (b) HARNESS - the two harness runs.
    A 99% block bootstrap (whole sessions, blocks of 5, O-8/O-9/A-17's constants, imported from
    `sweep_a17`) is run on the harness cut, because a harness cut that no longer excludes zero is
    a different verdict from one that merely shrank.

 5. THE REGIME AND YEAR LEGS, inherited from A-17 rather than rediscovered. A-17's limit is that
    the effect is negative in 5 of 10 years and carried by 2018 and 2020. Both scorings are
    printed by regime (the standing two-of-three rule) and by year, so the question "does the
    harness change WHICH years work" is answerable and not merely asserted.

 6. VERDICT VOCABULARY, fixed in advance, on the ES5 cut of `sleeve` vs `const`:
        CONFIRMED   harness cut > 0, >= ECON_MATERIAL (5%), 99% CI excludes zero, and >= 2 of 3
                    regimes positive - i.e. A-17's claim survives its own pass rule in the harness
        WEAKENED    harness cut > 0 but one of those conditions fails
        OVERTURNED  harness cut <= 0
    Whatever the verdict, the GAP of clause 3 is the item's output: it is what every OTHER sizing
    result on this sleeve, scored the linear way, is exposed to.
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
from sweep_a17 import (BOOT_ALPHA, BOOT_BLOCK, ECON_MATERIAL, EQUITY, REGIMES,  # noqa: E402
                       RNG_SEED, bootstrap_cut, book_stats, es05, q05, table, tail_cut, tstat)

A8 = REPO / "results" / "a8"
A17 = REPO / "results" / "a17"
OUT = REPO / "results" / "a18"
EXPERIMENTS = REPO / "research" / "experiments.jsonl"

YEARS = list(range(2017, 2027))     # 2016 lies entirely before A-17's first OOS session
ARMS = ("none", "const", "sleeve")
#: A-17's headline, for the record and for the reader; recomputed here, never taken on trust.
A17_PUBLISHED = {"ES5_cut_%": 11.08, "max_dd_const_%": 53.41, "max_dd_sleeve_%": 42.32}


# --------------------------------------------------------------------------------- schedules
def schedules() -> tuple[dict[str, dict], float, list]:
    """The three size schedules, off A-17's persisted exposures. No fit is re-run here."""
    f = A17 / "exposures.csv"
    if not f.exists():
        sys.exit(f"missing {f} - run `py -3.14 scripts/sweep_a17.py` first")
    e = pd.read_csv(f)
    e["day"] = pd.to_datetime(e["day"]).dt.date
    days = list(e["day"])
    m = float(e["CONST"].iloc[0])
    if abs(e["CONST"].std(ddof=0)) > 1e-12:
        sys.exit("CONST is not flat in exposures.csv; A-17's comparator has changed")
    return ({"none": {d: 1.0 for d in days},
             "const": {d: m for d in days},
             "sleeve": dict(zip(days, e["SW_SLEEVE"].astype(float)))}, m, days)


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
    print(f"{len(YEARS)} yearly jobs x {len(arms)} arm(s), {workers} workers; each year is a "
          f"fresh ${EQUITY:,.0f} book")
    jobs = [(y, a, sched[a]) for a in arms for y in YEARS]
    got: dict[str, dict[int, dict]] = {a: {} for a in arms}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for year, arm, out in ex.map(_job, jobs):
            if out is None:
                print(f"  {year} {arm}: no bars", flush=True)
                continue
            got[arm][year] = out
            d = out["daily"]
            print(f"  {year} {arm:6s}: {len(d):3d} sessions  $/day {d['pnl'].mean():>8,.0f}  "
                  f"trades {out['meta']['trades']:>6,}  stops {out['meta']['stopped_days']}",
                  flush=True)
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
def load_arm(arm: str) -> pd.DataFrame:
    f = OUT / f"daily_{arm}.csv"
    if not f.exists():
        sys.exit(f"missing {f} - run `py -3.14 scripts/sweep_a18.py --arms {arm}` first")
    d = pd.read_csv(f)
    d["day"] = pd.to_datetime(d["day"]).dt.date
    return d.sort_values("day").reset_index(drop=True)


def meta_of(arm: str) -> dict:
    f = OUT / f"meta_{arm}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def combine(args) -> int:
    sched, m, days = schedules()
    dayset = set(days)
    arms = {a: load_arm(a) for a in ARMS}

    # ------------------------------------------------------ clause 2: identity against the ledger
    stored = pd.read_csv(A8 / "daily_control.csv")
    stored["day"] = pd.to_datetime(stored["day"]).dt.date
    j = arms["none"].merge(stored, on="day", how="inner", suffixes=("_new", "_old"))
    dp = (j["pnl_new"] - j["pnl_old"]).to_numpy()
    dr = (j["ret_new"] - j["ret_old"]).to_numpy()
    ndiff = int((np.abs(dr) > 1e-12).sum())
    table([{"shared_sessions": len(j), "sessions_differing": ndiff,
            "max_abs_d_pnl_$": float(np.abs(dp).max()), "mean_d_pnl_$": float(dp.mean()),
            "max_abs_d_ret_bps": float(np.abs(dr).max()) * 1e4,
            "new_$/day": float(j["pnl_new"].mean()), "stored_$/day": float(j["pnl_old"].mean())}],
          "CLAUSE 2 - today's k=1.0 harness against results/a8/daily_control.csv",
          "not an input to the verdict; the base below is the FRESH `none` series")
    if ndiff:
        print("    NOTE: the stored control is NOT reproducible with today's harness. That is a "
              "statement about the ledger, and it is exactly why clause 2 fixed the base in "
              "advance as the fresh run rather than the CSV.")

    # ------------------------------------------------------------------- align the scored window
    base = arms["none"]
    base = base[base["day"].isin(dayset)].reset_index(drop=True)
    if len(base) != len(days):
        sys.exit(f"scored window mismatch: harness has {len(base)} of {len(days)} sessions")
    k = {a: np.array([sched[a][d] for d in base["day"]]) for a in ARMS}
    ret0 = base["ret"].to_numpy()
    low0 = base["low"].to_numpy() / (base["equity"].to_numpy() - base["pnl"].to_numpy()) - 1.0
    eqo = base["equity"].to_numpy() - base["pnl"].to_numpy()
    years = np.array([d.year for d in base["day"]])

    lin = {a: k[a] * ret0 for a in ARMS}                       # A-17's arithmetic
    har = {}
    for a in ARMS:
        d = arms[a]
        d = d[d["day"].isin(dayset)].reset_index(drop=True)
        if not (d["day"].to_numpy() == base["day"].to_numpy()).all():
            sys.exit(f"arm {a} does not cover the same sessions as `none`")
        har[a] = d["ret"].to_numpy()
        arms[a] = d
    assert np.abs(har["none"] - lin["none"]).max() == 0.0, "`none` must be its own linear scoring"

    # ---------------------------------------------------------------- clause 3: THE GAP
    gap_rows = []
    for a in ("const", "sleeve"):
        g = har[a] - lin[a]
        gd = g * eqo
        mu, se, t = tstat(gd)
        n_tr_h = sum(v["trades"] for v in meta_of(a).values())
        n_tr_0 = sum(v["trades"] for v in meta_of("none").values())
        c_h = sum(v["costs_total"] for v in meta_of(a).values())
        c_0 = sum(v["costs_total"] for v in meta_of("none").values())
        gap_rows.append({
            "arm": a, "mean_k": float(k[a].mean()),
            "gap_$/day": mu, "se": se, "t": t,
            "gap_sd_$": float(gd.std(ddof=1)),
            "gap_max_abs_bps": float(np.abs(g).max()) * 1e4,
            "sessions_differing_%": float((np.abs(g) > 1e-12).mean() * 100),
            "trades_harness": n_tr_h, "trades_linear": int(round(n_tr_0 * float(k[a].mean()))),
            "trades_vs_none_%": 100.0 * (n_tr_h / n_tr_0 - 1.0),
            "costs_vs_linear_%": 100.0 * (c_h / (c_0 * float(k[a].mean())) - 1.0),
            "stops_harness": int(arms[a]["stopped"].astype(bool).sum()),
            "stops_linear": int(((k[a] * low0) <= -0.025).sum()),
        })
    table(gap_rows, "CLAUSE 3 - THE GAP: harness return minus k x persisted return, per session",
          "trades_linear is what the linear scoring implicitly assumes (k x the unscaled count)")
    pd.DataFrame(gap_rows).to_csv(OUT / "gap.csv", index=False)

    # 3b - WHICH channel. The two nonlinearities are separable on the data: a session where the
    # SCALED book stopped and the linear scoring did not is the loss-limit channel and nothing
    # else; every other session's gap is share rounding and the no-trade band. The split matters
    # because A-17 declared the loss-limit channel INERT (0 stopped sessions) using the unscaled
    # book's intraday low - a series already truncated by the unscaled book's OWN stop.
    chan_rows = []
    for a in ("const", "sleeve"):
        g = (har[a] - lin[a]) * eqo
        st = arms[a]["stopped"].astype(bool).to_numpy()
        lin_st = (k[a] * low0) <= -0.025
        only = st & ~lin_st
        for label, sel in (("loss-limit (scaled book stopped, linear did not)", only),
                           ("rounding + no-trade band (all other sessions)", ~only)):
            chan_rows.append({"arm": a, "channel": label, "n": int(sel.sum()),
                              "share_of_gap_$/day": float(g[sel].sum() / len(g)),
                              "mean_gap_on_these_$": float(g[sel].mean()) if sel.sum() else 0.0,
                              "max_abs_bps": (float(np.abs(har[a] - lin[a])[sel].max()) * 1e4
                                              if sel.sum() else 0.0)})
    chans = table(chan_rows, "CLAUSE 3b - which nonlinearity the gap comes from",
                  "share_of_gap is that channel's contribution to the arm's mean gap $/day")
    chans.to_csv(OUT / "gap_channels.csv", index=False)

    # ---------------------------------------------------------------- clause 4: the headline
    book_rows = []
    for how, series in (("linear", lin), ("harness", har)):
        for a in ARMS:
            b = book_stats(series[a] * eqo, series[a])
            book_rows.append({"scoring": how, "arm": a, "mean_k": float(k[a].mean()),
                              "$/day": b["$/day"], "se": b["se"], "sharpe": b["sharpe"],
                              "q05_%": b["q05_%"], "ES5_%": b["ES5_%"],
                              "max_dd_%": b["max_dd_%"], "worst_%": b["worst_%"]})
    books = table(book_rows, "CLAUSE 4 - the books, both scorings, same 2,355 sessions",
                  "`none` is context; every cut below is `sleeve` against `const`")
    books.to_csv(OUT / "books.csv", index=False)

    cut_rows = []
    for how, series in (("linear", lin), ("harness", har)):
        d = (series["sleeve"] - series["const"]) * eqo
        mu, se, t = tstat(d)
        dd_c = book_stats(np.zeros(len(eqo)), series["const"])["max_dd_%"]
        dd_s = book_stats(np.zeros(len(eqo)), series["sleeve"])["max_dd_%"]
        cut_rows.append({"scoring": how,
                         "ES5_cut_%": tail_cut(series["sleeve"], series["const"], es05),
                         "q05_cut_%": tail_cut(series["sleeve"], series["const"], q05),
                         "d_$/day": mu, "se_d": se, "t_d": t,
                         "max_dd_const_%": dd_c, "max_dd_sleeve_%": dd_s,
                         "d_max_dd_pts": dd_s - dd_c})
    cuts = table(cut_rows, "CLAUSE 4 - A-17's headline recomputed both ways",
                 f"A-17 published ES5 cut {A17_PUBLISHED['ES5_cut_%']:+.2f}%, max dd "
                 f"{A17_PUBLISHED['max_dd_const_%']:.2f} -> {A17_PUBLISHED['max_dd_sleeve_%']:.2f}")
    cuts.to_csv(OUT / "cuts.csv", index=False)

    boot_rows = []
    for how, series in (("linear", lin), ("harness", har)):
        b = bootstrap_cut(series["sleeve"], series["const"], np.random.default_rng(RNG_SEED))
        b["scoring"] = how
        boot_rows.append(b)
    boots = table(boot_rows, f"CLAUSE 4 - {100 * (1 - BOOT_ALPHA):.0f}% block bootstrap on the ES5 "
                             f"cut (whole sessions, block {BOOT_BLOCK})")
    boots.to_csv(OUT / "bootstrap.csv", index=False)

    # ---------------------------------------------------------------- clause 5: regimes and years
    reg_rows = []
    for name, lo, hi in REGIMES:
        sel = (years >= lo) & (years <= hi)
        if sel.sum() < 100:
            continue
        row = {"regime": name, "n": int(sel.sum())}
        for how, series in (("linear", lin), ("harness", har)):
            row[f"{how}_ES5_cut_%"] = tail_cut(series["sleeve"][sel], series["const"][sel], es05)
        reg_rows.append(row)
    regs = table(reg_rows, "CLAUSE 5 - ES5 cut by regime, both scorings (two-of-three rule)")
    regs.to_csv(OUT / "regimes.csv", index=False)

    yr_rows = []
    for y in sorted(set(years.tolist())):
        sel = years == y
        if sel.sum() < 60:
            continue
        row = {"year": int(y), "n": int(sel.sum())}
        for how, series in (("linear", lin), ("harness", har)):
            row[f"{how}_%"] = tail_cut(series["sleeve"][sel], series["const"][sel], es05)
        row["d_pts"] = row["harness_%"] - row["linear_%"]
        yr_rows.append(row)
    yrs = table(yr_rows, "CLAUSE 5 - ES5 cut year by year, both scorings (descriptive)")
    yrs.to_csv(OUT / "years.csv", index=False)

    # ---------------------------------------------------------------- clause 6: the verdict
    lin_row = cuts[cuts.scoring == "linear"].iloc[0]
    har_row = cuts[cuts.scoring == "harness"].iloc[0]
    har_boot = boots[boots.scoring == "harness"].iloc[0]
    n_reg = sum(1 for _, r in regs.iterrows() if r["harness_ES5_cut_%"] > 0)
    cut = float(har_row["ES5_cut_%"])
    if cut <= 0:
        verdict = "OVERTURNED"
    elif (cut >= ECON_MATERIAL and bool(har_boot["excludes_zero"]) and n_reg >= 2
            and float(har_row["q05_cut_%"]) > 0):
        verdict = "CONFIRMED"
    else:
        verdict = "WEAKENED"
    print("\n=== VERDICT (clause 6 vocabulary)")
    print(f"  linear  ES5 cut {float(lin_row['ES5_cut_%']):+7.2f}%   "
          f"harness ES5 cut {cut:+7.2f}%   gap {cut - float(lin_row['ES5_cut_%']):+7.2f} points")
    print(f"  harness CI [{float(har_boot['ci_lo_%']):+.2f}, {float(har_boot['ci_hi_%']):+.2f}]  "
          f"regimes {n_reg}/3  q05 cut {float(har_row['q05_cut_%']):+.2f}%")
    print(f"  {verdict}")
    out = {"verdict": verdict, "linear": lin_row.to_dict(), "harness": har_row.to_dict(),
           "harness_bootstrap": har_boot.to_dict(), "regimes_positive": n_reg,
           "gap": gap_rows, "published_a17": A17_PUBLISHED}
    (OUT / "verdict.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")

    if args.record:
        record(books, cuts, verdict, gap_rows)
    print(f"\n[out] {OUT}")
    return 0


def record(books: pd.DataFrame, cuts: pd.DataFrame, verdict: str, gap_rows: list) -> None:
    """DIAGNOSTIC ledger rows. No harness --tag run happens here; these describe THIS study."""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=REPO,
                                capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        commit = ""
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    gap = {g["arm"]: g for g in gap_rows}
    lines = []
    for _, r in books[books.scoring == "harness"].iterrows():
        g = gap.get(r["arm"], {})
        lines.append({
            "ts": ts, "algorithm": "intraday/a18_sizing", "class": "intraday",
            "tag": f"A-18 harness re-score of A-17's {r['arm']} arm - {verdict} (DIAGNOSTIC)",
            "commit": commit, "run_dir": str(OUT.relative_to(REPO)), "track": "intraday",
            "params": {"arm": r["arm"], "mean_k": round(float(r["mean_k"]), 6),
                       "scoring": "harness", "size_schedule": "results/a17/exposures.csv"},
            "start": "2017-04-27", "end": "2026-09-09",
            "stats": {"Sessions": "2355", "Avg Daily PnL": f"{r['$/day']:.0f}",
                      "Sharpe Ratio": f"{r['sharpe']:.3f}", "Drawdown": f"{r['max_dd_%']:.3f}%",
                      "ES5 pct": f"{r['ES5_%']:.4f}",
                      "Gap vs Linear USD Day": ("" if not g else f"{g['gap_$/day']:.1f}"),
                      "Verdict": verdict, "Diagnostic": "true"}})
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
