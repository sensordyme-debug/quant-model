# Blockers needing the human

Items the agent cannot resolve alone. Remove an item when it is resolved and note the date.

## Open ops item for the human (2026-09-11, live alerting is dead)

- **Every alert the paper stack raised on 2026-09-10 was dropped.** The intraday log carries
  `notify_failed: no live/alerts.json` fifteen times and the daily log once, so a loss-limit halt,
  a connection failure or a flatten error is currently invisible outside the log files. Both
  runners read `live/alerts.json` (`{"channel": ..., "target": ...}`, see `paper_trade.py:36` and
  `intraday_common.py:238`) and push through OpenClaw's chat channel, which also needs the bot
  credential named in `live/secrets.env`.
- **Why the loop will not fix it.** It is a credential and an external-messaging channel: writing
  either is outside the agent's red lines, and the target chat id is yours. Configure the channel
  on the OpenClaw side and drop the `{"channel", "target"}` pair into `live/alerts.json`; nothing
  in the repo needs to change, and the next session's log will show `notify_ok` instead. Until
  then, treat `live/log/intraday-<date>.jsonl` as the only alert surface.

## Open question to the owner (2026-09-10, daily champion - risk posture, from O-1b)

- **The daily champion's gross is one constant away from ~1.6 points more CAR, and moving it is
  your call, not the loop's.** O-1b tried to buy that size with an options-implied dial and refused
  it - and in doing so measured that the size is available for free. All rows are LEAN runs over
  **2017-04-03..2026-09-04**, the window the options store covers:

  | cell | orders | fees | CAR | Sharpe | MaxDD | ann.std |
  | --- | --- | --- | --- | --- | --- | --- |
  | shipped champion | 2,951 | $13,090 | 29.456% | 1.025 | **22.6%** | 0.179 |
  | `margin_budget` 0.75 -> **0.792** | 3,039 | $14,530 | **31.006%** | 1.042 | **22.8%** | 0.188 |
  | the options-implied dial (refused) | 4,550 | $17,963 | 31.376% | 1.050 | 23.3% | 0.189 |

  **One constant buys +1.55 points of CAR for +0.2 points of drawdown and 88 extra orders.** The
  dial buys another +0.37 for +0.5 points of drawdown and **1,511** extra orders, which is why it
  was refused. No new data feed is involved in the middle row.
- **Why it is a question and not a change.** The 0.25 buffer under Reg-T is a deliberate risk
  choice, not a fitted parameter (see the `signals.py` docstring): a live account holding at the
  full budget has *zero* excess liquidity, so any adverse move is an immediate margin call. The
  measured window above starts in 2017 and misses 2012-2016; the full-period champion's drawdown is
  already 25.1% against your 35% cap, and a wider budget widens it - S-6 measured a *full* 1.0
  budget at 35.4% drawdown, over the cap, which is where this road ends. Three options:
  **(a)** leave `margin_budget` at 0.75 (default, nothing changes); **(b)** move it to 0.792, which
  the loop would then confirm on the full 2012-2026 sample through `evaluate.py` before promoting;
  **(c)** name a drawdown you are willing to carry and let the loop solve for the budget under it.
  Nothing has been changed pending your answer, and this is a size decision, so the loop will not
  take it on its own.
- **S-15 evidence added 2026-09-11: this question is now the highest-value lever left on the daily
  sleeve, and a second risk-posture dial sits beside it.** The attribution run (full period,
  `scripts/sweep_s15.py`) shows the vol target plus the margin budget produce **71% of the
  champion's return** - the nine ETFs held equal-weighted and unlevered, with no ranking and no
  regime filter, earn **17.282% CAR** against the shipped 24.404%, and the entire signal stack is
  worth +7.12 CAR at t = 1.37. Every signal lever the loop can still pull is smaller than the
  scatter on this constant.
- **The second dial is the 3x proxies.** Holding the same signal in the unlevered parents instead
  of UPRO/TQQQ/TMF gives **23.128% CAR at Sharpe 0.950, drawdown 23.6%, std 0.153, PSR 27.4% and
  $25,646 of fees** against the champion's 24.404% / 0.921 / 25.1% / 0.170 / 23.0% / $45,695 -
  **better on every risk-adjusted measure and on cost, for 1.28 points of CAR.** So the leveraged
  sleeve is not buying edge, it is buying volatility (the same thing L-1 found intraday), and
  whether to keep paying for it is the same kind of decision as the budget above. The loop has
  changed nothing; `S1_PROXY=off` exists only as a research override and defaults to the champion.

## Open request to the owner (2026-09-10, intraday sleeve - supersedes the size half of the 2026-09-09 item)

- **The question "can this sleeve be validated?" is now answered, and the answer is that it
  loses money. Decide whether it keeps trading paper capital at all.** A-4 said ~2,120 sessions
  were needed and that we would never have them. We do: `scripts/alpaca_data.py` holds
  split-adjusted SIP 1-minute bars for the same 16 names back to 2016-01-04 - **2,686 sessions**,
  free, and the per-share commission model has been corrected for the split adjustment (the raw
  IBKR store is unaffected; A-5's control reproduces to the digit). On that sample, with the
  shipped costs and the deployed framework:

  | | sessions | $/day | t |
  | --- | --- | --- | --- |
  | mix, 2016-2019 | 1,006 | -579 | -2.42 |
  | mix, 2020-2023 | 1,006 | -1,127 | -2.92 |
  | mix, 2024-2026 | 674 | -231 | -0.37 |
  | **mix, all** | **2,686** | **-697** | **-3.01** |
  | ORB alone, all | 2,686 | -289 | -1.17 |
  | late-day fade alone, all | 2,686 | -468 | **-7.38** |
  | mix, the window it was fitted on | 261 | +302 | +0.32 |

  The last row is the point: the only profitable window in eleven years is the one the parameters
  were chosen on, and even there the t-statistic is 0.32. **The loop has done what it can inside
  its own rules**: the late-day fade is dropped (`alloc.late_momo` 1.0 -> 0.0, refused at 7 sigma
  in every regime, and it costs nothing in sample), and `equity_frac` stays at the 0.5 this
  morning's preliminary set rather than being restored to 1.0. What remains is ORB alone at
  -$289/day, t = -1.17 - not proven to lose, not proven to earn.

  **Decision wanted, one of three:** (a) keep it at `equity_frac` 0.5 as a live execution
  experiment - the sleeve's real purpose for the next few weeks would be A-5 part 2, measuring
  actual fill slippage against the 1.5 bps the harness assumes, which needs it to place orders;
  (b) flatten it to `equity_frac` 0.0 and let the loop work on O-1 (options-implied regime gating)
  until something tests positive out of sample - this is the choice the numbers alone support,
  and it costs the slippage measurement; or (c) accept the drawdowns as the price of the volatile
  mandate and restore size - which the evidence does not support and the loop will not do on its
  own. **The loop's default without an answer is (a)**, because it is the only option that keeps
  producing information.

  One thing the study *confirms* rather than kills: the book is genuinely a long-volatility
  position. corr(daily P&L, universe mean daily range) is **+0.202 at t = +10.70** over 2,686
  sessions and positive in all three regimes separately. The mechanism is real; only the level is
  negative. That is why O-1's regime gate, not another stop or size lever, is where the loop
  goes next.

  **Update 2026-09-10 (O-1 is now answered, and option (b) has no candidate left).** Option (b)
  above was "flatten it and let the loop work on O-1 until something tests positive out of sample".
  O-1 has been run and is **refused**. SPY's prior-day implied volatility forecasts the day's
  realized range at **corr +0.598, t = +36.4** (2,381 sessions), and the realized range predicts
  the sleeve's P&L at **+0.260, t = +13.95** - but the composition of the two is **-0.030, t =
  -1.46**. Splitting the range into the part implied vol saw coming and the part it did not, the
  forecast part is worth nothing against P&L (-0.030 / -0.016 / -0.058 for the three features) and
  the **surprise part is worth +0.351 / +0.292 / +0.299 at t = +18.3 / +14.3 / +15.3**, positive at
  t > 7 in nine of nine feature-regime cells. **The sleeve is paid for volatility surprise, not for
  volatility** - so the thing that pays is unknowable at entry, which is the same wall A-9 hit with
  the opening range, now confirmed against a market-priced forecast on ten times the sample. All
  six gate cells fail the pre-registered rule 0/3, the best of them earning **+$43/day at
  t = +0.13**. Nothing was shipped and `equity_frac` is still 0.5.

  **So the choice is now two-way, and it is yours.** (a) keep `equity_frac` 0.5 purely to finish
  **A-5 part 2** - the sleeve has still never placed a live intraday order, today's 09:25 ET
  session is the first that can, and the measurement is worth having because the harness charges
  1.5 bps of slippage against a **2.62 bps breakeven**, so a real number either rescues the whole
  cost model or buries it for good; or (b) **retire the sleeve to `equity_frac` 0.0**, which is
  what the evidence on its own says, and accept that the slippage constant stays a guess. The loop
  is still defaulting to (a), and it has an end condition now rather than an open-ended one: once
  A-5 part 2 has enough fills to price the constant to within two standard errors, there is no
  further information the sleeve can produce, and (b) becomes the only defensible setting unless
  the measured slippage is low enough to move the level. **The loop will not restore size, and it
  will not go to zero on its own while an owner question is open on exactly that number.**

  **Update 2026-09-11 (A-11 removes the last defence, in both directions).** The standing objection
  to every negative number above was that the backtest might be unfair to the sleeve, because A-5
  found its orders are routinely a large share of the volume of the minute they fill in. A-11
  measured that on 90,441 fills over 2,686 sessions, and the defect is **four times worse** than
  the IBKR window showed - notional-weighted p90 **18.8%** of the minute (A-5: 5.55%), with
  **24.1% of traded notional filling above 5% of its minute, 9.7% above 20% and 4.1% above 100%**,
  i.e. orders larger than everything that traded. It changes nothing: clipping every order to 10%
  of the trailing median volume of its fill minute refuses **$4.78M/day** of intended notional
  across **213,338 clipped orders** and moves the book by **-$5/day (t = -0.25)**, of which
  +$10/day is the extra commission of slicing - **the impossible fills carry no gross.** The
  sharper half of the result is the universe split:

  | | share of notional filling above 5% of its minute | 2,684 sessions, $/day | t | the 261-session fitted window, $/day |
  | --- | --- | --- | --- | --- |
  | the 8 liquid names (AAPL AMZN META MSFT TSLA NVDA GOOGL NFLX) | 8.8% | **-195** | **-1.89** | **-102** |
  | the 8 illiquid names (SMCI SOXL MSTR SOXS AVGO PLTR COIN AMD) | 45.8% | -164 | -0.83 | **+361** |

  **The half of the universe where the backtest is believable is the half that loses most
  convincingly, and the sleeve's only profitable window in eleven years earned all of it in the
  half where the median order is 4.12% of its minute and the p90 is 94%.** This does not change
  the decision the loop is waiting on - it removes the remaining reason to hope the answer is (a)
  for any purpose other than finishing the slippage measurement, which is still 6.8 sessions from
  being settled (2026-09-10: 32 fills, +2.89 bps, se 1.33, against a shipped 1.50 and a 2.52 bps
  breakeven). `equity_frac` is still 0.5 and nothing was shipped.

## Open requests to the owner (2026-09-10, the 3-10%/day mandate)

- **Options permission and data - now answered on the research side, and the answer is "not yet"
  (O-2, 2026-09-10).** The measurement no longer needs your permission: Theta already serves the
  quotes, and O-2 ran the whole study on **1,884 SPY 0DTE expirations, 2016-2026, every fill priced
  at the quoted bid/ask**. Three things came out of it, and only the third is a question for you.
  **(1) The premium is real.** The market's own quoted probability of a 0DTE short strike being
  breached exceeds the realized rate at **z = -2.7 to -3.8 in six of six delta/right cells**. That
  is the variance risk premium, measured directly, and it is the first gross edge in this repository
  that survives crossing the bid/ask on entry.
  **(2) It is still refused, and not on a parameter.** Closed at the quoted spread the trade earns
  **-1.53% of its own max risk per session** and loses in 8 of 11 years; the only version that pays
  (+0.767%, t = +3.05) assumes an untouched position expires free at the bell. **The median session
  closes 0.28% of spot from the short strike** and 37.4% close within 0.2%, so requiring the close to
  clear the strike by just **0.10% of spot - about 65 cents - takes it to +0.445% at t = 1.78 and
  0 of 3 regimes.** SPY settles on the official 16:00 print and is exercisable against until
  17:30 ET, so that buffer is a real exposure, not a modelling nicety.
  **(3) The mandate is arithmetically out of reach for this instrument.** Even at the un-buffered
  best cell, a 3%/day book needs **3.9x equity at risk every session**, and a defined-risk position
  posts its risk in full as margin - the ceiling is 1.0x, where the worst session in eleven years is
  **-105%**. At a survivable 0.25x it scores CAR 21.5% at a **60.6% drawdown**.
  **What would change the answer, and what it costs you.** Not permission - **data**. To price the
  exit honestly the loop needs OPRA quotes through the closing auction and the official settlement
  print, so the expire-or-close decision can be measured instead of assumed. If you want an options
  sleeve pursued further, that subscription is the purchase to make; **IBKR options permission on
  its own would only let the loop deploy something it has just refused.** Nothing is blocked today,
  and the loop will not open an options position.
- **Drawdown cap - this is now the binding constraint, and it is the only open item that can
  change any verdict.** A book that moves 3-10% a day will see 30-50% drawdowns as a matter of
  arithmetic. The current promotion cap is 35%. **As of 2026-09-10 every candidate on your list has
  been measured and refused** - O-1, O-1b, L-1, X-1 and O-2 - and in the one case where the cap was
  the reason rather than the edge (O-2 sized at 0.25x equity at risk: CAR 21.5%, drawdown 60.6%) it
  is decisive. Say the number you accept for the aggressive track (50% is the choice consistent with
  the mandate), or say that 35% stands and the loop will stop proposing strategies the mandate asks
  for. Note what raising it would and would not do: it would make a **21% CAR at 60% drawdown**
  promotable, which is worse on both axes than the daily champion's 24.4% at 25.1%. On the evidence
  in this repository, the aggressive mandate and the drawdown cap are not in tension because the cap
  is too low - they are in tension because **no measured edge here is large enough to pay for that
  much volatility.**
- **Real-time data bundle** (below) so paper fills and live bars are current.

## Open request to the owner (2026-09-09, intraday sleeve)

- **The intraday sleeve cannot be validated by backtest, at any sample size we can reach
  (A-4). Decide how it should be judged.** The minute store now holds a full year - 260
  sessions, 2025-08-26..2026-09-08 - and on it the deployed mix earns **$610/day, std $16,222,
  CAR 15.3%, Sharpe 0.69, t = +0.61**, i.e. a 95% interval on the year's total P&L of
  **[-$354k, +$671k]** around a $158.6k point estimate. The 77 sessions before 2025-12-15 were never used to choose any
  parameter and the mix **loses -$813/day on them** against +$1,289/day on the 183 it was fitted
  to - though even that gap is only t = -0.96, so it neither confirms nor refutes anything. At
  Sharpe 0.69 the sample needed to reject "this sleeve earns zero" at two standard errors is
  **~8.4 years, about 2,120 sessions**. We will never have it. What *is* measured, at
  t = +10.25, is that the book is a long-volatility position (daily P&L correlates +0.538 with
  the universe's same-day range) and that the holdout is simply the calmer window. **Decision
  wanted, one of three:** (a) let the paper account run it as deployed and treat the live record
  as the experiment, accepting that months of paper P&L will also be inside the noise;
  (b) shrink it - `equity_frac` or `gross` down until a losing year is a size you would shrug
  at, at the cost of the volatile-book mandate; or (c) hold it flat until A-9 (the
  opening-range-width gate, the one lever with a measured mechanism) reports. The loop's default
  in the absence of an answer is (a): the config is untouched and the sleeve trades as scheduled,
  because changing a deployed book on a coin flip is worse than either alternative.

  **Addendum 2026-09-10 (A-5 part 1), three numbers that sharpen the same question.** (1) The
  sleeve's **breakeven slippage is 2.62 bps and the harness charges 1.5** - it turns over $5.46M
  a day on a $1M book, so one basis point of execution cost is $546/day and the whole modelled
  edge of $610/day is **1.1 bps wide**. At 0 bps it earns $1,671/day (CAR 41.9%, Sharpe 1.51); at
  3.0 bps it loses $231/day. Nothing about the sleeve's sign is settled until real fills are
  measured, and the first paper session with fills is today. (2) **On the holdout the breakeven is
  -0.02 bps**: gross P&L before any slippage over the 77 sessions no parameter ever saw is
  **-$11/day**, so A-4's -$813/day is not a calmer regime earning less, it is a book with no gross
  edge paying its costs. If you were leaning to (b) shrink it, this is the argument for it.
  (3) A cost-model defect found on the way, being fixed next as A-10 and **not** an owner
  decision: 30% of the sleeve's traded notional is in SMCI / SOXS / COIN / MSTR, where the order
  is regularly 6-19% of the volume of the minute it fills in (worst case 199%), so part of the
  backtested gross is booked at prices that could not have been had. Expect the honest version of
  this sleeve to be **smaller** than the numbers above once that is capped. No answer is needed
  for A-10; the deployed config stays as it is until it has OOS evidence.

- **The intraday daily loss limit is a pure risk-posture dial - pick a point (A-7).** Swept
  1.5-3.5% and off on the deployed mix over 183 sessions. It has **no measurable effect on
  return** (every cell |t| <= 1.06 paired against the shipped 2.5%; total P&L 200.5k at 2.0%,
  221.2k at 2.5%, 243.1k at 1.5% - the sample's own standard error on that total is $229.6k),
  and **halting is free** (on halted sessions the halted book beat the limit-off run on the same
  dates at every limit except 2.0%). What it does control, monotonically, is the worst day on a
  $1M sleeve: **1.5% -> -20.5k, 2.0% -> -25.8k, 2.5% (shipped) -> -30.3k, 3.0% -> -37.2k,
  3.5% -> -42.5k, off -> -57.0k**, halting 22% / 10% / 4% / 2% / 1% / 0% of sessions
  respectively. Because the evidence is silent on return, the agent left the shipped 2.5% alone
  rather than move risk posture unasked. **Decision wanted:** keep 2.5%, or name a worst-day
  budget and the loop will set the limit to that number minus ~0.3 points of overshoot. Related
  and also owner-level: sleeve `gross` 2.0 tested at +2.7% of P&L (t = +0.56), refused because
  it exceeds A-3's stated 1.0-1.5x target and would put the two sleeves near 3.2x against
  day-trading buying power.

- **Real-time market data subscription.** The paper account has no quote subscription:
  IBKR bars and quotes arrive 15 minutes late (measured), so the intraday trader runs on the
  Yahoo 1-minute feed. IBKR simulates paper fills from the data the account is entitled to,
  so fills may be stale until a subscription exists. Client Portal -> Settings -> Market Data
  Subscriptions -> "US Securities Snapshot and Futures Value Bundle" (~$10/month, waived with
  commissions) or the US equity streaming add-on; then restart Gateway once. After that the
  trader's feed auto-detection will pick IBKR bars (`feed_probe` in the intraday log).

## Decisions taken by the owner on 2026-09-09 (all four open items answered)

1. **Volatility mandate vs the 35% drawdown limit: option (c).** The 35% cap stays for
   anything that can be promoted or deployed. Higher volatility is to be *earned* by adding
   uncorrelated sleeves (S-2 intraday breakout now that D-2 is unblocked, S-5 allocator) and,
   later, by portfolio-level sizing across sleeves, not by pushing the single ETF sleeve to the
   Reg-T ceiling. Raising the cap is to be revisited only once the allocator has two sleeves
   with positive expected return.
2. **Sharpe vs return in the promotion rule: return-first with a Sharpe tolerance.**
   `champion.json` now requires beating the champion on CAR, allows Sharpe to be up to 0.03
   below the champion, and refuses any run whose drawdown is more than 1 point worse than the
   champion's (on top of the absolute 35% cap). `scripts/evaluate.py` implements this via
   `sharpe_tolerance` and `drawdown_tolerance_points`. The S-11 cell (`min_hold=10`,
   `margin_budget=0.85`) may be re-run through the sub-periods and promoted if it passes.
3. **Delisted-inclusive history: deferred, not bought now.** The ETF sleeve remains the only
   promotable universe; single-name results stay tagged `not promotable`. Revisit after two
   weeks of paper fills, with a cost quote for Norgate or Sharadar in hand.
4. **Execution no-trade band: keep 0.01.** The order list stays identical to the backtest and
   `compare_orders.py` remains the deploy gate. Revisit with measured paper slippage after two
   weeks of fills; if the measured spread cost per order is material, widen to 0.03 and
   rebaseline the hash.

Also on 2026-09-09: **paper trading is approved.** `live/APPROVED_PAPER.md` exists; the
15:45 ET weekday task now sends orders to DUT091359. I-1 is done. Do not touch the approval
file from any automated job.

- **2026-09-08 Intraday market data (decision requested, blocks S-2).** Daily bars are done:
  D-1 shipped 69 symbols of free `yfinance` daily history, 1998-2026, and LEAN reads them.
  Intraday is still missing - Yahoo caps 1-minute history at about 30 days, too short to
  backtest. To unblock S-2 (opening-range breakout) the human should pick one of: IBKR
  historical data (needs IB Gateway logged in on this machine, no extra cost) or a
  QuantConnect data subscription (`lean data download`, needs `lean login`, paid).
  Until then the loop runs daily-frequency strategies only.
- **2026-09-08 Delisted-inclusive history (decision requested; caps every single-name
  strategy).** Now measured rather than suspected. D-3 built a point-in-time universe -
  membership decided each rebalance by trailing 60-day dollar volume, so the 2012 sleeve
  really does hold BAC/GE/XOM/WFC/IBM and the 2026 one holds NVDA/TSLA/AMD - and it removed
  only **0.8 of the 7.8 points** by which the passive megacap basket beats SPY (22.8% -> 22.0%
  CAR against SPY's 15.0%). The other 7.0 points survive because `fetch_data.py` could only
  download the 69 tickers that still exist in 2026: a name that was heavily traded in 2012 and
  has since been acquired or delisted (Sprint, Yahoo, EMC, Dell) can never be a candidate, and
  those are disproportionately the losers. So every result on the single-name sleeve is an
  upper bound and is tagged `not promotable`, however good its statistics look. Only a
  delisted-inclusive data set fixes this, and that is paid: CRSP, Norgate, Sharadar or
  QuantConnect's US Equity Security Master are the usual options. **Decision needed:** buy one,
  or accept that the model stays on the ETF sleeve (which has no equivalent bias - all nine
  names traded throughout the sample). The current champion is on the ETF sleeve, so nothing
  is blocked today; what is blocked is ever trusting the higher single-name numbers.
- **2026-09-08 The volatility mandate vs the 35% drawdown limit (decision requested; caps how
  aggressive the model can be).** `USER.md` asks for an aggressive, volatile model and S-1's
  write-up targets 40-60% realized vol; `champion.json` caps drawdown at 35%. S-8 measured the
  frontier in LEAN and the two cannot both be had on the ETF-9 sleeve:

  | config | Vol | CAR | Sharpe | MaxDD |
  | --- | --- | --- | --- | --- |
  | champion (flat budget 0.75) | 16.5% | 18.1% | 0.693 | 25.2% |
  | elastic budget, target_vol 32% | 19.4% | 19.7% | 0.674 | **34.3%** |
  | flat budget 1.0 (Reg-T, maximum) | 20.6% | 20.4% | 0.672 | **35.4%** |

  The drawdown limit binds at 19-20% vol - and 20.6% is already the *Reg-T ceiling*, since an
  initial-margin budget of 1.0 means 2.0x gross on an ordinary ETF. Reaching 40% vol would
  need roughly double that again, which is impossible in a Reg-T account without either a
  portfolio-margin account or a much larger allocation to the 3x ETFs, and either way the
  drawdown would land far beyond 35%. S-8 tried four ways to earn the headroom (wider `top_n`,
  an earlier drawdown breaker, per-holding trailing stops, a vol-responsive margin budget) and
  all four cost more return than they saved in drawdown. **Decision needed, one of:** (a) keep
  the 35% limit and accept ~18-20% vol as the honest ceiling for this strategy, (b) raise the
  drawdown limit in `champion.json` to a stated number and let size go to the Reg-T cap, or
  (c) treat higher vol as something to be earned by *adding uncorrelated sleeves* (S-3, S-2,
  the S-5 allocator) rather than by leverage. Nothing is blocked today - the champion and the
  I-1 paper deployment are unaffected - but until this is answered the loop cannot pursue the
  mandate as written.

  **Addendum 2026-09-08 (S-11), which sharpens option (b) into a specific trade.** The whipsaw
  controls buy drawdown cheaply, and spending that headroom on size produces a run that beats
  the champion on *absolute* return at the *same* drawdown: `min_hold=10` with
  `margin_budget=0.85` earns CAR 25.07% at 25.7% drawdown (champion: 23.61% at 25.9%), on 306
  fewer orders and $2k less commission - but at Sharpe 0.861 against 0.874. `evaluate.py`
  refuses it, correctly, because `champion.json` requires beating the champion on Sharpe *and*
  CAR. So there is now a second, smaller decision inside this one: **is +1.5 points of annual
  return at unchanged drawdown worth 0.013 of Sharpe?** Under `USER.md`'s aggressive mandate
  the answer is plausibly yes, but changing a promotion rule is a change of risk posture and
  is not the loop's call. Answer it here (or say "keep Sharpe as a hard gate") and the loop
  will either re-run that cell through the sub-periods and promote it, or stop proposing it.
- **2026-09-09 The execution no-trade band for the paper account (decision requested; affects
  the live order list only, not the backtest).** S-13 swept `min_order_value` - the fraction of
  equity below which a rebalancing delta is skipped - and found the strategy is **insensitive**
  to it: from 0.01 to 0.08 the full-period CAR walks 24.40, 24.35, 24.54, 24.34, 23.92, 24.47
  with no trend, while order count falls 4,735 -> 1,727. So roughly **63% of the champion's
  orders are return-neutral**. In LEAN that is worth only the $6.1k of commission the widest
  band saves over 14 years, which is why no cell wins on the promotion rules and nothing was
  shipped. **Live it is worth more than that**, because LEAN charges commission but models no
  spread at all, and every skipped order is also a spread not crossed and a fill that cannot
  come back worse than the close the signal decided on.

  **Decision needed:** should `scripts/paper_trade.py` run a wider band (0.03 or 0.08) than the
  backtest's 0.01? The loop did not make this call for two reasons: it is an execution/cost
  judgement about real fills rather than a research result, and changing it would move the
  order list away from `OrderListHash 5246804e17a67af90028ffceead7d3b3`, which is the exact
  baseline I-1's pre-deploy comparison is built on. Say "keep 0.01" and this is closed; name a
  wider band and the loop will re-run that cell, re-verify the runner against it and rebaseline
  the hash before deploy. Nothing is blocked today - the champion and I-1 are unaffected.
- **RESOLVED 2026-09-09 ~14:30 UTC: IB Gateway API is up.** The human accepted the paper
  disclaimer; `paper_trade.py --check` returns account `DUT091359`, net liquidation
  $1,000,344, margin enabled (buying power $4M), no positions. I-1's remaining step is the
  human creating `live/APPROVED_PAPER.md`; D-2 (IBKR minute history) is unblocked now.
  Kept below for the record:
- **2026-09-09 IB Gateway API disclaimer (one click, blocks the whole 2026-09-10 deadline).**
  Supersedes the 2026-09-08 "install IB Gateway and log in" item, which is **done**: port 4002
  is open and answering as of 13:40 UTC today, so Gateway is running and logged in. The API
  handshake is refused one stage later:

  ```
  Error 10141, reqId -1: Paper trading disclaimer must first be accepted for API connection.
  ```

  This is a one-time acknowledgement inside Gateway, not a code or config problem on this side.
  **Action, about one minute:** in IB Gateway, Configure -> Settings -> API -> Settings, tick
  *"Accept paper trading account API connections"*, accept the disclaimer dialog it raises, and
  leave Gateway running. Then `py -3.11 scripts/paper_trade.py --check` returns an account
  summary and I-1, D-2 and S-2 all unblock in that order. Ports 7497/7496/4001 are closed,
  which is correct for Gateway rather than TWS. While accepting it, please also confirm the
  paper account has **margin enabled** - the champion's plan is a 1.23-1.5x gross book and a
  cash-only account will reject the first order.

  **Addendum 2026-09-09 (I-1 iteration), three things that shorten what happens after the
  click.** (a) It is definitely the disclaimer and not a stale API session: the same 10141
  comes back on a fresh `--client-id 91`, so there is nothing to kill or restart first.
  (b) The pre-deploy order-list comparison that item I-1 lists as remaining work is **no
  longer a manual step** - `scripts/compare_orders.py` now automates it, and it **passes**
  (3,689 of 3,689 decision dates, identical order counts). It found and fixed a real runner
  bug in the process, so the post-click sequence is now just `--check`, `--dry-run` on the
  real account, and a re-run of that gate. (c) Paper *orders* still require you to create
  `live/APPROVED_PAPER.md`; it does not exist, the runner refuses to trade without it, and
  the loop will not create it.
