# Topstep — master rule table

**Rulebook version `2026.09.13` · retrieved 2026-09-13 · all sources Topstep-owned.**

## How to read this table

**Enforcement**

| Class | Meaning | Simulator obligation |
|---|---|---|
| `HARD` | Breach ends the account (liquidation, closure, or failure of the evaluation) | Must be an absorbing terminal state |
| `SOFT` | Breach blocks a payout, raises a target, or forces a pause. The account survives. | Must gate the reward, never the survival |
| `ADMIN` | Cost, eligibility, or conduct review. Topstep applies discretion; outcomes range from a warning to permanent closure. | Must be a constraint on the *strategy design*, not a runtime check |

**Affects** — `R` research (which strategies are worth studying) · `S` simulation (backtest
accounting) · `E` execution (what the live runner must do or refuse)

**Tier** — `DOC` / `SEARCH` / `OWNER` as defined in [README.md](README.md#confidence-tiers).

---

## 1. Account parameters

| ID | Rule | Value | Enforce | Affects | Tier | Source |
|---|---|---|---|---|---|---|
| `TS-CMB-01` | Combine profit target | $50K → $3,000 · $100K → $6,000 · $150K → $9,000 | SOFT (pass condition) | R S | DOC | [no-activation-fee](https://www.topstep.com/no-activation-fee) + [topstep-prop](https://www.topstep.com/topstep-prop) |
| `TS-CMB-02` | Combine monthly cost, Standard path | $49 / $99 / $199 | ADMIN | R | DOC | [14289835](https://help.topstep.com/en/articles/14289835-topstep-pricing-and-payment-questions) |
| `TS-CMB-03` | Combine monthly cost, No Activation Fee path | $95 / $149 / $229 | ADMIN | R | DOC | [14289835](https://help.topstep.com/en/articles/14289835-topstep-pricing-and-payment-questions) |
| `TS-CMB-04` | Reset cost | Equals the monthly cost for that size and path | ADMIN | R | DOC | [14289835](https://help.topstep.com/en/articles/14289835-topstep-pricing-and-payment-questions) |
| `TS-CMB-05` | XFA activation fee | $149 once per XFA earned (Standard path); $0 (No Activation Fee path) | ADMIN | R | DOC | [14289835](https://help.topstep.com/en/articles/14289835-topstep-pricing-and-payment-questions) |
| `TS-CMB-06` | Max position size | 5 mini / 50 micro · 10 / 100 · 15 / 150 | HARD (order rejected) | S E | DOC | [8284197](https://help.topstep.com/en/articles/8284197-trading-combine-parameters) |
| `TS-CMB-07` | Path is locked at purchase | *"Paths cannot be changed after purchase"* | ADMIN | R | DOC | [14289835](https://help.topstep.com/en/articles/14289835-topstep-pricing-and-payment-questions) |
| `TS-CMB-08` | Reset purchase limit | *"2 Resets"* per account per calendar day; no limit on Combine purchases | ADMIN | R | DOC | [10370307](https://help.topstep.com/en/articles/10370307-account-purchase-limits) |
| `TS-CMB-09` | Account size locked after passing | Size is fixed once the Combine is passed | ADMIN | R | DOC | [8284215](https://help.topstep.com/en/articles/8284215-express-funded-account-parameters) |

## 2. Maximum Loss Limit (MLL)

| ID | Rule | Value | Enforce | Affects | Tier | Source |
|---|---|---|---|---|---|---|
| `TS-MLL-01` | MLL amount | $2,000 / $3,000 / $4,500 | HARD | S E | DOC | [8284204](https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit) |
| `TS-MLL-02` | Trails on end-of-day balance only | *"It rises as your end-of-day balance grows, but never moves down."* | HARD | S E | DOC | [8284204](https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit) |
| `TS-MLL-03` | Breach is tested intraday on unrealized P&L | *"if your balance touches or falls below a limit at any point, it's a violation and liquidation triggers immediately"*; the system monitors *"real-time unrealized P&L"* | HARD | S E | DOC | [8284204](https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit) |
| `TS-MLL-04` | Locks at the starting balance | Once the threshold reaches the starting balance it stops trailing, permanently | HARD | S E | DOC | [8284204](https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit) |
| `TS-MLL-05` | Breach consequence differs by stage | Combine: liquidated for the day, ineligible for funding until reset. XFA: **permanent closure** (Back2Funded may apply). | HARD | S E | DOC | [8284204](https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit) |
| `TS-MLL-06` | MLL goes to $0 after the first payout | *"Your MLL is set to $0 after your first Payout. If it's already at $0, it stays there. The remaining balance becomes your effective loss floor."* | HARD | S E | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |

> `TS-MLL-02` and `TS-MLL-03` together are the rule that does not fit a generic prop-firm model:
> the *threshold* advances end-of-day, the *breach* is tested intraday including unrealized P&L.
> `topstep.py` already models this as `TrailingMode.EOD_TRAIL_INTRADAY_BREACH` and that remains
> correct.

## 3. Daily Loss Limit (DLL)

| ID | Rule | Value | Enforce | Affects | Tier | Source |
|---|---|---|---|---|---|---|
| `TS-DLL-01` | DLL amount (Combine / XFA) | $1,000 / $2,000 / $3,000 | SOFT | S E | DOC | [10490293](https://help.topstep.com/en/articles/10490293-daily-loss-limit-in-the-trading-combine-and-express-funded-account) |
| `TS-DLL-02` | Optional in Combine and XFA, automatic in LFA | — | SOFT | S E | DOC | [10490293](https://help.topstep.com/en/articles/10490293-daily-loss-limit-in-the-trading-combine-and-express-funded-account) |
| `TS-DLL-03` | Hitting the DLL is not a violation | *"Open positions are flattened"*, *"Pending orders are canceled"*, *"No new trades until 5 PM CT next session"*. Account stays eligible for funding. | SOFT | S E | DOC | [10490293](https://help.topstep.com/en/articles/10490293-daily-loss-limit-in-the-trading-combine-and-express-funded-account) |
| `TS-DLL-04` | Trading-day window | 5:00 PM CT → 3:10 PM CT | SOFT | S E | DOC | [10490293](https://help.topstep.com/en/articles/10490293-daily-loss-limit-in-the-trading-combine-and-express-funded-account) |
| `TS-DLL-05` | A DLL hit blocks a payout that day | *"Hitting the Daily Loss Limit puts your account in a Temporary Violation. It lifts at the start of the next trading session."* | SOFT | E | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-DLL-06` | Voluntary DLL doubles the payout cap | Limited-time offering; see `TS-PAY-04` | SOFT | R | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |

## 4. Consistency

| ID | Rule | Value | Enforce | Affects | Tier | Source |
|---|---|---|---|---|---|---|
| `TS-CON-01` | Combine consistency threshold | **55%** — *"55% is a hard line. It is not rounded, and there is no buffer."* | SOFT | R S | DOC | [8284208](https://help.topstep.com/en/articles/8284208-consistency-at-topstep) |
| `TS-CON-02` | Combine consistency denominator | **Total profit** — formula *"Best Day Profit ÷ Total Profit = Best Day %"*, worked example *"$1,600 best day ÷ $3,000 total profit = 53%"* | SOFT | R S | DOC | [8284208](https://help.topstep.com/en/articles/8284208-consistency-at-topstep) |
| `TS-CON-03` | Exceeding it raises the target, does not fail the account | *"If it exceeds that, your Profit Target increases. You'll need to earn more to pass."* The size of the increase is not published. | SOFT | R S | DOC | [8284208](https://help.topstep.com/en/articles/8284208-consistency-at-topstep) |
| `TS-CON-04` | XFA consistency-path threshold | **40%** — *"Your Consistency % must be 40% or below to be Payout eligible."* | SOFT | R S E | DOC | [8284208](https://help.topstep.com/en/articles/8284208-consistency-at-topstep) |
| `TS-CON-05` | XFA consistency denominator | *"Largest Single-Day Net Profit ÷ Total Net Profit = Consistency %"* | SOFT | R S E | DOC | [8284208](https://help.topstep.com/en/articles/8284208-consistency-at-topstep) |
| `TS-CON-06` | Consistency implies a 2-day minimum | Not a stated rule. A single trading day makes Best Day / Total Profit = 100% > 55%, so the Combine cannot be passed in one day. | SOFT | R S | DOC (derived) | derived from `TS-CON-01` + `TS-CON-02` |

### The 50%-vs-55% question, resolved

The brief flagged article 8284208 as contradicting itself. It does — *"55% of your Profit Target"*
in the threshold sentence against *"Best Day Profit ÷ Total Profit"* in the calculation line. Three
pieces of evidence resolve it in favour of **55% of total profit**:

1. The same page's **worked example** divides by total profit: *"$1,600 best day ÷ $3,000 total
   profit = 53%"*. An example is a stronger signal than a prose sentence, because it is the form the
   dashboard actually computes.
2. [Program Overview 8284099](https://help.topstep.com/en/articles/8284099-topstep-program-overview)
   states the objective as *"best trading day ≤55% of total profits"* — threshold **and**
   denominator, in one sentence, on a different page.
3. [topstep.com/topstep-prop](https://www.topstep.com/topstep-prop) states a *"55% consistency
   target"* for all account sizes.

The 50% figure in the owner brief is not supported by any page reached on 2026-09-13. One search
summary echoed a 50% sentence, but no fetched page carried it; treat 50% as stale.
`topstep.py`'s `doc_calc` reading — `(0.55, "total")` — is the correct one, and its default `strict`
reading `(0.50, "total")` should be retired.

## 5. Trading hours and mandatory flat times

| ID | Rule | Value | Enforce | Affects | Tier | Source |
|---|---|---|---|---|---|---|
| `TS-HRS-01` | Week open | Sunday 5:00 PM CT | HARD | S E | DOC | [8284206](https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade) |
| `TS-HRS-02` | Daily close / mandatory flat | 3:10 PM CT every weekday | HARD | S E | DOC | [8284206](https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade) |
| `TS-HRS-03` | Daily reopen | 5:00 PM CT | HARD | S E | DOC | [8284206](https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade) |
| `TS-HRS-04` | Friday close | 3:10 PM CT, closed until Sunday 5:00 PM CT | HARD | S E | DOC | [8284206](https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade) |
| `TS-HRS-05` | Auto-flatten begins before the bell | Positions and pending orders *"begin to automatically cancel"* at 3:10 PM CT; the ToU says flattening happens *"about ten seconds prior to the closing bell at 3:10 PM CT"* | HARD | E | DOC | [8284206](https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade), [ToU](https://www.topstep.com/terms-of-use) |
| `TS-HRS-06` | Do not open after 3:08 PM CT | *"Avoid opening new positions after 3:08 PM CT — Risk Managers begin flattening at that time. It's still your responsibility to be flat by 3:10 PM CT."* | SOFT | E | DOC | [8284206](https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade) |
| `TS-HRS-07` | Products closing earlier than 3:10 PM CT | *"you must exit before that product's close"* | HARD | S E | DOC | [8284206](https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade) |
| `TS-HRS-08` | No swing trading, no overnight, no Forex | *"Topstep is a day trading program. No swing trading. No Forex."* | HARD | R S E | DOC | [8284206](https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade) |
| `TS-HRS-09` | CBOT grains session | Sun–Mon 7:00 PM – 7:45 AM CT; Mon–Fri 8:30 AM – 1:20 PM CT | HARD | S E | DOC | [8284206](https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade) |
| `TS-HRS-10` | CBOT grain pause | Mon–Fri 7:45–8:30 AM CT, no orders accepted; TopstepX manual lockout unavailable for CBOT positions held through it | HARD | E | DOC | [8284206](https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade) |
| `TS-HRS-11` | CME livestock session | Mon–Fri 8:30 AM – 1:05 PM CT (Live Cattle, Lean Hogs) | HARD | S E | DOC | [8284206](https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade) |
| `TS-HRS-12` | Early-close holidays | *"Close all positions 15 minutes before early close (e.g., close by 11:45 CT for a 12:00 CT close)"*. Applies to Combine, XFA and LFA. Open positions at the cutoff are auto-liquidated. | HARD | S E | DOC | [13350348](https://help.topstep.com/en/articles/13350348-topstep-holiday-trading-hours) |
| `TS-HRS-13` | CME blended trade dates | On some holidays CME merges calendar days into one session, so the DLL applies to the whole blended window. **Only LFA on TopstepX follows CME Protocol blending;** Combine and XFA treat each calendar day independently. | HARD | S E | DOC | [13350348](https://help.topstep.com/en/articles/13350348-topstep-holiday-trading-hours) |
| `TS-HRS-14` | No payouts during holiday hours | *"Payouts are not available during holiday hours"* | SOFT | E | DOC | [13350348](https://help.topstep.com/en/articles/13350348-topstep-holiday-trading-hours) |
| `TS-HRS-15` | Payout request window | *"Available during CME market hours: Sunday 5 PM CT – Friday 5 PM CT (excluding holidays)"* | SOFT | E | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |

> The permitted-product list is reproduced in [PROHIBITED.md § Permitted products](PROHIBITED.md#permitted-products).

## 6. Scaling and dynamic risk

| ID | Rule | Value | Enforce | Affects | Tier | Source |
|---|---|---|---|---|---|---|
| `TS-SCL-01` | The Scaling Plan exists and binds the XFA | *"It sets your Maximum Position Size — the max contracts you can hold at one time — based on your current account balance."* | HARD | S E | DOC | [8284223](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan) |
| `TS-SCL-02` | Size increases only at a session boundary | *"Your max contracts do not increase mid-session. Hit the threshold to release more buying power? Wait for the next session."* | HARD | S E | DOC | [8284223](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan) |
| `TS-SCL-03` | XFA starts at the lowest rung | *"Your XFA starts at a $0 balance. As your balance grows, so does your buying power."* | HARD | S E | DOC | [8284223](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan) |
| `TS-SCL-04` | Minis and micros are fungible against the rung | *"Example — $50K XFA, 2-lot Scaling Plan: 2 Minis, OR 20 Micros, OR Any combo equal to 2 Minis"* | HARD | S E | DOC | [8284223](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan) |
| `TS-SCL-05` | 10-second grace on an over-size error | *"Errors corrected in under 10 seconds are ignored. Leave too many contracts on for 10+ seconds and your account may be reviewed."* | ADMIN | E | DOC | [8284223](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan) |
| `TS-SCL-06` | A payout can demote you a rung | *"If a Payout reduces your balance to a lower tier, your maximum contract size decreases accordingly."* | HARD | S E | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| **`TS-SCL-07`** | **The ladder itself — balance thresholds → contracts** | **NOT PUBLISHED AS TEXT.** See [§ Not found](#not-found-on-any-official-page). | HARD | S E | **OWNER** | image `XFA charts - hc.png` on [8284223](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan) |
| `TS-SCL-08` | High-volatility position cuts | Mini limits cut to 3/6/9 for CL, GC, HO, RB; **SI cut to 0 minis**. Triggered by *"Expanding price limits"*, *"Velocity Logic halts"*, *"Historic price ranges"*, *"Rapid, sustained price movement"*. | HARD | S E | DOC | [13613539](https://help.topstep.com/en/articles/13613539-risk-adjustments-high-risk-high-volatility) |
| `TS-SCL-09` | CPI blackout | 10-minute window (5 min before, 5 min after). Equity index **minis (ES, RTY, YM, NQ, NKD): no new opening transactions.** Micros capped at 1/3/6/9/15 by size. | HARD | R S E | DOC | [13613539](https://help.topstep.com/en/articles/13613539-risk-adjustments-high-risk-high-volatility) |
| `TS-SCL-10` | Restrictions are temporary and notified out-of-band | Notified by email, dashboard banner, and @AskTopstep | ADMIN | E | DOC | [13613539](https://help.topstep.com/en/articles/13613539-risk-adjustments-high-risk-high-volatility) |

> `TS-SCL-09` is the one that most directly threatens an intraday equity-index strategy: a hard
> no-new-minis window around every CPI print, announced only through channels a runner does not read.

## 7. Payouts

Full mechanics in [PAYOUTS.md](PAYOUTS.md). Summary rows:

| ID | Rule | Value | Enforce | Affects | Tier | Source |
|---|---|---|---|---|---|---|
| `TS-PAY-01` | Profit split | 90/10 to the trader | SOFT | R | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-PAY-02` | Minimum payout | $125 | SOFT | E | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-PAY-03` | Per-request cap, XFA | 50% of balance, capped at $2,000/$3,000/$5,000 (Standard) or $3,000/$4,000/$6,000 (Consistency) by size | SOFT | R S E | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-PAY-04` | Voluntary-DLL cap doubling | Caps double to $4,000/$6,000/$10,000 and $6,000/$8,000/$12,000. Limited-time offering. | SOFT | R | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-PAY-05` | XFA Standard eligibility | 5 winning days of $150+ net P&L, non-consecutive, **and** positive net profit ($0.01) since the last payout (first payout exempt) | SOFT | R S E | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-PAY-06` | XFA Consistency eligibility | 3 trading days with ≥1 trade each, **and** consistency ≤40% | SOFT | R S E | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-PAY-07` | A day locks at 4:00 PM CT | *"A day locks in at 4:00 PM CT."* | SOFT | S E | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-PAY-08` | The request day is excluded from the next cycle | *"The trading day your Payout is requested doesn't count toward your next 5."* A request after 5:00 PM CT belongs to the **next** trading day. | SOFT | S E | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-PAY-09` | What a payout resets | MLL → $0 permanently; day count restarts; consistency calculation resets (Consistency path) | HARD + SOFT | S E | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-PAY-10` | LFA payouts are uncapped in dollars | 5 winning days of $150+ per cycle, up to 50% of balance, no dollar cap | SOFT | R S | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-PAY-11` | LFA daily payouts after 30 winning days | *"request as much of your unlocked balance as you want, once per day (min $125)"* | SOFT | R S | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-PAY-12` | A 100% LFA payout closes the account | *"Requesting a full 100% Payout closes your LFA since the balance reaches the Maximum Loss Limit."* | HARD | E | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-PAY-13` | Copy trading is disabled during processing | Must be **manually** re-enabled after the deduction completes | ADMIN | E | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-PAY-14` | Payout review covers conduct, not just arithmetic | Reviewed against the Payout Policy, Prohibited Conduct, Terms of Use, Professional Behavior, and Prohibited Trading Strategies | ADMIN | R E | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |
| `TS-PAY-15` | Each XFA pays out independently | *"Each XFA follows its own Payout Policy independently. Requests from one account don't affect another."* | SOFT | S | DOC | [8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) |

## 8. Prohibited conduct and strategies

Full text in [PROHIBITED.md](PROHIBITED.md). Every row here is `ADMIN` in the sense that Topstep
applies discretion — but the discretion runs up to *"Permanent account closure"* and *"Delay or
denial of a Payout request"*, so for research purposes these are **design-time hard constraints**.

| ID | Rule | Enforce | Affects | Tier | Source |
|---|---|---|---|---|---|
| `TS-PRH-01` | Account stacking — burn one account's MLL, switch, repeat | ADMIN→HARD | R | DOC | [10305426](https://help.topstep.com/en/articles/10305426-prohibited-trading-strategies-at-topstep), [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) |
| `TS-PRH-02` | Unfair technology — *"software, AI, ultra-high speed systems, or mass data entry"* | ADMIN→HARD | R E | DOC | [10305426](https://help.topstep.com/en/articles/10305426-prohibited-trading-strategies-at-topstep) |
| `TS-PRH-03` | Trading outside the best bid or offer | ADMIN→HARD | E | DOC | [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) |
| `TS-PRH-04` | Price exploitation — exploiting price-display errors or data-feed delays | ADMIN→HARD | R E | DOC | [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) |
| `TS-PRH-05` | Using an external or slow data feed to trade | ADMIN→HARD | E | DOC | [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) |
| `TS-PRH-06` | Disruptive practices, including spoofing | ADMIN→HARD | E | DOC | [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) |
| `TS-PRH-07` | Exploiting platform deficiencies — bugs, errors, deficiencies | ADMIN→HARD | R E | DOC | [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) |
| `TS-PRH-08` | Cross-account hedging (single user) — opposite positions across accounts | **HARD** (escalating; see below) | R S E | DOC | [13747047](https://help.topstep.com/en/articles/13747047-understanding-hedging) |
| `TS-PRH-09` | Coordinated trading with others — pooling or hedging aggregate risk | ADMIN→HARD | R | DOC | [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) |
| `TS-PRH-10` | Max position size into a scheduled major news event | ADMIN→HARD | R S E | DOC | [10305426](https://help.topstep.com/en/articles/10305426-prohibited-trading-strategies-at-topstep) |
| `TS-PRH-11` | Holding within 2% of a product's price lock limit | ADMIN→HARD | S E | DOC | [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct), [8284225](https://help.topstep.com/en/articles/8284225-staying-outside-the-2-price-limit-zone) |
| `TS-PRH-12` | SIM exploitation — scalping algos on unrealistic fills, hundreds of rapid trades for queue position, gap-fill hunting, exploiting the lack of slippage, tight brackets / auto-breakeven on favourable SIM fills | ADMIN→HARD | **R S E** | DOC | [10305426](https://help.topstep.com/en/articles/10305426-prohibited-trading-strategies-at-topstep) |
| `TS-PRH-13` | Trading inconsistent with real futures markets | ADMIN→HARD | R | DOC | [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) |
| `TS-PRH-14` | No VPN, proxy, TOR, or geo-obfuscation | ADMIN→HARD | E | DOC | [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) |
| `TS-PRH-15` | Trading on behalf of others / sharing incentives | ADMIN→HARD | R | DOC | [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) |
| `TS-PRH-16` | Intentionally depleting an LFA balance | ADMIN→HARD | R | DOC | [10305426](https://help.topstep.com/en/articles/10305426-prohibited-trading-strategies-at-topstep) |
| `TS-PRH-17` | Chargebacks or payment disputes | ADMIN→HARD | — | DOC | [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) |
| `TS-PRH-18` | Excessive purchases of Combines or Resets | ADMIN | R | DOC | [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) |
| `TS-PRH-19` | Multiple profiles | ADMIN→HARD | — | DOC | [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) |
| `TS-PRH-20` | Catch-all: conduct Topstep deems *"uncommercial, games the market, is not a viable strategy, or is not responsible trading"*, at its **sole discretion** | ADMIN→HARD | R | DOC | [10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) |

`TS-PRH-08` is the only prohibited-conduct rule with a **published, mechanical, real-time**
enforcement ladder rather than a case-by-case review — warning modal → same-day liquidation →
mandatory acknowledgement → immediate liquidation → temporary day-long violation → permanent
closure. It is also **not appealable** and closed accounts **forfeit unpaid profits**. It is tracked
at the *trader* level, not the account level. See
[PROHIBITED.md § Hedging](PROHIBITED.md#hedging--the-only-mechanically-enforced-conduct-rule).

## 9. Responsible Trading Program

| ID | Rule | Value | Enforce | Affects | Tier | Source |
|---|---|---|---|---|---|---|
| `TS-RTP-01` | Placement is at Topstep's initiative | Triggered by *"trading behavior that isn't sustainable in live markets"* | ADMIN | R | DOC | [13620045](https://help.topstep.com/en/articles/13620045-what-is-the-responsible-trading-program) |
| `TS-RTP-02` | Trigger behaviours | Multiple accounts hitting MLLs daily; maxing position size on most trades; losses larger than winners; no stop losses; full-portfolio or impulsive trades; disregarding daily limits | ADMIN | R | DOC | [13620045](https://help.topstep.com/en/articles/13620045-what-is-the-responsible-trading-program) |
| `TS-RTP-03` | While enrolled: DLL is mandatory | Every new Combine gets a DLL ($1,000 / $2,000 / $3,000) | SOFT | S E | DOC | [13620045](https://help.topstep.com/en/articles/13620045-what-is-the-responsible-trading-program) |
| `TS-RTP-04` | While enrolled: Consistency path only | *"best day must stay under 40% of total profits per Payout period"*. Standard XFA is unavailable. | SOFT | R S E | DOC | [13620045](https://help.topstep.com/en/articles/13620045-what-is-the-responsible-trading-program) |
| `TS-RTP-05` | Payouts while enrolled | Up to $6,000 every 3 trading days, consistency permitting | SOFT | R | DOC | [13620045](https://help.topstep.com/en/articles/13620045-what-is-the-responsible-trading-program) |
| `TS-RTP-06` | Exit condition | Reach an LFA and generate **$10,000** of profit in it. No set timeline. | ADMIN | R | DOC | [13620045](https://help.topstep.com/en/articles/13620045-what-is-the-responsible-trading-program) |

> This program is the single largest *tail risk to the research plan itself*. A high-turnover
> automated strategy that maxes size and runs several accounts is a near-exact match for
> `TS-RTP-02`, and enrolment is not a breach anyone appeals — it silently converts the whole
> program to the Consistency path with a mandatory DLL and an exit condition ($10K of **live**
> profit) that most accounts never reach.

## 10. Professional behaviour

| ID | Rule | Enforce | Tier | Source |
|---|---|---|---|---|
| `TS-PRO-01` | Excessive use of XFAs and trading irresponsibly within them | ADMIN | DOC | [10290170](https://help.topstep.com/en/articles/10290170-professional-behavior-at-topstep) |
| `TS-PRO-02` | Constantly asking for Resets, freebies, or exceptions | ADMIN | DOC | [10290170](https://help.topstep.com/en/articles/10290170-professional-behavior-at-topstep) |
| `TS-PRO-03` | Promo-code abuse | ADMIN | DOC | [10290170](https://help.topstep.com/en/articles/10290170-professional-behavior-at-topstep) |
| `TS-PRO-04` | Excessive support tickets or calls | ADMIN | DOC | [10290170](https://help.topstep.com/en/articles/10290170-professional-behavior-at-topstep) |
| `TS-PRO-05` | Rudeness, toxicity, threats of bad reviews, posting private correspondence, falsified screenshots | ADMIN | DOC | [10290170](https://help.topstep.com/en/articles/10290170-professional-behavior-at-topstep) |

---

## Not found on any official page

The seven priorities from the brief, scored. Four closed outright, two closed with a caveat, one open.

| # | Item | Status | Detail |
|---|---|---|---|
| 1 | Prohibited strategies / conduct | **CLOSED** | Two dedicated articles found (10305426, 10296582) plus ToU §27, a hedging policy (13747047), professional behaviour (10290170), and the 2% price-limit rule (8284225). 20 rules captured. |
| 2 | Permitted hours and mandatory flat times | **CLOSED** | 15 rules including per-product sessions, the 3:08/3:10 pair, the CBOT pause, and holiday early-close + CME blending. |
| 3 | Scaling plan ladder | **OPEN** | The plan is documented, its *rungs are not*. Published only as the image `XFA charts - hc.png` on article 8284223, which no text extraction reaches. The only numeric datapoint anywhere is the illustrative *"$50K XFA, 2-lot Scaling Plan"*. **Still `OWNER` tier — read it off the dashboard before an XFA is traded.** |
| 4 | Payout mechanics | **CLOSED** | 15 rules. Frequency, per-size caps, the DLL cap-doubling offer, the $0.01 profit gate, the 4:00 PM CT day lock, the request-day exclusion, the MLL→$0 reset, LFA daily payouts after 30 days, methods and fees. |
| 5 | Combine profit target and monthly cost | **CLOSED** | Target $3,000/$6,000/$9,000 on two Topstep-owned pages. Cost $49/$99/$199 (Standard) and $95/$149/$229 (No Activation Fee) from the help-centre pricing article. One unresolved discrepancy in the No-Activation-Fee row — see [COMBINE.md § Pricing](COMBINE.md#pricing). |
| 6 | Responsible Trading Program | **CLOSED** | Article 13620045, 6 rules. |
| 7 | Consistency 50% vs 55% | **CLOSED** | 55% of **total profit**. Resolved by the worked example on 8284208 plus corroboration on 8284099 and topstep.com/topstep-prop. See [§4](#the-50-vs-55-question-resolved). |

### Also searched for and not found

| Item | Status |
|---|---|
| An **8-day** payout variant | No 8-day rule appears in the current Payout Policy. The two live paths are 5-day Standard and 3-day Consistency. Either superseded or never a Topstep rule. |
| A minimum-trading-days rule for the Combine | No explicit rule on any page. `TS-CON-06` derives a floor of 2 days from the consistency arithmetic. |
| The size of the consistency profit-target increase (`TS-CON-03`) | Stated to happen, never quantified. Remains `OWNER`. |
| Copy-trading account limits as a *rule* | Search summaries mention a $750K buying-power ceiling via trade copier and that the LFA cannot use one, but neither was confirmed on a fetched page. `SEARCH` tier — do not rely on it. |
| Combine starting cash balance | Still not stated anywhere. Immaterial: every Topstep quantity is relative to the start (see the `topstep.py` module docstring). |
| A published news-event calendar or blackout list beyond CPI | Only CPI is named with an explicit window. Everything else falls under the discretionary `TS-PRH-10`. |
