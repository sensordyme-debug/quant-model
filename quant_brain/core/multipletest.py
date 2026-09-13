"""Multiplicity controls for a factory that evaluates thousands of hypotheses.

WHY THIS EXISTS
---------------
`quant_brain.core.stats` carries exactly one multiplicity control: Bonferroni, as a |t|
threshold sized by a trial count (`bonferroni_threshold`, `deflated`). That was the right
first move - it is the cheapest defensible correction and it assumes nothing at all about
how the trials relate to each other - but it answers one question, and this repository asks
four. The other three cannot be reached from a Bonferroni threshold at any alpha:

    "Which of these 200 sweep cells are real?"      A family-wise error rate at 200 tests
                                                    rejects almost nothing. The object the
                                                    researcher actually wants controlled is
                                                    the false DISCOVERY rate.
    "Is the BEST of these 60 backtests better       A question about the maximum of a
     than holding cash?"                            dependent set. No p-value adjustment
                                                    answers it; it needs the joint
                                                    distribution, which needs a bootstrap.
    "How much of this Sharpe was bought with        A threshold gives pass/fail. The
     search?"                                       deflated Sharpe gives the size of the
                                                    haircut, and PBO gives the probability
                                                    the selection itself was noise.

WHY DEPENDENCE IS THE WHOLE PROBLEM HERE
----------------------------------------
The 55 F-track specifications in this ledger are not 55 independent experiments. They are 55
views of the same tape over the same window, and a pair of strategies trading the same
instrument off overlapping signals routinely produces test statistics correlated above 0.9.
Two consequences, and they point in opposite directions:

  * Bonferroni and Holm stay EXACTLY valid - neither assumes anything about dependence - but
    both become very conservative when the tests are near-duplicates, because the effective
    number of independent trials is far below the nominal count. That conservatism is a cost,
    not an error, and the bootstrap methods below are the way to recover it: a stationary
    bootstrap resamples the whole panel jointly and therefore learns the dependence instead
    of assuming it away.
  * Benjamini-Hochberg is NOT automatically valid. It needs independence or positive
    regression dependence (PRDS). One-sided tests of positively correlated statistics satisfy
    PRDS; two-sided tests do not in general, and neither does a family containing a strategy
    and its own inverse - which the sweeps in this tree generate constantly, since a
    long/short flip is one sign change away. So `control_fdr` defaults to
    Benjamini-Yekutieli, which is valid under ARBITRARY dependence, and the BH entry point
    makes the caller say `dependence="positive"` out loud.

THE TRIAL COUNT IS STILL NOT AN ARGUMENT
----------------------------------------
`research/registry.py` refuses an `n_trials` parameter on purpose: the trial count is the
softest number in quantitative research because it is supplied by the person who wants the
result to be significant. Nothing here reintroduces it. Every FWER and FDR function takes the
VECTOR of p-values, so the trial count is the length of the vector - it cannot be understated
without literally withholding tests, and withholding one changes the vector the caller can
see. `deflated_sharpe_from_returns` works the same way: N is `len(trial_sharpes)`. The scalar
`deflated_sharpe` does take N, because Bailey and Lopez de Prado's formula needs it and there
is no honest way around that; inside the research loop it should be fed from
`Ledger.trials(family)` and never from a hand-typed integer.

REFUSE, OR RETURN A NUMBER - THE RULE THIS MODULE FOLLOWS
---------------------------------------------------------
A violated assumption about the CALL raises: mismatched series lengths, an odd split count,
an excess kurtosis passed where non-excess was required. Those are caller bugs and any number
returned would be wrong.

A violated assumption about the DATA returns an explicit unavailable result carrying the
reason, and never a plausible-looking number: too few observations to bootstrap, one trial to
deflate, a degenerate trial variance. That is not a bug, it is an honest "this history cannot
answer that question", and inventing an answer is exactly the false precision the brief
forbids.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
Sidak and Holm-Sidak. They buy power over Bonferroni/Holm only under independence, and the
gain is negligible: at alpha=0.05 and n=100 the per-test level moves from 5.00e-4 to 5.13e-4,
2.5% more power, in exchange for an assumption this tree's strategy families violate badly.
Declined.

Storey's adaptive q-value (estimating the null proportion pi0). Genuinely more powerful than
BH when most hypotheses are false, but pi0-hat is unstable at the scale of a strategy family
(tens of tests) and can land above 1 or near 0, at which point the correction is noise
pretending to be power. Revisit when a family routinely exceeds ~1,000 tests.

Romano-Wolf / Westfall-Young stepdown. This is the method most worth adding next: it is the
stepdown extension of the Reality Check and it identifies WHICH candidates beat the benchmark
rather than only whether the best one does, controlling FWER under dependence learned from
the same bootstrap `spa()` already runs. It is left out only for scope, and the panel input
and `_stationary_bootstrap_means` here are already the pieces it needs.

REFERENCES
----------
Holm (1979); Benjamini & Hochberg (1995); Benjamini & Yekutieli (2001); White (2000);
Hansen (2005); Politis & Romano (1994); Bailey & Lopez de Prado (2014); Bailey, Borwein,
Lopez de Prado & Zhu (2017); Harvey, Liu & Zhu (2016).
"""
from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
from numpy.typing import ArrayLike

#: Euler-Mascheroni constant, the gamma in the expected-maximum-Sharpe expression.
EULER_MASCHERONI = 0.5772156649015329

_NORM = NormalDist()
_SQRT2 = math.sqrt(2.0)

#: The dependence structures a correction can be asked to survive.
DEPENDENCE = ("arbitrary", "positive", "independent")


# ====================================================================== shared plumbing

def _check_alpha(alpha: float) -> float:
    a = float(alpha)
    if not (0.0 < a < 1.0):
        raise ValueError(f"alpha must lie strictly in (0, 1), got {alpha!r}")
    return a


def _check_dependence(dependence: str) -> str:
    d = str(dependence).lower()
    if d not in DEPENDENCE:
        raise ValueError(
            f"dependence must be one of {DEPENDENCE}, got {dependence!r}. There is no "
            f"default worth guessing: the answer changes which correction is valid.")
    return d


def _clean_pvalues(pvalues: ArrayLike) -> np.ndarray:
    """A finite p-value vector, or a refusal that says which assumption broke.

    A NaN p-value is a test that FAILED to run, not a test that found nothing. Dropping it
    silently would shrink the denominator of every correction below, which is the one number
    this module exists to protect, so the caller has to decide what to do with it.
    """
    p = np.asarray(pvalues, dtype=float).ravel()
    if p.size == 0:
        raise ValueError("an empty family is not a multiple-testing problem; there is "
                         "nothing to correct and returning 'no rejections' would hide that")
    if not np.all(np.isfinite(p)):
        bad = int(np.count_nonzero(~np.isfinite(p)))
        raise ValueError(
            f"{bad} of {p.size} p-values are not finite. A NaN p-value is a test that failed "
            f"to run, not a test that found nothing; dropping it here would quietly shrink "
            f"the trial count. Decide upstream whether those trials happened.")
    if np.any(p < 0.0) or np.any(p > 1.0):
        raise ValueError(f"p-values must lie in [0, 1]; got range "
                         f"[{p.min():.6g}, {p.max():.6g}] - are these t-statistics?")
    return p


def _average_ranks(x: np.ndarray) -> np.ndarray:
    """Ranks 1..n with ties averaged. No scipy: this package stays numpy-only.

    Ties are averaged rather than broken by position because a positional tie-break would
    make the PBO logit depend on the column ORDER of the candidate matrix, which is an
    artefact of how the sweep was written down.
    """
    n = int(x.size)
    order = np.argsort(x, kind="stable")
    ranks_sorted = np.arange(1, n + 1, dtype=float)
    _, start, counts = np.unique(x[order], return_index=True, return_counts=True)
    for s, c in zip(start, counts, strict=True):
        if c > 1:
            ranks_sorted[s:s + c] = ranks_sorted[s:s + c].mean()
    out = np.empty(n, dtype=float)
    out[order] = ranks_sorted
    return out


def pvalues_from_t(tstats: ArrayLike, *, two_sided: bool = True) -> np.ndarray:
    """Normal-tail p-values from t-statistics, the bridge from `stats.tstat_hac` to here.

    ASSUMPTION: the standard normal is the right reference distribution. For a HAC t it is
    the only asymptotically justified one anyway - the Student-t reference belongs to an iid
    Gaussian sample with a known degrees-of-freedom count, which a Newey-West estimator does
    not have. Below roughly 30 observations the normal tail is too thin and these p-values
    are optimistic; the correction is more data, not a different table.

    Use `two_sided=False` for the directional question that actually gets asked of a trading
    strategy ("does it make money"), and note that the one-sided form is also the form under
    which positively correlated tests satisfy the PRDS condition Benjamini-Hochberg needs.
    """
    t = np.asarray(tstats, dtype=float).ravel()
    if t.size == 0:
        raise ValueError("no t-statistics given")
    if not np.all(np.isfinite(t)):
        bad = int(np.count_nonzero(~np.isfinite(t)))
        raise ValueError(f"{bad} of {t.size} t-statistics are not finite; a non-finite t is a "
                         f"series with no usable variance, not a p-value of 1")
    if two_sided:
        p = np.array([math.erfc(abs(float(v)) / _SQRT2) for v in t], dtype=float)
    else:
        p = np.array([0.5 * math.erfc(float(v) / _SQRT2) for v in t], dtype=float)
    return np.clip(p, 0.0, 1.0)


def panel(series: Sequence[ArrayLike]) -> np.ndarray:
    """Stack K candidate P&L series into the (T, K) panel the bootstrap tests want.

    Exists because the orientation is load-bearing and a silent transpose would be a
    catastrophe: `reality_check` reads ROWS as time and COLUMNS as candidates, while the
    natural way to hold results in Python is a list of per-strategy series, which is the
    transpose. This function is the one place that flip happens, and the one place a ragged
    set of series - candidates measured over different periods, the single most common way to
    corrupt a reality check - is caught and named.
    """
    if len(series) == 0:
        raise ValueError("no candidate series given")
    cols = [np.asarray(s, dtype=float).ravel() for s in series]
    lengths = {int(c.size) for c in cols}
    if len(lengths) != 1:
        raise ValueError(
            f"the candidate series cover different numbers of periods {sorted(lengths)}. A "
            f"reality check compares the maximum across candidates period by period, so "
            f"series that do not span the SAME periods cannot be compared at all - align "
            f"them (and decide what a missing period means) before calling.")
    if cols[0].size == 0:
        raise ValueError("the candidate series are empty")
    return np.column_stack(cols)


def _clean_panel(pnl: ArrayLike, *, what: str) -> np.ndarray:
    """A finite (T, K) panel, rows = time, columns = candidates."""
    try:
        m = np.asarray(pnl, dtype=float)
    except (ValueError, TypeError) as exc:      # ragged input
        raise ValueError(
            f"{what} needs a rectangular (T, K) panel - rows are periods, columns are "
            f"candidates. The input is ragged, which means the candidates do not cover the "
            f"same periods; use `panel()` to stack aligned series.") from exc
    if m.ndim == 1:
        raise ValueError(
            f"{what} was given a single series. One candidate is not a multiple-testing "
            f"problem - use `stats.tstat_hac` or `stats.block_bootstrap_t` for that. Pass "
            f"the WHOLE set of candidates that were searched, including the ones that lost.")
    if m.ndim != 2:
        raise ValueError(f"{what} needs a 2-D (T, K) panel, got {m.ndim} dimensions")
    if m.shape[1] < 2:
        raise ValueError(f"{what} needs at least 2 candidates, got {m.shape[1]}")
    if m.shape[0] < 2:
        raise ValueError(f"{what} needs at least 2 periods, got {m.shape[0]}")
    if not np.all(np.isfinite(m)):
        bad = int(np.count_nonzero(~np.isfinite(m)))
        raise ValueError(
            f"{bad} of {m.size} panel entries are not finite. A hole in one candidate's "
            f"series breaks the time alignment of the whole panel, so it cannot be dropped "
            f"here without changing what every other candidate is being compared against.")
    return m


# ====================================================================== FWER and FDR

@dataclass(frozen=True, eq=False)
class MultipleTestResult:
    """One p-value adjustment, with the dependence assumption it rests on attached.

    `dependence` is a field rather than a docstring note because it is the part a reader six
    months later needs and the part that never gets written down: the same rejection set is
    defensible or worthless depending on whether BH's PRDS condition held for that family.
    """

    method: str
    alpha: float
    pvalues: np.ndarray
    adjusted: np.ndarray
    rejected: np.ndarray
    dependence: str
    controls: str
    note: str = ""

    @property
    def n_tests(self) -> int:
        return int(self.pvalues.size)

    @property
    def n_rejected(self) -> int:
        return int(np.count_nonzero(self.rejected))

    @property
    def survivors(self) -> np.ndarray:
        """Indices of the surviving hypotheses, in the order the caller supplied them."""
        return np.flatnonzero(self.rejected)

    def describe(self) -> str:
        return (f"{self.method}: {self.n_rejected}/{self.n_tests} survive at "
                f"alpha={self.alpha:g} [{self.controls}, valid under {self.dependence} "
                f"dependence]" + (f" - {self.note}" if self.note else ""))


def bonferroni(pvalues: ArrayLike, alpha: float = 0.05) -> MultipleTestResult:
    """Reject where n*p <= alpha. The p-value form of `stats.bonferroni_threshold`.

    ASSUMPTION: none. Bonferroni controls the family-wise error rate under any dependence
    structure whatsoever, which is why `stats.py` reached for it first and why it is the
    right answer when nothing is known about how the trials relate.

    WHEN IT IS THE WRONG TOOL: whenever `holm` is available, because Holm controls the same
    error rate under the same (absent) assumptions and rejects a superset - see the test that
    asserts exactly that. Bonferroni survives here as the baseline that superset is measured
    against, and as the t-scale threshold `Ledger.verdict` already applies; it is not a
    recommendation.
    """
    p = _clean_pvalues(pvalues)
    a = _check_alpha(alpha)
    adjusted = np.minimum(p * p.size, 1.0)
    return MultipleTestResult(
        method="bonferroni", alpha=a, pvalues=p, adjusted=adjusted, rejected=adjusted <= a,
        dependence="arbitrary", controls="FWER",
        note="single-step; dominated by holm at the same error rate")


def holm(pvalues: ArrayLike, alpha: float = 0.05) -> MultipleTestResult:
    """Holm-Bonferroni step-down. Uniformly at least as powerful as Bonferroni, free.

    Sort the p-values ascending and compare p_(i) against alpha/(n-i+1): the smallest faces
    the full Bonferroni bar alpha/n, and each rejection relaxes the bar for the next because
    one fewer hypothesis remains that could be a true null. Testing stops at the first
    failure, so the adjusted p-values are the running maximum of (n-i+1)*p_(i) - monotone by
    construction, which is what makes "adjusted <= alpha" equivalent to the step-down rule.

    ASSUMPTION: none, exactly as Bonferroni. Holm controls FWER in the strong sense under
    arbitrary dependence. Its extra power is a free lunch in the strict sense that it costs
    no assumption; there is no situation in which Bonferroni is preferable on validity
    grounds, only on the grounds that a single-step threshold is easier to state.

    WHEN IT IS THE WRONG TOOL: when the family is large and the goal is discovery rather than
    certainty. Controlling the probability of even ONE false positive across 200 sweep cells
    means rejecting almost nothing, and a research pipeline that rejects nothing learns
    nothing. That is what FDR is for. Holm is the right tool for the small, decision-carrying
    family - the handful of candidates about to be promoted - where one false positive costs
    real money.
    """
    p = _clean_pvalues(pvalues)
    a = _check_alpha(alpha)
    n = p.size
    order = np.argsort(p, kind="stable")
    steps = (n - np.arange(n)).astype(float)
    adj_sorted = np.minimum(np.maximum.accumulate(steps * p[order]), 1.0)
    adjusted = np.empty(n, dtype=float)
    adjusted[order] = adj_sorted
    return MultipleTestResult(
        method="holm-bonferroni", alpha=a, pvalues=p, adjusted=adjusted,
        rejected=adjusted <= a, dependence="arbitrary", controls="FWER",
        note="step-down; rejects a superset of bonferroni at the same alpha")


def _fdr(p: np.ndarray, a: float, *, factor: float, method: str, dependence: str,
         note: str) -> MultipleTestResult:
    """Step-up FDR with a dependence penalty of `factor` on the critical constants."""
    n = p.size
    order = np.argsort(p, kind="stable")
    ranks = np.arange(1, n + 1, dtype=float)
    scaled = factor * n / ranks * p[order]
    # Step-up: walk from the largest p-value down, taking a running minimum. That enforces
    # monotonicity of the adjusted values, which is what makes everything below the largest
    # rejected index get rejected too - the defining behaviour of a step-up rule.
    adj_sorted = np.minimum(np.minimum.accumulate(scaled[::-1])[::-1], 1.0)
    adjusted = np.empty(n, dtype=float)
    adjusted[order] = adj_sorted
    return MultipleTestResult(method=method, alpha=a, pvalues=p, adjusted=adjusted,
                              rejected=adjusted <= a, dependence=dependence,
                              controls="FDR", note=note)


def harmonic(n: int) -> float:
    """c(n) = sum 1/i, the Benjamini-Yekutieli price of assuming nothing about dependence.

    Roughly ln(n) + 0.577: 2.9 at n=10, 5.2 at n=100, 7.5 at n=1000. That is the factor by
    which BY's critical constants shrink relative to BH, and it is the honest cost of not
    knowing the correlation structure.
    """
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    return float(np.sum(1.0 / np.arange(1, int(n) + 1, dtype=float)))


def benjamini_hochberg(pvalues: ArrayLike, alpha: float = 0.05) -> MultipleTestResult:
    """BH step-up FDR: reject the largest k with p_(k) <= (k/n)*alpha, and everything below.

    Controls the expected proportion of false positives AMONG THE REJECTIONS, which is the
    quantity a research pipeline actually cares about: "of the twelve cells I am about to
    take to validation, how many are noise?" is a useful question, where "is any one of my
    two hundred cells noise?" is not.

    ASSUMPTION - AND IT IS A REAL ONE HERE: the p-values are independent, or positively
    regression dependent on the subset of true nulls (PRDS). One-sided tests of positively
    correlated Gaussian statistics satisfy PRDS, so a family of long-only strategies on the
    same market tested one-sided is usually fine. TWO-SIDED tests of correlated statistics
    are not covered, and a family containing a strategy and its own inverse is actively
    negatively dependent - and this tree's sweeps produce those routinely, because flipping a
    signal's sign is a one-character edit. Under negative dependence BH's guarantee is void,
    not merely approximate.

    If the answer to "are these positively dependent?" is "I have not checked", the correct
    call is `benjamini_yekutieli`, and `control_fdr` defaults there for that reason.

    WHEN IT IS THE WRONG TOOL: when a single false positive is expensive. FDR at 5% over
    twenty rejections expects one of them to be wrong; if that one is going to be sized into
    a live book, control FWER with `holm` instead.
    """
    p = _clean_pvalues(pvalues)
    a = _check_alpha(alpha)
    return _fdr(p, a, factor=1.0, method="benjamini-hochberg", dependence="positive",
                note="requires independence or PRDS; void under negative dependence")


def benjamini_yekutieli(pvalues: ArrayLike, alpha: float = 0.05) -> MultipleTestResult:
    """BY: BH with the critical constants divided by c(n) = sum 1/i. Valid under ANY
    dependence.

    Benjamini and Yekutieli (2001) proved that dividing BH's constants by the n-th harmonic
    number controls FDR for an arbitrary joint distribution of the test statistics, which is
    the guarantee a portfolio of correlated strategies needs. ASSUMPTION: none.

    THE PRICE, STATED PLAINLY: c(n) grows like ln(n), so at 100 tests BY needs a p-value 5.2
    times smaller than BH to make the same rejection, and at 1,000 tests 7.5 times smaller.
    That is often the difference between a discovery and none. The penalty is a worst-case
    bound over all dependence structures, so on a family that really is positively dependent
    BY is leaving power on the table - the way to get it back is to bootstrap the actual
    dependence (`spa`), not to assume it away by reaching for BH.

    WHEN IT IS THE WRONG TOOL: on a family known to be positively dependent AND large enough
    that the ln(n) penalty kills every candidate. At that point BY is not conservative, it is
    uninformative, and `spa` over the candidate P&L panel is the method that still has power.
    """
    p = _clean_pvalues(pvalues)
    a = _check_alpha(alpha)
    c = harmonic(p.size)
    return _fdr(p, a, factor=c, method="benjamini-yekutieli", dependence="arbitrary",
                note=f"harmonic penalty c(n)={c:.3f} buys validity under any dependence")


def control_fwer(pvalues: ArrayLike, alpha: float = 0.05, *,
                 dependence: str = "arbitrary") -> MultipleTestResult:
    """Control the family-wise error rate, by the method appropriate to the dependence.

    All three settings route to Holm, and that is the finding rather than a stub: Holm needs
    no dependence assumption, so knowing the structure buys nothing at this error rate unless
    one is willing to assume independence outright and take Sidak's ~2.5% - which this module
    declines (see the module docstring). The argument exists so the call site records what
    the caller believed, and so it reads the same as `control_fdr`, where the answer really
    does change.
    """
    d = _check_dependence(dependence)
    out = holm(pvalues, alpha)
    return MultipleTestResult(
        method=out.method, alpha=out.alpha, pvalues=out.pvalues, adjusted=out.adjusted,
        rejected=out.rejected, dependence="arbitrary", controls="FWER",
        note=f"{out.note}; caller declared {d} dependence, which does not change the method")


def control_fdr(pvalues: ArrayLike, alpha: float = 0.05, *,
                dependence: str = "arbitrary") -> MultipleTestResult:
    """Control the false discovery rate, by the method appropriate to the dependence.

    `arbitrary` (the default) gives Benjamini-Yekutieli; `positive` and `independent` give
    Benjamini-Hochberg. The default is the conservative one on purpose: strategies sharing a
    market are dependent in ways nobody has verified, and the failure mode of guessing wrong
    is a published FDR guarantee that does not hold.
    """
    d = _check_dependence(dependence)
    if d == "arbitrary":
        return benjamini_yekutieli(pvalues, alpha)
    return benjamini_hochberg(pvalues, alpha)


# ====================================================== White's Reality Check / Hansen's SPA

@dataclass(frozen=True, eq=False)
class BootstrapTestResult:
    """A bootstrap test of "the best of these candidates beats the benchmark".

    `pvalue` is None when the data could not support the test; `reason` then says why, and
    there is deliberately no number to misread.
    """

    method: str
    statistic: float | None
    pvalue: float | None
    pvalue_lower: float | None
    pvalue_upper: float | None
    n_obs: int
    n_candidates: int
    block: int
    reps: int
    best: int
    best_mean: float
    reason: str

    @property
    def available(self) -> bool:
        return self.pvalue is not None

    def describe(self) -> str:
        if self.pvalue is None:
            return f"{self.method} UNAVAILABLE - {self.reason}"
        bounds = ""
        if self.pvalue_lower is not None and self.pvalue_upper is not None:
            bounds = f" (lower {self.pvalue_lower:.4f}, upper {self.pvalue_upper:.4f})"
        return (f"{self.method}: p={self.pvalue:.4f}{bounds} for the best of "
                f"{self.n_candidates} candidates (#{self.best}, mean {self.best_mean:+.6g}) "
                f"over {self.n_obs} periods, {self.reps} stationary-bootstrap reps at mean "
                f"block {self.block}")


def _unavailable(method: str, reason: str, *, n_obs: int, k: int, block: int,
                 reps: int) -> BootstrapTestResult:
    return BootstrapTestResult(method=method, statistic=None, pvalue=None, pvalue_lower=None,
                               pvalue_upper=None, n_obs=n_obs, n_candidates=k, block=block,
                               reps=reps, best=-1, best_mean=float("nan"), reason=reason)


def _stationary_bootstrap_means(f: np.ndarray, *, block: int, reps: int,
                                seed: int) -> np.ndarray:
    """(reps, K) matrix of resampled column means, Politis-Romano stationary bootstrap.

    Blocks of geometric length with mean `block`, wrapped circularly, so the resample is
    stationary - a moving-block bootstrap is not, and the non-stationarity shows up in the
    tails of a maximum statistic, which is the only thing this is used for.

    The SAME resampled index path is applied to every candidate, which is what preserves the
    cross-sectional dependence the reality check exists to account for. Resampling each
    candidate independently would destroy exactly the structure being tested and produce a
    wildly optimistic p-value.
    """
    n = f.shape[0]
    rng = np.random.default_rng(seed)
    pos = np.arange(n)
    p_new = 1.0 / float(block)
    out = np.empty((reps, f.shape[1]), dtype=float)
    for b in range(reps):
        new = rng.random(n) < p_new
        new[0] = True
        starts = rng.integers(0, n, size=n)
        last = np.maximum.accumulate(np.where(new, pos, 0))
        idx = (starts[last] + (pos - last)) % n
        out[b] = f[idx].mean(axis=0)
    return out


def _prepare_panel(pnl: ArrayLike, benchmark: ArrayLike | None, *, what: str,
                   block: int, reps: int) -> tuple[np.ndarray, int, int]:
    m = _clean_panel(pnl, what=what)
    if benchmark is not None:
        b = np.asarray(benchmark, dtype=float).ravel()
        if b.size != m.shape[0]:
            raise ValueError(
                f"the benchmark covers {b.size} periods and the candidates cover "
                f"{m.shape[0]}. A reality check tests the DIFFERENCE period by period, so "
                f"the two must be the same series of periods.")
        if not np.all(np.isfinite(b)):
            raise ValueError("the benchmark series contains non-finite values")
        m = m - b[:, None]
    n, k = int(m.shape[0]), int(m.shape[1])
    if block < 1 or block > n:
        raise ValueError(
            f"the mean block length must lie in [1, {n}], got {block}. It is required rather "
            f"than defaulted because block length IS the serial-dependence assumption: 1 is "
            f"an iid bootstrap and asserts there is none. Use at least the label horizon, "
            f"and roughly n**(1/3) when the dependence is unspecified.")
    if reps < 100:
        raise ValueError(f"reps={reps} cannot resolve a p-value finer than {1.0 / reps:.3g}; "
                         f"use at least 100, and 1000 for anything reported")
    sd = m.std(axis=0, ddof=1)
    dead = np.flatnonzero(~(sd > 0))
    if dead.size:
        raise ValueError(
            f"candidates {dead.tolist()[:8]} have zero variance over the sample. A constant "
            f"P&L series has no sampling distribution to bootstrap and no studentised "
            f"statistic; a candidate that never traded is a data problem, not a candidate.")
    return m, n, k


def reality_check(pnl: ArrayLike, *, block: int, benchmark: ArrayLike | None = None,
                  reps: int = 1000, seed: int = 0,
                  min_obs: int = 30) -> BootstrapTestResult:
    """White's Reality Check: is the BEST of K candidates better than the benchmark?

    The null is that no candidate has positive expected performance relative to the
    benchmark, so the statistic is V = sqrt(T) * max_k mean_k and its distribution comes from
    resampling the whole panel jointly with a stationary bootstrap, recentring every
    candidate on its own sample mean. Because the bootstrap keeps the cross-sectional
    correlation, the critical value is far below the Bonferroni one when the candidates are
    near-duplicates - which is precisely the power a family of correlated strategies loses
    under a p-value adjustment.

    ASSUMPTIONS:
      * `pnl` is (T, K) with rows = periods and columns = candidates, aligned on the same
        periods. Use `panel()` to build it; the orientation is not guessed.
      * The series are stationary and weakly dependent. A strategy whose leverage or universe
        changed mid-sample violates this and the bootstrap will not notice.
      * `block` is at least the length of the dependence in the P&L. For overlapping labels
        that is the horizon; `stats.lag_for_overlap` is the same reasoning on the HAC side.
      * THE SET IS THE WHOLE SEARCH. This is the assumption that gets violated in practice
        and it cannot be checked from inside: running the reality check over the five
        survivors of a 500-cell sweep answers a question about five candidates and says
        nothing about the sweep. The number to compare `n_candidates` against is
        `Ledger.trials(family)`.

    WHEN IT IS THE WRONG TOOL: when many of the candidates are known to be bad. White's
    recentring leaves every candidate contributing to the bootstrap maximum, so padding the
    set with hopeless variants inflates the p-value without adding information - the test is
    not merely conservative, it is manipulable in the safe direction. `spa` fixes precisely
    that and should be the default here; the Reality Check is kept because it is the
    reference SPA is defined against, and because the gap between the two is a diagnostic.
    """
    m, n, k = _prepare_panel(pnl, benchmark, what="reality_check", block=block, reps=reps)
    if n < min_obs:
        return _unavailable(
            "white-reality-check",
            f"{n} periods is below the {min_obs} this test needs; a stationary bootstrap over "
            f"a sample this short resamples the same few blocks, and its tail is an artefact "
            f"of the sample rather than an estimate of the null distribution",
            n_obs=n, k=k, block=block, reps=reps)

    means = m.mean(axis=0)
    root = math.sqrt(n)
    best = int(np.argmax(means))
    v = float(root * means[best])
    bmeans = _stationary_bootstrap_means(m, block=block, reps=reps, seed=seed)
    vstar = (root * (bmeans - means)).max(axis=1)
    p = float(np.mean(vstar >= v))
    return BootstrapTestResult(
        method="white-reality-check", statistic=v, pvalue=p, pvalue_lower=None,
        pvalue_upper=None, n_obs=n, n_candidates=k, block=block, reps=reps, best=best,
        best_mean=float(means[best]),
        reason=f"max of {k} candidates against a stationary bootstrap of the joint null")


def spa(pnl: ArrayLike, *, block: int, benchmark: ArrayLike | None = None,
        reps: int = 1000, seed: int = 0, min_obs: int = 30) -> BootstrapTestResult:
    """Hansen's Superior Predictive Ability test. The Reality Check, de-manipulated.

    Two changes to White (2000), both of which matter here:

      1. STUDENTISATION. The statistic is max_k sqrt(T)*mean_k / omega_k rather than
         max_k sqrt(T)*mean_k, so a high-variance candidate cannot dominate the maximum on
         volatility alone. omega_k comes from the same bootstrap, which is the estimate
         consistent with the resampling scheme rather than an unrelated kernel estimator.
      2. RECENTRING WITH A THRESHOLD. Candidates whose sample performance is far enough below
         zero are recentred at 0 instead of at their own mean, so they drop out of the
         bootstrap maximum. This is what stops a search being made to look innocent by
         padding it with hopeless variants - under White's recentring, adding fifty terrible
         strategies RAISES the p-value of the good one.

    Three p-values are returned, as in Hansen (2005). `pvalue_lower` recentres at max(0,
    mean) and is liberal; `pvalue` uses the consistent threshold -sqrt(2 log log T) * omega_k;
    `pvalue_upper` recentres every candidate at its own mean and is therefore the studentised
    Reality Check. They bracket the truth, and a wide bracket is itself the finding: it means
    the answer depends entirely on how the marginal candidates are treated.

    ASSUMPTIONS: all of `reality_check`'s, plus enough observations for log log T to mean
    anything - the consistency threshold is asymptotic and at a few hundred periods it is a
    rule of thumb, not a guarantee.

    WHEN IT IS THE WRONG TOOL: when the candidate P&L series are not available, only their
    summary statistics. SPA needs the panel; with p-values alone the honest fallback is
    `control_fwer` / `control_fdr`, which need less and promise less.
    """
    m, n, k = _prepare_panel(pnl, benchmark, what="spa", block=block, reps=reps)
    if n < min_obs:
        return _unavailable(
            "hansen-spa",
            f"{n} periods is below the {min_obs} this test needs; the consistency threshold "
            f"is a sqrt(2 log log T) asymptotic and there is nothing asymptotic about "
            f"{n} observations",
            n_obs=n, k=k, block=block, reps=reps)

    means = m.mean(axis=0)
    root = math.sqrt(n)
    bmeans = _stationary_bootstrap_means(m, block=block, reps=reps, seed=seed)
    omega = (root * (bmeans - means)).std(axis=0, ddof=1)
    if not np.all(omega > 0):
        return _unavailable(
            "hansen-spa",
            "the bootstrap standard deviation of at least one candidate is zero, so the "
            "studentised statistic is undefined; the resample never varied, which means the "
            "block length is as long as the sample",
            n_obs=n, k=k, block=block, reps=reps)

    tk = root * means / omega
    best = int(np.argmax(tk))
    stat = float(max(0.0, tk[best]))
    threshold = -math.sqrt(2.0 * math.log(math.log(n)))

    def _p(g: np.ndarray) -> float:
        z = root * (bmeans - g) / omega
        return float(np.mean(np.maximum(0.0, z.max(axis=1)) >= stat))

    p_consistent = _p(np.where(tk >= threshold, means, 0.0))
    p_lower = _p(np.maximum(means, 0.0))
    p_upper = _p(means)
    return BootstrapTestResult(
        method="hansen-spa", statistic=stat, pvalue=p_consistent, pvalue_lower=p_lower,
        pvalue_upper=p_upper, n_obs=n, n_candidates=k, block=block, reps=reps, best=best,
        best_mean=float(means[best]),
        reason=(f"studentised max over {k} candidates, consistent recentring at "
                f"{threshold:.3f} standard errors"))


# ====================================================================== Deflated Sharpe

@dataclass(frozen=True, eq=False)
class DeflatedSharpe:
    """The probability the true Sharpe exceeds what the SEARCH alone would have produced.

    `value` is None when the inputs cannot support the statistic. There is no fallback
    number: a DSR computed with a guessed trial variance is a decimal with no content.
    """

    value: float | None
    sharpe: float
    expected_max_sharpe: float | None
    n_trials: int
    n_obs: int
    skew: float
    kurtosis: float
    reason: str

    @property
    def available(self) -> bool:
        return self.value is not None

    @property
    def survives(self) -> bool:
        """DSR above 0.95 - the conventional bar, and only meaningful when available."""
        return self.value is not None and self.value > 0.95

    def describe(self) -> str:
        if self.value is None or self.expected_max_sharpe is None:
            return f"DSR UNAVAILABLE - {self.reason}"
        return (f"DSR {self.value:.4f}: SR {self.sharpe:+.4f} against an expected maximum of "
                f"{self.expected_max_sharpe:+.4f} from {self.n_trials} trials "
                f"(n={self.n_obs}, skew {self.skew:+.2f}, kurtosis {self.kurtosis:.2f})")


def _dsr_unavailable(reason: str, *, sharpe: float, n_trials: int, n_obs: int,
                     skew: float, kurtosis: float) -> DeflatedSharpe:
    return DeflatedSharpe(value=None, sharpe=sharpe, expected_max_sharpe=None,
                          n_trials=n_trials, n_obs=n_obs, skew=skew, kurtosis=kurtosis,
                          reason=reason)


def expected_max_sharpe(n_trials: int, var_trials: float) -> float:
    """SR0: the Sharpe the best of N zero-skill trials would show anyway.

    Bailey and Lopez de Prado's expected maximum of N draws from a normal with variance V:

        SR0 = sqrt(V) * [ (1-gamma) * Z^-1(1 - 1/N) + gamma * Z^-1(1 - 1/(N e)) ]

    with gamma the Euler-Mascheroni constant. It grows like sqrt(2 V log N), so the bar rises
    without limit as the search widens - slowly, which is the uncomfortable part: going from
    10 trials to 1,000 only doubles it. A search cannot be excused by "we only tried a few"
    and cannot be condemned by "they tried thousands" alone; the variance of the trial
    Sharpes does the heavier lifting.

    ASSUMPTION: the N trial Sharpes are draws from a common normal. Independence is not
    needed for this approximation to the expected maximum, and the dependence enters through
    V instead: a family of near-duplicate strategies has a small V, so a correlated search
    gets a lighter haircut - correctly, because it really did explore less.
    """
    n = int(n_trials)
    v = float(var_trials)
    if n < 2:
        raise ValueError(f"the expected maximum of {n} trial(s) is not defined; "
                         f"Z^-1(1 - 1/1) is infinite")
    if not (math.isfinite(v) and v > 0.0):
        raise ValueError(f"the variance of the trial Sharpes must be finite and positive, "
                         f"got {var_trials!r}")
    z1 = _NORM.inv_cdf(1.0 - 1.0 / n)
    z2 = _NORM.inv_cdf(1.0 - 1.0 / (n * math.e))
    return math.sqrt(v) * ((1.0 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2)


def deflated_sharpe(*, sharpe: float, n_obs: int, n_trials: int, var_trials: float,
                    skew: float, kurtosis: float, min_obs: int = 30,
                    max_plausible_sharpe: float = 2.0) -> DeflatedSharpe:
    """Bailey & Lopez de Prado's Deflated Sharpe Ratio.

        DSR = Z[ (SR - SR0) * sqrt(n-1) / sqrt(1 - g3*SR + (g4-1)/4 * SR^2) ]

    The probabilistic Sharpe ratio evaluated against SR0 instead of zero: the probability
    that the true Sharpe exceeds what the best of `n_trials` searches would have shown with
    no skill at all. It is the only statistic in this module that reports how much of a
    number was bought with search rather than merely whether to keep it.

    `skew` and `kurtosis` have NO DEFAULTS on purpose. Defaulting them to 0 and 3 assumes
    Gaussian returns, and the two moments are not decoration: they set the width of the
    Sharpe's own sampling distribution. Negative skew and fat tails both inflate the
    denominator, which pulls the DSR toward 0.5 - so for a candidate that would otherwise
    PASS they lower it, which is the case a reviewer is looking at, and a Gaussian default
    would flatter exactly those results. (For a candidate already below its expected maximum
    the same inflation raises the DSR toward 0.5: this is a probability, not a score, and
    widening the uncertainty moves it toward a coin flip from either side. The test suite
    pins both directions.) `kurtosis` is NON-EXCESS (3 for a Gaussian); passing excess
    kurtosis is the standard implementation error and is refused rather than absorbed.

    ASSUMPTIONS:
      * `sharpe` is PER OBSERVATION and on the same clock as `n_obs`. An annualised Sharpe
        with a daily observation count overstates the statistic by roughly sqrt(252).
      * The trial Sharpes are measured on the same sample and frequency, and the selected
        strategy is one of them. Computing V from the survivors only understates it, which
        lowers SR0, which raises the DSR - the error runs in the flattering direction.
      * The returns are IID enough for the moment corrections to be the whole story. They are
        not, when the labels overlap; correct the Sharpe's standard error first
        (`stats.tstat_hac`) and read the DSR as the selection haircut on top of that.

    WHEN IT IS THE WRONG TOOL: with one trial (nothing to deflate - that case is the
    probabilistic Sharpe ratio, which `stats.tstat_hac` already reports in t form), or when
    the trial Sharpes were never recorded. A DSR with an invented V is not a conservative
    estimate, it is a decimal with no content, and this function returns UNAVAILABLE rather
    than produce one.
    """
    sr, n = float(sharpe), int(n_obs)
    g3, g4, nt = float(skew), float(kurtosis), int(n_trials)
    if min_obs < 4:
        raise ValueError(f"min_obs={min_obs} is below the 4 observations a fourth moment "
                         f"needs to exist at all")
    for name, val in (("sharpe", sr), ("skew", g3), ("kurtosis", g4),
                      ("var_trials", float(var_trials))):
        if not math.isfinite(val):
            raise ValueError(f"{name} must be finite, got {val!r}")
    if g4 < 1.0:
        raise ValueError(
            f"kurtosis={g4} is below 1, which no distribution has. This argument is "
            f"NON-EXCESS kurtosis (3 for a Gaussian) - you have almost certainly passed "
            f"excess kurtosis, which would shrink the denominator and inflate the DSR. "
            f"Add 3.")
    if abs(sr) > max_plausible_sharpe:
        raise ValueError(
            f"sharpe={sr} is per-observation, and {max_plausible_sharpe} per observation is "
            f"~{max_plausible_sharpe * math.sqrt(252):.0f} annualised on daily data - this is "
            f"almost certainly an annualised figure passed with a per-period n_obs. Divide by "
            f"sqrt(periods per year). (A coarse frequency check, not a proof: a modestly "
            f"wrong frequency cannot be detected from the number alone.)")

    if nt < 2:
        return _dsr_unavailable(
            f"{nt} trial(s): there is nothing to deflate. The expected maximum of a single "
            f"draw is undefined and the statistic degenerates to the probabilistic Sharpe "
            f"ratio, which stats.tstat_hac already reports in t form.",
            sharpe=sr, n_trials=nt, n_obs=n, skew=g3, kurtosis=g4)
    if not (float(var_trials) > 0.0):
        return _dsr_unavailable(
            f"the trial Sharpes have variance {float(var_trials):.6g}. With no spread across "
            f"trials the expected maximum collapses to zero and the DSR would silently equal "
            f"an UNDEFLATED probabilistic Sharpe ratio - a number that looks like a "
            f"correction and is not one.",
            sharpe=sr, n_trials=nt, n_obs=n, skew=g3, kurtosis=g4)
    if n < min_obs:
        return _dsr_unavailable(
            f"{n} observations is below the {min_obs} this statistic needs: it is driven by "
            f"the sample skew and kurtosis, and a fourth moment from {n} points is noise "
            f"rather than an estimate.",
            sharpe=sr, n_trials=nt, n_obs=n, skew=g3, kurtosis=g4)

    sr0 = expected_max_sharpe(nt, float(var_trials))
    den = 1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr * sr
    if den <= 0.0:
        return _dsr_unavailable(
            f"the variance term 1 - g3*SR + (g4-1)/4*SR^2 came out {den:.6g}, which is not a "
            f"variance. The moment estimates and the Sharpe are mutually inconsistent - "
            f"usually a tiny sample, or a frequency mismatch between them.",
            sharpe=sr, n_trials=nt, n_obs=n, skew=g3, kurtosis=g4)

    z = (sr - sr0) * math.sqrt(n - 1) / math.sqrt(den)
    return DeflatedSharpe(value=float(_NORM.cdf(z)), sharpe=sr,
                          expected_max_sharpe=float(sr0), n_trials=nt, n_obs=n, skew=g3,
                          kurtosis=g4, reason=f"deflated against the best of {nt} trials")


def sharpe_moments(returns: ArrayLike) -> tuple[float, int, float, float]:
    """(per-observation Sharpe, n, skew, NON-EXCESS kurtosis) - the four DSR inputs.

    The Sharpe uses the sample standard deviation (ddof=1) to match `stats.tstat_iid`; the
    standardised third and fourth moments use the population standard deviation, which is the
    g1/b2 convention every other library reports. The difference is O(1/n), and stating which
    is used matters more than which is chosen.
    """
    r = np.asarray(returns, dtype=float).ravel()
    r = r[np.isfinite(r)]
    n = int(r.size)
    if n < 4:
        raise ValueError(f"{n} finite observations cannot support a fourth moment")
    sd = float(r.std(ddof=1))
    mu = float(r.mean())
    # Relative, not `sd <= 0`: fifty copies of 0.1 have a standard deviation of 2.8e-17
    # rather than exactly zero, and an absolute test lets that through as a Sharpe ratio of
    # 3.6e15. Measured, not anticipated - the test for this guard is what found it.
    scale = float(np.max(np.abs(r)))
    if not (sd > 0.0) or sd <= 1e-12 * scale:
        raise ValueError(
            f"a return series with no variance has no Sharpe ratio: sd={sd:.6g} against a "
            f"scale of {scale:.6g}, which is floating-point dust rather than dispersion")
    d = (r - mu) / r.std(ddof=0)
    return float(mu / sd), n, float((d ** 3).mean()), float((d ** 4).mean())


def deflated_sharpe_from_returns(returns: ArrayLike, *, trial_sharpes: ArrayLike,
                                 min_obs: int = 30,
                                 max_plausible_sharpe: float = 2.0) -> DeflatedSharpe:
    """DSR from the return series and the Sharpes of EVERY trial that was run.

    The vector form, and the one to prefer: N is `len(trial_sharpes)` and V is their sample
    variance, so the trial count is structural rather than an argument - the same property
    `Ledger.verdict` is built around. Understating the search means deleting entries from a
    list the caller can see, not typing a smaller integer.

    `trial_sharpes` must be per-observation Sharpes on the same clock as `returns`, and must
    include the strategy being tested.
    """
    sr, n, g3, g4 = sharpe_moments(returns)
    s = np.asarray(trial_sharpes, dtype=float).ravel()
    if s.size == 0:
        raise ValueError("no trial Sharpes given; the DSR is defined against the search that "
                         "produced the candidate, and an empty search did not produce it")
    if not np.all(np.isfinite(s)):
        raise ValueError("the trial Sharpes contain non-finite values; a trial whose Sharpe "
                         "could not be computed still happened and still counts")
    if s.size < 2:
        return _dsr_unavailable(
            "1 trial Sharpe was supplied, so there is no trial variance to estimate and "
            "nothing to deflate against.",
            sharpe=sr, n_trials=int(s.size), n_obs=n, skew=g3, kurtosis=g4)
    return deflated_sharpe(sharpe=sr, n_obs=n, n_trials=int(s.size),
                           var_trials=float(s.var(ddof=1)), skew=g3, kurtosis=g4,
                           min_obs=min_obs, max_plausible_sharpe=max_plausible_sharpe)


# ============================================== Probability of Backtest Overfitting (CSCV)

@dataclass(frozen=True, eq=False)
class PBOResult:
    """Combinatorially symmetric cross-validation over a set of configurations."""

    value: float
    n_splits: int
    n_combinations: int
    n_configs: int
    logits: np.ndarray
    selected: np.ndarray
    is_scores: np.ndarray
    oos_scores: np.ndarray
    prob_oos_loss: float
    degradation_slope: float | None
    reason: str = ""

    def describe(self) -> str:
        slope = ("n/a" if self.degradation_slope is None
                 else f"{self.degradation_slope:+.3f}")
        return (f"PBO {self.value:.3f} over {self.n_combinations} splits of "
                f"{self.n_configs} configurations ({self.n_splits} blocks); "
                f"P(OOS loss) {self.prob_oos_loss:.3f}, IS->OOS slope {slope}")


def _sharpe_scores(block: np.ndarray) -> np.ndarray:
    """Per-configuration Sharpe over one block of rows. The CSCV paper's default metric."""
    mu = block.mean(axis=0)
    sd = block.std(axis=0, ddof=1)
    out = np.zeros_like(mu)
    ok = sd > 0
    out[ok] = mu[ok] / sd[ok]
    return out


def pbo(pnl: ArrayLike, *, n_splits: int = 8,
        metric: Callable[[np.ndarray], np.ndarray] | None = None,
        min_block: int = 2, max_combinations: int = 20_000) -> PBOResult:
    """Probability of Backtest Overfitting by combinatorially symmetric cross-validation.

    Bailey, Borwein, Lopez de Prado & Zhu (2017). Cut the sample into S contiguous blocks;
    for each of the C(S, S/2) ways of splitting those blocks into an in-sample half and an
    out-of-sample half, pick the configuration that looks best in sample and record where it
    ranks out of sample. PBO is the fraction of splits in which the in-sample winner lands
    below the out-of-sample median.

    WHAT MAKES IT DIFFERENT FROM EVERYTHING ELSE IN THIS MODULE: it does not ask whether a
    strategy is real. It asks whether the SELECTION PROCEDURE has any skill - whether "pick
    the best backtest" generalises at all on this configuration set. 0.5 is the value for
    pure noise, because ranking noise is a coin flip. That makes it the right diagnostic for
    a parameter sweep, where the question is never "is cell 47 real" but "does picking the
    best cell mean anything".

    ASSUMPTIONS:
      * `pnl` is (T, N): rows are periods, columns are the configurations that were TRIED.
        Feeding it only the finalists makes the answer meaningless in the flattering
        direction - a set of near-identical survivors all rank fine out of sample, and PBO
        collapses towards 0.
      * The blocks are exchangeable enough that an out-of-sample half made of scattered
        blocks is a fair test. Under a strong regime shift this is optimistic: CSCV trains on
        blocks that come after the test blocks, which walk-forward forbids. It measures
        selection fragility, not deployability - `core/validation.py` handles the second.
      * The metric is comparable across blocks of slightly different lengths. Sharpe is;
        total P&L is not, which is why the default is Sharpe.
      * N is large enough for a rank to mean something. With 4 configurations the relative
        rank takes 4 values and PBO is a very coarse estimate.

    REFUSALS: S must be even (the halves must be the same size, which is the "symmetric" in
    combinatorially symmetric cross-validation), at least 4 (S=2 gives two splits, and a
    probability estimated from two observations is not one), and must leave at least
    `min_block` periods in every block.

    WHEN IT IS THE WRONG TOOL: on a single strategy. PBO over one configuration is
    identically 0 and means nothing - there is no selection to overfit. Use the DSR for "how
    much of this Sharpe is selection" on one survivor, and PBO for "is this sweep's selection
    step doing anything at all".
    """
    m = _clean_panel(pnl, what="pbo")
    t, k = int(m.shape[0]), int(m.shape[1])
    if n_splits % 2 != 0:
        raise ValueError(f"n_splits must be even, got {n_splits}: the in-sample and "
                         f"out-of-sample halves must be the same size, which is the "
                         f"'symmetric' in combinatorially symmetric cross-validation")
    if n_splits < 4:
        raise ValueError(f"n_splits={n_splits} gives at most 2 splits; a probability "
                         f"estimated from two observations is not a probability. Use 8 "
                         f"(70 splits) or 16 (12,870, the paper's usual choice).")
    if min_block < 2:
        raise ValueError(f"min_block={min_block} is below the 2 rows a Sharpe ratio needs")
    if t // n_splits < min_block:
        raise ValueError(
            f"{t} periods cut into {n_splits} blocks leaves {t // n_splits} periods per "
            f"block, below min_block={min_block}. Either the history is too short for this "
            f"many blocks or the blocks are too short to score - both mean the answer would "
            f"be an artefact of the cut.")
    n_comb = math.comb(n_splits, n_splits // 2)
    if n_comb > max_combinations:
        raise ValueError(
            f"n_splits={n_splits} enumerates {n_comb} combinations, above "
            f"max_combinations={max_combinations}. Lower n_splits (16 gives 12,870) rather "
            f"than sampling them - a sampled CSCV is a different estimator and should not be "
            f"reported under the same name.")

    score = _sharpe_scores if metric is None else metric
    blocks = np.array_split(np.arange(t), n_splits)
    half = n_splits // 2

    logits = np.empty(n_comb, dtype=float)
    selected = np.empty(n_comb, dtype=int)
    is_sel = np.empty(n_comb, dtype=float)
    oos_sel = np.empty(n_comb, dtype=float)

    for j, combo in enumerate(itertools.combinations(range(n_splits), half)):
        chosen = set(combo)
        rows_is = np.concatenate([blocks[i] for i in combo])
        rows_oos = np.concatenate([blocks[i] for i in range(n_splits) if i not in chosen])
        s_is = np.asarray(score(m[rows_is]), dtype=float).ravel()
        s_oos = np.asarray(score(m[rows_oos]), dtype=float).ravel()
        if s_is.size != k or s_oos.size != k:
            raise ValueError(f"the metric returned {s_is.size} scores for {k} configurations; "
                             f"it must return exactly one score per column")
        if not (np.all(np.isfinite(s_is)) and np.all(np.isfinite(s_oos))):
            raise ValueError("the metric returned non-finite scores; a configuration that "
                             "cannot be scored on a block cannot be ranked against the rest")
        best = int(np.argmax(s_is))
        # Relative rank in (0, 1): rank 1..N over N+1 can never hit 0 or 1, so the logit is
        # always finite. That is the paper's construction, not a fudge to dodge infinities.
        omega = float(_average_ranks(s_oos)[best]) / (k + 1.0)
        logits[j] = math.log(omega / (1.0 - omega))
        selected[j] = best
        is_sel[j] = s_is[best]
        oos_sel[j] = s_oos[best]

    vx = float(is_sel.var())
    slope = (float(((is_sel - is_sel.mean()) * (oos_sel - oos_sel.mean())).mean() / vx)
             if vx > 0 else None)
    return PBOResult(
        value=float(np.mean(logits <= 0.0)), n_splits=n_splits, n_combinations=n_comb,
        n_configs=k, logits=logits, selected=selected, is_scores=is_sel, oos_scores=oos_sel,
        prob_oos_loss=float(np.mean(oos_sel <= 0.0)), degradation_slope=slope,
        reason=("fraction of splits where the in-sample winner fell below the out-of-sample "
                "median"))
