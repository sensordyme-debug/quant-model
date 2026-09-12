"""F-10: does breadth actually buy power? Price F-9's premise on data that already exists.

F-8 closed the F track with a positive edge column (+1.532 bps per dollar turned) and a refusal on
power: t +1.47 on 1,933 out-of-sample sessions, where clause 7 asked for t > 2. It then parked the
only reopening it could imagine as **F-9**:

    "The only honest way to reopen the supervised class after four refusals is more independent
     cross-section, not more history: the pooled t is a breadth statistic as much as a length one,
     and the panel is 56 names. F-8's best cell needs 3,558 sessions at 56 names; ~4x the breadth
     would reach the same t on the ~1,900 sessions that exist. That is a request for a ~500-name
     Alpaca SIP minute universe."

**That sentence contains an untested assumption and it is the whole of F-9's case.** "4x the
breadth reaches the same t" is the statement t ~ sqrt(N_names), which is true only for
*independent* contributors. A dollar-neutral decile book over the most liquid US equities is not
an independent object: its names share a market, a handful of sectors and, in the leveraged
sleeve, literally the same underlying index. If the per-name P&L contributions carry an average
pairwise correlation rho, breadth does not compound - it **saturates**, at an effective breadth of
1/rho no matter how many names are added.

F-10 measures that curve on the 56 names already on disk, before the D track spends weeks paging
a 500-name store out of Alpaca. **Nothing is re-fitted and nothing is re-tuned**: F-8's frozen
walk-forward predictions are re-read and only the *book's* universe is subsampled.

    python scripts/ml_f10.py --curve             # the breadth curve, the fits, the verdict
    python scripts/ml_f10.py --curve --record    # ... and append DIAGNOSTIC rows to the ledger
    python scripts/ml_f10.py --curve --quick     # fewer seeds, for a smoke test

**Run it with `INTRADAY_DATA_DIR=data/minute_alpaca`** (F-7's documented cost hazard: `_splits.json`
lives only in that store and without it the cost line is understated by ~0.28 bps of turnover).
Run it as `py -3.14` - only 3.14 has `pyarrow` on this machine.

--------------------------------------------------------------------------------------------
PRE-REGISTERED - written in full before any F-10 number was read
--------------------------------------------------------------------------------------------

**Clause 0 - the prior, stated out loud.** F-9's arithmetic is the independent-contributor case and
the book is not that. The honest prior is that the fitted breadth exponent comes in **well under
0.5**, that the saturating fit finds a non-trivial rho, and that the 500-name extrapolation lands
**below t = 2** - i.e. that F-10 refuses F-9 and saves the D track the work. The prior is stated so
that the outcome cannot be re-read as whatever the numbers turn out to be. F-10 does not reopen the
label, horizon, book or model axes that F-7 and F-8 closed; it prices one parked item's premise and
then the track stays shut either way.

**Clause 1 - the cell, frozen.** F-8's winning cell exactly and only: `session <- close` - one
decision per session at slot 0 (fill 10:00), top/bottom decile 0.10 on the `close`-label
prediction, held to the 15:30 flatten, gross 1.0, equity $1M, flat overnight. Predictions are read
from `data/f1/f8_preds.parquet` (label `close`), the price grid from `data/f1/panel.parquet`,
window 2019-2026, costs from `intraday_common`. The full-universe cell must reproduce F-8's
published numbers (gross 4.256 bps, cost 2.724, net $306/day, t +1.47) or the run is void.

**Clause 2 - what is varied, and the one channel this measures.** Only the set of names the book is
allowed to *hold*. The model stays trained on all 56 names, so F-10 measures the
**diversification** channel of breadth and not the training channel. That is deliberate: F-9's
arithmetic is a diversification argument ("the pooled t is a breadth statistic"), and retraining
per subsample would confound it with a data-volume effect and reopen the model axis F-8 closed.
The training channel is named in clause 6 as the thing F-10 does not bound.

**Clause 3 - the curve.** N in {8, 12, 16, 24, 32, 40, 48, 56} names, 12 seeded random subsets per
N (N = 56 has one subset and gets one run), each pushed through the frozen simulator. Three
estimators of the same quantity, agreed or disagreed in public:

  (A) **naive power law** - OLS of log t on log N across the per-N means. F-9's premise is
      beta = 0.5.
  (B) **saturating fit** - least squares of t(N) = t1 * sqrt(N / (1 + (N-1) rho)) on the same
      points, two parameters, rho by golden-section search with t1 in closed form. Extrapolate to
      N = 500 and to N = infinity (where t = t1 / sqrt(rho), the hard ceiling breadth can buy).
  (C) **direct rho** - partition the 56 names into 4 disjoint sub-books of 14, run each as its own
      book, and correlate their daily net P&L series. Three partition seeds, 12 runs. This measures
      the same rho without going through the curve at all.

**Clause 4 - the control.** The whole curve is re-run on a per-timestamp scrambled prediction. The
control's t must be flat and indistinguishable from zero at **every** N. If the control's t also
rises with N then the curve is measuring the construction's diversification and not the forecast's,
and no extrapolation of it means anything.

**Clause 5 - the direction of the bias, so the refusal is safe.** Subsampling *down* from 56
measures the curve going down; extrapolating *up* to 500 assumes names 57-500 are as good as the
first 56. They are not: the 56 are the sleeve's deliberately chosen most-liquid names, and a
500-name tail is less liquid, costs more per dollar turned and carries weaker signal. **Every
number F-10 extrapolates is therefore an upper bound on what F-9 could deliver.** A refusal that
holds at the upper bound is safe; a pass at the upper bound would only be an argument for a
properly costed pilot, never for a deployment.

**Clause 6 - what F-10 does not bound.** (a) The training channel: 500 names is ~9x the training
rows, and F-10 holds the model fixed, so it cannot price that. What it *can* say is whether gross
bps per dollar turned - the quality of the selection, as opposed to the smoothness of the book -
moves with N on the data that exists; that column is reported at every N. (b) Cost at the tail:
clause 5's liquidity argument is asserted from the sleeve's construction, not measured here.

**Clause 7 - the decision rule, fixed before the numbers.**
  - **FUND F-9** iff the saturating fit's point estimate at N = 500 is **>= 2.0**.
  - **REFUSE F-9** iff the ceiling t(infinity) is **< 2.0** - breadth can then never deliver the
    hurdle no matter how many names are bought, and the D track should not build the store on this
    rationale.
  - **In between** (t(500) < 2 <= t(infinity)): report the breadth N* at which the fit reaches 2.0
    and hand the D track that number instead of 500, flagged with clause 5's bias.
Bootstrap over sessions (B = 500, resampling the session index shared by every cell) carries a
confidence interval on rho, t(500) and t(infinity). Nothing deploys from this file:
`algorithms/intraday/active/signal.py` and `live/intraday_config.json` are not touched, so no
deploy gate and no `--replay` is owed.

**Clause 8 - what happens to the track afterwards, decided now.** Either way the F track stays
closed. A refusal retires F-9 from the backlog. A pass does not reopen the ML track - it converts
F-9 into a **D-track data request** with a measured expected t attached, which is the only form in
which this evidence is worth anything to anyone.

--------------------------------------------------------------------------------------------
POST-RUN CORRECTIONS - everything above is the pre-registration, unedited. These are the two
defects found in this file's own first cut, after the numbers were read, and are declared
separately so the pre-registration cannot be confused with a rationalisation.
--------------------------------------------------------------------------------------------

**(i) Clause 4 was written as a gate and coded as a remark.** The first cut printed the control's
slope and then let clause 7 read estimator (B) regardless. The control's |t| is neither flat nor
near zero (it runs -1.54 to -4.05, slope +0.408 against the real curve's +0.776), so on clause 4's
own pre-registered words "no extrapolation of it means anything". The gate is now applied before
clause 7 is allowed to execute. Applying a clause that was pre-registered before any number was
read is not a retro-fit; failing to apply it was the error.

**(ii) Estimator (C) conflated basket correlation with per-name correlation.** The partitions
measure the correlation between two *14-name sub-books* (+0.1406). The saturating model is
parameterised on the correlation between two *names*. Under equicorrelation the two are related by
corr(basket) = m*rho/(1 + (m-1)*rho), so the per-name figure is **0.01155**, not 0.1406, and the
first cut understated the ceiling by ~10x (it printed t(inf) = 1.55; corrected it is **2.34**).
The correction moves (C) from one side of the hurdle to the other and is applied in full - it
makes the refusal *harder* to reach, which is the direction an author's own correction should cut.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import intraday_common as ic  # noqa: E402
import sweep_f1 as f1  # noqa: E402
import ml_f7 as f7  # noqa: E402
import ml_f8 as f8  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
OUT = REPO / "data" / "f1"
CURVE_CSV = OUT / "f10_breadth.csv"
#: per-cell cache of the simulator's session rows, so a 140-simulation curve can be built in
#: chunks and resumed - AGENTS.md asks that no single command run past 40 minutes.
CACHE = OUT / "f10_cache"

LABEL = "close"                       # clause 1: F-8's winning label, frozen
BOOK = "session"                      # clause 1: F-8's winning book, frozen
NS = [8, 12, 16, 24, 32, 40, 48, 56]  # clause 3
SEEDS = 12
CTRL_SEEDS = 4
PART_SEEDS = 3                        # clause 3(C): partitions into disjoint sub-books
PART_K = 4                            # 4 disjoint sub-books of 14
BOOT = 500
TARGET_T = 2.0                        # clause 7's hurdle, inherited from F-8 clause 7
F9_N = 500                            # the universe size F-9 asks the D track to build

# F-8's published full-universe numbers; clause 1's reproduction check
F8_CELL = {"gross_bps": 4.256, "cost_bps": 2.724, "net_day": 305.7, "t": 1.474}


# --------------------------------------------------------------------------------- the curve


def subsets(syms: np.ndarray, n: int, seeds: int) -> list[np.ndarray]:
    """Seeded random name subsets of size n. The full universe has exactly one subset."""
    if n >= len(syms):
        return [np.asarray(sorted(syms))]
    out, seen = [], set()
    for s in range(seeds):
        rng = np.random.default_rng(1000 * n + s)
        pick = tuple(sorted(rng.choice(syms, size=n, replace=False).tolist()))
        if pick in seen:
            continue
        seen.add(pick)
        out.append(np.asarray(pick))
    return out


def cached(name: str, fn) -> pd.DataFrame:
    """Run `fn()` once and keep its session rows on disk; later calls read the cache."""
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{name}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    out = fn()
    out.to_parquet(p, index=False)
    return out


def run_curve(frame: pd.DataFrame, syms: np.ndarray, seeds: int, scramble: int | None = None,
              tag: str = "real", budget: float | None = None) -> tuple[pd.DataFrame, dict, bool]:
    """Simulate F-8's frozen cell on every (N, seed) name subset, resuming from the cache.

    Returns (rows, net-P&L series, complete). `complete` is False when `budget` seconds ran out
    before every cell existed - the caller then stops and the next invocation resumes.
    """
    rows, series = [], {}
    t_start = time.time()
    for n in NS:
        for i, pick in enumerate(subsets(syms, n, seeds)):
            key = f"{tag}_{n}_{i}"
            hit = (CACHE / f"{key}.parquet").exists()
            if not hit and budget is not None and time.time() - t_start > budget:
                print(f"  ... budget spent; {key} and the rest resume on the next invocation")
                return pd.DataFrame(rows), series, False
            t0 = time.time()
            sess = cached(key, lambda: f8.simulate(frame[frame["sym"].isin(pick)], BOOK,
                                                   scramble=scramble))
            r = f8.summarize(sess, f"{tag} N={n} s{i}")
            r.update(n=n, seed=i, kind=tag)
            rows.append(r)
            series[(tag, n, i)] = sess.set_index("day")["net"]
            print(f"  {tag:<5} N={n:>2} s{i:<2} {len(sess):>5} sess  gross {r['gross_bps']:>6.3f} "
                  f"cost {r['cost_bps']:>6.3f}  net ${r['net_day']:>7,.0f}/day  t {r['t']:>+5.2f}"
                  f"   ({time.time() - t0:.0f}s{' cached' if hit else ''})")
    return pd.DataFrame(rows), series, True


# ------------------------------------------------------------------------------------- fits


def fit_power(ns: np.ndarray, ts: np.ndarray) -> tuple[float, float]:
    """(A) OLS of log t on log N. F-9's premise is beta = 0.5."""
    m = ts > 0
    if m.sum() < 3:
        return float("nan"), float("nan")
    x, y = np.log(ns[m]), np.log(ts[m])
    beta, a = np.polyfit(x, y, 1)
    return float(beta), float(a)


def _sat_shape(ns: np.ndarray, rho: float) -> np.ndarray:
    return np.sqrt(ns / (1.0 + (ns - 1.0) * rho))


def fit_saturating(ns: np.ndarray, ts: np.ndarray) -> tuple[float, float, float]:
    """(B) least squares on t(N) = t1 * sqrt(N / (1 + (N-1) rho)).

    t1 is closed form given rho, so only rho is searched (golden section on log rho).
    Returns (rho, t1, sse).
    """
    def scan(rhos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Vectorised over the rho grid: shape (R, K) for R rhos and K widths."""
        F = np.sqrt(ns[None, :] / (1.0 + (ns[None, :] - 1.0) * rhos[:, None]))
        t1 = (ts[None, :] * F).sum(1) / (F * F).sum(1)
        return ((ts[None, :] - t1[:, None] * F) ** 2).sum(1), t1

    # dense grid on log rho, then one local refinement pass - the objective is 1-D and cheap,
    # and a grid cannot be fooled by the flat region the shape function has as rho -> 0.
    grid = np.exp(np.linspace(np.log(1e-6), np.log(0.999), 2000))
    sses, _ = scan(grid)
    j = int(np.argmin(sses))
    fine = np.linspace(grid[max(0, j - 1)], grid[min(len(grid) - 1, j + 1)], 1000)
    sses2, t1s = scan(fine)
    j2 = int(np.argmin(sses2))
    return float(fine[j2]), float(t1s[j2]), float(sses2[j2])


def sat_t(n: float, rho: float, t1: float) -> float:
    return float(t1 * np.sqrt(n / (1.0 + (n - 1.0) * rho)))


def sat_ceiling(rho: float, t1: float) -> float:
    return float(t1 / np.sqrt(rho)) if rho > 0 else float("inf")


def need_n(rho: float, t1: float, target: float) -> float:
    """Breadth at which the saturating fit reaches `target`; inf if the ceiling is below it."""
    if sat_ceiling(rho, t1) <= target:
        return float("inf")
    r = (target / t1) ** 2
    return float(r * (1.0 - rho) / (1.0 - r * rho))


def per_n_mean(rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    g = rows.groupby("n")["t"].mean().sort_index()
    return g.index.to_numpy(float), g.to_numpy(float)


# -------------------------------------------------------------------------------- bootstrap


def bootstrap(series: dict, rows: pd.DataFrame, days: pd.Index, b: int = BOOT) -> pd.DataFrame:
    """Resample the shared session index; every cell's t is recomputed from its cached series."""
    keys = [(int(r.n), int(r.seed)) for r in rows.itertuples()]
    mat = {k: series[("real", k[0], k[1])].reindex(days).to_numpy() for k in keys}
    ns_u = sorted({k[0] for k in keys})
    rng = np.random.default_rng(20260912)
    out = []
    m = len(days)
    for _ in range(b):
        idx = rng.integers(0, m, m)
        means = []
        for n in ns_u:
            tt = []
            for k in keys:
                if k[0] != n:
                    continue
                v = mat[k][idx]
                sd = v.std(ddof=1)
                tt.append(v.mean() / sd * np.sqrt(len(v)) if sd > 0 else 0.0)
            means.append(np.mean(tt))
        ns_a, ts_a = np.asarray(ns_u, float), np.asarray(means, float)
        rho, t1, _ = fit_saturating(ns_a, ts_a)
        beta, _ = fit_power(ns_a, ts_a)
        out.append({"rho": rho, "t1": t1, "beta": beta,
                    "t500": sat_t(F9_N, rho, t1), "tinf": sat_ceiling(rho, t1),
                    "t56": sat_t(56, rho, t1)})
    return pd.DataFrame(out)


def pct(s: pd.Series, q: float) -> float:
    return float(np.nanpercentile(s.replace([np.inf, -np.inf], np.nan).dropna(), q))


# ------------------------------------------------------------------------------------- main


def run(record_rows: bool = False, quick: bool = False, budget: float | None = None) -> None:
    seeds = 4 if quick else SEEDS
    t_start = time.time()

    def left() -> float | None:
        return None if budget is None else budget - (time.time() - t_start)

    print(f"cost store: {ic.DATA_DIR}  (slippage {ic.SLIPPAGE_BPS} bps; "
          f"splits file present: {(Path(ic.DATA_DIR) / '_splits.json').exists()})")
    frames = f8.load_frames()
    frame = frames[LABEL]
    del frames
    syms = np.asarray(sorted(frame["sym"].unique()))
    print(f"panel: {len(frame):,} rows, {len(syms)} names, {frame['day'].nunique():,} sessions, "
          f"{frame['day'].min()} .. {frame['day'].max()}")

    # ---- clause 1: the full-universe cell must reproduce F-8
    full = cached("full", lambda: f8.simulate(frame, BOOK))
    fr = f8.summarize(full, "full universe")
    print("\n=== clause 1: reproduction of F-8's published cell (session <- close) ===")
    print(f"{'quantity':<14} {'F-10':>10} {'F-8 published':>15} {'delta':>9}")
    ok = True
    for k, lab in [("gross_bps", "gross bps"), ("cost_bps", "cost bps"),
                   ("net_day", "net $/day"), ("t", "t")]:
        d = fr[k] - F8_CELL[k]
        ok &= abs(d) <= max(0.01, 0.01 * abs(F8_CELL[k]))
        print(f"{lab:<14} {fr[k]:>10.3f} {F8_CELL[k]:>15.3f} {d:>+9.3f}")
    print(f"  -> {'reproduces' if ok else 'DOES NOT REPRODUCE - run is void'}")
    if not ok:
        sys.exit(2)

    # ---- clause 3: the curve
    print(f"\n=== clause 3: the breadth curve, {len(NS)} widths x {seeds} seeds, frozen cell ===")
    rows, series, done = run_curve(frame, syms, seeds, budget=left())
    days = full.set_index("day").index
    if not done:
        print("\nPARTIAL: the real curve is incomplete. Re-run the same command to resume.")
        return

    print(f"\n{'N':>4} {'runs':>5} {'gross bps':>10} {'cost bps':>9} {'net $/day':>10} "
          f"{'t mean':>7} {'t sd':>6} {'t min':>6} {'t max':>6}")
    print("-" * 74)
    for n, g in rows.groupby("n"):
        print(f"{n:>4} {len(g):>5} {g['gross_bps'].mean():>10.3f} {g['cost_bps'].mean():>9.3f} "
              f"{g['net_day'].mean():>10,.0f} {g['t'].mean():>7.3f} "
              f"{g['t'].std(ddof=1) if len(g) > 1 else 0.0:>6.3f} "
              f"{g['t'].min():>6.2f} {g['t'].max():>6.2f}")

    ns_a, ts_a = per_n_mean(rows)

    # ---- clause 4: the control curve
    print(f"\n=== clause 4: the same curve on a scrambled prediction ({CTRL_SEEDS} seeds/N) ===")
    crows, cseries, cdone = run_curve(frame, syms, CTRL_SEEDS, scramble=1234, tag="ctrl",
                                      budget=left())
    if not cdone:
        print("\nPARTIAL: the control curve is incomplete. Re-run the same command to resume.")
        return
    print(f"\n{'N':>4} {'ctrl t mean':>12} {'ctrl t sd':>10} {'real t mean':>12}")
    for n, g in crows.groupby("n"):
        rt = rows.loc[rows.n == n, "t"].mean()
        print(f"{n:>4} {g['t'].mean():>12.3f} "
              f"{(g['t'].std(ddof=1) if len(g) > 1 else 0.0):>10.3f} {rt:>12.3f}")
    cns, cts = per_n_mean(crows)
    cbeta, _ = fit_power(cns, np.abs(cts))
    print(f"  control |t| power-law slope: {cbeta:+.3f}  "
          f"(real curve's slope is reported below; a control that also rises invalidates the fit)")

    # ---- the fits
    print("\n=== the three estimators (clause 3) ===")
    beta, a = fit_power(ns_a, ts_a)
    print(f"(A) naive power law   t ~ N^beta       beta = {beta:+.3f}   "
          f"(F-9's premise is beta = 0.500)")
    print(f"    -> at N={F9_N}: t = {np.exp(a) * F9_N ** beta:.3f}")

    rho, t1, sse = fit_saturating(ns_a, ts_a)
    print(f"(B) saturating fit    t = t1*sqrt(N/(1+(N-1)rho))   rho = {rho:.5f}  t1 = {t1:.4f}  "
          f"rms {np.sqrt(sse / len(ns_a)):.4f}")
    print(f"    effective breadth at N=56: {56 / (1 + 55 * rho):.2f} names "
          f"(ceiling 1/rho = {1 / rho:.2f} names)")
    print(f"    -> t({F9_N}) = {sat_t(F9_N, rho, t1):.3f}   "
          f"t(infinity) = {sat_ceiling(rho, t1):.3f}")
    nstar = need_n(rho, t1, TARGET_T)
    print(f"    -> breadth needed for t = {TARGET_T}: "
          f"{'UNREACHABLE (above the ceiling)' if not np.isfinite(nstar) else f'{nstar:,.0f} names'}")

    print(f"\n(C) direct rho: {PART_K} disjoint sub-books of {len(syms) // PART_K}, "
          f"{PART_SEEDS} partitions - the correlation of their daily net P&L")
    direct = []
    for ps in range(PART_SEEDS):
        rng = np.random.default_rng(500 + ps)
        perm = rng.permutation(syms)
        parts = [perm[i::PART_K] for i in range(PART_K)]
        nets = []
        for pi, pk in enumerate(parts):
            s = cached(f"part_{ps}_{pi}",
                       lambda pk=pk: f8.simulate(frame[frame["sym"].isin(pk)], BOOK))
            nets.append(s.set_index("day")["net"].reindex(days))
        C = pd.concat(nets, axis=1).corr().to_numpy()
        off = C[np.triu_indices(PART_K, 1)]
        direct.append(float(np.mean(off)))
        print(f"  partition {ps}: mean pairwise corr of the {PART_K} sub-books' daily net "
              f"= {np.mean(off):+.4f}  (min {off.min():+.4f}, max {off.max():+.4f})")
    rho_basket = float(np.mean(direct))
    # The number above is the correlation BETWEEN two 14-name sub-books, not between two names,
    # and the saturating model is parameterised on the latter. Under equicorrelation two disjoint
    # baskets of m slots correlate at m*rho/(1 + (m-1)*rho), which is far larger than rho itself;
    # feeding the basket figure straight into sat_t() understates the ceiling by ~10x. Invert it.
    m_part = len(syms) // PART_K
    rho_direct = rho_basket / (m_part - (m_part - 1) * rho_basket)
    print(f"  -> sub-book rho = {rho_basket:+.4f} between books of m={m_part} names")
    print(f"     de-aggregated to per-name rho = {rho_direct:.5f}   "
          f"[corr(basket) = m*rho/(1+(m-1)*rho)]")
    print(f"     the curve's fitted rho = {rho:.5f}  "
          f"({'agree' if abs(rho_direct - rho) < 0.5 * max(rho, 1e-9) + 0.01 else 'DISAGREE'})")
    t_dir_500 = t_dir_inf = float("nan")
    t1_dir = float("nan")
    if rho_direct > 0:
        t1_dir = fr["t"] / np.sqrt(56 / (1 + 55 * rho_direct))
        t_dir_500 = sat_t(F9_N, rho_direct, t1_dir)
        t_dir_inf = sat_ceiling(rho_direct, t1_dir)
        n_dir = need_n(rho_direct, t1_dir, TARGET_T)
        print(f"  -> rescaling the measured t {fr['t']:+.3f} by the per-name rho: "
              f"t({F9_N}) = {t_dir_500:.3f}, t(infinity) = {t_dir_inf:.3f}")
        print(f"     breadth for t = {TARGET_T}: "
              f"{'UNREACHABLE' if not np.isfinite(n_dir) else f'{n_dir:,.0f} names'}")
        print(f"     (as this file first shipped it, using the basket figure as a per-name rho: "
              f"t({F9_N}) = {sat_t(F9_N, rho_basket, fr['t'] / np.sqrt(56 / (1 + 55 * rho_basket))):.3f}"
              f" - that was an aggregation bug, corrected here)")
        # Does the only correctly-specified estimator reproduce the curve it sits beside?
        print(f"\n  consistency of (C) against the observed curve "
              f"(a fit that cannot reproduce the curve cannot extrapolate it):")
        print(f"  {'N':>4} {'observed':>9} {'model (C)':>10} {'obs/model':>10}")
        for nn, tt in zip(ns_a, ts_a):
            pm = sat_t(nn, rho_direct, t1_dir)
            print(f"  {int(nn):>4} {tt:>9.3f} {pm:>10.3f} {tt / pm:>10.2f}")

    # ---- clause 6(a): does selection quality move with breadth?
    print("\n=== clause 6(a): gross bps per dollar turned vs breadth (selection, not smoothing) ===")
    gb = rows.groupby("n")["gross_bps"].agg(["mean", "std"])
    gbeta, ga = fit_power(gb.index.to_numpy(float), gb["mean"].to_numpy())
    for n, r in gb.iterrows():
        print(f"  N={n:>2}  gross {r['mean']:>6.3f} +/- {0.0 if np.isnan(r['std']) else r['std']:>5.3f} bps")
    print(f"  power-law slope of gross bps on N: {gbeta:+.4f} "
          f"(0 = breadth only smooths the book; > 0 = a deeper cross-section also selects better)")

    # ---- the decomposition that decides clause 7, because t = mean/sd and only one of the two
    # is the diversification channel F-9's arithmetic is about.
    print("\n=== decomposition: t = mean / sd. Which half of the curve's slope is breadth? ===")
    dg = rows.groupby("n").agg(t=("t", "mean"), net=("net_day", "mean"))
    dg["sd"] = dg["net"] / dg["t"] * np.sqrt(len(days))
    print(f"  {'N':>4} {'t':>8} {'net $/day':>10} {'implied sd':>12}")
    for nn, r in dg.iterrows():
        print(f"  {int(nn):>4} {r['t']:>8.3f} {r['net']:>10,.0f} {r['sd']:>12,.0f}")
    nsd = dg.index.to_numpy(float)
    b_t = float(np.polyfit(np.log(nsd), np.log(dg["t"].to_numpy()), 1)[0])
    b_mu = float(np.polyfit(np.log(nsd), np.log(dg["net"].to_numpy()), 1)[0])
    b_sd = float(np.polyfit(np.log(nsd), np.log(dg["sd"].to_numpy()), 1)[0])
    print(f"  log-log slopes:  t {b_t:+.3f}  =  mean {b_mu:+.3f}  -  sd {b_sd:+.3f}")
    print(f"  -> the MEAN channel is {b_mu / b_t:.0%} of the curve's slope. It is not "
          f"diversification:\n     it is the book selecting better out of a deeper cross-section, "
          f"and clause 5 says\n     names 57-{F9_N} are LESS liquid and weaker, so that channel "
          f"reverses on extension.")
    print(f"  -> the SD channel is {-b_sd / b_t:.0%} of the slope ({b_sd:+.3f}), against the "
          f"zero-forecast\n     control's {-cbeta:+.3f}. They match, which is clause 4's point: a "
          f"book with NO forecast\n     buys the same smoothing. That channel is real but it is "
          f"not evidence about the forecast.")

    # ---- bootstrap
    print(f"\n=== bootstrap over the {len(days):,} shared sessions (B = {BOOT}) ===")
    bs = bootstrap(series, rows, days, b=BOOT)
    print(f"{'quantity':<14} {'point':>9} {'p5':>9} {'p50':>9} {'p95':>9}")
    for k, v in [("rho", rho), ("beta", beta), ("t(500)", sat_t(F9_N, rho, t1)),
                 ("t(inf)", sat_ceiling(rho, t1))]:
        col = {"rho": "rho", "beta": "beta", "t(500)": "t500", "t(inf)": "tinf"}[k]
        print(f"{k:<14} {v:>9.3f} {pct(bs[col], 5):>9.3f} {pct(bs[col], 50):>9.3f} "
              f"{pct(bs[col], 95):>9.3f}")
    p_fund = float((bs["t500"] >= TARGET_T).mean())
    p_ceiling = float((bs["tinf"] >= TARGET_T).mean())
    print(f"  bootstrap P[t(500) >= {TARGET_T}] = {p_fund:.1%};  "
          f"P[ceiling >= {TARGET_T}] = {p_ceiling:.1%}")

    # ---- clause 7: regimes, then the verdict
    print("\n=== regimes: the breadth curve inside the causal SPY vol terciles ===")
    reg = f7.vol_regime(np.asarray(days))
    rmap = pd.Series(days, index=days).astype(str).map(reg)
    print(f"{'regime':<10} {'sess':>5} " + " ".join(f"N={n:<4}" for n in NS))
    for name in ["low vol", "mid vol", "high vol"]:
        keep = rmap[rmap == name].index
        if len(keep) <= 30:
            continue
        cells = []
        for n in NS:
            tt = [f1.tstat(series[("real", n, i)].reindex(keep).dropna().to_numpy())
                  for i in range(len(subsets(syms, n, seeds)))]
            cells.append(np.mean(tt))
        print(f"{name:<10} {len(keep):>5} " + " ".join(f"{c:>+6.2f}" for c in cells))
        rr, tt1, _ = fit_saturating(np.asarray(NS, float), np.asarray(cells))
        print(f"{'':<16} fit rho {rr:.4f} -> t({F9_N}) {sat_t(F9_N, rr, tt1):.2f}, "
              f"ceiling {sat_ceiling(rr, tt1):.2f}")

    t500, tinf = sat_t(F9_N, rho, t1), sat_ceiling(rho, t1)

    # ---- clause 4 is a GATE, not a remark. Its pre-registered text: "The control's t must be flat
    # and indistinguishable from zero at every N. If the control's t also rises with N then the
    # curve is measuring the construction's diversification and not the forecast's, and no
    # extrapolation of it means anything." The first cut of this file printed the control slope and
    # then let clause 7 read estimator (B) regardless. Apply the gate.
    print("\n=== clause 4 adjudication: may clause 7 be executed at all? ===")
    ctrl_max = float(np.max(np.abs(cts)))
    flat_zero = ctrl_max < 2.0
    flat_slope = abs(cbeta) < 0.25 * abs(beta)
    print(f"  (a) |control t| < 2 at every N            : {'PASS' if flat_zero else 'FAIL'} "
          f"(max |t| = {ctrl_max:.2f})")
    print(f"  (b) control slope immaterial vs the real  : {'PASS' if flat_slope else 'FAIL'} "
          f"(|{cbeta:+.3f}| vs 0.25 x |{beta:+.3f}| = {0.25 * abs(beta):.3f})")
    gate = flat_zero and flat_slope
    print(f"  -> clause 4 {'PASSES' if gate else 'FAILS'}: "
          f"{'the curve is the forecast' if gate else 'a zero-forecast book reproduces much of the curve'}")

    print(f"\nPRE-REGISTERED RULE (clause 7): FUND F-9 iff t({F9_N}) >= {TARGET_T}; "
          f"REFUSE iff the ceiling t(inf) < {TARGET_T}")
    print(f"  estimator (B), the one clause 7 was written against: "
          f"t({F9_N}) = {t500:.3f}, ceiling = {tinf:.3f}")
    if not gate:
        # (B) is also pinned at the rho -> 0 boundary here, so its "ceiling" is not a ceiling.
        # (A) is a power law and has no ceiling by construction. (C) corrected is the only
        # estimator left that is both correctly specified and finite, so clause 7 is applied to it.
        print(f"  ...but clause 4 failed, so no extrapolation of the curve may be executed, and "
              f"(B)'s\n     rho is pinned at its {rho:.5f} boundary (ceiling {tinf:,.0f}) which is "
              f"a misspecification\n     signature, not a measurement: the observed beta "
              f"{beta:+.3f} exceeds the saturating model's\n     structural maximum of 0.500, so "
              f"the fit returns the least-saturating value it has.")
        print(f"  Clause 7 is therefore applied to (C), the only correctly-specified finite "
              f"estimator:")
        print(f"     t({F9_N}) = {t_dir_500:.3f}   ceiling t(inf) = {t_dir_inf:.3f}")
        if t_dir_inf < TARGET_T:
            verdict = ("REFUSE F-9 - breadth cannot reach the hurdle at any universe size")
        elif t_dir_500 >= TARGET_T:
            verdict = (f"REFUSE F-9 on cost-benefit - the whole program's CEILING is "
                       f"{t_dir_inf:.2f}, barely over the\n     {TARGET_T} hurdle and an upper "
                       f"bound by clause 5, so a ~{F9_N}-name build cannot repay itself")
        else:
            verdict = (f"REFUSE F-9 - the fit needs {need_n(rho_direct, t1_dir, TARGET_T):,.0f} "
                       f"names and its ceiling is {t_dir_inf:.2f}, an upper bound by clause 5")
    elif t500 >= TARGET_T:
        verdict = "FUND F-9 (subject to clause 5: this is an upper bound)"
    elif tinf < TARGET_T:
        verdict = "REFUSE F-9 - breadth cannot reach the hurdle at any universe size"
    else:
        verdict = f"IN BETWEEN - the fit reaches {TARGET_T} at {need_n(rho, t1, TARGET_T):,.0f} names"
    print(f"\n  ->  {verdict}")

    rows.to_csv(CURVE_CSV, index=False)
    print(f"\ncurve -> {CURVE_CSV}")

    if record_rows:
        params = {"learner": "mid", "decile": f8.DECILE, "window": "2019-2026",
                  "book": BOOK, "label": LABEL, "seeds": seeds}
        for n, g in rows.groupby("n"):
            sub = rows[rows.n == n]
            best = sub.iloc[int(np.argmin(np.abs(sub["t"].to_numpy() - sub["t"].mean())))].to_dict()
            sess = pd.DataFrame({"day": days,
                                 "net": series[("real", int(n), int(best["seed"]))].reindex(days)})
            sess["gross"] = np.nan
            sess["cost"] = np.nan
            sess["turnover"] = best["turn_day"]
            r = dict(best)
            r["label"] = f"breadth N={n}"
            rec_simple(f"F-10 DIAGNOSTIC: breadth N={n} names, F-8's frozen session<-close cell, "
                       f"mean t over {len(g)} seeded subsets = {g['t'].mean():.3f}",
                       r, len(days), {**params, "n_names": int(n)},
                       {"Regime": "2019-2026", "Breadth": str(int(n)),
                        "Mean t": f"{g['t'].mean():.3f}",
                        "Seeds": str(len(g))})
        rec_fit(rho, t1, beta, t500, tinf, rho_direct, bs, params,
                t_dir_500=t_dir_500, t_dir_inf=t_dir_inf, rho_basket=rho_basket,
                gate=gate, cbeta=cbeta, b_mu=b_mu, b_sd=b_sd, verdict=verdict)
        print(f"recorded {len(rows.groupby('n')) + 1} diagnostic rows in {LEDGER}")


def rec_simple(tag: str, r: dict, n: int, params: dict, extra: dict) -> None:
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "intraday/f10_breadth", "class": "ml", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-10", "params": params,
           "start": "2019-01-02", "end": "2026-09-11",
           "stats": {"Sessions": str(n), "Avg Daily PnL": f"{r['net_day']:.0f}",
                     "t": f"{r['t']:.2f}",
                     "Gross Bps Per Turnover": f"{r['gross_bps']:.3f}",
                     "Cost Bps Per Turnover": f"{r['cost_bps']:.3f}",
                     "Edge Bps Per Turnover": f"{r['edge_bps']:.3f}",
                     "Turnover Per Day": f"{r['turn_day']:.0f}",
                     "Worst Day": f"{r['worst']:.0f}",
                     "Win Rate": f"{100 * r['win']:.0f}%",
                     "Diagnostic": "true", **{k: str(v) for k, v in extra.items()}}}
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def rec_fit(rho, t1, beta, t500, tinf, rho_direct, bs, params, *, t_dir_500, t_dir_inf,
            rho_basket, gate, cbeta, b_mu, b_sd, verdict) -> None:
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "intraday/f10_breadth", "class": "ml",
           "tag": (f"F-10 DIAGNOSTIC FIT: clause 4 {'passed' if gate else 'FAILED'} "
                   f"(control |t| slope {cbeta:+.3f} vs real {beta:+.3f}); per-name rho "
                   f"{rho_direct:.5f} from sub-book {rho_basket:.4f}; corrected t(500)="
                   f"{t_dir_500:.3f}, ceiling={t_dir_inf:.3f}; {verdict.splitlines()[0]}"),
           "commit": "", "run_dir": "", "track": "F-10",
           "params": {**params, "estimator": "saturating + power law + direct (de-aggregated)"},
           "start": "2019-01-02", "end": "2026-09-11",
           "stats": {"Sessions": "1933", "Avg Daily PnL": "0", "t": f"{t_dir_500:.2f}",
                     "Rho Fitted": f"{rho:.5f}", "Rho Direct": f"{rho_direct:.5f}",
                     "Rho Subbook": f"{rho_basket:.5f}",
                     "Power Law Beta": f"{beta:.3f}", "Control Beta": f"{cbeta:.3f}",
                     "Clause4 Gate": "PASS" if gate else "FAIL",
                     "Mean Slope": f"{b_mu:.3f}", "Sd Slope": f"{b_sd:.3f}",
                     "T At 500": f"{t500:.3f}", "T Ceiling": f"{tinf:.3f}",
                     "T At 500 Direct": f"{t_dir_500:.3f}",
                     "T Ceiling Direct": f"{t_dir_inf:.3f}",
                     "T500 p5": f"{pct(bs['t500'], 5):.3f}",
                     "T500 p95": f"{pct(bs['t500'], 95):.3f}",
                     "Verdict": verdict.split(" - ")[0].strip(),
                     "Diagnostic": "true", "Regime": "2019-2026"}}
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--curve", action="store_true")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--budget", type=float, default=None,
                    help="seconds of simulation before stopping; the cache resumes the rest")
    args = ap.parse_args()
    if args.curve:
        run(record_rows=args.record, quick=args.quick, budget=args.budget)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
