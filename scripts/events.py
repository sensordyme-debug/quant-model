#!/usr/bin/env python
"""Event calendar for the sleeves: earnings dates from FMP into data/events/earnings.json.

    python scripts/events.py                 # refresh: past 400 days + next 30 days
    python scripts/events.py --show NVDA     # print stored dates for a symbol

The intraday framework reads the file through `events.earnings_window(symbol, day, before,
after)` to gate names around their earnings prints (the worst intraday days cluster there).
FMP's basic plan serves the earnings calendar; economic-calendar and news endpoints are not
on this plan (checked 2026-09-10), so those stay out until the plan changes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apikeys import require  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
EVENTS = REPO / "data" / "events" / "earnings.json"
BASE = "https://financialmodelingprep.com/stable/earnings-calendar"


def fetch(start: dt.date, end: dt.date, key: str) -> dict[str, list[str]]:
    out: dict[str, set[str]] = {}
    cur = start
    while cur <= end:                              # step 30-day windows; the basic plan refuses
        stop = min(end, cur + dt.timedelta(days=30))   # windows outside its allowed range (402)
        url = BASE + "?" + urllib.parse.urlencode({"from": str(cur), "to": str(stop), "apikey": key})
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                rows = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (402, 403):
                print(f"  window {cur}..{stop} not on this plan (HTTP {e.code}); skipping", flush=True)
                rows = []
            else:
                raise
        for row in rows:
            sym, d = row.get("symbol"), row.get("date")
            if sym and d and "." not in sym:      # US listings only
                out.setdefault(sym, set()).add(d)
        cur = stop + dt.timedelta(days=1)
    return {s: sorted(v) for s, v in out.items()}


def load() -> dict[str, list[str]]:
    if EVENTS.exists():
        return json.loads(EVENTS.read_text(encoding="utf-8")).get("earnings", {})
    return {}


_CACHE: dict | None = None


def earnings_window(symbol: str, day: dt.date, before: int = 1, after: int = 1) -> bool:
    """True if `symbol` has an earnings date within [day-before, day+after]."""
    global _CACHE
    if _CACHE is None:
        _CACHE = load()
    for d in _CACHE.get(symbol, ()):
        e = dt.date.fromisoformat(d)
        if day - dt.timedelta(days=before) <= e <= day + dt.timedelta(days=after):
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days-back", type=int, default=400)
    ap.add_argument("--days-ahead", type=int, default=30)
    ap.add_argument("--show")
    args = ap.parse_args()
    if args.show:
        print(args.show, load().get(args.show.upper(), []))
        return 0
    key = require("FMP_API_KEY")["FMP_API_KEY"]
    today = dt.date.today()
    data = fetch(today - dt.timedelta(days=args.days_back), today + dt.timedelta(days=args.days_ahead), key)
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    EVENTS.write_text(json.dumps({"generated": str(today), "source": "FMP earnings-calendar", "earnings": data},
                                 indent=0), encoding="utf-8")
    n = sum(len(v) for v in data.values())
    print(f"{len(data)} symbols, {n} earnings dates -> {EVENTS}")
    for s in ("NVDA", "TSLA", "AAPL", "AVGO", "COIN"):
        print(f"  {s}: {data.get(s, [])[-4:]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
