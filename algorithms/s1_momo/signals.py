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

import universe as uni

TRADING_DAYS = 252

# Unlevered ranking sleeve: index, sector, rates, commodity.
RANK_UNIVERSE = ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "TLT", "GLD"]

#: Single-name sleeve, available on disk from D-1. **Selection-biased**: it is the list of
#: megacaps as of 2026, so back-ranking it before ~2020 knows which companies were going to
#: win. Any result that depends on it is an upper bound, not a forecast - see S-7 in the
#: journal. Kept here so the bias is stated once, next to the data, rather than rediscovered.
#: D-3's `universe.py` fixes the *timing* half of this (membership re-decided each rebalance
#: from trailing dollar volume) but measured that it recovers only ~10% of the bias: the list
#: below is still the pool, and the pool is 2026 survivors. Treat it as a candidate set for
#: research, never as a promotable universe.
MEGACAP_SLEEVE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRKB", "AVGO", "LLY",
    "JPM", "V", "UNH", "XOM", "MA", "JNJ", "PG", "COST", "HD", "ABBV",
    "WMT", "NFLX", "MRK", "KO", "AMD", "PEP", "ADBE", "CRM", "TMO", "BAC",
    "CSCO", "ACN", "LIN", "MCD", "ABT", "ORCL", "PFE", "INTC", "DIS", "QCOM",
    "WFC", "TXN", "CAT", "IBM", "AMAT", "VZ", "NOW", "GE", "UBER", "MU",
]

# ranked ticker -> (instrument actually traded, exposure multiple)
LEVERED_PROXY = {"SPY": ("UPRO", 3.0), "QQQ": ("TQQQ", 3.0), "TLT": ("TMF", 3.0)}

REGIME_TICKER = "SPY"


def traded_universe(params: "Params | None" = None) -> list[str]:
    """Every ticker the algorithm must subscribe to for a given ranking sleeve."""
    ranked = list((params or DEFAULTS).rank_universe)
    return sorted(set(ranked) | {t for t, _ in LEVERED_PROXY.values()} | {REGIME_TICKER})

#: Overnight initial margin charged per dollar of notional. Reg-T is 50% for an ordinary
#: marginable ETF; IBKR multiplies the requirement by a leveraged ETF's leverage factor,
#: which caps the 3x names at 100% (i.e. they consume cash, they cannot be borrowed against).
BASE_MARGIN_REQ = 0.5


def margin_requirement(instrument: str) -> float:
    """Initial margin per dollar of notional for one traded instrument."""
    multiple = next((m for _, (proxy, m) in LEVERED_PROXY.items() if proxy == instrument), 1.0)
    return min(1.0, BASE_MARGIN_REQ * multiple)


@dataclass(frozen=True)
class Params:
    """Tunables. Every one of these is swept in the S-1 sensitivity test."""

    rank_universe: tuple = tuple(RANK_UNIVERSE)  # sleeve momentum is ranked over
    weight_mode: str = "equal"             # "equal" | "rank" | "momentum" (see allocate)
    #: D-3 point-in-time universe. 0 keeps `rank_universe` as a fixed list; any positive
    #: value treats `rank_universe` as a *candidate pool* and re-selects that many members
    #: by trailing dollar volume on every rebalance. Needs a `volumes` frame; without one
    #: the pool is used whole and `universe_reason` says so, so the fallback is visible in
    #: the diagnostics rather than silent.
    universe_size: int = 0
    dv_window: int = uni.DV_WINDOW         # trailing sessions of dollar volume
    min_history: int = uni.MIN_HISTORY     # sessions a name needs before it is selectable
    #: Blended momentum horizons, trading days. The fourth is S-9: one trading year, the
    #: canonical momentum horizon. It is *not* the sweep's argmax (250 was, by 0.06 of
    #: Sharpe) - the full-period Sharpe forms a shelf over a fourth horizon of 220-300
    #: (1.01/1.07/1.10/1.04/1.04/1.03) and falls away at 150 and 320, so 252 is the a-priori
    #: point inside the shelf rather than the fitted peak.
    mom_lookbacks: tuple = (20, 60, 120, 252)
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

    # --- S-9: change what the signal *says*, not how much of it is bought ---
    #: How a sleeve member's momentum is scored. "blend" is the champion: the plain mean of
    #: the trailing returns over `mom_lookbacks`. The other two are the ideas S-7 named and
    #: left untried, and both default off.
    #:   "zscore"  - each horizon is cross-sectionally standardized across the sleeve before
    #:               the horizons are averaged. Under "blend" a 120-day return is numerically
    #:               several times a 20-day one, so the longest horizon effectively decides
    #:               the ranking on its own; standardizing gives each horizon one equal vote.
    #:   "riskadj" - blended momentum divided by the name's own trailing vol, so a quiet
    #:               mover outranks a violent one at equal return. This is the ranking that
    #:               matches what the book is sized on, since the vol target then scales the
    #:               whole portfolio by realized risk anyway.
    mom_score: str = "blend"
    mom_vol_window: int = 60               # trailing vol window for mom_score="riskadj"
    #: Require every horizon in `mom_lookbacks` to be positive before a name is eligible.
    #: A blended score can be carried entirely by one horizon; this asks the horizons to
    #: agree instead of averaging a disagreement away.
    mom_confirm: bool = False
    #: Entry gate. "absolute" is the champion's `score > min_momentum` floor. "median" is
    #: cross-sectional: a name must beat the *sleeve median* score by `min_rel_momentum`.
    #: Note the two are not nested - with top_n < half the sleeve, a zero-threshold median
    #: gate is looser than the absolute floor (the top 3 of 9 always beat the median), so it
    #: keeps the book in the least-bad ETF through a decline. `min_rel_momentum` is what
    #: turns it into a dispersion requirement: trade only when the leaders are actually
    #: leading.
    entry_mode: str = "absolute"
    min_rel_momentum: float = 0.0

    # --- S-10: the two follow-ups S-9 opened, both defaulted off ---
    #: Skip-a-month momentum. Sessions dropped from the *recent* end of every horizon
    #: window, so a lookback of `lb` measures the return from `-1-skip-lb` to `-1-skip`
    #: instead of ending today. This is the standard 12-2 correction: the last month of a
    #: 12-month winner carries short-term reversal, which is noise at a monthly horizon and
    #: has the wrong sign. S-9 never tested it, and the champion is now a 252-day blend, so
    #: it is exactly the configuration the correction was written for.
    #:
    #: What the data says (S-10, LEAN, full period, skip applied to lookbacks >= 120):
    #: 2 -> 19.8% CAR / 0.74 Sharpe, 3 -> 23.0 / 0.86, **5 -> 23.6 / 0.87**, 8 -> 23.6 / 0.87,
    #: 10 -> 22.7 / 0.84, 15 -> 19.1 / 0.70, 20 -> 19.6 / 0.72, against a champion at
    #: 20.9 / 0.78. So the textbook *month* is wrong here and a **week** is right: the shelf
    #: runs 3-10 sessions and collapses on both sides of it. 5 is one trading week, the
    #: a-priori unit inside that shelf, not its argmax.
    mom_skip: int = 5
    #: Apply the skip only to horizons at least this long (0 = every horizon). The champion
    #: blends a 20-day horizon whose entire content *is* the recent month; skipping a week
    #: of a 20-day lookback does not correct that horizon, it truncates it - measured, and
    #: it costs 4.4 points of CAR (19.2% at skip_min_lookback=0 vs 23.6% at 120). Confining
    #: the skip to 252 alone gives 23.3% / 0.87, so the effect lives in the long horizons
    #: and is not a property of one of them.
    mom_skip_min_lookback: int = 120
    #: Per-horizon weights for the blend, aligned with `mom_lookbacks`. Empty = equal votes,
    #: which is what the champion ships. S-9's shelf (Sharpe 0.85 at a fourth horizon of
    #: 150 rising to 1.10 at 250) says the long horizon carries most of the information, so
    #: an explicit overweight on it is worth measuring. Weights are normalized, so only
    #: their ratios matter. Note "equal votes" is only equal after `mom_score="zscore"`;
    #: under "blend" the horizons are raw returns of very different scale, so a weight here
    #: reweights an already-unequal vote.
    mom_weights: tuple = ()

    # --- S-11: stop the book rotating on noise (the champion's remaining weakness) ---
    #: The three levers below all attack the same failure: S-10's calendar decomposition
    #: says the champion's losses are not crises and not the OOS half but 2014/2015/2016
    #: and 2024, and its worst drawdown is a 16-month grind, which is the signature of a
    #: ranking that keeps buying whichever sleeve member has just topped out. Each cuts
    #: turnover, which is also the direction S-3's 2.1bps cost floor rewards.
    #:
    #: (a) Hysteresis. An incumbent holding's score is credited with this many *cross-
    #: sectional standard deviations* of the day's scores before the ranking is cut at
    #: `top_n`, so a challenger has to win by a margin rather than by a rounding error.
    #: The unit is deliberately the day's own score dispersion rather than a return: the
    #: blended score is a mean of raw returns whose scale moves by an order of magnitude
    #: between 2017 and 2020, and a fixed return margin would be inert in one regime and
    #: binding in the other.
    hysteresis: float = 0.0
    #: (b) Minimum holding period, in rebalances. A newly funded name is kept for at least
    #: this many further decisions unless it fails the entry gate outright (score at or
    #: below the floor, or ineligible) or the book goes to cash for regime/drawdown
    #: reasons - so the lock never overrides a risk control, only the ranking.
    min_hold: int = 0
    #: (c) Rank persistence. A name that is not already held must have been inside the
    #: top `top_n` on each of the last this-many decision bars before it can be funded.
    #: Computed by re-scoring truncated price windows rather than from stored history, so
    #: it stays reproducible for the I-1 paper runner without extra persisted state.
    rank_persist: int = 0

    # --- S-8: earn drawdown headroom so that size can be spent ---
    #: Elastic margin budget. 0 keeps `margin_budget` a flat constant, which is what the
    #: champion ships and what makes its vol target inert: the vol target asks for up to
    #: `scale_cap` x exposure, the constant budget refuses, and the book therefore runs at
    #: a *constant margin* in every regime. Set positive and the day's budget becomes the
    #: margin the vol target actually asks for, clipped into
    #: [`margin_budget_floor`, `margin_budget_cap`] - a calm book may spend more than 0.75,
    #: a jumpy one must spend less. Pair it with a high `scale_cap`, otherwise the scale cap
    #: binds first and the elastic ceiling is never reached.
    margin_budget_cap: float = 0.0
    margin_budget_floor: float = 0.0
    #: Per-holding trailing stop: drop a winner trading more than this fraction below its
    #: own trailing `trail_window`-session high. 0 = off. Measured on the *ranked* (unlevered)
    #: series, because a 3x proxy is mechanically three times further below its own high.
    #: Deliberately stateless - it reads prices only, so the I-1 paper runner needs no extra
    #: persisted state, and a stopped name frees its share of the book to cash rather than
    #: concentrating it into the survivors.
    trail_stop: float = 0.0
    trail_window: int = 60
    #: Shape of the drawdown overlay between `dd_halve` and `dd_flat`. "step" is the
    #: champion's 1.0 / 0.5 / 0.0; "taper" declines linearly from 1.0 at `dd_halve` to 0.0
    #: at `dd_flat`, so the book is already small when it reaches the breaker instead of
    #: taking the last 10 points of drawdown at half size.
    dd_mode: str = "step"

    #: bars of history the signal needs before it can speak
    history_bars: int = field(default=300, compare=False)

    def __post_init__(self):
        # A lookback longer than the history window is a *silent* failure, not an error:
        # `target_weights` returns {} with reason "only N bars", the book sits in cash for
        # the entire sample, and the sweep prints a tidy 0.0% CAR that looks like a result.
        # S-9 lost a grid cell to exactly this (a 300-day horizon against the 300-bar
        # default). Widen the window instead, so the horizon is what is being tested.
        need = max(self.mom_lookbacks) + self.mom_skip + max(0, self.rank_persist - 1) + 50
        if self.history_bars < need:
            object.__setattr__(self, "history_bars", need)
        if self.mom_weights and len(self.mom_weights) != len(self.mom_lookbacks):
            raise ValueError(
                f"mom_weights has {len(self.mom_weights)} entries but there are "
                f"{len(self.mom_lookbacks)} lookbacks; they are matched positionally")

    def scaled(self, factor: float) -> "Params":
        """Sensitivity helper: stretch the lookbacks and the vol threshold together."""
        return replace(
            self,
            mom_lookbacks=tuple(max(2, int(round(lb * factor))) for lb in self.mom_lookbacks),
            mom_skip=int(round(self.mom_skip * factor)),
            regime_threshold=self.regime_threshold * factor,
        )


DEFAULTS = Params()

#: every ticker the shipped default subscribes to (main.py and the I-1 paper runner)
TRADED_UNIVERSE = traded_universe(DEFAULTS)

#: margin per dollar of notional; anything unlisted falls back to Reg-T 50%
MARGIN_REQ = {t: margin_requirement(t) for t in sorted(
    set(TRADED_UNIVERSE) | set(MEGACAP_SLEEVE))}


def allocate(winners, scores, mode: str) -> dict:
    """Share of the exposure budget per winner. Shares sum to 1.

    * `equal`    - 1/N each. The shipped default.
    * `rank`     - linearly declining in rank (N, N-1, ... 1), normalized. Uses only the
                   ordering, so it cannot be dominated by one outlier score.
    * `momentum` - proportional to the blended momentum score itself. Winners are already
                   filtered to positive scores, so shares are positive, but a single 3x-ETF
                   score can swallow most of the book.
    """
    n = len(winners)
    if n == 0:
        return {}
    if mode == "rank":
        raw = {t: float(n - i) for i, t in enumerate(winners)}
    elif mode == "momentum":
        raw = {t: max(float(scores[t]), 0.0) for t in winners}
        if sum(raw.values()) <= 0:
            raw = {t: 1.0 for t in winners}
    else:
        raw = {t: 1.0 for t in winners}
    total = sum(raw.values())
    return {t: v / total for t, v in raw.items()}


def horizon_returns(prices: pd.DataFrame, lookbacks, skip: int = 0,
                    skip_min_lookback: int = 0) -> pd.DataFrame:
    """Trailing total return per lookback (index) per ticker (columns).

    `skip` (S-10) ends each window that many sessions before the last bar, so a lookback
    of `lb` measures `-1-skip-lb` -> `-1-skip`. It is applied only to horizons of at least
    `skip_min_lookback` sessions, which is how a long-horizon-only skip is expressed
    without splitting the lookback tuple into two.
    """
    rows = {}
    for lb in lookbacks:
        gap = skip if lb >= skip_min_lookback else 0
        if len(prices) <= lb + gap:
            continue
        end = prices.iloc[-1 - gap]
        rows[int(lb)] = end / prices.iloc[-1 - gap - lb] - 1.0
    return pd.DataFrame(rows).T if rows else pd.DataFrame()


def horizon_weights(per_horizon: pd.DataFrame, p: "Params") -> pd.Series | None:
    """Normalized weight per surviving horizon row, or None for an equal blend.

    Rows can be missing when history is short, so weights are matched to their lookback
    by value rather than by position and then renormalized over what is left.
    """
    if not p.mom_weights:
        return None
    lookup = {int(lb): float(w) for lb, w in zip(p.mom_lookbacks, p.mom_weights)}
    w = pd.Series({lb: lookup.get(int(lb), 0.0) for lb in per_horizon.index}, dtype=float)
    total = w.sum()
    return None if total <= 0 else w / total


def blend(per_horizon: pd.DataFrame, p: "Params") -> pd.Series:
    """Collapse the per-horizon frame to one score per ticker (equal or weighted)."""
    w = horizon_weights(per_horizon, p)
    if w is None:
        return per_horizon.mean(axis=0)
    return per_horizon.mul(w, axis=0).sum(axis=0)


def blended_momentum(prices: pd.DataFrame, lookbacks) -> pd.Series:
    """Mean of the trailing total returns over each lookback, per column."""
    per_horizon = horizon_returns(prices, lookbacks)
    if per_horizon.empty:
        return pd.Series(dtype=float)
    return per_horizon.mean(axis=0)


def momentum_scores(prices: pd.DataFrame, p: Params) -> tuple[pd.Series, pd.Series]:
    """(ranking score, eligibility mask) per column. See `Params.mom_score` (S-9).

    Returned separately from the eligibility gate because the score is also what
    `allocate(mode="momentum")` sizes on, and a z-score is not a return.
    """
    per_horizon = horizon_returns(prices, p.mom_lookbacks, p.mom_skip, p.mom_skip_min_lookback)
    if per_horizon.empty:
        return pd.Series(dtype=float), pd.Series(dtype=bool)

    if p.mom_score == "zscore":
        centered = per_horizon.sub(per_horizon.mean(axis=1), axis=0)
        spread = per_horizon.std(axis=1, ddof=0).replace(0.0, np.nan)
        score = blend(centered.div(spread, axis=0).fillna(0.0), p)
    elif p.mom_score == "riskadj":
        vol = (prices.pct_change().iloc[-p.mom_vol_window:].std(ddof=1)
               * np.sqrt(TRADING_DAYS))
        score = blend(per_horizon, p) / vol.replace(0.0, np.nan)
        score = score.replace([np.inf, -np.inf], np.nan).fillna(-1e9)  # unrankable = last
    else:
        score = blend(per_horizon, p)

    eligible = pd.Series(True, index=score.index)
    if p.mom_confirm:
        eligible &= (per_horizon > 0).all(axis=0).reindex(score.index).fillna(False)
    return score, eligible


def entry_floor(scores: pd.Series, p: "Params") -> float:
    """The score a name must beat to be funded (S-9's `entry_mode`)."""
    if p.entry_mode == "median" and len(scores) >= 2:
        return float(scores.median()) + p.min_rel_momentum
    return p.min_momentum


def leaders(scores: pd.Series, eligible: pd.Series, p: "Params") -> list:
    """The `top_n` highest scores that also clear the entry gate, best first."""
    scores = scores.sort_values(ascending=False)
    floor = entry_floor(scores, p)
    return [t for t in scores.index[:p.top_n] if scores[t] > floor and eligible.get(t, True)]


def persistent_leaders(prices: pd.DataFrame, p: "Params") -> set:
    """S-11(c): names that have led on *every* one of the last `rank_persist` bars.

    Re-scores truncated windows instead of remembering past rankings, which keeps the
    lever stateless: the paper runner reproduces it from prices alone.
    """
    sets = []
    for back in range(max(1, p.rank_persist)):
        window = prices if back == 0 else prices.iloc[:-back]
        scores, eligible = momentum_scores(window, p)
        if scores.empty:
            return set()
        sets.append(set(leaders(scores, eligible, p)))
    return set.intersection(*sets)


def remember_holdings(state: dict, winners, prev_ages: dict) -> dict:
    """Write the funded set and its ages back onto the overlay state.

    Age is counted in rebalances *since* entry, so a name funded for the first time is 0
    and `min_hold=n` locks it through the next n decisions. Kept JSON-serializable for
    the live runner, which persists this dict between daily invocations.
    """
    state["held"] = list(winners)
    state["held_age"] = {t: int(prev_ages.get(t, -1)) + 1 for t in winners}
    return state


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
    if p.dd_mode == "taper" and p.dd_flat > p.dd_halve:
        mult = 1.0 if dd <= p.dd_halve else (p.dd_flat - dd) / (p.dd_flat - p.dd_halve)
        return round(float(mult), 4), {"peak": peak, "flat_countdown": 0}
    return (0.5 if dd >= p.dd_halve else 1.0), {"peak": peak, "flat_countdown": 0}


def target_weights(prices: pd.DataFrame, equity_curve=(), params: Params | None = None,
                   state: dict | None = None, volumes: pd.DataFrame | None = None):
    """Target portfolio weights for the next session. See module docstring.

    The returned diagnostics carry `state`, which the caller must feed back on the next
    call; it holds the drawdown overlay's cooldown counter.

    `volumes` is optional and only consulted when `params.universe_size > 0` (D-3): share
    volume on the same index/columns as `prices`, from which membership is re-decided each
    rebalance. It is a keyword argument rather than a second positional one so every
    existing caller - including the I-1 paper runner, which introspects this signature -
    keeps working unchanged.
    """
    p = params or DEFAULTS
    diag = {"n_bars": int(len(prices))}

    prices = prices.sort_index().dropna(axis=1, how="all").ffill()
    # The skip pushes the window back in time, so it lengthens the history the longest
    # horizon needs by exactly the gap (S-10).
    max_lb = max(p.mom_lookbacks) + (p.mom_skip if max(p.mom_lookbacks) >= p.mom_skip_min_lookback else 0)
    # Rank persistence re-scores windows truncated by up to `rank_persist - 1` bars, so it
    # needs that many extra rows before the signal can speak at all.
    need_bars = max_lb + 2 + max(0, p.rank_persist - 1)
    if len(prices) < need_bars:
        diag["state"] = dict(state or {})
        diag["reason"] = f"only {len(prices)} bars, need {need_bars}"
        return {}, diag

    # S-11: who was funded last time, and for how long. Read before the drawdown overlay,
    # because that call rebuilds the state dict from scratch and would drop these keys.
    prev_held = list((state or {}).get("held") or [])
    prev_ages = {str(t): int(a) for t, a in ((state or {}).get("held_age") or {}).items()}

    dd_mult, state = drawdown_multiplier(equity_curve, p, state)
    diag["dd_multiplier"] = dd_mult
    diag["state"] = state
    # Default to "holding nothing": every early return below is a decision to sit in cash,
    # so an incumbent set must not survive one. The funded set is written back at the end.
    remember_holdings(state, [], prev_ages)

    on, regime_diag = risk_on(prices, p)
    diag.update(regime_diag)
    if not on or dd_mult == 0.0:
        diag["reason"] = "risk-off" if not on else "drawdown flat"
        return {}, diag

    pool = p.rank_universe
    if p.universe_size > 0:
        if volumes is None:
            diag["universe_reason"] = "no volume frame; using the candidate pool whole"
        else:
            pool, udiag = uni.select(prices, volumes.sort_index().reindex(prices.index),
                                     p.rank_universe, p.universe_size,
                                     p.dv_window, p.min_history)
            diag.update(udiag)

    ranked = [t for t in pool if t in prices.columns
              and prices[t].iloc[-max_lb - 1:].notna().all()]
    diag["n_ranked"] = len(ranked)
    scores, eligible = momentum_scores(prices[ranked], p)
    scores = scores.sort_values(ascending=False)
    # S-9: the entry gate is either an absolute floor on the score (the champion) or a
    # cross-sectional one measured against the sleeve median on the same rebalance.
    floor = entry_floor(scores, p)
    if p.entry_mode == "median" and len(scores) >= 2:
        diag["entry_floor"] = round(floor, 4)

    def passes(ticker) -> bool:
        return float(scores.get(ticker, -np.inf)) > floor and bool(eligible.get(ticker, True))

    # S-11(a) hysteresis. Incumbents are *ranked* with a bonus but still *gated* on their
    # raw score, so the bonus can defend a holding against a marginal challenger and can
    # never fund a name the entry gate refuses.
    held = [t for t in prev_held if t in scores.index]
    ranking = scores
    if p.hysteresis > 0 and held:
        spread = float(scores.std(ddof=0))
        if np.isfinite(spread) and spread > 0:
            bonus = p.hysteresis * spread
            ranking = (scores + pd.Series({t: bonus if t in held else 0.0
                                           for t in scores.index})).sort_values(ascending=False)
            diag["hysteresis_bonus"] = round(bonus, 4)
    winners = [t for t in ranking.index[:p.top_n] if passes(t)]

    # S-11(c) rank persistence. A name that is not already held has to have led on every
    # one of the last `rank_persist` bars; incumbents are exempt, because the lever is
    # about what gets bought, not about what gets kept.
    if p.rank_persist > 1:
        confirmed = persistent_leaders(prices[ranked], p)
        blocked = [t for t in winners if t not in held and t not in confirmed]
        if blocked:
            diag["persist_blocked"] = blocked
            winners = [t for t in winners if t not in blocked]

    # S-11(b) minimum holding period. A young holding keeps its slot unless the gate
    # itself refuses it, which is what stops a one-day rank crossing from trading.
    if p.min_hold > 0 and held:
        locked = [t for t in ranking.index
                  if t in held and prev_ages.get(t, 0) < p.min_hold and passes(t)]
        if locked:
            diag["locked"] = locked
            keep = set((locked + [t for t in winners if t not in locked])[:p.top_n])
            winners = [t for t in ranking.index if t in keep]

    diag["scores"] = {t: round(float(v), 4) for t, v in scores.head(p.top_n + 2).items()}
    if not winners:
        diag["reason"] = "no positive momentum"
        return {}, diag

    # Notional per winner set by `weight_mode`, expressed through the levered proxy
    # where one exists.
    # Dividing by the multiple is what makes target_exposure mean what it says: a 3x ETF
    # gets a third of the weight for the same exposure. Sizing each name at 1/N of equity
    # instead would peg gross weight at 1.0 and leave the vol target able only to cut.
    shares = allocate(winners, scores, p.weight_mode)

    # S-8 trailing stop. Shares are allocated over the *pre-stop* winners and a stopped
    # name simply does not get funded, so the book shrinks toward cash instead of doubling
    # down on whatever has not broken yet.
    if p.trail_stop > 0:
        tail = prices[winners].iloc[-p.trail_window:]
        highs, last = tail.max(), tail.iloc[-1]
        stopped = [t for t in winners if last[t] < (1.0 - p.trail_stop) * highs[t]]
        if stopped:
            diag["stopped"] = stopped
            winners = [t for t in winners if t not in stopped]
            if not winners:
                diag["reason"] = "all winners stopped out"
                return {}, diag

    raw, leverage = {}, {}
    for ticker in winners:
        instrument, mult = LEVERED_PROXY.get(ticker, (ticker, 1.0))
        if instrument not in prices.columns or prices[instrument].iloc[-p.vol_est_window - 1:].isna().any():
            instrument, mult = ticker, 1.0     # fall back to the unlevered name
        raw[instrument] = raw.get(instrument, 0.0) + (p.target_exposure * shares[ticker]) / mult
        leverage[instrument] = mult

    # Vol target on the instruments actually held, not on their unlevered cousins.
    returns = prices[list(raw)].pct_change().iloc[-p.vol_est_window:]
    port_ret = (returns * pd.Series(raw)).sum(axis=1)
    sigma = realized_vol(port_ret, p.vol_est_window)
    unbounded = p.scale_cap if not np.isfinite(sigma) or sigma <= 0 else p.target_vol / sigma
    scale = min(unbounded, p.scale_cap)
    diag["portfolio_vol"] = None if not np.isfinite(sigma) else round(float(sigma), 4)
    diag["vol_scale"] = round(float(scale), 4)

    weights = {t: w * scale * dd_mult for t, w in raw.items()}

    # Two caps, whichever binds first (S-6). The margin budget is what a broker charges;
    # max_gross_weight is a blunt ceiling on notional so a hypothetical zero-margin
    # instrument could never produce an unbounded book.
    #
    # S-8: with `margin_budget_cap` set, that budget stops being a constant and becomes the
    # margin the vol target asks for, clipped into [floor, cap]. The clip is the whole point:
    # a flat budget makes the vol target inert, because the budget refuses the extra size in
    # calm markets and never demands less in violent ones.
    budget = p.margin_budget
    if p.margin_budget_cap > 0:
        want = sum(w * unbounded * dd_mult * MARGIN_REQ.get(t, BASE_MARGIN_REQ)
                   for t, w in raw.items())
        budget = float(min(max(want, p.margin_budget_floor), p.margin_budget_cap))
        diag["margin_budget"] = round(budget, 4)

    margin = sum(w * MARGIN_REQ.get(t, BASE_MARGIN_REQ) for t, w in weights.items())
    gross = sum(weights.values())
    shrink = 1.0
    if margin > budget > 0:
        shrink = min(shrink, budget / margin)
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
    # S-11: hand the funded set forward. Empty weights (everything rounded away) count as
    # cash, so the next call sees no incumbents to defend.
    remember_holdings(state, winners if weights else [], prev_ages)
    return weights, diag
