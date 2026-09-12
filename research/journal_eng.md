# Journal - eng track (platform engineering). Newest first.

## 2026-09-12 - E-8: the gate could stop the sleeve over how much RAM was free at 09:25.

**Hypothesis.** E-8 was filed as a dependency chore: four tests fail on 3.11 for want of
`pyarrow`, and since E-5 made `pytest exit 1` the one condition that stops the sleeve trading,
repointing the task at 3.11 would cause an outage. Latent, low value, fix with a `pip install`.

**It is not a dependency chore, and the interpreter was never the problem.** Reproducing it
turned up a fifth failure the backlog does not name, `test_qb_scheduler::
test_resolve_workers_respects_a_smaller_request`, which then *passed* when I ran it alone. Not
order dependence - the test asks the live machine:

```
resolve_workers(2, "futures")  ->  min(2, workers_for("futures"))
workers_for("futures")         ->  1      # measured 23:31 UTC, commit charge 81%
```

So `assert resolve_workers(2, "futures") == 2` is a statement about **free memory at the moment
pytest runs**, and it is false whenever another track is sweeping - which AGENTS.md guarantees,
because several jobs work this repo concurrently. That reframes the whole item. The gating suite
holds tests whose verdict is a property of the machine rather than of the code:

| test | verdict actually depends on | fires when |
| --- | --- | --- |
| `test_qb_scheduler` worker clamp | free RAM / commit charge | another track is sweeping at 09:25 |
| `test_qb_dataquality` (x2) | the deployed IBKR parquet store | an overnight fetch dies - E-6 found exactly that on 2026-09-11 |
| `test_qb_stats`, `test_qb_labels` | a parquet engine being installed | the task is repointed at 3.11 |

None of them says anything about the book, and **each would have cost the paper sleeve a full
trading day.** The pyarrow one needs an interpreter change to fire; the other two need only a
busy machine or a bad fetch, so this was live risk today, not latent risk.

**Two layers, because fixing only the first leaves the class open.**

*Root cause, per test.* The scheduler test now pins the budget to the file's own `snap()`
fixture and a second test keeps the live-machine half of the property that survives a loaded
box (`1 <= resolve_workers(want) <= want` - the clamp is one-directional, which is true under
any load). The four parquet tests take `importorskip`, the route `test_store_health.py` already
takes. Two of them already skipped on "artifacts not on disk ... a fresh clone should not report
a false failure" - the principle was accepted, the guard just missed the second axis.

*The class.* `tests/conftest.py` grows a `RUNNER_TESTS` set and applies a `runner` marker by
module name; on exit 1 the launcher re-runs `-m runner` and **that** decides. E-5's reasoning -
"a failing test means the sizing or book arithmetic the trader is about to use is provably
wrong" - is true of eight files and false of the other nineteen. The default is *not* gating, so
a new test file has to opt in to the power to cause an outage: E-5's asymmetry one level up.

The narrowing may only downgrade a refusal it can **prove** is off the trading path. Subset also
failed, marker not registered, re-run would not launch, nothing collected -> refuse, exactly as
before. `test_an_unmarked_repo_refuses_exactly_as_before` pins that, and it is why every
pre-existing E-5 test still passes unchanged: their throwaway repos have no marker.

**Verification.** Both new branches proven against the **real** repo and the real conftest, by
writing one probe file that differs only in carrying `pytestmark = pytest.mark.runner`:

| probe | may_trade | outcome |
| --- | --- | --- |
| failing test, unmarked | True | `warn` - "suite failed outside the live trading path" |
| same failing test, `runner` | False | `failed` -> exit 4, no trading |

Suite: **3.11 576 passed / 6 skipped (was 5 failed), 3.14 624 passed**, so the item's headline
is closed and the two interpreters now agree. Full `--preflight-only` against the real launcher
**exit 0**, replay of 2026-09-11 P&L -2,080, 36 trades, *open positions at end: none*;
`live/state/intraday_book.json` and `live/APPROVED_PAPER.md` byte-identical before and after, no
HALT file. `qb_check.py` GATE PASSED.

**Cost.** A green morning still costs exactly one pytest launch - `test_the_subset_rerun_only_
happens_on_a_failure` asserts the second process is never spawned on exit 0. The failure path
adds 13 s (183 tests) against the suite's 30 s, under its own 120 s budget rather than
inheriting the 300 s hang guard, so the gate's worst case does not double at 09:25.

**One thing I fixed outside my own diff.** `qb_check.py` was already failing on 3 pyright errors
in `tests/test_intraday_data_extend.py`, committed by the iterate track in d290f62 - a
`CALENDAR.session(d)` returning `Session | None`. The gate is shared and blocks every track, so
it is two `assert sess is not None` lines with a message that names the real cause (a fixture
date that is not a trading day). Flagged here rather than left silent.

**Decision.** Ship. The gate keeps full strength over the code the trader runs and can no longer
be tripped by an absent optional dependency, a stale data store, or another agent's sweep.

**Next.** E-9 (nothing consumes `store_health.py` on a schedule) is now cheaper and safer to do:
a store finding can be surfaced as a WARN without any risk of becoming a refusal, because the
refusal set is explicit. Then E-7 (3.14 is 6x slower than 3.11 on the same suite).

## 2026-09-12 - E-6: a bar count cannot tell a thin session from a dead fetch. A span can.

**Hypothesis.** `dataquality.py` validates the bars a store *contains* and is structurally blind
to the bars it is *missing* - a missing bar is not a row it can look at. Both minute stores pass
it cleanly and can still hand a backtest a half day. A coverage checker should find real holes.

**The measurement that shaped the design.** Over 169,039 stored sessions, "fewer bars than the
session holds" is two populations, not one, and they need opposite responses:

| shape | example | Alpaca | IBKR | verdict |
| --- | --- | --- | --- | --- |
| SPARSE - scattered minutes, spans 09:30-15:59 | 381/390 | 5,710 | 0 | benign: a consolidated-tape bar only exists if the name traded that minute |
| TRUNCATED - contiguous head or tail absent | 170/390, last bar 12:19 | 262 | 16 | poisons a backtest: the session silently ends at lunch |

A bar count cannot separate them - 170/390 and 381/390 are both "short". Comparing each
session's **first and last bar against the calendar's own open and close** can, and the two
populations barely overlap. So every session is scored on `start_lag`, `end_lead`, `fill`, and
only a contiguous hole is called truncation. That one decision is what the whole module is.

**What shipped.** `scripts/store_health.py` (report-only, never repairs, like `dataquality.py`),
`--strict` / `--json` / `--theta`, plus `tests/test_store_health.py` (27 tests). Reads
`columns=[]` - 63M Alpaca rows in 98 s, the 16-symbol IBKR store in 2.4 s. Findings roll up by
**date**, not by symbol: one dead fetch across 16 symbols is one line naming the date, not 16
copies of it, because a report that prints one fact 32 times is a report nobody reads twice.

Severity is deliberately asymmetric. FAIL is structural corruption only - duplicate stamps, bars
on a closed day, an unreadable file. Truncation and missing days are WARN **plus the exact
dates**, because the right response is to exclude those dates, not abandon the store. One
promotion: if the store's *last* session is truncated that is a FAIL, since it means the most
recent fetch died and every run from here samples a half day at the live edge. And `--strict` is
opt-in: a health report must never be the thing that breaks somebody's cron.

**What it found on the first run.**

| store | rows | finding |
| --- | --- | --- |
| `data/minute` | 1,631,879 | **all 16 symbols truncated on 2026-09-11** at ~12:20 ET (170-175/390). Zero defects in the other 4,192 sessions. |
| `data/minute_alpaca` | 62,998,631 | **44 of 63 symbols truncated on 2026-09-10**; 262 truncated and 356 missing sessions historically, clustered on real dates (2022-03-08, 2022-01-24, 2021-10-25) |
| `data/options/odte` | 18,248,558 | whole: 1,891 days, no missing expiry since SPY went daily, one chain 25 m short |

**A wrong turn worth recording.** I chased the truncated 2026-09-11 into the launch preflight -
the 09:25 gate replays "the last stored session", and replaying that day exits **0** with 15
positions still open and the flatten never reached, so the gate would have passed while testing
nothing. It does not: `last_session()` already skips truncated days. But the guard it uses is
`>= 300 bars`, and a bar count is exactly the instrument this module argues cannot classify a
session. Confirmed against the live store, it is wrong in both directions:

- **A complete early close is 210 bars.** `>= 300` rejects it, so 2025-11-28 and 2025-12-24 -
  both 210/210, both whole - are unreplayable, and the morning gate can **never** exercise the
  calendar-aware flatten that AUD-07 exists for, on precisely the mornings it matters.
- **A fetch that dies at 14:40 leaves 310/390.** `>= 300` accepts it and the replay ends with an
  open book - the defect the guard was added to prevent.

`last_session()` now asks whether the bars span the session. It falls back to the old heuristic
if `store_health` will not import, because a completeness checker must never be the reason the
sleeve fails to launch.

**Verification.** AGENTS.md's runner rule: full `--preflight-only` against the real launcher,
**exit 0 in 23 s** - suite 523 passed, replay of 2026-09-10 P&L -3,920, 45 trades, *open
positions at end: none*, identical to E-5's recorded run, so the deployed behaviour is unchanged
today while both failure modes are closed. `live/state/intraday_book.json` and
`live/APPROVED_PAPER.md` byte-identical before and after, no HALT file created. Suite 520 -> 523
(3.14). `qb_check.py` GATE PASSED (ruff, pyright 0 errors, pytest).

**One test earned its keep immediately.** `test_a_holiday_with_bars_is_a_fail` failed on the
first run: `session_shapes` can only score days the calendar has a session for, so a holiday was
silently absent from the shapes and the non-trading-day check - which read `present` - could
never see the one defect it existed for. Now asked of the raw index.

**Decision.** Ship. The classifier is pinned by tests on the real calendar in both directions,
and the two store findings are specific enough to act on: refetch 2026-09-11 (IBKR) and
2026-09-10 (Alpaca), or exclude those dates.

**Next.** E-8: on Python 3.11 the shared suite has 4 pre-existing failures, all `pyarrow`
missing. Harmless today because the 09:25 task runs 3.14 and `unit_tests_ok` uses
`sys.executable` - but that gate refuses to trade on pytest exit 1, so pointing the task at 3.11
would stop the sleeve over a missing optional dependency: the exact outage E-5 was designed to
avoid. Then E-7 (3.14 vs 3.11 suite speed).

## 2026-09-12 - E-5: the unit suite now gates the 09:25 launch, and it only ever refuses for one reason

**Hypothesis.** E-4's suite protects only the tracks that remember to run it. Wiring it into
`intraday_launch.py` - which already replays the last stored session before letting the trader
start - makes it protect the deploy. The risk is the obvious one: this is the first check in the
repo that can *stop the sleeve trading*, so the failure mapping has to be designed rather than
assumed, or a missing dev dependency becomes a self-inflicted outage.

**What shipped.** `unit_tests_ok()` in `scripts/intraday_launch.py`, called as preflight step 1
(before the replay, so a broken constant is caught in 35 s instead of after a 47 s replay), plus
`--skip-tests` and `--preflight-only`, and `tests/test_launch_preflight.py` (19 tests).

The whole design is one asymmetry - **exit 1 is the only refusal**:

| outcome | verdict | why |
| --- | --- | --- |
| pytest exit 0 | trade, silent | - |
| pytest exit 1 | **refuse, exit 4, alert** | assertion failures: the arithmetic is provably wrong |
| exit 2 collection error, 3 internal, 4 usage, 5 nothing collected | trade + warn | broken *tests*, not a broken book |
| pytest not importable | trade + warn | E-5's explicit requirement |
| suite hangs past 300 s | trade + warn | the replay is the check that guards the strategy path |

**The one real trap, and it would have bitten.** `python -m pytest` with pytest absent exits **1**
- the same code as a genuine test failure. Reading importability off the exit code would have
turned "dev dependency missing" into "sleeve does not trade", the exact outage E-5 said to avoid.
Importability is therefore probed in a separate process first, and
`test_probe_failure_is_detected_without_running_the_suite` asserts the suite is not run afterwards.

**Verification - all three branches, against the real launcher**, with `notify`/`log_event` stubbed
so the forced failure did not fire a false alert at the owner:

| branch | how | exit | alert | logged |
| --- | --- | --- | --- | --- |
| healthy | as-is | 0 | none | `preflight_tests outcome=passed` |
| failing | planted `assert 1 == 2` in `tests/` | **4** | names the failing test | `outcome=failed` |
| pytest missing | gate stubbed to `skipped` | 0 | "trading anyway" | `outcome=skipped` |

AGENTS.md's runner-change rule is satisfied: full `--preflight-only` run including the replay is
**exit 0 in 1 m 41 s** (tests 35 s, replay of 2026-09-10 = P&L -3,920, 45 trades, flat at end).
`live/state/intraday_book.json` still stamped 2026-09-11 15:42, `APPROVED_PAPER.md` untouched, no
HALT file created, and the planted test was removed. Suite: **126 passed** on both 3.14 and 3.11.

**Correction to E-4: the suite is not 0.5 s.** Measured today, pre-existing 107 tests only:
**19.9-24.8 s on Python 3.14, 3.27 s on 3.11.** The scheduled task runs
`pythoncore-3.14-64\python.exe`, i.e. the slow one, so the number that matters for the launch
budget was ~40x the journal's figure before I added anything. With E-5's 19 tests: 39 s on 3.14,
21 s on 3.11. My tests are ~19 s of that and it is almost entirely nested-interpreter start-up -
five cases spawn a real pytest against a throwaway repo in `tmp_path`, because "which exit code
does pytest actually emit for a collection error" is a fact about pytest, not about my mapping,
and a future version returning 1 there would silently start refusing to trade. The remaining
seven codes are pinned by one parametrized synthetic test at ~0 cost. I cut the probe subprocess
on the already-under-pytest path (-11 s) and dropped two cases that re-proved exit 1.
Net launch cost ~35 s against a 09:25 start and a 09:30 open: acceptable, but 3.14 being 6x
slower than 3.11 on the same suite is worth a look on its own.

**Two self-inflicted lessons, both about testing meta-properties.** A guard test that greps its
own file for `unit_tests_ok()` matched first its own docstring and then its own assertion line;
rewritten with `ast` to count zero-argument `Call` nodes, which is what it actually meant. And the
first draft of that guard was a test asserting the real suite passes - `unit_tests_ok()` with its
default root, from inside the suite it runs, which recurses until the machine gives up. The
`ast` guard now exists to stop the next person writing it.

**Decision.** Ship. The gate refuses on exactly one condition, every other path trades, and all
three branches were exercised against the real launcher rather than argued about.

**Next.** E-6 store-completeness checker (untested code reading `data/minute`,
`data/minute_alpaca` and the 0DTE store). Worth filing separately: why the shared suite is 6x
slower on 3.14 than 3.11, since 3.14 is the deploy interpreter.

## 2026-09-12 - E-4: the runners' money paths get a unit suite, and a mutation run proves it has teeth

**Hypothesis.** The two live runners carry ~1,150 lines of sizing, gate and book-accounting logic
that no automated check covers. AGENTS.md requires `--replay` and `compare_orders.py` before a
runner change, but both are integration checks: the replay exercises one stored session's happy
path and cannot reach the daily loss limit, the HALT files, the book rollover or the margin
ceiling, and `compare_orders.py` needs LEAN bars and minutes to run. With several tracks editing
shared code concurrently, a constant edited in one module and not the other, or a dropped sign in
`commission()`, would ship silently. A fast unit suite over exactly those paths should catch that
class of regression in under a second.

**What shipped.** `tests/` (5 files, 107 tests) plus `pytest.ini`, run with `python -m pytest -q`:

| file | n | covers |
| --- | --- | --- |
| `test_paper_sizing.py` | 34 | `plan_orders` band and share arithmetic, the LEAN equivalence, margin ceiling, MOO clock gate, `build_order`, `call_signal` |
| `test_intraday_gates.py` | 23 | `Trader.step`: settle-before-size ordering, same-bar guard, loss limit, HALT files, 15:38 flatten, strategy exceptions, persistence, snapshot cadence |
| `test_intraday_book.py` | 18 | `book_fill` P&L on 5 position paths, JSON round trip, `load_book` mode and date gating, the session clock |
| `test_costs.py` | 17 | `commission` sign/min/1%-cap/TAF-cap, `share_scale`, `slippage`, `volume_limits` causality, sleeve disjointness |
| `test_intraday_sizing.py` | 15 | `targets_to_orders`: gross / per-symbol caps, the 2% band, the always-allowed exit, the equity base |

Three defects already fixed in the repo are now regressions with a test each: the flat-$200 band
that would have sent 9,196 orders against LEAN's 4,653 (2026-09-09), yesterday's closed P&L
surviving into a new session and moving the loss limit by ~$6.8k (2026-09-11), and the sell-side
SEC/TAF fees that A-5 part 2 fitted to IBKR's own `commissionReport`.

**Safety.** `tests/conftest.py` has an autouse fixture that redirects `BOOK_FILE`, `HALT_FILES`,
`APPROVAL`, `LOG_DIR`, `STATE_DIR` and every `log_event`/`notify` entry point into `tmp_path`.
Without it these tests would rewrite `live/state/intraday_book.json` - the file the 09:25 trader
reads and flattens from - and push chat alerts. Verified after the run:
`live/state/intraday_book.json` still stamped 2026-09-11 15:42, no `live/log` file dated today.

**Key metric: does it catch anything.** A pytest plugin mutated each guarded constant one at a
time and the suite was re-run. Every mutation is caught; baseline is 0 failures.

| mutation | tests that fail |
| --- | --- |
| `commission` loses its sign (abs shares) | 6 |
| `MIN_ORDER_VALUE` 0.01 -> 0 (the 2026-09-09 defect) | 3 |
| `DAILY_LOSS_LIMIT` 0.025 -> 1.0 | 3 |
| `GROSS_HARD_CAP` 1.6 -> 99 | 2 |
| `PER_SYMBOL_HARD_CAP` 0.20 -> 99 | 2 |
| `FLATTEN_MINUTE` 368 -> 10,000 | 2 |
| `MAX_MARGIN_USED` 1.0 -> 99 | 2 |
| `MIN_CHANGE` 0.02 -> 0 | 2 |
| `SEC_FEE_RATE` -> 0 | 1 |

The `MIN_CHANGE` mutation caught only **1** test on the first pass, which exposed a real gap: the
value assertions read `intraday_common` while the trader runs on the copies `from ... import` bound
into its own namespace, so a constant changed in one and not the other was invisible. Added
`test_the_trader_uses_the_shared_constants_and_not_its_own_copies`; the mutation now catches 2.
That is the single most valuable test in the suite, because "the backtester and the live trader
cannot drift" is the guarantee the whole two-sleeve architecture rests on.

**One finding, no bug.** `plan_orders` (daily) has no `or target == 0` escape from the band, so a
holding worth less than 1% of equity is never sold; `targets_to_orders` (intraday) always allows an
exit. That asymmetry is correct - `s1_momo.submit_targets` has no escape either, and adding one
would break the `compare_orders.py` equivalence that makes the backtest's 24.4% a statement about
the deployed path - and is now pinned by a test that says so. One of my own assumptions was wrong
and the code was right: a held name absent from the target dict *is* sized to zero when it clears
the band (`set(targets) | set(positions)`), which is the S-18/TQQQ fix generalised.

**Decision.** Ship. Portable across both interpreters (3.11 and 3.14; pytest installed on both),
no network, no parquet, 0.5 s.

**Deliberately not done.** Not wired into `scripts/intraday_launch.py`'s preflight. That is the
obvious next step and it is where the suite would actually block a bad deploy, but the launcher
gates the 09:25 live start, and making it depend on pytest being importable by whichever
interpreter the scheduled task uses risks refusing to trade for a reason unrelated to the book.
Filed as **E-5** with the safe shape: run the suite, log the result, refuse only on a failure, and
treat "pytest missing" as a pass with a warning. Needs a `--replay` run to verify, so it belongs
in its own iteration.

**Next.** E-5 (preflight wiring, with the replay verification), then the store-completeness
checker from the data-pipeline-health option, which has no test coverage either.
