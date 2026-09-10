"""X-1: cross-sectional intraday momentum across the 50 US megacaps.

Hypothesis (backlog X-1). A 16-name book has no breadth: A-10 measured its edge at -$697/day on
2,686 sessions, and every lever since has been a way of re-cutting the same few names. With fifty
liquid names the same idea can be run as a *ranking* instead of a timing call - every `rebalance`
minutes, score each name by its intraday return relative to the equal-weight basket, hold the top
`k` long and the bottom `k` short, and let the framework flatten at 15:38. The book is
dollar-neutral by construction, so the market factor is differenced out and what is left is the
cross-sectional spread.

Mechanics, all causal (`base.features` uses bars <= t only):

    signal = c / c[-lookback] - 1        (lookback = 0 -> return since the session open)
    rank the cross-section on signal minus its cross-sectional mean
    long the top k, short the bottom k, one flat `weight` per leg
    re-rank every `rebalance` minutes between start_minute and stop_minute; hold in between

`direction = -1` inverts the ranking into the intraday reversal control, which is the sign check
that separates "winners keep winning" from "this window happened to trend".

The positions are decided only on rebalance bars; on every other bar `decide` returns the standing
book unchanged, so the framework's no-trade band sees no drift and the turnover is exactly the
re-ranking. `scripts/sweep_x1.py` measures the mechanism first as a cost-free event study and only
then runs this module through the harness.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from base import clamp_targets, is_new_session  # noqa: E402

NAME = "xsect"
PARAMS = {
    "lookback": 30,          # minutes of intraday return used to rank; 0 = since the session open
    "rebalance": 30,         # bars between re-rankings
    "k": 5,                  # names per side (top k long, bottom k short)
    "weight": 0.06,          # |weight| per leg, fraction of sleeve equity (2k legs -> 0.6 gross)
    "min_names": 20,         # refuse to rank a cross-section thinner than this
    "start_minute": 30,      # first ranking at 10:00; the open is too noisy to rank on
    "stop_minute": 330,      # last ranking at 15:00; the framework flattens at 15:38
    "direction": 1,          # +1 momentum (the hypothesis), -1 reversal (the control)
    "per_symbol": 0.10,      # strategy-level caps, applied before the framework's
    "gross": 1.20,
}


def decide(now, feats, book, equity, state, params):
    p = {**PARAMS, **(params or {})}
    is_new_session(state, now)
    held = state.setdefault("targets", {})
    lb, k = int(p["lookback"]), int(p["k"])
    row0 = next(iter(feats.values()), None)
    if row0 is None or len(row0) == 0:
        return {}
    m = int(row0["minute"].iloc[-1])
    due = (p["start_minute"] <= m <= p["stop_minute"]
           and (m - int(p["start_minute"])) % int(p["rebalance"]) == 0)
    if not due:
        return clamp_targets(dict(held), p["per_symbol"], p["gross"])

    scores = {}
    for sym, f in feats.items():
        if len(f) < lb + 2:
            continue
        c = float(f["c"].iloc[-1])
        base = float(f["sess_open"].iloc[-1]) if lb == 0 else float(f["c"].iloc[-1 - lb])
        if not (c > 0 and base > 0):
            continue
        scores[sym] = c / base - 1.0
    if len(scores) < max(int(p["min_names"]), 2 * k):
        state["targets"] = {}
        return {}
    mean = sum(scores.values()) / len(scores)
    ranked = sorted(scores, key=lambda s: scores[s] - mean)
    side = 1.0 if p["direction"] > 0 else -1.0
    targets = {}
    for sym in ranked[-k:]:                       # strongest relative to the basket
        targets[sym] = side * p["weight"]
    for sym in ranked[:k]:                        # weakest
        targets[sym] = -side * p["weight"]
    state["targets"] = targets
    return clamp_targets(dict(targets), p["per_symbol"], p["gross"])
