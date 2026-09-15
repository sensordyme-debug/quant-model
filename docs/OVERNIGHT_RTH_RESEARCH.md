# Overnight → RTH Information Discovery

**Research question.** Can information generated during the overnight session create a
predictable, cost-resilient, Combine-compatible edge during the tradable regular session?

**Answer.** Partly, and not the useful part. Overnight information predicts regular-session
**volatility** strongly, consistently, and on every instrument (r ≈ 0.32–0.44, t = 5.6–7.7,
survives Bonferroni over 46 tests). It predicts regular-session **direction** not at all —
out-of-sample R² is *negative* on all four instruments, and no time-of-day block, no
volatility regime, and no cross-market pairing rescues it. The one construction that turned
the volatility finding into a Combine improvement failed its matched-exposure control: it was
trading less, not knowing more.

Date: 2026-09-14 · No commits, no pushes, no network calls, no credentials touched.

---

## 1. What was actually run

| Module | What it establishes |
|---|---|
| `scripts/overnight_panel.py` | Builds the one-row-per-trade-date panel. 1,126 rows across ES/NQ/MES/MNQ. |
| `scripts/overnight_replicate.py` | Remeasures the decomposition on the full eligible window; replicates on 2,662 days of SPY/QQQ. |
| `scripts/overnight_confound.py` | Tests whether the futures result is about futures or about the calendar. |
| `scripts/overnight_hypotheses.py` | Ten preregistered signed hypotheses, 46 tests, Bonferroni. |
| `scripts/overnight_incremental.py` | Causal walk-forward: does overnight add to *yesterday*? |
| `scripts/overnight_combine.py` | Real intraday paths through the repo's `TopstepTwin`, intraday MLL armed. |
| `scripts/overnight_gate_control.py` | The matched-exposure control that killed the best-looking result. |
| `scripts/overnight_timeofday.py` | Session blocks and causal volatility regimes. |
| `tests/test_overnight_panel.py` | 23 regression tests pinning both the finding and the nulls. |

Artifacts: `research/overnight_panel.parquet`, `research/etf_overnight_panel.parquet`,
`research/overnight_hypotheses.csv`, `research/overnight_combine.csv`.

---

## 2. A correction to the previous report

`docs/RESEARCH_DISCOVERY_REPORT.md` stated that the regular session **drifted negative on all
four instruments**. That is wrong, and the reason it is wrong matters more than the number.

It was measured on a 09:30–15:45 window. The Topstep mandatory flat is **15:10 CT = 16:10
ET** (`quant_brain/markets/futures_cme/topstep.py:223`), so 15:45–16:00 ET was eligible
trading time that the measurement discarded — and it is the heaviest quarter-hour of the
session.

Remeasured on 09:30–16:00:

| | ES | NQ | MES | MNQ |
|---|---|---|---|---|
| RTH mean %/session | **+0.0099** | **+0.0071** | **+0.0007** | **+0.0028** |
| t | 0.29 | 0.15 | 0.02 | 0.05 |

Positive on all four, and indistinguishable from zero on all four. For completeness, even on
the *old* 15:45 window only MNQ was negative (−0.0010%, t = −0.02) — so the original claim
did not follow from its own window either.

Nothing was tradable in either version. The correction matters because "RTH drifts negative"
invites a short, and there is no short here.

---

## 3. The decomposition, on the full eligible window

Per session, in percent. `gap` is 09:29→09:30.

| Symbol | leg | n | mean % | t | total % | Sharpe |
|---|---|---|---|---|---|---|
| ES | overnight | 312 | 0.0492 | 1.87 | 15.35 | 1.68 |
| ES | gap | 312 | −0.0022 | −0.54 | −0.67 | −0.48 |
| ES | RTH | 312 | 0.0099 | 0.29 | 3.09 | 0.26 |
| NQ | overnight | 312 | 0.0567 | 1.42 | 17.68 | 1.28 |
| NQ | RTH | 312 | 0.0071 | 0.15 | 2.21 | 0.13 |
| MES | overnight | 251 | 0.0412 | 1.35 | 10.33 | 1.36 |
| MNQ | overnight | 251 | 0.0454 | 0.97 | 11.40 | 0.97 |

**Note the t-statistics.** Even the headline overnight drift does not clear |t| > 1.96 on any
instrument in the futures store. The "discovery" was never statistically significant in the
sample it was discovered in; it looked large because it was compared against an RTH leg that
had been truncated.

---

## 4. Independent replication: SPY and QQQ, 2016–2026

Different vendor (Alpaca), different venue, different instrument class, 8.6× the history.
These are RTH-only bars, which is not a limitation for this question: the overnight return
*is* the close-to-open gap.

| Symbol | leg | n | mean % | t | Sharpe |
|---|---|---|---|---|---|
| SPY | overnight | 2,662 | 0.0331 | **2.49** | 0.77 |
| SPY | RTH | 2,662 | 0.0226 | 1.39 | 0.43 |
| SPY | buy & hold | 2,662 | 0.0555 | 2.70 | **0.83** |
| QQQ | overnight | 2,659 | 0.0468 | **2.92** | 0.90 |
| QQQ | RTH | 2,659 | 0.0329 | 1.54 | 0.47 |
| QQQ | buy & hold | 2,659 | 0.0793 | 3.04 | **0.94** |

The phenomenon replicates: overnight drift is real and significant over ten years, and the
overnight leg out-earns the RTH leg per unit of time. This is consistent with the published
literature (Cliff/Cooper/Gulen; Lou/Polk/Skouras).

**But the Sharpe column is the one that decides it.** Overnight-only is *worse* risk-adjusted
than simply holding all day, on both ETFs, over the full sample.

---

## 5. Beta, not alpha — and the futures sample is a calendar artifact

| Symbol | period | share of B&H return | Sharpe ON / Sharpe B&H |
|---|---|---|---|
| SPY | 2016-01 … 2026-09 | 59.7% | **0.92** |
| QQQ | 2016-01 … 2026-09 | 59.0% | **0.96** |
| SPY | 2025-06 … 2026-09 *(futures dates)* | — | **1.40** |
| QQQ | 2025-06 … 2026-09 *(futures dates)* | — | **1.50** |
| ES | 2025-06 … 2026-09 | 86.4% | 1.44 |
| NQ | 2025-06 … 2026-09 | 93.9% | 1.53 |
| MES | 2025-09 … 2026-09 | 97.2% | 1.62 |
| MNQ | 2025-09 … 2026-09 | 100.3% | 1.64 |

Restricted to the futures store's own 313 dates, SPY gives 1.40 and QQQ 1.50 — the same
values the futures show. **The apparent superiority over buy-and-hold belongs to the
calendar, not to futures and not to the overnight session.**

Against SPY's own rolling history (every 312-session block since 2016, n = 2,350):

- The ES value of 1.44 sits at the **68th percentile** — unremarkable.
- **63.3%** of all 312-day windows show overnight beating buy-and-hold risk-adjusted.
- Only **30.9%** of 312-day windows show the overnight mean itself clearing |t| > 1.96.

The bootstrap confidence interval on the Sharpe ratio-of-ratios at n = 312 is **[−6.15,
9.01]** for ES. The quantity is not estimable at this sample size. Even at n = 2,662 the SPY
interval is [0.27, 2.09].

**Conclusion:** the overnight drift is market beta on a schedule. It captures ~60% of the
index's return over a full cycle while taking most of its risk, and it does not improve on
buy-and-hold. There is no alpha in *holding* the overnight session.

---

## 6. Ten preregistered hypotheses

Signed predictions, fixed in `scripts/overnight_hypotheses.py` before running. 46 tests,
Bonferroni threshold **|t| > 3.40**.

| | Hypothesis | Predicted | Result |
|---|---|---|---|
| A | Overnight return continues into RTH | + | **rejected** (ETF r = −0.047) |
| B | Overnight return reverses in RTH | − | nominal only, r = −0.047, t = −2.4; R² = 0.2% |
| C | Overnight range → RTH range | + | **PASSES**, r = 0.35–0.40, t = 5.8–7.7, all four |
| D | Overnight close location → first 30m | + | **wrong sign**, all four |
| E | The gap fills | − | **wrong sign** (futures continue, r = +0.06…+0.12) |
| F | One-way overnight → trending RTH | + | **wrong sign**, all four |
| G | Overnight volume → RTH range | + | **PASSES**, r = 0.32–0.44, t = 5.6–7.3, all four |
| H | Large overnight excursion reverses | − | null (r ≈ −0.02…−0.05) |
| I | Open outside overnight range continues | + | **wrong sign**, all four |
| J | NQ overnight → ES RTH | + | null (r ≈ +0.02…+0.04) |

Survivors: **8 of 46 tests, all of them C or G, all of them volatility, none of them
direction.**

12 tests cleared a naive |t| > 1.96 with the right sign against 1.2 expected by chance — but
8 of those 12 are C and G, and the remaining 4 do not survive correction.

Note that A and B are exact negations and were both registered deliberately, so one of them
was always going to read "wrong sign". The measured direction is weak reversal, worth 0.2% of
variance.

---

## 7. Does overnight add anything to *yesterday*?

The volatility finding is only interesting if the overnight session is an information source
rather than a thermometer reading the same weather as yesterday's close. Tested by expanding-
window, strictly causal, one-step-ahead forecasting.

**Target: today's RTH range**

| Symbol | n OOS | R² from prev-day | R² adding overnight | incremental | t(β_overnight) |
|---|---|---|---|---|---|
| ES | 223 | 0.135 | 0.198 | **+0.046** | 2.47 |
| NQ | 223 | 0.154 | 0.207 | **+0.042** | 2.60 |
| MES | 162 | 0.100 | 0.148 | +0.077 | 1.48 |
| MNQ | 162 | 0.094 | 0.124 | +0.038 | 1.12 |

Real but modest, and strongest where the sample is largest.

**Target: today's RTH return (direction)**

| Symbol | n OOS | out-of-sample R² |
|---|---|---|
| ES | 251 | **−0.050** |
| NQ | 251 | **−0.031** |
| MES | 190 | **−0.100** |
| MNQ | 190 | **−0.071** |

Negative on all four. Using the full overnight feature set to forecast direction is worse
than assuming the historical average. This is what an honest fit looks like when the true
coefficients are zero.

---

## 8. Time of day

Session cut into seven blocks, all ending at or before 16:00 ET, all inside the flatten.
28 cells, Bonferroni |t| > 3.1.

**Unconditional drift by block:** largest |t| is 1.8 (MES, 15:10–16:00). **Zero cells clear
the bar.** No part of the regular session drifts reliably in either direction.

**Overnight return → block return:** **zero of 28 cells clear the bar.** The largest are
MNQ/NQ 13:00–14:00 at t = 2.3 and a *negative* ES/MES 11:00–12:00 at t = −2.6…−2.8, which
have opposite signs and no mechanism.

**Overnight range → block |return|:** significant in **every one of the 28 cells**, t = 2.6
to 7.3. Strongest at the open (ES r = 0.381, t = 7.3) and — notably — also strong in the
15:10–16:00 block the earlier research discarded (ES r = 0.294, t = 5.4).

The volatility finding is not an opening-auction artifact. It is a property of the whole
session.

---

## 9. Volatility regimes

Trailing 20-day realised volatility, terciles from an expanding causal quantile.

**The volatility finding is robust:** positive in all 11 estimable regime cells (one cell had
n = 22), t up to 6.3. Weakest in LOW regimes, which is expected — there is less variation to
predict.

**The directional finding flips sign across regimes on all four instruments:**

| Symbol | LOW | MID | HIGH | signs |
|---|---|---|---|---|
| ES | +0.162 | +0.181 | −0.171 | **disagree** |
| NQ | +0.333 | +0.058 | −0.039 | **disagree** |
| MES | +0.335 | −0.101 | — | **disagree** |
| MNQ | +0.258 | −0.030 | +0.112 | **disagree** |

A sign flip across regimes with no mechanism is the signature of noise, not of regime
dependence.

### Does gross edge outgrow cost as volatility rises?

The brief asked this directly. It does — and it does not matter, because cost was never the
constraint:

| Symbol | regime | median \|RTH move\| | round turn | ratio | break-even hit rate |
|---|---|---|---|---|---|
| ES | HIGH | $1,412 | $3.78 | 374 | **50.1%** |
| MES | HIGH | $109 | $1.22 | 90 | **50.6%** |
| MNQ | HIGH | $363 | $1.22 | 298 | **50.2%** |
| NQ | HIGH | $3,175 | $3.78 | 840 | **50.1%** |

At a full-session horizon the break-even hit rate is **50.1%–50.6% in every regime**. A
single round turn against a whole-session move is economically negligible. **The binding
constraint on this research programme is not execution cost. It is the complete absence of
directional information.**

---

## 10. Through the actual Combine

Real minute-by-minute equity paths, the repository's own `TopstepTwin`, `strict_path=True` so
the intraday MLL test cannot be silently skipped. $50K account, $3,000 target, $2,000 trailing
MLL, 120 sessions, 400 block-bootstrapped paths per cell (blocks of 20, to preserve volatility
clustering). Round turns charged.

Best cells, of 32 tested:

| Symbol | leg | contracts | Combine pass rate |
|---|---|---|---|
| MES | overnight | 2 | 48.0% |
| MNQ | overnight | 1 | 40.8% |
| MES | overnight | 1 | 25.2% |
| MNQ | rth | 2 | 25.5% |
| ES | overnight | 2 | 22.8% |
| NQ | rth | 5 | 5.0% |

*Breach rate* in `research/overnight_combine.csv` is lifetime, including the Express Funded
phase that starts at $0 balance against the same $2,000 MLL — which is why it exceeds the
Combine failure rate. Many paths pass the Combine and then die in the XFA.

No construction is remotely reliable. The sizing sweep shows the expected tension: small size
survives but rarely reaches $3,000 inside 120 sessions; large size reaches it fast or dies
fast, with the median minimum buffer pinned at the full $2,000 (i.e. the account was
liquidated) at 5+ contracts almost everywhere.

---

## 11. The one construction that used the finding — and its control

The range forecast cannot pick direction, so the only thing it can do is pick *when* to take
the beta. Gate: take the RTH long only when the overnight range sits in the lowest tercile of
a **trailing** expanding quantile — decided at 09:29, no future information.

Raw result, MES at 5 contracts: **16.8% → 45.8%** pass rate. The best-looking number in the
study.

**It does not survive its control.** The gate selects 48 of 251 sessions, so it does two
things at once: it picks days by a criterion, *and* it is flat 81% of the time. A strategy
that is flat cannot breach a trailing drawdown. Against 60 random gates of **identical size**:

| Symbol | size | gate | k | gate pass | random median | random p5–p95 | percentile | verdict |
|---|---|---|---|---|---|---|---|---|
| MES | 5 | quiet | 48 | 36.3% | 22.1% | [2.5%, 43.3%] | 83.3% | inside the band |
| MES | 5 | loud | 143 | 20.0% | 21.7% | [13.3%, 32.7%] | 35.0% | inside the band |
| MES | 10 | quiet | 48 | 23.3% | 16.2% | [4.1%, 30.9%] | 70.0% | inside the band |
| MES | 10 | loud | 143 | 16.7% | 15.8% | [9.9%, 24.2%] | 56.7% | inside the band |
| MNQ | 5 | quiet | 34 | 29.0% | 17.9% | [2.5%, 39.6%] | 76.7% | inside the band |
| MNQ | 5 | loud | 157 | 19.3% | 20.0% | [11.6%, 27.6%] | 45.0% | inside the band |
| MNQ | 10 | quiet | 34 | 8.0% | 10.4% | [0.8%, 28.3%] | 45.0% | inside the band |
| MNQ | 10 | loud | 157 | 15.7% | 11.2% | [6.7%, 18.5%] | 80.0% | inside the band |

**Every cell is indistinguishable from picking the same number of days at random.** The
quiet-day gate is not a signal; it is a reduction in exposure with a story attached.

Two further tells. The loud-day gate should be correspondingly *worse* if the split carried
information — it is not, sitting at the 35th–80th percentile. And the gate's own point
estimate moved from 45.8% to 36.3% purely from changing the bootstrap seed, which is itself
evidence that the quantity is not estimable at n = 251.

**If you want the benefit, the honest instruction is "trade less", not "use this signal".**

---

## 12. Research failure analysis

Why did the directional hypotheses fail? Ranked by what the evidence supports.

1. **There is probably nothing there at this horizon.** Eight independent framings of
   "overnight tells you which way the day goes" — continuation, reversal, gap fill, close
   location, persistence, excursion, breakout, cross-market — all fail, and they fail with
   *inconsistent signs* across instruments and regimes. A real effect that weak would still
   agree with itself.

2. **Statistical power is genuinely inadequate on the futures store.** At n = 312 the
   smallest detectable correlation is 0.111; at n = 251 it is 0.124. The measured directional
   correlations are 0.02–0.12. Several are *not distinguishable from* an economically
   interesting effect — the confidence intervals include ±0.11. This is the one caveat that a
   larger sample could overturn, and it is why the ETF replication (n = 2,662, MDC = 0.038)
   matters: there the effect is pinned at −0.047 with a tight interval, and it is too small to
   trade.

3. **The efficient-markets prior is doing real work here.** The overnight→open relationship is
   the single most-studied intraday pattern in equities. If a simple version worked, it would
   not still be simple.

4. **What did *not* cause the failure:** execution cost (break-even is 50.1–50.6%), the
   window definition (fixed, and the wider window is now used throughout), and roll
   contamination (mixed-contract dates are dropped, not stitched).

### Second-generation hypotheses this suggests

Registered as *result-driven* under `quant_brain/research/genealogy.py` conventions — each
costs an extra trial against the multiplicity bar because each was written after seeing a
result.

- The 15:10–16:00 block carries the heaviest volume and the strongest range predictability
  outside the open, and was never examined before. Settlement-flow mechanisms deserve a look
  **on their own terms**, not as an overnight-conditioned trade.
- Volatility is forecastable at incremental R² ≈ 0.04–0.08 beyond yesterday. That is a
  **position-sizing** input, not a return input. The correct test is whether volatility-scaled
  sizing beats fixed sizing *at matched average exposure* — the control that the gate failed.
- The ETF panel (2,662 sessions) has 8.6× the power of the futures panel and is free. Any
  future directional hypothesis should be screened there **first** and only then confirmed on
  futures, rather than the reverse.

---

## 13. Extending the history without purchasing

| Source | Coverage | Status |
|---|---|---|
| ProjectX/TopstepX `retrieveBars` | ES/NQ from 2025-06, MES/MNQ from 2025-09 | **This is the floor.** ~313 and ~252 clean trade dates. Read-only client exists; no call was made this session. |
| **`data/minute_alpaca/SPY.parquet`, `QQQ.parquet`** | **2016-01-04 → 2026-09-10, 2,687 days** | **Already in the repo, already used.** Free, SIP minute bars. RTH-only, which is sufficient for close-to-open work. |
| `data/minute_alpaca/TQQQ, SQQQ` | same span | Leveraged proxies; not used — decay makes the return decomposition misleading. |
| Alpaca minute history generally | 2016+ | Free tier already provisioned (see memory: data-sources). Could add sector ETFs for cross-market work. |

**Recommendation: stop treating the futures store as the primary research sample.** It is
fifteen months, it is not significant on its own headline result, and it produced a Sharpe
ratio-of-ratios with a confidence interval spanning [−6.15, 9.01]. The SPY/QQQ store is
already local, already free, and has 8.6× the power. Futures data should be used for what only
it can answer — contract-specific microstructure, the actual tick sizes and costs, the real
overnight *path* — and not for screening directional hypotheses.

No purchase is required to make the next round of this research substantially better powered.

---

## 14. Parallel research branches

Status after this session. None of these were closed by this work; the overnight branch was.

| Branch | Status | Next concrete step |
|---|---|---|
| Overnight → RTH direction | **CLOSED — negative.** 8 hypotheses, 46 tests, OOS R² < 0 | Do not re-test without a new mechanism or a much larger sample. |
| Overnight → RTH volatility | **OPEN — positive but not yet useful.** Incremental R² 0.04–0.08 | Test volatility-scaled *sizing* at matched exposure. |
| Cross-market lead/lag (ES↔NQ) | Weakly tested (H-J only, r ≈ 0.02) | Needs intraday lead/lag at sub-session resolution, not daily. |
| Session transitions / settlement flow | **Newly opened.** 15:10–16:00 is the heaviest block and was previously discarded | Characterise it directly before hypothesising. |
| Failed breakout | Untested | Hypothesis I's wrong sign is a hint worth following. |
| Event-driven | Untested | `data/events` exists; not examined this session. |
| Institutional-flow proxies | Untested | `data/auctions` exists; not examined. |
| ML regime classification | Untested | Premature — nothing to classify *into* until a directional signal exists. |

---

## 15. What would change the conclusion

Stated in advance, so that a future positive result can be checked against it rather than
rationalised:

- A directional correlation above **0.11** on the futures panel, or above **0.038** on the ETF
  panel, with a **consistent sign** across instruments and across volatility regimes.
- A gated construction that beats its **matched-exposure random control** at the 95th
  percentile — not one that merely beats always-on.
- An out-of-sample R² for direction that is **positive**, under the same causal expanding-
  window protocol used here.

None of these was observed.

---

## 16. Safety and compliance

- **No orders. No network calls to ProjectX.** The read-only client was not invoked this
  session; all data came from local parquet stores.
- **Flags unchanged and verified:** `DRY_RUN=true`, `LIVE_TRADING_ENABLED=false`,
  `EXECUTION_ENABLED=false`, `ORDER_TRANSMISSION_ENABLED=false`.
- **`live/secrets.env` untouched.** No credential read, printed, or logged.
- **No git commit, no push, no pull, no fetch.** All work is left in the working tree for
  human review, per the standing instruction that Git automation is to be treated as hostile.
- **No data deleted.** The panel files are additions; no existing dataset was modified or
  removed.
- **Full suite green**, plus 23 new regression tests in `tests/test_overnight_panel.py` that
  pin the nulls as firmly as the positive result.
