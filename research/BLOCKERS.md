# Blockers needing the human

Items the agent cannot resolve alone. Remove an item when it is resolved and note the date.

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
