"""O-1 wiring confirmation: one calendar year of ORB with the iv_gate off / high / low.

The gate verdict is decided by the partition study in `scripts/sweep_o1.py` (2,686 cached
sessions). This is the smaller, separate job of proving the `iv_gate` parameter that ships in
`algorithms/intraday/orb/signal.py` actually does what the partition assumed - that it blocks
whole sessions, keeps roughly half of them, and is a no-op when off - and of putting the cells in
the ledger as real backtests rather than as a partition of someone else's series. 2024 is chosen
because it is the most recent complete year and sits in the regime that is least negative.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
os.environ.setdefault("INTRADAY_DATA_DIR", str(REPO / "data" / "minute_alpaca"))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "algorithms" / "intraday"))

import intraday_backtest as ib  # noqa: E402
from base import features  # noqa: E402
from intraday_common import UNIVERSE, load_universe  # noqa: E402

LO, HI = dt.date(2024, 1, 1), dt.date(2024, 12, 31)


def main() -> int:
    bars = load_universe(UNIVERSE, LO, HI)
    feats = {s: features(d) for s, d in bars.items()}
    strat = ib.load_strategy("active")
    print(f"{len(bars)} symbols loaded for {LO}..{HI}", flush=True)
    for gate in ("", "high", "low"):
        params = {"alloc": {"orb": 1.0, "vwap_trend": 0.0, "late_momo": 0.0},
                  "per_symbol": 0.15, "gross": 1.5,
                  "sub_params": {"orb": {"disaster_atr": 4.0, "iv_gate": gate}}}
        s = ib.run(strat, bars, 1_000_000.0, {**strat.PARAMS, **params}, LO, HI, False, feats_all=feats)
        d = s.pop("daily")
        traded = int((d["trades"] > 0).sum())
        print(f"gate={gate or 'off':<4} sessions {s['sessions']:>3}  traded days {traded:>3}  "
              f"$/day {s['avg_daily_pnl']:>8,.0f}  trades {s['trades']:>6}  "
              f"Sharpe {s['sharpe']:>6.2f}  CAR {s['cagr_pct']:>7.2f}%", flush=True)
        ib.record("active", f"O-1 confirmation: orb alone, iv_gate={gate or 'off'} on iv_atm_1w "
                            f"(prior-day EOD vs trailing 60-day median), 2024", s, params, LO, HI)
    return 0


if __name__ == "__main__":
    sys.exit(main())
