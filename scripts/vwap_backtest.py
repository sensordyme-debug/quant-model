"""THE FIRST HISTORICAL RUN of VWAP_PULLBACK V1.0.0_FROZEN. Measurement, not development.

    python scripts/vwap_backtest.py --instrument NQ
    python scripts/vwap_backtest.py --all --out research/vwap_v1

Nothing here optimises, tunes, filters, or selects. The frozen spec is loaded, the certified
anchored data path supplies the bars, and every execution profile on the declared ladder is
run. A parameter is never read from the command line, because a parameter that can be passed
is a parameter that can be swept.

WHAT THIS PRODUCES
--------------------
    ledger      one row per trade, with every field the result is reconstructed from
    daily       one row per session: realized P&L, the intraday mark path, governor events
    summary     the statistics, all derived FROM the ledger and never computed beside it
    manifest    spec hash, dataset id, profile hash, git sha, environment, result hashes

THE ONE-LEDGER RULE
---------------------
Every number in the report - equity, drawdown, monthly table, Topstep twin, Monte Carlo -
is derived from the ledger this script writes. There is no second P&L calculation anywhere,
because two calculations that agree prove nothing and two that disagree are found late.
`scripts/vwap_reconcile.py` is the exception that proves it: an INDEPENDENT reimplementation
whose only job is to disagree if the ledger is wrong.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from quant_brain.strategies.vwap_pullback.data import load_anchored  # noqa: E402
from quant_brain.strategies.vwap_pullback.engine import (  # noqa: E402
    EXIT_HARD_FLATTEN,
    EXIT_KILLSWITCH,
    EXIT_STALL,
    EXIT_STOP,
    EXIT_TARGET,
    Engine,
)
from quant_brain.strategies.vwap_pullback.indicators import trading_day  # noqa: E402
from quant_brain.strategies.vwap_pullback.spec import (  # noqa: E402
    EXECUTION_LADDER,
    FROZEN,
    FROZEN_MNQ,
    TIMEZONE,
    VERSION,
)

STORE = REPO / "data" / "futures"
SPECS = {"NQ": FROZEN, "MNQ": FROZEN_MNQ}
STARTING_BALANCE = 50_000.0

EXIT_REASONS = (EXIT_TARGET, EXIT_STOP, EXIT_KILLSWITCH, EXIT_HARD_FLATTEN, EXIT_STALL)


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                              timeout=20, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):          # pragma: no cover
        return ""


def _hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _et(when: dt.datetime) -> dt.datetime:
    return when.astimezone(TIMEZONE)


# ======================================================================================
# THE RUN
# ======================================================================================

def run_one(instrument: str, profile, sessions) -> dict:
    """Feed every usable session through the engine under ONE execution profile.

    The engine is constructed once and fed the whole history in order, because its governor,
    its VWAP and its halt state are all per-day and roll at 18:00 - restarting it per session
    would reset state the specification says carries.
    """
    spec = dataclasses.replace(SPECS[instrument], execution=profile)
    eng = Engine(spec=spec)

    #: Per-session bookkeeping. `marks` is the within-session equity path the Topstep twin
    #: needs: realized P&L after each closed trade, plus the running unrealized mark at the
    #: adverse intrabar extreme while a position is open. Built HERE from the engine's own
    #: state rather than reconstructed later from the ledger, because the unrealized part
    #: does not exist in the ledger at all.
    daily: list[dict] = []
    per_trade_bars: dict[int, list] = {}
    bar_lookup: dict[dt.datetime, object] = {}

    t0 = time.perf_counter()
    for s in sessions:
        realized = 0.0
        marks: list[float] = []
        entered = exited = 0
        governor_events: list[str] = []
        before = len(eng.trades)
        for bar in s.bars:
            bar_lookup[bar.timestamp] = bar
            out = eng.on_bar(bar)
            if out.entered:
                entered += 1
            if out.exited:
                exited += 1
            if eng.position is not None:
                p = eng.position
                adverse = bar.low if p.direction > 0 else bar.high
                unreal = (adverse - p.fill_price) * p.direction * spec.point_value
                marks.append(realized + unreal)
            realized = sum(t.net_pnl for t in eng.trades[before:])
            marks.append(realized)
        governor_events = list(eng.governor.events)
        eng.governor.events.clear()
        trades = eng.trades[before:]
        daily.append({
            "trading_day": str(s.trading_day),
            "instrument": instrument,
            "contract": s.contract,
            "bars": len(s.bars),
            "trades": len(trades),
            "entries": entered,
            "exits": exited,
            "gross_pnl": sum(t.gross_pnl for t in trades),
            "commission": sum(t.commission_and_spread for t in trades),
            "slippage": sum(t.slippage for t in trades),
            "net_pnl": sum(t.net_pnl for t in trades),
            "worst_mark": min(marks, default=0.0),
            "best_mark": max(marks, default=0.0),
            "marks": [round(m, 6) for m in marks],
            "governor_events": governor_events,
            "zero_volume_bars": s.quality.zero_volume_bars,
        })
    elapsed = time.perf_counter() - t0

    ledger = _ledger(eng, instrument, profile, bar_lookup, spec)
    return {
        "instrument": instrument,
        "profile": profile.name,
        "profile_spec_hash": spec.spec_hash,
        "contracts": spec.contracts,
        "sessions": len(sessions),
        "ledger": ledger,
        "daily": daily,
        "seconds": round(elapsed, 2),
        "transitions": len(eng.transitions),
    }


def _ledger(eng: Engine, instrument: str, profile, bar_lookup, spec) -> list[dict]:
    """One row per trade, joining the engine's trades to its per-bar outcome trail.

    Break-even and stall timestamps live on `BarOutcome`, not on `LedgerTrade`; MFE/MAE
    TIMESTAMPS live on neither and are recovered by walking the trade's own bars. None of
    that is a second P&L calculation - the money columns come straight from the trade.
    """
    by_bar = {i: o for i, o in enumerate(eng.outcomes)}
    rows = []
    for t in eng.trades:
        span = range(t.entry_bar, t.exit_bar + 1)
        be_at = next((by_bar[i].timestamp for i in span
                      if i in by_bar and by_bar[i].breakeven), None)
        stall_at = next((by_bar[i].timestamp for i in span
                         if i in by_bar and by_bar[i].stall_modified), None)

        bars = [bar_lookup[by_bar[i].timestamp] for i in span
                if i in by_bar and by_bar[i].timestamp in bar_lookup]
        mfe_at = mae_at = None
        if bars:
            d = t.direction
            best = max(bars, key=lambda b: ((b.high if d > 0 else -b.low) * d))
            worst = min(bars, key=lambda b: ((b.low if d > 0 else -b.high) * d))
            mfe_at, mae_at = best.timestamp, worst.timestamp

        pv = spec.point_value
        risk = spec.stop_points * pv
        rows.append({
            "trade_id": t.trade_id,
            "trading_day": str(t.session),
            "instrument": instrument,
            "contract": "",
            "profile": profile.name,
            "direction": "LONG" if t.direction > 0 else "SHORT",
            "quantity": t.quantity,
            "entry_time_utc": t.entry_time.isoformat(),
            "entry_time_et": _et(t.entry_time.to_pydatetime()).strftime("%Y-%m-%d %H:%M"),
            "entry_price": t.entry_price,
            "entry_slippage_ticks": profile.entry_ticks,
            "initial_stop": round(t.entry_price - spec.stop_points * t.direction, 4),
            "initial_target": round(t.entry_price + spec.target_points * t.direction, 4),
            "breakeven_time_et": _et(be_at).strftime("%Y-%m-%d %H:%M") if be_at else "",
            "breakeven_stop": round(
                t.entry_price + spec.breakeven_offset * t.direction, 4) if be_at else None,
            "stall_time_et": (_et(stall_at).strftime("%Y-%m-%d %H:%M")
                              if stall_at else ""),
            "modified_target": round(
                t.entry_price + spec.stall_target * t.direction, 4) if stall_at else None,
            "mfe_dollars": t.mfe,
            "mae_dollars": t.mae,
            "mfe_time_et": _et(mfe_at).strftime("%Y-%m-%d %H:%M") if mfe_at else "",
            "mae_time_et": _et(mae_at).strftime("%Y-%m-%d %H:%M") if mae_at else "",
            "exit_time_utc": t.exit_time.isoformat(),
            "exit_time_et": _et(t.exit_time.to_pydatetime()).strftime("%Y-%m-%d %H:%M"),
            "exit_price": t.exit_price,
            "exit_reason": t.exit_reason,
            "exit_slippage_ticks": _exit_ticks(t.exit_reason, profile),
            "gross_pnl": round(t.gross_pnl, 6),
            "commission": round(t.commission_and_spread, 6),
            "slippage_cost": round(t.slippage, 6),
            "net_pnl": round(t.net_pnl, 6),
            "r_multiple": round(t.r_multiple, 6),
            "r_multiple_net": round(t.net_pnl / risk, 6),
            "holding_minutes": t.holding_minutes,
            "ambiguous_bar": t.ambiguous_bar,
            "governor_exit": t.exit_reason == EXIT_KILLSWITCH,
            "forced_flatten": t.exit_reason == EXIT_HARD_FLATTEN,
            "entry_hour_et": _et(t.entry_time.to_pydatetime()).hour,
            "weekday": _et(t.entry_time.to_pydatetime()).strftime("%a"),
            "month": _et(t.entry_time.to_pydatetime()).strftime("%Y-%m"),
        })
    return rows


def _exit_ticks(reason: str, profile) -> float:
    if reason == EXIT_TARGET:
        return profile.target_ticks
    if reason == EXIT_STOP:
        return profile.stop_ticks
    return profile.market_exit_ticks


# ======================================================================================
# STATISTICS - every one of them derived from the ledger
# ======================================================================================

def _q(xs, p):
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _streak(flags) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


def statistics_for(ledger: list[dict], daily: list[dict]) -> dict:
    n = len(ledger)
    net = [r["net_pnl"] for r in ledger]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x < 0]
    scratches = [x for x in net if x == 0]
    day_pnl = [d["net_pnl"] for d in daily]
    traded_days = [d for d in daily if d["trades"]]

    gross_win, gross_loss = sum(wins), -sum(losses)
    out = {
        "total_trades": n,
        "total_sessions": len(daily),
        "sessions_with_a_trade": len(traded_days),
        "trades_per_session_mean": round(n / len(daily), 4) if daily else 0.0,
        "trades_per_session_median": _q([d["trades"] for d in daily], 0.5),
        "trades_per_traded_session_mean": round(n / len(traded_days), 4)
        if traded_days else 0.0,
        "gross_pnl": round(sum(r["gross_pnl"] for r in ledger), 2),
        "commission": round(sum(r["commission"] for r in ledger), 2),
        "slippage": round(sum(r["slippage_cost"] for r in ledger), 2),
        "net_pnl": round(sum(net), 2),
        "avg_dollars_per_trade": round(sum(net) / n, 2) if n else 0.0,
        "median_dollars_per_trade": round(_q(net, 0.5), 2) if n else 0.0,
        "wins": len(wins), "losses": len(losses), "scratches": len(scratches),
        "win_rate": round(len(wins) / n, 4) if n else 0.0,
        "loss_rate": round(len(losses) / n, 4) if n else 0.0,
        "avg_winner": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loser": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "payoff_ratio": round((sum(wins) / len(wins)) / abs(sum(losses) / len(losses)), 4)
        if wins and losses else float("nan"),
        "expectancy_per_trade": round(sum(net) / n, 2) if n else 0.0,
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss else float("inf"),
        "max_consecutive_wins": _streak([x > 0 for x in net]),
        "max_consecutive_losses": _streak([x < 0 for x in net]),
        "largest_winner": round(max(net), 2) if n else 0.0,
        "largest_loser": round(min(net), 2) if n else 0.0,
        "median_holding_minutes": _q([r["holding_minutes"] for r in ledger], 0.5),
        "mean_holding_minutes": round(
            sum(r["holding_minutes"] for r in ledger) / n, 2) if n else 0.0,
        "mfe_mean": round(sum(r["mfe_dollars"] for r in ledger) / n, 2) if n else 0.0,
        "mae_mean": round(sum(r["mae_dollars"] for r in ledger) / n, 2) if n else 0.0,
        "mfe_median": round(_q([r["mfe_dollars"] for r in ledger], 0.5), 2) if n else 0.0,
        "mae_median": round(_q([r["mae_dollars"] for r in ledger], 0.5), 2) if n else 0.0,
        "avg_r": round(sum(r["r_multiple_net"] for r in ledger) / n, 4) if n else 0.0,
        "median_r": round(_q([r["r_multiple_net"] for r in ledger], 0.5), 4) if n else 0.0,
        "r_p05": round(_q([r["r_multiple_net"] for r in ledger], 0.05), 4) if n else 0.0,
        "r_p95": round(_q([r["r_multiple_net"] for r in ledger], 0.95), 4) if n else 0.0,
        "daily_pnl_mean": round(sum(day_pnl) / len(daily), 2) if daily else 0.0,
        "daily_pnl_median": round(_q(day_pnl, 0.5), 2) if daily else 0.0,
        "daily_pnl_p05": round(_q(day_pnl, 0.05), 2) if daily else 0.0,
        "daily_pnl_p95": round(_q(day_pnl, 0.95), 2) if daily else 0.0,
        "daily_pnl_worst": round(min(day_pnl), 2) if daily else 0.0,
        "daily_pnl_best": round(max(day_pnl), 2) if daily else 0.0,
        "positive_days": sum(1 for x in day_pnl if x > 0),
        "negative_days": sum(1 for x in day_pnl if x < 0),
    }
    if n > 1:
        out["stdev_dollars_per_trade"] = round(statistics.stdev(net), 2)
    return out


def _group(ledger, key):
    out: dict[str, list] = {}
    for r in ledger:
        out.setdefault(str(r[key]), []).append(r)
    return out


def breakdowns(ledger: list[dict]) -> dict:
    def block(rows):
        net = [r["net_pnl"] for r in rows]
        w = [x for x in net if x > 0]
        return {"trades": len(rows), "net_pnl": round(sum(net), 2),
                "wins": len(w), "win_rate": round(len(w) / len(rows), 4) if rows else 0.0,
                "avg": round(sum(net) / len(rows), 2) if rows else 0.0}

    return {
        "by_direction": {k: block(v) for k, v in _group(ledger, "direction").items()},
        "by_exit_reason": {k: block(v) for k, v in _group(ledger, "exit_reason").items()},
        "by_month": {k: block(v) for k, v in sorted(_group(ledger, "month").items())},
        "by_weekday": {k: block(v) for k, v in _group(ledger, "weekday").items()},
        "by_entry_hour": {k: block(v)
                          for k, v in sorted(_group(ledger, "entry_hour_et").items(),
                                             key=lambda kv: int(kv[0]))},
        "by_contract": {k: block(v) for k, v in _group(ledger, "contract").items()},
    }


def equity_and_drawdown(daily: list[dict]) -> dict:
    """The equity curve, built from the ledger's own daily net P&L. No second calculation."""
    equity, peak, dd, cur_dd_days, worst_dd_days = STARTING_BALANCE, STARTING_BALANCE, 0.0, 0, 0
    curve, dd_start, worst_start, worst_end = [], None, None, None
    recovery_days = None
    for d in daily:
        equity += d["net_pnl"]
        curve.append({"day": d["trading_day"], "equity": round(equity, 2)})
        if equity > peak:
            if dd_start is not None and recovery_days is None and dd > 0:
                recovery_days = cur_dd_days
            peak, cur_dd_days, dd_start = equity, 0, None
        else:
            cur_dd_days += 1
            if dd_start is None:
                dd_start = d["trading_day"]
            if peak - equity > dd:
                dd = peak - equity
                worst_dd_days, worst_start, worst_end = cur_dd_days, dd_start, d["trading_day"]

    intraday_worst = min((d["worst_mark"] for d in daily), default=0.0)
    return {
        "starting_balance": STARTING_BALANCE,
        "strategy_net_pnl": round(equity - STARTING_BALANCE, 2),
        "ending_balance": round(equity, 2),
        "max_drawdown_dollars": round(dd, 2),
        "max_drawdown_pct_of_start": round(100.0 * dd / STARTING_BALANCE, 3),
        "max_drawdown_sessions": worst_dd_days,
        "drawdown_window": [worst_start, worst_end],
        "recovery_sessions_after_worst": recovery_days,
        "worst_session": round(min((d["net_pnl"] for d in daily), default=0.0), 2),
        "best_session": round(max((d["net_pnl"] for d in daily), default=0.0), 2),
        "max_intraday_adverse_excursion": round(intraday_worst, 2),
        "curve": curve,
    }


def monthly(daily: list[dict], ledger: list[dict]) -> dict:
    months: dict[str, list] = {}
    for d in daily:
        months.setdefault(d["trading_day"][:7], []).append(d)
    trades_by_month = _group(ledger, "month")

    rows = []
    for m, days in sorted(months.items()):
        pnl = [x["net_pnl"] for x in days]
        run, peak, mdd = 0.0, 0.0, 0.0
        for x in pnl:
            run += x
            peak = max(peak, run)
            mdd = max(mdd, peak - run)
        rows.append({
            "month": m,
            "sessions": len(days),
            "trades": len(trades_by_month.get(m, [])),
            "gross_pnl": round(sum(x["gross_pnl"] for x in days), 2),
            "commission": round(sum(x["commission"] for x in days), 2),
            "slippage": round(sum(x["slippage"] for x in days), 2),
            "net_pnl": round(sum(pnl), 2),
            "return_on_50k_pct": round(100.0 * sum(pnl) / STARTING_BALANCE, 4),
            "avg_daily_pnl": round(sum(pnl) / len(days), 2),
            "median_daily_pnl": round(_q(pnl, 0.5), 2),
            "positive": sum(pnl) > 0,
            "max_intra_month_drawdown": round(mdd, 2),
        })

    nets = [r["net_pnl"] for r in rows]
    rets = [r["return_on_50k_pct"] for r in rows]
    summary = {
        "months": len(rows),
        "mean_monthly_pnl": round(sum(nets) / len(nets), 2) if nets else 0.0,
        "median_monthly_pnl": round(_q(nets, 0.5), 2) if nets else 0.0,
        "mean_monthly_return_pct": round(sum(rets) / len(rets), 4) if rets else 0.0,
        "median_monthly_return_pct": round(_q(rets, 0.5), 4) if rets else 0.0,
        "stdev_monthly_return_pct": round(statistics.stdev(rets), 4) if len(rets) > 1 else 0.0,
        "positive_months": sum(1 for x in nets if x > 0),
        "negative_months": sum(1 for x in nets if x < 0),
        "flat_months": sum(1 for x in nets if x == 0),
        "pct_positive_months": round(100.0 * sum(1 for x in nets if x > 0) / len(nets), 2)
        if nets else 0.0,
        "best_month": round(max(nets), 2) if nets else 0.0,
        "worst_month": round(min(nets), 2) if nets else 0.0,
        "p25_month": round(_q(nets, 0.25), 2) if nets else 0.0,
        "p75_month": round(_q(nets, 0.75), 2) if nets else 0.0,
        "SAMPLE_SIZE_WARNING": f"{len(rows)} months. A 15-month window is not an estimate of "
                               f"long-run monthly performance and must not be read as one.",
    }
    return {"table": rows, "summary": summary}


# ======================================================================================
# MAIN
# ======================================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--instrument", choices=sorted(SPECS), help="one instrument")
    ap.add_argument("--all", action="store_true", help="every instrument")
    ap.add_argument("--out", default="research/vwap_v1", help="output directory")
    args = ap.parse_args()

    if not args.all and not args.instrument:
        ap.error("pass --instrument or --all")
    instruments = sorted(SPECS) if args.all else [args.instrument]

    out_dir = REPO / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    env = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "git_sha": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
    }
    import numpy
    import pandas
    env["numpy"], env["pandas"] = numpy.__version__, pandas.__version__

    everything = {"strategy": VERSION, "generated_utc": dt.datetime.now(dt.UTC).isoformat(),
                  "environment": env, "runs": {}}

    for inst in instruments:
        ds = load_anchored(STORE / f"{inst}.parquet", inst)
        sessions = ds.usable()
        dm = ds.manifest()
        print(f"\n{'=' * 96}")
        print(f"{inst}   {len(sessions)} usable sessions   manifest {dm['manifest_id']}   "
              f"spec {SPECS[inst].spec_hash}")
        print("=" * 96)

        for profile in EXECUTION_LADDER:
            r = run_one(inst, profile, sessions)
            r["statistics"] = statistics_for(r["ledger"], r["daily"])
            r["breakdowns"] = breakdowns(r["ledger"])
            r["equity"] = equity_and_drawdown(r["daily"])
            r["monthly"] = monthly(r["daily"], r["ledger"])
            r["dataset"] = {
                "manifest_id": dm["manifest_id"],
                "content_hash": dm["content_hash"],
                "file_sha256": dm["source"]["file_hashes"],
                "first_trading_day": dm["coverage"]["first_trading_day"],
                "last_trading_day": dm["coverage"]["last_trading_day"],
                "sessions_usable": dm["coverage"]["sessions_usable"],
                "sessions_found": dm["coverage"]["sessions_found"],
                "sessions_refused": dm["coverage"]["sessions_found"]
                - dm["coverage"]["sessions_usable"],
                "contract_coverage": dm["source"]["contract_coverage"],
            }
            r["ledger_hash"] = _hash(r["ledger"])
            r["daily_hash"] = _hash([{k: v for k, v in d.items() if k != "marks"}
                                     for d in r["daily"]])
            r["summary_hash"] = _hash(r["statistics"])
            everything["runs"][f"{inst}:{profile.name}"] = r

            s, e = r["statistics"], r["equity"]
            print(f"  {profile.name:16} trades {s['total_trades']:>4}  "
                  f"net ${s['net_pnl']:>10,.2f}  win {s['win_rate']:>6.1%}  "
                  f"PF {s['profit_factor']:>7}  maxDD ${e['max_drawdown_dollars']:>9,.2f}  "
                  f"ledger {r['ledger_hash']}")

    path = out_dir / "backtest.json"
    path.write_text(json.dumps(everything, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {path.relative_to(REPO)}")
    print("\nNo parameter was changed. No filter was added. No trade was removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
