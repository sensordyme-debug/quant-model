"""`python -m quant_brain <group> <command>` - the things worth asking from a terminal.

Built around the repository's existing convention (per-module `_main`, reached with
`python -m quant_brain.core.dataquality`) rather than the `python -m src.cli` shape the brief
suggests, because there is no `src/` here and inventing one would be a rename dressed as
architecture.

Every command answers a question that is genuinely hard to answer otherwise:

    mode                what is THIS process allowed to do, and why
    topstep rules       every rule with its source and confidence tier
    topstep unresolved  what still needs the owner before money is spent
    topstep readiness   the gate between here and a practice account
    broker list         every adapter and the authority it demands
    research ledger     how many hypotheses have been tried, and what happened

Commands that would need a venue connection are absent rather than stubbed. A `broker test`
that printed "OK" without connecting would be worse than not having one.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _mode(_args) -> int:
    from quant_brain.core.mode import LIVE_ENV, Mode, from_environment
    a = from_environment()
    print(f"  authority   {a.describe()}")
    print(f"  {LIVE_ENV:<26}{'set' if _live_set() else 'not set'}")
    print()
    print("  what that permits:")
    for m in Mode:
        mark = "yes" if a.permits(m) else "NO "
        note = "  <- real money" if m.risks_real_money else ""
        print(f"    {mark}  {m.name}{note}")
    print()
    print("  Live execution additionally requires an explicit argument and a per-account")
    print("  approval file; configuration alone cannot grant it.")
    return 0


def _live_set() -> bool:
    import os

    from quant_brain.core.mode import LIVE_ENV
    return os.environ.get(LIVE_ENV, "").strip().lower() in {"1", "true", "yes"}


def _topstep_rules(args) -> int:
    from quant_brain.markets.futures_cme import topstep as ts
    if args.raw:
        print(ts.rulebook())
        return 0
    rules = _all_rules(ts)
    by_tier: dict[str, int] = {}
    for r in rules.values():
        by_tier[r.confidence.name] = by_tier.get(r.confidence.name, 0) + 1
    print(f"  Topstep rulebook, retrieved {ts.RETRIEVED}")
    print(f"  {len(rules)} rules: " + ", ".join(f"{k}={v}" for k, v in sorted(by_tier.items())))
    print()
    for name, r in sorted(rules.items()):
        print(f"  {r.confidence.name:<7} {name:<34} {r.value!r}")
    print()
    print("  --raw for every citation. DOC = read on a Topstep-owned page; SEARCH = seen in")
    print("  a site summary only; OWNER = published nowhere reachable, you must supply it.")
    return 0


def _all_rules(ts) -> dict:
    out = {}
    for name in dir(ts):
        obj = getattr(ts, name)
        if isinstance(obj, ts.Rule):
            out[name] = obj
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, ts.Rule):
                    out[f"{name}[{k}]"] = v
    return out


def _topstep_unresolved(_args) -> int:
    from quant_brain.markets.futures_cme import topstep as ts
    gaps = ts.unresolved()
    if not gaps:
        print("  nothing unresolved")
        return 0
    print(f"  {len(gaps)} rule(s) below DOC confidence - read these off your own dashboard")
    print()
    for name, r in gaps.items():
        print(f"  {r.confidence.name:<7} {name}")
        print(f"          value {r.value!r}")
        print(f"          {r.note or r.quote}")
        print()
    return 1        # non-zero: this is a blocking condition, not information


def _topstep_readiness(_args) -> int:
    """The gate between here and a practice account. Every line is checked, not asserted."""
    from quant_brain.markets.futures_cme import topstep as ts
    checks: list[tuple[bool, str]] = []

    gaps = ts.unresolved()
    checks.append((not any("profit_target" in k for k in gaps),
                   "Combine profit target verified"))
    checks.append(("xfa_scaling_plan" not in gaps,
                   "XFA scaling ladder known (published only as an image)"))
    checks.append((Path("data/futures/ES.parquet").exists(), "futures price store present"))
    checks.append((Path("data/futures/ES_quotes.parquet").exists(),
                   "quote store present (spread measured, not assumed)"))

    led = Path("research/experiments_futures.jsonl")
    survived = 0
    if led.exists():
        from quant_brain.research import Ledger
        survived = sum(1 for e in Ledger(led).all() if e.stage.value == "validation")
    checks.append((survived > 0, f"a strategy has survived the funnel ({survived} so far)"))
    checks.append((Path("live/approvals").exists(), "an approval directory exists"))
    checks.append((False, "a prop-firm adapter has been exercised against a real venue"))

    print("  Topstep practice readiness")
    print()
    for ok, what in checks:
        print(f"    {'yes' if ok else 'NO ':<4} {what}")
    blocked = [w for ok, w in checks if not ok]
    print()
    if blocked:
        print(f"  NOT READY: {len(blocked)} of {len(checks)} conditions unmet.")
        print("  The software being complete is not the system being ready.")
        return 1
    print("  All checks pass. That still is not permission - see `python -m quant_brain mode`.")
    return 0


def _broker_list(_args) -> int:
    from quant_brain.core.execution import ExecutionAdapter, SimulatedAdapter
    from quant_brain.core.mode import Mode, from_environment
    rows: list[tuple[str, object, str]] = [
        ("SimulatedAdapter", SimulatedAdapter.requires, "in-memory; nothing leaves")]
    try:
        from quant_brain.brokers.ibkr import IBKRAdapter
        rows.append(("IBKRAdapter", IBKRAdapter.requires, "IB Gateway paper by default"))
    except Exception as exc:                                            # noqa: BLE001
        rows.append(("IBKRAdapter", None, f"unavailable: {type(exc).__name__}"))
    try:
        from quant_brain.brokers.projectx import ProjectXAdapter
        rows.append(("ProjectXAdapter", ProjectXAdapter.requires,
                     "TopstepX; dry run by default, cannot send"))
    except Exception as exc:                                            # noqa: BLE001
        rows.append(("ProjectXAdapter", None, f"unavailable: {type(exc).__name__}"))

    held = from_environment()
    print(f"  this process holds {held.mode.name}")
    print()
    print(f"  {'adapter':<20} {'requires':<17} {'reachable':<10} notes")
    for name, req, note in rows:
        if req is None:
            print(f"  {name:<20} {'?':<17} {'-':<10} {note}")
            continue
        assert isinstance(req, Mode)
        print(f"  {name:<20} {req.name:<17} "
              f"{'yes' if held.permits(req) else 'NO':<10} {note}")
    print()
    print(f"  base class default is {ExecutionAdapter.requires.name}, so an adapter that")
    print("  forgets to declare its requirement gets the strictest answer.")
    return 0


def _research_ledger(args) -> int:
    from quant_brain.research import Ledger
    path = Path(args.path)
    if not path.exists():
        print(f"  no ledger at {path}")
        return 1
    led = Ledger(path)
    rows = led.all()
    fams: dict[str, list] = {}
    for e in rows:
        fams.setdefault(e.family, []).append(e)
    print(f"  {path}: {led.summary()}")
    print()
    print(f"  {'family':<40} {'trials':>7} {'passed':>7} {'bar at n':>9}")
    for fam, es in sorted(fams.items()):
        passed = sum(1 for e in es if e.verdict and e.verdict.passed)
        bar = max((e.verdict.threshold for e in es if e.verdict), default=float("nan"))
        print(f"  {fam:<40} {led.trials(fam):>7} {passed:>7} {bar:>9.2f}")
    print()
    print("  The bar rises with the trial count and there is no argument that lowers it.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m quant_brain", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="group", required=True)

    sub.add_parser("mode", help="what this process is allowed to do").set_defaults(fn=_mode)

    ts = sub.add_parser("topstep", help="the Topstep rulebook and readiness")
    tsub = ts.add_subparsers(dest="cmd", required=True)
    p = tsub.add_parser("rules", help="every rule, with its confidence tier")
    p.add_argument("--raw", action="store_true", help="full citations")
    p.set_defaults(fn=_topstep_rules)
    tsub.add_parser("unresolved", help="what still needs the owner").set_defaults(
        fn=_topstep_unresolved)
    tsub.add_parser("readiness", help="the gate to a practice account").set_defaults(
        fn=_topstep_readiness)

    br = sub.add_parser("broker", help="execution adapters")
    bsub = br.add_subparsers(dest="cmd", required=True)
    bsub.add_parser("list", help="adapters and the authority each demands").set_defaults(
        fn=_broker_list)

    rs = sub.add_parser("research", help="the experiment ledger")
    rsub = rs.add_subparsers(dest="cmd", required=True)
    p = rsub.add_parser("ledger", help="trials and verdicts by family")
    p.add_argument("--path", default="research/experiments_futures.jsonl")
    p.set_defaults(fn=_research_ledger)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
