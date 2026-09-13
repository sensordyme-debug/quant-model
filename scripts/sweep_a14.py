#!/usr/bin/env python
"""A-14: is the ORB time stop pure cost, or is `stop368` the 2020-2023 regime?

    py -3.14 scripts/sweep_a14.py                 # the whole page
    py -3.14 scripts/sweep_a14.py --record        # + DIAGNOSTIC ledger rows

No backtest runs here. Every number is computed from the daily series A-8 already persisted
(`results/a8/daily_<cell>.csv`, 2,686 sessions x five `time_stop` cells) plus the VIX levels
S-29's `regime_data.py` wrote to `data/regime/vix.csv`. That is the whole point of the item:
A-8's grid is on disk, so the question can be asked without fitting anything new.

Why this exists
---------------
A-8 swept `time_stop` over {120, 180, 240 (shipped), 300, 368 (= the 15:38 flatten)} on the
2,686-session Alpaca store and found the ladder **monotone with no interior optimum**: the
sleeve's eleven-year loss goes -$954 -> -$340 -> -$324 -> -$160 -> **+$81** per day as the stop is
loosened, drawdown halves from 69.6% to 40.2%, and turnover is *flat* (35.1 vs 34.9 trades/day)
with costs *rising* ($998 vs $913), so none of it is a trade-reduction artifact.

A-8 refused `stop368` anyway, and correctly, because its whole significance is one regime:
paired +139.9 / **+990.7** / -76.3 $/day at t +0.91 / **+2.80** / -0.24 over 2016-2019 /
2020-2023 / 2024-2026. A three-regime paired test cannot tell those two stories apart:

* **"pure cost"** - the 240-minute stop truncates breakouts that were still working, so removing
  it should pay a stable amount in every period, and the 2020-2023 spike is just the period where
  the same mechanism had the most volatility to work with.
* **"one regime"** - the stop is roughly free, and 2020-2023 is a single volatile episode that
  happened to reward holding, which is why the newest regime disagrees in sign.

A-8's own decision rule counts regimes; it cannot separate these. The honest test is the harness's
own `--split`: fit nothing, choose the constant on 2016-2023, and ask whether it beats the control
on 2024-01-01 onward. That is this script.

Nothing here is deployable even if it passes. The sleeve's own book is at t +0.25 over eleven
years and runs at `equity_frac` 0.25 as a plumbing test; A-14 decides how the A-track *closes*,
not what it ships.

Decision rule, fixed before any number was read
----------------------------------------------
1. **Identity.** The on-disk series must reproduce A-8's published table - control book $/day by
   regime (-262 / -512 / -134), `stop368` paired by regime (+139.9 / +990.7 / -76.3 at
   t +0.91 / +2.80 / -0.24), full-period paired +405, book +$81/day at t +0.25, Sharpe 0.14,
   DD 40.2%. Tolerance 1 $/day, 0.02 t, 0.2 points of Sharpe/DD. A mismatch means the files are
   not the ones the journal describes and nothing below is comparable.
2. **In-sample selection.** On **2016-01-01..2023-12-31 only**, take the argmax of the existing
   ladder by paired mean $/day against the control. Whatever wins is carried unchanged to
   clause 3; no second axis, no re-fit, no post-hoc cell.
3. **THE DECISION (out of sample).** Paired daily difference (selected - control) over
   **2024-01-01..2026-12-31**. PASS requires mean > 0 **and** t > +2 **and** a stationary
   bootstrap one-sided p < 0.05. Anything else refuses "pure cost".
4. **Book level, out of sample.** The selected cell's own book on the OOS half: $/day > 0 at
   t > 2, drawdown no worse than the control's. Reported whether or not clause 3 passes, because
   a paired win on a book that still loses money is not a result.
5. **Power, and it can veto the reading of clause 3.** Two-sided 95% CI of the OOS paired mean.
   If that interval contains **both** zero and the IS point estimate, the OOS half cannot
   distinguish "pure cost" from "no effect" at all, and the verdict is UNDECIDED rather than
   REFUSED - a difference that matters, because REFUSED closes the item on evidence and UNDECIDED
   closes it on the sample. Report the sessions needed to resolve the IS estimate at 2 se.
6. **Homogeneity - the actual "pure cost vs one regime" discriminator.** (a) paired mean and t per
   calendar year, and the count of positive years; (b) the share of the full-period cumulative
   difference contributed by 2020-2023 and by the single best 1% of sessions - **>60% from one
   regime, or >50% from the top 1% of days, refutes "pure cost"**; (c) the spread of the three
   regime means against their pooled standard error.
7. **Mechanism, conditioned causally.** The previous session's VIX close (`data/regime/vix.csv`,
   S-29; row `d` is the level at the close of `d`, so lagging one session is strictly causal).
   (a) OLS of the daily paired difference on lagged VIX, slope and t; (b) the paired mean in each
   lagged-VIX tercile with **the tercile cuts solved on the IS half alone**; (c) the conditional
   rule - hold to the flatten only when lagged VIX is above its IS median, otherwise keep the
   shipped stop - scored out of sample as a paired difference against the control. "Pure cost"
   predicts a flat slope and a positive mean in every tercile; "one regime" predicts a positive
   slope with the low tercile at or below zero.
8. **Nothing ships.** Analysis only: no backtest, no shipped, runner-loaded or scheduled file
   touched, no `live/` file read or written, `live/intraday_config.json` unchanged. With
   `--record` the script appends DIAGNOSTIC rows to the ledger and nothing else.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

REPO = HERE.parent
A8 = REPO / "results" / "a8"
OUT = REPO / "results" / "a14"
VIX_CSV = REPO / "data" / "regime" / "vix.csv"

EQUITY = 1_000_000.0
#: The ladder A-8 ran. `control` is the shipped time_stop=240.
LADDER = {"stop120": 120, "stop180": 180, "control": 240, "stop300": 300, "stop368": 368}
#: A-8's three a-priori regimes, kept only so clause 1 can check the identity.
REGIMES = [("2016-2019", 2016, 2019), ("2020-2023", 2020, 2023), ("2024-2026", 2024, 2026)]
#: The split the item names. IS = everything A-8 could have selected on; OOS = withheld.
SPLIT = dt.date(2024, 1, 1)

#: A-8's published figures (journal 2026-09-12, `results/a8/books.csv` + `paired.csv`).
PUBLISHED_BOOK = {"control": (-262.0, -512.0, -134.0), "stop368": (-122.0, 479.0, -210.0)}
PUBLISHED_PAIRED = {"stop368": ((139.9, 0.91), (990.7, 2.80), (-76.3, -0.24))}
PUBLISHED_FULL = {"stop368": {"d$/day": 405.0, "$/day": 81.0, "t": 0.25, "sharpe": 0.14,
                              "dd": 40.2}}

BOOT_N = 20_000
BOOT_BLOCK = 10.0  # mean block length of the stationary bootstrap, in sessions
RNG_SEED = 14


# ------------------------------------------------------------------------------- statistics
def tstat(x: np.ndarray) -> tuple[float, float, float]:
    """(mean, standard error, t) of a sample."""
    n = len(x)
    if n < 2:
        return float("nan"), float("nan"), float("nan")
    se = float(x.std(ddof=1) / np.sqrt(n))
    m = float(x.mean())
    return m, se, (m / se if se else float("nan"))


def book_stats(d: pd.DataFrame) -> dict:
    """Pooled book statistics; identical convention to `sweep_a10.stats` (yearly-reset $1M book)."""
    n = len(d)
    pnl, ret = d["pnl"].values, d["ret"].values
    m, se, t = tstat(pnl)
    eq = EQUITY * np.cumprod(1.0 + ret)
    path = np.concatenate([[EQUITY], eq])
    peak = np.maximum.accumulate(path)
    sd = ret.std(ddof=1)
    return {"sessions": n, "$/day": m, "se": se, "t": t,
            "sharpe": float(ret.mean() / sd * np.sqrt(252)) if sd else float("nan"),
            "max_dd_pct": -float((path / peak - 1.0).min()) * 100,
            "net_pct": float(np.prod(1.0 + ret) - 1.0) * 100,
            "worst_day": float(pnl.min()), "win_days_pct": float((pnl > 0).mean() * 100)}


def stationary_bootstrap(x: np.ndarray, n_boot: int, mean_block: float, seed: int) -> np.ndarray:
    """Politis-Romano stationary bootstrap of the sample mean.

    The daily differences are serially dependent (a volatile week moves every cell the same
    way), so the i.i.d. standard error understates. Geometric block lengths with mean
    `mean_block` keep the resample stationary and preserve that dependence.
    """
    rng = np.random.default_rng(seed)
    n = len(x)
    p = 1.0 / mean_block
    idx = rng.integers(0, n, size=(n_boot, n))
    # with probability (1-p) continue the previous block, else jump to a fresh random index
    cont = rng.random((n_boot, n)) > p
    out = np.empty((n_boot, n), dtype=np.int64)
    out[:, 0] = idx[:, 0]
    for j in range(1, n):
        prev = (out[:, j - 1] + 1) % n
        out[:, j] = np.where(cont[:, j], prev, idx[:, j])
    return x[out].mean(axis=1)


def ols(x: np.ndarray, y: np.ndarray) -> dict:
    """Univariate OLS with an intercept; returns slope, its t, and R^2."""
    n = len(x)
    X = np.column_stack([np.ones(n), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = n - 2
    s2 = float(resid @ resid) / dof
    xtx_inv = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(s2 * xtx_inv))
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {"a": float(beta[0]), "b": float(beta[1]), "b_se": float(se[1]),
            "b_t": float(beta[1] / se[1]) if se[1] else float("nan"),
            "r2": 1.0 - float(resid @ resid) / ss_tot if ss_tot else float("nan"), "n": n}


# ------------------------------------------------------------------------------------ data
def load_cells() -> dict[str, pd.DataFrame]:
    out = {}
    for cell in LADDER:
        f = A8 / f"daily_{cell}.csv"
        if not f.exists():
            sys.exit(f"missing {f} - run `python scripts/sweep_a8.py --cells {cell}` first")
        d = pd.read_csv(f)
        d["day"] = pd.to_datetime(d["day"]).dt.date
        out[cell] = d.sort_values("day").reset_index(drop=True)
    days = {c: list(d["day"]) for c, d in out.items()}
    ref = days["control"]
    for c, v in days.items():
        if v != ref:
            sys.exit(f"cell {c} does not trade the same sessions as the control "
                     f"({len(v)} vs {len(ref)}) - the pairing would be invalid")
    return out


def load_vix() -> pd.Series:
    if not VIX_CSV.exists():
        sys.exit(f"missing {VIX_CSV} - run `python scripts/regime_data.py` first")
    v = pd.read_csv(VIX_CSV)
    v["date"] = pd.to_datetime(v["date"]).dt.date
    return v.set_index("date")["vix"].sort_index()


def paired(cell: pd.DataFrame, ctrl: pd.DataFrame) -> np.ndarray:
    m = ctrl[["day", "pnl"]].merge(cell[["day", "pnl"]], on="day", suffixes=("_c", "_x"))
    return (m["pnl_x"] - m["pnl_c"]).values


def slice_days(d: pd.DataFrame, lo: dt.date, hi: dt.date) -> pd.DataFrame:
    return d[(d["day"] >= lo) & (d["day"] <= hi)].reset_index(drop=True)


def table(rows: list[dict], title: str, note: str = "") -> pd.DataFrame:
    t = pd.DataFrame(rows)
    print(f"\n=== {title} ===")
    with pd.option_context("display.width", 220):
        print(t.to_string(index=False))
    if note:
        print(note)
    return t


# ------------------------------------------------------------------------------- the clauses
def clause1(cells: dict) -> bool:
    """Identity against A-8's published table."""
    print("\n" + "=" * 100)
    print("CLAUSE 1 - identity against A-8's published figures")
    print("=" * 100)
    ok = True
    rows = []
    for cell, pub in PUBLISHED_BOOK.items():
        for (name, y0, y1), want in zip(REGIMES, pub):
            s = book_stats(slice_days(cells[cell], dt.date(y0, 1, 1), dt.date(y1, 12, 31)))
            got = round(s["$/day"])
            hit = abs(got - want) <= 1.0
            ok &= hit
            rows.append({"check": f"book {cell} {name} $/day", "published": want, "on disk": got,
                         "ok": hit})
    for cell, pub in PUBLISHED_PAIRED.items():
        for (name, y0, y1), (wd, wt) in zip(REGIMES, pub):
            lo, hi = dt.date(y0, 1, 1), dt.date(y1, 12, 31)
            diff = paired(slice_days(cells[cell], lo, hi), slice_days(cells["control"], lo, hi))
            m, _, t = tstat(diff)
            hit = abs(m - wd) <= 1.0 and abs(t - wt) <= 0.02
            ok &= hit
            rows.append({"check": f"paired {cell} {name}", "published": f"{wd} / t {wt}",
                         "on disk": f"{m:.1f} / t {t:.2f}", "ok": hit})
    for cell, pub in PUBLISHED_FULL.items():
        diff = paired(cells[cell], cells["control"])
        s = book_stats(cells[cell])
        checks = [("full paired d$/day", pub["d$/day"], diff.mean(), 1.0),
                  ("full book $/day", pub["$/day"], s["$/day"], 1.0),
                  ("full book t", pub["t"], s["t"], 0.02),
                  ("full book sharpe", pub["sharpe"], s["sharpe"], 0.2),
                  ("full book DD %", pub["dd"], s["max_dd_pct"], 0.2)]
        for label, want, got, tol in checks:
            hit = abs(got - want) <= tol
            ok &= hit
            rows.append({"check": f"{cell} {label}", "published": want, "on disk": round(got, 2),
                         "ok": hit})
    table(rows, "clause 1: the on-disk series vs the journal")
    print(f"\n  clause 1: {'HOLDS' if ok else 'FAILS'}")
    if not ok:
        sys.exit("clause 1 failed: the persisted cells are not the ones A-8 reported. Stop.")
    return ok


def clause2(cells: dict) -> str:
    """In-sample selection over the ladder, 2016-2023 only."""
    print("\n" + "=" * 100)
    print(f"CLAUSE 2 - in-sample selection, 2016-01-01..{SPLIT - dt.timedelta(days=1)}")
    print("=" * 100)
    lo, hi = dt.date(2016, 1, 1), SPLIT - dt.timedelta(days=1)
    ctrl = slice_days(cells["control"], lo, hi)
    rows = []
    for cell, minutes in LADDER.items():
        d = slice_days(cells[cell], lo, hi)
        diff = paired(d, ctrl)
        m, se, t = tstat(diff)
        s = book_stats(d)
        rows.append({"cell": cell, "time_stop": minutes, "IS d$/day": round(m, 1),
                     "IS d_t": round(t, 2) if t == t else 0.0, "IS book $/day": round(s["$/day"]),
                     "IS book t": round(s["t"], 2), "IS sharpe": round(s["sharpe"], 2),
                     "IS DD %": round(s["max_dd_pct"], 1)})
    t_is = table(rows, "clause 2: the ladder on the in-sample half (2,012 sessions)")
    sel = str(t_is.loc[t_is["IS d$/day"].idxmax(), "cell"])
    print(f"\n  IS argmax = {sel} (time_stop {LADDER[sel]}). Carried to clause 3 unchanged.")
    if sel == "control":
        print("  the shipped stop is its own IS argmax - there is nothing to test out of sample.")
    return sel


def clause345(cells: dict, sel: str) -> dict:
    """The OOS decision, the OOS book, and the power veto."""
    print("\n" + "=" * 100)
    print(f"CLAUSES 3-5 - the decision: {sel} vs control, out of sample from {SPLIT}")
    print("=" * 100)
    is_lo, is_hi = dt.date(2016, 1, 1), SPLIT - dt.timedelta(days=1)
    oos_lo, oos_hi = SPLIT, dt.date(2026, 12, 31)

    d_is = paired(slice_days(cells[sel], is_lo, is_hi), slice_days(cells["control"], is_lo, is_hi))
    d_oos = paired(slice_days(cells[sel], oos_lo, oos_hi),
                   slice_days(cells["control"], oos_lo, oos_hi))
    m_is, se_is, t_is = tstat(d_is)
    m_oos, se_oos, t_oos = tstat(d_oos)

    boot = stationary_bootstrap(d_oos, BOOT_N, BOOT_BLOCK, RNG_SEED)
    p_one = float((boot <= 0).mean())
    b_lo, b_hi = (float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975)))
    ci_lo, ci_hi = m_oos - 1.96 * se_oos, m_oos + 1.96 * se_oos

    table([{"half": "IS 2016-2023", "n": len(d_is), "d$/day": round(m_is, 1),
            "se": round(se_is, 1), "t": round(t_is, 2)},
           {"half": f"OOS {SPLIT.year}-2026", "n": len(d_oos), "d$/day": round(m_oos, 1),
            "se": round(se_oos, 1), "t": round(t_oos, 2)}],
          "clause 3: the paired difference, fit nothing")
    print(f"\n  stationary bootstrap ({BOOT_N:,} resamples, mean block {BOOT_BLOCK:.0f} sessions):")
    print(f"    OOS mean 95% CI  [{b_lo:+.1f}, {b_hi:+.1f}] $/day   one-sided P(mean <= 0) = {p_one:.3f}")
    print(f"    normal 95% CI    [{ci_lo:+.1f}, {ci_hi:+.1f}] $/day")
    c3 = bool(m_oos > 0 and t_oos > 2 and p_one < 0.05)
    print(f"\n  clause 3: {'PASS' if c3 else 'FAIL'}"
          f"  (needs mean > 0, t > +2, bootstrap p < 0.05; got {m_oos:+.1f}, t {t_oos:+.2f}, "
          f"p {p_one:.3f})")

    b_sel = book_stats(slice_days(cells[sel], oos_lo, oos_hi))
    b_ctl = book_stats(slice_days(cells["control"], oos_lo, oos_hi))
    table([{"book": "control", **{k: round(b_ctl[k], 2) for k in
                                  ("sessions", "$/day", "t", "sharpe", "max_dd_pct",
                                   "win_days_pct", "worst_day")}},
           {"book": sel, **{k: round(b_sel[k], 2) for k in
                            ("sessions", "$/day", "t", "sharpe", "max_dd_pct",
                             "win_days_pct", "worst_day")}}],
          "clause 4: the books themselves, out of sample")
    c4 = bool(b_sel["$/day"] > 0 and b_sel["t"] > 2 and b_sel["max_dd_pct"] <= b_ctl["max_dd_pct"])
    print(f"\n  clause 4: {'PASS' if c4 else 'FAIL'}  (needs $/day > 0 at t > 2 and DD no worse "
          f"than the control's {b_ctl['max_dd_pct']:.1f}%)")

    excl_zero = not (ci_lo <= 0 <= ci_hi)
    excl_is = not (ci_lo <= m_is <= ci_hi)
    need_n = int(np.ceil((2.0 * d_is.std(ddof=1) / m_is) ** 2)) if m_is > 0 else -1
    excl_is_boot = not (b_lo <= m_is <= b_hi)
    print("\n  clause 5 (power):")
    print(f"    OOS 95% CI excludes zero?                      {'yes' if excl_zero else 'NO'}")
    print(f"    OOS normal    95% CI excludes the IS estimate ({m_is:+.1f})?  "
          f"{'yes' if excl_is else 'NO'}  (upper {ci_hi:+.1f})")
    print(f"    OOS bootstrap 95% CI excludes the IS estimate ({m_is:+.1f})?  "
          f"{'yes' if excl_is_boot else 'NO'}  (upper {b_hi:+.1f})")
    if excl_is != excl_is_boot:
        print("    -> the two conventions DISAGREE, so clause 5 is read on the bootstrap, which "
              "is the one that\n       respects the serial dependence in daily P&L. The IS "
              "estimate is therefore NOT rejected out of sample.")
    print(f"    minimum effect the OOS half can detect at 2 se: {2 * se_oos:,.0f} $/day "
          f"(the IS estimate is {m_is:+.1f}, i.e. BELOW it)")
    print(f"    sessions needed to resolve the IS estimate at 2 se: {need_n:,} "
          f"({need_n / 252:.1f} years); the OOS half has {len(d_oos):,} ({len(d_oos)/252:.1f} y)")
    # Clause 3 on its own is only informative if the OOS half could have SEEN the IS effect.
    # Read on the bootstrap it could not, so clause 3 alone yields UNDECIDED and the decision
    # is handed to clause 6, which is a statement about where the money is and needs no power.
    c3_informative = excl_zero or excl_is_boot
    if not c3_informative:
        print("    -> the OOS interval contains BOTH zero and the IS estimate: clause 3 alone "
              "cannot tell\n       'pure cost' from 'no effect', and the decision passes to "
              "clause 6.")
    return {"sel": sel, "m_is": m_is, "t_is": t_is, "m_oos": m_oos, "se_oos": se_oos,
            "t_oos": t_oos, "p_boot": p_one, "ci": (ci_lo, ci_hi), "boot_ci": (b_lo, b_hi),
            "c3": c3, "c4": c4, "excl_zero": excl_zero, "excl_is": excl_is,
            "excl_is_boot": excl_is_boot, "c3_informative": c3_informative, "need_n": need_n,
            "book_sel": b_sel, "book_ctl": b_ctl, "d_is": d_is, "d_oos": d_oos}


def clause6(cells: dict, sel: str) -> dict:
    """Homogeneity: is the difference a level, or one episode?"""
    print("\n" + "=" * 100)
    print("CLAUSE 6 - homogeneity: 'pure cost' is a LEVEL, 'one regime' is an EPISODE")
    print("=" * 100)
    ctrl, cell = cells["control"], cells[sel]
    rows = []
    pos = 0
    for y in sorted({d.year for d in ctrl["day"]}):
        lo, hi = dt.date(y, 1, 1), dt.date(y, 12, 31)
        diff = paired(slice_days(cell, lo, hi), slice_days(ctrl, lo, hi))
        m, se, t = tstat(diff)
        pos += m > 0
        rows.append({"year": y, "sessions": len(diff), "d$/day": round(m, 1),
                     "t": round(t, 2), "total $": round(float(diff.sum()))})
    t_year = table(rows, f"clause 6a: {sel} - control, by calendar year")
    n_years = len(rows)
    print(f"\n  positive years: {pos} of {n_years}")

    diff_all = paired(cell, ctrl)
    total = float(diff_all.sum())
    reg_share = {}
    for name, y0, y1 in REGIMES:
        lo, hi = dt.date(y0, 1, 1), dt.date(y1, 12, 31)
        s = float(paired(slice_days(cell, lo, hi), slice_days(ctrl, lo, hi)).sum())
        reg_share[name] = s / total if total else float("nan")
    k = max(1, int(round(0.01 * len(diff_all))))
    top_share = float(np.sort(diff_all)[-k:].sum()) / total if total else float("nan")
    print(f"\n  clause 6b: full-period cumulative difference = ${total:,.0f} over "
          f"{len(diff_all):,} sessions")
    for name, sh in reg_share.items():
        print(f"    {name}: {sh * 100:+6.1f}% of it")
    print(f"    best {k} sessions (top 1%): {top_share * 100:+.1f}% of it")
    worst_reg = max(reg_share, key=lambda n: reg_share[n])
    fails_level = reg_share[worst_reg] > 0.60 or top_share > 0.50
    print(f"\n  clause 6b: 'pure cost' is {'REFUTED' if fails_level else 'not refuted'} "
          f"(>60% from one regime or >50% from the top 1% of days)")

    # A RESTATEMENT of 6b, not a new test: the same pre-registered top-1% quantity read as a
    # payoff shape. If the top 1% carries the whole total, the other 99% of sessions must be
    # net negative, and the mean is then a tail statistic rather than a level.
    shape = {}
    rows = []
    for name, sub in (("full 2016-2026", diff_all), ("IS 2016-2023", paired(
            slice_days(cell, dt.date(2016, 1, 1), SPLIT - dt.timedelta(days=1)),
            slice_days(ctrl, dt.date(2016, 1, 1), SPLIT - dt.timedelta(days=1)))),
            (f"OOS {SPLIT.year}-2026", paired(
                slice_days(cell, SPLIT, dt.date(2026, 12, 31)),
                slice_days(ctrl, SPLIT, dt.date(2026, 12, 31))))):
        kk = max(1, int(round(0.01 * len(sub))))
        trim = np.sort(sub)[:-kk]
        mm, _, tt = tstat(sub)
        tm, _, tt2 = tstat(trim)
        shape[name] = {"mean": mm, "median": float(np.median(sub)), "trimmed": tm,
                       "positive_pct": float((sub > 0).mean() * 100)}
        rows.append({"half": name, "n": len(sub), "mean $": round(mm, 1),
                     "median $": round(float(np.median(sub)), 1),
                     "positive %": round(float((sub > 0).mean() * 100), 1),
                     "mean less best 1% $": round(tm, 1), "t of that": round(tt2, 2)})
    table(rows, "clause 6b restated: is the mean a level or a tail?",
          "  (the trimmed column drops only the best 1% of sessions; nothing else changes)")

    means = []
    for name, y0, y1 in REGIMES:
        lo, hi = dt.date(y0, 1, 1), dt.date(y1, 12, 31)
        d = paired(slice_days(cell, lo, hi), slice_days(ctrl, lo, hi))
        m, se, _ = tstat(d)
        means.append((name, m, se))
    print("\n  clause 6c: the three regime means against their own standard errors")
    for a in range(len(means)):
        for b in range(a + 1, len(means)):
            (na, ma, sa), (nb, mb, sb) = means[a], means[b]
            z = (ma - mb) / np.sqrt(sa ** 2 + sb ** 2)
            print(f"    {na} vs {nb}: {ma:+8.1f} vs {mb:+8.1f}  ->  z {z:+.2f}")
    return {"positive_years": pos, "years": n_years, "regime_share": reg_share,
            "top1_share": top_share, "level_refuted": fails_level, "by_year": t_year,
            "shape": shape}


def clause7(cells: dict, sel: str, vix: pd.Series) -> dict:
    """The mechanism, conditioned on the previous session's VIX (strictly causal)."""
    print("\n" + "=" * 100)
    print("CLAUSE 7 - does the difference buy volatility? (lagged VIX, causal)")
    print("=" * 100)
    ctrl, cell = cells["control"], cells[sel]
    m = ctrl[["day", "pnl"]].merge(cell[["day", "pnl"]], on="day", suffixes=("_c", "_x"))
    m["diff"] = m["pnl_x"] - m["pnl_c"]
    vd = list(vix.index)
    lagged = []
    for day in m["day"]:
        i = np.searchsorted(vd, day)          # first VIX date >= day
        lagged.append(float(vix.iloc[i - 1]) if i >= 1 else float("nan"))
    m["vix_lag"] = lagged
    m = m.dropna(subset=["vix_lag"]).reset_index(drop=True)
    print(f"  matched {len(m):,} sessions to a strictly prior VIX close "
          f"(range {m['vix_lag'].min():.1f}..{m['vix_lag'].max():.1f})")

    is_m = m[m["day"] < SPLIT]
    oos_m = m[m["day"] >= SPLIT]
    rows = []
    for name, sub in (("full", m), ("IS 2016-2023", is_m), (f"OOS {SPLIT.year}-2026", oos_m)):
        r = ols(sub["vix_lag"].values, sub["diff"].values)
        rows.append({"half": name, "n": r["n"], "intercept $": round(r["a"], 1),
                     "slope $/VIX pt": round(r["b"], 1), "slope t": round(r["b_t"], 2),
                     "R^2": round(r["r2"], 4)})
    table(rows, "clause 7a: OLS of the daily difference on the previous session's VIX")

    q1, q2 = float(is_m["vix_lag"].quantile(1 / 3)), float(is_m["vix_lag"].quantile(2 / 3))
    print(f"\n  clause 7b: tercile cuts solved on the IS half alone: "
          f"low < {q1:.2f} <= mid < {q2:.2f} <= high")
    rows = []
    for name, sub in (("IS 2016-2023", is_m), (f"OOS {SPLIT.year}-2026", oos_m)):
        for band, mask in (("low", sub["vix_lag"] < q1),
                           ("mid", (sub["vix_lag"] >= q1) & (sub["vix_lag"] < q2)),
                           ("high", sub["vix_lag"] >= q2)):
            d = sub.loc[mask, "diff"].values
            mm, se, t = tstat(d)
            rows.append({"half": name, "VIX band": band, "n": len(d), "d$/day": round(mm, 1),
                         "t": round(t, 2) if t == t else 0.0})
    table(rows, "clause 7b: the paired difference inside each lagged-VIX tercile")

    med = float(is_m["vix_lag"].median())
    oos_hi_mask = oos_m["vix_lag"] >= med
    cond = np.where(oos_hi_mask, oos_m["diff"].values, 0.0)
    cm, cse, ct = tstat(cond)
    plain_m, _, plain_t = tstat(oos_m["diff"].values)
    print(f"\n  clause 7c: the conditional rule - hold to the flatten only when the prior VIX "
          f"close >= the IS median ({med:.2f}),\n    otherwise keep the shipped 240-minute stop. "
          f"Scored OOS as a paired difference against the control.")
    table([{"rule": f"{sel} always", "n": len(oos_m), "d$/day": round(plain_m, 1),
            "t": round(plain_t, 2)},
           {"rule": f"{sel} when VIX_lag >= {med:.2f}", "n": len(cond),
            "sessions on": int(oos_hi_mask.sum()), "d$/day": round(cm, 1),
            "t": round(ct, 2)}],
          "clause 7c: conditional vs unconditional, out of sample")
    return {"slope_full": rows, "median": med, "cond_d": cm, "cond_t": ct}


# ------------------------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record", action="store_true",
                    help="append DIAGNOSTIC rows to research/experiments.jsonl")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    cells = load_cells()
    vix = load_vix()
    print(f"A-14: {len(cells['control']):,} sessions x {len(LADDER)} time_stop cells, "
          f"read from {A8.relative_to(REPO)} - no backtest runs here.")

    clause1(cells)
    sel = clause2(cells)
    dec = clause345(cells, sel)
    hom = clause6(cells, sel)
    clause7(cells, sel, vix)

    if dec["c3"] and dec["c4"]:
        verdict = "PASS - the time stop is pure cost and the OOS half says so"
    elif hom["level_refuted"]:
        verdict = ("REFUSED - the time stop is NOT pure cost: `stop368` is one regime, and "
                   "clause 6 decides it\n     without needing the power clause 3 does not have")
    elif dec["c3_informative"]:
        verdict = "REFUSED on clause 3"
    else:
        verdict = "UNDECIDED - the OOS half is too short to resolve either story"
    dec["verdict"] = verdict.split(" - ")[0]

    print("\n" + "=" * 100)
    print("VERDICT")
    print("=" * 100)
    print(f"  selected in sample: {sel} (time_stop {LADDER[sel]}), IS paired "
          f"{dec['m_is']:+.1f} $/day at t {dec['t_is']:+.2f}")
    print(f"  out of sample:      {dec['m_oos']:+.1f} $/day at t {dec['t_oos']:+.2f}, "
          f"bootstrap p {dec['p_boot']:.3f}, 95% CI [{dec['ci'][0]:+.1f}, {dec['ci'][1]:+.1f}]")
    print(f"  clause 3 {'PASS' if dec['c3'] else 'FAIL'}"
          f"{'' if dec['c3_informative'] else ' (uninformative: underpowered, clause 5)'} | "
          f"clause 4 {'PASS' if dec['c4'] else 'FAIL'} | "
          f"'pure cost' {'REFUTED' if hom['level_refuted'] else 'not refuted'} by clause 6b "
          f"({hom['positive_years']}/{hom['years']} positive years, "
          f"{hom['top1_share'] * 100:.1f}% of the total in the best 1% of sessions)")
    full = hom["shape"]["full 2016-2026"]
    print(f"  the one number that decides it: the MEDIAN session difference is "
          f"{full['median']:+.1f} $/day and only {full['positive_pct']:.1f}% of sessions are "
          f"positive;\n    drop the best 1% and the whole {full['mean']:+.1f} becomes "
          f"{full['trimmed']:+.1f}.")
    print(f"  => {verdict}")

    pd.DataFrame([{"cell": sel, "m_is": dec["m_is"], "t_is": dec["t_is"], "m_oos": dec["m_oos"],
                   "se_oos": dec["se_oos"], "t_oos": dec["t_oos"], "p_boot": dec["p_boot"],
                   "ci_lo": dec["ci"][0], "ci_hi": dec["ci"][1],
                   "boot_lo": dec["boot_ci"][0], "boot_hi": dec["boot_ci"][1],
                   "need_n": dec["need_n"], "c3_informative": dec["c3_informative"],
                   "positive_years": hom["positive_years"], "top1_share": hom["top1_share"],
                   "median_full": full["median"], "trimmed_full": full["trimmed"],
                   "positive_pct_full": full["positive_pct"],
                   "verdict": dec["verdict"]}]).to_csv(OUT / "decision.csv", index=False)
    hom["by_year"].to_csv(OUT / "by_year.csv", index=False)
    print(f"\n  wrote {(OUT / 'decision.csv').relative_to(REPO)} and "
          f"{(OUT / 'by_year.csv').relative_to(REPO)}")

    if args.record:
        import json
        import intraday_backtest as ib  # noqa: E402  (imported late: only --record needs it)
        halves = [("IS 2016-2023", dt.date(2016, 1, 1), SPLIT - dt.timedelta(days=1)),
                  (f"OOS {SPLIT.year}-2026", SPLIT, dt.date(2026, 12, 31))]
        for name, lo, hi in halves:
            for cellname in ("control", sel):
                d = slice_days(cells[cellname], lo, hi)
                s = book_stats(d)
                diff = paired(d, slice_days(cells["control"], lo, hi))
                dm, _, dt_ = tstat(diff) if len(diff) > 1 else (0.0, 0.0, 0.0)
                # per-year bookkeeping A-8 persisted beside each series
                meta = json.loads((A8 / f"meta_{cellname}.json").read_text())
                yrs = [y for y in meta if lo.year <= int(y) <= hi.year]
                tpd = float(np.mean([meta[y]["trades_per_day"] for y in yrs]))
                cpd = float(np.mean([meta[y]["costs_per_day"] for y in yrs]))
                fake = {"sessions": s["sessions"], "net_profit_pct": s["net_pct"],
                        "cagr_pct": (np.prod(1.0 + d["ret"].values) ** (252 / len(d)) - 1) * 100,
                        "sharpe": s["sharpe"], "max_drawdown_pct": s["max_dd_pct"],
                        "avg_daily_pnl": s["$/day"], "worst_day": s["worst_day"],
                        "trades": int(round(tpd * s["sessions"])), "trades_per_day": tpd,
                        "costs_per_day": cpd,
                        "stopped_days": sum(meta[y]["stopped_days"] for y in yrs)}
                ib.record("active",
                          f"A-14 split test {cellname} [{name}] (time_stop {LADDER[cellname]}, "
                          f"paired {dm:+.1f} $/day at t {dt_:+.2f}, yearly-reset $1M book, "
                          f"DIAGNOSTIC)", fake,
                          {"time_stop": LADDER[cellname], "split": str(SPLIT),
                           "selected_on": "2016-2023"}, lo, hi)
        print("  recorded 4 DIAGNOSTIC rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
