# Validation: splits, multiplicity, robustness, causality, and the red team

Status of this document: describes `quant_brain/core/{stats,validation,multipletest,labels}.py`,
`quant_brain/research/robustness.py`, `quant_brain/markets/futures_cme/features.py` and
`tests/test_leakage_redteam.py` at `HEAD = 28fa331` (2026-09-13 23:54 ET). Every caller claim
below was re-measured on 2026-09-14 by the commands printed beside it. These are library
modules; §7 says which of them any research driver actually calls, and the honest answer is
still "almost none of them".

| claim | status | evidence |
|---|---|---|
| ENGINE VALIDATED | yes | `tests/test_qb_stats.py` (25), `test_qb_validation.py` (38), `test_qb_multipletest.py` (77), `test_qb_robustness.py` (70), `test_qb_features_search.py` (30), `test_qb_labels.py` (18) |
| **THE LEAKAGE GUARDS ARE EXERCISED BY REAL CHEATS** | yes, 12 of 13 | `tests/test_leakage_redteam.py` (31 tests): thirteen planted cheats through real production entry points, twelve refused, one open (§6) |
| **THE SPLIT API IS USED ANYWHERE** | **no** | `purged_walk_forward`, `purged_kfold`, `cross_validate`, `assert_no_leakage`, `iter_splits` and `Holdout` have zero callers outside tests (§7) |
| STRATEGY VALIDATED | **no** | nothing has passed these tools; see `docs/RESEARCH.md` |
| LIVE EXECUTION VALIDATED | **no** | not applicable to this layer |
| PROFITABILITY DEMONSTRATED | **no** | |

---

## 1. Significance under overlap: `core/stats.py`

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

Callers: `Ledger.verdict` (`quant_brain/research/registry.py:42`),
`scripts/futures_topstep_baseline.py:50`, and - reachable from neither - `research/analytics.py`
and `research/robustness.py`. `research/sweep_audit.md` measured that **zero** of the 62
`scripts/sweep_*.py` / `scripts/ml_*.py` import it. The audit's headline is that this matters
less than it looks - almost every t in the archive is computed on one observation per session,
where no overlap correction is owed - and the exceptions (`sweep_f3.py`, `ml_f8.py`) are
named there.

---

## 2. Splits: `core/validation.py`

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

### Checking geometry: `assert_no_leakage`

`assert_no_leakage(split, *, horizon, embargo=0, walk_forward=True)` checks the property
directly on any split (`test_a_leaky_split_is_caught_by_the_assertion`,
`test_a_non_walk_forward_split_is_caught`). `cross_validate` runs it on every fold by default
(`check=True`). `coverage(splits, n)` reports what the correction cost as fractions of the
sample, because a score from folds that used 30% of the data is a different claim from one
that used 90%. `min_train` turns "the horizon ate the sample" into a refusal with an
explanation (`test_a_horizon_that_eats_the_sample_is_refused_with_an_explanation`).

### Checking the pipeline: `cross_validate(probe=...)`, new on 2026-09-13

`assert_no_leakage` inspects index **geometry**: which rows are in the training fold, which
are purged, which are embargoed. It says nothing about what the code inside `fit_score`
actually read. A standardiser fitted on the whole sample before the split is invisible to it,
and the two runs are numerically indistinguishable - `cross_validate` reported them
identically, down to the coverage line.

Measured on a 900-row fixture whose volatility regime changes at row 600 (the docstring's own
figures, `core/validation.py:452-460`), out-of-sample accuracy by fold:

```
train-only   0.9867 0.9667 0.9733 0.7333 0.8133
full-sample  0.8600 0.8533 0.8400 0.8867 0.8800
```

On the two folds that straddle and follow the regime change the contaminated pipeline is
materially **better** out of sample. That is the signature, and its lower mean is not a
defence.

`probe` closes it. The caller owns the data, so only the caller can perturb it: `probe(rows)`
takes a boolean mask of the rows **outside** a fold and returns a `fit_score` equivalent in
every way except that those rows have been changed. `_probe_transform` (line 495) calls
`fit_score` twice on the last fold and raises `LeakageError` if the score moves at all - the
comparison is `base != moved`, not a tolerance.

Four design choices worth naming, because each is where a weaker version would have failed:

- **Only the last fold is probed.** It has the largest training set and, on an expanding
  walk-forward, the smallest out-of-fold remainder, so it is the hardest fold to detect
  contamination on. One extra `fit_score` call rather than `folds` of them.
- **A probe that cannot fire returns False, not True.** When the last fold covers the whole
  sample there is nothing outside it to perturb, and claiming a clean bill from a probe that
  could not fire is the exact failure this function exists to prevent.
- **`probe` is not defaulted to a no-op.** Without it `CVResult.transform_verified` is False
  and `summary()` ends in `transform UNVERIFIED`, because "we did not check" and "we checked
  and it was clean" must not read the same
  (`test_cross_validate_says_UNVERIFIED_when_no_probe_was_supplied`).
- **The clean control passes the same probe.** `test_cross_validate_must_reject_a_scaler_fitted_on_the_full_sample`
  runs the train-only pipeline through the identical probe and asserts it is **not** refused,
  so this cannot be satisfied by a guard that rejects everything.

Both probe tests live in `tests/test_leakage_redteam.py`, not in `tests/test_qb_validation.py`,
which has no probe coverage at all.

### The holdout

`make_holdout` / `Holdout.spend` - a write-once tail keyed by a fingerprint of the data, so a
second look from a fresh process next week is still refused. Described in `docs/RESEARCH.md`.
**Never carved and never spent.** `grep -rn "make_holdout\|Holdout(" scripts/ quant_brain/
algorithms/` finds only the definition and one docstring reference in
`research/promotion.py:351`; no holdout ledger file exists anywhere in the tree.

---

## 3. Multiplicity: `core/multipletest.py`

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

**None of this has ever been applied to a candidate set.** The module has 77 tests and no
caller of any kind - see §7, and see the second reason it could not be wired even if someone
wanted to today: `tests/test_production_reachability.py::test_the_multiplicity_ledger_can_read_the_main_experiment_log`
is an `xfail(strict=True)` recording that `Ledger.all()` parses **0 of the 1,653 rows** in
`research/experiments.jsonl`, because the equity log and the `Ledger` class have disjoint
schemas. Wiring the Bonferroni denominator to the equity track tomorrow would silently return
0 trials and apply the n=1 bar of 1.96 to a search of several thousand cells.

### Deliberately not here

Sidak and Holm-Sidak (2.5% more power for an independence assumption the families violate),
Storey's q-value (unstable pi0 at tens of tests), Romano-Wolf / Westfall-Young stepdown
(the most worth adding next; left out for scope).

---

## 4. Robustness: `research/robustness.py`

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

70 tests. One importer (`research/analytics.py`), which itself has none.

---

## 5. Causality of features: `markets/futures_cme/features.py`

`Feature(name, family, fn, requires, warmup)` declares the columns it needs.
`FeatureSet.missing(columns)` names what a store cannot support; `build(df, strict=True)`
refuses rather than silently returning a narrower matrix. The microstructure family
(`spread_bps`, `quote_imbalance`) requires `bid`/`ask`/sizes and is therefore **absent** on an
OHLCV store rather than reconstructed - F-14 measured reconstructed bar-level flow at 0.65
correlation with the return and no better than scrambled columns
(`test_microstructure_is_absent_on_an_ohlcv_store`). `library()` ships nineteen features.

`assert_causal(feature, df, *, at=None, seed=0)` perturbs a bar and asserts no earlier value
of the feature changes. It **sweeps** rather than probes once: candidates
`[3, 5, 10, 20, 31, warmup + 2, 25%, 50%, 80%]` of the frame, deliberately weighted toward the
start. The first version probed a single index at 80% and passed `opening_range_pos` with a
leak confined to its first thirty bars - the leak that became the only funnel survivor ever
recorded (`docs/RESEARCH.md`). `test_the_causality_check_probes_early_bars_not_just_late_ones`
and `test_a_late_only_probe_would_still_miss_it` keep that lesson executable.

The perturbation itself was rebuilt on 2026-09-13, and all three changes were forced by a
counter-example in the red team (`_assert_causal_at`, line 289):

| was | is | what the old version missed |
|---|---|---|
| the hard-coded tuple `("c","h","l","o","v")` | **every numeric column** in the frame | `bid.shift(-1)` came back bit-identical. `spread_bps` and `quote_imbalance` declare `bid`/`ask`/sizes and had therefore **never once been tested** by the audit that reported them clean |
| a uniform scale (prices x1.05, volume x3) | a seeded **per-row scale and jitter**, `tail * U(1.5, 4.5) + N(0, sd)` | a uniform positive multiplier preserves order, so any argmax, rank or order statistic over the bumped region is exactly invariant to it. A future-argmax leak was invisible |
| `np.isclose(rtol=1e-5, atol=1e-8)` | exact `!=`, with `both_nan` handling the warm-up | a leak at amplitude 1e-9 on a base of 1.0 sat inside the tolerance, and its **sign** recovers the next bar's direction exactly - the red team pushed it through the funnel for 100.00% of the theoretical ceiling |

Exactness is affordable because every feature in the library is elementwise or
forward-cumulative, so a head row is computed from the same inputs in the same order before
and after; the measured worst head deviation across all nineteen at all nine probe points is
exactly 0.0. The seed is a constant on purpose: a guard whose verdict changes between runs
gets re-run until it passes.

`audit_causality(fs, df)` runs the sweep over a library and returns every failure, not the
first. `scripts/futures_discover.py::build_features` now calls it on three sessions (first,
middle, last) and raises `validation.LeakageError` on any failure - see §6.

`core/labels.forward_span_mask(index, steps, expected)` closes AUD-20: a `shift(-k)` label is
only a k-period return on a gapless grid, and the Alpaca store has 73 within-day gaps that
made 0.09% of 30-minute labels span up to 2h10m.

---

## 6. The red team: `tests/test_leakage_redteam.py`

Thirteen leaks, each injected into a **real production entry point** on a synthetic, seeded,
in-file fixture - `scripts/futures_discover.evaluator`, `scripts/sweep_s19.simulate`,
`scripts/sweep_s25.legs_simulate`, `features.assert_causal`, `validation.cross_validate`.
Nothing in the file reads `data/`, the network, or `live/`. Each leak is paired: a
CHARACTERISATION test that measures the cheat and asserts what the stack does, and a RATCHET
test that asserts what it should do. **Twelve ratchets are cleared; one remains.**

`python -m pytest tests/test_leakage_redteam.py -p no:cacheprovider -rxX` -> 30 passed,
1 xfailed.

| # | the cheat | what refuses it now |
|---|---|---|
| 1 | `pos[i] = sign(c[i+1] - c[i])` - one bar of perfect foresight | funnel gate 0: gross is 100.0000% of the one-bar-ahead ceiling, above `MAX_CEILING_SHARE = 0.20` (`futures_discover.py:86, 319`) |
| 2 | `pos[i]` reads bar i+1's high and low | gate 0 at 99.57% |
| 3 | `pos[i]` reads bar i+1's **volume** only, no future price | gate 0 at 94.68% |
| 4 | `X.shift(-1)` on every column of the real feature frame | gate 0 at 44.90% - the weakest leak measured, and still twice the refusal level |
| 5 | the target published as a feature (`c.pct_change().shift(-1)`) | `build_features` runs `audit_causality` over three sessions and raises `LeakageError` |
| 6 | `rolling(31, center=True)` - the textbook accident | same wiring |
| 7 | a standardiser fitted on all 900 rows before the split | `cross_validate(probe=...)` (§2) |
| 8 | decide on bar i's close, fill at bar i's close | the result dict now carries `fill_convention`, `gross_next_open_fill` and `fill_subsidy`, so the subsidy is a number the reader can subtract |
| 9 | `bid.shift(-1)` | `_assert_causal_at` perturbs every numeric column; caught at bar 1 (4997.875 -> 15711.614) |
| 10 | the argmax of the session's last closes, read forward | the per-row scale-and-jitter breaks order preservation; caught at bar 0 (0.0 -> 3.0) |
| 11 | a leak carried at amplitude 2e-9 | exact `!=` instead of `isclose(atol=1e-8)`; caught at bar 1 |
| 12 | `sweep_s19.simulate(lag=-2)` - a decision window reaching past the fill, reachable by typing a minus sign (measured: CAR 1,369%, Sharpe 15.4, MaxDD 1.8%, against the deployed 18.7% / 1.04 / 11.1%) | `simulate` raises `LeakageError` on `lag < 0` (`sweep_s19.py:160`) |
| 13 | `sweep_s25.legs_simulate(weights_fn=...)` fed tomorrow's returns | **nothing. Still open.** |

### The one that is open, and why a guard was reverted

`legs_simulate` computes a causality window - `closes.iloc[lo:i - lag]` - and then, when
`weights_fn` is supplied, does not use it: the branch is `targets = weights_fn(index[i])`.
The hook receives a bare timestamp and whatever dict comes back is trusted. Measured on
identical prices:

```
weights from closes[i]  /closes[i-1]   CAR    24.21%   Sharpe  1.826   MaxDD 8.03%
weights from closes[i+1]/closes[i]     CAR 2,554.97%   Sharpe 36.552   MaxDD 0.00%
```

A maximum drawdown of exactly zero over 190 sessions is what a leak looks like from the
outside. The audit measured CAR 2,133% / Sharpe 18.95 for the same cheat on the real panel.

A guard was **attempted and reverted on 2026-09-13**, and the xfail reason records the
measurement rather than the intention: requiring the hook to accept `window=` and passing it
the causal panel was implemented, and it refused the CAUSAL control too -
`{'causal': {'refused': True}, 'one_day_ahead': {'refused': True}}` - because a legacy
one-argument hook is refused whether or not it cheats. That is the false-positive machine
this file exists to catch, so it was reverted rather than shipped. The conclusion on the
record: the contract change is necessary and not sufficient, since a hook can accept the
window and still read a closure. A guard that discriminates has to test the **weights** -
their association with the next session's realised return against a causal baseline, the
equity-path analogue of the funnel's ceiling canary - and that is real work, not an API tweak.

### What the suite does not prove, in its own words

It proves that a specific set of cheats is or is not detected by a specific set of entry
points on synthetic data. It does not prove any *shipped* result is or is not contaminated,
it does not enumerate the leak space, and a green run means these thirteen mechanisms are
caught - not that the engine is causal. The clean controls in section G are what stops the
suite being satisfiable by an engine that refuses everything: a strictly causal feature and a
strictly causal strategy must pass through untouched, and a blanket guard was tried and made
every one of them fail.

---

## 7. What actually calls these modules

Measured on 2026-09-14 with `tests/test_production_reachability.py`, which walks the import
graph from six production entry points and from every non-test file mentioning `quant_brain`.
Of 53 `quant_brain` modules, 15 are production-reachable, 19 more are research-reachable, and
19 are reachable from nothing outside the test suite.

| module | callers outside its tests | is that use? |
|---|---|---|
| `core/stats.py` | `research/registry.py` (`Ledger.verdict`), `scripts/futures_topstep_baseline.py` | yes |
| `core/validation.py` | `scripts/futures_discover.py:37`, `scripts/sweep_s19.py:53` | **only the exception class.** Both import `LeakageError` and nothing else |
| `core/labels.py` | `scripts/sweep_f1.py:66` (`forward_span_mask`, applied at line 306; also hashed into the panel fingerprint at 210) | yes |
| `markets/futures_cme/features.py` | `scripts/futures_discover.py` | yes |
| `core/multipletest.py` | **none** | - |
| `research/robustness.py` | `research/analytics.py`, which has no caller | no |
| `research/promotion.py` | **none** | - |

The `core/validation.py` row is the one to read carefully. The module became reachable on
2026-09-13 and `test_the_leakage_guard_module_is_wired_to_the_research_path` records the
ratchet clearing - but the foothold is narrow, and narrower than "the validation module is
wired":

```
$ grep -rn "purged_walk_forward\|purged_kfold\|cross_validate\|assert_no_leakage\|iter_splits" \
      scripts/ quant_brain/ algorithms/ --include=*.py | grep -v core/validation.py
(nothing)
```

**No production or research code has ever called a split function, a cross-validation, a
leakage assertion or a holdout.** Two scripts import an exception type from the module and
raise it from their own guards. That is a real improvement over zero callers - it is why the
funnel refuses cheats 5 and 6 and why `sweep_s19` refuses cheat 12 - and it is not purged
walk-forward being used to evaluate anything.

## 8. Not implemented

- **A purged walk-forward anywhere a strategy is actually evaluated.** The funnel's gate 4 is
  a five-block sign test (`docs/RESEARCH.md`); `research/sweep_audit.md` records that no
  script in the sweep archive purges or embargoes, and that the S-track's IS/OOS boundary is
  a zero-session gap with a 307-bar warm-up crossing it.
- **A carved holdout.** `make_holdout` has never been called and `Holdout.spend()` has never
  run; no ledger file exists.
- **Any production call to `multipletest` or `robustness`.** Tested (147 tests between them)
  and unused. `multipletest` additionally cannot be pointed at the equity ledger without
  reading 0 trials (§3).
- **A promotion gate that applies any of this.** `research/promotion.py` has no caller;
  `scripts/evaluate.py` promotes on CAR with no significance test, no multiplicity and no OOS
  requirement.
- **A discriminating guard on `sweep_s25`'s `weights_fn`** (§6).
- Romano-Wolf / Westfall-Young stepdown, Storey's q-value, Sidak.
- **Retrofitting `tstat_hac` into the sweep archive.** `tests/test_sweep_stats_audit.py` (39
  tests) pins the archive's t-statistics as the naive iid form, so a retrofit fails a test
  until the audit document is updated - by design.
- **Withdrawal or re-statement of F-3's published `t +2.17`** in `research/backlog.md`, which
  the audit lists as its first action item; this document does not assert it has happened.

## 9. What this document does not claim

It does not claim these corrections have been applied to the research that produced this
repository's published numbers; outside `Ledger.verdict`, one baseline script and one label
mask they have not. It does not claim the validation module is in use because it is reachable;
two scripts import an exception from it and nothing calls a split (§7). It does not claim an
embargo protects a walk-forward split; it removes nothing there. It does not claim any of the
multiplicity or robustness tools has been run over a real candidate set; none has. It does not
claim `probe` proves a pipeline is clean in general; it proves that perturbing the rows
outside one fold does not move that fold's score, and only when a caller supplies a probe -
otherwise the result says UNVERIFIED and means it. It does not claim the causality sweep
proves the absence of lookahead; it proves that perturbing every numeric column at nine
chosen points does not move earlier values of the nineteen features in `library()`. It does
not claim the red team enumerates the leak space; thirteen mechanisms are not a space, and one
of the thirteen is still open.
