"""A prop firm as two interfaces: the rules a strategy must obey, and the objective it is paid on.

Part 5: "Do not hard-code one firm's rules into the core. Individual prop firms should be
configuration/adapters on top of that interface." Part 25: the platform must be able to take
on a new firm with rules plus an adapter, and no strategy change. This module is the
interface those two parts ask for, and it is built on the machinery the futures branch
already has rather than beside it:

    PropFirmProfile          markets/futures_cme/propfirm.py   the rules as data
    PropFirmRiskEngine       ditto                              the gate
    PropFirmSimulator        ditto                              one evaluation, one path
    TopstepTwin              markets/futures_cme/twin.py        the whole Topstep lifecycle
    evaluate_twin            ditto                              the distribution

What was missing was the seam a REGISTRY can hold: something firm-agnostic that a venue can
carry, that can say "this strategy would break rule X" before any account is bought, and that
can turn a set of resampled session paths into one comparable result. `PropFirmRules` is the
first; `PropFirmObjective` is the second.

WHY THE OBJECTIVE IS NOT A NUMBER
---------------------------------
Part 6: "Do NOT optimize futures solely for CAGR or Sharpe." The prop-firm objective is
capital accumulation SUBJECT TO a breach constraint, and collapsing that to a scalar hides
which half a strategy is failing on. `ObjectiveResult` therefore carries the pieces - pass
rate, violation rate, ruin rate, days, payout, value after fees - and the scalar `score` is
derived from them by a `Scoring` whose every weight is a named constructor argument with a
documented default. The default weights are 1.0 on value after fees and 0 on everything else:
the objective IS expected value after fees, and the constraint is enforced as a constraint
(`max_p_ruin`) rather than blended in. Anyone who wants a different trade-off writes it down
in a `Scoring`, and the `Scoring` travels inside the result so a ranking can never be read
without seeing the weights that produced it.

WHAT "RUIN" MEANS HERE
----------------------
Not "did not pass". A path that runs out of sessions still inside the Combine has not been
ruined, it has been censored. Ruin is the account gone with nothing ever withdrawn - the fee
spent, no payout, the attempt over. That is the outcome an owner is actually afraid of, and
it is the one an expected-value figure hides best, because a small probability of it is
cheap in expectation and catastrophic in fact.
"""
from __future__ import annotations

import abc
import datetime as dt
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from quant_brain.markets.futures_cme import topstep as ts
from quant_brain.markets.futures_cme import twin as tw
from quant_brain.markets.futures_cme.propfirm import (
    AccountState,
    Outcome,
    PropFirmProfile,
    PropFirmRiskEngine,
    PropFirmSimulator,
    SessionPnL,
    TrailingMode,
    evaluate,
)
from quant_brain.venues.base import StrategyProfile

#: One path of sessions, in the twin's own shape. Every objective consumes this so that a
#: registry can hand the SAME paths to every venue's objective and compare like with like.
Paths = Sequence[Sequence[tw.TwinDay]]


# =====================================================================================
# THE SCORING - every weight explicit, every weight visible in the result
# =====================================================================================

@dataclass(frozen=True)
class Scoring:
    """How `ObjectiveResult.score` is computed. Nothing in the scoring is implicit.

        score = value_weight * expected_value_after_fees
              - ruin_penalty * p_ruin
              - days_penalty * expected_days

    Defaults are chosen so that the default score IS expected value after fees:

        value_weight   1.0   dollars count one for one
        ruin_penalty   0.0   ruin is a CONSTRAINT (`max_p_ruin`), not a price. Pricing it
                             invites "a 30% chance of losing the account is fine at $X",
                             which is a sentence Part 6 exists to forbid by default.
        days_penalty   0.0   time to resolution is reported, not charged; a caller with a
                             real cost of capital sets dollars per day here.
        max_p_ruin     None  no constraint. Set it and a result above it is `acceptable ==
                             False`, which the registry treats as a rule violation.

    A score is None when its inputs are unknown: no fee means no value after fees, and a
    non-zero `days_penalty` with no resolved paths has nothing to charge. None is refused by
    the registry when ranking, never silently ranked last.
    """

    value_weight: float = 1.0
    ruin_penalty: float = 0.0
    days_penalty: float = 0.0
    max_p_ruin: float | None = None

    def __post_init__(self) -> None:
        if self.value_weight <= 0:
            raise ValueError(f"value_weight must be positive, got {self.value_weight}; a zero "
                             f"or negative weight on value would rank on penalties alone")
        if self.ruin_penalty < 0 or self.days_penalty < 0:
            raise ValueError("penalties are subtracted and must be non-negative")
        if self.max_p_ruin is not None and not 0.0 <= self.max_p_ruin <= 1.0:
            raise ValueError(f"max_p_ruin must be a probability, got {self.max_p_ruin}")

    def score(self, *, expected_value_after_fees: float | None, p_ruin: float,
              expected_days: float | None) -> float | None:
        if expected_value_after_fees is None:
            return None
        s = self.value_weight * expected_value_after_fees - self.ruin_penalty * p_ruin
        if self.days_penalty:
            if expected_days is None:
                return None
            s -= self.days_penalty * expected_days
        return s

    def as_dict(self) -> dict[str, float | None]:
        return {"value_weight": self.value_weight, "ruin_penalty": self.ruin_penalty,
                "days_penalty": self.days_penalty, "max_p_ruin": self.max_p_ruin}


@dataclass(frozen=True)
class ObjectiveResult:
    """What one strategy is worth on one firm's rules, over many paths, with the weights shown.

    `expected_value_after_fees` is None when the fee is unknown, by the same rule twin.py
    applies to `net_capital`: a profit figure that quietly omits the cost of the attempts is
    the number most likely to be believed and most likely to be wrong.
    """

    label: str
    paths: int
    p_pass: float
    p_violation: float
    p_ruin: float
    expected_days: float | None
    expected_payout: float
    expected_value_after_fees: float | None
    scoring: Scoring
    reasons: tuple[str, ...] = ()

    @property
    def score(self) -> float | None:
        return self.scoring.score(expected_value_after_fees=self.expected_value_after_fees,
                                  p_ruin=self.p_ruin, expected_days=self.expected_days)

    @property
    def acceptable(self) -> bool:
        """Inside the ruin constraint, if one was set. True when none was."""
        cap = self.scoring.max_p_ruin
        return cap is None or self.p_ruin <= cap

    def summary(self) -> str:
        ev = (f"E[net] ${self.expected_value_after_fees:,.0f}"
              if self.expected_value_after_fees is not None else "E[net] UNKNOWN (fee)")
        days = f"{self.expected_days:.0f}d" if self.expected_days is not None else "unresolved"
        score = f"{self.score:,.0f}" if self.score is not None else "none"
        return (f"{self.label}: pass {self.p_pass:.1%} violate {self.p_violation:.1%} "
                f"ruin {self.p_ruin:.1%} over {self.paths} paths, {days}, "
                f"E[payout] ${self.expected_payout:,.0f}, {ev}, score {score} "
                f"[weights {self.scoring.as_dict()}]")


class PropFirmObjective(abc.ABC):
    """Turn resampled session paths into one `ObjectiveResult`.

    One method, on purpose. The resampling is the caller's (paths.py has strong opinions and
    the objective must not override them); the rules are the firm's; the objective only
    joins the two and reports. Anything with more surface than this starts to make research
    decisions on the caller's behalf.
    """

    scoring: Scoring = Scoring()

    @abc.abstractmethod
    def evaluate(self, paths: Paths) -> ObjectiveResult:
        """Run every path through the firm's rules and summarise the distribution."""


def _check_paths(paths: Paths) -> list[list[tw.TwinDay]]:
    out = [list(p) for p in paths]
    if not out:
        raise ValueError("no paths supplied; an objective over zero paths is not an estimate")
    if any(not p for p in out):
        raise ValueError("a path with no sessions cannot be evaluated")
    return out


class TwinObjective(PropFirmObjective):
    """The Topstep objective: `evaluate_twin` over the whole Combine -> XFA -> payout lifecycle.

    Composes the twin rather than re-deriving it. The aggregate comes from `evaluate_twin`
    so its definitions - what counts as passing, what a payout is, when the fee is known -
    stay owned by twin.py and move with it. Two of the fields this result needs are not in
    that aggregate (violation and ruin are per-path facts), so there is a second explicit
    pass over `twin.run` for those two alone. It is a second run, not a second definition,
    and the cost is one more traversal of paths that take milliseconds each.
    """

    def __init__(self, twin: tw.TopstepTwin, *, scoring: Scoring | None = None,
                 label: str = ""):
        self.twin = twin
        self.scoring = scoring or Scoring()
        self.label = label

    def evaluate(self, paths: Paths) -> ObjectiveResult:
        runs = _check_paths(paths)
        ev = tw.evaluate_twin(self.twin, runs, label=self.label)
        results = [self.twin.run(p) for p in runs]
        n = len(results)
        liquidated = ts.TopstepStage.LIQUIDATED
        p_violation = sum(r.breach_day is not None for r in results) / n
        p_ruin = sum((r.terminal is liquidated and not r.payouts) for r in results) / n
        resolved = [r.days for r in results if r.terminal is liquidated or r.reached_funding]
        expected_days = statistics.fmean(resolved) if resolved else None

        reasons: list[str] = []
        if not ev.fee_known:
            reasons.append("combine fee unknown: expected_value_after_fees is None and the "
                           "result cannot be scored. Pass combine_fee to TopstepRules or the "
                           "twin; Topstep's pricing is in topstep.COMBINE_COST with its source.")
        censored = n - len(resolved)
        if censored:
            reasons.append(f"{censored} of {n} paths ended still inside the Combine; "
                           f"expected_days is over the {len(resolved)} resolved paths only")
        if not ev.p_first_payout and ev.p_pass_combine:
            reasons.append("Combines were passed but no path reached a payout: the second "
                           "barrier (XFA at $0 with the same MLL) is the binding one")
        return ObjectiveResult(
            label=ev.label, paths=n, p_pass=ev.p_pass_combine, p_violation=p_violation,
            p_ruin=p_ruin, expected_days=expected_days, expected_payout=ev.mean_gross,
            expected_value_after_fees=ev.mean_net, scoring=self.scoring,
            reasons=tuple(reasons))


class ProfileObjective(PropFirmObjective):
    """The generic objective: `propfirm.evaluate` over ONE evaluation of ANY profile.

    This is what makes a new firm evaluable with no new code. A firm that has published a
    rulebook but has no digital twin gets `ProfileRules(profile)`, whose objective is this
    class: one absorbing-barrier evaluation, fee and payout from the profile. It is less than
    the Topstep twin knows (no second barrier, no payout policy) and the result says so in
    `reasons` rather than pretending the two are comparable without caveat.
    """

    def __init__(self, profile: PropFirmProfile, *, scoring: Scoring | None = None,
                 label: str = ""):
        self.profile = profile
        self.scoring = scoring or Scoring()
        self.label = label or profile.name

    @staticmethod
    def _sessions(path: Sequence[tw.TwinDay]) -> list[SessionPnL]:
        return [SessionPnL(day=d.day, pnl=d.pnl, intraday_equity=list(d.path), traded=d.traded)
                for d in path]

    def evaluate(self, paths: Paths) -> ObjectiveResult:
        runs = [self._sessions(p) for p in _check_paths(paths)]
        ev = evaluate(self.profile, runs)
        sim = PropFirmSimulator(self.profile)
        results = [sim.run(s) for s in runs]
        n = len(results)
        failed = sum(r.outcome.is_failure for r in results) / n
        resolved = [r.days for r in results if r.outcome is not Outcome.IN_PROGRESS]

        reasons: list[str] = []
        if self.profile.evaluation_fee == 0:
            reasons.append(f"{self.profile.name}: evaluation_fee is 0, so value after fees "
                           f"equals gross; confirm the fee before comparing firms")
        intraday = self.profile.trailing_mode in (TrailingMode.INTRADAY,
                                                  TrailingMode.EOD_TRAIL_INTRADAY_BREACH)
        if intraday:
            bare = sum(1 for s in runs for d in s if not d.intraday_equity)
            if bare:
                reasons.append(f"{bare} sessions carry no intraday path; the intraday breach "
                               f"test was skipped on them and the pass rate is an upper bound")
        reasons.append("single-evaluation objective: no funded stage, no payout policy; a "
                       "firm with a lifecycle twin is not directly comparable")
        return ObjectiveResult(
            label=self.label, paths=n, p_pass=ev.pass_rate, p_violation=failed,
            # One stage, so a violation forfeits the fee with nothing to offset it: ruin.
            p_ruin=failed,
            expected_days=statistics.fmean(resolved) if resolved else None,
            # evaluate() subtracts the fee once per path; add it back for the gross figure.
            expected_payout=ev.expected_capital + self.profile.evaluation_fee,
            expected_value_after_fees=ev.expected_capital, scoring=self.scoring,
            reasons=tuple(reasons))


# =====================================================================================
# THE RULES
# =====================================================================================

def _minutes(t: dt.time) -> int:
    return t.hour * 60 + t.minute


def _segments(window: tuple[dt.time, dt.time]) -> list[tuple[int, int]]:
    """A local-time window as closed minute intervals on [0, 1440), split if it wraps."""
    a, b = _minutes(window[0]), _minutes(window[1])
    if a <= b:
        return [(a, b)]
    return [(a, 24 * 60 - 1), (0, b)]


def windows_overlap(a: tuple[dt.time, dt.time], b: tuple[dt.time, dt.time]) -> bool:
    """Do two local-time windows share a minute? Inclusive at both ends, midnight-aware.

    Inclusive because `PropFirmRiskEngine.in_blackout` is (`start <= when <= end`), and a
    check that disagreed with the engine at the boundary minute would certify a strategy
    the engine then refuses at 08:33:00.
    """
    return any(x0 <= y1 and y0 <= x1 for x0, x1 in _segments(a) for y0, y1 in _segments(b))


def _fmt(w: tuple[dt.time, dt.time]) -> str:
    return f"{w[0].isoformat('minutes')}-{w[1].isoformat('minutes')}"


class PropFirmRules(abc.ABC):
    """One firm's rulebook, in the shape a venue can carry and a registry can query.

    Three questions, and a fourth a firm may answer:

        profile()      the rules as data - the existing `PropFirmProfile`
        objective()    how this firm pays, as a `PropFirmObjective`
        check()        which rules a strategy's declared shape would break, statically
        unresolved()   rules the firm has not published, so nobody buys an account on a guess

    `check` is implemented ONCE, here, against the generic profile. That is what makes a new
    firm rules-plus-adapter: a subclass supplies a profile and an objective, and inherits the
    compliance check without writing one. A firm whose rule does not fit the profile extends
    the profile (as `TrailingMode.EOD_TRAIL_INTRADAY_BREACH` did for Topstep), not this
    method.
    """

    name: str = "rules"

    @property
    @abc.abstractmethod
    def profile(self) -> PropFirmProfile:
        """The rules a strategy is gated by. For a staged firm, the stage it enters first."""

    @abc.abstractmethod
    def objective(self) -> PropFirmObjective:
        """How the firm pays, as something `evaluate(paths)` can be called on."""

    def stages(self) -> Sequence[PropFirmProfile]:
        """Every profile a strategy will trade under. A strategy must comply with all of them."""
        return (self.profile,)

    def unresolved(self) -> Mapping[str, object]:
        """Rules below documentation confidence. Empty unless the firm says otherwise."""
        return {}

    def risk_engine(self, state: AccountState | None = None) -> PropFirmRiskEngine:
        """The deterministic gate for one live account under these rules."""
        return PropFirmRiskEngine(state or AccountState(profile=self.profile))

    def check(self, strategy: StrategyProfile) -> list[str]:
        """Rules the strategy's DECLARED shape would violate. Empty means shown compliant.

        Static and conservative. It reads only what the strategy declared, and an undeclared
        field a rule depends on is reported as a violation ("cannot be shown compliant"),
        because the alternative - treating silence as compliance - is how a strategy that
        opens risk at 08:30 gets certified clear of an 08:28-08:33 blackout it never mentioned.

        The runtime gate (`risk_engine`) still applies to every order; this exists so a
        strategy that can never fit is refused BEFORE an evaluation is purchased.
        """
        out: list[str] = []
        seen: set[str] = set()
        for p in self.stages():
            for v in _check_one(p, strategy):
                if v not in seen:
                    seen.add(v)
                    out.append(v)
        return out


def _check_one(p: PropFirmProfile, s: StrategyProfile) -> list[str]:
    out: list[str] = []
    who = p.name

    # --- session shape --------------------------------------------------------------------
    if s.holds_overnight and not p.allow_overnight:
        out.append(f"{who}: strategy holds overnight; the rulebook requires flat by the close")
    if s.holds_weekend and not p.allow_weekend:
        out.append(f"{who}: strategy holds over the weekend; the rulebook requires flat into it")
    deadline_binds = (not p.allow_overnight) or (not p.allow_weekend)
    if deadline_binds and not s.holds_overnight:
        # The EFFECTIVE deadline, not the offset: a firm may also state a wall clock (Topstep
        # flattens at 3:10 PM CT, 50 minutes before a 16:00 CT close) and then the earlier of
        # the two binds. Reading `flat_before_close_minutes` alone here would certify a
        # strategy as compliant against 15:45 CT while `PropFirmRiskEngine.must_be_flat`
        # refuses it at 15:10 - two layers applying two different tests, with the looser one
        # winning on the surface that exists to refuse a strategy BEFORE an account is bought.
        need = p.flat_deadline_minutes()
        if s.flat_by_minutes_before_close is None:
            out.append(f"{who}: requires flat {need} min before the close; the strategy does "
                       f"not declare flat_by_minutes_before_close, so compliance cannot be shown")
        elif s.flat_by_minutes_before_close < need:
            out.append(f"{who}: requires flat {need} min before the close; the strategy is "
                       f"flat only {s.flat_by_minutes_before_close} min before")

    # --- size -----------------------------------------------------------------------------
    for sym, want in sorted(s.max_contracts_per_symbol.items()):
        cap = p.max_contracts_per_symbol.get(sym)
        if cap is not None and want > cap:
            out.append(f"{who}: {sym} peak {want} contracts exceeds the {cap}-contract cap")
    # Day one is the binding rung of any ladder: an account has no profit yet.
    cap_total = p.contracts_allowed_at(0.0)
    if cap_total is not None:
        total = s.peak_total_contracts
        # The cap is in the firm's own units. Where those are contract-equivalents (Topstep:
        # one allowance, 5 minis OR 50 micros), the strategy's raw contract count is not
        # comparable with it - 3 ES is 30 micro-equivalents, not 3 - so the declared
        # per-symbol peaks are weighted the way the risk engine weights the live book.
        if p.contract_equivalence and s.max_contracts_per_symbol:
            total = sum(p.contract_units(sym) * n
                        for sym, n in s.max_contracts_per_symbol.items())
        if total is None:
            out.append(f"{who}: caps total size at {cap_total} contracts on day one; the "
                       f"strategy declares no peak size, so compliance cannot be shown")
        elif total > cap_total:
            out.append(f"{who}: peak {total:g} total contracts exceeds the day-one cap of "
                       f"{cap_total}")
    if p.max_notional is not None:
        if s.max_notional is None:
            out.append(f"{who}: caps notional at ${p.max_notional:,.0f}; the strategy declares "
                       f"no max_notional, so compliance cannot be shown")
        elif s.max_notional > p.max_notional:
            out.append(f"{who}: peak notional ${s.max_notional:,.0f} exceeds the "
                       f"${p.max_notional:,.0f} cap")

    # --- blackouts ------------------------------------------------------------------------
    if p.blackout_windows:
        if not s.opens_risk_in:
            out.append(f"{who}: has {len(p.blackout_windows)} blackout window(s); the strategy "
                       f"does not declare when it opens risk (opens_risk_in), so compliance "
                       f"cannot be shown")
        else:
            for w in s.opens_risk_in:
                for b in p.blackout_windows:
                    if windows_overlap(w, b):
                        out.append(f"{who}: strategy opens risk in {_fmt(w)}, which overlaps "
                                   f"the {_fmt(b)} blackout")
    return out


class ProfileRules(PropFirmRules):
    """Any firm whose rulebook is a `PropFirmProfile`. Configuration, not code.

    The path for a new firm: write its profile (profiles.py has the archetypes and the rule
    about confirming every number against the live rulebook), wrap it here, attach it to
    the venue that reaches it. No strategy is touched.
    """

    def __init__(self, profile: PropFirmProfile, *, scoring: Scoring | None = None,
                 name: str | None = None):
        self._profile = profile
        self.scoring = scoring or Scoring()
        self.name = name or profile.name

    @property
    def profile(self) -> PropFirmProfile:
        return self._profile

    def objective(self) -> PropFirmObjective:
        return ProfileObjective(self._profile, scoring=self.scoring)


class TopstepRules(PropFirmRules):
    """Topstep, bound to the machine-readable rulebook and the lifecycle twin.

    The Combine profile is the gate (`profile`) because it is the stage a strategy enters
    first; `stages()` adds the Express Funded Account so `check` certifies against both - the
    two share contract caps today, and if they ever diverge the stricter one binds without
    this class changing.

    `combine_fee` has no default, following the twin: with no fee the objective's value after
    fees is None and the registry refuses to rank on it. The documented monthly prices are in
    `topstep.COMBINE_COST`; passing one is a decision about which pricing path applies, and
    the two official pages disagree on the no-activation-fee row, which is why it is not
    defaulted here either.
    """

    def __init__(self, size: int, *, combine_fee: float | None = None,
                 profit_target: float | None = None,
                 daily_loss_limit: float | None = None,
                 reading: str = ts.DEFAULT_READING,
                 consistency_route: bool = False,
                 payout_policy: tw.PayoutPolicy = tw.IMMEDIATE,
                 max_combine_attempts: int = 1,
                 scaling: tuple[tuple[float, int], ...] | None = None,
                 strict_path: bool = True,
                 allow_unverified_target: bool = False,
                 scoring: Scoring | None = None):
        self.twin = tw.TopstepTwin(
            size, profit_target=profit_target, reading=reading,
            daily_loss_limit=daily_loss_limit, consistency_route=consistency_route,
            payout_policy=payout_policy, combine_fee=combine_fee,
            max_combine_attempts=max_combine_attempts, scaling=scaling,
            strict_path=strict_path, allow_unverified_target=allow_unverified_target)
        self.size = size
        self.scoring = scoring or Scoring()
        self.name = self.twin.combine_profile.name

    @property
    def profile(self) -> PropFirmProfile:
        return self.twin.combine_profile

    def stages(self) -> Sequence[PropFirmProfile]:
        return (self.twin.combine_profile, self.twin.xfa_profile)

    def objective(self) -> PropFirmObjective:
        return TwinObjective(self.twin, scoring=self.scoring, label=self.name)

    def unresolved(self) -> Mapping[str, object]:
        return ts.unresolved()


__all__ = [
    "ObjectiveResult", "Paths", "ProfileObjective", "ProfileRules", "PropFirmObjective",
    "PropFirmRules", "Scoring", "TopstepRules", "TwinObjective", "windows_overlap",
]
