# Machine learning in this repository

Status of this document: describes `scripts/ml_f*.py`, the shared engine `scripts/sweep_f1.py`,
`scripts/sweep_f3.py`, `quant_brain/core/validation.py`, `quant_brain/core/stats.py`,
`quant_brain/markets/futures_cme/features.py`, `tests/test_leakage_redteam.py`,
`tests/test_sweep_stats_audit.py` and the `data/f1/` artefact store as they stand in the **working
tree** on 2026-09-14 00:12 ET, at `HEAD = f58b36e`. It is pinned to a working tree rather than a
commit because several agents edit this tree concurrently; HEAD moved four times while this was
being written.

Every number here was read out of the code, measured read-only from a store, or reproduced by
running a test. The measurement is given beside the number. Nothing was copied from
`QUANT_MODEL_SYSTEM_AUDIT.md` or from a journal entry without re-deriving it, and four of those
figures did not survive that (§10).

| claim | status | evidence |
|---|---|---|
| ML EXPERIMENTS EXIST AND RUN | yes | 14 `ml_f*.py`, one shared engine, 135 recorded runs (§1) |
| ANY ML MODEL IS DEPLOYED | **no** | nothing on the production path imports the F-track; `algorithms/intraday/ml/`, the directory `AGENTS.md` names as this track's home, **does not exist** (§1.2) |
| ANY ML ARM SURVIVED ITS OWN HURDLE | **no** | every arm refused; best-ever was F-16 at $412/day, t +1.97 against a t > 2 bar, and it was later withdrawn (§3) |
| PURGED / EMBARGOED CV IS USED | **no** | `grep -rlciE "purge\|embargo"` over all 87 `sweep_*.py` + `ml_*.py` returns **zero files** (§4) |
| A HOLDOUT EXISTS | **no** | `make_holdout` has never been called, `spend()` has never run, no holdout ledger is on disk (§5) |
| RUN-TIME LEAKAGE GUARD ON THIS PATH | **no** | the causality audit and gate 0 are futures-only; the ML path's protection is a commit-time test suite (§9) |
| THE t-STATISTICS ARE CORRECTED | **no** | all 14 route through one naive iid t; zero import `quant_brain.core.stats` (§7) |
| THE ADMITTED FEATURE SETS ARE CLEAN | **no** | 12 distinct columns across all 8 test years carry one of three measured contamination mechanisms (§8) |

---

## 1. Inventory

### 1.1 The files

Fourteen scripts match `scripts/ml_f*.py`. They are one lineage, F-7 through F-24, and each reads a
prior run's frozen artefact rather than starting from raw data. Thirteen of the fourteen import
`scripts/sweep_f1.py` (`grep -rln "import sweep_f1" scripts/*.py`); the exception is `ml_f22.py`,
which imports `sweep_f3` instead.

| file | lines | what it tried | ledger rows in `research/experiments.jsonl` |
|---|---|---|---|
| `ml_f7.py` | 743 | lower-turnover constructions (dwell, band, EWMA, conviction gate) on F-1's frozen forecast | 29 `intraday/f7_turnover` |
| `ml_f8.py` | 743 | refit on longer-horizon labels (h4, h7, h10, close) instead of F-1's 30-minute label | 24 `intraday/f8_label` |
| `ml_f10.py` | 669 | subsample the name universe to fit a saturating breadth curve; no refit | 9 `intraday/f10_breadth` |
| `ml_f11.py` | 676 | rank by `pred - lambda * cost_i` instead of raw predicted alpha; no refit | 13 `intraday/f11_costaware` |
| `ml_f12.py` | 847 | a second model on `abs(y)` used to inverse-vol size the book | 22 `intraday/f12_risksize` |
| `ml_f14.py` | 652 | 20 new order-flow / path features on top of the 38 | 4 `intraday/f14_features` |
| `ml_f15.py` | 909 | two new data channels: the Alpaca auction cross and the 0DTE SPY chain | 6 `intraday/f15_altstore` |
| `ml_f16.py` | 491 | move F-15's feature gate *inside* the walk-forward (train+validation only, per test year) | 5 `intraday/f16_causalgate` |
| `ml_f17.py` | 639 | widen F-16's gate to 17 parents from both new stores, plus a redundancy leg | 5 `intraday/f17_poolgate` |
| `ml_f19.py` | 759 | rebuild the panel and the auction stores through a patched loader, re-run F-16's gate | 2 `intraday/f19_cleanpanel` |
| `ml_f20.py` | 588 | rebuild the flow store, re-run F-17's question | 4 `intraday/f20_cleanflow` |
| `ml_f21.py` | 827 | widen the panel from 56 to 62 names, feature-eligible but not tradable | 5 `intraday/f21_wide62` |
| `ml_f22.py` | 197 | an audit ruling on one `commission(..., 1.0)` call site in `sweep_f3.py` | **0**, by design |
| `ml_f23.py` | 346 | reprint two statistics the past decisions were made on, for every frozen arm | **0**, by design |

Total 9,086 lines. `F-9`, `F-13`, `F-18` and `F-24` have **no file of their own**: F-9 and F-18 were
retired on the backlog, F-13 was never opened, and F-24 lives inside `ml_f23.py`.

The engine is `scripts/sweep_f1.py` (F-1): `build_panel`, `fit_predict`, `simulate`, `ic_stats`,
`tstat`. Only two files fit a model at all — `sweep_f1.py:368`
(`HistGradientBoostingRegressor`) and `sweep_f3.py:255` (the same, plus a `Ridge` control at
`:240`). A repository-wide grep for `sklearn|lightgbm|xgboost|torch|tensorflow|catboost`, excluding
the gitignored `Quant Brain/` vault, finds **only sklearn**, and only in those two files plus six
`ml_f*.py` that import `permutation_importance` for a diagnostic.

### 1.2 Dead code, and the difference between reachable and used

An orphan scan of `scripts/` — a script is strictly orphaned when its stem appears in no other
tracked text file in the repository, with `Quant Brain/`, `.git/`, `results/` and `data/` excluded —
finds **1 of 132**:

```python
# read-only; run from the repo root
import os, re
from pathlib import Path
scripts = sorted(Path("scripts").glob("*.py"))
texts = {}
for dp, dn, fn in os.walk("."):
    dn[:] = [d for d in dn if d not in {".git", "Quant Brain", "results", "data",
                                        "__pycache__", ".pytest_cache", ".venv", ".obsidian"}]
    for f in fn:
        p = Path(dp) / f
        if p.suffix.lower() in {".py", ".md", ".ps1", ".json", ".jsonl", ".xml",
                                ".toml", ".cfg", ".ini", ".sh", ".txt", ".yml", ".yaml"}:
            texts[str(p).replace("\\", "/")] = p.read_text(encoding="utf-8", errors="replace")
for s in scripts:
    pat, key = re.compile(r"\b" + re.escape(s.stem) + r"\b"), str(s).replace("\\", "/")
    if not any(pat.search(t) for k, t in texts.items() if k != key):
        print("orphan:", s.stem)
# -> orphan: sweep_a20
```

`sweep_a20` is not an ML file — it is the `iterate` track's exposure sweep, committed unfinished in
`b612e63`. Every `ml_f*.py` is referenced somewhere. Separately, **48 of the 132 scripts are named
by no other `.py` file at all**, which is normal rather than alarming: they are standalone CLI entry
points, not libraries.

Reachable is not used, and on this track the gap is total:

- **No production entry point imports the F-track.** A grep over the six scripts
  `tests/test_production_reachability.py:35` names as `PRODUCTION_ENTRY_POINTS`
  (`intraday_trader.py`, `paper_trade.py`, `intraday_launch.py`, `reconcile_state.py`,
  `backtest.py`, `evaluate.py`), plus `algorithms/intraday/active/signal.py`,
  `algorithms/intraday/base.py` and `live/intraday_config.json`, finds no reference to `ml_f*`,
  `sweep_f1`, or any `data/f1/` artefact.
- **`algorithms/intraday/ml/` does not exist.** `AGENTS.md`'s "Parallel tracks" section names it as
  the `ml` scope's home directory. `ls algorithms/intraday/` returns `active`, `gap_fade`,
  `late_momo`, `lev_revert`, `orb`, `vwap_trend`, `xsect`, `base.py`, `CONTRACT.md` — there is no
  `ml`. The ML track's own journal says as much in its header: *"this track has never shipped a
  deployed file and does not ask to"* (`research/journal_ml.md:5`).

### 1.3 The artefact store

`data/f1/` holds 40 files, about 1.9 GB. The load-bearing ones for anything below:

| file | what it is |
|---|---|
| `panel.parquet` / `panel.dirty.parquet` | the 38-feature training panel, and the pre-rebuild copy F-19 kept beside it |
| `f14_flow.parquet` / `f14_flow.dirty.parquet` | the 20-column order-flow store, and its pre-rebuild copy |
| `f15_famA.parquet`, `f15_famB.parquet` | the auction family and the 0DTE chain family |
| `f16_admitted.json`, `f17_admitted.json`, `f19_admitted.json`, `f20_admitted.json` | **which columns each gate admitted, per test year** — the subject of §8 |
| `f8_preds.parquet` … `f21_preds.parquet` | frozen out-of-sample predictions, reused by every downstream run |
| `panel.meta.json`, `f14_flow.meta.json`, `f21_panel62.meta.json` | build stamps, added after F-19 |

Nothing here is a model artefact. No pickle, no joblib, no `.npz`, no ONNX
(`grep -rlE "pickle\.|joblib|\.npz|onnx" scripts/ml_f*.py` finds nothing). **Every fitted estimator
in this repository is discarded at the end of the process that fitted it.** What survives is the
predictions, which is why every downstream run is a re-reading of a frozen file rather than a refit
— and it is why a stale panel could go four experiments deep before anyone noticed (§8.5).

---

## 2. The one engine, and what it does at fit time

`sweep_f1.build_panel` (`:268`) constructs the panel once, over the whole 2016-2026 sample:

- **Label.** `fwd = log(o[i+1+HOLD] / o[i+1])` with `HOLD = 6` five-minute bars = 30 minutes, and
  decisions every `STEP = 6` bars. `:298` forces `fwd` to NaN whenever the exit bar falls on a
  different calendar day, so **the label never crosses a session boundary**. `y = fwd - mean(fwd)`
  within each timestamp (`:331`) — a cross-sectional demeaning computed inside one timestamp, and
  therefore inside one fold.
- **Features.** 38 columns (`len(sweep_f1.FEATURES)`), of four kinds: own-name trailing statistics,
  the same statistics on SPY (`m_*`), residuals against SPY (`x_*`), and within-timestamp percentile
  ranks (`cs_*`). Every rolling window is trailing.
- **Model.** `fit_predict` (`:366`) fits `HistGradientBoostingRegressor` with an explicit
  `(X_val, y_val)` for early stopping, and the source says why: *"sklearn's own validation_fraction
  would slice the training set at random, which leaks across time"* (`:391`). The `Ridge` control
  (`:344`) wraps `SimpleImputer` + `StandardScaler` + `Ridge` in a `Pipeline` and fits it on `X`
  inside `fit`. **That is the correct shape** — the transform is fitted on the training rows and
  nothing else, which is exactly the property §6's probe exists to check. It would pass.

---

## 3. What the fourteen experiments established

Every arm is refused. The table is the sequence of refusals and what each one bought. Each headline
is quoted from the run's own ledger row and cross-checked against the successor script's opening
paragraph, which is this track's convention for recording a result.

| run | headline | verdict |
|---|---|---|
| F-1 | the panel and the model; OOS mean per-timestamp rank IC +0.011 at t 4.74 | real, and worth ~0.8 bps against ~2.4 bps of cost |
| F-7 | turnover reduction cannot rescue it: net **-$2,206/day, t -6.02** | REFUSED |
| F-8 | longer labels help: `close` gives gross 4.256 bps, cost 2.724, net **+$306/day, t +1.47** | REFUSED (t < 2) |
| F-10 | breadth curve on F-8's predictions: ceiling **t(inf) = 2.34** at infinite names | REFUSE F-9 on cost-benefit |
| F-11 | cost-aware ranking: net **$362/day, t 1.88** | REFUSED |
| F-12 | risk-model sizing: net **$159/day, t 1.06** — worse than F-8 | REFUSED |
| F-14 | 20 flow features: paired against base **-$199/day, t -1.51** | REFUSED; flow makes it worse |
| F-15 | auction + 0DTE channels: both-arm **$158/day, t 0.80**; a post-hoc `lean3` arm hit $365/day | REFUSED; `lean3` barred as test-set-selected |
| F-16 | the gate made causal: **$412/day, t +1.97**, the best net this track ever fitted | REFUSED, then **withdrawn** by F-19 |
| F-17 | the gate widened to 17 parents: **$310/day, t 1.50**, below its own scrambled control | REFUSED |
| F-19 | the panel was stale; on the rebuild the gate admits **nothing in 8 of 8 years** and base falls 306 -> 258 | F-16's headline withdrawn |
| F-20 | the flow store was **bit-identical** after rebuild and the gate still changed **6 of 8** decisions | REFUSED, third time on this family |
| F-21 | 62 names instead of 56: paired **-$51.8/day, t -0.42**; the clause-1 disjointness check **FAILED** | REFUSED |
| F-22 | an audit ruling: the `scale=1.0` call site is correct; the residual is $8.24/day of overcharge | no change |
| F-23 / F-24 | the gate has made **6 admissions in its history and 0 turn on a resolvable margin**; the rank IC ranks a scrambled control above every real arm | no verdict flips |

The two most valuable results in this list are both negative and both about method rather than about
markets: F-20's *"a screen is not a property of its candidates"* (`research/journal_ml.md:421`) and
F-23's *"0 of 6 admissions turn on a margin the window can resolve"* (`research/journal_ml.md:9`).

---

## 4. Validation: what runs instead of purged cross-validation

### 4.1 The facility exists and has no caller

`quant_brain/core/validation.py` (526 lines) provides `purged_walk_forward`, `purged_kfold`,
`assert_no_leakage`, `coverage`, `cross_validate`, `iter_splits`, `make_holdout` and `Holdout`.

```
grep -rn "purged_walk_forward\|purged_kfold\|make_holdout\|Holdout\|cross_validate\|iter_splits" \
     --include=*.py . | grep -v "^./Quant Brain/" | grep -v "^./quant_brain/core/validation.py"
```

Every hit is either under `tests/` or in `quant_brain/research/promotion.py`, which is itself in the
`_UNWIRED` list at `tests/test_production_reachability.py:189` under `xfail(strict=True)`. **No
script under `scripts/` or `algorithms/` calls any of them.** The only symbol from this module that
reaches research code is the exception class `LeakageError`, imported by
`scripts/futures_discover.py:37` and `scripts/sweep_s19.py:53`.

The repository's own reachability test says the same thing in its docstring
(`tests/test_production_reachability.py:174-181`): *"`purged_walk_forward` and the write-once
`Holdout` are still uncalled, no holdout has ever been carved, and `Holdout.spend()` has never run.
Reachability is not use."*

The words themselves appear nowhere in the archive:

```
grep -rlciE "purge|embargo" scripts/sweep_*.py scripts/ml_*.py     # -> no files
```

Zero of 87.

### 4.2 What the ML scripts do instead

Every F-track run uses the same split, written out at `ml_f7.py:133-136` and repeated in
`ml_f8.py:219`, `ml_f12.py:221`, `ml_f14.py:349`, `ml_f15.py:610`, `ml_f16.py:293`, `ml_f17.py:445`,
`ml_f19.py:466`, `ml_f20.py:332` and `ml_f21.py:344`:

```python
for year in sorted(panel[panel.year >= 2024].year.unique()):
    trn = panel[panel.year <= year - 2]
    vld = panel[panel.year == year - 1]
    tst = panel[panel.year == year]
```

An expanding walk-forward by calendar year, with a **whole year of validation sitting between the
training set and the test set**. `sweep_f3.py:37-39` uses the identical shape on a daily cadence.

### 4.3 Is it sound? Mostly, and the reason is the label rather than the discipline

The purge that `purged_walk_forward` supplies removes training rows whose label window reaches into
the test fold. Measure what that would remove here:

- **Intraday F-track.** The label is intra-session by construction (`sweep_f1.py:298` NaNs any label
  whose exit falls on another day) and the folds are calendar years. The last training row of year
  Y-2 carries a label that ends the same afternoon, in year Y-2. **The purge would remove nothing at
  either boundary.** Its absence costs this track nothing.
- **`sweep_f3` (daily, h = 5 and h = 21).** The last training row of year Y-2 carries a label
  reaching up to 21 trading days into year Y-1. Year Y-1 is the *validation* fold, and it drives
  early stopping. So the train/test boundary is clean by construction and the train/validation
  boundary leaks up to 21 sessions of a ~250-session fold. Small, and unmeasured.

So the honest statement is not "the ML track is riddled with fold leakage". It is:

> **The split geometry is sound, and it is sound by accident of the label rather than as a checked
> property.** Nothing in these scripts asserts it, nothing computes the purge width, and nothing
> would notice the day a label is lengthened past a fold boundary. The one facility that would
> refuse such a split has no caller.

There is a second and larger consequence, and it is the one that actually bit. `assert_no_leakage`
inspects index geometry. Even if it had been wired in, **it would have passed every F-track run**,
F-16 included — because F-16's defect was never in the indices. It was in the substrate the indices
point at (§8).

---

## 5. The holdout that has never been carved

`validation.make_holdout(data, *, fraction, ledger_path, label)` carves the final fraction of a
series and fingerprints it with SHA-256 of the data itself, so that a second look **next week, in
another process** is still detectable. `Holdout.spend(*, result, note, force=False)` appends each
evaluation to an on-disk ledger and raises `LeakageError` on the second, in a message that names the
date and the note of the first.

Verified state:

```
find . -iname "*holdout*" -not -path "./.git/*" -not -path "./Quant Brain/*"   # -> nothing
```

**No holdout has ever been carved and `spend()` has never run.** For the ML track specifically,
measured over `research/experiments.jsonl`:

| measure | value |
|---|---|
| ML rows (`algorithm` matching `^intraday/f\d`) | **135** |
| rows whose window starts 2019-01-02 | **104** |
| rows on the single window 2019-01-02 .. 2026-09-10 | **95** |
| distinct windows across all 135 rows | **7** |
| rows with a real commit hash | **0** |
| rows with a `provenance` block | **0** |
| rows with `reproducible: true` | **0** |

`docs/RESEARCH_PROTOCOL.md` §5 makes the general argument; this is its ML instance. **One window has
been scored at least 104 times, and every design parameter of F-16 and F-17 — the gate's quantile,
its correlation ceiling, its candidate pool, its redundancy leg — was fixed by reading results from
that window in earlier runs.** There is no out-of-sample period on this track. A number from
2019-2026 is a fit statistic; it is not evidence of generalisation, and the count 104 has to travel
with it.

---

## 6. The probe: what `cross_validate` could not see until today

`assert_no_leakage` checks *which rows* are in each fold. It says nothing about what the code inside
`fit_score` read. A standardiser fitted on the whole sample before the split is invisible to it, and
`cross_validate` reported the contaminated and the clean run **identically, down to the coverage
line**.

### 6.1 The measurement

`tests/test_leakage_redteam.py:612` builds a 900-row fixture: one feature whose **volatility regime
changes at row 600**, a label that is "a one-sigma up move in *local* units", and two pipelines that
differ only in whether the standardiser's mean and sd are computed over the training rows or over
all 900. Reproduced read-only for this document, using the production splitter:

```python
import numpy as np
from quant_brain.core import validation as val
N, SHIFT, HI = 900, 600, 6.0
rng = np.random.default_rng(31337)
EPS = rng.normal(0.0, 1.0, N)
X = EPS * np.where(np.arange(N) < SHIFT, 1.0, HI)
Y = np.where(EPS > 1.0, 1.0, -1.0)
def fs(contaminated):
    def f(tr, te):
        rows = np.arange(N) if contaminated else np.asarray(tr)
        mu, sd = float(X[rows].mean()), float(X[rows].std(ddof=0))
        return float((np.where((X[te] - mu) / sd > 1.0, 1.0, -1.0) == Y[te]).mean())
    return f
sp = val.purged_walk_forward(N, horizon=1, folds=5)
print([round(fs(False)(s.train, s.test), 4) for s in sp])
print([round(fs(True)(s.train, s.test), 4) for s in sp])
```

Test blocks are `(150,299) (300,449) (450,599) (600,749) (750,899)`. Result:

| fold | 1 | 2 | 3 | **4** | **5** | mean |
|---|---|---|---|---|---|---|
| train-only | 0.9867 | 0.9667 | 0.9733 | **0.7333** | **0.8133** | 0.8947 |
| full-sample scaler | 0.8600 | 0.8533 | 0.8400 | **0.8867** | **0.8800** | 0.8640 |

**Read folds 4 and 5, not the mean.** On the folds that straddle and follow the regime change the
contaminated pipeline is materially *better* out of sample. That is the signature: it is not a
better model, it is a model that already knows the test period's scale. Its lower *mean* is not a
defence — on the three early folds it is worse because the full-sample sigma is inflated by a regime
that has not happened yet. **A leak can move a score in either direction; the direction is not the
tell, the direction changing at the regime boundary is.**

Without a probe the report reads:

```
+0.8640 +/- 0.0192 over 5 folds (h=1, embargo=0; train 50% of sample,
purged 0.6%, embargoed 0.0%; transform UNVERIFIED)
```

### 6.2 What `probe=` is, and what it costs

`cross_validate(..., probe=...)` (`validation.py:438`, helper at `:495`) takes a callable
`probe(outside_mask) -> fit_score` that returns the same scorer over data in which every row
**neither in the training fold nor in the test fold** has been perturbed. If the score moves, the
pipeline read rows it does not own and `LeakageError` is raised. If it does not move,
`CVResult.transform_verified` becomes `True` and `summary()` prints `transform probed`.

Three design choices in it are worth naming, because each is a refusal to reassure:

1. **Only the last fold is probed.** On an expanding walk-forward it has the largest training set
   and the smallest out-of-fold remainder — the hardest fold on which to detect contamination, so a
   probe that fires there would fire on any earlier one. On this fixture that remainder is **exactly
   one row** (the purged one), and one row is enough: the clean score does not move at all, the
   contaminated score moves by 0.12. The cost is one extra `fit_score` call, not `folds` of them.
2. **`probe` is not defaulted to a no-op.** The caller owns the data, so only the caller can perturb
   it; a synthesised default would pass silently. Absent a probe, `transform_verified` is `False`
   and the summary says `UNVERIFIED`, *"because 'we did not check' and 'we checked and it was clean'
   must not read the same"* (`validation.py:476`).
3. **A probe that cannot fire returns `False`, not `True`.** If the last fold covers the whole
   sample there is nothing outside it to move, and `_probe_transform` reports that it did not run
   rather than issuing a clean bill.

Pinned by three tests, all passing:
`test_scaler_fit_on_the_full_sample_helps_after_a_regime_change` (`:650`),
`test_cross_validate_must_reject_a_scaler_fitted_on_the_full_sample` (`:738`) — which also hands the
**clean** pipeline the identical probe and requires it *not* to be refused, so the guard cannot be
satisfied by rejecting everything — and
`test_cross_validate_says_UNVERIFIED_when_no_probe_was_supplied` (`:762`).
`python -m pytest tests/test_leakage_redteam.py` gives **30 passed, 1 xfailed in 5.53s**;
`python -m pytest -m leakage` collects the same 31.

### 6.3 What an ML researcher in this repository must now do

The probe is a capability, not a gate. Nothing on the research path calls `cross_validate`, so today
it protects nothing that runs. Concretely, from this point:

1. **A CV score without `transform_verified: True` is a diagnostic, not a result.** Quote
   `CVResult.summary()` verbatim in the journal entry; it ends in `probed` or in `UNVERIFIED`, and
   the distinction is the claim.
2. **Write the probe when you write the pipeline.** It is one function: copy the feature matrix,
   corrupt the masked rows, return a scorer over the copy. The red team's is nine lines
   (`tests/test_leakage_redteam.py:724`).
3. **Perturb, do not scale.** A uniform positive multiplier preserves order and is invisible to any
   rank, argmax or comparison (§9). Use a per-row random draw, and seed it.
4. **Compare exactly.** `np.isclose(atol=1e-8)` is how a 1e-9 leak worth 100% of the achievable
   profit went unnoticed (§9).
5. **The probe does not replace the fold check.** `check=True` (the default) still runs
   `assert_no_leakage` on every split. The two see different things and neither subsumes the other.
6. **It cannot see contamination already baked into the stored feature.** The probe perturbs rows of
   the array `fit_score` is handed. If the column was computed wrong before it reached the panel —
   which is what happened in F-15, F-16 and F-17 (§8) — every fold sees the same wrong column and
   nothing moves. **§8 is the failure the probe does not catch, and it is the one that actually
   happened here.**

---

## 7. Labels, horizon overlap, and the naive t

### 7.1 The correction exists

`quant_brain/core/stats.py:116` provides `tstat_hac(x, *, lag=None, horizon=None)` — Newey-West with
Bartlett weights. Passing `horizon` derives the lag through `lag_for_overlap` and **refuses a lag
below `horizon - 1`**, with a message that says why: *"a truncated lag leaves the overlap partly
uncorrected and still reports an inflated t"*. The module also carries `tstat_iid`,
`block_bootstrap_t`, `bonferroni_threshold` and `deflated`.

### 7.2 Nothing in the archive uses it

`tests/test_sweep_stats_audit.py` pins this as an executable measurement, and it passes today
(`python -m pytest tests/test_sweep_stats_audit.py -q` -> **39 passed**):

- `test_not_one_sweep_or_ml_script_imports_the_repos_stats_module` asserts the importer list is
  **empty** across all `scripts/sweep_*.py` + `scripts/ml_*.py` (73 + 14 = 87 files today; the
  test's own floor is 59).
- `TSTAT_SITES` (`:52`) enumerates **nine independent hand-rolled copies** of the t-statistic, and
  two parametrised tests assert that each one reproduces `stats.tstat_iid` to 1e-12 on a fixed
  sample *and* still returns the uncorrected number on a phi = 0.9 AR(1) series where HAC would
  change it by more than a third.

Every one of the 14 ML scripts computes every t through one of those nine — `sweep_f1.tstat`
(`sweep_f1.py:484`):

```python
sd = x.std(ddof=1)
return float(x.mean() / (sd / np.sqrt(n))) if sd > 0 else float("nan")
```

That is the plain iid t, applied both to daily net-P&L series and, through `ic_stats` (`:493`), to
per-timestamp Spearman IC series.

### 7.3 What that costs, per script, measured

`research/sweep_audit.md` (349 lines, dated 2026-09-13) prices it. The ML-relevant rows, each of
which I re-read against the code it cites:

| script | cells | defect | measured inflation | Bonferroni bar |
|---|---|---|---|---|
| `sweep_f3.py` | 10 | overlapping label + argmax + unpurged train/validation boundary | **1.66x** (h=5), **3.05x** (h=21) | 2.81 |
| `ml_f8.py` | 20 | argmax on the test window feeds a `t > 2` pass rule; the `close` label is **nested**, not merely overlapping | **1.94x** | 3.02 |
| `ml_f7.py` | — | IC(h) for h = 1..11 on cumulative returns sampled every interval | max **1.22x**, bounded by the session | — |

The F-3 row is the only place in the repository where a *published positive* claim dies under the
correction: IC +0.01133 at naive t **+2.17** becomes **+1.31** corrected, against a ten-cell bar of
2.81. Either correction alone refutes it, and
`test_sweep_stats_audit.py::test_f3s_published_ic_survives_neither_correction_alone_nor_the_pair`
pins the arithmetic.

`ml_f8.py`'s label is the sharpest case, and it is worth stating precisely because it is a shape the
next ML run could easily reproduce. `add_labels` (`:156-199`) builds the `close` label at **every**
one of 11 daily slots, all ending at the same 15:30 flatten, so within a session slot k's label is
slot k+1's plus one more interval — nested, not merely overlapping. Measured on
`data/f1/f8_preds.parquet`:

| label | slots/day | n | IC | naive t | HAC t | inflation |
|---|---|---|---|---|---|---|
| h4 | 8 | 15,432 | +0.01120 | +6.69 | +5.05 | 1.32x |
| h7 | 5 | 9,645 | +0.01081 | +5.35 | +3.58 | 1.50x |
| h10 | 2 | 3,858 | +0.01079 | +3.39 | +2.90 | 1.17x |
| **close** | **11** | **21,219** | +0.01104 | **+7.79** | **+4.02** | **1.94x** |

`close` is the label F-8 selects — the argmax of a 20-cell search, gated at `t > 2`, a threshold
calibrated for one pre-registered test. It carries the largest overlap inflation in the archive.

### 7.4 The one correction that runs the other way

On daily, non-overlapping return series the archive's naive t is **conservative**, not liberal:
`research/sweep_audit.md:255` measures daily equity returns mean-reverting at lag 1 (ac1 = -0.097),
so the iid standard error *overstates* the variance of the mean. This is worth saying because the
blanket sentence "the archive's t-statistics are inflated" is false, and a document that printed it
would be committing the error it is complaining about.

---

## 8. Feature contamination in F-16 and F-17

This is the section with the most measurement in it, because the claim that reaches this document —
`QUANT_MODEL_SYSTEM_AUDIT.md:187` — is right in substance and wrong in extent, in a direction that
matters.

### 8.1 What the gates admitted

`data/f1/f16_admitted.json` and `f17_admitted.json` record, per gate arm and per test year, exactly
which columns were admitted. Parsed read-only:

```python
import json, collections
f16 = json.load(open("data/f1/f16_admitted.json"))
f17 = json.load(open("data/f1/f17_admitted.json"))
cols, byyear = collections.Counter(), collections.defaultdict(set)
for doc in (f16, f17):
    for arm, years in doc.items():
        for y, cs in years.items():
            cols.update(cs); byyear[y] |= set(cs)
```

Five arms in total: `f16.q50` (pre-registered) and `f16.q25` (added post-hoc and explicitly barred
from F-16's adoption clause by its own docstring), `f17.pooled` (pre-registered), and `f17.flow` /
`f17.auction` (decomposition arms). Across all five:

| test year | admitted columns |
|---|---|
| 2019 | `amihud30`, `auc_osz_adv`, `clv30`, `cs_clv30`, `x_clv30` |
| 2020 | `amihud30`, `auc_osz_adv`, `ofi5` |
| 2021 | `clv30`, `cs_clv30`, `x_clv30` |
| 2022 | `auc_ofade`, `auc_osz_adv`, `cs_auc_ofade`, `x_auc_ofade` |
| 2023 | `auc_cdrift`, `auc_ofade`, `auc_osz_adv`, `cs_auc_cdrift`, `cs_auc_ofade`, `x_auc_cdrift`, `x_auc_ofade` |
| 2024 | `auc_ofade`, `auc_osz_adv`, `cs_auc_ofade`, `x_auc_ofade` |
| 2025 | `auc_ofade`, `auc_osz_adv`, `cs_auc_ofade`, `x_auc_ofade` |
| 2026 | `auc_ofade`, `auc_osz_adv`, `cs_auc_ofade`, `x_auc_ofade` |

**12 distinct columns, across all 8 test years.** Restricted to the two pre-registered arms
(`f16.q50` and `f17.pooled`) it is **9 distinct columns over 6 years**, which is the set
`QUANT_MODEL_SYSTEM_AUDIT.md:187` enumerates and which is a correct reading of those two arms.

### 8.2 Two corrections to the correction

That audit line already corrected an earlier claim that the sets were *"exactly and only three
columns"*. The correction is right and does not go far enough:

1. **It undercounts by three columns and two years.** The audit's list omits `f16.q25` entirely, and
   with it `auc_cdrift`, `x_auc_cdrift`, `cs_auc_cdrift` (2023) and every `auc_osz_adv` admission
   outside 2024. Full extent: **12 columns, 8 years**, not 9 columns and 6 years. There is **no year
   in which no gate arm admitted anything.**
2. **The three columns it omits are the ones the leak was actually measured on.** The audit's own
   evidence for the split-factor mechanism is a Spearman correlation between **`auc_cdrift`** and the
   future split factor. `auc_cdrift` appears in none of the arms the audit enumerates. So as written,
   the document proves a leak in a column it does not list and infers it structurally for the columns
   it does. §8.3 closes that gap by measuring the admitted columns directly.

### 8.3 Mechanism (a): a split-adjustment mismatch, measured on the admitted columns

`scripts/alpaca_data.py:39` fetches continuous minute bars with `adjustment: str = "split"` — the
bar store is **split-adjusted**. `ml_f15.auction_daily` (`:207`) reads the Alpaca auctions endpoint,
whose prices and sizes are **raw**, and then forms ratios that mix the two
(`scripts/ml_f15.py:249-256`):

```python
out["auc_osz_adv"] = d["open_sz"] / dvol_med                            # raw size / adjusted volume
out["auc_ofade"]   = 1e4 * (d["early_c"] / d["open_px"] - 1.0) / scale  # adjusted price / raw price
out["auc_cdrift"]  = 1e4 * (d["close_px"].shift(1) / d["last_c"].shift(1) - 1.0) / scale
```

A ratio of an adjusted price to a raw price **is** the cumulative split factor between that date and
the day the store was fetched. That factor is a fact about the future: it says whether the stock is
going to split. The three columns above are exactly the three parents the gates admitted.

Measured read-only on `data/f1/f15_famA.parquet` against `data/minute_alpaca/_splits.json`, where
the forward cumulative split factor for a date is the step function's value at that date:

| | |
|---|---|
| rows whose forward split factor is not 1.0 | **26,774 of 146,022 = 18.3%** |
| names with a factor change inside the sample | **14** |

Spearman correlation with that factor, per column, over the 14 affected names:

| column | median abs rho over the 14 | strongest names |
|---|---|---|
| `auc_cdrift` | **0.791** | TSLA +0.926, NVDA +0.910, GE +0.865, SOXL +0.864, AAPL +0.859, AMZN +0.848, GOOGL +0.844 |
| `auc_ofade` | **0.791** | SOXS **-0.986**, TSLA -0.873, SOXL -0.865, GE -0.865, AAPL -0.859 |
| `auc_osz_adv` | **0.801** | SOXS **-0.957**, TSLA -0.870, SOXL -0.849, AMZN -0.846, NVDA -0.837 |

The audit's headline **+0.844** is GOOGL's `auc_cdrift`; NVDA's is +0.910 on my construction of the
factor. NVDA's `auc_cdrift`, split by forward factor:

| NVDA forward split factor | sessions | median `auc_cdrift` |
|---|---|---|
| 40.0 (before both splits) | 1,384 | **1,655.98** |
| 10.0 (between them) | 727 | **274.36** |
| 1.0 (after both) | 564 | **0.0016** |

Six orders of magnitude between a pre-split and a post-split row, in a column whose stated units are
basis points of a trailing volatility. **The leak reaches all three admitted parents, not only
`auc_cdrift`, and on `auc_ofade` — the column the gates admitted most often — it is stronger than on
the column the audit measured.**

`auc_ofade`, `x_auc_ofade` and `cs_auc_ofade` are admitted in five of the eight test years, and
`auc_osz_adv` in seven of eight.

### 8.4 Mechanism (b): a SOXS fingerprint in `amihud30`

`data/minute_alpaca/SOXS.parquet`, measured:

| | |
|---|---|
| bars | **935,770** |
| zero-volume bars | **440,528 = 47.08%** |
| maximum close | **$768,499,200 per share** |
| zero-volume fraction by year | 2016 **1.0000**, 2017 **1.0000**, 2018 **1.0000**, 2019 **0.9999**, 2020 0.9887, 2021 0.6025, 2022 0.0191, then ~0 |

Split-adjusted volume on a heavily reverse-split inverse ETF, truncated to an integer, is zero. A
price divided by zero volume is not a liquidity measure; it is a marker saying "this row is SOXS
before 2021". Measured on `data/f1/f14_flow.parquet`:

| threshold on `amihud30` | rows | distinct names | top name's share |
|---|---|---|---|
| > 1 | 58,219 | 32 | SOXS 26.3% |
| > 5 | 10,587 | 5 | SOXS 97.6% |
| > 10 | **10,283** | **1** | **SOXS 100%** |
| > 40 | **10,283** | **1** | **SOXS 100%** |

SOXS is 1.66% of the store's rows. Its `amihud30` median is 2.005 against 0.216 for every other
name, and its maximum is 47.27 against 6.85. The years carrying those rows are **2016 (1,103),
2017 (1,629), 2018 (2,454), 2019 (2,621), 2020 (2,329), 2021 (147)** — the fingerprint starts in
2016, not in 2019.

`amihud30` is admitted in 2019 and 2020, the two years in which it is at its most SOXS-shaped.

### 8.5 Mechanism (c): the stale early-close cache, which the ML track found itself

The track's own journal never uses the words "split" or "SOXS" about any of this. Its explanation is
a different and independently proven defect, and it is the one that withdrew F-16:

- **F-19** (`research/journal_ml.md:475`). The panel was built 2026-09-11 11:44;
  `intraday_common.load_bars` only learned to drop post-early-close bars at 04:04 on 2026-09-13, and
  separately `sweep_f1.build_panel` gained `forward_span_mask` in `c2350a8` on 2026-09-12 16:49.
  **F-14, F-15, F-16 and F-17 all ran on a pre-fix cache.** The rebuild removes 15,358 rows (0.965%)
  and changes at least one feature on **574,287 of 1,576,616 surviving rows (36.4%), over 1,854
  sessions**. On the clean panel the gate admits **nothing in 8 of 8 years**
  (`data/f1/f19_admitted.json` — verified: every list empty) and `auc_ofade` loses **30-36% of its
  |IC|**. `auc_ofade` was measured as the single most contaminated auction column, at 15.0% of rows:
  its `scale` denominator is a 20-session trailing vol built from `last_c`, the session's last
  continuous bar, which on an early close is a post-market print.
- **F-20** (`research/journal_ml.md:299`). The flow store was rebuilt and came back
  **bit-identical** — 0 of 1,570,406 shared rows changed, on any of 20 columns, max abs delta 0 —
  and the gate still changed **6 of its 8 decisions**, because the floor and the incumbent set it
  measures against are panel columns. The admitted set becomes `dvol30` (2019-2022), `clv5` (2024),
  `ofi_sess` + `cs_ofi_sess` (2026) (`data/f1/f20_admitted.json`, verified). **None of F-17's
  columns is admitted on the clean panel, and none of F-20's was admitted on the dirty one.**
- **F-23** (`research/journal_ml.md:9`). Of the six admissions in the gate's entire history, four
  are contested and every one turns on an |IC| gap of **0.28 to 0.47 of the winning candidate's own
  IC standard error**; the other two clear the floor by 0.032 and 0.0006 standard errors. **Zero of
  six are resolvable.** In 2019 the two rivals are `dvol30` (|IC| 0.02325) and `amihud30` (0.02187),
  correlated at **0.876-0.886**, separated by **0.0014**.

### 8.6 Reading all of it together

Three mechanisms, independently measured, all landing on the same six admissions:

| mechanism | evidence | reaches |
|---|---|---|
| split-adjustment mismatch | rho up to 0.99 against the future split factor, 18.3% of rows, 14 names (§8.3) | `auc_ofade`, `auc_osz_adv`, `auc_cdrift` and their `x_`/`cs_` companions — **7 of the 12** |
| SOXS zero-volume fingerprint | `amihud30 > 10` selects 10,283 rows, 100% SOXS (§8.4) | `amihud30` — **1 of the 12** |
| stale early-close cache | 36.4% of panel rows moved; `auc_ofade` lost 30-36% of its \|IC\| (§8.5) | the floor and the incumbents, i.e. **every** admission |

The three do not all bear on every column, and this document will not claim they do. `clv30`,
`x_clv30`, `cs_clv30` and `ofi5` — 4 of the 12 — have no direct contamination evidence of their own.
What they have instead is F-23's finding that the decision to admit them was inside the noise, and
F-20's finding that they are not admitted at all once the substrate is fixed.

What is nonetheless true, and is the point:

> **F-16's $412/day at t +1.97 — the best net this track has ever fitted, and the number its whole
> discussion turned on — rests on a single admitted column, `auc_ofade`, which (i) mixes a
> split-adjusted price with a raw one and correlates with the future split factor at |rho| up to
> 0.99, (ii) was the most early-close-contaminated column in its family at 15.0% of rows, and
> (iii) is not admitted at all once either defect is fixed.**

---

## 9. The futures causality guard, and why it does not protect this path

`quant_brain/markets/futures_cme/features.py::assert_causal` (`:258`) perturbs a bar and requires
that no *earlier* value of a feature move. `futures_discover.build_features` calls it on three
sessions of every run and raises `validation.LeakageError` on failure. It was hardened on 2026-09-13
in three ways; each closed a blind spot with a measured counter-example in
`tests/test_leakage_redteam.py` section E (`:913-1073`).

**1. Every numeric column, not the hard-coded `c/h/l/o/v`.** The shipped bump touched five columns.
`bid.shift(-1)` — tomorrow's bid, a leak wearing no disguise — came back **bit-identical** and the
guard called it clean; a bump that included the quote columns found it at bar 207 of 320. The wider
consequence was worse than one missed counter-example: the feature library's microstructure family
declares `bid`, `ask`, `bid_size` and `ask_size`, so **`spread_bps` and `quote_imbalance` had never
once been tested by the audit that reported them clean.** With every numeric column perturbed the
same leak is caught at bar 1 (`4997.875 -> 15711.614`). The source states why `requires` is the
floor and not the ceiling: `fn` is handed the whole frame, so stopping at the declared set would
exempt any feature that under-declares what it reads.

**2. A seeded per-row random draw, not a uniform x1.05.** A uniform positive multiplier **preserves
order**. Any argmax, rank, "which came first", or order statistic taken over a window that lies
wholly inside the bumped region is exactly invariant to it. The counter-example is the position of
the maximum close among the session's last five bars, known at bar 0: bit-identical under the
shipped bump, caught at bar 0 (`0.0 -> 3.0`) under the new one. The bump is now
`tail * U(1.5, 4.5) + N(0, sd(tail))` per row — scale *and* jitter, because zero is a fixed point of
a pure multiplier and an all-zero volume stretch would otherwise pass through unchanged. The draw is
seeded, and the reason is in the source: *"a guard whose verdict changes between runs is not a
guard: a leak that fails on one run and passes on the next gets re-run until it passes."*

**3. Exact `!=`, not `np.isclose(rtol=1e-5, atol=1e-8)`.** A leak carried at amplitude 1e-9 on a
base of 1.0 sits inside that tolerance. Its *sign* recovers the next bar's direction exactly, and
the red team pushed it through the funnel for **100.00% of the theoretical profit ceiling**, clearing
every gate on the way (`test_sub_tolerance_leak_is_exploitable_to_the_entire_ceiling`, `:1040`).
**A leak's amplitude and a leak's value are different quantities, and an absolute tolerance confuses
them.** The comparison can afford to be exact: the measured worst head deviation across all 19
shipped features at all 9 probe points is exactly **0.0**, so no tolerance was needed. The 2e-9 leak
is now caught at bar 1.

A fourth change, older and in the same function, belongs beside these: `assert_causal` **sweeps nine
probe points weighted toward the start of the session** (`[3, 5, 10, 20, 31, warmup+2, 0.25n, 0.5n,
0.8n]`) instead of probing once at 80%. The single-probe version is how `opening_range_pos` shipped
with a look-ahead confined to the first 30 bars, produced the only positive result the futures
funnel ever recorded (t +6.25), and had to be retracted.

**None of this runs on the ML path.** `audit_causality` is called from `scripts/futures_discover.py`
and nowhere else; gate 0 (`MAX_CEILING_SHARE`) lives in the futures evaluator.
`algorithms/intraday/CONTRACT.md` and `algorithms/intraday/base.py` state a causality convention and
**nothing executes it**. The protection on the equity and intraday paths is
`tests/test_leakage_redteam.py` at commit time, which injects planted cheats into real entry points
including `sweep_s19.simulate` and `sweep_s25.legs_simulate` — and its one open defect, the single
`xfail`, is that `sweep_s25.legs_simulate` hands its `weights_fn` a bare timestamp, so a guard that
discriminated would have to test the weights against the next session's realised return: the equity
analogue of gate 0, and unbuilt.

The generalisable lesson from §8, stated against these three fixes: **all four checks are checks on
a transformation, and F-16's defect was in the input.** `auc_ofade` is perfectly causal. It reads no
future bar. It is contaminated because two of its inputs were adjusted on different bases. No
perturbation of the frame it is handed will ever reveal that.

---

## 10. Where I corrected the record

1. **"Exactly and only three columns"** — attributed by `QUANT_MODEL_SYSTEM_AUDIT.md:187` to an
   earlier ML agent whose original text is not in this repository. Already corrected there to nine
   columns over six years, which is right for the two pre-registered arms. Counting every recorded
   arm it is **12 columns over all 8 years**, and the three the audit omits (`auc_cdrift`,
   `x_auc_cdrift`, `cs_auc_cdrift`) are the ones its own leak measurement was performed on.
   §8.1-8.2.
2. **`amihud30 > 40` selects "10,136 rows, 100% SOXS"** (`QUANT_MODEL_SYSTEM_AUDIT.md:298`). The
   100% SOXS reproduces exactly. The count does not: **10,283** on the current `f14_flow.parquet`
   and **10,285** on `f14_flow.dirty.parquet`. Neither is 10,136. The threshold is also not
   load-bearing — the set is already 100% SOXS at `> 10`. §8.4.
3. **"zero-volume fraction 1.000 for every year 2016-2019"** (same line). 2016, 2017 and 2018 are
   exactly 1.0000; **2019 is 0.9999**. §8.4.
4. **The split-factor leak described as a 2024-26 phenomenon.** The affected columns are admitted in
   **2019, 2020 and 2022-2026** — seven of the eight test years — once `f16.q25` is counted. And the
   SOXS fingerprint in `amihud30` spans **2016-2021**, not 2019-21. §8.1, §8.4.

And two things in the repository's own documentation are themselves stale:

5. `AGENTS.md` names `algorithms/intraday/ml/` as the ML scope's directory. **It does not exist.**
   §1.2.
6. `research/sweep_audit.md:3` opens "62 `scripts/sweep_*.py` / `scripts/ml_*.py` exist". Today there
   are **87** (73 + 14). Its conclusions are unaffected — the scripts added since are not new
   t-statistic sites — but the denominator in its first sentence is no longer the one on disk.

---

## 11. What is not built

Stated explicitly, because the failure mode this repository is guarding against is describing things
as though they run.

- **No purged or embargoed cross-validation anywhere on the research path.** Zero of 87
  `sweep_*`/`ml_*` files contain the string `purge` or `embargo`. `purged_walk_forward` is called
  only by tests.
- **No holdout.** `make_holdout` has never been called, `spend()` has never run, and no holdout
  ledger exists on disk. The window that would be one has been scored 104 times.
- **No probe on any real pipeline.** `cross_validate(probe=...)` exists, works, and is called only
  by `tests/test_leakage_redteam.py`.
- **No HAC anywhere in the archive.** Nine hand-rolled iid t-statistics; zero importers of
  `quant_brain.core.stats`.
- **No multiplicity correction on any ML result.** `Ledger.verdict`'s Bonferroni denominator reads
  `research/experiments_futures.jsonl`; the 135 ML rows live in `research/experiments.jsonl`, of
  which `Ledger.all()` parses **0**.
- **No run-time causality audit on the ML path.** The guard is futures-only.
- **No provenance on any ML row.** 0 of 135 carry a commit, a provenance block, or
  `reproducible: true`.
- **No content hash on any feature store.** `panel.meta.json`, `f14_flow.meta.json` and
  `f21_panel62.meta.json` record build parameters, not digests. That is the exact gap that let F-14,
  F-15, F-16 and F-17 all run against a cache whose inputs had moved, each passing an identity check
  against the same stale file.
- **No saved model.** Every fitted estimator is discarded; only predictions are frozen. A published
  arm cannot be re-scored on new data without a refit, and a refit is not the same model.
- **No deployed ML.** Nothing on the production path imports the track, and the directory that would
  hold a deployed signal does not exist.

---

## 12. What an ML result here would need in order to be believable

A checklist. **Nothing below is enforced by code**; each item names what would enforce it if it
existed. Numbered so a journal entry can cite an item. Items 1-9 are specific to ML and are in
addition to `docs/RESEARCH_PROTOCOL.md` §8 items 17-26, which apply to any result.

**Before the fit**

1. **State the label's horizon in the same units as the fold boundary, and state the purge width
   that follows.** If the horizon is intra-session and the folds are calendar years, say so and say
   the purge is zero — that is a finding, not an omission. *Would be enforced by:*
   `purged_walk_forward(horizon=...)`, which refuses to guess a horizon.
2. **Name the trial budget and the family before the grid runs.** F-8's `t > 2` was applied to the
   argmax of 20 cells; the bar for 20 cells is 3.02. *Would be enforced by:* `Ledger.record` +
   `Ledger.verdict`, neither of which any ML script calls.
3. **Carve the holdout first.** One call to `validation.make_holdout` with a `ledger_path`, before
   the first fit rather than after the first promising number. *Would be enforced by:*
   `Holdout.spend`, which raises on the second look.

**At fit time**

4. **Fit every transform inside the fold, and prove it with a probe.** Pass `probe=` to
   `cross_validate` and quote `CVResult.summary()`; if it ends in `UNVERIFIED` the pipeline is
   unchecked and must be described that way. Perturb with a seeded per-row random draw and compare
   exactly. *Would be enforced by:* `cross_validate(probe=...)`, unused on any real pipeline.
5. **Hash the input store and record the digest with the run.** F-14 through F-17 each passed an
   identity check against the same stale cache; a reproduction test against a cache cannot detect
   that the cache is stale. *Would be enforced by:* nothing. `Provenance.capture()` records the
   interpreter and the commit but no dataset digest, and `dataset_version` is `""` on all 59 rows
   anywhere in the repository that carry a provenance block.
6. **Audit the feature's construction, not only its causality.** Every ratio must state the
   adjustment basis of its numerator and of its denominator. The check that would have caught F-16
   is one line — correlate each candidate against the forward cumulative split factor and refuse
   anything above a threshold. *Would be enforced by:* nothing.

**When reading the result**

7. **Report the HAC t beside the naive one**, with the lag and the reason for the lag. On a
   non-overlapping daily series the two will be close and the naive one may be the *conservative*
   one; say which. *Would be enforced by:* `stats.tstat_hac(x, horizon=h)`, which refuses a
   truncated lag.
8. **Report the margin, not only the decision.** F-23's rule: an admission whose gap to the
   displaced rival is smaller than the winner's own IC standard error is UNRESOLVED, not an
   admission. Six of six admissions in this track's history fail it. Extend it to the floor as well
   as to the rival.
9. **Run the scramble control and put it in the same table.** F-17's `pooled_scrambled` beat every
   real arm on the statistic that run led with. A lead statistic that ranks a no-information control
   first is not a lead statistic — which is how F-24 came to replace the rank IC with the slot-0
   decile spread (sign agreement 11/12 against 9/12, Spearman +0.993 against +0.699).

**Before it is called evidence**

10. **Name which of items 1-9 were done and which were not.** Not which facilities exist — which
    ran. Today the honest answer for every row in `research/experiments.jsonl` is: none of 1, 3, 4,
    5, 6 or 7.
11. **Say what would have to be true for the result to be an artefact, and say whether you checked.**
    F-19's premise was one sentence handed over by another track — "the panel predates a loader fix"
    — and it withdrew the best number this track had produced.
12. **A result that cannot answer 10 and 11 is a diagnostic.** It may be quoted as an observation or
    as a reason to run something else. It may not enter a promotion argument, and no ML result in
    this repository currently can.
