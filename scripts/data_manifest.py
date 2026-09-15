"""Canonicalise every dataset on disk, gate it, and write its manifest.

    python scripts/data_manifest.py --scan            # report, write nothing
    python scripts/data_manifest.py --write           # write data/manifests/*.json
    python scripts/data_manifest.py --cross-source    # compare feeds for one underlying
    python scripts/data_manifest.py --benchmark       # runtime, memory, throughput

WHY A SCRIPT AND NOT A DOCUMENT
---------------------------------
A manifest that a human writes is a manifest that drifts from the file it describes. Every
field here is derived from the bytes on disk or from the adapter that knows how they were
fetched, so re-running this after a re-fetch produces a manifest that matches - and a
manifest whose `manifest_id` has changed is a dataset whose representation has changed,
which is precisely the signal the old data path could not give.

This script reads. It never writes into `data/`, never re-fetches, and never repairs.
"""
from __future__ import annotations

import argparse
import gc
import sys
import time
import tracemalloc
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from quant_brain.data import cross_source as X          # noqa: E402
from quant_brain.data import loader as L                # noqa: E402
from quant_brain.data import quality as Q               # noqa: E402
from quant_brain.data import rolls as R                 # noqa: E402

MANIFEST_DIR = REPO / "data" / "manifests"

#: Every dataset this repository holds, with the adapter that knows how to read it. A store
#: absent from this table is a store nothing canonical can load - which is the point: a new
#: provider gets an adapter and an entry here, not a guess at its columns.
DATASETS: list[tuple[str, str, dict]] = [
    *[(f"data/futures/{s}.parquet", "ibkr_futures", {"instrument": s})
      for s in ("ES", "NQ", "MES", "MNQ")],
    *[(f"data/minute_alpaca/{s}.parquet", "alpaca_equity_minute", {"symbol": s})
      for s in ("SPY", "QQQ", "IWM", "DIA")],
]


def scan(write: bool) -> int:
    rows, worst = [], 0
    for rel, adapter, kw in DATASETS:
        path = REPO / rel
        if not path.exists():
            print(f"  {'MISSING':8} {rel}")
            continue
        try:
            ds = L.load(adapter, path, require_quality=False, **kw)
        except Exception as exc:                                  # noqa: BLE001
            print(f"  {'REFUSED':8} {rel}: {type(exc).__name__}: {str(exc)[:90]}")
            worst = max(worst, 2)
            continue
        m = ds.manifest
        print(f"\n  {m.quality.status:8} {ds.summary()}")
        for f in ds.report.of(Q.Level.FAIL):
            print(f"           FAIL {f.check}: {f.detail[:100]}")
        for f in ds.report.of(Q.Level.WARN):
            print(f"           WARN {f.check}: {f.detail[:100]}")
        if m.roll.roll_timestamps:
            ev = R.detect_rolls(ds.frame)
            gaps = ", ".join(f"{e.gap_pct:+.3f}%" for e in ev)
            print(f"           rolls {len(ev)}: {gaps}")
        if m.notes:
            for n in m.notes:
                print(f"           note: {n[:110]}")
        worst = max(worst, {"PASS": 0, "WARN": 1, "FAIL": 2}[m.quality.status])
        rows.append(ds)
        if write:
            out = MANIFEST_DIR / f"{m.dataset_id}.json"
            m.write(out)
            print(f"           wrote {out.relative_to(REPO)}")
    print(f"\n  {len(rows)} dataset(s) canonicalised; worst status "
          f"{['PASS', 'WARN', 'FAIL'][worst]}")
    return 0 if worst < 2 else 1


def cross() -> int:
    """Compare feeds that should describe the same underlying. Never ranks them."""
    pairs = [("ES", "MES"), ("NQ", "MNQ")]
    for a, b in pairs:
        pa, pb = REPO / f"data/futures/{a}.parquet", REPO / f"data/futures/{b}.parquet"
        if not (pa.exists() and pb.exists()):
            continue
        da = L.load("ibkr_futures", pa, require_quality=False, instrument=a)
        db = L.load("ibkr_futures", pb, require_quality=False, instrument=b)
        print()
        print(X.compare(da.frame, db.frame, left_id=f"ibkr-{a}",
                        right_id=f"ibkr-{b}").render())
    print("\n  NOTE: this comparison measures AGREEMENT. It deliberately does not rank the "
          "feeds,\n  and there is no code path that picks a source by strategy outcome.")
    return 0


def benchmark() -> int:
    """Section 18. Correctness is not traded for speed; the numbers are recorded.

    Timing and memory are measured in SEPARATE passes. `tracemalloc` inflates wall time by
    roughly 15x on this workload - reporting one number measured under it would understate
    the engine's speed by more than an order of magnitude and would be the kind of figure
    nobody can reproduce.
    """
    print(f"  {'dataset':28} {'MB disk':>8} {'bars':>10} {'load s':>7} {'bars/s':>10} "
          f"{'stream s':>9} {'frame MB':>9} {'peak MB':>8}")
    for rel, adapter, kw in DATASETS:
        path = REPO / rel
        if not path.exists():
            continue
        size = path.stat().st_size / 1e6

        # pass 1: wall time, no profiler attached
        gc.collect()
        t0 = time.perf_counter()
        ds = L.load(adapter, path, require_quality=False, **kw)
        load_s = time.perf_counter() - t0

        t0 = time.perf_counter()
        n = sum(1 for _ in ds.sessions())    # streamed; never a list of session frames
        stream_s = time.perf_counter() - t0
        frame_mb = ds.frame.memory_usage(deep=True).sum() / 1e6
        bars = ds.manifest.bars
        name = ds.manifest.dataset_id
        del ds
        gc.collect()

        # pass 2: peak allocation, timing discarded
        tracemalloc.start()
        ds = L.load(adapter, path, require_quality=False, **kw)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        del ds
        gc.collect()

        print(f"  {name:28} {size:8.1f} {bars:10,} {load_s:7.2f} "
              f"{bars / max(load_s, 1e-9):10,.0f} {stream_s:9.2f} {frame_mb:9.1f} "
              f"{peak / 1e6:8.0f}   ({n} sessions)")
    print("\n  `load s` includes the adapter, schema validation AND the full quality gate.")
    print("  `stream s` iterates every session without materialising a list of frames -")
    print("  the whole store never has to be held as N separate DataFrames.")
    print("  `peak MB` is from a separate tracemalloc pass; its timing is discarded.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--cross-source", action="store_true")
    ap.add_argument("--benchmark", action="store_true")
    args = ap.parse_args()
    if not any((args.scan, args.write, args.cross_source, args.benchmark)):
        args.scan = True

    rc = 0
    if args.scan or args.write:
        print("=" * 100)
        print("CANONICAL DATASETS")
        print("=" * 100)
        rc |= scan(write=args.write)
    if args.cross_source:
        print("\n" + "=" * 100)
        print("CROSS-SOURCE AGREEMENT")
        print("=" * 100)
        rc |= cross()
    if args.benchmark:
        print("\n" + "=" * 100)
        print("PERFORMANCE")
        print("=" * 100)
        rc |= benchmark()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
