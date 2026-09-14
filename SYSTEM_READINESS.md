# System readiness

As of 2026-09-14, at `e5364fb` plus the changes committed with it. Every number here was measured on this tree by the command
named beside it. Nothing is carried over from `AUDIT_REPORT.md` or
`QUANT_MODEL_SYSTEM_AUDIT.md` without re-deriving it; three of their figures did not survive
that and are corrected below.

---

## The verdict

**The research machine can now detect the failure modes it is supposed to detect. It has not
yet produced a result that can be believed, and no number currently in either ledger is one.**

Those are two separate claims and both matter. The first is new and is what changed: thirteen
planted cheats were run through the real entry points and twelve are now refused, three data
hazards that used to pass the only gate on the futures path now fail it, and ten places where
the prop-firm model disagreed with Topstep's published rules now agree with them. The second
is unchanged and is not a criticism of the work — it is the honest consequence of it. Every
row in `research/experiments_futures.jsonl` was produced by code that has since been found
wrong in four independent ways, and rerunning it is a decision that has not been taken.

The system also cannot place an order, deliberately, and as of today that is true for the
first time: the freeze existed only in an uncommitted working tree, and one of the two runners
could still transmit through a path nobody had guarded.

---

## Two readiness scores

### Futures backtest readiness: 55 / 100

Up from 26. What earns it:

| | state |
|---|---|
| Contract mechanics | 12 of 12 roots match published CME values; 14 of 14 P&L cases match hand arithmetic |
| Data integrity | 0 duplicates, 0 out-of-order, 0 bad OHLC, 0 interior holes across 1,612,886 rows |
| Session model | every session used is exactly 376 bars, tested for completeness rather than length |
| Round-turn accounting | the flatten at the bell is counted; net, gross and cost reconcile exactly on every path |
| Leakage detection | 12 of 13 planted cheats refused by production code, with a clean control proving it discriminates |
| Cost realism | commissions are the published Topstep rates; the fill convention is named and its alternative priced |

What holds it back, in order of how much:

1. **No result has been produced by this code.** The ledger is entirely pre-fix. Until the
   funnel is rerun, the backtest machinery is verified and unused.
2. ~~NQ's spread is undercharged by 36%~~ **FIXED.** The quote pages were already on disk
   and had never been assembled. Measured RTH: ES 1.00 tick over 152,736 observations, MES
   1.00 over 120,463, NQ **2.00** over 8,106 with only a 4.8% one-tick share. NQ's round turn
   moves $8.78 to $13.78. `CostModel.for_contract` now reads a measured table and
   `spread_measured` records which contracts are measurements and which are the one-tick
   fallback. MNQ has no quote page and is explicitly the fallback. NQ's figure rests on one
   page and 27 days, which is enough to reject one tick and not enough to be sure of exactly
   two.
3. **The roll is a raw stitch with no marker.** Gaps of +57.75 to +276.50 points sit in the
   series. Nothing differences across a session boundary today, so it is contained, but the
   containment is a property of the current code rather than of the data.
4. **No write-once holdout has ever been carved**, and `purged_walk_forward` still has no
   caller.
5. **The equity ledger and the multiplicity ledger cannot read each other.** `Ledger.all()`
   parses 0 of the 1,653 equity rows.

### Prop-firm research readiness: 45 / 100

Up from 20. The Topstep model is now the most defensible subsystem in the repository: every
parameter carries the help-page it came from and a confidence tier, both readings of the
ambiguous consistency rule are modelled rather than resolved by preference, and the ten
disagreements with the published rules are gone. Forty-nine acceptance tests hold it there.

What holds it back:

1. **`contracts_allowed` returns micro-equivalents and `PropFirmSizer` treats them as raw
   contracts.** A live unit mismatch on the sizing path.
2. **The twin has never been run on a strategy that survived the funnel**, because none has.
3. **Express Funded's scaling ladder was never published**, so the model uses a documented
   fallback of one rung and says so rather than guessing the real one.
4. **Commissions for the eight non-equity-index roots are still indicative $4.00/$1.00.** No
   Topstep rate for them was verified, and swapping one unverified number for another buys
   nothing.

---

## What may and may not be believed

**May be believed today**

- The contract arithmetic, the P&L identities, and the agreement of three independently
  written book implementations to 4.3e-12 on a $1M book.
- The four data stores' cleanliness, because it is now asserted by a validator that fails on
  duplicates, impossible bars and interior gaps, and all four stores pass it.
- The Topstep rule model, within the confidence tiers it declares.
- That the system cannot send an order.

**May not be believed**

- Any metric in `research/experiments_futures.jsonl`. All 817 rows predate four fixes.
  `ceiling_share`, `fill_convention` and `leakage_ok` appear on none of them; 624 carry a
  `trades: 0` that was an arithmetic error; every cost in the file used the wrong commission.
- `research/champion.json`'s headline. The displayed 24.403% CAR is the zero-cost column. The
  promotion decision was made on the 2.0 bp column, which is better than the audit claimed,
  but the repo's own all-in figure with spread, financing and clock-lag charged together is
  18.785%. The promotion criteria are return-first with no significance test, no multiplicity
  and no out-of-sample requirement.
- The equity ledger's out-of-sample claims. 189 rows share one "OOS" window; 733 rows (44.3%)
  have no params, no run directory and no commit.
- Any result from `sweep_s25` produced through its `weights_fn` hook, which remains
  unguarded.

**Three corrections to the earlier audits**, because an audit that is wrong in the repo's
favour still has to be corrected:

- `Ledger.verdict` compares a t-statistic to a t-threshold. It is dimensionally correct. The
  claim that it compared dollars to a t was wrong.
- There are zero mixed-contract days inside the RTH window in any store, so the one-contract
  filter in `load` drops nothing today.
- `ES_quotes.parquet` has 0 crossed rows and 30 locked ones, all consecutive and outside RTH.

---

## The ten open pinned defects

Each is a `pytest.mark.xfail(strict=True)`. The day one is fixed its test starts passing,
strict turns that into a failure, and whoever fixed it must delete the marker. That is the
only mechanism here that makes a to-do list get shorter.

| what | where |
|---|---|
| `sweep_s25`'s `weights_fn` executes an unchecked weight path | `test_leakage_redteam.py` |
| `multipletest` — Holm, BH, BY, Reality Check, SPA, DSR, PBO — has no caller | `test_production_reachability.py` |
| `research.promotion`'s `PromotionGate` has no caller | same |
| `core.protection` bracket verification has no caller | same |
| `core.reconcile` compare-and-halt has no caller | same |
| `core.portfolio` has no caller | same |
| `research.analytics` has no caller | same |
| `research.robustness` has no caller | same |
| `Ledger` cannot read the equity experiment log | same |
| the contract ceiling is enforced in the wrong unit | `test_propfirm_acceptance.py` |

Seven of the ten are the same fact: the validation apparatus is still largely disconnected.
16 of 53 modules, 7,581 lines, 40.0% of `quant_brain`, are unreachable from any non-test
importer. That is down from 17 modules and 44.3%, and the single module that moved —
`core.validation`, now raising `LeakageError` from the funnel's feature builder — moved
because of one narrow use. Reachability is not use.

The tenth is new and was measured rather than inferred. `TopstepAccount.contracts_allowed`
returns micro-equivalents - 50 on a $50K Combine, which is fifty micros or five minis - and
both consumers treat it as raw contracts. On a fresh Combine the sizer proposes 10 ES at a
one-point stop, 20 at half a point and 40 at one tick, against a published ceiling of five,
with the binding reported as the strategy signal every time because the prop-firm cap never
binds. It has not produced a wrong number anyone noticed because the futures funnel sizes in
micros, where the two units coincide; a passing control test asserts exactly that, so the pin
cannot be read as "sizing is broken".

On `sweep_s25` specifically, since a negative result is worth recording: a guard requiring the
hook to accept the causal window was implemented and measured, and it refused the causal
control as well as the cheat, because a legacy one-argument hook is refused whether or not it
cheats. It was reverted rather than shipped. A guard that discriminates has to test the
weights themselves against the next session's realised return.

---

## What changed, measured

Six commits, `0bababd` through `28fa331`.

| | before | after |
|---|---|---|
| tests collected | 1,797 | 2,250 |
| passing | 1,790 | 2,231 |
| open pinned defects | 36 | 10 |
| planted cheats refused by production code | 0 of 13 | 12 of 13 |
| `quant_brain` unreachable from any non-test importer | 17 modules, 44.3% | 16 modules, 40.0% |
| runners that can transmit an order | 1 of 2 | 0 of 2 |
| transmission freeze present in a commit | no | yes |

"before" is the first full suite measured this session, after the state-mutation fix landed
and before the new suites did. The 36 pinned defects are counted at the point where all four
new test suites had landed and none of their fixes had: that is the honest denominator,
because a defect nobody had written a test for was not yet a countable defect.

The four defects that mattered most, each reproduced before it was fixed:

**The test suite was rewriting production state.** `quant_brain.core.state.root_for()` resolves
its root from a module constant the fixture never redirected, so any test building a Trader in
live mode published to the real `live/state/governor.json` — the file the 09:25 pre-trade gate
reads. The teardown guard that should have caught it asserted the absence of a filename nothing
in the tree ever creates. Every full-suite run in this document is now bracketed by a hash of
`live/state` and `live/log`, and all of them came back byte-identical.

**The funnel charged three quarters of its hypotheses nothing to trade.** The round-turn count
omitted the flatten at the bell, so a rule holding a position into the close reported zero
trades and zero cost, and was then discarded by a 40-trade floor as "not a strategy". 624 of
816 scored rows. The same 76.5% turns out to be the fraction of the grid that is degenerate:
104 of 136 cells are constants, because the thresholds are absolute numbers and the features
are scaled in returns, so 52 cells are plain always-long and 52 always-short. Those are the
same rows. The funnel now counts them under their own name.

**A one-bar oracle scored 100.0000% of the arithmetic ceiling and cleared every gate.** There
was no leakage check anywhere in the pipeline. There now is one, ahead of the statistical gate,
because a t-statistic on a look-ahead P&L is not weak evidence but no evidence.

**`paper_trade.py --flatten` transmitted orders.** The branch fires on the flag or on the mere
existence of `live/HALT`, builds a real broker adapter, and sits about 124 lines before the
refusal the same file prints on its other path.

---

## Exact next steps, in order

1. **Rerun the futures funnel into a new family.** Nothing else on this list matters until
   there is a result produced by the current code. Use a new family name so the existing 817
   trials stay in the multiplicity denominator — they were attempted and they count — while
   their metrics stop being quoted. Expect the attrition table to look different in a
   specific way: most of the grid should now be reported as degenerate rather than rejected.
2. **Fix the NQ spread.** The BID_ASK pages are already on disk in `data/futures/.raw/` and
   have never been assembled. Assemble them, measure the per-contract spread, and replace the
   ES-everywhere assumption. This changes every NQ cost gate.
3. **Fix the contracts-allowed unit mismatch** between `TopstepAccount.contracts_allowed`
   (micro-equivalents) and `core/sizing.py::PropFirmSizer` (raw contracts).
4. **Replace the threshold grid with quantile thresholds.** Absolute thresholds on
   return-scaled features is why three quarters of the grid is constant. This is a research
   design change and should be made deliberately, not folded into a bug fix.
5. **Carve a holdout and never touch it.** `make_holdout` and `Holdout.spend()` exist and have
   never run. Nothing here can claim an out-of-sample result until one exists.
6. **Wire multiplicity to the equity track**, which requires the two ledger schemas to be
   reconciled first. Until then the equity ledger applies no correction to a search of several
   thousand cells.
7. **Add a dependency manifest.** There is none of any kind at the repo root. It is the
   largest single reproducibility gap and the cheapest to close.
8. **Resolve the two recovery refs.** `accidental-vault-commit-592e11a`,
   `accidental-vault-commit-bb4bbf8` and the tag `incident/2026-09-13-vault-commit` still hold
   the Obsidian vault. `git push --all` or `git push --tags` would publish it. Now measured:
   3,522 objects, 636.4 MiB, 418.9 MiB on disk, reachable only from those refs - 99% of the
   423 MiB pack. Two further facts found while documenting it: `Quant Brain/QuantModel/.git`
   is a 35-byte gitfile pointing at a module directory that does not exist, so git swept 942
   files in as a plain tree rather than a submodule link, which is *why* the vault was
   committable at all; and `.gitignore` is the entire protection - neither `qb_check.py` nor
   the pre-commit hook mentions the vault, and `commit_scope.py` would not stop an explicit
   `git commit -- "Quant Brain/"`. Deleting a ref that holds the only copy of something is
   the owner's decision, which is why it has not been done.

Items 1 through 3 are corrections to things now known to be wrong. Items 4 through 7 are the
difference between a machine that can detect a false result and a machine that can produce a
true one.
