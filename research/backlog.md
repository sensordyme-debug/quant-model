# Research backlog

Ranked list of hypotheses and infrastructure work. The improvement loop takes the top open
item. Move finished items to the bottom under "Done" with a one-line result and the
experiment timestamp.

## Current objective (set 2026-09-08)

A backtest-validated strategy running on IBKR **paper** trading by **2026-09-10**. That means:
S-1 (with the S-4 risk overlay built in) promoted to champion through `scripts/evaluate.py`,
then I-1 running it against the paper account. Daily-frequency only until D-2 delivers
intraday data. Live money stays off the table until the human signs off in `live/`.

Status 2026-09-08: S-1 is promoted and S-6 has raised it to 1.63x effective exposure and
16.5% vol (CAR 18.1%, Sharpe 0.69, DD 25.2%). The remaining gate is I-1, blocked on IB Gateway
being logged in on this machine (see `research/BLOCKERS.md`); the runner is built and passes
`--mock --dry-run` against the current champion. Realized vol is still short of the 40-60%
mandate, but the binding constraint is now the 35% drawdown limit rather than an execution
bug - a risk-budget decision for the human, not something to fix before the paper deadline.
S-7 has since been run and produced no champion change: the champion's order list is
unchanged (`OrderListHash 9f58b37cc2656b647ec88a5124daf02d`), so nothing about the I-1
deployment moves.

## Open (highest value first)

- **D-3 Point-in-time universe (blocks S-7).** Ranking must only ever see names that were
  liquid *as of the rebalance date*. `signals.MEGACAP_SLEEVE` is the 2026 list and is
  therefore unusable for backtesting (see S-7 below). Cheapest credible version needs no new
  data source: rank the 69 symbols already on disk by trailing 60-day dollar volume
  (close x volume, both in the LEAN daily files) recomputed on each rebalance, take the top
  N, and require a minimum history. Note this is still survivorship-biased at the *file*
  level - `fetch_data.py` only downloaded tickers that exist in 2026 - so also record how
  much room that leaves: the honest fix is delisted-inclusive history, which is a paid data
  set and a human decision. Deliver as a `universe.py` beside `signals.py` so the I-1 runner
  computes membership the same way.
- **S-7 Beat buy-and-hold on absolute return. Partially answered 2026-09-08; blocked on D-3.**
  S-1 compounds at 18.1% against SPY's 15.0% and QQQ's 19.9% - it clears SPY but not QQQ.
  Of the three named candidates, two are now closed on evidence: momentum-proportional
  weighting loses 2.6-2.9 points of CAR on both sub-periods (rejected), and `top_n` is flat
  from 3 to 6 in return while getting cheaper in drawdown (3 kept; 5-6 handed to S-8). The
  third, widening the sleeve, scores CAR 43.9% / Sharpe 1.19 / DD 32.2% in LEAN and passes
  every promotion rule, but it ranks the megacaps of 2026 back to 2012: holding that same
  list equal-weighted with no skill already returns 22.8% at Sharpe 1.27, above the strategy
  itself. Not promoted, tagged `not promotable` in the ledger. Re-open once D-3 lands.
  Remaining untried ideas: a second momentum horizon set per sleeve, and cross-sectional
  ranking against the sleeve median rather than an absolute `min_momentum` floor.
- **I-1 IBKR paper runner: BUILT, waiting on the human's IB Gateway login.**
  `scripts/paper_trade.py` (ib_async) already exists and passes `--mock --dry-run` against
  `algorithms/s1_momo/signals.py`: it introspects the signal signature, feeds back
  `diagnostics["state"]` and an equity curve, sizes whole shares, logs to `live/log/`, and
  refuses to trade without `live/APPROVED_PAPER.md`, a `DU` account, or with `live/HALT`
  present. `scripts/install_paper_task.ps1` schedules 15:45 ET weekdays. Do not rewrite it.
  Remaining work once Gateway is up: `--check`, then a `--dry-run` on the real account, then
  compare the runner's order list with what the LEAN backtest would have done on the same
  date (`results/s1_momo/<ts>/*-order-events.json`). S-6 did not change netting or staging -
  `plan_orders()` already nets against current positions - but it did add the
  `MAX_MARGIN_USED = 1.0` backstop, and the mock plan is now a 1.5x gross book, so the
  paper account must have margin enabled or the first real order will be rejected.
- **S-8 Reach the volatility mandate without breaching the drawdown limit.** After S-6 the
  gross cap no longer binds; `scale_cap = 2.0` and the 25.2% realized drawdown do. Simply
  raising the margin budget to 1.0 buys 2.07x exposure and 20.4% CAR but a 35.4% drawdown,
  which fails the promotion rule - so more size has to be paid for with a better drawdown
  profile, not asked for directly. Candidates: a volatility-responsive budget (spend more of
  it when the vol estimate is low), a trailing stop per holding rather than only at the
  portfolio level, and tightening `dd_halve` so the breaker engages earlier and cheaper.
  **Start from `top_n=5` or `6`** (S-7): return is within 1.5 points of `top_n=3` but full
  drawdown falls to 22.0% and vol to 18.4%, which is exactly the headroom this item needs.
  Requires a human decision if the answer turns out to be "raise the 35% limit".
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

- **E-3 Promotion guard against non-statistical bias.** 2026-09-08. `evaluate.py` refuses to
  promote any run whose ledger tag contains `not promotable`, because every other rule it
  applies is a statistic and no statistic can see a universe chosen with hindsight - S-7's
  wide sleeve passed all of them. Convention: tag a knowingly-compromised run at run time.
- **S-6 Raise S-1's exposure by fixing execution, not the signal.** 2026-09-08, run
  `20260908T182554Z`, promoted to champion. Flat `max_gross_weight = 1.0` replaced by a
  margin budget, `sum(w_i * MARGIN_REQ[i]) <= margin_budget`, with Reg-T 50% for ordinary
  ETFs and 100% for 3x ETFs. Mean effective exposure 1.27x -> 1.63x, CAR 13.7% -> 18.1%,
  Sharpe 0.60 -> 0.69, MaxDD 23.6% -> 25.2%; IS 13.5%/0.64/25.2%, OOS 23.8%/0.76/24.8%.
  Option (b) netting was already in place, and option (a) two-step rotation proved
  unnecessary - zero buying-power rejections, audited margin 0.793 vs a 0.75 budget.
  **The 2x target was measured but not banked:** budget 1.0 gives 2.07x exposure and 20.4%
  CAR but a 35.4% drawdown, over the 35% limit, so the shipped default is 0.75. Raising the
  drawdown limit is a human risk decision; going past 2x on merit is S-8.
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
