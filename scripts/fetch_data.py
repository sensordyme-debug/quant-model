#!/usr/bin/env python
"""Fetch daily US equity/ETF bars and write them in LEAN's on-disk format.

Backlog D-1. Stopgap source is `yfinance` (free, no credentials); the writer is
source-agnostic so an IBKR/`ib_async` feed can replace `fetch()` later.

Usage:
    python scripts/fetch_data.py                          # full universe, 1998-01-01 -> today
    python scripts/fetch_data.py --universe etf            # ETF sleeve only
    python scripts/fetch_data.py --symbols SPY,QQQ,TQQQ    # explicit list
    python scripts/fetch_data.py --start 2010-01-01 --force
    python scripts/fetch_data.py --dry-run                 # fetch and validate, write nothing

Written per symbol, under <LEAN_DATA>/equity/usa/:
    daily/<sym>.zip        containing <sym>.csv, rows "yyyyMMdd 00:00,o,h,l,c,v"
                           with OHLC scaled by 10000 and stored as integers
    map_files/<sym>.csv    "yyyyMMdd,<sym>,<exchange>" first and last row
    factor_files/<sym>.csv "yyyyMMdd,price_factor,split_factor,reference_price"

Adjustment model: Yahoo's OHLC are already split-adjusted, so the split factor is
1 throughout and the dividend adjustment is carried entirely by the price factor,
derived from Adj Close / Close and normalised so the most recent factor is 1.
That matches LEAN's convention (adjusted = raw * price_factor * split_factor) and
keeps the stored bars consistent with the factor file.

Existing files are backed up once to <name>.orig before the first overwrite, so the
LEAN sample data can always be restored.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LEAN_ROOT = Path(os.environ.get("LEAN_ROOT", REPO.parent / "Lean"))
DATA_DIR = Path(os.environ.get("LEAN_DATA", LEAN_ROOT / "Data"))
USA = DATA_DIR / "equity" / "usa"
MANIFEST = REPO / "research" / "data_manifest.json"

SCALE = 10000
SENTINEL = "20501231"

# ETF sleeve: index, leveraged, sector, rates, commodity, volatility.
ETFS = [
    "SPY", "QQQ", "IWM", "DIA", "TQQQ", "SQQQ", "UPRO", "SPXU", "SOXL", "SOXS",
    "TLT", "TMF", "GLD", "USO", "UVXY", "SVXY", "XLK", "XLF", "XLE",
]

# 50 most liquid US megacaps.
MEGACAPS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B", "AVGO", "LLY",
    "JPM", "V", "UNH", "XOM", "MA", "JNJ", "PG", "COST", "HD", "ABBV",
    "WMT", "NFLX", "MRK", "KO", "AMD", "PEP", "ADBE", "CRM", "TMO", "BAC",
    "CSCO", "ACN", "LIN", "MCD", "ABT", "ORCL", "PFE", "INTC", "DIS", "QCOM",
    "WFC", "TXN", "CAT", "IBM", "AMAT", "VZ", "NOW", "GE", "UBER", "MU",
]

# Yahoo ticker -> LEAN ticker where they differ.
LEAN_TICKER = {"BRK-B": "brkb"}

# Listing venue for the map file: P = NYSE Arca (most ETFs), Q = NASDAQ, N = NYSE.
NYSE = {"BRK-B", "JPM", "V", "UNH", "XOM", "MA", "JNJ", "PG", "HD", "ABBV", "WMT",
        "MRK", "KO", "CRM", "TMO", "BAC", "ACN", "LIN", "MCD", "ABT", "ORCL", "PFE",
        "DIS", "WFC", "CAT", "IBM", "VZ", "NOW", "GE", "UBER", "LLY", "DIA"}


def universe(name: str) -> list[str]:
    return {"etf": ETFS, "megacap": MEGACAPS, "all": ETFS + MEGACAPS}[name]


def exchange(yahoo_ticker: str) -> str:
    if yahoo_ticker in ETFS:
        return "N" if yahoo_ticker in NYSE else "P"
    return "N" if yahoo_ticker in NYSE else "Q"


def fetch(symbols: list[str], start: str, end: str):
    """Return {yahoo_ticker: DataFrame[Open,High,Low,Close,Adj Close,Volume]}."""
    import yfinance as yf

    out = {}
    for i in range(0, len(symbols), 20):
        batch = symbols[i:i + 20]
        raw = yf.download(batch, start=start, end=end, auto_adjust=False, actions=True,
                          progress=False, group_by="ticker", threads=True)
        for sym in batch:
            try:
                df = raw[sym] if len(batch) > 1 else raw
            except KeyError:
                continue
            df = df.dropna(subset=["Open", "High", "Low", "Close", "Adj Close"])
            df = df[df["Close"] > 0]
            if "Dividends" in df:
                df = df.assign(Dividends=df["Dividends"].fillna(0.0))
            if not df.empty:
                out[sym] = df
    return out


def daily_csv(df) -> tuple[str, int]:
    """Render bars as LEAN daily rows; returns the csv and the count of clamped bars.

    Yahoo occasionally returns a bar whose high/low do not bracket the open/close.
    Rather than drop the session, widen the range to the true extremes and report it.
    """
    lines, clamped = [], 0
    for date, row in df.iterrows():
        o, h, l, c = (int(round(float(row[k]) * SCALE)) for k in ("Open", "High", "Low", "Close"))
        hi, lo = max(o, h, l, c), min(o, h, l, c)
        if (hi, lo) != (h, l):
            clamped += 1
            h, l = hi, lo
        v = int(row["Volume"]) if row["Volume"] == row["Volume"] else 0
        lines.append(f"{date.strftime('%Y%m%d')} 00:00,{o},{h},{l},{c},{v}")
    return "\n".join(lines) + "\n", clamped


def factor_csv(df) -> tuple[str, float]:
    """Build LEAN factor rows from explicit dividends; returns the csv and a check value.

    One row per dividend, not one per bar: deriving the factor from the Adj Close /
    Close ratio looks equivalent but Yahoo rounds Adj Close, so that ratio wobbles in
    the 7th decimal every day and yields thousands of spurious rows.

    A dividend D with ex-date e reduces the price factor of every earlier bar by
    (1 - D / C), where C is the close on the last session before e. Factors therefore
    accumulate backwards from 1 at the most recent bar. A row's date is the last bar
    date on which its factor applies, matching LEAN's "first row with date >= bar date"
    lookup. Splits are absent because Yahoo's OHLC are already split-adjusted.

    The returned check value is the largest relative disagreement between these
    factors and Yahoo's own Adj Close, which catches dividends missing from the feed.
    """
    dates = list(df.index)
    closes = [float(c) for c in df["Close"]]
    divs = [float(d) for d in df["Dividends"]] if "Dividends" in df else [0.0] * len(dates)

    # (last bar before the ex-date, dividend, that bar's close)
    events = [(dates[i - 1], divs[i], closes[i - 1])
              for i in range(1, len(dates)) if divs[i] > 0 and closes[i - 1] > 0]

    steps, cumulative = [], 1.0
    for ex_prev_date, dividend, prev_close in reversed(events):
        cumulative *= (1.0 - dividend / prev_close)
        steps.append((ex_prev_date, cumulative, prev_close))
    steps.reverse()

    # LEAN files open with a listing row carrying the earliest factor and reference price 1.
    earliest = steps[0][1] if steps else 1.0
    rows = []
    if not steps or steps[0][0] != dates[0]:
        rows.append(f"{dates[0].strftime('%Y%m%d')},{earliest:.7f},1,1")
    rows += [f"{d.strftime('%Y%m%d')},{f:.7f},1,{round(c, 2)}" for d, f, c in steps]
    rows.append(f"{SENTINEL},1,1,0")

    # Cross-check against Adj Close, which is independently computed by Yahoo.
    ratio = df["Adj Close"] / df["Close"]
    ratio = ratio / float(ratio.iloc[-1])
    boundaries = [d for d, _, _ in steps]
    max_dev, step_index = 0.0, 0
    for date, observed in zip(dates, ratio):
        while step_index < len(boundaries) and boundaries[step_index] < date:
            step_index += 1
        expected = steps[step_index][1] if step_index < len(steps) else 1.0
        if observed > 0:
            max_dev = max(max_dev, abs(expected / float(observed) - 1.0))
    return "\n".join(rows) + "\n", max_dev


def map_csv(df, lean_sym: str, exch: str) -> str:
    first = df.index[0].strftime("%Y%m%d")
    return f"{first},{lean_sym},{exch}\n{SENTINEL},{lean_sym},{exch}\n"


def backup_once(path: Path) -> None:
    """Preserve the shipped LEAN sample file the first time we overwrite it."""
    orig = path.with_suffix(path.suffix + ".orig")
    if path.exists() and not orig.exists():
        shutil.copy2(path, orig)


def write_symbol(yahoo_sym: str, df) -> dict:
    lean_sym = LEAN_TICKER.get(yahoo_sym, yahoo_sym.lower())
    exch = exchange(yahoo_sym)

    zip_path = USA / "daily" / f"{lean_sym}.zip"
    map_path = USA / "map_files" / f"{lean_sym}.csv"
    factor_path = USA / "factor_files" / f"{lean_sym}.csv"
    for p in (zip_path, map_path, factor_path):
        p.parent.mkdir(parents=True, exist_ok=True)
        backup_once(p)

    csv, clamped = daily_csv(df)
    factors, adj_close_dev = factor_csv(df)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{lean_sym}.csv", csv)
    map_path.write_text(map_csv(df, lean_sym, exch), encoding="utf-8")
    factor_path.write_text(factors, encoding="utf-8")

    return {
        "symbol": lean_sym, "yahoo": yahoo_sym, "exchange": exch, "bars": int(len(df)),
        "first": df.index[0].strftime("%Y-%m-%d"), "last": df.index[-1].strftime("%Y-%m-%d"),
        "clamped_bars": clamped, "factor_rows": len(factors.strip().splitlines()),
        "adj_close_dev": round(adj_close_dev, 6), "zip_bytes": zip_path.stat().st_size,
    }


def validate(lean_sym: str) -> str | None:
    """Re-read what we wrote and check LEAN's structural invariants."""
    zip_path = USA / "daily" / f"{lean_sym}.zip"
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        if names != [f"{lean_sym}.csv"]:
            return f"zip entry is {names}, expected ['{lean_sym}.csv']"
        rows = z.read(names[0]).decode().strip().splitlines()
    if len(rows) < 100:
        return f"only {len(rows)} bars"
    dates = []
    for r in rows:
        stamp, o, h, l, c, v = r.split(",")
        o, h, l, c = int(o), int(h), int(l), int(c)
        if not (l <= o <= h and l <= c <= h and l > 0):
            return f"inconsistent OHLC at {stamp}: {o},{h},{l},{c}"
        dates.append(stamp.split()[0])
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        return "dates are not strictly increasing"
    factors = (USA / "factor_files" / f"{lean_sym}.csv").read_text().strip().splitlines()
    if not factors[-1].startswith(SENTINEL):
        return "factor file missing the 20501231 sentinel row"
    for row in factors:
        if len(row.split(",")) != 4:
            return f"malformed factor row: {row}"
    # A file holding only the sentinel makes LEAN drop the symbol entirely: it needs a
    # row dated at or before the first bar. This is what silently killed GLD/UVXY/BRKB.
    if len(factors) < 2:
        return "factor file has only the sentinel row; LEAN will return no data"
    if factors[0].split(",")[0] > dates[0]:
        return f"first factor row {factors[0].split(',')[0]} starts after first bar {dates[0]}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--universe", default="all", choices=["etf", "megacap", "all"])
    ap.add_argument("--symbols", help="comma-separated Yahoo tickers, overrides --universe")
    ap.add_argument("--start", default="1998-01-01")
    ap.add_argument("--end", default=None,
                    help="exclusive end date; defaults to today so the unfinished session is excluded")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    args = ap.parse_args()

    if not USA.exists():
        sys.exit(f"LEAN equity data folder not found: {USA}")

    symbols = ([s.strip().upper() for s in args.symbols.split(",") if s.strip()]
               if args.symbols else universe(args.universe))
    # Exclusive end at today: the in-progress session is a snapshot, not a bar, and
    # Yahoo returns it with high/low that do not bracket the open.
    end = args.end or dt.date.today().isoformat()

    print(f"[fetch] {len(symbols)} symbols, {args.start} -> {end}, target {USA}", flush=True)
    frames = fetch(symbols, args.start, end)
    missing = [s for s in symbols if s not in frames]

    written, failed = [], []
    for sym in symbols:
        df = frames.get(sym)
        if df is None:
            continue
        if args.dry_run:
            written.append({"symbol": LEAN_TICKER.get(sym, sym.lower()), "yahoo": sym,
                            "bars": int(len(df)), "first": df.index[0].strftime("%Y-%m-%d"),
                            "last": df.index[-1].strftime("%Y-%m-%d")})
            continue
        info = write_symbol(sym, df)
        problem = validate(info["symbol"])
        if problem:
            failed.append((sym, problem))
        else:
            written.append(info)

    suspect = []
    for info in written:
        note = f"  clamped {info['clamped_bars']}" if info.get("clamped_bars") else ""
        extra = ""
        if "factor_rows" in info:
            extra = f"  {info['factor_rows']:>4} factor rows  adj-dev {info['adj_close_dev']:.5f}"
            if info["adj_close_dev"] > 0.01:
                extra += "  <-- CHECK"
                suspect.append(info["symbol"])
        print(f"  {info['symbol']:<6} {info['bars']:>6} bars  "
              f"{info['first']} .. {info['last']}{extra}{note}")
    if suspect:
        print(f"[fetch] factors disagree with Adj Close by >1% for: {', '.join(suspect)}")
    if missing:
        print(f"[fetch] no data returned for: {', '.join(missing)}")
    for sym, problem in failed:
        print(f"[fetch] VALIDATION FAILED {sym}: {problem}")

    if not args.dry_run:
        MANIFEST.write_text(json.dumps({
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "source": "yfinance (split-adjusted OHLC, dividends via price factors)",
            "start": args.start, "end": end,
            "symbols_written": len(written), "symbols_missing": missing,
            "symbols_failed": {s: p for s, p in failed},
            "clamped_bars_total": sum(i.get("clamped_bars", 0) for i in written),
            "symbols_factor_check": suspect,
            "data": {i["symbol"]: {k: i[k] for k in
                                   ("bars", "first", "last", "clamped_bars",
                                    "factor_rows", "adj_close_dev")}
                     for i in written},
        }, indent=2) + "\n", encoding="utf-8")
        print(f"[fetch] manifest -> {MANIFEST.relative_to(REPO)}")

    print(f"[fetch] {len(written)} written, {len(missing)} missing, {len(failed)} failed validation")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
