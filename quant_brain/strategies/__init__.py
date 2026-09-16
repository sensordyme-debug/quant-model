"""Stateful strategy engines.

`quant_brain.research` runs STATELESS specifications: a signal array over a feature frame plus
declarative exits. That covers a large class of rules and is the certified path.

A strategy that carries state ACROSS bars - an armed regime, the identity of a particular bar,
a bounded forward window, a cooldown clock, per-day counters - cannot be written as an array,
and pretending otherwise is how a state machine becomes an undocumented side effect. Those
live here, one package each, each with its own frozen specification and its own golden suite.

Nothing in this package modifies anything in `quant_brain.research`.
"""
