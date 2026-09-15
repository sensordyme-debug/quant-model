# Exit & Risk Architecture Research

**Research question.** Given an existing entry mechanism, what simple exit/risk architecture
best matches its market mechanism while remaining robust and Topstep-compatible?

**Answer to Phase 16 — the question that controls everything else: the library has BAD
ENTRIES.** Five of six preregistered candidates carry no measurable forward information. The
one that does is borderline, and no exit architecture improves it.

Date: 2026-09-14 · Research only · No commits, no pushes, no ProjectX calls.

Plots: `docs/research/strategy_results/exit/` · Scorecards:
[STRATEGY_SCORECARDS.md](STRATEGY_SCORECARDS.md)

---

## 1. Executive conclusion

| finding | evidence |
|---|---|
| **1 of 6 entries carries information** | `breakout.failed_reversal` MNQ beats a bar-of-session-and-direction-matched control at bars 1, 3, 5 (99.0 / 97.5 / 97.5 percentile; t = 2.48 / 1.93 / 2.14), decaying to nothing by bar 10 |
| **The lab's best-earning cell has no entry edge at all** | `revert.vwap.q90` NQ — $24.73/trade, 80.9% win rate — beats the control at **0 of 7** horizons and sits at the **2nd percentile** at 10 bars |
| **There is no payoff geometry to exploit** | MFE/MAE ratios across all six candidates run **0.97–1.14**. Symmetric excursion means a stop and a target the same distance away hit about equally often |
| **The exit grid is pure overfit** | 41 preregistered architectures. IS↔OOS rank correlation **−0.002**. The in-sample best (+$7.19/trade) delivers **−$20.55/trade** out of sample |
| **The existing exit is already the right one** | `E.time1b` is byte-identical to `F.baseline_invalidation` — median hold is 1 bar, so the mechanism is a one-bar scalp and signal invalidation already fires optimally |
| **It dies at one tick** | OOS break-even slippage is **exactly 1.00 tick** ($0.50 on MNQ). At one tick, OOS expectancy is $0.00 |

**No candidate advances.** The single passing entry is a genuine but weak one-bar effect worth
$0.50/trade out of sample on 104 trades, which one tick of slippage erases exactly.

---

## 2. Phase 1 — candidate selection

Six cells, four families, fixed in `scripts/exit_entry_information.py:CANDIDATES` before any
entry-information number was computed.

| candidate | family | why selected |
|---|---|---|
| `breakout.failed_reversal` MNQ | failed breakout | **Named in the brief.** Best barrier-relative profile in the lab: +$0.95/trade stressed, DD 0.09× MLL, 0.0% DLL breaches. 343 trades is thin — the reason it was RESEARCH, not a candidate |
| `revert.vwap.q95` MNQ | reversion | Strongest positive-expectancy reversion already inside the barrier (0.90× MLL). 80.8% win on 755 trades, +$3.17 stressed |
| `revert.vwap.q90` NQ | reversion | **The canonical "good entry, bad exit?" test.** Highest expectancy in the lab, rejected solely on drawdown (20× MLL) |
| `session.midday_reversion` MNQ | session | Sub-barrier (0.69×) on 1,797 trades from a different family. Near-zero expectancy — a clean test of whether an exit alone moves a coin flip |
| `trend.ret_30.q80` MNQ | trend | **Contrast, not a hope.** Best trend cell is still −$1.62/trade, 24.1% win, t = −1.99. Phase 16 is only interpretable with a family expected to fail measured alongside |
| `breakout.range_expansion.q80` MNQ | breakout | Best pure breakout on micros. The brief asks for a breakout contrast and `failed_reversal` is a *fade*, not a breakout |

**Not selected on P&L.** `revert.vwap.q90` NQ is in the set precisely because its P&L is
suspicious relative to its risk, not because it is large.

---

## 3. Phases 4 & 16 — does the entry contain information?

This ran **first**, because the brief forbids using exit optimisation to rescue an entry with
no forward advantage.

**The control is the test.** Each candidate is compared against 200 controls matched on *both*
things that could manufacture a result: **bar-of-session** (same intraday timing distribution)
and **direction** (inherits the candidate's own long/short sequence). What survives that
matching is what the signal knows.

Declared before running: **PASS** = beats the control's 95th percentile at ≥2 horizons;
**MARGINAL** = exactly 1; **FAIL** = none. Plus the horizon must be mechanism-consistent —
each candidate's expected horizon was written down in advance.

| candidate | verdict | horizons beaten | expected horizon | consistent? |
|---|---|---|---|---|
| `breakout.failed_reversal` MNQ | **PASS** | 1b, 3b, 5b | short (fades a failed move) | **yes** |
| `revert.vwap.q95` MNQ | MARGINAL | 60b only | short (snap back) | no |
| `session.midday_reversion` MNQ | MARGINAL | 60b only | short (midday fade) | no |
| `trend.ret_30.q80` MNQ | MARGINAL | 60b only | long (trend needs time) | yes |
| `revert.vwap.q90` NQ | **FAIL** | none | short | — |
| `breakout.range_expansion.q80` MNQ | **FAIL** | none | long | — |

### The passing candidate, in detail

| bars | fwd $ | t | ctrl p95 | percentile | MFE $ | MAE $ | MFE/MAE |
|---|---|---|---|---|---|---|---|
| 1 | 3.203 | **2.48** | 1.957 | **99.0%** | 19.07 | −17.98 | 1.06 |
| 3 | 4.341 | 1.93 | 3.591 | **97.5%** | 32.91 | −29.35 | 1.12 |
| 5 | 6.240 | **2.14** | 5.274 | **97.5%** | 42.50 | −37.17 | **1.14** |
| 10 | 1.879 | 0.47 | 6.980 | 69.0% | 56.24 | −53.31 | 1.06 |
| 30 | 7.179 | 1.07 | 9.384 | 88.0% | 91.82 | −84.59 | 1.09 |
| 60 | 0.928 | 0.11 | 13.729 | 57.5% | 119.77 | −112.55 | 1.06 |

The edge is early and decays by bar 10 — exactly as preregistered for a fade mechanism.

### The result that answers Phase 16

`revert.vwap.q90` NQ earns **$24.73/trade on an 80.9% win rate** and has **no entry
information whatsoever** — 0 of 7 horizons, 2nd percentile at 10 bars. Its profit is not
coming from entry timing. Under the brief's own rule, exit optimisation must not be used to
rescue it, and it was not.

### The MFE/MAE table is the ceiling on everything downstream

| candidate | 1b | 3b | 5b | 10b | 20b | 30b | 60b |
|---|---|---|---|---|---|---|---|
| `breakout.failed_reversal` MNQ | 1.06 | 1.12 | **1.14** | 1.06 | 1.02 | 1.09 | 1.06 |
| `revert.vwap.q95` MNQ | 1.03 | 1.05 | 1.05 | 1.02 | 0.97 | 1.01 | 1.05 |
| `revert.vwap.q90` NQ | 1.07 | 1.03 | 1.01 | 0.97 | 0.98 | 0.99 | 0.98 |
| `session.midday_reversion` MNQ | 0.99 | 1.02 | 1.02 | 1.04 | 1.02 | 1.02 | 1.05 |
| `trend.ret_30.q80` MNQ | 1.01 | 1.00 | 1.00 | 1.00 | 1.01 | 1.02 | 1.02 |
| `breakout.range_expansion.q80` MNQ | 1.04 | 1.02 | 1.02 | 1.01 | 1.01 | 1.01 | 1.00 |

A ratio near 1.00 means favourable and adverse excursions are symmetric: **no placement of a
stop and a target creates an edge the entry did not already have.** This was recorded before
the grid ran, and it is what the grid then confirmed.

---

## 4. Phases 2 & 3 — preregistered architectures and their reasoning

41 cells, declared in `scripts/exit_architecture_research.py:build_grid()` before any exit
result. **Entry parameters frozen throughout** (Phase 14).

| # | architecture | grid | economic reasoning, written before testing |
|---|---|---|---|
| A | ATR stop × R target | stop {0.5, 0.75, 1.0, 1.25, 1.5} ATR × target {0.5, 0.75, 1.0, 1.5, 2.0} R = 25 | A fade of a failed move should pay quickly or not at all, so a tight stop with a near target matches the mechanism |
| C | structural stop × target | signal-bar extreme × same 5 targets = 5 | The signal bar's extreme is the natural invalidation price for a reversal |
| D | trailing / break-even | trail {0.75, 1.0, 1.5} ATR; break-even at 1R = 4 | Trailing suits an edge that **persists**. This one decays by bar 10, so trailing is a **falsifiable prediction of underperformance**, not a hope |
| E | time stop | {1, 3, 5, 10, 20, 30} bars = 6 | The measured edge lives at bars 1–5. The sharpest test of whether the information is captured at all |
| F | signal invalidation | the current behaviour = 1 | The thing to beat |
| G | end-of-session flatten | **not a parameter** | Always on. Topstep's mandatory flat is not negotiable |

**Intrabar ambiguity resolved pessimistically.** When a bar's range spans both stop and target,
the simulator always assumes the **stop** hit first. On a wide bar with tight levels, the
optimistic convention converts losses into wins at exactly the settings a grid search is drawn
to. Ambiguous share is recorded (0.0% for the baseline, which has no price levels).

---

## 5. Phases 5, 6, 9 & 10 — the exit surface and its out-of-sample truth

343 trades, split 60% in-sample (239 trades) / 40% out-of-sample (104 trades).

**Best architectures by in-sample $/trade, with what actually happened:**

| architecture | IS trades | IS $/tr | IS PF | **OOS trades** | **OOS $/tr** | **OOS PF** |
|---|---|---|---|---|---|---|
| `E.time30b` | 103 | **+7.19** | 1.21 | 47 | **−20.55** | 0.65 |
| `A.stop1.25atr_tgt2R` | 136 | +2.57 | 1.09 | 55 | −1.41 | 0.96 |
| `E.time1b` ≡ `F.baseline` | 239 | +1.87 | 1.24 | 104 | **+0.50** | 1.07 |
| `A.stop1.25atr_tgt1.5R` | 149 | +1.04 | 1.04 | 63 | −0.20 | 0.99 |
| `D.trail1atr` | 204 | −9.11 | 0.39 | 83 | −8.67 | 0.37 |

- architectures positive in-sample: **11 of 41**
- positive in **both** halves: **3** — and two of those three are the same architecture
- **IS↔OOS rank correlation: −0.002**

A correlation of zero *is* the definition of an overfit grid: choosing an exit on one half
carries no information about the other.

**Trailing stops underperformed, as preregistered.** All three trail variants and the
break-even variant occupy the bottom four rows. The prediction that a decaying edge would not
suit a trailing exit held.

### Phase 9 — is there a plateau?

Architecture A surface, $/trade:

**In-sample** — the only positive row is stop = 1.25 ATR:

| stop \ target | 0.50 | 0.75 | 1.00 | 1.50 | 2.00 |
|---|---|---|---|---|---|
| 0.50 | −5.30 | −4.89 | −3.62 | −4.19 | −2.87 |
| 0.75 | −4.05 | −1.60 | −3.72 | −3.40 | −2.76 |
| 1.00 | −2.02 | −2.14 | −3.00 | −2.32 | −0.90 |
| **1.25** | **+0.70** | −0.90 | **+0.71** | **+1.04** | **+2.57** |
| 1.50 | −2.61 | −2.17 | −1.72 | −0.83 | +0.76 |

**Out-of-sample** — that same row is the *worst* in the surface:

| stop \ target | 0.50 | 0.75 | 1.00 | 1.50 | 2.00 |
|---|---|---|---|---|---|
| 0.50 | −2.17 | −0.57 | −1.46 | −1.64 | −2.06 |
| 0.75 | +0.14 | −0.50 | −0.98 | −1.39 | +0.80 |
| 1.00 | −3.18 | −2.29 | −2.72 | +1.46 | +2.35 |
| **1.25** | **−5.61** | **−5.14** | **−5.31** | −0.20 | −1.41 |
| 1.50 | −6.14 | −6.45 | −6.45 | −5.51 | −1.51 |

5 of 25 positive in-sample, 4 of 25 out-of-sample, sign agreement **64%**. The apparent
plateau **inverts**. This is precisely the pattern the brief warns against, and selecting the
1.25 ATR row would have been the mistake.

### Phase 6 — trade distribution, baseline architecture

| | |
|---|---|
| exit reason mix | 98.7% signal invalidation, 1.3% forced flatten, **0% stop, 0% target** |
| median bars held | **1** |
| MFE/MAE | 1.06 |
| avg MAE of winners | −$12.46 |
| avg MFE of losers | +$8.30 |
| ambiguous bars | 0.0% |

**`E.time1b` is byte-identical to `F.baseline_invalidation`** — same trade count, same P&L, to
the cent. The signal's median hold is one bar, so invalidation already fires at bar one. **The
mechanism is a one-bar scalp and its existing exit is already correct.** That is the single
most useful result in this phase: there is nothing for an exit architecture to add.

---

## 6. Phase 11 — random exit controls

200 replications each, full sample, commission only. Real baseline = **$1.45/trade**.

| control | median | real percentile | reading |
|---|---|---|---|
| random stop/target | −$1.54 | **95.5%** | the baseline **beats** random price exits |
| random timing | $1.45 | 0.0% | **uninformative** — median hold is 1 bar, so geometric(1/1) always returns 1 and the control *is* the exit |
| fixed hold (1 bar) | $1.45 | — | identical, same reason |
| **random entry, identical 1-bar hold** | −$0.38 | **93.0%** | **below the 95% bar** |

**I corrected this control mid-run and it changed the conclusion.** The first version
randomised the entry bar *and* swapped in a random stop/target — two changes at once, giving an
uninterpretable 61.5%. Isolating the entry gives **93.0%**.

That matters: the entry clears the bar-of-session-matched control at 99.0% but only reaches
93.0% against a uniform random entry with the identical exit. **Both are reported.** The
honest reading is that the effect is borderline — consistent with a weak real edge, not an
established one — and 343 trades cannot resolve the difference.

---

## 7. Phase 8 — slippage

Baseline architecture, MNQ, one tick = $0.50.

| slippage | full sample $/tr | **OOS $/tr** | full net | OOS net |
|---|---|---|---|---|
| 0.0 ticks | 1.45 | **0.50** | $499 | $52 |
| 0.5 | 1.20 | 0.25 | $413 | $26 |
| **1.0** | 0.95 | **0.00** | $328 | **$0** |
| 2.0 | 0.45 | −0.50 | $156 | −$52 |

**Break-even slippage: 2.91 ticks on the full sample, exactly 1.00 tick out of sample.**

The brief's rule is explicit: *"A strategy that only works with perfect fills is REJECT."* This
one needs better than one tick of round-turn slippage out of sample — on a contract where one
tick is the minimum price increment. That is a fill assumption no live system should be
underwritten on.

---

## 8. Phase 7 — Topstep economics

Baseline architecture, real intraday paths, `strict_path=True`, 400 block-bootstrapped
120-session paths.

| contracts | pass | breach | survive 20d | median days to target | DLL/session | worst-1% DD |
|---|---|---|---|---|---|---|
| 1 | **0.0%** | **0.0%** | **100.0%** | never | 0.0% | −$436 |
| 5 | 11.2% | 4.2% | 95.8% | 98 | 0.0% | −$2,308 |
| 10 | 39.5% | 43.8% | 56.2% | 68 | 0.0% | −$4,841 |
| 20 | 31.8% | 82.0% | 18.0% | 42 | 4.8% | −$9,383 |
| 50 | 24.0% | 94.0% | 6.0% | 14 | 10.8% | −$23,452 |

The size sweep is the whole story: at 1 contract it is perfectly safe and **never reaches
$3,000**; at 10 it passes 39.5% and breaches 43.8%. **There is no size at which it both
reaches the target and survives the barrier.**

Notably the DLL is *not* the binding constraint here — 0.0% breaches up to 10 contracts. That
distinguishes this mechanism from the reversion cells, which trip the DLL on up to 41.6% of
sessions.

---

## 9. Diagnostic — is the trend entry destroyed by a fast exit?

`trend.ret_30.q80` MNQ was MARGINAL and its one control-beating horizon (60 bars) **is**
mechanism-consistent for trend. It turns over 5,511 times while losing money, which is the
classic "slow information, fast exit" shape. Run through time stops only, labelled a
diagnostic, not eligible for a verdict above WATCH:

| exit | IS trades | IS $/tr | **OOS $/tr** |
|---|---|---|---|
| baseline | 3,290 | −1.39 | −1.94 |
| time10b | 1,983 | −1.33 | −1.72 |
| time20b | 1,447 | **+1.42** | **−4.71** |
| time30b | 1,140 | **+3.56** | **−4.44** |
| time60b | 735 | **+3.61** | +1.64 |
| time120b | 446 | **+3.51** | **−14.29** |

**No.** Lengthening the hold looks good in-sample at every horizon ≥20 bars and collapses out
of sample at all but one — the same overfit signature as the main grid. The one OOS-positive
cell (time60b) is 1 of 7 and is the horizon that was cherry-picked from the entry test.

---

## 10. Phase 13 — exit architecture comparison

| strategy | exit | IS $/tr | OOS $/tr | PF (OOS) | Max DD | MLL ratio | DLL | Slippage break-even | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| `breakout.failed_reversal` MNQ | **F. invalidation ≡ 1-bar** | +1.87 | **+0.50** | 1.07 | −$188 | **0.09×** | 0.0% | **1.00 tick OOS** | **RESEARCH** |
| " | E.time5b | +0.26 | +5.72 | 1.33 | −$483 | 0.24× | — | — | WATCH (rank 10 IS) |
| " | A.stop1.25atr_tgt2R | +2.57 | −1.41 | 0.96 | −$630 | 0.31× | — | — | REJECT |
| " | E.time30b | +7.19 | −20.55 | 0.65 | −$1,059 | 0.53× | — | — | REJECT |
| " | D.trail1atr | −9.11 | −8.67 | 0.37 | −$1,839 | 0.92× | — | — | REJECT |
| `trend.ret_30.q80` MNQ | time30b (diagnostic) | +3.56 | −4.44 | 0.91 | — | — | — | — | REJECT |
| Other 4 candidates | not run | — | — | — | — | — | — | — | **REJECT at the entry gate** |

### The brief's six questions

1. **Which exit is best for each family?** Only one family had an entry worth exiting. For it,
   the best exit is the one it already has — a one-bar hold.
2. **Good entries, bad exits?** **None.** The only entry with information already has the
   matching exit.
3. **Bad entries that cannot be rescued?** Five of six: `revert.vwap.q90` NQ (0/7 horizons),
   `breakout.range_expansion.q80` MNQ (0/7), and the three MARGINALs whose only hit is at a
   horizon their mechanism does not hold for.
4. **Which exits reduce drawdown without destroying expectancy?** The tight-stop A cells cut
   drawdown (−$188 → −$154 at stop 0.75/target 0.75) but take expectancy negative. None does
   both.
5. **Which exits survive slippage?** Only the baseline, and only to 1.00 tick OOS.
6. **Which produce robust plateaus?** **None.** The one in-sample plateau inverts out of
   sample.

---

## 11. Phase 16 — the answer that controls the next direction

**A) BAD ENTRIES.**

Five of six candidates carry no measurable forward information against a matched control. The
sixth is borderline: it clears one control formulation at 99.0% and another at 93.0%, on 343
trades, with an effect that decays by bar 10 and is worth $0.50/trade out of sample.

The MFE/MAE evidence is the structural reason and it is uniform across the field: excursion
ratios of 0.97–1.14 mean these signals produce **symmetric** favourable and adverse movement.
There is no asymmetry for a stop or a target to harvest. That is consistent with the previous
phase's finding that intraday index sessions displace *less* than a random walk (median
`eff_vol` 0.655–0.738).

**Per the brief: stop optimising exits.** The constraint is not exit structure.

---

## 12. Failed and surviving architectures

**Failed** — every architecture except one, and the reasons differ:

- **Trailing stops and break-even** (4 cells): worst in the grid, as preregistered. A decaying
  edge gives back everything a trail waits for.
- **Structural stops** (5 cells): worst win rates in the field (19–23%). The signal bar's
  extreme is too close on a one-bar mechanism.
- **ATR stop × target** (25 cells): the in-sample plateau inverts out of sample.
- **Time stops beyond 5 bars** (4 cells): capture noise, not edge — consistent with the entry
  decaying by bar 10.

**Surviving:** `F.baseline_invalidation` (≡ `E.time1b`), which is what the strategy already
does. It survives in the sense of being positive in both halves and beating a random
stop/target control at 95.5% — and it is still not tradable, because 1.00 tick of OOS
slippage takes it to zero.

---

## 13. Recommended next phase

1. **Do not run more exit research on this library.** Phase 16's answer is bad entries. Exit
   architecture is not the constraint and 41 architectures on the best available entry
   produced a −0.002 correlation.
2. **The next question is entry generation, not entry tuning.** Every mechanism here is built
   from 19 features on 1-minute bars of two index complexes. The MFE/MAE symmetry says that
   feature set does not produce asymmetric excursion at any horizon tested.
3. **`breakout.failed_reversal` deserves one specific follow-up, not optimisation:** it is the
   only mechanism with a real (if weak) 1-bar effect and zero DLL breaches. The useful test is
   whether the *same rule* shows the same 1–5 bar effect on **different instruments or a
   longer history** — a replication question, not a parameter question. It currently has 343
   trades over 251 sessions.
4. **The engineering gates remain worth building in parallel** — they are prerequisites
   regardless of which strategy eventually qualifies.

---

## 14. Reproducibility

```bash
python scripts/exit_entry_information.py       # Phases 1, 4, 16 - the gate, ~40 min
python scripts/exit_architecture_research.py   # Phases 2,3,5,6,9,10 - the grid, ~35 min
python scripts/exit_controls_economics.py      # Phases 7,8,11,15 - controls & plots, ~50 min
python -m pytest tests/test_exits.py -q
```

Seeds: 20260914 (entry controls), 70707 (exit controls), 1234+size (twin). Deterministic.

**Artifacts:** `research/exit_entry_information.csv`, `exit_entry_gate.json`,
`exit_grid.csv`, `exit_slippage.csv`, `exit_controls.csv`, `exit_topstep.csv`;
`docs/research/strategy_results/exit/*.png`.

---

## 15. Data coverage

| store | span | sessions | trades analysed |
|---|---|---|---|
| `data/futures/MNQ` | 2025-09-08 … 2026-09-10 | 251 | 343 (passing candidate) |
| `data/futures/NQ` | 2025-06-09 … 2026-09-10 | 312 | 2,118 (`revert.vwap.q90`) |

Window 09:30–16:00 ET. `scripts/futures_discover.py:53` still defaults to a 15:45 close and is
still wrong; overridden locally in every module here.

**Power note:** 343 trades split 60/40 leaves 104 out-of-sample trades. At that size the
standard error on $/trade is roughly $2.30, so the OOS estimate of +$0.50 is not distinguishable
from zero. Stated rather than glossed.

---

## 16. Provenance

**Git:** HEAD `4141e88` = `origin/main`. No commit, no push, no pull, no fetch.

**Config:** `dry_run=True`, `live_trading_enabled=False`, `execution_enabled=False`,
`order_transmission_enabled=False` — verified at completion.

**Network:** zero. No ProjectX call, no order-placement endpoint in any module.

**Secrets:** `live/secrets.env` untouched.

**Entry parameters frozen throughout (Phase 14).** No entry threshold, quantile or feature was
modified. The one entry-side observation worth recording as a *separate future hypothesis*:
`added.donchian_breakout` produces numerically identical results to
`breakout.opening_range.q95` — the Donchian implementation added in the previous phase reuses
the same feature at the same quantile and is not a distinct mechanism. Logged, not silently
fixed.
