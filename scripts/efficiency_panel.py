"""The panel for the directional-efficiency question: how much of the day's motion goes somewhere.

WHY THIS PANEL EXISTS SEPARATELY
----------------------------------
The volatility forecast is settled: it predicts the regular session's PATH at an out-of-sample
R-squared near 0.5, robustly, on every instrument and in every regime. It also, just as
robustly, fails to predict DISPLACEMENT, at an R-squared near 0.05.

The question now is whether that failure is uniform or whether it hides a mixture. A day with
a large forecast path could resolve into a clean trend or into two-sided chop, and those are
opposite trading environments that the current forecast cannot tell apart. If some second
variable separates them BEFORE the open, the volatility model becomes useful. If nothing does,
the volatility model is a risk input and nothing more, and that is the answer.

So this panel is built around EFFICIENCY as the target rather than return or range, and around
path SHAPE as the descriptive layer, because a mixture has to be visible in the shape before it
is worth hunting a predictor for it.

FIVE TARGETS, ALL REPORTED, NONE CHOSEN FOR ITS BACKTEST
----------------------------------------------------------
The brief is explicit that the target must not be selected for producing the best result, so
all five are computed and all five are reported everywhere. They differ in what they forgive:

    eff_range     |close - open| / high-low range. The plain definition. Bounded [0, 1].
    eff_path      |close - open| / total absolute bar-to-bar motion. Harsher: a day that
                  travels the same distance in more wiggles scores lower even at the same range.
    eff_vol       |close - open| / (realised vol x sqrt(bars)). Scales displacement by the
                  random-walk expectation, so 1.0 means "moved as far as a random walk would".
    eff_mfe       maximum favourable excursion / range. What a perfect-exit trader could have
                  taken, as a share of the day. Always >= eff_range.
    cost_opp      the best realistic single directional move in dollars, minus one round turn.
                  The only target denominated in money rather than ratio.

`eff_vol` is the one with a natural null: a driftless random walk has expected |displacement|
of sigma*sqrt(n), so eff_vol near 1.0 is "no more directional than chance". Values well below
1 mean mean-reverting chop; well above 1 mean trend.

PATH SHAPE, WHICH IS THE DESCRIPTIVE HALF
-------------------------------------------
Counting how a session actually moved: how many times it changed direction, how far it ran
before it turned, whether the displacement happened early or late. These are not predictors
and they are not targets. They exist so that "high-volatility days are a mixture" can be
checked as a statement about shape rather than asserted from a scatter of R-squareds.

Direction changes are counted on a SMOOTHED series with a threshold, because on raw minute
bars every session has hundreds of sign flips and the count measures noise rather than
structure.

CAUSALITY
---------
Every column in this file is either a description of a completed period or a target. Nothing
here is a predictor of itself. The opening-window columns are the one place where a caller
could get it wrong: `open15_*` describes 09:30-09:45 and `rest15_*` describes 09:45 onward, so
those two must never appear on the same side of a regression. `test_efficiency.py` asserts the
boundary by perturbation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

#: Decision points after 09:30, in minutes.
OPEN_WINDOWS = (1, 5, 15, 30)

#: Round-turn cost in dollars and point value, for the money-denominated target.
ROUND_TURN = {"ES": 3.78, "NQ": 3.78, "MES": 1.22, "MNQ": 1.22,
              "SPY": 0.01, "QQQ": 0.01, "IWM": 0.01, "DIA": 0.01}
POINT_VALUE = {"ES": 50.0, "NQ": 20.0, "MES": 5.0, "MNQ": 2.0,
               "SPY": 100.0, "QQQ": 100.0, "IWM": 100.0, "DIA": 100.0}

#: A direction change is only counted when the retracement exceeds this share of the session
#: range. Without a threshold the count is a measure of tick noise, not of structure.
TURN_THRESHOLD = 0.15


def _eff_targets(o: float, c: float, h: float, low: float, closes: np.ndarray) -> dict:
    """The five efficiency definitions, from one session's OHLC and close path."""
    rng = h - low
    disp = abs(c - o)
    path = float(np.abs(np.diff(closes)).sum()) if len(closes) > 1 else np.nan
    rets = np.diff(np.log(closes)) if len(closes) > 2 and closes.min() > 0 else np.array([])
    sigma = float(np.std(rets, ddof=1)) if len(rets) > 2 else np.nan
    rw = sigma * np.sqrt(len(rets)) * o if np.isfinite(sigma) else np.nan
    mfe = max(h - o, o - low)
    return {
        "disp_pts": disp,
        "range_pts": rng,
        "path_pts": path,
        "eff_range": disp / rng if rng > 0 else np.nan,
        "eff_path": disp / path if path and path > 0 else np.nan,
        "eff_vol": disp / rw if rw and rw > 0 else np.nan,
        "eff_mfe": mfe / rng if rng > 0 else np.nan,
        "mfe_pts": mfe,
        "mae_pts": min(h - o, o - low),
    }


def _turns(closes: np.ndarray, rng: float) -> dict:
    """Path shape: how many confirmed direction changes, and where the motion happened.

    A zig-zag with a threshold: a swing is only confirmed once price retraces more than
    `TURN_THRESHOLD` of the session range away from the running extreme. Without a threshold
    every session has hundreds of sign flips and the count measures tick noise.

    The running HIGH and running LOW are tracked separately. An earlier version kept a single
    `extreme` and, while direction was still undetermined, let both the up-branch and the
    down-branch update it - so the extreme just followed the latest price, no retracement was
    ever large enough to confirm, and the function returned zero turns for every session in
    the store. The giveaway was `max_run_pts` collapsing to exactly |close - open|.
    """
    n = len(closes)
    if n < 20 or rng <= 0:
        return {"n_turns": np.nan, "first_half_disp": np.nan, "second_half_disp": np.nan,
                "max_run_pts": np.nan}
    thr = TURN_THRESHOLD * rng
    direction = 0
    pivot = hi = lo = float(closes[0])
    turns, max_run = 0, 0.0
    for x in map(float, closes[1:]):
        hi = max(hi, x)
        lo = min(lo, x)
        if direction >= 0 and (hi - x) > thr:
            max_run = max(max_run, abs(hi - pivot))
            turns += direction > 0
            direction, pivot, hi, lo = -1, hi, x, x
        elif direction <= 0 and (x - lo) > thr:
            max_run = max(max_run, abs(lo - pivot))
            turns += direction < 0
            direction, pivot, hi, lo = 1, lo, x, x
    max_run = max(max_run, abs(float(closes[-1]) - pivot))
    mid = n // 2
    return {"n_turns": float(turns),
            "first_half_disp": float(closes[mid] - closes[0]),
            "second_half_disp": float(closes[-1] - closes[mid]),
            "max_run_pts": float(max_run)}


def _session_row(sym: str, day, o: float, closes: np.ndarray, highs: np.ndarray,
                 lows: np.ndarray, vols: np.ndarray) -> dict:
    c, h, low = float(closes[-1]), float(highs.max()), float(lows.min())
    r: dict = {"tdate": day, "symbol": sym, "rth_open": o, "rth_close": c,
               "rth_high": h, "rth_low": low, "rth_volume": float(vols.sum())}
    r.update(_eff_targets(o, c, h, low, closes))
    r.update(_turns(closes, h - low))
    pv, rt = POINT_VALUE[sym], ROUND_TURN[sym]
    r["cost_opp_usd"] = r["mfe_pts"] * pv - rt
    r["round_turn_pts"] = rt / pv

    # ---- opening windows, and the remainder AFTER each -----------------------------------
    for w in OPEN_WINDOWS:
        if len(closes) <= w + 10:
            continue
        oc, oh, ol = closes[:w + 1], highs[:w + 1], lows[:w + 1]
        orng = float(oh.max() - ol.min())
        r[f"open{w}_ret_pct"] = (float(oc[-1]) / o - 1.0) * 100.0
        r[f"open{w}_range_pct"] = orng / o * 100.0
        r[f"open{w}_closeloc"] = ((float(oc[-1]) - float(ol.min())) / orng
                                  if orng > 0 else np.nan)
        # RAW opening volume. The share-of-day version is NOT causal - the day's total
        # volume is unknown at minute w - and an earlier pass of this study produced a
        # replicating "finding" from exactly that leak. `add_history` turns this into a
        # causal ratio against its own trailing mean.
        r[f"open{w}_volume"] = float(vols[:w + 1].sum())
        r[f"open{w}_vol_share_LEAKY"] = (float(vols[:w + 1].sum()) / float(vols.sum())
                                         if vols.sum() > 0 else np.nan)
        r[f"open{w}_absret_pct"] = abs(r[f"open{w}_ret_pct"])
        # the remainder, which is what an opening-conditioned decision would trade
        rc, rh, rl = closes[w:], highs[w:], lows[w:]
        base = float(rc[0])
        rest = _eff_targets(base, float(rc[-1]), float(rh.max()), float(rl.min()), rc)
        for k, v in rest.items():
            r[f"rest{w}_{k}"] = v
        r[f"rest{w}_ret_pct"] = (float(rc[-1]) / base - 1.0) * 100.0
        # did the opening move continue or reverse?
        r[f"open{w}_continued"] = float(
            np.sign(r[f"open{w}_ret_pct"]) == np.sign(r[f"rest{w}_ret_pct"]))
        r[f"open{w}_signed_cont_pct"] = (np.sign(r[f"open{w}_ret_pct"])
                                         * r[f"rest{w}_ret_pct"])
    return r


def etf_panel(sym: str) -> pd.DataFrame:
    """RTH-only minute bars, 2016-2026. The gap is the only overnight fact available."""
    d = pd.read_parquet(REPO / "data" / "minute_alpaca" / f"{sym}.parquet")
    t = d.index
    if getattr(t, "tz", None) is None:
        t = t.tz_localize("UTC")
    d = d.assign(_d=t.tz_convert("America/New_York").date).sort_index()
    rows, prev_close = [], None
    for day, g in d.groupby("_d"):
        c = g["c"].to_numpy(dtype=float)
        if len(c) < 380:
            prev_close = c[-1] if len(c) else prev_close
            continue
        o = float(g["o"].to_numpy(dtype=float)[0])
        r = _session_row(sym, day, o, c, g["h"].to_numpy(dtype=float),
                         g["l"].to_numpy(dtype=float), g["v"].to_numpy(dtype=float))
        r["gap_pct"] = ((o / prev_close - 1.0) * 100.0
                        if prev_close and prev_close > 0 else np.nan)
        rows.append(r)
        prev_close = c[-1]
    out = pd.DataFrame(rows)
    return out[out["gap_pct"].abs() < 10.0].reset_index(drop=True)


def futures_panel(sym: str) -> pd.DataFrame:
    """Full 24h store; carries the overnight PATH the ETF store cannot see."""
    from overnight_panel import RTH_LAST, RTH_OPEN, _overnight, load_full_session
    df = load_full_session(sym)
    rows = []
    for tdate, g in df.groupby("tdate", sort=True):
        on = _overnight(g)
        rth = g[(g["hm"] >= RTH_OPEN) & (g["hm"] <= RTH_LAST)]
        if len(on) < 200 or len(rth) < 300:
            continue
        c = rth["c"].to_numpy(dtype=float)
        o = float(c[0])
        r = _session_row(sym, tdate, o, c, rth["h"].to_numpy(dtype=float),
                         rth["l"].to_numpy(dtype=float), rth["v"].to_numpy(dtype=float))
        oc = on["c"].to_numpy(dtype=float)
        oh, ol = on["h"].to_numpy(dtype=float), on["l"].to_numpy(dtype=float)
        ref, on_hi, on_lo = float(oc[0]), float(oh.max()), float(ol.min())
        on_rng = on_hi - on_lo
        prev = np.concatenate([[oc[0]], oc[:-1]])
        tr = np.maximum(oh - ol, np.maximum(np.abs(oh - prev), np.abs(ol - prev)))
        r.update({
            "gap_pct": (o / float(oc[-1]) - 1.0) * 100.0,
            "on_ret_pct": (float(oc[-1]) / ref - 1.0) * 100.0,
            "on_range_pct": on_rng / ref * 100.0,
            "on_atr_pct": float(np.mean(tr)) / ref * 100.0,
            "on_rv_pct": float(np.sqrt(np.sum(np.diff(np.log(oc)) ** 2))) * 100.0,
            "on_volume": float(on["v"].sum()),
            "on_closeloc": ((float(oc[-1]) - on_lo) / on_rng) if on_rng > 0 else np.nan,
            "on_high": on_hi, "on_low": on_lo,
            # wick structure: how much of the overnight range was rejected on each side
            "on_upper_wick": ((on_hi - max(float(oc[0]), float(oc[-1]))) / on_rng
                              if on_rng > 0 else np.nan),
            "on_lower_wick": ((min(float(oc[0]), float(oc[-1])) - on_lo) / on_rng
                              if on_rng > 0 else np.nan),
            "on_eff": (abs(float(oc[-1]) - float(oc[0])) / on_rng
                       if on_rng > 0 else np.nan),
        })
        rows.append(r)
    return pd.DataFrame(rows)


def add_history(p: pd.DataFrame) -> pd.DataFrame:
    """Prior-session facts and trailing states. Shifted within instrument, always."""
    out = []
    for _, g in p.groupby("symbol", sort=False):
        g = g.sort_values("tdate").copy()
        for src in ("eff_range", "eff_path", "eff_vol", "range_pts", "disp_pts", "n_turns"):
            g[f"prev_{src}"] = g[src].shift(1)
        g["prev_ret_pct"] = ((g["rth_close"] / g["rth_open"] - 1.0) * 100.0).shift(1)
        g["prev_closeloc"] = (((g["rth_close"] - g["rth_low"])
                               / (g["rth_high"] - g["rth_low"])).shift(1))
        g["prev_range_pct"] = (g["range_pts"] / g["rth_open"] * 100.0).shift(1)
        g["prev_rv_pct"] = (g["path_pts"] / g["rth_open"] * 100.0).shift(1)
        # consecutive same-direction sessions, causal
        sign = np.sign(g["rth_close"] - g["rth_open"]).shift(1).fillna(0.0)
        streak, cur = [], 0.0
        for s in sign:
            cur = cur + s if (cur == 0 or np.sign(cur) == s) and s != 0 else s
            streak.append(cur)
        g["prev_streak"] = streak
        # trailing efficiency and volatility states
        # Causal opening-volume intensity: today's opening volume against the trailing
        # mean of the SAME window on prior sessions. Knowable at minute w; the share-of-day
        # version is not.
        for w in OPEN_WINDOWS:
            col = f"open{w}_volume"
            if col in g.columns:
                g[f"open{w}_vol_rel"] = g[col] / g[col].shift(1).rolling(20).mean()
        g["trail_eff_5"] = g["eff_range"].shift(1).rolling(5).mean()
        g["trail_eff_20"] = g["eff_range"].shift(1).rolling(20).mean()
        g["trail_rv_5"] = g["prev_rv_pct"].rolling(5).mean()
        g["trail_rv_20"] = g["prev_rv_pct"].rolling(20).mean()
        g["vol_state"] = np.log(g["trail_rv_5"] / g["trail_rv_20"])
        g["eff_state"] = g["trail_eff_5"] - g["trail_eff_20"]
        out.append(g)
    return pd.concat(out, ignore_index=True)


def main() -> int:
    etf = add_history(pd.concat([etf_panel(s) for s in ("SPY", "QQQ", "IWM", "DIA")],
                                ignore_index=True))
    fut = add_history(pd.concat([futures_panel(s) for s in ("ES", "NQ", "MES", "MNQ")],
                                ignore_index=True))
    etf.to_parquet(REPO / "research" / "efficiency_etf.parquet", index=False)
    fut.to_parquet(REPO / "research" / "efficiency_futures.parquet", index=False)

    print("=" * 96)
    print("EFFICIENCY PANEL")
    print("=" * 96)
    for name, p in (("ETF", etf), ("FUTURES", fut)):
        print(f"\n{name}:")
        for sym, g in p.groupby("symbol"):
            print(f"  {sym:5} {len(g):5d} sessions  {g.tdate.min()} .. {g.tdate.max()}")

    print("\n" + "=" * 96)
    print("THE FIVE EFFICIENCY DEFINITIONS, DESCRIBED")
    print("=" * 96)
    print(f"{'panel':8} {'sym':5} " + "".join(f"{k:>12}" for k in
          ("eff_range", "eff_path", "eff_vol", "eff_mfe")) + f"{'cost_opp $':>12}")
    for name, p in (("ETF", etf), ("FUTURES", fut)):
        for sym, g in p.groupby("symbol"):
            cells = "".join(f"{g[k].median():12.3f}" for k in
                            ("eff_range", "eff_path", "eff_vol", "eff_mfe"))
            print(f"{name:8} {sym:5} {cells}{g['cost_opp_usd'].median():12.0f}")
    print("\n  eff_vol near 1.0 means 'displaced as far as a random walk would'. Below 1 is")
    print("  mean-reverting chop; above 1 is trend.")

    print("\n" + "=" * 96)
    print("HOW CORRELATED ARE THE FIVE TARGETS?  (if they agree, the choice does not matter)")
    print("=" * 96)
    keys = ["eff_range", "eff_path", "eff_vol", "eff_mfe", "cost_opp_usd"]
    for name, p in (("ETF", etf), ("FUTURES", fut)):
        print(f"\n{name} (pooled, Spearman):")
        sub = p[keys].dropna()
        rk = sub.rank()
        print("            " + "".join(f"{k[:10]:>12}" for k in keys))
        for i, a in enumerate(keys):
            row = "".join(f"{np.corrcoef(rk[a], rk[b])[0, 1]:12.3f}" for b in keys)
            print(f"{a[:11]:12}{row}")
    print(f"\nwrote research/efficiency_etf.parquet and research/efficiency_futures.parquet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
