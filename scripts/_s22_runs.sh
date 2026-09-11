#!/usr/bin/env bash
# S-22: the three instrument corrections charged TOGETHER, and the forward-looking
# expectation of the deployed daily book.
#
# WHAT THIS IS AND WHY IT IS NOT A TWELFTH MECHANISM. Three iterations audited the
# instrument rather than the strategy, and each priced ONE defect against a clean control:
#
#   S-17  spread     LEAN's IB model returns NullSlippageModel, so no fill has ever
#                    crossed a bid/ask.   2 bp: 24.403 -> 23.068   (-1.335)
#   S-19  clock      the deployed runner decides on close[i-1] and fills at close[i],
#                    which LEAN cannot express; its bound S1_SIGNAL_LAG=1 is
#                    24.403 -> 21.384 (-3.019), and the pandas book measures the real
#                    convention at 61% of that.
#   S-21  financing  DefaultBrokerageModel returns MarginInterestRateModel.Null, whose
#                    ApplyMarginInterestRate is empty, so 0.49x of borrowed equity has
#                    been free.   24.403 -> 23.087   (-1.316)
#
# Nobody has run them together, and the owner has never been given one number for what the
# deployed paper book should be expected to earn. Three reasons the composite is not just
# the sum: (a) a staler signal changes WHICH trades fire, so it moves the spread bill;
# (b) financing is charged on a cash path that both other corrections move; (c) CAR is
# geometric, so points do not add.
#
# PRE-REGISTERED BEFORE ANY CELL RAN. Recorded here so the write-up cannot drift.
#
# 1. THIS IS A MEASUREMENT, NOT A CANDIDATE. Every cell charges a cost the control does not,
#    so every cell must lose, and `evaluate.py` is not the judge (it already refuses
#    S1_FINANCING=on runs as not comparable - S-21). Nothing here can be promoted, no
#    default changes, and the champion stays as S-18 left it.
#
# 2. THE A-PRIORI PREDICTION, written down before the first full run, so the composite can
#    be wrong rather than merely reported. Composing the three single-defect cells
#    multiplicatively in (1+CAR):
#       1.24403 x (1.23068/1.24403) x (1.23087/1.24403) x (1.21384/1.24403) = 1.18808
#    so the LEAN triple (spread 2 bp + financing + lag1 bound) should print CAR 18.81%,
#    against 18.73% if the points simply added. THE TEST: if the measured triple is within
#    +/-0.5 CAR points of 18.81 the three corrections are independent and the loop may keep
#    quoting them one at a time; if it is outside that, there is an interaction and it must
#    be named rather than averaged away.
#
# 3. THE HEADLINE IS THE DEPLOYED CONVENTION, NOT THE BOUND. LEAN cannot fill at the close
#    of the session it decided in, so the LEAN triple overstates the clock. The same
#    composition with S-19's measured deployed clock (1.22192/1.24077 = 0.98481 per session)
#    predicts 19.92%. `scripts/sweep_s22.py` measures that directly by charging financing
#    inside the S-19 pandas book, and it is only readable if that book reproduces LEAN's own
#    financing cell at the backtest convention - the same cross-harness check S-19 passed at
#    corr 0.99650 and 0.09 CAR points.
#
# 4. ONE SCENARIO CELL, LABELLED AS SUCH. 82% of the sample's interest was incurred in
#    2023-2026 (S-21), so the historical average understates the forward cost. The FORWARD
#    cell holds the benchmark flat at today's 3.63% over the whole sample. It is a
#    what-if, not a backtest: it does not claim the strategy would have earned that, only
#    what this much borrowing costs at today's price of money.
#
# 5. WHAT WILL NOT BE CHANGED, WHATEVER THE NUMBER SAYS. S1_SLIPPAGE_BPS stays 0.0,
#    S1_SIGNAL_LAG stays 0 and S1_FINANCING stays off, so the ledger stays on one scale
#    (S-17's and S-21's precedent). The correction belongs in champion.json and BLOCKERS.md
#    as a recorded expectation, not in a default. The control below must reproduce
#    OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3 or nothing here is readable.
#
# Usage:  bash scripts/_s22_runs.sh        (from the repo root)
set -u
cd "$(dirname "$0")/.."

run() { tag="$1"; shift; echo "=== $tag"; env "$@" py -3.11 scripts/backtest.py s1_momo --tag "$tag"; }

# --- the forward-rate benchmark table: the same dates, the price of money on 2026-09-09.
py -3.11 - <<'PY'
from pathlib import Path
import csv
src = Path("data/rates/usd_benchmark.csv")
dst = Path("data/rates/usd_flat_2026.csv")
rows = list(csv.DictReader(src.open(newline="", encoding="utf-8")))
last = float(rows[-1]["rate_pct"])
with dst.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["date", "rate_pct"])
    for r in rows:
        w.writerow([r["date"], f"{last:.2f}"])
print(f"wrote {dst} : {len(rows):,} rows all at {last:.2f}% (S-22 forward scenario)")
PY

# --- control: shipped defaults. Must reproduce a6d6224ce9c70091e5bfa8e96f046bf3
run "S-22 control: shipped defaults, no corrections (hash check)" S1_NOOP=1

# --- the two pairs LEAN has never run (the third, financing+spread, is S-21's 2 bp cell)
run "S-22 pair: clock bound + spread 2 bp" \
    S1_SIGNAL_LAG=1 S1_SLIPPAGE_BPS=2
run "S-22 pair: clock bound + financing, 0 bp" \
    S1_SIGNAL_LAG=1 S1_FINANCING=on

# --- the triple: every correction the three instrument audits found, charged at once
run "S-22 triple: clock bound + financing + spread 2 bp" \
    S1_SIGNAL_LAG=1 S1_FINANCING=on S1_SLIPPAGE_BPS=2

# --- the halves, because the financing half of the correction is not stationary
run "S-22 triple, IS 2012-2019" \
    S1_SIGNAL_LAG=1 S1_FINANCING=on S1_SLIPPAGE_BPS=2 S1_START=2012-01-03 S1_END=2019-12-31
run "S-22 triple, OOS 2020-2026" \
    S1_SIGNAL_LAG=1 S1_FINANCING=on S1_SLIPPAGE_BPS=2 S1_START=2020-01-02 S1_END=2026-09-04

# --- the scenario: the same book with money priced at today's 3.63% for the whole sample
run "S-22 forward scenario: triple with the benchmark flat at today's rate" \
    S1_SIGNAL_LAG=1 S1_FINANCING=on S1_SLIPPAGE_BPS=2 S1_FIN_RATES=data/rates/usd_flat_2026.csv
