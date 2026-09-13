"""Position sizing: how many units, in dollars at risk, and WHICH rule decided.

Phase 36 (money management). Every sizer here answers the same question - "given this
instrument, this account and this signal, how many contracts?" - and every answer passes
through the same funnel before it is allowed out:

    PROP-FIRM HARD RULE  >  BROKER / VENUE HARD RULE  >  RISK GOVERNOR  >  STRATEGY RISK
                                                                          >  STRATEGY SIGNAL

The ordering is structural, not a convention. `Sizer.size()` is `@final` and is the only
public entry point; a concrete sizer implements `propose()`, which is the STRATEGY SIGNAL
level and nothing more. `size()` rounds the proposal DOWN to whole units, takes the minimum
against every limit above it, and names the binding level. There is no channel through which
a sizer can hand back a number that skipped the funnel, for the same reason `RiskEngine`
gives a model no channel to pass an override: the property has to hold by shape, because a
convention is only as strong as the next person in a hurry.

Three rules apply everywhere in this module and are worth stating once:

  * Round down. Zero is a valid answer. Nothing here floors a size to one, because a budget
    that does not cover one contract is a budget that does not cover one contract - the
    `twin.max_contracts` docstring says the same and this module is built to agree with it.
  * No false precision. A sizer that cannot compute its answer from the inputs it was given
    returns `SizeDecision.available == False` with a coded reason. It does not assume a
    stop, an equity, a volatility or a drawdown of zero; every one of those assumptions is
    optimistic, and AUD-05 is what an optimistic default looks like in production.
  * Conservative defaults. Half a percent of equity per trade, a 10% annualised volatility
    target, half Kelly capped at 2%, size gone by a 10% drawdown. Every default can be
    raised by a caller who has decided to; none of them will surprise one who has not.

Layering: this module lives in `core` and may not import from `quant_brain.markets`. The
prop-firm budget is therefore consumed through `MllAccount`, a structural protocol that
`markets.futures_cme.topstep.TopstepAccount` already satisfies, and `PropFirmSizer` mirrors
`twin.risk_budget` / `twin.max_contracts` rather than importing them. `tests/test_qb_sizing.py`
pins the two against each other on a real Topstep account so they cannot drift apart.
"""
from __future__ import annotations

import abc
import enum
import math
import statistics
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Protocol, final

import numpy as np

from quant_brain.core.instruments import AssetClass, InstrumentSpec

# ======================================================================================
# THE HIERARCHY
# ======================================================================================


class Binding(str, enum.Enum):
    """Which level of the hierarchy decided the size. Ordered; higher rank is harder law.

    `str` mixin for the same reason every other enum in this package has one: decisions are
    logged as JSON, and `binding == "venue"` must read the way a human would write it.
    """

    #: Nothing above the sizer bit; the strategy's own arithmetic set the size.
    STRATEGY_SIGNAL = "strategy_signal"
    #: The strategy's declared ceiling on itself (max contracts, max dollars per trade).
    STRATEGY_RISK = "strategy_risk"
    #: The account-level governor: the owner's per-trade and portfolio budget.
    GOVERNOR = "governor"
    #: The broker's or exchange's hard rule: contract caps, margin.
    VENUE = "venue"
    #: The prop firm's hard rule: contracts allowed, and the distance to the MLL.
    PROP_FIRM = "prop_firm"

    @property
    def rank(self) -> int:
        return _RANK[self]

    @property
    def code(self) -> str:
        """The reason-code prefix a decision carries when this level reduced the size."""
        return f"LIMIT_{self.name}"


_RANK: dict[Binding, int] = {
    Binding.STRATEGY_SIGNAL: 0,
    Binding.STRATEGY_RISK: 1,
    Binding.GOVERNOR: 2,
    Binding.VENUE: 3,
    Binding.PROP_FIRM: 4,
}


class MllAccount(Protocol):
    """What a prop-firm account must expose to be sized against.

    Structural on purpose: `core` may not import `markets`, and `TopstepAccount` already has
    exactly these two properties. Anything with a distance to liquidation and a contract
    ceiling can be sized the same way.
    """

    @property
    def distance_to_mll(self) -> float: ...

    @property
    def contracts_allowed(self) -> int | None: ...


def _check_limit(name: str, value: float | None) -> None:
    if value is None:
        return
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite, non-negative number, got {value}")


@dataclass(frozen=True)
class SizeLimits:
    """The ceilings above the strategy signal, one pair per level.

    Each level may cap contracts, dollars at risk, or both. A dollar cap needs a stop
    distance to be turned into contracts; when none is available the decision is
    UNAVAILABLE rather than the cap being skipped - a limit that silently stops applying
    is the failure mode this whole module exists to prevent.

    The prop-firm pair is for static configuration (a `PropFirmProfile.max_total_contracts`
    read once). A live account's *dynamic* ceiling and its distance to the MLL arrive
    through `SizeContext.prop_account` and are merged at the same level.
    """

    strategy_max_contracts: int | None = None
    strategy_max_risk: float | None = None
    governor_max_contracts: int | None = None
    governor_max_risk: float | None = None
    venue_max_contracts: int | None = None
    venue_max_risk: float | None = None
    prop_firm_max_contracts: int | None = None
    prop_firm_max_risk: float | None = None

    def __post_init__(self) -> None:
        for level, contracts, risk in self.levels():
            _check_limit(f"{level.value} max contracts", contracts)
            _check_limit(f"{level.value} max risk", risk)

    def levels(self) -> Iterator[tuple[Binding, int | None, float | None]]:
        """The limit pairs, lowest level first. Order matters only for reason listing."""
        yield Binding.STRATEGY_RISK, self.strategy_max_contracts, self.strategy_max_risk
        yield Binding.GOVERNOR, self.governor_max_contracts, self.governor_max_risk
        yield Binding.VENUE, self.venue_max_contracts, self.venue_max_risk
        yield Binding.PROP_FIRM, self.prop_firm_max_contracts, self.prop_firm_max_risk


# ======================================================================================
# INPUTS AND OUTPUTS
# ======================================================================================


def _positive(name: str, value: float | None) -> None:
    if value is None:
        return
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite, positive number, got {value}")


def _finite(name: str, value: float | None) -> None:
    if value is not None and not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value}")


@dataclass(frozen=True)
class SizeContext:
    """Everything a sizer may look at. Every field but the spec is optional.

    Optional does not mean defaulted: a sizer that needs a field the caller did not supply
    returns an unavailable decision naming it. Units:

        price          instrument price, for notional and volatility conversion
        stop_distance  distance from entry to the stop in PRICE units (points for futures,
                       dollars per share for equities); `risk_per_contract` derives from it
        equity         account equity in dollars; may be zero or negative (an Express
                       Funded Account opens at $0, which is why `PropFirmSizer` exists)
        volatility     per-period return volatility of the instrument as a fraction
        atr            average true range in price units
        drawdown       current drawdown from the equity peak as a positive fraction
                       (0.0 = at the peak, 0.05 = five percent under it)
        confidence     a model's confidence in [0, 1]; can only ever shrink a size
        trades         realised per-trade outcomes as R-multiples (P&L / dollars risked)
        requested      the strategy's own ask in units, for `SignalSizer`
        prop_account   a live prop-firm account, sized through `MllAccount`
    """

    spec: InstrumentSpec
    limits: SizeLimits = field(default_factory=SizeLimits)
    price: float | None = None
    stop_distance: float | None = None
    equity: float | None = None
    volatility: float | None = None
    atr: float | None = None
    drawdown: float | None = None
    confidence: float | None = None
    trades: Sequence[float] | None = None
    requested: float | None = None
    prop_account: MllAccount | None = None

    def __post_init__(self) -> None:
        _positive("price", self.price)
        _positive("stop_distance", self.stop_distance)
        _positive("volatility", self.volatility)
        _positive("atr", self.atr)
        _finite("equity", self.equity)
        _finite("drawdown", self.drawdown)
        if self.drawdown is not None and self.drawdown < 0:
            raise ValueError(
                f"drawdown is a positive fraction below the peak, got {self.drawdown}")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must lie in [0, 1], got {self.confidence}")
        _finite("requested", self.requested)
        if self.requested is not None and self.requested < 0:
            raise ValueError(f"requested is unsigned, got {self.requested}")

    @property
    def risk_per_contract(self) -> float | None:
        """Dollars lost per unit if the stop is hit. None when no stop was supplied."""
        if self.stop_distance is None:
            return None
        return self.stop_distance * self.spec.multiplier


def reason(code: str, text: str) -> str:
    """The one format every reason string uses: `CODE: explanation`."""
    return f"{code}: {text}"


@dataclass(frozen=True)
class Proposal:
    """What a sizer's own arithmetic says, BEFORE the hierarchy. Never leaves this module.

    `contracts` is unrounded; `size()` rounds it down. `risk_per_contract` is set by a sizer
    that chose its own stop (the ATR sizer) and otherwise comes from the context.
    """

    contracts: float
    available: bool = True
    reasons: tuple[str, ...] = ()
    risk_per_contract: float | None = None

    @classmethod
    def of(cls, contracts: float, *reasons: str,
           risk_per_contract: float | None = None) -> Proposal:
        return cls(contracts, True, tuple(reasons), risk_per_contract)

    @classmethod
    def unavailable(cls, code: str, text: str) -> Proposal:
        return cls(0.0, False, (reason(code, text),))


@dataclass(frozen=True)
class SizeDecision:
    """The verdict: units, dollars at risk, the level that bound, and why.

    `available` False means the sizer could not answer from the inputs it was given; the
    reasons say which input was missing. `contracts` is then 0 and `binding` None, so a
    caller that ignores `available` still cannot trade on an unavailable decision.

    `signal` is the sizer's own answer before the hierarchy, so a log can show the gap
    between what the strategy wanted and what it was allowed - the difference between "this
    strategy fails" and "this strategy needs a bigger account".
    """

    sizer: str
    available: bool
    contracts: int
    risk_dollars: float | None
    binding: Binding | None
    reasons: tuple[str, ...] = ()
    signal: int | None = None

    @property
    def codes(self) -> tuple[str, ...]:
        """The leading code of every reason, for tests and dashboards."""
        return tuple(r.split(":", 1)[0] for r in self.reasons)

    def describe(self) -> str:
        if not self.available:
            return f"{self.sizer}: UNAVAILABLE - {'; '.join(self.reasons)}"
        risk = (f"${self.risk_dollars:,.0f} at risk" if self.risk_dollars is not None
                else "risk unknown")
        bound = self.binding.value if self.binding is not None else "?"
        return (f"{self.sizer}: {self.contracts} ({risk}) bound by {bound}"
                + (f" [{'; '.join(self.reasons)}]" if self.reasons else ""))


# ======================================================================================
# THE FUNNEL
# ======================================================================================


def lot_size(spec: InstrumentSpec) -> int | None:
    """The smallest tradeable unit for this spec, or None when it is not known.

    Futures and options are indivisible contracts. Equities and ETFs are sized in whole
    shares here because the runners trade whole shares and IBKR's fractional-share support
    is opt-in and venue-specific; a fractional lot would be a spec attribute added
    deliberately, not a sizing default. Crypto has no branch and no documented lot, so it
    returns None and every sizer refuses it rather than guessing.
    """
    if spec.asset_class in (AssetClass.FUTURE, AssetClass.OPTION,
                            AssetClass.EQUITY, AssetClass.ETF):
        return 1
    return None


def _unavailable(name: str, proposal_reasons: tuple[str, ...], code: str,
                 text: str) -> SizeDecision:
    return SizeDecision(name, False, 0, None, None,
                        (*proposal_reasons, reason(code, text)))


def enforce(name: str, ctx: SizeContext, proposal: Proposal) -> SizeDecision:
    """Push one proposal through the hierarchy. The only way a `SizeDecision` is made.

    The rule is `min` over every level, then credit the HIGHEST level whose cap equals the
    result. Crediting upward on a tie is deliberate: if the strategy asked for 5 and the
    venue allows 5, "you are at the venue cap" is the useful thing to know.
    """
    if not proposal.available:
        return SizeDecision(name, False, 0, None, None, proposal.reasons)
    if not math.isfinite(proposal.contracts):
        return _unavailable(name, proposal.reasons, "SIZING_NON_FINITE",
                            f"sizer produced {proposal.contracts}")

    lot = lot_size(ctx.spec)
    if lot is None:
        return _unavailable(name, proposal.reasons, "SIZING_UNSUPPORTED_ASSET_CLASS",
                            f"{ctx.spec.symbol} is {ctx.spec.asset_class.value}; no lot size "
                            f"is defined, so whole-unit rounding cannot be applied")
    # Round DOWN, and never below zero. `lot` is 1 for everything sized today, but the
    # arithmetic is written for the general case so a fractional lot does not need a rewrite.
    signal = max(0, int(math.floor(proposal.contracts / lot)) * lot)

    rpc = (proposal.risk_per_contract if proposal.risk_per_contract is not None
           else ctx.risk_per_contract)
    reasons = list(proposal.reasons)
    caps: list[tuple[Binding, int, str]] = []

    for level, max_contracts, max_risk in ctx.limits.levels():
        if max_contracts is not None:
            caps.append((level, int(max_contracts), f"{level.value} allows {max_contracts}"))
        if max_risk is not None:
            if rpc is None:
                return _unavailable(
                    name, tuple(reasons), "SIZING_NO_STOP",
                    f"{level.value} caps risk at ${max_risk:,.0f} but no stop distance was "
                    f"supplied, so the cap cannot be converted to contracts")
            caps.append((level, int(max_risk // rpc),
                         f"{level.value} caps risk at ${max_risk:,.0f} "
                         f"(${rpc:,.2f} per contract)"))

    account = ctx.prop_account
    if account is not None:
        allowed = account.contracts_allowed
        if allowed is not None:
            caps.append((Binding.PROP_FIRM, int(allowed),
                         f"prop firm allows {allowed} contracts at this balance"))
        room = account.distance_to_mll
        if rpc is None:
            return _unavailable(
                name, tuple(reasons), "SIZING_NO_STOP",
                f"prop-firm distance to MLL is ${room:,.0f} but no stop distance was "
                f"supplied, so the position's loss cannot be bounded against it")
        # The FULL distance, not a fraction of it, is the hard rule: a position that can
        # lose more than the room to the MLL liquidates the account on a single stop-out,
        # whichever sizer proposed it. The fraction is `PropFirmSizer`'s policy choice.
        caps.append((Binding.PROP_FIRM, max(0, int(room // rpc)),
                     f"prop-firm distance to MLL ${room:,.0f} (${rpc:,.2f} per contract)"))

    final = min([signal, *(c for _, c, _ in caps)])
    final = max(0, final)
    binding = Binding.STRATEGY_SIGNAL
    for level, cap, why in caps:
        if cap < signal:
            reasons.append(reason(level.code, f"{why}; signal asked {signal}"))
        if cap <= final and level.rank > binding.rank:
            binding = level

    risk = final * rpc if rpc is not None else None
    if risk is None and final > 0:
        reasons.append(reason("SIZING_RISK_UNKNOWN",
                              "no stop distance supplied; dollars at risk not computed"))
    return SizeDecision(name, True, final, risk, binding, tuple(reasons), signal)


class Sizer(abc.ABC):
    """One sizing rule. Implement `propose`; never touch `size`.

    `size` is final so that the hierarchy in `enforce` cannot be bypassed by a subclass
    that thinks its case is special. Composite sizers (drawdown-aware, confidence-weighted)
    wrap another sizer's `propose`, so the funnel still runs exactly once, at the end.
    """

    name: str = "sizer"

    @abc.abstractmethod
    def propose(self, ctx: SizeContext) -> Proposal:
        """The STRATEGY SIGNAL level: this rule's own arithmetic, unrounded, unclamped."""

    @final
    def size(self, ctx: SizeContext) -> SizeDecision:
        return enforce(self.name, ctx, self.propose(ctx))

    def __call__(self, ctx: SizeContext) -> SizeDecision:
        return self.size(ctx)


# ======================================================================================
# THE SIZERS
# ======================================================================================


class SignalSizer(Sizer):
    """The strategy already has a number. Pass it through the hierarchy unchanged.

    For strategies with their own sizing logic, and for the test that proves a strategy
    asking for 50 on a 5-contract venue gets 5.
    """

    name = "signal"

    def propose(self, ctx: SizeContext) -> Proposal:
        if ctx.requested is None:
            return Proposal.unavailable("SIZING_NO_REQUEST", "no requested size in context")
        return Proposal.of(ctx.requested)


def _budget_from_equity(ctx: SizeContext, fraction: float, dollars: float | None,
                        what: str) -> tuple[float, Proposal | None]:
    """A dollar budget from a fixed amount or a fraction of equity. Shared by two sizers."""
    if dollars is not None:
        return dollars, None
    if ctx.equity is None:
        return 0.0, Proposal.unavailable(
            "SIZING_NO_EQUITY", f"{what} is a fraction of equity and no equity was supplied")
    # Equity at or below zero is a real state (an XFA opens at $0), not an error. It means
    # a fraction-of-equity budget is zero, which is the honest answer from this sizer and
    # the reason `PropFirmSizer` sizes off distance-to-MLL instead.
    return max(0.0, ctx.equity) * fraction, None


class FixedRiskSizer(Sizer):
    """Risk a fixed amount per trade - dollars, or a fraction of equity - against the stop.

    contracts = budget / (stop_distance x multiplier), rounded down.

    Default 0.5% of equity. The folk rule is 1%; halving it is the price of the observation
    that a stop is a hope, not a guarantee - gaps, slippage on the exit and a wide spread at
    the wrong moment all fill worse than the stop price, so realised risk per trade runs
    above the planned figure, and a default should leave room for that.
    """

    name = "fixed_risk"

    def __init__(self, *, risk_fraction: float = 0.005, risk_dollars: float | None = None):
        if not (0.0 < risk_fraction <= 1.0):
            raise ValueError(f"risk_fraction must lie in (0, 1], got {risk_fraction}")
        _check_limit("risk_dollars", risk_dollars)
        self.risk_fraction = risk_fraction
        self.risk_dollars = risk_dollars

    def propose(self, ctx: SizeContext) -> Proposal:
        rpc = ctx.risk_per_contract
        if rpc is None:
            return Proposal.unavailable("SIZING_NO_STOP",
                                        "fixed-risk sizing needs a stop distance")
        budget, refusal = _budget_from_equity(ctx, self.risk_fraction, self.risk_dollars,
                                              "fixed risk")
        if refusal is not None:
            return refusal
        return Proposal.of(budget / rpc,
                           reason("FIXED_RISK",
                                  f"budget ${budget:,.2f} at ${rpc:,.2f} per contract"))


class VolatilityTargetSizer(Sizer):
    """Size so the position's expected volatility is a set fraction of equity.

    contracts = (target_vol / sqrt(periods_per_year) x equity)
                / (volatility x price x multiplier)

    Default 10% annualised. Trend-following shops run 20-40% at the portfolio level, but
    that is across dozens of markets whose volatilities partly cancel; a single position at
    a 20% target on a prop-firm account with a 4% trailing limit is a coin flip on the
    account, not a position. Ten percent for one instrument is conservative on purpose.

    Dollars at risk are reported only if a stop was also supplied. Volatility is not a
    stop, and the decision does not pretend it is.
    """

    name = "vol_target"

    def __init__(self, *, target_vol: float = 0.10, periods_per_year: int = 252):
        if not (0.0 < target_vol <= 1.0):
            raise ValueError(f"target_vol must lie in (0, 1], got {target_vol}")
        if periods_per_year <= 0:
            raise ValueError(f"periods_per_year must be positive, got {periods_per_year}")
        self.target_vol = target_vol
        self.periods_per_year = periods_per_year

    def propose(self, ctx: SizeContext) -> Proposal:
        if ctx.equity is None:
            return Proposal.unavailable("SIZING_NO_EQUITY", "volatility targeting needs equity")
        if ctx.price is None:
            return Proposal.unavailable("SIZING_NO_PRICE", "volatility targeting needs a price")
        if ctx.volatility is None:
            return Proposal.unavailable(
                "SIZING_NO_VOLATILITY", "volatility targeting needs the instrument's volatility")
        per_contract = ctx.volatility * ctx.price * ctx.spec.multiplier
        target = self.target_vol / math.sqrt(self.periods_per_year) * max(0.0, ctx.equity)
        return Proposal.of(target / per_contract,
                           reason("VOL_TARGET", f"target ${target:,.2f} per period against "
                                                f"${per_contract:,.2f} per contract"))


class ATRSizer(Sizer):
    """Fixed fractional risk with the stop set at a multiple of the ATR.

    contracts = (risk_fraction x equity) / (atr_multiple x ATR x multiplier)

    The stop is this sizer's own, so the decision's dollars at risk are computed from it
    even if the context carried a different stop. Defaults: 0.5% of equity, 2 x ATR - the
    same half-a-percent as `FixedRiskSizer`, for the same reason.
    """

    name = "atr"

    def __init__(self, *, risk_fraction: float = 0.005, atr_multiple: float = 2.0):
        if not (0.0 < risk_fraction <= 1.0):
            raise ValueError(f"risk_fraction must lie in (0, 1], got {risk_fraction}")
        if not (atr_multiple > 0 and math.isfinite(atr_multiple)):
            raise ValueError(f"atr_multiple must be positive, got {atr_multiple}")
        self.risk_fraction = risk_fraction
        self.atr_multiple = atr_multiple

    def propose(self, ctx: SizeContext) -> Proposal:
        if ctx.atr is None:
            return Proposal.unavailable("SIZING_NO_ATR", "ATR sizing needs the ATR")
        if ctx.equity is None:
            return Proposal.unavailable("SIZING_NO_EQUITY", "ATR sizing needs equity")
        rpc = self.atr_multiple * ctx.atr * ctx.spec.multiplier
        budget = max(0.0, ctx.equity) * self.risk_fraction
        return Proposal.of(
            budget / rpc,
            reason("ATR_STOP", f"stop {self.atr_multiple:g} x ATR {ctx.atr:g} = "
                               f"${rpc:,.2f} per contract; budget ${budget:,.2f}"),
            risk_per_contract=rpc)


# --- Kelly -----------------------------------------------------------------------------


def kelly_binary(win_rate: float, payoff: float) -> float:
    """Classic Kelly for a bet that wins `payoff` R with probability p and loses 1 R.

    f* = p - (1 - p) / b. Negative means do not bet. Exposed for the known-answer test and
    for callers whose outcomes genuinely are binary; `KellySizer` uses the moment form
    because real trade outcomes are not.
    """
    if not (0.0 <= win_rate <= 1.0):
        raise ValueError(f"win_rate must lie in [0, 1], got {win_rate}")
    if payoff <= 0:
        raise ValueError(f"payoff must be positive, got {payoff}")
    return win_rate - (1.0 - win_rate) / payoff


def kelly_fraction(mean: float, variance: float) -> float:
    """Kelly for continuous outcomes: f* = mean / variance of the per-R-multiple return.

    The second-order (log-utility, small-edge) approximation. It is exact for Gaussian
    outcomes and OPTIMISTIC for fat left tails, because the expansion truncates the terms
    that a large loss contributes - one more reason the sizer never bets the full figure.
    """
    if variance <= 0 or not math.isfinite(variance):
        raise ValueError(f"variance must be positive and finite, got {variance}")
    return mean / variance


@dataclass(frozen=True)
class KellyEstimate:
    """The edge estimate and its admissibility. `full` is None whenever `code` is set."""

    n: int
    mean: float
    variance: float
    se: float
    lower: float
    confidence: float
    full: float | None
    code: str = ""
    detail: str = ""

    @property
    def admissible(self) -> bool:
        return self.full is not None


def estimate_kelly(trades: Sequence[float], *, min_trades: int = 30,
                   confidence: float = 0.99) -> KellyEstimate:
    """Estimate f* from realised R-multiples, or refuse.

    Refuses when:
      * fewer than `min_trades` outcomes         KELLY_TOO_FEW_TRADES
      * any outcome is not finite                KELLY_NON_FINITE
      * the outcomes have no variance            KELLY_DEGENERATE
      * the mean edge is not positive            KELLY_NEGATIVE_EDGE
      * the confidence interval on the mean
        reaches zero                             KELLY_EDGE_NOT_SIGNIFICANT

    The interval is a plain iid normal interval on the mean at `confidence` (two-sided,
    default 99%). That is a FILTER, not a proof: one zero-edge sample in two hundred will
    pass it by construction, and trades that overlap in time understate the standard error
    further. Both are reasons the sizer also caps and fractions what passes.
    """
    if min_trades < 2:
        raise ValueError(f"min_trades must be at least 2, got {min_trades}")
    if not (0.0 < confidence < 1.0):
        raise ValueError(f"confidence must lie in (0, 1), got {confidence}")
    x = np.asarray(list(trades), dtype=float)
    n = int(x.size)
    nan = float("nan")
    if n and not np.all(np.isfinite(x)):
        return KellyEstimate(n, nan, nan, nan, nan, confidence, None, "KELLY_NON_FINITE",
                             "trade outcomes contain NaN or inf")
    if n < min_trades:
        return KellyEstimate(n, nan, nan, nan, nan, confidence, None, "KELLY_TOO_FEW_TRADES",
                             f"{n} trades, {min_trades} required")
    mean = float(x.mean())
    variance = float(x.var(ddof=1))
    if variance <= 0:
        return KellyEstimate(n, mean, variance, 0.0, mean, confidence, None,
                             "KELLY_DEGENERATE",
                             "all outcomes identical; no variance to size against")
    se = math.sqrt(variance / n)
    z = statistics.NormalDist().inv_cdf(0.5 + confidence / 2.0)
    lower = mean - z * se
    if mean <= 0:
        return KellyEstimate(n, mean, variance, se, lower, confidence, None,
                             "KELLY_NEGATIVE_EDGE", f"mean R {mean:+.4f} is not positive")
    if lower <= 0:
        return KellyEstimate(n, mean, variance, se, lower, confidence, None,
                             "KELLY_EDGE_NOT_SIGNIFICANT",
                             f"mean R {mean:+.4f} +/- {z * se:.4f} at {confidence:.0%} "
                             f"reaches zero over {n} trades")
    return KellyEstimate(n, mean, variance, se, lower, confidence,
                         kelly_fraction(mean, variance))


class KellySizer(Sizer):
    """Fractional Kelly on a realised trade sample, capped, or an explicit refusal.

    Applied as a fraction of EQUITY at risk per trade: f* is estimated on R-multiples, so
    "risk f x equity" is the bet the estimate refers to. contracts = f x equity / rpc.

    WHY HALF (OR QUARTER) KELLY IS THE DEFAULT AND FULL KELLY IS NOT
    ----------------------------------------------------------------
    Full Kelly maximises expected log growth ONLY when the edge is known exactly. It is
    estimated, and the growth curve is asymmetric around the optimum: betting half of f*
    keeps three quarters of the growth rate at half the variance and roughly half the
    drawdown depth; betting twice f* yields ZERO growth, and anything beyond that loses money
    with a positive edge. The standard error on a mean R of 0.2 over 200 trades is about
    0.07 - the same order as the edge - so the true f* is easily half or double the estimate,
    and the penalty for overshooting is far larger than the penalty for undershooting.
    Half Kelly is the sane default; quarter Kelly is the sane default for a strategy whose
    sample is short, overlapping or from a different regime. Full Kelly is permitted here
    only by asking for it explicitly, and the decision flags it when you do.

    A prop-firm account makes the argument stronger, not weaker: drawdown there is not a
    variance cost, it is absorbing. Which is why this sizer sits under `PROP_FIRM` in the
    hierarchy and why `max_risk_fraction` caps it at 2% of equity by default whatever f* says.
    """

    name = "kelly"

    def __init__(self, *, fraction: float = 0.5, min_trades: int = 30,
                 confidence: float = 0.99, max_risk_fraction: float = 0.02):
        if not (0.0 < fraction <= 1.0):
            raise ValueError(f"fraction must lie in (0, 1], got {fraction}")
        if not (0.0 < max_risk_fraction <= 1.0):
            raise ValueError(f"max_risk_fraction must lie in (0, 1], got {max_risk_fraction}")
        self.fraction = fraction
        self.min_trades = min_trades
        self.confidence = confidence
        self.max_risk_fraction = max_risk_fraction

    def propose(self, ctx: SizeContext) -> Proposal:
        rpc = ctx.risk_per_contract
        if rpc is None:
            return Proposal.unavailable("SIZING_NO_STOP", "Kelly sizing needs a stop distance")
        if ctx.equity is None:
            return Proposal.unavailable("SIZING_NO_EQUITY", "Kelly sizing needs equity")
        if ctx.trades is None:
            return Proposal.unavailable("KELLY_NO_TRADES", "no trade sample in context")
        est = estimate_kelly(ctx.trades, min_trades=self.min_trades, confidence=self.confidence)
        if est.full is None:
            return Proposal.unavailable(est.code, est.detail)
        reasons = [reason("KELLY", f"f* {est.full:.4f} from {est.n} trades "
                                   f"(mean R {est.mean:+.4f}, CI lower {est.lower:+.4f}); "
                                   f"applying {self.fraction:g} x")]
        if self.fraction > 0.5:
            reasons.append(reason("KELLY_FRACTION_ABOVE_HALF",
                                  f"{self.fraction:g} x Kelly; see KellySizer for why not"))
        f = self.fraction * est.full
        if f > self.max_risk_fraction:
            reasons.append(reason("KELLY_CAPPED",
                                  f"{f:.4f} of equity capped at {self.max_risk_fraction:g}"))
            f = self.max_risk_fraction
        budget = max(0.0, ctx.equity) * f
        return Proposal.of(budget / rpc, *reasons)


# --- Modifiers: shrink another sizer's answer, never grow it -----------------------------


class DrawdownAwareSizer(Sizer):
    """Scale a base sizer down as the drawdown deepens. Monotone, never above 1x.

    factor = 1 at drawdown <= `start`, falling linearly to `floor` at `stop`, and `floor`
    beyond. Defaults: shrinking begins immediately and size is gone at a 10% drawdown.
    Ten percent is far past the point at which the strategy's premise should have been
    re-examined; a caller running a firm account with a 4% trailing limit should set `stop`
    well inside it, and `PropFirmSizer` is the sizer that knows that limit.

    Missing drawdown is a refusal, not zero: "no drawdown supplied" and "at the peak" are
    different facts, and only one of them is safe to assume.
    """

    name = "drawdown_aware"

    def __init__(self, base: Sizer, *, start: float = 0.0, stop: float = 0.10,
                 floor: float = 0.0):
        if not (0.0 <= start < stop) or not math.isfinite(stop):
            raise ValueError(f"need 0 <= start < stop, got start={start} stop={stop}")
        if not (0.0 <= floor <= 1.0):
            raise ValueError(f"floor must lie in [0, 1], got {floor}")
        self.base = base
        self.start = start
        self.stop = stop
        self.floor = floor
        self.name = f"drawdown_aware({base.name})"

    def factor(self, drawdown: float) -> float:
        if drawdown <= self.start:
            return 1.0
        if drawdown >= self.stop:
            return self.floor
        return 1.0 - (1.0 - self.floor) * (drawdown - self.start) / (self.stop - self.start)

    def propose(self, ctx: SizeContext) -> Proposal:
        if ctx.drawdown is None:
            return Proposal.unavailable("SIZING_NO_DRAWDOWN",
                                        "drawdown-aware sizing needs the current drawdown")
        base = self.base.propose(ctx)
        if not base.available:
            return base
        k = self.factor(ctx.drawdown)
        return Proposal.of(base.contracts * k, *base.reasons,
                           reason("DRAWDOWN_SCALED",
                                  f"{k:.3f} x at {ctx.drawdown:.2%} drawdown"),
                           risk_per_contract=base.risk_per_contract)


class ConfidenceWeightedSizer(Sizer):
    """Scale a base sizer by a model's confidence. The model can only make the size smaller.

    factor = 0 at or below `min_confidence`, rising as ((c - min) / (1 - min)) ** power to
    1 at confidence 1. With the default `min_confidence` of 0.5 a calibrated 55% classifier
    sizes at a tenth of the base - which is what a 5-point edge over a coin flip deserves
    until it has been shown to be calibrated. Confidence above 1 is rejected at context
    construction, so no model output can ever multiply a size by more than one; that is the
    `RiskEngine` principle - the model proposes, it does not override - applied to sizing.
    """

    name = "confidence_weighted"

    def __init__(self, base: Sizer, *, min_confidence: float = 0.5, power: float = 1.0):
        if not (0.0 <= min_confidence < 1.0):
            raise ValueError(f"min_confidence must lie in [0, 1), got {min_confidence}")
        if power <= 0:
            raise ValueError(f"power must be positive, got {power}")
        self.base = base
        self.min_confidence = min_confidence
        self.power = power
        self.name = f"confidence_weighted({base.name})"

    def factor(self, confidence: float) -> float:
        if confidence <= self.min_confidence:
            return 0.0
        return min(1.0, ((confidence - self.min_confidence)
                         / (1.0 - self.min_confidence)) ** self.power)

    def propose(self, ctx: SizeContext) -> Proposal:
        if ctx.confidence is None:
            return Proposal.unavailable("SIZING_NO_CONFIDENCE",
                                        "confidence-weighted sizing needs a confidence")
        base = self.base.propose(ctx)
        if not base.available:
            return base
        k = self.factor(ctx.confidence)
        return Proposal.of(base.contracts * k, *base.reasons,
                           reason("CONFIDENCE_SCALED",
                                  f"{k:.3f} x at confidence {ctx.confidence:.2f}"),
                           risk_per_contract=base.risk_per_contract)


# --- Prop firm ---------------------------------------------------------------------------


class PropFirmSizer(Sizer):
    """Size off the distance to the MLL, the way `twin.risk_budget` does.

    budget = distance_to_mll x fraction; contracts = budget / rpc, rounded down.

    Anchored to the room above the floor rather than to equity, because equity is not what
    kills the account: a Combine at $53,000 with the MLL at $50,000 has $3,000 of room, and
    an Express Funded Account at a $500 balance with the MLL at -$1,500 has $2,000. Sizing
    the first off equity puts on eighteen times what it can survive; sizing the second off
    equity leaves a survivable account trading too small to pay its own fee.

    A quarter of the room per trade is the twin's default and is kept here. It means four
    consecutive full stop-outs end the account, which is already a thin margin against the
    kind of week every strategy eventually has; a larger fraction is a choice to be made
    with the twin's liquidation probability in front of you. There is no `floor` parameter
    on purpose: a floor on a risk budget is a rule that the account must trade even when it
    cannot afford to, and that is the one rule this sizer exists to refuse.

    The account's contract ceiling and its FULL distance to the MLL are enforced by
    `enforce` for every sizer, not just this one; this sizer only decides the fraction.
    """

    name = "prop_firm"

    def __init__(self, *, fraction: float = 0.25):
        # The same domain check as `twin.risk_budget`, so the two cannot disagree on what a
        # legal fraction is.
        if fraction <= 0 or fraction > 1:
            raise ValueError(f"fraction must be in (0, 1], got {fraction}")
        self.fraction = fraction

    def propose(self, ctx: SizeContext) -> Proposal:
        if ctx.prop_account is None:
            return Proposal.unavailable("SIZING_NO_PROP_ACCOUNT",
                                        "prop-firm sizing needs the account in context")
        rpc = ctx.risk_per_contract
        if rpc is None:
            return Proposal.unavailable("SIZING_NO_STOP",
                                        "prop-firm sizing needs a stop distance")
        room = ctx.prop_account.distance_to_mll
        if not math.isfinite(room):
            return Proposal.unavailable("SIZING_NON_FINITE", f"distance to MLL is {room}")
        budget = max(0.0, room) * self.fraction
        return Proposal.of(budget / rpc,
                           reason("PROP_FIRM_BUDGET",
                                  f"{self.fraction:g} x ${room:,.0f} to the MLL = "
                                  f"${budget:,.2f} at ${rpc:,.2f} per contract"))
