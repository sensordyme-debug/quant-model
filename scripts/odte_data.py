"""0DTE option chain store for O-2.

Caches SPY same-day-expiry chains from the local Theta Terminal (see scripts/theta_data.py)
into data/options/odte/<SYMBOL>/<YYYY-MM-DD>.parquet, one file per expiration date, holding
bid/ask for both rights at a fixed interval over the regular session.

The store is deliberately narrow - strike, right, timestamp, bid, ask, bid_size, ask_size -
because the O-2 study prices fills at the quoted bid/ask and never at the mid, and needs
nothing else. Strikes are limited to a window around the money (`--range` in strikes).

    python scripts/odte_data.py --symbol SPY --start 2016-01-01 --end 2026-09-10
    python scripts/odte_data.py --status

Theta's STANDARD plan serves option quotes at intervals >= 1m back to 2012. A trading day with
no same-day expiration simply has no file: SPY expired weekly in 2016, twice a week from 2017,
three times from 2019 and every session from 2023-05, so the sample density is a fact of the
instrument, not of the store.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import theta_data as td  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "options" / "odte"
KEEP = ["strike", "right", "timestamp", "bid", "ask", "bid_size", "ask_size"]

_print_lock = threading.Lock()


def day_path(symbol: str, date: str) -> Path:
    return STORE / symbol.upper() / f"{date}.parquet"


def expiration_dates(symbol: str, start: str, end: str) -> list[str]:
    """Expirations that are themselves in [start, end] - i.e. every 0DTE session."""
    exps = pd.Series(pd.to_datetime(td.expirations(symbol)))
    exps = exps[(exps >= pd.Timestamp(start)) & (exps <= pd.Timestamp(end))]
    return [str(x.date()) for x in sorted(exps)]


def fetch_day(symbol: str, date: str, interval: str = "5m", strike_range: int = 30,
              overwrite: bool = False) -> tuple[str, int, str]:
    """Fetch one 0DTE chain. Returns (date, rows, status)."""
    path = day_path(symbol, date)
    if path.exists() and not overwrite:
        return date, -1, "cached"
    try:
        df = td.quotes(symbol, date, strike="*", right="both", date=date,
                       interval=interval, strike_range=strike_range)
    except Exception as exc:  # noqa: BLE001  - 472 = no data for that day
        return date, 0, f"error {exc}"
    if df.empty:
        return date, 0, "empty"
    df = df[[c for c in KEEP if c in df.columns]].copy()
    df["right"] = df["right"].astype(str).str[0]  # C / P
    df["strike"] = df["strike"].astype("float32")
    for c in ("bid", "ask"):
        df[c] = df[c].astype("float32")
    for c in ("bid_size", "ask_size"):
        if c in df:
            df[c] = df[c].astype("int32")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, compression="zstd")
    return date, len(df), "ok"


def load_day(symbol: str, date: str) -> pd.DataFrame:
    path = day_path(symbol, date)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def stored_dates(symbol: str) -> list[str]:
    d = STORE / symbol.upper()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.parquet"))


def _resolve_workers(requested: int, market: str) -> int:
    """Clamp to the machine's budget; fall back to the request if the scheduler is absent."""
    try:
        import sys as _sys
        if str(REPO) not in _sys.path:
            _sys.path.insert(0, str(REPO))
        from quant_brain.core.scheduler import resolve_workers
        return resolve_workers(requested, market)
    except Exception:  # noqa: BLE001
        return max(1, int(requested))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="SPY")
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--end", default=dt.date.today().isoformat())
    ap.add_argument("--interval", default="5m")
    ap.add_argument("--range", type=int, default=30, help="strikes each side of the money")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    sym = args.symbol.upper()
    if args.status:
        got = stored_dates(sym)
        if not got:
            print(f"{sym}: store empty ({STORE / sym})")
            return 0
        size = sum(p.stat().st_size for p in (STORE / sym).glob("*.parquet")) / 1e6
        s = pd.Series(pd.to_datetime(got))
        print(f"{sym}: {len(got)} sessions {got[0]} .. {got[-1]}, {size:.0f} MB")
        print(s.dt.year.value_counts().sort_index().to_string())
        return 0

    if not td.alive() and not td.start_terminal():
        print("Theta Terminal is not answering on 127.0.0.1:25503", file=sys.stderr)
        return 2

    dates = expiration_dates(sym, args.start, args.end)
    todo = [d for d in dates if args.overwrite or not day_path(sym, d).exists()]
    print(f"{sym}: {len(dates)} 0DTE sessions in range, {len(todo)} to fetch")
    ok = empty = err = 0
    rows = 0
    done = 0
    # Part 6: the worker count comes from the machine, not from a constant. This can only
    # LOWER the request - ask for 2 and you get 2 - so it never reshapes an experiment; what
    # it prevents is the 2026-09-12 state, where hard-coded fan-out put the box at 98% commit
    # charge while 34.7 GB of physical RAM still read as free.
    workers = _resolve_workers(args.workers, "options")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for date, n, status in ex.map(lambda d: fetch_day(sym, d, args.interval, args.range,
                                                          args.overwrite), todo):
            done += 1
            if status == "ok":
                ok += 1
                rows += n
            elif status == "empty":
                empty += 1
            elif status.startswith("error"):
                err += 1
                if err <= 5:
                    with _print_lock:
                        print(f"  {date}: {status}")
            if done % 100 == 0:
                print(f"  {done}/{len(todo)} ok={ok} empty={empty} err={err} rows={rows:,}")
    print(f"done: ok={ok} empty={empty} err={err} rows={rows:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
