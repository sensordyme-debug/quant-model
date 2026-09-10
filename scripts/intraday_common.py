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

#: Regular session in ET. Bars are stamped at their START (IBKR convention), so the last
#: regular bar starts at 15:59.
SESSION_OPEN = dt.time(9, 30)
SESSION_CLOSE = dt.time(16, 0)

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


def commission(shares: float, price: float, scale: float = 1.0) -> float:
    """IBKR per-share commission. `scale` is share_scale(): the per-share term is charged on the
    real share count, while the 1% cap is on notional, which splits leave unchanged."""
    c = max(COMMISSION_MIN, abs(shares) / (scale or 1.0) * COMMISSION_PER_SHARE)
    return min(c, 0.01 * abs(shares) * price)


def slippage(shares: float, price: float) -> float:
    return abs(shares) * price * SLIPPAGE_BPS / 1e4


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
    return df


def save_bars(symbol: str, df: pd.DataFrame) -> int:
    """Merge bars into the store; returns the stored row count."""
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
    """Push through OpenClaw's chat channel when live/alerts.json exists. Never raises."""
    alerts = LIVE / "alerts.json"
    if not alerts.exists():
        return
    try:
        cfg = json.loads(alerts.read_text(encoding="utf-8"))
        channel, target = cfg.get("channel"), str(cfg.get("target", ""))
        if not channel or not target:
            return
        node_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "nodejs"
        entry = node_dir / "node_modules" / "openclaw" / "dist" / "index.js"
        cmd = [str(node_dir / "node.exe"), str(entry)] if entry.exists() else [shutil.which("openclaw") or "openclaw"]
        cmd += ["message", "send", "--channel", channel, "--target", target, "--message", text[:3500]]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if res.returncode != 0:
            log_event(name, "notify_failed", error=(res.stderr or res.stdout)[-300:])
    except Exception as exc:  # noqa: BLE001
        log_event(name, "notify_failed", error=str(exc)[:300])
