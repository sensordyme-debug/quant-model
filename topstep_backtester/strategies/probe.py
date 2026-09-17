"""A deterministic wiring test that happens to be shaped like a strategy.

WHAT IT IS FOR
--------------
Proving that a bar written into a canonical frame comes out the far end of the upstream
engine as the P&L arithmetic says it should. It exercises the whole path - canonical frame,
bar adapter, contract identity, account profile, execution profile, engine, result
projection - against a series small enough to work out by hand.

That last part is what makes it worth having. A test that asserts the pipeline returns the
same number as last time only detects change. This one asserts a number derived
independently: buy one ES at 5000.00, exit at 5002.00, that is 8 ticks at $12.50 = $100
gross, minus one round turn of fees. If the pipeline disagrees with that, the pipeline is
wrong, and no amount of internal consistency rescues it.

THE ORDER LIFECYCLE THESE FIXTURES ENCODE
-----------------------------------------
Getting the expected number right requires knowing exactly when upstream acts, and the
engine is explicit about it (``execution/sim_broker.py``: "children created on an intrabar
fill carry accepted_ts stamps that defer them to the next bar"). So:

    bar N completes    ->  the strategy is shown bar N and places a market order
    bar N+1            ->  the entry fills, at bar N+1's OPEN
    bar N+1            ->  the bracket children are created, stamped with the fill time,
                           and are therefore NOT yet active
    bar N+2 onward     ->  the stop and target can fill

Two consequences worth stating, because both look like bugs the first time you meet them.
An entry never fills on the bar that triggered it, and a protective order never fills on the
bar the entry filled on. That is not conservatism for its own sake: within a single bar the
price path is unknown, so filling an exit on the entry bar would require assuming an order
of events the data does not contain.

The two fixtures below cover the two ways a target resolves once it IS active, because they
pay differently and a pipeline that confuses them would misreport every winning trade:

    probe_series()       the bar straddles the target  -> fills AT the limit, 5002.00
    probe_series_gap()   the bar OPENS beyond it       -> the limit is marketable and fills
                                                          at the open, 5003.00, which is
                                                          better than the limit price

WHAT IT IS NOT
--------------
Not a strategy, not a candidate, not registered, and it has no hypothesis. It buys on a bar
index. It refuses to run on anything but its own synthetic series - see the
``synthetic_series_id`` guard - because a fixture that can be pointed at real data eventually
is, and then a wiring probe is quietly reported as a result.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pandas as pd

from quant_brain.data.schema import build_frame
from topstep_backtester.strategies.base import ResearchStrategy
from topstep_backtester.strategies.spec import FrozenStrategySpec

#: Any series this probe will trade must carry this prefix.
SYNTHETIC_PREFIX = "SYNTH-"

#: The bar the probe buys on, counting from zero within the series it is given.
ENTRY_BAR_INDEX = 2

#: Bracket in ticks. Symmetric, so a wrong-signed P&L is unmistakable.
TAKE_PROFIT_TICKS = 8
STOP_LOSS_TICKS = 8

#: ES terms, restated here ONLY so the expected values below are derived independently of
#: the engine. If these ever disagree with upstream's SPECS["ES"], the probe's own test
#: fails - which is the point: two sources that must agree, checked rather than assumed.
ES_TICK_SIZE = Decimal("0.25")
ES_TICK_VALUE = Decimal("12.50")

#: The price every fixture enters at: the open of the bar after the signal bar.
ENTRY_PRICE = Decimal("5000.00")

#: probe_series(): the target is 8 ticks up, and bar 4 straddles it, so it fills there.
EXPECTED_EXIT_PRICE = ENTRY_PRICE + TAKE_PROFIT_TICKS * ES_TICK_SIZE
EXPECTED_GROSS_PNL = TAKE_PROFIT_TICKS * ES_TICK_VALUE

#: probe_series_gap(): bar 4 opens at 5003.00, already through the 5002.00 target, so the
#: resting limit is marketable and fills at the open - twelve ticks rather than eight.
GAP_EXIT_PRICE = Decimal("5003.00")
GAP_TICKS = int((GAP_EXIT_PRICE - ENTRY_PRICE) / ES_TICK_SIZE)
EXPECTED_GAP_GROSS_PNL = GAP_TICKS * ES_TICK_VALUE

PROBE_SPEC = FrozenStrategySpec(
    name="synthetic_wiring_probe",
    version="1.0.0",
    instrument="ES",
    bar_interval="1min",
    session_window="09:30-16:00 ET",
    entry_rules=(
        f"buy 1 contract on the completion of bar index {ENTRY_BAR_INDEX} of the supplied "
        f"synthetic series, unconditionally",
    ),
    exit_rules=(
        f"bracket: take profit {TAKE_PROFIT_TICKS} ticks, stop loss {STOP_LOSS_TICKS} ticks",
    ),
    risk_rules=("one contract, one trade, one series",),
    parameters={
        "entry_bar_index": ENTRY_BAR_INDEX,
        "take_profit_ticks": TAKE_PROFIT_TICKS,
        "stop_loss_ticks": STOP_LOSS_TICKS,
        "size": 1,
    },
    hypothesis=(
        "None. This is a wiring test. It asserts arithmetic, not an edge, and must never "
        "be reported as a research result."
    ),
).freeze(author="pipeline-certification", at=dt.datetime(2026, 9, 17, tzinfo=dt.UTC))


class SyntheticProbe(ResearchStrategy):
    """Buys once, on a fixed bar index, and lets the bracket resolve it."""

    def __init__(self, contract_id: str, *, synthetic_series_id: str) -> None:
        if not synthetic_series_id.startswith(SYNTHETIC_PREFIX):
            raise ValueError(
                f"SyntheticProbe refuses series {synthetic_series_id!r}: it trades only "
                f"series whose id begins with {SYNTHETIC_PREFIX!r}. This probe buys on a "
                f"bar index with no hypothesis behind it, so a P&L from it on real data "
                f"would be noise wearing the clothes of a result."
            )
        super().__init__(contract_id, spec=PROBE_SPEC, require_ready=False)
        self.synthetic_series_id = synthetic_series_id
        self._seen = 0
        self._entered = False

    async def on_bar(self, bar: object) -> None:
        index = self._seen
        self._seen += 1
        if index == ENTRY_BAR_INDEX and not self._entered:
            self._entered = True
            await self.buy(
                1,
                stop_loss_ticks=STOP_LOSS_TICKS,
                take_profit_ticks=TAKE_PROFIT_TICKS,
                custom_tag="probe-entry",
            )


def _frame(day: dt.date, contract_symbol: str, rows: list[tuple[float, float, float, float, int]],
           name: str) -> pd.DataFrame:
    if day.weekday() >= 5:
        raise ValueError(f"{day} is a weekend; upstream rejects weekend bars")
    #: 10:00 ET. June is EDT (UTC-4), stated as a fixed UTC stamp rather than localised, so
    #: the fixture does not depend on a timezone database lookup to mean what it says, and
    #: sits nowhere near the 17:00-18:00 ET maintenance halt the validator rejects.
    stamps = pd.date_range(
        pd.Timestamp(f"{day.isoformat()} 14:00:00", tz="UTC"), periods=len(rows),
        freq="1min", tz="UTC",
    )
    return build_frame(
        instrument="ES",
        contract_symbol=contract_symbol,
        contract_family="ES",
        timestamp=stamps,
        session_date=[day] * len(rows),
        bar_interval="1min",
        open_=[r[0] for r in rows],
        high=[r[1] for r in rows],
        low=[r[2] for r in rows],
        close=[r[3] for r in rows],
        volume=[r[4] for r in rows],
        name=name,
    )


def probe_series(*, day: dt.date = dt.date(2025, 6, 3),
                 contract_symbol: str = "ESM5") -> pd.DataFrame:
    """Six ES bars whose single outcome is a target fill AT the limit price.

    Bar 2 closes at 5000.25 and is where the probe signals. Bar 3 opens at 5000.00, which is
    the entry fill, and stays well inside the bracket. Bar 4 is the first bar on which the
    protective orders are active and it straddles the 5002.00 target - opening below it and
    trading above it - so the limit fills at exactly 5002.00. Bar 5 is quiet.

    Nothing in the series comes within four ticks of the 4998.00 stop, so there is exactly
    one possible outcome: +8 ticks, +$100.00 gross.
    """
    rows = [
        # open,     high,     low,      close,    volume
        (4999.00, 4999.75, 4998.75, 4999.50, 120),   # 0
        (4999.50, 5000.25, 4999.25, 5000.00, 140),   # 1
        (5000.00, 5000.50, 4999.75, 5000.25, 155),   # 2  signal
        (5000.00, 5000.75, 4999.50, 5000.50, 310),   # 3  entry fills at the open, 5000.00
        (5000.50, 5002.50, 5000.25, 5002.25, 280),   # 4  target active; straddles 5002.00
        (5002.25, 5002.75, 5002.00, 5002.50, 150),   # 5
    ]
    return _frame(day, contract_symbol, rows, "SYNTH-probe")


def probe_series_gap(*, day: dt.date = dt.date(2025, 6, 3),
                     contract_symbol: str = "ESM5") -> pd.DataFrame:
    """The same shape, except bar 4 OPENS beyond the target.

    The resting 5002.00 limit is already marketable when the bar opens at 5003.00, so it
    fills at the open rather than at the limit - twelve ticks, +$150.00 gross. A pipeline
    that reported $100 here would be silently capping winners at their limit price.
    """
    rows = [
        (4999.00, 4999.75, 4998.75, 4999.50, 120),   # 0
        (4999.50, 5000.25, 4999.25, 5000.00, 140),   # 1
        (5000.00, 5000.50, 4999.75, 5000.25, 155),   # 2  signal
        (5000.00, 5000.75, 4999.50, 5000.50, 310),   # 3  entry fills at the open, 5000.00
        (5003.00, 5003.25, 5002.50, 5002.75, 420),   # 4  opens through the target
        (5002.75, 5003.00, 5002.50, 5002.75, 150),   # 5
    ]
    return _frame(day, contract_symbol, rows, "SYNTH-probe-gap")


__all__ = [
    "ENTRY_BAR_INDEX",
    "ENTRY_PRICE",
    "ES_TICK_SIZE",
    "ES_TICK_VALUE",
    "EXPECTED_EXIT_PRICE",
    "EXPECTED_GAP_GROSS_PNL",
    "EXPECTED_GROSS_PNL",
    "GAP_EXIT_PRICE",
    "GAP_TICKS",
    "PROBE_SPEC",
    "STOP_LOSS_TICKS",
    "SYNTHETIC_PREFIX",
    "TAKE_PROFIT_TICKS",
    "SyntheticProbe",
    "probe_series",
    "probe_series_gap",
]
