"""S-1 signal: volatility-regime momentum rotation with a risk overlay.

Plain pandas, no LEAN imports. `main.py` calls it inside a backtest and the IBKR
paper runner (backlog I-1) imports the identical code, so a signal change can never
silently diverge between research and execution.

Contract
--------
    weights, diag = target_weights(prices, equity_curve, params)

`prices`  : DataFrame of split/dividend-adjusted closes, DatetimeIndex ascending,
            one column per ticker. Must cover at least `HISTORY_BARS` rows and
            include every ticker in RANK_UNIVERSE plus their levered proxies.
`equity_curve` : Series or list of portfolio equity values (oldest first). Only the
            running peak and the latest value matter; pass an empty sequence to skip
            the drawdown overlay.
`params`  : optional Params override.
returns   : (dict ticker -> portfolio weight, dict of diagnostics). Weights are
            fractions of equity and always sum to <= params.max_gross_weight, so the
            strategy never borrows: all leverage comes from the 3x ETFs themselves.

Design notes worth keeping
--------------------------
* Momentum is ranked on the *unlevered* sleeve only. Leveraged ETFs compound daily
  and would win a raw momentum race mechanically rather than on signal.
* Execution swaps a winner for its 3x proxy where an honest one exists (SPY->UPRO,
  QQQ->TQQQ, TLT->TMF). SOXL is deliberately not used as an XLK proxy: semiconductors
  are not the tech sector.
* The vol target is measured on the instruments actually held, so the daily-reset
  decay of the leveraged ETFs is inside the risk estimate rather than assumed away.
* Size is capped by a *margin budget*, not by a flat gross cap (backlog S-6). The old
  `max_gross_weight = 1.0` was an execution artifact: orders are MarketOnOpen, so during
  a rotation both legs are outstanding and LEAN charged initial margin on both without
  netting them, which rejected 3,004 of 3,690 rebalances at gross 1.3. That is now fixed
  in `main.py` (netted share deltas, sells submitted first, and a leverage setting high
  enough that the un-netted intermediate state is not itself the binding constraint), so
  the cap can express what a broker actually charges instead:

      sum(weight_i * MARGIN_REQ[i])  <=  margin_budget

  Reg-T initial margin is 50% of notional for an ordinary ETF, and IBKR marks leveraged
  ETFs up by their leverage factor, which pins the 3x names at 100%. A budget of 1.0
  therefore lets an unlevered basket run at 2.0x gross while a basket of 3x ETFs is still
  held to 1.0x gross - exactly the asymmetry a real account faces. `max_gross_weight`
  survives as a hard ceiling on notional, not as the day-to-day constraint.

  The default budget is 0.75, not the full 1.0, and the 0.25 is a risk buffer rather than
  a fitted parameter: a full Reg-T budget measured 2.07x mean effective exposure and 20.4%
  CAR in LEAN but a 35.4% drawdown, over the 35% limit in `research/champion.json`. 0.75
  keeps 1.63x exposure and 25.2% drawdown. Note also that a live account holding at the
  budget has *zero* excess liquidity, so any adverse move is an immediate margin call;
  the buffer is what makes the number executable rather than merely legal.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

TRADING_DAYS = 252

# Unlevered ranking sleeve: index, sector, rates, commodity.
RANK_UNIVERSE = ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "TLT", "GLD"]

# ranked ticker -> (instrument actually traded, exposure multiple)
LEVERED_PROXY = {"SPY": ("UPRO", 3.0), "QQQ": ("TQQQ", 3.0), "TLT": ("TMF", 3.0)}

REGIME_TICKER = "SPY"

#: every ticker the algorithm must subscribe to
TRADED_UNIVERSE = sorted(set(RANK_UNIVERSE) | {t for t, _ in LEVERED_PROXY.values()})

#: Overnight initial margin charged per dollar of notional. Reg-T is 50% for an ordinary
#: marginable ETF; IBKR multiplies the requirement by a leveraged ETF's leverage factor,
#: which caps the 3x names at 100% (i.e. they consume cash, they cannot be borrowed against).
BASE_MARGIN_REQ = 0.5


def margin_requirement(instrument: str) -> float:
    """Initial margin per dollar of notional for one traded instrument."""
    multiple = next((m for _, (proxy, m) in LEVERED_PROXY.items() if proxy == instrument), 1.0)
    return min(1.0, BASE_MARGIN_REQ * multiple)


MARGIN_REQ = {t: margin_requirement(t) for t in TRADED_UNIVERSE}


@dataclass(frozen=True)
class Params:
    """Tunables. Every one of these is swept in the S-1 sensitivity test."""

    mom_lookbacks: tuple = (20, 60, 120)   # blended momentum horizons, trading days
    top_n: int = 3                         # holdings when risk-on
    trend_window: int = 0                  # risk-off while SPY is below this MA (0 = off)
    regime_vol_window: int = 20            # realized-vol window for the crisis switch
    regime_median_window: int = 252        # its 1-year median
    regime_threshold: float = 1.5          # risk-off once vol_20 > threshold * median
    target_exposure: float = 1.75          # effective exposure before the vol target
    vol_est_window: int = 60               # window for the portfolio vol estimate
    target_vol: float = 0.40               # annualized portfolio vol target
    scale_cap: float = 2.0                 # max vol-target multiplier
    margin_budget: float = 0.75            # fraction of equity usable as initial margin
    max_gross_weight: float = 2.0          # hard ceiling on summed weights; see note above
    dd_halve: float = 0.15                 # halve exposure below this drawdown
    dd_flat: float = 0.25                  # go flat below this drawdown
    dd_cooldown: int = 21                  # rebalances to stay flat after a dd_flat breach
    min_momentum: float = 0.0              # a holding must beat this blended return

    #: bars of history the signal needs before it can speak
    history_bars: int = field(default=300, compare=False)

    def scaled(self, factor: float) -> "Params":
        """Sensitivity helper: stretch the lookbacks and the vol threshold together."""
        return replace(
            self,
            mom_lookbacks=tuple(max(2, int(round(lb * factor))) for lb in self.mom_lookbacks),
            regime_threshold=self.regime_threshold * factor,
        )


DEFAULTS = Params()


def blended_momentum(prices: pd.DataFrame, lookbacks) -> pd.Series:
    """Mean of the trailing total returns over each lookback, per column."""
    scores = []
    for lb in lookbacks:
        if len(prices) <= lb:
            continue
        scores.append(prices.iloc[-1] / prices.iloc[-1 - lb] - 1.0)
    if not scores:
        return pd.Series(dtype=float)
    return pd.concat(scores, axis=1).mean(axis=1)


def realized_vol(returns: pd.Series, window: int) -> float:
    """Annualized realized vol over the last `window` returns."""
    tail = returns.dropna().iloc[-window:]
    if len(tail) < max(5, window // 2):
        return float("nan")
    return float(tail.std(ddof=1) * np.sqrt(TRADING_DAYS))


def risk_on(prices: pd.DataFrame, p: Params) -> tuple[bool, dict]:
    """Regime switch: risk-off only in a genuine volatility crisis.

    Two departures from the original S-1 write-up, both forced by the data (see
    `python scripts/sweep_s1.py --mode regimes`):

    * The write-up asked for risk-on only while 20-day vol sits below its 1-year median.
      That filter is anti-predictive here: SPY earns 4.7%/yr (Sharpe 0.58) on its "calm"
      days versus 10.0% (Sharpe 0.75) on the days it excludes, because vol peaks coincide
      with the sharpest rebounds. Applying it costs the strategy 13 points of annual
      return. Vol is therefore used only to step aside from a crisis - a *multiple* of the
      median, not the median itself.
    * A 200-day trend filter, the obvious replacement, also loses on both halves of the
      sample (2012-2019: 14.7% vs 16.7% CAR; 2020-2026: 15.5% vs 21.2%) while giving up
      no drawdown. It is kept as an option but defaults off.
    """
    if REGIME_TICKER not in prices.columns:
        return False, {"regime_reason": f"{REGIME_TICKER} missing"}
    spy = prices[REGIME_TICKER]
    diag = {}

    if p.trend_window:
        if len(spy) < p.trend_window:
            return False, {"regime_reason": "insufficient trend history"}
        ma = float(spy.iloc[-p.trend_window:].mean())
        diag["trend_ma"] = round(ma, 2)
        if float(spy.iloc[-1]) <= ma:
            diag["regime_reason"] = "below trend"
            return False, diag

    vol_series = spy.pct_change().rolling(p.regime_vol_window).std(ddof=1) * np.sqrt(TRADING_DAYS)
    vol_now = vol_series.iloc[-1]
    median = vol_series.iloc[-p.regime_median_window:].median()
    if not np.isfinite(vol_now) or not np.isfinite(median) or median <= 0:
        return False, {**diag, "regime_reason": "insufficient vol history"}
    diag.update(regime_vol=round(float(vol_now), 4), regime_median=round(float(median), 4))
    if vol_now >= p.regime_threshold * median:
        diag["regime_reason"] = "vol crisis"
        return False, diag
    diag["regime_reason"] = "risk-on"
    return True, diag


def drawdown_multiplier(equity_curve, p: Params, state: dict | None = None):
    """Risk overlay / circuit breaker. Returns (multiplier, new state dict).

    Below `dd_halve` from the running high, exposure is halved. Below `dd_flat` the book
    goes flat for `dd_cooldown` rebalances, and **the high-water mark resets to the
    equity at the moment trading resumes**.

    That reset is the whole trick, and it cost two rewrites to get right:

    1. "Stay flat until a new equity high" is an absorbing state. A flat book earns
       nothing, so its equity can never print a new high; the first version stopped
       trading permanently in 2015.
    2. A cooldown alone does not fix it if the watermark survives. On release the
       drawdown is still past `dd_flat`, so the breaker re-arms immediately and the
       strategy trades one day in twenty-two forever. That version made every parameter
       set collapse onto DD ~25% with erratic, non-monotonic returns.

    Resetting the mark means the breaker measures the loss *since trading resumed*,
    which is what a risk desk actually does after a stop-out.

    `state` is a plain JSON-serializable dict (`peak`, `flat_countdown`) so the live
    runner can persist it across daily invocations.
    """
    state = dict(state or {})
    equity = pd.Series(list(equity_curve), dtype=float).dropna()
    if equity.empty:
        return 1.0, state
    last = float(equity.iloc[-1])
    if last <= 0:
        return 1.0, state

    peak = max(float(state.get("peak", last)), last)
    countdown = int(state.get("flat_countdown", 0))

    if countdown > 0:
        countdown -= 1
        if countdown == 0:
            peak = last                       # fresh start once the breaker releases
        return 0.0, {"peak": peak, "flat_countdown": countdown}

    dd = 1.0 - last / peak
    if dd >= p.dd_flat:
        return 0.0, {"peak": peak, "flat_countdown": p.dd_cooldown}
    return (0.5 if dd >= p.dd_halve else 1.0), {"peak": peak, "flat_countdown": 0}


def target_weights(prices: pd.DataFrame, equity_curve=(), params: Params | None = None,
                   state: dict | None = None):
    """Target portfolio weights for the next session. See module docstring.

    The returned diagnostics carry `state`, which the caller must feed back on the next
    call; it holds the drawdown overlay's cooldown counter.
    """
    p = params or DEFAULTS
    diag = {"n_bars": int(len(prices))}

    prices = prices.sort_index().dropna(axis=1, how="all").ffill()
    max_lb = max(p.mom_lookbacks)
    if len(prices) < max_lb + 2:
        diag["state"] = dict(state or {})
        diag["reason"] = f"only {len(prices)} bars, need {max_lb + 2}"
        return {}, diag

    dd_mult, state = drawdown_multiplier(equity_curve, p, state)
    diag["dd_multiplier"] = dd_mult
    diag["state"] = state

    on, regime_diag = risk_on(prices, p)
    diag.update(regime_diag)
    if not on or dd_mult == 0.0:
        diag["reason"] = "risk-off" if not on else "drawdown flat"
        return {}, diag

    ranked = [t for t in RANK_UNIVERSE if t in prices.columns
              and prices[t].iloc[-max_lb - 1:].notna().all()]
    scores = blended_momentum(prices[ranked], p.mom_lookbacks).sort_values(ascending=False)
    winners = [t for t in scores.index[:p.top_n] if scores[t] > p.min_momentum]
    diag["scores"] = {t: round(float(v), 4) for t, v in scores.head(p.top_n + 2).items()}
    if not winners:
        diag["reason"] = "no positive momentum"
        return {}, diag

    # Equal *notional* per winner, expressed through the levered proxy where one exists.
    # Dividing by the multiple is what makes target_exposure mean what it says: a 3x ETF
    # gets a third of the weight for the same exposure. Sizing each name at 1/N of equity
    # instead would peg gross weight at 1.0 and leave the vol target able only to cut.
    raw, leverage = {}, {}
    for ticker in winners:
        instrument, mult = LEVERED_PROXY.get(ticker, (ticker, 1.0))
        if instrument not in prices.columns or prices[instrument].iloc[-p.vol_est_window - 1:].isna().any():
            instrument, mult = ticker, 1.0     # fall back to the unlevered name
        raw[instrument] = raw.get(instrument, 0.0) + (p.target_exposure / len(winners)) / mult
        leverage[instrument] = mult

    # Vol target on the instruments actually held, not on their unlevered cousins.
    returns = prices[list(raw)].pct_change().iloc[-p.vol_est_window:]
    port_ret = (returns * pd.Series(raw)).sum(axis=1)
    sigma = realized_vol(port_ret, p.vol_est_window)
    scale = p.scale_cap if not np.isfinite(sigma) or sigma <= 0 else min(p.target_vol / sigma, p.scale_cap)
    diag["portfolio_vol"] = None if not np.isfinite(sigma) else round(float(sigma), 4)
    diag["vol_scale"] = round(float(scale), 4)

    weights = {t: w * scale * dd_mult for t, w in raw.items()}

    # Two caps, whichever binds first (S-6). The margin budget is what a broker charges;
    # max_gross_weight is a blunt ceiling on notional so a hypothetical zero-margin
    # instrument could never produce an unbounded book.
    margin = sum(w * MARGIN_REQ.get(t, BASE_MARGIN_REQ) for t, w in weights.items())
    gross = sum(weights.values())
    shrink = 1.0
    if margin > p.margin_budget > 0:
        shrink = min(shrink, p.margin_budget / margin)
    if gross > p.max_gross_weight > 0:
        shrink = min(shrink, p.max_gross_weight / gross)
    if shrink < 1.0:
        weights = {t: w * shrink for t, w in weights.items()}
    weights = {t: round(w, 6) for t, w in weights.items() if w > 1e-4}

    diag["margin_used"] = round(sum(w * MARGIN_REQ.get(t, BASE_MARGIN_REQ)
                                    for t, w in weights.items()), 4)
    diag["gross_weight"] = round(sum(weights.values()), 4)
    diag["effective_exposure"] = round(sum(w * leverage[t] for t, w in weights.items()), 4)
    diag["winners"] = winners
    diag["reason"] = "risk-on"
    return weights, diag
