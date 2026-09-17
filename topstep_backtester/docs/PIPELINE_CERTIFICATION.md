# Pipeline certification — `topstep_backtester` (Layer B) over `topstep-backtest` 0.4.0

Forensic integration audit of the research pipeline. This certifies the **plumbing**, not
any strategy. No strategy has been backtested; `ACTIVE_STRATEGIES = 0`.

```
upstream engine       topstep-backtest 0.4.0
upstream API hash     fbc36b5fa62afdad
upstream modified     NO
Layer B code hash     f0f02e66bb660e37
Layer B source files  37
Layer B tests         144 passed
lint / types          ruff clean, pyright 0 errors
active strategies     0
```

## Verdict

> **YELLOW**

GREEN would mean every question below is answered GREEN. Five are not: three capabilities
the upstream engine does not have (funded accounts, XFA, payout timing), one that neither
layer has (an exchange-holiday calendar), and one that cannot honestly be claimed yet —
the pipeline has never processed a real dataset, only synthetic fixtures. YELLOW is the
accurate reading and the pipeline is nonetheless **ready for the first user strategy**, with
the limitations stated explicitly rather than discovered later.

A note on what YELLOW is not: it is not a hedge about correctness. Every question about
arithmetic, causality, determinism and reconstruction is GREEN, with evidence.

---

## The fifteen questions

| # | question | verdict |
|---:|---|---|
| 1 | Is the upstream package untouched? | **GREEN** |
| 2 | Is the integration faithful? | **GREEN** |
| 3 | Is the data valid? | **YELLOW** |
| 4 | Are timestamps correct? | **GREEN** |
| 5 | Is DST correct? | **GREEN** |
| 6 | Is the strategy interface deterministic? | **GREEN** |
| 7 | Is lookahead prevented? | **GREEN** |
| 8 | Are results reproducible? | **GREEN** |
| 9 | Can every trade be reconstructed? | **GREEN** |
| 10 | Can monthly P&L be reconstructed? | **GREEN** |
| 11 | Can Topstep account paths be reconstructed? | **YELLOW** |
| 12 | Are Monte Carlo assumptions documented? | **YELLOW** |
| 13 | Can stale results be detected? | **GREEN** |
| 14 | Is strategy genealogy tracked? | **GREEN** |
| 15 | Is live trading impossible from this pipeline? | **GREEN** |

---

### 1. Is the upstream package untouched? — GREEN

Installed from PyPI into system Python 3.14.7; `pip install --dry-run` first confirmed the
resolution was clean (prebuilt `ta_lib-0.7.1` wheel, zero upgrades or downgrades to existing
packages). Nothing in this repository writes to `site-packages`.

Enforced three ways:

- `validation/layering.py:scan_upstream_imports` parses **every** Layer B module with `ast`
  and fails if any module other than `upstream.py` imports `topstep_backtest`. Result: 0
  findings across 37 files. AST rather than grep, so a docstring that names the package is
  invisible to it and the check never needs an exclusion list.
- `test_the_upstream_package_has_not_been_modified` reads the mtime of every installed `.py`
  and fails if the spread exceeds an install window — an in-place edit stands out as an
  outlier.
- `upstream.api_fingerprint_hash()` captures the structural shape of all 23 consumed names
  and is pinned at `fbc36b5fa62afdad` by a test. An engine upgrade that renames a field or
  changes a default fails loudly instead of silently moving every number.

No monkey-patching, no subclass that overrides a calculation, no vendored copy.

### 2. Is the integration faithful? — GREEN

Layer B computes no fill, no P&L, no drawdown and no prop-firm verdict. It translates,
configures, runs, and reports. The evidence that the translation is faithful is not internal
consistency but agreement with arithmetic derived independently:

- **Hand-computed goldens.** `strategies/probe.py` buys 1 ES at 5000.00 and exits at 5002.00:
  2.00 points ÷ 0.25 tick = 8 ticks × $12.50 = **$100.00** gross, less one round turn =
  **$96.20**. The engine reports exactly that. A second fixture where the bar opens *through*
  the target pays **$150.00**, and a test asserts it pays strictly more than the first — a
  pipeline that capped winners at their limit price would fail.
- **Independent reconciliation.** `reference/arithmetic.py` recomputes the money from the
  engine's fills using only the tick table. It imports nothing from `topstep_backtest` or from
  the seam — asserted by parsing its imports, which resolve to `{__future__,
  collections.abc, dataclasses, decimal}` — so agreement is evidence, not tautology.
  Result at every rung: `gross_delta 0.00`, `net_delta 0.00`, exact, with no tolerance.
- **The reconciliation can fail.** `test_the_reconciliation_detects_a_disagreement` feeds it a
  deliberate $50 error and requires it to notice; another test proves a single cent is a
  disagreement. Without those, every green tick would mean nothing.
- **The probe's constants are checked against the engine's own instrument table**, so the
  expected arithmetic cannot drift from the real contract terms while still passing.

### 3. Is the data valid? — YELLOW

The path is built and enforced; it has not yet carried a real dataset.

What is GREEN: `data/prepare.py` goes through the certified canonical layer
(`quant_brain.data.loader.load`) for schema validation and the three-valued quality gate, then
adds the conditions the **engine** imposes — instrument coverage, a translatable bar interval,
and execution validity. `adapters/bars.py` then refuses, rather than repairs, every defect it
can see: an off-grid price, a fractional volume, a missing price, impossible OHLC, a duplicate
timestamp, an out-of-order frame, and any adjusted continuous series. Adapted bars additionally
pass upstream's own `validate_bars` with zero issues. Quality WARNs are carried into the run
manifest rather than swallowed.

Why YELLOW: every test to date runs on synthetic fixtures. The first real dataset may surface
conditions no fixture anticipated. Also U5 — neither layer has an exchange-holiday calendar,
by deliberate agreement between them, so a holiday bar is indistinguishable from any weekday
bar.

### 4. Are timestamps correct? — GREEN

**This is where the audit found its most serious defect, in Layer B.**

The canonical store is start-stamped; the engine advances its clock to `ts_init` and only then
shows the strategy the bar (`engine/backtest.py:181`), so `ts_init` is the bar's completion
instant. The adapter maps canonical stamp → `ts_event` and `ts_event + one interval` →
`ts_init`.

The defect: the obvious spelling `stamps.astype("int64")` returns the column's integers **in
its own unit**, and pandas 3.0.5 builds `datetime64[us]` where pandas 2.x built `[ns]`. On a
microsecond column it therefore returned microseconds, the engine read them as nanoseconds,
and every bar landed in **January 1970** — ordered, self-consistent, and passing upstream
validation because the sequence was still a well-formed weekday series. The `delta` between
bars looked correct because the step is computed separately, which masked it.

Fixed in `_epoch_ns`, which converts explicitly via `.dt.as_unit("ns")` and then **verifies by
converting back**, refusing if the round trip fails. Pinned by
`test_the_epoch_conversion_survives_a_microsecond_column`, which also asserts the fixture is
still microsecond-resolution so the test cannot pass vacuously, and by a test that microsecond
and nanosecond columns produce byte-identical bars.

### 5. Is DST correct? — GREEN

Canonical storage is UTC; the venue clock is applied by the engine, not re-derived in Layer B,
so there is exactly one conversion and it is the one tested. Asserted on four dates spanning
both transitions — 2025-03-07 (EST), 2025-03-10 (EDT), 2025-10-31 (EDT), 2025-11-03 (EST) —
that 09:30 ET remains 09:30 ET with the correct UTC offset on each side. A separate test
asserts that bar spacing stays exactly 60 seconds across a transition: a wall-clock day is 23
or 25 hours there, a one-minute bar never is, and conflating the two is the classic
spring-forward bug.

### 6. Is the strategy interface deterministic? — GREEN

`integrity.check_determinism` runs the same backtest twice with a freshly constructed strategy
each time and compares ending balance, total profit, best day, days traded, trade count, the
**full equity curve** and every round trip. Result: identical, `run_id ca4c2005ce498081` both
times.

Two guards make the interface hard to misuse, both checked at class-definition time:

- `on_bar` must be `async def`. A plain function creates a coroutine that is never scheduled,
  so orders silently vanish and the run reports zero trades — which reads like a strategy that
  found no signals rather than a bug.
- A subclass may not shadow any public name on upstream's `SymbolStrategy`. **This was a real
  defect in the first draft**: `ResearchStrategy` assigned `self.spec`, and upstream's `spec`
  is the *instrument* spec — the tick size and tick value every P&L is computed from. It was
  caught only because upstream happens to expose it as a read-only property; the other thirty-odd
  public names have no such protection, so the guard now covers all of them. The field was
  renamed `research_spec`.

### 7. Is lookahead prevented? — GREEN

Three independent mechanisms, two of them upstream's:

1. **Stamp mapping.** The canonical start stamp becomes `ts_event`, never `ts_init`. Mapping it
   to `ts_init` would hand every strategy one bar of hindsight. Upstream independently rejects
   `ts_event >= ts_init`, which it names "the classic off-by-one look-ahead stamp bug".
2. **Order deferral.** Upstream defers every order to the next bar (`accepted_ts = fill time →
   active next bar`). Asserted: the entry fills on bar `ENTRY_BAR_INDEX + 1`, never on the
   signal bar.
3. **Bracket deferral.** Protective orders created on an intrabar fill are stamped to the next
   bar, so a stop or target can never fill on the bar the entry filled on. Within one bar the
   price path is unknown, so doing otherwise would assume an ordering the data does not contain.
   Asserted directly.

The adapter also refuses adjusted continuous series, which are a subtler form of the same
problem: their prices were never quoted, so a fill against one could not have happened.

### 8. Are results reproducible? — GREEN

`manifests/manifest.py` computes a `run_id` over inputs and assumptions only: the bars as the
engine consumed them, the spec hash, the account and execution profile, the upstream API
fingerprint, the upstream version, and a hash of the ten Layer B modules that can change a
number.

Provenance — operator, wall-clock time, hostname, platform, notes — is recorded **beside**
identity and excluded from it. Tested both directions: two runs by different operators at
different times share a `run_id`; changing any input or assumption changes it. Each ladder rung
has a distinct id (`ea8f348c…`, `ca4c2005…`, `58cbc872…`, `47c9ad12…`), so results computed
under different assumptions cannot be compared by accident.

This inverts a defect from an earlier phase of this repository, where source **file paths** sat
inside a dataset identity hash and the same data hashed differently on two machines.

### 9. Can every trade be reconstructed? — GREEN

`reporting/ledger.trade_ledger` emits one row per closed round trip — contract, side, open and
close timestamps, quantity, gross, costs, net, initial risk and R multiple — read directly off
the engine's `round_trips`. A test asserts the ledger's net total equals the headline
`ending_balance − starting_balance`; a ledger that does not add up to the reported P&L is not a
reconstruction.

### 10. Can monthly P&L be reconstructed? — GREEN

`reporting/ledger.monthly` groups the engine's own `day_records` — using the trading day the
**engine** assigned, not a date re-derived here, so a session spanning midnight lands where the
engine put it. Each row carries trading days, days traded, net P&L, best and worst day, and
ending balance.

`reconcile_monthly` checks the monthly totals sum back to the run's total profit (result:
agrees, delta `0.00`), and `test_the_monthly_reconciliation_can_fail` tampers with a row to
prove that check can fail. The monthly view is the single most effective guard against a curve
that is really one lucky week.

### 11. Can Topstep account paths be reconstructed? — YELLOW

For the **Combine**, GREEN. `reporting/ledger.account_path` returns each trading day with EOD
balance, day P&L, the trailing floor after that day, and the headroom between them.
`worst_headroom` names the day the account came closest to liquidation — reported even on a
winning run, because "ended up $4,000" and "was $80 from liquidation in week one" are both true
of the same equity curve and only one tells you whether to trade it.

The trailing MLL is demonstrably live: after the probe's +$96.20 day the floor moved from
$48,000 to **$48,096.20**, exactly $2,000 below the high-water balance. A static floor would
have meant the rule was not being applied.

Why YELLOW: the account journey **stops at the Combine**. Funded accounts, XFA and payouts are
not modelled anywhere in the upstream engine (see FINDING 2 in `UPSTREAM_FINDINGS.md`). They are
registered as U1–U4 in `reporting/unmodeled.py` and printed as **UNMODELED** in every report.
Nothing here estimates a payout.

### 12. Are Monte Carlo assumptions documented? — YELLOW

`reporting/montecarlo.py` is a thin pass-through to upstream's block bootstrap, which resamples
whole **trading days** in blocks — preserving both the clustering of losses within a day and
the day-level sequence the trailing drawdown rule operates on. A naive per-trade IID shuffle
would report a better pass probability for the same strategy, and would be wrong in the
direction that flatters.

Documented and fixed: `DEFAULT_SEED = 0`, `DEFAULT_PATHS = 2000`, `DEFAULT_BLOCK_LENGTH = 5`.
The seed is explicitly **not a parameter** — running several seeds and reporting the best is the
cleanest way to manufacture a pass probability, so `pass_probability_curve` varies the
**horizon** (5/10/20/30/unbounded days), which answers a real question, rather than the seed,
which answers none. Upstream's `provisional` and `source_truncated` flags travel with every
result and `caveat()` renders the sentence that must accompany any quoted probability.

Why YELLOW: it has never been executed on a real result, because there is no strategy yet.
The assumptions are documented; their behaviour on real data is unverified. Separately,
upstream's `PROVISIONAL_DAY_FLOOR` is 30 days, so any Combine-length sample will carry the
provisional flag — a fact about what this pipeline can conclude, and one worth knowing in
advance.

### 13. Can stale results be detected? — GREEN

`integrity.check_staleness` compares a recorded manifest against the pipeline as it stands: the
spec hash, the Layer B source hash, and the upstream API fingerprint. Any movement is reported
with a specific message naming what changed. Tested: a fresh result is current; a result whose
spec has since moved a parameter raises `StaleResultError` with "spec hash moved".

This is the failure mode that bites in practice — a backtest is run, a threshold is adjusted
three days later, and the number in the report is still the old one. Not through dishonesty, but
because nothing connected the two.

### 14. Is strategy genealogy tracked? — GREEN

`FrozenStrategySpec` carries `derived_from` (a parent spec hash) and `derivation_reason`, and
`derived_from` is **inside** the identity hash: "v2 of the one that lost" is a different
experiment from an independently invented idea, and that difference is precisely what a
multiple-testing correction needs to know. A lineage with no stated reason is refused — that is
the shape a quiet re-tune takes.

`registry.GENEALOGY` records every spec ever registered and **does not forget**: unregistering
removes a strategy from `ACTIVE_STRATEGIES` and leaves the ledger intact, because a strategy that
was tested and withdrawn was still tested, and a ledger that shrank would understate how many
hypotheses were examined — the direction that makes a marginal result look significant.
`lineage()` walks the chain, `family_size()` counts variants sharing a root, and
`hypotheses_examined()` gives the total.

### 15. Is live trading impossible from this pipeline? — GREEN

- `safety.py` declares the posture as constants, all False, and they are **tripwires, not
  switches**: setting one True enables nothing because the capability is absent from the
  package — `assert_research_only()` simply fails. Tested by flipping one and requiring the
  failure, so the guard is known to work.
- `scan_forbidden_imports` (AST) finds no import of `topstep_sdk`, `projectx`, `ib_async`,
  `ib_insync` or `ibapi` anywhere in Layer B. The SDK is a legitimate dependency *of the
  upstream package* for its live/parity code; it is unreachable from ours.
- `scan_for_transmission` (textual, because the risk includes a URL in a string or a key name
  in a dict) finds no occurrence of `place_order`, `submit_order`, `modify_order`,
  `cancel_order_by_id`, `AsyncTopstepClient`, `api_key`, `api_token` or
  `account_credentials`. Exactly two files are exempt — `safety.py`, which defines the list,
  and `layering.py`, which consumes it. A third file needing an exemption would itself be the
  finding.
- No credentials are read, stored or referenced. There is no gateway client, no network call,
  and no code path that constructs an order destined for anything outside the process.

---

## Defects found by this audit

All three were in **Layer B**, not upstream. All three were silent.

| # | defect | how it would have shown up | status |
|---|---|---|---|
| D1 | `astype("int64")` on a `datetime64[us]` column returned microseconds; every bar landed in 1970 | no error — a well-formed, correctly ordered series with the right bar spacing, passing upstream validation | fixed in `_epoch_ns` with a round-trip assertion; pinned by two tests |
| D2 | `ResearchStrategy` assigned `self.spec`, shadowing upstream's **instrument** spec (tick size, tick value) | would have replaced contract economics; caught only because upstream exposes it as a read-only property | renamed to `research_spec`; a `__init_subclass__` guard now covers all 40 public upstream names |
| D3 | `PreparedData.session_count` stored a bound **method**, not an `int` | a method object serialised into a manifest field | fixed; found by pyright once Layer B was added to its scope |

Two further discrepancies were my own **expectations**, not code defects, and the engine was
right in both cases: the bracket-deferral lifecycle (F5) and the trailing MLL raising the floor
after a winning day. Both are now encoded as tests that document the real behaviour.

## Known limitations

1. **Funded accounts, XFA and payout timing are UNMODELED** (U1–U4). Upstream models the
   Combine only and says so. Not estimable here; closing the gap needs an upstream funded
   kernel plus a cited rulebook.
2. **No exchange-holiday calendar** (U5), by deliberate agreement between both layers. A holiday
   bar is indistinguishable from a weekday bar.
3. **The consistency rate diverges**: upstream hardcodes 0.50, this repository's cited rulebook
   reads 0.55. We default to upstream's **stricter** 0.50 so the divergence cannot flatter a
   result; the 0.55 reading is a named non-default profile for measuring sensitivity. Which is
   correct is a question about Topstep's rulebook, not about the engine.
4. **Three ES round-turn costs are in reach** ($3.80 upstream, $3.78 repo table, $4.14 an earlier
   frozen spec). Every profile names its fee source in the manifest; the ladder uses upstream's
   defaults.
5. **No real dataset has been processed.** Every result in this document comes from synthetic
   fixtures.
6. **Monte Carlo has never been run on a real result**, and any Combine-length sample will be
   flagged provisional (upstream's floor is 30 days).
7. **Layer B requires Python ≥ 3.12** and cannot be imported by this repository's 3.11 LEAN
   interpreter. Guarded with an explanatory `ImportError`.
8. **The probe's gross P&L is insensitive to entry slippage** by construction, because upstream
   places bracket children at tick offsets from the actual entry fill. The ladder is verified
   live by asserting the entry **price** moves (5000.00 → 5000.50 at STRESS_2TICK), not the
   gross. A test that compared only gross would pass on a pipeline where the execution profile
   was never wired up.

## What this certification does not say

It says nothing about whether any strategy will make money. A correctly functioning backtester
can and should report a losing strategy; this document certifies that when it reports one, the
number can be trusted, traced, reproduced and taken apart. Engine accuracy and strategy
profitability are separate questions, and only the first has been examined here.
