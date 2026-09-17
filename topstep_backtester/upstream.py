"""The single seam between this package and the upstream ``topstep-backtest`` engine.

WHY A SEAM AT ALL
-----------------
The upstream package is authoritative and immutable. We do not patch it, subclass around
its calculations, or keep a copy of its source. Concentrating every reference to it in one
module makes that discipline *testable*: ``validation.layering`` reads the source of every
other module in this package and fails if any of them names ``topstep_backtest``. A rule
that can be checked survives; a rule in a README does not.

The seam re-exports names. It does not wrap them. There is no function here that takes an
upstream result and "corrects" it, and there must never be one. If an upstream number looks
wrong, the answer is to reproduce it, document it and report it upward (see
``docs/UPSTREAM_FINDINGS.md``), not to quietly substitute our own.

WHY THE FINGERPRINT
-------------------
An engine upgrade that renames a field or changes a default would otherwise change every
number this pipeline reports, silently, with no diff in our tree to explain it.
``api_fingerprint()`` captures the shape of everything we consume and hashes it; a
validation test pins that hash. When upstream moves, the test fails and says so, and a
human decides whether to re-certify. That converts an invisible risk into a loud one.

PYTHON VERSION
--------------
Upstream requires >= 3.12, and this repository also runs a 3.11 interpreter for the LEAN
side. Importing this package from 3.11 therefore fails, and it should. The guard below
explains the failure instead of surfacing it as a confusing ImportError from a submodule.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import sys
from importlib import metadata
from typing import Any

if sys.version_info < (3, 12):  # pragma: no cover - environment guard
    raise ImportError(
        "topstep_backtester requires Python >= 3.12 because the upstream topstep-backtest "
        f"engine does; this interpreter is {sys.version_info.major}.{sys.version_info.minor}. "
        "The 3.11 interpreter in this repository exists for LEAN/pythonnet and must not "
        "import this package."
    )

import topstep_backtest as _upstream
from topstep_backtest import AccountSize, Backtest, SymbolStrategy
from topstep_backtest.core.instruments import (
    SPECS,
    InstrumentSpec,
    spec_for_symbol,
    symbol_of_contract_id,
)
from topstep_backtest.data.feed import Bar
from topstep_backtest.data.validator import validate_bars
from topstep_backtest.engine.backtest import BacktestResult
from topstep_backtest.execution.sim_broker import SimBrokerConfig
from topstep_backtest.fills.bar_fill import BarFillConfig
from topstep_backtest.fills.fees import FeeSchedule, TopstepFees
from topstep_backtest.metrics.economics import EvalEconomics, evaluate_ev
from topstep_backtest.metrics.montecarlo import MonteCarloResult, monte_carlo
from topstep_backtest.metrics.stats import SummaryStats
from topstep_backtest.protocols import AggregateBarUnit, BarType
from topstep_backtest.rules.params import CombineParams, combine_params

#: The engine version this pipeline was certified against. Not a floor and not a ceiling -
#: an exact reading. Any other version is uncertified until someone re-runs the audit.
CERTIFIED_VERSION = "0.4.0"

#: What is actually installed right now.
INSTALLED_VERSION = metadata.version("topstep-backtest")

#: Everything Layer B is allowed to consume. The fingerprint covers exactly this set, so a
#: name added here without re-certifying changes the hash and trips the pinning test.
CONSUMED_API: tuple[str, ...] = (
    "AccountSize",
    "AggregateBarUnit",
    "Backtest",
    "BacktestResult",
    "Bar",
    "BarFillConfig",
    "BarType",
    "CombineParams",
    "EvalEconomics",
    "FeeSchedule",
    "InstrumentSpec",
    "MonteCarloResult",
    "SPECS",
    "SimBrokerConfig",
    "SummaryStats",
    "SymbolStrategy",
    "TopstepFees",
    "combine_params",
    "evaluate_ev",
    "monte_carlo",
    "spec_for_symbol",
    "symbol_of_contract_id",
    "validate_bars",
)


class UpstreamVersionError(RuntimeError):
    """The installed engine is not the certified one."""


def assert_certified_version() -> None:
    """Refuse to produce quotable numbers on an uncertified engine build."""
    if INSTALLED_VERSION != CERTIFIED_VERSION:
        raise UpstreamVersionError(
            f"topstep-backtest {INSTALLED_VERSION} is installed but this pipeline was "
            f"certified against {CERTIFIED_VERSION}. Results from an uncertified engine are "
            f"not comparable with anything already reported. Re-run the integration audit "
            f"(topstep_backtester/docs/PIPELINE_CERTIFICATION.md) and update "
            f"CERTIFIED_VERSION deliberately."
        )


def _shape_of(obj: Any) -> Any:
    """A structural description stable enough to diff across releases.

    Signatures for callables, field lists for msgspec structs and namedtuples, member names
    for enums, sorted keys for mappings. Deliberately NOT the repr of default values, which
    can carry addresses or environment state and would make the hash unstable for reasons
    that have nothing to do with the API.
    """
    if isinstance(obj, dict):
        return {"kind": "mapping", "keys": sorted(map(str, obj))}
    fields = getattr(obj, "__struct_fields__", None)
    if fields is not None:
        return {"kind": "struct", "fields": list(fields)}
    named_fields = getattr(obj, "_fields", None)
    if isinstance(obj, type) and issubclass(obj, tuple) and named_fields is not None:
        return {"kind": "namedtuple", "fields": list(named_fields)}
    members = getattr(obj, "__members__", None)
    if members is not None:
        return {"kind": "enum", "members": sorted(members)}
    if isinstance(obj, type):
        try:
            return {"kind": "class", "init": str(inspect.signature(obj.__init__))}
        except (TypeError, ValueError):  # pragma: no cover - builtins without signatures
            return {"kind": "class", "init": "<unavailable>"}
    if callable(obj):
        try:
            return {"kind": "callable", "signature": str(inspect.signature(obj))}
        except (TypeError, ValueError):  # pragma: no cover
            return {"kind": "callable", "signature": "<unavailable>"}
    return {"kind": "value", "type": type(obj).__name__}


def api_fingerprint() -> dict[str, Any]:
    """The shape of every upstream name this pipeline consumes."""
    here = globals()
    return {name: _shape_of(here[name]) for name in CONSUMED_API}


def api_fingerprint_hash() -> str:
    """A short stable digest of :func:`api_fingerprint`."""
    blob = json.dumps(api_fingerprint(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def upstream_provenance() -> dict[str, str]:
    """Where the engine came from, for the run manifest."""
    return {
        "package": "topstep-backtest",
        "installed_version": INSTALLED_VERSION,
        "certified_version": CERTIFIED_VERSION,
        "api_fingerprint": api_fingerprint_hash(),
        "location": str(getattr(_upstream, "__file__", "<unknown>")),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }


__all__ = [
    "CERTIFIED_VERSION",
    "CONSUMED_API",
    "INSTALLED_VERSION",
    "SPECS",
    "AccountSize",
    "AggregateBarUnit",
    "Backtest",
    "BacktestResult",
    "Bar",
    "BarFillConfig",
    "BarType",
    "CombineParams",
    "EvalEconomics",
    "FeeSchedule",
    "InstrumentSpec",
    "MonteCarloResult",
    "SimBrokerConfig",
    "SummaryStats",
    "SymbolStrategy",
    "TopstepFees",
    "UpstreamVersionError",
    "api_fingerprint",
    "api_fingerprint_hash",
    "assert_certified_version",
    "combine_params",
    "evaluate_ev",
    "monte_carlo",
    "spec_for_symbol",
    "symbol_of_contract_id",
    "upstream_provenance",
    "validate_bars",
]
