# Upstream findings — `topstep-backtest` 0.4.0

Behaviour in the upstream engine that diverges from this repository's own sources, or that
is absent and matters. **Nothing here was fixed.** The doctrine is reproduce → document →
report; the engine is immutable and Layer B does not patch, wrap or override it.

Each finding records what was observed, where in the upstream source, what this repository
says instead, what Layer B does about it, and whether the divergence is conservative.

| ref | topic | direction | Layer B response |
|---|---|---|---|
| F1 | consistency rate 0.50 vs 0.55 | **conservative** (upstream is stricter) | default to upstream, offer the other as a named profile |
| F2 | funded / XFA / payout absent | n/a — capability gap | report as UNMODELED, refuse to invent |
| F3 | ES round turn $3.80 vs $3.78 vs $4.14 | small, direction varies | every profile names its fee source |
| F4 | no exchange-holiday calendar | n/a — deliberate upstream choice | matches this repo's own doctrine; recorded |
| F5 | bracket children deferred one bar | **conservative** | encoded in the goldens, documented |

---

## F1 — the consistency rate is 0.50 upstream and 0.55 in this repository

**Observed.** `rules/params.py:73` constructs every `CombineParams` with
`consistency_pct=Decimal("0.5")`, hardcoded. `rules/kernel.py:271` enforces it as the third
conjunct of the pass test:

```python
if (
    closed_balance >= params.starting_balance + params.profit_target
    and total_profit > _ZERO
    and self._best_day <= params.consistency_pct * total_profit
):
    self._verdict = Verdict.PASSED
```

**What this repository says.** `quant_brain/markets/futures_cme/topstep.py`,
`CONSISTENCY_READINGS`, retrieved 2026-09-13, records the *documented* reading as **0.55**
(`doc_calc`, basis `total`) and lists 0.50 only as a `strict` variant.

**Which way it cuts.** Upstream is **stricter**. At a given total profit a lower percentage
caps the best day lower:

| total profit | best day allowed at 0.50 | at 0.55 |
|---|---|---|
| $3,000 | $1,500.00 | $1,650.00 |

A strategy whose best day is $1,600 on $3,000 of profit **fails** upstream and **passes**
under this repository's reading. In the other direction: a single $3,100 day needs $6,200 of
total profit under upstream and $5,636 under the documented reading.

**Layer B's response.** `profiles/account.py` defaults to upstream's 0.50 unmodified,
precisely because it is the harder test — the divergence therefore cannot flatter a result.
The 0.55 reading exists as `TOPSTEP_50K_COMBINE_DOC55/v1` so the sensitivity is a measured
number rather than an argument. It is set through `msgspec.structs.replace` on upstream's own
frozen struct, which is upstream's configuration surface used as intended: the kernel still
enforces the rule, Layer B only states the rate. Any result quoted from that profile carries
its profile id in the manifest and says so.

**Not resolved.** Which reading is correct is a question about Topstep's current rulebook,
not about the engine. Both are available; neither is asserted to be right here.

---

## F2 — funded accounts, XFA and payouts are not modelled at all

**Observed.** The engine models the Combine. `metrics/economics.py:18` states in its own
header: *"Funded is parked; see `docs/ROADMAP.md`"*. Grep across the distribution finds no
XFA logic, no funded rule kernel, no payout schedule, no withdrawal mechanics.

`EvalEconomics(monthly_fee, pass_value, reset_fee, trading_days_per_month)` looks like it
might cover this and does not: `pass_value` is a **scalar the caller supplies** for what
passing is worth. Feeding it a number and reporting the output as an expected payout would
be circular — the answer would be the assumption.

**Layer B's response.** `reporting/unmodeled.py` registers U1 (funded simulation), U2 (XFA),
U3 (first payout timing and distribution) and U4 (the complete account journey) as
**UNMODELED**, with the reason and what would be needed to answer each. Every report prints
that register. No payout figure is estimated anywhere in this pipeline.

**Consequence for the brief.** Any request for funded-account behaviour, first-payout timing
or the full signup-to-withdrawal journey cannot be answered by this pipeline. That is a
capability gap, not an omission from a particular run, and closing it requires an upstream
funded kernel plus a cited rulebook — not Layer B code.

---

## F3 — three different ES round-turn costs are in reach

**Observed.**

| source | ES round turn |
|---|---|
| upstream `fills/fees.py` defaults | **$3.80** ($0.50 commission + $1.38 exchange + $0.02 NFA, per side, doubled) |
| this repository's `instruments.py` | $3.78 (Topstep published, retrieved 2026-09-13) |
| the earlier Initial-Balance frozen spec | $4.14 |

**Why it matters despite being small.** On a strategy taking two trades a day for twenty
days the spread between $3.80 and $4.14 is about $14. That is negligible against a $3,000
target and is not negligible for a result sitting near break-even — which is exactly the
regime where a cost assumption gets waved through.

**Layer B's response.** Every `ExecutionProfile` carries a `fee_source` string and it lands
in the manifest, so no number is ever reported without saying which cost model produced it.
The ladder currently uses upstream's defaults throughout; `fee_overrides` exists for an
explicit, justified departure. A test pins the $3.80 figure so a silent upstream change to
the fee table fails loudly rather than moving every P&L.

---

## F4 — there is deliberately no exchange-holiday calendar

**Observed.** `data/validator.py` states: *"There is deliberately no exchange-holiday check:
this package ships no holiday calendar (see the note in `core/time.py`), so a bar landing on
a market holiday is indistinguishable from any other weekday bar here."*

**Assessment: not a defect, and it agrees with this repository.** The prior release gate in
this repo reached the same position independently and forbids inventing one — a short session
is recorded as `INCOMPLETE_SESSION`, never as `HOLIDAY`, unless objectively verified. Two
independent implementations refusing to guess at a calendar is the correct outcome.

**Layer B's response.** Recorded as U5 in the unmodeled register. Closing it means sourcing a
real CME holiday and early-close calendar and applying it in the canonical data layer, where
the provenance is, rather than inferring it from bar counts.

---

## F5 — bracket children cannot fill on the bar the entry filled on

**Observed.** `execution/sim_broker.py:943`: *"accepted_ts = fill time → active next bar."*
And at line 491: *"Candidate fills are computed once against the bar-start order book (no new
orders can join mid-bar: children created on an intrabar fill carry accepted_ts stamps that
defer them to the next bar)."*

So the lifecycle is:

```
bar N completes  ->  the strategy is shown bar N and places a market order
bar N+1          ->  the entry fills, at bar N+1's OPEN
bar N+1          ->  the bracket children are created but are NOT yet active
bar N+2 onward   ->  the stop and target can fill
```

**Assessment: correct and conservative, but surprising.** Within one bar the price path is
unknown, so filling a protective order on the entry bar would require assuming an ordering
the data does not contain. It is documented upstream, not incidental.

**Why it is recorded here anyway.** It changes hand-computed expectations, and getting it
wrong produces a plausible number rather than an error. The first draft of the Layer B probe
expected an 8-tick target fill and the engine returned 12 ticks — because the target only
became active on a bar that opened beyond it, making the resting limit marketable. The
engine was right.

**Layer B's response.** Both paths are pinned as hand-computed goldens in
`strategies/probe.py`: `probe_series()` straddles the target and fills at the limit
($100.00), `probe_series_gap()` opens through it and fills at the open ($150.00). A test
asserts the second pays strictly more than the first, so a pipeline that silently capped
winners at their limit price would fail.

---

## A note on what is NOT in this register

No finding here is a claim that upstream is wrong. F1 is a sourcing disagreement, F2 and F4
are scope, F3 is a table that needs naming, and F5 is upstream being careful. The engine
behaved correctly in every case Layer B tested it against independent arithmetic; where the
first draft disagreed with it, the first draft was wrong. That is recorded in
`PIPELINE_CERTIFICATION.md` §Defects found.
