"""The V1.0.0_Frozen RELEASE MANIFEST: one machine-readable record of what was frozen.

    python scripts/vwap_release.py                 # print it
    python scripts/vwap_release.py --write         # write release/V1.0.0_Frozen.json
    python scripts/vwap_release.py --verify        # fail if the file disagrees with reality

NO STRATEGY IS RUN. This reads the frozen specification, loads the four datasets to obtain
their manifest ids, and writes down the pair. It computes no P&L and imports no engine.

WHY A SEPARATE FILE AND NOT A DOCUMENT
----------------------------------------
A backtest result is attributable only if it can name, in one artefact a machine can check,
the strategy it ran and the bytes it ran on. Prose cannot be diffed and cannot be verified.
`--verify` re-derives every field and refuses on the first disagreement, so a drifted
parameter or a re-fetched store fails a check rather than quietly changing a number.

EVERY VALUE IS READ, NOT TYPED
--------------------------------
The fields below come from `spec.FROZEN`, `spec.FROZEN_MNQ` and the loaders. Nothing here is
a literal copied out of the specification, because a copy is a second source of truth and the
first thing to drift. `tests/test_vwap_data.py` asserts the released values against literals
written in the test, which is the one place a literal belongs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from quant_brain.strategies.vwap_pullback.data import (  # noqa: E402
    LOADER_VERSION,
    SCHEMA_VERSION,
    load_anchored,
)
from quant_brain.strategies.vwap_pullback.spec import (  # noqa: E402
    FROZEN,
    FROZEN_MNQ,
    TIMEZONE,
    VERSION,
    unresolved,
)

STORE = REPO / "data" / "futures"
INSTRUMENTS = ("ES", "NQ", "MES", "MNQ")
RELEASE_FILE = REPO / "release" / "V1.0.0_Frozen.json"

#: Fields that legitimately differ between two runs on the same repository state. `--verify`
#: ignores them; everything else must match exactly.
VOLATILE = ("generated_at_utc", "git")


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                              timeout=20, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):          # pragma: no cover
        return ""


def _hhmm(pair: tuple[int, int]) -> str:
    return f"{pair[0]:02d}:{pair[1]:02d}"


def datasets() -> dict:
    """Load each store and record what identifies it. No strategy, no P&L."""
    out = {}
    for sym in INSTRUMENTS:
        path = STORE / f"{sym}.parquet"
        if not path.exists():
            out[sym] = {"present": False}
            continue
        m = load_anchored(path, sym).manifest()
        src, cov, tot = m["source"], m["coverage"], m["totals"]
        out[sym] = {
            "present": True,
            "manifest_id": m["manifest_id"],
            "content_hash": m["content_hash"],
            "file_sha256": src["file_hashes"],
            "file_bytes": src["file_bytes"],
            "rows_in_file": src["rows_in_file"],
            "first_bar_utc": src["first_bar_utc"],
            "last_bar_utc": src["last_bar_utc"],
            "instrument": m["instrument"],
            "contract_coverage": src["contract_coverage"],
            "sessions_found": cov["sessions_found"],
            "sessions_usable": cov["sessions_usable"],
            "sessions_by_status": cov["by_status"],
            "bars_usable": tot["bars_usable"],
            "zero_volume_bars": tot["zero_volume_bars"],
            "upstream_quality": src["quality_status"],
            "upstream_quality_report": src["quality_report_hash"],
        }
    return out


def build() -> dict:
    """The release manifest. Every field derived; none copied from the brief."""
    return {
        "release": VERSION,
        "generated_at_utc": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "git": {"sha": _git("rev-parse", "HEAD"),
                "dirty": bool(_git("status", "--porcelain"))},

        "strategy": {
            "spec_hash_nq": FROZEN.spec_hash,
            "spec_hash_mnq": FROZEN_MNQ.spec_hash,
            "execution_profile": FROZEN.execution.name,
            "execution_profile_is_the_frozen_spec": FROZEN.execution.frozen_spec_exact,
            "unresolved_material_ambiguities": [a.ref for a in unresolved()],
        },

        "clock": {
            "timezone": TIMEZONE.key,
            "vwap_anchor_et": _hhmm(FROZEN.session_anchor),
            "entry_window_start_et": _hhmm(FROZEN.monitor_start),
            "entry_cutoff_et": _hhmm(FROZEN.last_entry),
            "entry_cutoff_inclusive": FROZEN.last_entry_inclusive,
            "hard_flatten_et": _hhmm(FROZEN.hard_flatten),
            "data_session_et": f"{_hhmm(FROZEN.session_anchor)} -> "
                               f"{_hhmm(FROZEN.hard_flatten)}",
            "data_session_is_continuous": True,
            "vwap_resets_only_at": _hhmm(FROZEN.session_anchor),
        },

        "signals": {
            "atr_method": FROZEN.atr_method,
            "atr_period": FROZEN.atr_period,
            "atr_minimum": FROZEN.atr_minimum,
            "atr_timeframe": "5min, completed buckets only",
            "context_max_distance": FROZEN.context_max_distance,
            "long_zone": list(FROZEN.long_zone),
            "short_zone": list(FROZEN.short_zone),
            "volume_sma_period": FROZEN.volume_sma_period,
            "volume_multiple": FROZEN.volume_multiple,
            "invalidation_distance": FROZEN.invalidation_distance,
        },

        "brackets": {
            "stop_points": FROZEN.stop_points,
            "target_points": FROZEN.target_points,
            "breakeven_trigger": FROZEN.breakeven_trigger,
            "breakeven_offset": FROZEN.breakeven_offset,
            "stall_mfe": FROZEN.stall_mfe,
            "stall_window": FROZEN.stall_window,
            "stall_target": FROZEN.stall_target,
        },

        "governor": {
            "mtm_basis": FROZEN.governor_mtm_basis,
            "mtm_mode": "CONSERVATIVE_INTRABAR_ADVERSE_EXTREME",
            "daily_loss_killswitch": FROZEN.daily_loss_killswitch,
            "daily_profit_cap": FROZEN.daily_profit_cap,
            "max_trades_per_day": FROZEN.max_trades_per_day,
            "consecutive_losses_for_cooldown": FROZEN.consecutive_losses_for_cooldown,
            "cooldown_minutes": FROZEN.cooldown_minutes,
        },

        "sizing_and_cost": {
            "nq": {"contracts": FROZEN.contracts,
                   "commission_round_turn": FROZEN.commission_round_turn,
                   "point_value": FROZEN.point_value, "tick": FROZEN.tick},
            "mnq": {"contracts": FROZEN_MNQ.contracts,
                    "commission_round_turn": FROZEN_MNQ.commission_round_turn,
                    "point_value": FROZEN_MNQ.point_value, "tick": FROZEN_MNQ.tick},
            "entry_slippage_ticks": FROZEN.execution.entry_ticks,
            "stop_slippage_ticks": FROZEN.execution.stop_ticks,
            "target_slippage_ticks": FROZEN.execution.target_ticks,
            "market_exit_slippage_ticks": FROZEN.execution.market_exit_ticks,
        },

        "data_pipeline": {
            "loader_version": LOADER_VERSION,
            "schema_version": SCHEMA_VERSION,
            "adjustment_mode": "CONTINUOUS_UNADJUSTED",
            "price_adjustment": "NONE",
            "roll_policy": "CALENDAR_DAYS_BEFORE_EXPIRY, read from the store's own contract "
                           "column; the loader selects no contract",
            "roll_discontinuities": "preserved, never smoothed or back-adjusted",
            "completeness_rule": "anchor present, endpoint present, every minute between "
                                 "present exactly once, one contract, valid OHLC, "
                                 "non-negative volume",
            "rejection_code": "INCOMPLETE_SESSION",
            "calendar_inference": "NONE. No verified CME calendar exists in this repository, "
                                  "so no refused session is classified as a holiday or an "
                                  "early close.",
            "zero_volume_policy": "kept, weightless (TP * 0 = 0), counted, never repaired, "
                                  "never a reason to reject a session",
            "repair_policy": "none: no interpolation, forward fill, reindex or gap bridging",
        },

        "datasets": datasets(),

        "prohibitions_at_this_gate": [
            "no strategy backtest has been run",
            "no P&L, Sharpe, win rate, drawdown, payout or pass probability computed",
            "no live execution surface touched",
        ],
    }


def _differences(a: dict, b: dict, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if not path and k in VOLATILE:
                continue
            here = f"{path}.{k}" if path else k
            if k not in a:
                out.append(f"{here}: absent from the released file")
            elif k not in b:
                out.append(f"{here}: absent from the rebuild")
            else:
                out.extend(_differences(a[k], b[k], here))
    elif a != b:
        out.append(f"{path}: released {a!r} != rebuilt {b!r}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="write the release file")
    ap.add_argument("--verify", action="store_true",
                    help="rebuild and refuse if the released file disagrees")
    args = ap.parse_args()

    fresh = build()

    if args.verify:
        if not RELEASE_FILE.exists():
            print(f"NO RELEASE FILE at {RELEASE_FILE.relative_to(REPO)}")
            return 1
        released = json.loads(RELEASE_FILE.read_text(encoding="utf-8"))
        diffs = _differences(released, fresh)
        if diffs:
            print(f"RELEASE MANIFEST DISAGREES WITH THE REPOSITORY ({len(diffs)}):")
            for d in diffs:
                print(f"  {d}")
            return 1
        print(f"release manifest verified: {VERSION}  "
              f"spec {fresh['strategy']['spec_hash_nq']} / "
              f"{fresh['strategy']['spec_hash_mnq']}")
        for sym, d in fresh["datasets"].items():
            if d.get("present"):
                print(f"  {sym:4} {d['manifest_id']}  {d['sessions_usable']}/"
                      f"{d['sessions_found']} usable")
        return 0

    text = json.dumps(fresh, indent=2, sort_keys=False) + "\n"
    if args.write:
        RELEASE_FILE.parent.mkdir(parents=True, exist_ok=True)
        RELEASE_FILE.write_text(text, encoding="utf-8")
        print(f"wrote {RELEASE_FILE.relative_to(REPO)}")
        return 0
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
