#!/usr/bin/env python
"""Live intraday trader for the active sleeve (ib_async, IB Gateway paper on 127.0.0.1:4002).

    python scripts/intraday_trader.py --replay 2026-09-08       # offline, stored bars, simulated fills
    python scripts/intraday_trader.py --dry-run                 # live bars, decisions logged, no orders
    python scripts/intraday_trader.py                           # live paper trading (needs approval file)
    python scripts/intraday_trader.py --flatten                 # close this sleeve's book now and exit

Runs from launch until 15:42 ET: every completed 1-minute bar it recomputes features, asks the
strategy (algorithms/intraday/<name>/signal.py) for target weights, scales them by --equity-frac
of net liquidation, and sends market orders tagged orderRef=INTRADAY. It tracks ITS OWN book in
live/state/intraday_book.json (fills, not account positions), so it never touches the daily
sleeve's holdings, and it is flat by 15:38 ET so the 15:45 daily rebalance sees only its own book.

Safety: live/APPROVED_PAPER.md required for orders; account must start with DU; live/HALT or
live/HALT_INTRADAY flattens and stops; daily loss limit flattens and stops; per-symbol and gross
caps; reconnects on Gateway drops. Logs: live/log/intraday-<date>.jsonl. Alerts via live/alerts.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import math
import sys
import time
import traceback
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from intraday_common import (DAILY_LOSS_LIMIT, ET, EXIT_MINUTE, FLATTEN_MINUTE, GROSS_HARD_CAP, LIVE,  # noqa: E402
                             MIN_CHANGE, PER_SYMBOL_HARD_CAP, REPO, UNIVERSE, commission, load_universe,
                             log_event, slippage)
from intraday_common import notify as _notify  # noqa: E402

sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
if str(REPO) not in sys.path:            # so `quant_brain` resolves when run as a script
    sys.path.insert(0, str(REPO))
from base import features  # noqa: E402

APPROVAL = LIVE / "APPROVED_PAPER.md"
HALT_FILES = [LIVE / "HALT", LIVE / "HALT_INTRADAY"]
BOOK_FILE = LIVE / "state" / "intraday_book.json"
ORDER_REF = "INTRADAY"
LOG = "intraday"


def log(kind, **f):
    log_event(LOG, kind, **f)


def notify(text: str) -> None:
    """Replay runs never alert; only live/dry runs push to the chat channel."""
    if LOG == "intraday":
        _notify(text, LOG)


def load_strategy(name: str):
    path = REPO / "algorithms" / "intraday" / name / "signal.py"
    spec = importlib.util.spec_from_file_location(f"intraday_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def minute_index(t: pd.Timestamp) -> int:
    return int((t.hour - 9) * 60 + t.minute - 30)


#: Minutes before the close at which the sleeve must be targeting flat. 390 - 368 = 22 on a
#: regular session, which is the 15:38 the framework has always used; expressed as a distance
#: from the close it is also correct on a 13:00 early close, where minute 368 does not exist.
FLATTEN_BEFORE_CLOSE = 390 - FLATTEN_MINUTE
EXIT_BEFORE_CLOSE = 390 - EXIT_MINUTE


def flatten_minute_for(day) -> int:
    """The bar index from the open at which to start flattening, for THIS session. AUD-07.

    `FLATTEN_MINUTE = 368` is the 368th minute after 09:30. On a 13:00 early close the
    session is 210 minutes long, so bar 368 never arrives: `step` returns on `t <= last_t`,
    no flatten is ever sent, and the position is carried into the 15:45 daily rebalance as a
    foreign holding. Falls back to the constant if the calendar cannot answer, which keeps a
    calendar problem from becoming a trading outage.
    """
    try:
        from quant_brain.markets.equity_us import CALENDAR
        m = CALENDAR.minutes_before_close(day, FLATTEN_BEFORE_CLOSE)
    except Exception:  # noqa: BLE001
        return FLATTEN_MINUTE
    return FLATTEN_MINUTE if m is None else int(m)


def exit_minute_for(day) -> int:
    """Bar index at which the live loop exits, for THIS session."""
    try:
        from quant_brain.markets.equity_us import CALENDAR
        m = CALENDAR.minutes_before_close(day, EXIT_BEFORE_CLOSE)
    except Exception:  # noqa: BLE001
        return EXIT_MINUTE
    return EXIT_MINUTE if m is None else int(m)


# ----------------------------------------------------------------------------- book
class Book:
    def __init__(self):
        self.pos: dict[str, int] = {}
        self.cost: dict[str, float] = {}      # cash paid per symbol (signed), for P&L
        self.realized = 0.0
        self.costs = 0.0
        self.trades = 0

    _closed = 0.0   # P&L of symbols that have gone flat (see book_fill)

    def pnl(self, prices: dict[str, float]) -> float:
        """Sleeve P&L since the book was last empty: closed P&L + open symbols' cash flow + marks."""
        return self._closed + sum(self.cost.values()) + sum(q * prices.get(s, 0.0) for s, q in self.pos.items())

    def to_json(self, mode: str = "live"):
        return {"mode": mode, "date": str(dt.date.today()), "pos": self.pos, "cost": self.cost,
                "closed": self._closed, "costs": self.costs, "trades": self.trades}

    @classmethod
    def from_json(cls, d):
        b = cls()
        b.pos = {k: int(v) for k, v in d.get("pos", {}).items()}
        b.cost = {k: float(v) for k, v in d.get("cost", {}).items()}
        b._closed = float(d.get("closed", 0.0))
        b.costs = float(d.get("costs", 0.0))
        b.trades = int(d.get("trades", 0))
        return b


def reconcile_book(book: Book, account: dict[str, int], universe) -> list[tuple[str, int, int]]:
    """Make the book agree with what the account actually holds. AUD-08.

    Start-up and `--flatten` used to sell what the BOOK said, not what the ACCOUNT held. A
    position closed by any other path - the daily runner's HALT branch, a manual close, an
    order that filled after the loop exited - stayed in the book, so the next session's
    flatten sold shares that were not there and opened an untracked short. The reverse case
    is worse: a position the book does not know about is never flattened at all.

    Only symbols in the sleeve's own universe are touched. The daily sleeve's holdings are
    foreign; adopting them here would let the intraday flatten sell the daily book, which is
    the mirror image of AUD-03.

    Returns [(symbol, book_qty, account_qty)] for every discrepancy, so the caller can log
    each one rather than silently converging.
    """
    universe = set(universe)
    changes: list[tuple[str, int, int]] = []
    for sym in sorted(universe | set(book.pos)):
        if sym not in universe:
            continue
        held = int(account.get(sym, 0))
        booked = int(book.pos.get(sym, 0))
        if held == booked:
            continue
        changes.append((sym, booked, held))
        if held:
            book.pos[sym] = held
        else:
            book.pos.pop(sym, None)
        # The cost basis for an adopted position is unknowable from a position snapshot.
        # Dropping it means this symbol contributes only its mark to `pnl` until it closes,
        # which understates or overstates the day by the unknown entry - but a wrong basis
        # that LOOKS authoritative is worse than an absent one, and the daily loss limit is
        # measured against nav_open rather than the book's own history.
        book.cost.pop(sym, None)
    return changes


def expected_latest_bar(now: pd.Timestamp):
    """The most recent 1-minute bar that should exist by `now`, or None if unknowable.

    AUD-09: `--feed auto` measured IBKR's delay by comparing the newest bar it returned
    against the wall clock. At the 09:25 launch the newest bar is the PREVIOUS session's
    15:59, so the computed delay was ~1,046 minutes, the probe always failed, and the runner
    silently never used the IB feed at all - the fallback was permanent rather than
    conditional.

    The comparison has to be against the last bar that could exist, which needs the exchange
    calendar. Before the open that is the prior session's close; during the session it is
    the previous minute; after the close it is today's close.
    """
    try:
        from quant_brain.markets.equity_us import CALENDAR
    except Exception:  # noqa: BLE001 - the probe must never be the thing that stops trading
        return None
    day = now.date()
    sess = CALENDAR.session(day) if CALENDAR.is_trading_day(day) else None
    if sess is not None:
        open_t = pd.Timestamp.combine(day, sess.open_t).tz_localize(now.tz)
        close_t = pd.Timestamp.combine(day, sess.close_t).tz_localize(now.tz)
        if now >= close_t:
            return close_t - pd.Timedelta(minutes=1)
        if now > open_t:
            return now - pd.Timedelta(minutes=1)
    # Pre-open, or a non-trading day: the newest bar that can exist is the previous
    # session's last minute. Ten days back clears any holiday-plus-weekend run.
    cur = day
    for _ in range(10):
        cur = cur - dt.timedelta(days=1)
        if not CALENDAR.is_trading_day(cur):
            continue
        ps = CALENDAR.session(cur)
        if ps is None:
            return None
        return pd.Timestamp.combine(cur, ps.close_t).tz_localize(now.tz) - pd.Timedelta(minutes=1)
    return None


def startup_reconcile(book: Book, account_positions: dict[str, int], universe) -> list[tuple[str, int, int]]:
    """Reconcile the book against the account, and log every discrepancy. AUD-08.

    Called on EVERY start-up path - normal, --flatten and --flatten-from-account - so that
    whatever the runner does next it is acting on what the account actually holds.
    """
    changes = reconcile_book(book, account_positions, universe)
    for sym, was, now in changes:
        log("reconcile", symbol=sym, book=was, account=now)
    if changes:
        log("reconciled", count=len(changes), book=dict(book.pos))
    return changes


def book_fill(book: Book, sym: str, qty: int, price: float, cost: float):
    """Simpler, exact P&L accounting: track cash per symbol; when a symbol goes flat, move its
    cash into closed P&L."""
    prev = book.pos.get(sym, 0)
    new = prev + qty
    book.cost[sym] = book.cost.get(sym, 0.0) - qty * price - cost
    book.costs += cost
    book.trades += 1
    if new == 0:
        book._closed += book.cost.pop(sym, 0.0)
        book.pos.pop(sym, None)
    else:
        book.pos[sym] = new


def save_book(book: Book):
    """Only the LIVE trader persists its book. Replay/backtest books must never reach this file,
    or a later live start would try to flatten simulated positions on the real account."""
    BOOK_FILE.parent.mkdir(parents=True, exist_ok=True)
    BOOK_FILE.write_text(json.dumps(book.to_json("live"), indent=2) + "\n", encoding="utf-8")


def load_book() -> Book:
    """The live book from a previous LIVE run (any date: leftovers from a crash must be
    flattened). Files written by anything other than a live run are ignored."""
    if BOOK_FILE.exists():
        d = json.loads(BOOK_FILE.read_text(encoding="utf-8"))
        if d.get("mode") == "live":
            b = Book.from_json(d)
            if d.get("date") != str(dt.date.today()):
                # A new session: positions carry over (they must be flattened), but yesterday's
                # closed P&L, costs and trade count do not - on 2026-09-11 they leaked into the
                # day's P&L and would have tripped the loss limit ~$6.8k early.
                log("book_rollover", from_date=d.get("date"), positions=b.pos, dropped_closed=b._closed, dropped_trades=b.trades)
                b._closed, b.costs, b.trades = 0.0, 0.0, 0
            return b
        log("ignored_book_file", mode=d.get("mode"), date=d.get("date"))
    return Book()


# ----------------------------------------------------------------------------- executors
class SimExecutor:
    """Replay: fills at the next bar's open plus slippage (same model as the backtester)."""

    def __init__(self, bars: dict[str, pd.DataFrame]):
        self.bars = bars
        self.pending: dict[str, int] = {}

    def submit(self, orders: dict[str, int], when):
        self.pending.update({s: self.pending.get(s, 0) + q for s, q in orders.items()})

    def pending_qty(self) -> dict[str, int]:
        """Signed quantity submitted but not yet booked. AUD-06."""
        return {s: q for s, q in self.pending.items() if q}

    def settle(self, t) -> list[tuple[str, int, float, float]]:
        fills = []
        for s, q in list(self.pending.items()):
            df = self.bars.get(s)
            if df is None or t not in df.index:
                continue
            px = float(df.loc[t, "o"])
            fills.append((s, q, px, commission(q, px) + slippage(q, px)))
            del self.pending[s]
        return fills


class LiveExecutor:
    def __init__(self, ib, contracts: dict):
        self.ib, self.contracts = ib, contracts
        from ib_async import MarketOrder
        self.MarketOrder = MarketOrder
        self.open: list = []

    def submit(self, orders: dict[str, int], when):
        # AUD-08/09: an order sent outside RTH has outsideRth=False, so IBKR queues it to the
        # next open where nothing is tracking it and the sleeve re-sells it. Refuse and say so.
        now_et = pd.Timestamp(dt.datetime.now(ET))
        try:
            from quant_brain.markets.equity_us import CALENDAR
            sess = CALENDAR.session(now_et.date())
        except Exception:  # noqa: BLE001
            sess = None
        if sess is not None and not (sess.open_t <= now_et.time() <= sess.close_t):
            log("submit_refused_outside_rth", orders=orders, now=str(now_et),
                session=f"{sess.open_t}-{sess.close_t}")
            _notify(f"INTRADAY refused {len(orders)} order(s) outside RTH at "
                    f"{now_et:%H:%M} (session {sess.open_t}-{sess.close_t})", LOG)
            return
        for s, q in orders.items():
            o = self.MarketOrder("BUY" if q > 0 else "SELL", abs(q))
            o.orderRef = ORDER_REF
            o.outsideRth = False
            o.tif = "DAY"                 # explicit: an empty TIF makes IBKR emit code 10349, which ib_async mislabels as a cancel
            tr = self.ib.placeOrder(self.contracts[s], o)
            self.open.append(tr)
            # `t` is the decision bar; scripts/slippage_report.py joins on `id` and prices the
            # fill against the next bar's open, which is what the backtester assumes.
            log("order", symbol=s, qty=q, id=tr.order.orderId, t=str(when))

    def pending_qty(self) -> dict[str, int]:
        """Signed quantity still working at the broker, per symbol. AUD-06.

        Remaining, not submitted: an order half filled has half its size outstanding, and
        sizing must net only the part that is still on the wire. `tr.fills` is the same
        source `settle` trusts, deliberately - IBKR's status flag lied on 2026-09-10 and the
        two must not disagree about what is outstanding.
        """
        out: dict[str, int] = {}
        for tr in self.open:
            done = float(sum(f.execution.shares for f in tr.fills))
            left = float(tr.order.totalQuantity) - done
            if left <= 1e-9:
                continue
            sign = 1 if tr.order.action == "BUY" else -1
            sym = tr.contract.symbol
            out[sym] = out.get(sym, 0) + int(round(left)) * sign
        return {s: q for s, q in out.items() if q}

    def settle(self, t) -> list[tuple[str, int, float, float]]:
        """Collect fills from orders sent earlier; returns (sym, signed_qty, avg_px, commission)."""
        self.ib.sleep(3)
        fills, still = [], []
        now = time.time()
        seen = getattr(self, "_seen", None)
        if seen is None:
            seen = self._seen = {}
        for tr in self.open:
            st = tr.orderStatus
            oid = tr.order.orderId
            seen.setdefault(oid, now)
            # Truth comes from executions, not from the library's status flag: IBKR's informational
            # code 10349 ("TIF set to DAY") made ib_async mark live orders Cancelled on 2026-09-10
            # while they filled normally seconds later.
            execs = [f.execution for f in tr.fills]
            filled_qty = float(sum(e.shares for e in execs))
            sign = 1 if tr.order.action == "BUY" else -1
            complete = filled_qty >= tr.order.totalQuantity - 1e-9 or (st.status == "Filled" and filled_qty > 0)
            if complete:
                q = int(round(filled_qty)) * sign
                avg = sum(e.shares * e.price for e in execs) / filled_qty
                comm = sum((f.commissionReport.commission or 0.0) for f in tr.fills if f.commissionReport) or commission(q, avg)
                fills.append((tr.contract.symbol, q, float(avg), float(comm)))
                # filled_at is the exchange's own fill time; the record's `ts` is only when this
                # loop noticed, so A-5 needs both to separate latency from polling cadence.
                at = max((f.time for f in tr.fills if getattr(f, "time", None)), default=None)
                log("fill", symbol=tr.contract.symbol, qty=q, avg_price=avg, commission=comm,
                    status=st.status, id=oid, filled_at=str(at) if at else None)
                seen.pop(oid, None)
                continue
            dead_status = st.status in ("Cancelled", "Inactive", "ApiCancelled")
            if dead_status and now - seen[oid] > 90:
                # 90 s of grace so a false "Cancelled" has time to be overwritten by the real status
                if filled_qty > 0:                                   # partial fill: book what happened
                    q = int(round(filled_qty)) * sign
                    avg = sum(e.shares * e.price for e in execs) / filled_qty
                    fills.append((tr.contract.symbol, q, float(avg), commission(q, avg)))
                    log("fill", symbol=tr.contract.symbol, qty=q, avg_price=avg, status="partial", id=oid)
                log("order_dead", symbol=tr.contract.symbol, status=st.status, filled=filled_qty, id=oid)
                seen.pop(oid, None)
                continue
            still.append(tr)
        self.open = still
        return fills


# ----------------------------------------------------------------------------- feeds
class IBFeed:
    """1-minute bars from IBKR's historical endpoint with keepUpToDate. Current to the minute
    with a market data subscription; 15 minutes DELAYED without one (measured 2026-09-09)."""
    name = "ib"

    def __init__(self, ib, contracts):
        self.ib, self.streams = ib, {}
        for s, c in contracts.items():
            self.streams[s] = ib.reqHistoricalData(c, endDateTime="", durationStr="3 D", barSizeSetting="1 min",
                                                   whatToShow="TRADES", useRTH=True, keepUpToDate=True, formatDate=2)
            ib.sleep(0.25)

    def bars(self, cutoff) -> dict[str, pd.DataFrame]:
        out = {}
        for s, bl in self.streams.items():
            if not bl:
                continue
            df = pd.DataFrame([{"date": b.date, "o": b.open, "h": b.high, "l": b.low, "c": b.close, "v": b.volume} for b in bl])
            df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_convert(ET)
            df = df.set_index("date").sort_index()
            out[s] = df[df.index < cutoff]
        return out


class YahooFeed:
    """1-minute bars from Yahoo (one batched download per minute). Real-time-ish (about a
    minute behind) and free, used when IBKR bars are delayed."""
    name = "yahoo"

    def __init__(self, symbols):
        self.symbols = list(symbols)

    def bars(self, cutoff) -> dict[str, pd.DataFrame]:
        import yfinance as yf
        data = yf.download(self.symbols, period="2d", interval="1m", auto_adjust=False, prepost=False,
                           progress=False, group_by="column", threads=True)
        out = {}
        for s in self.symbols:
            try:
                df = pd.DataFrame({"o": data["Open"][s], "h": data["High"][s], "l": data["Low"][s],
                                   "c": data["Close"][s], "v": data["Volume"][s]}).dropna(subset=["c"])
            except KeyError:
                continue
            df.index = pd.to_datetime(df.index).tz_convert(ET)
            t = df.index.time
            df = df[(t >= dt.time(9, 30)) & (t < dt.time(16, 0))]
            out[s] = df[df.index < cutoff]
        return out


def make_feed(choice: str, ib, contracts):
    if choice == "yahoo":
        return YahooFeed(contracts.keys())
    ibf = IBFeed(ib, contracts)
    if choice == "ib":
        return ibf
    # auto: measure IBKR's delay on one symbol; fall back to Yahoo if it is stale
    ib.sleep(3)
    now = pd.Timestamp(dt.datetime.now(ET)).floor("min")
    probe = ibf.bars(now)
    latest = max((df.index[-1] for df in probe.values() if not df.empty), default=None)
    # AUD-09: compare against the newest bar that COULD exist, not against the wall clock.
    # At the 09:25 launch the newest bar is the prior session's 15:59, so a wall-clock
    # comparison reported ~1,046 minutes of delay and the IB feed was never once selected.
    reference = expected_latest_bar(now) or (now - pd.Timedelta(minutes=1))
    delay = (reference - latest).total_seconds() / 60.0 if latest is not None else 99.0
    log("feed_probe", ib_delay_minutes=delay, reference=str(reference), latest=str(latest))
    if delay > 3:
        print(f"IBKR bars are {delay:.0f} min delayed (no market data subscription); using Yahoo feed")
        for bl in ibf.streams.values():
            try:
                ib.cancelHistoricalData(bl)
            except Exception:  # noqa: BLE001
                pass
        return YahooFeed(contracts.keys())
    return ibf


# ----------------------------------------------------------------------------- core step
class Trader:
    def __init__(self, strategy, params, equity_frac: float, book: Book, executor, dry_run: bool, mode: str):
        self.strategy, self.params, self.equity_frac = strategy, params, equity_frac
        self.book, self.ex, self.dry_run, self.mode = book, executor, dry_run, mode
        self.persist = (mode == "live" and not dry_run)   # only real paper runs write the book file
        self.state: dict = {}
        self.stopped = False
        self.nav_open = None
        self.last_report = None
        self.last_t = None
        self.decisions = 0
        #: AUD-05. Last finite price seen per symbol, so a dropped bar marks at the last
        #: known level instead of at zero. A stale mark is wrong by the size of one move;
        #: a zero mark is wrong by the whole notional and reads as a total loss.
        self.last_px: dict[str, float] = {}
        #: AUD-09. Alerts are queued and flushed AFTER orders are on the wire. notify() can
        #: block for up to 45 s on the OpenClaw CLI, and it used to run before the
        #: loss-limit flatten was submitted, holding the book open across the alert.
        self._pending_notes: list[str] = []
        self.submit_before_notify = False

    def pending_qty(self) -> dict[str, int]:
        """In-flight signed quantity from the executor, or {} if it cannot report.

        Tolerant on purpose: a replay executor that settles instantly has nothing pending,
        and an executor without the method must degrade to the old behaviour rather than
        crash the trading loop.
        """
        fn = getattr(self.ex, "pending_qty", None)
        if not callable(fn):
            return {}
        try:
            return {s: int(q) for s, q in (fn() or {}).items() if q}
        except Exception:  # noqa: BLE001 - never let bookkeeping stop the loop
            log("pending_qty_error", trace=traceback.format_exc()[-600:])
            return {}

    def marks(self, prices: dict[str, float]) -> tuple[dict[str, float], list[str]]:
        """Usable marks for every open position, and the symbols that have none. AUD-05.

        A price is usable only if it is finite and positive - `if not px` lets NaN through
        (`not nan` is False), which is the same hole that made `math.floor` raise in sizing.
        Symbols never seen at any price are returned separately so the caller can refuse to
        act on a P&L that does not include them.
        """
        marks = dict(self.last_px)
        for sym, px in (prices or {}).items():
            try:
                v = float(px)
            except (TypeError, ValueError):
                continue
            if math.isfinite(v) and v > 0:
                marks[sym] = v
                self.last_px[sym] = v
        unmarked = [s for s, q in self.book.pos.items() if q and s not in marks]
        return marks, unmarked

    def _queue_note(self, text: str) -> None:
        self._pending_notes.append(text)

    def _flush_notes(self) -> None:
        notes, self._pending_notes = self._pending_notes, []
        for text in notes:
            self.submit_before_notify = True
            notify(text)

    def targets_to_orders(self, targets, prices, equity):
        orders = {}
        gross = sum(abs(w) for w in targets.values())
        scale = min(1.0, GROSS_HARD_CAP / gross) if gross > GROSS_HARD_CAP else 1.0
        pending = self.pending_qty()
        for sym in set(targets) | set(self.book.pos) | set(pending):
            px = prices.get(sym)
            # AUD-09: `not px or px <= 0` passes NaN, because `not nan` is False and
            # `nan <= 0` is False. math.floor then raises and the exception skips the whole
            # step - including the end-of-day flatten. isfinite is the actual guard.
            try:
                px = float(px)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(px) or px <= 0:
                continue
            w = max(-PER_SYMBOL_HARD_CAP, min(PER_SYMBOL_HARD_CAP, float(targets.get(sym, 0.0)) * scale))
            tgt = int(math.copysign(math.floor(abs(w) * equity / px), w)) if w else 0
            # AUD-06: what we will hold once the wire clears, not what we hold now. Sizing
            # against book.pos alone resends the same delta every minute until it books.
            cur = self.book.pos.get(sym, 0) + pending.get(sym, 0)
            delta = tgt - cur
            if delta and (abs(delta) * px >= MIN_CHANGE * equity or tgt == 0):
                orders[sym] = delta
        return orders

    def step(self, t: pd.Timestamp, feats: dict[str, pd.DataFrame], prices: dict[str, float], nav: float):
        if self.last_t is not None and t <= self.last_t:
            # same bar seen again (feed not advanced): no new decision, but still mark
            # against last-known prices rather than defaulting absent symbols to zero.
            return self.book.pnl(self.marks(prices)[0])
        self.last_t = t
        if self.nav_open is None:
            self.nav_open = nav
        equity = nav * self.equity_frac
        # 1) settle fills from the previous minute
        for sym, q, px, cost in self.ex.settle(t):
            book_fill(self.book, sym, q, px, cost)
        # AUD-05: mark against last-known prices, and know which positions have no mark.
        marks, unmarked = self.marks(prices)
        pnl = self.book.pnl(marks)
        m = minute_index(t)
        # 2) risk gates
        halted = any(p.exists() for p in HALT_FILES)
        if unmarked:
            # A P&L computed without these is not a P&L, it is a partial sum. Acting on it is
            # exactly the AUD-05 defect: one dropped SMCI bar marked a $30k long at zero,
            # breached the 2.5% limit and flattened the whole book. Report and do not stop.
            log("unmarked_positions", symbols=sorted(unmarked), t=str(t), pnl_partial=pnl)
            self._queue_note(
                f"INTRADAY: no price for {', '.join(sorted(unmarked))} at {t:%H:%M}; "
                f"daily loss limit not evaluated this bar.")
        elif not self.stopped and (pnl <= -DAILY_LOSS_LIMIT * self.nav_open):
            self.stopped = True
            log("loss_limit", pnl=pnl, nav_open=self.nav_open)
            self._queue_note(f"INTRADAY loss limit hit: sleeve P&L {pnl:,.0f} on NAV {self.nav_open:,.0f}. Flattening, done for the day.")
        if halted and not self.stopped:
            self.stopped = True
            log("halt", files=[str(p) for p in HALT_FILES if p.exists()])
            self._queue_note("INTRADAY halted by HALT file; flattening.")
        flatten = self.stopped or m >= flatten_minute_for(t.date())
        # 3) decide
        targets = {}
        if not flatten:
            try:
                targets = self.strategy.decide(t, feats, dict(self.book.pos), equity, self.state, self.params) or {}
                self.decisions += 1
            except Exception as exc:  # noqa: BLE001
                log("decide_error", error=str(exc)[:300], trace=traceback.format_exc()[-1500:])
                targets = {}
        orders = self.targets_to_orders(targets, marks, equity)
        if flatten:
            # AUD-06: net what is already on the wire. A sell sent at 15:38 that has not
            # filled by 15:39 must not be sent again (a double sell), and must not be bought
            # back at 15:40 when it finally books.
            pend = self.pending_qty()
            orders = {}
            for sym in set(self.book.pos) | set(pend):
                effective = self.book.pos.get(sym, 0) + pend.get(sym, 0)
                if effective:
                    orders[sym] = -effective
        if orders:
            log("decision", t=str(t), minute=m, targets=targets, orders=orders, pnl=pnl, equity=equity, mode=self.mode,
                ref={s: round(float(marks[s]), 4) for s in orders if marks.get(s)})
            if not self.dry_run:
                self.ex.submit(orders, t)
        # AUD-09: alerts go out only once the orders are on the wire. notify() can block for
        # up to 45 s and previously ran inside the risk gate above, holding an open book
        # across the call it was alerting about.
        self._flush_notes()
        # 4) periodic report
        if self.last_report is None or (t - self.last_report) >= pd.Timedelta(minutes=30):
            self.last_report = t
            gross_now = sum(abs(q) * marks.get(s, 0.0) for s, q in self.book.pos.items())
            log("snapshot", t=str(t), pnl=pnl, trades=self.book.trades, costs=self.book.costs, gross=gross_now, positions=self.book.pos)
            if self.mode == "live":
                notify(f"INTRADAY {t.strftime('%H:%M')}: P&L {pnl:+,.0f}, trades {self.book.trades}, gross {gross_now:,.0f}, "
                       f"positions {len(self.book.pos)}{' (DRY RUN)' if self.dry_run else ''}"
                       + (f" | UNMARKED: {', '.join(sorted(unmarked))}" if unmarked else ""))
        if self.persist:
            save_book(self.book)
        return pnl


# ----------------------------------------------------------------------------- replay
def replay(strategy, params, day: dt.date, equity_frac: float, nav: float):
    global LOG
    LOG = "intraday-replay"          # replay events go to live/log/intraday-replay-<date>.jsonl, never the live log
    bars = load_universe(UNIVERSE, day - dt.timedelta(days=7), day)
    bars = {s: df for s, df in bars.items() if (df.index.date == day).any()}
    if not bars:
        sys.exit(f"no stored bars for {day}; run scripts/intraday_data.py")
    feats_all = {s: features(df) for s, df in bars.items()}
    ex = SimExecutor({s: df[df.index.date == day] for s, df in bars.items()})
    trader = Trader(strategy, params, equity_frac, Book(), ex, dry_run=False, mode="replay")
    times = sorted(set().union(*[set(df[df.index.date == day].index) for df in bars.values()]))
    pnl = 0.0
    for t in times:
        m = minute_index(t)
        if m >= exit_minute_for(t.date()):
            break
        feats = {}
        prices = {}
        for s, f in feats_all.items():
            upto = f[f.index <= t]
            if len(upto) and upto.index[-1].date() == day:
                feats[s] = upto
                prices[s] = float(upto["c"].iloc[-1])
        pnl = trader.step(t, feats, prices, nav)
    # settle anything pending at the last bar
    for sym, q, px, cost in ex.settle(times[-1]):
        book_fill(trader.book, sym, q, px, cost)
    print(f"replay {day}: P&L {trader.book.pnl({}):+,.0f} on sleeve equity {nav * equity_frac:,.0f}, "
          f"trades {trader.book.trades}, costs {trader.book.costs:,.0f}, decisions {trader.decisions}, "
          f"open positions at end {trader.book.pos or 'none'}")
    return 0


# ----------------------------------------------------------------------------- live
def live(strategy, params, args):
    from ib_async import IB, Stock
    if not args.dry_run and not args.flatten and not APPROVAL.exists():
        print(f"REFUSED: {APPROVAL} missing; running as --dry-run instead")
        args.dry_run = True
    ib = IB()
    ib.connect(args.host, args.port, clientId=args.client_id, timeout=30)
    ib.reqMarketDataType(3)
    account = ib.managedAccounts()[0]
    if not account.startswith("DU"):
        print(f"REFUSED: {account} is not a paper account")
        return 3
    summary = {r.tag: r.value for r in ib.accountSummary(account) if r.currency in ("USD", "BASE", "")}
    nav = float(summary.get("NetLiquidation", 0) or 0)
    contracts = {s: Stock(s, "SMART", "USD") for s in UNIVERSE}
    ib.qualifyContracts(*contracts.values())
    book = load_book()
    ex = LiveExecutor(ib, contracts)
    # AUD-08. Two things, before any path decides what to send.
    # 1) Cancel INTRADAY orders left working from a previous run. An order queued outside RTH
    #    fills at the next open with nothing tracking it, and the sleeve then re-sells it.
    stale = [o for o in ib.reqAllOpenOrders() if getattr(o.order, "orderRef", "") == ORDER_REF]
    for o in stale:
        try:
            ib.cancelOrder(o.order)
        except Exception as exc:  # noqa: BLE001
            log("cancel_failed", id=getattr(o.order, "orderId", None), error=str(exc)[:200])
    if stale:
        ib.sleep(3)
        log("cancelled_stale_orders", count=len(stale),
            ids=[getattr(o.order, "orderId", None) for o in stale])
    # 2) Make the book agree with the account. Every branch below - normal start, --flatten,
    #    --flatten-from-account - then acts on what is actually held.
    acct_now = {p.contract.symbol: int(p.position) for p in ib.positions(account)
                if p.contract.symbol in set(UNIVERSE) and p.position}
    drift = startup_reconcile(book, acct_now, UNIVERSE)
    if drift:
        notify("INTRADAY start-up: book disagreed with the account on "
               + ", ".join(f"{s} book={b} account={a}" for s, b, a in drift)
               + ". Adopted the account.")
    if args.flatten_from_account:
        # Safety net: close every account position in the intraday universe, whatever the book
        # says (the universe is disjoint from the daily sleeve's, so nothing else is touched).
        acct = {p.contract.symbol: int(p.position) for p in ib.positions(account)
                if p.contract.symbol in UNIVERSE and p.position}
        print(f"account intraday positions: {acct or 'none'}; book: {book.pos or 'empty'}")
        log("flatten_from_account", account_positions=acct, book=book.pos)
        if acct:
            ex.submit({s: -q for s, q in acct.items()}, None)
            ib.sleep(25)
            for sym, q, px, cost in ex.settle(None):
                book_fill(book, sym, q, px, cost)
        left = {p.contract.symbol: int(p.position) for p in ib.positions(account) if p.contract.symbol in UNIVERSE and p.position}
        book.pos = {}
        book.cost = {}
        save_book(book)
        print(f"remaining intraday positions: {left or 'none'}; book cleared")
        log("flatten_from_account_done", remaining=left)
        ib.disconnect()
        return 0 if not left else 2
    if args.flatten:
        if book.pos:
            ex.submit({s: -q for s, q in book.pos.items()}, None)
            ib.sleep(20)
            for sym, q, px, cost in ex.settle(None):
                book_fill(book, sym, q, px, cost)
            save_book(book)
        print(f"flattened; book now {book.pos or 'empty'}")
        ib.disconnect()
        return 0
    if book.pos:
        print(f"WARNING: sleeve book not empty at start ({book.pos}); flattening leftovers first")
        log("stale_book", positions=book.pos)
        if not args.dry_run:
            ex.submit({s: -q for s, q in book.pos.items()}, None)
            ib.sleep(15)
            for sym, q, px, cost in ex.settle(None):
                book_fill(book, sym, q, px, cost)
            save_book(book)
    mode = "live"
    trader = Trader(strategy, params, args.equity_frac, book, ex, args.dry_run, mode)
    print(f"account {account} NAV {nav:,.0f} sleeve equity {nav * args.equity_frac:,.0f} "
          f"strategy {args.strategy} universe {len(UNIVERSE)} {'DRY RUN' if args.dry_run else 'LIVE PAPER'}")
    log("start", account=account, nav=nav, equity_frac=args.equity_frac, strategy=args.strategy, dry_run=args.dry_run)
    notify(f"INTRADAY start: {account} NAV {nav:,.0f}, sleeve {nav * args.equity_frac:,.0f}, {args.strategy} on "
           f"{len(UNIVERSE)} names{' (DRY RUN)' if args.dry_run else ''}")
    feed = make_feed(args.feed, ib, contracts)
    print(f"feed: {feed.name}")
    last_minute = None
    delay_warned = False
    while True:
        ib.sleep(1)
        now = dt.datetime.now(ET)
        m = minute_index(pd.Timestamp(now))
        if m >= exit_minute_for(t.date()):
            break
        if now.second < 5 or now.minute == last_minute:
            continue
        last_minute = now.minute
        if not ib.isConnected():
            log("disconnected")
            notify("INTRADAY: Gateway connection lost, reconnecting")
            for _ in range(10):
                try:
                    ib.connect(args.host, args.port, clientId=args.client_id, timeout=30)
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(15)
            if not ib.isConnected():
                notify("INTRADAY: could not reconnect; book left as is")
                break
        cutoff = pd.Timestamp(now.replace(second=0, microsecond=0))  # bars starting before this minute are complete
        try:
            bars = feed.bars(cutoff)
        except Exception as exc:  # noqa: BLE001
            log("feed_error", feed=feed.name, error=str(exc)[:300])
            continue
        feats, prices = {}, {}
        for s, df in bars.items():
            if df.empty or df.index[-1].date() != now.date():
                continue
            feats[s] = features(df)
            prices[s] = float(df["c"].iloc[-1])
        if not feats:
            continue
        t = max(f.index[-1] for f in feats.values())
        delay_min = (cutoff - t).total_seconds() / 60.0 - 1.0
        if delay_min > 3 and not delay_warned:
            delay_warned = True
            log("feed_delayed", feed=feed.name, delay_minutes=delay_min)
            notify(f"INTRADAY warning: {feed.name} bars are {delay_min:.0f} min behind the clock; decisions are stale")
        try:
            trader.step(t, feats, prices, nav)
        except Exception as exc:  # noqa: BLE001
            log("step_error", error=str(exc)[:300], trace=traceback.format_exc()[-1500:])
    # final flatten and report
    if trader.book.pos and not args.dry_run:
        ex.submit({s: -q for s, q in trader.book.pos.items()}, None)
        ib.sleep(20)
        for sym, q, px, cost in ex.settle(None):
            book_fill(trader.book, sym, q, px, cost)
    save_book(trader.book)
    pnl = trader.book.pnl({})
    log("end", pnl=pnl, trades=trader.book.trades, costs=trader.book.costs, positions=trader.book.pos)
    notify(f"INTRADAY end of day: P&L {pnl:+,.0f}, trades {trader.book.trades}, costs {trader.book.costs:,.0f}, "
           f"open {trader.book.pos or 'none'}")
    print(f"end of day: P&L {pnl:+,.0f}, trades {trader.book.trades}, costs {trader.book.costs:,.0f}, open {trader.book.pos or 'none'}")
    ib.disconnect()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strategy", default="active")
    ap.add_argument("--params", help="JSON overrides")
    ap.add_argument("--equity-frac", type=float, default=1.0, help="fraction of NAV this sleeve may use as its equity base")
    ap.add_argument("--replay", help="YYYY-MM-DD: offline replay on stored bars")
    ap.add_argument("--nav", type=float, default=1_000_000, help="NAV assumed in replay")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--flatten", action="store_true")
    ap.add_argument("--flatten-from-account", action="store_true",
                    help="close every account position in the intraday universe regardless of the book, then clear the book")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--client-id", type=int, default=71)
    ap.add_argument("--feed", choices=["auto", "ib", "yahoo"], default="auto",
                    help="bar feed: auto measures IBKR's delay and falls back to Yahoo when bars are stale")
    args = ap.parse_args()
    strategy = load_strategy(args.strategy)
    params = {**strategy.PARAMS, **(json.loads(args.params) if args.params else {})}
    if args.replay:
        return replay(strategy, params, dt.date.fromisoformat(args.replay), args.equity_frac, args.nav)
    return live(strategy, params, args)


def guarded_main() -> int:
    """Run `main`, and make sure an unhandled exception is never silent. AUD-09.

    A yfinance outage raises `KeyError` deep in the feed, the process dies, and the only
    evidence is a Task Scheduler exit code nobody reads - while a position sits open with no
    loop left to flatten it. The traceback goes to the trading log and the alert channel, and
    exit code 4 distinguishes "crashed" from the meaningful codes (2 halted, 3 refused).
    """
    try:
        return main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - the whole point is to catch everything
        trace = traceback.format_exc()
        try:
            log("crashed", error=f"{type(exc).__name__}: {exc}"[:300], trace=trace[-2000:])
        except Exception:  # noqa: BLE001
            pass
        try:
            _notify(f"INTRADAY CRASHED: {type(exc).__name__}: {str(exc)[:200]}. "
                    f"Positions may be open - check the account.", LOG)
        except Exception:  # noqa: BLE001
            pass
        print(trace, file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(guarded_main())
