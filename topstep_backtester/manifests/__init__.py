"""Run manifests: everything needed to say what produced a number, and to produce it again.

A result without a manifest is an anecdote. The manifest names the data, the strategy, the
rules, the execution assumptions, the engine version and the code - each by content hash, so
"the same run" is a claim that can be checked rather than remembered.
"""
from __future__ import annotations

__all__: list[str] = []
