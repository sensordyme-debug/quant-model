# Research backlog

Ranked list of hypotheses and infrastructure work. The improvement loop takes the top open
item. Move finished items to the bottom under "Done" with a one-line result and the
experiment timestamp.

## Current objective (set 2026-09-08)

A backtest-validated strategy running on IBKR **paper** trading by **2026-09-10**. That means:
S-1 (with the S-4 risk overlay built in) promoted to champion through `scripts/evaluate.py`,
then I-1 running it against the paper account. Daily-frequency only until D-2 delivers
intraday data. Live money stays off the table until the human signs off in `live/`.

Status 2026-09-09 (latest): **S-12 has promoted a new champion** - the same signal, but the
exposure budget is now split between the three winners by **1/sigma on their own trailing
one-month vol** instead of 1/N: CAR 23.61% -> **24.40%**, Sharpe 0.874 -> **0.921**, drawdown
25.9% -> **25.1%**, PSR 17.7% -> **23.0%**, at 84% more orders and $8.3k more commission. It is
a shelf in both dimensions (vol windows 20/21/30 all win; the tilt is monotone in strength) and
21 sessions is the a-priori one trading month inside it, not the argmax. IS 19.18%/0.884/25.1%
beats S-10 on all three; OOS 30.86%/0.985/22.6% wins on Sharpe and is flat on CAR, so the gain
is an in-sample-half gain. New order list
**`OrderListHash 5246804e17a67af90028ffceead7d3b3`**, and I-1's pre-deploy comparison must be
made against that hash, not `ff4a7cbaaf6e36e58ace2b82ab216bdf`. Ports 4002 and 7497 were checked
again at the top of this iteration and are both still closed, so I-1/D-2/S-2 remain blocked.
**With the allocation step now spent, this sleeve has no cheap levers left**: what remains
inside a three-name ETF book needs breadth (correlation-aware weights want more than nine
names), so the next real gains are still S-2 and D-2 behind the Gateway login.

Status 2026-09-08: **S-11 closed negatively - the champion stood at S-10.** Every
whipsaw control (hysteresis, minimum holding period, rank persistence) trades return for
drawdown roughly in proportion, so the champion's turnover is *paid for*: its rotation is
signal, not noise. What the iteration does leave behind is a priced frontier - `min_hold=10`
plus `margin_budget=0.85` earns 25.07% CAR at 25.7% drawdown (champion 23.61% at 25.9%) for
0.013 of Sharpe - which is now a one-line question to the human in `BLOCKERS.md`. Signal work
that adds return without adding turnover has therefore run out of cheap moves on this sleeve;
the next real gains are a second uncorrelated sleeve (S-2/S-5) and intraday data (D-2), and
both of those, like I-1, wait on the IB Gateway login.

Status 2026-09-08: **S-10 has promoted a new champion** - S-9 with the 120- and 252-day
momentum windows ending one trading week before the decision bar: CAR 20.9% -> **23.6%**,
Sharpe 0.78 -> **0.87**, drawdown 28.9% -> **25.9%**, at 10% fewer orders, beating the old
champion on both sub-periods. New order list:
**`OrderListHash ff4a7cbaaf6e36e58ace2b82ab216bdf`**, and I-1's pre-deploy comparison must now
be made against that hash, not `b763e292cb0eb9a2c81af5739188d437`. The remaining gate is still
I-1, blocked on IB Gateway being logged in on this machine (see `research/BLOCKERS.md`); the
runner is built and re-verified `--mock --dry-run` against the new signal.

Three constraints stay measured rather than assumed: single-name sleeves are capped because the
pool on disk is a 2026 survivor list, leaving the ETF-9 sleeve as the only honest universe here
(S-7, D-3); the 40-60% volatility mandate is **unreachable** under the 35% drawdown limit on
that sleeve, at any size, by any of the four levers S-8 tried; and a daily-turnover book on this
$100k account pays ~2.1bps per unit of turnover in commission alone, which is more than the
whole gross edge S-3 could find. The first two are decisions for the human in `BLOCKERS.md`.
S-9 and S-10 are the only results to move the champion *without* spending more turnover, which
is the only kind of gain that cost floor cannot tax away - so signal work, not sizing work, is
where the next iteration should look too.

One methodology change, from S-10: **`sweep_s1.py` and LEAN now disagree in sign**, not only in
magnitude - the sweep rejected the skip lever that LEAN promoted, and inverted its drawdown
ranking. A sweep rejection is therefore grounds for one LEAN confirmation run, not for closing
an idea; the sweep is a cheap generator of candidates, and only LEAN decides.

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
  Re-verified `--mock --dry-run` against the **S-12** champion on 2026-09-09 (1.23x gross,
  margin 0.75, XLE/XLK/TQQQ, with the new `alloc_vols` tilt visible in the diagnostics); the
  pre-deploy comparison is against `OrderListHash 5246804e17a67af90028ffceead7d3b3`.
- **D-2 Intraday data (blocks S-2).** `fetch_data.py` writes daily bars only; Yahoo caps
  1-minute history at ~30 days, which is useless for backtesting. Once IB Gateway is logged
  in, pull minute bars with `ib_async` `reqHistoricalData` (1-day chunks, respect pacing
  limits) for SPY/QQQ/IWM/TQQQ/SQQQ first. LEAN minute format:
  `equity/usa/minute/<symbol>/<yyyyMMdd>_trade.zip` holding
  `<yyyyMMdd>_<symbol>_minute_trade.csv` with rows `<ms since midnight ET>,o,h,l,c,v`,
  prices scaled by 10000. Reuse the writer/validator structure already in `fetch_data.py`.
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

- **S-12 Risk parity inside the top_n. PROMOTED 2026-09-09**, run `20260909T042431Z` (control
  `20260909T034600Z`, reproducing `ff4a7cbaaf6e36e58ace2b82ab216bdf`; window scan
  `20260909T034953Z` / `035356Z` / `035803Z` / `040157Z` / `040554Z` / `041013Z`; tilt-strength
  check `20260909T041912Z`; sub-periods `20260909T041413Z` / `041644Z`). Momentum still picks
  the three names; their share of the exposure budget is now `(1/sigma) ** alloc_vol_power` on
  the **unlevered** ranked series rather than 1/N, because equal weight equalizes notional and
  this sleeve spans 12% vol (GLD/TLT) to 30% (XLE/XLK). Shipped: `weight_mode="invvol"`,
  `alloc_vol_window=21`, `alloc_vol_power=1.0`; `S1_WEIGHT_MODE=equal` restores S-10.
  LEAN full period CAR 23.61% -> 24.40%, Sharpe 0.874 -> 0.921, drawdown 25.9% -> 25.1%,
  PSR 17.7% -> 23.0%; IS 19.18%/0.884/25.1% (beats 17.64%/0.801/25.9% on all three), OOS
  30.86%/0.985/22.6% (Sharpe ahead of 0.972, CAR 0.23 points behind). **Shelf in both
  dimensions**: windows 20/21/30 beat the champion on CAR, Sharpe and drawdown, 40/60 win on
  Sharpe and drawdown only, 10 loses; and the tilt is monotone in strength (power 0.5 gives
  24.10%/0.902, half the gain). 21 = one trading month is the a-priori point, 20 is the argmax.
  **The cost is turnover**: 2,573 -> 4,735 orders and $37.4k -> $45.7k of fees, because vol
  ratios drift and the book re-weights between rotations - so window 30 (4,102 orders) is the
  named fallback if commission ever rises. `weight_mode="rank"`, still never LEAN-tested, loses
  in the sweep (19.3%/0.93 against 21.2%/1.03) and was not carried forward.
- **S-11 The whipsaw. Closed negatively 2026-09-08**, runs `20260909T024906Z` (control,
  reproduces `OrderListHash ff4a7cbaaf6e36e58ace2b82ab216bdf`), `20260909T025256Z` /
  `025647Z` / `030039Z` (hysteresis 0.05/0.10/0.20 sigma), `20260909T030434Z` (min_hold=10),
  `20260909T030824Z` (rank_persist=2), `20260909T031243Z` and `20260909T032059Z` (the two
  size-spend frontier points), `20260909T031632Z` / `031842Z` (sub-periods). No promotion.
  All three levers shipped in `signals.py` defaulted off (`hysteresis`, `min_hold`,
  `rank_persist`; env `S1_HYSTERESIS`, `S1_MIN_HOLD`, `S1_RANK_PERSIST`), plus
  `sweep_s1.py --mode s11`. **The core finding is that the champion's rotation is not
  noise**: refusing a rank crossing removes return monotonically in the strength of the
  refusal (hysteresis 0.05 -> 0.20 sigma walks CAR 23.57% -> 22.34% and Sharpe 0.873 ->
  0.827), so the frontier slides along rather than moving up. It is however a *cheap* trade
  in drawdown: `min_hold=10` costs 0.45 points of CAR and buys 3.1 points of drawdown and
  $10k of fees; hysteresis 0.05 costs 0.04 points of CAR (a rounding error) for 1.3 points of
  drawdown, 373 fewer orders and $7.8k less commission, and its sub-periods put the whole
  gain in the IS half where S-10 diagnosed the whipsaw (IS 17.73%/0.806/24.6% beats the
  champion's 17.64%/0.801/25.9% on all three; OOS is a hair behind). Spending the headroom on
  size does not recover the return - `min_hold=10` + `margin_budget=0.85` reaches 25.07% CAR
  at a matched 25.7% drawdown but 0.861 Sharpe, refused by `evaluate.py` on the Sharpe rule
  and now a named question for the human in `BLOCKERS.md`. `rank_persist` is the one lever
  both harnesses reject outright: blocking an entry parks the book in cash and buys it back,
  so it *raises* turnover (2,727 orders, $46k fees against 2,573 and $37k). Implementation
  note for I-1: (a) and (b) persist `held`/`held_age` in the existing `state` dict the runner
  already round-trips; (c) is stateless by construction.
- **S-10 Skip-a-month momentum and horizon weighting. PROMOTED 2026-09-08**, run
  `20260909T013820Z` (control `20260909T005513Z`, sub-periods `20260909T013359Z` /
  `20260909T013608Z`, LEAN skip scan `20260909T0059-0122`). Two levers, both defaulted off,
  the control reproducing S-9's `OrderListHash b763e292cb0eb9a2c81af5739188d437`.
  **Horizon weighting lost everywhere** - every vector overweighting the long horizon costs
  2-3 points of CAR and widens drawdown, on the raw blend and after standardizing
  (`mom_weights` stays in `signals.py`, defaulted empty). **The skip won, but not at the
  textbook parameter**: the 12-2 month skip (20 sessions) loses (19.6% / 0.72), the shelf is
  at 3-10 sessions (23.0-23.6% CAR, 0.84-0.87 Sharpe), and it collapses at 2 and at 15+.
  Shipped: `mom_skip=5` (one trading week) on `mom_skip_min_lookback=120`, i.e. the 120- and
  252-day horizons only - applying it to the 20-day horizon as well costs 4.4 points of CAR,
  and confining it to 252 alone earns 23.3%, so the effect belongs to long-horizon momentum
  generally. LEAN full period: CAR 20.9% -> 23.6%, Sharpe 0.782 -> 0.874, drawdown 28.9% ->
  25.9%, orders 2,870 -> 2,573, PSR 10.1% -> 17.7%; IS 17.6%/0.80/25.9%, OOS 31.1%/0.97/21.5%,
  both ahead of S-9's 15.2%/0.70 and 28.0%/0.88. **The methodology finding matters as much as
  the result**: `sweep_s1.py` rejected this cell and inverted its drawdown ranking, so the two
  harnesses disagree in sign and LEAN decides. Also delivered the S-9(c) diagnostic that
  became S-11.
- **S-9 A second signal on the ETF sleeve. PROMOTED 2026-09-08**, run `20260908T235647Z`
  (control `20260908T234444Z`, sub-periods `20260908T235224Z` / `20260908T235437Z`). Both
  ideas S-7 named were tested and **both lost**: cross-sectional ranking against the sleeve
  median is a *looser* gate than the absolute floor at `top_n=3` of nine (17.9% CAR) and
  asking for real dispersion strands the book in cash through 2012-2019 (6.4% CAR, 49.2%
  drawdown); horizon agreement (`mom_confirm`) costs 6 points of CAR and 14 of drawdown at
  55% more turnover. Risk-adjusted momentum (`mom_score="riskadj"`) beats the champion only
  in a 15-30 day vol window, wins IS at one end and OOS at the other, and is not shipped.
  **What won was a fourth momentum horizon of 252 sessions**: LEAN CAR 18.1% -> 20.9%,
  Sharpe 0.693 -> 0.782, orders 3,410 -> 2,870, fees $38.6k -> $37.3k, drawdown 25.2% ->
  28.9%; IS 15.2%/0.70, OOS 28.0%/0.88, both ahead of the old champion's 13.5%/0.64 and
  23.8%/0.76. It is a **shelf, not a spike** - every fourth horizon from 220 to 300 beats
  the champion on CAR, Sharpe and drawdown, collapsing at 150 and 320 - and 252 is shipped
  as the a-priori one trading year rather than the 250 argmax. Also fixed a harness bug the
  scan exposed: a lookback longer than `history_bars` made `target_weights` hold cash for
  the whole sample and print a plausible 0.0% CAR, so `Params.__post_init__` now widens the
  window to `max(lookback) + 50`. Recalibration: the sweep understated LEAN drawdown by 7.8
  points on this configuration, against the +2 S-8 measured at the champion's size.
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
