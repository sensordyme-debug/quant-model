#!/usr/bin/env python
"""C-2: adversarial verification of S-33 (AUD-11), the daily track's 2026-09-12 claim that
"the label is wrong and the number is not".

    py -3.11 scripts/verify_s33.py              # all attacks (~18 min)
    py -3.11 scripts/verify_s33.py --attack 1   # one attack

CRITIC SCOPE. This file runs no new hypothesis, promotes nothing and ships nothing. It
re-derives S-33's numbers with independent code where it can, and attacks the three
sentences of that entry that reach the owner.

THE CLAIMS UNDER ATTACK, quoted from research/journal_daily.md, 2026-09-12
--------------------------------------------------------------------------
  (i)   "Re-selecting on 2012-2019 ... costs -1.865 CAR points on the withheld half at
         -0.569 bps/day over 1,677 sessions, t -2.18 - past |t| = 2, and the first thing on
         this sleeve to get there that is not S-31's arithmetic."
  (ii)  "the only t past 2 sigma this sleeve has produced from an actual book"
  (iii) "Selection on these three axes inflates the published 2020-2026 figure by about
         half a CAR point at zero cost" -> carried into the decision as "right to within
         about half a point in its arithmetic".

PRE-REGISTERED ATTACKS, written before any number below was read
----------------------------------------------------------------
(0) IDENTITY. Reproduce the deployed cell (CAR 22.192150%, 5,052 orders, 2012-2026, 0 bp)
    and the shipped OOS cell (29.124 / 1.262 / 23.855 / 2,267). If either misses, stop:
    every attack below is then measuring a different book.

(1) THE FAMILY THE t BELONGS TO. S-33 reports ONE paired t - the IS-argmax cell against
    shipped - and calls it the only |t| > 2 this sleeve has produced from a book. But that
    cell is one of the 17 non-shipped cells of S-33's own grid, and S-33's clause 5
    establishes that IS rank carries no OOS content (pooled premium -0.049), which makes the
    IS-argmax an effectively RANDOM draw with respect to the OOS difference. So the honest
    reference distribution is the paired t of ALL 17 cells against shipped. Compute every
    one. REFUTED IF: two or more other cells reach |t| >= 2, i.e. |t| > 2 is the ordinary
    consequence of moving a dial on 1,677 paired sessions rather than a fact about the
    audit's remedy. CONFIRMED IF: -2.18 is the extreme or near-extreme of the family.

(2) AUTOCORRELATION. `sweep_s19.tstat` is the iid Student t - mean / (sd / sqrt(n)) - with
    no correction. A daily long/short rotation book differenced against a near-copy of
    itself can carry serial dependence in the difference (both books rebalance on the same
    dates and hold overlapping names for weeks). Recompute t with Newey-West at lags 5, 10
    and 21, and with a stationary bootstrap (10,000 resamples, mean block 10). REFUTED IF
    the corrected |t| drops below 2. CONFIRMED IF it holds at every lag.

(3) THE ERROR BAR ON "HALF A CAR POINT". S-33 estimates the selection inflation as the
    shipped cell's OOS CAR minus the grid's central tendency (+0.492 against the median,
    +0.974 against the mean) and reports it as a point estimate with no dispersion. The
    grid's own sd is 1.832. State the inflation with its error bar and report whether it is
    distinguishable from zero. REFUTED IF |estimate| < 1 sd of the reference distribution,
    i.e. the quoted half-point is noise and the sentence the owner should carry is about
    the DISPERSION, not the bias.

(4) LOOK-AHEAD, by construction rather than by reading. `legs_simulate` receives the FULL
    1998-2026 price frames and slices with `i0 = searchsorted(start) + 1`, so a full-sample
    statistic anywhere in the signal or the sizing would leak silently into every window.
    Test it the only way that cannot be argued with: truncate the frames at a cut date T,
    re-run OOS_START..T, and compare against the full-frame run restricted to the same
    dates. REFUTED IF any daily return differs. CONFIRMED IF the two books are bit-identical.

(5) THE GAP'S OWN RANK. -1.865 CAR points is quoted as the cost of the audit's remedy.
    Where does it sit in the distribution of (cell OOS CAR - shipped OOS CAR) over the 17
    non-shipped cells? Reported whatever it says.

DIAGNOSTIC. No shipped or runner-loaded file is touched; nothing is written to the ledger,
to champion.json or to live/.
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                                          # noqa: E402
from lean_prices import load_ohlcv                             # noqa: E402
from sweep_s25 import legs_simulate                            # noqa: E402
from sweep_s31 import describe                                 # noqa: E402
from sweep_s19 import tstat                                    # noqa: E402
from sweep_s33 import AXES, SHIPPED, WINDOWS, make_params, cell_name  # noqa: E402

S25_DEPLOYED_CAR = 22.192150170492255
S25_DEPLOYED_ORDERS = 5052
S33_SHIPPED_OOS_CAR = 29.124229434905136
S33_IS_SELECTED = {"alloc_vol_window": 10}
S33_GAP = -1.865
S33_T = -2.18
S33_BPS = -0.569


# ------------------------------------------------------------------- independent statistics

def nw_tstat(x: np.ndarray, lag: int) -> float:
    """Newey-West t for the mean of a serially-dependent series (Bartlett kernel)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    e = x - x.mean()
    s = float(e @ e) / n
    for l in range(1, lag + 1):
        g = float(e[l:] @ e[:-l]) / n
        s += 2.0 * (1.0 - l / (lag + 1.0)) * g
    if s <= 0:
        return float("nan")
    return float(x.mean() / np.sqrt(s / n))


def stationary_bootstrap_t(x: np.ndarray, *, block: float = 10.0,
                           reps: int = 10000, seed: int = 0) -> tuple[float, float]:
    """Politis-Romano stationary bootstrap. Returns (p two-sided, implied |t|).

    The null is imposed by centring: resample the demeaned series and ask how often the
    resampled mean is at least as far from zero as the observed one.
    """
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    obs = x.mean()
    c = x - obs
    rng = np.random.default_rng(seed)
    p_geom = 1.0 / block
    starts = rng.integers(0, n, size=(reps, n))
    jumps = rng.random((reps, n)) < p_geom
    idx = np.empty((reps, n), dtype=np.int64)
    idx[:, 0] = starts[:, 0]
    for j in range(1, n):
        idx[:, j] = np.where(jumps[:, j], starts[:, j], (idx[:, j - 1] + 1) % n)
    means = c[idx].mean(axis=1)
    p = float((np.abs(means) >= abs(obs)).mean())
    p = max(p, 1.0 / reps)
    # implied two-sided normal |t|
    from math import erfc, sqrt
    lo, hi = 0.0, 12.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if erfc(mid / sqrt(2.0)) > p:
            lo = mid
        else:
            hi = mid
    return p, 0.5 * (lo + hi)


def ac(x: np.ndarray, lag: int) -> float:
    x = np.asarray(x, dtype=float)
    e = x - x.mean()
    return float((e[lag:] @ e[:-lag]) / (e @ e))


def paired_diff(a: pd.DataFrame, b: pd.DataFrame) -> np.ndarray:
    """bps of daily return difference, paired on date. Independent of sweep_s19.paired."""
    m = a[["date", "ret"]].merge(b[["date", "ret"]], on="date", suffixes=("_a", "_b"))
    assert len(m) == len(a) == len(b), f"pairing lost rows: {len(m)} vs {len(a)}/{len(b)}"
    return 1e4 * (m["ret_a"] - m["ret_b"]).to_numpy()


def all_cells() -> list[dict]:
    """The 18 unique cells of S-33's coordinate grid, shipped first."""
    out = [{"over": {}, "name": "shipped", "axis": "-", "value": "-"}]
    seen = {()}
    for axis, values in AXES.items():
        for v in values:
            if v == SHIPPED[axis]:
                continue
            over = {axis: v}
            key = tuple(sorted(over.items()))
            if key in seen:
                continue
            seen.add(key)
            out.append({"over": over, "name": cell_name(over), "axis": axis, "value": v})
    return out


# ------------------------------------------------------------------------------- attack 0

def attack_0(frames: dict) -> dict:
    print("=== attack 0: identity - is this S-33's book? ===")
    t0 = time.time()
    full = describe(legs_simulate(frames, sig.Params(), "both", *WINDOWS["FULL"], 0.0, None),
                    "shipped @ FULL")
    oos_book = legs_simulate(frames, sig.Params(), "both", *WINDOWS["OOS"], 0.0, None)
    oos = describe(oos_book, "shipped @ OOS")
    ok_full = abs(full["CAR"] - S25_DEPLOYED_CAR) < 1e-9 and full["orders"] == S25_DEPLOYED_ORDERS
    ok_oos = abs(oos["CAR"] - S33_SHIPPED_OOS_CAR) < 1e-9 and oos["orders"] == 2267
    print(f"  FULL 2012-2026  CAR {full['CAR']:.6f}%  orders {full['orders']:,}   "
          f"(S-25..S-32: {S25_DEPLOYED_CAR:.6f}% / {S25_DEPLOYED_ORDERS:,})  "
          f"-> {'MATCH' if ok_full else 'MISMATCH'}")
    print(f"  OOS  2020-2026  CAR {oos['CAR']:.6f}%  Sharpe {oos['Sharpe']:.3f}  "
          f"DD {oos['MaxDD']:.3f}%  orders {oos['orders']:,}  "
          f"-> {'MATCH' if ok_oos else 'MISMATCH'}")
    print(f"  [{time.time() - t0:.0f}s]\n")
    return {"ok": ok_full and ok_oos, "oos_book": oos_book, "oos": oos}


# ------------------------------------------------------------------------- attacks 1 and 5

def attack_1_5(frames: dict, base_book: pd.DataFrame) -> dict:
    print("=== attacks 1 and 5: the family the t and the gap belong to ===")
    print("  every non-shipped cell of S-33's own grid, paired against shipped on 2020-2026\n")
    base = describe(base_book, "shipped")
    rows = []
    t0 = time.time()
    for c in all_cells():
        if not c["over"]:
            continue
        b = legs_simulate(frames, make_params(**c["over"]), "both", *WINDOWS["OOS"], 0.0, None)
        d = describe(b, c["name"])
        diff = paired_diff(b, base_book)
        rows.append({**c, "CAR": d["CAR"], "gap": d["CAR"] - base["CAR"],
                     "bps": float(diff.mean()), "t": tstat(diff),
                     "t_nw10": nw_tstat(diff, 10), "diff": diff, "orders": d["orders"]})
    print(f"  ({len(rows)} cells, {time.time() - t0:.0f}s)\n")

    rows.sort(key=lambda r: r["t"])
    hdr = (f"{'cell':<26}{'OOS CAR%':>10}{'gap vs shipped':>16}{'bps/day':>10}"
           f"{'t (iid)':>10}{'t (NW10)':>10}{'|t|>=2':>8}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        mark = "  <-- S-33's quoted cell" if r["over"] == S33_IS_SELECTED else ""
        print(f"{r['name']:<26}{r['CAR']:>10.3f}{r['gap']:>+16.3f}{r['bps']:>+10.3f}"
              f"{r['t']:>+10.2f}{r['t_nw10']:>+10.2f}"
              f"{('YES' if abs(r['t']) >= 2 else '-'):>8}{mark}")
    print("-" * len(hdr))

    sig2 = [r for r in rows if abs(r["t"]) >= 2]
    quoted = next(r for r in rows if r["over"] == S33_IS_SELECTED)
    order = sorted(rows, key=lambda r: -abs(r["t"]))
    rank = 1 + order.index(quoted)
    print(f"\n  cells of the 17 with iid |t| >= 2 : {len(sig2)}  "
          f"({', '.join(r['name'] for r in sig2)})")
    print(f"  S-33's quoted cell ranks {rank} of 17 by |t|; the family max is "
          f"|t| = {abs(order[0]['t']):.2f} ({order[0]['name']})")
    gaps = np.array([r["gap"] for r in rows])
    print(f"\n  attack 5 - the gap's rank: -1.865 is {1 + sorted(gaps).index(quoted['gap'])} "
          f"of 17 from the bottom; gap distribution min {gaps.min():+.3f} "
          f"median {np.median(gaps):+.3f} max {gaps.max():+.3f}")
    print(f"  cells WORSE than the audit's remedy: "
          f"{int((gaps < quoted['gap']).sum())} of 17\n")
    return {"rows": rows, "quoted": quoted, "n_sig": len(sig2), "rank": rank,
            "family_max": abs(order[0]["t"]), "family_max_name": order[0]["name"]}


# ------------------------------------------------------------------------------- attack 2

def attack_2(quoted: dict) -> dict:
    print("=== attack 2: is the iid t honest about serial dependence? ===")
    d = quoted["diff"]
    print(f"  series: IS-selected minus shipped, {len(d)} sessions, "
          f"mean {d.mean():+.4f} bps/day (S-33: {S33_BPS:+.3f})")
    print(f"  S-33 reports t {S33_T:+.2f} using sweep_s19.tstat (iid Student t)\n")
    print(f"  autocorrelation of the difference: "
          + "  ".join(f"r{l} {ac(d, l):+.3f}" for l in (1, 2, 5, 10, 21)))
    out = {"iid": tstat(d)}
    print(f"\n  {'estimator':<34}{'t':>9}{'|t|>=2':>9}")
    print("  " + "-" * 50)
    print(f"  {'iid (S-33s own)':<34}{out['iid']:>+9.2f}"
          f"{('YES' if abs(out['iid']) >= 2 else 'no'):>9}")
    for lag in (5, 10, 21):
        t = nw_tstat(d, lag)
        out[f"nw{lag}"] = t
        print(f"  {'Newey-West lag ' + str(lag):<34}{t:>+9.2f}"
              f"{('YES' if abs(t) >= 2 else 'no'):>9}")
    p, timp = stationary_bootstrap_t(d, block=10.0, reps=10000, seed=0)
    out["boot_p"], out["boot_t"] = p, timp
    print(f"  {'stationary bootstrap (block 10)':<34}{timp:>+9.2f}"
          f"{('YES' if timp >= 2 else 'no'):>9}   p = {p:.4f}")
    print()
    return out


# ------------------------------------------------------------------------------- attack 3

def attack_3(rows: list[dict], base: dict) -> dict:
    print("=== attack 3: the error bar S-33 did not put on 'about half a CAR point' ===")
    oos = np.array([base["CAR"]] + [r["CAR"] for r in rows])
    med, mean, sd = float(np.median(oos)), float(oos.mean()), float(oos.std(ddof=1))
    vs_med = base["CAR"] - med
    vs_mean = base["CAR"] - mean
    pct = 100.0 * (oos < base["CAR"]).mean()
    print(f"  18 unique cells: min {oos.min():.3f}  median {med:.3f}  mean {mean:.3f} "
          f"(sd {sd:.3f})  max {oos.max():.3f}")
    print(f"  shipped {base['CAR']:.3f}  ->  {vs_med:+.3f} vs median, {vs_mean:+.3f} vs mean, "
          f"{pct:.0f}th percentile")
    print(f"\n  S-33 quotes {vs_med:+.3f} (median) / {vs_mean:+.3f} (mean) as THE selection")
    print(f"  inflation and carries 'right to within about half a point' into its decision.")
    print(f"  In units of the grid's own dispersion that is "
          f"{abs(vs_med) / sd:.2f} sd (median) / {abs(vs_mean) / sd:.2f} sd (mean).")
    se = sd / np.sqrt(len(oos))
    print(f"  se of the grid mean = {se:.3f}, so vs-mean is {abs(vs_mean) / se:.2f} se.")
    refuted = abs(vs_med) < sd
    print(f"\n  -> the point estimate is {'INSIDE' if refuted else 'OUTSIDE'} one sd of the")
    print(f"     reference dispersion. Honest sentence for the owner: the selection BIAS on")
    print(f"     these three axes is indistinguishable from zero; the selection UNCERTAINTY")
    print(f"     is +/- {sd:.1f} CAR points (1 sd), a {oos.max() - oos.min():.1f}-point range.\n")
    return {"median": med, "mean": mean, "sd": sd, "vs_med": vs_med, "vs_mean": vs_mean,
            "pct": pct, "refuted": refuted}


# ------------------------------------------------------------------------------- attack 4

def attack_4(frames: dict, base_book: pd.DataFrame) -> dict:
    print("=== attack 4: look-ahead, by truncation rather than by reading ===")
    cut = "2023-06-30"
    trunc = {k: v.loc[:pd.Timestamp(cut)].copy() for k, v in frames.items()
             if isinstance(v, pd.DataFrame)}
    for k in frames:
        if k not in trunc:
            trunc[k] = frames[k]
    print(f"  frames truncated at {cut}: "
          f"{frames['close'].shape[0]} -> {trunc['close'].shape[0]} sessions")
    b_tr = legs_simulate(trunc, sig.Params(), "both", WINDOWS["OOS"][0], cut, 0.0, None)
    b_fu = legs_simulate(frames, sig.Params(), "both", WINDOWS["OOS"][0], cut, 0.0, None)
    m = b_tr[["date", "ret"]].merge(b_fu[["date", "ret"]], on="date", suffixes=("_t", "_f"))
    worst = float(np.abs(m["ret_t"] - m["ret_f"]).max()) if len(m) else float("nan")
    same_n = len(b_tr) == len(b_fu) == len(m)
    ok = same_n and worst == 0.0
    print(f"  sessions: truncated {len(b_tr)}, full-frame {len(b_fu)}, paired {len(m)}")
    print(f"  max |daily return difference| = {worst:.3e}")
    print(f"  -> {'NO LOOK-AHEAD (bit-identical)' if ok else 'DIFFERENCE FOUND - investigate'}\n")
    return {"ok": ok, "worst": worst, "n": len(m)}


# ----------------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--attack", type=int, default=None)
    args = ap.parse_args()

    p = sig.Params()
    frames = load_ohlcv(sig.traded_universe(p))
    print(f"store: {len(sig.traded_universe(p))} tickers, "
          f"{frames['close'].index[0].date()} .. {frames['close'].index[-1].date()}")
    print(f"IS {WINDOWS['IS'][0]}..{WINDOWS['IS'][1]}   "
          f"OOS {WINDOWS['OOS'][0]}..{WINDOWS['OOS'][1]}\n")

    a0 = attack_0(frames)
    if not a0["ok"]:
        print("attack 0 FAILED - this is not S-33's book. Everything below would be "
              "measuring something else. Stop.")
        return 1

    if args.attack == 4:
        attack_4(frames, a0["oos_book"])
        return 0

    a15 = attack_1_5(frames, a0["oos_book"])
    a2 = attack_2(a15["quoted"])
    a3 = attack_3(a15["rows"], a0["oos"])
    a4 = attack_4(frames, a0["oos_book"])

    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    print(f"  attack 0 identity ................. REPRODUCED to the digit")
    print(f"  attack 1 the t's family ........... "
          f"{'REFUTES' if a15['n_sig'] >= 3 else 'survives'}: {a15['n_sig']} of 17 cells "
          f"reach |t| >= 2; the quoted cell ranks {a15['rank']} of 17 "
          f"(family max |t| {a15['family_max']:.2f})")
    nw_ok = all(abs(a2[k]) >= 2 for k in ("nw5", "nw10", "nw21"))
    print(f"  attack 2 autocorrelation .......... "
          f"{'survives' if nw_ok else 'REFUTES'}: NW t "
          f"{a2['nw5']:+.2f}/{a2['nw10']:+.2f}/{a2['nw21']:+.2f}, "
          f"bootstrap p {a2['boot_p']:.4f}")
    print(f"  attack 3 the half-point's error bar "
          f"{'REFUTES' if a3['refuted'] else 'survives'}: {a3['vs_med']:+.3f} vs median "
          f"against a grid sd of {a3['sd']:.3f}")
    print(f"  attack 4 look-ahead ............... "
          f"{'survives (clean)' if a4['ok'] else 'REFUTES'}: "
          f"max |dret| {a4['worst']:.3e} over {a4['n']} sessions")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
