# Research backlog

Ranked list of hypotheses and infrastructure work. The improvement loop takes the top open
item. Move finished items to the bottom under "Done" with a one-line result and the
experiment timestamp.

## Current objective (set 2026-09-08)

A backtest-validated strategy running on IBKR **paper** trading by **2026-09-10**. That means:
S-1 (with the S-4 risk overlay built in) promoted to champion through `scripts/evaluate.py`,
then I-1 running it against the paper account. Daily-frequency only until D-2 delivers
intraday data. Live money stays off the table until the human signs off in `live/`.

Status 2026-09-09 14:0x UTC (latest, I-1 iteration): **the pre-deploy gate is built, and it
caught a real bug in the runner.** Gateway is up but the API is still refused by 10141, so
instead of a sleeve experiment this iteration finished I-1's last unbuilt piece:
`scripts/compare_orders.py`, which walks LEAN's own bars and hands *identical* inputs to
`main.py:submit_targets` and `paper_trade.py:plan_orders`, diffing the two order lists. Any
difference is therefore execution-layer by construction, not data or signal. **It failed on
first run**: the runner banded orders at a flat `MIN_NOTIONAL = $200` while the backtest bands
at `0.01 x equity` ($1,000 at $100k, $24,000 by the end of the sample), so the runner would
have placed **9,196 orders against the backtest's 4,653** and agreed on only **36.6%** of
decision dates - all 4,543 divergences the same shape, the runner sending small drift
adjustments LEAN bands out. These are exactly the orders S-13 measured as return-neutral, so
the paper account was about to pay a spread on ~4,500 orders with no return in them and
underperform its own backtest for a reason nothing would have surfaced. Fixed
(`max(MIN_NOTIONAL, MIN_ORDER_VALUE * net_liq)`, `MIN_ORDER_VALUE = 0.01` tracking `main.py`);
the gate now passes **3,689 / 3,689 dates with identical order counts**, and fails with exit 1
on a deliberately mismatched band, so it discriminates. **Nothing under `algorithms/` was
touched**, so `OrderListHash 5246804e17a67af90028ffceead7d3b3` stands unchanged and no
rebaselining run was needed. Champion unchanged at S-12.

Status 2026-09-09 13:40 UTC (daily review, no experiments run): **the Gateway blocker moved,
and it is now one dialog box.** Port 4002 is open and answering for the first time - Gateway is
running and logged in - but the API handshake is refused with `Error 10141: Paper trading
disclaimer must first be accepted for API connection`. That is a one-time tick-box inside
Gateway (Configure -> Settings -> API -> Settings), not work on this side, and it is the only
thing between the repo and tomorrow's deadline. Re-probe with `paper_trade.py --check` at the
top of every iteration; the moment it clears, **I-1 is the top item and everything else waits**,
with D-2 immediately behind it on the same connection. Full review in
`research/reports/2026-09-09.md`. If the API stays blocked, do **not** hunt for another lever on
the ETF-9 sleeve - S-11 and S-13 measured that there are none left cheaply; the useful offline
work is S-5 harness scaffolding and generalizing `sweep_s1.py` off S-1 (E-2's deferred half).

Status 2026-09-09: **S-13 closed negatively - the champion stands at S-12.** The
execution no-trade band (`min_order_value`, pinned at 0.01 since S-1 and never swept) was
tested at 0.015/0.02/0.03/0.05/0.08 to win back the commission S-12 spent. It cannot be won
back, because **there is nothing to win**: the response is non-monotone and flat, with CAR
walking 24.40 -> 24.35 -> 24.54 -> 24.34 -> 23.92 -> 24.47 across a factor of eight in the
band and a factor of 2.7 in order count. The 0.02 cell beats the champion and `evaluate.py`
says **BEATS champion**, and it was **refused** on the shelf-not-spike rule - both its
neighbours lose, so its +0.14 CAR is inside the region's own scatter. Nothing shipped;
`OrderListHash 5246804e17a67af90028ffceead7d3b3` is unchanged and I-1 needs no rebaselining.
The durable finding is the flatness: **~3,000 of the champion's 4,735 orders (63%) are
return-neutral**, free to remove in backtest and strictly *better* to remove live, where the
unmodelled spread is paid per order. That is a live-execution decision and is now a one-line
question in `BLOCKERS.md`. Ports 4002 and 7497 checked again at the top of this iteration:
both still closed.

Status 2026-09-09: **S-12 has promoted a new champion** - the same signal, but the
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

Owner decisions of 2026-09-09 (see `BLOCKERS.md`): paper trading is approved and running,
the 35% drawdown cap stays, promotion is now return-first with a 0.03 Sharpe tolerance and a
1-point drawdown tolerance, delisted-inclusive data is deferred, the no-trade band stays 0.01.
Priority is therefore the **intraday active sleeve (A-track)**: volatility is to be earned with
a second, uncorrelated intraday sleeve, not by leverage on the ETF sleeve. IB Gateway is up.

Owner instruction 2026-09-09 (afternoon): by the 2026-09-10 open the paper account must run a
volatile, active, high-turnover book on most of the capital. The infrastructure for that now
exists (see AGENTS.md "The intraday active sleeve"): 16-name disjoint universe, IBKR minute
store, causal features, three strategies, a minute backtester, and a live trader with replay,
scheduled 09:25 ET. **The loop's job from here is signal quality**: the first honest numbers
(2 names, 62 sessions) were ORB +10% annualized / Sharpe 2.5, VWAP-trend -12% after costs,
late-day momentum flat. Every A-track iteration: pick one strategy, change one thing, run
`scripts/intraday_backtest.py --split <date>` on the full universe, keep it only if OOS
improves after costs, journal it, and update `live/intraday_config.json` only per AGENTS.md rule (c).

- **A-1 Make the VWAP-trend engine pay for its turnover.** It is the turnover engine (21
  trades/day on two names) and loses ~12%/yr after $400/day of costs on 2 names. Candidates,
  one per iteration: wider entry band (20-30 bps) with a minimum hold (10-15 bars); only trade
  in the direction of the session's trend (`day_ret` sign, or price on the same side of VWAP
  for 30+ bars); skip 11:30-14:00; require range expansion (`atr14` above its session median);
  evaluate on 5-minute aggregates instead of 1-minute closes. Judge on OOS Sharpe and P&L per
  trade after costs, not on trade count.
- **A-2 Strengthen ORB, the only sub-strategy with positive evidence.** 30-minute range
  variant, ATR-based stop instead of the midpoint, scale-out at 1.5R, volume filter sweep
  (1.0-2.0x), entry window sweep. Check that it survives on the leveraged ETFs (SOXL/SOXS)
  where the range is wider.
- **A-3 Deployed mix.** Set `alloc` and `gross` in `live/intraday_config.json` from OOS
  evidence: strategies with negative OOS after costs get alloc 0 until fixed. Target gross
  1.0-1.5x of NAV so daily P&L swings are in the tens of thousands on the $1M account, with the
  framework's 2.5% daily loss limit as the floor.
- **A-4 Extend the minute store** to 9-12 months (`python scripts/intraday_data.py --months 12`,
  paced, resumable) so IS/OOS splits have enough sessions; then re-run A-1/A-2 conclusions.
- **A-5 Execution quality from the live log.** After each session compare
  `live/log/intraday-<date>.jsonl` fills against the replay of the same day: slippage per
  order, fill rate, latency. Feed the measured slippage back into `SLIPPAGE_BPS` if it differs.
- **D-2 Intraday data (unblocked 2026-09-09; LEAN-format part, for LEAN-based S-2 work).** `fetch_data.py` writes daily bars
  only; Yahoo caps 1-minute history at ~30 days. Pull minute bars with `ib_async`
  `reqHistoricalData` (`barSizeSetting="1 min"`, `whatToShow="TRADES"`, `useRTH=True`,
  1-day chunks, respect IBKR pacing of ~60 requests per 10 minutes) for SPY/QQQ/IWM/TQQQ/SQQQ
  first, as far back as IBKR serves. LEAN minute format:
  `equity/usa/minute/<symbol>/<yyyyMMdd>_trade.zip` holding
  `<yyyyMMdd>_<symbol>_minute_trade.csv` with rows `<ms since midnight ET>,o,h,l,c,v`,
  prices scaled by 10000. Reuse the writer/validator structure already in `fetch_data.py`.
  Use a distinct `clientId` (e.g. 31) so it never collides with the paper runner's 17.
- **S-2 Opening-range breakout.** Intraday on SPY/QQQ/IWM (futures later). Enter on a
  break of the first 15-30 minute range with ATR stops, scale out into strength, flat at
  close. Hypothesis: high-frequency small edges compound into volatile but positive equity.
  Needs D-2. Judge with the same IS/OOS split and the promotion rules; it is a *second sleeve*,
  so record its correlation with the champion's daily returns as a first-class metric.
- **S-5 Allocator.** Route capital across S-1, S-2 and any future sleeve by trailing 60-day
  Sharpe with a floor per sleeve. Scaffold now against the S-1 and S-3 return series.
- **I-1 IBKR paper runner: DONE 2026-09-09, paper trading approved and scheduled.**
  `scripts/paper_trade.py` (ib_async) already exists and passes `--mock --dry-run` against
  `algorithms/s1_momo/signals.py`: it introspects the signal signature, feeds back
  `diagnostics["state"]` and an equity curve, sizes whole shares, logs to `live/log/`, and
  refuses to trade without `live/APPROVED_PAPER.md`, a `DU` account, or with `live/HALT`
  present. `scripts/install_paper_task.ps1` schedules 15:45 ET weekdays. Do not rewrite it.
  Remaining work once the 10141 disclaimer is accepted, in order: `--check`, then a
  `--dry-run` on the real account, then `py -3.11 scripts/compare_orders.py`. **That last
  step is now automated and already passing** - it was the manual "compare the runner's order
  list with what the backtest would have done" item, and building it on 2026-09-09 caught the
  `MIN_NOTIONAL` band bug that would have doubled the paper account's order count (see the
  journal). It needs no IB connection, so re-run it after any change to `plan_orders`,
  `submit_targets` or `min_order_value`; exit 1 means the runner and the backtest have
  drifted apart and the deploy should stop. S-6 did not change netting or staging -
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
  sits behind S-2. **Its plumbing is the designated offline work** if the API stays blocked:
  it can be scaffolded and tested against the existing S-1 and S-3 return series without
  touching the champion.
- **E-2b Generalize `sweep_s1.py` off S-1.** Explicitly deferred when E-2 shipped; the second
  designated offline item. Needed before any second sleeve can be swept the same way.

## Done

- **S-13 The execution no-trade band. Closed negatively 2026-09-09**, runs
  `20260909T043527Z` (0.02), `045041Z` (0.015), `044105Z` (0.03), `044610Z` (0.05),
  `045910Z` (0.08), sub-periods `20260909T045454Z` / `045705Z`; the champion run
  `20260909T042431Z` is the 0.01 cell, so no control was needed and **no code changed** -
  `min_order_value` was already wired to `S1_MIN_ORDER_VALUE`. Full period: 0.01 24.40%/0.921/
  25.1%/4,735 orders, 0.015 24.35%/0.919/26.9%/3,887, 0.02 24.54%/0.927/25.2%/3,355,
  0.03 24.34%/0.917/25.5%/2,737, 0.05 23.92%/0.900/29.2%/2,112, 0.08 24.47%/0.920/25.4%/1,727.
  **Non-monotone and flat** - no trend in either direction across a factor of eight in the
  band, and the one deviant cell (0.05, drawdown 29.2%, four points wide of every neighbour)
  deviates in a metric no mechanism predicts, which is what path dependence looks like when a
  threshold moves *which day* a rebalance fires. 0.02 passes `evaluate.py` outright (and its
  sub-periods agree in sign: IS 19.32%/0.891/25.2% vs 19.18%/0.884/25.1%, OOS 30.98%/0.988/
  22.7% vs 30.86%/0.985/22.6%) and was **refused as a spike** - both neighbours lose to the
  champion, so there is no shelf and the +0.14 CAR sits inside the region's scatter. **The
  finding is the flatness**: ~3,000 of the champion's orders are return-neutral, worth only
  the $6.1k of commission the widest band saves in backtest, but worth that *plus* an
  unmodelled spread per order live. Filed as a live-execution question in `BLOCKERS.md`;
  the shipped default stays 0.01 precisely so the I-1 order list does not move.
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
