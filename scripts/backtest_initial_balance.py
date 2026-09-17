"""THE HISTORICAL RUN of Initial Balance Statistical Reversion, ES V1.0_Frozen.

    python scripts/backtest_initial_balance.py --out research/ib_reversion

Measurement, not development. Nothing is optimised, no parameter is exposed on the command
line, and every execution profile on the declared ladder is run on the same frozen rules.

ONE LEDGER
------------
Equity, drawdown, monthly tables, the Topstep twin and the Monte Carlo are all derived from
the single trade ledger this script writes. There is no second P&L calculation anywhere;
`quant_brain.research.reference_ledger` is the exception, and its only job is to disagree.

THE SESSION FILTER, BOUNDED AT BOTH ENDS
------------------------------------------
The certified loader hands back an 18:00-anchored session, so a filter of `minute >= 09:30`
also keeps the previous evening's bars. That defect sealed an empty Initial Balance and halted
every day - a silent zero-trade backtest. The filter below is bounded at both ends and
`InitialBalance.seal` now raises if it ever sees an empty window again.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import hashlib
import json
import platform
import random
import statistics
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from quant_brain.markets.futures_cme import topstep as ts  # noqa: E402
from quant_brain.markets.futures_cme.twin import (  # noqa: E402
    NEVER,
    TopstepTwin,
    TwinDay,
)
from quant_brain.research.reference_ledger import reference_pnl_one_trade  # noqa: E402
from quant_brain.strategies.initial_balance_reversion.engine import Engine  # noqa: E402
from quant_brain.strategies.initial_balance_reversion.spec import (  # noqa: E402
    AMBIGUITIES,
    EXECUTION_LADDER,
    FROZEN,
    TIMEZONE,
    VERSION,
    FrozenSpec,
    unresolved,
)
from quant_brain.strategies.vwap_pullback.data import load_anchored  # noqa: E402

STORE = REPO / "data" / "futures"
RTH_LO, RTH_HI = 9 * 60 + 30, 15 * 60 + 45
ACCOUNT = 50_000
SEED = 20260917
MC_REPS = 10_000


def _git(*a: str) -> str:
    try:
        return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True,
                              timeout=20, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):          # pragma: no cover
        return ""


def _hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _q(xs, p):
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def rth_bars(session):
    """09:30-15:45 ET inclusive. Bounded at BOTH ends - see the module docstring."""
    out = []
    for b in session.bars:
        local = b.timestamp.astimezone(TIMEZONE)
        m = local.hour * 60 + local.minute
        if RTH_LO <= m <= RTH_HI:
            out.append(b)
    return out


# ======================================================================================
# THE RUN
# ======================================================================================

def run_profile(sessions, profile) -> dict:
    spec = dataclasses.replace(FROZEN, execution=profile)
    eng = Engine(spec=spec)
    daily = []
    for s in sessions:
        bars = rth_bars(s)
        before = len(eng.trades)
        eng.start_session(s.trading_day, bars[0].timestamp)
        marks = [0.0]
        for b in bars:
            eng.on_bar(b)
            if eng.position is not None:
                p = eng.position
                adverse = b.low if p.direction > 0 else b.high
                unreal = (adverse - p.fill_price) * p.direction * spec.point_value
                marks.append(eng.governor.realized + unreal)
            else:
                marks.append(eng.governor.realized)
        eng.end_session(bars[-1].timestamp)
        trades = eng.trades[before:]
        daily.append({
            "trading_day": str(s.trading_day),
            "contract": s.contract,
            "ib_high": eng.ib.ib_high if eng.ib.complete else None,
            "ib_low": eng.ib.ib_low if eng.ib.complete else None,
            "ib_range": eng.ib.ib_range if eng.ib.complete else None,
            "in_regime": bool(eng.ib.complete and eng.ib.in_regime(
                spec.ib_range_min, spec.ib_range_max)),
            "halted": eng.governor.halted,
            "halt_reason": eng.governor.halt_reason,
            "trades": len(trades),
            "gross_pnl": round(sum(t.gross_pnl for t in trades), 6),
            "commission": round(sum(t.commission for t in trades), 6),
            "slippage": round(sum(t.entry_slippage + t.exit_slippage for t in trades), 6),
            "net_pnl": round(sum(t.net_pnl for t in trades), 6),
            "worst_mark": round(min(marks), 6),
            "marks": [round(m, 6) for m in marks],
        })

    ledger = []
    for t in eng.trades:
        ledger.append({
            "trade_id": t.trade_id, "date": str(t.session),
            "entry_time_et": t.entry_time.astimezone(TIMEZONE).strftime("%Y-%m-%d %H:%M"),
            "exit_time_et": t.exit_time.astimezone(TIMEZONE).strftime("%Y-%m-%d %H:%M"),
            "side": "LONG" if t.direction > 0 else "SHORT", "quantity": t.quantity,
            "entry_price": t.entry_price, "exit_price": t.exit_price,
            "ib_high": t.ib_high, "ib_low": t.ib_low, "ib_range": t.ib_range,
            "ib_midpoint": t.ib_midpoint, "trap_extreme": t.trap_extreme,
            "stop_price": t.stop_price, "target_price": t.target_price,
            "gross_pnl": round(t.gross_pnl, 6), "commission": round(t.commission, 6),
            "entry_slippage": round(t.entry_slippage, 6),
            "exit_slippage": round(t.exit_slippage, 6),
            "total_cost": round(t.commission + t.entry_slippage + t.exit_slippage, 6),
            "net_pnl": round(t.net_pnl, 6), "exit_reason": t.exit_reason,
            "holding_minutes": t.holding_minutes, "mae": round(t.mae, 6),
            "mfe": round(t.mfe, 6), "ambiguous_bar": t.ambiguous_bar,
            "daily_realized_before": round(t.realized_before, 6),
            "daily_realized_after": round(t.realized_after, 6),
            "month": t.entry_time.astimezone(TIMEZONE).strftime("%Y-%m"),
            "weekday": t.entry_time.astimezone(TIMEZONE).strftime("%a"),
            "entry_hour_et": t.entry_time.astimezone(TIMEZONE).hour,
            "profile": profile.name,
        })
    return {"profile": profile.name, "spec_hash": spec.spec_hash, "ledger": ledger,
            "daily": daily, "ambiguous_buckets": eng.ambiguous_buckets,
            "immediate_targets": eng.immediate_targets,
            "same_bucket_traps": eng.same_bucket_traps,
            "transitions": len(eng.transitions)}


# ======================================================================================
# STATISTICS, ALL FROM THE LEDGER
# ======================================================================================

def _streak(flags):
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


def stats(ledger, daily):
    n = len(ledger)
    net = [r["net_pnl"] for r in ledger]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x < 0]
    day_pnl = [d["net_pnl"] for d in daily]
    traded = [d for d in daily if d["trades"]]
    gw, gl = sum(wins), -sum(losses)
    out = {
        "sessions_analyzed": len(daily),
        "sessions_in_regime": sum(1 for d in daily if d["in_regime"]),
        "sessions_skipped_out_of_regime": sum(1 for d in daily if not d["in_regime"]),
        "sessions_traded": len(traded),
        "trades": n,
        "trades_per_session": round(n / len(daily), 4) if daily else 0.0,
        "trades_per_traded_session": round(n / len(traded), 4) if traded else 0.0,
        "gross_pnl": round(sum(r["gross_pnl"] for r in ledger), 2),
        "commissions": round(sum(r["commission"] for r in ledger), 2),
        "slippage": round(sum(r["entry_slippage"] + r["exit_slippage"] for r in ledger), 2),
        "net_pnl": round(sum(net), 2),
        "average_trade": round(sum(net) / n, 2) if n else 0.0,
        "median_trade": round(_q(net, 0.5), 2) if n else 0.0,
        "profit_factor": round(gw / gl, 4) if gl else float("inf"),
        "win_rate": round(len(wins) / n, 4) if n else 0.0,
        "average_winner": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "average_loser": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "payoff_ratio": round((sum(wins) / len(wins)) / abs(sum(losses) / len(losses)), 4)
        if wins and losses else None,
        "expectancy": round(sum(net) / n, 2) if n else 0.0,
        "max_consecutive_wins": _streak([x > 0 for x in net]),
        "max_consecutive_losses": _streak([x < 0 for x in net]),
        "worst_trade": round(min(net), 2) if n else 0.0,
        "best_trade": round(max(net), 2) if n else 0.0,
        "worst_day": round(min(day_pnl), 2) if daily else 0.0,
        "best_day": round(max(day_pnl), 2) if daily else 0.0,
        "mae_mean": round(sum(r["mae"] for r in ledger) / n, 2) if n else 0.0,
        "mfe_mean": round(sum(r["mfe"] for r in ledger) / n, 2) if n else 0.0,
        "mae_worst": round(min((r["mae"] for r in ledger), default=0.0), 2),
        "mfe_best": round(max((r["mfe"] for r in ledger), default=0.0), 2),
        "median_holding_minutes": _q([r["holding_minutes"] for r in ledger], 0.5) if n else 0,
        "ambiguous_trades": sum(1 for r in ledger if r["ambiguous_bar"]),
    }
    if n > 1:
        out["stdev_trade"] = round(statistics.stdev(net), 2)
    if len(day_pnl) > 1 and statistics.stdev(day_pnl) > 0:
        mu, sd = statistics.mean(day_pnl), statistics.stdev(day_pnl)
        out["sharpe_daily_unit"] = round(mu / sd, 4)
        out["sharpe_annualised_252_sessions"] = round((mu / sd) * (252 ** 0.5), 4)
        downs = [x for x in day_pnl if x < 0]
        if len(downs) > 1 and statistics.stdev(downs) > 0:
            out["sortino_daily_unit"] = round(mu / statistics.stdev(downs), 4)
        out["SHARPE_NOTE"] = ("time unit is one TRADING SESSION; annualised with sqrt(252). "
                              "Computed on daily P&L, not on trade P&L.")
    by_reason = {}
    for r in ledger:
        b = by_reason.setdefault(r["exit_reason"], {"n": 0, "net": 0.0, "wins": 0})
        b["n"] += 1
        b["net"] += r["net_pnl"]
        b["wins"] += int(r["net_pnl"] > 0)
    out["by_exit_reason"] = {k: {"trades": v["n"], "net_pnl": round(v["net"], 2),
                                 "wins": v["wins"]} for k, v in sorted(by_reason.items())}
    return out


def equity(daily):
    eq = ACCOUNT
    peak, dd, dd_days, worst_days = eq, 0.0, 0, 0
    curve, start, window = [], None, [None, None]
    recovery = None
    for d in daily:
        eq += d["net_pnl"]
        curve.append({"day": d["trading_day"], "equity": round(eq, 2)})
        if eq > peak:
            if start is not None and recovery is None and dd > 0:
                recovery = dd_days
            peak, dd_days, start = eq, 0, None
        else:
            dd_days += 1
            if start is None:
                start = d["trading_day"]
            if peak - eq > dd:
                dd, worst_days, window = peak - eq, dd_days, [start, d["trading_day"]]
    return {
        "starting_balance": float(ACCOUNT),
        "strategy_net_pnl": round(eq - ACCOUNT, 2),
        "ending_account_balance": round(eq, 2),
        "account_return_pct": round(100.0 * (eq - ACCOUNT) / ACCOUNT, 4),
        "max_drawdown_dollars": round(dd, 2),
        "max_drawdown_pct_of_account": round(100.0 * dd / ACCOUNT, 4),
        "max_drawdown_sessions": worst_days,
        "drawdown_window": window,
        "recovery_sessions": recovery,
        "max_intraday_adverse": round(min((d["worst_mark"] for d in daily), default=0.0), 2),
        "curve": curve,
        "NOTE": "ACCOUNT RETURN uses the declared $50,000 simulated account as denominator. "
                "There is no separate strategy return denominator; 1 ES is not a capital "
                "commitment of a stated size.",
    }


def monthly(daily, ledger):
    months = {}
    for d in daily:
        months.setdefault(d["trading_day"][:7], []).append(d)
    tbm = {}
    for r in ledger:
        tbm.setdefault(r["month"], []).append(r)
    rows = []
    for m, ds in sorted(months.items()):
        pnl = [x["net_pnl"] for x in ds]
        run = peak = mdd = 0.0
        for x in pnl:
            run += x
            peak = max(peak, run)
            mdd = max(mdd, peak - run)
        rows.append({"month": m, "sessions": len(ds), "trades": len(tbm.get(m, [])),
                     "gross_pnl": round(sum(x["gross_pnl"] for x in ds), 2),
                     "commission": round(sum(x["commission"] for x in ds), 2),
                     "slippage": round(sum(x["slippage"] for x in ds), 2),
                     "net_pnl": round(sum(pnl), 2),
                     "return_on_account_pct": round(100.0 * sum(pnl) / ACCOUNT, 4),
                     "positive": sum(pnl) > 0,
                     "max_intra_month_drawdown": round(mdd, 2)})
    nets = [r["net_pnl"] for r in rows]
    return {"table": rows, "summary": {
        "months": len(rows),
        "mean_monthly_pnl": round(sum(nets) / len(nets), 2) if nets else 0.0,
        "median_monthly_pnl": round(_q(nets, 0.5), 2) if nets else 0.0,
        "stdev_monthly_pnl": round(statistics.stdev(nets), 2) if len(nets) > 1 else 0.0,
        "positive_months": sum(1 for x in nets if x > 0),
        "negative_months": sum(1 for x in nets if x < 0),
        "best_month": round(max(nets), 2) if nets else 0.0,
        "worst_month": round(min(nets), 2) if nets else 0.0,
        "SAMPLE": f"{len(rows)} months. Not an estimate of long-run monthly performance.",
    }}


# ======================================================================================
# TOPSTEP, MONTE CARLO, RECONCILIATION
# ======================================================================================

def twin_days(daily):
    return [TwinDay(day=dt.date.fromisoformat(d["trading_day"]), pnl=d["net_pnl"],
                    path=tuple(d["marks"]) or (0.0,), traded=bool(d["trades"]))
            for d in daily]


def topstep(daily):
    r = TopstepTwin(size=ACCOUNT, payout_policy=NEVER, strict_path=True).run(twin_days(daily))
    c = TopstepTwin(size=ACCOUNT).combine_profile
    return {
        "profile_retrieved": str(ts.RETRIEVED),
        "starting_balance": float(ACCOUNT),
        "profit_target": ts.COMBINE_PROFIT_TARGET[ACCOUNT].value,
        "mll": ts.MLL[ACCOUNT].value,
        "mll_trailing": ts.MLL_TRAILS.value.value,
        "dll": getattr(c, "daily_loss_limit", None),
        "dll_optional": ts.DLL_IS_OPTIONAL.value,
        "max_contracts": list(ts.CONTRACTS[ACCOUNT].value),
        "days_traded": sum(1 for d in daily if d["trades"]),
        "days_profitable": sum(1 for d in daily if d["net_pnl"] > 0),
        "target_reached": r.combine_days is not None,
        "days_to_target": r.combine_days,
        "mll_breached": r.breach_day is not None,
        "breach_day": str(r.breach_day) if r.breach_day else None,
        "breach_reason": r.breach_reason,
        "terminal_stage": r.terminal.value,
        "minimum_buffer_to_mll": round(r.min_buffer, 2),
        "final_balance": round(r.final_balance, 2),
        #: NOT a Topstep rule. This counts days halted by the USER'S OWN governor - almost
        #: all of them the IB regime filter refusing to trade - and the brief is explicit
        #: that the two must not be conflated.
        "strategy_governor_halt_days": sum(1 for d in daily if d["halted"]),
        "strategy_governor_halts_out_of_regime": sum(
            1 for d in daily if d["halted"] and not d["in_regime"]),
        "topstep_halt_days": 0 if r.breach_day is None else 1,
    }


def monte_carlo(daily):
    """Bootstrap complete TRADING DAYS, preserving within-day clustering."""
    rng = random.Random(SEED)
    day_pnl = [d["net_pnl"] for d in daily]
    target, mll = ts.COMBINE_PROFIT_TARGET[ACCOUNT].value, ts.MLL[ACCOUNT].value

    def walk(seq, horizon=None):
        run = peak = dd = 0.0
        hit = None
        for i, x in enumerate(seq):
            run += x
            peak = max(peak, run)
            dd = max(dd, peak - run)
            if hit is None and run >= target:
                hit = ("TARGET", i + 1)
            if hit is None and run <= -mll:
                hit = ("MLL", i + 1)
            if horizon and i + 1 >= horizon:
                break
        return run, dd, hit

    n = len(day_pnl)
    samples = [walk([rng.choice(day_pnl) for _ in range(n)]) for _ in range(MC_REPS)]
    ends = [s[0] for s in samples]
    dds = [s[1] for s in samples]
    hits = [s[2] for s in samples]
    tt = [h[1] for h in hits if h and h[0] == "TARGET"]

    by_h = {}
    for horizon in (5, 10, 20):
        got = 0
        for _ in range(MC_REPS):
            _, _, h = walk([rng.choice(day_pnl) for _ in range(horizon)], horizon)
            got += int(bool(h and h[0] == "TARGET"))
        by_h[f"P_target_within_{horizon}_sessions"] = round(got / MC_REPS, 4)

    return {
        "method": "iid bootstrap of complete trading days (preserves within-day trade "
                  "clustering and the daily P&L distribution)",
        "reps": MC_REPS, "seed": SEED, "sessions_resampled": n,
        "distinct_nonzero_days": sum(1 for x in day_pnl if x != 0),
        "median_ending_pnl": round(_q(ends, 0.5), 2),
        "p10": round(_q(ends, 0.10), 2), "p25": round(_q(ends, 0.25), 2),
        "p75": round(_q(ends, 0.75), 2), "p90": round(_q(ends, 0.90), 2),
        "prob_negative": round(sum(1 for x in ends if x < 0) / len(ends), 4),
        "prob_mll_breach_first": round(
            sum(1 for h in hits if h and h[0] == "MLL") / len(hits), 4),
        "prob_target_first": round(
            sum(1 for h in hits if h and h[0] == "TARGET") / len(hits), 4),
        "median_max_drawdown": round(_q(dds, 0.5), 2),
        "p90_max_drawdown": round(_q(dds, 0.90), 2),
        "median_sessions_to_target": round(_q(tt, 0.5), 1) if tt else None,
        "max_losing_streak_note": "see statistics.max_consecutive_losses on the real path",
        **by_h,
        "LABEL": "CONDITIONAL SIMULATION on the observed daily distribution. Not a "
                 "prediction of future profitability, and not a probability of passing.",
    }


def reconcile(ledger):
    bad = []
    for t in ledger:
        d = 1 if t["side"] == "LONG" else -1
        pv = FROZEN.point_value
        ideal_entry = t["entry_price"] - (t["entry_slippage"] / pv) * d
        ideal_exit = t["exit_price"] + (t["exit_slippage"] / pv) * d
        gross, comm, _ = reference_pnl_one_trade(ideal_entry, ideal_exit, d, 1, pv,
                                                 FROZEN.commission_round_turn)
        net = gross - t["entry_slippage"] - t["exit_slippage"] - comm
        for f, mine, theirs in (("gross_pnl", t["gross_pnl"], gross),
                                ("commission", t["commission"], comm),
                                ("net_pnl", t["net_pnl"], net)):
            if abs(mine - theirs) > 1e-9:
                bad.append({"trade_id": t["trade_id"], "field": f, "ledger": mine,
                            "reference": theirs})
    return {"trades_checked": len(ledger), "tolerance": 1e-9, "mismatches": bad,
            "AGREES": not bad}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="research/ib_reversion")
    args = ap.parse_args()
    out_dir = REPO / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    ds = load_anchored(STORE / "ES.parquet", "ES")
    sessions = ds.usable()
    dm = ds.manifest()

    import numpy
    import pandas
    manifest = {
        "strategy": VERSION,
        "strategy_spec_hash": FROZEN.spec_hash,
        "unresolved_ambiguities": [a.ref for a in unresolved()],
        "ambiguities_declared": len(AMBIGUITIES),
        "dataset_manifest_id": dm["manifest_id"],
        "dataset_content_hash": dm["content_hash"],
        "dataset_sha256": dm["source"]["file_hashes"],
        "dataset_rows": dm["source"]["rows_in_file"],
        "sessions_usable": dm["coverage"]["sessions_usable"],
        "sessions_found": dm["coverage"]["sessions_found"],
        "contract_coverage": dm["source"]["contract_coverage"],
        "topstep_profile_retrieved": str(ts.RETRIEVED),
        "git_sha": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "python": platform.python_version(),
        "numpy": numpy.__version__, "pandas": pandas.__version__,
        "seed": SEED,
        "run_utc": dt.datetime.now(dt.UTC).isoformat(),
    }

    everything = {"manifest": manifest, "runs": {}}
    print(f"ES {len(sessions)} usable sessions  spec {FROZEN.spec_hash}  "
          f"dataset {dm['manifest_id']}")
    for profile in EXECUTION_LADDER:
        r = run_profile(sessions, profile)
        r["statistics"] = stats(r["ledger"], r["daily"])
        r["equity"] = equity(r["daily"])
        r["monthly"] = monthly(r["daily"], r["ledger"])
        r["topstep"] = topstep(r["daily"])
        r["monte_carlo"] = monte_carlo(r["daily"])
        r["reconciliation"] = reconcile(r["ledger"])
        r["ledger_hash"] = _hash(r["ledger"])
        r["daily_hash"] = _hash([{k: v for k, v in d.items() if k != "marks"}
                                 for d in r["daily"]])
        r["summary_hash"] = _hash(r["statistics"])
        everything["runs"][profile.name] = r
        s, e = r["statistics"], r["equity"]
        print(f"  {profile.name:16} trades {s['trades']:>4}  net ${s['net_pnl']:>10,.2f}  "
              f"win {s['win_rate']:>6.1%}  PF {s['profit_factor']:>7}  "
              f"maxDD ${e['max_drawdown_dollars']:>9,.2f}  "
              f"reconcile {'OK' if r['reconciliation']['AGREES'] else 'MISMATCH'}  "
              f"{r['ledger_hash']}")
        if r["ledger"]:
            with (out_dir / f"ledger_{profile.name}.csv").open(
                    "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(r["ledger"][0]))
                w.writeheader()
                w.writerows(r["ledger"])

    (out_dir / "backtest.json").write_text(
        json.dumps(everything, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {(out_dir / 'backtest.json').relative_to(REPO)}")
    bad = [k for k, v in everything["runs"].items() if not v["reconciliation"]["AGREES"]]
    if bad:
        print(f"RECONCILIATION MISMATCH in {bad} - results must not be published")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
