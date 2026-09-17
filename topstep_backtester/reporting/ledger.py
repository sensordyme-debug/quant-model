"""Reconstruct the run: every trade, every month, and the account path day by day.

WHY RECONSTRUCTION IS A REQUIREMENT AND NOT A FEATURE
-----------------------------------------------------
A headline P&L that cannot be decomposed into the trades that produced it is not a result,
it is an assertion. Three reconstructions matter, and each answers a different challenge:

    the trade ledger    "which trades made this number" - one row per round trip, with the
                        engine's own entry, exit, gross, costs and R multiple
    the monthly table   "was it one good month or twelve" - the single most effective check
                        against a curve that is really one lucky week
    the account path    "what did the account look like on the worst day" - balance, the
                        trailing floor, and the headroom between them, per trading day

The third is the one prop-firm work lives or dies on. A strategy can end a Combine well up
and still have been two ticks from liquidation in week one, and nothing in a summary
statistic shows that. ``account_path`` puts the floor next to the balance on every day.

EVERY FIGURE HERE COMES FROM THE ENGINE
---------------------------------------
Nothing in this module computes P&L. The round trips, the day records and the trailing floor
are read off ``BacktestResult`` exactly as upstream produced them; this module groups and
formats. Grouping is the only arithmetic, and the monthly totals are checked against the
run's own net P&L by :func:`reconcile_monthly` so a grouping bug cannot pass silently.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


def _et_date(ts_ns: int) -> dt.date:
    """A nanosecond stamp as its UTC calendar date.

    Deliberately NOT converted to a venue clock. The engine already assigned each fill to a
    trading day through its own ``trading_day_of``, and the day records carry that
    assignment; re-deriving a session date here with a different rule would produce a second,
    disagreeing calendar. Used only for ordering and display of individual trades.
    """
    return dt.datetime.fromtimestamp(ts_ns / 1e9, dt.UTC).date()


@dataclass(frozen=True)
class TradeRow:
    """One closed round trip, exactly as the engine booked it."""

    index: int
    contract_id: str
    direction: int
    opened_utc: str
    closed_utc: str
    qty: int
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    initial_risk: Decimal | None
    r_multiple: Decimal | None
    duration_seconds: float

    @property
    def side(self) -> str:
        return "long" if self.direction > 0 else "short"

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "contract_id": self.contract_id,
            "side": self.side,
            "opened_utc": self.opened_utc,
            "closed_utc": self.closed_utc,
            "qty": self.qty,
            "gross_pnl": str(self.gross_pnl),
            "costs": str(self.costs),
            "net_pnl": str(self.net_pnl),
            "initial_risk": None if self.initial_risk is None else str(self.initial_risk),
            "r_multiple": None if self.r_multiple is None else str(self.r_multiple),
            "duration_seconds": self.duration_seconds,
        }


def trade_ledger(result: Any) -> tuple[TradeRow, ...]:
    """One row per closed round trip."""
    rows: list[TradeRow] = []
    for index, trip in enumerate(result.round_trips, start=1):
        opened = dt.datetime.fromtimestamp(trip.opened_ts_ns / 1e9, dt.UTC)
        closed = dt.datetime.fromtimestamp(trip.closed_ts_ns / 1e9, dt.UTC)
        rows.append(
            TradeRow(
                index=index,
                contract_id=trip.contract_id,
                direction=trip.direction,
                opened_utc=opened.isoformat(),
                closed_utc=closed.isoformat(),
                qty=trip.max_qty,
                gross_pnl=trip.gross_pnl,
                costs=trip.costs,
                net_pnl=trip.net_pnl,
                initial_risk=trip.initial_risk,
                r_multiple=trip.r_multiple,
                duration_seconds=(trip.closed_ts_ns - trip.opened_ts_ns) / 1e9,
            )
        )
    return tuple(rows)


@dataclass(frozen=True)
class MonthRow:
    month: str
    trading_days: int
    days_with_a_trade: int
    net_pnl: Decimal
    best_day: Decimal
    worst_day: Decimal
    ending_balance: Decimal

    def as_dict(self) -> dict[str, Any]:
        return {
            "month": self.month,
            "trading_days": self.trading_days,
            "days_with_a_trade": self.days_with_a_trade,
            "net_pnl": str(self.net_pnl),
            "best_day": str(self.best_day),
            "worst_day": str(self.worst_day),
            "ending_balance": str(self.ending_balance),
        }


def monthly(result: Any) -> tuple[MonthRow, ...]:
    """Month-by-month P&L, grouped from the engine's own day records.

    The grouping key is the day the ENGINE assigned, not a date this module re-derived, so
    a session that spans midnight lands in the month the engine put it in.
    """
    buckets: dict[str, list[Any]] = {}
    for record in result.day_records:
        buckets.setdefault(f"{record.day.year:04d}-{record.day.month:02d}", []).append(record)

    rows: list[MonthRow] = []
    for month in sorted(buckets):
        records = sorted(buckets[month], key=lambda r: r.day)
        pnls = [r.day_pnl for r in records]
        rows.append(
            MonthRow(
                month=month,
                trading_days=len(records),
                days_with_a_trade=sum(1 for r in records if r.had_trade),
                net_pnl=sum(pnls, Decimal(0)),
                best_day=max(pnls) if pnls else Decimal(0),
                worst_day=min(pnls) if pnls else Decimal(0),
                ending_balance=records[-1].eod_balance,
            )
        )
    return tuple(rows)


def reconcile_monthly(result: Any, rows: Sequence[MonthRow]) -> tuple[bool, Decimal]:
    """Do the monthly totals add back up to the run's own total profit?

    A grouping bug is easy to introduce and invisible in a table that looks plausible. This
    is the check that makes the monthly view trustworthy rather than decorative.
    """
    summed = sum((row.net_pnl for row in rows), Decimal(0))
    expected = result.ending_balance - result.starting_balance
    return summed == expected, summed - expected


@dataclass(frozen=True)
class AccountDay:
    """One trading day of the prop-firm account, with the floor beside the balance."""

    day: dt.date
    eod_balance: Decimal
    day_pnl: Decimal
    floor_after: Decimal
    had_trade: bool

    @property
    def headroom(self) -> Decimal:
        """How far the closing balance sat above the trailing liquidation floor."""
        return self.eod_balance - self.floor_after

    def as_dict(self) -> dict[str, Any]:
        return {
            "day": self.day.isoformat(),
            "eod_balance": str(self.eod_balance),
            "day_pnl": str(self.day_pnl),
            "floor_after": str(self.floor_after),
            "headroom": str(self.headroom),
            "had_trade": self.had_trade,
        }


def account_path(result: Any) -> tuple[AccountDay, ...]:
    """The Topstep account, day by day: balance, trailing floor, and the gap between."""
    return tuple(
        AccountDay(
            day=record.day,
            eod_balance=record.eod_balance,
            day_pnl=record.day_pnl,
            floor_after=record.floor_after,
            had_trade=record.had_trade,
        )
        for record in sorted(result.day_records, key=lambda r: r.day)
    )


def worst_headroom(path: Sequence[AccountDay]) -> AccountDay | None:
    """The day the account came closest to liquidation.

    Reported even on a profitable run, because "ended up $4,000" and "was $80 from
    liquidation in week one" are both true of the same equity curve and only one of them
    tells you whether to trade it.
    """
    return min(path, key=lambda day: day.headroom) if path else None


def markdown_trades(rows: Sequence[TradeRow], *, limit: int | None = None) -> str:
    shown = rows if limit is None else rows[:limit]
    lines = [
        "| # | side | opened (UTC) | closed (UTC) | qty | gross | costs | net | R |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in shown:
        r = "-" if row.r_multiple is None else f"{row.r_multiple:.2f}"
        lines.append(
            f"| {row.index} | {row.side} | {row.opened_utc} | {row.closed_utc} | {row.qty} | "
            f"${row.gross_pnl:,.2f} | ${row.costs:,.2f} | ${row.net_pnl:,.2f} | {r} |"
        )
    if limit is not None and len(rows) > limit:
        lines.append(f"| ... | _{len(rows) - limit} more trades not shown_ | | | | | | | |")
    return "\n".join(lines)


def markdown_monthly(rows: Sequence[MonthRow]) -> str:
    lines = [
        "| month | trading days | days traded | net P&L | best day | worst day | "
        "ending balance |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.month} | {row.trading_days} | {row.days_with_a_trade} | "
            f"${row.net_pnl:,.2f} | ${row.best_day:,.2f} | ${row.worst_day:,.2f} | "
            f"${row.ending_balance:,.2f} |"
        )
    return "\n".join(lines)


def markdown_account_path(path: Sequence[AccountDay], *, limit: int | None = None) -> str:
    shown = path if limit is None else path[:limit]
    lines = [
        "| day | day P&L | EOD balance | trailing floor | headroom | traded |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for day in shown:
        lines.append(
            f"| {day.day.isoformat()} | ${day.day_pnl:,.2f} | ${day.eod_balance:,.2f} | "
            f"${day.floor_after:,.2f} | ${day.headroom:,.2f} | "
            f"{'yes' if day.had_trade else 'no'} |"
        )
    if limit is not None and len(path) > limit:
        lines.append(f"| ... | _{len(path) - limit} more days not shown_ | | | | |")
    return "\n".join(lines)


__all__ = [
    "AccountDay",
    "MonthRow",
    "TradeRow",
    "account_path",
    "markdown_account_path",
    "markdown_monthly",
    "markdown_trades",
    "monthly",
    "reconcile_monthly",
    "trade_ledger",
    "worst_headroom",
]
