"""CVD_ABSORPTION_HARVESTER / XFA_V2.0 - the owner's frozen strategy.

    tick_schema.py     the tick-data contract, and the checker that gates every run on it
    spec.py            the specification, its hash, and the 17-item ambiguity register
    ticks.py           per-trade delta classification and CVD, reset at 09:30 ET
    signal.py          1-minute aggregation, swing memory, the divergence detector
    governor.py        the winning-day lock, the killswitch, and the state machine
    strategy.py        the wiring onto the upstream engine
    governor_probe.py  the PART 20 plumbing test, which is NOT a strategy backtest

STATUS
------
The historical backtest is BLOCKED, twice over and independently:

  1. DATA. The strategy requires per-trade time and sales with the quote standing at each
     trade. This repository holds 1-minute bars only - minimum inter-record gap 60 seconds,
     zero simultaneous prints. CVD cannot be approximated from that and will not be.
  2. SPECIFICATION. Eleven of the seventeen register items are unresolved, so the spec cannot
     be frozen, so it cannot run. Deciding those readings after seeing results would be
     choosing the reading that won.

Both are reported rather than worked around.
"""
from __future__ import annotations

__all__: list[str] = []
