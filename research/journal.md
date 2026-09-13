# Research journal

From 2026-09-12 the `daily` track writes to `research/journal_daily.md` (AGENTS.md, "Parallel
tracks"); this file keeps the pre-split history and the daily review's merge target, and each
entry there leaves a pointer here.

## 2026-09-13 - D-7 (`iterate` track)

**AUD-17's premise is true, its P&L reach is 4x bigger than the axis it names, and its
prescribed remedy does not work - proven by a LEAN run, not by reading the engine.** The daily
store is split-adjusted prices labelled raw, exactly as the audit says. But the fix it
prescribes - "store true raw prices with real split factors" - changes **no fee at all**,
because LEAN charges `$0.005 x quantity` on the share count the *algorithm* orders, and in
`DataNormalizationMode.ADJUSTED` that count is the adjusted one whatever the factor file says.
`scripts/sweep_d7.py` (9 clauses pre-registered in the docstring), `algorithms/_d7_feeprobe`
(a one-question LEAN probe), `tests/test_daily_fee_basis.py` (16 tests), 2 DIAGNOSTIC rows
`daily/d7_aud17` plus the probe's own row. Nothing in `live/`, no scheduled task, no price in
any store, and `champion.json` untouched: this run measures and files, it does not migrate.

**Clause 9 (efficacy) is the finding, and it came from LEAN's own sample data.** AUD-17's remedy
is only a remedy if the split factor reaches the fee model. `Lean/Data/equity/usa/factor_files/
aig.csv` carries `split_factor = 20` before 2009-06-30 over **true raw** prices - the file this
repo's fetcher does not write - so the probe buys a fixed $10k of AIG on each side of that
boundary in ADJUSTED mode:

| leg | factor-file split_factor | price the algorithm sees | shares | fee charged | $0.005 x shares |
|---|---|---|---|---|---|
| 2009-06-25 | **20** | $20.4408 | 489 | **$2.4450** | $2.4450 |
| 2010-06-25 | 1 | $26.0938 | 393 | **$1.9650** | $1.9650 |

AIG's raw close on 2009-06-25 was **$1.45** (20.4408 / (0.7048563 x 20)), so a real $10k order was
~6,900 shares and ~$34.48 of commission. LEAN charged **$2.45**. A correct factor file did not
help, and it is sitting right there in the file it read. **The mis-charge is a property of
ADJUSTED normalization plus a per-share fee model, not of this repo's factor files**, so the
migration AUD-17 asks for would move 430,639 bars and correct nothing. The remedy is a fee model
that divides the order quantity by the cumulative adjustment - which is what today's sidecar is
for - or `Raw` mode, which no algorithm here uses.

**Clause 5 (reach) - the champion IS affected, in the conservative direction, and by more than
the audit's own axis accounts for.** The 5,128 recorded fills, repriced at the true raw share
count. The replica is not a model of LEAN's fee: clause 4 reproduces all **5,128 of 5,128**
recorded `orderFeeAmount` values to **$0.0000**, so only the share count is in question.

| basis | total fees | delta vs charged | |
|---|---|---|---|
| as charged (= the promotion row) | **$27,199.76** | - | |
| (a) split axis only, AUD-17's sentence | $22,840.70 | **-$4,359.06** | -16.03% of fees |
| (b) full adjustment, dividends included | **$21,320.92** | **-$5,878.84** | -21.61% of fees, -0.248% of net profit |

A per-share fee is charged on a share count, and the share count is wrong by the **whole**
adjustment, not just its split leg - so (b) is the honest column and **AUD-17 names 74% of its
own defect**. Per symbol, the whole of it is the three sector ETFs and the dividend factor:

| sym | fills | charged | true (full) | delta | min price factor | split in window |
|---|---|---|---|---|---|---|
| XLK | 1,005 | $5,661.65 | $3,113.44 | **-$2,548.21** | 0.8292 | 2.0 on 2025-12-05 |
| XLE | 495 | $5,693.63 | $3,763.80 | **-$1,929.83** | 0.6022 | 2.0 on 2025-12-05 |
| XLF | 673 | $8,183.80 | $7,199.82 | **-$983.98** | 0.7694 | 1.231 on 2016-09-19 |
| TLT | 327 | $871.21 | $712.18 | -$159.03 | 0.6641 | - |
| SPY | 375 | $967.81 | $890.72 | -$77.09 | 0.7769 | - |
| IWM | 550 | $1,781.53 | $1,710.22 | -$71.31 | 0.8226 | - |
| DIA | 258 | $655.10 | $591.00 | -$64.10 | 0.7402 | - |
| QQQ | 908 | $1,831.68 | $1,786.37 | -$45.31 | 0.8833 | - |
| **GLD** | 537 | $1,553.36 | $1,553.36 | **$0.00** | **1.0000** | - |

GLD is the control and it lands exactly where a control should: the one champion symbol that
pays no dividend and never split has an adjusted price identical to its raw price and a
correction of **exactly zero**. Every other row is an **overcharge** - the store bills the
champion more commission than reality would - so the promotion row is conservative and the
direction is safe. The size is not nothing: 21.6% of the fee line. **Do not "fix" this into
the champion's favour without re-running the promotion gate**, because it moves CAR the right
way for the wrong reason.

The XLF row carries a caveat the sidecar cannot express: **1.231 on 2016-09-19 is the XLRE
spin-off, which Yahoo encodes as a split.** No share count changed that day. The fee arithmetic
is unaffected - the adjusted price still differs from the raw one by that factor, so a fixed
dollar order still buys the wrong number of shares - but anyone reading `data/daily_splits.json`
as a pure share-split calendar will be wrong about XLF, and about any other spin-off in it.

**Clause 6 (tradeability) - the failure mode the audit does not name at all.** An adjusted price
far above the raw one does not merely undercharge; LEAN orders whole shares, so the order rounds
to **zero** and the symbol is silently absent from the book. Across 430,639 stored sessions a
$10k order buys nothing on **10,541 (2.45%)** and a $100k order buys nothing on **7,689 (1.78%)**,
and it is not spread out:

| sym | stored sessions | $10k -> 0 shares | $100k -> 0 shares |
|---|---|---|---|
| SOXS | 4,148 | **3,949 (95.2%)** | 3,533 (85.2%) |
| UVXY | 3,752 | **2,426 (64.7%)** | 1,913 (51.0%) |
| SQQQ | 4,167 | **2,522 (60.5%)** | 1,717 (41.2%) |
| SPXU | 4,326 | 1,644 (38.0%) | 526 (12.2%) |

SOXS's cumulative factor at its first stored bar is **1.04e-09**, so its 2010 bars carry an
adjusted price of about **$2.3e11 per share**. Any daily backtest that has ever "tested" the
inverse-leveraged sleeve before ~2020 was testing an empty position, not a bad one, and would
have reported that as zero exposure rather than as an error. Separately, the $1 minimum fee -
which LEAN applies as an `if/ELSE-if`, so it is **not** subject to the 0.5% cap - masks a real
per-share charge on 14,865 sessions.

**Clause 7 (blast radius) - and the sign is not the one the audit gives.** Fee error on a $10k
order, bps of notional, full adjustment. AUD-17 names an understatement (SQQQ/SOXS); the store's
dominant error is a large **over**statement on the forward-split megacaps, because their deep
history is adjusted below $1 a share, where `$0.005/share` exceeds the 0.5% cap:

| sym | splits in span | median err | worst | |
|---|---|---|---|---|
| NVDA | 6 | **-46.34 bps** | -49.00 | the cap binds on most of its history |
| NFLX | 3 | -7.62 | -49.00 | |
| TQQQ | 8 | -7.58 | -49.00 | |
| SOXL | 2 | -5.07 | -49.00 | |
| AMZN | 4 | -3.52 | -49.00 | |
| UVXY | 13 | **+1.73** | +24.24 | the audit's direction, and it is the smaller half |
| USO | 1 | +0.28 | +20.54 | |

**55 of 69 symbols** have a worst absolute error above the intraday harness's own 1.5 bps
slippage line. NVDA at -46 bps per side is ~0.9% round-trip of pure fiction in every daily
backtest that touched it. The champion's own sleeve is mild by comparison - XLK -1.97 bps
median, XLE -1.39, XLF -1.26, and 0.000 for SPY/QQQ/IWM/DIA/GLD/TLT - which is the second
reason the promotion row survives this.

**Clauses 1-3 (the premise, and why the sidecar was safe to write).** 69 factor files, 5,291
rows, **0** with `split_factor != 1`; 58 of 69 symbols have at least one split inside their own
stored span; and the stored close matches Yahoo's split-adjusted close with a worst median
relative error of **3.8e-06** (NVDA) against a storage quantisation floor of 1.0e-04, so the
store is unambiguously on the current share basis and not raw. Had clause 3 failed the whole
item would have flipped sign and nothing would have been written - D-5's rule, that a factor
applied to an already-raw store is the same defect reversed.

`data/daily_splits.json` (gitignored with the rest of `data/`, regenerate with
`py -3.11 scripts/sweep_d7.py --net --write`) is the only artefact that changes behaviour, and
it changes none yet: it is the validated calendar a future fee model needs. Suite green on 3.14
at **1,488 passed, 7 skipped**. The three items this opens - the fee model, the untradeable
inverse-ETF history, and the `sweep_s19.py` cap mismatch AUD-17 also names - are filed under
D-8, D-9 and S-43 rather than done here, because two of them belong to other tracks and the
third changes every daily metric.

**Next:** D-9 (the untradeable inverse-ETF history) is the one that can invalidate a conclusion
rather than a cost column, and it is `iterate`'s own.

## 2026-09-13 - S-42 (`daily` track; full entry in `research/journal_daily.md`)

**The ensemble trick loses on the signal axes, and clears the incumbent of the charge S-40
convicted the crisis switch of.** S-41 blended the 36-cell crisis-switch grid and found it "a
vote on GROSS" (identical name sets on 86.83% of sessions); S-42 re-ran it on the axes that
choose names - `mom_skip` {2,**5**,10} x `mom_lookbacks[3]` {220,**252**,300} x `top_n`
{2,**3**,4,5}, 36 cells, every value from S-38's own list - through `scripts/sweep_s42.py`, 8
clauses pre-registered, 128 DIAGNOSTIC rows `daily/s42_blend`, no LEAN run, no shared-code
change, nothing shipped or owner-owned touched. **The by-product is worth more than the
hypothesis.** S-40 found the shipped crisis-switch cell ranks 24 of 36 in-sample and 1 of 36
out-of-sample - the shape that located AUD-11. The shipped *signal* cell ranks **4 of 36 IS and
5 of 36 OOS**, above its grid mean by +2.344 and +3.161, on a surface whose IS-to-OOS rank
correlation is **negative** (Spearman -0.206 against S-40's +0.208), where the IS top-3 land at
OOS ranks 18/30/16 and **0 of 36 cells beat it on CAR in both halves**: the sleeve's selection
inflation lives in the crisis switch, not on the axes that pick names. The blend itself behaved
exactly as predicted and still lost - a membership vote (identical name sets on 1.90% of
sessions, 4.88 names against 2.47) that nets **0.69x the turnover** for 0.87x the fees, the
first real netting saving measured on this book, and still **17.482 / 0.986 / 23.397 against
19.640 / 1.047 / 24.037** fully charged, paired **-0.784 bps/day at t -2.08**. The loss is not
cost, it is dilution: averaging a concentrated ranking is the same operation as widening it.
Unlike S-41, the incumbent also wins the *decision* bar - both walk-forward selectors pick it in
0 of 11 years and lose to it by ~4 CAR points, and it beats the blend too. **C-8's attack was
then answered on this grid rather than waited for** (clause 8b, added the same day the critic
landed it): 17 of 36 fixed cells dominate `wf-CAR` and 15 of 36 dominate `wf-Sharpe`, so the
margin over the selector is struck from the case, and the rank table C-8 asked for puts the blend
at **14 / 14 / 17 of 36** on CAR / Sharpe / MaxDD against the shipped cell's 2 / 5 / 19 - the
honest refusal is not "it loses to the incumbent" but "it is mediocre among its own
constituents". Nothing promoted, nothing moved, nothing filed for the owner. Opens **S-43**
(rank vote instead of weight average: blend, truncate to `top_n=3`, renormalize).

## 2026-09-13 - D-6 (`iterate` track)

**AUD-07's store half CONFIRMED, FIXED, and LATENT - and the audit's own sentence about it is no
longer true, because a fix in a different file closed the P&L reach while leaving the defect
itself untouched. The Alpaca store holds 22,081 post-market rows wearing an RTH timestamp on 21
early closes; the deployed sleeve's book is bit-identical with and without them (0 of 105 sessions
move, Δ = exactly $0), while `gap_fade` - the one strategy that reads a cross-session feature -
moves on 27 of those sessions by a mean |Δ| of 12.5 bps of equity, up to 65.8 bps, at a mean t of
0.03.** `scripts/sweep_d6.py`, eight clauses pre-registered in the docstring, 2 DIAGNOSTIC rows
under `intraday/active`, `tests/test_intraday_calendar_trim.py` (13 tests).
`live/intraday_config.json`, `live/APPROVED_PAPER.md`, `live/HALT*`, the scheduled tasks and
`scripts/intraday_trader.py` are untouched; the replay and preflight gates were still run, because
the patch touches `load_bars`, which the trader imports.

**Clause 2 (premise) - the store is dirty and the live store is not, which is what makes this
shippable without a live change.** Measured against `quant_brain.markets.equity_us.CALENDAR`:

| store | rows | at/after the session's close | on a full-day closure | sessions |
|---|---|---|---|---|
| `data/minute_alpaca` | 14,781,245 | **22,081 (0.1494%)** | 0 | **21** |
| `data/minute` (IBKR, live) | 1,635,362 | **0** | 0 | 0 |

The IBKR store was fetched RTH-only and already stops at 12:59 on both early closes inside its
span, so trimming on load cannot change anything the live trader reads. That was pre-registered as
the condition for shipping at all (clause 8); had it failed, the patch would have been withdrawn
and re-gated as a live change.

**Clause 3 (tape) - these are not bars, they are a rumour of bars.** Over 310 (symbol, session)
pairs: only a median **31.1%** of the post-close minutes print at all, and the volume that does
print is a median **14.3%** of what the same clock window carries on the five regular sessions
before it (q25 0.083, q75 0.247). The harness charges 1.5 bps of notional for a fill; in that tape
the charge is wrong by about **7.0x**, and that is before the whole-share fill model pretends a
market order clears at the next bar's open.

**Clause 4 (reachability) and clause 5 (materiality) - the defect cannot reach the deployed book,
and the reason is not the store.** Across 21 pinned windows of ±2 sessions around every early
close (105 sessions, each its own $1M book - exact here, not an approximation, because every
feature in `base.features` is session-scoped except `prev_close` and the sleeve is flat at every
close): **0 fills at or after the calendar close, 0 forced end-of-day fills**, and the two arms
agree to the cent.

| `active` | trades | costs | net |
|---|---|---|---|
| post-close bars kept | 17,607 | $282,070 | -$273,923 |
| session trimmed | 17,607 | $282,070 | -$273,923 |
| Δ | 0 | $0 | **$0.00** |

**So AUD-07's "`late_momo` opens at 15:00 in the post-market tape and the flatten fills against it
at 1.5 bp" is out of date, and the correction matters more than the fact.** It was true when
written. It was closed on 2026-09-12 by `eng`'s calendar-aware `flatten_minute_for`, which returns
**188** on a 13:00 close, so `run()` sets `targets = {}` from 12:38 and `late_momo.decide` is never
called at its `entry_minute` of 330. Nothing about the store changed. The bad rows are still there,
still validated as WARN, still loaded - what changed is that a guard in a different file now stops
the strategy before it can read them.

**Clause 6 (channel) - what that looks like when the guard is absent, which is the only number
here worth carrying.** `gap_fade` is not in the deployed `alloc`, but it is the one strategy that
gates on `prev_close`, and on the session after an early close `prev_close` is the 15:59
post-market print instead of the 13:00 official close. Same windows, same arms:

| `gap_fade` | trades | costs | net | sessions moved |
|---|---|---|---|---|
| post-close bars kept | 760 | $26,580 | -$44,067 | - |
| session trimmed | 764 | $26,778 | -$43,895 | **27 of 105** |

Pooled, that is +$1.64/session against a pre-registered threshold of $20.98, i.e. **NOT MATERIAL**
and it would be dishonest to call it anything else. Per affected session it is not small: over the
**14 of 21** early closes whose next session moves at all, mean Δ **+$15**, sd **$2,083**,
**t = 0.03**, mean |Δ| **$1,252 = 12.5 bps of equity**, max **$6,584 = 65.8 bps**. The defect
injects noise with no sign, not a bias. **No P&L test would ever have justified fixing this**, and
a P&L test is the wrong instrument: the store is wrong on 21 sessions whatever the mean lands on.

**Reusable rule: a defect's blast radius and its P&L reach are separate quantities, and closing the
second does not close the first.** AUD-07 was filed as one finding across four files; three were
fixed and the fourth was left because the item read as closed. The evidence that it was not is that
the shipped CLI on a five-session window printed **16 `after_hours` WARNs and ran anyway** - a
validator firing on every run of an eleven-year store is a validator nobody reads.

**Shipped.** `intraday_common.calendar_trim` + `CALENDAR_TRIM` (a pure subset, never raises, and
returns the same object when no day is affected, so the 99.85% of the store it does not touch costs
one set intersection); `load_bars` trims each session at **its own** `CALENDAR.session(day).close_t`
rather than a 13:00 literal; `alpaca_data.py` trims at fetch, closing the site AUD-07 names
(`alpaca_data.py:100-102`), so the store stops growing the defect; `intraday_backtest.py` reports
`forced_eod_orders/notional/days` on **every** run instead of only when A-11's participation cap is
set - the one fill in a session that is never worked, and therefore the one that would land in that
tape - with `--strict-eod` to turn it into a non-zero exit and `--no-calendar-trim` to reproduce a
pre-2026-09-13 row. The 22,081 rows stay on disk on purpose: the loader is the enforcement point,
which is source-agnostic, and any overlapping re-fetch now repairs the parquet.

**Gates.** `--replay 2026-09-11` reproduces D-5's recorded figures exactly (**-9,489 / 215 trades /
$2,498 / flat**); `--replay 2025-11-28`, a real early close, makes **188 decisions** and ends flat
against 368 on 2025-12-01; `intraday_launch.py --preflight-only` passes every gate; full `tests/`
**1,472 passed, 7 skipped** on py -3.14 (the launch gate's interpreter); `paper_trade.py --help`
exits 0 on py -3.11. Clause 1 identity: in-process **-5,653.121423 $/day, 962 trades, $3,510.52
costs/day** on 2025-11-25..2025-12-02 against the shipped CLI's **-5,653 / 962 / 3,511**. Clause 7:
`calendar_trim` checked on all 32 symbol-stores of both stores, **0 violations**. The same window
run through the CLI validates **0 fail, 0 warn** with the trim and **0 fail, 24 warn** without.

**Opens F-19** (`ml`): `data/f1/panel.parquet` is built from `ic.load_bars` by `sweep_f1.py:186`
and cached, so every F-track panel built before today carries the post-close rows, resampled into
bogus 5-minute bars on those 21 sessions. Cheap to close - rebuild the panel - but it is the ml
track's file and the ml track's call.

## 2026-09-13 - S-41 (`daily` track, pointer; full entry in `research/journal_daily.md`)

**The ensemble S-40 filed is worth having, the sentence it was filed on is not, and the two facts
are independent.** S-41 built the implementable object S-40 could only bound: the equal-weight mean
of the 36 crisis-switch cells' target **WEIGHTS** - one account, one order list - rather than of
their returns, executed through the deployed rebalance and fully charged in S-22 cell C. Clause 1b
is the new licence: the shipped cell's weights are extracted day by day and fed back through the
same simulator and reproduce the deployed book **to the digit on CAR and order count**. First
result: weight-averaging and return-averaging are **the same book here**, agreeing to 0.034 CAR
points and 0.001 Sharpe on all three windows - because the blended target holds at most 3 names and
on **86.83%** of sessions holds the *identical name set* as the shipped cell, differing only in
size. The ensemble is a vote on gross, not on which names to own, so there is nothing to net.
Second, and it withdraws S-41's own premise: S-40's "best Sharpe 1.173" is a **2,684-session** row
(the 2016-2026 walk-forward span) compared against a **3,689-session** FULL-window 1.159. Span-
matched, the shipped cell scores **1.228** and the blend **1.174** - the blend never had the best
Sharpe. The drawdown half survives by luck (the worst drawdown is the 2020 crash, inside both
spans). Rule, for the second time this month: **a number quoted from a table is a comparison only
if the row it is compared against has the same session count.** Fully charged the blend gives up
**-1.096 CAR on FULL and -3.924 on OOS** to buy **0.286 / 0.217 points of drawdown**, at paired t
-0.92 / -1.64, and it trades **1.26x the orders** at 0.99x the turnover because gross now ratchets
in 1/36 steps across a fractional risk-off boundary that is live on **39%** of sessions. It fails
the pre-registered promotion bar on Sharpe and CAR and passes on drawdown and executability (0.002%
of target weight lost to the no-trade band, bar 10%). **Nothing ships.** But clause 7b is the
number that matters: against what a real-time selector *actually gets* - not against a cell S-40
proved unfindable - the blend beats the walk-forward CAR selector by **+1.587 CAR / +0.163 Sharpe /
-14.858 drawdown points** and the Sharpe selector by +1.886 / +0.174 / -14.858. The blend is not a
better cell than the one that shipped; it is a better book than *choosing* a cell. Opens **S-42**
(the same trick on the FITTED axes that are not risk dials). `scripts/sweep_s41.py`, 7 clauses, 21
DIAGNOSTIC rows under `daily/s41_blend`, one default-inert `weights_fn` on `sweep_s25.legs_simulate`
(re-proved bit-identical), no LEAN run, `champion.json`, `live/*` and all scheduled tasks untouched.

## 2026-09-13 - S-40 (`daily` track, pointer; full entry in `research/journal_daily.md`)

**The crisis switch is a drawdown instrument that has been read as a return instrument, and its
shipped cell is the argmax of its own 36-cell grid on the half this repository labels
out-of-sample (rank 1 of 36, 29.124%) while sitting below the median on the half it labels
in-sample (rank 24 of 36, 16.488%).** S-38 named `regime_vol_window` (+3.596) and
`regime_threshold` (+3.016) as the two biggest contributors to selection inflation; S-40 ran the
joint surface, ablated the switch for the first time since S-1, and walk-forwarded the two dials
on a selector that sees only a 31-December backtest. The selector picks the shipped cell in **0 of
11 years** under both a CAR and a Sharpe objective and lands **-1.389 / -1.688 CAR points below
the grid mean** with the worst drawdown of any book tested (38.185%), so the shipped cell's
distance above the grid mean is hindsight in full. Turning the switch off is worth **+2.68 CAR at
t +0.96 fully charged and costs 12.9 points of maximum drawdown** (24.037% -> 36.892%), which the
promotion gate refuses on its own terms (`max_drawdown_limit: "35%"`, `drawdown_tolerance_points:
1.0`) - so the switch stays and nothing ships. Two things carry: S-38's FITTED classification of
these two axes is **wrong** (they are risk dials, so a CAR grid over them measures the dial doing
its job, and S-38's +1.25 to +2.07 is biased upward by an unmeasured amount), while AUD-11's label
finding is strengthened rather than weakened - clause 3 is the mechanism behind the percentile.
The by-product is the only thing worth building: the equal-weight blend of all 36 cells requires
no selection at all and carries the best Sharpe (1.173) and the lowest drawdown (23.389%) of every
book in the table. Filed as **S-41**. `scripts/sweep_s40.py`, 7 clauses, 118 DIAGNOSTIC rows under
`daily/s40_regime`, no LEAN run, `champion.json` and `live/*` untouched.

## 2026-09-13 - D-5 (`iterate` track)

**AUD-15 CONFIRMED, FIXED and MATERIAL at the largest |t| a cost correction has produced on this
sleeve: the IBKR minute store is split-adjusted, `share_scale` was 1.0 for it, and pricing it as
raw understated this sleeve's commission by $548/day - 29.8% of its whole cost line - out of 279
of 4,208 stored symbol-days. The IBKR-store book is -$2,460/day, not -$1,924/day.** The audit's
numbers needed three corrections and all three make the defect wider or smaller in a way that
matters. `scripts/sweep_d5.py`, eight clauses pre-registered in the docstring, 2 DIAGNOSTIC rows
under `intraday/active`, `tests/test_intraday_splits.py` (14 tests). `live/intraday_config.json`,
`live/APPROVED_PAPER.md`, `live/HALT*`, the scheduled tasks and `scripts/intraday_trader.py` are
untouched; the replay gate was still run, because the patch touches shared code the trader imports.

**Clause 1 (identity).** With no table loaded, `share_scale` is exactly 1.0 on all **4,208** stored
symbol-days (16 symbols x 263 sessions, 2025-08-26 .. 2026-09-11), and the in-process control book
reproduces the shipped CLI to every printed digit: **263 sessions, 53,526 trades, -$1,923.77/day,
costs $1,839.11/day, net -50.595%, Sharpe -3.2245, DD 50.595%, 203.52 tr/day, worst -$22,588.81,
10 loss-limit days**. So clause 5 measures the correction and nothing else.

**Clause 2 (premise) - the store really is adjusted, and it is not MIXED, which is the half the
audit did not check.** Three split events fall inside the store's span. The store's own
close-to-close step across each one sits at 1.0, not at the raw-basis prediction, and the decision
is against the symbol's own overnight-gap distribution rather than a guessed tolerance:

| symbol | split | ratio | store's step | raw would be | own gap q99 | verdict |
|---|---|---|---|---|---|---|
| NFLX | 2025-11-17 | 10-for-1 | 0.9920 | 10 | 9.20% | ADJUSTED |
| SOXS | 2026-03-05 | 1-for-20 | 1.0325 | 0.05 | 27.51% | ADJUSTED |
| SOXS | 2026-07-15 | 1-for-10 | 1.0684 | 0.1 | 27.51% | ADJUSTED |

And because Alpaca is adjusted to the current basis by its own table, the monthly median
IBKR/Alpaca close ratio is a mixed-basis detector: **14 months, ~101k overlapping bars per symbol,
every monthly median inside 1.00000..1.00003 for all 16 names, worst deviation 0.00%**. An
incrementally built store would have shown a step of the split ratio across the seam; this one was
re-fetched after both splits (D-4's repair did it), so it is on one basis throughout - by luck, not
by design, which is what clause 7 fixes.

**Clause 3 (source-agnostic derivation).** The table is derived from a split **calendar**
(yfinance, no API key) rather than from Alpaca's raw/adjusted price ratio, and the two agree on
**4,208 of 4,208 symbol-days, 0 disagreements**: SOXS `0.005 / 0.1 / 1.0` and NFLX `10 / 1` to the
digit. Two independent sources was the pre-condition for writing the file, not a nicety - a factor
applied to a store that is actually raw is the same defect with the sign flipped.

**Clause 4 (the ceiling, quoted before the P&L column - S-32's rule) and clause 6 (direction).**

| symbol | segment | sessions | factor | adj px | raw px | as priced | correct | error |
|---|---|---|---|---|---|---|---|---|
| NFLX | 2025-08-26 .. 2025-11-16 | 58 | 10 | 120.25 | 1,202.45 | 0.416 | 0.042 | **-0.374** |
| SOXS | 2025-08-26 .. 2026-03-04 | 131 | 0.005 | 680.00 | 3.400 | 0.074 | 14.706 | **+14.632** |
| SOXS | 2026-03-05 .. 2026-07-14 | 90 | 0.1 | 99.45 | 9.945 | 0.503 | 5.028 | **+4.525** |

bps of notional, one side. **Three corrections to AUD-15.** (a) Its "about 1.25 bp versus about
100 bp per side" assumes the 1% commission cap binds; it does not - SOXS's raw price is $3.40, so
the correct charge is **14.71 bps, not ~100**, and the as-priced charge is **0.074 bps, not 1.25**.
The *ratio* the audit gives (1/200) is exactly right; both of its levels are wrong, one by 17x and
one by 7x, and the error that matters is **14.63 bps/side**, nearly 10x the 1.5 bps slippage line.
(b) It names only the segment before 2026-03-05; the **middle segment is also wrong** (90 sessions
at 10x, +4.53 bps/side), so the affected set is **279 symbol-days, not ~188**. (c) It calls the
whole thing an understatement; **NFLX is OVERcharged** by 0.374 bps/side for 58 sessions. Two of
the three segments are the same mechanism pointing in opposite directions, and only the sign of the
factor decides which.

**Clause 5 (materiality) - two paired harness runs on the shipped harness, one load of bars, the
only difference being the table.** 263 sessions, $1M book, `active` as deployed:

| | control (shipped) | corrected | delta |
|---|---|---|---|
| net $/day | **-1,923.8** | **-2,460.0** | **-536.3 (t -4.08)** |
| costs $/day | 1,839.1 | 2,387.4 | **+548.3 (+29.8%)** |
| trades | 53,526 | 53,153 | -373 |
| Sharpe (daily) | -3.22 | -4.65 | -1.43 |
| max drawdown % | 50.60 | 64.70 | +14.10 |
| loss-limit days | 10 | 16 | +6 |

Pre-registered thresholds were 5% of the cost line ($92.0) and 5% of |net| ($96.2): the measured
deltas are **6.0x and 5.6x** them. **MATERIAL.** The net delta is smaller than the cost delta
because the correction also moves the whole-share floor to the real price and the book trades 373
times less; the rest is the sleeve paying its own commission. Note what 6.6% of the symbol-days
did to the whole book - this is a **one-name** effect, and SOXS is a $3 stock on the real tape.

**Clause 7 (the guard, AUD-15's second half).** `save_bars` now refuses a merge whose overlapping
closes disagree (`BasisMismatch`): median |new/old - 1| over the overlap, 2% tolerance, minimum 10
overlapping bars, `allow_rebasis=True` for the deliberate full re-fetch after a split, plumbed to
`intraday_data.py --rebasis` (only with `--repair`, which spans the whole calendar). The statistic
has to separate ~1.0 from >=0.5, so 2% is generous to IBKR's own bar revisions and nowhere near a
split. On the real store, all 16 symbols: **honest re-save allowed 16/16, a x10 rebasis caught
16/16**. The minimum-overlap rule is deliberate and is D-4's lesson applied - a guard that refuses
on a 5-bar boundary overlap freezes the store, and a frozen store is worse than a mis-costed one.

**Gates.** Full suite **1,203 passed / 13 skipped** (1,208 under the launch gate's own run);
`intraday_launch.py --preflight-only` **green**, replaying 2026-09-11 with no open positions. The
table is proven **inert for the live path**: `scripts/intraday_trader.py --replay 2026-09-11` gives
**-9,489 / 215 trades / $2,498 costs / 368 decisions / flat** with the file present and absent,
byte-identical, and equal to D-4's recorded replay. That separation is structural, not luck - the
trader prices fills from the live raw tape and never calls `share_scale`.

**What it changes for the loop.** Every IBKR-store result before today is costed 30% light, and the
number to use for that store is **-$2,460/day**. The Alpaca-store results (A-8, A-13, A-14, A-15,
the F-series) are unaffected - `data/minute_alpaca/_splits.json` has existed since A-10. Reusable
rule: **a cost defect's ratio and its levels are two claims, and an audit that gets the ratio right
can still be 17x out on the level** - so re-derive the level from the store's own prices before
quoting an audit's bps figure, and re-read the *cap* as well as the rate, because AUD-15's ~100 bps
was the cap and the cap never binds. Second rule, from clause 2b: **"is this store adjusted" and
"is this store adjusted CONSISTENTLY" are different questions**, and only the second one is
answered by comparing against another store that is known to be on the current basis.

**Filed, not fixed (out of this iteration's scope, both latent):** `intraday_trader.py`'s own
replay path calls `commission(q, px)` with no scale while reading the adjusted store, so a replay
of a session inside an affected window would undercharge it the same way. Unreachable from the
deployed task - `intraday_launch.last_session()` always picks the most recent complete session -
so it is filed as **A-16** rather than patched, because the fix edits a runner-loaded file for a
path the runner cannot take. **AUD-17** is the same defect one store over (the LEAN daily store)
and is the next `iterate` data item that needs no trading day.

## 2026-09-13 - S-39 (`daily` track; full entry in `research/journal_daily.md`)

**C-5a/b/c closed. The paper runner's data gate was one-sided because S-37 assigned the missing
half to `fetch_history_ib` and then never fixed it - a test (`test_paper_dataquality.py:104`)
made the assignment permanent - so `--history ib` at 15:45 ET returned the session in progress,
the signal ranked on a mid-session print, and the gate that exists to stop exactly that passed
it. Latent, never live: the deployed task passes no arguments and yfinance drops today's bar.
Both ends are now closed** - the source filters and the gate reports `day > prev` under its own
message - **and six existing tests moved onto the live contract (`as_of == previous_session`),
which they had been violating by one session.** New `scripts/sweep_s39.py` priced the frame the
hole admitted, on nine names of Alpaca SIP minute bars (six fetched for this, all nine priced on
2,683 of 2,683 sessions): both books fill at the same real 15:45 print, so they differ only in
whether the signal saw today's partial bar, and **it is worth -0.049 bps/day at t -0.08 fully
charged** (22.483% against the deployed 22.602%, agreeing in both halves) **while rewriting the
order list on 76.7% of sessions for 10.2% more orders.** Noise in the last row of the ranking
window, not fresher information. The reusable by-product is about S-19: its `bound` companion
cell hands the signal **close[i], a price 15 minutes after it decides**, and that still loses
(-0.141 bps/day, t -0.24), so **the ~1.9-2.1 CAR points S-19 attributed to this sleeve's clock
are entirely a FILL-MOMENT effect - S-19 never varied what the signal reads, both its rows read
close[i-1]** - and the pre-open question in BLOCKERS.md gains nothing from a fresher input.
Identity exact (22.192150170492255% / 5,052), `compare_orders.py` 3,689/3,689 at 5,021 orders,
full suite green on py -3.14. C-5a (the S-37 verification script could not run at HEAD, because
clause 1 grepped for text S-37's own patch had deleted) and C-5b (the owner-facing break-even
was quoted from a cell running at 11x its own stated outage rate - it is **two to four** bad
prints a year, not 2.0; the MATERIAL verdict is unchanged) are fixed and corrected in place.
Nothing promoted, no strategy parameter touched, `champion.json` untouched.

## 2026-09-13 - A-15 (`iterate` track)

**REFUSED, and the refusal is a general one: this sleeve is paid +$2,651/day per 1 sd of the
SURPRISE in market magnitude at t +8.41, and -$230/day per 1 sd of the FORECASTABLE part at
t -0.73. A perfect magnitude nowcast is worth +$550/day; every causal one is worth nothing,
because 90% of the magnitude the sleeve lives on cannot be forecast and the 10% that can pays
the wrong sign.** O-6 handed this track the question of whether the 0DTE chain's `rn_half`
magnitude nowcast - incremental over the tape at 5 of 5 clocks, DM t +3.5..+4.2 - can SIZE the
intraday sleeve. `scripts/sweep_a15.py`, eleven clauses pre-registered in the docstring, **no
backtest** - every number comes off A-8's persisted sleeve P&L (`results/a8/daily_control.csv`,
2,686 sessions of the shipped config), O-5's frozen chain cache, the Alpaca SPY minute store and
S-29's VIX series. **4 DIAGNOSTIC ledger rows** under `intraday/active`; nothing shipped, no
runner-loaded or scheduled file touched, `live/*` untouched, so no replay and no
`compare_orders.py` is owed.

**Clause 0 finds the item's premise is wrong, and it matters.** A-15 was written as "beat the
sleeve's realized-vol sizing". The sleeve has no vol sizing: `orb` is a constant 0.12 of equity
per position, `vwap_trend` 0.10, capped at `per_symbol` 0.15 and `gross` 1.0. The incumbent is
**flat notional**, so the tape control had to be built here and the item is two questions - does
**any** causal magnitude forecast beat flat sizing (free), and does the **chain** beat the free
one (costs the Theta VALUE ask). Clause 1 reproduces A-14's control book to the digit
(-262.2 / -512.1 / -133.7 by regime, -323.6 full period, 2,686 sessions).

**The trap the test is built around, because the control book loses money.** At -$324/day, any
scaler averaging below 1 "wins" by turning a losing sleeve down - which is a decision the owner
already made twice and needs no options data. So `k` is divided by its own **expanding prior
mean** (causal) and every headline is reported as `mean[(k-1)·pnl] = cov(k,pnl) + (mean k - 1)·
mean(pnl)`, with the PASS condition on the covariance term alone.

**Clause 2 says the mechanism is real and large.** Sleeve P&L on the realized |SPY open-to-close
move|: **+$2,789/day per 1 sd at t +11.67**, terciles monotone at -2,819 / -1,732 / **+3,583**
$/day. A breakout sleeve is exactly the thing a magnitude forecast should size.

**Clauses 3-5: every causal scaler fails, and the hindsight ceiling shows how much is being
left.**

| scaler (beta 0.30, band [0.5, 2.0]) | n | cov $/day | t | book $/day | Sharpe |
|---|---|---|---|---|---|
| flat (the shipped control) | 2,686 | - | - | -323.6 | -0.36 |
| tape `rv20`, pre-open | 2,686 | **-62.5** | -1.05 | -394.7 | -0.39 |
| tape `vix_lag`, pre-open | 2,686 | -70.0 | -1.12 | -406.3 | -0.39 |
| chain `rn_half` @10:00, raw | 1,847 | -168.7 | -1.92 | -554.2 | -0.54 |
| **chain @10:00, residual over tape** | 1,847 | **-157.6** | -1.94 | -546.4 | -0.55 |
| chain, pre-open lagged, residual | 2,282 | +105.9 | +1.28 | -208.2 | -0.17 |
| **ORACLE \|move\| (CEILING, not tradeable)** | 2,686 | **+550.2** | **+9.46** | **+222.0** | **+0.28** |

Perfect hindsight on the session's magnitude turns this book from -$324/day at Sharpe -0.36 into
**+$222/day at Sharpe +0.28 with drawdown 69.6% -> 40.8%** - the largest single improvement
anything has produced on this sleeve. No causal version captures any of it. The one positive
causal variant, the strictly pre-open lagged chain residual, is +$106/day at **t +1.28** and 3 of
3 regimes, which does not clear and is not claimed.

**Two pre-registered defences fired, and both were honoured rather than written around.**
(1) Clause 8's linearity bound **FAILED**: linear scaling implies 64 (tape) and 55 (chain) NEW
2.5% loss-limit breaches, 2.38% and 2.05% of sessions against a 2% bound. So clause 8b becomes
the headline - a loss-limit-aware book that stops the moment `k·low_ret` crosses the limit,
calibrated on the control's own 93 stopped sessions (which are **exactly** the 93 with
`low_ret <= -2.5%` and realize -2.598%, a 0.098-point flatten cost). Under it the tape scalers
are **free rather than harmful** (+23.5 / +36.7 $/day at t +0.34 / +0.50) and the chain residual
is still -135.9 at t -1.51: the linear version's harm was partly an artifact of not modelling the
stop, and modelling it does not rescue the chain. (2) Clause 9's single scramble landed at
-$139.5, **not** at zero - so one scramble is one draw, not a null. The 300-permutation
distribution has mean -11.9 and sd 68.8, band [-121.4, +93.1]: the tape scaler is **inside** it
(z -0.42, indistinguishable from noise) and the chain residual is at z **-2.12**, nominally
outside but one of four comparisons, with its own sign softening to t -1.51 under the correct
book. Read honestly: the chain scaler cannot be called helpful, and should not be called harmful
either.

**Clause 10 is the answer, and it generalizes past the two scalers actually built.** Split
log|SPY move| by expanding causal OLS into the part a forecast can see and the surprise, then
pay the sleeve on each:

| forecast built from | var(log\|move\|) explained | PREDICTABLE part | SURPRISE part |
|---|---|---|---|
| tape (`rv20`, `vix_lag`) | 0.090 | -$230/day per 1sd, t -0.73 | **+$2,651/day per 1sd, t +8.41** |
| tape + chain `rn_half` | 0.100 | -$662/day per 1sd, t -1.93 | **+$2,939/day per 1sd, t +8.56** |

The chain buys **one point of R²** on top of the tape - consistent with O-6, which is not
contradicted anywhere here - and the 10% of magnitude that is forecastable at all pays **nothing,
leaning negative**. The +$2,789/day of clause 2 lives entirely in the 90% no one can see in
advance. That is why the sensitivity grid is a shelf of negatives (all nine beta x band cells
land between -82 and -257 cov for the chain residual, -31 to -102 for the tape): there is no cell
to find, because the input is the wrong input.

**What this closes and what it does not.** It closes A-15 as posed and, more usefully, closes the
whole *class*: on this sleeve, **conditioning size on any predictor of realized volatility is
refused on the mechanism, not on the sample**, so a better magnitude model - a longer chain, a
second underlying, an ML nowcast - cannot change the verdict, and O-6's finding should not be
re-proposed as a sizing input for the A-track. It does **not** touch O-6's own claim, which is
about SPY forecast accuracy and reproduces here. It does **not** say volatility sizing is useless
generally - under the loss-limit-aware book it is roughly free, so it remains available as a risk
dial (dispersion, drawdown) as long as nobody quotes it as a P&L improvement. And it leaves one
number for the owner file: the gap between the ORACLE's +$222/day book and the deployed -$324/day
is the **entire** remaining value of this sleeve, and it is locked behind a quantity that is by
construction unforecastable. `live/intraday_config.json` is unchanged at `equity_frac` 0.25 and
`time_stop` 240.

**Next:** nothing in the A-track. A-14 closed the last item with a stated mechanism and A-15
closed the last handoff into it; the standing per-session job A-5 part 2 is the only open
`iterate` work, and it needs live fills, not a sweep.

## 2026-09-13 - A-14 (`iterate` track)

**The time stop is not pure cost, and the way it fails is worth more than the answer: 9 of 11
years are positive, the median session is -$226, and 27 sessions carry 108% of the money.**
A-8 left the ORB `time_stop` ladder monotone with no interior optimum - -$954 / -$340 / -$324 /
-$160 / **+$81** per day at 120 / 180 / 240 (shipped) / 300 / 368 - and refused the best cell
because its whole significance was one regime (+990.7 at t +2.80 on 2020-2023 against -76.3 at
t -0.24 on 2024-2026). A-14 is the test A-8's three-regime rule could not run: fit nothing, select
on 2016-2023, score on 2024-2026. `scripts/sweep_a14.py`, eight clauses pre-registered in the
docstring, **no backtest** - every number comes off A-8's persisted series
(`results/a8/daily_<cell>.csv`) and S-29's `data/regime/vix.csv`. **4 DIAGNOSTIC ledger rows**
under `intraday/active`; nothing shipped, no runner-loaded or scheduled file touched, `live/*`
untouched, so no replay and no `compare_orders.py` is owed.

**Clause 1 holds on all 14 checks to the published digit** - control book -262 / -512 / -134 $/day
by regime, `stop368` paired +139.9 / +990.7 / -76.3 at t +0.91 / +2.80 / -0.24, full-period paired
+404.28 against the journal's +405, book +$80.71/day at t +0.25, Sharpe 0.14, DD 40.17%. The
files are the ones A-8 reported.

**Clause 2 selects honestly and selects the same cell.** On 2016-2023 alone the ladder is
-489.9 / +33.5 / 0 / +170.8 / **+565.3** $/day paired, `stop368` at **t +2.93** - so the cell is a
real in-sample winner past 2 sigma, not a cell that only looks good because the OOS half was in
the sample. Its IS book is the only positive one on the ladder (+$178/day, Sharpe +0.23, DD 32.8%
against the control's -$387, -0.47, 60.8%).

| | IS 2016-2023 | OOS 2024-2026 |
|---|---|---|
| sessions | 2,012 | 674 |
| paired d$/day | **+565.3** | **-76.3** |
| t | +2.93 | -0.24 |
| block-bootstrap 95% CI | - | [-733, +584] |

**Clauses 3 and 4 fail, and clause 5 says that on its own this proves nothing.** OOS is -$76/day
at t -0.24, bootstrap one-sided p 0.602, and the book is worse than the control (-$210 vs -$134,
Sharpe -0.09 vs -0.10; the only thing it wins is drawdown, 40.2% against 43.5%). But the OOS half
can only detect **$625/day at 2 se** and the IS estimate is **+565** - *below* its own detection
floor. Resolving the IS number needs **939 sessions (3.7 years)** and the withheld half has 674.
The two CI conventions even disagree about whether the IS estimate is excluded (normal upper
+535.9, so yes by $29/day; stationary bootstrap upper +584.4, so no), and the bootstrap is the one
that respects the serial dependence in daily P&L, so clause 5 is read as **not rejected**. A split
test that was cheap and correct to run turns out to be the wrong instrument for this question, and
saying so is the point of pre-registering a power clause.

**Clause 6 decides it, and needs no power to do so, because it is a statement about where the
money is.** 91.8% of the $1,085,905 cumulative difference is 2020-2023; the best **27** sessions
(top 1%) are **107.8%** of it, so the other 2,659 sessions are net negative together. Read as a
shape rather than a share, the same fact is brutal:

| | mean $/day | median $/day | positive sessions | mean less the best 1% |
|---|---|---|---|---|
| full 2016-2026 | +404.3 | **-225.9** | 47.4% | **-31.7** |
| IS 2016-2023 | +565.3 | -149.0 | 48.0% | +112.8 |
| OOS 2024-2026 | -76.3 | -527.3 | 45.4% | -452.8 |

On the typical session the 240-minute stop is mildly **helpful**. The entire advertised +$405/day
is 27 days of letting a breakout run through a crash. That is a lottery ticket, not a cost, and it
is exactly the payoff shape a paired t-test on 2,686 daily numbers is worst at describing. Between
regimes, 2020-2023 vs 2024-2026 is z **+2.26** and 2016-2019 vs 2020-2023 is z **-2.21** - the
three means are not draws from one distribution.

**Clause 7 finds the mechanism, confirms it is volatility, and then watches it fail out of
sample.** On the prior session's VIX close (strictly causal, lagged one session) the daily
difference regresses at **+$59 per VIX point at t +2.57** full period, +58.6 at t +2.37 in sample,
and the IS terciles are monotone: **+85.8 / +475.7 / +1,134.2** $/day at t +0.66 / +1.72 / +2.31.
Out of sample the slope is +39.1 at **t +0.56** and the terciles are not even ordered
(+186.8 / -217.3 / +160.6). The conditional rule this suggests - hold to the 15:38 flatten only
when the prior VIX close is above its IS median of 17.02, keep the shipped stop otherwise - is
worth **+$9.5/day at t +0.04** over the withheld half, on 293 of 674 sessions. The mechanism is
real, it is volatility, and it is not harvestable by a rule chosen before seeing the outcome.

**The A-track closes on evidence rather than exhaustion.** A-8 was the last item with a stated
mechanism and A-14 was the last question A-8 left; the answer is that the ORB sleeve's best
remaining lever is a bet on the next 2020, and the deployed book is at t +0.25 over eleven years.
`live/intraday_config.json` stays at `time_stop` 240 and `equity_frac` 0.25, and the Current
objective's instruction - say the sleeve cannot be validated rather than find a twelfth lever -
now has nothing left standing in its way except A-5 part 2's fill constant.

**Standing job, re-quoted (Saturday, no new fills since 2026-09-11):** `slippage_report.py` - 66
fills over 2 sessions, **+2.21 bps** notional-weighted, se 0.80, |measured - shipped| / se = **0.88**,
still short of the 2 se bar; ~145 fills (~4.4 sessions) are needed. Unchanged, and unchangeable
until the market reopens.

**What it changes for the loop:** when a paired mean is positive and its median is negative, the
mean is a tail statistic and the t-test on it is describing the wrong object - quote the median,
the positive-session share and the trimmed mean **before** the t, on any daily-difference table.
And second: a pre-registered power clause is worth as much as a pre-registered decision clause,
because without it this iteration would have reported "refused out of sample at t -0.24" about a
half that could never have seen the effect it was testing for.

## 2026-09-12 - A-8 (`iterate` track)

**The entry window and the time stop move nothing on this sleeve, and the one constant that does
move it is the one the event study said would not.** `entry_after` / `entry_before` / `time_stop`
have sat at **15 / 150 / 240** through every A-track iteration since A-1 and had never been asked
a question; the backlog parked A-8 on A-4's power calculation (260 IBKR sessions cannot resolve a
sleeve at Sharpe 0.62) and that objection expired when `data/minute_alpaca` reached **2,686
sessions** of consolidated SIP bars on the same 16 names. `scripts/sweep_a8.py` runs the
pre-registered grid on that store - eleven cells, each the deployed config (`alloc` ORB 1.0,
`per_symbol` 0.15, `gross` 1.5, `disaster_atr` 4.0, i.e. `live/intraday_config.json` exactly) with
**one** minute constant moved, one backtest per (cell, calendar year) from a fresh $1M book. It
was run in four batches across the day because a cell costs ~4 minutes of wall clock per year and
the whole grid does not fit under the 40-minute per-command ceiling; `--combine` reads the
persisted batches back into one table, and every result below is from that combined run
(`results/a8/combined.log`, 36 DIAGNOSTIC ledger rows under `intraday/active`).

**THE VERDICT IS REFUSED: 0 OF 11 CELLS PASS CLAUSES 2-4.** Not one cell reaches "paired daily
difference positive at t > 2 in two of the three regimes", not one produces a book that is
positive at t > 2 in two regimes, and the two cells that get a single regime past t = 2
(`before120` at +2.14 on 2024-2026, `stop368` at +2.80 on 2020-2023) are contradicted by another
regime of their own. The control is the deployed book at **-$324/day, t -1.32, Sharpe -0.36,
DD 69.6%, 34.9 trades/day, $913/day of costs** over the eleven years.

**Clause 1 (identity) holds in decisions and cannot hold in P&L, and that is not a defect.** The
control reproduces A-12's control **exactly where the framework decides** - sessions
1,006 / 1,006 / 674 and trades/day **27.3 / 39.4 / 39.1** in the three regimes, identical to the
printed precision - and differs in P&L (-262.2 / -512.1 / -133.7 against A-12's -287 / -522 / -112,
pooled **+$7.6/day**). Four commits have changed this harness since A-12 ran: `f1c9968` (A-13's
six bias fixes), `1311586` (the calendar-aware flatten, AUD-07), `25d30db` (the validation gate)
and `9d67bef`. So the "same $/day" half of the clause was void before the grid started, and the
check that survives is the decision-level one plus this: A-8's control on 2024-2026 (**-$133.7**)
agrees with **A-13's own recorded control cell (-$133)** rather than with A-12's -$112, which ties
this grid to the current harness's most recently measured control.

**The entry window is dead in both directions, and the post-hoc window kills it most cleanly.**
Stage 1's event study (44,219 round trips, `--attribute`) found exactly one positive entry-minute
bucket out of six - **90-119 minutes, +$43.2/trip at t +2.27, z +3.31 against the pooled
-$20.1/trip** - with 30-44, 45-59, 60-89 and 120-150 all negative at t -1.97 to -2.90. Clause 6
let that be isolated as a labelled post-hoc cell, `win90_119`, so that the *strongest* form of the
hypothesis was priced rather than left as an anecdote. It does not survive: the paired difference
is **-85.5 / +305.8 / -0.5 $/day at t -0.47 / +0.90 / -0.00**, the book is **-$241/day** with the
worst single-regime t on the whole page (**-2.20** on 2016-2019), and it reaches that on
**21.8 trades/day against the control's 34.9** - it is a 37% turnover cut that buys nothing. The
six pre-registered cells agree: `after30/45/60` are 0/3 on clause 2 and `before60/90/120` are
0/3, 0/3 and 1/3, and every one of the six fails the trade-reduction falsification (clause 3) in
at least two regimes. A bucket that pays at the trip level does not pay when it is the only
bucket traded, which is the whole content of clause 3.

**The one real finding is the time stop, and it is the cell the trip-level table would have told
you to skip.** `attr_timestop.csv` reads like a forecast: trips closed *by* the 240-minute stop
earn **+$1,057/trip** and trips that exit on their own terms lose **-$1,083/trip**, and the
hold-time ladder rises monotonically from -$1,059/trip at 0-14 minutes to +$1,238 at 200+. That is
a composition artifact - a trip survives to the time stop *because* it has not been stopped out -
and the grid is the only thing that can price it. It does, and the ordering is **monotone in stop
length with no interior optimum**:

| cell | $/day | t | Sharpe | DD % | tr/day | costs/day |
|---|---|---|---|---|---|---|
| `stop120` | **-954** | -5.27 | -1.57 | 95.3 | 50.2 | 1,239 |
| `stop180` | -340 | -1.48 | -0.40 | 67.5 | 34.8 | 911 |
| control (240) | -324 | -1.32 | -0.36 | 69.6 | 34.9 | 913 |
| `stop300` | -160 | -0.58 | -0.13 | 49.1 | 35.0 | 943 |
| `stop368` (= the flatten) | **+81** | +0.25 | +0.14 | 40.2 | 35.1 | 998 |

Removing the time stop entirely - letting a breakout run to the framework's own 15:38 flatten -
is worth **+$405/day paired** (+139.9 / +990.7 / -76.3 by regime, **t +0.91 / +2.80 / -0.24**),
turns the sleeve's eleven-year loss into roughly zero, and **halves the drawdown from 69.6% to
40.2%**. It is the best cell on the page and it is still refused, on three grounds that matter
more than the headline: clause 2 is **1 of 3** and the sign **flips in the most recent regime**,
clause 4 is 0 of 3, and +$81/day on a $1M book is 0.2 bps a session - indistinguishable from
zero at t +0.25. What it is *not* is a trade-reduction artifact: turnover is **35.1 against 34.9
trades/day** and costs *rise* ($998 vs $913), so `stop300`/`stop368` are exempt from clause 3 and
both pass it trivially. Tightening the stop is unambiguous in the other direction:
**`stop120` loses -$630/day paired at t -5.27**, the largest and most significant number in the
whole study, on 50.2 trades/day - the stop is a cost, and the shipped 240 is 5 minutes of
arbitrary history sitting two cells away from the only value that is not.

**Nothing shipped and nothing could.** `live/intraday_config.json` is untouched; no shipped,
runner-loaded or scheduled-task file was modified, so no `--replay` or `compare_orders.py` is owed
(AGENTS.md rule a). The sleeve already runs at `equity_frac` 0.25 as a plumbing test because
A-10/A-11 found it negative in every regime, and A-8 does not change that: the best window this
grid can build is a book at t +0.25. **A-8 was the last A-track item with a stated mechanism and a
permitted instrument, so the honest report is the one the Current objective asked for - the ORB
sleeve cannot be validated on 2,686 sessions by moving its windows.** The reusable rule is that
**an event study on round trips cannot price a parameter that decides which round trips exist**:
the entry-bucket table pointed at a cell that turned out to be the second-worst on the page, and
the exit table pointed away from the only cell that moved the book, both for the same reason.

## 2026-09-12 - S-38 / AUD-11 part 2 (`daily` track; full entry in `research/journal_daily.md`)

**S-33 called its +0.974 a floor because five dials were unpriced; run all eight, the estimate
is +1.25 to +2.07 CAR points, and the two axes that carry it are the two with the weakest paper
trail.** `scripts/sweep_s38.py`, seven pre-registered clauses, 123 unique books, no LEAN run and
nothing shipped. Clause 4 was meant to be a formality and became the first finding: S-33's three
axes re-ran to **+0.877 / 65th percentile** until two unstated counting conventions were
recovered - count the shipped cell **once** (7+6+7 = 20 cells is **18 unique**) and rank
**inclusively** - after which all five of its statistics reproduce to the third decimal. On all
eight axes the shipped set sits **+2.073 above the 32-cell fitted grid mean** (0.89 sd, 84th
percentile), pre-registered branch (c); restricted post-hoc to the **25** cells that pass
`evaluate.py`'s own drawdown tolerance it is **+1.254**, branch (b). The mechanism is countable:
selection ran on 2012-2026, which *contains* the "OOS" half, and the shipped value is the
**out-of-sample argmax of its own axis on 3 of 6 fitted axes** against 0.99 expected,
Poisson-binomial **P = 0.060**. The two biggest contributors are `regime_vol_window` (**+3.596**,
and the one dial in the whole parameter set with **no selection record anywhere**) and
`regime_threshold` (+3.016) - both halves of the crisis switch, while `mom_skip` is a dead heat
at +0.074. Two by-products: **`target_exposure` is inert** (byte-identical book from 0.875 to
10.0; `scale_cap` binds only below 0.875, so the shipped 1.75 is 2x above the point where the
dial does anything, and it is not the leverage lever it reads as), and **coordinate deltas are
not additive** - the full-period argmax set sums to +8.492 and delivers +4.004 jointly, so any
total built by adding axes overstates ~2x. Fully charged the joint argmax set is *worse on both
axes* (21.707% / DD 40.191% against 25.967% / 24.040%, paired -1.174 bps/day, **t -0.65**).
Nothing promoted, `champion.json` untouched; the relabel it earns is still the manual edit to a
reserved file that S-34 showed no promotion can carry.

## 2026-09-12 - S-37 / AUD-13 (`daily` track; full entry in `research/journal_daily.md`)

**The paper runner answered a broken history frame with `print("warning: no history for ...")`
and carried on, and two bad yfinance prints a year cost the whole selection premium this sleeve
was measured to have.** AUD-13 is three defects in one bullet; each was corrupted into the real
decision frame at the real decision site and run through the deployed book. The loud one -
`REGIME_TICKER` missing, `risk_on` returning `"SPY missing"`, the account liquidated under a
reason that reads like a risk decision - costs **0.138 CAR points per outage at 0 bp and 0.252
at 2 bp**, so the break-even against S-33's 0.5-point "cosmetic" bar is ~~2.0~~ **between two
and four outages a year** (corrected 2026-09-13 by S-39 / C-5b: 2.0 is the 1-in-21 cell, which
runs at 11x the rate the sentence describes; the matching 0.93/yr cell gives 2.6 at 2 bp and
3.6 at 0 bp) against a pre-registered threshold of 12 (t 3.10 / 3.85 on the powered cells; the
low-rate cells are underpowered at t 0.90 / 1.24). The MATERIAL verdict is unchanged. The silent one is worse-behaved than the audit says:
an all-NaN column changes the funded set on **10.5% to 83.6% of corrupted sessions for every
one of the nine names**, and no CAR delta clears the 1.689 seed sd - the defect is noise in the
portfolio, not a bias, which is why refusing is the only available remedy. XLK, the audit's
example, ranks third. The stale-price defect is real only in its sizing half: **29.70% of
name-days move more than the 1% no-trade band** and p95 is 2.441%, while *ranking* on a stale
close is worth ±0.1 CAR points, i.e. nothing. The remedy's own tail test was the interesting
part: holding yesterday's book is 11x cheaper than the spurious flatten (-0.209 vs -2.338 CAR)
but shows **+0.602 worse MaxDD against it** - because the flatten's drawdown is *below the
control's*, random liquidation being accidental de-risking. Against the control, which is the
book the runner exists to reproduce, holding costs **+0.046** drawdown points. Shipped:
`data_faults()` + `previous_session()` in `paper_trade.py`, called before `call_signal` so a
fault cannot become an order, with the predicate measured at **0 false positives on 3,690
sessions** before it was written. `signals.py` deliberately untouched. Identity exact,
`compare_orders` **3,689/3,689**, suite 593, launch preflight green. Files **AUD-13b [eng]**:
`CALENDAR.trading_days` keeps answering past `coverage_end` from the weekday rule instead of
raising, so only `check_covered` enforces the contract. Reusable rule: **price a remedy against
the thing it is supposed to restore, not against the defect it replaces.**

## 2026-09-12 - S-36 / AUD-25 (`daily` track; full entry in `research/journal_daily.md`)

**The guard whose docstring says it exists so "the horizon is what is being tested" covers one
parameter out of eleven, and the audit named the smaller half of what it leaves open.** Seven
of the eleven integer windows on `Params` are outside `__post_init__`, in two modes:
**SILENT-ZERO** (`trend_window`, `regime_vol_window` - the book sits risk-off for the whole
sample and prints a tidy 0% CAR, which is the audit's example) and **SILENT-TRUNCATE**
(`alloc_vol_window`, `regime_median_window`, `vol_est_window`, `mom_vol_window`, `trail_window`
- `.iloc[-N:]` yields fewer than N bars, so two different values are the *same cell*; all five
produce byte-identical weights at `history_bars + 100` and at `+ 500`). The second mode is not
in the audit and is the worse one, because it manufactures a flat parameter **shelf**, which is
exactly the artefact S-33 taught this track to treat as its strongest evidence. Fixed by taking
`need` over every price window; `iv_scale_window` is excluded with its reason (it reads the IV
store, not `prices`, and already fails loudly). Of the other five claims: the `ML_MODE="rank"`
double gate is real, reaches **10.79% of sessions**, and is worth **+0.286 CAR points** - it
*helps*, so the docstring was fixed and the code kept, and S-27's twelve ranked rows are
flattered by it rather than penalised; the **S-3 harness claim has the wrong sign** (the
close-to-close convention *costs* that book **3.291 CAR points**, 2.559% against 5.851% at zero
cost, because a reversal signal is on the losing side of the overnight gap - though at the
harness's own 5 bps both conventions are deeply negative, so S-3's refusal on cost stands);
`minimum_order_margin_portfolio_percentage` is confirmed **inert** on the `market_order` path
(17 LEAN call sites, none of them it) and labelled rather than removed; `blended_momentum` has
zero AST references but is the written spec `sweep_f3.py:432` points at, so it is kept; and
`--history ib` is **unreachable from the deployed task**, so it is filed as **AUD-25b** for
`eng` rather than fixed here. Identity exact (22.192150170492255% / 5,052), `compare_orders`
**3,689/3,689 PASS**, suite **615**. Adds no research item, closes the last `daily`-owned audit
item, files one `eng` item.

## 2026-09-12 - D-4 / AUD-16 (`iterate` track)

**The IBKR minute store had not advanced since 2026-09-11 12:35 ET and could not, because the
fetcher's two defects hid each other: it wrote a truncated session, then counted that session as
present and refused to request the month again. Both fixed, the store repaired against the live
gateway (16 symbols, +3,483 bars, E-6 now reports 0 fail / 0 warn), and the thing the truncated
session was worth is not in its P&L - it is 27% of the day's trades and a replay that ends with
14 open positions.**

`scripts/sweep_d4.py`, seven clauses pre-registered in its docstring, no ledger row (this is a
data-pipeline fix, not a strategy result), `tests/test_intraday_data_extend.py` (17 tests), suite
**601 pass** (584 before). Nothing under `live/` touched; `live/intraday_config.json` unchanged.

**What was broken.** Both defects are in `scripts/intraday_data.py`, and each one is a decision
the module makes locally before it asks IBKR anything:

| # | defect | fixed to |
| --- | --- | --- |
| 1 | `snap_after_close` clamped its end timestamp with `min(20:00, now)`. During regular hours `now` **is** inside the session, so the clamp re-introduced the exact truncation the function exists to prevent - IBKR truncates the session `endDateTime` lands in | clamped to `last_safe_end`: after the CALENDAR's close plus a 15-minute settle margin `now` is safe, before it the only safe boundary is the previous 20:00. A midday run now fetches nothing for today instead of a third of it |
| 2 | `fetch_symbol` skipped any window with **15 or more sessions on disk**. A count cannot tell a complete month from one missing its last five days, and with 263 sessions stored every window cleared 15, so `--months N` was a no-op for every N | skip only when no CALENDAR session in the window is missing or truncated (`sessions_needed`) |
| 3 | `--repair` iterated the days **on disk**, so a session that was never fetched at all was invisible to it, and the default run did not repair | `incomplete_sessions` spans the calendar, not the store; the default run repairs everything inside `--months` and names what is left older than that |
| 4 | truncation was `n < 390 and n != 210`, which calls every sparse session truncated and passes a 390-minute day stored with exactly 210 bars | `store_health.session_shapes` (E-6's head/tail rule) imported rather than re-drawn |

**Clause by clause.**

1. **Identity: PASS, and it is the withdrawal condition.** A fetcher that re-requests a complete
   store is worse than one that cannot extend it, because it burns the pacing budget the repair
   needs. Measured twice: before the repair 0 of 16 symbols were clean, so the clause was
   vacuous; **after** it, all 16 are clean and the new rule issues **0 requests** for
   `--months 3`, against 3 windows x 16 symbols it could have asked for.
2. **Truncation: PASS, and the old rule fails it badly.** Over 288 five-minute probes across a
   whole day, the OLD `snap_after_close` returned an instant inside a live session on **78** of
   them on a regular day and **42** on an early close; the NEW rule on **0 of 3 x 288**, regular
   day, early close and holiday. The settle margin is added to the *calendar's* close, so it is
   16:15 on a regular day and 13:15 on an early close - a hard-coded 16:15 would have thrown away
   three of the only hours in which a half day can be stored complete.
3. **No-op: PASS.** A `--months 3` run today issues **0 requests for all 16 symbols** under the
   count-based skip while every one of them holds a truncated last session, and **exactly 1** per
   symbol under the new rule, on the window containing 2026-09-11.
4. **Line: PASS, 0 of 16 disagree.** The fetcher's "needs a refetch" set equals
   `store_health`'s truncated-or-missing set symbol by symbol. Two modules that disagree about
   what "complete" means give an operator two answers and no way to choose, which is how the
   2026-09-10 defect survived a `--repair`.
5. **Materiality: 16 (symbol, session) pairs, 3,483 bars.** One session, but *the last* one, and
   `scripts/intraday_launch.py` preflights by replaying the last stored session.
6. **Deploy gate: PASS, and the honest version is narrower than the audit implies.** The preflight
   was **not** broken by AUD-16 - `intraday_launch.last_session()` already skips a truncated day
   on E-6's shape test, so the gate silently fell back to an older session rather than replaying a
   half day. The damage was that the store could not advance at all. What the truncated session is
   worth to a consumer *without* that guard, measured by reconstructing the pre-repair store
   (2026-09-11 cut at 12:25 ET) and replaying it through `intraday_trader.py` on the same $1M base:

   | store | decisions | trades | replay P&L | open at close |
   | --- | --- | --- | --- | --- |
   | truncated | 175 | 146 | **-149,012** | 14 names |
   | repaired | 368 | 215 | **-9,489** | none |

   The research harness is nearly immune, because it flattens on its last bar: **-9,920 against
   -9,418** for that session, +$502 or 5.3%. But it books **158 trades against 215**, so a
   truncated session hides **27% of the day's trading** from research while barely moving its
   P&L - which is exactly why a P&L-only check would have passed it and why E-6's shape test is
   the right instrument. After the repair `scripts/intraday_launch.py --preflight-only` passes and
   replays the full 2026-09-11 (P&L -2,080 on 250,000, 36 trades, 368 decisions, flat at close).
7. **Withdrawal: not triggered.** `--legacy-skip` restores the count-based skip and
   `snap_after_close(..., legacy=True)` the old clamp, both pinned by tests, so D-4's control
   cells are reproducible rather than remembered.

**The repair itself.** `python scripts/intraday_data.py --months 3` against IB Gateway (clientId
61), **6.1 minutes, 16 requests**, one per symbol. Every symbol went 101,990-101,997 ->
**102,210 bars** and `store_health.py --store minute` now reports **16 symbols, 1,635,362 rows,
0 fail, 0 warn -> usable**. A side finding from the reconstruction: the repaired 09:30-12:24 head
is dense at 175 bars for all 16 while the implied pre-repair counts were 170-175, so the dead
fetch had also left **0-5 minutes missing inside its own head** - a truncated fetch is not only
short at the tail.

**What it changes for the loop.** The fetcher's skip and the completeness checker were asking the
same question with different instruments, and the cheap instrument won by default: a bar count is
always available, a calendar has to be imported. Every store this repo keeps (`data/minute`,
`data/minute_alpaca`, `data/options/odte`) has a fetcher with its own idea of "already have it",
and **AUD-24 files the same shape for the events and options caches** ("marked complete when
partial"). The rule D-4 leaves behind: **a fetcher's resume rule must be the completeness
checker's rule, imported, or the store will freeze at exactly the defect the checker was written
to find.**

## 2026-09-12 - A-13 / AUD-21 (`iterate` track)

**All six harness biases fixed, and priced on the book the owner is deciding about: they are worth
+$35/day in the mean (t +0.69, sign-inconsistent across regimes) and 37% in the tail. The audit's
"all in its own favour" is wrong for the biggest of them - the harness was stopping the sleeve out
on 92 of 2,686 sessions the live trader would have traded through, and hiding a worst day $12,551
larger than any A-track table has ever shown.**

`scripts/sweep_a13.py`, seven clauses pre-registered in its docstring, **7 DIAGNOSTIC ledger rows**
under `intraday/active`, `tests/test_intraday_harness_bias.py` (12 tests), suite **473 pass**.
Nothing under `live/` touched; `live/intraday_config.json` unchanged.

**What was broken.** AUD-21 filed six defects in `scripts/intraday_backtest.py` and
`algorithms/intraday/base.py`. Three can move a P&L and three are reporting:

| # | defect | fixed to |
| --- | --- | --- |
| 1 | a pending order whose symbol printed no bar at the fill minute was booked at the **decision bar's own close** - zero latency, at a price that minute never showed - or dropped in silence if the symbol had not printed at all yet | held on the wire until the symbol prints, filled at that bar's open; sizing nets pending exactly as `intraday_trader.py:562` does (AUD-06's live rule, which the harness never had) |
| 2 | the live loss limit is -2.5% of **account NAV**, the harness charged it against **sleeve equity**, so at the deployed `equity_frac` 0.25 the harness stopped the book **4x earlier than live** | `RISK["nav_frac"]` / `--nav-frac`; default 1.0 keeps every earlier row exact, and the harness now **prints a warning** whenever the run's base is tighter than the deployed sleeve's |
| 3 | turnover divided by the equity the book started with | divided by mean equity over the run |
| 4 | drawdown was end-of-day marks only | `max_drawdown_intraday_pct` on the full bar path, reported and recorded alongside the unchanged EOD figure |
| 5 | `--split` recorded `end` on the in-sample row, a window it never ran | `split - 1 day` |
| 6 | bar 0's true range used the **previous session's** close, so every overnight gap was one minute of range and `atr14` was inflated for minutes 4-13 | `close.groupby(day).shift(1)`; `features(df, gap_true_range=True)` reproduces the old one |

**The price, on the deployed ORB book, Alpaca SIP, yearly-reset $1M, shipped costs** (`control` =
the pre-fix harness, `all` = all three money defects fixed at the deployed `nav_frac` 0.25):

| window | n | control $/day | t | corrected $/day | t | paired $/day | t | control worst day | corrected worst day |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2016-2019 | 1,006 | -303.4 | -1.25 | -269.3 | -1.11 | **+34.1** | +3.12 | -26,826 | **-33,445** |
| 2020-2023 | 1,006 | -528.6 | -1.19 | -605.0 | -1.34 | **-76.4** | -1.00 | -30,902 | **-46,850** |
| 2024-2026 | 674 | -132.5 | -0.22 | +71.4 | +0.11 | **+204.0** | +1.22 | -34,300 | **-45,283** |
| **ALL** | **2,686** | **-344.9** | **-1.41** | **-309.6** | **-1.24** | **+35.3** | **+0.69** | **-34,300** | **-46,850** |

**Clause by clause.**

1. **Identity: PASS, and it reconciles to the cent-ish.** The `control` cell is the pre-fix harness
   and should land on A-10's published `orb` row (-$65/day, 674 sessions, 39.1 tr/day, 30 stops,
   $996 costs/day) rather than on the -$132.53 it prints. Sessions (674), trades/day (39.07 vs
   39.1) and stop-outs (30 vs 30) match exactly; the $/day does not, and the gap is entirely two
   commits made **after** A-10 ran (its row is stamped `20260910T084825Z`):
   the sell-side regulatory fees added by `babee70` at 12:02 ET the same day (costs/day 996 ->
   1,041 = **-$45/day**) and AUD-07's calendar-aware flatten `1311586`, isolated by
   `scripts/_a13_flatten_check.py` at **-$20.76/day**. -65 - 45 - 21 = **-131.8 against -132.5**,
   a residual of $0.77/day. Nothing in AUD-21 is responsible for any of it.
2. **Direction: the audit is right about two defects and WRONG about the one that matters.** Fixing
   the fill model costs the book -$1.19/day (paired t -0.82) and fixing `atr14` costs it
   1.9e-11 $/day, both in the harness's favour as filed. Fixing the loss-limit base **improves**
   the measured P&L by +$205.15/day on 2024-2026 and +$35.32/day pooled, because the harness was
   *more* conservative than the live trader, not less. What the defect actually hid is the tail:
   the worst day gets worse in **every one of the three regimes**, by $6,619 / $15,948 / $10,983.
3. **Materiality: one of three.** Against the pre-registered 10%-of-|control| and 0.25-of-t
   thresholds - **fill** 0.9% and Δt 0.002, **not material**; **atr** zero, **not material**;
   **nav** 155% of |control| and Δt 0.330 on 2024-2026, **material**, and on the full history 10.2%
   and Δt 0.170, material on one leg only.
4. **The `atr14` prediction: PASS, and it is the cheapest result here.** `orb` reads `atr14` only
   from minute 15, and a `rolling(14)` at positional index >= 14 no longer contains bar 0 - so the
   defect can only bite where bars are MISSING at the open. Counted directly rather than inferred:
   **0 of 10,784** (symbol, session) pairs on Alpaca 2024-2026 and **0 of 4,208** on the whole IBKR
   store have their opening-range bar at positional index < 14, against **2,992 of 40,078 = 7.47%**
   over the full eleven years, where the store thins out badly before 2020. Under the 10% clause.
   The isolated `atr` cell confirms it: **0 of 674 sessions differ by as much as a cent**, mean
   1.9e-11 $/day - at a paired **t of +1.93**, which is the sleeve's cleanest demonstration that a
   t-statistic without a magnitude beside it is worth nothing.
5. **nav direction: PASS.** Stop-outs 92 -> 0 over the full history (30 -> 0 on 2024-2026) and the
   worst day is not improved anywhere.
6. **Deploy gate: PASS.** `base.py` is loaded by the live trader, so the `atr14` fix is a live
   change. `scripts/intraday_launch.py --preflight-only` passes, and replaying **2026-09-10**
   through `intraday_trader.py` with the old and the new `features` gives the identical session -
   *P&L -3,920 on 250,000, 45 trades, 368 decisions, flat at close* - which clause 4 predicts,
   because the IBKR store has no sparse opening range anywhere in it.
7. **Withdrawal: not triggered.** `--legacy-fills` / `--legacy-atr` / `nav_frac 1.0` reproduce the
   old harness; the two fill models agree to the cent on any complete session, which is pinned in
   `tests/test_intraday_harness_bias.py`.

**Decision: all six fixes shipped, no research verdict overturned, one owner-facing number
corrected.** The eleven-year answer for the deployed ORB book moves from A-10's published
-$289/day to **-$310/day at t -1.24** - the same answer, still short of two sigma, so the open
request in `BLOCKERS.md` is unchanged and no config was touched. The addendum filed there is the
tail: **the live sleeve's real intraday stop is -10% of its own equity, not the -2.5% every A-track
backtest enforced**, and on the eleven-year sample that is worth a worst day of **-$46,850 against
the -$34,300 the owner has been shown**, on a $1M book. Whether the live limit should be charged
against sleeve equity instead is a risk-posture change and therefore the owner's.

**Two reusable rules.** (a) *When an audit says a defect favours the harness, that is a claim about
sign and it has to be measured* - here the largest of the six ran the other way, and the reason is
that a harness bias can be conservative in the P&L column while being reckless in the risk column;
read both. (b) *A defect that is real can still be provably inert*, and the cheapest way to find
out is to count how often its mechanism can reach the code that consumes it - one 40,078-row count
settled `atr14` before any backtest ran, and told us why the answer is 0% on the store the sleeve
trades and 7.47% on the store it is judged on.

**One process note, because it will happen again.** Most of this iteration's harness hunks are not
in this commit: a concurrent `eng` job ran `git add scripts/intraday_backtest.py` mid-iteration and
swept them into **`25d30db` ("a standing data-validation gate...", AUD-13)**, along with 5 of the 7
A-13 ledger rows. Nothing was lost and nothing is wrong in the code - it is now covered by
`tests/test_intraday_harness_bias.py` and the suite is green - but git attributes the AUD-21 fix to
an AUD-13 commit. AGENTS.md's "commit ONLY the files you touched" is not sufficient protection when
two tracks hold edits in the same file at the same time; the rule that would have prevented it is
**stage by path only after checking `git diff --stat` for hunks you did not write**.

**Next:** AUD-16 [data, `iterate` scope] - `scripts/intraday_data.py` cannot extend the store and
truncates the current session (all 16 symbols hold a 170-bar 2026-09-11), which is what keeps the
execution-matched store from reaching A-5 part 2's end condition.

## 2026-09-12 - S-35 / AUD-12 (pointer; full entry in `research/journal_daily.md`)

**One row in the ledger passes the promotion gate today and would put a strategy on the paper
account that the runner cannot trade: it claims +1.914 CAR points and delivers 0.000 of them.**
`main.py` builds its `Params` from `S1_*` environment variables; `paper_trade.py:196` asks for
`getattr(sig, "PARAMS", None)` and `signals.py` defines `DEFAULTS`, so the runner always trades
the defaults; `compare_orders.py:158` builds `sig.Params()`, so the deploy gate compares the
defaults with the defaults and agrees with itself; and `--promote` recorded no `env` at all.
`scripts/sweep_s35.py`, seven clauses pre-registered, prices it on the real row `20260911T184723Z`
(S-20's defensive off-state at 2 bp), which returned `(True, [])` from `verdict()` before the
patch. Identity exact on the union price frame (22.192150170492255% / 5,052). The reach surface,
re-derived from `main.py` by AST: **56 `S1_*` names, 49 of which reach the shared signal path and
7 of which do not** - so the fix has to be an allow list, and `S1_PROXY` (which mutates a
`signals.py` global rather than a `Params` field) is why it cannot be derived from the `Params(...)`
call. Of 167 `s1_momo` rows, 15 carry a reaching key - a **floor**, since `env` recording only began
with S-18 - and 1 passes. What the account gets: the promoted book and the runner's book **hold
different things on 13.6% of sessions** (the runner flat on 590 of 3,689 against the promoted
book's 87), paired
+0.51 bps/day at t +0.47, and in LEAN's column the promotion moves the champion from 23.068% to a
claimed 24.982% while the account keeps trading 23.068%. **Second order, and larger: 11 of the 167
rows then flip from "beats" to "does not"** against a bar no deployed book can reach - AUD-10 handed
a candidate slack it had not earned, AUD-12 denies the account improvements it had. Fixed in two
independent halves (`param_env_note()` candidate-side, `champion_env_note()` reader-side) plus
`--promote` now recording the run's `env`; the audit's second remedy (plumb the env into the runner
and the gate) is **refused on merit** - it would widen the deployed surface to buy a capability
nothing asked for, and a parameter worth shipping belongs in `signals.py`'s defaults. Withdrawal
condition holds: 167 rows re-judged, **exactly 1 verdict moved, `yes -> no`, on the tainted row**,
0 the dangerous way and 0 on a clean row; suite **543 pass**; `champion.json` untouched. No LEAN
run, no ledger row, no live-runner edit (clause 7 pins that invariant with a test instead of
patching `paper_trade.py`). Adds no research item and closes one audit item. Next daily audit item
that needs no trading day: **AUD-25**.

## 2026-09-12 - S-34 / AUD-10 (pointer; full entry in `research/journal_daily.md`)

**The promotion gate hands the next candidate 4.2 points of drawdown slack, and 15 rows already in
the ledger would take it.** `evaluate.py --promote` wrote `stats` and never touched
`stats_by_spread`, which `champion_stats()` prefers - so the first candidate judged after any
promotion was compared against the book that had just lost. `scripts/sweep_s34.py`, seven clauses
pre-registered, prices it on the real S-12 -> S-18 promotion: the CAR gap is **-0.001 at 0 bp**
(harmless, the dead heat S-18 reported) and the damage is entirely in risk - **+1.400 and +4.200
points of drawdown headroom** at 0 and 2 bp, against a `drawdown_tolerance_points` of **1.0**.
Replaying all 167 `s1_momo` rows, **15 flip and all 15 in the dangerous direction**, including
five S-16 budget-0.80 cells (`20260911T120010Z`: 26.474% / 1.012 / DD 25.700%) that clear the
retired ceiling and breach the champion's - live candidates, since S-31 re-priced that budget the
same day. Fixed in two independent halves: `promoted_columns()` makes the promoted run the only
cost column, and `stale_note()` refuses every comparison when no column carries the champion's own
`run_dir`, catching a bad file however it got there. The audit's one-line fix ("delete the others")
would have destroyed the **11 dated `*_note` keys** that share that dict - the S-21..S-33 research
record - so columns and notes are now separated by `cost_columns()`; notes are preserved
byte-identical. Backward compatibility was the pre-registered withdrawal condition and holds:
**167 verdicts compared, 0 changed**, table output byte-for-byte identical, suite **241 pass**,
`champion.json` untouched. One finding beyond the audit: `--promote` never writes `note` either,
which is where AUD-11's wrong OOS label lives, so **AUD-11's filed remedy ("have the next
promotion carry this replacement") cannot work** and is corrected in the backlog. Next: AUD-12,
the same shape - a promotion that does not carry the `env` the champion was run with.

## 2026-09-12 - S-33 / AUD-11 (pointer; full entry in `research/journal_daily.md`)

**The champion's "OOS 2020-2026" label is wrong and its number is not - and the audit's own first
remedy would have cost 1.87 CAR points at t -2.18.** The operator's audit filed AUD-11 [daily]:
every shipped parameter was chosen on full-period tables, so the published OOS is a sub-period of
a fit. Correct as a matter of record; what it did not say is what the contamination is worth.
`scripts/sweep_s33.py` re-does the selection with 2020-2026 genuinely withheld - three axes copied
verbatim from the `signals.py` docstrings that record how each shipped value was chosen, seven
clauses pre-registered, **60 DIAGNOSTIC rows** under `daily/s33_oos`, **no shipped or
runner-loaded file touched**, identity exact at 22.192150% / 5,052. Three findings. (1) **The
shipped set is not even the full-period argmax** - `mom_skip=10` beats the shipped 5 by 0.485 on
the window the choice was made on and was not taken, exactly as S-10's docstring says. (2)
**Re-selecting on 2012-2019 is refused**: it moves one axis, `alloc_vol_window` 21 -> 10, which is
the *worst* of that axis's six cells out of sample, costing **-1.865 CAR points, -0.569 bps/day,
t -2.18** - past |t| = 2 and the first non-arithmetic statistic on this sleeve to get there. (3)
**The contamination itself is about half a point.** Against the 18 unique cells the shipped set
sits +0.974 above the grid mean (0.53 sd, 78th percentile) and +0.492 above the median, under the
pre-registered 0.5 threshold for "cosmetic". The reason both (2) and (3) are true is one number:
the **selection premium is -0.049 CAR points** pooled over 20 cells - the IS top three cells
average 28.420 OOS against the IS bottom three at 28.283, and the single global IS-argmax lands
*below* the grid mean. Choosing a parameter on this sleeve's first half tells you nothing about
its second, which is why there was nothing to inflate the published figure with and nothing for a
re-selection to select on. Honest fully-charged (cell C) withheld half: **shipped 25.967% /
1.151 / DD 24.040**, grid band ~20.0..27.7%. Decision: AUD-11's re-select branch **refused**, its
relabel branch **adopted** and now quotable at ~0.5 CAR points; the champion.json label edit is
**owed, not taken** (AGENTS.md reserves that file to `--promote`, and AUD-10 should be fixed
first), with the exact replacement text filed under AUD-11 in the backlog. The reusable rules: on
this sleeve a parameter *shelf* is worth reporting and a parameter *argmax* is worth nothing, and
when an audit names a defect and a fix they are two claims - here the finding was right and its
first remedy was the expensive one.

## 2026-09-12 - S-32 (pointer; full entry in `research/journal_daily.md`)

**The no-trade band, re-priced on the honest book: keep 0.01, and the 2026-09-09 conditional
resolves to "not material".** S-31's rule applied to the second open owner decision - both
standing jobs ran first and, it being a Saturday, neither has new input (`daily_fills.py`: 10
fills / $2.37M / **+3.2 bps**, se 4.5). `scripts/sweep_s32.py`, seven clauses pre-registered, 55
DIAGNOSTIC rows under `daily/s32_band`, **no shipped or runner-loaded file touched** so no deploy
gate and no replay owed; identity exact at **22.192150% / 5,052** and **19.640168% / 1.047 / DD
24.037**. The pre-registered premise - a band buys back spread, so its gain must grow with the
spread charged - **holds** for the winning band 0.080 (+0.380 / +0.391 / +0.450 / **+0.519** at
0 / 1 / 2 / 3.2 bp), and by `champion.json`'s own criteria five bands pass the decision cell
including the owner's 0.03. It is still refused, on three numbers that all say the CAR column is
measuring the path and not the mechanism: the **spread-attributable** part of band 0.080's +0.544
is **+0.139** (monotone in the band across the whole grid, unlike the gain itself, which zig-zags
+0.090 / +0.013 / +0.313 / +0.544 / +0.206); the **arithmetic ceiling** on the prize at the
measured 3.2 bps is **0.155% of equity a year**, so the claim is 3.5x larger than the mechanism
can produce, and it agrees with the +0.139 to 0.016 points; and the **placebo** - the same 67.5%
of orders removed at random - returns -0.176 mean with **sd 0.791**, one seed of five beating the
band outright (permutation p = 0.33) while swinging drawdown 20.26-28.10%. Paired t +1.96 full
period, +1.35 IS / +1.74 OOS. The owner's named 0.03 is the local worst of the five passing bands
(+0.013, t +0.12, worth **0.067%/yr**). `BLOCKERS.md` item 4 gets a priced addendum; the live
order list stays on `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`.

## 2026-09-12 - S-31: the owner's size decision was priced on a book that does not exist - half the gain is not there, and the Sharpe argument for it reverses

**Why this iteration exists, given that the backlog says to stop finding levers.** It does not add
a seventh owner decision; it re-prices the largest of the six. Both standing measurement jobs ran
first and, this being a Saturday, neither has new input: `slippage_report.py` still reads 66 fills
/ **+2.22 bps** / se 0.80 / |diff|/se 0.90 (~4.4 sessions from settling), and `daily_fills.py`
still reads 10 fills / $2.37M / **+3.2 bps** (se 4.5) with `ref_price` the previous close 10 of 10.
With no research item left that has a stated premise and a permitted instrument, the highest-value
thing the loop can do is make the binding constraint - the `margin_budget` question open in
`BLOCKERS.md` since 2026-09-10 as options (a)/(b)/(c)/(d+) - answerable on the right numbers.

**Hypothesis.** Every table the owner has been shown for that decision is on a book that pays none
of the three costs this repository has since measured. S-16's frontier (0.75/0.78/0.80/0.82 ->
24.403 / 25.307 / 25.903 / 26.474) is LEAN at zero spread, zero financing and the backtest's clock;
S-21's (23.087 / 24.296 / 24.742) charges financing only. S-22 then established that the deployed
book charged all three earns **19.640%, not 24.403%** - the headline is ~18% high. The claim S-31
tests is that **the correction to this particular decision cannot be a parallel shift**, because
the financing drag is proportional to the debit balance and the spread bill to turnover, and a
larger budget raises both. If so, the *gain* from spending the Reg-T buffer is smaller than
advertised by a predictable amount, and it can be quoted.

**Method.** `scripts/sweep_s31.py`, seven clauses pre-registered before the first number, 37
DIAGNOSTIC ledger rows under `daily/s31_budget`. **No shipped or runner-loaded file was touched**
(the budget is already an ordinary `Params` field and an `S1_MARGIN_BUDGET` override), so **no
deploy gate and no replay is owed**. Eight budgets - 0.70 / 0.75 / 0.78 / 0.80 / 0.82 / 0.85 /
0.90 / 1.00, run to the Reg-T corner rather than to a chosen stopping point - in four cost cells:
**(A)** the backtest convention at zero cost, S-16's scale; **(B)** the deployed 15:45 convention
at zero cost, S-19's scale; **(C)** the deployed convention charged 2 bp of one-way spread and
IBKR Pro financing on the historic effective fed funds rate; **(D)** the same at today's 3.63%.

**(1) Identity, to the digit.** Budget 0.75 reproduces the deployed cell at **CAR 22.192150% /
5,052 orders**, and its fully-charged cell lands on **19.640168% / Sharpe 1.047 / DD 24.037%**,
the figure S-22, S-26, S-28 and S-30 each quote independently. The dial sizes the book; it does
not change it.

**(2) Calibration, because the decision is selected on drawdown and this is a pandas harness.**
Pre-registered limits: the harness's drawdown error against LEAN may not exceed 2.0 points at any
budget, nor grow by more than 1.0 point between them. Scored on the backtest-convention cell
against LEAN rows, including **one new LEAN run at the budget clause 6 would go on to select**
(`20260912T130734Z`, 5,587 orders, `OrderListHash 7352a42d118919eec701e44af7a4dfff`):

| budget | LEAN CAR / DD | harness CAR / DD | CAR error | DD error |
|---|---|---|---|---|
| 0.75 (champion run) | 24.403% / 23.700% | 24.077% / 23.258% | -0.326 | **-0.442** |
| 0.80 (S-16) | 25.903% / 25.100% | 25.531% / 23.965% | -0.372 | **-1.135** |
| **0.90 (new)** | **28.796% / 27.900%** | 28.377% / 26.606% | -0.419 | **-1.294** |

**PASSES**, and the sign matters: the harness is optimistic on drawdown and grows more so with
size, which is exactly the bias that would make a too-large budget look safe, so every drawdown
below is quoted with the measured error added back. Two conventions are *not* comparable between
the two engines and are never compared here: LEAN's Sharpe subtracts a risk-free rate and its
reported `Annual Standard Deviation` is on a different basis (0.155 against the harness's 0.187 at
the same cell). Only drawdown and CAR are read across engines.

**(3) The frontier.** Full period, 3,689 sessions:

| budget | A backtest 0bp | B deployed 0bp | **C deployed costed** | D deployed today | DD (C) | mean gross | mean debit |
|---|---|---|---|---|---|---|---|
| 0.70 | 22.578 | 20.814 | 18.663 | 18.311 | 23.728 | 1.17x | 0.33x |
| **0.75 (shipped)** | 24.077 | 22.192 | **19.640** | 19.102 | 24.037 | 1.25x | 0.41x |
| 0.78 | 24.954 | 22.981 | 20.198 | 19.530 | 24.272 | 1.30x | 0.46x |
| 0.80 | 25.531 | 23.458 | 20.533 | 19.780 | 24.475 | 1.33x | 0.49x |
| 0.82 | 26.093 | 23.955 | 20.897 | 20.061 | 24.619 | 1.36x | 0.52x |
| 0.85 | 26.956 | 24.705 | 21.408 | 20.455 | 24.780 | 1.41x | 0.57x |
| 0.90 | 28.377 | 25.889 | 22.212 | 21.093 | 25.027 | 1.49x | 0.65x |
| 1.00 | 31.129 | 28.222 | 23.818 | 22.288 | 27.653 | 1.64x | 0.80x |

Cell A reproduces S-16's *gain* independently: LEAN gives +1.500 CAR from 0.75 to 0.80, the
harness +1.454.

**(4) THE RESULT: about half the advertised gain is not there, and the haircut is stable across
the whole frontier.** Gain over the shipped 0.75, by cell:

| budget | A gain (what was shown) | B gain | C gain | **D gain (what you get)** | survives |
|---|---|---|---|---|---|
| 0.78 | +0.877 | +0.789 | +0.558 | **+0.428** | 49% |
| 0.80 | +1.454 | +1.266 | +0.893 | **+0.679** | 47% |
| 0.82 | +2.017 | +1.763 | +1.257 | **+0.959** | 48% |
| 0.85 | +2.879 | +2.513 | +1.767 | **+1.353** | 47% |
| 0.90 | +4.301 | +3.697 | +2.572 | **+1.991** | 46% |
| 1.00 | +7.052 | +6.030 | +4.178 | **+3.186** | 45% |

So `BLOCKERS.md`'s "one constant buys +1.55 points of CAR" is, on the book the paper account
actually runs, **+0.68 points**. The haircut decays gently with size (49% -> 45%) because the
financed debit grows faster than the return does. **The CAR ordering does not reverse anywhere**:
more budget still buys more return, monotonically, in all four cells. Clause 4's expectation of a
quarter-to-half shrinkage was right at the top of its range.

**(5) AND THE SHARPE ARGUMENT REVERSES, WHICH IS THE HEADLINE.** The strongest single sentence in
the case for (d+) is S-18's and S-21's observation that Sharpe *rises* with size on the unlevered
book. It does not:

| budget | A backtest 0bp | B deployed 0bp | **C costed** | **D today** |
|---|---|---|---|---|
| 0.75 | 1.247 | 1.159 | **1.047** | **1.023** |
| 0.80 | 1.246 | 1.156 | 1.036 | 1.004 |
| 0.90 | 1.244 | 1.150 | 1.016 | 0.975 |
| 1.00 | 1.246 | 1.148 | **1.003** | **0.952** |

**It is not a Sharpe-convention artifact**, which is the obvious objection since these are raw
ratios and LEAN's subtract a risk-free rate. Recomputed as excess-return Sharpe at the sample's
own mean effective fed funds rate (**1.6924%**), cell A **rises 1.156 -> 1.176** from 0.75 to 1.00
- i.e. it *reproduces* S-21's argument, and LEAN's own runs say the same thing directly (0.994 at
0.75, 1.008 at 0.80, **1.032 at 0.90**) - while cell C **falls 0.957 -> 0.933** and cell D, at a
3.63% cost of money, **falls 0.830 -> 0.802**. The convention is what made the cost invisible:
subtracting a fixed rate from a numerator while the denominator grows manufactures a rising Sharpe
out of a flat one. **Spending the buffer buys return. On the deployed book it no longer buys
risk-adjusted return - it is a pure leverage lever now, and it should be argued for as one.**

**(6) Halves, and an honest reading of a statistic that finally clears |t| = 2.** On cell C the
paired difference against 0.75 reaches **t +2.35 to +2.40 in 2012-2019 and +2.00 to +2.18 in
2020-2026, at every budget above 0.75** - the first thing on the daily sleeve to pass 2 sigma in
both halves. **Read it for what it is**: a budget change is a scaled version of the same book, so
the paired residual variance is nearly zero and the test is measuring the significance of
arithmetic, not of an edge. What it does establish is that the *sign* is not sample-dependent. The
OOS half is where the size is worth most in absolute terms (0.90: 28.749% against 25.967%).

**(7) Option (c) answered in advance - and the cap the owner was told is binding is not.**
`BLOCKERS.md` offers "name a drawdown and the loop solves for the budget". On cell C with the
clause-2 error added back:

- **drawdown <= 25%** -> budget **0.70**, i.e. *below* the shipped 0.75, whose own adjusted
  drawdown is 25.2%. Costs -0.98 CAR points.
- **drawdown <= 30%** -> budget **0.90** (adjusted DD **26.3%** using the measured -1.294 at that
  exact budget), worth **+2.57 CAR points** historically and **+1.99** at today's cost of money.
- **drawdown <= 35%** -> **also 0.90**, because nothing between 0.90 and 1.00 is Reg-T-clean.

**The 35% absolute limit is not binding on this decision anywhere.** The constraint that binds is
Reg-T: mark-to-market gross peaks at 1.88x at budget 0.90 and **2.12x at 1.00**, over the 2.0x
ceiling. (Decision-time gross is capped at 2.0 by `max_gross_weight`; the 2.12 is drift between
rebalances - the daily-book version of the 1.034x `GROSS_HARD_CAP` peak I-2 found intraday.) And
the reason the cap stopped binding is **S-18**: S-6 measured budget 1.0 at a 35.4% drawdown on the
3x-proxy book, while the unlevered book that replaced it reaches ~30% at the same budget. Retiring
the proxies moved the whole frontier inside the risk mandate, so the only thing still holding the
budget at 0.75 is the excess-liquidity buffer - which is a risk-posture preference, and the
owner's.

**Decision: nothing promoted, nothing shipped, no default changed.** `margin_budget` stays 0.75,
every row is tagged DIAGNOSTIC and not promotable, `live/*` and all three scheduled tasks are
untouched. A size decision is the owner's under AGENTS.md and this iteration's purpose was to make
it answerable, not to answer it. `BLOCKERS.md` gains the four-cell table and the inverse solve;
`champion.json` gains a `budget_note`. **The loop is not recommending a move** - on the honest
numbers the case is "+0.68 CAR points at 0.80 for 0.05 of your excess liquidity and 0.019 of
Sharpe", which is materially weaker than the case that was on the page this morning.

**What it changes for the loop.** The reusable rule is that **a cost correction measured on the
champion does not transfer to a decision about the champion's size** - the three costs are
independent of each other (S-22) but none of them is independent of leverage, so any lever that
moves the debit balance or the turnover has to be re-priced rather than shifted. Everything in
this repository that was quoted at zero financing and compares two *different-sized* books is
suspect by the same argument; the two that matter are already listed in `BLOCKERS.md` (S-26's
half hedge and S-28's vol estimator), and both were priced fully charged, so nothing else is owed.

## 2026-09-12 - I-2: the end-of-session assertion pass, validated by reproducing both live defects on the day they happened

**Hypothesis.** Not a strategy hypothesis - the top of the backlog is now two standing
measurement jobs and this one ops item, because S-30 closed the last research item with a stated
premise and a permitted instrument. The claim I-2 makes is operational and falsifiable: **the two
live defects of the deployment window each left a signature in `live/log/*.jsonl` on the day they
happened, so a log-only assertion pass would have caught both within the session rather than at
the next review.** Those defects were (a) the S-18 TQQQ orphan - the daily runner treating a name
the champion had stopped targeting as "foreign" and leaving 3,227 shares in the account after the
15:45 rebalance, fixed in `c34ff7b`; and (b) the intraday book's closed P&L, costs and trade count
not resetting on session rollover, which would have tripped the -2.5% loss limit about $6.8k
early, fixed in `c16cca4`. Both were found by reading logs by hand, days late. With
`live/alerts.json` still missing (BLOCKERS.md item 2) the log files are the only alert surface
this repository has, so the test of the hypothesis is whether a script can turn them into a
verdict.

**What was built.** `scripts/session_audit.py` - 21 assertions over `live/log/<date>.jsonl` and
`live/log/intraday-<date>.jsonl`, one page of output, a single rolled-up verdict and an exit code
(0 PASS / 1 WARN / 2 FAIL) so a wrapper can act on it. `--all` audits every date on disk,
`--json` writes `live/log/audit-<date>.json`. It reads logs and nothing else: **no IBKR
connection, no order, no write outside the optional artifact**, and **no shipped, runner-loaded or
scheduled-task file was touched**, so no deploy gate and no replay is owed under AGENTS.md rule
(a). The two defect signatures are encoded directly. For (a): post-`c34ff7b` the runner's
`foreign` set is exactly the intraday sleeve's universe and that sleeve is flat by 15:38 ET, so a
`foreign_positions_ignored` event at the rebalance can only mean either the intraday book did not
flatten or the fix regressed - and the check names which, by testing the skipped symbols against
`intraday_common.UNIVERSE`. For (b): one `fill` event is one book trade, so if a snapshot's trade
count runs ahead of the fills logged by that timestamp, yesterday's book leaked into today's P&L
and the loss limit is being measured against the wrong number.

**Result - the pass reproduces both defects and raises no false alarm on the other three days.**
Run over every session log on disk:

| date | verdict | fail | warn | pass | what failed |
|---|---|---|---|---|---|
| 2026-09-08 | PASS | 0 | 0 | 0 | pre-deployment, 11 mock runs, nothing to audit |
| 2026-09-09 | WARN | 0 | 3 | 5 | - |
| 2026-09-10 | WARN | 0 | 5 | 12 | - |
| 2026-09-11 | **FAIL** | **2** | 5 | 12 | `daily.no_foreign_positions`, `intraday.pnl_reset` |

The two 2026-09-11 failures are the two known defects, quoted by the script in their own terms:
`positions ['TQQQ'] left alone - ['TQQQ'] are NOT intraday-sleeve names (the S-18 orphan
signature)` and `2026-09-11 09:30:00-04:00: trades 32 > 0 fill(s) logged by then` - 32 being
exactly 2026-09-10's fill count carried across the rollover. Both fixes are in the shipped runners
already, so these two rows are now **regression guards**, not open defects.

**Four false positives were removed by reading the code rather than loosening a threshold**, and
each correction is a fact about the runners worth keeping. (1) `effective_exposure` is **not** a
limit: it was 1.7363x on 2026-09-10 and 1.7669x on 2026-09-09 against a 1.50x notional gross,
because a 3x proxy carries three units of economic exposure per unit of notional at 0.333 of the
margin - which is S-18's whole point. The single shipped ceiling is `margin_used <= 0.75`, which
held on every live plan, so the assertion moved there and exposure gets a loose 2.30x runaway
alarm plus an INFO line. (2) A `connect_failed` only costs a session if no live plan follows it;
2026-09-09 and 2026-09-10 carry six each from manual attempts while IB Gateway was down and the
scheduled rebalance went through both times. (3) A live plan that wants orders and logs none is a
`--dry-run` outside the 15:40-15:50 ET submission window and a lost session inside it - the
2026-09-09 13:48 UTC plan is the former. (4) Dates before the first real fills (daily 2026-09-09,
intraday 2026-09-10) have no session to lose, so "no live plan" is INFO there, not FAIL.

**One genuinely new finding, and it is not a defect.** On 2026-09-10 the intraday book's
mark-to-market gross peaked at **$818,518 = 1.034x the $791,280 `GROSS_HARD_CAP`** (1.6x of
$494,550 sleeve equity) on 14 names - 1 of 15 snapshots across both live sessions over the cap,
max 1.034x. The cause is structural rather than a breach: `targets_to_orders` applies
`GROSS_HARD_CAP` to the **target weights at decision time**, while the snapshot marks the book to
market a minute or more later, and `MIN_CHANGE` deliberately leaves a name alone until it drifts
2% of sleeve equity. The implied per-name drift at that peak is **0.0025 of sleeve equity against
the 0.02 band** - eight times smaller than the slack the trader is designed to carry. It is also
**not a live-vs-backtest divergence**: `intraday_backtest.py` caps targets the same way from the
same constants, so the harness already prices this drift. And the binding external constraint has
room - total notional was ~2.09x of NAV on 2026-09-10 (daily 1.2637x + intraday 0.827x) against
4x day-trading buying power. So it is recorded, the check reports it as a WARN naming the band,
and **the trader was not changed** - there is no evidence a change is warranted and rule (a) would
require a replay for one.

**Standing jobs, both run first, both with no new input** (Saturday, so unchanged from
2026-09-11's close). A-5 part 2: 66 fills over 2 sessions, **+2.22 bps** notional-weighted, se
0.80, `|measured - shipped| / se = 0.90` against the shipped 1.50 - the harness is optimistic by
0.72 bps and the two are still **not distinguishable at 2 se**, which needs ~145 fills, i.e. ~4.4
more sessions at 33 fills/session. `intraday_common.SLIPPAGE_BPS` unchanged. S-17 part 2: 10 fills
over 3 sessions, $2.37M traded, **+3.2 bps** against the auction the runner aimed at (per-fill sd
14.1, se 4.5), and `ref_price` was the previous close in **10 of 10**.

**Decision.** Ship the script, change nothing else. Champion unchanged at S-18, `live/*`
untouched, all three scheduled tasks untouched, no default moved, `champion.json` not edited (this
iteration produced no strategy number). The pass is validated by the only test that matters for an
alert - it fires on the two real defects and stays quiet on the three clean days.

**Next.** The audit currently runs when the loop runs. Wiring it to fire at ~16:00 ET from its own
scheduled task is the ops step that would make it an actual alert surface, and that needs the
owner (AGENTS.md bars the loop from touching the scheduled tasks) - filed in `BLOCKERS.md` beside
item 2, whose `live/alerts.json` credential would let the same verdict be pushed rather than
polled. Beyond that the backlog is down to the two standing measurement jobs, and A-5 part 2 is
~4.4 sessions from settling the intraday sleeve's slippage constant, at which point the Current
objective's own instruction applies: say the sleeve cannot be validated and hand the owner
BLOCKERS.md item 6 (b), rather than look for a twelfth lever.

## 2026-09-12 - S-30: the leg split's equity route is priced and refused on COST, and the delta book it was built on does not exist

**Hypothesis.** The backlog's top item, and the last untried route in the leg-split program.
S-25 measured that 94% of the deployed daily book's return and all of its measurable alpha is
earned overnight (+8.103 bps/day at t +6.80 against +0.738 intraday at t +0.47; same-gross
selection excess +3.087 at t +4.20 against -0.314 at t -0.37) while 61% of its variance sits in
the intraday leg that pays nothing. S-26 tried to remove that leg with a futures overlay and was
refused on **drawdown** at a breakeven 2.3x above its instrument's cost; S-28 tried to re-measure
it and was refused by 0.027 CAR points. S-30 asks the one question left: shed the intraday leg in
the **equity book** - sell a fraction `h` of the carried position at the open, hold none of it
through the session, let the deployed close rebalance buy it back - and relever the freed
variance. If it paid it would be the only construction on file delivering S-26's risk reduction
with **no futures, no owner consent and no Reg-T decision**, i.e. it would move a refused-on-risk
result into the loop's own authority.

New `scripts/sweep_s30.py`; **18 ledger rows** under `daily/s30_delta`, every one DIAGNOSTIC;
**seven clauses pre-registered**, no post-hoc column. The mechanism is a fourth default-inert
argument on the research harness - `flat_frac` on `sweep_s25.legs_simulate`, S-26's `hedge=` /
`scale=` and S-28's `diag_out=` precedent - read only when `mode="both"` and ignored at 0.0. **No
shipped or runner-loaded file was touched**, so no deploy gate is owed: the edit is confined to
`scripts/sweep_s25.py`, which nothing in `live/` or `algorithms/` imports.

**(1) Clause 1, two identities, both exact.** `flat_frac=0.0` reproduces the deployed cell to
the digit - **CAR 22.192150% / 5,052 orders**, the figure S-25 through S-29 each landed on - with
the leg+cost residual at **5.33e-16 of equity**. And `flat_frac=1.0` reproduces
`mode="overnight"`'s overnight leg on **3,689 of 3,689 sessions at a maximum absolute difference
of exactly 0.000e+00**.

**(2) Clause 4 first, because that second identity refutes the premise the item was built on.**
The backlog item's case for re-opening S-25's refusal was that S-25 had priced an overnight-only
book as *a full round trip on every name every session*, and that a "delta" version routed
through the deployed rebalance would be cheaper. **It is not cheaper. It is the same book, to the
cent.** A book that holds **nothing** through the session has no delta at the **open** - the
whole carried position must go, there is nothing to net it against - and at the **close** the
reload *is* the rebalance, so there is nothing to net there either:

| book | CAR% | Sharpe | MaxDD% | turn x/yr |
|---|---|---|---|---|
| S-25 `mode="overnight"` (liquidate and reload) | 14.432 | 1.234 | 19.972 | 630.4 |
| S-30 `flat_frac=1.0` (through the rebalance) | 14.432 | 1.234 | 19.972 | 630.4 |

The delta routing saves **0.0x equity/yr, 0.0%**, against the pre-registered 10% threshold.
Clause 4's premise is **REFUTED** and written down as refuted. One correction does survive it:
S-25's printed **1,248x** was not growth-normalized (S-26's defect), and the same book normalized
turns over **630.4x**, exactly 2 x the book's 1.2496x gross - a factor of 2.0x.

**(3) Clause 3, what is sold before what is bought - and at zero cost the construction does
exactly what S-25 and S-26 say it should.** It sells a drift it cannot measure (+0.738 bps/day at
t +0.47) and buys a variance reduction it can (leg vol 0.115 overnight against 0.151 intraday,
0.188 total). Charged **nothing**, the family is a clean monotone risk improvement and a third
independent confirmation of the leg split:

| h | CAR% | Sharpe | MaxDD% | std | turn x/yr |
|---|---|---|---|---|---|
| 0.00 (deployed) | 22.192 | 1.159 | 23.860 | 0.188 | 49.4 |
| 0.25 | 20.503 | 1.246 | 21.467 | 0.160 | 188.0 |
| 0.50 | 18.626 | **1.321** | **19.051** | 0.136 | 335.2 |
| 0.75 | 16.583 | **1.337** | 19.113 | 0.120 | 482.8 |
| 1.00 | 14.432 | 1.234 | 19.972 | 0.115 | 630.4 |

Sharpe rises from 1.159 to 1.337 and drawdown falls 4.8 points. **The risk reduction is real.**

**(4) Clause 2, the pre-registered arithmetic, and it refuses the idea before any book is
judged.** The raw edge is **negative at every h** (-0.749 / -1.512 / -2.285 / -3.050 bps/day at
t -1.92 / -1.93 / -1.95 / -1.95), so the whole case is the relever. Vol-matching to the deployed
0.188 permits 1.177x / 1.380x / 1.566x / 1.643x, and the breakeven one-way cost is the levered
edge divided by the extra turnover it pays it on:

| h | relever | levered edge bps/day | extra turn/day (x equity) | breakeven bp one way |
|---|---|---|---|---|
| 0.25 | 1.177 | +1.328 | 0.682 | **1.948** |
| 0.50 | 1.380 | +2.837 | 1.640 | 1.730 |
| 0.75 | 1.566 | +4.133 | 2.805 | 1.474 |
| 1.00 | 1.643 | +4.483 | 3.914 | 1.145 |

**Under the 2 bp every other daily row here is charged, at every h**, best 1.948 at h=0.25.
Note the shape: the breakeven is **highest where the construction does least** and falls
monotonically as it does more. There is no interior optimum, which is the signature of a pure
cost problem rather than a tuning one. The pre-registered expectation was "refused, and by
roughly 1.5x rather than by a factor, c* ~= 1.3-1.5 bp" - the measurement is 1.145-1.948, so the
expectation was right in sign, in magnitude and in mechanism.

**(5) Clause 5, the refusal quoted as a book rather than as an inequality - because 1.948
against 2.000 is 2.6% from the line and too narrow to leave as arithmetic.** Charged 2 bp of
one-way spread and IBKR Pro financing on the deployed convention:

| cell | CAR% | Sharpe | MaxDD% | turn x/yr | paired vs deployed |
|---|---|---|---|---|---|
| deployed (costed) | **19.640** | **1.047** | **24.037** | 49.4 | - |
| flat 0.25 | 14.689 | 0.937 | 21.909 | 188.0 | -1.875 (t **-4.79**) |
| flat 0.50 | 9.593 | 0.741 | 24.161 | 335.1 | -3.819 (t **-4.88**) |
| flat 0.75 | 4.497 | 0.427 | 29.405 | 482.5 | -5.792 (t **-4.93**) |
| flat 1.00 | -0.555 | 0.009 | 50.206 | 629.7 | -7.785 (t **-4.97**) |

Read the two columns together: at **zero** cost nothing in this family is distinguishable from
the deployed book (|t| <= 1.95); at **2 bp** every cell is refused at **|t| between 4.79 and
4.97**, the most significant refusal in the daily file. The difference between those two columns
*is* the spread, and it is the whole result.

**(6) And the exact vol-matched books are WORSE than the first-order arithmetic that refused
them**, which is worth stating because it means clause 2's breakeven was a *generous* bound:

| vol-matched | scale | CAR% | Sharpe | MaxDD% | gross mean / max | turn x/yr |
|---|---|---|---|---|---|---|
| h=0.50 | 1.381 | 11.896 | 0.691 | 32.930 | 1.73 / **2.18** | 463.0 |
| h=1.00 | 1.646 | -3.470 | -0.093 | **71.825** | 2.06 / **2.68** | 1036.5 |

Both breach **Reg-T's 2.0x** on peak gross as well as every return and risk criterion, so even a
breakeven that cleared the spread would have run into the margin limit. The reason first order
over-promises is mechanical: levering the book levers the spread bill **linearly** while the edge
it buys is sublinear once financing on the larger debit is charged. Halves agree - IS 2012-2019
h=0.50 **3.294** (DD 24.2) against the deployed 14.317 (20.9), OOS 2020-2026 **17.589** (19.8)
against 25.967 (24.0) - so it fails in both, not on one episode.

**(7) Clause 6, the placebo, passes and confirms the split a third time.** The mirror
construction - flat **overnight**, holding the session, i.e. shedding the leg that pays - costs
**-15.395 bps/day at t -12.19** (-18.269% CAR, DD 95.121%) against flat-all-session's -7.785 at
t -4.97. Shedding the leg with the alpha is **twice** as expensive as shedding the leg without
it, on identical turnover (624.3x against 629.7x). Nothing here is a statement about leverage.

**Decision: REFUSED, on cost, at every h - and the backlog item's premise refuted separately.**
Nothing shipped, nothing promoted, no default changed. `flat_frac` is unset in every deployed
path and the deployed book holds around the clock as it always has. `live/*` and all three
scheduled tasks are untouched. `champion.json` gains a `delta_note` only.

**What it changes for the loop.** The reusable rule is that **when one construction can be
expressed in two instruments, the refusal mode identifies the instrument, not the idea.** S-26
and S-30 are the *same* mechanism - remove the intraday leg, relever the freed variance - and
they fail in opposite ways: the futures version cleared its instrument's cost by **2.3x** and
died on **drawdown**; the equity version dies on **cost**, at a breakeven **2.0x below** its
instrument's round trip, and the ratio between the two verdicts is just the ratio of the two
round trips (ES 0.488 bps against an equity 4.0 bps, ~8x). So S-26's "refused on risk" was a
statement about the book and S-30's "refused on cost" is a statement about the equity market;
the leg split itself has now been confirmed by three independent routes and monetized by none.
Second, and procedural: **a premise quoted from a prior iteration's printed number owes an
identity check before it is built on.** The entire case for re-opening S-25 was that its
overnight book had been priced with the wrong convention, and one identity run - two minutes -
showed the two conventions are the same book to the cent. That check belonged at the top of the
script, and it is where it went.

**Standing jobs, both run first, no new input (Saturday, no session since 2026-09-11).**
`slippage_report.py`: 66 fills, **+2.22 bps** notional-weighted, se 0.80,
|measured - shipped| / se = **0.90**, still not distinguishable at 2 se from the shipped 1.50;
the power note is unchanged at ~145 fills (~4.4 sessions). `daily_fills.py`: 10 fills, $2.37M,
**+3.2 bps** against the auction the runner aimed at (se 4.5), `ref_price` the previous close
**10 of 10**. One ops fact worth recording so the next session does not lose a cycle to it:
`slippage_report.py` reads the parquet minute store and **only Python 3.14 has `pyarrow`
installed** on this machine - under `py -3.11` it dies with `ImportError: Unable to find a usable
engine`. Run it as `py -3.14`.

**Reproduce.** `py -3.14 scripts/sweep_s30.py --stage a` for the identity and the arithmetic that
refuses it (~4 min); `--stage all --force-stage-b` for the costed grid, the vol-matched columns
and the placebo (~12 min).


## 2026-09-12 - S-29: a strictly better volatility forecast makes a strictly worse crisis switch, and the sessions VIX removes are the best in the sample

**Hypothesis.** Volatility enters this book in exactly two places. S-28 priced the first, the
vol target `target_vol / sigma`, which decides SIZE and which binds on only 2.8% of sessions
because the flat margin budget pins the book at ~1.50x gross the rest of the time. The second
is `risk_on`, the crisis switch, which decides DIRECTION: when SPY's trailing 20-session
**realized** volatility exceeds 1.5x its own one-year median the book holds nothing at all,
and it has been off on 590 of 3,689 sessions (16.0%) since S-1. A realized estimate is a
backward-looking measurement of a forward-looking quantity, and there is a market that quotes
the forward-looking one directly. S-25 sharpens the motive: 94% of this book's return and all
of its measurable alpha is earned overnight, in the leg that carries gap risk, which is
precisely the risk an option prices. This is also the first input tried on the daily sleeve
that is **new information** rather than a new rule on the same bars, which is what the
owner-side note of 2026-09-11 asked the next program to bring.

New `scripts/sweep_s29.py` and `scripts/regime_data.py`; **30 ledger rows** under
`daily/s29_regime`, every one DIAGNOSTIC; **six clauses pre-registered**, no post-hoc column.
The mechanism is a third default-inert hook in the shipped `signals.py` - `S1_REGIME_SERIES` /
`set_regime_series()`, F-3's `S1_ML_SCORES` and S-28's `S1_VOL_RETURNS` pattern - that supplies
the LEVEL the switch compares to its own trailing median and nothing else. The gate is
scale-free (`level >= threshold * median(level)`), so a VIX in percentage points and a realized
vol as a fraction produce identical arithmetic and **no constant is re-tuned**. The environment
variable is unset in every deployed path. **Both deploy gates were re-run after the edit**:
`scripts/compare_orders.py` 3,689/3,689 dates and 5,021 orders on both sides, and a full LEAN
control run reproducing `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3` at 5,128 orders /
24.403% / 0.994 / 23.700% / $27,199.76 (run `20260912T093609Z`).

**(1) Clause 1, two identities, both to the digit.** The shipped realized level pushed
*through the hook* reproduces the deployed cell exactly - **CAR 22.192150% / 5,052 orders /
end $1,880,257.37**, the figure S-25 through S-28 each landed on - and an independently
computed gate series reproduces the book's own risk-off days on **3,689 of 3,689** sessions,
which is what makes every off-rate below readable.

**(2) Clause 2, the diagnostic, passes - and passes loudly.** Correlation of log level with
the log realized volatility of the **next 21 sessions**, on the identical 3,669 sessions:

| level | corr | obs |
|---|---|---|
| trailing 20-session realized (**shipped**) | 0.4985 | 3,669 |
| **VIX** | **0.6361** | 3,669 |
| VIX made stale by 5 sessions | 0.5326 | 3,669 |
| SPY 1-month ATM implied (Theta, 2017-) | **0.6857** | 2,411 |

The market's forecast is **a quarter better than the book's own**, and the ordering is the one
the variance-risk-premium literature predicts. At the same 1.5x-of-median threshold VIX is off
on **9.3%** of sessions against realized's 16.0%, they disagree on 9.9%, and clause 6's written
expectation (a smoother, more persistent series fires less often) held.

**(3) And the better forecast is a worse switch, which is the result.** A gate's job is not to
forecast volatility, it is to remove sessions worth removing, so the decisive column is what an
**ungated** version of this book (threshold 99, so the gate runs and never fires - asking what
the *deployed* book earned on its own off days is circular) earns on the sessions each gate
removes:

| sessions | bps/day | t | n |
|---|---|---|---|
| every session | +10.01 | +4.38 | 3,689 |
| the realized gate removes them | +8.72 | +1.16 | 590 |
| **VIX removes them** | **+20.07** | +1.86 | 343 |
| SPY ATM implied removes them | +13.15 | +1.12 | 328 |
| **realized off, VIX on** | +1.48 | +0.17 | 307 |
| **VIX off, realized on** | **+36.56** | **+2.01** | 60 |

**VIX removes sessions worth twice the average session**, and the sixty it removes that
realized does not are worth **three and a half times** the average at the only |t| > 2 in the
diagnostic. The shipped gate removes sessions worth +8.72 against +10.01, i.e. it barely earns
its return cost - it is bought for drawdown, not for return, and the reference row below prices
that.

**(4) Clauses 3, 5 and 6, the books, charged 2 bp of one-way spread and IBKR Pro financing on
the deployed convention. Everything is refused.**

| cell | CAR% | Sharpe | MaxDD% | std | gross | off% | turn x/yr | paired vs shipped |
|---|---|---|---|---|---|---|---|---|
| **shipped (realized @1.50)** | **19.640** | **1.047** | **24.037** | 0.188 | 1.25 | 16.0 | 196 | - |
| VIX @1.50 (**primary**) | 15.901 | 0.842 | **37.758** | 0.199 | 1.35 | 9.3 | 196 | -1.177, t -1.46 |
| VIX stale 5d (**placebo**) | 16.666 | 0.858 | 35.795 | 0.204 | 1.35 | 9.3 | 216 | -0.875, t -0.99 |
| VIX @1.27 (**off-matched**) | 12.188 | 0.729 | 31.540 | 0.180 | 1.23 | 17.3 | 131 | **-2.612, t -3.06** |
| no gate at all (*reference*) | 22.317 | 1.026 | 36.892 | 0.220 | 1.48 | 0.0 | 295 | +1.139, t +0.96 |

The primary fails **every** criterion in the full period and in **both** halves (IS 13.251 vs
14.317 at DD 27.290 vs 20.936; OOS 18.763 vs 25.967 at DD 37.802 vs 24.040) and breaches the
35% absolute drawdown limit. **The off-matched column is the one that matters** and it was
pre-registered rather than reached for: its threshold (1.2688) was solved on the in-sample half
alone so the VIX gate steps aside on the same 14.3% of sessions the shipped gate does, which
removes the "it is only more exposure" explanation - and it is the **worst** book in the table,
**-2.612 bps/day at t -3.06**, the only significant statistic anywhere in this iteration and it
is *against* the switch. So the loss is in the **timing**, not in the exposure.

**(5) The placebo triggers clause 5's withdrawal condition, and the primary was already
refused.** Making VIX five sessions **stale** - deliberately destroying a third of the forecast
advantage, 0.6361 down to 0.5326 - makes the book **better**, 16.666% against 15.901% full
period and 15.911% against 13.251% in-sample. Nothing here is paying for forecast quality.

**(6) Clause 4, the shelf: there is no threshold that rescues it.** Six thresholds on each
input, full period, same cost model:

| threshold | 1.25 | 1.40 | 1.50 | 1.60 | 1.75 | 2.00 |
|---|---|---|---|---|---|---|
| realized CAR% | 17.138 | 18.251 | **19.640** | 19.279 | 19.004 | 20.010 |
| realized MaxDD% | 20.790 | 24.044 | 24.037 | 24.038 | 25.885 | 38.901 |
| VIX CAR% | 13.399 | 14.144 | 15.901 | 15.842 | 18.497 | 19.464 |
| VIX MaxDD% | 32.990 | 34.475 | 37.758 | 41.253 | 36.894 | 36.893 |

**The VIX gate is worse than the realized gate at every one of the six**, its drawdown is
33-41% at every one of the six, and it only approaches the shipped book by turning itself off
(2.5% off-rate at 2.00). The shipped 1.50 is simultaneously confirmed as a **shelf, not a
spike**: it is the Sharpe maximum of the realized row (1.047 against 0.996 / 1.001 / 1.011 /
0.988 / 0.999) and its two neighbours sit within 1.4 CAR points.

**(7) Not a VIX-construction artifact.** The second implied series is a different instrument
computed by a different vendor from actual SPY option quotes, and it is the **best** forecaster
in clause 2's table (0.6857). On its own 2018-2026 window it agrees in sign: **15.926% / 0.791
/ DD 35.193** against the shipped book's 21.219% / 1.036 / 24.040 on the same sessions, with
VIX at 13.753 / 0.693 / 37.811 between them.

**(8) One number this iteration produced that was not being asked for.** The reference row
prices the switch itself on today's book for the first time - S-15 (b) measured it on the
retired 3x champion at zero spread (22.383% / DD 31.4). Honestly costed on the unlevered
champion, **removing the crisis switch entirely earns +2.68 CAR points (22.317 vs 19.640) for
+12.9 points of drawdown (36.892 vs 24.037)**, paired +1.139 bps/day at t +0.96. That is
**refused on the spot** rather than filed as an owner option, because 36.9% is past the 35%
absolute limit in `champion.json` - the one constraint in this repository that is not a
preference. The switch is expensive and it is the only thing keeping this book inside its own
risk mandate.

**Decision: refused on every clause, nothing promoted, nothing shipped, no default changed.**
`S1_REGIME_SERIES` is unset in every deployed path, `champion.json` gains a `regime_note` only,
`live/*` and all three scheduled tasks are untouched, and the champion stands at S-18.

**What it changes for the loop.** The reusable rule is that **a risk switch is not a
forecasting problem**. Every previous refusal on this sleeve was a cost refusal (L-1, X-1, F-1,
F-3), a sign refusal (F-4, F-6) or a risk refusal (S-26); this one is new: the input was
*improved* on its own stated terms, by a quarter, measured on 3,669 sessions, and the book got
**2.6 bps a day worse at t -3.06 with the exposure held fixed**. The mechanism is written in
the shipped docstring already and S-1 found it in 2026-09-08: vol peaks coincide with the
sharpest rebounds, so the value of a realized-vol switch is precisely that it is **late** - it
is a trailing stop denominated in volatility, acting on damage already done. A forward-looking
input converts it back into the anti-predictive "risk-off above the median" filter the original
S-1 write-up asked for and the data refused, and the 60 sessions in clause 3 are those rebounds
being sold. The second reusable piece is procedural and cuts the other way from usual: **the
diagnostic passed and the book still failed**, so a clause-2 pass is a licence to read the book,
never a substitute for it. Three durable artifacts survive: the `S1_REGIME_SERIES` hook (any
future regime input - a credit spread, a breadth measure, a term structure - is now priced
through the shipped algorithm without editing it), `scripts/regime_data.py` (VIX 2005-2026 and
the SPY ATM implied series on disk as plain level files), and the standalone `gate_series`
identity, which means an off-rate can be quoted without running a book.

## 2026-09-12 - S-28: the risk model is the one place the leg split does change the book - same return, 2.1 points less drawdown, and it is refused by a return-first rule

**Hypothesis.** S-25 measured that 94% of this book's return and all of its measurable alpha
is earned overnight, and that the two legs carry 0.115 and 0.151 of annualized vol against the
book's 0.188 - the leg that pays carries the *smaller* share of the risk. S-26 asked what the
book should then HOLD (a futures overlay; refused on drawdown) and S-27 asked what it should
RANK on (an overnight momentum blend; refused - the whole trend forecasts the overnight leg
better than its own history). Neither asked the third question, and it is the one the sizing
machinery poses directly: the book is sized by `target_vol / sigma`, and `sigma` is a
**close-to-close** estimate of a quantity 61% of whose variance comes from the session leg the
book is not paid for. A risk model is a forecast of the risk about to be taken; if the two legs
have different volatility dynamics, the shipped estimator is the wrong forecast for a book
whose P&L is an overnight object, and the de-risking that follows from it happens at the wrong
times.

Where it can bite was stated in advance, because it decides how the result reads: with
`margin_budget = 0.75` flat the book is pinned at ~1.50x gross whenever the vol target asks for
more than the budget can fund (S-8's "the vol target is inert upwards"), so `sigma` moves the
book only when it is **large**. This is a study about how the book de-risks in a crisis, not
about its average exposure.

New `scripts/sweep_s28.py`; **18 ledger rows** under `daily/s28_volest`, every one DIAGNOSTIC;
**six clauses pre-registered** plus one column labelled post hoc. The mechanism is a new
default-inert hook in the shipped `signals.py` - `S1_VOL_RETURNS` / `set_vol_returns()`, F-3's
`S1_ML_SCORES` pattern - that supplies the return window `_size` measures the vol target on.
Nothing else in that file changed, the environment is unset in every deployed path, and the
**I-1 gate was re-run after the edit: `compare_orders.py` 3,689/3,689 dates, 5,021 orders on
both sides, PASS**. One default-inert argument (`diag_out=`) was added to
`sweep_s25.legs_simulate` on S-26's precedent so every S-25/S-26/S-27 row stays bit-identical.

**(1) Clause 1, the identity, passes to the digit.** The leg identity `(1+on)(1+id) = (1+cc)`
holds to **2.220e-16** across the store, and the close-to-close frame pushed *through the hook*
reproduces the deployed cell exactly - **CAR 22.192150% / 5,052 orders / end $1,880,257.37**,
the same figure S-25, S-26 and S-27 each landed on - so the hook is the estimator and nothing
else.

**(2) Clause 2, the diagnostic, says there is real leg-specific information, and how much.**
Pooled over the nine names, trailing 60 sessions against the realized vol of the next 21,
correlation of log vols (59,662 observations):

| trailing | -> cc | -> on | -> id |
|---|---|---|---|
| close-to-close (shipped) | **0.7260** | 0.6608 | 0.7122 |
| overnight only | 0.6407 | **0.6764** | 0.5789 |
| intraday only | 0.7193 | 0.5940 | **0.7492** |

**Every leg forecasts its own future risk better than the pooled estimate does** - the diagonal
is the maximum of every column - so the premise is not empty: the overnight estimator beats the
shipped one at forecasting the leg the book is paid in, by **+0.0156**. It is a small edge, and
clause 6's written-down expectation held for the reason written down: the two estimators are
**0.9029 correlated in log level and 0.8261 in log change**, with `sigma_on / sigma_cc` averaging
**0.5888**.

**(3) Clause 3-5, the books, charged 2 bp of spread and IBKR Pro financing on the deployed
convention. All four are refused.**

| cell | CAR% | Sharpe | MaxDD% | std | gross | scale at cap | sessions the vol target sizes |
|---|---|---|---|---|---|---|---|
| shipped (cc) | 19.640 | 1.047 | 24.037 | 0.188 | 1.25 | 37.2% | 2.8% |
| on (raw) | 20.333 | 1.046 | **32.031** | 0.195 | 1.26 | 86.3% | 1.0% |
| **on_k (level-matched)** | 19.400 | **1.049** | **21.622** | 0.186 | 1.24 | 32.3% | 4.7% |
| id (raw) | 20.084 | 1.043 | 30.196 | 0.194 | 1.26 | 68.9% | 1.7% |
| id_k (level-matched) | 19.801 | 1.048 | 25.470 | 0.190 | 1.25 | 44.8% | 3.4% |

The two **raw** columns are exactly what clause 4 said they would be and must not be read as
edge: overnight vol is 0.59x close-to-close vol, so handing it to `target_vol / sigma` unchanged
pins the scale at its cap on **86.3%** of sessions and buys **+0.69 CAR points for +8.0 points of
drawdown** - it deletes the crisis de-risking, which S-16 and O-1b already priced as leverage.
The **primary** is the level-matched column, rescaled by a *causal* expanding-window factor
(burned in on 1998-2011 history, so no cell here runs on the fallback), and it is **refused on
CAR, 19.400 against 19.640**, paired **-0.100 bps/day at t -0.92**.

**(4) The placebo is what makes the primary readable, and it separates cleanly.** The identical
construction on the leg the book is *not* paid in moves the book the **opposite way**: `id_k`
buys **+0.16 CAR points for +1.43 points of drawdown** (refused on drawdown) while `on_k` buys
**-0.24 CAR points for -2.42 points of drawdown**. Same machinery, same level match, same
turnover to within 4%: the leg that pays makes the risk model *more* conservative when it
matters and the leg that does not makes it less. This is not "any alternative estimator helps".

**(5) Where the primary's CAR shortfall comes from, which the post-hoc column then removes.**
The causal level match equalizes the average *name's* vol, not the *portfolio's*: mean estimated
portfolio vol is 0.2584 against the shipped 0.2380, i.e. the matched book still runs 8.6% high
on the estimate and therefore 1% light on gross (1.24x against 1.25x, realized vol 0.186 against
0.188). **Post hoc and labelled as such**, re-levered on the real machinery to the shipped book's
own 0.1883 (scale 1.015, S-26's `scale=` argument): **19.613% / Sharpe 1.046 / DD 21.931 against
19.640% / 1.047 / 24.037** - a **dead heat in return (paired -0.009 bps/day, t -0.08) for 2.1
points less drawdown**. It still fails the return-first rule, by **0.027 CAR points**. By half:
**OOS 2020-2026 passes every criterion** (26.007 vs 25.967, DD **20.67 vs 24.04**) and **IS
2012-2019 fails** (14.254 vs 14.317, DD 21.72 vs 20.94).

**(6) It is two episodes, not one, and they point opposite ways - stated because the effective
sample here is small.** The vol target sets the book's size on 2.8% of sessions (4.7% under
`on_k`), so the whole result lives in a handful of crises, and no statistic in this iteration
reaches |t| = 2. The deepest drawdowns: shipped **24.04% (2022-08-12 -> 2022-09-26)** and
**20.94% (2015-07-17 -> 2016-01-11)**; `on_k` **20.27%** and **21.62%** over the identical
windows. So the leg-aware estimator trades 0.7 points of the 2015-16 drawdown for 3.8 points of
the 2022 one. In the in-sample half the vol target is *never* the binding constraint for the
shipped, raw and `id_k` books (all three print 14.317% to three decimals); only `on_k` differs
there at all.

**Standing jobs both ran first.** `slippage_report.py --refresh`: 66 fills / $2,875,065 /
**+2.22 bps (se 0.80)** against the shipped 1.50, |diff|/se **0.90**, ~4.4 more sessions to
resolve - **not met, `SLIPPAGE_BPS` untouched**. `daily_fills.py`: 10 fills / $2.37M / **+3.2 bps
(se 4.5)**, `ref_price` the previous close 10 of 10. Saturday, so neither had new input.

**Decision.** Refused - all four estimators, and the post-hoc matched-risk column too. Nothing
promoted, nothing shipped, no default changed: `S1_VOL_RETURNS` is unset in every deployed path,
`champion.json` gains a `risk_note` only, and `live/*` and all three scheduled tasks are
untouched. The matched-risk column is appended to `BLOCKERS.md` as a **priced risk-posture
option**, beside S-26's un-relevered half hedge, because it is the cheaper of the two - it needs
no futures permission and no Reg-T decision, only a change of default - and because "the same
return at less risk" is the exact argument S-18 was promoted on, which makes it the owner's call
rather than the loop's under a return-first rule.

**What it changes for the loop.** The reusable rule is that **a leg attribution is a statement
about the risk model before it is a statement about the signal**. S-27 established that knowing
which leg pays does not tell you which leg to *rank* on; S-28 establishes that it does change
what to *size* on - by little in return and measurably in drawdown - and that the sign of the
change is specific to the leg that pays, because the placebo on the other leg moves the book the
other way. Two durable pieces survive it: the **`S1_VOL_RETURNS` hook**, so any future risk-model
question (a different estimator, a different window, an implied-vol input) can be priced through
the shipped algorithm without editing it, and the **`diag_out=` argument**, so any question about
*when* the vol target rather than the margin budget sets the book's size is now one column.

**Next.** The leg-split program is finished on this sleeve: hold (S-26), rank (S-27) and size
(S-28) have all been asked and all three are refused, two of them on risk rather than on edge.
What binds is unchanged and is not research - the owner decisions in `BLOCKERS.md`, which now
carry three priced options (the pre-open task move at +1.98 CAR points, S-26's half hedge, and
S-28's risk model) and the two standing measurements accruing on their own.

## 2026-09-12 - F-6: the overnight gap does not reverse during the session on the names this sleeve may trade - the effect is absent, not unaffordable

**Hypothesis.** S-27 closed the daily sleeve's leg question and left one number behind, labelled
post hoc and explicitly not pursued: on the champion's nine ETFs, a momentum score built from
**overnight** returns forecasts the next session's **intraday** leg *negatively*, top-3 minus
equal-weight **-2.230 bps/day at t -3.30**, sign-stable in both halves. It was parked for three
stated reasons - the nine names are the daily champion's, so AGENTS.md's disjointness rule bars
the intraday sleeve from them; the object is a daily round trip whose gross sits under any
realistic cost on that book; and a tradable version needs its own pre-registration and an
instrument. F-6 supplies all three: the same shape at its shortest, cleanest horizon (the single
overnight gap `open[d]/close[d-1]-1`, fading during session `d`), on the **56 names the intraday
sleeve is allowed to trade**, on `data/minute_alpaca`. That is an instrument the sleeve already
owns, a universe the disjointness rule permits, and a published effect (the overnight/intraday
tug of war) this repository had never measured.

It is also a different object from everything already refused on this store: F-4 fades the
session's return **to date**, F-5 does the same on the three index ETFs, X-1 ranks on a 15/30/60
minute **intraday** lookback. None of the three uses information from before the opening bell,
which is where the entire measurable alpha of the *daily* sleeve turned out to live (S-25:
+8.103 bps/day overnight at t +6.80 against +0.738 intraday at t +0.47).

New `scripts/sweep_f6.py`, built on X-1's event-study primitives unchanged (`_panel_job`,
`_cost_bps`, `_cluster_t`) so the three studies span identical calendars leg for leg.
**2,647 sessions, 2016-01-05..2026-09-09, 14,510,968 legs.** Nine clauses pre-registered in the
docstring; clause (9) is labelled as a post-hoc extension and is discussed as one below.

**(1) A clean refusal, and it is the strongest form available: 0 of 336.** No cell (3 lookbacks
x 7 entry minutes x 2 exits x 2 books x 2 selections, each at both signs) is positive net of the
real cost model at t > 2 in two of three regimes. The second screen - *effect present but
unaffordable?* - returns **0 of 168**: not one cell has a gross fade at t < -2 in two of three
regimes. Across **504 regime-cells the count reaching t < -2 in the fade direction is zero**,
while 21 reach t > +2 in the extension direction.

**(2) Clause (6)'s expected sign is refuted, and that is the finding.** The clause wrote down
first that the gross fade would be *present* and the cell refused *on cost*, because the effect
is published and S-27 measured its daily cousin at t -3.30. The table says the opposite:
**156 of the 168 pooled gross columns are positive** - the gap *extends*, it does not fade - and
**the largest |t| anywhere in 168 pooled cells is 2.08** (1.86 on the tradable `flatten` exit).
The pre-registered primary, the dollar-neutral book on every valid name at lookback 1:

| entry | clock | legs | gross bps | t gross | cost bps | rev net bps | t rev |
|---|---|---|---|---|---|---|---|
| 0 | 9:31 | 136,561 | +0.10 | +0.10 | 4.59 | -4.68 | -4.74 |
| 30 | 10:01 | 137,414 | +1.04 | +1.34 | 4.59 | -5.62 | -7.26 |
| 60 | 10:31 | 137,170 | **+1.29** | **+1.86** | 4.59 | -5.88 | -8.48 |
| 120 | 11:31 | 136,780 | +1.02 | +1.83 | 4.59 | -5.61 | -10.00 |
| 240 | 13:31 | 136,130 | +0.06 | +0.16 | 4.59 | -4.65 | -12.32 |

Hit rate 49.5-50.1% at every entry minute and demeaned-signal breadth -0.027, so the book is
genuinely neutral and genuinely a coin flip.

**(3) So this is NOT a cost refusal, which separates it from most of the file.** L-1, X-1, F-1
and F-3 all found something and could not afford it; F-6 finds nothing to afford. The breakeven
makes it concrete: the strongest pooled *fade* anywhere is **-0.32 bps at t -0.43**, i.e. a
breakeven round trip of **0.32 bps** against this store's measured **4.59**. Even F-2a's ES
contract at 0.488 bps would not clear it - and a single future cannot carry a 56-name
cross-section in any case. **A cheaper instrument cannot buy a gross column that is the wrong
sign and insignificant**, which is F-4's rule applied for the third time.

**(4) Clause (9), the post-hoc extension, and why it was run.** The lookback-1 table refuses the
single gap but does not close the question F-6 was opened to answer, because S-27's by-product is
not a single gap - it is a 20/60/120/252-day momentum blend of overnight returns. So the identical
grid was re-run with the signal generalized to the **compounded overnight return of the last L
sessions**, L in {1, 5, 20}, with L=1 reproducing the first table bit-for-bit as the identity
check on the change. It is counted honestly as a widening of the search: 56 cells become 168, so
~15 passes would be expected by chance at t > 2 if the tests were independent, and the actual
count is **zero**. Neither multi-session column carries the sign either - pooled neutral/all at
the best entry reads **+0.94 (t +1.39)** at L=5 and **+0.36 (t +0.50)** at L=20. **S-27's
by-product does not transport to this universe.**

**(5) The raw book fails its own control too.** Per F-5's rule the directional book's gross may
not be called a forecast until it beats the always-long control over the identical windows. It
does not: the reversal-minus-always-long column is **negative at every one of the 42 pooled
cells**, best **t -2.03**, while the always-long drift over the same windows is +0.6 to +3.1 bps
at t 0.4-1.7. The raw book is a small long-the-market bet with no forecasting content, which is
exactly what F-5 found on the indices.

**(6) Two contaminants were stated in advance rather than assumed away**, and both point the same
way: the store is split-adjusted but **dividend-raw**, so an ex-date prints a spurious downward
gap on ~1% of name-days and biases the *fade* book toward a spurious long; and earnings gaps
cannot be excluded historically (AGENTS.md: the FMP basic plan serves only a narrow window around
today), so the tails of `q20` are disproportionately earnings reactions. Both would have inflated
a fade result. There is no fade result to deflate, so neither needs repairing - which is why
`all` and `q20` were reported side by side.

**Nothing shipped, nothing promoted, no default changed.** Champion unchanged at S-18;
`champion.json`, `live/APPROVED_PAPER.md`, `live/HALT*`, `live/intraday_config.json` and all
three scheduled tasks untouched; `late_momo` still at alloc 0.0 and no strategy module edited;
one new script only, so AGENTS.md rule (a) owes no replay and the I-1 gate is unaffected.
**No ledger rows**, on F-4's and F-5's precedent: `record` is reached only from a stage 2, and a
stage-1 event study measures bars rather than running a strategy.

**Standing jobs both ran first with no new input** (Saturday, no session since the last
iteration): `slippage_report.py` 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90 (~4.4 more
sessions to resolve); `daily_fills.py` 10 fills / $2.37M / **+3.2 bps (se 4.5)**, `ref_price` the
previous close 10 of 10.

**Decision.** Refused, 0 of 336, and refused on **absence** rather than on cost or on sign
strength: nothing in this grid reaches |t| = 2 in either direction before a cent is charged.

**What it changes for the loop.** The reusable rule is that **a post-hoc result measured on nine
correlated ETFs is a hypothesis about that universe, not about the mechanism** - S-27's -2.230
bps/day at t -3.30 was nine names whose effective breadth is far below what a 3,689-session t
suggests, and on 56 genuinely different names the same shape is absent at three lookbacks. Read
forward, it says that by-products filed from the daily sleeve need a transport test before they
are treated as leads for the intraday sleeve, and F-6 is the cheapest form of that test. It also
means the overnight/intraday tug of war is **not** an available mechanism for this sleeve, which
removes the last item on the intraday track that had a stated mechanism and a permitted
instrument.

**Next.** The intraday sleeve's research surface is now empty of mechanisms with a stated prior:
F-4 (sign), F-5 (control), F-6 (absence), L-1, X-1, A-10, A-12, O-1, O-2 are all refused on the
same store, and the current objective's own instruction applies - say so rather than find a
twelfth lever. The binding constraints remain the owner decisions in `BLOCKERS.md` (the pre-open
task move at +1.98 CAR points, the Reg-T buffer, S-26's priced futures overlay, CME history for
the index track), and the standing measurements keep accruing on their own.

## 2026-09-12 - S-27: the leg that pays is not forecast by its own history - the champion's close-to-close score beats overnight momentum at predicting the overnight leg

**Hypothesis.** S-25 and S-26 both asked what this sleeve should *hold*. Neither asked what it
should *rank on*. The shipped signal is a blend of 20/60/120/252-day **close-to-close** returns,
i.e. it scores nine ETFs on a quantity that is 94% composed of a leg the book is not paid for
(S-25: +8.103 bps/day overnight at t +6.80 against +0.738 intraday at t +0.47; selection
difference +3.087 at t +4.20 against -0.314 at t -0.37). If the overnight leg is a separate
*persistent characteristic* rather than an accounting slice, a momentum blend built from
**overnight returns only** should rank better in the leg that pays - and it is free: same nine
names, same top-3, same vol target, same regime gate, same rebalance, same instruments, no new
cost model and no owner consent. This is the one direction S-25 left open that needs nothing new.

New `scripts/sweep_s27.py`; **12 ledger rows** under `daily/s27_rank`, every one DIAGNOSTIC.
Three synthetic price indices per ticker from the same adjusted store - `cc` (the close series),
`on` (compounded close[d-1]->open[d]) and `id` (compounded open[d]->close[d]), whose leg identity
`(1+on)(1+id) = (1+cc)` holds to **2.22e-16** - and the champion's own blend computed on each,
handed to the shipped algorithm through **F-3's `S1_ML_SCORES` hook in `ML_MODE="rank"`**, which
replaces the ranking order and keeps the champion's absolute momentum floor as the entry gate.
**No file the runner loads was modified.** Six clauses pre-registered in the docstring before the
first number, including clause (5), which wrote the expected outcome down first, and clause (4),
a placebo that could have withdrawn clause (3) even if it had passed.

**(1) Clause 1, the identity, passes to the digit - and it is what caught a real defect in this
iteration's own code.** The `cc` index pushed through the hook reproduces the deployed book at
**CAR 22.192150% / 5,052 orders / end $1,880,257.37**, bit-identical to S-19/S-25/S-26's cell. The
first attempt did **not**: it read 20.676% on 5,260 orders, because a naive `pct_change` blend
silently omits **S-10's skip of 5 sessions on horizons of 120 or more** (`mom_skip=5`,
`mom_skip_min_lookback=120`). An end-to-end identity clause catches a vectorized reimplementation
of a shipped signal; inspecting the two formulas does not.

**(2) The signal diagnostic, clause 2, is the finding, and it is a clean inversion of the
hypothesis.** Cross-sectional rank IC of each score against each forward leg of session D+1, over
3,689 sessions:

| score | -> overnight | -> intraday | -> close-to-close |
|---|---|---|---|
| close-to-close (shipped) | **+0.0574 (t +7.25)** | +0.0141 (t +1.81) | +0.0299 (t +3.78) |
| overnight only | **+0.0574 (t +7.32)** | -0.0024 (t -0.32) | +0.0132 (t +1.72) |
| intraday only | +0.0205 (t +2.84) | +0.0093 (t +1.26) | +0.0144 (t +1.96) |

The two scores have **the same rank IC on the overnight leg to four decimals**, so overnight
momentum is not a worse *ordering*. Where they separate is the quantity the book actually
collects - the **top-3-minus-equal-weight spread**, the champion's own selection size: the shipped
score earns **+2.106 bps/day (t +3.24)** of overnight leg against the overnight-only score's
**+1.311 (t +2.04)**, and the gap holds in both halves (IS +2.176 vs +0.947, OOS +2.021 vs
+1.740). **The leg that pays is better forecast by the whole trend than by its own history.**
Nothing forecasts the intraday leg: the best cell in that column is the shipped score's
+0.0141 at t +1.81, and its spread is **negative** (-0.727, t -1.04).

**(3) The primary screen is refused on every criterion, and it is not close.** Charged 2 bp of
spread and IBKR Pro financing on the deployed convention, the overnight-ranked book earns
**11.751% / Sharpe 0.656 / DD 35.210** against the deployed **19.640% / 1.047 / 24.037** - paired
**-2.619 bps/day at t -2.41**, worse in both halves (IS 7.693 vs 14.317, OOS 16.582 vs 25.967),
and its drawdown breaches `champion.json`'s absolute 35% limit outright. At 0 bp it is 14.188%
against 22.192%. **(4) The placebo is refused too**, which is the outcome that keeps clause 3
readable: intraday-ranked earns **13.167% / 0.778 / DD 27.591**, paired -2.270 at t -2.08. Neither
reconstruction beats the shipped ranking, so this is not a case of any perturbation of the blend
helping.

**(5) The refusal is about selection, not about exposure, and the leg attribution proves it.**
The obvious objection is that the overnight-ranked book is simply invested less or differently,
but its mean gross is **1.24x against the deployed book's 1.25x** - and against the same-gross
always-invested control the overnight excess is **+3.087 bps/day (t +4.20) for the shipped score,
+1.686 (t +1.86) for the overnight score and +1.183 (t +1.51) for the intraday score**. Matched
exposure, same nine names, same gate: the shipped ranking is **1.8x** the overnight one at
forecasting the only leg this sleeve is paid in. Its turnover is also *lower* (131x equity/yr
against 240x), so it is not being refused for trading more.

**(6) Clause 5's written-down expectation held, and for the reason written down.** The overnight
leg carries 94% of the return but only +3.087 of the +8.662 bps/day is selection; the rest is beta
the control collects too. An overnight-only index compounds roughly a third of the close-to-close
variance into a 252-day window, so its momentum is a noisier estimate of the same trend - which is
exactly what the table shows: the same ordering (identical IC) with a smaller top-end spread.

**(7) One by-product, labelled post hoc and sign-stable in both halves**: the overnight-only score
forecasts the next **intraday** leg **negatively** - top-3-minus-EW **-2.230 bps/day at t -3.30**
(IS -2.182 at t -3.03, OOS -2.290 at t -1.89), the largest |t| in the diagnostic after the two
overnight cells. Names that have been climbing overnight give some of it back during the session.
It is recorded and **not pursued here**: the nine names are the daily champion's, so AGENTS.md's
disjointness rule bars the intraday sleeve from them; the object is a daily round trip whose gross
2.2 bps sits under any realistic entry-and-exit cost on this book; and F-5's rule already applies -
the figure quoted is a spread over the equal-weight control, which is the right form, but a
tradable version needs its own pre-registration and an instrument.

**Nothing shipped, nothing promoted, no default changed.** `S1_ML_SCORES` stays unset in every
deployed path, champion unchanged at S-18, `live/APPROVED_PAPER.md`, `live/HALT*`,
`live/intraday_config.json` and all three scheduled tasks untouched, and **no file either runner
loads was modified**, so AGENTS.md rule (a) owes no replay and the I-1 gate is unaffected (S-19's
precedent). `champion.json` gains a `rank_note` and nothing else.

**Standing jobs both ran first with no new input** (Saturday, no session since the last
iteration): `slippage_report.py` 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90;
`daily_fills.py` 10 fills / $2.37M / **+3.2 bps (se 4.5)**, `ref_price` the previous close 10 of 10.

**Decision.** Refused. The overnight-ranked book fails the full period, both halves, the drawdown
tolerance and the absolute drawdown limit; the placebo fails too.

**What it changes for the loop.** S-25's split is an **attribution, not a signal recipe**, and
that is the reusable rule: *knowing which leg a book is paid in does not tell you which leg to
build the signal from* - the forecast horizon and the payment window are different objects, and a
leg attribution may not be read as a feature-selection instruction without its own IC table. It
also closes the direction S-25 left open by the only route that needed nothing new; what remains
of that direction (a sleeve chosen for its overnight behaviour, or a holding period measured in
nights) needs a different universe and a cost model that survives it, not another score on these
nine names. One durable piece survives: `sweep_s27.score_frame` plus the three leg indices, which
turn any leg-conditional ranking question into a table the shipped algorithm can run through the
F-3 hook without being edited.

**Next.** The unblocked research surface on the daily sleeve is now the same as it was before
S-25: the binding constraints are the owner decisions in `BLOCKERS.md` (the pre-open task move at
+1.98 CAR points, the Reg-T buffer, the futures overlay S-26 priced, CME history for the index
track). The standing measurements (A-5 part 2 at ~4.4 more sessions, `daily_fills.py`) keep
accruing on their own.

## 2026-09-12 - S-26: the alpha-free intraday leg can be hedged for less than it is worth, and the book that does it is refused on drawdown

**Hypothesis.** S-25 left exactly one direction open and named it: the overnight leg is the only
place this sleeve has ever shown alpha (**+3.087 bps/day at t +4.20** over an always-invested
control at the book's own gross, against **-0.314 at t -0.37** intraday), and nothing has ever
targeted it. S-25 also closed the obvious route - a book that liquidates at the open and
re-establishes at the close turns over 1,248x its equity a year and loses *before a cent of cost
is charged*. So the leg cannot be isolated by trading the equity book. It can only be isolated by
**overlaying a short of the index over one leg**, and that is only worth asking because F-2a
measured the instrument: an **ES round trip is 0.488 bps** of notional (MES 0.744) against the
4.70-8.20 bps every intraday refusal in this repository was written on. This iteration puts the
two results together: short `h x beta x equity` of the index from the open to the close, where
beta is the trailing OLS slope of the book's own intraday leg on the index's, and ask whether the
variance it removes is worth more than the drift it sells.

New `scripts/sweep_s26.py`, plus **two optional arguments on `sweep_s25.legs_simulate`**
(`hedge=`, `scale=`) that change nothing when absent - S-22's precedent on `sweep_s19.simulate`.
**10 ledger rows** under `daily/s26_hedge`, every one tagged DIAGNOSTIC. **Seven clauses
pre-registered in the docstring before the first number**, three of which (2, 5, 6) could refuse
or invalidate the whole thing, and clause 5 wrote the expected outcome down first.

**(1) Clause 1, the identity, passes to the digit.** With `hedge=None, scale=1.0` the harness
reproduces S-25's deployed cell at **CAR 22.192150% / 5,052 orders** with a leg-and-cost residual
of **5.33e-16 of equity**, so the two new arguments overlay on the deployed book rather than
changing it. The unhedged costed cell lands on **19.640%**, S-22's independent honest expectation,
for the third time.

**(2) Clause 2 - the proxy is validated rather than assumed, and it is the tightest fit in the
repository.** No long ES history exists (F-2a: IBKR retains ~4 expired quarters, CONTFUT cannot be
paged), so the overlay is priced on SPY's own open-to-close return. On F-2a's 313-session stitch,
**corr(ES cash session, SPY open->close) = 0.9994, slope 0.9984, basis sd 2.1 bps/session**
(means: ES +1.45, SPY +1.77 bps/day). **The substitution is admissible**, which also means this
overlay is one of the few futures questions in this repository that needs **no CME purchase**.

**(3) Clause 3, said before pricing anything: the intraday leg has no alpha, and it does not
follow that it has no return.** SPY's own intraday leg over 2012-2026 is **+2.432 bps/day at
t +1.86** (IS +2.207 at t +1.52, OOS +2.702 at t +1.18) and its overnight leg **+3.666 at t
+3.33**. So the overlay is an exchange of one drift that has never reached |t| = 2 for a certain
reduction in variance - which is why it has to be measured rather than reasoned about.

**(4) The grid, charged 2 bp of one-way equity spread, IBKR Pro financing and the 0.488 bps
futures round trip every session.** The trailing beta prints **1.12**.

| cell | CAR% | Sharpe | MaxDD% | std | hedge x equity | paired vs unhedged |
| --- | --- | --- | --- | --- | --- | --- |
| unhedged | **19.640** | 1.047 | 24.04 | 0.188 | - | - |
| h=0.25 | 18.972 | 1.098 | 23.28 | 0.172 | 0.28 | -0.342 (t -1.01) |
| h=0.50 | 18.174 | **1.124** | 22.45 | 0.160 | 0.55 | -0.686 (t -1.01) |
| h=0.75 | 17.263 | 1.108 | 21.61 | 0.155 | 0.83 | -1.028 (t -1.01) |
| h=1.00 | 16.224 | 1.043 | 20.77 | 0.156 | 1.10 | -1.373 (t -1.02) |

It does exactly what the split predicts: **every basis point of return the overlay sells buys
volatility and drawdown back**, Sharpe peaks at a *half* hedge, and variance stops falling past
h=0.75 because the trailing beta over-hedges.

**(5) The primary screen is REFUSED, and for the first time on either sleeve it is refused on
RISK rather than on cost, sign or significance.** Vol-matched on the real machinery to the
unhedged book's own 0.1883 (so gross, commission and the financed debit all follow):

| cell | scale | CAR% | Sharpe | MaxDD% | gross mean/max | IS | OOS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| unhedged (the bar) | - | 19.640 | 1.047 | **24.04** | 1.25 / - | 14.317 (DD 20.9) | 25.967 (DD 24.0) |
| h=0.50 vol-matched | 1.176 | **20.837** | 1.100 | **26.02** | 1.47 / 1.83 | 15.041 (DD 21.3) | 27.627 (DD 26.0) |
| h=1.00 vol-matched | 1.208 | 18.932 | 1.016 | 24.78 | 1.51 / 1.90 | 13.488 (DD 19.8) | 25.211 (DD 24.8) |

`h=0.50` **beats the bar on CAR by +1.197 points, on Sharpe, and in both halves** (+0.72 IS,
+1.66 OOS) while staying inside Reg-T - and it is **refused because its drawdown is 1.99 points
worse against the champion's 1.0-point tolerance**. `h=1.00` is refused on CAR full period and in
both halves. Nothing in the comparison reaches |t| = 2: paired **+0.395 at t +0.60** and -0.236 at
t -0.16. **Clause 5's written-down expectation was "refused, and narrowly", which is what
happened - but it expected the refusal to come from the drift being sold, and it came from the
leverage used to buy the risk saving back.** Note also that `h=0.50` is the grid's best-Sharpe
cell, so the *choice* to vol-match that ratio is an in-sample pick and is labelled as one.

**(6) The placebo passes, and it is the durable positive result here.** The identical overlay run
on the **overnight** leg earns **7.598% / Sharpe 0.507 / DD 28.60**, i.e. **-4.310 bps/day at
t -4.14** against the intraday overlay's -1.373 at t -1.02 - a factor of 3.1 and **the only
statistic past |t| = 2 in the whole file**. So the overlay is acting on the split rather than on
volatility in general: **the overnight leg's return survives an independent test by a completely
different route - a hedge rather than an attribution - and the intraday leg's does not.**

**(7) The breakeven, which is the durable number now that the screen has refused.** At zero hedge
cost, `h=0.50` earns **21.821%** (edge +0.717 bps/day, t +1.08) on **0.65x** of live equity of
hedge notional a session (163x/yr) -> **breakeven +1.108 bps a round trip**; `h=1.00` earns
20.914% (+0.420, t +0.29) on 1.33x (335x/yr) -> **+0.316**. Against **ES at 0.488** (0.856 at a
full tick, MES 0.744): **the half hedge clears the cheapest instrument on file by 2.3x and the
full hedge fails it by 1.5x.** So the refusal is emphatically *not* a cost refusal - this is the
first candidate in this repository whose edge survives its own execution and dies on its risk.
**Granularity, because a contract is not divisible**: the `h=1.00` hedge needs a median $239,134
of notional, which is below one ES contract on **65.4%** of sessions and below one MES on 8.2%,
with a mean integer rounding error of 5.0% of the hedge in MES units, on an equity path of
$100k -> $899k.

**One correction to a prior iteration's arithmetic, found by this one.** A breakeven is an edge in
bps of equity per day divided by a turnover, so the turnover has to be on the same
growth-normalized basis. S-25's breakeven (and this repository's `turn x/yr` column) divides
dollar turnover by the **start** equity, which on this book compresses the divisor by the factor
it compounded: the same `h=1.00` cell reads **1,447x/yr and a breakeven of +0.073 bps** on that
basis against the correct **335x/yr and +0.316**, a 4.3x error. **S-25's conclusion is unaffected**
- its two conditional books were behind the deployed book at *zero* cost, so their breakevens are
negative on any divisor - but the printed magnitudes (-0.751 and -9.988 bps) are compressed and
should be read as signs, not sizes. `sweep_s26.py` states the basis in its own output.

**Decision: refused. Nothing shipped, nothing promoted, no default changed.** Champion unchanged
at S-18, `champion.json` gains a `hedge_note` and nothing else, `live/*` and all three scheduled
tasks untouched, and no file either runner loads was modified - one new script plus two
default-inert arguments on a research script - so AGENTS.md rule (a) owes no replay and the I-1
gate is unaffected (S-19/S-24 precedent). Nothing here could have shipped in any case: clause 7
put on the record before the first number that an overlay needs the owner's consent to hold
futures at all.

**Standing jobs both ran first, with no new input.** `slippage_report.py` unchanged at **66 fills
/ +2.22 bps / se 0.80 / |diff|/se 0.90** (~4.4 sessions to settle); `daily_fills.py` at **10 fills
/ $2.37M / +3.2 bps (se 4.5)** with `ref_price` the previous close **10 of 10** - 2026-09-11's
closes have now published, so the +1.7 F-4/F-5 saw is confirmed as the benchmark-availability
artifact it was called.

**Next.** S-25's one open direction is now priced and closed in its cheapest available form, and
the reusable rule is the one this refusal turns on: **matching daily volatility is not matching
drawdown, so a vol-matched relever owes its own drawdown column** - the risk twin of S-15/S-20's
vol-matched control, which was written to stop a *size* decision masquerading as return and says
nothing about the path. What is left is not a research item: the un-relevered `h=0.50` book
(18.174% / Sharpe 1.124 / DD 22.45 against 19.640 / 1.047 / 24.04) is a live offer to trade
**1.47 CAR points for 1.58 points of drawdown and +0.08 of Sharpe**, which is a risk-posture
change and therefore the owner's, and it is written into `BLOCKERS.md` as one.

## 2026-09-12 - S-25: 94% of the champion's return is earned while the market is shut, and so is all of its measurable alpha

**Hypothesis.** Every number this repository has ever written about the daily sleeve is a
close-to-close number, and a book that holds nine ETFs around the clock is paid twice a day: once
while the market is shut (the previous close into the open) and once while it is open. Nothing had
ever separated them. The split is not cosmetic - the two legs have different volatility, the
published equity premium is mostly an overnight effect, and a turnover cost is only payable in the
leg where the trade happens - so it decides where the next lever on this sleeve should be looked
for, and it prices the two routes the owner is being offered in `BLOCKERS.md`.

New `scripts/sweep_s25.py`. The book is S-19's share-level pandas harness, which runs the shared
`algorithms/s1_momo/signals.py` and was validated at corr 0.99650 against the champion's own LEAN
equity curve; this script adds per-session leg attribution and two flat-in-one-leg variants.
Window 2012-01-03..2026-09-04, **3,689 sessions**, the champion's own. **Five clauses
pre-registered in the docstring before the first number**, two of which (3 and 4) could refuse the
whole thing.

**(1) Clause 1, the identity, passes to the digit.** The attributing book reproduces
`sweep_s19.simulate(fill="close")` at **CAR 22.192150% / Sharpe 1.159496 / 5,052 orders /
$1,880,257.37**, and legs + fees + interest reproduce each day's P&L with a maximum residual of
**5.33e-16 of equity** on 3,689 sessions, with **0 sessions** missing an open. A second check came
free at the other end: the costed `both @ 2bp` cell lands on **19.640%**, which is S-22's
independently-derived honest expectation for the deployed book to the digit.

**(2) The split, and it is lopsided.** The deployed book earns **+8.662 bps/day** in total:
**+8.103 overnight (t +6.80), 94% of it**, and **+0.738 intraday (t +0.47), 9%** (fees are the
rest). The legs are not equally risky - annualized, overnight **0.115**, intraday **0.151**,
total 0.188, correlation **-0.014** - so **the leg that pays 94% of the return carries 61% of the
volatility and the leg that pays 9% carries 80% of it**.

**(3) Clause 2's control is what makes it a finding rather than a restatement of the equity
premium.** A long book collects whatever the overnight session pays whether or not its ranking has
content, so each leg is quoted against an **always-invested control scaled every day to the book's
own gross** (1.25x), paired by session. Overnight, the equal-weight sleeve earns **+5.016** against
the book's +8.103, so the **selection difference is +3.087 bps/day at t +4.20**; against SPY
+3.081 at t +3.79. Intraday the same comparison is **-0.314 at t -0.37** (SPY -1.111 at t -1.18).
**Both halves agree**: overnight +2.993 (t +3.62) in 2012-2019 and +3.200 (t +2.51) in 2020-2026;
intraday -0.498 (t -0.52) and -0.094 (t -0.06). **The ranking's alpha is an overnight object, and
fourteen years of data cannot find any intraday content in it at all.**

**(4) Clause 5 refutes the obvious objection.** In a back-adjusted store the ex-date credit lands
inside the overnight leg, so a book tilted toward high-yield names would book more of its total
return overnight for no economic reason. Measured from the store's own adjustment factors (yields
in bps/yr: TLT 290, XLE 251, DIA 208, XLF 186, SPY 172, IWM 118, XLK 104, QQQ 60, GLD 0), the book
carries **+0.683 bps/day** of ex-date credit against the control's **+0.826** - it tilts the
*wrong* way - and price-only the selection difference is **+3.231 at t +4.36**, slightly larger
than the headline. The overnight excess is not a dividend-classification artifact.

**(5) Clause 4 says it is not a Yahoo artifact either.** The whole split hinges on one price, and
S-24 established that the store's open is the first consolidated print rather than the opening
auction. Re-run on the **official opening crosses** (2,683 sessions, 2016-2026), the overnight leg
reads **+8.864 bps/day against the store's +8.887** - a 0.023 difference against the clause's 1.0
tolerance - and the selection difference is +2.966 against +2.972. **PASS.**

**(6) Clause 3, the strategy screen, is a clean refusal, and the expectation written down first was
right about the direction and wrong about the size.** Both conditional books turn the whole
portfolio over twice a day. Charged IBKR Pro financing throughout:

| cell | CAR% | Sharpe | MaxDD% | std | orders | turnover x equity/yr |
| --- | --- | --- | --- | --- | --- | --- |
| deployed, 0 bp | 20.853 | 1.101 | 23.9 | 0.188 | 5,052 | 217 |
| overnight only, 0 bp | 13.113 | 1.133 | 20.6 | 0.115 | 18,251 | 1,248 |
| intraday only, 0 bp | -3.032 | -0.133 | 57.0 | 0.148 | 18,254 | 444 |
| deployed, 2 bp | 19.640 | 1.047 | 24.0 | 0.188 | 5,054 | 196 |
| overnight only, 2 bp | -0.555 | 0.009 | 50.2 | 0.114 | 18,251 | 431 |
| intraday only, 2 bp | -18.269 | -1.297 | 95.1 | 0.147 | 18,254 | 213 |

Paired against the deployed book at 2 bp, overnight-only is **-7.785 bps/day at t -4.97** and
intraday-only **-15.395 at t -12.19**; both halves fail (at 2 bp, IS 14.317 / -7.322 / -18.264 and
OOS 25.967 / 8.804 / -10.708). **The breakeven is the durable half and it is negative**: -0.751
bps one-way for the overnight book and -9.988 for the intraday one, i.e. **they already lose at
zero cost, so no execution improvement anywhere rescues them**. What the clause got wrong is
*why*: the overnight-only book was expected to be a good book made unaffordable, and it is not -
at zero cost it earns 13.1% against the deployed 20.9%. It has the *better Sharpe* (1.133 against
1.101) at 0.115 of vol, which is S-15/S-20's standing lesson again - it is a smaller book, not a
better one, and buying the size back costs turnover the leg cannot pay for.

**(7) Post hoc and labelled as such: which leg pays for the move the owner is being asked to
make.** `BLOCKERS.md` recommends the pre-open MOO switch on S-23's +1.85 and S-24's +1.98 CAR
points. Split by leg, **all of it is intraday**: whole day +0.599 bps/day (t +1.41), intraday
**+0.604 (t +1.43)**, overnight **-0.006 (t -1.34)**. That is structurally forced once it is
stated - both conventions hold the *same* targets overnight, and differ only in what they hold
between the open and the close of the session they trade in - but it puts the recommendation in a
sharper light: **the move buys a leg in which this strategy has never demonstrated an edge**
(-0.314 bps/day at t -0.37 over fourteen years), and its own statistic has never reached |t| = 2
either. It does not reverse the recommendation - the staleness defect is certain and the point
estimate is positive - but the honest framing is now that the certain part of it is the defect,
not the payoff.

**(8) And the other route in `BLOCKERS.md` is dead.** The "smaller in-place alternative" - append
the 15:45 price so the signal reads through day D, then fill at D's close - is priced here as an
upper bound (decide on close[D], fill at close[D], which no runner can actually do): **CAR 22.374%
against the deployed 22.192%, i.e. +0.18 CAR points**, against the pre-open route's +1.885. Leg by
leg it is the interesting one: it buys the same intraday improvement (+0.616, t +1.45) and
**gives almost all of it back overnight (-0.572, t -1.79)**. Putting today's close into the signal
makes the *overnight* leg worse - a one-day reversal - which is S-9/S-10's skip lever rediscovered
from the opposite direction, since the champion's momentum windows already end a trading week
before the decision bar. **The consequence for the owner is concrete: the real-time market-data
subscription cannot be justified by this fix, because the fix is worth 0.18 CAR points.**

**Nothing shipped, nothing promoted, no default changed**: champion unchanged at S-18,
`champion.json` stats untouched (one explanatory `leg_note` added), `live/*` and all three
scheduled tasks untouched, and one new script only, so AGENTS.md rule (a) owes no replay and the
I-1 gate is unaffected (S-19's precedent). **6 ledger rows** under `daily/s25_legs`, every one
tagged DIAGNOSTIC and not promotable. **Standing jobs both ran first**: `daily_fills.py` at
**10 fills / $2.37M / +3.2 bps (se 4.5)** with `ref_price` the previous close **10 of 10** - the
2026-09-11 closes have now published, so today's four fills score and the +1.7 bps F-4/F-5
reported is confirmed as the benchmark-availability artifact it was called; `slippage_report.py`
unchanged at **66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90** (~4.4 sessions to settle).

**What it changes for the loop.** Three things. **(a)** The daily sleeve's alpha is an overnight
object at t +4.2 in both halves, so any future candidate that spends turnover to change what the
book holds *between* the open and the close is spending it on the leg where fourteen years of data
find nothing. **(b)** The two ops routes in `BLOCKERS.md` are now separated by an order of
magnitude - pre-open +1.885, in-place +0.18 - and the paid data subscription is no longer part of
the cheap fix. **(c)** The reusable rule, the daily twin of F-5's always-long control: **a
daily-sleeve return statement must say which leg it lives in, and must be quoted against an
always-invested control at the same gross in that leg**, because the overnight leg pays a premium
to anything that is merely long.

## 2026-09-12 - F-5: F-4's momentum column is mostly the drift, and the published intraday-momentum effect is not in this store

**Hypothesis.** F-4 closed the last open item with a stated mechanism and left behind one piece of
arithmetic it never followed up. Its refusal of the afternoon reversal was on **sign**: over
6,654,000 legs the day's move *extends*, the directional book's gross is positive at **12 of 12**
entry minutes, and every gross statistic in the grid past |t| = 2 is momentum (raw 11:30 **+2.24
bps at t +2.61**, raw 15:00 +0.89 at +2.48, neutral 11:30 +1.78 at +3.54). F-4 then wrote down a
reusable rule - *a cost refusal is an argument for a cheaper instrument only when the gross column
has the right sign at |t| > 2* - and applied it **only to the sign its own table says is wrong**.
Charged F-2a's measured **0.488 bps** ES round trip instead of the equity sleeve's 4.59, that raw
11:30 cell reads +2.24 - 0.49 = **+1.75 bps** rather than -2.35. F-5 exists to ask whether that
arithmetic survives being put to the instrument that would actually carry it, because a 56-name
equal-weighted basket is not something a future can hold.

New `scripts/sweep_f5.py`. Store `data/minute_alpaca`, **SPY / QQQ / IWM**, 1-minute SIP bars,
**2016-01-04..2026-09-10, 2,687 sessions, 367,872 legs** - the three index ETFs this repository
has never run an event study on, because X-1, L-1, A-10, F-1 and F-4 all excluded them under the
AGENTS.md disjointness rule. **Said before the first number and repeated here: nothing measured
on SPY/QQQ/IWM may ever be deployed on the intraday equity sleeve**, whatever it says, because
that sleeve's universe must stay disjoint from the daily champion's book. The only instrument
this mechanism could trade is the index future, whose history past 313 sessions is the purchase
request in `BLOCKERS.md`, so a survivor here would be evidence for that purchase, not a strategy.

**Pre-registered in the script docstring before the first number**, in seven clauses. Signal =
the **sign** of a session return measured from bars that have closed, entered at the **open of
the next bar**; two definitions (`todate`, the open-to-minute-T return, which is F-4's own; and
`first30`, the first half hour held fixed, which is the published Gao/Han/Li/Zhou predictor), two
exits (`flatten` = the 15:38 framework constant, `h30` = thirty minutes), twelve entry minutes
10:00-15:30, three indices. One leg per session per cell, so the t is over sessions with no
overlap to cluster. Pass mark is the one every A-, X- and F-track candidate has faced: **net of
the 0.488 bps decision cost, positive at t > 2 in at least two of the three regimes**. Two clauses
carry the entry. **Clause (5) is the control F-4 did not run**: a book that is long whenever the
market is up so far is long more often than not, so it collects the equity risk premium with no
forecasting content at all - the cell must therefore **also** beat an **always-long control over
the identical windows**, paired session by session, at t > 2, with a fixed-seed random-sign
placebo printed beside it. **Clause (6) wrote the expectation down first**: the index should carry
a noisier version of F-4's number, the survivor was most likely to be `first30` into a late `h30`
because that is the published object, and *if clause (5) killed the `todate` family the honest
reading would be that F-4's momentum column was the risk premium seen through a directional book -
which would also explain why it was positive at 12 of 12 entry minutes, since a mechanism is
rarely that tidy.* Clause (7) put the dependence on the record: F-4's gross column **is** the
discovery sample for this hypothesis over the same calendar window on a correlated object, so
nothing pooled here is an out-of-sample confirmation of anything, which is why the pass mark is
enforced per index and per regime.

**(1) The verdict is a clean refusal: 0 of 144 cells** (3 indices x 2 signals x 2 exits x 12
entry minutes) reach t > 2 net in two of three regimes.

**(2) Clause (5) is the finding, and it lands exactly where clause (6) said it would.**
Session-clustered over the `todate`/`flatten` family, gross is **+1.55 bps at t +2.42** - F-4's
sign and roughly its size, reproduced on the index - but the **always-long control on the
identical windows earns +0.54**, and the difference that is the actual forecast is **+1.01 bps at
t +0.89**. By regime it is **-0.78 / +1.83 / +2.47 at t -0.51 / +0.81 / +1.22**: negative in the
first third of the sample and never significant anywhere. Cell by cell, **5 of 138 beat the
always-long control at t > 2** against the ~3.2 expected by chance at a one-sided 2.3% - i.e. at
chance - and all five sit at the **same entry minute (15:00)** across correlated books, which is
what one lucky window looks like, not five confirmations. The signal is long on **52.6%** of
sessions.

**(3) So F-4's momentum column is identified rather than contradicted.** The index reproduces it
at the same entry minutes and the same magnitude - 11:30 gross **+1.99 (SPY) / +3.64 (QQQ) /
+1.57 (IWM)** against F-4's 56-name **+2.24** - which says F-4's directional book was a market-
factor bet all along. That is why it was positive at 12 of 12 entry minutes, and about a third of
it is drift the always-long control collects for nothing.

**(4) Clause (6)'s named favourite is the weakest family in the file.** The published effect -
the first half hour predicting a later window - is **13 of 33 cells positive net** and pooled
negative. The exact classic cell (first-30-minute signal, entering 15:30 and held to the flatten)
is **gross -0.19 / +0.10 / +0.05 bps on SPY / QQQ / IWM, |t| <= 0.73**, i.e. indistinguishable
from zero before any cost, and -0.68 / -0.39 / -0.44 net. As a book its best-t cell earns **CAR
0.90% at Sharpe 0.25**. This repository cannot find market intraday momentum in 2,687 sessions of
SIP bars at this construction.

**(5) The nearest miss, labelled post hoc and failing both clauses.** QQQ, `todate`, entering
15:00 and held to the flatten: gross **+2.52 at t +3.30**, net **+2.03 at t +2.66**, by regime
**+0.04 (t 0.04) / +3.94 (t 2.56) / +2.12 (t 1.78)** - **one** of three regimes, so it fails
clause (3) - and against always-long **+1.75 at t +1.54**, so it fails clause (5) as well. As a
1x-notional session book net of 0.488 bps it earns **CAR 4.99% / Sharpe 0.82 / maxDD 8.4% / win
51.7% / worst day -359 bps**. Put against the owner's 3-10%/day mandate that is the useful way to
read it: reaching 3% a day from a 5% CAR book needs roughly **10x** on the future, where the worst
session becomes **-36%**.

**(6) One cell worth recording for the same reason X-1 recorded its own by-product.** Entering at
**15:30** in the day's direction and holding to the flatten is gross **-0.05 / +0.10 / +0.07** -
zero - and net **-0.53 (t -2.09) / -0.39 / -0.41**. The last half hour is the one place the sign
leans against the day's move, which is where X-1's afternoon reversal lives, and it is a **pure
cost refusal**: there is no gross there to buy in either direction.

**Nothing shipped, nothing promoted, no default changed.** Champion unchanged at S-18;
`champion.json`, `live/APPROVED_PAPER.md`, `live/HALT*`, `live/intraday_config.json` and all three
scheduled tasks untouched; one new script only and no runner-loaded file modified, so AGENTS.md
rule (a) owes no replay and the I-1 gate is unaffected (S-19's precedent). **No ledger rows**, on
F-4's precedent: `record` is reached only from a harness run, and a stage-1 event study measures
bars rather than running a strategy.

**Standing jobs both ran first, neither has new input.** `slippage_report.py` unchanged at **66
fills / +2.22 bps / se 0.80 / |diff|/se 0.90** (~4.4 sessions to settle), so `SLIPPAGE_BPS` stays
1.5. `daily_fills.py` at 10 fills / $2,373,115, `ref_price` the previous close in **10 of 10** (a
sixth confirmation of the S-19 clock), pooled execution **+1.7 bps (se 5.3)** - still the
benchmark-availability artifact F-4 recorded, because the daily store has not published
2026-09-11's closes and today's four fills score NaN.

**What it changes for the loop.** The durable rule is clause (5) itself: **a directional intraday
book must be quoted against an always-long control on the identical windows before its gross
column may be called momentum**, because the equity risk premium is delivered intraday and a
sign-based book that is long 52.6% of sessions collects part of it for free. That is the
time-series twin of what S-15/S-16/S-20 made compulsory on the daily sleeve (the vol-matched
control) and of what F-1 and F-3 needed the shuffled-label control for. Applied backwards it
resolves F-4's own loose end: the arithmetic that opened F-5 is **refused**, so the CME purchase
case in `BLOCKERS.md` keeps the cost table and the 0.62% gross sd per contract and loses this
third leg as well. The backlog again holds no open research item with a stated mechanism, and the
binding constraint remains the owner decisions in `BLOCKERS.md`.

## 2026-09-11 - F-4: the afternoon reversal does not exist at this construction, and the sign is what refuses it rather than the cost

**Hypothesis.** F-4 was opened by F-2a as the last open item with a stated mechanism. Two
independent samples had pointed the same way and in both cases the number was filed as a
by-product rather than tested: **X-1** on 2,684 sessions of megacap equities (+0.63 bps
entering at 10:30, **-0.69 at t -2.80** entering at 14:30) and **F-2a** on 313 sessions of
front-month ES (day momentum into the last 30 minutes **-2.415 bps at t -2.56**, the only
significant statistic in that table and with the premise's sign reversed). The backlog's
instruction was to test it properly where the power is. New `scripts/sweep_f4.py`; the store is
`data/minute_alpaca`, the universe is the **56 names the intraday sleeve may trade** (the 50
megacaps plus PLTR/MSTR/COIN/SMCI/SOXL/SOXS, all disjoint from the daily champion's book),
**2,664 sessions / 6,654,000 legs, 2016-01-04..2026-09-09**. No file either runner loads was
modified - stage 2 would have run the **shipped** `late_momo` module through the shipped
harness rather than a new one - so AGENTS.md rule (a) owes no replay and the I-1 gate is
unaffected (S-19's precedent). Both standing jobs ran first.

**Pre-registered in the script docstring before the first number was computed**, in seven
clauses. The mechanism is the **sign of the session's return from the open to minute T**,
entered at the open of bar T+1 and held to the framework's 15:38 flatten; the decision
statistic is the per-session **sum** of the legs with the t over sessions (L-1's and X-1's
rule, because legs inside a session overlap and share the market factor); the pass mark is the
one every A-track and X-track candidate has faced - **net positive at t > 2 in at least two of
the three regimes** (2016-2019, 2020-2023, 2024-2026). Two clauses matter for how this entry
should be read. **Clause (4)**: the pre-registered book is the **directional** one the backlog
specified (`raw`); the dollar-neutral version (`neutral`, signal and return both demeaned
against the equal-weight basket) is carried as a **labelled diagnostic** and a pass on it alone
is not a pass on F-4. **Clause (5) wrote the expected outcome down first**: failure on **cost,
not on sign**, which is what X-1's own +0.36 bps against a 4.70 bps round trip predicts - and
in that case F-4 would not be a strategy but the third measurement of an effect whose only
viable instrument is the one F-2a priced at a 0.488 bps round trip. **Clause (6) put the prior
on the record**: A-10 already killed the deployed form of this trade (`late_momo direction=-1`
at 15:00, six names, a 60 bps magnitude filter) at **-$468/day, t -7.38** over 2,686 of these
same sessions.

**(1) The verdict is a clean refusal on the pre-registered rule: 0 of 96 cells** (12 entry
minutes x 2 books x 2 exit conventions x 2 signs). **Every one of the 96 net columns is
negative**, the best being raw momentum entering at 11:30 at **-2.35 bps, t -2.74**, against a
pooled round-trip cost of **4.59 bps per leg** (4.90 in 2016-2019 falling to 4.26 in 2024-2026,
because the per-share commission shrinks in basis points as prices rise).

**(2) But clause (5) is itself refused, and that is the finding.** The failure is not on cost -
it is on **sign**. Over the pooled sample the gross column is **positive at 12 of 12 entry
minutes in the raw book and 10 of 12 in the neutral book**: the day's move *extends*, it does
not fade. Every gross statistic in the whole grid that reaches |t| > 2 is **momentum**:

| book | entry | gross bps | t |
| --- | --- | --- | --- |
| neutral | 11:30 | +1.78 | **+3.54** |
| raw | 11:30 | +2.24 | **+2.61** |
| raw | 15:00 | +0.89 | **+2.48** |
| neutral | 10:00 | +1.56 | **+2.39** |
| raw, 2020-2023 | 15:00 | +2.18 | **+3.38** |
| neutral, 2020-2023 | 15:00 | +1.20 | **+3.63** |

The largest single-regime statistic in the file is **A-10's exact entry minute with the
opposite sign**. The second pre-registered screen - is the effect present but merely
unaffordable? - returns **0 of 48**: the gross reversal never reaches t < -2 in two of three
regimes anywhere.

**(3) Where the effect does survive, it survives as a whisper, and only in the diagnostic
book.** Neutral, afternoon entries, by regime: 2024-2026 **-0.81 / -0.59 / -0.42 bps** at
14:00 / 14:30 / 15:00 (**t -1.11 / -0.98 / -0.85**) and 2016-2019 -0.22 / -0.16 (t -0.68 /
-0.62), against 2020-2023 at +0.87 / +0.24. So the sign X-1 reported is carried in **two of
three regimes** in the afternoon of a dollar-neutral book - and never past **|t| = 1.2**, at
one fifth to one eighth of its own cost. F-4 does not reproduce X-1 and it is worth being
exact about why rather than calling it a contradiction: **X-1 ranked a 15/30/60-minute lookback
and held 30-60 minutes; F-4's signal is the whole session's return held to the flatten.** They
are different objects. What F-4 establishes is that the *session-long* version of the effect -
the one the backlog pre-registered and the one F-2a measured on ES - is not there.

**(4) The counterfactual that prices F-2a's own conclusion, and corrects it.** F-2a closed by
arguing that an effect refused on cost is an argument for buying CME history, because the
instrument is 10x-17x cheaper. That is testable without any new data: hold the measured gross
column fixed and swap the cost column. Charged **F-2a's 0.488 bps ES round trip** instead of
the equity sleeve's 4.59, the same legs give **0 of 24 cells** reaching the pass mark - and
**every cell is still negative**, from -0.37 bps (neutral, 14:30) to -2.73 (raw, 11:30). A
cheaper instrument does not rescue this mechanism; it only makes it lose less. (Upper bound
only, and labelled as one in the script: one future cannot carry a 56-name cross-section.)
**The reusable rule is the correction: a cost refusal is an argument for a cheaper instrument
only when the gross column has the right sign at |t| > 2. When the gross sign is wrong, the
cheap instrument buys a smaller loss, not an edge.** F-2a's cost table stands on its own - it
is a property of the instrument - but the purchase case may not lean on F-4.

**(5) Stage 2 was not run, on the pre-registered rule rather than on convenience.** Clause (7)
earns a framework run only for a stage-1 survivor, and there is none on three separate screens
(net 0/96, gross 0/48, cheap-instrument 0/24). A single confirmation year was started anyway
and abandoned after >30 minutes of wall clock for one year x one entry minute; the honest
reading is that it would have been fitting a book the pre-registration had already refused, and
A-10 has in any case already run this trade's deployed form through the shipped harness over
2,686 sessions. **No ledger rows are written by this iteration** - `intraday_backtest.record`
is only reached from stage 2, and a stage-1 event study is a measurement of bars, not a run of
a strategy.

**Nothing shipped, nothing promoted, no default changed.** Champion unchanged at S-18,
`champion.json`, `live/APPROVED_PAPER.md`, `live/HALT*`, `live/intraday_config.json` and all
three scheduled tasks untouched; `late_momo` keeps `alloc 0.0` from A-10 and its module was not
edited; one new script only, so rule (a) owes no replay.

**Standing jobs both ran.** `slippage_report.py` unchanged at **66 fills / +2.22 bps / se 0.80
/ |diff|/se 0.90** (~4.4 sessions to settle), so `SLIPPAGE_BPS` stays 1.5. `daily_fills.py`:
10 fills / $2,373,115 over three sessions, `ref_price` the previous close in **10 of 10** (a
fifth confirmation of the S-19 clock) - but note the pooled execution number reads **+1.7 bps
(se 5.3)** tonight against **+3.2 (se 4.5)** this afternoon, because the daily store has not yet
published 2026-09-11's closes and today's four fills therefore score NaN rather than entering
the pool. That is a benchmark-availability artifact at 20:4x ET, not a change in execution.

**What it changes for the loop.** F-4 closes the last open item with a stated mechanism, and it
closes it on sign rather than on arithmetic - which is a stronger refusal than F-1's or F-3's,
because those two found a real forecast and could not afford it. **Do not re-open F-4 as an
entry-minute, universe, holding-period or magnitude-filter question**: 6.65M legs over 2,664
sessions is the largest sample this repository has ever put on one mechanism, the grid is
already twelve entry times x two books x two exits, and the pooled sign is the wrong one. The
one thing it leaves genuinely open is the object F-4 did *not* test and X-1 did - a **short**
lookback reversal at a **short** horizon - which is a different mechanism and would have to be
pre-registered as one. The binding constraint remains the owner decisions in `BLOCKERS.md`.

## 2026-09-11 - F-2a: the futures blocker was never a permission problem, and the instrument's round trip is a tenth of anything this repository has refused

**Hypothesis.** The backlog has carried F-2 (the index-futures track) since 2026-09-10 as
"needs owner: IBKR futures permission + CME data, or a Databento key", and after S-24 it is
the last open item with a stated mechanism - everything else is refused, standing, or an
owner decision. Nobody had ever tested that claim. A blocker that has never been probed is
an assumption, and this repository's own rule since S-24 is that an assumption gets measured
or it gets a sign. Two new scripts, `scripts/futures_data.py` (probe, depth, stitch) and
`scripts/sweep_f2.py` (costs, event study, books); **4 ledger rows** under `futures/f2_es`;
no file either runner loads was modified, so rule (a) owes no replay and the I-1 gate is
unaffected (S-19's precedent). Both standing jobs were run first and neither had new input.

**Pre-registered in the script docstrings before the first request, in three clauses.**
(1) UNBLOCKED if IB Gateway returns at least one full session of 1-minute TRADES bars for a
front-month ES/MES/NQ/MNQ contract. (2) BLOCKED if every request is refused - and then the
deliverable is the exact product name and error code, not "needs data". (3) A contract
definition that resolves is **not** evidence of (1): IBKR describes instruments it will not
price, so the test is bars and the number of them. For the research half, added before any
statistic was computed: a mechanism survives only at gross above the cost floor with |t| > 2
and the sign holding in both halves, and **nothing in the file is promotable whatever it
prints**, because 313 sessions is 16% of A-4's ~2,000-session power requirement and A-10 is
the standing lesson about exactly that (260 IBKR sessions kept a strategy 2,686 Alpaca
sessions killed at t = -7.38).

**(1) The permission claim is simply wrong, and that is the first finding.** The paper
account (DUT091359) fetched 2,760 one-minute TRADES bars - two full 23-hour sessions - for
**every one of ES, MES, NQ and MNQ, with zero errors**: no 354 (not subscribed), no 162, no
10197. Daily bars came back for all four as well. There is nothing to buy for access, and an
IBKR CME market-data subscription would buy nothing that is missing.

**(2) What is actually missing is retention, and it took one wrong turn to establish.**
The first depth probe reported that expired quarterlies return error 200 and would have
concluded they were gone. That was an artifact of a **guessed expiry date** - `ES 20260619`
does not exist because the real third Friday is the 18th. Addressed by `localSymbol`
instead, the expired contracts qualify and serve full data: **ESM6 7,740 bars / 5.9M
contracts of volume, ESH6 6,540 / 6.3M, ESZ5 7,455 / 5.5M, ESU5 6,600 / 4.4M** - and
**ESM5 and older return no security definition**. So IBKR retains about **four expired
quarters**. The continuous series is not a way around it: `reqHistoricalData` on a CONTFUT
refuses an `endDateTime` outright (**error 10339, "Setting end date/time for continuous
future security type is not allowed"**) and caps a 1-minute request at one month, so CONTFUT
cannot be paged - a "6 M" and a "1 Y" minute request both time out and are cancelled
server-side. Daily CONTFUT does go back further and is the one long series available:
**ES 826 sessions from 2023-06-19**, NQ 633 from 2024-03-18, MES/MNQ 499 from 2024-09-23.

**(3) So the store was built from what exists**: five dated contracts used only in their own
front quarter, rolling 8 calendar days before expiry, **447,600 one-minute bars over
2025-06-09..2026-09-10 = 313 cash sessions** (`data/futures/ES.parquet`, gitignored).

**(4) The cost floor is the result worth keeping, because it is a property of the instrument
and not of the sample.** One ES contract carries **$347,117** of notional at the sample's
mean price, IBKR Pro charges **$2.05 a side** all-in ($0.85 execution + $1.18 CME + $0.02
NFA) and the book is one tick ($12.50) wide essentially all session:

| | commission | spread | **round trip** |
| --- | --- | --- | --- |
| ES, half tick | 0.121 bps | 0.368 bps | **0.488 bps** |
| ES, full tick | 0.121 | 0.735 | **0.856** |
| MES, half tick | 0.376 | 0.368 | 0.744 |

Against this repository's own measured equity round trips - **L-1 6.40-8.20 bps** on
leveraged ETFs, **X-1 4.70 bps** per megacap leg, **F-1 0.892 bps of commission alone at
zero spread** - the ES round trip is **10x to 17x cheaper**. That matters more than any
single backtest here, because **every intraday refusal this repository has written was a
refusal on cost rather than on signal**: F-1 found a real forecast (pooled OOS IC +0.0113,
t +4.74) and was refused at 0.797 gross bps against a 0.892 bps floor. The same forecast on
this instrument would have cleared its floor by 60%.

**(5) Both pre-registered mechanisms are refused on the 313 sessions.** Sign trades, no
threshold, no sizing, gross:

| mechanism | exit | gross bps | t | 1st half | 2nd half |
| --- | --- | --- | --- | --- | --- |
| M1 overnight (18:00 -> 09:15) into the cash open | 10:00 | **+1.161** | +0.78 | +0.378 | +1.940 |
| M1 | 11:00 | -0.316 | -0.15 | -1.157 | +0.519 |
| M1 | 16:00 | -0.431 | -0.12 | -5.982 | +5.086 |
| M2 day momentum (09:30 -> 15:30) into the last 30m | 16:00 | **-2.415** | **-2.56** | -3.925 | -0.916 |

M1 clears the 0.488 floor at its best horizon and **does not reach |t| = 2 anywhere**; it is
gone by 11:00. M2 is the interesting one: the only statistic in the table that reaches
significance does so **with the sign reversed from the premise** - the last half hour
*fades* the day rather than extending it.

**(6) The reversal is recorded, and it is labelled post hoc, but it is not invented here.**
Flipping M2's sign earns **+2.415 gross / +1.927 net bps at t +2.05, win rate 57%**. The
flip was chosen after reading stage 1, so by this repository's own A-12 precedent it is in
sample by construction, and its halves (-3.925 then -0.916 in momentum terms) say the effect
is concentrated in the first half. What it is not is a new idea: **X-1 already measured
exactly this shape on megacap equities on 2026-09-10** - "+0.63 bps at 10:30 and **-0.69 bps
(t = -2.80) at 14:30** - continuation in the morning, reversion in the afternoon" - on a
different instrument, a different sample and 2,684 sessions, and that entry filed it as
"worth keeping for a later idea". M1's own shape agrees (positive to 10:00, zero after). So
the direction was on record before this table existed; what is not on record is whether it
survives on futures with enough sessions to tell, and 313 cannot tell.

**(7) On the mandate.** The cash session's own gross sd is **0.62% of notional** per
contract before any leverage decision, against the intraday equity sleeve's 0.49% (L-1) and
0.27% (X-1) *after* leverage. This is the first instrument the loop has measured where the
owner's 3-10%/day range is reachable without sizing up an unproven signal - which is the
distinction USER.md draws. It still needs an edge, and this iteration did not find one.

**Decision.** F-2's blocker is rewritten rather than removed. **Nothing shipped, nothing
promoted, no default changed**: champion unchanged at S-18, `champion.json`, `live/*` and
all three scheduled tasks untouched, and no runner-loaded file modified. The purchase request
in `BLOCKERS.md` is now precise and an order of magnitude better justified than "needs data":
it is **historical CME futures history back to ~2016 for ES/NQ** (Databento MDP-3 or
equivalent), **not** an IBKR futures permission or CME market-data subscription, and the
reason to buy it is the 0.488 bps round trip rather than any number in section 5.

**Standing jobs.** Both ran first and neither had new input (the S-24 iteration had already
pooled today's sessions): A-5 part 2 at **66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90**
(~4.4 sessions to settle, constant untouched at 1.50), `daily_fills.py` at **10 fills /
$2.37M / +3.2 bps (se 4.5)** with `ref_price` the previous close in 10 of 10.

**Next.** Nothing further on this track without the history. Two things worth doing on what
exists, neither of which needs the owner: the afternoon-reversal shape is now measured on
two instruments and two samples (X-1's equities at t -2.80, F-2's futures at t -2.56) and
can be tested properly on the **Alpaca store**, which has 2,684 sessions and where X-1 found
it in the first place; and `whatIfOrder` would give the margin-to-notional ratio that turns
section 7's 0.62% into the mandate's own percentage.

## 2026-09-11 - S-24: the harness's "open" is not the opening cross, and the pre-open move survives being priced at the one a real MOO order gets

**Hypothesis.** S-23 left the owner's cheapest decision resting on one unmeasured
assumption. It priced the pre-open move at **+1.85 CAR points** and solved for indifference
- the opening auction may cost up to **3.10 bps more** than the closing one before the move
stops paying - but it could not measure that surcharge, because the only store it had
(Alpaca SIP 1-minute TRADES bars) carries no quotes. It fell back on a proxy, the opening
minute's *range* against the closing minute's (1.0x-2.0x), and wrote "do not re-open as a
'what is the real opening spread' question **from this data**". This is different data: the
same Alpaca key already in `live/secrets.env` serves two endpoints this repository has never
used - `/v2/stocks/auctions` (official opening and closing cross prints, 2016-2026) and
`/v2/stocks/quotes` (full SIP NBBO). New `scripts/sweep_s24.py`; **4 ledger rows** under
`daily/s24_auction`; no file either runner loads was modified, so rule (a) owes no replay and
the I-1 gate is unaffected (S-19's precedent).

**Pre-registered in the script docstring before any fetch, in three clauses.** (1) *Identity*:
if the daily store's own open/close ratio matches the SIP cross ratio on at least 95% of
sessions within 2 bps, the harness's "open" IS the opening cross and an MOO fill carries zero
slippage against it by construction. (2) *Surcharge*: what the opening auction costs against
the market 30 seconds later, minus what a 15:45 market order costs against the market at
15:45. (3) *Verdict* against 3.10 bps, and nothing is promotable - both books are the same
strategy at a different fill.

**(1) The identity fails, and how it fails is the finding.** Pooled, only **82.18%** of
sessions land within 2 bps, against the pre-registered 95%. Splitting the test by leg says
why, and the split is clean: the implied *close* factor `store_close / sip_close` has a
median day-over-day change of **exactly 0.000 bps for all nine names** - **the store's close
is the official closing cross to the cent, every session** - while the implied *open* factor
wobbles 0.6-1.5 bps a day for six of them. On raw recent bars where the dividend factor is 1,
SPY's store open misses the Arca cross by -0.39 / +0.52 / -1.04 / +0.78 bps on consecutive
sessions while its close matches at 0.00 every time, and XLE misses by -10.88 and -7.80 on
two of eight. **Yahoo's daily open is the first consolidated print, not the primary opening
auction.** So the deployed 15:45 convention was already being marked at exactly the right
price, and it is the *pre-open* book - the one the owner is being asked to authorise - that
was priced against a price no MOO order can receive. One instrument check worth keeping: the
"largest print by size" rule for picking the official cross independently recovered each
fund's listing venue (Arca for the seven Arca-listed, NASDAQ for QQQ and TLT) without a
hard-coded listing table.

**(2) So the surcharge was measured directly instead of estimated.** Because the close leg is
exact, `f = store_close / sip_close` recovers each date's whole adjustment - dividend factor
and splits together - and `sip_open x f` puts the real cross on the book's own basis. S-19's
`simulate` reads `frames["open"]`, so the substitution needs no change to that harness.
Over **2,683 sessions (2016-2026)**, 2 bp base spread, today's cost of money:

| cell | CAR% | Sharpe | MaxDD% |
| --- | --- | --- | --- |
| deployed 15:45 MKT (fills at the closing cross) | 22.007 | 1.117 | 24.065 |
| pre-open MOO at the store's open (S-23's assumption) | 24.134 | 1.212 | 23.559 |
| **pre-open MOO at the OFFICIAL opening cross (S-24)** | **23.985** | **1.206** | **23.609** |
| pre-open MOO at the cross, charged no spread (band) | 25.204 | 1.256 | 23.429 |

**The move is worth +1.977 CAR points at the price a real MOO order receives**, against
+2.126 as S-23 priced it on this window: the benchmark defect costs **-0.149 CAR points**
(paired -0.047 bps/day at t -1.86), about **8%** of the move. The store's open sits a
sleeve-weighted **+0.050 bps** better than the cross with a median of exactly 0.000 and mixed
signs - it is a noisy benchmark, not a flattering one, which is why correcting it moves so
little. The fourth row is the other end of a band the loop had not stated: an MOO order is
matched in a single-price call auction and **does not cross a quoted spread**, so charging it
the same 2 bp as a continuous market order is an overcharge of unknown size. **The honest
range for the move is +1.98 to +3.20 CAR points, and +1.98 is the conservative end.**

**(3) Clause 2's own statistic turned out to be mis-specified, and the placebo is what says
so.** On 135 sampled sessions x 4 instants x 9 names (6,074 NBBO rows), the opening cross
sits **6.12 bps** from the mid 30 seconds later, which read naively is a surcharge of 5.75
bps and would refuse the move at the 3.10 breakeven. It is not a cost: an unsigned deviation
has no direction, and the book's direction is set by the previous close, independently of the
auction imbalance. A matched placebo - the *next* 30 seconds, with no auction in them - moves
the same names **4.10 bps**, so two thirds of it is simply what these names do in 30 seconds
at the open; signed, the cross sits **-0.213 bps** from fair value with mixed signs across the
nine. The arithmetic closes it without the quotes at all: S-17 measured this book at **0.68
CAR points per basis point** of one-way cost, so a systematic 6.1 bps auction cost would be
worth ~4.2 CAR points, and the direct substitution above found **0.149**, i.e. ~0.22 bps.
**The 6 bps is drift.** Recorded as a reusable rule: on this sleeve an execution cost has to
be measured with a sign, or by re-filling the book, never as an unsigned distance.

**What the quotes do establish is an operational risk, not a cost.** The quoted spread at
09:30:00 is **4.63x** the closing one sleeve-weighted - far worse than the 1.0x-2.0x range
proxy S-23 had to use - and it is concentrated in exactly the names that need it least:
**XLK 12.7x (5.00 bps half-spread), XLE 11.7x (6.82 bps)** against SPY 3.0x (0.28 bps). It
decays fast (XLK 5.00 -> 1.52 bps by 09:30:30). None of that is what an MOO order pays, but
it is precisely what a *fallback* market order would pay if the MOO were ever missed - so it
raises the value of the clock guard S-23 already built, and it is an argument against any
future "send a market order at the open instead" shortcut.

**Decision.** Nothing promoted, nothing shipped, no default changed: `--order-type` still
defaults to `MKT`, `champion.json`, `live/APPROVED_PAPER.md`, `live/HALT*`,
`live/intraday_config.json` and all three scheduled tasks untouched, and the only tracked
changes are one new script and the ledger. **The recommendation to the owner is unchanged and
is now better supported than it was**: the surcharge S-23 could only bound is measured, it is
about 0.22 bps against a 3.10 bps breakeven - **7% of the budget** - and the move is worth
**+1.98 CAR points** conservatively charged. `BLOCKERS.md` is corrected in place.

**Standing jobs both ran and both had no new input** (S-23 had already pooled today's session
after the close): A-5 part 2 unchanged at 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90
(~4.4 sessions to settle), `daily_fills.py` unchanged at 10 fills / $2.37M / +3.2 bps (se 4.5)
with `ref_price` the previous close in 10 of 10.

**Next.** The owner decision is unchanged and now fully priced; the loop has nothing further
to add to it. `daily_fills.py` scores MOO fills against the open they aim at, and S-24 has
now established that the open it should be scored against is the **official cross**, not the
store's open - a one-line correction that the first post-move session will exercise.

## 2026-09-11 - S-23: the pre-open MOO path is written and verified, and the move it buys survives up to 3.1 bps of extra opening-auction cost

**Hypothesis.** `BLOCKERS.md` has asked the owner since S-17 to move the daily task to a
pre-open slot, and S-22 priced the move at **+1.85 CAR points** on an honestly-costed book.
Two things were missing and neither is a strategy question. **(1) The loop's half of the
request was never written**: the page promises "say the word and the loop will write the
`--order-type` OPG/MOO support", so the owner has been asked to schedule a run that the
runner could not have executed. **(2) Every version of the +1.85 assumes the opening
auction fills at the same price as the closing one**, which is the one assumption a
reasonable person pushes on - the closing cross is the deepest print of the US day and the
opening cross is not. So the decision-shaped question is not "what is the move worth", it
is **"how much more than the closing auction would the opening auction have to cost before
the move stops paying"**. That has the same units as `daily_fills.py` measures on live
fills, which turns an unfalsifiable worry into something the next fifty fills settle.

**Pre-registered before the sweep ran.** (1) Not a candidate and not promotable: both cells
are the *same* strategy at a different fill, so the winner is known in advance and only its
margin is in question; `evaluate.py` is not the judge. (2) The deployed default must not
move - MKT stays the default, the 15:45 task keeps behaving exactly as it does today, and
the I-1 gate must still pass at 3,689/3,689 and 5,021 orders or the code change is reverted.
(3) The breakeven is reported against the *measured* live execution cost, not against zero.

**What was built.**
- `scripts/paper_trade.py`: `--order-type MOO`. IBKR has no "MOO" order type - an
  opening-auction order is a plain `MKT` carrying `tif="OPG"` - so the three supported types
  now go through one `build_order()` helper. Because IBKR rejects `OPG` outside 04:00-09:28
  ET, and rejecting them one at a time would leave the book half rebalanced, `--order-type
  MOO` checks the clock **once, before connecting**, and refuses with exit 3. Verified live:
  at 17:51 ET it printed `REFUSED: --order-type MOO needs a weekday between 04:00 and 09:28
  ET ... it is Fri 17:51 ET. No orders sent.` without opening a socket. `--ignore-clock` is
  there for testing only. MOO and MOC fills are also no longer waited on - they settle at an
  auction that has not happened yet, so the run confirms acceptance and says "queued for the
  open" rather than reporting a fill of zero.
- `scripts/daily_fills.py`: a fill's reference price now depends on the order type it came
  from. A 15:45 MKT aims at that session's close; **a pre-open MOO aims at that session's
  open, which is also what the backtest fills at**, so for MOO the execution column and the
  convention column collapse onto each other - and that collapse is precisely what the task
  move is meant to buy. Once both types are present the pooled block prints them separately,
  because the breakeven below is an open-minus-close difference.
- `scripts/sweep_s23.py`: both conventions through S-19's share-level book with S-22's
  financing hook, halves, the paired statistic, the breakeven solve, and a minute-store
  liquidity read. **4 ledger rows** under `daily/s23_preopen`.

**(1) What the move is worth, both books fully charged** (2 bp spread + IBKR Pro financing,
3,689 sessions, book units; add **+0.314** for LEAN units, the S-22 offset):

| financing | convention | CAR% | Sharpe | MaxDD% | orders | fees | interest |
| --- | --- | --- | --- | --- | --- | --- | --- |
| historical (`usd_benchmark`) | deployed 15:45 MKT | 19.640 | 1.047 | 24.04 | 5,054 | $19,121 | -$86,303 |
| historical | **pre-open MOO** | **21.515** | 1.136 | 24.33 | 5,048 | $20,902 | -$100,823 |
| today's 3.63% (`usd_flat_2026`) | deployed 15:45 MKT | 19.102 | 1.023 | 24.06 | 5,056 | $18,141 | -$85,514 |
| today's 3.63% | **pre-open MOO** | **20.946** | 1.111 | 24.67 | 5,045 | $19,754 | -$96,895 |

**+1.875 CAR points at historical rates and +1.844 at today's**, which reproduces S-22's
+1.85 on an independent path, and the deployed row lands on S-22's own 19.640 to the digit.
**Say the error bar out loud**: paired **+0.609 bps/day at t +1.44** (and +0.601 at t +1.42),
so this still does not reach |t| = 2 on 3,689 sessions - the same thing S-19 said. The
reason to make the change is that the *defect* is certain (`ref_price` has been the previous
close in 10 of 10 paper fills) and not that 1.9 points are measured with confidence. The
gain is **out-of-sample weighted more than three to one**: IS 2012-2019 **+0.963** (15.280
against 14.317), OOS 2020-2026 **+3.222** (29.189 against 25.967). It also costs a little
risk, unlike the clock alone: drawdown 24.33 against 24.04, and the book finances more
(-$100.8k against -$86.3k) because an earlier fill carries the position one session longer.

**(2) The number this iteration exists for.** Charging the opening auction a surcharge over
the closing one and solving for indifference: **the opening auction may cost up to 3.10 bps
MORE than the closing auction (2 -> 5.10 bp all-in) before the move stops paying**, and 3.07
bps at today's cost of money. For scale, the deployed 15:45 market orders measure **+3.2 bps
against the close they aim at** (`daily_fills.py`, 10 fills, se 4.5) and a half-cent tick on
this sleeve is 0.27-0.77 bps (S-17). **So the opening auction would have to be roughly twice
as expensive as the closing one for the move to be a wash.**

**(3) Is it? The one read the data supports, labelled as a proxy.** Alpaca SIP minute bars
carry no quotes, so the auction spread is not observable here; what is observable is how
much of the day trades in the first minute against the last, and how wide those minutes are:

| symbol | sessions | open minute, % of day's volume | close minute | open range bps | close range bps | ratio |
| --- | --- | --- | --- | --- | --- | --- |
| SPY | 2,687 | 1.22 | 3.46 | 10.67 | 10.29 | 1.04 |
| QQQ | 2,687 | 1.78 | 2.49 | 16.43 | 10.66 | 1.54 |
| IWM | 2,687 | 1.36 | 2.75 | 21.75 | 10.86 | **2.00** |
| TQQQ | 2,687 | 1.98 | 1.11 | 48.55 | 30.23 | 1.61 |

The open is thinner and wider in every name, by **1.0x to 2.0x**, and IWM - which the book
holds today - is the worst of the three sleeve names in the store. Read against a 3.2 bps
measured execution cost, a 2.0x opening auction would cost **+3.2 bps extra against a 3.10
bps breakeven**: the move would be a wash rather than a loss. **That is the honest
conclusion and it is not the comfortable one.** The proxy overstates the risk - a minute's
high-low range is continuous trading, while an MOO order fills in the opening *cross*, a
single crossing whose price is not the first minute's range - but the margin is thinner than
the +1.85 alone suggests, and this is the first time anyone has put a number on the other
side of the trade.

**(4) Nothing shipped, nothing promoted, no default changed.** `--order-type` still defaults
to `MKT`; the `--mock --dry-run` plan is identical to before the change (XLE/XLK/IWM at
1.50x gross, margin 0.75, as of 2026-09-10); the **I-1 gate passes 3,689/3,689 at 5,021
orders on both sides**; `champion.json`, `live/APPROVED_PAPER.md`, `live/HALT*`,
`live/intraday_config.json` and all three scheduled tasks are untouched; `signals.py` and
`main.py` were not modified, so the intraday sleeve's replay rule owes nothing here. The only
write into `live/` was the runner's own refusal log line from the clock-gate test.

**Standing jobs both ran first and both had no new input** (17:3x ET, after today's close but
after the S-22 iteration had already pooled today's session): A-5 part 2 unchanged at 66
fills / +2.22 bps / se 0.80 / |diff|/se 0.90 (~4.4 sessions to settle), `daily_fills.py`
unchanged at 10 fills / $2.37M / **+3.2 bps (se 4.5)** with `ref_price` the previous close in
10 of 10.

**Decision.** The request to the owner stands and is now a *one-line* request: move "Quant
Paper Rebalance" to before 09:28 ET and add `--order-type MOO`. The loop's half is written,
clock-guarded and gated. **What changed in the case for it**: the payoff is unchanged at
+1.85, but it is no longer quoted against an assumption - it survives up to 3.1 bps of extra
opening-auction cost, and the only evidence available says the opening minute is 1.0-2.0x as
wide as the closing one, so the margin is real but thin. **What settles it is live fills,
not another backtest**: `daily_fills.py` now measures MOO fills against the open they aim at,
so the first session after the move produces the number that decides whether the +1.85 was
collected.

**Next.** Nothing on the daily sleeve is unblocked that is not an owner decision. The two
standing measurements continue (A-5 part 2 ~4.4 sessions out), and F-2 still needs data the
human must buy.

## 2026-09-11 - S-22: the three instrument corrections charged together, and the first honest expectation for the deployed daily book

**Hypothesis.** S-17 (no spread), S-19 (the runner's clock) and S-21 (no financing) each
priced one harness defect against a clean control, and each was reported alone. Charged at
once they should compose, and the composite - not the champion's headline 24.403% - is what
the paper account should be expected to earn. Three reasons the sum is not obviously the
answer: a staler signal changes *which* trades fire and so moves the spread bill; financing
is charged on a cash path the other two corrections both move; and CAR is geometric.

**Pre-registered in `scripts/_s22_runs.sh` before any cell ran.** (1) A measurement, not a
candidate: every cell charges a cost the control does not, so every cell must lose and
`evaluate.py` is not the judge (it already refuses `S1_FINANCING=on` as not comparable).
(2) The a-priori prediction, written down first so the composite could be wrong rather than
merely reported: composing the three singles multiplicatively in (1+CAR) gives **18.81%**
for the LEAN triple, against 18.73% if the points simply added; **the test was |measured -
multiplicative| <= 0.5 CAR points**. (3) The headline is the *deployed* convention, which
LEAN cannot express, so it had to come from the S-19 pandas book and is readable only if
that book reproduces LEAN's financing drag. (4) One scenario cell, labelled as such.
(5) Nothing shipped, no default changed.

**What was built.** `scripts/_s22_runs.sh` (7 LEAN cells), `scripts/sweep_s22.py`
(`--report` reads the 2^3 factorial out of the ledger and runs the composition test;
`--book` runs the pandas book), and **one optional argument on `scripts/sweep_s19.py`**:
`simulate(..., financing=...)` accrues interest on the settled cash balance at the top of
each session for the calendar days since the last, before the day's sizing, exactly as
`main.py:accrue_financing` does. Default `None` leaves every S-19 row bit-identical, and the
full-period clean cells reproduce S-19 to the digit (24.077 / 22.192 / 20.965). **25 ledger
rows.** Control reproduces **`OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`**.

**(1) The factorial, and the corrections are independent.** Full period, LEAN:

| cell | CAR% | drag | Sharpe | MaxDD% | fees |
| --- | --- | --- | --- | --- | --- |
| control (as promoted) | 24.403 | - | 0.994 | 23.70 | $27,200 |
| spread 2 bp (S-17/S-18) | 23.068 | -1.335 | 0.938 | 25.00 | $24,921 |
| financing (S-21) | 23.087 | -1.316 | 0.939 | 24.10 | $25,313 |
| clock bound, lag1 (S-19) | 21.384 | -3.019 | 0.860 | 22.70 | $23,808 |
| spread + financing | 21.745 | -2.658 | 0.882 | 25.40 | $23,211 |
| spread + clock | 20.074 | -4.329 | 0.805 | 22.90 | $21,929 |
| financing + clock | 20.095 | -4.308 | 0.806 | 22.80 | $22,278 |
| **all three** | **18.785** | **-5.618** | **0.750** | 23.00 | $20,565 |

The multiplicative null is **18.811** and the measured triple is **18.785**: the interaction
is **-0.026 CAR points**, and every pair is inside 0.021. **The three corrections are
independent to a fortieth of a point**, so the loop may keep pricing them one at a time and
compose them afterwards - which is the useful half of this result, because it means the
three audits did not need to be re-run against each other.

**(2) The headline, from the book that can fill where the runner fills.** The pandas book
agrees with LEAN's financing drag at the backtest convention (**-1.357 against -1.316**) and
its fully-charged `lag1` cell translates to **18.755** in LEAN units against LEAN's own
**18.785** - two harnesses, **0.03 CAR points apart**, on the one cell both can run:

| what it is | book CAR% | in LEAN units | against the promoted 24.403% |
| --- | --- | --- | --- |
| the champion as reported | 24.077 | 24.403 | - |
| the deployed 15:45 clock alone (S-19) | 22.192 | 22.513 | -1.890 |
| **the deployed book, fully charged** | **19.640** | **19.954** | **-4.449** |
| the same at today's 3.63% cost of money | 19.102 | **19.415** | **-4.988** |
| the pre-open fix, fully charged, today's rates | 20.946 | 21.264 | -3.139 |

**So the number to carry is ~20% CAR, not 24.4%** - the promoted headline is about **18%
high**, and 20% at today's price of money. This is not a defect and nothing is broken: the
paper account has been paying all three since its first fill.

**(3) The correction is out-of-sample weighted, again.** LEAN's triple by half: **IS
2012-2019 14.194% against 17.698%** (-3.504 points, -2.98% in wealth terms) and **OOS
2020-2026 24.259% against 32.801%** (-8.542 points, **-6.43%**) - more than two to one, the
same shape S-21 found and for the same reason (82% of the interest was incurred in
2023-2026). **And it costs return, not risk**: drawdown across the whole factorial moves
23.70 -> 23.00, and realized vol 0.155 -> 0.156.

**(4) One thing it changes for the owner, and it is not the risk posture.** The pre-open fix
in `BLOCKERS.md` is worth **+1.85 CAR points on an honestly-costed book at today's rates**
(19.415 -> 21.264), which is close to the -1.9 S-19 measured on an uncosted one, because the
clock and the two costs do not interact. The Reg-T frontier is untouched by this iteration
and stays where S-21 left it.

**Decision.** Measured, not judged. **Nothing shipped, nothing promoted, no default
changed**: `S1_SLIPPAGE_BPS` stays 0.0, `S1_SIGNAL_LAG` stays 0 and `S1_FINANCING` stays off
so the ledger stays on one scale (S-17's and S-21's precedent); champion unchanged at S-18;
`live/*` and the three scheduled tasks untouched. `signals.py` and `main.py` were not
modified, so rule (a) owes no replay, and the **I-1 gate was re-run anyway: 3,689/3,689
dates, 5,021 orders both sides**. `champion.json` carries the expectation as a recorded
note and `BLOCKERS.md` is updated in place.

**Standing jobs.** `daily_fills.py` **has new input** - today's rebalance now shows 4 fills
(the 15:51 TQQQ sale is in), pooling to **10 fills / $2.37M / +3.2 bps (se 4.5)** against
9 / +3.9 / se 5.0, with `ref_price` the previous close in **10 of 10**, a fourth confirmation
of the S-19 clock. A-5 part 2 unchanged at **66 fills / +2.22 bps / se 0.80 / |diff|/se
0.90** (~4.4 sessions to settle), so `intraday_common.SLIPPAGE_BPS` stays 1.50. One
instrument note: `slippage_report.py` reads the parquet minute store and **fails under
`py -3.11`** (no `pyarrow` in that interpreter); it runs under the default `python`, which is
what AGENTS.md prescribes for utility scripts. Nothing was installed.

**Next.** The instrument audit is finished - spread, clock and financing are measured,
composed and proved independent, and there is no fourth defect of that kind left to find.
The unblocked work is back to the two standing per-session measurements and per-session ops;
everything else is one of the four owner decisions in `BLOCKERS.md`, of which the cheapest
and now the best-priced is the pre-open task move.

## Paper session 2026-09-11

Operations only, no research. Account DUT091359, net liquidation 988,089.19 at 15:49 ET.

| sleeve | trades | P&L | costs | worst event |
| --- | --- | --- | --- | --- |
| intraday `active` | 34 | -201.99 (realized, closed) | 57.95 | 17 `notify_failed` (no `live/alerts.json`); no halt, no loss_limit, no error |
| daily `s1_momo` | 3 | -3,414.56 unrealized on the book | IBKR commission, not itemized in log | `foreign_positions_ignored` for TQQQ 3,227 sh (~229.8k) at the 15:45 rebalance |

- **Intraday.** Two `start` events (09:25 launch at equity_frac 0.50, 09:33 relaunch at 0.25;
  the 09:33 preflight replay of 2026-09-10 passed). 34 orders, 34 fills across 15 names
  (PLTR and AVGO 4 fills each, the rest 2). `end` at 15:42 ET with `positions: {}` - the
  sleeve ended flat, and `live/state/intraday_book.json` confirms empty `pos`. No flatten run
  was needed. Costs of 57.95 against -201.99 realized: the day's loss is signal, not friction.
- **Daily 15:45 rebalance.** Plan `s1_momo` as of 2026-09-10, regime risk-on (vol 0.0854 vs
  median 0.127), vol_scale 1.9658, gross weight 1.50. Targets XLE 0.5154, XLK 0.3755,
  IWM 0.6091 on net_liq 988,671.84. Orders sent and all filled at 15:46:33:
  BUY IWM 2,093 @ 289.19 (ref 287.70), SELL XLE 942 @ 65.10 (ref 64.93),
  SELL XLK 286 @ 187.90 (ref 185.22). The 15:49 re-plan emitted no orders, so the book is
  on target. Resulting positions: IWM 2,093, XLE 7,847, XLK 2,004, TQQQ 3,227.
- **Flag for the owner.** TQQQ 3,227 shares is outside the `s1_momo` universe and the runner
  logs it as `foreign_positions_ignored` every session - it is neither managed nor hedged by
  either sleeve. It is also a daily-sleeve instrument sitting in an account the intraday
  sleeve trades, so the disjoint-universe rule is intact but the position is orphaned.
  No action taken (flattening it changes risk posture and is the owner's call).
- **Also.** `live/alerts.json` is missing, so every notify attempt fails in both logs.
  Cosmetic today, but it means a real halt would go unannounced.

## 2026-09-11 - S-21: the book has been borrowing half its equity for free for twenty-one iterations, and 82% of what that costs was incurred in the last four years

- **What.** The backlog's unblocked work is two standing measurements and four owner
  decisions, so this iteration took the next instrument audit in the S-17 / S-19 line rather
  than a twelfth mechanism. The defect is read off the engine source, not inferred:
  `Common/Brokerages/DefaultBrokerageModel.cs:368` returns `MarginInterestRateModel.Null`,
  `Common/Securities/IMarginInterestRateModel.cs:41` defines that as a class whose
  `ApplyMarginInterestRate` has an **empty method body**, and
  `InteractiveBrokersBrokerageModel` does not override it. **LEAN charges no interest on a
  debit balance and pays none on a credit balance.** The shipped champion carries 1.50x
  gross against 1.00x of equity - a margin loan of about half its equity on every invested
  day - and it has never paid a cent for it. New `scripts/rates.py` (FRED `DFF`, IBKR's USD
  "BM", plus the Pro tier schedule), `scripts/sweep_s21.py` (`--probe`, `--schedule`,
  `--report`) and `scripts/_s21_runs.sh`; one knob on the shipped algorithm
  (`S1_FINANCING`, default **off**) with `S1_FIN_SPREAD` / `S1_FIN_RATES`; **8 ledger rows**
  plus a tagged 2023Q1 smoke row, control reproducing **`OrderListHash
  a6d6224ce9c70091e5bfa8e96f046bf3`**.
- **Say first what this is not.** S-17 (the missing spread) and S-19 (the runner's stale
  clock) were both defects that could in principle be *fixed*. This one cannot: there is
  nothing wrong with the runner, the paper account is already paying this every day, and the
  only thing the measurement changes is the expectation. The rule was pre-registered in
  `_s21_runs.sh` before any full cell ran, and its first clause is that **charging a cost can
  only lower CAR, so nothing here is promotable and `evaluate.py` is not the judge**; the
  deliverables are the corrected champion figure, the split by half, and the corrected
  owner frontier. The a-priori estimate was written down first too (~1.45 CAR points, from
  0.50x debit at a ~2.9% mean loan rate) so the accrual could be wrong rather than merely
  reported; it came in at 1.32, and a 2023Q1 smoke run reproduced a hand-computed $975
  against LEAN's $1,010.88 before any full-sample cell was believed.
- **(1) The state, which is a fact about the strategy rather than the broker.** The probe
  walks the shipped signal through the share-level book S-19 validated against LEAN's own
  equity curve (corr 0.99650) and records the cash balance every session: **a debit balance
  on 3,073 of 3,689 sessions (83.3%)**, mean gross exposure 1.250x, mean debit **0.410x of
  equity over all days and 0.493x over debit days**, and **616 sessions in credit (16.7%)** -
  which is S-20's risk-off count (16.0%) arriving by a completely different route, and is the
  cross-check that the cash path is the strategy's and not an artifact. LEAN's own accrual
  reports the identical state (**mean debit 0.493x**, 3,047 debit days, credit earned within
  1.4% of the probe's) and 11% less interest paid, which is exactly the direction compounding
  predicts: the financed book is smaller, so it borrows less.
- **(2) The calendar is the finding.** The benchmark is not stationary, so a single
  full-period number hides where the money went. Probe, by year, simple drag at constant
  equity:

  | year | mean BM | debit/equity | blended loan rate | $ interest | CAR points |
  | --- | --- | --- | --- | --- | --- |
  | 2012-2016 | 0.09-0.39% | 0.40-0.50 | 1.59-1.90% | $0.9-1.5k | 0.66-0.84 |
  | 2017 | 1.00% | 0.498 | 2.45% | $2,804 | 1.238 |
  | 2018-2022 | 0.08-2.16% | 0.19-0.47 | 1.26-3.65% | $0.5-4.2k | 0.16-1.18 |
  | **2023** | **5.03%** | 0.499 | **6.14%** | **$28,450** | **3.115** |
  | **2024** | **5.14%** | 0.460 | **6.21%** | **$31,273** | **2.535** |
  | 2025 | 4.21% | 0.404 | 5.25% | $22,652 | 1.477 |
  | 2026 (170 sessions) | 3.63% | 0.440 | 4.66% | $24,246 | 1.689 |

  Total $129,406 simple (paid $151,712, earned $22,306), mean drag **0.439 bps/day = 1.106
  simple CAR points**. **$106,621 of that $129,406 - 82% - was incurred in 2023-2026**, partly
  because the book is larger by then and mostly because the loan rate quadrupled. So the
  forward-looking number at today's benchmark is not 1.3 points; the 2026 row prices it at
  **1.69 simple, about 2.0 once it compounds**.
- **(3) LEAN, charged to the cash book so it compounds against the equity the next day is
  sized from.** Cells against their own unfinanced baselines:

  | cell | financed | unfinanced | delta |
  | --- | --- | --- | --- |
  | full period, 0 bp | **23.087% / 0.939 / DD 24.1** | 24.403% / 0.994 / 23.7 | **-1.316 CAR** |
  | full period, 2 bp | 21.745% / 0.882 / 25.4 | 23.068% / 0.938 / 25.0 | -1.323 |
  | IS 2012-2019 | 16.791% / 0.864 / 24.1 | 17.698% / 0.911 / 23.7 | -0.907 |
  | **OOS 2020-2026** | **30.774% / 1.037 / 23.4** | 32.801% / 1.108 / 23.3 | **-2.027** |

  **The correction is out-of-sample weighted at more than two to one**, which matters because
  the OOS half is the one the S-18 promotion leaned on. It costs return and a little risk
  (Sharpe -0.055, drawdown +0.4 points): a debit balance is paid whether the book is up or
  down. No t-statistic is quoted and none should be - unlike S-19's clock this is a
  deterministic charge, certain in a way none of the S-track's mechanisms are.
- **(4) Half of it is the cost of money and half is the price list.** `S1_FIN_SPREAD` shifts
  every tier together, so the answer does not rest on one broker. Same cash path, only the
  rate on it moving (probe, simple CAR points): **benchmark only 0.559**, tiers -1.00pp
  0.557, -0.50pp 0.845, **IBKR Pro published 1.106**, +0.50pp 1.356. The benchmark-only row is
  the part that is arithmetic - no lender charges below its own funding cost - so roughly
  **0.56 of the 1.11 is irreducible and the rest is IBKR's markup**, which a larger account
  pays less of (+0.75% above $1M against +1.50% on the first $100k). One honest correction to
  the run set: the LEAN `floor` cell (-1.50pp, 24.136%, -0.267 CAR) is labelled as the
  benchmark and **is not** - shifting every tier down by 1.50 puts the tranches above $100k
  *below* the benchmark, so that cell is a lower bound on the lower bound, and the
  benchmark-only figure is the probe's 0.559 rather than 0.267.
- **(5) The one thing that changes a decision, and it was pre-registered as such.** The
  owner's open Reg-T question in `BLOCKERS.md` is *exactly* a decision about how large a debit
  balance to carry, and it has been asked on numbers that charge nothing for it:

  | margin_budget | unfinanced | gain | financed | gain | Sharpe (fin.) | MaxDD (fin.) |
  | --- | --- | --- | --- | --- | --- | --- |
  | 0.75 (shipped) | 24.403% | - | **23.087%** | - | 0.939 | 24.1% |
  | 0.80 | 25.903% | +1.500 | **24.296%** | **+1.209** | 0.944 | 25.6% |
  | 0.82 | 26.474% | +2.071 | **24.742%** | **+1.655** | 0.945 | 26.2% |

  **The reward for spending the buffer is overstated by about a fifth**, and the Sharpe
  argument is the part that really thins: unfinanced, Sharpe rises 0.994 -> 1.012 across the
  frontier; financed it rises 0.939 -> 0.945, a sixth as much, while drawdown still climbs
  2.1 points. **The frontier flattens, it does not invert** - the ordering and the sign are
  unchanged - so this is a correction to the owner's brief, not a new recommendation, and
  `BLOCKERS.md` now carries both columns.
- **Decision: nothing promoted, nothing shipped, no default changed.** `S1_FINANCING` stays
  **off** and the ledger stays on one scale, exactly as S-17 left `S1_SLIPPAGE_BPS` at 0.0
  rather than silently re-basing every past row; the correction lives in `champion.json` as a
  recorded note and in `BLOCKERS.md` as a second column. One instrument fix went with it:
  `evaluate.py` now **refuses** any run recorded with `S1_FINANCING=on` as not comparable,
  which is S-18's same-cost-model rule on a third axis - and note the direction, because this
  one *understates* a candidate rather than flattering it, which is the failure mode that
  quietly buries a good strategy. Verified: the financed cell returns "does NOT beat
  champion" with the new reason first, the control ties itself.
- **No-ops.** `signals.py` was not touched, so the daily runner loads identical code and
  AGENTS.md rule (a) owes no replay; the intraday trader's execution, risk and flatten code
  was not touched either. The control reproduces `OrderListHash
  a6d6224ce9c70091e5bfa8e96f046bf3` and the I-1 gate re-ran anyway: `compare_orders.py`
  passes **3,689/3,689 at 5,021 orders** on both sides. `live/APPROVED_PAPER.md`,
  `live/HALT*`, `live/intraday_config.json` and the three scheduled tasks untouched; champion
  unchanged at S-18.
- **Standing jobs, both run after the close.** A-5 part 2 has **no new input beyond S-19** -
  today's intraday session was already in it - pooled **66 fills / +2.22 bps / se 0.80**
  against the shipped 1.50, `|diff|/se 0.90`, ~4.4 sessions to settle, so `SLIPPAGE_BPS` is
  untouched. `daily_fills.py` **does** have new input: today's 15:45 rebalance filled IWM /
  XLE / XLK for $720,338, taking the pool to **9 fills / $2.14M / +3.9 bps against the close
  the runner aims at (per-fill sd 14.9, se 5.0)**, up from 6 fills / +2.9 bps - and
  `ref_price` was the previous session's close in **9 of 9**, the S-19 clock defect confirmed
  for a third session.
- **Next.** S-21 opens nothing and closes nothing that was open; it moves a number. The
  daily sleeve's three instrument audits now read: the missing spread (S-17, 0.68 CAR per bp),
  the runner's clock (S-19, -1.9 CAR, `|t| < 2`, fixable) and financing (S-21, **-1.32 CAR
  full period, -2.03 out of sample, ~2.0 forward, certain, not fixable**). The unblocked work
  is still the two standing measurements and the four owner decisions, and the Reg-T question
  is now posed on honest numbers.

## 2026-09-11 - S-20: the regime gate's off-state does not want to be a defensive holding, and the reason is the one every other lever on this sleeve gave

- **What.** The backlog holds no open research item that is not blocked on the owner or on
  data the human must buy, so this iteration took the one thing on the daily sleeve that is
  neither a ranker lever nor a risk-posture parameter: `risk_on` has switched the whole book
  off in a volatility crisis since S-1, and it has only ever had **one** off-state, cash.
  S-15 priced the switch itself and it stays (turning it off earns +2.02 CAR and costs 6.3
  points of drawdown - it is a drawdown instrument). S-20 asks a different question: same
  gate, same trigger, something else held while it is pulled. New `scripts/sweep_s20.py`
  (`--probe`, `--report`) and `scripts/_s20_runs.sh`; three parameters on the shipped
  algorithm, all defaulting to the champion (`risk_off_sleeve` empty, `risk_off_top_n`,
  `risk_off_exposure`) with matching `S1_RISK_OFF_*` overrides; **9 ledger rows**.
  Nothing shipped, nothing promoted.
- **Pre-registered before any LEAN cell ran**, and written into `_s20_runs.sh` at the top:
  the primary cell is the shipped momentum ranking run over a three-name defensive sleeve
  (same score, same absolute entry floor, cash when nothing is trending), it must pass
  `evaluate.py` at **0 bp and at 2 bp** (S-18's same-cost-model rule) and must not lose the
  2020-2026 out-of-sample half, and **TLT alone** is carried as the a-priori control - what
  a researcher writes down before looking at anything.

### 1. The state, measured before the strategy (`--probe`)

Over 2012-01-03..2026-09-04 the gate is off on **590 of 3,690 sessions (16.0%)** in **29
episodes**, median length 15 sessions, longest 72 (2018-10-10..2019-01-24). Held one
session forward, against cash = 0:

| name | bps/day | t | annualized | worst day | same, risk-on |
| --- | --- | --- | --- | --- | --- |
| TLT | +1.68 | 0.35 | +4.3% | -6.67% | +0.29 |
| IEF | +1.86 | 0.96 | +4.8% | -2.51% | +0.36 |
| **GLD** | **+9.92** | **2.20** | **+28.4%** | -3.99% | +1.85 |
| SLV | +7.36 | 0.97 | +20.4% | -12.34% | +3.17 |
| HYG | +0.92 | 0.26 | +2.3% | -5.50% | +2.14 |
| SPY | +6.57 | 0.88 | +18.0% | **-10.94%** | +6.02 |

Two readings the LEAN cells then have to survive. **(a) The gate is not avoiding down
markets.** SPY earns +6.57 bps/day on exactly the sessions the book sits out; what it is
avoiding is the -10.94% day. **(b) Nothing here is conditional on the crisis.** Risk-off
minus risk-on is +1.39 / +1.50 / +8.07 bps for TLT / IEF / GLD at **t 0.28 / 0.73 / 1.66** -
so "hold gold" and "hold gold in a crisis" are not distinguishable in this sample, and only
the first of those is a mechanism the gate is needed for. The shipped momentum blend picking
among the three earns **+5.35 bps/day at t 1.13** (GLD 267 sessions, TLT 198, IEF 38, cash 87).

### 2. LEAN, nine cells, control reproducing `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`

| cell | orders | CAR | Sharpe | MaxDD | ann.std | PSR | fees |
| --- | --- | --- | --- | --- | --- | --- | --- |
| control (the promoted champion, off-state = cash) | 5,128 | **24.403%** | **0.994** | **23.7%** | 0.155 | 33.2% | $27,200 |
| **primary: TLT/IEF/GLD, top 1** | 5,304 | **26.550%** | 0.972 | 25.4% | 0.177 | 28.8% | $33,990 |
| primary at 2 bp | 5,305 | 24.982% | 0.914 | 25.7% | 0.177 | 21.7% | $30,493 |
| a-priori control: TLT alone | 5,239 | 24.819% | 0.935 | **23.3%** | 0.171 | 24.5% | $34,092 |
| post-hoc: GLD alone | 5,246 | 27.735% | **1.040** | 25.4% | 0.172 | 38.5% | $33,737 |
| primary, top 2 of 3 | 5,603 | 25.968% | 1.004 | 25.4% | 0.165 | 33.8% | $34,657 |
| primary at half exposure | 5,304 | 26.550% | 0.972 | 25.4% | 0.177 | 28.8% | $33,990 |

Halves for the primary, against S-18's champion rows (IS 17.698 / 0.911 / 23.7, OOS 32.801 /
1.108 / 23.3): **IS 2012-2019 19.135% / 0.915 / 21.3%** (+1.44 CAR, better Sharpe, 2.4 fewer
points of drawdown) and **OOS 2020-2026 35.905% / 1.074 / 25.4%** (+3.10 CAR, 0.034 less
Sharpe, 2.1 more points of drawdown). So the return gain is in **both** halves, which is more
than most things this loop has measured can say.

### 3. And it is still refused, on the column that has refused everything else here

The gain is bought with volatility: realized std goes **0.155 -> 0.177**. Scaling the
control's own CAR to each cell's realized vol - the comparison S-15 made compulsory on this
sleeve, because 71% of this book's return is its sizing machinery:

| cell | ann.std | CAR | control at the same vol | excess |
| --- | --- | --- | --- | --- |
| primary | 0.177 | 26.550% | 27.867% | **-1.317** |
| primary at 2 bp | 0.177 | 24.982% | 27.867% | -2.885 |
| a-priori TLT alone | 0.171 | 24.819% | 26.922% | -2.103 |
| primary, top 2 of 3 | 0.165 | 25.968% | 25.977% | -0.009 |
| post-hoc GLD alone | 0.172 | 27.735% | 27.079% | +0.656 |

**Every pre-registered cell is worse than running the existing book bigger.** The paired
daily difference says the same thing more quietly - primary **+0.90 bps/day at t 0.83**, and
on the 590 risk-off sessions alone **+4.85 at t 0.73** - and the risk-on column is
**+0.15 bps at t 0.56**, which is the check that the change does only what it claims: it
touches the off-state and leaves the rest of the book alone (what is left is path
dependence, since a different crisis book means different equity to size the next rotation
with).

`evaluate.py`, run on all four full-period candidates: the primary is **refused at 0 bp**
(drawdown 25.400% against 23.700% plus the 1.0-point tolerance) and **"BEATS champion" at
2 bp** (24.982% against 23.068%, Sharpe 0.914 against 0.938, drawdown 25.7 against 25.0).
The pre-registered rule required both, so **the verdict is REFUSED** - and unlike S-18,
where the same split appeared and the 0 bp refusal was by 0.001 CAR points, this one is a
0.7-point drawdown miss with a Sharpe that falls. `top 2 of 3` and `GLD alone` are refused
on the same drawdown line.

**The post-hoc cell is the one to be most careful about.** GLD alone earns 27.735% at Sharpe
**1.040**, PSR 38.5% against the champion's 33.2%, and is the only cell with a positive
vol-matched excess. It is also the cell chosen *after* reading the probe table, its own
conditionality statistic is t = 1.66, its paired difference is t = 1.28, and the a-priori
version of the same idea (TLT) is worth -2.10 vol-matched. One asset picked out of six on a
590-session sample is exactly the shape of result this loop has refused eleven times.

### 4. One instrument fact that fell out, worth more than the cell that produced it

`risk_off_exposure` is **inert over [0.5, 1.0]**, and LEAN proved it by reproducing the 1.0
cell to every digit at 0.5 (5,304 orders, 26.550%, $33,990.30). The vol target scales the
book by `target_vol / sigma` and `sigma` is proportional to the exposure request, so halving
`target_exposure` exactly doubles `vol_scale`: on 2020-03-20 the TLT book is gross 1.1183 at
both settings (vol_scale 0.639 / 1.278) and only falls to 0.875 at 0.25, where `scale_cap`
stops the compensation. This is S-8's finding about the vol target restated for the
off-state - **under a flat margin budget an exposure *request* is not a size dial** - and it
is now written into the `Params` docstring so no future iteration spends a cell rediscovering it.

### 5. No-ops and standing jobs

- Shipped defaults reproduce **5,128 orders / 24.403% / 0.994 / 23.700% / $27,199.76 /
  `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`**.
- **I-1 deploy gate re-run** because `signals.py` is a file the paper runner loads:
  `compare_orders.py` passes **3,689/3,689 dates, 5,021 orders on both sides**, unchanged
  from the S-18 baseline.
- `live/APPROVED_PAPER.md`, `live/HALT*`, `live/intraday_config.json` and the three
  scheduled tasks were not touched. Champion unchanged at S-18.
- **A-5 part 2: no new input.** Ran at 14:5x ET, and `slippage_report.py --refresh` refuses
  to pull a session that has not closed, so the pooled figure is S-19's - **66 fills over 2
  sessions, +2.22 bps notional-weighted (se 0.80) against the shipped 1.50, |diff|/se 0.90**,
  ~4.4 sessions to settle against the 2.52 bps breakeven. `SLIPPAGE_BPS` untouched.
- **`daily_fills.py`: no new input**, 6 fills / **+2.9 bps (sd 16.7, se 6.8)** - this ran
  before the 15:45 ET rebalance.

### 6. Decision and next step

**Refused and closed.** The off-state is not where this book's missing return is: putting
capital back to work during the 16% of sessions the gate is pulled adds 2.15 CAR points and
2.2 points of realized vol, and the same risk spent through the machinery that already
exists would have paid more. That is the third form of the same finding - S-15 (the ranker),
S-16 (the proxies and the breaker), S-20 (the off-state): **on this sleeve, anything that
looks like new return is a size decision until it beats the vol-matched control.** The
durable pieces are the refusal itself, the `risk_off_exposure` inertness, and
`sweep_s20.py`'s vol-matched column, which every future daily-sleeve cell should be read
through. Priority is unchanged: the two standing per-session measurements, per-session ops,
then the owner decisions in `BLOCKERS.md`.

Newest entry first. Each entry: what was tried, why, the result, the decision, the next step.

## 2026-09-11 - Ops: the S-18 rotation left 3,227 TQQQ in the account; fixed and sold before the close

- **What happened.** S-18 retired the 3x proxies, so TQQQ dropped out of the champion's signal
  universe. At 15:45 the daily runner bought IWM and trimmed XLE/XLK to the new targets but did
  not sell TQQQ: its sleeve-isolation rule treated any position outside the signal universe as
  another sleeve's and left it alone. The account carried the intended 1.5x book plus a stale
  $230k TQQQ position for seven minutes.
- **Fix (scripts/paper_trade.py).** Only positions in the intraday sleeve's universe
  (`intraday_common.UNIVERSE`) are foreign now; every other held name is this runner's and gets a
  zero target when the champion stops naming it. History is fetched for held names outside the
  universe so they have a price. Re-run at 15:51: SELL 3,227 TQQQ filled at 71.06. Deploy gate
  (`compare_orders.py`) re-run afterwards: PASS.
- **Lesson.** A champion that changes its universe changes what "foreign" means. Any future
  universe change must be followed by a `--dry-run` that shows the retired names with a zero
  target before the 15:45 session.

## 2026-09-11 - S-19: the deployed runner's clock costs 1.9 CAR points, not 4.75, and two thirds of the correction is the promotion that already happened

- **What.** The largest unblocked number on the daily sleeve is the one in `BLOCKERS.md` asking the
  owner to move a scheduled task, and it was measured on a strategy that no longer exists. S-17
  priced the runner's staleness at **-4.75 CAR** with `S1_SIGNAL_LAG=1` on the S-12 champion - 3x
  proxies, drawdown breaker, 2.25x economic exposure - and S-18 retired both of those mechanisms
  the same day. S-19 re-prices it on the book that is actually deployed and, separately, replaces
  the *bound* with the *number*. New `scripts/_s19_runs.sh` (six LEAN cells) and
  `scripts/sweep_s19.py` (a share-level book that runs the shared `signals.py` and fills wherever it
  is told, plus a `--validate` mode that scores itself against LEAN's own equity curve).
  **10 ledger rows**: 6 LEAN runs tagged `S-19` and 4 under `daily/s19_clock`. Nothing shipped.
- **Why `S1_SIGNAL_LAG=1` was never the answer.** Written with `i` as the session the orders fill
  in, the three conventions are:

  | convention | last close the signal reads | fills at | elapsed signal -> fill |
  | --- | --- | --- | --- |
  | LEAN backtest, and the pre-open fix | `close[i-1]` | `open[i]` | one overnight gap |
  | `paper_trade.py` as scheduled at 15:45 ET | `close[i-1]` | `close[i]` | one overnight gap **+ a session** |
  | `S1_SIGNAL_LAG=1` | `close[i-2]` | `open[i]` | two overnight gaps **+ a session** |

  Rows one and two **decide identically** - same bars, same targets, same order list from the same
  state - and differ in one thing, where the order fills. Row three is a whole overnight gap staler
  than the deployed path, which is why S-17 called it an upper bound. LEAN cannot express row two on
  daily bars: a bar for D arrives stamped `D 16:00`, so nothing submitted then can fill at D's close.

### 1. The bound, re-run on the promoted champion

All six cells are `S1_*` overrides on the shipped algorithm; the control reproduces **`OrderListHash
a6d6224ce9c70091e5bfa8e96f046bf3`** (5,128 orders, 24.403%, 0.994, 23.700%, $27,199.76).

| cell | orders | CAR | Sharpe | MaxDD | fees |
| --- | --- | --- | --- | --- | --- |
| control (the promoted champion) | 5,128 | **24.403%** | 0.994 | 23.700% | $27,200 |
| `S1_SIGNAL_LAG=1` | 5,170 | **21.384%** | 0.860 | 22.700% | $23,808 |
| `S1_SIGNAL_LAG=2` | 5,184 | 20.417% | 0.816 | 21.800% | $23,477 |
| `S1_SIGNAL_LAG=1` at 2 bp | 5,170 | 20.074% | 0.805 | 22.900% | $21,929 |

So the bound is **-3.02 CAR at 0 bp** and **-2.99 at 2 bp** (the champion's own 2 bp column is
23.068%), against S-17's **-4.75** on the retired book: **the promotion to the unlevered sleeve cut
the cost of the runner's clock by 36%**, which is what a return cost does when economic exposure
falls from 2.25x to 1.50x. It is still a return cost and not a risk one - drawdown *improves* again,
22.7% against 23.7%. The ladder is strongly concave: the first session of staleness costs 3.02
points and the second 0.97, so this is not a linear decay to be extrapolated.

Halves, against S-18's champion rows (IS 17.698 / 0.911 / 23.7, OOS 32.801 / 1.108 / 23.3):
**IS 2012-2019 16.443% / 0.831 / 17.7** (-1.26 CAR) and **OOS 2020-2026 27.431% / 0.916 / 22.7**
(-5.37 CAR). Both halves lose, and the cost is out-of-sample weighted - the same shape S-18 found
for the promotion itself, and for the same reason: a bigger cost in a faster regime.

### 2. The exact convention, in a book that was checked against LEAN first

`sweep_s19.py` steps the shipped signal day by day, sizes with `main.py:submit_targets`' own rule
against `close[i-1]` (the price *both* implementations hold when they decide - LEAN's
`securities[symbol].price` at the rebalance bar, and the runner's `prices` dict built from the last
complete yfinance close), and then fills at whichever price the convention names. Holding the
sizing reference fixed is what makes the comparison paired: the two books cannot differ in what they
decide, only in what they pay.

**The validation, which comes first because nothing below it is readable otherwise.** Against the
control run's own equity curve, over the same 3,688 sessions: **corr(daily returns) 0.99650**,
annualized std **0.1863 LEAN / 0.1872 book**, mean annual return **0.2365 / 0.2335**, end equity
**$2,463,129 / $2,348,450**, tracking sd of the daily difference **9.86 bps**. The book is the
champion.

| convention | CAR | Sharpe | MaxDD | orders | fees |
| --- | --- | --- | --- | --- | --- |
| backtest / the pre-open fix | **24.077%** | 1.247 | 23.258% | 5,039 | $24,292 |
| **the deployed 15:45 runner** | **22.192%** | 1.159 | 23.860% | 5,052 | $22,045 |
| `lag1`, the LEAN bound | 20.965% | 1.102 | 22.697% | 5,090 | $21,214 |
| `lag1` + a 15:45 fill | 19.793% | 1.052 | 22.958% | 5,108 | $19,947 |

Paired daily return differences against the backtest convention: **deployed -0.599 bps/day
(t -1.41)**, lag1 -0.994 (t -1.86), lag1+close -1.383 (t -2.42). Halves of the deployed gap:
**IS -0.317 bps/day (t -0.58), OOS -0.995 (t -1.49)**.

**The conversion, which is the deliverable.** In this harness the deployed clock costs **1.885 CAR
points against the bound's 3.111 - 61% of it** - and the harness agrees with LEAN to **0.09 CAR
points** on the one cell both can run (3.111 against 3.02). So the number that belongs in
`BLOCKERS.md` is **about -1.9 CAR points**, not -4.75: 0.61 x 3.02.

**And the honest qualifier, stated as loudly as the number.** Nothing here reaches `|t| = 2`. The
direction is unanimous - every cell, both halves, both harnesses, both spreads, and the ladder is
monotone in staleness - but on 3,689 sessions a 0.6 bps/day difference is not distinguishable from
zero. This is evidence about a defect that is *known by construction* (the runner's own log has
recorded `as_of = D-1` on every session and `ref_price` matched the previous close in 6 of 6 fills),
so the case for fixing it does not rest on the t-statistic; what the t-statistic says is that the
fix should not be *sold* as +1.9 points of return.

### 3. One instrument finding, in S-17's line of work

LEAN reports **Annual Standard Deviation 0.155** and **Sharpe 0.994** for the control, while the
control's own equity curve carries **0.186** of annualized volatility on trading days. The gap is a
reporting convention: resampling that curve onto *calendar* days - weekends and holidays entering as
zero-return sessions, then annualizing by 252 - reproduces **0.157**. So every Sharpe and every
standard deviation in `research/experiments.jsonl` is on a calendar-day basis and is biased *down*
by about 17%. Cross-cell comparisons inside the ledger are unaffected, because every row shares the
convention; what is not safe is comparing a LEAN Sharpe against one computed anywhere else, which is
exactly what a script like this one would otherwise invite. `sweep_s19.py --validate` prints both
tables with that warning attached, and it also carries the two traps found getting there: LEAN's
`Strategy Equity` series has several samples per session, and taking the last of each date mixes a
close with a mid-session mark (correlation falls 0.997 -> 0.804 for no reason); and a midnight point
stamped D is the value *after* the close of D-1.

### 4. Decision

**Nothing shipped, nothing promoted, no default changed.** The champion is unchanged at S-18, the
control reproduces its `OrderListHash` bit-for-bit, `live/APPROVED_PAPER.md`, `live/HALT*`,
`live/intraday_config.json` and the three scheduled tasks were not touched, and the only files added
are two new scripts that neither runner loads - so AGENTS.md rule (a) owes no replay and the I-1
order-list gate is untouched. `BLOCKERS.md` is corrected in place: the ops item now reads -1.9 CAR
with the -4.75 kept as the superseded figure and the reason it moved.

**Standing jobs, both run.** `slippage_report.py` had new input: today's session adds **34 fills at
+0.94 bps**, so the pooled figure over 2 sessions is **66 fills / $2.88M / +2.22 bps (se 0.80)**
against the shipped 1.50 - `|diff|/se = 0.90`, inside 2 se, so `intraday_common.SLIPPAGE_BPS` was
**not** touched; ~4.4 more sessions settle it against A-5 part 1's 2.52 bps breakeven.
`daily_fills.py` is unchanged at **6 fills / $1.42M / +2.9 bps (se 6.8)** because this ran at 13:3x
ET, before the 15:45 rebalance.

**Next.** The backlog's own reading still holds - there is no open research item with a mechanism
that is not blocked on the owner or on data the human must buy - and S-19 narrows rather than opens.
What it changes is the price tag on the one ops decision the owner has been handed: moving "Quant
Paper Rebalance" before the open is worth about 1.9 CAR points at t -1.41, on a defect that is
certain even though its value is not.

## 2026-09-11 - F-3: the same machine at a daily horizon, and this time the hand-built signal wins

- **What.** The top backlog item, opened by F-1's refusal. F-1's arithmetic was that a forecast
  worth 0.797 gross bps per dollar traded cannot survive a 0.892 bps commission floor when the book
  turns 13.8x its equity a day; F-3 runs the identical method where the turnover is a hundredth.
  New `scripts/sweep_f3.py` (panel builder, walk-forward GBDT, book simulation, falsification
  control, ridge baseline, and a `--diagnose` mode), a 128,882-row daily panel
  (`data/f3/panel.parquet`), an exported forecast file (`data/f3/ml_scores.csv`, 3,692 dates x 22
  names), two new environment knobs on the shipped algorithm and one hardening of `evaluate.py`.
  **12 ledger rows**: 7 under `daily/f3_gbdt` and 5 LEAN runs (one control, three candidates and
  the short convention check).
- **The setup, fixed before a fit was read.** LEAN's own daily store through
  `lean_prices.load_ohlcv` (new: the loader now returns open/high/low as well as close and volume,
  which is what an ATR and an open-to-open label need). **Universe: the 22-name ETF sleeve only** -
  `RANK_UNIVERSE` + S-14's sector and macro rings. The 50 megacaps on disk are excluded *entirely,
  features included*: that list is the 2026 survivor set (S-7), so a breadth feature built from it
  leaks exactly what the tradable universe was forbidden. **Decide on the close of D, fill at the
  open of D+1**, the shipped algorithm's own convention. **Target** `log(open[D+1+h]/open[D+1])`
  demeaned across the date, in basis points, `h` in {5, 21} chosen like any hyperparameter.
  **41 causal features** (multi-horizon momentum with the champion's skip-5, distance from the
  20/50/200-day averages in ATR units, realized-vol levels and ratios, volume against its own
  trailing median, position in the 252-day range, beta/correlation/residual against SPY, seven SPY
  features, ten cross-sectional ranks, month and day-of-week). **Split**: hyperparameters chosen on
  train <= 2007 -> validate 2008-2011, then walk-forward over **2012-2026, the champion's own
  window**, retrained each year on <= Y-2 and early-stopped on Y-1 - so nothing in the comparison
  window was seen by selection or by fitting and the full-period LEAN run is directly comparable to
  `champion.json`.
- **Pre-registered rule**: the LEAN book returns "BEATS champion" from `evaluate.py` at the 2 bp
  column *and* beats the champion's CAR in the 2020-2026 half, or it is refused.

### 1. The date convention was proved before anything was joined to it

A forecast file joined onto LEAN's history index is a look-ahead bug if the index is stamped with
the bar's *next* midnight, which LEAN can do. Rather than assume, `main.py` now logs the frame's
last bar and its SPY close for the first three rebalances (log-only). A two-month run answers it:
`FRAME 2012-01-03 16:00:00 last_bar=2012-01-03 16:00:00 spy_close=99.0570`, against the store's own
99.057032 for 2012-01-03. The last bar in the frame **is** day D's, the algorithm decides at D's
close and fills at D+1's open, and an exact-date join of a score computed from bars <= D is causal.
The lookup in `signals.ml_scores` is therefore an exact match that **raises** on a miss inside the
file's range - a calendar disagreement must fail loudly, never silently rank on a neighbour's row.

### 2. Selection, and a horizon that is not close

| horizon | cell | validation IC | IC t | gross bps / $ turned | cost bps |
| --- | --- | --- | --- | --- | --- |
| **5 sessions** | `slow` | **+0.04762** | **+4.27** | +6.53 | 4.67 |
| 5 sessions | `deep` | +0.04688 | +4.28 | +7.75 | 4.71 |
| 5 sessions | `mid` | +0.02972 | +2.58 | +11.39 | 4.66 |
| 21 sessions | `slow` | +0.00979 | +1.03 | +3.34 | 4.63 |
| 21 sessions | `ridge` | -0.03425 | -2.76 | +11.38 | 4.75 |

The 5-day horizon wins on IC in every cell of the grid; `slow` wins within it and is what stage 2
used. Note already that the cost floor is **~1.3 bps of commission** on these ETFs (low share
prices, per-share fees) plus whatever spread is charged - not the 0.89 bps F-1 faced, because the
sleeve is cheaper per dollar of turnover but its members are cheaper per share.

### 3. The walk-forward, 2012-2026: a small IC that never becomes money

| book (long-short deciles, daily) | days | $/day | t | gross bps / $ turned | cost bps | turn/day | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| no costs at all | 3,691 | -59 | -0.61 | **+0.304** | 0.000 | 587k | -0.16 |
| commission only | 3,691 | -59 | -0.61 | +0.304 | 1.312 | 587k | -0.16 |
| **commission + 2 bp** | 3,691 | **-176** | **-1.83** | +0.304 | 3.311 | 587k | -0.48 |
| IS 2012-2019 | 2,012 | -309 | -2.91 | -1.898 | 3.617 | 559k | -1.03 |
| OOS 2020-2026 | 1,679 | -18 | -0.11 | +2.686 | 2.981 | 620k | -0.04 |
| falsification (shuffled labels) | 3,691 | -335 | -4.18 | -0.142 | 3.300 | 973k | -1.09 |
| ridge baseline | 3,691 | -109 | -1.08 | +1.728 | 3.304 | 690k | -0.28 |

Pooled out-of-sample **IC +0.01133 at t = +2.17** - nominally significant, and the same magnitude
F-1 found. Three things say it is worth nothing here. **(a)** The gross P&L t-statistic is
**+0.18**: the IC does not survive translation into a book, which is what happens when the
correlation lives in names and days that move little. **(b)** The **ridge baseline scores a
*higher* IC than the tree (+0.01223 vs +0.01133)** - the exact opposite of F-1, where the tree beat
ridge four to one. There are no interactions to find here, so the model's complexity earns nothing.
**(c)** Yearly IC is a coin flip: +0.026, **-0.053**, +0.044, +0.049, **-0.091**, +0.020, +0.027,
+0.053, -0.024, **+0.067**, -0.009, +0.009, +0.023, +0.030, -0.008 - six of fifteen years negative,
and the two largest magnitudes point in opposite directions. The falsification control behaved
(IC -0.0087), though on a 22-name cross-section its per-date IC is noisy enough to reach t -1.88,
which is worth remembering: **with twenty names a per-date rank correlation is a weak instrument.**

- **What F-3's thesis got right**: the turnover really does collapse. 0.59x of equity per day here
  against F-1's 13.8x, a factor of 23, and $194/day of cost against $3,308/day.
- **What it got wrong**: the edge per dollar traded collapsed further. **0.304 bps against F-1's
  0.797.** The daily horizon does not spread the same edge over less turnover - it finds less edge.

### 4. LEAN, the decisive test: three cells, all refused on every criterion

The forecast was wired into the shipped algorithm as a *ranking* input (`S1_ML_SCORES` names the
file, `S1_ML_MODE` chooses whether it also owns the entry gate), with every other mechanism -
regime filter, vol target, margin budget, inverse-vol allocation, no-trade band - left as shipped.

| cell | orders | CAR | Sharpe | DD | fees | `evaluate.py` |
| --- | --- | --- | --- | --- | --- | --- |
| **control, no environment** | 5,128 | **24.403%** | 0.994 | 23.7% | $27,200 | `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3` |
| ML ranking, champion entry gate | 7,109 | **10.322%** | 0.408 | **36.6%** | $40,193 | does NOT beat champion |
| ML ranking and ML entry gate | 8,567 | 9.908% | 0.385 | 35.6% | $33,776 | does NOT beat champion |
| ML ranking, no floor on the ML score | 7,456 | 11.400% | 0.461 | 36.0% | $41,910 | does NOT beat champion |

Every candidate fails **all four** criteria: over the 35% absolute drawdown limit, below the
champion on CAR by 13-14 points, below it on Sharpe by far more than the tolerance, and worse on
drawdown by more than a point. The third cell exists to answer the obvious objection - that the
entry floor, not the ranking, broke it - and it does not: freeing the gate moves 10.32% to 11.40%
and leaves the drawdown at 36%. **The ranking is what lost.** For context from S-15's attribution,
this same book with *no ranking at all* earned 17.7%: the forecast is worse than not choosing.

### 5. Why - the measurement that makes the refusal a finding

The panel is 22 names wide but the shipped sleeve ranks nine. `sweep_f3.py --diagnose` scores both
candidates on exactly that cross-section over 2012-2026 (3,684 sessions):

| score, on the nine names the champion ranks | IC | t |
| --- | --- | --- |
| F-3 GBDT forecast, pooled | +0.00691 | +0.97 |
| **champion momentum blend, pooled** | **+0.04268** | **+5.43** |
| F-3 GBDT, IS 2012-2019 / OOS 2020-2026 | +0.00848 / +0.00502 | +0.89 / +0.47 |
| **champion momentum blend, IS / OOS** | **+0.03265 / +0.05475** | **+3.03 / +4.77** |

Mean per-date rank correlation between the two scores: **+0.091**. They are nearly unrelated, and
the hand-built one is six times better - in both halves. As unlevered top-3-of-9 books with no
other machinery at all (no regime filter, no vol target, no margin budget):

| book | $/day | t | gross bps / $ turned | turn/day | Sharpe |
| --- | --- | --- | --- | --- | --- |
| GBDT top-3 of 9 | 305 | +1.77 | 9.29 | 486k | 0.46 |
| **momentum top-3 of 9** | **617** | **+3.94** | **61.51** | **105k** | **1.03** |

**The champion's momentum blend earns 61.5 bps per dollar it turns over, on a fifth of the
turnover.** That is 6.6x the forecast's edge per dollar traded and 77x F-1's 0.797 bps. Read across
the three iterations, the ratio of edge to cost is the whole story of the last day's work: F-1
0.797 bps of edge against 0.892 of cost (refused), F-3's forecast 9.29 against 3.01 (refused
anyway, because momentum does better on the same names), and the shipped champion **61.5 against
2.93**. The daily sleeve was never short of turnover budget; it is already spending it well.

### 6. Decision, and what did not move

- **REFUSED and closed.** Nothing shipped. `live/intraday_config.json`, `live/APPROVED_PAPER.md`,
  `live/HALT*` and the scheduled tasks were not touched; the champion is unchanged at S-18's
  unlevered book.
- **The two no-ops are proved, not asserted.** The control run with no environment reproduces
  **`OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`** with 5,128 orders / 24.403% / 0.994 / 23.7%
  / $27,199.76 - identical to `champion.json` - so the new knob, the new log line and the new
  loader are bit-for-bit inert. The **I-1 deploy gate passes 3,689/3,689 dates at 5,021 orders on
  both sides**, so the daily runner's path is unchanged.
- **One defect found in the instrument and fixed.** The two-month run used to prove the date
  convention annualizes to **47.3% CAR at a 1.2% drawdown on 71 orders**, and before this iteration
  `evaluate.py` would have called it "BEATS champion" - every criterion passes, and it is not a
  strategy. `evaluate.py` now refuses any run whose recorded environment moved `S1_START` or
  `S1_END` as "not comparable", the same principle S-18 applied to the cost model. Verified on the
  diagnostic row (refused on the window) and on the control (judged normally, and it ties rather
  than beats).
- **Standing jobs both ran, neither had new input** (this iteration ran at 12:3x ET, before the
  15:45 rebalance and before the close). `slippage_report.py`: **58 fills over 2 sessions, +2.42
  bps pooled (se 0.88) against the shipped 1.50, |diff|/se 1.04** - inside 2 se, so the constant is
  untouched; ~5.5 sessions to settle. `daily_fills.py`: unchanged at 6 fills / **+2.9 bps (se
  6.8)**.
- **Do not re-open F-3 as a feature, model, horizon or universe question.** The gap is not a
  percent: on the nine names the sleeve trades, the forecast's IC is +0.0069 at t +0.97 against
  momentum's +0.0427 at t +5.43, and the two scores are 0.09 correlated. A longer feature list does
  not close a six-fold gap in the direction the simple signal already points.

### 7. What it changes for the loop

F-1 and F-3 together close the supervised track, and they close it with a *reason* rather than a
tally. Machine learning on this data finds an IC of about +0.011 wherever it is pointed - intraday
and daily, 38 features or 41, tree or ridge. What decides whether that is worth anything is the
**edge-to-cost ratio of the mechanism it is riding**, and on both sleeves the model rides a weaker
mechanism than the one already shipped. The daily champion is not beatable by a better ranker: its
ranking is already a t = +5.4 signal worth 61 bps per dollar turned, S-14 measured that diluting it
costs money, and S-15 measured that the rest of its return is sizing machinery.

So the loop is back where the 2026-09-11 review left it, with the ML detour now priced: **the
binding constraint is the owner decisions in `BLOCKERS.md`, not a missing idea.** In order of the
number attached to them: the runner's clock (**-4.75 CAR**, needs the scheduled task moved to a
pre-open MOO convention), the Reg-T buffer (S-16: budget 0.78 / 0.80 / 0.82 earn 25.307 / 25.903 /
26.474 at *rising* Sharpe on the now-unlevered book), and `equity_frac` on an intraday sleeve that
eleven tracks have now measured negative. The next unblocked research item is **F-2**, the index
futures track, and it needs data the human must buy.

## 2026-09-11 - F-1: the machine finds a real forecast and it is worth half its own commission

- **What.** The top backlog item and the one mechanism class this loop had never tried: a
  walk-forward gradient-boosted forecaster on the ten-year Alpaca minute store, instead of another
  hand-designed rule. New `scripts/sweep_f1.py` (panel builder + model + book simulation +
  falsification control), a cached 1.59M-row modelling panel (`data/f1/panel.parquet`, gitignored),
  5 ledger rows under `intraday/f1_gbdt`. `scikit-learn` 1.9.1 installed (the backlog item allows
  pip); nothing else in the repository changed.
- **The setup, all of it fixed before a single fit was read.** 5-minute bars, regular session,
  **56 tradable names** (the whole Alpaca store minus SPY/QQQ/IWM/TQQQ/UPRO/SQQQ/SPXU, which stay
  as market features so AGENTS.md's disjointness rule holds). A decision on the close of the bar
  starting 09:55, 10:25 ... 14:55 - **11 per session, 2,682 sessions** - filled at the next bar's
  open and unwound 30 minutes later, so the book is flat long before the 15:38 flatten.
  **38 features**, every one causal: returns at 5/15/30/60 min, session return, overnight gap,
  VWAP deviation in ATR units and bps, range/ATR, realized-vol ratio, volume against the trailing
  20-session median of the *same* time-of-day slot, position in the session range, time-of-day,
  day-of-week, prior day's return, the SPY copies, the residual against SPY, and the
  cross-sectional percentile rank of nine of them. **Target**: `log(open[t+7]/open[t+1])` demeaned
  across the cross-section - what a dollar-neutral book can actually capture. **Split**: train
  2016-2021, validate 2022-2023 (hyperparameters only), test 2024-2026 with a yearly expanding
  retrain (year Y trained on 2016..Y-2, early-stopped on Y-1). **Book**: long the top decile,
  short the bottom decile, gross 1.0x, rebalanced every 30 minutes, costs from
  `intraday_common` (1.5 bps slippage + IBKR commission + the A-5 part 2 regulatory fees).
- **Pre-registered rule**: net P&L/day positive at t > 2 pooled over 2024-2026 **and** positive in
  at least two of the three test years.

### 1. There is a signal, and it is out of sample

| year | trained on | IC | IC t | gross $/day | gross t | gross bps per $ turned | net $/day | net t |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024 | <=2022, valid 2023 | **+0.01917** | **+5.08** | +1,781 | +3.19 | **1.293** | -1,434 | -2.54 |
| 2025 | <=2023, valid 2024 | **+0.01133** | **+2.85** | +913 | +1.69 | 0.638 | -2,582 | -4.72 |
| 2026 | <=2024, valid 2025 | -0.00012 | -0.03 | +387 | +0.45 | 0.293 | -2,787 | -3.23 |
| **pooled 2024-2026** | | **+0.01133** | **+4.74** | **+1,102** | **+3.04** | **0.797** | **-2,206** | **-6.02** |

- The pooled out-of-sample information coefficient is **+0.0113 at t = +4.74** and the gross P&L of
  the book it implies is **+$1,102/day at t = +3.04**. This is the **first candidate on the
  intraday side of this repository with a positive, significant gross edge measured out of
  sample** - O-1, L-1, X-1, A-10 and S-2 all had gross at or below zero before a cent of cost.
- **The falsification control says the pipeline is not the source.** The identical code trained on
  labels shuffled *within each timestamp* scores IC **+0.0031 (t +1.59)** and gross **0.071 bps**
  per dollar turned, against the real model's 0.797 - a ninth of it, and its book loses more
  ($-3,817/day) purely because noise turns the book over harder.
- **A linear baseline does not find it**: ridge on the same 38 features scores validation IC
  +0.0027 (t +0.74) against the tree's +0.0105 (t +3.34), so the edge is in the interactions.

### 2. And it is worth about half of its own commission

The book turns over **$13.8M/day on a $1M account** - 13.8x equity a day, 11 rebalances of a
decile book. At that turnover the only statistic that matters is what a dollar traded earns
against what a dollar traded costs:

| cell | gross bps per $ turned | commission+fees bps | **breakeven slippage** | net $/day | net t |
| --- | --- | --- | --- | --- | --- |
| decile 0.04 (2 names a side) | 1.551 | 1.422 | **+0.129 bps** | -1,943 | -2.58 |
| decile 0.10 (the pre-registered book) | 0.797 | 0.892 | **-0.095 bps** | -2,206 | -6.02 |
| decile 0.20 | 0.513 | 0.743 | -0.229 bps | -2,361 | -9.79 |
| decile 0.34 | 0.353 | 0.713 | -0.360 bps | -2,355 | -14.86 |

- **At the pre-registered book the breakeven slippage is negative.** The signal does not cover the
  commission and the regulatory fees *at zero spread* - this is not a question about the 1.5 bps
  constant A-5 has been measuring, and no execution improvement can reach it.
- The narrowest slice is the only one where gross clears commission, and it clears it by
  **0.129 bps**. Half a cent on these names is **0.3-1.0 bps** of half-spread (S-18's tick
  arithmetic), so the hard floor of a real fill is several times the whole surplus. Concentrating
  further is not available either: at 2 names a side the worst day is already **-$81,038** on a
  $1M book, past the sleeve's own 2.5% daily loss limit.
- The ranking across deciles is the honest shape of a real but thin signal: gross bps rises
  monotonically as the book concentrates (0.353 -> 0.513 -> 0.797 -> 1.551) while its t-statistic
  stays flat at ~2.9-3.0. There is edge; there is not enough of it per dollar.

### 3. The edge decays, which is the part that matters for a next step

IC by test year runs **+0.0192 -> +0.0113 -> -0.0001** and gross bps **1.293 -> 0.638 -> 0.293**.
The 2026 model, trained through 2024 and early-stopped on 2025, forecasts nothing. Two readings
are available and this iteration cannot separate them: the features are being arbitraged away, or
an expanding window trained mostly on 2016-2021 is increasingly mismatched to the current market.
**Feature importance is stable while the edge is not** - permutation importance ranks correlate
**0.66-0.77** across the three retrains and the top of the list is the same every year
(`vwap_atr`, its cross-sectional rank, `vol_rel`, `rng_atr`, `cs_rvol_ratio`) - i.e. the model
keeps reading intraday mean reversion against VWAP conditioned on relative volume, the same
mechanism L-1 refused on leveraged ETFs, and that mechanism's *payoff* is shrinking, not the
model's grip on it.

### 4. Decision

**Refused and closed. Nothing shipped.** `live/intraday_config.json`, `live/APPROVED_PAPER.md`,
`live/HALT*` and the scheduled tasks were not touched; no file the live trader or the daily runner
loads was modified, so AGENTS.md rule (a) owes no replay. The champion is unchanged at S-18's
unlevered book.

**Do not re-open as a feature, model or horizon question.** The refusal is not "the model is not
good enough" - it is that a 30-minute cross-sectional forecast of this quality is worth **0.8-1.6
bps per dollar traded** against a commission floor of **0.7-1.4 bps** before any spread at all.
Making the model better has to move gross by a factor, not a percent. What *would* change the
arithmetic is a lower-turnover expression of the same forecast (a horizon measured in days rather
than 30 minutes, where the same bps of edge is spread over a hundredth of the turnover) - and that
is the daily sleeve, where the champion already lives and where S-14 measured its cross-sectional
edge at +2.02 bps/day. That is a genuinely new item, not a re-run of this one.

### 5. Standing jobs, both with new input

- **A-5 part 2** (`slippage_report.py`): **58 fills over 2 sessions, $2.64M traded**, realized
  slippage **+2.42 bps notional-weighted (se 0.89)** against the shipped 1.50 - **|diff|/se = 1.03**,
  still inside 2 se, so `SLIPPAGE_BPS` is untouched. Per session: 2026-09-10 32 fills +2.89 (se 1.33),
  2026-09-11 26 fills **+1.26 (se 0.95)** - today's session pulled the pooled estimate *down* from
  S-18's +2.42 reading on 23 fills while halving its standard error. ~5.5 sessions to settle against
  the 2.52 bps breakeven.
- **`daily_fills.py`**: unchanged at 6 fills / +2.9 bps (se 6.8) - the daily sleeve's 15:45 ET
  rebalance had not run when this iteration finished.

## 2026-09-11 - S-18: the champion is now the unlevered book - same return, less risk, less leverage, 40% less commission

- **What.** The top backlog item, and the first promotion since S-12. The candidate is S-16's
  (e+g) cell at the **unchanged** 0.75 margin budget: the shipped signal held in unlevered parent
  ETFs (`LEVERED_PROXY = {}`) with the step drawdown breaker off (`dd_halve = dd_flat = 9.0`). S-16
  refused it by **0.001 CAR points** and S-17 showed that margin exists only at exactly zero
  spread, which is LEAN's default rather than anyone's choice. S-17 named three missing pieces and
  each was a run, not a judgement: the two sub-periods at both cost models, a decision about what
  `evaluate.py` compares against, and a re-baselined `OrderListHash`. All three are supplied here.
  Eight new LEAN cells (`scripts/_s18_runs.sh`, read by `scripts/sweep_s18.py`) plus three
  verification runs; 11 ledger rows.
- **Why now and not in S-16.** The refusal was an artifact of a cost model, and the cost model is
  not a matter of opinion: `DefaultBrokerageModel.GetSlippageModel` returns
  `NullSlippageModel.Instance`, so the two books were compared with the more turnover-hungry one
  paying nothing for its extra orders. The crossover between them is at **~0.03 bp**. A half-cent
  tick is **0.27 bp on XLK, 0.71 on TQQQ and 0.77 on XLE**, so the *hard floor* of what any real
  fill can cost is an order of magnitude past the point where the ranking flips. That is a
  structural argument about tick size, not a fitted constant, and it is what carries this
  promotion - not the six paper fills (see the standing job below).

### 1. The halves, which is what S-16 never ran

Candidate minus champion, on the two windows S-12 itself was promoted on:

| window | spread | candidate | champion | dCAR | Sharpe | MaxDD | paired bps/day (t) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| full 2012-2026 | 0 bp | 24.403 | 24.404 | **-0.001** | 0.994 vs 0.921 | 23.7 vs 25.1 | -0.00 (**-0.00**) |
| full 2012-2026 | 2 bp | 23.068 | 22.926 | **+0.142** | 0.938 vs 0.865 | 25.0 vs 29.2 | +0.05 (+0.12) |
| IS 2012-2019 | 0 bp | 17.698 | 19.180 | **-1.482** | 0.911 vs 0.884 | 23.7 vs 25.1 | -0.50 (-1.25) |
| IS 2012-2019 | 2 bp | 16.349 | 17.509 | -1.160 | 0.840 vs 0.808 | **25.0 vs 29.2** | -0.39 (-0.99) |
| OOS 2020-2026 | 0 bp | 32.801 | 30.863 | **+1.938** | 1.108 vs 0.985 | 23.3 vs 22.6 | +0.58 (+0.87) |
| OOS 2020-2026 | 2 bp | 31.477 | 29.621 | +1.856 | 1.062 vs 0.943 | 23.4 vs 22.8 | +0.57 (+0.84) |

- **The return difference is out-of-sample weighted and the risk difference is in both halves.**
  The unlevered book gives up ~1.5 CAR in 2012-2019 and takes back ~1.9 in 2020-2026, which is why
  fourteen years look like a dead heat; Sharpe is better in **both** windows and at both spreads,
  realized vol is 0.155 against 0.170 throughout, and the drawdown gap at 2 bp is 4.2 points in
  sample. This is the mirror image of S-15's finding about S-12's allocation tilt (in-sample only),
  and it is the direction one would rather have - but it is stated, not sold: **nothing in this
  comparison reaches |t| = 2**, and on return alone the full-period paired statistic is t = +0.12.
- **Fees**: $27.2k against $45.7k at 0 bp, $24.9k against $41.9k at 2 bp, on *more* orders (5,128
  vs 4,735). The champion's commission was concentrated in the 3x sleeve's re-weighting.
- **Economic exposure falls from 2.25x to 1.50x** at the same 0.75 margin budget. IBKR charges
  0.333 of margin per unit of exposure on a 3x ETF against 0.5 on an ordinary one, which is the
  whole reason the proxies were ever there: room, not edge.

### 2. What `evaluate.py` compares against, which was the real open question

A candidate charged 2 bp cannot be judged against a champion row that paid nothing - the bias runs
toward whichever book trades most, and between these two that is 400 orders. Three small changes
make the comparison explicit instead of implicit:

- `scripts/backtest.py` now records the `S1_*` environment with every run. Until now the only
  description of a cell was its free-text tag, which no script can read.
- `research/champion.json` carries `stats_by_spread`, one column per cost model, each with its own
  `run_dir`. The headline `stats` stay the 0 bp column so the whole ledger remains one scale.
- `scripts/evaluate.py` picks the column matching the candidate's own `S1_SLIPPAGE_BPS`, and
  **refuses a run at a spread it has no column for** rather than judging it against the wrong one.

Both verdicts were then produced by the gate rather than by hand: at 2 bp **BEATS champion** (CAR
23.068 vs 22.926, Sharpe 0.938 vs 0.865, DD 25.0 vs 29.2), at 0 bp **refused by 0.001 CAR points**,
exactly as S-16 recorded. The promotion was made on the 2 bp row through
`scripts/evaluate.py --promote`, and `champion.json` records both columns and says which one
decided it.

### 3. The two no-ops that had to hold before anything shipped

- **The promoted defaults reproduce the tested cell exactly.** With no environment at all:
  **5,128 orders, 24.403%, 0.994, 23.700%, $27,199.76, `OrderListHash
  a6d6224ce9c70091e5bfa8e96f046bf3`** - identical to S-16's env-override run, so the shipped code
  is the cell that was measured and not a near relative of it.
- **The retired champion is one environment away and bit-identical.** `S1_PROXY=on
  S1_DD_HALVE=0.15 S1_DD_FLAT=0.25` gives **4,735 orders, 24.404%, 0.921, 25.100%, $45,695.46,
  `OrderListHash 5246804e17a67af90028ffceead7d3b3`**. This needed one structural fix:
  `margin_requirement` now reads `LEVERED_PROXY_3X` rather than `LEVERED_PROXY`, because what IBKR
  charges for TQQQ is a fact about TQQQ and not about whether this strategy holds it - otherwise
  the restore would have charged the 3x names Reg-T 50% and quietly failed to reproduce.
- **The I-1 deploy gate was re-run, since promotion moves the live order list**:
  `scripts/compare_orders.py` passes **3,689/3,689 dates, 5,021 orders on both sides**, and
  `paper_trade.py --mock --dry-run` plans **XLE 793 / XLK 202 / IWM 211 at 1.50x gross, margin
  0.75 of 1.00**, with no 3x name in the universe. Expect the next 15:45 ET paper session to
  rotate the book out of TQQQ into unlevered names; that is what a promotion means and it is paper.

### 4. The band was measured on the new book and deliberately not changed

S-17 found `min_order_value` 0.03 worth **+0.57 CAR (t +1.22)** on the champion once orders cost
something. On the candidate's own book it is worth **+0.064 CAR at 0 bp (t +0.58)** and **+0.103 at
2 bp (t +0.94)**, with 0.4 points *more* drawdown - about a fifth of the effect. The reason is the
same one that explains the fee difference: most of what a wider band used to save was the 3x
sleeve's vol-drift re-weighting, and that sleeve is gone. So the shipped band stays **0.01**, one
change ships rather than two, and S-13's warning that this parameter's fine structure is path luck
still stands.

### 5. Decision

**Promoted.** `research/champion.json` now records the unlevered book, and
`algorithms/s1_momo/signals.py` ships `LEVERED_PROXY = {}` with the overlay off. The case, stated
the way it should be read: **not more return - the same return, carried with 0.073 more Sharpe,
1.5 points less realized vol, 1.4 fewer points of drawdown at 0 bp and 4.2 at 2 bp, 40% less
commission and two thirds of the economic exposure.** What did not change: `margin_budget` stays
0.75, the band stays 0.01, `S1_SLIPPAGE_BPS` stays 0.0, the momentum signal and the regime filter
are untouched, and `live/APPROVED_PAPER.md`, `live/HALT*`, `live/intraday_config.json` and the
scheduled tasks were not touched. The intraday sleeve was not touched at all, so its rule (a) owes
no replay.

**Standing jobs, both run, neither moved a constant.** `daily_fills.py`: still 2 sessions / 6
fills / $1.42M, execution **+2.9 bps against the 15:45 close (sd 16.7, se 6.8)** - note that the
2 bp column this promotion was decided on sits comfortably inside that interval, but the argument
that carries it is the tick-size floor, not these six fills. `slippage_report.py` on the intraday
sleeve **had new input for the first time since A-5 part 2**: today's partial session adds 23 fills
at +1.11 bps, so pooled it is **+2.42 bps against the shipped 1.50, |diff|/se = 0.99** - still
inside 2 se, so `intraday_common.SLIPPAGE_BPS` is untouched; ~6.1 more sessions settle it.

### 6. What it changes for the loop

- **The daily sleeve's remaining levers are now all risk-posture ones.** S-15 measured that 71% of
  the return is the sizing machinery; this promotion removed the two components that were worth
  zero return between them, which leaves the vol target, the margin budget and the regime filter -
  and the first two are the owner's Reg-T buffer question in `BLOCKERS.md`. That question is now
  worth **more**: the unlevered book at budget 0.78 / 0.80 / 0.82 earns 25.307 / 25.903 / 26.474 at
  **rising** Sharpe (S-16), so the freed risk has a measured, monotone price and the owner is one
  decision away from it. This iteration deliberately did not take it.
- **On the mandate.** The promotion lowers realized vol from 0.170 to 0.155, which looks like the
  wrong direction for a book that is supposed to be aggressive. It is not: S-15 and S-16 both
  measured that the 3x instruments supplied volatility and no edge, and USER.md's directive is that
  volatility must be earned by edge rather than by sizing. The honest way to buy the vol back is
  the budget dial above, at a known price, with the owner's consent.
- **The next daily-sleeve work is the runner's clock**, not a signal: S-17 priced the deployed
  path's one-session staleness at **-4.75 CAR**, which is larger than anything the S-track has
  moved since S-9, and the fix needs a scheduled task moved (in `BLOCKERS.md`). Under "Open" the
  top item is now **F-1**, the supervised intraday forecaster.

## 2026-09-11 - S-17: the daily sleeve has been judged on a harness that charges no spread, and the deployed runner trades a signal one session stale

- **What.** The backlog held no open research item with a mechanism, so this iteration audited the
  instrument instead of the strategy: what does the champion's 24.404% assume about *execution*,
  and what does each assumption cost? Two omissions came out of reading the engine source and the
  live log rather than out of any sweep. Both are now priceable knobs on the shipped algorithm
  (`S1_SLIPPAGE_BPS`, `S1_SIGNAL_LAG`, both defaulting to the champion), twelve full-period LEAN
  cells (`scripts/_s17_runs.sh`, read by `scripts/sweep_s17.py`), a new live-fill instrument
  (`scripts/daily_fills.py`), 12 ledger rows. **The control reproduces `OrderListHash
  5246804e17a67af90028ffceead7d3b3`** (4,735 orders, 24.404%, 0.921, 25.100%, $45,695.46), so both
  knobs are inert at their defaults and the daily paper runner's path is untouched.
- **Why it was worth an iteration.** S-1 through S-16 have compared cells against each other on a
  number that charges commission and **no spread at all**, and the cells differ in order count by
  up to 2.7x (S-13: 4,735 vs 1,727). A cost that scales with turnover and is set to zero does not
  bias a comparison a little - it biases it in one direction, toward whichever cell trades most.

### 1. The harness charges zero spread, and that is LEAN's default, not a choice anyone made

`DefaultBrokerageModel.GetSlippageModel` returns `NullSlippageModel.Instance` and
`InteractiveBrokersBrokerageModel` does not override it, so every fill in this repository is booked
at the exact opening print. `EquityFillModel.MarketOnOpenFill` *does* apply a slippage model when
one is set (`+slip` on a buy, `-slip` on a sell), so the omission is priceable:

| champion + | orders | CAR% | dCAR | Sharpe | MaxDD% | PSR% | fees | paired bps/day | t |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 bp (shipped) | 4,735 | **24.404** | | 0.921 | 25.1 | 23.0 | $45,695 | | |
| 1 bp | 4,725 | 23.699 | -0.70 | 0.894 | 27.2 | 20.0 | $43,632 | -0.23 | -1.84 |
| 2 bp | 4,723 | 22.926 | -1.48 | 0.865 | 29.2 | 17.0 | $41,886 | -0.48 | -3.48 |
| 5 bp | 4,783 | 21.129 | -3.27 | 0.795 | 31.7 | 11.0 | $37,997 | -1.06 | -9.32 |
| 10 bp | 4,772 | 18.216 | -6.19 | 0.684 | 32.3 | 4.8 | $32,755 | -2.03 | -10.27 |

- **A basis point of spread costs 0.68 points of CAR** (mean slope over the ladder; -0.705 / -0.739
  / -0.655 / -0.619 per bp, so essentially linear). That slope is also a turnover meter: 0.68 CAR
  per bp implies the book pays spread on roughly **68x its equity a year of one-way notional**,
  about 27% of equity a session, which is what a daily-rebalanced vol-targeted three-name book at
  1.5-2.25x gross does.
- **Drawdown is where it hurts most**: 25.1 -> 27.2 -> 29.2 -> 31.7 -> 32.3. A cost that is charged
  every day compounds into the path, not just the level, and at 10 bp the champion is 2.7 points
  from the owner's 35% cap on a strategy that is nominally at 25.1.
- **The honest caveat on the size of the constant.** A true MarketOnOpen order is filled at the
  official opening print, which is not a spread-crossing venue, so for a book that really used MOO
  the omitted cost is impact rather than half-spread and 0 bp is less wrong than it looks. The
  deployed runner does **not** use MOO - it sends plain MKT orders at 15:45 ET, which do cross a
  spread - so the ladder above is most relevant to the path that is actually live. What was
  measured on that path is below, and it is 2.9 bps.

### 2. The live fills: +2.9 bps of execution cost, and a convention gap that is not slippage

New `scripts/daily_fills.py`, the daily counterpart of `slippage_report.py`. Six fills over the two
paper sessions (2026-09-09, 2026-09-10), $1.42M traded:

| measured against | notional-weighted | per-fill sd | se |
| --- | --- | --- | --- |
| the 15:45 close the runner aimed at (**execution cost**) | **+2.9 bps** | 16.7 | 6.8 |
| the D+1 open the backtest fills at (**convention**) | -16.9 bps | 63.2 | 25.8 |

The first number is execution cost and is the one that belongs against the ladder - it is the same
size as the intraday sleeve's measured +2.89 bps (A-5 part 2), on far more liquid instruments, which
is a coincidence worth distrusting until there are more fills. The second is a **whole session of
price movement**: its per-fill dispersion is four times the first's, so six fills say nothing about
it and it can only be priced over fourteen years. That is section 3.

### 3. The deployed runner trades a signal one session stale, and it costs 4.75 CAR points

This started as a suspicion that XLK's sizing `ref_price` was stale (byte-identical on both
sessions) and ended as something better established and less exotic. XLK really did close at 187.87
on 2026-09-08 *and* 2026-09-09, so that was a coincidence, not a bug. What is real:

- `scripts/paper_trade.py` builds its price frame from `yf.download(period="2y")` at 15:45 ET, and
  the last **complete** daily bar at that moment is the **previous** session's close. Measured, not
  inferred: `ref_price` equals the previous close in **6 of 6 fills**, and the runner's own `plan`
  event has been recording it the whole time - `as_of = 2026-09-08` on the 2026-09-09 session and
  `as_of = 2026-09-09` on the 2026-09-10 one.
- So the two paths are: **backtest** reads closes through D and fills at the open of D+1 (one
  overnight gap); **live** reads closes through D-1 and fills at the close of D (one overnight gap
  plus a full session). Both act on the same signal date and fill a session apart.

`S1_SIGNAL_LAG=1` prices that, holding the sizing price current so the effect is signal staleness
alone. It is an **upper bound**: it adds a session of staleness *and* keeps the D+1 open fill, so it
is one overnight gap more stale than the live path, never less.

| champion + | orders | CAR% | dCAR | Sharpe | MaxDD% | PSR% | paired bps/day | t |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 session of lag, 0 bp | 4,878 | **19.649** | **-4.75** | 0.736 | **23.7** | 7.2 | -1.55 | **-2.65** |
| 1 session of lag, 2 bp | 4,879 | 18.592 | -5.81 | 0.695 | 24.2 | 5.2 | -1.90 | -3.24 |

- **The deployed daily champion is not running the backtested strategy.** Its 24.404% assumes it
  acts on the close it has just seen; the runner acts on a close that is a session old, and that is
  worth up to 4.75 points of CAR at t = -2.65 on 3,689 paired sessions - **the largest single
  number this iteration produced, and larger than every lever the S-track has argued about since
  S-9.** With the measured spread on top the honest expectation for the deployed path is around
  **18.6%, not 24.4%**.
- **It costs return, not risk**: drawdown *improves* (23.7 vs 25.1) and realized vol is unchanged
  (0.171 vs 0.170). A staler momentum signal trades less of the whipsaw and less of the edge.
- **The fix is a schedule change, which the loop may not make.** The exact match for the backtest
  is a pre-open run: read the previous close (complete by then) and send MarketOnOpen/OPG orders,
  which fill at the open of D - literally "decide on the close of D-1, fill at the open of D". That
  needs the Windows task moved from 15:45 ET to before 09:28 ET and `--order-type` extended, and
  AGENTS.md forbids the loop from touching scheduled tasks. It is in `BLOCKERS.md` with the exact
  prescription. A smaller in-place alternative (append the live 15:45 price as the frame's last row
  so the signal reads through D) is written up there too, with its own risk: the paper account has
  no real-time subscription, so that price is itself delayed.

### 4. The spread re-ranks S-16's parked frontier, and frees one cell from the owner's question

S-16 measured that turning off the 3x proxies *and* the drawdown overlay at the **unchanged** 0.75
margin budget earns the champion's return to three decimal places with strictly less risk, and had
to refuse it because it missed on CAR by **0.001 points**. That margin only exists at exactly zero
spread:

| spread | (e+g) at budget 0.75 | champion | dCAR | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| 0.0 bp | 24.403% | 24.404% | **-0.001** | 0.994 vs 0.921 | 23.7 vs 25.1 |
| 1.0 bp | 23.735% | 23.699% | **+0.036** | 0.966 vs 0.894 | 24.3 vs 27.2 |
| 2.0 bp | 23.068% | 22.926% | **+0.142** | 0.938 vs 0.865 | 25.0 vs 29.2 |

- **The crossover is at about 0.03 bp.** A half-cent tick is 0.27 bp on XLK, 0.71 on TQQQ and 0.77
  on XLE, so the *hard floor* of what a real fill can cost is already an order of magnitude past
  it. At 2 bp the unlevered book wins on CAR, wins on Sharpe by 0.073, carries **4.2 fewer points
  of drawdown** and pays **$24.9k of commission against $41.9k**.
- **And it needs no change to `margin_budget`**, so unlike S-16's three passing cells it is not
  behind the open owner question. Its economic exposure is 1.50x against the champion's 2.25x.
- **What it is not.** The paired return difference at 2 bp is **+0.05 bps/day at t = +0.12** -
  indistinguishable from zero, exactly as at 0 bp. The case for this cell is not that it earns more;
  it is that it earns the same for less risk and less cost, and that the 0.001-point refusal was an
  artifact of a harness that charges nothing per order. S-16's other cell (e+g at budget 0.80) keeps
  its lead at 2 bp (24.453% vs 22.926%, +1.53 CAR, t +1.46) and stays behind the owner's question.

### 5. The owner's no-trade-band question is answered, in the direction S-13 predicted

S-13 swept `min_order_value` with zero spread, found CAR flat across a factor of eight, and sent it
to the owner precisely because "every skipped order is also a spread not crossed" and the backtest
could not see it. Charged at 2 bp:

| band | orders | CAR% @0bp | CAR% @2bp | Sharpe @2bp | MaxDD% @2bp | vs 0.01 @2bp |
| --- | --- | --- | --- | --- | --- | --- |
| 0.01 (shipped) | 4,723 | 24.40 | 22.926 | 0.865 | 29.2 | |
| **0.03** | 2,752 | 24.34 | **23.491** | 0.885 | **25.4** | **+0.57 CAR, t +1.22** |
| 0.08 | 1,720 | 24.47 | 23.015 | 0.865 | 29.7 | +0.09 CAR, t +0.19 |

A wider band is worth **+0.57 CAR and 3.8 points of drawdown** once orders cost something, and 0.08
gives almost all of it back - which is S-13's own conclusion that this parameter's fine structure is
path luck. So the *direction* is now evidence (wider is better than 0.01) and the *level* still is
not. Note what this does not settle: LEAN's MOO fill means the band is being priced against opening
prints, while live it is priced against 15:45 market orders.

### 6. Decision

**Nothing shipped, nothing promoted, and no default changed.** Specifically:

- **`S1_SLIPPAGE_BPS` stays 0.0.** Charging 2 bp by default would re-baseline every number in this
  repository against a constant measured on **six fills with a standard error of 6.8 bps**. That is
  A-5 part 2's rule applied to the daily sleeve: measure first, move the constant only when the gap
  exceeds two standard errors. What changes today is that the knob exists and every future
  judgement can be made at a non-zero spread as well as at zero.
- **The champion is unchanged at S-12** and `research/champion.json` is untouched. The (e+g) cell at
  budget 0.75 is the best candidate this iteration produced and it is **not promoted**, for reasons
  that are about evidence and not about the rule: the case rests on a cost model introduced in this
  same iteration, its return advantage is t = +0.12, and it has no in-sample/out-of-sample runs and
  no re-baselined `OrderListHash`. Promoting a deployed strategy on a same-iteration cost model
  would be exactly the mistake A-9's holdout was built to catch. It is the top backlog item (S-18)
  with its three missing pieces named.
- **`live/` and the scheduled tasks are untouched**, and no file the daily runner or the intraday
  trader loads was modified - the two new knobs are in `algorithms/s1_momo/main.py`, which LEAN
  loads and the runner does not (the runner imports `signals.py`). Rule (a) owes no replay.
- **A-5 part 2 (standing job) had no new input**: this ran at 08:4x ET, before the open, so the
  intraday ledger is still the single 2026-09-10 session - 32 fills, $1.87M, **+2.89 bps (se
  1.33)** against the shipped 1.50, |diff|/se 1.05, ~6.8 sessions to settle it. `SLIPPAGE_BPS`
  untouched. One incidental fix: `slippage_report.py` must be run on the default Python, not
  `py -3.11`, which has no pyarrow.

### 7. What it changes for the loop

The backlog's conclusion after S-15/S-16 was that nothing was left but owner decisions. That was
true about *strategies* and wrong about the *instrument*. Two of the three things this iteration
found are measurement defects rather than levers, which is why they were invisible to sixteen
iterations of sweeping: the harness's cost model and the runner's clock. Concretely:

1. **Every cross-cell comparison in the S-track is biased toward turnover** by up to 0.68 CAR per
   bp of unmodelled spread, and the cells differ by 2.7x in order count. The S-13 band result, the
   S-12 promotion (which added 2,162 orders) and the S-16 frontier all sit inside that bias.
2. **The deployed path is worth 4.75 CAR points less than the backtest says**, for a reason that is
   a scheduling accident and is fixable. That is a bigger number than any signal lever measured
   since S-9, and it is the one thing on this sleeve where effort has a known, large payoff.
3. **The next candidate is free of the owner's budget question**, which is the first time since
   O-1b that the daily sleeve has had one.

## 2026-09-11 - S-16: the 3x sleeve and the drawdown breaker are worth zero return between them

- **What.** S-15 removed each of the champion's switches one at a time. Two of them pointed the
  same way and were never run together: the **levered proxies** (cell e - better on every
  risk-adjusted measure when off) and the **drawdown overlay** (cell g - the only switch with a
  near-significant paired statistic, and the sign was against it). S-16 runs the interaction, then
  asks the question the attribution could not: when the unlevered book gives up exposure, what
  happens if that exposure is bought back with **account** leverage (`margin_budget`) instead of
  **instrument** leverage (UPRO/TQQQ/TMF)? Nine full-period LEAN cells plus two sub-period runs,
  all environment overrides of the shipped algorithm; `scripts/_s16_runs.sh` produces them,
  `scripts/sweep_s16.py` reads them. 11 ledger rows.
- **Why the two are the same question.** Reg-T charges 50% of notional for an ordinary ETF and
  IBKR marks a 3x ETF to 100%, so per unit of *economic exposure* the proxies cost **0.333** of
  margin and the unlevered names cost **0.5**. The 3x sleeve is 33% cheaper in margin - that, and
  not any signal, is why the champion reaches ~2.25x exposure on a 0.75 budget while the same
  signal held unlevered stops at 1.5x. S-15 measured the proxies with the exposure removed; that
  confounds the instrument with the size.
- **The control reproduces `OrderListHash 5246804e17a67af90028ffceead7d3b3`** (4,735 orders, CAR
  24.404%, Sharpe 0.921, DD 25.100%, fees $45,695.46), so every cell below is a pure override and
  the daily paper runner's path is untouched.

### 1. The table (full period 2012-01-03..2026-09-04)

| cell | budget | held | max exp | orders | CAR% | dCAR | Sharpe | MaxDD% | std | fees | PSR% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **champion (S-12, shipped)** | 0.75 | 3x proxies | 2.25 | 4,735 | **24.404** | | 0.921 | 25.1 | 0.170 | $45,695 | 23.0 |
| (e) proxies off | 0.75 | unlevered | 1.50 | 5,136 | 23.128 | -1.28 | 0.950 | 23.6 | 0.153 | $25,646 | 27.4 |
| (g) overlay off | 0.75 | 3x proxies | 2.25 | 4,768 | 25.998 | +1.59 | 0.967 | 27.2 | 0.174 | $48,970 | 28.5 |
| **(e+g) both off** | 0.75 | unlevered | 1.50 | 5,128 | **24.403** | **-0.00** | **0.994** | **23.7** | **0.155** | **$27,200** | 33.2 |
| (e) proxies off | 0.80 | unlevered | 1.60 | 5,226 | 24.551 | +0.15 | 0.964 | 25.5 | 0.162 | $29,312 | 28.7 |
| (e + wide overlay 0.20/0.30) | 0.80 | unlevered | 1.60 | 5,287 | 25.333 | +0.93 | 0.990 | 25.0 | 0.163 | $30,697 | 32.2 |
| (e+g) | 0.78 | unlevered | 1.56 | 5,219 | 25.307 | +0.90 | 1.003 | 24.6 | 0.160 | $29,800 | 34.0 |
| **(e+g)** | **0.80** | unlevered | 1.60 | 5,283 | **25.903** | **+1.50** | **1.008** | **25.1** | 0.164 | $31,622 | 34.5 |
| (e+g) | 0.82 | unlevered | 1.64 | 5,347 | **26.474** | **+2.07** | **1.012** | 25.7 | **0.168** | $33,530 | 34.9 |

Paired daily log returns, **cell minus champion** (the reverse of S-15's convention), on the 3,689
sessions both books are marked:

| cell | bps/day | t | ann.% | IS bps | IS t | OOS bps | OOS t |
| --- | --- | --- | --- | --- | --- | --- | --- |
| (e) proxies off, 0.75 | -0.41 | -1.21 | -1.03 | -0.50 | -1.26 | -0.30 | -0.52 |
| (g) overlay off, 0.75 | +0.51 | 1.93 | +1.28 | -0.11 | -0.62 | +1.25 | 2.35 |
| **(e+g) both off, 0.75** | **-0.00** | **-0.00** | **-0.00** | -0.49 | -1.25 | +0.59 | 0.84 |
| (e) proxies off, 0.80 | +0.05 | 0.17 | +0.12 | -0.17 | -0.52 | +0.30 | 0.65 |
| (e + wide overlay), 0.80 | +0.30 | 1.00 | +0.75 | -0.14 | -0.45 | +0.82 | 1.51 |
| (e+g), 0.78 | +0.29 | 0.82 | +0.73 | -0.25 | -0.75 | +0.94 | 1.42 |
| (e+g), 0.80 | +0.48 | 1.42 | +1.21 | -0.09 | -0.31 | +1.16 | 1.81 |
| **(e+g), 0.82** | **+0.66** | **2.02** | **+1.67** | +0.07 | 0.24 | +1.36 | **2.16** |

### 2. What it says

- **The two switches are worth exactly zero return between them.** Turn off the 3x proxies and the
  drawdown breaker at the same margin budget and the book earns **24.403%** against the champion's
  24.404% - **-0.00 bps/day at t = -0.00** on 3,689 paired sessions, which is as close to a dead
  heat as fourteen years can produce. It gets there at **0.155 realized vol instead of 0.170, a
  23.7% drawdown instead of 25.1%, PSR 33.2% instead of 23.0% and $27.2k of fees instead of
  $45.7k**. The champion is paying a wider risk footprint and 68% more commission for a return
  that is already there without either device.
- **The proxies buy margin efficiency, not edge.** Their whole contribution is that 2.25x of
  exposure fits inside a 0.75 budget. Give the unlevered book the same *risk* instead - budget
  0.82, realized vol 0.168 against the champion's 0.170 - and it earns **26.474% at Sharpe 1.012**,
  **+0.66 bps/day at t = 2.02**, the first t above 2 the S-track has produced *in favour of* a
  change rather than against one.
- **In an unlevered book the drawdown breaker costs return and buys no drawdown.** At budget 0.80:
  shipped overlay 24.551% / DD 25.5, widened to 0.20/0.30 **25.333% / DD 25.0**, off **25.903% /
  DD 25.1**. Monotone in return, flat-to-better in drawdown - a shelf, not a spike. This is S-8's
  re-arming problem: a step breaker that flattens at -25% and re-arms sells the bottom, and on a
  1.5x unlevered book the tail it is insuring against never justifies the sale.
- **The gain is out of sample, and the loop should say so.** Every cell is negative or flat in
  2012-2019 and positive in 2020-2026 (the winner: IS +0.07 bps/day at t 0.24, OOS +1.36 at
  t 2.16). Sub-periods for (e+g) at 0.80: **IS 18.894% / 0.923 / DD 25.1** against the champion's
  19.18% / 0.884 / 25.1, **OOS 34.687% / 1.124 / DD 23.6** against 30.86% / 0.985 / 22.6. It wins
  the half it did not come from and ties the half it did, which is the right way round, but the
  effect is one regime deep.
- **The budget response is a clean dial, not a cliff**: 0.75 -> 0.78 -> 0.80 -> 0.82 gives CAR
  24.403 / 25.307 / 25.903 / 26.474 at std 0.155 / 0.160 / 0.164 / 0.168 and Sharpe 0.994 / 1.003 /
  1.008 / 1.012. Sharpe *rises* with size here, where on the 3x book (O-1b) it fell.

### 3. Decision

**Nothing shipped and nothing promoted, and this time it is not a refusal.** Three cells - (e) at
0.80, (e+g) at 0.80 and (e+g) at 0.82 - **pass `scripts/evaluate.py` outright** ("BEATS champion":
more CAR, more Sharpe, drawdown inside the 1-point tolerance and far under the 35% cap). Every one
of them needs `margin_budget` above 0.75, and that constant is an **open owner question** opened by
O-1b on 2026-09-10 and still unanswered; `BLOCKERS.md` records that the loop will not move it on
its own, so it did not. The budget-neutral version, (e+g) at 0.75, is the one cell the loop could
have promoted by itself and it **misses by 0.001 CAR points** - `evaluate.py` reports "does NOT
beat champion: 24.403% does not beat 24.404%". The rule is the rule; it is refused, and the honest
description is a dead heat with strictly less risk.

**What went to the owner instead**: a fourth option on the open budget question, which dominates
the one O-1b put there. Option (b) was `margin_budget` 0.75 -> 0.792 keeping the 3x sleeve: about
+1.5 CAR bought at std 0.188. S-16's option (d) is the same +1.50 CAR (25.903% vs 24.404%) at
**std 0.164, the identical 25.1% drawdown, Sharpe 1.008 against 0.921 and 31% lower fees**, because
it spends the buffer on unlevered notional instead of stacking account leverage on top of
instrument leverage. The residual risk it does add is real and is stated there: the Reg-T excess
liquidity falls from 25% to 20% of equity, against economic exposure that falls from up to 2.25x
to 1.60x.

**Champion unchanged at S-12**, `research/champion.json` untouched, `live/` and the scheduled tasks
untouched, no file the daily runner or the intraday trader loads was modified (new scripts only, so
rule (a) owes no replay).

- **A-5 part 2 (standing job) had no new input**: this ran at 07:3x ET, before the open, so the
  ledger is still the single 2026-09-10 session - 32 fills, $1.87M, **+2.89 bps (se 1.33)** against
  the shipped 1.50, |diff|/se 1.05, ~6.8 sessions to settle it. `SLIPPAGE_BPS` untouched.

## 2026-09-11 - S-15: where the champion's 24.4% actually comes from, and it is mostly not skill

- **What.** The attribution S-14 asked for. Eight full-period LEAN runs, each the shipped
  algorithm with exactly one switch removed through an `S1_*` environment override, plus the
  control and a vol-matched steelman: (a) no ranking, (b) no regime filter, (d) no allocation
  tilt, (e) no levered proxies, (g) no drawdown overlay, (f) none of them at all.
  `scripts/_s15_runs.sh` produces the runs, `scripts/sweep_s15.py` reads their LEAN output.
  **Judged nothing**: the deliverable is the table and a sentence.
- **Why.** S-9 through S-14 are six consecutive iterations spent tuning the *ranker*, and S-14
  priced its entire cross-sectional contribution at +2.02 bps/day (t = 2.07). If that is the
  whole of selection, then most of a 24.4% CAR is something else, and nobody had measured what.
- **Two new knobs, both defaulting to the champion**: `S1_MIN_MOMENTUM` (the absolute entry
  floor, so "rank nothing" is expressible as `top_n=9` with the gate off) and `S1_PROXY=off`
  (drop the levered proxy map, hold every winner in its own unlevered name). The control run
  reproduces **`OrderListHash 5246804e17a67af90028ffceead7d3b3`** with 4,735 orders, CAR
  24.404%, Sharpe 0.921, fees $45,695.46 - bit-identical to the champion - so both are inert.

### 1. The table (full period 2012-01-03..2026-09-04)

| cell | orders | CAR% | dCAR | Sharpe | MaxDD% | std | fees | PSR% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **champion (S-12, shipped)** | 4,735 | **24.404** | | **0.921** | 25.1 | 0.170 | $45,695 | 23.0 |
| (a) no ranking (top 9, equal) | 1,704 | 17.700 | **-6.70** | 0.780 | 23.3 | 0.137 | $7,907 | 10.3 |
| (a2) no ranking, vol-matched | 2,332 | 20.745 | **-3.66** | 0.804 | 26.1 | 0.163 | $12,747 | 11.7 |
| (b) regime filter off | 5,495 | 22.383 | -2.02 | 0.781 | **31.4** | 0.189 | $46,318 | 9.6 |
| (d) allocation tilt off | 2,573 | 23.605 | -0.80 | 0.874 | 25.9 | 0.174 | $37,380 | 17.7 |
| (e) levered proxies off | 5,136 | 23.128 | -1.28 | **0.950** | **23.6** | 0.153 | $25,646 | **27.4** |
| (g) drawdown overlay off | 4,768 | **25.998** | **+1.59** | 0.967 | 27.2 | 0.174 | $48,970 | 28.5 |
| **(f) no skill at all** | 1,386 | **17.282** | **-7.12** | 0.711 | 28.8 | 0.149 | $3,357 | 6.1 |

Paired daily log returns, champion minus cell, on the 3,689 trading days both books are marked
(the same split S-12 was promoted on):

| switch removed | bps/day | t | ann.% | IS bps | IS t | OOS bps | OOS t |
| --- | --- | --- | --- | --- | --- | --- | --- |
| (a) no ranking | +2.20 | 1.76 | 5.71 | +1.77 | 1.27 | +2.73 | 1.24 |
| (a2) no ranking, vol-matched | +1.19 | 0.92 | 3.04 | +0.44 | 0.29 | +2.08 | 0.94 |
| (b) regime filter off | +0.65 | 0.53 | 1.66 | **-0.04** | -0.03 | +1.49 | 0.70 |
| (d) allocation tilt off | +0.26 | 0.82 | 0.65 | +0.52 | 1.45 | **-0.06** | -0.10 |
| (e) levered proxies off | +0.41 | 1.21 | 1.04 | +0.50 | 1.26 | +0.30 | 0.52 |
| (g) drawdown overlay off | **-0.51** | **-1.93** | -1.27 | +0.11 | 0.62 | **-1.25** | **-2.35** |
| (f) no skill at all | +2.35 | 1.37 | 6.09 | +1.04 | 0.56 | +3.92 | 1.30 |

### 2. What it says

- **71% of the champion's CAR is no skill of any kind.** Cell (f) - the nine ETFs held
  equal-weighted, every name unlevered, no ranking, no entry gate, no regime filter - earns
  **17.282%** through the vol target, the margin budget and the overlay alone, against the
  champion's 24.404%. The whole signal stack is worth **+7.12 CAR at t = 1.37**. The sizing
  machinery is doing the heavy lifting: the unlevered pool itself earns ~13.9%/yr (S-14's
  5.20 bps/day menu), and SPY over the same window compounds at 9.5%.
- **Nothing the loop has tuned is individually distinguishable from zero.** Not one switch
  reaches |t| = 2 on the paired daily series, and the only one that comes close is the drawdown
  overlay **with the sign against it** (-0.51 bps/day, t -1.93; OOS -1.25 at **t -2.35**).
- **The ranker is the biggest piece and a third of it is leverage, not selection.** Removing
  ranking costs 6.70 CAR, but it also drops realized vol 0.170 -> 0.137: hold 9 names instead of
  3 and the book is simply more diversified. Sized back to the champion's own volatility
  (`margin_budget` 0.93, std 0.163) the no-ranking book earns **20.745%**, so ranking is worth
  **+3.66 CAR at t = 0.92**, not +6.70. That is the same ~2 bps/day S-14 measured unlevered,
  arriving by a completely different route.
- **The regime filter is a drawdown instrument, not a return one.** +2.02 CAR at t = 0.53, and
  its in-sample contribution is **exactly zero** (-0.04 bps/day, t -0.03) - the whole of it is
  2020-2026, i.e. COVID and 2022. What it reliably buys is risk: drawdown **31.4 -> 25.1** and
  realized vol **0.189 -> 0.170**.
- **The 3x proxies buy volatility, not edge.** Held in their unlevered parents the same signal
  earns 23.128% at **Sharpe 0.950, drawdown 23.6%, std 0.153 and PSR 27.4%** - better than the
  champion on every risk-adjusted measure and on fees ($25.6k against $45.7k) - for 1.28 CAR.
  This is L-1's intraday finding on the daily sleeve: leveraged instruments supply volatility,
  and the vol target then hands most of that volatility back.
- **The last promotion is in-sample.** S-12's allocation tilt is +0.80 CAR overall, but
  **+0.52 bps/day (t 1.45) in 2012-2019 and -0.06 (t -0.10) in 2020-2026**. It was promoted on
  a full-period run that beat the champion on all three criteria; the halves say the edge is
  not there after 2020. Not a reason to demote - t is nowhere near 2 in either direction - but
  it is the honest read.

### 3. Decision

**Nothing shipped, nothing promoted, nothing refused.** `research/champion.json` is unchanged at
S-12, the control reproduces the deployed order list hash, and `live/` and the scheduled tasks
were not touched (all eight cells are environment overrides; the item owes no replay and the
intraday trader was not loaded). The sentence S-15 was asked for: **the champion is a levered
long-ETF-beta book with a volatility governor, and the four switches the research loop has spent
six iterations tuning are worth about seven CAR points between them, none of which is
individually distinguishable from zero on fourteen years of daily data.**

**What it changes.** Further ranker tuning is the lowest-value work available: its measured
contribution is +3.66 CAR at t = 0.92, and S-14 showed it does not survive dilution. The two
components with real, repeatable effects are the ones nobody has swept - the **vol target /
margin budget** (which produces 71% of the return) and the **regime filter** (which produces the
drawdown profile). Both are risk-posture parameters, so both run into the open owner questions in
`BLOCKERS.md` rather than into another backtest.

- **A-5 part 2 (standing job) had no new input**: this ran at 06:3x ET, before the open, so the
  ledger is still the single 2026-09-10 session - 32 fills, $1.87M, **+2.89 bps (se 1.33)**
  against the shipped 1.50, |diff|/se 1.05, ~6.8 sessions to settle it. `SLIPPAGE_BPS` untouched.

## 2026-09-11 - S-14: breadth, and the discovery that the champion's whole cross-sectional edge is one thin number

- **What.** The backlog closed its last open mechanism yesterday (S-2), so this iteration took
  the one direction the repository has repeatedly named and never measured: **breadth**. S-12's
  note says "what remains inside a three-name ETF book needs breadth (correlation-aware weights
  want more than nine names)" and the 2026-09-09 owner decision says volatility is to be earned
  by widening, not by leverage. The champion ranks **nine** unlevered ETFs and holds the top
  three, i.e. a third of its own universe - which is barely a selection at all.
- **Why it should have worked.** Cross-sectional momentum earns the spread between the names it
  picks and the names it passes over. With 9 candidates the top 3 is 33% of the menu; completing
  the GICS sector map (the sleeve carries only XLK/XLF/XLE) takes it to 18%, and the sectors it
  is missing are genuinely dispersed - utilities against energy can differ by forty points in a
  year. More candidates should mean a better top three.
- **Data.** Fetched the eight missing sector SPDRs and five asset-class ETFs from Yahoo through
  the shipped D-1 pipeline (XLV XLY XLP XLI XLU XLB XLRE XLC EFA HYG IEF SLV VNQ, 1998-2026, all
  validated, factor deviation 0.00000). Two of them list mid-sample (XLRE 2015-10-08, XLC
  2018-06-19) and the ranking gate in `target_weights` admits a name only once it has a full
  lookback of priced bars, so they enter on their own schedule and nothing is back-dated.
- **Three nested sleeves**, so the only thing that changes between runs is how many names the
  signal ranks: `etf9` (shipped, 9), `sector` (17), `broad` (22), added as presets in `main.py`.
  The pre-registered rule, fixed before the runs: promote only through `evaluate.py`, and only
  if the wider sleeve also wins **both** sub-periods and the two nested sleeves agree in sign.

### 1. LEAN, full period 2012-01-03..2026-09-04

| sleeve | ranked | orders | CAR | Sharpe | MaxDD | ann.std | fees | PSR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **etf9 (champion, control)** | 9 | 4,735 | **24.404%** | **0.921** | 25.1% | 0.170 | $45,695 | 23.0% |
| sector | 17 | 5,534 | 17.253% | 0.663 | 30.3% | 0.163 | $40,726 | 4.0% |
| broad | 22 | 5,629 | **11.622%** | **0.430** | 29.7% | 0.165 | $32,236 | 0.3% |
| sector, `top_n=5` | 17 | 7,696 | 19.625% | 0.826 | 21.7% | 0.147 | $41,693 | 13.9% |
| sector, `top_n=5`, budget 0.867 (vol-matched) | 17 | 8,279 | 22.879% | 0.872 | 23.6% | 0.168 | $57,670 | 17.6% |

**Monotone in the number of candidates, and monotone the wrong way**, at essentially unchanged
realized volatility (0.170 / 0.163 / 0.165). `evaluate.py` refuses all four candidates. The
control reproduces **`OrderListHash 5246804e17a67af90028ffceead7d3b3`** exactly, so the two new
constants are inert on the deployed path, and `compare_orders.py` still passes 3,689/3,689.

Sub-periods for the nearest candidate (`sector`, top_n 3) against the champion's recorded halves:
**IS 2012-2019 12.626% / 0.603 / 30.3%** against 19.18% / 0.884 / 25.1%, **OOS 2020-2026 22.929%
/ 0.739 / 20.1%** against 30.86% / 0.985 / 22.6%. It loses in both halves, so this is not a
regime artifact.

### 2. Why - the decomposition, with leverage and the vol target switched off

`scripts/sweep_s14.py` walks the same signal day by day with no drawdown overlay, no vol target,
no margin budget and no levered proxies, and splits the unlevered top-3 basket's daily return
into `selected = pool_mean + spread`: the quality of the **menu**, which the signal is not
responsible for, and the **spread**, which is the only part ranking earns.

| sleeve | selected | pool mean | spread | t | unlevered CAR | Sharpe | MaxDD | churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| etf9 | 7.21 bps/day | 5.20 | **+2.02** | **2.07** | 15.5% | 1.18 | 22.4% | 0.15 |
| sector17 | 5.73 | 4.90 | +0.82 | 0.81 | 12.0% | 0.96 | 15.7% | 0.20 |
| broad22 | 5.27 | 4.32 | +0.94 | 0.82 | 10.8% | 0.83 | 14.3% | 0.21 |

Paired on the 3,099 days both books are invested: **sector17 - etf9 = -1.37 bps/day (t -1.95)**,
**broad22 - etf9 = -1.89 (t -2.23)**. Of the -1.48 bps that separates etf9 from sector17, only
**-0.30 is the menu** and **-1.20 is the spread**: four fifths of the damage is the signal
picking worse, not the added names being worse assets. The spread falls in both halves
(etf9 1.69 / 2.43 against sector17 0.32 / 1.45).

**The finding that matters more than the verdict**: the champion's entire cross-sectional
contribution is **+2.02 bps/day at t = 2.07** over fourteen years, and it exists only at
top-3-of-9. Re-run at `top_n=5` the spreads collapse into each other and none is significant -
etf9 **+0.84 (t 1.16)**, sector17 +0.99 (1.32), broad22 +1.34 (1.59). So the champion is not a
broad momentum engine that happens to run on nine names; it is a concentrated bet whose edge is
thin, and every dilution of that concentration - more candidates, more holdings - costs it.

### 3. Two things breadth *does* buy, and what they cost

Composition (`--mode compose`): widening moves **38.4%** (sector) and **45.0%** (broad) of funded
slots into names the shipped sleeve does not have, and cuts the share of funded slots in names
that carry a 3x proxy from **32.7% to 17.6% / 15.8%** - the sleeve starts winning momentum races
with defensives (XLV 20%, XLU 17%, XLP 9%) and silver (SLV 22% in broad). **This is not why it
loses**: realized vol is unchanged across all three books, because the vol target and margin
budget lever the unlevered winners back up. The steelman confirms it - `top_n=5` on the wide
sleeve recovers 2.4 points of CAR and 8.6 points of drawdown, and **sized to the champion's own
0.17 std it still earns 22.879% at Sharpe 0.872 against 24.404% / 0.921, on 8,279 orders against
4,735 and $12k more commission.** What breadth genuinely delivers is diversification: the
unlevered basket's drawdown falls 22.4% -> 15.7% -> 14.3% and the vol-matched book's is 23.6%
against 25.1%. It buys a smoother path and pays 1.5 points of CAR and 75% more turnover for it.

### 4. Two defects fixed in the data tool on the way

- `fetch_data.py` **rewrote the whole manifest** from each run, so today's 13-symbol fetch erased
  the provenance record of the other 69. Same shape as the `alpaca_data.py --splits` landmine S-2
  fixed yesterday, and cheaper only because nothing reads this file. It now **merges** per symbol
  and prints `(n re-derived, m kept)`; the 69 lost entries were restored from git and a no-op
  re-fetch of SLV verifies the path (1 re-derived, 81 kept, 82 on disk).
- `--symbols <ONE>` **crashed**: yfinance ignores `group_by="ticker"` for a single-symbol batch
  and returns (field, ticker) MultiIndex columns, so the frame handed to `dropna` had no `Open`
  column. The ticker is now selected from whichever column level carries it. Verified: a
  one-symbol run reproduces the batch run's 5,124 SLV bars.

### 5. Decision

**Refused and closed; nothing shipped.** `research/champion.json` is unchanged at S-12, the daily
runner's order list is bit-identical (hash reproduced, deploy gate passes), and `live/` and the
scheduled tasks were not touched. The two new sleeve presets stay in the tree defaulted off
(`S1_SLEEVE=etf`), because the decomposition behind the refusal is worth being able to re-run.
**Do not re-open breadth as a "which names" question** - three nested pools, two holding counts
and a vol-matched control all point the same way, and the mechanism is measured: the ranking
spread does not survive dilution. The honest successor question is the opposite one, and it is
uncomfortable: if +2.02 bps/day at t = 2.07 is the whole cross-sectional edge, then most of the
champion's 24.4% CAR is the levered beta of a 3x proxy basket plus the regime filter, not
selection - which is worth measuring before any further work is spent on the ranker.
- **A-5 part 2 (standing job) had no new input**: this ran at 05:3x ET, before the open, so the
  ledger is still the single 2026-09-10 session - 32 fills, $1.87M, **+2.89 bps (se 1.33)**
  against the shipped 1.50, |diff|/se 1.05, ~6.8 sessions to settle it. `SLIPPAGE_BPS` untouched.

## 2026-09-11 - S-2: the index-ETF opening-range breakout, and the stop that makes both signs look profitable

- **What.** S-2 has been on the backlog since 2026-09-08 and was unblocked for SPY on 2026-09-09:
  an opening-range breakout as a **second sleeve** on SPY/QQQ/IWM, with TQQQ as the leveraged
  read. It is the last open research item in the repository that is not parked, an owner
  question, or infrastructure. The A-track already measured an ORB on sixteen single names at
  -$331/day, so the question here is narrow: the index ETFs are a **different universe** - an
  order of magnitude more liquid, a high enough share price that IBKR's per-share commission is
  near-invisible (the measured round trip here is **3.65 bps**, of which 3.0 is slippage, against
  the A-track universe's 4.70), no single-name event risk - and they are the only intraday
  instruments the daily champion could plausibly share.
- **Two stages, the cheap one first**, which is the standing lesson from L-1, X-1 and O-2:
  measure the mechanism on the whole history with nothing fitted, and build the expensive
  harness only if gross clears the cost floor. New `scripts/sweep_s2.py` is the event study;
  stage 2 is the **shipped ORB module through the deployed framework** (`intraday_backtest.py
  --strategy orb --symbols SPY QQQ IWM`), one run per regime, three ledger rows under
  `intraday/orb`. Data: SPY/QQQ/IWM fetched here from Alpaca SIP (2016-01-04..2026-09-10,
  ~1.046M bars each; the store is now 63 symbols).
- **The decision rule was fixed before the runs**: a cell passes only if the per-session net $
  series is positive at **t > 2 in at least two of the three a-priori regimes** (2016-2019 /
  2020-2023 / 2024-2026), and only if its own fade control does not also pass.

### 1. A landmine found on the way in, and fixed

`alpaca_data.py --splits` **replaced** the store's split table with only the symbols passed, and
`--symbols` defaults to the 16-name UNIVERSE while `--start` defaults to 2024-01-01. A bare
`python scripts/alpaca_data.py --splits` therefore rewrites a 60-symbol table as 16 symbols
measured over two years, and every dropped name then costs at `share_scale` 1.0 - which is the
exact defect A-10 spent an iteration fixing, worth up to 40x on the per-share commission, and it
would have been silent. `write_splits()` now **merges** into the existing file and prints how many
entries it kept against how many it re-derived. Verified: the table is 63 symbols, SPY/QQQ/IWM all
factor 1.0 (no splits in the sample, as expected for these three), and **all 60 pre-existing
factors are byte-identical** to the pre-run backup.

### 2. Stage 1: the mechanism, 2,687 sessions, nothing fitted

Opening range = the first `orb_min` minutes; a breakout is a bar whose **close** is beyond the
range and the fill is the **next bar's open** (the harness's causal convention); stop is one
range ('opp') or half a range ('mid') from the fill; otherwise the trip is closed on the last bar
of the session. One trip per session per symbol. $250,000 a trip, shipped costs.

**0 of 16 breakout cells pass, and every one of them loses money:**

| best four cells, net | trips/day | gross bps/trip | cost | net bps/trip | $/day all | t |
| --- | --- | --- | --- | --- | --- | --- |
| orb15 mid e120 | 2.94 | +2.11 | 3.65 | **-1.54** | -113 | -1.64 |
| orb60 mid e120 | 2.15 | +1.76 | 3.65 | -1.89 | -101 | -1.57 |
| orb15 opp e120 | 2.94 | +1.43 | 3.65 | -2.22 | -163 | -1.89 |
| orb30 mid e120 | 2.78 | +1.16 | 3.65 | -2.49 | -173 | -2.51 |

**The finding is why the gross looked positive.** Run the same machinery on the *fade* - the
falsification control - and it earns positive gross too, in **14 of 16 cells**. Both signs cannot
own a directional edge, so the gross splits into a part the signal owns, `(breakout - fade)/2`,
and a part both signs share, `(breakout + fade)/2`:

| | gross brk | gross fade | **directional edge** | stop convexity | cost/trip |
| --- | --- | --- | --- | --- | --- |
| orb15 mid e120 | +2.11 | +0.76 | **+0.67** | +1.43 | 3.65 |
| orb60 mid e120 | +1.76 | -0.42 | **+1.09** | +0.67 | 3.65 |
| orb5 opp e120 | +0.53 | +1.05 | **-0.26** | +0.79 | 3.65 |
| orb30 opp e390 | +0.43 | +0.97 | **-0.27** | +0.70 | 3.65 |

The shared part is **positive in all sixteen cells** (+0.33 to +1.43 bps) and it is not edge: a
stop plus a hold-to-close exit is convex in either direction, so a coin flip collects it, and it
is the reason a naive ORB study reports a "+2 bps" gross that no signal produced. **The largest
directional edge anywhere in the grid is +1.09 bps against a 3.65 bps round trip - 0.30x - and in
6 of 16 cells it is negative**, i.e. the fade beats the breakout. That is X-1's verdict on a
different instrument: the effect is real, tiny, and an order of magnitude under the cost floor.

**TQQQ, the leveraged read (8 cells): 0 of 8 pass, and the direction disappears entirely.** Cost
is **4.85 bps** a round trip, not 3.65, because the same per-share commission is charged on a much
lower share price. In the best cell the breakout earns **+$33.78/day and its own fade
+$33.79/day** - identical to the cent, so there is nothing directional left at all - and the
cell with the largest separation, `orb30 opp`, runs **+$225 / +$95 / -$396** across the three
regimes. Leverage supplies volatility here, not edge, which is exactly what L-1 measured.

### 3. Stage 2: the same thing through the shipped harness

The deployed ORB module (volume filter, midpoint stop, two entries a side, time stop, the daily
loss limit and the 15:38 flatten), `--symbols SPY QQQ IWM`, `weight` 0.12 x 3 names = **0.36x
gross on a $1M book**:

| regime | sessions | $/day | Sharpe | trades/day | costs/day | turnover/day | **implied gross/day** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2016-2019 | 1,006 | **-186** | -2.14 | 8.8 | 179 | 0.94x | -7 |
| 2020-2023 | 1,006 | **-211** | -1.67 | 8.5 | 157 | 0.88x | -54 |
| 2024-2026 | 675 | **-39** | -0.35 | 8.6 | 175 | 1.01x | +136 |
| **all** | **2,687** | **-158** | | 8.6 | 171 | | **+11** |

**0 of 3 regimes.** Backing the costs out is the cleanest statement this iteration produces:
over eleven years the index-ETF ORB generates **+$11/day of gross on a $1M book and pays $171/day
to collect it**, and the gross is negative in two of the three regimes separately. The two
instruments agree in sign and in magnitude once the different book sizes are lined up (the event
study's -$113/day at 0.75x gross scales to -$54/day at 0.36x against the harness's -$158; the
harness is the more negative because it takes 8.6 trips a day where the event study takes 3.0),
so no harness reconciliation is owed beyond this.

**Stage 1's known optimism only helps the strategy.** It closes an untouched trip at the last
minute bar, and D-2 measured the daily close diverging from that bar by up to ~1% on violent days
because the close is the auction print. Modelling the auction with a market-on-close order - the
thing backlog S-2 specifically asks for in LEAN - can only make these numbers worse, which is why
the refusal does not need the LEAN build.

### 4. Decision

**Refused and closed; nothing shipped.** No file the live trader or the daily runner loads was
touched. The only behaviour change anywhere is `alpaca_data.py --splits` merging instead of
replacing, which is a research-store fix that makes a silent cost-model regression impossible;
`live/intraday_config.json`, `live/APPROVED_PAPER.md`, `live/HALT*` and the scheduled tasks are
untouched, and the rule-(a) replay of 2026-09-08 with the exact deployed config reproduces the
sleeve to the digit: **34 trades, 368 decisions, flat at close, P&L -2,302 on 500k**. Champion
unchanged at S-12.

**Do not re-open S-2 as a range-length, stop, entry-window, symbol or resolution question** - the
grid spans the first four and the negative is on *gross*, in both signs, on 2,687 sessions and
through two independent instruments. What would be a different question, and is not on the
backlog, is a breakout with a **holding period longer than a session**; everything measured here
is about a book that must pay a round trip every day.

**On the mandate.** Daily P&L standard deviation is **$1,339-$1,954 on a $1M book at 0.36x
gross**, i.e. 0.13-0.20% of equity, or roughly 0.5% at 1x. Like L-1 (0.49%) and X-1 (0.27%) this
is two orders of magnitude short of the owner's 3-10%/day, before the sign is even considered.

**A-5 part 2 ran first, as the standing job, and had no new input**: `slippage_report.py` still
finds exactly one session with live intraday fills (2026-09-10, 32 fills, $1.87M, **+2.89 bps
notional-weighted, se 1.33** against the shipped 1.50; |diff|/se = 1.05, so `SLIPPAGE_BPS` was not
touched), because this ran at 04:3x ET, before today's open. ~6.8 more sessions settle it. Note
for whoever runs it next: it needs plain `python`, not `py -3.11` - the LEAN-side 3.11 has no
pyarrow and the script reads the parquet store.

**What is left.** With S-2 refused, the backlog holds no open research item with a stated
mechanism: A-8 is parked by A-4's power calculation, A-3 is settled by A-10, D-2b and E-2b are
infrastructure, and S-5 (the allocator) needs two sleeves with positive expected return and there
is one. Every remaining lever in this repository is an **owner decision** in `BLOCKERS.md` - the
`equity_frac` question on the intraday sleeve, `margin_budget` on the daily champion, the 35%
drawdown cap, and the dead alert channel.

## 2026-09-11 - A-11: the impossible fills are real, and they are not load-bearing

- **What.** A-5 measured that the sleeve's orders are **median 1.03%, p90 5.55%, p99 26.1% and at
  worst 199%** of the volume of the minute they fill in, on the 260-session IBKR store, and called
  it a cost-model defect rather than a lever: a fill of a fifth of a minute's volume at that
  minute's open with zero impact is not a fill. A-11 sizes the defect on ten years and asks the
  only question that matters - **what does the sleeve earn when the impossible fills are gone?**
  `scripts/sweep_a11.py` on the Alpaca SIP store (2,686 sessions, 2016-01-04..2026-09-09, the
  deployed allocation, which after A-10 is ORB alone), one backtest per (cell, calendar year) from
  a fresh $1M book, pooled into A-10's three a-priori regimes; 18 ledger rows under
  `intraday/active`. `RISK["part_cap"]` clips every order to a share of the **trailing median**
  volume of the minute it will fill in (`volume_limits()`, 20 prior sessions, strictly before the
  session, so the cap is knowable at decision time); a clipped order is *worked* over the following
  bars rather than dropped, and whatever the cap cannot work off by the close is dumped into the
  closing bar and counted.
- **Provenance, stated plainly.** The three sweeps (main grid, and the universe split in half by
  participation) ran to completion at 03:40-04:03 ET in the preceding iteration, which was cut off
  before it wrote anything. This iteration verified the outputs against the store, added the
  cost/gross decomposition and the paired liquid-vs-illiquid statistics below, ran the replay, and
  recorded the result. No sweep was re-run; nothing in the ledger was rewritten.
- **The decision rule was fixed before the runs** and cannot promote anything: A-10 measured this
  book at -$289/day and a cap can only make a losing book smaller. The outcomes that mattered were
  (a) capped materially *better* - the shipped numbers were dragged down by impossible fills;
  (b) materially *worse* - every A-track number is optimistic by that amount; (c) inside one
  standard error - the defect is real and immaterial, and the honest record is that it was measured.

### 1. The diagnostic: the defect is four times what the IBKR window showed

90,441 fills, 16 names, 2,686 sessions, each fill's size against the **actual** volume of the
minute the backtester assumed it filled in, notional-weighted:

| | p50 | p75 | p90 | p99 | max |
| --- | --- | --- | --- | --- | --- |
| A-5, 260 IBKR sessions | 1.03% | - | 5.55% | 26.1% | 199% |
| **A-11, 2,686 Alpaca sessions** | **1.46%** | **4.71%** | **18.80%** | **950%** | **38,759%** |

**24.1% of traded notional fills at more than 5% of its minute, 9.7% at more than 20%, and 4.1%
(3,651 fills) at more than 100%** - orders larger than everything that traded in the minute they
are booked at. It is one half of the universe:

| sym | notional % | median % | p90 % | p99 % | sym | notional % | median % | p90 % | p99 % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SMCI | 4.8 | **23.04** | **1733** | 4668 | NFLX | 7.0 | 1.86 | 7.23 | 26.3 |
| SOXL | 7.6 | 5.14 | 159 | 1400 | GOOGL | 7.0 | 1.58 | 6.30 | 23.1 |
| MSTR | 5.2 | 7.21 | 143 | 834 | NVDA | 7.1 | 0.50 | 5.24 | 33.9 |
| SOXS | 4.0 | 3.80 | 28.2 | 106 | TSLA | 7.2 | 0.27 | 4.33 | 23.5 |
| AVGO | 7.2 | 4.99 | 21.5 | 68.2 | MSFT | 7.1 | 0.91 | 4.25 | 13.0 |
| PLTR | 3.9 | 2.34 | 17.9 | 79.5 | META | 7.2 | 0.86 | 3.01 | 9.26 |
| COIN | 4.0 | 2.45 | 10.5 | 35.7 | AMZN | 7.1 | 0.55 | 2.02 | 6.93 |
| AMD | 6.8 | 0.86 | 9.97 | 491 | AAPL | 6.8 | 0.50 | 1.63 | 4.55 |

The store is split-adjusted on **both** price and volume - SMCI 2016-01-04 shows 4.34M adjusted
shares at an adjusted $2.39, i.e. 434k real shares at $23.88 - so the ratio is internally
consistent and these are real participations, not an adjustment artifact. That was checked against
the raw tape before any of the numbers below were believed.

### 2. The cap: removing the impossible fills costs the book nothing in gross

Paired against the uncapped control on the same 2,686 sessions, and decomposed against the cost
per day the ledger rows carry:

| cap | tr/day | $/day | t | vs off $/day | vs off t | costs/day | **implied Δgross** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| off (shipped) | 34.9 | -331 | -1.35 | | | 907 | |
| 0.10 | 95.3 | -336 | -1.39 | **-5** | -0.25 | 917 | **+5** |
| 0.05 | 137.2 | -367 | -1.52 | -36 | -1.24 | 941 | -2 |
| 0.02 | 206.8 | -430 | -1.83 | -99 | **-2.40** | 969 | -37 |

By regime the paired difference is -11 / -3 / +1 at the 0.10 cap (t -0.34 / -0.06 / +0.38) and
never reaches |t| = 2 except at 0.02 in 2016-2019. **Outcome (c), and sharply.** At the 0.10 cap
the backtester clips **213,338 orders** and refuses a cumulative **$4.78M/day** of intended
notional against $3.59M/day actually executed (the same intended position is re-clipped every
minute until it is worked off, so that flow is far larger than the book's turnover), and the book
moves by **-$5/day at t = -0.25** - of which **+$10/day is the extra commission and slippage of
slicing**. The gross is unchanged. Only at 0.02, where the sleeve is forced to 207 trades a day,
does gross itself erode ($37/day), and that is the cost of the slicing schedule, not lost alpha:
the cap also starts failing, dumping 261 fills and $2,269/day of un-workable residual into the
closing bar.

**So the fills nobody could get were not the ones making the money.** Every A-track number stands
where it is: the sleeve's negative result is not an artifact of impossible fills, and the shipped
`part_cap = 0` stays, because switching it on buys nothing and pays 3x the turnover for it.

### 3. The half of the universe whose fills are real is the half that never made money

The strongest thing in this iteration is not the cap. Running the same book on the 8 names whose
fills are executable and the 8 whose are not, as two disjoint $1M books over the same sessions:

| universe | fills > 5% of the minute | $/day, 2,684 sessions | t | Sharpe | tr/day | costs/day |
| --- | --- | --- | --- | --- | --- | --- |
| **liquid 8** (AAPL AMZN META MSFT TSLA NVDA GOOGL NFLX) | **8.8% of notional** | **-195** | **-1.89** | -0.54 | 18.1 | 385 |
| **illiquid 8** (SMCI SOXL MSTR SOXS AVGO PLTR COIN AMD) | **45.8%** | -164 | -0.83 | -0.23 | 15.1 | 553 |
| full 16 (deployed) | 24.1% | -329 | -1.34 | -0.37 | 34.9 | 907 |

The two halves are not redundant (corr of daily P&L 0.498) and the paired difference between them
is **-$31/day at t = -0.18**, i.e. indistinguishable - but the liquid half, where the median fill
is 0.89% of its minute and only 1.0% of notional exceeds 20%, is the **most significant negative
reading this sleeve has ever produced**. Restricting to the names where the backtest is believable
does not rescue it; it sharpens the loss.

And it accounts for the one piece of positive evidence the sleeve has:

| | fitted window (261 sessions, >= 2025-08-26) | t |
| --- | --- | --- |
| liquid 8 | **-$102/day** | -0.40 |
| illiquid 8 | **+$361/day** | +0.42 |
| full 16 | +$278/day | +0.29 |

**The only window in eleven years where this sleeve made money made all of it in the half of the
universe whose fills cannot be trusted** - the half where the median order is 4.12% of its minute,
p90 is 94% and 21.8% of notional exceeds a fifth of the minute's volume. That is the same finding
as A-9's holdout in another shape, and it is the last defence the sleeve had.

- **Decision. Refused and closed; nothing shipped.** `part_cap` stays 0 in the shared sizing code,
  `live/intraday_config.json`, `live/APPROVED_PAPER.md`, `live/HALT*` and the scheduled tasks were
  not touched, and the only file changed is `scripts/sweep_a11.py` (a `--label` flag so a subset
  run cannot be confused with the main one). Champion unchanged at **S-12**; the daily sleeve was
  not touched.
- **Rule (a) replay.** No file the live trader loads moved, so none was owed; run anyway against
  the deployed config - 2026-09-08, `--equity-frac 0.5` with the config's params: **34 trades, 368
  decisions, flat at close, P&L -2,302 on 500k**, identical to A-12's. (The toolchain note from
  2026-09-10 still bites: a *naive* `--replay` reads strategy defaults at `equity_frac` 1.0 and
  reports 217 trades / -10,051, which looks like a regression and is not one.)
- **A-5 part 2, the standing job: no input today.** `slippage_report.py` still finds exactly one
  session with live fills (2026-09-10, 32 fills, $1.87M): **+2.89 bps notional-weighted, se 1.33,
  against the shipped 1.50 - |diff|/se = 1.05**, not yet 2 se, so `SLIPPAGE_BPS` was not touched.
  ~6.8 more sessions settle it against A-5 part 1's 2.52 bps breakeven.
- **Next.** The A-track is now out of levers *and* out of defences: A-9 killed the entry gate, A-10
  killed the level, O-1 killed the regime conditioner, A-12 killed the re-entry filter, and A-11
  has now killed the last "the backtest was unfair to it" argument in both directions - the
  impossible fills were not helping, and the executable names lose at t = -1.89. The open owner
  question in `BLOCKERS.md` (keep `equity_frac` 0.5 to finish the slippage measurement, or retire
  the sleeve to 0.0) is the only thing left on it, and A-11 is appended there as evidence.

## 2026-09-11 - A-12: the ORB whipsaw lockout - the mechanism is real, measured, and points the other way

- **What.** The question the 2026-09-10 paper session left behind: the sleeve lost -6,779 and
  **-5,191 of it (77%) came from one pattern** - short SOXL/SOXS at 09:52 ET, stopped out into a
  rally at 10:25, long the same pair at 10:36, out into the fade at 12:35. The shipped ORB module
  permits that by construction, because `max_entries` is counted **per side**, so being stopped out
  of a short never consumes any of the long budget, and nothing in A-1..A-11 ever tested it. New
  `reentry_block` / `reentry_mode` on the ORB module (default **0 = off**, the shipped behaviour)
  and new `scripts/sweep_a12.py`; 18 ledger rows under `intraday/active`.
- **Why in two stages.** L-1's discipline: measure the mechanism where there is nothing to fit
  before pricing a parameter. Stage 1 labels the control's own round trips and fits nothing;
  stage 2 is the paired grid, one backtest per (variant, calendar year) from a fresh $1M book on
  2,686 sessions of the Alpaca SIP store, pooled into the three a-priori regimes.

### Stage 1: the premise is refuted at the root, and the sign is inverted

Every fill of the deployed control reconstructed into round trips per (symbol, session) - P&L is
the book's own cash change over the trip's fills, costs included, nothing re-priced - and each trip
labelled by what preceded it that day in that symbol:

| kind | trips | $/trip | t | win % | total $ |
| --- | --- | --- | --- | --- | --- |
| first entry of the session | 35,025 | **-25** | -2.66 | 40.2 | **-872,347** |
| `flip` (the 2026-09-10 pattern) | 4,841 | **+15** | +0.65 | 38.9 | **+70,708** |
| `same` (continuation re-entry) | 4,353 | -20 | -1.03 | 39.5 | -88,087 |
| ALL | 44,219 | -20 | -2.50 | 40.0 | -889,726 |

**The reversal re-entry is the only profitable category in the sleeve.** The loss is in first
entries - 98% of it - and a filter on re-entries cannot reach it. By regime the flip trip earns
+3 / -27 / +89 $/trip and is never the worst of the three. How long the effect lasts is the
sharpest part:

| gap since the last exit | flip n | flip $/trip | t | same n | same $/trip | t |
| --- | --- | --- | --- | --- | --- | --- |
| 0-15 min | 1,670 | **+78** | +1.72 | 1,036 | **-81** | **-1.96** |
| 15-30 | 1,368 | -26 | -0.66 | 1,456 | -14 | -0.38 |
| 30-60 | 1,333 | -12 | -0.34 | 1,412 | +13 | +0.41 |
| 60-120 | 470 | -14 | -0.25 | 449 | -7 | -0.12 |

Everything the data has to say is inside the **first fifteen minutes**, and it says the opposite of
the anecdote: a fast reversal is the sleeve's best trade and a fast continuation is its worst. So
the grid dropped the dead pre-registered lengths (30/120/999), added 15, and kept 60 as the
"inside an hour" reading of the live session.

### Stage 2: the paired grid, 2,686 sessions, and 0 of 5 cells pass

Paired daily difference against the deployed control (same sessions, same bars, only the entry
filter moves):

| cell | dtr/day | 2016-2019 d$ / t | 2020-2023 d$ / t | 2024-2026 d$ / t | ALL d$/day | t | regimes t>2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| flip 15 | -0.4 | -7 / -0.44 | -49 / -1.29 | -37 / -0.45 | **-31** | -1.17 | 0 |
| flip 60 | -2.0 | -15 / -0.42 | -43 / -0.47 | -100 / -0.73 | **-47** | -0.93 | 0 |
| any 15 | -0.5 | +10 / +0.63 | +40 / +0.63 | -65 / -0.76 | +3 | +0.08 | 0 |
| same 15 | -0.1 | +16 / +0.97 | +75 / +1.44 | +16 / +0.43 | **+38** | +1.69 | 0 |
| same 60 | -1.7 | +20 / +0.62 | -5 / -0.08 | +68 / +0.83 | +23 | +0.68 | 0 |

**Gate 1 (mechanism) fails for every cell, and the two cells with the hypothesised sign are the
two that lose.** Blocking the whipsaw reversal costs -$31 to -$47/day. The only cell with a
positive sign is `same`, which was written as the *falsification control* - and it is exactly what
stage 1 predicted, so the two instruments agree. It is not a candidate either: it was chosen after
seeing the gap table, i.e. in sample, it removes 0.1 trades/day, and it does not reach t = 2 in any
regime. **Gate 2 (deployability) fails for all five**: the book stays negative everywhere -
control **-$331/day, t -1.35**, best variant `same15` -$293/day, t -1.19, and no variant reaches
t > 2 in a single regime, let alone two.

### A free measurement: the corrected cost model, on the full sample

This control is the first full-sample re-run of the deployed sleeve since A-5 part 2 charged the US
sell-side regulatory pass-throughs. Trades/day are identical to A-10's rows to the decimal
(27.3 / 39.4 / 39.1), so the whole difference is the fee fix: **ORB alone moves from -$289/day to
-$331/day** (regimes -251 -> -287, -476 -> -522, -65 -> -112). Every A-track number quoted before
2026-09-10 noon is light by about $42/day on this configuration.

### Decision

**Refused; nothing shipped.** `live/intraday_config.json`, `live/APPROVED_PAPER.md`, `live/HALT*`
and the scheduled tasks were not touched; the parameter stays in the module defaulted off. Rule (a)
replay of 2026-09-08 against the current trader with the deployed config: **34 trades, 368
decisions, flat at close, P&L -2,302 on 500k** - identical to the post-fee-fix figure recorded on
2026-09-10, so the new code is inert on the live path. On the 261 sessions any A-track parameter
has ever seen - the window that produced every A-track false positive - the control earns +$278/day
and nothing here would have shipped from it either (`same60` +320, `flip60` +138, all t < 0.4).

**Do not re-open as a block-length, mode or symbol question.** The mechanism was measured on 44,219
round trips with nothing to fit and its sign is the reverse of the story; the grid then priced both
signs at two lengths and neither reaches the pre-registered bar. The durable lesson is the one A-9
taught in a different shape: **a single session's worst pattern is not evidence about the
population.** The day that motivated this item was a 4,841-trip category that earns +$15 a trip.

**Next.** The sleeve's loss is 98% first entries, so no re-entry rule can reach it - that is the
last signal-layer idea the 2026-09-10 session suggested, and it is closed. A-5 part 2 stays the
standing per-session job (~6-7 more sessions of fills to resolve `SLIPPAGE_BPS` against its 2.52
bps breakeven at two standard errors), and the binding constraint is unchanged: the three open
owner questions in `BLOCKERS.md`, to which this iteration adds a fourth, small one - live alerting
is dead for want of a channel the loop may not configure itself.

## Paper session 2026-09-10

Operations only, no research. Account DUT091359, NAV 989,100.58 at the 09:25 ET intraday start,
**977,119.53** at 15:50 ET (**-11,981, -1.21%** on the day across both sleeves).

| Sleeve | Trades | P&L (net) | Costs | Worst event |
|---|---|---|---|---|
| Intraday `active` (ORB, equity_frac 0.5) | 32 | **-6,778.79** | 91.97 commission | SOXL -2,782 and SOXS -2,409: a whipsaw in semis cost -5,191, 77% of the day's loss |
| Daily `s1_momo` (15:45 rebalance) | 3 | mark-to-market only; book unrealised **-14,727.12** | included in fills | TQQQ -6,999 unrealised, filled 2.20 below the 71.55 plan reference price |

**Intraday.** Started 09:25 ET, flat by 13:30 ET (ORB exits) and confirmed flat at the 15:42
`end` event: `positions: {}`, matching `live/state/intraday_book.json` (`pos: {}`). No
`loss_limit`, `halt` or `error` events. Equity curve by snapshot: -252 at 10:00, -3,925 at 10:30,
-6,336 at 13:00, -6,779 final — a one-way drift, not a single blow-up. Peak gross 818,518 at
11:30. **Step 4 not run: the book was already flat, so no `--flatten` was needed.**

**Daily rebalance, 15:45 ET.** Plan `s1_momo` as-of 2026-09-09, regime risk-on (vol 0.084 vs
median 0.127), targets XLE 0.5873 / XLK 0.4402 / TQQQ 0.2363 on net_liq 977,489.04, gross weight
1.2637, effective exposure 1.7363. Three market orders sent, all filled:

| Symbol | Action | Qty | Ref price | Fill |
|---|---|---|---|---|
| TQQQ | SELL | 473 | 71.55 | 69.35 |
| XLE | BUY | 1,456 | 65.31 | 65.09 |
| XLK | SELL | 326 | 187.87 | 185.45 |

Closing book: XLE 8,789 / XLK 2,290 / TQQQ 3,227, gross 1,220,496.93, cash -243,807.80.

**Two non-fatal defects.** (1) `notify_failed: no live/alerts.json` fired 15 times in the
intraday log and once in the daily log — alerting is silently dead and every alert today was
dropped. (2) `feed_probe: ib_delay_minutes 1045` again: IBKR is serving delayed quotes to the
paper account, so all intraday marks come from the minute-history path, not the live feed.
Also six `connect_failed` events against port 4002 between 06:19 and 06:45 ET before the gateway
came up; the 15:45 run connected fine.

**The semis whipsaw, in fills.** The sleeve trades SOXL and SOXS as one directional pair and was
stopped out twice in the same direction of error. Short semis at 09:52 ET (SOXL -520 @ 114.12,
SOXS +1,254 @ 47.29), out at 10:25 into a rally (SOXL @ 117.50, SOXS @ 46.11). It then flipped
long at 10:36 (SOXL +482 @ 118.15, SOXS -1,244 @ 45.89) and exited at 12:35 into the fade
(SOXL @ 116.02, SOXS @ 46.64). Two ORB entries, both on the wrong side of the same reversal —
this is a signal cost, not an execution defect.

**Next.** Fix `live/alerts.json` so the notifier stops swallowing alerts, and check whether the
ORB re-entry rule should be blocked after a same-symbol stop-out reverses direction inside an hour.

## 2026-09-10 - O-2: SPY 0DTE credit spreads - the first candidate with real gross, refused on the one assumption that makes it pay

- **What.** The last item on the owner's 3-10%/day list, and the only one that had never been
  measured: sell a same-day-expiry SPY vertical credit spread and price every fill at the quoted
  bid/ask. New `scripts/odte_data.py` built a 0DTE chain store from the Theta Terminal -
  **1,884 expirations, 2016-01-08 .. 2026-09-10, 5-minute bid/ask for both rights, +/-30 strikes,
  ~17.8M quote rows, 125 MB** - and new `scripts/sweep_o2.py` runs the study while
  `scripts/_o2_confirm.py` attacks the result. Sixteen ledger rows under `options/odte_put_spread`.
- **Why it needed no owner action to start.** The backlog carried O-2 as blocked on IBKR options
  permission. Permission blocks *deployment*, not research: Theta's STANDARD plan already serves
  every quote the study needs. Nothing here is deployable and nothing was deployed.

### Method, fixed before the runs

One session = one 0DTE expiration. The underlying is recovered by **put-call parity** (0DTE, so
carry is negligible) and the risk-neutral probability of finishing in the money is read off the
chain's own slope - `dP/dK` for puts, `-dC/dK` for calls - so strike selection uses no volatility
model and no external data. Short strike = the strike whose prob-ITM is closest to the target;
long strike = a fixed percentage of spot further out, snapped to the grid. **Entry sells the short
leg at the bid and buys the long leg at the ask; exit buys at the ask and sells at the bid. The mid
is a diagnostic and never a fill.** Commission $0.75 per contract per transaction. The decision
statistic is **return on risk** - P&L over the position's own maximum loss - so 2016 and 2026 are
comparable and a book that risks `risk_frac` of equity earns `risk_frac x ror`. Verdict rule, also
fixed in advance: **net positive at t > 2 in at least two of the three a-priori regimes.**

### The instrument was proved before its verdict was believed

`sweep_o2.py --audit` asks whether the chain's own slope is a calibrated probability. Over
1,749-1,890 sessions per cell, quoted against realized:

| side | quoted prob | realized breach | z |
| --- | --- | --- | --- |
| put 0.05 | 0.049 | 0.033 | -3.14 |
| put 0.10 | 0.098 | 0.080 | -2.68 |
| put 0.16 | 0.157 | 0.131 | -3.04 |
| put 0.25 | 0.247 | 0.220 | -2.72 |
| call 0.10 | 0.096 | 0.070 | -3.81 |
| call 0.16 | 0.155 | 0.125 | -3.65 |

Realized tracks quoted at every delta and on both rights - which proves the parity spot and the
slope - and sits **consistently below** it. That gap *is* the variance risk premium, measured
directly rather than assumed, and it is why this study's gross is positive where O-1, L-1 and X-1
had none.

### Stage 1: the pre-registered grid is a clean negative

36 cells (put / call / condor x 0.10 / 0.16 / 0.25 delta x 10:00 / 12:00 entry x stop 2x / none),
0.75% wide, closed at the quote at 15:50: **0 of 36 pass, every cell negative in every regime.**
The decomposition of the widest-sample cell says why - percentages are of the position's own risk,
per session:

| regime | n | gross | spread | commission | net | cover |
| --- | --- | --- | --- | --- | --- | --- |
| 2016-2019 | 480 | +0.547 | -1.732 | -1.402 | **-2.588** | 0.17 |
| 2020-2023 | 735 | +1.001 | -1.343 | -0.941 | **-1.282** | 0.44 |
| 2024-2026 | 674 | +0.713 | -1.122 | -0.639 | **-1.047** | 0.41 |
| **all** | **1,889** | **+0.783** | **-1.363** | **-0.950** | **-1.530** | **0.34** |

**The mid-price edge is a third of the cost of harvesting it**, and on a $355 risk unit the
commission alone is bigger than the entire gross. Making the trade as cheap as the data allows -
72 cells over width 0.75-5%, entry 10:00-14:00, with and without commission - the best net is
**+0.30% of risk at t = +0.94, and that is at zero commission**; with IBKR's fee the best
full-coverage cell is **-0.006%**.

### Stage 2: the exit convention is worth more than every parameter in the study

Closing a spread at the quote pays the spread twice. A real 0DTE book does not do that - it lets an
untouched position expire. Modelling exactly that (expire free only when nothing is in the money at
the bell, buy back at the quote otherwise) **flips the sign**, and the response to entry time is a
monotone shelf rather than a spike:

| entry | net % of risk | t | 2016-19 | 2020-23 | 2024-26 | win % | expired % | credit/width |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:35 | +0.090 | +0.19 | -1.099 | +0.604 | +0.379 | 80.0 | 78.0 | 0.074 |
| 11:00 | +0.437 | +1.12 | -0.808 | +1.005 | +0.703 | 80.3 | 78.7 | 0.062 |
| 12:00 | +0.685 | +2.09 | +0.349 | +0.899 | +0.691 | 80.4 | 79.4 | 0.055 |
| 13:30 | +0.851 | +3.16 | +0.514 | +0.924 | +1.008 | 82.4 | 82.1 | 0.046 |
| **14:00** | **+0.767** | **+3.05** | +0.268 | **+1.071** | **+0.786** | 82.5 | 82.4 | 0.042 |
| 14:30 | +0.907 | +4.32 | +0.125 | +1.269 | +1.064 | 82.1 | 82.6 | 0.038 |
| 15:30 | +0.684 | +5.20 | +0.311 | +0.883 | +0.721 | 83.8 | 86.0 | 0.025 |

Three of 36 exit-variant cells pass the pre-registered rule, all of them late-entry and
expire-at-the-bell; the same cells closed at the quote earn **-0.282%, t = -1.16, positive in
3 of 11 years** against the expire version's **+0.767%, t = +3.05, positive in 10 of 11 years**
(only 2018 negative). **The entire result is the exit.**

### And the exit assumption does not survive contact with settlement

SPY options settle on the official 16:00 print and can be exercised against until 17:30 ET, so a
position that is barely out of the money at the last quote is not a free expiry. Charging the
quoted spread whenever the close fails to clear the short strike by a buffer:

| buffer (of spot) | net % of risk | t | 2016-19 | 2020-23 | 2024-26 | regimes passing | expired % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.00% | +0.767 | +3.05 | +0.268 | +1.071 | +0.786 | 2 | 82.4 |
| 0.05% | +0.583 | +2.32 | +0.090 | +0.914 | +0.567 | 1 | 77.2 |
| 0.10% | +0.445 | +1.78 | -0.052 | +0.776 | +0.433 | **0** | 71.4 |
| 0.20% | +0.202 | +0.81 | -0.332 | +0.548 | +0.200 | 0 | 55.3 |
| 0.50% | -0.116 | -0.47 | -0.710 | +0.240 | -0.087 | 0 | 21.0 |

**The whole edge lives in the last few cents around the short strike at the bell.** The pin
distribution is the reason: the median session closes **0.28% of spot** from the short strike,
p25 = 0.14%, p10 = 0.06%, p5 = 0.03%, and **37.4% of sessions close within 0.2% of it**, 509 of
those 700 booked as free expiries. At **0.10% of spot - about 65 cents on today's SPY - the result
fails the pre-registered rule outright**, and 0.10% is a *generous* reading of when a desk would
stop paying to close.

### The mandate arithmetic, which refuses it a second time

Even taking the un-buffered +0.767% at face value, on ~175 0DTE sessions a year:

| equity at risk per session | mean %/day | sd %/day | worst day | 1st pct day | simple %/yr |
| --- | --- | --- | --- | --- | --- |
| 0.10 | +0.077 | 1.09 | -10.5% | -4.7% | +19.3% |
| 0.25 | +0.192 | 2.72 | -26.3% | -11.8% | +48.3% |
| 0.50 | +0.383 | 5.44 | -52.6% | -23.6% | +96.6% |
| 1.00 | +0.767 | 10.87 | **-105.2%** | -47.3% | +193.3% |

**A 3%/day book needs 3.9x equity at risk every session, and a defined-risk position posts its risk
in full as margin - so the ceiling is 1.0x and the mandate is unreachable by a factor of four.**
At 1.0x the worst session is ruin; at the 0.25x that keeps a bad day survivable the ledger row
scores CAR 21.5% at a **60.6% drawdown**, far outside the owner's 35% cap. (The worst day exceeds
100% of nominal risk because closing a breached vertical at the quote costs more than the width -
itself a real cost this study charges and most write-ups do not.)

- **Decision: refused, nothing shipped.** No file the live trader or the daily runner loads was
  touched, `live/` and the scheduled tasks were not opened, and the champion is unchanged at S-12.
  Rule (a) owes no replay: only new scripts were added.
- **Do not re-open O-2 as a delta, width, entry-time, structure or stop question.** The grid spans
  all five and the negative is decided one level above them, by the exit: at the quote the trade
  loses in 8 of 11 years, and the version that wins depends on a settlement convention this data
  cannot price. What *would* re-open it is different data - OPRA quotes through the close and a
  measured settlement print - which is an owner purchase, not a loop decision.
- **What is worth keeping.** The variance risk premium is real, calibrated and measurable
  (z = -2.7 to -3.8 across six delta-right cells), and it is the **first gross edge in this
  repository that survives crossing the bid/ask on entry**. Its size is ~0.8% of risk per session
  and the cost of harvesting it is 2.3%; the gap closes only by not paying the exit. That is a
  genuine finding about where an options sleeve could live, and a genuine reason not to fund one yet.

### A-5 part 2, the standing per-session job

First full paper session with intraday fills. **32 fills, $1,873,486 traded, 100% fill rate:
realized slippage +2.92 bps notional-weighted (se 1.32) against the shipped 1.50 - |diff|/se =
1.08, still inside two standard errors, so `SLIPPAGE_BPS` was not touched.** The direction matters:
the measurement has moved from +1.30 on yesterday's partial session to +2.92, i.e. **above A-5
part 1's 2.52 bps breakeven**, and if it holds the intraday sleeve's cost model is worse than
shipped rather than better. Power line: **215 fills, ~6.7 sessions** at this rate to resolve the
constant against breakeven at 2 se. Per-fill sd is 7.48 bps and the close-to-open gap is
-0.30 / sd 2.16, so the reference is still not what costs precision. Worst names SOXL +6.17,
COIN +8.63, MSTR +5.37 bps; PLTR is negative at -6.28.

- **Next.** The owner's 3-10%/day list is now **exhausted**: O-1, O-1b, L-1, X-1 and O-2 have each
  been measured on the full history and each refused. Nothing in this repository reaches the
  mandate, and the only edge that survives out of sample is the daily champion. The loop's
  remaining honest work is A-5 part 2 (about six more sessions settles the intraday sleeve's sign)
  and the open owner questions in `BLOCKERS.md`, one of which - the drawdown cap - is now the
  binding constraint on every candidate the mandate asks for.

## 2026-09-10 - X-1: fifty megacaps, eleven years, and an intraday cross-sectional edge worth a fourteenth of its own cost

- **What.** The last item on the owner's midday list that needs no options permission: rank the 50
  US megacaps every 30 minutes by intraday return against the basket, hold the top decile long and
  the bottom decile short, flat by 15:38. Fetched the 40 names the store lacked from Alpaca
  (**2016-01-04 .. 2026-09-10, ~1.04M regular-hours bars each**; the store is now 60 symbols, 357 MB
  -> 1.1 GB), re-derived every split factor, wrote `algorithms/intraday/xsect/signal.py` and
  `scripts/sweep_x1.py`, and judged it on A-10's three a-priori regimes.
- **Why breadth was worth one more iteration.** A-10 measured the deployed 16-name sleeve at
  -$697/day on 2,686 sessions and O-1/A-9/L-1 each refused a lever on it; the one structural
  criticism those results do not answer is that a 16-name book has no cross-section. A ranking
  strategy is also the only candidate on the owner's list that is dollar-neutral by construction,
  so it is the one whose P&L is not a disguised market bet.
- **Method: L-1's two stages, and L-1's weighting.** Stage 1 is a cost-free event study on the raw
  bars - at each rebalance minute the cross-section is demeaned, the top and bottom `k` are entered
  at the **next bar's open** (the harness's fill convention) and unwound `h` bars later at that
  bar's open, each leg scored **relative to the equal-weight basket** over the same window. The
  decision statistic is the **per-session sum** of leg returns, never the session-equal average that
  inverted L-1's verdict; both are printed. (For this study the two agree to 0.01 bps and
  `corr(legs/session, session mean gross) = +0.006, t = +0.32` - the L-1 pathology is specific to a
  strategy whose signal count varies with the tape, and a fixed-`k` ranking is not one.) Demeaning
  is exact bookkeeping rather than a choice here: with `k` longs and `k` shorts the basket term
  cancels out of the session sum identically.

### Stage 1: the effect is real, tiny, and the wrong order of magnitude

Sixteen parameter cells (lookback 15/30/60 minutes and since-the-open, hold 30/60 bars, k = 5/10),
2016-2026, **2,684 sessions and 267,000-587,000 legs per cell**:

| lookback | hold | k | legs | gross bps | t | cost bps | net bps | t net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| since open | 60 | 5 | 267,230 | **+0.36** | +2.00 | 4.70 | -4.34 | -23.9 |
| since open | 60 | 10 | 533,380 | +0.26 | +1.93 | 4.52 | -4.26 | -31.6 |
| since open | 30 | 5 | 294,060 | +0.19 | +1.96 | 4.70 | -4.51 | -45.6 |
| 30 min | 30 | 5 | 294,040 | +0.03 | +0.35 | 4.66 | -4.63 | -46.1 |
| 60 min | 60 | 10 | 479,760 | +0.14 | +1.09 | 4.51 | -4.37 | -35.0 |

**Gross is positive - momentum, not reversal - and it is 0.36 bps against a 4.70 bps round trip.**
The whole eleven-year edge is **7.7% of the cost of harvesting it**; the book would need a **13x**
larger spread to break even. Per regime the same cell is +0.35 / +0.27 / +0.51 bps (t = +1.44 /
+0.83 / +1.34): stable in sign, never significant on its own, and the pooled t of +2.00 is what
2,684 sessions buy. **No cell reaches t > 2 in two of three regimes on either sign - and that is
before costs**; net of costs the verdict is 0 of 32.

Two secondary readings, both consistent with the main one:

| entry | 10:00 | 10:30 | 11:00 | 13:00 | 14:00 | 14:30 | 15:00 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gross bps | +0.25 | **+0.63** | +0.48 | +0.35 | -0.26 | **-0.69** | -0.19 |
| t | +0.48 | +1.46 | +1.30 | +1.39 | -1.02 | **-2.80** | -0.70 |

Continuation in the morning, mean reversion in the afternoon, and the only |t| > 2 in the table is
the 14:30 **reversal** - a shape worth remembering, and still an order of magnitude under cost at
every hour. And the cost falls monotonically across the regimes (5.45 -> 4.42 -> 4.00 bps per round
trip) purely because the megacaps' share prices rose against a fixed per-share commission, which is
the only reason the net numbers improve at all.

### Stage 2: the harness agrees, and it agrees on both signs at once

`algorithms/intraday/xsect/signal.py` through the shipped framework (defaults: lookback 30, hold to
the next 30-minute re-rank, k = 5, 0.06 of equity per leg, 0.6 gross), **one year per regime**
(2018, 2022, 2025 - a full 11-year pass is ~45 minutes of wall clock per year at 50 names and buys
nothing stage 1 has not already settled):

| variant | $/day | t | Sharpe | 2016-19 | 2020-23 | 2024-26 | tr/day | costs/day |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| momentum | **-1,681** | **-16.9** | -10.2 | t -13.5 | t -9.4 | t -7.8 | 158.9 | $1,760 |
| reversal (control) | **-1,786** | **-18.8** | -11.2 | t -15.8 | t -9.1 | t -9.7 | 158.8 | $1,689 |

0/3 regimes for both signs, against the 2/3-at-t>2 rule fixed before the runs. **The two signs
losing the same amount is the whole result**: back out the modelled costs and the implied gross is
**+$79/day for momentum and -$97/day for reversal** on a $1M book - zero to within a few dollars a
day, in both directions, exactly as stage 1 said. Turnover is 8.07x equity per day, so the sleeve
pays $1,760/day for the privilege; the compounding of that bleed, not any drawdown of the signal, is
what makes the eleven-year equity curve read -80%.
- **The reconciliation is arithmetic, not luck.** Stage 1's cell for the module's own defaults
  (lookback 30, hold 30, k = 5) is +0.03 bps per leg on 109.6 legs/day, i.e. **+$20/day** at 0.06 of
  equity per leg; the harness's implied gross is +$79/day on the three sampled years. The two
  instruments are measuring the same nothing, so no audit of the harness was owed this time (L-1
  needed `_l1_reconcile.py` because they disagreed in *sign*).
- **On the mandate.** Daily P&L standard deviation is **$2,730 on $1M, 0.27% of equity**. Even
  levered to the framework's 1.5 gross cap this book moves a quarter of one percent on a typical
  day, so it was never a 3-10%/day candidate: a market-neutral ranking is the *least* volatile thing
  the owner's list contained, and its edge is smaller still.
- **Decision. X-1 is refused and closed.** Nothing shipped. `live/intraday_config.json`,
  `live/APPROVED_PAPER.md` and the scheduled tasks were not touched, and no file the live trader
  loads was edited - `algorithms/intraday/xsect/` is a new directory that only `scripts/sweep_x1.py`
  imports, so **rule (a) owes no replay** (the deployed `active` module, `base.py` and
  `intraday_common.py` are byte-identical to this morning's).
- **What did ship is data.** `data/minute_alpaca` now holds **60 symbols** (the 16-name sleeve, the
  six leveraged ETFs, and all 50 megacaps, 2016-2026, ~1.04M bars each), and `_splits.json` was
  re-derived for all 60 in one pass. That file is rewritten wholesale by `alpaca_data.py --splits`,
  so it had to be re-derived for the *union*, not the new names - **every pre-existing factor came
  back identical**, so A-10's and L-1's costed results are unaffected. The store is gitignored;
  rebuild with `python scripts/alpaca_data.py --symbols <names> --start 2016-01-01` (~4 min/symbol,
  three parallel processes stay inside Alpaca's 200 requests/minute).
- **Next.** The owner's list is now exhausted except **O-2**, which needs options permission on the
  paper account (open question in `BLOCKERS.md`), and the A-track refinements. Three of the four
  ideas that were supposed to deliver 3-10%/day have now been measured and refused on ten years of
  bars - O-1 (no forecastable regime), L-1 (no reversion in leveraged ETFs), X-1 (no cross-sectional
  spread) - and the honest summary for the owner is that **this repo has found exactly one edge that
  survives out of sample, and it is the daily champion S-12**. The next iteration should either take
  O-2 (options, which is the only untried instrument class with intrinsic convexity) or answer the
  standing question in `BLOCKERS.md` about whether the intraday sleeve should keep trading paper
  capital at all. **A-5 part 2 is still owed today**: the sleeve trades until 15:42 ET, so
  `python scripts/slippage_report.py --refresh` runs after the close, not inside this iteration.

## 2026-09-10 - L-1: leveraged ETFs do not revert intraday, and the statistic that said they did was weighted wrong

- **What.** The owner's midday mandate put L-1 at the top of the backlog: fade VWAP bands on the
  3x index ETFs, where the daily-reset construction and dealer hedging are supposed to push price
  away from fair value and back. Fetched the missing half of that universe from Alpaca
  (TQQQ, SQQQ, UPRO, SPXU: **2016-01-04 .. 2026-09-10, ~1.03-1.04M regular-hours bars each**,
  joining SOXL/SOXS), wrote `algorithms/intraday/lev_revert/signal.py` and `scripts/sweep_l1.py`,
  and judged it on the same three a-priori regimes A-10 uses.
- **Why in two stages.** Every A-track false positive came from fitting a strategy on one window
  and reading its P&L, so the mechanism is measured first with no strategy and nothing to fit:
  an **event study** on the raw bars. Whenever the deviation from session VWAP exceeds `z` of the
  name's own 14-bar ATR, buy the cheap side at the *next* bar's open - the harness's own fill
  convention - and unwind `h` bars later at that bar's open. Only a cell that clears cost earns a
  strategy run.

### The result: refused, in both instruments, in all three regimes

| | gross bps/round trip | cost bps | net bps | t (net) |
| --- | --- | --- | --- | --- |
| z >= 3, hold 5 (540,740 events) | **-0.28** | 7.32 | -7.60 | -62.1 |
| z >= 5, hold 30 (93,373) | **-1.79** | 7.14 | -8.94 | -15.5 |
| z >= 8, hold 30 (55,454) | **-1.18** | 6.83 | -8.01 | -11.6 |
| z >= 12, hold 30 (26,552) | **-1.68** | 6.46 | -8.15 | -9.7 |
| z >= 12, hold 60 (14,495) | **-3.16** | 6.47 | -9.63 | -6.1 |

**Gross is negative in all sixteen cells and for all six names**, before a cent of cost: a stretched
3x ETF drifts a little further, it does not come back. The drift is small (-0.04 to -3.30 bps) and
only reaches |t| ~ 3 at the loose thresholds, so the honest statement is that there is no
tradeable deviation in either direction - which the harness confirms by losing on the inverted
control too. **Stage 2, the module through the shipped framework, 2,686 sessions:**

| variant | $/day | t | Sharpe | 2016-19 | 2020-23 | 2024-26 | tr/day | costs/day |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fade, 6 names | **-902** | **-9.45** | -2.93 | t -7.09 | t -6.20 | t -3.42 | 17.5 | $738 |
| fade, 3 deployable names | -667 | -9.02 | -2.77 | t -6.81 | t -6.12 | t -3.25 | 10.6 | $542 |
| continuation control | -587 | -6.26 | -1.96 | t -5.93 | t -2.57 | t -3.32 | 17.6 | $787 |

0/3 regimes for every variant, against a rule of 2/3 at t > 2 fixed before the runs.

### The finding worth keeping: the aggregation chose the sign

Stage 1 originally **passed 3/3 regimes at +7.09 bps net, t = +6.56**. That number came from
averaging the events inside a session and then averaging the sessions - one vote per session. A
book does not do that: it puts the same notional on every event, so a session earns the **sum**,
not the average, and the money-weighted statistic is **-1.68 bps**. The two disagree by 15 bps and
in sign because the fade's payoff is inversely proportional to how much of it there is:

| sessions ranked by signal count (z >= 12, hold 30) | events/session | gross bps/event |
| --- | --- | --- |
| Q1 fewest | 2.4 | **+37.94** |
| Q2 | 6.9 | +16.37 |
| Q3 | 12.5 | +3.40 |
| Q4 most | 25.5 | **-10.60** |

`corr(events/session, session mean gross) = -0.340 at t = -17.5` (z >= 8: **-0.412 at t = -23.4**,
monotone in every quartile). On a quiet tape two stretches appear and both revert; on a violent
tape twenty-five appear, the book is fully deployed in all of them, and they run. **A per-event
average over sessions is not an estimate of what a strategy earns unless the strategy trades one
event per session**, and this repo now has a cell where that distinction is worth 15 bps and a
verdict. `sweep_l1.py` prints the session-equal number as a labelled diagnostic and decides on the
P&L-weighted one.
- **The harness was audited before it was believed.** When stage 1 and stage 2 disagreed in sign
  the first suspect was the backtester, so `scripts/_l1_reconcile.py` pairs the harness's own
  trade log into round trips and matches them to the event study entry by entry on 2023 Q1:
  **235 matched entries, event +1.12 bps vs harness +1.12 bps, corr 1.000, zero disagreements
  above 1 bp.** The two instruments agree per fill; only the weighting differed.
- **Cost is the second wall, and it is structural on this universe.** A round trip costs
  **6.4-8.2 bps** here against ~3.8 on the megacap sleeve, because the inverse ETFs trade at
  \$20-26 and IBKR charges per *share*: SOXS pays **13.58 bps** a round trip, SPXU 9.12, SQQQ 9.08,
  against TQQQ's 4.85 and UPRO's 4.79. A mechanism worth +/-1-3 bps cannot pay a 7 bps toll no
  matter which way it points, and the continuation control losing $587/day is that sentence
  measured.
- **Secondary observation, not the reason it loses.** In the reconciliation window 17 of 433 round
  trips exited early - the 2.5% daily loss limit or the 15:38 flatten - and those averaged **-93
  to -129 bps** against the full-length trades' -6.2. A loss limit truncates a fade at exactly the
  moment the fade is claiming to be right, so a mean-reverting sleeve would have to price that
  interaction. Irrelevant here, because gross is negative with or without them.
- **Decision. L-1 is refused and closed.** Nothing shipped. `live/intraday_config.json`,
  `live/APPROVED_PAPER.md` and the scheduled tasks were not touched; `algorithms/intraday/active/`
  is unchanged, so the live trader loads exactly the code it loaded this morning. The only shared
  file edited is `scripts/intraday_common.py`, which gains two module-level constants
  (`LEVERAGED_UNIVERSE`, `LEVERAGED_DEPLOYABLE`) and no behaviour; the 2026-09-08 replay was run
  anyway and reproduces the deployed sleeve exactly (see below). Two of the six names (TQQQ, UPRO)
  are the daily champion's own instruments, so only `LEVERAGED_DEPLOYABLE` could ever have been
  traded - the study carried all six so that "does leverage revert" was not confounded with "which
  leg was available", and the answer is the same on both sets.
- **On the mandate.** Even the passing version of this was never going to deliver 3-10% days: the
  book's daily P&L standard deviation is **0.49% of equity** at 0.9 gross on 3x ETFs, because the
  fade holds offsetting stretches for thirty minutes at a time. Leveraged instruments supply the
  *volatility*; they do not supply the *edge*, and a sleeve with no edge sized up to move 5% a day
  loses 5% a day just as often.
- **Next.** X-1, cross-sectional intraday momentum on the 50 megacaps - the last untried item on
  the owner's list that does not need options permission, and the only one whose premise (breadth,
  a market-neutral ranking) is not already refuted by an A-track measurement. Fetch the D-1 megacap
  list into `data/minute_alpaca` and judge it the same way: event study first, money-weighted, then
  the harness, three regimes, 2/3 at t > 2.

## 2026-09-10 - A-5 part 2: the first live fills say nothing about slippage and prove a missing cost

- **What.** The intraday sleeve placed real orders for the first time this morning, so A-5 part 2
  finally had an input. Ran `scripts/slippage_report.py` on the live log, read the fills against
  IBKR's own `commissionReport`, and re-baselined the harness against the 260-session store.
- **Why.** `SLIPPAGE_BPS = 1.5` is the only guessed number in the intraday harness and A-5 part 1
  showed the sleeve's sign is a property of it (breakeven 2.62-2.64 bps, P&L linear at $546/day
  per bp). Bars cannot pin it - every 1-minute spread estimator turned out to be measuring
  volatility - so only live fills can.

### The slippage measurement: not yet an answer, and now a dated one

Partial session, 19 orders / 19 fills at 12:0x ET (the sleeve trades until 15:42), $1,108,469
traded, fill rate 100%:

| | value |
| --- | --- |
| realized slippage, notional-weighted | **+1.30 bps** (se 1.65) |
| unweighted / median | +1.26 / +2.28 |
| shipped `SLIPPAGE_BPS` | +1.50 |
| \|measured - shipped\| / se | **0.12** |
| fill latency past the model | median **10 s**, worst 13 s |

**Not distinguishable, so nothing moved.** `SLIPPAGE_BPS` stays 1.5, which is what the rule
requires and what the script refuses to do by itself.

**The reference is not the problem, and the obvious model said it would be.** The store has no
bars for a session in progress, so at 11:04 all 17 fills were priced against the decision bar's
close instead of the next bar's open. The whole-store close-to-next-open gap has sd **6.20 bps**
on this symbol mix (SOXS alone 14.04), which predicts that the fallback carries 76% of the
variance and that refreshing the store would cut the sample needed from ~162 fills to ~39. **The
store caught up mid-session and refuted it directly.** Pricing the *same 17 fills* both ways:

| reference | wmean | median | per-fill sd | wse |
| --- | --- | --- | --- | --- |
| decision close (fallback) | +1.55 | -0.01 | **7.13** | 1.73 |
| next-bar open (what the backtester uses) | +1.10 | +2.28 | **7.55** | 1.83 |

The realized gap on those fills was mean -0.30 bps, sd **2.16**, and it correlates **-0.33** with
the fill error - so the fallback is very slightly *quieter*, not noisier. A population noise
estimate does not transfer to the minutes a strategy selects; the sleeve trades the liquid first
hour, not the average minute. **What is expensive is the ~10 seconds of detection latency**, and
that drift is mean-zero, so only fills buy precision: **166 fills, ~3-4 full sessions at A-5's
49 trades/day**, to resolve the shipped constant against breakeven at 2 standard errors.

### The finding that did land: the harness never charged the sell-side regulatory fees

IBKR's `commissionReport` matched `intraday_common.commission()` to **$0.004 on all twelve buys**
and undercharged **every one of the five sells**. Fitting the excess jointly on notional and share
count reproduces all five **exactly, to the cent** (residuals 0.000), which makes these posted
rates rather than estimates:

- **SEC Section 31 fee $20.60 per $1,000,000 of sell proceeds** (0.206 bps), sells only;
- **FINRA TAF $0.000198 per share**, sells only, capped $8.30.

Notional-weighted commission on the session: **0.501 bps actual against 0.434 modelled**; with the
fix, 0.501 modelled and every one of the 17 fills reproduced to rounding.

### What it costs, on the 260-session store, paired

Same parameters as A-5's control (`orb` 1.0 + `late_momo` 1.0, `per_symbol` 0.15, `gross` 1.5,
`disaster_atr` 4.0), 2025-08-26..2026-09-08:

| | trades | turnover/day | costs/day | $/day | CAR | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pre-fix (A-5's control) | 12,743 | 5.46x | $1,025 | **$610** | 15.3% | 0.689 | 14.39% |
| **with the fees charged** | 12,742 | 5.43x | **$1,078** | **$557** | **14.0%** | **0.640** | 14.67% |

**$53/day, 5.2% of the sleeve's modelled cost, 1.3 points of annualized return and 0.05 of
Sharpe.** The one-trade / 0.03x turnover difference is the cost feeding back into equity and
therefore sizing; decisions are otherwise identical. **The breakeven moves with it**: at $546/day
per bp the control's $557/day now runs out **1.02 bps above the shipped constant, so breakeven is
2.52 bps, not 2.62** - still well above 1.5, so this changes no verdict, only the target the
measurement has to reach. Scaled to the deployed half-size sleeve the fees are ~$22/day, so the
2,686-session Alpaca result moves from -$697/day to roughly -$740/day. Every one of these numbers
moves against the sleeve, which is the direction an omitted cost always moves.

- **Rule (a) replay, run twice because the trader changed under this iteration.** 2026-09-08 with
  the deployed config, against the trader as it stands after `9bb492a`: old model **P&L -2,280,
  34 trades, 368 decisions, costs 375, flat at close** - reproducing the A-10/O-1 journal to the
  digit - and new model **-2,302, 34 trades, 368 decisions, costs 397, flat at close**. Identical
  decisions and identical trades; the entire difference is the $22 of measured fees.
- **A no-op proved for free.** The old-model control reproduces A-5's recorded ledger row to every
  digit (12,743 / 15.867% / 15.343% / 0.689 / 14.390% / 49.0 / $610 / $1,025 / -28,368 / 12 / 260).
  That run went through the participation-cap code path an earlier interrupted session left
  uncommitted in `intraday_backtest.py`, so **A-11's `part_cap = 0.0` default is bit-for-bit
  inert**, as its author claimed but had not shown. It is committed here on that evidence; A-11
  itself is still unrun.
- **Decision.** Shipped the commission fix and the instrument work; refused to touch
  `SLIPPAGE_BPS`, `live/intraday_config.json`, `live/APPROVED_PAPER.md` or any scheduled task.
  `scripts/slippage_report.py` now splits the two references and never pools them, prices every
  fill under both where both exist, reports fill latency, and prints the fills-to-breakeven power
  line; `--refresh` pulls closed sessions into `data/minute` and refuses a session still trading
  (verified: it refused today at 11:09 ET).
- **Next.** Re-run `python scripts/slippage_report.py --refresh` after today's 15:42 close for the
  first complete session, and after every close after that. Note for whoever takes the next
  iteration: the owner's midday mandate (3-10%/day, priority O-1 / L-1 / X-1 / O-2) landed in the
  backlog at 11:40 ET while this was running, and it says every candidate is judged "with real
  costs" - those costs are now $53/day higher per $5.46M/day of turnover than they were this
  morning, so L-1 and X-1 should be judged against the corrected model from their first run.

## 2026-09-10 - O-1b: the implied-vol size dial is a leverage dial, and it pays 50% more turnover for it

- **What.** O-1's deferred half, on the daily champion instead of the intraday sleeve. A size
  multiplier on S-12's funded book, driven by SPY options-implied vol:
  `clip((trailing median IV / prior-day IV) ** iv_scale_power, iv_scale_min, iv_scale_max)`,
  applied to the final weights. `iv_scale_power = 0` is off and is the shipped default.
- **Why.** O-1 refused implied vol as a *gate* but measured a residual that survived every cut it
  tried: corr(SPY ATM IV, |intraday daily P&L|) = **+0.252 at t = +12.67**, positive in all three
  regimes for all three features. Implied vol forecasts how *big* a day will be and not which way.
  That is worthless on a book whose level is negative, and it is exactly what a size dial wants -
  so the only place it could pay is a book whose level is positive. S-12 is that book.
- **Plumbing.** `signals.py` gains `iv_regime_series` / `iv_size_factor` and five `Params` fields,
  `main.py` gains the matching `S1_IV_SCALE_*` overrides, and `scripts/iv_regime.py --export-csv`
  mirrors the parquet to `data/options/iv_regime.csv` because the LEAN-side Python 3.11 has no
  pyarrow. Two things kept honest by construction: the factor reads only store rows dated
  **strictly before** the last price bar, so it is causal under either harness's timestamp
  convention; and it multiplies the weights *after* the margin-budget shrink rather than folding
  into `scale`, because with a flat budget the vol target is already inert upwards (S-8) and a
  dial that can only cut is not a dial.
- **Coverage, stated rather than hidden.** The store runs 2017-01-03..2026-09-09 and the champion's
  sample starts 2012. Uncovered days get factor 1.0, i.e. they run as the champion, so the study is
  judged on the covered period **2017-04-03..2026-09-04** (the start is pushed to April so the
  60-row median window is full on day one). A full-period run would be a blend of a bit-identical
  half and the half measured below, so it can only move the verdict toward the control.

### Every cell, covered period, against its own control

| cell | orders | fees | CAR | Sharpe | MaxDD | ann.std | PSR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| control, dial off | 2,951 | $13,090 | 29.456% | 1.025 | 22.6% | 0.179 | 37.7% |
| power **+1.0** (inverse: cut when a big day is priced) | 4,991 | $19,128 | 27.692% | 0.950 | 21.1% | 0.182 | 29.5% |
| power **-0.5** (direct) | 4,550 | $17,963 | **31.376%** | **1.050** | 23.3% | 0.189 | **40.0%** |
| power **-1.0** (direct) | 4,966 | $21,937 | 31.705% | 1.025 | 24.6% | 0.198 | 36.7% |
| power **-2.0** (direct) | 4,768 | $23,702 | 29.772% | 0.939 | 25.4% | 0.204 | 27.4% |

**The inverse reading - the one the residual actually motivates - is the losing side.** Spending
less when the market prices a big day costs 1.76 points of CAR and 0.075 of Sharpe *while carrying
more vol than the control* (0.182 against 0.179), so it is worse on both axes at once. The side
that wins is the direct one: lever up when implied vol is high. That is not a risk dial, it is the
long-volatility reading A-10 found in the intraday sleeve, arriving on a book that is paid for it.

And the response in `power` is a **pure vol dial**: annualized std walks 0.179 -> 0.189 -> 0.198 ->
0.204 monotonically as the tilt strengthens, CAR peaks at -0.5/-1.0 and rolls over at -2.0, and
Sharpe peaks at -0.5 and then decays. That is the shape leverage plus compounding decay makes, not
the shape information makes.

### The benchmark that settles it: the same gross, with no IV in it

The mean factor is only **1.0198** at power -0.5, so most of the level is unchanged; the dial's
claim has to be about *timing*. Degenerating the clip (`iv_scale_min = iv_scale_max = c`) turns the
same code path into a constant gross-up with the IV timing removed:

| cell | orders | fees | CAR | Sharpe | MaxDD | ann.std | PSR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CONSTANT 1.0198 (matches the dial's mean gross) | 2,973 | $13,588 | 30.022% | 1.030 | 23.0% | 0.183 | 38.0% |
| CONSTANT 1.056 (matches the dial's realized vol) | 3,027 | $14,556 | 31.107% | 1.040 | 23.8% | **0.189** | 38.9% |
| IV dial, power -0.5 | 4,550 | $17,963 | 31.376% | 1.050 | 23.3% | **0.189** | 40.0% |

**At identical realized vol the whole of the dial's edge over a dumb constant gross-up is +0.27
points of CAR and +0.010 of Sharpe, bought with 50% more orders (4,550 vs 3,027) and 23% more
commission ($17,963 vs $14,556).** S-13 measured this harness's own path scatter on a parameter
with no mechanism at roughly +/-0.3 CAR and +/-0.01 Sharpe across neighbouring cells. The dial's
entire measured contribution is one unit of that scatter, and it is charged for.

Two thirds of the raw "gain" is not even timing: constant 1.0198 already earns +0.57 CAR over the
control for a 2% gross-up.

And the constant does not need the dial's code at all. Expressed as the knob the owner actually
sets - `margin_budget` 0.75 -> **0.792**, no IV feed, no new module - the same window gives
**3,039 orders / $14,530 / CAR 31.006% / Sharpe 1.042 / DD 22.8% / std 0.188 / PSR 39.1%**. That is
**+1.55 CAR over the shipped champion for +0.2 points of drawdown and 88 extra orders**, against the
dial's further +0.37 CAR for +0.5 points of drawdown and **1,511** extra orders. The dial is
strictly the worse way to buy the same thing.

- **Decision. Refused; nothing shipped.** `iv_scale_power` stays 0.0, the champion stays S-12, and
  `research/champion.json` is unchanged. The plumbing is kept in the tree defaulted off because it
  is the read path any future options study needs.
- **The no-op is proved, not asserted.** `signals.py` is the module the IBKR paper runner imports,
  so the shipped-defaults run was repeated on the full period: 4,735 orders, CAR 24.404%, Sharpe
  0.921, DD 25.100%, fees $45,695.46, end equity $2,467,638.72 and
  **`OrderListHash 5246804e17a67af90028ffceead7d3b3`** - bit-identical to the champion. The live
  paper path is unchanged and `live/` was not touched.
- **Do not re-open this as a feature or threshold question.** The negative is not that
  `iv_atm_1w` is the wrong field or 60 the wrong window: it is that the only thing implied vol can
  contribute to a *long-only-in-spirit* momentum book is the level of gross, and the level of gross
  is already available for free and without turnover through `margin_budget`. If the owner wants
  the extra 1.6 points of CAR that the covered period shows, the honest instrument is a one-line
  constant, not an options feed - and it is a risk-posture decision, so it goes to `BLOCKERS.md`.
- **Also this iteration: A-5 part 2 had no input.** `python scripts/slippage_report.py` at the top
  of the iteration reports no session on disk with live fills - the only intraday log with orders
  is still absent, and 2026-09-09's is the hand-started dry run. Today's 09:25 ET session (this
  iteration ran at 08:3x ET, before the open) is the first that can produce one, so the measurement
  moves to the post-close run.
- **Next.** After today's close: `scripts/slippage_report.py` for A-5 part 2, which is the only
  measurement that can still move `SLIPPAGE_BPS` and therefore the intraday sleeve's sign. The
  A-track has no untried lever left; O-2 (defined-risk 0DTE options) needs owner permissions.

## 2026-09-10 - O-1: implied vol forecasts the day this sleeve pays for, and pays nothing

- **What.** The last idea on the A-track with a measured mechanism behind it. `scripts/iv_regime.py`
  builds `data/options/iv_regime.parquet` from Theta Data's EOD greeks - **2,383 trading days,
  2017-01-03 .. 2026-09-09**, one row per day: SPY front-weekly ATM implied vol (strike-interpolated
  at the underlying, calls and puts averaged), the 25-delta put/call skew (delta-interpolated), and
  the 1w/1m term ratio. `scripts/sweep_o1.py` then asks whether that forecast separates the days
  the intraday sleeve earns on from the days it pays on, and `algorithms/intraday/orb/signal.py`
  carries the gate itself (`iv_gate` = `high` / `low` / off, default off).
- **Why.** A-10 left exactly one thing standing on a 2,686-session sample: the sleeve's daily P&L
  rides the universe's realized daily range at **corr +0.202, t = +10.70**, positive in all three
  regimes, while the *level* is negative in all three. So the question stopped being "how big" and
  became "when". A-9 had already refused the *opening* range as the handle, for a mechanical
  reason - ORB's stop is the range midpoint, so a wide opening scales the win and the loss
  together. Implied vol is the one candidate that is a **forecast** rather than a realization, and
  it is knowable before the open.
- **Method.** A day gate is all-or-nothing, so it needs no backtest per cell: the instrument is
  A-10's cached per-session P&L series (`results/a10/daily_orb.csv`, fresh $1M book each calendar
  year), partitioned by the gate state. Every cell is therefore a partition of one fixed sample,
  not a new fit. The gate value for session `d` is the **previous** trading day's EOD reading and
  its threshold is the trailing 60-day median of readings strictly before it
  (`iv_regime.load_gate`), so nothing is contemporaneous. Rule fixed before the runs (backlog O-1):
  the gated book must be positive at **t > 2 in at least two of three regimes**, or the feature is
  refused - and a feature that separates but leaves the ON side negative is still a refusal,
  because it would only shrink a losing book.

### The forecast works. The link to P&L does not exist.

| step | measure | ALL (n) | 2016-2019 | 2020-2023 | 2024-2026 |
| --- | --- | --- | --- | --- | --- |
| 1. forecast | corr(prior-day ATM IV, today's universe range) | **+0.598, t +36.4** (2,381) | +0.452 | +0.654 | +0.535 |
| 2. payoff | corr(prior-day ATM IV, today's ORB P&L) | **-0.030, t -1.46** (2,381) | +0.001 | -0.052 | +0.010 |
| 2. control | corr(*realized* range, today's ORB P&L) | **+0.260, t +13.95** (2,686) | +0.316 | +0.228 | +0.357 |

Implied vol predicts the realized range about as well as a daily forecast can - **t = +36** on
2,381 sessions, and it holds separately in every regime. The realized range predicts the P&L at
**t = +14**. And the composition of the two is **zero**. The other two features behave the same
way: `term_ratio` forecasts the range at t = +20.9 and the P&L at t = -0.77, `skew25_1w` at t =
+17.0 and t = **-2.81** - the only feature to reach |t| > 2 against P&L, with the wrong sign.

**The decomposition says why, and it is A-9's finding arriving with a real forecast.** Regressing
today's range on yesterday's IV and correlating the two parts with P&L separately:

| feature | corr(IV-forecast part of range, P&L) | corr(surprise part, P&L) |
| --- | --- | --- |
| iv_atm_1w | -0.030, t -1.46 | **+0.351, t +18.31** |
| term_ratio | -0.016, t -0.77 | **+0.292, t +14.29** |
| skew25_1w | -0.058, t -2.81 | **+0.299, t +15.31** |

and the surprise column is positive at t > 7 in **every feature x every regime**, nine of nine.
So the sleeve is not paid for volatility, it is paid for **volatility surprise** - the range the
day adds beyond what was priced in at yesterday's close. A-9 measured that shape with the opening
range and it could be dismissed as a within-session artefact of the midpoint stop. It is not:
the same shape holds against a genuinely forward-looking, market-priced forecast on ten times the
sample. What pays is, by construction, unknowable at entry.

### The gate, and the verdict

Six cells (three features x two signs), 2,190-2,381 covered sessions each:

| feature | gate | on days | on $/day | t on | off $/day | welch t(on-off) |
| --- | --- | --- | --- | --- | --- | --- |
| term_ratio | low | 1,091 | **+43** | **+0.13** | -491 | +0.97 |
| iv_atm_1w | low | 1,258 | -60 | -0.19 | -373 | +0.56 |
| skew25_1w | low | 1,212 | -142 | -0.40 | -279 | +0.25 |
| skew25_1w | high | 1,149 | -279 | -0.67 | -142 | -0.25 |
| iv_atm_1w | high | 1,104 | -373 | -0.81 | -60 | -0.56 |
| term_ratio | high | 1,080 | -491 | -1.15 | +43 | -0.97 |

**0 of 3 regimes at t > 2, for all six cells. The rule fires.** The best ON side in the whole
sweep is +$43/day at t = +0.13 - zero. The largest separation anywhere is Welch t = 2.26
(`term_ratio low`, 2016-2019, +$636/day against -$702), and it **inverts in 2024-2026** (-$632
against +$551, t = -0.88); `iv_atm_1w low` does the same, +$330/day in 2016-2019 and -$358/day in
2024-2026. That is the A-9 signature again: a lever that selects which part of the sample you are
looking at, not which trades you take.

**One thing survives, and it is not a gate.** corr(IV, |P&L|) is **+0.252 at t = +12.67** and
positive in all three regimes for all three features. Implied vol forecasts **how big the day
will be, not which way** - so it is a size scaler, not a filter. On a book whose level is negative
that is worth nothing on its own (scaling a loser by its own volatility is not an edge), but it is
the honest form of the residual signal, and it is what the deferred half of O-1 asked about for
the *daily* champion, where the level is positive.

### The gate itself works; it is the verdict that is negative

A partition of a cached series is not a backtest, so the `iv_gate` parameter was run through the
real backtester on one calendar year (`scripts/_o1_confirm_2024.py`, three ledger rows, ORB alone,
2024 = the most recent complete year and the least negative regime):

| gate | sessions | traded days | trades | $/day | Sharpe | CAR |
| --- | --- | --- | --- | --- | --- | --- |
| off | 252 | 252 | 10,131 | +524 | 0.62 | +13.20% |
| high | 252 | **118** | 4,850 | +452 | 0.62 | +11.39% |
| low | 252 | **131** | 5,164 | -23 | 0.02 | -0.57% |

The wiring does what the partition assumed: it blocks whole sessions, keeps about half of them,
118 + 131 = 249 rather than 252 because the three sessions the store does not cover **fail closed**,
and off is a no-op. **Read this table as a wiring check, not as evidence.** 2024 is a positive year
for ORB inside a regime that is -$65/day overall, and the side it favours (`high`) is the side the
full 2,381-session partition scores **worst** (-$373/day against -$60 for `low`). One year cannot
adjudicate that, which is the entire reason the verdict is taken on 2,686 sessions and three
regimes instead.

- **Decision. O-1 is refused; nothing shipped to `live/intraday_config.json`.** The gate stays in
  the tree defaulted off, together with the store builder and the sweep, so the negative is
  reproducible. Replay of 2026-09-08 with the deployed config after the ORB edit reproduces the
  A-10 replay exactly - **34 trades, 368 decisions, flat at close, P&L -2,280 on 500k of sleeve
  equity** - so the module change is a no-op for the live path (rule a).
- **`equity_frac` held at 0.5, not cut to 0.** The backlog's objective pre-committed to taking the
  sleeve to zero if O-1 failed, and the numbers alone support it. It is not being done unilaterally
  because the owner already has this exact question open in `BLOCKERS.md` as a three-way choice,
  and the loop's stated default there is (a) *keep it at 0.5 as a live execution experiment*, whose
  entire purpose - **A-5 part 2**, measuring real fill slippage against the 1.5 bps the harness
  assumes - has still never had a single live fill (checked again at the top of this iteration:
  `slippage_report.py` reports no session on disk with orders). Today at 09:25 ET is the first
  session that can produce one, and the breakeven slippage is 2.62 bps against a shipped 1.5, so
  that measurement can still move every number on this track. Cutting to zero this morning ends it
  before it starts. The `BLOCKERS.md` item is updated to say option (b) now has no candidate left.
- **What this closes.** A-10 measured the level: negative at t = -3.01 on 2,686 sessions. O-1
  measured the conditioner: there is none that is knowable at entry, because the regressor that
  pays is a surprise. Between them the A-track's mechanism is fully accounted for, and there is no
  twelfth lever worth pulling on this sleeve. Champion unchanged at S-12; the daily sleeve was not
  touched.
- **Also shipped, in the background (P-1, the broken alert path).** `intraday_common.notify()` and
  `paper_trade.notify()` now write every alert to **`live/log/alerts-<date>.jsonl`**
  (`{ts, event, source, text, delivered, error}`) *before* attempting the chat push, and the push
  is allowed to fail. The 2026-09-09 failure left only a `notify_failed` line inside that day's own
  trading log; a rejected order or a halted sleeve was effectively invisible. It is worse than the
  review found, in fact: `live/alerts.json` does not currently exist on this machine at all, so
  **both** notify paths were silent no-ops, not just the Telegram push. No credentials were
  touched - configuring the channel stays an owner item - but the failure is now recorded instead
  of swallowed, and the daily review reads one file for it. Self-tested from both modules, and
  `compare_orders.py` re-run after the `paper_trade.py` edit still passes 3,689/3,689.
- **Toolchain note that cost time here.** `py -3.11` has no `pyarrow`, so everything that touches
  the parquet stores - the intraday harness, `sweep_o1.py`, and the trader's `--replay` - must run
  on the system `python` (3.14.7). And `--replay` does **not** read `live/intraday_config.json`:
  it takes strategy defaults unless `--params` is passed and `--equity-frac` defaults to 1.0, so a
  naive replay reports 217 trades / -9,914 against the deployed 34 / -2,280 and looks like a
  regression that is not one. Both are now in `MEMORY.md`/`memory/2026-09-10.md`.
- **Next.** A-5 part 2 after today's close - the only open measurement on this track. Then O-1's
  deferred half, the *size scaler*, applied where the level is positive: the daily champion
  (carried as O-1b in the backlog).

## 2026-09-10 - A-10: with 2,686 sessions the sleeve is not unproven, it is negative

- **What.** The power test A-4 said could not be run on any reachable sample. `scripts/sweep_a10.py`
  runs the deployed mix and each sub-strategy alone on the Alpaca SIP store - the same 16 names,
  split-adjusted 1-minute bars, **2016-01-04 .. 2026-09-09, 2,686 sessions** against the IBKR
  store's 260 - as one backtest per calendar year from a fresh $1,000,000 book, then pools the
  daily series into three a-priori regimes. The yearly reset is deliberate: it makes a dollar in
  2016 comparable with a dollar in 2026, which is what a t-statistic on daily P&L needs, and it
  stops eleven years of compounding from letting the last two years own the sample.
- **Why.** A-4 measured Sharpe 0.69 at t = +0.61 and computed that ~2,120 sessions are needed to
  reject zero at two sigma. A-5 sharpened it: on the 77 sessions no A-track parameter had seen,
  gross P&L *before any slippage* was -$11/day. The Alpaca store is the first sample large enough
  to answer, and the decision rule was fixed before the runs (backlog A-10): positive at t > 2 in
  at least two of three regimes, or the size comes down.

### The cost-model bug that had to be fixed first

The Alpaca store is **split-adjusted**, which is right for features and wrong for a per-share
commission. A 2016 share of NVDA is priced at 1/40th of what it traded at, so a dollar position
buys 40x the shares that were really bought - and IBKR charges per share, capped at 1% of trade
value. The uncorrected model charged **$1,523/day of commission on 7 trades/day** in a two-name
2016 smoke test (it was pinned to the 1% cap, i.e. 100 bps a side). Worse, SOXS's cumulative
factor is 8.3e-08, so its adjusted 2016 price is in the tens of millions and the whole-share floor
silently sized every early SOXS position to **zero**.

Fixed in shared code, so the backtester and the live trader cannot drift: `alpaca_data.py --splits`
asks Alpaca for the same daily bars twice, raw and split-adjusted, and writes the ratio as
`data/minute_alpaca/_splits.json` (NVDA 40 -> 10 -> 1, TSLA 15 -> 3 -> 1, SOXS 8.3e-08 through
seven reverse splits - no split table to maintain and nothing to keep up to date by hand);
`intraday_common.share_scale()` reads it; `commission()` takes an optional scale so the per-share
term is charged on real shares while the 1% cap stays on notional; and the whole-share floor is
applied at the price that was really quoted. **The raw IBKR store has no such file, every factor
is 1.0, and the regression proves it is a no-op there**: A-5's control reproduces to the digit -
260 sessions, CAR 15.343%, Sharpe 0.689, $610/day, 12,743 fills, worst day -28,368, 12 loss-limit
days. Same 2016 smoke test after the fix: costs/day $222, not $1,523.

### The result

Deployed framework, shipped costs (1.5 bps + IBKR commission), $1M book, 2,686 sessions:

| variant | regime | sessions | $/day | t | Sharpe | CAR % | max DD % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **mix** | 2016-2019 | 1,006 | **-579** | **-2.42** | -1.18 | -15.0 | 50.0 |
| **mix** | 2020-2023 | 1,006 | **-1,127** | **-2.92** | -1.30 | -30.2 | 77.2 |
| **mix** | 2024-2026 | 674 | -231 | -0.37 | -0.24 | -9.1 | 52.5 |
| **mix** | ALL | 2,686 | **-697** | **-3.01** | -0.91 | -19.7 | 92.0 |
| orb | ALL | 2,686 | -289 | -1.17 | -0.32 | -8.6 | 67.2 |
| **fade** | ALL | 2,686 | **-468** | **-7.38** | -2.24 | -12.2 | 77.1 |
| mix | *(fitted window, >= 2025-08-26)* | 261 | +302 | +0.32 | +0.27 | +3.7 | 15.6 |

**0 of 3 regimes pass. The rule fires.** And the finding is stronger than the rule asked for: at
t = -3.01 on a sample above A-4's own 2,120-session threshold, the mix is not *unproven*, it is
**significantly negative**. The last row is the whole story - the only window in eleven years
where this sleeve makes money is the one its parameters were fitted on, and even there
**t = +0.32**. Year by year the mix is positive in 4 of 11 years and no year reaches |t| = 1.

**The late-day fade is the clearest negative the A-track has produced: -$468/day at t = -7.38**,
negative in every regime separately (-4.33 / -6.75 / -1.60) and on the fitted window too
(-$106/day). A-4 explicitly refused to drop it because on 260 IBKR sessions it scored +$65/day
marginal at t = +0.27. That sample could not see a 7-sigma effect; this one can. This is the
overfitting lesson A-9 predicted, arriving from the other direction.

**A-4's long-volatility mechanism survives, with power.** corr(daily P&L, universe mean range) is
**+0.202 at t = +10.70** over 2,686 sessions and positive in all three regimes separately
(+0.240 / +0.161 / +0.300) against A-4's +0.538 on 260. So the *variation* really is a range bet -
the level is just below zero. That keeps O-1 (options-implied regime features) alive as the one
remaining idea with a measured mechanism behind it, and kills size as a lever.

- **Shipped** (rule c, with a passed replay of 2026-09-08 first: 34 trades, 368 decisions, flat at
  close, P&L -2,280 on 500k of sleeve equity): `live/intraday_config.json` `alloc.late_momo`
  **1.0 -> 0.0**. It is refused at 7 sigma out of sample and costs nothing in sample - on the 261
  sessions any A-track parameter has seen, ORB alone earns +$322/day against the mix's +$302.
- **Held, not restored:** `equity_frac` stays at **0.5** (this morning's A-10 preliminary cut it
  from 1.0). What is left after dropping the fade is ORB alone at -$289/day, t = -1.17 - not
  proven to lose, not proven to earn. Restoring size to a book with no demonstrated edge is not
  something evidence supports, and taking it to zero would also end A-5 part 2 before it starts:
  the live slippage measurement needs the sleeve to place orders.
- **Next.** Not another size or stop lever - A-1, A-2, A-7, A-9 and now A-10 have between them
  spent the signal layer and the framework constants. The two live threads are **A-5 part 2**
  (run `scripts/slippage_report.py` after today's close, the first session that will place real
  orders) and **O-1**, whose regime gate is the only untried idea with a mechanism this study
  actually confirms. Whether the sleeve should trade paper capital at all in its current form is
  now a one-line question to the owner in `BLOCKERS.md`.

## 2026-09-10 - A-10 preliminary: the sleeve on ten years of Alpaca bars, and a size cut for today

- **What.** `scripts/alpaca_data.py` now holds split-adjusted SIP 1-minute bars for the 16-name
  universe from 2016-01-04 (~2,686 sessions each). Two runs of the deployed mix
  (`INTRADAY_DATA_DIR=data/minute_alpaca`), before the loop's split-factor commission fix
  landed, so costs are overstated on pre-split history (NVDA/AVGO/SMCI in H1 2024):
  (a) the A-6 window 2025-12-15..2026-09-09, split 2026-06-15: IS +11.5%/yr Sharpe 0.57,
  OOS +38.2%/yr Sharpe 1.33, 47-50 trades/day, 4 loss-limit days per half - same sign and
  shape as the IBKR store (+24.2/+55.3), smaller magnitude; (b) 2024-01-02..2026-09-09 (674
  sessions): -3.8%/yr, Sharpe -0.02, max drawdown 48.5%, 44 loss-limit days, best day +107k,
  worst -37k.
- **Reading.** The data source is not the story; the period is. 2024 to mid-2025 was a
  losing regime for this mix and the last nine months a winning one, consistent with A-4's
  finding that the sleeve is long the day's range. A-10 proper (three regimes, corrected
  costs, `scripts/sweep_a10.py`) is running in the loop.
- **Decision.** `live/intraday_config.json` `equity_frac` 1.0 -> 0.5 for the 2026-09-10 session
  (trade count unchanged, dollars halved, daily loss limit unchanged at 2.5% of NAV). Restore
  to 1.0 only if A-10 shows the mix positive in at least two of three regimes on the corrected
  cost model; otherwise keep 0.5 or lower and redirect the loop to regime gating (O-1 IV
  features, A-9 range gate) rather than size.
- **Next.** A-10 result; then the regime gate work.

## 2026-09-10 - A-5 (part 1): the sleeve breaks even at 2.6 bps of slippage, and it is charged 1.5

- **What.** A-5's live-fill measurement needs a paper session that actually placed orders and
  there is none yet, so this iteration did the half that does not: it priced the cost model from
  the same 260-session store the harness runs on. New `scripts/sweep_a5.py` with three phases
  (`spread`, `impact`, `breakeven`), a backtest-only `--slippage-bps` override in
  `scripts/intraday_backtest.py`, and `scripts/slippage_report.py` - the live-fill comparison
  itself, finished and self-tested, waiting on tonight's log. The control reproduces A-4 exactly:
  260 sessions, CAR 15.3%, Sharpe 0.689, $610/day, $1,025/day of costs, 12,743 fills.
- **Why.** Top open backlog item. `SLIPPAGE_BPS = 1.5` in `scripts/intraday_common.py` is the one
  number in the harness that was never measured, and it is charged on 49 trades/day - **$820/day
  of slippage plus $208 of commission against a $610/day modelled edge.** The cost model is
  bigger than the result it is judging, so its error bar is the sleeve's error bar.

### The decision number: breakeven slippage

Slippage is `|qty| * px * bps / 1e4` on every fill, so at fixed turnover P&L is linear in the
constant. Two confirming full-store runs bracket the shipped value and the line is straight to
$73/day:

| slippage | $/day | CAR % | Sharpe | costs/day |
| --- | --- | --- | --- | --- |
| 0.0 bps | **1,671** | 41.9 | 1.51 | 230 |
| **1.5 bps (shipped)** | **610** | 15.3 | 0.69 | 1,025 |
| 3.0 bps | **-231** | -5.8 | -0.11 | 1,660 |

**Breakeven is 2.64 bps from the runs, 2.62 bps analytically.** The sleeve turns over
**$5.46M/day on a $1M book - 5.5x equity a day** - so one basis point of slippage is $546/day and
the entire modelled edge is **1.1 bps wide**. Per window:

| window | sessions | notional/day | $/bp/day | $/day at 1.5 | $/day at 0 | breakeven | se in bps |
| --- | --- | --- | --- | --- | --- | --- | --- |
| full store | 260 | $5.46M | 546 | +610 | +1,430 | **2.62 bps** | 1.84 |
| A-4 holdout | 77 | $5.34M | 534 | -813 | **-11** | **-0.02 bps** | 3.28 |
| tuning window | 183 | $5.52M | 552 | +1,209 | +2,036 | 3.69 bps | 2.22 |

**The holdout line reframes A-4.** Its breakeven is zero: on the 77 sessions no A-track parameter
ever saw, the sleeve's *gross* P&L before any slippage at all is **-$11/day**. The -$813/day A-4
reported is not a calmer regime earning less - it is a book with **no gross edge whatsoever**
paying $802/day of modelled costs. A-4's long-volatility explanation still holds for the
variation, but the level on unseen data is zero before costs.

### Bounding the constant from the bars: an upper bound, and why it is only that

Roll (1984) and Corwin-Schultz (2012) on 1-minute bars, per name, notional-weighted by what the
sleeve actually trades: **half-spread 2.65 bps**, unweighted mean 2.40, median 1.67. Taken at
face value that sits exactly on the 2.62 bps breakeven. It should **not** be taken at face value:
`corr(CS estimate, 1-minute return std) = +0.906` across the 16 names and the CS/vol ratio is
0.32-0.65 with a median of 0.34, i.e. the estimator is a rescaled volatility, not a spread - the
extreme is SOXS at 21.7 bps "spread" on 33 bps of per-minute vol. The hard lower bound, half of
one tick notional-weighted, is **0.36 bps**. So the honest statement is
**half-spread ∈ [0.36, 2.65] bps, breakeven 2.62 bps**: the constant cannot be shown wrong from
bars alone, and no estimator on this data will settle it. Only fills will.

### What the bars *can* prove is wrong: participation

Every fill's size against the volume of the minute it fills in, over 12,743 fills:

| | median | p75 | p90 | p99 | max |
| --- | --- | --- | --- | --- | --- |
| share of the fill minute's volume | 1.03% | 2.43% | 5.55% | **26.1%** | **199%** |

Notional-weighted mean 2.69%; mean fill $111.5k. The tail is concentrated and it is not random:
**SMCI (median 5.5%, p90 17.3%), SOXS (2.8% / 18.7%), COIN (3.1% / 10.6%) and MSTR (2.2% / 6.1%)
carry 30% of the sleeve's traded notional** while the megacaps sit at 0.2-0.9%. A fill of 199% of
a minute's volume at that minute's open, with zero impact, does not exist. This is a modelling
defect rather than a lever, so removing it is not a lever hunt and A-4's power argument does not
apply to it - it is the successor item **A-10**.

One thing the harness is *not* missing: the delay from deciding on bar t's close to filling at
bar t+1's open is **-0.12 bps notional-weighted (se 0.04)** - a hair in the sleeve's favour, not
a hidden cost. So the whole modelled cost of a fill is 1.50 slippage + 0.38 commission = **1.76
bps all-in**, and there is no cushion in the fill convention.

### The live half, ready and idle

`scripts/slippage_report.py` prices every live fill against the same next-bar open the backtester
uses, signed so positive means the fill cost more than the backtest assumed, and reports the
notional-weighted mean, its standard error, per-symbol and per-side breakdowns, fill rate and
latency, pooled across sessions. It **self-tests**: injected +2.75 bps on synthetic two-sided
fills is recovered as +2.75, and a buy filled below the reference reads negative. It refuses to
write the constant. Its input needs three small additions to the trader's logging, all made and
verified: `order` now carries the decision bar `t`, `fill` carries the IB order id and the
exchange's own `filled_at`, and `decision` carries the price the strategy saw (`ref`). Because
that touches `Trader.step` and `LiveExecutor`, a replay was run per AGENTS.md rule (a):
**2026-09-08 with the deployed params, 46 trades, flat at close, identical to the A-9 replay**,
and the log now carries `ref` on every decision that ordered.

Why there is no measurement yet: the only live log on disk, 2026-09-09, is a `--dry-run` started
by hand at 11:08 ET that stopped at 11:15, so it has 10 live decisions and zero orders. The
scheduled task is Ready with next run today 09:25 ET and no `--dry-run` in its arguments, and
`live/APPROVED_PAPER.md` exists, so tonight is the first session with fills.

- **Decision. Nothing shipped.** `SLIPPAGE_BPS` stays 1.5, `live/intraday_config.json` is
  untouched, no framework constant moved. The measurement that A-5 asks for does not exist yet
  and the bars cannot substitute for it; moving a constant that sets the sleeve's sign on an
  estimator that is provably measuring volatility would be worse than leaving it.
- **Next.** Run `python scripts/slippage_report.py` after tonight's close, every session, and
  accumulate - the pooled mean and its standard error are the deliverable, not one day. Then
  **A-10**: cap order size at a share of the fill minute's median volume and re-run the mix on
  both halves, because ~30% of the sleeve's notional is traded at a participation rate its cost
  model cannot support.

## 2026-09-10 - A-9: the day's range pays, but only the half of it that is unknowable at entry

- **What.** Added `range_atr_min` / `range_atr_max` to `algorithms/intraday/orb/signal.py` (both
  default 0 = off) gating the breakout on the opening range's width divided by ATR14 at the
  moment the range closes, and `scripts/sweep_a9.py`: an attribution phase (one ORB run, P&L
  attributed to each traded symbol-session, bucketed by width) and two grids (11 cells on the
  ORB module, 4 in the deployed mix), all on the 260-session store split at A-4's 2025-12-15
  holdout boundary.
- **Why.** Top open backlog item, and the only lever left with a measured mechanism behind it:
  A-4 found daily P&L correlating **+0.538 (t = +10.25, n = 260)** with the universe's same-day
  range, and ORB gates on volume alone. The opening range closes before the first entry, so its
  width is causal - the one piece of "today is a wide day" available in time to act on.

### The mechanism is real, and it is entirely in the part you cannot see

Decomposing each session's mean range across the universe into the opening 15 minutes and the
residual after regressing that out:

| predictor of ORB's daily P&L | all 260 | holdout 77 | tuning 183 |
| --- | --- | --- | --- |
| realized full-day range | **+0.568 (t +11.09)** | +0.622 (t +6.87) | +0.560 (t +9.10) |
| opening range (known at entry) | **+0.080 (t +1.28)** | **-0.009 (t -0.07)** | +0.101 (t +1.37) |
| residual (not known at entry) | **+0.665 (t +14.29)** | +0.725 (t +9.12) | +0.645 (t +11.37) |

A-4's correlation reproduces on the ORB module alone and is stable in both halves, so it is not
a fitting artifact. But the opening range - which is itself a decent proxy for the day's range,
**corr +0.626** - carries essentially none of the payoff, and none at all in the holdout. The
reason is mechanical: ORB's stop is the range midpoint, so the width *is* the risk unit. A wide
opening scales the win and the loss together and nets out; what pays is the range the day adds
**after** entry, which is unknowable by construction. **A-9's premise is refused at the root.**

Attribution agrees, on 3,731 traded symbol-sessions: corr(P&L, width/ATR14) = +0.029 (t +1.80),
and after demeaning within symbol it is +0.036 (t +2.19) - which splits into **TUNE +0.052
(t +2.65) and HOLDOUT -0.022 (t -0.73)**.

### The grid, which is the sharpest overfitting demonstration in the A-track so far

ORB module, deployed sub-params, both halves (control reproduces A-4's `orb` rows to the digit):

| cell | HOLD CAR / Sharpe / $day | TUNE CAR / Sharpe / $day | tr/day | paired t vs control |
| --- | --- | --- | --- | --- |
| control (no gate) | -2.0 / 0.05 / -80 | 25.8 / 1.02 / +990 | 36 | - |
| min 3.2 | -8.2 / -0.31 / -335 | 26.7 / 1.17 / +1,025 | 31 | -0.14 |
| **min 3.6** | **-20.5 / -1.19 / -878** | **49.7 / 2.17 / +1,861** | 26 | +0.75 |
| min 4.0 | -20.2 / -1.45 / -863 | 41.9 / 2.19 / +1,581 | 20 | +0.29 |
| min 4.4 | -3.3 / -0.21 / -131 | 40.8 / **2.43** / +1,542 | 15 | +0.52 |
| min 5.0 | +0.9 / 0.14 / +35 | 22.6 / 1.83 / +873 | 9 | -0.06 |
| max 4.4 | +0.6 / 0.12 / +24 | -9.4 / -0.49 / -377 | 22 | -1.52 |
| **max 3.6** | **+21.6 / 1.46 / +801** | **-13.9 / -1.27 / -561** | 11 | -1.02 |

**Every "keep the wide openings" cell beats the control in the tuning window and loses in the
holdout; every "keep the narrow openings" cell does the exact opposite.** The lever does not
select trades, it selects *which half of the sample you are looking at*. `min 3.6` nearly
doubles the tuning window's Sharpe to 2.17 - the best number this sleeve has ever produced -
while turning the holdout into -20.5% CAR at Sharpe -1.19. Its mirror, `max 3.6`, earns Sharpe
1.46 on the holdout and -1.27 on the tuning window. Paired against the control over all 260
sessions, **not one of the eleven cells reaches |t| = 1.6.**

In the deployed mix the pattern is identical and larger: `min 3.6` gives HOLD -31.8 / -1.96 /
-$1,432 against TUNE 58.6 / **2.32** / +$2,174 (paired t +0.92); `min 4.4` gives -16.3 / -1.27
against 49.5 / **2.53** (t +0.62); `max 3.6` gives +5.4 / 0.48 against -7.2 / -0.60 (t -1.02).
The mix control reproduces A-4 exactly (-19.1 / -0.73 / -$813 and 33.8 / 1.27 / +$1,289).

The wide-range names the backlog asked about separately (SOXL/SOXS/SMCI/MSTR) carry most of the
in-sample effect - split at the median width their mean symbol-session P&L is -158 vs +733
(SOXL), -23 vs +580 (SOXS), -176 vs +491 (MSTR), +74 vs +296 (SMCI) - and their width quintiles
are non-monotone (-12, -233, +30, +725, +256), i.e. the effect is one bucket in four names.

### Decision

**Refused. Nothing shipped.** `live/intraday_config.json` is untouched, `range_atr_min` and
`range_atr_max` stay at 0, and no framework constant moved. The gate has no OOS improvement, so
rule (c) forbids it; and had it been judged on the 183-session window every prior A-track
iteration used, `min 3.6` would have looked like the best result in the sleeve's history and
would have shipped. **That is the holdout earning its keep, and it is the reusable lesson.**

The signal edit is behaviour-preserving with the gates off - the control rows match A-4 to the
digit in both the module and the mix - and the ORB module is loaded by the live trader, so a
**replay of 2026-09-08 was run anyway: 46 trades, flat at close, P&L -4,881 on 368 decisions**,
identical to the replay recorded in the config when A-2 shipped.

- **Next.** A-9 was the last A-track item with a stated mechanism. A-8 (the entry window) is now
  the only open lever and A-4 already said to park it: it would produce the same table of
  statistically identical cells this one did. The binding constraint has not moved - the sleeve
  needs ~2,120 sessions to prove itself and has 260 - so the honest next step is **not another
  gate**. It is A-5: replace estimated slippage with slippage measured from the live log, which
  is the one number in the harness that is currently a guess rather than a measurement, and the
  paper account starts generating it today. Champion unchanged at S-12; the daily sleeve was not
  touched.

## 2026-09-09 - A-4: twelve months of sessions, and the sleeve's return is not distinguishable from zero

- **What.** `scripts/intraday_data.py --months 12` extended the minute store from 183 sessions
  (2025-12-15..2026-09-08, the window every A-track parameter was chosen on) to **260**
  (2025-08-26..2026-09-08, plus today's partial). The 77 sessions before 2025-12-15 are a
  genuine **holdout**: no allocation, stop, filter or constant in this sleeve has ever seen
  them. New `scripts/sweep_a4.py` runs the deployed mix and its two modules over both halves in
  a process pool; the headline is a single 260-session run of the deployed config.
- **Why.** Top open backlog item, and it was put there by A-7's own arithmetic: on 183 sessions
  one standard error on the sleeve's total P&L was $229.6k against a $221.2k total, so A-1, A-2
  and A-7 had all been judged with an instrument that cannot resolve the thing being judged.

### The data first: a truncation bug, found and fixed

`intraday_data.py` requested each month window ending at the **wall-clock time of the run**.
IBKR truncates the session `endDateTime` lands in, so the newest session of every window was
stored as a partial day - a 139-bar session that every strategy then treated as a full one and
booked a session P&L on two hours of tape. Fixed by snapping every request end to 20:00 ET on
its own day (`snap_after_close`), so a window boundary can now only ever fall *between*
sessions; added `--repair`, which re-fetches only the months holding a short session, and
`truncated_sessions()`, which `--status` now flags. The store is clean: **all 16 symbols hold
261 sessions, 101k bars each, with exactly two 210-bar days (2025-11-28 and 2025-12-24, real
NYSE half days) and one partial (today, still open).** Re-running A-7's control on the repaired
bars moves it by about a tenth of a point (IS 24.211/1.007 -> 24.322/1.010, OOS 55.328/1.731 ->
56.444/1.757, ledger `20260910T015251Z`), so **every
prior A-track conclusion stands on the repaired data**; the bug mattered for the fetch, not for
the record.

### The holdout

| cell | HOLD 77 sess: CAR / Sharpe / $day / worst | TUNE 183 sess: CAR / Sharpe / $day / worst | 260-sess total |
| --- | --- | --- | --- |
| **deployed mix (orb + late fade)** | **-19.1 / -0.73 / -813 / -28.2k** | **33.8 / 1.27 / +1,289 / -30.3k** | **$173,229** |
| orb only | -5.2 / -0.08 / -209 / -29.0k | 24.5 / 1.00 / +943 / -30.7k | $156,437 |
| late fade only | -13.5 / -2.46 / -563 / -15.8k | 6.2 / 1.09 / +243 / -19.1k | **$1,099** |

- **The deployed sleeve loses money on the sessions it was not tuned on.** -$813/day over 77
  sessions, against +$1,289/day over the 183 it was fitted to.
- **And that difference is not measurable either.** Welch t on daily P&L, holdout against
  tuning: mix **-0.96**, orb -0.51, late fade -1.65. The holdout's own mean is **-0.46**
  standard errors from zero. So the honest statement is not "the sleeve broke", it is *"the
  sleeve has never been measured"*.
- **The headline, a single 260-session run of the deployed config: net +15.87% on the $1M
  sleeve, CAR 15.3%, Sharpe 0.69, $610/day at std $16,222, t = +0.61.** A 95% interval on the
  year's total P&L is **[-$354k, +$671k]** around a point estimate of $158.6k. 12,743 trades
  (49.0/day, turnover 5.46x equity/day), costs $1,025/day, 45% winning days, worst day
  -$28,368, 12 loss-limit halts, max drawdown 14.4%. (The two half-runs summed give $173.2k
  rather than $158.6k because each half restarts at $1M; the single run is the honest figure.)
- **The late-day fade contributes nothing over a year.** Standalone it made **$1,099 across 260
  sessions** - four dollars a day, on 11.8 trades/day costing $232/day, i.e. its gross edge is
  spent entirely on its own turnover. Its marginal contribution *inside* the mix is +$65/day
  (t = +0.27), split -$604/day on the holdout and +$346/day on the tuning window. A-6 shipped it
  on the strength of the tuning window alone.

### The power calculation, which is the real result

At the measured Sharpe of 0.69, the sessions needed to reject "this sleeve earns zero" at two
standard errors are `(2/0.69)^2` years = **~8.4 years, about 2,120 sessions**. The store holds
260. **No achievable backtest sample can validate this sleeve at this effect size**, and it
follows that no A-track experiment run on this harness - A-1, A-2, A-7 and every cell in them,
all of which sought differences *smaller* than the base rate - was ever capable of returning an
answer. Doubling the universe with equally good uncorrelated signals buys sqrt(2) of Sharpe and
still needs four years. The lever hunt is finished not because the levers are spent but because
the measuring instrument does not exist.

### What does have a mechanism, and one unspent lever

Regressing daily sleeve P&L on the universe's mean daily range, 260 observations:

| instrument | corr | t | fitted $/day at 3.78% range (holdout mean) | at 4.44% (tuning mean) |
| --- | --- | --- | --- | --- |
| same-day range | **+0.538** | **+10.25** | -$2,613 | +$2,011 |
| prior-day range (causal) | +0.029 | +0.47 | +$514 | +$768 |

- **The sleeve is a long-volatility position, and that is measurable at t = +10.** ORB's payoff
  scales with the day's range while its cost floor does not, so it wins on wide days and bleeds
  on calm ones. The holdout is the calmer window by a wide margin - mean daily range 3.78% vs
  4.44%, mean absolute daily move 2.36% vs 2.96%, on comparable dollar volume - so the negative
  holdout is a **regime**, not a decayed signal. That is worth more than the holdout sign itself.
- **Yesterday's range does not predict today's** (t = +0.47), so a day-ahead volatility gate is
  not available. Split into terciles on the causal proxy the pattern is still suggestive - calm
  -$341/day, mid -$332/day, wild +$2,772/day, with the wild third carrying $238k against -$58k
  from the other two - but at |t| ~ 1 that is the same unmeasurable scatter as everything else.
- **The unspent lever is same-day and causal**: ORB enters after the 15-minute opening range, so
  the **width of that range relative to trailing ATR14 is known at entry**. ORB currently gates
  on volume (`vol_ratio_min = 1.2`) and never on range width. That is the one instrument that
  attacks the +0.54 correlation without look-ahead, and it is filed as **A-9**.

### Decision

- **Nothing shipped. `live/intraday_config.json` is untouched and the trader is byte-identical,
  so no replay was owed.** Dropping the late-day fade is the tempting move - it improves the
  holdout half from -$813 to -$209/day - but it *costs* $16.8k over the full 260 sessions at
  t = +0.27, so it fails AGENTS.md rule (c) on its face: there is no OOS improvement, only a
  different slice of the same noise. Changing a deployed book eleven hours before it trades on
  a coin flip would be the worst of both.
- **Shipped instead:** the extended and repaired 12-month store, the `snap_after_close` /
  `--repair` / `truncated_sessions` fix in `intraday_data.py`, and `scripts/sweep_a4.py`.
- **The finding goes to the owner** as a one-line question in `BLOCKERS.md`: the intraday
  sleeve's twelve-month backtest cannot distinguish its return from zero, and at this Sharpe no
  backtest ever will, so it can only be judged live on paper or shrunk.
- **A-4 is done and closed. A-9 is the new top item** - the opening-range-width gate, the only
  lever with a measured mechanism behind it rather than a table of indistinguishable cells.
  A-8 (the ORB entry window) stays parked for the reason A-7 gave and A-4 has now quantified.

## 2026-09-09 - A-7: the framework risk limits are a tail dial with no price. Nothing shipped

- **What.** The three shared constants in `scripts/intraday_common.py` that A-2 pointed at -
  `DAILY_LOSS_LIMIT`, `PER_SYMBOL_HARD_CAP` and the sleeve `gross` - swept on the deployed mix
  (ORB with the 4x ATR backstop + late-day fade) over the usual window 2025-12-15..2026-09-08,
  split 2026-06-15, 124 IS / 59 OOS sessions. Fifteen cells, 30 half-runs.
  `scripts/intraday_backtest.py` grew a `--risk` override that applies **to the backtest only**
  (`RISK` dict, defaults are exactly the shipped constants), so nothing under `scripts/` that
  the live trader executes changed and no replay was owed. `scripts/sweep_a7.py` runs the grid
  in a process pool, loading bars and causal features once per worker. The control reproduces
  A-1's mix run to the digit: IS 24.211% / 1.007, OOS 55.328% / 1.731.
- **Why.** Top open backlog item. A-2 measured that every *signal*-level control leaves the
  loss-limit days where they are unless it is tight enough to destroy the in-sample return, so
  the framework constants were the last untested surface on this sleeve.

### The daily loss limit (deployed 2.5%)

| limit | IS CAR / Sharpe | OOS CAR / Sharpe | halts (183 sess) | worst day | total P&L |
| --- | --- | --- | --- | --- | --- |
| 1.5% | 17.6 / 0.79 | 88.6 / 2.57 | 40 (21.9%) | -20,470 | 243,052 |
| 2.0% | 18.9 / 0.83 | 57.0 / 1.78 | 18 (9.8%) | -25,816 | 200,528 |
| **2.5% (shipped)** | **24.2 / 1.01** | **55.3 / 1.73** | **8 (4.4%)** | **-30,284** | **221,188** |
| 3.0% | 26.1 / 1.07 | 62.0 / 1.90 | 3 (1.6%) | -37,170 | 240,724 |
| 3.5% | 23.5 / 0.98 | 61.7 / 1.89 | 2 (1.1%) | -42,463 | 228,649 |
| off | 20.4 / 0.86 | 61.7 / 1.89 | 0 | -57,009 | 214,740 |

- **The tail response is monotone and mechanical; the return response is scatter.** The worst
  day walks -20.5k -> -25.8k -> -30.3k -> -37.2k -> -42.5k -> -57.0k across the range, i.e. the
  limit does exactly the one job it was written to do. Return does not walk with it at all:
  total P&L is 200.5k at 2.0% and 243.1k at 1.5%, with the shipped 2.5% in between and 3.0%
  near the top. **Nothing here is measurable.** Paired against the control on the same 183
  daily returns, every cell in the whole sweep scores |t| <= 1.06 (limit 3.0% t=+0.80,
  limit 1.5% t=+0.39, limit 2.0% t=-0.62, off t=-0.16); the control's own daily P&L std is
  $16,974, so one standard error on the 183-session total is $229.6k against a total of
  $221.2k. The sample cannot distinguish any of these cells from any other.
- **A-7's stated worry is refused: stopping early is free.** On the sessions each cell halted,
  compared with the limit-off run on those same dates: at 1.5% (40 halts) the halted book
  ended -1.57% against -1.63% for the same days run to the close, i.e. halting *saved* $453 per
  halt; at 2.5% it saved $1,053 per halt; at 3.0% $8,497 and at 3.5% $6,265. Only the 2.0% cell
  shows a cost, $697 per halt. So a day that has lost 1.5-2.5% by lunchtime is not a day that
  keeps falling, and it is not a day with edge left either - the remainder is a coin flip worth
  approximately zero, at every limit tested, even one that fires on a fifth of all sessions.
- **The limit overshoots its nominal level by 0.15-0.38 points of NAV** (2.5% delivers a -2.65%
  worst day, 1.5% delivers -1.88%), because the breach is detected on a marked-to-close bar and
  the flatten then pays spread. To bound the worst day at X, set the limit near X - 0.3.

### The per-symbol cap (deployed 0.15 in config, 0.20 as the framework backstop)

| cap | IS CAR / Sharpe | OOS CAR / Sharpe | total P&L |
| --- | --- | --- | --- |
| 0.06 | 10.4 / 0.82 | 32.4 / 2.06 | 117,581 |
| 0.08 | 15.7 / 0.94 | 45.0 / 2.07 | 165,105 |
| 0.10 | 22.9 / 1.09 | 57.4 / 2.04 | 218,702 |
| 0.12 / 0.15 / 0.20 / 0.25 | 24.2 / 1.01 | 55.3 / 1.73 | 221,188 |

- **The framework's `PER_SYMBOL_HARD_CAP = 0.20` has never bound, and neither has the config's
  0.15.** Cells at 0.12, 0.15, 0.20 and 0.25 are bit-identical - zero dollars of difference over
  183 sessions - so the deployed mix never asks for more than ~0.12 of equity in one name.
  Below 0.12 the cap stops being a risk control and becomes a **size dial**: it removes P&L
  roughly in proportion to the size it removes (221k -> 219k -> 165k -> 118k).
- **0.10 is a spike, not a shelf, and was refused.** It is the only cell that beats the control
  on IS Sharpe (1.09 vs 1.01) and it improves OOS Sharpe (2.04 vs 1.73) and drawdown in both
  halves, for a $2.5k P&L wash (t = -0.21). But its neighbours disagree: 0.08 loses on IS Sharpe
  (0.94) and 0.12 is the control. OOS Sharpe is flat at 2.04-2.07 from 0.06 to 0.10, which is
  the signature of a size dial against a fixed cost floor, not of a lever finding better risk.
- **Gross is monotone in the in-sample half and saturates at the deployed 1.5**: 1.00 gives
  17.9 / 0.96 IS and 54.1 / 2.02 OOS on 190.9k, 1.25 gives 20.5 / 0.93 and 58.9 / 1.90 on
  210.7k, the deployed 1.5 gives 24.2 / 1.01 and 55.3 / 1.73 on 221.2k, and 2.0 gives
  24.7 / 1.01 and 57.6 / 1.76 on 227.3k (t = +0.56). OOS Sharpe falls monotonically as gross
  rises, which is what leverage does. Gross 2.0 buys +2.7% of P&L for a step outside A-3's
  stated 1.0-1.5x target and outside the `GROSS_HARD_CAP = 1.6` rationale (it would put the two
  sleeves at ~3.2x against day-trading buying power), so it is a risk-posture decision for the
  owner, not an experiment result. Refused.
- **Decision. Nothing shipped.** `DAILY_LOSS_LIMIT` stays 0.025, `PER_SYMBOL_HARD_CAP` stays
  0.20, `GROSS_HARD_CAP` stays 1.6, and `live/intraday_config.json` was not touched, so the
  live trader is byte-identical and no replay was required. The finding is that this family of
  levers has **no measurable price and one real product**: a monotone bound on the worst day.
  That makes the limit a pure risk-posture dial, and risk posture belongs to the owner - the
  priced menu (1.5% caps the worst day near -2.0% of NAV and halts a fifth of sessions; the
  shipped 2.5% caps it near -2.7% and halts 4%; off leaves -5.0%) is now a one-line question in
  `BLOCKERS.md`.
- **What this closes.** With A-1, A-2 and A-7 all negative, both the signal layer and the risk
  layer of this sleeve are measured and spent at the current sample size. Every remaining
  difference is smaller than one standard error of 183 sessions, which is the real constraint:
  **the sleeve needs more sessions, not more levers.** That makes A-4 (extend the minute store
  to 12 months) the highest-value item, ahead of A-8's entry-window sweep, since A-8 would be
  judged with the same instrument that just failed to resolve a 20% swing in total P&L.
- **Next.** A-4, then A-8 on the longer sample.

## 2026-09-09 - A-1: the VWAP fade is repairable but not additive. Retired from the mix, alloc stays 0

- **What.** Eleven variants of `algorithms/intraday/vwap_trend/signal.py` plus six sleeve-level
  runs, fixed window 2025-12-15..2026-09-08, split 2026-06-15, 124 IS / 59 OOS sessions.
  The module was given the five levers A-1 named, every one defaulted to the shipped
  behaviour: `min_hold`, `skip_from`/`skip_to` (a midday blackout), `trend_align`/`trend_min`
  (a session-trend filter), `atr_expand_min` (a range-expansion gate on the session-so-far
  mean ATR14, accumulated causally) and `agg` (a coarser decision cadence). The refactor is
  exact - the control run reproduces the A-6 fade to the digit, IS -56.040% / OOS -10.132%.
- **Why.** Top backlog item. The fade is the sleeve's only turnover engine at ~98 trades/day
  and A-6 set its alloc to 0 because it loses -56%/yr in-sample. A-1's own exit criterion:
  make it positive in both halves after costs, or delete the alloc entry and close it.

### Standalone (annualized after costs, IS -> OOS)

| variant | IS CAR / Sharpe | OOS CAR / Sharpe | trades/day IS | $/trade OOS |
| --- | --- | --- | --- | --- |
| control (30/8, shipped) | -56.0 / -3.26 | -10.1 / -0.26 | 97.8 | -4 |
| band 50/12 + hold 12 | -50.9 / -2.92 | -11.1 / -0.35 | 67.8 | -6 |
| 5-minute cadence | -57.5 / -3.57 | -9.7 / -0.29 | 72.6 | -5 |
| skip 11:30-14:00 | -50.1 / -2.96 | -3.7 / -0.02 | 83.3 | -2 |
| **trend filter, 20 bps** | **-11.9 / -1.00** | **+16.9 / +1.23** | 31.7 | +18 |
| trend filter, 10 bps | -8.9 / -0.71 | +23.6 / +1.64 | 34.2 | +23 |
| trend filter, 40 bps | -5.3 / -0.49 | +15.6 / +1.16 | 26.1 | +19 |
| trend filter **inverted** | -46.3 / -2.78 | -5.5 / -0.13 | 74.9 | -3 |
| trend + 50/12 + hold 12 | -1.4 / -0.09 | +9.7 / +0.81 | 17.2 | +18 |
| trend + 50/12 + hold 12, 40 bps | -1.9 / -0.15 | +11.1 / +0.92 | 14.5 | +24 |
| **trend + 70/15 + hold 20** | **+0.8 / +0.13** | **+11.3 / +0.94** | 11.0 | +32 |
| + range expansion 1.2x | -0.7 / -0.27 | +5.4 / +2.45 | 0.8 | +263 |

- **Only one of the five levers is a mechanism.** Min hold, the midday blackout and the coarse
  cadence each remove trades roughly in proportion to the loss they remove and leave the
  module deeply negative - they shrink the position, they do not change the sign. The
  **session-trend filter does change the sign**: taking only the fades that lean *with* the
  day's direction (buy the dip below VWAP on an up day, short the pop above VWAP on a down
  day) moves the module from -56.0/-10.1 to -11.9/+16.9 while cutting turnover by two thirds.
  **Inverting the filter is the control and it fails as predicted** (-46.3/-5.5), so this is
  the mechanism and not a threshold that happened to land well: the fade was losing because it
  was fighting trend days, and the losses are concentrated in exactly the trades the filter
  removes. It is also a shelf - `trend_min` at 10, 20 and 40 bps all give OOS Sharpe 1.16-1.64
  and the same sign in both halves.
- **Range expansion is not usable.** Requiring atr14 >= 1.2x the session's mean kills the
  module: 0.8 trades/day, 104 trades over 124 sessions. The OOS Sharpe of 2.45 on 50 trades is
  not a result, it is an empty sample, and it is not carried forward.
- **Stacking the levers onto the trend filter walks a frontier, it does not climb.** Widening
  the band and adding a hold trades OOS return for IS return one-for-one - 20 bps alone is
  -11.9/+16.9, plus 50/12 and hold 12 is -1.4/+9.7, plus 70/15 and hold 20 is +0.8/+11.3.
  The best cell in both halves is the last one, and it is the only cell positive in both -
  by +0.8% CAR at Sharpe 0.13 on 124 sessions, which is indistinguishable from zero
  (SE of an annualized Sharpe on 124 days is ~1.4).

### The sleeve is what decides, and the sleeve says no

| mix (ORB 4x ATR + late fade, + trend-filtered fade at) | IS CAR / Sharpe / DD | OOS CAR / Sharpe / DD | trades/day | total P&L, 183 sessions |
| --- | --- | --- | --- | --- |
| **0 (deployed control)** | **24.21 / 1.007 / 14.5** | **55.33 / 1.731 / 7.30** | **46-49** | **$221,211** |
| 0.25 (70/15, hold 20, 20 bps) | 23.48 / 0.977 / 15.7 | 57.95 / 1.827 / 7.06 | 58.0 | $222,294 |
| 0.5 (70/15, hold 20, 20 bps) | 22.25 / 0.932 / 16.6 | 59.11 / 1.880 / 6.73 | 58.1 | $218,785 |
| 0.5 (50/12, hold 12, 40 bps) | 23.34 / 0.959 / 16.6 | 60.04 / 1.901 / 6.89 | 62.4 | $225,155 |
| 0.5 (70/15, hold 20, 40 bps) | 21.04 / 0.886 / 16.8 | 61.24 / 1.927 / 6.87 | 56.9 | $216,934 |
| 1.0 (70/15, hold 20, 20 bps) | 20.74 / 0.866 / 18.4 | 54.32 / 1.769 / 5.87 | 57.5 | $204,124 |

- **Every cell is the same trade: IS return and IS drawdown for OOS return.** The IS response
  is monotone in the allocation (24.21 -> 23.48 -> 22.25 -> 20.74) and IS drawdown widens by
  1.2-3.9 points in every one; OOS rises to a peak near 0.5 and falls again at 1.0. Three
  different fade parameter cells at 0.5 give the same shape, so this is a shelf and not a
  spike - the effect is real, it is just not a gain.
- **Over the whole window it is a wash bought with turnover.** Total P&L across all 183
  sessions is $221.2k deployed against $222.3k / $218.8k / $225.2k / $216.9k for the four
  cells at alloc 0.25-0.5 - a spread of +/-2% around doing nothing - and $204.1k at 1.0.
  The price of that wash is 22-34% more trades per day (46-49 -> 57-62) and 2 points of IS
  drawdown, on a sleeve whose live costs are only estimated (1.5 bps plus commission) and
  whose first live paper session is tomorrow morning.
- **Decision: refused. `vwap_trend` alloc stays 0 and `live/intraday_config.json` is not
  touched.** Rule (c) asks for OOS improvement and the fade does deliver that, but OOS
  improvement bought by an equal IS loss is the same regime rotation A-2 documented on the ORB
  stop, and here the two-half total does not move at all. Paying 25% more turnover for a
  measured zero is not a trade worth making the day before the sleeve goes live.
- **A-1 is closed.** The module is not deleted: the trend filter repaired it from -56%/yr to
  break-even, which is a genuine finding about *why* VWAP fading loses on these names, and all
  five levers ship in the module defaulted off with the control reproducing A-6 exactly. It
  stays available for A-5 to reconsider once measured live slippage replaces the estimate, or
  for a future allocator with a real regime signal - but it earns no capital on this evidence.
- **Next.** A-7: the daily loss limit and the per-symbol cap. A-2 and A-1 have now both
  measured that signal-level levers cannot move this sleeve's tail or its turnover economics,
  which leaves the framework constants in `scripts/intraday_common.py` as the untested surface.
  Any change there needs a replay per AGENTS.md rule (a).

## 2026-09-09 - Paper session 2026-09-09 (ops close)

End-of-day operations check. The daily sleeve rebalanced and filled; the intraday sleeve did
**not** run a live session today - the paper deploy date for it is 2026-09-10, and everything
in `live/log/intraday-2026-09-09.jsonl` is research replay plus two short dry-run launches.

| sleeve | trades | P&L | costs | worst event |
| --- | --- | --- | --- | --- |
| daily (`s1_momo`) | 3 fills (TQQQ 3700, XLE 7333, XLK 2616, all BUY MKT, all Filled) | -497.79 unrealised at 15:50 ET | not itemised in the log; slippage vs stale ref prices: XLE +0.96%, TQQQ -0.93%, XLK -0.01% | 4x `connect_failed` to 127.0.0.1:4002 between 09:38 and 09:46 ET (IB Gateway not yet up); the 15:45 run connected first try |
| intraday (`active`) | 0 live trades | 0 | 0 | 2 dry-run launches (11:08, 11:12 ET) ran ~7 min and were stopped; no `end` event, no live snapshot, no fills |

- **Daily rebalance, 15:45 ET.** Plan `s1_momo` as-of 2026-09-08, regime risk-on (vol 0.0832 vs
  median 0.127), winners XLE/XLK/QQQ, vol_scale 1.31, gross weight 1.2331, effective exposure
  1.7669. Targets XLE 0.4748, XLK 0.4913, TQQQ 0.2669 on net liq 1,000,344.32. Three market
  orders sent at 19:45:07-08 UTC, all filled by 19:46:38 UTC: TQQQ 3700 @ 71.49, XLE 7333 @
  65.39, XLK 2616 @ 187.8508. Post-trade gross position value 1,235,006.07 (1.23x net liq),
  cash -235,503.86, available funds 558,561.03, unrealised -497.79.
- **Intraday sleeve.** No live session. Preflight/replay ran repeatedly over 2026-09-04 and
  2026-09-08 (the last replay of 09-08 ends -5,271 P&L, 40 trades, 854 costs - research, not
  the paper book). Two `start` events today both carry `dry_run: true`. One `stale_book` event
  at 11:08 ET reported a leftover book (NVDA -667, AAPL -478, MSFT 202) from an earlier dry
  run; the 11:12 relaunch logged `ignored_book_file` and discarded it. `feed_probe` measured
  IB delayed quotes at 14.0 minutes, as expected on the paper data subscription.
- **Flat check.** `live/state/intraday_book.json` does not exist and the broker account holds
  only daily-sleeve names (XLK, XLE, TQQQ) - no intraday universe symbols. The sleeve is flat;
  no `--flatten` was required or run.
- **Loss limit / halt / error events.** None in either log today.
- **Open item.** `notify_failed` at 10:06 ET: Telegram bot token missing, so the daily plan
  notification did not send. Ops-only, does not affect trading.
- **Next.** Tomorrow is the intraday sleeve's first scheduled live paper session (09:25 ET task).
  Verify the preflight replay passes and that the launch is not `--dry-run`.

## 2026-09-09 - A-2: ORB tail control. The tail does not come off for free; what the stop does is rotate return between regimes

- **What.** Nine variants of `algorithms/intraday/orb/signal.py` on the 9-month store, fixed
  window 2025-12-15..2026-09-08 (the 09-09 session is still in progress), split 2026-06-15,
  124 IS / 59 OOS sessions. The module was rewritten to carry the levers as parameters, all
  defaulted to the shipped behaviour: `stop` ("mid" | "atr") with `stop_atr`, `range_minutes`,
  `scale_out`/`scale_r`/`scale_breakeven`, and `disaster_atr` (an ATR backstop *on top of* the
  midpoint stop, whichever triggers first). The refactor is exact: the control run reproduces
  the A-6 in-sample cell to the digit - 16.225% net, 4,359 trades, 35.739% CAR.
- **Why.** Top backlog item. ORB is positive in both halves but its worst days (-34k, -26k)
  are what trip the framework's 2.5% daily loss limit 3-4 times per half, and A-6 named those
  days as the sleeve's tail risk.

### The frontier (ORB standalone, annualized after costs, IS -> OOS)

| stop | IS CAR / Sharpe | OOS CAR / Sharpe | worst day IS / OOS | loss-limit days |
| --- | --- | --- | --- | --- |
| midpoint (shipped) | 35.7 / 1.31 | 10.7 / 0.51 | -33.9k / -26.4k | 3 / 4 |
| + 8x ATR backstop | 35.3 / 1.30 | 10.9 / 0.52 | -33.8k / -26.4k | 3 / 4 |
| + 6x ATR backstop | 34.7 / 1.27 | 13.3 / 0.60 | -33.4k / -26.2k | 3 / 3 |
| **+ 4x ATR backstop** | **31.4 / 1.19** | **19.3 / 0.80** | **-30.5k / -26.0k** | **3 / 4** |
| + 3x ATR backstop | 21.5 / 0.88 | 26.5 / 1.04 | -31.9k / -27.1k | 4 / 3 |
| pure 3.0x ATR | 25.1 / 0.99 | 19.8 / 0.83 | -32.6k / -26.7k | 4 / 3 |
| pure 1.5x ATR | -12.3 / -0.51 | 43.1 / 1.65 | -25.0k / -22.9k | 1 / 0 |
| pure 1.0x ATR | -0.3 / 0.08 | 36.8 / 1.56 | -21.4k / -18.0k | 0 / 0 |

- **The hypothesis as written is refused.** No variant cuts the tail while keeping the return.
  The tail only comes off materially at a *tight* stop - 1.0x ATR14 takes the worst day from
  -33.9k to -21.4k and the loss-limit days to zero in both halves - and that same stop takes
  the in-sample return to zero. Read across the table and the response is **monotone in the
  stop distance**: tightening does not create return, it moves it from the first half of the
  sample to the second. The mean of the two halves is roughly conserved (23% at the midpoint
  stop, 25% at 4x, 24% at 3x, 15% at 1.5x). That is a regime property, not an edge, and it is
  the same shape that got the VWAP fade removed in A-6 - only this time both ends stay
  positive over the window as a whole.
- **The other three levers all lose outright.** Scale-out of 50% at 1.5R with a breakeven stop:
  IS 24.8 / OOS 8.0, worse in both halves at the same worst day (it clips the best days,
  86k -> 60k, and the tail is not where it acts). A 30-minute opening range: 15.9 / -1.1.
  Volume filter at 1.6x instead of 1.2x: 15.0 / -9.8. All are worse than the control in both
  halves; none is carried forward.

### What shipped, and what it is worth

`disaster_atr = 4.0` on the ORB sub-strategy in `live/intraday_config.json`. At the sleeve
level (ORB 1.0 + late fade 1.0, per-symbol 0.15, gross 1.5, same window and split):

| mix | IS CAR / Sharpe | OOS CAR / Sharpe | worst day | loss-limit days |
| --- | --- | --- | --- | --- |
| deployed (no backstop) | 27.2 / 1.10 | 36.2 / 1.24 | -31.4k / -26.9k | 4 / 5 |
| + 4x ATR backstop | 24.2 / 1.01 | 55.3 / 1.73 | -30.3k / -26.9k | 4 / 4 |

- **Decision: ship it, with the reason stated plainly.** It satisfies AGENTS.md rule (c) - OOS
  improves, +19 points of CAR and +0.49 of Sharpe - both halves stay positive, the worst day
  is no worse, one loss-limit day comes off, and total P&L over the 183 sessions rises from
  $201k to $221k. It sits on a shelf, not a spike: 8x is indistinguishable from off, and 6x,
  4x and 3x walk the frontier smoothly, so 4x is a point on a monotone response rather than an
  argmax found by search. The mechanism is defensible before the fact - a breakout entered at
  the extreme of an unusually wide range has its midpoint stop very far away, and the backstop
  caps exactly those trades - which is why the 8x cell changes nothing (it almost never binds).
  **What it is not** is a free improvement: the in-sample half pays 3 points of CAR and 0.09
  of Sharpe for it, and if the next quarter looks like the first half of this sample rather
  than the second, this change will have cost money. Replay of 2026-09-08 with the deployed
  config passed before it was written (46 trades, flat at the close, -4,881 P&L on the day).
- **Next.** A-1 (make the VWAP fade pay on the long window, or retire the module). The tail
  itself is now a *framework* question rather than a signal one: the loss-limit days survive
  every signal-level control tried here, so the lever that actually bounds them is the 2.5%
  daily limit and the per-symbol cap, and sweeping those is A-7.

## 2026-09-09 - A-6: the deployed mix re-derived on 9 months (2025-12-15..2026-09-09, split 2026-06-15)

- **What.** With the minute store extended to 184 sessions per name, every strategy and both
  candidate mixes were re-run on a fixed window with a 124/60-session split.
- **Result (annualized after costs, IS -> OOS).** Late-day fade -4.5% (Sharpe -0.76) ->
  +26.4% (5.20): regime-dependent, carried by the last three months. VWAP fade (30/8/15)
  -56.0% (-3.26, 22 loss-limit days) -> -7.2%: **the A-0 out-of-sample number was a
  one-month regime, not an edge; removed.** ORB +35.7% (1.31) -> +8.2% (0.43): positive both
  halves, 34 trades/day, worst days -34k/-26k, 3-4 loss-limit days. Gap fade -4% both halves:
  dropped. The A-0 deployed mix (with VWAP fade) -18.0% -> +53.9%: fails the both-halves rule.
  ORB 0.5 + late fade 1.0: +11.8% (0.89) -> +34.6% (2.03), 46 trades/day, std ~9k.
  **ORB 1.0 + late fade 1.0: +27.2% (1.10) -> +32.6% (1.15), 46-49 trades/day, daily P&L
  std ~17k, best +77k, worst -31k, 4-5 loss-limit days per half, costs ~1k/day.**
- **Decision.** Deploy ORB 1.0 + late-day fade 1.0, VWAP fade 0, per-symbol 0.15, gross 1.5
  (`live/intraday_config.json`). It is the only candidate positive in both halves that also
  delivers the owner's volatility mandate (~27% annualized vol on the sleeve). The
  breakout's worst days are the sleeve's tail risk; the framework's 2.5% daily loss limit is
  what bounds them and it will fire roughly one day in twelve.
- **Next.** A-2 (ORB tail control: ATR stop, scale-out) and A-1 (make a VWAP fade pay on the
  long window, or retire it). Measure the sleeve's correlation with the daily champion from
  paper logs. Replay of 2026-09-08 with the final config passed before deployment.

## 2026-09-09 - A-0: the intraday active sleeve, first evidence and the deployed mix

- **What.** Built the intraday sleeve end to end (see AGENTS.md "The intraday active sleeve"):
  16-name disjoint universe, IBKR 1-minute store (`data/minute`, 3 months, being extended to
  9), causal features, four strategies (ORB, VWAP trend, late-day momentum, gap fade), a
  minute backtester with 1.5 bps slippage + IBKR commission, and a live trader with an offline
  replay. Deployed via the 09:25 ET task with a replay preflight.
- **Why.** Owner mandate: a volatile, high-turnover book on most of the capital by the
  2026-09-10 open. The daily champion runs ~16% vol; this sleeve is where the turnover lives.
- **Result (16 names, fixed window 2026-06-11..2026-09-09, split 2026-08-15, after costs).**
  Trend-following loses *before* costs at the 1-minute horizon: VWAP trend -82%/yr IS,
  -89%/yr OOS at ~150 trades/day; late-day momentum -25%/yr IS, -29%/yr OOS with 29% winning
  days. Their inverses are the edge: **late-day fade** +18%/yr Sharpe 2.9 IS, +25%/yr Sharpe
  8.2 OOS, 11 trades/day, worst day -1.7k OOS; **VWAP fade** (30 bps band, 8 bps exit,
  15-bar momentum) +124%/yr Sharpe 4.2 OOS at ~100 trades/day, but negative over the longer
  (unstable, extension-in-progress) in-sample window, so it is a regime bet. ORB is ~0 IS,
  +14%/yr OOS. Gap fade fails OOS (-31%/yr).
- **Deployed mix** (`live/intraday_config.json`): late fade x1.0, VWAP fade x0.5, ORB x0.5,
  per-symbol 0.15, gross 1.5. Fixed-window result: IS +22.6%/yr Sharpe 1.31 (45 sessions,
  1 loss-limit day, worst -27k), OOS +119%/yr Sharpe 9.5 (17 sessions, worst -7.6k), 133-146
  trades/day, turnover ~8x equity/day, costs ~$1.6k/day, daily P&L std $5-10k. The
  conservative alternative without VWAP fade: IS +15.6%, OOS +35%, 45 trades/day.
- **Caveats, stated plainly.** 62 sessions is a short sample; OOS is 17 sessions. The
  in-sample counts in the ledger rows from 15:4x-16:1x UTC differ because the 9-month
  extension was writing older sessions between runs; only rows with `--start 2026-06-11` are
  comparable. IBKR quotes are 15 minutes delayed without a subscription, so the live trader
  uses the Yahoo 1-minute feed (measured real-time) until the owner subscribes; paper fills
  may still be simulated on delayed data.
- **Next.** A-6: once the 9-month store lands, re-run every strategy and the mix on the full
  window with a 2-way split; re-derive the deployed mix from that; measure the sleeve's
  correlation with the daily champion; then A-1/A-2 refinements.

## 2026-09-09 - D-2: intraday data, and the month boundary that ate a session a month

**Why this.** `paper_trade.py --check` was the first thing run this iteration and it now
answers - account `DUT091359`, net liquidation $1,000,344, no positions. The 10141 disclaimer
has been accepted, so the IB API is open for the first time and **D-2 is the top open item**,
exactly as the backlog said it would be. Everything the owner decided yesterday routes through
it: volatility is to be earned with a second, uncorrelated intraday sleeve (S-2), and S-2 has
never had a bar to test on because Yahoo caps 1-minute history at ~30 days.

**What was built.** `scripts/fetch_minute.py`: IBKR `reqHistoricalData` at `1 min` /
`TRADES` / `useRTH=True`, written as LEAN minute files
(`equity/usa/minute/<sym>/<yyyyMMdd>_trade.zip` -> `<yyyyMMdd>_<sym>_minute_trade.csv`,
`<ms since midnight ET>,o,h,l,c,v`, prices x10000), reusing `fetch_data.py`'s
writer/validator shape. Three properties it needed and has: a sliding-window pacer for
IBKR's 60-requests-per-10-minutes rule, resumability by month chunk (an interrupted
backfill restarts by re-running the same command), and `clientId` 31, clear of the paper
runner's 17. Prices are raw; dividends stay in the D-1 factor files, as at every other
resolution.

**The bug worth recording.** The obvious chunking - `durationStr="1 M"` ending at 23:59 on
the month's last day - is wrong, and wrong *silently*. IBKR measures a duration backwards
from `endDateTime`, so a 1-month window ending 23:59 on 31 July begins 23:59 on 1 July,
which is **after that session's close**. The first session of every month is dropped. The
smoke run made it visible - 21 sessions for July 2026 when the daily file says 22, one
missing date, `20260701` - and at scale that is ~5% of the sample gone, in a shape that
looks like nothing: the bar counts are all exactly 390, every session that is present is
complete, and only a cross-check against an independent trading calendar shows the hole.
Fixed by requesting `5 W` (35 days, four days of slack on the longest month) and filtering
the overlap back to the chunk, so a session is still written exactly once. Re-run: 22
sessions for July, 0 missing.

**Result - SPY 2020-01-02 .. 2026-09-08 complete.**

| | |
| --- | --- |
| sessions | **1,679**, 0 missing against the daily calendar, 0 truncated |
| bars | **652,650** (mean 388.7/session; 12 half days at 210) |
| clamped bars | 0 |
| close vs D-1 daily, median | **0.007%** |
| close vs D-1 daily, worst | 0.957% (2025-04-09) |
| on disk | 14 MB |

**The acceptance test is a LEAN run, not a file check**, because D-1's worst bug was a file
that passed every structural check and made LEAN return *zero bars* with no error.
`algorithms/d2_minute_smoke` streams the whole backfill at minute resolution and asserts
seven properties: run `20260909T160005Z`, **all seven PASS**. LEAN sees 652,650 bars over
1,679 sessions - bit-identical to what the writer counted, so nothing was silently dropped -
every session opens at 09:31 and closes at 16:00 (1,667) or 13:00 (12 half days), no
inconsistent OHLC, 65 zero-volume bars out of 652,650. `evaluate.py` correctly refuses it:
0 orders, and it is tagged `not promotable`. Champion unchanged at S-12.

**The close deviation is real and is not a data error.** The six sessions deviating more
than 0.2% are 2020-03-13/17/18/19/23/24 and 2025-04-03/09 - the COVID crash and the April
2025 tariff selloff. On violent days the closing auction clears away from the last 1-minute
RTH trade, and the daily close is the auction print while the minute file's last bar is not.
**This is a design constraint for S-2, not a defect**: a sleeve that flattens at the close
must model the 16:00 auction, and assuming the 15:59 bar's close is a fill price will book
up to ~1% of free P&L on exactly the days an intraday strategy makes its money.

**Decision.** No promotion - D-2 is infrastructure. SPY is complete and validated end to end,
so **S-2 is unblocked on its primary instrument** and is the next item.

**Cost, honestly.** IBKR serves ~260-790 bars/s, so this is slow: one symbol-decade is
~40 minutes of wall clock and the full five-symbol set is a multi-hour job. That is why the
script is resumable by month, and why only SPY was taken to completion in one iteration.
QQQ, IWM, TQQQ and SQQQ are one command each (`--symbols QQQ --start 2020-01-01`) and are
the first thing to run in the background of the next iteration.

**Next.** S-2 opening-range breakout on SPY minute bars, judged on the same IS/OOS split and
promotion rules, with its correlation to the champion's daily returns as a first-class metric.

## 2026-09-09 - I-1: the paper runner would have placed twice the backtest's orders

**Why this and not a backtest.** Port 4002 answered at the top of this iteration for the
first time - Gateway is up and logged in - so I-1 became the top open item and I took it
instead of another sleeve experiment. It got exactly one step further before stopping:

```
Error 10141, reqId -1: Paper trading disclaimer must first be accepted for API connection.
```

A one-time acknowledgement inside Gateway's GUI, confirmed not to be a stale API session
(same error on a fresh `--client-id 91`). That is the human's click and is already filed;
the sibling review job filed the same finding independently this morning. So the question
became: **what part of I-1 can be finished today, with no connection?**

The answer is its last unbuilt piece. I-1's checklist ends with "compare the runner's order
list with what the LEAN backtest would have done on the same date" - the gate that decides
whether the thing about to trade real-shaped orders is the thing that was validated. It had
never been built, and it does not actually need IB.

**Hypothesis.** The signal cannot diverge - `signals.py` is imported by both LEAN and the
runner, which was the whole point of splitting it out in S-1. But *everything downstream of
the signal is duplicated*: `main.py:submit_targets` and `paper_trade.py:plan_orders` are two
independent implementations of "turn target weights into integer share deltas and drop the
ones too small to bother with". Nothing had ever compared them. Two implementations of one
rule, written weeks apart, are where I expected to find a divergence.

**Method.** `scripts/compare_orders.py` walks LEAN's own daily bars with the shipped
champion signal, maintains a share-level book the way `submit_targets` does, and at every
decision date hands *identical* inputs - same targets, same positions, same prices, same
equity - to both implementations, then diffs the two order lists. Because the inputs are
identical by construction, a difference cannot be a data or signal artifact; it can only be
the execution layer. It imports `plan_orders` from `paper_trade.py` rather than copying it,
so it tests the code that will actually trade, and it exits non-zero on any disagreement so
the deploy checklist can gate on it.

### Result: the runner and the backtest did not agree, and it was not close

| | decision dates | agreement | orders placed |
| --- | --- | --- | --- |
| **before** | 3,689 | **1,350 (36.6%)** | LEAN 4,653 / runner **9,196** (+98%) |
| **after** | 3,689 | **3,689 (100.0%)** | LEAN 4,653 / runner 4,653 (+0) |

**One cause, all 4,543 of them: `MIN_NOTIONAL = 200.0`.** The backtest bands orders at a
*fraction of equity* (`min_order_value = 0.01`); the runner banded at a *flat $200*. On the
$100k paper account those are $1,000 and $200 - a 5x tighter band - and the gap widens with
every dollar the book compounds, because LEAN's band grows to $24,000 by the end of the
sample while the runner's stays at $200. Every disagreement was the same shape and the same
sign: the runner sending a small drift adjustment the backtest bands out. Nothing subtle,
nothing offsetting, and it would have been invisible on the first day's trade (from flat,
all three orders are tens of thousands of dollars and clear both bands identically) and then
compounded silently from the second rebalance onward.

**What makes this more than a tidy-up is S-13, last night.** S-13 measured that ~63% of the
champion's orders are return-neutral - they buy nothing in backtest and cost a spread live -
and concluded the *research* question was closed. This is the same population of orders seen
from the execution side: the runner's tight band was about to opt the paper account into
roughly 4,500 extra small orders a decade, precisely the ones S-13 showed have no return in
them. The backtest would have looked fine and the paper account would have quietly
underperformed it on fills, which is the specific failure mode a paper stage exists to catch
and the hardest one to diagnose after the fact.

**Fix.** `plan_orders` now bands at `max(MIN_NOTIONAL, MIN_ORDER_VALUE * net_liq)` with
`MIN_ORDER_VALUE = 0.01` tracking `main.py`, and uses the same `max(px, 0.01)` notional. The
$200 survives only as an absolute floor for a small account, where it binds below ~$20k of
net liquidation; at the paper account's size the fraction dominates and the two agree
exactly. Both constants now carry a comment saying they must move together.

**Guarding against a test that passes for the wrong reason.** Re-run with
`--min-order-value 0.02`, i.e. a deliberately mismatched pair, and the gate fails with 442
divergent orders and exit code 1; at the matched value it exits 0. So it discriminates.

- **Decision. No promotion and no champion change** - and nothing under `algorithms/` was
  touched, so `OrderListHash 5246804e17a67af90028ffceead7d3b3` is unchanged by construction
  and needs no rebaselining run. What shipped is `scripts/compare_orders.py` (new) and a
  one-line band fix plus documentation in `scripts/paper_trade.py`. `--mock --dry-run`
  re-verified after the fix: unchanged 1.23x gross, margin 0.75, XLE/XLK/TQQQ - correctly,
  since from flat every order clears both bands.
- **Next.** The click is the whole critical path. The moment 10141 clears: `--check`,
  `--dry-run` against the real account, re-run `compare_orders.py`, then stop at
  `live/APPROVED_PAPER.md`, which is the human's. If it has not cleared by the next
  iteration, the honest offline work is the other half of this same audit - the runner and
  the backtest also disagree about *where prices come from* (yfinance `auto_adjust` against
  LEAN's adjusted bars), and that is measurable today with the same harness, without IB.


## 2026-09-09 - S-13: the execution band buys nothing and costs nothing, and that is the result

**Hypothesis.** S-12 bought 0.8 points of CAR by re-weighting the book as vol ratios drift,
and paid for it with 84% more orders (2,573 -> 4,735) and $8.3k more commission. Those extra
orders are by construction *small* - they are drift adjustments, not rotations. The execution
layer already has a no-trade band for exactly this, `min_order_value`, which skips any delta
worth less than that fraction of equity - and it has been pinned at 0.01 since S-1 and **never
swept**. If most of S-12's cost sits just above a 1% band, widening it should hand back the
commission and keep the risk-parity gain. Cheap to test: the knob is already wired to
`S1_MIN_ORDER_VALUE`, so no code changed and no control run was needed - the champion run
`20260909T042431Z` *is* the 0.01 cell.

### Result (LEAN, full period 2012-01-03 .. 2026-09-04, S-12 champion signal throughout)

| band | CAR | Sharpe | MaxDD | orders | fees |
| --- | --- | --- | --- | --- | --- |
| **0.01 (champion)** | 24.40% | **0.921** | **25.1%** | 4,735 | $45,695 |
| 0.015 | 24.35% | 0.919 | 26.9% | 3,887 | $44,239 |
| 0.02 | **24.54%** | **0.927** | 25.2% | 3,355 | $43,960 |
| 0.03 | 24.34% | 0.917 | 25.5% | 2,737 | $42,329 |
| 0.05 | 23.92% | 0.900 | 29.2% | 2,112 | $39,729 |
| 0.08 | 24.47% | 0.920 | 25.4% | 1,727 | $39,568 |

**The response is non-monotone and essentially flat.** Across a factor of eight in the band -
and a factor of 2.7 in order count - CAR walks 24.40, 24.35, 24.54, 24.34, 23.92, 24.47 and
Sharpe walks 0.921, 0.919, 0.927, 0.917, 0.900, 0.920. There is no trend, in either direction.
The one cell that visibly deviates, 0.05, deviates in *drawdown* (29.2%, four points wide of
every other cell) with no mechanism that explains why a 5% threshold should be worse than both
a 3% and an 8% one. That is the signature of path dependence: the band changes *which day* a
rebalance fires, and a different fill date reshuffles the entire subsequent equity path.

**So the honest reading is not "0.02 wins".** 0.02 does beat the champion on both `must_beat`
metrics at a 25.2% drawdown, and `scripts/evaluate.py --candidate 20260909T043527Z` returns
**BEATS champion**. Its sub-periods even agree in sign - IS 2012-2019 19.32% / 0.891 / 25.2%
against the champion's 19.18% / 0.884 / 25.1%, OOS 2020-2026 30.98% / 0.988 / 22.7% against
30.86% / 0.985 / 22.6%. **It was refused anyway**, on the shelf-not-spike rule that promoted
S-9, S-10 and S-12: both of 0.02's neighbours *lose* to the champion, so there is no shelf and
no dose-response, and the whole 0.01-0.03 region scatters by +/-0.1 points of CAR with 0.02's
margin (+0.14) sitting inside that scatter. Promoting it would be fitting an execution
threshold to path luck, which is the specific thing `AGENTS.md` says to fight. Both sub-periods
agreeing is worth less than it looks here: at +0.11 and +0.14 points they are two draws from
the same scatter, not independent confirmation.

**What the flatness is actually worth, which is more than a promotion would have been.**
Turnover between 1,727 and 4,735 orders is *return-neutral*. About 3,000 of the champion's
orders - 63% of them - buy nothing at all. In the backtest that costs only the $6.1k of
commission the 0.08 cell saves, which is why no cell wins: LEAN charges commission and the
fee difference is too small to move a 24% CAR. **Live it is not neutral**, because every one
of those orders also crosses a spread that the backtest does not model at all. S-3 measured
the commission floor at 2.1bps per unit of turnover; a half-spread on a liquid 3x ETF is of
the same order, so the true saving from the wide band is plausibly around double the modelled
$6.1k - and, more importantly, 63% fewer chances for a real fill to come back worse than the
close the signal decided on.

That makes the band a **live-execution decision rather than a research one**, and it is not
the loop's call to make three days before a paper deploy: switching to 0.08 would move the
order list and invalidate the `OrderListHash` I-1's pre-deploy comparison is built on, in
exchange for a backtest improvement of exactly zero. Filed for the human instead.

- **Decision. No promotion; the champion is unchanged at S-12.** No parameter shipped -
  `min_order_value` stays 0.01, the signal is untouched, and `OrderListHash
  5246804e17a67af90028ffceead7d3b3` still stands, so I-1 needs no rebaselining. The six-cell
  curve is recorded in `main.py` next to the parameter so a later session does not re-fit it,
  and the wide-band option is a one-line question in `BLOCKERS.md`.
- **Next.** This is the second iteration running (with S-11) to find that the champion's
  turnover cannot be converted into return, and now also that it cannot be *removed* for
  return - the sleeve is simply insensitive to execution timing at this frequency. Combined
  with S-12 spending the allocation step, the ETF-9 sleeve is out of cheap levers by
  measurement rather than by assumption. Ports 4002 and 7497 were checked again at the top of
  this iteration and are both still closed, so S-2 (a second sleeve), D-2 (intraday data) and
  the I-1 paper deploy all remain behind the IB Gateway login, and that login is now the only
  thing standing between this repo and its 2026-09-10 deadline.

## 2026-09-09 - S-12: risk parity inside the top 3, new champion at 24.4% / 0.92

**Hypothesis.** Every iteration since S-6 has changed *what* the signal picks (S-9's fourth
horizon, S-10's skip) or *whether* it re-picks (S-11's whipsaw controls). Nothing has touched
the last step: once momentum has chosen three names, the exposure budget is split 1/N between
them. Equal weight equalizes *notional*, not risk, and this sleeve is not homogeneous - GLD and
TLT run near 12% annualized vol while XLE and XLK run near 30%. So on any day the book holds a
quiet name and a violent one, the violent one supplies most of the variance and the quiet one is
close to decoration. **Weighting each winner by 1/sigma on its own trailing vol should raise
Sharpe**, and it should be nearly free in rotation turnover, because vol ratios move far more
slowly than rankings do.

Two implementation notes. The vol is measured on the **unlevered ranked series**, not on the
3x proxy actually traded, because the sizing step already divides by the proxy's leverage
multiple - the share being split is unlevered-equivalent exposure, so it has to be equalized
against unlevered-equivalent risk. And the tilt is a *dial*, not a mode: shares are
`(1/sigma) ** alloc_vol_power`, so power 0 is exactly equal weight and 0.5 is half the tilt.
That is what makes a dose-response test possible, which is the check that separates an effect
from a lucky cell.

**Control first.** LEAN run `20260909T034600Z` at the defaults reproduces
`OrderListHash ff4a7cbaaf6e36e58ace2b82ab216bdf` bit for bit, so the new code is provably inert
until it is switched on.

### Result (LEAN, full period 2012-01-03 .. 2026-09-04, power 1.0 unless stated)

| cell | CAR | Sharpe | MaxDD | orders | fees | PSR |
| --- | --- | --- | --- | --- | --- | --- |
| S-10 champion (equal weight) | 23.61% | 0.874 | 25.9% | 2,573 | $37,380 | 17.7% |
| invvol window 10 | 22.77% | 0.857 | 29.4% | 6,318 | $50,184 | 16.2% |
| invvol window 20 | 24.25% | 0.915 | 25.4% | 4,768 | $45,982 | 22.3% |
| **invvol window 21 (shipped)** | **24.40%** | **0.921** | **25.1%** | 4,735 | $45,695 | **23.0%** |
| invvol window 30 | 24.18% | 0.911 | 25.1% | 4,102 | $42,997 | 21.8% |
| invvol window 40 | 23.74% | 0.893 | 27.4% | 3,644 | $40,034 | 19.8% |
| invvol window 60 | 23.40% | 0.879 | 25.5% | 3,239 | $39,162 | 18.4% |
| invvol window 21, power 0.5 | 24.10% | 0.902 | 25.1% | 3,680 | $41,186 | 20.8% |

**It is a shelf, not a spike, in both dimensions.** Across the vol window, 20/21/30 all beat
the champion on CAR, Sharpe *and* drawdown; 40 and 60 still beat it on Sharpe and drawdown but
give the CAR back as the tilt decays toward equal weight; 10 loses outright, which is what a
vol estimate made of noise should do. Across the tilt strength, half the power buys half the
gain (0.902 sits almost exactly between 0.874 and 0.921). A fitted cell does not have a
dose-response curve. **21 sessions is one trading month**, the a-priori point inside the
20-30 shelf; 20 is the argmax and is not what shipped, on the same rule S-9 and S-10 used.

**Sub-periods.** IS 2012-2019 **19.18% / 0.884 / 25.1%** against the champion's
17.64% / 0.801 / 25.9% - ahead on all three. OOS 2020-2026 **30.86% / 0.985 / 22.6%** against
31.09% / 0.972 / 21.5% - ahead on Sharpe, 0.23 points of CAR behind, 1.1 points of drawdown
worse. So the gain is concentrated in the in-sample half, and the out-of-sample half is a
wash. That is the same shape S-11 found for its whipsaw controls, and it is worth naming: the
2012-2019 half is the one that holds mixed baskets of quiet and violent names, and the
2020-2026 half is more often three correlated risk-on names at once, where 1/sigma and 1/N
are nearly the same weights.

**What it costs.** 84% more orders (2,573 -> 4,735) and $8.3k more commission, because the vol
ratios drift daily and the book re-weights between rotations. At S-3's measured 2.1bps cost
floor that is a real bill, and it is paid for here - 0.8 points of CAR and 0.047 of Sharpe
after fees - but it means the honest fallback if commission ever rises is a longer window
(30 keeps most of the gain for 633 fewer orders) rather than a smaller tilt.

**Harness agreement.** Unlike S-10, `sweep_s1.py` agreed on the *direction* - it scored the
shipped cell 22.1% / 1.09 against a 21.2% / 1.03 equal-weight baseline - but it understated the
size of the win and, as in every previous iteration, understated drawdown by about 6 points.
It also flagged window 20 as an isolated spike where LEAN sees a 20-30 shelf, so the sweep
remains a candidate generator only.

- **Decision. Promoted through `scripts/evaluate.py`** (run `20260909T042431Z`, 4,735 orders,
  drawdown 25.1% < 35%, beats the champion on both `must_beat` metrics). The shipped default
  is `weight_mode="invvol"`, `alloc_vol_window=21`, `alloc_vol_power=1.0`; `S1_WEIGHT_MODE=equal`
  restores S-10. New order list **`OrderListHash 5246804e17a67af90028ffceead7d3b3`**, and the
  I-1 pre-deploy comparison must now be made against that hash. `scripts/paper_trade.py
  --mock --dry-run` was re-verified against the new signal and reports the tilt in its
  diagnostics (`alloc_vols`).
- **Next.** The allocation step is now spent as an idea: momentum picks, risk parity sizes, and
  the levers left inside a three-name book (correlation-aware weights, an ex-ante covariance
  target) need more sleeve breadth than nine ETFs to bite. The two things that can still move
  return materially are a second uncorrelated sleeve (S-2) and intraday data (D-2), and both,
  like the I-1 paper deploy, wait on the IB Gateway login - checked again at the top of this
  iteration, ports 4002 and 7497 are both still closed.

## 2026-09-08 - S-11: the whipsaw is real, and suppressing it buys drawdown, not return

**Hypothesis.** S-10's calendar decomposition said the champion's losses are not crises and
not the out-of-sample half - they are 2014/2015/2016 and 2024, and the worst drawdown is a
16-month grind from 2015-07-20 - which is the signature of a ranking that rotates into
whichever sleeve member has just topped out. Three levers, all defaulted off, all of which
also cut turnover (the direction S-3's 2.1bps cost floor rewards): (a) **hysteresis** - an
incumbent's score is credited with `hysteresis` *cross-sectional standard deviations* of the
day's scores before the ranking is cut at `top_n`; (b) **min_hold** - a funded name keeps its
slot for N more decisions unless the entry gate itself refuses it; (c) **rank_persist** - a
name not already held must have led for k consecutive bars before it is funded.

Two implementation notes worth keeping. The hysteresis margin is measured in the day's own
score dispersion, not in return: the blended score is a mean of raw returns whose scale moves
by an order of magnitude between 2017 and 2020, so a fixed return margin would be inert in
one regime and binding in the other. And `rank_persist` is computed by **re-scoring truncated
price windows** rather than from remembered rankings, so it stays stateless and the I-1 paper
runner reproduces it from prices alone; (a) and (b) do need memory, and it rides in the
existing `state` dict (`held`, `held_age`) that the runner already persists. `drawdown_multiplier`
rebuilds that dict from scratch, so the incumbent set is read before it is called and written
back after - and every early return (risk-off, drawdown-flat, no winners, all stopped) leaves
`held` empty, because each of those is a decision to sit in cash and must not leave a phantom
incumbent to defend.

**Control first.** LEAN run `20260909T024906Z` at the defaults reproduces
`OrderListHash ff4a7cbaaf6e36e58ace2b82ab216bdf` bit for bit, so the plumbing is provably inert.

### Result (LEAN, full period 2012-01-03 .. 2026-09-04)

| cell | CAR | Sharpe | MaxDD | orders | fees |
| --- | --- | --- | --- | --- | --- |
| champion (control) | **23.61%** | **0.874** | 25.9% | 2,573 | $37,380 |
| (a) hysteresis 0.05 sigma | 23.57% | 0.873 | 24.6% | 2,200 | $29,562 |
| (a) hysteresis 0.10 sigma | 23.12% | 0.858 | 23.8% | 1,998 | $25,673 |
| (a) hysteresis 0.20 sigma | 22.34% | 0.827 | 23.5% | 1,832 | $22,729 |
| (b) min_hold 10 | 23.15% | 0.860 | **22.8%** | 1,901 | $27,194 |
| (c) rank_persist 2 | 22.77% | 0.832 | 21.6% | 2,727 | $46,345 |

**The champion's rotation is not noise.** Every device that refuses a rank crossing takes
return with it, monotonically in the strength of the refusal: the frontier slides along, it
does not move up. Nothing here beats the champion on both CAR and Sharpe, and `evaluate.py`
refuses the best of them on exactly that (`Sharpe 0.873 does not beat 0.874`,
`CAR 23.568% does not beat 23.605%`).

**But the exchange rate is cheap in drawdown terms**, which matters because S-8 established
that drawdown, not vol, is what binds this book's size. `min_hold=10` gives up 0.45 points of
CAR and buys 3.1 points of drawdown and $10k of fees; hysteresis at 0.05 sigma gives up 0.04
points of CAR - a rounding error - for 1.3 points of drawdown, 373 fewer orders and $7.8k less
commission. Sub-periods on that cell say the gain lands exactly where S-10 diagnosed the
problem: **IS 2012-2019 17.73% / 0.806 / 24.6% beats the champion's 17.64% / 0.801 / 25.9% on
all three**, while OOS 2020-2026 30.85% / 0.965 / 21.5% is a hair behind 31.09% / 0.972 / 21.5%.
The whipsaw control fixes the whipsaw years and does nothing in the years that had no whipsaw.

**Spending the headroom on size does not recover the return.** Two frontier points:
hysteresis 0.05 + `margin_budget` 0.90 earns 25.21% CAR at 30.4% drawdown and 0.840 Sharpe;
`min_hold=10` + budget 0.85 earns **25.07% CAR at 25.7% drawdown** - matched with the champion
on drawdown, ahead by 1.47 points of CAR, cheaper by 306 orders and $2k of fees - but at 0.861
Sharpe. Return/vol is simply lower for these signals (1.30 vs 1.36), so no size setting fixes
it; the promotion rule that requires beating Sharpe *and* CAR is doing its job here rather
than getting in the way.

**Harness agreement, for the record.** The sweep and LEAN disagreed again on magnitude and on
the sign of the CAR effect (the sweep scored hysteresis 0.05 at 21.8% CAR / 1.06 against a
21.2% / 1.03 control, i.e. a clear win; LEAN says a hair worse) but they agreed on the two
things that decided the iteration: the drawdown improvement, and the fact that `rank_persist`
*raises* turnover (sweep 0.15 vs 0.13; LEAN 2,727 orders and $46k of fees against 2,573 and
$37k) because blocking an entry parks the book in cash and then buys it back.

- **Decision. No promotion; champion unchanged at S-10.** All three parameters ship defaulted
  off in `signals.py`/`main.py` (`S1_HYSTERESIS`, `S1_MIN_HOLD`, `S1_RANK_PERSIST`) with the
  measured numbers in the docstrings. S-11 closes as a *measured trade-off*, not a dead end:
  it says the champion's turnover is paid for, and it hands the human a concrete frontier
  point - 25.07% CAR at the same 25.9%-class drawdown for 0.013 of Sharpe - if the promotion
  rule's Sharpe clause is ever to be traded against the aggressive-return mandate.
- **Next.** The two things left that can move return without spending turnover are a *second*
  uncorrelated sleeve (S-5 has nothing to allocate to until S-2 exists) and intraday data
  (D-2). Both sit behind the IB Gateway login, which is also the only thing between the built
  I-1 runner and the 2026-09-10 paper deadline. That login is the binding constraint on this
  repository now, and it is in `research/BLOCKERS.md`.

## 2026-09-08 - S-10: the textbook skip-a-month is wrong, a skip-a-week is right (new champion)

**Hypothesis.** S-9 opened three follow-ups and this run answers all three on the honest
ETF-9 sleeve: (a) skip-a-month momentum - rank on returns that stop short of the recent
month, the standard 12-2 correction for short-term reversal; (b) horizon weighting - S-9 gave
four horizons an equal vote while its own shelf said the long one carries the information;
(c) why the 2012-2019 half improved so little.

**Two levers, both defaulted off, control run first.** `mom_skip` with
`mom_skip_min_lookback` (which horizons the gap applies to) and `mom_weights` (per-horizon
weights, normalized, matched to `mom_lookbacks` by position with a length guard). LEAN run
`20260909T005513Z` at the defaults reproduces `OrderListHash b763e292cb0eb9a2c81af5739188d437`,
so the plumbing is provably inert.

**Horizon weighting is rejected outright.** Every weight vector loses in the sweep, on both
halves, on the raw blend (`(1,1,1,2)` 18.7% CAR, `(1,1,1,3)` 18.9%, `(1,1,2,3)` 19.0%,
`(1,2,3,4)` 18.1%, against the champion's 21.0%) and also after standardizing the horizons
first, which is the only construction in which "equal vote" is even true (`zscore` alone
19.2%, `zscore` + `(1,1,2,4)` 19.6%). Overweighting the long horizon also *widens* drawdown,
21.1% -> 25-31%. The S-9 shelf was evidence that a 252-day horizon belongs in the blend, not
that it should outvote the others; under a raw-return blend it already dominates
arithmetically, and asking for more is asking for a slower book, not a better one.

**The skip is where the sweep and LEAN disagree in sign, and it matters.** The sweep rejects
every skip cell: skipping all horizons costs 3-4 points of CAR, and confined to
`lookbacks>=120` it decays monotonically from the control (21.0% CAR / 1.04 Sharpe) through
skip=5 (21.2% / 1.03, but drawdown 21.1% -> 31.2%) down to 16-17% at skip=25-40. Run the
same cells through LEAN and the picture inverts:

| skip (on lookbacks >= 120) | CAR | Sharpe | MaxDD | orders |
| --- | --- | --- | --- | --- |
| 0 - the S-9 champion | 20.9% | 0.782 | 28.9% | 2,870 |
| 2 | 19.8% | 0.741 | 26.0% | 2,613 |
| 3 | 23.0% | 0.859 | 20.8% | 2,555 |
| **5 (shipped)** | **23.6%** | **0.874** | **25.9%** | **2,573** |
| 8 | 23.6% | 0.872 | 21.5% | 2,449 |
| 10 | 22.7% | 0.840 | 21.9% | 2,563 |
| 15 | 19.1% | 0.702 | 27.0% | 2,681 |
| 20 - the textbook 12-2 skip | 19.6% | 0.715 | 29.4% | 2,425 |

That is a shelf over 3-10 sessions that collapses on both sides, so the effect is real but
the *textbook parameter is wrong*: on a daily-rebalanced sleeve of index ETFs the reversal
that contaminates a long-horizon momentum measure lives at a one-to-two-week horizon, not a
one-month one. 5 sessions is one trading week, the a-priori unit inside the shelf, chosen
the same way S-9 chose 252 over its 250 argmax.

**Where the skip belongs is measured, not assumed.** Applied to every horizon it loses
(19.2% / 0.704), because the 20-day horizon *is* the recent week or two and truncating it
leaves a stale signal. Confined to the 252-day horizon alone it earns 23.3% / 0.870 / 23.0% -
almost the whole gain - so the effect is a property of long-horizon momentum generally, not
of one lookback. Shipped on `lookbacks >= 120`.

**Result: promoted.** Full period CAR 20.9% -> **23.6%**, Sharpe 0.782 -> **0.874**, drawdown
28.9% -> **25.9%**, orders 2,870 -> 2,573, fees $37.3k -> $37.4k, probabilistic Sharpe 10.1%
-> 17.7%. Both halves win: IS 2012-2019 15.2%/0.70/28.9% -> **17.6%/0.80/25.9%**, OOS
2020-2026 28.0%/0.88/21.0% -> **31.1%/0.97/21.5%**. This is the second consecutive gain that
comes from the signal at *lower* turnover, which is the only kind S-3's 2.1bps cost floor
cannot tax away. `OrderListHash ff4a7cbaaf6e36e58ace2b82ab216bdf`, reproduced by the shipped
default with no environment variables. The I-1 paper runner re-verified `--mock --dry-run`
against it: 1.5x gross, margin 0.75, XLK/XLE/IWM.

**(c) The diagnostic, and where the drawdown actually lives.** Calendar-year decomposition of
the S-9 champion against SPY (sweep harness): the IS half is not uniformly weak, it is three
bad years inside a good decade - 2014 -4.9% excess, 2015 -5.9%, 2016 -11.3% - and the worst
drawdown is a single 16-month grind from 2015-07-20 to 2016-11-07. 2024 is the same failure
again (-17.0% excess). None of those are crises; the crisis-vol filter fires correctly in
2020 and 2022 (2022 is the strategy's best excess year, +33.3%). The failure mode is a
*whipsaw* market where the momentum ranking rotates the book into whichever sleeve just
topped out. That is a signal-persistence problem, not a sizing one, and it is the natural
next hypothesis - filed as S-11.

**Caveat that must not be lost.** `sweep_s1.py` and LEAN now disagree in *sign* on this
lever, not just in magnitude. Earlier calibrations (S-8: sweep understates drawdown by ~2
points at champion size; S-9: by 7.8 points) treated the sweep as a biased but monotone
ranker. It is not, at least where turnover timing matters: the sweep earns weights on the
next day's close-to-close return while LEAN fills MarketOnOpen the next morning and pays
IBKR's real fee schedule. Every future lever gets a LEAN confirmation before it is believed
or discarded - a sweep rejection is now grounds for one LEAN run, not for closing the idea.

**Next.** S-11: attack the 2015-2016 / 2024 whipsaw directly (rank persistence / minimum
holding period / hysteresis on entry and exit), judged against 23.6% / 0.874 / 25.9%.

## 2026-09-08 - S-9: the champion's momentum was too short-sighted (new champion)

**Hypothesis.** Everything since S-6 changed *size* or *universe* and none of it moved the
champion, so S-9 changed what the signal says. S-7 named two untried ideas - a second momentum
horizon scored per sleeve member, and cross-sectional ranking against the sleeve median instead
of the absolute `min_momentum` floor - and this run answers both, plus two variations, on the
honest ETF-9 sleeve with no new data and no survivorship caveat.

**Four levers, all defaulted off, control run first.** `mom_score` (`blend` | `zscore` |
`riskadj`), `mom_confirm`, `entry_mode` (`absolute` | `median`) with `min_rel_momentum`, and the
horizon set itself. LEAN run `20260908T234444Z` at the defaults reproduces
`OrderListHash 9f58b37cc2656b647ec88a5124daf02d`, so the plumbing is provably inert.

**Three of the four are rejected on the sweep** (`sweep_s1.py --mode s9`, full period, against
the champion's CAR 18.7% / Sharpe 0.97 / DD 23.2% / turnover 0.22 in that harness):

| lever | CAR | Sharpe | MaxDD | turn | verdict |
| --- | --- | --- | --- | --- | --- |
| `mom_score=zscore` (equalize horizon scale) | 17.8% | 0.94 | 22.8% | 0.26 | loses both halves |
| `mom_score=riskadj`, 60d vol | 17.6% | 0.93 | 24.4% | 0.21 | loses OOS by 2.1 pts |
| `mom_score=riskadj`, 20d vol | 19.7% | 1.03 | 21.1% | 0.22 | a ridge, see below |
| `mom_confirm` (all horizons positive) | 12.3% | 0.69 | 37.1% | 0.34 | badly worse |
| `entry=median +0%` | 17.9% | 0.94 | 23.4% | 0.22 | loses |
| `entry=median +3%` | 6.4% | 0.41 | 49.2% | 0.31 | catastrophic |

`mom_confirm` fails for a reason worth keeping: demanding agreement across horizons throws the
book out of a trend exactly when the short horizon is mid-shakeout, and it pays 55% more
turnover for the privilege. The median gate fails for the reason the parameter docstring
predicted - with `top_n=3` of nine names the top three always beat the median, so at +0% it is a
*looser* gate that keeps the book in the least-bad ETF through a decline; and asking for real
dispersion (+3%, +8%) strands it in cash through 2012-2019, which is where the -0.7% CAR and
49.2% drawdown come from.

**`riskadj` is a narrow ridge, and the ridge is the interesting part.** Its full-period Sharpe
is monotone in the vol window - 5d 0.91, 10d 0.96, 15d 1.02, 20d 1.03, 30d 0.99, 40d 0.95,
60d 0.93, 120d 0.85 - so only a 15-30 day window beats the champion at all, and it wins entirely
OOS at 15-20 and entirely IS at 30. That inconsistency is the fingerprint of noise, and the
margin (+1.0 CAR, +0.06 Sharpe) is inside the sweep's own known error. Not shipped, kept
available as `mom_score="riskadj"`.

**The fourth horizon is the real finding.** Adding a 250-day member to the blend scored CAR
22.6% / Sharpe 1.10 / DD 21.4% at *lower* turnover (0.16 vs 0.22). The first check made it look
like a fitted spike - a fourth horizon of 200 gives only 19.0%, and 300 returned a tidy 0.0%
CAR. That 0.0% was a **bug in the harness, not a result**: `history_bars` defaults to 300, and a
lookback past 298 makes `target_weights` bail with "only N bars" and hold cash for the whole
sample, silently. `Params.__post_init__` now widens the window to `max(lookback) + 50`, so a
horizon is what is being tested rather than the buffer around it. With that fixed the scan is a
**shelf, not a spike** - full-period Sharpe over the fourth horizon:

| 150 | 180 | 200 | 220 | 240 | 250 | 260 | 280 | 300 | 320 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.85 | 0.96 | 0.96 | 1.01 | 1.07 | **1.10** | 1.04 | 1.04 | 1.03 | 0.88 |

Everything from 220 to 300 beats the champion on CAR, Sharpe *and* drawdown; it collapses at
both edges. **252 sessions is shipped, not the 250 argmax** - one trading year is the a-priori
momentum horizon, it sits inside the shelf, and choosing it costs 0.06 of sweep Sharpe in
exchange for not tuning to the last basis point. Sensitivity holds either side: `top_n` 2/3/4
gives 0.93/1.04/0.98, and removing the crisis-vol filter still costs 12 points of drawdown, so
the S-1 regime overlay is not made redundant by the longer horizon.

**LEAN decides, and it agrees** (run `20260908T235647Z`, shipped default, no env vars):

| | Orders | CAR | Sharpe | MaxDD | Fees | PSR |
| --- | --- | --- | --- | --- | --- | --- |
| champion (20/60/120) | 3,410 | 18.14% | 0.693 | 25.2% | $38,630 | 5.1% |
| **S-9 (20/60/120/252)** | **2,870** | **20.89%** | **0.782** | 28.9% | $37,319 | **10.1%** |
| IS 2012-2019 | 1,551 | 15.18% | 0.701 | 28.9% | | 12.9% |
| OOS 2020-2026 | 1,328 | 28.01% | 0.883 | 21.0% | | 25.7% |

It beats the old champion on both halves (13.5%/0.64 IS and 23.8%/0.76 OOS) and on both
promotion metrics, at 16% fewer orders. `evaluate.py --promote 20260908T235647Z` passed and
**champion.json now points at it**. The economics are the honest attraction: the whole gain
comes with *less* trading, which is the only kind of improvement S-3's 2.1bps-per-turnover cost
floor cannot tax away.

**Two caveats, stated plainly.** Drawdown got worse, 25.2% -> 28.9%, still inside the 35% limit
but with less headroom - and it is all in the 2012-2019 half, where CAR only improved 13.5% ->
15.2%. Most of the headline is the OOS half. And the sweep understated LEAN drawdown by **7.8
points** here (21.1% vs 28.9%), far more than the +2 S-8 calibrated at the champion's size; a
longer horizon holds positions through deeper retracements than the crude sweep cost model
models. Sweeps rank, LEAN decides - again.

**Next.** I-1 is still the gate, and this promotion moves its target: the paper runner's order
list must now be compared against `b763e292cb0eb9a2c81af5739188d437`, not the S-6 hash.
`paper_trade.py --mock --dry-run` re-verified against the new signal and plans XLK/XLE/IWM at
1.50x gross, 0.75 margin.

## 2026-09-08 - S-3: the reversal sleeve is genuinely uncorrelated and genuinely worthless

- **What.** `algorithms/s3_reversal/`, built on the same split as S-1: `signals.py` (plain
  pandas, signed weights, so short = negative) plus `main.py` for LEAN plumbing, and
  `scripts/sweep_s3.py` for the offline walk-forward. Rank the point-in-time top-30 most
  liquid megacaps by trailing k-session return, buy the bottom `n_side`, short the top
  `n_side`, equal dollars per leg, hold one session. The S-1 drawdown overlay, vol helper
  and Reg-T margin table are *imported* from the S-1 module, not copied - loaded by path
  under the alias `s1_signals`, because this file is also called `signals` and a plain
  import from the sibling directory returns itself.
- **Why.** S-8 closed with the measurement that the ETF-9 sleeve cannot be pushed past
  ~20% realized vol inside the 35% drawdown limit by any amount of leverage. If the
  mandate is reachable at all, it is reachable by *adding uncorrelated return streams*.
  So the number that decides S-3 is the correlation with the champion, and the Sharpe
  second.

### The correlation is exactly what was hoped for

| | corr with champion | 50/50 blend Sharpe | blend vol | blend MaxDD |
| --- | --- | --- | --- | --- |
| S-3 reversal, zero cost | **-0.026** | 0.97 | 11.5% | 12.0% |
| S-1 champion alone | 1.000 | 0.97 | 19.8% | 23.2% |

A dollar-neutral single-name book really is orthogonal to a levered ETF momentum book.
The blend keeps the champion's Sharpe and halves its volatility - which is the *wrong*
direction for this mandate, and only because the sleeve added is a zero-return one. The
orthogonality is the finding worth keeping for S-5; the sleeve is not.

### There is no edge to allocate to, before costs and in both directions

30 configurations (lookback 1/2/3/5/10 x n_side 3/5/10 x vol-adjusted or raw), **all at
zero trading cost**, so this measures the signal and nothing else:

| | best cell | median cell | worst cell |
| --- | --- | --- | --- |
| Sharpe, zero cost | +0.27 | -0.11 | -0.72 |

24 of the 30 cells are negative and no cell reaches Sharpe 0.3. The shipped defaults are the *best* cell
(lookback 5, n_side 10, no vol adjustment), chosen with hindsight over the full sample, so
that what follows rejects the hypothesis at its strongest rather than at an unlucky
parameter. Two systematic patterns, both against the hypothesis: n_side 10 beats n_side 3
at every horizon, so the extreme movers are the *worst* part of the cross-section, not the
best; and the raw ranking beats the vol-adjusted one, so what little signal exists is a
vol effect rather than a reversal effect.

Splitting that best cell in half kills it:

| direction | window | CAR @0bps | Sharpe @0bps | CAR @5bps | Sharpe @5bps |
| --- | --- | --- | --- | --- | --- |
| reversal | IS 2012-2019 | +6.2% | 0.64 | -5.8% | -0.56 |
| reversal | OOS 2020-2026 | -1.1% | -0.01 | -11.0% | -0.71 |
| continuation | IS 2012-2019 | -6.0% | -0.58 | -16.6% | -1.88 |
| continuation | OOS 2020-2026 | -1.4% | -0.02 | -9.5% | -0.71 |

The entire zero-cost edge is in-sample, in a cell picked by looking at the full sample. And
flipping the sign - the obvious response to 25 negative cells - is not an edge either: the
mirror image is negative in-sample and flat out-of-sample. Both directions are inside the
noise, which is the honest reading of a cross-section that is 30 daily-rebalanced pairs of
megacaps.

### LEAN confirms, and LEAN is the *optimistic* number here

Run `20260908T224519Z`, 2012-01-03 .. 2026-09-04, shipped defaults:

| | CAR | Sharpe | MaxDD | Orders | Fees | Vol | Beta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S-3 | -0.14% | -0.19 | 48.6% | 44,353 | $64,721 | 10.1% | 0.07 |

Beta 0.07 and `mean_abs_net = 0.0000` at decision time (max 0.094 carried, from drift
between rebalances) - the book is dollar-neutral as designed, and max margin used 0.792
against a 0.75 budget, the same small overshoot S-1 shows. **$64,721 of commission on a
$100,000 account**: 4.4% of equity a year, which on 209 turnover units a year is 2.1bps per
unit of turnover. That is commission *only* - LEAN's IB model charges no spread and no
impact, so the honest cost is higher than the one that already ate the whole return. The
sweep's 5bps assumption is the realistic end and it gives -9.0% CAR.

- **Decision.** **No promotion; champion unchanged.** `evaluate.py` refused on all four
  grounds it has: the `not promotable` tag, 48.6% drawdown over the limit, Sharpe and CAR
  both below the champion. S-3 is closed negatively.
- **What it costs to have learned this.** Two things are now measured rather than assumed.
  (1) Daily-rebalanced single-name pairs cannot pay for themselves on a $100k account: 2.1bps
  of pure commission per unit of turnover against a gross edge of at most 2.6% a year. Any
  future sleeve that turns the book over daily has to clear roughly 5% a year gross before
  it is worth running at this account size. (2) The market-neutral construction *does*
  deliver orthogonality (-0.03), so S-5 remains a live idea - it just needs a sleeve with a
  return.
- **Also worth noting the bias that did not matter.** The megacap pool is a 2026 survivor
  list, and reversal is the strategy that survivorship flatters most (buying the biggest
  loser only pays if the loser comes back, and everything on disk came back). The result is
  negative *anyway*, so the delisted-data blocker did not need resolving to close this one.
- **Next.** Open strategy work is now S-2 (opening-range breakout), which is blocked on
  intraday data, which is blocked on the IB Gateway login - the same human gate as I-1. The
  loop's remaining unblocked lever is a different *signal* on daily bars for the ETF sleeve,
  not another sizing or universe change.

## 2026-09-08 - S-8: four ways to buy drawdown headroom, all four rejected, and the mandate is measured as unreachable

- **What.** The S-8 question: reach the 40-60% volatility mandate without breaching the 35%
  drawdown limit. Four levers, three of them new code in `signals.py`, every one defaulted
  off so the champion is untouched - `margin_budget_cap`/`margin_budget_floor` (an elastic,
  vol-responsive margin budget), `trail_stop`/`trail_window` (a stateless per-holding trailing
  stop), and `dd_mode="taper"` (a continuous drawdown overlay instead of the 1.0/0.5/0.0 step).
  Swept with `scripts/sweep_s1.py --mode s8` and `--mode s8vol`, then the two survivors
  confirmed in LEAN.
- **Why.** S-6 left the constraint on the drawdown limit rather than on execution: budget 1.0
  buys 2.07x exposure and 20.4% CAR but 35.4% drawdown. More size has to be *paid for*.

### The control is clean

Run `20260908T213829Z` at champion defaults reproduces `OrderListHash
9f58b37cc2656b647ec88a5124daf02d` and every statistic. Three new parameters, zero behaviour
change.

### 1. `top_n=5-6` does not survive the size increase

S-7 measured `top_n=6` as cheaper in drawdown at equal return, and the backlog told S-8 to
start there. At the champion's budget that is true; at budget 1.0 it inverts:

| top_n, budget=1.0 | full CAR | Sharpe | MaxDD | Vol |
| --- | --- | --- | --- | --- |
| 3 | **22.4%** | **0.95** | 27.4% | 24.4% |
| 5 | 19.4% | 0.88 | 27.4% | 23.3% |
| 6 | 20.4% | 0.92 | 29.9% | 23.0% |

The headroom S-7 found was a property of a small book, not of the wider one. Rejected.

### 2. An earlier breaker is dominated by simply carrying less size

| dd_halve/dd_flat, budget=1.0 | full CAR | Sharpe | MaxDD |
| --- | --- | --- | --- |
| 0.15/0.25 (shipped) | 22.4% | 0.95 | 27.4% |
| 0.10/0.25 | 16.6% | 0.81 | 23.3% |
| 0.08/0.20 | 16.3% | 0.82 | 22.3% |

Tightening to 0.10/0.25 lands on 16.6% CAR at 23.3% drawdown. The champion, in the same
harness, gets 18.7% at 23.2%. So the tighter breaker is strictly worse than turning the size
back down - it is a more expensive way to buy the same drawdown. Rejected.

### 3. The continuous taper re-creates the 2015 absorbing state

Full period **CAR -0.2%**, exposure 0.21x, invested 53.8% of days. The mechanism is exactly
the bug the journal already records once: the high-water mark only resets on a hard `dd_flat`
breach. A taper asymptotes to zero exposure *just below* `dd_flat`, so the breach never
happens, the peak never resets, and a book earning nothing can never climb back out. The step
function's brutality is load-bearing - it forces the hard breach that resets the mark.
Rejected, and worth keeping as the second instance of the same failure mode.

### 4. The trailing stop does not touch drawdown at all

Five (stop, window) settings, and `MaxDD` is 27.4% in every one of them, against 27.4% with
no stop. Portfolio drawdown here comes from the levered index proxies falling *together*, not
from one holding breaking down, so a per-name stop has nothing to bite on. Rejected.

### 5. The elastic budget: the diagnosis was right, the fix is a size dial

The first sweep showed the elastic budget doing almost nothing, and the reason is a real
finding about the shipped champion: **the vol target has never been active.** The book
realizes ~24% vol against a 40% target, so `target_vol / sigma` sits above every ceiling on
essentially every day, and the strategy therefore carries a *constant* margin through every
regime. Lowering the target to something reachable makes it bind - and that does trace a
better frontier in the sweep. But confirmed in LEAN it collapses:

| LEAN run | Vol | CAR | Sharpe | MaxDD | Orders | Fees |
| --- | --- | --- | --- | --- | --- | --- |
| champion, flat budget 0.75 | 16.5% | **18.1%** | **0.693** | 25.2% | 3,410 | $38,630 |
| elastic [0.2,1.0], tv=26% (`214625Z`) | 17.1% | 16.3% | 0.604 | 24.6% | 4,427 | $37,910 |
| elastic [0.2,1.0], tv=32% (`214218Z`) | 19.4% | 19.7% | 0.674 | 34.3% | 4,307 | $54,498 |
| flat budget 1.0 (S-6, measured) | 20.6% | 20.4% | 0.672 | 35.4% | 4,146 | $55,171 |

The matched-risk row is the verdict. At 17.1% vol against the champion's 16.5% - the same
risk - the elastic budget returns 1.8 points *less* and gives up 0.09 of Sharpe, while placing
30% more orders on a *smaller* book. A budget that moves with the vol estimate re-sizes the
whole portfolio every day, and daily rotation of 3x ETFs cannot afford that. It is a size
dial, not a shape improvement: at tv=32% it lands on the same frontier point as flat 1.0
(19.7%/0.674/34.3% against 20.4%/0.672/35.4%) - a hair less drawdown for a hair less return.

### The harness lied about drawdown, and it lies more as size goes up

Worth recording as a calibration, because every future sweep depends on it:

| config | sweep MaxDD | LEAN MaxDD | gap |
| --- | --- | --- | --- |
| champion (exp 1.62x) | 23.2% | 25.2% | +2.0 |
| elastic tv=32% (exp 1.94x) | 24.6% | 34.3% | +9.7 |
| flat budget 1.0 (exp 2.06x) | 27.4% | 35.4% | +8.0 |

`sweep_s1.py`'s flat 2bps turnover charge is fine for *ranking* at fixed size and badly
optimistic across size: it also scored the tv=26% elastic config at Sharpe 0.97, level with
the champion, where LEAN says 0.604 against 0.693. The docstring already says "choose here,
confirm in LEAN"; this is the magnitude of why.

- **Decision.** **No promotion; champion unchanged** (`evaluate.py` refused both candidates,
  on Sharpe for `214218Z` and on Sharpe *and* CAR for `214625Z`). The new parameters stay in
  the code, defaulted off and documented, because they are the evidence.
- **S-8 is closed, and it closes into a human decision.** The measured LEAN frontier above
  says the drawdown limit is already binding at 19-20% realized vol. The mandate asks for
  40-60%, roughly double again, which on this universe means a drawdown far past 35%. The two
  are not simultaneously reachable on the ETF-9 sleeve by any of the four levers, so this is
  now a risk-budget decision, filed in `BLOCKERS.md`. **Nothing about I-1 moves**: the
  champion's order list is unchanged and the paper deadline is untouched.
- **Next.** With S-8 closed, the open strategy work is a *different signal* rather than a
  different size: S-3 cross-sectional short-term reversal is the next sleeve, and it is the
  one that could raise vol by adding an uncorrelated return stream instead of leverage.
  I-1 remains the deadline gate and is still blocked on the IB Gateway login.

## 2026-09-08 - D-3 point-in-time universe: the timing bias is gone, the pool bias is 90% of it

- **What.** `algorithms/s1_momo/universe.py`: membership decided on each rebalance date from
  the trailing 60-day *median* dollar volume of bars already on disk, top N, with a 252-session
  minimum history. Wired into `signals.Params` as `universe_size` (0 = the fixed sleeve the
  champion ships, so the default is unchanged), into `main.py` behind `S1_UNIVERSE_SIZE`, and
  into `scripts/sweep_s1.py --mode d3`. `lean_prices.load_frames` now returns volume beside
  the adjusted closes.
- **Why.** S-7 printed CAR 43.9% by ranking the megacaps *of 2026* back to 2012. The backlog
  asked for the cheapest honest universe that needs no new data source, and liquidity is what
  the mandate cares about anyway.

### The selection is real, and it moves

Straight from the run log, 20 names picked out of the 59-name pool:

| as of | sleeve |
| --- | --- |
| 2012-12-31 | SPY AAPL IWM QQQ GOOGL **BAC** MSFT GLD **XOM** INTC **JPM** **GE** XLF XLE **WFC** AMZN **IBM** JNJ DIA **PFE** |
| 2024-12-02 | SPY TSLA QQQ **NVDA** AAPL **AMD** MSFT AMZN META IWM GOOGL **AVGO** ORCL GLD MU NFLX INTC LLY UNH DIA |

47 different names are selected at some point, 458 entries and exits, and only 10 of the 20
seats are held by the same ticker in 2026 as in 2012. The 2012 sleeve is full of the banks and
oil majors that then underperformed for a decade, which is exactly what a list built without
hindsight should look like.

### But the honest control says it barely helped

| passive, equal weight, 2012-2026 | CAR | Sharpe | Vol |
| --- | --- | --- | --- |
| EW 50 megacaps, 2026 list (S-7's control) | 22.8% | 1.27 | 17.4% |
| **EW top-20 point-in-time (D-3)** | **22.0%** | 1.09 | 20.2% |
| SPY buy & hold | 15.0% | 0.93 | 16.5% |

Point-in-time selection gives back **0.8 points of the 7.8** by which the biased basket beats
SPY. The remaining 7.0 are not a timing problem and D-3 cannot touch them: `fetch_data.py`
downloaded 69 tickers *that exist in 2026*, so Sprint, Yahoo, EMC and Dell were never
candidates in 2012 no matter what their dollar volume was, and those are disproportionately
the names that later failed. **About 90% of the universe bias is in the file, not in the
ranking date.** Promoted to a decision item in `BLOCKERS.md`.

### And the signal still does not beat its own sleeve

LEAN, run `20260908T203212Z`, `S1_SLEEVE=wide S1_UNIVERSE_SIZE=20 S1_TOP_N=3`:

| | CAR | Sharpe | MaxDD | Orders | Fees | PSR |
| --- | --- | --- | --- | --- | --- | --- |
| D-3 point-in-time sleeve | 32.1% | 0.90 | 32.3% | 4,816 | $69,571 | 16.8% |
| champion (fixed ETF-9) | 18.1% | 0.69 | 25.2% | 3,410 | $38,630 | 5.1% |
| *its own passive sleeve* | *22.0%* | *1.09* | *34.0%* | *0* | *~0* | - |

+14.0 points of CAR over the champion, and it clears QQQ's 19.9% - the thing S-7 wanted. It is
still not a win. Against the sleeve it actually trades, the strategy adds 10.1 points of CAR at
1.25x the vol and **gives up 0.19 of Sharpe** once LEAN's commission model is applied rather
than the sweep's flat 2bps. Buying the same 20 names and doing nothing is the better
risk-adjusted trade. That is the same verdict S-7 reached on the biased sleeve, and it survives
the fix - so the momentum ranking's edge over a liquid large-cap basket is leverage, not skill.

- **Decision.** **No promotion; champion unchanged.** The run is tagged `not promotable`
  and `evaluate.py` refused it on that tag alone - worth noting that it passed every
  statistical rule (32.3% drawdown inside the 35% limit, 4,816 orders, wins both must-beat
  metrics), so the E-3 guard is the only thing standing between a future session and a
  survivorship artifact. The control run `20260908T202809Z` reproduces
  `OrderListHash 9f58b37cc2656b647ec88a5124daf02d`, so plumbing volume through `main.py`
  changed nothing the champion trades.
- **S-7 is closed, negatively.** All three named levers are now answered: momentum-proportional
  weighting loses, `top_n` is flat, and a wider sleeve wins only on borrowed vol and a
  survivor pool. Beating buy-and-hold on absolute return is not a universe problem.
- **I-1 untouched by design.** `paper_trade.py` calls the signal by introspecting its
  parameters and would simply not pass `volumes`; with the champion at `universe_size=0` that
  is correct behaviour, not a gap. If a point-in-time sleeve is ever promoted, the runner needs
  `fetch_history_yf` to return volume too and `call_signal` to forward it - deliberately not
  done today, two days before the paper deadline, for a code path nothing uses.
- **Next.** S-8 on the ETF-9 sleeve, which is the only universe here without a selection
  story: reach the volatility mandate by earning drawdown headroom (start from `top_n=5-6`),
  not by asking for size.

## 2026-09-08 - S-7 beat buy-and-hold: two levers rejected, one is a mirage

- **What.** The three S-7 candidates for beating QQQ's 19.9% CAR, tested on both sub-periods
  with `scripts/sweep_s1.py --mode s7`: momentum-proportional weighting, a wider `top_n`, and
  widening the ranking sleeve to the 50 megacaps D-1 put on disk. `signals.py` gained two
  parameters for it - `rank_universe` and `weight_mode` (`equal` / `rank` / `momentum`) - and
  `main.py` gained `S1_SLEEVE` and `S1_WEIGHT_MODE`.
- **Why.** S-1 clears SPY (18.1% vs 15.0%) but not QQQ, and the backlog named these three.

### 1. Momentum-proportional weighting loses, on both halves

| weight_mode | IS CAR | OOS CAR | full CAR | full Sharpe | full MaxDD |
| --- | --- | --- | --- | --- | --- |
| equal (shipped) | 16.3% | 21.5% | **18.7%** | **0.97** | 23.2% |
| rank | 12.1% | 20.2% | 15.8% | 0.81 | 24.4% |
| momentum | 11.6% | 21.5% | 16.1% | 0.83 | 25.9% |

Concentration costs 2.6-2.9 points of CAR and ~0.15 Sharpe, and it is *in-sample* that it
loses most, so this is not a regime accident. Rejected; `weight_mode` stays `equal`.

### 2. top_n=3 survives, but 5-6 is the interesting neighbour

| top_n | IS CAR | OOS CAR | full CAR | full Sharpe | full MaxDD | vol |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 10.8% | 15.9% | 13.2% | 0.69 | 24.4% | 21.4% |
| 3 | 16.3% | 21.5% | **18.7%** | 0.97 | 23.2% | 19.8% |
| 4 | 15.4% | 19.6% | 17.3% | 0.93 | 22.3% | 19.1% |
| 5 | 13.9% | 21.1% | 17.2% | 0.94 | 22.1% | 18.7% |
| 6 | 14.7% | 20.8% | 17.5% | **0.97** | **22.0%** | 18.4% |

The earlier "top_n=3 is a local peak" caution is only half right: 3 wins on return, but the
curve from 4 to 6 is flat and monotonically *cheaper* in drawdown and vol (OOS drawdown falls
16.7% at top_n=6 against 23.2% at 3, with equal Sharpe). No change to the champion, but this
is a lead for S-8: the binding constraint there is the 35% drawdown limit, and a wider book
buys drawdown headroom that the margin budget could then spend on size.

### 3. The wide sleeve is a survivorship mirage, and the harness could not see it

Adding the 50 megacaps to the ranking sleeve produces the best number this repo has ever
printed. LEAN, run `20260908T192552Z`, `S1_SLEEVE=wide S1_TOP_N=5`:

| | CAR | Sharpe | MaxDD | Orders | Fees | PSR |
| --- | --- | --- | --- | --- | --- | --- |
| wide sleeve | 43.9% | 1.19 | 32.2% | 7,830 | $243,278 | 52.5% |
| champion (ETF-9) | 18.1% | 0.69 | 25.2% | 3,410 | $38,630 | 5.1% |

`scripts/evaluate.py --candidate` said **BEATS champion**: 32.2% drawdown is inside the 35%
limit, 7,830 orders clears 30, and it wins on both must-beat metrics. It is still not real.
`MEGACAP_SLEEVE` is the megacap list *as of 2026*, so ranking it back to 2012 knows in advance
which fifty companies were going to survive and win. The two obvious defences both fail:

* **The IS/OOS split does not detect it.** IS 50.2% CAR vs OOS 54.3% - the halves agree,
  because the hindsight is in universe construction and is therefore spread evenly across
  the whole sample rather than fitted to one end of it.
* **It is not a late-IPO artifact.** Only 4 of the 50 (META, ABBV, NOW, UBER) listed after
  2012-01-03, and dropping them changes almost nothing (44.4% -> 41.8% CAR in the sweep,
  and 22.8% -> 22.4% for the passive basket).
  The bias is in *which names were on the list at all*.

The control that does work is holding the same universe passively
(`scripts/sweep_s1.py --mode s7bias`, 2012-2026):

| | CAR | Sharpe | Vol |
| --- | --- | --- | --- |
| SPY buy & hold | 15.0% | 0.93 | 16.5% |
| EW 50 megacaps (2026 list), no skill at all | **22.8%** | **1.27** | 17.4% |
| momentum top_n=5 on that same sleeve | 44.4% | 1.37 | 30.3% |

So simply *owning* the 2026 megacap list from 2012, equal weighted, beats SPY by 7.8 points
of annual return with a higher Sharpe than the strategy. Against its own basket the signal
adds +21.6% CAR at 1.74x the vol - which is very close to what levering the basket would
give - and only +0.10 Sharpe. Essentially all of the headline uplift is the universe and the
leverage; almost none of it is the ranking.

- **Decision.** **No promotion**, and the champion is unchanged. Rather than rely on
  remembering why, `evaluate.py` now refuses to promote any run whose tag contains
  `not promotable`, and the S-7 run is tagged that way - a later session reading the ledger
  cold would otherwise find a run that passes every statistical rule. The new
  `rank_universe` / `weight_mode` parameters ship defaulted to the current behaviour: the
  control run `20260908T192208Z` reproduces `OrderListHash 9f58b37cc2656b647ec88a5124daf02d`,
  byte-identical to the champion's order list, so the refactor changed nothing that trades.
- **What S-7 actually needs.** A point-in-time universe: membership decided from information
  available on each rebalance date (index membership as of that date, or a rolling
  dollar-volume rank recomputed daily from bars already on disk), not a list downloaded in
  2026. The second option needs no new data source and is now backlog **D-3**. Until then the
  answer to "can a wider sleeve beat QQQ" is unknown, not yes.
- **Next.** D-3, which unblocks S-7 properly; S-8 can start from top_n=5-6 for drawdown room.
  I-1 remains the deadline gate and is still blocked on IB Gateway (`research/BLOCKERS.md`).

## 2026-09-08 - S-6 margin-budget sizing (new champion, exposure 1.27x -> 1.63x)

- **Hypothesis.** S-1's size was limited by a flat `max_gross_weight = 1.0`, which was never
  a risk preference - it was a workaround for LEAN charging un-netted initial margin on both
  legs of a MarketOnOpen rotation. With that execution problem already fixed (netted share
  deltas, sells first, daily-bar rebalance), replacing the flat cap with the constraint a
  broker actually enforces should buy materially more exposure at the same risk.
- **What.** `signals.py` now caps on `sum(weight_i * MARGIN_REQ[i]) <= margin_budget`, where
  `MARGIN_REQ` is Reg-T 50% for an ordinary ETF and 100% for a 3x ETF (IBKR multiplies the
  requirement by the leverage factor). `max_gross_weight` demotes to a hard notional ceiling
  at 2.0. `main.py` audits realized initial margin daily alongside gross. `sweep_s1.py`
  gained `--mode margin`. `paper_trade.py` gained an independent `MAX_MARGIN_USED = 1.0`
  backstop that aborts before sending orders, so a signal bug cannot silently place size.
- **Why this is not just "turn the leverage up".** The cap is asymmetric in exactly the way
  a real account is: three unlevered winners can now run at 1.5x gross, while three 3x ETFs
  are still held to 0.75x gross. The old flat cap punished the *safe* basket and let the
  levered one through, which is why mean effective exposure sat at 1.27x.

### Result (LEAN, `20260908T182554Z`, 2012-01-03 .. 2026-09-04)

| Window | CAR | Sharpe | MaxDD | Orders | Fees |
| --- | --- | --- | --- | --- | --- |
| Full 2012-2026 | **18.1%** | **0.69** | 25.2% | 3,410 | $38,630 |
| IS 2012-2019 | 13.5% | 0.64 | 25.2% | 1,776 | $22,062 |
| OOS 2020-2026 | 23.8% | 0.76 | 24.8% | 1,637 | $6,348 |

Against the outgoing champion: CAR 13.7% -> 18.1%, Sharpe 0.60 -> 0.69, drawdown 23.6% ->
25.2%, mean effective exposure 1.27x -> 1.63x, realized vol 13.3% -> 16.5%. Both sub-periods
improve, and out-of-sample is again the stronger half. Audit: max initial margin actually
carried 0.793 against a 0.75 budget (the 6% overshoot is intraday drift between the decision
close and the next open, not a sizing error), max gross 1.536 against the 2.0 ceiling.

- **Where the budget was set, and why not higher.** `--mode margin` shows return flat above
  budget 1.0 - `scale_cap = 2.0` binds first, so budgets of 1.0, 1.25, 1.5 and 2.0 all land
  on the same book. The full Reg-T budget of 1.0 *does* hit S-6's stated 2x target (LEAN:
  2.07x mean exposure, CAR 20.4%, Sharpe 0.67) but posts a **35.4% drawdown, over the 35%
  limit in `champion.json`**, so it is not promotable. 0.75 is that limit respected with a
  buffer, not a fitted optimum: a book sitting at a full budget has zero excess liquidity and
  any adverse move is a margin call. Both runs are in the ledger; the 1.0 result is the
  measured edge of the risk limit, recorded so the next iteration does not re-derive it.
- **Decision.** Promoted through `scripts/evaluate.py` (3,410 orders, drawdown 25.2% < 35%,
  beats the champion on both Sharpe and CAR). The default `margin_budget = 0.75` is set in
  the code, not passed by environment variable: a confirmation run with no env produced the
  identical `OrderListHash 9f58b37cc2656b647ec88a5124daf02d`, so the champion reproduces from
  a clean checkout, and `paper_trade.py --mock --dry-run` now plans the same 1.5x gross book.
- **Honest limits.** 16.5% realized vol is still far short of the 40-60% mandate; the binding
  constraint has moved from the gross cap to `scale_cap` and the drawdown limit, which is a
  risk-budget conversation, not an execution bug. Fees grew $27k -> $39k on 12% more orders.
  It now beats SPY on return (18.1% vs 15.0%) but still not QQQ (19.9%), so S-7 stays open.
- **Next.** I-1 remains the deadline gate and is still blocked on IB Gateway being logged in.

## 2026-09-08 - S-1 volatility-regime momentum rotation (first champion)

- **What.** `algorithms/s1_momo/`, split into `signals.py` (plain pandas, prices in, target
  weights out) and `main.py` (LEAN plumbing only), so the I-1 paper runner can import the
  identical decision code. Supporting tools: `scripts/lean_prices.py` reads LEAN's own zips
  and factor files back into a DataFrame, and `scripts/sweep_s1.py` walks the shipped signal
  day by day outside the engine (~25s a config vs ~3.5 min for a LEAN run).
- **Why.** Top backlog item and the gate on the 2026-09-10 paper-trading objective.

### Two parts of the specified hypothesis did not survive contact with the data

1. **The regime filter as written is anti-predictive.** S-1 called for risk-on while 20-day
   realized vol sits below its 1-year median. On 2012-2026 SPY returns 4.7%/yr (Sharpe 0.58)
   on those "calm" days and 10.0% (Sharpe 0.75) on the days the filter excludes - vol peaks
   coincide with the sharpest rebounds. Applying it costs 13 points of annual return
   (18.8% -> 5.8% CAR). Replaced with a *crisis* filter: risk-off only once vol exceeds
   1.5x its median.
2. **A 200-day trend filter, the obvious substitute, also loses** - and loses on both halves
   independently (IS 14.7% vs 16.7% CAR, OOS 15.5% vs 21.2%), while buying no drawdown. Kept
   as an option, defaulted off. Deciding this on both sub-periods rather than the full sample
   is what makes it a finding rather than a fit.

### Three execution bugs, each of which silently faked a result

The signal was right early; every bad number came from execution. Worth recording because
they are all invisible in the summary statistics:

| Symptom | Cause |
| --- | --- |
| Stopped trading permanently in 2015 | "Flat until a new equity high" is an absorbing state - a flat book cannot print a high. |
| Every parameter set collapsed onto DD ~25% with erratic returns | Adding a cooldown but keeping the watermark: the breaker re-armed on release and traded 1 day in 22. Fixed by resetting the high-water mark when the breaker releases. |
| 9,095 orders, zero fills | Daily bars leave the exchange looking shut, so market orders degrade to MarketOnOpen, which IB rejects outside 04:00-09:28. |
| DD 87.5% at gross 1.3, then 57.6% at 1.0 | `set_holdings(PortfolioTarget(...))` sizes against *buying power*, so account leverage multiplies every target: same signals gave 27% vol at 2x and 43% at 4x against 16% on paper. Replaced with explicit share math. |
| Account wiped to $1.18, 264%/day turnover, 12.7x gross | MOO orders sent at 09:00 on day D were still unfilled at 09:00 on day D+1, so each rebalance read stale zero holdings and stacked another full target. Fixed by rebalancing on the daily bar, so one order batch is in flight at a time. |

The last one only became visible because `on_data` audits gross exposure actually carried
against the cap. That audit is now permanent; without it the blowup looked like a bad signal.

### Result (LEAN, `20260908T174548Z`, 2012-01-03 .. 2026-09-04)

| Window | CAR | Sharpe | MaxDD | Orders | Fees |
| --- | --- | --- | --- | --- | --- |
| Full 2012-2026 | 13.7% | 0.60 | 23.6% | 3,033 | $27,118 |
| IS 2012-2019 | 10.4% | 0.57 | 23.6% | 1,665 | $18,307 |
| OOS 2020-2026 | 17.8% | 0.64 | 20.8% | 1,373 | $4,200 |

Out-of-sample is the *stronger* half, which is the right direction for an honest fit.
Audited max gross carried 1.047 against a 1.0 cap, zero buying-power rejections, 83.7% of
days invested, mean effective exposure 1.27x.

Sensitivity (`--mode sensitivity`, +/-25% shocks): drawdown is robust, staying in 18.0-22.4%
across every shock. Return is not uniformly robust - halving the distance of the vol
threshold toward the median drops CAR to 7.7%, and `top_n=3` is a local peak (2 -> 10.2%,
4 -> 13.5%). No shock produces a loss or breaches the drawdown limit.

- **Decision.** Promoted to champion through `scripts/evaluate.py` (3,033 orders >= 30,
  drawdown 23.6% < 35%, no incumbent to beat). **It is a baseline, not a win.** Over the same
  period SPY compounds at ~15.0% and QQQ at ~19.9%, so S-1 does not beat buy-and-hold on
  absolute return; what it buys is drawdown, 23.6% against SPY's 33.7% and QQQ's 35.1%. It
  also does not meet the aggressive mandate: 13.3% realized vol, nowhere near the 40-60%
  target. Beating QQQ on return is the bar for the next champion.
- **Why it is not more aggressive.** Gross weight is capped at 1.0 because orders are
  MarketOnOpen and a rotation has both legs outstanding at once. At gross 1.3 LEAN rejected
  3,004 of 3,690 rebalances for buying power. Leverage is therefore limited to what is inside
  the 3x ETFs, and the vol target is inert - the gross cap binds first, which is why
  `target_vol` and `target_exposure` shocks move nothing. The risk control that actually
  works is the crisis filter plus the drawdown breaker.
- **Next.** I-1: the paper runner against IBKR, importing `signals.py` unchanged. The
  execution constraint above is the thing to fix to raise exposure, and it is an execution
  problem, not a signal problem.

## 2026-09-08 - D-1 data pipeline (yfinance daily stopgap)

- **What.** Wrote `scripts/fetch_data.py`: fetches daily bars and writes LEAN-format
  `daily/<sym>.zip`, `map_files/<sym>.csv` and `factor_files/<sym>.csv` into
  `..\Lean\Data\equity\usa\`. Universe is the 19 ETFs from the backlog plus 50 megacaps
  (69 symbols, 1998-01-01 to 2026-09-04, ~430k bars). Existing LEAN sample files are
  backed up to `<name>.orig` before the first overwrite.
- **Why.** Every strategy result so far was a mechanics check on one sample week of SPY.
  Nothing in the backlog can be tested as alpha until real history exists.
- **Adjustment model.** Yahoo's OHLC are already split-adjusted, so the split factor stays
  1 and dividends are carried entirely by the price factor, accumulated backwards from 1
  as `(1 - D / C_prev)` per ex-date.
- **Two bugs the acceptance test caught, both silent:**
  1. Deriving factors from the `Adj Close / Close` ratio looks equivalent but Yahoo rounds
     `Adj Close`, so the ratio wobbles in the 7th decimal daily. SPY got 5490 factor rows
     instead of 117. Fixed by using explicit dividends.
  2. A symbol with no dividends produced a factor file containing only the `20501231`
     sentinel row, and **LEAN silently returned zero bars for it** - no error, no failed
     data request. GLD, UVXY and BRKB were dropped from the first smoke run this way.
     Fixed by always emitting a listing row at the first bar date; the validator now
     rejects a sentinel-only file.
  Also: Yahoo's bar for the in-progress session has `high < open`, so the default end date
  is now today (exclusive), with a clamp-and-report fallback for residual bad bars.
- **Result.** `d1_data_smoke` (20260908T162819Z) reports PASS: all 15 probed symbols deliver
  3690 bars over 2012-01-03 .. 2026-09-04 with no malformed bars. Independent checks: the
  computed factors agree with Yahoo's own `Adj Close` to within 0.003% worst-case across all
  69 symbols, and raw closes match known values (AAPL 2020-08-31 = 129.04, SPY 2020-03-23 =
  222.95, NVDA 2024-06-24 = 118.11).
- **Decision.** No champion. The run's headline numbers (8660% net profit, CAR 35.6%,
  Sharpe 0.80, drawdown 72.7%, 14 orders) are equal-weight buy-and-hold of 15 tickers
  including TQQQ/SOXL/UVXY across a 14-year bull run - a coverage probe, not a strategy.
  `evaluate.py` correctly refused it (14 orders < 30, drawdown 72.7% > 35%).
- **Next.** S-1 volatility-regime momentum rotation, which now has the ETF history it needs.
  Daily bars only: S-2 opening-range breakout still has no intraday data (see D-2).

## 2026-09-08 - Toolchain bring-up

- Built LEAN natively (.NET 10 SDK, Python 3.11, pythonnet) because Docker and WSL2 are
  unavailable on this machine.
- `python scripts/backtest.py _template` ran the SPY buy-and-hold template on the bundled
  sample week (2013-10-07 to 2013-10-11): 1 order, net profit 1.692%, Sharpe 8.85 on five days,
  which is meaningless as alpha and only proves the pipeline works.
- Decision: no champion yet. Next step is backlog D-1 (data pipeline); without real data every
  strategy result is a mechanics check, not evidence.
