"""Phase 6: does overnight information become useful once the opening auction has spoken?

THE ARGUMENT FOR LOOKING ONE MORE TIME
----------------------------------------
Overnight information does not predict the regular session's direction. That has now been
established eight ways on the futures panel, again on 2,662 ETF sessions, and again through
110 conditional cells. Nothing survived.

But every one of those tests asked the overnight session to predict the session from 09:30.
The opening auction is where overnight order flow actually clears, and it is entirely
plausible that the overnight number is uninformative on its own and informative in
combination with what the first few minutes do with it. "Gapped up and held" and "gapped up
and immediately sold" are different states, and neither is visible in the gap alone.

This is the last directional avenue in the brief, and it is a real one rather than a
consolation prize: the interaction is a genuinely different hypothesis, not a re-run.

THE THREE MODELS, WHICH IS THE WHOLE DESIGN
---------------------------------------------
For each opening window - 5, 15, 30 and 60 minutes - the remainder of the session is
forecast three ways:

    overnight only   the overnight variables, ignoring what the open did
    opening only     what the open did, ignoring the overnight
    both             overnight, opening, and their INTERACTION

The interaction term is the point. If "both" beats the better of the two singles, then
overnight information has conditional value that it does not have alone, and that is a
finding. If "both" merely matches "opening only", the overnight session contributed nothing
and the opening was doing all the work.

Reporting all three is what makes that distinguishable. A single model that includes
everything and posts a positive R-squared would prove nothing, because the opening return is
in it.

THE COST OF LOOKING AT THE OPEN
--------------------------------
Waiting until 10:30 to make a decision throws away an hour of a session that must be flat by
16:10 ET. That is a real cost and it is reported: the remaining session's typical movement
shrinks as the decision is deferred, so a later signal has to be proportionally better to be
worth the same money. The table prints the remaining range alongside the R-squared so the two
can be read together.

WHERE
-----
Both panels. The futures store has the contracts that would actually be traded, at 312 and
251 sessions. The ETF store has 2,600 sessions, a minimum detectable correlation three times
smaller, and no overnight path - but the opening-transition hypothesis needs only the
close-to-open gap and the intraday bars, both of which it has. A null on the ETF panel is
therefore a real null rather than a statement about sample size.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from quant_brain.research import opportunity as opp  # noqa: E402

#: Decision points, in minutes after 09:30.
WINDOWS = (5, 15, 30, 60)
MIN_TRAIN = 120


def etf_intraday(sym: str) -> pd.DataFrame:
    """Per trade date: the gap, the first-N-minute returns, and the remainder after each."""
    d = pd.read_parquet(REPO / "data" / "minute_alpaca" / f"{sym}.parquet")
    t = d.index
    if getattr(t, "tz", None) is None:
        t = t.tz_localize("UTC")
    t = t.tz_convert("America/New_York")
    d = d.assign(_d=t.date).sort_index()
    rows = []
    prev_close = None
    for day, g in d.groupby("_d"):
        c = g["c"].to_numpy(dtype=float)
        h, low = g["h"].to_numpy(dtype=float), g["l"].to_numpy(dtype=float)
        o = float(g["o"].to_numpy(dtype=float)[0])
        if len(c) < 380 or prev_close is None or prev_close <= 0:
            prev_close = c[-1] if len(c) else prev_close
            continue
        r = {"tdate": day, "symbol": sym,
             "gap_pct": (o / prev_close - 1.0) * 100.0,
             "rth_ret_pct": (c[-1] / o - 1.0) * 100.0,
             "rth_range_pct": (h.max() - low.min()) / o * 100.0}
        for w in WINDOWS:
            if len(c) > w + 5:
                r[f"open{w}_pct"] = (c[w] / o - 1.0) * 100.0
                r[f"rest{w}_pct"] = (c[-1] / c[w] - 1.0) * 100.0
                r[f"restrange{w}_pct"] = (h[w:].max() - low[w:].min()) / c[w] * 100.0
        rows.append(r)
        prev_close = c[-1]
    out = pd.DataFrame(rows)
    return out[out["gap_pct"].abs() < 10.0].reset_index(drop=True)


def futures_intraday(sym: str) -> pd.DataFrame:
    from overnight_panel import RTH_LAST, RTH_OPEN, _overnight, load_full_session
    df = load_full_session(sym)
    rows = []
    for tdate, g in df.groupby("tdate", sort=True):
        on = _overnight(g)
        rth = g[(g["hm"] >= RTH_OPEN) & (g["hm"] <= RTH_LAST)]
        if len(on) < 200 or len(rth) < 300:
            continue
        oc = on["c"].to_numpy(dtype=float)
        c = rth["c"].to_numpy(dtype=float)
        h, low = rth["h"].to_numpy(dtype=float), rth["l"].to_numpy(dtype=float)
        o = float(c[0])
        on_hi, on_lo = float(on["h"].max()), float(on["l"].min())
        r = {"tdate": tdate, "symbol": sym,
             "gap_pct": (o / float(oc[-1]) - 1.0) * 100.0,
             "on_ret_pct": (float(oc[-1]) / float(oc[0]) - 1.0) * 100.0,
             "on_range_pct": (on_hi - on_lo) / float(oc[0]) * 100.0,
             "on_close_loc": ((float(oc[-1]) - on_lo) / (on_hi - on_lo))
             if on_hi > on_lo else np.nan,
             "rth_ret_pct": (c[-1] / o - 1.0) * 100.0,
             "rth_range_pct": (h.max() - low.min()) / o * 100.0}
        for w in WINDOWS:
            if len(c) > w + 5:
                r[f"open{w}_pct"] = (c[w] / o - 1.0) * 100.0
                r[f"rest{w}_pct"] = (c[-1] / c[w] - 1.0) * 100.0
                r[f"restrange{w}_pct"] = (h[w:].max() - low[w:].min()) / c[w] * 100.0
        rows.append(r)
    return pd.DataFrame(rows)


def score(g: pd.DataFrame, feats: list[str], target: str) -> tuple[float, int]:
    """Causal walk-forward out-of-sample R-squared against the expanding mean."""
    sub = g.dropna(subset=[*feats, target]).reset_index(drop=True)
    if len(sub) < MIN_TRAIN + 40:
        return np.nan, len(sub)
    x = sub[feats].to_numpy(dtype=float)
    y = sub[target].to_numpy(dtype=float)
    pred = opp.walk_forward(x, y, min_train=MIN_TRAIN)
    return opp.oos_r2(y, pred, opp.expanding_mean(y, min_train=MIN_TRAIN))


def run(panel: pd.DataFrame, on_feats: list[str], label: str) -> pd.DataFrame:
    rows = []
    print(f"\n{'=' * 106}")
    print(f"{label}")
    print(f"{'=' * 106}")
    print(f"{'sym':5} {'win':>4} {'n':>5} {'overnight only':>15} {'opening only':>14} "
          f"{'both+interact':>15} {'best single':>12} {'gain':>8} {'rest range %':>13}")
    for sym, g in panel.groupby("symbol"):
        g = g.sort_values("tdate").reset_index(drop=True)
        for w in WINDOWS:
            oc, rc = f"open{w}_pct", f"rest{w}_pct"
            if rc not in g.columns:
                continue
            gg = g.copy()
            gg["interact"] = gg[oc] * gg[on_feats[0]]
            r_on, n = score(gg, on_feats, rc)
            r_op, _ = score(gg, [oc], rc)
            r_both, _ = score(gg, [*on_feats, oc, "interact"], rc)
            best = np.nanmax([r_on, r_op])
            gain = r_both - best if np.isfinite(best) else np.nan
            rr = float(gg[f"restrange{w}_pct"].median())
            rows.append({"panel": label, "symbol": sym, "window": w, "n": n,
                         "r2_overnight": r_on, "r2_opening": r_op, "r2_both": r_both,
                         "gain_over_best_single": gain, "rest_range_pct": rr})
            print(f"{sym:5} {w:4d} {n:5d} {r_on:15.4f} {r_op:14.4f} {r_both:15.4f} "
                  f"{best:12.4f} {gain:+8.4f} {rr:13.3f}")
    return pd.DataFrame(rows)


def main() -> int:
    etf = pd.concat([etf_intraday(s) for s in ("SPY", "QQQ")], ignore_index=True)
    fut = pd.concat([futures_intraday(s) for s in ("ES", "NQ", "MES", "MNQ")],
                    ignore_index=True)

    print("=" * 106)
    print("PHASE 6 - THE OPENING TRANSITION")
    print("target: the REMAINDER of the session after the decision point.")
    print("A positive number means the model beat the historical mean out of sample.")
    print("=" * 106)

    a = run(etf, ["gap_pct"], "ETF PANEL  (SPY, QQQ, 2016-2026)")
    b = run(fut, ["on_ret_pct", "on_range_pct", "on_close_loc"],
            "FUTURES PANEL  (ES, NQ, MES, MNQ, 2025-2026)")

    out = pd.concat([a, b], ignore_index=True)
    out.to_csv(REPO / "research" / "opening_transition.csv", index=False)

    print("\n" + "=" * 106)
    print("DOES DEFERRING THE DECISION HELP?")
    print("=" * 106)
    pos = out[out["r2_both"] > 0]
    print(f"  cells where ANY model beat the mean out of sample: "
          f"{len(pos)} of {len(out)}")
    print(f"  cells where the interaction model beat both singles: "
          f"{int((out['gain_over_best_single'] > 0).sum())} of {len(out)}")
    best = out.loc[out["r2_both"].idxmax()] if out["r2_both"].notna().any() else None
    if best is not None:
        print(f"\n  best cell: {best['panel']} {best['symbol']} at {int(best['window'])}m, "
              f"R2 = {best['r2_both']:+.4f}")
    print("\n  For reference, every R-squared here should be compared against the value")
    print("  a coin flip produces, which is 0.0 - and against the negative values that an")
    print("  honestly-fitted model produces when the true coefficients are zero.")

    print("\n" + "=" * 106)
    print("THE COST OF WAITING: how much session is left at each decision point")
    print("=" * 106)
    print(f"{'sym':5} " + "".join(f"{'at ' + str(w) + 'm':>12}" for w in WINDOWS)
          + f"{'full RTH':>12}")
    for sym, g in pd.concat([etf, fut]).groupby("symbol"):
        cells = "".join(f"{g[f'restrange{w}_pct'].median():12.3f}" for w in WINDOWS
                        if f"restrange{w}_pct" in g.columns)
        print(f"{sym:5} {cells}{g['rth_range_pct'].median():12.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
