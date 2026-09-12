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

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

import universe as uni

TRADING_DAYS = 252

# Unlevered ranking sleeve: index, sector, rates, commodity.
RANK_UNIVERSE = ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "TLT", "GLD"]

#: S-14 breadth. The eight sector SPDRs that complete the GICS map RANK_UNIVERSE starts
#: (it carries only XLK/XLF/XLE), fetched 2026-09-11. No survivorship issue - every one of
#: these still trades - but two list mid-sample (XLRE 2015-10-08, XLC 2018-06-19) and the
#: ranking gate in `target_weights` only admits a name once it has a full lookback of
#: priced bars, so they enter the sleeve on their own schedule rather than retroactively.
SECTOR_SLEEVE = ["XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC"]

#: S-14 breadth, second ring: asset classes the sector map does not span at all
#: (developed ex-US, high yield credit, intermediate Treasuries, silver, REITs).
MACRO_SLEEVE = ["EFA", "HYG", "IEF", "SLV", "VNQ"]

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
#
#: The 3x map the sleeve shipped with from S-1 to S-17, kept as a named constant because
#: `S1_PROXY=on` puts it back and because MARGIN_REQ below must state IBKR's requirement on
#: these instruments whether or not this strategy currently holds them.
LEVERED_PROXY_3X = {"SPY": ("UPRO", 3.0), "QQQ": ("TQQQ", 3.0), "TLT": ("TMF", 3.0)}

#: **Shipped: empty.** S-18 retired the 3x sleeve. The structural fact is that IBKR charges
#: 0.333 of margin per unit of economic exposure on a 3x ETF against 0.5 on an ordinary one,
#: so the proxies' entire contribution was that 2.25x of exposure fitted inside the 0.75
#: margin budget - not edge, only room. Measured: S-15 (e) priced them at **-1.28 CAR for
#: worse Sharpe, worse drawdown and $20k more commission**, S-16 measured the combination
#: with the overlay off at **24.403% against the champion's 24.404%, paired -0.00 bps/day
#: (t -0.00, 3,689 sessions)** at std 0.155 vs 0.170, and S-18 split it: the unlevered book
#: gives up 1.48 CAR in 2012-2019 and takes back 1.94 in 2020-2026, with better Sharpe in
#: both halves. `S1_PROXY=on` restores the map (main.py) and reproduces the S-12 champion.
LEVERED_PROXY = {}

REGIME_TICKER = "SPY"


def traded_universe(params: "Params | None" = None) -> list[str]:
    """Every ticker the algorithm must subscribe to for a given ranking sleeve."""
    p = params or DEFAULTS
    ranked = list(p.rank_universe)
    return sorted(set(ranked) | set(p.risk_off_sleeve)
                  | {t for t, _ in LEVERED_PROXY.values()} | {REGIME_TICKER})

#: Overnight initial margin charged per dollar of notional. Reg-T is 50% for an ordinary
#: marginable ETF; IBKR multiplies the requirement by a leveraged ETF's leverage factor,
#: which caps the 3x names at 100% (i.e. they consume cash, they cannot be borrowed against).
BASE_MARGIN_REQ = 0.5


def margin_requirement(instrument: str) -> float:
    """Initial margin per dollar of notional for one traded instrument.

    Read off `LEVERED_PROXY_3X` rather than `LEVERED_PROXY`: what IBKR charges for TQQQ is a
    fact about TQQQ, not about whether this strategy happens to hold it today. Keeping the
    two apart is what lets S-18's empty proxy map and an `S1_PROXY=on` control produce the
    same margin table, so the control reproduces the S-12 champion to the digit.
    """
    multiple = next((m for _, (proxy, m) in LEVERED_PROXY_3X.items() if proxy == instrument), 1.0)
    return min(1.0, BASE_MARGIN_REQ * multiple)


@dataclass(frozen=True)
class Params:
    """Tunables. Every one of these is swept in the S-1 sensitivity test."""

    rank_universe: tuple = tuple(RANK_UNIVERSE)  # sleeve momentum is ranked over
    #: "equal" | "rank" | "momentum" | "invvol". S-12 promoted "invvol": momentum decides
    #: *which* three names are held, and their share of the exposure budget is then set by
    #: risk rather than by count. Equal weight equalizes notional, so the most volatile
    #: winner supplies most of the book's variance - and on this sleeve that gap is a factor
    #: of two or three (GLD/TLT ~12% vol against XLE/XLK ~30%).
    weight_mode: str = "invvol"
    #: S-12 risk parity. Trailing window (sessions) and exponent for `weight_mode="invvol"`:
    #: a winner's share of the exposure budget is proportional to (1 / sigma) ** power,
    #: measured on the *unlevered* ranked series. power 0 collapses to equal weight, 1 is
    #: full inverse-vol, and the intermediate values are the usual shrinkage between the
    #: two - a single dial rather than a second allocation mode.
    #:
    #: LEAN, full period, at power 1.0: window 10 -> 22.8% CAR / 0.857 Sharpe / 29.4% DD,
    #: **20 -> 24.25 / 0.915 / 25.4**, **21 -> 24.40 / 0.921 / 25.1**, **30 -> 24.18 / 0.911
    #: / 25.1**, 40 -> 23.74 / 0.893 / 27.4, 60 -> 23.40 / 0.879 / 25.5, against an
    #: equal-weight champion at 23.61 / 0.874 / 25.9. So it is a shelf over 20-30 that
    #: collapses at 10 and decays back toward equal weight by 60; 21 is one trading month,
    #: the a-priori point inside the shelf, and 20 is the argmax. The tilt is also monotone
    #: in strength at window 21 - power 0.5 gives 24.10 / 0.902, i.e. half the gain for half
    #: the tilt - which is the dose-response a fitted cell does not have.
    #:
    #: It is not free: the vol ratios drift daily, so the book re-weights between rotations
    #: and orders rise 2,573 -> 4,735 with fees $37.4k -> $45.7k. The extra $8.3k is paid
    #: for out of the 0.8 points of extra CAR, but it is the reason a *longer* window is the
    #: honest fallback if commission ever rises.
    alloc_vol_window: int = 21
    alloc_vol_power: float = 1.0
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
    #: S-18 shipped the overlay **off**. 9.0 is a 900% drawdown, which is unreachable, so
    #: the breaker code runs and never fires; `S1_DD_HALVE=0.15 S1_DD_FLAT=0.25` restores the
    #: S-12 champion's breaker exactly. Why it was retired, in order of evidence: S-15 priced
    #: it at **-1.59 CAR** (paired -0.51 bps/day, t -1.93, OOS t -2.35) for 2.1 points of
    #: drawdown - the only near-significant statistic in that whole attribution, and its sign
    #: is against the switch; S-16 then showed that in an *unlevered* book it is strictly
    #: harmful, monotone in return and flat-to-better in drawdown (0.80 budget: shipped
    #: 24.551 / DD 25.5, widened 25.333 / DD 25.0, off 25.903 / DD 25.1), which is S-8's
    #: re-arming problem - a step breaker that flattens at -25% sells the bottom and the
    #: 21-day cooldown then holds the book out of the recovery.
    dd_halve: float = 9.0                  # halve exposure below this drawdown (off: see above)
    dd_flat: float = 9.0                   # go flat below this drawdown (off: see above)
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
    # --- S-20: what the book holds while the regime gate is pulled ---
    #: **Shipped: empty, which is the champion - the off-state is cash.** `risk_on` switches
    #: the whole book off in a volatility crisis, and that switch stays (S-15 priced it at
    #: -2.02 CAR for 6.3 points of drawdown: it is a drawdown instrument). What it has never
    #: had is a second off-state. A non-empty sleeve here is ranked by the *same* momentum
    #: score as the main sleeve and its top `risk_off_top_n` names are funded while the gate
    #: is off, subject to the same `min_momentum` floor - so a defensive name is held only if
    #: it is actually trending, and the book falls back to cash when none is.
    #:
    #: The sleeve is deliberately a parameter rather than a constant: the point of the item
    #: is that the off-state is a *choice*, and naming a fixed basket in code would hide it.
    #:
    #: **S-20 measured it and REFUSED it, and the reason is the one S-15 and S-16 gave for
    #: every other lever on this sleeve: it buys size, not edge.** `TLT,IEF,GLD` at top 1
    #: earns 26.550% / 0.972 / DD 25.4% against the champion's 24.403% / 0.994 / 23.7%, so
    #: +2.15 CAR at *lower* Sharpe, and realized vol rises 0.155 -> 0.177. Scaled to that
    #: same vol the champion itself would have earned 27.867%, i.e. the defensive off-state
    #: is **-1.32 CAR points worse than simply running the existing book bigger**. The
    #: paired daily difference is +0.90 bps/day at t 0.83 (risk-off sessions alone +4.85 at
    #: t 0.73), `evaluate.py` refuses it at 0 bp on the drawdown tolerance, and the
    #: pre-registered rule required both cost models. TLT alone - the a-priori choice - is
    #: worth +0.28 bps/day at t 0.31 and -2.10 vol-matched. Do not re-open as a sleeve,
    #: `top_n` or threshold question; what would change the answer is a defensive asset with
    #: a *conditional* crisis payoff, and the probe found none (risk-off minus risk-on for
    #: TLT/IEF/GLD is +1.39 / +1.50 / +8.07 bps at t 0.28 / 0.73 / 1.66).
    risk_off_sleeve: tuple = ()
    risk_off_top_n: int = 1
    #: Multiplier on `target_exposure` for the defensive book only. 1.0 gives the defensive
    #: holding the same exposure request a risk-on holding would get, which the vol target
    #: and the margin budget then size exactly as they size everything else.
    #:
    #: **Measured inert over [0.5, 1.0] and kept only as documentation of that** (S-20).
    #: The vol target scales the book by `target_vol / sigma` and `sigma` is proportional to
    #: the exposure request, so halving `target_exposure` exactly doubles `vol_scale` and
    #: the funded weights do not move - LEAN reproduced the 1.0 cell to every digit at 0.5
    #: (5,304 orders, 26.550%, $33,990.30). It only bites once `scale_cap` binds: on
    #: 2020-03-20 the TLT book is gross 1.1183 at both 1.0 and 0.5 (vol_scale 0.639 / 1.278)
    #: and only falls to 0.875 at 0.25, where the cap stops the compensation. This is S-8's
    #: finding about the vol target restated for the off-state: under a flat margin budget
    #: an exposure *request* is not a size dial.
    risk_off_exposure: float = 1.0
    #: Shape of the drawdown overlay between `dd_halve` and `dd_flat`. "step" is the
    #: champion's 1.0 / 0.5 / 0.0; "taper" declines linearly from 1.0 at `dd_halve` to 0.0
    #: at `dd_flat`, so the book is already small when it reaches the breaker instead of
    #: taking the last 10 points of drawdown at half size.
    dd_mode: str = "step"

    # --- O-1b: options-implied size scaler ---
    #: O-1 refused implied vol as a *gate* on the intraday sleeve but measured a real
    #: residual: corr(SPY ATM IV, |daily P&L|) = +0.252 at t = +12.67, positive in all three
    #: regimes for all three features. Implied vol forecasts how *big* a day is, not which
    #: way - worthless on a book whose level is negative, possibly worth something on this
    #: one, where the level is positive. This is a size dial, not a signal: the final weights
    #: are multiplied by
    #:
    #:      clip( (trailing median IV / prior-day IV) ** iv_scale_power, min, max )
    #:
    #: 0 = off and reproduces the champion bit for bit. Positive power is the *inverse*
    #: reading (spend less when the market prices a big day); negative is the direct one.
    #: The store (`data/options/iv_regime.csv`) starts 2017-01-03 and the champion's sample
    #: starts 2012, so uncovered days get factor 1.0 - they run exactly as the champion,
    #: which is why the study is judged on the 2017-2026 sub-period as well as the full one.
    iv_scale_power: float = 0.0
    iv_scale_field: str = "iv_atm_1w"
    iv_scale_window: int = 60              # trailing median window, in store rows
    iv_scale_min: float = 0.5
    iv_scale_max: float = 1.5

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

#: margin per dollar of notional; anything unlisted falls back to Reg-T 50%. The 3x
#: instruments are listed whether or not the shipped map trades them (S-18), so an
#: `S1_PROXY=on` control charges them the 100% IBKR really requires.
MARGIN_REQ = {t: margin_requirement(t) for t in sorted(
    set(TRADED_UNIVERSE) | {p for p, _ in LEVERED_PROXY_3X.values()}
    | set(MEGACAP_SLEEVE) | set(SECTOR_SLEEVE) | set(MACRO_SLEEVE))}


#: O-1b store location. `scripts/iv_regime.py` writes the parquet and mirrors it here as
#: CSV, because the LEAN-side Python 3.11 has no pyarrow. Overridable so a sweep can point
#: at an alternative build without editing code.
IV_REGIME_CSV = Path(os.environ.get(
    "IV_REGIME_CSV", Path(__file__).resolve().parents[2] / "data" / "options" / "iv_regime.csv"))

_IV_CACHE: dict = {}


def iv_regime_series(field: str) -> pd.Series:
    """`field` from the IV store, indexed by date, ascending. Empty if the store is absent.

    Cached per field: `target_weights` is called once per session and the file is small,
    but a full backtest calls it ~3,700 times.
    """
    if field in _IV_CACHE:
        return _IV_CACHE[field]
    series = pd.Series(dtype=float)
    try:
        frame = pd.read_csv(IV_REGIME_CSV, usecols=["day", field])
        series = pd.Series(frame[field].astype(float).values,
                           index=pd.to_datetime(frame["day"])).sort_index().dropna()
    except Exception:                      # missing file or column: the scaler stays inert
        series = pd.Series(dtype=float)
    _IV_CACHE[field] = series
    return series


def iv_size_factor(as_of, p: "Params") -> tuple[float, dict]:
    """Size multiplier from options-implied vol, and its diagnostics (O-1b).

    Causal by construction: only store rows dated **strictly before** the last price bar
    are read, so whatever timestamp convention the caller's price index uses - LEAN stamps
    a daily bar at the start of the next session, the paper runner at the session itself -
    the value used was published before the order can be sent. The reference is the trailing
    median of the same field over `iv_scale_window` rows ending at that same row, so the
    dial has no level parameter to fit.

    Returns 1.0, i.e. the champion's behaviour, whenever the scaler is off, the store is
    missing, the day is not covered (the store starts 2017 and the sample starts 2012) or
    there is not yet a full median window.
    """
    if not p.iv_scale_power:
        return 1.0, {}
    series = iv_regime_series(p.iv_scale_field)
    if series.empty:
        return 1.0, {"iv_scale_reason": "no store"}
    prior = series.loc[series.index < pd.Timestamp(as_of)]
    if len(prior) < p.iv_scale_window:
        return 1.0, {"iv_scale_reason": "uncovered"}
    latest = float(prior.iloc[-1])
    median = float(prior.iloc[-p.iv_scale_window:].median())
    if not (np.isfinite(latest) and np.isfinite(median)) or latest <= 0 or median <= 0:
        return 1.0, {"iv_scale_reason": "bad value"}
    factor = float(np.clip((median / latest) ** p.iv_scale_power,
                           p.iv_scale_min, p.iv_scale_max))
    return factor, {"iv_scale": round(factor, 4), "iv_latest": round(latest, 4),
                    "iv_median": round(median, 4),
                    "iv_asof": str(prior.index[-1].date())}


def allocate(winners, scores, mode: str, vols: pd.Series | None = None,
             power: float = 1.0) -> dict:
    """Share of the exposure budget per winner. Shares sum to 1.

    * `equal`    - 1/N each. The shipped default.
    * `rank`     - linearly declining in rank (N, N-1, ... 1), normalized. Uses only the
                   ordering, so it cannot be dominated by one outlier score.
    * `momentum` - proportional to the blended momentum score itself. Winners are already
                   filtered to positive scores, so shares are positive, but a single 3x-ETF
                   score can swallow most of the book.
    * `invvol`   - S-12 risk parity: proportional to `(1 / sigma) ** power` on the trailing
                   vol of the *unlevered* ranked name. Equal weight equalizes notional, which
                   means the riskiest winner supplies most of the portfolio's variance; the
                   sleeve spans GLD/TLT at ~12% vol and XLE/XLK at ~30%, so the gap is a
                   factor of two or three. `vols` is a Series indexed by winner; a name whose
                   vol is missing or non-positive is given the median vol rather than dropped,
                   so a data gap cannot silently concentrate the book.
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
    elif mode == "invvol" and vols is not None:
        finite = [float(v) for v in (vols.get(t) for t in winners)
                  if v is not None and np.isfinite(v) and v > 0]
        if not finite:
            raw = {t: 1.0 for t in winners}
        else:
            fallback = float(np.median(finite))
            raw = {}
            for t in winners:
                v = float(vols.get(t, np.nan))
                if not np.isfinite(v) or v <= 0:
                    v = fallback
                raw[t] = v ** (-float(power))
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


#: F-3. Path to a CSV of daily cross-sectional forecasts, `date` rows by ticker columns, as
#: written by `scripts/sweep_f3.py --export`. Empty (the default) means the champion's momentum
#: blend decides the ranking and nothing below runs.
ML_SCORES_PATH = os.environ.get("S1_ML_SCORES", "")
#: "rank" (the researched cell) replaces only the *ranking*, keeping the absolute momentum floor
#: as the entry gate; "pure" hands both the ranking and the gate to the forecast.
ML_MODE = os.environ.get("S1_ML_MODE", "rank")

_ML_TABLE: "pd.DataFrame | None" = None
_ML_LOADED = False


def ml_table() -> "pd.DataFrame | None":
    """The forecast file, read once. Returns None when the feature is off."""
    global _ML_TABLE, _ML_LOADED
    if not _ML_LOADED:
        _ML_LOADED = True
        if ML_SCORES_PATH:
            path = Path(ML_SCORES_PATH)
            if not path.is_absolute():
                path = Path(__file__).resolve().parents[2] / ML_SCORES_PATH
            frame = pd.read_csv(path, index_col=0)
            frame.index = pd.to_datetime(frame.index).normalize()
            _ML_TABLE = frame.sort_index()
    return _ML_TABLE


def ml_scores(as_of, tickers) -> "pd.Series | None":
    """The forecast row for `as_of`, reindexed onto `tickers`, or None.

    The lookup is an **exact** date match, never an as-of fill. The file is written from the
    same daily calendar the engine reads, so a miss means the two calendars disagree - which
    must fail loudly rather than silently rank on a neighbouring day's forecast. A date
    outside the file's range (before it starts or after it ends) simply returns None and the
    caller keeps the momentum ranking, so a run wider than the forecast is still well defined.
    """
    table = ml_table()
    if table is None:
        return None
    stamp = pd.Timestamp(as_of).normalize()
    if stamp not in table.index:
        if stamp < table.index[0] or stamp > table.index[-1]:
            return None
        raise KeyError(f"S1_ML_SCORES has no row for {stamp.date()} inside its own range "
                       f"({table.index[0].date()}..{table.index[-1].date()})")
    row = table.loc[stamp]
    if isinstance(row, pd.DataFrame):           # duplicate dates would be a build bug
        raise KeyError(f"S1_ML_SCORES has {len(row)} rows for {stamp.date()}")
    # A name with no forecast (listed after the panel was built, or dropped from it) is
    # unrankable rather than best: -1e9 puts it last, the convention `mom_score="riskadj"`
    # already uses above.
    return row.reindex(tickers).astype(float).fillna(-1e9)


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

    # F-3: an external cross-sectional forecast may replace the ranking score. Off unless
    # S1_ML_SCORES names a file, so an unset environment leaves the champion untouched.
    ml = ml_scores(prices.index[-1], score.index)
    if ml is not None:
        if ML_MODE == "rank":
            # Keep the champion's entry discipline - a name must still clear the absolute
            # momentum floor to be fundable - and change only the *order* of the survivors.
            eligible &= (score > p.min_momentum)
        score = ml
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


#: S-28. Path to a CSV of per-instrument daily returns, `date` rows by ticker columns, used
#: **only** for the vol-target estimate in `_size`. Empty (the default) means the estimate is
#: the close-to-close `pct_change` this book has always used and nothing below runs. It exists
#: because S-25 showed the book is paid in the overnight leg while its risk model is measured
#: close to close; F-3's `S1_ML_SCORES` is the same pattern for the ranking.
VOL_RETURNS_PATH = os.environ.get("S1_VOL_RETURNS", "")

_VOL_TABLE: "pd.DataFrame | None" = None
_VOL_LOADED = False


def vol_table() -> "pd.DataFrame | None":
    """The vol-estimate return file, read once. Returns None when the feature is off."""
    global _VOL_TABLE, _VOL_LOADED
    if not _VOL_LOADED:
        _VOL_LOADED = True
        if VOL_RETURNS_PATH:
            path = Path(VOL_RETURNS_PATH)
            if not path.is_absolute():
                path = Path(__file__).resolve().parents[2] / VOL_RETURNS_PATH
            frame = pd.read_csv(path, index_col=0)
            frame.index = pd.to_datetime(frame.index).normalize()
            _VOL_TABLE = frame.sort_index()
    return _VOL_TABLE


def set_vol_returns(frame: "pd.DataFrame | None") -> None:
    """Research hook: install (or clear) the vol-estimate frame in this process.

    A sweep that prices several estimators in one run cannot do it through the environment,
    because the file is read once at first use. `None` restores the shipped estimate.
    """
    global _VOL_TABLE, _VOL_LOADED
    _VOL_TABLE = None if frame is None else frame.sort_index()
    _VOL_LOADED = True


def vol_returns(prices: pd.DataFrame, instruments: list, p: "Params") -> pd.DataFrame:
    """The return window the vol target is measured on.

    Close-to-close on the instruments actually held, which is what the champion ships. When
    an override frame is installed it supplies the same window instead, on the same dates and
    in the same units, so only the *definition* of a daily return changes and every other
    piece of sizing is untouched. Dates outside the frame's own range fall back to the shipped
    estimate (a run wider than the override is still well defined); a date or an instrument
    missing *inside* its range fails loudly rather than silently mixing the two, which is the
    rule `ml_scores` already follows.
    """
    base = prices[instruments].pct_change().iloc[-p.vol_est_window:]
    table = vol_table()
    if table is None:
        return base
    window = pd.DatetimeIndex(base.index).normalize()
    if window[0] < table.index[0] or window[-1] > table.index[-1]:
        return base
    missing = window.difference(table.index)
    if len(missing):
        raise KeyError(f"S1_VOL_RETURNS has no row for {missing[0].date()} inside its own "
                       f"range ({table.index[0].date()}..{table.index[-1].date()})")
    absent = [t for t in instruments if t not in table.columns]
    if absent:
        raise KeyError(f"S1_VOL_RETURNS has no column for {absent}")
    out = table.loc[window, list(instruments)].copy()
    out.index = base.index
    return out


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
    if dd_mult == 0.0:
        diag["reason"] = "drawdown flat"
        return {}, diag
    # S-20. The gate's off-state is cash unless a defensive sleeve is configured, in which
    # case the same momentum machinery runs over that sleeve instead. The drawdown breaker
    # above is *not* given this second state: it fires on the book's own losses, so a book
    # that has already lost should stop, not rotate.
    defensive = bool(p.risk_off_sleeve) and not on
    if not on and not defensive:
        diag["reason"] = "risk-off"
        return {}, diag

    pool = tuple(p.risk_off_sleeve) if defensive else p.rank_universe
    if p.universe_size > 0 and not defensive:
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
    # S-20: the defensive sleeve is two or three names, so a cross-sectional median gate
    # would always admit its leader whatever it is doing. The off-state keeps the absolute
    # floor, which is what makes "hold cash when nothing is trending" reachable.
    floor = p.min_momentum if defensive else entry_floor(scores, p)
    if p.entry_mode == "median" and len(scores) >= 2 and not defensive:
        diag["entry_floor"] = round(floor, 4)

    def passes(ticker) -> bool:
        return float(scores.get(ticker, -np.inf)) > floor and bool(eligible.get(ticker, True))

    if defensive:
        winners = [t for t in scores.index[:p.risk_off_top_n] if passes(t)]
        diag["defensive"] = True
        diag["scores"] = {t: round(float(v), 4) for t, v in scores.items()}
        if not winners:
            diag["reason"] = "risk-off, nothing defensive trending"
            return {}, diag
        return _size(prices, winners, scores, p, dd_mult, diag, state, prev_ages,
                     exposure=p.target_exposure * p.risk_off_exposure, defensive=True)

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

    return _size(prices, winners, scores, p, dd_mult, diag, state, prev_ages,
                 exposure=p.target_exposure, defensive=False)


def _size(prices, winners, scores, p: Params, dd_mult, diag, state, prev_ages,
          exposure: float, defensive: bool):
    """Turn a chosen set of names into funded weights. The only sizing path in the file.

    Split out of `target_weights` by S-20 so the defensive off-state book is sized by
    *exactly* the machinery the risk-on book is sized by - the vol target, the margin
    budget, the gross cap and the O-1b dial in the same order - rather than by a second
    implementation that could drift. `exposure` is the only thing the two callers pass
    differently, and `defensive` decides whether the funded set is handed forward as
    momentum incumbents (it is not: a defensive holding must not defend a slot in the
    risk-on ranking when the gate flips back on).
    """
    # Notional per winner set by `weight_mode`, expressed through the levered proxy
    # where one exists.
    # Dividing by the multiple is what makes target_exposure mean what it says: a 3x ETF
    # gets a third of the weight for the same exposure. Sizing each name at 1/N of equity
    # instead would peg gross weight at 1.0 and leave the vol target able only to cut.
    # S-12: risk parity needs each winner's own trailing vol. Measured on the unlevered
    # ranked series, not on the proxy actually traded, because `raw` below already divides
    # by the proxy's leverage multiple - so the share being split here is unlevered-
    # equivalent exposure, and it must be equalized against unlevered-equivalent risk.
    alloc_vols = None
    if p.weight_mode == "invvol":
        alloc_vols = (prices[winners].pct_change().iloc[-p.alloc_vol_window:].std(ddof=1)
                      * np.sqrt(TRADING_DAYS))
        diag["alloc_vols"] = {t: round(float(v), 4) for t, v in alloc_vols.items()}
    shares = allocate(winners, scores, p.weight_mode, alloc_vols, p.alloc_vol_power)

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
        raw[instrument] = raw.get(instrument, 0.0) + (exposure * shares[ticker]) / mult
        leverage[instrument] = mult

    # Vol target on the instruments actually held, not on their unlevered cousins.
    # S-28: `vol_returns` is the shipped close-to-close window unless an override is installed.
    returns = vol_returns(prices, list(raw), p)
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

    # O-1b. Applied *after* the budget shrink, not to `scale`. With a flat margin budget the
    # vol target is already inert upwards (S-8): the budget refuses the extra size, so a
    # multiplier folded into `scale` could only ever cut. A size dial has to be able to do
    # both, so it multiplies the funded book. The consequence is explicit rather than hidden:
    # a factor above 1 spends more than `margin_budget`, which is why `iv_scale_max` exists
    # and why main.py measures the margin actually carried.
    iv_factor, iv_diag = iv_size_factor(prices.index[-1], p)
    diag.update(iv_diag)
    if iv_factor != 1.0:
        weights = {t: w * iv_factor for t, w in weights.items()}

    weights = {t: round(w, 6) for t, w in weights.items() if w > 1e-4}

    diag["margin_used"] = round(sum(w * MARGIN_REQ.get(t, BASE_MARGIN_REQ)
                                    for t, w in weights.items()), 4)
    diag["gross_weight"] = round(sum(weights.values()), 4)
    diag["effective_exposure"] = round(sum(w * leverage[t] for t, w in weights.items()), 4)
    diag["winners"] = winners
    diag["reason"] = "risk-off, defensive" if defensive else "risk-on"
    # S-11: hand the funded set forward. Empty weights (everything rounded away) count as
    # cash, so the next call sees no incumbents to defend. S-20: a defensive holding is
    # never handed forward - it was not chosen by the risk-on ranking and must not be
    # credited with hysteresis or a holding lock inside it.
    remember_holdings(state, [] if defensive else (winners if weights else []), prev_ages)
    return weights, diag
