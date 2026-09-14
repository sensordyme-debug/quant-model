# Research protocol: what has to be true before a number from this repository may be quoted

Status of this document: describes `research/experiments.jsonl`,
`research/experiments_futures.jsonl`, `quant_brain/research/{registry,search,promotion}.py`,
`quant_brain/core/{stats,multipletest,validation,provenance}.py`, `scripts/futures_discover.py`
and `scripts/evaluate.py` at commit `4fbc22e` (2026-09-13). The numbers below were measured
against the **working tree**, not the commit: several agent tracks were editing this tree
concurrently while this was written, so line numbers may drift by a few lines and every
citation also names the symbol. Every number names the file and function that produces it or
the read-only command that measured it. Where a facility exists but nothing calls it, that is
stated, not implied away.

| claim | status | evidence |
|---|---|---|
| A RESEARCH PROTOCOL IS ENFORCED | **no** | nothing in the repository refuses a result for skipping a step; the sections below are a procedure, not a gate |
| MULTIPLICITY IS CORRECTED | **partly** | `Ledger.verdict` corrects the 817 futures rows; the 1,653 equity rows carry no trial count, no family and no verdict |
| A HOLDOUT EXISTS | **no** | `make_holdout` has never been called; no holdout ledger exists on disk |
| STRATEGY VALIDATED | **no** | 817 futures experiments, all rejected on read; the one survivor was retracted as a lookahead |
| PROFITABILITY DEMONSTRATED | **no** | |

---

## 0. Why this document exists

A hostile audit of this repository found that results are quoted without a procedure that says
when quoting is allowed. That is not a gap documentation can close on its own. Sections 1 to 7
below are the measured state; section 8 is a checklist. The checklist is enforced by nothing.
Treating it as enforced is the exact failure it describes.

---

## 1. Two ledgers, and they are incompatible

| file | lines | parsed by `Ledger.all()` | keys on a row | trial accounting |
|---|---|---|---|---|
| `research/experiments.jsonl` | 1,653 | **0** | `algorithm, class, commit, end, params, run_dir, start, stats, tag, track, ts` (plus `env_key, provenance, reproducible` on 59) | none |
| `research/experiments_futures.jsonl` | 818 (817 experiments + 1 retraction) | 817 | `created, experiment_id, family, hypothesis, metrics, notes, params, provenance, stage, verdict` | yes, per family |

Measured:

    python -c "import json; f=lambda p: sum(1 for l in open(p,encoding='utf-8') if l.strip()); print(f('research/experiments.jsonl'), f('research/experiments_futures.jsonl'))"
    # 1653 818

    python -c "import sys; sys.path.insert(0,'.'); from quant_brain.research.registry import Ledger; print(len(Ledger('research/experiments.jsonl').all()), len(Ledger('research/experiments_futures.jsonl').all()))"
    # 0 817

The mechanism is `Experiment.from_dict` in `quant_brain/research/registry.py`, which reads
`d["hypothesis"]` and `d["family"]`. No equity row has either key, so every one raises
`KeyError`, and `Ledger.all()`'s `except KeyError: continue` drops it. The reader does not
report a schema mismatch; it reports an empty ledger. The repository's own CLI shows this:

    python -m quant_brain research ledger --path research/experiments.jsonl
    #   research\experiments.jsonl: 0 experiment(s) across 0 famil(y/ies)

Two further consequences, both verified:

- `quant_brain/core/knowledge.py` -- the "has this already been tested?" index -- reads
  `research/experiments.jsonl` only (`knowledge.py:200`). It cannot see the 817 futures rows.
- `quant_brain/__main__.py:302` defaults `qb research ledger` to
  `research/experiments_futures.jsonl`. It reports nothing about the 1,653 equity rows.

So the duplicate-detection facility and the trial-counting facility point at different
ledgers, and neither covers both. A researcher asking "has this been tried" and a researcher
asking "how many trials is this" are reading two disjoint histories.

---

## 2. Multiplicity: what is corrected, and what is not

### The futures ledger corrects, and the correction is dimensionally correct

`Ledger.verdict` in `quant_brain/research/registry.py`:

    t = stats.tstat_hac(series, horizon=horizon)
    threshold = stats.bonferroni_threshold(n)
    value = float(t.t)
    passed = bool(abs(value) > threshold) and math.isfinite(value)

`value` is a t-statistic and `threshold` is a t-threshold. **An earlier audit claim that this
compared a dollar metric against a t-threshold is wrong.** The dollar mean is carried
separately in `Verdict.metric` (`metric=float(getattr(t, "mean", ...))`) and takes no part in
the pass/fail decision. `n` comes from `Ledger.trials(family)`, read from the ledger at
decision time; there is no `n_trials` parameter, and `tests/test_qb_research.py` asserts none
can be added.

Thresholds from `quant_brain/core/stats.py::bonferroni_threshold`:

| trials | 1 | 5 | 20 | 55 | 136 | 272 | 817 | 1,653 |
|---|---|---|---|---|---|---|---|---|
| bar on \|t\| | 1.96 | 2.58 | 3.02 | 3.32 | 3.56 | 3.74 | 4.01 | 4.17 |

### Three ways a trial escapes the denominator, all measured

1. **`verdict()` does not record.** Fifty calls leave the count at zero and write nothing:

       L = Ledger(tmp/'t.jsonl'); e = Experiment(hypothesis='h', family='fam', params={'a':1})
       for _ in range(50): v = L.verdict(e, series)
       # L.trials('fam') == 0 ; the file does not exist ; every call judged at |t| > 1.96

2. **Renaming the family resets the bar.** `Experiment.fingerprint` hashes
   `{hypothesis, family, params}`, so the same specification under a new family name is a new
   experiment with a fresh count. Verified: the same spec under `fam` and `fam.v2` produces
   fingerprints `add53c1d5c742de6` and `76bd25a2298e8f13`, and `trials()` returns 1 for each.

3. **`--no-record`.** 22 scripts under `scripts/` accept it
   (`grep -rl "no-record" --include=*.py scripts/ | wc -l` gives 22), and `AGENTS.md`
   instructs agents to use it "for exploratory sweeps". Every trial run that way is invisible
   to the correction.

### The equity ledger corrects nothing, and neither does the promotion path

- `scripts/backtest.py` and `scripts/intraday_backtest.py` append a row of LEAN statistics.
  No t, no family, no trial count, no verdict.
- `scripts/evaluate.py` -- the only path that may write `research/champion.json` -- decides on
  `research/champion.json::criteria`: `min_trades: 30`, `must_beat: ["Compounding Annual
  Return"]`, `sharpe_tolerance: 0.03`, `drawdown_tolerance_points: 1.0`,
  `max_drawdown_limit: "35%"`. Grepping `evaluate.py` for
  `t-stat|bonferroni|multiplic|p-value|significan|oos|holdout` returns one hit, and it is
  prose in a comment. There is no significance test, no multiplicity correction, no
  out-of-sample requirement and no holdout in the equity promotion gate.
- Of the 87 `scripts/sweep_*.py` and `scripts/ml_*.py` files, **none** imports
  `quant_brain.core.stats`.

One correction to the blanket statement "the equity side applies no correction": five options
sweeps do apply a Bonferroni bar, but as a hand-typed constant. `scripts/sweep_o5.py:127` sets
`BONFERRONI_T = 3.02  # two-sided alpha 0.05 over 20 Stage-A tests` and
`scripts/sweep_o7.py:161` sets `POOLED_T = 2.576`. Both are arithmetically right for the
counts named (`bonferroni_threshold(20) = 3.0233`, `bonferroni_threshold(5) = 2.5758`), and
both take the count from the author rather than from a ledger. That is precisely the failure
mode `registry.py`'s docstring names: the trial count is "the softest number in quantitative
research because it is supplied by the person who wants the result to be significant."

### The correction suite that nothing calls

`quant_brain/core/multipletest.py` implements Holm, Benjamini-Hochberg, Benjamini-Yekutieli,
White's Reality Check, Hansen's SPA, the deflated Sharpe ratio and PBO. Its only importer in
the repository is `tests/test_qb_multipletest.py`.
`tests/test_production_reachability.py:190` pins it in a `_UNWIRED` list under
`xfail(strict=True)`, so the gap is a tracked defect rather than an oversight. Nothing on the
research path can control a false discovery rate, test the best of a dependent set, or deflate
a Sharpe for search. Bonferroni over a per-family count is the whole of the machinery in use.

---

## 3. A measured duplication problem: the ES and NQ grids were run twice

`futures.es.threshold_grid` and `futures.es.threshold_grid.v2` each hold 136 rows. Comparing
them by hypothesis:

    python -c "
    import json
    rows=[json.loads(l) for l in open('research/experiments_futures.jsonl',encoding='utf-8') if l.strip()]
    byfam={}
    for r in rows:
        if '_retraction' not in r: byfam.setdefault(r['family'],{})[r['hypothesis']]=r
    for base in ['futures.es.threshold_grid','futures.nq.threshold_grid']:
        v1,v2 = byfam[base], byfam[base+'.v2']; c=set(v1)&set(v2)
        print(base, len(c), sum(1 for h in c if v1[h]['params']==v2[h]['params'] and v1[h]['metrics']==v2[h]['metrics']))
    "
    # futures.es.threshold_grid 136 132
    # futures.nq.threshold_grid 136 132

**132 of the 136 cells are identical in params and metrics between v1 and v2, on both ES and
NQ.** The four that differ are exactly the `opening_range_pos` cells, which is what the rerun
was for: the retraction row records that `opening_range_pos` "used the first 30 bars' high and
low at every bar INCLUDING those first 30". `rel_volume > +1.00 dir -1` carries
t = -11.91940142980419 in both ES families and t = -5.1105317874099505 in both NQ families --
bit-identical.

Because `fingerprint()` includes the family name, those 136 shared specifications produce 272
distinct `experiment_id` values, and `Ledger.trials()` reports 136 per family rather than 272
for the tape. **The honest denominator for the ES tape is about 272 specifications evaluated,
not 136.** The bar moves from 3.56 to 3.74 -- small, but the mechanism is not: a `.v2` suffix
halves the apparent search.

The recorded thresholds *within* a family are also order-dependent. `trials` runs from 1 to
136 across each family's rows, so the first cell written was judged at |t| > 1.96 and the last
at |t| > 3.56. Which cell got the easy bar is an artefact of grid iteration order.

### What the funnel actually produced

    python -m quant_brain research ledger --path research/experiments_futures.jsonl
    #   817 experiment(s) across 7 famil(y/ies) [rejected=817]

41 rows carry `verdict.passed == true`. **40 of them have a negative t** -- statistically
significant losing rules, worst at t = -11.92 -- and are staged `rejected`.
`scripts/futures_discover.py` says so in its own gate-0 comment. The single positive survivor
ever produced, `opening_range_pos > +0.50 dir -1` on NQ at t = +6.25, carries the note
"survived every gate; eligible for the holdout" and is the row the retraction withdraws.
Nothing has survived this funnel.

---

## 4. Provenance: what the rows carry

**Futures ledger: 817 of 817 rows have `provenance: null`, and the string `commit` does not
occur anywhere in the file.** The mechanism is `quant_brain/research/search.py:50`,
`Hypothesis.experiment()`, which constructs
`Experiment(hypothesis=..., family=..., params=...)` and passes no `provenance`, so the
dataclass default of `None` stands. No futures result can be tied to code.

**Equity ledger:**

| measure | count | share |
|---|---|---|
| rows | 1,653 | |
| rows with a real commit hash | 255 | 15.4% |
| rows with `commit` set to the literal `"unknown"` | 3 | |
| rows with an empty or null `commit` | 1,395 | 84.4% |
| distinct commits referenced | 47 | |
| rows carrying a `provenance` block | 59 | 3.6% |
| rows with `reproducible: true` | **0** | |

All 59 provenance blocks report `git_dirty: true`, which is why `reproducible` is false on
every one: `Provenance.reproducible` in `quant_brain/core/provenance.py` returns
`bool(self.git_commit) and not self.git_dirty`. All 59 also carry `random_seed: null` and
`dataset_version: ""`. The recorded commits are abbreviated inconsistently, at 7 or 12
characters.

`env_key` across those 59 rows: `py314-5ba485` on 56, `py311-689198` on 3. Two interpreters
with different major pandas versions are appending to one file, which is the condition
`provenance.py`'s docstring was written about.

---

## 5. Window reuse in the equity ledger

    python -c "
    import json
    from collections import Counter
    rows=[json.loads(l) for l in open('research/experiments.jsonl',encoding='utf-8') if l.strip()]
    for k,v in Counter((r.get('start'),r.get('end')) for r in rows).most_common(5): print(v,k)
    "

| window | rows | distinct algorithms | distinct tags |
|---|---|---|---|
| 2012-01-03 .. 2026-09-04 (full) | 345 | 16 | 325 |
| 2020-01-02 .. 2026-09-04 (the "out of sample" half) | 189 | 9 | 182 |
| 2012-01-03 .. 2019-12-31 (the in-sample half) | 166 | 9 | 159 |
| no window recorded | 202 | | |

The 189 scorings of the "OOS" half were written on two calendar days, 2026-09-12 and
2026-09-13.

**What repeated use does to the label.** An out-of-sample window earns that name from being
looked at once, after the specification is fixed. Each further look lets the window influence
the next specification, and after 189 looks the window is a validation set: the selection has
been fitted to it exactly as a training set is fitted, only without the accounting. The
accurate description of the current state is that this repository has one in-sample period of
2012-01-03..2026-09-04 and no out-of-sample period at all. A number from the 2020-2026 window
may be quoted as a fit statistic. It may not be quoted as evidence of generalisation, and the
count 189 has to travel with it.

---

## 6. The write-once holdout that has never been used

`quant_brain/core/validation.py` provides `make_holdout(data, *, fraction, ledger_path,
label)` and a `Holdout` dataclass whose `spend(*, result, note, force=False)` appends each
evaluation to an on-disk ledger keyed by a SHA-256 fingerprint of the data, and raises
`LeakageError` on a second look.

Verified state:

- The only importers of `make_holdout` / `Holdout` are `quant_brain/research/promotion.py`
  and `tests/test_qb_promotion.py`. `promotion.py` is itself in the `_UNWIRED` list of
  `tests/test_production_reachability.py`; the live promotion path is `scripts/evaluate.py`,
  which does not import it.
- `find . -iname "*holdout*"`, excluding `.git/` and the untracked `Quant Brain/` vault,
  returns nothing. **No holdout has ever been carved and `spend()` has never run.**
- `purged_walk_forward` is called only from `tests/test_qb_validation.py` and
  `tests/test_leakage_redteam.py`. No research driver uses purged, embargoed folds. The
  futures funnel's walk-forward is `np.array_split(pnls, 5)` with a count of positive fold
  means (`scripts/futures_discover.py`, the walk-forward gate), which is neither purged nor a
  train/test split.

---

## 7. Statistical power, and why a null result cannot be read without it

A funnel that rejects everything is either rejecting correctly or blind, and the attrition
table cannot tell those apart. Power can.

Measured per-session P&L standard deviation of a **1-lot always-in rule** -- long one contract
09:30 to 15:45 ET, P&L = (last close - first close) x multiplier -- over the funnel's own
session set:

| symbol | sessions | multiplier | sd per session | standard error | edge detectable at 80% power, bar \|t\| > 3.56 |
|---|---|---|---|---|---|
| ES | 313 | 50 | $2,124.4 | $120.08 | $529 / session |
| MES | 252 | 5 | $226.4 | $14.26 | $63 / session |
| NQ | 313 | 20 | $4,578.0 | $258.76 | $1,140 / session |
| MNQ | 252 | 2 | $493.6 | $31.09 | $137 / session |

Power to detect a genuine **$20 per session** edge, at the family's own bar of
`bonferroni_threshold(136) = 3.5623`:

| symbol | power at \|t\| > 3.56 | power at \|t\| > 1.96 |
|---|---|---|
| ES | 0.04% | 5.3% |
| MES | **1.5%** | 28.9% |
| NQ | 0.04% | 5.1% |
| MNQ | **0.2%** | 9.9% |

Re-derive read-only, using the funnel's own loader and session filter:

    import importlib.util, math, numpy as np
    from pathlib import Path
    from statistics import NormalDist
    spec = importlib.util.spec_from_file_location("fd", "scripts/futures_discover.py")
    fd = importlib.util.module_from_spec(spec); spec.loader.exec_module(fd)
    from quant_brain.markets.futures_cme import instruments as inst
    from quant_brain.core.stats import bonferroni_threshold
    thr, N = bonferroni_threshold(136), NormalDist()
    for sym in ("ES", "MES", "NQ", "MNQ"):
        sess = fd.session_frames(fd.load(Path("data/futures")/f"{sym}.parquet", sym))
        m = inst.CONTRACTS[sym].spec.multiplier
        p = np.array([(g["c"].to_numpy(float)[-1]-g["c"].to_numpy(float)[0])*m for g in sess])
        se = p.std(ddof=1)/math.sqrt(len(p)); ncp = 20.0/se
        print(sym, len(p), round(p.std(ddof=1),1),
              round(((1-N.cdf(thr-ncp))+N.cdf(-thr-ncp))*100, 2))

**One caveat that matters.** These figures depend on which sessions count as complete.
`session_frames` was tightened on 2026-09-13 from `len(g) > 200` to a structural completeness
test, which drops early closes. Under the *previous* filter the same computation gives ES
$2,085.9 over 326 sessions, MES $222.7 over 261, NQ $4,492.2 over 326, MNQ $485.5 over 261,
and MES / MNQ power of 1.7% / 0.19%. The ledger's 817 rows were scored under the old filter,
so those are the numbers that describe the recorded results; the table above describes what
the code does today. The conclusion is identical either way.

**How to read this.** On MNQ, the instrument a $50K prop account is actually permitted to
trade, the funnel would miss a real $20-per-session edge 998 times in 1,000. Its 817
rejections are therefore consistent with "there is no edge here" and equally consistent with
"there are edges here and this sample cannot see them". Nothing in the funnel's output
distinguishes those two worlds. Until a minimum detectable effect is published beside the
attrition table, "the funnel rejected it" is not evidence of absence.

---

## 8. The protocol

Numbered so a step can be cited by number in a journal entry. Nothing below is enforced by
code; each step names what would enforce it if it existed.

### A. Before the first number is produced

1. **Write the hypothesis down, in the file that will run it, before running it.** State the
   instrument, the window, the rule, the cost model, the decision rule, and the number that
   would falsify it. The convention is already near-universal here:
   `grep -rliE "pre-regist|preregist" --include=*.py scripts/ quant_brain/ algorithms/` matches
   78 files. `scripts/ml_f10.py:34` is the cleanest example -- "PRE-REGISTERED - written in
   full before any F-10 number was read", with post-run corrections in a separately labelled
   block so the pre-registration "cannot be confused with a rationalisation". There is no
   mechanism that checks a pre-registration exists, that it predates the run, or that it was
   not edited afterwards; it is a docstring convention and the git history is the only
   timestamp.
2. **Name the family, and never rename it.** The family is the unit multiplicity is counted
   over. A `.v2` suffix creates a second family with its own count; section 3 measures what
   that cost. If a rerun is genuinely a rerun, it belongs in the original family, where
   `Ledger.record` will detect it by fingerprint and not double-count it.
3. **Declare the trial budget.** How many specifications will this family contain? Write the
   number down. A family whose size is decided after the results are in has no denominator.
4. **Check whether it has been tried.** `quant_brain/core/knowledge.py` indexes
   `research/experiments.jsonl`, `research/journal*.md` and `research/backlog.md`. It does not
   index `research/experiments_futures.jsonl`; for futures, read
   `python -m quant_brain research ledger` as well.
5. **Compute the minimum detectable effect before running.** Use the per-session standard
   deviation of the instrument and the bar the family will face (section 7). If the MDE
   exceeds any edge worth trading, the experiment cannot answer the question, and running it
   converts a power problem into a false negative you will later quote as evidence.

### B. While the family runs

6. **Record every trial, including every failure.** The rejections are the denominator. On the
   futures path, `search.py` records each hypothesis whether it survives or not; that is what
   makes the count real. On the equity path there is no equivalent, so the record is whatever
   the author chooses to append.
7. **Do not use `--no-record` for anything you will later reason about.** It is legitimate for
   a plumbing check. It is not legitimate for a specification, because the trial happened
   whether or not the file says so.
8. **`verdict()` is not a record.** It reads the count; it does not increment it. Call
   `Ledger.record(exp)` for every specification evaluated, then `Ledger.verdict(...)`.
9. **Do not re-look at a window you have already used to choose a specification.** Count the
   looks and write the count into the journal entry.

### C. The correction

10. **Bonferroni over the family's own trial count is the floor.** It is applied by
    `Ledger.verdict` on the futures path and by nothing on the equity path. It is what exists
    and it is valid under arbitrary dependence.
11. **When the family is many near-duplicate cells, Bonferroni is the wrong instrument** and
    `quant_brain/core/multipletest.py` holds the right ones: `control_fdr`
    (Benjamini-Yekutieli by default, valid under arbitrary dependence), `reality_check`,
    `spa`, `deflated_sharpe_from_returns`, `pbo`. Wiring one of them into a driver is
    unfinished work; until it is done, say "Bonferroni only" out loud when quoting.
12. **State the denominator with the result, always.** "t = 3.7" is not a result. "t = 3.7
    against a 136-trial bar of 3.56, in family `futures.es.threshold_grid`" is. If the same
    tape has been searched under more than one family name, quote the sum.
13. **Correct for label overlap before correcting for multiplicity, and report both.**
    `stats.tstat_hac(x, horizon=h)` refuses a lag below h-1. The two corrections compound.

### D. Leakage

14. **The futures funnel refuses at run time, in two places, and both are real.**
    - `scripts/futures_discover.py::build_features` runs `fe.audit_causality(lib, g)` on the
      first, middle and last session and raises `validation.LeakageError` on any failure.
      `features.assert_causal` sweeps a nine-point candidate list weighted toward the start of
      the session (`[3, 5, 10, 20, 31, warmup+2, 0.25n, 0.5n, 0.8n]`, deduplicated and
      filtered to the frame), bumps every column rather than OHLCV only, uses a seeded per-row
      random draw rather than an order-preserving scale, and compares exactly rather than with
      `np.isclose`. Each of those three changes closed a measured blind spot; the single-probe
      version is how `opening_range_pos` shipped with a lookahead.
    - Gate 0: `MAX_CEILING_SHARE = 0.20` (`scripts/futures_discover.py:86`). Gross P&L is
      divided by the one-bar-ahead oracle's profit, and a hypothesis above 20% is refused
      before any statistic is computed. The level sits in a measured 11x-wide empty band: the
      weakest planted cheat scored 44.90% of the ceiling, the best clean causal rule 3.97%
      (`futures_discover.py:74-76`). The check is on `abs(gross)`, so a sign-flipped oracle is
      caught too -- the funnel has produced 40 passing verdicts with negative t, and the code
      says so at `futures_discover.py:316`. It is **one-sided**: a high share is strong
      evidence of a leak, a low share is evidence of nothing.
15. **The equity and intraday paths have no run-time leakage guard.**
    `algorithms/intraday/CONTRACT.md` and `algorithms/intraday/base.py` state a causality
    convention; nothing executes it. The protection there is `tests/test_leakage_redteam.py`,
    which injects planted cheats into real entry points including `sweep_s19.simulate` and
    `sweep_s25.legs_simulate`. Current state: `python -m pytest -m leakage -q` gives
    **30 passed, 1 xfailed**. The single open defect is
    `test_sweep_s25_must_refuse_a_weights_fn_that_reads_the_future`: `sweep_s25.legs_simulate`
    hands its `weights_fn` a bare timestamp, and a guard that discriminates would have to test
    the weights against the next session's realised return -- the equity analogue of gate 0,
    and unbuilt.
16. **Before quoting an equity result, say which of these applied.** For any row in
    `research/experiments.jsonl` the honest answer today is: neither gate 0 nor a causality
    audit ran; the protection is a commit-time test suite.

### E. Before a result may be quoted

All of these must be answerable, in writing, in the journal entry that quotes it.

17. The row exists in a ledger, and you have named which ledger and which row id or timestamp.
18. The family was named before the run and has not been renamed since.
19. The trial count in that family at the time of the verdict, and the bar it faced.
20. The correction applied, with its denominator, and a statement of which corrections were
    *not* applied.
21. The minimum detectable effect at that bar, so a null can be distinguished from blindness
    (section 7).
22. Which leakage checks executed at run time -- not which exist (section D).
23. The window, and how many prior rows used the same window (section 5). If the window is
    described as out-of-sample, the number of prior looks must be quoted with it.
24. The commit, and whether the tree was clean. 84.4% of equity rows cannot answer this and 0%
    report `reproducible: true`; a row that cannot answer it is a diagnostic, not evidence.
25. Costs, as a share of gross, and the fill convention. The funnel records
    `fill_convention: "decision_bar_close"` and a `fill_subsidy` measuring the difference from
    a next-open fill, because a rule whose entire edge was the fill convention has been
    measured in this tree at 99.8% of gross.
26. The sign. A "significant" result with a negative t is a significant loss; 40 of the
    funnel's 41 passes are of that kind.

A result that cannot answer 17-26 may be described as a diagnostic, an observation, or a
reason to run something else. It may not be described as evidence, and it may not enter a
promotion argument.

### F. Before a strategy may be promoted

27. **What the code enforces today, equity.** `scripts/evaluate.py` against
    `research/champion.json::criteria`: at least 30 orders, beats the champion on Compounding
    Annual Return, Sharpe no more than 0.03 below, drawdown no more than 1 point worse and
    never above 35% absolute, and the comparison must be at the same cost model. No
    significance test, no multiplicity, no out-of-sample requirement, no holdout.
28. **What the code enforces today, futures.** Nothing promotes.
    `quant_brain/research/promotion.py::PromotionGate` exists, is tested, and has no caller.
29. **What `PromotionGate` would require if it were wired**, as a statement of the standard
    this repository has written for itself: every rung requires `ladder`, `statistical`,
    `costs`, `topstep` and `walk_forward`; CHALLENGER and above add `holdout`; CHAMPION adds
    `beats_champion`. Its floors (`Rules`) are `min_folds=4`, `min_fold_win_rate=0.6`,
    `min_topstep_pass_rate=0.35`, `max_cost_share=0.35`, `min_beat_margin=0.0`. It has no
    `force`, no `override` and no `score` shortcut, and a test asserts those names never
    appear in the signature. `refuse_cross_environment` raises when a challenger and a
    champion carry different `env_key` values.
30. **The holdout is a precondition of promotion in that design, and it does not exist.**
    Carving one costs one call to `validation.make_holdout`. Until it is carved, no promotion
    in this repository is out-of-sample in the strict sense, whatever the window says.

---

## 9. What is not built

Named plainly, because each of these is described somewhere in the repository's documentation
as though it were part of the system.

- **No enforced protocol.** Nothing refuses a result for skipping any step above.
- **No pre-registration mechanism.** 78 files carry pre-registration language in their
  docstrings and nothing checks that any of it predates the run it describes.
- **No holdout.** `make_holdout` has never been called, `spend()` has never run, and no
  holdout ledger exists on disk.
- **No purged cross-validation on any research path.** `purged_walk_forward` is called only by
  tests.
- **No FDR, Reality Check, SPA, deflated Sharpe or PBO in use.**
  `quant_brain/core/multipletest.py` has no caller outside its own tests.
- **No multiplicity accounting whatsoever on the 1,653-row equity ledger**, which is where the
  deployed intraday sleeve and the daily champion both live.
- **No provenance on any futures result.** 817 of 817 rows are `provenance: null`.
- **No run-time leakage guard on the equity or intraday path.**
- **No power or MDE published beside any funnel table.**
- **No promotion gate that tests significance.** The one that does exists and is unwired.
- **No single reader that can see both ledgers.**

See `docs/REPRODUCIBILITY.md` for whether a quoted result can be re-run at all.
