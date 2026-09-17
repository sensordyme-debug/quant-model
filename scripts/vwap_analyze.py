"""Everything downstream of the ledger: Topstep twin, pass paths, payouts, Monte Carlo.

    python scripts/vwap_analyze.py --in research/vwap_v1/backtest.json

READS THE LEDGER. COMPUTES NO P&L. Every number here is a transformation of the daily net
P&L and intraday mark path that `vwap_backtest.py` wrote, so a disagreement between this and
the headline result is impossible by construction rather than by luck.

`--reconcile` additionally recomputes each trade through
`quant_brain.research.reference_ledger`, which shares no code with the strategy engine.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from quant_brain.markets.futures_cme import paths as P  # noqa: E402
from quant_brain.markets.futures_cme import topstep as ts  # noqa: E402
from quant_brain.markets.futures_cme.twin import (  # noqa: E402
    IMMEDIATE,
    NEVER,
    PayoutPolicy,
    TopstepTwin,
    TwinDay,
)
from quant_brain.research.reference_ledger import reference_pnl_one_trade  # noqa: E402
from quant_brain.strategies.vwap_pullback.spec import FROZEN, FROZEN_MNQ  # noqa: E402

SPECS = {"NQ": FROZEN, "MNQ": FROZEN_MNQ}
ACCOUNT = 50_000
MC_REPS = 2000
SEED = 20260916


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


def twin_days(daily: list[dict]) -> list[TwinDay]:
    """The ledger's sessions, as the twin's input type. The path is the mark series."""
    out = []
    for d in daily:
        marks = tuple(d["marks"]) or (0.0,)
        out.append(TwinDay(day=dt.date.fromisoformat(d["trading_day"]),
                           pnl=d["net_pnl"], path=marks, traded=bool(d["trades"])))
    return out


def topstep_profile() -> dict:
    """The versioned configuration, read out rather than restated."""
    twin = TopstepTwin(size=ACCOUNT, strict_path=True)
    c = twin.combine_profile
    return {
        "source_retrieved": str(ts.RETRIEVED),
        "account_size": ACCOUNT,
        "starting_balance": float(ACCOUNT),
        "profit_target": ts.COMBINE_PROFIT_TARGET[ACCOUNT].value,
        "maximum_loss_limit": ts.MLL[ACCOUNT].value,
        "mll_trailing_mode": ts.MLL_TRAILS.value.value,
        "mll_locks_at_start": ts.MLL_LOCKS.value,
        "mll_resets_on_payout": ts.MLL_RESETS_ON_PAYOUT.value,
        "daily_loss_limit": getattr(c, "daily_loss_limit", None),
        "daily_loss_limit_is_optional": ts.DLL_IS_OPTIONAL.value,
        "dll_window_ct": [str(x) for x in ts.DLL_WINDOW.value],
        "contract_limit_mini_micro": list(ts.CONTRACTS[ACCOUNT].value),
        "mandatory_flat_ct": str(ts.MANDATORY_FLAT.value),
        "min_trading_days": ts.COMBINE_MIN_DAYS.value,
        "consistency_reading": ts.DEFAULT_READING,
        "consistency_boundary": ts.DEFAULT_BOUNDARY,
        "consistency_readings_available": {k: list(v)
                                           for k, v in ts.CONSISTENCY_READINGS.items()},
    }


def run_twin(days: list[TwinDay], policy: PayoutPolicy) -> dict:
    twin = TopstepTwin(size=ACCOUNT, payout_policy=policy, strict_path=True)
    r = twin.run(days)
    return {
        "terminal_stage": r.terminal.value,
        "days_stepped": r.days,
        "combine_attempts": r.combine_attempts,
        "days_to_pass_combine": r.combine_days,
        "reached_funding": r.reached_funding,
        "breach_day": str(r.breach_day) if r.breach_day else None,
        "breach_reason": r.breach_reason,
        "min_buffer_to_mll": round(r.min_buffer, 2),
        "payouts": [[str(d), round(a, 2)] for d, a in r.payouts],
        "total_paid_out": round(r.total_paid, 2),
        "final_balance": round(r.final_balance, 2),
        "transitions": [[str(d), s.value] for d, s in r.transitions],
    }


def pass_paths(days: list[TwinDay], *, min_len: int = 20) -> dict:
    """Every historical start that can legitimately be evaluated, walked forward.

    A "path" is the sequence beginning at session i and running to the end of the sample.
    Starts too close to the end cannot reach a verdict and are reported as UNFINISHED rather
    than dropped, because dropping them would quietly select for the starts that resolved.
    """
    outcomes = {"PASS": 0, "MLL_BREACH": 0, "DLL_BREACH": 0, "UNFINISHED": 0,
                "INSUFFICIENT": 0}
    detail = []
    for i in range(len(days)):
        window = days[i:]
        if len(window) < min_len:
            outcomes["INSUFFICIENT"] += 1
            continue
        twin = TopstepTwin(size=ACCOUNT, payout_policy=NEVER, strict_path=True)
        r = twin.run(window)
        if r.combine_days is not None:
            verdict = "PASS"
        elif r.breach_day is not None:
            verdict = "DLL_BREACH" if "daily" in r.breach_reason.lower() else "MLL_BREACH"
        else:
            verdict = "UNFINISHED"
        outcomes[verdict] += 1
        detail.append({"start": str(window[0].day), "sessions_available": len(window),
                       "verdict": verdict,
                       "days_to_pass": r.combine_days,
                       "breach_day": str(r.breach_day) if r.breach_day else None,
                       "breach_reason": r.breach_reason})
    evaluated = sum(v for k, v in outcomes.items() if k != "INSUFFICIENT")
    return {
        "attempts_evaluated": evaluated,
        "attempts_insufficient": outcomes["INSUFFICIENT"],
        "outcomes": outcomes,
        "HISTORICAL_PATH_PASS_RATE": round(outcomes["PASS"] / evaluated, 4)
        if evaluated else 0.0,
        "LABEL": "HISTORICAL PATH PASS RATE - the share of overlapping historical starts "
                 "that reached the target first. These paths overlap heavily and share the "
                 "same few trades, so they are NOT independent attempts and this is NOT a "
                 "probability of passing.",
        "detail": detail[:40],
    }


def payout_analysis(daily: list[dict], twin_result: dict) -> dict:
    """What the versioned payout rules would allow. No payout is assumed from profit alone."""
    pnl = [d["net_pnl"] for d in daily]
    winning = [d for d in daily if d["net_pnl"] > 0]
    total = sum(pnl)
    best_day = max(pnl, default=0.0)
    target = ts.COMBINE_PROFIT_TARGET[ACCOUNT].value
    frac, basis = ts.CONSISTENCY_READINGS[ts.DEFAULT_READING][:2]
    denominator = total if basis == "total" else target
    consistency_ok = best_day <= frac * denominator if denominator > 0 else False
    effective_target = (best_day / frac) if frac and best_day > 0 else target

    return {
        "policy_version": ts.DEFAULT_READING,
        "winning_day_definition": "a session whose NET P&L is strictly greater than $0, "
                                  "measured from the same ledger as every other number here",
        "winning_days": len(winning),
        "total_net_pnl": round(total, 2),
        "profit_target": target,
        "reached_profit_target": total >= target,
        "best_single_day": round(best_day, 2),
        "consistency_fraction": frac,
        "consistency_basis": basis,
        "consistency_satisfied": bool(consistency_ok),
        "effective_target_given_best_day": round(effective_target, 2),
        "payout_opportunities": len(twin_result["payouts"]),
        "total_paid_out": twin_result["total_paid_out"],
        "days_to_first_eligibility": twin_result["days_to_pass_combine"],
        "NOTE": "A payout does not follow from reaching $3,000. The Combine must be passed "
                "under the consistency reading in force, the account must then be funded, "
                "and the MLL RESETS TO THE STARTING BALANCE ON EACH PAYOUT - so a withdrawal "
                "spends the buffer that keeps the account alive.",
    }


# ======================================================================================
# MONTE CARLO - resampling the observed ledger, never manufacturing trades
# ======================================================================================

def monte_carlo(daily: list[dict], ledger: list[dict]) -> dict:
    rng = random.Random(SEED)
    day_pnl = [d["net_pnl"] for d in daily]
    trade_pnl = [t["net_pnl"] for t in ledger]
    target = ts.COMBINE_PROFIT_TARGET[ACCOUNT].value
    mll = ts.MLL[ACCOUNT].value

    def walk(seq):
        """Cumulative P&L, plus whether it hit +target or -MLL first (EOD marks only)."""
        run, peak, dd, hit = 0.0, 0.0, 0.0, None
        for i, x in enumerate(seq):
            run += x
            peak = max(peak, run)
            dd = max(dd, peak - run)
            if hit is None and run >= target:
                hit = ("TARGET", i + 1)
            if hit is None and run <= -mll:
                hit = ("MLL", i + 1)
        return run, dd, hit

    def summarise(samples):
        ends = [s[0] for s in samples]
        dds = [s[1] for s in samples]
        hits = [s[2] for s in samples]
        to_target = [h[1] for h in hits if h and h[0] == "TARGET"]
        return {
            "reps": len(samples),
            "median_ending_pnl": round(_q(ends, 0.5), 2),
            "p05_ending_pnl": round(_q(ends, 0.05), 2),
            "p25_ending_pnl": round(_q(ends, 0.25), 2),
            "p75_ending_pnl": round(_q(ends, 0.75), 2),
            "p95_ending_pnl": round(_q(ends, 0.95), 2),
            "prob_negative_ending_pnl": round(
                sum(1 for x in ends if x < 0) / len(ends), 4),
            "prob_mll_breach_eod": round(
                sum(1 for h in hits if h and h[0] == "MLL") / len(hits), 4),
            "prob_reach_target_first": round(
                sum(1 for h in hits if h and h[0] == "TARGET") / len(hits), 4),
            "median_max_drawdown": round(_q(dds, 0.5), 2),
            "p95_max_drawdown": round(_q(dds, 0.95), 2),
            "median_sessions_to_target": round(_q(to_target, 0.5), 1) if to_target else None,
        }

    n_days = len(day_pnl)
    out = {}

    # A. trade-sequence bootstrap: same trade count, resampled order/identity
    if trade_pnl:
        samples = []
        for _ in range(MC_REPS):
            seq = [rng.choice(trade_pnl) for _ in range(len(trade_pnl))]
            samples.append(walk(seq))
        out["A_trade_bootstrap"] = summarise(samples)

    # B. daily-P&L bootstrap: same session count, iid resampled days
    samples = [walk([rng.choice(day_pnl) for _ in range(n_days)]) for _ in range(MC_REPS)]
    out["B_daily_bootstrap"] = summarise(samples)

    # C. moving-block bootstrap, preserving short-run serial dependence
    block = 20
    samples = []
    for _ in range(MC_REPS):
        seq = []
        while len(seq) < n_days:
            start = rng.randrange(max(1, n_days - block))
            seq.extend(day_pnl[start:start + block])
        samples.append(walk(seq[:n_days]))
    out["C_moving_block_bootstrap"] = {**summarise(samples), "block_sessions": block}

    # D. Topstep path simulation: the same resampled days, through the certified twin
    template = twin_days(daily)
    try:
        resampled = P.moving_block(template, block=block, reps=200, seed=SEED)
        passes = breaches = unfinished = 0
        for path in resampled:
            twin = TopstepTwin(size=ACCOUNT, payout_policy=NEVER, strict_path=True)
            r = twin.run(list(path))
            if r.combine_days is not None:
                passes += 1
            elif r.breach_day is not None:
                breaches += 1
            else:
                unfinished += 1
        n = passes + breaches + unfinished
        out["D_topstep_path_simulation"] = {
            "reps": n, "block_sessions": block,
            "passed": passes, "breached": breaches, "unfinished": unfinished,
            "share_passed": round(passes / n, 4) if n else 0.0,
            "share_breached": round(breaches / n, 4) if n else 0.0,
        }
    except Exception as exc:                                     # noqa: BLE001
        out["D_topstep_path_simulation"] = {"unavailable": str(exc)}

    out["LABEL"] = ("CONDITIONAL HISTORICAL RESAMPLING. Every figure is a property of the "
                    "observed sample re-ordered; none is a probability of future success. "
                    "With a handful of trades the resample draws from a handful of numbers, "
                    "so the percentiles describe those numbers and not the strategy.")
    out["distinct_trades_resampled"] = len(trade_pnl)
    out["distinct_sessions_resampled"] = n_days
    return out


def withdrawal_paths(daily: list[dict]) -> dict:
    """The payout policy materially changes MLL survival. Measured, not assumed."""
    days = twin_days(daily)
    policies = {
        "no_withdrawal": NEVER,
        "first_eligible_full": IMMEDIATE,
        "first_eligible_keep_1000_buffer": PayoutPolicy(min_buffer_after=1000.0),
        "repeated_half": PayoutPolicy(fraction=0.5),
    }
    out = {}
    for name, policy in policies.items():
        r = run_twin(days, policy)
        out[name] = {
            "terminal_stage": r["terminal_stage"],
            "reached_funding": r["reached_funding"],
            "payouts": len(r["payouts"]),
            "total_paid_out": r["total_paid_out"],
            "final_balance": r["final_balance"],
            "breach_day": r["breach_day"],
            "breach_reason": r["breach_reason"],
            "min_buffer_to_mll": r["min_buffer_to_mll"],
        }
    return out


# ======================================================================================
# INDEPENDENT RECONCILIATION
# ======================================================================================

def reconcile(ledger: list[dict], daily: list[dict], instrument: str,
              profile_name: str) -> dict:
    """Recompute every trade through code that shares nothing with the engine."""
    spec = SPECS[instrument]
    pv_per_contract = spec.point_value / spec.contracts
    rt_per_contract = spec.commission_round_turn / spec.contracts

    mismatches = []
    for t in ledger:
        d = 1 if t["direction"] == "LONG" else -1
        #: The engine reports GROSS at the IDEAL (unslipped) prices and slippage on its own
        #: line, so the reference is handed the same ideal prices - otherwise the two would
        #: be computing different quantities and agreeing would mean nothing.
        entry_slip = t["entry_slippage_ticks"] * spec.tick
        exit_slip = t["exit_slippage_ticks"] * spec.tick
        ideal_entry = t["entry_price"] - entry_slip * d
        ideal_exit = t["exit_price"] + exit_slip * d
        gross, cost, _ = reference_pnl_one_trade(
            ideal_entry, ideal_exit, d, spec.contracts, pv_per_contract, rt_per_contract)
        slip_cost = (entry_slip + exit_slip) * spec.point_value
        net = gross - slip_cost - cost
        for field, mine, theirs in (("gross_pnl", t["gross_pnl"], gross),
                                    ("commission", t["commission"], cost),
                                    ("slippage_cost", t["slippage_cost"], slip_cost),
                                    ("net_pnl", t["net_pnl"], net)):
            if abs(mine - theirs) > 1e-9:
                mismatches.append({"trade_id": t["trade_id"], "field": field,
                                   "ledger": mine, "reference": theirs,
                                   "difference": mine - theirs})

    #: and the daily roll-up, recomputed by explicit loop rather than by the same sum
    by_day: dict[str, float] = {}
    for t in ledger:
        by_day[t["trading_day"]] = by_day.get(t["trading_day"], 0.0) + t["net_pnl"]
    for d in daily:
        mine = d["net_pnl"]
        theirs = by_day.get(d["trading_day"], 0.0)
        if abs(mine - theirs) > 1e-9:
            mismatches.append({"trading_day": d["trading_day"], "field": "daily_net_pnl",
                               "ledger": mine, "reference": theirs,
                               "difference": mine - theirs})

    #: and the equity total
    total_ledger = sum(t["net_pnl"] for t in ledger)
    total_daily = sum(d["net_pnl"] for d in daily)
    if abs(total_ledger - total_daily) > 1e-9:
        mismatches.append({"field": "total_net_pnl", "ledger": total_ledger,
                           "reference": total_daily,
                           "difference": total_ledger - total_daily})

    return {
        "instrument": instrument, "profile": profile_name,
        "trades_checked": len(ledger),
        "fields_checked_per_trade": 4,
        "tolerance": 1e-9,
        "mismatches": mismatches,
        "AGREES": not mismatches,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="src", default="research/vwap_v1/backtest.json")
    ap.add_argument("--out", default="research/vwap_v1/analysis.json")
    args = ap.parse_args()

    data = json.loads((REPO / args.src).read_text(encoding="utf-8"))
    out = {"topstep_profile": topstep_profile(), "seed": SEED, "mc_reps": MC_REPS,
           "runs": {}}

    for key, r in data["runs"].items():
        inst, profile = key.split(":")
        days = twin_days(r["daily"])
        twin = run_twin(days, NEVER)
        block = {
            "instrument": inst, "profile": profile,
            "twin_no_withdrawal": twin,
            "pass_paths": pass_paths(days),
            "payout": payout_analysis(r["daily"], twin),
            "monte_carlo": monte_carlo(r["daily"], r["ledger"]),
            "withdrawal_paths": withdrawal_paths(r["daily"]),
            "reconciliation": reconcile(r["ledger"], r["daily"], inst, profile),
        }
        out["runs"][key] = block
        rec = block["reconciliation"]
        print(f"  {key:26} twin {twin['terminal_stage']:<18} "
              f"pass-paths {block['pass_paths']['HISTORICAL_PATH_PASS_RATE']:>6.1%}  "
              f"reconcile {'AGREES' if rec['AGREES'] else 'MISMATCH'}")

    dest = REPO / args.out
    dest.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {dest.relative_to(REPO)}")

    bad = [k for k, v in out["runs"].items() if not v["reconciliation"]["AGREES"]]
    if bad:
        print(f"\nRECONCILIATION MISMATCH in {bad} - results must not be published")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
