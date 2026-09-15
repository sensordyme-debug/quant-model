# Combine Readiness — where we actually stand

**Goal:** a solid strategy running live on a Topstep Combine, producing payouts.

**Status: we do not have one, and I will not present one we don't have.** What we now have
that we didn't before is an exact specification of what would suffice, and a costed view of
the funnel.

Date: 2026-09-14 · No commits, no pushes, no orders, no credential access.

---

## 1. The position, stated plainly

Six research phases. ~6,400 recorded trials. Every mechanism in the library is REJECT:

| phase | what it tested | outcome |
|---|---|---|
| Overnight → RTH | 46 tests, 8 directional hypotheses | overnight drift is beta, and a calendar artifact |
| Conditional opportunity | 500 trials | volatility forecastable (R² 0.5); direction not |
| Volatility × efficiency | 4,788 window-matched tests | 0 replicate; two "findings" were leaks |
| Strategy lab | 132 cells, 458k trades | 130 REJECT, 0 paper candidates |
| Exit architecture | 41 architectures | IS↔OOS correlation −0.002 |
| Failed-reversal replication | 8 instruments, 17,776 entries | REJECT — QQQ inverts the sign on the same index |
| **Reversion discovery (this session)** | 12 preregistered variants, 4 ETFs, ~2,600 sessions each | **0 of 12 pass train selection** |

The reversion run this session is the one I'd have bet on: it targeted the single most robust
fact the programme established (intraday index sessions mean-revert, `eff_vol` 0.66–0.74) at
holding periods long enough for cost not to dominate, on the panel with 30× the power.

It found a real but insufficient edge: **best gross 0.245 bps/trade against a realistic MNQ
round-turn cost of 0.35 bps.** The edge and the cost are the same size.

An exploratory extension to 3–4σ deviations looked much better on train (+1.224 bps/trade,
Sharpe 0.82) and **inverted on validate** (−1.194 bps/trade, 0 of 4 instruments positive).
Win rates stayed high (0.56–0.62) while the losers grew — fading extremes works in
trending-up-with-dips markets and fails in the 2022 downtrend. Regime-dependent, and the
regime is not forecastable. **The holdout was not inspected and is preserved.**

---

## 2. What we learned that is genuinely new and useful

### The Combine barrier is far softer than it looks

The $2,000 trailing MLL **locks permanently at breakeven once equity reaches +$2,000**
(`topstep.py:179`). That changes the barrier problem completely. Simulated against the real
mechanics with no day limit:

| annualised Sharpe | pass probability | median sessions |
|---|---|---|
| 0.50 | 38% | 51 |
| 1.00 | 49% | 50 |
| 1.50 | 58% | 47 |
| 2.00 | 69% | 45 |
| 3.00 | 83% | 38 |

We do **not** need a Sharpe of 3. A validated Sharpe near 1.5 is a genuinely realistic target.

### The funnel is EV-positive from a surprisingly low bar — but it is a lottery

Full lifecycle through the repo's Topstep twin: $49/month, Combine → Express Funded → payout
(capped $2,000 at $50K, 90% split, MLL resets to $0 after each payout).

| Sharpe | pass | payout | **mean net $** | **median net $** | P(lose money) |
|---|---|---|---|---|---|
| 0.0 | 24.0% | 15.5% | −49 | −103 | 88.3% |
| 0.5 | 39.5% | 29.2% | +73 | −91 | 78.8% |
| 1.0 | 47.5% | 37.5% | +241 | −82 | 71.5% |
| 1.5 | 59.2% | 52.5% | +402 | −49 | 58.7% |
| 2.0 | 67.2% | 61.8% | +812 | **+7** | 49.0% |
| 3.0 | 85.0% | 81.3% | +2,296 | +408 | 29.7% |

**Break-even mean EV arrives at Sharpe ≈ 0.5. The median only turns positive near Sharpe 2.0.**
Below that you make money on average and lose money most of the time — the mean is carried by
the payout tail. That is a real fact about the product and worth understanding before funding
an account.

### Position size has an optimum, and it is not "as small as safely possible"

At Sharpe 1.0, varying per-session volatility:

| sd per session | pass | payout | mean net $ |
|---|---|---|---|
| $100 | 25.5% | 9.7% | **−496** |
| $250 | 48.0% | 38.5% | **+162** |
| $500 | 36.0% | 24.2% | +352 |
| $800 | 34.8% | 14.8% | +351 |

Trading too *small* is the worst outcome: you never reach +$2,000 to trigger the MLL lock, so
the trailing barrier follows you for months while the fee accrues. The sweet spot is roughly
**$250–500 per-session standard deviation** on a $50K account.

---

## 3. The specification

Anything proposed from here must hit this before it goes near a funded account:

| requirement | value |
|---|---|
| annualised Sharpe, **net of commission and 1 tick slippage** | **≥ 1.5** |
| per-session P&L standard deviation | **$250–500** |
| net expectancy | **≥ 0.8 bps/day** at 20 MNQ (≈ $75/session) |
| max drawdown at trading size | **< $2,000** before the lock engages |
| DLL breaches | **< 5%** of sessions |
| evidence | positive on ≥3 of 4 independent instruments in train **and** validate, before the holdout is opened |

Everything measured so far: best validated Sharpe in 132 lab cells was 1.12, and it was
falsified on replication.

---

## 4. Honest options from here

**A. Build the execution stack now.** Fake broker, reconciliation, duplicate-order prevention,
bracket protection, restart/recovery, flatten verification, risk governor. These are
prerequisites for *any* strategy and none of them depends on finding an edge. Doing this now
means that when something does validate, it can be paper-traded in days rather than weeks.
This is the only work that is unambiguously on the critical path today.

**B. Widen the data.** The binding constraint is 19 features on 1-minute bars of two index
complexes. The untested probability mass is in data the repo does not hold: order book /
tick data, or a different asset class. This is a purchasing decision, not a research one.

**C. Fund a Combine on beta and accept the odds.** At Sharpe ~0 the expected loss is the fee
(−$49). At index-beta Sharpe (~0.8 historically) the mean is positive and the median is not.
This is a real option and it is a gamble, not a strategy. I will implement it if you want it,
with the odds stated on the tin — but it is not what "solid" means.

**My recommendation: A now, B in parallel.** A is real progress toward live trading that costs
nothing in research integrity. C is available whenever you want it, and the table in §2 is
what you'd be buying.

---

## 5. What I will not do

Fit a strategy to the 251–312-session futures store and call it validated. That store has now
produced three "findings" that larger samples destroyed — the overnight drift, the failed
reversal, and the 3–4σ reversion extension in this session. Each looked convincing at the
moment of discovery.

---

## 6. Reproducibility

```bash
python scripts/reversion_discovery.py    # the preregistered 12-variant run
python scripts/combine_funnel_ev.py      # the funnel specification
```

Artifacts: `research/reversion_discovery.csv`, `research/combine_funnel_ev.csv`.
Hypotheses `REV-1` and `REV-2` registered in `research/hypotheses.jsonl` (REV-2 flagged
result-driven). 48 rows appended to the experiment ledger.

**Holdout status: ETF 2024-01 → 2026-09 remains unopened for the reversion family.**
