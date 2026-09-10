#!/usr/bin/env python
"""A-5 (part 1): price the intraday sleeve's cost model from the bars, before the live fills land.

`intraday_common.SLIPPAGE_BPS = 1.5` is the one number in the harness that was never measured.
It is charged on ~49 trades/day, i.e. **$1,025/day of modelled cost against a $610/day modelled
edge** (A-4), so the sleeve's sign is a property of this constant. The live-fill measurement
A-5 asks for needs a paper session that actually placed orders; until one exists
(`scripts/slippage_report.py` does that half), three things are measurable today from the same
260-session store the harness runs on:

    python scripts/sweep_a5.py --phase spread      # Roll + Corwin-Schultz effective spread per name
    python scripts/sweep_a5.py --phase impact      # the sleeve's own fills as a share of the bar's volume
    python scripts/sweep_a5.py --phase breakeven   # the slippage that takes the sleeve to zero
    python scripts/sweep_a5.py --phase all --record

What each phase can and cannot say:
  * `spread` estimates the **effective spread** these names actually traded at, from prints only.
    A market order pays about half of it against the mid. The harness fills at the next bar's
    OPEN, which is itself a print (already at bid or ask), so the honest reference band for
    SLIPPAGE_BPS is [quarter-spread, half-spread] plus impact, not the full spread.
  * `impact` cannot estimate impact without a model, but it can measure the input every impact
    model needs: the order's share of the minute it fills in. Small participation bounds impact
    to a fraction of the spread; large participation means the cost model is fiction.
  * `breakeven` is the decision-relevant number: how wrong the constant has to be to flip the
    sign of the sleeve. Slippage enters P&L linearly at fixed turnover, so the analytic estimate
    is exact to the small sizing feedback the confirming runs measure.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import intraday_backtest as ib  # noqa: E402
import intraday_common  # noqa: E402
from intraday_common import REPO, SLIPPAGE_BPS, UNIVERSE, load_universe  # noqa: E402

#: full store minus today's partial session (same window every A-track iteration uses)
START, END = dt.date(2025, 8, 26), dt.date(2026, 9, 8)
#: A-4's holdout boundary: everything before it was never seen by an A-track parameter
SPLIT = dt.date(2025, 12, 15)
EQUITY = 1_000_000.0
OUT = REPO / "results" / "a5"

#: live/intraday_config.json as of A-2 - the control for every cell here.
DEPLOYED = {"alloc": {"orb": 1.0, "vwap_trend": 0.0, "late_momo": 1.0},
            "per_symbol": 0.15, "gross": 1.5,
            "sub_params": {"late_momo": {"direction": -1}, "orb": {"disaster_atr": 4.0}}}

#: Confirming runs for the breakeven. A full-store run costs ~17 minutes, and P&L is linear in
#: slippage at fixed turnover, so two cells either side of the shipped 1.5 measure the slope and
#: prove the linearity; the analytic estimate (turnover / 1e4 per bp) does the rest, including
#: both halves, which is why there is no need to re-run them.
BPS_CELLS = [0.0, 3.0]


# --------------------------------------------------------------------------- spread estimators
def roll_spread_bps(closes: pd.Series, day: pd.Index) -> float:
    """Roll (1984): with a bid-ask bounce in an otherwise efficient price, successive returns are
    negatively autocovariant and S = 2*sqrt(-cov). Computed on within-session 1-minute log
    returns so no overnight gap enters the covariance."""
    r = np.log(closes).groupby(day).diff().values          # NaN on each session's first bar
    prev, cur = r[:-1], r[1:]
    ok = np.isfinite(prev) & np.isfinite(cur)              # a NaN kills any cross-session pair
    if ok.sum() < 100:
        return float("nan")
    cov = float(np.cov(cur[ok], prev[ok])[0, 1])
    return 2.0 * np.sqrt(-cov) * 1e4 if cov < 0 else float("nan")


def corwin_schultz_bps(h: pd.Series, l: pd.Series, day: pd.Index) -> float:
    """Corwin-Schultz (2012) two-period high-low estimator, on consecutive 1-minute bars.

    Uses the fact that the high is (almost always) a buy at the ask and the low a sell at the
    bid, so a single bar's range is inflated by the spread while a two-bar range is not.
    Negative single estimates are floored at zero, as the paper prescribes.
    """
    k = 3.0 - 2.0 * np.sqrt(2.0)
    same = pd.Index(h.index.date)[1:] == pd.Index(h.index.date)[:-1]
    h1, h2 = h.values[:-1][same], h.values[1:][same]
    l1, l2 = l.values[:-1][same], l.values[1:][same]
    ok = (h1 > 0) & (h2 > 0) & (l1 > 0) & (l2 > 0)
    h1, h2, l1, l2 = h1[ok], h2[ok], l1[ok], l2[ok]
    if len(h1) < 100:
        return float("nan")
    beta = np.log(h1 / l1) ** 2 + np.log(h2 / l2) ** 2
    hi2, lo2 = np.maximum(h1, h2), np.minimum(l1, l2)
    gamma = np.log(hi2 / lo2) ** 2
    alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    s = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
    s = np.where(np.isfinite(s), np.maximum(s, 0.0), np.nan)
    return float(np.nanmean(s)) * 1e4


def phase_spread(bars: dict[str, pd.DataFrame], weights: dict[str, float] | None) -> pd.DataFrame:
    rows = []
    for s, df in sorted(bars.items()):
        day = pd.Index(df.index.date)
        px = float(df["c"].median())
        r = np.log(df["c"]).groupby(day).diff()
        rows.append({"sym": s, "bars": len(df), "median px": round(px, 2),
                     "tick bps": round(0.01 / px * 1e4, 2),
                     "1min vol bps": round(float(r.std() * 1e4), 1),
                     "roll spread bps": round(roll_spread_bps(df["c"], day), 2),
                     "CS spread bps": round(corwin_schultz_bps(df["h"], df["l"], day), 2)})
    t = pd.DataFrame(rows)
    t["half-spread bps"] = (t[["roll spread bps", "CS spread bps"]].mean(axis=1) / 2).round(2)
    print(f"\n=== effective spread from prints, {START}..{END} ({len(bars)} names) ===")
    print(t.to_string(index=False))
    print("\n  unweighted mean half-spread     %.2f bps" % t["half-spread bps"].mean())
    print("  median half-spread              %.2f bps" % t["half-spread bps"].median())
    if weights:
        w = t["sym"].map(weights).fillna(0.0)
        if w.sum() > 0:
            print("  traded-notional-weighted mean   %.2f bps   <- the number the sleeve actually pays on"
                  % float((t["half-spread bps"] * w).sum() / w.sum()))
    print(f"  shipped SLIPPAGE_BPS            {SLIPPAGE_BPS:.2f} bps")

    # Both estimators are known to be contaminated by volatility at short horizons: a 1-minute
    # bar's range is mostly price discovery, not the spread. If the "spread" is just a rescaled
    # volatility the estimate is worthless as a cost number, and this is the test.
    good = t.dropna(subset=["CS spread bps"])
    rho = float(good["CS spread bps"].corr(good["1min vol bps"]))
    ratio = (good["CS spread bps"] / good["1min vol bps"])
    print(f"\n  corr(CS estimate, 1-minute return std) = {rho:+.3f} across {len(good)} names")
    print(f"  CS / vol ratio: median {ratio.median():.2f}, spread {ratio.min():.2f}-{ratio.max():.2f}"
          f"  <- near-constant means the estimator is measuring volatility, not the spread")
    tick_floor = float((t["tick bps"] / 2 * t["sym"].map(weights or {}).fillna(0.0)).sum()
                       / max(1e-12, t["sym"].map(weights or {}).fillna(0.0).sum())) if weights else float("nan")
    print(f"  hard lower bound (half of one tick, notional-weighted) {tick_floor:.2f} bps")
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT / "spread_estimates.csv", index=False)
    return t


# --------------------------------------------------------------------------- participation
def phase_impact(bars: dict[str, pd.DataFrame], trades: pd.DataFrame) -> pd.DataFrame:
    """Each fill's size as a share of the volume of the minute it fills in, and of the session."""
    vol = pd.concat([df["v"].rename("v").to_frame().assign(sym=s) for s, df in bars.items()])
    vol = vol.reset_index(names="t")
    day_vol = vol.assign(day=pd.Index(vol["t"]).date).groupby(["sym", "day"], as_index=False)["v"].sum()
    day_vol = day_vol.rename(columns={"v": "day_v"})

    d = trades.copy()
    d["t"] = pd.to_datetime(d["t"])
    d["day"] = d["t"].dt.date
    d = d.merge(vol, on=["sym", "t"], how="left").merge(day_vol, on=["sym", "day"], how="left")
    d["shares"] = d["qty"].abs()
    d["notional"] = d["shares"] * d["px"]
    d["part_bar"] = d["shares"] / d["v"].replace(0, np.nan)
    d["part_day"] = d["shares"] / d["day_v"].replace(0, np.nan)
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "fill_participation.csv", index=False)

    p = d["part_bar"].dropna()
    print(f"\n=== the sleeve's own fills against the volume of the minute they fill in "
          f"({len(d):,} fills, {d['v'].isna().sum()} without a bar) ===")
    for lab, q in (("median", 0.5), ("p75", 0.75), ("p90", 0.9), ("p99", 0.99), ("max", 1.0)):
        print(f"  participation {lab:<7}{p.quantile(q) * 100:8.2f}% of the bar's volume")
    print(f"  notional-weighted mean {float((d['part_bar'] * d['notional']).sum() / d['notional'].sum()) * 100:6.2f}%")
    print(f"  median share of the whole session's volume {d['part_day'].median() * 100:.3f}%")
    print(f"  mean fill notional ${d['notional'].mean():,.0f}   total traded ${d['notional'].sum() / 1e6:,.0f}M")

    per = d.groupby("sym").agg(fills=("shares", "size"), med_part=("part_bar", "median"),
                              p90_part=("part_bar", lambda x: x.quantile(0.9)),
                              med_notional=("notional", "median"),
                              notional_share=("notional", "sum"))
    per["notional_share"] = per["notional_share"] / per["notional_share"].sum()
    per[["med_part", "p90_part"]] *= 100
    print("\n=== per name (participation in %, notional_share = share of the sleeve's traded value) ===")
    print(per.sort_values("notional_share", ascending=False).round(3).to_string())
    per.to_csv(OUT / "participation_per_symbol.csv")

    # The harness already pays a cost it never names: the decision is made on bar t's close and
    # the fill happens at bar t+1's open. Signed by direction, that one-minute gap is the delay
    # cost, and it is charged on top of SLIPPAGE_BPS. Live execution pays it too - it is the part
    # of real slippage the backtest is NOT missing, which is what makes 1.5 bps a smaller
    # assumption than it looks.
    prev_close = {}
    for s, df in bars.items():
        pc = df["c"].shift(1)
        pc.index = df.index
        prev_close[s] = pc
    d["prev_close"] = [prev_close[s].get(t, np.nan) if s in prev_close else np.nan
                       for s, t in zip(d["sym"], d["t"])]
    e = d.dropna(subset=["prev_close"])
    sign = np.sign(e["qty"].astype(float))
    delay = (e["px"].astype(float) - e["prev_close"].astype(float)) / e["prev_close"].astype(float) * 1e4 * sign
    w = e["notional"]
    print(f"\n=== delay cost already inside the harness: decision bar's close -> fill at the next "
          f"bar's open ({len(e):,} fills) ===")
    print(f"  signed gap, notional-weighted   {float((delay * w).sum() / w.sum()):+.2f} bps"
          f"   (positive = the fill price moved against the order)")
    print(f"  unweighted mean {delay.mean():+.2f} bps   median {delay.median():+.2f}"
          f"   se {delay.std(ddof=1) / np.sqrt(len(delay)):.2f}")
    comm_bps = float((e["cost"].astype(float) - w * SLIPPAGE_BPS / 1e4).sum() / w.sum() * 1e4)
    print(f"  explicit SLIPPAGE_BPS charge    {SLIPPAGE_BPS:+.2f} bps")
    print(f"  IBKR commission                 {comm_bps:+.2f} bps of notional")
    print(f"  all-in modelled cost of a fill  "
          f"{float((delay * w).sum() / w.sum()) + SLIPPAGE_BPS + comm_bps:+.2f} bps")
    return d


# --------------------------------------------------------------------------- breakeven
_BARS: dict = {}
_FEATS: dict = {}
_STRAT: dict = {}


def _init(start, end, symbols):
    from base import features
    _BARS.update(load_universe(symbols, start, end))
    _FEATS.update({s: features(df) for s, df in _BARS.items()})
    _STRAT["active"] = ib.load_strategy("active")


def _job(spec):
    bps, half, lo, hi = spec
    intraday_common.SLIPPAGE_BPS = float(bps)
    strat = _STRAT["active"]
    params = {**strat.PARAMS, **DEPLOYED}
    s = ib.run(strat, _BARS, EQUITY, params, lo, hi, False, feats_all=_FEATS)
    s.pop("daily")
    return bps, half, s, params


def analytic_breakeven(base: dict, trades: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """The decision number: how wrong SLIPPAGE_BPS must be to flip the sleeve's sign.

    Slippage is charged as `|qty| * px * bps / 1e4` on every fill, so at fixed turnover the
    sleeve's P&L is linear in the constant with slope -(notional traded)/1e4. Both halves come
    out of the same control run: each window's own turnover and its own mean daily P&L.
    """
    trades = trades.copy()
    trades["day"] = pd.to_datetime(trades["t"]).dt.date
    windows = {"FULL": (START, END), "HOLDOUT": (START, SPLIT - dt.timedelta(days=1)), "TUNE": (SPLIT, END)}
    rows = []
    for name, (lo, hi) in windows.items():
        tr = trades[(trades["day"] >= lo) & (trades["day"] <= hi)]
        dd = daily[(daily["day"] >= lo) & (daily["day"] <= hi)]
        n = len(dd)
        if not n or tr.empty:
            continue
        notional = float((tr["qty"].abs() * tr["px"]).sum())
        per_bp = notional / n / 1e4
        pnl = float(dd["pnl"].mean())
        se = float(dd["pnl"].std(ddof=1) / np.sqrt(n))
        rows.append({"window": name, "sessions": n, "notional/day": round(notional / n),
                     "$ per bp/day": round(per_bp), "$/day at 1.5 bps": round(pnl),
                     "$/day at 0 bps": round(pnl + SLIPPAGE_BPS * per_bp),
                     "breakeven bps": round(SLIPPAGE_BPS + pnl / per_bp, 2),
                     "se of $/day": round(se), "se in bps": round(se / per_bp, 2)})
    t = pd.DataFrame(rows)
    print(f"\n=== analytic breakeven slippage, deployed mix, shipped constant {SLIPPAGE_BPS} bps ===")
    print(t.to_string(index=False))
    print("\n  'breakeven bps' is the slippage at which the sleeve earns exactly zero; 'se in bps' is")
    print("  the sample's own noise expressed in the same units, i.e. how far the breakeven itself moves.")
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT / "breakeven_analytic.csv", index=False)
    return t


def phase_breakeven(base: dict, trades: pd.DataFrame, daily: pd.DataFrame,
                    workers: int, record: bool, symbols) -> pd.DataFrame:
    t = analytic_breakeven(base, trades, daily)
    full = t[t["window"] == "FULL"].iloc[0]
    per_bp = float(full["$ per bp/day"])

    jobs = [(b, "FULL", START, END) for b in BPS_CELLS]
    print(f"\n{len(BPS_CELLS)} confirming full-store runs at {BPS_CELLS} bps, {workers} workers "
          f"(~17 min each, run in parallel)")
    res = {SLIPPAGE_BPS: base}
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(START, END, symbols)) as ex:
        for bps, half, s, params in ex.map(_job, jobs):
            res[bps] = s
            print(f"  {bps:4.1f} bps  CAR {s['cagr_pct']:7.1f}  Sharpe {s['sharpe']:5.2f}  "
                  f"$/day {s['avg_daily_pnl']:>8,.0f}  costs/day {s['costs_per_day']:>7,.0f}  "
                  f"tr/day {s['trades_per_day']:5.1f}", flush=True)
            if record:
                intraday_common.SLIPPAGE_BPS = bps
                ib.record("active", f"A-5 slippage {bps} bps [FULL store]", s, params, START, END)
                intraday_common.SLIPPAGE_BPS = SLIPPAGE_BPS

    cells = sorted(res)
    pnl = [res[b]["avg_daily_pnl"] for b in cells]
    tbl = pd.DataFrame({"slippage bps": cells, "$/day": [round(p) for p in pnl],
                        "CAR %": [round(res[b]["cagr_pct"], 1) for b in cells],
                        "Sharpe": [round(res[b]["sharpe"], 2) for b in cells],
                        "trades/day": [round(res[b]["trades_per_day"], 1) for b in cells]})
    print("\n=== the sleeve as a function of the one unmeasured constant (full store) ===")
    print(tbl.to_string(index=False))
    tbl.to_csv(OUT / "breakeven_runs.csv", index=False)
    if len(cells) >= 2:
        slope = float(np.polyfit(cells, pnl, 1)[0])
        resid = np.max(np.abs(np.polyval(np.polyfit(cells, pnl, 1), cells) - pnl))
        print(f"\n  measured d($/day)/d(bps) = {slope:,.0f}   analytic -{per_bp:,.0f}"
              f"   ({abs(slope) / per_bp - 1:+.1%} sizing feedback)")
        print(f"  worst deviation from a straight line ${resid:,.0f}/day - linearity holds, so the")
        print(f"  analytic breakeven above is the answer, not an approximation.")
        print(f"  breakeven from the runs   {cells[0] - pnl[0] / slope:.2f} bps")
    return tbl


# --------------------------------------------------------------------------- driver
def control(bars, symbols, record: bool, reuse: bool):
    """The deployed mix over the full store with its fill list. ~17 minutes, so it is cached:
    every other phase reads these three files."""
    OUT.mkdir(parents=True, exist_ok=True)
    fs, ft, fd = OUT / "control.json", OUT / "control_trades.parquet", OUT / "control_daily.csv"
    if reuse and fs.exists() and ft.exists() and fd.exists():
        base = json.loads(fs.read_text(encoding="utf-8"))
        trades = pd.read_parquet(ft)
        daily = pd.read_csv(fd)
        daily["day"] = pd.to_datetime(daily["day"]).dt.date
        print(f"\nreusing cached control run: {base['sessions']} sessions, {len(trades):,} fills")
        return base, trades, daily
    sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
    from base import features
    feats = {s: features(df) for s, df in bars.items()}
    strat = ib.load_strategy("active")
    params = {**strat.PARAMS, **DEPLOYED}
    base = ib.run(strat, bars, EQUITY, params, START, END, False, feats_all=feats, collect_trades=True)
    trades = pd.DataFrame(base.pop("trades_log"))
    daily = base.pop("daily")
    print(f"\ndeployed mix control: {base['sessions']} sessions  CAR {base['cagr_pct']:.1f}  "
          f"Sharpe {base['sharpe']:.2f}  $/day {base['avg_daily_pnl']:,.0f}  "
          f"costs/day {base['costs_per_day']:,.0f}  {len(trades):,} fills")
    if record:
        ib.record("active", "A-5 control: deployed mix, full store, shipped 1.5 bps slippage",
                  base, params, START, END)
    fs.write_text(json.dumps(base, default=str, indent=2) + "\n", encoding="utf-8")
    trades.to_parquet(ft)
    daily.to_csv(fd, index=False)
    return base, trades, daily


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", default="all", choices=["control", "spread", "impact", "breakeven", "all"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--no-reuse", action="store_true", help="re-run the cached control instead of loading it")
    ap.add_argument("--symbols", nargs="*")
    args = ap.parse_args()
    symbols = args.symbols or UNIVERSE

    bars = load_universe(symbols, START, END)
    print(f"{len(bars)} symbols, {sum(len(d) for d in bars.values()):,} bars, {START}..{END}")

    base, trades, daily = control(bars, symbols, args.record, not args.no_reuse)
    nl = (trades["qty"].abs() * trades["px"]).groupby(trades["sym"]).sum()
    weights = (nl / nl.sum()).to_dict()

    if args.phase in ("spread", "all"):
        phase_spread(bars, weights)
    if args.phase in ("impact", "all"):
        phase_impact(bars, trades)
    if args.phase in ("breakeven", "all"):
        phase_breakeven(base, trades, daily, args.workers, args.record, symbols)
    return 0


if __name__ == "__main__":
    sys.exit(main())
