# Options track journal (O-)

Newest first. The `options` scope: the Theta store, `scripts/odte_*`, `scripts/theta_data.py`,
`scripts/sweep_o*`. Evidence only - this track has never had, and does not ask for, a deployment.

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
