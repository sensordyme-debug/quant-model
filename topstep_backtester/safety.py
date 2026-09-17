"""The research posture, stated as constants so it can be asserted rather than believed.

WHY CONSTANTS AND NOT A COMMENT
-------------------------------
"This pipeline does not transmit orders" is a claim about an entire package. A comment
saying so is worth nothing; a comment that has drifted from the code is worth less than
nothing. These flags exist so a test can read them, so an entry point can refuse to start
when one of them is wrong, and so a reviewer can find the single place the posture is
declared.

Every flag here is False and none of them is a switch. Turning one True does not enable a
capability - the capability is absent from the package. They are tripwires: a True value
means someone has begun building something this pipeline is not allowed to contain, and
the guard below turns that into a failure at import time rather than a surprise later.
"""
from __future__ import annotations

#: No connection to any broker, gateway or prop-firm API is made by this package.
LIVE_TRADING = False
#: Practice/demo endpoints are connections too, and are equally out of scope.
PRACTICE_TRADING = False
#: Nothing here constructs, signs, queues or sends an order to anything outside the process.
ORDER_TRANSMISSION = False
#: No parameter search, no sweep, no "best of N". A strategy arrives frozen or not at all.
OPTIMIZATION = False
#: The pipeline does not invent strategies. The owner supplies them.
STRATEGY_DISCOVERY = False
#: Data is historical, on disk, and immutable during a run.
HISTORICAL_ONLY = True

#: Modules whose mere presence in ``sys.modules`` proves a live path was imported. The SDK
#: is a legitimate dependency OF THE UPSTREAM PACKAGE for its live/parity code; it must
#: never be reachable from ours.
FORBIDDEN_MODULE_PREFIXES = (
    "topstep_sdk",
    "projectx",
    "ib_async",
    "ib_insync",
    "ibapi",
)

#: Names that only appear in code that sends something to a venue. Searched for in this
#: package's own source by ``validation.layering.scan_for_transmission``.
FORBIDDEN_CALL_TOKENS = (
    "place_order",
    "submit_order",
    "modify_order",
    "cancel_order_by_id",
    "AsyncTopstepClient",
    "api_key",
    "api_token",
    "account_credentials",
)


class SafetyViolation(RuntimeError):
    """A research-only invariant was broken. Never caught inside this package."""


def assert_research_only() -> None:
    """Fail unless the declared posture is intact.

    Called by every entry point and by the test suite. Cheap enough to call anywhere.
    """
    live = {
        "LIVE_TRADING": LIVE_TRADING,
        "PRACTICE_TRADING": PRACTICE_TRADING,
        "ORDER_TRANSMISSION": ORDER_TRANSMISSION,
        "OPTIMIZATION": OPTIMIZATION,
        "STRATEGY_DISCOVERY": STRATEGY_DISCOVERY,
    }
    enabled = sorted(name for name, value in live.items() if value)
    if enabled:
        raise SafetyViolation(
            f"research-only posture broken: {', '.join(enabled)} is True. This package has "
            f"no code path that can honour it; the flag is a tripwire, not a feature switch."
        )
    if not HISTORICAL_ONLY:
        raise SafetyViolation("HISTORICAL_ONLY is False; there is no live data path here.")


def imported_forbidden_modules() -> tuple[str, ...]:
    """Which live-path modules are currently imported, if any.

    Reported rather than raised: another part of the repository may legitimately have one
    loaded in the same interpreter. What matters is that nothing in THIS package imports
    one, which ``validation.layering`` proves from the source text.
    """
    import sys

    return tuple(
        sorted(
            name
            for name in sys.modules
            if any(name == p or name.startswith(p + ".") for p in FORBIDDEN_MODULE_PREFIXES)
        )
    )


__all__ = [
    "FORBIDDEN_CALL_TOKENS",
    "FORBIDDEN_MODULE_PREFIXES",
    "HISTORICAL_ONLY",
    "LIVE_TRADING",
    "OPTIMIZATION",
    "ORDER_TRANSMISSION",
    "PRACTICE_TRADING",
    "STRATEGY_DISCOVERY",
    "SafetyViolation",
    "assert_research_only",
    "imported_forbidden_modules",
]
