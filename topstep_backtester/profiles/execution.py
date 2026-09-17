"""The execution ladder: what we assume about fills, stated as a ladder rather than a number.

WHY A LADDER AND NOT A SETTING
------------------------------
Slippage is not measured, it is assumed, and every result is a function of the assumption.
A single "realistic" setting hides that dependence; running the same frozen strategy at four
rungs exposes it. The question a reader should be able to answer from the report is not "is
this profitable" but "how much worse would execution have to be before it is not", and that
question has no answer unless the ladder was run.

The rungs are fixed and are NOT a search space. Picking the rung that makes a strategy look
best, after seeing the results, is curve fitting with extra steps. BASELINE is the rung a
result is quoted at; the others are context that must be published alongside it.

    IDEAL          0 / 0    a lower bound that cannot be achieved. Its only job is to show
                            how much of the edge is consumed by execution.
    BASELINE       1 / 0    one tick against on a stop, none on a market order. The rung
                            results are quoted at.
    STRESS_1TICK   2 / 1
    STRESS_2TICK   3 / 2    if the conclusion survives here it is not an execution artefact.

WHAT "fill_limit_on_touch" MEANS AND WHY IT STAYS FALSE
-------------------------------------------------------
Upstream defaults it to False: a resting limit needs the market to trade THROUGH the price,
not merely touch it. That is the conservative reading - at a touch you are at the back of
the queue and may not be filled - and it makes profit targets strictly harder to reach. It
stays False on every rung. A True setting would improve every backtest in this pipeline and
justify none of them.

FEES ARE A DIVERGENCE, NOT A DEFAULT
------------------------------------
Three different ES round-turn costs exist in reach of this pipeline: upstream's built-in
$3.80, this repository's instrument table at $3.78, and the $4.14 an earlier frozen spec
used. They are close, and that is exactly why the difference gets waved through; on a
strategy taking two trades a day for twenty days it is a $14 spread, which is small against
$3,000 but not against a marginal result. Each profile therefore names its fee source
explicitly and records it in the manifest. See UPSTREAM_FINDINGS.md FINDING 3.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from topstep_backtester.upstream import BarFillConfig, FeeSchedule, SimBrokerConfig, TopstepFees

EXECUTION_SCHEMA_VERSION = "1.0.0"

#: Where a profile's costs come from. A string in the manifest, so a reader never has to
#: guess which of the three figures a number was computed with.
FEE_SOURCE_UPSTREAM_DEFAULT = "upstream topstep_backtest.fills.fees.TopstepFees defaults"


@dataclass(frozen=True)
class ExecutionProfile:
    """One rung. Moves fills and costs only - never a strategy rule."""

    profile_id: str
    description: str
    stop_slippage_ticks: int
    market_slippage_ticks: int
    fill_limit_on_touch: bool
    forced_liq_slippage_ticks: int
    fee_source: str
    #: ``None`` uses upstream's built-in schedules. A mapping here is an explicit override
    #: and must be justified in ``fee_source``.
    fee_overrides: tuple[tuple[str, Decimal, Decimal, Decimal], ...] = ()

    def bar_fill_config(self) -> BarFillConfig:
        return BarFillConfig(
            stop_slippage_ticks=self.stop_slippage_ticks,
            market_slippage_ticks=self.market_slippage_ticks,
            fill_limit_on_touch=self.fill_limit_on_touch,
        )

    def broker_config(self) -> SimBrokerConfig:
        return SimBrokerConfig(forced_liq_slippage_ticks=self.forced_liq_slippage_ticks)

    def fee_model(self) -> TopstepFees:
        if not self.fee_overrides:
            return TopstepFees()
        return TopstepFees(
            {
                symbol: FeeSchedule(
                    commission_per_side=commission,
                    exchange_per_side=exchange,
                    nfa_per_side=nfa,
                )
                for symbol, commission, exchange, nfa in self.fee_overrides
            }
        )

    def round_turn_cost(self, symbol: str) -> Decimal:
        """Total cost of one contract in and out, from THIS profile's fee model."""
        schedule = self.fee_model().schedule_for(symbol)
        per_side = (
            schedule.commission_per_side + schedule.exchange_per_side + schedule.nfa_per_side
        )
        return per_side * 2

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "schema_version": EXECUTION_SCHEMA_VERSION,
            "description": self.description,
            "stop_slippage_ticks": self.stop_slippage_ticks,
            "market_slippage_ticks": self.market_slippage_ticks,
            "fill_limit_on_touch": self.fill_limit_on_touch,
            "forced_liq_slippage_ticks": self.forced_liq_slippage_ticks,
            "fee_source": self.fee_source,
            "fee_overrides": [
                {"symbol": s, "commission_per_side": str(c),
                 "exchange_per_side": str(e), "nfa_per_side": str(n)}
                for s, c, e, n in self.fee_overrides
            ],
        }


IDEAL = ExecutionProfile(
    profile_id="IDEAL/v1",
    description="No slippage anywhere. Not achievable; quoted only as an upper bound.",
    stop_slippage_ticks=0,
    market_slippage_ticks=0,
    fill_limit_on_touch=False,
    forced_liq_slippage_ticks=0,
    fee_source=FEE_SOURCE_UPSTREAM_DEFAULT,
)

BASELINE = ExecutionProfile(
    profile_id="BASELINE/v1",
    description=(
        "One tick against on stop fills, none on market orders, two on a forced "
        "liquidation. The rung results are quoted at."
    ),
    stop_slippage_ticks=1,
    market_slippage_ticks=0,
    fill_limit_on_touch=False,
    forced_liq_slippage_ticks=2,
    fee_source=FEE_SOURCE_UPSTREAM_DEFAULT,
)

STRESS_1TICK = ExecutionProfile(
    profile_id="STRESS_1TICK/v1",
    description="Two ticks against on stops, one on market orders.",
    stop_slippage_ticks=2,
    market_slippage_ticks=1,
    fill_limit_on_touch=False,
    forced_liq_slippage_ticks=3,
    fee_source=FEE_SOURCE_UPSTREAM_DEFAULT,
)

STRESS_2TICK = ExecutionProfile(
    profile_id="STRESS_2TICK/v1",
    description="Three ticks against on stops, two on market orders.",
    stop_slippage_ticks=3,
    market_slippage_ticks=2,
    fill_limit_on_touch=False,
    forced_liq_slippage_ticks=4,
    fee_source=FEE_SOURCE_UPSTREAM_DEFAULT,
)

#: The ladder, in the order it must be reported. Order matters: a report that lists only
#: the rung that flatters the strategy is the failure mode this tuple exists to prevent.
LADDER: tuple[ExecutionProfile, ...] = (IDEAL, BASELINE, STRESS_1TICK, STRESS_2TICK)

#: The rung a headline number is quoted at.
QUOTED_RUNG = BASELINE

PROFILES: dict[str, ExecutionProfile] = {p.profile_id: p for p in LADDER}


def get_profile(profile_id: str) -> ExecutionProfile:
    if profile_id not in PROFILES:
        raise KeyError(
            f"unknown execution profile {profile_id!r}; the ladder is {sorted(PROFILES)}. "
            f"Rungs are fixed - a new one is a change to the assumptions, not a tuning knob."
        )
    return PROFILES[profile_id]


__all__ = [
    "BASELINE",
    "EXECUTION_SCHEMA_VERSION",
    "FEE_SOURCE_UPSTREAM_DEFAULT",
    "IDEAL",
    "LADDER",
    "PROFILES",
    "QUOTED_RUNG",
    "STRESS_1TICK",
    "STRESS_2TICK",
    "ExecutionProfile",
    "get_profile",
]
