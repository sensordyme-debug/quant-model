#!/usr/bin/env python
"""A-9: does the width of the opening range predict the breakout?

A-4 measured the sleeve's daily P&L correlating +0.538 (t = +10.25, n = 260) with the
universe's same-day range: ORB's payoff scales with the day's range while its cost floor does
not. Prior-day range does not predict it (t = +0.47), but the opening range is *closed* before
the first entry, so its width relative to ATR14 at that moment is known at entry and causal.
`algorithms/intraday/orb/signal.py` gates only on volume and never on width.

    python scripts/sweep_a9.py --phase attrib     # per-(symbol, session) P&L by width decile
    python scripts/sweep_a9.py --phase grid       # sweep range_atr_min / range_atr_max
    python scripts/sweep_a9.py --phase mix        # carry the survivors into the deployed mix
    python scripts/sweep_a9.py --phase all --record

Phase `attrib` is the powerful test: ORB is flat in every name at the close, so the realized
P&L of one (symbol, session) is exact, and one run yields ~7,000 of them instead of the 260
daily numbers a grid cell is judged on. A gate is only shippable if the decile response is
large, monotone and present in BOTH halves - A-4's power result says a cell whose edge is a
fraction of the sleeve's own Sharpe cannot be resolved on this sample.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import intraday_backtest as ib  # noqa: E402
from intraday_common import REPO, UNIVERSE, load_universe  # noqa: E402

#: full store minus today's partial session
START, END = dt.date(2025, 8, 26), dt.date(2026, 9, 8)
#: A-4's holdout boundary: everything before this was never seen by an A-track parameter
SPLIT = dt.date(2025, 12, 15)
EQUITY = 1_000_000.0
OUT = REPO / "results" / "a9"

#: live/intraday_config.json as of A-2 - the control.
DEPLOYED = {"alloc": {"orb": 1.0, "vwap_trend": 0.0, "late_momo": 1.0},
            "per_symbol": 0.15, "gross": 1.5,
            "sub_params": {"late_momo": {"direction": -1}, "orb": {"disaster_atr": 4.0}}}
#: the ORB module exactly as deployed inside that mix
ORB_DEPLOYED = {"disaster_atr": 4.0}

#: names whose opening range is widest in percentage terms, where the cost floor is
#: proportionally smallest (the backlog asks for these separately)
WIDE_NAMES = ["SOXL", "SOXS", "SMCI", "MSTR"]

GRID = [
    {"name": "control (no width gate)", "orb": {}},
    {"name": "min 3.2", "orb": {"range_atr_min": 3.2}},
    {"name": "min 3.6", "orb": {"range_atr_min": 3.6}},
    {"name": "min 4.0", "orb": {"range_atr_min": 4.0}},
    {"name": "min 4.4", "orb": {"range_atr_min": 4.4}},
    {"name": "min 5.0", "orb": {"range_atr_min": 5.0}},
    {"name": "max 5.4", "orb": {"range_atr_max": 5.4}},
    {"name": "max 4.8", "orb": {"range_atr_max": 4.8}},
    {"name": "max 4.4", "orb": {"range_atr_max": 4.4}},
    {"name": "max 3.6", "orb": {"range_atr_max": 3.6}},
    {"name": "band 3.6-5.4", "orb": {"range_atr_min": 3.6, "range_atr_max": 5.4}},
]

_BARS: dict = {}
_FEATS: dict = {}
_STRATS: dict = {}


def _init(start, end, symbols):
    from base import features
    _BARS.update(load_universe(symbols, start, end))
    _FEATS.update({s: features(df) for s, df in _BARS.items()})
    _STRATS["orb"] = ib.load_strategy("orb")
    _STRATS["active"] = ib.load_strategy("active")


def _job(spec):
    """(cell, module, half, lo, hi) -> summary. `module` is 'orb' (standalone) or 'active' (mix)."""
    cell, module, half, lo, hi = spec
    strat = _STRATS[module]
    if module == "orb":
        params = {**strat.PARAMS, **ORB_DEPLOYED, **cell["orb"]}
    else:
        sub = {**DEPLOYED["sub_params"], "orb": {**ORB_DEPLOYED, **cell["orb"]}}
        params = {**strat.PARAMS, **DEPLOYED, "sub_params": sub}
    s = ib.run(strat, _BARS, EQUITY, params, lo, hi, False, feats_all=_FEATS)
    daily = s.pop("daily")
    return cell["name"], module, half, s, daily.to_dict("records"), params


# --------------------------------------------------------------------------- width table
def width_table(feats: dict, rng_minutes: int = 15) -> pd.DataFrame:
    """Per (symbol, session): opening-range width, ATR14 at the range close, and their ratio.

    Exactly the numbers `orb.signal._range` snapshots, so the table and the gate agree.
    """
    rows = []
    for s, f in feats.items():
        g = f[f["minute"] == rng_minutes]
        if g.empty:
            continue
        w = (g["or_high"] - g["or_low"]).values
        atr = g["atr14"].values
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = np.where(atr > 0, w / atr, np.nan)
        rows.append(pd.DataFrame({"sym": s, "day": g["day"].values, "width": w, "atr": atr,
                                  "px": g["c"].values, "r_atr": ratio,
                                  "r_pct": w / g["c"].values * 100.0}))
    return pd.concat(rows, ignore_index=True)


def _t(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    if len(x) < 2 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def attribution(start, end, split, symbols, record: bool) -> pd.DataFrame:
    from base import features
    bars = load_universe(symbols, start, end)
    feats = {s: features(df) for s, df in bars.items()}
    strat = ib.load_strategy("orb")
    params = {**strat.PARAMS, **ORB_DEPLOYED}
    s = ib.run(strat, bars, EQUITY, params, start, end, False, feats_all=feats, collect_trades=True)
    trades = pd.DataFrame(s.pop("trades_log"))
    daily = s.pop("daily")
    print(f"ORB standalone, {s['sessions']} sessions: CAR {s['cagr_pct']:.1f}  Sharpe {s['sharpe']:.2f}  "
          f"$/day {s['avg_daily_pnl']:,.0f}  {len(trades):,} fills")
    if record:
        ib.record("orb", "A-9 attribution base run: ORB standalone, deployed sub-params, full store",
                  s, params, start, end)

    # ORB is flat in every name at the close, so realized P&L per (symbol, session) is exact.
    trades["day"] = pd.to_datetime(trades["t"]).dt.date
    trades["cash"] = -(trades["qty"] * trades["px"]) - trades["cost"]
    trades["gross_cash"] = -(trades["qty"] * trades["px"])
    pnl = trades.groupby(["sym", "day"], as_index=False).agg(
        pnl=("cash", "sum"), gross=("gross_cash", "sum"), cost=("cost", "sum"), fills=("qty", "size"))

    w = width_table(feats)
    d = pnl.merge(w, on=["sym", "day"], how="left").dropna(subset=["r_atr"])
    d["half"] = np.where(pd.to_datetime(d["day"]).dt.date < split, "HOLD", "TUNE")
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "attrib_symbol_sessions.csv", index=False)

    def corr_t(a, b):
        r = float(pd.Series(a).corr(pd.Series(b)))
        n = len(a)
        t = r * np.sqrt(max(n - 2, 1)) / np.sqrt(max(1e-12, 1 - r * r))
        return r, t

    print(f"\n=== A-9 attribution: {len(d):,} traded (symbol, session) pairs, {start}..{end} ===")
    for lab, col in (("width/ATR14", "r_atr"), ("width/price %", "r_pct")):
        r, t = corr_t(d["pnl"].values, d[col].values)
        print(f"  corr(P&L, {lab:<14}) = {r:+.4f}  t = {t:+.2f}")
        rg, tg = corr_t(d["gross"].values, d[col].values)
        print(f"  corr(gross, {lab:<13}) = {rg:+.4f}  t = {tg:+.2f}")

    d["decile"] = pd.qcut(d["r_atr"], 10, labels=False, duplicates="drop") + 1
    rows = []
    for dec, g in d.groupby("decile"):
        r = {"decile": int(dec), "r_atr lo": round(g["r_atr"].min(), 2), "r_atr hi": round(g["r_atr"].max(), 2),
             "n": len(g), "mean $": round(g["pnl"].mean()), "t": round(_t(g["pnl"].values), 2),
             "gross $": round(g["gross"].mean()), "cost $": round(g["cost"].mean()),
             "win %": round((g["pnl"] > 0).mean() * 100), "fills": round(g["fills"].mean(), 1),
             "total $": round(g["pnl"].sum())}
        for half in ("HOLD", "TUNE"):
            h = g[g["half"] == half]
            r[f"{half} $"] = round(h["pnl"].mean()) if len(h) else float("nan")
        rows.append(r)
    table = pd.DataFrame(rows)
    print("\n=== mean P&L per traded (symbol, session) by width/ATR14 decile ===")
    print(table.to_string(index=False))
    table.to_csv(OUT / "attrib_deciles.csv", index=False)

    print("\n=== the same split above/below the median width, per symbol ===")
    med = d["r_atr"].median()
    per = d.assign(wide=d["r_atr"] >= med).groupby(["sym", "wide"])["pnl"].agg(["mean", "sum", "size"]).round(0)
    print(per.unstack().to_string())
    per.to_csv(OUT / "attrib_per_symbol.csv")

    print("\n=== wide-range names only ===")
    sub = d[d["sym"].isin(WIDE_NAMES)]
    if len(sub):
        sub_dec = sub.assign(q=pd.qcut(sub["r_atr"], 5, labels=False, duplicates="drop") + 1)
        print(sub_dec.groupby("q").agg(n=("pnl", "size"), mean=("pnl", "mean"), t=("pnl", lambda x: _t(x.values)),
                                       lo=("r_atr", "min"), hi=("r_atr", "max")).round(2).to_string())
    return d


# --------------------------------------------------------------------------- grids
def run_cells(cells, module, start, end, split, symbols, workers, record, tag_prefix):
    halves = {"HOLD": (start, split - dt.timedelta(days=1)), "TUNE": (split, end)}
    jobs = [(c, module, h, *halves[h]) for c in cells for h in ("HOLD", "TUNE")]
    print(f"\n{len(cells)} cells x 2 halves on '{module}', {workers} workers, {start}..{end} split {split}")
    res, dailies = {}, {}
    with ProcessPoolExecutor(max_workers=workers, initializer=_init,
                             initargs=(start, end, symbols)) as ex:
        for name, mod, half, s, daily, params in ex.map(_job, jobs):
            res[(name, half)] = s
            dailies[(name, half)] = pd.DataFrame(daily)
            print(f"  {mod:<7} {name:<24} {half:<5} CAR {s['cagr_pct']:7.1f}  Sharpe {s['sharpe']:5.2f}  "
                  f"$/day {s['avg_daily_pnl']:>8,.0f}  tr/day {s['trades_per_day']:5.1f}  "
                  f"worst {s['worst_day']:>9,.0f}", flush=True)
            if record:
                lo, hi = halves[half]
                label = "HOLDOUT<" if half == "HOLD" else "TUNED>="
                ib.record(mod, f"{tag_prefix} {name} [{label}{split}]", s, params, lo, hi)
    rows = []
    for c in cells:
        n = c["name"]
        r = {"cell": n}
        for half in ("HOLD", "TUNE"):
            s = res[(n, half)]
            r[f"{half} CAR"] = round(s["cagr_pct"], 1)
            r[f"{half} Sh"] = round(s["sharpe"], 2)
            r[f"{half} $/day"] = round(s["avg_daily_pnl"])
            r[f"{half} tr/day"] = round(s["trades_per_day"], 1)
            r[f"{half} worst"] = round(s["worst_day"])
        r["total P&L"] = round(sum(res[(n, h)]["avg_daily_pnl"] * res[(n, h)]["sessions"] for h in ("HOLD", "TUNE")))
        rows.append(r)
    table = pd.DataFrame(rows)
    print(f"\n=== {tag_prefix} on '{module}' ===")
    print(table.to_string(index=False))
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / f"grid_{module}.csv", index=False)

    # paired t of each cell's daily P&L against the control, on the sessions both traded
    base = pd.concat([dailies[(cells[0]["name"], h)] for h in ("HOLD", "TUNE")], ignore_index=True)
    print(f"\n=== paired daily P&L vs {cells[0]['name']} (n = {len(base)}) ===")
    for c in cells[1:]:
        d = pd.concat([dailies[(c["name"], h)] for h in ("HOLD", "TUNE")], ignore_index=True)
        m = base.merge(d, on="day", suffixes=("_b", "_c"))
        diff = (m["pnl_c"] - m["pnl_b"]).values
        print(f"  {c['name']:<24} delta {diff.mean():>+8,.0f}/day   t = {_t(diff):+.2f}")
    for k, v in dailies.items():
        v.to_csv(OUT / f"daily_{module}_{k[1]}_{k[0].replace(' ', '_').replace('(', '').replace(')', '')}.csv",
                 index=False)
    return res, dailies


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", default="all", choices=["attrib", "grid", "mix", "all"])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--symbols", nargs="*")
    ap.add_argument("--start"); ap.add_argument("--end"); ap.add_argument("--split")
    ap.add_argument("--mix-cells", nargs="*", help="cell names to carry into the deployed mix")
    args = ap.parse_args()
    start = dt.date.fromisoformat(args.start) if args.start else START
    end = dt.date.fromisoformat(args.end) if args.end else END
    split = dt.date.fromisoformat(args.split) if args.split else SPLIT
    symbols = args.symbols or UNIVERSE
    OUT.mkdir(parents=True, exist_ok=True)

    if args.phase in ("attrib", "all"):
        attribution(start, end, split, symbols, args.record)
    if args.phase in ("grid", "all"):
        run_cells(GRID, "orb", start, end, split, symbols, args.workers, args.record, "A-9 grid")
    if args.phase in ("mix", "all"):
        names = set(args.mix_cells or ["min 3.6", "max 5.4", "band 3.6-5.4"])
        cells = [GRID[0]] + [c for c in GRID[1:] if c["name"] in names]
        run_cells(cells, "active", start, end, split, symbols, args.workers, args.record, "A-9 mix")
    return 0


if __name__ == "__main__":
    sys.exit(main())
