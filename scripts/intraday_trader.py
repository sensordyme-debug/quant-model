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
                             log_event, notify, slippage)

sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
from base import features  # noqa: E402

APPROVAL = LIVE / "APPROVED_PAPER.md"
HALT_FILES = [LIVE / "HALT", LIVE / "HALT_INTRADAY"]
BOOK_FILE = LIVE / "state" / "intraday_book.json"
ORDER_REF = "INTRADAY"
LOG = "intraday"


def log(kind, **f):
    log_event(LOG, kind, **f)


def load_strategy(name: str):
    path = REPO / "algorithms" / "intraday" / name / "signal.py"
    spec = importlib.util.spec_from_file_location(f"intraday_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def minute_index(t: pd.Timestamp) -> int:
    return int((t.hour - 9) * 60 + t.minute - 30)


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
            return Book.from_json(d)
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
        for s, q in orders.items():
            o = self.MarketOrder("BUY" if q > 0 else "SELL", abs(q))
            o.orderRef = ORDER_REF
            o.outsideRth = False
            tr = self.ib.placeOrder(self.contracts[s], o)
            self.open.append(tr)
            log("order", symbol=s, qty=q, id=tr.order.orderId)

    def settle(self, t) -> list[tuple[str, int, float, float]]:
        """Collect fills from orders sent earlier; returns (sym, signed_qty, avg_px, commission)."""
        self.ib.sleep(3)
        fills, still = [], []
        for tr in self.open:
            st = tr.orderStatus
            done = st.status in ("Filled", "Cancelled", "Inactive", "ApiCancelled")
            if st.filled and st.status == "Filled":
                q = int(st.filled) * (1 if tr.order.action == "BUY" else -1)
                comm = sum((f.commissionReport.commission or 0.0) for f in tr.fills if f.commissionReport) or commission(q, st.avgFillPrice)
                fills.append((tr.contract.symbol, q, float(st.avgFillPrice), float(comm)))
                log("fill", symbol=tr.contract.symbol, qty=q, avg_price=st.avgFillPrice, commission=comm, status=st.status)
            elif not done:
                still.append(tr)
            else:
                log("order_dead", symbol=tr.contract.symbol, status=st.status, filled=st.filled)
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
    delay = (now - latest).total_seconds() / 60.0 - 1.0 if latest is not None else 99.0
    log("feed_probe", ib_delay_minutes=delay)
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
        self.persist = (mode == "live")
        self.state: dict = {}
        self.stopped = False
        self.nav_open = None
        self.last_report = None
        self.last_t = None
        self.decisions = 0

    def targets_to_orders(self, targets, prices, equity):
        orders = {}
        gross = sum(abs(w) for w in targets.values())
        scale = min(1.0, GROSS_HARD_CAP / gross) if gross > GROSS_HARD_CAP else 1.0
        for sym in set(targets) | set(self.book.pos):
            px = prices.get(sym)
            if not px or px <= 0:
                continue
            w = max(-PER_SYMBOL_HARD_CAP, min(PER_SYMBOL_HARD_CAP, float(targets.get(sym, 0.0)) * scale))
            tgt = int(math.copysign(math.floor(abs(w) * equity / px), w)) if w else 0
            cur = self.book.pos.get(sym, 0)
            delta = tgt - cur
            if delta and (abs(delta) * px >= MIN_CHANGE * equity or tgt == 0):
                orders[sym] = delta
        return orders

    def step(self, t: pd.Timestamp, feats: dict[str, pd.DataFrame], prices: dict[str, float], nav: float):
        if self.last_t is not None and t <= self.last_t:
            return self.book.pnl(prices)          # same bar seen again (feed not advanced): no new decision
        self.last_t = t
        if self.nav_open is None:
            self.nav_open = nav
        equity = nav * self.equity_frac
        # 1) settle fills from the previous minute
        for sym, q, px, cost in self.ex.settle(t):
            book_fill(self.book, sym, q, px, cost)
        pnl = self.book.pnl(prices)
        m = minute_index(t)
        # 2) risk gates
        halted = any(p.exists() for p in HALT_FILES)
        if not self.stopped and (pnl <= -DAILY_LOSS_LIMIT * self.nav_open):
            self.stopped = True
            log("loss_limit", pnl=pnl, nav_open=self.nav_open)
            notify(f"INTRADAY loss limit hit: sleeve P&L {pnl:,.0f} on NAV {self.nav_open:,.0f}. Flattening, done for the day.")
        if halted and not self.stopped:
            self.stopped = True
            log("halt", files=[str(p) for p in HALT_FILES if p.exists()])
            notify("INTRADAY halted by HALT file; flattening.")
        flatten = self.stopped or m >= FLATTEN_MINUTE
        # 3) decide
        targets = {}
        if not flatten:
            try:
                targets = self.strategy.decide(t, feats, dict(self.book.pos), equity, self.state, self.params) or {}
                self.decisions += 1
            except Exception as exc:  # noqa: BLE001
                log("decide_error", error=str(exc)[:300], trace=traceback.format_exc()[-1500:])
                targets = {}
        orders = self.targets_to_orders(targets, prices, equity)
        if flatten and self.book.pos:
            orders = {s: -q for s, q in self.book.pos.items()}
        if orders:
            log("decision", t=str(t), minute=m, targets=targets, orders=orders, pnl=pnl, equity=equity, mode=self.mode)
            if not self.dry_run:
                self.ex.submit(orders, t)
        # 4) periodic report
        if self.last_report is None or (t - self.last_report) >= pd.Timedelta(minutes=30):
            self.last_report = t
            gross_now = sum(abs(q) * prices.get(s, 0.0) for s, q in self.book.pos.items())
            log("snapshot", t=str(t), pnl=pnl, trades=self.book.trades, costs=self.book.costs, gross=gross_now, positions=self.book.pos)
            if self.mode == "live":
                notify(f"INTRADAY {t.strftime('%H:%M')}: P&L {pnl:+,.0f}, trades {self.book.trades}, gross {gross_now:,.0f}, "
                       f"positions {len(self.book.pos)}{' (DRY RUN)' if self.dry_run else ''}")
        if self.persist:
            save_book(self.book)
        return pnl


# ----------------------------------------------------------------------------- replay
def replay(strategy, params, day: dt.date, equity_frac: float, nav: float):
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
        if m >= EXIT_MINUTE:
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
        if m >= EXIT_MINUTE:
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


if __name__ == "__main__":
    sys.exit(main())
