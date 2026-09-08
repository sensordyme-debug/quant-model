"""S-3 signal: cross-sectional short-term reversal, dollar neutral.

Plain pandas, no LEAN imports, same contract as `algorithms/s1_momo/signals.py`
(`algorithms/SIGNAL_CONTRACT.md`), so `main.py` and the I-1 paper runner execute
identical decision code.

Hypothesis
----------
Over 1-5 sessions, liquid single names over-react: the biggest recent losers out-perform
the biggest recent winners. Buying the losers and shorting the winners in equal dollars
is a *market-neutral* return stream, which is the property that matters here - S-8
measured that the ETF-9 momentum sleeve cannot be pushed past ~20% realized vol without
breaching the 35% drawdown limit, so more portfolio volatility has to come from adding
uncorrelated sleeves (backlog S-5), not from more leverage on the one sleeve that exists.
The number this experiment has to produce is therefore *correlation with the champion*
first and Sharpe second.

Contract
--------
    weights, diag = target_weights(prices, equity_curve, params, state, volumes=...)

Weights are fractions of equity, **signed**: negative is short. `sum(|w|)` is gross.

Shared code, not copied code
----------------------------
The drawdown overlay, the annualized-vol helper and the Reg-T margin table are imported
from the S-1 module rather than re-implemented. The overlay in particular encodes two
bugs that took a rewrite each to find (a flat book cannot print a new equity high, so
"stay flat until a new high" is an absorbing state; and a cooldown without resetting the
high-water mark re-arms the breaker on release) - a second copy is a second chance to
reintroduce them. It is loaded by path under a distinct module name because this file is
*also* called `signals`, so a plain `import signals` from the sibling directory would
return this module back.

Known biases, stated once
-------------------------
* The candidate pool is `MEGACAP_SLEEVE`, the megacaps **as of 2026**. D-3's point-in-time
  selection fixes the timing half (membership is re-decided each rebalance from trailing
  dollar volume) but measured that the pool itself carries ~90% of the bias. Reversal is
  the strategy that bias flatters *most*: buying the biggest loser is only profitable if
  the loser comes back, and every name on disk did come back far enough to still be a
  megacap in 2026. Every megacap-pool run here is tagged `not promotable`.
* Short borrow is not modelled - neither by LEAN nor here. On megacaps that is roughly
  0.25-0.5%/yr on the short notional, so subtract about that much from any CAR below.
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

_S1_DIR = Path(__file__).resolve().parent.parent / "s1_momo"
if str(_S1_DIR) not in sys.path:
    sys.path.append(str(_S1_DIR))          # so the S-1 module finds its own `universe`

import universe as uni                     # noqa: E402  (D-3, shared)


def _load_s1():
    """Import `s1_momo/signals.py` under an alias so it cannot shadow this module."""
    if "s1_signals" in sys.modules:
        return sys.modules["s1_signals"]
    spec = importlib.util.spec_from_file_location("s1_signals", _S1_DIR / "signals.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["s1_signals"] = module
    spec.loader.exec_module(module)
    return module


s1 = _load_s1()

TRADING_DAYS = s1.TRADING_DAYS
BASE_MARGIN_REQ = s1.BASE_MARGIN_REQ
MARGIN_REQ = s1.MARGIN_REQ

#: Candidate pools. "megacap" is the 50 names D-1 downloaded (selection-biased, see the
#: module docstring); "etf" is the nine unlevered ETFs, which have no equivalent bias
#: because all nine traded throughout the sample - a small pool, but an honest one.
POOLS = {
    "megacap": tuple(s1.MEGACAP_SLEEVE),
    "etf": tuple(s1.RANK_UNIVERSE),
    "wide": tuple(s1.MEGACAP_SLEEVE) + tuple(s1.RANK_UNIVERSE),
}

#: SPY is subscribed in every configuration: it is the benchmark and the bar whose arrival
#: drives the rebalance, not a tradable name for this strategy.
TRIGGER_TICKER = "SPY"


def traded_universe(params: "Params | None" = None) -> list[str]:
    """Every ticker that must be subscribed for a given pool."""
    pool = POOLS[(params or DEFAULTS).pool]
    return sorted(set(pool) | {TRIGGER_TICKER})


@dataclass(frozen=True)
class Params:
    pool: str = "megacap"            # key into POOLS
    universe_size: int = 30          # point-in-time liquid names; 0 = use the pool whole
    dv_window: int = uni.DV_WINDOW
    min_history: int = uni.MIN_HISTORY
    #: Horizon and breadth. The backlog specified 1-3 sessions and a narrow basket; the
    #: shipped values are lookback 5 / n_side 10 because that is the best of the 30 cells
    #: in `sweep_s3.py --mode grid --cost 0`, i.e. the configuration chosen *with hindsight
    #: and no trading costs* - deliberately, so the rejection below is of the hypothesis at
    #: its strongest rather than of an unlucky parameter choice.
    lookback: int = 5                # reversal horizon, sessions
    #: Divide the trailing return by the name's own trailing vol before ranking. Without
    #: it the loser basket is simply the highest-vol names in the pool every day, so the
    #: strategy is a short-vol bet wearing a reversal costume; with it the ranking asks
    #: "unusually far down *for this name*". The hypothesis wanted the second; the grid
    #: prefers the first at every breadth, which is itself part of the finding.
    vol_adjust: bool = False
    vol_window: int = 20             # trailing window for that per-name vol
    n_side: int = 10                 # names long and names short
    #: +1 buys the losers (reversal, the S-3 hypothesis); -1 buys the winners (short-term
    #: continuation). A diagnostic, not a second strategy: the grid comes out negative in
    #: 24 of 30 cells, so the interesting question is whether the *inverse* is a real edge
    #: or whether both directions are inside the noise. Flipping the sign after reading the
    #: result is data snooping, so a -1 number is only ever reported as a diagnosis.
    direction: int = 1
    gross: float = 2.0               # gross exposure before the vol target
    vol_est_window: int = 60         # window for the portfolio vol estimate
    target_vol: float = 0.20         # annualized target for the neutral book
    scale_cap: float = 2.0
    margin_budget: float = 0.75      # Reg-T is charged on *both* legs, so this is the
    max_gross_weight: float = 3.0    # binding constraint: budget 0.75 -> gross 1.5
    dd_halve: float = 0.15
    dd_flat: float = 0.25
    dd_cooldown: int = 21
    dd_mode: str = "step"

    history_bars: int = field(default=300, compare=False)

    def scaled(self, factor: float) -> "Params":
        """Sensitivity helper: stretch the horizons together."""
        return replace(
            self,
            lookback=max(1, int(round(self.lookback * factor))),
            vol_window=max(5, int(round(self.vol_window * factor))),
        )


DEFAULTS = Params()
TRADED_UNIVERSE = traded_universe(DEFAULTS)


def reversal_scores(prices: pd.DataFrame, p: Params) -> pd.Series:
    """Rank score per name: trailing `lookback`-session return, optionally vol-adjusted.

    Low score = biggest loser = the long leg. Names without a complete window are dropped
    rather than filled, so a halted or freshly listed name cannot be ranked on stale bars.
    """
    if len(prices) <= p.lookback:
        return pd.Series(dtype=float)
    ret = prices.iloc[-1] / prices.iloc[-1 - p.lookback] - 1.0
    ret = ret.replace([np.inf, -np.inf], np.nan).dropna()
    if not p.vol_adjust:
        return ret.sort_values()
    daily = prices[ret.index].pct_change().iloc[-p.vol_window:]
    sigma = daily.std(ddof=1)
    sigma = sigma.where(sigma > 0)
    return (ret / sigma).replace([np.inf, -np.inf], np.nan).dropna().sort_values()


def target_weights(prices: pd.DataFrame, equity_curve=(), params: Params | None = None,
                   state: dict | None = None, volumes: pd.DataFrame | None = None):
    """Signed target weights for the next session. See the module docstring."""
    p = params or DEFAULTS
    diag = {"n_bars": int(len(prices))}

    prices = prices.sort_index().dropna(axis=1, how="all").ffill()
    need = max(p.lookback, p.vol_window, p.vol_est_window) + 2
    if len(prices) < need:
        diag["state"] = dict(state or {})
        diag["reason"] = f"only {len(prices)} bars, need {need}"
        return {}, diag

    dd_mult, state = s1.drawdown_multiplier(equity_curve, p, state)
    diag["dd_multiplier"] = dd_mult
    diag["state"] = state
    if dd_mult == 0.0:
        diag["reason"] = "drawdown flat"
        return {}, diag

    pool = [t for t in POOLS[p.pool] if t in prices.columns]
    if p.universe_size > 0:
        if volumes is None:
            diag["universe_reason"] = "no volume frame; using the candidate pool whole"
        else:
            pool, udiag = uni.select(prices, volumes.sort_index().reindex(prices.index),
                                     pool, p.universe_size, p.dv_window, p.min_history)
            diag.update(udiag)

    scores = reversal_scores(prices[pool], p)
    diag["n_ranked"] = int(len(scores))
    if len(scores) < 2 * p.n_side:
        diag["reason"] = f"only {len(scores)} rankable names, need {2 * p.n_side}"
        return {}, diag

    low, high = list(scores.index[:p.n_side]), list(scores.index[-p.n_side:])
    longs, shorts = (low, high) if p.direction >= 0 else (high, low)
    per_leg = p.gross / (2.0 * p.n_side)
    raw = {t: per_leg for t in longs}
    raw.update({t: -per_leg for t in shorts})

    # Vol target on the neutral book itself. A dollar-neutral basket realizes far less vol
    # than either leg, so this normally asks for more size than the margin budget will
    # fund; the budget is the dial that actually binds (the same saturation S-8 found in
    # the champion, here by construction rather than by accident).
    returns = prices[list(raw)].pct_change().iloc[-p.vol_est_window:]
    port_ret = (returns * pd.Series(raw)).sum(axis=1)
    sigma = s1.realized_vol(port_ret, p.vol_est_window)
    scale = min(p.scale_cap if not np.isfinite(sigma) or sigma <= 0 else p.target_vol / sigma,
                p.scale_cap)
    diag["portfolio_vol"] = None if not np.isfinite(sigma) else round(float(sigma), 4)
    diag["vol_scale"] = round(float(scale), 4)

    weights = {t: w * scale * dd_mult for t, w in raw.items()}

    # Reg-T charges initial margin on the short leg as well as the long, so a neutral book
    # at gross G consumes G/2 of budget. Both caps are on |weight|.
    margin = sum(abs(w) * MARGIN_REQ.get(t, BASE_MARGIN_REQ) for t, w in weights.items())
    gross = sum(abs(w) for w in weights.values())
    shrink = 1.0
    if margin > p.margin_budget > 0:
        shrink = min(shrink, p.margin_budget / margin)
    if gross > p.max_gross_weight > 0:
        shrink = min(shrink, p.max_gross_weight / gross)
    if shrink < 1.0:
        weights = {t: w * shrink for t, w in weights.items()}
    weights = {t: round(w, 6) for t, w in weights.items() if abs(w) > 1e-4}

    diag["margin_used"] = round(sum(abs(w) * MARGIN_REQ.get(t, BASE_MARGIN_REQ)
                                    for t, w in weights.items()), 4)
    diag["gross_weight"] = round(sum(abs(w) for w in weights.values()), 4)
    diag["net_weight"] = round(sum(weights.values()), 4)
    diag["longs"] = longs
    diag["shorts"] = shorts
    diag["reason"] = "reversal"
    return weights, diag
