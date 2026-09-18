"""Prove, or disprove, that this repository holds tick-level order-flow data.

    python -m topstep_backtester.scripts.survey_tick_data
    python topstep_backtester/scripts/survey_tick_data.py --root data --json out.json

WHY THIS IS A COMMITTED SCRIPT AND NOT A ONE-OFF
------------------------------------------------
"CVD_ABSORPTION_HARVESTER is blocked because we have no tick data" is the load-bearing
claim of that strategy's report. A claim like that has to be re-runnable by someone who
doubts it, on a store that will have grown by then, without taking anyone's word for which
files were checked.

WHAT IT TESTS, AND WHY NOT BY FILENAME
--------------------------------------
Two properties, on every parquet file found:

  GRANULARITY  the smallest positive gap between consecutive timestamps, and how many
               records share a stamp. A real trade feed prints in bursts inside a single
               millisecond; a resampled grid has a fixed modal gap and no ties at all.
  COLUMNS      per-trade classification needs a trade price, a trade size, and the bid and
               ask standing at that trade. One bid and one ask per minute cannot say how
               many of that minute's contracts traded at the offer.

Filenames are ignored on purpose. This store contains files called ``ES_..._BID_ASK_...``
and ``MES_..._TRADES_...`` which are IBKR historical BAR requests, not time and sales - the
names promise order flow the contents do not carry, which is exactly the trap a
name-matching survey walks into.

THE PANDAS TRAP THIS SCRIPT ITSELF FELL INTO
--------------------------------------------
The first version computed gaps with ``stamps.astype("int64")``. On pandas 3.0 the canonical
columns are ``datetime64[us]``, and ``astype`` returns the column's OWN unit - so a
60-second bar grid reported a modal gap of 0.06 seconds and the store looked like a tick
feed. Converting with ``.dt.as_unit("ns")`` first is not a stylistic preference here; it is
the difference between this script's answer being right and being off by a factor of a
thousand in the direction that would have unblocked a backtest it should have blocked.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

if __package__ in (None, ""):  # pragma: no cover - direct `python path/to/script.py`
    #: Run as a file rather than with -m, so the repository root is not on sys.path yet.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from topstep_backtester.strategies.cvd_absorption_harvester.tick_schema import (
    MAX_USABLE_GAP_SECONDS,
    REQUIRED_TICK_FIELDS,
    check_frame,
)

#: Columns that would indicate per-trade records rather than aggregates.
TRADE_LEVEL_HINTS = frozenset(
    {
        "size", "trade_size", "last_size", "qty", "quantity",
        "side", "aggressor", "aggressor_side", "taker_side",
        "trade_id", "seq", "sequence", "tick_type", "cond", "condition",
        "bid_size", "ask_size", "bid_sz", "ask_sz",
    }
)
QUOTE_HINTS = frozenset({"bid", "ask", "bid_price", "ask_price", "bid_px", "ask_px"})
TIME_HINTS = ("t", "timestamp", "time", "ts", "datetime", "date", "dt")


def _time_column(names: list[str]) -> str | None:
    for candidate in TIME_HINTS:
        if candidate in names:
            return candidate
    for name in names:
        lowered = name.lower()
        if "time" in lowered or lowered.startswith("ts"):
            return name
    return None


def _stamps(path: Path, column: str) -> pd.Series | None:
    """Read just the time column, tolerating files that carry it as an index level."""
    try:
        frame = pd.read_parquet(path, columns=[column])
    except Exception:
        try:
            frame = pd.read_parquet(path)
        except Exception:
            return None
    if column in frame.columns:
        raw = frame[column]
    elif frame.index.nlevels:
        raw = pd.Series(frame.index.get_level_values(0))
    else:
        return None
    return pd.to_datetime(raw, errors="coerce").dropna()


def survey_file(path: Path) -> dict[str, Any]:
    handle = pq.ParquetFile(path)
    names = list(handle.schema_arrow.names)
    lowered = {n.lower() for n in names}
    record: dict[str, Any] = {
        "path": path.as_posix(),
        "rows": handle.metadata.num_rows,
        "columns": names,
        "trade_level_columns": sorted(lowered & TRADE_LEVEL_HINTS),
        "quote_columns": sorted(lowered & QUOTE_HINTS),
        "min_gap_seconds": None,
        "modal_gap_seconds": None,
        "simultaneous_stamps": 0,
        "missing_required_fields": sorted(REQUIRED_TICK_FIELDS),
        "tick_like": False,
    }

    column = _time_column(names)
    if column is None or record["rows"] < 3:
        return record
    stamps = _stamps(path, column)
    if stamps is None or len(stamps) < 3:
        return record

    #: as_unit("ns") FIRST - see the module docstring. Without it a 60s grid reads as 0.06s.
    ordered = stamps.sort_values().dt.as_unit("ns").astype("int64").to_numpy()
    gaps = np.diff(ordered) / 1e9
    positive = gaps[gaps > 0]
    record["simultaneous_stamps"] = int((gaps == 0).sum())
    if positive.size:
        record["min_gap_seconds"] = float(positive.min())
        record["modal_gap_seconds"] = float(pd.Series(positive).mode().iloc[0])

    #: Granularity alone is not enough. Apply the FULL tick contract - a file can be
    #: sub-second and still be useless if it carries no trade price or size, which is
    #: exactly what the one sub-second file in this store turned out to be.
    verdict = check_frame(pd.read_parquet(path).head(5000), source=path.as_posix())
    record["missing_required_fields"] = list(verdict.missing_fields)

    minimum = record["min_gap_seconds"]
    record["tick_like"] = bool(
        minimum is not None
        and minimum <= MAX_USABLE_GAP_SECONDS
        and record["simultaneous_stamps"] > 0
        and not verdict.missing_fields
    )
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="data", help="directory to scan (default: data)")
    parser.add_argument("--json", default="", help="write the full per-file survey here")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.exists():
        print(f"{root}/ does not exist", file=sys.stderr)
        return 2

    files = sorted(root.rglob("*.parquet"))
    print(f"scanning {len(files)} parquet files under {root}/\n")

    records: list[dict[str, Any]] = []
    grid: Counter[str] = Counter()
    unreadable: list[str] = []
    total_rows = 0

    for path in files:
        try:
            record = survey_file(path)
        except Exception as exc:  # pragma: no cover - a corrupt file is itself a finding
            unreadable.append(f"{path.as_posix()}: {type(exc).__name__}: {exc}")
            continue
        records.append(record)
        total_rows += record["rows"]
        modal = record["modal_gap_seconds"]
        if modal is None:
            grid["no usable time column"] += 1
        elif modal == 60.0:
            grid["1-minute bars"] += 1
        elif modal == 1.0:
            grid["1-second bars"] += 1
        elif modal == 86400.0:
            grid["daily bars"] += 1
        elif modal < 1.0:
            grid["sub-second"] += 1
        else:
            grid[f"{modal:g}s grid"] += 1

    print("GRANULARITY")
    for label, count in grid.most_common():
        print(f"  {count:5d} files   {label}")
    print(f"\n  {total_rows:,} rows across {len(records)} readable files")

    tick_like = [r for r in records if r["tick_like"]]
    quotes = [r for r in records if r["quote_columns"]]
    per_trade = [r for r in records if r["trade_level_columns"]]

    print(f"\nFILES THAT LOOK LIKE A TRADE SEQUENCE "
          f"(gap <= {MAX_USABLE_GAP_SECONDS}s AND tied stamps): {len(tick_like)}")
    for record in tick_like[:20]:
        print(f"  {record['path']}  {record['rows']:,} rows  "
              f"min gap {record['min_gap_seconds']}s  "
              f"ties {record['simultaneous_stamps']}  {record['columns']}")

    near_miss = [
        r for r in records
        if r["min_gap_seconds"] is not None
        and r["min_gap_seconds"] <= MAX_USABLE_GAP_SECONDS
        and r["missing_required_fields"]
    ]
    if near_miss:
        print(f"\nsub-second files REJECTED on missing required fields: {len(near_miss)}")
        for record in near_miss[:10]:
            print(f"  {record['path']}  missing {record['missing_required_fields']}")

    print(f"\nfiles carrying a bid/ask column:        {len(quotes)}")
    print(f"files carrying per-trade columns:       {len(per_trade)}")
    if unreadable:
        print(f"\nunreadable: {len(unreadable)}")
        for line in unreadable[:5]:
            print(f"  {line}")

    if args.json:
        Path(args.json).write_text(json.dumps(records, indent=1), encoding="utf-8")
        print(f"\nfull per-file survey written to {args.json}")

    print("\n" + "=" * 70)
    if tick_like:
        print("TICK-LEVEL ORDER FLOW: FOUND - these files satisfy the full contract "
              "(trade price, size, bid, ask, sub-second, tied stamps)")
        return 0
    print("TICK-LEVEL ORDER FLOW: NONE FOUND")
    print("CVD cannot be computed. Do not approximate it from OHLCV - see PART 2 of the")
    print("brief and topstep_backtester/docs/CVD_ABSORPTION_HARVESTER_XFA_V2.0_REPORT.md.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
