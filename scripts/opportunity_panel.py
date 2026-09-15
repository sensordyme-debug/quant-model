"""Phase 1: an opportunity model. How much is there to win today, decided at 09:29.

THE QUESTION THIS ANSWERS, AND THE ONE IT DOES NOT
---------------------------------------------------
The previous study closed the direction question hard: eight framings of "overnight tells you
which way" all failed, out-of-sample R-squared was negative on every instrument, and the one
gate that looked like it worked was exposed as a reduction in exposure wearing a story.

What survived was magnitude. Overnight range and overnight volume predict the regular
session's range at t between 5.6 and 7.7, and they still do it after yesterday's range is
already in the model, at an incremental out-of-sample R-squared of 0.04 to 0.08.

This module turns that into a forecast rather than a correlation, because a correlation
cannot gate anything. A gate needs a NUMBER at 09:29 - an expected range, a probability that
the day is big enough to be worth trading - and it needs that number to have been produced
without looking at the day it is forecasting.

WHY THE TARGETS ARE WHAT THEY ARE
----------------------------------
Four targets, and the last two are the ones that matter for a Combine.

  rth_range_pct        how wide the day gets. The natural magnitude target.
  rth_rv_pct           realised volatility over the session. Range's less outlier-prone twin;
                       carried because a single spike makes range and leaves rv alone, and a
                       forecast that only works on one of them is suspect.
  p_range_gt(k)        probability the day's range exceeds k times the round-turn cost. This
                       is the decision-relevant quantity: a mechanism that needs ten round
                       turns needs a day that can pay for ten round turns.
  p_move_gt_cost       probability the session's NET move covers a single round turn. The
                       weakest possible bar, included so the report can say how often even
                       that is missed.

NO THRESHOLD OPTIMISATION HERE, DELIBERATELY
---------------------------------------------
The brief says not to optimise thresholds initially and it is right to say so. Every quantile
cut in this module is a fixed conventional level - deciles, terciles - declared before the
data is read. The place where a threshold could be tuned is the gate, and the gate is in a
later module where its multiplicity can be counted. Mixing the two is how a forecast quietly
becomes a fit.

CAUSALITY
---------
Every predictor is computable at 09:29 ET on the trade date. Prior-day columns are shifted by
one trade date within instrument. Every rolling statistic uses `shift(1)` before the window,
so the day being predicted never enters its own predictor. `test_opportunity.py` checks this
by perturbation rather than by reading the code.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

#: Round-turn cost in dollars, and the point value, so cost can be expressed in points.
ROUND_TURN = {"ES": 3.78, "NQ": 3.78, "MES": 1.22, "MNQ": 1.22}
POINT_VALUE = {"ES": 50.0, "NQ": 20.0, "MES": 5.0, "MNQ": 2.0}

#: How many round turns a mechanism might spend in a session. Declared, not tuned.
COST_MULTIPLES = (1, 5, 10, 20)

#: The fourteen predictors the brief asks for. Order fixed so the report is reproducible.
PREDICTORS = (
    "on_range_pct",            # overnight range
    "on_rv_pct",               # overnight realised volatility
    "on_atr_pct",              # overnight ATR, a range measure robust to a single spike
    "on_volume",               # overnight volume, raw
    "on_range_pctile",         # overnight range percentile, expanding, causal
    "on_volume_pctile",        # overnight volume percentile, expanding, causal
    "on_close_loc",            # where it closed inside its own range
    "on_absret_pct",           # overnight return magnitude
    "on_ret_over_vol",         # overnight return normalised by overnight volatility
    "on_expansion",            # overnight high/low expansion vs its own trailing range
    "prev_rth_range_pct",      # prior-day RTH range
    "prev_rth_rv_pct",         # prior-day RTH realised volatility
    "on_over_prev_range",      # overnight range / prior-day RTH range
    "on_vol_ratio",            # overnight volume / trailing mean overnight volume
    "vol_state",               # expansion / contraction state, signed
)


def _rv_pct(c: np.ndarray) -> float:
    """Realised volatility of a close series, as a percent of its first price."""
    if len(c) < 3 or c[0] <= 0:
        return np.nan
    return float(np.sqrt(np.sum(np.diff(np.log(c)) ** 2)) * 100.0)


def _atr_pct(h: np.ndarray, low: np.ndarray, c: np.ndarray, n: int = 14) -> float:
    """Average true range over the leg, as a percent. Uses every bar, not a trailing n."""
    if len(c) < 3 or c[0] <= 0:
        return np.nan
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - low, np.maximum(np.abs(h - prev), np.abs(low - prev)))
    return float(np.mean(tr) / c[0] * 100.0)


def build(symbol: str) -> pd.DataFrame:
    """One row per trade date: the overnight leg's description and the RTH leg's outcome."""
    from overnight_panel import RTH_LAST, RTH_OPEN, _overnight, load_full_session

    df = load_full_session(symbol)
    rows = []
    for tdate, g in df.groupby("tdate", sort=True):
        on = _overnight(g)
        rth = g[(g["hm"] >= RTH_OPEN) & (g["hm"] <= RTH_LAST)]
        if len(on) < 200 or len(rth) < 300:
            continue
        oc = on["c"].to_numpy(dtype=float)
        oh, ol = on["h"].to_numpy(dtype=float), on["l"].to_numpy(dtype=float)
        rc = rth["c"].to_numpy(dtype=float)
        ref = float(oc[0])
        on_hi, on_lo = float(oh.max()), float(ol.min())
        on_range = on_hi - on_lo
        on_rv = _rv_pct(oc)

        rows.append({
            "tdate": tdate, "symbol": symbol,
            "rth_open": float(rc[0]),
            # ---- overnight description, all knowable at 09:29 -------------------------
            "on_range_pct": on_range / ref * 100.0 if ref else np.nan,
            "on_rv_pct": on_rv,
            "on_atr_pct": _atr_pct(oh, ol, oc),
            "on_volume": float(on["v"].sum()),
            "on_close_loc": ((float(oc[-1]) - on_lo) / on_range) if on_range > 0 else np.nan,
            "on_ret_pct": (float(oc[-1]) / ref - 1.0) * 100.0 if ref else np.nan,
            "on_high": on_hi, "on_low": on_lo, "on_close": float(oc[-1]),
            # ---- the RTH outcome, all strictly after 09:30 -----------------------------
            "rth_range_pct": float(rth["h"].max() - rth["l"].min()) / float(rc[0]) * 100.0,
            "rth_range_pts": float(rth["h"].max() - rth["l"].min()),
            "rth_rv_pct": _rv_pct(rc),
            "rth_ret_pct": (float(rc[-1]) / float(rc[0]) - 1.0) * 100.0,
            "rth_ret_pts": float(rc[-1] - rc[0]),
            "rth_absret_pts": abs(float(rc[-1] - rc[0])),
        })
    p = pd.DataFrame(rows)
    if p.empty:
        return p
    p["on_absret_pct"] = p["on_ret_pct"].abs()
    p["on_ret_over_vol"] = p["on_ret_pct"] / p["on_rv_pct"].replace(0.0, np.nan)
    return p


def add_causal_predictors(p: pd.DataFrame) -> pd.DataFrame:
    """Everything that needs history. Shifted within instrument so today never sees itself.

    The `shift(1)` before every rolling and expanding window is the whole causality argument.
    A percentile computed on a window that includes today's value tells you today's value.
    """
    out = []
    for _, g in p.groupby("symbol", sort=False):
        g = g.sort_values("tdate").copy()
        # prior-day RTH facts
        g["prev_rth_range_pct"] = g["rth_range_pct"].shift(1)
        g["prev_rth_rv_pct"] = g["rth_rv_pct"].shift(1)
        # expanding percentiles of the overnight description, on history only
        for src, dst in (("on_range_pct", "on_range_pctile"),
                         ("on_volume", "on_volume_pctile")):
            s = g[src]
            g[dst] = s.shift(1).expanding(40).rank(pct=True)
            # rank(pct) on the shifted history gives today's standing among prior days only
            g[dst] = [
                float((s.iloc[:i] < s.iloc[i]).mean()) if i >= 40 else np.nan
                for i in range(len(g))]
        # overnight range against the day before it, and against the prior RTH range
        g["on_expansion"] = g["on_range_pct"] / g["on_range_pct"].shift(1).rolling(20).mean()
        g["on_over_prev_range"] = g["on_range_pct"] / g["prev_rth_range_pct"]
        g["on_vol_ratio"] = g["on_volume"] / g["on_volume"].shift(1).rolling(20).mean()
        # expansion / contraction state: is trailing short-horizon vol above longer-horizon?
        short = g["prev_rth_rv_pct"].rolling(5).mean()
        long = g["prev_rth_rv_pct"].rolling(20).mean()
        g["vol_state"] = np.log(short / long)
        out.append(g)
    return pd.concat(out, ignore_index=True)


def add_targets(p: pd.DataFrame) -> pd.DataFrame:
    """The decision-relevant binary targets, in the instrument's own cost units."""
    p = p.copy()
    rt_pts = p["symbol"].map(lambda s: ROUND_TURN[s] / POINT_VALUE[s])
    p["round_turn_pts"] = rt_pts
    for k in COST_MULTIPLES:
        p[f"range_gt_{k}rt"] = (p["rth_range_pts"] > k * rt_pts).astype(float)
    p["move_gt_cost"] = (p["rth_absret_pts"] > rt_pts).astype(float)
    return p


def main() -> int:
    frames = [build(s) for s in ["ES", "NQ", "MES", "MNQ"]]
    p = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    p = add_targets(add_causal_predictors(p))
    out = REPO / "research" / "opportunity_panel.parquet"
    p.to_parquet(out, index=False)

    print("=" * 92)
    print("OPPORTUNITY PANEL")
    print("=" * 92)
    for sym, g in p.groupby("symbol"):
        print(f"{sym:5} {len(g):4d} sessions  {g.tdate.min()} .. {g.tdate.max()}  "
              f"round turn {g['round_turn_pts'].iloc[0]:.4f} pts")
    print(f"\n{len(p)} rows -> {out}")

    print("\n" + "=" * 92)
    print("HOW OFTEN IS THERE ENOUGH MOVEMENT TO PAY FOR TRADING?")
    print("=" * 92)
    print(f"{'sym':5} " + "".join(f"{'P(range>' + str(k) + 'rt)':>16}" for k in COST_MULTIPLES)
          + f"{'P(|move|>rt)':>14}")
    for sym, g in p.groupby("symbol"):
        cells = "".join(f"{g[f'range_gt_{k}rt'].mean():16.3f}" for k in COST_MULTIPLES)
        print(f"{sym:5} {cells}{g['move_gt_cost'].mean():14.3f}")
    print("\n  Cost is not the binding constraint at session horizon: even 20 round turns is")
    print("  covered by the day's range essentially always. What a gate can add is therefore")
    print("  not 'can we afford to trade' but 'is the day big enough to be worth the risk'.")

    print("\n" + "=" * 92)
    print("PREDICTOR COVERAGE (non-null share, after the causal warm-up)")
    print("=" * 92)
    print(f"{'predictor':24}" + "".join(f"{s:>9}" for s in ["ES", "NQ", "MES", "MNQ"]))
    for f in PREDICTORS:
        cells = "".join(f"{p[p.symbol == s][f].notna().mean():9.2f}"
                        for s in ["ES", "NQ", "MES", "MNQ"])
        print(f"{f:24}{cells}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
