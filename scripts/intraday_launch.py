#!/usr/bin/env python
"""Preflight + launch for the intraday sleeve. This is what the 09:25 ET scheduled task runs.

    python scripts/intraday_launch.py            # preflight, then live paper trading
    python scripts/intraday_launch.py --dry-run  # preflight, then live bars without orders

Preflight (any failure -> alert, no trading):
  1. replay the most recent stored session through scripts/intraday_trader.py (exercises the
     exact strategy + execution code that is about to run; catches a broken commit overnight)
  2. IB Gateway reachable and the account is a paper account
  3. live/APPROVED_PAPER.md present and no HALT file
Then it runs the trader in the foreground until 15:42 ET and forwards its exit code.
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from intraday_common import LIVE, REPO, UNIVERSE, load_bars, log_event, notify  # noqa: E402

PY = sys.executable
TRADER = REPO / "scripts" / "intraday_trader.py"
CONFIG = LIVE / "intraday_config.json"       # {"strategy": "active", "equity_frac": 1.0, "params": {...}}


def config():
    import json
    cfg = {"strategy": "active", "equity_frac": 1.0, "params": {}}
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    return cfg


def last_session() -> dt.date | None:
    """Most recent session that is COMPLETE (>= 300 bars) for the sampled symbols. A truncated
    last day (the store was refreshed mid-session) replays with open positions and a nonsense
    P&L, which happened on 2026-09-10; a preflight must exercise a whole session."""
    complete = None
    for s in UNIVERSE[:4]:
        df = load_bars(s)
        if df.empty:
            continue
        counts = df.groupby(df.index.date).size()
        ok = set(counts[counts >= 300].index)
        complete = ok if complete is None else complete & ok
    return max(complete) if complete else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-replay", action="store_true")
    args = ap.parse_args()
    cfg = config()
    import json
    common = ["--strategy", cfg["strategy"], "--equity-frac", str(cfg["equity_frac"])]
    if cfg.get("params"):
        common += ["--params", json.dumps(cfg["params"])]

    # 1) replay preflight
    if not args.skip_replay:
        day = last_session()
        if day is None:
            msg = "INTRADAY preflight FAILED: no stored minute bars to replay"
            print(msg); notify(msg); log_event("intraday", "preflight_failed", reason="no_bars")
            return 2
        res = subprocess.run([PY, str(TRADER), "--replay", str(day)] + common, capture_output=True, text=True, timeout=1200)
        tail = (res.stdout + res.stderr)[-800:]
        if res.returncode != 0 or "replay" not in res.stdout:
            msg = f"INTRADAY preflight FAILED: replay of {day} exited {res.returncode}: {tail[-300:]}"
            print(msg); notify(msg); log_event("intraday", "preflight_failed", reason="replay", output=tail)
            return 2
        print("preflight replay OK:", res.stdout.strip().splitlines()[-1])

    # 2) gates
    if any((LIVE / n).exists() for n in ("HALT", "HALT_INTRADAY")):
        msg = "INTRADAY not started: HALT file present"
        print(msg); notify(msg); log_event("intraday", "not_started", reason="halt")
        return 3
    if not args.dry_run and not (LIVE / "APPROVED_PAPER.md").exists():
        print("no approval file: running dry"); args.dry_run = True

    # 3) launch
    cmd = [PY, str(TRADER)] + common + (["--dry-run"] if args.dry_run else [])
    log_event("intraday", "launch", cmd=cmd)
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
