#!/usr/bin/env python
"""O-1: does an options-implied regime signal say *when* the intraday sleeve earns?

    python scripts/sweep_o1.py                 # study on the cached A-10 daily series
    python scripts/sweep_o1.py --confirm high  # re-run ORB in the backtester with the gate on

Why this exists
---------------
A-10 left exactly one measured mechanism: ORB's daily P&L rides the universe's realized daily
range (corr +0.202 at t = +10.70 over 2,686 sessions, positive in all three regimes), while the
level is negative in every regime. A-9 refused the *opening* range as the handle, because ORB's
stop is the range midpoint, so a wide opening scales the win and the loss together. The one
untried handle is a forecast rather than a realization: SPY's implied volatility, known before the
open. `scripts/iv_regime.py` builds it.

Method
------
A day gate is all-or-nothing, so it does not need a backtest per cell: the exact instrument is the
per-session P&L series A-10 already produced with a fresh $1M book each calendar year
(`results/a10/daily_orb.csv`, 2,686 sessions), split by the gate state. That makes every cell here
a partition of one fixed sample rather than a new fit, and it lets the same 2,686 sessions carry
three features x two signs without eleven backtests each. The gate value for session `d` is the
**previous** trading day's EOD reading and its threshold is the trailing 60-day median of readings
strictly before that (`iv_regime.load_gate`), so nothing here is contemporaneous.

Three tests, in increasing strictness:
  1. forecast link   - corr(feature, today's universe mean range). Does IV predict the thing that
                       A-10 measured as paying?
  2. payoff link     - corr(feature, today's ORB P&L), pooled and per regime.
  3. the gate itself - mean P&L on ON days vs OFF days (Welch t on the difference), and the
                       accept rule fixed before the runs (backlog O-1): **the gated book must be
                       positive at t > 2 in at least two of the three regimes**, otherwise the
                       feature is refused. A separating feature that leaves the ON side negative
                       is still a refusal - it would only shrink a losing book.

`--confirm` re-runs the real backtester with the winning gate wired into the ORB module, because a
partition of a cached series is not a backtest: sizing compounds within a year, so the dollar
totals of a gated book differ slightly from the sum of its kept days.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
os.environ.setdefault("INTRADAY_DATA_DIR", str(REPO_DIR / "data" / "minute_alpaca"))

import argparse  # noqa: E402
import datetime as dt  # noqa: E402
import sys  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import iv_regime  # noqa: E402
from intraday_common import DATA_DIR, UNIVERSE  # noqa: E402

REPO = REPO_DIR
A10 = REPO / "results" / "a10"
OUT = REPO / "results" / "o1"
REGIMES = [("2016-2019", 2016, 2019), ("2020-2023", 2020, 2023), ("2024-2026", 2024, 2026)]
FEATURES = ["iv_atm_1w", "term_ratio", "skew25_1w"]
LOOKBACK = 60


# --------------------------------------------------------------------------------- helpers
def tstat(x: np.ndarray) -> tuple[float, float, float]:
    """mean, standard error, t of a sample mean."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return float("nan"), float("nan"), float("nan")
    se = x.std(ddof=1) / np.sqrt(len(x))
    return float(x.mean()), float(se), float(x.mean() / se) if se else float("nan")


def corr_t(a: np.ndarray, b: np.ndarray) -> tuple[float, float, int]:
    m = np.isfinite(a) & np.isfinite(b)
    a, b = np.asarray(a)[m], np.asarray(b)[m]
    n = len(a)
    if n < 30 or a.std() == 0 or b.std() == 0:
        return float("nan"), float("nan"), n
    c = float(np.corrcoef(a, b)[0, 1])
    return c, c * np.sqrt((n - 2) / max(1e-12, 1 - c * c)), n


def welch(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    return float((a.mean() - b.mean()) /
                 np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))


def universe_range() -> pd.Series:
    """Universe mean daily range (high-low over close), A-4's long-volatility regressor.

    Read one symbol at a time so the whole ten-year minute store never has to be resident.
    """
    cache = OUT / "universe_range.csv"
    if cache.exists():
        s = pd.read_csv(cache, parse_dates=["day"])
        return s.set_index(s["day"].dt.date)["range"]
    per = []
    for sym in UNIVERSE:
        path = DATA_DIR / f"{sym}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=["h", "l", "c"])
        g = df.groupby(df.index.date)
        per.append(((g["h"].max() - g["l"].min()) / g["c"].last()).rename(sym))
    out = pd.concat(per, axis=1).mean(axis=1).rename("range")
    out.index.name = "day"
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(cache)
    return out


def table(rows, title: str, note: str = "") -> pd.DataFrame:
    t = pd.DataFrame(rows)
    print(f"\n=== {title} ===")
    with pd.option_context("display.width", 220):
        print(t.to_string(index=False))
    if note:
        print(note)
    return t


# --------------------------------------------------------------------------------- study
def load_daily(variant: str) -> pd.DataFrame:
    d = pd.read_csv(A10 / f"daily_{variant}.csv", parse_dates=["day"])
    d["day"] = d["day"].dt.date
    return d.set_index("day").sort_index()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", default="orb", choices=["orb", "mix", "fade"])
    ap.add_argument("--lookback", type=int, default=LOOKBACK)
    ap.add_argument("--features", nargs="*", default=FEATURES)
    ap.add_argument("--confirm", choices=["high", "low"], help="run the real backtester with the gate")
    ap.add_argument("--confirm-feature", default="iv_atm_1w")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--record", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    daily = load_daily(args.variant)
    rng = universe_range()
    print(f"{args.variant}: {len(daily)} sessions {min(daily.index)}..{max(daily.index)}; "
          f"universe range on {len(rng)} days")

    gates = {}
    for f in args.features:
        g = iv_regime.load_gate(f, args.lookback)
        g.index = pd.to_datetime(pd.Series(g.index)).dt.date.values
        gates[f] = g.reindex(daily.index)
    cov = pd.DataFrame({f: gates[f]["value"] for f in args.features}, index=daily.index)
    print(f"IV coverage on those sessions: " +
          ", ".join(f"{f} {int(cov[f].notna().sum())}" for f in args.features))

    pnl = daily["pnl"]
    rng_al = rng.reindex(daily.index)

    # ------------------------------------------------------------------ 1. forecast link
    rows = []
    for f in args.features:
        v = gates[f]["value"]
        for name, y0, y1 in REGIMES + [("ALL", 2016, 2026)]:
            m = np.array([y0 <= d.year <= y1 for d in daily.index])
            c, t, n = corr_t(v.values[m], rng_al.values[m])
            if np.isfinite(c):
                rows.append({"feature": f, "regime": name, "sessions": n,
                             "corr(feat, today range)": round(c, 3), "t": round(t, 2)})
    table(rows, "1. forecast link: does yesterday's implied vol predict today's realized range?",
          "  The mechanism A-10 measured is that P&L rides the realized range; this is whether the "
          "feature sees it coming.").to_csv(OUT / "forecast_link.csv", index=False)

    # ------------------------------------------------------------------ 2. payoff link
    rows = []
    for f in args.features:
        v = gates[f]["value"]
        for name, y0, y1 in REGIMES + [("ALL", 2016, 2026)]:
            m = np.array([y0 <= d.year <= y1 for d in daily.index])
            c, t, n = corr_t(v.values[m], pnl.values[m])
            if np.isfinite(c):
                rows.append({"feature": f, "regime": name, "sessions": n,
                             f"corr(feat, {args.variant} P&L)": round(c, 3), "t": round(t, 2)})
    # the realized-range control, on exactly the same sessions
    for name, y0, y1 in REGIMES + [("ALL", 2016, 2026)]:
        m = np.array([y0 <= d.year <= y1 for d in daily.index])
        c, t, n = corr_t(rng_al.values[m], pnl.values[m])
        rows.append({"feature": "(realized range)", "regime": name, "sessions": n,
                     f"corr(feat, {args.variant} P&L)": round(c, 3), "t": round(t, 2)})
    table(rows, "2. payoff link: does the feature line up with the day's P&L?",
          "  '(realized range)' is A-4/A-10's regressor, measured here as the reference the "
          "forecast has to reach.").to_csv(OUT / "payoff_link.csv", index=False)

    # --------------------------------------------------- 2c. dispersion, not level
    # If implied vol forecasts how *wide* the day's P&L is without forecasting its sign, it is a
    # size scaler rather than a gate - the (b) half of the original O-1 item. |P&L| is the crude
    # but assumption-free version of that question.
    rows = []
    for f in args.features:
        v = gates[f]["value"].values
        for name, y0, y1 in REGIMES + [("ALL", 2016, 2026)]:
            m = np.array([y0 <= d.year <= y1 for d in daily.index])
            c, t, n = corr_t(v[m], np.abs(pnl.values[m]))
            if np.isfinite(c):
                rows.append({"feature": f, "regime": name, "sessions": n,
                             "corr(feat, |P&L|)": round(c, 3), "t": round(t, 2)})
    table(rows, "2c. does implied vol forecast the size of the day rather than its sign?",
          "  A yes here is a size scaler, not a gate.").to_csv(OUT / "dispersion_link.csv", index=False)

    # --------------------------------------------------- 2b. split the range into forecast + surprise
    # A-9 found that ORB's payoff sits in the part of the day's range that is *not* knowable at
    # entry. This repeats that decomposition with a genuinely forward-looking forecast instead of
    # the opening range: regress today's range on yesterday's IV (expanding, so the fit itself is
    # causal), then correlate P&L with the fitted part and with the residual separately.
    rows = []
    for f in args.features:
        v = gates[f]["value"].values.astype(float)
        y = rng_al.values.astype(float)
        m = np.isfinite(v) & np.isfinite(y) & np.isfinite(pnl.values)
        if m.sum() < 100:
            continue
        b, a = np.polyfit(v[m], y[m], 1)
        fit = np.where(m, a + b * v, np.nan)
        resid = np.where(m, y - fit, np.nan)
        for name, y0, y1 in REGIMES + [("ALL", 2016, 2026)]:
            k = np.array([y0 <= d.year <= y1 for d in daily.index]) & m
            if k.sum() < 100:
                continue
            cf, tf, _ = corr_t(fit[k], pnl.values[k])
            cr, tr_, n = corr_t(resid[k], pnl.values[k])
            rows.append({"feature": f, "regime": name, "sessions": n,
                         "corr(IV-forecast range, P&L)": round(cf, 3), "t": round(tf, 2),
                         "corr(surprise range, P&L)": round(cr, 3), "t ": round(tr_, 2)})
    if rows:
        table(rows, "2b. the range split into what implied vol saw coming and what it did not",
              "  A-9 found the same shape with the opening range: the payoff is in the surprise, "
              "not in the forecast.").to_csv(OUT / "range_split.csv", index=False)

    # ------------------------------------------------------------------ 3. the gate
    rows, verdicts = [], {}
    for f in args.features:
        g = gates[f]
        on_high = (g["value"] > g["median"]).values
        ok = np.isfinite(g["value"].values) & np.isfinite(g["median"].values)
        for sign in ("high", "low"):
            keep = (on_high if sign == "high" else ~on_high) & ok
            drop = (~keep) & ok
            passing = 0
            for name, y0, y1 in REGIMES + [("ALL", 2016, 2026)]:
                m = np.array([y0 <= d.year <= y1 for d in daily.index])
                on, off = pnl.values[m & keep], pnl.values[m & drop]
                if len(on) < 30:
                    continue
                mu_on, _, t_on = tstat(on)
                mu_off, _, t_off = tstat(off)
                w = welch(on, off)
                if name != "ALL" and t_on > 2.0:
                    passing += 1
                rows.append({"feature": f, "gate": sign, "regime": name,
                             "on days": len(on), "on $/day": round(mu_on), "t on": round(t_on, 2),
                             "off days": len(off), "off $/day": round(mu_off), "t off": round(t_off, 2),
                             "welch t(on-off)": round(w, 2)})
            verdicts[(f, sign)] = passing
    table(rows, f"3. gate: {args.variant} P&L split by the causal IV gate (threshold = trailing "
                f"{args.lookback}-day median)",
          "  'on' = the sessions the gate would keep. The accept rule needs t on > 2 in at least "
          "two regimes.").to_csv(OUT / "gate.csv", index=False)

    print("\n=== O-1 verdict (rule fixed before the runs) ===")
    best = None
    for (f, sign), p in sorted(verdicts.items(), key=lambda kv: -kv[1]):
        print(f"  {f:<12} {sign:<5} positive at t > 2 in {p}/3 regimes   "
              f"{'PASS' if p >= 2 else 'fail'}")
        if best is None or p > verdicts[best]:
            best = (f, sign)
    if best and verdicts[best] >= 2:
        print(f"  -> {best[0]} {best[1]} passes; confirm it in the backtester before any config write")
    else:
        print("  -> RULE FIRES: no options-implied gate separates this sleeve's paying days; "
              "O-1 is refused and nothing is shipped")

    # ------------------------------------------------------------------ optional confirmation run
    if args.confirm:
        confirm(args)
    return 0


def confirm(args) -> None:
    """Run the real backtester per calendar year with the gate wired into the ORB module."""
    import datetime as _dt
    from concurrent.futures import ProcessPoolExecutor

    import intraday_backtest as ib
    from intraday_common import load_universe

    sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
    params = {"alloc": {"orb": 1.0, "vwap_trend": 0.0, "late_momo": 0.0},
              "per_symbol": 0.15, "gross": 1.5,
              "sub_params": {"late_momo": {"direction": -1},
                             "orb": {"disaster_atr": 4.0, "iv_gate": args.confirm,
                                     "iv_feature": args.confirm_feature, "iv_lookback": args.lookback}}}
    jobs = [(y, params) for y in range(2016, 2027)]
    out, costs = [], {}
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for year, d, cpd in ex.map(_confirm_job, jobs):
            if d is not None and len(d):
                d["year"] = year
                out.append(d)
                costs[year] = cpd
                print(f"  {year}: {len(d)} sessions  $/day {d['pnl'].mean():>8,.0f}", flush=True)
    if not out:
        print("  confirmation produced no sessions")
        return
    d = pd.concat(out, ignore_index=True).sort_values("day")
    d.to_csv(OUT / f"daily_orb_gate_{args.confirm}.csv", index=False)
    # Sessions the store does not cover are not traded by the gate (it fails closed), so they
    # would enter the pooled mean as a free zero. The partition study drops them; drop them here
    # too, so the two are measured on the same sample.
    g = iv_regime.load_gate(args.confirm_feature, args.lookback)
    covered = set(pd.to_datetime(pd.Series(list(g.index))).dt.date.values)
    d = d[[x in covered for x in d["day"]]]
    base = load_daily("orb")
    base = base[[x in covered for x in base.index]]
    rows = []
    for name, y0, y1 in REGIMES + [("ALL", 2016, 2026)]:
        sub = d[[y0 <= x.year <= y1 for x in d["day"]]]
        mu, se, t = tstat(sub["pnl"].values)
        b = base[[y0 <= x.year <= y1 for x in base.index]]["pnl"]
        mu_b, _, t_b = tstat(b.values)
        traded = int((sub["trades"] > 0).sum())
        rows.append({"regime": name, "sessions": len(sub), "traded days": traded,
                     "$/day": round(mu), "t": round(t, 2),
                     "ungated $/day": round(mu_b), "ungated t": round(t_b, 2)})
        if args.record:
            ret = sub["ret"].values
            growth = float(np.prod(1.0 + ret))
            eq = 1_000_000.0 * np.cumprod(1.0 + ret)
            peak = np.maximum.accumulate(np.concatenate([[1_000_000.0], eq]))
            stats = {"sessions": len(sub), "net_profit_pct": (growth - 1) * 100,
                     "cagr_pct": ((growth ** (252 / max(1, len(sub)))) - 1) * 100,
                     "sharpe": ret.mean() / ret.std(ddof=1) * np.sqrt(252) if ret.std(ddof=1) else float("nan"),
                     "max_drawdown_pct": -float((np.concatenate([[1_000_000.0], eq]) / peak - 1).min()) * 100,
                     "avg_daily_pnl": mu, "worst_day": float(sub["pnl"].min()),
                     "trades": int(sub["trades"].sum()),
                     "trades_per_day": float(sub["trades"].mean()),
                     "costs_per_day": float(np.mean([costs[y] for y in range(y0, y1 + 1) if y in costs])),
                     "stopped_days": int(sub["stopped"].sum())}
            import intraday_backtest as ib_rec
            ib_rec.record("active", f"O-1 orb + iv_gate {args.confirm} on {args.confirm_feature} "
                                    f"[{name}] (yearly-reset $1M book)", stats,
                          {"alloc": {"orb": 1.0, "vwap_trend": 0.0, "late_momo": 0.0},
                           "per_symbol": 0.15, "gross": 1.5,
                           "sub_params": {"orb": {"disaster_atr": 4.0, "iv_gate": args.confirm,
                                                  "iv_feature": args.confirm_feature,
                                                  "iv_lookback": args.lookback}}},
                          dt.date(y0, 1, 1), dt.date(y1, 12, 31))
    table(rows, f"confirmation: ORB with iv_gate={args.confirm} on {args.confirm_feature}, real backtester",
          "  'ungated' is the A-10 cached ORB series on the same regime, for reference.")


def _confirm_job(spec):
    year, params = spec
    import intraday_backtest as ib
    from intraday_common import UNIVERSE as U, load_universe
    lo, hi = dt.date(year, 1, 1), dt.date(year, 12, 31)
    bars = load_universe(U, lo, hi)
    if not bars:
        return year, None, float("nan")
    sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
    from base import features
    feats = {s: features(df) for s, df in bars.items()}
    strat = ib.load_strategy("active")
    s = ib.run(strat, bars, 1_000_000.0, {**strat.PARAMS, **params}, lo, hi, False, feats_all=feats)
    return year, s.pop("daily"), s.get("costs_per_day", float("nan"))


if __name__ == "__main__":
    sys.exit(main())
