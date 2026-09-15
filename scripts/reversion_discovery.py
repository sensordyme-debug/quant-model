"""A properly-powered discovery run on the panel that has the power.

WHY THIS IS DIFFERENT FROM EVERY PRIOR DISCOVERY PHASE
--------------------------------------------------------
Every discovery run in this repository so far has been executed on 251-312 futures sessions.
That store has now twice produced a "finding" that a larger sample destroyed: the overnight
drift (a calendar artifact) and the failed reversal (an instrument artifact, killed by QQQ on
the same index). The minimum correlation the futures panel can resolve is 0.111; the ETF panel
resolves 0.038.

So this run happens on SPY, QQQ, IWM and DIA over 2016-2026 - roughly 2,600 sessions each,
four instruments, three of which track indices with genuinely different constituents. Futures
confirmation comes afterwards, and only for something that survives here.

THE MECHANISM, CHOSEN FROM EVIDENCE RATHER THAN FROM A LIST
--------------------------------------------------------------
Four phases of measurement point at one family and away from the others:

    Intraday index sessions displace LESS than a random walk. Median |net move| over the
    random-walk expectation is 0.655-0.738 across eight instruments and eleven years. The
    asset class mean-reverts intraday; that is the single most robust fact this programme has
    established.

    Directional information from overnight or cross-market sources is dead - 46, then 110,
    then 4,788 tests.

    Volatility IS forecastable out of sample at R-squared 0.46-0.51, robust in every regime
    partition. Useless for direction, but exactly the right input for SIZING.

    Cost is binding at one- to two-minute holds and negligible at session horizon: the
    break-even hit rate at a full-session horizon is 50.1-50.6%.

Every mechanism in the existing library is a one- to two-minute scalp, which is the horizon
where cost is most binding, in an asset class whose edge is mean reversion. This run tests
mean reversion at holds long enough for cost not to dominate. That is the specific untested
combination, and it is why this is worth one more discovery run rather than a fifth sweep.

THE TARGET SPEC, COMPUTED FROM THE RULES
------------------------------------------
Because Topstep's trailing MLL LOCKS at breakeven once equity reaches +$2,000, the barrier is
far more survivable than a permanently trailing one. Simulated against the real mechanics:

    Sharpe 1.0 -> 49% pass    Sharpe 1.5 -> 58%    Sharpe 2.0 -> 69%    Sharpe 3.0 -> 83%

and per-session volatility has an optimum near $200-300: at $100 it takes 178 sessions to
reach the lock, at $800 it breaches before reaching it.

So the hunt is for an annualised Sharpe around 1.5 or better on net P&L. Not 3. That is a
real target rather than a fantasy, and it is what makes this worth running.

DISCIPLINE, FIXED BEFORE ANY RESULT
-------------------------------------
    TRAIN     2016-01 .. 2021-12   variant selection happens here and nowhere else
    VALIDATE  2022-01 .. 2023-12   a variant must survive here to reach the holdout
    HOLDOUT   2024-01 .. 2026-09   inspected ONCE, at the end, for survivors only

The holdout was touched once before, by a single preregistered bucket test in an earlier phase
on a different question. That is disclosed; it is the cleanest window available.

Twelve preregistered variants. Not a sweep.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

SYMBOLS = ("SPY", "QQQ", "IWM", "DIA")
TRAIN_END, VALIDATE_END = "2021-12-31", "2023-12-31"

#: Warm-up before any entry: the anchor needs history and the open is its own regime.
WARMUP_BARS = 60
#: No new entries after this bar, so every position can close inside the session.
LAST_ENTRY_BAR = 330


@dataclass(frozen=True)
class Variant:
    name: str
    anchor: str      # "vwap" or "ma60"
    sigma: float     # entry deviation in rolling standard deviations
    max_hold: int    # bars; exit earlier on reversion to the anchor


#: PREREGISTERED. Twelve variants, fixed before any result was computed.
VARIANTS: tuple[Variant, ...] = tuple(
    Variant(f"{a}.{s:g}sd.{h}m", a, s, h)
    for a in ("vwap", "ma60") for s in (1.5, 2.0, 2.5) for h in (30, 60))


def load(sym: str) -> list[pd.DataFrame]:
    d = pd.read_parquet(REPO / "data" / "minute_alpaca" / f"{sym}.parquet")
    t = d.index
    if getattr(t, "tz", None) is None:
        t = t.tz_localize("UTC")
    t = t.tz_convert("America/New_York")
    d = d.assign(day=t.date).sort_index()
    return [g.reset_index(drop=True) for _, g in d.groupby("day", sort=True)
            if len(g) >= 380]


def signals(g: pd.DataFrame, v: Variant) -> tuple[np.ndarray, np.ndarray]:
    """Anchor and deviation in sigmas. Both strictly causal within the session."""
    c = g["c"].to_numpy(dtype=float)
    vol = g["v"].to_numpy(dtype=float)
    if v.anchor == "vwap":
        tp = (g["h"].to_numpy(float) + g["l"].to_numpy(float) + c) / 3.0
        cum_v = np.cumsum(vol)
        anchor = np.where(cum_v > 0, np.cumsum(tp * vol) / np.maximum(cum_v, 1e-9), c)
    else:
        s = pd.Series(c).rolling(60, min_periods=20).mean()
        anchor = s.to_numpy(dtype=float)
    dev = c - anchor
    sd = pd.Series(dev).rolling(60, min_periods=20).std().to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(sd > 1e-9, dev / sd, 0.0)
    return anchor, np.nan_to_num(z, nan=0.0)


def run_session(g: pd.DataFrame, v: Variant) -> list[dict]:
    """One session. Fade a deviation; exit on reversion to the anchor, a hold cap, or the bell.

    One position at a time, no pyramiding. Entry and exit both at the bar close, which is the
    convention the rest of the repository uses.
    """
    c = g["c"].to_numpy(dtype=float)
    anchor, z = signals(g, v)
    n = len(c)
    out = []
    i = WARMUP_BARS
    while i < min(n - 2, LAST_ENTRY_BAR):
        if not np.isfinite(z[i]) or abs(z[i]) < v.sigma:
            i += 1
            continue
        d = -int(np.sign(z[i]))          # fade the deviation
        entry, entry_bar = c[i], i
        end = min(i + v.max_hold, n - 1)
        exit_bar, reason = end, "time"
        for k in range(i + 1, end + 1):
            # reversion target is the anchor itself
            if (d > 0 and c[k] >= anchor[k]) or (d < 0 and c[k] <= anchor[k]):
                exit_bar, reason = k, "reversion"
                break
        if exit_bar >= n - 1:
            reason = "flatten"
        pts = (c[exit_bar] - entry) * d
        seg = c[i:exit_bar + 1]
        mfe = float((seg.max() - entry) * d) if d > 0 else float((entry - seg.min()) * -d * -1)
        mfe = float(np.max((seg - entry) * d))
        mae = float(np.min((seg - entry) * d))
        out.append({"session": g["day"].iloc[0], "entry_bar": entry_bar,
                    "exit_bar": exit_bar, "direction": d, "entry": entry,
                    "points": pts, "ret_bps": pts / entry * 1e4,
                    "bars": exit_bar - entry_bar, "reason": reason,
                    "mfe_bps": mfe / entry * 1e4, "mae_bps": mae / entry * 1e4,
                    "z": z[i]})
        i = exit_bar + 1
    return out


def evaluate(trades: pd.DataFrame, cost_bps: float) -> dict:
    if not len(trades):
        return {"trades": 0}
    net = trades["ret_bps"].to_numpy(dtype=float) - cost_bps
    daily = pd.Series(net, index=trades["session"]).groupby(level=0).sum()
    sd = float(daily.std(ddof=1)) if len(daily) > 1 else 0.0
    wins, losses = net[net > 0], net[net < 0]
    eq = np.cumsum(daily.to_numpy())
    return {
        "trades": len(net), "sessions": int(daily.size),
        "bps_per_trade": float(net.mean()), "bps_per_day": float(daily.mean()),
        "win_rate": float((net > 0).mean()),
        "profit_factor": (float(wins.sum() / -losses.sum())
                          if len(losses) and losses.sum() < 0 else np.nan),
        "sharpe": float(daily.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0,
        "t_stat": (float(daily.mean() / (sd / np.sqrt(len(daily))))
                   if sd > 0 and len(daily) > 1 else 0.0),
        "max_dd_bps": float((eq - np.maximum.accumulate(eq)).min()),
        "trades_per_day": len(net) / max(1, daily.size),
        "median_bars": float(trades["bars"].median()),
        "pct_reversion": float((trades.reason == "reversion").mean()),
        "mfe_mae": float(abs(trades.mfe_bps.mean() / trades.mae_bps.mean()))
        if trades.mae_bps.mean() else np.nan,
    }


def main() -> int:
    #: Round-turn cost in basis points. An MNQ round turn is $1.22 on a ~$48,000 notional
    #: micro contract = 0.25 bps; one tick of slippage adds $0.50 = 0.10 bps. Charged at
    #: 0.5 bps, which is DOUBLE the modelled futures cost, so the screen is conservative.
    cost_bps = 0.5

    print("=" * 108)
    print("REVERSION DISCOVERY ON THE HIGH-POWER PANEL")
    print(f"{len(VARIANTS)} preregistered variants x {len(SYMBOLS)} instruments")
    print(f"train <= {TRAIN_END} | validate <= {VALIDATE_END} | holdout after, "
          f"INSPECTED ONCE AT THE END")
    print(f"round-turn cost charged: {cost_bps} bps (2x the modelled MNQ cost)")
    print("=" * 108)

    store: dict = {}
    for sym in SYMBOLS:
        sess = load(sym)
        store[sym] = sess
        print(f"  {sym}: {len(sess)} sessions")

    rows = []
    for v in VARIANTS:
        for sym in SYMBOLS:
            tr = pd.DataFrame([r for g in store[sym] for r in run_session(g, v)])
            if not len(tr):
                continue
            tr["d"] = pd.to_datetime(tr["session"])
            train = tr[tr.d <= TRAIN_END]
            val = tr[(tr.d > TRAIN_END) & (tr.d <= VALIDATE_END)]
            rows.append({"variant": v.name, "symbol": sym, "anchor": v.anchor,
                         "sigma": v.sigma, "hold": v.max_hold,
                         **{f"tr_{k}": x for k, x in evaluate(train, cost_bps).items()},
                         **{f"va_{k}": x for k, x in evaluate(val, cost_bps).items()}})
    df = pd.DataFrame(rows)
    df.to_csv(REPO / "research" / "reversion_discovery.csv", index=False)

    print("\n" + "=" * 108)
    print("TRAIN (2016-2021) — selection happens here and nowhere else")
    print("=" * 108)
    agg = df.groupby("variant").agg(
        n_sym=("symbol", "size"), trades=("tr_trades", "sum"),
        bps=("tr_bps_per_trade", "mean"), sharpe=("tr_sharpe", "mean"),
        pos=("tr_bps_per_trade", lambda s: int((s > 0).sum())),
        tpd=("tr_trades_per_day", "mean"), bars=("tr_median_bars", "mean"),
        rev=("tr_pct_reversion", "mean")).sort_values("sharpe", ascending=False)
    print(f"  {'variant':18} {'trades':>8} {'bps/tr':>8} {'Sharpe':>8} {'pos/4':>6} "
          f"{'tr/day':>7} {'bars':>6} {'%rev':>6}")
    for name, r in agg.iterrows():
        print(f"  {name:18} {int(r.trades):8d} {r.bps:8.3f} {r.sharpe:8.2f} "
              f"{int(r.pos):4d}/4 {r.tpd:7.2f} {r.bars:6.0f} {r.rev:6.1%}")

    print("\n" + "=" * 108)
    print("SELECTION RULE, declared before looking: positive on 4 of 4 instruments in TRAIN")
    print("and mean train Sharpe > 0.5. Survivors go to VALIDATE.")
    print("=" * 108)
    surv = agg[(agg.pos == 4) & (agg.sharpe > 0.5)]
    print(f"  {len(surv)} of {len(agg)} variants survive train selection")
    if len(surv):
        print(f"\n  {'variant':18} {'va trades':>10} {'va bps/tr':>10} {'va Sharpe':>10} "
              f"{'va pos/4':>9} {'va t':>7}")
        for name in surv.index:
            s = df[df.variant == name]
            print(f"  {name:18} {int(s.va_trades.sum()):10d} "
                  f"{s.va_bps_per_trade.mean():10.3f} {s.va_sharpe.mean():10.2f} "
                  f"{int((s.va_bps_per_trade > 0).sum()):7d}/4 {s.va_t_stat.mean():7.2f}")
    print(f"\nwrote {REPO / 'research' / 'reversion_discovery.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
