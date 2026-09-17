"""Strategy specifications and the registry that holds them.

THERE ARE NO STRATEGIES IN THIS PACKAGE.
``registry.ACTIVE_STRATEGIES`` is empty and is meant to stay empty until the owner supplies
one. Nothing here auto-discovers, imports by glob, or resurrects a previous candidate - see
``registry`` for why that is a hard rule rather than a default.

The one executable strategy in this directory is ``probe.SyntheticProbe``, which trades a
hand-built synthetic series to prove the wiring works. It is not registered, not a research
candidate, and refuses to run on real data.
"""
from __future__ import annotations

__all__: list[str] = []
