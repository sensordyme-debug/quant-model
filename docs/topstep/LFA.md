# Live Funded Account (LFA)

**Rulebook version `2026.09.13` · retrieved 2026-09-13.**

Topstep's own capital, in the live market. Entry is **not** a mechanical threshold — it is a Risk
Team decision. Article 10657969: *"Once the Risk Team determines you're ready, your options are to
move to Live or close your Express Funded Account."*

For scale: Topstep's own 2025 statistics page states that **0.71%** of individual participants
trading in an Express Funded Account were called up to a Live Funded Account. Any plan whose
economics depend on reaching the LFA should be discounted accordingly.

Primary sources:
[10657969](https://help.topstep.com/en/articles/10657969-live-funded-account-parameters) ·
[11748475](https://help.topstep.com/en/articles/11748475-dynamic-live-risk-expansion) ·
[topstep.com/live-funded-account-rules](https://www.topstep.com/live-funded-account-rules) ·
[8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy)

## Starting balance and the reserve

Two inputs determine the opening balance:

1. **Account size** — the average of eligible XFAs, rounded up to the nearest tier ($50K / $100K / $150K)
2. **Cumulative balance** — the actual combined balances of those accounts, capped at the account size

The money then splits:

- **20% available to trade immediately**, minimum $10,000
- **80% held in Reserve**, released in **four 25% increments**

### Reserve release

| LFA size | Profit target to unlock each 25% increment |
|---|---|
| $50K | $3,000 |
| $100K | $6,000 |
| $150K | $9,000 |

*"Reserve funds unlock in 25% increments each time you hit the Profit Target"*, *"Reviewed every
Monday morning"*, deposited within 1–2 business days. The marketing page states expansion is
reviewed *"no more than once per calendar week"* with profits measured *"after market close on
Friday of each week"* and approved unlocks applied *"by the following Tuesday"*.

Note the coincidence worth not over-reading: the reserve-unlock targets are the **same three
numbers** as the Combine profit targets. They are separate rules that happen to share values.

## Daily Loss Limit — automatic, and dynamic

The DLL is **not optional** in an LFA.

| LFA size | Standard DLL | Max position size |
|---|---|---|
| $50K | $2,000 | 5 contracts |
| $100K | $3,000 | 10 contracts |
| $150K | $4,500 | 15 contracts |

Note these are the **MLL** amounts from the Combine/XFA reused as the LFA's *daily* limit — a much
tighter constraint than it looks at first glance.

When it triggers: *"Positions are flattened"* and *"Trading is paused until the next session."*

### Safeguard tightening

| Tradable balance | Adjusted DLL | Max contracts |
|---|---|---|
| ≤ $10,000 | $2,000 | 5 |
| ≤ $5,000 | $1,000 | 3 |

These update on Fridays and revert once the balance recovers.

## Dynamic Live Risk Expansion

Replaces the XFA Scaling Plan in the LFA. Unlike the Scaling Plan, **this ladder is published as
text**. Advancement is by net profit *earned in the LFA only*, and each tier additionally requires
**10 Active Trading Days** (≥1 trade, no minimum P&L).

| LFA net profit | Daily Loss Limit | Max position size |
|---|---|---|
| $15,000 | up to $5,000 | standard |
| $20,000 | up to $5,500 | standard |
| $50,000 | up to $6,000 | standard |
| $100,000 | up to $10,000 | up to 30 lots |
| $200,000 | up to $20,000 | up to 50 lots |
| $550,000 | up to $50,000 | up to 70 lots |
| $100,000+ (top band) | up to $100,000 | up to 100 lots |

> The bottom four rows are reliable; the **ordering and labelling of the top three rows as extracted
> is internally inconsistent** (a "$100K+" band appearing above "$550K"). The extraction is
> untrustworthy at the top of the ladder. Treat rows above $200,000 as `SEARCH` tier and re-verify
> on the page before any plan depends on them. Nothing in this repo's horizon reaches them.

Rules: only LFA profits count; dropping below your current tier **resets the 10-day counter**; tiers
must be taken in order with no skipping; the Risk Team may adjust limits at discretion. Standard
position limits hold until $100,000 of profit.

## Payouts

- **5 winning days** of $150+ net P&L per cycle, non-consecutive.
- Up to **50% of the account balance**, with **no dollar cap** — the XFA caps do not apply.
- Withdrawals come from the **unlocked** balance only, never the reserve.
- After **30 non-consecutive winning days** of $150+: daily payouts unlock. *"request as much of
  your unlocked balance as you want, once per day (min $125)."*
- *"Payout eligibility is not tied to capital expansion. You can take Payouts while still trading
  with partial account access."*
- The marketing page adds: before 30 benchmark days, limited to *"50% of your share of Trading
  Profits"*; after, *"100% of your share"*; total payouts capped at *"90% of the Starting Balance
  plus net Trading Profits"*.
- **A 100% payout closes the account** — the balance reaches the MLL.
- After submitting a request, *"trading should be paused until the Payout has been fully processed
  and the funds have been deducted from the account."* This is stated for Live accounts specifically
  and is stricter than the XFA guidance.

## What ends an LFA

| Event | Consequence |
|---|---|
| Balance drops below **$1,000** | *"the account will be liquidated immediately and closed at the end of the trading day"* |
| Withdrawing the full balance | Closes the account |
| Intentionally depleting the balance to force a failure | Prohibited conduct (`TS-PRH-16`) |
| Position open past 3:10 PM CT | Auto-flattened *"about ten seconds before"* the bell |

## Simulation notes

- The LFA transition is an **external decision**, not a threshold. A simulator must model it as an
  input, never as something the strategy can trigger. `topstep.py`'s `promote_to_live()` is the
  right shape.
- The tradable balance, not the nominal account size, is what the DLL and contract limits key off.
  Simulating against the nominal size overstates capacity by 5x at the start (20% tradable).
- The LFA is the **only** stage that follows CME blended trade dates on holidays (`TS-HRS-13`), so a
  holiday-week DLL simulation differs between LFA and XFA/Combine.
- The trade copier is reportedly unavailable in the LFA. That is `SEARCH` tier — not confirmed on a
  fetched page — but it is the direction to assume when planning multi-account execution.
