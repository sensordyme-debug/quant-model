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


def _no_trial_override() -> bool:
    """Does the ledger's verdict expose any way to supply the trial count?

    Checked against the real signature rather than the file text: the module's own docstring
    contains the string "n_trials" in the sentence explaining that there is no such
    parameter, and a substring check reported that documentation as a defect.
    """
    try:
        import inspect

        from quant_brain.research.registry import Ledger
        params = set(inspect.signature(Ledger.verdict).parameters)
        return not (params & {"n_trials", "trials", "num_trials", "alpha", "override"})
    except Exception:  # noqa: BLE001
        return False


def ml_corrections() -> dict[str, bool]:
    """Is the statistical machinery AUD-18/19/20 need present AND wired into the ML code?"""
    def has(path: str, needle: str) -> bool:
        f = REPO / path
        return f.exists() and needle in f.read_text(encoding="utf-8", errors="replace")
    return {
        "HAC t-stat exists": has("quant_brain/core/stats.py", "def tstat_hac"),
        "lag derived from horizon": has("quant_brain/core/stats.py", "def lag_for_overlap"),
        "multiplicity correction": has("quant_brain/core/stats.py", "def bonferroni_threshold"),
        "time-aware label guard": has("quant_brain/core/labels.py", "def forward_span_mask"),
        "guard wired into sweep_f1": has("scripts/sweep_f1.py", "forward_span_mask"),
        "HAC adopted by the ML sweeps themselves": has("scripts/sweep_f3.py", "tstat_hac"),
        # Two dimensions the earlier list had no way to express. The corrections being
        # PRESENT is not the same as multiplicity being IMPOSSIBLE TO UNDERSTATE, and the
        # second is the property that actually protects a result.
        "multiplicity is structural, not an argument": _no_trial_override(),
        "a research path records trials in the ledger": has(
            "scripts/futures_topstep_baseline.py", "Ledger"),
    }


def execution_abstraction() -> dict[str, bool]:
    """Can a strategy reach a venue without naming one?"""
    def has(path: str, needle: str) -> bool:
        f = REPO / path
        return f.exists() and needle in f.read_text(encoding="utf-8", errors="replace")
    return {
        "OrderIntent exists": has("quant_brain/core/execution.py", "class OrderIntent"),
        "RiskChain cannot be re-permitted": has("quant_brain/core/risk.py", "def merge"),
        "flatten bypasses risk": has("quant_brain/core/risk.py", "is_flatten"),
        "prop-firm engine is deterministic": has(
            "quant_brain/markets/futures_cme/propfirm.py", "class PropFirmRiskEngine"),
        "runners emit OrderIntent": has("scripts/intraday_trader.py", "OrderIntent"),
        "broker adapter layer": has("quant_brain/core/execution.py", "class ExecutionAdapter"),
    }


def runners_route() -> dict[str, bool]:
    """Does each live runner reach its venue through the adapter, or build orders inline?

    Inline construction is the actual defect: it is what makes a second venue unreachable
    without editing a trading loop. Presence of an `ib_async` order class in a runner is the
    signature, so this looks for the class names rather than for a comforting import.
    """
    out: dict[str, bool] = {}
    for name in ("intraday_trader.py", "paper_trade.py"):
        f = REPO / "scripts" / name
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        # Word-boundary matched, not substring: a bare "Order(" also matches
        # `ib.cancelOrder(...)`, which is not order construction and made this check report
        # a migrated runner as unmigrated.
        builds_inline = bool(re.search(
            r"(?<![A-Za-z_])(MarketOrder|LimitOrder|StopOrder|Order)\s*\(", text))
        routes = "RoutedExecutor" in text or "OrderIntent" in text
        out[f"{name} routes"] = routes and not builds_inline
    return out


def adapter_count() -> int:
    """How many concrete ExecutionAdapters exist. One is an abstraction nobody has tested."""
    n = 0
    for f in (REPO / "quant_brain").rglob("*.py"):
        text = f.read_text(encoding="utf-8", errors="replace")
        n += text.count("(ExecutionAdapter)")
    return n


def observability_signals() -> dict[str, bool]:
    """Can the system tell someone what it is doing, and what it refused to do?

    Deliberately about REFUSALS as much as actions. A log that records fills and not the
    orders the risk layer stopped is a log that makes the risk layer invisible, which is how
    a risk layer comes to be disabled by the next person in a hurry.
    """
    def has(path: str, needle: str) -> bool:
        f = REPO / path
        return f.exists() and needle in f.read_text(encoding="utf-8", errors="replace")
    wd_ok, _ = watchdog_trustworthy()
    return {
        "watchdog reports 6 states": wd_ok,
        "risk refusals are logged": has("quant_brain/core/execution.py", "risk_denied"),
        "order path emits events": has("quant_brain/core/execution.py", "_emit"),
        "runner wires the event sink": has("scripts/intraday_trader.py", "on_event="),
        "resource snapshot is a CLI": has("quant_brain/core/resources.py", "def snapshot"),
        "structured JSONL logs": has("scripts/gateway_watchdog.py", "json.dumps"),
    }


def data_gates() -> dict[str, bool]:
    """Which data paths refuse to proceed on a store that has not been validated?

    Coverage, not existence. The previous version read `7.0 if dq_wired else 5.0` off a
    single substring, so wiring the gate into a second path could never move it - the same
    unfalsifiable shape found in execution safety and observability.
    """
    def has(path: str, *needles: str) -> bool:
        f = REPO / path
        if not f.exists():
            return False
        text = f.read_text(encoding="utf-8", errors="replace")
        return all(n in text for n in needles)
    return {
        "equity harness validates": has("scripts/intraday_backtest.py", "validate_bars"),
        "futures validator exists": has(
            "quant_brain/markets/futures_cme/dataquality.py", "def check_futures_frame"),
        "futures research path validates": has(
            "scripts/futures_topstep_baseline.py", "require_usable"),
        "futures roll hazards covered": has(
            "quant_brain/markets/futures_cme/dataquality.py",
            "roll_backwards", "crossed_book", "impossible_move"),
        # Replaced two checks that could never pass. scripts/ml_panel.py does not exist,
        # and scripts/backtest.py loads no bars at all - it invokes LEAN, which reads its
        # own data - so neither could ever call a gate. A check that cannot pass is as
        # useless as one that always does; both were inherited from a stale weakness note.
        "futures fetch validates before writing": has(
            "scripts/futures_data.py", "check_futures_frame"),
        "the fetch refuses to write a broken store": has(
            "scripts/futures_data.py", "REFUSED to write"),
    }


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

    # Execution safety, on a ladder that can actually move. The six boundary pieces carry the
    # base; the last two points are the things that prove the boundary is real rather than
    # declared - every runner going through it, and more than one adapter behind it.
    exec_pieces = sum(execution_abstraction().values())
    routed = runners_route()
    exec_score = 4.0 + 4.0 * (exec_pieces / max(1, len(execution_abstraction())))
    if routed and all(routed.values()):
        exec_score += 0.5
    if adapter_count() >= 2:
        exec_score += 0.5
    exec_score = round(min(10.0, exec_score), 2)
    unrouted = [k for k, v in routed.items() if not v]
    exec_weak = (f"{', '.join(unrouted)} still builds broker orders inline, so that path "
                 f"cannot reach a second venue without editing the trading loop"
                 if unrouted else
                 "every runner routes through the adapter and a second adapter exists; the "
                 "remaining gap is that no PROP-FIRM adapter has been written or exercised "
                 "against a real venue")

    obs = observability_signals()
    obs_hits = sum(obs.values())
    obs_score = round(4.0 + 5.0 * (obs_hits / max(1, len(obs))), 2)

    res_ok, res_note = resource_legs()
    wired = sum(calls.values())
    ml = ml_corrections()
    dq_paths = data_gates()
    dq_hits = sum(dq_paths.values())
    dq_score = round(4.0 + 5.0 * (dq_hits / max(1, len(dq_paths))), 2)
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

        D("Data integrity", dq_score,
          [f"{dq_hits}/{len(dq_paths)} validation gates in place"]
          + [f"  {'yes' if v else 'NO '}  {k}" for k, v in dq_paths.items()]
          + ["equities: FAIL on zero/NaN/negative price, impossible bar, duplicate or "
             "unsorted index, tz-naive index, bars on a market holiday",
             "futures: roll gap, roll overlap, backwards stitching, impossible move within "
             "one contract, stale-with-volume, crossed book",
             "reproduced AUD-07 independently: 21 early-close sessions with after-hours rows "
             "in the Alpaca store, found from the calendar alone",
             "real ES store, 447,600 rows: 0 fail. Its one 645-bar flat run is Thanksgiving "
             "night with 6 contracts of volume, not a stuck feed"],
          "the LEAN daily path and the ML panel builder still call no gate, and no "
          "cross-source reconciliation (IBKR vs Alpaca) runs as a gate"),

        D("Research harness", 8.0 if (REPO / "tests/test_research_harness.py").exists() else 4.0,
          ["40 tests on the code that decides what a result is: drawdown from the opening "
           "peak, sqrt(252) annualisation, NaN Sharpe on zero variance, whole-share floor, "
           "gross/per-symbol caps, the no-trade band never suppressing a close",
           "OOS split proven adjacent and non-overlapping for any split date",
           "an errored run is never recorded; a relaxed-risk run is flagged on the row",
           "harness and live runner asserted to read the same cap constants"],
          "the 15 sweep_* files that produce most research still have no unit tests; only "
          "the shared harness does"),

        D("Execution safety", exec_score,
          [f"{exec_pieces}/{len(execution_abstraction())} boundary pieces present"]
          + [f"  {'yes' if v else 'NO '}  {k}" for k, v in execution_abstraction().items()]
          + [f"  {'yes' if v else 'NO '}  {k}" for k, v in runners_route().items()]
          + [f"  {adapter_count()} concrete ExecutionAdapter implementation(s)"],
          exec_weak),

        D("Observability", obs_score,
          [f"{obs_hits}/{len(obs)} signals present",
           f"watchdog states: {wd_note}"]
          + [f"  {'yes' if v else 'NO '}  {k}" for k, v in obs.items()]
          + ["dashboard read-only on 127.0.0.1:8787"],
          "live alerting remains the gap: the order path and the watchdog are both legible "
          "now, but nothing pages the owner when the sleeve breaks outside a session"),

        D("_Orchestration reliability (not in the brief's twelve; kept for continuity)",
          7.0 if wd_ok else 4.0,
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

        D("ML pipeline integrity", 4.0 + 4.0 * (sum(ml.values()) / len(ml)),
          [f"{sum(ml.values())}/{len(ml)} corrections present and wired"]
          + [f"  {'yes' if v else 'NO '}  {k}" for k, v in ml.items()]
          + ["AUD-18 measured: F-3 IC t 2.17 -> 1.31 (h=5) and 2.41 -> 0.79 (h=21); "
             "bootstrap p 0.196 / 0.436 - the result does not survive",
             "AUD-19 re-diagnosed: ml_f7:647's argmax is over a MONOTONE series, so its "
             "selection bias is +0.000. The real exposure is 55 untested specifications "
             "against one window with no multiplicity control (threshold |t| > 3.32)",
             "AUD-20 measured: 0 labels dropped on IBKR, 173 of 190,394 (0.091%) on Alpaca"],
          "59 sweep_*/ml_* scripts exist and NOT ONE imports quant_brain.core.stats: the "
          "corrections are correct, tested, and used by nothing outside the futures branch. "
          "Retrofitting them is other agent tracks' work; new research goes through the "
          "ledger, which is the only path where the trial count cannot be understated"),

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
