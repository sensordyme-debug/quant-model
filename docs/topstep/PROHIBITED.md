# Prohibited conduct, prohibited strategies, and trading hours

**Rulebook version `2026.09.13` · retrieved 2026-09-13.**

Nothing in this file was previously captured anywhere in this repo. It is also the part of the
rulebook that most directly constrains what is worth *researching*, because several of the
prohibitions describe, almost exactly, the class of strategy an automated intraday system naturally
drifts toward.

Primary sources:
[Prohibited Trading Strategies, 10305426](https://help.topstep.com/en/articles/10305426-prohibited-trading-strategies-at-topstep) (dated 10 June 2026) ·
[Prohibited Conduct, 10296582](https://help.topstep.com/en/articles/10296582-prohibited-conduct) ·
[Professional Behavior, 10290170](https://help.topstep.com/en/articles/10290170-professional-behavior-at-topstep) (dated 10 June 2026) ·
[Understanding Hedging, 13747047](https://help.topstep.com/en/articles/13747047-understanding-hedging) ·
[2% Price Limit, 8284225](https://help.topstep.com/en/articles/8284225-staying-outside-the-2-price-limit-zone) ·
[Terms of Use §27](https://www.topstep.com/terms-of-use) (last updated 8 September 2026) ·
[Responsible Trading Program, 13620045](https://help.topstep.com/en/articles/13620045-what-is-the-responsible-trading-program)

---

## Consequences

Article 10296582 lists the possible responses to a Prohibited Conduct violation:

- Warning
- Deletion of the impacted trading day
- Account Reset
- Permanent account closure
- Delay or denial of a Payout request

*"Ultimately, the action Topstep takes will depend on the infractions severity and your prior
history (or lack thereof)."* *"Violations are reviewed case-by-case based on severity and history."*

So these are discretionary rather than mechanical — with **one exception** (hedging, below). For
research purposes discretion is not comfort: "deletion of the impacted trading day" alone destroys a
consistency calculation, and "delay or denial of a Payout request" removes the entire return.

### Who enforces

The **Trust Team**. *"Trust reviews Terms of Use violations, fraudulent activity, and account
manipulation. They do not handle platform or technical issues — that's Trader Support."*

### Appeals

*"You don't need to initiate an appeal."* The Trust Team contacts you if one is available. Appeals
can be denied. If accepted you must accept terms and conditions to return, and *"Breaching those
terms will result in immediate account termination."* New profiles created after a ban *"will be
closed immediately and no refunds will be issued."*

Identity verification is mandatory and may be re-requested at any time.

---

## Prohibited Trading Strategies (article 10305426)

Verbatim headings, with the article's own framing: *"These aren't gray areas — they're hard stops."*

| Strategy | The article's wording |
|---|---|
| **Account Stacking** | *"Repeatedly trading aggressively, hitting the Maximum Loss Limit (MLL) in one account, then switching to another account and repeating. The goal is to run high-risk attempts until a large win occurs. This exploits risk parameters and is not permitted."* |
| **Intentionally Depleting a Live Funded Account** | *"Deliberately drawing down a Live Funded Account® (LFA) balance to force a failure. Not permitted."* |
| **Violating Topstep's Terms of Use** | *"Any trades performed in conflict with Topstep's Terms of Use or the Trading Combine® (TC) terms and conditions."* |
| **Using Unfair Technology** | *"Using software, AI, ultra-high speed systems, or mass data entry that manipulates, abuses, or provides an unfair advantage on the platform or in the program."* |
| **Trading Outside Real Market Behavior** | *"Executing trades in a way that contradicts how trading actually works in the applicable futures markets, or in a way that creates justified concern that Topstep may suffer financial or other harm."* |
| **Trading Outside the Best Bid or Offer** | *"Placing orders at prices outside the current best bid or offer."* |
| **Trading Maximum Position Size into Major News Events** | *"Purposefully trading your full Maximum Position Size directly into a scheduled major news event."* |

### SIM fills — the section that matters most here

*"SIM fills aren't free money. Exploiting the simulator will get you removed from the program."*
Topstep *"retain[s] the right to reject profit claims if abuse is suspected."*

Examples given, *"including but not limited to"*:

- *"Running scalping algorithms designed to exploit unrealistic SIM fills"*
- *"Making hundreds of rapid trades to take advantage of preferential queue position in SIM"*
- *"Initiating reckless trades in gapped markets to profit from stray fills — these are improbable
  in live markets"*
- *"Repeatedly exploiting the relative lack of slippage in SIM to achieve impossible stop-loss
  execution"*
- *"Using tight brackets or auto-breakeven to take advantage of favorable SIM fills"*

The article's own calibration of where the line sits:

> *"If this doesn't sound like you, it probably isn't. The vast majority of Traders are here to
> learn and build toward consistent profitability. A few lucky fills won't get your Payout rejected.
> The behaviors above are intentional and systematic — usually hundreds or thousands of trades per
> day, with average durations measured in seconds, not minutes."*

**Read this against this repo's own intraday sleeve.** The stated threshold — *hundreds or thousands
of trades per day, holding times in seconds* — is the operative one, and it is the only quantitative
guidance Topstep gives anywhere on this subject. A high-turnover strategy stays clearly inside the
line while it trades tens of times a day with holds measured in minutes, and approaches the line as
turnover rises. This is a **design constraint on the research programme**, not a runtime check: it
must be honoured when a strategy is *chosen*, because by the time it is detected the payout is
already denied.

The three SIM-specific items also carry a research warning independent of the rules. *"The relative
lack of slippage in SIM"*, *"preferential queue position in SIM"*, and *"unrealistic SIM fills"* are
Topstep telling you, in writing, that its simulator's fill model is optimistic. Any edge that
survives only under optimistic fills is not an edge — the prohibition and the backtest hygiene point
the same way.

---

## Prohibited Conduct (article 10296582)

The full list as published:

- **Unprofessional behavior** — see Professional Behavior at Topstep
- **Excessive purchases** of Trading Combines or Resets
- **Price exploitation** — *"strategies designed to exploit errors in price display or data feed delays"*
- **Disruptive practices** — including spoofing
- **Trading outside the best bid or offer**
- **Using an external or slow data feed** to trade
- **Coordinated trading** — *"performing trades in concert with others (including unconnected
  accounts or third parties) to pool risk, hedge aggregate positions, or trade the same or opposite
  strategy simultaneously"*
- **Cross-account hedging (single-user)** — *"holding opposite positions across multiple accounts
  simultaneously"*
- **Trades conflicting with Topstep's Terms of Use**
- **Unfair technology** — *"using software, AI, ultra-high speed systems, or mass data entry to gain
  an unfair advantage"*
- **Trading inconsistent with real futures markets** — or in a way that creates financial risk for Topstep
- **Chargebacks or Disputes** — filing a dispute against a payment to Topstep
- **Exploiting platform deficiencies** — *"using instruments or methods that misuse bugs, errors, or
  deficiencies in the platform"*
- **Circumventing geographical or technical restrictions**
- **Holding a position within 2% of a product's price lock limit**
- **Trading on behalf of others** — including sharing incentives as part of any business arrangement
- **Account stacking**
- **Any other conduct** that Topstep determines, **at its sole discretion**, *"is uncommercial, games
  the market, is not a viable strategy, or is not responsible trading"*
- **No VPN** — *"VPNs, proxy services, TOR, geo-location obfuscation, and other identity-masking
  services are not permitted at Topstep."*

Also prohibited on Trader Profiles: harmful/offensive/illegal/sexual content, personal data or
misleading claims, unauthorised names or trademarks, advertising or scams. Profile content is
subject to automated screening.

On multi-account trading generally: *"Trading with friends & family is part of the Ultimate Trading
Experience. Just keep it by the book — no coordinated group trading, no account-sharing, no
single-account rule workarounds."*

### Note on "unfair technology" and automated trading

*"Using software, AI, ultra-high speed systems, or mass data entry"* appears in both articles and in
the Terms of Use. **It is not a blanket ban on automation** — it is qualified in every instance by
purpose: *"that manipulates, abuses, or provides an unfair advantage on the platform or in the
program"* (10305426) and *"to gain an unfair advantage"* (10296582). Topstep sells a trade copier
and documents automated risk tools, so software-driven order entry is plainly contemplated.

What is banned is software used *for* an unfair advantage — the SIM-fill exploitation list above
being the concrete examples. A LEAN algorithm placing ordinary orders at ordinary rates is not what
this clause describes. A LEAN algorithm placing thousands of orders per day to farm queue position
in a simulator is exactly what it describes. **The distinction is turnover and intent, not
automation.**

That said, this is the single clause under which a discretionary adverse finding is most likely for
this project, and the catch-all (*"at its sole discretion ... is not a viable strategy"*) means the
firm does not have to prove the exploitation. Plan accordingly.

---

## Hedging — the only mechanically enforced conduct rule

Article 13747047. Everything else in this file is a case-by-case review; this one is a **real-time
automated system with a published escalation ladder**.

**What it covers:** *"simultaneously going long and short the same or correlated instrument across
multiple accounts — such as MES/ES, MNQ/NQ."* Correlated micro/mini pairs count. Being long ES in an
XFA while short ES in a Combine is the canonical case.

**Detection** analyses position timing, position size, duration, and inferred intent.

**Escalation ladder:**

| Step | What happens |
|---|---|
| 1. First attempt | Real-time modal warning, brief window to un-hedge. Un-hedge in time and you continue. Otherwise positions are auto-liquidated, account flagged, trading continues. Follow-up email. |
| 2. Repeat, same day | Brief window, **no timer shown**. Failure to un-hedge → auto-liquidation. Trading continues. |
| 3. Next trading day | Mandatory acknowledgement on login — type *"I agree"*. **You cannot trade until it is completed.** |
| 4. After acknowledgement | **Any** future hedge → immediate liquidation, no window. |
| 5. Excessive attempts | Immediate liquidation, no window, plus a **Temporary Hedging Violation barring trading for the remainder of the day, across all hedged accounts**. |
| 6. Continued | *"your account may be permanently closed without further notice ... This action is irreversible."* |

**The three facts that make this the sharpest rule in the book:**

1. **Tracked at the trader level, not the account level.** *"If a Trader received a first-time
   warning and acknowledged the hedging policy, subsequent hedging activity in any newly purchased
   account is treated as a post-acknowledgment violation."* Buying a fresh account does not reset
   your position on the ladder.
2. **Not appealable.** *"Confirmed hedging violations are final and cannot be appealed. Accounts
   closed due to these violations cannot be reopened or reinstated."*
3. **Profits are forfeited.** *"accounts closed for hedging violations are not eligible for payouts,
   and any associated profits cannot be withdrawn."*

**Brevity and intent are no defence.** *"Opposing positions are prohibited even if the overlap is
brief or unintentional."* Explicitly including glitches and copy-trading artefacts: *"you're still
fully responsible for all activity across your accounts, including anything created by automated
systems or third-party tools."* Manual direction-switches without flattening first also count.

**What is allowed:** *"You can trade the same markets across different accounts. What's prohibited
is holding opposite positions simultaneously in a way that eliminates market risk."*

Practice Accounts are excluded from hedging detection. A hedging *warning* alone does not affect a
payout.

### Execution consequences for this repo

Directly actionable, and the most important operational finding in this document:

- **Any multi-account runner must enforce a global net-direction invariant per correlated instrument
  group** — `{ES, MES}`, `{NQ, MNQ}`, `{RTY, M2K}`, `{YM, MYM}` and so on — *before* an order is
  sent, not after. Position state across all accounts must be checked at order time.
- **Flatten before reversing.** *"Ensure all open positions are closed and any working orders are
  canceled before entering a new trade in the opposite direction."* A reversal implemented as a
  double-size opposing order can register as a hedge.
- The safest configuration is Topstep's own first recommendation: *"Trade a single account to
  completely avoid the possibility of hedging."* Given that violations are trader-level,
  unappealable, and forfeit profits, the expected cost of multi-account operation is much higher
  than the linear-scaling intuition suggests.

---

## The 2% price-limit rule

Article 8284225 plus Prohibited Conduct plus ToU §27.

*"When a product is within 2% of a price limit, market conditions are extreme and execution is
unreliable."* Topstep *"will not allow market participation when a product is trading within 2% of a
Price Limit."* Holding a position inside that band is Prohibited Conduct.

Price limits *"vary by product, contract month, and time of day."* Equity products with expanded
overnight limits: **ES, MES, NQ, MNQ, RTY, M2K, YM, MYM** — i.e. every equity-index product this
repo is likely to trade.

Two published monitoring methods:

1. Watch **% Net Change** on the quote board. *"Stop trading when % Net Change approaches the limit
   minus 2%."* With a 5% limit, stop at 3%.
2. Compute from the settlement price:
   - stop above: `settlement × (1 + limit% − 2%)`
   - stop below: `settlement × (1 − limit% + 2%)`

Method 2 is directly implementable and is the form a runner should use: it needs only the prior
settlement and the product's limit percentage, both known before the session opens.

---

## News-event restrictions

Two distinct rules.

**Discretionary (`TS-PRH-10`).** *"Purposefully trading your full Maximum Position Size directly
into a scheduled major news event."* No list of qualifying events, no window, no size threshold
below "full". The conservative reading: do not carry maximum size into any scheduled release.

**Mechanical (`TS-SCL-09`), CPI only.** From article
[13613539](https://help.topstep.com/en/articles/13613539-risk-adjustments-high-risk-high-volatility):
a **10-minute window, 5 minutes before and 5 after** the CPI release.

- Equity index **minis (ES, RTY, YM, NQ, NKD): no new opening transactions permitted.**
- **Micros**: capped at 1 / 3 / 6 / 9 / 15 contracts depending on account size.

Existing positions are not addressed; the restriction is on *opening*.

### Other volatility restrictions

Triggered by *"Expanding price limits"*, *"Velocity Logic halts"*, *"Historic price ranges"*, or
*"Rapid, sustained price movement"*. Current standing restrictions (Combine / XFA / Pro **and** LFA):

| Product | Mini limit |
|---|---|
| Crude Oil (CL) | 3 / 6 / 9 |
| Gold (GC) | 3 / 6 / 9 |
| Heating Oil (HO) | 3 / 6 / 9 |
| RBOB Gasoline (RB) | 3 / 6 / 9 |
| **Silver (SI)** | **0 minis** |

These are *"Temporary"* and last *"only while volatility levels are elevated."* Notification is by
email, dashboard banner, and @AskTopstep — **all out-of-band channels an automated runner does not
read.** Any strategy in these products needs a manual pre-session check or a rejected-order
fallback path.

---

## Trading hours

Grouped here because the flat-time rules are enforcement rules. Rule IDs `TS-HRS-01`..`15`.

Source: [8284206](https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade),
[13350348](https://help.topstep.com/en/articles/13350348-topstep-holiday-trading-hours), ToU §27.

### Standard session

| Session | Time (CT) |
|---|---|
| Sunday open | 5:00 PM |
| Weekday close | 3:10 PM |
| Weekday reopen | 5:00 PM |
| Friday close | 3:10 PM, closed until Sunday 5:00 PM |

- All open positions and pending orders *"begin to automatically cancel"* at 3:10 PM CT. The Terms
  of Use put the flatten *"about ten seconds prior to the closing bell at 3:10 PM CT."*
- *"Avoid opening new positions after 3:08 PM CT — Risk Managers begin flattening at that time. It's
  still your responsibility to be flat by 3:10 PM CT."*
- *"If you're trading a product with an earlier daily close than 3:10 PM CT, you must exit before
  that product's close."*
- *"Topstep is a day trading program. No swing trading. No Forex."*

**Design rule for this repo: 3:08 PM CT is the last entry, 3:10 PM CT is the hard flat.** A runner
should target flat by roughly 3:05 PM CT to leave room for slippage on the exit, because the
auto-flatten is a market order into the same liquidity everyone else is exiting through.

### Product-specific sessions

| Products | Session (CT) |
|---|---|
| CBOT grains — Corn, Wheat, Soybeans, Soybean Meal, Soybean Oil | Sun–Mon 7:00 PM – 7:45 AM; Mon–Fri 8:30 AM – 1:20 PM |
| CBOT grain pause | Mon–Fri 7:45–8:30 AM — **no orders accepted**; TopstepX manual lockout unavailable for CBOT positions held through it |
| CME agriculture — Live Cattle, Lean Hogs | Mon–Fri 8:30 AM – 1:05 PM |

### Holidays

- *"Close all positions 15 minutes before early close (e.g., close by 11:45 CT for a 12:00 CT
  close)."* Applies to Combine, XFA and LFA. Open positions at the cutoff are **auto-liquidated**.
- **CME blended trade dates:** on some holidays CME merges calendar days into one trading session,
  so *"your Daily Loss Limit applies to the entire combined period, not individual calendar days"*
  and a DLL hit can lock the account through what looks like the next calendar day.
- **Only Live Funded Accounts on TopstepX follow CME Protocol blending.** Combine and XFA treat each
  calendar day independently.
- **Payouts are not available during holiday hours.**
- *"Holiday trading hours are subject to change per the exchange"* — always confirm against the CME
  calendar.

### Permitted products

**CME Equity:** ES, MES, NQ, MNQ, RTY, M2K, NKD, MBT (Micro Bitcoin), MET (Micro Ether)
**CBOT Equity:** YM, MYM
**CME FX:** 6A, 6B, 6C, 6E, 6J, 6S, E7, M6E, M6A, 6M, 6N, M6B
**CME Agriculture:** HE, LE
**NYMEX:** CL, QM, NG, QG, MCL, RB, HO, PL, MNG
**CBOT Agriculture:** ZC, ZW, ZS, ZM, ZL
**CBOT Financial/Rates:** ZT, ZF, ZN, TN, ZB, UB
**COMEX:** GC, SI, HG, MGC, SIL, MHG

No Forex (spot). No products outside this list.

---

## The Responsible Trading Program

Article 13620045. Not a punishment — *"a structured path to rebuild discipline, consistency, and
sound risk management"* — but its parameters are binding while you are in it, and **placement is at
Topstep's initiative**, triggered by *"trading behavior that isn't sustainable in live markets."*

**Trigger behaviours as listed:** multiple accounts hitting maximum loss limits daily; maxing
position size on most trades; failing to keep losses smaller than winners; not using stop losses;
trading the full portfolio or acting on emotional impulses; disregarding daily limits.

**While enrolled:**

- All new Trading Combines automatically get a Daily Loss Limit ($1,000 / $2,000 / $3,000)
- Passing a Combine gives you **XFA Consistency only** — *"best day must stay under 40% of total
  profits per Payout period"*. Standard XFA is unavailable.
- Payouts up to $6,000 every 3 trading days, consistency permitting

**Exit:** no set timeline. Qualify for and begin trading a Live Funded Account, generate **$10,000
of profit in that live account**, then you are removed.

Topstep's framing: *"Can't trade small? You can't trade big. Consistency first — then size and
scale."*

> **Why this is a first-order risk to the research plan, not a footnote.** The trigger list is close
> to a description of a naive aggressive automated system: several accounts, maximum size, no
> discretionary stop discipline. Enrolment is silent, has no appeal process described, and its exit
> condition requires $10,000 of profit in a Live Funded Account — a stage 0.71% of XFA participants
> reach. In practice, enrolment is close to permanent, and it permanently converts the economics
> from the Standard path to the Consistency path.
>
> The mitigation is a design choice, made before the first Combine is purchased: **size below the
> cap, always use stops, respect a self-imposed daily limit, and do not run many accounts in
> parallel.** Every one of those also improves the honest risk-adjusted return, which is the
> convenient case where the compliance constraint and the trading constraint agree.

---

## Professional Behavior (article 10290170)

Behaviours that *"put your account at risk"*: excessive use of XFAs and irresponsible trading within
them; intentionally depleting an LFA; rudeness to Topstep employees or Discord Ambassadors;
constantly asking for resets, freebies or exceptions; threatening bad reviews for discounts; promo
code abuse; excessive support tickets or calls; excessive tagging in Discord; creating a toxic
atmosphere; publicly posting private correspondence; initiating chargebacks; sharing falsified
images or screenshots.

Relevant to an automated operation mainly through the first item — *"Excessive use of Express Funded
Accounts® (XFAs) and trading irresponsibly within them"* — which overlaps `TS-PRH-18` and the
Responsible Trading Program triggers.

---

## Terms of Use §27

The [Terms of Use](https://www.topstep.com/terms-of-use), **last updated 8 September 2026** — five
days before this retrieval — carry the contractual version of the Prohibited Conduct list. Notable
clauses in their own wording:

- *"Using any trading strategy intended to exploit or create errors in the Services"*
- *"Using any trading strategy that includes disruptive practices ... spoofing strategies"*
- *"Performing trades any time outside the best bid or offer"*
- *"Performing trades using an external or slow Data feed"*
- Coordinated trading to manipulate or gain unfair advantage, *"including high-frequency trades"*
- *"Using any software, artificial intelligence, ultra-high speed, or mass Data entry"*
- *"Using any instruments that may adversely affect the operation of the Site"*
- Holding positions within 2% of lock limits
- *"Trading on behalf of others including ... sharing any incentives"*

And on hours: *"Products may be traded during normal electronic trading hours unless otherwise
indicated"*; *"All positions MUST be closed prior to 3:10 PM CT or prior to the market close"*;
positions *"will automatically be flattened ... about ten seconds prior to the closing bell at
3:10 PM CT."*

The ToU is the contract; the help centre is the explanation. Where they conflict the ToU governs,
and its 8 September 2026 update date should be **re-checked at every rulebook version bump** — it is
the fastest-moving of the sources here.
