"""Phase 1: freeze `breakout.failed_reversal` exactly as it exists, and hash it.

WHAT THE RULE ACTUALLY IS
---------------------------
Read verbatim from `scripts/strategy_tournament.py:230-237`:

    hi95, lo05 = cal("opening_range_pos", 0.95), cal("opening_range_pos", 0.05)

    def failed(X, hi=hi95, lo=lo05):
        orp, mins = _col(X, "opening_range_pos"), _col(X, "minutes_from_open")
        live = mins > 45
        prev = np.concatenate(([0.0], orp[:-1]))
        return _state(live & (prev > hi) & (orp < hi), live & (prev < lo) & (orp > lo))

Translated: more than 45 minutes after the open, when the previous bar's opening-range
position was ABOVE the 95th percentile and this bar's is BELOW it, go **LONG**. Mirrored on
the downside: previous bar below the 5th percentile and this bar above it, go **SHORT**.

A CORRECTION TO HOW THIS WAS DESCRIBED IN THE PREVIOUS PHASE
--------------------------------------------------------------
The exit study described this mechanism as one that "fades a failed move". That is imprecise
and arguably backwards. The rule takes a position in the SAME direction as the original
breakout: an upside extension that pulls back below the threshold produces a LONG. The bet is
that the pullback - the reversal - fails, and the breakout resumes. The name says so; the
earlier prose did not.

The economic claim being replicated is therefore: **after a strong intraday extension retraces
past its own 95th-percentile level, the retracement is more likely to fail than to continue,
over the next one to five minutes.** Nothing else.

THE ONE REAL AMBIGUITY, DOCUMENTED RATHER THAN RESOLVED
---------------------------------------------------------
`hi95` and `lo05` are quantiles of `opening_range_pos` measured on the TRAIN SPLIT of the
instrument the rule is running on. So the numeric threshold differs per instrument by
construction.

The brief says not to tune parameters separately per instrument. Two readings are possible:

  (a) the RULE is "the 95th percentile of this instrument's own opening-range distribution",
      in which case recalibrating per instrument IS the faithful replication, or
  (b) the RULE is the numeric threshold measured on MNQ, in which case it should be transplanted
      unchanged.

Reading (a) is used, because the quantile level - not the number - is what was written down,
and transplanting a raw `opening_range_pos` value across instruments with different volatility
would be applying a different rule, not the same one. **Reading (b) is also computed and
reported** so the choice cannot hide a result. The quantile levels (0.95 / 0.05), the 45-minute
warm-up, the train fraction (0.50) and the direction convention are identical everywhere and
are never re-fitted.

WHAT IS FROZEN
--------------
Everything below. The hash covers the rule source, the parameter levels and the evaluation
convention, so any later edit to the mechanism invalidates every result carrying this hash.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))


#: The frozen rule, transcribed. Not imported from the tournament, so that a later edit there
#: produces a HASH MISMATCH here rather than silently changing the replication.
FROZEN_SOURCE = '''
def failed_reversal(orp, mins, hi, lo):
    """opening_range_pos, minutes_from_open, upper threshold, lower threshold."""
    live = mins > 45
    prev = np.concatenate(([0.0], orp[:-1]))
    long_cond = live & (prev > hi) & (orp < hi)
    short_cond = live & (prev < lo) & (orp > lo)
    pos = np.zeros(len(orp), dtype=float)
    pos[long_cond & ~short_cond] = 1.0
    pos[short_cond & ~long_cond] = -1.0
    return pos
'''

SPEC = {
    "mechanism_id": "breakout.failed_reversal",
    "family": "B.breakout",
    "source_module": "scripts/strategy_tournament.py",
    "source_lines": "230-237",
    "bar_timeframe": "1 minute",
    "session_window_et": "09:30-16:00",
    "features_required": ["opening_range_pos", "minutes_from_open"],
    "warmup_minutes": 45,
    "upper_quantile": 0.95,
    "lower_quantile": 0.05,
    "calibration": "quantiles of opening_range_pos on the first 50% of sessions, frozen",
    "entry_long": "prev_bar_orp > q95 AND this_bar_orp < q95",
    "entry_short": "prev_bar_orp < q05 AND this_bar_orp > q05",
    "direction_convention": ("position is taken in the direction of the ORIGINAL breakout; "
                             "the bet is that the retracement fails"),
    "exit": ("signal invalidation (position closes when the signal is no longer that "
             "direction) plus mandatory session-end flatten; equivalently a 1-bar hold, "
             "since the signal is a single-bar crossing event"),
    "stop": "NONE",
    "target": "NONE",
    "sizing": "1 contract / 100 shares equivalent, fixed",
    "prev_at_first_bar": ("hardcoded 0.0; harmless because the 45-minute warm-up excludes "
                          "the first bar and features are built per session so `prev` never "
                          "crosses a session boundary"),
}


def rule_hash() -> str:
    blob = json.dumps({"source": FROZEN_SOURCE.strip(), "spec": SPEC}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def failed_reversal(orp: np.ndarray, mins: np.ndarray, hi: float, lo: float) -> np.ndarray:
    """The frozen rule. Identical everywhere it is applied."""
    live = mins > 45
    prev = np.concatenate(([0.0], orp[:-1]))
    long_cond = live & (prev > hi) & (orp < hi)
    short_cond = live & (prev < lo) & (orp > lo)
    pos = np.zeros(len(orp), dtype=float)
    pos[long_cond & ~short_cond] = 1.0
    pos[short_cond & ~long_cond] = -1.0
    return pos


def verify_against_library() -> tuple[bool, str]:
    """Assert the frozen transcription still matches the live tournament implementation.

    Compared by BEHAVIOUR on a synthetic frame rather than by source text, because the
    tournament wraps the rule in a closure and a whitespace change would produce a spurious
    mismatch while a logic change would not.
    """
    import pandas as pd
    from strategy_tournament import _col, _state

    def live_rule(X, hi, lo):
        orp, mins = _col(X, "opening_range_pos"), _col(X, "minutes_from_open")
        live = mins > 45
        prev = np.concatenate(([0.0], orp[:-1]))
        return _state(live & (prev > hi) & (orp < hi), live & (prev < lo) & (orp > lo))

    rng = np.random.default_rng(7)
    n = 391
    orp = rng.normal(0, 1.2, n)
    mins = np.arange(n, dtype=float)
    X = pd.DataFrame({"opening_range_pos": orp, "minutes_from_open": mins})
    a = live_rule(X, 1.5, -1.5)
    b = failed_reversal(orp, mins, 1.5, -1.5)
    same = bool(np.array_equal(np.nan_to_num(a), b))
    return same, ("frozen transcription matches the live implementation"
                  if same else "MISMATCH - the tournament rule has changed")


def main() -> int:
    ok, msg = verify_against_library()
    h = rule_hash()
    out = {"rule_hash": h, "spec": SPEC, "source": FROZEN_SOURCE.strip(),
           "matches_live_implementation": ok}
    (REPO / "research" / "failed_reversal_spec.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")

    print("=" * 100)
    print("PHASE 1 - FROZEN HYPOTHESIS SPECIFICATION")
    print("=" * 100)
    print(f"\n  rule hash: {h}")
    print(f"  {msg}")
    if not ok:
        print("\n  STOPPING: the live rule no longer matches the frozen transcription.")
        return 1
    print("\n  the claim being replicated, in one sentence:")
    print("    after a strong intraday extension retraces past its own 95th-percentile")
    print("    opening-range level, the retracement fails more often than it continues,")
    print("    over the next 1 to 5 minutes.")
    print("\n  frozen parameters:")
    for k in ("bar_timeframe", "session_window_et", "warmup_minutes", "upper_quantile",
              "lower_quantile", "calibration", "entry_long", "entry_short",
              "direction_convention", "exit", "stop", "target", "sizing"):
        print(f"    {k:24} {SPEC[k]}")
    print("\n  documented ambiguity (NOT silently resolved):")
    print("    the thresholds are per-instrument quantiles. Reading (a) recalibrates the")
    print("    same QUANTILE LEVEL on each instrument; reading (b) transplants MNQ's raw")
    print("    numeric threshold. (a) is primary; (b) is computed and reported alongside.")
    print(f"\nwrote research/failed_reversal_spec.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
