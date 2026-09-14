"""Can this hypothesis pay for itself, and could we even tell? Ask before backtesting.

WHY THIS MODULE EXISTS
----------------------
A 240-trial study on this repository's own data, run 2026-09-14, found that the binding
constraint on short-horizon index-futures strategies here is **transaction cost, not
direction**. Measured on the validation split:

    median cost per round turn                       $2.10
    median gross captured per round turn             $1.04
    cells positive on both selection splits          8 of 240   (a null predicts ~60)

and profitability fell monotonically with turnover: 33% of cells profitable at 1-3 round
turns per session, 17% at 3-10, 4% above 10. Thirty mechanisms and their exact inverses were
tested and nothing survived.

The lesson is not "try different indicators". It is that most of those 240 backtests were
answerable in advance with arithmetic. A mechanism predicting a two-tick move traded twenty
times a day cannot clear $2.10 a round turn, and no amount of parameter search changes that.
Running it anyway costs a backtest, adds a trial to the multiplicity denominator, and raises
the bar for everything tested afterwards.

So this module is a gate placed BEFORE the laboratory rather than after it.

TWO DIFFERENT WAYS TO BE HOPELESS, AND THEY ARE NOT THE SAME
------------------------------------------------------------
**INFEASIBLE** - the edge, even if entirely real and captured perfectly, does not pay its own
costs. This is a property of the mechanism and the fee schedule. More data will never fix it.
The only remedies are fewer trades, a bigger move, or a cheaper instrument.

**UNTESTABLE** - the edge might well be real and profitable, but it is too small to
distinguish from noise in the data we hold. This is a property of our sample. More data fixes
it; more cleverness does not. Measured per-session standard deviation of a one-lot always-in
rule is $222.70 on MES over 261 sessions, so an edge of $20 a session needs roughly 480
sessions to reach even an uncorrected t of 1.96, and we have 252.

Conflating these two is how a research programme wastes a year. The first says stop. The
second says go and get more data, or accept that the result will be a ranking rather than a
proof. `Verdict` keeps them apart.

WHAT THIS IS NOT
----------------
It is not a filter that decides what is true. It refuses hypotheses that arithmetic has
already answered, and it lets everything else through to be falsified properly. A mechanism
that passes here has earned a backtest, nothing more.

It is also not a licence to believe the numbers a researcher puts in. `expected_magnitude` and
`expected_trades` are estimates, usually from a paper measured on a different market in a
different decade. The `capture` parameter exists because the honest default is that we get a
fraction of a published effect, not all of it, and the fraction should be stated rather than
assumed to be one.
"""
from __future__ import annotations

import enum
import math
from dataclasses import dataclass

#: Measured per-session P&L standard deviation of a ONE-LOT ALWAYS-IN rule, in dollars, from
#: the real stores on 2026-09-14. This is the noise an edge has to be seen against.
#:
#: It is an upper bound for most strategies: a rule in the market a third of the session has
#: roughly a third of the variance, so using these numbers makes the detectability test
#: CONSERVATIVE. That is the right direction for a gate whose job is to stop us fooling
#: ourselves. `Hypothesis.time_in_market` scales it when a caller knows better.
SESSION_SIGMA: dict[str, float] = {
    "ES": 2085.9, "NQ": 4492.2, "MES": 222.7, "MNQ": 485.5,
}

#: Sessions actually available per instrument after the completeness filter, 2026-09-14.
SESSIONS_AVAILABLE: dict[str, int] = {"ES": 313, "NQ": 313, "MES": 252, "MNQ": 252}

#: Dollars per point. Derived from the instrument table and independently confirmed against
#: the venue's own `Contract/search` tick values on 2026-09-14.
POINT_VALUE: dict[str, float] = {"ES": 50.0, "NQ": 20.0, "MES": 5.0, "MNQ": 2.0}


class Verdict(str, enum.Enum):
    """Why a hypothesis may or may not proceed to a backtest."""

    #: The arithmetic works and the sample could see it. Go.
    FEASIBLE = "FEASIBLE"
    #: Pays for itself, but the effect is smaller than this sample can resolve. The result
    #: will be a ranking, never a proof. Proceed only with that written down.
    UNTESTABLE_HERE = "UNTESTABLE_HERE"
    #: Does not pay its own transaction costs even if captured perfectly. Stop.
    INFEASIBLE_COST = "INFEASIBLE_COST"
    #: The inputs needed to judge were not supplied. Not a verdict about the market.
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Assessment:
    """The arithmetic, kept so a reader can disagree with the inputs rather than the answer."""

    verdict: Verdict
    instrument: str
    gross_per_round_turn: float
    cost_per_round_turn: float
    edge_ratio: float
    net_per_session: float
    trades_per_session: float
    sessions_available: int
    sessions_needed_uncorrected: float
    sessions_needed_corrected: float
    reasons: tuple[str, ...] = ()

    @property
    def pays_for_itself(self) -> bool:
        return self.gross_per_round_turn > self.cost_per_round_turn

    def explain(self) -> str:
        lines = [
            f"{self.verdict.value} on {self.instrument}",
            f"  gross/round turn   ${self.gross_per_round_turn:,.2f}",
            f"  cost/round turn    ${self.cost_per_round_turn:,.2f}"
            f"   -> ratio {self.edge_ratio:.2f}x (needs > 1.00x)",
            f"  net/session        ${self.net_per_session:,.2f}"
            f"   at {self.trades_per_session:.2f} round turns",
            f"  sessions to detect {self.sessions_needed_uncorrected:,.0f} uncorrected, "
            f"{self.sessions_needed_corrected:,.0f} multiplicity-corrected",
            f"  sessions we have   {self.sessions_available}",
        ]
        lines += [f"  - {r}" for r in self.reasons]
        return "\n".join(lines)


def round_turn_cost(instrument: str, contracts: int = 1) -> float:
    """The real modelled cost, from the execution simulator rather than a constant here.

    Imported lazily so this module stays importable in a context with no market package
    loaded, and so there is exactly one place in the repository that knows what a round turn
    costs.
    """
    from quant_brain.markets.futures_cme import execution_sim as ex

    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(instrument),
                                symbol=instrument)
    return float(sim.round_turn_cost(contracts))


def assess(*, instrument: str, expected_magnitude_points: float | None,
           expected_trades_per_session: float | None, capture: float = 0.5,
           contracts: int = 1, time_in_market: float = 1.0,
           sessions: int | None = None, trials: int = 1) -> Assessment:
    """Decide whether a hypothesis has earned a backtest.

    `capture` is the fraction of the published or theorised move we expect to actually keep
    after entering late, exiting early and crossing the spread. The default of 0.5 is
    deliberately pessimistic and deliberately explicit: assuming 1.0 is the single most common
    way a feasibility estimate flatters a hypothesis, and a researcher who believes they will
    capture more should have to type the number.

    `time_in_market` scales the noise. `SESSION_SIGMA` is measured for an always-in rule, so a
    strategy in the market a third of the session faces roughly a third of the variance. Left
    at 1.0 the detectability test is conservative.

    `trials` is the size of the search this hypothesis belongs to. Detectability is reported
    against a Bonferroni-corrected bar as well as an uncorrected one, because a hypothesis
    that is only visible at t = 1.96 inside a 240-trial programme is not visible at all.
    """
    reasons: list[str] = []
    inst = instrument.upper()
    cost = round_turn_cost(inst, contracts)
    pv = POINT_VALUE.get(inst)
    n = sessions if sessions is not None else SESSIONS_AVAILABLE.get(inst, 0)

    if expected_magnitude_points is None or expected_trades_per_session is None or pv is None:
        missing = [nm for nm, v in (("expected_magnitude_points", expected_magnitude_points),
                                    ("expected_trades_per_session",
                                     expected_trades_per_session),
                                    ("point value", pv)) if v is None]
        return Assessment(Verdict.UNKNOWN, inst, 0.0, cost, 0.0, 0.0, 0.0, n,
                          math.inf, math.inf,
                          (f"cannot judge: {', '.join(missing)} not supplied. This is a gap "
                           f"in the hypothesis, not a finding about the market.",))

    gross_rt = expected_magnitude_points * pv * capture * contracts
    ratio = gross_rt / cost if cost > 0 else math.inf
    net_session = (gross_rt - cost) * expected_trades_per_session

    sigma = SESSION_SIGMA.get(inst, 0.0) * contracts * max(time_in_market, 1e-9)
    if net_session <= 0 or sigma <= 0:
        need_unc = need_cor = math.inf
    else:
        # n such that mean / (sigma/sqrt(n)) = z  ->  n = (z * sigma / mean)^2
        z_cor = _bonferroni_z(trials)
        need_unc = (1.96 * sigma / net_session) ** 2
        need_cor = (z_cor * sigma / net_session) ** 2

    if ratio <= 1.0:
        reasons.append(
            f"the move is worth ${gross_rt:,.2f} a round turn at {capture:.0%} capture and "
            f"the round turn costs ${cost:,.2f}. No parameter search fixes this; only fewer "
            f"trades, a larger move, or a cheaper instrument.")
        return Assessment(Verdict.INFEASIBLE_COST, inst, gross_rt, cost, ratio, net_session,
                          expected_trades_per_session, n, need_unc, need_cor, tuple(reasons))

    if need_cor > n:
        reasons.append(
            f"it pays for itself at {ratio:.2f}x, but ${net_session:,.2f} a session against "
            f"${sigma:,.0f} of per-session noise needs {need_cor:,.0f} sessions to clear a "
            f"{trials}-trial corrected bar and we hold {n}. Testable as a ranking, not as a "
            f"proof. More data fixes this; more cleverness does not.")
        return Assessment(Verdict.UNTESTABLE_HERE, inst, gross_rt, cost, ratio, net_session,
                          expected_trades_per_session, n, need_unc, need_cor, tuple(reasons))

    reasons.append(
        f"pays for itself at {ratio:.2f}x and needs {need_cor:,.0f} of our {n} sessions to "
        f"clear a {trials}-trial corrected bar.")
    return Assessment(Verdict.FEASIBLE, inst, gross_rt, cost, ratio, net_session,
                      expected_trades_per_session, n, need_unc, need_cor, tuple(reasons))


def _bonferroni_z(trials: int) -> float:
    """The two-sided normal quantile for alpha = 0.05 / trials.

    Uses the repository's own `stats.bonferroni_threshold` so the bar here and the bar the
    ledger applies to a verdict cannot drift apart.
    """
    if trials <= 1:
        return 1.96
    from quant_brain.core.stats import bonferroni_threshold
    return float(bonferroni_threshold(trials))


def required_accuracy(instrument: str, median_move_dollars: float, *,
                      contracts: int = 1) -> float:
    """The directional hit rate a strategy needs, at a horizon whose median move is given.

    THIS IS THE RESEARCH TARGET, and it is the number this whole module exists to produce.

    A strategy that holds for one horizon and is right with probability p earns, in
    expectation, |move| x (2p - 1) per round turn, and pays the round-turn cost regardless.
    Setting that above zero:

        p > 0.5 + cost / (2 x |move|)

    Measured on the real stores 2026-09-14, using the median absolute 30-minute move:

        MNQ   51.4%      MES   54.3%      ES   52.9%      NQ   51.2%

    Those are small numbers and that is the point. The barrier is not the fee schedule; it is
    finding any signal at all with a hit rate a point or two above a coin. The 240-trial
    tournament captured a median of **0.24% of the theoretical ceiling**, which is what a
    hit rate indistinguishable from 50% looks like from the outside. It needed roughly 3%.

    So a research programme aimed at cutting costs or cutting turnover is aimed at the wrong
    thing. Both help, and neither closes a thirteen-fold gap in signal.
    """
    cost = round_turn_cost(instrument, contracts)
    if median_move_dollars <= 0:
        return float("inf")
    return 0.5 + cost / (2.0 * median_move_dollars * contracts)


def break_even_magnitude(instrument: str, *, capture: float = 0.5,
                         contracts: int = 1) -> float:
    """The smallest move, in points, that pays for its own round turn.

    The single most useful number for a researcher to hold in their head before proposing
    anything. On the measured cost schedule and a 50% capture assumption it is about 0.99
    points on MES and 1.72 on MNQ - roughly four and seven ticks respectively.
    """
    pv = POINT_VALUE[instrument.upper()]
    return round_turn_cost(instrument, contracts) / (pv * capture * contracts)


@dataclass(frozen=True)
class CombineRequirement:
    """What an edge must be worth to matter here, from both ends at once.

    The feasibility gate above asks "is this hypothesis worth testing". This asks the more
    useful question in the other direction: **what would a strategy have to be, for us to both
    pass the Combine with it and be able to tell that it is real?**

    Two bars, and they are different in kind:

    `target_per_session` is an ECONOMIC bar. $3,000 of profit spread over the number of
    sessions you are willing to take. It does not care about noise.

    `detectable_per_session` is an EPISTEMIC bar. The smallest per-session edge that clears
    t = 1.96 over the sessions we hold, given the noise a strategy of this participation
    faces. It does not care about the Combine.

    The relationship between them is the whole research programme in one number. When the
    economic bar is ABOVE the epistemic bar, any strategy good enough to pass is also large
    enough for us to see, and a null result is real evidence of absence. When it is below,
    a strategy could be good enough to pass and still be invisible in our sample, and a null
    result means nothing.
    """

    instrument: str
    sessions_to_target: int
    target_per_session: float
    detectable_per_session: float
    sessions_available: int
    time_in_market: float

    @property
    def a_passing_edge_would_be_visible(self) -> bool:
        return self.target_per_session >= self.detectable_per_session

    def explain(self) -> str:
        v = ("a passing edge WOULD be visible in this sample"
             if self.a_passing_edge_would_be_visible else
             "a passing edge could be INVISIBLE in this sample - a null result proves nothing")
        return (f"{self.instrument}: to make ${3000:,.0f} in "
                f"{self.sessions_to_target} sessions needs "
                f"${self.target_per_session:,.2f}/session. Smallest edge visible in "
                f"{self.sessions_available} sessions at {self.time_in_market:.0%} "
                f"participation: ${self.detectable_per_session:,.2f}/session. -> {v}")


def combine_requirement(instrument: str, *, sessions_to_target: int = 60,
                        profit_target: float = 3_000.0, contracts: int = 1,
                        time_in_market: float = 0.15,
                        sessions: int | None = None) -> CombineRequirement:
    """The two bars, side by side.

    `time_in_market` defaults to 0.15 rather than 1.0 here because the question is about a
    realistic Combine strategy, and a rule that is in the market all session is not one - it
    is buy-and-hold with a sign, which this repository's own tournament found to be the
    degenerate case. Fifteen per cent is roughly one hour of a six-and-a-quarter-hour session.
    """
    inst = instrument.upper()
    n = sessions if sessions is not None else SESSIONS_AVAILABLE.get(inst, 0)
    sigma = SESSION_SIGMA.get(inst, 0.0) * contracts * max(time_in_market, 1e-9)
    detectable = 1.96 * sigma / math.sqrt(n) if n > 0 else math.inf
    return CombineRequirement(inst, sessions_to_target,
                              profit_target / max(sessions_to_target, 1),
                              detectable, n, time_in_market)


def assess_all(**kw) -> dict[str, Assessment]:
    """The same hypothesis across every instrument we hold, because feasibility is a property
    of the pair and not of the idea. A mechanism that is hopeless on MNQ can be comfortable on
    MES: the cost is $1.72 against $2.47 but the point is worth $2 against $5."""
    kw.pop("instrument", None)
    return {i: assess(instrument=i, **kw) for i in ("MES", "MNQ", "ES", "NQ")}


__all__ = ["Assessment", "CombineRequirement", "SESSIONS_AVAILABLE",
           "SESSION_SIGMA", "Verdict", "assess", "assess_all",
           "break_even_magnitude", "combine_requirement",
           "required_accuracy", "round_turn_cost"]
