"""E-6: is the store WHOLE? Coverage checks that `dataquality.py` cannot make.

`quant_brain/core/dataquality.py` validates the bars a store *contains* - no zeros, no NaNs,
no duplicate stamps, no bars on a market holiday. It is blind to the bars a store is *missing*,
because a missing bar is not a row it can look at. Both stores are clean by that standard and
still hand a backtest a half day.

The distinction this module is built on
---------------------------------------
Measured over 169,039 stored sessions, "fewer bars than the session holds" splits into two
populations that need opposite responses:

  * **SPARSE** - bars scattered but spanning the session (e.g. 381/390, first 09:30, last 15:59).
    5,710 sessions in the Alpaca store. Benign and expected: a consolidated-tape minute bar only
    exists if the symbol traded that minute, so a thin name legitimately skips minutes. Nothing
    to do.
  * **TRUNCATED** - a contiguous head or tail is absent (e.g. 170/390, first 09:30, last 12:19).
    262 sessions in the Alpaca store, 16 in the IBKR store. A fetch that died mid-day. This is
    the one that lies to a backtest: the session silently ends at lunch, the strategy is never
    asked to trade the afternoon, and the day's P&L enters the ledger as if it were a full one.

Counting bars cannot tell them apart - 170/390 and 381/390 are both "short". Comparing the first
and last bar of each session against the calendar's own open and close can, and does: the two
populations barely overlap. So every session is scored on three numbers - `start_lag`,
`end_lead`, `fill` - and only a contiguous hole is called truncation.

Severity, and why nothing here is fatal by default
--------------------------------------------------
FAIL is reserved for structural corruption (duplicate stamps, bars on a closed day, an
unreadable or empty file) - facts that make the file wrong rather than short. Truncation and
missing sessions are WARN plus the exact dates, because the consumer's right response is to
exclude those dates, not to abandon the store. The one promotion: **if the store's LAST session
is truncated, that is a FAIL** - not because one day matters more than another, but because it
means the most recent fetch died and every run from now on quietly samples a half day at the
live edge of the data. That is an operational fact with an owner and a fix.

Like `dataquality.py`, this module reports and never repairs. The fetchers
(`intraday_data.py`, `alpaca_data.py`, `odte_data.py`) are where a refetch belongs.

    python scripts/store_health.py                      # every store, summary + findings
    python scripts/store_health.py --store minute -v    # one store, per-symbol table
    python scripts/store_health.py --json               # machine-readable
    python scripts/store_health.py --strict             # exit 1 if anything FAILs
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

from quant_brain.core.calendar import SessionCalendar  # noqa: E402
from quant_brain.core.dataquality import Report, Severity  # noqa: E402

ET = "America/New_York"

#: A session is TRUNCATED when its first bar is this many minutes after the open, or its last
#: bar this many minutes before the close. 15 is loose enough that a genuinely thin name missing
#: the first few minutes is not accused of truncation, and tight enough that every real
#: mid-session death measured (>= 32 minutes of missing tail) is caught.
TRUNCATION_MINUTES = 15

#: Below this fill ratio a session is reported as SPARSE (INFO). Not a defect - see the
#: module docstring - but a number a sweep may want to see before it trusts a thin symbol.
SPARSE_FILL = 0.90

#: How many trading days a store may lag the last closed session before it is called stale.
#: Two, so that a fetcher that skips a single night is not an alert but a dead one is.
STALE_DAYS = 2

#: 0DTE stops being a property of the calendar and starts being a property of the store on this
#: date: from 2023-05-01 SPY expires every session, so from here a missing file is a missing
#: fetch. Before it, absence is the instrument (weeklies), not a gap.
ODTE_DAILY_FROM = dt.date(2023, 5, 1)


# --------------------------------------------------------------------------- per-session shape

@dataclass(frozen=True)
class SessionShape:
    """What one stored session looks like against what the calendar says it should be."""

    day: dt.date
    bars: int
    expected: int
    start_lag: float   #: minutes between the session open and the first stored bar
    end_lead: float    #: minutes between the last stored bar and the session close

    @property
    def fill(self) -> float:
        return self.bars / self.expected if self.expected else 0.0

    @property
    def truncated(self) -> bool:
        return (self.end_lead > TRUNCATION_MINUTES) or (self.start_lag > TRUNCATION_MINUTES)

    @property
    def sparse(self) -> bool:
        return (not self.truncated) and self.fill < SPARSE_FILL

    def why(self) -> str:
        side = "ends" if self.end_lead > TRUNCATION_MINUTES else "starts"
        gap = self.end_lead if self.end_lead > TRUNCATION_MINUTES else self.start_lag
        return f"{self.day} {side} {gap:.0f}m short ({self.bars}/{self.expected})"


def session_shapes(index, calendar: SessionCalendar) -> list[SessionShape]:
    """Score every session in a tz-aware minute index. One pass, O(rows).

    The last regular bar of a US equity session *starts* at 15:59 (IBKR and Alpaca both stamp a
    bar at its open), so a complete session has `end_lead == 0` once that one-minute convention
    is subtracted. Getting this wrong would report every complete session as a minute short.
    """
    if index is None or len(index) == 0:
        return []
    agg = pd.Series(index, index=index).groupby(index.date).agg(["min", "max", "size"])
    out: list[SessionShape] = []
    for day, row in agg.iterrows():
        if not isinstance(day, dt.date):
            continue
        try:
            sess = calendar.session(day)
        except Exception:  # noqa: BLE001 - outside the calendar's coverage; reported elsewhere
            continue
        if sess is None:
            continue
        open_dt = pd.Timestamp(dt.datetime.combine(day, sess.open_t), tz=ET)
        close_dt = pd.Timestamp(dt.datetime.combine(day, sess.close_t), tz=ET)
        out.append(SessionShape(
            day=day,
            bars=int(row["size"]),
            expected=sess.minutes,
            start_lag=(row["min"] - open_dt).total_seconds() / 60.0,
            end_lead=(close_dt - row["max"]).total_seconds() / 60.0 - 1.0,
        ))
    return out


def rth_index(path: Path, open_t=dt.time(9, 30), close_t=dt.time(16, 0)):
    """The regular-session timestamps of a minute parquet, in ET.

    Reads `columns=[]`: the index alone is ~3x faster than the full frame and this module never
    looks at a price. Mirrors `intraday_common.load_bars` on tz and RTH so a finding here means
    the same thing the harness would see - except that duplicates are kept, since `load_bars`
    drops them and dropping them is precisely what would hide the defect.
    """
    df = pd.read_parquet(path, columns=[])
    idx = df.index
    if getattr(idx, "tz", None) is None:
        idx = idx.tz_localize("UTC")
    idx = idx.tz_convert(ET).sort_values()
    t = idx.time
    return idx[(t >= open_t) & (t < close_t)]


# --------------------------------------------------------------------------- minute stores

def check_minute_symbol(symbol: str, path: Path, calendar: SessionCalendar, rep: Report,
                        *, today: dt.date) -> tuple[dict, list[SessionShape]]:
    """Coverage of one symbol's minute parquet.

    Appends only the findings that are genuinely about THIS symbol - a file that will not read,
    a duplicate stamp, bars on a closed day. Coverage defects are returned as shapes instead and
    rolled up by date at the store level: when one dead fetch truncates all 16 symbols, the fact
    is "2026-09-11 died at 12:20", not sixteen copies of it, and a report that prints it sixteen
    times is a report nobody reads twice.
    """
    row = {"symbol": symbol, "sessions": 0, "rows": 0, "first": None, "last": None,
           "missing": 0, "truncated": 0, "sparse": 0, "duplicates": 0, "lag_days": None}
    try:
        idx = rth_index(path)
    except Exception as exc:  # noqa: BLE001 - an unreadable store is the finding
        rep.add("unreadable", Severity.FAIL, symbol, f"{type(exc).__name__}: {exc}"[:90])
        return row, []
    rep.symbols += 1
    if len(idx) == 0:
        rep.add("empty", Severity.FAIL, symbol, "no regular-session bars at all")
        return row, []
    rep.rows += len(idx)
    row["rows"] = int(len(idx))

    dupes = int(pd.Index(idx).duplicated().sum())
    if dupes:
        row["duplicates"] = dupes
        rep.add("duplicates", Severity.FAIL, symbol, "duplicate timestamps", dupes)

    shapes = session_shapes(idx, calendar)
    if not shapes:
        rep.add("uncovered", Severity.WARN, symbol, "no session falls inside the calendar")
        return row, []
    present = {s.day for s in shapes}
    first, last = min(present), max(present)
    row.update(sessions=len(shapes), first=str(first), last=str(last))
    row["missing"] = sum(1 for d in calendar.trading_days(first, last) if d not in present)
    row["truncated"] = sum(1 for s in shapes if s.truncated)
    row["sparse"] = sum(1 for s in shapes if s.sparse)

    # Asked of the RAW index, not of `present`: `session_shapes` can only score days the
    # calendar has a session for, so a holiday is silently absent from `shapes` and checking
    # `present` would make bars on Thanksgiving invisible - the one defect this check exists for.
    try:
        shut = sorted({d for d in set(idx.date) if not calendar.is_trading_day(d)})
    except Exception:  # noqa: BLE001 - outside the calendar's coverage; not a data defect
        shut = []
    if shut:
        rep.add("non_trading_day", Severity.FAIL, symbol,
                f"bars on days the market was shut, e.g. {shut[0]}", len(shut))

    closed = [d for d in calendar.trading_days(last, today) if d < today]
    row["lag_days"] = max(0, len(closed) - 1)
    return row, shapes


def _by_day(per_symbol: dict[str, list], examples: int) -> list[str]:
    """Render a {day: [symbol, ...]} roll-up as at most `examples` newest lines."""
    days = sorted(per_symbol, reverse=True)[:examples]
    return [f"{d} ({len(per_symbol[d])} sym: {', '.join(sorted(per_symbol[d])[:4])}"
            f"{'...' if len(per_symbol[d]) > 4 else ''})" for d in days]


def check_minute_store(store: Path, calendar: SessionCalendar, *, today: dt.date,
                       symbols: list[str] | None = None,
                       examples: int = 3) -> tuple[Report, list[dict]]:
    rep = Report()
    rows: list[dict] = []
    if not store.exists():
        rep.add("absent", Severity.WARN, store.name, f"no such store: {store}")
        return rep, rows
    files = sorted(store.glob("*.parquet"))
    if symbols:
        want = {s.upper() for s in symbols}
        files = [p for p in files if p.stem.upper() in want]
    if not files:
        rep.add("absent", Severity.WARN, store.name, "no parquet files")
        return rep, rows

    name = store.name
    trunc: dict[dt.date, list[str]] = {}
    missing: dict[dt.date, list[str]] = {}
    tail_broken: list[str] = []
    worst_gap = 0.0
    sparse_total = 0
    for p in files:
        row, shapes = check_minute_symbol(p.stem, p, calendar, rep, today=today)
        rows.append(row)
        if not shapes:
            continue
        present = {s.day for s in shapes}
        for d in calendar.trading_days(min(present), max(present)):
            if d not in present:
                missing.setdefault(d, []).append(p.stem)
        for s in shapes:
            if s.truncated:
                trunc.setdefault(s.day, []).append(p.stem)
                worst_gap = max(worst_gap, s.end_lead, s.start_lag)
        sparse_total += row["sparse"]
        if max(shapes, key=lambda s: s.day).truncated:
            tail_broken.append(p.stem)

    if missing:
        rep.add("missing_session", Severity.WARN, name,
                "trading days with no bars, inside the symbol's own covered range: "
                + "; ".join(_by_day(missing, examples)),
                sum(len(v) for v in missing.values()))
    if trunc:
        rep.add("truncated_session", Severity.WARN, name,
                f"sessions missing a contiguous head/tail (worst {worst_gap:.0f}m) - exclude "
                f"these dates: " + "; ".join(_by_day(trunc, examples)),
                sum(len(v) for v in trunc.values()))
    if tail_broken:
        last_day = max(r["last"] for r in rows if r["last"])
        rep.add("truncated_tail", Severity.FAIL, name,
                f"the store's LAST session ({last_day}) is truncated for {len(tail_broken)} of "
                f"{len(rows)} symbols - the most recent fetch died mid-session; refetch before "
                f"researching the live edge")
    if sparse_total:
        rep.add("sparse_session", Severity.INFO, name,
                f"symbol-sessions under {SPARSE_FILL:.0%} filled but spanning the session "
                f"(thin minutes, not a defect)", sparse_total)

    lags = [r["lag_days"] for r in rows if r["lag_days"] is not None]
    if lags and max(lags) > STALE_DAYS:
        behind = sorted(r["symbol"] for r in rows if (r["lag_days"] or 0) > STALE_DAYS)
        rep.add("stale", Severity.WARN, name,
                f"{len(behind)} symbol(s) up to {max(lags)} trading days behind {today}, e.g. "
                + ", ".join(behind[:examples]), len(behind))

    # --- coverage skew: a sweep over the union silently changes universe by date ----------
    firsts = [r["first"] for r in rows if r["first"]]
    if len(firsts) > 1 and min(firsts) != max(firsts):
        late = sorted(r["symbol"] for r in rows if r["first"] == max(firsts))[:examples]
        rep.add("coverage_skew", Severity.INFO, name,
                f"symbols start on different days ({min(firsts)} .. {max(firsts)}); a sweep over "
                f"the union has a smaller universe early on, e.g. {', '.join(late)}")
    return rep, rows


# --------------------------------------------------------------------------- 0DTE chain store

def check_odte_store(store: Path, calendar: SessionCalendar, *, today: dt.date,
                     examples: int = 3) -> tuple[Report, list[dict]]:
    """Completeness of `data/options/odte/<SYM>/<date>.parquet`.

    A chain day is truncated the same way a minute session is: the quotes stop before the close.
    Missing *days* can only be judged from `ODTE_DAILY_FROM` onward - before it, SPY did not
    expire every session and an absent file is the instrument, not the fetch.
    """
    rep = Report()
    rows: list[dict] = []
    if not store.exists():
        rep.add("absent", Severity.WARN, "odte", f"no such store: {store}")
        return rep, rows
    for symdir in sorted(p for p in store.iterdir() if p.is_dir()):
        sym = symdir.name
        files = sorted(symdir.glob("*.parquet"))
        if not files:
            rep.add("absent", Severity.WARN, sym, "no chain files")
            continue
        rep.symbols += 1
        dates: list[dt.date] = []
        for p in files:
            try:
                dates.append(dt.date.fromisoformat(p.stem))
            except ValueError:
                rep.add("bad_name", Severity.WARN, sym, f"not a date-named file: {p.name}")
        if not dates:
            continue
        first, last = min(dates), max(dates)
        empty: list[str] = []
        truncated: list[str] = []
        total = 0
        for p in files:
            try:
                df = pd.read_parquet(p, columns=["timestamp", "strike"])
            except Exception as exc:  # noqa: BLE001
                rep.add("unreadable", Severity.FAIL, sym, f"{p.name}: {type(exc).__name__}")
                continue
            total += len(df)
            if df.empty:
                empty.append(p.stem)
                continue
            day = dt.date.fromisoformat(p.stem)
            sess = calendar.session(day)
            if sess is None:
                rep.add("non_trading_day", Severity.FAIL, sym,
                        f"chain stored for a day the market was shut: {p.stem}")
                continue
            close_dt = pd.Timestamp(dt.datetime.combine(day, sess.close_t))
            lead = (close_dt - pd.Timestamp(df["timestamp"].max())).total_seconds() / 60.0
            # The store is sampled at 5m, so the last bar sits up to one interval before the
            # close by construction; only a gap several intervals wide is a dead fetch.
            if lead > 20:
                truncated.append(f"{p.stem} ends {lead:.0f}m short")
        rep.rows += total
        rows.append({"symbol": sym, "days": len(dates), "first": str(first), "last": str(last),
                     "rows": total, "empty": len(empty), "truncated": len(truncated)})
        if empty:
            rep.add("empty_chain", Severity.WARN, sym, "chain files with no quotes, e.g. "
                    + ", ".join(empty[:examples]), len(empty))
        if truncated:
            rep.add("truncated_chain", Severity.WARN, sym, "; ".join(truncated[-examples:]),
                    len(truncated))
        window_start = max(first, ODTE_DAILY_FROM)
        if last >= window_start:
            have = set(dates)
            gaps = [d for d in calendar.trading_days(window_start, last) if d not in have]
            if gaps:
                rep.add("missing_chain", Severity.WARN, sym,
                        f"trading days with no 0DTE file since {window_start} (SPY expires every "
                        f"session from then), e.g. " + ", ".join(str(d) for d in gaps[:examples]),
                        len(gaps))
        closed = [d for d in calendar.trading_days(last, today) if d < today]
        if max(0, len(closed) - 1) > STALE_DAYS:
            rep.add("stale", Severity.WARN, sym,
                    f"last chain {last} is {len(closed) - 1} trading days behind {today}")
    return rep, rows


# --------------------------------------------------------------------------- Theta liveness

def check_theta(rep: Report) -> dict:
    """Is the local Theta Terminal serving? Reuses `theta_data.status()`; never raises.

    A dead terminal is INFO, not a defect: it is started on demand and is expected to be down
    between options runs. What would be a defect is a terminal that is *bound* but not serving,
    which `status()` distinguishes - that one blocks a restart.
    """
    try:
        import theta_data as td
        st = td.status()
    except Exception as exc:  # noqa: BLE001
        rep.add("theta", Severity.INFO, "theta", f"probe unavailable ({type(exc).__name__})")
        return {"listening": None, "alive": None}
    if st.get("alive"):
        rep.add("theta", Severity.INFO, "theta", "terminal alive and serving")
    elif st.get("listening"):
        rep.add("theta", Severity.WARN, "theta",
                f"port 25503 is bound but not serving: {st.get('detail', '')}"[:110])
    else:
        rep.add("theta", Severity.INFO, "theta",
                "terminal down (normal between options runs; --start-terminal to raise it)")
    return st


# --------------------------------------------------------------------------- CLI

STORES = {
    "minute": REPO / "data" / "minute",
    "minute_alpaca": REPO / "data" / "minute_alpaca",
    "odte": REPO / "data" / "options" / "odte",
}


def _print_table(rows: list[dict], cols: list[str]) -> None:
    if not rows:
        return
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    print("  " + "  ".join(c.rjust(widths[c]) for c in cols))
    for r in rows:
        print("  " + "  ".join(str(r.get(c, "")).rjust(widths[c]) for c in cols))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Store completeness and freshness (E-6).")
    ap.add_argument("--store", nargs="*", choices=sorted(STORES), default=sorted(STORES))
    ap.add_argument("--symbols", nargs="*", default=None, help="limit the minute stores")
    ap.add_argument("--examples", type=int, default=3, help="dates named per finding")
    ap.add_argument("--theta", action="store_true", help="also probe the Theta Terminal")
    ap.add_argument("--json", action="store_true", help="machine-readable, no table")
    ap.add_argument("--strict", action="store_true", help="exit 1 if anything FAILs")
    ap.add_argument("-v", "--verbose", action="store_true", help="per-symbol table")
    ap.add_argument("--today", default=None, help="override 'today' for staleness (tests)")
    args = ap.parse_args(argv)

    from quant_brain.markets.equity_us import CALENDAR
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    out: dict[str, dict] = {}
    failed = False
    for name in args.store:
        path = STORES[name]
        if name == "odte":
            rep, rows = check_odte_store(path, CALENDAR, today=today, examples=args.examples)
            cols = ["symbol", "days", "first", "last", "rows", "empty", "truncated"]
        else:
            rep, rows = check_minute_store(path, CALENDAR, today=today, symbols=args.symbols,
                                           examples=args.examples)
            cols = ["symbol", "sessions", "rows", "first", "last", "missing", "truncated",
                    "sparse", "duplicates", "lag_days"]
        failed = failed or rep.failed
        out[name] = {"summary": rep.summary(),
                     "findings": [{"check": f.check, "severity": f.severity.value,
                                   "symbol": f.symbol, "detail": f.detail, "count": f.count}
                                  for f in rep.findings],
                     "symbols": rows}
        if not args.json:
            print(f"\n=== {name}  ({path})")
            if args.verbose:
                _print_table(rows, cols)
            for f in rep.findings:
                if f.severity is not Severity.INFO or args.verbose:
                    print(f.line())
            print(f"  {rep.summary()}")

    if args.theta:
        trep = Report()
        st = check_theta(trep)
        out["theta"] = {"status": st, "findings": [
            {"check": f.check, "severity": f.severity.value, "symbol": f.symbol,
             "detail": f.detail, "count": f.count} for f in trep.findings]}
        failed = failed or trep.failed
        if not args.json:
            print("\n=== theta terminal")
            for f in trep.findings:
                print(f.line())

    if args.json:
        print(json.dumps(out, indent=2, default=str))
    elif failed:
        print("\nFAIL findings present. Fix or exclude before trusting a run on this store.")

    return 1 if (args.strict and failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
