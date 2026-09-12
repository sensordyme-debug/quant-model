"""What an instrument *is*, independent of any market, broker or strategy.

This is the seam the rest of Quant Brain hangs off. Before this module the repository
described an instrument implicitly, in constants scattered across the runners:
`intraday_common.COMMISSION_PER_SHARE = 0.005` says "equities" and
`futures_data.SPECS["ES"]["multiplier"] = 50.0` says "futures", and nothing connected them.
A strategy that wanted to run on both had to know which one it was.

An `InstrumentSpec` is the answer to that: the *contractual* facts about a tradable thing -
what one unit is worth, how finely it may be priced, what currency it settles in - with no
opinion about cost, session, sizing or venue. Those are separate abstractions (`costs`,
`calendar`, `sizing`, `execution`) precisely so a market branch can vary one without the
others, and so the core never has to grow an `if asset_class == ...`.

Deliberately NOT here, because they are market-specific and belong in `markets/<name>/`:
futures roll rules and expiry chains, options greeks and exercise style, crypto's 24/7
session, equity corporate actions.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass


class AssetClass(str, enum.Enum):
    """The market branches Quant Brain is designed around.

    `str` mixin so a spec round-trips through JSON as `"future"` rather than an enum repr -
    every provenance record and prop-firm profile in this system is a JSON file.

    EQUITY and FUTURE are live. The rest are declared so the registry, the provenance
    schema and the risk plumbing already have a name to key on; declaring an enum member
    costs nothing and is not the same as building a branch (see AGENTS.md / Part 27).
    """

    EQUITY = "equity"
    FUTURE = "future"
    OPTION = "option"
    ETF = "etf"
    CRYPTO = "crypto"


@dataclass(frozen=True)
class InstrumentSpec:
    """The contract terms of one tradable instrument.

    Frozen because a spec is a fact about the world, not state: two strategies holding the
    same ES spec must not be able to change each other's tick value. Cheap to copy, safe to
    share across processes, hashable so it can key a dict of per-instrument caches.

    Attributes:
        symbol:       the root the repository trades under ("ES", "NVDA"). Not a broker's
                      contract id - `execution` adapters map this to whatever the venue wants.
        asset_class:  which market branch owns it.
        multiplier:   dollars of notional per 1.0 of price. 50.0 for ES, 1.0 for a share.
        tick:         minimum price increment. 0.25 for ES, 0.01 for a US equity.
        currency:     settlement currency; only USD is exercised today, but a spec that
                      cannot say what it settles in is a spec that silently assumes USD.
        exchange:     venue string, used for reporting and for adapters that need it.
        description:  human label, for reports and dashboards.
    """

    symbol: str
    asset_class: AssetClass
    multiplier: float = 1.0
    tick: float = 0.01
    currency: str = "USD"
    exchange: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        # A spec with a non-positive multiplier or tick is not a degenerate instrument, it is
        # a typo - and it is one that produces silently wrong money downstream rather than an
        # exception: notional would be zero, tick_value would be zero, and a sizer would
        # happily return an unbounded position. Fail at construction, where the fix is obvious.
        if self.multiplier <= 0:
            raise ValueError(f"{self.symbol}: multiplier must be > 0, got {self.multiplier}")
        if self.tick <= 0:
            raise ValueError(f"{self.symbol}: tick must be > 0, got {self.tick}")

    @property
    def tick_value(self) -> float:
        """Dollars gained or lost per contract per one-tick move.

        Derived rather than stored: `futures_data.SPECS` carries multiplier, tick AND
        tick_value as three independent numbers, which is three chances to disagree. ES is
        50.0 x 0.25 = 12.50, which is what that table says - so this is a refactor of a
        redundancy, not a change of behaviour. `tests/test_qb_instruments.py` pins every
        derived value against the hand-written table it replaces.
        """
        return self.multiplier * self.tick

    def notional(self, price: float, quantity: float = 1.0) -> float:
        """Dollar notional of `quantity` units at `price`.

        Signed: a short position has negative notional. Callers that want exposure take
        `abs()` themselves, because the risk layer needs to distinguish net from gross and a
        helper that silently absolutes makes that impossible.
        """
        return price * self.multiplier * quantity

    def round_to_tick(self, price: float) -> float:
        """Snap a price to the instrument's grid.

        Rounds half away from zero via the tick count, so a limit computed as 4501.126 on ES
        becomes 4501.25 rather than a price the exchange will reject. Applied symmetrically
        for shorts because Python's round() is banker's rounding and would bias a long run of
        limits toward even ticks.
        """
        ticks = price / self.tick
        # int(x + copysign(0.5, x)) is round-half-away-from-zero without importing decimal.
        snapped = int(ticks + (0.5 if ticks >= 0 else -0.5))
        return snapped * self.tick

    def ticks_between(self, entry: float, exit_: float) -> float:
        """Signed tick move from `entry` to `exit_`. Positive = price rose.

        The unit futures risk is actually quoted in. A prop-firm daily loss limit of $1,000
        on MES is 800 ticks; expressing that in percent would need an account value the
        limit does not depend on.
        """
        return (exit_ - entry) / self.tick


def equity(symbol: str, *, exchange: str = "SMART", description: str = "") -> InstrumentSpec:
    """A US cash equity or ETF: one share, penny tick, no multiplier.

    A named constructor rather than a table, because the equity universe here is data-driven
    (69 daily symbols, 16 intraday, any Alpaca symbol) and enumerating it would go stale the
    first time the universe changes. Futures are the opposite - a small fixed set with
    per-contract terms - so those ARE a table, in `markets/futures_cme/instruments.py`.
    """
    return InstrumentSpec(
        symbol=symbol,
        asset_class=AssetClass.EQUITY,
        multiplier=1.0,
        tick=0.01,
        exchange=exchange,
        description=description or symbol,
    )
