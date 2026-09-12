#!/usr/bin/env python
"""C-1: the critic's attempt to refute S-31's margin-budget re-pricing.

    py -3.11 scripts/verify_s31.py            # the whole attack, ~12 harness runs
    py -3.11 scripts/verify_s31.py --quick    # budgets 0.75 / 1.00 only

S-31 (commit 9197bd4) makes three claims that feed the owner's open `margin_budget`
decision in `BLOCKERS.md`, and this script tries to break each of them with arithmetic
this file owns rather than with the arithmetic S-31 used:

  (i)  IDENTITY - budget 0.75 fully charged earns 19.640%, the figure S-22/S-26/S-28/S-30
       quote. Re-run here and compared to six decimal places.
  (ii) "ABOUT HALF THE ADVERTISED GAIN IS NOT THERE" - the gain over 0.75 shrinks by
       ~53% between cell A (what the owner was shown) and cell D (charged).
  (iii)"THE SHARPE ARGUMENT REVERSES" - the headline. Raw Sharpe falls with the budget
       once spread and financing are charged, and S-31 argues the rise LEAN reports is a
       risk-free-rate convention artifact.

Three attacks, all pre-registered here before the numbers were read:

  ATTACK 1 - SIGNIFICANCE OF THE REVERSAL. S-31 deflated its own CAR t-stat ("the
       significance of arithmetic") but quoted the Sharpe reversal with no error bar at
       all. A budget change is a near-scalar multiple of one book, so the two Sharpes are
       enormously correlated and the right test is Jobson-Korkie with Memmel's
       correction, not two independent standard errors. If |t| on the DIFFERENCE is below
       2, the headline is a point estimate pointing the right way, not an established
       reversal, and the journal should say so.

  ATTACK 2 - THE RISK-FREE PATH. S-31 rebuts the convention objection with a SINGLE
       constant rate (the sample's mean effective fed funds, 1.6924%). That is the one
       choice guaranteed to be wrong in both regimes: rates were ~0.1% to 2021 and 4-5%
       from 2023, and the book's leverage is not constant across those regimes either. The
       honest version subtracts the ACTUAL DAILY rf path. If cell A's excess Sharpe stops
       rising, S-31's rebuttal collapses and with it the claim that the rise was an
       artifact.

  ATTACK 3 - IS IT ONE BOOK SCALED? Clause 6 solves for a budget under a drawdown, which
       is only meaningful if the budget dial sizes the book rather than changing it.
       S-31 verifies that at 0.75 alone (clause 1) and then asserts it at every other
       budget. Here: the correlation and the regression slope of each budget's daily
       return on the shipped book's, plus the Reg-T ceiling on the harness's own peak
       gross, checked against the initial margin LEAN reports in its own run log.

  ATTACK 4 - THE INVERSE SOLVE, WHICH IS THE ONLY CLAUSE THAT RECOMMENDS AN ACTION.
       Clause 7 (BLOCKERS.md "Option (c) answered in advance") answers a named drawdown
       with a budget, and its 25% row says 0.70 - BELOW the shipped 0.75 - on the stated
       ground that "the shipped 0.75 book's own drawdown is 25.2%". S-31's own stated
       correction rule is "the harness is optimistic on drawdown by 0.44 / 1.14 / 1.29
       points at 0.75 / 0.80 / 0.90 and that error is added back". 24.037 + 0.44 is 24.48,
       not 25.2. This attack re-solves the table under three SELF-CONSISTENT error rules -
       measured-at-the-budget, worst-case-uniform, and S-31's own published per-budget
       numbers - and reports whether the recommendation survives any of them. Budgets 0.70
       and 0.78 are added because the answer can land between the gaps in S-31's grid.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                       # noqa: E402
import rates                                # noqa: E402
from lean_prices import load_ohlcv          # noqa: E402
from sweep_s25 import legs_simulate         # noqa: E402
from sweep_s19 import simulate              # noqa: E402

START, END = "2012-01-03", "2026-09-04"
BUDGETS = (0.70, 0.75, 0.78, 0.80, 0.90, 1.00)
SPREAD_BPS = 2.0

#: S-31's published cells, the numbers this script is trying to break
S31 = {
    "identity_costed_CAR": 19.640168,
    "A": {0.70: 22.578, 0.75: 24.077, 0.78: 24.954, 0.80: 25.531, 0.90: 28.377,
          1.00: 31.129},
    "C": {0.70: 18.663, 0.75: 19.640, 0.78: 20.198, 0.80: 20.533, 0.90: 22.212,
          1.00: 23.818},
    "D": {0.70: 18.311, 0.75: 19.102, 0.78: 19.530, 0.80: 19.780, 0.90: 21.093,
          1.00: 22.288},
    #: S-31's cell-C drawdown column, the input to the clause-7 solve
    "dd_C": {0.70: 23.728, 0.75: 24.037, 0.78: 24.272, 0.80: 24.475, 0.90: 25.027,
             1.00: 27.653},
    #: the per-budget drawdown error S-31 PUBLISHES and says it adds back
    "dd_err_published": {0.75: 0.442, 0.80: 1.135, 0.90: 1.294},
    #: clause 7 / BLOCKERS.md "option (c) answered in advance"
    "solve": {25.0: 0.70, 30.0: 0.90, 35.0: 0.90},
    "solve_premise_dd_at_075": 25.2,
    "sharpe_C": {0.75: 1.047, 0.80: 1.036, 0.90: 1.016, 1.00: 1.003},
    "sharpe_D": {0.75: 1.023, 0.80: 1.004, 0.90: 0.975, 1.00: 0.952},
    "excess_A_mean_rate": {0.75: 1.156, 1.00: 1.176},
    "excess_C_mean_rate": {0.75: 0.957, 1.00: 0.933},
    "gross_max": {0.90: 1.88, 1.00: 2.12},
}
#: LEAN rows on file. 0.90 is the run S-31 added for its clause 2.
LEAN = {0.75: (24.403, 23.700, 0.994, "20260911T145705Z"),
        0.80: (25.903, 25.100, 1.008, "S-16"),
        0.90: (28.796, 27.900, 1.032, "20260912T130734Z")}


# ------------------------------------------------------------------ metrics, owned here

def metrics(book: pd.DataFrame) -> dict:
    """Deliberately NOT sweep_s19.summarize - the critic recomputes from the returns."""
    r = book["ret"].to_numpy()
    n = len(r)
    curve = np.cumprod(1.0 + r)
    sd = r.std(ddof=1)
    return {"n": n,
            "CAR": 100.0 * (curve[-1] ** (252.0 / n) - 1.0),
            "Sharpe": float(r.mean() / sd * np.sqrt(252.0)),
            "MaxDD": 100.0 * float((1.0 - curve / np.maximum.accumulate(curve)).max()),
            "std": float(sd * np.sqrt(252.0)),
            "orders": int(book["orders"].sum()),
            # `sweep_s19.simulate` (cell A) carries no `gross_x`; the exposure the Reg-T
            # clause reads is derived from the book's own cash instead, which is the same
            # quantity one session later and is the one the broker margins.
            "gross_mean": float(book["gross_x"].mean()) if "gross_x" in book
            else float(((book["equity"] - book["cash"]) / book["equity"]).mean())
            if "cash" in book else float("nan"),
            "gross_max": float(book["gross_x"].max()) if "gross_x" in book
            else float(((book["equity"] - book["cash"]) / book["equity"]).max())
            if "cash" in book else float("nan"),
            "mv_mean": float(((book["equity"] - book["cash"]) / book["equity"]).mean())
            if "cash" in book else float("nan"),
            "mv_max": float(((book["equity"] - book["cash"]) / book["equity"]).max())
            if "cash" in book else float("nan")}


def sharpe_excess(book: pd.DataFrame, rf_daily: np.ndarray) -> float:
    """Annualised Sharpe of the excess return, rf subtracted DAY BY DAY (attack 2)."""
    x = book["ret"].to_numpy() - rf_daily
    return float(x.mean() / x.std(ddof=1) * np.sqrt(252.0))


def sharpe_excess_const(book: pd.DataFrame, rate_pct: float) -> float:
    """S-31's version: one constant rate over the whole sample."""
    x = book["ret"].to_numpy() - (rate_pct / 100.0) / 252.0
    return float(x.mean() / x.std(ddof=1) * np.sqrt(252.0))


def jkm(a: np.ndarray, b: np.ndarray) -> dict:
    """Jobson-Korkie test of S(a) == S(b) with Memmel's correction, paired daily returns.

    var(d) = (1/n) [ 2(1-rho) + 0.5(Sa^2 + Sb^2 - 2 Sa Sb rho^2) ]  on DAILY Sharpes.
    """
    n = len(a)
    sa, sb = a.mean() / a.std(ddof=1), b.mean() / b.std(ddof=1)
    rho = float(np.corrcoef(a, b)[0, 1])
    var = (2.0 * (1.0 - rho) + 0.5 * (sa ** 2 + sb ** 2 - 2.0 * sa * sb * rho ** 2)) / n
    d = sa - sb
    return {"dS_daily": d, "dS_ann": d * np.sqrt(252.0), "rho": rho,
            "se_ann": np.sqrt(var) * np.sqrt(252.0),
            "t": d / np.sqrt(var) if var > 0 else float("nan")}


def rf_path(book: pd.DataFrame, rate_map: dict) -> np.ndarray:
    """Actual daily risk-free accrual over each session's own calendar gap, actual/360."""
    dates = pd.to_datetime(book["date"]).dt.date.to_numpy()
    first, final = min(rate_map), max(rate_map)
    out = np.zeros(len(dates))
    for i, d in enumerate(dates):
        days = 1 if i == 0 else (d - dates[i - 1]).days
        stamp = min(max(d.isoformat(), first), final)
        out[i] = rate_map[stamp] / 100.0 * days / 360.0
    return out


# ------------------------------------------------------------------------------- the run

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    budgets = (0.75, 1.00) if args.quick else BUDGETS

    p = sig.Params()
    frames = load_ohlcv(sig.traded_universe(p))
    rate_map = rates.load()
    fin_hist = {"rates": rate_map, "spread": 0.0}
    fin_today = {"rates": rates.load(REPO / "data" / "rates" / "usd_flat_2026.csv"),
                 "spread": 0.0}

    books: dict[tuple[str, float], pd.DataFrame] = {}
    rows: list[dict] = []
    t0 = time.time()
    for b in budgets:
        par = replace(p, margin_budget=b)
        cells = {
            "A": lambda: simulate(frames, par, 0, "open", START, END, 0.0, None),
            "C": lambda: legs_simulate(frames, par, "both", START, END, SPREAD_BPS, fin_hist),
            "D": lambda: legs_simulate(frames, par, "both", START, END, SPREAD_BPS, fin_today),
        }
        for cell, fn in cells.items():
            bk = fn()
            books[(cell, b)] = bk
            m = metrics(bk)
            m["cell"], m["budget"] = cell, b
            rows.append(m)
            print(f"  [{time.time()-t0:6.0f}s] {cell} {b:.2f}  CAR {m['CAR']:8.3f}  "
                  f"Sharpe {m['Sharpe']:.3f}  DD {m['MaxDD']:7.3f}  "
                  f"gross max {m['gross_max']:.3f}  orders {m['orders']:,}", flush=True)

    def cell(c, b): return next(r for r in rows if r["cell"] == c and r["budget"] == b)

    # ---------------------------------------------------------------- claim (i) identity
    print("\n=== claim (i): the identity S-31 stops on if it fails ===")
    got = cell("C", 0.75)["CAR"]
    print(f"  critic recompute  CAR {got:.6f}%     S-31 {S31['identity_costed_CAR']:.6f}%"
          f"     diff {got - S31['identity_costed_CAR']:+.6f}")
    print(f"  -> {'REPRODUCED' if abs(got - S31['identity_costed_CAR']) < 5e-4 else 'FAILED'}")

    # ------------------------------------------------------- claim (ii) the gain haircut
    print("\n=== claim (ii): 'about half the advertised gain is not there' ===")
    hdr = (f"{'budget':>7}{'A CAR':>10}{'C CAR':>10}{'D CAR':>10}{'A gain':>9}{'C gain':>9}"
           f"{'D gain':>9}{'survives':>10}{'S-31 said':>11}")
    print(hdr); print("-" * len(hdr))
    for b in budgets:
        if b == 0.75:
            continue
        ga = cell("A", b)["CAR"] - cell("A", 0.75)["CAR"]
        gc = cell("C", b)["CAR"] - cell("C", 0.75)["CAR"]
        gd = cell("D", b)["CAR"] - cell("D", 0.75)["CAR"]
        shown = S31["A"][b] - S31["A"][0.75]
        s31_got = S31["D"][b] - S31["D"][0.75]
        print(f"{b:>7.2f}{cell('A', b)['CAR']:>10.3f}{cell('C', b)['CAR']:>10.3f}"
              f"{cell('D', b)['CAR']:>10.3f}{ga:>+9.3f}{gc:>+9.3f}{gd:>+9.3f}"
              f"{100 * gd / ga:>9.0f}%{100 * s31_got / shown:>10.0f}%")

    # --------------------------------------------- claim (iii) + attack 1: significance
    print("\n=== attack 1: is the Sharpe reversal distinguishable from zero? ===")
    print("  Jobson-Korkie / Memmel on the paired daily returns, against the shipped 0.75\n")
    hdr = (f"{'cell':>5}{'budget':>8}{'Sharpe':>9}{'vs 0.75':>10}{'rho':>9}{'se':>9}"
           f"{'t':>8}{'verdict':>12}")
    print(hdr); print("-" * len(hdr))
    for c in ("A", "C", "D"):
        for b in budgets:
            if b == 0.75:
                continue
            a = books[(c, b)]["ret"].to_numpy()
            z = books[(c, 0.75)]["ret"].to_numpy()
            k = jkm(a, z)
            v = "significant" if abs(k["t"]) >= 2.0 else "NOT at |t|=2"
            print(f"{c:>5}{b:>8.2f}{cell(c, b)['Sharpe']:>9.3f}{k['dS_ann']:>+10.3f}"
                  f"{k['rho']:>9.5f}{k['se_ann']:>9.3f}{k['t']:>+8.2f}{v:>12}")

    # ------------------------------------------------ attack 2: the risk-free rate path
    print("\n=== attack 2: the excess-return Sharpe on the ACTUAL daily rf path ===")
    print("  S-31 rebuts the convention objection with ONE constant rate. Both are shown.\n")
    rf = rf_path(books[("C", 0.75)], rate_map)
    rf_a = rf_path(books[("A", 0.75)], rate_map)
    # `rates.load()` is already in PERCENT, the same units S-31 quotes (1.6924), so the
    # sample mean is a plain average of the map - no 100x rescale.
    mean_rate = float(np.mean([rate_map[min(max(d.isoformat(), min(rate_map)), max(rate_map))]
                               for d in pd.to_datetime(books[("C", 0.75)]["date"]).dt.date]))
    print(f"  sample mean benchmark rate {mean_rate:.4f}%   (S-31 used 1.6924%)\n")
    hdr = (f"{'cell':>5}{'budget':>8}{'raw':>9}{'excess @ const':>16}{'excess @ daily rf':>19}")
    print(hdr); print("-" * len(hdr))
    for c in ("A", "C", "D"):
        for b in budgets:
            bk = books[(c, b)]
            path = rf_a if c == "A" else rf
            path = path[:len(bk)] if len(path) >= len(bk) else rf_path(bk, rate_map)
            print(f"{c:>5}{b:>8.2f}{metrics(bk)['Sharpe']:>9.3f}"
                  f"{sharpe_excess_const(bk, mean_rate):>16.3f}"
                  f"{sharpe_excess(bk, path):>19.3f}")

    # --------------------------------------- attack 3: is the dial a scale, and Reg-T
    print("\n=== attack 3: does the budget dial SIZE the book or CHANGE it? ===")
    hdr = (f"{'cell':>5}{'budget':>8}{'corr vs 0.75':>14}{'OLS slope':>11}{'R2':>8}"
           f"{'gross mean':>12}{'gross max':>11}{'Reg-T':>8}")
    print(hdr); print("-" * len(hdr))
    for c in ("A", "C", "D"):
        for b in budgets:
            a = books[(c, b)]["ret"].to_numpy()
            z = books[(c, 0.75)]["ret"].to_numpy()
            rho = float(np.corrcoef(a, z)[0, 1])
            slope = float(np.cov(a, z, ddof=1)[0, 1] / z.var(ddof=1))
            m = cell(c, b)
            peak = max(m["gross_max"], m["mv_max"])
            print(f"{c:>5}{b:>8.2f}{rho:>14.5f}{slope:>11.4f}{rho ** 2:>8.4f}"
                  f"{m['gross_mean']:>12.3f}{peak:>11.3f}"
                  f"{('OVER' if peak > 2.0 else 'ok'):>8}")

    # ------------------------------------------------ attack 4: clause 7's inverse solve
    print("\n=== attack 4: the inverse solve, the only clause that recommends an action ===")
    pub = S31["dd_err_published"]
    meas = {b: cell("A", b)["MaxDD"] - LEAN[b][1] for b in LEAN}      # negative = optimistic
    print("  drawdown error re-measured here (harness A minus LEAN), and as published:")
    for b in sorted(LEAN):
        print(f"    budget {b:.2f}   critic {meas[b]:+.3f}   S-31 published -{pub[b]:.3f}")

    def err_measured(b: float) -> float:
        """Rule M: the error measured AT that budget; linear in the gaps, flat outside."""
        xs = sorted(pub)
        if b <= xs[0]:
            return pub[xs[0]]
        if b >= xs[-1]:
            return pub[xs[-1]]
        return float(np.interp(b, xs, [pub[x] for x in xs]))

    rules = {
        "M measured-at-budget": err_measured,
        "W worst-case uniform": lambda b: max(pub.values()),
        "Z no adjustment": lambda b: 0.0,
    }
    print("\n  cell-C drawdown, raw and adjusted under each self-consistent rule:\n")
    hdr = (f"{'budget':>7}{'C DD raw':>10}{'S-31 raw':>10}" +
           "".join(f"{k.split()[0]+' adj':>10}" for k in rules) + f"{'C CAR':>9}{'D CAR':>9}")
    print(hdr); print("-" * len(hdr))
    for b in budgets:
        raw = cell("C", b)["MaxDD"]
        line = f"{b:>7.2f}{raw:>10.3f}{S31['dd_C'].get(b, float('nan')):>10.3f}"
        for fn in rules.values():
            line += f"{raw + fn(b):>10.3f}"
        print(line + f"{cell('C', b)['CAR']:>9.3f}{cell('D', b)['CAR']:>9.3f}")

    print(f"\n  S-31's stated premise for the 25% row: 0.75's own drawdown is "
          f"{S31['solve_premise_dd_at_075']:.1f}%")
    print(f"  under rule M it is {cell('C', 0.75)['MaxDD'] + err_measured(0.75):.2f}% "
          f"-> the premise is {'CONFIRMED' if cell('C', 0.75)['MaxDD'] + err_measured(0.75) > 25.0 else 'REFUTED'}")
    print("\n  re-solve: the LARGEST budget whose adjusted drawdown fits the named cap\n")
    hdr = f"{'cap':>6}{'S-31 says':>11}" + "".join(f"{k.split()[0]:>22}" for k in rules)
    print(hdr); print("-" * len(hdr))
    for cap in (25.0, 30.0, 35.0):
        line = f"{cap:>5.0f}%{S31['solve'][cap]:>11.2f}"
        for fn in rules.values():
            ok = [b for b in budgets if cell("C", b)["MaxDD"] + fn(b) <= cap
                  and max(cell("C", b)["gross_max"], cell("C", b)["mv_max"]) <= 2.0]
            if not ok:
                line += f"{'none in grid':>22}"
            else:
                best = max(ok)
                d = cell("D", best)["CAR"] - cell("D", 0.75)["CAR"]
                line += f"{f'{best:.2f}  ({d:+.2f} CAR)':>22}"
        print(line)

    print("\n=== LEAN calibration, re-scored ===")
    hdr = f"{'budget':>7}{'LEAN CAR':>10}{'crit A CAR':>12}{'LEAN DD':>9}{'crit A DD':>11}{'DD err':>9}"
    print(hdr); print("-" * len(hdr))
    for b in budgets:
        if b not in LEAN:
            continue
        lc, ld, _, src = LEAN[b]
        m = cell("A", b)
        print(f"{b:>7.2f}{lc:>10.3f}{m['CAR']:>12.3f}{ld:>9.3f}{m['MaxDD']:>11.3f}"
              f"{m['MaxDD'] - ld:>+9.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
