"""E-6: pin the store-completeness checker, and above all the line it draws.

`store_health.py` exists to separate two things that look identical to a bar count:

    381 bars, 09:30 -> 15:59   thin name, skipped minutes           SPARSE, benign
    170 bars, 09:30 -> 12:19   fetch died at lunch                  TRUNCATED, poisons a backtest

Almost every test here is about that line. If truncation is ever reclassified as sparsity the
tool goes quiet on the one defect it was written for, and if sparsity is ever reclassified as
truncation the Alpaca store produces 5,710 false alarms and gets ignored - which is the same
outcome by a different route.

The tests run against the REAL US equity calendar rather than a stub, because the off-by-ones
that matter are calendar facts: a complete session's last bar starts at 15:59 (one minute before
the close), and an early close is 210 minutes, not 390. A stub calendar would let both through.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

pytest.importorskip("pyarrow", reason="the minute stores are parquet; 3.11 has no engine")

import pandas as pd  # noqa: E402
import store_health as sh  # noqa: E402

from quant_brain.core.dataquality import Severity  # noqa: E402
from quant_brain.markets.equity_us import CALENDAR  # noqa: E402

ET = "America/New_York"
FULL = dt.date(2024, 11, 27)        # ordinary 390-minute session
EARLY = dt.date(2024, 11, 29)       # Black Friday, 13:00 close, 210 minutes
HOLIDAY = dt.date(2024, 11, 28)     # Thanksgiving


# --------------------------------------------------------------------------- builders

def session_index(day: dt.date, *, start: str = "09:30", bars: int | None = None,
                  keep: list[int] | None = None) -> pd.DatetimeIndex:
    """Minute stamps for one session, in ET. `keep` selects offsets to make a frame sparse."""
    sess = CALENDAR.session(day)
    assert sess is not None
    first = pd.Timestamp(f"{day} {start}", tz=ET)
    n = bars if bars is not None else sess.minutes
    idx = pd.date_range(first, periods=n, freq="1min", tz=ET)
    if keep is not None:
        full = pd.date_range(pd.Timestamp(f"{day} {start}", tz=ET),
                             periods=sess.minutes, freq="1min", tz=ET)
        idx = full[keep]
    return pd.DatetimeIndex(idx)


def write_store(root, symbol: str, index: pd.DatetimeIndex):
    """Write a minute parquet the way the fetchers do: tz-aware UTC index, o/h/l/c/v."""
    root.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 100},
                      index=index.tz_convert("UTC"))
    df.index.name = "date"
    df.to_parquet(root / f"{symbol}.parquet")
    return root / f"{symbol}.parquet"


def shapes_for(index: pd.DatetimeIndex) -> list[sh.SessionShape]:
    return sh.session_shapes(index, CALENDAR)


def checks(rep, severity: Severity | None = None) -> set[str]:
    return {f.check for f in (rep.of(severity) if severity else rep.findings)}


# --------------------------------------------------------------------------- the line itself

def test_a_complete_session_is_neither_truncated_nor_sparse():
    """The off-by-one that would flag every session in both stores.

    Bars are stamped at their open, so the last bar of a 16:00 close starts at 15:59. Measuring
    `close - last_bar` without subtracting that minute makes every complete session look one
    minute short - harmless at a 15-minute threshold, but it is the same arithmetic the
    truncation test depends on, so it is pinned here rather than assumed.
    """
    s, = shapes_for(session_index(FULL))
    assert s.bars == 390 and s.expected == 390
    assert s.start_lag == 0 and s.end_lead == 0
    assert not s.truncated and not s.sparse
    assert s.fill == 1.0


def test_a_full_early_close_is_complete_at_210_bars_not_short_by_180():
    """AUD-07's trap in coverage form: 390 is wrong on 21 days of the last decade."""
    s, = shapes_for(session_index(EARLY))
    assert s.bars == 210 and s.expected == 210
    assert s.end_lead == 0
    assert not s.truncated and not s.sparse


def test_a_dead_fetch_is_truncated():
    """170/390 ending 12:19 - the exact shape found in data/minute on 2026-09-11."""
    s, = shapes_for(session_index(FULL, bars=170))
    assert s.bars == 170
    assert s.end_lead == pytest.approx(220)
    assert s.truncated
    assert "ends 220m short (170/390)" in s.why()


def test_a_late_start_is_truncated_too():
    s, = shapes_for(session_index(FULL, start="11:00", bars=300))
    assert s.start_lag == pytest.approx(90)
    assert s.truncated
    assert "starts 90m short" in s.why()


def test_scattered_holes_are_sparse_and_never_truncated():
    """The discrimination the whole module rests on.

    350 of 390 bars, 40 minutes missing at random inside the session, first bar on the open and
    last bar on the close. A bar count alone cannot tell this from the 170-bar dead fetch above;
    the span can, and must, because this shape is 5,710 sessions of the Alpaca store and is what
    a trade-gated consolidated tape legitimately looks like for a thin name.
    """
    keep = [0] + list(range(1, 389, 11))[:348] + [389]
    s, = shapes_for(session_index(FULL, keep=keep))
    assert s.bars < 390
    assert s.start_lag == 0 and s.end_lead == 0
    assert not s.truncated
    assert s.sparse


def test_a_small_gap_at_the_close_is_below_the_threshold():
    """14 minutes of missing tail is thinness, 16 is a defect. The boundary is a choice; pin it."""
    ok, = shapes_for(session_index(FULL, bars=390 - sh.TRUNCATION_MINUTES + 1))
    bad, = shapes_for(session_index(FULL, bars=390 - sh.TRUNCATION_MINUTES - 1))
    assert not ok.truncated
    assert bad.truncated


# --------------------------------------------------------------------------- store level

def concat_sessions(parts: list[pd.DatetimeIndex]) -> pd.DatetimeIndex:
    """Join session indexes into one store index, in ET.

    `.values` drops the zone and yields UTC instants, so the result must be localized to UTC and
    then converted - localizing straight to ET shifts every session by five hours and makes a
    complete day look truncated, which is how this helper was wrong the first time.
    """
    return pd.DatetimeIndex(pd.concat([pd.Series(p) for p in parts]).values,
                            tz="UTC").tz_convert(ET)


def build_minute_store(tmp_path, spec: dict[str, list], name: str = "minute"):
    """spec: {symbol: [index, ...]} - one index per session, concatenated."""
    root = tmp_path / name
    for sym, parts in spec.items():
        write_store(root, sym, concat_sessions(parts))
    return root


def week(days: list[dt.date], **kw) -> list[pd.DatetimeIndex]:
    return [session_index(d, **kw) for d in days]


DAYS = [dt.date(2024, 11, 25), dt.date(2024, 11, 26), FULL, EARLY, dt.date(2024, 12, 2)]
AFTER = dt.date(2024, 12, 3)   # 'today' for staleness: one trading day past the last session


def test_a_whole_store_produces_no_warning_and_no_fail(tmp_path):
    root = build_minute_store(tmp_path, {"AAA": week(DAYS), "BBB": week(DAYS)})
    rep, rows = sh.check_minute_store(root, CALENDAR, today=AFTER)
    assert not rep.failed
    assert rep.of(Severity.WARN) == []
    assert [r["sessions"] for r in rows] == [5, 5]
    assert rep.rows == 2 * (390 * 3 + 210 + 390)


def test_a_skipped_day_inside_the_range_is_reported_with_its_date(tmp_path):
    root = build_minute_store(tmp_path, {"AAA": week([d for d in DAYS if d != FULL])})
    rep, _ = sh.check_minute_store(root, CALENDAR, today=AFTER)
    miss, = [f for f in rep.findings if f.check == "missing_session"]
    assert miss.severity is Severity.WARN
    assert str(FULL) in miss.detail
    assert miss.count == 1


def test_a_holiday_with_bars_is_a_fail(tmp_path):
    """Structural corruption, not a coverage gap: the file describes a day that did not exist."""
    idx = pd.DatetimeIndex(pd.date_range(pd.Timestamp(f"{HOLIDAY} 09:30", tz=ET),
                                         periods=390, freq="1min", tz=ET))
    root = build_minute_store(tmp_path, {"AAA": week(DAYS) + [idx]})
    rep, _ = sh.check_minute_store(root, CALENDAR, today=AFTER)
    assert rep.failed
    assert "non_trading_day" in checks(rep, Severity.FAIL)


def test_duplicate_timestamps_are_a_fail(tmp_path):
    root = build_minute_store(tmp_path, {"AAA": week(DAYS) + [session_index(FULL)]})
    rep, rows = sh.check_minute_store(root, CALENDAR, today=AFTER)
    assert rep.failed
    assert "duplicates" in checks(rep, Severity.FAIL)
    assert rows[0]["duplicates"] == 390


def test_an_interior_truncation_warns_but_does_not_fail(tmp_path):
    """A dead fetch in the middle of history is a date to exclude, not a reason to stop."""
    parts = [session_index(d, bars=170 if d == FULL else None) for d in DAYS]
    root = build_minute_store(tmp_path, {"AAA": parts})
    rep, rows = sh.check_minute_store(root, CALENDAR, today=AFTER)
    assert not rep.failed
    trunc, = [f for f in rep.findings if f.check == "truncated_session"]
    assert str(FULL) in trunc.detail and "worst 220m" in trunc.detail
    assert rows[0]["truncated"] == 1


def test_a_truncated_LAST_session_is_the_one_coverage_fail(tmp_path):
    """The promotion the module argues for: the live edge of the store is broken right now."""
    parts = [session_index(d, bars=170 if d == DAYS[-1] else None) for d in DAYS]
    root = build_minute_store(tmp_path, {"AAA": parts, "BBB": week(DAYS)})
    rep, _ = sh.check_minute_store(root, CALENDAR, today=AFTER)
    assert rep.failed
    tail, = rep.of(Severity.FAIL)
    assert tail.check == "truncated_tail"
    assert str(DAYS[-1]) in tail.detail
    assert "1 of 2 symbols" in tail.detail


def test_one_dead_fetch_across_every_symbol_is_reported_once(tmp_path):
    """The roll-up. Sixteen copies of one fact is a report nobody reads twice."""
    spec = {f"S{i}": [session_index(d, bars=170 if d == FULL else None) for d in DAYS]
            for i in range(6)}
    root = build_minute_store(tmp_path, spec)
    rep, _ = sh.check_minute_store(root, CALENDAR, today=AFTER)
    trunc = [f for f in rep.findings if f.check == "truncated_session"]
    assert len(trunc) == 1
    assert trunc[0].count == 6           # six symbol-sessions ...
    assert "(6 sym:" in trunc[0].detail  # ... named as one date


def test_a_store_that_stopped_updating_is_stale(tmp_path):
    root = build_minute_store(tmp_path, {"AAA": week(DAYS)})
    fresh, _ = sh.check_minute_store(root, CALENDAR, today=AFTER)
    assert "stale" not in checks(fresh)
    later, _ = sh.check_minute_store(root, CALENDAR, today=dt.date(2024, 12, 20))
    stale, = [f for f in later.findings if f.check == "stale"]
    assert stale.severity is Severity.WARN and "AAA" in stale.detail


def test_symbols_with_different_start_dates_are_flagged_as_skew(tmp_path):
    root = build_minute_store(tmp_path, {"AAA": week(DAYS), "BBB": week(DAYS[2:])})
    rep, _ = sh.check_minute_store(root, CALENDAR, today=AFTER)
    skew, = [f for f in rep.findings if f.check == "coverage_skew"]
    assert skew.severity is Severity.INFO
    assert "BBB" in skew.detail


def test_an_unreadable_file_fails_instead_of_raising(tmp_path):
    root = tmp_path / "minute"
    root.mkdir()
    (root / "AAA.parquet").write_bytes(b"not a parquet file")
    rep, _ = sh.check_minute_store(root, CALENDAR, today=AFTER)
    assert rep.failed and "unreadable" in checks(rep, Severity.FAIL)


def test_an_absent_store_warns_rather_than_crashing(tmp_path):
    rep, rows = sh.check_minute_store(tmp_path / "nope", CALENDAR, today=AFTER)
    assert rows == [] and "absent" in checks(rep, Severity.WARN)
    assert not rep.failed


# --------------------------------------------------------------------------- 0DTE chain store

def write_chain(root, symbol: str, day: dt.date, *, last: str = "15:55", rows: int = 8):
    d = root / symbol
    d.mkdir(parents=True, exist_ok=True)
    ts = pd.date_range(pd.Timestamp(f"{day} 09:30"), pd.Timestamp(f"{day} {last}"), periods=rows)
    pd.DataFrame({"strike": 100.0, "right": "C", "timestamp": ts, "bid": 1.0, "ask": 1.1,
                  "bid_size": 1, "ask_size": 1}).to_parquet(d / f"{day}.parquet", index=False)


ODTE_DAYS = [dt.date(2024, 11, 25), dt.date(2024, 11, 26), FULL, EARLY, dt.date(2024, 12, 2)]


def test_a_whole_chain_store_is_clean(tmp_path):
    root = tmp_path / "odte"
    for d in ODTE_DAYS:
        write_chain(root, "SPY", d, last="12:55" if d == EARLY else "15:55")
    rep, rows = sh.check_odte_store(root, CALENDAR, today=AFTER)
    assert not rep.failed and rep.of(Severity.WARN) == []
    assert rows[0]["days"] == 5


def test_a_chain_that_stops_at_lunch_is_truncated(tmp_path):
    root = tmp_path / "odte"
    for d in ODTE_DAYS:
        write_chain(root, "SPY", d, last="12:00" if d == FULL else
                    ("12:55" if d == EARLY else "15:55"))
    rep, _ = sh.check_odte_store(root, CALENDAR, today=AFTER)
    t, = [f for f in rep.findings if f.check == "truncated_chain"]
    assert str(FULL) in t.detail and t.count == 1


def test_a_missing_expiry_counts_only_after_spy_went_daily(tmp_path):
    """Before 2023-05 an absent file is the instrument (weeklies); after it, a dead fetch."""
    root = tmp_path / "odte"
    old = [dt.date(2019, 1, 4), dt.date(2019, 1, 11)]      # two Fridays, a week apart
    for d in old:
        write_chain(root, "SPY", d)
    rep, _ = sh.check_odte_store(root, CALENDAR, today=dt.date(2019, 1, 15))
    assert "missing_chain" not in checks(rep)

    root2 = tmp_path / "odte2"
    for d in [d for d in ODTE_DAYS if d != FULL]:
        write_chain(root2, "SPY", d, last="12:55" if d == EARLY else "15:55")
    rep2, _ = sh.check_odte_store(root2, CALENDAR, today=AFTER)
    m, = [f for f in rep2.findings if f.check == "missing_chain"]
    assert str(FULL) in m.detail


# --------------------------------------------------------------------------- CLI

def run_cli(tmp_path, monkeypatch, argv, *, spec=None):
    root = build_minute_store(tmp_path, spec or {"AAA": week(DAYS)})
    monkeypatch.setitem(sh.STORES, "minute", root)
    return sh.main(["--store", "minute", "--today", str(AFTER), *argv])


def test_the_cli_exits_zero_on_a_clean_store(tmp_path, monkeypatch, capsys):
    assert run_cli(tmp_path, monkeypatch, ["--strict"]) == 0
    assert "0 fail" in capsys.readouterr().out


def test_a_fail_only_changes_the_exit_code_under_strict(tmp_path, monkeypatch):
    """A health report must never be the thing that breaks somebody's cron by default."""
    broken = {"AAA": [session_index(d, bars=170 if d == DAYS[-1] else None) for d in DAYS]}
    assert run_cli(tmp_path, monkeypatch, [], spec=broken) == 0
    assert run_cli(tmp_path, monkeypatch, ["--strict"], spec=broken) == 1


def test_json_output_is_parseable_and_names_the_findings(tmp_path, monkeypatch, capsys):
    broken = {"AAA": [session_index(d, bars=170 if d == DAYS[-1] else None) for d in DAYS]}
    run_cli(tmp_path, monkeypatch, ["--json"], spec=broken)
    doc = json.loads(capsys.readouterr().out)
    assert {f["check"] for f in doc["minute"]["findings"]} >= {"truncated_session", "truncated_tail"}
    assert doc["minute"]["symbols"][0]["symbol"] == "AAA"


# ------------------------------------------------- the launcher's use of the shape test
#
# `intraday_launch.last_session()` is the one consumer of `session_shapes` on the live path: it
# picks the session the 09:25 preflight replays. These tests live here rather than in
# test_launch_preflight.py because what they pin is the shape test itself - the two cases where
# the bar count it replaced gave the wrong answer.

def store_with(monkeypatch, frames: dict[str, pd.DatetimeIndex]):
    import intraday_common as ic
    import intraday_launch as il
    monkeypatch.setattr(il, "UNIVERSE", sorted(frames))
    monkeypatch.setattr(il, "load_bars", lambda s: pd.DataFrame(
        {"c": 1.0}, index=frames[s]) if s in frames else pd.DataFrame())
    assert ic is not None
    return il


def test_the_preflight_may_replay_a_complete_early_close(monkeypatch):
    """The 210-bar regression. `>= 300 bars` made every early close unreplayable, so the gate
    could never exercise the calendar-aware flatten on the mornings AUD-07 was written for."""
    parts = [session_index(d) for d in
             [dt.date(2024, 11, 25), dt.date(2024, 11, 26), FULL, EARLY]]
    frames = {s: concat_sessions(parts) for s in ("AAA", "BBB")}
    il = store_with(monkeypatch, frames)
    assert il.last_session() == EARLY


def test_the_preflight_refuses_a_session_that_died_after_300_bars(monkeypatch):
    """The other direction: 310/390 passed the count test and replayed with an open book."""
    parts = [session_index(d, bars=310 if d == EARLY else None)
             for d in [dt.date(2024, 11, 25), dt.date(2024, 11, 26), FULL]]
    parts.append(session_index(dt.date(2024, 12, 2), bars=310))
    frames = {s: concat_sessions(parts) for s in ("AAA", "BBB")}
    il = store_with(monkeypatch, frames)
    assert il.last_session() == FULL


def test_the_launcher_falls_back_rather_than_failing_to_start(monkeypatch):
    """A completeness checker must never be the reason the sleeve does not trade."""
    import builtins

    import intraday_launch as il
    frames = {s: concat_sessions([session_index(FULL), session_index(dt.date(2024, 12, 2))])
              for s in ("AAA", "BBB")}
    store_with(monkeypatch, frames)
    real_import = builtins.__import__

    def no_store_health(name, *a, **k):
        if name == "store_health":
            raise ImportError("simulated: module missing")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_store_health)
    assert il.last_session() == dt.date(2024, 12, 2)


def test_theta_probe_never_raises_and_never_fails_the_run(monkeypatch):
    """The terminal is started on demand; down is normal and must not read as a data defect."""
    import theta_data as td

    from quant_brain.core.dataquality import Report

    for status, severity in [({"alive": True}, Severity.INFO),
                             ({"alive": False, "listening": True, "detail": "no data"}, Severity.WARN),
                             ({"alive": False, "listening": False}, Severity.INFO)]:
        rep = Report()
        monkeypatch.setattr(td, "status", lambda s=status: s)
        sh.check_theta(rep)
        assert rep.findings[0].severity is severity
        assert not rep.failed

    rep = Report()
    monkeypatch.setattr(td, "status", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    sh.check_theta(rep)
    assert not rep.failed


# ------------------------------------------------- the LEAN daily store's tradeability (D-9)
#
# A different defect from everything above. The minute checks ask whether a session is WHOLE;
# the daily store has one bar per session, so the only question left is whether the bar's price
# is one an order can transact at. D-7 proved it often is not: this repo's fetcher writes
# split-adjusted prices with `split_factor = 1`, so a reverse-split name's adjusted price runs to
# $10^11 and a sleeve-sized order rounds to zero shares. The failure is SILENT - LEAN emits no
# order at all - which is why these tests pin the count, the span and the scale, not just a flag.

def build_daily_store(tmp_path, spec: dict[str, list[tuple[dt.date, float]]],
                      factors: dict[str, list[tuple[dt.date, float]]] | None = None):
    """spec: {symbol: [(date, raw_close), ...]}; factors: {symbol: [(date, price_factor), ...]}.

    Writes LEAN's own layout - `daily/<sym>.zip` holding `<sym>.csv` in deci-cents, and
    `factor_files/<sym>.csv` - so the test reads through the same `lean_prices` code the engine's
    ADJUSTED mode mirrors rather than through a stub of it.
    """
    import zipfile

    root = tmp_path / "lean"
    (root / "daily").mkdir(parents=True, exist_ok=True)
    (root / "factor_files").mkdir(parents=True, exist_ok=True)
    for sym, bars in spec.items():
        csv = "\n".join(
            f"{d:%Y%m%d} 00:00,{int(round(px * sh_scale))},{int(round(px * sh_scale))},"
            f"{int(round(px * sh_scale))},{int(round(px * sh_scale))},1000000"
            for d, px in bars)
        with zipfile.ZipFile(root / "daily" / f"{sym.lower()}.zip", "w") as z:
            z.writestr(f"{sym.lower()}.csv", csv)
        rows = (factors or {}).get(sym, [(bars[-1][0], 1.0)])
        (root / "factor_files" / f"{sym.lower()}.csv").write_text(
            "\n".join(f"{d:%Y%m%d},{f},1,0" for d, f in rows))
    return root


sh_scale = 10000   # LEAN's deci-cent price scale; `lean_prices.SCALE`


DAILY_DAYS = [dt.date(2024, 11, 25), dt.date(2024, 11, 26), FULL, dt.date(2024, 12, 2)]


def daily_report(tmp_path, monkeypatch, spec, factors=None, **kw):
    import lean_prices

    root = build_daily_store(tmp_path, spec, factors)
    monkeypatch.setattr(lean_prices, "EQUITY", root)
    return sh.check_daily_store(root / "daily", CALENDAR, today=AFTER, **kw)


def flat(price: float) -> list[tuple[dt.date, float]]:
    return [(d, price) for d in DAILY_DAYS]


def test_an_ordinary_price_is_tradeable_and_produces_no_defect(tmp_path, monkeypatch):
    rep, rows = daily_report(tmp_path, monkeypatch, {"AAA": flat(100.0)})
    assert not rep.failed
    assert rep.of(Severity.WARN) == []
    assert rows[0]["zero_order"] == 0 and rows[0]["sessions"] == 4
    assert rows[0]["adj_max"] == pytest.approx(100.0)


def test_an_adjusted_price_above_the_order_is_untradeable_and_fails(tmp_path, monkeypatch):
    """The D-9 defect itself: a reverse-split name priced past the order size."""
    bars = [(d, 100.0 if d == DAILY_DAYS[-1] else 5e10) for d in DAILY_DAYS]
    rep, rows = daily_report(tmp_path, monkeypatch, {"AAA": bars})
    assert rep.failed
    (f,) = [f for f in rep.findings if f.check == "untradeable"]
    assert f.severity is Severity.FAIL and f.symbol == "AAA" and f.count == 3
    assert "ZERO shares on 3 of 4" in f.detail
    assert f"{DAILY_DAYS[0]}..{DAILY_DAYS[-2]}" in f.detail   # the span, not every date
    assert rows[0]["zero_order"] == 3 and rows[0]["zero_pct"] == 75.0


def test_the_price_factor_is_what_makes_a_clean_raw_price_untradeable(tmp_path, monkeypatch):
    """The mechanism D-7 found: the bar on disk is ordinary, the FACTOR is what LEAN pays.

    Without this the check could be satisfied by reading the stored close alone and would miss
    every symbol whose adjustment lives in the factor file - which is where LEAN's does.
    """
    factors = {"AAA": [(DAILY_DAYS[1], 1e9), (DAILY_DAYS[-1], 1.0)]}
    rep, rows = daily_report(tmp_path, monkeypatch, {"AAA": flat(100.0)}, factors)
    assert rep.failed
    assert rows[0]["zero_order"] == 2          # the two bars on or before the 1e9 factor row
    assert rows[0]["adj_max"] == pytest.approx(1e11)


def test_the_verdict_is_about_the_ORDER_and_not_the_price(tmp_path, monkeypatch):
    """Same store, two order sizes: $1k cannot buy a $5k share and $10k can.

    Pins that `--notional` is the assertion's scale. A check that hard-coded a price ceiling
    would call this symbol broken or fine forever, and neither is true of a real book.
    """
    spec = {"AAA": flat(5000.0)}
    assert daily_report(tmp_path, monkeypatch, spec, notional=1_000.0)[0].failed
    assert not daily_report(tmp_path, monkeypatch, spec, notional=10_000.0)[0].failed


def test_adj_max_is_exactly_the_smallest_order_that_always_buys_a_share(tmp_path, monkeypatch):
    """`adj_max` is the number a reader acts on, so the boundary is pinned rather than implied."""
    spec = {"AAA": flat(250.0)}
    rep, rows = daily_report(tmp_path, monkeypatch, spec, notional=250.0)
    assert not rep.failed and rows[0]["adj_max"] == pytest.approx(250.0)
    assert daily_report(tmp_path, monkeypatch, spec, notional=249.99)[0].failed


def test_the_headroom_line_reports_the_clean_symbols_separately(tmp_path, monkeypatch):
    """One broken symbol must not hide the headroom of the rest - it is 8 orders of magnitude
    away, so the store-wide maximum on its own says nothing about a book that never held it."""
    rep, _ = daily_report(tmp_path, monkeypatch,
                          {"AAA": flat(100.0), "BBB": flat(400.0), "ZZZ": flat(5e10)})
    assert "ZZZ" in [f for f in rep.findings if f.check == "headroom"][0].detail
    assert "$400 (BBB)" in [f for f in rep.findings if f.check == "headroom_clean"][0].detail


def test_an_unreadable_daily_zip_fails_instead_of_raising(tmp_path, monkeypatch):
    import lean_prices

    root = build_daily_store(tmp_path, {"AAA": flat(100.0)})
    (root / "daily" / "aaa.zip").write_bytes(b"not a zip")
    monkeypatch.setattr(lean_prices, "EQUITY", root)
    rep, rows = sh.check_daily_store(root / "daily", CALENDAR, today=AFTER)
    assert rep.failed and rep.findings[0].check == "unreadable"
    assert rows[0]["sessions"] == 0


def test_an_absent_daily_store_warns_rather_than_crashing(tmp_path):
    rep, rows = sh.check_daily_store(tmp_path / "nope", CALENDAR, today=AFTER)
    assert not rep.failed and rep.findings[0].check == "absent" and rows == []


def test_the_daily_store_reaches_the_cli_and_strict_exits_one(tmp_path, monkeypatch, capsys):
    import lean_prices

    root = build_daily_store(tmp_path, {"AAA": flat(5e10)})
    monkeypatch.setattr(lean_prices, "EQUITY", root)
    monkeypatch.setitem(sh.STORES, "daily", root / "daily")
    argv = ["--store", "daily", "--today", str(AFTER)]
    assert sh.main(argv) == 0                     # a report never breaks somebody's cron
    assert sh.main([*argv, "--strict"]) == 1
    assert "untradeable" in capsys.readouterr().out
