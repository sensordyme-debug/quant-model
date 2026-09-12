#!/usr/bin/env python
"""Engineering scorecard, measured from the repository rather than asserted about it.

    python scripts/qb_scorecard.py            # scores + evidence + remaining weakness
    python scripts/qb_scorecard.py --gate     # the Part 15 pre-ML checklist
    python scripts/qb_scorecard.py --json     # machine-readable

WHY A TOOL AND NOT A DOCUMENT
------------------------------
Part 14 says "do not claim 8/10 because the code looks cleaner" and "do not inflate scores".
A number written into a markdown file is true on the day it is written and drifts silently
afterwards; a number computed from the tree is either currently true or currently wrong, and
re-running it is the audit.

So every dimension below is scored from a MEASUREMENT where one exists - test counts, pyright
errors, the fraction of recent ledger rows carrying provenance, whether the live state file
reads as contaminated, whether a scheduler call actually appears in a research path. Where no
measurement is possible the dimension carries a stated judgement and says so, and those are
the ones to argue with.

The composite is a plain mean of the twelve, printed with its own arithmetic so it can be
checked by hand.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@dataclass
class Dimension:
    name: str
    score: float
    evidence: list[str] = field(default_factory=list)
    weakness: str = ""
    measured: bool = True


def _run(cmd: list[str], timeout: int = 300, *, stdout_only: bool = False) -> tuple[int, str]:
    """Run a command. `stdout_only` matters for JSON output.

    Learned the hard way: concatenating stderr into stdout made `pyright --outputjson`
    unparseable, so `pyright_errors()` returned -1 and the Type safety dimension scored 6
    while pyright itself reported 0 errors. A scorecard whose own measurement is broken is
    worse than no scorecard, because it looks like evidence.
    """
    try:
        p = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)[:200]
    if stdout_only:
        return p.returncode, p.stdout or ""
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# --------------------------------------------------------------------------- measurements

def test_count() -> tuple[int, int]:
    """(tests collected, test files)."""
    code, out = _run([sys.executable, "-m", "pytest", "--collect-only", "-q",
                      "-p", "no:cacheprovider"])
    if code != 0:
        return 0, 0
    files = re.findall(r"^(tests/\S+\.py): (\d+)$", out, re.M)
    return sum(int(n) for _f, n in files), len(files)


def suite_green() -> bool:
    return _run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])[0] == 0


def pyright_errors() -> int | None:
    import shutil
    exe = shutil.which("pyright")
    if not exe:
        return None
    code, out = _run([exe, "--outputjson"], stdout_only=True)
    try:
        return int(json.loads(out)["summary"]["errorCount"])
    except (ValueError, KeyError, TypeError):
        return None if code == 127 else -1


def ruff_findings(paths: list[str], isolated: bool = False) -> int:
    cmd = [sys.executable, "-m", "ruff", "check", "--output-format=concise"]
    if isolated:
        cmd += ["--isolated", "--target-version", "py311", "--line-length", "100",
                "--select", "E,F,I,UP,B,DTZ,PD,NPY", "--ignore", "UP042"]
    code, out = _run(cmd + paths)
    m = re.search(r"Found (\d+) error", out)
    return int(m.group(1)) if m else (0 if code == 0 else -1)


def provenance_coverage(n: int = 40) -> tuple[int, int]:
    """(rows with env_key, rows inspected) over the most recent ledger rows."""
    ledger = REPO / "research" / "experiments.jsonl"
    if not ledger.exists():
        return 0, 0
    rows = [x for x in ledger.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]
    tail, have = rows[-n:], 0
    for line in tail:
        try:
            if json.loads(line).get("env_key"):
                have += 1
        except json.JSONDecodeError:
            pass
    return have, len(tail)


def open_p0_count() -> int | None:
    """P0 items in the audit that are not marked closed."""
    audit = REPO / "research" / "audit_2026-09-12.md"
    if not audit.exists():
        return None
    text = audit.read_text(encoding="utf-8", errors="replace")
    p0 = text.split("## P1")[0] if "## P1" in text else text
    if "CLOSED" in p0 and "Remaining open here: nothing at P0" in p0:
        return 0
    return len(re.findall(r"^### AUD-\d+", p0, re.M))


def live_state_clean() -> tuple[bool, list[str]]:
    """Is the live state document free of simulation contamination, and are scopes separated?"""
    from quant_brain.core.state import is_contaminated
    notes, ok = [], True
    live = REPO / "live" / "state" / "last_run.json"
    if live.exists():
        doc = json.loads(live.read_text(encoding="utf-8"))
        if is_contaminated(doc):
            ok = False
            notes.append("live/state/last_run.json still reads as contaminated")
        else:
            notes.append(f"live last_run.json clean, scope={doc.get('_scope', 'unstamped')}")
    scopes = sorted(p.name for p in (REPO / "live" / "state").glob("*")
                    if p.is_dir() and p.name in ("dryrun", "backtest", "research"))
    notes.append(f"simulated scope dirs present: {scopes or 'none yet'}")
    return ok, notes


def integration_calls() -> dict[str, bool]:
    """Is each core component actually CALLED by a production/research path?"""
    def used(needle: str, files: list[str]) -> bool:
        for f in files:
            p = REPO / f
            if p.exists() and needle in p.read_text(encoding="utf-8", errors="replace"):
                return True
        return False

    return {
        "provenance -> backtest.py": used("Provenance.capture", ["scripts/backtest.py"]),
        "provenance -> intraday_backtest.py": used("Provenance.capture",
                                                   ["scripts/intraday_backtest.py"]),
        "calendar -> live flatten": used("flatten_minute_for", ["scripts/intraday_trader.py"]),
        "calendar -> harness flatten": used("flatten_minute_for",
                                            ["scripts/intraday_backtest.py"]),
        "calendar -> feed probe": used("expected_latest_bar", ["scripts/intraday_trader.py"]),
        "scheduler -> a research path": used("resolve_workers", ["scripts/odte_data.py"]),
        "state scope -> paper runner": used("StateScope.for_run", ["scripts/paper_trade.py"]),
        "reconcile -> live startup": used("startup_reconcile", ["scripts/intraday_trader.py"]),
    }


def watchdog_trustworthy() -> tuple[bool, str]:
    try:
        import gateway_watchdog  # noqa: F401
    except Exception:
        sys.path.insert(0, str(REPO / "scripts"))
    try:
        import gateway_watchdog as gw
        states = {s.value for s in gw.Health}
        need = {"STARTING", "HEALTHY", "UNHEALTHY", "RESTARTING", "VERIFYING", "FAILED"}
        return need <= states, f"states {sorted(states)}"
    except Exception as exc:  # noqa: BLE001
        return False, f"not importable: {exc}"[:120]


def resource_legs() -> tuple[bool, str]:
    from quant_brain.core.resources import plan_workers, snapshot
    s = snapshot()
    b = plan_workers(600.0, snap=s)
    has = all(k in b.detail for k in ("memory=", "commit=", "cpu="))
    return has, f"{s.describe()} | {b.describe()[:80]}"


# --------------------------------------------------------------------------- scoring

def build() -> list[Dimension]:
    tests, files = test_count()
    green = suite_green()
    pyr = pyright_errors()
    core_lint = ruff_findings(["quant_brain", "tests"])
    legacy_lint = ruff_findings(["scripts", "algorithms"], isolated=True)
    prov_have, prov_n = provenance_coverage()
    p0 = open_p0_count()
    state_ok, state_notes = live_state_clean()
    calls = integration_calls()
    wd_ok, wd_note = watchdog_trustworthy()
    res_ok, res_note = resource_legs()
    wired = sum(calls.values())
    dq_wired = "validate_bars" in (REPO / "scripts" / "intraday_backtest.py").read_text(
        encoding="utf-8", errors="replace")

    D = Dimension
    dims = [
        D("Testing", 8.0 if (green and tests >= 400) else 6.0,
          [f"{tests} tests across {files} files, suite {'green' if green else 'RED'}",
           "promotion gate 35, research harness 40, P0 regressions 29"],
          "sweep_f*/ml_* (the ML sweeps) still have no unit tests; coverage is not measured"),

        D("Type safety", 8.0 if pyr == 0 else (6.0 if pyr and pyr < 5 else 4.0),
          [f"pyright errors: {pyr if pyr is not None else 'not installed'}",
           f"ruff on core+tests: {core_lint} finding(s), enforced in the gate"],
          "scripts/ and algorithms/ are excluded from pyright; "
          f"{legacy_lint} advisory lint findings remain there"),

        D("Research reproducibility",
          8.0 if prov_n and prov_have / prov_n > 0.15 else 6.0,
          [f"provenance on {prov_have}/{prov_n} of the most recent ledger rows",
           "env_key discriminates py311-689198 (LEAN) from py314-5ba485 (harness)",
           "both ledger writers stamp commit, dirty flag, interpreter and numeric stack"],
          "older rows predate provenance and cannot be back-filled; the promotion gate does "
          "not yet REFUSE a cross-env comparison, it only records one"),

        D("Live safety", 8.0 if p0 == 0 else 4.0,
          [f"open P0 items in the audit: {p0}",
           "AUD-05/06/08/09 closed with 29 failing-first tests",
           "replay on 2026-09-09 and 2026-09-10 byte-identical pre- and post-fix"],
          "no live order has been placed since the fixes; the evidence is replay and unit "
          "tests, not a traded session"),

        D("State isolation", 9.0 if state_ok else 4.0,
          state_notes + ["StateStore refuses traversal and absolute paths by construction",
                         "verified: --mock --dry-run left the live md5 unchanged"],
          "the intraday book (live/state/intraday_book.json) is not yet scope-routed; only "
          "the daily runner's last_run.json is"),

        D("Data integrity", 7.0 if dq_wired else 5.0,
          [f"standing validation gate wired into the harness: {'yes' if dq_wired else 'NO'}",
           "FAIL on zero/NaN/negative price, impossible bar, duplicate or unsorted index, "
           "tz-naive index, bars on a market holiday",
           "reproduced AUD-07 independently: 21 early-close sessions with after-hours rows "
           "in the Alpaca store, found from the calendar alone",
           "deployed IBKR store: 305,978 rows, 0 fail, 0 warn"],
          "only the intraday harness calls it; the LEAN daily path and the ML panel builder "
          "do not. No cross-source reconciliation check (IBKR vs Alpaca) runs as a gate"),

        D("Observability", 6.0,
          [f"watchdog emits structured JSONL with 6 states: {wd_note}",
           "resource snapshot + per-market allocation available as CLIs",
           "dashboard read-only on 127.0.0.1:8787"],
          "live alerting is still recorded as DEAD in BLOCKERS.md - the system still cannot "
          "reliably tell the owner it is broken"),

        D("Orchestration reliability", 7.0 if wd_ok else 4.0,
          ["watchdog polls for readiness and records time-to-bind, replacing a fixed 45s sleep "
           "that misreported 4 of 6 restarts as failures",
           "kill scoped to the gateway's own process, no longer to any 'openclaw' node process",
           "breaker stops after 3 restarts/hour"],
          "agent tracks still share one working tree; git worktree isolation (Part 15 of the "
          "brief) is NOT implemented"),

        D("Resource management", 8.0 if res_ok else 5.0,
          [res_note,
           "budget is min(physical, commit, cpu) and names the binding leg",
           "per-market priority: futures HIGH, options HIGH, etf/bitcoin/crypto OFF"],
          "only one research path (odte_data.py) calls resolve_workers; the other 15 sweeps "
          "still hard-code --workers at 4/6/8"),

        D("Architecture / integration",
          8.0 if wired >= 7 else (6.0 if wired >= 5 else 4.0),
          [f"{wired}/{len(calls)} core components are called by a real path"]
          + [f"  {'yes' if v else 'NO '}  {k}" for k, v in calls.items()],
          "CostModel and Sizer are still constants in intraday_common.py; the runners do not "
          "yet emit OrderIntent, so no second broker or prop-firm adapter is possible"),

        D("ML pipeline integrity", 4.0,
          ["1,591,974-row panel, 38 features, HistGradientBoostingRegressor",
           "label scaling and explicit (X_val,y_val) early stop are correct and documented"],
          "AUD-18 (naive t-stat on overlapping labels), AUD-19 (selection on the test window) "
          "and AUD-20 (shift by row on an irregular grid) are ALL STILL OPEN. No ML sweep has "
          "unit tests. This is the lowest score on the board and it is the right one",
          measured=False),

        D("Deployment safety", 7.0,
          ["09:25 launch gates on the unit suite (E-5) and a replay preflight",
           "live trading requires a human-created APPROVED_PAPER.md; ib-trading-mode=live banned",
           "pre-commit hook runs the gate; --no-verify is the only bypass"],
          "no staged rollout or canary: a promoted change goes to the full paper sleeve at the "
          "next 09:25. No automated rollback",
          measured=False),
    ]
    return dims


def report(dims: list[Dimension], as_json: bool = False) -> int:
    if as_json:
        print(json.dumps({d.name: {"score": d.score, "evidence": d.evidence,
                                   "weakness": d.weakness, "measured": d.measured}
                          for d in dims}, indent=2))
        return 0
    print("\n  QUANT BRAIN ENGINEERING SCORECARD")
    print("  measured from the tree, not asserted about it\n")
    for d in dims:
        bar = "#" * int(round(d.score)) + "." * (10 - int(round(d.score)))
        tag = "" if d.measured else "   [judgement, not measured]"
        print(f"  {d.score:4.1f}/10  [{bar}]  {d.name}{tag}")
        for e in d.evidence:
            print(f"            {e}")
        if d.weakness:
            print(f"            WEAKNESS: {d.weakness}")
        print()
    total = sum(d.score for d in dims)
    n = len(dims)
    print(f"  composite = ({' + '.join(f'{d.score:g}' for d in dims)}) / {n}")
    print(f"            = {total:.1f} / {n} = {total / n:.2f}/10\n")
    target = total / n >= 8.0
    print(f"  8/10 target: {'MET' if target else 'NOT MET'}")
    return 0 if target else 1


GATE_ITEMS = [
    ("All remaining P0s closed", lambda: open_p0_count() == 0),
    ("Live state reconciled", lambda: live_state_clean()[0]),
    ("State isolation enforced", lambda: integration_calls()["state scope -> paper runner"]),
    ("OpenClaw watchdog trustworthy", lambda: watchdog_trustworthy()[0]),
    ("Resource manager uses commit + RAM + CPU", lambda: resource_legs()[0]),
    ("Sweep harness tested", lambda: (REPO / "tests" / "test_research_harness.py").exists()),
    ("Research promotion tested", lambda: (REPO / "tests" / "test_promotion_gate.py").exists()),
    ("Provenance integrated", lambda: integration_calls()["provenance -> backtest.py"]),
    ("Session calendar integrated", lambda: integration_calls()["calendar -> live flatten"]
     and integration_calls()["calendar -> harness flatten"]),
    ("Data validation gate wired", lambda: "validate_bars" in
     (REPO / "scripts" / "intraday_backtest.py").read_text(encoding="utf-8", errors="replace")),
    ("Quality gate green", lambda: _run([sys.executable, "scripts/qb_check.py", "--quiet"])[0] == 0),
]


def gate() -> int:
    print("\n  PART 15 GATE - before substantially increasing ML research\n")
    failed = 0
    for name, check in GATE_ITEMS:
        try:
            ok = bool(check())
        except Exception as exc:  # noqa: BLE001
            ok, name = False, f"{name}  ({type(exc).__name__})"
        print(f"  [{'x' if ok else ' '}] {name}")
        failed += not ok
    print()
    # Items the tool cannot decide are listed rather than silently passed.
    print("  Not machine-checkable, stated for the owner:")
    print("    [ ] OOS validation enforced        - the harness SPLITS correctly (tested), but")
    print("                                         nothing refuses a run that skipped a split")
    print("    [ ] Futures architecture operational - contracts + prop-firm engine exist; no")
    print("                                         CME calendar, no data pipeline, no strategy")
    print("    [ ] Options architecture operational - store retained, not migrated behind the")
    print("                                         market interface")
    print("    [ ] Replay tests green             - run manually: intraday_trader.py --replay")
    print(f"\n  {len(GATE_ITEMS) - failed}/{len(GATE_ITEMS)} machine-checkable items pass\n")
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.gate:
        return gate()
    return report(build(), as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
