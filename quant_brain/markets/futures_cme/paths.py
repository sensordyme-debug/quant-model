"""Monte Carlo path generation and deliberate failure testing for the prop-firm objective.

Parts 23 and 25. The twin takes paths and reports a distribution; this is where the paths
come from, and where they are made hostile on purpose.

WHY RESAMPLING AND NOT THE BACKTEST
------------------------------------
A backtest produces one ordering of one set of sessions. Against an absorbing barrier that is
almost no information: the same sessions in a different order can pass comfortably or die in
week two, because what kills a prop account is not the mean, it is where the losing run
happens to fall. The distribution of outcomes over orderings is the answer; the single
realised ordering is one draw from it, and the least interesting one, because it is the draw
the strategy was selected on.

WHICH RESAMPLER, AND WHY IT MATTERS MORE HERE THAN USUAL
----------------------------------------------------------
IID resampling destroys serial dependence. For a mean that barely matters; against an
absorbing barrier it matters enormously, because clustering is what produces both the losing
runs that breach a limit and the winning runs that reach a target.

The direction is NOT one-way, and it is worth being exact because the obvious intuition is
wrong. Clustering raises the variance of cumulative P&L. Against the drawdown barrier that
hurts. Against a profit target that is close by, it HELPS - a clustered series reaches +$3,000
sooner. Which effect dominates depends on the strategy and the account, and measurement here
found both signs: on an AR(0.9) series the block bootstrap passed the Combine 15 percentage
points MORE often than IID, the opposite of what "clustering is dangerous" would predict.

So `iid` is a sensitivity reference, not a conservative bound. `clustering_premium` reports
the gap without asserting a sign; a large gap in either direction means the block length has
become a load-bearing assumption that has to be justified rather than defaulted.

Default is the moving-block bootstrap at a block length the caller must choose, matching
`stats.block_bootstrap_t`, which this repository already trusts.

WHAT FAILURE TESTING IS FOR
---------------------------
Part 25 asks for the strategy to be tested to destruction rather than to significance. The
scenarios here are not forecasts and are not weighted by probability; they answer "what would
have to be true for this to fail", which is a question with an answer even when the
probability of the scenario is unknown. `break_even_shock` inverts it and solves for the
smallest adverse shift that breaks the strategy - usually far more informative than any
single scenario, because it is a number the owner can compare against their own judgement.
"""
from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from quant_brain.markets.futures_cme.twin import TopstepTwin, TwinDay, evaluate_twin


def _pnl(days: Sequence[TwinDay]) -> np.ndarray:
    return np.array([d.pnl for d in days], dtype=float)


# ======================================================================================
# PATH RECONSTRUCTION
# ======================================================================================
#
# THE RATIO BUG, AND WHY THE PRIMITIVES ARE SPLIT
# -----------------------------------------------
# Every session carries an intraday path, and Topstep's MLL is tested on that path rather
# than on the close, so how a path is reconstructed when a session is moved or transformed
# decides whether a breach is seen. This used to be one function that rescaled the template
# day's path by `new_pnl / template_pnl`. That ratio is UNBOUNDED, and the resamplers fed it
# a P&L from one session and the intraday shape of an unrelated one, so a template day that
# happened to close near flat became a divide-by-almost-zero:
#
#     template  pnl   +1.00  path (-900, +1)      # a real session: -$900 at its worst
#     resampled pnl  -100.00 -> k = -100
#     reconstructed          path (+90,000, -100) # a $90k intraday swing that never happened
#
# Measured on a 60-session fixture whose worst mark anywhere was -$900, the median resampled
# path reached -$476,410. It also flips sign whenever k < 0, so the -$900 trough above became
# a +$90,000 PEAK and the day was reported with no drawdown at all - the intraday breach test
# silently disappearing is the more dangerous half of the two.
#
# The replacement is three primitives, each bounded, each linear in the inputs (multiply
# every P&L and every path by 10 and every output multiplies by 10 - see the scale test):
#
#   _lay_out   move whole sessions - P&L and its own path together - onto a calendar.
#              Used by every resampler and every reordering. Nothing is rescaled, so each
#              reconstructed session's worst mark IS some real session's worst mark.
#   _shifted   change a session's close by a fixed amount; the change accrues linearly
#              across the session. For costs, decay, and any additive transform.
#   _scaled_day  multiply a session, path and all. For position size and loss scaling.
#
# A caller must say which of the three it means. The old single function could not know, and
# defaulting to the ratio is what produced the blow-up.
#
# WHAT IT COST, AND WHY NO TEST CAUGHT IT
# ----------------------------------------
# Measured on the 325 real ES sessions behind `futures_topstep_baseline`, whose worst single
# session mark is -$1,106 and thirteen of which close within $5 of flat:
#
#                pass    paid     liq   median worst mark
#     old        1.7%    0.0%  100.0%        -$599,614
#     fixed     32.0%   22.0%   97.3%          -$1,917
#
# So the defect was PESSIMISTIC, not optimistic - it manufactured liquidations, and the
# `MIN_PASS_RATE` gate in the discovery funnel would have thrown away strategies on paths
# that could not happen. Every twin number computed on real intraday paths before this fix
# is void in that direction.
#
# It survived a full test suite because every fixture here used `u_shaped_path`, whose marks
# are PROPORTIONAL to the close. Rescaling a proportional path by a ratio maps it onto
# another proportional path, so the bug is close to invisible on synthetic shapes (68.8%
# against 66.2% on the standard fixture) and only bites on real, non-proportional paths -
# which is to say, only in production. That is the argument for the hand-computed fixtures
# in `tests/test_path_reconstruction.py` carrying non-proportional paths on purpose.


def _lay_out(source: Sequence[TwinDay], idx: Sequence[int],
             calendar: Sequence[dt.date]) -> list[TwinDay]:
    """Whole sessions, in the order `idx` names, re-dated onto `calendar`.

    P&L and intraday path travel together and neither is touched. This is the only
    reconstruction a resampler or a reordering is allowed to perform.
    """
    return [TwinDay(day=d, pnl=source[i].pnl, path=source[i].path,
                    traded=source[i].traded)
            for i, d in zip(idx, calendar, strict=True)]


def _shifted(day: TwinDay, pnl: float) -> TwinDay:
    """The same session closing at `pnl`, its excursion carried across unchanged.

    The difference is accrued LINEARLY through the session rather than applied as a ratio:
    mark `t` of `n` moves by `(pnl - day.pnl) * (t + 1) / n`, so the last mark moves the whole
    way and the path still ends at the close. Bounded by construction - the worst mark can
    move by at most the size of the change - and it needs no special case for a flat day.
    """
    delta = float(pnl) - day.pnl
    if not day.path or delta == 0.0:
        return TwinDay(day=day.day, pnl=float(pnl), path=day.path, traded=day.traded)
    n = len(day.path)
    path = tuple(m + delta * (t + 1) / n for t, m in enumerate(day.path))
    return TwinDay(day=day.day, pnl=float(pnl), path=path, traded=day.traded)


def _scaled_day(day: TwinDay, k: float) -> TwinDay:
    """The whole session multiplied: twice the size is twice the P&L AND twice the swing."""
    return TwinDay(day=day.day, pnl=day.pnl * k,
                   path=tuple(m * k for m in day.path), traded=day.traded)


def _rebuild(template: Sequence[TwinDay], pnl: Sequence[float] | np.ndarray) -> list[TwinDay]:
    """Re-close each template session at the matching P&L. An ADDITIVE re-lay - see above.

    `strict=True` on the zip is deliberate: a length mismatch used to truncate in silence,
    which is the same family of defect as the ratio blow-up this replaced.
    """
    return [_shifted(d, float(x)) for d, x in zip(template, pnl, strict=True)]


def _calendar(template: Sequence[TwinDay], length: int) -> list[dt.date]:
    """`length` session DATES, continuing the template's weekday spacing where it runs out.

    Only dates are extended. Sessions are never invented: a resampler emits `length` real
    sessions drawn from the input, so there is nothing to pad. The previous version padded
    the SESSION list with a copy of a real day and then rescaled a foreign P&L onto its
    intraday shape - the padding was harmless, the rescale was not.
    """
    out = [d.day for d in template[:length]]
    day = out[-1]
    while len(out) < length:
        day += dt.timedelta(days=1)
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        out.append(day)
    return out


# ======================================================================================
# RESAMPLERS
# ======================================================================================

def moving_block(days: Sequence[TwinDay], *, block: int, reps: int = 1000,
                 seed: int = 0, length: int | None = None) -> list[list[TwinDay]]:
    """Moving-block bootstrap. The default, because it keeps losing runs intact.

    `block` should be at least as long as the dependence you care about. For a prop-firm
    question that is the typical length of a losing run, not the label horizon - a block
    shorter than the runs will chop them up and flatter the pass rate.
    """
    n = len(days)
    if n < 2:
        raise ValueError(f"need at least 2 sessions to resample, got {n}")
    if block < 1:
        raise ValueError(f"block must be at least 1, got {block}")
    out_len = n if length is None else int(length)
    block = min(int(block), n)
    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(out_len / block))
    starts_max = n - block + 1
    paths: list[list[TwinDay]] = []
    template = list(days)
    cal = _calendar(template, out_len)
    for _ in range(reps):
        starts = rng.integers(0, starts_max, size=n_blocks)
        # INDICES, not P&L. The sampled session brings its own intraday path with it.
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:out_len]
        paths.append(_lay_out(template, idx.tolist(), cal))
    return paths


def stationary_bootstrap(days: Sequence[TwinDay], *, mean_block: float, reps: int = 1000,
                         seed: int = 0, length: int | None = None) -> list[list[TwinDay]]:
    """Politis-Romano: geometric block lengths, so the resample is stationary.

    Worth having beside `moving_block` because a fixed block length is itself an assumption,
    and results that flip between the two are telling you the answer depends on it.
    """
    n = len(days)
    if n < 2:
        raise ValueError(f"need at least 2 sessions to resample, got {n}")
    if mean_block < 1:
        raise ValueError(f"mean_block must be at least 1, got {mean_block}")
    out_len = n if length is None else int(length)
    p = 1.0 / mean_block
    rng = np.random.default_rng(seed)
    template = list(days)
    cal = _calendar(template, out_len)
    paths: list[list[TwinDay]] = []
    for _ in range(reps):
        idx = [0] * out_len
        i = int(rng.integers(0, n))
        for t in range(out_len):
            idx[t] = i
            i = int(rng.integers(0, n)) if rng.random() < p else (i + 1) % n
        paths.append(_lay_out(template, idx, cal))
    return paths


def iid(days: Sequence[TwinDay], *, reps: int = 1000, seed: int = 0,
        length: int | None = None) -> list[list[TwinDay]]:
    """IID resampling. A SENSITIVITY REFERENCE, not an estimate - see the module docstring.

    Compare its rates against the block bootstrap's. A large gap in EITHER direction says the
    answer depends on the dependence structure, and therefore on the block length, which is
    then a modelling choice that needs defending. It is not a conservative bound: clustering
    can raise the pass rate as easily as lower it.
    """
    n = len(days)
    if n < 2:
        raise ValueError(f"need at least 2 sessions to resample, got {n}")
    out_len = n if length is None else int(length)
    rng = np.random.default_rng(seed)
    template = list(days)
    cal = _calendar(template, out_len)
    return [_lay_out(template, rng.integers(0, n, size=out_len).tolist(), cal)
            for _ in range(reps)]


# ======================================================================================
# FAILURE TESTING (Part 25)
# ======================================================================================

@dataclass(frozen=True)
class Scenario:
    """One adverse transformation of a session series, with a name that says what it assumes.

    Deliberately not carrying a probability. Assigning one would invite the scenarios to be
    averaged into an expected value, which is precisely the operation that makes stress
    testing useless - the point is the conditional answer, not its weighted contribution.
    """

    name: str
    describe: str
    #: Leading sessions the stress harness must hold in place instead of resampling.
    #:
    #: An ordering scenario is destroyed by a bootstrap. `WorstRunFirst` moves the worst
    #: stretch to day one, and a moving-block resample immediately shuffles it back into the
    #: middle - which is not a subtle loss of power, it inverts the result: before this field
    #: existed, "worst 10 days first" measured as SAFER than the base case (93.2% pass against
    #: 91.2%), because the reordering also happened to break up a losing run the base ordering
    #: contained. Pinning the prefix keeps the scenario's content and still bootstraps the
    #: remainder, so the answer stays a distribution rather than a single path.
    pin_prefix: int = 0

    def apply(self, days: Sequence[TwinDay]) -> list[TwinDay]:
        raise NotImplementedError


@dataclass(frozen=True)
class ScaleLosses(Scenario):
    """Every losing day is worse by a factor. Models cost or slippage being underestimated."""

    factor: float = 1.5

    def apply(self, days):
        # A MULTIPLICATIVE re-lay: a session that loses 1.5x as much swung 1.5x as far
        # getting there. Bounded, because the factor is a constant rather than a ratio.
        return [_scaled_day(d, self.factor) if d.pnl < 0 else d for d in days]


@dataclass(frozen=True)
class AddCost(Scenario):
    """A fixed dollar cost per session. Models commission or spread being wrong."""

    per_day: float = 25.0

    def apply(self, days):
        return _rebuild(days, [d.pnl - self.per_day for d in days])


@dataclass(frozen=True)
class WorstRunFirst(Scenario):
    """The worst window moved to the front, before any buffer has been earned.

    The single most informative reordering for a trailing-drawdown account, because the
    account is at its most fragile on day one and a strategy's realised ordering almost never
    puts its worst stretch there.
    """

    window: int = 10

    def apply(self, days):
        a = _pnl(days)
        n = len(a)
        w = min(self.window, n)
        sums = np.convolve(a, np.ones(w), mode="valid")
        i = int(np.argmin(sums))
        # Whole sessions move, keeping their own intraday paths. Reordering the P&L series
        # alone and re-laying it on the original calendar is what turned "worst run first"
        # into a reconstruction with swings no session ever had.
        order = [*range(i, i + w), *range(0, i), *range(i + w, n)]
        return _lay_out(days, order, [d.day for d in days])


@dataclass(frozen=True)
class Shock(Scenario):
    """One catastrophic session inserted at a chosen point. A gap day.

    Size it BELOW the account's MLL. A shock at or beyond the limit liquidates a fresh
    account with probability one and so measures the rulebook, not the strategy.
    """

    size: float = -1_000.0
    at: int = 0

    def apply(self, days):
        """Insert one session; every real session keeps its own path and its own order.

        The inserted day needs an intraday shape, and inventing one silently is exactly what
        this module refuses to do elsewhere. So it borrows the shape of a real session and
        says which: the largest session that already moves the same way as the shock, or
        failing that the largest session outright. Taking the LARGEST keeps the rescaling
        factor as small as the data allows, which is the whole lesson of the ratio bug.
        """
        seq = list(days)
        at = max(0, min(self.at, len(seq)))
        usable = [d for d in seq if d.path and d.pnl != 0]
        same_sign = [d for d in usable if (d.pnl < 0) == (self.size < 0)]
        donor = max(same_sign or usable, key=lambda d: abs(d.pnl), default=None)
        path = ((self.size,) if donor is None
                else tuple(m * (self.size / donor.pnl) for m in donor.path))
        cal = _calendar(seq, len(seq) + 1)
        seq.insert(at, TwinDay(day=cal[at], pnl=float(self.size), path=path, traded=True))
        return _lay_out(seq, range(len(seq)), cal)


@dataclass(frozen=True)
class Decay(Scenario):
    """The edge fades linearly to `end_fraction` of itself. Models alpha decay."""

    end_fraction: float = 0.0

    def apply(self, days):
        a = _pnl(days)
        n = len(a)
        k = np.linspace(1.0, self.end_fraction, n)
        mu = a.mean()
        # Decay the EDGE, not the variance: shrink the mean toward zero and keep the noise.
        return _rebuild(days, (a - mu) + mu * k)


@dataclass(frozen=True)
class WidenIntraday(Scenario):
    """The intraday excursion is deeper than recorded, with the same close.

    Aimed squarely at Topstep's rule: the MLL is tested on the path, so a strategy whose
    survival depends on never having had a bad hour is fragile in a way the daily series
    cannot show.
    """

    factor: float = 1.5

    def apply(self, days):
        out = []
        for d in days:
            if not d.path:
                out.append(d)
                continue
            deeper = tuple(m * self.factor if m < 0 else m for m in d.path[:-1])
            # The CLOSE is the one mark this scenario must not move - widening it too would
            # hand the twin a terminal mark that disagrees with the day's settled P&L.
            out.append(TwinDay(day=d.day, pnl=d.pnl, path=(*deeper, d.path[-1]),
                               traded=d.traded))
        return out


DEFAULT_SCENARIOS: tuple[Scenario, ...] = (
    ScaleLosses(name="losses +50%", describe="every losing day 1.5x worse", factor=1.5),
    AddCost(name="cost +$25/day", describe="an extra $25 of cost per session", per_day=25.0),
    WorstRunFirst(name="worst 10d first",
                  describe="the worst ten-day stretch moved to day one", window=10,
                  pin_prefix=10),
    # Sized against the INTRADAY trough, not the close. The shock day borrows a real
    # session's shape, so with u_shaped_path(1.4) a close of -X dips to about -1.4X, and the
    # binding constraint on a fresh $2,000 MLL is 1.4X < 2000 - i.e. any close worse than
    # about -$1,430 is certain death regardless of what follows. -$3,000 and -$1,500 both
    # measured 100.0% liquidated for that reason, which tests the rulebook rather than the
    # strategy. -$1,000 troughs around -$1,400 and survives the day with $600 of room, making
    # the interesting question askable: can the account climb back out from there? The exact
    # trough now depends on the donor session, so the test asserts the built path rather
    # than a hard-coded 1.4.
    Shock(name="-$1,000 shock on day 1",
          describe="a bad gap before any buffer exists, surviving the day", size=-1_000.0,
          at=0, pin_prefix=1),
    Decay(name="edge decays to zero",
          describe="the mean fades linearly to nothing", end_fraction=0.0),
    WidenIntraday(name="intraday 1.5x deeper",
                  describe="the same closes, worse excursions", factor=1.5),
)


@dataclass
class StressReport:
    """Base case and each scenario, side by side."""

    base: dict
    scenarios: dict[str, dict]

    def table(self) -> str:
        rows = [f"{'scenario':<28} {'pass':>7} {'paid':>7} {'liq':>7} {'E[gross]':>10}",
                "-" * 62,
                _row("base", self.base)]
        rows.extend(_row(k, vals) for k, vals in self.scenarios.items())
        return "\n".join(rows)

    def worst(self) -> tuple[str, dict]:
        """The scenario that hurts the paid rate most. Usually the one worth arguing about."""
        if not self.scenarios:
            return "base", self.base
        name = min(self.scenarios, key=lambda k: self.scenarios[k]["p_first_payout"])
        return name, self.scenarios[name]


def _row(name: str, d: dict) -> str:
    return (f"{name:<28} {d['p_pass_combine']:>6.1%} {d['p_first_payout']:>6.1%} "
            f"{d['p_liquidated']:>6.1%} {d['mean_gross']:>10,.0f}")


def resample_with_prefix(days: Sequence[TwinDay], *, pin: int, block: int,
                         reps: int, seed: int) -> list[list[TwinDay]]:
    """Bootstrap the tail while holding the first `pin` sessions in place.

    The two halves of a stress test that a plain bootstrap cannot hold at once: the scenario's
    ordering, and a distribution over everything that follows it.
    """
    if pin <= 0:
        return moving_block(days, block=block, reps=reps, seed=seed)
    pin = min(pin, len(days) - 1)
    head, tail = list(days[:pin]), list(days[pin:])
    if len(tail) < 2:
        return [list(days)] * reps
    return [head + t for t in moving_block(tail, block=block, reps=reps, seed=seed)]


def stress(twin: TopstepTwin, days: Sequence[TwinDay], *,
           scenarios: Sequence[Scenario] = DEFAULT_SCENARIOS,
           block: int = 10, reps: int = 500, seed: int = 0) -> StressReport:
    """Run the base case and every scenario through the twin on resampled paths.

    Each scenario is applied to the ORIGINAL sessions and then resampled - and any scenario
    declaring a `pin_prefix` keeps that many leading sessions fixed through the resample, so
    an ordering scenario survives the bootstrap instead of being shuffled away by it.
    """
    def run(d: Sequence[TwinDay], pin: int = 0) -> dict:
        paths = resample_with_prefix(d, pin=pin, block=block, reps=reps, seed=seed)
        ev = evaluate_twin(twin, paths)
        return {"p_pass_combine": ev.p_pass_combine, "p_first_payout": ev.p_first_payout,
                "p_liquidated": ev.p_liquidated, "mean_gross": ev.mean_gross,
                "mean_net": ev.mean_net}

    return StressReport(
        base=run(days),
        scenarios={s.name: run(s.apply(days), s.pin_prefix) for s in scenarios})


def break_even_shock(twin: TopstepTwin, days: Sequence[TwinDay], *,
                     target_paid_rate: float = 0.5,
                     block: int = 10, reps: int = 300, seed: int = 0,
                     lo: float = 0.0, hi: float = 200.0,
                     tol: float = 1.0) -> float:
    """The per-session cost increase that drags the payout rate down to `target_paid_rate`.

    Far more useful than any single scenario, because the answer is a number the owner can
    weigh against their own view: "this strategy stops paying if costs are $18 a day worse
    than modelled" is a claim someone can accept or reject from experience, where "it fails
    under a 1.5x cost shock" is not.

    Returns `hi` when even the largest tested shift leaves the rate above target - meaning the
    strategy is robust across the whole tested range, not that the answer is `hi`.
    """
    def paid_at(extra: float) -> float:
        d = _rebuild(days, [x.pnl - extra for x in days])
        return evaluate_twin(twin, moving_block(d, block=block, reps=reps,
                                                seed=seed)).p_first_payout

    if paid_at(lo) < target_paid_rate:
        return lo
    if paid_at(hi) >= target_paid_rate:
        return hi
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if paid_at(mid) >= target_paid_rate:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clustering_premium(twin: TopstepTwin, days: Sequence[TwinDay], *,
                       block: int = 10, reps: int = 500, seed: int = 0) -> dict[str, float]:
    """How much the answer depends on serial dependence. A sensitivity, with no assumed sign.

    Runs the same sessions through an IID resample and a block resample and reports both,
    plus the signed gap (iid minus block). A large magnitude in either direction means the
    block length is load-bearing and should be justified from the strategy's own losing-run
    lengths rather than defaulted.

    Do not read a positive gap as "clustering is dangerous" and a negative one as "clustering
    is safe". Clustering raises the variance of cumulative P&L, which hurts against the
    drawdown barrier and helps against a nearby profit target; measured on an AR(0.9) series
    the block bootstrap passed 15 points more often than IID. Only the magnitude is
    interpretable without further work.
    """
    block_ev = evaluate_twin(twin, moving_block(days, block=block, reps=reps, seed=seed))
    iid_ev = evaluate_twin(twin, iid(days, reps=reps, seed=seed))
    return {
        "block_pass": block_ev.p_pass_combine,
        "iid_pass": iid_ev.p_pass_combine,
        "block_paid": block_ev.p_first_payout,
        "iid_paid": iid_ev.p_first_payout,
        "pass_premium": iid_ev.p_pass_combine - block_ev.p_pass_combine,
        "paid_premium": iid_ev.p_first_payout - block_ev.p_first_payout,
    }


def with_scenario(twin: TopstepTwin, **kw) -> TopstepTwin:
    """A copy of a twin with constructor-independent attributes overridden."""
    clone = object.__new__(TopstepTwin)
    clone.__dict__.update(twin.__dict__)
    for k, val in kw.items():
        if not hasattr(clone, k):
            raise AttributeError(f"TopstepTwin has no attribute {k!r}")
        setattr(clone, k, val)
    return clone


def scaled(days: Sequence[TwinDay], factor: float) -> list[TwinDay]:
    """Every session scaled - the crudest position-size lever, and a useful sweep axis."""
    if factor <= 0:
        raise ValueError(f"factor must be positive, got {factor}")
    # Multiplicative, path and all: trading twice the contracts doubles the intraday swing
    # as well as the close, and a size sweep that widened only the close would understate
    # liquidation risk at exactly the sizes it exists to warn about.
    return [_scaled_day(d, factor) for d in days]


def size_sweep(twin: TopstepTwin, days: Sequence[TwinDay],
               factors: Sequence[float] = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0),
               *, block: int = 10, reps: int = 400, seed: int = 0) -> dict[float, dict]:
    """Pass and payout rates against position size.

    Against an absorbing barrier this is not monotone and that is the point: too small never
    reaches the target before the fee runs out, too large breaches. The optimum is interior,
    and a strategy tuned on Sharpe will not have found it because Sharpe is scale-invariant.
    """
    out: dict[float, dict] = {}
    for f in factors:
        paths = moving_block(scaled(days, f), block=block, reps=reps, seed=seed)
        ev = evaluate_twin(twin, paths)
        out[f] = {"p_pass_combine": ev.p_pass_combine, "p_first_payout": ev.p_first_payout,
                  "p_liquidated": ev.p_liquidated, "mean_gross": ev.mean_gross}
    return out


def best_size(sweep: dict[float, dict], key: str = "p_first_payout") -> float:
    """The size that maximises `key`. Ties go to the smaller size, which is the safer error."""
    return min(sweep, key=lambda f: (-sweep[f][key], f))


__all__ = [
    "AddCost", "Decay", "DEFAULT_SCENARIOS", "Scenario", "ScaleLosses", "Shock",
    "StressReport", "WidenIntraday", "WorstRunFirst", "best_size", "break_even_shock",
    "clustering_premium", "iid", "moving_block", "scaled", "size_sweep",
    "resample_with_prefix", "stationary_bootstrap", "stress", "with_scenario",
]
