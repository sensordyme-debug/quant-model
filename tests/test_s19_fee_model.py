"""S-44: the S-track's shared commission replica is LEAN's US-equity IB fee model.

`sweep_s19.commission` is the fee function of `sweep_s19.simulate`, which S-22/S-23/S-24/S-31
and `verify_s31` execute and which S-25/S-39/S-21 import by name. Every dollar column and every
CAR figure the daily track has ever quoted to the owner passes through it, so the thing worth
pinning is not a number but a *transcription*: it must equal the engine, and it must equal the
one other replica in this repo that was written independently from the same source
(`sweep_d7.lean_ib_fee`, D-7, itself pinned against the champion's recorded fees).

Not `runner`-marked: nothing here is executed by the 09:25 intraday launch.

Four things a future edit could silently break, in descending order of cost:

1. The constants. `InteractiveBrokersFeeModel.cs:150` is `feePerShare 0.005, minimumFee 1,
   maximumFeeRate 0.005`. The pre-S-44 file had the cap at 0.01, twice the engine's.
2. The SHAPE. The minimum and the cap are an `if`/**`else if`**, not a clamp. A `min(max(...))`
   lets the cap pull a fee below the $1 floor, which the engine never does - that half of the
   defect was not in S-44's item text and only a transcription finds it.
3. The single source. `sweep_s21` used to carry its own fee function - IBKR's *tiered*
   schedule - under a docstring calling it "the same model". It must now BE the same object.
4. The legacy forms, verbatim, so any ledger row written before 2026-09-13 stays reproducible.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

sweep_s19 = pytest.importorskip("sweep_s19")
sweep_s21 = pytest.importorskip("sweep_s21")
sweep_d7 = pytest.importorskip("sweep_d7")

commission = sweep_s19.commission
legacy = sweep_s19.commission_legacy

CHAMPION_EVENTS = (REPO / "results" / "s1_momo" / "20260911T145705Z"
                   / "S1MomentumRotationAlgorithm-order-events.json")
CHAMPION_FEES = 27199.76

GRID_Q = [1, 2, 5, 10, 50, 100, 150, 199, 200, 201, 500, 1_000, 5_000, 50_000]
GRID_PX = [0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.49, 0.5, 0.51, 0.75, 0.99, 1.0, 1.01,
           2.0, 5.0, 9.5, 50.0, 97.16, 500.0, 1_000.0]


# ------------------------------------------------------------------ 1. the constants

def test_constants_are_the_engines():
    assert sweep_s19.FEE_PER_SHARE == 0.005
    assert sweep_s19.FEE_MIN == 1.00
    assert sweep_s19.FEE_MAX_FRAC == 0.005, "cap rate is maximumFeeRate 0.005m, not 0.01"


def test_matches_the_independent_d7_replica_everywhere_on_the_grid():
    for q in GRID_Q:
        for px in GRID_PX:
            assert commission(q, px) == sweep_d7.lean_ib_fee(q, px), (q, px)
            assert commission(-q, px) == sweep_d7.lean_ib_fee(-q, px), (-q, px)


@pytest.mark.skipif(not CHAMPION_EVENTS.exists(), reason="champion run not on disk")
def test_reproduces_the_champions_recorded_fees_to_the_cent():
    fills = [e for e in json.loads(CHAMPION_EVENTS.read_text(encoding="utf-8"))
             if e.get("status") == "filled"]
    assert len(fills) == 5128
    total = sum(commission(f["fillQuantity"], f["fillPrice"]) for f in fills)
    assert abs(total - CHAMPION_FEES) < 0.005


# ------------------------------------------------------------------------ 2. the shape

def test_the_minimum_is_not_subject_to_the_cap():
    """One share at a penny: the engine charges the $1 floor, a clamp would charge $0.0001."""
    assert commission(1, 0.01) == pytest.approx(1.0)
    assert legacy(1, 0.01) == pytest.approx(0.0001)


def test_the_cap_binds_only_below_a_dollar():
    assert commission(10_000, 0.50) == pytest.approx(0.005 * 10_000 * 0.50)   # capped
    assert commission(10_000, 2.00) == pytest.approx(0.005 * 10_000)          # per-share
    assert commission(10_000, 1.00) == pytest.approx(0.005 * 10_000)          # exactly at it


def test_sign_and_zero():
    assert commission(-500, 10.0) == commission(500, 10.0)
    assert commission(500, -10.0) == commission(500, 10.0)
    assert commission(0, 10.0) == pytest.approx(1.0)      # the floor, as the engine does


# ---------------------------------------------------------------- 3. the single source

def test_sweep_s21_uses_the_same_object_not_a_copy():
    assert sweep_s21.commission is sweep_s19.commission


# ---------------------------------------------------------------- 4. the legacy forms

def test_legacy_forms_are_preserved_verbatim():
    assert legacy(1_000, 10.0) == pytest.approx(min(max(1.00, 0.005 * 1_000), 0.01 * 10_000))
    tiered = sweep_s21.commission_tiered_legacy
    assert tiered(1_000, 10.0) == pytest.approx(min(max(0.0035 * 1_000, 0.35), 0.01 * 10_000))


def test_legacy_and_engine_agree_outside_the_two_bands():
    """The licence for changing shared code: they part only under $1 or under $200 of value."""
    for q in GRID_Q:
        for px in GRID_PX:
            if px < 1.0 or (0.005 * q < 1.0 and q * px < 200.0):
                continue
            assert commission(q, px) == pytest.approx(legacy(q, px)), (q, px)
