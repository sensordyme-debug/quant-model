"""Which safety-critical modules does production actually load, and which are decorative?

An audit measured that of 53 `quant_brain` modules only 15 are imported by any of the six
production entry points, that 17 modules totalling 8,023 lines (44.3%) are unreachable from
any non-test importer, and that every validation and execution-safety API — the promotion
gate, the write-once holdout, purged walk-forward, the deflated Sharpe ratio, PBO, White's
Reality Check, Hansen's SPA, the reconciler, the order state machine and the bracket
verifier — has **no production caller at all**.

That is not a style complaint. `docs/IMPLEMENTATION_REPORT.md` and `ARCHITECTURE.md` describe
those components as though they run. A reader, or an agent, planning against those documents
plans against a machine that does not exist.

This module is the guard that keeps the claim and the code honest. It does not assert that
the architecture is good; it asserts that **the documented safety surface is the executed
one**, and it fails loudly the day a component silently loses its last caller.

The `xfail(strict=True)` markers below are deliberate and load-bearing. Each one is pinned to
a component that SHOULD be on the production path and currently is not. When one is finally
wired up, its test starts passing, `strict=True` turns that into a failure, and whoever did
the wiring is forced to delete the marker — which is the only way a to-do list like this ever
gets shorter. Do not "fix" a failure here by weakening the assertion.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

#: The scripts that actually run: the two scheduled runners, the launcher that gates them,
#: the state reconciler, and the two research launchers that write the ledgers.
PRODUCTION_ENTRY_POINTS = (
    "scripts/intraday_trader.py",
    "scripts/paper_trade.py",
    "scripts/intraday_launch.py",
    "scripts/reconcile_state.py",
    "scripts/backtest.py",
    "scripts/evaluate.py",
)

#: Everything that imports `quant_brain` and is not a test: the entry points above plus the
#: research funnel and the sweeps. "Research-reachable" is a weaker claim than "production-
#: reachable" and both are worth distinguishing.
def _research_entry_points() -> list[pathlib.Path]:
    out = []
    for sub in ("scripts", "algorithms"):
        for p in (REPO / sub).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            try:
                src = p.read_text(encoding="utf-8", errors="replace")
            except OSError:                                      # pragma: no cover
                continue
            if "quant_brain" in src:
                out.append(p)
    return out


def _module_name(p: pathlib.Path) -> str:
    parts = list(p.relative_to(REPO).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_modules(p: pathlib.Path) -> set[str]:
    """Every `quant_brain.*` module this file imports, resolved to real modules.

    `from quant_brain.markets.futures_cme import features` imports a MODULE, not a name, so
    the alias has to be appended to the base before resolution or the edge is missed. Getting
    this wrong is what made an earlier reachability estimate name the wrong module set.
    """
    try:
        tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"), str(p))
    except SyntaxError:                                          # pragma: no cover
        return set()
    raw: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            raw.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            raw.add(node.module)
            raw.update(f"{node.module}.{a.name}" for a in node.names)
    return {n for n in raw if n.startswith("quant_brain")}


def _all_quant_brain_modules() -> set[str]:
    return {
        _module_name(p)
        for p in (REPO / "quant_brain").rglob("*.py")
        if "__pycache__" not in p.parts
    }


def _resolve(target: str, known: set[str]) -> str | None:
    while target and target not in known:
        target = target.rsplit(".", 1)[0] if "." in target else ""
    return target or None


def _reachable_from(entry_files) -> set[str]:
    known = _all_quant_brain_modules()
    edges: dict[str, set[str]] = {}
    for p in (REPO / "quant_brain").rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        me = _module_name(p)
        edges[me] = {
            r for t in _imported_modules(p)
            if (r := _resolve(t, known)) and r != me
        }
    seeds: set[str] = set()
    for f in entry_files:
        path = f if isinstance(f, pathlib.Path) else REPO / f
        if path.exists():
            seeds |= {r for t in _imported_modules(path) if (r := _resolve(t, known))}
    seen, stack = set(), list(seeds)
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(edges.get(n, ()))
    return seen


@pytest.fixture(scope="module")
def production_reachable() -> set[str]:
    return _reachable_from(PRODUCTION_ENTRY_POINTS)


@pytest.fixture(scope="module")
def research_reachable() -> set[str]:
    return _reachable_from(_research_entry_points())


# ---------------------------------------------------------------------------------------
# Invariants that hold today. If one of these breaks, something load-bearing was unplugged.
# ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("module", [
    "quant_brain.core.risk",         # the chain every order passes
    "quant_brain.core.execution",    # RoutedExecutor: the one path to a venue
    "quant_brain.core.governor",     # the limits actually armed by the intraday runner
    "quant_brain.core.mode",         # the authority ladder checked at construction
    "quant_brain.core.state",        # StateScope containment
    "quant_brain.brokers.ibkr",      # the only adapter that can reach a venue
])
def test_the_order_path_is_loaded_by_production(module, production_reachable):
    """These are the modules an order actually travels through. They must stay reachable."""
    assert module in production_reachable, (
        f"{module} is no longer imported by any of {PRODUCTION_ENTRY_POINTS}. "
        f"Either a runner stopped using it or the order path moved."
    )


def test_no_broker_sdk_is_importable_above_the_broker_package():
    """`ib_async` may appear only under quant_brain/brokers/. Cheap, and it has caught a real
    regression before; the AST test in test_qb_adapter.py owns the detailed version."""
    offenders = []
    for p in (REPO / "quant_brain").rglob("*.py"):
        if "__pycache__" in p.parts or "brokers" in p.parts:
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        if "import ib_async" in src or "from ib_async" in src:
            offenders.append(str(p.relative_to(REPO)))
    assert not offenders, f"broker SDK imported outside quant_brain/brokers/: {offenders}"


def test_the_leakage_guard_module_is_wired_to_the_research_path(research_reachable):
    """RATCHET CLEARED 2026-09-13. `quant_brain.core.validation` had no caller of any kind.

    `scripts/futures_discover.py::build_features` now raises `validation.LeakageError` when
    the feature library fails its own causality audit, which is the module's first real use.
    That is a narrow foothold and it is worth being honest about what it does NOT mean:
    `purged_walk_forward` and the write-once `Holdout` are still uncalled, no holdout has
    ever been carved, and `Holdout.spend()` has never run. Reachability is not use.
    """
    assert "quant_brain.core.validation" in research_reachable


# ---------------------------------------------------------------------------------------
# The gap. Each of these SHOULD be on the production or research path and is not.
# ---------------------------------------------------------------------------------------

_UNWIRED = [
    ("quant_brain.core.multipletest",
     "Holm/BH/BY/Reality Check/SPA/DSR/PBO; the funnel uses only stats.bonferroni_threshold "
     "and the equity ledger applies no correction at all"),
    ("quant_brain.research.promotion",
     "PromotionGate; the real promotion path is scripts/evaluate.py, whose criteria are CAR-"
     "first with no significance test, no multiplicity and no OOS requirement"),
    ("quant_brain.core.protection",
     "bracket verification; neither runner places a protective order, so by this module's own "
     "definition every open position is UNPROTECTED for the whole session"),
    ("quant_brain.core.reconcile",
     "compare-and-halt reconciliation; intraday_trader.py carries its own reconcile_book and "
     "paper_trade.py reconciles nothing"),
    ("quant_brain.core.portfolio",
     "portfolio exposure and correlated risk; no caller"),
    ("quant_brain.research.analytics",
     "trade analytics with UNAVAILABLE semantics; no caller"),
    ("quant_brain.research.robustness",
     "regime labelling and concentration/ordering nulls; no caller"),
]


@pytest.mark.parametrize("module,why", _UNWIRED, ids=[m.split(".")[-1] for m, _ in _UNWIRED])
@pytest.mark.xfail(strict=True, reason="documented-but-unwired safety component; see docstring")
def test_documented_safety_components_are_reachable(module, why, research_reachable):
    """Pinned gap: the architecture documents describe this component as part of the system.

    When it is genuinely wired to a research or production caller this test will pass, the
    strict xfail will then fail the suite, and the marker must be deleted. That is the intent.
    """
    assert module in research_reachable, f"{module} has no non-test caller — {why}"


@pytest.mark.xfail(strict=True, reason="the equity ledger and the Ledger class have disjoint "
                                       "schemas, so multiplicity cannot be applied to it")
def test_the_multiplicity_ledger_can_read_the_main_experiment_log():
    """`Ledger.all()` parses 0 of the 1,653 rows in research/experiments.jsonl.

    The two ledgers share no keys: the equity log is {algorithm, class, commit, run_dir,
    stats, tag, ts} and the Ledger's own rows are {created, experiment_id, family, hypothesis,
    metrics, notes, params, provenance, stage, verdict}. This matters more than "unused": if
    the Bonferroni denominator were wired to the equity track tomorrow it would silently
    return 0 trials and apply the n=1 bar of 1.96 to a search of several thousand cells.
    """
    import shutil
    import tempfile

    from quant_brain.research.registry import Ledger

    src = REPO / "research" / "experiments.jsonl"
    if not src.exists():                                          # pragma: no cover
        pytest.skip("equity ledger absent")
    raw = sum(1 for line in src.open(encoding="utf-8") if line.strip())
    tmp = pathlib.Path(tempfile.mkdtemp()) / "eq.jsonl"
    shutil.copy(src, tmp)
    parsed = len(Ledger(tmp).all())
    assert parsed == raw, f"Ledger parsed {parsed} of {raw} rows in the equity experiment log"
