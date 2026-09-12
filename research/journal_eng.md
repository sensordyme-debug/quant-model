# Journal - eng track (platform engineering). Newest first.

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
