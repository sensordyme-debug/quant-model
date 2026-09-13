# Express Funded Account (XFA)

**Rulebook version `2026.09.13` · retrieved 2026-09-13.**

What you get for passing a Combine. Still a simulated account — Topstep's own Payout Policy calls
traders here *"Research Analyst, the designation Topstep uses for Traders operating in the simulated
environment"* — but it pays real money at a 90/10 split.

Primary sources:
[8284215](https://help.topstep.com/en/articles/8284215-express-funded-account-parameters) ·
[8284223](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan) ·
[8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) ·
[topstep.com/express-funded-account-rules](https://www.topstep.com/express-funded-account-rules)

## Parameters

| | $50K | $100K | $150K |
|---|---|---|---|
| Starting balance | $0 | $0 | $0 |
| Maximum Loss Limit | $2,000 | $3,000 | $4,500 |
| MLL locks at | $0 balance-equivalent, once the balance reaches the MLL amount | | |
| Ceiling contracts | 5 / 50 | 10 / 100 | 15 / 150 |
| Actual contracts | **Scaling Plan, by current balance** — ladder not published | | |
| Daily Loss Limit | Optional: $1,000 | $2,000 | $3,000 |
| Payout cap, Standard | $2,000 | $3,000 | $5,000 |
| Payout cap, Consistency | $3,000 | $4,000 | $6,000 |
| Profit split | 90/10 | 90/10 | 90/10 |

*"Each Express Funded Account starts with a $0 balance"* and *"grows from your trading profits."*
Because the balance starts at $0, the MLL starts at **minus** the amount and locks at $0 once the
balance reaches that amount — e.g. on a $50K XFA, once the balance reaches $2,000 the MLL locks at
$0 permanently.

## Account limits

- Up to **5 active XFAs** at a time (1 only for Shoulder Tap account holders). Pass a Combine while
  at the limit and the new XFA is **held** until one closes.
- Each XFA runs its own payout cycle independently (`TS-PAY-15`).
- Running several accounts is permitted; running them *against each other* is not. See
  [PROHIBITED.md § Hedging](PROHIBITED.md#hedging--the-only-mechanically-enforced-conduct-rule) —
  the enforcement ladder is tracked at the **trader** level, so a violation in one account follows
  you into every account you own now or buy later.

## The Scaling Plan — documented, but not quantified

This is the largest open gap in the whole rulebook.

**What is known** (article 8284223, all `DOC`):

- *"The Scaling Plan is an Express Funded Account® (XFA) objective. It sets your Maximum Position
  Size — the max contracts you can hold at one time — based on your current account balance."*
- *"Your XFA starts at a $0 balance. As your balance grows, so does your buying power."*
- *"Your max contracts do not increase mid-session. Hit the threshold to release more buying power?
  Wait for the next session."*
- Minis and micros are fungible against the rung: *"Example — $50K XFA, 2-lot Scaling Plan: 2 Minis,
  OR 20 Micros, OR Any combo equal to 2 Minis"*
- *"Errors corrected in under 10 seconds are ignored. Leave too many contracts on for 10+ seconds
  and your account may be reviewed."*
- A payout that drops you a tier drops your size with it: *"If a Payout reduces your balance to a
  lower tier, your maximum contract size decreases accordingly."* (Payout Policy)
- The Scaling Plan applies **only to the XFA**. In the LFA it was superseded by Dynamic Live Risk
  Expansion — see [LFA.md](LFA.md).

**What is not known:** the ladder itself. The balance→contracts table is published as an embedded
image (`XFA charts - hc.png`) with no text equivalent, no alt text, and no caption. Every text
extraction of article 8284223, article 8284215, and
`topstep.com/express-funded-account-rules` returned the prose above and no tier numbers. Multiple
search formulations returned the same prose and no numbers.

**Consequence, and the direction of the error.** An XFA simulated at the *ceiling* contract count
(5 / 10 / 15) will size far too large at low balances — and low balance is exactly the state a fresh
XFA is in, because it starts at $0. That error **flatters** results: it is the direction that turns
a marginal edge into an apparent one. `topstep.py` gets this right by leaving `XFA_SCALING` empty and
recording it as a gap rather than assuming the ceiling.

**Action required before any XFA is traded or simulated:** read the ladder off the dashboard or the
chart image and populate it. Until then the XFA size model is `OWNER` tier and any XFA backtest is
not admissible evidence.

## Payout paths

Two, chosen per account. Full detail in [PAYOUTS.md](PAYOUTS.md).

| | Standard | Consistency |
|---|---|---|
| Days required | 5 winning days of **$150+ net P&L**, non-consecutive | 3 trading days with **≥1 trade** each |
| Extra condition | Positive net profit ($0.01) since the last payout; first payout exempt | Largest single day ≤ **40%** of total net profit |
| Cap by size | $2,000 / $3,000 / $5,000 | $3,000 / $4,000 / $6,000 |
| Both | 50% of balance, whichever is less; $125 minimum; 90/10 split | |

Exceeding 40% on the Consistency path does not fail anything — *"keep trading. As you earn more net
profit, the percentage will naturally come down."* It blocks the payout and nothing else.

> **Correction to prior work.** `topstep.py` sets `XFA_STANDARD_CAP = 5_000` and
> `XFA_CONSISTENCY_CAP = 6_000` for **every** size. Those are the **$150K** figures. A $50K XFA caps
> at $2,000 / $3,000 — the module overstates a $50K payout by up to 2.5x, and that is the
> flattering direction. The Payout Policy's per-size table is the authority; article 8284215's
> generic *"up to $5,000"* / *"up to $6,000"* wording is the largest-size case stated without its
> qualifier.

## Costs

- Activation fee: **$149** once per XFA earned (Standard path) or **$0** (No Activation Fee path).
- No monthly subscription once funded.
- Back2Funded reactivation within 30 days of losing a funded account: **$599 / $699 / $829**, max 2
  reactivations, 7-day activation window.

## What ends an XFA

| Event | Consequence |
|---|---|
| MLL breach | **Permanent closure** of that XFA. Harsher than the Combine, where a breach only costs a reset. Back2Funded may apply. |
| Full 100% payout | Closes the account (balance reaches the MLL) |
| Confirmed hedging violation | Permanent closure, **no appeal**, and unpaid profits are forfeited |
| DLL hit (if enabled) | Temporary violation only; lifts next session |

## Simulation notes

- Starting balance is **$0**, so `total_profit == balance` and the MLL is negative until the balance
  clears the MLL amount. Any code that assumes a positive opening balance is wrong here.
- After the first payout the MLL is **$0 permanently** and the remaining balance is the whole risk
  budget. This makes payout timing a genuine risk decision: taking a payout shrinks the distance to
  the floor by the amount withdrawn and the floor does not follow it down.
- The Consistency path's denominator resets at each payout, so consistency must be tracked
  **per payout period**, not per account lifetime.
- Do not simulate an XFA at ceiling size (see the Scaling Plan gap above).
