# Blockers needing the human

Items the agent cannot resolve alone. Remove an item when it is resolved and note the date.

## Open ops item for the human (2026-09-11, the daily runner's clock - **re-priced at ~1.9 CAR points by S-19**)

- **The deployed daily champion is trading a signal one session staler than the strategy that was
  backtested, and closing the gap needs a scheduled task moved, which the loop may not touch.**
  This is measured, not suspected:

  | path | signal reads closes through | fills at | elapsed from signal to fill |
  | --- | --- | --- | --- |
  | LEAN backtest (24.404% then; **24.403% on the promoted champion**) | day D | the **open of D+1** | one overnight gap |
  | `scripts/paper_trade.py` as scheduled | day **D-1** | the **close of D** | one overnight gap **plus a full session** |

  The evidence is the runner's own log: `ref_price` equals the previous session's close in **6 of 6
  fills** (2026-09-09 and 2026-09-10), and the `plan` event recorded `as_of = 2026-09-08` and
  `as_of = 2026-09-09` respectively. The cause is benign - `fetch_history_yf` calls
  `yf.download(period="2y")` at 15:45 ET and the last *complete* daily bar at that moment is
  yesterday's. Priced over the full sample with `S1_SIGNAL_LAG=1` (a tight upper bound: it is one
  overnight gap staler than the live path, never less), the cost is **CAR 24.404% -> 19.649%,
  Sharpe 0.921 -> 0.736, paired -1.55 bps/day at t = -2.65 on 3,689 sessions**, and about
  **18.6%** once the measured 2.9 bps of spread is charged as well. It costs return, not risk:
  drawdown *improves* (23.7% vs 25.1%).
- **The clean fix, and why it is yours.** Run the daily sleeve **before the open instead of before
  the close** and send MarketOnOpen orders: read the previous session's close (complete by then) and
  fill at the open of D. That is *literally* the backtest's convention, so the deployed path and the
  24.404% would finally be the same strategy. It needs two things: the Windows task "Quant Daily
  Sleeve" moved from 15:45 ET to a time before **09:28 ET** (IBKR rejects opening orders outside
  04:00-09:28), and `paper_trade.py --order-type` extended with an OPG/MOO option. The task is
  **"Quant Paper Rebalance"** (currently `Ready`; the other two, "Quant Intraday Sleeve" and
  "Quant Dashboard", are unrelated and were only read, never modified). AGENTS.md forbids
  the loop from changing scheduled tasks, so **say the word and the loop will write the order-type
  support, verify it with `--mock --dry-run` and `compare_orders.py`, and hand you the one task
  change to make.** Nothing has been changed.
- **A smaller in-place alternative, if you would rather not move the task.** Append the current
  15:45 price as the last row of the runner's price frame, so the signal reads through day D and the
  15:46 fill is a minute behind its own decision - *tighter* than the backtest's overnight gap rather
  than a session looser. The loop did not do this unasked because of a real risk: the paper account
  has **no real-time market data subscription** (see the item below), so that price is itself 15
  minutes delayed and the fix would silently re-introduce a smaller version of the same defect. The
  data bundle below is therefore a prerequisite for this route and not for the pre-open route.
- **What is not affected.** The champion, `champion.json`, `compare_orders.py` and the
  `OrderListHash` are all unchanged; this is about *when* the runner acts, not what it decides, and
  `compare_orders.py` compares order lists on historical dates so it still passes 3,689/3,689.
- **Update 2026-09-11 (S-19): the defect is unchanged, the price tag is a third smaller, and it is
  now a measurement rather than a bound.** Two things were wrong with the -4.75 above, neither of
  them the diagnosis. **(1) It was measured on a strategy that was retired the same day.** S-18
  replaced the 3x proxies and the drawdown breaker with the unlevered book, and a staleness cost is
  a *return* cost, so it shrinks with exposure. Re-run on the promoted champion, `S1_SIGNAL_LAG=1`
  earns **21.384% / 0.860 / DD 22.7%** against 24.403% / 0.994 / 23.7%, i.e. **-3.02 CAR at 0 bp**
  and **-2.99 at 2 bp** (20.074% against the champion's 23.068%). **(2) `S1_SIGNAL_LAG=1` is an
  upper bound by construction** - it hides the last close *and* still fills at the next open, so it
  is one whole overnight gap staler than the deployed path, which fills at the close of the session
  it decided in. LEAN cannot express the real convention on daily bars, so `scripts/sweep_s19.py`
  runs the shared `signals.py` through a book that fills wherever it is told, after checking itself
  against the champion's own LEAN equity curve (**corr 0.99650**, annualized std 0.1863 / 0.1872,
  tracking sd 9.86 bps/day). In that harness:

  | convention | CAR | paired vs the backtest |
  | --- | --- | --- |
  | backtest, and what the pre-open fix would restore | 24.077% | - |
  | **the deployed 15:45 runner** | **22.192%** | **-0.599 bps/day, t -1.41** |
  | `S1_SIGNAL_LAG=1` (the LEAN bound) | 20.965% | -0.994 bps/day, t -1.86 |

  The deployed clock costs **61% of the bound**, and the harness agrees with LEAN to 0.09 CAR points
  on the cell both can run - so **the number to use is about -1.9 CAR points** (0.61 x 3.02), and
  the -4.75 above is superseded. The cost is out-of-sample weighted (IS -0.32 bps/day at t -0.58,
  OOS -0.99 at t -1.49) and it still costs return rather than risk (drawdown improves, 22.7% against
  23.7%). **Say the number out loud with its error bar**: nothing in this comparison reaches
  |t| = 2 on 3,689 sessions. The reason to fix it is that the defect is certain - the runner's own
  log records `as_of = D-1` every session and `ref_price` matched the previous close in 6 of 6 fills
  - not that 1.9 points of return are being measured with confidence. **Nothing changed**: the
  request is still the one task move plus the `--order-type` work, and the loop has not touched
  either.
- **Update 2026-09-11 (S-22): the number survives being charged the other two costs, and the
  request is now the cheapest and best-priced item on this page.** S-17's spread, S-19's clock and
  S-21's financing have been charged together for the first time. They are **independent** (the LEAN
  triple prints 18.785% against a pre-registered multiplicative null of 18.811, every pairwise
  interaction inside 0.021 CAR points), so the clock's value does not shrink once the book is paying
  for its spread and its margin loan. On the honestly-costed book, at today's 3.63% cost of money:

  | path | CAR (fully charged) |
  | --- | --- |
  | the deployed 15:45 runner | **19.415%** |
  | **the pre-open MOO fix you are being asked for** | **21.264%** |

  **+1.85 CAR points**, against S-19's -1.9 on a book that paid neither of the other two costs.
  Everything else about the request is unchanged: move "Quant Paper Rebalance" to before 09:28 ET
  and the loop writes the `--order-type` OPG/MOO support, verifies it with `--mock --dry-run` and
  `compare_orders.py`, and hands you the one task change. **One further fact you should have when
  you read any number in this repository**: the champion's promoted headline of 24.403% is what the
  harness reports with all three costs switched off. The deployed book's honest expectation is
  **~20%** (19.95% at historical rates, 19.42% at today's), and `champion.json` now records that
  beside the headline. `ref_price` has now matched the previous close in **10 of 10** paper fills.
- **Update 2026-09-11 (S-23): the loop's half is written, and the move now has a breakeven instead
  of an assumption. The ask is down to one line.**
  - **Written and verified**: `scripts/paper_trade.py --order-type MOO` sends the opening-auction
    order IBKR actually accepts (a `MKT` carrying `tif="OPG"`), and because IBKR rejects `OPG`
    outside **04:00-09:28 ET** - one order at a time, which would leave the book half rebalanced -
    it **checks the clock before it connects and refuses** with exit 3. Proved live at 17:51 ET.
    `MKT` is still the default, so the 15:45 task is byte-for-byte unchanged in behaviour; the
    `--mock --dry-run` plan is identical and `compare_orders.py` passes **3,689/3,689 at 5,021
    orders**. **Nothing has been scheduled and no task was touched.** When you are ready:
    move "Quant Paper Rebalance" to any weekday time before 09:28 ET and append `--order-type MOO`
    to its command line. That is the whole change.
  - **The payoff is unchanged and now has an error bar and a breakeven.** Both books fully charged
    (2 bp spread + IBKR Pro financing), today's cost of money, LEAN units: deployed **19.416%** ->
    pre-open **21.260%**, i.e. **+1.844 CAR points** (+1.875 at historical rates), paired **+0.601
    bps/day at t +1.42** on 3,689 sessions - so, as with S-19, **nothing here reaches |t| = 2**. The
    gain is out-of-sample weighted more than three to one (IS +0.93, OOS +3.16).
  - **The assumption nobody had charged**: every version of the +1.85 assumed the opening auction
    fills as cheaply as the closing one. Solved for indifference, **the opening auction may cost up
    to 3.10 bps MORE than the closing auction before the move stops paying**. For scale your live
    15:45 market orders measure **+3.2 bps** against the close they aim at. The only evidence
    available on the other side is a proxy - Alpaca minute bars have no quotes - and it says the
    **opening minute is 1.0x to 2.0x as wide as the closing minute** (SPY 1.04, QQQ 1.54, IWM 2.00,
    TQQQ 1.61) on 2,687 sessions. At the 2.0x end the move is a wash rather than a gain. **The
    recommendation is still to make the move** - the defect is certain while its price tag is not -
    but it is now an informed call rather than a free one, and `daily_fills.py` has been extended to
    score MOO fills against the **open** they aim at, so the first post-move session measures
    whether the 1.85 was collected.
- **Update 2026-09-11 (S-24): the assumption above is no longer an assumption. It was measured on
  the official auction prints, it costs about 0.22 bps against the 3.10 bps you had to budget for,
  and the move still pays.** The Alpaca key already in `live/secrets.env` serves two endpoints the
  loop had never used - `/v2/stocks/auctions` (the official opening and closing cross prints back
  to 2016) and `/v2/stocks/quotes` (full SIP NBBO) - so the surcharge S-23 could only bound has now
  been priced directly rather than proxied.
  - **One thing you should know about every "open" number in this repository.** The daily store's
    **close is the official closing cross to the cent, on every session of all nine names** - so
    the deployed 15:45 convention has always been marked at exactly the right price. Its **open is
    not the opening cross**: Yahoo's daily open is the first consolidated print, and it misses the
    primary auction by about a basis point a day (XLE by 8-11 bps on some sessions). That defect
    lands entirely on the *pre-open* book - the one you are being asked to authorise - so it was
    worth removing before you decide.
  - **Re-priced at the price a real MOO order actually receives**, on 2,683 sessions (2016-2026),
    both books fully charged, today's cost of money:

    | path | CAR (fully charged) |
    | --- | --- |
    | the deployed 15:45 runner | **22.007%** |
    | the pre-open MOO fix, as S-23 priced it | 24.134% |
    | **the pre-open MOO fix at the official cross** | **23.985%** |

    **+1.98 CAR points**, against +2.13 on the same window before the correction - the benchmark
    defect costs 0.149 points, about 8% of the move, and it is the *conservative* end of a band.
    An MOO order is matched in a single-price call auction and **does not cross a quoted spread**,
    so the 2 bp charged to that row is an overcharge; charged nothing it earns 25.204%, i.e.
    **+3.20 points**. The honest range is **+1.98 to +3.20, and the recommendation uses +1.98.**
  - **The worry S-23 raised is answered and it was drift, not cost.** The opening cross sits 6.12
    bps from the mid 30 seconds later, but the *next* 30 seconds - with no auction in them - move
    the same names 4.10 bps, and signed the cross sits -0.21 bps from fair value with mixed signs
    across the nine. Re-filling the whole book at the real cross cost 0.149 CAR points, i.e. ~0.22
    bps, against the 3.10 bps you had to budget for: **7% of the budget.**
  - **One new operational fact, and it argues for the guard rather than against the move.** The
    quoted spread at 09:30:00 is **4.6x** the closing one (XLK **12.7x**, a 5.00 bps half-spread;
    XLE **11.7x**, 6.82 bps) and decays within 30 seconds. That is *not* what an MOO order pays -
    it is matched in the cross - but it is exactly what a fallback market order would pay if the
    MOO were ever missed. So the 04:00-09:28 clock guard S-23 built is doing real work, and
    "just send a market order at the open instead" is not a shortcut worth taking.
  - **The ask is unchanged and still one line**: move "Quant Paper Rebalance" to a weekday time
    before 09:28 ET and append `--order-type MOO`. Nothing has been changed.
- **Update 2026-09-12 (S-25): the ask is unchanged, the recommendation is unchanged, and two things
  about it are now known that were not. The move buys the half of the day where this strategy has
  never demonstrated an edge - and the alternative below it is dead.** The deployed book's daily
  return has been split into its two legs for the first time (`scripts/sweep_s25.py`, 3,689
  sessions, on the S-19 harness that reproduces the deployed book to the digit).
  - **Where the champion is actually paid**: **+8.103 bps/day while the market is shut (t +6.80),
    94% of the total**, against **+0.738 bps/day while it is open (t +0.47)**. Quoted against an
    always-invested book scaled to the same gross - the control that separates a forecast from
    simply being long - the ranking adds **+3.087 bps/day overnight at t +4.20** (both halves) and
    **-0.314 intraday at t -0.37**. It is not a dividend effect (price-only the overnight excess is
    larger, +3.231 at t +4.36) and not an artifact of Yahoo's open (on S-24's official crosses the
    leg reads +8.864 against +8.887).
  - **What that means for this decision.** The deployed runner and the pre-open runner hold the
    *same* targets overnight; they differ only in what they hold between the open and the close of
    the session they trade in. So the whole +1.98 is intraday by construction, and the measurement
    confirms it: **intraday +0.604 bps/day (t +1.43), overnight -0.006 (t -1.34)**. The move is
    still worth making - the staleness defect is certain, the drawdown does not worsen, and the
    point estimate has been positive in four independent harnesses - but it is buying a leg with no
    demonstrated edge, at a statistic that has never reached |t| = 2 in any of them. **Read the
    +1.98 as the best estimate of something genuinely uncertain, not as found money.**
  - **The "smaller in-place alternative" three items above is now priced, and it is dead.** Feeding
    the 15:45 price into the signal so it reads through day D and still filling at D's close is
    worth **+0.18 CAR points** (22.374% against the deployed 22.192%), priced as an *upper* bound
    that assumes a decision can be executed at the very close it is made on. Leg by leg it buys the
    same intraday improvement (+0.616, t +1.45) and **hands almost all of it back overnight
    (-0.572, t -1.79)**, because putting today's close into the signal fights the one-day reversal
    the champion's own week-skip momentum windows were built to avoid. **Consequence for a purchase
    you may have been considering: the real-time market-data subscription cannot be justified by
    this fix.** It may still be worth buying for the intraday sleeve or for order safety - that is
    a separate question - but not for the daily runner's clock.

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
- **2026-09-12 (I-2): the verdict now exists, the delivery does not.**
  `scripts/session_audit.py` turns both logs into 21 assertions and one verdict with an exit code
  (`py -3.11 scripts/session_audit.py`, `--all`, `--json`). It is validated: it FAILs 2026-09-11 on
  exactly the two real defects of the window (the S-18 TQQQ orphan and the intraday rollover P&L
  leak) and stays quiet on the three clean days. **Two things need you, and they are independent.**
  (1) *Delivery* - with `live/alerts.json` in place the same verdict can be pushed at 16:00 ET
  instead of polled. (2) *Schedule* - the pass currently runs only when the research loop runs, so
  a FAIL can still sit unread until the next iteration. Firing it from its own Windows scheduled
  task at ~16:00 ET (after the intraday sleeve's 15:42 exit and the daily 15:45 rebalance) is a
  one-line task registration, and **AGENTS.md bars the loop from creating or editing scheduled
  tasks**, so it is yours. Nothing else about it needs a decision: it opens no connection, places
  no order, and writes nothing outside `live/log/audit-<date>.json`.

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
- **S-16 evidence added 2026-09-11: there is now a fourth option, and it dominates (b).** The two
  dials below are one dial. The 3x proxies' only contribution is *margin efficiency* - IBKR charges
  0.333 of margin per unit of economic exposure for a 3x ETF against 0.5 for an ordinary one - so
  the choice is between buying exposure through the instrument or through the budget. Measured on
  the full period (`scripts/sweep_s16.py`, all cells environment overrides, control reproducing
  `OrderListHash 5246804e17a67af90028ffceead7d3b3`):

  | cell | budget | held | max exp | CAR | Sharpe | MaxDD | ann.std | fees |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | shipped champion | 0.75 | 3x proxies | 2.25x | 24.404% | 0.921 | 25.1% | 0.170 | $45,695 |
  | (b) budget 0.792, 3x kept (2017-2026 window) | 0.792 | 3x proxies | 2.38x | +1.55 pts | 1.042 | 22.8% | 0.188 | $14,530 |
  | **(d) proxies off + overlay off** | **0.75** | unlevered | 1.50x | **24.403%** | **0.994** | **23.7%** | **0.155** | **$27,200** |
  | **(d+) the same, budget 0.80** | **0.80** | unlevered | 1.60x | **25.903%** | **1.008** | **25.1%** | 0.164 | $31,622 |
  | (d+) the same, budget 0.82 | 0.82 | unlevered | 1.64x | 26.474% | 1.012 | 25.7% | 0.168 | $33,530 |

  **Read the third row first: at the *unchanged* 0.75 budget the same signal earns the champion's
  return to three decimal places** (paired difference -0.00 bps/day, t -0.00 on 3,689 sessions)
  **with 0.015 less realized vol, 1.4 fewer points of drawdown and $18.5k less commission.** So the
  3x sleeve and the drawdown breaker together are buying no return at all. Row four spends the
  freed risk: **+1.50 CAR at the champion's own 25.1% drawdown and below its realized vol**, which
  is the same size (b) offers, bought more cheaply. `evaluate.py` says "BEATS champion" for rows
  four and five and refuses row three by 0.001 CAR points, which is why nothing was promoted.
- **What (d+) costs that the table does not show.** Reg-T excess liquidity falls from 25% to 20% of
  equity - the buffer objection below still applies, at 0.80 instead of 0.792 - but the account's
  *economic* exposure falls from up to 2.25x to 1.60x, and a 1.6x unlevered book marks down far
  more slowly in a crash than a 0.75x book of 3x ETFs, so the margin call it is guarding against is
  further away, not nearer. **Answer (a), (b), (c) or (d/d+), or name the excess liquidity you want
  held and the loop will solve for the budget under it.** Nothing has been changed.
- **S-17 update 2026-09-11: one of the options is no longer yours to answer.** S-16's row three -
  proxies off and overlay off at the **unchanged** 0.75 budget - was refused only because it missed
  the champion's CAR by 0.001 points, and S-17 found that the harness charging **zero spread** is
  what created that margin. Charge a spread and the cell wins outright: at 1 bp **+0.036 CAR**, at
  2 bp **+0.142 CAR with Sharpe 0.938 against 0.865, drawdown 25.0 against 29.2 and $24.9k of
  commission against $41.9k**, and the crossover is at about **0.03 bp** against a half-cent tick
  worth 0.27-0.77 bp on these names. Because it holds the budget at 0.75, **it does not touch your
  Reg-T buffer at all** and its economic exposure *falls* from 2.25x to 1.50x - so the loop will
  pursue it as S-18 without an answer from you. **What still needs you is only the size question**:
  options (b), (c) and (d+) all raise `margin_budget` above 0.75, and rows four and five of the
  table above are still parked behind that. The honest restatement is that the menu is now "keep the
  buffer and take the risk reduction for free (loop's call, in progress), or additionally spend the
  buffer for +1.5 CAR (yours)".
- **The second dial is the 3x proxies.** Holding the same signal in the unlevered parents instead
  of UPRO/TQQQ/TMF gives **23.128% CAR at Sharpe 0.950, drawdown 23.6%, std 0.153, PSR 27.4% and
  $25,646 of fees** against the champion's 24.404% / 0.921 / 25.1% / 0.170 / 23.0% / $45,695 -
  **better on every risk-adjusted measure and on cost, for 1.28 points of CAR.** So the leveraged
  sleeve is not buying edge, it is buying volatility (the same thing L-1 found intraday), and
  whether to keep paying for it is the same kind of decision as the budget above. The loop has
  changed nothing; `S1_PROXY=off` exists only as a research override and defaults to the champion.
- **Update 2026-09-11 (S-18): the second dial is no longer a question - it was taken, and it makes
  the first one worth more.** The loop promoted the unlevered book at the **unchanged 0.75 budget**,
  because that change needs no Reg-T decision from you: same return (24.403% vs 24.404% at zero
  spread, +0.14 CAR once a 2 bp spread is charged), Sharpe 0.994 vs 0.921, realized vol 0.155 vs
  0.170, drawdown 23.7 vs 25.1, fees $27.2k vs $45.7k, and **economic exposure 1.50x against 2.25x**.
  The halves are in the journal; the paired return difference is t = +0.12, so this was promoted on
  risk and cost, not on return. **What that leaves for you is the same size question on a better
  book**: spending the freed risk through the budget now reads **0.75 -> 0.78 -> 0.80 -> 0.82 giving
  CAR 24.403 / 25.307 / 25.903 / 26.474 at Sharpe 0.994 / 1.003 / 1.008 / 1.012** - Sharpe *rising*
  with size, which it did not do on the 3x book - and at 0.82 the unlevered book matches the retired
  champion's own realized vol (0.168 vs 0.170) while earning **+2.07 CAR** over it. The buffer
  argument is unchanged and still yours: at 0.82 a live account holds 0.18 of excess liquidity
  instead of 0.25. The loop stops at 0.75 until you answer.
- **Update 2026-09-11 (S-21): every number you have been shown on this question was computed
  with the cost of the borrowing left out, and here is the same table with it charged.** This
  question is *exactly* a decision about how large a margin loan to carry, and LEAN charges no
  interest on one: `DefaultBrokerageModel.GetMarginInterestRateModel` returns
  `MarginInterestRateModel.Null`, whose `ApplyMarginInterestRate` is an empty method, and the
  IB model does not override it. The shipped book runs a debit balance on **83.3% of sessions,
  averaging 0.49x of equity**, and has never paid for it. Charged at IBKR Pro's published
  tiers on the historical effective fed funds rate (FRED `DFF`, IBKR's USD "BM"):

  | `margin_budget` | CAR as previously shown | CAR with financing charged | gain over 0.75 | Sharpe | MaxDD |
  | --- | --- | --- | --- | --- | --- |
  | **0.75 (shipped)** | 24.403% | **23.087%** | - | 0.939 | 24.1% |
  | 0.80 | 25.903% | **24.296%** | **+1.209** (was +1.500) | 0.944 | 25.6% |
  | 0.82 | 26.474% | **24.742%** | **+1.655** (was +2.071) | 0.945 | 26.2% |

  **Read it as a flattening, not a reversal.** The ordering and the sign are unchanged, so
  nothing above is withdrawn - spending the buffer still buys return. What shrinks is how
  much: **the reward is overstated by about a fifth**, and the Sharpe argument thins much
  more than that. Unfinanced, Sharpe *rises* across the frontier 0.994 -> 1.008 -> 1.012,
  which is the strongest single sentence in the case for (d+); financed it rises 0.939 ->
  0.944 -> 0.945, a sixth as much, while drawdown climbs 24.1% -> 25.6% -> 26.2%. So the
  honest restatement of (d+) is **"+1.2 to +1.7 points of CAR for ~2 points of drawdown and
  essentially no improvement in risk-adjusted return"**, where it used to read "+1.5 to +2.1
  points at a *better* Sharpe". Whether that is worth 0.05-0.07 of your excess liquidity is
  still yours, and the loop still stops at 0.75.
- **Two things this does not mean.** (a) It is not a new cost and not a defect: the paper
  account has been paying it since the first fill, the runner is fine, and the only thing that
  was wrong was the expectation. (b) It is not a reason to shrink the book either - the
  financed champion at 0.75 still earns 23.087% and the drag is proportional to the borrowing,
  so the comparison between budgets is what moves, not the case for the strategy.
- **What it is worth on its own, for the record**: **-1.316 CAR full period, -0.907 in
  2012-2019 and -2.027 in 2020-2026**, because the benchmark went from ~0.1% to 5% - **82% of
  the interest over the whole sample was incurred in 2023-2026** - so the forward-looking
  number at today's 3.63% benchmark is about **2.0 points a year, not 1.3**. About half of it
  is the cost of money and cannot be avoided by anyone; the other half is the broker's markup,
  and a larger account pays less of that (+0.75% above $1M against +1.50% on the first $100k).
  Nothing was changed: `S1_FINANCING` defaults off so the ledger stays on one scale, and
  `scripts/sweep_s21.py --report` reproduces every figure here.

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
- **CME futures HISTORY - a purchase request that is now priced, and NOT the one the backlog
  has been asking for (F-2a, 2026-09-11).** The backlog carried F-2 as "needs IBKR futures
  permission + CME data". **That was never probed and it is wrong.** This paper account already
  fetches **ES, MES, NQ and MNQ 1-minute TRADES bars for the full 23-hour session with zero
  errors** - no 354 "not subscribed", no 162, no 10197 - so **an IBKR futures market-data
  subscription would buy nothing that is missing, and you should not buy one for this.**

  What is missing is **history retention**. IBKR keeps roughly **four expired quarters**
  (`ESU5` still serves 6,600 bars and 4.4M contracts of volume; `ESM5` and older return "no
  security definition"), and the continuous series is not a way around it - `reqHistoricalData`
  on a CONTFUT **refuses an `endDateTime` outright (error 10339)** and caps a 1-minute request
  at one month, so it cannot be paged backwards. The best stitch available is **313 cash
  sessions**, which is **16%** of the ~2,000 that A-4 measured as this repository's own power
  requirement - and A-10 is the standing lesson about ignoring that, having kept a strategy on
  260 IBKR sessions that 2,686 Alpaca sessions then killed at t = -7.38.

  **Why it is worth money, which is the part that changed.** Every intraday refusal in this
  repository was a refusal on **cost**, not on signal:

  | instrument | round trip | source |
  | --- | --- | --- |
  | **ES futures** | **0.488 bps** (0.856 at a full tick) | F-2a, measured |
  | MES futures | 0.744 bps | F-2a, measured |
  | F-1's intraday equity book | 0.892 bps of commission *alone*, at zero spread | F-1 |
  | X-1 megacap legs | 4.70 bps | X-1 |
  | L-1 leveraged ETFs | 6.40 - 8.20 bps | L-1 |

  F-1 found a genuinely real forecast (out-of-sample IC +0.0113 at t +4.74) and it died at
  0.797 gross bps against a 0.892 bps floor. **On ES that same forecast clears its floor by
  60%.** The futures instrument is **10x to 17x cheaper** than anything the loop has been
  allowed to trade, and that is a property of the contract rather than of a backtest.
  Separately, one ES contract carries $347k of notional whose cash-session gross sd is **0.62%
  before any leverage decision**, against 0.49% and 0.27% for the equity intraday books *after*
  theirs - the first instrument measured here where your 3-10%/day range is reachable without
  sizing up an unproven signal.

  **The ask, concretely**: historical CME futures data for **ES and NQ back to ~2016**, 1-minute
  or finer, e.g. **Databento MDP-3** (or any vendor that sells expired-contract history). Not an
  IBKR permission, not a market-data subscription. **What the loop has already built so it is
  ready the day it arrives**: `scripts/futures_data.py` (probe, retention audit, front-quarter
  stitch with an 8-day roll) and `scripts/sweep_f2.py` (the cost table above, the event study and
  the book). **What it will not do without the history**: propose a futures strategy. On the 313
  sessions available both pre-registered mechanisms were refused - overnight-into-the-open at
  t +0.78, day-momentum-into-the-close at t -2.56 with the premise's sign reversed - and the one
  positive cell is a post-hoc sign flip that this repository's own rules do not let it act on.
  Nothing is blocked today and nothing has been deployed.

  **Amendment (F-4, 2026-09-11) - one leg of the case above is withdrawn, and the cost table is
  not.** F-2a closed by arguing that an effect refused on cost becomes tradable on a 10x-17x
  cheaper instrument. F-4 tested that on the one effect it was offered for - the afternoon
  reversal - by holding the measured gross column fixed over **6,654,000 legs / 2,664 sessions**
  and swapping in ES's 0.488 bps round trip. **0 of 24 cells reach the pass mark and every one is
  still negative** (-0.37 to -2.73 bps), because on that sample the gross sign is **momentum, not
  reversal**: the directional book is positive at 12 of 12 entry minutes and the only gross
  statistics past |t| = 2 anywhere in the grid extend the day's move. So **a cheaper instrument
  rescues a mechanism only when the gross sign is right at |t| > 2** - otherwise it buys a smaller
  loss. What still stands, and is what the ask rests on: the **cost table itself** (a property of
  the contract), the **0.62% gross sd per contract** against your 3-10%/day mandate, and F-1's
  forecast, which was real at t +4.74 and would clear the ES floor by 60%. Read the request as
  "buy the instrument's economics", not "buy it to rescue the afternoon reversal".

  **Amendment (F-5, 2026-09-12) - the other half of that leg is withdrawn too, and the cost table
  still is not.** F-4 refused the reversal sign and reported that the *momentum* sign was the one
  with |t| > 2 gross, which by its own rule made it the candidate a 0.488 bps instrument could
  rescue. F-5 tested exactly that, on the object a future can hold - **SPY / QQQ / IWM minute
  bars, 2,687 sessions, 367,872 legs** - and **0 of 144 cells** pass, because the gross was mostly
  the market's own drift: the always-long book over the identical windows earns +0.54 of the +1.55
  bps, and the forecast that is left is **+1.01 bps at t +0.89**, negative in 2016-2019. The
  published market-intraday-momentum effect is not there either (**gross -0.19 / +0.10 / +0.05
  bps, |t| <= 0.73**). So neither sign of the day-move mechanism is a reason to buy CME history.
  **What the request still rests on is unchanged and is not a backtest**: the **0.488 bps round
  trip** (a property of the contract), the **0.62% cash-session gross sd per contract before any
  leverage**, against the 3-10%/day mandate, and **F-1's forecast**, which was real at t +4.74 and
  died 11% short of an equity commission floor the future clears by 60%. Nothing is blocked today.

  **Amendment (S-26, 2026-09-12) - a futures use has finally been found whose edge clears the
  0.488 bps round trip, it needs NO history at all, and it is refused on drawdown. Two things here
  are yours, and neither is a purchase.** S-25 showed all of the daily champion's measurable alpha
  is earned overnight and none of it intraday. S-26 acted on that the only way the arithmetic
  allows - not by trading the equity book (1,248x turnover, negative at zero cost) but by
  **shorting the index over the intraday leg**, sized on a causal trailing beta.
  - **It needs no CME purchase.** The overlay is priced on SPY's own open-to-close return, and
    that substitution was validated rather than assumed: over your own 313-session ES stitch,
    **corr(ES cash session, SPY open->close) = 0.9994, slope 0.9984, basis sd 2.1 bps/session**.
    So the request above stands on its own merits and this result neither adds to nor subtracts
    from it.
  - **The edge clears the instrument by a factor and dies on risk.** Charged 2 bp of equity spread,
    IBKR Pro financing and the 0.488 bps round trip, then vol-matched to the deployed book's own
    volatility, the half hedge earns **20.837% / Sharpe 1.100 against 19.640 / 1.047**, wins both
    halves and stays inside Reg-T - and **its drawdown is 26.0% against 24.0%**, two points worse
    against the 1.0-point tolerance you set on 2026-09-09, so the loop refused it. Its breakeven is
    **1.108 bps a round trip** against ES's 0.488. Nothing in the comparison reaches |t| = 2
    (paired +0.395 bps/day at t +0.60).
  - **DECISION 1, the only one that could change that verdict, and it is a risk-posture question
    so it is yours**: the refusal is the drawdown tolerance doing exactly what you asked it to do.
    If you want the cell judged instead on Sharpe and return with a wider drawdown allowance, say
    so and it goes back through `evaluate.py` on those criteria - **but read the t-statistic first;
    this is a +1.2 CAR point claim at t +0.60 on 3,689 sessions, which is not a result the loop
    would push.**
  - **DECISION 2, the offer that needs no leverage and no argument about significance**: the
    **un-relevered** half hedge earns **18.174% / Sharpe 1.124 / DD 22.45%** against the deployed
    **19.640% / 1.047 / 24.04%**. That is a straight trade of **1.47 CAR points for 1.58 points of
    drawdown and +0.08 of Sharpe**, with no extra leverage anywhere. It is priced, not recommended -
    your standing mandate is aggressive and return-first, which argues against it, and the loop will
    not change the book's risk posture on its own.
  - **What either decision would additionally require, stated so it is not discovered later**:
    consent to hold **futures** in the paper account at all (the loop has never held any, and
    AGENTS.md forbids it from changing what the runner trades without you), and enough equity for
    the hedge to be held continuously - the full hedge is **below one ES contract on 65.4% of
    sessions** on this book's $100k -> $899k path, so the practical instrument is **MES** at
    0.744 bps, which still clears the 1.108 breakeven.

  **Amendment (S-28, 2026-09-12) - the same trade, a third of the size, and with none of the
  requirements above. DECISION 3, and it is the cheapest thing in this file.** S-26 above buys
  drawdown with futures and Reg-T; S-28 buys it by changing **which returns the vol target is
  measured on** and nothing else. The book is sized `target_vol / sigma` and `sigma` has always
  been a close-to-close estimate, although `leg_note`/`risk_note` in `champion.json` show 94% of
  the return is overnight and 61% of the variance is the intraday leg that pays nothing. Measured
  on 59,662 name-observations, **every leg forecasts its own next-21-session volatility better
  than the pooled estimate does** (overnight->overnight 0.6764 against close-to-close->overnight
  0.6608), so the premise is real rather than rhetorical.
  - **The offer, at matched risk and the same 2 bp + IBKR Pro financing cost model**: the book
    sized on a causally level-matched **overnight** vol estimate earns **19.613% / Sharpe 1.046 /
    DD 21.93%** against the deployed **19.640% / 1.047 / DD 24.04%**. That is **the same return -
    paired -0.009 bps/day at t -0.08, a dead heat - for 2.1 points less drawdown**, on the same
    nine names, the same signal, the same turnover (196.8x against 195.6x equity a year) and the
    same gross. **It was refused by 0.027 CAR points**, which is the return-first rule you set on
    2026-09-09 doing exactly what you asked it to.
  - **Why it is cheaper than DECISION 1 and 2**: no futures, no instrument permission, no extra
    leverage, no change to your Reg-T buffer, and nothing new in the account - the deployed runner
    already reads the daily opens it needs. It is a one-line default in `signals.py`
    (`S1_VOL_RETURNS`, already built and gated by the I-1 order-list check, 3,689/3,689 PASS).
  - **What to read before saying yes, because the loop will not push this either**: the vol target
    rather than the margin budget sizes this book on only **2.8% of sessions** (4.7% under the new
    estimator), so the whole difference is a handful of crises - **-3.8 points on the 2022 drawdown
    against +0.7 points on the 2015-16 one** - and nothing in the comparison reaches |t| = 2. It
    **passes every criterion out of sample** (2020-2026: 26.007% vs 25.967%, DD 20.67 vs 24.04) and
    **fails in sample** (2012-2019: 14.254% vs 14.317%, DD 21.72 vs 20.94).
  - **The decision, in one sentence**: say whether "the same return at 2.1 points less drawdown"
    is worth 0.027 CAR points to you - that is the identical argument S-18 was promoted on, and
    under a return-first rule it is yours and not the loop's. Reproduce with
    `python scripts/sweep_s28.py`.

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
