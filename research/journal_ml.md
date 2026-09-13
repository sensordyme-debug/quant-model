# ML track journal (F-)

Newest first. The `ml` scope: the supervised intraday forecaster - `algorithms/intraday/ml/`,
`scripts/ml_*.py`, `scripts/sweep_f*.py`, and the `data/f1/` prediction caches. Evidence only;
this track has never shipped a deployed file and does not ask to.

---

## 2026-09-13 - F-21: the six new names are the DAILY CHAMPION'S OWN, and `sweep_f1.EXCLUDE` was one list short of saying so - a naive `--build` today would have made six of the champion's instruments tradable here. On the experiment itself the widening makes the FORECAST 24.6% better and the BOOK $51/day worse, because 100% of the gain lands in the ten slots the book never trades and the one slot it does trade gets 7.0% worse. REFUSED, and the IC-vs-P&L dissociation is the finding.

**Hypothesis.** F-19 filed the widening with a stated mechanism - six liquid sector/asset ETFs
(DIA, GLD, TLT, XLE, XLF, XLK, added to the Alpaca store at 01:0x) give the within-timestamp
`cs_*` ranks a MACRO AXIS that 56 megacaps do not have - and attached a condition: "it must check
AGENTS.md's disjointness rule ... before it is traded". That condition is clause 1 and it ran
first, because it decides which arms are even admissible.

`scripts/ml_f21.py`, **5 ledger rows** under `intraday/f21_wide62`, ten clauses; clauses 0-9 were
pre-registered in the module docstring before a number was read, **clause 10 was added after
clause 8 and says so in its own docstring**. Run with `INTRADAY_DATA_DIR=data/minute_alpaca`. **No
shipped or runner-loaded file was touched**, so no deploy gate and no `--replay` is owed.
`data/f1/panel.parquet` was not modified; the wide panel is a new file beside it.

**(1) Clause 1 FAILS, and it is not a technicality.** All six new names are in the deployed daily
champion's own traded sleeve:

| | list | names |
|---|---|---|
| `sweep_f1.EXCLUDE` | 7 | SPY, QQQ, IWM, TQQQ, UPRO, SQQQ, SPXU |
| champion `RANK_UNIVERSE` (`algorithms/s1_momo/signals.py:68`) | 9 | SPY, QQQ, IWM, **DIA, XLK, XLF, XLE, TLT, GLD** |
| `ic.DAILY_SLEEVE_UNIVERSE` | 12 | the nine above plus TMF, TQQQ, UPRO |

**The difference between the first two lists is exactly the six symbols that arrived.** So
`python scripts/sweep_f1.py --build` on 2026-09-13 would have put six instruments the champion
holds into this track's tradable set, and nothing anywhere would have said so. The panel is a
research cache, so no order was ever at risk - but the next run to read it would have been
measuring a book that breaks AGENTS.md's disjointness rule, and would have had no way to know.
Every such name is **feature-eligible and trade-ineligible**, whatever it scores.

**(2) The fix, and the proof that it costs nothing.** Clause 9: `EXCLUDE` gains the six. That
changes `panel_fingerprint()`, which hashes `EXCLUDE`, so after the edit every F-script would warn
that `panel.parquet` was built by different code - and F-19 exists precisely because that warning
was missing, so it is not silenced by assertion. `--verify-fix` REBUILDS the 56-name panel under
the new constant (261 s) and compares it with the file on disk: **all 46 columns identical to the
bit over 1,576,616 rows.** Only then is `panel.meta.json` re-stamped. The guard changes no number
this track has ever printed.

**(3) The experiment. REFUSED on the pre-registered hurdle, and the headline is nearly a null.**
1,933 out-of-sample sessions, 2019-2026, decile 0.10, F-8's `session` book. Clause 3's identity
passes on every digit: `base56` reproduces F-19's clean base at gross **4.023** bps, cost
**2.720**, t **+1.203**, net **$258/day**.

| arm | panel | book | gross bps | cost bps | edge | net $/day | t | yrs + | paired vs base56 |
|---|---|---|---|---|---|---|---|---|---|
| base56 | 56 | 56 | 4.023 | 2.720 | +1.304 | **258** | +1.20 | 5/8 | - |
| **wide62_feat** | 62 | 56 | 3.771 | 2.729 | +1.042 | **207** | +0.99 | 5/8 | **-52 (t -0.42)** |
| wide62_scram (control) | 62 scrambled | 56 | 3.761 | 2.730 | +1.031 | 204 | +0.96 | 5/8 | -54 (t -0.46) |
| wide62_traded *(diag)* | 62 | 62 | 3.359 | 2.720 | +0.640 | 127 | +0.63 | 5/8 | -132 (t -1.06) |
| wide62_etfonly *(diag)* | 62 | 6 ETFs | 0.812 | 2.463 | -1.651 | **-327** | **-2.48** | **1/8** | **-586 (t -2.37)** |

Hurdle: net t **+0.99** vs 2.0 (FAIL), 5/8 years (PASS), paired **-$52/day at t -0.42** (FAIL).
**REFUSE.** And clause 6's yardstick makes the honest reading plainer than the verdict does: F-19
measured **$176/day** of spread in this same book from a ~1% change in the panel's rows, and every
admissible effect here is **inside** it. The two cells this run can actually resolve are the ones
that clear it: the ETF-only book at **-$586/day**, and nothing else.

**(4) Clause 7, the control, lands on top of the arm it controls - $2/day apart.** `wide62_feat`
-$52/day, `wide62_scram` -$54/day. Permuting the six ETFs' features across sessions within their
own time-of-day slot - same marginals, same place in every rank denominator and in the label's
mean, no contemporaneous link to the tape - reproduces the widening's book to within $2. **At the
book level the widening is arithmetic, not information.**

**(5) And then the IC says the opposite, which is the finding.** Clause 7 is a book statistic. The
forecast statistic disagrees, and both are right. Scored like for like - **the same 1,152,862 rows,
the same 56 names, the same target** (the clean panel's `y_close`, so the 62-name demeaning cannot
flatter anything):

| arm | mean rank IC | t | vs base |
|---|---|---|---|
| base56 | +0.01022 | +7.06 | - |
| wide62_scram | +0.00999 | +6.83 | -0.00023 |
| **wide62_feat** | **+0.01273** | **+8.89** | **+0.00241 (+24%)** |

The scramble lands on base to the fourth decimal, which is what makes the control credible; the
real widening beats it by **+0.00261**. So the macro axis IS information. It just does not become
money - and the raw per-panel IC printed at fit time (+0.01186 at 62 names against +0.00971 at 56)
is **not** the number that shows it, because that one compares two different targets on two
different samples and happens to point the same way by luck.

**(6) WHERE the forecast improves, and it is the whole explanation.** F-8's `session` book opens
ONE cohort, at **slot 0 (09:55)**, and holds it to the flatten. Rank IC is pooled over all eleven
slots. Decile spread - mean `y` of the top 6 by prediction minus the bottom 6, per timestamp, in
bps - is the only ordering the book is paid for:

| | base56 | wide62_feat | change |
|---|---|---|---|
| full-cross-section rank IC | +0.01022 | +0.01273 | **+24.6%** |
| decile spread, pooled over 11 slots | 10.255 bps | 10.648 bps | +3.8% |
| decile spread, **slot 0 only** | **16.803 bps** | **15.630 bps** | **-7.0%** |
| decile spread, slots 1-10 | - | - | **+0.549 bps** |
| IC inside the middle the book never holds | +0.00245 | +0.00754 | **+208%** |
| book gross bps | 4.023 | 3.771 | **-6.3%** |

**The book's -6.3% gross tracks the slot-0 spread's -7.0% and nothing else.** The +24.6% IC is
bought almost entirely in the middle of the cross-section (+208%) and in the ten slots that never
open a position. A decile book is indifferent to every ordering except the top and bottom six at
the minute it trades; rank IC is not.

**(7) Clause 8, feature-importance stability, refutes the stated mechanism directly.** Permutation
importance per retrain, 8 retrains per panel:

| | 56 names | 62 names |
|---|---|---|
| mean pairwise Spearman between retrains | **+0.479** (min +0.026) | **+0.449** (min **-0.182**) |
| positive in all 8 retrains | 0 of 38 | 1 of 38 |
| sign-flipping | 29 | 30 |
| mean rank of the 9 `cs_*` columns | 18.4 / 38 | **18.1 / 38** |

F-19's mechanism requires `cs_*` to move UP. It moves **0.3 places of 38**, and the direction
inside the family is wrong: the four *directional* ranks all move DOWN (`cs_r3` -2.25, `cs_r12`
-2.25, `cs_r6` -1.50, `cs_r1` -0.38) while the gain is concentrated in `cs_rvol_ratio` (11.6 ->
**7.1**), a VOLATILITY rank. Six macro ETFs do not make a megacap's return rank more informative;
they make its volatility rank more informative. **Stability is also slightly worse at 62 names,
not better** - the minimum pairwise retrain correlation goes negative.

**(8) Clause 10, POST-HOC and labelled as such.** (6) implies the `cohort_close` book - one entry
at every slot - should collect what `session` leaves. It does, and it does not help, because those
slots cannot pay for themselves: base56 **-$74/day**, wide62_feat **-$53/day** (+$21, t +0.55),
wide62_scram **-$86/day**. The widening beats its scramble by **+$33/day** here, the first place in
this run where it does so at the book level - and the whole family is negative, at gross **2.83**
bps against a cost line of **3.12**. The slots where the widening helps have a decile spread of
**3-11 bps against a 3.12 bps round trip**; slot 0's is 15.6. **Reported, not adopted** - a book
chosen after the statistic that recommends it is a selection, and this track has refused four
families on exactly that reasoning.

**Decision. REFUSED.** Nothing adopted, nothing promoted, `champion.json` untouched, no deployed
file changed, `panel.parquet` unchanged in content. `sweep_f1.EXCLUDE` gains six names as a GUARD,
proven content-neutral by rebuild. The wide panel and its scramble are kept as
`data/f1/f21_panel62*.parquet` with a fingerprint stamp, because a successor may want the 62-name
cross-section as features even though this book cannot pay for it. **F-21 closes.**

**What it changes for the loop. One rule, and it retires a headline this track has printed since
F-8.** **(e) RANK IC IS NOT THE STATISTIC THIS BOOK MONETISES.** (5) and (6): the widening improved
pooled rank IC by 24.6% and the book's gross by **-6.3%**, and they disagree because the `session`
book collects one of eleven slots and only its tails. From here the per-run diagnostic is the
**slot-0 decile spread**, printed beside the IC - it is what `gross_bps` is a noisy function of,
`ml_f21.tails` already computes it, and had it been on the page this run would have predicted its
own book before simulating it.

---

## 2026-09-13 - F-20: the flow store was NOT the stale part - 0 of 1,570,406 shared rows moved, to the last bit, on all 20 columns. And yet the gate built on it changed 6 of its 8 decisions, because the screen is a property of the PANEL, not of the candidates. F-17's three admitted flow columns are now admitted in ZERO windows, which removes F-18's premise rather than confirming it. Flow is REFUSED a third time, at $197/day against base's $258 - and below its own no-information scramble at $209, for the second run running.

**Hypothesis.** F-19 rebuilt the panel and both auction families and deliberately left the 19-column
flow store alone, arguing that F-14 and F-17 both refused flow and a cleaner tape does not rescue a
family whose loss F-17 (5) traced to one 2020 regime break. That argument is about the CONCLUSION
and it is right. It says nothing about the SUBSTRATE, and F-19's own rule (a) is that a cache whose
inputs have moved has unknown content until it is rebuilt. Two separable questions, pre-registered
as such: **(A)** does the trim move the flow store itself, and **(B)** does F-17's flow refusal
survive the clean panel - which must be re-asked whatever (A) says, because the gate's floor and all
38 incumbents are panel columns and F-19 (3) moved 36.4% of the panel's rows.

`scripts/ml_f20.py`, **4 ledger rows** under `intraday/f20_cleanflow`, nine clauses pre-registered in
the module docstring including clause 0, the prior, which for once carries a **mechanism and a
falsifier** rather than an expectation. Run with `INTRADAY_DATA_DIR=data/minute_alpaca`. **No
shipped or runner-loaded file was touched**, so no deploy gate and no `--replay` is owed. What it
changed on disk is `data/f1/f14_flow.parquet`, rebuilt through the patched loader and pinned to the
clean panel's 56 names; the original is kept beside it as `f14_flow.dirty.parquet`.

**(1) (A) is answered exactly, and the answer is NO.** Clause 2, the full diff:

| | dirty store | rebuilt store |
|---|---|---|
| rows | 1,571,236 | 1,570,406 |
| rows at or after their own session's close | **830** (21 sessions, 54 names) | **0** |
| shared rows with any changed column | - | **0 of 1,570,406 (0.0000%)** |
| max abs delta, each of the 20 columns | - | **0** |
| coverage when merged onto the clean panel | 98.93% | **98.93%** |

Not "small". **Zero, bit for bit, on every column.** Clause 0 predicted it and gave the mechanism
before the run: every column in `flow_one` is a strictly WITHIN-SESSION trailing window
(`_roll_within_day` groups by calendar date, `*_sess` is a within-day cumsum, `m_*` is the same
construction on SPY), so a post-close bar at 13:05 can only enter a window evaluated at 13:05 or
later - i.e. only the 13:25/13:55/14:25/14:55 slots, which are exactly the 830 rows the clean panel
no longer has. The `cs_*` cross-sectional ranks spread contamination only WITHIN the timestamp they
are computed on, and those timestamps are the dropped ones.

**The contrast with F-19 is the reusable part.** Same defect, same store directory, same day:

| store | rows removed | share of survivors that MOVED | why |
|---|---|---|---|
| `panel.parquet` (F-19) | 0.965% | **36.4%**, over 1,854 sessions | 20-SESSION same-slot median; ranks over a cross-section whose members moved |
| `f14_flow.parquet` (F-20) | 0.053% | **0.000%**, over 0 sessions | within-session windows only; ranks confined to dropped timestamps |

**Contamination travels exactly as far as the feature's own lookback reaches, and no further.**
That is computable from the feature definitions before anything is rebuilt, and this run is the
first time this track has predicted the reach and then measured it exactly.

**(2) (B) is the finding, and it is not the one I went looking for. The candidate store is
bit-identical and the gate still changed 6 of its 8 decisions.**

| test year | F-17 admitted (dirty panel) | F-20 admitted (clean panel) |
|---|---|---|
| 2019 | `amihud30`, `clv30` | **`dvol30`** |
| 2020 | `amihud30`, `ofi5` | **`dvol30`** |
| 2021 | `clv30` | **`dvol30`** |
| 2022 | (none) | **`dvol30`** |
| 2023 | (none) | (none) |
| 2024 | (none) | **`clv5`** |
| 2025 | (none) | (none) |
| 2026 | (none) | **`ofi_sess`** |

**The three columns F-17 admitted are admitted in zero windows here; the three admitted here were
admitted in zero windows there.** Nothing about the candidates changed - clause 2 proves that to
the bit. What changed is the floor and the incumbent set the redundancy leg measures against, and
both are built from panel columns. Abstention went from F-17's flow gate 5/8 to **2/8**.

**(3) The mechanism, and it is a hair's width.** `dvol30` and `amihud30` are two views of the same
30-bar dollar-volume roll and correlate at **0.876-0.886**, so clause 4c keeps exactly one. In 2019
the clean window scores them `dvol30` **|IC| 0.02325** against `amihud30` **0.02187** - a gap of
**0.0014**, about 6% of either - and `dvol30` wins. On the dirty panel the order was the other way
and `amihud30` won. **Four of the eight windows are decided by a 0.0014 difference between two
columns correlated at 0.88.** That is not a screen selecting a signal; it is a coin landing on the
side the substrate happened to tilt.

**(4) The book. REFUSED, for the third time on this family.** 1,933 out-of-sample sessions,
2019-2026, decile 0.10, turnover spread across arms **$0**.

| arm | gross bps | cost bps | edge | net $/day | t | yrs + | worst | mean rank IC |
|---|---|---|---|---|---|---|---|---|
| base | 4.023 | 2.720 | +1.304 | **258** | +1.203 | 5/8 | -63,056 | +0.00971 |
| **flow_only** | 3.706 | 2.713 | +0.993 | **197** | **+0.947** | 5/8 | -46,418 | +0.00818 |
| flow_scram (no information) | 3.784 | 2.731 | +1.053 | **209** | +0.990 | 5/8 | -49,572 | **+0.00883** |
| auction_only | 4.023 | 2.720 | +1.304 | 258 | +1.203 | 5/8 | -63,056 | +0.00971 |

Hurdle: net t **+0.947** vs 2.0 (FAIL), 5/8 years (PASS), paired `flow_only - base` **-$62/day at
t -0.63** (FAIL). **REFUSE.** And F-17 (c)'s rule earns its keep again: **the scramble control beats
the arm it controls**, $209 against $197 in net and +0.00883 against +0.00818 in rank IC. Permuting
the admitted flow columns within each timestamp - same width, same marginals, same per-year
schedule, no information - is better than reading them, for the second run running.

**(5) Two identity checks, both exact, and the second is what makes any of this comparable.**
Clause 3: `base` reproduces F-19's clean base on every printed digit - gross **4.023** bps, cost
**2.720**, t **+1.203**, net **$258/day**, mean rank IC **+0.00971**. Clause 4: the clean auction
gate admits **0 parents in 8 of 8 windows**, reproducing F-19 exactly, so merging a second 98 MB
store did not move the sample. `auction_only` is therefore base to the cent, as it must be.

**(6) F-19 rule (b) reported for the first time with a clean answer.** Every admitted column next to
its own changed-row share: `dvol30` **0.0000%**, `clv5` **0.0000%**, `ofi_sess` **0.0000%**. F-19
found the one column its gate ever admitted was the most contaminated in its family; here no
admission is contaminated at all, because there is no contamination left to be exposed to.

**(7) The yardstick, F-19 rule (c).** flow_only-minus-base **-$62/day**, flow_scram-minus-base
**-$50/day**. Both are **inside** the $176/day the base book spans across a ~1% change in the
panel's rows. Stated plainly: **this run cannot resolve the flow effect either way, and saying so
is the deliverable.** What it CAN resolve is (1) and (2), which are counts and set memberships, not
book cells, and are exact.

**Decision. REFUSE**, nothing adopted, nothing promoted, `champion.json` untouched, no deployed file
changed. On clause 9's authority, which needs no hurdle because it is hygiene: `f14_flow.parquet` is
**REPLACED** by the rebuild and stamped with `f14_flow.meta.json` (F-19 rule (a) extended to this
store), the original kept as `f14_flow.dirty.parquet`. **F-20 closes**, and with it the last stale
store this track owns.

**F-18's premise is removed, not confirmed.** F-18 exists to fix F-17 (3)'s |IC| inversion - the
five largest train-window |IC| admissions all losing. Four of those five were `amihud30`/`ofi5`/
`clv30` on the flow side, **and none of them is admitted on the clean panel**. F-19 had already
made the inversion "unverified"; F-20 measures it and finds the admissions it was built on do not
occur. F-18 may still be a good idea on its own merits (scoring a candidate on the validation year
rather than the window it is fitted on is causally cleaner either way), but it can no longer be
sold as fixing an observed defect, and its discriminating prediction - "declines `amihud30` in
2020" - is now vacuous, because the existing gate already declines it. Re-stated on the backlog.

**What it changes for the loop. One rule, and it is the sharper half of F-19 (b).**
**(d) A SCREEN IS NOT A PROPERTY OF ITS CANDIDATES.** (2) and (3): the candidate store was identical
to the bit and the gate still changed 6 of 8 decisions, because its floor and its redundancy leg are
computed against an incumbent set that moved. Any claim of the form "the gate admits X" is a joint
statement about X and about the 38 incumbents on that day, and it must be reported as one. The cheap
version, which F-20 should have printed and the next run will: **alongside each admission, the |IC|
gap to the next candidate it displaced.** Here that gap was 0.0014 on a pair correlated at 0.88, and
knowing it would have told F-17 its result was a coin flip before F-19 ever rebuilt anything.

---

## 2026-09-13 - F-22 (was A-16's F-20, renumbered here because F-19 had already opened an F-20): `sweep_f3.py:338`'s explicit `scale=1.0` is a DECISION, it stays, and passing `share_scale()` there would have been the bug. The residual is $8.24/day of OVERcharge on a book that is refused at -$46/day.

A-16 closed the `commission(` call-site class for the intraday sleeve and left this one for its
owning track, on the grounds that an explicit `1.0` reads as a decision rather than an omission and
only the owner can say which. D-9 had measured factors reaching 1.04e-09 on the inverse-leveraged
sleeve, so the concern was that the error here is not bounded by the intraday case's 200x.

`scripts/ml_f22.py`, no ledger row (it is an audit ruling, not an experiment), no file changed.

**Ground 1, and it settles the question.** `scripts/fetch_data.py` writes **split factor 1.0 on
every row of every factor file**, and the audit confirms it for all 22 of F-3's tradable names: min
and max split factor are exactly 1.0 in every file. There is no split adjustment in the LEAN daily
store for a scale to undo. `share_scale()` - the thing the intraday call sites pass - reads
`data/minute_alpaca/_splits.json`, the INTRADAY store's split table, which does not describe these
bars at all. **Passing it at this call site would have been the defect.** D-9's 1.04e-09 cannot
reach F-3 twice over: none of SPXU/SQQQ/TQQQ/UPRO is in `TRADABLE`, and ground 1 means even they
would carry split factor 1 in this store.

**Ground 2, the residual, measured rather than argued.** What `_price_factors` does apply is the
DIVIDEND factor, whose floor across the sleeve is 0.299 (HYG) and whose median at F-3's actual fills
is 0.8865. That inflates the implied share count and therefore the per-share commission. Replaying
F-3's own test book (2012-01-03..2026-09-09, 3,692 sessions, 20,586 fills; the replay reproduces
`simulate`'s cost line to the cent):

| convention | cost $/day | bps of turnover |
|---|---|---|
| `scale=1.0`, as shipped | 55.48 | 1.2591 |
| `scale=1/dividend factor` | 47.23 | 1.0721 |
| **delta (shipped minus correct)** | **+8.24** | **+0.1871** |

The bias is **0.19 bps of turnover in the CONSERVATIVE direction**, the 1% notional cap binds on
**0 of 20,586** fills (so A-16's unbounded-error concern does not reach this site), and the $1.00
minimum binds on 778. F-3's book is **-$46.05/day net**; the correction would move it to -$37.81 and
change no verdict. **NOT changed** - a conservative bias on a refused book is not worth a shipped
edit to a script another track reads - but the number is now on the record so the next run can price
it instead of re-deriving it.

**One thing found on the way and reported rather than swept.** `sweep_f3.simulate` adds `notional`
to turnover BEFORE its own `np.isfinite(p)` guard, so a fill with no usable price is counted as
traded and never costed. It inflates the denominator of every bps column F-3 prints, by
**$285,714 of $1.626bn = 0.0176%** on this book. Immaterial here, and left alone for the same reason,
but it is the kind of thing that is not immaterial on a book with more gaps.

## 2026-09-13 - F-19: F-16's result was an artifact of a STALE CACHE. On a rebuilt panel the causal gate admits NOTHING in 8 of 8 windows, so its $412/day arm collapses into base at $258. The panel also predated this track's OWN audit fix from the day before, and the identity check that F-14, F-15, F-16 and F-17 each passed could never have caught it - all four compared themselves to the same stale file.

**Hypothesis.** D-6 (`iterate`) opened F-19 with a narrow claim: `data/f1/panel.parquet` was built
on 2026-09-11 11:44 and `intraday_common.load_bars` only learned to drop post-early-close bars at
04:04 today, so 21 half-day sessions carry up to 180 minutes of tape that never traded. D-6 called
the materiality "unknown rather than zero". It is not zero, and the item was smaller than the
defect.

`scripts/ml_f19.py`, **2 ledger rows** under `intraday/f19_cleanpanel`, nine clauses pre-registered
in the module docstring including clause 0, the prior, and clause 9 (the decomposition), which was
added mid-run when the premise turned out to have two causes rather than one. Run with
`INTRADAY_DATA_DIR=data/minute_alpaca`. **No shipped or runner-loaded file was touched**, so no
deploy gate and no `--replay` is owed. What it DID change is `data/f1/panel.parquet`,
`f15_famA.parquet` and `f15_famB.parquet`, which are now the rebuilt stores; the originals are kept
beside them as `*.dirty.parquet`.

**(1) The premise holds, and the cache was stale on TWO counts, not one.** Clause 1: the old panel
holds **1,247 decision rows at or after the session's own close**, on 21 sessions and 50 names, at
the 13:25 / 13:55 / 14:25 / 14:55 slots; the rebuild holds 0, and adds nothing (the trim is a
subset, as D-6's clause 7 promised). But the rebuild removes **15,358 rows, 0.965% of the panel**,
and only 3,144 of them are on an early close. The other 12,214 are on **1,684 ordinary sessions**.
The cause is on this track's own record: `sweep_f1.build_panel` gained AUD-20's
`forward_span_mask` in commit c2350a8 on **2026-09-12 16:49** - and the panel was never rebuilt, so
**F-14 (22:41), F-15 (01:13), F-16 (02:43) and F-17 (04:45) all ran on a pre-AUD-20 cache.**
AUD-20's own note said it "changes no shipped number"; on the Alpaca panel it removes 13,309 rows.
Clause 9 separates them with a third build (trim off, span mask on): **AUD-20 alone accounts for
13,309 of the 15,358 removed rows, AUD-07's calendar trim for the remaining 2,049.**

**(2) Clause 2, the identity check, passes exactly - and that is the problem it exposes.**
Re-simulating the frozen `f16_preds.parquet` reproduces `f16_arms.csv` to **$0.0000 per day on all
five arms** (base 305.71, causal 411.60, causal_p25 397.21, causal_scrambled 283.82, lean3 365.44;
|Δt| 0.000000). So the comparison below is like-for-like. It also means every "base reproduces F-8
to the printed digit" check this track has run since F-12 was comparing a cached artifact with
itself. **A reproduction test against a cache cannot detect that the cache is stale.**

**(3) The contamination is not confined to the 21 sessions, and clause 3 was pre-registered on
that.** Of the 1,576,616 rows present in both panels, **574,287 (36.4%) have at least one changed
feature, over 1,854 sessions.**

| channel | changed rows | % | sessions |
|---|---|---|---|
| `cs_*` (within-timestamp ranks, 9 columns) | 502,040-525,683 | ~32% | - |
| `y` (the label, demeaned per timestamp) | 512,234 | 32.5% | - |
| `vol_rel6` / `vol_rel` (20-session same-slot median) | 66,310 / 33,616 | 4.2 / 2.1% | - |
| `prev_ret` | 23,800 | 1.5% | - |
| `rvol_ratio` / `m_rvol_ratio` (78-bar roll) | 12,401 / 12,411 | 0.79% | - |
| family A, any auction column | 22,232 | 15.2% | **427** |

The mechanism is the one clause 3 named in advance: a trailing 20-session median of the *same
time-of-day slot* carries a fake 13:25 bar forward into the next 20 normal sessions, and a
within-timestamp rank moves for **every** name when one member's input moves. Family A's 427
touched sessions is 21 early closes x the 20-session `scale` window, almost exactly.

**(4) The finding. On a clean panel the causal gate admits NOTHING, in every year.**

| year | F-16 (dirty) admitted | F-19 (clean) admitted |
|---|---|---|
| 2019-2023 | (none) x5 | (none) x5 |
| 2024 | `auc_osz_adv` | **(none)** |
| 2025 | `auc_ofade` | **(none)** |
| 2026 | `auc_ofade` | **(none)** |

Abstention goes from **5/8 windows to 8/8**. The three admissions that made F-16 a result do not
survive, and the reason is legible in the gate's own statistics - the candidate weakens and the
floor rises at the same time:

| year | column | \|IC\| dirty | \|IC\| clean | floor dirty | floor clean |
|---|---|---|---|---|---|
| 2024 | `auc_osz_adv` | 0.00842 (t -2.06) | **0.00619** (t -1.53) | 0.00766 | 0.00727 |
| 2025 | `auc_ofade` | 0.00856 (t -2.68) | **0.00546** (t -1.71) | 0.00834 | **0.00982** |
| 2026 | `auc_ofade` | 0.00871 (t -2.89) | **0.00603** (t -2.00) | 0.00853 | **0.00903** |

`auc_ofade` loses **30-36% of its \|IC\|**. That is not a coincidence of the rebuild: `auc_ofade` is
`(early_c / open_px - 1) / scale`, and `scale` is the 20-session trailing vol built from `last_c`,
the session's last continuous bar - which on an early close **is a post-market print**. Clause 3
measured `auc_ofade` as the single most contaminated auction column (15.0% of rows). **The one
column the screen ever admitted was the one most exposed to what was wrong with the data.**

**(5) The book, and F-16's headline is withdrawn.** 1,933 out-of-sample sessions, 2019-2026,
decile 0.10, turnover spread across arms **$0**. With an empty admitted set in all 8 years,
`causal` and `causal_scrambled` are not merely close to `base` - they are the **same book to the
cent**, so only one distinct row was written to the ledger.

| arm | net $/day dirty | net $/day clean | Δ | t dirty | t clean |
|---|---|---|---|---|---|
| base | 306 | **258** | -47 | +1.474 | **+1.203** |
| causal (F-16's arm) | **412** | **258** | **-153** | **+1.969** | **+1.203** |
| causal_scrambled | 284 | 258 | -25 | +1.364 | +1.203 |

Clean base: gross **4.023** bps, cost **2.720**, edge +0.650, mean rank IC **+0.00971** (was
+0.01030), **5/8** years positive, worst **-63,056**, win 49.0%. Hurdle: net t +1.203 vs 2.0
(FAIL), 5/8 years (PASS), paired vs base undefined because the arms are identical (FAIL).
**REFUSE**, as F-16 was refused - but the $412/day and the t +1.969 that made it "the best net this
track has fitted" were **produced by the stale cache** and are withdrawn.

**(6) Clause 9, and it is the number I would carry forward over everything else here.** The same
frozen learner, seed, universe, last day and 8 test years, on three panels that differ by ~1% of
rows:

| panel | net $/day | t | mean rank IC |
|---|---|---|---|
| dirty cache (neither fix) | 306 | +1.474 | +0.01030 |
| + AUD-20 span mask only | **129** | **+0.638** | **+0.01271** |
| + AUD-07 calendar trim (clean) | 258 | +1.203 | +0.00971 |

The two audits push in **opposite directions and nearly cancel**: -$176/day then +$129/day for a
net -$47. These are three different fits, not one book with rows deleted, so the honest reading is
not an attribution but a **sensitivity: the F-8 base book spans $176/day across a 1% change in the
panel.** F-16's causal-minus-base was +$106/day and F-17's pooled-minus-auction was -$112/day.
**Both are smaller than the panel's own construction noise.** Note also that the AUD-20-only panel
has the **highest** mean rank IC of the three (+0.01271) and the **worst** book ($129/day) - IC and
P&L disagreeing again, as in F-17 (3).

**Decision.** **REFUSE**, nothing adopted, nothing promoted, `champion.json` untouched, no deployed
file changed. Separately and on clause 6's authority, which needs no hurdle because it is data
hygiene rather than a result: `panel.parquet`, `f15_famA.parquet` and `f15_famB.parquet` are
**REPLACED** by the rebuilds (56 names and last day 2026-09-10, pinned to the old panel so the
comparison isolates the fixes); the originals are kept as `*.dirty.parquet`. **F-16 is superseded**
and the "best net this track has fitted" line is retired.

**Two items opened rather than assumed.** `f14_flow.parquet` was **not** rebuilt (**F-20**) - F-14
and F-17 both refused the flow family and a cleaner tape does not rescue a family whose loss was
traced to one 2020 regime break, but it must be rebuilt before flow is ever reopened. And clause 8:
the Alpaca store grew **six symbols** (DIA, GLD, TLT, XLE, XLF, XLK, added 01:0x today by another
track) and one session after the old panel was built. Rebuilding on the whole store would have
measured the fixes and a 62-name cross-section at once, so the run is pinned to the old 56;
the wider universe is **F-21**.

**What it changes for the loop.** Three rules.
**(a) An identity check against a CACHED artifact proves nothing about the pipeline.** (2): four
consecutive runs passed "base reproduces F-8 to the printed digit" while reading a panel that was
already a day behind this track's own audit fix. The check must be "the cache is newer than every
input that builds it", or a rebuild-and-compare. Cheap version: assert the panel's mtime is newer
than `sweep_f1.py`, `intraday_common.py` and the store.
**(b) Report a screened column's exposure to the known defects in its own inputs.** (4): the only
column the gate ever admitted, `auc_ofade`, was the most contaminated one in its family, and it
lost a third of its |IC| when the contamination went. A screen selects on apparent strength, so it
selects **for** whatever is inflating it.
**(c) An effect smaller than the panel's construction noise is not a result.** (6): $176/day of
spread from a 1% change in the rows. Every F cell this track has ruled on since F-12 is inside
that. Any future F run states the effect it claims **next to** that number, or re-measures it.

**Rule (a) is enforced, not just written down.** `sweep_f1.panel_fingerprint/stamp_panel/
check_panel_fresh` write and check `data/f1/panel.meta.json`, which records a SHA of the source of
`build_panel`, `features_one`, `to_5min`, `slot_volume_median`, `decision_mask`, `ic.load_bars`,
`ic.calendar_trim` and `qb_labels.forward_span_mask`, plus the store's directory, symbol count and
newest mtime. `sweep_f1 --train` and `ml_f15.load_panel` (so F-15, F-16, F-17 and everything after)
call it and print a warning. It hashes **source, not mtimes**, on purpose: an mtime check trips on
a comment, gets ignored, and then fails to fire on the one edit that mattered - which is how F-19
happened. Verified both ways: silent on the installed panel, and it fires on a changed builder hash
and on a store that gained symbols. It is a warning and never an exception, because several
scripts load the panel mid-run.

## 2026-09-13 - F-17: the gate ranks candidates in the WRONG ORDER. Given a wider pool it admitted the five columns with the LARGEST train-window |IC| - |t| 5.7 to 7.7 - and every one of them lost, while the three weakest, barely over the floor, made all the money. The pooled arm finished BELOW its own no-information scramble control. F-16 (a) is confirmed from the adversarial side: the abstention was the product.

**Hypothesis.** F-16 built the first screen this track has that ranks a candidate without spending
the test window, and closed with a rule: *a gate earns its keep in the windows where it admits
nothing*. But that gate had never been shown a candidate it was not already expecting to like - six
parents, one store, one tape. F-17 makes it choose: **17 parents from two disjoint stores in one
pool** - F-14's 11 own-name flow columns and F-15's 6 own auction columns - per-year floor, per-year
admission. It answers the question F-14 named and left open: F-14 refused its flow family **as a
family**, and F-15 (a) says a family should be admitted at the size its members justify, which for
flow has never been measured.

`scripts/ml_f17.py`, **5 ledger rows** under `intraday/f17_poolgate`, per-year gate in
`data/f1/f17_gate.csv`, admitted sets in `f17_admitted.json`, cells in `f17_arms.csv`. Eight clauses
pre-registered in the module docstring including clause 0, the prior. One new leg, clause 4c
(within-pool redundancy), pre-registered because eleven of the seventeen are one construction at
three horizons. No new data pull - `f14_flow.parquet`, `f15_famA.parquet`, `f15_famB.parquet` read
unchanged. Run with `INTRADAY_DATA_DIR=data/minute_alpaca`. **No shipped or runner-loaded file was
touched**, so no deploy gate and no `--replay` is owed.

**(1) Both identity checks pass, and the second one is the reason this run is comparable rather
than merely similar.** Clause 1a: `base` reproduces the frozen F-8 model to the printed digit -
mean rank IC **+0.01030**, gross **4.256** bps, cost **2.724**, net **$305.7/day**, t **+1.474**,
1,933 sessions. Clause 1b: the pooled gate **restricted to F-16's six auction parents reproduces
F-16's admitted sets in all 8 years exactly** (none x5, `auc_osz_adv`, `auc_ofade`, `auc_ofade`) and
its book to the dollar - 4.795 gross bps, **$412/day at t +1.97**, worst -45,005, paired +$106 at
t +1.42. Merging a 98 MB second store did not move the sample.

**(2) The result, and the control is the headline.** 1,933 out-of-sample sessions, 2019-2026, one
decision, decile 0.10. **Turnover is identical in every arm to the dollar (spread $0).**

| arm | gate pool | mean rank IC | gross bps | cost bps | net $/day | t | yrs + | worst |
|---|---|---|---|---|---|---|---|---|
| base | - | +0.01030 | 4.256 | 2.724 | 306 | +1.474 | 5/8 | -51,431 |
| **pooled** | **17, pre-registered** | +0.00837 | 4.286 | 2.730 | **310** | **+1.503** | 5/8 | -45,005 |
| flow_only | 11 flow | +0.00928 | 3.748 | 2.722 | **205** | +1.00 | 5/8 | -51,431 |
| auction_only | 6 auction (= F-16) | +0.00939 | 4.795 | 2.732 | **412** | +1.97 | 5/8 | -45,005 |
| pooled_scrambled | 17, information destroyed | +0.01180 | 4.322 | 2.725 | **319** | +1.54 | 5/8 | -55,836 |

**The scramble control beats the arm it controls**: `pooled_scrambled` $319/day against `pooled`
$310, paired `pooled - pooled_scrambled` **-$16/day at t -0.14**. Permuting the admitted columns
within each timestamp - same width, same marginals, same per-year schedule, no information - is not
worse than reading them. Widening the pool cost **$112/day at t +1.35** against F-16's own arm.

**(3) The inversion, which is the finding and is not subtle.** Read the train-window statistics of
the eight columns the pooled gate admitted, alongside what each cost or earned out of sample:

| year | store | admitted | train |IC| | train |t| | paired vs base, that year |
|---|---|---|---|---|---|
| 2019 | flow | `clv30`, `amihud30` | 0.0181, 0.0212 | 6.9, 7.7 | **-51/day** (t -0.21) |
| 2020 | flow | `ofi5`, `amihud30` | 0.0129, 0.0159 | 5.7, 6.8 | **-974/day** (t -1.90) |
| 2021 | flow | `clv30` | 0.0145 | 5.8 | +169/day (t +0.61) |
| 2024 | auction | `auc_osz_adv` | 0.0084 | 2.1 | **+457/day** (t +1.32) |
| 2025 | auction | `auc_ofade` | 0.0086 | 2.7 | **+468/day** (t +1.22) |
| 2026 | auction | `auc_ofade` | 0.0087 | 2.9 | -155/day (t -0.42) |

The flow admissions carry **2-3x the |IC| and 3x the |t|** of the auction admissions on the window
the gate is allowed to read, and they are the ones that lose. There is no overlap in the ranges:
every flow admission scores above 0.0129, every auction admission below 0.0088. **A floor that
ranks candidates by their strength on the training window sorts them into exactly the wrong
order here.** Clause 4c, the new within-pool leg, dropped three more flow columns (`ofi30` |t| 6.4,
`dvol30` |t| 6.8 and 5.9) - all of them from the losing side, and it still was not enough.

**(4) F-14's open question is answered, and the answer is no.** `flow_only` - the flow family
admitted at the size its own members justify, which is 1-2 columns in 3 of 8 years and zero in the
other 5 - is **$205/day against base's $306**, paired **-$101/day at t -1.22**, and **-$258/day on
the 757 sessions where it is active**. F-14 refused the family as a family; F-15 (a) suggested the
refusal might be about size. It is not. The flow store does not carry, at 19 columns or at one.

**(5) All of it is one year, and the year is the one that matters.** `flow_only` in 2020:
**-$974/day at t -1.90**, 45% of sessions up. Base earns $1,273/day in 2020, its best year;
`flow_only` earns $359. `amihud30` (illiquidity) and `ofi5` were fitted on 2016-2019 and traded
through the liquidity event those four years contain no analogue of. The remaining two active years
are noise (-$51 and +$169). The whole flow result is a single regime break, which is also why its
train-window |t| of 6.8 was meaningless.

**(6) Clause 8(a), pre-registered as an outcome: the wider pool abstains LESS, and that is the
mechanism of its loss.** `auction_only` abstains in **5 of 8** windows and is active on 35% of
sessions; `pooled` abstains in **2 of 8** and is active on 74%. Every window where the pooled gate
is active and the auction gate was not - 2019, 2020, 2021 - is a window it fills with flow. F-16 (a)
claimed a gate earns its keep by declining; F-17 is the adversarial test of that claim and it holds:
handed more candidates, the gate declined less, and the book went from $412 to $310.

**(7) Clause 8(b), the paired-on-active statistic.** `pooled` **+$6/day on its 1,432 active sessions
(t +0.04)**; `auction_only` **+$303/day on 675 (t +1.42)**; `flow_only` **-$258/day on 757
(t -1.22)**; `pooled_scrambled` +$18/day on 1,432 (t +0.16). The pooled gate's active sessions are
statistically indistinguishable from its own scramble.

**(8) And it gives up the regime where the book actually earns.** Net $/day across terciles of SPY
trailing 20-session realised vol: base **-65 / +208 / +626**; pooled **-222 / +519 / +397**;
auction_only **-53 / +401 / +693**; scrambled +3 / +262 / +564. `pooled` is the only arm that loses
**more than a third of base's high-vol cell**. F-16's arm improved every tercile it touched;
diluting it with flow moved the damage into the sessions with movement to trade.

**Decision.** **REFUSE.** net t **+1.503** against 2.0 (FAIL), **5/8** years positive (PASS), paired
`pooled - base` **+0.043** against 2.0 (FAIL). Nothing adopted, nothing promoted, `champion.json`
untouched, no deployed file changed. F-16's auction arm is **not** superseded - it is reproduced
exactly and it remains the best net this track has fitted ($412/day, t +1.97), still below the
hurdle.

**What it changes for the loop.** Three rules, and the first one retires a method.
**(a) A train-window |IC| floor is an ANTI-selector when candidates come from stores with different
regime exposure.** (3): the five admissions with the largest in-window |IC| all lost; the three
smallest made all the money, and the ranges do not overlap. F-14 (a) + F-15 (a) as a gate is
finished in this form. Any future screen must score a candidate on data the floor did not see.
**(b) An abstention rate is a result, not a knob to minimise.** (6): the same gate, same threshold,
same rule, over a wider pool abstains in 2 of 8 windows instead of 5 and loses $112/day for it.
Report it, and treat a gate that became more active as a gate that got worse until shown otherwise.
**(c) Print the scramble control's NET, not only its paired t against base.** (2): `pooled` beats
base in gross and beats base on paired t, and still finishes **below its own scramble**. A run that
compared each arm only to `base` would have reported "pooled +$5/day, harmless" and missed that the
information content is negative.

**Next.** **F-18**, and (a) names it exactly. The gate's defect is that it scores a candidate on the
window it is fitted on, where a column that broke once looks strongest. The causal fix costs
nothing: **score the candidate on the VALIDATION year alone** (year Y-1, already held out of the
model's own fit) instead of on the whole train window, with the floor recomputed the same way on
the same year. That is still strictly causal - Y-1 < Y - and it asks the question that matters,
"did this column carry the last time it was out of sample", rather than "how strong does it look
in sample". Pre-register two arms against F-17's admitted sets as the reference: `val_floor` (the
minimal fix, no fit, ~10 minutes) and `val_contrib` (rank each candidate by the change in
validation-year rank IC when it is added to the 38, 17 x 8 = 136 fits at ~8 s, ~20 minutes). Same
hurdle, and per (b) pre-register the abstention rate again - the prediction that separates the two
readings is that a validation-year floor **abstains MORE than 2 of 8**, and specifically that it
declines `amihud30` in 2020.

**Housekeeping, and it refines F-16's fix rather than confirming it.** Committed with
`git commit --only <paths>` per F-16's note, and it did what F-16 claimed: **no other track's code
file entered `43816d1`** - `quant_brain/*`, `scripts/sweep_{d6,o8,s41}.py`, `tests/*` and the eight
other modified files all stayed out, where `git add <mine> && git commit` would have swept them in.
But `--only` is path-level, not hunk-level, so it commits the **whole working-tree content** of a
named path. `research/backlog.md` is shared, and the eng and options tracks edited it between my
edit and my commit: **E-11 and O-8's new items are in this commit under my message.** Nothing was
lost or rewritten. The honest statement of the rule is therefore narrower than F-16 wrote it:
`--only` protects you from files you did not name; for a shared file you DID name there is no
protection, and `research/backlog.md` and `research/experiments.jsonl` will always carry whatever
a concurrent track appended. Worth stating that way in AGENTS.md by whichever track owns it.

**Housekeeping 2: the pre-commit gate flapped, and it was not mine.** `.githooks/pre-commit` runs
`scripts/qb_check.py`, which lints and tests the **whole working tree** including other tracks'
in-flight edits. The first commit attempt failed it on `ruff (core + tests)`, `ruff (10 changed
elsewhere)` and `pytest`; `ruff check scripts/ml_f17.py` passed on its own, and re-running the same
gate unchanged a few minutes later printed **GATE PASSED**. The failure was another track
mid-edit. A gate over the shared tree cannot tell whose red it is, so read it, check your own
files, and retry before assuming you broke something - do not reach for `--no-verify`.

## 2026-09-13 - F-16: the causal gate BEATS the oracle it was built to imitate, and it beats it by admitting nothing in 5 of 8 years. Closest this track has ever come to the hurdle - net t +1.969 against 2.0 - and still REFUSED, because the paired test is +1.42. `lean3` is not confirmed: the causal gate does not pick `auc_ofade` in most years, it picks the column F-15's gate called nothing.

**Hypothesis.** F-15 (7) found that 3 of 19 auction columns turned a -$148/day loss into a +$60/day
gain, posted the highest gross this track had measured and were the first arm ever positive in the
low-vol tercile - but the 3 were chosen **after reading the test window**, so `lean3` was a
selection artefact and F-15 said so in its own closing paragraph. F-16 is the one experiment that
separates the two readings: take the gate that picked them (F-14 (a)'s redundancy rule plus
F-15 (a)'s incumbent-floor rule) and **run it inside the walk-forward**, at every retrain, on
train + validation only. Nothing in the selection path may see the year it trades.

`scripts/ml_f16.py`, **5 ledger rows** under `intraday/f16_causalgate`, per-year gate in
`data/f1/f16_gate.csv`, admitted sets in `f16_admitted.json`, cells in `f16_arms.csv`. Eight
clauses pre-registered in the module docstring including clause 0, the prior, written before a
number of this run was read. No new data pull - `f15_famA.parquet` and `f15_famB.parquet` read
unchanged. Run with `INTRADAY_DATA_DIR=data/minute_alpaca`. **No shipped or runner-loaded file was
touched**, so no deploy gate and no `--replay` is owed.

**(1) Clause 1 identity is exact.** `base` reproduces the frozen F-8 model to the printed digit:
mean rank IC **+0.01030**, gross **4.256** bps, cost **2.724**, net **$305.7/day**, t **+1.474**,
1,933 sessions, turnover $1,995,861/day.

**(2) The pre-registered floor is nearly degenerate, and that is the first finding.** Clause 4a set
the floor at the **median** |IC| of the 38 incumbents, recomputed per window. On a train window the
median incumbent reads 0.0077-0.0135 - far above the 0.002-0.006 F-15 measured for the auction
family on the pooled test window - so the q50 gate **admits nothing in 5 of the 8 years**:

| test year | window | floor q50 | admitted (q50) | admitted (q25) |
|---|---|---|---|---|
| 2019 | 2016-2018 | 0.01485 | *(none)* | `auc_osz_adv` |
| 2020 | 2016-2019 | 0.01275 | *(none)* | `auc_osz_adv` |
| 2021 | 2016-2020 | 0.01352 | *(none)* | *(none)* |
| 2022 | 2016-2021 | 0.01074 | *(none)* | `auc_osz_adv`, `auc_ofade` |
| 2023 | 2016-2022 | 0.01153 | *(none)* | + `auc_cdrift` |
| 2024 | 2016-2023 | 0.00766 | **`auc_osz_adv`** | `auc_osz_adv`, `auc_ofade` |
| 2025 | 2016-2024 | 0.00834 | **`auc_ofade`** (triple) | `auc_osz_adv`, `auc_ofade` |
| 2026 | 2016-2025 | 0.00853 | **`auc_ofade`** (triple) | `auc_osz_adv`, `auc_ofade` |

Because that made the pre-registered arm a copy of base in most years, a **second specification**
was added **after** the gate pass was read and is labelled as such throughout and barred from
clause 5: `q25`, the same rule at the 25th percentile of the same incumbent distribution, still
computed on train + validation only. It admits 0-3 parents per year and is active in 87% of
sessions against q50's 35%.

**(3) Clause 8, the secondary deliverable: the causal gate does NOT reproduce the oracle's pick.**
`auc_ofade` - F-15's survivor, the column the whole `lean3` result rests on - is admitted in
**2 of 8 years at q50** and 5 of 8 at q25. What the causal gate admits most often is
**`auc_osz_adv`**, the opening cross size against ADV, which **F-15's own test-window gate rated
IC -0.00151 at t -0.8, i.e. nothing**, and which reads -0.0065 to -0.0084 on every train window.
The two gates disagree about which column of the auction tape carries. Mean pairwise Jaccard of the
admitted parent sets: **+0.393** (q50), **+0.512** (q25); **no column is admitted in every year**.
Clause 0 predicted `auc_ofade` in >= 6 of 8 and a Jaccard of 0.5-0.8, and was wrong on the first.

**(4) And the book went UP anyway - past the oracle, and further than anything this track has
fitted.** 1,933 out-of-sample sessions, 2019-2026, one decision, decile 0.10. **Turnover is
identical in every arm to the dollar (spread $0)**, so every bps column is like-for-like.

| arm | selection | mean rank IC | gross bps | cost bps | net $/day | t | yrs + | worst |
|---|---|---|---|---|---|---|---|---|
| base | - | +0.01030 | 4.256 | 2.724 | 306 | +1.474 | 5/8 | -51,431 |
| **causal (q50)** | **causal, pre-registered** | +0.00939 | **4.795** | 2.732 | **412** | **+1.969** | 5/8 | -45,005 |
| causal_p25 | causal, post-hoc threshold | +0.01170 | 4.743 | 2.753 | 397 | +1.90 | 5/8 | -39,807 |
| causal_scrambled | causal, information destroyed | +0.01104 | 4.146 | 2.724 | 284 | +1.36 | 5/8 | -49,652 |
| lean3 | **oracle, test-set-selected** | +0.00951 | 4.643 | 2.812 | 365 | +1.75 | 5/8 | -45,005 |

`causal`'s **4.795 gross bps is the highest this track has recorded on this label**, above
F-15 `lean3`'s 4.643 and base's 4.256. Paired per session: `causal - base` **+$106/day at t +1.42**,
`causal - lean3` **+$46/day at t +0.43**, `causal_scrambled - base` **-$22/day at t -0.33**.
Clause 0 predicted causal would land *between* base and the oracle at t +1.3 to +1.8. It landed
**above both**.

**(5) Clause 5: REFUSE, and it fails by 0.031 on the leg it came closest on.** net t **+1.969**
against 2.0 (**FAIL**), **5/8** years positive (PASS), paired `causal - base` **+1.416** against
2.0 (**FAIL**). Nothing adopted, nothing promoted, `champion.json` untouched, no deployed file
changed.

**(6) The pooled t is the wrong number to be impressed by, and the post-run split says so.** An arm
that *is* base in 5 of 8 years shares 65% of its sessions with base, so base +1.474 -> causal
+1.969 is not an independent test. On the **675 sessions where the gate actually admitted
something**, the paired effect is **+$303/day at t +1.42** - a large magnitude that does not reach
significance - and the scramble control on the *same* 675 sessions is **-$63/day at t -0.33**. The
information, not the width, is what moves it; there just is not enough of it to clear 2.0.

**(7) Why the causal arm beats the oracle, which is the reusable part.** Decompose by year. In
**2025 and 2026 the causal gate independently rediscovers `lean3`'s exact triple** and the two arms
are identical to the dollar ($818 and $768). In **2024** it picks `auc_osz_adv` instead and earns
$1,320 against `lean3`'s $1,086. And in **2019-2023 it admits nothing at all**, which is where
`lean3` - forced to carry `auc_ofade` in every year - averages $74/day against base's $97, giving
back **$660/day in 2020 alone** (base $1,273, `lean3` $613). **The causal gate's
advantage over the oracle is entirely the years it declines to add
anything.** A gate is not primarily a device for finding columns; it is a device for refusing them
in the windows where they do not yet carry.

**(8) The tighter floor is the better floor, which confirms F-15 (a) from the other direction.**
q25 is active in 87% of sessions and worth **+$105/day per active session (t +0.76)**; q50 is
active in 35% and worth **+$303/day per active session (t +1.42)**. Three times the effect at a
third of the exposure. Loosening the floor to admit more members of the family diluted it exactly
as F-15 (a) predicted, measured this time on a causal selection rather than a hand-picked one.

**(9) `lean3`'s headline low-vol result does NOT survive.** Net $/day across terciles of SPY
trailing 20-session realised vol: base **-133 / +250 / +623**; causal **-121 / +423 / +713**;
causal_p25 -52 / +327 / +736; scrambled -90 / +185 / +609; lean3 **+103 / +354 / +532**. `causal`
is the best arm in the mid and high terciles and is the only arm to beat base in both, but it is
**negative in the low-vol tercile** (-121) like every arm before F-15. F-15 (7)'s "first arm ever
positive in low vol" was a property of forcing `auc_ofade` into all 8 years, and it is a property
the causal selection does not have. The forecast is still paid only where there is movement.

**Decision.** **REFUSE.** Nothing deployed, nothing promoted. The F-15 mechanism is **not**
confirmed as stated - the causal gate does not pick `auc_ofade` in most years - while the broader
claim it sat inside, that the auction tape adds something the 38-column panel does not have, is
**strengthened**: a selection that never sees its test year still produces the best gross and the
best net this track has fitted, and its scramble control produces neither.

**What it changes for the loop.** Three rules.
**(a) A feature gate earns its keep in the windows where it admits NOTHING.** (7): the causally
selected arm beats the test-set-selected oracle purely by abstaining in 2019-2023. Any track
adding features should report how often its gate declines, and treat a gate that always admits
something as unscreened.
**(b) Never read the pooled t of an arm whose feature set varies by window.** (6): base +1.474 ->
+1.969 looks like a large move and 65% of those sessions are the same trade. Report the paired
statistic on the ACTIVE subset, and report how large that subset is.
**(c) An incumbent floor measured on a TRAIN window is far higher than one measured on a pooled
TEST window** - median 0.0077-0.0135 against F-15's test-window reading of the same 38. A rule
calibrated on test-window ICs will be much stricter than intended when it is made causal. (2) cost
this run its pre-registered arm's power and is the reason `q25` had to be added.

**Next.** **F-17**, and it is now cheap because the machinery exists. The causal gate takes ~16 s
per window and is the first screen this track has that can rank candidates *without* spending the
test window. Point it at the **whole candidate space the track has accumulated**: F-14's 19 flow
columns (`data/f1/f14_flow.parquet`) and F-15's auction family in one pool, per-year floor, per-year
admission. F-14 refused its flow family **as a family** and F-15 (a)'s rule says a family should be
admitted at the size its members justify - which for flow may be 1 or 2 columns in some years and
zero in others, and has never been measured. Both stores are on disk, so it is one file, no data
pull and roughly 45 minutes. Pre-register the same hurdle and, per (a), pre-register the abstention
rate as a reported outcome rather than a diagnostic.

**Housekeeping, and it is the same defect 560b0bb recorded yesterday.** F-16's commit `98512df`
swept in another track's files - `research/experiments_futures.jsonl`,
`research/futures_discovery_{es,mes,mnq}.json` and `scripts/futures_fetch_multi.py` - which the
futures track had staged in the shared index between my `git add` and my `git commit`. Nothing was
lost and nothing was rewritten; the files are in the repo under the wrong message. The cause is
that `git add <mine> && git commit` commits **the whole index**, not the paths just added, so the
AGENTS.md rule "commit ONLY the files you touched" is not actually enforced by the command the rule
recommends. **The fix, and the ml track uses it from here: `git commit --only <paths> -m ...`,
which commits exactly the named paths whatever else a concurrent track has staged.** Worth
promoting to AGENTS.md by whichever track owns that file.

## 2026-09-13 - F-15: the auction tape DOES carry orthogonal, sign-stable signal the panel does not have - and adding all 19 columns of it made the book worse while 3 of them made it better. Refused on the pre-registered arm. The gate is necessary and NOT sufficient: F-14 screened the REDUNDANT, and what beat this run was the WEAK-AND-NUMEROUS.

**Hypothesis.** F-14 closed the supervised class with a sentence and a rule. The sentence: all seven
priced axes ran on the same 38 columns, every one a transform of 5-minute OHLCV, so *"this panel
does not support a t = 2 book"*. The rule, F-14 (a): **measure a candidate's univariate IC and its
correlation against the incumbents BEFORE fitting anything.** F-15 is the first F iteration to leave
the trade-bar store, and the first to make **the gate the primary deliverable** rather than a
post-run diagnostic. Two channels, neither computable from OHLCV at any width:

- **A, the auction tape, per name.** `/v2/stocks/auctions` (Alpaca SIP, one request per symbol,
  2015-12 to 2026-09-11) returns the official opening and closing **cross** - a single batch print
  struck by an imbalance mechanism. Two things live in it that no bar can say: the **size** of the
  cross (how much stock the open/close had to clear - index, rebalance, MOC flow) and the **gap
  between the cross print and the continuous tape** around it (how far the auction reached to
  clear). 14 columns.
- **B, the SPY 0DTE chain, market-level.** `data/options/odte/SPY`, 1,891 same-day expirations at
  5-minute bid/ask, already local. The ATM straddle over spot **is** the market's forecast of
  |move to today's close| in bps; no trade bar contains a forecast. 5 columns.

`scripts/ml_f15.py`, **6 ledger rows** under `intraday/f15_altstore` (4 pre-registered, 2 post-run),
cells in `data/f1/f15_arms.csv`, gate in `f15_gate.csv`, per-year ICs in `f15_post.csv`, importance
in `importance_f15.csv`. Eight clauses pre-registered in the module docstring including clause 0,
the prior, written before a number was read: *"`auc_ojump` ~0.9 correlated with `gap` and DROPPED;
`auc_cdrift` and the size surprises survive with |IC| 0.002-0.006; `both` lands within +/-$120 of
base's $306/day at t +1.3 to +1.7; refused on clause 5."* Run with
`INTRADAY_DATA_DIR=data/minute_alpaca`, `_splits.json` confirmed present. **No shipped or
runner-loaded file was touched**, so no deploy gate and no `--replay` is owed.

**(0) A defect found and fixed mid-run, and it is worth recording because it would have inverted
the headline.** Family A was first built on `intraday_common.UNIVERSE` - the 16-name *deployed
sleeve*. But `sweep_f1` builds its panel from **every** symbol in the Alpaca store minus
`f1.EXCLUDE`: **56 names**, and the book ranks over all 56. Coverage was 27.08% and, worse, the
`cs_*` ranks were computed over a different and narrower cross-section than the one being traded.
On that wrong cross-section `auc_ofade` read IC **-0.0131 (t -7.7)** and `auc_cdrift` **+0.0080
(t +4.5)**; on the correct 56 they read **-0.0069 (t -4.9)** and **+0.0004 (t +0.3)**. The second of
those is the difference between a finding and nothing. `panel_symbols()` now reads the panel itself
rather than any hand-maintained list, and coverage is **99.64%**.

**(1) Clause 1 identity is exact.** Alt columns are merged, never inner-joined; the 0.36% of rows
with no auction print and the 28.89% with no 0DTE session are kept carrying NaN. `base` reproduces
the frozen F-8 model to the printed digit: mean rank IC **+0.01030**, gross **4.256** bps, cost
**2.724**, net **$305.7/day**, t **+1.474** on 1,933 sessions.

**(2) THE GATE, and the prior was wrong in both directions.** Per-timestamp rank IC over the 8 test
years, and max median |Spearman| against each of the 38 incumbents. **19 of 19 survive** - not one
candidate was >= 0.50 correlated with an incumbent carrying a larger |IC|, which is the opposite of
F-14, where the whole flow family was a 0.645-correlated copy of `r6`.

| column | rank IC | t | max abs rho vs the 38 | against | that column's IC |
|---|---|---|---|---|---|
| **`auc_ofade`** (first 5 min of tape vs the opening cross) | **-0.00690** | **-4.9** | **0.295** | `r_sess` | -0.00387 |
| `auc_ojump` (cross-to-cross overnight) | -0.00532 | -3.3 | **0.905** | `gap` | **-0.00086** |
| `auc_osz_z` (opening cross size surprise) | +0.00326 | +2.8 | 0.347 | `vol_rel6` | +0.00427 |
| `auc_osz_adv` | -0.00151 | -0.8 | 0.345 | `atr` | -0.00586 |
| `auc_csz_z` (prior close cross size) | +0.00133 | +1.1 | 0.156 | `vol_rel6` | +0.00427 |
| **`auc_cdrift`** (prior close cross vs last tape print) | **+0.00041** | **+0.3** | 0.142 | `gap` | -0.00086 |
| *(reference)* `prev_ret` | -0.01310 | -7.0 | - | - | - |
| *(reference)* `vwap_atr` | -0.01112 | -7.0 | - | - | - |

Clause 0 named `auc_cdrift` as the likely survivor and it is **dead on arrival** (t +0.3). What
carries is the column the prior did not name: **`auc_ofade`**, how far the first five minutes of
continuous tape travelled away from the opening cross print. And `auc_ojump` is kept **by the rule
as written** despite 0.905 correlation with `gap`, because `gap`'s own IC is **-0.00086** against
`auc_ojump`'s **-0.00532** - the cross-to-cross jump carries **6x** what the bar-based gap does.
Measured directly post-run: their residual, `auc_ojump - gap`, has IC **-0.00547 (t -3.38)**. *The
part of the overnight move that only the auction print knows is the part that predicts.*

**(3) Clause 3b: the market-level channel needed a different screen, and that is a methodological
point the brief's framing hides.** A SPY-level column is constant across names at a timestamp, so
its per-timestamp rank IC is **undefined, not zero**, and clause 3a cannot screen it at all - which
also caught `m_auc_osz_z`/`m_auc_cdrift`, two family-A columns that are market-level by
construction. Screened instead on correlation with the regime already in use (SPY trailing 20-day
realised vol): `iv_strad` **+0.667**, `iv_rvgap` -0.299, `iv_d30` -0.264, `iv_skew` +0.192,
`iv_qi` +0.036. None reaches the 0.70 drop threshold, so all 7 pass to the fit. Clause 0 predicted
0.6-0.75 for the straddle and was right.

**(4) And the fit refused it anyway, on all three legs.** 1,933 out-of-sample sessions, 2019-2026,
one decision, decile 0.10, **turnover identical in every arm to the dollar ($1,995,861/day, spread
$0)**, so every bps column is like-for-like by construction.

| arm | features | mean rank IC | gross bps | cost bps | net $/day | t | yrs + | worst |
|---|---|---|---|---|---|---|---|---|
| **base** | 38 | **+0.01030** | 4.256 | 2.724 | **306** | **+1.47** | 5/8 | -51,431 |
| **alt** | 19 | +0.00137 | 0.658 | 2.657 | **-399** | **-2.52** | 2/8 | -40,162 |
| **both** | 57 | +0.00743 | 3.587 | 2.797 | **158** | **+0.80** | 4/8 | -44,020 |
| **both_scrambled** | 57 | +0.00864 | 4.210 | 2.722 | **297** | **+1.40** | 5/8 | -40,154 |

**Clause 5: REFUSE.** net t **+0.799** against 2.0 (FAIL), **4/8** years positive (FAIL), paired
`both - base` **-$148/day at t -0.913** (FAIL). Clause 0 predicted t +1.3 to +1.7 and was generous.

**(5) F-14's control reproduces exactly, so the loss is again the INFORMATION and not the width.**
19 columns permuted within each timestamp - every marginal, every cross-sectional dispersion and
every within-family correlation preserved, only the name destroyed - cost **-$9/day at t -0.07**,
statistically indistinguishable from adding nothing. 19 columns of **real** data cost **-$148/day**.

**(6) But the MECHANISM is new, because F-14's explanation is ruled out by (2).** F-14's flow
family lost because it was a 0.645-correlated, noisier copy of `r6`. Nothing here is a copy: the
best survivor is 0.295 correlated with its nearest incumbent. And per-year univariate IC
(`f15_post.csv`) shows it is not F-14 (6)'s sign-instability either - **`auc_ofade` carries the same
sign in 7 of 8 test years**, which is exactly what `prev_ret` (7/8) and `r6` (7/8), the two best
incumbents, manage. It is orthogonal, it is real, it is stable, and the book still got worse.

**(7) The parsimony arms, POST-RUN and test-set-selected, and they identify the cause.** Barred
from clause 5 by construction - they cannot accept anything - and run only to separate *"the
auction tape carries nothing"* from *"19 columns carrying one signal dilute 38 carrying several."*
Same learner, same seed, same walk-forward, turnover still $0 apart:

| arm | features | gross bps | net $/day | t | yrs + | paired vs base | low-vol regime |
|---|---|---|---|---|---|---|---|
| base | 38 | 4.256 | 306 | +1.47 | 5/8 | - | -133 |
| both | 57 | 3.587 | 158 | +0.80 | 4/8 | -148 (t -0.91) | -38 |
| **lean3** (+`auc_ofade`, `x_`, `cs_`) | **41** | **4.643** | **365** | **+1.75** | **5/8** | **+60 (t +0.49)** | **+103** |
| lean1 (+`auc_ofade` raw only) | 39 | 2.940 | 28 | +0.13 | 5/8 | -278 (t -2.33) | -117 |

**The same family, the same data, the same learner: 19 columns cost -$148/day and 3 of those 19
columns gain +$60/day.** `lean3` posts the **highest gross this track has measured on this label**
(4.643 bps against base's 4.256) and is the only arm ever to be **positive in the low-vol tercile**
(+$103 against base's -$133), the regime F-8/F-11/F-12/F-14 all report as dead. It is still not
significant (paired t +0.49) and it is selected on the test window, so it proves a mechanism, not
an edge.

**(8) `lean1` is the other half of the mechanism and it is a warning about "just add the column".**
The *raw* column alone, without its market residual and its cross-sectional rank, reads **$28/day**
- worse than base by $278 at t -2.33. A column that helps as a triple hurts as a single. F-1's
original design gave every feature `x_`/`cs_` companions, and (8) is the first direct measurement
of why: the book ranks cross-sectionally, so a level the tree must itself convert into a rank is a
harder question than the rank.

**(9) Importance stability, the brief's second criterion, collapses exactly as in F-14.** Mean
pairwise Spearman of the yearly rankings: base **+0.434** (F-14's measurement), F-14's `both`
+0.036, **F-15's `both` +0.001** (-0.500..+0.339), with **no** feature in every year's top 10. The
alt family takes **18.2% to 81.2%** of positive importance (2024: 81.2%). A 19-column family is
not merely unhelpful - the tree genuinely spends on it, and what it spends on changes completely
every retrain.

**(10) Regimes, which the brief asks for explicitly.** Net $/day across terciles of SPY trailing
20-session realised vol: base -133 / +250 / +623; `alt` -458 / -775 / +35; `both` -38 / +244 /
**+180**; scrambled -149 / +216 / +646; `lean3` **+103 / +354 / +532**. `both` again does its
damage in the **high-vol** tercile, the only regime this forecast has ever been paid in - and
`lean3` is the first arm to earn in all three.

**(11) What was NOT tried, and it is not a choice.** F-15's own pre-registered favourite - per-name
implied skew and term structure from Theta - is **blocked**. The terminal answers `listening: true`
but every history/quote endpoint returns HTTP 403, *"requires a value subscription... you only have
a FREE subscription"*. This is already open in `research/BLOCKERS.md` as O-3, re-diagnosed and
priced by O-4 on 2026-09-12; F-15 adds a second track waiting on it and does **not** re-file it.
The local 0DTE store predates the lapse and reads fine, which is why family B exists at all.

**Decision.** **REFUSE** the pre-registered arm. Nothing deployed, nothing promoted,
`champion.json` untouched. `lean3` is filed as **F-16**, not adopted.

**What it changes for the loop.** Three rules, and one correction to F-14.
**(a) The F-14 gate is NECESSARY and NOT SUFFICIENT, and F-15 is the counterexample.** F-14's rule
screens out the *redundant*. It says nothing about the *weak and numerous*, and that is what beat
this run: 19 columns, 1 of them above the incumbent floor, and the 18 below it cost $208/day of
gross by diluting the tree's budget. **Add a second leg: a candidate FAMILY is admitted only at the
size justified by how many of its members clear the incumbent floor** - here, admit 3, not 19.
Every track adding features should count survivors before adding a family.
**(b) Add a column as a TRIPLE or not at all.** (8): the raw level alone is worse than nothing
(-$278/day, t -2.33) while the raw + market-residual + cross-sectional-rank triple is the best
arm measured (+$60/day). For a book that ranks cross-sectionally, handing the tree a level and
asking it to infer the rank is a strictly harder question than handing it the rank.
**(c) Build alt features on the PANEL'S universe, not the sleeve's.** (0) cost this run a rebuild
and would have inverted the headline had it gone unnoticed. Read the universe from the artifact
being joined to, never from a constant that happens to be nearby.
**(d) The correction to F-14's closing statement.** F-14 wrote *"this panel does not support a
t = 2 book"* and inferred that no new column could help. That inference is now too strong: the
auction tape is a store outside 5-minute OHLCV, it holds a column that is orthogonal (rho 0.295),
significant (t -4.9) and sign-stable (7/8 years), and the 3-column form of it posts the highest
gross and the first positive low-vol regime this track has measured. **The ceiling is real, but
F-14 attributed it entirely to the market and part of it is the panel.** What is still true, and
now on stronger evidence, is that **no arm of any construction has reached t = 2.0**, and `lean3`
at +1.75 post-run and test-set-selected is not a counterexample to that.

**Next.** **F-16**, and it must be pre-registered against the one thing (7) cannot answer.
`auc_ofade` was chosen *after* seeing the test window, so `lean3`'s +$60/day is a selection
artefact until the selection itself is made causally. F-16: run the gate **inside** the
walk-forward - at each retrain, screen every candidate on train+validation only, admit the
survivors above the incumbent floor, and fit. If the causal selection reproduces `lean3`, the
auction tape is a real addition to the panel and the F-14 closing statement needs rewriting; if it
does not, then (7) is a test-set artefact and F-14 stands as written. That is one file and roughly
40 minutes of compute, and it is the cheapest remaining question in the F scope.

---

## 2026-09-13 - F-14: the seventh axis was never a construction, it was the 38 columns. Bar-level order flow is the one channel in this store that is not a transform of 5-minute OHLCV, and it makes the book strictly worse - while 20 columns of SCRAMBLED flow cost nothing. Refused. The feature-set axis closes, and with it the panel.

**Hypothesis.** F-12 closed with a sentence that names its own binding constraint: *"this **feature
set** on this panel does not support a t = 2 book by any construction available in this scope."*
Six axes are now priced - construction (F-7), label horizon (F-8), breadth (F-10), cost-aware
selection (F-11), sizing and label family (F-12), decision frequency (F-1's own 11-slot grid) - and
**every one of them ran on the same 38 columns**, `sweep_f1.FEATURES`, unchanged since F-1. All 38
are deterministic transforms of **5-minute OHLCV**. What that matrix cannot contain is **direction
of flow**: a 5-minute bar says where the price ended (`r6`) and how much traded (`vol_rel`), and
nothing about which side lifted. The 1-minute bars underneath the panel can say it, approximately,
and the panel throws them away at `to_5min()`. So F-14 builds the two standard bar-level flow
proxies at 1-minute resolution - the **tick rule** (sign of each minute's return times its volume)
and **close-location value** (Chaikin money flow) - plus the path-shape and liquidity columns the
5-minute frame averages away, and asks the one question the track has never asked: **is the IC
ceiling this panel keeps hitting a property of the market, or of the features?**

`scripts/ml_f14.py`, **4 DIAGNOSTIC ledger rows** under `intraday/f14_features` (cells in
`data/f1/f14_arms.csv`, features in `data/f1/f14_flow.parquet`, predictions in `f14_preds.parquet`,
importance in `importance_f14.csv`). Seven clauses pre-registered in the module docstring including
clause 0, the prior, written before a number was read: *"`flow` alone scores +0.003 to +0.008,
`both` scores +0.022 to +0.025 against base's +0.021, the book's t moves from +1.474 to roughly
+1.6, refused on clause 5."* **20 new features** (`ofi5/30/sess`, `updn30`, `clv5/30/sess`,
`eff5/30`, `amihud30`, `dvol30`, three SPY copies, two residuals, four cross-sectional ranks), all
causal: the window for a decision on the bar starting 09:55+30k ends at the **1-minute bar starting
T+4**, the last minute of the decision bar, and nothing reads the fill bar. Rolling sums are
cumulative **within the session**, so the 30-minute window at slot 0 is exactly 09:30-09:59 and no
feature at any slot reads the prior day's tape. Three arms at constant everything else -
`base` (38), `flow` (20), `both` (58) - same `GRID["mid"]` learner, same seed, same expanding
walk-forward, same label `y_close`, same 8 test years, **no hyperparameter search**. Run with
`INTRADAY_DATA_DIR=data/minute_alpaca`, `_splits.json` confirmed present. **No shipped or
runner-loaded file was touched**, so no deploy gate and no `--replay` is owed.

**(1) Clause 1 identity is exact.** Flow is **merged, never inner-joined** - coverage is 98.47% and
the 24,395 uncovered rows are kept carrying NaN (the learner handles NaN natively) - so the row set
is F-8's exactly and the arms are read at constant sample. `base` reproduces the frozen F-8 `close`
model to the printed digit: mean rank IC **+0.01030** (F-12 (2)'s own re-measurement), gross
**4.256** bps, cost **2.724**, net **$305.7/day**, t **+1.474** on 1,933 sessions.

**(2) The flow family carries nothing, and the book it builds alone is significantly negative.**

| arm | features | mean rank IC | gross bps | cost bps | net $/day | t | yrs + | worst |
|---|---|---|---|---|---|---|---|---|
| **base** | 38 | **+0.01030** | 4.256 | 2.724 | **306** | **+1.47** | 5/8 | -51,431 |
| **flow** | 20 | **+0.00006** | 0.943 | 2.464 | **-304** | **-1.93** | 2/8 | -34,061 |
| **both** | 58 | +0.00843 | 3.214 | 2.682 | **106** | **+0.53** | 5/8 | -56,295 |
| **both_scrambled** | 58 | **+0.01114** | 4.403 | 2.724 | **335** | **+1.58** | 5/8 | -45,382 |

`flow` alone is rank IC **+0.00006** - zero to four decimal places, negative in 4 of its 8 test
years. Clause 0 predicted +0.003 to +0.008 and the prior was too generous.

**(3) Adding it to the 38 makes the model worse, and the paired test is unambiguous.** Turnover is
$1,995,861/day in every arm (one decision, decile 0.10, in and out), so the bps columns are
like-for-like. Paired per session, F-11's standing rule:

| comparison | net $/day | paired t | gross t | cost t |
|---|---|---|---|---|
| flow - base | **-609** | **-2.70** | -2.93 | +23.63 |
| both - base | **-199** | -1.51 | -1.57 | +5.22 |
| **both_scrambled - base** | **+29** | **+0.29** | +0.29 | +0.04 |

**Clause 5: REFUSE.** `both` fails on t (+0.528 against 2.0) and on the paired test (-1.506); the
years-positive leg passes at 5/8 and is the only one that does.

**(4) Clause 6 is the finding. Twenty columns of SCRAMBLED flow are free; twenty columns of REAL
flow cost $199/day.** The control permutes each flow column **within its timestamp**, preserving
every marginal, the cross-sectional dispersion and the within-family correlation, destroying only
the name it is attached to. It lands at IC **+0.01114** and **+$29/day, t +0.29** against base -
statistically indistinguishable from adding nothing, which is exactly what 20 noise columns should
do to a tree with `max_features=0.7`. So the degradation in `both` is **not** dimensionality, not
capacity, not overfitting the extra width: **it is the information in the flow columns.** The model
is misled by the real flow and untroubled by the fake.

**(5) POST-RUN, and it explains (2)-(4) completely: the flow columns that are NEW are
uninformative, and the flow columns that are INFORMATIVE are not new.** Univariate per-timestamp
rank IC against `y_close` over the test window, and each column's maximum |Spearman| against the
38 it was added to:

| column | rank IC | t | max corr vs the 38 | against |
|---|---|---|---|---|
| `ofi30` | **-0.00928** | **-7.1** | **0.645** | `r6` |
| `x_ofi30` | -0.00921 | -7.0 | 0.441 | `cs_r6` |
| `ofi_sess` | -0.00858 | -6.1 | 0.660 | `r_sess` |
| `clv30` | -0.00667 | -5.2 | 0.558 | `r6` |
| `updn30` | -0.00572 | -4.3 | 0.637 | `r6` |
| `amihud30` | -0.00450 | -4.0 | **0.222** | `vol_rel6` |
| `dvol30` | **+0.00252** | +1.6 | 0.445 | `atr` |
| `eff5` | **+0.00124** | +1.1 | **0.339** | `rng_atr` |
| `eff30` | **+0.00028** | **+0.3** | **0.161** | `vol_rel` |
| *(reference)* `r6` | -0.00966 | -5.3 | - | - |
| *(reference)* `vwap_atr` | **-0.01131** | **-7.1** | - | - |

The directional columns **do** predict - they predict **reversal**, significantly (t -4 to -7):
names bought over the last 30 minutes underperform to the flatten. But `ofi30`'s IC of -0.00928 is
**the same number as `r6`'s -0.00966**, they are **0.645** correlated, and `vwap_atr` - already in
the panel since F-1 - beats both at -0.01131. Meanwhile the columns that are genuinely orthogonal
(`eff30` median correlation 0.012, `eff5` 0.004, `amihud30` 0.021, `dvol30` 0.015) have IC
**+0.00028, +0.00124, -0.00450, +0.00252**. Stated as one sentence: **the tick rule is a 0.65
correlated, noisier copy of the 30-minute return, and everything about it that the return is not,
is noise.** That is why the tree does worse with it - it is offered a second, degraded measurement
of a signal it already has, spends budget on it, and dilutes the original.

**(6) And the pooled sign is not a sign a walk-forward can trade.** (5) is measured on the test
window pooled; `flow`'s *causal* yearly ICs are +0.011, +0.004, **-0.004**, +0.001, **-0.006**,
**-0.005**, **-0.004**, +0.003 - the learner picks the reversal up in 2019-2020 and it inverts for
the rest of the sample. A full-period univariate t of -7.1 and a causal mean IC of +0.00006 are
both true, and the gap between them is the whole difference between a statistic and a trade.

**(7) Feature-importance stability, the brief's second criterion, and it collapses.** Permutation
importance on each retrain's validation year, `both` arm:

| model | mean pairwise Spearman | in every year's top 10 |
|---|---|---|
| risk model (F-12, `\|y_close\|`) | +0.772 | `vol_rel`, `vol_rel6` |
| return model (F-8, 38 features) | +0.434 | none |
| **return model + flow (F-14, 58)** | **+0.036** (-0.418..+0.323) | **`gap` only** |

The flow family takes **2.7% to 23.7%** of positive importance (mean **13.5%**), so the tree is
genuinely spending on it - and the ranking of *all* 58 features goes from weakly stable to
**uncorrelated year to year**. Adding a redundant family did not just fail to help; it destabilised
the attribution of the features that were working. And the flow members that rank highest across
the retrains are `dvol30` (mean rank 19.8) and `amihud30` - the two **non-directional** ones,
consistent with (5).

**(8) Regimes, which the brief asks for explicitly.** Base -133 / +250 / +623 $/day across terciles
of SPY's trailing 20-session realised vol; `both` -347 / +250 / **+221**; scrambled -96 / +331 /
+593. The damage is concentrated in the **high-vol** tercile, which is the only regime this
forecast has ever been paid in (F-8, F-11, F-12 (9) all report it) - the flow family is worst
exactly where the book's entire edge lives.

**Decision.** **REFUSE.** Nothing deployed, nothing promoted, `champion.json` untouched.

**What it changes for the loop.** Two reusable rules, and one closing statement.
**(a) Check a candidate feature's correlation against the incumbent set BEFORE fitting anything.**
A new column that is 0.6 correlated with an existing one and has a *smaller* univariate IC is not a
new signal, it is a measurement error on an old one, and a tree cannot tell the difference - it
will spend budget on it and lose. The two-line diagnostic in (5) - univariate IC and max |Spearman|
against the incumbents - would have predicted this entire file in under a minute, and it is cheaper
than any of the 32 walk-forward fits it took to confirm. Every track adding features should run it.
**(b) F-12's rule (b) generalises from signals to feature sets.** The scrambled-flow control is
what separates "the extra columns hurt" from "the information in them hurt", and here it is the
difference between a boring result and (4). Any feature-set change must be run against a
within-timestamp permutation of the columns it adds.
**(c) The closing statement.** The one information channel in this store that is not a transform of
5-minute OHLCV has now been tried, priced, and refused - so F-12's sentence upgrades from *"this
feature set does not support a t = 2 book"* to **"this panel does not."** Seven axes, eight
refusals, one IC ceiling at +0.01 to +0.02, and the ceiling is the market's, not the model's.

**Next.** Nothing in the F scope is open. F-11's standing test for reopening the supervised class -
*"a different instrument, a different frequency, or a different label family"* - is now spent on all
three (F-3 frequency, F-12 label family, F-2a/F-4 instrument) plus construction, cost, breadth,
sizing and, here, the feature set. **The supervised class on this universe is closed and should not
be reopened on new columns built from the same OHLCV store.** What is genuinely untried is a
different *store*: the panel has never seen a column that cannot be computed from trade bars at all
- options-implied skew and term structure per name (Theta, O-track's data), or true tape-level
signed volume. Filed as **F-15**, pre-registered and unread, and it is an O-track/D-track data
question before it is an F-track model question. F-13 (the universe question F-12 opened) remains
open and still belongs to A/D-track.

---

## 2026-09-12 - F-12: forecast the denominator. The risk model works (rank IC +0.53 against the return model's +0.02) and using it makes the book worse, because this forecast's alpha scales as vol^1.49 and inverse-vol sizing is a bet on vol^1.0. Refused. The sizing axis is bounded on BOTH sides and neither end reaches t = 2.

**Hypothesis.** F-11 closed the track with a standing sentence: reopening the supervised class
needs *"a different instrument, a different frequency, or a different label family - not another
construction on this one."* F-12 is the third. F-7 moved the book, F-8 the label's horizon, F-10
the breadth, F-11 the cost - **all four are the numerator of the P&L and none is the denominator
of the t**. And three separate runs have reported the same incidental fact without acting on it:
*the only feature family that survives a retrain on this panel is the volatility family*
(F-11 (10): `vol_rel6` rank mean 6.8, `m_rvol_ratio` 7.5, `rvol_ratio` 7.9). A model asked for
direction keeps reaching for the volatility features, which is what a model does when the thing
it can resolve is not the thing it was asked for. So F-12 **fits a second model on a new label
family** - `|y_close|`, the absolute demeaned move to the flatten, i.e. the per-name risk
contribution of a dollar-neutral book - and spends it on **sizing** rather than selection:
`w_i proportional to sigma_hat_i^-p`, p in {0, 0.5, 1, 2}, p = 0 being F-8 exactly and **p = 1
the pre-registered primary** (the optimum is alpha/sigma^2, so p = 1 is right when alpha scales
with vol and p = 2 when it is constant; the two bracket every plausible view).

`scripts/ml_f12.py`, **22 DIAGNOSTIC ledger rows** under `intraday/f12_risksize` (18 pre-registered
cells in `data/f1/f12_risksize.csv`, 4 post-run). Eight clauses pre-registered in the module
docstring including clause 0, the prior, written before a number was read: *"sd down ~15%, mean
down ~10%, t from +1.47 to roughly +1.6, refused on clause 5."* The **return** predictions are
re-read frozen from `data/f1/f8_preds.parquet` - nothing about F-8's forecast is re-fitted - and
the only new fitted object is the risk model (`data/f1/f12_risk.parquet`, same 38 features, same
`GRID["mid"]` learner, same expanding walk-forward, 8 test years). **No shipped or runner-loaded
file was touched**, so no deploy gate and no `--replay` is owed. Run with
`INTRADAY_DATA_DIR=data/minute_alpaca`, `_splits.json` confirmed present.

**(1) Clause 1 identity is exact and this file has no turnover confound at all.** p = 0
reproduces F-8 to the printed digit: gross **4.256**, cost **2.724**, net **$305.7/day**, t
**+1.474** on 1,933 sessions. And uniquely among F-track constructions, **turnover is identical
in every cell to the dollar - $1,995,861/day, spread $0** - because each side still sums to
gross/2 on entry and to zero at the flatten however the dollars are split inside it. Every bps
column below is like-for-like by construction rather than by control.

**(2) The risk model is a genuinely good forecast, and 32x the return model's.** Per-timestamp
rank IC on `|y_close|`, by test year: **+0.3065 to +0.3563, mean +0.3302** (IC t-stats +100 to
+146), level R^2 **+0.251 to +0.350, mean +0.315**. The same walk-forward on the *signed* label
- F-8's own `close` predictions, re-measured here - gives mean rank IC **+0.01030**, and it is
**negative in 2026 (-0.00755)** while the risk model's worst year is +0.3065. Predicted session
risk runs **BRK.B 47 bps to SOXS 242 bps, a 5.1x cross-sectional spread**, which is the
dispersion F-8's equal-weight book was ignoring.

**(3) The lever does exactly what it was built to do on the risk side.** 1,933 out-of-sample
sessions, 2019-2026, turnover constant:

| p | eff. N | gross bps | cost bps | net $/day | t | sd $/day | worst |
|---|---|---|---|---|---|---|---|
| **0 (= F-8)** | 11.4 | 4.256 | 2.724 | **306** | **+1.47** | 9,118 | -51,431 |
| 0.5 | 10.9 | 3.708 | 2.580 | 225 | +1.31 | 7,575 | -37,352 |
| **1 (primary)** | 9.9 | **3.267** | 2.469 | **159** | **+1.06** | **6,622** | -32,402 |
| 2 | 7.8 | 2.656 | 2.326 | 66 | +0.49 | 5,923 | -27,421 |

**sd falls 27%** at p = 1 and 35% at p = 2, monotonically, and the worst day improves from
-$51,431 to -$27,421. Clause 0 predicted 10-25%; the risk side of the prior was right.

**(4) And the mean falls twice as fast, so it is refused.** **t +1.058 against a hurdle of 2.0**,
5/8 years positive. **REFUSE.** Clause 6(a): mean **x0.521**, sd **x0.726**, t **x0.718** - the
entire loss is the mean channel. Paired per session (clause 6(b)), p = 1 minus p = 0:

| component | mean $/day | paired t |
|---|---|---|
| gross given up | **-197** | **-2.28** |
| cost saved | +51 | +42.38 |
| **net** | **-146** | **-1.69** |

This is the **exact mirror of F-11**. There the cost saving was arithmetic (t +41.67) and the
gross it bought was noise (t -0.48); here the cost saving is the same arithmetic (t +42.38) and
**the gross given up is the significant term** (t -2.28). Same standing rule, opposite verdict,
and only the paired test shows it.

**(5) Clause 4(ii) FAILS, and the way it fails is the finding.** Scrambling `sigma_hat` per
timestamp keeps the weight *dispersion* and assigns it to the wrong names. Random dispersion
costs the book almost nothing - **t +1.400 +/- 0.065** against equal weight's +1.474 - while the
**correct** risk forecast costs it a great deal, **t +1.058**. *Sizing unequally is nearly free;
sizing by this forecast is expensive.* The better the risk forecast, the worse the book, because
it is better at finding exactly the names the book should be overweight. Clause 4(i) passes
(scrambled alpha under inverse-vol sizing earns gross t **-0.13**), so the lever is not a static
short-the-leveraged-sleeve tilt.

**(6) The free baseline beats the ML model at every rung.** Trailing 20-bar ATR - the panel's own
causal range feature, available to any desk for nothing - gives **t +1.41 / +1.28 / +0.93** at
p = 0.5/1/2 against the model's +1.31 / +1.06 / +0.49, and paired, `p1 - atr_p1` is **-$35/day at
t -1.55**. sigma_hat and atr are Spearman **+0.945** correlated, so the ML model is the same
object plus a refinement, and **the refinement is the part that loses money**. That is the
sharpest version of (5).

**(7) The elasticity, measured. This is the reusable number.** Clause 0 stated the analytic floor
in advance: by Cauchy-Schwarz, inverse-vol weighting is *weakly better* than equal weighting
whenever alpha is proportional to sigma, so a loss requires alpha to rise with vol **faster than
linearly**. Post-run, over 21,940 held name-days:

| sigma quintile | n | sigma bps | realised alpha bps | t | alpha/sigma |
|---|---|---|---|---|---|
| 1 (quietest) | 4,388 | 60.6 | **-0.76** | -0.49 | **-0.0125** |
| 2 | 4,388 | 90.5 | 3.94 | +1.77 | 0.0435 |
| 3 | 4,388 | 123.5 | 6.08 | +1.98 | 0.0492 |
| 4 | 4,388 | 170.2 | 10.20 | +2.40 | 0.0599 |
| 5 (loudest) | 4,388 | 275.2 | **20.51** | +3.00 | **0.0745** |

**log-log slope beta = +1.494.** Break-even for inverse-vol sizing is beta = 1. And the
`alpha/sigma` column - the per-name information ratio - **rises monotonically across the whole
range**: the forecast has *no edge at all* in the quietest fifth of its own holdings (-0.76 bps,
t -0.49) and its edge per unit of risk is 6x larger in the loudest. Harmonic/arithmetic mean of
sigma over held name-days is 0.751, which is the mean ratio the linear case predicts; the mean
actually fell to 0.521, i.e. **31% more than beta = 1 allows**. This is the same volatility
finding F-8 and F-11 reported as a regime split (low vol dead, high vol paying), measured in the
cross-section instead of the time series, and it says the two are one phenomenon.

**(8) The other direction is better and still does not clear the hurdle - which bounds the axis.**
Post-run and explicitly barred from clause 5 (test-set-selected, no control): p = -1 tilts *into*
the loud names and reads net **$499/day at t +1.57**, paired **+$194/day, gross t +2.03** - a
significant gross gain, unlike F-11's. But sd goes **9,118 -> 14,029** and the worst day
**-$51,431 -> -$82,537**, so t moves only +0.10. **The full sizing ladder p in [-1, 2] spans t
from +0.49 to +1.57 and never touches 2.0.** The axis is bounded on both sides.

**(9) Regimes, which the brief asks for explicitly.** Risk sizing makes the dead regime deader.
Low vol **-$69 -> -$200 -> -$299/day** at p = 0/1/2; mid vol $452 -> $272 -> $177; high vol $534
-> $407 -> $320. It helps nowhere. F-8's and F-11's volatility finding stands and (7) explains it.

**(10) Feature-importance stability, the brief's second criterion, and the contrast confirms the
premise.** Permutation importance over the same 8 test years and 38 features, both models:

| | mean pairwise Spearman | top-10 overlap | in the top 10 of every year |
|---|---|---|---|
| return model (F-8, `y_close`) | +0.434 (0.147..0.798) | 44% | **none** |
| risk model (F-12, `\|y_close\|`) | **+0.772** (0.598..0.957) | **61%** | **`vol_rel`, `vol_rel6`** |

The risk model's top two features are `vol_rel` (rank mean **1.9**, rank sd 1.0) and `vol_rel6`
(**2.2**, sd 1.4) - stable to within one rank across eight retrains, against a return model where
nothing survives. **And the return model's own most-persistent feature is `vol_rel6`** (rank mean
6.8), i.e. the #2 feature of the risk model: the direction model has been reaching for the risk
model's inputs all along, which is the observation F-12 was built on and is now measured rather
than inferred. **That stability bought nothing.** F-11 asked whether unstable importance was a
symptom of a weak forecast; the answer here is that the stable object is simply not the one the
book needs, and a forecast can be 32x more accurate, 1.8x more stable, and strictly harmful.

**Decision.** **REFUSE.** Nothing deployed, nothing promoted, `champion.json` untouched.

**What it changes for the loop.** Two reusable rules. **(a) Risk parity is a bet on beta = 1.**
Equal-risk sizing is only optimal when a forecast's alpha scales linearly with the name's own
volatility; measure the log-log elasticity of realised alpha on predicted risk *before* applying
any inverse-vol overlay, and if beta > 1 the overlay is a tax. This applies to every sleeve in
this repository, including the daily champion and the deployed intraday `active` book, neither of
which has ever measured its own beta. **(b) A better forecast of the wrong quantity is worse than
no forecast of it.** The scrambled-sigma control here beat the real one: random dispersion cost
0.07 of t, the correct risk forecast cost 0.42. Any future overlay must be run against a
*scrambled version of its own signal*, not only against a null book.

**Next.** The label-family axis is now priced alongside the other five, and with (8) the sizing
axis is bounded on both sides. The honest reading is that **this feature set on this panel does
not support a t = 2 book by any construction available in this scope.** The one direction (7)
opens that is not a construction is a *universe* question rather than a model question - the
forecast's edge is concentrated where beta is largest and is negative in its own quietest
quintile - but that is A-track/D-track territory (which names belong in the sleeve), not F-track.
Filed as **F-13** for whoever wants it, pre-registered and unread.

---

## 2026-09-12 - F-11: rank on alpha net of the name's own round trip. The cost saving is real to five decimal places, the gross it buys back is pure noise, and the improvement in t is therefore not an improvement at all. Refused. The cost axis closes.

**Hypothesis.** F-8 and F-10 both tried to make the numerator bigger - a better label, then more
breadth. Neither touched the other side of the subtraction, and that is where most of the money
is: **F-8 pays away 64% of its gross as cost** (4.256 bps per dollar turned against 2.724). The
cost is not a constant of the book. IBKR charges $0.005 per **share**, so a round trip costs
`2*1.5 + 2*50/price + 0.206 + 1.98/price` bps of the position, and on this universe that runs
**3.40 bps (TMO at $516) to 11.08 bps (SOXS at $13)** - a 7.7 bps spread against a gross of ~8.5
bps of position. **One name's round trip can eat the entire edge and another's costs nothing.**

And a plain decile walks into it: ranking on predicted alpha alone buys the widest predicted
moves, which here are the low-priced leveraged and reverse-split names. F-7 measured the premium
from the other side ("1.7 bps of the 2.4 bps of extra cost is selection, not construction") and
its conviction gate made it worse **by design**; the inverse has never been tried. F-11 changes
the ranking and nothing else - `long = pred - lambda*c_i`, `short = -pred - lambda*c_i`, with
**lambda = 1 the economically correct value** (both terms are basis points of the same position,
so lambda = 1 is literally "rank on net alpha") and therefore the primary cell, fixed before any
number was read.

`scripts/ml_f11.py`, **13 DIAGNOSTIC ledger rows** under `intraday/f11_costaware` (the 12 control
cells are in `data/f1/f11_costaware.csv`). Nine clauses pre-registered in the module docstring,
including clause 0, the prior, written before a number was read: *"a partial win - cost down ~0.4
bps, gross down ~0.3 bps, edge up ~0.1 bps, t landing near 1.6, better and still under the
hurdle."* **Nothing is re-fitted**: F-8's frozen walk-forward predictions are re-read and only the
*ranking* changes. **No shipped or runner-loaded file was touched**, so no deploy gate and no
`--replay` is owed. Run with `INTRADAY_DATA_DIR=data/minute_alpaca`, `_splits.json` confirmed
present.

**(1) Clause 1 identity is exact.** lambda = 0 reproduces F-8 to the printed digit: gross
**4.256**, cost **2.724**, net **$305.7/day**, t **+1.474** on 1,933 sessions.

**(2) The lever does what it was built to do, and the ladder has a genuine interior optimum.**
1,933 out-of-sample sessions, 2019-2026, turnover held at $1,995,861/day at every rung:

| lambda | gross bps | cost bps | edge bps | net $/day | t | sd $/day |
|---|---|---|---|---|---|---|
| 0 (= F-8) | 4.256 | 2.724 | 1.532 | 306 | +1.47 | 9,118 |
| 0.25 | 4.349 | 2.520 | 1.829 | 365 | +1.79 | 8,985 |
| 0.5 | 4.309 | 2.398 | 1.911 | 381 | +1.93 | 8,690 |
| **1 (primary)** | **4.063** | **2.250** | **1.813** | **362** | **+1.88** | 8,457 |
| 2 | 4.178 | 2.090 | 2.089 | 417 | +2.26 | 8,101 |
| 4 | 3.557 | 1.942 | 1.616 | 322 | +1.89 | 7,513 |
| 8 | 3.080 | 1.841 | 1.238 | 247 | +1.57 | 6,934 |

Cost falls **monotonically, 2.724 to 1.841** - and 1.5 bps of that is slippage, a shipped
constant, so the ~1.22 bps commission-and-fees term is cut by **72%**. The mechanism is exactly
the one claimed: name-days held move **SOXS -634, PLTR -325, INTC -210, UBER -206** and **NOW
+413, COST +410, AVGO +338, LLY +285**, i.e. the book stops renting the most expensive names.
Clause 0's prior was close to right and if anything pessimistic (cost -0.47, gross -0.19, edge
+0.28, t 1.88).

**(3) And it is refused, on the clause fixed before the run.** Clause 5 reads **lambda = 1 only**:
**t +1.881 against a hurdle of 2.0**, 5/8 years positive against a hurdle of 5. **REFUSE.** The
best cell on the test set is lambda = 2 at **t +2.26**, and clause 5 forbids reading it - it is
selected on the same sessions it is scored on, and section (4) says why that matters more than
usual here.

**(4) The finding is the paired test, and it deflates everything above.** Comparing two separately
noisy t's (+1.47 against +1.88) is the wrong statistic when both books trade the same sessions.
Paired per session, lambda = 1 minus lambda = 0:

| component | mean $/day | paired t |
|---|---|---|
| cost saved | **+95** | **+41.67** |
| gross given up | -39 | -0.48 |
| **net** | **+56** | **+0.70** |

**The cost saving is deterministic - t +41.67, it is arithmetic on a known price - and the gross
it costs is indistinguishable from noise.** The net improvement is therefore **+$56/day at t
+0.70, positive on only 45% of sessions**: the median session is *worse* and the mean is carried
by a right tail. So "t 1.47 -> 1.88" is **not a measured improvement**; it is one draw of a
difference this data cannot resolve, and the same sentence disposes of the lambda = 2 cell's
+2.26. Split in half by time the paired delta is **+$42 (t +0.35)** on 2019-01..2022-10 and
**+$71 (t +0.67)** on 2022-11..2026-09 - same sign, same non-significance, in both halves.

**(5) Clause 4's control passes on both limbs, and coded as a gate this time.** (F-10's post-run
defect (i) was a clause written as a gate and coded as a remark.) Per-timestamp scrambled
predictions, 3 seeds per cell: the zero-forecast book's **gross stays at zero under cost-aware
ranking at every lambda** (mean gross t **-0.90 / -0.20 / -0.34 / -1.39**), so the lever is not a
static short-the-leveraged-sleeve tilt dressed up as a forecast. And the control's cost falls too,
2.236 to 1.998 - **50% of the real book's 0.475 bps drop** - which passes clause 4(ii) and also
explains the other half: the real book started at 2.724 against the control's 2.236, i.e. it was
carrying F-7's **+0.488 bps selection premium**, and lambda removes the premium *and* part of the
base. That is the mechanism claimed, measured from the null side.

**(6) Clause 6's decomposition says the change is a mean effect, which is the good direction.**
mean x1.184, sd x0.928, t x1.276 - 72% of the t change is the mean channel. Unlike F-10's breadth
curve, this is not a smoothing artifact. It is simply too small to resolve.

**(7) The blunt version is worse, and non-monotonically so.** Hard price floors at lambda = 0:
$25 -> net $286 (t +1.56), **$50 -> net $62 (t +0.39)**, $100 -> net $256 (t +1.56). A floor
throws the name out of the *universe*; lambda only makes it pay for its place, so a floor
destroys gross (2.25 bps at $50) that lambda keeps. **A continuous cost penalty strictly dominates
an eligibility filter** - the one clean, reusable result in this file.

**(8) The gate is the cell a live desk would actually want, and it still does not pass.** Trading
only names whose own net score is positive holds **4.5 names instead of 11.4** and turns
**$790k/day instead of $1.996M** - **40% of the turnover for 95% of the net** ($289/day, t +1.85),
at **6.214 bps gross per dollar turned**, the highest gross-per-dollar anywhere on this track
except F-7's conviction cell. If any F-track construction is ever revived for an execution-limited
book, this is the one; it is not revived here, because its t is 1.85.

**(9) Regimes, which the brief asks for explicitly.** The cost cut helps everywhere and does not
rescue the dead regime: low vol goes **-$69/day (t -0.22) to +$22/day (t +0.08)**, mid vol $452 ->
$464, high vol **$534 (t +1.28) -> $601 (t +1.60)**. F-8's and F-10's volatility finding stands -
low vol is flat at best - and the improvement is broad rather than concentrated in one third.

**(10) Feature-importance stability, the brief's second criterion.** Over F-8's 8 test years and
38 features: mean pairwise Spearman of the yearly rankings **+0.434** (min +0.147, max +0.798),
mean top-10 overlap between year pairs **44%**, and **no feature is in the top 10 of every year**.
The volatility family is what persists (`vol_rel6` rank mean 6.8, `m_rvol_ratio` 7.5,
`rvol_ratio` 7.9, `cs_rvol_ratio` 10.1) but each swings by 20-30 ranks across years. **The model
re-selects its inputs substantially at every retrain**, which is consistent with a forecast whose
IC is +0.02 and whose book cannot reach t = 2: there is a persistent volatility signal underneath
and a lot of year-specific noise on top.

**(11) Two defects in this file's own first cut, declared separately from the pre-registration.**
**(i) The units were wrong.** `sweep_f1.fit_predict` trains on `y * 1e4`, so **`pred` is already
in basis points**; the first cut multiplied it by 1e4 again, making lambda = 1 behave as
lambda = 1e-4 and flattening the whole ladder to within $14/day. **Clause 1 caught it** - the
identity check failed, the run was declared void by its own rule, and nothing was read. That is
the second time a clause written before the numbers has stopped a wrong result on this track.
**(ii) The greedy selection broke exact prediction ties in the opposite direction from F-8's
`argsort`**, which the tree emits often (identical leaf values); it moved the base cell by $5/day
and 0.03 of t on 316 of 1,933 sessions. lambda = 0 now delegates to F-8's own `_decile` so the
identity is exact by construction, and a `lambda 0 (greedy)` rung is reported beside it so the
ladder's first step is not read as a cost effect.

**Decision.** **REFUSE.** The cost axis is now closed, and it closes with a bound rather than a
verdict: cost is floored by slippage at 1.5 bps of turnover, lambda = 8 already removes 72% of
everything above that floor, and the book still reaches only t +1.57. **Removing the entire
commission dispersion cannot clear the hurdle, so nothing on this axis can.** Nothing deployed,
nothing promoted, `champion.json` untouched.

**What it changes for the loop.** The reusable rule is a paired one, and it is the twin of F-10's:
**an improvement that is a certainty on one side of a subtraction and noise on the other must be
tested paired on the shared sessions, not by comparing the two books' t's.** Here a cost saving
with t = +41.67 bought a net improvement with t = +0.70, because the gross it sacrificed has a
standard error twenty times its mean - and a side-by-side reading of 1.47 against 1.88 shows none
of that. The secondary rule is (7): **a continuous cost penalty dominates an eligibility filter**,
which applies to every sleeve in this repository that has ever considered a price or liquidity
floor.

**Next.** Nothing open on the ML track. F-1/F-3 priced the method, F-7 the book, F-8 the label and
horizon, F-10 the breadth, and F-11 the cost. All five axes of F-1's forecast are now measured and
the forecast clears its cost line by +1.8 bps per dollar turned and cannot reach t = 2 on the data
that exists. Reopening the supervised class needs a **new mechanism** - a different instrument, a
different frequency, or a different label family - not another construction on this one.

---

## 2026-09-12 - F-10: breadth does not buy the power F-9 assumed. 57% of the curve is a channel a zero-forecast book gets too, 43% is a channel clause 5 says reverses, and the only correctly-specified ceiling is 2.34. F-9 refused; the D track does not build a 500-name store on this rationale.

**Hypothesis.** F-8 closed the F track with a positive edge column (+1.532 bps per dollar turned)
and a refusal on power - t +1.47 where clause 7 asked for t > 2 - and parked its only reopening as
**F-9**: *"the pooled t is a breadth statistic as much as a length one... ~4x the breadth would
reach the same t on the ~1,900 sessions that exist. That is a request for a ~500-name Alpaca SIP
minute universe."* That sentence contains an untested assumption and it is the whole of F-9's case:
"4x the breadth reaches the same t" is the claim t ~ sqrt(N), which holds only for *independent*
contributors. A dollar-neutral decile book over the most liquid US equities shares a market, a
handful of sectors and, in the leveraged sleeve, literally the same underlying index. F-10 measures
the breadth curve on the 56 names **already on disk**, before the D track spends weeks paging a
500-name store out of Alpaca.

**Resumed, not started.** `scripts/ml_f10.py` was written in a prior run that was cut off with
114 of 129 simulations cached and no ledger rows or journal entry. This run finished the remaining
15 (the N=56 control and the 12 partition sub-books), found two defects in the file's own first
cut, fixed them, and recorded. **9 DIAGNOSTIC ledger rows** under `intraday/f10_breadth`. Nothing
is re-fitted and nothing is re-tuned: F-8's frozen walk-forward predictions are re-read and only
the *book's* universe is subsampled, so this measures the **diversification** channel of breadth
and not the training channel (clause 2/6a). **No shipped or runner-loaded file was touched**, so no
deploy gate and no `--replay` is owed. Run with `INTRADAY_DATA_DIR=data/minute_alpaca`, `_splits.json`
confirmed present.

**(1) Clause 1 identity is exact.** The full-universe cell reproduces F-8 to the printed digit:
gross **4.256**, cost **2.724**, net **$306/day**, t **+1.474** on 1,933 sessions. The run is valid.

**(2) The curve rises, and that is not the finding - what it is made of is.** 12 seeded subsets per
width, 1,933 out-of-sample sessions, 2019-2026:

| N | runs | gross bps | cost bps | net $/day | t mean | t sd |
|---|---|---|---|---|---|---|
| 8 | 12 | 3.591 | 2.835 | 150 | +0.267 | 0.642 |
| 12 | 12 | 3.361 | 2.367 | 197 | +0.588 | 0.892 |
| 16 | 12 | 4.271 | 2.772 | 298 | +0.872 | 0.950 |
| 24 | 12 | 3.456 | 2.407 | 209 | +0.765 | 0.734 |
| 32 | 12 | 4.049 | 2.716 | 266 | +1.051 | 0.350 |
| 40 | 12 | 3.993 | 2.601 | 278 | +1.218 | 0.328 |
| 48 | 12 | 4.539 | 2.778 | 351 | +1.519 | 0.254 |
| **56** | 1 | **4.256** | **2.724** | **306** | **+1.474** | - |

Fitted log-log slope **beta = +0.776**, which is *above* F-9's assumed 0.500 and would extrapolate
to **t = 8.94 at N = 500**. Taken at face value that funds F-9 outright. It should not be taken at
face value.

**(3) The decomposition is the iteration. t = mean / sd, and only one of those is breadth.**

| channel | log-log slope | share of the curve |
|---|---|---|
| t | +0.776 | 100% |
| mean (net $/day) | +0.334 | **43%** |
| sd (implied) | -0.441 | **57%** |

**43% of the curve is the book's mean improving with N** - $150/day at 8 names against $306 at 56,
with gross bps per dollar turned sloping +0.106 (clause 6a). That is not diversification; it is the
book selecting better out of a deeper cross-section. And it is precisely the channel **clause 5
pre-registered as running the wrong way on extension**: names 57-500 are less liquid, cost more per
dollar turned and carry weaker signal than the sleeve's deliberately-chosen 56. So the larger half
of the extrapolation rests on a channel that clause 5 says reverses.

**(4) Clause 4 fails, and it fails against the other 57%.** The pre-registered control - the same
curve on a per-timestamp scrambled prediction - was required to be "flat and indistinguishable from
zero at **every** N", on pain of "no extrapolation of it means anything". It is neither: it runs
**-1.54 at N=8 to -4.05 at N=48**, log-log slope of |t| **+0.408**. A book with **no forecast at
all** buys 0.408 of the real curve's 0.776 - and 0.408 sits right on top of the real book's sd
channel of 0.441. The two measurements agree, and together they say the smoothing half of the curve
is a property of the *construction*, not of the forecast. Both sub-tests fail: max |control t| =
4.05 against a threshold of 2, and the control slope is 0.408 against 0.25 x 0.776 = 0.194.

**(5) So the three estimators span the decision boundary and the quantity is not identified.**

| estimator | t(500) | ceiling t(inf) | status |
|---|---|---|---|
| (A) naive power law | 8.94 | none by construction | no ceiling exists in the form |
| (B) saturating fit | 4.285 | **191.7** | rho pinned at the 0.00000 boundary |
| (C) direct rho, as first shipped | 1.543 | 1.552 | **aggregation bug** |
| **(C) direct rho, corrected** | **2.166** | **2.344** | the only finite, correctly-specified one |

(B)'s rho = 0 is a **misspecification signature, not a measurement**: a saturating model is bounded
above by sqrt(N), the observed beta is +0.776, so the fit returns the least-saturating value it
owns. Its "ceiling" of 191.7 is the claim that 56 leveraged-and-liquid US equities have literally
zero common P&L factor, which (C) measures directly at **+0.1406 between disjoint sub-books**. The
regime table makes the non-identification plain: the same object fits rho **0.999 / 0.0119 / 0.0000**
across the causal SPY vol terciles, extrapolating to t(500) of **-0.20 / 1.95 / 3.37**. An estimator
that swings from -0.2 to 3.4 depending on which third of the sessions it is fed is not measuring a
structural constant. (Low vol is flat-to-negative at every width, which is F-8's volatility finding
again.)

**(6) Two defects in this file's own first cut, declared separately from the pre-registration.**
**(i) Clause 4 was written as a gate and coded as a remark** - the first cut printed the control
slope and then let clause 7 read (B) regardless. Applying a clause pre-registered before any number
was read is not a retro-fit; failing to apply it was the error. **(ii) Estimator (C) conflated
basket correlation with per-name correlation.** The partitions measure the correlation between two
*14-name sub-books*; the saturating model is parameterised on the correlation between two *names*.
Under equicorrelation corr(basket) = m*rho/(1+(m-1)*rho), so the per-name figure is **0.01155**, not
0.1406, and the first cut understated the ceiling by ~10x. **The correction moves (C) from 1.55 to
2.34 - from one side of the hurdle to the other, in the direction that makes the refusal harder**,
which is the direction an author's own correction should cut. It is applied in full.

**(7) The refusal, and it does not need the estimator dispute settled.** Clause 7 may not be
executed on (B), so it is applied to (C) corrected: **t(500) = 2.166, ceiling t(inf) = 2.344**. Even
the most favourable correctly-specified estimator caps the **entire program at t = 2.34 at infinite
breadth** - and by clause 5 every number here is an **upper bound**, because subsampling down from
56 measures a curve whose mean channel extension will degrade. A multi-week 500-name data build,
chasing a t = 2.0 hurdle, against a theoretical maximum of 2.34 before the haircut, does not repay
itself. **REFUSE F-9.** Consistency check on the same estimator: it over-predicts the small-N end
badly (model 0.685 at N=8 against an observed 0.267), so even (C) cannot reproduce the curve it sits
beside - one more reason not to spend weeks on its extrapolation.

**Decision.** F-9 is **refused and retired from the backlog**, not parked. The F track stays closed
on clause 8's terms. Nothing deployed, nothing promoted, `champion.json` untouched.

**What it changes for the loop.** This is the first item in the repository to refuse a *data
purchase* rather than a strategy, and the reusable rule is the decomposition: **a breadth or
sample-size curve must be split into its mean and its variance channel before it is extrapolated,
and the variance channel must be run against a zero-forecast control.** Here 57% of a curve that
looked like t ~ N^0.78 was available to a book with no forecast, and 43% was a selection effect
pointing the wrong way for the extension being argued for. Any future "more data would fix the t"
argument on this repository - and F-8's own power arithmetic was one - owes the same two columns.

**Next.** Nothing open on the ML track. If the supervised class is ever reopened it needs a new
mechanism, not more cross-section and not more history: F-1/F-3 priced the method, F-7 the book,
F-8 the label and horizon, and F-10 now prices the only scaling argument that was left.

---

## 2026-09-12 - F-8: fit the label the forecast actually has. The right label is worth 2.84x on gross per dollar turned and flips the book positive, and it still fails - not on cost this time, but on a power requirement this data set cannot meet. Refused. The track closes.

**Hypothesis.** F-7 closed every construction axis on F-1's forecast and left exactly one open, and
it was not a book axis: clause 2 measured that this feature set's IC **rises** with horizon
(+0.01133 at 30 minutes, +0.02064 at 3.5 hours, +0.02115 at 5 hours), so every F-7 construction was
harvesting a multi-hour signal with a model fitted to **the worst horizon that signal has**. F-8
changes the label and nothing else: same panel, same 38 features, same learner
(`sweep_f1.GRID["mid"]`, `random_state=0`), same walk-forward, same books, same costs.

`scripts/ml_f8.py`, **24 DIAGNOSTIC ledger rows** under `intraday/f8_label` (20 book x label cells,
4 scrambled controls). Eight clauses pre-registered in the module docstring - including clause 0,
the prior, written before a number was read: *"the honest prior is that F-8 finds IC ~+0.02 on a
longer label, converts it to ~3.5 bps per dollar turned, and fails a cost line that prices at
2.5-3.7."* **No shipped or runner-loaded file was touched**, so no deploy gate and no `--replay` is
owed. Run with `INTRADAY_DATA_DIR=data/minute_alpaca` (F-7's documented cost hazard); the module
prints the store it costed against and the run confirms `_splits.json` present.

**(1) The labels, and the one that mattered was not on the backlog's list.** Consecutive decision
slots chain exactly (`fwd[k]` ends where `fwd[k+1]` begins), so the h-interval label is the sum of
h consecutive `fwd` values inside one session, invalidated by any missing slot. The backlog asked
for h in {4, 7, 10}; those are defined on only 8, 5 and 2 of the 11 slots, which confounds horizon
with time of day and throws away 27%/55%/82% of the panel. So a fourth label was added and it is
the one that wins: **`close`, hold to the 15:30 flatten, horizon 11 - slot, defined at every slot**
(1,574,099 rows vs 285,252 for h10). It is also the only label that matches what the sleeve's
flatten actually does.

**(2) The label ladder is what this iteration is worth keeping.** Same book, same turnover
($1,995,861/day, exactly 2x equity - one round trip), same names available, same costs. The only
thing that moves is what the model was asked to predict. 1,933 out-of-sample sessions, 2019-2026:

| label | horizon | gross bps per $ turned | x h1 | gross t | net $/day | t |
|---|---|---|---|---|---|---|
| h1 (F-1's own) | 30 min | 1.501 | 1.00 | +1.53 | **-232** | -1.19 |
| h4 | 2 h | 2.632 | 1.75 | +2.77 | -15 | -0.08 |
| h7 | 3.5 h | 3.293 | 2.19 | +3.38 | +116 | +0.60 |
| h10 | 5 h | 3.608 | 2.40 | +3.70 | +191 | +0.98 |
| **close** | 11 - slot | **4.256** | **2.84** | **+4.10** | **+306** | **+1.47** |

**Monotone in horizon, five for five, at constant construction and constant turnover.** F-7's
clause-2 prediction was that the persistence is real and harvestable; this is the same claim read
through a book instead of through an IC table, and it holds. Fitting the label the book actually
holds is worth **2.84x on gross per dollar turned** and it is the difference between a book that
loses $232/day and one that makes $306/day.

**(3) It is the first F-track cell whose gross clears its own cost line, and the margin is real.**
`session <- close` prices at **4.256 gross against 2.724 cost = +1.532 bps of edge per dollar
turned**. F-7's best cell on this same window was 3.495 against 3.697, i.e. **-0.202**. Five
scrambled-prediction seeds put the control at **-0.202 +/- 0.543 bps**, so the real cell sits
**8.2 control sd above the null** - the gross is the forecast, not the construction. Clause 4's
cost check is also much cleaner than F-7's: the selection premium (real cost minus its own
control's cost) is **+0.484 bps** here against F-7's +1.7, because a plain decile at one decision a
day does not preferentially buy the low-priced reverse-split leveraged names the conviction gate
went hunting for.

**(4) And it is refused, on the clause that was fixed before the run.** Clause 7 asks for t > 2
pooled and >= 5 of 8 positive years. It gets **5/8 years** (2019 -317, 2020 +1,273, 2021 +595,
2022 -642, 2023 -422, 2024 +865, 2025 +350, 2026 +923) and **t +1.47**. **0 of 20 cells pass.**
The 20-cell grid is not a search that got unlucky - it is four books x five labels with every
parameter fixed in advance, and its best cell is the one the ladder predicts.

**(5) The decisive number is the power arithmetic, and it closes the track rather than deferring
it.** t scales as sqrt(sessions), so t +1.47 on 1,933 sessions needs **3,558 sessions - 14.1 years
of out-of-sample** - to reach t = 2 at this effect size. The Alpaca SIP store begins 2016-01-04,
the walk-forward burns three years to train and validate, and the ceiling is therefore **~7.7
years**. **This finding cannot be resolved on the data this repository can obtain, ever.** F-7 was
refused for lack of power and could at least name a longer window; F-8 is refused for lack of power
and the window does not exist. That is a different and final kind of refusal.

**(6) Regimes: the label effect is concentrated exactly where the mandate wants it, which does not
rescue it.** By causal trailing 20-session SPY realized-volatility tercile:

| regime | sessions | gross bps (close) | gross bps (h1) | cost bps | net $/day | t |
|---|---|---|---|---|---|---|
| low vol | 645 | 2.369 | 1.728 | 2.714 | -69 | -0.22 |
| mid vol | 644 | 4.970 | 1.496 | 2.709 | +452 | +1.31 |
| high vol | 644 | 5.421 | 1.279 | 2.751 | +534 | +1.28 |

The h1 column is flat-to-falling across the terciles while the `close` column more than doubles, so
the horizon effect is a volatility effect: in calm markets a 30-minute and a five-hour forecast are
worth the same and neither is worth much; in volatile ones the multi-hour forecast is worth 4.2x
the 30-minute one. Conditioning on the high-vol tercile is not a rescue - it is the same t (+1.28)
on a third of the data, and the tercile cut is itself a parameter that was not pre-registered as a
book.

**(7) Feature-importance stability got WORSE with the better label, and that is the strongest
argument against the finding.** Permutation importance per retrain on the `close` label, 38
features, 8 retrains, `data/f1/importance_f8.csv`. Spearman rank correlation between retrains runs
**0.147 to 0.798, mean ~0.42**, against F-7's 0.665-0.767 on three retrains, and **0 of 38 features
have a positive importance in all 8 retrains** while **30 of 38 flip sign**. The top of the ranking
has also moved: F-7's `close`-free model led with the VWAP-displacement family, this one leads with
the volume family (`vol_rel6`, `m_rvol_ratio`, `rvol_ratio`, `cs_rvol_ratio`) and `vwap_atr` has
fallen to 15th. A model whose validation-set importances change sign every year is not reading a
stable object, and the honest reading of (2) + (7) together is that **the horizon effect is real and
the model that exploits it is not stable** - which is exactly the shape of an edge too small to
resolve.

**Decision: REFUSED, and the F track closes.** The supervised class is now priced four ways.
F-1 refused the 30-minute book on cost (0.797 bps against 2.392). F-3 refused the daily horizon on
absence (0.304 bps, IC t +0.18). F-7 refused the low-turnover construction on power (3.495 against
3.697, t -0.15 on this same 1,933-session window). F-8 refuses the correctly-labelled forecast on
power again - but this time **with a positive edge column (+1.532 bps) and a named, unreachable
data requirement (14.1 years)**. Clause 0 said F-8 should be the last item on this track unless it
clears the hurdle outright; it did not clear it, so the track closes. `champion.json` untouched,
`live/` untouched, nothing filed in `BLOCKERS.md` - a finding that needs 14 years of minute data
nobody sells is not an owner option.

**Do not re-open as a label, horizon, book or model question.** The label axis is now swept end to
end (30 min / 2 h / 3.5 h / 5 h / to-the-flatten), the book axis was exhausted by F-7 (dwell, band,
EWMA, conviction, decile, and the stacked cells), and the learner was deliberately held fixed so
the label effect would be readable - swapping in LightGBM would confound the one clean comparison
this iteration produced. The only honest way to reopen the class is **more independent
cross-section**, not more history: the panel is 56 names, and the pooled t is a breadth statistic
as much as a length one. That is a data-track question (a 500-name Alpaca universe), not an ML one,
and it is filed as **F-9 (parked, needs the D track first)** rather than as an open ML item.

**Three durable pieces survive the refusal.**
(a) **The label ladder method**: hold the book, the turnover and the learner fixed and vary only the
training label, then read gross bps per dollar turned. It converts F-7's cheap persistence table
into a book number and it is reusable by any future forecaster on this repo.
(b) **`close` is the right label for this sleeve** and `h4`/`h7`/`h10` are not, because a fixed
horizon is only defined on the early slots and silently confounds horizon with time of day. Any
future intraday supervised work should train on time-to-flatten.
(c) **A bug fix in `scripts/ml_f7.py`**: `vol_regime()` reindexed SPY's `datetime.date` keys against
the panel's string day keys, so **F-7's clause-6 regime table silently returned "n/a" for every
session**. Both sides are now normalised to `str`. F-7's published conclusion does not depend on it
(F-7 was refused on the power extension, not on regimes), but its regime clause was never actually
answered and now can be.

**Standing jobs**: none on this track. A-5 part 2 and S-17 part 2 belong to `iterate`/`daily`.

**Next**: nothing on the F track. F-9 is parked behind a D-track universe expansion; if the `daily`
or `iterate` tracks ever want the horizon finding, the one transferable claim is that **on this
universe a multi-hour intraday forecast is worth ~3x a 30-minute one per dollar traded, and the
gap is entirely a high-volatility phenomenon.**

---

## 2026-09-12 - F-7: the lower-turnover expression of F-1's forecast. The construction lifts gross per dollar 8.5x, the pre-registered rule still refuses it, and a 2.5x power extension turns the one promising cell to zero. Refused. Nothing shipped.

**Hypothesis.** F-1 found this repository's first positive out-of-sample intraday edge and refused
it on arithmetic, not judgement: pooled IC **+0.01133 at t +4.74**, gross **+$1,102/day at t
+3.04**, and a book that turns **$13.83M/day on $1M** while the forecast is worth **0.797 bps per
dollar turned** against **0.892 bps** of commission plus regulatory fees and **2.392 bps** once the
shipped 1.5 bps slippage constant is charged. F-1's closing paragraph named the single thing that
would change that arithmetic - *a lower-turnover expression of the same forecast* - and then
followed only the **daily** route (F-3, refused: 0.304 bps per dollar turned, IC t +0.18). The
**within-session** route was never tried. It needs no new model, no new feature and no new label:
freeze F-1's out-of-sample predictions and vary only the book built on top of them.

`scripts/ml_f7.py`, **29 DIAGNOSTIC ledger rows** under `intraday/f7_turnover` (19 constructions,
5 scrambled controls, 5 power-extension cells). Eight clauses pre-registered in the module
docstring before a construction number was read. **No shipped or runner-loaded file was touched** -
`algorithms/intraday/active/signal.py` and `live/intraday_config.json` are untouched, so no deploy
gate and no `--replay` is owed.

**(1) Clause 1, identity, exact.** The frozen forecast run through this module's own simulator at
F-1's decile-0.10 book reproduces ledger row `20260911T155155Z` to the cent: gross **1,102.352**
vs 1,102, net **-2,206.101** vs -2,206, turnover **13,831,037.037** vs 13,831,037, gross bps
**0.797**, IC **+0.01133**. Everything below is F-1's forecast, unchanged.

**(2) Clause 2 predicted the wrong answer, and that is the first finding.** The persistence table -
IC(h) of the frozen prediction against the demeaned cumulative return h intervals ahead, computable
with no book at all - does **not** decay. It *rises*:

| h | minutes | IC(h) | t | IC(h)/IC(1) | cumulative multiple |
|---|---|---|---|---|---|
| 1 | 30 | +0.01133 | +4.74 | 1.000 | 1.000 |
| 2 | 60 | +0.01069 | +4.31 | 0.944 | 1.944 |
| 4 | 120 | +0.01447 | +5.22 | 1.277 | 4.264 |
| 7 | 210 | +0.02064 | +6.01 | 1.822 | 9.428 |
| 10 | 300 | +0.02115 | +3.96 | 1.868 | 14.534 |
| 11 | 330 | +0.01622 | +2.09 | 1.432 | 15.966 |

Best cumulative multiple **15.966 at k=11** against the **3.00x** needed to clear the shipped cost
and **1.12x** to clear commission alone, so clause 2 pre-registered **CAN**. The 30-minute horizon
F-1 trained on is the *worst* horizon its own forecast has; the signal is a multi-hour one being
harvested every 30 minutes. **That number, not the books below, is what F-7 is worth keeping.**

**(3) Clause 3: the construction does exactly what clause 2 said, and it is not enough.** Nineteen
cells - decile width, dwell (re-decide every k-th point), hysteresis bands, within-session EWMA of
the prediction, and a conviction gate that trades only names whose predicted |alpha| in bps exceeds
a multiple of the one-way cost:

| cell | gross bps | x F-1 | gross t | cost bps | turn/day | net $/day | t |
|---|---|---|---|---|---|---|---|
| base decile 0.10 (F-1) | 0.797 | 1.00 | 3.04 | 2.392 | 13,831,037 | -2,206 | -6.02 |
| dwell 6 (3 h) | 2.096 | 2.63 | 2.01 | 2.504 | 3,393,457 | -139 | -0.39 |
| dwell 11 (once a day) | 3.487 | 4.38 | 1.79 | 2.585 | 2,000,000 | +180 | +0.46 |
| ewma 0.25 | 2.113 | 2.65 | 2.79 | 2.454 | 5,024,469 | -171 | -0.45 |
| conv 2.0x cost | 4.193 | 5.26 | 2.36 | 4.090 | 3,726,469 | +38 | +0.06 |
| conv 2.0x, wide decile | 4.232 | 5.31 | 2.39 | 4.086 | 3,730,896 | +55 | +0.08 |
| **band 0.10/0.40 + conv 2.0x** | **6.797** | **8.53** | **3.08** | 3.883 | 3,435,835 | **+1,001** | **+1.33** |

Gross per dollar turned goes from 0.797 to **6.797 bps, 8.53x**, on **a quarter of the turnover**,
and the best cell is **net positive in 3 of 3 test years** (+1,598 / +460 / +913). It is still
**REFUSED: 0 of 19 cells pass**, because clause 7 asks for t > 2 pooled and the best cell reaches
**t +1.33**. On 675 sessions the construction produced a plausible book and no evidence.

**(4) The conviction gate buys its gross partly by trading more expensive names, and the control
is what exposes it.** Clause 4 re-runs every construction on a per-timestamp permutation of the
prediction - same breadth, same turnover profile, forecast destroyed. The controls are clean on
gross (**-0.298 / -0.336 / -0.308 / +0.488 / -0.115 bps**, |t| <= 1.33, so the improvement is the
forecast and not the construction's arithmetic) but their **cost column is not**: every control
prices at **2.13-2.19 bps** while the real conviction books pay **3.88-4.09**. The gate does not
select names at random from the decile - it selects the ones with the widest predicted moves, which
are the low-priced, high-commission, reverse-split leveraged names. **1.7 bps of the 2.4 bps of
extra cost is selection, not construction**, and no turnover reduction removes it.

**(5) Clause 8, the power extension, is the verdict.** 675 sessions cannot resolve a t of 1.33, so
the identical cells at the identical parameters were re-run on a walk-forward started in **2019
instead of 2024** - **1,933 out-of-sample sessions, 2.5x the window, nothing re-tuned**, and early
test years training on less history, which biases *against* the finding. Pooled IC on the longer
window is **+0.01392 at t +9.84**, i.e. the forecast is more significant, not less. The books are
not:

| cell | gross bps | x F-1 | cost bps | turn/day | net $/day | t | positive years |
|---|---|---|---|---|---|---|---|
| base decile 0.10 | 0.752 | 0.94 | 2.530 | 15,179,186 | -2,698 | -13.45 | 0/8 |
| dwell 6 (3 h) | 1.387 | 1.74 | 2.598 | 3,490,352 | -423 | -2.19 | 1/8 |
| conv 1.0x cost | 1.676 | 2.10 | 3.475 | 7,450,897 | -1,340 | -3.44 | 2/8 |
| conv 2.0x cost | 2.202 | 2.76 | 3.834 | 2,935,178 | -479 | -1.39 | 2/8 |
| band 0.10/0.40 + conv 2.0x | 3.495 | 4.39 | 3.697 | 2,764,265 | **-56** | -0.15 | 4/8 |

**The best cell's gross per dollar halves (6.797 -> 3.495) and its net goes from +$1,001/day to
-$56/day at t -0.15, positive in 4 of 8 years - a coin flip.** Its three-for-three year record on
the short window was the 675-session sample, not a property of the book: the five years F-7's own
grid never saw are 2019 -183, 2020 +174, 2021 -781, 2022 -1,526, 2023 -808. The extended controls
confirm the gross is still the forecast's (**-0.042 / +0.058 bps**, |t| <= 0.21) - **what fails is
not the signal, it is that the signal is worth ~3.5 bps per dollar turned against a cost line that
prices at 3.7 when you select for it.** Refused on the pre-registered rule at 0 of 5 cells.

**(6) Feature-importance stability (the second thing the job asks to judge on).** Permutation
importance on each retrain's validation year, 38 features, `data/f1/importance_f7.csv`. Spearman
rank correlation between retrains **0.665 (2024/2026) / 0.699 (2024/2025) / 0.767 (2025/2026)** -
the model reads a recognisably similar object each year. The top of the ranking is the VWAP
displacement family (`vwap_atr`, `cs_vwap_atr`), relative volume (`vol_rel`, `rvol_ratio`) and
range (`rng_atr`), which is the same mean-reversion-against-VWAP story the hand-written intraday
strategies encode. **But the magnitudes flip sign year to year on the same feature** - `cs_vwap_atr`
is +1.38e-2 / -1.05e-2 / +4.10e-2 and `rvol_ratio` -1.52e-2 / +9.07e-2 / +9.38e-3 - and a negative
permutation importance means shuffling the feature *improved* validation MSE. A stable ranking over
unstable, sign-flipping magnitudes is what a weak true signal read through noise looks like. It is
consistent with IC +0.011 to +0.014 and it is not evidence of anything the book can spend.

**Decision: REFUSED, and the supervised class is now priced three ways rather than two.** F-1
refused the 30-minute book on cost, F-3 refused the daily horizon on absence of edge, F-7 refuses
the low-turnover *construction* on power - and the three together say the same thing with different
arithmetic: **this feature set forecasts at IC ~ +0.011 to +0.014 wherever it is pointed, that is
worth single-digit bps per dollar turned at best, and this instrument's round trip costs 2.4 to 4.1
bps.** Nothing in F-7 moves toward deployment. `champion.json` untouched; nothing filed in
`BLOCKERS.md`, because a refusal on cost and power is not an owner option.

**Do not re-open as a dwell, band, EWMA, conviction-threshold or decile question.** The grid spans
dwell 1 to 11 (one decision to once a day), bands from 0.04/0.20 to 0.10/0.40, EWMA lambda 0.25 and
0.50, conviction 0.5x to 2.0x cost, deciles 0.04 to 0.34, and the stacked cells of the two that
moved the number most - and the best of all nineteen dies on a 2.5x window with nothing re-tuned.
The one axis F-7 did **not** close is the one clause 2 identified and the harness cannot express:
**the forecast's IC peaks at h = 7-10 intervals (3.5-5 hours), and the label F-1 trains on is the
30-minute one.** A model trained directly on the multi-hour label is a different forecast, not a
different book, so it is a new pre-registration - filed below as **F-8** - and it inherits F-7's
cost arithmetic: it needs ~3.7 bps per dollar turned, and the honest prior after three refusals is
that it will find IC ~ +0.014 and be worth ~3.5.

**Two durable pieces survive the refusal.** (a) **The persistence table is reusable and cheap** -
`data/f1/f7_persistence.csv`, and the method (IC(h) on the demeaned cumulative return, computed
from the frozen prediction with no book) prices any forecast's natural holding period before a
simulator is written. (b) **A reproducibility hazard was found and fixed in this file**: F-1's cost
model depends on `data/minute_alpaca/_splits.json`, which only exists in the Alpaca store, so
running any F-track script **without `INTRADAY_DATA_DIR=data/minute_alpaca` silently understates
cost by 0.28 bps of turnover** (2.110 vs 2.392 on the base book - 12% of the cost line) while gross,
turnover and IC all still match to the cent. The mechanism is the reverse-split leveraged names
(`SQQQ` factor 0.0001, `SPXU` 0.0025, `SOXS` ~0): without the file `share_scale()` is 1.0, the
per-share commission is charged on split-*adjusted* share counts that are four orders of magnitude
too few, and most of those orders collapse to the $1.00 minimum. `ml_f7.py` now prints the store it
is costing against and names this as the first suspect when clause 1 fails. **Any future F-track
run must be started with that variable set**; the first clause-1 failure of this iteration was
exactly this and nothing else.

**Standing jobs**: neither belongs to this track (A-5 part 2 and S-17 part 2 are `iterate`/`daily`),
and it is a Saturday, so no new fills exist to re-quote.

**Next**: F-8 as filed in the backlog - retrain on the multi-hour label clause 2 identified, with
F-7's cost arithmetic and the power extension as the pre-registered window from the start.
