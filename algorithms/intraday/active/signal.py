"""Active sleeve: the deployed combination of the intraday strategies.

Each sub-strategy gets its own state and an equity allocation; their target weights are
summed per symbol, then capped per symbol and in gross. This module is what
scripts/intraday_trader.py runs live and what scripts/intraday_backtest.py judges.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from base import clamp_targets  # noqa: E402

NAME = "active"
PARAMS = {
    "alloc": {"orb": 1.0, "vwap_trend": 1.0, "late_momo": 1.0},   # multipliers on each strategy's own weights
    "per_symbol": 0.15,      # max |weight| per symbol
    "gross": 1.0,            # max sum of |weights|
    "sub_params": {},        # {"orb": {...}, ...} overrides
}


def _load(name):
    path = HERE / name / "signal.py"
    spec = importlib.util.spec_from_file_location(f"intraday_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_SUBS = {}


def subs(names):
    for n in names:
        if n not in _SUBS:
            _SUBS[n] = _load(n)
    return {n: _SUBS[n] for n in names}


def decide(now, feats, book, equity, state, params):
    p = {**PARAMS, **(params or {})}
    alloc = {k: float(v) for k, v in p["alloc"].items() if float(v) > 0}
    total = {}
    for name, mod in subs(list(alloc)).items():
        sub_state = state.setdefault(name, {})
        sub_params = {**mod.PARAMS, **p.get("sub_params", {}).get(name, {})}
        t = mod.decide(now, feats, book, equity, sub_state, sub_params) or {}
        for s, w in t.items():
            total[s] = total.get(s, 0.0) + alloc[name] * float(w)
    return clamp_targets(total, p["per_symbol"], p["gross"])
