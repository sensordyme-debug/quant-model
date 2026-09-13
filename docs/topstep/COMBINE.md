# Trading Combine

**Rulebook version `2026.09.13` · retrieved 2026-09-13.**

The evaluation. A paid monthly subscription against a simulated account; pass it and you are issued
an Express Funded Account. Rule IDs cross-reference [RULES.md](RULES.md).

## Parameters

| | $50K | $100K | $150K |
|---|---|---|---|
| **Profit target** (`TS-CMB-01`) | $3,000 | $6,000 | $9,000 |
| **Maximum Loss Limit** (`TS-MLL-01`) | $2,000 | $3,000 | $4,500 |
| **Max contracts** (`TS-CMB-06`) | 5 mini / 50 micro | 10 / 100 | 15 / 150 |
| **Daily Loss Limit, optional** (`TS-DLL-01`) | $1,000 | $2,000 | $3,000 |
| **Consistency target** (`TS-CON-01`) | 55% of total profit | 55% | 55% |
| **Monthly cost, Standard path** (`TS-CMB-02`) | $49 | $99 | $199 |
| **Monthly cost, No Activation Fee path** (`TS-CMB-03`) | $95 | $149 | $229 |

Sources: [8284197](https://help.topstep.com/en/articles/8284197-trading-combine-parameters) ·
[8284204](https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit) ·
[10490293](https://help.topstep.com/en/articles/10490293-daily-loss-limit-in-the-trading-combine-and-express-funded-account) ·
[8284208](https://help.topstep.com/en/articles/8284208-consistency-at-topstep) ·
[14289835](https://help.topstep.com/en/articles/14289835-topstep-pricing-and-payment-questions) ·
[topstep.com/no-activation-fee](https://www.topstep.com/no-activation-fee) ·
[topstep.com/topstep-prop](https://www.topstep.com/topstep-prop)

## Objectives, in Topstep's own framing

Article 8284197 states two objectives and one prohibition:

1. *"Reach and maintain your Profit Target"*
2. *"Meet the Consistency Target — your best single day should stay below 55% of your Profit Target"*
3. *"Do not let your account balance hit or go below the Maximum Loss Limit (MLL)"*

Objective 2 as printed on 8284197 says **"of your Profit Target"**. Article 8284208's calculation
line and worked example say **of total profit**, and article 8284099 says
*"best trading day ≤55% of total profits"*. **Total profit is the operative denominator** — see
[RULES.md § The 50%-vs-55% question](RULES.md#the-50-vs-55-question-resolved). This spec adopts
`(0.55, total)`.

## Where the profit target came from, and why it is now DOC-tier

`topstep.py` holds these three numbers at `SEARCH` tier with the note *"Not found on 8284197,
8284099 or /our-program."* That remains true — none of those three pages carries the figures. They
were found instead on two **other** Topstep-owned pages, each stating all three sizes in a
parameters table alongside figures already independently verified (MLL, max contracts), which is
what makes the corroboration meaningful rather than circular:

- [topstep.com/no-activation-fee](https://www.topstep.com/no-activation-fee) — a pricing page whose
  table gives, per size: monthly cost, profit target, max loss limit, max contracts, payout cap.
- [topstep.com/topstep-prop](https://www.topstep.com/topstep-prop) — the same parameter set, plus
  the standard and consistency payout caps.

Both give $3,000 / $6,000 / $9,000, and both agree with the MLL and contract figures already
confirmed from the help centre. Independently, article
[10657969](https://help.topstep.com/en/articles/10657969-live-funded-account-parameters) uses the
same three numbers as the LFA reserve-unlock targets.

**This closes the owner's #1 blocker.** `COMBINE_PROFIT_TARGET` in `topstep.py` can be promoted from
`Confidence.SEARCH` to `Confidence.DOC` with these two sources, and `combine()` will then build a
profile without `allow_unverified_target=True`. *That code change is not made by this pass.*

The residual caution is worth stating plainly: these are marketing/pricing pages rather than help-centre
rule articles, and the fetch was an automated extraction. Confirm on the dashboard before purchase.

## Pricing

Two purchase paths, chosen at checkout and **locked** (`TS-CMB-07`):

| Path | Monthly | XFA activation fee | Total to first funded account |
|---|---|---|---|
| **Standard** | $49 / $99 / $199 | $149, once per XFA earned | monthly × months + $149 |
| **No Activation Fee** | $95 / $149 / $229 | $0 | monthly × months |

A **Reset** costs the same as one month at that size and path (`TS-CMB-04`), and is limited to
**2 per account per calendar day** (`TS-CMB-08`). There is no cap on the number of Combines
purchased — but *"Excessive purchases of Trading Combines or Resets"* is itself listed as Prohibited
Conduct (`TS-PRH-18`), so the absence of a hard cap is not permission.

**One unresolved discrepancy.** The help-centre pricing article
([14289835](https://help.topstep.com/en/articles/14289835-topstep-pricing-and-payment-questions))
gives the No Activation Fee path as **$95 / $149 / $229**. The marketing page
[topstep.com/no-activation-fee](https://www.topstep.com/no-activation-fee) was extracted as
**$85 / $129 / $199** for the same path. The Standard path ($49 / $99 / $199) agrees on both. This
spec adopts the help-centre figures as authoritative, because a help-centre pricing article outranks
a landing page and because a landing page is the more likely place for a promotional rate. Treat the
No-Activation-Fee row as `DOC` on the help-centre number and **verify at checkout**.

Back2Funded reactivation, if a funded account is lost within 30 days: **$599 / $699 / $829**, max 2
reactivations per account, 7-day window to activate.

## Passing

There is **no published minimum number of trading days**. The binding floor is arithmetic, not a
rule: with the consistency test at 55% of *total* profit, one trading day gives 100% and cannot
pass, so **two days is the practical minimum** (`TS-CON-06`).

Exceeding the consistency target does **not** fail the Combine. Article 8284208: *"If it exceeds
that, your Profit Target increases. You'll need to earn more to pass."* The size of the increase is
never stated. `topstep.py` models it as the smallest increase that restores compliance — earn until
`best_day / total_profit` falls back to the limit — which is a lower bound on the real penalty
rather than a guess at it. That treatment survives this review; the number itself stays `OWNER`.

## What ends a Combine

| Event | Consequence |
|---|---|
| Balance touches or falls below the MLL, **including on unrealized P&L** | Liquidated for the remainder of the day; ineligible for funding until reset (`TS-MLL-05`) |
| Optional DLL hit | **Not** a failure. Flattened, orders cancelled, no new trades until 5:00 PM CT next session. Account stays eligible. (`TS-DLL-03`) |
| Position open past 3:10 PM CT | Auto-flattened. A held overnight position is not a permitted state at all (`TS-HRS-02`, `TS-HRS-08`). |
| Prohibited conduct | Case-by-case: warning, deletion of the trading day, account reset, or permanent closure ([PROHIBITED.md](PROHIBITED.md)) |

## Simulation notes

- The MLL is **EOD-trailing with an intraday breach test**. Do not simplify it in either direction;
  the two simplifications err in opposite directions and both errors are large. `topstep.py`'s
  `TrailingMode.EOD_TRAIL_INTRADAY_BREACH` is correct.
- Outcomes are **invariant to the starting cash balance**, which Topstep never publishes. Every
  quantity — MLL, target, lock level — is measured relative to the start.
- The consistency test must be evaluated on **daily** P&L, so a simulator that only reports a final
  equity curve cannot evaluate a Combine at all. Daily settlement is mandatory.
- Consistency is checked against total profit *as it stands*, so it is path-dependent: the same set
  of daily P&Ls in a different order passes or fails identically (the test uses only max and sum),
  but *adding* a losing day after a big win makes the test **harder**, not easier, because total
  profit falls while the best day does not.
