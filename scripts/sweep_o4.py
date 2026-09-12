"""O-4: can this track survive without a quote feed? The false-positive rate of trade-print data.

Why this study exists
---------------------
The Theta Data options plan lapsed from STANDARD to FREE between 2026-09-10 02:24 and
2026-09-12 13:32 (both `Subscriptions:` lines are in the terminal's own log). On FREE every
option data endpoint returns the entitlement error and only `/v3/option/list/*` still answers,
so the 0DTE store is frozen at 1,891 sessions ending 2026-09-10.

The only other options source this repository can reach is Alpaca. Probed live on 2026-09-12
with the existing key, it serves `/v1beta1/options/bars` and `/v1beta1/options/trades` back to
roughly 2024-02 (2024-03-15 returns data, 2024-02-02 and every 2022/2023 date returns an empty
body), and `/v1beta1/options/snapshots/<root>` returns a *current* bid/ask. It does **not**
serve historical option quotes: `/v1beta1/options/quotes` is 404 on this account.

That is the whole question. O-2 refused the SPY 0DTE credit spread on cost, not on edge, and
the decisive term was the spread crossed on every fill (-1.363% of the position's own maximum
loss against gross +0.783%). A trade-print dataset cannot see that term. So before this track
spends an iteration porting itself to Alpaca, measure what porting would do to its verdicts.

Design, pre-registered before any run
-------------------------------------
Two estimators, the *same* sessions and the *same* trades, differing only in what the data can
see. Both are computed from the columns `sweep_o2.run_session` already returns; no line of the
trade is re-implemented here.

  NET_QUOTE = pnl / risk                  O-2's method and the truth: the short leg is sold at
                                          the bid and the long leg bought at the ask, reversed
                                          on exit, plus commission.
  NET_PRINT = (pnl_gross - fees) / risk   the best a trade-print dataset can do: fills at the
                                          mid, plus commission. The bid/ask it would need to do
                                          better is not in the data.

NET_PRINT is deliberately *generous* to the fallback. Real prints are the mid plus noise and
sit nearer the far touch on a marketable order, so an honest Alpaca backtest would be at least
this wrong and probably worse. Every number below is therefore an upper bound on the fallback's
accuracy, and any failure it shows is a floor on the fallback's error.

Grid: O-2's own axes, taken unchanged so that no new tuning enters here.
  structure {put, call} x target {0.05, 0.10, 0.16, 0.25, 0.35}
  x width_pct {0.003, 0.0075, 0.015} x entry {10:00, 14:00},  exit 15:50, fee $0.75 = 60 cells.

Verdict rule, also O-2's, applied identically to both estimators: mean return on risk positive
with t > 2 in at least two of the three a-priori regimes (2016-2019, 2020-2023, 2024-2026).

Pre-registered statistics and the conclusion rule
-------------------------------------------------
  1. SIGN FLIP      cells with mean NET_PRINT > 0 and mean NET_QUOTE <= 0.
  2. DECISION FLIP  cells that PASS the verdict rule under NET_PRINT and FAIL it under
                    NET_QUOTE. This is the false-positive count of the fallback and is the
                    headline number.
  3. FALSE NEGATIVE the reverse: pass under quote, fail under print.
  4. BLIND TERM     the distribution across the grid of spread_cost / risk, the quantity the
                    fallback cannot observe, in points of maximum loss.

Declared before the run: if DECISION FLIP >= 1, trade-print data is disqualified for
cost-sensitive options research on this track, and a quote source - the restored Theta plan or
another vendor - is the only path. If DECISION FLIP == 0 and the blind term is small relative
to the dispersion of NET_QUOTE, the fallback is usable and the track can continue unblocked.

Added after the first run, and labelled post-hoc in the output because it is
---------------------------------------------------------------------------
DECISION FLIP came back 0, and the reason is degenerate rather than reassuring: **no cell
reaches t > +2 under either estimator**, so a statistic that only detects a fallback inventing
a *pass* is identically zero here whatever the fallback does. It had no power. The direction
that does have power is the mirror image, and it is the one this track actually depends on,
because every O-item to date has ended in a refusal: can the fallback still *refuse*? The
post-hoc block counts cells decisively refused on quotes (t < -2) that stop being decisive on
prints. The pre-registered block is left exactly as it was run.

    py -3.11 scripts/sweep_o4.py
    py -3.11 scripts/sweep_o4.py --record
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep_o2 as o2  # noqa: E402  - Chain / Cfg / run_cells / record, imported and unmodified

ROOT = Path(__file__).resolve().parent.parent

TARGETS = (0.05, 0.10, 0.16, 0.25, 0.35)
WIDTHS = (0.003, 0.0075, 0.015)
ENTRIES = ("10:00", "14:00")
STRUCTURES = ("put", "call")


def grid() -> list[o2.Cfg]:
    return [o2.Cfg(structure=s, target=t, width_pct=w, entry=e, exit="15:50", fee=0.75)
            for s in STRUCTURES for t in TARGETS for w in WIDTHS for e in ENTRIES]


def _t(x: np.ndarray) -> float:
    n = len(x)
    sd = x.std(ddof=1) if n > 1 else 0.0
    return float(x.mean() / (sd / np.sqrt(n))) if n > 1 and sd > 0 else float("nan")


def estimators(df: pd.DataFrame) -> pd.DataFrame:
    """Per-session return on risk under both estimators, plus the term the fallback cannot see."""
    out = df[["date"]].copy()
    out["quote"] = df.pnl / df.risk
    out["print"] = (df.pnl_gross - df.fees) / df.risk
    out["blind"] = df.spread_cost / df.risk
    return out


def verdict(e: pd.DataFrame, col: str) -> tuple[int, float, float]:
    """O-2's rule: how many of the three regimes have mean > 0 at t > 2, plus the pooled stats."""
    passes = 0
    for _, s, f in o2.REGIMES:
        sub = e[(e.date >= s) & (e.date <= f)][col].to_numpy()
        if len(sub) > 1 and sub.mean() > 0 and _t(sub) > 2:
            passes += 1
    a = e[col].to_numpy()
    return passes, 100 * float(a.mean()), _t(a)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC ledger rows")
    ap.add_argument("--limit", type=int, default=0, help="first N stored sessions (smoke test)")
    args = ap.parse_args()

    import odte_data
    dates = odte_data.stored_dates("SPY")
    if args.limit:
        dates = dates[:args.limit]
    cfgs = grid()
    print(f"O-4: {len(cfgs)} cells x {len(dates)} stored sessions, one pass over the store.")
    frames = o2.run_cells(cfgs, "SPY", dates, progress=250)

    rows = []
    for cfg, df in zip(cfgs, frames):
        if df.empty or len(df) < 100:
            continue
        e = estimators(df)
        pq, mq, tq = verdict(e, "quote")
        pp, mp, tp = verdict(e, "print")
        rows.append({"structure": cfg.structure, "target": cfg.target, "width": cfg.width_pct,
                     "entry": cfg.entry, "n": len(e),
                     "quote%": mq, "t_q": tq, "reg_q": pq,
                     "print%": mp, "t_p": tp, "reg_p": pp,
                     "blind%": 100 * float(e["blind"].mean()),
                     "sd_quote%": 100 * float(e["quote"].std(ddof=1)),
                     "sign_flip": int(mp > 0 >= mq),
                     "decision_flip": int(pp >= 2 and pq < 2),
                     "false_neg": int(pq >= 2 and pp < 2)})
    g = pd.DataFrame(rows)

    print()
    print("=" * 118)
    print("THE GRID - the same 60 trades priced two ways. 'quote%' is the truth, 'print%' is what")
    print("a trade-print dataset would report. 'reg_*' counts regimes passing O-2's rule (need 2).")
    print("=" * 118)
    print(o2.fmt(g.sort_values("print%", ascending=False)))

    n = len(g)
    sf, dfl, fn = int(g.sign_flip.sum()), int(g.decision_flip.sum()), int(g.false_neg.sum())
    print()
    print("=" * 118)
    print("PRE-REGISTERED STATISTICS")
    print("=" * 118)
    print(f"cells evaluated                                  {n}")
    print(f"1. SIGN FLIP      print > 0 >= quote             {sf}  ({100 * sf / max(n, 1):.1f}% of the grid)")
    print(f"2. DECISION FLIP  passes on print, fails on quote {dfl}  <- the headline")
    print(f"3. FALSE NEGATIVE passes on quote, fails on print {fn}")
    print(f"4. BLIND TERM     spread_cost / risk, points of maximum loss:")
    print(f"                  mean {g['blind%'].mean():.3f}  min {g['blind%'].min():.3f} "
          f"max {g['blind%'].max():.3f}")
    print(f"                  as a multiple of the per-session sd of NET_QUOTE: "
          f"{(g['blind%'] / g['sd_quote%']).mean():.3f} mean")
    print(f"                  mean |quote% - print%| = {(g['quote%'] - g['print%']).abs().mean():.3f} "
          f"points, and the gap is the blind term by construction "
          f"(max |diff| {(g['blind%'] - (g['print%'] - g['quote%'])).abs().max():.2e})")
    best_p = g.loc[g["print%"].idxmax()]
    print()
    print("The cell a trade-print study would have chosen, and what it really is:")
    print(f"  {best_p.structure} {best_p.target:.2f} width {best_p.width:.4f} entry {best_p.entry}: "
          f"print {best_p['print%']:+.3f}% (t {best_p.t_p:+.2f}, {int(best_p.reg_p)}/3 regimes) "
          f"-> quote {best_p['quote%']:+.3f}% (t {best_p.t_q:+.2f}, {int(best_p.reg_q)}/3 regimes)")

    # ---------------------------------------------------------------- post-hoc, and labelled so
    # The pre-registered statistic (2) only catches a fallback that invents a *pass*. On this grid
    # nothing passes under either estimator - no cell reaches t > +2 either way - so statistic (2)
    # is identically zero whatever the fallback does, and it has no power. The direction that does
    # have power is the opposite one, and it is the one this track actually needs, because every
    # O-item so far has ended in a refusal: can the fallback still REFUSE a bad trade?
    dec = g[g.t_q < -2]
    lost = int((dec.t_p > -2).sum())
    pos = int((dec["print%"] > 0).sum())
    print()
    print("=" * 118)
    print("POST-HOC (declared post-hoc; statistic (2) above has no power on this grid)")
    print("=" * 118)
    print(f"cells reaching t > +2 under quote {int((g.t_q > 2).sum())}, under print "
          f"{int((g.t_p > 2).sum())} - so statistic (2) is 0 by degeneracy, not by accuracy.")
    print(f"cells DECISIVELY REFUSED on quotes (t < -2)          {len(dec)} of {n}")
    print(f"  of those, no longer refused on prints (t > -2)     {lost}  "
          f"({100 * lost / max(len(dec), 1):.0f}% of the refusals lost)")
    print(f"  of those, prints report a positive mean            {pos}")
    print(f"bias / effect: mean blind term {g['blind%'].mean():.3f} points against mean |print%| "
          f"{g['print%'].abs().mean():.3f} = {g['blind%'].mean() / g['print%'].abs().mean():.2f}x")
    print(f"rank distortion: Spearman(quote%, print%) = "
          f"{g['quote%'].corr(g['print%'], method='spearman'):.3f}")

    print()
    print("=" * 118)
    print("VERDICT")
    print("=" * 118)
    if dfl >= 1:
        print(f"DISQUALIFIED. {dfl} of {n} cells pass O-2's own two-of-three-regimes rule on "
              f"trade-print data and fail it on quotes.")
    elif lost >= 1:
        print(f"DISQUALIFIED, on the post-hoc direction. The pre-registered rule returns "
              f"'usable' only because nothing passes under either estimator.")
        print(f"What the fallback destroys is the refusal: {lost} of {len(dec)} decisive "
              f"refusals stop being decisive, and {pos} turn positive.")
        print("The term it cannot see is a one-directional bias "
              f"{g['blind%'].mean() / g['print%'].abs().mean():.1f}x the size of the effect being "
              "measured, so it cannot be averaged away.")
        print("This track exists to refuse trades. A feed that cannot refuse is not a fallback.")
    else:
        print("USABLE. No cell's decision changes in either direction.")
    print()
    print("Note on generosity: NET_PRINT prices every fill at the mid. Real prints sit nearer the")
    print("far touch on a marketable order, so an honest Alpaca backtest is at least this wrong.")

    out = ROOT / "results" / "options" / "o4_feed_grid.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    g.to_csv(out, index=False)
    print(f"\ngrid written to {out}")

    if args.record:
        for cfg, df in zip(cfgs, frames):
            if df.empty or len(df) < 100:
                continue
            e = estimators(df)
            pq, mq, tq = verdict(e, "quote")
            pp, mp, tp = verdict(e, "print")
            o2.record("odte_o4_feed",
                      f"DIAGNOSTIC O-4 {cfg.structure} {cfg.target:.2f} w{cfg.width_pct} "
                      f"{cfg.entry}: quote {mq:+.3f}% t{tq:+.2f} {pq}/3 vs print {mp:+.3f}% "
                      f"t{tp:+.2f} {pp}/3 [quote-priced row]",
                      df, cfg)
        print(f"\nrecorded {len(g)} DIAGNOSTIC rows under options/odte_o4_feed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
