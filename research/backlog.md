# Research backlog

Ranked list of hypotheses and infrastructure work. The improvement loop takes the top open
item. Move finished items to the bottom under "Done" with a one-line result and the
experiment timestamp.

## Current objective (set 2026-09-08; **met 2026-09-09**, restated at the 2026-09-10 review)

Original: a backtest-validated strategy running on IBKR **paper** trading by **2026-09-10**.
**Done** - S-12 `s1_momo` is the champion via `scripts/evaluate.py`, `compare_orders.py` gates the
deploy, and the runner filled its first real paper orders at 15:46 ET on 2026-09-09.

Objective from here: **make the second (intraday) sleeve honest, or retire it.** It is deployed at
half size and measured negative on 2,686 sessions, so the work is (1) replace the estimated
slippage constant with measured fills (A-5 part 2, every session), (2) find a causal regime gate
for the long-volatility mechanism A-10 confirmed at t = +10.70 (O-1), judged on the Alpaca
regimes; and if that fails, say so and take the sleeve to zero rather than find a twelfth lever.
Live money stays off the table until the human signs off in `live/`.

Status 2026-09-12 05:0x UTC (S-26): **the one direction S-25 left open is now priced, and the book
that takes it is the first candidate in this repository whose edge survives its own execution and
dies on its risk.** S-25 named exactly one successor - target the overnight leg without paying for
a daily equity round trip - and the only instrument that can do that is a futures overlay on the
*other* leg, which is only worth asking because F-2a measured an ES round trip at 0.488 bps.
New `scripts/sweep_s26.py` plus **two default-inert arguments on `sweep_s25.legs_simulate`**
(`hedge=`, `scale=`, S-22's precedent); **10 ledger rows** under `daily/s26_hedge`, all DIAGNOSTIC;
seven clauses pre-registered, three of which could have invalidated the run. **(1) Identity passes
to the digit**: `hedge=None, scale=1.0` reproduces S-25's deployed cell at CAR 22.192150% / 5,052
orders / residual 5.33e-16, and the costed cell lands on S-22's **19.640%** a third time.
**(2) The proxy is validated, not assumed, and it is the tightest fit on file**: over F-2a's 313
ES sessions **corr(ES cash session, SPY open->close) = 0.9994, slope 0.9984, basis sd 2.1
bps/session**, so this overlay needs **no CME purchase at all**. **(3) Said before pricing
anything**: the intraday leg has no alpha but it does have a return - SPY's own intraday leg is
**+2.432 bps/day at t +1.86** (overnight +3.666 at t +3.33) - so the trade is one drift that has
never reached |t| = 2 against a certain variance reduction. **(4) The grid** (2 bp equity spread +
IBKR Pro financing + 0.488 bps futures round trip, trailing beta 1.12): unhedged **19.640% / 1.047
/ DD 24.04 / std 0.188**, then 18.972 / 18.174 / 17.263 / **16.224** at h = 0.25 / 0.50 / 0.75 /
1.00, with **Sharpe peaking at a HALF hedge (1.124)** and drawdown falling monotonically to 20.77 -
every basis point sold buys risk back. **(5) The primary screen is REFUSED, and on RISK rather than
on cost, sign or significance - a refusal mode this repository has not produced before.**
Vol-matched to the unhedged 0.1883 on the real machinery, **h=0.50 earns 20.837% / Sharpe 1.100
(+1.197 CAR points), beats the bar in both halves (+0.72 IS, +1.66 OOS) and stays inside Reg-T at
1.83x max gross - and is refused because its drawdown is 26.02 against 24.04, 1.99 points worse
against the champion's 1.0-point tolerance**; h=1.00 is refused on CAR full period and in both
halves. Paired **+0.395 at t +0.60**, so nothing reaches |t| = 2. Clause 5's written-down
expectation ("refused, and narrowly") held, but it expected the refusal from the drift being sold
and got it from the **leverage used to buy the risk saving back**. **(6) The placebo passes and is
the durable positive**: the identical overlay on the **overnight** leg costs **-4.310 bps/day at
t -4.14** (7.598% / DD 28.60) against the intraday overlay's -1.373 at t -1.02 - a factor of 3.1
and the only |t| > 2 in the file - so **S-25's split is confirmed by a second, independent route**
(a hedge rather than an attribution). **(7) The breakeven, the durable number**: at zero hedge cost
h=0.50 earns 21.821% on 0.65x of live equity a session -> **breakeven +1.108 bps a round trip**,
h=1.00 +0.316, against **ES 0.488** (full tick 0.856, MES 0.744) - **the half hedge clears the
cheapest instrument on file by 2.3x**. Granularity: the h=1.00 hedge is below one ES contract on
**65.4%** of sessions (below one MES on 8.2%). **One correction to a prior number, found by this
iteration**: a breakeven divides a growth-normalized edge, so its turnover divisor must be
growth-normalized too; S-25's (and this repo's `turn x/yr` column's) start-equity basis reads
1,447x/yr and +0.073 bps where the correct figures are 335x/yr and +0.316, a **4.3x compression**.
**S-25's conclusion is unaffected** (its variants lost at zero cost, so the sign holds on any
divisor) but its printed breakeven magnitudes should be read as signs, not sizes. **Nothing
shipped, nothing promoted, no default changed**: champion unchanged at S-18, `champion.json` gains
a `hedge_note` only, `live/*` and all three scheduled tasks untouched, no runner-loaded file
modified so rule (a) owes no replay. **Standing jobs both ran first with no new input**:
`slippage_report.py` 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90; `daily_fills.py` 10 fills /
$2.37M / **+3.2 bps (se 4.5)**, `ref_price` the previous close 10 of 10. **What it changes for the
loop**: the reusable rule is that **matching daily volatility is not matching drawdown, so a
vol-matched relever owes its own drawdown column** - the risk twin of S-15/S-20's vol-matched
control, which was written to catch a size decision dressed as return and says nothing about the
path. And what is left of the overlay is not a research item but an owner one: the *un-relevered*
h=0.50 book trades **1.47 CAR points for 1.58 points of drawdown and +0.08 of Sharpe**, a
risk-posture change, and it is written into `BLOCKERS.md` as a priced option rather than a
recommendation.

Status 2026-09-12 03:0x UTC (S-25): **the daily champion is paid while the market is shut - 94% of
its return and all of its measurable alpha is the overnight leg - and that re-prices both ops
routes the owner is holding.** With the intraday tracks closed by F-4/F-5 and the daily instrument
audit closed by S-22, this iteration measured the one thing about the deployed book nobody had ever
separated: a book that holds nine ETFs around the clock is paid twice a day, and every figure in
this repository is a close-to-close number. New `scripts/sweep_s25.py`, built on S-19's validated
share-level harness (corr 0.99650 against LEAN's own equity curve); 3,689 sessions 2012-2026;
**6 ledger rows** under `daily/s25_legs`, all tagged DIAGNOSTIC; five clauses pre-registered.
**(1) Identity passes to the digit**: the attributing book reproduces `sweep_s19`'s deployed cell
at 22.192150% / 5,052 orders, the leg residual is 5.33e-16 of equity on every session, and the
costed cell lands on S-22's independently-derived **19.640%**. **(2) The split**: +8.662 bps/day
total = **+8.103 overnight (t +6.80, 94%)** and **+0.738 intraday (t +0.47, 9%)**, with annualized
leg vol 0.115 / 0.151 against 0.188 total - **the leg paying 94% of the return carries 61% of the
risk**. **(3) The control is the finding**: against an always-invested book scaled daily to the
champion's own 1.25x gross, the selection difference is **+3.087 bps/day at t +4.20 overnight**
(SPY control +3.081, t +3.79) and **-0.314 at t -0.37 intraday**, with both halves agreeing
(+2.993 t +3.62 IS, +3.200 t +2.51 OOS). **Fourteen years find no intraday content in this
ranking at all.** **(4) Two artifacts ruled out**: the ex-date credit is +0.683 bps/day for the
book against +0.826 for the control, so price-only the excess is *larger* (+3.231, t +4.36); and
on S-24's official opening crosses the overnight leg reads +8.864 against the store's +8.887
(2,683 sessions), so it is not Yahoo's print convention. **(5) The strategy screen is refused and
the breakeven is negative**: overnight-only earns 13.113% at 0 bp (Sharpe 1.133 at 0.115 vol) and
**-0.555% at 2 bp**, intraday-only -3.032% and -18.269%, against the deployed 20.853% / 19.640%,
paired -7.785 (t -4.97) and -15.395 (t -12.19), failing in both halves - they lose **at zero cost**
(breakeven -0.751 and -9.988 bps one-way), so this is S-15/S-20's lesson again: a smaller book, not
a better one. **(6) Post hoc, labelled: the pre-open MOO move's entire payoff is intraday**
(+0.604 bps/day at t +1.43; overnight -0.006), which is structurally forced - both conventions hold
identical targets overnight - so **the owner's recommended move buys the leg where this strategy
has never shown an edge**, at a statistic that has never reached |t| = 2. The recommendation stands
(the defect is certain, the payoff is not) but the framing is sharper. **(7) The other route is
dead**: the in-place fix, priced as an upper bound (decide on close[D], fill at close[D]), earns
**22.374% against 22.192% - +0.18 CAR points** - because it buys the same intraday leg (+0.616) and
**gives it back overnight (-0.572, t -1.79)**. Feeding today's close into the signal makes the
overnight leg worse, which is S-9/S-10's skip lever rediscovered from the opposite side, and it
means **the paid real-time data subscription can no longer be justified by that fix**. **Nothing
shipped, nothing promoted, no default changed**: champion unchanged at S-18, `live/*` and all three
scheduled tasks untouched, one new script only so rule (a) owes no replay; `champion.json` gains a
`leg_note` and nothing else. **Standing jobs both ran first**: `daily_fills.py` 10 fills / $2.37M /
**+3.2 bps (se 4.5)**, `ref_price` the previous close 10 of 10 (2026-09-11's closes have published,
so F-4/F-5's +1.7 is confirmed as the benchmark-availability artifact); `slippage_report.py`
unchanged at 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90. **What it changes for the loop**:
the reusable rule is the daily twin of F-5's always-long control - **a daily-sleeve return
statement must say which leg it lives in and be quoted against an always-invested control at the
same gross in that leg** - and any future candidate that spends turnover on what the book holds
*between* the open and the close is spending it where the evidence is zero.

Status 2026-09-12 02:0x UTC (F-5): **F-4's momentum column is about a third drift and the rest does
not reach significance, and the published market-intraday-momentum effect is not in this store at
all.** F-4 refused the afternoon reversal on sign and left one piece of arithmetic unfollowed: it
wrote the rule *a cost refusal is an argument for a cheaper instrument only when the gross column
has the right sign at |t| > 2* and then applied it **only to the sign its own table says is
wrong**. Charged F-2a's 0.488 bps ES round trip, F-4's raw 11:30 momentum cell reads **+2.24 -
0.49 = +1.75 bps** instead of -2.35. F-5 put that arithmetic to the instrument that would carry
it - the **index itself**, since a 56-name basket is not something a future holds. New
`scripts/sweep_f5.py`; store `data/minute_alpaca`, **SPY / QQQ / IWM**, **2,687 sessions /
367,872 legs, 2016-01-04..2026-09-10** - the three index ETFs no event study in this repository
had ever touched, because the disjointness rule excludes them from the sleeve. **Stated before the
first number and unchanged by the result: nothing measured here may ever be deployed on the
intraday equity sleeve**; the only instrument is the index future, so a survivor would have been
evidence for the CME purchase, not a strategy. Seven clauses pre-registered, two of which carry
the entry. **(1) A clean refusal: 0 of 144 cells** (3 indices x 2 signals x 2 exits x 12 entry
minutes) reach the pass mark of net positive at t > 2 in two of three regimes. **(2) Clause (5) -
the always-long control F-4 did not run - is the finding, and clause (6) predicted it.**
Session-clustered over the `todate`/`flatten` family the gross is **+1.55 bps at t +2.42**, F-4's
sign reproduced on the index; the **always-long book over the identical windows earns +0.54**; and
the difference that is the actual forecast is **+1.01 bps at t +0.89**, by regime **-0.78 / +1.83
/ +2.47 at t -0.51 / +0.81 / +1.22** - negative in the first third and never significant. Cell by
cell **5 of 138 beat the control at t > 2** against ~3.2 expected by chance, and all five sit at
the **same entry minute**. The signal is long on **52.6%** of sessions. **(3) So F-4 is identified
rather than contradicted**: the index reproduces its column at the same minutes and size (11:30
gross **+1.99 / +3.64 / +1.57** on SPY/QQQ/IWM against F-4's 56-name +2.24), which says the raw
book was a market-factor bet - and is why it was positive at 12 of 12 entry minutes. **(4) The
published effect is the weakest family in the file**: first-30-minute signal into a later window,
**13 of 33 cells positive net**, and the exact classic cell (enter 15:30, hold to the flatten) is
**gross -0.19 / +0.10 / +0.05 bps, |t| <= 0.73** - zero before any cost - with a best-t book at
**CAR 0.90% / Sharpe 0.25**. **(5) The nearest miss, post hoc and failing both clauses**: QQQ
`todate` 15:00 -> flatten, gross +2.52 (t +3.30), net **+2.03 (t +2.66)**, but **one** of three
regimes (+0.04 / +3.94 / +2.12 at t 0.04 / 2.56 / 1.78) and only +1.75 (t +1.54) over always-long;
as a 1x book **CAR 4.99% / Sharpe 0.82 / DD 8.4% / worst day -359 bps**, i.e. ~**10x** on the
future to reach the 3%/day mandate, where the worst session is -36%. **(6) One by-product**:
entering at **15:30** in the day's direction is gross **-0.05 / +0.10 / +0.07** and net -0.53
(t -2.09) / -0.39 / -0.41 - the last half hour is where X-1's reversal sign lives and it is a
**pure cost refusal**, with no gross to buy in either direction. **Nothing shipped, nothing
promoted, no default changed**: champion unchanged at S-18, `champion.json`, `live/*` and all
three scheduled tasks untouched, one new script only so rule (a) owes no replay. **No ledger
rows**, on F-4's precedent. **Standing jobs both ran first with no new input**: A-5 part 2 at 66
fills / +2.22 bps / se 0.80 / |diff|/se 0.90; `daily_fills.py` 10 fills / $2.37M / +1.7 bps
(se 5.3), `ref_price` the previous close **10 of 10**, still the benchmark-availability artifact
(2026-09-11's closes unpublished, today's four fills NaN). **What it changes for the loop**: the
reusable rule is that **a directional intraday book must be quoted against an always-long control
on the identical windows before its gross column may be called momentum** - the time-series twin
of the vol-matched control S-15/S-16/S-20 made compulsory on the daily sleeve. Applied backwards
it closes F-4's loose end: the arithmetic that opened F-5 is refused, so the CME purchase case
keeps the cost table and the 0.62% gross sd per contract and **loses this third leg too**.

Status 2026-09-12 01:0x UTC (F-4): **the afternoon reversal is refused, and it is refused on SIGN
rather than on cost - on 6,654,000 legs over 2,664 sessions the day's move extends, it does not
fade, and the only gross statistics past |t| = 2 anywhere in the grid are momentum.** F-2a opened
F-4 as the last item with a stated mechanism, on the strength of two by-products pointing the same
way: X-1's **-0.69 bps at t -2.80** into 14:30 on 2,684 sessions of equities and F-2a's **-2.415 at
t -2.56** into the close on 313 sessions of ES. New `scripts/sweep_f4.py`; store `data/minute_alpaca`,
universe the **56 names the intraday sleeve may trade** (50 megacaps + PLTR/MSTR/COIN/SMCI/SOXL/SOXS,
disjoint from the daily champion), 2016-01-04..2026-09-09; **seven clauses pre-registered in the
docstring before the first number**, including clause (5) which wrote the expected outcome down
first - *failure on cost, not on sign* - and clause (6) which put A-10's prior refusal of the
deployed form (**-$468/day at t -7.38**) on the record rather than leaving it to be rediscovered.
**(1) A clean refusal: 0 of 96 cells** (12 entry minutes x 2 books x 2 exits x 2 signs), with
**all 96 net columns negative** - best raw momentum at 11:30, **-2.35 bps at t -2.74** against a
pooled **4.59 bps** round trip (4.90 in 2016-2019 falling to 4.26 by 2024-2026, because per-share
commission shrinks in bps as prices rise). **(2) Clause (5) is itself refused, and that is the
finding.** The gross column is **positive at 12 of 12 entry minutes in the directional book and 10
of 12 in the dollar-neutral one**; every gross statistic reaching |t| > 2 is **momentum** - neutral
11:30 **+1.78 at t +3.54**, raw 11:30 +2.24 at +2.61, raw 15:00 +0.89 at +2.48, neutral 10:00 +1.56
at +2.39 - and the largest single-regime cell in the file is **2020-2023 at 15:00, +2.18 at t +3.38
(neutral +1.20 at +3.63): A-10's exact entry minute with the opposite sign.** The second screen -
effect present but unaffordable? - returns **0 of 48**. **(3) Where the sign survives it is a
whisper and only in the labelled diagnostic book**: neutral afternoons, 2024-2026 **-0.81 / -0.59 /
-0.42 bps** at 14:00 / 14:30 / 15:00 (**t -1.11 / -0.98 / -0.85**), 2016-2019 -0.22 / -0.16, against
2020-2023 at +0.87 / +0.24 - two of three regimes carrying the sign at a fifth to an eighth of cost
and never past |t| = 1.2. **This does not contradict X-1, it fails to reach it**: X-1 ranked a
15/30/60-minute lookback held 30-60 minutes, F-4's signal is the whole session's return held to the
flatten, so they are different objects and the session-long one is not there. **(4) The
counterfactual that corrects F-2a's own closing sentence**: hold the measured gross fixed, swap the
cost column for **F-2a's 0.488 bps ES round trip**, and the same legs give **0 of 24** with **every
cell still negative** (-0.37 neutral 14:30 to -2.73 raw 11:30). **A cost refusal is an argument for
a cheaper instrument only when the gross column has the right sign at |t| > 2; when the sign is
wrong, the cheap instrument buys a smaller loss rather than an edge.** F-2a's cost table stands - it
is a property of the instrument - but the purchase case may not lean on F-4. **(5) Stage 2 was not
run, on clause (7) rather than on convenience**: a framework run is earned by a stage-1 survivor and
there is none on three screens; a confirmation year was started and abandoned at >30 minutes per
year because it would have been fitting an already-refused book, and A-10 has run the deployed form
on 2,686 sessions in any case. **No ledger rows**: `record` is reached only from stage 2, and a
stage-1 event study measures bars rather than running a strategy. **Nothing shipped, nothing
promoted, no default changed**: champion unchanged at S-18, `champion.json`, `live/*` and all three
scheduled tasks untouched, `late_momo` still at alloc 0.0 and its module not edited, one new script
only so rule (a) owes no replay. **Standing jobs both ran first**: A-5 part 2 unchanged at 66 fills
/ +2.22 bps / se 0.80 / |diff|/se 0.90; `daily_fills.py` 10 fills / $2.37M / `ref_price` the
previous close **10 of 10**, with the pooled execution number reading **+1.7 bps (se 5.3)** tonight
against +3.2 this afternoon purely because the daily store has not yet published 2026-09-11's
closes, so today's four fills score NaN - a benchmark-availability artifact, not an execution
change. **What it changes for the loop**: F-4 closes the last open item with a stated mechanism, and
on a stronger footing than F-1 or F-3, which found real forecasts and could not afford them. The
only thing left genuinely open on this line is the object F-4 did **not** test and X-1 did - a
**short** lookback reversal at a **short** horizon - which is a different mechanism needing its own
pre-registration. The binding constraint remains the owner decisions in `BLOCKERS.md`.

Status 2026-09-12 00:4x UTC (F-2a): **the futures blocker was never a permission problem - this
account already fetches ES/NQ/MES/MNQ minute history with zero errors - and the one number that
survives the thin sample is that an ES round trip costs 0.488 bps against the 4.70-8.20 bps every
intraday refusal in this repository was written on.** With the standing jobs holding no new input,
the owner decisions blocked and S-24 closing the auction question, this iteration took the last
open item with a stated mechanism: **F-2**, carried since 2026-09-10 as "needs owner: IBKR futures
permission + CME data, or a Databento key" and **never once probed**. New `scripts/futures_data.py`
(probe / depth / front-quarter stitch) and `scripts/sweep_f2.py`; **4 ledger rows** under
`futures/f2_es`; three clauses pre-registered in the docstrings before the first request, including
that a resolving contract definition is *not* evidence of a data grant. **(1) The claim is wrong.**
The paper account returned 2,760 one-minute TRADES bars - two full 23-hour sessions - for **all four
of ES, MES, NQ, MNQ with zero errors** (no 354, no 162, no 10197), plus daily bars. Nothing needs to
be bought for access. **(2) What is missing is retention, and one wrong turn established it**: the
first probe's "expired contracts are gone" was an artifact of a **guessed expiry date** (`20260619`;
the real third Friday is the 18th). By `localSymbol` the expired quarterlies qualify and serve full
data - **ESM6 7,740 bars / 5.9M contracts, ESH6 6,540 / 6.3M, ESZ5 7,455 / 5.5M, ESU5 6,600 / 4.4M**
- while **ESM5 and older return no security definition**, so IBKR retains about **four expired
quarters**. CONTFUT is not a way around it: it **refuses an `endDateTime` outright (error 10339)**
and caps a 1-minute request at one month, so it cannot be paged; daily CONTFUT is the one long
series (**ES 826 sessions from 2023-06-19**, NQ 633, micros 499). **(3) The store**: five contracts
used only in their own front quarter, rolling 8 days before expiry, **447,600 one-minute bars /
313 cash sessions, 2025-06-09..2026-09-10**. **(4) The durable result, because it is a property of
the instrument and not of the sample**: one ES contract carries **$347,117** of notional, IBKR Pro
charges **$2.05 a side** all-in and the book is one tick wide, giving **0.488 bps a round trip**
(0.856 at a full tick, MES 0.744) against **L-1's 6.40-8.20**, **X-1's 4.70** and **F-1's 0.892 of
commission alone at zero spread** - **10x to 17x cheaper**. That reframes every intraday refusal on
file: F-1's forecast was real (OOS IC +0.0113, t +4.74) and died at 0.797 gross bps against a 0.892
floor; on this instrument it would have cleared by 60%. **(5) Both pre-registered mechanisms are
refused**: overnight-into-the-open earns **+1.161 bps at t +0.78** to 10:00 and is gone by 11:00
(-0.316, then -0.431 to the close), and day-momentum-into-the-last-30-minutes is **-2.415 bps at
t -2.56** - the only significant statistic in the table, **with the sign reversed from the premise**.
**(6) The reversal is recorded and labelled post hoc** (+2.415 gross / **+1.927 net at t +2.05**,
win 57%, halves -3.93 / -0.92, so it is concentrated in the first half) - but the *direction* was on
record before this table existed: **X-1 measured the same shape on megacap equities on 2026-09-10**
(+0.63 bps at 10:30, **-0.69 at t -2.80** at 14:30) over 2,684 sessions and filed it as "worth
keeping for a later idea". **(7) On the mandate**: the cash session's gross sd is **0.62% of
notional per contract before any leverage decision**, against the intraday equity sleeve's 0.49%
(L-1) and 0.27% (X-1) *after* leverage - the first instrument measured here where the owner's
3-10%/day range is reachable without sizing up an unproven signal. **Nothing shipped, nothing
promoted, no default changed**: champion unchanged at S-18, `champion.json`, `live/*` and all three
scheduled tasks untouched, no runner-loaded file modified so rule (a) owes no replay. **Standing
jobs both ran first with no new input**: A-5 part 2 at 66 fills / +2.22 bps / se 0.80 / |diff|/se
0.90, `daily_fills.py` at 10 fills / $2.37M / +3.2 bps (se 4.5), `ref_price` the previous close 10
of 10. **What it changes for the loop**: `BLOCKERS.md`'s futures request is rewritten from "needs
data" into a priced one - **CME history back to ~2016 for ES/NQ (Databento MDP-3 or equivalent),
not an IBKR permission** - and the reusable rule is that **a blocker nobody has probed is an
assumption**, which on this one was wrong in its subject (permission, not retention) and understated
in its value (the reason to buy is a 0.488 bps round trip, not any backtest above).

Status 2026-09-11 22:5x UTC (S-24): **the daily store's close is the official closing cross to the
cent and its open is not the opening cross - and once the pre-open book is filled at the price a
real MOO order actually receives, the move the owner is being asked for is worth +1.98 CAR points
rather than +2.13.** S-23 closed with one unmeasured assumption and an explicit instruction not to
re-open it *from that data*: the surcharge the opening auction might charge over the closing one,
bounded at a 3.10 bps breakeven and proxied by minute *ranges* (1.0x-2.0x) because the Alpaca
minute store carries no quotes. This iteration used different data - the same key serves
`/v2/stocks/auctions` (official cross prints, 2016-2026) and `/v2/stocks/quotes` (full SIP NBBO),
neither of which this repository had ever touched. New `scripts/sweep_s24.py`; **4 ledger rows**
under `daily/s24_auction`; three clauses pre-registered in the docstring **before any fetch**.
**(1) The identity clause failed, and how it failed is the finding**: only **82.18%** of sessions
match within 2 bps against the pre-registered 95%, and splitting the test by leg says why - the
implied *close* factor `store_close / sip_close` has a median day-over-day change of **exactly
0.000 bps for all nine names** while the implied *open* factor wobbles 0.6-1.5 bps a day for six of
them. **Yahoo's daily open is the first consolidated print, not the primary auction**; the deployed
15:45 convention has always been marked at exactly the right price, and the defect lands entirely
on the pre-open book. A useful instrument check came free: picking the official cross as "the
largest print by size" independently recovered each fund's listing venue (Arca for seven, NASDAQ
for QQQ/TLT) with no hard-coded table. **(2) So the surcharge was measured rather than estimated.**
The exact close leg makes `f = store_close / sip_close` recover each date's whole adjustment, so
`sip_open x f` puts the real cross on the book's basis and S-19's `simulate` needs no change.
On 2,683 sessions: deployed **22.007%**, pre-open at the store's open 24.134%, **pre-open at the
official cross 23.985%** - the benchmark defect costs **-0.149 CAR points** (paired -0.047 bps/day,
t -1.86), **8% of the move**. And it is the conservative end: an MOO order is matched in a call
auction and **crosses no spread**, so the 2 bp charged to that row is an overcharge; charged
nothing it earns **25.204%**, making the honest range **+1.98 to +3.20** and the recommendation
+1.98. **(3) The pre-registered clause-2 statistic was mis-specified and the placebo is what caught
it.** On 6,074 NBBO rows the opening cross sits **6.12 bps** from the mid 30 seconds later, which
read naively is a 5.75 bps surcharge that would refuse the move - but an unsigned deviation has no
direction, and the *next* 30 seconds with no auction in them move the same names **4.10 bps**.
Signed, the cross sits **-0.213 bps** from fair value with mixed signs. The arithmetic closes it
without the quotes at all: at S-17's **0.68 CAR points per bp**, a real 6.1 bps auction cost would
be worth ~4.2 CAR points, and re-filling the book found 0.149, i.e. **~0.22 bps** against a 3.10 bps
breakeven - **7% of the budget**. **What the quotes do establish is operational, not economic**: the
quoted spread at 09:30:00 is **4.63x** the closing one (XLK **12.7x**, XLE **11.7x**), far worse
than the range proxy, decaying within 30 seconds - not what an MOO order pays, but exactly what a
*fallback* market order would pay, which raises the value of S-23's 09:28 clock guard.
**Nothing shipped, nothing promoted, no default changed**: `--order-type` still defaults to `MKT`,
champion unchanged at S-18, `champion.json`, `live/*` and all three scheduled tasks untouched, and
no file either runner loads was modified, so rule (a) owes no replay and the I-1 gate is unaffected
(S-19's precedent). **Standing jobs both ran with no new input** (S-23 had already pooled today's
session): A-5 part 2 at 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90, `daily_fills.py` at 10
fills / $2.37M / +3.2 bps (se 4.5), `ref_price` the previous close 10 of 10. **What it changes for
the loop**: the owner's cheapest decision is now fully priced with nothing left to assume, and the
reusable rule is that **an execution cost on this sleeve must be measured with a sign, or by
re-filling the book - never as an unsigned distance**, because an unsigned distance is mostly
volatility and the placebo proves it.

Status 2026-09-11 21:5x UTC (S-23): **the pre-open MOO path is written, clock-guarded and gated, and
the move it buys survives up to 3.1 bps of extra opening-auction cost - which the only evidence
available says is roughly what the opening auction might charge.** With the instrument audit closed
by S-22 and no open research item that is not blocked on the owner or on data the human must buy,
this iteration took the top item on the corrected priority list: the **pre-open task move**, the
cheapest and best-priced of the owner decisions at +1.85 CAR points. Two things were missing from
it and neither was a strategy question. **(1) The loop's half had never been written** - the page
has been promising `--order-type` OPG/MOO support since S-17, so the owner was being asked to
schedule a run the runner could not execute. **(2) Every version of the +1.85 assumed the opening
auction fills as cheaply as the closing one**, which is the assumption a reasonable person pushes
on. New `scripts/sweep_s23.py`, one new order type on `scripts/paper_trade.py` and a reference-price
fix on `scripts/daily_fills.py`; **4 ledger rows** under `daily/s23_preopen`.
**(1) Written and proved**: IBKR has no "MOO" order type - an opening-auction order is a `MKT`
carrying `tif="OPG"` - and it rejects `OPG` outside **04:00-09:28 ET** one order at a time, which
would leave the book half rebalanced, so the flag **checks the clock before it connects and
refuses** (verified live at 17:51 ET, exit 3, no socket opened). MOO/MOC fills are no longer waited
on, because they settle at an auction that has not happened yet. **(2) The payoff, reproduced on an
independent path**: both books fully charged (2 bp + IBKR Pro financing) through S-19's share-level
harness, the deployed row lands on S-22's **19.640%** to the digit, and pre-open earns **21.515%**
(**+1.875**); at today's cost of money 19.102 -> 20.946 (**+1.844**). Paired **+0.609 bps/day at
t +1.44**, so **nothing here reaches |t| = 2**, exactly as S-19 said; the gain is out-of-sample
weighted **more than three to one** (IS +0.963, OOS +3.222) and it costs a little risk this time
(DD 24.33 against 24.04, and $14.5k more financing, because an earlier fill carries the position a
session longer). **(3) The number this iteration exists for**: solving for indifference, **the
opening auction may cost up to 3.10 bps MORE than the closing auction (2 -> 5.10 bp all-in) before
the move stops paying**, 3.07 at today's rates - against a **measured +3.2 bps** of live 15:45
execution cost, so the opening auction would have to be about twice as expensive as the closing one
for the move to be a wash. **(4) And it might be.** The one read the data supports is a proxy -
Alpaca minute bars carry no quotes - but on 2,687 sessions the **opening minute is 1.0x to 2.0x as
wide as the closing minute** (SPY 1.04, QQQ 1.54, **IWM 2.00**, TQQQ 1.61) and thinner in every
name. At the 2.0x end the move is a wash rather than a gain. The proxy overstates the risk (a
minute's range is continuous trading; an MOO order fills in the opening *cross*), but **the margin
is thinner than +1.85 alone suggests and this is the first time anything has been put on the other
side of the trade**. The recommendation is unchanged - the defect is certain while its price tag is
not - and `daily_fills.py` now scores MOO fills against the **open** they aim at, so the first
post-move session measures whether the 1.85 was collected. **Nothing shipped, nothing promoted, no
default changed**: `--order-type` still defaults to `MKT`, the `--mock --dry-run` plan is identical
to before the change, the **I-1 gate passes 3,689/3,689 at 5,021 orders**, champion unchanged at
S-18, `champion.json`, `live/APPROVED_PAPER.md`, `live/HALT*`, `live/intraday_config.json` and all
three scheduled tasks untouched, and `signals.py`/`main.py` were not modified so rule (a) owes no
replay. **Standing jobs both ran first with no new input** (17:3x ET, after the S-22 iteration had
already pooled today's session): A-5 part 2 at 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90,
`daily_fills.py` at 10 fills / $2.37M / +3.2 bps (se 4.5), `ref_price` the previous close 10 of 10.
**What it changes for the loop**: the owner's cheapest decision is now a one-line task change with
the loop's half already merged and gated, and the reusable rule is that **an execution change on
this sleeve should be quoted as a breakeven in the units `daily_fills.py` measures**, not as a CAR
delta against a costless counterfactual.

Status 2026-09-11 21:0x UTC (S-22): **the three instrument corrections are independent, they
compose, and the deployed daily book should be expected to earn about 20% CAR rather than the
champion's headline 24.4%.** S-17 (spread), S-19 (clock) and S-21 (financing) each priced one
harness defect alone; nobody had charged them together, and the owner had never been given one
number for the paper account. New `scripts/_s22_runs.sh` (7 LEAN cells) and `scripts/sweep_s22.py`
(`--report` = the 2^3 factorial and the composition test, `--book` = the pandas book), plus **one
optional argument on `scripts/sweep_s19.py`** (`simulate(..., financing=...)`, default `None`, so
every S-19 row stays bit-identical - the clean cells reproduce 24.077 / 22.192 / 20.965 to the
digit); **25 ledger rows**, control reproducing **`OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`**.
**The rule was pre-registered in `_s22_runs.sh` before any cell ran**, and its second clause wrote
down the answer first: composing the three singles multiplicatively predicts **18.81%** for the LEAN
triple, and the test was whether the measurement landed within 0.5 CAR points of it. **(1) It
landed within 0.026.** Full period: control 24.403 / spread 23.068 / financing 23.087 / clock bound
21.384 / spread+fin 21.745 / spread+clock 20.074 / fin+clock 20.095 / **all three 18.785**, every
pairwise interaction inside **0.021 points**. **The three corrections are independent**, so the loop
may keep pricing defects one at a time and compose them afterwards - which is the reusable half of
the result. **(2) The headline needs the book LEAN cannot be**: the engine cannot fill at the close
of the session it decided in, so its triple overstates the clock. The S-19 pandas book with the new
financing hook agrees with LEAN's financing drag at the backtest convention (**-1.357 against
-1.316**) and its fully-charged `lag1` cell translates to **18.755 against LEAN's 18.785 - two
harnesses 0.03 CAR points apart**. On that footing the deployed 15:45 convention, charged 2 bp of
spread and IBKR Pro financing, earns **19.640% (19.954% in LEAN units), i.e. -4.449 points**, and
**19.415% at today's 3.63% cost of money (-4.988)**. **The promoted headline is about 18% high.**
**(3) Out-of-sample weighted, again**: the triple's halves are **IS 14.194% against 17.698%**
(-2.98% in wealth terms) and **OOS 24.259% against 32.801% (-6.43%)**, more than two to one, for
S-21's reason. **And it costs return, not risk** - across the whole factorial drawdown moves
23.70 -> 23.00 and realized vol 0.155 -> 0.156. **(4) One owner number moves and it is not the risk
posture**: the pre-open task move is worth **+1.85 CAR points on an honestly-costed book at today's
rates** (19.415 -> 21.264), close to S-19's -1.9 on an uncosted one, precisely because the clock and
the two costs do not interact. **Nothing shipped, nothing promoted, no default changed**:
`S1_SLIPPAGE_BPS` 0.0, `S1_SIGNAL_LAG` 0 and `S1_FINANCING` off, champion unchanged at S-18,
`live/*` and the three scheduled tasks untouched, `signals.py`/`main.py` not modified so rule (a)
owes no replay, and the I-1 gate re-ran anyway at **3,689/3,689, 5,021 orders**. **Standing jobs**:
`daily_fills.py` **has new input** - the 15:51 TQQQ sale lands, pooling to **10 fills / $2.37M /
+3.2 bps (se 4.5)** with `ref_price` the previous close in **10 of 10**, a fourth confirmation of the
S-19 clock; A-5 part 2 unchanged at 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90 (~4.4 sessions).
One instrument note: `slippage_report.py` needs the default `python` (no `pyarrow` under `py -3.11`),
which is what AGENTS.md prescribes for utility scripts. **What it changes for the loop: the
instrument audit is finished.** Spread, clock and financing are measured, composed and proved
independent; there is no fourth defect of that class left, and every daily-sleeve number from here
should be quoted against ~20% rather than 24.4%.

Status 2026-09-11 20:0x UTC (S-21): **the champion has been borrowing half its equity for free
for twenty-one iterations, that is worth 1.32 CAR points full period and 2.03 out of sample, and
82% of the money was spent in the last four years.** With the unblocked work down to two standing
measurements and four owner decisions, this iteration took the next instrument audit in the
S-17 / S-19 line. The defect is read off the engine source: `DefaultBrokerageModel.cs:368` returns
`MarginInterestRateModel.Null`, whose `ApplyMarginInterestRate` has an **empty method body**, and
`InteractiveBrokersBrokerageModel` does not override it - **LEAN charges no interest on a debit
balance and pays none on a credit balance**. New `scripts/rates.py` (FRED `DFF` = IBKR's USD "BM",
plus the Pro tier schedule), `scripts/sweep_s21.py` (`--probe`, `--schedule`, `--report`) and
`scripts/_s21_runs.sh`; one knob on the shipped algorithm (`S1_FINANCING`, **default off**) with
`S1_FIN_SPREAD` / `S1_FIN_RATES`; **8 ledger rows**, control reproducing **`OrderListHash
a6d6224ce9c70091e5bfa8e96f046bf3`**. **Say first what it is not**: S-17 and S-19 found defects that
could be *fixed*; this one cannot. The paper account has been paying it since its first fill, the
runner is fine, and the only thing wrong was the expectation. **The rule was pre-registered in
`_s21_runs.sh` before any full cell ran** and its first clause is that charging a cost can only
lower CAR, so **nothing here is promotable and `evaluate.py` is not the judge**; the a-priori
estimate (~1.45 points) was written down first so the accrual could be wrong rather than merely
reported, and a 2023Q1 smoke run matched a hand computation ($1,010.88 against $975) before any
full cell was believed. **(1) The state**: a debit balance on **3,073 of 3,689 sessions (83.3%)**,
mean gross 1.250x, mean debit **0.410x of equity overall and 0.493x on debit days**, and **616
sessions in credit (16.7%)** - S-20's risk-off count arriving by a different route. LEAN's own
accrual reports the identical state (mean debit 0.493x, credit within 1.4% of the probe) and 11%
less interest paid, which is the direction compounding predicts. **(2) The calendar is the
finding**: simple drag by year runs 0.16-1.24 CAR points through 2022 and then **3.115 (2023) /
2.535 (2024) / 1.477 (2025) / 1.689 (2026)**; **$106,621 of the sample's $129,406 - 82% - was
incurred in 2023-2026**, so the forward number at today's 3.63% benchmark is about **2.0 points a
year, not 1.3**. **(3) LEAN**, charged to the cash book so it compounds into the next day's sizing:
full period **23.087% / 0.939 / DD 24.1%** against 24.403% / 0.994 / 23.7% (**-1.316**), at 2 bp
21.745% against 23.068% (-1.323), **IS -0.907 (16.791 vs 17.698) and OOS -2.027 (30.774 vs
32.801)** - **out-of-sample weighted more than two to one**, which matters because the OOS half is
the one the S-18 promotion leaned on. **No t-statistic is quoted and none should be**: unlike
S-19's clock this is a deterministic charge. **(4) Half of it is the cost of money and half is the
price list**: same cash path, only the rate moving, gives benchmark-only **0.559** simple points
against IBKR Pro's **1.106** (+0.50pp 1.356), and the markup is the half a larger account pays less
of. One honest correction to the run set: the LEAN `floor` cell (-1.50pp, 24.136%) is **not** the
benchmark - that shift puts the tranches above $100k *below* it - so 0.559 is the floor, not 0.267.
**(5) The one decision it moves, pre-registered as such**: the owner's Reg-T question *is* a
decision about the size of a margin loan and has been asked with the loan free. Budget 0.75 / 0.80
/ 0.82 reads **23.087 / 24.296 / 24.742 financed** against 24.403 / 25.903 / 26.474 unfinanced, so
**the reward for spending the buffer is overstated by about a fifth** and the Sharpe argument thins
six-fold (financed 0.939 -> 0.945 against unfinanced 0.994 -> 1.012) while drawdown still climbs
2.1 points. **It flattens, it does not invert** - `BLOCKERS.md` carries both columns and the
recommendation is unchanged. **Nothing shipped, nothing promoted, no default changed**:
`S1_FINANCING` stays off so the ledger stays on one scale (S-17's precedent), `signals.py` was not
touched so rule (a) owes no replay, `live/*` and the three scheduled tasks are untouched, champion
unchanged at S-18, and the I-1 gate re-ran anyway at **3,689/3,689, 5,021 orders**. **One
instrument fix**: `evaluate.py` now refuses any run recorded with `S1_FINANCING=on` as not
comparable - S-18's same-cost-model rule on a third axis, and note the direction, because this one
*understates* a candidate rather than flattering it. **Standing jobs both ran after the close**:
A-5 part 2 unchanged at 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90 (~4.4 sessions);
`daily_fills.py` **has new input** - today's 15:45 rebalance adds IWM/XLE/XLK for $720,338, pooling
to **9 fills / $2.14M / +3.9 bps (se 5.0)** against 6 fills / +2.9 bps, with `ref_price` the
previous close in **9 of 9**, confirming the S-19 clock for a third session. **What it changes for
the loop**: the daily sleeve's three instrument audits now read spread (S-17, 0.68 CAR per bp),
clock (S-19, -1.9, |t| < 2, fixable) and financing (**S-21, -1.32 full / -2.03 OOS / ~2.0 forward,
certain, not fixable**), and every future comparison between two *differently levered* cells on
this sleeve owes the financed column the way S-20 made the vol-matched column compulsory.

Status 2026-09-11 19:0x UTC (S-20): **the regime gate has had one off-state since S-1 - cash -
and giving it a second one adds 2.15 CAR points that the champion's own sizing machinery would
have paid more for. Refused.** With no open research item that is not blocked on the owner or on
data the human must buy, this iteration took the last thing on the daily sleeve that is neither a
ranker lever nor a risk-posture parameter. New `scripts/sweep_s20.py` (`--probe` measures the
*state*, `--report` reads the LEAN cells and adds a vol-matched column) and `scripts/_s20_runs.sh`;
three parameters on the shipped algorithm defaulting to the champion (`risk_off_sleeve` empty,
`risk_off_top_n`, `risk_off_exposure`) with `S1_RISK_OFF_*` overrides; **9 ledger rows**, control
reproducing **`OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`**. **The rule was pre-registered in
`_s20_runs.sh` before any cell ran**: pass `evaluate.py` at 0 bp *and* 2 bp, do not lose the OOS
half, and carry **TLT alone** as the a-priori control. **(1) The state**: the gate is off on
**590 of 3,690 sessions (16.0%)** in 29 episodes, median 15 sessions, longest 72
(2018-10-10..2019-01-24). Held a session forward, TLT earns **+1.68 bps/day (t 0.35)**, IEF +1.86
(0.96), **GLD +9.92 (2.20)**, SLV +7.36 (0.97), HYG +0.92 (0.26) - and **SPY itself +6.57 (0.88)**,
so the gate is not avoiding down markets, it is avoiding the -10.94% day. **Nothing is conditional
on the crisis**: risk-off minus risk-on is +1.39 / +1.50 / +8.07 bps at **t 0.28 / 0.73 / 1.66**.
**(2) LEAN**: the primary (shipped momentum ranking over TLT/IEF/GLD, top 1) earns **26.550% /
0.972 / DD 25.4% / std 0.177** against the champion's 24.403% / 0.994 / 23.7% / 0.155, i.e.
**+2.15 CAR at lower Sharpe and 2.2 more points of realized vol**; TLT alone 24.819% / 0.935 /
23.3%, top 2 of 3 25.968% / 1.004 / 25.4%, and the **post-hoc** GLD-alone cell 27.735% / **1.040** /
25.4%. The halves both gain (**IS 19.135% / 0.915 / 21.3** against 17.698 / 0.911 / 23.7, **OOS
35.905% / 1.074 / 25.4** against 32.801 / 1.108 / 23.3). **(3) The refusal is on the vol-matched
column, which S-15 made compulsory here**: scaling the control to each cell's own realized vol,
the excess is **primary -1.317, primary at 2 bp -2.885, a-priori TLT -2.103, top 2 -0.009** and
only the post-hoc GLD cell is positive (+0.656) - **every pre-registered cell is worse than simply
running the existing book bigger**. Paired daily: primary **+0.90 bps/day at t 0.83** (risk-off
sessions alone +4.85 at t 0.73), and the risk-on column **+0.15 at t 0.56**, which is the proof the
change touches only the state it claims to. `evaluate.py` **refuses the primary at 0 bp** (drawdown
25.400 against 23.700 + 1.0) and returns **"BEATS champion" at 2 bp** (24.982 vs 23.068) - the rule
required both, and unlike S-18's identical-looking split this refusal is a 0.7-point drawdown miss
with a falling Sharpe, not 0.001 CAR points. **(4) One instrument fact, worth more than the cell**:
`risk_off_exposure` is **inert over [0.5, 1.0]** - LEAN reproduced the 1.0 cell to every digit at
0.5 - because the vol target's `target_vol / sigma` exactly cancels an exposure request under a
flat margin budget; it only bites once `scale_cap` binds (0.25). That is S-8's finding restated for
the off-state and is now in the `Params` docstring. **Nothing shipped, nothing promoted, no default
changed**: champion unchanged at S-18, `live/*` and the three scheduled tasks untouched, and the
**I-1 gate was re-run because `signals.py` is a file the paper runner loads** - `compare_orders.py`
passes **3,689/3,689 at 5,021 orders**, unchanged from the S-18 baseline. **Standing jobs ran with
no new input** (14:5x ET, before the intraday close and before the 15:45 rebalance): A-5 part 2
unchanged at 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90 (~4.4 sessions to settle),
`daily_fills.py` unchanged at 6 fills / +2.9 bps. **What it changes for the loop**: S-15 (the
ranker), S-16 (the proxies and the breaker) and S-20 (the off-state) are three forms of one
finding - **on this sleeve anything that looks like new return is a size decision until it beats
the vol-matched control** - so that column belongs in every future daily-sleeve comparison, and the
binding constraint remains the owner's size question in `BLOCKERS.md`.

Status 2026-09-11 18:1x UTC (S-19): **the largest unblocked number on the daily sleeve was measured
on a strategy that no longer exists and with an instrument that could only bound it; re-measured, the
deployed runner's clock costs about 1.9 CAR points rather than 4.75, and nothing in the comparison
reaches |t| = 2.** With no open research item left that is not blocked on the owner or on data the
human must buy, this iteration took the top unblocked ops number instead of a twelfth mechanism. New
`scripts/_s19_runs.sh` (six LEAN cells) and `scripts/sweep_s19.py` (a share-level book that runs the
shared `signals.py`, fills wherever it is told, and scores itself against LEAN's own equity curve);
**10 ledger rows**, control reproducing **`OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`**.
**(1) The bound, re-run on the promoted champion**: `S1_SIGNAL_LAG=1` earns **21.384% / 0.860 /
DD 22.7%** against 24.403% / 0.994 / 23.7%, i.e. **-3.02 CAR at 0 bp** and **-2.99 at 2 bp**, against
S-17's -4.75 on the retired 3x book - **the S-18 promotion cut the cost of the clock by 36%**, which
is what a return cost does when economic exposure falls from 2.25x to 1.50x. The ladder is concave
(lag 1 costs 3.02, lag 2 a further 0.97) and the halves both lose, out-of-sample weighted (IS 16.443
vs 17.698, OOS 27.431 vs 32.801). **(2) The exact convention, which LEAN cannot express**: a daily
bar for D arrives stamped `D 16:00`, so nothing submitted then can fill at D's close, and
`S1_SIGNAL_LAG=1` is therefore one whole overnight gap staler than the deployed path rather than
equal to it. The pandas book prices all three - **backtest 24.077 / deployed 22.192 / lag1 20.965**,
paired **-0.599 bps/day (t -1.41)** and -0.994 (t -1.86) - after validating at **corr 0.99650**
against the control's own LEAN equity curve (annualized std 0.1863 / 0.1872, tracking sd 9.86
bps/day). **The deployed clock is 61% of the bound**, and the two harnesses agree to **0.09 CAR
points** on the one cell both can run, so **-1.9 CAR** is the number and it replaces -4.75 in
`BLOCKERS.md`. **(3) One instrument finding, in S-17's line**: LEAN reports Annual Standard Deviation
**0.155** and Sharpe **0.994** for a curve carrying **0.186** of trading-day volatility - resampling
onto *calendar* days reproduces 0.157 - so **every Sharpe in the ledger is on a calendar-day basis
and biased down by ~17%**. Cross-cell comparisons inside the ledger are unaffected; comparing a LEAN
Sharpe against one computed anywhere else is not safe, and `sweep_s19.py --validate` prints the
warning with both tables. **Nothing shipped, nothing promoted, no default changed**: champion
unchanged at S-18, `live/*` and the three scheduled tasks untouched, only two new scripts added so
rule (a) owes no replay and the I-1 gate is unaffected. **Standing jobs both ran**: A-5 part 2 has
new input - today's session adds **34 fills at +0.94 bps**, pooled **66 fills / +2.22 bps / se 0.80**
against the shipped 1.50, `|diff|/se 0.90`, ~4.4 sessions to settle; `daily_fills.py` unchanged at
6 fills / +2.9 bps (this ran before the 15:45 rebalance). **What it changes for the loop**: the ops
decision the owner holds is worth less than it looked and is still worth taking, and the honest
framing is that the defect is certain while its value is not.

Status 2026-09-11 17:1x UTC (F-3): **the supervised track is closed, and it closes on a comparison
rather than a tally: at a daily horizon the model's ranking is six times weaker than the momentum
blend it was built to replace, and the champion's own signal is worth 61.5 bps per dollar it turns
over.** The top item, opened by F-1's refusal, which was arithmetic and not a verdict: 0.797 gross
bps against a 0.892 bps floor at 13.8x daily turnover. F-3 ran the identical method where the
turnover is a hundredth. New `scripts/sweep_f3.py` (panel, walk-forward GBDT, book simulation,
falsification control, ridge baseline, `--diagnose`), a **128,882-row panel over 22 ETFs x 6,718
sessions** with 41 causal features, an exported forecast (`data/f3/ml_scores.csv`, 3,692 dates),
two defaulted-off knobs on the shipped algorithm (`S1_ML_SCORES`, `S1_ML_MODE`), an OHLC loader on
`lean_prices`, and **12 ledger rows**. Universe is the ETF sleeve **only** - the 50 megacaps are
excluded features and all, because that list is the 2026 survivor set (S-7). Selection on
train <= 2007 -> validate 2008-2011 picks the 5-day horizon in every cell; the walk-forward then
covers **2012-2026, the champion's own window**, retrained yearly on <= Y-2, so the LEAN comparison
is directly against `champion.json`. **The date convention was proved, not assumed**: `main.py` now
logs the history frame's last bar, and a two-month run shows `last_bar=2012-01-03 16:00:00` with
the store's own close, so an exact-date join of a score built from bars <= D is causal.
**The forecast is real and tiny**: pooled out-of-sample **IC +0.01133 at t +2.17**, but gross P&L
**t +0.18** and only **0.304 bps per dollar turned** - *less* than F-1's 0.797 - and the **ridge
baseline scores a higher IC than the tree (+0.01223)**, the opposite of F-1, so there are no
interactions to earn the complexity. Six of fifteen test years have negative IC. **LEAN refuses it
on every criterion, three times**: ML ranking with the champion's gate **10.322% / 0.408 / DD
36.6%**, with the ML gate 9.908% / 0.385 / 35.6%, and with no floor on the ML score at all (the
cell that answers "was it the gate?") **11.400% / 0.461 / 36.0%** - against the champion's 24.403%
/ 0.994 / 23.7%, and worse than S-15's *no ranking at all* (17.7%). **The diagnosis is the keeper**:
on the nine names the sleeve actually ranks, the forecast scores **IC +0.00691 (t +0.97)** against
the momentum blend's **+0.04268 (t +5.43)**, in both halves, with the two scores only **+0.091**
rank-correlated; as unlevered top-3-of-9 books the forecast earns $305/day at 9.29 bps per dollar
turned on 486k/day, the momentum blend **$617/day at 61.51 bps on 105k/day**. **Nothing shipped**:
control reproduces **`OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`** (5,128 orders, 24.403%,
$27,199.76) and the I-1 gate passes **3,689/3,689 at 5,021 orders**, so the knob is inert on the
deployed path; `live/*` and the scheduled tasks untouched; champion unchanged at S-18.
**One instrument defect fixed**: the two-month convention run annualizes to 47.3% CAR / 1.2% DD on
71 orders and `evaluate.py` would have called it "BEATS champion" - it now refuses any run whose
recorded environment moved `S1_START`/`S1_END` as not comparable, S-18's rule applied to the window
instead of the cost model. **Standing jobs both ran with no new input** (12:3x ET, before the
rebalance): A-5 part 2 unchanged at 58 fills / +2.42 bps / se 0.88 / |diff|/se 1.04 (~5.5 sessions
to settle), `daily_fills.py` unchanged at 6 fills / +2.9 bps. **What it changes for the loop**:
F-1 and F-3 together price the whole supervised class - the model finds IC ~ +0.011 wherever it is
pointed, and what decides its worth is the edge-to-cost ratio of the mechanism it rides, which on
both sleeves is weaker than what already ships. **The backlog holds no open research item that is
not blocked on the owner or on data the human must buy**; the top unblocked number is still the
runner's clock at -4.75 CAR.

Status 2026-09-11 15:5x UTC (F-1): **the machine learning track finds the first positive
out-of-sample gross edge the intraday side of this repository has ever produced, and it is worth
about half of its own commission.** The top backlog item, and the one mechanism class the loop had
never tried. New `scripts/sweep_f1.py` (panel builder, walk-forward GBDT, book simulation,
falsification control), a cached 1.59M-row panel over **56 tradable names x 2,682 sessions x 11
decision points**, 38 causal features, 5 ledger rows under `intraday/f1_gbdt`; `scikit-learn`
1.9.1 installed. Train 2016-2021, validate 2022-2023 (hyperparameters only), test 2024-2026 with a
yearly expanding retrain. **The signal is real**: pooled out-of-sample IC **+0.0113 at t = +4.74**
and gross **+$1,102/day at t = +3.04**, against a falsification control (labels shuffled within
each timestamp) at IC +0.0031 and gross **0.071 bps** per dollar turned - a ninth - and a ridge
baseline that finds almost nothing (validation IC +0.0027 vs the tree's +0.0105), so it lives in
the interactions. **And it is refused on arithmetic that no execution can reach**: the book turns
**$13.8M/day on $1M**, and per dollar traded it earns **0.797 bps against 0.892 bps of commission
and regulatory fees - at zero spread**. Breakeven slippage by decile: 0.04 **+0.129 bps**, 0.10
**-0.095**, 0.20 -0.229, 0.34 -0.360; the one cell that clears commission does so by 0.129 bps
against a half-cent tick worth 0.3-1.0 bps, and its worst day is **-$81,038** on a $1M book, past
the sleeve's own 2.5% loss limit. Net **-$2,206/day at t -6.02**, 0 of 3 test years positive,
**REFUSED** by the pre-registered rule. **The decay is the finding for the next step**: IC by test
year **+0.0192 -> +0.0113 -> -0.0001** and gross bps **1.293 -> 0.638 -> 0.293**, while permutation
importance is *stable* (rank correlation 0.66-0.77 across retrains, the same top features every
year: `vwap_atr`, its cross-sectional rank, `vol_rel`, `rng_atr`) - the model keeps its grip on
intraday VWAP reversion conditioned on relative volume and that mechanism's payoff is shrinking.
**Nothing shipped**: `live/intraday_config.json`, `live/APPROVED_PAPER.md`, `live/HALT*` and the
scheduled tasks untouched, no file either runner loads was modified, so rule (a) owes no replay;
champion unchanged at S-18's unlevered book. **What it changes for the loop**: F-1 is closed and
should not be re-opened as a feature, model or horizon question - the gap is a factor, not a
percent. The successor it opens is **F-3**: the same supervised method at a *daily* horizon on the
daily sleeve, where a hundredth of the turnover buys the same bps of edge. **Standing jobs both
ran**: A-5 part 2 now has **58 fills over 2 sessions** (+2.42 bps pooled, se **0.89**, |diff|/se
1.03 - today's 26 fills came in at +1.26 and halved the standard error; ~5.5 sessions to settle),
`daily_fills.py` unchanged at 6 fills / +2.9 bps because the 15:45 ET rebalance had not run.

Status 2026-09-11 15:1x UTC (S-18): **the champion is now the unlevered book - the first promotion
since S-12, and the first one whose case is risk rather than return.** S-17 left (e+g) at the
unchanged 0.75 budget as the top item with three missing pieces, each a run rather than a judgement;
all three are supplied. Eight new LEAN cells (`scripts/_s18_runs.sh`, read by `scripts/sweep_s18.py`)
plus three verification runs, 11 ledger rows. **The halves, which S-16 never ran** (candidate vs
champion, the windows S-12 itself was promoted on): IS 2012-2019 **17.698 / 0.911 / DD 23.7 against
19.180 / 0.884 / 25.1** (-1.48 CAR, paired -0.50 bps/day, t -1.25), OOS 2020-2026 **32.801 / 1.108 /
23.3 against 30.863 / 0.985 / 22.6** (+1.94 CAR, +0.58 bps/day, t +0.87); at 2 bp IS 16.349 vs
17.509 at **DD 25.0 vs 29.2** and OOS 31.477 vs 29.621. **So the return difference is out-of-sample
weighted and the risk difference holds in both halves** - the mirror image of S-15's reading of
S-12's tilt - while **nothing in the comparison reaches |t| = 2** and the full-period return
statistic is +0.05 bps/day at t +0.12. **What `evaluate.py` compares against is answered in code**:
`backtest.py` now records the `S1_*` environment with every run, `champion.json` carries
`stats_by_spread` (one column per cost model, each with its own `run_dir`), and `evaluate.py` picks
the column matching the candidate's own `S1_SLIPPAGE_BPS` and **refuses a run at a spread it has no
column for**. The gate then produced both verdicts: **2 bp BEATS champion** (23.068 / 0.938 / 25.0
against 22.926 / 0.865 / 29.2), **0 bp refused by 0.001 CAR points**, and the promotion was made on
the 2 bp row. **The two no-ops held**: the shipped defaults reproduce the tested cell exactly
(**5,128 orders, 24.403%, 0.994, 23.700%, $27,199.76, new `OrderListHash
a6d6224ce9c70091e5bfa8e96f046bf3`**) and `S1_PROXY=on S1_DD_HALVE=0.15 S1_DD_FLAT=0.25` reproduces
the retired champion bit-for-bit (**5246804e17a67af90028ffceead7d3b3**), which needed one structural
fix - `margin_requirement` reads `LEVERED_PROXY_3X`, because IBKR's 100% on TQQQ is a fact about
TQQQ and not about whether this strategy holds it. **I-1 gate re-run**: `compare_orders.py` passes
3,689/3,689 at 5,021 orders both sides, and `--mock --dry-run` plans XLE/XLK/IWM at 1.50x gross with
margin 0.75 - expect the next 15:45 ET paper session to rotate out of TQQQ. **The band was measured
on the new book and NOT changed**: 0.03 is worth +0.064 CAR at 0 bp and +0.103 at 2 bp (t +0.58 /
+0.94), a fifth of S-17's +0.57 on the 3x champion, because most of what it used to save was the
proxy sleeve's vol-drift re-weighting. **The case, stated as it should be read: not more return -
the same return with 0.073 more Sharpe, 1.5 points less realized vol, 4.2 fewer points of drawdown
at 2 bp, 40% less commission and 1.50x economic exposure against 2.25x.** `margin_budget` stays
0.75, `S1_SLIPPAGE_BPS` stays 0.0, the signal and regime filter are untouched, and `live/APPROVED_PAPER.md`,
`live/HALT*`, `live/intraday_config.json` and the scheduled tasks were not touched. **Standing jobs
both ran**: `daily_fills.py` unchanged at 6 fills / **+2.9 bps (se 6.8)**; `slippage_report.py` had
**new input for the first time since A-5 part 2** - today's partial session adds 23 fills at +1.11
bps, pooled **+2.42 vs the shipped 1.50, |diff|/se 0.99**, still inside 2 se so the constant is
untouched (~6.1 sessions to settle). **What it changes for the loop**: the daily sleeve's remaining
levers are all risk-posture ones, and the owner's Reg-T buffer question is now worth *more* (the
unlevered book at budget 0.78 / 0.80 / 0.82 earns 25.307 / 25.903 / 26.474 at rising Sharpe), while
the largest unblocked number on this sleeve is still the runner's clock (-4.75 CAR, S-17). The top
open item is now **F-1**.

Status 2026-09-11 13:3x UTC (S-17): **sixteen iterations have judged the daily sleeve on a harness
that charges no spread, and the deployed runner trades a signal one session stale - which is worth
4.75 CAR points and is the largest number on this sleeve since S-9.** With no open research item
left, this iteration audited the instrument instead of the strategy. Two knobs on the shipped
algorithm (`S1_SLIPPAGE_BPS`, `S1_SIGNAL_LAG`, both defaulting to the champion), twelve LEAN cells
(`scripts/_s17_runs.sh`, read by `scripts/sweep_s17.py`), a new live-fill instrument
(`scripts/daily_fills.py`), 12 ledger rows, control reproducing **`OrderListHash
5246804e17a67af90028ffceead7d3b3`**. **(1) The zero spread is LEAN's default, not a choice**:
`DefaultBrokerageModel.GetSlippageModel` returns `NullSlippageModel.Instance` and the IB model does
not override it, while `EquityFillModel.MarketOnOpenFill` *does* apply a model when set. The ladder:
**24.404 -> 23.699 (1bp) -> 22.926 (2bp) -> 21.129 (5bp) -> 18.216 (10bp)** at drawdown **25.1 ->
27.2 -> 29.2 -> 31.7 -> 32.3**, i.e. **0.68 CAR points per basis point** (paired t -1.84 / -3.48 /
-9.32 / -10.27), which implies the book pays spread on ~68x its equity a year. **Every cross-cell
comparison in the S-track is therefore biased toward turnover, and the cells differ by 2.7x in order
count.** **(2) The measured cost**: `daily_fills.py` on the 6 paper fills / $1.42M gives **+2.9 bps
(sd 16.7, se 6.8)** against the 15:45 close the runner aims at - the same size as the intraday
sleeve's +2.89. **(3) The deployed runner is a session late**, proved not inferred: `paper_trade.py`
reads `yf.download(period="2y")` at 15:45 ET, whose last *complete* bar is the previous close, and
`ref_price` equals it in **6 of 6 fills** while the runner's own `plan` event has been logging
`as_of = D-1` all along. So the backtest reads closes through D and fills at the open of D+1, while
live reads through D-1 and fills at the close of D. `S1_SIGNAL_LAG=1` (a tight upper bound, one
overnight gap staler than live) prices it at **19.649% / 0.736, -4.75 CAR, paired -1.55 bps/day at
t -2.65**, and **18.592% with the spread on top** - it costs return, not risk (drawdown *improves*,
23.7 vs 25.1). The fix is the pre-open MOO convention, which needs the scheduled task moved and is
in `BLOCKERS.md`. **(4) The spread re-ranks S-16's frontier and frees one cell from the owner's
question**: S-16's (e+g) at the **unchanged** 0.75 budget was refused by 0.001 CAR points, and that
margin exists only at exactly zero spread - **0 bp -0.001, 1 bp +0.036, 2 bp +0.142**, with Sharpe
0.938 vs 0.865, drawdown **25.0 vs 29.2** and fees $24.9k vs $41.9k at 2 bp. The crossover is at
~0.03 bp against a half-cent tick of 0.27-0.77 bp. Its return edge is still t = +0.12: the case is
same return for less risk and less cost, not more return. **(5) The owner's no-trade-band question
is answered**: at 2 bp, band **0.03 earns +0.57 CAR (t +1.22) and 3.8 fewer points of drawdown**
than the shipped 0.01, while 0.08 gives it back (+0.09) - the direction is evidence now, the level is
still S-13's path luck. **Nothing shipped, nothing promoted, no default changed**: `S1_SLIPPAGE_BPS`
stays 0.0 because 2 bps rests on six fills with se 6.8 (A-5 part 2's rule), the champion is unchanged
at S-12, `champion.json`, `live/` and the scheduled tasks are untouched, and neither new knob is in a
file the runners load, so rule (a) owes no replay. **What it changes for the loop**: the post-S-16
conclusion that only owner decisions remained was true about strategies and wrong about the
instrument - **S-18** (promote the unlevered cell properly) and the runner's clock are both real work
that no owner answer blocks.

Status 2026-09-11 12:1x UTC (S-16): **the champion's 3x sleeve and its drawdown breaker are worth
exactly zero return between them, and three cells that pass `evaluate.py` are now sitting behind one
unanswered owner question.** S-15 removed each switch alone; S-16 runs the two that pointed the same
way together and asks what the unlevered book does when its lost exposure is bought back with
*account* leverage instead of *instrument* leverage. Nine full-period LEAN cells plus two
sub-periods, all `S1_*` overrides (`scripts/_s16_runs.sh`, read by `scripts/sweep_s16.py`), 11
ledger rows, control reproducing **`OrderListHash 5246804e17a67af90028ffceead7d3b3`**. **The
structural fact behind it**: IBKR charges 0.333 of margin per unit of economic exposure on a 3x ETF
against 0.5 on an ordinary one, so the proxies' whole contribution is that 2.25x of exposure fits
inside a 0.75 budget. **The dead heat**: proxies off *and* overlay off at the unchanged 0.75 budget
earns **24.403% against the champion's 24.404%** - paired **-0.00 bps/day, t -0.00 on 3,689
sessions** - at **std 0.155 vs 0.170, drawdown 23.7 vs 25.1, PSR 33.2 vs 23.0 and $27.2k of fees vs
$45.7k**. **The frontier**: spending the freed risk through the budget is a clean dial, 0.75 ->
0.78 -> 0.80 -> 0.82 giving CAR 24.403 / 25.307 / 25.903 / 26.474 at std 0.155 / 0.160 / 0.164 /
0.168 and Sharpe **rising** 0.994 / 1.003 / 1.008 / 1.012 (on the 3x book, O-1b measured Sharpe
falling with size). At budget 0.82 the unlevered book matches the champion's realized vol (0.168 vs
0.170) and earns **26.474% / 1.012 / DD 25.7**, i.e. **+0.66 bps/day at t = 2.02** - the first t
above 2 the S-track has produced *in favour of* a change. **In an unlevered book the breaker is
strictly harmful**: at budget 0.80, shipped overlay 24.551 / DD 25.5, widened to 0.20/0.30 25.333 /
DD **25.0**, off 25.903 / DD 25.1 - monotone in return, flat-to-better in drawdown, a shelf and not
a spike (S-8's re-arming problem: a step breaker that flattens at -25% sells the bottom).
**Nothing shipped, and this is not a refusal**: (e) at 0.80, (e+g) at 0.80 and (e+g) at 0.82 each
return **"BEATS champion"** from `evaluate.py`, and every one of them needs `margin_budget` above
0.75 - the open owner question from O-1b, which `BLOCKERS.md` records as not the loop's to move. The
budget-neutral cell is the one the loop could have promoted alone and it **misses by 0.001 CAR
points**. Champion unchanged at S-12, `champion.json`, `live/` and the scheduled tasks untouched,
new scripts only so rule (a) owes no replay. **What it changes for the loop**: the owner question in
`BLOCKERS.md` now carries a fourth option that dominates O-1b's option (b) - the same +1.50 CAR at
**lower** realized vol, the identical 25.1% drawdown and 31% lower fees - and until it is answered
there is no daily-sleeve work left that is not behind it. The gain is also one regime deep (IS +0.07
bps/day at t 0.24, OOS +1.36 at t 2.16), which the entry says out loud. A-5 part 2 had no new input
(ran 07:3x ET, before the open; still 2026-09-10 alone: 32 fills, +2.89 bps, se 1.33, ~6.8 sessions
to settle).

Status 2026-09-11 11:1x UTC (S-15): **71% of the champion's 24.4% CAR is no skill of any kind, and
not one of the switches the loop has spent six iterations tuning is distinguishable from zero.**
The attribution S-14 asked for: eight full-period LEAN runs, each the shipped algorithm with one
switch removed through an `S1_*` override (`scripts/_s15_runs.sh` runs them, `scripts/sweep_s15.py`
reads them), 8 ledger rows, nothing judged. Two new knobs default to the champion
(`S1_MIN_MOMENTUM`, `S1_PROXY`) and the control reproduces **`OrderListHash
5246804e17a67af90028ffceead7d3b3`** exactly. **The table**: champion **24.404% / 0.921 / 25.1% DD
/ 0.170 std**; (f) **no skill at all** - nine ETFs equal-weighted, unlevered, no ranking, no entry
gate, no regime filter, only the vol target, margin budget and overlay - **17.282% / 0.711**, i.e.
the entire signal stack is worth **+7.12 CAR at t = 1.37**; (a) no ranking 17.700% / 0.780 at std
**0.137**, and **vol-matched (a2, budget 0.93, std 0.163) 20.745%**, so **ranking is +3.66 CAR at
t = 0.92**, not +6.70 - a third of its apparent value is just that three names carry more vol than
nine, and the +2.20 bps/day it scores is S-14's +2.02 arriving by another route; (b) regime filter
off 22.383% but **drawdown 31.4%** and std 0.189, with an in-sample contribution of **exactly zero**
(-0.04 bps/day, t -0.03) - it is a drawdown instrument, not a return one; (e) **levered proxies off
23.128% at Sharpe 0.950, DD 23.6%, std 0.153, PSR 27.4% and $25.6k of fees** - better than the
champion on every risk-adjusted measure for 1.28 CAR, which is L-1's finding on the daily sleeve:
**3x instruments supply volatility, not edge**; (g) overlay off **25.998%**, so the breaker costs
**1.59 CAR** and is the only near-significant statistic in the table, against it (-0.51 bps/day,
**t -1.93**, OOS **t -2.35**), buying 2.1 points of drawdown; (d) S-12's allocation tilt +0.80 CAR
overall but **+0.52 bps/day (t 1.45) in 2012-2019 and -0.06 (t -0.10) in 2020-2026** - the last
promotion's edge is in-sample. **Nothing shipped, nothing promoted, nothing refused**; champion
unchanged at S-12, `live/` and the scheduled tasks untouched, all eight cells are env overrides so
rule (a) owes no replay. **What it changes for the loop**: further ranker tuning is the
lowest-value work available (+3.66 CAR at t = 0.92, and S-14 showed it does not survive dilution);
the two components with real effects - the **vol target / margin budget**, which produces 71% of
the return, and the **regime filter**, which produces the drawdown profile - are risk-posture
parameters, so they run into the open owner questions in `BLOCKERS.md`, not into another backtest.
A-5 part 2 had no new input (ran 06:3x ET, before the open; still 2026-09-10 alone: 32 fills,
+2.89 bps, se 1.33, ~6.8 sessions to settle).

Status 2026-09-11 10:3x UTC (daily review, no experiments run): **ten iterations, 82 ledger rows,
nothing shipped to a deployed file, and the backlog is out of mechanisms.** In 24 hours the owner's
3-10%/day list was measured in full and refused in full (O-1, O-1b, L-1, X-1, O-2), the A-track
spent its last two defences (A-12, A-11), S-2 closed the last open S-track mechanism, and S-14
priced the champion's own ranking edge at **+2.02 bps/day, t = 2.07**. The champion is unchanged at
S-12 and reproduced `OrderListHash 5246804e17a67af90028ffceead7d3b3` three separate times.
**Priority for the next 24 hours: (1) A-5 part 2 after the close** - today is only the second
session that can produce fills, and the slippage constant is ~6.8 sessions from settling against a
2.52 bps breakeven; **(2) S-15**, the return attribution, which is the only remaining question whose
answer cannot be guessed from the ledger; (3) per-session ops. One new ops blocker carried forward:
`live/alerts.json` does not exist, so all 17 alerts raised on 2026-09-10 were dropped and the
intraday log is the only alert surface. One process gap recorded: **L-1 wrote zero ledger rows**
(`sweep_l1.py` does not record) - wire the ledger call into the next sweep script. Full review in
`research/reports/2026-09-11.md`.

Status 2026-09-11 10:2x UTC (S-14): **breadth is refused - more candidates make the daily champion
monotonically worse - and the measurement behind the refusal found that the champion's entire
cross-sectional edge is +2.02 bps/day at t = 2.07.** With the backlog out of open mechanisms
(S-2 closed the last one), this iteration took the direction S-12 and the 2026-09-09 owner
decision both name and nobody had measured: the sleeve ranks **nine** ETFs and holds three, so
completing the GICS sector map should make the top three a real selection. Fetched 13 ETFs
through the D-1 pipeline (XLV XLY XLP XLI XLU XLB XLRE XLC EFA HYG IEF SLV VNQ, 1998-2026, all
validated; XLRE/XLC list mid-sample and enter only when they have a full lookback), added two
nested sleeve presets and `scripts/sweep_s14.py`; 7 ledger rows. **LEAN, full period: CAR
24.404% / Sharpe 0.921 (etf9, control) -> 17.253% / 0.663 (17 names) -> 11.622% / 0.430 (22
names)**, at unchanged realized vol (0.170 / 0.163 / 0.165), and `evaluate.py` refuses all four
candidates. The nearest candidate loses **both** halves (IS 12.626% vs 19.18%, OOS 22.929% vs
30.86%). **The decomposition is the keeper**: with leverage, the vol target and the overlay
switched off, the unlevered top-3 basket's return splits into the menu and the ranking spread -
etf9 **7.21 = 5.20 + 2.02 bps/day (t 2.07)**, sector17 5.73 = 4.90 + 0.82, broad22 5.27 = 4.32 +
0.94; paired, **-1.37 bps/day (t -1.95)** and **-1.89 (t -2.23)** against the champion, of which
only -0.30 is the worse menu and **-1.20 is the signal picking worse**. At `top_n=5` every spread
collapses to insignificance (etf9 **+0.84, t 1.16**), so **the edge exists only at top-3-of-9 and
every dilution costs it**. The steelman does not rescue breadth: `top_n=5` on the wide sleeve
recovers 2.4 points of CAR, and **vol-matched to the champion's own 0.17 std it still earns
22.879% / 0.872 against 24.404% / 0.921 on 8,279 orders against 4,735**. What breadth does buy is
a smoother path (unlevered drawdown 22.4% -> 14.3%). **Refused and closed; nothing shipped** -
champion unchanged at S-12, the control reproduces `OrderListHash
5246804e17a67af90028ffceead7d3b3`, `compare_orders.py` passes 3,689/3,689, `live/` and the
scheduled tasks untouched. Two defects fixed in `fetch_data.py`: the manifest was **rewritten**
rather than merged (69 entries erased by a 13-symbol fetch; restored and the merge verified) and
`--symbols <ONE>` crashed on yfinance's single-symbol column layout. **The successor is S-15**,
the uncomfortable question this raises: if 2 bps/day is the whole selection edge, most of the
champion's 24.4% CAR is levered beta plus the regime filter, and that attribution should be
measured before more work is spent on the ranker. A-5 part 2 had no new input (ran 05:3x ET,
before the open; still 2026-09-10 alone: 32 fills, +2.89 bps, se 1.33, ~6.8 sessions to settle).

Status 2026-09-11 09:3x UTC (S-2): **the index-ETF opening-range breakout is refused before the
LEAN build, and the thing that made it look profitable is the stop, not the signal.** S-2 has been
open since 2026-09-08 and was the last research item on the backlog with a stated mechanism that
is not parked, an owner question or infrastructure. Fetched SPY/QQQ/IWM from Alpaca SIP
(2016-01-04..2026-09-10, ~1.046M bars each; the store is now 63 symbols), built the event study
(`scripts/sweep_s2.py`) and confirmed it through the shipped harness; 3 ledger rows under
`intraday/orb`. **Stage 1, 2,687 sessions with nothing fitted, 16 breakout cells and their 16 fade
controls: 0 of 16 pass** the pre-registered rule and every cell loses - the best on net is
`orb15 mid e120` at **gross +2.11 bps/trip against a 3.65 bps round trip, net -1.54, -$113/day,
t -1.64**. **The finding is the symmetry**: the fade earns positive gross too, in **14 of 16
cells**, so gross splits into the part a signal owns, `(brk - fade)/2`, and the part both signs
share, `(brk + fade)/2`. The shared part is **positive in all sixteen cells (+0.33 to +1.43 bps)**
and is pure stop convexity - a stop plus a hold-to-close exit is convex in either direction, so a
coin flip collects it - while **the largest directional edge anywhere is +1.09 bps against 3.65
bps of cost (0.30x), and in 6 of 16 cells it is negative.** TQQQ, the leveraged read, is worse:
cost **4.85 bps**, 0 of 8, and in its best cell the breakout earns **+$33.78/day against its own
fade's +$33.79** - no direction left at all. **Stage 2 through the deployed framework** (shipped
ORB module, `--symbols SPY QQQ IWM`, 0.36x gross on $1M): **-$186 / -$211 / -$39 per day by
regime, 0 of 3**, and backing out costs, **+$11/day of gross over eleven years against $171/day
paid to collect it**. Stage 1's one optimism - closing an untouched trip at the last minute bar
rather than the auction - only helps the strategy, so the LEAN build S-2 asks for could only make
this worse. **Refused and closed; nothing shipped**; the only behaviour change is a research-store
fix (`alpaca_data.py --splits` **merged** instead of replacing - a bare run used to silently
rewrite the 60-symbol split table as 16 symbols over a 2024+ window, re-introducing the exact
cost-model defect A-10 fixed; all 60 pre-existing factors verified byte-identical). `live/` and
the scheduled tasks untouched; the rule-(a) replay of 2026-09-08 with the exact deployed config
reproduces the sleeve to the digit (34 trades, 368 decisions, flat, P&L -2,302 on 500k). Champion
unchanged at S-12. A-5 part 2 ran first as the standing job and **had no new input** (still one
session: 2026-09-10, 32 fills, +2.89 bps, se 1.33 vs the shipped 1.50, |diff|/se 1.05, ~6.8
sessions to settle it) because this ran at 04:3x ET, before the open. **The backlog now holds no
open research item with a stated mechanism**: A-8 is parked by A-4's power calculation, A-3 is
settled by A-10, D-2b and E-2b are infrastructure, and S-5 needs two sleeves with positive
expected return where there is one. Everything that remains is an owner decision in `BLOCKERS.md`.

Status 2026-09-11 08:3x UTC (A-11): **the impossible fills are real, four times larger than the
IBKR window showed, and they are not load-bearing - and the half of the universe whose fills *are*
real is the half that never made money.** A-5 flagged the sleeve's participation as a cost-model
defect; A-11 sizes it on 2,686 Alpaca sessions with the deployed allocation (ORB alone), one
backtest per (cell, year) from a fresh $1M book, 18 ledger rows. (The three sweeps ran to
completion at 03:40-04:03 ET in a preceding iteration that was cut off before writing anything;
this iteration verified them against the store, added the cost/gross decomposition and the paired
liquid-vs-illiquid statistics, replayed, and recorded. No sweep was re-run.) **The diagnostic**:
90,441 fills, notional-weighted **p50 1.46% / p75 4.71% / p90 18.80% / p99 950% / max 38,759%**
against A-5's 1.03 / 5.55 / 26.1 / 199, with **24.1% of notional filling at >5% of its minute,
9.7% at >20% and 4.1% (3,651 fills) at >100%** - orders bigger than everything that traded in the
minute they are booked at. The store is split-adjusted on price *and* volume (SMCI 2016-01-04:
4.34M adjusted shares at $2.39 = 434k real at $23.88), checked before anything was believed, so
these are real participations. **The cap** (clip to a share of the trailing-median volume of the
fill minute, knowable at decision time, worked over following bars): **$/day off -331 -> 0.10
-336 -> 0.05 -367 -> 0.02 -430**, paired t **-0.25 / -1.24 / -2.40**, against costs/day
**907 -> 917 -> 941 -> 969** - so at the 0.10 cap the backtester clips **213,338 orders** refusing
a cumulative **$4.78M/day** of intended notional (vs $3.59M/day executed) and the book moves
**-$5/day, of which +$10/day is the slicing commission: implied Δgross +$5**. **Outcome (c): the
defect is real and immaterial.** The fills nobody could get were not the ones making the money, so
every A-track number stands and `part_cap` stays 0. **The finding is the universe split**: as two
disjoint books, the **liquid 8** (AAPL/AMZN/META/MSFT/TSLA/NVDA/GOOGL/NFLX, 8.8% of notional above
5% of the minute) earn **-$195/day at t = -1.89**, the **most significant negative reading this
sleeve has produced**, while the **illiquid 8** (SMCI/SOXL/MSTR/SOXS/AVGO/PLTR/COIN/AMD, 45.8%)
earn -$164 at -0.83; paired difference -$31/day, t -0.18, corr 0.498. **And on the 261-session
fitted window - the sleeve's only positive evidence in eleven years - liquid 8 earn -$102/day and
illiquid 8 +$361/day**: all of it is in the half whose fills cannot be trusted (median order 4.12%
of its minute, p90 94%). **Refused and closed; nothing shipped**, only `scripts/sweep_a11.py`
changed (a `--label` flag); `live/intraday_config.json`, `live/APPROVED_PAPER.md`, `live/HALT*` and
the scheduled tasks untouched, and the deployed-config replay of 2026-09-08 reproduces the sleeve
exactly (34 trades, 368 decisions, flat, P&L -2,302 on 500k). Champion unchanged at S-12. A-5
part 2 had no new input (still one session: 2026-09-10, 32 fills, **+2.89 bps, se 1.33** vs the
shipped 1.50, |diff|/se 1.05, ~6.8 sessions to settle it). **The A-track is now out of both levers
and defences** - A-11 was the last "the backtest was unfair to it" argument, and it fails in both
directions. The open `equity_frac` question in `BLOCKERS.md` is all that is left on this sleeve;
A-11 is appended there as evidence.

Status 2026-09-11 04:5x UTC (A-12): **the ORB whipsaw lockout is refused, and the event study that
refused it found the sign inverted - the reversal re-entry is the sleeve's only profitable trade
category.** The 2026-09-10 paper session lost 77% of its -6,779 in one stopped-out-then-flipped
pattern in semis, which the shipped module permits because `max_entries` is counted per *side*. New
`reentry_block`/`reentry_mode` on the ORB module (default **0 = off**) and `scripts/sweep_a12.py`;
18 ledger rows. **Stage 1, 44,219 round trips over 2,686 sessions with nothing fitted**: the
session's first entry earns **-$25/trip (t -2.66, total -$872,347)**, the `flip` re-entry **+$15
(+0.65, +$70,708)** and the `same` continuation -$20 (-1.03); **98% of the sleeve's loss is in first
entries**, which no re-entry filter can reach. The whole effect lives in the **first fifteen
minutes** and points the other way: gap 0-15 is **flip +$78/trip (t +1.72)** against **same -$81
(t -1.96)**, and every longer bucket is flat (|$| <= 26, |t| <= 0.66). **Stage 2, the paired grid
(5 cells, one backtest per variant-year, 2,686 sessions): 0 of 5 pass.** The two cells with the
hypothesised sign lose - flip15 **-$31/day (t -1.17)**, flip60 **-$47 (-0.93)** - and the only
positive cell is the falsification control, `same15` **+$38/day at t +1.69, 0 of 3 regimes**, chosen
after seeing the gap table and worth 0.1 trades/day. Deployability fails for all: control
**-$331/day (t -1.35)**, best variant -$293 (-1.19). **A free measurement fell out**: this control
is the first full-sample run since A-5 part 2 charged the sell-side regulatory fees, and with
trades/day identical to A-10's rows the whole delta is cost - **ORB alone -$289/day -> -$331/day**.
**Refused and closed; nothing shipped**, `live/intraday_config.json`, `live/APPROVED_PAPER.md`,
`live/HALT*` and the scheduled tasks untouched, and the rule-(a) replay of 2026-09-08 reproduces the
deployed sleeve exactly (34 trades, 368 decisions, flat at close, P&L -2,302). Champion unchanged at
S-12. **The durable lesson is A-9's in another shape: one session's worst pattern is not evidence
about the population** - the day that motivated this item belongs to a 4,841-trip category that
earns +$15 a trip. One ops blocker added: live alerting is dead (`no live/alerts.json`), which needs
a channel and credentials the loop may not configure.

Status 2026-09-10 20:4x UTC (O-2): **SPY 0DTE credit spreads are the first candidate in this
repository with a real, calibrated gross edge - and they are refused, because the only version that
pays depends on a settlement convention the data cannot price.** Built the 0DTE chain store
(`scripts/odte_data.py`: **1,884 expirations, 2016-01-08..2026-09-10, 5-minute bid/ask both rights,
+/-30 strikes, ~17.8M rows, 125 MB** from Theta), the study (`scripts/sweep_o2.py`) and the
confirmation (`scripts/_o2_confirm.py`); 16 ledger rows under `options/odte_put_spread`. **The
instrument was proved first**: the chain's own slope (`dP/dK`) is a calibrated probability -
realized breach tracks the quoted prob at every delta on both rights and sits **consistently below**
it at **z = -2.7 to -3.8** in six of six cells - which is the variance risk premium measured rather
than assumed, and the reason gross is positive here where O-1/L-1/X-1 had none. **Stage 1, the
pre-registered grid (36 cells, closed at the quote): 0 of 36 pass, every cell negative in every
regime.** Decomposition, as % of the position's own max loss per session: gross **+0.783**, quoted
spread **-1.363**, commission **-0.950**, net **-1.530** - **the mid edge is a third of the cost of
harvesting it**, and on a $355 risk unit IBKR's fee alone exceeds the whole gross. Made as cheap as
the data allows (72 cells, width 0.75-5%, entry 10:00-14:00, with and without commission) the best
net is **+0.30% at t = +0.94 and that is at zero commission**. **Stage 2 is the finding**: a real
0DTE book does not buy back an untouched position, it lets it expire, and modelling exactly that
**flips the sign** - entry time becomes a monotone shelf (**09:35 +0.09 / t 0.19 -> 12:00 +0.685 /
2.09 -> 14:30 +0.907 / 4.32 -> 15:30 +0.684 / 5.20**), the best cell earns **+0.767% of risk at
t = +3.05, positive in 10 of 11 years**, and 3 of 36 cells pass the rule. **The same cells closed at
the quote earn -0.282% at t = -1.16, positive in 3 of 11 years: the entire result is the exit.**
**And the exit does not survive settlement.** SPY settles on the official 16:00 print and is
exercisable against until 17:30 ET, so a barely-OTM close is not a free expiry; charging the quote
unless the close clears the short strike by a buffer walks the result **+0.767 (t 3.05, 2 regimes)
-> +0.583 (2.32, 1) -> +0.445 (1.78, **0**) at 0.10% of spot -> +0.202 (0.81) at 0.20%**. The pin
distribution is why: **the median session closes 0.28% of spot from the short strike** (p25 0.14%,
p10 0.06%, p5 0.03%) and **37.4% close within 0.2% of it**. At ~65 cents of buffer on today's SPY
the trade fails the pre-registered rule outright. **The mandate refuses it a second time**: at the
un-buffered best cell a book earns +0.767% per session per unit of equity at risk, so **3%/day needs
3.9x equity at risk and a defined-risk position posts its risk in full as margin** - ceiling 1.0x,
where the worst session is **-105%**. At a survivable 0.25x the ledger row is CAR 21.5% at a
**60.6% drawdown**, far outside the 35% cap. **Refused and closed; nothing shipped**, no file the
live trader or the daily runner loads was touched, `live/` and the scheduled tasks untouched, rule
(a) owes no replay (new scripts only). Champion unchanged at S-12. **A-5 part 2 ran as the standing
job on the first full session of intraday fills: 32 fills / $1.87M / 100% filled, realized slippage
+2.92 bps (se 1.32) against the shipped 1.50 - |diff|/se = 1.08, not yet 2 se, so `SLIPPAGE_BPS` was
not touched - but it has moved from +1.30 (partial session) to +2.92, i.e. above A-5 part 1's
2.52 bps breakeven; ~6.7 more sessions settle it.** **The owner's 3-10%/day list is now exhausted.**
O-1, O-1b, L-1, X-1 and O-2 have each been measured on the full history and each refused; nothing in
this repository reaches the mandate, and the only edge that survives out of sample is the daily
champion. The binding constraint is now an owner decision, not a missing idea.

Status 2026-09-10 19:3x UTC (X-1): **breadth does not rescue the intraday sleeve - fifty megacaps
carry a cross-sectional spread of +0.36 bps against a 4.70 bps round trip.** Fetched the 40 missing
megacaps (2016-2026, ~1.04M bars each; the Alpaca store is now 60 symbols) and re-derived
`_splits.json` for the union with every pre-existing factor identical. Stage 1, sixteen cells over
2,684 sessions: gross is **positive (momentum) and never above +0.36 bps per leg**, and **no cell
reaches t > 2 in two of three regimes before a cent of cost**; net, 0 of 32. Stage 2 through the
shipped framework, one year per regime: momentum **-$1,681/day (t = -16.9)** and the reversal
control **-$1,786/day (t = -18.8)** - **both signs losing the same amount**, i.e. gross of +$79 and
-$97/day on a $1M book against $1,760/day of costs at 8.07x turnover. Time-of-day residual worth
keeping: **+0.63 bps at 10:30, -0.69 bps (t = -2.80) at 14:30**. **Refused and closed; nothing
shipped**, no file the live trader loads was touched (rule (a) owes no replay). Champion unchanged
at S-12. **The owner's 3-10%/day list is now exhausted except O-2**, which needs options permission:
O-1, L-1 and X-1 have each been measured on ten years of bars and refused, and the only edge in this
repo that survives out of sample is the daily champion.

Status 2026-09-10 17:0x UTC (L-1): **leveraged ETFs do not revert intraday, and the statistic that
said they did was weighted wrong.** Event study on 2016-2026 Alpaca bars for SOXL/SOXS/TQQQ/SQQQ/
UPRO/SPXU (the last four fetched here): fading a `z`-ATR VWAP deviation at the next bar's open earns
**-0.28 to -3.16 gross bps per round trip in all sixteen cells and on all six names**, against a
**6.4-8.2 bps** cost. Through the shipped framework on 2,686 sessions the fade is **-$902/day at
t = -9.45** (three deployable names -$667/-9.02) and the **continuation control loses too**
(-$587/-6.26): 0/3 regimes everywhere. **The keeper is the weighting**: session-equal averaging
made the same study pass 3/3 at +7.09 bps, because `corr(events/session, session mean gross) =
-0.340 at t = -17.5` - a book puts the same notional on every event, so a session earns the sum.
`_l1_reconcile.py` proved the harness and the event study agree per fill (235 round trips,
corr 1.000) before either was believed. **Refused and closed; nothing shipped**, `live/` and the
scheduled tasks untouched, 2026-09-08 replay reproduces the deployed sleeve exactly. Champion
unchanged at S-12. **X-1 is the top open item.**

Status 2026-09-10 16:0x UTC (A-5 part 2): **the first live fills say nothing about slippage and
prove a cost the harness never charged.** The sleeve placed real orders for the first time this
morning. On the partial session (19 fills, $1.11M, 100% fill rate) realized slippage is **+1.30 bps
notional-weighted, se 1.65, against the shipped 1.50 - z = 0.12**, so `SLIPPAGE_BPS` was not
touched. **The reference worry is refuted by direct measurement**: the same 17 fills score +1.10 /
sd **7.55** against the next-bar open and +1.55 / sd **7.13** against the decision close (realized
gap sd 2.16, corr -0.33 with the fill error), even though the whole-store gap sd of 6.20 bps on
this symbol mix predicted the fallback would carry 76% of the variance - **a population noise
estimate does not transfer to the minutes a strategy selects.** What costs precision is the ~10 s
detection latency (median 10 s, worst 13 s), which is mean-zero drift, so only fills buy it:
**166 fills, ~3-4 full sessions**, to resolve the constant against breakeven at 2 se. **What did
land is a missing cost, measured exactly.** IBKR's `commissionReport` matched the harness to
$0.004 on all twelve buys and undercharged all five sells; fitting the excess on notional and
shares reproduces every sell **to the cent**, so the harness omitted the US sell-side regulatory
pass-throughs - **SEC Section 31 $20.60/$1M of proceeds (0.206 bps) and FINRA TAF $0.000198/share**
- now charged in `intraday_common.commission()` when `shares < 0` (measured commission 0.501 bps
against 0.434 modelled; 0.501 after). Paired 260-session control at A-5's parameters: costs/day
**$1,025 -> $1,078**, $/day **$610 -> $557**, CAR **15.3% -> 14.0%**, Sharpe **0.689 -> 0.640**,
trades 12,743 -> 12,742. **Breakeven slippage is therefore 2.52 bps, not 2.62**, the deployed
half-size sleeve pays ~$22/day of it, and the 2,686-session Alpaca result moves from -$697/day to
roughly -$740/day: every number moves against the sleeve, which is where omitted costs always
move. **Two no-ops proved**: the old-model control reproduces A-5's ledger row to every digit,
which incidentally proves the participation-cap path an interrupted session left uncommitted in
`intraday_backtest.py` is **bit-for-bit inert at `part_cap = 0.0`** (committed here on that
evidence; A-11 itself is still unrun), and the rule-(a) replay of 2026-09-08 against the current
trader gives identical 34 trades / 368 decisions / flat at close under both models, differing only
by the $22 of fees. `scripts/slippage_report.py` gains the two-reference split (never pooled),
per-fill pricing under both references, fill latency, a fills-to-breakeven power line and
`--refresh`. Nothing else shipped: `live/intraday_config.json`, `live/APPROVED_PAPER.md` and the
scheduled tasks were not touched, and the champion is unchanged at S-12. **Note for the next
iteration**: the owner's midday mandate (3-10%/day; priority O-1 / L-1 / X-1 / O-2) landed at
11:40 ET while this ran, and it judges every candidate "with real costs" - so L-1 and X-1 must be
run against the corrected model from their first backtest, not compared to pre-fix numbers.

Status 2026-09-10 12:5x UTC (O-1b): **the implied-vol size dial is a leverage dial, and it pays 50%
more turnover for it. Refused; nothing shipped.** O-1's deferred half, on the daily champion, where
the level is positive. `signals.py` gains `iv_regime_series` / `iv_size_factor` and five `Params`
fields (`iv_scale_power`, default **0.0 = off**, `iv_scale_field`, `iv_scale_window`,
`iv_scale_min/max`), `main.py` the matching `S1_IV_SCALE_*` overrides, and
`scripts/iv_regime.py --export-csv` mirrors the parquet to `data/options/iv_regime.csv` (the
LEAN-side Python 3.11 has no pyarrow). The factor multiplies the **final** weights - after the
margin-budget shrink, because with a flat budget the vol target is inert upwards (S-8) - and reads
only store rows dated **strictly before** the last price bar, so it is causal under either harness's
timestamp convention. Covered period **2017-04-03..2026-09-04** (uncovered days get factor 1.0 and
run as the champion, so a full-period run can only move the verdict toward the control). Against its
own control (2,951 orders / $13,090 / CAR 29.456% / Sharpe 1.025 / DD 22.6% / std 0.179 / PSR 37.7%):
**the inverse reading, the one the residual motivates, is the losing side** - power +1.0 gives
27.692% / 0.950 / 21.1% / std **0.182** / PSR 29.5%, worse on return *and* carrying more vol than
the control. The winning side is the direct one (lever up when IV is high, i.e. A-10's
long-volatility reading on a book that is paid for it), and its response is a **pure vol dial**:
std 0.179 -> 0.189 -> 0.198 -> 0.204 monotone in the tilt, CAR 29.46 / 31.38 / 31.71 / 29.77 rolling
over, Sharpe peaking at -0.5 (1.050) and decaying to 0.939. **The benchmark settles it**: degenerate
the clip into a constant gross-up and the IV timing is gone while the gross is identical - CONSTANT
1.056 scores 3,027 orders / $14,556 / **31.107% / 1.040 / 23.8% / std 0.189** / 38.9% against the
dial's 4,550 / $17,963 / 31.376% / 1.050 / 23.3% / std 0.189 / 40.0%. **At identical realized vol
the dial's entire edge over a dumb constant is +0.27 CAR and +0.010 Sharpe, bought with 50% more
orders and 23% more commission** - one unit of the +/-0.3 CAR path scatter S-13 measured on a
parameter with no mechanism. Two thirds of the raw gain is not timing at all: CONSTANT 1.0198
(the dial's own mean factor) already earns +0.57 CAR. **And the constant needs none of this code**:
`margin_budget` 0.75 -> **0.792** gives 3,039 orders / $14,530 / **31.006% / 1.042 / DD 22.8% /
std 0.188 / PSR 39.1%** - +1.55 CAR over the shipped champion for **+0.2 points of drawdown and 88
extra orders**, against the dial's further +0.37 CAR for +0.5 points and **1,511** extra orders.
**The no-op is proved**: the shipped-defaults
full-period run reproduces **`OrderListHash 5246804e17a67af90028ffceead7d3b3`** with 4,735 orders,
CAR 24.404%, Sharpe 0.921, DD 25.100%, fees $45,695.46 - bit-identical to the champion - so the
IBKR paper runner's path is unchanged and `live/` was not touched. **Do not re-open as a feature or
threshold question**: the only thing implied vol can give a momentum book is the *level* of gross,
and that level is free and turnover-less through `margin_budget`; the 1.6 points of CAR it buys is
a risk-posture decision, now a one-line question in `BLOCKERS.md`. **A-5 part 2 had no input**:
`slippage_report.py` at the top of this iteration still finds no session with live fills (this ran
at 08:3x ET, before today's open). Champion unchanged at S-12; the intraday sleeve was not touched.

Status 2026-09-10 11:4x UTC (O-1): **implied vol forecasts the day this sleeve is paid for, and
that forecast is worth nothing - the sleeve is paid for volatility *surprise*.** New
`scripts/iv_regime.py` builds `data/options/iv_regime.parquet` from Theta EOD greeks (**2,383 days,
2017-01-03..2026-09-09**: SPY front-weekly ATM IV, 25-delta skew, 1w/1m term ratio), new
`scripts/sweep_o1.py` partitions A-10's cached 2,686-session P&L series by the strictly prior-day
gate, and `algorithms/intraday/orb/signal.py` carries `iv_gate` (high/low/off, default off).
**The chain breaks in the middle**: corr(prior-day ATM IV, today's universe range) = **+0.598 at
t = +36.4**, corr(realized range, ORB P&L) = **+0.260 at t = +13.95**, and corr(IV, P&L) =
**-0.030 at t = -1.46** (regimes +0.001 / -0.052 / +0.010). Splitting the range into the part IV
saw coming and the part it did not: the forecast part scores -0.030 / -0.016 / -0.058 against P&L
and the **surprise part +0.351 / +0.292 / +0.299 at t = +18.3 / +14.3 / +15.3**, positive at t > 7
in **nine of nine feature-regime cells**. That is A-9's finding arriving against a real,
market-priced forecast on ten times the sample: what pays is unknowable at entry by construction.
**All six gate cells fail 0/3 regimes**; the best ON side in the sweep is `term_ratio low` at
**+$43/day, t = +0.13**, and the largest separation anywhere (Welch t 2.26, `term_ratio low`
2016-2019, +$636/day) **inverts to -$632/day in 2024-2026**. What does survive is not a gate:
corr(IV, **|P&L|**) = **+0.252 at t = +12.67**, positive in all three regimes for all three
features - implied vol forecasts how *big* the day is, not which way, i.e. a size scaler, which is
worthless on a book whose level is negative and is exactly O-1's deferred half for the *daily*
champion (now carried as **O-1b**). The gate parameter was confirmed in the real backtester on one
year (`scripts/_o1_confirm_2024.py`, three ledger rows: 2024 ORB alone, gate off 252 traded days /
+$524 day / Sharpe 0.62, high 118 / +$452 / 0.62, low 131 / -$23 / 0.02) - it blocks whole
sessions, keeps about half, and fails closed on the 3 uncovered days - but **that year is a wiring
check, not evidence**: 2024 is a positive year inside a regime that is -$65/day, and the side it
favours is the side the full partition scores worst. **Refused; nothing shipped,
`live/intraday_config.json` untouched**, and the
2026-09-08 replay with the deployed config reproduces A-10 to the digit (34 trades, 368 decisions,
flat at close, P&L -2,280 on 500k) so the ORB edit is a no-op on the live path. **`equity_frac`
held at 0.5, not cut to 0**: the owner's three-way question in `BLOCKERS.md` is still open and its
default (a) exists to feed **A-5 part 2**, which has still had zero live fills (re-checked at the
top of this iteration) and whose first chance is today's 09:25 ET session. **A-10 measured the
level, O-1 measured the conditioner, and there is no twelfth lever on this sleeve.** Champion
unchanged at S-12; the daily sleeve was not touched.

Status 2026-09-10 10:3x UTC (daily review, no experiments run): **the deadline was met and the
second sleeve was disproved in the same 24 hours.** The daily champion filled on IBKR paper at
15:46 ET on 2026-09-09 (TQQQ 3,700 @ 71.49, XLE 7,333 @ 65.39, XLK 2,616 @ 187.85, 1.23x gross on
DUT091359), so S-1 -> S-12 is now a live paper strategy and the 2026-09-10 objective is closed.
Twelve A-track iterations and 217 ledger rows later the intraday sleeve is measured at **-$697/day,
t = -3.01 on 2,686 sessions**; the late-day fade is dropped and `equity_frac` held at 0.5.
**Order of work for the next 24 hours: (1) A-5 part 2 after today's close** - today is the first
session that places real intraday orders and `scripts/slippage_report.py` is the only instrument
that can move the 1.5 bps constant that owns the sleeve's sign; **(2) O-1**, judged on the Alpaca
regimes; (3) per-session ops. Two ops items found in the review: IB Gateway's port 4002 is down
nightly ~02:15-02:45 ET and was open again at 06:30, so an off-hours connect failure is expected,
not the old blocker returning; and phone alerts are **broken** - `notify_failed`
(`TELEGRAM_BOT_TOKEN` missing) on 2026-09-09, so a live failure is invisible outside the logs.
Full review in `research/reports/2026-09-10.md`. Champion unchanged at S-12.

Status 2026-09-10 08:5x UTC (A-10): **with 2,686 sessions the sleeve is not
unproven, it is negative - and the late-day fade is refused at 7 sigma.** A-4 said ~2,120 sessions
were needed and unreachable; the Alpaca SIP store has 2,686 (2016-01-04..2026-09-09, same 16
names). New `scripts/sweep_a10.py` runs the deployed mix and each sub-strategy alone as one
backtest per calendar year from a fresh $1M book, pooled into three a-priori regimes.
**A cost-model bug had to be fixed first**: the store is split-adjusted, so a dollar position
bought up to 40x the shares really bought and the per-share commission pinned to its 1% cap
($1,523/day on 7 trades/day in a 2016 smoke test, $222 after the fix), while SOXS's 8.3e-08
cumulative factor put its adjusted 2016 price in the tens of millions and the whole-share floor
sized every early SOXS position to **zero**. Fixed in shared code - `alpaca_data.py --splits`
derives the factor by asking Alpaca for the same daily bars raw and adjusted and writes
`_splits.json`, `intraday_common.share_scale()` reads it, `commission()` takes a scale, and the
whole-share floor is applied at the price really quoted. **The raw IBKR store has every factor
1.0 and the regression proves the no-op**: A-5's control reproduces to the digit (260 sessions,
CAR 15.343%, Sharpe 0.689, $610/day, 12,743 fills). The result: mix **-$697/day at t = -3.01**
over 2,686 sessions, negative in all three regimes (**-$579 / t -2.42**, **-$1,127 / t -2.92**,
-$231 / t -0.37), positive in 4 of 11 years and no year at |t| = 1. **The only profitable window
in eleven years is the 261 sessions the parameters were fitted on, and even there t = +0.32.**
**The late-day fade alone is -$468/day at t = -7.38**, negative in every regime separately and on
the fitted window too - A-4 kept it on 260 IBKR sessions at t = +0.27 because that sample could
not see a 7-sigma effect. **A-4's mechanism survives with power**: corr(daily P&L, universe range)
**+0.202 at t = +10.70**, positive in all three regimes. **Shipped** after a passed 2026-09-08
replay (34 trades, 368 decisions, flat at close): `alloc.late_momo` **1.0 -> 0.0** in
`live/intraday_config.json` - refused at 7 sigma OOS and free in sample (ORB alone earns +$322/day
on the fitted window against the mix's +$302). **`equity_frac` held at 0.5**, not restored: what
is left is ORB alone at -$289/day, t = -1.17. Whether the sleeve should trade paper capital at all
is now the top question in `BLOCKERS.md`. **O-1 (options-implied regime gating) is the new top
item** - it is the only untried idea whose mechanism this study confirms; the participation cap
A-5 found is demoted, because it can only make a losing book smaller. Champion unchanged at S-12;
the daily sleeve was not touched.

Status 2026-09-10 06:3x UTC (A-5 part 1): **the sleeve breaks even at 2.6 bps of
slippage and is charged 1.5, so the cost constant owns its sign.** A-5's live-fill measurement
needs a session that placed orders and there is none yet, so this iteration priced the cost model
from the store instead. New `scripts/sweep_a5.py` (`spread` / `impact` / `breakeven`), a
backtest-only `--slippage-bps` override, and `scripts/slippage_report.py` - the live-fill
comparison, finished and self-tested, idle until tonight. Control reproduces A-4 exactly (260
sessions, CAR 15.3%, Sharpe 0.689, $610/day, 12,743 fills). **P&L is linear in the constant to
$73/day**: 0 bps -> **$1,671/day, CAR 41.9%, Sharpe 1.51**; 1.5 bps (shipped) -> $610, 15.3%,
0.69; 3.0 bps -> **-$231, -5.8%, -0.11**. The sleeve turns over **$5.46M/day on a $1M book, 5.5x
equity a day**, so one bp is $546/day and the whole modelled edge is **1.1 bps wide**; breakeven
is **2.64 bps from the runs, 2.62 analytically**. **The holdout's breakeven is -0.02 bps**: on the
77 sessions no A-track parameter ever saw, gross P&L *before any slippage* is **-$11/day**, so
A-4's -$813/day is not a weaker regime, it is **no gross edge at all** paying $802/day of costs.
Bounding the constant from bars fails on purpose: Roll and Corwin-Schultz give a
notional-weighted half-spread of **2.65 bps** - sitting exactly on the breakeven - but
`corr(estimate, 1-minute return std) = +0.906` with a CS/vol ratio of 0.32-0.65, so **the
estimator is measuring volatility, not spread**; the hard floor (half a tick) is 0.36 bps, so all
that is honest is **half-spread ∈ [0.36, 2.65] against a 2.62 breakeven** - only fills settle it.
What the bars *do* refute is participation: over 12,743 fills the order is **median 1.03%, p90
5.55%, p99 26.1% and at worst 199% of the volume of the minute it fills in**, concentrated in
**SMCI / SOXS / COIN / MSTR, which carry 30% of traded notional** at p90 6-19% against the
megacaps' 0.2-0.9%. That is a modelling defect, not a lever, so A-4's power argument does not
excuse it - it is the new top item **A-10**. The harness's fill convention is *not* hiding a cost:
the decision-close-to-next-open gap is **-0.12 bps (se 0.04)**, so the all-in modelled cost of a
fill is 1.50 + 0.38 commission = **1.76 bps**. **Nothing shipped**: `SLIPPAGE_BPS` stays 1.5,
`live/intraday_config.json` untouched, and a 2026-09-08 replay passed (46 trades, flat at close)
because three logging fields were added to the trader for the live report. Champion unchanged at
S-12; the daily sleeve was not touched.

Status 2026-09-10 05:2x UTC (A-9 iteration): **the day's range pays, and the half of it
that is knowable at entry pays nothing.** A-4 said ORB's P&L rides the same-day range; A-9 asked
whether the opening range, which closes before the first entry, can be used as the causal handle.
Decomposing each session's universe mean range into the opening 15 minutes and the residual:
ORB's daily P&L correlates **+0.568 (t = +11.09)** with the realized full-day range and
**+0.665 (t = +14.29)** with the residual - stable in both halves - but only **+0.080 (t = +1.28)**
with the opening range, and **-0.009** on the holdout, even though the opening range predicts the
day's range at corr +0.626. The reason is mechanical: **ORB's stop is the range midpoint, so the
width is the risk unit** - a wide opening scales the win and the loss together, and what pays is
the range added *after* entry. **A-9's premise is refused at the root.** The grid proves it in the
sharpest way the A-track has produced: with `range_atr_min` / `range_atr_max` added to the ORB
module (defaults 0 = off, control reproducing A-4 to the digit), **every "keep the wide openings"
cell beats the control on the tuning window and loses on the holdout, and every "keep the narrow
openings" cell does the exact opposite.** `min 3.6` reaches **TUNE Sharpe 2.17 / CAR 49.7%** - the
best number this sleeve has ever produced - against **HOLD -1.19 / -20.5%**; its mirror `max 3.6`
earns **HOLD 1.46** against **TUNE -1.27**. Paired against the control over all 260 sessions **no
cell in the eleven reaches |t| = 1.6**, and in the deployed mix the same cells give 2.32 and 2.53
tuning-window Sharpe against -1.96 and -1.27 on the holdout (paired t +0.92, +0.62). The lever
does not select trades, it selects which half of the sample you are looking at. **Refused; nothing
shipped, `live/intraday_config.json` untouched, both gates stay 0**, and a 2026-09-08 replay was
run anyway because the live trader loads this module (46 trades, flat at close, identical to the
A-2 replay). New `scripts/sweep_a9.py` and an opt-in `collect_trades` in the backtester. **The
durable lesson is that the holdout is now doing real work**: on the 183-session window every prior
A-track iteration used, `min 3.6` would have shipped. **A-5 is the new top item** - A-9 was the
last lever with a stated mechanism, A-8 stays parked, and measured slippage is the one number in
the harness that is still a guess. Champion unchanged at S-12; the daily sleeve was not touched.

Status 2026-09-10 02:2x UTC (A-4 iteration): **the minute store is now 260 sessions,
and on them the intraday sleeve's return is not distinguishable from zero.** The store was
extended to 12 months (2025-08-26..2026-09-08) and repaired - `intraday_data.py` was ending each
request at the wall-clock time of the run, so IBKR truncated the newest session of every window
into a partial day; `snap_after_close`, `--repair` and `truncated_sessions()` fix it, and all 16
symbols now hold 261 clean sessions with only the two real NYSE half days short. Re-running
A-7's control on the repaired bars moves it a tenth of a point, so **every prior A-track
conclusion stands**. The 77 sessions before 2025-12-15 are a true **holdout** - no A-track
parameter has ever seen them - and the deployed mix **loses -$813/day on them** (CAR -19.1%,
Sharpe -0.73) against +$1,289/day on the 183 it was fitted to. **But nothing here is
measurable**: Welch t between the halves is **-0.96** for the mix, and a single run over all 260
sessions earns $610/day at std $16,222 - net +15.87%, **CAR 15.3%, Sharpe 0.69, t = +0.61, 95%
CI on the year's total P&L [-$354k, +$671k]** around $158.6k, on 49.0 trades/day and $1,025/day
of costs. **The power calculation is the result**: at Sharpe
0.69 you need `(2/0.69)^2` years = **~8.4 years / 2,120 sessions** to reject zero at 2 sigma,
so no achievable backtest sample can validate this sleeve, and A-1/A-2/A-7 - all hunting
differences *smaller* than the base rate - were never capable of answering. The **late-day fade
is worth $1,099 over 260 sessions** ($4/day on $232/day of costs; marginal inside the mix +$65/day,
t = +0.27), so A-6 shipped it on the tuning window alone. What *is* measurable, at **t = +10.25**,
is that the sleeve is a **long-volatility position**: daily P&L correlates +0.538 with the
universe's same-day range, the holdout is the calmer window (mean range 3.78% vs 4.44%), and the
negative holdout is therefore a **regime, not decay**. Prior-day range does not predict it
(t = +0.47), but the **opening range's width relative to ATR14 is known at ORB's entry and is
never used** (ORB gates on volume only) - that is **A-9, the new top item**, the one lever with
a mechanism behind it. **Nothing shipped; `live/intraday_config.json` untouched**, so the trader
is byte-identical and no replay was owed - dropping the late fade improves the holdout but costs
$16.8k over the full store at t = +0.27, which is not the OOS improvement rule (c) requires.
The unmeasurability of the sleeve is now a one-line question to the owner in `BLOCKERS.md`.
Champion unchanged at S-12; the daily sleeve was not touched.

Status 2026-09-09 23:0x UTC (A-7 iteration): **the framework risk limits are a tail
dial with no price, and the sample is now the binding constraint.** Fifteen cells on the usual
9-month window (2025-12-15..2026-09-08, split 2026-06-15, 124/59 sessions), deployed mix, via a
new backtest-only `--risk` override and `scripts/sweep_a7.py`. The daily loss limit does exactly
one thing and does it monotonically: the worst day walks **-20.5k (1.5%) -> -30.3k (2.5%,
shipped) -> -57.0k (off)**, with a 0.15-0.38 point overshoot past nominal because the breach is
marked to close and the flatten pays spread. It does **nothing measurable to return**: total P&L
is 200.5k at 2.0% and 243.1k at 1.5% with the shipped 2.5% at 221.2k, and **paired against the
control every cell in the whole sweep scores |t| <= 1.06** on 183 daily returns. A-7's stated
worry is refused - **stopping early is free**: on halted sessions the halted book beat the
limit-off run on the same dates at every limit except 2.0% (saving $453/halt at 1.5%, which
fires on 22% of sessions, and $8,497/halt at 3.0%). `PER_SYMBOL_HARD_CAP` is **inert**: 0.12,
0.15, 0.20 and 0.25 are bit-identical, so the mix never asks for more than ~0.12 of equity in one
name, and below 0.12 the cap is a size dial (0.10 is a spike on IS Sharpe with losing neighbours,
refused). Gross saturates at the deployed 1.5; 2.0 buys +2.7% of P&L outside A-3's stated range
and is an owner decision. **Nothing shipped; no constant changed, `live/intraday_config.json`
untouched, so the trader is byte-identical and no replay was owed.** The durable conclusion is
that with A-1, A-2 and A-7 all negative, **the sleeve needs more sessions, not more levers** -
one standard error on the 183-session total is $229.6k against a $221.2k total. **A-4 (extend
the minute store to 12 months) is now the top open item**, ahead of A-8, because A-8 would be
judged with the same instrument that just failed to resolve a 20% swing in P&L. Champion
unchanged at S-12; the daily sleeve was not touched.

Status 2026-09-09 21:3x UTC (A-1 iteration): **the VWAP fade can be repaired, and it
still is not worth capital.** Eleven standalone variants and six sleeve runs on the 9-month
window (2025-12-15..2026-09-08, split 2026-06-15, 124/59 sessions). Only one of A-1's five
levers is a mechanism: the **session-trend filter** takes the module from IS -56.0 / OOS -10.1
to -11.9 / +16.9 at a third of the turnover, and **the inverted filter fails as predicted**
(-46.3 / -5.5), so the fade was losing by fighting trend days rather than by mistuning. Min
hold, a midday blackout and a 5-minute cadence only shrink the position; range expansion leaves
0.8 trades/day. The only cell positive in both halves is +0.8 / +11.3, and Sharpe 0.13 on 124
sessions is zero. **At the sleeve it is a wash bought with turnover**: three fade cells at
alloc 0.25-0.5 give total P&L $216.9-225.2k over 183 sessions against the deployed $221.2k,
with IS CAR falling monotonically in the allocation and IS drawdown 1.2-3.9 points wider, for
22-34% more trades per day. **Refused; `vwap_trend` alloc stays 0 and `live/intraday_config.json`
was not touched.** A-1 is closed. Champion unchanged at S-12; the daily sleeve was not touched.
**A-7 is now the top open item** - A-1 and A-2 together say the signal layer is spent and the
framework constants in `scripts/intraday_common.py` are the untested surface.

Status 2026-09-09 19:0x UTC (A-2 iteration): **the ORB tail does not come off for
free.** Nine variants on the 9-month window (2025-12-15..2026-09-08, split 2026-06-15, 124/59
sessions): the response to stop distance is **monotone and rotates return between the halves**
rather than adding any - midpoint (shipped) 35.7 IS / 10.7 OOS, +4x ATR backstop 31.4 / 19.3,
+3x 21.5 / 26.5, pure 1.5x ATR -12.3 / 43.1, with the two-half mean roughly conserved. The
worst day and the loss-limit days only fall materially at a stop tight enough to zero the
in-sample return (pure 1.0x ATR: worst -33.9k -> -21.4k, loss-limit days 0/0, IS CAR -0.3%),
so **A-2's stated hypothesis - cut the tail, keep the return - is refused**. Scale-out at 1.5R,
a 30-minute range and a 1.6x volume filter all lose in both halves. What shipped is the shelf
point on that frontier: `disaster_atr=4.0` on ORB in `live/intraday_config.json` (sleeve mix
IS 27.2/1.10 -> 24.2/1.01, OOS 36.2/1.24 -> 55.3/1.73, worst day flat, one fewer loss-limit
day), with a 2026-09-08 replay passed before the write. The ORB module now carries every lever
as a parameter and the control run reproduces A-6 to the digit. **Champion unchanged at S-12**;
the daily sleeve was not touched. Next is A-1, then A-7 (the tail is a framework-constant
question now, not a signal one).

Status 2026-09-09 16:0x UTC (D-2 iteration): **the intraday data blocker is gone for
SPY.** The 10141 disclaimer has been accepted - `paper_trade.py --check` answers on account
`DUT091359` ($1,000,344 net liq, no positions) - so D-2 became the top item and shipped:
`scripts/fetch_minute.py` pulls IBKR 1-minute TRADES bars and writes LEAN minute files, paced
for IBKR's 60-per-10-minutes rule, resumable by month chunk, `clientId` 31. **SPY 2020-01-02
.. 2026-09-08 is complete and validated: 1,679 sessions, 652,650 bars, 0 missing against the
daily calendar, 0 truncated, 0 clamped, 14 MB.** The acceptance test is a LEAN run
(`algorithms/d2_minute_smoke`, run `20260909T160005Z`) rather than a file check, because D-1's
worst bug was a file that passed structural validation and made LEAN return zero bars silently;
**all seven checks PASS** and LEAN's bar count matches the writer's exactly. One bug found and
fixed, worth remembering: `durationStr="1 M"` ending on the month's last day starts *after*
the first session's close, so IBKR silently drops **the first session of every month** - ~5% of
the sample, invisible because every session that survives is a complete 390 bars. Chunks are
now `5 W` with the overlap filtered back. Two durable facts: minute and daily closes agree to a
median 0.007%, but diverge up to ~1% on violent days (COVID, April 2025) because the daily
close is the **auction print** and the last minute bar is not - so **S-2 must model the 16:00
auction, not assume a 15:59 fill**; and IBKR serves ~260-790 bars/s, making a five-symbol
backfill a multi-hour job, which is why only SPY was completed. Champion unchanged at S-12.
**S-2 is now the top open item.**

Note for whoever takes S-2: a parallel session is building an intraday harness outside LEAN
(`scripts/intraday_backtest.py`, `algorithms/intraday/{orb,vwap_trend,late_momo,gap_fade}`)
and its ledger entries from 2026-09-09 15:4x-16:0x all split IS/OOS at 2026-08-15 - a ~30-day
sample, i.e. the Yahoo 1-minute cap. **That constraint is now lifted**: those signals can be
re-run against 6.7 years of SPY instead of one month, which is the difference between a
sample that can reject a hypothesis and one that cannot. Reconcile the two harnesses before
promoting anything from either - LEAN decides, per the S-10 methodology finding.

Status 2026-09-09 14:0x UTC (I-1 iteration): **the pre-deploy gate is built, and it
caught a real bug in the runner.** Gateway is up but the API is still refused by 10141, so
instead of a sleeve experiment this iteration finished I-1's last unbuilt piece:
`scripts/compare_orders.py`, which walks LEAN's own bars and hands *identical* inputs to
`main.py:submit_targets` and `paper_trade.py:plan_orders`, diffing the two order lists. Any
difference is therefore execution-layer by construction, not data or signal. **It failed on
first run**: the runner banded orders at a flat `MIN_NOTIONAL = $200` while the backtest bands
at `0.01 x equity` ($1,000 at $100k, $24,000 by the end of the sample), so the runner would
have placed **9,196 orders against the backtest's 4,653** and agreed on only **36.6%** of
decision dates - all 4,543 divergences the same shape, the runner sending small drift
adjustments LEAN bands out. These are exactly the orders S-13 measured as return-neutral, so
the paper account was about to pay a spread on ~4,500 orders with no return in them and
underperform its own backtest for a reason nothing would have surfaced. Fixed
(`max(MIN_NOTIONAL, MIN_ORDER_VALUE * net_liq)`, `MIN_ORDER_VALUE = 0.01` tracking `main.py`);
the gate now passes **3,689 / 3,689 dates with identical order counts**, and fails with exit 1
on a deliberately mismatched band, so it discriminates. **Nothing under `algorithms/` was
touched**, so `OrderListHash 5246804e17a67af90028ffceead7d3b3` stands unchanged and no
rebaselining run was needed. Champion unchanged at S-12.

Status 2026-09-09 13:40 UTC (daily review, no experiments run): **the Gateway blocker moved,
and it is now one dialog box.** Port 4002 is open and answering for the first time - Gateway is
running and logged in - but the API handshake is refused with `Error 10141: Paper trading
disclaimer must first be accepted for API connection`. That is a one-time tick-box inside
Gateway (Configure -> Settings -> API -> Settings), not work on this side, and it is the only
thing between the repo and tomorrow's deadline. Re-probe with `paper_trade.py --check` at the
top of every iteration; the moment it clears, **I-1 is the top item and everything else waits**,
with D-2 immediately behind it on the same connection. Full review in
`research/reports/2026-09-09.md`. If the API stays blocked, do **not** hunt for another lever on
the ETF-9 sleeve - S-11 and S-13 measured that there are none left cheaply; the useful offline
work is S-5 harness scaffolding and generalizing `sweep_s1.py` off S-1 (E-2's deferred half).

Status 2026-09-09: **S-13 closed negatively - the champion stands at S-12.** The
execution no-trade band (`min_order_value`, pinned at 0.01 since S-1 and never swept) was
tested at 0.015/0.02/0.03/0.05/0.08 to win back the commission S-12 spent. It cannot be won
back, because **there is nothing to win**: the response is non-monotone and flat, with CAR
walking 24.40 -> 24.35 -> 24.54 -> 24.34 -> 23.92 -> 24.47 across a factor of eight in the
band and a factor of 2.7 in order count. The 0.02 cell beats the champion and `evaluate.py`
says **BEATS champion**, and it was **refused** on the shelf-not-spike rule - both its
neighbours lose, so its +0.14 CAR is inside the region's own scatter. Nothing shipped;
`OrderListHash 5246804e17a67af90028ffceead7d3b3` is unchanged and I-1 needs no rebaselining.
The durable finding is the flatness: **~3,000 of the champion's 4,735 orders (63%) are
return-neutral**, free to remove in backtest and strictly *better* to remove live, where the
unmodelled spread is paid per order. That is a live-execution decision and is now a one-line
question in `BLOCKERS.md`. Ports 4002 and 7497 checked again at the top of this iteration:
both still closed.

Status 2026-09-09: **S-12 has promoted a new champion** - the same signal, but the
exposure budget is now split between the three winners by **1/sigma on their own trailing
one-month vol** instead of 1/N: CAR 23.61% -> **24.40%**, Sharpe 0.874 -> **0.921**, drawdown
25.9% -> **25.1%**, PSR 17.7% -> **23.0%**, at 84% more orders and $8.3k more commission. It is
a shelf in both dimensions (vol windows 20/21/30 all win; the tilt is monotone in strength) and
21 sessions is the a-priori one trading month inside it, not the argmax. IS 19.18%/0.884/25.1%
beats S-10 on all three; OOS 30.86%/0.985/22.6% wins on Sharpe and is flat on CAR, so the gain
is an in-sample-half gain. New order list
**`OrderListHash 5246804e17a67af90028ffceead7d3b3`**, and I-1's pre-deploy comparison must be
made against that hash, not `ff4a7cbaaf6e36e58ace2b82ab216bdf`. Ports 4002 and 7497 were checked
again at the top of this iteration and are both still closed, so I-1/D-2/S-2 remain blocked.
**With the allocation step now spent, this sleeve has no cheap levers left**: what remains
inside a three-name ETF book needs breadth (correlation-aware weights want more than nine
names), so the next real gains are still S-2 and D-2 behind the Gateway login.

Status 2026-09-08: **S-11 closed negatively - the champion stood at S-10.** Every
whipsaw control (hysteresis, minimum holding period, rank persistence) trades return for
drawdown roughly in proportion, so the champion's turnover is *paid for*: its rotation is
signal, not noise. What the iteration does leave behind is a priced frontier - `min_hold=10`
plus `margin_budget=0.85` earns 25.07% CAR at 25.7% drawdown (champion 23.61% at 25.9%) for
0.013 of Sharpe - which is now a one-line question to the human in `BLOCKERS.md`. Signal work
that adds return without adding turnover has therefore run out of cheap moves on this sleeve;
the next real gains are a second uncorrelated sleeve (S-2/S-5) and intraday data (D-2), and
both of those, like I-1, wait on the IB Gateway login.

Status 2026-09-08: **S-10 has promoted a new champion** - S-9 with the 120- and 252-day
momentum windows ending one trading week before the decision bar: CAR 20.9% -> **23.6%**,
Sharpe 0.78 -> **0.87**, drawdown 28.9% -> **25.9%**, at 10% fewer orders, beating the old
champion on both sub-periods. New order list:
**`OrderListHash ff4a7cbaaf6e36e58ace2b82ab216bdf`**, and I-1's pre-deploy comparison must now
be made against that hash, not `b763e292cb0eb9a2c81af5739188d437`. The remaining gate is still
I-1, blocked on IB Gateway being logged in on this machine (see `research/BLOCKERS.md`); the
runner is built and re-verified `--mock --dry-run` against the new signal.

Three constraints stay measured rather than assumed: single-name sleeves are capped because the
pool on disk is a 2026 survivor list, leaving the ETF-9 sleeve as the only honest universe here
(S-7, D-3); the 40-60% volatility mandate is **unreachable** under the 35% drawdown limit on
that sleeve, at any size, by any of the four levers S-8 tried; and a daily-turnover book on this
$100k account pays ~2.1bps per unit of turnover in commission alone, which is more than the
whole gross edge S-3 could find. The first two are decisions for the human in `BLOCKERS.md`.
S-9 and S-10 are the only results to move the champion *without* spending more turnover, which
is the only kind of gain that cost floor cannot tax away - so signal work, not sizing work, is
where the next iteration should look too.

One methodology change, from S-10: **`sweep_s1.py` and LEAN now disagree in sign**, not only in
magnitude - the sweep rejected the skip lever that LEAN promoted, and inverted its drawdown
ranking. A sweep rejection is therefore grounds for one LEAN confirmation run, not for closing
an idea; the sweep is a cheap generator of candidates, and only LEAN decides.

## Open (highest value first)

- **S-26 DONE 2026-09-12 (see journal): refused - and the first refusal here that is about RISK
  rather than cost, sign or significance.** `scripts/sweep_s26.py` + two default-inert arguments
  on `sweep_s25.legs_simulate`; 10 DIAGNOSTIC ledger rows; seven clauses pre-registered. The
  overlay shorts `h x beta x equity` of the index over the intraday leg on a causal trailing beta,
  charged 2 bp of equity spread, IBKR Pro financing and F-2a's **0.488 bps** futures round trip.
  Identity passes to the digit (22.192150%, residual 5.33e-16) and the **proxy is validated, not
  assumed**: corr(ES cash session, SPY open->close) **0.9994**, slope 0.9984, basis sd 2.1 bps over
  313 sessions, so **this overlay needs no CME purchase**. Vol-matched, **h=0.50 earns 20.837% /
  Sharpe 1.100 against 19.640 / 1.047, wins both halves (+0.72 IS, +1.66 OOS), stays inside Reg-T -
  and is REFUSED on drawdown, 26.02 against 24.04 + 1.0**; h=1.00 is refused on CAR everywhere.
  Paired +0.395 at **t +0.60**. **The placebo is the durable positive**: the same overlay on the
  *overnight* leg costs **-4.310 bps/day at t -4.14** against the intraday overlay's -1.373 at
  t -1.02, the only |t| > 2 in the file, so **S-25's split is confirmed by a second route**.
  **Breakeven +1.108 bps a round trip at h=0.50 against ES's 0.488** - the edge clears the cheapest
  instrument on file by 2.3x and dies on risk instead. **Do not re-open as a hedge-ratio, beta-window,
  benchmark or instrument question** - the ratio grid spans 0 to 1, the best ratio already clears
  the cost by a factor, and a cheaper instrument cannot fix a drawdown. Three durable pieces survive
  it: the **`hedge=`/`scale=` arguments** (any future overlay or risk-matched column runs on the
  deployed book without editing it), the **validated ES-to-SPY proxy** (an index-overlay question
  can now be priced with no futures history), and the rule that **matching daily volatility is not
  matching drawdown, so a vol-matched relever owes its own drawdown column**. It also corrects one
  prior number: a breakeven's turnover divisor must be growth-normalized, so S-25's printed
  breakevens are compressed ~4.3x and are signs rather than sizes (its conclusion stands - those
  books lost at zero cost). **What it leaves open is not research but an owner decision**: the
  un-relevered h=0.50 book trades 1.47 CAR points for 1.58 points of drawdown and +0.08 of Sharpe,
  now priced in `BLOCKERS.md`.

- **S-25 DONE 2026-09-12 (see journal): measured, not judged - the champion's alpha is an
  overnight object, and the two ops routes in `BLOCKERS.md` are an order of magnitude apart.**
  `scripts/sweep_s25.py` on S-19's validated harness, 3,689 sessions, 6 DIAGNOSTIC ledger rows,
  five clauses pre-registered. **+8.103 bps/day overnight (t +6.80, 94% of the return) against
  +0.738 intraday (t +0.47)**; against an always-invested control at the book's own gross the
  selection difference is **+3.087 (t +4.20) overnight and -0.314 (t -0.37) intraday**, in both
  halves. Not a dividend artifact (price-only +3.231, t +4.36) and not a print artifact (official
  crosses +8.864 vs +8.887). Both conditional books **refused at negative breakeven** - they lose
  at zero cost. Post hoc: the pre-open MOO move is **100% intraday** (+0.604, t +1.43; overnight
  -0.006) and the in-place alternative is worth **+0.18 CAR points** because its overnight leg is
  -0.572 (t -1.79). **Do not re-open as a leg-timing strategy question** - the two variants turn
  the book over 1,248x and 444x equity a year and are behind before a cent of cost is charged.
  Two durable pieces survive it: the leg attribution itself (`legs_simulate`, which reproduces the
  deployed book exactly and can split any convention this harness can run) and the rule that a
  daily-sleeve return statement must name its leg and carry the same-gross always-invested control.
  **What it leaves genuinely open**: the overnight leg is the only place this sleeve has ever shown
  alpha and it has never been *targeted* - a candidate that trades the overnight leg without paying
  for a daily round trip (holding period measured in nights, not sessions; or a sleeve chosen for
  its overnight behaviour) is the one direction this result points to, and it needs its own
  pre-registration and a cost model that survives 1,248x turnover, which nothing here does.

Owner-side status 2026-09-11 09:40 ET: the daily review says the backlog is out of cheap
mechanisms - ten refusals in 24 hours, every intraday candidate negative on 2,686 sessions,
0DTE refused at the quote, breadth refused, and the champion's return traced to its sizing
machinery. That is a finding, not a failure. The next program has to bring NEW information,
not new rules on the same bars. Two tracks are opened below; the second needs the owner.

- **F-3 DONE 2026-09-11 (see journal): refused, and the refusal is a comparison.** Pooled
  out-of-sample **IC +0.01133 (t +2.17)** over 2012-2026 but gross P&L t **+0.18** and only **0.304
  bps per dollar turned**, *less* than F-1's 0.797; the **ridge baseline beats the tree on IC**
  (+0.01223), so there are no interactions here. In LEAN, three cells at **10.322% / 9.908% /
  11.400% CAR** against the champion's 24.403%, all with drawdown above the 35% limit, all refused
  by `evaluate.py` on all four criteria - and worse than S-15's no-ranking-at-all 17.7%. **The
  diagnosis**: on the nine names the sleeve ranks, the forecast is **IC +0.00691 (t +0.97)** against
  the momentum blend's **+0.04268 (t +5.43)**, the two are +0.091 rank-correlated, and as unlevered
  top-3-of-9 books the blend earns **61.51 bps per dollar turned on 105k/day against the model's
  9.29 on 486k/day**. `scripts/sweep_f3.py`, 12 ledger rows, nothing shipped, control reproduces
  `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`, I-1 gate 3,689/3,689. **Do not re-open as a
  feature, model, horizon or universe question** - a longer feature list does not close a six-fold
  gap in the direction the simple signal already points. Two durable pieces survive it:
  `S1_ML_SCORES`/`S1_ML_MODE` (any future external forecast can be ranked through the shipped
  algorithm without editing it) and `evaluate.py`'s new refusal of runs whose window was moved.
- **F-3 (original text, kept for the pre-registration) The same supervised method at a DAILY
  horizon, on the daily sleeve (opened
  by F-1).** F-1's refusal is arithmetic, not a verdict on machine learning: a cross-sectional
  forecast worth 0.8-1.6 bps per dollar traded cannot survive a 0.7-1.4 bps commission floor when
  the book turns 13.8x its equity a day. The same bps of edge spread over a *hundredth* of the
  turnover is a different trade. Build the panel on the daily LEAN store (69 symbols, 1998-2026,
  `scripts/fetch_data.py`; the ETF sleeve is the trusted universe - the single names are
  survivorship-biased and must be excluded from any tradable book, features only), target = next
  5-day or next 21-day cross-sectionally demeaned return, features the daily analogues of F-1's
  (multi-horizon momentum, distance from moving averages in ATR units, realized-vol ratios, volume
  against its own trailing median, the market's own features, cross-sectional ranks). Same
  discipline as F-1 and it is what made F-1 readable: walk-forward expanding retrain, a
  shuffled-label falsification control, a ridge baseline, and the decisive column reported as
  **gross bps per dollar turned over against the cost floor** rather than as P&L. Judge the book
  through LEAN (`scripts/backtest.py` + `scripts/evaluate.py`) against the champion at the same
  cost model (S-18's `stats_by_spread` rule), at 0 bp and at 2 bp. Pre-register before fitting:
  beats the champion on `evaluate.py`'s criteria in the 2020-2026 out-of-sample half, or it is
  refused. **Carry F-1's three usable facts forward**: the target must be in basis points or
  sklearn's absolute early-stopping `tol` silently stops the fit at iteration 1; early stopping
  must use an explicit time-ordered `X_val`/`y_val`, never `validation_fraction`; and the model's
  edge was in the interactions, so the ridge baseline is the control that says whether a tree is
  earning its complexity.
- **F-1 DONE 2026-09-11 (see journal): a real out-of-sample forecast - pooled IC +0.0113 at
  t = +4.74, gross +$1,102/day at t = +3.04 - refused because it earns 0.797 bps per dollar traded
  against a 0.892 bps commission floor at zero spread. Nothing shipped.** `scripts/sweep_f1.py`;
  1.59M-row panel (56 tradable names, 2,682 sessions, 11 decisions/session, 38 causal features),
  train 2016-2021 / validate 2022-2023 / test 2024-2026 with a yearly expanding retrain; 5 ledger
  rows under `intraday/f1_gbdt`. Net **-$2,206/day at t -6.02**, **0 of 3 test years positive**.
  Breakeven slippage by decile **+0.129 / -0.095 / -0.229 / -0.360 bps**; the only cell that clears
  commission does so by 0.129 bps against a 0.3-1.0 bps tick and posts a **-$81,038** worst day on
  $1M. Falsification control (labels shuffled within each timestamp) 0.071 gross bps, a ninth of
  the model's; ridge baseline validation IC +0.0027 against the tree's +0.0105. IC decays by test
  year **+0.0192 -> +0.0113 -> -0.0001** while permutation-importance ranks stay stable at
  0.66-0.77 correlation, the top features being VWAP deviation, its cross-sectional rank and
  relative volume. **Do not re-open as a feature, model, decile or retrain-frequency question** -
  the gap between edge and cost is a factor, not a percent, and every knob inside this design was
  measured. The successor is **F-3**, above: the same method where the turnover is a hundredth.
- **F-1 (original text, kept for the pre-registration) Supervised intraday forecaster on the
  ten-year minute store.** Stop hand-
  designing rules. Build a walk-forward machine-learning model on `data/minute_alpaca` for the
  50 megacaps + the 16-name universe: features per 5-minute bar (returns at 5/15/30/60 min,
  VWAP deviation, range/ATR ratios, volume vs 20-day same-time-of-day average, opening gap,
  time-of-day, day-of-week, cross-sectional rank of each feature across names, the market's
  own features), target = next-30-minute return net of the cost model. Gradient boosting
  (`lightgbm` or sklearn `HistGradientBoostingRegressor`), trained on 2016-2021, validated on
  2022-2023, tested on 2024-2026, retrained yearly (expanding window). Judge on out-of-sample
  P&L after costs of a long-top-decile / short-bottom-decile book rebalanced every 30 minutes,
  and on feature importance stability. Report honestly if it is zero; this is the one
  mechanism class the loop has not tried, and it is the one that scales with the data we now
  have. Pip installs allowed. Nothing deploys without positive in two of three regimes.
- **F-2a DONE 2026-09-11 (see journal): the blocker was mis-stated. Permission is not missing -
  retention is - and the instrument's round trip is 0.488 bps.** The account fetches ES/MES/NQ/MNQ
  1-minute TRADES bars with **zero errors**; IBKR keeps ~**four expired quarters** (ESU5 serves,
  ESM5 does not) and **CONTFUT refuses an `endDateTime` (error 10339)** and caps a minute request at
  one month, so the continuous series cannot be paged. Front-quarter stitch: **447,600 bars / 313
  sessions, 2025-06-09..2026-09-10** (`data/futures/ES.parquet`, gitignored). **Cost floor, the
  durable half**: $347,117 of notional, $2.05/side all-in, one tick wide -> **0.488 bps round trip**
  (0.856 full tick, MES 0.744) against L-1's 6.40-8.20, X-1's 4.70 and F-1's 0.892 of commission
  alone - **10x-17x cheaper**, which is decisive because every intraday refusal on file was a
  refusal on cost. **Both pre-registered mechanisms refused**: overnight-into-the-open +1.161 bps at
  **t +0.78** (gone by 11:00), day-momentum-into-the-last-30m **-2.415 at t -2.56**, i.e. significant
  with the premise's sign reversed. The reversal (+1.927 net, t +2.05) is recorded **post hoc** and
  is concentrated in the first half, but X-1 measured the same shape on equities over 2,684 sessions
  (**-0.69 bps at t -2.80** at 14:30). `scripts/futures_data.py`, `scripts/sweep_f2.py`, 4 ledger
  rows, nothing shipped, no runner-loaded file modified. **Do not re-open as a mechanism question on
  this store** - 313 sessions is 16% of A-4's power requirement and A-10 is the standing lesson.
  Two durable pieces survive it: the **cost table** (the number that justifies the purchase) and the
  **front-quarter stitcher**, so the day deeper history arrives the harness already runs.
- **F-2 (original text, kept for the pre-registration) Index futures track (needs owner: IBKR
  futures permission + CME data, or a Databento
  key for ES/NQ minute history).** ES/NQ trade 23 hours with 20x built-in leverage and no
  daily-reset decay; overnight session momentum into the cash open and the 15:30-16:00 futures
  flow are documented effects that the equity-only data cannot express. Prepare the harness
  (contract roll, tick value, CME fees) so the day the data arrives the tests run.
- **F-5 DONE 2026-09-12 (see journal): refused, 0 of 144 cells - and the always-long control is
  what refuses it, which retro-diagnoses F-4's own momentum column.** F-4 left one piece of
  arithmetic unfollowed (its rule about cheap instruments, applied only to the wrong sign); F-5
  put it to the instrument that could carry it. `scripts/sweep_f5.py`, **SPY / QQQ / IWM**,
  `data/minute_alpaca`, **2,687 sessions / 367,872 legs, 2016-01-04..2026-09-10**; seven clauses
  pre-registered. **Nothing measured here is deployable on the intraday equity sleeve** (the three
  index ETFs are the daily champion's, AGENTS.md disjointness) - the only instrument is the index
  future. **0 of 144** cells reach net t > 2 in two of three regimes. **The diagnosis is clause
  (5)**: session-clustered, `todate`/`flatten` gross is +1.55 bps (t +2.42) but the **always-long
  book on the identical windows earns +0.54** and the forecast difference is **+1.01 at t +0.89**,
  by regime **-0.78 / +1.83 / +2.47** - negative in the first third; **5 of 138 cells** beat the
  control at t > 2 against ~3.2 expected by chance, all five at one entry minute. The index
  reproduces F-4's column at the same minutes and size (11:30 gross +1.99 / +3.64 / +1.57 against
  F-4's +2.24), so **F-4's raw book was a market-factor bet and about a third of its gross is
  drift**. The **published market-intraday-momentum effect is absent**: the classic cell (first 30
  minutes -> 15:30 to the flatten) is gross **-0.19 / +0.10 / +0.05 bps at |t| <= 0.73**, best-t
  book CAR 0.90% / Sharpe 0.25. Nearest miss, post hoc and failing both clauses: QQQ 15:00 ->
  flatten, net +2.03 (t +2.66) but 1 of 3 regimes and +1.75 (t +1.54) over always-long; 1x book
  CAR 4.99% / Sharpe 0.82 / DD 8.4%, so ~10x on the future for the 3%/day mandate at a -36% worst
  session. **Do not re-open as an entry-minute, index, signal-definition or holding-period
  question** - the grid spans all four on 2,687 sessions and the control is what kills it, not the
  grid. Two durable pieces survive it: the **always-long control rule** (a directional intraday
  book is quoted against always-long on the identical windows before its gross is called
  momentum - the time-series twin of the daily sleeve's vol-matched control), and the closing of
  F-4's loose end, which removes the third leg of the CME purchase case in `BLOCKERS.md` while
  leaving the cost table and the 0.62% gross sd per contract standing.
- **F-4 DONE 2026-09-11 (see journal): refused, and refused on SIGN rather than on cost - which
  is the stronger refusal and the one clause (5) did not expect.** `scripts/sweep_f4.py`, 56
  names disjoint from the daily sleeve, **2,664 sessions / 6,654,000 legs, 2016-01-04..2026-09-09**
  - the largest sample this repository has put on one mechanism. **0 of 96 cells** pass the
  pre-registered mark (12 entry minutes x 2 books x 2 exit conventions x 2 signs) and **all 96 net
  columns are negative**, the best being raw momentum at 11:30, **-2.35 bps at t -2.74** against a
  **4.59 bps** pooled round trip. **The gross column is positive at 12 of 12 entry minutes in the
  directional book and 10 of 12 in the dollar-neutral one**: the day's move extends, it does not
  fade, and every gross statistic in the grid reaching |t| > 2 is momentum - neutral 11:30 +1.78
  (t +3.54), raw 11:30 +2.24 (t +2.61), raw 15:00 +0.89 (t +2.48), and the largest single-regime
  cell is **2020-2023 at 15:00, +2.18 at t +3.38 - A-10's exact entry minute with the opposite
  sign**. The second screen (is the effect there but unaffordable?) returns **0 of 48**. Where the
  sign does survive it is a whisper in the diagnostic book only: neutral afternoons, 2024-2026
  -0.81 / -0.59 / -0.42 bps at 14:00 / 14:30 / 15:00 (**t -1.11 / -0.98 / -0.85**) and 2016-2019
  -0.22 / -0.16, i.e. two of three regimes at a fifth to an eighth of cost and never past |t| = 1.2.
  **It does not contradict X-1, it fails to reach it**: X-1 ranked a 15/30/60-minute lookback held
  30-60 minutes; F-4's signal is the whole session's return held to the flatten. **The cheap
  instrument does not rescue it**: charged F-2a's 0.488 bps ES round trip the same legs give
  **0 of 24** and every cell is still negative (-0.37 to -2.73). Stage 2 was not run, on clause (7)
  - a framework run is earned by a stage-1 survivor and there is none - and no ledger rows are
  written, because a stage-1 event study measures bars rather than running a strategy. **Do not
  re-open as an entry-minute, universe, holding-period or magnitude-filter question.** One durable
  rule survives it: **a cost refusal is an argument for a cheaper instrument only when the gross
  column has the right sign at |t| > 2; when the sign is wrong the cheap instrument buys a smaller
  loss, not an edge** - which corrects F-2a's own closing sentence. The only thing left genuinely
  open is the object F-4 did not test and X-1 did: a SHORT lookback reversal at a SHORT horizon,
  a different mechanism that would need its own pre-registration.
- **F-4 (original text, kept for the pre-registration) the afternoon reversal, on the store that
  can actually resolve it.**
  Two independent samples now point the same way - X-1 on 2,684 sessions of megacap equities
  (**-0.69 bps at t -2.80** into 14:30) and F-2a on 313 sessions of ES (**-2.415 bps at t -2.56**
  into the close) - and in both cases it was filed as a by-product rather than tested as a
  mechanism. Test it properly where the power is: `data/minute_alpaca`, 60 symbols, 2016-2026,
  through the shipped intraday framework with the real per-share commission. Pre-register before
  fitting: the signal is the sign of the session's return to time T, the trade is T -> close, and it
  must be positive in **two of three regimes at t > 2** after costs, as every A-track candidate has
  been. **Expect it to fail on cost, not on sign** - that is what X-1's own +0.36 bps against a
  4.70 bps round trip predicts - in which case the result is not a strategy but the **third**
  measurement of an effect whose only viable instrument is the one with a 0.488 bps round trip, and
  that is an argument for the F-2 purchase rather than for a twelfth equity lever.

**2026-09-11 (S-2): the backlog now holds no open research item with a stated mechanism.** A-12,
A-11 and S-2 closed the last three. What remains under "Open" is parked (A-8, by A-4's power
calculation), settled elsewhere (A-3, by A-10), infrastructure (D-2b, E-2b), a standing
per-session measurement (A-5 part 2, ~6.8 sessions from settling), or blocked on a second positive
sleeve that does not exist (S-5). **The binding constraint is the four owner decisions in
`BLOCKERS.md`**, not a missing idea.

- **S-24 DONE 2026-09-11 (see journal): measured, not judged. The harness's "open" is not the
  opening cross, and at the price a real MOO order receives the pre-open move is worth +1.98 CAR
  points.** The daily store's **close is the official closing cross to the cent on every session of
  all nine names** (implied close factor, median day-over-day change exactly 0.000 bps); its
  **open is the first consolidated print, not the primary auction**, so the pre-open identity clause
  failed at **82.18% within 2 bps** against a pre-registered 95%. Re-filled at the official cross on
  2,683 sessions: deployed **22.007%**, S-23's assumption 24.134%, **the real MOO fill 23.985%** -
  the benchmark defect is **-0.149 CAR points** (paired -0.047 bps/day, t -1.86), and the 2 bp
  charged to a call-auction fill that crosses no spread is an overcharge, so the honest band is
  **+1.98 to +3.20**. The surcharge S-23 bounded at 3.10 bps measures **~0.22 bps**, 7% of the
  budget. The pre-registered unsigned statistic (6.12 bps) was **mis-specified and the matched
  placebo caught it**: 30 auction-free seconds move the same names 4.10 bps, signed the cross sits
  -0.213 bps from fair value, and at S-17's 0.68 CAR/bp a real 6.1 bps cost would have shown up as
  ~4.2 CAR points instead of 0.149. `scripts/sweep_s24.py`, 4 ledger rows, nothing shipped, no
  runner-loaded file modified so rule (a) owes no replay. **Do not re-open as an auction-cost
  question** - it is now measured on the official prints at both ends and the residual is a fifth of
  a basis point. Three durable pieces survive it: the **auction store** (`data/auctions/`, official
  opening and closing crosses for the sleeve, 2016-2026) and the `cross_frames` substitution, which
  let any future execution question be asked at real auction prices; the finding that **the store's
  close is exact and its open is not**, which every future "open" number in this repository is
  subject to; and the rule that **an execution cost must be measured with a sign, or by re-filling
  the book, never as an unsigned distance**.

- **S-23 DONE 2026-09-11 (see journal): the loop's half of the pre-open request is written and
  gated, and the move now has a breakeven instead of an assumption.**
  `scripts/paper_trade.py --order-type MOO` sends the order IBKR accepts (`MKT` + `tif="OPG"`) and
  **refuses before connecting** outside 04:00-09:28 ET, because IBKR rejects `OPG` one order at a
  time and a half-rebalanced book is worse than no rebalance (proved live, exit 3). `MKT` remains
  the default: the `--mock --dry-run` plan is unchanged and the **I-1 gate passes 3,689/3,689 at
  5,021 orders**. `scripts/sweep_s23.py` prices both conventions through S-19's book with S-22's
  financing hook: deployed **19.640%** (S-22's figure to the digit) against pre-open **21.515%**,
  **+1.875 CAR** (+1.844 at today's rates), paired **+0.609 bps/day at t +1.44** - *not* significant
  - and out-of-sample weighted more than three to one (IS +0.963, OOS +3.222). **The new number**:
  the opening auction may cost up to **3.10 bps more than the closing auction** before the move
  stops paying, against **+3.2 bps** of measured live execution cost and a minute-store proxy that
  puts the opening minute at **1.0x-2.0x** the closing minute's width (IWM 2.00). So the margin is
  real but thin, and the recommendation is unchanged. 4 ledger rows, nothing shipped, no default
  changed, no task touched. **Do not re-open as a "what is the real opening spread" question from
  this data** - the store has no quotes, so it cannot answer; `daily_fills.py` now scores MOO fills
  against the **open** they aim at, and the first post-move session settles it with live fills.
  Two durable pieces survive it: the `build_order()` helper (any future order type is one branch)
  and the rule that an execution change here is quoted as a **breakeven in `daily_fills.py`'s own
  units**, not as a CAR delta against a costless counterfactual.

- **S-22 DONE 2026-09-11 (see journal): measured, not judged. The three instrument corrections are
  independent, and the deployed daily book's honest expectation is ~20% CAR, not 24.4%.**
  LEAN full-period factorial: control 24.403 / spread 2 bp 23.068 / financing 23.087 / clock bound
  21.384 / **all three 18.785**, against a **pre-registered multiplicative null of 18.811** - an
  interaction of **-0.026 points**, every pair inside 0.021. The S-19 pandas book (new optional
  `financing=` argument, S-19's own rows bit-identical) prices the convention LEAN cannot express:
  the deployed 15:45 clock fully charged earns **19.640%, i.e. 19.954% in LEAN units, -4.449 points**,
  and **19.415% at today's 3.63% benchmark**; its `lag1` cell agrees with LEAN's to **0.03 CAR
  points**. Halves **IS 14.194 / OOS 24.259** against 17.698 / 32.801, out-of-sample weighted more
  than two to one, and drawdown is flat across the whole factorial (23.70 -> 23.00), so it costs
  return and not risk. `scripts/_s22_runs.sh`, `scripts/sweep_s22.py`, 25 ledger rows, nothing
  shipped, control reproduces `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`, I-1 gate 3,689/3,689
  at 5,021 orders. **Do not re-open as a fourth-defect or an interaction question** - the factorial
  is complete and the residual is a fortieth of a CAR point. Two durable pieces survive it: the
  financing hook on `sweep_s19.py` (any future execution question can now be asked on a financed
  book) and the rule that **defects on this sleeve compose multiplicatively**, so they may be priced
  one at a time and multiplied, which is what makes the three audits reusable rather than stale.

- **S-21 DONE 2026-09-11 (see journal): measured, not judged. LEAN charges no financing, and the
  champion's leverage costs 1.32 CAR points full period, 2.03 out of sample and about 2.0 a year
  forward.** `DefaultBrokerageModel.cs:368` -> `MarginInterestRateModel.Null` (empty
  `ApplyMarginInterestRate`), not overridden by the IB model. The book runs a debit balance on
  **83.3% of sessions averaging 0.493x of equity** and has never paid for it. Full period
  **23.087% / 0.939 / DD 24.1%** against 24.403% / 0.994 / 23.7%; IS -0.907, **OOS -2.027**;
  **82% of the sample's $129k of interest was incurred in 2023-2026** as the benchmark went from
  ~0.1% to 5%. Benchmark-only is 0.559 of the 1.106 simple points, so about half is irreducible
  and half is a markup a larger account pays less of. `scripts/rates.py`, `scripts/sweep_s21.py`,
  `scripts/_s21_runs.sh`, 8 ledger rows, `S1_FINANCING` **defaulted off**, control reproduces
  `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`, I-1 gate 3,689/3,689 at 5,021 orders.
  **Do not re-open as a rate-source, tier or day-count question** - the schedule sensitivity is
  already tabulated (`--schedule`) and the two implementations agree on the state. **It is not a
  defect to fix**: the paper account is already paying it and the runner is correct. Two durable
  pieces survive it: the corrected owner frontier in `BLOCKERS.md` (0.75 / 0.80 / 0.82 =
  23.087 / 24.296 / 24.742 financed, so the reward for spending the Reg-T buffer is a fifth
  smaller and its Sharpe argument six times weaker) and `evaluate.py`'s refusal of
  `S1_FINANCING=on` runs as not comparable.

- **S-20 DONE 2026-09-11 (see journal): refused. The regime gate's off-state stays cash, and the
  refusal is the vol-matched column.** The gate is off on **590 of 3,690 sessions (16.0%)** and has
  held nothing there since S-1. Giving it a defensive sleeve (shipped momentum ranking over
  TLT/IEF/GLD, top 1) earns **26.550% / 0.972 / DD 25.4% / std 0.177** against the champion's
  24.403% / 0.994 / 23.7% / 0.155 - +2.15 CAR at *lower* Sharpe - and **scaled to its own realized
  vol the champion would have earned 27.867%, so the mechanism is -1.32 CAR points worse than
  running the existing book bigger**. Paired +0.90 bps/day at t 0.83; `evaluate.py` refuses it at
  0 bp on the drawdown tolerance and passes it at 2 bp, and the pre-registered rule required both.
  The a-priori control (TLT alone) is -2.10 vol-matched; the only positive cell is the **post-hoc**
  GLD-alone pick (+0.656), chosen after reading the probe table, on a conditionality statistic of
  t = 1.66. `scripts/sweep_s20.py`, `scripts/_s20_runs.sh`, 9 ledger rows, nothing shipped, control
  reproduces `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`, I-1 gate 3,689/3,689 at 5,021 orders.
  **Do not re-open as a sleeve, `top_n` or threshold question** - what would change the answer is a
  defensive asset with a *conditional* crisis payoff, and there is none in this store. Two durable
  pieces survive it: `risk_off_sleeve`/`risk_off_top_n` (a future conditional asset can be tested
  without editing the algorithm) and the measurement that **`risk_off_exposure` is inert over
  [0.5, 1.0]** because the vol target cancels an exposure request under a flat margin budget -
  S-8's finding restated for the off-state.

- **S-19 DONE 2026-09-11 (see journal): the deployed daily runner's clock is worth ~1.9 CAR points,
  not 4.75, and the correction is two parts instrument and one part the S-18 promotion.** Six LEAN
  cells (`scripts/_s19_runs.sh`) and a validated pandas book (`scripts/sweep_s19.py`), 10 ledger
  rows, control reproducing `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`. On the promoted
  champion `S1_SIGNAL_LAG=1` is **-3.02 CAR at 0 bp / -2.99 at 2 bp** (S-17 measured -4.75 on the
  retired 3x book), and that cell is an *upper bound* because LEAN cannot fill at the close of the
  session it decided in; the book that can prices the deployed convention at **-1.885 CAR, paired
  -0.599 bps/day at t -1.41**, i.e. **61% of the bound**, after validating against the control's own
  LEAN equity curve at **corr 0.99650**. `BLOCKERS.md` is corrected in place. **Do not re-open as a
  "what is the real lag" question** - the convention is proved from the runner's own log and the
  arithmetic is now done at both ends. Two durable pieces survive it: `sweep_s19.py` can execute the
  shipped signal at any fill convention (the harness any future execution question needs), and the
  measurement that **LEAN's reported Sharpe and Annual Standard Deviation are resampled onto
  calendar days** and so sit ~17% below the same curve's trading-day figures - safe to compare
  within the ledger, never against a statistic computed elsewhere.

**Priority after F-2a (2026-09-11), in order: (1) A-5 part 2 and `daily_fills.py`, the two standing
per-session measurements, unchanged and both ~4.4 sessions from settling; (2) per-session ops;
(3) F-4, the afternoon reversal on the Alpaca store - the only open item with a mechanism, a
pre-registration and enough sessions to resolve it, opened above; (4) the owner decisions in
`BLOCKERS.md`, unchanged in order - the pre-open move (+1.98 CAR at the real MOO fill), the Reg-T
buffer, `equity_frac` on the intraday sleeve - now joined by a **fifth** that is a purchase rather
than a policy: CME history back to ~2016 for ES/NQ, which F-2a priced at a 0.488 bps round trip
against the 4.70-8.20 bps that has refused every intraday candidate on file.** F-2a opened F-4 and
closed the last "needs data" item that had never been checked; the reusable rule it leaves is that
**a blocker nobody has probed is an assumption**, and this one was wrong in its subject (retention,
not permission) and understated in its value. One column is added to the compulsory four: any future
candidate that could be expressed on futures owes **the cost floor of the instrument it would
actually trade on**, because on this repository's evidence that floor, not the signal, has decided
every intraday verdict.

Superseded, kept for the reasoning: **Priority after S-24 (2026-09-11): unchanged in order from S-23 below, with one item now fully
priced.** The pre-open move is no longer carrying an assumption - it is **+1.98 CAR points** at the
real MOO fill (band to +3.20), the surcharge is **~0.22 bps against a 3.10 bps breakeven**, and the
loop has nothing further to add to that decision. The compulsory columns are now four: vol-matched
(S-20), financed (S-21), the breakeven surcharge for anything that moves *where* an order fills
(S-23), and - new - **priced at the official auction print rather than the store's open** (S-24),
because the store's open is the first consolidated print and only its close is the real cross.

**Priority after S-23 (2026-09-11), in order: (1) A-5 part 2 and `daily_fills.py`, the two standing per-session measurements - A-5 part 2 is ~4.4 sessions from settling, and `daily_fills.py` now carries the instrument that settles the S-23 breakeven the moment the task moves; (2) per-session ops; (3) the owner decisions in `BLOCKERS.md`, unchanged in order but with the top one now reduced to a single task change: the **pre-open move** (+1.844 CAR at today's rates, breakeven +3.10 bps of extra opening-auction cost, the loop's half merged and gated), then the Reg-T buffer (+1.209 / +1.655 financed at budget 0.80 / 0.82) and `equity_frac` on the intraday sleeve; (4) F-2, the index futures track, which needs data the human must buy.** S-23 opened nothing: it finished a request rather than starting a line of research, and the one general thing it leaves behind is a framing rule - **an execution change on this sleeve is quoted as a breakeven in the units `daily_fills.py` measures on live fills**, because a CAR delta against a counterfactual that charges the other side nothing is not a decision, it is an assumption. The three compulsory columns are now vol-matched (S-20), financed (S-21) and, for anything that moves *where* an order fills, the breakeven surcharge (S-23).

Superseded, kept for the reasoning: **Priority after S-22 (2026-09-11), in order: (1) A-5 part 2 and `daily_fills.py`, the two standing per-session measurements - A-5 part 2 is ~4.4 sessions from settling and `daily_fills.py` now gets input every rebalance (10 fills, +3.2 bps, se 4.5); (2) per-session ops; (3) the owner decisions in `BLOCKERS.md`, which remain the whole of the unblocked work, now in a corrected order of value: the **pre-open task move** is the cheapest and best-priced of them at **+1.85 CAR points on an honestly-costed book at today's rates**, then the Reg-T buffer (+1.209 / +1.655 financed at budget 0.80 / 0.82) and `equity_frac` on the intraday sleeve; (4) F-2, the index futures track, which needs data the human must buy.** S-22 closed the instrument audit rather than opening anything: spread (S-17), clock (S-19) and financing (S-21) are now measured, composed and **proved independent to 0.026 CAR points**, so there is no fourth defect of that class to look for and no reason to re-run the three against each other. **One number replaces another everywhere on this sleeve**: the deployed daily book's honest expectation is **~20% CAR (19.95% at historical rates, 19.42% at today's)**, not the champion's 24.403%, and any future candidate quoted against the headline is being flattered by about 18%. The two compulsory columns from S-20 (vol-matched) and S-21 (financed) are unchanged, and S-22 adds the rule that makes them cheap: **corrections on this sleeve multiply**, so a cell may be priced against one defect at a time and composed afterwards.

Superseded, kept for the reasoning: **Priority after S-21 (2026-09-11), in order: (1) A-5 part 2 and `daily_fills.py`, the two standing per-session measurements - A-5 part 2 is ~4.4 sessions from settling and `daily_fills.py` now gets input every rebalance (9 fills, +3.9 bps); (2) per-session ops; (3) the owner decisions in `BLOCKERS.md`, which remain the whole of the unblocked work and whose headline item has just been re-priced: the Reg-T buffer now reads +1.209 / +1.655 CAR at budget 0.80 / 0.82 rather than +1.500 / +2.071, with the Sharpe argument six times weaker; then the runner's clock (-1.9 CAR, S-19) and `equity_frac` on the intraday sleeve; (4) F-2, the index futures track, which needs data the human must buy.** S-21 opened nothing and closed nothing that was open - it moved a number, and it is the third and last of the instrument audits that were available (spread S-17, clock S-19, financing S-21). **Two columns are now compulsory on any future daily-sleeve comparison**: the vol-matched one (S-20) whenever a cell changes realized volatility, and the financed one (S-21) whenever two cells carry *different amounts of leverage* - the second exists because the owner's own frontier was being judged on numbers that gave the borrowing away.

Superseded, kept for the reasoning: **Priority after S-20 (2026-09-11), in order: (1) A-5 part 2 and `daily_fills.py`, the two standing per-session measurements - A-5 part 2 is ~4.4 sessions from settling and gets input every session; (2) per-session ops; (3) the owner decisions in `BLOCKERS.md`, which remain the whole of the unblocked work: the Reg-T buffer (budget 0.78 / 0.80 / 0.82 earn 25.307 / 25.903 / 26.474 at rising Sharpe on the unlevered book), the runner's clock (-1.9 CAR, S-19), and `equity_frac` on the intraday sleeve; (4) F-2, the index futures track, which needs data the human must buy.** S-20 closed the last daily-sleeve item that was neither a ranker lever nor a risk-posture parameter, and it closed it by measuring that it *is* a risk-posture parameter in disguise. **Read every future daily-sleeve cell through the vol-matched column** (`sweep_s20.py --report`): S-15, S-16 and S-20 are three forms of one finding - on this sleeve anything that looks like new return is a size decision until it beats the control scaled to its own realized volatility.

Superseded, kept for the reasoning: **Priority after S-19 (2026-09-11), in order: (1) A-5 part 2 and `daily_fills.py`, the two standing per-session measurements - A-5 part 2 is ~4.4 sessions from settling and gets input every session; (2) per-session ops; (3) the owner decisions in `BLOCKERS.md`, which remain the whole of the unblocked work, now in a corrected order of value: the Reg-T buffer (S-16/S-18: budget 0.78 / 0.80 / 0.82 earn 25.307 / 25.903 / 26.474 at rising Sharpe on the unlevered book), the runner's clock (**-1.9 CAR**, re-priced by S-19 and no longer the largest number on this sleeve), and `equity_frac` on the intraday sleeve; (4) F-2, the index futures track, which needs data the human must buy.** S-19 did not open an item; it closed one and moved a number.

Superseded, kept for the reasoning: **Priority after F-3 (2026-09-11), in order: (1) A-5 part 2 and `daily_fills.py`, the two standing per-session measurements - A-5 part 2 is ~5.5 sessions from settling and now gets input every session; (2) per-session ops; (3) the owner decisions in `BLOCKERS.md`, which are now the whole of the unblocked work, in order of the number attached to them: the runner's clock (-4.75 CAR, the largest unblocked number on the daily sleeve), the Reg-T buffer (S-16: budget 0.78 / 0.80 / 0.82 earn 25.307 / 25.903 / 26.474 at rising Sharpe on the now-unlevered book), and `equity_frac` on the intraday sleeve; (4) F-2, the index futures track, which needs data the human must buy.** The supervised track is closed by F-1 and F-3 together: the model finds an IC of about +0.011 wherever it is pointed, and on both sleeves it rides a weaker mechanism than the one already shipped - intraday it could not clear its commission, daily it could not out-rank a four-horizon momentum blend that is itself a t = +5.4 signal worth 61 bps per dollar turned.

Superseded, kept for the reasoning: **Priority after F-1 (2026-09-11), in order: (1) F-3, the
supervised method at a daily horizon -
F-1 proved the method finds real out-of-sample signal on this data and refused it on turnover
arithmetic, so the next run is the same method where the turnover is a hundredth; (2) A-5 part 2
and `daily_fills.py`, the two standing per-session measurements (A-5 part 2 is ~5.5 sessions from
settling and now gets input every session); (3) per-session ops; (4) the owner decisions in
`BLOCKERS.md` - the Reg-T buffer, which S-18 made more valuable, and the runner's clock, which is
the largest unblocked number on the daily sleeve at -4.75 CAR.** The intraday sleeve has now been
refused by a rule-based track (A-3 .. A-12), by every instrument the owner's mandate named (O-1,
O-1b, L-1, X-1, O-2, S-2) and by a supervised model with a measurably real forecast (F-1). Its
binding constraint is not a missing signal - it is that 13.8x daily turnover costs more than any
30-minute forecast measured here is worth.

Superseded, kept for the reasoning: **Priority after S-18 (2026-09-11), in order: (1) F-1, the
supervised intraday forecaster - the only
open item left with a mechanism, and the one class of model this loop has never tried; (2) A-5
part 2 and `daily_fills.py`, the two standing per-session measurements (A-5 part 2 is ~6 sessions
from settling and now has live input every session); (3) per-session ops; (4) the owner decisions in
`BLOCKERS.md` - the Reg-T buffer, which S-18 made more valuable, and the runner's clock, which is
the largest unblocked number on the daily sleeve at -4.75 CAR.** S-18 closed the daily sleeve's last
unblocked research item by promoting it; every remaining daily-sleeve lever is a risk-posture
parameter and therefore the owner's.

Superseded, kept for the reasoning: **Priority after S-17 (2026-09-11), in order: (1) S-18 - promote
the unlevered cell properly, which is the first daily-sleeve candidate since O-1b that no owner
answer blocks; (2) A-5 part 2 and `daily_fills.py`, the two standing per-session measurements;
(3) per-session ops; (4) the owner decisions in `BLOCKERS.md`, which now include the runner's
clock.** S-17 replaced the post-S-16
conclusion that only owner decisions remained: that was true about strategies and wrong about the
instrument. The harness charges no spread (0.68 CAR per bp, and the cells it has been ranking differ
by 2.7x in order count), and the deployed runner acts on a signal a session stale (-4.75 CAR). Both
are measurement defects, which is why sixteen iterations of sweeping could not see them. Everything
else under "Open" is parked, settled, infrastructure, or an owner decision. Do not open a new
intraday lever (the A-track is out of both levers and defences, and the S-track's last mechanism
closed with S-2), and **do not open a new ranker lever**: S-15 priced the ranker at +3.66 CAR at
t = 0.92 vol-matched, and S-14 showed it does not survive dilution. The two components that carry
the book - the vol target / margin budget (71% of the return) and the regime filter (the drawdown
profile) - are risk-posture parameters, so the next move on this sleeve is an owner decision, not
a backtest.

- **S-18 DONE 2026-09-11 (see journal): promoted. The champion is the unlevered book - same return,
  0.073 more Sharpe, 4.2 fewer points of drawdown at 2 bp, 40% less commission, 1.50x exposure
  against 2.25x.** Eight cells (`scripts/_s18_runs.sh`, `scripts/sweep_s18.py`) plus three
  verification runs; new `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`, and `S1_PROXY=on
  S1_DD_HALVE=0.15 S1_DD_FLAT=0.25` reproduces the retired champion bit-for-bit. Halves: IS
  **-1.48 CAR (t -1.25)**, OOS **+1.94 (t +0.87)**, Sharpe better in both. `evaluate.py` now
  compares at the same cost model (`champion.json.stats_by_spread`, `backtest.py` records the
  `S1_*` environment) and produced both verdicts: 2 bp BEATS, 0 bp refused by 0.001. Band measured
  on the new book and **not** changed (+0.103 CAR at 2 bp, t +0.94). **Do not re-open as a proxy or
  breaker question** - both are retired on three iterations of evidence and one environment variable
  away. **The successor is not another S-track cell**: what is left on this sleeve is the owner's
  margin-budget question (now worth more: 0.78 / 0.80 / 0.82 give 25.307 / 25.903 / 26.474 at rising
  Sharpe on the unlevered book) and the runner's clock (-4.75 CAR, S-17), both in `BLOCKERS.md`.
- **S-18 was opened by S-17 2026-09-11 as: promote S-16's (e+g) cell at the unchanged
  0.75 margin budget - the first daily-sleeve candidate since O-1b that no owner answer blocks.**
  The cell is `S1_PROXY=off S1_DD_HALVE=9.0 S1_DD_FLAT=9.0` (unlevered parents, no drawdown
  breaker, budget untouched at 0.75, economic exposure 1.50x against the champion's 2.25x). At zero
  spread it is a dead heat refused by 0.001 CAR points; at any spread above ~0.03 bp it wins on CAR,
  Sharpe and drawdown at once (2 bp: **23.068 / 0.938 / DD 25.0 / $24.9k fees** against the
  champion's 22.926 / 0.865 / 29.2 / $41.9k). **Three pieces are missing and each is a run, not a
  judgement call:** (a) the in-sample 2012-2019 and out-of-sample 2020-2026 halves at this
  configuration, which S-16 only produced for the budget-0.80 variant, run both at 0 bp and at 2 bp;
  (b) a decision on what `evaluate.py` compares against, because the recorded champion stats are
  zero-spread and a candidate charged 2 bp cannot be measured against them - the like-for-like
  comparison is the one in journal section 4 and the promotion should be made on it, with
  `champion.json` recording both columns; (c) `scripts/compare_orders.py` re-run and a new
  `OrderListHash` baselined, since promotion moves the live order list (I-1's deploy gate). **Do not
  promote on the return difference** - it is +0.05 bps/day at t = +0.12. The case is identical
  return for 0.073 more Sharpe, 4.2 fewer points of drawdown and 40% less commission, and the
  write-up must say that. Related and cheap once (a) is running: `min_order_value` 0.03 is worth
  +0.57 CAR at 2 bp (t +1.22) with 3.8 fewer points of drawdown, so the band should be swept on the
  *promoted* cell rather than on the champion, and S-13's warning that its fine structure is path
  luck still stands.
- **S-17 DONE 2026-09-11 (see journal): the harness charges no spread and the deployed runner is a
  session late. Nothing shipped, nothing promoted, no default changed.** Two new knobs on the
  shipped algorithm, both defaulting to the champion (`S1_SLIPPAGE_BPS`, `S1_SIGNAL_LAG`), twelve
  full-period LEAN cells (`scripts/_s17_runs.sh`, `scripts/sweep_s17.py`), a new live-fill
  instrument (`scripts/daily_fills.py`), 12 ledger rows, control reproducing `OrderListHash
  5246804e17a67af90028ffceead7d3b3`. Spread ladder **24.404 / 23.699 / 22.926 / 21.129 / 18.216** at
  0 / 1 / 2 / 5 / 10 bp with drawdown **25.1 -> 32.3**, i.e. **0.68 CAR per bp**; measured execution
  cost on the 6 paper fills **+2.9 bps (se 6.8)**; signal lag of one session **-4.75 CAR at t
  -2.65**, proved from `ref_price` in 6 of 6 fills and the runner's own logged `as_of`. **Do not
  re-open as a "what should the constant be" question** - it is a standing measurement now
  (`daily_fills.py` after every paper close, same rule as A-5 part 2: move the default only at two
  standard errors). **Do re-use the knobs**: judge every future daily-sleeve cell at 0 bp *and* at a
  non-zero spread, because the zero-spread comparison is biased toward whichever cell trades most.
- **S-16 DONE 2026-09-11 (see journal): the 3x proxies and the drawdown overlay are worth zero
  return between them; three passing candidates are parked behind the margin-budget question.**
  Nine full-period cells plus two sub-periods (`scripts/_s16_runs.sh`, `scripts/sweep_s16.py`), 11
  ledger rows, control reproducing `OrderListHash 5246804e17a67af90028ffceead7d3b3`. **Both off at
  the unchanged 0.75 budget: 24.403% vs 24.404%, paired -0.00 bps/day (t -0.00, 3,689 days), at std
  0.155 / DD 23.7 / PSR 33.2 / $27.2k fees** against 0.170 / 25.1 / 23.0 / $45.7k. Budget dial with
  proxies off: 0.78 **25.307 / 1.003 / 24.6**, 0.80 **25.903 / 1.008 / 25.1**, 0.82 **26.474 / 1.012
  / 25.7 at std 0.168** (+0.66 bps/day, **t 2.02**; IS +0.07 / 0.24, OOS +1.36 / **2.16**). Overlay
  shelf at 0.80: shipped 24.551 / DD 25.5 -> wide 0.20/0.30 25.333 / **25.0** -> off 25.903 / 25.1.
  Sub-periods of the 0.80 cell: **IS 18.894 / 0.923 / 25.1**, **OOS 34.687 / 1.124 / 23.6**.
  `evaluate.py`: three cells "BEATS champion", the budget-neutral one refused by **0.001 CAR
  points**. **Do not re-open as a proxy-map, breaker-threshold or budget-grid question** - the
  frontier is measured and the remaining decision is the Reg-T buffer, which is the owner's. The
  evidence and a fourth option that dominates O-1b's (b) are appended to `BLOCKERS.md`.
- **S-15 DONE 2026-09-11 (see journal): 71% of the champion's CAR is no skill of any kind, and no
  single switch is distinguishable from zero. Nothing shipped, nothing judged.** Eight full-period
  LEAN cells, each the shipped algorithm with one switch removed through an `S1_*` override
  (`scripts/_s15_runs.sh`, read by `scripts/sweep_s15.py`); two new knobs, `S1_MIN_MOMENTUM` and
  `S1_PROXY`, both defaulting to the champion, with the control reproducing `OrderListHash
  5246804e17a67af90028ffceead7d3b3`. Champion **24.404 / 0.921 / 25.1 / 0.170**; **(f) no skill at
  all 17.282 / 0.711** (whole signal stack = **+7.12 CAR, t 1.37**); (a) no ranking 17.700 at std
  0.137 and **vol-matched 20.745** (**ranking = +3.66 CAR, t 0.92**); (b) regime off 22.383 at
  **DD 31.4** with **zero in-sample contribution** (-0.04 bps/day); (e) **proxies off 23.128 at
  Sharpe 0.950 / DD 23.6 / PSR 27.4 / $25.6k fees** - better risk-adjusted than the champion;
  (g) overlay off **25.998**, so the breaker costs 1.59 CAR (-0.51 bps/day, **t -1.93**, OOS
  **-2.35**) for 2.1 points of drawdown; (d) S-12's tilt +0.80 CAR but **+0.52 bps/day IS,
  -0.06 OOS**. **Do not re-open as a parameter question** - the answer is a table, and it says the
  levers left are risk-posture ones in `BLOCKERS.md`.

**Owner instruction 2026-09-10 (midday) - the list is now exhausted, 2026-09-10 20:4x UTC.**
O-1, O-1b, L-1, X-1 and O-2 have each been measured on the full history and each refused. Nothing
in this repository reaches 3-10%/day: the closest candidate, O-2, needs 3.9x equity at risk per
session against a defined-risk ceiling of 1.0x. What is left is not another lever - it is the three
open owner questions in `BLOCKERS.md`, of which the **drawdown cap** now binds every candidate the
mandate asks for. Original instruction: the strategy set is too weak and too calm. Target is
3-10% portfolio moves per day from fast, high-win-rate strategies. Volatility must come from
EDGE and instruments with intrinsic leverage, not from sizing up unproven signals (A-10 showed
the intraday mix has none yet). Research priority from here, in order: **O-1** (options-implied
regime gate, data ready), **L-1**, **X-1**, **O-2** (needs owner's options permission), then the
A-track refinements. Every candidate is judged on ten years of Alpaca bars with a three-regime
split and real costs; nothing is deployed without being positive in at least two regimes.

- **S-14 DONE 2026-09-11 (see journal): breadth makes the daily champion monotonically worse, and
  its whole cross-sectional edge is +2.02 bps/day at t = 2.07. Refused, nothing shipped.** Three
  nested ranking sleeves - etf9 (shipped), sector (17), broad (22) - after fetching 13 ETFs
  through the D-1 pipeline; presets in `main.py`, decomposition in `scripts/sweep_s14.py`, 7
  ledger rows. LEAN full period: **24.404% / 0.921 / 25.1% -> 17.253% / 0.663 / 30.3% -> 11.622%
  / 0.430 / 29.7%** at unchanged realized vol; `sector` loses both halves (IS 12.626%, OOS
  22.929%); `evaluate.py` refuses all four candidates. Leverage-free decomposition
  (`selected = pool_mean + spread`): **etf9 7.21 = 5.20 + 2.02 (t 2.07)**, sector17 5.73 = 4.90 +
  0.82, broad22 5.27 = 4.32 + 0.94, paired **-1.37 (t -1.95)** and **-1.89 (t -2.23)** bps/day,
  four fifths of it the spread rather than the menu. At `top_n=5` no sleeve's spread is
  significant (etf9 +0.84, t 1.16). Vol-matched steelman (`sector`, top_n 5, budget 0.867, std
  0.168): **22.879% / 0.872** on 8,279 orders. **Do not re-open as a "which names" question** -
  three pools, two holding counts and a vol-matched control agree. What breadth does buy is
  drawdown (unlevered 22.4% -> 14.3%), which is a risk-posture trade, not a return one. Control
  reproduces `OrderListHash 5246804e17a67af90028ffceead7d3b3` and `compare_orders.py` passes
  3,689/3,689, so the daily deploy path is untouched. Also fixed in `fetch_data.py`: the manifest
  is now **merged** rather than rewritten (a 13-symbol fetch had erased the other 69 entries;
  restored from git, merge verified at 1 re-derived / 81 kept) and a one-symbol `--symbols` run no
  longer crashes on yfinance's single-ticker column layout. Successor: **S-15**, above.
- **A-12 DONE 2026-09-11 (see journal): the ORB whipsaw lockout is refused - the reversal re-entry
  is the only profitable trip category in the sleeve, and 98% of the loss is in first entries.
  Nothing shipped.** Motivated by the 2026-09-10 paper session, where one stopped-out-then-flipped
  pattern in semis carried 77% of a -6,779 day; the shipped ORB module permits it because
  `max_entries` is counted per *side*. Built `reentry_block` / `reentry_mode` on the module
  (default **0 = off**, three modes so the mechanism can be separated from the mere loss of
  turnover) and `scripts/sweep_a12.py`; 18 ledger rows under `intraday/active`. **Stage 1 is an
  event study with nothing to fit**: 44,219 round trips over 2,686 sessions, each labelled by what
  preceded it that day - first entry **-$25/trip (t -2.66, -$872,347 total)**, `flip` **+$15
  (+0.65, +$70,708)**, `same` -$20 (-1.03, -$88,087) - and the effect is entirely inside the first
  fifteen minutes, with the sign reversed from the anecdote (**flip +$78/trip at t +1.72, same
  -$81 at t -1.96**, every longer gap flat). **Stage 2, the paired grid**: flip15 **-$31/day
  (t -1.17)**, flip60 -$47 (-0.93), any15 +$3 (+0.08), same15 **+$38 (+1.69)**, same60 +$23
  (+0.68); **0 of 5 cells reach t > 2 in any regime**, and the book stays negative in all of them
  (control **-$331/day, t -1.35**; best variant -$293, -1.19). The one positive cell is the
  falsification control and was chosen after seeing the gap table, so it is in sample by
  construction. **Do not re-open as a block-length, mode or symbol question** - the mechanism was
  measured on 44,219 trips and its sign is the reverse of the premise. Rule (a) replay passed
  (2026-09-08, deployed config: 34 trades, 368 decisions, flat, P&L -2,302, identical to the
  post-fee-fix figure), so the new parameter is inert on the live path. **A free measurement**: the
  control is the first full-sample run under A-5 part 2's corrected commission, with trades/day
  identical to A-10's rows, so **ORB alone is -$331/day, not the -$289 on record**.
- **L-1 DONE 2026-09-10 (see journal): leveraged ETFs do not revert intraday - gross is negative
  before costs, in both directions, on all six names. Refused, nothing shipped.** Two stages, the
  event study first so the mechanism was measured with nothing to fit: over 2016-2026 Alpaca bars
  (TQQQ/SQQQ/UPRO/SPXU fetched here, ~1.03M bars each, joining SOXL/SOXS), fading a VWAP deviation
  of `z` ATRs at the next bar's open and unwinding `h` bars later earns **-0.28 to -3.16 gross bps
  per round trip in all sixteen cells**, against a **6.4-8.2 bps** round-trip cost. Stage 2 through
  the shipped framework on 2,686 sessions: fade on six names **-$902/day at t = -9.45**, on the
  three deployable names -$667/-9.02, and the **continuation control also loses** (-$587/-6.26) -
  0/3 regimes for every variant against the 2/3-at-t>2 rule fixed before the runs. **The durable
  finding is a statistics one**: the same event study *passes* 3/3 regimes at +7.09 bps if sessions
  are equally weighted, because `corr(events per session, session mean gross) = -0.340 at t = -17.5`
  - quiet sessions produce 2.4 stretches that revert (+37.9 bps), violent ones produce 25.5 that do
  not (-10.6). **A per-event average over sessions is not an estimate of what a book earns**;
  `sweep_l1.py` now prints it as a labelled diagnostic and decides on the money-weighted number.
  The harness was audited before it was believed: `scripts/_l1_reconcile.py` matches 235 harness
  round trips to event-study entries at **corr 1.000** (+1.12 vs +1.12 bps). Cost is structural
  here - the inverse ETFs trade at $20-26 and IBKR charges per share, so SOXS pays 13.58 bps a
  round trip against TQQQ's 4.85. **Do not re-open as a threshold, horizon or name-selection
  question** - the negative is on gross, in both signs. Only `scripts/intraday_common.py` changed
  (two constants, no behaviour); the 2026-09-08 replay reproduces the deployed sleeve exactly.
  **On the mandate**: at 0.9 gross on 3x ETFs the book's daily P&L sd is 0.49% of equity - the
  leveraged instruments supply volatility, not edge.
- **X-1 DONE 2026-09-10 (see journal): the cross-sectional intraday spread on the megacaps is
  +0.36 bps against a 4.70 bps round trip - real, tiny, and 13x too small. Refused, nothing
  shipped.** Fetched the 40 missing megacaps (2016-2026, ~1.04M bars each; the Alpaca store is now
  60 symbols) and re-derived `_splits.json` for the union, every pre-existing factor identical.
  Stage 1, sixteen parameter cells over **2,684 sessions and 267k-587k legs each**: gross is
  **positive (momentum, not reversal) and never above +0.36 bps per leg**, best cell "since the
  open, hold 60, k=5" at t = +2.00 pooled and +1.44 / +0.83 / +1.34 by regime - **no cell reaches
  t > 2 in two of three regimes even before costs**, and net of costs the verdict is 0 of 32.
  Stage 2, the module through the shipped framework on one year per regime: momentum
  **-$1,681/day (t = -16.9)** and the reversal control **-$1,786/day (t = -18.8)**, 0/3 regimes
  both. **The symmetry is the finding**: backing out costs leaves +$79/day and -$97/day of gross
  on a $1M book - zero in both directions - while turnover of 8.07x equity/day pays $1,760/day.
  Stage 1 predicted +$20/day of gross at the module's defaults, so the two instruments agree and
  no harness audit was owed. **Do not re-open as a lookback, horizon, decile or rebalance-frequency
  question** - the grid spans all four and the mechanism is an order of magnitude under the cost
  floor everywhere. Worth keeping for a later idea: the gross effect is **+0.63 bps at 10:30 and
  -0.69 bps (t = -2.80) at 14:30** - continuation in the morning, reversion in the afternoon - and
  the per-share commission means the same strategy costs 5.45 bps in 2016-2019 and 4.00 in
  2024-2026. **On the mandate**: this book's daily P&L sd is 0.27% of equity, the least volatile
  thing on the owner's list.

Owner decisions of 2026-09-09 (see `BLOCKERS.md`): paper trading is approved and running,
the 35% drawdown cap stays, promotion is now return-first with a 0.03 Sharpe tolerance and a
1-point drawdown tolerance, delisted-inclusive data is deferred, the no-trade band stays 0.01.
Priority is therefore the **intraday active sleeve (A-track)**: volatility is to be earned with
a second, uncorrelated intraday sleeve, not by leverage on the ETF sleeve. IB Gateway is up.

Owner instruction 2026-09-09 (afternoon): by the 2026-09-10 open the paper account must run a
volatile, active, high-turnover book on most of the capital. The infrastructure for that now
exists (see AGENTS.md "The intraday active sleeve"): 16-name disjoint universe, IBKR minute
store, causal features, three strategies, a minute backtester, and a live trader with replay,
scheduled 09:25 ET. **The loop's job from here is signal quality**: the first honest numbers
(2 names, 62 sessions) were ORB +10% annualized / Sharpe 2.5, VWAP-trend -12% after costs,
late-day momentum flat. Every A-track iteration: pick one strategy, change one thing, run
`scripts/intraday_backtest.py --split <date>` on the full universe, keep it only if OOS
improves after costs, journal it, and update `live/intraday_config.json` only per AGENTS.md rule (c).

- **S-17 part 2 Measured fill slippage on the *daily* sleeve. Standing per-session job, opened
  2026-09-11.** Run `python scripts/daily_fills.py` after every paper close. It reports two numbers
  and they must not be pooled: **execution cost** against the 15:45 close the runner aims at
  (currently **+2.9 bps notional-weighted on 6 fills / $1.42M, per-fill sd 16.7, se 6.8**), and the
  **convention difference** against the D+1 open the backtest fills at (-16.9 bps, se 25.8, which is
  a whole session of price movement and is uninformative at this sample size - it is priced by
  `S1_SIGNAL_LAG` over fourteen years, not here). LEAN charges **0 bps** of spread by default, and
  each bp is worth **0.68 CAR points** on the champion, so this constant owns roughly 2 points of the
  reported return. Same decision rule as A-5 part 2: move `S1_SLIPPAGE_BPS`'s default only when the
  gap to the current value exceeds two standard errors, with a journal entry. At the observed sd of
  16.7 bps, ~130 fills are needed to place the constant within 1.5 bps, which at 3 fills a session is
  a long standing job - so judge candidates at a *bracket* (0 bp and 2 bp) rather than waiting for it.
- **A-5 part 2 Measured fill slippage. First fills measured 2026-09-10 (see journal); slippage is
  still open, the commission half is CLOSED and shipped. Standing per-session job.**
  **Slippage, still open**: 19 fills / $1.1M on the partial first session give **+1.30 bps
  notional-weighted (se 1.65) against the shipped 1.50, z = 0.12** - not distinguishable, so
  `SLIPPAGE_BPS` was not touched. **The reference question is settled and it was a red herring**:
  the same 17 fills priced against the next-bar open score +1.10 bps / sd **7.55** and against the
  decision-close fallback +1.55 / sd **7.13**, with the realized close-to-open gap at sd 2.16 and
  correlation -0.33 to the fill error, so the fallback is if anything *quieter*. The whole-store
  gap sd of 6.20 bps predicted the opposite; a population noise estimate does not transfer to the
  minutes a strategy selects. The cost is the **~10 s detection latency** (median 10 s, worst 13),
  which is mean-zero drift, so only fills buy precision: **166 fills, ~3-4 full sessions at 49
  trades/day**, to resolve the constant against breakeven at 2 se. Run
  `python scripts/slippage_report.py --refresh` after **every** paper close (`--refresh` pulls the
  closed sessions into `data/minute` and refuses a session still trading), report the running
  notional-weighted mean and its standard error, and move `SLIPPAGE_BPS` only when the gap exceeds
  two standard errors, with a replay and a journal entry (rule a). **Do not re-open the reference
  as a question.** **Commission, closed**: IBKR's own `commissionReport` matched the harness on all
  twelve buys to $0.004 and undercharged all five sells; fitting the excess reproduces every sell
  **to the cent**, so the harness was omitting the US sell-side regulatory pass-throughs - **SEC
  Section 31 $20.60 per $1M of proceeds (0.206 bps) and FINRA TAF $0.000198/share**, now charged in
  `intraday_common.commission()` when `shares < 0`. Paired 260-session control: costs/day
  $1,025 -> **$1,078**, $/day $610 -> **$557**, CAR 15.3% -> **14.0%**, Sharpe 0.689 -> **0.640**,
  trades 12,743 -> 12,742. **The breakeven is therefore 2.52 bps, not 2.62**, and every intraday
  number quoted before 2026-09-10 12:00 ET is 5.2% light on cost. Rule (a) replay passed twice
  (2026-09-08, deployed config, current trader): identical 34 trades / 368 decisions / flat at
  close, P&L -2,280 -> -2,302, the whole difference being the measured fees.
- **O-1b DONE 2026-09-10 (see journal): the implied-vol size dial is a leverage dial and costs 50%
  more turnover than the constant that replaces it. Refused, nothing shipped.** Built the dial on
  the champion (`iv_scale_power` etc. in `signals.py`, `S1_IV_SCALE_*` in `main.py`,
  `iv_regime.py --export-csv` for the pyarrow-free LEAN Python), causal by strict prior-day
  lookup, applied after the margin-budget shrink, uncovered pre-2017 days at factor 1.0 and the
  study judged on 2017-04-03..2026-09-04. **The inverse reading that the O-1 residual motivates
  loses on both axes** (CAR 27.69 vs 29.46 control, and std 0.182 vs 0.179). The direct reading is
  a pure vol dial - std monotone 0.179/0.189/0.198/0.204 in the tilt, Sharpe peaking at power -0.5
  and decaying - and **at matched realized vol a constant gross-up with no IV in it scores 31.107%
  / 1.040 / 0.189 against the dial's 31.376% / 1.050 / 0.189, on 3,027 orders against 4,550**. The
  shipped-defaults regression reproduces `OrderListHash 5246804e17a67af90028ffceead7d3b3` exactly.
  **Do not re-open as a field, window or threshold question** - the negative is that the only
  contribution available is the *level* of gross, which `margin_budget` already provides free.
  Kept for the record, the original item: O-1 refused the
  *gate* but measured a real residual: corr(SPY implied vol, |intraday daily P&L|) = **+0.252 at
  t = +12.67**, positive in all three regimes for all three features. Implied vol forecasts how
  big a day will be and not which way, which is worthless on a book whose level is negative - and
  potentially worth something on **S-12, where the level is positive**. Test it as a size scaler
  on the daily champion: scale gross by the inverse of prior-day SPY ATM IV against its trailing
  median (and test the direct sign too), judged through `scripts/backtest.py` + `scripts/evaluate.py`
  on both sub-periods with the shelf-not-spike rule, not as a new signal. `data/options/iv_regime.parquet`
  already covers 2017-2026; the daily champion's sample starts 2012, so the pre-2017 years are
  ungated and the study must say what it does with them rather than silently dropping them
  (Theta answers 403 before 2016 and 472 for 2016 greeks on this account's plan).
- **O-1 DONE 2026-09-10 (see journal): implied vol forecasts the day this sleeve is paid for and
  the forecast is worth nothing; the payoff is in the volatility *surprise*. Refused, nothing
  shipped.** Built `scripts/iv_regime.py` (Theta EOD greeks -> `data/options/iv_regime.parquet`,
  2,383 days 2017-01-03..2026-09-09: front-weekly ATM IV, 25-delta skew, 1w/1m term ratio; 491
  expirations cached under `data/options/raw/`, resumable, `--rebuild` free), `scripts/sweep_o1.py`
  (partitions A-10's cached 2,686-session series by a strictly prior-day gate, so every cell is a
  partition of one fixed sample rather than a new fit) and `iv_gate` on the ORB module, default
  off, failing closed on days the store does not cover. **corr(prior-day ATM IV, today's universe
  range) = +0.598 at t = +36.4** and **corr(realized range, ORB P&L) = +0.260 at t = +13.95**, but
  **corr(IV, P&L) = -0.030 at t = -1.46**; `term_ratio` +20.9 / -0.77 and `skew25_1w` +17.0 /
  **-2.81** (the only |t| > 2 against P&L, wrong sign). Range split into forecast and surprise:
  forecast -0.030 / -0.016 / -0.058, **surprise +0.351 / +0.292 / +0.299 at t = +18.3 / +14.3 /
  +15.3**, positive at t > 7 in nine of nine feature-regime cells. **All six gate cells fail 0/3
  regimes**; best ON side `term_ratio low` **+$43/day at t = +0.13**; the largest separation
  (Welch 2.26 in 2016-2019) inverts in 2024-2026. Replay of 2026-09-08 with the deployed config
  reproduced A-10 exactly. **Do not re-open this as a threshold, feature or horizon question** -
  the negative is that the payoff regressor is a surprise, so no forecast of any quality can reach
  it; the surviving residual is the size scaler now carried as O-1b. Kept for the record, the
  original item: A-10 measured the
  only mechanism this sleeve has that survives a 2,686-session sample: daily P&L correlates
  **+0.202 with the universe's mean daily range at t = +10.70**, positive in all three regimes
  separately. The level is negative everywhere, so the question is no longer "how big" but
  "when": is there a causal, known-at-entry regime signal that separates the range days the book
  earns on from the ones it pays on? A-9 proved the *opening range* is not it (the stop is the
  range midpoint, so width scales win and loss together). Options-implied volatility is the
  untried candidate and it is knowable before the open. Build `data/options/iv_regime.parquet`
  from `scripts/theta_data.py`: SPY ATM IV (nearest weekly), 25-delta put/call skew and the IV
  term ratio (1w/1m) per day and per 30-minute bucket, back to 2012. Gate ORB on it (trade only
  when IV is above/below its 60-day median, and test both signs) and judge it on the **Alpaca
  store with `scripts/sweep_a10.py`'s three regimes**, not on the 260-session IBKR window - that
  window is what produced every A-track false positive. Causal only: the bucket before the
  decision bar. A gate that does not reach t > 2 in at least two regimes is refused. Secondary
  use, carried over from the original O-1 statement and not to be done before the gate: the same
  features as a **size scaler for the daily champion**. Live note: the IV store is EOD, so a
  deployed gate needs the launcher to refresh it before the open - keep `iv_gate` defaulted off
  until a study justifies it. **Ordering (daily review 2026-09-10): A-5 part 2 runs first each
  day** - it is a ~1 minute job after the close and it is the only measurement that can move the
  cost constant every other A-track number depends on - **then O-1 takes the rest of the
  iteration.**
- **A-10 DONE 2026-09-10 (see journal): the sleeve is significantly negative on 2,686 sessions;
  the late-day fade is dropped.** Mix -$697/day at t = -3.01; regimes -$579/-2.42, -$1,127/-2.92,
  -$231/-0.37; ORB alone -$289/-1.17; late fade alone **-$468/-7.38**, negative in every regime
  and on the fitted window. The only profitable window in eleven years is the 261 sessions the
  parameters were chosen on (+$302/day, t = +0.32). Shipped `alloc.late_momo` 1.0 -> 0.0 after a
  passed replay; `equity_frac` held at 0.5. Also shipped the prerequisite cost fix (`--splits`,
  `share_scale()`, scaled `commission()`, whole-share floor at the real price) with an
  IBKR-store regression that reproduces A-5's control to the digit. **Do not re-open this as a
  parameter question** - the negative is about the level of the whole sleeve on unseen data.
  Kept for the record, the original item: A-4 proved the IBKR store
  (260 sessions) cannot resolve the deployed mix's edge (t = +0.61, ~2,000 sessions needed).
  `scripts/alpaca_data.py` now pulls consolidated 1-minute bars for any US symbol back to
  2016, free. Fetch the 16-name universe from 2016 (`--start 2016-01-01`, ~10 minutes), then
  re-run the deployed mix and each sub-strategy with `INTRADAY_DATA_DIR=data/minute_alpaca`
  and a 3-way split (2016-2019 / 2020-2023 / 2024-2026). Report t-stats per regime and the
  range-correlation from A-4. If the mix is not positive in at least two of three regimes at
  t > 2, cut its `gross` in `live/intraday_config.json` to 0.75 and say so in the journal:
  the owner asked for volatility, but not for noise dressed as edge. Also widen the universe
  test: the 50 megacaps from D-1 are now fetchable at minute resolution.
- **O-2 DONE 2026-09-10 (see journal): the SPY 0DTE credit spread has a real, calibrated gross
  edge and it is still refused - at the quote it loses in 8 of 11 years, and the version that wins
  needs a settlement convention the data cannot price. Nothing shipped.** Research needed no owner
  action: permission blocks deployment, not measurement. Built `scripts/odte_data.py` (1,884
  expirations 2016-01-08..2026-09-10, 5-minute bid/ask both rights, +/-30 strikes, ~17.8M rows),
  `scripts/sweep_o2.py` and `scripts/_o2_confirm.py`; 16 ledger rows under `options/odte_put_spread`.
  **The instrument was proved before its verdict**: strike selection reads the risk-neutral prob-ITM
  off the chain's own slope (`dP/dK`, no vol model, no external data) and realized breach tracks the
  quoted probability at every delta on both rights while sitting **below** it at **z = -2.7 to -3.8
  in six of six cells** - the variance risk premium, measured. **Stage 1 (36 pre-registered cells,
  closed at the quote at 15:50): 0 of 36 pass.** As % of the position's own max loss per session:
  gross **+0.783**, quoted spread **-1.363**, commission **-0.950**, net **-1.530**; the mid edge is
  **a third** of the cost of harvesting it and on a $355 risk unit the commission alone exceeds the
  gross. Cheapest possible version (72 cells) tops out at **+0.30% at t = +0.94, at zero commission**.
  **Stage 2 is the whole result**: letting an untouched position expire instead of buying it back
  flips the sign to **+0.767% at t = +3.05, 10 of 11 years positive**, with entry time a monotone
  shelf (09:35 +0.09 / 12:00 +0.685 / 14:30 +0.907 / 15:30 +0.684, t rising 0.19 -> 5.20) - while the
  same cells closed at the quote earn **-0.282% at t = -1.16**. **The exit assumption is what fails**:
  SPY settles on the official 16:00 print and is exercisable against until 17:30 ET, so requiring the
  close to clear the short strike by a buffer walks the result +0.767 (2 regimes) -> +0.583 (1) ->
  **+0.445 at t = 1.78 and 0 regimes at a 0.10%-of-spot buffer** -> +0.202 at 0.20%. **The median
  session closes 0.28% of spot from the short strike** (p25 0.14%, p10 0.06%, p5 0.03%) and 37.4%
  close within 0.2%, so the edge lives in the last few cents at the bell. **On the mandate**: the
  best cell earns +0.767% per unit of equity at risk, so 3%/day needs **3.9x equity at risk** against
  a defined-risk ceiling of 1.0x, where the worst session is **-105%**; at a survivable 0.25x the
  ledger row is CAR 21.5% at a **60.6% drawdown**. **Do not re-open as a delta, width, entry-time,
  structure or stop question** - the grid spans all five and the negative is decided one level above
  them. What would re-open it is **different data**: OPRA quotes through the close plus a measured
  settlement print, which is an owner purchase (see `BLOCKERS.md`), not a loop decision.
- **A-11 DONE 2026-09-11 (see journal): the impossible fills are real, four times larger than the
  IBKR window showed, and they are not load-bearing - and the executable half of the universe is
  the half that never made money. Refused, nothing shipped, `part_cap` stays 0.** Diagnostic over
  90,441 fills / 2,686 Alpaca sessions: notional-weighted **p50 1.46% / p75 4.71% / p90 18.80% /
  p99 950% / max 38,759%** of the fill minute's volume (A-5 on 260 IBKR sessions: 1.03 / 5.55 /
  26.1 / 199), with **24.1% of notional above 5% of its minute, 9.7% above 20%, 4.1% above 100%**;
  the store is split-adjusted on price *and* volume, verified against the raw tape, so the ratios
  are real. The cap cells (clip to a share of the trailing-median volume of the fill minute,
  knowable at decision time, worked over following bars) give **-331 / -336 / -367 / -430 $/day**
  at paired t **-0.25 / -1.24 / -2.40** against costs/day **907 / 917 / 941 / 969**: at 0.10 the
  backtester clips 213,338 orders refusing a cumulative $4.78M/day of intended notional (vs
  $3.59M/day executed) and the book moves -$5/day, **+$10/day of which is the slicing commission,
  so implied Δgross is +$5**. **Outcome (c) of the pre-registered rule: the defect is real and
  immaterial** - the fills nobody could get were not the ones making the money, so every A-track
  number stands and switching the cap on buys nothing at 3x the turnover. **The finding is the
  universe split**: liquid 8 (8.8% of notional above 5% of the minute) **-$195/day at t = -1.89**,
  the sharpest negative this sleeve has produced; illiquid 8 (45.8%) -$164 at -0.83; paired
  difference -$31/day at t -0.18, corr 0.498. **On the 261-session fitted window the liquid half
  earns -$102/day and the illiquid half +$361/day**, so the sleeve's only positive evidence in
  eleven years lives entirely in the names whose fills cannot be trusted. **Do not re-open as a
  cap-level, helper or universe question** - the mechanism was measured on 90,441 fills and both
  directions are closed. 18 ledger rows under `intraday/active`; only `scripts/sweep_a11.py`
  changed (a `--label` flag). Rule (a) owed no replay (no file the trader loads moved); run anyway
  with the deployed config: 34 trades, 368 decisions, flat, P&L -2,302 on 500k.
  **Implementation status as of 2026-09-10 (A-5 part 2)**: an interrupted session left the whole
  thing in the tree, and it is now committed - `intraday_common.volume_limits()` (trailing median
  volume per session and minute-of-day, strictly prior sessions, so it is causal),
  `part_cap` in `intraday_backtest.py`'s `RISK` defaulted **0.0 = off** with the clip applied to
  what executes rather than to the no-trade band, and `scripts/sweep_a11.py`. **The default is
  proved bit-for-bit inert**: the A-5 part 2 control run went through that path and reproduced
  A-5's recorded ledger row to every digit. **No sweep has been run**, so the item itself is
  untouched; what remains is exactly the study below, and it must now be judged against the
  corrected commission model (breakeven 2.52 bps, control $557/day), not A-5's pre-fix numbers.
  Still a real cost-model defect - over 12,743 fills the order is median 1.03%, p90 5.55%, p99
  26.1% and at worst 199% of the minute's volume, concentrated in SMCI/SOXS/COIN/MSTR - but A-10
  measured the sleeve as negative *before* removing any impossible fill, so a participation cap
  can now only make a losing book smaller. Take it when a signal tests positive on the Alpaca
  regimes, and take it before any such signal is sized. Original statement: The one thing A-5
  found that the bars *prove* is wrong rather than merely leave uncertain. Over the deployed mix's
  12,743 fills on the 260-session store, the order is **median 1.03%, p75 2.43%, p90 5.55%, p99
  26.1% and at worst 199%** of the volume of the minute it fills in, and the tail is not random:
  **SMCI (median 5.5% / p90 17.3%), SOXS (2.8% / 18.7%), COIN (3.1% / 10.6%) and MSTR (2.2% /
  6.1%) carry 30% of the sleeve's traded notional**, against 0.2-0.9% for the megacaps. A fill of
  a fifth of a minute's volume at that minute's open with zero impact is not a fill, and 199% is
  not a trade at all - so an unknown part of the sleeve's $1,430/day gross is booked at prices that
  never existed. **This is a cost-model defect, not a lever**, so A-4's power argument (a real
  effect must be visible on 260 sessions) does not excuse leaving it: the question is not whether
  a cap earns more, it is what the sleeve earns when the impossible fills are removed.
  Implementation: a participation cap in `targets_to_orders` - clip `|delta|` to
  `part_cap * <trailing median volume of that minute-of-day for that symbol> ` (trailing, so it
  stays causal; the backtester and `scripts/intraday_trader.py` must use the same helper in
  `scripts/intraday_common.py` or they will drift). Sweep `part_cap` at 0.02 / 0.05 / 0.10 / off
  on both halves with `scripts/sweep_a5.py`'s cached control as the baseline. Expect the sleeve to
  get *smaller*, not better - the honest outcome is a lower gross with the same Sharpe, which
  would mean the shipped numbers were inflated by fills that cannot happen. Because it changes
  sizing in shared code it needs a replay before any config write (rule a) and OOS evidence
  before `live/intraday_config.json` moves (rule c). A full-store run is ~17 minutes; use the
  `results/a5/control*` cache and `--workers`.
- **A-5 Execution quality from the live log. Part 1 DONE 2026-09-10 (see journal); the live half
  is still open and is a standing per-session job.** What part 1 settled: the sleeve's **breakeven
  slippage is 2.62-2.64 bps against a shipped 1.5**, P&L is linear in the constant to $73/day
  (0 bps -> $1,671/day / CAR 41.9% / Sharpe 1.51; 1.5 -> $610 / 15.3% / 0.69; 3.0 -> -$231 /
  -5.8% / -0.11), turnover is **$5.46M/day on a $1M book** so one bp is $546/day, and **the
  holdout breaks even at -0.02 bps** - gross P&L before any slippage on the 77 unseen sessions is
  -$11/day, which reframes A-4's -$813/day as no gross edge rather than a weaker regime. Bars
  cannot pin the constant: Roll and Corwin-Schultz give a notional-weighted half-spread of 2.65
  bps but `corr(estimate, 1-min return std) = +0.906` and CS/vol is 0.32-0.65, so the estimator is
  volatility; the tick floor is 0.36, leaving **[0.36, 2.65] against a 2.62 breakeven**. The
  fill convention hides nothing: decision close -> next bar open is **-0.12 bps (se 0.04)**.
  **What remains is the measurement itself**, and the tool is built and self-tested:
  `python scripts/slippage_report.py` prices every live fill against the same next-bar open the
  backtester assumes (positive = worse than the backtest), pooling notional-weighted mean, its
  standard error, per-symbol and per-side breakdowns, fill rate and latency, across every
  `live/log/intraday-<date>.jsonl` on disk. Run it after **every** paper close and report the
  running mean and standard error; the first session with fills is 2026-09-10 (the only earlier
  log is a hand-started `--dry-run` with zero orders). Move `SLIPPAGE_BPS` only when
  |measured - 1.5| exceeds two standard errors, with a replay and a journal entry (rule a) - the
  script prints that test and refuses to write the constant itself.
- **A-9 DONE 2026-09-10 (see journal): the day's range pays, but only the part that is not
  knowable at entry; nothing shipped.** ORB's daily P&L correlates +0.568 (t = +11.09) with the
  realized full-day range and +0.665 (t = +14.29) with the part of it left after regressing out
  the opening range - both stable across halves - but only **+0.080 (t = +1.28)** with the
  opening range itself, and -0.009 on the holdout, despite the opening range predicting the
  day's range at corr +0.626. **Mechanical reason: ORB's stop is the range midpoint, so the
  width is the risk unit** - a wide opening scales win and loss together, and the payoff is in
  the range the day adds after entry. Attribution over 3,731 traded symbol-sessions agrees
  (corr +0.029 raw, +0.036 within-symbol, splitting TUNE +0.052 / HOLD -0.022). Shipped to the
  tree defaulted off: `range_atr_min` / `range_atr_max` on the ORB module (snapshotting ATR14
  when the range closes, so a session's gate is one number per symbol), `scripts/sweep_a9.py`
  (attribution + two grids), and an opt-in `collect_trades` in `scripts/intraday_backtest.py`.
  **The grid is the A-track's sharpest overfitting demonstration**: every wide-opening cell wins
  the tuning window and loses the holdout, every narrow-opening cell does the reverse, `min 3.6`
  scores TUNE Sharpe 2.17 against HOLD -1.19 and `max 3.6` scores HOLD 1.46 against TUNE -1.27,
  and no cell reaches |t| = 1.6 paired against the control on 260 sessions. Replay of 2026-09-08
  passed (46 trades, flat at close). **Do not re-open this as a "better threshold" question** -
  the negative is about what is available at entry, not about where the cut goes.
- **A-4 DONE 2026-09-09 (see journal): the store is 260 sessions and the sleeve's return is not
  distinguishable from zero; nothing shipped.** Store extended to 2025-08-26..2026-09-08 and a
  truncation bug fixed - requests ended at the wall-clock time of the run, so IBKR truncated the
  newest session of every window into a partial day that strategies then traded as a full one;
  `snap_after_close`, `--repair` and `truncated_sessions()` in `scripts/intraday_data.py` fix it,
  all 16 symbols now hold 261 sessions with only the two real NYSE half days short, and A-7's
  control reproduces on the repaired bars to a tenth of a point. New `scripts/sweep_a4.py`.
  Holdout (77 sessions never seen by any A-track parameter) vs tuning window (183):
  mix **-19.1% / -0.73 / -$813 day** vs **+33.8% / 1.27 / +$1,289 day**, orb only -5.2 / -0.08 /
  -$209 vs 24.5 / 1.00 / +$943, late fade only -13.5 / -2.46 / -$563 vs 6.2 / 1.09 / +$243.
  **None of it is measurable**: Welch t between halves -0.96 / -0.51 / -1.65, and pooled over
  260 sessions the mix is $610/day, std $16,222, **CAR 15.3%, Sharpe 0.69, t = +0.61, 95% CI on
  the year [-$354k, +$671k]** around $158.6k. **The power calculation is the durable result:
  ~8.4 years / 2,120 sessions are needed to reject zero at 2 sigma**, so no reachable sample validates this
  sleeve and no A-track lever hunt on this harness ever could. The late fade is worth **$1,099
  over 260 sessions** and +$65/day marginal (t = +0.27). Refused to drop it: it improves the
  holdout but costs $16.8k over the full store, which is not rule (c)'s OOS improvement.
  Successor is A-9; the owner question is in `BLOCKERS.md`.
- **A-7 DONE 2026-09-09 (see journal): the framework risk limits are a tail dial with no
  measurable price; nothing shipped.** The daily loss limit's tail response is monotone and
  mechanical - worst day -20.5k (1.5%), -25.8k (2.0%), -30.3k (2.5%, shipped), -37.2k (3.0%),
  -42.5k (3.5%), -57.0k (off) - with a 0.15-0.38 point overshoot past nominal, since the breach
  is marked to close and the flatten pays spread. Its return response is scatter: total P&L
  200.5k / 221.2k / 243.1k across 2.0% / 2.5% / 1.5%, and **paired on 183 daily returns every
  cell in the sweep scores |t| <= 1.06**. **Stopping early is free** - on halted sessions the
  halted book beat the limit-off run on the same dates at every limit except 2.0% ($453/halt
  saved at 1.5%, which fires on 22% of sessions; $8,497/halt at 3.0%) - so the stated worry that
  a frequent limit forfeits the session's edge is measured and refused. `PER_SYMBOL_HARD_CAP`
  is **inert**: 0.12/0.15/0.20/0.25 are bit-identical, the mix never asks for more than ~0.12 of
  equity in one name, and below 0.12 the cap is a size dial (0.10 is a spike on IS Sharpe with
  both neighbours losing, refused). Gross saturates at the deployed 1.5 and 2.0 is an
  owner-level risk decision. Nothing changed in `scripts/intraday_common.py` or
  `live/intraday_config.json`, so the trader is byte-identical and no replay was owed. Shipped
  instead: a backtest-only `--risk` override in `scripts/intraday_backtest.py` (`RISK` dict,
  defaults exactly the shipped constants, recorded in the ledger when non-default) plus
  `scripts/sweep_a7.py`, and `Worst Day` / `Loss Limit Days` are now ledger columns. The priced
  menu for the loss limit is a one-line question in `BLOCKERS.md`.
- **A-1 DONE 2026-09-09 (see journal): the VWAP fade is repairable but not additive; retired
  from the mix, alloc stays 0, `live/intraday_config.json` untouched.** Of the five levers,
  only the **session-trend filter** is a mechanism: taking only the fades that lean with the
  day's direction moves the module from IS -56.0 / OOS -10.1 to -11.9 / +16.9 at a third of
  the turnover, and **inverting the filter fails as predicted** (-46.3 / -5.5), so the fade was
  losing by fighting trend days. Min hold, a midday blackout and a 5-minute cadence only shrink
  the position (all still worse than -50 IS); range expansion leaves 0.8 trades/day and is an
  empty sample. Stacking levers walks a frontier rather than climbing: the only cell positive
  in both halves is trend 20 bps + band 70/15 + hold 20 at **+0.8 / +11.3**, and +0.8% CAR at
  Sharpe 0.13 on 124 sessions is indistinguishable from zero. **The sleeve decides and says
  no**: at alloc 0.25/0.5/1.0 across three fade cells, IS CAR falls monotonically
  (24.21 -> 23.48 -> 22.25 -> 20.74) and IS drawdown widens 1.2-3.9 points while OOS rises to a
  peak near 0.5, so total P&L over all 183 sessions is $221.2k deployed against $216.9-225.2k
  for the fade cells - a +/-2% wash bought with 22-34% more trades per day. Refused on that.
  The module and all five levers stay in the tree defaulted off, control reproducing A-6 to the
  digit; revisit only when A-5 replaces estimated slippage with measured.
- **A-2 DONE 2026-09-09 (see journal): shipped a 4x ATR14 disaster backstop on ORB; the
  stated hypothesis was refused.** No variant cuts the tail while keeping the return - the
  response to stop distance is monotone and *rotates* return from the IS half to the OOS half
  (midpoint 35.7/10.7, +4x ATR 31.4/19.3, +3x 21.5/26.5, pure 1.5x ATR -12.3/43.1), with the
  two-half mean roughly conserved. The tail only comes off at a stop tight enough to zero the
  in-sample return: pure 1.0x ATR takes the worst day -33.9k -> -21.4k and the loss-limit days
  to 0/0 at IS CAR -0.3%. Scale-out at 1.5R (24.8/8.0), a 30-minute range (15.9/-1.1) and a
  1.6x volume filter (15.0/-9.8) all lose in both halves and are not carried forward. Shipped
  `disaster_atr=4.0` on the sleeve mix (IS 27.2/1.10 -> 24.2/1.01, OOS 36.2/1.24 -> 55.3/1.73,
  worst day flat, one fewer loss-limit day, $201k -> $221k over 183 sessions) as a shelf point
  - 8x is indistinguishable from off, 6x/4x/3x walk the frontier smoothly. Follow-up is A-7.
- **A-6 DONE 2026-09-09 (see journal): deployed mix re-derived on 9 months = ORB 1.0 + late
  fade 1.0, no VWAP fade.** Kept for the record:
  A-0 found the edge in the *inverses*: late-day fade (robust in both halves) and VWAP fade
  (huge OOS, negative on the longer IS window, i.e. a regime bet at half size). Re-run
  `scripts/intraday_backtest.py` for orb, vwap_trend(direction -1, band 30/8, mom 15),
  late_momo(direction -1), gap_fade and the `active` mix with `--start <first session>
  --split <2/3 point>`; keep only strategies positive after costs in both halves; if VWAP fade
  is negative on the long window, set its alloc to 0.25 or 0. Record the mix change in the
  journal and `live/intraday_config.json`. Also verify the store has no dropped first-of-window
  sessions (compare session count to the daily calendar; `intraday_data.py` now overlaps
  windows, re-run `--months 9 --force` if gaps exist).
- **A-8 The one ORB lever A-2 did not spend: the entry window.** `entry_after` /
  `entry_before` / `time_stop` were left at 15 / 150 / 240 throughout A-2, and the frontier it
  found says the shipped edge is concentrated in *which* breakouts are taken, not in how they
  are stopped. Sweep the entry window and the time stop, and check the result separately on
  the leveraged ETFs (SOXL/SOXS) where the range is wider, since the backstop now scales with
  ATR and those names are where it binds most. **Parked, and A-4 says park it harder**: the
  extra 77 sessions did not buy the power A-7 was missing - at Sharpe 0.62 the sleeve needs
  ~2,600 sessions to prove *itself*, so an entry-window sweep would again produce a table of
  statistically identical cells. Take it only after A-9, and only if A-9 finds an effect large
  enough to be visible on 260 sessions.
- **A-3 Deployed mix.** Set `alloc` and `gross` in `live/intraday_config.json` from OOS
  evidence: strategies with negative OOS after costs get alloc 0 until fixed. Target gross
  1.0-1.5x of NAV so daily P&L swings are in the tens of thousands on the $1M account, with the
  framework's 2.5% daily loss limit as the floor.
- **P-1 DONE 2026-09-10 (O-1 iteration, background): the alert path can no longer fail silently.**
  `intraday_common.notify()` and `paper_trade.notify()` now always append the alert to
  **`live/log/alerts-<date>.jsonl`** - `{ts, event: "alert", source, text, delivered, error}` -
  and only then attempt the chat push, which is allowed to fail. `delivered: false` with the
  reason is the durable trace that was missing on 2026-09-09. **The daily review must read that
  file**; any `"delivered": false` line is an alert nobody received. No credentials were touched:
  the chat channel itself is still unconfigured (`live/alerts.json` does not currently exist on
  this machine, so both notify paths were silent no-ops, not just the Telegram one), and making it
  work remains an owner item. Verified by self-test from both modules and by re-running
  `compare_orders.py` after the `paper_trade.py` edit (3,689/3,689 dates, PASS). Kept for the
  record, the original item: `live/log/2026-09-09.jsonl` carries
  `notify_failed: Telegram bot token missing. Set TELEGRAM_BOT_TOKEN or channels.telegram.botToken`
  from the 2026-09-09 paper session, so `live/alerts.json`'s phone alerts never leave the machine
  and a live failure - a rejected order, a halted sleeve, a launcher preflight refusal - is visible
  only if someone reads the logs. Either configure the channel the loop is allowed to use or
  degrade the alert to something that cannot silently fail (append to a file the daily review
  reads, and surface it in the report). **Do not touch credentials**: if the fix needs a token,
  it is an owner item for `BLOCKERS.md`, not a loop item.
- **D-2b Extend the LEAN minute store past SPY.** SPY is done (see Done). QQQ, IWM, TQQQ and
  SQQQ are one command each - `py -3.11 scripts/fetch_minute.py --symbols QQQ --start 2020-01-01` -
  and the script is resumable by month, so an interrupted run is restarted by re-running it.
  Budget ~40 minutes of wall clock per symbol-decade; IBKR serves ~260-790 bars/s and that is
  the binding constraint, not pacing. Run it in the background of another iteration rather
  than spending a whole iteration on it.
- **S-2 DONE 2026-09-11 (see journal): the index-ETF opening-range breakout carries +1.09 bps of
  directional edge at most against a 3.65 bps round trip, and most of its apparent gross belongs
  to the stop, not the signal. Refused, nothing shipped, and the LEAN build was not owed.**
  Fetched SPY/QQQ/IWM from Alpaca SIP (2016-01-04..2026-09-10, ~1.046M bars each; the store is
  now 63 symbols) and built `scripts/sweep_s2.py`. **Stage 1, 2,687 sessions, 16 breakout cells
  and their 16 fade controls, nothing fitted: 0 of 16 pass** - best on net `orb15 mid e120`,
  gross +2.11 bps/trip, cost 3.65, net **-1.54**, -$113/day at t -1.64. **The keeper is the
  decomposition**: the fade earns positive gross in **14 of 16 cells**, so
  `(brk + fade)/2` - positive in **all sixteen**, +0.33 to +1.43 bps - is stop convexity that a
  coin flip collects, and only `(brk - fade)/2` belongs to the signal: **max +1.09 bps (0.30x
  cost), negative in 6 of 16 cells.** Any ORB study that reports gross without its own fade
  control is reporting this artifact. TQQQ (the leveraged read, 8 cells): cost **4.85 bps**, 0 of
  8, and in its best cell breakout **+$33.78/day** against fade **+$33.79** - identical, i.e. no
  direction at all - while its widest cell runs +$225 / +$95 / -$396 across the three regimes.
  **Stage 2**, the shipped ORB module through the deployed framework (`--symbols SPY QQQ IWM`,
  0.36x gross on $1M, 3 ledger rows): **-$186 / -$211 / -$39 per day, 0 of 3 regimes**, i.e.
  **+$11/day of gross over eleven years against $171/day of costs**, with gross negative in two
  regimes separately. **Do not re-open as a range-length, stop, entry-window, symbol or
  resolution question** - the grid spans the first four and the negative is on gross, in both
  signs, through two independent instruments. The one thing not tested and not on this backlog is
  a breakout held **longer than a session**; everything here pays a round trip every day. Stage
  1's only optimism (closing an untouched trip at the last minute bar instead of the auction)
  favours the strategy, so modelling the 16:00 auction in LEAN - what this item asked for - could
  only make it worse, which is why no LEAN run was owed. On the mandate: daily P&L sd is
  0.13-0.20% of equity at 0.36x gross, ~0.5% at 1x, alongside L-1's 0.49% and X-1's 0.27%. Kept
  for the record, the original item: intraday on SPY first, then QQQ/IWM as D-2b delivers them;
  enter on a break of the first 15-30 minute range with ATR stops, scale out into strength, flat
  at close; judge with the same IS/OOS split and the promotion rules, recording correlation with
  the champion's daily returns as a first-class metric; **model the 16:00 closing auction**,
  because D-2 measured the daily close diverging from the last 1-minute bar by up to ~1% on
  violent days.
- **S-5 Allocator.** Route capital across S-1, S-2 and any future sleeve by trailing 60-day
  Sharpe with a floor per sleeve. Scaffold now against the S-1 and S-3 return series.
- **I-1 IBKR paper runner: DONE 2026-09-09, paper trading approved and scheduled.**
  `scripts/paper_trade.py` (ib_async) already exists and passes `--mock --dry-run` against
  `algorithms/s1_momo/signals.py`: it introspects the signal signature, feeds back
  `diagnostics["state"]` and an equity curve, sizes whole shares, logs to `live/log/`, and
  refuses to trade without `live/APPROVED_PAPER.md`, a `DU` account, or with `live/HALT`
  present. `scripts/install_paper_task.ps1` schedules 15:45 ET weekdays. Do not rewrite it.
  Remaining work once the 10141 disclaimer is accepted, in order: `--check`, then a
  `--dry-run` on the real account, then `py -3.11 scripts/compare_orders.py`. **That last
  step is now automated and already passing** - it was the manual "compare the runner's order
  list with what the backtest would have done" item, and building it on 2026-09-09 caught the
  `MIN_NOTIONAL` band bug that would have doubled the paper account's order count (see the
  journal). It needs no IB connection, so re-run it after any change to `plan_orders`,
  `submit_targets` or `min_order_value`; exit 1 means the runner and the backtest have
  drifted apart and the deploy should stop. S-6 did not change netting or staging -
  `plan_orders()` already nets against current positions - but it did add the
  `MAX_MARGIN_USED = 1.0` backstop, and the mock plan is now a 1.5x gross book, so the
  paper account must have margin enabled or the first real order will be rejected.
  Re-verified `--mock --dry-run` against the **S-12** champion on 2026-09-09 (1.23x gross,
  margin 0.75, XLE/XLK/TQQQ, with the new `alloc_vols` tilt visible in the diagnostics); the
  pre-deploy comparison is against `OrderListHash 5246804e17a67af90028ffceead7d3b3`.
- **D-2 Intraday data (blocks S-2).** `fetch_data.py` writes daily bars only; Yahoo caps
  1-minute history at ~30 days, which is useless for backtesting. Once IB Gateway is logged
  in, pull minute bars with `ib_async` `reqHistoricalData` (1-day chunks, respect pacing
  limits) for SPY/QQQ/IWM/TQQQ/SQQQ first. LEAN minute format:
  `equity/usa/minute/<symbol>/<yyyyMMdd>_trade.zip` holding
  `<yyyyMMdd>_<symbol>_minute_trade.csv` with rows `<ms since midnight ET>,o,h,l,c,v`,
  prices scaled by 10000. Reuse the writer/validator structure already in `fetch_data.py`.
- **S-2 Opening-range breakout.** Intraday on SPY/QQQ/IWM (futures later). Enter on a
  break of the first 15-30 minute range with ATR stops, scale out into strength, flat at
  close. Hypothesis: high-frequency small edges compound into volatile but positive equity.
  **Blocked on D-2**, which is blocked on the IB Gateway login.
- **S-5 Allocator.** Route capital across S-1, S-2 and any future sleeve by trailing 60-day
  Sharpe with a floor per sleeve. Still worth building - S-3 proved the market-neutral
  construction really does deliver orthogonality (corr -0.03 with the champion) - but it
  has nothing to allocate *to* until a second sleeve has a positive expected return, so it
  sits behind S-2. **Its plumbing is the designated offline work** if the API stays blocked:
  it can be scaffolded and tested against the existing S-1 and S-3 return series without
  touching the champion.
- **E-2b Generalize `sweep_s1.py` off S-1.** Explicitly deferred when E-2 shipped; the second
  designated offline item. Needed before any second sleeve can be swept the same way.

## Done

- **D-2 Intraday data, LEAN minute store. SPY DONE 2026-09-09**, acceptance run
  `20260909T160005Z` (`algorithms/d2_minute_smoke`, tagged not promotable; no champion change).
  `scripts/fetch_minute.py`: IBKR `reqHistoricalData` 1-min / TRADES / `useRTH=True` -> LEAN
  `equity/usa/minute/<sym>/<yyyyMMdd>_trade.zip`, raw prices with dividends left in the D-1
  factor files, sliding-window pacer for the 60-per-10-minutes rule, resumable by month chunk,
  `clientId` 31. **SPY 2020-01-02 .. 2026-09-08: 1,679 sessions, 652,650 bars, 0 missing
  against the daily calendar, 0 truncated, 0 clamped, 14 MB.** The acceptance test runs
  *through LEAN* and asserts seven properties - all PASS, and LEAN's bar count equals the
  writer's exactly - because D-1's worst bug was a file that passed structural validation and
  made LEAN return zero bars with no error; only asking the engine catches that class.
  **The bug found: `durationStr="1 M"` ending on the month's last day silently drops the first
  session of every month**, because IBKR measures the window back from `endDateTime` and lands
  after that session's close. ~5% of the sample, invisible - every surviving session is a
  complete 390 bars. Chunks are `5 W` with the overlap filtered back to the chunk.
  **Two durable facts.** (1) Minute and daily closes agree to a median 0.007%, but the six
  sessions over 0.2% are all violent days (2020-03-13/17/18/19/23/24, 2025-04-03/09): the
  daily close is the **auction print**, the last minute bar is not, so an intraday sleeve that
  flattens at the close must model the 16:00 auction or book up to ~1% of imaginary P&L on
  exactly its best days. (2) IBKR serves ~260-790 bars/s, so a symbol-decade is ~40 minutes
  and the five-symbol set is a multi-hour job - hence the resumability, and hence only SPY in
  one iteration. Remainder is D-2b. Complements, does not duplicate, `scripts/intraday_data.py`
  (parquet, clientId 61) which feeds the non-LEAN A-track harness.
- **S-13 The execution no-trade band. Closed negatively 2026-09-09**, runs
  `20260909T043527Z` (0.02), `045041Z` (0.015), `044105Z` (0.03), `044610Z` (0.05),
  `045910Z` (0.08), sub-periods `20260909T045454Z` / `045705Z`; the champion run
  `20260909T042431Z` is the 0.01 cell, so no control was needed and **no code changed** -
  `min_order_value` was already wired to `S1_MIN_ORDER_VALUE`. Full period: 0.01 24.40%/0.921/
  25.1%/4,735 orders, 0.015 24.35%/0.919/26.9%/3,887, 0.02 24.54%/0.927/25.2%/3,355,
  0.03 24.34%/0.917/25.5%/2,737, 0.05 23.92%/0.900/29.2%/2,112, 0.08 24.47%/0.920/25.4%/1,727.
  **Non-monotone and flat** - no trend in either direction across a factor of eight in the
  band, and the one deviant cell (0.05, drawdown 29.2%, four points wide of every neighbour)
  deviates in a metric no mechanism predicts, which is what path dependence looks like when a
  threshold moves *which day* a rebalance fires. 0.02 passes `evaluate.py` outright (and its
  sub-periods agree in sign: IS 19.32%/0.891/25.2% vs 19.18%/0.884/25.1%, OOS 30.98%/0.988/
  22.7% vs 30.86%/0.985/22.6%) and was **refused as a spike** - both neighbours lose to the
  champion, so there is no shelf and the +0.14 CAR sits inside the region's scatter. **The
  finding is the flatness**: ~3,000 of the champion's orders are return-neutral, worth only
  the $6.1k of commission the widest band saves in backtest, but worth that *plus* an
  unmodelled spread per order live. Filed as a live-execution question in `BLOCKERS.md`;
  the shipped default stays 0.01 precisely so the I-1 order list does not move.
- **S-12 Risk parity inside the top_n. PROMOTED 2026-09-09**, run `20260909T042431Z` (control
  `20260909T034600Z`, reproducing `ff4a7cbaaf6e36e58ace2b82ab216bdf`; window scan
  `20260909T034953Z` / `035356Z` / `035803Z` / `040157Z` / `040554Z` / `041013Z`; tilt-strength
  check `20260909T041912Z`; sub-periods `20260909T041413Z` / `041644Z`). Momentum still picks
  the three names; their share of the exposure budget is now `(1/sigma) ** alloc_vol_power` on
  the **unlevered** ranked series rather than 1/N, because equal weight equalizes notional and
  this sleeve spans 12% vol (GLD/TLT) to 30% (XLE/XLK). Shipped: `weight_mode="invvol"`,
  `alloc_vol_window=21`, `alloc_vol_power=1.0`; `S1_WEIGHT_MODE=equal` restores S-10.
  LEAN full period CAR 23.61% -> 24.40%, Sharpe 0.874 -> 0.921, drawdown 25.9% -> 25.1%,
  PSR 17.7% -> 23.0%; IS 19.18%/0.884/25.1% (beats 17.64%/0.801/25.9% on all three), OOS
  30.86%/0.985/22.6% (Sharpe ahead of 0.972, CAR 0.23 points behind). **Shelf in both
  dimensions**: windows 20/21/30 beat the champion on CAR, Sharpe and drawdown, 40/60 win on
  Sharpe and drawdown only, 10 loses; and the tilt is monotone in strength (power 0.5 gives
  24.10%/0.902, half the gain). 21 = one trading month is the a-priori point, 20 is the argmax.
  **The cost is turnover**: 2,573 -> 4,735 orders and $37.4k -> $45.7k of fees, because vol
  ratios drift and the book re-weights between rotations - so window 30 (4,102 orders) is the
  named fallback if commission ever rises. `weight_mode="rank"`, still never LEAN-tested, loses
  in the sweep (19.3%/0.93 against 21.2%/1.03) and was not carried forward.
- **S-11 The whipsaw. Closed negatively 2026-09-08**, runs `20260909T024906Z` (control,
  reproduces `OrderListHash ff4a7cbaaf6e36e58ace2b82ab216bdf`), `20260909T025256Z` /
  `025647Z` / `030039Z` (hysteresis 0.05/0.10/0.20 sigma), `20260909T030434Z` (min_hold=10),
  `20260909T030824Z` (rank_persist=2), `20260909T031243Z` and `20260909T032059Z` (the two
  size-spend frontier points), `20260909T031632Z` / `031842Z` (sub-periods). No promotion.
  All three levers shipped in `signals.py` defaulted off (`hysteresis`, `min_hold`,
  `rank_persist`; env `S1_HYSTERESIS`, `S1_MIN_HOLD`, `S1_RANK_PERSIST`), plus
  `sweep_s1.py --mode s11`. **The core finding is that the champion's rotation is not
  noise**: refusing a rank crossing removes return monotonically in the strength of the
  refusal (hysteresis 0.05 -> 0.20 sigma walks CAR 23.57% -> 22.34% and Sharpe 0.873 ->
  0.827), so the frontier slides along rather than moving up. It is however a *cheap* trade
  in drawdown: `min_hold=10` costs 0.45 points of CAR and buys 3.1 points of drawdown and
  $10k of fees; hysteresis 0.05 costs 0.04 points of CAR (a rounding error) for 1.3 points of
  drawdown, 373 fewer orders and $7.8k less commission, and its sub-periods put the whole
  gain in the IS half where S-10 diagnosed the whipsaw (IS 17.73%/0.806/24.6% beats the
  champion's 17.64%/0.801/25.9% on all three; OOS is a hair behind). Spending the headroom on
  size does not recover the return - `min_hold=10` + `margin_budget=0.85` reaches 25.07% CAR
  at a matched 25.7% drawdown but 0.861 Sharpe, refused by `evaluate.py` on the Sharpe rule
  and now a named question for the human in `BLOCKERS.md`. `rank_persist` is the one lever
  both harnesses reject outright: blocking an entry parks the book in cash and buys it back,
  so it *raises* turnover (2,727 orders, $46k fees against 2,573 and $37k). Implementation
  note for I-1: (a) and (b) persist `held`/`held_age` in the existing `state` dict the runner
  already round-trips; (c) is stateless by construction.
- **S-10 Skip-a-month momentum and horizon weighting. PROMOTED 2026-09-08**, run
  `20260909T013820Z` (control `20260909T005513Z`, sub-periods `20260909T013359Z` /
  `20260909T013608Z`, LEAN skip scan `20260909T0059-0122`). Two levers, both defaulted off,
  the control reproducing S-9's `OrderListHash b763e292cb0eb9a2c81af5739188d437`.
  **Horizon weighting lost everywhere** - every vector overweighting the long horizon costs
  2-3 points of CAR and widens drawdown, on the raw blend and after standardizing
  (`mom_weights` stays in `signals.py`, defaulted empty). **The skip won, but not at the
  textbook parameter**: the 12-2 month skip (20 sessions) loses (19.6% / 0.72), the shelf is
  at 3-10 sessions (23.0-23.6% CAR, 0.84-0.87 Sharpe), and it collapses at 2 and at 15+.
  Shipped: `mom_skip=5` (one trading week) on `mom_skip_min_lookback=120`, i.e. the 120- and
  252-day horizons only - applying it to the 20-day horizon as well costs 4.4 points of CAR,
  and confining it to 252 alone earns 23.3%, so the effect belongs to long-horizon momentum
  generally. LEAN full period: CAR 20.9% -> 23.6%, Sharpe 0.782 -> 0.874, drawdown 28.9% ->
  25.9%, orders 2,870 -> 2,573, PSR 10.1% -> 17.7%; IS 17.6%/0.80/25.9%, OOS 31.1%/0.97/21.5%,
  both ahead of S-9's 15.2%/0.70 and 28.0%/0.88. **The methodology finding matters as much as
  the result**: `sweep_s1.py` rejected this cell and inverted its drawdown ranking, so the two
  harnesses disagree in sign and LEAN decides. Also delivered the S-9(c) diagnostic that
  became S-11.
- **S-9 A second signal on the ETF sleeve. PROMOTED 2026-09-08**, run `20260908T235647Z`
  (control `20260908T234444Z`, sub-periods `20260908T235224Z` / `20260908T235437Z`). Both
  ideas S-7 named were tested and **both lost**: cross-sectional ranking against the sleeve
  median is a *looser* gate than the absolute floor at `top_n=3` of nine (17.9% CAR) and
  asking for real dispersion strands the book in cash through 2012-2019 (6.4% CAR, 49.2%
  drawdown); horizon agreement (`mom_confirm`) costs 6 points of CAR and 14 of drawdown at
  55% more turnover. Risk-adjusted momentum (`mom_score="riskadj"`) beats the champion only
  in a 15-30 day vol window, wins IS at one end and OOS at the other, and is not shipped.
  **What won was a fourth momentum horizon of 252 sessions**: LEAN CAR 18.1% -> 20.9%,
  Sharpe 0.693 -> 0.782, orders 3,410 -> 2,870, fees $38.6k -> $37.3k, drawdown 25.2% ->
  28.9%; IS 15.2%/0.70, OOS 28.0%/0.88, both ahead of the old champion's 13.5%/0.64 and
  23.8%/0.76. It is a **shelf, not a spike** - every fourth horizon from 220 to 300 beats
  the champion on CAR, Sharpe and drawdown, collapsing at 150 and 320 - and 252 is shipped
  as the a-priori one trading year rather than the 250 argmax. Also fixed a harness bug the
  scan exposed: a lookback longer than `history_bars` made `target_weights` hold cash for
  the whole sample and print a plausible 0.0% CAR, so `Params.__post_init__` now widens the
  window to `max(lookback) + 50`. Recalibration: the sweep understated LEAN drawdown by 7.8
  points on this configuration, against the +2 S-8 measured at the champion's size.
- **S-3 Cross-sectional short-term reversal. Closed negatively 2026-09-08**, runs
  `20260908T223450Z` (2012-2013 plumbing smoke) and `20260908T224519Z` (full period), no
  promotion. `algorithms/s3_reversal/` (signals + LEAN plumbing, importing S-1's drawdown
  overlay and margin table rather than copying them) and `scripts/sweep_s3.py`. The sleeve
  is dollar-neutral as designed - beta 0.07, mean |net| 0.0000 at decision time - and its
  correlation with the champion is **-0.026**, which was the point of running it. But there
  is no return to allocate: **at zero trading cost**, 24 of 30 parameter cells score a
  negative Sharpe and the best reaches only 0.27, all of it in-sample (IS Sharpe 0.64, OOS
  -0.01) in a cell chosen with hindsight over the whole sample. Inverting the sign to
  short-term continuation is not an edge either. LEAN on the best cell: CAR -0.14%, Sharpe
  -0.19, MaxDD 48.6%, 44,353 orders, **$64,721 of commission on a $100k account** - 2.1bps
  per unit of turnover, commission only, before any spread. Two durable numbers came out of
  it: that 2.1bps cost floor for any daily-turnover book at this account size, and the
  confirmation that a market-neutral sleeve is genuinely orthogonal to the champion, which
  keeps S-5 alive. The survivorship caveat on the megacap pool did not need resolving - the
  result is negative even with the bias working in its favour.
- **S-8 Reach the volatility mandate without breaching the drawdown limit. Closed negatively
  2026-09-08**, runs `20260908T213829Z` (control), `20260908T214218Z`, `20260908T214625Z`, no
  promotion. All four named levers measured and rejected: `top_n=5-6` inverts at higher size
  (S-7's headroom was a small-book property); an earlier breaker (`dd_halve` 0.08-0.10) is
  strictly dominated by carrying less size; a continuous `dd_mode="taper"` re-creates the 2015
  absorbing state and returns -0.2% CAR, because the high-water mark only resets on a *hard*
  `dd_flat` breach; and a per-holding trailing stop leaves `MaxDD` bit-identical, since the
  drawdown comes from the levered index proxies falling together. The elastic vol-responsive
  budget (`margin_budget_cap`/`_floor`) did expose a real defect - the shipped vol target is
  *saturated*, so the champion has never actually vol-targeted, it carries constant margin -
  but fixing it is a size dial, not a shape improvement: at matched 17.1% vol it loses 1.8
  points of CAR and 0.09 Sharpe to the champion while placing 30% more orders. All three
  parameters remain in `signals.py` defaulted off; the control run reproduces
  `OrderListHash 9f58b37cc2656b647ec88a5124daf02d`. **The mandate itself is now a human
  decision** - the LEAN frontier has drawdown binding at 19-20% vol, so 40-60% is unreachable
  under a 35% limit (see `BLOCKERS.md`). Also calibrated: `sweep_s1.py` understates drawdown
  by +2 points at the champion's size and by +8 to +10 at 2x exposure, so sweeps rank, LEAN
  decides.
- **D-3 Point-in-time universe.** 2026-09-08, run `20260908T203212Z`, no promotion.
  `algorithms/s1_momo/universe.py` picks the top N of a candidate pool by trailing 60-day
  median dollar volume on each rebalance, with a 252-session minimum history;
  `Params.universe_size=0` keeps the champion's fixed sleeve, so the default is unchanged
  (control run `20260908T202809Z` reproduces the champion's OrderListHash). Membership is
  genuinely dynamic - 47 names selected across the sample, 458 entries/exits, 2012 holds
  BAC/GE/XOM/WFC/IBM and 2026 holds NVDA/TSLA/AMD - and the strategy on it scores CAR 32.1% /
  Sharpe 0.90 / DD 32.3%, beating the champion and QQQ. **It is still not promotable**, for two
  measured reasons: point-in-time selection removes only 0.8 of the 7.8 points by which the
  megacap basket beats SPY (the other 7.0 are the survivor pool on disk), and the strategy
  gives up 0.19 of Sharpe against simply holding the same 20 names. Filed as a paid-data
  decision in `BLOCKERS.md`.
- **S-7 Beat buy-and-hold on absolute return. Closed negatively 2026-09-08.** S-1 compounds at
  18.1% against SPY's 15.0% and QQQ's 19.9%. All three named levers are answered:
  momentum-proportional weighting loses 2.6-2.9 points of CAR on both sub-periods; `top_n` is
  flat from 3 to 6 in return while getting cheaper in drawdown (3 kept, 5-6 handed to S-8);
  and the wide sleeve beats QQQ only because it is levered and drawn from a survivor pool -
  under D-3's point-in-time membership it still loses to its own basket on Sharpe. Beating
  buy-and-hold on absolute return is therefore not a universe problem, and the untried ideas
  (a second momentum horizon per sleeve, cross-sectional ranking against the sleeve median
  instead of an absolute `min_momentum` floor) belong to whatever replaces the S-1 signal.
- **E-3 Promotion guard against non-statistical bias.** 2026-09-08. `evaluate.py` refuses to
  promote any run whose ledger tag contains `not promotable`, because every other rule it
  applies is a statistic and no statistic can see a universe chosen with hindsight - S-7's
  wide sleeve passed all of them. Convention: tag a knowingly-compromised run at run time.
- **S-6 Raise S-1's exposure by fixing execution, not the signal.** 2026-09-08, run
  `20260908T182554Z`, promoted to champion. Flat `max_gross_weight = 1.0` replaced by a
  margin budget, `sum(w_i * MARGIN_REQ[i]) <= margin_budget`, with Reg-T 50% for ordinary
  ETFs and 100% for 3x ETFs. Mean effective exposure 1.27x -> 1.63x, CAR 13.7% -> 18.1%,
  Sharpe 0.60 -> 0.69, MaxDD 23.6% -> 25.2%; IS 13.5%/0.64/25.2%, OOS 23.8%/0.76/24.8%.
  Option (b) netting was already in place, and option (a) two-step rotation proved
  unnecessary - zero buying-power rejections, audited margin 0.793 vs a 0.75 budget.
  **The 2x target was measured but not banked:** budget 1.0 gives 2.07x exposure and 20.4%
  CAR but a 35.4% drawdown, over the 35% limit, so the shipped default is 0.75. Raising the
  drawdown limit is a human risk decision; going past 2x on merit is S-8.
- **S-1 Volatility-regime momentum rotation.** 2026-09-08, run `20260908T174548Z`, promoted
  to champion. Full period CAR 13.7%, Sharpe 0.60, MaxDD 23.6%, 3,033 orders; IS 2012-2019
  10.4%/0.57/23.6%, OOS 2020-2026 17.8%/0.64/20.8%. Sensitivity: drawdown holds in 18.0-22.4%
  under every +/-25% shock. Two specified components were rejected on evidence - the
  vol-below-median regime filter is anti-predictive (costs 13 points of CAR) and a 200-day
  trend filter loses on both sub-periods - so the regime switch is a crisis filter at 1.5x the
  median. Signal lives in `algorithms/s1_momo/signals.py` (named `signals` not `signal` to
  avoid shadowing the stdlib module on LEAN's PYTHONPATH). Gross exposure is capped at 1.0 by
  execution constraints, so the 40-60% vol target was *not* met; that shortfall is carried
  forward as S-6, and beating buy-and-hold on return as S-7.
- **E-2 Walk-forward and parameter sweeps** (partial). `scripts/sweep_s1.py` runs ablation,
  grid, sensitivity, regime-comparison and IS/OOS modes against the shipped signal code, and
  `scripts/lean_prices.py` reads LEAN's bars back into pandas. Still S-1-specific: generalize
  to any algorithm when a second strategy needs it.
- **D-1 Data pipeline.** 2026-09-08, run `20260908T162819Z`. `scripts/fetch_data.py` writes
  LEAN daily bars, map files and factor files for 69 symbols (19 ETFs + 50 megacaps),
  1998-01-01 to 2026-09-04. Acceptance algorithm `d1_data_smoke` returns PASS: 15/15 probed
  symbols stream 3690 bars over 2012-2026; factors agree with Yahoo `Adj Close` to 0.003%.
  Minute data deferred to D-2.
- **E-1 Evaluation harness.** `scripts/evaluate.py` compares runs with `champion.json`,
  enforces the min-trades and drawdown rules and promotes only on a pass. Verified on the
  D-1 run, which it correctly refused (14 orders < 30, drawdown 72.7% > 35%). Parameter
  sweeps split out to E-2.
