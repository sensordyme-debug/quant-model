# Sweep archive statistics audit - 2026-09-13

62 `scripts/sweep_*.py` / `scripts/ml_*.py` exist. 40 compute a t-statistic or a significance
gate. 19 wire an explicit `|t| > 2` to a printed verdict. **Zero** import
`quant_brain.core.stats`, and **zero** contain the string `purge` or `embargo`.

Read-only audit. Nothing under `scripts/` was modified.

---

## The headline, which is not the one this audit expected to write

The obvious hypothesis - "60 call sites of a naive iid t on overlapping labels, so the
archive's results are inflated across the board" - is **mostly false**, and the reason is a
design habit rather than luck. Almost every t in the archive is computed on a
**one-observation-per-session** series: the books are flat overnight, the event studies collapse
every leg into a session sum before testing (`sweep_x1.py:238-241`), the event loops enforce
non-overlap explicitly (`sweep_l1.py:132,145`), and the S-track's comparisons are *paired daily
differences* of two books on identical dates. AUD-18's overlap problem needs a label longer than
the sampling interval, and outside two scripts the archive does not have one.

What the archive has instead is three different things, and they do not rank the way the
call-site count suggests:

1. **Uncorrected multiplicity** across roughly 760 pre-registered cells and >3,000 signed
   regime-level comparisons. This is real but **it has produced almost no false conclusions**,
   because the archive's verdicts are overwhelmingly *refusals*. Correcting a refusal makes it
   safer, never weaker. Multiplicity is a latent liability here, not a realized one.
2. **Cross-sectional pooling**, which is the largest measured distortion anywhere in the tree
   (3.84x) and which nobody has named before. It lives in the per-trip tables, not the headlines.
3. **Genuine label overlap**, confined to `sweep_f3.py` and `ml_f8.py` - and `sweep_f3` is the
   one script in the archive whose *published positive claim* dies under correction.

So the ranking below is by grid x severity, as asked, but severity is decomposed into
**inflation x whether the error can flip the conclusion**. A naive t on 336 cells that all
refused is a smaller problem than a naive t on 10 cells that produced a "significant" finding.

### Method

Every inflation factor below is either **measured on the repository's own cached data** (marked
*measured*) or derived from a structure read out of the code (marked *structural*). The measuring
scripts read `data/f3/panel.parquet`, `data/f1/preds_test.parquet`, `data/f1/f8_preds.parquet`
and the LEAN daily store, and use `quant_brain.core.stats` for the corrections.

    naive t          what the script prints
    corrected t      Newey-West with lag = horizon - 1 (or day-clustered where h = 1)
    inflation        |naive| / |corrected|
    bar              Bonferroni |t| for the script's own cell count
    verdict          does the published conclusion survive both corrections?

---

## The ranked table

Rank = (uncorrected comparisons) x (measured inflation) x (can it flip the published claim).

| # | script | cells | statistical error | inflation | bar | published verdict | exposure |
|---|---|---|---|---|---|---|---|
| **1** | **`sweep_f3.py`** | **10** | overlapping label + argmax + unpurged split | **1.66x / 3.05x** *measured* | 2.81 | **POSITIVE** (`IC +0.01133 at t +2.17`) | **REALIZED - the claim is wrong** |
| **2** | `ml_f8.py` | 20 | argmax on the **test** window feeds a `t > 2` pass rule; nested label | 1.94x *measured* | 3.02 | refused | latent, high |
| **3** | `sweep_a9`/`a12`/`a8` | 10k-44k trips | same-day names pooled as independent | **3.84x** *measured* | - | diagnostic tables | realized in the tables |
| **4** | `sweep_f6.py` | **168** (336 signed, 1008 regime) | largest grid in the repo, tested at unadjusted 2.0 | 1.0x | 3.62 | refused | latent |
| **5** | `sweep_f5.py` | 138 (~690 stats) | as above, and the printed denominator is wrong | 1.0x | 3.57 | refused | latent |
| **6** | `sweep_a10.py` | 3 (9 regime) | small grid, but the **only t wired to a live config change** | 1.0x | 2.77 | keeps gross 1.5 | **consequence out of proportion** |
| **7** | `sweep_o2.py` | ~131 | argmax-then-condition (`:453-455`) with no correction | 1.0x | 3.55 | refused | latent |
| **8** | `sweep_s2.py` | 32 (128 t's) | `t > 2` decides the verdict (`:220`) | 1.0x | 3.16 | refused | latent |
| **9** | `sweep_f4.py` / `sweep_x1.py` | 48 / 16 (96 / 32 signed) | denominator printed, never applied | 1.0x | 3.28 / 2.96 | refused | latent |
| **10** | `sweep_s28`/`s29` | 9 corr | 21-session forward vol sampled **daily**, pooled over 9 names | ~21x *structural* | - | no t computed | latent, unclaimed |
| **11** | `sweep_o1.py` | 6 (88 stats) | feature **and its negation** both tested; in-sample polyfit at `:230` | 1.0x | 2.64 | refused | latent |
| **12** | `sweep_s20.py` | 21 t's | subset is 29 contiguous episodes read as 590 draws | 1.0-1.6x *measured* | 3.04 | null | latent, small |

Rows 4-9 and 11-12 are ranked by grid size, and every one of them **refused**. That is why they
sit below a 10-cell script: the correction they are missing would only have made their refusals
more certain. They are listed because the next positive result on one of those grids would be
unsafe, not because a past one is.

---

## 1. `sweep_f3.py` - the one published claim the corrections refute

**The claim.** `research/backlog.md:891` and `:2633`: *"The forecast is real and tiny: pooled
out-of-sample IC +0.01133 at t +2.17."* Two ledger rows carry it.

**Defect A - the label overlaps and the t assumes it does not.**
`sweep_f3.py:179` forms `labels[h] = log(op.shift(-(1+h)) / entry)` on **every** session for
h in {5, 21}. Consecutive labels share h-1 days of the same returns, so the IC series is
MA(h-1). `sweep_f3.py:283-288`'s `tstat` is `mean / (sd / sqrt(n))`, and `ic_stats` (`:291-299`)
feeds it the per-date IC directly.

Measured on `data/f3/panel.parquet` - the label's autocorrelation is exactly the fingerprint of
overlap, dying at the horizon and not before:

```
y_5   mean per-symbol autocorr  L1=+0.755  L2=+0.543  L5=-0.075  L10=-0.002
y_21  mean per-symbol autocorr  L1=+0.934  L2=+0.878  L5=+0.727  L20=+0.027  L21=-0.027
```

and the correction on the shipped forecast, test window 2012-2026:

| horizon | n | IC | naive t | HAC t (L = h-1) | inflation | block-bootstrap p |
|---|---|---|---|---|---|---|
| 5 | 3,687 | +0.01133 | **+2.17** | **+1.31** | 1.66x | 0.185 |
| 21 | 3,671 | +0.01264 | **+2.41** | **+0.79** | 3.05x | 0.418 |

The realized factors are below sqrt(h) (2.24 and 4.58) because the sample is finite, which is
exactly why they are worth measuring rather than asserting.

**Defect B - the reported cell is an argmax over ten.**
`sweep_f3.py:537-553` scores `len(GRID)=5` models x `len(HORIZONS)=2` horizons on one validation
window and takes `max(sel, key=ic)`. Ten cells. Bonferroni bar = **2.81**. The published 2.17
does not clear it *before any overlap correction at all*. On pure noise, the best of ten
independent cells clears 1.96 about a third of the time.

**Defect C - no purge at any boundary.**
Selection is `year <= 2007` / `2008-2011` (`:99-100`); the walk-forward is `year <= Y-2` /
`year == Y-1` / `year == Y` (`:565-567`). The last training row is 31 December of Y-2 and its
21-session label does not resolve until roughly 1 February of Y-1 - inside the early-stopping
window. Nothing drops those rows.

**Verdict.** Either correction alone refutes the claim; together they are not close. Defects A
and C are already logged as AUD-18; **Defect B is not**, and it is sufficient on its own.

---

## 2. `ml_f8.py` - a pre-registered pass rule applied to the maximum of a search

**The selection defect.** `ml_f8.py:520`:

```python
best = max(cells.items(), key=lambda kv: kv[1][0]["net_day"])
```

`cells` is `len(BOOKS)=4` books x 5 labels (`h1` benchmark + `h4/h7/h10/close`) = **20**, all
scored on the same 2019-2026 test window. Clause 7's rule at `:606` -
`passed = brow["net_day"] > 0 and brow["t"] > 2 and years_pos >= 5` - is then applied to `brow`,
the winner of that search, at a threshold calibrated for one pre-registered test. Bonferroni bar
for 20 cells = **3.02**. `:612-614` prints how many cells passed, which is an acknowledgement,
not a correction.

`ml_f11.py:573` and `ml_f12.py:636` run the same argmax and label it
*"clause 5: may NOT be read as the result"*, gating instead on a pre-specified primary cell
(`:569`, `:632`). F-8 has no such guard. That difference is the whole finding.

**The label defect.** `add_labels` (`:156-199`) builds `close` at **every** slot, all ending at
the same 15:30 flatten - so within a session the labels are **nested**, not merely overlapping:
slot k's label is slot k+1's plus one more interval. Measured on `data/f1/f8_preds.parquet`:

| label | slots/day | n | IC | naive t | HAC t | inflation | day-clustered t |
|---|---|---|---|---|---|---|---|
| h4 | 8 | 15,432 | +0.01120 | +6.69 | +5.05 | 1.32x | +4.54 |
| h7 | 5 | 9,645 | +0.01081 | +5.35 | +3.58 | 1.50x | +3.41 |
| h10 | 2 | 3,858 | +0.01079 | +3.39 | +2.90 | 1.17x | +2.82 |
| **close** | **11** | **21,219** | +0.01104 | **+7.79** | **+4.02** | **1.94x** | +3.60 |

`close` is the label F-8 selects, and it carries the largest inflation in the archive. Corrected,
`h10` (+2.90) falls below its own 3.02 bar; the rest survive. The `run_ic` matrix at `:631-650`
prints 20 of these t's side by side on samples that differ by a factor of five.

**A money-path defect found while testing this, not previously recorded.** Clause 3 (`:74-76`)
states: *"A hold of L intervals trades once in and once out, so **every book below turns exactly
2x equity per session** and the sweep F-7 already exhausted cannot be re-run by accident."*
Two of the four books violate it, because `:346` sums (nets) cohort weights before charging
turnover:

| book | turnover / equity, agreeing slots | disagreeing slots |
|---|---|---|
| `session` | 2.00x | 2.00x |
| `cohort_close` | 2.00x | **1.42x** |
| `cohort_h7` | 2.00x | 2.00x |
| `cohort_h4` | **1.00x** | 1.86x |

`cohort_h4` is worse than a turnover discrepancy: `:333-335` sets `sub = gross/len(entries)` with
8 entries but only a 4-slot hold, so at most 4 of the 8 cohorts are ever live and the book runs
at **0.5x gross** where `session` and `cohort_h7` run at 1.0x. The h4 row is therefore not a
label comparison at constant construction - it is a label comparison at half the risk. And
turnover varying with how much the forecast churns is precisely the axis clause 3 claims to have
fixed so that F-7's sweep could not be re-run by accident.

---

## 3. Cross-sectional pooling - the largest measured distortion in the tree

`sweep_a9.py:170`, `sweep_a12.py:197` and `sweep_a8.py:198` compute a t over per-round-trip P&L
pooled across names: ~7,000 units in a9, ~44,219 in a12. Each trip is exact and non-overlapping,
so overlap is not the issue - **same-day names are**. They share a market factor, so the
effective sample is smaller than the row count by Kish's design effect `1 + (m-1)*rho`.

Measured on the real F-1 store (56 names, per-session returns, 675 sessions):

```
mean pairwise same-day correlation rho = 0.250
design effect 1 + (m-1)rho             = 14.8
t inflation sqrt(deff)                 = 3.84x
effective independent units per session = 3.80, not 56
observed pooled-vs-clustered t ratio    = 2.65x
```

**3.84x is larger than any overlap effect measured anywhere in this repository**, including
F-3's 3.05x. It is unrecorded in `research/audit_2026-09-12.md`. It applies to decile and
quintile attribution tables rather than to headline verdicts - `sweep_a9.py:170` reads ten decile
t's whose real degrees of freedom are ~260 sessions, not ~7,000 trips - so nothing shipped on it,
but the monotonicity arguments those tables support are weaker than they look.

---

## 6. `sweep_a10.py` - three cells, one live trading decision

The only statistic in the archive wired to a change in deployed risk. `sweep_a10.py:260-269`:

```python
passing = [r for r in verdict_rows if r["t"] > 2.0]
...
if len(passing) >= 2: "-> the mix keeps gross 1.5"
else:                 "-> RULE FIRES: cut gross 1.5 -> 0.75 in live/intraday_config.json"
```

`t` at `:130` is the naive iid t on pooled daily P&L (`:178-180`) - non-overlapping, so no
inflation. The exposure is **direction**: an overstated t makes the rule *keep leverage on*.
Three verdict cells across three regimes is 9 statistics; the Bonferroni bar is 2.77 against the
2.0 used. Small grid, but this is the one row where being wrong costs money rather than an
iteration.

---

## What was measured and **cleared** - the other half of the answer

Reporting only the failures would misdescribe the archive.

**`sweep_f1.py` - the hub, and it holds.** Its `tstat` (`:396-402`) is imported by seven `ml_*`
modules across ~35 call sites, so it looked like the highest-leverage defect. It is not. F-1's
design sets `HOLD = STEP = 6` (`:77-78`), so its labels **tile** and do not overlap, and the
`net` series it tests is a daily sum. Measured on its own headline (`IC +0.01133 at t +4.74`):

```
tstat_hac(horizon=1)        t +4.74   (lag 0 - no correction is owed)
day-clustered (675 days)    t +4.84
IC-series autocorrelation   L1=+0.008  L2=-0.012  L11=-0.011
day-block bootstrap p       0.0000
Bonferroni bar, 55 F-track specifications  3.32
```

F-1's forecast clears every correction with room. The refusal it published was on cost
arithmetic, not on significance, and that refusal stands.

**`sweep_s25.py` - the premise four tracks are built on, and it holds.** Its `t +6.80` /
`t +4.20` (`:389,391`) are hardcoded into the docstrings of `sweep_s26`, `s27`, `s28` and `s30`
as the premise for four subsequent iterations, which made it the highest-value thing in the S
track to check. Measured on the EW sleeve legs over the same 2012-2026 window:

| leg | n | bps/day | naive t | Newey-West(8) | ratio | bootstrap p |
|---|---|---|---|---|---|---|
| overnight | 3,689 | +3.736 | +4.00 | **+4.27** | **0.93x** | 0.0000 |
| intraday | 3,690 | +1.537 | +1.41 | +1.65 | 0.86x | 0.087 |

The correction moves the t **up**, not down: daily equity returns mean-revert at lag 1
(ac1 = -0.097), so the iid standard error *overstates* the variance of the mean. **On daily
non-overlapping return series the archive's naive t is conservative, not liberal.** S-25 clears
the Bonferroni bar for its own ~24 cells (3.08) and for the ~35 S-track iterations before it
(3.19). The four downstream tracks rest on a sound premise.

**`ml_f7.py` - measured, minor.** Its persistence table (`:394-421`) computes IC(h) for h=1..11
on cumulative returns sampled every interval, which looks like textbook overlap. It is bounded by
the session:

```
h:            1     2     3     4     5     6     7     8     9    10    11
naive t:    4.74  4.31  4.52  5.22  6.29  6.14  6.01  5.00  3.98  3.96  2.09
HAC t:      4.74  4.02  3.93  4.37  5.24  5.04  5.01  4.32  3.51  3.57  1.91
inflation:  1.00  1.07  1.15  1.20  1.20  1.22  1.20  1.16  1.13  1.11  1.09
```

Maximum 1.22x, and the h=1 row that carries clause 2's argument is uncorrected because it needs
no correction. Only h=11 (bootstrap p 0.045) is marginal, and it is one decision point per day.

**`sweep_l1.py` and `sweep_x1.py` - the false positives of this audit.** Both carry `HORIZONS`
lists in bars held, which reads like overlap. Neither has any: L-1 enforces non-overlap in the
event loop (`:132,145`, `last = i + h`), and X-1 has genuinely overlapping raw legs at h=60 with
a 30-minute rebalance but collapses each session to one number before the t (`:238-241`) and
forbids a leg crossing the flatten (`:163`).

**`sweep_a14.py` / `sweep_a15.py` - best in class.** The only scripts that go beyond the iid t:
a Politis-Romano stationary bootstrap at `a14:140-158` (20,000 resamples, mean block 10 sessions)
with the reason stated in the docstring, a 300-draw within-regime permutation null at
`a15:507-529`, and explicit power vetoes that convert an unpowered REFUSE into UNDECIDED. `a15`'s
verdict text explicitly disclaims its own t and rests on the permutation band.

**`sweep_s38.py` - the only real multiplicity test in the repository.** An exact Poisson-binomial
p-value at `:476-487` on whether the shipped value being the OOS argmax on k of 6 axes is beyond
chance, plus a cross-cell selection-inflation z at `:379-385`. `sweep_s33.py:326-355`'s selection
premium is the same idea done well.

---

## Incidental defects found while auditing (not statistical)

| where | what |
|---|---|
| `ml_f8.py:74-76,333-346` | clause 3's "every book turns exactly 2x equity" is false for `cohort_close` (1.42x) and `cohort_h4` (1.0x, at 0.5x gross). **New.** |
| `sweep_o1.py:230` | `np.polyfit` over the **full** sample while `:221-223` claims the fit is expanding and causal; the forecast/surprise split at `:239-242` is in-sample. |
| `sweep_a8.py:443` | the clause-3 statistic divides a trade-reduction-**adjusted** numerator by `p["d_se"]`, the standard error of the **unadjusted** difference. |
| `sweep_f5.py:250` | prints 144 cells as the denominator; `:176` drops `h30`/entry-360 for all six (index, signal) pairs, so 138 are evaluated. |
| `sweep_s24.py:505` | `reprice(surcharge, ...)` - `surcharge` is never assigned in `report()`. `--report --breakeven` raises `NameError`. |
| `sweep_a15.py:139` | declares `SPLIT` and never references it. Dead constant in a file whose discipline is otherwise the best in the tree. |
| `sweep_s36.py:349-350` | SILENT-TRUNCATE: `alloc_vol_window`, `regime_median_window`, `vol_est_window` give byte-identical weights above `history_bars`, so the **"broad shelf, not a spike"** robustness argument used at `sweep_s1:388-390`, `sweep_s29:62-64` and in `sweep_s33` can be an artefact of window truncation on those axes. |

## Splits

**No script in the archive purges or embargoes.** The S-track's shared boundary is
`IS 2012-2019 / OOS 2020-01-02` - a zero-session gap, since 1 January is a holiday. That is
harmless where the label is one session, which is almost everywhere. Two places where it is not:

- `sweep_f3.py:565-567`, above - a 21-session label across an unpurged year boundary into the
  early-stopping window.
- The **warm-up** crosses every S-track boundary: `sweep_s19.py:143` and `sweep_s25.py:228` slice
  `lo = max(0, i - lag - params.history_bars)` with `history_bars = 307`, so the OOS book's first
  ~15 months of signal input is IS data. `sweep_s38.py:467-470` names this exactly and counts it.

---

## Tests written

| file | covers |
|---|---|
| `tests/test_sweep_stats_audit.py` | 9 copies of the t-statistic proven identical to `stats.tstat_iid`; the zero-importers measurement; the grid sizes and Bonferroni bars this document quotes; the three dependence structures (overlap, cross-sectional pooling, episode clustering) demonstrated on constructions with known answers. |
| `tests/test_sweep_f3.py` | `ic_stats`, `simulate`, `summarize`, the label's MA(h-1) structure, the unpurged boundary, and the ten-cell argmax. |
| `tests/test_ml_f8.py` | `add_labels` (nesting, per-timestamp demeaning, gap invalidation, per-horizon coverage), `ic_vs`, `simulate` (including the clause-3 turnover defect above), `summarize`, and the twenty-cell argmax. |

66 tests, all passing, ruff clean. They are **not** gating (`tests/conftest.py:RUNNER_TESTS`),
because none of this touches the live book.

These tests pin the audit rather than fix the scripts. If a track retrofits `tstat_hac` into one
of the audited modules, `test_every_archive_tstat_is_the_naive_iid_form` fails - and that failure
means **this document is out of date**, not that the code is broken.

---

## What to do, in order

1. **Withdraw or re-state F-3's claim.** It is the only published positive result the corrections
   refute. Two ledger rows and `research/backlog.md:891,2633` carry `t +2.17` as evidence.
2. **Give `ml_f8` the guard `ml_f11`/`ml_f12` already have** - gate clause 7 on a pre-specified
   primary cell, not on `max(..., key=net_day)`. One line, and it is the difference between a
   refusal that means something and one that got lucky.
3. **Fix `ml_f8`'s `cohort_h4` gross**, or stop describing the label ladder as like-for-like.
4. **Cluster the per-trip tables by session** in `a8`/`a9`/`a12`. The 3.84x design effect is the
   biggest single number in this audit and the cheapest to fix.
5. Leave the large refusing grids (`f4`/`f5`/`f6`/`o2`/`x1`/`s2`) alone. Adopt a threshold from
   `stats.bonferroni_threshold` on the **next** positive result from one of them, not
   retrospectively - the refusals are safe as they stand.
