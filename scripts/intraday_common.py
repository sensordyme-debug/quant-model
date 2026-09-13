"""Shared pieces of the intraday (active) sleeve: universe, bar store, cost model, logging.

Used by scripts/intraday_data.py (fetch), scripts/intraday_backtest.py (research) and
scripts/intraday_trader.py (live). Keeping them here is what guarantees the backtest and
the live loop see identical bars, costs and universe.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
LIVE = REPO / "live"
#: Minute-bar store: <SYM>.parquet, gitignored. Default is the IBKR store; set INTRADAY_DATA_DIR
#: to data/minute_alpaca to run the same code on the Alpaca SIP store (scripts/alpaca_data.py).
DATA_DIR = Path(os.environ.get("INTRADAY_DATA_DIR", REPO / "data" / "minute"))
ET = ZoneInfo("America/New_York")

#: Intraday sleeve universe. Deliberately DISJOINT from the daily champion's traded universe
#: (SPY/QQQ/IWM/DIA/XLK/XLF/XLE/TLT/GLD/UPRO/TQQQ/TMF) so the two sleeves never hold the same
#: symbol and each can flatten its own book without touching the other's.
UNIVERSE = ["NVDA", "TSLA", "AAPL", "MSFT", "META", "AMD", "AMZN", "GOOGL", "AVGO", "NFLX",
            "SOXL", "SOXS", "PLTR", "MSTR", "COIN", "SMCI"]
DAILY_SLEEVE_UNIVERSE = {"SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "TLT", "GLD", "UPRO", "TQQQ", "TMF"}
assert not set(UNIVERSE) & DAILY_SLEEVE_UNIVERSE

#: L-1 research universe: the 3x index ETFs, in inverse pairs (semis, Nasdaq-100, S&P 500).
#: **This is not the deployed sleeve universe** - it is what scripts/sweep_l1.py studies. TQQQ and
#: UPRO are the daily champion's own instruments, so only LEVERAGED_DEPLOYABLE could ever be traded
#: by this sleeve without breaking the disjointness rule (AGENTS.md); the other two are carried in
#: the study because dropping half of each pair would confound "does leverage revert" with "which
#: leg was available".
LEVERAGED_UNIVERSE = ["SOXL", "SOXS", "TQQQ", "SQQQ", "UPRO", "SPXU"]
LEVERAGED_DEPLOYABLE = [s for s in LEVERAGED_UNIVERSE if s not in DAILY_SLEEVE_UNIVERSE]

#: Regular session in ET. Bars are stamped at their START (IBKR convention), so the last
#: regular bar starts at 15:59.
SESSION_OPEN = dt.time(9, 30)
SESSION_CLOSE = dt.time(16, 0)

#: AUD-07 / D-6: trim every session to ITS OWN calendar close, not to a hard-coded 16:00.
#: `scripts/alpaca_data.py` filtered incoming bars on the literal 09:30-16:00 window, so all 21
#: early closes 2016-2025 in `data/minute_alpaca` carry 13:00-15:59 bars - 22,081 rows over the
#: sleeve universe - that are POST-MARKET prints wearing an RTH timestamp: only ~31% of those
#: minutes print at all and they carry a median 14.3% of the volume the same clock window carries
#: on the five regular sessions before them, so a fill there priced at the harness's 1.5 bps is
#: fiction by about 7x. The IBKR store (`data/minute`) was fetched RTH-only and already stops at
#: 12:59 on both early closes inside its span, which is why this is a no-op for the live trader.
#: Set False only to reproduce a row already in research/experiments.jsonl.
CALENDAR_TRIM = True

#: Cost model shared by backtest and live sizing. IBKR Pro tiered-ish: $0.005/share, $1 min,
#: capped at 1% of trade value; plus a slippage/spread charge in basis points of notional
#: (these names are the most liquid in the market; half-spread is ~0.5-1 bp, and a market
#: order at a 1-minute bar close is charged 1.5 bp in total to stay honest).
COMMISSION_PER_SHARE = 0.005
COMMISSION_MIN = 1.0
SLIPPAGE_BPS = 1.5


#: Framework constants shared by the backtester and the live trader so they cannot drift.
MIN_CHANGE = 0.02            # rebalance a name only when the change is >= 2% of sleeve equity (or to flat)
PER_SYMBOL_HARD_CAP = 0.20   # |weight| ceiling per name, on top of any strategy cap
GROSS_HARD_CAP = 1.6         # sum |weights| ceiling; with the daily sleeve's ~1.2x overnight book this stays under 4x DT buying power
DAILY_LOSS_LIMIT = 0.025     # -2.5% of start-of-day NAV -> flatten and stop for the day
FLATTEN_MINUTE = 368         # 15:38 ET: target zero from here so the book is flat before the 15:45 daily rebalance
EXIT_MINUTE = 372            # 15:42 ET: live loop exits


#: Cumulative split factor per store, {SYM: [[iso_date, factor], ...]} sorted by date, written by
#: `scripts/alpaca_data.py --splits`. A store of SPLIT-ADJUSTED bars (data/minute_alpaca) prices a
#: 2016 share of NVDA at ~1/40th of what it traded at, so sizing a position in dollars buys ~40x
#: the shares that were really bought - and IBKR charges per SHARE, so the commission model reads
#: 40x too high (and hits its 1% cap, i.e. 100 bps, on names that split a lot). `factor` is
#: raw_close / adjusted_close on that date, so real_shares = adjusted_shares / factor. The raw IBKR
#: store has no such file and every factor is 1.0, which is why this is a no-op for the live trader.
SPLITS_FILE = "_splits.json"
_SPLITS: dict[str, list] | None = None


def _splits() -> dict[str, list]:
    global _SPLITS
    if _SPLITS is None:
        p = DATA_DIR / SPLITS_FILE
        try:
            _SPLITS = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except Exception:  # noqa: BLE001 - a broken file must not silently change costs
            _SPLITS = {}
    return _SPLITS


def share_scale(symbol: str, day) -> float:
    """adjusted shares per real share on `day` (1.0 when the store is unadjusted)."""
    segs = _splits().get(symbol.upper())
    if not segs:
        return 1.0
    d = str(day)
    f = segs[0][1]
    for start, factor in segs:
        if start <= d:
            f = factor
        else:
            break
    return float(f) or 1.0


#: US regulatory pass-throughs. They are charged on SELLS only, they are not part of IBKR's
#: commission tier, and the harness omitted them until A-5 part 2 measured them against IBKR's own
#: commissionReport on the first live session (2026-09-10). Both rates were fitted jointly on that
#: session's five sells and reproduce every one of them exactly, to the cent (the twelve buys
#: already matched the old model to $0.004), so these are IBKR's posted 2026 rates, not estimates:
#: SEC Section 31 fee $20.60 per $1,000,000 of proceeds and FINRA TAF $0.000198 per share.
SEC_FEE_RATE = 20.60e-6
TAF_PER_SHARE = 0.000198
TAF_CAP = 8.30


def commission(shares: float, price: float, scale: float = 1.0) -> float:
    """IBKR per-share commission plus the sell-side regulatory fees.

    `scale` is share_scale(): the per-share term is charged on the real share count, while the
    1% cap is on notional, which splits leave unchanged.

    **`shares` must keep its sign.** A negative `shares` is a sale and pays SEC_FEE_RATE on the
    proceeds and TAF_PER_SHARE on the real share count on top of the commission; a purchase pays
    neither. Both live call sites pass a signed quantity. Passing an absolute value silently
    reverts to the pre-2026-09-10 model, which undercharged a round trip by ~0.21 bps of the
    sell leg (~0.10 bps of turnover, ~$55/day on this sleeve's $5.46M/day)."""
    real = abs(shares) / (scale or 1.0)
    c = max(COMMISSION_MIN, real * COMMISSION_PER_SHARE)
    c = min(c, 0.01 * abs(shares) * price)
    if shares < 0:
        c += abs(shares) * price * SEC_FEE_RATE + min(real * TAF_PER_SHARE, TAF_CAP)
    return c


def slippage(shares: float, price: float) -> float:
    return abs(shares) * price * SLIPPAGE_BPS / 1e4


def volume_limits(df: pd.DataFrame, lookback: int = 20, min_sessions: int = 5) -> pd.DataFrame:
    """Trailing median volume per (session, minute-of-day) - the causal denominator for A-11.

    Returns a frame indexed by session date with one column per minute-of-day (0 = 09:30), whose
    row for day D is the median volume of that minute over the `lookback` sessions *strictly
    before* D. Nothing from D itself enters, so a participation cap built on it is knowable at
    decision time. NaN until `min_sessions` prior sessions exist; callers treat NaN as "no cap".

    Volumes are in the same share convention as the store's prices: the Alpaca store adjusts both
    (dollar volume is continuous across NVDA's 2024 10:1 split), so an order's participation ratio
    is split-scale-invariant and needs no `share_scale()` correction.
    """
    if df.empty:
        return pd.DataFrame()
    mod = (df.index.hour - 9) * 60 + df.index.minute - 30
    piv = df["v"].groupby([df.index.date, mod]).sum().unstack()
    return piv.shift(1).rolling(lookback, min_periods=min_sessions).median()


def parquet_path(symbol: str) -> Path:
    return DATA_DIR / f"{symbol.upper()}.parquet"


def load_bars(symbol: str, start: dt.date | None = None, end: dt.date | None = None,
              rth_only: bool = True) -> pd.DataFrame:
    """1-minute bars for one symbol: DataFrame[o,h,l,c,v] with a tz-aware ET DatetimeIndex."""
    p = parquet_path(symbol)
    if not p.exists():
        return pd.DataFrame(columns=["o", "h", "l", "c", "v"])
    df = pd.read_parquet(p)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(ET)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    if start is not None:
        df = df[df.index >= pd.Timestamp(start, tz=ET)]
    if end is not None:
        df = df[df.index < pd.Timestamp(end, tz=ET) + pd.Timedelta(days=1)]
    if rth_only:
        t = df.index.time
        df = df[(t >= SESSION_OPEN) & (t < SESSION_CLOSE)]
        if CALENDAR_TRIM and len(df):
            df = calendar_trim(df)
    return df


def calendar_trim(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows the exchange calendar says are not in that day's session (AUD-07).

    Two kinds of row go: anything at or after a 13:00 early close, and anything on a full-day
    closure. Deliberately a pure subset of what is passed in - it never fills, shifts or
    reindexes, so a store that is already correct comes back identical (`is` is not promised,
    equality is).

    Never raises. A loader is on the live path, and a calendar import failure or a date past
    `CALENDAR.coverage_end` must degrade to the pre-AUD-07 behaviour rather than stop the
    sleeve from trading; `intraday_launch.py` and `paper_trade.py` already call
    `check_covered` where an expiry should be an exception.
    """
    try:
        from quant_brain.markets.equity_us import CALENDAR
    except Exception:  # noqa: BLE001 - the calendar must never be the outage
        return df
    days = pd.Index(df.index.date)
    uniq = set(days)
    hit_e = uniq & CALENDAR.early_closes()
    hit_h = uniq & CALENDAR.holidays()
    if not hit_e and not hit_h:
        return df
    keep = ~days.isin(hit_h)
    times = df.index.time
    for d in hit_e:
        # the close comes from the session, not a 13:00 literal, so a differently-shortened
        # session would be trimmed correctly without touching this function
        sess = CALENDAR.session(d)
        if sess is None:
            continue
        keep &= ~((days == d) & (times >= sess.close_t))
    return df[keep]


#: A merge is refused when the median |new/old - 1| over the overlapping bars exceeds this and at
#: least REBASIS_MIN_BARS bars overlap. A split rebases the whole history by a factor of 2..200, so
#: the statistic it has to separate is ~1.0 against >= 0.5; 2% leaves room for IBKR's own bar
#: revisions (same source, same venue, typically 0) without coming near a split.
REBASIS_TOL = 0.02
REBASIS_MIN_BARS = 10


class BasisMismatch(ValueError):
    """Incoming bars disagree with the stored ones where they overlap (AUD-15)."""


def basis_mismatch(old: pd.DataFrame, new: pd.DataFrame) -> dict | None:
    """The overlap statistic `save_bars` refuses on, or None when the two agree.

    AUD-15: IBKR serves SPLIT-ADJUSTED bars on the basis current at fetch time, so the first
    incremental fetch after a split returns a history rebased by the split ratio. Merged into a
    store on the old basis that produces one parquet holding two price scales, silently, with no
    gap and no duplicate timestamp to find it by - and every feature, position size and per-share
    commission computed across the seam is wrong by the ratio. The overlap is the only place the
    two bases are comparable, so it is where the merge has to be checked.
    """
    common = old.index.intersection(new.index)
    if len(common) < REBASIS_MIN_BARS or "c" not in old.columns or "c" not in new.columns:
        return None
    a = pd.to_numeric(old.loc[common, "c"], errors="coerce")
    b = pd.to_numeric(new.loc[common, "c"], errors="coerce")
    ok = a.notna() & b.notna() & (a != 0)
    if int(ok.sum()) < REBASIS_MIN_BARS:
        return None
    ratio = (b[ok] / a[ok]).astype(float)
    med = float(ratio.median())
    dev = float((ratio - 1.0).abs().median())
    if dev <= REBASIS_TOL:
        return None
    return {"overlap": int(ok.sum()), "median_ratio": med, "median_abs_dev": dev,
            "tolerance": REBASIS_TOL}


def save_bars(symbol: str, df: pd.DataFrame, allow_rebasis: bool = False) -> int:
    """Merge bars into the store; returns the stored row count.

    Raises `BasisMismatch` when the incoming bars disagree with the stored ones where they overlap
    (AUD-15). Pass `allow_rebasis=True` only when the whole history is being rewritten on one
    basis - i.e. a full re-fetch after a split, where the disagreement is the point.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize(ET)
    df.index = df.index.tz_convert("UTC")
    p = parquet_path(symbol)
    if p.exists():
        old = pd.read_parquet(p)
        if old.index.tz is None:
            old.index = old.index.tz_localize("UTC")
        bad = None if allow_rebasis else basis_mismatch(old, df)
        if bad is not None:
            raise BasisMismatch(
                f"{symbol}: incoming bars disagree with the store on {bad['overlap']} overlapping "
                f"bars (median ratio {bad['median_ratio']:.4g}, median |dev| "
                f"{bad['median_abs_dev']:.4g} > {bad['tolerance']:.4g}). A split rebases the "
                f"whole adjusted history, so merging would leave two price scales in one file. "
                f"Re-fetch the full span and pass allow_rebasis=True, then re-run "
                f"`intraday_data.py --splits`.")
        df = pd.concat([old, df])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    tmp = p.with_suffix(".parquet.tmp")
    df.to_parquet(tmp)
    os.replace(tmp, p)          # atomic: readers never see a half-written file
    return len(df)


def load_universe(symbols=None, start=None, end=None) -> dict[str, pd.DataFrame]:
    out = {}
    for s in (symbols or UNIVERSE):
        df = load_bars(s, start, end)
        if not df.empty:
            out[s] = df
    return out


def sessions(bars: dict[str, pd.DataFrame]) -> list[dt.date]:
    days = set()
    for df in bars.values():
        days.update(d for d in df.index.date)
    return sorted(days)


def log_event(name: str, kind: str, **fields) -> None:
    """Append a JSON line to live/log/<name>-<date>.jsonl."""
    d = LIVE / "log"
    d.mkdir(parents=True, exist_ok=True)
    rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "event": kind, **fields}
    with (d / f"{name}-{dt.date.today():%Y-%m-%d}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def notify(text: str, name: str = "intraday") -> None:
    """Push through OpenClaw's chat channel, and *always* leave a durable record. Never raises.

    P-1: on 2026-09-09 the channel send failed (`TELEGRAM_BOT_TOKEN` missing) and the only trace
    was a `notify_failed` line buried in that session's own log, so a rejected order or a halted
    sleeve would have been invisible to anyone not reading it. Every alert is therefore written to
    `live/log/alerts-<date>.jsonl` first, with `delivered` recording whether the push actually
    left the machine. That file is the alert path the daily review reads; the chat push is a
    convenience on top of it and is allowed to fail.
    """
    delivered, err = False, ""
    alerts = LIVE / "alerts.json"
    try:
        if alerts.exists():
            cfg = json.loads(alerts.read_text(encoding="utf-8"))
            channel, target = cfg.get("channel"), str(cfg.get("target", ""))
            if channel and target:
                node_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "nodejs"
                entry = node_dir / "node_modules" / "openclaw" / "dist" / "index.js"
                cmd = ([str(node_dir / "node.exe"), str(entry)] if entry.exists()
                       else [shutil.which("openclaw") or "openclaw"])
                cmd += ["message", "send", "--channel", channel, "--target", target,
                        "--message", text[:3500]]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
                delivered = res.returncode == 0
                if not delivered:
                    err = (res.stderr or res.stdout)[-300:]
            else:
                err = "alerts.json has no channel/target"
        else:
            err = "no live/alerts.json"
    except Exception as exc:  # noqa: BLE001
        err = str(exc)[:300]
    try:
        log_event("alerts", "alert", source=name, text=text[:3500], delivered=delivered, error=err)
    except Exception:  # noqa: BLE001 - a broken alert path must never stop the trader
        pass
    if not delivered:
        log_event(name, "notify_failed", error=err)
