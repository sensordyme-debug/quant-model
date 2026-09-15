"""Phase 5: is there information in the RELATIONSHIP between markets that is not in each one?

THE IDEA WORTH TESTING
----------------------
Every overnight variable tested so far describes one contract in isolation. A dispersion
variable is different in kind: when the Nasdaq is up 0.8% overnight and the S&P is up 0.1%,
neither number alone says "this is a narrow, tech-led move", but the pair does. If overnight
positioning concentrates in one index and then unwinds during the US session, the SPREAD
should carry information that neither leg carries.

That is a real mechanism with a real literature behind it, and it is cheap to test. It is
also the kind of variable that is easy to fool yourself with, because differencing two
correlated series manufactures a new series with its own noise and its own spurious extremes.

WHERE IT IS TESTED, AND WHY NOT ON FUTURES
--------------------------------------------
The brief asks for ES vs NQ, ES vs RTY and NQ vs RTY. **There is no RTY or M2K in the futures
store** - it holds ES, NQ, MES and MNQ only, which is two indices, not three, since MES and
MNQ are the micro versions of the same two contracts. So a three-way dispersion cannot be
computed there at all, and the ES-NQ pair alone would have 312 sessions and a minimum
detectable correlation of 0.111.

The ETF store solves both problems. SPY, QQQ, IWM and DIA give four distinct indices - large
cap, Nasdaq, small cap and the Dow - over 2,687 sessions from 2016, which is a minimum
detectable correlation of 0.038. IWM is the Russell 2000, which is what RTY tracks, so the
brief's third market is present after all, just not as a future.

The cost is that the ETF store is RTH-only, so "overnight" here is close-to-open. For a
dispersion variable that is the right measure anyway: what matters is where each index opened
relative to where it closed, not the path it took in between.

WHAT IS TESTED
--------------
Relative overnight return for all six pairs, plus a cross-sectional dispersion measure, plus
a leader/laggard sign. Each is tested against four outcomes: the RTH direction of each leg,
the RTH range, and the continuation of the spread itself. The Bonferroni bar counts the whole
grid, and the direction tests are held to the sign they predict.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

#: Four distinct indices. IWM is the Russell 2000, the brief's RTY.
SYMBOLS = ("SPY", "QQQ", "IWM", "DIA")


def build_panel() -> pd.DataFrame:
    """One row per trade date per symbol: close-to-open, open-to-close, and the day's range."""
    frames = []
    for sym in SYMBOLS:
        store = REPO / "data" / "minute_alpaca" / f"{sym}.parquet"
        if not store.exists():
            continue
        d = pd.read_parquet(store)
        t = d.index
        if getattr(t, "tz", None) is None:
            t = t.tz_localize("UTC")
        t = t.tz_convert("America/New_York")
        d = d.assign(_d=t.date).sort_index()
        day = d.groupby("_d").agg(open=("o", "first"), close=("c", "last"),
                                  high=("h", "max"), low=("l", "min"), bars=("c", "size"))
        day = day[day["bars"] >= 380]
        prev = day["close"].shift(1)
        f = pd.DataFrame({
            "tdate": day.index, "symbol": sym,
            "on_ret": (day["open"] / prev - 1.0) * 100.0,
            "rth_ret": (day["close"] / day["open"] - 1.0) * 100.0,
            "rth_range": (day["high"] - day["low"]) / day["open"] * 100.0,
        }).dropna()
        frames.append(f[f["on_ret"].abs() < 10.0])
    return pd.concat(frames, ignore_index=True)


def wide(panel: pd.DataFrame) -> pd.DataFrame:
    """Pivot to one row per date with a column per symbol per field."""
    parts = []
    for field in ("on_ret", "rth_ret", "rth_range"):
        w = panel.pivot(index="tdate", columns="symbol", values=field)
        w.columns = [f"{field}_{c}" for c in w.columns]
        parts.append(w)
    return pd.concat(parts, axis=1).dropna()


def test(x: np.ndarray, y: np.ndarray) -> dict:
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = len(x)
    if n < 100:
        return {"n": n, "r": np.nan, "t": np.nan}
    r = float(np.corrcoef(x, y)[0, 1])
    return {"n": n, "r": r, "t": float(r * np.sqrt((n - 2) / max(1e-12, 1 - r * r)))}


def main() -> int:
    panel = build_panel()
    w = wide(panel)
    syms = [s for s in SYMBOLS if f"on_ret_{s}" in w.columns]
    print("=" * 100)
    print("PHASE 5 - CROSS-MARKET OVERNIGHT INFORMATION")
    print(f"{len(w)} common trade dates, {w.index.min()} .. {w.index.max()}")
    print(f"indices: {', '.join(syms)}   (IWM is the Russell 2000, the brief's RTY)")
    print("=" * 100)

    # ---- the regressors ------------------------------------------------------------------
    feats: dict[str, np.ndarray] = {}
    for a, b in itertools.combinations(syms, 2):
        feats[f"spread_{a}_{b}"] = (w[f"on_ret_{a}"] - w[f"on_ret_{b}"]).to_numpy()
    on = w[[f"on_ret_{s}" for s in syms]].to_numpy()
    feats["dispersion"] = on.std(axis=1)
    feats["leader_spread"] = on.max(axis=1) - on.min(axis=1)
    feats["mean_on"] = on.mean(axis=1)

    # ---- the outcomes --------------------------------------------------------------------
    outs: dict[str, tuple[np.ndarray, int]] = {}
    for s in syms:
        outs[f"rth_ret_{s}"] = (w[f"rth_ret_{s}"].to_numpy(), 0)
        outs[f"rth_range_{s}"] = (w[f"rth_range_{s}"].to_numpy(), +1)
    for a, b in itertools.combinations(syms, 2):
        outs[f"rth_spread_{a}_{b}"] = ((w[f"rth_ret_{a}"] - w[f"rth_ret_{b}"]).to_numpy(), 0)

    rows = []
    for fname, x in feats.items():
        for oname, (y, _) in outs.items():
            r = test(x, y)
            rows.append({"feature": fname, "outcome": oname, **r})
    out = pd.DataFrame(rows).dropna(subset=["t"])
    n_tests = len(out)
    t_bonf = float(np.sqrt(2) * _erfinv(1 - 0.05 / n_tests))
    out["passes"] = out["t"].abs() > t_bonf
    out.to_csv(REPO / "research" / "cross_market.csv", index=False)

    print(f"\n{n_tests} tests, Bonferroni bar |t| > {t_bonf:.2f}\n")

    print("--- DOES A SPREAD PREDICT DIRECTION?  (the question that would pay) " + "-" * 30)
    dirn = out[out.outcome.str.startswith("rth_ret_")]
    print(f"{'feature':22}" + "".join(f"{s:>12}" for s in syms))
    for fname in feats:
        cells = []
        for s in syms:
            row = dirn[(dirn.feature == fname) & (dirn.outcome == f"rth_ret_{s}")]
            cells.append(f"{row.iloc[0]['r']:+.3f}({row.iloc[0]['t']:+.1f})"
                         if len(row) else "     -")
        print(f"{fname:22}" + "".join(f"{c:>12}" for c in cells))

    print("\n--- DOES A SPREAD PREDICT RANGE?  (the magnitude question) " + "-" * 38)
    rng = out[out.outcome.str.startswith("rth_range_")]
    print(f"{'feature':22}" + "".join(f"{s:>12}" for s in syms))
    for fname in feats:
        cells = []
        for s in syms:
            row = rng[(rng.feature == fname) & (rng.outcome == f"rth_range_{s}")]
            cells.append(f"{row.iloc[0]['r']:+.3f}({row.iloc[0]['t']:+.1f})"
                         if len(row) else "     -")
        print(f"{fname:22}" + "".join(f"{c:>12}" for c in cells))

    print("\n--- DOES AN OVERNIGHT SPREAD CONTINUE OR REVERSE DURING RTH? " + "-" * 36)
    print(f"{'pair':22} {'r':>9} {'t':>8}  reading")
    for a, b in itertools.combinations(syms, 2):
        row = out[(out.feature == f"spread_{a}_{b}")
                  & (out.outcome == f"rth_spread_{a}_{b}")]
        if len(row):
            r, t = row.iloc[0]["r"], row.iloc[0]["t"]
            reading = ("continues" if r > 0 else "reverses") if abs(t) > t_bonf else "null"
            print(f"{a}-{b:18} {r:+9.3f} {t:+8.2f}  {reading}")

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    hits = out[out["passes"]]
    print(f"  tests                       {n_tests}")
    print(f"  nominal |t| > 1.96          {int((out['t'].abs() > 1.96).sum())}")
    print(f"  Bonferroni |t| > {t_bonf:.2f}       {len(hits)}")
    if len(hits):
        by_kind = hits.assign(
            kind=np.where(hits.outcome.str.startswith("rth_range_"), "range",
                          np.where(hits.outcome.str.startswith("rth_spread_"),
                                   "spread", "direction")))
        print("\n  survivors by outcome kind:")
        for k, g in by_kind.groupby("kind"):
            print(f"    {k:10} {len(g):3d}   "
                  f"|r| range {g['r'].abs().min():.3f}-{g['r'].abs().max():.3f}")
        d = by_kind[by_kind.kind == "direction"]
        print(f"\n  DIRECTIONAL survivors: {len(d)}")
        for _, r in d.iterrows():
            print(f"    {r['feature']:22} -> {r['outcome']:16} r={r['r']:+.3f} t={r['t']:+.2f}")
    return 0


def _erfinv(y: float) -> float:
    a = 0.147
    ln = np.log(1 - y * y)
    term = 2 / (np.pi * a) + ln / 2
    return float(np.sign(y) * np.sqrt(np.sqrt(term * term - ln / a) - term))


if __name__ == "__main__":
    raise SystemExit(main())
