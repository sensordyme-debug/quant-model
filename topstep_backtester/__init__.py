"""Layer B: integration around the upstream ``topstep-backtest`` engine.

WHAT THIS PACKAGE IS
--------------------
A harness. It prepares data, describes strategies, configures accounts, runs the UPSTREAM
engine, and reports what the upstream engine returned. It is deliberately incapable of
computing a fill, a P&L, a drawdown or a prop-firm verdict on its own.

WHAT THIS PACKAGE IS NOT
------------------------
It is not a backtesting engine. There is exactly one engine in this system and it lives in
site-packages. If you find yourself writing a loop that walks bars and decides whether a
stop was hit, stop: that calculation already exists upstream and a second copy of it would
be a second answer nobody can adjudicate.

THE LAYER RULE, AND HOW IT IS ENFORCED
--------------------------------------
``topstep_backtester.upstream`` is the ONLY module here permitted to ``import
topstep_backtest``. Everything else imports the names it needs from that seam. This is not
a style preference - it is what makes "we did not patch, shadow or override upstream"
a checkable claim instead of a promise. ``validation/layering.py`` reads the source of
every module in this package and fails if the rule is broken.

THE SAFETY POSTURE
------------------
Historical research only. No credentials, no gateway, no order transmission - see
``safety.py``, which states the posture as constants and provides the assertion that the
test suite and every entry point call.
"""
from __future__ import annotations

#: Layer B's own version. Independent of the upstream engine's version, which is recorded
#: separately in ``upstream.CERTIFIED_VERSION`` because they drift for different reasons.
__version__ = "0.1.0"

__all__ = ["__version__"]
