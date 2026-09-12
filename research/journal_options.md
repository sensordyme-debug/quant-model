# Options track journal (O-)

Newest first. The `options` scope: the Theta store, `scripts/odte_*`, `scripts/theta_data.py`,
`scripts/sweep_o*`. Evidence only - this track has never had, and does not ask for, a deployment.

---

## 2026-09-12 - O-5: the cost wall is not an options-market phenomenon. Moved the same chain signal into the underlying, cut the round trip 68x, and the edge shrank to match it. Refused; nothing shipped.

**Why this item, when O-4 said the track should not be scheduled.** O-4's conclusion was that no
item can advance *from the Theta feed* - correct, and re-confirmed live at the top of this run:
`theta_data.py --check` returns `listening True serving True` with `history/quote` at **HTTP 403,
"you only have a FREE subscription"**. SPXW is still one `fetch_day` behind that 403. But O-4's
survey of remaining questions was of *options trades*, and every refusal this track has produced -
O-2 on cost, O-3 on the ceiling of selection, O-4 on the blind estimator - is about the cost of
**transacting in options**. None is about the **information content of the chain**. An
options-derived signal does not have to be harvested in options. That is the one lever never
pulled, it needs nothing but disk, and it is what O-5 tests.

**Hypothesis.** The SPY 0DTE chain's risk-neutral state at a fixed intraday clock carries a
*directional* forecast of the rest of the session's move in SPY, big enough to pay an **equity**
round trip - 3.41 bps of notional on this repository's own cost model, against the ~230 bps of
risked capital that killed O-2. A factor of **68**. If the chain knows anything about direction,
this is the cheapest possible way to collect it.

**Why this is not O-1 re-opened.** O-1 refused an IV gate and its negative was "the payoff
regressor is a volatility *surprise*, so no forecast can reach it" - measured on *prior-day,
end-of-day, 1-week* IV against **|P&L|**. Two things differ. (a) The observation is
**same-session and intraday**: the 0DTE chain at 12:00 prices the move that has not happened yet,
conditional on everything that has, so it is a nowcast of the residual session, not a forecast of
the whole day. (b) The target is the **sign**, which O-1 never tested - its own words were
"implied vol forecasts how big a day will be and not which way". O-1's single |t| > 2 against P&L
was `skew25_1w` at t = -2.81, a *direction* reading it left unexamined.

**Design, pre-registered in `scripts/sweep_o5.py`'s docstring before any run.** Four features x
five clocks {10:00, 11:00, 12:00, 13:00, 14:00}, exit 15:50, **1,890 sessions / 9,445 cells**,
2016-01-08..2026-09-10. Features are read from the chain bar at the clock; the SPY position is
entered at the **open of the minute bar one full minute later** and exited at the open of the
15:50 bar, priced on **real consolidated SPY minute bars** (`data/minute_alpaca/SPY.parquet`), not
on the synthetic parity spot. Every Stage-B threshold is a trailing 60-session median, shifted one
session. Directions were declared up front and the gate is **two-sided**, so it can find either
sign and a pass against the declaration is reported as such.

| feature | definition, at the clock | declared |
|---|---|---|
| `rn_skew` | `p_put(S(1-0.005)) - p_call(S(1+0.005))` off the chain's own `dP/dK` (O-3's) | high -> negative |
| `rn_tail` | the same read at 2.0% of spot - crash-premium tilt, not near-body tilt | high -> negative |
| `rn_drift` | `(K_med - S)/S`, `K_med` = strike where the put's prob-ITM crosses 0.5 | above spot -> positive |
| `d_rn_skew` | `rn_skew(clock) - rn_skew(09:35)` - the intraday *repricing*, O-1's surprise | steepening -> negative |
| `rn_half` | **control, not traded**: half the risk-neutral interquartile span | must predict \|move\| |

**Gate 0 passed, and it is what makes the rest readable.** The chain's put-call-parity spot agrees
with the real tape at **median 0.23 bps, p99 2.19 bps**, so the join and the parity spot are sound.
The control is emphatic: **corr(`rn_half`, |forward move|) = +0.540 at t = +60.0**. The chain
forecasts *magnitude* extremely well on this very sample - which is precisely why a null on
direction is a statement about direction and not about broken feature extraction.

**Two pre-registration errors, both found before any forward return was looked at, both stated
rather than quietly patched.** (1) I declared `rn_skew` would be *identical* to
`sweep_o3.features`. It is not: relaxing O-3's both-rights-two-sided mask to a per-right one also
moves `np.interp`'s bracketing neighbours, so **3 of 8,777 cells differ** (worst 5.01e-01, exact on
**99.97%**, Spearman 0.9993). The check was replaced with an agreement criterion *after* it failed;
no forward return enters it either way, it compares two features with each other. The looser mask
is kept as primary for a reason worth recording: **O-3's mask does not drop cells at random - it
drops the calm ones**, mean |move| **13.3 bps where it drops out against 38.7 bps where it
survives**, because the far wings go no-bid on quiet days. Stage A is reported on **both** masks
and the answer does not move. (2) `rn_tail` is **degenerate**: 28% of cells are exactly zero
overall, **42% by 14:00**, because a 2%-of-spot move prices to zero on *both* wings as the session
decays. Terciles collapse; the groups are reported with their realized sizes rather than presented
as equal thirds.

**Stage A - is there a directional signal at all? 3 of 20 cells reach nominal |t| > 2, 0 of 20
survive Bonferroni (|t| > 3.02 at 20 tests, where ~0.7 nominal passes are expected by chance).**

| clock | feature | T1 / T2 / T3 (bps) | t(T3-T1) | monotone? |
|---|---|---|---|---|
| 10:00 | `rn_skew` | +10.16 / -4.76 / -0.72 | **-2.449** | no - T2 is the lowest |
| 10:00 | `rn_drift` | -3.63 / +1.25 / +7.07 | **+2.375** | **yes** |
| 13:00 | `rn_drift` | -2.67 / +0.73 / +4.34 | **+2.187** | **yes** |
| 10:00 | `o3_rn_skew` (robustness, O-3's mask) | +10.85 / -5.33 / -1.20 | **-2.662** | no |

All three nominal passes carry the **declared** sign, and the 10:00 `rn_skew` reading is *stronger*
on O-3's stricter mask, so it is not an artifact of the mask choice. `rn_drift` is the honest
survivor: monotone at two clocks, in the declared direction. It is also **not a stale chain
re-reading the tape** - corr(`rn_drift`, the SPY move already made that session) is **+0.02 to
-0.05**, and corr with the parity-vs-tape gap is **<= 0.10**. It is real chain information.

**Stage B - does it survive equity costs? 0 of 20 cells clear two-of-three. The best cell is a
coin flip sitting exactly on the cost line.**

| | best cell |
|---|---|
| rule | `rn_drift` @ 10:00, causal long/short on the trailing-60 median, held to 15:50 |
| gross | **+3.28 bps** |
| round trip | **-3.41 bps** |
| net | **-0.13 bps at t = -0.07**, n 1,829, long fraction 0.488 |

The long fraction near 0.49 everywhere is the median split doing its job: these are balanced
long/short books, not a buy-and-hold in disguise (buy-and-hold over the same 10:00->15:50 window
is +1.35 bps). And the regime pattern is decisive against the signal rather than merely
inconclusive: **2016-2019 is negative in nearly every cell** (t -2.4 to -2.9 across `rn_drift`,
`rn_skew` and their clocks), while 2020-2023 is mixed and 2024-2026 negative. Nothing here is
stable across the three regimes in the direction it was declared.

**The result that generalises, and the reason this closes the axis rather than one feature.**
Printed as the `BOUND` block and labelled post-hoc, deliberately in O-3's units:

- `cover` = gross / round trip. **Best of 20 cells, chosen with full hindsight: 0.963.**
  **Zero cells have cover > 1** - not one construction's gross edge covers even the equity cost,
  before any question of significance.
- O-3's cover on the options version of the same chain was **0.319 / 0.765**. O-5 cut the cost by
  **68x** by moving the trade into the underlying, and cover moved to **0.963** - still under one.
  The edge shrank almost exactly as fast as the cost.

**Decision: refused, and the "trade the chain's information somewhere cheaper" escape is closed.**
Nothing shipped, nothing promoted, no config touched, no owner risk posture changed. The durable
finding is the one that took three iterations to see and is now visible in one line: **three
independent constructions on this chain - a credit spread (O-2), a selected credit spread (O-3),
and a directional equity trade (O-5) - all land at cover ~= 1.** The cost wall was never a property
of the options market's spreads; it is a property of how much this chain actually knows. It
forecasts *magnitude* superbly (+0.540 at t +60) and *direction* at the level of the transaction
cost of whatever instrument you use to collect it. **Do not re-open as a feature, clock, horizon or
instrument question** - a fourth construction on the same chain will find cover ~= 1 again.

**Ledger**: 40 DIAGNOSTIC rows under `options/odte_o5_direction` (20 Stage A, 20 Stage B). Feature
cache at `results/options/o5_features.parquet` (gitignored); `python scripts/sweep_o5.py` rebuilds
it in ~3 minutes and reruns every number here from cache in seconds. `sweep_o2.py` and
`sweep_o3.py` were **imported, not modified**; no shipped or runner-loaded file was touched, so no
deploy gate is owed.

**Operational**: `py -3.11` still has no pyarrow - run `sweep_o*` on the default `python`.

**Next step.** With O-5 closed, every question this store can answer has been answered and the
remaining one - **cash-settled European SPXW**, where O-2's fatal exit assumption becomes a fact
and commission per unit of risk falls ~10x - is unchanged behind the **VALUE-tier 403** already in
`BLOCKERS.md`. O-4's advice stands and O-5 does not weaken it: **this track should not be scheduled
again until VALUE is restored.** The one thing O-5 adds to the ask is that it is now the *only*
open item, so the scheduler is otherwise idle on this scope.

---

## 2026-09-12 - O-4: the free options feed cannot refuse a bad trade. Trade prints disqualified; the track is blocked on the human. Also: half of O-3's blocker diagnosis was wrong and this repository caused it.

**Housekeeping first, because it changes how this entry should be read.** O-4 was designed, run
and recorded by the previous run on this track at 17:56 UTC (60 DIAGNOSTIC rows under
`options/odte_o4_feed`), which then ended without journaling or committing anything. This entry
lands that work, and it does not take it on trust. Before writing a word of it:

- the full 60-cell grid was **rerun from scratch over all 1,891 stored sessions** (141 s) and
  reproduces the recorded numbers exactly - sign flips 10, decision flips 0, 56 decisive refusals,
  33 lost, 6 turned positive, blind term 1.610, Spearman 0.776;
- the load-bearing *external* claim was **re-probed live on the Alpaca key**:
  `/v1beta1/options/quotes` is **HTTP 404**, while `/bars` and `/trades` return 200 on the same
  contract and `/snapshots/SPY` returns only a *current* bid/ask;
- the Theta entitlement was **re-checked live** with the new `--check`: `listening True serving
  True`, `history/quote` is **HTTP 403 "requires a value subscription ... you only have a FREE
  subscription"**. The blocker is still open as of 20:4x UTC today.

**Correction to O-3, and the loop caused the error.** O-3 reported "every options endpoint returns
HTTP 478" and read 478 as the lapsed entitlement. It never was. The body says *Invalid session ID.
This can occur if more than one terminal is running* - and more than one was running because
`theta_data.alive()` treated **any** HTTP error as "terminal is dead", so `start_terminal()`
launched a second instance at 10:32. It could not bind the port (`Address 127.0.0.1:25503 already
in use`, in `terminal.out`) but its login invalidated the live instance's session, turning a
recoverable 403 into a dead data path. Stopping both and starting exactly one restored the listing
endpoints immediately. Fixed in `scripts/theta_data.py`: `listening()` now separates "nothing bound
to the port" from "bound and answering with an error", `alive()` no longer reads an HTTP error as
death, `start_terminal()` **refuses** to start a duplicate, and `--check` reports terminal state and
entitlement in one call. **The other half of O-3's diagnosis stands**: the subscription really did
lapse, STANDARD -> FREE between 2026-09-10 02:24 and 2026-09-12 13:32.

**The ask is cheaper than O-3 implied.** The 0DTE store is built by `odte_data.py`, which calls
exactly one endpoint, `/v3/option/history/quote`, and that needs **VALUE**, not STANDARD. VALUE
unfreezes the store, catches up the missing sessions and buys SPXW. STANDARD is needed only by
`scripts/iv_regime.py`, whose output is already on disk. Recorded in `BLOCKERS.md`.

**Hypothesis.** Before this track spends an iteration porting itself to the only reachable free
options source, measure what porting would do to its verdicts. O-2 refused the SPY 0DTE credit
spread on **cost**, not edge, and the decisive term was the spread crossed on every fill (-1.363%
of the position's own max loss against gross +0.783%). A trade-print dataset cannot see that term.
So: **re-price the same trades two ways and count the decisions that change.**

**Design, pre-registered in `scripts/sweep_o4.py`'s docstring before any run.** Same sessions, same
trades, same columns out of `sweep_o2.run_session` - `sweep_o2.py` is imported, **not modified**,
and no shipped or runner-loaded file was touched, so no deploy gate is owed.

| estimator | definition | what it represents |
|---|---|---|
| `NET_QUOTE` | `pnl / risk` - short leg sold at the bid, long bought at the ask, reversed on exit, plus commission | O-2's method, and the truth |
| `NET_PRINT` | `(pnl_gross - fees) / risk` - every fill at the mid, plus commission | the best a trade-print dataset can do |

`NET_PRINT` is deliberately **generous**: real prints sit nearer the far touch on a marketable
order, so an honest Alpaca backtest is at least this wrong. Every number below is an upper bound on
the fallback's accuracy. Grid is O-2's own axes unchanged, so no new tuning enters:
`{put, call} x target {0.05, 0.10, 0.16, 0.25, 0.35} x width {0.30%, 0.75%, 1.50%} x entry
{10:00, 14:00}`, exit 15:50, fee $0.75 = **60 cells x 1,891 sessions**. Verdict rule is O-2's,
applied identically to both: mean > 0 at t > 2 in >= 2 of 3 regimes.

**Result on the pre-registered statistics - and the headline had no power.**

| statistic | value |
|---|---|
| cells evaluated | 60 |
| 1. SIGN FLIP (print > 0 >= quote) | **10** (16.7% of the grid) |
| 2. DECISION FLIP (passes on print, fails on quote) | **0** <- the declared headline |
| 3. FALSE NEGATIVE | 0 |
| 4. BLIND TERM `spread_cost / risk` | mean **1.610** points of max loss (min 0.335, max 8.313) |

Statistic (2) is zero for a degenerate reason, not a reassuring one: **no cell reaches t > +2 under
either estimator**, so a test that only detects a fallback *inventing a pass* is identically zero
here whatever the fallback does. Stating that plainly rather than reporting "0 false positives, the
feed is usable" is the whole point. The identity holds exactly - `quote% - print%` equals the blind
term by construction at max |difference| **1.78e-15** - which is the arithmetic check that the two
estimators differ in the spread and in nothing else.

**The direction that does have power, declared post-hoc and labelled post-hoc in the output.**
Every O-item to date has ended in a refusal, so the question this track actually depends on is the
mirror image: **can the fallback still refuse?**

| | |
|---|---|
| cells decisively refused on quotes (t < -2) | **56 of 60** |
| of those, no longer decisive on prints (t > -2) | **33 (59% of the refusals lost)** |
| of those, prints report a **positive** mean | **6** |
| bias / effect: mean blind term vs mean \|print%\| | **2.72x** |
| Spearman(quote%, print%) across the grid | 0.776 |

The single cell a trade-print study would have picked as its best is
**put 0.35, 1.50% wide, entry 14:00: print +0.356% (t +1.28)** - which at the quote is
**-0.477% (t -1.54)**. The fallback's error is not noise that averages out over 1,891 sessions: the
spread cost is non-negative by construction, so it is a **one-directional bias**, and it is 2.7x
the size of the effect being measured. Rank correlation of 0.776 is the trap - the ordering mostly
survives, so the fallback *looks* usable, while the level that every verdict on this track turns on
is displaced by more than the verdict.

**Decision: trade-print data is disqualified for cost-sensitive options research on this track, and
the track is blocked on the human.** Nothing shipped, nothing promoted, no owner risk posture
changed. This is a negative result about a *data source*, not about a strategy, and it closes the
"can we work around the lapsed subscription for free?" question that would otherwise have consumed
several iterations. A feed that cannot refuse a bad trade is not a fallback for a track whose every
result so far has been a refusal.

**Ledger**: 60 DIAGNOSTIC rows under `options/odte_o4_feed` (already appended by the run that
produced them; this entry adds none). Grid CSV at `results/options/o4_feed_grid.csv` (gitignored).

**Operational note for the next run on this track**: `py -3.11` has **no pyarrow**, so every
`sweep_o*` script that touches the parquet store must be run with the default `python` (3.14).
`py -3.11 scripts/sweep_o4.py` dies in `pd.read_parquet` before doing any work.

**Next step, and there is only one that is not the owner's.** The store is intact and frozen at
1,891 SPY sessions (2016-01-08..2026-09-10, 176 MB) and every question it can answer has been
answered: O-2 closed delta, width, entry time, structure and stop; O-3 closed selection and bounded
it at net zero; O-4 closed the free-substitute escape hatch. The one remaining question -
**price the same premium in cash-settled European SPXW**, where O-2's fatal exit assumption becomes
a fact and commission per unit of risk falls roughly tenfold - is one `fetch_day('SPXW', ...)` away
and is blocked precisely by the 403. **VALUE tier on Theta is the whole ask**; it is in
`BLOCKERS.md` with the endpoint-by-endpoint evidence. Until it is answered this track should not be
scheduled - it has no item that can advance from disk.

---

## 2026-09-12 - O-3: the 0DTE variance risk premium is not conditional, and the ceiling on selection is net zero. Refused. Nothing shipped.

**Hypothesis.** O-2 refused the SPY 0DTE credit spread on COST, not on edge: it measured a real,
calibrated variance risk premium (the chain's quoted breach probability exceeds the realized
breach rate at z = -2.7 to -3.8 in six of six delta/right cells) and then showed that harvesting
it costs more than it pays - gross +0.783% of the position's own max loss against spread -1.363%
and commission -0.950%, net -1.530%. O-2 closed the delta, width, entry-time, structure and stop
axes. **One lever survived all five: selection.** Every cost term is paid per session traded, so a
filter that keeps only the sessions where the premium is richest raises gross per unit of cost
without touching a single parameter of the trade. O-2's own conditioning test (STRESS 2) used only
`iv_regime.parquet` - the ATM 1-week implied level and the term ratio, both *external* to the
traded chain. The chain the trade is written on carries information that study never used.

**Design, pre-registered in `scripts/sweep_o3.py`'s docstring before any run.** Two features,
two directions, terciles formed *within* regime, both reported whatever they say:

| feature | definition (causal, from the entry-timestamp chain and strictly prior sessions) | declared direction |
|---|---|---|
| `rn_skew` | `p_put(S(1-0.005)) - p_call(S(1+0.005))`, interpolated on the strike grid from the chain's own `dP/dK` - the asymmetry of the risk-neutral distribution | sell the side the market overpays for -> top tercile |
| `vrp` | `rn_half - rz_half`: half the risk-neutral interquartile span (distance to the 0.25-prob-ITM strike, both rights, as a fraction of spot) minus the median `\|spot_exit/spot_entry - 1\|` over the previous 20 stored sessions on the same clock | sell when the premium is rich -> top tercile |

Base cells taken **unchanged from O-2's own verdict list**, so no new tuning enters here: **B1** =
put 0.16 prob-ITM, 0.75% wide, enter 10:00, close at the quote 15:50 (O-2's default); **B2** = put
0.25, 1.50% wide, enter 14:00, close 15:55 (O-2's best cell). Both closed at the quote - the
expire-free branch is deliberately excluded, because O-2 showed the exit assumption is what fails.
Gates: **Stage A** gross monotone across terciles *and* `|t(T3-T1)| > 2`; **Stage B** net > 0 at
t > 2 in >= 2 of 3 regimes; **placebo** the complement must not also pass; n >= 100 per cell.

**Identity, both exact.** `sweep_o2.run_study(B1)` over the whole store reproduces the ledger row
O-2's verdict rests on (`20260910T203647Z`) to every recorded digit - **1,889 sessions, -1.5301%,
t -3.20** - and restricted to O-3's 1,848 feature-complete sessions it equals O-3's control at
**max |difference| = 0.000e+00**. The gap between the two is 41 dropped sessions and nothing else;
no line of the trade was re-implemented. `scripts/sweep_o3.py --identity` reruns both.

**Result: 0 of 4 feature/cell pairs clear Stage A. Stage B never ran.**

| cell | control net% (t) | feature | gross T1 / T2 / T3 | t(T3-T1) | Stage A |
|---|---|---|---|---|---|
| B1 | -1.575 (-3.22), n 1,848 | `rn_skew` | 2.365 / -0.884 / 0.723 | -1.61 | FAIL (non-monotone, wrong sign) |
| B1 | | `vrp` | 1.143 / 0.865 / 0.561 | -0.52 | FAIL (monotone, **wrong direction**, null) |
| B2 | -0.242 (-0.88), n 1,645 | `rn_skew` | 1.271 / 0.337 / 0.748 | -0.76 | FAIL (non-monotone) |
| B2 | | `vrp` | 0.908 / 0.411 / 1.009 | +0.15 | FAIL (non-monotone) |

**The `vrp` row is the informative one.** On B1 it is cleanly monotone over 1,768 sessions and it
runs the *opposite* way to the declared direction: the richer the premium the chain is handing the
seller, the *lower* the gross return. That is the textbook reason implied vol is not a free lunch -
it is high because realized is about to be high - and it is now measured on this store rather than
assumed. Selling more when the premium looks rich is the wrong trade here, and selling less does
not help either, because the difference is null at t -0.52.

**The result that generalises, and the reason this closes the axis rather than one feature.**
Printed as the `BOUND` block, labelled post-hoc:

- `cover` = gross / (spread + fee). **`cover = 1.000` IS net zero by construction**, so any filter
  must find sessions with cover > 1 out of sample. Unconditional cover is **0.319 on B1** (needs a
  3.14x lift) and **0.765 on B2** (needs only 1.31x).
- Per-session **corr(gross, cost) = -0.598 (B1) / -0.482 (B2)**. The expensive sessions are the
  *losing* ones - a breached position is bought back through a wide quote - so cost and edge are
  adversely coupled and cannot be pulled apart by choosing sessions.
- **The best of twelve terciles, chosen with full hindsight: B2 `rn_skew` T1, n 550, cover 1.043,
  net +0.052% at t +0.09.** That is the ceiling. Even the single most favourable sixth of the
  sample, selected after seeing every answer, is a coin flip at exactly zero. Two cells reach
  cover ~= 1.0 (1.043, 0.997) and both are net ~= 0, which is the identity restating itself.

**Decision: refused, and the selection axis is closed with the other five.** O-2's five axes plus
this one now span every lever on the SPY 0DTE credit spread that does not require different data.
**Do not re-open as a feature, threshold, quantile or conditioner question** - the bound is not a
property of `rn_skew` or `vrp`, it is the -0.5 to -0.6 coupling between gross and cost, and no
filter built from the same chain escapes a correlation that strong. What O-2 said re-opens it is
still the only thing that does: **OPRA quotes through the closing auction plus the official
settlement print**, which is an owner purchase.

**Ledger**: 14 DIAGNOSTIC rows under `options/odte_o3_select` (both controls, all twelve
terciles). Only `scripts/sweep_o3.py` was added; **`sweep_o2.py` is imported, not modified**, and
no shipped or runner-loaded file was touched, so no deploy gate is owed.

**Blocker found in passing, and it is the bigger news for this track.** The Theta Data options
subscription **dropped from STANDARD to FREE between 2026-09-10 02:24 and 2026-09-12 10:32** (both
lines are in the terminal's own log). Every options endpoint now returns **HTTP 478**, including
the cheapest one: `expirations('SPY')` fails, and the missing 2026-09-11 0DTE chain cannot be
fetched. **The 0DTE store is frozen at 1,891 sessions ending 2026-09-10** and is the only options
data this repository will have until the plan is restored. Filed in `BLOCKERS.md`. O-3 was run
entirely from disk and is unaffected; anything after it is blocked.

**Next step.** With selection closed and the data path dead, the O-track has no item that can
advance without the owner. The one that would have been next - pricing the same premium in a
**cash-settled European index option (SPXW)**, where O-2's fatal exit assumption becomes a fact
rather than an assumption and the commission per unit of risk falls roughly tenfold - is a
`fetch_day('SPXW', ...)` away and is blocked precisely by the 478. It is named in `BLOCKERS.md` as
what the restored subscription would buy.
