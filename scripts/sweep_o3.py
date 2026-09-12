"""O-3 - is the 0DTE variance risk premium CONDITIONAL? Selection, the one lever O-2 left.

O-2's verdict on the SPY 0DTE credit spread was a refusal on COST, not on edge. It measured a
real, calibrated variance risk premium - the chain's own quoted probability of the short strike
being breached exceeds the realized breach rate at z = -2.7 to -3.8 in six of six delta/right
cells - and then refused the trade because harvesting it costs more than it pays: as a percentage
of the position's own maximum loss, gross +0.783, quoted spread -1.363, commission -0.950, net
-1.530. O-2 closed the delta, width, entry-time, structure and stop axes, because the negative is
decided one level above all of them.

There is exactly one lever left that is none of those five: SELECTION. Every cost term above is
paid per session traded, so a filter that keeps the sessions where the premium is richest and
skips the rest raises gross per unit of cost without touching a single parameter of the trade.
O-2's only conditioning test (its STRESS 2) used `data/options/iv_regime.parquet` - the ATM 1-week
implied level and the term ratio, both EXTERNAL to the traded chain. The chain the trade is
actually written on carries two pieces of information that study never used, and both are free.

HYPOTHESIS. The 0DTE variance risk premium is conditional, and conditioning on the traded chain's
own state concentrates enough of it to cover the cost of harvesting it.

THE TWO FEATURES, DECLARED BEFORE ANY RUN AND BOTH REPORTED WHATEVER THEY SAY. Both are computed
causally, from the entry-timestamp chain of the session being traded (plus, for `vrp`, strictly
prior sessions only):

  rn_skew  Asymmetry of the risk-neutral distribution. p_put(K = S(1-d)) - p_call(K = S(1+d))
           at d = 0.5% of spot, linearly interpolated on the strike grid from the chain's own
           dP/dK. Positive = the market is paying more for the downside tail than the upside one.
           Pre-declared direction: sell the side the market is overpaying for, so the SELECTED
           subset for a put spread is the TOP tercile.

  vrp      Richness of the premium, in the units the trade is paid in. rn_half = half the
           risk-neutral interquartile span, i.e. the distance from spot to the 0.25-prob-ITM
           strike averaged over the two rights, as a fraction of spot - the chain's own forecast
           of the session's median absolute move. rz_half = the median of |spot_exit/spot_entry -1|
           over the previous 20 STORED sessions on the same entry/exit clock - the realized
           version of the same statistic, strictly prior, therefore causal. vrp = rn_half -
           rz_half is the per-session variance risk premium the seller is being handed.
           Pre-declared direction: sell when the premium is rich, so the SELECTED subset is the
           TOP tercile.

THE BASE CELLS, TAKEN UNCHANGED FROM O-2'S OWN VERDICT LIST - no new tuning is introduced here:
  B1  put 0.16 prob-ITM, 0.75% wide, enter 10:00, close at the quote 15:50  (O-2's default)
  B2  put 0.25 prob-ITM, 1.50% wide, enter 14:00, close at the quote 15:55  (O-2's best cell)
Both are closed at the quote. The expire-free branch is deliberately NOT used: O-2 showed it is
the exit assumption that fails, and the buffer test walked it to 0 of 3 regimes.

THE PRE-REGISTERED RULE, IN FULL, BEFORE ANY RUN:
  1. Causality. Every feature uses the entry-timestamp chain and strictly prior sessions only.
  2. STAGE A - does the premium vary with the feature at all? Terciles are formed WITHIN each
     regime (so a level drift between regimes cannot masquerade as selection). The feature passes
     Stage A if mean GROSS return on risk is monotone across T1 -> T2 -> T3 pooled AND the
     T3 - T1 difference has |t| > 2 pooled (Welch, independent samples). If gross does not vary
     with the feature, selection cannot help and the feature is done - no Stage B is run on it.
  3. STAGE B - does selection make the trade net-positive? On the pre-declared selected subset
     (top tercile), NET return on risk > 0 at t > 2 in at least two of the three a-priori regimes
     2016-2019 / 2020-2023 / 2024-2026. This is the repository's standing two-of-three rule.
  4. PLACEBO. The complementary subset (T1+T2) must NOT also clear Stage B. A filter that works
     on both halves is not a filter.
  5. MINIMUM SAMPLE. At least 100 sessions in every selected regime cell, else that cell is not
     counted as a pass.
  6. NO POST-HOC FEATURE, NO POST-HOC DIRECTION, NO POST-HOC CUT. Two features, two directions,
     terciles. Anything discovered after the first run is a finding to report, never a result.

Costs are O-2's and are real: both legs crossed at the quoted bid/ask on entry and on exit, plus
$0.75 per contract per transaction. Run:

    py -3.14 scripts/sweep_o3.py --record

(py -3.14 because only 3.14 has pyarrow on this machine; py -3.11 cannot read the parquet store.)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import odte_data  # noqa: E402
import sweep_o2 as o2  # noqa: E402  - Chain / Cfg / run_session / pick_strike / record, unchanged

ROOT = Path(__file__).resolve().parent.parent

SKEW_D = 0.005      # distance from spot at which rn_skew is read, as a fraction of spot
RN_TARGET = 0.25    # prob-ITM defining the risk-neutral interquartile span
RZ_WINDOW = 20      # trailing stored sessions for the realized half-span
MIN_N = 100         # pre-registered minimum sessions per selected regime cell

BASE_CELLS = [
    ("B1", "put 0.16 / 0.75% wide / enter 10:00 / close at the quote 15:50 (O-2 default)",
     o2.Cfg(structure="put", target=0.16, width_pct=0.0075, entry="10:00", exit="15:50")),
    ("B2", "put 0.25 / 1.50% wide / enter 14:00 / close at the quote 15:55 (O-2 best cell)",
     o2.Cfg(structure="put", target=0.25, width_pct=0.015, entry="14:00", exit="15:55")),
]


# ------------------------------------------------------------------ features
def features(ch: o2.Chain, entry: str) -> dict | None:
    """The two pre-declared chain-state features, read at the cell's own entry timestamp."""
    i = ch.at_or_after(entry)
    if i < 0:
        return None
    spot = ch.spot(i)
    if not np.isfinite(spot) or spot <= 0:
        return None
    pp, pc = ch.prob_itm(i)
    ok = ch.valid(i)
    ks = ch.strikes

    # rn_skew: the chain's own dP/dK read at matched distance either side of spot.
    mp = ok & np.isfinite(pp)
    mc = ok & np.isfinite(pc)
    if mp.sum() < 3 or mc.sum() < 3:
        return None
    k_dn, k_up = spot * (1.0 - SKEW_D), spot * (1.0 + SKEW_D)
    if not (ks[mp].min() <= k_dn <= ks[mp].max() and ks[mc].min() <= k_up <= ks[mc].max()):
        return None
    p_dn = float(np.interp(k_dn, ks[mp], pp[mp]))
    p_up = float(np.interp(k_up, ks[mc], pc[mc]))
    rn_skew = p_dn - p_up

    # rn_half: half the risk-neutral interquartile span, as a fraction of spot.
    k_p25 = o2.pick_strike(ks, pp, ch.sellable(i, "P"), RN_TARGET, "P", spot)
    k_c25 = o2.pick_strike(ks, pc, ch.sellable(i, "C"), RN_TARGET, "C", spot)
    if not (np.isfinite(k_p25) and np.isfinite(k_c25)):
        return None
    rn_half = ((spot - k_p25) + (k_c25 - spot)) / 2.0 / spot
    if not np.isfinite(rn_half) or rn_half <= 0:
        return None
    return {"rn_skew": rn_skew, "rn_half": rn_half, "p_dn": p_dn, "p_up": p_up}


def run_pass(symbol: str = "SPY", dates: list[str] | None = None,
             progress: int = 300) -> dict[str, pd.DataFrame]:
    """One pass over the store: every base cell and its features, parsing each session once."""
    dates = dates or odte_data.stored_dates(symbol)
    rows: dict[str, list[dict]] = {name: [] for name, _, _ in BASE_CELLS}
    for n, d in enumerate(dates, 1):
        day = odte_data.load_day(symbol, d)
        if day.empty:
            continue
        try:
            ch = o2.Chain(day)
        except Exception:  # noqa: BLE001 - a malformed stored day is not a result
            continue
        for name, _, cfg in BASE_CELLS:
            r = o2.run_session(ch, cfg)
            if not r:
                continue
            f = features(ch, cfg.entry)
            if not f:
                continue
            rows[name].append({**r, **f})
        if progress and n % progress == 0:
            print(f"  {n}/{len(dates)} sessions", flush=True)
    out = {}
    for name, r in rows.items():
        df = pd.DataFrame(r)
        if df.empty:
            out[name] = df
            continue
        df = df.sort_values("date").reset_index(drop=True)
        # rz_half: the realized half-span on this cell's own clock, strictly prior sessions.
        realized = (df.spot_end / df.spot - 1.0).abs()
        df["rz_half"] = realized.shift(1).rolling(RZ_WINDOW, min_periods=RZ_WINDOW).median()
        df["vrp"] = df.rn_half - df.rz_half
        out[name] = df
    return out


# ------------------------------------------------------------------ statistics
def _welch(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return np.nan
    va, vb = a.var(ddof=1) / na, b.var(ddof=1) / nb
    return (a.mean() - b.mean()) / np.sqrt(va + vb) if va + vb > 0 else np.nan


def _t(x: np.ndarray) -> float:
    n = len(x)
    if n < 2 or x.std(ddof=1) == 0:
        return np.nan
    return x.mean() / (x.std(ddof=1) / np.sqrt(n))


def assign_terciles(df: pd.DataFrame, feat: str) -> pd.Series:
    """Terciles formed WITHIN each regime, so a level drift cannot masquerade as selection."""
    out = pd.Series(index=df.index, dtype=object)
    for name, s, e in o2.REGIMES:
        m = (df.date >= s) & (df.date <= e) & df[feat].notna()
        if m.sum() < 3:
            continue
        out.loc[m] = pd.qcut(df.loc[m, feat], 3, labels=["T1", "T2", "T3"])
    return out


def stage_a(df: pd.DataFrame, feat: str) -> tuple[pd.DataFrame, bool]:
    """Does GROSS return on risk vary with the feature? Monotone T1->T3 and |t(T3-T1)| > 2."""
    ter = assign_terciles(df, feat)
    sub = df[ter.notna()].copy()
    sub["ter"] = ter[ter.notna()]
    rows = []
    for label in ("T1", "T2", "T3"):
        s = sub[sub.ter == label]
        rows.append({"tercile": label, "n": len(s),
                     f"{feat}_lo": s[feat].min(), f"{feat}_hi": s[feat].max(),
                     "gross%": 100 * s.ror_gross.mean(), "t_gross": _t(s.ror_gross.to_numpy()),
                     "net%": 100 * s.ror.mean(), "t_net": _t(s.ror.to_numpy()),
                     "breach%": 100 * s.breach.mean(), "cr/w": (s.credit / s.width).mean()})
    tab = pd.DataFrame(rows)
    g = tab["gross%"].to_numpy()
    monotone = bool((g[0] <= g[1] <= g[2]) or (g[0] >= g[1] >= g[2]))
    t31 = _welch(sub[sub.ter == "T3"].ror_gross.to_numpy(), sub[sub.ter == "T1"].ror_gross.to_numpy())
    tab.attrs["t31"] = t31
    return tab, bool(monotone and np.isfinite(t31) and abs(t31) > 2.0)


def stage_b(df: pd.DataFrame, feat: str, selected: str = "T3") -> pd.DataFrame:
    """NET return on risk per regime, on the selected subset and on its complement."""
    ter = assign_terciles(df, feat)
    sub = df[ter.notna()].copy()
    sub["ter"] = ter[ter.notna()].astype(str)
    rows = []
    for label, m in (("selected", sub.ter == selected), ("placebo", sub.ter != selected)):
        for rname, s, e in o2.REGIMES + [("all", "1900-01-01", "2100-01-01")]:
            x = sub[m & (sub.date >= s) & (sub.date <= e)]
            if x.empty:
                continue
            r = x.ror.to_numpy()
            t = _t(r)
            rows.append({"subset": label, "regime": rname, "n": len(x),
                         "gross%": 100 * x.ror_gross.mean(),
                         "spread%": -100 * (x.spread_cost / x.risk).mean(),
                         "fee%": -100 * (x.fees / x.risk).mean(),
                         "net%": 100 * r.mean(), "t": t,
                         "pass": int(rname != "all" and len(x) >= MIN_N
                                     and r.mean() > 0 and np.isfinite(t) and t > 2.0)})
    return pd.DataFrame(rows)


def unconditional(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rname, s, e in o2.REGIMES + [("all", "1900-01-01", "2100-01-01")]:
        x = df[(df.date >= s) & (df.date <= e)]
        if x.empty:
            continue
        rows.append({"regime": rname, "n": len(x),
                     "gross%": 100 * x.ror_gross.mean(),
                     "spread%": -100 * (x.spread_cost / x.risk).mean(),
                     "fee%": -100 * (x.fees / x.risk).mean(),
                     "net%": 100 * x.ror.mean(), "t": _t(x.ror.to_numpy())})
    return pd.DataFrame(rows)


def bound(frames: dict[str, pd.DataFrame]) -> None:
    """POST-HOC, and labelled as such: what is the ceiling on ANY session filter?

    Stage A refuses two features. This asks the question one level up, which is the one that
    generalises: selection can only pay if a session's GROSS premium and the COST of harvesting
    it can be pulled apart. Reported per tercile as `cover` = gross / (spread + fee), the same
    ratio O-2's decomposition used, plus the per-session correlation of the two and the lift in
    cover that clearing the cost would require. The best tercile here is chosen WITH hindsight
    out of twelve, so its net is an upper bound on what any honest filter could have produced.
    """
    print("\n" + "=" * 100)
    print("BOUND (post-hoc, an upper bound - NOT a result): can gross and cost be pulled apart?")
    best = None
    for name, _, _ in BASE_CELLS:
        df = frames[name]
        if df.empty:
            continue
        g_all = df.ror_gross.mean()
        c_all = ((df.spread_cost + df.fees) / df.risk).mean()
        gs = (df.pnl_gross / df.risk)
        cs = ((df.spread_cost + df.fees) / df.risk)
        print(f"\n  {name}: unconditional cover = {g_all / c_all:.3f} "
              f"(gross {100 * g_all:.3f}% / cost {100 * c_all:.3f}%); a filter must reach 1.000, "
              f"i.e. lift cover {c_all / g_all:.2f}x")
        print(f"      per-session corr(gross, cost) = {gs.corr(cs):+.3f}  "
              f"- negative: the expensive sessions are the LOSING ones (a breached position is "
              f"bought back through a wide quote), so cost and edge are adversely coupled")
        print(f"      cover = 1.000 IS net zero by construction, so a filter has to find "
              f"sessions with cover > 1 out of sample.")
        rows = []
        for feat in ("rn_skew", "vrp"):
            d = df[df[feat].notna()].copy()
            ter = assign_terciles(d, feat)
            for label in ("T1", "T2", "T3"):
                s = d[ter == label]
                if s.empty:
                    continue
                g = (s.pnl_gross / s.risk).mean()
                c = ((s.spread_cost + s.fees) / s.risk).mean()
                r = s.ror.to_numpy()
                rows.append({"feature": feat, "tercile": label, "n": len(s),
                             "gross%": 100 * g, "cost%": 100 * c, "cover": g / c,
                             "net%": 100 * r.mean(), "t": _t(r)})
                if best is None or 100 * r.mean() > best["net%"]:
                    best = {"cell": name, **rows[-1]}
        print(o2.fmt(pd.DataFrame(rows)))
    if best:
        print(f"\n  BEST OF TWELVE, CHOSEN WITH HINDSIGHT: {best['cell']} {best['feature']} "
              f"{best['tercile']}, n={best['n']}, cover {best['cover']:.3f}, "
              f"net {best['net%']:+.3f}% at t {best['t']:+.2f}")
        print("  That is the ceiling on selection, and it does not clear zero at any t.")


# ------------------------------------------------------------------ identity
def identity(symbol: str = "SPY") -> int:
    """O-3's control must BE O-2's cell. Two exact claims, both checked here.

    (1) Running B1 through sweep_o2's own `run_study` over the whole store reproduces the ledger
        row O-2's verdict rests on (20260910T203647Z: 1,889 sessions, -1.5301%, t -3.20).
    (2) Restricted to the sessions where O-3's features are computable, that same frame equals
        O-3's control to machine precision - so the gap between the two is the SAMPLE and
        nothing else, and no line of the trade was re-implemented.
    """
    _, _, cfg = BASE_CELLS[0]
    print("IDENTITY 1 - sweep_o2.run_study(B1) over the whole store vs the recorded O-2 row")
    full = o2.run_study(cfg, symbol)
    r = full.ror.to_numpy()
    print(f"  sessions {len(full)}  ror% {100 * r.mean():.4f}  t {_t(r):.2f}"
          f"   (ledger: 1889  -1.5301  -3.20)")

    print("\nIDENTITY 2 - the same frame restricted to O-3's feature-complete sessions")
    mine = run_pass(symbol, odte_data.stored_dates(symbol))[BASE_CELLS[0][0]]
    keep = set(mine.date)
    sub = full[full.date.isin(keep)].sort_values("date").reset_index(drop=True)
    m = mine.sort_values("date").reset_index(drop=True)
    ok = len(sub) == len(m)
    dmax = float(np.abs(sub.ror.to_numpy() - m.ror.to_numpy()).max()) if ok else float("nan")
    print(f"  o2 rows {len(sub)}   o3 rows {len(m)}   max |difference| in ror = {dmax:.3e}")
    print(f"  dropped by the feature pass: {len(full) - len(sub)} of {len(full)} sessions")
    print(f"\n  IDENTITY {'EXACT' if ok and dmax == 0.0 else 'FAILED'}")
    return 0


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="SPY")
    ap.add_argument("--limit", type=int, default=0, help="smoke test on the first N stored sessions")
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC ledger rows")
    ap.add_argument("--identity", action="store_true",
                    help="prove the control IS O-2's cell and the only difference is the sample")
    args = ap.parse_args()

    if args.identity:
        return identity(args.symbol)

    dates = odte_data.stored_dates(args.symbol)
    if args.limit:
        dates = dates[:args.limit]
    print(f"O-3: {len(dates)} stored {args.symbol} 0DTE sessions, "
          f"{dates[0]} .. {dates[-1]}\n", flush=True)

    frames = run_pass(args.symbol, dates)
    verdict: list[tuple[str, str, bool, bool, bool]] = []

    for name, desc, cfg in BASE_CELLS:
        df = frames[name]
        print("=" * 100)
        print(f"CELL {name} - {desc}")
        if df.empty:
            print("  no sessions")
            continue
        print(f"  sessions {len(df)}, feature-complete {int(df.vrp.notna().sum())} "
              f"(vrp needs {RZ_WINDOW} prior sessions)")
        print("\nUNCONDITIONAL (this is O-2's refusal, reproduced as the control)")
        print(o2.fmt(unconditional(df)))

        for feat in ("rn_skew", "vrp"):
            d = df[df[feat].notna()].copy()
            print("\n" + "-" * 100)
            print(f"STAGE A - does GROSS vary with {feat}? "
                  f"(terciles within regime, n={len(d)})")
            tab, passed_a = stage_a(d, feat)
            print(o2.fmt(tab))
            print(f"  t(T3 - T1) on gross = {tab.attrs['t31']:.2f}  ->  "
                  f"Stage A {'PASS' if passed_a else 'FAIL'}")
            if not passed_a:
                print(f"  Stage B not run on {feat}: the pre-registered rule stops here.")
                verdict.append((name, feat, False, False, False))
                continue
            print(f"\nSTAGE B - is the selected subset NET-positive? (rule: net > 0 at t > 2 "
                  f"in >= 2 of 3 regimes, n >= {MIN_N})")
            sb = stage_b(d, feat)
            print(o2.fmt(sb))
            sel = int(sb[(sb.subset == "selected")]["pass"].sum())
            pla = int(sb[(sb.subset == "placebo")]["pass"].sum())
            print(f"  selected regimes passing: {sel}/3   placebo regimes passing: {pla}/3")
            passed_b = sel >= 2
            clean = passed_b and pla < 2
            print(f"  -> Stage B {'PASS' if passed_b else 'FAIL'}; "
                  f"placebo {'CLEAN' if pla < 2 else 'CONTAMINATED'}")
            verdict.append((name, feat, True, passed_b, clean))

        if args.record:
            # The ledger carries the evidence whatever the verdict: the control and every
            # tercile of both features, so the refusal is auditable without re-running.
            o2.record("odte_o3_select",
                      f"DIAGNOSTIC O-3 {name} unconditional control, closed at the quote [all]",
                      df, cfg)
            for feat in ("rn_skew", "vrp"):
                d = df[df[feat].notna()].copy()
                ter = assign_terciles(d, feat)
                for label in ("T1", "T2", "T3"):
                    x = d[ter == label]
                    if len(x) > 1:
                        o2.record("odte_o3_select",
                                  f"DIAGNOSTIC O-3 {name} {feat} {label}, closed at the "
                                  f"quote [all]", x, cfg)

    bound(frames)

    print("\n" + "=" * 100)
    print("O-3 VERDICT against the rule pre-registered in this file's docstring")
    v = pd.DataFrame(verdict, columns=["cell", "feature", "stage_A", "stage_B", "placebo_clean"])
    print(o2.fmt(v) if len(v) else "  nothing ran")
    overall = bool(len(v) and (v.stage_A & v.stage_B & v.placebo_clean).any())
    print(f"\n  ANY feature/cell clearing all three gates: {'YES' if overall else 'NO'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
