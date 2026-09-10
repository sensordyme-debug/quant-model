"""FastAPI app for the local quant dashboard (read-only, 127.0.0.1:8787).

Responsibilities are split in two files:
    sources.py - collectors, the in-memory Cache and the background threads. All data assembly
                 (IB, log parsing, research ledger, subprocesses, quotes) lives there.
    server.py  - this file: the HTTP surface only. Static files, the fixed /api/* JSON contract,
                 query validation, the "secret" path block and the never-500 error envelope.

Rules implemented here (build spec sections 0, 4 and 5.1):
- Handlers never touch IB, subprocesses, the network or data files. They call the sources.*
  functions, which only read the cache, so a request never blocks on a collector.
- Every /api/* response is HTTP 200 JSON carrying `as_of`, `server_now` and `error`. An exception
  inside an assembler becomes `error: "<Type>: <message>"` (redacted, 300 chars) with the contract
  keys present as null/empty, so the UI dims one panel instead of blanking the page. Malformed
  query input that the spec does not map to a 200-with-error result (e.g. `days=abc`) gets a 422
  JSON reply in the same envelope. /api/logs, /api/chart and /api/options answer invalid input
  with 200 + `error` because the spec's acceptance checks require exactly that.
- Any request whose URL-decoded, lowercased path or query string contains "secret" is answered
  404 before routing - belt and braces on top of sources.py never opening live/secrets.env.
- NaN/inf/numpy/pandas/Path values are sanitized to null/float/str before encoding, because
  Starlette encodes with json.dumps(allow_nan=False) and a stray NaN would otherwise be a 500.
- The collector threads are started once, in the lifespan hook (or lazily on the first request
  if the app was mounted without a lifespan, e.g. under a test client), never at import time -
  importing this module must not open an IB socket.

Run: `python scripts/dashboard.py` (launcher: dependency check, port check) or, for a bare
server, `python scripts/dashboard/server.py [--port 8787]`.
"""
from __future__ import annotations

import copy
import datetime as dt
import decimal
import importlib
import json
import logging
import math
import re
import sys
import threading
import time
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("dashboard.server")

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
REPO = HERE.parents[1]
ET = ZoneInfo("America/New_York")

HOST = "127.0.0.1"
DEFAULT_PORT = 8787

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
LOG_NAMES = ("intraday", "daily", "alerts")
CHART_SOURCES = ("auto", "yahoo", "ibkr_parquet", "alpaca_parquet")
TRACKS = ("daily", "intraday")
DEFAULT_DAYS, MAX_DAYS = 30, 400
DEFAULT_LIMIT, MAX_LIMIT = 200, 2000
DEFAULT_LOG_N, MAX_LOG_N = 200, 2000
DEFAULT_CHART_SYMBOL = "NVDA"
DEFAULT_OPTIONS_SYMBOL = "SPY"
ERROR_MAX_CHARS = 300
BLOCKED_WORD = "secret"

API_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


# --------------------------------------------------------------------------------------------
# sources module: imported once, started once, failures reported per request (never fatal)
# --------------------------------------------------------------------------------------------
sources: Any = None
_sources_error: str | None = None
_sources_retry_at = 0.0
_started = False
_start_retry_at = 0.0
_start_lock = threading.Lock()


def _import_sources() -> Any:
    """Import the sibling sources module under whichever name this file was loaded as.

    `dashboard.server` (launcher / uvicorn import string) -> `dashboard.sources`;
    `python scripts/dashboard/server.py` (no package) -> plain `sources` next to this file.
    A stub placed in sys.modules under the package name is honoured (used by the self-test).
    """
    pkg = __package__ or ""
    if pkg:
        name = f"{pkg}.sources"
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as e:
            if e.name != name:
                raise  # a dependency inside sources.py is missing: report that, do not mask it
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    return importlib.import_module("sources")


def _load_sources() -> Any:
    """Return the sources module, retrying a failed import at most once a minute."""
    global sources, _sources_error, _sources_retry_at
    if sources is not None:
        return sources
    now = time.monotonic()
    if now >= _sources_retry_at:
        _sources_retry_at = now + 60.0
        try:
            sources = _import_sources()
            _sources_error = None
            log.info("sources module loaded from %s", getattr(sources, "__file__", "?"))
            return sources
        except Exception as e:  # noqa: BLE001 - surfaced in every response instead
            _sources_error = f"{type(e).__name__}: {e}"
            log.error("sources import failed: %s", _sources_error)
    raise RuntimeError(f"sources unavailable: {_sources_error}")


def _ensure_started() -> None:
    """Start the collector threads once (idempotent, throttled retry on failure)."""
    global _started, _start_retry_at
    if _started or sources is None:
        return
    with _start_lock:
        if _started or time.monotonic() < _start_retry_at:
            return
        _start_retry_at = time.monotonic() + 60.0
        try:
            sources.start_background()
            _started = True
            log.info("background collectors started")
        except Exception as e:  # noqa: BLE001
            log.error("start_background failed: %s: %s", type(e).__name__, e)


def _stop_sources() -> None:
    fn = getattr(sources, "stop_background", None)
    if callable(fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            log.error("stop_background failed: %s: %s", type(e).__name__, e)


def _src() -> Any:
    """The sources module for a request handler: loaded, and its threads started."""
    mod = _load_sources()
    _ensure_started()
    return mod


def redact(s: str) -> str:
    """Route error text through sources.redact (known key values -> ***) when it exists."""
    fn = getattr(sources, "redact", None)
    if callable(fn):
        try:
            return str(fn(s))
        except Exception:  # noqa: BLE001
            pass
    return s


try:  # surface an import problem in the log at startup; the app still constructs
    _load_sources()
except Exception:  # noqa: BLE001
    pass


# --------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------
def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _today_et() -> str:
    return dt.datetime.now(ET).date().isoformat()


def _errstr(e: BaseException) -> str:
    return redact(f"{type(e).__name__}: {e}")[:ERROR_MAX_CHARS]


def sanitize(obj: Any, _depth: int = 0) -> Any:
    """Make an arbitrary assembler result JSON-safe: NaN/inf -> null, numpy/pandas scalars ->
    plain values, datetimes/Timestamps -> ISO strings, Paths and anything else -> str."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        return float(obj) if math.isfinite(obj) else None
    if _depth > 64:
        return str(obj)
    if isinstance(obj, dict):
        return {(k if isinstance(k, str) else str(k)): sanitize(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v, _depth + 1) for v in obj]
    if isinstance(obj, (set, frozenset)):
        try:
            seq = sorted(obj)
        except TypeError:
            seq = list(obj)
        return [sanitize(v, _depth + 1) for v in seq]
    tname = type(obj).__name__
    if tname in ("NaTType", "NAType"):  # pandas missing markers (NaT subclasses datetime: test first)
        return None
    if isinstance(obj, (dt.datetime, dt.date, dt.time)):
        return obj.isoformat()
    if isinstance(obj, dt.timedelta):
        return obj.total_seconds()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", "replace")
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, decimal.Decimal):
        return float(obj) if obj.is_finite() else None
    if tname == "datetime64":  # .item() of a ns-precision value is a raw integer
        return str(obj)
    iso = getattr(obj, "isoformat", None)  # pandas Timestamp and friends
    if callable(iso):
        try:
            return iso()
        except Exception:  # noqa: BLE001
            pass
    item = getattr(obj, "item", None)  # numpy scalars / 0-d arrays
    if callable(item):
        try:
            v = item()
            if v is not obj:
                return sanitize(v, _depth + 1)
        except Exception:  # noqa: BLE001
            pass
    tolist = getattr(obj, "tolist", None)  # numpy arrays, pandas Index/Series
    if callable(tolist):
        try:
            return sanitize(tolist(), _depth + 1)
        except Exception:  # noqa: BLE001
            pass
    try:
        if obj != obj:  # any other NaN-like object
            return None
    except Exception:  # noqa: BLE001
        pass
    return str(obj)


def _json(payload: dict, status: int = 200) -> Response:
    try:
        body = json.dumps(sanitize(payload), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except Exception as e:  # noqa: BLE001 - last resort, never a 500
        body = json.dumps({"error": f"encode failed: {type(e).__name__}: {e}"[:ERROR_MAX_CHARS],
                           "as_of": None, "server_now": _now_iso()})
    return Response(content=body, status_code=status, media_type="application/json", headers=API_HEADERS)


def _merge(base: dict, new: dict) -> None:
    """Copy `new` over `base`; dict-valued contract keys are filled in place so nested contract
    keys stay present even when the assembler omitted one. `new` is never mutated."""
    for k, v in new.items():
        cur = base.get(k)
        if isinstance(v, dict) and isinstance(cur, dict):
            merged = dict(cur)
            _merge(merged, v)
            base[k] = merged
        else:
            base[k] = v


_last_logged: dict[str, str | None] = {}


def _log_state(name: str, err: str | None) -> None:
    """Log a failure (or a recovery) once per state change, not once per 10 s tick."""
    if _last_logged.get(name) == err:
        return
    _last_logged[name] = err
    if err:
        log.warning("%s: %s", name, err)
    else:
        log.info("%s: recovered", name)


def _api(name: str, template: dict, call: Callable[[], Any], **echo: Any) -> Response:
    """Run one assembler and wrap it in the fixed envelope. Never raises."""
    out = copy.deepcopy(template)
    out.update(echo)
    try:
        result = call()
        if not isinstance(result, dict):
            raise TypeError(f"sources.{name} returned {type(result).__name__}, expected dict")
        _merge(out, result)
        err = out.get("error")
        _log_state(name, str(err)[:ERROR_MAX_CHARS] if err else None)
    except Exception as e:  # noqa: BLE001 - the whole point: one broken source, one dimmed panel
        out["error"] = _errstr(e)
        log.debug("%s failed", name, exc_info=True)
        _log_state(name, out["error"])
    out.setdefault("as_of", None)
    out["server_now"] = _now_iso()
    return _json(out)


def _api_invalid(name: str, template: dict, reason: str, **echo: Any) -> Response:
    """Spec-mandated 200 + error for invalid input on /api/logs, /api/chart, /api/options."""
    out = copy.deepcopy(template)
    out.update(echo)
    out["error"] = reason[:ERROR_MAX_CHARS]
    out["server_now"] = _now_iso()
    _log_state(name, out["error"])
    return _json(out)


def _reject(message: str) -> Response:
    return _json({"error": message[:ERROR_MAX_CHARS], "detail": message[:ERROR_MAX_CHARS],
                  "as_of": None, "server_now": _now_iso()}, status=422)


class BadInput(ValueError):
    """Query parameter failed validation."""


def _date_param(v: str | None, name: str = "date") -> str:
    if v is None or not v.strip():
        return _today_et()
    s = v.strip()
    if not DATE_RE.match(s):
        raise BadInput(f"invalid {name}: expected YYYY-MM-DD")
    try:
        dt.date.fromisoformat(s)
    except ValueError:
        raise BadInput(f"invalid {name}: not a calendar date") from None
    return s


def _symbol_param(v: str | None, default: str) -> str:
    if v is None or not v.strip():
        return default
    s = v.strip().upper()
    if not SYMBOL_RE.match(s):
        raise BadInput("invalid symbol: expected ^[A-Z][A-Z0-9.-]{0,9}$")
    return s


def _int_param(v: str | None, name: str, default: int, lo: int, hi: int) -> int:
    """Integer query param, clamped to [lo, hi]; missing -> default; non-integer -> BadInput."""
    if v is None or not v.strip():
        return default
    try:
        n = int(v.strip())
    except ValueError:
        raise BadInput(f"invalid {name}: expected an integer") from None
    return max(lo, min(hi, n))


def _choice_param(v: str | None, name: str, choices: tuple[str, ...], default: str | None) -> str | None:
    if v is None or not v.strip():
        return default
    s = v.strip().lower()
    if s not in choices:
        raise BadInput(f"invalid {name}: expected one of {', '.join(choices)}")
    return s


def _text_param(v: str | None, name: str, max_len: int = 200) -> str | None:
    if v is None or not v.strip():
        return None
    s = v.strip()
    if len(s) > max_len or any(ord(c) < 32 for c in s):
        raise BadInput(f"invalid {name}")
    return s


# --------------------------------------------------------------------------------------------
# contract templates: every key the contract (plus its additive keys) promises, null/empty
# --------------------------------------------------------------------------------------------
def _section() -> dict:
    return {"as_of": None, "error": None}


T_STATUS: dict = {
    "as_of": None, "gateway_connected": None, "account_id": None, "feed": None,
    "intraday": {"running": None, "mode": None, "equity_frac": None, "strategy": None,
                 "last_event_ts": None, "pnl_today": None, "trades_today": None, "positions_n": None,
                 "loss_limit_hit": None, "halted": None, "state": None},
    "daily": {"last_plan_ts": None, "last_fills_n": None, "next_run": None, "last_plan_kind": None},
    "loop": {"research_iterate_status": None, "last_run_ts": None, "next_run": None},
    "gates": {"approved_paper": None, "halt": None, "halt_intraday": None},
    "tasks": [],
    "sources": {k: {"ok": None, "detail": None} for k in ("ibkr", "yahoo", "alpaca", "theta", "fmp")},
    "integrity": {"evaluated": None, "items": []},
    "sections": {"ibkr": _section(), "files": _section(), "system": _section()},
    "heartbeats": {"ib": None, "files": None, "system": None, "data": None, "quotes": None},
    "server_now": None, "error": None,
}

T_ACCOUNT: dict = {
    "as_of": None, "gateway_connected": None, "nav": None, "cash": None, "buying_power": None,
    "gross_position_value": None, "unrealized_pnl": None, "realized_pnl": None,
    "positions": [], "open_orders": [], "fills": [], "available_funds": None, "warnings": [],
    "last_good_at": None, "reconnects": None, "server_now": None, "error": None,
}

T_NAV: dict = {
    "points": [], "days": None,
    "sources_n": {"dashboard": None, "plan": None, "intraday_start": None},
    "mock_excluded": None, "day_baseline": None, "as_of": None, "server_now": None, "error": None,
}

T_INTRADAY: dict = {
    "date": None,
    "config": {"start": None, "launch_params": None, "deployed": None, "drift": None, "sleeve_equity": None},
    "events_summary": {"counts": {}, "first_ts": None, "last_ts": None, "feed_delay_minutes": None,
                       "feed_delayed_n": None, "excluded": {"replay_decisions": None, "foreign_date_snapshots": None},
                       "available_dates": [], "bad_lines": None},
    "pnl_curve": [], "trades": [], "decisions_n": None, "positions_now": {}, "errors": [],
    "state": None, "mode": None, "pnl_today": None, "trades_today": None, "positions_source": None,
    "last_decision": None, "dead_orders": [], "pending_orders": [], "loss_limit_hit": None, "halted": None,
    "as_of": None, "server_now": None, "error": None,
}

T_DAILY: dict = {
    "date": None, "champion": None, "last_plan": None, "fills": [], "history": [],
    "last_executed_plan": None, "state": None, "warnings": [], "next_run": None,
    "as_of": None, "server_now": None, "error": None,
}

T_SUMMARY: dict = {
    "champion": None, "experiments_n": None, "last_20": [], "by_algorithm": [], "backlog_open": [],
    "journal_latest": [], "blockers_excerpt": None,
    "counts": {"daily": None, "intraday": None, "bad_lines": None}, "ledger_mtime": None,
    "backlog_meta": {"open_n": None, "done_n": None, "objective_excerpt": None, "preamble": None},
    "blockers_headings": [], "champion_run_dir_exists": None, "reports": [],
    "as_of": None, "server_now": None, "error": None,
}

T_EXPERIMENTS: dict = {"rows": [], "total": None, "as_of": None, "server_now": None, "error": None}

T_STRATEGIES: dict = {
    "deployed_intraday": None, "champion_daily": None, "intraday_modules": [], "daily_algorithms": [],
    "daily_docstrings": {},
    "framework": {"MIN_CHANGE": None, "PER_SYMBOL_HARD_CAP": None, "GROSS_HARD_CAP": None,
                  "DAILY_LOSS_LIMIT": None, "FLATTEN_MINUTE": None, "EXIT_MINUTE": None,
                  "SLIPPAGE_BPS": None, "UNIVERSE": [], "DAILY_SLEEVE_UNIVERSE": []},
    "as_of": None, "server_now": None, "error": None,
}

T_DATA: dict = {
    "stores": {"ibkr_minute": {"symbols": []}, "alpaca_minute": {"symbols": []},
               "lean_daily_n": None, "lean_minute_symbols": []},
    "events": {"generated": None, "symbols_n": None},
    "theta": {"alive": None, "plan": None},
    "keys_present": {k: None for k in ("ALPACA", "THETADATA", "FMP", "POLYGON", "FINNHUB", "NASDAQ", "TELEGRAM")},
    "scan_as_of": None, "as_of": None, "server_now": None, "error": None,
}

T_CHART: dict = {
    "symbol": None, "date": None, "bars": [], "trades": [], "source_used": None, "pending": False,
    "retry_in": None, "last_bar_t": None, "as_of": None, "server_now": None, "error": None,
}

T_SYSTEM: dict = {
    "automations": [], "last_runs": {"research_iterate": [], "research_review": []}, "git_log": [],
    "gateway_log_tail": [], "scheduled_tasks": [],
    "sections": {k: _section() for k in ("openclaw", "runs", "tasks", "git", "gateway_log")},
    "as_of": None, "server_now": None, "error": None,
}

T_LOGS: dict = {
    "lines": [], "file": None, "size": None, "mtime": None, "skipped": None,
    "as_of": None, "server_now": None, "error": None,
}

T_OPTIONS: dict = {
    "alive": None, "nearest_expiration": None, "atm_quotes": [], "message": None, "symbol": None,
    "spot": None, "as_of": None, "server_now": None, "error": None,
}


# --------------------------------------------------------------------------------------------
# middleware: 404 anything mentioning secrets; no-cache for static files
# --------------------------------------------------------------------------------------------
def _decoded_variants(raw: str) -> list[str]:
    out, cur = [], raw
    for _ in range(3):  # peel double encoding (%2573ecrets)
        cur = urllib.parse.unquote_plus(cur)
        out.append(cur.lower())
    return out


def _mentions_secret(scope: dict) -> bool:
    parts = [scope.get("path") or ""]
    raw_path = scope.get("raw_path")
    if raw_path:
        parts.append(raw_path.decode("latin-1", "replace") if isinstance(raw_path, bytes) else str(raw_path))
    qs = scope.get("query_string") or b""
    parts.append(qs.decode("latin-1", "replace") if isinstance(qs, bytes) else str(qs))
    return any(BLOCKED_WORD in v for p in parts for v in _decoded_variants(p))


class _GuardMiddleware:
    """Pure ASGI: 404 for any URL mentioning secrets; Cache-Control: no-cache on /static/."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        if _mentions_secret(scope):
            await PlainTextResponse("not found", status_code=404)(scope, receive, send)
            return
        if (scope.get("path") or "").startswith("/static/"):
            async def send_no_cache(message: dict) -> None:
                if message.get("type") == "http.response.start":
                    MutableHeaders(scope=message)["cache-control"] = "no-cache"
                await send(message)
            await self.app(scope, receive, send_no_cache)
            return
        await self.app(scope, receive, send)


# --------------------------------------------------------------------------------------------
# app
# --------------------------------------------------------------------------------------------
@asynccontextmanager
async def _lifespan(_app: FastAPI):
    try:
        _load_sources()
        _ensure_started()
    except Exception:  # noqa: BLE001 - already logged; serve error envelopes instead of dying
        pass
    try:
        yield
    finally:
        _stop_sources()


app = FastAPI(title="Quant Dashboard", lifespan=_lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(_GuardMiddleware)


@app.exception_handler(RequestValidationError)
async def _on_validation_error(_request: Request, exc: RequestValidationError) -> Response:
    return _reject(f"invalid input: {exc}")


@app.exception_handler(StarletteHTTPException)
async def _on_http_error(_request: Request, exc: StarletteHTTPException) -> Response:
    return PlainTextResponse(str(exc.detail or "error"), status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(Exception)
async def _on_unhandled(request: Request, exc: Exception) -> Response:
    # Safety net only: every /api handler already catches its own exceptions.
    if request.url.path.startswith("/api/"):
        return _json({"error": _errstr(exc), "as_of": None, "server_now": _now_iso()})
    return PlainTextResponse("internal error", status_code=500)


@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def index() -> Response:
    page = STATIC_DIR / "index.html"
    if not page.is_file():
        return PlainTextResponse(f"dashboard page missing: {page}", status_code=404)
    return FileResponse(str(page), media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    icon = STATIC_DIR / "favicon.ico"
    if icon.is_file():
        return FileResponse(str(icon), media_type="image/x-icon")
    return Response(status_code=204)


@app.get("/api/health")
def api_health() -> Response:
    now = _now_iso()
    return _json({"ok": True, "as_of": now, "server_now": now, "error": None})


@app.get("/api/status")
def api_status() -> Response:
    return _api("status", T_STATUS, lambda: _src().status())


@app.get("/api/account")
def api_account() -> Response:
    return _api("account", T_ACCOUNT, lambda: _src().account())


@app.get("/api/nav_history")
def api_nav_history(days: str | None = None) -> Response:
    try:
        n = _int_param(days, "days", DEFAULT_DAYS, 1, MAX_DAYS)
    except BadInput as e:
        return _reject(str(e))
    return _api("nav_history", T_NAV, lambda: _src().nav_history(n), days=n)


@app.get("/api/sleeves/intraday")
def api_sleeve_intraday(date: str | None = None) -> Response:
    try:
        d = _date_param(date)
    except BadInput as e:
        return _reject(str(e))
    return _api("sleeve_intraday", T_INTRADAY, lambda: _src().sleeve_intraday(d), date=d)


@app.get("/api/sleeves/daily")
def api_sleeve_daily(date: str | None = None) -> Response:
    try:
        d = _date_param(date)
    except BadInput as e:
        return _reject(str(e))
    return _api("sleeve_daily", T_DAILY, lambda: _src().sleeve_daily(d), date=d)


@app.get("/api/research/summary")
def api_research_summary() -> Response:
    return _api("research_summary", T_SUMMARY, lambda: _src().research_summary())


@app.get("/api/research/experiments")
def api_research_experiments(algorithm: str | None = None, limit: str | None = None,
                             track: str | None = None) -> Response:
    try:
        algo = _text_param(algorithm, "algorithm")
        lim = _int_param(limit, "limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
        trk = _choice_param(track, "track", TRACKS + ("all",), None)
        if trk == "all":
            trk = None
    except BadInput as e:
        return _reject(str(e))
    return _api("experiments", T_EXPERIMENTS, lambda: _src().experiments(algo, lim, trk))


@app.get("/api/strategies")
def api_strategies() -> Response:
    return _api("strategies", T_STRATEGIES, lambda: _src().strategies())


@app.get("/api/data")
def api_data() -> Response:
    return _api("data", T_DATA, lambda: _src().data())


@app.get("/api/chart")
def api_chart(symbol: str | None = None, date: str | None = None, source: str | None = None) -> Response:
    raw_symbol = (symbol or "").strip().upper()[:32] or None
    try:
        sym = _symbol_param(symbol, DEFAULT_CHART_SYMBOL)
        d = _date_param(date)
        src = _choice_param(source, "source", CHART_SOURCES, "auto")
    except BadInput as e:  # spec: 200 with error and no bars
        return _api_invalid("chart", T_CHART, str(e), symbol=raw_symbol, date=(date or "").strip()[:32] or None)
    return _api("chart", T_CHART, lambda: _src().chart(sym, d, src), symbol=sym, date=d)


@app.get("/api/system")
def api_system() -> Response:
    return _api("system", T_SYSTEM, lambda: _src().system())


@app.get("/api/logs")
def api_logs(name: str | None = None, date: str | None = None, n: str | None = None) -> Response:
    try:
        nm = _choice_param(name, "name", LOG_NAMES, "intraday")
        d = _date_param(date)
        count = _int_param(n, "n", DEFAULT_LOG_N, 1, MAX_LOG_N)
    except BadInput as e:  # spec: 200 with error and empty lines
        return _api_invalid("logs", T_LOGS, str(e))
    return _api("logs", T_LOGS, lambda: _src().logs(nm, d, count))


@app.get("/api/options")
def api_options(symbol: str | None = None) -> Response:
    raw_symbol = (symbol or "").strip().upper()[:32] or None
    try:
        sym = _symbol_param(symbol, DEFAULT_OPTIONS_SYMBOL)
    except BadInput as e:
        return _api_invalid("options", T_OPTIONS, str(e), symbol=raw_symbol, message=str(e))
    return _api("options", T_OPTIONS, lambda: _src().options(sym), symbol=sym)


# static files last so /api and / routes win; html=False -> no directory index, no listing
app.mount("/static", StaticFiles(directory=str(STATIC_DIR), check_dir=False, html=False), name="static")


def main(argv: list[str] | None = None) -> int:
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description="Quant dashboard server (binds 127.0.0.1 only)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(app, host=HOST, port=args.port, workers=1, log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
