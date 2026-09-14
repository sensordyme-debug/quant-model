"""CME/CBOT/NYMEX/COMEX futures contract terms.

Supersedes `scripts/futures_data.py:SPECS`, which carried four contracts (MES/ES/MNQ/NQ) and
stored multiplier, tick AND tick_value as three independent numbers - three chances to
disagree. Here tick_value is derived (`InstrumentSpec.tick_value`) and
`tests/test_qb_futures.py` pins every derived value against that original table, so this is
a refactor of a redundancy rather than a change of any number.

Part 4 asks for ES, NQ, YM, RTY, CL, GC "and additional contracts later", and says not to
assume all futures behave identically. They do not, and the table is the place that knows:
YM ticks in whole index points, RTY and GC in tenths, CL in cents, and the equity-index
micros are a tenth of their parent while MCL and MGC are a tenth of theirs on a different
tick grid. Every one of those combinations is wrong if a caller assumes ES.

Margin is deliberately NOT here. A contract's terms are a fact about the exchange; margin is
a fact about whoever is carrying the position, and for this project's purpose that is a prop
firm whose limits differ per account and per firm. It lives in `propfirm.PropFirmProfile`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from quant_brain.core.instruments import AssetClass, InstrumentSpec

#: Quarterly cycle for the equity-index complex: March, June, September, December.
QUARTERLY = (3, 6, 9, 12)
#: CL lists every calendar month.
MONTHLY = tuple(range(1, 13))
#: GC's liquid months. Trading the illiquid ones is a slippage decision, not a data one.
GOLD_ACTIVE = (2, 4, 6, 8, 12)


@dataclass(frozen=True)
class FuturesContract:
    """A futures root: its contract terms plus how it rolls.

    Wraps rather than subclasses `InstrumentSpec` so the core stays free of roll logic -
    "what a contract is worth" is market-agnostic, "when it expires" is not.
    """

    spec: InstrumentSpec
    #: Months in which a contract lists. Drives front-month selection and roll windows.
    cycle: tuple[int, ...] = QUARTERLY
    #: Calendar days before expiry at which the front month stops being the traded one.
    #: 8 matches `futures_data.ROLL_DAYS`, which the existing ES/MES store was built with -
    #: changing it would silently invalidate `data/futures/ES.parquet`.
    roll_days: int = 8
    #: The parent contract when this is a micro. Lets a strategy researched on ES be sized
    #: on MES without re-researching it, which is the whole point of micros for prop firms.
    parent: str | None = None
    #: Indicative round-turn commission in USD, all-in (broker + exchange + NFA). Used as the
    #: default in `costs.py`; a real account overrides it. Kept beside the contract because
    #: it is per-contract, not per-notional, which is the thing an equity cost model gets
    #: structurally wrong.
    commission_round_turn: float = 0.0
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def symbol(self) -> str:
        return self.spec.symbol

    @property
    def is_micro(self) -> bool:
        return self.parent is not None


def _fut(symbol: str, mult: float, tick: float, exch: str, desc: str, *,
         cycle: tuple[int, ...] = QUARTERLY, parent: str | None = None,
         rt: float = 0.0, tags: tuple[str, ...] = ()) -> FuturesContract:
    return FuturesContract(
        spec=InstrumentSpec(symbol=symbol, asset_class=AssetClass.FUTURE, multiplier=mult,
                            tick=tick, exchange=exch, description=desc),
        cycle=cycle, parent=parent, commission_round_turn=rt, tags=tags,
    )


#: Round-turn commissions. ES/NQ/MES/MNQ are Topstep's PUBLISHED all-in round-turn rates -
#: ES $3.78, NQ $3.78, MES $1.22, MNQ $1.22 (help.topstep.com/en/articles/8284197, retrieved
#: 2026-09-13) - because a Topstep account is the venue this repository is actually sizing
#: for, and the rate the account pays is not a modelling choice. They replace the round $4.00
#: / $1.00 placeholders that stood here before: the micro figure was the one that mattered,
#: $1.00 against $1.22 undercharging a micro round turn by 18% in the flattering direction,
#: on the contract a $50K account is permitted to trade and at the size where commission is a
#: large share of the edge. `CostModel.for_contract` halves these into a per-side charge and
#: `futures_discover` prices its whole funnel off it, so the error propagated into every cost
#: gate and every Topstep pass-rate estimate.
#:
#: The remaining roots (YM, RTY, CL, GC and their micros) keep the indicative $4.00 / $1.00
#: retail/prop level as of 2026-09. That is a DEFAULT, not a measurement, and it is left
#: alone deliberately: no per-product rate for them was verified on a Topstep page on
#: 2026-09-13, and replacing an unverified number with a differently unverified one buys
#: nothing. Cite a rate before you trade one of them.
#:
#: Either way a rate here is a default, not a measurement: F-2a measured the ES round trip at
#: 0.488 bps of notional from real quotes, and that measurement - not this constant - is what
#: a cost-sensitive result should cite. Recorded here so a sizing call never silently charges
#: zero.
CONTRACTS: dict[str, FuturesContract] = {
    # --- equity index, full size -------------------------------------------------------
    "ES":  _fut("ES",  50.0,  0.25, "CME",  "E-mini S&P 500",        rt=3.78, tags=("equity_index",)),
    "NQ":  _fut("NQ",  20.0,  0.25, "CME",  "E-mini Nasdaq-100",     rt=3.78, tags=("equity_index",)),
    "YM":  _fut("YM",   5.0,  1.00, "CBOT", "E-mini Dow",            rt=4.00, tags=("equity_index",)),
    "RTY": _fut("RTY", 50.0,  0.10, "CME",  "E-mini Russell 2000",   rt=4.00, tags=("equity_index",)),
    # --- equity index, micro -----------------------------------------------------------
    "MES": _fut("MES",  5.0,  0.25, "CME",  "Micro E-mini S&P 500",   parent="ES",  rt=1.22, tags=("equity_index", "micro")),
    "MNQ": _fut("MNQ",  2.0,  0.25, "CME",  "Micro E-mini Nasdaq",    parent="NQ",  rt=1.22, tags=("equity_index", "micro")),
    "MYM": _fut("MYM",  0.5,  1.00, "CBOT", "Micro E-mini Dow",       parent="YM",  rt=1.00, tags=("equity_index", "micro")),
    "M2K": _fut("M2K",  5.0,  0.10, "CME",  "Micro E-mini Russell",   parent="RTY", rt=1.00, tags=("equity_index", "micro")),
    # --- energy ------------------------------------------------------------------------
    "CL":  _fut("CL", 1000.0, 0.01, "NYMEX", "Crude Oil",  cycle=MONTHLY, rt=4.00, tags=("energy",)),
    "MCL": _fut("MCL", 100.0, 0.01, "NYMEX", "Micro Crude", cycle=MONTHLY, parent="CL", rt=1.00, tags=("energy", "micro")),
    # --- metals ------------------------------------------------------------------------
    "GC":  _fut("GC",  100.0, 0.10, "COMEX", "Gold",       cycle=GOLD_ACTIVE, rt=4.00, tags=("metal",)),
    "MGC": _fut("MGC",  10.0, 0.10, "COMEX", "Micro Gold", cycle=GOLD_ACTIVE, parent="GC", rt=1.00, tags=("metal", "micro")),
}

#: The contracts F-2a actually proved data for, from `research/futures_probe.json`
#: (2,760 one-minute TRADES bars each on the existing IBKR paper account, 2026-09-11).
#: Anything outside this set is architecturally supported but has no verified history here,
#: and a research run that uses one should say so.
DATA_VERIFIED: frozenset[str] = frozenset({"ES", "MES", "NQ", "MNQ"})


def get(symbol: str) -> FuturesContract:
    """Look up a contract root, with a message that lists the alternatives.

    Raises rather than returning None: every caller of this needs a real multiplier, and a
    None that flows into a sizing call becomes a wrong position rather than an error.
    """
    try:
        return CONTRACTS[symbol.upper()]
    except KeyError:
        raise KeyError(
            f"unknown futures root {symbol!r}; known roots: {', '.join(sorted(CONTRACTS))}"
        ) from None


def micros_of(symbol: str) -> list[str]:
    """Micro contracts whose parent is `symbol`.

    The prop-firm sizing path uses this: a firm's contract limit is counted in contracts,
    not notional, so expressing a position in micros buys 10x the granularity under the same
    limit. That is a real strategic lever when the limit is 3 contracts.
    """
    root = symbol.upper()
    return sorted(s for s, c in CONTRACTS.items() if c.parent == root)
