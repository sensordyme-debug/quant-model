"""Significance testing that survives overlapping observations.

WHY THIS EXISTS: AUD-18
------------------------
`sweep_f1.tstat` (and a duplicated copy in `sweep_f3.py`) is the textbook iid t-statistic,
`mean / (sd / sqrt(n))`, and it is used at 60 call sites across the ML track. It is correct
only when the observations are independent.

They are not, wherever a label's horizon exceeds the sampling interval. F-3 is the clearest
case: its target is `log(open[t+1+h] / open[t+1])` with **h = 5 or 21 sessions**, formed on
**every** trading day (`sweep_f3.py:179`). Consecutive labels therefore share h-1 days of the
same returns. Under that structure the sample mean's variance is understated by roughly the
factor h, so the reported t is inflated by roughly sqrt(h):

    h = 5    naive t is up to ~2.2x too large
    h = 21   naive t is up to ~4.6x too large

F-3's headline result is `IC 0.01133, IC t = 2.17` - "significant" at the 5% level under the
iid assumption, and the entire conclusion rests on it.

THE CORRECT TREATMENT
---------------------
A heteroskedasticity- and autocorrelation-consistent (HAC) standard error, Newey-West with a
Bartlett kernel:

    Var(xbar) = (1/n) [ g0 + 2 * sum_{k=1..L} (1 - k/(L+1)) * gk ]

with gk the lag-k autocovariance. The Bartlett weights guarantee a non-negative estimate,
which a raw truncated sum does not.

The lag matters more than the kernel. For labels overlapping by h-1 periods the MA structure
is exactly order h-1, so **L must be at least h-1**; anything less leaves part of the
dependence uncorrected. `lag_for_overlap` encodes that, and `tstat_hac` refuses a lag that is
too small for a horizon the caller has declared, rather than quietly returning a number that
looks like a correction and is not.

WHAT THIS MODULE DOES NOT CLAIM
--------------------------------
HAC fixes the standard error. It does not fix selection bias, multiple testing, or a label
that is wrong - those are AUD-19 and AUD-20 and they are separate. A HAC t-stat on a
specification chosen by looking at the test window is still not evidence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TStat:
    """A mean, its standard error, and how that error was estimated."""

    mean: float
    t: float
    se: float
    n: int
    lag: int
    method: str

    @property
    def significant(self) -> bool:
        """|t| > 1.96, the conventional two-sided 5% threshold on a large sample."""
        return bool(np.isfinite(self.t) and abs(self.t) > 1.96)

    def describe(self) -> str:
        return (f"mean {self.mean:+.6g}  t {self.t:+.2f}  se {self.se:.4g}  "
                f"n {self.n}  [{self.method}{f', L={self.lag}' if self.lag else ''}]")


def tstat_iid(x) -> TStat:
    """The naive t-statistic. Correct only for independent observations.

    Kept so a correction can be reported against it rather than silently replacing it - the
    point of AUD-18 is the SIZE of the inflation, which needs both numbers.
    """
    a = np.asarray(x, dtype=float)
    a = a[np.isfinite(a)]
    n = len(a)
    if n < 2:
        return TStat(float("nan"), float("nan"), float("nan"), n, 0, "iid")
    sd = a.std(ddof=1)
    if sd <= 0:
        return TStat(float(a.mean()), float("nan"), 0.0, n, 0, "iid")
    se = sd / math.sqrt(n)
    return TStat(float(a.mean()), float(a.mean() / se), float(se), n, 0, "iid")


def lag_for_overlap(horizon: int, n: int | None = None) -> int:
    """The minimum Newey-West lag for labels overlapping by `horizon - 1` periods.

    A label spanning h periods, sampled every period, is an MA(h-1) process. Truncating below
    h-1 leaves real dependence in the residual and produces a t that is still inflated - just
    less visibly, which is worse.

    Where the sample is short relative to the horizon the lag is capped at n//4: past that the
    autocovariance estimates are noise and the correction stops being a correction.
    """
    lag = max(0, int(horizon) - 1)
    if n is not None and n > 0:
        lag = min(lag, max(1, n // 4))
    return lag


def newey_west_lag(n: int) -> int:
    """Newey and West's automatic bandwidth, floor(4 (n/100)^(2/9)).

    Use this only when there is no KNOWN overlap. When a horizon is known,
    `lag_for_overlap` dominates it - the automatic rule is about unspecified serial
    correlation, not about a structure the researcher can write down.
    """
    return int(math.floor(4.0 * (max(n, 1) / 100.0) ** (2.0 / 9.0))) if n > 1 else 0


def tstat_hac(x, *, lag: int | None = None, horizon: int | None = None) -> TStat:
    """Newey-West (Bartlett) HAC t-statistic for the mean of `x`.

    Pass `horizon` when the observations are overlapping labels and the overlap is known;
    the lag is then derived and cannot be set too low by accident. Pass `lag` directly only
    for unspecified serial correlation.
    """
    a = np.asarray(x, dtype=float)
    a = a[np.isfinite(a)]
    n = len(a)
    if n < 3:
        return TStat(float("nan"), float("nan"), float("nan"), n, 0, "hac")
    if horizon is not None:
        want = lag_for_overlap(horizon, n)
        if lag is not None and lag < want:
            raise ValueError(
                f"lag={lag} is below the {want} required by horizon={horizon}; a truncated "
                f"lag leaves the overlap partly uncorrected and still reports an inflated t")
        lag = want
    if lag is None:
        lag = newey_west_lag(n)
    lag = max(0, min(int(lag), n - 1))

    d = a - a.mean()
    g0 = float(d @ d) / n
    s = g0
    for k in range(1, lag + 1):
        gk = float(d[k:] @ d[:-k]) / n
        s += 2.0 * (1.0 - k / (lag + 1.0)) * gk
    # Bartlett weights make s >= 0 in theory; clamp against floating-point drift rather than
    # returning a NaN that a caller might read as "no result" instead of "no variance".
    s = max(s, 0.0)
    if s <= 0:
        return TStat(float(a.mean()), float("nan"), 0.0, n, lag, "hac")
    se = math.sqrt(s / n)
    return TStat(float(a.mean()), float(a.mean() / se), float(se), n, lag, "hac")


def inflation(x, *, horizon: int) -> float:
    """How many times too large the naive t is on this series. 1.0 means no correction needed.

    This is the number AUD-18 is actually about. Reporting it alongside a corrected t makes
    the size of the error visible instead of leaving a reader to compare two t-values and
    guess whether the difference matters.
    """
    iid, hac = tstat_iid(x), tstat_hac(x, horizon=horizon)
    if not (np.isfinite(iid.t) and np.isfinite(hac.t)) or hac.t == 0:
        return float("nan")
    return float(abs(iid.t) / abs(hac.t))


def block_bootstrap_t(x, *, block: int, reps: int = 2000, seed: int = 0) -> tuple[float, float]:
    """(p-value for mean > 0, bootstrap SE) via a moving-block bootstrap.

    An independent check on the HAC number rather than a replacement. HAC is an asymptotic
    correction and can behave badly when the horizon is large relative to the sample; the
    block bootstrap makes no such assumption, at the cost of needing a block length. Use
    `block >= horizon` so a block carries a whole overlapping window.

    This repository already trusts a day-block bootstrap - the audit records a 2,000-rep run
    behind F-1's t of 4.74 - so the method is not new here, only shared.
    """
    a = np.asarray(x, dtype=float)
    a = a[np.isfinite(a)]
    n = len(a)
    block = max(1, min(int(block), n))
    if n < 3:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n / block))
    starts_max = n - block + 1
    means = np.empty(reps, dtype=float)
    for r in range(reps):
        starts = rng.integers(0, starts_max, size=n_blocks)
        sample = np.concatenate([a[s:s + block] for s in starts])[:n]
        means[r] = sample.mean()
    centred = means - means.mean()
    observed = a.mean()
    # One-sided: how often a centred resample is at least as extreme as what was observed.
    p = float((np.abs(centred) >= abs(observed)).mean())
    return p, float(means.std(ddof=1))


def summarize(x, *, horizon: int | None = None, label: str = "") -> str:
    """One line carrying both t-statistics and the inflation, for a report or a log."""
    iid = tstat_iid(x)
    if horizon is None:
        return f"{label + ': ' if label else ''}{iid.describe()}"
    hac = tstat_hac(x, horizon=horizon)
    infl = inflation(x, horizon=horizon)
    return (f"{label + ': ' if label else ''}"
            f"naive t {iid.t:+.2f} -> HAC t {hac.t:+.2f} (L={hac.lag}, h={horizon}), "
            f"inflation {infl:.2f}x, n={iid.n}")


# --------------------------------------------------------------------- multiplicity (AUD-19)

def bonferroni_threshold(n_trials: int, alpha: float = 0.05) -> float:
    """The |t| a result must clear when `n_trials` specifications were tried.

    AUD-19's real form. `ml_f7` evaluates 24 constructions against one test window, and the
    ledger carries 55 distinct F-track specifications - all judged against |t| > 1.96, which
    is the threshold for ONE pre-registered test. At 55 trials roughly 2.75 spurious
    "significant" results are expected from noise alone.

    Bonferroni is conservative and deliberately so: it is the cheapest defensible correction,
    it needs no assumption about dependence between the trials, and the point here is to stop
    a t of 2.17 being read as evidence, not to extract the last drop of power.
    """
    from statistics import NormalDist
    n = max(1, int(n_trials))
    a = alpha / n
    return float(NormalDist().inv_cdf(1.0 - a / 2.0))


def deflated(t: float, n_trials: int, alpha: float = 0.05) -> tuple[bool, float]:
    """(survives the correction, the threshold it had to clear)."""
    thr = bonferroni_threshold(n_trials, alpha)
    return bool(np.isfinite(t) and abs(t) > thr), thr


def verdict(x, *, horizon: int | None = None, n_trials: int = 1,
            alpha: float = 0.05, label: str = "") -> str:
    """The honest one-line verdict: overlap-corrected AND multiplicity-corrected.

    Both corrections matter and they compound. F-3's IC is the worked example: a naive t of
    2.17 becomes 1.31 once its 5-day label overlap is accounted for, and the threshold it
    would have to clear rises from 1.96 to about 3.28 once the 55 specifications this track
    has tried are accounted for. Either correction alone kills it; the pair is not close.
    """
    iid = tstat_iid(x)
    stat = tstat_hac(x, horizon=horizon) if horizon else iid
    ok, thr = deflated(stat.t, n_trials, alpha)
    return (f"{label + ': ' if label else ''}"
            f"t {stat.t:+.2f} ({stat.method}"
            f"{f', L={stat.lag}' if stat.lag else ''}) vs threshold {thr:.2f} "
            f"for {n_trials} trial(s) -> {'SURVIVES' if ok else 'does NOT survive'}"
            + (f"  [naive t was {iid.t:+.2f}]" if horizon else ""))
