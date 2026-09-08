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
`--mock --dry-run` against the current champion. S-7, D-3 and now S-8 have all been run and
all closed negatively, so the champion has not moved and its order list is unchanged
(`OrderListHash 9f58b37cc2656b647ec88a5124daf02d`, re-verified by run `20260908T213829Z`) -
nothing about the I-1 deployment moves. S-3 has now also been run and closed negatively, so
the champion's order list is still unchanged (`OrderListHash 9f58b37cc2656b647ec88a5124daf02d`).
Three constraints are now measured rather than assumed: single-name sleeves are capped because
the pool on disk is a 2026 survivor list, leaving the ETF-9 sleeve as the only honest universe
here; the 40-60% volatility mandate is **unreachable** under the 35% drawdown limit on that
sleeve, at any size, by any of the four levers S-8 tried; and a daily-turnover book on this
$100k account pays ~2.1bps per unit of turnover in commission alone, which is more than the
whole gross edge S-3 could find. The first two are decisions for the human in `BLOCKERS.md`.
With S-3 closed and S-2 blocked on data, the only unblocked strategy work is a *different
signal on the ETF sleeve* (S-9).

## Open (highest value first)

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
- **D-2 Intraday data (blocks S-2).** `fetch_data.py` writes daily bars only; Yahoo caps
  1-minute history at ~30 days, which is useless for backtesting. Once IB Gateway is logged
  in, pull minute bars with `ib_async` `reqHistoricalData` (1-day chunks, respect pacing
  limits) for SPY/QQQ/IWM/TQQQ/SQQQ first. LEAN minute format:
  `equity/usa/minute/<symbol>/<yyyyMMdd>_trade.zip` holding
  `<yyyyMMdd>_<symbol>_minute_trade.csv` with rows `<ms since midnight ET>,o,h,l,c,v`,
  prices scaled by 10000. Reuse the writer/validator structure already in `fetch_data.py`.
- **S-9 A second signal on the ETF sleeve (new, the only unblocked strategy work).**
  Everything since S-6 has changed *size* or *universe* and none of it moved the champion;
  S-7 named the two untried signal ideas and they are still untried: a second momentum
  horizon scored per sleeve member, and cross-sectional ranking against the sleeve median
  instead of the absolute `min_momentum` floor. Daily bars on the honest ETF-9 sleeve, so
  it needs no new data and carries no survivorship caveat. Judge it against the champion's
  18.1% / 0.69 / 25.2%, and heed the S-3 cost lesson: at this account size a daily-turnover
  book pays ~2.1bps per unit of turnover in commission alone.
- **S-2 Opening-range breakout.** Intraday on SPY/QQQ/IWM (futures later). Enter on a
  break of the first 15-30 minute range with ATR stops, scale out into strength, flat at
  close. Hypothesis: high-frequency small edges compound into volatile but positive equity.
  **Blocked on D-2**, which is blocked on the IB Gateway login.
- **S-5 Allocator.** Route capital across S-1, S-2 and any future sleeve by trailing 60-day
  Sharpe with a floor per sleeve. Still worth building - S-3 proved the market-neutral
  construction really does deliver orthogonality (corr -0.03 with the champion) - but it
  has nothing to allocate *to* until a second sleeve has a positive expected return, so it
  sits behind S-2.

## Done

- **S-3 Cross-sectional short-term reversal. Closed negatively 2026-09-08**, runs
  `20260908T223450Z` (2012-2013 plumbing smoke) and `20260908T224519Z` (full period), no
  promotion. `algorithms/s3_reversal/` (signals + LEAN plumbing, importing S-1's drawdown
  overlay and margin table rather than copying them) and `scripts/sweep_s3.py`. The sleeve
  is dollar-neutral as designed - beta 0.07, mean |net| 0.0000 at decision time - and its
  correlation with the champion is **-0.026**, which was the point of running it. But there
  is no return to allocate: **at zero trading cost**, 24 of 30 parameter cells score a
  negative Sharpe and the best reaches only 0.27, all of it in-sample (IS Sharpe 0.64, OOS
  -0.01) in a cell chosen with hindsight over the whole sample. Inverting the sign to
  short-term continuation is not an edge either. LEAN on the best cell: CAR -0.14%, Sharpe
  -0.19, MaxDD 48.6%, 44,353 orders, **$64,721 of commission on a $100k account** - 2.1bps
  per unit of turnover, commission only, before any spread. Two durable numbers came out of
  it: that 2.1bps cost floor for any daily-turnover book at this account size, and the
  confirmation that a market-neutral sleeve is genuinely orthogonal to the champion, which
  keeps S-5 alive. The survivorship caveat on the megacap pool did not need resolving - the
  result is negative even with the bias working in its favour.
- **S-8 Reach the volatility mandate without breaching the drawdown limit. Closed negatively
  2026-09-08**, runs `20260908T213829Z` (control), `20260908T214218Z`, `20260908T214625Z`, no
  promotion. All four named levers measured and rejected: `top_n=5-6` inverts at higher size
  (S-7's headroom was a small-book property); an earlier breaker (`dd_halve` 0.08-0.10) is
  strictly dominated by carrying less size; a continuous `dd_mode="taper"` re-creates the 2015
  absorbing state and returns -0.2% CAR, because the high-water mark only resets on a *hard*
  `dd_flat` breach; and a per-holding trailing stop leaves `MaxDD` bit-identical, since the
  drawdown comes from the levered index proxies falling together. The elastic vol-responsive
  budget (`margin_budget_cap`/`_floor`) did expose a real defect - the shipped vol target is
  *saturated*, so the champion has never actually vol-targeted, it carries constant margin -
  but fixing it is a size dial, not a shape improvement: at matched 17.1% vol it loses 1.8
  points of CAR and 0.09 Sharpe to the champion while placing 30% more orders. All three
  parameters remain in `signals.py` defaulted off; the control run reproduces
  `OrderListHash 9f58b37cc2656b647ec88a5124daf02d`. **The mandate itself is now a human
  decision** - the LEAN frontier has drawdown binding at 19-20% vol, so 40-60% is unreachable
  under a 35% limit (see `BLOCKERS.md`). Also calibrated: `sweep_s1.py` understates drawdown
  by +2 points at the champion's size and by +8 to +10 at 2x exposure, so sweeps rank, LEAN
  decides.
- **D-3 Point-in-time universe.** 2026-09-08, run `20260908T203212Z`, no promotion.
  `algorithms/s1_momo/universe.py` picks the top N of a candidate pool by trailing 60-day
  median dollar volume on each rebalance, with a 252-session minimum history;
  `Params.universe_size=0` keeps the champion's fixed sleeve, so the default is unchanged
  (control run `20260908T202809Z` reproduces the champion's OrderListHash). Membership is
  genuinely dynamic - 47 names selected across the sample, 458 entries/exits, 2012 holds
  BAC/GE/XOM/WFC/IBM and 2026 holds NVDA/TSLA/AMD - and the strategy on it scores CAR 32.1% /
  Sharpe 0.90 / DD 32.3%, beating the champion and QQQ. **It is still not promotable**, for two
  measured reasons: point-in-time selection removes only 0.8 of the 7.8 points by which the
  megacap basket beats SPY (the other 7.0 are the survivor pool on disk), and the strategy
  gives up 0.19 of Sharpe against simply holding the same 20 names. Filed as a paid-data
  decision in `BLOCKERS.md`.
- **S-7 Beat buy-and-hold on absolute return. Closed negatively 2026-09-08.** S-1 compounds at
  18.1% against SPY's 15.0% and QQQ's 19.9%. All three named levers are answered:
  momentum-proportional weighting loses 2.6-2.9 points of CAR on both sub-periods; `top_n` is
  flat from 3 to 6 in return while getting cheaper in drawdown (3 kept, 5-6 handed to S-8);
  and the wide sleeve beats QQQ only because it is levered and drawn from a survivor pool -
  under D-3's point-in-time membership it still loses to its own basket on Sharpe. Beating
  buy-and-hold on absolute return is therefore not a universe problem, and the untried ideas
  (a second momentum horizon per sleeve, cross-sectional ranking against the sleeve median
  instead of an absolute `min_momentum` floor) belong to whatever replaces the S-1 signal.
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
