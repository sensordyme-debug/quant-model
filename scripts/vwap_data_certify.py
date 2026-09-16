"""The authoritative census of the 18:00-anchored data path. DATA ONLY - no strategy is run.

    python scripts/vwap_data_certify.py                 # every instrument, the summary
    python scripts/vwap_data_certify.py --instrument ES --rejected
    python scripts/vwap_data_certify.py --instrument ES --manifest > es_manifest.json

This script loads bars, cuts sessions, measures them and prints what it found. It computes no
P&L, no Sharpe, no win rate and no drawdown, and it does not import the strategy engine. The
question it answers is the one PHASE 2 asks: which sessions are complete enough that the
frozen specification is even defined on them, and exactly why each of the rest is not.

WHAT "USABLE" MEANS, AND WHY IT IS NOT A PERCENTAGE
----------------------------------------------------
A session is usable only when the 18:00 anchor is present, the 15:45 flatten is present,
every minute between them is present exactly once and one contract covers all of them. A
percentage rule would accept NQ 2025-06-10, which is 1,305 of 1,306 bars - 99.92% - and
missing only the anchor itself, so its VWAP would start at 18:01 against a series the
specification never defined.

The manifest this prints is the provenance a backtest must quote. A result that cannot name
the manifest id it ran on is a number nobody can reproduce.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from quant_brain.strategies.vwap_pullback.data import (  # noqa: E402
    LOADER_VERSION,
    SessionStatus,
    load_anchored,
)
from quant_brain.strategies.vwap_pullback.spec import FROZEN, TIMEZONE, VERSION  # noqa: E402

STORE = REPO / "data" / "futures"
INSTRUMENTS = ("ES", "NQ", "MES", "MNQ")


def report(symbol: str, *, show_rejected: bool) -> dict:
    ds = load_anchored(STORE / f"{symbol}.parquet", symbol)
    m = ds.manifest()
    c, t = m["coverage"], m["totals"]

    print(f"\n{'=' * 96}")
    print(f"{symbol}   {c['first_trading_day']} .. {c['last_trading_day']}   "
          f"manifest {m['manifest_id']}   content {m['content_hash']}")
    print("=" * 96)
    print(f"  anchored sessions found      {c['sessions_found']}")
    print(f"  USABLE                       {c['sessions_usable']}")
    for status in SessionStatus:
        n = c["by_status"].get(status.value, 0)
        if n:
            fate = "fed to the strategy" if status.usable else "refused"
            print(f"    {status.value:16} {n:>4}   {fate}")
    print(f"  bars in usable sessions      {t['bars_usable']:,}"
          f"   ({t['overnight_bars_usable']:,} overnight + {t['rth_bars_usable']:,} RTH)")
    print(f"  bars absent, all sessions    {t['missing_bars_all_sessions']:,}")
    print(f"  duplicate timestamps         {t['duplicate_timestamps']}")
    print(f"  impossible bars              {t['invalid_bars']}")
    print(f"  zero-volume bars             {t['zero_volume_bars']:,}")
    print(f"  price representation         {m['adjustment_mode']} / "
          f"adjustment {m['roll_adjustment']}")
    print(f"  roll rule                    {m['roll_method']}, "
          f"{m['roll_days_before_expiry']} days before expiry")
    print(f"  upstream quality             {m['source']['quality_status']} "
          f"(report {m['source']['quality_report_hash']})")

    if m["rolls"]:
        print("\n  ROLLS - preserved, never adjusted")
        for r in m["rolls"]:
            where = {"AT_THE_ANCHOR": "opens a session - contaminates none",
                     "BETWEEN_SESSIONS": "in the 15:46-17:59 break - no session",
                     "INSIDE_A_SESSION": "INSIDE A SESSION"}[r["position"]]
            print(f"    {r['at_et']}  {r['previous_contract']} -> {r['new_contract']}  "
                  f"{r['price_difference']:+8.2f} ({r['price_difference_pct']:+.3f}%)  {where}")

    if show_rejected:
        print("\n  REFUSED SESSIONS")
        for s in ds.rejected():
            q = s.quality
            print(f"    {q.trading_day}  {q.status.value:14} {q.actual_bars:>5}/"
                  f"{q.expected_bars}  last bar {q.last_et}")
            for why in q.reasons:
                print(f"        {why}")
    return m


def perf(symbols) -> int:
    """Measure the loader: runtime, peak Python memory, throughput. Nothing is optimised.

    `tracemalloc` measures Python-level allocation, which is the number this loader can be
    held responsible for; the parquet reader's native buffers sit outside it, so treat the
    peak as a floor rather than as resident set size.
    """
    print("=" * 96)
    print("ANCHORED LOADER PERFORMANCE - no strategy was run")
    print("=" * 96)
    print(f"  {'store':5} {'rows':>10} {'sessions':>9} {'usable':>7} {'bars':>10} "
          f"{'seconds':>8} {'bars/sec':>10} {'peak MiB':>9}")
    for sym in symbols:
        path = STORE / f"{sym}.parquet"
        if not path.exists():
            continue
        #: TWO PASSES, because `tracemalloc` costs roughly 4x the runtime. Timing a traced
        #: run and reporting it as the loader's speed would overstate the cost by a factor
        #: nobody reading the number could see.
        t0 = time.perf_counter()
        ds = load_anchored(path, sym)
        elapsed = time.perf_counter() - t0

        tracemalloc.start()
        load_anchored(path, sym)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        bars = sum(len(s.bars) for s in ds.usable())
        rows = ds.source_manifest.bars
        print(f"  {sym:5} {rows:>10,} {len(ds.sessions):>9} {len(ds.usable()):>7} "
              f"{bars:>10,} {elapsed:>8.2f} {rows / elapsed:>10,.0f} "
              f"{peak / 1024 / 1024:>9.1f}")
    print()
    print("  Measured, not tuned. Time is from an UNTRACED run; peak memory is from a")
    print("  second, traced one, because tracemalloc costs about 4x the runtime. The peak")
    print("  is Python-level allocation only - the parquet reader's native buffers sit")
    print("  outside it - so read it as a floor, not as resident set size.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--instrument", choices=INSTRUMENTS, help="just this one")
    ap.add_argument("--rejected", action="store_true", help="list every refused session")
    ap.add_argument("--manifest", action="store_true",
                    help="emit the manifest as JSON and nothing else")
    ap.add_argument("--perf", action="store_true",
                    help="measure the loader instead of describing the data")
    args = ap.parse_args()

    symbols = (args.instrument,) if args.instrument else INSTRUMENTS

    if args.manifest:
        if not args.instrument:
            ap.error("--manifest needs --instrument: one manifest describes one dataset")
        ds = load_anchored(STORE / f"{args.instrument}.parquet", args.instrument)
        print(json.dumps(ds.manifest(), indent=1, default=str))
        return 0

    if args.perf:
        return perf(symbols)

    print("=" * 96)
    print("V1.0.0_FROZEN ANCHORED DATA CERTIFICATION - data only, no strategy was run")
    print("=" * 96)
    print(f"  strategy spec      {VERSION}  hash {FROZEN.spec_hash}")
    print(f"  loader             {LOADER_VERSION}")
    print(f"  session            18:00 ET (previous calendar day) -> 15:45 ET, one continuous "
          f"VWAP session")
    print(f"  clock              {TIMEZONE.key}; bar counts derived per session, never assumed")

    found = 0
    for sym in symbols:
        if not (STORE / f"{sym}.parquet").exists():
            print(f"\n  {sym}: NO STORE")
            continue
        report(sym, show_rejected=args.rejected)
        found += 1
    if not found:
        print("\n  no store found - nothing to certify")
        return 1
    print("\n" + "=" * 96)
    print("  No strategy was run. No P&L, Sharpe, win rate, drawdown or pass probability was")
    print("  computed. This is a statement about DATA and nothing else.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
