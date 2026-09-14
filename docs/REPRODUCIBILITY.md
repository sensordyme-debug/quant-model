# Reproducibility: can a result from this repository be re-run, and by whom

Status of this document: describes the repository at commit `4fbc22e` (2026-09-13), measured
against the working tree rather than the commit. Several agent tracks were editing this tree
concurrently while this was written, so line numbers may drift by a few lines; every citation
also names the symbol. Every number below names the read-only command that produced it or the
file and function that implements the behaviour. Counts exclude `.git/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`,
`results/` and the untracked third-party vault `Quant Brain/` (gitignored,
`.gitignore` line 55, 0 tracked files).

| claim | status | evidence |
|---|---|---|
| A STRANGER CAN REPRODUCE A RESULT | **no** | no dependency manifest exists anywhere at the repo root; `data/` and `results/` are gitignored; 44.3% of equity ledger rows record no commit, no parameters and no output directory |
| THE AUTHOR CAN REPRODUCE A RESULT ON THIS MACHINE | **partly** | 0 of 1,653 equity rows report `reproducible: true`; the 817 futures rows carry no provenance at all |
| RUNS ARE DETERMINISTIC GIVEN THE SAME INPUTS | **probably yes on the research path** | no unseeded randomness found in `scripts/`, `quant_brain/`, `algorithms/`, `live/`; see section 6 for what was searched and what that does not cover |
| THE ENVIRONMENT IS RECORDED | **partly** | `env_key` on 59 of 1,653 equity rows, 0 of 817 futures rows |

---

## 1. Two interpreters, and both write to the same ledger

Measured:

    python -c "import sys, pandas, numpy; print(sys.version.split()[0], pandas.__version__, numpy.__version__)"
    # 3.14.7 3.0.5 2.5.3
    python -c "import pyarrow; print(pyarrow.__version__)"
    # 25.0.1

    py -3.11 -c "import sys, pandas, numpy; print(sys.version.split()[0], pandas.__version__, numpy.__version__)"
    # 3.11.9 2.2.3 2.4.6
    py -3.11 -c "import pyarrow"
    # ModuleNotFoundError: No module named 'pyarrow'

| | harness | LEAN |
|---|---|---|
| interpreter | Python 3.14.7 | Python 3.11.9 |
| pandas | 3.0.5 | 2.2.3 |
| numpy | 2.5.3 | 2.4.6 |
| pyarrow | 25.0.1 | **absent** |
| `env_key` | `py314-5ba485` | `py311-689198` |

3.11 is fixed by LEAN: `scripts/env.ps1` sets `PYTHONNET_PYDLL` to
`%LOCALAPPDATA%\Python\pythoncore-3.11-64\python311.dll`, so anything running inside the LEAN
launcher runs on that interpreter. 3.14 is where the parquet stores live, because 3.11 has no
parquet engine.

**Which code must work on both.** Anything importable from an `algorithms/` module that LEAN
loads, and anything in `quant_brain/` that a LEAN-hosted algorithm or a 3.11-run script
touches. `quant_brain/core/knowledge.py` says so explicitly in its own docstring: it is pure
stdlib "so it imports on both the 3.11 and 3.14 interpreters without touching either
environment."

**How the test suite handles it.** Not with a matrix; with per-test skips. `pytest.importorskip`
appears on 16 lines across 10 test files, 7 of them for `pyarrow`. Two files skip at module
scope and therefore do not collect at all on 3.11:

    python -m pytest --collect-only -q      # 2,227 tests across 74 files
    py -3.11 -m pytest --collect-only -q    # 2,174 tests across 72 files
    # missing on 3.11: tests/test_intraday_data_extend.py, tests/test_store_health.py

So 53 tests never run on the interpreter that runs LEAN, and the two that are whole files are
the ones covering the minute and futures parquet stores.

**Why this matters for a result rather than for tooling.** `quant_brain/core/provenance.py`
records the observation directly: on 2026-09-12, `sweep_s32.py --stage b` on 3.11 and
`sweep_a8.py` on 3.14 were both appending rows to `research/experiments.jsonl`. pandas 3.0
changed copy-on-write, string dtype and resample semantics against 2.2. `env_key` exists to
make that detectable; it is present on 59 of 1,653 rows, so for the other 1,594 the
interpreter that produced them is unrecorded.

---

## 2. There is no dependency manifest of any kind

This is the single largest reproducibility gap in the repository.

    ls -a | grep -iE "requirements|pyproject|setup\.(py|cfg)|Pipfile|poetry|uv\.lock|environment\.y|conda|constraints"
    # (no output)

    find . -maxdepth 3 \( -iname "requirements*.txt" -o -iname "pyproject.toml" -o -iname "Pipfile*" \
        -o -iname "*.lock" -o -iname "setup.py" -o -iname "environment.yml" \) | grep -v "^./.git/"
    # ./Quant Brain/QuantModel/pyproject.toml
    # ./Quant Brain/QuantModel/uv.lock
    # ./Quant Brain/_System/pyproject.toml
    # ./Quant Brain/_System/uv.lock

The four hits belong to `Quant Brain/`, which is a gitignored, untracked import of a third
party's project (`.gitignore` line 55 and the comment block above it). They describe a
different package (`quantbrain`, not `quant_brain`) and are not this repository's manifest.

**There is no `requirements.txt`, no `pyproject.toml`, no lockfile, no `environment.yml` and
no pinned version anywhere in `scripts/env.ps1`.**

What that costs, concretely. An AST scan of all 282 Python files for non-stdlib, non-local
top-level imports finds ten distinct third-party names and nothing declares any of them:

| import | files | note |
|---|---|---|
| `pandas` | 184 | major version differs between the two interpreters |
| `numpy` | 131 | |
| `pytest` | 73 | |
| `sklearn` | 18 | |
| `ib_async` | 17 | the IBKR client |
| `yfinance` | 9 | the daily data fetcher |
| `AlgorithmImports` | 6 | injected by the LEAN engine; not installable from PyPI |
| `fastapi`, `uvicorn`, `starlette` | 4 / 2 / 2 | the local dashboard |
| `scipy` | 1 | |

`pyarrow` does not appear in that list and is nevertheless required: it is used only as
pandas' parquet engine, so an import scan cannot discover it and a manifest is the only place
it could be recorded. It is absent on 3.11, which is why two whole test files do not collect
there.

- The one place versions are captured at all is `Provenance.NUMERIC_STACK` -- five package
  names -- and only on the 59 equity rows that carry a provenance block.
- A stranger cloning this repository cannot construct either environment. They cannot even
  discover that two are required except by reading `AGENTS.md` prose.
- Because 3.11 and 3.14 have different pandas majors, "pip install pandas" produces the wrong
  answer for at least one of them, and nothing in the tree says which.

The cheapest fix in the repository is two files. See section 8.

---

## 3. Nothing is signed

    git log -50 --pretty="%G?" | sort | uniq -c
    # 50 N

`%G?` returns `N` for "no signature" on all 50 of the most recent commits. There is no
cryptographic link between a commit hash quoted in a ledger row and the person who wrote it.
On a repository where six agent tracks and a human share one working tree, and where
`.gitignore`'s own comment block records two accidental `git add -A` sweeps of 3,200 files
each, that is worth stating rather than assuming.

---

## 4. The manifests carry no content hash, and the data is not in git

`research/data_manifest.json` records `generated_at`, `source`, `start`, `end`,
`symbols_written`, `symbols_missing`, `symbols_failed`, `symbols_on_disk`,
`clamped_bars_total`, `symbols_factor_check`, and a per-symbol `data` block of
`{bars, first, last, clamped_bars, factor_rows, adj_close_dev}`.
`research/minute_manifest.json` has the same shape.

    grep -oiE '"[a-z_]*(hash|sha|digest|md5|checksum)[a-z_]*"' research/*.json | sort | uniq -c
    # 1 research/champion.json:"sharpe_tolerance"

**No manifest carries a content hash of any data file.** Bar counts and first/last dates are
the whole of the integrity record, and they cannot distinguish two files with the same shape
and different values -- an adjusted-vs-unadjusted refetch, a vendor restatement, a partially
rewritten parquet.

Hashing does exist elsewhere in the tree, which shows the omission is not a missing
capability: `provenance.config_hash` (SHA-256 of a config), `Experiment.fingerprint`
(SHA-256 of hypothesis+family+params), `validation.make_holdout` (SHA-256 of the data itself),
and code hashes in `scripts/sweep_f1.py:218` and `scripts/ml_f20.py:551`. Data files are the
one category not covered.

Compounding this:

    git ls-files data/ | wc -l      # 0
    git ls-files results/ | wc -l   # 0

`data/` and `results/` are both gitignored (`.gitignore`). Every parquet store the futures
funnel reads -- `data/futures/{ES,MES,NQ,MNQ}.parquet`, 25 MB -- exists only on this machine,
with no hash recorded anywhere and no way to tell whether a re-fetch produced the same bytes.

And the ledger rows mostly do not point at their outputs:

| equity ledger row property | count | share of 1,653 |
|---|---|---|
| non-empty `run_dir` | 179 | 10.8% |
| non-empty `params` | 744 | 45.0% |
| no `params`, no `run_dir`, no `commit` | **733** | **44.3%** |

All 179 `run_dir` paths still exist on disk, and all 179 point into gitignored `results/`.
The 733 rows with none of the three carry only `algorithm`, `class`, a free-text `tag`, a
timestamp, and the statistics. Nothing in them says what was run.

---

## 5. Provenance capture: what exists and what calls it

`quant_brain/core/provenance.py` defines `Provenance`, a frozen dataclass whose `capture()`
gathers, without ever raising:

| captured automatically | supplied by the caller |
|---|---|
| `git_commit` (full SHA), `git_dirty`, `git_branch` | `dataset_version`, `data_timestamp` |
| `python_version`, `python_executable`, `platform` | `feature_version`, `model_version`, `strategy_version` |
| `dependencies` for `pandas, numpy, scipy, scikit-learn, pyarrow` | `configuration_hash`, `random_seed`, `notes` |
| `ts`, `experiment_id` | |

Derived: `env_key` (interpreter major.minor plus a 6-hex digest of the numeric stack) and
`reproducible` (`bool(git_commit) and not git_dirty`). It also offers
`require_interpreter(major, minor, *, why="")`, which raises on the wrong interpreter.

**Who calls it:** `scripts/backtest.py:145` and `scripts/intraday_backtest.py:632`, both inside
a `try/except Exception` that records a `provenance_error` string rather than failing the run.
`quant_brain/research/promotion.py` consumes a `Provenance` but has no caller.
`require_interpreter` has no caller at all.

**Who does not:** the futures funnel. `quant_brain/research/search.py:50`,
`Hypothesis.experiment()`, builds `Experiment(hypothesis=..., family=..., params=...)` with no
`provenance` argument, so the field defaults to `None`. All 817 rows of
`research/experiments_futures.jsonl` are `provenance: null`, and the string `commit` does not
appear anywhere in the file.

**What the 59 captured blocks show.** All 59 report `git_dirty: true`, so all 59 report
`reproducible: false`; all 59 carry `random_seed: null` and `dataset_version: ""`. That is not
a bug in the capture -- it is an accurate report that no equity result was produced from a
clean tree.

**What a ledger row would need to carry to be re-runnable.** The minimum set, none of which is
currently guaranteed:

1. the full commit SHA and a clean-tree flag (present on 59 rows, clean on 0);
2. the `env_key`, and behind it a resolvable dependency set (no manifest exists, section 2);
3. the exact parameters (`params`, present on 744 rows);
4. the data identity -- a content hash of each input file, not a bar count (does not exist,
   section 4);
5. the seed (`random_seed`, `null` on all 59);
6. the window (`start`/`end`, absent on 202 rows);
7. the command line or entry point (nowhere recorded; `run_dir` on 179 rows is the closest
   proxy and points into gitignored output).

---

## 6. Determinism: what is seeded and what was searched

**Seeded, on the research path:**

- `quant_brain/markets/futures_cme/paths.py::moving_block(days, *, block, reps=1000, seed=0,
  length=None)` builds `np.random.default_rng(seed)`. The funnel calls it as
  `pa.moving_block(days, block=10, reps=150, seed=0)` in `scripts/futures_discover.py`'s
  Topstep gate, so the survival estimate is reproducible run to run. `stationary_bootstrap`
  takes the same `seed=0` default.
- `quant_brain/markets/futures_cme/features.py::assert_causal(feature, df, *, at=None, seed=0)`
  and `_assert_causal_at(..., seed=0)`. The docstring states why the argument exists: the
  perturbation is now a per-row random draw rather than an order-preserving scale, and "a
  guard whose verdict changes between runs is not a guard: a leak that fails on one run and
  passes on the next gets re-run until it passes."
- Every model fit found in `scripts/ml_*.py` and `scripts/sweep_f*.py` passes
  `random_state=0` or `random_state=seed` with `seed: int = 0`, and every permutation
  importance call passes `n_jobs=1`.
- Every bootstrap and permutation null found in `scripts/sweep_a1[4578].py` constructs
  `np.random.default_rng(RNG_SEED)` or `default_rng(seed)`.

**Searched for unseeded randomness, and found none:**

    grep -rn "default_rng()" --include=*.py scripts/ quant_brain/ algorithms/ live/
    grep -rnE "np\.random\.(rand|randn|randint|choice|shuffle|permutation|normal|uniform|seed)\b" \
        --include=*.py scripts/ quant_brain/ algorithms/ live/
    grep -rnP "^\s*import random\b|^\s*from random import|(?<![a-z_.])random\.(random|randint|choice|shuffle|uniform|sample)\(" \
        --include=*.py scripts/ quant_brain/ algorithms/ live/
    # all three: no output

    grep -rnE "random_state\s*=\s*[^0-9]" --include=*.py scripts/ quant_brain/ algorithms/
    # scripts/sweep_f1.py:386 and scripts/sweep_f3.py:271, both random_state=seed, seed default 0

There is no `default_rng()` without a seed, no use of the legacy global numpy RNG, and no use
of the stdlib `random` module anywhere on the research path.

**What that does not cover, and should not be claimed:**

- LEAN itself. `scripts/backtest.py` shells out to the .NET launcher; nothing in this
  repository controls or records determinism inside the engine.
- Float reduction order under different BLAS builds or thread counts. `n_jobs=1` is set for
  permutation importance only; numpy's own threading is not pinned, and no
  `OMP_NUM_THREADS` is set anywhere.
- pandas version differences between 3.0.5 and 2.2.3 (section 1). Seeding makes a run
  repeatable on one interpreter; it says nothing about agreement across the two.
- Anything reading wall-clock time or live free memory. `quant_brain/core/scheduler.py`'s
  `resolve_workers` reads free memory and is called out in `tests/conftest.py` as
  machine-dependent.

---

## 7. 143 files mutate `sys.path`, and `scripts/` imports itself 302 ways

Measured with an AST scan over the 282 Python files in the repository (excluding the
directories named at the top of this document). The scan counted a file as a `sys.path`
mutator if it contains a call to `sys.path.insert/append/extend` or an assignment to
`sys.path` or a slice of it.

| | count |
|---|---|
| Python files considered | 282 |
| files that mutate `sys.path` | **143** (50.7%) |
| -- of those, in `scripts/` | 119 |
| -- in `tests/` | 15 |
| -- in `algorithms/` | 8 |
| -- in `quant_brain/` | 1 (`core/dataquality.py:305`) |
| modules in `scripts/` | 132 |
| distinct script-to-script import edges | **302** |
| script-to-script import statements | 322 |

Most-imported script modules: `intraday_common` (52 importers), `lean_prices` (35),
`sweep_s19` (25), `intraday_backtest` (22), `rates` (19), `sweep_s25` (17), `sweep_f1` (13).

A representative example, `scripts/sweep_s19.py:56-57`:

    sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
    sys.path.insert(0, str(REPO / "scripts"))

**What this does to reproducibility.** `scripts/` is not a package. Each script makes itself
importable by editing the interpreter's search path at import time, and 302 of those imports
cross from one script to another. Four consequences, all of them things a stranger would hit:

1. **Import success depends on the working directory and on which script was entered first.**
   `tests/conftest.py` documents the failure this already caused: `paper_trade.py` was unable
   to import for 83 minutes while 1,221 tests stayed green, because every test imported it
   through the path help `conftest.py` gives and the Task Scheduler gives none. The fixture
   `run_as_scheduler` exists solely to run a script the way the scheduler does, stripping
   `PYTHONPATH`, `PYTHONHOME` and `PYTHONSTARTUP` so the path help cannot leak in.
2. **A sweep is not a self-contained artefact.** Re-running `sweep_s19` means re-creating
   whatever `sweep_s19` imported at the time, which includes other sweeps that are themselves
   under active edit by concurrent tracks.
3. **`sys.path.insert(0, ...)` shadows.** A module in `scripts/` takes precedence over an
   installed package of the same name for the rest of the process. `AGENTS.md` records the
   instance that bit: "Never name a module `secrets` (it shadows the stdlib module numpy
   imports from)."
4. **The dependency graph is invisible to packaging tools.** Because there is no manifest and
   no package, nothing can compute the closure of files a given result depends on.

---

## 8. To make a result from this repository reproducible by a stranger

Ordered cheapest first. Each item states what it would fix.

1. **Write two dependency manifests: `requirements-3.14.txt` and `requirements-3.11.txt`,
   generated by `pip freeze` on each interpreter and committed.** Cost: two commands. Fixes
   the largest single gap (section 2). Without this nothing below matters, because no other
   record can be acted on.
2. **Record the full commit SHA, uniformly, in every ledger row.** The equity path already has
   `provenance.capture()`; the futures path needs `Hypothesis.experiment()` in
   `quant_brain/research/search.py:50` to accept and pass a `Provenance`. Cost: one argument.
   Fixes 817 null-provenance rows and 1,395 commit-less rows. Standardise the abbreviation
   while doing it -- the ledger currently mixes 7- and 12-character hashes.
3. **Refuse to record a result from a dirty tree, or stamp it `DIAGNOSTIC`.** `reproducible`
   is already computed and is `false` on all 59 rows that carry it. Making the flag consequential
   is a conditional, not a feature.
4. **Hash the data.** Add a SHA-256 of each input file to `research/data_manifest.json`,
   `research/minute_manifest.json` and to every ledger row's provenance as
   `dataset_version`. `validation.make_holdout` already hashes a numpy array; the same three
   lines apply to a parquet file. Fixes section 4.
5. **Record the command line.** One string per ledger row -- `sys.argv` -- makes 733 otherwise
   unreproducible rows re-runnable in principle. Currently nothing records how a run was
   invoked.
6. **Record the seed.** `Provenance.random_seed` exists and is `null` on all 59 rows. Pass it
   from the caller that owns the RNG.
7. **Turn `scripts/` into a package, or add one `conftest`-equivalent bootstrap that every
   entry point imports.** Removes 119 ad-hoc `sys.path` edits and makes the 302 script-to-script
   edges resolvable without a working-directory assumption (section 7). This is the largest
   piece of work on the list and the one that most reduces the chance of a silent divergence.
8. **Call `provenance.require_interpreter` at the top of every entry point that only works on
   one interpreter.** It exists and has no caller. Cheap; converts a mid-run `ImportError`
   into a first-line refusal.
9. **Run the test suite on both interpreters in a check, not by hand.** 53 tests and two whole
   files currently never run on 3.11 (section 1), and nothing reports that as a gap.
10. **Sign commits.** 0 of the last 50 are signed (section 3). Lowest value of the ten for
    re-running a number, and the only one that addresses who produced it.

---

## 9. What is not built

- **No dependency manifest, of any kind, anywhere at the repo root.**
- **No lockfile and no pinned versions.** `scripts/env.ps1` pins paths, not versions.
- **No content hash on any data file**, and `data/` is not in version control.
- **No command line recorded on any ledger row.**
- **No provenance on any futures result**; 817 of 817 rows are `provenance: null`.
- **No clean-tree result anywhere in the equity ledger**; 0 of 1,653 rows report
  `reproducible: true`.
- **No enforcement of the interpreter split.** `require_interpreter` exists and has no caller.
- **No cross-interpreter test run.** 53 tests never execute on the interpreter LEAN uses.
- **No signed commits.**
- **`scripts/` is not a package**, and 143 files edit `sys.path` to work around that.

See `docs/RESEARCH_PROTOCOL.md` for whether a result may be quoted in the first place.
