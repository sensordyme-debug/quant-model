"""Theta Data (options) client for the research loop. Talks to the local Theta Terminal v3.

Terminal: C:\\Users\\ashur\\AppData\\Local\\Programs\\ThetaTerminal\\ThetaTerminalv3.jar, started with
the user-local Java 21 (%LOCALAPPDATA%\\Programs\\jre21) and the key from live/secrets.env; it
listens on http://127.0.0.1:25503. Start it with `python scripts/theta_data.py --start-terminal`.

Plan on this account: **Options FREE as of 2026-09-12 13:32** (it was STANDARD on 2026-09-10
02:24; both `Subscriptions:` lines are in the terminal's own terminal.out). On FREE only
`/v3/option/list/*` answers - every history, greeks, open-interest and snapshot endpoint
returns the entitlement error - so the 0DTE store is frozen at 1,891 sessions ending
2026-09-10. `--check` reports this in one call. See research/BLOCKERS.md for the ask: the
0DTE store needs only the **VALUE** tier (`/v3/option/history/quote`); STANDARD is needed
only by scripts/iv_regime.py (greeks/eod and implied_volatility).

Never run two terminals. A second login invalidates the first instance's session ID and
every endpoint then returns 478; `start_terminal` now refuses rather than causing it.

STANDARD serves, per contract or per expiration (strike=* with strike_range):
  option quotes / OHLC / trades at intervals >= 1m, implied vol history, first-order greeks
  history (delta/theta/vega/rho), EOD rows with the full greek set, open interest, snapshots,
  expirations and strikes back to 2012. NOT on STANDARD: /greeks/all intraday (Pro), stock
  history (needs a stock plan; use data/minute or Alpaca instead).

    python scripts/theta_data.py --expirations SPY
    python scripts/theta_data.py --chain SPY 2026-09-11 --date 2026-09-09 --interval 15m --range 5
    python scripts/theta_data.py --iv SPY 2026-09-11 650 C --date 2026-09-09 --interval 5m
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

BASE = "http://127.0.0.1:25503"
TERMINAL_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "ThetaTerminal"
JAVA = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "jre21" / "bin" / "java.exe"


def _get(path: str, **params) -> pd.DataFrame:
    q = {k: v for k, v in params.items() if v is not None}
    url = BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
    with urllib.request.urlopen(url, timeout=120) as r:
        text = r.read().decode("utf-8")
    if not text.strip():
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(text))
    for col in ("timestamp", "underlying_timestamp", "created", "last_trade"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def listening() -> bool:
    """Is anything bound to the terminal's port? True even when it answers with an error.

    This is the question `start_terminal` must ask, and it is not the same as `alive`.
    An HTTP error status means a terminal *is* running and refused the request - on 478
    ('Invalid session ID'), 403 or an entitlement error the process is very much there.
    Starting a second one then cannot bind 25503, and its login invalidates the first
    instance's session, which turns a recoverable error into a dead data path. That is
    exactly what happened between 2026-09-10 02:24 and 2026-09-12 13:32; see
    research/journal_options.md, O-4.
    """
    try:
        with socket.create_connection(("127.0.0.1", 25503), timeout=3):
            return True
    except OSError:
        return False


def alive() -> bool:
    """Is the terminal up and serving data? False when it is up but refusing."""
    try:
        urllib.request.urlopen(BASE + "/v3/option/list/expirations?symbol=SPY", timeout=5).read(64)
        return True
    except urllib.error.HTTPError:
        return False
    except Exception:  # noqa: BLE001
        return False


def status() -> dict:
    """Terminal and entitlement state in one call, so a failure names its own cause."""
    if not listening():
        return {"listening": False, "alive": False, "detail": "nothing bound to 127.0.0.1:25503"}
    try:
        urllib.request.urlopen(BASE + "/v3/option/list/expirations?symbol=SPY", timeout=10).read(64)
    except urllib.error.HTTPError as exc:
        body = exc.read(300).decode("utf-8", "replace").strip()
        return {"listening": True, "alive": False, "detail": f"HTTP {exc.code}: {body}"}
    except Exception as exc:  # noqa: BLE001
        return {"listening": True, "alive": False, "detail": repr(exc)}
    # The listing endpoints are served on FREE; a data endpoint is what tells us the plan.
    try:
        urllib.request.urlopen(
            BASE + "/v3/option/history/quote?symbol=SPY&expiration=2026-09-11&strike=650000"
                   "&right=C&start_date=2026-09-11&end_date=2026-09-11&interval=5m", timeout=20).read(64)
        return {"listening": True, "alive": True, "detail": "list and history/quote both served"}
    except urllib.error.HTTPError as exc:
        body = exc.read(300).decode("utf-8", "replace").strip()
        return {"listening": True, "alive": True,
                "detail": f"list served, but history/quote is HTTP {exc.code}: {body}"}
    except Exception as exc:  # noqa: BLE001
        return {"listening": True, "alive": True, "detail": f"list served; history/quote {exc!r}"}


def start_terminal(wait: int = 30) -> bool:
    if alive():
        return True
    if listening():
        # Never start a second instance. It cannot bind the port, and its login invalidates
        # the running instance's session ID.
        raise SystemExit(
            "A Theta Terminal is already bound to 127.0.0.1:25503 but is not serving data.\n"
            "Do NOT start a second one - the duplicate login invalidates the live session.\n"
            f"Diagnose with `python scripts/theta_data.py --check`; state: {status()['detail']}\n"
            "If it is a session error, stop the running terminal first, then start exactly one.")
    if not (TERMINAL_DIR / "ThetaTerminalv3.jar").exists() or not JAVA.exists():
        raise SystemExit("Theta Terminal jar or Java 21 missing; see the module docstring")
    subprocess.Popen([str(JAVA), "-jar", "ThetaTerminalv3.jar"], cwd=TERMINAL_DIR,
                     stdout=open(TERMINAL_DIR / "terminal.out", "ab"), stderr=subprocess.STDOUT,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(wait):
        time.sleep(1)
        if alive():
            return True
    return False


# ----------------------------------------------------------------------------- queries
def expirations(symbol: str) -> list[str]:
    df = _get("/v3/option/list/expirations", symbol=symbol)
    return sorted(df["expiration"].astype(str)) if not df.empty else []


def strikes(symbol: str, expiration: str) -> list[float]:
    df = _get("/v3/option/list/strikes", symbol=symbol, expiration=expiration)
    return sorted(df["strike"].astype(float)) if not df.empty else []


def quotes(symbol: str, expiration: str, strike: float | str = "*", right: str = "both",
           date: str | None = None, interval: str = "1m", strike_range: int | None = None,
           start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
    """Bid/ask history. strike='*' with strike_range=n returns n strikes around the money."""
    return _get("/v3/option/history/quote", symbol=symbol, expiration=expiration, strike=strike, right=right,
                date=date, interval=interval, strike_range=strike_range, start_date=start_date, end_date=end_date)


def ohlc(symbol: str, expiration: str, strike: float | str = "*", right: str = "both",
         date: str | None = None, interval: str = "1m", strike_range: int | None = None) -> pd.DataFrame:
    return _get("/v3/option/history/ohlc", symbol=symbol, expiration=expiration, strike=strike, right=right,
                date=date, interval=interval, strike_range=strike_range)


def implied_vol(symbol: str, expiration: str, strike: float | str = "*", right: str = "both",
                date: str | None = None, interval: str = "5m", strike_range: int | None = None) -> pd.DataFrame:
    return _get("/v3/option/history/greeks/implied_volatility", symbol=symbol, expiration=expiration, strike=strike,
                right=right, date=date, interval=interval, strike_range=strike_range)


def first_order_greeks(symbol: str, expiration: str, strike: float | str = "*", right: str = "both",
                       date: str | None = None, interval: str = "5m", strike_range: int | None = None) -> pd.DataFrame:
    """delta, theta, vega, rho, implied_vol per interval (STANDARD plan)."""
    return _get("/v3/option/history/greeks/first_order", symbol=symbol, expiration=expiration, strike=strike,
                right=right, date=date, interval=interval, strike_range=strike_range)


def eod_greeks(symbol: str, expiration: str, strike: float | str = "*", right: str = "both",
               start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
    """End-of-day rows with the full greek set (gamma, vanna, charm ...)."""
    return _get("/v3/option/history/greeks/eod", symbol=symbol, expiration=expiration, strike=strike, right=right,
                start_date=start_date, end_date=end_date)


def open_interest(symbol: str, expiration: str, strike: float | str = "*", right: str = "both",
                  start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
    return _get("/v3/option/history/open_interest", symbol=symbol, expiration=expiration, strike=strike, right=right,
                start_date=start_date, end_date=end_date)


def snapshot_quote(symbol: str, expiration: str, strike: float | str = "*", right: str = "both") -> pd.DataFrame:
    return _get("/v3/option/snapshot/quote", symbol=symbol, expiration=expiration, strike=strike, right=right)


def nearest_expiration(symbol: str, on: dt.date, min_days: int = 0) -> str | None:
    exps = [e for e in expirations(symbol) if dt.date.fromisoformat(e) >= on + dt.timedelta(days=min_days)]
    return exps[0] if exps else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start-terminal", action="store_true")
    ap.add_argument("--check", action="store_true", help="terminal and entitlement state")
    ap.add_argument("--expirations")
    ap.add_argument("--chain", nargs=2, metavar=("SYMBOL", "EXPIRATION"))
    ap.add_argument("--iv", nargs=4, metavar=("SYMBOL", "EXPIRATION", "STRIKE", "RIGHT"))
    ap.add_argument("--date"); ap.add_argument("--interval", default="15m"); ap.add_argument("--range", type=int, default=5)
    args = ap.parse_args()
    if args.check:
        st = status()
        print(f"listening {st['listening']}  serving {st['alive']}\n  {st['detail']}")
        return 0 if st["alive"] else 1
    if args.start_terminal:
        print("terminal alive" if start_terminal() else "terminal did not come up")
        return 0
    if not alive():
        print("Theta Terminal is not running; use --start-terminal")
        return 1
    if args.expirations:
        e = expirations(args.expirations)
        print(len(e), "expirations;", e[:3], "...", e[-5:])
    if args.chain:
        df = quotes(args.chain[0], args.chain[1], "*", "both", date=args.date, interval=args.interval, strike_range=args.range)
        print(df.tail(12).to_string(index=False))
    if args.iv:
        s, e, k, r = args.iv
        df = implied_vol(s, e, float(k), r, date=args.date, interval=args.interval)
        print(df[["timestamp", "midpoint", "implied_vol", "underlying_price"]].tail(10).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
