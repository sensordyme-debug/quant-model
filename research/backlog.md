# Research backlog

Ranked list of hypotheses and infrastructure work. The improvement loop takes the top open
item. Move finished items to the bottom under "Done" with a one-line result and the
experiment timestamp.

## Current objective (set 2026-09-08)

A backtest-validated strategy running on IBKR **paper** trading by **2026-09-10**. That means:
S-1 (with the S-4 risk overlay built in) promoted to champion through `scripts/evaluate.py`,
then I-1 running it against the paper account. Daily-frequency only until D-2 delivers
intraday data. Live money stays off the table until the human signs off in `live/`.

Status 2026-09-08: S-1 is promoted, so the remaining gate is I-1. It is blocked on IB Gateway
being logged in on this machine (see `research/BLOCKERS.md`); the runner can be built and
tested against a mock until then. S-1 currently trades at 1.27x exposure and 13.3% vol, which
is well short of the aggressive mandate - deliberately deferred to S-6 rather than allowed to
delay the paper deadline.

## Open (highest value first)

- **S-6 Raise S-1's exposure by fixing execution, not the signal.** S-1 is stuck at 1.27x
  effective exposure and 13.3% realized vol against a 40-60% mandate, purely because
  MarketOnOpen orders leave both legs of a rotation outstanding and gross above 1.0 gets
  rejected for buying power (3,004 of 3,690 rebalances at gross 1.3). Options, cheapest
  first: (a) rotate in two steps, selling into the same batch that buys only the freed
  notional; (b) net the order list so unchanged holdings are never round-tripped, which also
  cuts the $27k fee bill; (c) once D-2 lands minute data, trade the actual close with market
  orders and drop MOO entirely. Target: effective exposure 2x+ with drawdown still under 35%.
  This is the single highest-value change - S-1's Sharpe is fine, its size is not.
- **S-7 Beat buy-and-hold on absolute return.** S-1 compounds at 13.7% against SPY's 15.0%
  and QQQ's 19.9% over 2012-2026; it wins only on drawdown. Candidates: widen the ranking
  sleeve beyond 9 ETFs (the 50 megacaps from D-1 are already on disk), replace equal weight
  with momentum-proportional weight, and revisit `top_n` (3 is a local peak, which is a
  caution flag). Judge on both sub-periods separately, as with the regime filter.
- **I-1 IBKR paper runner (needs IB Gateway logged in on this machine).** Write
  `scripts/paper_trade.py` using `ib_async`: connect to 127.0.0.1:4002 (paper), pull daily
  history for the universe, call the champion's `signals.py` to get target weights, compute
  the order list against current positions, place market-on-close or limit orders, log every
  fill to `live/log/YYYY-MM-DD.jsonl`, and refuse to run if `live/APPROVED_PAPER.md` is missing
  or if the account is not a paper account (IBKR paper account ids start with `DU`). Add a
  kill switch (`live/HALT` file flattens everything) and a Windows scheduled task template
  that runs it at 15:45 ET on trading days. Until Gateway is up, build and test it against
  a mocked connection.
- **D-2 Intraday data (blocks S-2).** `fetch_data.py` writes daily bars only; Yahoo caps
  1-minute history at ~30 days, which is useless for backtesting. Once IB Gateway is logged
  in, pull minute bars with `ib_async` `reqHistoricalData` (1-day chunks, respect pacing
  limits) for SPY/QQQ/IWM/TQQQ/SQQQ first. LEAN minute format:
  `equity/usa/minute/<symbol>/<yyyyMMdd>_trade.zip` holding
  `<yyyyMMdd>_<symbol>_minute_trade.csv` with rows `<ms since midnight ET>,o,h,l,c,v`,
  prices scaled by 10000. Reuse the writer/validator structure already in `fetch_data.py`.
- **S-3 Cross-sectional short-term reversal.** Top-50 liquid names, buy the biggest 1-3 day
  losers and short the biggest winners, hold 1-3 days, dollar neutral, 200% gross. Daily
  data is enough; a second sleeve for the allocator.
- **S-2 Opening-range breakout.** Intraday on SPY/QQQ/IWM (futures later). Enter on a
  break of the first 15-30 minute range with ATR stops, scale out into strength, flat at
  close. Hypothesis: high-frequency small edges compound into volatile but positive equity.
- **S-5 Allocator.** Route capital across S-1, S-2, S-3 by trailing 60-day Sharpe with a
  floor per sleeve.

## Done

- **S-1 Volatility-regime momentum rotation.** 2026-09-08, run `20260908T174548Z`, promoted
  to champion. Full period CAR 13.7%, Sharpe 0.60, MaxDD 23.6%, 3,033 orders; IS 2012-2019
  10.4%/0.57/23.6%, OOS 2020-2026 17.8%/0.64/20.8%. Sensitivity: drawdown holds in 18.0-22.4%
  under every +/-25% shock. Two specified components were rejected on evidence - the
  vol-below-median regime filter is anti-predictive (costs 13 points of CAR) and a 200-day
  trend filter loses on both sub-periods - so the regime switch is a crisis filter at 1.5x the
  median. Signal lives in `algorithms/s1_momo/signals.py` (named `signals` not `signal` to
  avoid shadowing the stdlib module on LEAN's PYTHONPATH). Gross exposure is capped at 1.0 by
  execution constraints, so the 40-60% vol target was *not* met; that shortfall is carried
  forward as S-6, and beating buy-and-hold on return as S-7.
- **E-2 Walk-forward and parameter sweeps** (partial). `scripts/sweep_s1.py` runs ablation,
  grid, sensitivity, regime-comparison and IS/OOS modes against the shipped signal code, and
  `scripts/lean_prices.py` reads LEAN's bars back into pandas. Still S-1-specific: generalize
  to any algorithm when a second strategy needs it.
- **D-1 Data pipeline.** 2026-09-08, run `20260908T162819Z`. `scripts/fetch_data.py` writes
  LEAN daily bars, map files and factor files for 69 symbols (19 ETFs + 50 megacaps),
  1998-01-01 to 2026-09-04. Acceptance algorithm `d1_data_smoke` returns PASS: 15/15 probed
  symbols stream 3690 bars over 2012-2026; factors agree with Yahoo `Adj Close` to 0.003%.
  Minute data deferred to D-2.
- **E-1 Evaluation harness.** `scripts/evaluate.py` compares runs with `champion.json`,
  enforces the min-trades and drawdown rules and promotes only on a pass. Verified on the
  D-1 run, which it correctly refused (14 orders < 30, drawdown 72.7% > 35%). Parameter
  sweeps split out to E-2.
