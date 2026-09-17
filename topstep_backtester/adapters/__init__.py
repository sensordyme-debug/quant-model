"""Adapters: canonical repository data in, upstream engine types out.

An adapter translates. It does not compute, clean, fill, interpolate or improve. If a bar
cannot be represented exactly in the upstream types, the adapter refuses and says which bar
and why - it never rounds a price to make the load succeed, because a price that has been
nudged onto a tick grid is a price nobody quoted, and a fill at one is fiction.
"""
from __future__ import annotations

__all__: list[str] = []
