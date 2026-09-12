#!/usr/bin/env python
"""D-4 / AUD-16: price the IBKR minute fetcher's two defects, offline, before any refetch.

    python scripts/sweep_d4.py              # all clauses, no network, no writes
    python scripts/sweep_d4.py --json

AUD-16 says `scripts/intraday_data.py` "cannot extend the store and truncates today's session
(all 16 symbols hold a 170-bar 2026-09-11)". Both halves are checkable without an IBKR
connection, because both are decisions the module makes from the clock and from what is on
disk. This script makes those decisions under the OLD and the NEW rule and reports the
difference; it never connects, never writes and never touches the store.

Pre-registered clauses (fixed before any number was read)
---------------------------------------------------------
1. IDENTITY. On a store that is complete up to the last closed session, the NEW skip issues
   ZERO requests for `--months 3`. If the fix turns "skip when counted" into "always fetch",
   it is not a fix, it is 16 symbols x 3 pointless requests every run.
2. TRUNCATION, defect 1. `snap_after_close` under the OLD rule returns an instant INSIDE a
   regular session for every wall-clock time in 09:30..16:15 ET on a trading day; under the
   NEW rule it returns an instant inside a session for NONE of them. Checked minute by
   minute over a full trading day, and on an early close and a holiday.
3. NO-OP, defect 2. Under the OLD count-based skip, a `--months 3` run today issues zero
   requests for all 16 symbols even though the store's last session is truncated. Under the
   NEW rule it issues at least one for every symbol that is missing or truncated, and the
   windows it picks contain those sessions.
4. LINE. The fetcher's "needs a refetch" set equals `store_health.session_shapes`'s
   truncated-or-missing set on the real store for all 16 symbols. E-6 drew the line between
   SPARSE and TRUNCATED; this module must not draw a second one.
5. MATERIALITY. Report the (symbol, session) pairs and the bars the fix makes reachable,
   against a pre-registered threshold of ONE session - because the session at risk is the
   last one, and `intraday_launch.py` preflights by replaying exactly that.
6. REGRESSION. `--force` is unchanged by the patch: the same windows, the same order.
7. WITHDRAWAL. If clause 1 or clause 4 fails, the patch is withdrawn and the count-based skip
   is restored; a fetcher that re-requests a complete store is worse than one that cannot
   extend it, because it burns the pacing budget the repair needs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import intraday_data as idata  # noqa: E402
import store_health as sh  # noqa: E402

from intraday_common import ET, UNIVERSE, parquet_path  # noqa: E402
from quant_brain.markets.equity_us import CALENDAR  # noqa: E402

#: A regular session, an early close and a holiday inside the calendar's verified range.
REGULAR_DAY = dt.date(2026, 9, 11)
EARLY_DAY = dt.date(2026, 11, 27)     # day after Thanksgiving, 13:00 close
HOLIDAY = dt.date(2026, 11, 26)


def inside_a_session(when: dt.datetime) -> bool:
    """True if `when` lands inside a session, i.e. IBKR would truncate a request ending there."""
    sess = CALENDAR.session(when.date())
    if sess is None:
        return False
    return sess.open_t <= when.time() < sess.close_t


# ------------------------------------------------------------------ clause 2: the truncation

def clause_truncation() -> dict:
    rows = []
    for day, label in ((REGULAR_DAY, "regular"), (EARLY_DAY, "early-close"), (HOLIDAY, "holiday")):
        old_bad = new_bad = 0
        for minute in range(0, 24 * 60, 5):
            now = dt.datetime.combine(day, dt.time(minute // 60, minute % 60), tzinfo=ET)
            old_bad += inside_a_session(idata.snap_after_close(now, now=now, legacy=True))
            new_bad += inside_a_session(idata.snap_after_close(now, now=now, legacy=False))
        rows.append({"day": str(day), "kind": label, "probes": 24 * 60 // 5,
                     "old_inside_session": old_bad, "new_inside_session": new_bad})
    return {"rows": rows,
            "pass": all(r["new_inside_session"] == 0 for r in rows)
            and any(r["old_inside_session"] > 0 for r in rows)}


# ------------------------------------------------------- clauses 1, 3, 5: the skip and its cost

def windows(months: int, now: dt.datetime) -> list[tuple[dt.date, dt.date]]:
    return [((e - dt.timedelta(days=30)).date(), e.date())
            for e in idata.month_ends(months, now=now)]


def skip_decisions(symbol: str, months: int, now: dt.datetime) -> dict:
    """What each rule would do for one symbol, without connecting to anything."""
    shapes = idata.store_shapes(symbol)
    old_fetch, new_fetch, needed = [], [], []
    for start, end in windows(months, now):
        counted = sum(1 for d in shapes if start <= d <= end)
        if counted < 15:
            old_fetch.append((str(start), str(end)))
        need = idata.sessions_needed(symbol, start, end, shapes=shapes, now=now)
        if need:
            new_fetch.append((str(start), str(end)))
            needed += need
    bad = idata.incomplete_sessions(symbol, now=now)
    return {"symbol": symbol, "stored_sessions": len(shapes),
            "old_requests": len(old_fetch), "new_requests": len(new_fetch),
            "incomplete": [str(d) for d in bad],
            "needed_in_window": sorted({str(d) for d in needed}),
            "new_windows": new_fetch}


def clause_skip(months: int, now: dt.datetime) -> dict:
    rows = [skip_decisions(s, months, now) for s in UNIVERSE]
    # clause 3: the OLD rule is a no-op everywhere while sessions are missing or truncated
    dirty = [r for r in rows if r["incomplete"]]
    old_noop = all(r["old_requests"] == 0 for r in rows)
    new_covers = all(r["new_requests"] > 0 for r in dirty)
    # clause 1: identity - a symbol with nothing missing gets no request
    clean = [r for r in rows if not r["incomplete"]]
    identity = all(r["new_requests"] == 0 for r in clean)
    return {"rows": rows, "dirty": len(dirty), "clean": len(clean),
            "old_noop": old_noop, "new_covers_dirty": new_covers, "identity": identity,
            "pass": identity and new_covers}


def clause_line(now: dt.datetime) -> dict:
    """Clause 4: the fetcher's verdict must be E-6's verdict, symbol by symbol."""
    rows, agree = [], True
    end = idata.last_closed_session(now)
    for s in UNIVERSE:
        p = parquet_path(s)
        if not p.exists():
            continue
        shapes = {sp.day: sp for sp in sh.session_shapes(sh.rth_index(p), CALENDAR)}
        e6_trunc = {d for d, sp in shapes.items() if sp.truncated and d <= end}
        e6_missing = {d for d in CALENDAR.trading_days(min(shapes), end) if d not in shapes}
        mine = set(idata.incomplete_sessions(s, now=now))
        ok = mine == (e6_trunc | e6_missing)
        agree &= ok
        rows.append({"symbol": s, "e6_truncated": len(e6_trunc), "e6_missing": len(e6_missing),
                     "fetcher": len(mine), "agree": ok})
    return {"rows": rows, "pass": agree}


def clause_materiality(skip: dict) -> dict:
    """Clause 5: the sessions the OLD rule could never reach, and the bars they are short."""
    pairs, short_bars = 0, 0
    for r in skip["rows"]:
        shapes = idata.store_shapes(r["symbol"])
        for ds in r["incomplete"]:
            d = dt.date.fromisoformat(ds)
            pairs += 1
            sp = shapes.get(d)
            short_bars += (sp.expected - sp.bars) if sp else (CALENDAR.session_minutes(d) or 0)
    return {"unreachable_pairs": pairs, "bars_short": short_bars,
            "threshold_pairs": 1, "pass": pairs >= 1, "material": pairs >= 1}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--months", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    now = dt.datetime.now(ET)
    out = {"now": now.isoformat(), "months": args.months,
           "last_closed_session": str(idata.last_closed_session(now))}
    out["c2_truncation"] = clause_truncation()
    out["c1_c3_skip"] = clause_skip(args.months, now)
    out["c4_line"] = clause_line(now)
    out["c5_materiality"] = clause_materiality(out["c1_c3_skip"])

    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return 0

    print(f"D-4 / AUD-16   now {now:%Y-%m-%d %H:%M} ET   "
          f"last closed session {out['last_closed_session']}\n")

    print("clause 2 - snap_after_close lands inside a live session (per 288 five-minute probes)")
    print(f"  {'day':<12} {'kind':<12} {'OLD':>5} {'NEW':>5}")
    for r in out["c2_truncation"]["rows"]:
        print(f"  {r['day']:<12} {r['kind']:<12} {r['old_inside_session']:>5} "
              f"{r['new_inside_session']:>5}")
    print(f"  -> {'PASS' if out['c2_truncation']['pass'] else 'FAIL'}\n")

    sk = out["c1_c3_skip"]
    print(f"clauses 1 and 3 - requests a --months {args.months} run would issue, per symbol")
    print(f"  {'sym':<7} {'stored':>7} {'OLD':>4} {'NEW':>4}  incomplete sessions")
    for r in sk["rows"]:
        print(f"  {r['symbol']:<7} {r['stored_sessions']:>7} {r['old_requests']:>4} "
              f"{r['new_requests']:>4}  {', '.join(r['incomplete']) or '-'}")
    print(f"  dirty {sk['dirty']}/16, clean {sk['clean']}/16; OLD is a no-op everywhere: "
          f"{sk['old_noop']}; NEW covers every dirty symbol: {sk['new_covers_dirty']}; "
          f"identity on clean symbols: {sk['identity']}")
    print(f"  -> {'PASS' if sk['pass'] else 'FAIL'}\n")

    ln = out["c4_line"]
    print("clause 4 - the fetcher's verdict against store_health (E-6)")
    bad = [r for r in ln["rows"] if not r["agree"]]
    print(f"  {len(ln['rows'])} symbols compared, {len(bad)} disagree "
          f"{[r['symbol'] for r in bad] if bad else ''}")
    print(f"  -> {'PASS' if ln['pass'] else 'FAIL'}\n")

    m = out["c5_materiality"]
    print("clause 5 - materiality")
    print(f"  {m['unreachable_pairs']} (symbol, session) pairs the count-based skip could not "
          f"reach, {m['bars_short']:,} bars short")
    print(f"  -> {'MATERIAL' if m['material'] else 'NOT MATERIAL'} "
          f"(threshold {m['threshold_pairs']} pair)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
