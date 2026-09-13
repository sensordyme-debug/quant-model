#!/usr/bin/env python
"""C-8: the attack on S-41 clause 7b - "a better book than CHOOSING a cell".

    py -3.11 scripts/verify_c8.py --stage ab      # cache-only, no simulation (~20 s)
    py -3.11 scripts/verify_c8.py --stage all     # adds the charged leg (36 sims, ~5 min)

WHAT IS UNDER ATTACK, AND WHY THIS ONE. No promotion moved in the last 24 hours -
`research/champion.json` is byte-identical to `9197bd4` (S-31) and every track's entry today
either refuses (F-17, O-8, S-41 clause 7) or ships platform code (D-6, E-11). So the brief
falls to the strongest CLAIM, and S-41's is the only positive research conclusion of the day
that reaches a decision: clause 7b, which ends

    "The blend is not a better cell than the one that shipped. It is a better book than
     CHOOSING a cell - which is the only thing on offer to anyone deciding this dial today
     without S-40's hindsight."

supported by a five-row table on 2,684 sessions in which the 36-cell weight-blend beats
S-40's walk-forward CAR selector by +1.587 CAR / +0.163 Sharpe / -14.858 drawdown points.

WHAT IS NOT THE ATTACK. S-41 already withdraws its own opening sentence (the 1.173-vs-1.159
span mismatch), already prints that it FAILS its own promotion bar on CAR and Sharpe in both
windows, already says the drawdown prize halves once charged (-0.533 -> -0.286 points),
already runs the leave-the-shipped-cell-out control (clause 4b), and already says the
mechanism is the fractional risk-off boundary rather than diversification (clause 6). None of
those are attackable: an entry that reports its own weak points does not get attacked on them.

THE ATTACK, DECLARED HERE BEFORE A NUMBER WAS READ. Clause 7b's table contains exactly ONE
no-selection alternative - the 36-cell blend - and compares it against two selectors and two
hindsight books. It omits the cheapest no-selection alternative there is, the one that needs
no ensemble, no signal-level change to `algorithms/s1_momo/signals.py` and no second LEAN
run: **PICK ONE CELL ON 2015-12-31 AND NEVER TOUCH IT AGAIN.** That is as available to "anyone
deciding this dial today" as the blend is, and S-40's own grid gives 36 of them. If most of
those 36 fixed cells ALSO beat the walk-forward selector on all three metrics over the
identical span, then clause 7b's margin is a statement about the SELECTOR being bad - which
is S-40's finding, already published - and not about the ENSEMBLE being good, and the
sentence quoted above is carrying more weight than its table can bear.

PRE-REGISTERED BARS, so the verdict cannot be moved after the numbers are in
--------------------------------------------------------------------------
(A) LICENCE. Recompute clause 3b's three rows from `results/s41_cache.pkl` on the
    2,684-session span. Must reproduce the printed 24.705/1.228/23.860 (shipped),
    22.932/1.174/23.327 (blend36) and 28.021/1.169/36.619 (off) to 0.001 on all three
    statistics, and INDEPENDENTLY re-derive S-40's two selector books from
    `results/s40_cache.pkl` - same picks, same 21.345/1.011/38.185 and 21.046/1.000/38.185.
    If either misses, the attack is withdrawn and the failure IS the finding, because clause
    7b mixes rows from two harnesses (blend from S-41, selectors from S-40) and a mismatch
    there is the same defect S-41 caught in its own opening sentence.

(B) THE MISSING CONTROL, zero cost, identical span. All 36 fixed cells summarized with the
    SAME function clause 3b uses. Then:
      b1  how many of the 36 dominate the walk-forward CAR selector on all three metrics
          (CAR >, Sharpe >, MaxDD <)?
      b2  where does the blend rank among the 36 on each metric?
    VERDICT RULE, pre-registered:
      - clause 7b SURVIVES AS WRITTEN if the blend is in the top quartile (rank <= 9 of 36)
        on BOTH Sharpe and MaxDD. Then the ensemble is doing something a fixed cell does not.
      - clause 7b is OVERSTATED if fewer than a quarter of the fixed cells (<= 9 of 36)
        dominate the selector - i.e. beating the selector really is the hard part - but the
        blend is at or below the median of the 36 on either Sharpe or MaxDD.
      - clause 7b's HEADLINE IS CARRIED BY THE SELECTOR'S BADNESS if a MAJORITY of the 36
        fixed cells (>= 19) dominate the selector on all three. In that case the true
        statement is the weaker "almost any fixed cell beats S-40's argmax", the ensemble's
        marginal contribution is the blend-minus-best-fixed-cell gap, and the entry's closing
        sentence should be corrected in the journal.
    These three are exhaustive except for the overlap case (majority dominate AND the blend
    is top-quartile on both), which is reported as PARTIAL: the sentence is true but the
    table that supports it is the wrong table.

(C) IS THE ADVANTAGE JUST EXPOSURE? The blend holds a fractional book on 39% of sessions
    (S-41 clause 4), so its mean gross sits between the cells'. Regress MaxDD and CAR on mean
    gross across the 36 cells and report where the blend falls against that line. If the
    blend's drawdown sits ON the fixed-cell gross/drawdown line, its smoothing bought nothing
    a differently-sized fixed cell would not have bought.

(D) CHARGED. Clause 7b is quoted at ZERO COST throughout while S-41's own clause 5 shows
    costing halves the only prize. Re-run (B) in S-22 cell C (2 bp one-way spread + IBKR Pro
    financing on the historical EFFR) - 36 fresh simulations - with the selector books
    stitched from the charged per-cell books, and report whether the verdict from (B) moves.
    The stitch is S-40's own construction and carries its acknowledged <= 0.024 CAR points of
    unmodelled boundary rebalance.

SCOPE. Read-only with respect to every other track: this script imports `sweep_s40`/`sweep_s41`
and their caches and writes nothing but its own report. No shipped file, no runner-loaded file,
no `live/*`, no `champion.json`, no ledger row (the critic track records evidence in its
journal, not as trials). DIAGNOSTIC.
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

from sweep_s40 import (SHIPPED_CELL, SPREAD_BPS, THRESHOLDS,  # noqa: E402
                       VOL_WINDOWS, WF_FIRST_YEAR, WINDOWS)
from sweep_s41 import WF_SPAN_START, _init_worker, _sim_job, grid_cells  # noqa: E402

S40_CACHE = REPO / "results" / "s40_cache.pkl"
S41_CACHE = REPO / "results" / "s41_cache.pkl"
C8_CACHE = REPO / "results" / "c8_cache.pkl"

#: clause 3b's printed rows, the licence for everything below
CLAUSE_3B = {"shipped": (24.705, 1.228, 23.860),
             "off (switch never fires)": (28.021, 1.169, 36.619),
             "blend36": (22.932, 1.174, 23.327)}
#: S-40's printed selector rows, quoted by clause 7b
S40_SELECTORS = {"CAR": (21.345, 1.011, 38.185), "Sharpe": (21.046, 1.000, 38.185)}
TOL = 0.001
EXPECTED_SESSIONS = 2684


def h(title: str) -> None:
    print("\n" + "=" * 96)
    print(title)
    print("=" * 96)


def summarize(ret: np.ndarray, label: str, gross: np.ndarray | None = None) -> dict:
    """`sweep_s41.summarize_span` exactly, plus mean gross where the book carries it."""
    ret = np.asarray(ret, dtype=float)
    curve = np.cumprod(1 + ret)
    sd = ret.std(ddof=1)
    return {"cell": label, "sessions": len(ret),
            "CAR": 100 * (curve[-1] ** (252.0 / len(ret)) - 1),
            "Sharpe": ret.mean() / sd * np.sqrt(252),
            "MaxDD": 100 * float((1 - curve / np.maximum.accumulate(curve)).max()),
            "std": sd * np.sqrt(252),
            "gross": float(np.mean(gross)) if gross is not None else float("nan")}


def span_of(book: pd.DataFrame) -> pd.DataFrame:
    return book[pd.to_datetime(book["date"]) >= pd.Timestamp(WF_SPAN_START)]


def cell_key(c: dict) -> tuple:
    return (c["regime_threshold"], c["regime_vol_window"])


def cell_label(c: dict) -> str:
    return f"thr={c['regime_threshold']:.2f} win={c['regime_vol_window']}"


def load_caches() -> tuple[dict, dict]:
    c40 = pickle.loads(S40_CACHE.read_bytes())
    c41 = pickle.loads(S41_CACHE.read_bytes())
    for c in (c40, c41):
        for k in list(c):
            if len(k) == 3 and isinstance(c[k][1], list):
                c[k] = (c[k][0], pd.DataFrame(c[k][1]))
    return c40, c41


def cell_books(c40: dict, costed: bool, fresh: dict | None = None) -> dict:
    """{(thr, win): full-period book} - from S-40's cache at zero cost, from stage D's own
    simulations when charged (S-40 never ran the 36 cells in cell C)."""
    if not costed:
        out = {}
        for c in grid_cells():
            k = (tuple(sorted(c.items())), "FULL", False)
            out[cell_key(c)] = c40[k][1]
        return out
    return dict(fresh or {})


# ------------------------------------------------------------------------------ clause A

def stitch(books: dict, how: str) -> tuple[dict, dict]:
    """S-40 clause 4's walk-forward, re-derived here rather than quoted.

    Each year Y from 2016 the selector sees only returns up to (Y-1)-12-31 and takes that
    window's argmax under `how`; the book is the chosen cell's returns for year Y.
    """
    rets = {k: pd.Series(v["ret"].to_numpy(), index=pd.to_datetime(v["date"]))
            for k, v in books.items()}
    years = sorted({d.year for d in rets[SHIPPED_CELL].index if d.year >= WF_FIRST_YEAR})

    def score(k, upto):
        s = rets[k][rets[k].index <= upto]
        if how == "CAR":
            return float(np.prod(1 + s.to_numpy()) ** (252.0 / len(s)) - 1)
        sd = s.std(ddof=1)
        return float(s.mean() / sd * np.sqrt(252)) if sd else float("nan")

    picks, series = {}, []
    for y in years:
        pick = max(rets, key=lambda k: score(k, pd.Timestamp(f"{y - 1}-12-31")))
        picks[y] = pick
        seg = rets[pick]
        series.append(seg[(seg.index >= pd.Timestamp(f"{y}-01-01"))
                          & (seg.index <= pd.Timestamp(f"{y}-12-31"))])
    wf = pd.concat(series).sort_index()
    return picks, summarize(wf.to_numpy(), f"walk-forward ({how})")


def clause_a(c40: dict, c41: dict) -> bool:
    h("CLAUSE A - LICENCE: are clause 7b's rows reproducible, and from the same span?")
    ok = True
    print(f"  {'row':<34}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>9}   vs printed")
    print("  " + "-" * 84)
    for name, (car, sh, dd) in CLAUSE_3B.items():
        b = span_of(c41[(name, "FULL", False)][1])
        d = summarize(b["ret"].to_numpy(), name)
        bad = (abs(d["CAR"] - car) > TOL or abs(d["Sharpe"] - sh) > TOL
               or abs(d["MaxDD"] - dd) > TOL or d["sessions"] != EXPECTED_SESSIONS)
        ok &= not bad
        print(f"  {name:<34}{d['sessions']:>6}{d['CAR']:>9.3f}{d['Sharpe']:>8.3f}"
              f"{d['MaxDD']:>9.3f}   {car:.3f}/{sh:.3f}/{dd:.3f} "
              f"{'MISMATCH' if bad else 'ok'}")

    print()
    books = cell_books(c40, costed=False)
    for how, (car, sh, dd) in S40_SELECTORS.items():
        picks, d = stitch(books, how)
        bad = (abs(d["CAR"] - car) > TOL or abs(d["Sharpe"] - sh) > TOL
               or abs(d["MaxDD"] - dd) > TOL or d["sessions"] != EXPECTED_SESSIONS)
        ok &= not bad
        print(f"  {d['cell']:<34}{d['sessions']:>6}{d['CAR']:>9.3f}{d['Sharpe']:>8.3f}"
              f"{d['MaxDD']:>9.3f}   {car:.3f}/{sh:.3f}/{dd:.3f} "
              f"{'MISMATCH' if bad else 'ok'}")
        print(f"    picks: " + "  ".join(f"{y}:{p[0]:.2f}/{p[1]}" for y, p in picks.items()))
        print(f"    shipped cell {SHIPPED_CELL[0]:.2f}/{SHIPPED_CELL[1]} chosen in "
              f"{sum(1 for p in picks.values() if p == SHIPPED_CELL)} of {len(picks)} years")
    print(f"\n  LICENCE: {'PASS' if ok else 'FAIL'}")
    return ok


# ------------------------------------------------------------------------------ clause B

def clause_b(books: dict, blend: dict, selectors: dict, costed: bool) -> dict:
    tag = "S-22 cell C (2 bp + IBKR Pro financing)" if costed else "zero cost"
    h(f"CLAUSE B - THE MISSING CONTROL: all 36 FIXED cells on the same 2,684 sessions, {tag}")
    rows = []
    for c in grid_cells():
        b = span_of(books[cell_key(c)])
        g = b["gross_x"].to_numpy() if "gross_x" in b else None
        d = summarize(b["ret"].to_numpy(), cell_label(c), g)
        d["key"] = cell_key(c)
        rows.append(d)
    rows.sort(key=lambda d: -d["Sharpe"])

    sel = selectors["CAR"]
    dom = [d for d in rows if d["CAR"] > sel["CAR"] and d["Sharpe"] > sel["Sharpe"]
           and d["MaxDD"] < sel["MaxDD"]]
    dom_sh = [d for d in rows if d["CAR"] > selectors["Sharpe"]["CAR"]
              and d["Sharpe"] > selectors["Sharpe"]["Sharpe"]
              and d["MaxDD"] < selectors["Sharpe"]["MaxDD"]]

    print(f"  {'fixed cell':<22}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>9}{'gross':>8}"
          f"   beats CAR-selector on all 3?")
    print("  " + "-" * 76)
    for d in rows:
        mark = "YES" if d in dom else ""
        star = " *shipped" if d["key"] == SHIPPED_CELL else ""
        print(f"  {d['cell']:<22}{d['CAR']:>9.3f}{d['Sharpe']:>8.3f}{d['MaxDD']:>9.3f}"
              f"{d['gross']:>8.3f}   {mark}{star}")
    print("  " + "-" * 76)
    print(f"  {'weight-blend36':<22}{blend['CAR']:>9.3f}{blend['Sharpe']:>8.3f}"
          f"{blend['MaxDD']:>9.3f}{blend['gross']:>8.3f}")
    for how, d in selectors.items():
        print(f"  {'walk-forward ' + how:<22}{d['CAR']:>9.3f}{d['Sharpe']:>8.3f}"
              f"{d['MaxDD']:>9.3f}{'n/a':>8}")

    def rank(metric: str, better_low: bool) -> int:
        """1 = the blend beats every fixed cell. Counts cells strictly BETTER than it."""
        if better_low:
            better = sum(1 for d in rows if d[metric] < blend[metric])
        else:
            better = sum(1 for d in rows if d[metric] > blend[metric])
        return better + 1

    r_car, r_sh, r_dd = rank("CAR", False), rank("Sharpe", False), rank("MaxDD", True)
    med = {m: float(np.median([d[m] for d in rows])) for m in ("CAR", "Sharpe", "MaxDD")}
    best = {m: (max if m != "MaxDD" else min)([d[m] for d in rows])
            for m in ("CAR", "Sharpe", "MaxDD")}

    print(f"\n  b1  fixed cells dominating the walk-forward CAR selector on all three: "
          f"{len(dom)} of 36")
    print(f"      fixed cells dominating the walk-forward SHARPE selector on all three: "
          f"{len(dom_sh)} of 36")
    print(f"  b2  the blend's rank among the 36 fixed cells (1 = best):")
    print(f"        CAR     {r_car:>2} of 36   (blend {blend['CAR']:.3f}, "
          f"median {med['CAR']:.3f}, best {best['CAR']:.3f})")
    print(f"        Sharpe  {r_sh:>2} of 36   (blend {blend['Sharpe']:.3f}, "
          f"median {med['Sharpe']:.3f}, best {best['Sharpe']:.3f})")
    print(f"        MaxDD   {r_dd:>2} of 36   (blend {blend['MaxDD']:.3f}, "
          f"median {med['MaxDD']:.3f}, best {best['MaxDD']:.3f})")

    top_quartile = r_sh <= 9 and r_dd <= 9
    majority = len(dom) >= 19
    if majority and top_quartile:
        verdict = ("PARTIAL - the sentence is true but the table is the wrong table: "
                   f"{len(dom)} of 36 fixed cells already dominate the selector, so the "
                   "+1.587/+0.163/-14.858 margin is not evidence about the ensemble; the "
                   "ensemble's own case is its top-quartile rank against those 36.")
    elif majority:
        verdict = ("CARRIED BY THE SELECTOR'S BADNESS - clause 7b's margin measures S-40's "
                   f"argmax, not the blend: {len(dom)} of 36 fixed cells dominate the same "
                   "selector, and the blend is not top-quartile among them.")
    elif top_quartile:
        verdict = ("SURVIVES AS WRITTEN - the blend is top-quartile among the fixed cells on "
                   f"both Sharpe and MaxDD and only {len(dom)} of 36 fixed cells dominate "
                   "the selector, so beating it is the hard part and the ensemble does it.")
    else:
        verdict = ("OVERSTATED - beating the selector is hard "
                   f"({len(dom)} of 36 fixed cells manage it) but the blend is not "
                   "top-quartile among the fixed cells either.")
    print(f"\n  PRE-REGISTERED VERDICT ({tag}): {verdict}")
    return {"rows": rows, "dom": len(dom), "dom_sh": len(dom_sh),
            "ranks": (r_car, r_sh, r_dd), "verdict": verdict}


# ------------------------------------------------------------------------------ clause C

def clause_c(rows: list[dict], blend: dict) -> None:
    h("CLAUSE C - is the blend's drawdown just its exposure?")
    g = np.array([d["gross"] for d in rows])
    if not np.isfinite(g).all():
        print("  gross not carried in these books; skipped")
        return
    for metric in ("MaxDD", "CAR", "Sharpe"):
        y = np.array([d[metric] for d in rows])
        slope, intercept = np.polyfit(g, y, 1)
        pred = slope * blend["gross"] + intercept
        resid = y - (slope * g + intercept)
        r = float(np.corrcoef(g, y)[0, 1])
        print(f"  {metric:<7} vs mean gross: slope {slope:>9.3f}  r {r:>6.3f}   "
              f"line at the blend's gross {blend['gross']:.3f} -> {pred:>8.3f}   "
              f"blend {blend[metric]:>8.3f}   residual {blend[metric] - pred:>+8.3f} "
              f"({(blend[metric] - pred) / resid.std(ddof=1):+.2f} sd of the cells')")
    near = sorted(rows, key=lambda d: abs(d["gross"] - blend["gross"]))[:3]
    print("\n  the three fixed cells closest to the blend's mean gross:")
    for d in near:
        print(f"    {d['cell']:<22}{d['CAR']:>9.3f}{d['Sharpe']:>8.3f}{d['MaxDD']:>9.3f}"
              f"{d['gross']:>8.3f}")
    print(f"    {'weight-blend36':<22}{blend['CAR']:>9.3f}{blend['Sharpe']:>8.3f}"
          f"{blend['MaxDD']:>9.3f}{blend['gross']:>8.3f}")


# ------------------------------------------------------------------------------ clause D

def charged_cells(workers: int) -> dict:
    """The 36 cells in S-22 cell C. S-40 never ran these, so there is nothing to quote."""
    cache: dict = {}
    if C8_CACHE.exists():
        cache = pickle.loads(C8_CACHE.read_bytes())
    jobs = [((cell_label(c),), c, "FULL", True, None) for c in grid_cells()
            if cell_label(c) not in cache]
    if jobs:
        from concurrent.futures import ProcessPoolExecutor
        print(f"  [charged cells] {len(jobs)} simulations on {workers} workers ...",
              flush=True)
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
            for out in ex.map(_sim_job, jobs):
                cache[out[0][0]] = out[2]
        C8_CACHE.write_bytes(pickle.dumps(cache))
    return {cell_key(c): pd.DataFrame(cache[cell_label(c)]) for c in grid_cells()}


def clause_e(c40: dict, c41: dict, charged: dict | None) -> None:
    """Post hoc, and labelled as such: is the blend DOMINATED by a fixed cell, and is that
    cell any more findable than the shipped one?

    Clause B is a rank statement. This is the stronger question it implies: does there exist a
    single `Params()` - one cell, no signal-level change, no second LEAN run - that beats the
    36-cell blend on CAR *and* Sharpe *and* drawdown at once, and does it keep doing so when
    the window moves? Selected AFTER the numbers were read, so it is evidence about the
    blend's ceiling and NOT a candidate; the honest counterweight is printed with it.
    """
    h("CLAUSE E (POST HOC) - is the blend dominated by a single cell, and in which windows?")
    for window, costed in (("FULL", False), ("IS", False), ("OOS", False),
                           ("FULL", True), ("OOS", True)):
        kb = ("blend36", window, costed)
        if kb not in c41:
            continue
        bb = c41[kb][1]
        bl = summarize(bb["ret"].to_numpy(), "blend36")
        doms = []
        for c in grid_cells():
            if costed:
                if charged is None or window != "FULL":
                    continue
                b = charged[cell_key(c)]
            else:
                k = (tuple(sorted(c.items())), window, False)
                if k not in c40:
                    continue
                b = c40[k][1]
            d = summarize(b["ret"].to_numpy(), cell_label(c))
            if d["CAR"] > bl["CAR"] and d["Sharpe"] > bl["Sharpe"] and d["MaxDD"] < bl["MaxDD"]:
                doms.append(d)
        tag = f"{window} {'charged' if costed else 'zero cost'}"
        doms.sort(key=lambda d: -d["Sharpe"])
        print(f"\n  --- {tag}: blend36 {bl['CAR']:.3f} / {bl['Sharpe']:.3f} / "
              f"{bl['MaxDD']:.3f}   ({len(doms)} of 36 fixed cells dominate it)")
        for d in doms[:5]:
            print(f"      {d['cell']:<22}{d['CAR']:>9.3f}{d['Sharpe']:>8.3f}{d['MaxDD']:>9.3f}")
    print("\n  THE COUNTERWEIGHT, stated so this clause cannot be misread: any cell named here\n"
          "  was chosen with the same hindsight S-40 disqualified the shipped cell for, and\n"
          "  clause A's own walk-forward picks (1.75/2.00 thresholds in all 11 years) show a\n"
          "  real-time selector never goes near thr=1.25. This clause bounds the blend from\n"
          "  above; it does not name a book anyone could have held.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="ab", choices=("ab", "all"))
    ap.add_argument("--workers", type=int, default=10)
    a = ap.parse_args()

    c40, c41 = load_caches()
    if not clause_a(c40, c41):
        print("\nPRE-REGISTERED STOP: clause 7b's own rows do not reproduce. That failure is "
              "the finding; the attack below is withdrawn.")
        return 1

    zero_books = cell_books(c40, costed=False)
    zero_sel = {how: stitch(zero_books, how)[1] for how in ("CAR", "Sharpe")}
    b = span_of(c41[("blend36", "FULL", False)][1])
    blend0 = summarize(b["ret"].to_numpy(), "blend36",
                       b["gross_x"].to_numpy() if "gross_x" in b else None)
    out = clause_b(zero_books, blend0, zero_sel, costed=False)
    clause_c(out["rows"], blend0)
    if a.stage != "all":
        clause_e(c40, c41, None)

    if a.stage == "all":
        ch = charged_cells(a.workers)
        ch_sel = {how: stitch(ch, how)[1] for how in ("CAR", "Sharpe")}
        bc = span_of(c41[("blend36", "FULL", True)][1])
        blend1 = summarize(bc["ret"].to_numpy(), "blend36",
                           bc["gross_x"].to_numpy() if "gross_x" in bc else None)
        out_c = clause_b(ch, blend1, ch_sel, costed=True)
        h("CLAUSE D - does the verdict move once the books are charged?")
        print(f"  zero cost : {out['dom']} of 36 dominate; blend ranks "
              f"CAR {out['ranks'][0]} / Sharpe {out['ranks'][1]} / MaxDD {out['ranks'][2]}")
        print(f"  charged   : {out_c['dom']} of 36 dominate; blend ranks "
              f"CAR {out_c['ranks'][0]} / Sharpe {out_c['ranks'][1]} / "
              f"MaxDD {out_c['ranks'][2]}")
        same = (out["dom"] >= 19) == (out_c["dom"] >= 19) and \
               (out["ranks"][1] <= 9 and out["ranks"][2] <= 9) == \
               (out_c["ranks"][1] <= 9 and out_c["ranks"][2] <= 9)
        print(f"  the pre-registered verdict is {'UNCHANGED' if same else 'DIFFERENT'} "
              f"once the 2 bp spread and the financing are charged.")
        clause_e(c40, c41, ch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
