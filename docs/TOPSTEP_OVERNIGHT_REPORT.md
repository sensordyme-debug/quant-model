# Topstep $50K Combine — overnight report, 2026-09-14

Read `docs/TOPSTEP_STATUS.md` first if you want the two-minute version.

Nothing was pushed. Nothing was committed. Every change is in the working tree for review.
Order transmission stayed off. `/api/Order/place` was never called and, as of tonight, cannot
be reached by any code path in this repository.

---

## 1. Executive summary

Two things happened, and they are independent.

**Your ProjectX credential does not authenticate.** The venue answers `errorCode 3`,
`InvalidCredentials`. The request reaches `api.topstepx.com`, is accepted as well-formed, and
is rejected on the pair itself. That blocks Gates 2 through 5 and 10, and it is the only thing
standing between this repository and real ProjectX data.

**A 240-trial strategy tournament on real minute data found nothing, and the way it found
nothing is useful.** Zero candidates cleared the multiplicity-corrected bar. The single result
that cleared the uncorrected bar went negative out of sample. Four of the eight nominal
survivors are one good day each. Underneath the null result is a quantified reason: at these
costs the average trade in the entire tournament captures about half of what it costs to make.

Three real defects were found and fixed, one of them worse than the audit that flagged it.
Seven further defects in the execution path were found, proved against a fake venue, and
pinned rather than papered over. One of those seven is the most immediately relevant thing in
this report: the governor's contract caps are direction-blind, so adding the Topstep
five-contract cap would make the risk engine block your exits. The suite went from 2,280 to 2,462 passing with nothing weakened.

---

## 2. Initial state

`git status` clean at `e0ba311`. Suite 2,280 passed, 9 skipped, 10 xfailed.
`live/secrets.env` present, untracked, gitignored, containing seven names including the three
ProjectX ones. Config doctor reported `READ_ONLY_READY`.

## 3. Final state

`git status`: 10 modified, 9 new, nothing committed, nothing staged.

```
 M quant_brain/core/sizing.py                 M tests/conftest.py
 M quant_brain/markets/futures_cme/paths.py   M tests/test_propfirm_acceptance.py
 M quant_brain/markets/futures_cme/propfirm.py M tests/test_qb_paths.py
 M quant_brain/markets/futures_cme/topstep.py  M tests/test_qb_sizing.py
 M quant_brain/markets/futures_cme/twin.py
?? quant_brain/brokers/projectx_readonly.py  ?? tests/fakes/
?? scripts/strategy_tournament.py            ?? tests/test_contract_ceiling.py
?? research/tournament_2026_09_14*.json (3)  ?? tests/test_execution_integration.py
?? docs/TOPSTEP_STATUS.md                    ?? tests/test_path_reconstruction.py
?? docs/TOPSTEP_OVERNIGHT_REPORT.md          ?? tests/test_projectx_readonly.py
```

Suite: **2,462 passed, 9 skipped, 15 xfailed, 0 failed.** `ruff check` clean.

## 4. ProjectX authentication — FAIL

| | |
|---|---|
| Endpoint | `POST https://api.topstepx.com/api/Auth/loginKey` |
| Result | HTTP 200, `success: false`, `errorCode: 3`, `errorMessage: null` |
| Meaning | `InvalidCredentials` per `docs/topstep/API.md` §1297 |

What this rules out. The network is reachable and the base URL is right, because a JSON body
came back. The request shape is right, because a body missing `userName` or `apiKey` is
rejected with HTTP 400 before any credential check and this was a 200. The parsing is right:
credential shape measured without printing any value is username 8 characters all lowercase,
key 44 characters mixed case with digits and punctuation, neither carrying quotes or
whitespace. They are being sent exactly as stored.

So the pair itself does not match an active key. The documented remedy is to confirm you are
sending your **platform login username** rather than your email, and to generate a fresh key
and copy it exactly.

**One attempt was made and no retry.** That is deliberate and enforced by a test: a wrong key
retried in a loop is how an account gets locked, and a lockout during a Combine is worse than
a failed script.

## 5. Target account — BLOCKED, and one thing worth knowing

`TOPSTEP_TARGET_ACCOUNT_ID` is set to `50KTC-SKU-V2-DLL-679574-19137660`.

That is an account **name**. The API's `Account/search` returns objects whose `id` is an
integer and whose `name` is a string, so binding needs a lookup rather than a direct use.
`bind_account()` was written for exactly this and is tested: it matches on name or numeric
id, **exactly** — not prefix, not case-insensitive — and it refuses on zero matches, refuses
on more than one, and refuses when the target is unset. It never falls back to the first
account. In the fixture used by the tests the first account is a PRACTICE account, which is
what a silent fallback would have selected.

It cannot be verified against the venue until authentication works.

## 6. Contracts — BLOCKED

No contract discovery was possible. The repository's existing contract table was independently
verified earlier against published CME values, 12 of 12 roots and 14 of 14 P&L cases, so the
research below rests on verified mechanics even without the venue.

## 7. Data — real, and already here

No ProjectX history could be downloaded. It was not needed for tonight, because real minute
data is already on disk and was validated earlier this week.

| store | rows | RTH sessions | complete sessions used |
|---|---|---|---|
| ES | 447,600 | 326 | 313 |
| NQ | 447,596 | 326 | 313 |
| MES | 358,845 | 261 | 252 |
| MNQ | 358,845 | 261 | 252 |

**1,612,886 rows.** No data was fabricated and no synthetic series was substituted anywhere.

## 8. Data quality — PASS

All four stores pass the futures validator with 0 FAIL: zero duplicate timestamps, zero
out-of-order rows, zero impossible OHLC bars, zero interior session gaps, DST correct at both
transitions. The two warnings per store are the known, explained roll-overlap and roll-gap
entries. Sessions are admitted only when they open on the window's first minute, close on its
last, and hold one bar for every minute between; every session used is exactly 376 bars.

## 9. Bugs fixed

**The Monte Carlo path reconstruction, and it was worse than the audit said — in the
opposite direction to the obvious guess.** The audit reported a −$900 worst mark becoming a
−$51,947 median path. It reproduced, and the mechanism is now named: `paths._rebuild` laid a
resampled day's P&L onto an **unrelated** template session's intraday shape and rescaled that
shape by `new_pnl / template_pnl`, an **unbounded ratio**. A session closing near flat is a
divide-by-almost-zero, and a negative ratio flips the sign, so the same day could come back
either as a −$476,410 trough or as a peak with no drawdown recorded at all.

Measured on the 325 real ES sessions behind the Topstep baseline, whose worst single-session
mark is −$1,106:

| | pass rate | paid | liquidated | median worst mark |
|---|---|---|---|---|
| before | 1.7% | 0.0% | 100.0% | −$599,614 |
| after | **32.0%** | **22.0%** | **97.3%** | **−$1,917** |

So the net effect on real data was **pessimistic**: it manufactured liquidations, and the
funnel's Topstep survival gate was discarding strategies on paths that cannot happen. Every
pass probability computed on real intraday paths before tonight is void and was biased
against the strategy. Anything previously rejected by that gate deserves re-scoring.

No existing test caught it because every fixture used a helper whose intraday marks are
*proportional* to the close, and a ratio rescale maps a proportional path to another
proportional path. The defect was nearly invisible in fixtures and only bit on real,
non-proportional data — that is, only in production.

Fixed by replacing one ratio function with three bounded primitives, each caller stating which
it means: move whole sessions unchanged, re-close additively, or scale the session and its
path together. Nineteen hand-computed tests, verified by monkeypatching the old
implementation back in: 7 of the 19 fail against it. Four related defects were fixed in
passing, including a `zip(strict=False)` that truncated silently.

Worth recording because the brief was wrong about it: the scale test I asked for does **not**
detect this class of bug. A ratio is scale-invariant, so the old code passes it. The detector
is the worst-mark bound — a reconstructed path's trough can never be worse than the sum of
the losing closes plus the deepest single-session mark.

**The contract-ceiling unit mismatch.** One correction to how this was described earlier:
at a 2-point stop the sizer's own budget binds at 5, not the ceiling, so that row was a
coincidence for a different reason than assumed. `contracts_allowed` returns micro-equivalents and both
consumers treated it as raw contracts, so the sizer proposed 10 ES at a one-point stop, 20 at
half a point and **40 at one tick** against a published ceiling of five, reporting the binding
as the strategy signal every time. Fixed by giving the account protocol a symbol-aware `max_contracts_for`.
Verified: ES 5, NQ 5, MES 50, MNQ 50, at every stop distance, binding correctly reported as
the prop-firm cap, an unknown root sized at 0, and with 3 ES open the MES headroom correctly
falls to 20. 83 tests. The equivalence reaches `core` without `core` importing `markets`
because it travels as an answer rather than as data: core asks "how many ES may I hold" and
the markets object replies in the caller's unit.

One consequence to be aware of: on an Express Funded Account this now sizes ES at **zero**.
The fallback ladder permits a tenth of the allowance, five micro-equivalents, and one ES
consumes ten. That is arithmetically right given the fallback; if it looks wrong, the number
to argue with is the unpublished XFA ladder, not the ceiling.

**A read-only ProjectX client that cannot place an order.** `ReadOnlyTransport` holds a closed
allow-list of 11 documented read endpoints and refuses anything else before a socket opens,
with a separate named refusal for order and position writes. Verified: `/api/Order/place`,
`/api/Order/modify`, `/api/Order/cancel`, `/api/Position/closeContract` and an unknown path
are all refused, and a refused call is not even recorded as attempted.

## 10. Bugs found and pinned, not fixed

The fake-broker suite drove the real risk and execution chain end to end for the first time.
Seven findings, each proved against a fake venue and pinned as a strict xfail carrying its
evidence. Of the ten invariants tested, six hold and four fail.

1. **No production `RoutedExecutor` is given an intent journal, so nothing deduplicates.**
   `intraday_trader.py:352` and `paper_trade.py:717` and `:867` all construct it without
   `journal`, and `_claim()` then returns `None` for every intent. Neither runner sets an
   `intent_id` either, so attaching a journal alone would refuse everything with
   `IDEMPOTENCY_NO_ID` — both halves have to be fixed together. Demonstrated live: **6
   contracts on the wire for a 3-contract decision.**

2. **Nothing carries a fill into a position book.** `RoutedExecutor` owns no positions, no
   fills and no fill callback, and `ExecutionAdapter` declares only `submit`, `working` and
   `cancel_all`, so an adapter has no upward channel for a fill at all.
   `core.execution.Position.apply` is correct and has exactly one caller in the tree, the
   in-memory research ledger. This is the structural form of "the position book stayed zero".

3. **`Fill` carries no venue identity** — no fill id, exec id or broker id — so a repeated
   fill message cannot be told from a second fill. An echoed fill doubles the book while the
   venue holds one contract.

4. **`IntentState` cannot represent a fill.** PENDING → SUBMITTED → ACKED or FAILED, and
   `advance()` raises out of ACKED. An ack is acceptance, not execution, so after an ack
   `recover()` returns nothing whether the order filled, half-filled, or filled with the
   message dropped.

5. **`ExecutionAdapter` cannot report positions**, so production code can never hand
   `reconcile()` a broker-side snapshot. The one adapter that could ask a real venue raises
   `NotPermitted` from both `working()` and `reconcile()`.

6. **`OrderType` has no STOP or STOP_LIMIT**, and `OrderIntent` has no stop price and no
   attached or OCO leg. `protection.verify()` counts an order only when its kind is a stop, so
   a stop placed through `RoutedExecutor` can never appear as one. This is the mechanical
   reason every open position is UNPROTECTED by the module's own definition: not unwired,
   **not expressible**.

7. **The governor's contract caps are direction-blind and block the exit.** `LimitEngine`
   computes `held = abs(positions[symbol])` and `room = max(0, cap - held)` with no reference
   to the intent's side. Verified: long 2 with a cap of 2, a SELL 2 is **denied**; long 1 with
   a cap of 2, a SELL 2 is **silently reduced to 1**, leaving a position the strategy believes
   it closed. Only an explicit FLATTEN escapes, and neither runner spells an ordinary exit
   that way. It is latent today only because the intraday runner configures a daily-loss limit
   and no contract cap — **it goes live the moment a Topstep contract cap is added, which is
   exactly what this mission requires.** The fix is to size the room against the resulting
   position rather than the current one.

A hazard rather than a bug, and worth a decision: `RoutedExecutor.flatten(positions)` closes
what the *caller believes* is open. With a broker-only position the emergency exit sends
nothing and the exposure survives the flatten. Its correct input is a broker-sourced map,
which finding 5 makes impossible.

**`core.reconcile` and `core.protection` are correct and usable.** Driven end to end they
behave exactly as documented: reconciliation reports the broker's number, adopts neither side,
trips `POSITION_UNRECONCILED`, refuses to conclude from a stale snapshot and does not un-trip
on a later clean pass; `verify()` returns PROTECTED, PENDING or UNPROTECTED and refuses to
infer protection from intent. The audit is right that they have no production caller. Findings
5 and 6 are the concrete blockers to wiring them.

## 11. Tests

2,462 passed, 9 skipped, 14 xfailed, 0 failed. Added tonight: 83 contract-ceiling, 19 path
reconstruction, 59 execution integration (54 pass, 5 pinned findings), 24 read-only client.
Nothing was weakened and no test was deleted. One new test was classified as gating so a
failure stops the 09:25 sleeve.

## 12–14. Strategies tested, rejected, surviving

**Tested: 240 trials.** 30 mechanisms across 7 families, each on ES, NQ, MES and MNQ, each on
three temporal splits, plus the exact sign inverse of every one — counted as trials, which is
why the corrected bar is |t| = 3.709 rather than 3.529.

Families: trend/momentum, breakout, mean reversion, session/time, volatility, volume.
**Family G, microstructure, was NOT RUN** and is recorded as such: the bar stores carry no
bid/ask, ES quotes live in a separate file, and a family of always-flat strategies would have
appeared in the table as tested and rejected, which would be a lie about what was tested.

Thresholds are quantiles measured on the **train split only**, then frozen for validation,
test and holdout. A first pass hard-coded them by eye and four never fired while two fired on
three quarters of all bars; a mechanism that never triggers and one that is always on are both
untested and both look tested in a results table.

**Rejected: 232 of 240** on the selection splits. **Surviving to positive on both train and
validation: 8.** Of those, **zero** clear the corrected bar, and exactly one clears even the
uncorrected 1.96 — `NQ INV::breakout.opening_range.q95` at validation t = 1.99, which then
returns **−$1,018 at t = −1.11 on the test split it was not selected on**.

Red team on the eight: four are a single day. Removing each one's best day turns
`MNQ revert.vwap.q95`, `MNQ INV::breakout.opening_range.q95` and `MNQ INV::trend.accel_confirm`
negative, and drops `NQ revert.vwap.q95` from +$657 to +$13.

**Eight of 240 positive on both splits, where a zero-edge null predicts about 60.** The
systematic effect across these mechanisms is negative.

## 15. Topstep simulation

Pass probabilities in this section are **post-fix** — the tournament was re-run after the path
reconstruction was repaired, and the pre-fix run is retained separately for comparison.

26 of 240 cells reached the twin at all; the rest were stopped by the cost gate first. Median
`p_pass_combine` is 0.003. Six exceed the 10% survival floor. The best is 0.440, for a cell
that is not among the eight survivors. Among the survivors the best is 0.307, on a strategy
whose train net is $14 and whose test t is 0.24, which is noise.

**No candidate is put forward.** There is no strategy for which a pass probability should be
quoted as a property of a strategy rather than of a sample.

## 16–18. Shadow, practice, Combine readiness

Shadow mode: **BLOCKED**, needs realtime data, needs authentication. The interface work is not
wasted — the read-only client is built and tested — but no realtime connection was attempted
because there is no session token to attempt it with.

Practice: **NO.** Finding 5 above means a protective stop cannot currently be expressed.

Combine: **NO**, and nothing overnight moved it. Human approval remains required and no
process can remove that checkpoint.

## 19. Remaining blockers

1. The ProjectX credential. Everything from Gate 2 to Gate 10 waits on it.
2. No stop order type, so no bracket protection.
3. No fill-to-position-book connection and no intent journal in the live path.
4. No strategy candidate.
5. Statistical power. Per-session P&L standard deviation of a one-lot always-in rule is $222.7
   on MES over 261 sessions. This dataset can reject a large claimed edge and cannot confirm a
   small real one. That is a property of fifteen months of data, not of the code.

## 20. Exact next steps

**1. Fix the credential.** Platform login username, not email. Fresh API key, copied exactly,
into `live/secrets.env`. Then `python -m quant_brain config doctor`.

**2. Decide the research question.** Median cost is $2.10 per round turn and median gross
captured is $1.04. The turnover buckets are monotone: under 3 round turns a session, 33% of
cells are profitable and median gross exceeds cost at 1.25×; over 10 a session, 4% and 0.36×.
A one-minute intraday mechanism cannot pay $2.10 a round turn on these instruments. Lower
frequency or larger capture — different programmes, and the choice is yours.

**3. Fix the execution path, in this order.** A stop order type first, because without it a
position cannot be protected at all. Then the direction-blind contract cap, because adding a
Topstep cap without fixing it means the governor blocks your exits. Then the intent journal
with intent ids, then the fill-to-position-book wiring, then a position-reporting adapter
method so reconciliation and restart recovery become possible.
