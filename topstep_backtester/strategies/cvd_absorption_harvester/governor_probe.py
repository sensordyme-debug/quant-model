"""The PART 20 governor integration test. NOT a strategy backtest.

WHAT THIS IS AND IS NOT
-----------------------
It is a plumbing test. It drives the REAL ``Governor`` class through the REAL upstream
engine on hand-built synthetic bars whose outcomes are decided in advance, and checks that
HALTED_SUCCESS and HALTED_FAIL occur exactly where the arithmetic says they must.

It is NOT evidence about CVD_ABSORPTION_HARVESTER. It contains no CVD, no swing memory and
no divergence test - it cannot, because those need tick data this repository does not have.
Its entry rule is a bar index. Any P&L it produces is a property of the fixture, not of a
hypothesis, and reporting it as strategy performance would be a fabricated result.

WHY A SEPARATE SPEC
-------------------
The real specification has ten unresolved ambiguities and therefore cannot be frozen or
run. This probe has none - its rules are whatever this file says - so it freezes cleanly.
Keeping the two apart is what stops a plumbing fixture from borrowing the strategy's
identity: the probe has its own name, its own hash, and its own genealogy node.

THE ARITHMETIC, WORKED OUT IN ADVANCE
-------------------------------------
One ES contract, $12.50 a tick, upstream's default $3.80 round turn.

    a winning trade   the target is a resting LIMIT and is charged no slippage (A13):
                      +16 ticks = +$200.00 gross, -$3.80 round turn = +$196.20 realized
                      196.20 >= 160  ->  HALTED_SUCCESS after ONE win

    a losing trade    the stop pays the declared 1 tick of slippage, so it is NINE ticks
                      and not eight - the single easiest figure to get wrong here:
                      -(8+1) ticks = -$112.50 gross, -$3.80 = -$116.30 realized
                      one loss is -116.30, two are -232.60, neither trips -250
                      a third entry half a point under water adds -$25.00 unrealized
                      -232.60 + -25.00 = -$257.60 <= -250  ->  HALTED_FAIL

That last line is the one worth having: it is the only path in this fixture that reaches the
killswitch, and it reaches it on REALIZED PLUS UNREALIZED rather than on realized alone -
which is the distinction PART 18 turns on and the one a careless governor gets wrong.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from topstep_backtester.strategies.base import ResearchStrategy
from topstep_backtester.strategies.cvd_absorption_harvester import spec as S
from topstep_backtester.strategies.cvd_absorption_harvester.governor import Governor, State
from topstep_backtester.strategies.spec import FrozenStrategySpec
from topstep_backtester.upstream import AggregateBarUnit, Bar, BarType

#: Bars per synthetic session. Enough to hold three entries and their resolutions.
BARS_PER_DAY = 60

#: The bar indices the probe enters on. Fixed, unconditional, no hypothesis.
ENTRY_BARS = (5, 25, 45)

#: What each expected outcome implies, restated so the assertions are independent of the
#: engine. Upstream default ES round turn.
ROUND_TURN = Decimal("3.80")
#: The target is a limit and pays no slippage; the stop pays the declared one tick, so a
#: stop-out is NINE ticks wide, not eight.
WIN_REALIZED = S.TICK_VALUE * S.TARGET_TICKS - ROUND_TURN                       # +196.20
LOSS_REALIZED = -S.TICK_VALUE * (S.STOP_TICKS + S.STOP_SLIPPAGE_TICKS) - ROUND_TURN  # -116.30


PROBE_SPEC = FrozenStrategySpec(
    name="cvd_governor_plumbing_probe",
    version="1.0.0",
    instrument=S.INSTRUMENT,
    bar_interval="1min",
    session_window="09:30-16:00 ET",
    entry_rules=(
        f"buy or sell 1 ES unconditionally at the close of bar indices {list(ENTRY_BARS)} of "
        f"each synthetic session, subject only to the governor gate",
    ),
    exit_rules=(
        f"OCO bracket: stop {S.STOP_TICKS} ticks, target {S.TARGET_TICKS} ticks, from the "
        f"actual fill",
    ),
    risk_rules=(
        f"the REAL Governor: winning-day lock at +${S.WINNING_DAY_LOCK_USD} realized, "
        f"killswitch at ${S.KILLSWITCH_USD} on realized + unrealized",
    ),
    parameters={
        "entry_bars": list(ENTRY_BARS),
        "stop_ticks": S.STOP_TICKS,
        "target_ticks": S.TARGET_TICKS,
        "winning_day_lock_usd": str(S.WINNING_DAY_LOCK_USD),
        "killswitch_usd": str(S.KILLSWITCH_USD),
    },
    hypothesis=(
        "None. This is a governor plumbing test. It asserts that two thresholds fire where "
        "the arithmetic says they must, and must never be reported as strategy performance."
    ),
).freeze(author="governor-integration-test", at=dt.datetime(2026, 9, 17, tzinfo=dt.UTC))


class GovernorProbe(ResearchStrategy):
    """Enters on fixed bar indices and lets the real Governor gate and halt it."""

    def __init__(self, contract_id: str) -> None:
        super().__init__(contract_id, spec=PROBE_SPEC, require_ready=False)
        self.governor = Governor()
        self._day: dt.date | None = None
        self._index = 0
        self._entry_price: Decimal | None = None
        self._direction = 0
        #: Costs arrive PER HALF-TURN on HalfTradeModel, so the entry side must be carried
        #: forward or the governor is told a realised figure short of one side's commission.
        self._entry_costs = Decimal(0)
        self.daily_states: dict[dt.date, str] = {}
        self.equity_marks: list[tuple[str, str]] = []

    def _unrealized(self, price: Decimal) -> Decimal:
        if self._entry_price is None:
            return Decimal(0)
        return (price - self._entry_price) * self._direction * S.POINT_VALUE

    async def on_bar(self, bar: object) -> None:
        ts_ns = int(bar.ts_init)  # type: ignore[attr-defined]
        when = dt.datetime.fromtimestamp(ts_ns / 1e9, dt.UTC)
        price = Decimal(str(bar.close))  # type: ignore[attr-defined]

        if when.date() != self._day:
            self._day = when.date()
            self._index = 0
            self.governor.start_day(when.date())
        self._index += 1

        state = self.governor.on_equity(at=when, unrealized=self._unrealized(price))
        self.daily_states[when.date()] = state.value
        if state is State.HALTED_FAIL:
            await self.cancel_working()
            if self._entry_price is not None:
                await self.close()
            return
        if state is State.HALTED_SUCCESS:
            await self.cancel_working()
            return

        if self._index in ENTRY_BARS and self._entry_price is None:
            self.governor.record_entry()
            self._direction = 1
            await self.buy(
                S.CONTRACTS,
                stop_loss_ticks=S.STOP_TICKS,
                take_profit_ticks=S.TARGET_TICKS,
                custom_tag=f"probe-{self._day}-{self._index}",
            )

    async def on_fill(self, fill: object) -> None:
        """``fill`` is an SDK HalfTradeModel: profit_and_loss is None on the OPENING half.

        That None is the discriminator between an entry and an exit, and it is upstream's
        own convention rather than something inferred from position state - which would go
        wrong the moment a position were scaled.
        """
        fees = Decimal(str(getattr(fill, "fees", 0) or 0))
        commissions = Decimal(str(getattr(fill, "commissions", 0) or 0))
        pnl = getattr(fill, "profit_and_loss", None)
        if pnl is None:
            self._entry_price = Decimal(str(fill.price))  # type: ignore[attr-defined]
            self._entry_costs = fees + commissions
            return

        #: An exit. Upstream owns the money; the governor is only TOLD the realised amount
        #: so its realized-only winning-day lock can be evaluated on the flat side.
        stamp = getattr(fill, "creation_timestamp", None)
        when = stamp if stamp is not None else dt.datetime.now(dt.UTC)
        round_turn_costs = self._entry_costs + fees + commissions
        self._entry_price = None
        self._entry_costs = Decimal(0)
        self._direction = 0
        state = self.governor.record_exit(
            net_pnl=Decimal(str(pnl)) - round_turn_costs, at=when
        )
        self.daily_states[when.date()] = state.value


# ======================================================================================
# the synthetic sessions - outcomes decided in advance, not sampled
# ======================================================================================


@dataclass(frozen=True)
class SyntheticDay:
    day: dt.date
    shape: str
    expected_state: str


def _bar(bar_type: BarType, ts_ns: int, step: int, o: Decimal, h: Decimal,
         low: Decimal, c: Decimal) -> Bar:
    return Bar(bar_type=bar_type, ts_event=ts_ns, ts_init=ts_ns + step,
               open=o, high=h, low=low, close=c, volume=100)


def build_sessions(
    *, contract_id: str, start: dt.date = dt.date(2025, 6, 2), days: int = 30,
    base: Decimal = Decimal("5000.00"),
) -> tuple[tuple[Bar, ...], tuple[SyntheticDay, ...]]:
    """Thirty weekday sessions cycling three shapes with predetermined outcomes.

    WIN      price marches up after the first entry; the 16-tick target is taken, realizing
             +$196.20, which trips the winning-day lock on one trade.
    KILL     price marches down; the first two entries stop out for -$103.80 each, and the
             third drifts one point adverse, putting realized + unrealized at -$257.60.
    QUIET    price never travels far enough to touch either barrier, so the day ends ACTIVE.
    """
    bar_type = BarType(contract_id=contract_id, unit=AggregateBarUnit.MINUTE, unit_number=1)
    step = 60_000_000_000
    tick = S.TICK_SIZE

    bars: list[Bar] = []
    plan: list[SyntheticDay] = []
    day = start
    emitted = 0
    shapes = ("WIN", "KILL", "QUIET")

    while emitted < days:
        if day.weekday() >= 5:
            day += dt.timedelta(days=1)
            continue
        shape = shapes[emitted % len(shapes)]
        #: 09:30 ET. June is EDT (UTC-4), stated as a fixed UTC stamp so the fixture does not
        #: depend on a tz lookup to mean what it says.
        open_ns = int(
            dt.datetime(day.year, day.month, day.day, 13, 30, tzinfo=dt.UTC).timestamp() * 1e9
        )
        price = base

        for index in range(BARS_PER_DAY):
            ts = open_ns + index * step
            if shape == "WIN":
                #: after the first entry (bar 5), climb two ticks a bar: the +16-tick target
                #: is reached well inside the session and nothing approaches the stop.
                move = tick * 2 if index >= 6 else Decimal(0)
                nxt = price + move
                bars.append(_bar(bar_type, ts, step, price, max(price, nxt), min(price, nxt), nxt))
            elif shape == "KILL":
                #: fall two ticks a bar so each entry stops out, then leave the third entry
                #: one point under water to trip the killswitch on live equity.
                move = -tick * 2 if index >= 6 else Decimal(0)
                nxt = price + move
                bars.append(_bar(bar_type, ts, step, price, max(price, nxt), min(price, nxt), nxt))
            else:
                #: oscillate inside +/- 1 tick: never 8 ticks either way.
                nxt = price + (tick if index % 2 else -tick)
                bars.append(_bar(bar_type, ts, step, price, max(price, nxt), min(price, nxt), nxt))
            price = nxt

        plan.append(
            SyntheticDay(
                day=day,
                shape=shape,
                expected_state=(
                    State.HALTED_SUCCESS.value if shape == "WIN"
                    else State.HALTED_FAIL.value if shape == "KILL"
                    else State.ACTIVE.value
                ),
            )
        )
        emitted += 1
        day += dt.timedelta(days=1)

    return tuple(bars), tuple(plan)


__all__ = [
    "BARS_PER_DAY",
    "ENTRY_BARS",
    "LOSS_REALIZED",
    "PROBE_SPEC",
    "WIN_REALIZED",
    "GovernorProbe",
    "SyntheticDay",
    "build_sessions",
]
