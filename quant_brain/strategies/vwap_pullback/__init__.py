"""Intraday Multi-Timeframe VWAP Pullback System V1.0.0_Frozen.

A stateful engine, kept out of `quant_brain.research` because the certified research path runs
stateless signal arrays and this strategy cannot be written as one. See
`docs/VWAP_PULLBACK_INTEGRATION_PLAN.md` for the conflict register - nine places where this
specification and the certified architecture disagree, each resolved by ADDING rather than by
editing anything already certified.

    spec.py         every frozen constant, hashed; the ambiguity and conflict registers
    indicators.py   one VWAP array anchored at 18:00 ET, a causal 5-minute aggregate, ATR(14)
    orders.py       a simulated OCO bracket with idempotent actions and a book audit
    governor.py     the intraday limits: killswitch, profit cap, trade cap, loss breaker
    engine.py       the state machine and the bar loop

No network, no broker, no credentials. This phase is synthetic-test-only.
"""
from quant_brain.strategies.vwap_pullback.engine import Engine, State
from quant_brain.strategies.vwap_pullback.indicators import Bar
from quant_brain.strategies.vwap_pullback.spec import FROZEN, FROZEN_MNQ, VERSION

__all__ = ["Bar", "Engine", "FROZEN", "FROZEN_MNQ", "State", "VERSION"]
