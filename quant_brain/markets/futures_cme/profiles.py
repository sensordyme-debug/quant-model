"""Prop-firm rule archetypes, as configuration.

Part 5: "Do not hard-code one firm's rules into the core. Individual prop firms should be
configuration/adapters on top of that interface." These are the configurations.

They are named by **rule shape**, not by firm, and that is deliberate. Firms change their
rulebooks without notice and several have changed trailing conventions mid-programme; a
profile called `topstep_50k` frozen in source in 2026 is a liability the first time it is
wrong, because it looks authoritative. A profile called `EOD_TRAILING_50K` states what it
models and forces whoever deploys it to confirm the numbers against the live rulebook.

    RULE, BEFORE ANY REAL EVALUATION IS PURCHASED
    ---------------------------------------------
    Copy the closest archetype, set every field from the firm's current written rules, save
    it as JSON under live/propfirm/<firm>_<size>.json, and cite that file in the journal
    entry. `PropFirmProfile.from_dict` rejects unknown keys, so a rule the firm has that this
    module does not model fails loudly at load rather than being silently ignored.

The three archetypes cover the conventions actually in the market: end-of-day trailing,
intraday trailing (strictly harsher on the same equity path), and a static floor.
"""
from __future__ import annotations

import datetime as dt

from quant_brain.markets.futures_cme.propfirm import PropFirmProfile, TrailingMode

#: US index futures see the bulk of their scheduled-event risk in these windows: the 08:30 ET
#: macro releases (CPI, PPI, NFP, claims) and the 14:00 ET FOMC statement. Blocking new risk
#: across them is the most common firm-imposed news rule and also, independently, a sane
#: default - F-2a's 0.488 bps cost floor is a calm-tape number and spreads blow out here.
DEFAULT_BLACKOUTS: tuple[tuple[dt.time, dt.time], ...] = (
    (dt.time(8, 28), dt.time(8, 33)),
    (dt.time(13, 58), dt.time(14, 3)),
)


EOD_TRAILING_50K = PropFirmProfile(
    name="EOD_TRAILING_50K",
    starting_balance=50_000.0,
    daily_loss_limit=1_100.0,
    max_drawdown=2_000.0,
    trailing_mode=TrailingMode.EOD,
    # Threshold stops climbing once it reaches the starting balance, so the account cannot
    # fail below breakeven after it has earned the buffer. This one field is worth more to a
    # strategy's survival than most parameter choices.
    trailing_locks_at=50_000.0,
    daily_loss_ends_account=False,
    profit_target=3_000.0,
    min_trading_days=5,
    max_single_day_profit_share=0.40,
    max_total_contracts=5,
    max_contracts_per_symbol={"ES": 5, "MES": 50, "NQ": 5, "MNQ": 50},
    allow_overnight=False,
    flat_before_close_minutes=15,
    blackout_windows=DEFAULT_BLACKOUTS,
    evaluation_fee=165.0,
    payout_on_pass=0.0,
    profit_split=0.90,
)


INTRADAY_TRAILING_50K = PropFirmProfile(
    name="INTRADAY_TRAILING_50K",
    starting_balance=50_000.0,
    # No separate daily cap: the intraday trailing threshold already ends the day, and
    # stacking both would model a firm that does not exist.
    daily_loss_limit=None,
    max_drawdown=2_500.0,
    trailing_mode=TrailingMode.INTRADAY,
    trailing_locks_at=None,          # trails forever - the harshest common convention
    profit_target=3_000.0,
    min_trading_days=0,
    max_single_day_profit_share=None,
    max_total_contracts=3,
    max_contracts_per_symbol={"ES": 3, "MES": 30, "NQ": 3, "MNQ": 30},
    allow_overnight=False,
    flat_before_close_minutes=15,
    blackout_windows=DEFAULT_BLACKOUTS,
    evaluation_fee=137.0,
    payout_on_pass=0.0,
    profit_split=0.90,
)


STATIC_DRAWDOWN_100K = PropFirmProfile(
    name="STATIC_DRAWDOWN_100K",
    starting_balance=100_000.0,
    daily_loss_limit=2_000.0,
    max_drawdown=3_000.0,
    trailing_mode=TrailingMode.NONE,     # fixed floor at 97,000
    profit_target=6_000.0,
    min_trading_days=10,
    max_single_day_profit_share=0.30,
    max_total_contracts=10,
    max_contracts_per_symbol={"ES": 10, "MES": 100, "NQ": 10, "MNQ": 100},
    allow_overnight=False,
    flat_before_close_minutes=15,
    blackout_windows=DEFAULT_BLACKOUTS,
    evaluation_fee=550.0,
    payout_on_pass=0.0,
    profit_split=0.90,
)


ARCHETYPES: dict[str, PropFirmProfile] = {
    p.name: p for p in (EOD_TRAILING_50K, INTRADAY_TRAILING_50K, STATIC_DRAWDOWN_100K)
}


def get(name: str) -> PropFirmProfile:
    try:
        return ARCHETYPES[name]
    except KeyError:
        raise KeyError(
            f"unknown archetype {name!r}; known: {', '.join(sorted(ARCHETYPES))}. "
            f"A real firm's account should be a JSON profile, not an archetype - "
            f"see this module's docstring."
        ) from None
