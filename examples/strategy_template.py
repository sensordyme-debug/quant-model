"""COPY THIS FILE to describe a strategy. Fill it in; change nothing else.

    cp examples/strategy_template.py examples/my_strategy.py
    # edit it
    python scripts/run_strategy.py --spec examples.my_strategy:SPEC

The engine runs what is written here and nothing else. It does not tune it, does not select
among variants, does not substitute a default for a rule left unstated, and does not resolve
an ambiguity in the author's favour - a spec with two readings is REFUSED at construction with
the conflict named.

WHAT THE ENGINE ENFORCES WHATEVER THIS FILE SAYS
--------------------------------------------------
  - the session ends flat. Topstep's mandatory flat is 15:10 CT and is not a parameter.
  - every completed round turn is charged.
  - a position decided on bar i fills at bar i's CLOSE and earns from bar i's close onward.
  - a stop or target must rest a whole number of ticks away, or the spec is refused.

THE ONE THING TO GET RIGHT
----------------------------
`signal(X)` returns one number per bar: +1 long, -1 short, 0 flat. It is called once per
session with that session's feature frame, so a window can never reach across a session
boundary. It must be CAUSAL - value at bar i may use bars 0..i and nothing later. The feature
library is audited for causality before the run and refuses to proceed if a feature can see
the future; a leak written directly into this function is the one thing that audit cannot
catch, so do not index ahead.
"""
from __future__ import annotations

import numpy as np

from quant_brain.research.strategy_spec import (
    CostSpec,
    ExitSpec,
    RiskSpec,
    SessionSpec,
    SizingSpec,
    StrategySpec,
)

# ======================================================================================
# PARAMETERS - every literal the rule depends on, named here rather than buried in the body
# ======================================================================================
# These are declared on the spec too (`params=`), so they are hashed and printed in the
# report. A result whose parameters are not written down is a result nobody can reproduce.

PARAMS = {
    "example_threshold": 1.5,
    "example_lookback": 20,
}


# ======================================================================================
# THE ENTRY RULE
# ======================================================================================

def signal(X):
    """Return one position per bar: +1 long, -1 short, 0 flat.

    `X` is the feature frame for ONE session. Useful columns include `minutes_from_open`,
    `opening_range_pos`, and the rest of `quant_brain.markets.futures_cme.features.library()`.
    Print `list(X.columns)` once to see what is available on this store.

    REPLACE THE BODY BELOW. What is here is a placeholder that never trades, so that running
    the template unedited produces an honest "no trades" rather than a result.
    """
    n = len(X)
    pos = np.zeros(n, dtype=float)

    # --- example of the shape a real rule takes -------------------------------------
    # orp  = np.nan_to_num(np.asarray(X["opening_range_pos"], dtype=float), nan=0.0)
    # mins = np.nan_to_num(np.asarray(X["minutes_from_open"], dtype=float), nan=0.0)
    # live = mins > PARAMS["example_lookback"]
    # pos[live & (orp >  PARAMS["example_threshold"])] = -1.0
    # pos[live & (orp < -PARAMS["example_threshold"])] = +1.0

    return pos


# ======================================================================================
# THE FROZEN SPECIFICATION
# ======================================================================================

SPEC = StrategySpec(
    name="my_strategy",                  # names the result files; make it distinctive
    instrument="MNQ",                    # ES · NQ · MES · MNQ (what is on disk)
    timeframe="1min",                    # the only supported bar size
    signal=signal,

    session=SessionSpec(
        open_et="09:30",                 # the window the strategy trades
        close_et="16:00",                # must be at or before 16:10 ET
        warmup_bars=0,                   # bars after the open before any entry is allowed
        last_entry_et=None,              # e.g. "15:00" - no NEW position after this
        flat_by_et=None,                 # e.g. "15:45" - the strategy's own forced flat
    ),

    # Exactly one stop form, exactly one target form, exactly one trail form.
    # Points are a fixed distance; ATR multiples move with the session's volatility.
    # `target_r` and `breakeven_at_r` need a stop, because R IS the stop distance.
    exit=ExitSpec(
        stop_points=None,                # e.g. 20.0   (a whole number of ticks)
        stop_atr=None,                   # e.g. 1.5    (multiples of the session ATR)
        structural_stop=False,           # stop at the signal bar's own extreme
        target_points=None,              # e.g. 40.0
        target_r=None,                   # e.g. 2.0    (needs a stop)
        trail_points=None,               # e.g. 15.0
        trail_atr=None,
        breakeven_at_r=None,             # e.g. 1.0    (needs a stop)
        time_stop_bars=None,             # e.g. 30     (hard exit N bars after entry)
        use_invalidation=True,           # exit when the signal stops being true
    ),

    sizing=SizingSpec(
        contracts=1,                     # fixed size; nothing adaptive
        max_contracts=None,
    ),

    risk=RiskSpec(
        max_open_positions=1,            # the engine simulates ONE; anything else is refused
        cooldown_bars=0,                 # bars after an exit before re-entry is allowed
        max_trades_per_session=None,     # e.g. 3
    ),

    cost=CostSpec(
        commission_round_turn=None,      # None = the repository's measured commission
        slippage_ticks=0.0,              # the execution ladder adds its own on top of this
        include_spread=True,
    ),

    params=PARAMS,
    rationale=(
        "State the MECHANISM in one or two sentences: what is supposed to make this work, "
        "and who is on the other side of the trade. This is recorded, never parsed - but a "
        "rule with no statable mechanism is the one most likely to be curve fit."),
    notes={},
)
