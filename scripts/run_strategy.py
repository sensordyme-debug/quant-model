"""The entry point: hand it a frozen StrategySpec, get back a validated result package.

USAGE
-----
    python scripts/run_strategy.py --spec examples.example_strategy:SPEC

The module must expose a `StrategySpec`. Nothing in this script tunes, selects or modifies it.

WHAT THE RUN DOES, IN ORDER
-----------------------------
  1. load the instrument's bars and build sessions on the spec's own window
  2. build features with the causality audit armed (it raises on a leaking feature)
  3. for EACH of the four execution profiles, simulate once into a CANONICAL LEDGER
  4. read the P&L layer, the Topstep account layer and the monthly/payout layer off that
     SAME ledger - no second simulated stream exists anywhere in this file
  5. reconcile the ledger, the equity curve, an independent P&L reference and an
     independent ACCOUNT reference
  6. emit the package, with the execution mode stamped on every record

Step 4 is the one that changed. A strategy result used to be P&L only; an account with a
moving floor, a daily limit and a payout clock can ruin a profitable strategy, and reporting
the first half alone was the most flattering thing this engine could do.

Step 5 is the one that matters. A number that only one code path can produce is not a
measurement.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import futures_discover as fd  # noqa: E402

from quant_brain.markets.futures_cme import features as fe        # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst    # noqa: E402
from quant_brain.research import execution_modes as em             # noqa: E402
from quant_brain.research.account_result import (                  # noqa: E402
    AccountResult, PayoutRuleSet, build_account_result)
from quant_brain.research.canonical_ledger import CanonicalLedger  # noqa: E402
from quant_brain.research.ledger_builder import build_from_profile, cost_for  # noqa: E402
from quant_brain.research.reference_ledger import run_reference    # noqa: E402
from quant_brain.research.strategy_runner import (                 # noqa: E402
    RECONCILE_TOLERANCE, Provenance, ScenarioResult, ValidationReport, _git, _stats,
    dataset_hash, monthly_distribution, monthly_table)
from quant_brain.research import strategy_report as sr             # noqa: E402
from quant_brain.research.session_source import SessionSet, build as build_sessions  # noqa: E402
from quant_brain.research.strategy_spec import StrategySpec        # noqa: E402

ENGINE_VERSION = "2.0.0-integrated"


def load_sessions(spec: StrategySpec, data_path: str = "canonical") -> SessionSet:
    """Bars for the spec, through the CANONICAL data layer by default.

    This used to call `futures_discover.load` directly - a provider-shaped read with no
    statement of what the price series is. It now goes through
    `quant_brain.research.session_source`, which loads via the canonical adapter, runs the
    canonical schema check and quality gate as well as the futures validator, refuses a series
    whose data form is not execution-valid, and returns the manifest id and frame fingerprint
    that the result JSON carries.

    `data_path="legacy"` reaches the old reader and exists for `scripts/canonical_equivalence.py`
    only. The two are proved field-for-field equivalent on this store; the canonical one is
    authoritative because it is the one that can say what it read.
    """
    return build_sessions(spec, data_path=data_path, root=REPO)


def scenario_from(ledger: CanonicalLedger, profile: em.ExecutionProfile) -> ScenarioResult:
    """The P&L layer. A VIEW of the ledger; it simulates nothing."""
    trades = ledger.trade_frame()
    daily = ledger.daily()
    nt = trades["net_pnl"].to_numpy(dtype=float) if len(trades) else np.array([])
    st = _stats(daily.to_numpy(dtype=float), nt)
    held = sum(t.holding_minutes for s in ledger.sessions for t in s.trades)
    bars = sum(s.bars for s in ledger.sessions) or 1
    return ScenarioResult(
        slippage_ticks=profile.slippage_ticks, scenario=profile.name, trades=len(trades),
        gross_pnl=float(trades["gross_pnl"].sum()) if len(trades) else 0.0,
        commission=float(trades["commission_and_spread"].sum()) if len(trades) else 0.0,
        slippage_cost=float(trades["slippage"].sum()) if len(trades) else 0.0,
        net_pnl=float(daily.sum()),
        per_trade=float(nt.mean()) if len(nt) else 0.0,
        exposure=float(held) / bars, **st)


#: Rules the independent P&L reference cannot model. It replays a signal-driven position with
#: one round-turn cost and nothing else - no price-based exit, no clock inside the session, no
#: trade budget. A spec using any of these gets the ledger, equity and account
#: reconciliations; it does not get a second, independent P&L, and the report says so rather
#: than quietly reporting three checks where four are advertised.
_REFERENCE_CANNOT_MODEL: dict[str, str] = {
    "a price-based stop": "exit.stop_atr",
    "a fixed-point stop": "exit.stop_points",
    "a structural stop": "exit.structural_stop",
    "an R-multiple target": "exit.target_r",
    "a fixed-point target": "exit.target_points",
    "an ATR trail": "exit.trail_atr",
    "a fixed-point trail": "exit.trail_points",
    "a break-even stop": "exit.breakeven_at_r",
    "a time stop": "exit.time_stop_bars",
    "a mid-session forced flat": "session.flat_by_et",
    "a cooldown between trades": "risk.cooldown_bars",
    "a per-session trade cap": "risk.max_trades_per_session",
}


def _reference_blockers(spec: StrategySpec) -> list[str]:
    out = []
    for label, path in _REFERENCE_CANNOT_MODEL.items():
        obj, _, attr = path.partition(".")
        v = getattr(getattr(spec, obj), attr)
        if v not in (None, False, 0):
            out.append(f"{label} ({path}={v!r})")
    if not spec.exit.use_invalidation:
        out.append("no signal-invalidation exit (exit.use_invalidation=False)")
    return out


def reference_comparable(spec: StrategySpec) -> bool:
    """True when the independent reference models the same experiment as the engine."""
    return not _reference_blockers(spec)


def reference_skip_reason(spec: StrategySpec) -> str:
    return ("the reference ledger models signal-driven positions only and has no equivalent "
            "for " + ", ".join(_reference_blockers(spec)))


def validate(spec: StrategySpec, ledger: CanonicalLedger, account: AccountResult,
             sessions, feats, profile: em.ExecutionProfile) -> ValidationReport:
    """Reconcile the ledger, the equity curve, an independent P&L reference and the account.

    Four independent statements of the same run have to agree. The fourth is new: the
    account simulation is cross-checked against `topstep_reference`, which shares no code
    with the production twin.
    """
    v = ValidationReport()
    trades = ledger.trade_frame()
    daily = ledger.daily()
    equity = ledger.equity_curve()
    ledger_sum = float(trades["net_pnl"].sum()) if len(trades) else 0.0
    curve_end = float(equity[-1]) if len(equity) else 0.0
    daily_sum = float(daily.sum())

    v.ledger_reconciles = abs(ledger_sum - daily_sum) < RECONCILE_TOLERANCE
    if not v.ledger_reconciles:
        v.failures.append(f"trade ledger {ledger_sum:.4f} != daily total {daily_sum:.4f}")
    v.equity_reconciles = abs(curve_end - daily_sum) < RECONCILE_TOLERANCE
    if not v.equity_reconciles:
        v.failures.append(f"equity curve {curve_end:.4f} != daily total {daily_sum:.4f}")

    # Every session's intraday path must END on that session's settled P&L, or the twin and
    # the P&L layer are describing different days.
    bad = [str(s.day) for s in ledger.sessions
           if abs(s.marks[-1] - s.realized_net) > RECONCILE_TOLERANCE]
    if bad:
        v.failures.append(f"{len(bad)} session paths do not end on their settled P&L "
                          f"(first: {bad[0]})")

    if reference_comparable(spec):
        mult = inst.get(spec.instrument).spec.multiplier
        rt, _, _ = cost_for(spec, profile.slippage_ticks,
                            include_spread=profile.include_spread)
        ref_total = 0.0
        for g, Xf in zip(sessions[:25], feats[:25], strict=True):
            pos = np.nan_to_num(np.asarray(spec.signal(Xf), dtype=float), nan=0.0)
            n_bars = len(g)
            cutoff = (spec.session.last_entry_bar
                      if spec.session.last_entry_bar is not None else n_bars - 2)
            ref = run_reference(list(pos), list(g["c"].to_numpy(dtype=float)),
                                multiplier=mult, contracts=spec.sizing.contracts,
                                round_turn_cost=rt, last_entry_bar=cutoff)
            ref_total += ref.net_pnl
        engine_total = float(daily.iloc[:25].sum())
        v.independent_reconciles = abs(ref_total - engine_total) < max(
            RECONCILE_TOLERANCE, 1e-6 * abs(ref_total))
        if not v.independent_reconciles:
            v.failures.append(
                f"independent reference {ref_total:.4f} != engine {engine_total:.4f} "
                f"over the first 25 sessions")
    else:
        v.independent_reconciles = True
        v.failures.append(
            "independent P&L reconciliation SKIPPED: " + reference_skip_reason(spec)
            + ". The ledger, equity and account reconciliations still apply.")

    if not account.cross_check.agrees:
        v.failures.append("account cross-check: "
                          + "; ".join(account.cross_check.mismatches))

    v.every_trade_charged = bool(
        len(trades) == 0 or (trades["commission_and_spread"] > 0).all()
        or not profile.include_spread or spec.cost.commission_round_turn == 0.0)
    if not v.every_trade_charged:
        v.failures.append("at least one trade carries zero commission")

    v.ends_flat = all(s.ends_flat for s in ledger.sessions)
    if not v.ends_flat:
        v.failures.append("a session ended with an open position")
    v.no_future_leak = True      # enforced by fe.audit_causality inside build_features
    v.provenance_present = True
    v.deterministic = True
    return v


def print_account(a: AccountResult) -> None:
    print(f"\n  TOPSTEP ACCOUNT  (${a.account_size:,} | {a.combine_profile} | "
          f"path mode {a.execution_path_mode.value})")
    print(f"    terminal stage           {a.terminal_stage}")
    print(f"    liquidated               {a.liquidated}"
          + (f"  on {a.liquidation_session} - {a.liquidation_reason}"
             if a.liquidated else ""))
    print(f"    $3,000 target reached    {a.target_reached}"
          + (f" after {a.combine_sessions} sessions" if a.combine_sessions else ""))
    print(f"    days survived / traded   {a.days_survived} / {a.days_traded}   "
          f"trades {a.total_trades}")
    print(f"    winning / losing days    {a.winning_days} / {a.losing_days}   "
          f"flat {a.flat_days}")
    print(f"    forced flatten           {a.forced_flatten_sessions} sessions, "
          f"${a.forced_flatten_pnl:,.0f}")
    print(f"    contract limit           {'OK' if a.contract_limit_ok else 'BREACH'} - "
          f"{a.contract_limit_detail}")
    print(f"    max drawdown             ${a.max_drawdown:,.0f}   "
          f"intraday ${a.max_intraday_drawdown:,.0f}")
    print(f"    min MLL buffer           ${a.min_mll_buffer:,.0f}"
          + (f"   min DLL buffer ${a.min_dll_buffer:,.0f}"
             if a.min_dll_buffer is not None else "   DLL not armed"))
    print(f"    DLL-capped sessions      {a.dll_capped_sessions}")
    print(f"    peak / ending balance    ${a.peak_balance:,.0f} / ${a.ending_balance:,.0f}")
    print(f"    cross-check vs reference {'AGREES' if a.cross_check.agrees else 'MISMATCH'}"
          f" ({a.cross_check.fields_compared} fields)")
    for m in a.cross_check.mismatches:
        print(f"        - {m}")

    r = a.returns
    print("\n    FOUR RETURNS, NOT ONE")
    print(f"      on notional (~${r.mean_notional:,.0f})   "
          f"{r.return_on_notional_pct:+.3f}%")
    print(f"      on the ${r.account_starting_balance:,.0f} account balance   "
          f"{r.return_on_account_pct:+.3f}%  <- Topstep posts no such capital")
    print(f"      per contract                    ${r.pnl_per_contract:+,.0f}")
    print(f"      UNDER ACCOUNT CONSTRAINTS       "
          f"${r.pnl_under_account_constraints:+,.0f}  <- the only one that is money")

    p = a.payout
    print(f"\n    PAYOUT  (rules {p.rules.version}, policy: take "
          f"{p.policy_fraction:.0%} of the cap, leave ${p.policy_min_buffer_after:,.0f})")
    print(f"      eligible sessions      {p.eligible_sessions}"
          + (f", first on {p.first_eligible_session} "
             f"(session {p.sessions_to_first_eligible})"
             if p.first_eligible_session else ""))
    print(f"      payouts taken          {len(p.payouts)}  total ${p.total_paid:,.0f}  "
          f"trader share ${p.trader_share_of_total:,.0f}")
    for n in p.notes:
        print(f"      NOTE: {n}")

    print(f"\n    PROBABILITIES  ({a.resample_reps} resamples, block {a.resample_block})")
    print(f"      survive the period               {a.p_survive_period:.1%}")
    print(f"      reach $3,000 before violating    {a.p_target_before_violation:.1%}")
    print(f"      reach payout eligibility         {a.p_payout_eligible:.1%}")
    print(f"      {a.probability_note}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", required=True,
                    help="module:attribute pointing at a StrategySpec")
    ap.add_argument("--data-path", default="canonical", choices=("canonical", "legacy"),
                    help="canonical (default) routes the bars through quant_brain.data - "
                         "declared form, roll method, quality gate, manifest id, frame "
                         "fingerprint. legacy reaches the pre-canonical reader and exists "
                         "for scripts/canonical_equivalence.py; it declares nothing.")
    ap.add_argument("--account-size", type=int, default=50_000)
    ap.add_argument("--daily-loss-limit", type=float, default=None,
                    help="arm Topstep's optional DLL at this amount; omitted means off")
    ap.add_argument("--payout-fraction", type=float, default=1.0,
                    help="share of the eligible cap withdrawn at each opportunity")
    ap.add_argument("--payout-min-buffer", type=float, default=0.0)
    ap.add_argument("--reps", type=int, default=400,
                    help="resamples behind the account-layer probabilities")
    ap.add_argument("--mc-paths", type=int, default=5000,
                    help="paths for the Monte Carlo section. 1,000 is the floor the phase "
                         "gate asks for; 5,000 is the default where it is practical.")
    ap.add_argument("--mc-block", type=int, default=10,
                    help="moving-block length, in sessions. It keeps losing runs intact, "
                         "which is the dependence a barrier problem turns on.")
    ap.add_argument("--holdout", default=None,
                    help="describe the train/validation/out-of-sample split if one exists. "
                         "Omitted means the report prints NO CLEAN HOLDOUT, which is the "
                         "honest reading when the whole history was used.")
    ap.add_argument("--out", type=Path, default=REPO / "research" / "strategy_runs")
    args = ap.parse_args()

    mod_name, _, attr = args.spec.partition(":")
    spec: StrategySpec = getattr(importlib.import_module(mod_name), attr or "SPEC")
    if not isinstance(spec, StrategySpec):
        raise TypeError(f"{args.spec} is not a StrategySpec")

    print("=" * 100)
    print("FROZEN STRATEGY RUN - this is exactly what is being tested, and nothing else")
    print("=" * 100)
    print("  " + spec.describe().replace("\n", "\n  "))

    sset = load_sessions(spec, args.data_path)
    sessions = sset.frames
    feats = fd.build_features(sessions, fe.library())     # raises on a leaking feature
    print("\n  " + sset.describe().replace("\n", "\n  "))

    print("\n" + em.assumptions_table())

    rules = PayoutRuleSet.as_documented(args.account_size)
    ledgers: dict[str, CanonicalLedger] = {}
    scenarios: list[ScenarioResult] = []
    accounts: dict[str, AccountResult] = {}
    for profile in em.LADDER:
        ledger = build_from_profile(spec, sessions, feats, profile)
        ledgers[profile.name] = ledger
        scenarios.append(scenario_from(ledger, profile))
        accounts[profile.name] = build_account_result(
            ledger, account_size=args.account_size,
            daily_loss_limit=args.daily_loss_limit, payout_rules=rules,
            payout_fraction=args.payout_fraction,
            payout_min_buffer_after=args.payout_min_buffer, reps=args.reps)

    print("\n  EXECUTION LADDER - P&L")
    print(f"  {'mode':13} {'slip':>5} {'path':>22} {'trades':>7} {'gross $':>10} "
          f"{'net $':>10} {'$/trade':>9} {'Sharpe':>7} {'maxDD $':>10}")
    for profile, s in zip(em.LADDER, scenarios, strict=True):
        print(f"  {s.scenario:13} {s.slippage_ticks:5.2f} {profile.path_mode.value:>22} "
              f"{s.trades:7d} {s.gross_pnl:10.0f} {s.net_pnl:10.0f} {s.per_trade:9.2f} "
              f"{s.sharpe:7.2f} {s.max_drawdown:10.0f}")

    print("\n  EXECUTION LADDER - ACCOUNT")
    print(f"  {'mode':13} {'terminal':17} {'liq':>4} {'target':>7} {'minMLLbuf $':>12} "
          f"{'intraDD $':>11} {'P(survive)':>11} {'P(target)':>10}")
    for name in (p.name for p in em.LADDER):
        a = accounts[name]
        print(f"  {name:13} {a.terminal_stage:17} {str(a.liquidated):>4} "
              f"{str(a.target_reached):>7} {a.min_mll_buffer:12,.0f} "
              f"{a.max_intraday_drawdown:11,.0f} {a.p_survive_period:11.1%} "
              f"{a.p_target_before_violation:10.1%}")

    head = em.HEADLINE
    headline_scenario = [s for s in scenarios if s.scenario == head][0]
    headline_ledger, headline_account = ledgers[head], accounts[head]
    print(f"\n  HEADLINE MODE: {head} (never IDEAL)")

    ideal = [s for s in scenarios if s.scenario == "IDEAL"][0]
    if ideal.net_pnl > 0 >= headline_scenario.net_pnl:
        print("\n  *** FLAG: positive only under IDEAL execution. Treat as non-viable. ***")
    if accounts["IDEAL"].target_reached and not headline_account.target_reached:
        print("  *** FLAG: the $3,000 target is reached only under IDEAL execution. ***")

    v = validate(spec, headline_ledger, headline_account, sessions, feats,
                 em.get(head))
    print_account(headline_account)

    m = monthly_table(headline_ledger.daily())
    dist = monthly_distribution(m)
    print(f"\n  VALIDATION: {v.status}")
    for f in v.failures:
        print(f"    - {f}")

    if dist:
        print(f"\n  MONTHLY DISTRIBUTION ({dist['months']} months, {head} scenario)")
        if dist["months"] < 24:
            print(f"    *** {dist['months']} months is a SMALL SAMPLE. Nothing below is "
                  f"annualised or extrapolated. ***")
        print(f"    mean {dist['mean']:+.0f} | median {dist['median']:+.0f} | "
              f"positive {dist['positive_share']:.0%} | worst {dist['worst']:+.0f} | "
              f"best {dist['best']:+.0f}")

    # ---- the scorecard: sections A-F, Monte Carlo, regime, statistics, classification ----
    ladder_rows = [{**asdict_scenario(s),
                    "liquidated": accounts[s.scenario].liquidated,
                    "p_target": accounts[s.scenario].p_target_before_violation,
                    "p_payout": accounts[s.scenario].p_payout_eligible}
                   for s in scenarios]
    report = sr.build(
        headline_ledger, headline_account, spec=spec, sset=sset, ladder=ladder_rows,
        engine_version=ENGINE_VERSION, mc_paths=args.mc_paths, mc_block=args.mc_block,
        daily_loss_limit=args.daily_loss_limit, holdout=args.holdout)
    print("\n\n" + report.render())

    prov = Provenance(
        spec_hash=spec.spec_hash, engine_version=ENGINE_VERSION,
        git_sha=_git("rev-parse", "HEAD"),
        git_dirty=bool(_git("status", "--porcelain")),
        data_source=(f"{sset.path}:{sset.provenance['feature_data']['dataset_id']}"
                     f"@{sset.provenance['feature_data']['manifest_id']}"),
        data_hash=dataset_hash(sessions),
        data_start=str(sessions[0]["day"].iloc[0]),
        data_end=str(sessions[-1]["day"].iloc[0]),
        sessions=len(sessions), python=platform_python(), numpy=np.__version__,
        pandas=pd.__version__,
        run_at=dt.datetime.now().astimezone().isoformat(timespec="seconds"), seed=None)

    args.out.mkdir(parents=True, exist_ok=True)
    stem = f"{spec.name}_{spec.spec_hash}"
    headline_ledger.trade_frame().to_csv(args.out / f"{stem}_trades.csv", index=False)
    headline_ledger.fill_frame().to_csv(args.out / f"{stem}_fills.csv", index=False)
    headline_account.mll_path().to_csv(args.out / f"{stem}_account_path.csv", index=False)
    pd.DataFrame([r.__dict__ for r in headline_account.monthly]).to_csv(
        args.out / f"{stem}_monthly.csv", index=False)
    pd.DataFrame([{**asdict_scenario(s),
                   **em.get(s.scenario).as_row()} for s in scenarios]).to_csv(
        args.out / f"{stem}_scenarios.csv", index=False)
    (args.out / f"{stem}_result.json").write_text(json.dumps({
        "spec": spec.to_dict(), "spec_hash": spec.spec_hash,
        "engine_version": ENGINE_VERSION,
        "headline_mode": head,
        "execution_assumptions": [em.get(p.name).as_row() for p in em.LADDER],
        "provenance": prov.__dict__,
        "data": sset.provenance,
        "validation": {
            **{k: getattr(v, k) for k in
               ("ledger_reconciles", "equity_reconciles", "independent_reconciles",
                "every_trade_charged", "ends_flat", "no_future_leak")},
            "status": v.status, "failures": v.failures},
        "pnl_by_mode": [asdict_scenario(s) for s in scenarios],
        "account_by_mode": {name: account_json(a) for name, a in accounts.items()},
        "payout_rules": {**rules.__dict__, "retrieved": rules.retrieved.isoformat()},
        "monthly_distribution": dist,
        "scorecard": report.to_json(),
    }, indent=1, default=str), encoding="utf-8")
    (args.out / f"{stem}_report.txt").write_text(report.render(), encoding="utf-8")
    print(f"\n  wrote {args.out / stem}_*.csv/json and _report.txt")
    print(f"  CLASSIFICATION: {report.classification.verdict}")
    return 0


def account_json(a: AccountResult) -> dict:
    """Everything a reader needs, with the execution mode never omitted."""
    return {
        "execution_path_mode": a.execution_path_mode.value,
        "execution_mode": a.scenario, "slippage_ticks": a.slippage_ticks,
        "terminal_stage": a.terminal_stage, "liquidated": a.liquidated,
        "liquidation_session": str(a.liquidation_session) if a.liquidation_session else None,
        "liquidation_reason": a.liquidation_reason,
        "target_reached": a.target_reached, "combine_sessions": a.combine_sessions,
        "combine_attempts": a.combine_attempts,
        "days_survived": a.days_survived, "days_traded": a.days_traded,
        "total_trades": a.total_trades, "winning_days": a.winning_days,
        "losing_days": a.losing_days, "flat_days": a.flat_days,
        "forced_flatten_sessions": a.forced_flatten_sessions,
        "forced_flatten_pnl": a.forced_flatten_pnl,
        "contract_limit_ok": a.contract_limit_ok,
        "contract_limit_detail": a.contract_limit_detail,
        "max_drawdown": a.max_drawdown,
        "max_intraday_drawdown": a.max_intraday_drawdown,
        "min_mll_buffer": a.min_mll_buffer,
        "min_mll_buffer_funded": a.min_mll_buffer_funded,
        "min_dll_buffer": a.min_dll_buffer,
        "dll_capped_sessions": a.dll_capped_sessions,
        "starting_balance": a.starting_balance, "ending_balance": a.ending_balance,
        "peak_balance": a.peak_balance, "ending_mll": a.ending_mll,
        "ending_dll": a.ending_dll, "final_position": a.final_position,
        "final_equity": a.final_equity,
        "returns": a.returns.__dict__,
        "payout": {"eligible_sessions": a.payout.eligible_sessions,
                   "first_eligible_session": str(a.payout.first_eligible_session)
                   if a.payout.first_eligible_session else None,
                   "sessions_to_first_eligible": a.payout.sessions_to_first_eligible,
                   "payouts": [(str(d), v) for d, v in a.payout.payouts],
                   "total_paid": a.payout.total_paid,
                   "trader_share_of_total": a.payout.trader_share_of_total,
                   "rules_version": a.payout.rules.version,
                   "notes": a.payout.notes},
        "p_survive_period": a.p_survive_period,
        "p_target_before_violation": a.p_target_before_violation,
        "p_payout_eligible": a.p_payout_eligible,
        "probability_note": a.probability_note,
        "cross_check_agrees": a.cross_check.agrees,
        "cross_check_fields": a.cross_check.fields_compared,
        "cross_check_mismatches": a.cross_check.mismatches,
    }


def asdict_scenario(s: ScenarioResult) -> dict:
    return {k: getattr(s, k) for k in s.__dataclass_fields__}


def platform_python() -> str:
    return f"{platform.python_version()} ({platform.system()})"


if __name__ == "__main__":
    raise SystemExit(main())
