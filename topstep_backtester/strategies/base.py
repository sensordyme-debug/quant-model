"""The base class the owner's strategy subclasses. Thin on purpose.

WHAT IT ADDS
------------
Three things, and nothing else: it binds a frozen spec to the running strategy so the result
can name what produced it, it asserts the research-only posture at construction, and it
refuses to start if the spec was never frozen.

WHAT IT DELIBERATELY DOES NOT ADD
---------------------------------
No order helpers, no position tracking, no P&L, no session logic, no bracket manager. All of
that already exists on upstream's ``SymbolStrategy`` and is already tested there. A
convenience wrapper over it would be a second implementation of the most consequential code
in the system, and the first time the two disagreed nobody would be able to say which was
right. Subclasses call ``self.buy``, ``self.sell``, ``self.close``, ``self.move_stop`` and
``self.in_trade_session`` directly - upstream's API is the API.

TWO MISTAKES THIS CLASS MAKES IMPOSSIBLE
----------------------------------------
1. A NON-ASYNC CALLBACK. ``on_bar`` is a coroutine and the order methods are awaitable.
   Forgetting the ``await`` does not raise where you wrote it: the coroutine is created,
   never scheduled, and the order is simply never placed. The backtest then runs to
   completion and reports zero trades, which reads like a strategy that found no signals
   rather than like a bug.

2. SHADOWING UPSTREAM. ``SymbolStrategy`` already defines ``spec`` - and it is the
   INSTRUMENT spec, the tick size and tick value every P&L is computed from. A subclass
   that assigns its own ``spec`` is replacing the contract economics with something else
   entirely. That is not hypothetical: the first version of this file did exactly that, and
   was caught only because upstream happens to expose it as a read-only property. The other
   thirty-odd public names on that class have no such protection, so the check below covers
   all of them.

Both are checked at class-definition time, which is the last moment they can be caught
before a result exists.
"""
from __future__ import annotations

import inspect

from topstep_backtester.safety import assert_research_only
from topstep_backtester.strategies.spec import FrozenStrategySpec
from topstep_backtester.upstream import SymbolStrategy

#: Every public name upstream's strategy base already uses. Computed rather than listed, so
#: it cannot fall out of date when the engine is upgraded.
UPSTREAM_RESERVED_NAMES: frozenset[str] = frozenset(
    name for name in dir(SymbolStrategy) if not name.startswith("_")
)

#: Callbacks a subclass is expected to override. Overriding these is the whole point.
_OVERRIDABLE: frozenset[str] = frozenset(
    {"on_bar", "on_fill", "on_order", "on_position", "on_reject", "on_start", "on_stop"}
)


class StrategyContractError(TypeError):
    """A subclass that does not honour the upstream callback contract."""


class ResearchStrategy(SymbolStrategy):
    """Bind a frozen spec to an upstream strategy. Historical research only."""

    #: Deliberately NOT named ``spec`` - see the module docstring.
    research_spec: FrozenStrategySpec

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

        handler = cls.__dict__.get("on_bar")
        if handler is not None and not inspect.iscoroutinefunction(handler):
            raise StrategyContractError(
                f"{cls.__name__}.on_bar must be `async def`. The engine awaits it, and a "
                f"plain function returning None makes every order you place vanish silently "
                f"- the run completes and reports no trades, which looks like a strategy "
                f"that found nothing rather than like a wiring bug."
            )

        collisions = sorted(
            name
            for name in vars(cls)
            if not name.startswith("_")
            and name in UPSTREAM_RESERVED_NAMES
            and name not in _OVERRIDABLE
        )
        if collisions:
            raise StrategyContractError(
                f"{cls.__name__} defines {collisions}, which upstream's SymbolStrategy "
                f"already uses. Shadowing one of those replaces engine internals with "
                f"something the engine did not expect - `spec`, for instance, is the "
                f"instrument's tick size and tick value, and overriding it silently changes "
                f"every dollar of P&L. Rename yours."
            )

    def __init__(self, contract_id: str, *, spec: FrozenStrategySpec, **kwargs: object) -> None:
        assert_research_only()
        spec.assert_runnable()
        super().__init__(contract_id, **kwargs)  # type: ignore[arg-type]
        self.research_spec = spec

    @property
    def spec_id(self) -> str:
        return self.research_spec.spec_id


__all__ = ["UPSTREAM_RESERVED_NAMES", "ResearchStrategy", "StrategyContractError"]
