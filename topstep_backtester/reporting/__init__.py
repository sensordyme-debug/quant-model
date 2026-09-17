"""Reporting: present what the engine returned, including the parts that are missing.

The hard part of reporting is not formatting. It is refusing to fill a row that has no
number behind it. A report with an empty "expected first payout" line is honest; one with a
plausible figure derived from an assumption nobody stated is not, and the second is much
easier to write.

So every field here resolves to one of three things: a number the engine produced, a number
``reference.arithmetic`` produced independently, or the string UNMODELED with a reason. There
is no fourth category and nothing is estimated in this package.
"""
from __future__ import annotations

__all__: list[str] = []
