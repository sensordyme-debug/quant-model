"""Versioned account and execution configuration.

Two kinds of assumption live here, and they are kept apart on purpose:

    account.py      what the prop firm requires - the target, the trailing loss limit,
                    the consistency rule, the position cap. Facts about the contract
                    you signed, not choices.
    execution.py    what we assume about fills - slippage, fees, whether a limit fills
                    on touch. Choices, and the results move when they change, so they
                    are a LADDER rather than a single setting.

Both are versioned. A result carries the id of the profile that produced it, so two
numbers computed under different assumptions can never be compared by accident.
"""
from __future__ import annotations

__all__: list[str] = []
