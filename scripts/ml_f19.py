"""F-19: every F-track panel was built from a tape that included bars after an early close.

D-6 (2026-09-13, `iterate`) closed AUD-07 and patched `intraday_common.load_bars` to drop rows the
exchange calendar says are not in that day's session. The patch landed at 04:04 today. Every store
this track has ever built predates it:

    data/f1/panel.parquet      2026-09-11 11:44
    data/f1/f14_flow.parquet   2026-09-12 22:41
    data/f1/f15_famA.parquet   2026-09-13 01:13
    data/f1/f15_famB.parquet   2026-09-13 01:07

So every F-track number from F-1 to F-17 was fitted on a panel that, on 21 half-day sessions, holds
up to 180 minutes of post-13:00 tape resampled by `to_5min` into 5-minute bars that never existed -
a window where 31.1% of minutes print at all and volume is 14.3% of normal (D-6 clause 3).

The contamination is NOT confined to those 21 days, and that is the reason this item is worth a
run rather than a one-line rebuild:

  (i)   FAKE DECISIONS.  Slots at 12:55, 13:25, 13:55, 14:25, 14:55 on a 13:00 close are decision
        rows built entirely from post-close prints.
  (ii)  CONTAMINATED LABELS.  The 12:25 decision fills at 12:30 and unwinds at the 13:00 open,
        which is the first post-close bar. `fwd` for a REAL row is read off a bar that does not
        exist. F-8's `y_close` chains `fwd` to the flatten, so on those sessions every earlier
        slot's `close` label inherits it.
  (iii) LEAKAGE FORWARD, the channel D-6 could not see from the store side.  `slot_volume_median`
        is a trailing 20-session median of the SAME time-of-day slot, so a fake 13:25 bar's volume
        enters `vol_rel` on the next 20 NORMAL sessions. `rvol_ratio` rolls 78 bars across the day
        boundary. `prev_ret` on the day after an early close reads the fake close. In family A,
        `last_c` is the session's last continuous bar - on an early close that is a post-market
        print - and it feeds `auc_cdrift` directly and `scale` (a trailing 20-session vol) for the
        next 20 sessions. `scale` is the denominator of `auc_ofade`, WHICH IS THE COLUMN F-16
        ADMITTED AND THE BEST NET THIS TRACK HAS FITTED.

21 of ~2,400 sessions is 0.9% of the rows. Through (iii) it is not 0.9% of the panel.

`--build` rebuilds the panel and both F-15 auction families through the patched loader into f19
paths, leaving the F-16/F-17 stores untouched so the comparison has a fixed reference.

PRE-REGISTERED CLAUSES (written before a number of this run was read; clause 0 is the prior).

0. THE PRIOR.  This is a correctness item, not an alpha item, and I expect it to change nothing
   that a decision rests on. Concretely: I expect the clean panel to lose 5,000-9,000 of ~1.2M
   rows (21 sessions x ~56 names x 5 fake slots, plus the labels in (ii)); I expect channel (iii)
   to touch far more rows than (i) and (ii) combined but at a magnitude too small to move a book;
   I expect `base` on the clean panel to land within $30/day of the frozen $305.7 with the same
   sign and the same 5/8 years; and I expect F-16's causal arm to stay REFUSED - its t was +1.97
   against a hurdle of 2.0, so a favourable half-percent of sessions could in principle flip it,
   which is exactly why this must be measured rather than assumed. The honest expected outcome is
   "the substrate was dirty, no conclusion moves, and every future F run reads a clean store".
   I name the one way this run would be interesting: if the causal arm crosses t 2.0 on clean
   data, a REFUSAL becomes an ADOPTION on a data fix, and clause 6 says what happens then.

1. PREMISE, and it must hold or there is nothing to fix.  The OLD panel must contain decision rows
   at or after the early close on the 21 D-6 sessions, and the NEW panel must contain none. Both
   counts are printed. If the old count is zero, F-19 is withdrawn, not "passed".

2. IDENTITY.  Re-simulating the FROZEN `f16_preds.parquet` through this run's own book code must
   reproduce `f16_arms.csv` to the cent for every arm. That is what makes the f19 numbers a
   comparison against F-16 rather than a second, differently-plumbed measurement. If it does not
   reproduce, the run is void.

3. PROPAGATION, the clause that decides whether this is a rebuild or a finding.  For rows present
   in BOTH panels on the SAME (ts, sym), count the rows where any modelling feature differs by
   more than 1e-6 relative, report the count per feature and the share of sessions touched, and do
   the same for family A. Pre-registered prediction from (iii): `vol_rel`, `vol_rel6` and
   `prev_ret` carry more changed rows than the 21 sessions can explain, and family A's changed
   rows outnumber 21 x 56 by roughly the 20-session `scale` window.

4. THE GATE, re-run.  F-16's causal q50 gate (`ml_f16.causal_gate`, unmodified) is re-run per test
   year on the CLEAN panel. Floors, candidate ICs and correlations are all recomputed, because a
   floor is a quantile of the incumbents' |IC| and the incumbents changed. The admitted sets are
   compared year by year with F-16's. A change in the admitted set is a RESULT, not a bug.

5. ARMS AND HURDLE, both unchanged.  `base`, `causal` (clause 4's sets), `causal_scrambled`
   (F-14 b: the gate runs on real data, the fit reads the admitted columns permuted within each
   timestamp). Adoption needs net t > 2.0 AND >= 5 of 8 test years positive AND paired
   `causal - base` at t > 2.0. Per F-17 (b) the abstention rate is pre-registered as an OUTCOME,
   and per F-17 (c) the scramble control's NET is printed next to base, not only its paired t.

6. WHAT THIS RUN IS ALLOWED TO DO.  It replaces `data/f1/panel.parquet`, `f15_famA.parquet` and
   `f15_famB.parquet` with the clean rebuilds IFF clauses 1 and 2 pass - that is a data-hygiene
   action and needs no hurdle. It does NOT revise any past F-track verdict unless a hurdle LEG
   flips, and if one does the honest reading is "F-16's result was a coin-flip on 0.9% of the
   sessions", which is a reason to distrust the arm, not to adopt it. Nothing is promoted,
   `champion.json` is untouched, and no shipped or runner-loaded file is modified, so no deploy
   gate and no `--replay` is owed.

7. SCOPE, stated so the gap is on the record.  `f14_flow.parquet` (F-14's 19 flow columns) is NOT
   rebuilt here. F-14 and F-17 both REFUSED the flow family, F-17 (4) measured it at -$101/day
   paired, and a cleaner tape does not rescue a family whose loss was traced to one regime break
   in 2020. If flow is ever reopened the store must be rebuilt first; that is carried as F-20.

Usage:
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f19.py --build
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f19.py --diff
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f19.py --gate
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f19.py --fit
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f19.py --books --record
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f19.py --install
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
import intraday_common as ic  # noqa: E402
import sweep_f1 as f1  # noqa: E402
import ml_f8 as f8  # noqa: E402
import ml_f14 as f14  # noqa: E402
import ml_f15 as f15  # noqa: E402
import ml_f16 as f16  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
OUT = REPO / "data" / "f1"

PANEL_NEW = OUT / "f19_panel.parquet"
#: clause 9: the same rebuild with the calendar trim OFF, which isolates AUD-20 from AUD-07
PANEL_SPAN = OUT / "f19_panel_spanonly.parquet"
FAMA_NEW = OUT / "f19_famA.parquet"
FAMB_NEW = OUT / "f19_famB.parquet"
GATE = OUT / "f19_gate.csv"
ADMIT = OUT / "f19_admitted.json"
PREDS = OUT / "f19_preds.parquet"
CELLS = OUT / "f19_arms.csv"
DIFF = OUT / "f19_diff.csv"

PANEL_OLD = f1.PANEL
FAMA_OLD = OUT / "f15_famA.parquet"
FAMB_OLD = OUT / "f15_famB.parquet"

EQUITY = f8.EQUITY
DECILE = f8.DECILE

#: clause 5: `causal` uses clause 4's per-year sets; `causal_scrambled` permutes them.
ARMS = {"base": (False, False), "causal": (True, False), "causal_scrambled": (True, True)}

REL_TOL = 1e-6          # clause 3: what counts as "the same number"


# ------------------------------------------------------------------------ clause 1 + 6: the build


def pin() -> tuple[list[str], str]:
    """The OLD panel's universe and last session - clause 8.

    Discovered mid-run and not anticipated by clause 0: the Alpaca store grew SIX symbols
    (DIA, GLD, TLT, XLE, XLF, XLK, added 2026-09-13 01:0x by another track) and one session
    (2026-09-11) after `panel.parquet` was built on 2026-09-11 11:44. A rebuild on the whole
    store would change the cross-section every row is ranked and demeaned against, and F-19
    would then be measuring the calendar trim AND a 62-name universe at once. The comparison
    panel is therefore pinned to the old panel's own 56 names and its own last day, so the
    only thing that differs is the trim. The wider store is a separate question and is carried
    as F-21.
    """
    o = pd.read_parquet(PANEL_OLD, columns=["sym", "day"])
    return sorted(o["sym"].unique().tolist()), str(o["day"].max())


def build(what: str = "pab") -> None:
    """Rebuild the panel and the two auction families through the PATCHED loader."""
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"store {ic.DATA_DIR}   calendar trim: {ic.CALENDAR_TRIM}")
    if not ic.CALENDAR_TRIM:
        raise SystemExit("intraday_common.CALENDAR_TRIM is off - the rebuild would be a no-op")
    syms, last_day = pin()
    print(f"clause 8: pinned to the old panel's {len(syms)} names and last day {last_day}")
    if "s" in what:
        # clause 9: trim OFF, so the only thing this panel has that the cache does not is
        # AUD-20's forward-span mask. old -> this isolates AUD-20; this -> clean isolates AUD-07.
        print("\n=== panel, SPAN MASK ONLY (calendar trim disabled)")
        t0 = time.time()
        ic.CALENDAR_TRIM = False
        try:
            p = f1.build_panel(symbols=syms, verbose=False)
        finally:
            ic.CALENDAR_TRIM = True
        p = p[p["day"].astype(str) <= last_day].reset_index(drop=True)
        p.to_parquet(PANEL_SPAN, index=False)
        print(f"  {len(p):,} rows, {p['sym'].nunique()} names -> {PANEL_SPAN}  "
              f"({time.time() - t0:.0f}s)")
    if "p" in what:
        print("\n=== panel (pinned universe, 11 decision slots)")
        t0 = time.time()
        p = f1.build_panel(symbols=syms)
        p = p[p["day"].astype(str) <= last_day].reset_index(drop=True)
        p.to_parquet(PANEL_NEW, index=False)
        print(f"  {len(p):,} rows, {p['sym'].nunique()} names -> {PANEL_NEW}  "
              f"({time.time() - t0:.0f}s)")
    if PANEL_NEW.exists():
        # `f15.panel_symbols` reads `f1.PANEL`; the universe must come from the clean panel
        f1.PANEL = PANEL_NEW
    if "a" in what:
        print("\n=== family A: the auction tape, per name")
        t0 = time.time()
        a = f15.build_family_a()
        a.to_parquet(FAMA_NEW, index=False)
        print(f"  {len(a):,} rows -> {FAMA_NEW}  ({time.time() - t0:.0f}s)")
    if "b" in what:
        print("\n=== family B: the SPY 0DTE chain, market-level")
        t0 = time.time()
        b = f15.build_family_b()
        b.to_parquet(FAMB_NEW, index=False)
        print(f"  {len(b):,} rows -> {FAMB_NEW}  ({time.time() - t0:.0f}s)")


def past_close(p: pd.DataFrame) -> pd.Series:
    """Clause 1: decision rows stamped at or after the session's OWN close.

    Only early closes can produce one - `load_bars` has always cut at 16:00 - so the test is
    "this date is an early close and the stamp is at or after 13:00", read straight off the
    calendar table D-6 pinned rather than off a second copy of it.
    """
    from quant_brain.markets.equity_us import CALENDAR
    early = CALENDAR.early_closes()
    ec = pd.Series(p["ts"].dt.date, index=p.index).isin(early)
    tod = p["ts"].dt.hour * 60 + p["ts"].dt.minute
    from quant_brain.markets.equity_us.calendar import EARLY_CLOSE
    return ec & (tod >= EARLY_CLOSE.hour * 60 + EARLY_CLOSE.minute)


def load_clean_panel(scramble: int | None = None, cols: list[str] | None = None) -> pd.DataFrame:
    """`f15.load_panel`, verbatim in structure, reading the f19 stores instead."""
    panel = pd.read_parquet(PANEL_NEW)
    p = f8.add_labels(panel)
    del panel
    a = pd.read_parquet(FAMA_NEW)
    # Family B is the SPY 0DTE chain: MARKET-level columns, which F-16 clause 3 puts out of the
    # gate's scope because a market-level column has no per-timestamp rank IC. It therefore
    # enters no arm of this run and its rebuild is not on the critical path; if it is missing the
    # dirty store is merged and the fact is printed. Carried as F-20.
    b_src = FAMB_NEW if FAMB_NEW.exists() else FAMB_OLD
    if b_src is FAMB_OLD:
        print("family B: reading the DIRTY store (market-level, admitted by no arm; F-20)")
    b = pd.read_parquet(b_src)
    p["_day"] = pd.to_datetime(p["ts"]).dt.date
    a["day"] = pd.to_datetime(a["day"]).dt.date
    b["day"] = pd.to_datetime(b["day"]).dt.date

    n0 = len(p)
    p = p.merge(a.rename(columns={"day": "_day"}), on=["_day", "sym"], how="left")
    p = p.merge(b.rename(columns={"day": "_day"}), on=["_day", "slot"], how="left")
    assert len(p) == n0, "the alt merge duplicated rows"
    for c in f15.ALT_FEATS:
        p[c] = p[c].astype("float32")
    print(f"panel {len(p):,} rows; family A coverage "
          f"{100 * p['auc_cdrift'].notna().mean():.2f}%, family B coverage "
          f"{100 * p['iv_strad'].notna().mean():.2f}%")
    if scramble is not None:
        rng = np.random.default_rng(scramble)
        tgt = cols or f15.ALT_FEATS
        print(f"clause 5 control: permuting {len(tgt)} alt columns within each timestamp")
        for c in tgt:
            p[c] = (p.groupby("ts", sort=False)[c]
                    .transform(lambda s: rng.permutation(s.to_numpy())).astype("float32"))
    return p


# --------------------------------------------------------------- clauses 1-3: premise, propagation


def _panel_key(p: pd.DataFrame) -> pd.DataFrame:
    q = p.copy()
    q["ts"] = pd.to_datetime(q["ts"])
    return q.set_index(["ts", "sym"]).sort_index()


def diff() -> None:
    """Clause 1 and clause 3: what the fake bars put in the panel, and how far it reached."""
    old = pd.read_parquet(PANEL_OLD)
    new = pd.read_parquet(PANEL_NEW)
    old["ts"] = pd.to_datetime(old["ts"])
    new["ts"] = pd.to_datetime(new["ts"])
    print(f"old panel {len(old):,} rows   new panel {len(new):,} rows   "
          f"delta {len(new) - len(old):+,}")

    # ---- clause 1: rows at or after the session's own close
    om, nm = past_close(old), past_close(new)
    print("\n=== clause 1: PREMISE - decision rows at or after the session's own close ===")
    print(f"  OLD {int(om.sum()):>7,} rows on {old.loc[om, 'day'].nunique():>3} sessions, "
          f"{old.loc[om, 'sym'].nunique()} names")
    print(f"  NEW {int(nm.sum()):>7,} rows")
    if int(om.sum()) == 0:
        print("  PREMISE FAILS - the old panel holds no post-close row; F-19 is WITHDRAWN")
    for d, g in old[om].groupby("day"):
        print(f"    {d}  {len(g):>4} rows  slots {sorted(g['ts'].dt.strftime('%H:%M').unique())}")

    # ---- clause 1(ii): labels on real rows that reached into the fake tape
    ok = set(zip(new["ts"], new["sym"]))
    lost = old[~pd.Series(list(zip(old["ts"], old["sym"])), index=old.index).isin(ok)]
    print(f"\n  rows the rebuild REMOVED: {len(lost):,} "
          f"({100 * len(lost) / len(old):.3f}% of the old panel)")
    print(f"    of which past-close (clause i): {int(past_close(lost).sum()):,}")
    print(f"    of which in-session with a label that spanned the close (clause ii): "
          f"{len(lost) - int(past_close(lost).sum()):,}")
    gained = new[~pd.Series(list(zip(new["ts"], new["sym"])), index=new.index)
                 .isin(set(zip(old["ts"], old["sym"])))]
    print(f"  rows the rebuild ADDED: {len(gained):,}  (must be 0 - the trim is a subset)")

    # ---- clause 3: propagation into rows that survived
    o, n = _panel_key(old), _panel_key(new)
    common = o.index.intersection(n.index)
    o, n = o.loc[common], n.loc[common]
    print(f"\n=== clause 3: PROPAGATION - {len(common):,} rows present in both panels ===")
    rows = []
    any_changed = np.zeros(len(common), dtype=bool)
    for c in list(f1.FEATURES) + ["fwd", "y"]:
        a = o[c].to_numpy(dtype="float64")
        b = n[c].to_numpy(dtype="float64")
        both_nan = np.isnan(a) & np.isnan(b)
        scale = np.maximum(np.abs(a), np.abs(b))
        d = np.abs(a - b) > (REL_TOL * np.where(scale > 0, scale, 1.0))
        d = d & ~both_nan
        d = np.where(np.isnan(a) ^ np.isnan(b), True, d)
        any_changed |= d
        if d.any():
            rows.append({"feature": c, "changed": int(d.sum()),
                         "pct": 100.0 * d.mean(),
                         "med_rel": float(np.nanmedian(
                             np.abs(a[d] - b[d]) / np.where(scale[d] > 0, scale[d], np.nan)))})
    tab = pd.DataFrame(rows).sort_values("changed", ascending=False)
    print(tab.to_string(index=False, float_format=lambda v: f"{v:,.4f}") if len(tab)
          else "  no surviving row changed")
    ch_days = pd.Index(o.index.get_level_values("ts")[any_changed]).normalize().nunique()
    print(f"\n  surviving rows with ANY changed feature: {int(any_changed.sum()):,} "
          f"({100 * any_changed.mean():.3f}%) over {ch_days} sessions "
          f"(the 21 early closes alone cannot explain more than 21)")
    if len(tab):
        tab.to_csv(DIFF, index=False)

    # ---- clause 3: family A
    fa, fb = pd.read_parquet(FAMA_OLD), pd.read_parquet(FAMA_NEW)
    fa["day"] = pd.to_datetime(fa["day"]).dt.date
    fb["day"] = pd.to_datetime(fb["day"]).dt.date
    fa = fa.set_index(["day", "sym"]).sort_index()
    fb = fb.set_index(["day", "sym"]).sort_index()
    k = fa.index.intersection(fb.index)
    fa, fb = fa.loc[k], fb.loc[k]
    print(f"\n=== clause 3: family A - {len(k):,} (session, symbol) rows in both ===")
    frows, fany = [], np.zeros(len(k), dtype=bool)
    for c in f16.PARENTS:
        a, b = fa[c].to_numpy("float64"), fb[c].to_numpy("float64")
        both_nan = np.isnan(a) & np.isnan(b)
        scale = np.maximum(np.abs(a), np.abs(b))
        d = (np.abs(a - b) > REL_TOL * np.where(scale > 0, scale, 1.0)) & ~both_nan
        d = np.where(np.isnan(a) ^ np.isnan(b), True, d)
        fany |= d
        frows.append({"feature": c, "changed": int(d.sum()), "pct": 100.0 * d.mean()})
    print(pd.DataFrame(frows).to_string(index=False, float_format=lambda v: f"{v:,.4f}"))
    nd = pd.Index(fa.index.get_level_values("day")[fany]).nunique()
    print(f"  rows with ANY changed auction column: {int(fany.sum()):,} over {nd} sessions")


# --------------------------------------------------------------------------- clause 2: identity


def _summ(sess: pd.DataFrame, label: str) -> dict:
    return f8.summarize(sess, label)


def identity() -> None:
    """Clause 2: this run's book code must reproduce `f16_arms.csv` from `f16_preds.parquet`."""
    ref = pd.read_csv(OUT / "f16_arms.csv").set_index("label")
    preds = pd.read_parquet(OUT / "f16_preds.parquet")
    preds["ts"] = pd.to_datetime(preds["ts"])
    print("\n=== clause 2: IDENTITY - re-simulating the frozen F-16 predictions ===")
    worst = 0.0
    saved, f1.PANEL = f1.PANEL, PANEL_OLD      # the grid PAYS; F-16 was paid by the dirty grid
    try:
        for arm in sorted(set(preds["arm"])):
            s = f8.simulate(f14.frame_for(preds, arm), "session", decile=DECILE)
            r = _summ(s, f"session/{arm}")
            lab = f"session/{arm}"
            if lab not in ref.index:
                continue
            d_net = abs(r["net_day"] - float(ref.loc[lab, "net_day"]))
            d_t = abs(r["t"] - float(ref.loc[lab, "t"]))
            worst = max(worst, d_net)
            print(f"  {arm:<18} net ${r['net_day']:>8.2f}/day (frozen "
                  f"${float(ref.loc[lab, 'net_day']):>8.2f})  |delta| ${d_net:.4f}  "
                  f"t {r['t']:+.5f} (frozen {float(ref.loc[lab, 't']):+.5f})  d {d_t:.6f}")
    finally:
        f1.PANEL = saved
    print(f"  worst |delta net/day| across arms: ${worst:.4f}  "
          f"-> {'PASS' if worst < 0.01 else 'FAIL - the run is VOID'}")


# ------------------------------------------------------------------------------ clause 4: the gate


def gate() -> None:
    p = load_clean_panel()
    p = p.dropna(subset=["y_close"]).copy()
    years = [y for y in sorted(p["year"].unique()) if y >= f8.FIRST_TEST_YEAR]
    all_rows, admit = [], {"q50": {}}
    for year in years:
        print(f"\n--- gate for test year {year} (reads year <= {year - 1} only)")
        t0 = time.time()
        a, rows = f16.causal_gate(p, year)
        admit["q50"][str(year)] = a["q50"]
        all_rows += rows
        print(f"    ({time.time() - t0:.0f}s)")
    pd.DataFrame(all_rows).to_csv(GATE, index=False)
    ADMIT.write_text(json.dumps(admit, indent=1), encoding="utf-8")
    compare_gates()


def compare_gates() -> None:
    """Clause 4: the clean admitted sets against F-16's, year by year."""
    new = json.loads(ADMIT.read_text(encoding="utf-8"))["q50"]
    old = json.loads((OUT / "f16_admitted.json").read_text(encoding="utf-8"))["q50"]
    print("\n=== clause 4: what the gate admits, F-16 (dirty) vs F-19 (clean) ===")
    same = 0
    for y in sorted(new):
        a = [c for c in old.get(y, []) if c in f16.PARENTS]
        b = [c for c in new[y] if c in f16.PARENTS]
        same += (sorted(a) == sorted(b))
        flag = "same" if sorted(a) == sorted(b) else "CHANGED"
        print(f"  {y}  dirty {', '.join(a) or '(none)':<28} clean "
              f"{', '.join(b) or '(none)':<28} {flag}")
    n = len(new)
    abst = sum(1 for y in new if not [c for c in new[y] if c in f16.PARENTS])
    print(f"  identical in {same}/{n} years")
    print(f"  clause 5 OUTCOME - abstention rate: {abst}/{n} windows admit NOTHING "
          f"(F-16 dirty: {sum(1 for y in old if not [c for c in old[y] if c in f16.PARENTS])}/{n})")


# ------------------------------------------------------------------------------- clause 5: the fit


def fit() -> None:
    if not ADMIT.exists():
        raise SystemExit("run --gate first")
    admit = json.loads(ADMIT.read_text(encoding="utf-8"))
    params = dict(f1.GRID["mid"])
    base = list(f1.FEATURES)
    frames, ics = [], []
    reuse: dict[int, pd.DataFrame] = {}

    for scr in (None, 0):
        arms = [a for a in ARMS if ARMS[a][1] == (scr is not None)]
        p = load_clean_panel(scramble=scr, cols=f16.POOL)
        p = p.dropna(subset=["y_close"]).copy()
        p["y"] = p["y_close"]
        years = [y for y in sorted(p["year"].unique()) if y >= f8.FIRST_TEST_YEAR]
        saved = list(f1.FEATURES)
        try:
            for arm in arms:
                print(f"\n--- arm {arm}")
                for year in years:
                    add = ([] if not ARMS[arm][0]
                           else [c for c in admit["q50"].get(str(year), []) if c not in base])
                    feats = base + add
                    trn, vld, tst = (p[p.year <= year - 2], p[p.year == year - 1],
                                     p[p.year == year])
                    if not (len(trn) and len(vld) and len(tst)):
                        continue
                    if not add and arm != "base" and int(year) in reuse:
                        k = reuse[int(year)].copy()
                        k["arm"] = arm
                        frames.append(k)
                        r = next(x for x in ics if x["arm"] == "base" and x["year"] == year)
                        ics.append({**r, "arm": arm})
                        print(f"  {year}: 38 feats, admitted set EMPTY -> identical to base "
                              f"(rank IC {r['ic']:+.5f}), reused", flush=True)
                        continue
                    f1.FEATURES = feats
                    t0 = time.time()
                    model, pt = f1.fit_predict(trn, vld, tst, dict(params))
                    icm, ict = f1.ic_stats(tst, pt)
                    ics.append({"arm": arm, "year": int(year), "ic": icm, "ic_t": ict,
                                "n_feat": len(feats)})
                    k = tst[["ts", "day", "year", "sym", "slot", "entry_px", "fwd"]].copy()
                    k["arm"] = arm
                    k["pred"] = pt
                    frames.append(k)
                    if arm == "base":
                        reuse[int(year)] = k
                    print(f"  {year}: {len(feats):>2} feats  train<={year-2} ({len(trn):,}) "
                          f"test ({len(tst):,})  iters {model.n_iter_:>4}  "
                          f"rank IC {icm:+.5f} (t {ict:+.1f})  ({time.time()-t0:.0f}s)",
                          flush=True)
        finally:
            f1.FEATURES = saved
        del p

    pd.concat(frames, ignore_index=True).to_parquet(PREDS, index=False)
    icd = pd.DataFrame(ics)
    print("\n=== per-timestamp rank IC on y_close, by arm and test year ===")
    piv = icd.pivot(index="year", columns="arm", values="ic")
    print(piv.round(5).to_string())
    print("mean " + "  ".join(f"{a} {piv[a].mean():+.5f}" for a in piv.columns))
    print(f"\nwritten: {PREDS}")


# ----------------------------------------------------------------------- clauses 5-6: the books


def record(tag: str, r: dict, sess: pd.DataFrame, params: dict, extra: dict) -> None:
    net = sess["net"].to_numpy()
    n = len(sess)
    ret = net / EQUITY
    sd = ret.std(ddof=1) if n > 1 else 0.0
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "intraday/f19_cleanpanel", "class": "ml", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-19", "params": params,
           "start": str(sess["day"].min()), "end": str(sess["day"].max()),
           "stats": {"Sessions": str(n),
                     "Avg Daily PnL": f"{net.mean():.0f}",
                     "t": f"{f1.tstat(net):.2f}",
                     "Gross Per Day": f"{sess['gross'].mean():.0f}",
                     "Costs Per Day": f"{sess['cost'].mean():.0f}",
                     "Turnover Per Day": f"{sess['turnover'].mean():.0f}",
                     "Gross Bps Per Turnover": f"{r['gross_bps']:.3f}",
                     "Cost Bps Per Turnover": f"{r['cost_bps']:.3f}",
                     "Edge Bps Per Turnover": f"{r['edge_bps']:.3f}",
                     "Worst Day": f"{net.min():.0f}",
                     "Win Rate": f"{100 * (net > 0).mean():.0f}%",
                     "Sharpe Ratio": f"{(ret.mean() / sd * np.sqrt(252)) if sd else float('nan'):.3f}",
                     "Diagnostic": "true",
                     **{k: str(v) for k, v in extra.items()}}}
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def books(record_rows: bool = False) -> None:
    preds = pd.read_parquet(PREDS)
    preds["ts"] = pd.to_datetime(preds["ts"])
    reg = f14.market_regime()
    arms = [a for a in ARMS if a in set(preds["arm"])]
    ref = pd.read_csv(OUT / "f16_arms.csv").set_index("label")

    sess, rows = {}, []
    saved, f1.PANEL = f1.PANEL, PANEL_NEW      # the CLEAN grid pays the clean predictions
    try:
        for arm in arms:
            sess[arm] = f8.simulate(f14.frame_for(preds, arm), "session", decile=DECILE)
            rows.append(_summ(sess[arm], f"session/{arm}"))
    finally:
        f1.PANEL = saved

    print("\n=== clause 5: the same book, on the CLEAN panel ===")
    f8.print_table(rows)

    tv = pd.Series({a: sess[a]["turnover"].mean() for a in arms})
    print(f"\nturnover spread across arms ${tv.max() - tv.min():,.0f} (mean ${tv.mean():,.0f})")

    print("\n=== clause 5: CLEAN against F-16's DIRTY, arm by arm ===")
    print(f"  {'arm':<20}{'dirty $/day':>13}{'clean $/day':>13}{'delta':>10}"
          f"{'dirty t':>10}{'clean t':>10}{'sessions':>10}")
    lut = {x["label"]: x for x in rows}
    for arm in arms:
        lab = f"session/{arm}"
        if lab not in ref.index:
            continue
        o, n = ref.loc[lab], lut[lab]
        print(f"  {arm:<20}{float(o['net_day']):>13,.0f}{n['net_day']:>13,.0f}"
              f"{n['net_day'] - float(o['net_day']):>+10,.0f}"
              f"{float(o['t']):>+10.3f}{n['t']:>+10.3f}"
              f"{int(o['sessions']):>6,}->{n['sessions']:,}")

    print("\n=== net $/day by test year ===")
    yr = pd.DataFrame({a: f14.by_year(sess[a]) for a in arms})
    print(yr.to_string())
    print("years positive: " + "  ".join(f"{a} {int((yr[a] > 0).sum())}/{len(yr)}" for a in arms))

    print("\n=== paired per session against base ===")
    pairs = {}
    for arm in arms:
        if arm != "base":
            pairs[arm] = f14.paired(sess["base"], sess[arm], f"{arm} - base")

    print("\n=== regimes: terciles of SPY trailing 20-session realised vol ===")
    print(f"{'cell':<20}" + "".join(f"{k:>12}" for k in ("low", "mid", "high")))
    for arm in arms:
        s = sess[arm].copy()
        s["reg"] = s["day"].astype(str).map(reg)
        m = s.groupby("reg")["net"].mean()
        print(f"{arm:<20}" + "".join(f"{m.get(k, float('nan')):>12,.0f}"
                                    for k in ("low", "mid", "high")))

    compare_gates()

    r, b = lut["session/causal"], lut["session/base"]
    n_pos = int((yr["causal"] > 0).sum())
    dp = pairs.get("causal", {})
    ok = (r["t"] > 2.0) and (n_pos >= 5) and (dp.get("d_net_t", -9) > 2.0)
    print("\n=== clause 5: the unchanged hurdle, on clean data ===")
    print(f"  net t > 2.0                : {r['t']:+.3f}   {'PASS' if r['t'] > 2 else 'FAIL'}")
    print(f"  >= 5 of 8 years positive   : {n_pos}/{len(yr)}     "
          f"{'PASS' if n_pos >= 5 else 'FAIL'}")
    print(f"  paired causal - base t>2.0 : {dp.get('d_net_t', float('nan')):+.3f}   "
          f"{'PASS' if dp.get('d_net_t', -9) > 2 else 'FAIL'}")
    print(f"  -> {'ADOPT' if ok else 'REFUSE'}")
    print(f"\n  clause 0 check: F-16 refused at t +1.969; clean t is {r['t']:+.3f} "
          f"-> the verdict {'HOLDS' if not ok else 'FLIPS (see clause 6)'}")
    print(f"  clause 5 (F-17 c): scramble NET ${lut['session/causal_scrambled']['net_day']:,.0f}/day "
          f"vs base ${b['net_day']:,.0f} vs causal ${r['net_day']:,.0f}")

    pd.DataFrame(rows).to_csv(CELLS, index=False)
    if record_rows:
        # The gate abstains in 8/8 windows, so `causal` and `causal_scrambled` are the SAME BOOK
        # as `base` to the cent. Writing three identical ledger rows would inflate the trial
        # count for a single measurement; only distinct books are recorded, and the collapse is
        # carried in the tag.
        seen, n = set(), 0
        for arm in arms:
            r = lut[f"session/{arm}"]
            key = (round(r["net_day"], 6), round(r["t"], 6), round(r["worst"], 6))
            if key in seen:
                print(f"  {arm}: identical to an already-recorded book, not recorded again")
                continue
            seen.add(key)
            record(f"F-19 clean panel (AUD-20 + AUD-07): {arm}; gate admits 0/8 windows",
                   r, sess[arm],
                   {"arm": arm, "learner": "mid", "decile": DECILE, "window": "2019-2026",
                    "panel": "span-masked (AUD-20) + calendar-trimmed (AUD-07)"},
                   {"Arm": arm, "Clause": "5", "Admitted Windows": "0/8"})
            n += 1
        print(f"\nrecorded {n} distinct row(s) to {LEDGER}")


# ------------------------------------------------------- clause 9: which audit moved the book


def span(record_rows: bool = False) -> None:
    """Clause 9: fit `base` on the SPAN-ONLY panel, so the $/day delta splits into two audits.

    dirty (neither fix) -> span-only (AUD-20 alone) -> clean (AUD-20 + AUD-07). The arms differ
    in nothing else: same learner, same seed, same 56 names, same last day, same 8 test years.
    """
    p = f8.add_labels(pd.read_parquet(PANEL_SPAN))
    p = p.dropna(subset=["y_close"]).copy()
    p["y"] = p["y_close"]
    years = [y for y in sorted(p["year"].unique()) if y >= f8.FIRST_TEST_YEAR]
    frames, ics = [], []
    for year in years:
        trn, vld, tst = p[p.year <= year - 2], p[p.year == year - 1], p[p.year == year]
        if not (len(trn) and len(vld) and len(tst)):
            continue
        t0 = time.time()
        model, pt = f1.fit_predict(trn, vld, tst, dict(f1.GRID["mid"]))
        icm, ict = f1.ic_stats(tst, pt)
        ics.append({"year": int(year), "ic": icm})
        k = tst[["ts", "day", "year", "sym", "slot", "entry_px", "fwd"]].copy()
        k["arm"] = "base_spanonly"
        k["pred"] = pt
        frames.append(k)
        print(f"  {year}: rank IC {icm:+.5f} (t {ict:+.1f})  ({time.time()-t0:.0f}s)", flush=True)
    preds = pd.concat(frames, ignore_index=True)
    preds.to_parquet(OUT / "f19_preds_spanonly.parquet", index=False)

    saved, f1.PANEL = f1.PANEL, PANEL_SPAN
    try:
        s = f8.simulate(f14.frame_for(preds, "base_spanonly"), "session", decile=DECILE)
    finally:
        f1.PANEL = saved
    r = _summ(s, "session/base_spanonly")
    f8.print_table([r])

    ref = pd.read_csv(OUT / "f16_arms.csv").set_index("label")
    clean = pd.read_csv(CELLS).set_index("label")
    d0 = float(ref.loc["session/base", "net_day"])
    c0 = float(clean.loc["session/base", "net_day"])
    print("\n=== clause 9: the base book, decomposed over the two audits ===")
    print(f"  dirty cache (neither fix)     ${d0:>7,.0f}/day   t "
          f"{float(ref.loc['session/base', 't']):+.3f}   mean rank IC +0.01030")
    print(f"  + AUD-20 span mask only       ${r['net_day']:>7,.0f}/day   t {r['t']:+.3f}   "
          f"mean rank IC {np.mean([x['ic'] for x in ics]):+.5f}")
    print(f"  + AUD-07 calendar trim (clean)${c0:>7,.0f}/day   t "
          f"{float(clean.loc['session/base', 't']):+.3f}")
    print(f"  attributed to AUD-20: {r['net_day'] - d0:+,.0f} $/day;  "
          f"to AUD-07: {c0 - r['net_day']:+,.0f} $/day;  total {c0 - d0:+,.0f}")
    print("\n  These are three DIFFERENT FITS, not one book with rows deleted: each panel trains\n"
          "  its own model, so the swing is the base book's sensitivity to a ~1% change in the\n"
          "  panel, not an attributable P&L. The number to carry is the SPREAD.")
    print(f"  spread of the F-8 base book over the three panels: "
          f"${max(d0, c0, r['net_day']) - min(d0, c0, r['net_day']):,.0f}/day")
    if record_rows:
        record("F-19 clause 9: base on the AUD-20-only panel (calendar trim OFF)", r, s,
               {"arm": "base_spanonly", "learner": "mid", "decile": DECILE,
                "window": "2019-2026", "panel": "span-masked only (AUD-20), trim OFF"},
               {"Arm": "base_spanonly", "Clause": "9"})
        print(f"\nrecorded 1 row to {LEDGER}")


# ---------------------------------------------------------------------------- clause 6: install


def install() -> None:
    """Clause 6: promote the clean rebuilds to the canonical paths. Data hygiene, no hurdle."""
    pairs = [(PANEL_NEW, PANEL_OLD), (FAMA_NEW, FAMA_OLD)]
    if FAMB_NEW.exists():
        pairs.append((FAMB_NEW, FAMB_OLD))
    else:
        print("  family B NOT installed - not rebuilt this run, and it enters no arm (F-20)")
    for src, dst in pairs:
        if not src.exists():
            raise SystemExit(f"missing {src} - run --build first")
        bak = dst.with_suffix(".dirty.parquet")
        if dst.exists() and not bak.exists():
            shutil.copy2(dst, bak)
            print(f"  kept the dirty store as {bak.name}")
        shutil.copy2(src, dst)
        print(f"  installed {src.name} -> {dst.name}")
    meta = f1.stamp_panel()
    print(f"  stamped {f1.PANEL_META.name}: code {meta['code']}, "
          f"{meta['store_files']} store symbols")
    print("\ndone. Every later F run reads a span-masked, calendar-trimmed panel, and "
          "`f1.check_panel_fresh()` now says so if that stops being true.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", nargs="?", const="pab", default=None,
                    help="rebuild stores: p=panel a=familyA b=familyB")
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--identity", action="store_true")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--books", action="store_true")
    ap.add_argument("--span", action="store_true")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--install", action="store_true")
    a = ap.parse_args()
    if a.build:
        build(a.build)
    if a.diff:
        diff()
    if a.identity:
        identity()
    if a.gate:
        gate()
    if a.fit:
        fit()
    if a.books:
        books(a.record)
    if a.span:
        span(a.record)
    if a.install:
        install()
    if not any([a.build, a.diff, a.identity, a.gate, a.fit, a.books, a.span, a.install]):
        ap.print_help()


if __name__ == "__main__":
    main()
