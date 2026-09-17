"""Independent arithmetic, written to disagree with the engine if the engine is wrong.

Nothing in this directory imports the engine's money, fill or accounting code. It takes the
engine's FILLS - side, size, price - and recomputes the money from the contract terms, by
hand, the way a person with a tick table would. Agreement is then evidence; if these modules
shared code with upstream, agreement would be a tautology.

What this can and cannot catch is worth being precise about. It verifies the ACCOUNTING laid
on top of the fills. It cannot verify the fills themselves - whether the stop should have
been hit on that bar is a question about the fill model, and the only independent check on
that is the hand-computed golden fixtures in ``strategies/probe.py``.
"""
from __future__ import annotations

__all__: list[str] = []
