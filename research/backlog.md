# Research backlog

Ranked list of hypotheses and infrastructure work. The improvement loop takes the top open
item. Move finished items to the bottom under "Done" with a one-line result and the
experiment timestamp.

## Open (highest value first)

- **S-1 Volatility-regime momentum rotation.** Daily rebalance. Rank the ETF universe by
  blended 20/60/120-day momentum, hold the top 3 with 150-200% gross exposure through
  leveraged ETFs while realized volatility is below its 1-year median, flip to inverse or
  cash when the regime breaks. Hypothesis: trend plus vol gating gives large returns with
  controlled tail risk.
- **S-2 Opening-range breakout.** Intraday on SPY/QQQ/IWM (futures later). Enter on a
  break of the first 15-30 minute range with ATR stops, scale out into strength, flat at
  close. Hypothesis: high-frequency small edges compound into volatile but positive equity.
- **S-3 Cross-sectional short-term reversal.** Top-100 liquid names, buy the biggest 1-3 day
  losers and short the biggest winners, hold 1-3 days, dollar neutral, 200% gross.
- **S-4 Risk overlay module.** Shared vol-targeting and drawdown circuit breaker used by
  every strategy (target 40-60% annualized vol, cut exposure by half after a 15% drawdown,
  flat after 25% until a new high or a manual reset).
- **S-5 Allocator.** Route capital across S-1, S-2, S-3 by trailing 60-day Sharpe with a
  floor per sleeve.
- **D-2 Intraday data (blocks S-2).** `fetch_data.py` writes daily bars only; Yahoo caps
  1-minute history at ~30 days, which is useless for backtesting. S-2 opening-range breakout
  needs minute bars from IBKR (`ib_async`, needs IB Gateway) or a QuantConnect subscription.
  LEAN minute format: `equity/usa/minute/<symbol>/<yyyyMMdd>_trade.zip` holding
  `<yyyyMMdd>_<symbol>_minute_trade.csv` with rows
  `<ms since midnight ET>,o,h,l,c,v`, prices scaled by 10000. Reuse the writer/validator
  structure already in `fetch_data.py`.
- **E-2 Parameter sweeps.** `evaluate.py` compares and promotes but has no sweep. Add
  support for the LEAN Optimizer launcher so parameter sensitivity is measurable rather
  than asserted (the anti-overfitting requirement in AGENTS.md).
- **I-1 IBKR paper pipeline.** Install IB Gateway, write `live/config.paper.template.json`,
  add `scripts/paper_trade.py` that launches LEAN in `live-interactive` paper mode with a
  kill switch and heartbeat log. Requires the human to log in to IB Gateway.

## Done

- **D-1 Data pipeline.** 2026-09-08, run `20260908T162819Z`. `scripts/fetch_data.py` writes
  LEAN daily bars, map files and factor files for 69 symbols (19 ETFs + 50 megacaps),
  1998-01-01 to 2026-09-04. Acceptance algorithm `d1_data_smoke` returns PASS: 15/15 probed
  symbols stream 3690 bars over 2012-2026; factors agree with Yahoo `Adj Close` to 0.003%.
  Minute data deferred to D-2.
- **E-1 Evaluation harness.** `scripts/evaluate.py` compares runs with `champion.json`,
  enforces the min-trades and drawdown rules and promotes only on a pass. Verified on the
  D-1 run, which it correctly refused (14 orders < 30, drawdown 72.7% > 35%). Parameter
  sweeps split out to E-2.
