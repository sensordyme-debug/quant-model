# Blockers

Things that cannot be resolved from the repository, the connected systems, or authoritative
documentation. Everything here needs the owner.

Anything an agent can fix belongs in a track journal, not in this file. Kept short on purpose:
a blocker list that accumulates nice-to-haves stops being read.

Last reviewed: 2026-09-13.

---

## OWNER-1 — Three Topstep numbers are unverified

**Status: OPEN. Blocks any purchase of an evaluation.**

The Topstep rulebook in `quant_brain/markets/futures_cme/topstep.py` carries a source URL,
a retrieval date and a confidence tier for every parameter. Three could not be verified from
any page reachable on 2026-09-12, and the code refuses them rather than guessing.

| What | Best available | Why it matters |
|---|---|---|
| Combine profit target | `$3,000 / $6,000 / $9,000`, **SEARCH tier** — a topstep.com summary, corroborated by the Live Funded page quoting the same three figures as *reserve-unlock* targets, but on no page actually fetched | The single number that decides whether a simulated account passes. Every pass-probability figure produced so far is conditional on it |
| Consistency threshold | Genuinely contradictory. Article 8284208 says *"at or below 55% of your Profit Target"* in one sentence and *"Best Day Profit ÷ Total Profit"* in the next. Your brief says 50% | Both the threshold and the denominator are ambiguous. Defaulted to the strictest reading in play (50% of total profit) |
| Combine monthly cost | **Not found on any page.** No default in the code | With no fee, `TwinResult.net_capital` is `None` and the twin reports gross only, labelled `FEE UNKNOWN - not a profit figure` |

**What is needed:** read the three off your own Combine dashboard and paste them here. Five
minutes. Until then `combine()` raises `UnverifiedRule` unless a caller opts in explicitly,
which is deliberate.

Related but lower stakes: the Express Funded **scaling ladder** is documented to exist
(8284215 quotes the rule) but its rungs are unpublished. `scaling` is empty, which means
simulated size is too large at low balances — the direction that flatters results.

---

## OWNER-2 — No live alerting

**Status: OPEN. Does not block research; blocks unattended operation.**

The order path and the gateway watchdog are both legible now — structured JSONL, six watchdog
states, and every risk refusal logged with the rule that bound it. Nothing **pages the owner**
when the sleeve breaks outside a session. The system can explain itself to someone who looks;
it cannot get someone to look.

**What is needed:** a decision on the channel (email, phone push, something else) and any
credential it requires. The plumbing is a small change once the channel exists.

---

## OWNER-3 — Futures history is a fifth of what the method needs

**Status: OPEN. This is the binding constraint on the whole futures branch.**

**Step 1 is now done and it did not help enough.** Four contracts are stored and validated:

| | bars | sessions | span |
|---|---|---|---|
| ES | 447,600 | 395 | 2025-06-08 → 2026-09-10 |
| NQ | 447,596 | 395 | 2025-06-08 → 2026-09-10 |
| MES | 358,845 | 317 | 2025-09-07 → 2026-09-10 |
| MNQ | 358,845 | 317 | 2025-09-07 → 2026-09-10 |

MES and MNQ stop a quarter short because MESU5 and MNQU5 have aged out of IBKR retention.
ES `BID_ASK` also landed, which retired a real assumption: the spread is a measured median of
exactly 1.00 tick in RTH (95.6% of bars), so the cost model's 0.480 bps agrees with both the
tape and F-2a's independently measured 0.488 bps.

**But breadth is not depth.** Four contracts over the same 1.25 years are four views of one
market regime, not four independent samples. A-4 measured ~2,000 sessions as necessary to
resolve an intraday edge to this repository's own standard; the deepest series here is 395,
which is 20%. There is no 2020 crash and no 2022 rate shock in any of it.

That remains exactly enough data to produce a confident-looking result that will not survive —
F-3's t fell from 2.41 to 0.79 on the horizon correction alone, and this session produced its
own example when a lookahead manufactured a *t* of +6.25 that cleared a 3.56 multiplicity bar.

**The one free step left, and it still does not need the owner:** test whether a free
QuantConnect account offers deeper CME history than IBKR's 2–4 years.

**Owner input is needed only if that comes back short**, at which point the question is whether
to buy depth — and that decision should be made against a specific result worth confirming
rather than as insurance.

---

## OWNER-4 — No Topstep account, and no prop-firm adapter

**Status: OPEN. Blocks execution, not research.**

Both live runners now route through `OrderIntent -> RiskChain -> ExecutionAdapter`, and two
adapters exist (`IBKRAdapter`, `SimulatedAdapter`). **No prop-firm adapter has been written or
exercised against a real venue**, because no account exists and the venue's API is unknown
until one does.

**What is needed:** if and when an evaluation is purchased, the platform Topstep assigns
(Rithmic, Tradovate, ProjectX) and its credentials. The adapter is a contained piece of work
once the target is known; guessing at it now would be building against an imagined API.

---

## OWNER-5 — The Options track is blocked on a paid data tier

**Status: OPEN. Carried forward from `research/BLOCKERS.md`, which this file supersedes.**

This entry exists because creating this file nearly lost the item. The root `BLOCKERS.md` was
written on 2026-09-13 claiming to hold everything that needs the owner, and contained zero
mentions of Theta, options, or the VALUE tier — the only thing blocking an entire branch. A
superseding document that silently drops a live blocker is worse than no document.

The Theta Data plan has lapsed to FREE and re-probes as `HTTP 403 "you only have a FREE
subscription"`. O-4 disqualified the free trade-print fallback: it cannot refuse a bad trade.
The stored 0DTE data (18.2 M rows, 0 fail) remains readable; nothing new arrives.

**One caution before spending.** `research/BLOCKERS.md` justified the VALUE tier partly by
pointing at O-6's PASS being handed to the A-track. That justification has lapsed: A-15
(`cc14f9e`) refused the whole class on mechanism — *"O-6's finding should not be re-proposed
as a sizing input for the A-track"* — and nobody updated the blocker. The VALUE tier may still
be worth buying, but it needs a fresh reason, not that one.

---

## Resolved

- **Runners built broker objects inline** — closed 2026-09-13. Both runners route through the
  adapter; a test walks the AST of every module outside `quant_brain/brokers/` and fails on a
  broker-SDK import.
- **Multiplicity was a caller-supplied number** — closed 2026-09-13. `Ledger.verdict()` counts
  trials from disk and exposes no override.
- **Futures store was written unvalidated** — closed 2026-09-13. `scripts/futures_data.py`
  validates the stitched series and refuses to write a store that fails.
