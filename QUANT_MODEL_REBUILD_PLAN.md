# Quant Model rebuild plan

Written 2026-09-14 at `28fa331`. Companion to `SYSTEM_READINESS.md`, which says where things
stand; this says what to do next and how to know when each thing is done.

The goal this plan serves is not "build a profitable strategy". It is: **build a research
machine that can reliably distinguish a genuine trading edge from leakage, overfitting, bad
data, unrealistic execution, statistical noise, and prop-firm simulation artifacts.** Every
item below is judged against that and nothing else.

---

## The organising idea

The work splits cleanly into three kinds, and confusing them is what produced the state the
audit found.

**Detection** is machinery that can tell a false result from a true one. Most of it now
exists: a leakage gate, a causality audit, a data validator that fails on the hazards it used
to miss, a prop-firm model that matches the published rules, and 2,238 tests including
thirteen planted cheats and their clean controls.

**Production** is a result the machine has actually produced. There is none. The ledger holds
817 rows, all of them made by code since found wrong in four ways.

**Correction** is fixing what detection has revealed. Nine defects remain pinned, and three
more were found while writing the documentation.

The mistake to avoid is building more detection before producing anything. Detection has
reached the point of diminishing returns for now; the next real information comes from
running the machine.

---

## Phase 1 — Produce one result the current code made

Nothing on the rest of this list can be evaluated until this is done. It is one command and
an afternoon of reading the output.

### 1.1 Rerun the futures funnel into a new family

Run `scripts/futures_discover.py` for each of ES and NQ under a family name that does not
already exist, for example `futures.es.threshold_grid.v3`.

Use a new family deliberately. The 817 existing trials stay in the multiplicity denominator,
because they were attempted and a search does not get cheaper by being redone, but their
metrics stop being quoted. Do not delete or edit `research/experiments_futures.jsonl`.

**What to expect, so a surprise is informative.** Most of the grid should now be reported as
degenerate rather than statistically rejected: 104 of 136 cells are constants on the ES store.
If the attrition table does not show that, something is wrong with the run, not with the
market.

**Done when** the funnel table separates degenerate, leakage, statistical, cost, Topstep and
walk-forward rejections, and every new row carries `ceiling_share`, `fill_convention` and a
non-null provenance.

### 1.2 Read the attrition, not the survivors

A run that promotes nothing is not worse than a run that promotes something. A run where the
gates do not discriminate is the only bad outcome.

**Done when** there is a written comparison of the v3 attrition against the recorded v1/v2
attrition, naming which differences are explained by which of the four fixes.

---

## Phase 2 — Correct what is known to be wrong

These are not improvements. They are places where the system currently produces a number that
is wrong by an amount that has been measured.

### 2.1 The NQ spread — DONE 2026-09-14

The cost model assumes ES's one-tick spread for every contract. Measured on BID_ASK pages
already sitting unassembled in `data/futures/.raw/`: NQ's RTH median is 2.00 ticks with only
4.75% of minutes at one tick, so the modelled round turn of $8.78 should be $13.78. A 36%
undercharge on the contract with the largest point value in the universe.

Assemble the pages, measure the per-contract spread the same way ES's was measured, and
replace the assumption with a table. MES's median is 1.00 tick, so that assumption survives
measurement; MNQ has no quote data and must stay explicitly an assumption rather than quietly
inheriting ES's.

**Done when** `CostModel.for_contract` reads a measured spread per contract, a test pins each
measured value to the store it came from, and MNQ's remaining assumption is named in the code
and in `docs/DATA.md`. All three are done. What remains is the sample: NQ's two ticks rest on
one BID_ASK page, 8,106 RTH observations over 27 days of a single contract month. Fetching
more NQ pages is the cheapest improvement available anywhere on this list.

### 2.2 The contracts-allowed unit mismatch

`TopstepAccount.contracts_allowed` returns micro-equivalents. `core/sizing.py::PropFirmSizer`
treats the same number as raw contracts. Both are on the sizing path.

Now pinned rather than only described:
`test_the_contract_ceiling_is_enforced_in_the_unit_the_caller_is_trading` is a strict xfail
carrying the measured numbers, and a passing control asserts the micro case is correct, so
the pin cannot be read as "sizing is broken". The fix needs the equivalence to reach `core`,
which may not import `markets`: a `max_contracts_for(symbol)` on the `MllAccount` protocol,
implemented where the table lives.

**Done when** one unit is used end to end, the conversion happens in exactly one place, the
strict xfail's marker is deleted because it passes, and the micro control still passes.

### 2.3 The four validator holes found while documenting

NaN bars, NaN volume, negative volume, and an open outside its own low-high range all pass
the futures validator silently. They were named in `docs/DATA.md` rather than fixed, so that
the fix lands with the next validator change rather than buried in a documentation commit.

**Done when** each is a FAIL with a golden-dataset test, and all four real stores still pass.

---

## Phase 3 — Make the funnel able to test something

Phase 1 will show that three quarters of the grid is not a hypothesis. That is a research
design problem, not a bug, and it should be fixed deliberately rather than folded into a
correction.

### 3.1 Quantile thresholds

`threshold_hypotheses` uses absolute thresholds of -1.0, -0.5, +0.5 and +1.0 against a feature
library scaled in returns, so most comparisons never flip and the cell collapses to
buy-and-hold with a sign. Express thresholds in the feature's own distribution — quantiles or
in-sample z-scores computed causally — so that every cell is a rule.

This changes the hypothesis family. It does not invalidate the multiplicity accounting, but it
does mean v3 and v4 are different searches and must not be pooled.

**Done when** no cell in a fresh grid is reported degenerate on the ES store, and a test
asserts that the grid produces as many distinct position paths as it has cells, up to
deliberate duplicates.

### 3.2 The signal shape

`np.where(x >= thr, 1, -1) * direction` is always in the market. That is a strong and probably
unintended commitment: it makes every rule a continuously held position, forces the round-turn count
to depend entirely on threshold crossings, and rules out the whole class of "in only when the
condition holds" strategies. Consider a third state.

**Done when** the family's position states are a documented choice with a stated reason,
rather than an artefact of one `np.where`.

---

## Phase 4 — Connect the validation apparatus

Seven of the nine open pinned defects are the same fact: 16 modules, 7,581 lines, 40.0% of
`quant_brain`, have no non-test caller, and they are the modules that decide whether a result
is real.

Order matters here. Wiring a component that nothing needs produces a caller and no value.

### 4.1 Carve a holdout and never touch it

`make_holdout` and the write-once `Holdout` exist. No holdout has ever been carved and
`spend()` has never been called. Until one exists, nothing in this repository can claim an
out-of-sample result, and every "OOS" figure in the equity ledger is a window that has been
used 189 times.

**Done when** a holdout exists on disk, is excluded from every research path by construction
rather than by discipline, and `Holdout.spend()` is the only way to read it.

### 4.2 Reconcile the two ledger schemas

`Ledger.all()` parses 0 of the 1,653 rows in `research/experiments.jsonl`. The two files share
no keys. This blocks multiplicity on the equity track entirely, and it is a live hazard: if
the Bonferroni denominator were wired to the equity track tomorrow it would silently return
0 trials and apply the n=1 bar of 1.96 to a search of several thousand cells.

**Done when** one reader parses both files, the pinned test
`test_the_multiplicity_ledger_can_read_the_main_experiment_log` passes and its marker is
deleted.

### 4.3 Wire multiplicity to the equity track

Only after 4.2. `multipletest.py` implements Holm, BH, BY, White's Reality Check, Hansen's
SPA, the deflated Sharpe ratio and PBO, and has no caller. Five options sweeps currently apply
a hand-typed Bonferroni constant — arithmetically right for the counts named, but sized by an
author rather than by a ledger.

**Done when** the equity promotion path reads a correction from the ledger's own trial count.

### 4.4 The promotion gate

`research/promotion.py::PromotionGate` has no caller. The real promotion path is
`scripts/evaluate.py`, whose criteria are return-first with no significance test, no
multiplicity and no out-of-sample requirement.

**Done when** promotion requires, at minimum: a significance test corrected for the family's
trial count, a holdout that has not been spent, and a cost column that matches between the
candidate and the incumbent.

### 4.5 Protection and reconciliation

`core/protection.py` and `core/reconcile.py` have no caller. Neither matters while
transmission is frozen, and both matter the moment it is not. They belong immediately before
any decision to unfreeze, not before.

---

## Phase 5 — Reproducibility

### 5.1 A dependency manifest

There is none of any kind at the repo root. The real dependency set is ten third-party names
plus pyarrow, which no import scan finds because it is only pandas' parquet engine. This is
the largest reproducibility gap and the cheapest to close.

**Done when** a manifest exists, pins versions for both interpreters, and a test asserts the
installed versions match it.

### 5.2 Content hashes on the manifests

`data_manifest`, `minute_manifest` and `futures_capability` carry no content hash, and `data/`
is gitignored, so 25 MB of futures parquet exists only on this machine and nothing can detect
if it changes.

### 5.3 Provenance on every ledger row

All 817 futures rows carry `provenance: null`. Of 1,653 equity rows, 255 carry a real commit
and 0 have `reproducible: true`. 733 have no params, no run directory and no commit, and are
irreproducible by construction.

**Done when** a row cannot be written without a commit, a dataset identifier and a seed.

---

## Phase 6 — The vault hazard

`accidental-vault-commit-592e11a`, `accidental-vault-commit-bb4bbf8` and the tag
`incident/2026-09-13-vault-commit` still contain the whole Obsidian vault. They were created
deliberately as recovery points before two accidental commits were reverted, and nothing was
deleted from disk. But `git push --all` or `git push --tags` would publish the vault.

This is the owner's decision and is deliberately not scheduled here. The safe options, in
increasing order of finality: push only `main` explicitly and never use `--all`/`--tags`;
export the refs to a bundle outside the repository and then delete them; or delete them
outright once the vault is confirmed intact on disk.

The vault is user data. It must never be bulk-deleted, never "cleaned" by removing conflicting
evidence, never reorganised, and never committed. It is now gitignored, and
`git add -A --dry-run` matches zero vault paths.

---

## What this plan deliberately does not do

**It does not schedule enabling live trading.** Both runners are frozen and
`tests/test_no_order_can_be_transmitted.py` is in the 09:25 gating set. Unfreezing is a
separate decision with its own preconditions, of which Phase 4.5 is the first.

**It does not schedule deleting or rewriting any data.** The 817 ledger rows stay. The vault
stays. `results/` stays.

**It does not add more detection machinery.** Thirteen planted cheats, twelve of them refused,
142 golden-dataset tests, 49 prop-firm acceptance tests and 28 accounting invariants are
enough to be going on with. The binding constraint is no longer detection.

**It does not promise a result.** Phase 1 may well produce another run in which nothing
survives. On MES the measured power to detect a genuine $20-per-session edge at the family's
own Bonferroni bar is 1.7%, and on MNQ 0.2%. A funnel that rejects everything may be rejecting
correctly or may be blind, and only power tells the two apart. That number should be computed
and reported beside every attrition table from now on.
