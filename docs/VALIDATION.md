# Validation: splits, multiplicity, robustness, and causality

Status of this document: describes `quant_brain/core/{stats,validation,multipletest,labels}.py`,
`quant_brain/research/robustness.py` and `quant_brain/markets/futures_cme/features.py` at
commit `2a7367f` (2026-09-13). These are library modules. The last section says which of them
any research driver actually calls; most are called only by their tests.

| claim | status | evidence |
|---|---|---|
| ENGINE VALIDATED | yes | `tests/test_qb_stats.py`, `test_qb_validation.py`, `test_qb_multipletest.py`, `test_qb_robustness.py`, `test_qb_features_search.py`, `test_qb_labels.py` |
| STRATEGY VALIDATED | **no** | nothing has passed these tools; see `docs/RESEARCH.md` |
| LIVE EXECUTION VALIDATED | **no** | not applicable to this layer |
| PROFITABILITY DEMONSTRATED | **no** | |

---

## Significance under overlap: `core/stats.py`

`tstat_iid` is the textbook `mean / (sd / sqrt(n))`, kept so the size of a correction can be
reported against it. `tstat_hac(x, *, lag=None, horizon=None)` is Newey-West with a Bartlett
kernel. When `horizon` is given the lag is derived by `lag_for_overlap(horizon, n)` =
`max(0, h - 1)` capped at `n // 4`, and a caller-supplied `lag` below that is **refused**
rather than accepted (`test_a_lag_below_the_horizon_is_refused_not_silently_accepted`): a
label spanning h periods sampled every period is an MA(h-1), and truncating below h-1 leaves
real dependence in the residual and reports a t that is still inflated, only less visibly.

The worked example the module was built on (AUD-18, `research/sweep_audit.md`): F-3's
published `IC +0.01133 at t +2.17` is +1.31 after the 5-day overlap correction and +0.79 at
the 21-day horizon (from a naive +2.41). `bonferroni_threshold(n_trials)` supplies the
|t| a result must clear given the trials; at F-3's ten selection cells the bar is 2.81 before
any overlap correction, so either correction alone refutes the claim
(`test_f3_survives_neither_correction`).

`block_bootstrap_t(x, *, block, reps=2000)` is the moving-block cross-check on the HAC
number. `inflation(x, horizon=)` is the number AUD-18 is about: `|naive| / |HAC|`.

What `stats.py` is used by: `Ledger.verdict` (`quant_brain/research/registry.py`) and
`scripts/futures_topstep_baseline.py`. `research/sweep_audit.md` measured that **zero** of the
62 `scripts/sweep_*.py` / `scripts/ml_*.py` import it. The audit's headline is that this
matters less than it looks - almost every t in the archive is computed on one observation per
session, where no overlap correction is owed - and the exceptions (`sweep_f3.py`, `ml_f8.py`)
are named there.

---

## Splits: `core/validation.py`

### Purged walk-forward

`purged_walk_forward(n, *, horizon, folds=5, embargo=0.0, min_train=1, expanding=True)`
tiles test folds across the tail of the sample and trains strictly before each one. `horizon`
is **required** - defaulting it to zero would produce splits that look purged, pass every
test, and leak exactly as much as no purging (`test_the_horizon_is_required_and_not_defaulted`).

Two corrections, and they are not the same thing:

| correction | drops | width |
|---|---|---|
| PURGE | training rows whose label window `[i, i+horizon]` reaches the test fold | the label horizon |
| EMBARGO | training rows in the `emb` rows immediately **after** the test fold | a judgement about feature persistence |

### The embargo is vacuous under walk-forward, and why

Under strict walk-forward every training row precedes the test fold by construction, so the
set of training rows following the test fold is empty and the embargo removes nothing at any
width. The parameter is accepted, computed and reported, and
`test_the_embargo_removes_nothing_under_walk_forward_at_any_width` asserts the count is zero
rather than letting the knob imply work it does not do. The purge does all of the work.

The embargo earns its keep in `purged_kfold(n, *, horizon, folds=5, embargo=0.01)`, where
training resumes on the far side of the test block and the first rows of training are
serially correlated with the last rows of test
(`test_the_embargo_does_remove_rows_under_kfold`). That scheme trains on data after the test
fold - a look-ahead in the **fitting** even with purged labels - so its score is an upper bound
on walk-forward and the module says the repository's default should stay walk-forward.

An earlier draft of `_embargo` banned rows following *earlier* test folds from *later*
training sets; that discards data without protecting anything, and the docstring keeps the
correction.

### Checking rather than trusting

`assert_no_leakage(split, *, horizon, embargo=0, walk_forward=True)` checks the property
directly on any split (`test_a_leaky_split_is_caught_by_the_assertion`,
`test_a_non_walk_forward_split_is_caught`). `cross_validate(fit_score, n, *, horizon, ...)`
runs it on every fold by default (`check=True`). `coverage(splits, n)` reports what the
correction cost as fractions of the sample, because a score from folds that used 30% of the
data is a different claim from one that used 90%. `min_train` turns "the horizon ate the
sample" into a refusal with an explanation
(`test_a_horizon_that_eats_the_sample_is_refused_with_an_explanation`).

### The holdout

`make_holdout` / `Holdout.spend` - a write-once tail keyed by a fingerprint of the data, so a
second look from a fresh process next week is still refused. Described in `docs/RESEARCH.md`.
Never carved or spent in this repository.

---

## Multiplicity: `core/multipletest.py`

`stats.py` has one correction, Bonferroni. This module adds the other three questions a
factory asks, and the module docstring's rule for all of them is: a violated assumption about
the **call** raises; a violated assumption about the **data** returns an explicit unavailable
result carrying the reason, never a plausible number.

### Which method, when

| you have | question | use | valid under | do not use when |
|---|---|---|---|---|
| p-values | any one false positive is expensive (a handful of candidates about to be sized) | `holm` (`control_fwer` always routes here) | arbitrary dependence | the family is large and the goal is discovery |
| p-values | which of many cells are worth taking to validation | `benjamini_yekutieli` (`control_fdr` default) | arbitrary dependence, at a `ln(n)` price | the family is known positively dependent and large enough that the penalty kills everything - then `spa` |
| p-values, and you can say `dependence="positive"` out loud | same, with more power | `benjamini_hochberg` | independence or PRDS | two-sided tests of correlated statistics; a family containing a strategy and its own inverse, which this tree's sweeps generate constantly |
| the (T, K) P&L panel of the **whole** search | is the best of these better than the benchmark | `spa` | stationary, weakly dependent, `block >= dependence length` | only survivors are available - the set must be the whole search; compare `n_candidates` to `Ledger.trials(family)` |
| the same panel | reference for `spa` | `reality_check` | as above | as a default - see padding below |
| one survivor's returns and every trial's Sharpe | how much of this Sharpe was bought with search | `deflated_sharpe_from_returns` | trial Sharpes on the same clock, including the survivor | one trial (unavailable), or a variance computed from survivors only |
| the (T, N) panel of every configuration tried | does "pick the best backtest" generalise at all | `pbo` | exchangeable blocks; N large enough for a rank to mean something | a single strategy (identically 0) |

`bonferroni` survives as the baseline `holm` is measured against
(`test_holm_rejects_a_superset_of_bonferroni_on_every_random_family`) and as the t-scale
threshold `Ledger.verdict` applies.

### SPA over Reality Check: the padding measurement

White's recentring leaves every candidate contributing to the bootstrap maximum, so adding
hopeless variants raises the p-value of the good one. The test is manipulable in the safe
direction, which is still manipulable. Measured (`ARCHITECTURE.md` section 4b, pinned by
`test_padding_a_search_with_hopeless_variants_fools_the_reality_check_and_not_spa`): a
marginal edge among 20 candidates gives Reality Check p = 0.032; adding 80 hopeless variants
pushes it to 0.129 while SPA stays at 0.015. Hansen's two changes are studentisation and
recentring with a threshold, and SPA returns three p-values (`pvalue_lower`, `pvalue`,
`pvalue_upper`) that bracket the truth in a documented order
(`test_hansens_three_p_values_bracket_in_the_documented_order`). A wide bracket is itself the
finding.

The bootstrap is Politis-Romano stationary, applied with the **same** resampled index path to
every candidate so cross-sectional dependence is preserved; `block` is required and
range-checked, because block length is the serial-dependence assumption.

### The trial count is still not an argument

Every FWER and FDR function takes the vector of p-values, so N is its length and cannot be
understated without withholding a test the caller can see
(`test_no_correction_accepts_a_trial_count_argument`,
`test_the_only_way_to_weaken_the_correction_is_to_withhold_trials`). The scalar
`deflated_sharpe` does take `n_trials` because the formula needs it; the module says to feed
it from `Ledger.trials(family)`. `skew` and `kurtosis` have **no defaults** (a Gaussian default
would flatter exactly the candidates a reviewer is looking at), `kurtosis` is non-excess and
passing excess is refused with the fix named, and a per-observation Sharpe above 2.0 is
refused as an annualised figure passed with a daily count.

### Deliberately not here

Sidak and Holm-Sidak (2.5% more power for an independence assumption the families violate),
Storey's q-value (unstable pi0 at tens of tests), Romano-Wolf / Westfall-Young stepdown
(the most worth adding next; left out for scope).

---

## Robustness: `research/robustness.py`

Significance and robustness are different questions; a strategy can pass every gate and be,
in substance, one very good Tuesday.

### Regime labels are features and can leak

`session_table(bars, *, time_col="t", tz, rollover=18:00, buckets)` computes per-session
statistics (`ret`, `rvol`, `volume`, `range_frac`, `efficiency`, `trend_strength`, and the
same per clock bucket). It refuses a timezone-naive column (AUD-07) and rolls the CME trade
date at 18:00 ET on the wall clock.

`labellers(short=5, long=60)` gives `vol_regime`, `vol_tercile`, `trend_regime`,
`volume_regime`. Every one computes its state from sessions **strictly before** the one it
labels (`_state` shifts first, then rolls) and its boundaries from a trailing window, never
the whole sample. `pd.qcut(vol, 3)` is the one-liner everybody writes and it is a lookahead:
January is labelled with December's volatility
(`test_a_whole_sample_qcut_labeller_is_caught`). Sessions before the warm-up are labelled
`WARMUP`, not NaN, so they cannot vanish from a groupby.

`assert_causal_labels` rewrites the table from row `at` onward - scaled **and** jittered, so a
rank-reading labeller cannot survive it - and checks no earlier label moves. Probe points are
weighted toward the start of the sample, for the same reason `features.assert_causal` is:
`test_a_leak_confined_to_the_warmup_survives_a_single_late_probe`.

`regime_performance` returns per-regime rows with `carry` = share of net / share of sessions;
a regime that is 12% of sessions and 80% of profit reads 6.7. `intraday_attribution` takes
fixed clock buckets as an argument and does not choose them, because a boundary chosen from
the data ("the most profitable hour") is a selection needing multiplicity accounting.

### Concentration: is it one lucky path?

`concentration(pnl, *, dates, tops, drop, windows)` reports best-day/week/month share, top
1/5/10% share, Herfindahl and effective sessions, Gini against its arithmetic floor
(`1 - winners/n`), totals with the best 1/5/10 days removed, days-to-zero, longest losing
streak, max drawdown, time under water. Every share against the net total is NaN when the
total is not positive (`net_positive` says why) and the `_gross` variants are reported
beside them, because `best_day / total` on a losing strategy is arithmetic noise
(`test_shares_against_a_non_positive_total_are_nan_rather_than_negative`).

Where a threshold could be replaced by a measurement, it is: `ordering_null` reshuffles the
strategy's own sessions to ask whether the streak and drawdown are unusual for these sessions
in another order; `tail_null` asks how concentrated the profit would look under a Gaussian of
the same mean and sd, with the assumption stated as a reference and not a belief.

`METRIC_DOCS` carries an interpretation for every reported field with a `basis` of
`arithmetic` or `judgement`; `readings()` refuses an undocumented field and `undocumented()`
must return an empty set. "A best-day share above 25% is worrying" is labelled a judgement.

### Parameter sensitivity

`parameter_sensitivity(scores, *, axis_names, tolerance=0.5, best_key=None)` reports the mean
and worst neighbour ratio one grid step away, sign agreement, plateau fraction and per-axis
ratios. `best_key` lets the caller evaluate the shipped point rather than the grid argmax,
which is the more honest question because the argmax is selection.

---

## Causality of features: `markets/futures_cme/features.py`

`Feature(name, family, fn, requires, warmup)` declares the columns it needs.
`FeatureSet.missing(columns)` names what a store cannot support; `build(df, strict=True)`
refuses rather than silently returning a narrower matrix. The microstructure family
(`spread_bps`, `quote_imbalance`) requires `bid`/`ask`/sizes and is therefore **absent** on an
OHLCV store rather than reconstructed - F-14 measured reconstructed bar-level flow at 0.65
correlation with the return and no better than scrambled columns
(`test_microstructure_is_absent_on_an_ohlcv_store`). `scripts/futures_discover.py` prints
which features were refused for the store it ran on.

`assert_causal(feature, df, *, at=None)` perturbs prices from bar `at` onward (x1.05, volume
x3) and asserts no earlier value of the feature changes. It **sweeps** rather than probes
once: candidates `[3, 5, 10, 20, 31, warmup + 2, 25%, 50%, 80%]` of the frame. The first
version probed a single index at 80% and passed `opening_range_pos` with a leak confined to
its first thirty bars - the leak that became the only funnel survivor ever recorded
(`docs/RESEARCH.md`). `test_the_causality_check_probes_early_bars_not_just_late_ones` and
`test_a_late_only_probe_would_still_miss_it` keep that lesson executable.
`audit_causality(fs, df)` runs it over a library and returns every failure, not the first.

`core/labels.forward_span_mask(index, steps, expected)` closes AUD-20: a `shift(-k)` label is
only a k-period return on a gapless grid, and the Alpaca store has 73 within-day gaps that
made 0.09% of 30-minute labels span up to 2h10m.

---

## What actually calls these modules

| module | callers outside its tests |
|---|---|
| `core/stats.py` | `research/registry.py` (`Ledger.verdict`), `scripts/futures_topstep_baseline.py` |
| `core/validation.py` | `research/promotion.py` (the `Holdout` type only) |
| `core/multipletest.py` | **none** |
| `research/robustness.py` | **none** |
| `markets/futures_cme/features.py` | `scripts/futures_discover.py` |
| `core/labels.py` | none outside tests |

Measured by grep over `scripts/`, `quant_brain/` and `algorithms/` on 2026-09-13.

## Not implemented

- A purged walk-forward anywhere a strategy is actually evaluated. The funnel's gate 4 is a
  five-block sign test (`docs/RESEARCH.md`); `research/sweep_audit.md` records that no script
  in the sweep archive purges or embargoes, and that the S-track's IS/OOS boundary is a
  zero-session gap with a 307-bar warm-up crossing it.
- Any production call to `multipletest` or `robustness`. They are tested and unused.
- Romano-Wolf / Westfall-Young stepdown, Storey's q-value, Sidak.
- Retrofitting `tstat_hac` into the sweep archive. `tests/test_sweep_stats_audit.py` pins the
  archive's t-statistics as the naive iid form, so a retrofit fails a test until the audit
  document is updated - by design.
- Withdrawal or re-statement of F-3's published `t +2.17` in `research/backlog.md`, which the
  audit lists as its first action item; this document does not assert it has happened.

## What this document does not claim

It does not claim these corrections have been applied to the research that produced this
repository's published numbers; outside `Ledger.verdict` and one baseline script they have
not. It does not claim an embargo protects a walk-forward split; it removes nothing there. It
does not claim any of the multiplicity or robustness tools has been run over a real candidate
set; none has. It does not claim the causality sweep proves the absence of lookahead in
general; it proves that perturbing later bars at nine chosen points does not move earlier
values of the features in `library()`.
