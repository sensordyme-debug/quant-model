# Research: the ledger, the funnel, the ladder, and what has survived them (nothing)

Status of this document: describes code under `quant_brain/research/` and
`quant_brain/core/validation.py` as it exists at commit `2a7367f` (2026-09-13). Every claim
names the file that supports it. Where a facility exists but nothing in the repository calls
it, that is stated rather than implied away.

| claim | status | evidence |
|---|---|---|
| ENGINE VALIDATED | yes | `tests/test_qb_research.py`, `tests/test_qb_features_search.py`, `tests/test_qb_promotion.py`, `tests/test_qb_validation.py` - 1,550 tests collected repo-wide on 2026-09-13, all of these among them |
| STRATEGY VALIDATED | **no** | 817 experiments in `research/experiments_futures.jsonl`, every one REJECTED; the single survivor ever produced was retracted as a lookahead |
| LIVE EXECUTION VALIDATED | **no** | no futures adapter can send an order (`docs/topstep/EXECUTION.md`); the equity runners trade an IBKR **paper** account |
| PROFITABILITY DEMONSTRATED | **no** | nothing in this repository has demonstrated a profit on any account, paper or otherwise |

---

## Two ledgers, and only one of them counts trials

There are two experiment ledgers in `research/`, with different schemas and different
guarantees. Confusing them overstates what the second one protects.

| file | rows (2026-09-13) | written by | schema | multiplicity accounting |
|---|---|---|---|---|
| `research/experiments.jsonl` | 1,647 | `scripts/backtest.py`, `scripts/intraday_backtest.py` | `algorithm, class, commit, end, params, run_dir, start, stats, tag, track, ts` - no `experiment_id`, no `family` | **none**. Rows are appended; no verdict, no trial count |
| `research/experiments_futures.jsonl` | 818 (817 experiments + 1 retraction) | `scripts/futures_discover.py`, `scripts/futures_topstep_baseline.py`, through `quant_brain.research.Ledger` | `Experiment.to_dict()` in `quant_brain/research/registry.py` | yes, as described below |

`AGENTS.md`'s instruction that every idea gets a row in `research/experiments.jsonl` is
followed. The property "the trial count is not an argument" applies only to the futures
ledger, because only `Ledger` implements it. `quant_brain/core/knowledge.py` (the "have we
tried this?" index) reads `experiments.jsonl` only (`knowledge.py:200`), so the 817 futures
rows are invisible to it.

---

## The ledger: `quant_brain/research/registry.py`

**An experiment is a fingerprint.** `Experiment.fingerprint()` is a SHA-256 over
`{hypothesis, family, params}` and deliberately excludes metrics, timestamp and verdict.
Re-running the same specification is the same experiment: `Ledger.record()` returns the
prior row instead of appending, and `Ledger.trials(family)` counts distinct fingerprints, not
rows. A search therefore cannot inflate its own penalty by repeating itself, and cannot
launder multiplicity by re-running until a number comes out right
(`test_re_running_the_same_specification_does_not_add_a_trial`,
`test_identity_comes_from_the_specification_not_the_outcome`).

**A family is required.** `Experiment.__post_init__` raises on a blank family, because the
family is the unit multiplicity is counted over and an unnamed one would escape it.

**The trial count is read from disk.** `Ledger.verdict(experiment, series, *, horizon=1)`
has no `n_trials` parameter. It calls `self.trials(experiment.family)`, adds one if this
experiment is new, computes `stats.tstat_hac(series, horizon=horizon)` and compares against
`stats.bonferroni_threshold(n)`. `tests/test_qb_research.py:56` asserts the signature exposes
none of `n_trials`, `trials`, `num_trials`, `alpha`, `override`, `force`. Measured on the
futures ledger: the first hypothesis in a family faces |t| > 1.96, the 136th faces |t| > 3.56
(`python -m quant_brain research ledger`, "bar at n" column).

**Rejected experiments stay in the denominator.** `Stage.REJECTED` rows are never deleted;
`trials()` counts them (`test_rejected_experiments_stay_in_the_denominator`).

**Appends are locked and fsynced.** The lock is an `O_CREAT | O_EXCL` lock file with a 10 s
stale-lock breaker (`registry._file_lock`; in an uncommitted change present on disk at the
time of writing it lives in `quant_brain/core/locking.py` and is re-exported under the old
name). Six agent tracks write this tree concurrently, and the docstring records that unlocked
appends lost three of eight rows on this machine because Windows emulates `O_APPEND` with
seek-then-write. The duplicate check and the append happen under the same lock
(`test_concurrent_records_do_not_lose_experiments`,
`test_concurrent_duplicates_still_count_as_one_trial`).

**Provenance rides along.** `Experiment.provenance` is a `core.provenance.Provenance` whose
`env_key` records interpreter and numeric-stack versions; `from_dict` rebuilds it, filtered to
the current field set so rows written by older code still load
(`test_provenance_survives_the_round_trip`, `test_a_row_written_by_older_code_still_loads`).

---

## The funnel: `quant_brain/research/search.py`

`search(hypotheses, *, ledger, evaluate, limits, horizon)` runs each hypothesis through four
gates and records every outcome in the ledger, rejections included.

```
generated
  -> duplicate?    ledger.seen by fingerprint: not re-run, not re-counted
  -> too short?    sessions < Limits.min_sessions (default 100) -> REJECTED
  -> gate 1  statistics        ledger.verdict at the ledger's own trial count
  -> gate 2  cost / execution  result["cost_ok"]
  -> gate 3  Topstep survival  result["topstep_ok"]
  -> gate 4  walk-forward      result["walkforward_ok"]
  -> Stage.VALIDATION          "survived every gate; eligible for the holdout"
```

### The order is load-bearing

Statistics first, then costs, then survival, then walk-forward - increasing cost, and the
statistical gate first. The module docstring gives the reason that matters: the multiplicity
penalty must be paid on every hypothesis **tried**, not on the ones that reached the end. If
the statistical gate ran last, the survivors would have been pre-selected by filters the
correction cannot see, and the reported t would describe a much smaller search than the one
that happened. `test_the_statistical_gate_runs_first` pins the order.

### What bounds it

`Limits`: `max_experiments` (200), `max_seconds` (600), `stop_above_pressure` ("high", read
from `core.resources.snapshot().pressure` between candidates), `min_sessions` (100). The
`Funnel` result records which limit stopped the loop and where every hypothesis died
(`Funnel.table()`). A resumed search skips fingerprints already in the ledger, which is what
makes it resumable (`test_a_resumed_search_skips_what_is_already_in_the_ledger`).

### A survivor reaches VALIDATION and no further

`test_a_survivor_reaches_validation_not_champion`. The funnel promotes nothing past the first
rung; the gate in `promotion.py` owns everything after that.

### What the gates actually are in the one driver that runs them

`scripts/futures_discover.py` is the only caller of `search()`. Its `evaluator()` supplies the
gate booleans, and the thresholds are named constants in that file:

| gate | implementation in `futures_discover.py` | threshold |
|---|---|---|
| cost / execution | round turns `< MIN_TRADES` -> "not a strategy"; else `costs / abs(gross) > MAX_COST_SHARE` | 40 trades; 60% of gross |
| Topstep survival | `twin.evaluate_twin` over `paths.moving_block(days, block=10, reps=150)` on a `$50K` Combine twin with a 50% payout policy; `p_pass_combine < MIN_PASS_RATE` | 10% |
| walk-forward | `np.array_split(pnl, 5)`; count folds with `mean > 0`; fewer than `MIN_WF_FOLDS` positive fails | 3 of 5 |

Two things to read off that table honestly. The "walk-forward" gate is a five-block sign
test on the realised per-session P&L sequence. Nothing is fitted, so there is no train/test
boundary and no purge; `core/validation.purged_walk_forward` is **not** called here or by any
other script (the only references outside its own module are in `promotion.py`, for the
`Holdout` type). And costs are charged as `ExecutionSimulator.round_turn_cost(contracts)` per
turn on close-to-close P&L with a one-bar lag; the simulator's fill-price, impact and
rejection logic (`execute()`) is not exercised by the funnel. See `docs/BACKTESTING.md`.

---

## The result: 544 hypotheses, 0 survivors

Two passes have been run over the futures store, and the first produced the only survivor in
the repository's history.

**Pass 1 (families `futures.es.threshold_grid`, `futures.nq.threshold_grid`, 136 hypotheses
each, 272 total).** One hypothesis survived: `opening_range_pos > +0.50 dir -1` on NQ, at
t = +6.25 against a 3.56 bar, "5 of 5 walk-forward folds positive", $140.75 per session on a
single MNQ. It was produced by a lookahead. `features._opening_range_pos` divided every bar
by the high-low range of the first 30 bars **including bars later than the one being
labelled**, so bar 5 knew the extremes of bars 6-29. The feature's docstring keeps the
history; `assert_causal` was rewritten to sweep early bars because a single probe at 80%
through the series could not see a leak confined to the first thirty
(`test_a_late_only_probe_would_still_miss_it`). Commit `90704c4`.

**Pass 2 (the `.v2` families, feature made causal, all four stored contracts).**

| family | rejected: statistical | rejected: cost | reached Topstep gate | reached walk-forward | survived |
|---|---|---|---|---|---|
| `futures.es.threshold_grid.v2` | 124 | 12 | 0 | 0 | 0 |
| `futures.mes.threshold_grid.v2` | 127 | 9 | 0 | 0 | 0 |
| `futures.nq.threshold_grid.v2` | 134 | 2 | 0 | 0 | 0 |
| `futures.mnq.threshold_grid.v2` | 135 | 1 | 0 | 0 | 0 |

Source: `research/futures_discovery_{es,mes,nq,mnq}.json` and `research/journal_futures.md`.
544 in, 544 rejected, and no hypothesis reached the Topstep gate. Those runs landed in commit
`98512df` under another track's message; `3a7b764` records why.

The ledger today (`python -m quant_brain research ledger`, 2026-09-13):

```
research\experiments_futures.jsonl: 817 experiment(s) across 7 famil(y/ies) [rejected=817]

family                                    trials  passed  bar at n
futures.es.intraday_momentum                   1       0      1.96
futures.es.threshold_grid                    136      13      3.56
futures.es.threshold_grid.v2                 136      12      3.56
futures.mes.threshold_grid.v2                136       9      3.56
futures.mnq.threshold_grid.v2                136       1      3.56
futures.nq.threshold_grid                    136       4      3.56
futures.nq.threshold_grid.v2                 136       2      3.56
```

Read the `passed` column carefully: it counts experiments whose **statistical verdict**
passed (`e.verdict.passed`), i.e. hypotheses that cleared gate 1 and were then rejected at
gate 2. It is not a survivor count. Every row is `rejected`.

The seventh family is `scripts/futures_topstep_baseline.py`'s pre-registered
first-30-minute-momentum strategy: 325 ES sessions, mean $2.39 per session, HAC t = +0.23
against a 1.96 bar at one trial (`research/futures_topstep_baseline.json`).

---

## Retraction: `Ledger.retract(experiment_id, *, why)`

A retraction is an **appended** row `{"_retraction": id, "why": ..., "when": ...}`, never an
edit. `Ledger.all()` applies it on read by moving the experiment to `Stage.REJECTED` and
writing `RETRACTED: <why>` into its notes. The original row stays byte-identical on disk
(`test_the_original_row_stays_byte_identical_on_disk`), `trials()` is unchanged
(`test_a_retraction_withdraws_the_verdict_without_deleting_the_trial`), and a blank reason is
refused. The one retraction on disk:

```
_retraction 0100e0062ede61b4   2026-09-13T05:15:42-04:00
why: produced by a lookahead in opening_range_pos, which used the first 30 bars' high and
     low at every bar INCLUDING those first 30. Re-run on the identical grid with the
     feature made causal: 0 survivors.
```

The raw row for `0100e0062ede61b4` still says `"stage": "validation"`; the reader is what
says REJECTED. Any tool that reads the JSONL without `Ledger.all()` will see a survivor that
does not exist.

---

## The promotion ladder: `registry.Stage` and `research/promotion.py`

```
RESEARCH -> VALIDATION -> CHALLENGER -> PAPER -> CHAMPION
                 REJECTED is reachable from every rung and is terminal
```

`registry.ALLOWED` is the only transition table; `Candidate.advance(to, *, why)` raises on
anything else and on a blank reason (`test_a_candidate_cannot_skip_a_rung`).

`PromotionGate.decide(evidence, *, to)` returns a `Decision` naming every condition, never a
bool. Conditions are cumulative by rung (`CHECKS_BY_RUNG`, `test_the_rungs_are_cumulative`):

| condition | required from | what it checks |
|---|---|---|
| `ladder` | VALIDATION | the transition is in `ALLOWED` |
| `statistical` | VALIDATION | the verdict passed **and** was taken at the trial count the ledger holds now (`test_a_verdict_taken_before_the_search_grew_is_refused`) |
| `costs` | VALIDATION | costs below `Rules.max_cost_share` (0.35) of **gross** profit |
| `topstep` | VALIDATION | pass rate over resampled paths at least `Rules.min_topstep_pass_rate` (0.35) |
| `walk_forward` | VALIDATION | at least `Rules.min_folds` (4) folds, `min_fold_win_rate` (0.6) positive, and a positive mean |
| `holdout` | CHALLENGER | the holdout ledger holds exactly one look, stamped with this candidate's id, and it passed |
| `beats_champion` | CHAMPION | strictly better than the incumbent by `min_beat_margin` (0.0) |
| `reproducible` | advisory only | clean tree at run time; reported, never blocking |

Before any condition is measured, `refuse_cross_environment` raises `EnvironmentMismatch` if
challenger and champion carry different `env_key`s or an unrecorded one - a py3.11/pandas 2.2
number and a py3.14/pandas 3.0 number are not compared, they are refused
(`test_comparing_a_py314_challenger_with_a_py311_champion_raises`). `apply()` refuses a
failing, mismatched or stale decision. There is no `force` or `override` keyword
(`test_there_is_no_keyword_that_forces_a_promotion`).

**No production code constructs a `PromotionGate` or a `Candidate`.** The only references
are inside `promotion.py` and `tests/test_qb_promotion.py`. The equity champion in
`research/champion.json` is promoted by `scripts/evaluate.py --promote`, which applies its own
rules (the "criteria" block in `champion.json`) and has no connection to this ladder.

---

## The holdout: `core/validation.Holdout`

`make_holdout(data, *, fraction=0.2, ledger_path, label)` carves the final fifth of a series
and fingerprints the data bytes plus `n`, `fraction` and `label`. `Holdout.spend(result=,
note=)` appends to `ledger_path`; a second `spend` on the same fingerprint raises
`LeakageError` unless `force=True`, and the forced record says which look number it was
(`test_a_second_look_is_refused`, `test_the_refusal_survives_a_new_process`).
`purged_train_index(horizon)` purges the training side the same way the CV folds are purged.

`PromotionGate.spend_holdout()` wraps this with the candidate stamp and takes no `force`
parameter, so a burnt holdout cannot be used for a promotion through the supported path
(`test_spend_holdout_offers_no_way_to_force_a_second_look`,
`test_a_candidate_cannot_ride_on_another_candidates_holdout_look`).

**No holdout has ever been carved or spent in this repository.** `make_holdout` has no caller
outside `validation.py`, `promotion.py` and the tests, and no holdout ledger file exists on
disk. `Stage.VALIDATION`'s note "eligible for the holdout" describes a next step no code has
taken, which is consistent with nothing having reached VALIDATION.

---

## Not implemented

- A purged walk-forward inside the funnel. Gate 4 is a five-block sign test on realised
  P&L (`scripts/futures_discover.py`); `validation.purged_walk_forward` and `cross_validate`
  have no caller outside their module, `promotion.py` and the tests.
- Any use of the holdout. Never carved, never spent.
- Any use of `PromotionGate`, `Candidate` or the five-rung ladder by a runner or a script.
  `research/champion.json` moves only through `scripts/evaluate.py --promote`.
- Multiplicity accounting for the equity ledger. `research/experiments.jsonl` has no family,
  no fingerprint and no verdict; `research/sweep_audit.md` measured that zero of the 62
  sweep/ml scripts import `quant_brain.core.stats`.
- Any consumer of `research/experiments_futures.jsonl` besides `python -m quant_brain
  research ledger`, `topstep readiness` and the two futures scripts. `core/knowledge.py`
  does not read it.
- Hypothesis generation beyond `threshold_hypotheses` (one feature, one threshold, one
  direction). The docstring of `futures_discover.py` says so: the grid exists to measure the
  funnel, not to find an edge.
- Enough history for the funnel to resolve an intraday edge. The deepest futures series is
  395 sessions against ~2,000 measured as necessary (`BLOCKERS.md` OWNER-3).

## What this document does not claim

It does not claim any hypothesis has an edge; the count is 544 tried, 0 survived, 1 retracted.
It does not claim the promotion ladder or the holdout have been exercised on real research;
they are tested library code with no caller. It does not claim the equity ledger carries the
protections described here; it does not. It does not claim the funnel's walk-forward gate is
a purged walk-forward; it is a sign test over five contiguous blocks of realised P&L.
