# Payouts

**Rulebook version `2026.09.13` · retrieved 2026-09-13.**

Primary source: [Topstep Payout Policy, article
8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy). Where another page is
used it is named inline.

Every rule here is `SOFT` unless marked otherwise: failing a payout condition blocks the money, it
does not end the account. The two exceptions are marked `HARD` and both concern the MLL.

## The basics

- Requested from the Topstep Dashboard, in the **XFA** and **LFA** only.
- *"Available during CME market hours: Sunday 5 PM CT – Friday 5 PM CT (excluding holidays)"*.
  Payouts are **not** available during holiday hours
  ([13350348](https://help.topstep.com/en/articles/13350348-topstep-holiday-trading-hours)).
- **Minimum payout: $125.**
- **90/10 split**, trader keeps 90%.
- Legacy: traders who joined the new dashboard before **12 January 2026** *"receive 100% of your
  first $10,000 in lifetime profits. After that, the 90/10 split applies."*

## Eligibility

### XFA Standard — both conditions required

1. **5 winning days of $150+ net P&L.** *"Days don't need to be consecutive. A day locks in at
   4:00 PM CT. The trading day your Payout is requested doesn't count toward your next 5."*
2. **Positive net profit since the last payout.** *"You must have earned at least $0.01 since your
   last Payout. Your first Payout is exempt."*

### XFA Consistency — both conditions required

1. **3 trading days with at least 1 trade each.**
2. **Consistency ≤ 40%.** *"Your largest single day cannot exceed 40% of your total net profit. Days
   lock in at 4:00 PM CT. The trading day your Payout is requested doesn't count toward your next 3."*

### LFA

- **5 winning days of $150+ net P&L** per cycle, non-consecutive.
- After **30 non-consecutive winning days** of $150+ in the LFA, **daily payouts** unlock: *"request
  as much of your unlocked balance as you want, once per day (min $125)."*

## Caps

Per request: **50% of the account balance**, capped by size and path.

| Account size | XFA Standard | XFA Consistency |
|---|---|---|
| $50K | $2,000 | $3,000 |
| $100K | $3,000 | $4,000 |
| $150K | $5,000 | $6,000 |

*"Payout caps apply to XFA accounts only. Live Funded Account Payouts are not capped."*

### Limited-time: voluntary DLL doubles the cap

*"Traders who voluntarily add a Daily Loss Limit to their account unlock double per-request payout
caps."*

| Account | Path | Current cap | With DLL |
|---|---|---|---|
| $50K | Standard | $2,000 | $4,000 |
| $50K | Consistency | $3,000 | $6,000 |
| $100K | Standard | $3,000 | $6,000 |
| $100K | Consistency | $4,000 | $8,000 |
| $150K | Standard | $5,000 | $10,000 |
| $150K | Consistency | $6,000 | $12,000 |

This is a **limited-time offering** and must be re-checked at each rulebook version bump. It is the
one rule in this document that makes accepting a *tighter* risk constraint strictly profitable, and
it is worth modelling both ways.

> **Two internal inconsistencies on the source page, for the record.** The page's own "2 paths"
> summary says *"Request 50% of the account balance up to $5000"* (Standard) and *"up to $6,000"*
> (Consistency) with no size qualifier — those are the **$150K** rows quoted as if universal.
> Article 8284215 repeats the same unqualified phrasing. The per-size table above is more specific
> and is treated as authoritative.

## What a payout resets

| | XFA Standard | XFA Consistency | LFA |
|---|---|---|---|
| MLL | **→ $0 permanently** (`HARD`) | **→ $0 permanently** (`HARD`) | — |
| Day count | restarts | restarts | restarts |
| Consistency calculation | n/a | **resets** | n/a |
| Request day | excluded from the next cycle | excluded from the next cycle | excluded |

*"Your MLL is set to $0 after your first Payout. If it's already at $0, it stays there. The
remaining balance becomes your effective loss floor."*

This is the payout rule with the largest effect on risk and the one `topstep.py` does not model at
all. The balance falls by the amount withdrawn; the floor does not follow it down. **Taking a payout
shrinks the risk budget by exactly the amount taken.** Topstep's own guidance: *"We recommend
reaching a balance where your MLL is at $0 first. This gives your account a healthier base."*

## Timing, precisely

Getting this wrong silently costs a payout cycle, so it is worth stating in full.

- A trading day **locks at 4:00 PM CT**.
- The trading day runs **5:00 PM CT → 3:10 PM CT the following day**.
- *"The trading day your Payout is requested will not count toward your winning days for the next
  Payout cycle. ... A request submitted after 5:00 PM CT belongs to the next trading day — that day
  becomes the Payout request day and is excluded from the new cycle. This applies to all account
  types."*
- Worked example from the page: *"A Payout request submitted at 5:59 PM CT on Monday belongs to the
  Tuesday trading session. Tuesday is the Payout request day and does not count. The new cycle
  begins on Wednesday."*

So a request made in the evening burns the **following** day, not the one just finished. A runner
that fires payout requests after the close is throwing away a day per cycle.

## Interactions

| Situation | Rule |
|---|---|
| DLL hit today | *"Yes — but not yet. Hitting the Daily Loss Limit puts your account in a Temporary Violation. It lifts at the start of the next trading session."* |
| MLL hit after requesting | *"Yes. Once the Payout amount has been deducted from your balance, hitting the MLL won't affect it."* |
| Trading during processing (XFA) | *"the funds are transferred immediately, allowing you to start trading again right away"* — but mind which day counts |
| Trading during processing (LFA) | *"trading should be paused until the Payout has been fully processed and the funds have been deducted"* |
| Copy trading | *"automatically disabled while a Payout processes"*; must be **manually** re-enabled afterwards |
| Payout drops you a scaling tier | *"your maximum contract size decreases accordingly"* |
| Multiple XFAs | *"Each XFA follows its own Payout Policy independently. Requests from one account don't affect another."* |
| 100% payout from an LFA | Closes the account |

## Worked example from the policy page

Illustrating the $0.01 profit gate on an XFA Standard account:

| Balance | Eligible? | Action |
|---|---|---|
| $6,000 (from $0) | Yes — no profit requirement on the first payout | Take $3,000 → new balance $3,000 |
| $4,000 (up from $3,000) | Yes — profitable since last payout | Take $1,800 → new balance $2,200 |
| $4,500 (up from $2,200) | Yes — profitable since last payout | Take $2,000 → new balance $2,500 |
| $1,800 (down from $2,500) | **No** — not profitable | Keep trading |

Note the trap in the last row: after a payout you must climb back above the **post-payout balance**
before the next payout, not above zero. A drawdown after a payout locks the money up until it is
recovered.

## Review

Approval is not arithmetic alone. Topstep reviews against, in its own ordering:

1. Payout Policy requirements
2. Prohibited Conduct, Terms of Use, and Professional Behavior
3. Prohibited Trading Strategies

A prohibited-conduct finding can *"Delay or deny a Payout request"* even where no account rule was
breached — see [PROHIBITED.md](PROHIBITED.md). An account closed for a hedging violation forfeits
unpaid profits entirely.

## Methods and fees

| Method | Availability | Processing | Topstep fee |
|---|---|---|---|
| Prop-to-Brokerage | US only | Same day if requested by 12:00 PM CT | none |
| Aeropay | US banks only | Instant after approval | none* |
| Wise | China, Canada, UK | 1–3 business days | none* |
| ACH | US banks only | 1–3 business days | $30 |
| Wire / SWIFT | International | 5–10 business days | $30 |

\* *"No Topstep fee for Aeropay or Wise, but your bank or those services may charge their own fees."*

Worked example on the page: *"$500 minus $50 (10% split) minus $30 (processing fee) = $420
received"* — note the split is taken **before** the processing fee, and the $125 minimum is on the
requested amount.

Tax forms: W-9 (US persons) or W-8BEN (non-US), submitted as part of the request. Payouts go only to
a bank account in your own name.

## Not found

- **No "8-day" payout variant** appears in the current policy. The two live paths are 5-day Standard
  and 3-day Consistency. If an 8-day rule ever existed it has been superseded; nothing on
  help.topstep.com on 2026-09-13 mentions one.
- **No mandatory minimum number of days between payouts** beyond re-earning the day count. The
  practical floor is 3 trading days (Consistency path) or 5 (Standard), plus the excluded request
  day.
