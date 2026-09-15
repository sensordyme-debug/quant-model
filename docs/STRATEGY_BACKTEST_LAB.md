# Strategy Backtest & Selection Lab

**Objective.** Backtest the existing strategy library through one interface, understand where
each mechanism works and fails, and identify whether any can survive Topstep-specific
validation.

**Result: no strategy is ready to paper-trade.** 132 strategy×instrument cells. **130 REJECT,
1 RESEARCH, 1 WATCH, 0 PAPER CANDIDATE, 0 COMBINE CANDIDATE.**

Date: 2026-09-14 · Research only · No commits, no pushes, no ProjectX calls, nothing connected.

Dashboard: `docs/research/strategy_results/index.html` · Scorecards:
[STRATEGY_SCORECARDS.md](STRATEGY_SCORECARDS.md)

---

## 1. Executive conclusion

**The binding constraint is not profitability. It is the barrier.**

Topstep's trailing maximum loss limit is $2,000, tested intraday on unrealised P&L. Measured
at **one contract** — the smallest position it is possible to hold:

| | |
|---|---|
| cells whose own max drawdown fits inside $2,000 | **8 of 132** |
| median drawdown ÷ MLL | **7.9×** |
| ratio for the highest-net cell | **20.0×** |

Sizing down does not fix this. Halving the position halves the drawdown *and* halves the edge,
while the round-turn cost stays where it is — and with a **2-minute median holding time**,
cost is already most of the arithmetic.

Two further facts close the case:

- **0 of 132 cells have `t > 1.96` on the daily series with positive net P&L.** 81 cells *are*
  significant — they are the reliably losing ones.
- **One tick of round-turn slippage halves the survivors**, 12 positive cells → 6.

The Monte Carlo probability of a drawdown exceeding the MLL is **100.0%** for every ES and NQ
cell tested, at every contract count.

---

## 2. Phase 1 — the authoritative registry

Built by importing and instantiating every strategy, not by reading documentation
(`scripts/strategy_registry.py` → `research/strategy_registry.json`).

**33 strategies constructed:** trend 9, breakout 6, reversion 5, session 4, volatility 3,
volume 3, **added 3**.

### The brief's named list, audited against the code

| named | maps to | status |
|---|---|---|
| ORB | `breakout.opening_range.*` | present |
| VWAP reversion | `revert.vwap.*` | present |
| Z-score reversion | `revert.z_60.*` | present |
| Failed breakout | `breakout.failed_reversal` | present |
| EMA trend | `trend.ma_agree.30_120` | **partial** — simple MA distance, not exponential |
| ATR volatility breakout | `vol.expansion_trend` | **partial** — gates on realised-vol expansion, not an ATR band break |
| **Donchian breakout** | `added.donchian_breakout` | **ABSENT** — added by this phase |
| **Bollinger reversion** | `added.bollinger_revert.2sd` | **ABSENT** — added by this phase |
| **VWAP trend** | `added.vwap_trend` | **ABSENT** — added by this phase |

Donchian, Bollinger and Keltner exist in the repo only under `Quant Brain/`, an equities
archive with its own engine and no path into the futures lab.

Three canonical mechanisms were added with **textbook parameters declared before any result**
(Donchian at the 95th-percentile channel with a 20-bar warm-up; Bollinger at exactly 2.0σ,
uncalibrated; VWAP trend gated at median relative volume). They are flagged `newly_added` in
every artifact and cost three extra trials, disclosed rather than absorbed.

### The structural gap that shapes everything downstream

**No strategy in this library has a stop, a target, or any exit rule.** All 33 are stateless
per-bar signals mapping features → position in {−1, 0, +1}. A position ends when the signal
changes or the session does.

Consequences, reported rather than hidden:

1. Exit reasons have only three categories — measured at **80.3% `signal_flat`, 16.2%
   `signal_flip`, 3.5% `forced_flatten`**.
2. **The R multiple has no stop-based denominator.** It is computed against the entry
   session's ATR and labelled as such everywhere. It is not a stop-based R.
3. MAE describes how much pain each mechanism *asks* you to take, not how much it was allowed
   to.

Brackets would fix all three and add two parameters per strategy — a Phase 9 question for
survivors, not a baseline.

---

## 3. Phase 2 — the standardised interface

`quant_brain/research/strategy_lab.py`. Every strategy runs through one function, on the same
sessions, with the same cost model, window and flatten rule. No strategy reports its own
numbers its own way.

**Trade level:** entry/exit timestamp and price, direction, contracts, gross, commission,
slippage, net, R multiple, MAE, MFE, exit reason, holding minutes.
**Session level:** P&L, trade count, max intraday drawdown, MFE/MAE, end position, forced-flatten
flag, time in market, full equity path.
**Portfolio level:** net, expectancy per trade and per session, win rate, average win/loss,
payoff, profit factor, max drawdown and duration, Sharpe, Sortino, t, consecutive losing days,
exposure, trades/session, median hold, exit mix, by-year and by-month.

Two deliberate choices:

- **One round turn per completed trade, charged at exit.** A direct long→short reversal is
  *two* round turns because it is two trades — charging one would understate cost by half on
  any mechanism that flips rather than stands down, which is most of this library. Unit-tested.
- **Undefined metrics return a sentinel, not a flattering default.** A cell with no losing
  trade gets `NaN` profit factor, not `inf`, because `inf` beside a real 1.13 corrupts a
  ranking.

---

## 4. Phases 3–4 — the baseline tournament

Canonical parameters, one contract, 09:30–16:00 ET, **132 cells** (33 × 4 instruments),
**458,110 trades**. Two cost regimes:

| | positive net P&L | positive $/trade | t > 1.96 **and** net > 0 |
|---|---|---|---|
| **normal** (commission only) | 12 / 132 | 12 / 132 | **0** |
| **stressed** (+1 tick round turn) | 6 / 132 | 6 / 132 | **0** |

One tick erases half the survivors. On these contracts a tick is $12.50 (ES), $5.00 (NQ),
$1.25 (MES), $0.50 (MNQ) — not a rounding adjustment.

Best cells by net, normal regime:

| strategy | sym | trades | net $ | $/trade | PF | win% | max DD $ | t |
|---|---|---|---|---|---|---|---|---|
| revert.vwap.q90 | NQ | 2,118 | 52,379 | 24.73 | 1.13 | 80.9% | **−39,960** | 1.10 |
| revert.vwap.q95 | NQ | 1,246 | 27,675 | 22.21 | 1.11 | 79.5% | −25,508 | 0.69 |
| session.midday_reversion | NQ | 2,229 | 13,404 | 6.01 | 1.06 | 67.5% | −13,477 | 0.75 |
| added.bollinger_revert.2sd | NQ | 3,841 | 13,301 | 3.46 | 1.03 | 66.1% | −14,784 | 0.55 |

Read the drawdown column against a $2,000 barrier. The leader breathes **20× the limit**.

---

## 5. Phase 5 — the plots that explain why

`docs/research/strategy_results/`. Five charts, chosen because they explain the failure; the
brief's other twelve would have been decoration for a field with one dominant failure mode.

| file | what it settles |
|---|---|
| `01_drawdown_vs_mll.png` | **the decisive chart** — every cell's drawdown against the barrier |
| `02_cost_cliff.png` | $/trade at 0 vs 1 tick; where the remaining edge goes |
| `03_equity_underwater.png` | the leaders' ride, with the $2,000 line drawn on the drawdown panel |
| `04_trade_anatomy.png` | holding time, MAE, MFE — what these mechanisms *are* |
| `05_regime.png` | net P&L by year and by causal trailing-volatility tercile |

Per-hour and per-weekday P&L are computed into the scorecards as numbers but not plotted: 132
cells would be 132 charts nobody reads.

---

## 6. Phases 6–7 — scorecards and the verdict ladder

The ladder was **declared before the data was read** and is applied mechanically
(`scripts/strategy_lab_report.py:verdict`):

| verdict | condition |
|---|---|
| **REJECT** | 1-contract max drawdown ≥ $2,000 **or** negative stressed expectancy |
| **WATCH** | survives both, but \|t\| < 1.0 — not evidence, just not yet disproved |
| **RESEARCH** | survives both, \|t\| ≥ 1.0, fails a robustness leg |
| **PAPER CANDIDATE** | + t ≥ 1.96 and Monte Carlo P[drawdown > MLL] < 50% |
| **COMBINE CANDIDATE** | + engineering and practice gates — **unreachable from a backtest by construction** |

A regression test asserts the ladder rejects profitable cells, so it cannot silently collapse
into a P&L ranking.

**Result: 130 REJECT · 1 RESEARCH · 1 WATCH · 0 PAPER · 0 COMBINE.**

Full per-strategy pros, cons and falsification conditions:
[STRATEGY_SCORECARDS.md](STRATEGY_SCORECARDS.md).

---

## 7. Phase 8 — ranking, not by P&L

Composite score: barrier compatibility (×3), stressed expectancy (×3), evidence (t, capped),
daily-limit behaviour, profit factor.

| # | strategy | sym | score | DD/MLL | stressed $/tr | t | DLL/session | verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | breakout.failed_reversal | MNQ | 8.71 | **0.09×** | +0.95 | 1.11 | **0.0%** | RESEARCH |
| 2 | revert.vwap.q95 | MNQ | 8.35 | 0.90× | +3.17 | 0.78 | 1.6% | WATCH |
| 3 | revert.vwap.q90 | NQ | 5.25 | 20.0× | +19.73 | 1.10 | 41.6% | REJECT |
| 4 | session.midday_reversion | NQ | 5.06 | 6.7× | +1.01 | 0.75 | 21.6% | REJECT |

**Note rows 1 and 3.** The NQ cell earns twenty times more per trade and is rejected; the MNQ
cell earns $0.95 and ranks first. That inversion is the ladder working — the NQ cell breaches
the MLL on its own history and trips the daily loss limit on **41.6% of sessions**.

**Nothing proceeds to Phases 9–10 (parameter optimisation).** The brief says only top
candidates optimise. The top candidate has t = 1.11 on 343 trades; tuning parameters against a
sample that cannot distinguish it from zero would manufacture exactly the result the brief
forbids. Optimisation is gated on evidence that does not exist.

---

## 8. Phase 12 — Monte Carlo, with the precondition discharged

The brief forbids relying on the existing path-reconstruction logic unless independently
verified, and says to **STOP** if it is still suspect. It was verified first, with property
checks written against the machinery rather than against the existing suite's framing:

- iid resampling preserves session-P&L mean and standard deviation, and emits only real
  session P&Ls
- `_shifted` re-closes a session **additively**: the close lands exactly on target and no
  intraday mark moves by more than \|delta\|, tested at 0×, 1×, 5× and −1×
- the documented near-flat blow-up specifically: re-closing a $0.01 session at $1,000 does not
  scale its −$500 excursion by 100,000×
- `_lay_out` carries whole sessions with P&L *and* path byte-identical
- `_scaled_day` multiplies P&L and every mark by the same factor

One check initially failed and **the failure was mine**: a synthetic template built from
consecutive calendar days contains weekends, and `_calendar` preserves the template's own dates
while guaranteeing weekday spacing only for dates it *invents*. Clean on a realistic template.

**Precondition discharged.** These properties are now pinned in `tests/test_strategy_lab.py`
alongside the 19 in `tests/test_path_reconstruction.py`.

**Result** (2,000 iid day-reshuffles per cell): **P[max drawdown > $2,000] = 100.0%** for
every ES and NQ cell at every size tested. The minimum across the whole field is 0.0%, and it
belongs to `breakout.failed_reversal` MNQ at 1 contract — which never reaches the target.

---

## 9. Phase 13 — Topstep digital twin

Real intraday paths, `strict_path=True` so the intraday MLL test cannot be silently skipped.
$50K / $3,000 target / $2,000 trailing MLL / 120 sessions / 400 block-bootstrapped paths.

| strategy | sym | ct | pass | breach | med days | DLL/session |
|---|---|---|---|---|---|---|
| breakout.failed_reversal | MNQ | 1 | 0.0% | **0.0%** | — | **0.0%** |
| breakout.failed_reversal | MNQ | 5 | 12.5% | 3.8% | 90 | 0.0% |
| breakout.failed_reversal | MNQ | 10 | **44.2%** | 47.2% | 61 | 0.0% |
| revert.vwap.q95 | MNQ | 5 | 42.0% | 98.0% | 17 | 12.9% |
| revert.vwap.q90 | NQ | 1 | 28.7% | 99.8% | 8 | 41.6% |
| revert.vwap.q95 | ES | 2 | 35.8% | 98.8% | 11 | 24.5% |

The size sweep shows the tension plainly: at 1 contract `breakout.failed_reversal` never
breaches and never passes; at 10 it passes 44.2% and breaches 47.2%. There is no size at which
it both reaches $3,000 and survives.

**The DLL column is the underreported one.** `revert.vwap.q90` on NQ trips the $1,000 daily
loss limit on **41.6% of sessions** — stood down two days in five, whatever its expectancy.

---

## 10. Phase 14 — are the leaders distinct mechanisms?

Spearman correlation of daily P&L among the five highest-net cells:

|  | vwap.q90 NQ | vwap.q95 NQ | midday NQ | bollinger NQ | z_60.q95 NQ |
|---|---|---|---|---|---|
| **vwap.q90 NQ** | 1.00 | 0.41 | 0.07 | 0.15 | 0.13 |
| **vwap.q95 NQ** | 0.41 | 1.00 | −0.03 | 0.09 | 0.06 |
| **midday NQ** | 0.07 | −0.03 | 1.00 | 0.48 | 0.45 |
| **bollinger NQ** | 0.15 | 0.09 | 0.48 | 1.00 | **0.81** |
| **z_60.q95 NQ** | 0.13 | 0.06 | 0.45 | 0.81 | 1.00 |

Median pairwise 0.14. The **0.81** between Bollinger and z-score is expected and important:
both fade a standardised deviation from a rolling mean, so they are one mechanism under two
names. Counting them as two diversifiers would be double-counting.

**No ensemble is built.** The brief permits ensembles only after individual strategies are
understood and only from genuinely distinct mechanisms. Combining components that are all
REJECT produces a portfolio that is REJECT.

---

## 11. Phase 15–16 — the gate, and where this stops

Nothing reaches the transition. For the record, the checklist a candidate must clear:

**Research** — [ ] positive expectancy after costs · [ ] positive OOS · [ ] walk-forward
survives · [ ] parameter plateau · [ ] regime robustness · [ ] slippage robustness ·
[ ] Monte Carlo survives

**Engineering** — [ ] fake broker · [ ] reconciliation · [ ] no duplicate orders · [ ] bracket
protection · [ ] restart/recovery · [ ] flatten verified · [ ] position limits · [ ] risk
governor

**Practice** — [ ] full Practice week · [ ] no unexplained discrepancies · [ ] fills
reconciled · [ ] no safety violations

**Human** — [ ] manual review · [ ] parameters frozen · [ ] git commit/tag · [ ] provenance
frozen · [ ] explicit approval

**Current state: 0 of 7 research boxes tickable by any strategy.** No engineering or practice
work was started, because starting it would imply a candidate exists.

---

## 12. Why each family fails

Full per-strategy detail in [STRATEGY_SCORECARDS.md](STRATEGY_SCORECARDS.md).

| family | cells | under MLL | why it fails here |
|---|---|---|---|
| **trend** (9) | 36 | **0** | Intraday index sessions displace *less* than a random walk (median eff_vol 0.66–0.74, established last phase). Trend mechanisms are paid for displacement and are fighting the asset class's arithmetic. Worst drawdowns in the field. |
| **breakout** (6) | 24 | 2 | Same displacement problem plus false-breakout cost. The one survivor, `failed_reversal`, works by *fading* breakouts — i.e. by not being a breakout strategy. |
| **reversion** (5) | 20 | **4** | The only family with real win rates (80.9% on `revert.vwap.q90`). Consistent with a mean-reverting asset class. Fails on drawdown: high win rate with a fat left tail is exactly the shape a trailing barrier punishes. |
| **session** (4) | 16 | 1 | Time-of-day drift was shown null last phase (0 of 28 blocks significant). No mechanism underneath. |
| **volatility** (3) | 12 | 0 | Forecastable volatility predicts *path*, not *displacement*. Established and re-confirmed. |
| **volume** (3) | 12 | 0 | Volume predicts magnitude, not direction — the same wall. |
| **added** (3) | 12 | 1 | Bollinger duplicates z-score (ρ = 0.81). Donchian and VWAP-trend inherit the trend family's problem. |

---

## 13. What would change the conclusion

Stated in advance so a future positive can be checked rather than rationalised:

1. A cell with **1-contract max drawdown under $2,000** *and* **t ≥ 1.96** *and* positive
   stressed expectancy. None of the 132 has two of the three.
2. A **bracketed** version of a reversion mechanism: the family has the win rate; its problem
   is the untruncated left tail. Adding a stop is the single highest-value structural change
   available and it is currently untested because no strategy has one.
3. A **path-paid** mechanism. Everything here is displacement-paid, and the asset class
   mean-reverts.

---

## 14. Recommended next work

1. **Add a bracket layer to the reversion family and re-run this lab.** Reversion has 4 of the
   8 sub-barrier cells and the only strong win rates. Its failure is drawdown shape, which is
   exactly what a stop addresses. Two parameters (stop multiple, target multiple), predeclared
   ranges — this is the legitimate Phase 9.
2. **Do not optimise anything else.** t = 1.11 on the best cell.
3. **Treat MNQ as the instrument of record.** 6 of 8 sub-barrier cells are micros; the tick is
   $0.50 against ES's $12.50, so the same mechanism has a 25× smaller cost floor.
4. **The engineering gates can be built in parallel** — fake broker, reconciliation, restart
   recovery. They are prerequisites regardless of which strategy eventually qualifies, and
   building them now costs no research integrity.

---

## 15. Reproducibility

```bash
python scripts/strategy_registry.py       # Phase 1  -> research/strategy_registry.json
python scripts/strategy_lab_run.py        # Phases 3-4, ~25 min
python scripts/strategy_lab_topstep.py    # Phases 12-13, ~30 min
python scripts/strategy_lab_report.py     # Phases 5-8, 14
python scripts/strategy_lab_dashboard.py  # Phase 17
python -m pytest tests/test_strategy_lab.py -q
```

Seeds: 4242 + contract count (twin), 909 (Monte Carlo), 0 (feature probe). Deterministic.

**Artifacts:** `research/strategy_registry.json`, `lab_portfolio.csv`, `lab_trades.parquet`
(458,110 rows), `lab_sessions.pkl`, `lab_topstep.csv`, `lab_scorecards.csv`,
`lab_ranking.csv`, `lab_correlations.csv`; `docs/research/strategy_results/*.png` and
`index.html`.

---

## 16. Data coverage

| store | span | sessions |
|---|---|---|
| `data/futures/ES,NQ` | 2025-06-09 … 2026-09-10 | 312 |
| `data/futures/MES,MNQ` | 2025-09-08 … 2026-09-10 | 251 |

Window 09:30–16:00 ET, ten minutes inside the 16:10 ET flatten. **`scripts/futures_discover.py:53`
still defaults to a 15:45 close and is still wrong**; overridden locally in every lab script
because golden fixtures pin 376 bars.

Calibration on the first 50% of sessions, frozen — matching the tournament's convention.

---

## 17. Provenance

**Git:** HEAD `4141e88` = `origin/main`. No commit, no push, no pull, no fetch. All work
uncommitted for review.

**Config:** `dry_run=True`, `live_trading_enabled=False`, `execution_enabled=False`,
`order_transmission_enabled=False` — verified at completion.

**Network:** zero. No ProjectX call, no order-placement endpoint referenced in any lab module.
The dashboard is a static local file with no network resource and no form.

**Secrets:** `live/secrets.env` untouched.

**Tests:** 18 new in `tests/test_strategy_lab.py` — trade extraction against hand-computed
arithmetic, the two-round-turns-on-reversal rule, slippage charged once per round turn, the
Monte Carlo preconditions, and three findings tests including one asserting the verdict ladder
still rejects profitable cells. Full suite green.
