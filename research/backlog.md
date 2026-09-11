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

**2026-09-11 (S-2): the backlog now holds no open research item with a stated mechanism.** A-12,
A-11 and S-2 closed the last three. What remains under "Open" is parked (A-8, by A-4's power
calculation), settled elsewhere (A-3, by A-10), infrastructure (D-2b, E-2b), a standing
per-session measurement (A-5 part 2, ~6.8 sessions from settling), or blocked on a second positive
sleeve that does not exist (S-5). **The binding constraint is the four owner decisions in
`BLOCKERS.md`**, not a missing idea.

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
