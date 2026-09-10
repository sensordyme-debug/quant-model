"""Data collection for the quant dashboard: cache, refresher threads, parsers, assemblers.

Everything the dashboard knows comes through this module. Five daemon threads keep an
in-memory `Cache` warm (IB Gateway, live/research files, system/OpenClaw, data stores,
chart quotes); the public assemblers (`status()`, `account()`, ...) only *read* the cache and
never block on IB, a subprocess, the network or a parquet file. Every public function returns
a plain JSON-serializable dict and never raises: an assembly failure comes back as the contract
keys with null/empty values and `error` set.

Write discipline: the process writes exactly one file under live/, `ALLOWED_WRITE`
(live/state/nav_history.jsonl, append only, at most once per 60 s, only from the IB thread after
a fully successful tick). `append_nav()` is the only code path that opens anything for writing.

IB is read-only and single-threaded: the `IB` object is created and used only inside T-IB, in
read-only mode with the dashboard's dedicated client id (81); nothing else ever holds a reference
to it, and it is never retried under another client id.

Secrets: live/secrets.env is never opened here except through `apikeys.keys()`, and only to
compute `{name: bool}` (the values dict is discarded in the same expression) plus a private
tuple of values that `redact()` uses to scrub error strings before they are stored. Those values
are never logged, returned or placed in the cache.

Known limitations (documented, not solved): mock plans are detected by `net_liq == 100000.0`
(the MockAccount constant); executed-vs-dry-run is inferred from a following `order` event; IB
marks are delayed, so IB P&L and the runner's log P&L are two different figures and labelled so;
`ib.fills()` coverage of other client ids is partial; OpenClaw table parsing is best effort;
scheduled-task times are local and converted to UTC; yfinance is the only source for today's
bars; a zombie dashboard process must be killed by hand (it holds clientId 81).
"""
from __future__ import annotations

import ast
import asyncio
import copy
import datetime as dt
import functools
import json
import logging
import math
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections import Counter, OrderedDict
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent            # scripts/dashboard
SCRIPTS = HERE.parent                             # scripts
REPO = SCRIPTS.parent                             # repo root
for _p in (str(SCRIPTS), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ----------------------------------------------------------------------------- repo imports
_IMPORT_ERRORS: dict[str, str] = {}
try:
    from intraday_common import (UNIVERSE, DAILY_SLEEVE_UNIVERSE, ET, load_bars, DATA_DIR, MIN_CHANGE,
                                 PER_SYMBOL_HARD_CAP, GROSS_HARD_CAP, DAILY_LOSS_LIMIT, FLATTEN_MINUTE,
                                 EXIT_MINUTE, SLIPPAGE_BPS)
    UNIVERSE = list(UNIVERSE)
    DAILY_SLEEVE_UNIVERSE = set(DAILY_SLEEVE_UNIVERSE)
except Exception as _e:  # noqa: BLE001 - hard-coded fallback copies so the dashboard still starts
    _IMPORT_ERRORS["intraday_common"] = f"{type(_e).__name__}: {_e}"
    UNIVERSE = ["NVDA", "TSLA", "AAPL", "MSFT", "META", "AMD", "AMZN", "GOOGL", "AVGO", "NFLX",
                "SOXL", "SOXS", "PLTR", "MSTR", "COIN", "SMCI"]
    DAILY_SLEEVE_UNIVERSE = {"SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "TLT", "GLD", "UPRO", "TQQQ", "TMF"}
    ET = ZoneInfo("America/New_York")
    DATA_DIR = Path(os.environ.get("INTRADAY_DATA_DIR", REPO / "data" / "minute"))
    MIN_CHANGE, PER_SYMBOL_HARD_CAP, GROSS_HARD_CAP, DAILY_LOSS_LIMIT = 0.02, 0.20, 1.6, 0.025
    FLATTEN_MINUTE, EXIT_MINUTE, SLIPPAGE_BPS = 368, 372, 1.5
    load_bars = None  # type: ignore[assignment]

try:
    from apikeys import keys as _apikeys
except Exception as _e:  # noqa: BLE001
    _IMPORT_ERRORS["apikeys"] = f"{type(_e).__name__}: {_e}"
    _apikeys = None  # type: ignore[assignment]

try:
    from theta_data import alive as _theta_alive_fn, expirations as _theta_expirations, \
        nearest_expiration as _theta_nearest_expiration, snapshot_quote as _theta_snapshot_quote, BASE as THETA_BASE
except Exception as _e:  # noqa: BLE001
    _IMPORT_ERRORS["theta_data"] = f"{type(_e).__name__}: {_e}"
    _theta_alive_fn = _theta_expirations = _theta_nearest_expiration = _theta_snapshot_quote = None  # type: ignore
    THETA_BASE = "http://127.0.0.1:25503"

# ----------------------------------------------------------------------------- constants
UTC = dt.timezone.utc
LIVE = REPO / "live"
LOG_DIR = LIVE / "log"
STATE_DIR = LIVE / "state"
RESEARCH = REPO / "research"
ALGORITHMS = REPO / "algorithms"
ALLOWED_WRITE = REPO / "live" / "state" / "nav_history.jsonl"
IB_SYMBOL_MAP = {"BRK B": "BRK-B", "BF B": "BF-B"}          # IB symbol -> repo symbol
IB_HOST, IB_PORT, IB_CLIENT_ID = "127.0.0.1", 4002, 81
IB_TAGS = ("NetLiquidation", "TotalCashValue", "BuyingPower", "GrossPositionValue", "AvailableFunds",
           "UnrealizedPnL", "RealizedPnL")
MOCK_NET_LIQ = 100000.0                                      # MockAccount constant (documented limitation)
JOB_IDS = {"research-iterate": "8af1ec1b-6699-44bf-b273-07f3689f198e",
           "research-review": "7ad2fcc4-8ed9-425b-aefd-d1b5f08ad8fd"}
KNOWN_JOBS = ("research-iterate", "research-review", "ops-open", "ops-close")
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
NODE_DIR = LOCALAPPDATA / "Programs" / "nodejs"
NODE_EXE = NODE_DIR / "node.exe"
OPENCLAW_JS = NODE_DIR / "node_modules" / "openclaw" / "dist" / "index.js"
GATEWAY_LOG_DIR = LOCALAPPDATA / "Temp" / "openclaw"
DASH_LOG_DIR = LOCALAPPDATA / "Temp" / "quant-dashboard"
LEAN_ROOT = Path(os.environ.get("LEAN_ROOT") or (REPO.parent / "Lean"))
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
THETA_PLAN = "Options STANDARD, Stock FREE"

SESSION_OPEN_MIN = 9 * 60 + 30
SLEEVE_START_MIN = 9 * 60 + 25
FLATTEN_MIN = SESSION_OPEN_MIN + int(FLATTEN_MINUTE)     # 15:38
EXIT_MIN = SESSION_OPEN_MIN + int(EXIT_MINUTE)           # 15:42
DAILY_WINDOW = (15 * 60 + 44, 15 * 60 + 55)
DAILY_DEADLINE_MIN = 15 * 60 + 47
SESSION_CLOSE_MIN = 16 * 60

PERIODS = {"ib": 15, "files": 5, "system": 60, "data": 60, "quotes": 60}
STALE_S = 180

INTRADAY_ERROR_EVENTS = {"step_error", "decide_error", "feed_error", "disconnected", "order_dead", "loss_limit",
                         "halt", "preflight_failed", "not_started", "stale_book", "ignored_book_file",
                         "flatten_from_account"}
SESSION_END_EVENTS = {"end", "halt", "loss_limit"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
DAILY_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.jsonl$")
INTRADAY_FILE_RE = re.compile(r"^intraday-(\d{4}-\d{2}-\d{2})\.jsonl$")
LEDGER_TS_RE = re.compile(r"^\d{8}T\d{6}Z$")

STAT_KEYS = {"car": "Compounding Annual Return", "sharpe": "Sharpe Ratio", "sortino": "Sortino Ratio",
             "dd": "Drawdown", "psr": "Probabilistic Sharpe Ratio", "orders": "Total Orders",
             "fees": "Total Fees", "net_profit": "Net Profit", "avg_daily_pnl": "Avg Daily PnL",
             "costs_per_day": "Costs Per Day", "trades_per_day": "Trades Per Day", "worst_day": "Worst Day",
             "loss_limit_days": "Loss Limit Days", "sessions": "Sessions"}
STAT_INT_KEYS = {"orders", "sessions", "loss_limit_days"}
SUMMARY_STAT_NAMES = ("Compounding Annual Return", "Sharpe Ratio", "Drawdown", "Total Orders", "Net Profit",
                      "Avg Daily PnL", "Trades Per Day")

# ----------------------------------------------------------------------------- logging
log = logging.getLogger("quant.dashboard.sources")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        d = {"t": dt.datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
             "lvl": record.levelname, "src": record.name, "msg": redact(record.getMessage())}
        if record.exc_info:
            d["exc"] = redact(self.formatException(record.exc_info))[-800:]
        return json.dumps(d)


def _setup_logging() -> None:
    root = logging.getLogger("quant.dashboard")
    if getattr(root, "_quant_dashboard_configured", False):
        return
    root._quant_dashboard_configured = True  # type: ignore[attr-defined]
    root.setLevel(logging.INFO)
    fmt = _JsonFormatter()
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    try:
        DASH_LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(DASH_LOG_DIR / "dashboard.log", maxBytes=5 * 1024 * 1024, backupCount=3,
                                 encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:  # noqa: BLE001 - stderr logging still works
        pass


# ----------------------------------------------------------------------------- secrets / redaction
def _load_secret_values() -> tuple[str, ...]:
    """Values (>= 8 chars) of the known API keys, kept privately for redact() only."""
    vals: set[str] = set()
    try:
        if _apikeys is not None:
            vals = {v for v in _apikeys().values() if isinstance(v, str) and len(v) >= 8}
    except Exception:  # noqa: BLE001
        vals = set()
    return tuple(sorted(vals, key=len, reverse=True))


_SECRET_VALUES = _load_secret_values()


def redact(s) -> str:
    """Replace every known key value (length >= 8) with *** in any string stored or served."""
    s = "" if s is None else str(s)
    for v in _SECRET_VALUES:
        if v and v in s:
            s = s.replace(v, "***")
    return s


def keys_present() -> dict[str, bool]:
    """Which API keys exist, as booleans only. The values dict is discarded in the same expression."""
    names: set[str] = set()
    try:
        if _apikeys is not None:
            names = set(_apikeys().keys())
    except Exception:  # noqa: BLE001
        names = set()
    return {"ALPACA": {"ALPACA_API_KEY", "ALPACA_SECRET_KEY"} <= names,
            "THETADATA": "THETADATA_API_KEY" in names,
            "FMP": "FMP_API_KEY" in names,
            "POLYGON": "POLYGON_API_KEY" in names,
            "FINNHUB": "FINNHUB_API_KEY" in names,
            "NASDAQ": "NASDAQ_DATA_LINK_API_KEY" in names,
            "TELEGRAM": "TELEGRAM_BOT_TOKEN" in names}


_setup_logging()

# ----------------------------------------------------------------------------- time helpers
def utcnow() -> dt.datetime:
    return dt.datetime.now(UTC)


def iso_utc(t: dt.datetime | None = None) -> str:
    return (t or utcnow()).astimezone(UTC).isoformat(timespec="seconds")


def et_now() -> dt.datetime:
    return dt.datetime.now(ET)


def today_et() -> str:
    return et_now().date().isoformat()


def parse_ts(s):
    """ISO / '20260910T160700Z' / epoch(ms) -> aware datetime, or None."""
    if s is None or s == "":
        return None
    if isinstance(s, dt.datetime):
        return s if s.tzinfo else s.replace(tzinfo=UTC)
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        try:
            v = float(s)
            if not math.isfinite(v):
                return None
            return dt.datetime.fromtimestamp(v / 1000.0 if v > 1e11 else v, UTC)
        except Exception:  # noqa: BLE001
            return None
    t = str(s).strip()
    try:
        if LEDGER_TS_RE.match(t):
            return dt.datetime.strptime(t, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        t = re.sub(r"(\.\d{6})\d+", r"\1", t)          # more than 6 fractional digits (PowerShell 'o')
        d = dt.datetime.fromisoformat(t)
        if d.tzinfo is None:
            d = d.replace(tzinfo=UTC)
        return d
    except Exception:  # noqa: BLE001
        return None


def iso_off(d: dt.datetime | None) -> str | None:
    return d.isoformat(timespec="seconds") if d else None


def to_et(d: dt.datetime | None) -> dt.datetime | None:
    return d.astimezone(ET) if d else None


def et_minute_iso(d: dt.datetime | None) -> str | None:
    """ET timestamp floored to the minute, ISO with offset (chart marker time)."""
    if not d:
        return None
    e = d.astimezone(ET).replace(second=0, microsecond=0)
    return e.isoformat(timespec="seconds")


def et_date_of(d: dt.datetime | None) -> str | None:
    return d.astimezone(ET).date().isoformat() if d else None


def age_seconds(ts, now: dt.datetime | None = None):
    d = parse_ts(ts)
    if d is None:
        return None
    return ((now or utcnow()) - d).total_seconds()


def _local_iso_to_utc(s) -> str | None:
    """PowerShell round-trip ('o') local time -> UTC ISO."""
    if not s:
        return None
    t = re.sub(r"(\.\d{6})\d+", r"\1", str(s).strip())
    try:
        d = dt.datetime.fromisoformat(t)
    except Exception:  # noqa: BLE001
        return None
    if d.tzinfo is None:
        d = d.astimezone()      # naive -> local zone
    return iso_utc(d)


# ----------------------------------------------------------------------------- number / json helpers
def to_num(s):
    """'24.404%' / '$45695.46' / '4,735' -> float (percent units kept), None on failure."""
    if s is None or isinstance(s, bool):
        return None
    if isinstance(s, (int, float)):
        return float(s) if math.isfinite(float(s)) else None
    t = str(s).strip().replace("$", "").replace(",", "").replace("%", "").strip()
    if not t:
        return None
    try:
        v = float(t)
        return v if math.isfinite(v) else None
    except Exception:  # noqa: BLE001
        return None


def _f(x):
    """float or None (never 0 for unknown; nan/inf -> None)."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except Exception:  # noqa: BLE001
        return None
    return v if math.isfinite(v) else None


def _i(x):
    v = _f(x)
    if v is None:
        return None
    return int(round(v)) if abs(v - round(v)) < 1e-9 else v


def sanitize(o):
    """NaN/inf/numpy/Timestamp/Path -> JSON-safe values, recursively."""
    if o is None or isinstance(o, (bool, str, int)):
        return o
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {str(k): sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set, frozenset)):
        return [sanitize(v) for v in o]
    if isinstance(o, (dt.datetime, dt.date, dt.time)):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, bytes):
        return o.decode("utf-8", "replace")
    if str(o) in ("NaT", "nan", "NaN"):
        return None
    item = getattr(o, "item", None)
    if callable(item):
        try:
            v = item()
            if v is not o:
                return sanitize(v)
        except Exception:  # noqa: BLE001
            pass
    isof = getattr(o, "isoformat", None)
    if callable(isof):
        try:
            return isof()
        except Exception:  # noqa: BLE001
            pass
    return str(o)


def _min_iso(*vals):
    xs = [v for v in vals if v]
    return min(xs) if xs else None


def _max_iso(*vals):
    xs = [v for v in vals if v]
    return max(xs) if xs else None


def _norm_json(x) -> str:
    return json.dumps(x, sort_keys=True, default=str)


# ----------------------------------------------------------------------------- cache
class Entry:
    __slots__ = ("data", "as_of", "ok", "error", "error_since", "last_good", "last_good_at", "heartbeat", "period_s")

    def __init__(self, data=None, as_of=None, ok=False, error=None, error_since=None, last_good=None,
                 last_good_at=None, heartbeat=None, period_s=None):
        self.data, self.as_of, self.ok, self.error, self.error_since = data, as_of, ok, error, error_since
        self.last_good, self.last_good_at, self.heartbeat, self.period_s = last_good, last_good_at, heartbeat, period_s


class Cache:
    """name -> immutable Entry snapshots. Writers replace whole entries; readers take the reference."""

    def __init__(self):
        self._lock = threading.Lock()
        self._e: dict[str, Entry] = {}

    def set_ok(self, name: str, data, as_of: str | None = None, period_s: float | None = None) -> None:
        now = iso_utc()
        with self._lock:
            old = self._e.get(name)
            self._e[name] = Entry(data=data, as_of=as_of or now, ok=True, error=None, error_since=None,
                                  last_good=data, last_good_at=as_of or now,
                                  heartbeat=old.heartbeat if old else now,
                                  period_s=period_s or (old.period_s if old else None))

    def set_error(self, name: str, err: str, period_s: float | None = None) -> None:
        now = iso_utc()
        err = redact(err)[:300]
        with self._lock:
            old = self._e.get(name)
            since = old.error_since if (old and not old.ok and old.error_since) else now
            self._e[name] = Entry(data=old.data if old else None, as_of=old.as_of if old else None, ok=False,
                                  error=err, error_since=since, last_good=old.last_good if old else None,
                                  last_good_at=old.last_good_at if old else None, heartbeat=now,
                                  period_s=period_s or (old.period_s if old else None))

    def heartbeat(self, name: str) -> None:
        now = iso_utc()
        with self._lock:
            old = self._e.get(name)
            if old is None:
                self._e[name] = Entry(heartbeat=now)
            else:
                self._e[name] = Entry(data=old.data, as_of=old.as_of, ok=old.ok, error=old.error,
                                      error_since=old.error_since, last_good=old.last_good,
                                      last_good_at=old.last_good_at, heartbeat=now, period_s=old.period_s)

    def get(self, name: str) -> Entry | None:
        with self._lock:
            return self._e.get(name)

    def data(self, name: str, default=None):
        e = self.get(name)
        if e is None or e.last_good is None:
            return default
        return e.last_good

    def meta(self, name: str) -> dict:
        e = self.get(name)
        if e is None:
            return {"as_of": None, "error": None, "ok": None, "heartbeat": None, "last_good_at": None,
                    "error_since": None}
        return {"as_of": e.last_good_at or e.as_of, "error": e.error, "ok": e.ok, "heartbeat": e.heartbeat,
                "last_good_at": e.last_good_at, "error_since": e.error_since}

    def section(self, name: str) -> dict:
        m = self.meta(name)
        return {"as_of": m["as_of"], "error": m["error"]}

    def heartbeat_of(self, name: str):
        e = self.get(name)
        return e.heartbeat if e else None


CACHE = Cache()
STOP = threading.Event()
_THREADS: dict[str, threading.Thread] = {}
_START_LOCK = threading.Lock()
_STARTED = False
_STATE_LOG: dict[str, str | None] = {}


def _log_state(name: str, err: str | None) -> None:
    """Log a failure or recovery once per state change, not per tick."""
    if _STATE_LOG.get(name) == err:
        return
    _STATE_LOG[name] = err
    if err:
        log.warning("%s: %s", name, err)
    else:
        log.info("%s: ok", name)


# ----------------------------------------------------------------------------- the single writer
def append_nav(rec: dict, path: Path = ALLOWED_WRITE) -> None:
    """The only write this process performs: one JSON line appended to live/state/nav_history.jsonl."""
    assert Path(path) == ALLOWED_WRITE, "append_nav may only write ALLOWED_WRITE"
    ALLOWED_WRITE.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ts": rec["ts"], "nav": rec["nav"], "cash": rec.get("cash"), "gross": rec.get("gross")})
    with open(ALLOWED_WRITE, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()


# ----------------------------------------------------------------------------- file readers
class JsonlFile:
    """Incremental JSONL reader: parses appended bytes only; reparses from 0 when the file shrinks
    or its mtime changes at equal size; drops a trailing fragment without a newline; counts bad
    lines instead of raising. `lines` is replaced (never mutated in place) so readers holding the
    previous list are safe."""

    def __init__(self, path: Path, require_key: str | None = "event"):
        self.path = Path(path)
        self.require_key = require_key
        self._lock = threading.Lock()
        self.lines: list[dict] = []
        self.bad = 0
        self.offset = 0
        self.size = 0
        self.mtime_ns = 0
        self.mtime: str | None = None
        self.exists = False
        self.last_check = 0.0

    def refresh(self) -> bool:
        with self._lock:
            self.last_check = time.monotonic()
            try:
                st = self.path.stat()
            except FileNotFoundError:
                changed = self.exists or bool(self.lines)
                self.lines, self.bad, self.offset, self.size, self.mtime_ns, self.mtime, self.exists = [], 0, 0, 0, 0, None, False
                return changed
            self.exists = True
            size, mt = st.st_size, st.st_mtime_ns
            if size == self.size and mt == self.mtime_ns:
                return False
            if size < self.size or (mt != self.mtime_ns and size == self.size):
                self.lines, self.bad, self.offset = [], 0, 0
            with open(self.path, "rb") as fh:
                fh.seek(self.offset)
                chunk = fh.read()
            self.size, self.mtime_ns = size, mt
            self.mtime = iso_utc(dt.datetime.fromtimestamp(st.st_mtime, UTC))
            if not chunk:
                return True
            parts = chunk.split(b"\n")
            tail = parts.pop()                       # b"" when the file ends with a newline
            consumed = len(chunk) - len(tail)
            new: list[dict] = []
            for raw in parts:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    d = json.loads(raw.decode("utf-8", "replace"))
                except Exception:  # noqa: BLE001
                    self.bad += 1
                    continue
                if isinstance(d, dict) and (self.require_key is None or self.require_key in d):
                    new.append(d)
                else:
                    self.bad += 1
            self.offset += consumed
            if new:
                self.lines = self.lines + new
            return True


_JSONL: dict[Path, JsonlFile] = {}
_JSONL_LOCK = threading.Lock()


def _jsonl(path: Path, require_key: str | None = "event") -> JsonlFile:
    path = Path(path)
    with _JSONL_LOCK:
        jf = _JSONL.get(path)
        if jf is None:
            jf = JsonlFile(path, require_key)
            _JSONL[path] = jf
        return jf


def _drop_jsonl(path: Path) -> None:
    with _JSONL_LOCK:
        _JSONL.pop(Path(path), None)


_TEXT_CACHE: dict[Path, tuple[tuple[int, int], str | None, str | None]] = {}
_TEXT_LOCK = threading.Lock()


def _read_text_cached(path: Path) -> tuple[str | None, str | None, bool]:
    """(text, mtime_iso, changed) with parsing gated on (mtime_ns, size). Missing -> (None, None, changed)."""
    path = Path(path)
    try:
        st = path.stat()
        sig = (st.st_mtime_ns, st.st_size)
        mtime = iso_utc(dt.datetime.fromtimestamp(st.st_mtime, UTC))
    except FileNotFoundError:
        with _TEXT_LOCK:
            old = _TEXT_CACHE.pop(path, None)
        return None, None, old is not None
    with _TEXT_LOCK:
        old = _TEXT_CACHE.get(path)
        if old and old[0] == sig:
            return old[1], old[2], False
    text = path.read_text(encoding="utf-8", errors="replace")
    with _TEXT_LOCK:
        _TEXT_CACHE[path] = (sig, text, mtime)
    return text, mtime, True


_JSON_CACHE: dict[Path, tuple[tuple[int, int], object, str | None]] = {}


def _read_json_cached(path: Path, retry: bool = False):
    """Parsed JSON file -> (data, exists, mtime_iso, changed). Raises json.JSONDecodeError after
    the optional 50 ms retry (the intraday trader writes its book non-atomically)."""
    path = Path(path)
    try:
        st = path.stat()
    except FileNotFoundError:
        with _TEXT_LOCK:
            old = _JSON_CACHE.pop(path, None)
        return None, False, None, old is not None
    sig = (st.st_mtime_ns, st.st_size)
    mtime = iso_utc(dt.datetime.fromtimestamp(st.st_mtime, UTC))
    with _TEXT_LOCK:
        old = _JSON_CACHE.get(path)
        if old and old[0] == sig:
            return old[1], True, old[2], False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        if not retry:
            raise
        time.sleep(0.05)
        data = json.loads(path.read_text(encoding="utf-8"))
    with _TEXT_LOCK:
        _JSON_CACHE[path] = (sig, data, mtime)
    return data, True, mtime, True


# ----------------------------------------------------------------------------- sleeve attribution
def norm_symbol(sym) -> str:
    s = (sym or "").strip()
    return IB_SYMBOL_MAP.get(s, s)


def sleeve_of(symbol: str, order_ref: str | None = None) -> str:
    if order_ref == "INTRADAY":
        return "intraday"
    if symbol in UNIVERSE:
        return "intraday"
    if symbol in DAILY_SLEEVE_UNIVERSE:
        return "daily"
    return "other"


# ----------------------------------------------------------------------------- intraday log parser (5.8)
def _launch_params(launch: dict | None) -> dict | None:
    if not launch:
        return None
    cmd = launch.get("cmd") or []
    out = {"strategy": None, "equity_frac": None, "params": None, "dry_run": False, "argv": [str(c) for c in cmd[2:]]}
    i = 0
    while i < len(cmd):
        a = str(cmd[i])
        nxt = str(cmd[i + 1]) if i + 1 < len(cmd) else None
        if a == "--strategy" and nxt is not None:
            out["strategy"] = nxt
            i += 2
        elif a == "--equity-frac" and nxt is not None:
            out["equity_frac"] = _f(nxt)
            i += 2
        elif a == "--params" and nxt is not None:
            try:
                out["params"] = json.loads(nxt)
            except Exception:  # noqa: BLE001
                out["params"] = {"_unparsed": nxt[:200]}
            i += 2
        elif a.startswith("--params="):
            try:
                out["params"] = json.loads(a.split("=", 1)[1])
            except Exception:  # noqa: BLE001
                out["params"] = {"_unparsed": a[:200]}
            i += 1
        elif a == "--dry-run":
            out["dry_run"] = True
            i += 1
        else:
            i += 1
    return out


def _config_drift(launch_params: dict | None, deployed: dict | None) -> bool:
    if not launch_params or not isinstance(deployed, dict):
        return False
    if launch_params.get("strategy") is not None and launch_params["strategy"] != deployed.get("strategy"):
        return True
    lf, df_ = launch_params.get("equity_frac"), _f(deployed.get("equity_frac"))
    if lf is not None and df_ is not None and abs(lf - df_) > 1e-9:
        return True
    if lf is not None and df_ is None:
        return True
    if _norm_json(launch_params.get("params")) != _norm_json(deployed.get("params")):
        return True
    return False


def _event_detail(d: dict, limit: int = 200) -> str:
    parts = []
    for k in ("error", "reason", "symbol", "status", "feed", "files", "positions", "output", "mode", "date"):
        if k in d and d[k] not in (None, ""):
            v = d[k]
            parts.append(f"{k}={v}" if k not in ("error", "reason") else str(v))
    return redact("; ".join(parts))[:limit]


def parse_intraday(lines: list[dict], date: str, book: dict | None = None, deployed: dict | None = None,
                   gates: dict | None = None, bad_lines: int = 0, available_dates: list[str] | None = None,
                   now: dt.datetime | None = None) -> dict:
    """Session view of one intraday log (everything after the last `start`). Never raises on content."""
    now = now or utcnow()
    gates = gates or {}
    today = today_et()
    etn = now.astimezone(ET)
    mins = etn.hour * 60 + etn.minute
    weekday = etn.weekday() < 5
    exists = bool(lines)

    excluded = {"replay_decisions": 0, "foreign_date_snapshots": 0}
    clean: list[dict] = []
    for d in lines:
        ev = d.get("event")
        if ev == "decision" and d.get("mode") == "replay":
            excluded["replay_decisions"] += 1
            continue
        if ev == "snapshot":
            t = parse_ts(d.get("t"))
            if t is None or et_date_of(t) != date:
                excluded["foreign_date_snapshots"] += 1
                continue
        clean.append(d)

    start_idx = None
    for k in range(len(clean) - 1, -1, -1):
        if clean[k].get("event") == "start":
            start_idx = k
            break
    launch = None
    if start_idx is None:
        session = clean
        start = None
        for d in reversed(clean):
            if d.get("event") == "launch":
                launch = d
                break
    else:
        start = clean[start_idx]
        session = clean[start_idx:]
        for d in reversed(clean[:start_idx]):
            ev = d.get("event")
            if ev == "launch":
                launch = d
                break
            if ev == "start":
                break

    counts = Counter(str(d.get("event")) for d in session)
    if launch is not None:
        counts["launch"] += 1
    ts_all = [parse_ts(d.get("ts")) for d in session]
    ts_all = [t for t in ts_all if t]
    first_ts = min(ts_all) if ts_all else None
    last_ts = max(ts_all) if ts_all else None

    decisions = [d for d in session if d.get("event") == "decision"]
    snapshots = [d for d in session if d.get("event") == "snapshot"]
    fills = [d for d in session if d.get("event") == "fill"]
    orders = [d for d in session if d.get("event") == "order"]
    dead = [d for d in session if d.get("event") == "order_dead"]
    end_ev = next((d for d in reversed(session) if d.get("event") == "end"), None)
    halt_ev = next((d for d in reversed(session) if d.get("event") == "halt"), None)
    loss_ev = next((d for d in reversed(session) if d.get("event") == "loss_limit"), None)
    probe = next((d for d in reversed(session) if d.get("event") == "feed_probe"), None)

    # ---- state
    age = (now - last_ts).total_seconds() if last_ts else None
    detail = None
    if not exists:
        state = "off"
        detail = f"no log file for {date}"
    elif start is None:
        state = "off"
        last = session[-1] if session else None
        detail = f"no start event; last event {last.get('event')} {_event_detail(last, 120)}".strip() if last else "no start event"
    elif end_ev is not None:
        state = "ended"
    elif loss_ev is not None:
        state = "ended"
        detail = "loss_limit"
    elif halt_ev is not None:
        state = "ended"
        detail = "halt"
    elif date != today:
        state = "ended"
        detail = "no end event"
    elif age is not None and age < STALE_S:
        state = "running"
    elif mins > EXIT_MIN:
        state = "ended"
        detail = "no end event"
    else:
        state = "stalled"
        silent = to_et(last_ts)
        detail = f"silent since {silent:%H:%M}" if silent else "silent"
        if not (weekday and SLEEVE_START_MIN <= mins <= EXIT_MIN):
            detail += " (outside 09:25-15:42 ET)"

    # ---- mode / config
    mode = None
    if decisions and decisions[-1].get("mode"):
        mode = str(decisions[-1]["mode"])
    elif start is not None:
        mode = "dry_run" if start.get("dry_run") else "live"
    elif exists:
        mode = "live"
    launch_params = _launch_params(launch)
    drift = _config_drift(launch_params, deployed)
    start_cfg = None
    sleeve_equity = None
    if start is not None:
        start_cfg = {"account": start.get("account"), "nav": _f(start.get("nav")), "equity_frac": _f(start.get("equity_frac")),
                     "strategy": start.get("strategy"), "dry_run": bool(start.get("dry_run")), "ts": start.get("ts")}
        if start_cfg["nav"] is not None and start_cfg["equity_frac"] is not None:
            sleeve_equity = start_cfg["nav"] * start_cfg["equity_frac"]

    # ---- P&L / trades / positions
    latest = None
    for d in decisions + snapshots:
        t = parse_ts(d.get("ts"))
        if t and (latest is None or t >= latest[0]):
            latest = (t, d)
    pnl_today = _f(latest[1].get("pnl")) if latest else None
    if end_ev is not None and not end_ev.get("positions"):
        pnl_today = _f(end_ev.get("pnl")) if _f(end_ev.get("pnl")) is not None else pnl_today
    book_ok = isinstance(book, dict) and book.get("date") == date and book.get("mode") == "live"
    if snapshots:
        trades_today = _i(snapshots[-1].get("trades"))
    elif book_ok and book.get("trades") is not None:
        trades_today = _i(book.get("trades"))
    elif exists:
        trades_today = len(fills)
    else:
        trades_today = None
    if book_ok and isinstance(book.get("pos"), dict):
        positions_now = {str(k): _i(v) for k, v in book["pos"].items() if _i(v)}
        positions_source = "book"
    elif snapshots and isinstance(snapshots[-1].get("positions"), dict):
        positions_now = {str(k): _i(v) for k, v in snapshots[-1]["positions"].items() if _i(v)}
        positions_source = "snapshot"
    else:
        positions_now, positions_source = {}, "none"

    # ---- curve
    curve = []
    for d in decisions:
        t = parse_ts(d.get("t"))
        if t:
            curve.append({"t": t, "pnl": _f(d.get("pnl")), "equity": _f(d.get("equity")), "gross": None, "trades": None})
    for s in snapshots:
        t = parse_ts(s.get("t"))
        if t:
            curve.append({"t": t, "pnl": _f(s.get("pnl")), "equity": None, "gross": _f(s.get("gross")), "trades": _i(s.get("trades"))})
    curve.sort(key=lambda r: r["t"])
    g, tr = None, None
    pnl_curve = []
    for r in curve:
        if r["gross"] is not None:
            g = r["gross"]
        if r["trades"] is not None:
            tr = r["trades"]
        pnl_curve.append({"t": iso_off(r["t"]), "pnl": r["pnl"], "gross": g, "trades": tr, "equity": r["equity"]})

    # ---- fills / orders
    order_by_id = {o.get("id"): o for o in orders if o.get("id") is not None}
    filled_ids = set()
    trades = []
    for f in fills:
        fa = parse_ts(f.get("filled_at")) or parse_ts(f.get("ts"))
        o = order_by_id.get(f.get("id"))
        lat = None
        if o is not None and parse_ts(f.get("filled_at")) and parse_ts(o.get("ts")):
            lat = round((parse_ts(f["filled_at"]) - parse_ts(o["ts"])).total_seconds(), 1)
        filled_ids.add(f.get("id"))
        trades.append({"ts": iso_off(fa), "symbol": f.get("symbol"), "qty": _i(f.get("qty")), "avg_price": _f(f.get("avg_price")),
                       "commission": _f(f.get("commission")), "status": f.get("status"), "id": f.get("id"),
                       "latency_s": lat, "partial": f.get("status") != "Filled"})
    dead_ids = {d.get("id") for d in dead}
    pending_orders = [{"ts": o.get("ts"), "symbol": o.get("symbol"), "qty": _i(o.get("qty")), "id": o.get("id"), "t": o.get("t")}
                      for o in orders if o.get("id") not in filled_ids and o.get("id") not in dead_ids]
    dead_orders = [{"ts": d.get("ts"), "symbol": d.get("symbol"), "status": d.get("status"), "filled": _f(d.get("filled")), "id": d.get("id")}
                   for d in dead]

    # ---- errors
    errors = []
    nf = [d for d in session if d.get("event") == "notify_failed"]
    for d in session:
        ev = d.get("event")
        if ev in INTRADAY_ERROR_EVENTS:
            errors.append({"ts": d.get("ts"), "event": ev, "detail": _event_detail(d), "count": 1})
    if nf:
        errors.append({"ts": nf[-1].get("ts"), "event": "notify_failed", "detail": redact(str(nf[-1].get("error", "")))[:200], "count": len(nf)})
    errors.sort(key=lambda e: e.get("ts") or "")
    errors = errors[-50:]

    last_decision = None
    if decisions:
        d = decisions[-1]
        last_decision = {"t": iso_off(parse_ts(d.get("t"))) or d.get("t"), "targets": d.get("targets") or {}, "orders": d.get("orders") or {},
                         "pnl": _f(d.get("pnl")), "minute": d.get("minute")}

    delay = _f(probe.get("ib_delay_minutes")) if probe else None
    if delay is None:
        feed = "unknown"
    elif delay <= 5:
        feed = "ibkr"
    else:
        feed = f"yahoo 1m (IB delayed {delay:.0f}m)"

    halted = halt_ev is not None or bool(gates.get("halt")) or bool(gates.get("halt_intraday"))
    return {
        "date": date,
        "config": {"start": start_cfg, "launch_params": launch_params, "deployed": deployed, "drift": bool(drift), "sleeve_equity": sleeve_equity},
        "events_summary": {"counts": dict(counts), "first_ts": iso_off(first_ts), "last_ts": iso_off(last_ts),
                           "feed_delay_minutes": delay, "feed_delayed_n": int(counts.get("feed_delayed", 0)),
                           "excluded": excluded, "available_dates": list(available_dates or []), "bad_lines": int(bad_lines)},
        "pnl_curve": pnl_curve, "trades": trades, "decisions_n": len(decisions), "positions_now": positions_now,
        "errors": errors, "state": state, "state_detail": detail, "mode": mode, "pnl_today": pnl_today,
        "trades_today": trades_today, "positions_source": positions_source, "last_decision": last_decision,
        "dead_orders": dead_orders, "pending_orders": pending_orders, "loss_limit_hit": loss_ev is not None,
        "halted": halted, "feed": feed, "last_event_ts": iso_off(last_ts), "session_start_ts": start.get("ts") if start else None,
        "exists": exists, "has_end": end_ev is not None, "feed_error_n": int(counts.get("feed_error", 0)),
        "closed_positions_at_end": (end_ev.get("positions") if end_ev else None),
    }


# ----------------------------------------------------------------------------- daily log parser (5.7)
def _plan_public(p: dict | None) -> dict | None:
    if not p:
        return None
    return {"ts": p.get("ts"), "signal": p.get("signal"), "as_of": p.get("as_of"), "kind": p.get("kind"),
            "targets": p.get("targets") or {}, "orders": p.get("orders") or [], "net_liq": p.get("net_liq"),
            "diagnostics": p.get("diagnostics") or {}}


def parse_daily(lines: list[dict], date: str, bad_lines: int = 0) -> dict:
    plans: list[dict] = []
    cur: dict | None = None
    fills_all: list[dict] = []
    last_order: dict[str, dict] = {}
    counts = Counter(str(d.get("event")) for d in lines)
    warn_acc: dict[tuple, dict] = {}

    def warn(ev, detail, ts):
        # connect_failed / notify_failed aggregate per event (detail = last error text);
        # refused / flatten / foreign_positions_ignored aggregate per reason.
        key = (ev, None) if ev in ("connect_failed", "notify_failed") else (ev, detail)
        w = warn_acc.get(key)
        if w is None:
            warn_acc[key] = {"event": ev, "count": 1, "last_ts": ts, "detail": detail}
        else:
            w["count"] += 1
            if ts and (w["last_ts"] is None or ts > w["last_ts"]):
                w["last_ts"] = ts
                if detail:
                    w["detail"] = detail

    for d in lines:
        ev = d.get("event")
        if ev == "plan":
            cur = {"ts": d.get("ts"), "signal": d.get("signal"), "as_of": d.get("as_of"), "targets": d.get("targets") or {},
                   "net_liq": _f(d.get("net_liq")), "diagnostics": d.get("diagnostics") or {}, "orders": d.get("orders") or [],
                   "kind": None, "fills": [], "order_n": 0}
            plans.append(cur)
        elif ev == "order":
            sym = d.get("symbol")
            if sym:
                last_order[sym] = d
            if cur is not None:
                cur["order_n"] += 1
        elif ev == "fill":
            sym = d.get("symbol")
            o = last_order.get(sym)
            filled = _f(d.get("filled"))
            sign = None
            if o is not None:
                sign = 1 if str(o.get("action", "")).upper() == "BUY" else -1
            qty = sign * filled if (sign is not None and filled is not None) else None
            f = {"ts": d.get("ts"), "symbol": sym, "qty": _i(qty) if qty is not None else None, "filled": filled,
                 "remaining": _f(d.get("remaining")), "avg_price": _f(d.get("avg_price")), "status": d.get("status"),
                 "ref_price": _f(o.get("ref_price")) if o else None}
            fills_all.append(f)
            if cur is not None:
                cur["fills"].append(f)
        elif ev == "connect_failed":
            warn("connect_failed", redact(str(d.get("error") or ""))[:160], d.get("ts"))
        elif ev == "notify_failed":
            warn("notify_failed", redact(str(d.get("error") or ""))[:160], d.get("ts"))
        elif ev in ("refused", "flatten"):
            warn(ev, str(d.get("reason") or "")[:160], d.get("ts"))
        elif ev == "foreign_positions_ignored":
            warn(ev, json.dumps(d.get("positions"), default=str)[:160], d.get("ts"))

    for p in plans:
        if p["order_n"] > 0:
            p["kind"] = "executed"
        elif p["net_liq"] is not None and p["net_liq"] == MOCK_NET_LIQ:
            p["kind"] = "mock"           # documented limitation: MockAccount constant
        else:
            p["kind"] = "dry_run"
    last_plan = plans[-1] if plans else None
    last_exec = next((p for p in reversed(plans) if p["kind"] == "executed"), None)
    ref = last_exec or last_plan
    return {
        "date": date,
        "plans": [{"ts": p["ts"], "net_liq": p["net_liq"], "kind": p["kind"]} for p in plans],
        "last_plan": _plan_public(last_plan),
        "last_executed_plan": _plan_public(last_exec),
        "fills": fills_all,
        "last_fills_n": sum(1 for f in fills_all if f.get("status") == "Filled"),
        "warnings": sorted(warn_acc.values(), key=lambda w: w.get("last_ts") or ""),
        "mock_n": sum(1 for p in plans if p["kind"] == "mock"),
        "counts": dict(counts),
        "bad_lines": int(bad_lines),
        "history_row": {"date": date, "kind": ref["kind"] if ref else None, "targets": (ref["targets"] if ref else {}),
                        "fills_n": len(fills_all), "net_liq": ref["net_liq"] if ref else None,
                        "connect_failed_n": int(counts.get("connect_failed", 0)), "refused_n": int(counts.get("refused", 0)),
                        "flatten_n": int(counts.get("flatten", 0))},
        "exists": bool(lines),
    }


# ----------------------------------------------------------------------------- research parsers (5.10)
def _parse_stats(stats: dict) -> dict:
    out = {}
    for k, name in STAT_KEYS.items():
        v = to_num(stats.get(name)) if isinstance(stats, dict) else None
        if v is not None and k in STAT_INT_KEYS:
            v = int(round(v))
        out[k] = v
    return out


def _augment_row(row: dict) -> dict:
    algo = str(row.get("algorithm") or "")
    track = row.get("track") or ("intraday" if algo.startswith("intraday/") else "daily")
    parsed = _parse_stats(row.get("stats") or {})
    t = parse_ts(row.get("ts"))
    parsed["ts"] = iso_utc(t) if t else row.get("ts")
    new = dict(row)
    new["parsed"] = parsed
    new["track"] = track
    return new


def _by_algorithm(rows: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for r in rows:
        a = str(r.get("algorithm") or "")
        g = groups.get(a)
        if g is None:
            g = groups[a] = {"algorithm": a, "runs": 0, "best_sharpe": None, "best_car": None, "last_ts": None, "track": r.get("track")}
        g["runs"] += 1
        p = r.get("parsed") or {}
        if p.get("sharpe") is not None and (g["best_sharpe"] is None or p["sharpe"] > g["best_sharpe"]):
            g["best_sharpe"] = p["sharpe"]
        if p.get("car") is not None and (g["best_car"] is None or p["car"] > g["best_car"]):
            g["best_car"] = p["car"]
        ts = p.get("ts") or r.get("ts")
        if ts and (g["last_ts"] is None or str(ts) > str(g["last_ts"])):
            g["last_ts"] = ts
    return sorted(groups.values(), key=lambda g: str(g["last_ts"] or ""), reverse=True)


_BACKLOG_ID_RE = re.compile(r"^([A-Z]{1,3}-\d+[A-Za-z]?(?:\s+part\s+\d+)?)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _md_section(lines: list[str], prefix: str) -> list[str]:
    start = next((i for i, l in enumerate(lines) if l.startswith(prefix)), None)
    if start is None:
        return []
    end = next((j for j in range(start + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
    return lines[start + 1:end]


def _md_bullets(section: list[str]) -> tuple[list[list[str]], list[str]]:
    blocks: list[list[str]] = []
    preamble: list[str] = []
    cur: list[str] | None = None
    i = 0
    while i < len(section):
        ln = section[i]
        if ln.startswith("- "):
            cur = [ln[2:]]
            blocks.append(cur)
        elif cur is not None:
            if ln.strip() == "":
                j = i + 1
                while j < len(section) and section[j].strip() == "":
                    j += 1
                if j < len(section) and not section[j].startswith("- ") and not section[j].startswith((" ", "\t")):
                    cur = None
            else:
                cur.append(ln)
        elif not blocks:
            preamble.append(ln)
        i += 1
    return blocks, preamble


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def parse_backlog(text: str) -> dict:
    lines = text.splitlines()
    open_sec = _md_section(lines, "## Open")
    blocks, preamble = _md_bullets(open_sec)
    items = []
    for b in blocks:
        joined = " ".join(l.strip() for l in b)
        m = _BOLD_RE.search(joined)
        if m:
            bold = m.group(1).strip()
            rest = joined[m.end():]
        else:
            bold = joined[:120]
            rest = joined[120:]
        im = _BACKLOG_ID_RE.match(bold)
        if im:
            bid = im.group(1)
            title = bold[im.end():].strip()
        else:
            parts = bold.split(None, 1)
            bid = parts[0] if parts else ""
            title = parts[1] if len(parts) > 1 else ""
        title = title.rstrip(".").strip()
        items.append({"id": bid, "title": title, "text": _collapse(rest)[:600], "done": "DONE" in bold})
    obj = _md_section(lines, "## Current objective")
    paras: list[str] = []
    curp: list[str] = []
    for ln in obj:
        if ln.strip():
            curp.append(ln.strip())
        elif curp:
            paras.append(" ".join(curp))
            curp = []
    if curp:
        paras.append(" ".join(curp))
    done_sec = _md_section(lines, "## Done")
    done_blocks, _ = _md_bullets(done_sec)
    return {"open": items, "meta": {"open_n": sum(1 for it in items if not it["done"]),
                                    "done_n": len(done_blocks) + sum(1 for it in items if it["done"]),
                                    "objective_excerpt": (paras[0] if paras else "")[:600],
                                    "preamble": _collapse("\n".join(preamble))[:800]}}


def parse_journal(text: str) -> list[dict]:
    entries = []
    title, body = None, []
    for ln in text.splitlines():
        if ln.startswith("## "):
            if title is not None:
                entries.append((title, body))
            title, body = ln[3:].strip(), []
        elif title is not None:
            body.append(ln)
    if title is not None:
        entries.append((title, body))
    out = []
    for t, b in entries:
        raw = _collapse(" ".join(b)).replace("**", "").replace("`", "")
        out.append({"title": t, "text_excerpt": raw[:300]})
    return out


def parse_blockers(text: str) -> tuple[str, list[str]]:
    cut = text[:1200]
    if len(text) > 1200 and "\n" in cut:
        cut = cut[:cut.rfind("\n")]
    heads = [ln[3:].strip() for ln in text.splitlines() if ln.startswith("## ")]
    return cut, heads


def _module_info(path: Path) -> tuple[str, dict]:
    src = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    doc = ast.get_docstring(tree) or ""
    first = next((l.strip() for l in doc.splitlines() if l.strip()), "")
    params: dict = {}
    for node in tree.body:
        names: list[str] = []
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        if any(n in ("PARAMS", "DEFAULTS", "DEFAULT_PARAMS") for n in names) and node.value is not None:
            try:
                val = ast.literal_eval(node.value)
            except Exception:  # noqa: BLE001
                val = {"_unparsed": True}
            if isinstance(val, dict):
                params = val
                break
    return first, params


# ----------------------------------------------------------------------------- T-FILES (5.3)
_FILES_LOCK = threading.Lock()
_INTRADAY_LRU: "OrderedDict[str, None]" = OrderedDict()      # past dates requested (LRU 5)
_INTRADAY_PARSED: dict[str, dict] = {}                        # date -> parsed (past dates only)
_DAILY_PARSED: dict[str, dict] = {}                           # date -> parsed (every daily file)
_INTRADAY_STARTS: dict[str, tuple[tuple[int, int], list[dict]]] = {}   # path name -> (sig, starts)
_RESEARCH_SIG: dict = {}
_RESEARCH_STATE: dict = {"rows": [], "by_algorithm": [], "counts": {"daily": 0, "intraday": 0, "bad_lines": 0}, "ledger_mtime": None}
_STRATEGIES_SIG: tuple | None = None
_STRATEGIES_DATA: dict | None = None


def _available_intraday_dates() -> list[str]:
    out = []
    try:
        for p in LOG_DIR.iterdir():
            m = INTRADAY_FILE_RE.match(p.name)
            if m:
                out.append(m.group(1))
    except FileNotFoundError:
        pass
    return sorted(out, reverse=True)


def _daily_dates() -> list[str]:
    out = []
    try:
        for p in LOG_DIR.iterdir():
            if DAILY_FILE_RE.match(p.name):
                out.append(p.name[:-6])
    except FileNotFoundError:
        pass
    return sorted(out, reverse=True)


def _scan_intraday_starts(path: Path) -> list[dict]:
    """Cheap extraction of `start` events (for NAV history) without retaining the file's lines."""
    try:
        st = path.stat()
    except FileNotFoundError:
        _INTRADAY_STARTS.pop(path.name, None)
        return []
    sig = (st.st_mtime_ns, st.st_size)
    old = _INTRADAY_STARTS.get(path.name)
    if old and old[0] == sig:
        return old[1]
    starts = []
    try:
        with open(path, "rb") as fh:
            for raw in fh:
                if b'"start"' not in raw:
                    continue
                try:
                    d = json.loads(raw.decode("utf-8", "replace"))
                except Exception:  # noqa: BLE001
                    continue
                if isinstance(d, dict) and d.get("event") == "start" and _f(d.get("nav")):
                    starts.append({"ts": d.get("ts"), "nav": _f(d.get("nav"))})
    except Exception:  # noqa: BLE001
        pass
    _INTRADAY_STARTS[path.name] = (sig, starts)
    return starts


def _gates() -> dict:
    return {"approved_paper": (LIVE / "APPROVED_PAPER.md").exists(), "halt": (LIVE / "HALT").exists(),
            "halt_intraday": (LIVE / "HALT_INTRADAY").exists()}


def _files_small_json() -> None:
    for name, path, retry in (("config", LIVE / "intraday_config.json", False),
                              ("book", STATE_DIR / "intraday_book.json", True),
                              ("last_run", STATE_DIR / "last_run.json", True)):
        try:
            data, exists, mtime, _ = _read_json_cached(path, retry=retry)
            CACHE.set_ok(name, {"data": data, "exists": exists, "mtime": mtime})
        except Exception as e:  # noqa: BLE001 - keeps last_good
            CACHE.set_error(name, f"{type(e).__name__}: {e}")


def _parse_intraday_date(date: str, today: str) -> dict:
    jf = _jsonl(LOG_DIR / f"intraday-{date}.jsonl")
    jf.refresh()
    book = (CACHE.data("book") or {}).get("data")
    deployed = (CACHE.data("config") or {}).get("data")
    gates = CACHE.data("gates") or _gates()
    return parse_intraday(jf.lines, date, book=book, deployed=deployed, gates=gates, bad_lines=jf.bad,
                          available_dates=_available_intraday_dates())


def _files_tick() -> None:
    today = today_et()
    CACHE.set_ok("gates", _gates())
    _files_small_json()
    avail = _available_intraday_dates()

    # today's intraday log
    try:
        parsed = _parse_intraday_date(today, today)
        CACHE.set_ok("files.intraday", parsed)
    except Exception as e:  # noqa: BLE001
        CACHE.set_error("files.intraday", f"{type(e).__name__}: {e}")

    # requested past intraday dates (LRU 5) + eviction of the rest
    with _FILES_LOCK:
        wanted = list(_INTRADAY_LRU.keys())
    for d in wanted:
        try:
            _INTRADAY_PARSED[d] = _parse_intraday_date(d, today)
        except Exception as e:  # noqa: BLE001
            log.debug("intraday parse %s failed: %s", d, e)
    for d in list(_INTRADAY_PARSED):
        if d not in wanted:
            _INTRADAY_PARSED.pop(d, None)
            _drop_jsonl(LOG_DIR / f"intraday-{d}.jsonl")

    # intraday start events for NAV history (cheap scan, no retained lines)
    starts = []
    for d in avail:
        for s in _scan_intraday_starts(LOG_DIR / f"intraday-{d}.jsonl"):
            starts.append(s)
    CACHE.set_ok("files.intraday_starts", starts)

    # daily logs: today + every dated file (tiny), history = 10 newest
    try:
        dates = _daily_dates()
        if today not in dates:
            dates.insert(0, today)
        for d in dates:
            jf = _jsonl(LOG_DIR / f"{d}.jsonl")
            if jf.refresh() or d not in _DAILY_PARSED:
                _DAILY_PARSED[d] = parse_daily(jf.lines, d, jf.bad)
        for d in list(_DAILY_PARSED):
            if d not in dates:
                _DAILY_PARSED.pop(d, None)
        hist_dates = [d for d in dates if _DAILY_PARSED.get(d, {}).get("exists")][:10]
        CACHE.set_ok("files.daily", {"today": _DAILY_PARSED.get(today), "by_date": dict(_DAILY_PARSED),
                                     "history": [_DAILY_PARSED[d]["history_row"] for d in hist_dates], "dates": dates})
    except Exception as e:  # noqa: BLE001
        CACHE.set_error("files.daily", f"{type(e).__name__}: {e}")

    # alerts
    try:
        jf = _jsonl(LOG_DIR / f"alerts-{today}.jsonl")
        jf.refresh()
        lines = jf.lines
        errs = sorted({redact(str(l.get("error")))[:160] for l in lines if l.get("delivered") is False and l.get("error")})
        CACHE.set_ok("files.alerts", {"date": today, "total": len(lines), "delivered": sum(1 for l in lines if l.get("delivered")),
                                      "undelivered": sum(1 for l in lines if l.get("delivered") is False), "errors": errs,
                                      "last_ts": lines[-1].get("ts") if lines else None, "exists": jf.exists})
    except Exception as e:  # noqa: BLE001
        CACHE.set_error("files.alerts", f"{type(e).__name__}: {e}")

    # nav history file (the dashboard's own appends)
    try:
        jf = _jsonl(ALLOWED_WRITE, require_key=None)
        if jf.refresh() or CACHE.get("nav_file") is None:
            pts = []
            for l in jf.lines:
                t = parse_ts(l.get("ts"))
                nav = _f(l.get("nav"))
                if t and nav is not None:
                    pts.append({"ts": iso_utc(t), "nav": nav, "cash": _f(l.get("cash")), "gross": _f(l.get("gross")), "source": "dashboard"})
            CACHE.set_ok("nav_file", {"points": pts, "bad": jf.bad, "last_ts": pts[-1]["ts"] if pts else None, "mtime": jf.mtime})
        else:
            CACHE.set_ok("nav_file", CACHE.data("nav_file"))
    except Exception as e:  # noqa: BLE001
        CACHE.set_error("nav_file", f"{type(e).__name__}: {e}")

    # research
    try:
        _research_tick()
    except Exception as e:  # noqa: BLE001
        CACHE.set_error("research", f"{type(e).__name__}: {e}")

    # strategies
    try:
        _strategies_tick()
    except Exception as e:  # noqa: BLE001
        CACHE.set_error("strategies", f"{type(e).__name__}: {e}")


def _research_tick() -> None:
    global _RESEARCH_SIG
    st = _RESEARCH_STATE
    jf = _jsonl(RESEARCH / "experiments.jsonl", require_key=None)
    if jf.refresh() or not st["rows"] and jf.lines:
        rows = [_augment_row(r) for r in jf.lines]
        st["rows"] = rows
        st["by_algorithm"] = _by_algorithm(rows)
        st["counts"] = {"daily": sum(1 for r in rows if r["track"] == "daily"),
                        "intraday": sum(1 for r in rows if r["track"] == "intraday"), "bad_lines": jf.bad}
        st["ledger_mtime"] = jf.mtime
    prev = CACHE.data("research") or {}
    champ_text, champ_mtime, ch_changed = _read_text_cached(RESEARCH / "champion.json")
    bl_text, _, bl_changed = _read_text_cached(RESEARCH / "backlog.md")
    jn_text, _, jn_changed = _read_text_cached(RESEARCH / "journal.md")
    bk_text, _, bk_changed = _read_text_cached(RESEARCH / "BLOCKERS.md")
    champion = prev.get("champion")
    if ch_changed or "champion" not in prev:
        champion = None
        if champ_text:
            try:
                champion = json.loads(champ_text)
                if isinstance(champion, dict):
                    stats = champion.get("stats") or {}
                    champion["parsed"] = {"car": to_num(stats.get("Compounding Annual Return")), "sharpe": to_num(stats.get("Sharpe Ratio")),
                                          "dd": to_num(stats.get("Drawdown")), "orders": _i(to_num(stats.get("Total Orders")))}
            except Exception as e:  # noqa: BLE001
                champion = {"error": f"champion.json: {e}"}
    backlog = prev.get("backlog") if not (bl_changed or "backlog" not in prev) else (parse_backlog(bl_text) if bl_text else {"open": [], "meta": {"open_n": 0, "done_n": 0, "objective_excerpt": "", "preamble": ""}})
    journal = prev.get("journal") if not (jn_changed or "journal" not in prev) else (parse_journal(jn_text) if jn_text else [])
    if bk_changed or "blockers" not in prev:
        excerpt, heads = parse_blockers(bk_text) if bk_text else ("", [])
        blockers = {"excerpt": excerpt, "headings": heads}
    else:
        blockers = prev.get("blockers")
    try:
        reports = [p.name for p in sorted((RESEARCH / "reports").glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)]
    except Exception:  # noqa: BLE001
        reports = []
    run_dir = (champion or {}).get("run_dir") if isinstance(champion, dict) else None
    run_dir_exists = bool(run_dir) and (REPO / str(run_dir)).exists()
    CACHE.set_ok("research", {"rows": st["rows"], "by_algorithm": st["by_algorithm"], "counts": st["counts"],
                              "ledger_mtime": st["ledger_mtime"], "champion": champion, "backlog": backlog, "journal": journal,
                              "blockers": blockers, "reports": reports, "champion_run_dir_exists": run_dir_exists})


def _strategies_tick() -> None:
    global _STRATEGIES_SIG, _STRATEGIES_DATA
    files = sorted(list(ALGORITHMS.glob("*/main.py")) + list((ALGORITHMS / "intraday").glob("*/signal.py")))
    sig = tuple((str(p), p.stat().st_mtime_ns) for p in files)
    if sig != _STRATEGIES_SIG or _STRATEGIES_DATA is None:
        mods = []
        for p in sorted((ALGORITHMS / "intraday").glob("*/signal.py")):
            try:
                first, params = _module_info(p)
            except Exception as e:  # noqa: BLE001
                first, params = f"(unparsable: {e})", {}
            mods.append({"name": p.parent.name, "docstring_first_line": first, "params": params})
        daily, docs = [], {}
        for d in sorted(ALGORITHMS.iterdir()):
            if d.is_dir() and (d / "main.py").exists() and d.name not in ("_template", "intraday"):
                daily.append(d.name)
                try:
                    docs[d.name] = _module_info(d / "main.py")[0]
                except Exception as e:  # noqa: BLE001
                    docs[d.name] = f"(unparsable: {e})"
        _STRATEGIES_DATA = {"intraday_modules": mods, "daily_algorithms": daily, "daily_docstrings": docs}
        _STRATEGIES_SIG = sig
    CACHE.set_ok("strategies", _STRATEGIES_DATA)


def _framework() -> dict:
    return {"MIN_CHANGE": MIN_CHANGE, "PER_SYMBOL_HARD_CAP": PER_SYMBOL_HARD_CAP, "GROSS_HARD_CAP": GROSS_HARD_CAP,
            "DAILY_LOSS_LIMIT": DAILY_LOSS_LIMIT, "FLATTEN_MINUTE": FLATTEN_MINUTE, "EXIT_MINUTE": EXIT_MINUTE,
            "SLIPPAGE_BPS": SLIPPAGE_BPS, "UNIVERSE": list(UNIVERSE), "DAILY_SLEEVE_UNIVERSE": sorted(DAILY_SLEEVE_UNIVERSE)}


def _files_worker(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            _files_tick()
            CACHE.set_ok("files", {"ok": True})
            _log_state("files", None)
        except Exception as e:  # noqa: BLE001
            msg = redact(f"{type(e).__name__}: {e}")[:300]
            CACHE.set_error("files", msg)
            _log_state("files", msg)
        finally:
            CACHE.heartbeat("files")
        stop.wait(PERIODS["files"])


# ----------------------------------------------------------------------------- T-IB (5.2)
_IB_STATE_DEFAULT = {"connected": False, "account_id": None, "reconnects": 0, "last_good_at": None, "last_error": None,
                     "skew_s": None, "skew_at": None, "last_append_at": None, "backoff_s": PERIODS["ib"],
                     "connect_attempts": 0, "connected_since": None, "error_since": None}


def _ib_collect(ib, account: str) -> dict:
    """One read-only tick: summary, portfolio, open orders, fills. Runs only inside T-IB."""
    pref = {"USD": 0, "BASE": 1, "": 2}
    best: dict[str, tuple[int, object]] = {}
    for row in ib.accountSummary(account):
        tag, cur = getattr(row, "tag", None), getattr(row, "currency", "") or ""
        if tag in IB_TAGS and cur in pref:
            rank = pref[cur]
            if tag not in best or rank < best[tag][0]:
                best[tag] = (rank, row.value)
    # UnrealizedPnL / RealizedPnL are not account-summary tags; they arrive as account values
    # ($LEDGER) through the account-updates subscription, so fill the gaps from there.
    try:
        for row in ib.accountValues(account):
            tag, cur = getattr(row, "tag", None), getattr(row, "currency", "") or ""
            if tag in IB_TAGS and cur in pref:
                rank = pref[cur] + 3
                if tag not in best or rank < best[tag][0]:
                    best[tag] = (rank, row.value)
    except Exception as e:  # noqa: BLE001
        log.debug("accountValues failed: %s", e)
    summary = {tag: _f(best[tag][1]) if tag in best else None for tag in IB_TAGS}

    positions, warnings, realized_by_symbol = [], [], {}
    for item in ib.portfolio(account):
        sym = norm_symbol(getattr(item.contract, "symbol", ""))
        sec = getattr(item.contract, "secType", "STK")
        if sec and sec != "STK":
            sym = f"{sym} {sec}"
        price = _f(getattr(item, "marketPrice", None))
        unpriced = price is None or price == 0
        sleeve = sleeve_of(sym)
        if sleeve == "other":
            warnings.append(f"{sym} in neither universe -> other")
        realized_by_symbol[sym] = _f(getattr(item, "realizedPNL", None))
        positions.append({"symbol": sym, "shares": _i(item.position), "avg_cost": _f(getattr(item, "averageCost", None)),
                          "price": None if unpriced else price, "market_value": _f(getattr(item, "marketValue", None)),
                          "unrealized_pnl": _f(getattr(item, "unrealizedPNL", None)), "sleeve": sleeve, "unpriced": bool(unpriced)})

    open_orders = []
    for tr in ib.openTrades():
        o, s = tr.order, tr.orderStatus
        sym = norm_symbol(getattr(tr.contract, "symbol", ""))
        open_orders.append({"order_id": getattr(o, "orderId", None), "symbol": sym, "action": getattr(o, "action", None),
                            "qty": _f(getattr(o, "totalQuantity", None)), "order_type": getattr(o, "orderType", None),
                            "status": getattr(s, "status", None), "filled": _f(getattr(s, "filled", None)),
                            "order_ref": getattr(o, "orderRef", None) or None, "client_id": getattr(o, "clientId", None),
                            "sleeve": sleeve_of(sym, getattr(o, "orderRef", None))})

    fills = []
    for f in ib.fills():
        ex = f.execution
        sym = norm_symbol(getattr(f.contract, "symbol", ""))
        side = getattr(ex, "side", "")
        side = "BUY" if side == "BOT" else ("SELL" if side == "SLD" else side)
        comm = getattr(getattr(f, "commissionReport", None), "commission", None)
        t = getattr(f, "time", None) or getattr(ex, "time", None)
        ref = getattr(ex, "orderRef", None) or None
        fills.append({"ts": iso_utc(parse_ts(t)) if parse_ts(t) else None, "symbol": sym, "side": side,
                      "qty": _f(getattr(ex, "shares", None)), "price": _f(getattr(ex, "price", None)), "order_ref": ref,
                      "exec_id": getattr(ex, "execId", None), "commission": _f(comm), "sleeve": sleeve_of(sym, ref),
                      "order_id": getattr(ex, "orderId", None), "client_id": getattr(ex, "clientId", None)})
    fills.sort(key=lambda x: x["ts"] or "", reverse=True)
    return {"account_id": account, "summary": summary, "positions": positions, "open_orders": open_orders,
            "fills": fills[:500], "warnings": sorted(set(warnings)), "realized_by_symbol": realized_by_symbol,
            "collected_at": iso_utc()}


def _ib_worker(stop: threading.Event) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    state = dict(_IB_STATE_DEFAULT)

    def publish():
        CACHE.set_ok("ib_state", dict(state))

    def wait_hb(seconds: float):
        end = time.monotonic() + seconds
        while not stop.is_set() and time.monotonic() < end:
            CACHE.heartbeat("ib")
            stop.wait(min(5.0, max(0.1, end - time.monotonic())))

    try:
        from ib_async import IB
    except Exception as e:  # noqa: BLE001
        msg = redact(f"ib_async unavailable: {type(e).__name__}: {e}")[:300]
        CACHE.set_error("ibkr", msg)
        state["last_error"] = msg
        publish()
        _log_state("ibkr", msg)
        while not stop.is_set():
            wait_hb(60)
        return

    ib = None
    account = ""
    backoff = PERIODS["ib"]
    last_time_req = 0.0
    last_append = 0.0
    try:                                        # seed the 60 s throttle from the file so a quick restart cannot double-append
        if ALLOWED_WRITE.exists():
            with open(ALLOWED_WRITE, "rb") as fh:
                fh.seek(max(0, ALLOWED_WRITE.stat().st_size - 4096))
                tail = [l for l in fh.read().decode("utf-8", "replace").splitlines() if l.strip()]
            prev = parse_ts(json.loads(tail[-1]).get("ts")) if tail else None
            gap = (utcnow() - prev).total_seconds() if prev else None
            if gap is not None and 0 <= gap < 60:
                last_append = time.monotonic() - gap
                state["last_append_at"] = iso_utc(prev)
    except Exception:  # noqa: BLE001 - a bad last line only means no seed
        pass
    ever_connected = False
    while not stop.is_set():
        try:
            if ib is None or not ib.isConnected():
                if ib is not None:
                    try:
                        ib.disconnect()
                    except Exception:  # noqa: BLE001
                        pass
                ib = IB()                       # a half-broken IB is not reusable: fresh object per attempt
                ib.RequestTimeout = 10

                def _on_disconnected():
                    state["connected"] = False
                    publish()

                ib.disconnectedEvent += _on_disconnected
                state["connect_attempts"] += 1
                ib.connect(IB_HOST, IB_PORT, clientId=81, timeout=20, readonly=True)   # the only client id; never retried under another
                accts = ib.managedAccounts()
                account = accts[0] if accts else ""
                ib.reqAccountSummary()
                ib.reqAllOpenOrders()
                ib.reqExecutions()
                if ever_connected:
                    state["reconnects"] += 1
                ever_connected = True
                state.update(connected=True, account_id=account, last_error=None, backoff_s=PERIODS["ib"],
                             connected_since=iso_utc(), error_since=None)
                backoff = PERIODS["ib"]
                last_time_req = 0.0
                _log_state("ibkr", None)
                log.info("IB connected: account %s clientId %s", account, IB_CLIENT_ID)
            if time.monotonic() - last_time_req > 300:
                try:
                    srv = ib.reqCurrentTime()
                    d = parse_ts(srv)
                    state["skew_s"] = round((d - utcnow()).total_seconds(), 2) if d else None
                    state["skew_at"] = iso_utc()
                except Exception as e:  # noqa: BLE001
                    log.debug("reqCurrentTime failed: %s", e)
                last_time_req = time.monotonic()
            data = _ib_collect(ib, account)
            CACHE.set_ok("ibkr", data)
            state["connected"] = True
            state["last_good_at"] = data["collected_at"]
            nav = data["summary"].get("NetLiquidation")
            if nav is not None and math.isfinite(nav) and nav > 0 and time.monotonic() - last_append >= 60:
                append_nav({"ts": iso_utc(), "nav": nav, "cash": data["summary"].get("TotalCashValue"),
                            "gross": data["summary"].get("GrossPositionValue")})
                last_append = time.monotonic()
                state["last_append_at"] = iso_utc()
            publish()
            CACHE.heartbeat("ib")
        except Exception as e:  # noqa: BLE001
            msg = redact(f"{type(e).__name__}: {e}")[:300] or type(e).__name__
            CACHE.set_error("ibkr", msg)
            state["connected"] = False
            state["last_error"] = msg
            state["error_since"] = state.get("error_since") or iso_utc()
            state["backoff_s"] = backoff
            publish()
            _log_state("ibkr", msg)
            try:
                if ib is not None:
                    ib.disconnect()
            except Exception:  # noqa: BLE001
                pass
            ib = None
            CACHE.heartbeat("ib")
            wait_hb(backoff)
            backoff = min(backoff * 2, 300)
            continue
        try:
            end = time.monotonic() + PERIODS["ib"]
            while not stop.is_set() and time.monotonic() < end:
                ib.sleep(1)                       # pumps the socket between ticks; 1 s slices so stop() is prompt
        except Exception:  # noqa: BLE001
            wait_hb(PERIODS["ib"])
        CACHE.heartbeat("ib")
    try:
        if ib is not None:
            ib.disconnect()
    except Exception:  # noqa: BLE001
        pass


# ----------------------------------------------------------------------------- T-SYS (5.4)
def _run(cmd: list[str], timeout: float, cwd: Path | None = None) -> tuple[int, str, str]:
    res = subprocess.run([str(c) for c in cmd], capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
                         cwd=str(cwd) if cwd else None, shell=False, creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL)
    return res.returncode, res.stdout or "", res.stderr or ""


def _strip_clixml(text: str) -> str:
    keep = []
    for ln in text.splitlines():
        s = ln.lstrip()
        if s.startswith("#< CLIXML") or s.startswith("<Objs") or s.startswith("<?xml"):
            continue
        keep.append(ln.rstrip("\r"))
    return "\n".join(keep)


def _openclaw_cmd(*args: str) -> list[str]:
    if not NODE_EXE.exists() or not OPENCLAW_JS.exists():
        raise FileNotFoundError(f"openclaw CLI not found under {NODE_DIR}")
    return [str(NODE_EXE), str(OPENCLAW_JS), *args]


def _parse_openclaw_table(text: str) -> list[dict]:
    lines = [l for l in text.splitlines() if l.strip()]
    hdr_i = next((i for i, l in enumerate(lines) if l.lstrip().startswith("ID")), None)
    rows = []
    if hdr_i is not None:
        hdr = lines[hdr_i]
        cols = [(m.group(0).strip().lower(), m.start()) for m in re.finditer(r"\S+(?: \S+)*", hdr)]
        for l in lines[hdr_i + 1:]:
            if set(l.strip()) <= set("-─═│| "):
                continue
            vals = {}
            for k, (name, start) in enumerate(cols):
                end = cols[k + 1][1] if k + 1 < len(cols) else len(l)
                vals[name] = l[start:end].strip()
            row = {"name": vals.get("name") or None, "schedule": vals.get("schedule") or None, "next": vals.get("next") or None,
                   "last": vals.get("last") or None, "status": vals.get("status") or None, "id": vals.get("id") or None,
                   "raw_row": l.strip()[:400]}
            if not row["name"]:
                row["name"] = next((j for j in KNOWN_JOBS if j in l), None)
            rows.append(row)
    if not rows:
        for l in lines:
            job = next((j for j in KNOWN_JOBS if j in l), None)
            if job:
                parts = [p.strip() for p in re.split(r"\s{2,}|[│|]", l) if p.strip()]
                rows.append({"name": job, "schedule": parts[3] if len(parts) > 3 else None, "next": parts[4] if len(parts) > 4 else None,
                             "last": parts[5] if len(parts) > 5 else None, "status": parts[6] if len(parts) > 6 else None,
                             "id": parts[0] if parts else None, "raw_row": l.strip()[:400]})
    order = {"research-iterate": 0, "research-review": 1}
    rows.sort(key=lambda r: order.get(str(r.get("name")), 9))
    return rows


def _collect_openclaw_list() -> dict:
    rc, out, err = _run(_openclaw_cmd("automations", "list", "--all"), timeout=25)
    text = _strip_clixml(out)
    rows = _parse_openclaw_table(text)
    if rc != 0 and not rows:
        raise RuntimeError(f"openclaw list rc={rc}: {(err or out)[-200:]}")
    return {"automations": rows}


def _first_json(text: str):
    i = text.find("{")
    if i < 0:
        raise ValueError("no JSON object in output")
    return json.JSONDecoder().raw_decode(text[i:])[0]


def _run_entry(e: dict) -> dict:
    ts = None
    for k in ("runAtIso", "startedAt", "finishedAt", "runAtMs", "ts", "createdAt"):
        if e.get(k) is not None:
            d = parse_ts(e[k])
            if d:
                ts = iso_utc(d)
                break
    nxt = None
    for k in ("nextRunAtIso", "nextRunAtMs"):
        if e.get(k) is not None:
            d = parse_ts(e[k])
            if d:
                nxt = iso_utc(d)
                break
    summary = str(e.get("summary") or "")
    return {"status": e.get("status"), "completionStatus": e.get("completionStatus"), "durationMs": e.get("durationMs"),
            "summary_tail": redact(summary[-300:]), "ts": ts, "error": e.get("error") or e.get("errorReason"), "next_run": nxt,
            "runId": e.get("runId")}


def _collect_openclaw_runs() -> dict:
    out: dict = {}
    errors = []
    for job, jid in JOB_IDS.items():
        key = job.replace("-", "_")
        try:
            rc, txt, err = _run(_openclaw_cmd("automations", "runs", jid, "--limit", "5"), timeout=25)
            data = _first_json(_strip_clixml(txt))
            entries = data.get("entries") if isinstance(data, dict) else data
            out[key] = [_run_entry(e) for e in (entries or [])[:5] if isinstance(e, dict)]
        except Exception as e:  # noqa: BLE001
            out[key] = []
            errors.append(f"{job}: {type(e).__name__}: {e}")
    if errors and not any(out.values()):
        raise RuntimeError("; ".join(errors)[:300])
    out["_errors"] = errors
    return out


def _collect_git() -> dict:
    rc, out, err = _run(["git", "log", "--oneline", "-n", "30"], timeout=10, cwd=REPO)
    if rc != 0:
        raise RuntimeError(f"git log rc={rc}: {err[-200:]}")
    rows = []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        h, _, subj = ln.partition(" ")
        rows.append({"hash": h, "subject": subj})
    return {"git_log": rows}


_PS_TASKS = ("Get-ScheduledTask -TaskName 'Quant *','OpenClaw*' -ErrorAction SilentlyContinue | ForEach-Object { "
             "$i=$_|Get-ScheduledTaskInfo; $n=$null; if($i.NextRunTime){$n=$i.NextRunTime.ToString('o')}; "
             "$l=$null; if($i.LastRunTime){$l=$i.LastRunTime.ToString('o')}; "
             "[pscustomobject]@{name=$_.TaskName; state=[string]$_.State; next=$n; last=$l; result=$i.LastTaskResult} } "
             "| ConvertTo-Json -Compress")


def _task_result_text(name: str, code) -> str | None:
    if code is None:
        return None
    try:
        c = int(code)
    except Exception:  # noqa: BLE001
        return str(code)
    table = {0: "OK", 267009: "RUNNING", 267011: "NEVER_RUN", 267014: "TERMINATED"}
    if c in table:
        return table[c]
    if c in (267008, 267010):
        return str(c)
    if name == "Quant Paper Rebalance" and c in (1, 2, 3):
        return {1: "connect_failed", 2: "flatten", 3: "refused"}[c]
    return f"0x{c & 0xFFFFFFFF:08X} unknown"


def _collect_tasks() -> dict:
    rc, out, err = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _PS_TASKS], timeout=20)
    text = _strip_clixml(out).strip()
    if not text:
        if rc != 0:
            raise RuntimeError(f"Get-ScheduledTask rc={rc}: {err[-200:]}")
        return {"tasks": []}
    i = min([k for k in (text.find("["), text.find("{")) if k >= 0], default=-1)
    if i < 0:
        raise RuntimeError(f"unexpected task output: {text[:120]}")
    data = json.loads(text[i:])
    if isinstance(data, dict):
        data = [data]
    tasks = []
    for t in data:
        name = str(t.get("name"))
        res = t.get("result")
        tasks.append({"name": name, "state": t.get("state"), "next_run": _local_iso_to_utc(t.get("next")),
                      "last_run": _local_iso_to_utc(t.get("last")), "last_result": res,
                      "last_result_text": _task_result_text(name, res)})
    return {"tasks": tasks}


def _collect_gateway_log() -> dict:
    try:
        files = sorted(GATEWAY_LOG_DIR.glob("openclaw-????-??-??.log"))
    except Exception:  # noqa: BLE001
        files = []
    if not files:
        return {"file": None, "lines": [], "stalled_last_hour": 0}
    path = files[-1]
    size = path.stat().st_size
    with open(path, "rb") as fh:
        fh.seek(max(0, size - 64 * 1024))
        chunk = fh.read()
    raw_lines = chunk.decode("utf-8", "replace").splitlines()
    if size > 64 * 1024 and raw_lines:
        raw_lines = raw_lines[1:]                 # first line may be a fragment
    raw_lines = [l for l in raw_lines if l.strip()][-50:]
    out = []
    stalled = 0
    cutoff = utcnow() - dt.timedelta(hours=1)
    for l in raw_lines:
        try:
            d = json.loads(l)
            if not isinstance(d, dict):
                raise ValueError
        except Exception:  # noqa: BLE001
            out.append({"raw": redact(l[:300])})
            if "stalled session" in l:
                stalled += 1
            continue
        meta = d.get("_meta") if isinstance(d.get("_meta"), dict) else {}
        t = meta.get("date") or d.get("time")
        level = meta.get("logLevelName") or d.get("level")
        subsystem = None
        k0 = d.get("0")
        if isinstance(k0, str):
            try:
                j = json.loads(k0)
                if isinstance(j, dict):
                    subsystem = "/".join(str(j[k]) for k in ("subsystem", "module") if j.get(k)) or None
            except Exception:  # noqa: BLE001
                subsystem = None                 # key "0" was plain text, not a subsystem record
        msg = None
        for k in ("1", "2", "message"):
            if isinstance(d.get(k), str):
                msg = d[k]
                break
        if msg is None:
            msg = json.dumps(d.get("1"), default=str)[:300]
        msg = redact(msg)[:500]
        if "stalled session" in msg:
            td = parse_ts(t)
            if td is None or td >= cutoff:
                stalled += 1
        out.append({"time": t, "level": level, "subsystem": subsystem, "message": msg})
    return {"file": str(path), "lines": out, "stalled_last_hour": stalled}


def _theta_alive() -> bool:
    try:
        urllib.request.urlopen(THETA_BASE + "/v3/option/list/expirations?symbol=SPY", timeout=5).read(64)
        return True
    except Exception:  # noqa: BLE001
        return False


def _collect_theta() -> dict:
    return {"alive": _theta_alive(), "checked_at": iso_utc()}


def _sys_worker(stop: threading.Event) -> None:
    steps = (("sys.openclaw", _collect_openclaw_list), ("sys.runs", _collect_openclaw_runs), ("sys.git", _collect_git),
             ("sys.tasks", _collect_tasks), ("sys.gateway_log", _collect_gateway_log), ("sys.theta", _collect_theta))
    while not stop.is_set():
        for name, fn in steps:
            if stop.is_set():
                break
            try:
                CACHE.set_ok(name, fn())
                _log_state(name, None)
            except Exception as e:  # noqa: BLE001
                msg = redact(f"{type(e).__name__}: {e}")[:300]
                CACHE.set_error(name, msg)
                _log_state(name, msg)
            CACHE.heartbeat("system")
        CACHE.set_ok("system", {"ok": True})
        CACHE.heartbeat("system")
        stop.wait(PERIODS["system"])


# ----------------------------------------------------------------------------- T-DATA (5.5)
_STORE_CACHE: dict[str, dict[str, dict]] = {"ibkr_minute": {}, "alpaca_minute": {}}
_OPTIONS_SYMBOL = {"symbol": "SPY"}
_OPTIONS_LOCK = threading.Lock()


def _scan_store(dir_path: Path, prev: dict[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not dir_path.exists():
        return out
    for p in sorted(dir_path.glob("*.parquet")):
        if p.name.startswith("_"):
            continue
        sym = p.stem.upper()
        try:
            st = p.stat()
        except FileNotFoundError:
            continue
        sig = (st.st_mtime_ns, st.st_size)
        old = prev.get(sym)
        if old and old["sig"] == sig:
            out[sym] = old
            continue
        row = {"symbol": sym, "sessions": None, "first": None, "last": None}
        try:
            import pandas as pd
            df = pd.read_parquet(p, columns=[])
            idx = df.index
            if not isinstance(idx, pd.DatetimeIndex):
                idx = pd.DatetimeIndex(pd.to_datetime(df["date"] if "date" in df.columns else idx))
            if idx.tz is None:
                idx = idx.tz_localize("UTC")
            idx = idx.tz_convert(ET)
            days = idx.normalize().unique()
            if len(days):
                row.update(sessions=int(len(days)), first=days.min().date().isoformat(), last=days.max().date().isoformat())
            else:
                row["sessions"] = 0
        except Exception as e:  # noqa: BLE001 - sessions stays None ("scan failed")
            log.debug("store scan %s failed: %s", p, e)
        out[sym] = {"sig": sig, "row": row}
    return out


def _data_scan() -> dict:
    for key, d in (("ibkr_minute", REPO / "data" / "minute"), ("alpaca_minute", REPO / "data" / "minute_alpaca")):
        _STORE_CACHE[key] = _scan_store(d, _STORE_CACHE[key])
    stores = {k: {"symbols": [v["row"] for v in _STORE_CACHE[k].values()]} for k in _STORE_CACHE}
    lean_daily = LEAN_ROOT / "Data" / "equity" / "usa" / "daily"
    n = len(list(lean_daily.glob("*.zip"))) if lean_daily.exists() else 0
    if n == 0:
        try:
            man = json.loads((RESEARCH / "data_manifest.json").read_text(encoding="utf-8"))
            n = int(man.get("symbols_written") or len(man.get("data") or {}))
        except Exception:  # noqa: BLE001
            n = None
    lean_min = LEAN_ROOT / "Data" / "equity" / "usa" / "minute"
    minute_syms = sorted(p.name for p in lean_min.iterdir() if p.is_dir()) if lean_min.exists() else []
    stores["lean_daily_n"] = n
    stores["lean_minute_symbols"] = minute_syms
    events = {"generated": None, "symbols_n": None}
    try:
        ev = json.loads((REPO / "data" / "events" / "earnings.json").read_text(encoding="utf-8"))
        events = {"generated": ev.get("generated"), "symbols_n": len(ev.get("earnings") or {})}
    except Exception:  # noqa: BLE001
        pass
    return {"stores": stores, "events": events, "keys_present": keys_present(), "scan_as_of": iso_utc()}


def _theta_csv(path: str, timeout: float = 15, **params):
    """Theta Terminal GET with a short timeout (theta_data._get waits 120 s)."""
    import io
    import pandas as pd
    q = {k: v for k, v in params.items() if v is not None}
    url = THETA_BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
    with urllib.request.urlopen(url, timeout=timeout) as r:
        text = r.read().decode("utf-8")
    if not text.strip():
        return pd.DataFrame()
    return pd.read_csv(io.StringIO(text))


def _options_fetch(symbol: str, alive: bool) -> dict:
    base = {"alive": alive, "nearest_expiration": None, "atm_quotes": [], "message": None, "symbol": symbol, "spot": None}
    if not alive:
        base["message"] = "Theta terminal down - no quotes"
        return base
    t0 = time.monotonic()
    try:
        df = _theta_csv("/v3/option/list/expirations", symbol=symbol, timeout=10)
        exps = sorted(str(x) for x in df["expiration"].astype(str)) if len(df) and "expiration" in df.columns else []
        today = dt.date.today()
        exp = next((e for e in exps if dt.date.fromisoformat(e) >= today), None)
        base["nearest_expiration"] = exp
        if exp is None:
            base["message"] = f"no expirations listed for {symbol}"
            return base
        remaining = max(2.0, 15.0 - (time.monotonic() - t0))
        q = _theta_csv("/v3/option/snapshot/quote", symbol=symbol, expiration=exp, strike="*", right="both", timeout=remaining)
        if q is None or not len(q) or "strike" not in q.columns:
            base["message"] = f"no quotes returned for {symbol} {exp}"
            return base
        q = q.copy()
        q["mid"] = (q["bid"].astype(float) + q["ask"].astype(float)) / 2.0
        q["right"] = q["right"].astype(str).str.upper().str[0]
        spot = None
        ibd = CACHE.data("ibkr") or {}
        for p in ibd.get("positions") or []:
            if p.get("symbol") == symbol and p.get("price"):
                spot = float(p["price"])
        if spot is None:
            with _CHARTS_LOCK:
                for (sym, d, _s), ent in _CHARTS.items():
                    bars = (ent.get("data") or {}).get("bars") or []
                    if sym == symbol and d == today_et() and bars:
                        spot = float(bars[-1]["c"])
        if spot is None:
            for col in ("underlying_price", "underlying"):
                if col in q.columns:
                    spot = _f(q[col].astype(float).median())
                    break
        if spot is None:
            calls = q[q["right"] == "C"].groupby("strike")["mid"].first()
            puts = q[q["right"] == "P"].groupby("strike")["mid"].first()
            both = calls.to_frame("c").join(puts.to_frame("p"), how="inner")
            both = both[(both["c"] > 0) & (both["p"] > 0)]
            if len(both):
                spot = float((both["c"] - both["p"]).abs().idxmin())   # put-call parity ATM
        base["spot"] = spot
        strikes = sorted(set(float(s) for s in q["strike"]))
        if spot is not None:
            strikes = sorted(strikes, key=lambda s: abs(s - spot))[:5]
        else:
            strikes = strikes[:5]
        strikes = sorted(strikes)
        rows = []
        for s in strikes:
            for right in ("C", "P"):
                sub = q[(q["strike"].astype(float) == s) & (q["right"] == right)]
                if not len(sub):
                    continue
                r = sub.iloc[0]
                bid, ask = _f(r.get("bid")), _f(r.get("ask"))
                mid = (bid + ask) / 2.0 if bid is not None and ask is not None else None
                iv = _f(r.get("implied_vol")) if "implied_vol" in sub.columns else None
                rows.append({"strike": s, "right": right, "bid": bid, "ask": ask, "mid": mid, "iv": iv})
        base["atm_quotes"] = rows
        if not rows:
            base["message"] = f"no ATM quotes for {symbol} {exp}"
        return base
    except Exception as e:  # noqa: BLE001
        base["message"] = redact(f"quote fetch failed: {type(e).__name__}: {e}")[:200]
        return base


def _data_worker(stop: threading.Event) -> None:
    last_scan = 0.0
    while not stop.is_set():
        try:
            if time.monotonic() - last_scan >= 600 or CACHE.get("data.scan") is None:
                CACHE.set_ok("data.scan", _data_scan())
                last_scan = time.monotonic()
                _log_state("data.scan", None)
        except Exception as e:  # noqa: BLE001
            msg = redact(f"{type(e).__name__}: {e}")[:300]
            CACHE.set_error("data.scan", msg)
            _log_state("data.scan", msg)
        CACHE.heartbeat("data")
        try:
            th = CACHE.data("sys.theta")
            alive = bool(th["alive"]) if th else _theta_alive()
            with _OPTIONS_LOCK:
                sym = _OPTIONS_SYMBOL["symbol"]
            CACHE.set_ok("options", _options_fetch(sym, alive))
        except Exception as e:  # noqa: BLE001
            CACHE.set_error("options", f"{type(e).__name__}: {e}")
        CACHE.heartbeat("data")
        stop.wait(PERIODS["data"])


# ----------------------------------------------------------------------------- T-QUOTES (5.6)
_CHARTS: dict[tuple, dict] = {}
_CHARTS_LOCK = threading.Lock()
_WATCH: "OrderedDict[tuple, None]" = OrderedDict()
_EXECUTOR: ThreadPoolExecutor | None = None
_YAHOO = {"last_ok_at": None, "last_error": None, "tested": False}


def _bars_from_df(df, date: str) -> list[dict]:
    import pandas as pd
    if df is None or len(df) == 0:
        return []
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    cols = {str(c).lower(): c for c in df.columns}
    o, h, l, c, v = (cols.get(k) for k in ("open", "high", "low", "close", "volume"))
    if o is None:
        o, h, l, c, v = (cols.get(k) for k in ("o", "h", "l", "c", "v"))
    if c is None:
        return []
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        idx = pd.DatetimeIndex(pd.to_datetime(idx))
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    idx = idx.tz_convert(ET)
    df.index = idx
    day = dt.date.fromisoformat(date)
    start = dt.datetime.combine(day, dt.time(9, 30), tzinfo=ET)
    end = dt.datetime.combine(day, dt.time(16, 0), tzinfo=ET)
    df = df[(df.index >= start) & (df.index < end)]
    out = []
    for t, row in df.iterrows():
        cc = _f(row[c])
        if cc is None:
            continue
        out.append({"t": t.isoformat(timespec="seconds"), "o": _f(row[o]) if o is not None else cc,
                    "h": _f(row[h]) if h is not None else cc, "l": _f(row[l]) if l is not None else cc,
                    "c": cc, "v": _i(row[v]) if v is not None else None})
    return out[-400:]


def _yf_bars(symbol: str, period: str, date: str) -> list[dict]:
    import yfinance as yf
    try:
        df = yf.download(symbol, period=period, interval="1m", auto_adjust=False, prepost=False, progress=False,
                         threads=False, timeout=20)
        _YAHOO["last_ok_at"] = iso_utc()
        _YAHOO["last_error"] = None
    except Exception as e:  # noqa: BLE001
        _YAHOO["last_error"] = redact(f"{type(e).__name__}: {e}")[:200]
        raise
    finally:
        _YAHOO["tested"] = True
    return _bars_from_df(df, date)


def _store_bars_ibkr(symbol: str, date: str) -> list[dict]:
    if load_bars is None:
        return []
    d = dt.date.fromisoformat(date)
    return _bars_from_df(load_bars(symbol, start=d, end=d), date)


def _store_bars_alpaca(symbol: str, date: str) -> list[dict]:
    import pandas as pd
    p = REPO / "data" / "minute_alpaca" / f"{symbol.upper()}.parquet"
    if not p.exists():
        return []
    d = dt.date.fromisoformat(date)
    start = pd.Timestamp(d, tz=ET).tz_convert("UTC")
    end = start + pd.Timedelta(days=1)
    try:
        df = pd.read_parquet(p, filters=[("date", ">=", start.to_pydatetime()), ("date", "<", end.to_pydatetime())])
    except Exception:  # noqa: BLE001
        df = pd.read_parquet(p)
        idx = df.index if df.index.tz is not None else df.index.tz_localize("UTC")
        df = df[(idx >= start) & (idx < end)]
    return _bars_from_df(df, date)


def _intraday_parsed(date: str) -> dict | None:
    today = today_et()
    if date == today:
        p = CACHE.data("files.intraday")
        if p is None:                          # before T-FILES has run: parse today's log on demand
            try:
                p = _parse_intraday_date(today, today)
                CACHE.set_ok("files.intraday", p)
            except Exception as e:  # noqa: BLE001
                CACHE.set_error("files.intraday", f"{type(e).__name__}: {e}")
        return p
    p = _INTRADAY_PARSED.get(date)
    if p is not None:
        return p
    with _FILES_LOCK:
        _INTRADAY_LRU[date] = None
        _INTRADAY_LRU.move_to_end(date)
        while len(_INTRADAY_LRU) > 5:
            _INTRADAY_LRU.popitem(last=False)
    try:
        p = _parse_intraday_date(date, today)
        _INTRADAY_PARSED[date] = p
        return p
    except Exception as e:  # noqa: BLE001
        log.debug("on-demand intraday parse %s: %s", date, e)
        return None


def _daily_parsed(date: str) -> dict | None:
    fd = CACHE.data("files.daily") or {}
    p = (fd.get("by_date") or {}).get(date)
    if p is not None:
        return p
    jf = _jsonl(LOG_DIR / f"{date}.jsonl")
    jf.refresh()
    return parse_daily(jf.lines, date, jf.bad)


def _trade_markers(symbol: str, date: str) -> list[dict]:
    out = []
    intr = _intraday_parsed(date) or {}
    for tr in intr.get("trades") or []:
        if tr.get("symbol") == symbol and tr.get("qty"):
            out.append({"t": et_minute_iso(parse_ts(tr.get("ts"))), "qty": tr["qty"], "price": tr.get("avg_price"),
                        "sleeve": "intraday", "commission": tr.get("commission"), "id": tr.get("id")})
    dly = _daily_parsed(date) or {}
    for f in dly.get("fills") or []:
        if f.get("symbol") == symbol:
            qty = f.get("qty") if f.get("qty") is not None else f.get("filled")
            if qty:
                out.append({"t": et_minute_iso(parse_ts(f.get("ts"))), "qty": qty, "price": f.get("avg_price"),
                            "sleeve": "daily", "commission": None, "id": None})
    return sorted([m for m in out if m["t"]], key=lambda m: m["t"])


def _fetch_chart(symbol: str, date: str, source: str) -> dict:
    today = today_et()
    bars: list[dict] = []
    used = None
    err = None
    try:
        if date == today and source in ("auto", "yahoo"):
            bars, used = _yf_bars(symbol, "1d", date), "yahoo"
        elif source == "yahoo":
            bars, used = _yf_bars(symbol, "7d", date), "yahoo"
        else:
            order = ["ibkr_parquet", "alpaca_parquet", "yahoo"] if source == "auto" else [source]
            for s in order:
                try:
                    if s == "ibkr_parquet":
                        bars = _store_bars_ibkr(symbol, date)
                    elif s == "alpaca_parquet":
                        bars = _store_bars_alpaca(symbol, date)
                    elif s == "yahoo":
                        bars = _yf_bars(symbol, "7d", date)
                except Exception as e:  # noqa: BLE001
                    err = redact(f"{s}: {type(e).__name__}: {e}")[:200]
                    bars = []
                if bars:
                    used = s
                    break
        if not bars:
            err = err or f"no minute source for {symbol} on {date}"
    except Exception as e:  # noqa: BLE001
        err = redact(f"{type(e).__name__}: {e}")[:200]
    try:
        trades = _trade_markers(symbol, date)
    except Exception as e:  # noqa: BLE001
        trades = []
        err = err or redact(f"markers: {e}")[:200]
    return {"symbol": symbol, "date": date, "bars": bars, "trades": trades, "source_used": used if bars else None,
            "pending": False, "retry_in": None, "last_bar_t": bars[-1]["t"] if bars else None, "as_of": iso_utc(),
            "error": err if not bars else None}


def _chart_job(key: tuple) -> None:
    symbol, date, source = key
    try:
        data = _fetch_chart(symbol, date, source)
    except Exception as e:  # noqa: BLE001
        data = {"symbol": symbol, "date": date, "bars": [], "trades": [], "source_used": None, "pending": False, "retry_in": None,
                "last_bar_t": None, "as_of": iso_utc(), "error": redact(f"{type(e).__name__}: {e}")[:200]}
    with _CHARTS_LOCK:
        _CHARTS[key] = {"data": data, "fetched_at": time.monotonic(), "inflight": False}


def _enqueue_chart(key: tuple) -> None:
    global _EXECUTOR
    with _CHARTS_LOCK:
        ent = _CHARTS.get(key)
        if ent and ent.get("inflight"):
            return
        _CHARTS[key] = {"data": ent["data"] if ent else None, "fetched_at": ent["fetched_at"] if ent else 0.0, "inflight": True}
        _WATCH[key] = None
        _WATCH.move_to_end(key)
        while len(_WATCH) > 5:
            _WATCH.popitem(last=False)
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="quotes")
        ex = _EXECUTOR
    try:
        ex.submit(_chart_job, key)
    except Exception as e:  # noqa: BLE001
        with _CHARTS_LOCK:
            if key in _CHARTS:
                _CHARTS[key]["inflight"] = False
        log.warning("chart enqueue failed: %s", e)


def _quotes_worker(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            today = today_et()
            with _CHARTS_LOCK:
                keys = list(_WATCH.keys())
                stale = [k for k in keys if k[1] == today and not _CHARTS.get(k, {}).get("inflight")
                         and time.monotonic() - _CHARTS.get(k, {}).get("fetched_at", 0.0) >= 55]
                # drop cached past-date charts nobody watches any more (memory bound)
                for k in list(_CHARTS):
                    if k not in _WATCH and not _CHARTS[k].get("inflight"):
                        _CHARTS.pop(k, None)
            for k in stale:
                _enqueue_chart(k)
            CACHE.set_ok("quotes", {"watch": [list(k) for k in keys], "yahoo": dict(_YAHOO)})
        except Exception as e:  # noqa: BLE001
            CACHE.set_error("quotes", f"{type(e).__name__}: {e}")
        finally:
            CACHE.heartbeat("quotes")
        stop.wait(PERIODS["quotes"])


# ----------------------------------------------------------------------------- lifecycle
def start_background() -> dict:
    """Start the five collector threads once; idempotent. Returns which threads are alive."""
    global _STARTED
    with _START_LOCK:
        if not _STARTED:
            STOP.clear()
            for name, fn in (("ib", _ib_worker), ("files", _files_worker), ("system", _sys_worker),
                             ("data", _data_worker), ("quotes", _quotes_worker)):
                old = _THREADS.get(name)
                if old is not None and old.is_alive():
                    continue                      # still winding down from a stop(): it sees STOP cleared and keeps going
                t = threading.Thread(target=fn, args=(STOP,), name=f"dash-{name}", daemon=True)
                t.start()
                _THREADS[name] = t
            _STARTED = True
            log.info("background collectors started: %s", ", ".join(_THREADS))
        return {"started": True, "threads": {n: t.is_alive() for n, t in _THREADS.items()}}


def stop_background(timeout: float = 5.0) -> None:
    global _STARTED, _EXECUTOR
    STOP.set()
    for t in _THREADS.values():
        try:
            t.join(timeout)
        except Exception:  # noqa: BLE001
            pass
    ex = _EXECUTOR
    if ex is not None:
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except Exception:  # noqa: BLE001
            pass
    _EXECUTOR = None
    _STARTED = False


def threads_alive() -> dict:
    return {n: t.is_alive() for n, t in _THREADS.items()}


# ----------------------------------------------------------------------------- assembler helpers
def _endpoint(contract: dict):
    """Never raise: on failure return the contract keys with null/empty values plus `error`."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            try:
                out = fn(*a, **kw)
                if not isinstance(out, dict):
                    raise TypeError(f"{fn.__name__} returned {type(out).__name__}")
            except Exception as e:  # noqa: BLE001
                log.debug("%s failed", fn.__name__, exc_info=True)
                out = copy.deepcopy(contract)
                out["error"] = redact(f"{type(e).__name__}: {e}")[:300]
            out.setdefault("as_of", None)
            out.setdefault("error", None)
            out["server_now"] = iso_utc()
            return sanitize(out)
        return wrapper
    return deco


def _clamp_int(v, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)
    except Exception:  # noqa: BLE001
        return default
    return max(lo, min(hi, n))


def _valid_date(d) -> str | None:
    if d is None or d == "":
        return today_et()
    d = str(d).strip()
    if not DATE_RE.match(d):
        return None
    try:
        dt.date.fromisoformat(d)
    except ValueError:
        return None
    return d


def _valid_symbol(s) -> str | None:
    s = str(s or "").strip().upper()
    return s if SYMBOL_RE.match(s) else None


def _et_mins(now: dt.datetime | None = None) -> tuple[int, bool, str]:
    e = (now or utcnow()).astimezone(ET)
    return e.hour * 60 + e.minute, e.weekday() < 5, e.date().isoformat()


def _in_order_window(mins: int) -> bool:
    return SLEEVE_START_MIN <= mins <= EXIT_MIN or DAILY_WINDOW[0] <= mins <= DAILY_WINDOW[1]


def _compose_account() -> dict:
    e = CACHE.get("ibkr")
    d = (e.last_good if e else None) or {}
    st = CACHE.data("ib_state") or dict(_IB_STATE_DEFAULT)
    connected = bool(st.get("connected"))
    summary = d.get("summary") or {}
    nav = summary.get("NetLiquidation")
    book_w = CACHE.data("book") or {}
    book = book_w.get("data") if isinstance(book_w.get("data"), dict) else None
    today = today_et()
    book_ok = bool(book) and book.get("date") == today and book.get("mode") == "live"
    daily_fills_sign = {}
    if not book_ok:
        pass
    positions = []
    for p in d.get("positions") or []:
        q = dict(p)
        q["weight"] = (q["market_value"] / nav) if (nav and q.get("market_value") is not None) else None
        bq = None
        if q.get("sleeve") == "intraday" and book_ok:
            b = _i((book.get("pos") or {}).get(q["symbol"], 0)) or 0
            if b != (q.get("shares") or 0):
                bq = b
        q["book_qty"] = bq
        q.pop("realized_pnl", None)
        positions.append(q)
    open_orders = [{k: v for k, v in o.items() if k != "sleeve"} for o in d.get("open_orders") or []]
    fills = [{k: v for k, v in f.items() if k in ("ts", "symbol", "side", "qty", "price", "order_ref", "exec_id", "commission", "sleeve")}
             for f in d.get("fills") or []]
    err = e.error if e else None
    if e is None:
        err = "IB collector not started yet"
    return {"as_of": (e.last_good_at if e else None) or st.get("last_good_at"), "gateway_connected": connected,
            "account_id": d.get("account_id") or st.get("account_id"), "nav": nav, "cash": summary.get("TotalCashValue"),
            "buying_power": summary.get("BuyingPower"), "gross_position_value": summary.get("GrossPositionValue"),
            "unrealized_pnl": summary.get("UnrealizedPnL"), "realized_pnl": summary.get("RealizedPnL"),
            "positions": positions, "open_orders": open_orders, "fills": fills, "available_funds": summary.get("AvailableFunds"),
            "warnings": list(d.get("warnings") or []), "last_good_at": st.get("last_good_at") or (e.last_good_at if e else None),
            "reconnects": st.get("reconnects"), "error": err, "_state": st, "_realized_by_symbol": d.get("realized_by_symbol") or {}}


# ----------------------------------------------------------------------------- integrity (5.9)
_INTEGRITY_SINCE: dict[str, str] = {}
_INTEGRITY_LOCK = threading.Lock()
_SEV_RANK = {"red": 0, "amber": 1, "grey": 2}


def _integrity(acct: dict, intr: dict, dailyf: dict, gates: dict, tasks: list, runs: dict, alerts: dict, gwlog: dict,
               last_run: dict | None, now: dt.datetime) -> dict:
    items: list[dict] = []
    evaluated = 0
    mins, weekday, today = _et_mins(now)

    def add(code, sev, msg, source, key=None):
        msg = redact(str(msg))[:300]
        items.append({"code": code, "severity": sev, "message": msg, "source": source, "_key": key or f"{code}|{msg[:80]}"})

    positions = acct.get("positions") or []
    pos_by_sym = {p["symbol"]: p for p in positions}
    connected = bool(acct.get("gateway_connected"))
    nav = acct.get("nav")
    st = acct.get("_state") or {}
    book_w = CACHE.data("book") or {}
    book = book_w.get("data") if isinstance(book_w.get("data"), dict) else None
    book_live_today = bool(book) and book.get("date") == today and book.get("mode") == "live"
    running = intr.get("state") == "running"
    dtoday = (dailyf.get("today") or {})
    lep = dtoday.get("last_executed_plan")
    start_cfg = (intr.get("config") or {}).get("start") or {}

    def rule(fn):
        nonlocal evaluated
        evaluated += 1
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            add("R?", "grey", f"integrity rule {fn.__name__} failed: {type(e).__name__}: {e}", "dashboard")

    def r1():
        if book_live_today and connected:
            ib_intr = {p["symbol"]: (p.get("shares") or 0) for p in positions if p.get("sleeve") == "intraday"}
            for sym in sorted(set(book.get("pos") or {}) | set(ib_intr)):
                b, i = _i((book.get("pos") or {}).get(sym, 0)) or 0, ib_intr.get(sym, 0)
                if b != i:
                    add("R1", "red" if running else "amber", f"{sym}: intraday book {b} vs IB {i} shares", "book/ibkr", f"R1|{sym}")
        if weekday and mins > EXIT_MIN and not running and connected:
            for p in positions:
                if p.get("sleeve") == "intraday" and p.get("shares"):
                    add("R1", "red", f"STRAGGLER {p['symbol']} {p['shares']} sh still held after 15:42 ET", "ibkr", f"R1S|{p['symbol']}")

    def r2():
        if not lep or not nav or not connected:
            return
        targets = {k: _f(v) for k, v in (lep.get("targets") or {}).items()}
        weights = {p["symbol"]: (p.get("weight") or 0.0) for p in positions if p.get("sleeve") == "daily" and p.get("shares")}
        for sym in sorted(set(targets) | set(weights)):
            t, w = targets.get(sym), weights.get(sym)
            if t is None or t == 0:
                if w:
                    add("R2", "amber", f"{sym} held ({w:+.2f} of NAV) but not in the last executed plan", "plan/ibkr", f"R2|{sym}")
            elif w is None:
                add("R2", "amber", f"{sym} targeted ({t:.2f}) but not held", "plan/ibkr", f"R2|{sym}")
            elif abs(t - w) > 0.05:
                add("R2", "amber", f"{sym} weight {w:.2f} vs target {t:.2f} ({(w - t) * 100:+.1f} pt)", "plan/ibkr", f"R2|{sym}")

    def r3():
        for p in positions:
            if p.get("sleeve") == "other" and p.get("shares"):
                add("R3", "red", f"FOREIGN {p['symbol']} {p['shares']} sh in neither universe", "ibkr", f"R3|{p['symbol']}")

    def r4():
        refs = {"intraday start": start_cfg.get("nav") if intr.get("date") == today else None,
                "last executed plan": (lep or {}).get("net_liq")}
        if nav:
            for name, v in refs.items():
                if v and abs(v - nav) / nav > 0.05:
                    add("R4", "amber", f"NAV {nav:,.0f} (IB) vs {v:,.0f} ({name}): {abs(v - nav) / nav * 100:.1f}% gap", "ibkr/logs", f"R4|{name}")
        mock_n = dtoday.get("mock_n") or 0
        if mock_n:
            add("R4", "grey", f"{mock_n} mock plan(s) today (net_liq == 100000.0)", "daily log", "R4|mock")

    def r5():
        if not (book_live_today and connected and intr.get("pnl_today") is not None):
            return
        unpriced, mv = [], 0.0
        for sym, sh in (book.get("pos") or {}).items():
            p = pos_by_sym.get(sym)
            if p and p.get("price"):
                mv += (_f(sh) or 0.0) * p["price"]
            elif _f(sh):
                unpriced.append(sym)
        if unpriced:
            add("R5", "grey", f"P&L cross-check partial: unpriced {', '.join(unpriced)}", "book/ibkr", "R5|unpriced")
            return
        costs = _f(book.get("costs")) or 0.0
        book_pnl = (_f(book.get("closed")) or 0.0) + sum((_f(v) or 0.0) for v in (book.get("cost") or {}).values()) + mv
        log_pnl = intr["pnl_today"]
        thr = max(500.0, 0.001 * nav) if nav else 500.0
        d1 = min(abs(book_pnl - log_pnl), abs(book_pnl - costs - log_pnl), abs(book_pnl + costs - log_pnl))
        if d1 > thr:
            add("R5", "amber", f"intraday P&L: book {book_pnl:+,.0f} vs log {log_pnl:+,.0f} (diff {d1:,.0f} > {thr:,.0f})", "book/log", "R5|book")
        rb = acct.get("_realized_by_symbol") or {}
        ib_pnl, have = 0.0, False
        for p in positions:
            if p.get("sleeve") == "intraday":
                have = True
                ib_pnl += (p.get("unrealized_pnl") or 0.0) + (rb.get(p["symbol"]) or 0.0)
        if have:
            d2 = min(abs(ib_pnl - log_pnl), abs(ib_pnl - costs - log_pnl), abs(ib_pnl + costs - log_pnl))
            if d2 > thr:
                add("R5", "amber", f"intraday P&L: IB {ib_pnl:+,.0f} vs log {log_pnl:+,.0f} (diff {d2:,.0f} > {thr:,.0f}; IB marks delayed)", "ibkr/log", "R5|ib")

    def r6():
        s0 = parse_ts(intr.get("session_start_ts")) if intr.get("date") == today else None
        if not s0 or not connected:
            return
        # IB reports one Fill per execution (partial prints), the log one fill per order: compare
        # distinct IB order ids against the log's per-order fills.
        raw_fills = (CACHE.data("ibkr") or {}).get("fills") or []
        ib_orders = {f.get("order_id") for f in raw_fills if f.get("order_ref") == "INTRADAY" and f.get("order_id") is not None
                     and parse_ts(f.get("ts")) and parse_ts(f["ts"]) >= s0}
        ib_n = len(ib_orders)
        trades = intr.get("trades") or []
        ids = {t.get("id") for t in trades if t.get("id") is not None}
        log_n = len(ids) if ids else len(trades)
        if log_n < ib_n:
            add("R6", "red", f"log fills {log_n} < IB filled orders {ib_n} since session start", "log/ibkr", "R6")
        elif ib_n < log_n:
            add("R6", "grey", f"IB filled orders {ib_n} < log fills {log_n} (IB coverage of other client ids is partial)", "log/ibkr", "R6")

    def r7():
        if connected and not _in_order_window(mins):
            n = len(acct.get("open_orders") or [])
            if n:
                syms = ", ".join(str(o.get("symbol")) for o in (acct.get("open_orders") or [])[:6])
                add("R7", "amber", f"{n} open order(s) outside 09:25-15:42 / 15:44-15:55 ET: {syms}", "ibkr", "R7")

    def r8():
        if running and (intr.get("config") or {}).get("drift"):
            add("R8", "red", "CONFIG DRIFT: launch params differ from live/intraday_config.json while running", "log/config", "R8")

    def r9():
        if intr.get("date") != today:
            return
        ex = (intr.get("events_summary") or {}).get("excluded") or {}
        if ex.get("replay_decisions") or ex.get("foreign_date_snapshots"):
            add("R9", "amber", f"live log contamination: {ex.get('replay_decisions', 0)} replay decisions, {ex.get('foreign_date_snapshots', 0)} foreign-date snapshots", "log", "R9")

    def r10():
        task = next((t for t in tasks if t.get("name") == "Quant Intraday Sleeve"), None)
        if weekday and SESSION_OPEN_MIN <= mins <= EXIT_MIN:
            reasons = []
            if not start_cfg or intr.get("date") != today or intr.get("mode") != "live":
                reasons.append("no live start today")
            else:
                age = age_seconds(intr.get("last_event_ts"), now)
                if age is not None and age > STALE_S:
                    reasons.append(f"last event {age:.0f}s ago")
            if task and task.get("state") != "Running":
                reasons.append(f"task 'Quant Intraday Sleeve' is {task.get('state')}")
            if reasons and (start_cfg or task) and intr.get("state") != "ended":
                add("R10", "red", "intraday sleeve liveness: " + "; ".join(reasons), "log/tasks", "R10|live")
        if weekday and mins > EXIT_MIN and start_cfg and intr.get("date") == today and not intr.get("has_end") \
                and intr.get("state") == "ended":
            add("R10", "amber", "intraday session has no end event after 15:42 ET", "log", "R10|noend")
        if weekday and mins > DAILY_DEADLINE_MIN and not lep:
            add("R10", "red", "no executed daily plan by 15:47 ET today", "daily log", "R10|daily")
        for w in dtoday.get("warnings") or []:
            if w.get("event") in ("refused", "flatten", "connect_failed"):
                add("R10", "red", f"daily runner {w['event']} x{w.get('count')}: {w.get('detail') or ''}".strip(), "daily log", f"R10|{w['event']}|{w.get('detail')}")

    def r11():
        n = alerts.get("undelivered") or 0
        if n:
            add("R11", "amber", f"{n} alert(s) not delivered today: {'; '.join(alerts.get('errors') or [])[:200]}", "alerts log", "R11")

    def r12():
        if intr.get("date") != today:
            return
        delay = (intr.get("events_summary") or {}).get("feed_delay_minutes")
        if delay is not None and delay > 3:
            add("R12", "amber", f"feed delay {delay:.0f} min (IB delayed; yahoo 1m fallback)", "log", "R12|delay")
        if intr.get("feed_error_n"):
            add("R12", "amber", f"{intr['feed_error_n']} feed_error event(s) this session", "log", "R12|err")

    def r13():
        if intr.get("date") != today:
            return
        if intr.get("loss_limit_hit"):
            add("R13", "red", "LOSS LIMIT hit: intraday sleeve flattened and stopped", "log", "R13|hit")
            return
        pnl, snav = intr.get("pnl_today"), start_cfg.get("nav")
        if pnl is not None and snav:
            frac = pnl / snav
            if frac <= -(DAILY_LOSS_LIMIT - 0.005):
                add("R13", "amber", f"intraday P&L {frac * 100:+.2f}% of start NAV, within 0.5 pt of the {-DAILY_LOSS_LIMIT * 100:.1f}% loss limit", "log", "R13|near")

    def r14():
        for t in tasks:
            name = t.get("name")
            res = t.get("last_result")
            try:
                code = int(res) if res is not None else None
            except Exception:  # noqa: BLE001
                code = None
            if code is not None and code not in (0, 267009):
                add("R14", "amber", f"task '{name}' last result {t.get('last_result_text') or code}", "tasks", f"R14|{name}|res")
            if t.get("state") not in ("Disabled", "Running") and not t.get("next_run"):
                add("R14", "amber", f"task '{name}' ({t.get('state')}) has no next run time", "tasks", f"R14|{name}|next")

    def r15():
        ri = (runs.get("research_iterate") or [None])[0]
        if ri:
            s = str(ri.get("status") or "").lower()
            cs = str(ri.get("completionStatus") or "").lower()
            if s in ("error", "timeout", "failed") or cs in ("error", "timeout", "failed"):
                add("R15", "amber", f"research-iterate last run {s or cs}: {ri.get('error') or ''}".strip(), "openclaw", "R15|status")
            age = age_seconds(ri.get("ts"), now)
            if age is not None and age > 3 * 3600:
                add("R15", "amber", f"research-iterate last run {age / 3600:.1f} h ago", "openclaw", "R15|age")
        n = gwlog.get("stalled_last_hour") or 0
        if n:
            add("R15", "amber", f"{n} 'stalled session' line(s) in the gateway log in the last hour", "gateway log", "R15|stalled")

    def r16():
        for name, period in PERIODS.items():
            hb = CACHE.heartbeat_of(name)
            age = age_seconds(hb, now)
            if hb is None or (age is not None and age > 3 * period):
                add("R16", "red", f"collector '{name}' heartbeat {'missing' if hb is None else f'{age:.0f}s old'} (period {period}s)", "dashboard", f"R16|hb|{name}")
        skew = st.get("skew_s")
        if skew is not None and abs(skew) > 5:
            add("R16", "amber", f"IB clock skew {skew:+.1f}s", "ibkr", "R16|skew")
        if connected:
            la = st.get("last_append_at") or st.get("connected_since")
            age = age_seconds(la, now)
            if age is not None and age > 180:
                add("R16", "amber", f"nav_history append {age:.0f}s ago while connected", "dashboard", "R16|nav")

    def r17():
        if isinstance(last_run, dict) and last_run.get("dry_run"):
            add("R17", "grey", "last_run.json says the daily runner's last run was a dry run", "last_run.json", "R17")

    def r18():
        aid = acct.get("account_id")
        if aid and not str(aid).startswith("DU"):
            add("R18", "red", f"account {aid} is not a paper account (id does not start with DU)", "ibkr", "R18")

    for fn in (r1, r2, r3, r4, r5, r6, r7, r8, r9, r10, r11, r12, r13, r14, r15, r16, r17, r18):
        rule(fn)

    now_iso = iso_utc(now)
    with _INTEGRITY_LOCK:
        active = {it["_key"] for it in items}
        for k in list(_INTEGRITY_SINCE):
            if k not in active:
                _INTEGRITY_SINCE.pop(k, None)
        for it in items:
            it["since"] = _INTEGRITY_SINCE.setdefault(it["_key"], now_iso)
    out = [{"code": it["code"], "severity": it["severity"], "message": it["message"], "since": it["since"], "source": it["source"]}
           for it in items]
    out.sort(key=lambda it: (_SEV_RANK.get(it["severity"], 3), it["since"]), reverse=False)
    out.sort(key=lambda it: it["since"], reverse=True)
    out.sort(key=lambda it: _SEV_RANK.get(it["severity"], 3))
    return {"evaluated": evaluated, "items": out}


# ----------------------------------------------------------------------------- public assemblers
_C_STATUS = {"as_of": None, "gateway_connected": None, "account_id": None, "feed": None,
             "intraday": {"running": None, "mode": None, "equity_frac": None, "strategy": None, "last_event_ts": None,
                          "pnl_today": None, "trades_today": None, "positions_n": None, "loss_limit_hit": None, "halted": None, "state": None},
             "daily": {"last_plan_ts": None, "last_fills_n": None, "next_run": None, "last_plan_kind": None},
             "loop": {"research_iterate_status": None, "last_run_ts": None, "next_run": None},
             "gates": {"approved_paper": None, "halt": None, "halt_intraday": None}, "tasks": [],
             "sources": {k: {"ok": None, "detail": None} for k in ("ibkr", "yahoo", "alpaca", "theta", "fmp")},
             "integrity": {"evaluated": None, "items": []},
             "sections": {"ibkr": {"as_of": None, "error": None}, "files": {"as_of": None, "error": None}, "system": {"as_of": None, "error": None}},
             "heartbeats": {"ib": None, "files": None, "system": None, "data": None, "quotes": None}, "error": None}


@_endpoint(_C_STATUS)
def status() -> dict:
    now = utcnow()
    acct = _compose_account()
    st = acct.get("_state") or {}
    today = today_et()
    intr = _intraday_parsed(today) or {}
    dailyf = CACHE.data("files.daily") or {}
    dtoday = dailyf.get("today")
    if dtoday is None:                          # before T-FILES has run: today's file is tiny
        dtoday = _daily_parsed(today) or {}
        dailyf = dict(dailyf, today=dtoday)
    gates = CACHE.data("gates") or _gates()
    tasks = (CACHE.data("sys.tasks") or {}).get("tasks") or []
    runs = CACHE.data("sys.runs") or {}
    oc = (CACHE.data("sys.openclaw") or {}).get("automations") or []
    alerts = CACHE.data("files.alerts") or {}
    gwlog = CACHE.data("sys.gateway_log") or {}
    last_run = (CACHE.data("last_run") or {}).get("data")
    theta = CACHE.data("sys.theta") or {}
    scan = CACHE.data("data.scan") or {}
    kp = scan.get("keys_present") or keys_present()
    yahoo = dict(_YAHOO)                        # live state, not the 60 s quotes snapshot

    cfg = intr.get("config") or {}
    start_cfg = cfg.get("start") or {}
    state = intr.get("state") or ("off" if CACHE.get("files.intraday") else None)
    intraday = {"running": state == "running" if state else None, "mode": intr.get("mode"),
                "equity_frac": start_cfg.get("equity_frac") if start_cfg else ((cfg.get("deployed") or {}).get("equity_frac") if cfg.get("deployed") else None),
                "strategy": start_cfg.get("strategy") if start_cfg else ((cfg.get("deployed") or {}).get("strategy") if cfg.get("deployed") else None),
                "last_event_ts": intr.get("last_event_ts"), "pnl_today": intr.get("pnl_today"), "trades_today": intr.get("trades_today"),
                "positions_n": len(intr.get("positions_now") or {}) if intr else None, "loss_limit_hit": intr.get("loss_limit_hit"),
                "halted": intr.get("halted") if intr else (bool(gates.get("halt")) or bool(gates.get("halt_intraday"))),
                "state": state, "state_detail": intr.get("state_detail")}
    task_by = {t.get("name"): t for t in tasks}
    lp = dtoday.get("last_plan") or {}
    daily = {"last_plan_ts": lp.get("ts"), "last_fills_n": dtoday.get("last_fills_n") if dtoday else None,
             "next_run": (task_by.get("Quant Paper Rebalance") or {}).get("next_run"), "last_plan_kind": lp.get("kind")}
    ri = (runs.get("research_iterate") or [None])[0]
    next_run = (ri or {}).get("next_run")
    if not next_run:
        row = next((r for r in oc if r.get("name") == "research-iterate"), None)
        next_run = row.get("next") if row else None
    loop = {"research_iterate_status": (ri or {}).get("status") or ("unknown" if CACHE.get("sys.runs") else None),
            "last_run_ts": (ri or {}).get("ts"), "next_run": next_run}
    yahoo_age = age_seconds(yahoo.get("last_ok_at"), now)
    if not yahoo.get("tested"):
        y_ok, y_detail = True, "untested"
    else:
        y_ok = yahoo_age is not None and yahoo_age < 600
        y_detail = f"last 1m fetch ok {yahoo_age:.0f}s ago" if yahoo_age is not None else f"last fetch failed: {yahoo.get('last_error')}"
    alp_n = len(((scan.get("stores") or {}).get("alpaca_minute") or {}).get("symbols") or [])
    sources = {"ibkr": {"ok": bool(st.get("connected")), "detail": (f"{acct.get('account_id')} clientId {IB_CLIENT_ID}" if st.get("connected")
                                                                    else (st.get("last_error") or "not connected"))},
               "yahoo": {"ok": y_ok, "detail": y_detail},
               "alpaca": {"ok": bool(kp.get("ALPACA")) and alp_n > 0, "detail": f"key {'present' if kp.get('ALPACA') else 'missing'}; {alp_n} symbols in data/minute_alpaca"},
               "theta": {"ok": bool(theta.get("alive")), "detail": "terminal alive" if theta.get("alive") else "terminal down"},
               "fmp": {"ok": bool(kp.get("FMP")), "detail": f"earnings.json generated {(scan.get('events') or {}).get('generated')}"}}
    tasks_out = [{"name": t.get("name"), "state": t.get("state"), "next_run": t.get("next_run"), "last_result": t.get("last_result")} for t in tasks]
    integrity = _integrity(acct, intr, dailyf, gates, tasks, runs, alerts, gwlog, last_run, now)
    sections = {"ibkr": {"as_of": acct.get("as_of"), "error": acct.get("error")}, "files": CACHE.section("files"), "system": CACHE.section("system")}
    heartbeats = {k: CACHE.heartbeat_of(k) for k in ("ib", "files", "system", "data", "quotes")}
    as_of = _min_iso(acct.get("as_of"), CACHE.meta("files")["as_of"], CACHE.meta("system")["as_of"])
    return {"as_of": as_of, "gateway_connected": bool(st.get("connected")), "account_id": acct.get("account_id"),
            "feed": intr.get("feed") or "unknown", "intraday": intraday, "daily": daily, "loop": loop, "gates": gates,
            "tasks": tasks_out, "sources": sources, "integrity": integrity, "sections": sections, "heartbeats": heartbeats,
            "error": None}


_C_ACCOUNT = {"as_of": None, "gateway_connected": None, "nav": None, "cash": None, "buying_power": None, "gross_position_value": None,
              "unrealized_pnl": None, "realized_pnl": None, "positions": [], "open_orders": [], "fills": [], "available_funds": None,
              "warnings": [], "last_good_at": None, "reconnects": None, "error": None}


@_endpoint(_C_ACCOUNT)
def account() -> dict:
    a = _compose_account()
    a.pop("_state", None)
    a.pop("_realized_by_symbol", None)
    return a


_C_NAV = {"points": [], "days": None, "sources_n": {"dashboard": None, "plan": None, "intraday_start": None}, "mock_excluded": None,
          "day_baseline": None, "as_of": None, "error": None}


@_endpoint(_C_NAV)
def nav_history(days=30) -> dict:
    n = _clamp_int(days, 1, 400, 30)
    now = utcnow()
    cutoff = now - dt.timedelta(days=n)
    pts: list[dict] = []
    navf = CACHE.data("nav_file") or {}
    for p in navf.get("points") or []:
        pts.append(dict(p))
    mock = 0
    dailyf = CACHE.data("files.daily") or {}
    for d, parsed in (dailyf.get("by_date") or {}).items():
        for pl in parsed.get("plans") or []:
            if pl.get("kind") == "mock":
                mock += 1
                continue
            t = parse_ts(pl.get("ts"))
            if t and pl.get("net_liq"):
                pts.append({"ts": iso_utc(t), "nav": pl["net_liq"], "cash": None, "gross": None, "source": "plan"})
    for s in CACHE.data("files.intraday_starts") or []:
        t = parse_ts(s.get("ts"))
        if t and s.get("nav"):
            pts.append({"ts": iso_utc(t), "nav": s["nav"], "cash": None, "gross": None, "source": "intraday_start"})
    pts = [p for p in pts if parse_ts(p["ts"]) and parse_ts(p["ts"]) >= cutoff]
    pts.sort(key=lambda p: p["ts"])
    by_min: "OrderedDict[str, dict]" = OrderedDict()
    for p in pts:
        k = p["ts"][:16]
        cur = by_min.get(k)
        if cur is None or (p["source"] == "dashboard" and cur["source"] != "dashboard") or (cur["source"] != "dashboard" and p["source"] != "dashboard"):
            by_min[k] = p
    pts = list(by_min.values())
    if len(pts) > 2000:
        bucket = 60 if n <= 2 else (900 if n <= 30 else 3600)
        keep: "OrderedDict[str, dict]" = OrderedDict()
        first_of_day: dict[str, dict] = {}
        last_of_day: dict[str, dict] = {}
        for p in pts:
            t = parse_ts(p["ts"])
            day = et_date_of(t)
            first_of_day.setdefault(day, p)
            last_of_day[day] = p
            keep[str(int(t.timestamp()) // bucket)] = p
        chosen = {id(p) for p in keep.values()} | {id(p) for p in first_of_day.values()} | {id(p) for p in last_of_day.values()}
        pts = [p for p in pts if id(p) in chosen]
    today = today_et()
    todays = [p for p in pts if et_date_of(parse_ts(p["ts"])) == today]
    baseline = None
    for src in ("dashboard", "intraday_start", "plan"):
        c = next((p for p in todays if p["source"] == src), None)
        if c:
            baseline = {"ts": c["ts"], "nav": c["nav"], "source": src}
            break
    counts = Counter(p["source"] for p in pts)
    as_of = _max_iso(navf.get("last_ts"), CACHE.meta("files")["as_of"])
    return {"points": pts, "days": n, "sources_n": {"dashboard": counts.get("dashboard", 0), "plan": counts.get("plan", 0),
                                                    "intraday_start": counts.get("intraday_start", 0)},
            "mock_excluded": mock, "day_baseline": baseline, "as_of": as_of, "error": CACHE.meta("nav_file")["error"]}


_C_INTRADAY = {"date": None, "config": {"start": None, "launch_params": None, "deployed": None, "drift": None, "sleeve_equity": None},
               "events_summary": {"counts": {}, "first_ts": None, "last_ts": None, "feed_delay_minutes": None, "feed_delayed_n": None,
                                  "excluded": {"replay_decisions": None, "foreign_date_snapshots": None}, "available_dates": [], "bad_lines": None},
               "pnl_curve": [], "trades": [], "decisions_n": None, "positions_now": {}, "errors": [], "state": None, "mode": None,
               "pnl_today": None, "trades_today": None, "positions_source": None, "last_decision": None, "dead_orders": [],
               "pending_orders": [], "loss_limit_hit": None, "halted": None, "as_of": None, "error": None}
_INTRADAY_PUBLIC = ("date", "config", "events_summary", "pnl_curve", "trades", "decisions_n", "positions_now", "errors", "state",
                    "state_detail", "mode", "pnl_today", "trades_today", "positions_source", "last_decision", "dead_orders",
                    "pending_orders", "loss_limit_hit", "halted", "feed", "last_event_ts")


@_endpoint(_C_INTRADAY)
def sleeve_intraday(date=None) -> dict:
    d = _valid_date(date)
    if d is None:
        out = copy.deepcopy(_C_INTRADAY)
        out["date"] = str(date)[:32]
        out["error"] = f"invalid date {str(date)[:32]!r} (expected YYYY-MM-DD)"
        return out
    today = today_et()
    parsed = _intraday_parsed(d)
    if parsed is None:
        parsed = parse_intraday([], d, gates=CACHE.data("gates") or _gates(), available_dates=_available_intraday_dates())
    out = {k: parsed.get(k) for k in _INTRADAY_PUBLIC}
    out["as_of"] = CACHE.meta("files.intraday")["as_of"] if d == today else iso_utc()
    out["error"] = CACHE.meta("files.intraday")["error"] if d == today else None
    return out


_C_DAILY = {"date": None, "champion": None, "last_plan": None, "fills": [], "history": [], "last_executed_plan": None, "state": None,
            "warnings": [], "next_run": None, "as_of": None, "error": None}


@_endpoint(_C_DAILY)
def sleeve_daily(date=None) -> dict:
    d = _valid_date(date)
    if d is None:
        out = copy.deepcopy(_C_DAILY)
        out["date"] = str(date)[:32]
        out["error"] = f"invalid date {str(date)[:32]!r} (expected YYYY-MM-DD)"
        return out
    dailyf = CACHE.data("files.daily")
    if dailyf is None:                          # before T-FILES has run: the daily files are tiny
        history = []
        for hd in _daily_dates()[:10]:
            hp = _daily_parsed(hd)
            if hp and hp.get("exists"):
                history.append(hp["history_row"])
        dailyf = {"history": history}
    parsed = _daily_parsed(d) or parse_daily([], d)
    research = CACHE.data("research")
    champion = research.get("champion") if research else None
    if research is None:
        try:
            champion = json.loads((RESEARCH / "champion.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            champion = None
    tasks = (CACHE.data("sys.tasks") or {}).get("tasks") or []
    task = next((t for t in tasks if t.get("name") == "Quant Paper Rebalance"), None)
    return {"date": d, "champion": champion, "last_plan": parsed.get("last_plan"), "fills": parsed.get("fills") or [],
            "history": dailyf.get("history") or [], "last_executed_plan": parsed.get("last_executed_plan"),
            "state": (CACHE.data("last_run") or {}).get("data"), "warnings": parsed.get("warnings") or [],
            "next_run": task.get("next_run") if task else None, "as_of": CACHE.meta("files.daily")["as_of"],
            "error": CACHE.meta("files.daily")["error"]}


_C_SUMMARY = {"champion": None, "experiments_n": None, "last_20": [], "by_algorithm": [], "backlog_open": [], "journal_latest": [],
              "blockers_excerpt": None, "counts": {"daily": None, "intraday": None, "bad_lines": None}, "ledger_mtime": None,
              "backlog_meta": {"open_n": None, "done_n": None, "objective_excerpt": None, "preamble": None}, "blockers_headings": [],
              "champion_run_dir_exists": None, "reports": [], "as_of": None, "error": None}


@_endpoint(_C_SUMMARY)
def research_summary() -> dict:
    r = CACHE.data("research")
    if r is None:
        _research_tick()                      # first call before T-FILES ran: small local files
        r = CACHE.data("research") or {}
    rows = r.get("rows") or []
    last = []
    for row in reversed(rows[-20:]):
        stats = row.get("stats") or {}
        last.append({"ts": row.get("ts"), "algorithm": row.get("algorithm"), "tag": row.get("tag"),
                     "stats": {k: stats[k] for k in SUMMARY_STAT_NAMES if k in stats}, "track": row.get("track"),
                     "commit": row.get("commit"), "parsed": row.get("parsed")})
    backlog = r.get("backlog") or {"open": [], "meta": {}}
    blockers = r.get("blockers") or {"excerpt": "", "headings": []}
    return {"champion": r.get("champion"), "experiments_n": len(rows), "last_20": last, "by_algorithm": r.get("by_algorithm") or [],
            "backlog_open": backlog.get("open") or [], "journal_latest": (r.get("journal") or [])[:5],
            "blockers_excerpt": blockers.get("excerpt") or "", "counts": r.get("counts") or {"daily": None, "intraday": None, "bad_lines": None},
            "ledger_mtime": r.get("ledger_mtime"), "backlog_meta": backlog.get("meta") or {}, "blockers_headings": blockers.get("headings") or [],
            "champion_run_dir_exists": r.get("champion_run_dir_exists"), "reports": r.get("reports") or [],
            "as_of": CACHE.meta("research")["as_of"], "error": CACHE.meta("research")["error"]}


_C_EXPERIMENTS = {"rows": [], "total": None, "as_of": None, "error": None}


@_endpoint(_C_EXPERIMENTS)
def experiments(algorithm=None, limit=200, track=None) -> dict:
    r = CACHE.data("research")
    if r is None:
        _research_tick()
        r = CACHE.data("research") or {}
    rows = list(r.get("rows") or [])
    err = None
    if track:
        track = str(track).strip().lower()
        if track not in ("daily", "intraday"):
            err = f"invalid track {track!r} (daily|intraday)"
            rows = []
        else:
            rows = [x for x in rows if x.get("track") == track]
    if algorithm:
        a = str(algorithm).strip()
        rows = [x for x in rows if x.get("algorithm") == a or x.get("algorithm") == f"intraday/{a}"]
    lim = _clamp_int(limit, 1, 2000, 200)
    total = len(rows)
    rows = list(reversed(rows))[:lim]
    return {"rows": rows, "total": total, "as_of": CACHE.meta("research")["as_of"], "error": err or CACHE.meta("research")["error"]}


_C_STRATEGIES = {"deployed_intraday": None, "champion_daily": None, "intraday_modules": [], "daily_algorithms": [], "daily_docstrings": {},
                 "framework": {"MIN_CHANGE": None, "PER_SYMBOL_HARD_CAP": None, "GROSS_HARD_CAP": None, "DAILY_LOSS_LIMIT": None,
                               "FLATTEN_MINUTE": None, "EXIT_MINUTE": None, "SLIPPAGE_BPS": None, "UNIVERSE": [], "DAILY_SLEEVE_UNIVERSE": []},
                 "as_of": None, "error": None}


@_endpoint(_C_STRATEGIES)
def strategies() -> dict:
    s = CACHE.data("strategies")
    if s is None:
        _strategies_tick()
        s = CACHE.data("strategies") or {}
    cfg = CACHE.data("config")
    if cfg is None:
        _files_small_json()
        cfg = CACHE.data("config") or {}
    research = CACHE.data("research") or {}
    champ = research.get("champion")
    if champ is None:
        try:
            champ = json.loads((RESEARCH / "champion.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            champ = None
    return {"deployed_intraday": cfg.get("data"), "champion_daily": champ, "intraday_modules": s.get("intraday_modules") or [],
            "daily_algorithms": s.get("daily_algorithms") or [], "daily_docstrings": s.get("daily_docstrings") or {},
            "framework": _framework(), "as_of": _min_iso(CACHE.meta("strategies")["as_of"], CACHE.meta("config")["as_of"]),
            "error": CACHE.meta("strategies")["error"] or CACHE.meta("config")["error"]}


_C_DATA = {"stores": {"ibkr_minute": {"symbols": []}, "alpaca_minute": {"symbols": []}, "lean_daily_n": None, "lean_minute_symbols": []},
           "events": {"generated": None, "symbols_n": None}, "theta": {"alive": None, "plan": None},
           "keys_present": {k: None for k in ("ALPACA", "THETADATA", "FMP", "POLYGON", "FINNHUB", "NASDAQ", "TELEGRAM")},
           "scan_as_of": None, "as_of": None, "error": None}


@_endpoint(_C_DATA)
def data() -> dict:
    scan = CACHE.data("data.scan") or {}
    theta = CACHE.data("sys.theta") or {}
    stores = scan.get("stores") or copy.deepcopy(_C_DATA["stores"])
    return {"stores": stores, "events": scan.get("events") or {"generated": None, "symbols_n": None},
            "theta": {"alive": theta.get("alive"), "plan": THETA_PLAN},
            "keys_present": scan.get("keys_present") or keys_present(), "scan_as_of": scan.get("scan_as_of"),
            "as_of": _min_iso(CACHE.meta("data.scan")["as_of"], CACHE.meta("sys.theta")["as_of"]) or CACHE.meta("data.scan")["as_of"],
            "error": CACHE.meta("data.scan")["error"]}


_C_CHART = {"symbol": None, "date": None, "bars": [], "trades": [], "source_used": None, "pending": False, "retry_in": None,
            "last_bar_t": None, "as_of": None, "error": None}
CHART_SOURCES = ("auto", "yahoo", "ibkr_parquet", "alpaca_parquet")


@_endpoint(_C_CHART)
def chart(symbol=None, date=None, source="auto") -> dict:
    sym = _valid_symbol(symbol)
    d = _valid_date(date)
    src = str(source or "auto").strip().lower()
    out = copy.deepcopy(_C_CHART)
    out["symbol"] = sym or str(symbol or "")[:32]
    out["date"] = d or str(date or "")[:32]
    if sym is None:
        out["error"] = f"invalid symbol {str(symbol)[:32]!r}"
        return out
    if d is None:
        out["error"] = f"invalid date {str(date)[:32]!r} (expected YYYY-MM-DD)"
        return out
    if src not in CHART_SOURCES:
        out["error"] = f"invalid source {src[:32]!r} (auto|yahoo|ibkr_parquet|alpaca_parquet)"
        return out
    key = (sym, d, src)
    today = today_et()
    with _CHARTS_LOCK:
        ent = _CHARTS.get(key)
        cached = ent.get("data") if ent else None
        inflight = bool(ent and ent.get("inflight"))
        _WATCH[key] = None
        _WATCH.move_to_end(key)
        while len(_WATCH) > 5:
            _WATCH.popitem(last=False)
    if cached is not None:
        if d == today and not inflight and ent and time.monotonic() - ent.get("fetched_at", 0) >= 60:
            _enqueue_chart(key)
        return dict(cached)
    if not inflight:
        _enqueue_chart(key)
    out["pending"] = True
    out["retry_in"] = 3
    try:
        out["trades"] = _trade_markers(sym, d)
    except Exception:  # noqa: BLE001
        out["trades"] = []
    out["as_of"] = iso_utc()
    return out


_C_SYSTEM = {"automations": [], "last_runs": {"research_iterate": [], "research_review": []}, "git_log": [], "gateway_log_tail": [],
             "scheduled_tasks": [], "sections": {k: {"as_of": None, "error": None} for k in ("openclaw", "runs", "tasks", "git", "gateway_log")},
             "as_of": None, "error": None}


@_endpoint(_C_SYSTEM)
def system() -> dict:
    oc = CACHE.data("sys.openclaw") or {}
    runs = CACHE.data("sys.runs") or {}
    git = CACHE.data("sys.git") or {}
    tasks = CACHE.data("sys.tasks") or {}
    gl = CACHE.data("sys.gateway_log") or {}
    runs_err = CACHE.meta("sys.runs")["error"]
    if not runs_err and runs.get("_errors"):
        runs_err = "; ".join(runs["_errors"])[:300]
    sections = {"openclaw": CACHE.section("sys.openclaw"), "runs": {"as_of": CACHE.meta("sys.runs")["as_of"], "error": runs_err},
                "tasks": CACHE.section("sys.tasks"), "git": CACHE.section("sys.git"), "gateway_log": CACHE.section("sys.gateway_log")}
    first_err = next((s["error"] for s in sections.values() if s["error"]), None)
    return {"automations": oc.get("automations") or [], "last_runs": {"research_iterate": runs.get("research_iterate") or [],
                                                                     "research_review": runs.get("research_review") or []},
            "git_log": git.get("git_log") or [], "gateway_log_tail": gl.get("lines") or [], "scheduled_tasks": tasks.get("tasks") or [],
            "sections": sections, "as_of": _min_iso(*(s["as_of"] for s in sections.values())),
            "error": None if any(s["as_of"] for s in sections.values()) else first_err}


_C_LOGS = {"lines": [], "file": None, "size": None, "mtime": None, "skipped": None, "as_of": None, "error": None}
LOG_NAMES = {"intraday": "intraday-{date}.jsonl", "daily": "{date}.jsonl", "alerts": "alerts-{date}.jsonl"}


@_endpoint(_C_LOGS)
def logs(name=None, date=None, n=200) -> dict:
    out = copy.deepcopy(_C_LOGS)
    nm = str(name or "").strip().lower()
    if nm not in LOG_NAMES:
        out["error"] = f"invalid log name {str(name)[:32]!r} (intraday|daily|alerts)"
        return out
    d = _valid_date(date)
    if d is None:
        out["error"] = f"invalid date {str(date)[:32]!r} (expected YYYY-MM-DD)"
        return out
    count = _clamp_int(n, 1, 2000, 200)
    path = LOG_DIR / LOG_NAMES[nm].format(date=d)
    jf = _jsonl(path)
    if d != today_et() or time.monotonic() - jf.last_check > 2:
        jf.refresh()
    lines = list(reversed(jf.lines))[:count]
    out.update({"lines": lines, "file": str(path), "size": jf.size if jf.exists else None, "mtime": jf.mtime, "skipped": jf.bad,
                "as_of": jf.mtime or iso_utc(), "error": None if jf.exists else f"no such log: {path.name}"})
    if nm == "alerts":
        errs = sorted({redact(str(l.get("error")))[:160] for l in jf.lines if l.get("delivered") is False and l.get("error")})
        out["summary"] = {"total": len(jf.lines), "delivered": sum(1 for l in jf.lines if l.get("delivered")), "errors": errs}
    return out


_C_OPTIONS = {"alive": None, "nearest_expiration": None, "atm_quotes": [], "message": None, "symbol": None, "spot": None, "as_of": None, "error": None}


@_endpoint(_C_OPTIONS)
def options(symbol="SPY") -> dict:
    sym = _valid_symbol(symbol or "SPY")
    out = copy.deepcopy(_C_OPTIONS)
    if sym is None:
        out["symbol"] = str(symbol)[:32]
        out["error"] = f"invalid symbol {str(symbol)[:32]!r}"
        out["message"] = out["error"]
        return out
    with _OPTIONS_LOCK:
        _OPTIONS_SYMBOL["symbol"] = sym
    cached = CACHE.data("options")
    theta = CACHE.data("sys.theta") or {}
    alive = theta.get("alive")
    if cached and cached.get("symbol") == sym:
        out.update({k: cached.get(k) for k in ("alive", "nearest_expiration", "atm_quotes", "message", "symbol", "spot")})
        out["as_of"] = CACHE.meta("options")["as_of"]
        out["error"] = CACHE.meta("options")["error"]
        return out
    out.update({"alive": alive, "symbol": sym, "atm_quotes": [],
                "message": "Theta terminal down - no quotes" if alive is False else f"fetching {sym} quotes (next refresh within 60 s)",
                "as_of": CACHE.meta("sys.theta")["as_of"]})
    return out


__all__ = ["ALLOWED_WRITE", "CACHE", "Cache", "JsonlFile", "append_nav", "redact", "sanitize", "keys_present", "parse_intraday",
           "parse_daily", "parse_backlog", "parse_journal", "parse_blockers", "status", "account", "nav_history", "sleeve_intraday",
           "sleeve_daily", "research_summary", "experiments", "strategies", "data", "chart", "system", "logs", "options",
           "start_background", "stop_background", "threads_alive", "UNIVERSE", "DAILY_SLEEVE_UNIVERSE", "IB_SYMBOL_MAP"]
