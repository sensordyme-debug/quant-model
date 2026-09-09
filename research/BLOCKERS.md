# Blockers needing the human

Items the agent cannot resolve alone. Remove an item when it is resolved and note the date.

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
