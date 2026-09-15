"""Sections 3-5: does overnight INFORMATION predict the regular session?

THE DISTINCTION THIS WHOLE FILE RESTS ON
----------------------------------------
Holding the overnight session is beta - `overnight_confound.py` settles that. But the brief
asks a different and much better question: not whether to HOLD overnight, but whether what
happens overnight tells you something about the session you are allowed to trade.

That is a question about conditional means, and it has a property the drift question does
not: it can be true even when the unconditional drift is zero. A signal that says "go long
on these days and short on those" earns nothing from drift and everything from the
conditioning. It is also the only version that fits a Combine, because the position opens
after 09:30 and closes before 16:10 ET, so the overnight session is an input rather than an
exposure.

TEN HYPOTHESES, AND WHY THEY ARE PREREGISTERED HERE IN CODE
------------------------------------------------------------
The list below is fixed before any of it runs, and the count is what sets the multiplicity
bar. Ten hypotheses x up to four instruments is up to forty tests, so the Bonferroni
threshold is 0.05/40 and a t of 2.0 means nothing. Writing them down in the module rather
than choosing them as results arrive is the only thing that makes that denominator honest.

Each is stated as a signed prediction, so that a result of the opposite sign is a failure and
not a discovery. This matters more than it sounds: with ten two-sided tests, "something was
significant" is nearly guaranteed, and the sign is what separates a mechanism from a coincidence.

WHERE EACH ONE CAN BE TESTED
----------------------------
The futures store holds the overnight PATH - range, volume, where it closed inside its range,
how much of the move was retraced. That is 312 sessions and a minimum detectable correlation
of 0.111, which is a weak instrument.

The ETF store holds ten years but only RTH bars, so the only overnight fact it knows is the
close-to-open return. Minimum detectable correlation 0.038.

So the hypotheses split into those that can be asked of 2,662 sessions and those that can only
be asked of 312, and that split is reported rather than hidden - a null on 312 sessions is
mostly a statement about the sample size.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))


@dataclass(frozen=True)
class H:
    """A preregistered, signed prediction."""

    key: str
    title: str
    x: str
    y: str
    #: +1 predicts continuation (positive slope), -1 predicts reversal.
    sign: int
    mechanism: str
    #: "both" if the ten-year ETF panel can answer it, "futures" if it needs the overnight path.
    where: str


HYPOTHESES: tuple[H, ...] = (
    H("A", "Overnight return continues into the regular session",
      "on_ret_pct", "rth_ret_pct", +1,
      "Information arriving while the US is closed is only partially impounded by 09:30, so "
      "the remainder bleeds into the day session.", "both"),
    H("B", "Overnight return reverses during the regular session",
      "on_ret_pct", "rth_ret_pct", -1,
      "Overnight books are thin; a move made on low liquidity is an inventory imbalance "
      "rather than information, and US liquidity corrects it. This is the direct negation "
      "of A and the two cannot both be right.", "both"),
    H("C", "Overnight range predicts regular-session range",
      "on_range_pct", "rth_range_pct", +1,
      "Volatility is persistent at every horizon ever measured. Not a return prediction - "
      "included because a range forecast sizes a position even when it cannot direct one.",
      "futures"),
    H("D", "Where the overnight session closed inside its range predicts the first 30 minutes",
      "on_close_loc", "r30_pct", +1,
      "Closing on the high means buyers were still paying up at 09:29; the imbalance does not "
      "vanish at the bell.", "futures"),
    H("E", "The opening gap fills",
      "gap_pct", "rth_ret_pct", -1,
      "The classic retail claim, and the one most likely to be folklore. A gap is a price "
      "struck in the auction; calling it an error requires believing the auction is wrong.",
      "both"),
    H("F", "A one-way overnight session predicts a trending regular session",
      "on_persistence", "rth_abs_ret_pct", +1,
      "Persistence overnight is a proxy for a single dominant flow, which does not usually "
      "finish in one session.", "futures"),
    H("G", "Heavy overnight volume predicts a large regular-session range",
      "on_volume_z", "rth_range_pct", +1,
      "Volume overnight means the news was real rather than a drift on no participation.",
      "futures"),
    H("H", "A large overnight excursion reverses",
      "on_excursion_pct", "rth_ret_pct", -1,
      "Signed by the excursion's direction: an overextended overnight move mean-reverts once "
      "size can trade against it.", "futures"),
    H("I", "Opening outside the overnight range continues in that direction",
      "open_break_pct", "r60_pct", +1,
      "An open beyond the overnight extreme is a breakout with the whole US session left to "
      "run.", "futures"),
    H("J", "Nasdaq's overnight move predicts the S&P's regular session",
      "cross_on_pct", "rth_ret_pct", +1,
      "NQ is the higher-beta expression of the same risk factor and is where overnight "
      "positioning concentrates, so it should lead.", "futures"),
)


def fisher_ci(r: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Confidence interval for a correlation, via the variance-stabilising transform."""
    if n < 4 or not np.isfinite(r) or abs(r) >= 1:
        return (np.nan, np.nan)
    zr = np.arctanh(r)
    se = 1.0 / np.sqrt(n - 3)
    return float(np.tanh(zr - z * se)), float(np.tanh(zr + z * se))


def test_one(x: np.ndarray, y: np.ndarray, sign: int) -> dict:
    """Correlation, its t, and the SIGNED verdict.

    Spearman as well as Pearson because a handful of crisis sessions can manufacture or
    destroy a Pearson correlation on their own, and a mechanism that only exists on the four
    biggest days of the sample is not a mechanism.
    """
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = len(x)
    if n < 30:
        return {"n": n, "r": np.nan, "t": np.nan, "rho": np.nan, "lo": np.nan, "hi": np.nan,
                "signed_ok": False}
    r = float(np.corrcoef(x, y)[0, 1])
    rho = float(np.corrcoef(pd.Series(x).rank(), pd.Series(y).rank())[0, 1])
    t = r * np.sqrt((n - 2) / max(1e-12, 1 - r ** 2))
    lo, hi = fisher_ci(r, n)
    return {"n": n, "r": r, "t": float(t), "rho": rho, "lo": lo, "hi": hi,
            "signed_ok": bool(np.sign(r) == sign)}


def futures_features(fut: pd.DataFrame) -> pd.DataFrame:
    """Derive the normalised regressors. Everything is a percentage or a unit-free ratio.

    Raw points are never used as a regressor or a target: NQ moves five times as many points
    as ES for the same economic event, so a points-based correlation pooled across
    instruments measures the contract specification.
    """
    f = fut.copy()
    px = f["rth_open"]
    f["rth_range_pct"] = f["rth_range_pts"] / px * 100.0
    f["rth_abs_ret_pct"] = f["rth_ret_pct"].abs()
    for c in ("r5", "r15", "r30", "r60"):
        f[f"{c}_pct"] = f[f"{c}_pts"] / px * 100.0
    # Excursion signed by which side it happened on: positive if the overnight high was the
    # farther extreme, so a positive value means "extended upward".
    up = f["on_high"] - (f["rth_open"] - f["gap_pts"])
    dn = (f["rth_open"] - f["gap_pts"]) - f["on_low"]
    f["on_excursion_pct"] = np.where(up >= dn, up, -dn) / px * 100.0
    # How far outside the overnight range the session opened. Zero when it opened inside.
    f["open_break_pct"] = np.where(
        f["rth_open"] > f["on_high"], (f["rth_open"] - f["on_high"]),
        np.where(f["rth_open"] < f["on_low"], (f["rth_open"] - f["on_low"]), 0.0)) / px * 100.0
    # Volume standardised WITHIN instrument, using an expanding window so that no future
    # volume enters the score for any given date.
    f = f.sort_values(["symbol", "tdate"])
    g = f.groupby("symbol")["on_volume"]
    f["on_volume_z"] = ((f["on_volume"] - g.transform(lambda s: s.expanding(30).mean()))
                        / g.transform(lambda s: s.expanding(30).std()))
    # The cross-market regressor: the Nasdaq contract's overnight return, aligned by date.
    nq = (f[f.symbol.isin(["NQ"])].set_index("tdate")["on_ret_pct"]
          .rename("cross_on_pct"))
    f = f.merge(nq, left_on="tdate", right_index=True, how="left")
    return f


def etf_features(etf: pd.DataFrame) -> pd.DataFrame:
    """The ten-year panel. Its only overnight fact is the close-to-open return, which for an
    ETF is simultaneously the overnight return AND the gap - there is no 18:00 reference
    price - so hypotheses A, B and E all read from the same column here."""
    e = etf.copy()
    e["gap_pct"] = e["on_ret_pct"]
    return e


def main() -> int:
    fut = futures_features(pd.read_parquet(REPO / "research" / "overnight_panel.parquet"))
    etf = etf_features(pd.read_parquet(REPO / "research" / "etf_overnight_panel.parquet"))

    rows = []
    for h in HYPOTHESES:
        panels = [("ETF 10y", etf)] if h.where == "both" else []
        panels.append(("futures", fut))
        for pname, panel in panels:
            if h.x not in panel.columns or h.y not in panel.columns:
                continue
            for sym, g in panel.groupby("symbol"):
                res = test_one(g[h.x].to_numpy(dtype=float),
                               g[h.y].to_numpy(dtype=float), h.sign)
                rows.append({"h": h.key, "title": h.title, "panel": pname, "sym": sym,
                             "pred_sign": h.sign, **res})
    out = pd.DataFrame(rows)
    n_tests = len(out)
    # Bonferroni over every test this module runs, which is the honest family: they were all
    # preregistered together and all run together.
    t_bonf = float(abs(np.round(
        __import__("math").sqrt(2) * _erfinv(1 - 0.05 / n_tests), 4)))
    out["passes_bonf"] = (out["t"].abs() > t_bonf) & out["signed_ok"]
    out["passes_naive"] = (out["t"].abs() > 1.96) & out["signed_ok"]
    out.to_csv(REPO / "research" / "overnight_hypotheses.csv", index=False)

    print("=" * 96)
    print(f"TEN PREREGISTERED HYPOTHESES, {n_tests} TESTS")
    print(f"Bonferroni threshold for 0.05 family-wise over {n_tests} tests: |t| > {t_bonf:.2f}")
    print("=" * 96)
    cur = None
    for _, r in out.iterrows():
        if r["h"] != cur:
            cur = r["h"]
            hh = next(x for x in HYPOTHESES if x.key == cur)
            print(f"\n{cur}. {hh.title}   [predicts sign {'+' if hh.sign > 0 else '-'}]")
            print(f"   {hh.x} -> {hh.y}")
            print(f"   {'panel':9} {'sym':5} {'n':>5} {'r':>7} {'95% CI':>17} "
                  f"{'rho':>7} {'t':>7}  verdict")
        ci = f"[{r['lo']:+.3f},{r['hi']:+.3f}]"
        v = ("PASSES BONFERRONI" if r["passes_bonf"] else
             "nominal only" if r["passes_naive"] else
             "wrong sign" if np.isfinite(r["r"]) and not r["signed_ok"] else "null")
        print(f"   {r['panel']:9} {r['sym']:5} {r['n']:5d} {r['r']:+7.3f} {ci:>17} "
              f"{r['rho']:+7.3f} {r['t']:+7.2f}  {v}")

    print("\n" + "=" * 96)
    print("SUMMARY")
    print("=" * 96)
    print(f"  tests run                          {n_tests}")
    print(f"  correct sign AND |t|>1.96 (naive)  {int(out['passes_naive'].sum())}")
    print(f"  expected by chance at 0.05         {n_tests * 0.05 / 2:.1f} (one-sided on sign)")
    print(f"  survive Bonferroni                 {int(out['passes_bonf'].sum())}")
    if out["passes_bonf"].any():
        print("\n  survivors:")
        for _, r in out[out["passes_bonf"]].iterrows():
            print(f"    {r['h']} {r['panel']:9} {r['sym']:5} r={r['r']:+.3f} t={r['t']:+.2f}")
    return 0


def _erfinv(y: float) -> float:
    """Inverse error function. Written out because the LEAN interpreter has no scipy and this
    module must run under both."""
    a = 0.147
    ln = np.log(1 - y * y)
    term = 2 / (np.pi * a) + ln / 2
    return float(np.sign(y) * np.sqrt(np.sqrt(term * term - ln / a) - term))


if __name__ == "__main__":
    raise SystemExit(main())
