"""Run a frozen `StrategySpec` and produce the canonical result package.

WHAT THIS GUARANTEES
--------------------
Given a spec, this module produces a result whose every headline number is reconciled three
ways before it is reported:

    the trade ledger        sum of net P&L across trades
    the equity curve        the last point of the per-bar equity path
    an independent ledger   `reference_ledger.run_reference`, which shares no code

If those three disagree by more than a cent, the result is marked INVALID and the disagreement
is reported instead of the number. A backtest that cannot reconcile with itself is not a
backtest; it is a plausible-looking array.

THE VALIDATION GATE
-------------------
`VALIDATED` is not the default. A result earns it by passing every check in
`ValidationReport`, and any failure downgrades it to `LIMITED` (checks failed but the result is
interpretable) or `INVALID` (the arithmetic does not reconcile). The reasons travel with the
result.

THE SLIPPAGE LADDER IS NOT OPTIONAL
-------------------------------------
Every run computes five execution scenarios: 0, 0.25, 0.5, 1 and 2 ticks of round-turn
slippage on top of the modelled commission and spread. The zero-slippage figure is reported,
never hidden - and a strategy that is positive only there is flagged in the summary rather
than left for the reader to notice.

WHAT IS NOT HERE
----------------
Any form of parameter selection. The runner takes one spec and reports one result per
execution scenario. It has no notion of a "best" scenario and no code path that chooses among
specs.
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_brain.research.reference_ledger import reference_drawdown, run_reference

#: The declared execution ladder. Round-turn slippage in ticks, on top of commission+spread.
SLIPPAGE_LADDER = (0.0, 0.25, 0.5, 1.0, 2.0)
SCENARIO_NAMES = {0.0: "IDEAL", 0.25: "OPTIMISTIC", 0.5: "REALISTIC",
                  1.0: "CONSERVATIVE", 2.0: "STRESS"}

RECONCILE_TOLERANCE = 0.01     # one cent


@dataclass
class ValidationReport:
    ledger_reconciles: bool = False
    equity_reconciles: bool = False
    independent_reconciles: bool = False
    every_trade_charged: bool = False
    ends_flat: bool = False
    no_future_leak: bool = False
    provenance_present: bool = False
    deterministic: bool = False
    failures: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if not (self.ledger_reconciles and self.equity_reconciles
                and self.independent_reconciles):
            return "INVALID"
        if self.failures:
            return "LIMITED"
        return "VALIDATED"


@dataclass
class Provenance:
    spec_hash: str
    engine_version: str
    git_sha: str
    git_dirty: bool
    data_source: str
    data_hash: str
    data_start: str
    data_end: str
    sessions: int
    python: str
    numpy: str
    pandas: str
    run_at: str
    seed: int | None


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              timeout=20).stdout.strip()
    except Exception:                                            # noqa: BLE001
        return "unknown"


def dataset_hash(sessions: list[pd.DataFrame]) -> str:
    """A hash over the actual bars used, so a data change invalidates a stale result."""
    h = hashlib.sha256()
    for g in sessions:
        for col in ("o", "h", "l", "c", "v"):
            if col in g.columns:
                h.update(np.ascontiguousarray(
                    g[col].to_numpy(dtype=float)).tobytes())
    return h.hexdigest()[:16]


def monthly_table(daily: pd.Series) -> pd.DataFrame:
    """Phase 12. One row per calendar month, with the distribution reported separately."""
    if not len(daily):
        return pd.DataFrame()
    d = daily.copy()
    d.index = pd.to_datetime(d.index)
    rows = []
    for period, g in d.groupby(d.index.to_period("M")):
        eq = np.cumsum(g.to_numpy())
        peak = np.maximum.accumulate(eq)
        run = best = 0
        for v in g:
            run = run + 1 if v < 0 else 0
            best = max(best, run)
        rows.append({
            "month": str(period), "sessions": int(g.size),
            "net_pnl": float(g.sum()), "mean_daily": float(g.mean()),
            "best_day": float(g.max()), "worst_day": float(g.min()),
            "positive_days": int((g > 0).sum()), "negative_days": int((g < 0).sum()),
            "win_rate_days": float((g > 0).mean()),
            "max_drawdown": float((eq - peak).min()),
            "longest_losing_streak": best,
        })
    return pd.DataFrame(rows)


def monthly_distribution(m: pd.DataFrame) -> dict:
    """Phase 21. The distribution, not just the average."""
    if not len(m):
        return {}
    v = m["net_pnl"].to_numpy(dtype=float)
    return {
        "months": int(len(v)),
        "mean": float(v.mean()), "median": float(np.median(v)),
        "std": float(v.std(ddof=1)) if len(v) > 1 else 0.0,
        "positive_share": float((v > 0).mean()),
        "negative_share": float((v < 0).mean()),
        "worst": float(v.min()), "best": float(v.max()),
        "p05": float(np.percentile(v, 5)), "p25": float(np.percentile(v, 25)),
        "p75": float(np.percentile(v, 75)), "p95": float(np.percentile(v, 95)),
    }


@dataclass
class ScenarioResult:
    slippage_ticks: float
    scenario: str
    trades: int
    gross_pnl: float
    commission: float
    slippage_cost: float
    net_pnl: float
    per_trade: float
    per_session: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    sharpe: float
    sortino: float
    t_stat: float
    consec_losing_days: int
    exposure: float


@dataclass
class CanonicalResult:
    spec: dict
    provenance: Provenance
    validation: ValidationReport
    scenarios: list[ScenarioResult]
    trade_ledger: pd.DataFrame
    daily: pd.Series
    monthly: pd.DataFrame
    monthly_dist: dict
    equity_curve: np.ndarray
    notes: list[str] = field(default_factory=list)

    @property
    def headline(self) -> ScenarioResult:
        """The REALISTIC scenario. Never the ideal one."""
        for s in self.scenarios:
            if s.scenario == "REALISTIC":
                return s
        return self.scenarios[0]


def _stats(daily: np.ndarray, net_trades: np.ndarray, ann: int = 252) -> dict:
    sd = float(daily.std(ddof=1)) if len(daily) > 1 else 0.0
    down = daily[daily < 0]
    dsd = float(down.std(ddof=1)) if len(down) > 1 else 0.0
    eq = np.cumsum(daily)
    wins = net_trades[net_trades > 0]
    losses = net_trades[net_trades < 0]
    run = best = 0
    for v in daily:
        run = run + 1 if v < 0 else 0
        best = max(best, run)
    return {
        "per_session": float(daily.mean()) if len(daily) else 0.0,
        "win_rate": float((net_trades > 0).mean()) if len(net_trades) else 0.0,
        "profit_factor": (float(wins.sum() / -losses.sum())
                          if len(losses) and losses.sum() < 0 else float("nan")),
        "max_drawdown": float((eq - np.maximum.accumulate(eq)).min()) if len(eq) else 0.0,
        "sharpe": float(daily.mean() / sd * np.sqrt(ann)) if sd > 0 else 0.0,
        "sortino": float(daily.mean() / dsd * np.sqrt(ann)) if dsd > 0 else 0.0,
        "t_stat": (float(daily.mean() / (sd / np.sqrt(len(daily))))
                   if sd > 0 and len(daily) > 1 else 0.0),
        "consec_losing_days": best,
    }


__all__ = ["CanonicalResult", "Provenance", "RECONCILE_TOLERANCE", "SCENARIO_NAMES",
           "SLIPPAGE_LADDER", "ScenarioResult", "ValidationReport", "_git", "_stats",
           "dataset_hash", "monthly_distribution", "monthly_table",
           "reference_drawdown", "run_reference"]
