"""scripts/intraday_trader.py: Trader.targets_to_orders - the sleeve's hard caps and its band.

These four constants are the framework's promise to the account, enforced *after* the strategy
has spoken, so a signal bug cannot place size the risk model never agreed to:
GROSS_HARD_CAP (1.6x), PER_SYMBOL_HARD_CAP (0.20), MIN_CHANGE (2% of sleeve equity),
and the equity base itself (NAV x --equity-frac, never NAV).
"""
from __future__ import annotations

import intraday_trader as it
import pytest
from intraday_common import GROSS_HARD_CAP, MIN_CHANGE, PER_SYMBOL_HARD_CAP

EQUITY = 100_000.0


def trader(pos=None, equity_frac=1.0):
    t = it.Trader(strategy=None, params={}, equity_frac=equity_frac, book=it.Book(),
                  executor=None, dry_run=True, mode="test")
    t.book.pos.update(pos or {})
    return t


# --------------------------------------------------------------------------- basic sizing
def test_weight_becomes_shares_floored_toward_zero():
    t = trader()
    assert t.targets_to_orders({"NVDA": 0.10}, {"NVDA": 300.0}, EQUITY) == {"NVDA": 33}   # 33.33 -> 33


def test_a_short_weight_floors_toward_zero_as_well():
    t = trader()
    assert t.targets_to_orders({"NVDA": -0.10}, {"NVDA": 300.0}, EQUITY) == {"NVDA": -33}


def test_the_equity_base_is_nav_times_equity_frac():
    """The caller passes `nav * equity_frac` as `equity`; half the fraction is half the shares."""
    t = trader()
    full = t.targets_to_orders({"NVDA": 0.10}, {"NVDA": 100.0}, EQUITY)
    half = t.targets_to_orders({"NVDA": 0.10}, {"NVDA": 100.0}, EQUITY / 2)
    assert full == {"NVDA": 100} and half == {"NVDA": 50}


# --------------------------------------------------------------------------- the rebalance band
def test_a_change_below_min_change_is_not_traded():
    t = trader({"NVDA": 99})
    # target is 100 shares, so the delta is 1 share = $100 = 0.1% of equity, well under the 2% band.
    assert t.targets_to_orders({"NVDA": 0.10}, {"NVDA": 100.0}, EQUITY) == {}
    assert MIN_CHANGE == 0.02


def test_a_change_at_the_band_is_traded():
    t = trader({"NVDA": 80})
    # target 100, delta 20 shares at $100 = $2,000 = exactly 2% of equity.
    assert t.targets_to_orders({"NVDA": 0.10}, {"NVDA": 100.0}, EQUITY) == {"NVDA": 20}


def test_an_exit_always_clears_the_band():
    """Unlike the daily runner, this sleeve must be able to reach flat at any size, because it is
    required to be flat by 15:38 ET. A residual position below MIN_CHANGE would never leave."""
    t = trader({"NVDA": 3})
    assert t.targets_to_orders({}, {"NVDA": 100.0}, EQUITY) == {"NVDA": -3}
    assert t.targets_to_orders({"NVDA": 0.0}, {"NVDA": 100.0}, EQUITY) == {"NVDA": -3}


def test_a_held_name_with_no_price_is_skipped_not_guessed():
    t = trader({"NVDA": 100})
    assert t.targets_to_orders({}, {}, EQUITY) == {}
    assert t.targets_to_orders({}, {"NVDA": 0.0}, EQUITY) == {}


def test_no_order_when_the_book_already_matches_the_target():
    t = trader({"NVDA": 100})
    assert t.targets_to_orders({"NVDA": 0.10}, {"NVDA": 100.0}, EQUITY) == {}


# --------------------------------------------------------------------------- hard caps
def test_per_symbol_cap_clamps_a_single_oversized_weight():
    t = trader()
    orders = t.targets_to_orders({"NVDA": 0.90}, {"NVDA": 100.0}, EQUITY)
    assert orders == {"NVDA": int(PER_SYMBOL_HARD_CAP * EQUITY / 100.0)} == {"NVDA": 200}


def test_per_symbol_cap_clamps_a_short_symmetrically():
    t = trader()
    assert t.targets_to_orders({"NVDA": -0.90}, {"NVDA": 100.0}, EQUITY) == {"NVDA": -200}


def test_gross_cap_scales_every_weight_down_proportionally():
    """Ten names at 0.20 is 2.0x gross; the cap scales all of them by 1.6/2.0 = 0.8 so each
    lands at 0.16, below the per-symbol cap, and the book's gross is exactly 1.6x."""
    names = [f"S{i}" for i in range(10)]
    targets = {s: 0.20 for s in names}
    prices = {s: 100.0 for s in names}
    orders = trader().targets_to_orders(targets, prices, EQUITY)
    assert set(orders) == set(names)
    assert all(q == 160 for q in orders.values())
    gross = sum(abs(q) * 100.0 for q in orders.values())
    assert gross == pytest.approx(GROSS_HARD_CAP * EQUITY)


def test_gross_cap_counts_shorts_and_does_not_net_them():
    """A 0.9/-0.9 pair is 1.8x gross, not 0x. Netting would let the sleeve run unbounded risk."""
    targets = {f"S{i}": (0.18 if i % 2 == 0 else -0.18) for i in range(10)}
    prices = {f"S{i}": 100.0 for i in range(10)}
    orders = trader().targets_to_orders(targets, prices, EQUITY)
    gross = sum(abs(q) * 100.0 for q in orders.values())
    assert gross <= GROSS_HARD_CAP * EQUITY + 1.0
    assert sum(1 for q in orders.values() if q < 0) == 5


def test_a_book_within_both_caps_is_left_alone():
    targets = {"NVDA": 0.15, "TSLA": 0.15, "AAPL": 0.15}
    prices = {s: 100.0 for s in targets}
    orders = trader().targets_to_orders(targets, prices, EQUITY)
    assert orders == {"NVDA": 150, "TSLA": 150, "AAPL": 150}


def test_caps_are_the_values_the_journal_and_agents_md_quote():
    assert (GROSS_HARD_CAP, PER_SYMBOL_HARD_CAP, MIN_CHANGE) == (1.6, 0.20, 0.02)


def test_the_trader_uses_the_shared_constants_and_not_its_own_copies():
    """`intraday_trader` does `from intraday_common import GROSS_HARD_CAP, ...`, which binds a
    *copy* into its namespace. AGENTS.md's guarantee is that the backtester and the live trader
    cannot drift; a constant redefined in one module and not the other is exactly that drift, and
    a value assertion against intraday_common alone would not see it."""
    import intraday_common as ic
    for name in ("MIN_CHANGE", "PER_SYMBOL_HARD_CAP", "GROSS_HARD_CAP", "DAILY_LOSS_LIMIT",
                 "FLATTEN_MINUTE", "EXIT_MINUTE"):
        assert getattr(it, name) == getattr(ic, name), f"{name} differs between trader and common"
