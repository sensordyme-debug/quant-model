#!/usr/bin/env bash
# S-21: what it costs to finance the book, which LEAN has never charged.
#
# THE DEFECT, read off the engine source rather than inferred (same method as S-17):
#   Common/Brokerages/DefaultBrokerageModel.cs:368  GetMarginInterestRateModel
#       -> MarginInterestRateModel.Null
#   Common/Securities/IMarginInterestRateModel.cs:41  NullMarginInterestRateModel
#       -> ApplyMarginInterestRate(...) {}      # an empty method body
#   Common/Brokerages/InteractiveBrokersBrokerageModel.cs  does NOT override it.
# So every backtest in this repository has borrowed money for free. The shipped champion
# carries 1.50x gross against 1.00x of equity, i.e. it runs a debit balance of about half
# its equity every day it is invested, and it pays nothing for it. The other side is real
# too: the regime gate puts the book in cash on 16.0% of sessions (S-20) and LEAN pays no
# credit interest on that cash either.
#
# WHY THE SIGN IS NOT OBVIOUS AND WHY THIS IS NOT A ONE-LINE CORRECTION: the benchmark is
# not stationary over the sample. Effective fed funds (FRED DFF, IBKR's USD "BM"), annual
# mean, with the blended IBKR Pro loan rate on a $500k debit beside it:
#     2012 0.14 / 1.24    2015 0.13 / 1.23    2018 1.83 / 2.93    2021 0.08 / 1.18
#     2013 0.11 / 1.21    2016 0.39 / 1.49    2019 2.16 / 3.26    2022 1.69 / 2.79
#     2014 0.09 / 1.19    2017 1.00 / 2.10    2020 0.37 / 1.47    2023 5.03 / 6.13
#                                                                 2024 5.14 / 6.24
#                                                                 2025 4.21 / 5.31
#                                                                 2026 3.63 / 4.73
# The cost is therefore concentrated in the out-of-sample half, which is the half every
# recent promotion has leaned on. This is the opposite of a cosmetic correction.
#
# PRE-REGISTERED BEFORE ANY FULL CELL RAN. Recorded here so the write-up cannot drift:
#
# 1. THIS IS A MEASUREMENT, NOT A CANDIDATE. Charging a cost can only lower CAR, so no cell
#    below can be promoted and `evaluate.py` is not the judge of the primary. The three
#    deliverables are (a) the corrected CAR of the shipped champion, (b) the split by half,
#    because the rate regime is not stationary, and (c) the corrected margin-budget
#    frontier, because that frontier is *exactly* a decision about how large a debit
#    balance to carry and it is the open owner question in BLOCKERS.md.
#
# 2. THE A-PRIORI ESTIMATE, written down before the first full run, so the measurement can
#    be wrong rather than merely reported: mean debit ~0.50x equity (1.50x gross), mean
#    blended loan rate over 2012-2026 ~2.9%, so ~1.45 CAR points full period, and roughly
#    double that over 2023-2026. If the measured drag is far from that, the accrual is
#    wrong and must be debugged before it is believed.
#
# 3. THE SCHEDULE IS A PARAMETER, NOT A FACT. The primary uses IBKR Pro's published tiers
#    (+1.50/+1.00/+0.75/+0.50 over BM, blended per tranche; credit at BM-0.50 above $10k).
#    `S1_FIN_SPREAD` shifts all of them together, and the FLOOR cell at -1.50 charges the
#    benchmark itself - no broker can do better than that, so the -1.50 row is the part of
#    the correction that is arithmetic rather than a price list.
#
# 4. WHAT WILL NOT BE CHANGED, WHATEVER THE NUMBER SAYS. `S1_FINANCING` stays defaulted
#    **off** and the ledger stays on one scale, exactly as S-17 left `S1_SLIPPAGE_BPS` at
#    0.0 rather than silently re-basing every past row. The correction belongs in
#    champion.json and BLOCKERS.md as a recorded column, not in the default. The control
#    below must reproduce OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3 or nothing here is
#    readable.
#
# 5. THE ONE THING THAT COULD CHANGE A DECISION, stated in advance: if financing flattens or
#    inverts the margin-budget frontier (0.75 -> 0.80 -> 0.82 currently reads 24.403 /
#    25.903 / 26.474 with the cost omitted), then the owner's open question in BLOCKERS.md
#    is being asked on numbers that overstate the reward, and the corrected table replaces
#    it there. That is a correction to an owner brief, not a change of risk posture, and the
#    loop may make it.
#
# Usage:  bash scripts/_s21_runs.sh        (from the repo root)
set -u
cd "$(dirname "$0")/.."

run() { tag="$1"; shift; echo "=== $tag"; env "$@" py -3.11 scripts/backtest.py s1_momo --tag "$tag"; }

# --- control: shipped defaults, financing off. Must reproduce a6d6224ce9c70091e5bfa8e96f046bf3
run "S-21 control: shipped defaults, financing off (hash check)" S1_NOOP=1

# --- primary: IBKR Pro tiers on the historical benchmark
run "S-21 primary: financing on, IBKR Pro tiers, 0 bp" S1_FINANCING=on

# --- floor: the benchmark itself, no broker markup at all
run "S-21 floor: financing on at the benchmark (spread shift -1.50), 0 bp" \
    S1_FINANCING=on S1_FIN_SPREAD=-1.50

# --- the halves, because the rate regime is not stationary
run "S-21 primary, IS 2012-2019, 0 bp" \
    S1_FINANCING=on S1_START=2012-01-03 S1_END=2019-12-31
run "S-21 primary, OOS 2020-2026, 0 bp" \
    S1_FINANCING=on S1_START=2020-01-02 S1_END=2026-09-04

# --- the same cell at the cost model the S-18 promotion was decided on
run "S-21 primary: financing on, 2 bp" S1_FINANCING=on S1_SLIPPAGE_BPS=2

# --- the owner's frontier, re-priced with the cost of the leverage it buys
run "S-21 owner frontier: financing on, margin_budget 0.80, 0 bp" \
    S1_FINANCING=on S1_MARGIN_BUDGET=0.80
run "S-21 owner frontier: financing on, margin_budget 0.82, 0 bp" \
    S1_FINANCING=on S1_MARGIN_BUDGET=0.82
