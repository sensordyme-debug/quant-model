"""PART 6-14: carry the dev survivors through every remaining gate, on one scorecard.

    python scripts/mechanism_scorecard.py

The horizon for each mechanism was CHOSEN ON DEV and is carried unchanged into validation.
That is what the split is for. The holdout is not read by this script at all.

No parameter is searched. The exit is the simplest conceptually justified one - hold for the
dev-selected horizon, plus a fixed stop sized to the mechanism's own adverse excursion - and
there are exactly two of them, which is the declared budget.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from mechanism_screen import (  # noqa: E402
    OPEN_MIN,
    build,
    forward,
    mechanisms,
    non_overlapping,
)

from quant_brain.markets.futures_cme import topstep as ts  # noqa: E402
from quant_brain.research import feasibility as F  # noqa: E402

#: mechanism -> horizon selected on the DEV split, frozen before validation was read
SURVIVORS = {
    "mean_reversion_z2": 10,
    "orb_failure": 30,
    "session_hl_rejection": 30,
    "tod_meanrev_late": 30,
    "trend_pullback": 30,
}
MLL = ts.MLL[50_000].value
TARGET = ts.COMBINE_PROFIT_TARGET[50_000].value


def run(sessions, nm, h, inst, contracts, stop_points=None):
    pv = F.POINT_VALUE[inst] * contracts
    rt = F.round_turn_cost(inst, contracts)
    prior_h = prior_l = float("nan")
    trades, days = [], {}
    for s in sessions:
        M = mechanisms(s, prior_h, prior_l)
        rth = s.minute >= OPEN_MIN
        prior_h = s.h[rth].max() if rth.any() else float("nan")
        prior_l = s.lo[rth].min() if rth.any() else float("nan")
        lg, sh = M[nm]
        keep = non_overlapping(np.flatnonzero(lg | sh), h)
        f = forward(s, h)
        day_total = 0.0
        for i in keep:
            if not np.isfinite(f[i]):
                continue
            d = 1.0 if lg[i] else -1.0
            j = min(i + h, len(s.c) - 1)
            lows, highs = s.lo[i:j + 1], s.h[i:j + 1]
            adverse = (lows.min() - s.c[i]) if d > 0 else (s.c[i] - highs.max())
            move = f[i] * d
            if stop_points is not None and -adverse >= stop_points:
                move = -stop_points            # stopped at the level, the repo's policy
            p = move * pv - rt
            trades.append({"pnl": p, "mae_pts": adverse, "day": s.day})
            day_total += p
        days[s.day] = days.get(s.day, 0.0) + day_total
    return trades, days


def stats(trades, days, sessions):
    pnl = np.array([t["pnl"] for t in trades]) if trades else np.zeros(0)
    dv = np.array([days.get(s.day, 0.0) for s in sessions])
    if pnl.size == 0:
        return {"trades": 0}
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    srt = np.sort(pnl)[::-1]
    tot = pnl.sum()
    streak = best = 0
    for x in pnl:
        streak = streak + 1 if x < 0 else 0
        best = max(best, streak)
    eq = np.cumsum(dv)
    peak = np.maximum.accumulate(eq)
    return {
        "trades": int(pnl.size),
        "trades_per_session": round(pnl.size / len(sessions), 3),
        "net_total": round(float(tot), 2),
        "net_per_session": round(float(tot / len(sessions)), 2),
        "expectancy": round(float(pnl.mean()), 2),
        "median_trade": round(float(np.median(pnl)), 2),
        "win_rate": round(float((pnl > 0).mean()), 4),
        "profit_factor": round(float(wins.sum() / -losses.sum()), 3) if losses.size else None,
        "max_dd": round(float((peak - eq).max()), 2),
        "worst_day": round(float(dv.min()), 2),
        "longest_losing_streak": int(best),
        "top10_share_of_total": round(float(srt[:10].sum() / tot), 3) if tot else None,
        "mae_p95_dollars": round(float(np.percentile(
            np.abs([t["mae_pts"] for t in trades]), 95)), 2),
        "mae_worst_dollars": round(float(np.abs([t["mae_pts"] for t in trades]).max()), 2),
        "positive_sessions": round(float((dv > 0).mean()), 4),
    }


def main() -> int:
    out = {}
    print(f"{'mechanism':22}{'inst':5}{'h':>4}{'dev $/s':>10}{'val $/s':>10}"
          f"{'sign':>6}{'top10':>8}{'MAEp95$':>9}{'vsMLL':>7}{'trd/s':>7}")
    for inst, k in (("NQ", 1), ("MNQ", 10)):
        ses = build(inst)
        d, v = int(len(ses) * 0.6), int(len(ses) * 0.8)
        dev, val = ses[:d], ses[d:v]
        pvk = F.POINT_VALUE[inst] * k
        for nm, h in SURVIVORS.items():
            td, dd = run(dev, nm, h, inst, k)
            tv, dvv = run(val, nm, h, inst, k)
            sd, sv = stats(td, dd, dev), stats(tv, dvv, val)
            mae95 = sd["mae_p95_dollars"] * pvk
            agree = "same" if np.sign(sd["net_per_session"]) == np.sign(
                sv.get("net_per_session", 0)) else "FLIP"
            out[f"{inst}:{nm}"] = {"instrument": inst, "contracts": k, "horizon": h,
                                   "dev": sd, "val": sv,
                                   "mae_p95_dollars": round(mae95, 2),
                                   "mll": MLL, "dev_val_sign": agree}
            print(f"{nm:22}{inst:5}{h:>4}{sd['net_per_session']:>10,.2f}"
                  f"{sv.get('net_per_session', 0):>10,.2f}{agree:>6}"
                  f"{sd['top10_share_of_total']:>8.1%}{mae95:>9,.0f}"
                  f"{'OVER' if mae95 > MLL else 'under':>7}{sd['trades_per_session']:>7.2f}")

    dest = REPO / "research/mechanisms/scorecard.json"
    dest.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"\nMLL ${MLL:,.0f}   target ${TARGET:,.0f}")
    print(f"wrote {dest.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
