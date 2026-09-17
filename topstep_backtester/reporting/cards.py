"""The executive result card: the smallest set of numbers nobody may quote without.

WHAT GOES ON A CARD
-------------------
The figures that decide whether a result means anything, arranged so the disqualifying ones
cannot be scrolled past. Net P&L is near the bottom on purpose. A strategy that breached the
trailing loss limit has no P&L worth discussing, and a card that leads with the profit
invites exactly that conversation.

THE PROVISIONAL FLAG
--------------------
Upstream sets ``provisional`` on its summary stats when the sample is too small for the
statistics to be load-bearing, and its Monte Carlo carries the same flag plus
``source_truncated``. Those flags are propagated here verbatim and rendered as a banner
rather than a footnote. A provisional result is not a weak result - it is a result whose
error bars have not been earned, and the distinction is the whole difference between
research and wishful thinking.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from topstep_backtester.reporting.unmodeled import UNMODELED


def _money(value: Any) -> str:
    if value is None:
        return UNMODELED
    return f"${Decimal(str(value)):,.2f}"


def _pct(value: Any) -> str:
    if value is None:
        return UNMODELED
    return f"{Decimal(str(value)) * 100:.1f}%"


@dataclass(frozen=True)
class ExecutiveCard:
    """One backtest, reduced to what a reader must see before any other number."""

    run_id: str
    spec_id: str
    instrument: str
    account_profile_id: str
    execution_profile_id: str
    period: str
    bars: int

    verdict: str
    verdict_reason: str
    breached: bool
    breach_detail: str

    days_traded: int
    trade_count: int
    closed_trades: int
    win_rate: Any
    net_pnl: Any
    ending_balance: Any
    best_day: Any
    consistency_headroom: Any
    max_drawdown: Any
    intraday_trailing_drawdown: Any

    provisional: bool
    reconciled: bool
    reconciliation_note: str

    monte_carlo_pass_probability: Any = None
    monte_carlo_provisional: Any = None
    monte_carlo_note: str = UNMODELED

    def banner(self) -> str:
        """The one line that must appear above everything else."""
        flags: list[str] = []
        if self.breached:
            flags.append("ACCOUNT BREACHED")
        if not self.reconciled:
            flags.append("RECONCILIATION FAILED")
        if self.provisional:
            flags.append("PROVISIONAL - SAMPLE TOO SMALL FOR THE STATISTICS")
        if not flags:
            return "no disqualifying flags raised"
        return " | ".join(flags)

    def as_rows(self) -> list[tuple[str, str]]:
        """Ordered deliberately: disqualifiers first, profit last."""
        return [
            ("verdict", f"{self.verdict} - {self.verdict_reason}"),
            ("breached", "YES - " + self.breach_detail if self.breached else "no"),
            ("reconciled vs independent arithmetic",
             "yes" if self.reconciled else f"NO - {self.reconciliation_note}"),
            ("provisional", "YES - statistics not load-bearing" if self.provisional else "no"),
            ("period", self.period),
            ("bars", f"{self.bars:,}"),
            ("days traded", str(self.days_traded)),
            ("fills", str(self.trade_count)),
            ("closed round trips", str(self.closed_trades)),
            ("win rate", _pct(self.win_rate)),
            ("max drawdown", _money(self.max_drawdown)),
            ("intraday trailing drawdown", _money(self.intraday_trailing_drawdown)),
            ("best day", _money(self.best_day)),
            ("consistency headroom", _money(self.consistency_headroom)),
            ("Monte Carlo P(pass)",
             _pct(self.monte_carlo_pass_probability)
             if self.monte_carlo_pass_probability is not None
             else self.monte_carlo_note),
            ("net P&L", _money(self.net_pnl)),
            ("ending balance", _money(self.ending_balance)),
        ]

    def to_markdown(self) -> str:
        lines = [
            f"### {self.spec_id}",
            "",
            f"**{self.banner()}**",
            "",
            f"`run_id {self.run_id}` | {self.instrument} | "
            f"{self.account_profile_id} | {self.execution_profile_id}",
            "",
            "| | |",
            "|---|---|",
        ]
        lines.extend(f"| {label} | {value} |" for label, value in self.as_rows())
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "spec_id": self.spec_id,
            "instrument": self.instrument,
            "account_profile_id": self.account_profile_id,
            "execution_profile_id": self.execution_profile_id,
            "period": self.period,
            "bars": self.bars,
            "verdict": self.verdict,
            "verdict_reason": self.verdict_reason,
            "breached": self.breached,
            "breach_detail": self.breach_detail,
            "days_traded": self.days_traded,
            "trade_count": self.trade_count,
            "closed_trades": self.closed_trades,
            "win_rate": None if self.win_rate is None else str(self.win_rate),
            "net_pnl": None if self.net_pnl is None else str(self.net_pnl),
            "ending_balance": None if self.ending_balance is None else str(self.ending_balance),
            "best_day": None if self.best_day is None else str(self.best_day),
            "consistency_headroom": (
                None if self.consistency_headroom is None else str(self.consistency_headroom)
            ),
            "max_drawdown": None if self.max_drawdown is None else str(self.max_drawdown),
            "provisional": self.provisional,
            "reconciled": self.reconciled,
            "banner": self.banner(),
        }


def card_from_run(run: Any, *, monte_carlo: Any = None) -> ExecutiveCard:
    """Project a ``RunResult`` onto a card. Reads only; computes nothing."""
    result = run.result
    stats = run.stats
    breach = result.breach
    drawdown = getattr(stats, "drawdown", None)

    return ExecutiveCard(
        run_id=run.run_id,
        spec_id=run.spec.spec_id,
        instrument=run.bar_report.instrument,
        account_profile_id=run.account_profile.profile_id,
        execution_profile_id=run.execution_profile.profile_id,
        period=f"{run.bar_report.first_ts_event_utc} .. {run.bar_report.last_ts_init_utc}",
        bars=run.bar_report.bars_out,
        verdict=str(getattr(result.verdict, "name", result.verdict)),
        verdict_reason=result.reason,
        breached=breach is not None,
        breach_detail="" if breach is None else str(breach),
        days_traded=result.days_traded,
        trade_count=result.trade_count,
        closed_trades=getattr(stats, "closed_trades", 0),
        win_rate=getattr(stats, "win_rate", None),
        net_pnl=getattr(stats, "net_pnl", None),
        ending_balance=result.ending_balance,
        best_day=result.best_day,
        consistency_headroom=getattr(stats, "consistency_headroom", None),
        max_drawdown=getattr(stats, "max_drawdown", None),
        intraday_trailing_drawdown=(
            None if drawdown is None else getattr(drawdown, "intraday_trailing", None)
        ),
        provisional=bool(getattr(stats, "provisional", False)),
        reconciled=run.reconciled,
        reconciliation_note=(
            "" if run.reconciled
            else f"net delta {run.reconciliation.net_delta}"
        ),
        monte_carlo_pass_probability=(
            None if monte_carlo is None else monte_carlo.pass_probability
        ),
        monte_carlo_provisional=(
            None if monte_carlo is None else getattr(monte_carlo, "provisional", None)
        ),
        monte_carlo_note="not run" if monte_carlo is None else "",
    )


__all__ = ["ExecutiveCard", "card_from_run"]
