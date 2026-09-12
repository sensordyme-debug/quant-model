# Journal - eng track (platform engineering). Newest first.

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
