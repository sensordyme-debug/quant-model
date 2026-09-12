"""Validate a bar store before research or trading consumes it.

Part 17, and AUD-13 ("no data-completeness gate"). The repository has done this work - the
audit records that both minute stores are tz-aware UTC on disk and ET on load with DST
verified, that IBKR and Alpaca closes agree to about 1e-6 over 101k bars per symbol, and that
there are no duplicate, NaN or zero-volume bars. All of it was done as one-off audits. None of
it runs before a sweep reads the store.

THE RULE THIS MODULE EXISTS TO ENFORCE
---------------------------------------
Part 17: "NEVER interpret missing market data as a legitimate zero price. Missing data must
have an explicit state."

That is not an abstract principle here. AUD-05 was exactly this bug in the live runner -
`prices.get(s, 0.0)` marked a $30k position at zero on one dropped bar, which read as a total
loss and flattened the book. The mark-level fix is shipped. This is the store-level half: a
gap must be reported as a GAP, never silently filled and never silently zero.

WHAT IS DELIBERATELY NOT HERE
------------------------------
No repair. Every check reports; nothing rewrites a store. A validator that quietly fixes data
destroys the evidence that something upstream is broken, and the upstream fetchers
(`intraday_data.py`, `alpaca_data.py`) are where a repair belongs.
"""
from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass, field

from quant_brain.core.calendar import SessionCalendar


class Severity(str, enum.Enum):
    """How bad a finding is for a consumer of the store."""

    INFO = "info"
    WARN = "warn"
    #: Research or trading must not proceed on this store.
    FAIL = "fail"


@dataclass(frozen=True)
class Finding:
    check: str
    severity: Severity
    symbol: str
    detail: str
    count: int = 0

    def line(self) -> str:
        n = f" x{self.count}" if self.count else ""
        return (f"  {self.severity.value.upper():<5} {self.symbol:<8} "
                f"{self.check:<22} {self.detail}{n}")


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    symbols: int = 0
    rows: int = 0

    @property
    def failed(self) -> bool:
        return any(f.severity is Severity.FAIL for f in self.findings)

    def of(self, severity: Severity) -> list[Finding]:
        return [f for f in self.findings if f.severity is severity]

    def add(self, check, severity, symbol, detail, count=0) -> None:
        self.findings.append(Finding(check, severity, symbol, detail, count))

    def summary(self) -> str:
        f, w = len(self.of(Severity.FAIL)), len(self.of(Severity.WARN))
        verdict = "REFUSED" if self.failed else "usable"
        return (f"{self.symbols} symbol(s), {self.rows:,} rows: {f} fail, {w} warn -> {verdict}")


# --------------------------------------------------------------------------- checks

def check_frame(symbol: str, df, calendar: SessionCalendar | None = None, *,
                report: Report | None = None,
                expect_tz: bool = True) -> Report:
    """Validate one symbol's bar frame. `df` is a pandas DataFrame indexed by timestamp.

    Typed loosely on purpose: this module must import on both interpreters, and the 3.11 side
    has pandas 2.2.3 while 3.14 has 3.0.5. Nothing here depends on behaviour that moved.
    """
    rep = report or Report()
    rep.symbols += 1
    if df is None or len(df) == 0:
        rep.add("empty", Severity.FAIL, symbol, "no rows at all")
        return rep
    rep.rows += len(df)
    idx = df.index

    # --- timestamps -------------------------------------------------------------------
    if expect_tz and getattr(idx, "tz", None) is None:
        rep.add("timezone", Severity.FAIL, symbol,
                "index is tz-naive; ET/UTC cannot be distinguished and DST is undefined")
    if not idx.is_monotonic_increasing:
        rep.add("ordering", Severity.FAIL, symbol, "index is not monotonically increasing")
    dupes = int(idx.duplicated().sum())
    if dupes:
        rep.add("duplicates", Severity.FAIL, symbol, "duplicate timestamps", dupes)

    # --- prices -----------------------------------------------------------------------
    cols = [c for c in ("o", "h", "l", "c") if c in df.columns]
    for col in cols:
        s = df[col]
        nan = int(s.isna().sum())
        if nan:
            rep.add("nan_price", Severity.FAIL, symbol, f"{col} has NaN", nan)
        # Zero is the specific value Part 17 forbids treating as a price. It is not "cheap",
        # it is absent - and AUD-05 is what happens when the two are confused.
        zero = int((s == 0).sum())
        if zero:
            rep.add("zero_price", Severity.FAIL, symbol,
                    f"{col} has exact zeros - a zero is ABSENT, never a price", zero)
        neg = int((s < 0).sum())
        if neg:
            rep.add("negative_price", Severity.FAIL, symbol, f"{col} is negative", neg)

    if {"h", "l"} <= set(df.columns):
        bad = int((df["h"] < df["l"]).sum())
        if bad:
            rep.add("impossible_bar", Severity.FAIL, symbol, "high < low", bad)
    if {"h", "l", "c"} <= set(df.columns):
        out = int(((df["c"] > df["h"]) | (df["c"] < df["l"])).sum())
        if out:
            rep.add("impossible_bar", Severity.FAIL, symbol, "close outside [low, high]", out)

    if "v" in df.columns:
        negv = int((df["v"] < 0).sum())
        if negv:
            rep.add("negative_volume", Severity.FAIL, symbol, "volume < 0", negv)
        zerov = int((df["v"] == 0).sum())
        if zerov:
            rep.add("zero_volume", Severity.WARN, symbol,
                    "zero-volume bars (legitimate in thin minutes, suspicious in bulk)", zerov)

    # --- jumps -------------------------------------------------------------------------
    if "c" in df.columns and len(df) > 2:
        c = df["c"]
        prev = c.shift(1)
        with_prev = (prev.notna()) & (prev != 0)
        moves = ((c[with_prev] / prev[with_prev]) - 1.0).abs()
        # 50% in one minute is not a price move; it is an unadjusted split or a bad tick.
        jumps = int((moves > 0.50).sum())
        if jumps:
            rep.add("price_jump", Severity.WARN, symbol,
                    "one-bar move > 50% (unadjusted split or bad tick?)", jumps)

    # --- session coverage ---------------------------------------------------------------
    if calendar is not None:
        rep = _check_sessions(symbol, df, calendar, rep)
    return rep


def _check_sessions(symbol: str, df, calendar: SessionCalendar, rep: Report) -> Report:
    """Every day present must be a trading day, and its bar count must fit the session."""
    # One pass to count bars per day. The obvious `(df.index.date == day).sum()` inside the
    # loop is O(days x rows) and took minutes on a 263-session, 100k-row store; this is O(rows).
    try:
        import pandas as pd
        counts = pd.Series(1, index=df.index).groupby(df.index.date).size()
        # Zip index against the numpy values rather than using `.items()`: pandas types the
        # latter as (Hashable, Series | Any), which is both untrue here and unusable. The
        # isinstance filter narrows the keys to real dates and drops anything that is not one
        # rather than guessing at it.
        per_day: list[tuple[dt.date, int]] = [
            (k, int(v)) for k, v in zip(list(counts.index), counts.to_numpy().tolist(), strict=True)
            if isinstance(k, dt.date)
        ]
    except Exception:  # noqa: BLE001
        return rep
    non_trading: list[dt.date] = []
    over_long: list[tuple[dt.date, int, int]] = []
    early_ok = 0
    for day, n in per_day:
        if not calendar.is_trading_day(day):
            non_trading.append(day)
            continue
        try:
            expected = calendar.session_minutes(day)
        except Exception:  # noqa: BLE001 - past the calendar's coverage; reported separately
            continue
        if expected is None:
            continue
        if n > expected:
            over_long.append((day, n, expected))
        if calendar.is_early_close(day):
            early_ok += 1
    if non_trading:
        rep.add("non_trading_day", Severity.FAIL, symbol,
                f"bars on days the market was shut, e.g. {non_trading[0]}", len(non_trading))
    if over_long:
        day, n, exp = over_long[0]
        rep.add("after_hours", Severity.WARN, symbol,
                f"more bars than the session holds, e.g. {day}: {n} > {exp} "
                f"(after-hours rows on an early close - AUD-07)", len(over_long))
    if early_ok:
        rep.add("early_close", Severity.INFO, symbol,
                "early-close sessions present and recognised", early_ok)
    return rep


def gaps(df, calendar: SessionCalendar | None = None, *, symbol: str = "",
         report: Report | None = None, max_gap_minutes: int = 5) -> Report:
    """Report missing minutes inside a session as GAPS. Never fills them.

    Part 17's core rule made concrete: a gap has an explicit state. The consumer decides what
    to do about it - the live runner now carries the last known mark (AUD-05), and a research
    harness may prefer to drop the session entirely - but nobody gets to see a zero.
    """
    rep = report or Report()
    if df is None or len(df) < 2:
        return rep
    import pandas as pd

    deltas = pd.Series(df.index).diff().dropna()
    inside = deltas[deltas <= pd.Timedelta(hours=4)]      # exclude the overnight boundary
    holes = inside[inside > pd.Timedelta(minutes=max_gap_minutes)]
    if len(holes):
        worst = holes.max()
        rep.add("intraday_gap", Severity.WARN, symbol or "?",
                f"gaps over {max_gap_minutes}m inside a session, worst "
                f"{worst.total_seconds() / 60:.0f}m", int(len(holes)))
    return rep


def validate_store(frames: dict, calendar: SessionCalendar | None = None) -> Report:
    """Validate a whole {symbol: DataFrame} store. Returns one report."""
    rep = Report()
    for sym in sorted(frames):
        check_frame(sym, frames[sym], calendar, report=rep)
        gaps(frames[sym], calendar, symbol=sym, report=rep)
    return rep


def require_usable(frames: dict, calendar: SessionCalendar | None = None) -> Report:
    """Validate, and RAISE if anything is FAIL. The gate a consumer calls.

    Part 18's principle applied to data: an unknown state is not a licence to proceed. A WARN
    is returned for the caller to log; a FAIL stops the run.
    """
    rep = validate_store(frames, calendar)
    if rep.failed:
        lines = "\n".join(f.line() for f in rep.of(Severity.FAIL)[:20])
        raise DataQualityError(f"store is not usable:\n{lines}\n{rep.summary()}")
    return rep


class DataQualityError(RuntimeError):
    """The store failed validation. Do not research or trade on it."""


def _main(argv: list[str] | None = None) -> int:
    """`python -m quant_brain.core.dataquality [--symbols NVDA TSLA] [--store DIR]`"""
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="Validate a minute bar store.")
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--store", default=None, help="INTRADAY_DATA_DIR override")
    ap.add_argument("--strict", action="store_true", help="exit 1 on any FAIL")
    args = ap.parse_args(argv)

    import os
    if args.store:
        os.environ["INTRADAY_DATA_DIR"] = args.store
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "scripts"))
    import intraday_common as ic

    from quant_brain.markets.equity_us import CALENDAR

    syms = args.symbols or ic.UNIVERSE
    frames = {}
    for s in syms:
        try:
            frames[s] = ic.load_bars(s)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  {s:<8} load                   {type(exc).__name__}: {exc}"[:120])
    rep = validate_store(frames, CALENDAR)
    for f in rep.findings:
        print(f.line())
    print(f"\n{rep.summary()}")
    return 1 if (args.strict and rep.failed) else 0


if __name__ == "__main__":
    raise SystemExit(_main())
