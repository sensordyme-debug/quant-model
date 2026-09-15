# Strategy Scorecards

Generated from `research/lab_scorecards.csv`, `lab_portfolio.csv` and `lab_topstep.csv` — never hand-edited, so it cannot drift from the data.

**132 cells.** **REJECT** 130 · **RESEARCH** 1 · **WATCH** 1

Verdict ladder is declared in `scripts/strategy_lab_report.py:verdict` and applied mechanically. `DD/MLL` is the cell's own 1-contract maximum drawdown divided by Topstep's $2,000 trailing limit; anything at or above 1.0 is structurally incompatible before any simulation runs.

---

## REVERSION  ·  20 cells, 4 inside the barrier

**Why it could work.** An extreme deviation from a rolling mean or from VWAP is an inventory imbalance rather than information, and liquidity providers are paid to correct it. This is the family the asset class's own arithmetic favours: sessions mean-revert, and the measured win rates here (up to 80.9%) are consistent with that rather than with luck.

**Why it could fail.** A high win rate with an untruncated left tail is precisely the shape a trailing drawdown barrier punishes. Fading a genuine regime change is how a reversion book dies, and no strategy here has a stop to prevent it. revert.vwap.q90 on NQ wins 80.9% of trades and still draws down $39,960.

**What would kill it.** Reject unless a bracketed version keeps its win rate above 65% AND brings 1-contract max drawdown under $2,000. Untested - no strategy has a stop.

| strategy | sym | trades | net $ | $/tr | stressed $/tr | PF | win% | max DD $ | DD/MLL | t | hold min | DLL/sess | twin pass | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `revert.vwap.q95` | MNQ | 755 | 2,771 | 3.67 | 3.17 | 1.17 | 80.8% | -1,804 | 0.9× | 0.78 | 3 | 1.6% | 42.0% | **WATCH** |
| `revert.vwap.q90` | NQ | 2,118 | 52,379 | 24.73 | 19.73 | 1.13 | 80.9% | -39,960 | 20.0× | 1.10 | 3 | 41.6% | 28.7% | **REJECT** |
| `revert.vwap.q95` | NQ | 1,246 | 27,675 | 22.21 | 17.21 | 1.11 | 79.5% | -25,508 | 12.8× | 0.69 | 3 | 26.1% | 27.0% | **REJECT** |
| `revert.vwap.q90` | MNQ | 1,299 | 1,493 | 1.15 | 0.65 | 1.05 | 81.1% | -3,662 | 1.8× | 0.35 | 3 | 2.0% | 31.2% | **REJECT** |
| `revert.z_60.q95` | MNQ | 2,594 | -81 | -0.03 | -0.53 | 1.00 | 63.6% | -1,355 | 0.7× | -0.04 | 2 | — | — | **REJECT** |
| `revert.z_calm_only` | MNQ | 1,316 | -664 | -0.50 | -1.00 | 0.95 | 61.4% | -1,404 | 0.7× | -0.52 | 2 | — | — | **REJECT** |
| `revert.vwap.q95` | MES | 648 | -557 | -0.86 | -2.11 | 0.93 | 75.9% | -1,392 | 0.7× | -0.34 | 3 | — | — | **REJECT** |
| `revert.vwap.q95` | ES | 1,233 | 10,439 | 8.47 | -4.03 | 1.09 | 75.5% | -11,601 | 5.8× | 0.53 | 3 | 16.1% | 35.8% | **REJECT** |
| `revert.z_60.q95` | NQ | 3,276 | 11,592 | 3.54 | -1.46 | 1.04 | 65.0% | -11,149 | 5.6× | 0.57 | 2 | 23.2% | 21.0% | **REJECT** |
| `revert.z_calm_only` | NQ | 1,668 | -175 | -0.10 | -5.10 | 1.00 | 63.1% | -14,657 | 7.3× | -0.01 | 2 | — | — | **REJECT** |
| `revert.vwap.q90` | ES | 2,046 | -1,071 | -0.52 | -13.02 | 0.99 | 76.7% | -20,127 | 10.1× | -0.05 | 3 | — | — | **REJECT** |
| `revert.z_60.q90` | NQ | 5,058 | -31,349 | -6.20 | -11.20 | 0.95 | 66.4% | -38,733 | 19.4× | -1.07 | 2 | — | — | **REJECT** |
| `revert.vwap.q90` | MES | 1,282 | -1,495 | -1.17 | -2.42 | 0.89 | 77.6% | -2,062 | 1.0× | -0.74 | 3 | — | — | **REJECT** |
| `revert.z_60.q90` | MNQ | 4,040 | -5,878 | -1.45 | -1.95 | 0.88 | 63.8% | -6,474 | 3.2× | -2.09 | 2 | — | — | **REJECT** |
| `revert.z_60.q95` | ES | 3,270 | -38,673 | -11.83 | -24.33 | 0.79 | 57.4% | -38,957 | 19.5× | -3.43 | 2 | — | — | **REJECT** |
| `revert.z_60.q90` | ES | 5,078 | -69,370 | -13.66 | -26.16 | 0.78 | 59.3% | -71,156 | 35.6× | -4.36 | 2 | — | — | **REJECT** |
| `revert.z_calm_only` | ES | 1,752 | -27,785 | -15.86 | -28.36 | 0.70 | 55.7% | -27,842 | 13.9× | -4.32 | 2 | — | — | **REJECT** |
| `revert.z_60.q90` | MES | 4,164 | -8,496 | -2.04 | -3.29 | 0.69 | 60.3% | -8,588 | 4.3× | -5.84 | 2 | — | — | **REJECT** |
| `revert.z_60.q95` | MES | 2,612 | -5,135 | -1.97 | -3.22 | 0.68 | 57.6% | -5,192 | 2.6× | -4.82 | 2 | — | — | **REJECT** |
| `revert.z_calm_only` | MES | 1,381 | -3,416 | -2.47 | -3.72 | 0.59 | 56.0% | -3,404 | 1.7× | -5.51 | 2 | — | — | **REJECT** |

## BREAKOUT  ·  24 cells, 2 inside the barrier

**Why it could work.** Price leaving an established range attracts continuation flow: stops trigger, and passive liquidity steps away. Directly opposed to reversion, which is why both belong in the library.

**Why it could fail.** A range break is the single most watched pattern in the instrument, so it is the most crowded. False breakouts dominate in a mean-reverting tape, and the entry is by construction at the worst price in the range. Cost is paid on every attempt; the payoff arrives on a minority.

**What would kill it.** Reject unless a breakout cell's profit factor exceeds 1.2 under stressed costs. The only cell that survives at all does so by FADING breakouts.

| strategy | sym | trades | net $ | $/tr | stressed $/tr | PF | win% | max DD $ | DD/MLL | t | hold min | DLL/sess | twin pass | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `breakout.failed_reversal` | MNQ | 343 | 499 | 1.45 | 0.95 | 1.19 | 48.7% | -188 | 0.1× | 1.11 | 1 | 0.0% | 44.2% | **RESEARCH** |
| `breakout.failed_reversal` | MES | 449 | -1,082 | -2.41 | -3.66 | 0.54 | 39.2% | -1,082 | 0.5× | -4.31 | 1 | — | — | **REJECT** |
| `breakout.failed_reversal` | NQ | 470 | 188 | 0.40 | -4.60 | 1.01 | 48.7% | -6,239 | 3.1× | 0.04 | 1 | — | — | **REJECT** |
| `breakout.range_expansion.q80` | MNQ | 2,383 | -2,867 | -1.20 | -1.70 | 0.93 | 39.0% | -3,678 | 1.8× | -0.88 | 3 | — | — | **REJECT** |
| `breakout.range_expansion.q90` | MNQ | 1,217 | -1,786 | -1.47 | -1.97 | 0.92 | 39.5% | -2,678 | 1.3× | -0.70 | 3 | — | — | **REJECT** |
| `breakout.compression_expansion` | NQ | 3,317 | -34,743 | -10.47 | -15.47 | 0.92 | 33.5% | -44,776 | 22.4× | -1.25 | 3 | — | — | **REJECT** |
| `breakout.range_expansion.q80` | NQ | 2,880 | -46,281 | -16.07 | -21.07 | 0.90 | 39.1% | -60,332 | 30.2× | -1.37 | 3 | — | — | **REJECT** |
| `breakout.compression_expansion` | MNQ | 2,797 | -4,264 | -1.52 | -2.02 | 0.90 | 31.5% | -4,509 | 2.3× | -1.54 | 3 | — | — | **REJECT** |
| `breakout.range_expansion.q90` | NQ | 1,409 | -29,156 | -20.69 | -25.69 | 0.89 | 38.3% | -34,282 | 17.1× | -1.17 | 3 | — | — | **REJECT** |
| `breakout.range_expansion.q90` | ES | 1,418 | -28,798 | -20.31 | -32.81 | 0.80 | 35.9% | -29,376 | 14.7× | -2.19 | 3 | — | — | **REJECT** |
| `breakout.range_expansion.q80` | ES | 2,859 | -54,520 | -19.07 | -31.57 | 0.79 | 35.8% | -55,197 | 27.6× | -3.12 | 3 | — | — | **REJECT** |
| `breakout.range_expansion.q90` | MES | 1,174 | -2,654 | -2.26 | -3.51 | 0.79 | 36.8% | -2,656 | 1.3× | -2.10 | 3 | — | — | **REJECT** |
| `breakout.compression_expansion` | ES | 3,811 | -57,618 | -15.12 | -27.62 | 0.78 | 29.9% | -59,138 | 29.6× | -4.09 | 3 | — | — | **REJECT** |
| `breakout.opening_range.q95` | MNQ | 385 | -2,465 | -6.40 | -6.90 | 0.78 | 9.6% | -4,469 | 2.2× | -0.93 | 4 | — | — | **REJECT** |
| `breakout.failed_reversal` | ES | 364 | -4,476 | -12.30 | -24.80 | 0.73 | 40.7% | -4,796 | 2.4× | -2.44 | 1 | — | — | **REJECT** |
| `breakout.range_expansion.q80` | MES | 2,372 | -6,824 | -2.88 | -4.13 | 0.72 | 35.2% | -6,795 | 3.4× | -3.93 | 3 | — | — | **REJECT** |
| `breakout.opening_range.q90` | MES | 780 | -3,254 | -4.17 | -5.42 | 0.71 | 10.1% | -3,869 | 1.9× | -1.88 | 4 | — | — | **REJECT** |
| `breakout.opening_range.q90` | ES | 976 | -38,302 | -39.24 | -51.74 | 0.69 | 9.5% | -38,302 | 19.2× | -2.14 | 4 | — | — | **REJECT** |
| `breakout.opening_range.q95` | ES | 414 | -18,777 | -45.36 | -57.86 | 0.68 | 9.4% | -18,777 | 9.4× | -1.41 | 4 | — | — | **REJECT** |
| `breakout.opening_range.q95` | NQ | 515 | -39,722 | -77.13 | -82.13 | 0.67 | 7.8% | -51,352 | 25.7× | -1.49 | 3 | — | — | **REJECT** |
| `breakout.compression_expansion` | MES | 3,356 | -8,454 | -2.52 | -3.77 | 0.67 | 28.2% | -8,388 | 4.2× | -5.90 | 3 | — | — | **REJECT** |
| `breakout.opening_range.q90` | MNQ | 802 | -7,128 | -8.89 | -9.39 | 0.67 | 7.6% | -8,228 | 4.1× | -1.99 | 3 | — | — | **REJECT** |
| `breakout.opening_range.q90` | NQ | 961 | -78,558 | -81.75 | -86.75 | 0.67 | 7.9% | -75,908 | 38.0× | -2.16 | 3 | — | — | **REJECT** |
| `breakout.opening_range.q95` | MES | 496 | -2,878 | -5.80 | -7.05 | 0.61 | 8.3% | -3,500 | 1.8× | -1.92 | 3 | — | — | **REJECT** |

## TREND  ·  36 cells, 0 inside the barrier

**Why it could work.** A move that is large in its own recent units continues, because information arrives in pieces and the market prices it over minutes rather than instantly. The structural advantage would be that a trend rider needs no view on fair value, only on persistence.

**Why it could fail.** Intraday index futures displace LESS than a random walk - the previous phase measured median |net move| / sigma*sqrt(n) at 0.655-0.738 on eight instruments over eleven years. A trend mechanism is paid for displacement and this asset class systematically fails to deliver it. On top of that, every entry pays the spread while the signal is at its most crowded.

**What would kill it.** Reject unless a trend cell shows positive stressed expectancy AND a 1-contract max drawdown below $2,000. Currently 0 of 36 trend cells clear either leg.

| strategy | sym | trades | net $ | $/tr | stressed $/tr | PF | win% | max DD $ | DD/MLL | t | hold min | DLL/sess | twin pass | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `trend.ret_30.q80` | MNQ | 5,511 | -8,911 | -1.62 | -2.12 | 0.90 | 24.1% | -9,433 | 4.7× | -1.99 | 3 | — | — | **REJECT** |
| `trend.ret_15.q80` | MNQ | 5,560 | -9,230 | -1.66 | -2.16 | 0.89 | 24.6% | -9,252 | 4.6× | -2.07 | 3 | — | — | **REJECT** |
| `trend.ret_60.q80` | MNQ | 5,310 | -8,979 | -1.69 | -2.19 | 0.89 | 24.8% | -9,495 | 4.7× | -2.00 | 3 | — | — | **REJECT** |
| `trend.ret_15.q80` | NQ | 6,936 | -114,383 | -16.49 | -21.49 | 0.88 | 24.6% | -114,647 | 57.3× | -2.49 | 3 | — | — | **REJECT** |
| `trend.ret_30.q80` | NQ | 6,882 | -116,859 | -16.98 | -21.98 | 0.88 | 24.1% | -116,347 | 58.2× | -2.53 | 3 | — | — | **REJECT** |
| `trend.ret_60.q80` | NQ | 6,612 | -112,423 | -17.00 | -22.00 | 0.88 | 24.8% | -111,925 | 56.0× | -2.45 | 3 | — | — | **REJECT** |
| `trend.multi_horizon_agree` | MNQ | 6,782 | -14,971 | -2.21 | -2.71 | 0.87 | 30.9% | -14,867 | 7.4× | -2.79 | 3 | — | — | **REJECT** |
| `trend.multi_horizon_agree` | NQ | 8,555 | -185,323 | -21.66 | -26.66 | 0.86 | 31.2% | -184,332 | 92.2× | -3.37 | 3 | — | — | **REJECT** |
| `trend.ret_30.q90` | MNQ | 4,033 | -8,060 | -2.00 | -2.50 | 0.85 | 28.1% | -8,306 | 4.2× | -2.78 | 2 | — | — | **REJECT** |
| `trend.ret_15.q90` | MNQ | 4,037 | -8,118 | -2.01 | -2.51 | 0.85 | 28.2% | -8,245 | 4.1× | -2.83 | 2 | — | — | **REJECT** |
| `trend.accel_confirm` | NQ | 10,851 | -254,877 | -23.49 | -28.49 | 0.84 | 36.5% | -256,459 | 128.2× | -5.13 | 2 | — | — | **REJECT** |
| `trend.ret_60.q90` | MNQ | 3,965 | -8,492 | -2.14 | -2.64 | 0.84 | 28.0% | -8,927 | 4.5× | -2.90 | 2 | — | — | **REJECT** |
| `trend.accel_confirm` | MNQ | 8,633 | -22,571 | -2.61 | -3.11 | 0.84 | 36.1% | -22,753 | 11.4× | -4.65 | 2 | — | — | **REJECT** |
| `trend.ret_30.q90` | NQ | 5,052 | -108,182 | -21.41 | -26.41 | 0.83 | 27.7% | -109,063 | 54.5× | -3.62 | 2 | — | — | **REJECT** |
| `trend.ret_15.q90` | NQ | 5,054 | -108,874 | -21.54 | -26.54 | 0.83 | 27.8% | -109,580 | 54.8× | -3.67 | 2 | — | — | **REJECT** |
| `trend.ret_60.q90` | NQ | 4,964 | -110,544 | -22.27 | -27.27 | 0.82 | 27.6% | -113,103 | 56.6× | -3.67 | 2 | — | — | **REJECT** |
| `trend.ma_agree.30_120` | MNQ | 5,317 | -18,173 | -3.42 | -3.92 | 0.81 | 20.7% | -18,070 | 9.0× | -3.70 | 4 | — | — | **REJECT** |
| `trend.ma_agree.30_120` | NQ | 6,734 | -221,885 | -32.95 | -37.95 | 0.80 | 20.8% | -220,522 | 110.3× | -4.42 | 3 | — | — | **REJECT** |
| `trend.ret_15.q80` | ES | 6,981 | -136,551 | -19.56 | -32.06 | 0.75 | 22.2% | -136,151 | 68.1× | -6.09 | 3 | — | — | **REJECT** |
| `trend.ret_30.q80` | ES | 6,971 | -137,925 | -19.79 | -32.29 | 0.75 | 21.7% | -137,496 | 68.7× | -6.19 | 3 | — | — | **REJECT** |
| `trend.multi_horizon_agree` | ES | 8,573 | -190,243 | -22.19 | -34.69 | 0.73 | 26.9% | -189,847 | 94.9× | -6.82 | 3 | — | — | **REJECT** |
| `trend.ret_30.q90` | ES | 5,067 | -95,453 | -18.84 | -31.34 | 0.73 | 22.8% | -96,237 | 48.1× | -5.70 | 2 | — | — | **REJECT** |
| `trend.ret_15.q90` | ES | 5,069 | -95,398 | -18.82 | -31.32 | 0.73 | 22.9% | -96,099 | 48.0× | -5.72 | 2 | — | — | **REJECT** |
| `trend.ret_60.q80` | ES | 6,768 | -144,958 | -21.42 | -33.92 | 0.73 | 21.8% | -144,412 | 72.2× | -6.48 | 3 | — | — | **REJECT** |
| `trend.ma_agree.30_120` | ES | 6,654 | -165,490 | -24.87 | -37.37 | 0.73 | 19.6% | -166,729 | 83.4× | -6.11 | 4 | — | — | **REJECT** |
| `trend.ret_60.q90` | ES | 4,997 | -98,226 | -19.66 | -32.16 | 0.72 | 22.8% | -98,969 | 49.5× | -5.91 | 2 | — | — | **REJECT** |
| `trend.accel_confirm` | ES | 10,808 | -258,904 | -23.95 | -36.45 | 0.71 | 32.3% | -257,594 | 128.8× | -9.75 | 2 | — | — | **REJECT** |
| `trend.ret_30.q80` | MES | 5,602 | -15,878 | -2.83 | -4.08 | 0.68 | 21.6% | -15,776 | 7.9× | -7.34 | 3 | — | — | **REJECT** |
| `trend.ret_15.q80` | MES | 5,607 | -15,997 | -2.85 | -4.10 | 0.68 | 22.1% | -15,895 | 7.9× | -7.31 | 3 | — | — | **REJECT** |
| `trend.multi_horizon_agree` | MES | 6,876 | -20,844 | -3.03 | -4.28 | 0.68 | 27.2% | -20,667 | 10.3× | -7.85 | 3 | — | — | **REJECT** |
| `trend.ret_60.q80` | MES | 5,436 | -16,131 | -2.97 | -4.22 | 0.67 | 22.0% | -15,996 | 8.0× | -7.36 | 3 | — | — | **REJECT** |
| `trend.ma_agree.30_120` | MES | 5,380 | -18,930 | -3.52 | -4.77 | 0.66 | 19.6% | -18,853 | 9.4× | -7.21 | 4 | — | — | **REJECT** |
| `trend.accel_confirm` | MES | 8,656 | -28,379 | -3.28 | -4.53 | 0.64 | 32.4% | -28,283 | 14.1× | -11.19 | 2 | — | — | **REJECT** |
| `trend.ret_30.q90` | MES | 4,159 | -12,035 | -2.89 | -4.14 | 0.64 | 22.7% | -11,912 | 6.0× | -7.65 | 2 | — | — | **REJECT** |
| `trend.ret_15.q90` | MES | 4,162 | -12,034 | -2.89 | -4.14 | 0.64 | 22.9% | -11,911 | 6.0× | -7.65 | 2 | — | — | **REJECT** |
| `trend.ret_60.q90` | MES | 4,093 | -12,081 | -2.95 | -4.20 | 0.63 | 23.0% | -11,965 | 6.0× | -7.80 | 2 | — | — | **REJECT** |

## SESSION  ·  16 cells, 1 inside the barrier

**Why it could work.** The clock matters: the auction, the European close, the settlement window and the cash close each concentrate different flow, so a rule conditioned on time of day needs no price forecast.

**Why it could fail.** Measured directly last phase: zero of 28 time-of-day blocks showed a significant unconditional drift on any instrument, largest |t| = 1.8 against a Bonferroni bar of 3.1. There is no drift for a clock rule to harvest.

**What would kill it.** Reject unless a session block shows drift clearing |t| > 3.1 on a fresh sample. Already tested and failed.

| strategy | sym | trades | net $ | $/tr | stressed $/tr | PF | win% | max DD $ | DD/MLL | t | hold min | DLL/sess | twin pass | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `session.midday_reversion` | NQ | 2,229 | 13,404 | 6.01 | 1.01 | 1.06 | 67.5% | -13,477 | 6.7× | 0.75 | 2 | 21.6% | 25.0% | **REJECT** |
| `session.midday_reversion` | MNQ | 1,797 | 360 | 0.20 | -0.30 | 1.02 | 65.6% | -1,387 | 0.7× | 0.21 | 2 | 0.0% | 26.0% | **REJECT** |
| `session.late_day_continuation` | MNQ | 2,182 | -2,173 | -1.00 | -1.50 | 0.94 | 30.6% | -3,645 | 1.8× | -0.73 | 4 | — | — | **REJECT** |
| `session.opening_drive` | NQ | 2,975 | -53,051 | -17.83 | -22.83 | 0.93 | 35.2% | -60,259 | 30.1× | -0.99 | 3 | — | — | **REJECT** |
| `session.opening_drive` | MNQ | 2,385 | -6,117 | -2.56 | -3.06 | 0.91 | 34.5% | -6,479 | 3.2× | -1.18 | 4 | — | — | **REJECT** |
| `session.late_day_continuation` | NQ | 2,796 | -39,009 | -13.95 | -18.95 | 0.91 | 30.5% | -52,228 | 26.1× | -1.25 | 4 | — | — | **REJECT** |
| `session.late_day_fade` | NQ | 2,796 | -38,049 | -13.61 | -18.61 | 0.91 | 63.2% | -52,561 | 26.3× | -1.27 | 4 | — | — | **REJECT** |
| `session.midday_reversion` | ES | 2,256 | -13,865 | -6.15 | -18.65 | 0.88 | 59.7% | -14,804 | 7.4× | -1.45 | 2 | — | — | **REJECT** |
| `session.opening_drive` | ES | 2,915 | -47,169 | -16.18 | -28.68 | 0.87 | 31.5% | -50,962 | 25.5× | -2.02 | 3 | — | — | **REJECT** |
| `session.late_day_fade` | ES | 2,908 | -28,605 | -9.84 | -22.34 | 0.87 | 58.1% | -40,410 | 20.2× | -2.02 | 3 | — | — | **REJECT** |
| `session.late_day_fade` | MNQ | 2,182 | -5,334 | -2.44 | -2.94 | 0.86 | 61.3% | -6,001 | 3.0× | -1.88 | 4 | — | — | **REJECT** |
| `session.opening_drive` | MES | 2,327 | -5,839 | -2.51 | -3.76 | 0.82 | 31.8% | -5,864 | 2.9× | -2.58 | 4 | — | — | **REJECT** |
| `session.midday_reversion` | MES | 1,812 | -2,041 | -1.13 | -2.38 | 0.81 | 61.0% | -2,101 | 1.1× | -2.34 | 2 | — | — | **REJECT** |
| `session.late_day_fade` | MES | 2,297 | -4,605 | -2.00 | -3.25 | 0.76 | 58.3% | -4,744 | 2.4× | -3.59 | 3 | — | — | **REJECT** |
| `session.late_day_continuation` | ES | 2,908 | -66,080 | -22.72 | -35.22 | 0.74 | 25.1% | -65,882 | 32.9× | -4.23 | 3 | — | — | **REJECT** |
| `session.late_day_continuation` | MES | 2,297 | -6,742 | -2.94 | -4.19 | 0.70 | 25.8% | -6,752 | 3.4× | -4.54 | 3 | — | — | **REJECT** |

## VOLATILITY  ·  12 cells, 0 inside the barrier

**Why it could work.** Volatility is the one genuinely forecastable quantity here - out-of-sample R-squared 0.46-0.51, robust in every regime partition. A rule that trades when movement is expected should at least be trading when there is something to trade.

**Why it could fail.** The forecast predicts PATH, not DISPLACEMENT: R-squared 0.03-0.08 for the absolute net move, and measured efficiency FALLS as forecast volatility rises. High-volatility sessions are choppier, not more directional, so a directional rule gated on volatility is gated toward its worst environment.

**What would kill it.** Reject unless a volatility-conditioned cell beats a regime-matched, scale-normalised random gate at the 95th percentile AND is profitable. Tested last phase: the gate beats its control but never produces profit.

| strategy | sym | trades | net $ | $/tr | stressed $/tr | PF | win% | max DD $ | DD/MLL | t | hold min | DLL/sess | twin pass | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `vol.contraction_revert` | NQ | 3,349 | -16,134 | -4.82 | -9.82 | 0.95 | 66.9% | -21,198 | 10.6× | -0.84 | 2 | — | — | **REJECT** |
| `vol.vol_of_vol_shock` | MNQ | 622 | -936 | -1.51 | -2.01 | 0.95 | 35.4% | -3,556 | 1.8× | -0.44 | 5 | — | — | **REJECT** |
| `vol.contraction_revert` | MNQ | 2,690 | -1,778 | -0.66 | -1.16 | 0.94 | 64.6% | -2,316 | 1.2× | -0.94 | 2 | — | — | **REJECT** |
| `vol.expansion_trend` | NQ | 5,530 | -96,983 | -17.54 | -22.54 | 0.92 | 36.7% | -96,940 | 48.5× | -1.67 | 3 | — | — | **REJECT** |
| `vol.expansion_trend` | MNQ | 4,382 | -8,593 | -1.96 | -2.46 | 0.92 | 36.6% | -8,727 | 4.4× | -1.53 | 3 | — | — | **REJECT** |
| `vol.vol_of_vol_shock` | NQ | 1,164 | -30,305 | -26.04 | -31.04 | 0.89 | 34.5% | -55,839 | 27.9× | -1.14 | 4 | — | — | **REJECT** |
| `vol.expansion_trend` | ES | 5,783 | -124,635 | -21.55 | -34.05 | 0.81 | 33.2% | -124,640 | 62.3× | -4.72 | 3 | — | — | **REJECT** |
| `vol.contraction_revert` | ES | 3,251 | -33,901 | -10.43 | -22.93 | 0.79 | 58.2% | -35,395 | 17.7× | -3.40 | 2 | — | — | **REJECT** |
| `vol.vol_of_vol_shock` | ES | 1,121 | -36,625 | -32.67 | -45.17 | 0.77 | 30.2% | -41,351 | 20.7× | -2.27 | 4 | — | — | **REJECT** |
| `vol.expansion_trend` | MES | 4,707 | -14,984 | -3.18 | -4.43 | 0.75 | 34.1% | -14,924 | 7.5× | -5.97 | 3 | — | — | **REJECT** |
| `vol.vol_of_vol_shock` | MES | 636 | -2,721 | -4.28 | -5.53 | 0.72 | 29.7% | -3,135 | 1.6× | -2.32 | 4 | — | — | **REJECT** |
| `vol.contraction_revert` | MES | 2,651 | -4,052 | -1.53 | -2.78 | 0.72 | 59.6% | -4,114 | 2.1× | -4.39 | 2 | — | — | **REJECT** |

## VOLUME  ·  12 cells, 0 inside the barrier

**Why it could work.** Heavy relative volume means real participation rather than drift on an empty book, so a move accompanied by volume should be more informative.

**Why it could fail.** Volume predicts MAGNITUDE, not direction - the same wall the volatility family hits, reached by a different route. Overnight volume predicts RTH range at t up to 7.3 and RTH direction at nothing.

**What would kill it.** Reject unless a volume cell shows directional skill independent of the magnitude channel. No test has ever shown one.

| strategy | sym | trades | net $ | $/tr | stressed $/tr | PF | win% | max DD $ | DD/MLL | t | hold min | DLL/sess | twin pass | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `volume.climax_reversion` | NQ | 1,044 | -12,536 | -12.01 | -17.01 | 0.92 | 60.3% | -22,155 | 11.1× | -0.75 | 2 | — | — | **REJECT** |
| `volume.heavy_continuation.q90` | NQ | 4,418 | -82,890 | -18.76 | -23.76 | 0.82 | 43.4% | -84,525 | 42.3× | -3.67 | 1 | — | — | **REJECT** |
| `volume.heavy_continuation.q80` | MNQ | 7,052 | -12,623 | -1.79 | -2.29 | 0.82 | 42.0% | -12,535 | 6.3× | -4.42 | 1 | — | — | **REJECT** |
| `volume.heavy_continuation.q80` | NQ | 8,339 | -155,501 | -18.65 | -23.65 | 0.81 | 42.7% | -156,548 | 78.3× | -5.25 | 1 | — | — | **REJECT** |
| `volume.climax_reversion` | MNQ | 819 | -2,576 | -3.14 | -3.64 | 0.80 | 58.7% | -3,003 | 1.5× | -1.66 | 3 | — | — | **REJECT** |
| `volume.climax_reversion` | ES | 1,061 | -17,623 | -16.61 | -29.11 | 0.80 | 56.6% | -18,726 | 9.4× | -1.98 | 3 | — | — | **REJECT** |
| `volume.heavy_continuation.q90` | MNQ | 3,891 | -7,803 | -2.01 | -2.51 | 0.80 | 42.4% | -7,752 | 3.9× | -3.78 | 1 | — | — | **REJECT** |
| `volume.climax_reversion` | MES | 949 | -2,279 | -2.40 | -3.65 | 0.72 | 56.9% | -2,381 | 1.2× | -2.86 | 2 | — | — | **REJECT** |
| `volume.heavy_continuation.q90` | ES | 3,913 | -80,491 | -20.57 | -33.07 | 0.67 | 37.5% | -81,194 | 40.6× | -6.21 | 1 | — | — | **REJECT** |
| `volume.heavy_continuation.q80` | ES | 7,444 | -142,638 | -19.16 | -31.66 | 0.66 | 35.5% | -142,731 | 71.4× | -8.53 | 1 | — | — | **REJECT** |
| `volume.heavy_continuation.q80` | MES | 6,786 | -18,593 | -2.74 | -3.99 | 0.56 | 37.4% | -18,461 | 9.2× | -11.21 | 1 | — | — | **REJECT** |
| `volume.heavy_continuation.q90` | MES | 3,812 | -10,824 | -2.84 | -4.09 | 0.56 | 36.9% | -10,715 | 5.4× | -9.62 | 1 | — | — | **REJECT** |

## ADDED  ·  12 cells, 1 inside the barrier

**Why it could work.** Three canonical mechanisms the library was missing: a channel breakout, a band reversion and the trend-side counterpart to VWAP reversion. Added so that 'which existing mechanism is strongest' is answered against a complete field rather than a partial one.

**Why it could fail.** Bollinger duplicates the z-score reversion it sits beside - daily P&L correlation 0.81, so it is one mechanism under two names. Donchian and VWAP-trend inherit the trend family's displacement problem in full.

**What would kill it.** Reject Bollinger as a separate mechanism outright: at rho = 0.81 with revert.z_60 it is not a diversifier. Reject the other two on the trend family's condition.

| strategy | sym | trades | net $ | $/tr | stressed $/tr | PF | win% | max DD $ | DD/MLL | t | hold min | DLL/sess | twin pass | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `added.bollinger_revert.2sd` *(added)* | MNQ | 3,058 | 352 | 0.12 | -0.38 | 1.01 | 64.8% | -1,563 | 0.8× | 0.15 | 2 | — | — | **REJECT** |
| `added.bollinger_revert.2sd` *(added)* | NQ | 3,841 | 13,301 | 3.46 | -1.54 | 1.03 | 66.1% | -14,784 | 7.4× | 0.55 | 2 | 31.6% | 23.5% | **REJECT** |
| `added.vwap_trend` *(added)* | NQ | 3,570 | -98,340 | -27.55 | -32.55 | 0.90 | 24.2% | -98,554 | 49.3× | -1.42 | 4 | — | — | **REJECT** |
| `added.vwap_trend` *(added)* | MNQ | 2,748 | -9,009 | -3.28 | -3.78 | 0.90 | 25.7% | -12,188 | 6.1× | -1.38 | 4 | — | — | **REJECT** |
| `added.vwap_trend` *(added)* | ES | 3,566 | -80,904 | -22.69 | -35.19 | 0.84 | 23.9% | -82,574 | 41.3× | -2.41 | 4 | — | — | **REJECT** |
| `added.bollinger_revert.2sd` *(added)* | ES | 3,884 | -38,419 | -9.89 | -22.39 | 0.83 | 58.8% | -39,261 | 19.6× | -3.04 | 2 | — | — | **REJECT** |
| `added.vwap_trend` *(added)* | MES | 2,624 | -7,694 | -2.93 | -4.18 | 0.82 | 25.9% | -8,492 | 4.2× | -2.47 | 4 | — | — | **REJECT** |
| `added.donchian_breakout` *(added)* | MNQ | 385 | -2,465 | -6.40 | -6.90 | 0.78 | 9.6% | -4,469 | 2.2× | -0.93 | 4 | — | — | **REJECT** |
| `added.bollinger_revert.2sd` *(added)* | MES | 3,099 | -5,687 | -1.84 | -3.09 | 0.71 | 58.6% | -5,710 | 2.9× | -4.71 | 2 | — | — | **REJECT** |
| `added.donchian_breakout` *(added)* | NQ | 515 | -39,542 | -76.78 | -81.78 | 0.68 | 7.8% | -51,172 | 25.6× | -1.48 | 3 | — | — | **REJECT** |
| `added.donchian_breakout` *(added)* | ES | 417 | -19,089 | -45.78 | -58.28 | 0.67 | 9.4% | -19,089 | 9.5× | -1.43 | 4 | — | — | **REJECT** |
| `added.donchian_breakout` *(added)* | MES | 496 | -2,878 | -5.80 | -7.05 | 0.61 | 8.3% | -3,500 | 1.8× | -1.92 | 3 | — | — | **REJECT** |

---

## The two cells that are not REJECT

### `breakout.failed_reversal` · MNQ — **RESEARCH**

**Core.** Net $499 on 343 trades ($1.45/trade, $0.95 after a tick of slippage). Profit factor 1.19, win rate 48.7%. Max drawdown $-188 = **0.09× the MLL**. Sharpe 1.12, Sortino 1.51, t = 1.11. Median hold 1 min, 1.4 trades/session, 2 consecutive losing days at worst.

**Why it survived.** It is one of only 8 cells whose own worst historical run fits inside the $2,000 barrier, and its expectancy stays positive with a full tick of round-turn slippage charged. It trips the $1,000 daily loss limit on 0.0% of sessions — never, in the whole sample.

**Topstep twin, by size.**

| contracts | pass | breach | median days | P[MC drawdown > MLL] |
|---|---|---|---|---|
| 1 | 0.0% | 0.0% | never | 0.0% |
| 5 | 12.5% | 3.8% | 90 | 8.5% |
| 10 | 44.2% | 47.2% | 61 | 86.0% |
| 20 | 36.2% | 82.5% | 44 | 100.0% |

**Why it is still not a candidate.** t = 1.11 on the daily series, short of 1.96 — and that is before correcting for having examined 132 cells, which would require roughly |t| > 3.6. There is no contract size at which it both reaches $3,000 and survives the barrier.

### `revert.vwap.q95` · MNQ — **WATCH**

**Core.** Net $2,771 on 755 trades ($3.67/trade, $3.17 after a tick of slippage). Profit factor 1.17, win rate 80.8%. Max drawdown $-1,804 = **0.90× the MLL**. Sharpe 0.78, Sortino 0.46, t = 0.78. Median hold 3 min, 3.0 trades/session, 4 consecutive losing days at worst.

**Why it survived.** It is one of only 8 cells whose own worst historical run fits inside the $2,000 barrier, and its expectancy stays positive with a full tick of round-turn slippage charged. It trips the $1,000 daily loss limit on 1.6% of sessions.

**Topstep twin, by size.**

| contracts | pass | breach | median days | P[MC drawdown > MLL] |
|---|---|---|---|---|
| 1 | 20.8% | 66.0% | 81 | 91.8% |
| 5 | 42.0% | 98.0% | 17 | 100.0% |
| 10 | 32.2% | 99.0% | 11 | 100.0% |
| 20 | 31.8% | 97.8% | 10 | 100.0% |

**Why it is still not a candidate.** t = 0.78 on the daily series, short of 1.96 — and that is before correcting for having examined 132 cells, which would require roughly |t| > 3.6. There is no contract size at which it both reaches $3,000 and survives the barrier.

---

## Instrument note

| instrument | cells | inside the barrier | median DD/MLL |
|---|---|---|---|
| ES | 33 | 0 | 27.6× |
| MES | 33 | 2 | 3.4× |
| MNQ | 33 | 6 | 3.0× |
| NQ | 33 | 0 | 27.9× |

The micros carry every survivor. A tick is $0.50 on MNQ against $12.50 on ES, so the same mechanism faces a 25× smaller cost floor and a 25× smaller drawdown in dollars — which is the entire reason those cells fit inside a $2,000 barrier and their full-size twins do not.

---

## Exit & Risk Architecture — appended by the exit phase

Full analysis: [EXIT_RISK_RESEARCH.md](EXIT_RISK_RESEARCH.md). Generated from `research/exit_*.csv`.

### The entry-information gate (Phases 4 & 16)

Signed forward excursion against 200 controls matched on **bar-of-session and direction**. This gate ran *before* any exit was built, because the brief forbids using exit optimisation to rescue an entry with no forward advantage.

| candidate | verdict | horizons beaten (of 7) | MFE/MAE @5b | note |
|---|---|---|---|---|
| `breakout.failed_reversal` MNQ | **PASS** | 3 | 1.14 | edge at bars 1/3/5, mechanism-consistent |
| `revert.vwap.q95` MNQ | **MARGINAL** | 1 | 1.05 | only at 60b |
| `revert.vwap.q90` NQ | **FAIL** | 0 | 1.01 | **highest-earning cell in the lab; 2nd percentile at 10b** |
| `session.midday_reversion` MNQ | **MARGINAL** | 1 | 1.02 | only at 60b |
| `trend.ret_30.q80` MNQ | **MARGINAL** | 1 | 1.00 | only at 60b |
| `breakout.range_expansion.q80` MNQ | **FAIL** | 0 | 1.02 | no horizon |

### Exit architectures on the one passing entry

41 preregistered cells, 60/40 temporal split. **IS↔OOS rank correlation -0.002** — in-sample selection carries no out-of-sample information.

| architecture | IS $/tr | OOS $/tr | IS PF | OOS PF | OOS max DD |
|---|---|---|---|---|---|
| `E.time30b` | +7.19 | -20.55 | 1.21 | 0.65 | -1,059 |
| `A.stop1.25atr_tgt2R` | +2.57 | -1.41 | 1.09 | 0.96 | -630 |
| `E.time1b` | +1.87 | +0.50 | 1.24 | 1.07 | -151 |
| `F.baseline_invalidation` | +1.87 | +0.50 | 1.24 | 1.07 | -151 |
| `A.stop1.25atr_tgt1.5R` | +1.04 | -0.20 | 1.04 | 0.99 | -570 |
| `E.time10b` | +0.80 | -2.35 | 1.03 | 0.91 | -489 |
| `A.stop1.5atr_tgt2R` | +0.76 | -1.51 | 1.02 | 0.96 | -751 |
| `A.stop1.25atr_tgt1R` | +0.71 | -5.31 | 1.03 | 0.80 | -565 |

`E.time1b` is byte-identical to `F.baseline_invalidation`: median hold is one bar, so the mechanism is a one-bar scalp whose existing exit is already correct.

### Slippage — the binding constraint

| slippage | full $/tr | OOS $/tr |
|---|---|---|
| 0.0 ticks | +1.45 | +0.50 |
| 0.5 ticks | +1.20 | +0.25 |
| 1.0 ticks | +0.95 | +0.00 |
| 2.0 ticks | +0.45 | -0.50 |

**OOS break-even is exactly 1.00 tick** ($0.50 on MNQ). The brief's rule — *a strategy that only works with perfect fills is REJECT* — applies.

### Random exit controls

| control | median $/tr | real percentile |
|---|---|---|
| random_stop_target | -1.54 | 95.5% |
| random_timing | +1.45 | 0.0% |
| fixed_hold | +1.45 | — |
| random_entry | +1.04 | 61.5% |

The `random_entry` control was **corrected mid-run** — the first version randomised the entry *and* the stop/target, changing two things at once. Isolated, the real entry sits at **93.0%**, below the 95% bar, against 99.0% on the bar-matched control. Borderline; both reported.

### Topstep economics, baseline architecture

| contracts | pass | breach | survive 20d | DLL/session |
|---|---|---|---|---|
| 1 | 0.0% | 0.0% | 100.0% | 0.0% |
| 5 | 11.2% | 4.2% | 95.8% | 0.0% |
| 10 | 39.5% | 43.8% | 56.2% | 0.0% |
| 20 | 31.8% | 82.0% | 18.0% | 4.8% |
| 50 | 24.0% | 94.0% | 6.0% | 10.8% |

No size both reaches $3,000 and survives the barrier.

### Verdict after exit research

| strategy | before | after | why |
|---|---|---|---|
| `breakout.failed_reversal` MNQ | RESEARCH | **RESEARCH** (unchanged) | real but weak 1-bar edge; no exit improves it; dies at 1.00 tick OOS |
| `revert.vwap.q95` MNQ | WATCH | **WATCH** (unchanged) | MARGINAL at the entry gate, not mechanism-consistent; no exit research run |
| all other candidates | REJECT | **REJECT** | failed the entry gate |

**No strategy advances to PAPER CANDIDATE.**

---

## Failed-Reversal Replication — appended by Phase 17

Full analysis: [FAILED_REVERSAL_REPLICATION.md](FAILED_REVERSAL_REPLICATION.md). Frozen rule hash `8ed5bb73283cb506`.

**VERDICT: A. REJECT.** The only remaining research candidate from the strategy library does not replicate. On QQQ — the same index as MNQ, over the exact same dates — the sign is opposite.

### Cross-instrument, signed 1-bar forward return

| panel | sym | entries | 1b $ | t | ctl %ile | verdict |
|---|---|---|---|---|---|---|
| futures | **MNQ** | 343 | +3.203 | +2.48 | 99.0% | REPLICATES |
| futures | **NQ** | 470 | +14.426 | +1.46 | 89.5% | REPLICATES |
| futures | **MES** | 449 | +0.062 | +0.12 | 50.0% | MARGINAL |
| futures | **ES** | 364 | +4.006 | +0.65 | 77.5% | MARGINAL |
| etf | **SPY** | 4,395 | +0.465 | +1.63 | 95.5% | FAILS |
| etf | **QQQ** | 4,124 | -0.668 | -2.18 | 0.5% | FAILS |
| etf | **IWM** | 3,719 | -0.057 | -0.31 | 37.0% | FAILS |
| etf | **DIA** | 3,912 | +0.260 | +1.09 | 92.5% | MARGINAL |

### The decisive test — same index, same dates

| series | entries | 1b | 3b | 5b | ctl %ile |
|---|---|---|---|---|---|
| **MNQ** 2025-06..2026-09 (futures era) | 343 | +3.203 | +4.341 | +6.240 | 99.3% |
| **QQQ** 2025-06..2026-09 (futures era) | 451 | -0.799 | -3.040 | -3.786 | 15.3% |

Not a period effect — an instrument/sample artifact.

### Friction gate — net $/trade at one tick

| panel | sym | gross | net @1 tick | classification |
|---|---|---|---|---|
| futures | MNQ | +3.203 | +0.983 | MARGINAL AFTER COSTS |
| futures | NQ | +14.426 | -4.354 | NEGATIVE AFTER COSTS |
| futures | MES | +0.062 | -3.658 | NEGATIVE AFTER COSTS |
| futures | ES | +4.006 | -24.774 | NEGATIVE AFTER COSTS |
| etf | SPY | +0.465 | -1.535 | NEGATIVE AFTER COSTS |
| etf | QQQ | -0.668 | -2.668 | NEGATIVE AFTER COSTS |
| etf | IWM | -0.057 | -2.057 | NEGATIVE AFTER COSTS |
| etf | DIA | +0.260 | -1.740 | NEGATIVE AFTER COSTS |

**7 of 8 NEGATIVE AFTER COSTS.**

### Verdict change

| strategy | before | after | why |
|---|---|---|---|
| `breakout.failed_reversal` MNQ | RESEARCH | **REJECT** | fails cross-instrument replication (QQQ inverts), fails the clean 2016–2023 holdout, fails the decay-shape test, 2 of 44 instrument-years replicate |

**All 132 lab cells are now REJECT or unpromotable. No live candidate remains.**
