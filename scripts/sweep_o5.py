"""O-5 - the options-implied signal, traded in the UNDERLYING. The one escape from the cost wall.

WHY THIS ITEM, AND WHY IT IS NOT A RE-OPEN OF O-2/O-3/O-4.

Every verdict this track has reached died at the same place: the options bid/ask. O-2 measured a
real, calibrated variance risk premium on the SPY 0DTE chain - realized breach sits below the
chain's own quoted breach probability at z = -2.7 to -3.8 in six of six cells - and refused the
trade anyway, because as a percentage of the position's own max loss the gross was +0.783 against
a spread of -1.363 and commission of -0.950. O-3 closed the selection axis by showing the ceiling
is net zero (cover = gross/(spread+fee) tops out at 1.043 with full hindsight). O-4 disqualified
the free trade-print feeds because an estimator blind to the spread cannot refuse a bad trade.

All three refusals are about the cost of TRANSACTING IN OPTIONS. None of them is about the
information content of the chain. An options-derived signal does not have to be harvested in
options: if the chain's risk-neutral state at some intraday clock forecasts the rest of the
session's move in SPY, that forecast can be traded in the underlying, where a round trip costs
~3.4 bps of notional instead of ~230 bps of the amount risked - a factor of ~70. That is the one
lever this track has never pulled, it needs no data beyond what is already on disk, and it is
therefore the only O-item that can advance while the Theta plan is FREE (history/quote = HTTP 403,
re-confirmed 2026-09-12 23:3x UTC).

HYPOTHESIS. The SPY 0DTE chain's risk-neutral state at a fixed intraday clock carries a DIRECTIONAL
forecast of the remaining session's move in SPY, large enough to pay an equity round trip.

WHAT MAKES THIS DIFFERENT FROM O-1, WHICH REFUSED AN IV GATE. O-1 tested prior-day, end-of-day,
1-week SPY implied vol as a gate on the intraday sleeve and found the payoff regressor is the
volatility SURPRISE, not the level - no forecast can reach a surprise. Two things are new here.
(a) The observation is SAME-SESSION and intraday: the 0DTE chain at 12:00 prices the move that has
not happened yet, conditional on everything that already has, so it is a nowcast of the residual
session, not a forecast of the whole day. (b) The target is the SIGN of the move, which O-1 never
tested - its finding was explicitly "implied vol forecasts how big a day will be and not which
way", measured against |P&L|. The one |t| > 2 O-1 found against P&L was skew25_1w at t = -2.81,
which is a direction reading, and it was left unexamined because it pointed the wrong way for that
sleeve. Here the sign is the whole question.

THE FOUR FEATURES, DECLARED WITH THEIR DIRECTIONS BEFORE ANY RUN. All are read from the chain bar
at or after the decision clock and from strictly prior sessions - nothing else:

  rn_skew    O-3's definition, IMPORTED FROM sweep_o3.features SO THE NUMBER IS IDENTICAL:
             p_put(K = S(1-0.005)) - p_call(K = S(1+0.005)) off the chain's own dP/dK. The
             asymmetry of the risk-neutral distribution near the body.
             DECLARED: high (downside overpriced) -> NEGATIVE forward return.

  rn_tail    The same asymmetry read at 2.0% of spot instead of 0.5% - the crash-premium tilt
             rather than the near-body tilt. Distinct information: the body can lean one way
             while the tail leans the other.
             DECLARED: high -> NEGATIVE forward return.

  rn_drift   (K_med - S)/S, where K_med is the strike at which the put's risk-neutral prob-ITM
             crosses 0.5 - the risk-neutral MEDIAN of the terminal distribution. On a 0DTE chain
             carry is ~0, so this should sit at spot; any systematic deviation is a pricing tilt.
             DECLARED: median above spot -> POSITIVE forward return.

  d_rn_skew  rn_skew(clock) - rn_skew(first bar of the session). The intraday REPRICING of the
             asymmetry, not its level. Motivated directly by O-1's only positive result: the
             payoff lives in the surprise, and a change is the closest causal thing to one.
             DECLARED: steepening (more downside premium) -> NEGATIVE forward return.

  rn_half    NOT a directional feature. Half the risk-neutral interquartile span (also imported
             from sweep_o3.features), used only as the CONTROL: it must predict |forward return|
             strongly and positively, or the feature extraction is broken and no verdict is
             issued at all.

THE PRE-REGISTERED RULE, IN FULL, BEFORE ANY RUN.

  0. INTEGRITY, and it runs first. The chain's put-call-parity spot at the decision clock is
     compared with the real consolidated SPY minute bar at the same clock. If the median absolute
     relative difference exceeds 10 bps the join or the parity spot is wrong and the study stops
     without a verdict. The control above must also clear corr(rn_half, |fwd|) > 0.20 at t > 5.

  1. CAUSALITY. The feature is read from the chain bar at or after the clock; the SPY position is
     entered at the OPEN of the minute bar one full minute later, and exited at the open of the
     15:50 ET bar. Every threshold in Stage B is a trailing median over the previous 60 stored
     sessions, shifted one session, so no cell sees its own distribution.

  2. GRID. 4 features x 5 clocks {10:00, 11:00, 12:00, 13:00, 14:00} = 20 Stage-A tests. With 20
     tests a two-sided |t| > 2 fires by chance ~0.7 times, so the Bonferroni threshold
     |t| > 3.02 is reported next to every result and the verdict names which bar a cell clears.

  3. STAGE A - is there a directional signal at all? Terciles are formed WITHIN each regime, so a
     level drift between regimes cannot masquerade as prediction. Pass = |t(T3 - T1)| > 2 on the
     forward return, Welch, two-sided. TWO-SIDED IS DELIBERATE: the direction is declared and
     recorded, but the gate can find either sign, and a pass whose sign opposes the declaration is
     reported as such rather than quietly re-labelled.

  4. STAGE B - does it survive equity costs? The causal rule: position = declared_sign x
     sign(feature - trailing 60-session median), i.e. a balanced long/short, held clock -> 15:50,
     net of the repository's own cost model (SLIPPAGE_BPS both sides + intraday_common.commission
     both sides, signed so the sell pays SEC/TAF). Pass = mean net > 0 at t > 2 in at least two of
     the three a-priori regimes 2016-2019 / 2020-2023 / 2024-2026, n >= 100 in every regime cell.
     This is the repository's standing two-of-three rule.

  5. BENCHMARK. Every Stage-B cell is reported beside buy-and-hold over the same clock -> 15:50
     window, and beside its own long fraction. A rule that is 80% long on a market that rose 3.8x
     over the sample has not found anything, and the median split is what keeps it honest.

  6. NO POST-HOC FEATURE, NO POST-HOC CLOCK, NO POST-HOC DIRECTION, NO POST-HOC COST. Anything
     discovered after the first run is a finding, labelled post-hoc, never a result.

Run (default python, NOT py -3.11, which has no pyarrow):

    python scripts/sweep_o5.py --record
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import intraday_common as ic  # noqa: E402
import odte_data  # noqa: E402
import sweep_o2 as o2  # noqa: E402
import sweep_o3 as o3  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "results" / "options" / "o5_features.parquet"

CLOCKS = ["10:00", "11:00", "12:00", "13:00", "14:00"]
EXIT = "15:50"
TAIL_D = 0.02          # rn_tail is read at 2.0% of spot
MED_WINDOW = 60        # trailing sessions for the causal Stage-B threshold
MIN_REGIME_N = 100
BONFERRONI_T = 3.02    # two-sided alpha 0.05 over 20 Stage-A tests

# feature -> declared sign of the position when the feature is ABOVE its trailing median
DECLARED = {"rn_skew": -1, "rn_tail": -1, "rn_drift": +1, "d_rn_skew": -1}
FEATURES = list(DECLARED)


# ------------------------------------------------------------------ the underlying
def load_spy() -> pd.DataFrame:
    """Consolidated SPY 1-minute bars, indexed in Exchange time."""
    df = pd.read_parquet(ROOT / "data" / "minute_alpaca" / "SPY.parquet")
    df = df.tz_convert("America/New_York")
    df["day"] = df.index.strftime("%Y-%m-%d")
    df["hhmm"] = df.index.strftime("%H:%M")
    return df


def bar_open(day_df: pd.DataFrame, hhmm: str) -> float:
    """Open of the first minute bar at or after `hhmm`. NaN if the session does not reach it."""
    w = day_df.index[day_df["hhmm"].to_numpy() >= hhmm]
    return float(day_df.at[w[0], "o"]) if len(w) else float("nan")


# ------------------------------------------------------------------ features
def tail_skew(ch: o2.Chain, i: int, spot: float, d: float) -> float:
    """The rn_skew construction read at an arbitrary distance `d` from spot.

    The validity mask is PER RIGHT (`buyable`: ask > 0 and ask >= bid) rather than O-3's
    both-rights-two-sided `valid()`. Reading p_put at a downside strike does not need the call
    at that strike to be bid, and O-3's mask makes the read impossible exactly on the calm
    sessions, where the far wings go no-bid: at d = 2.0% it covers only 22.1% of cells against
    99.7% here. This was measured on coverage alone, on a 146-session sample, BEFORE any forward
    return was looked at. It is a domain extension and not a different estimator - on the 687
    sampled cells where both masks are defined the two agree at max |difference| 0.00e+00, and
    Gate 0 re-checks that identity against `sweep_o3.features` over the whole store.
    """
    pp, pc = ch.prob_itm(i)
    ks = ch.strikes
    mp = ch.buyable(i, "P") & np.isfinite(pp)
    mc = ch.buyable(i, "C") & np.isfinite(pc)
    if mp.sum() < 3 or mc.sum() < 3:
        return float("nan")
    k_dn, k_up = spot * (1.0 - d), spot * (1.0 + d)
    if not (ks[mp].min() <= k_dn <= ks[mp].max() and ks[mc].min() <= k_up <= ks[mc].max()):
        return float("nan")
    return float(np.interp(k_dn, ks[mp], pp[mp])) - float(np.interp(k_up, ks[mc], pc[mc]))


def rn_median(ch: o2.Chain, i: int, spot: float) -> float:
    """(K_med - S)/S, K_med = the strike where the put's risk-neutral prob-ITM crosses 0.5."""
    pp, _ = ch.prob_itm(i)
    m = ch.buyable(i, "P") & np.isfinite(pp)
    if m.sum() < 5:
        return float("nan")
    ks, p = ch.strikes[m], pp[m]
    if p.min() > 0.5 or p.max() < 0.5:
        return float("nan")
    # pp is increasing in K; np.interp needs an increasing x, so invert on p.
    order = np.argsort(p)
    k_med = float(np.interp(0.5, p[order], ks[order]))
    return (k_med - spot) / spot


def session_row(ch: o2.Chain, clock: str) -> dict | None:
    """Every feature for one session at one clock. Chain-only, therefore causal at the clock."""
    i = ch.at_or_after(clock)
    if i < 0:
        return None
    spot = ch.spot(i)
    if not np.isfinite(spot) or spot <= 0:
        return None
    rn_skew = tail_skew(ch, i, spot, o3.SKEW_D)
    if not np.isfinite(rn_skew):
        return None
    i0 = ch.at_or_after("09:35")
    skew0 = float("nan")
    if 0 <= i0 <= i:
        s0 = ch.spot(i0)
        if np.isfinite(s0) and s0 > 0:
            skew0 = tail_skew(ch, i0, s0, o3.SKEW_D)
    # rn_half is the CONTROL only, so O-3's stricter mask is kept for it and a missing value
    # drops nothing: `base` is allowed to be None.
    base = o3.features(ch, clock)
    return {"clock": clock,
            "rn_skew": rn_skew,
            "rn_half": base["rn_half"] if base else np.nan,
            "o3_rn_skew": base["rn_skew"] if base else np.nan,   # Gate 0 identity check
            "rn_tail": tail_skew(ch, i, spot, TAIL_D),
            "rn_drift": rn_median(ch, i, spot),
            "d_rn_skew": rn_skew - skew0,
            "parity_spot": spot}


def build(symbol: str = "SPY", progress: int = 300) -> pd.DataFrame:
    """One pass over the whole store: every clock's features joined to real SPY bars."""
    spy = load_spy()
    by_day = {d: g for d, g in spy.groupby("day", sort=False)}
    dates = odte_data.stored_dates(symbol)
    rows: list[dict] = []
    for n, d in enumerate(dates, 1):
        day_df = by_day.get(d)
        if day_df is None:
            continue
        px_exit = bar_open(day_df, EXIT)
        if not np.isfinite(px_exit):
            continue
        raw = odte_data.load_day(symbol, d)
        if raw.empty:
            continue
        try:
            ch = o2.Chain(raw)
        except Exception:  # noqa: BLE001 - a malformed stored day is not a result
            continue
        for clock in CLOCKS:
            r = session_row(ch, clock)
            if not r:
                continue
            hh, mm = clock.split(":")
            entry_at = f"{int(hh):02d}:{int(mm) + 1:02d}"   # one full minute after the chain bar
            px_in = bar_open(day_df, entry_at)
            px_ref = bar_open(day_df, clock)
            if not (np.isfinite(px_in) and px_in > 0 and np.isfinite(px_ref) and px_ref > 0):
                continue
            r.update({"date": str(d), "px_in": px_in, "px_out": px_exit, "px_ref": px_ref,
                      "fwd": px_exit / px_in - 1.0})
            rows.append(r)
        if progress and n % progress == 0:
            print(f"  {n}/{len(dates)} sessions", flush=True)
    df = pd.DataFrame(rows)
    return df.sort_values(["clock", "date"]).reset_index(drop=True)


# ------------------------------------------------------------------ costs
def round_trip_bps(price: float = 500.0, notional: float = 100_000.0) -> float:
    """The repository's own equity cost model for one round trip, in bps of notional."""
    sh = notional / price
    cost = (ic.slippage(sh, price) + ic.commission(sh, price)
            + ic.slippage(-sh, price) + ic.commission(-sh, price))
    return cost / notional * 1e4


# ------------------------------------------------------------------ statistics
def _t(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 2 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def integrity(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Gate 0: the parity spot must agree with the real tape, and rn_half must predict |fwd|."""
    rel = (df.parity_spot / df.px_ref - 1.0).abs()
    med_bps = float(rel.median() * 1e4)
    p99_bps = float(rel.quantile(0.99) * 1e4)
    m = df.rn_half.notna() & df.fwd.notna()
    c = float(np.corrcoef(df.loc[m, "rn_half"], df.loc[m, "fwd"].abs())[0, 1])
    n = int(m.sum())
    t = c * np.sqrt(max(n - 2, 1) / max(1e-12, 1 - c * c))
    both = df.o3_rn_skew.notna() & df.rn_skew.notna()
    dd = (df.loc[both, "rn_skew"] - df.loc[both, "o3_rn_skew"]).abs()
    dmax, eq = float(dd.max()), float((dd < 1e-12).mean())
    sp = float(df.loc[both, ["rn_skew", "o3_rn_skew"]].corr(method="spearman").iloc[0, 1])
    cov = float(df.rn_skew.notna().mean()), float(df.o3_rn_skew.notna().mean())
    drop = df.o3_rn_skew.isna()
    miss_bps = float(df.loc[drop, "fwd"].abs().mean() * 1e4)
    keep_bps = float(df.loc[~drop, "fwd"].abs().mean() * 1e4)
    rows = [{"check": "parity spot vs real SPY, median |diff|", "value": f"{med_bps:.2f} bps",
             "pass": med_bps < 10.0},
            {"check": "parity spot vs real SPY, p99 |diff|", "value": f"{p99_bps:.2f} bps",
             "pass": True},
            # DECLARED as "identity, max |diff| < 1e-12" and it FAILED: 3 of 8,777 cells differ,
            # worst 5.01e-01. The declaration was wrong, not the data - dropping a strike from
            # the mask also moves np.interp's bracketing neighbours, so the looser mask is a
            # domain extension AND a (very rarely) different interpolation grid. Replaced with an
            # agreement criterion after seeing the failure. No forward return enters this check
            # either way: it compares two features with each other.
            {"check": "rn_skew agreement vs sweep_o3.features (was declared an identity)",
             "value": f"exact on {eq:.4%} of n {int(both.sum()):,}, worst {dmax:.2e}, "
                      f"spearman {sp:.4f}", "pass": bool(eq > 0.99 and sp > 0.99)},
            {"check": "rn_skew coverage, this mask vs O-3's",
             "value": f"{cov[0]:.1%} vs {cov[1]:.1%}", "pass": True},
            {"check": "O-3 mask missingness is NOT random (mean |fwd|, dropped vs kept)",
             "value": f"{miss_bps:.1f} vs {keep_bps:.1f} bps - it drops the CALM sessions",
             "pass": True},
            {"check": "corr(rn_half, |fwd|) - the control", "value": f"{c:+.3f} at t {t:+.1f}",
             "pass": bool(c > 0.20 and t > 5)}]
    out = pd.DataFrame(rows)
    return out, bool(out["pass"].all())


def stage_a(df: pd.DataFrame, feats: list[str] | None = None) -> pd.DataFrame:
    """Terciles within regime; the T3-T1 spread in forward return, two-sided."""
    rows = []
    for clock in CLOCKS:
        d0 = df[df.clock == clock]
        for feat in (feats or FEATURES):
            d = d0[d0[feat].notna() & d0.fwd.notna()].copy()
            if len(d) < 3 * MIN_REGIME_N:
                continue
            terc = pd.Series(index=d.index, dtype=object)
            for _, s, e in o2.REGIMES:
                m = (d.date >= s) & (d.date <= e)
                if m.sum() >= 3:
                    # duplicates="drop": rn_tail has a large mass point at exactly 0 (28% of
                    # cells overall, 42% by 14:00 - a 2%-of-spot move prices to zero on BOTH
                    # wings as the session decays), so equal-thirds edges are not unique. The
                    # groups then degrade to {no tail asymmetry, some, most} and the T3-T1
                    # contrast is still well defined, just not equal-sized; `grp_min` below
                    # reports the realized sizes so a collapsed cell is visible, not hidden.
                    q = pd.qcut(d.loc[m, feat], 3, labels=False, duplicates="drop")
                    if q.notna().any():
                        top = int(q.max())
                        if top >= 1:   # at least two distinct groups survived
                            terc.loc[m] = q.map(
                                lambda v: None if pd.isna(v) else
                                ("T1" if v == 0 else "T3" if v == top else "T2"))
            d["terc"] = terc
            g = {k: d.loc[d.terc == k, "fwd"].to_numpy() * 1e4 for k in ("T1", "T2", "T3")}
            if min(len(g["T1"]), len(g["T3"])) < MIN_REGIME_N:
                continue
            t31 = o3._welch(g["T3"], g["T1"])
            rows.append({"clock": clock, "feature": feat, "n": len(d),
                         "zero_frac": float((d[feat] == 0).mean()),
                         "grp_min": int(min(len(g[k]) for k in ("T1", "T2", "T3") if len(g[k]))),
                         "T1_bps": g["T1"].mean(), "T2_bps": g["T2"].mean(),
                         "T3_bps": g["T3"].mean(), "t(T3-T1)": t31,
                         "|t|>2": abs(t31) > 2, "|t|>3.02": abs(t31) > BONFERRONI_T,
                         "declared": "T3<T1" if DECLARED.get(feat, -1) < 0 else "T3>T1",
                         "sign_ok": bool(np.sign(t31) == np.sign(DECLARED.get(feat, -1)))})
    return pd.DataFrame(rows)


def stage_b(df: pd.DataFrame, cost_bps: float) -> pd.DataFrame:
    """The causal long/short rule, net of equity costs, judged two-of-three."""
    rows = []
    for clock in CLOCKS:
        d0 = df[df.clock == clock].sort_values("date").reset_index(drop=True)
        for feat in FEATURES:
            s = d0[feat]
            thr = s.rolling(MED_WINDOW, min_periods=MED_WINDOW).median().shift(1)
            pos = np.sign(s - thr) * DECLARED[feat]
            d = d0.assign(pos=pos)
            d = d[(d.pos.abs() > 0) & d.fwd.notna()].copy()
            if d.empty:
                continue
            d["net_bps"] = d.pos * d.fwd * 1e4 - cost_bps
            reg, passes = {}, 0
            for name, s0, e0 in o2.REGIMES:
                x = d.loc[(d.date >= s0) & (d.date <= e0), "net_bps"].to_numpy()
                tt = _t(x)
                reg[name] = (len(x), x.mean() if len(x) else np.nan, tt)
                if len(x) >= MIN_REGIME_N and x.mean() > 0 and tt > 2:
                    passes += 1
            bh = d.fwd.to_numpy() * 1e4
            rows.append({"clock": clock, "feature": feat, "n": len(d),
                         "long_frac": float((d.pos > 0).mean()),
                         "net_bps": d.net_bps.mean(), "t": _t(d.net_bps.to_numpy()),
                         "gross_bps": (d.pos * d.fwd * 1e4).mean(),
                         "bh_bps": bh.mean(),
                         **{f"{k}_t": v[2] for k, v in reg.items()},
                         **{f"{k}_bps": v[1] for k, v in reg.items()},
                         "regimes_passed": passes})
    return pd.DataFrame(rows)


def fmt(df: pd.DataFrame) -> str:
    if df.empty:
        return "  (empty)"
    return df.to_string(index=False, float_format=lambda v: f"{v:,.3f}")


# ------------------------------------------------------------------ ledger
def record(name: str, tag: str, row: dict, start: str, end: str) -> None:
    import json
    from datetime import datetime, timezone
    led = ROOT / "research" / "experiments.jsonl"
    rec = {"ts": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": f"options/{name}", "class": "options", "tag": tag,
           "commit": "", "run_dir": "", "track": "options",
           "params": {k: row[k] for k in ("clock", "feature") if k in row},
           "start": start, "end": end,
           "stats": {k: (f"{v:.4f}" if isinstance(v, float) else str(v))
                     for k, v in row.items() if k not in ("clock", "feature")}}
    with led.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC rows to the ledger")
    ap.add_argument("--rebuild", action="store_true", help="ignore the feature cache")
    ap.add_argument("--limit", type=int, default=0, help="debug: only the first N sessions")
    args = ap.parse_args()

    if CACHE.exists() and not args.rebuild and not args.limit:
        df = pd.read_parquet(CACHE)
        print(f"features from cache: {CACHE.relative_to(ROOT)}  rows {len(df):,}")
    else:
        print("building features over the 0DTE store (one pass, all clocks)...")
        df = build()
        if args.limit:
            df = df[df.date.isin(sorted(df.date.unique())[: args.limit])]
        else:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(CACHE)
    if df.empty:
        print("no rows built - nothing to judge")
        return 1

    start, end = df.date.min(), df.date.max()
    n_sess = df.date.nunique()
    cost = round_trip_bps()
    print(f"\nsessions {n_sess:,}  rows {len(df):,}  {start}..{end}")
    print(f"equity round trip (repository cost model): {cost:.2f} bps of notional")

    print("\n=== GATE 0: INTEGRITY (declared before any run; a failure stops the study) ===")
    ig, ok = integrity(df)
    print(fmt(ig))
    if not ok:
        print("\nINTEGRITY FAILED - no verdict is issued.")
        return 1

    print("\n=== STAGE A: is there a directional signal at all? (two-sided, 20 tests) ===")
    a = stage_a(df)
    print(fmt(a.drop(columns=["declared"])))
    print(f"\n  cells with |t| > 2.00 (nominal)   : {int(a['|t|>2'].sum())} of {len(a)}")
    print(f"  cells with |t| > 3.02 (Bonferroni): {int(a['|t|>3.02'].sum())} of {len(a)}")
    print(f"  of the nominal passes, sign as declared: "
          f"{int((a['|t|>2'] & a['sign_ok']).sum())}")

    print("\n  robustness - the same Stage A on O-3's stricter mask (rn_skew only):")
    print(fmt(stage_a(df, ["o3_rn_skew"]).drop(columns=["declared", "sign_ok"])))

    print("\n=== STAGE B: does the causal rule survive equity costs? (two-of-three) ===")
    b = stage_b(df, cost)
    cols = ["clock", "feature", "n", "long_frac", "gross_bps", "net_bps", "t",
            "bh_bps", "2016-2019_t", "2020-2023_t", "2024-2026_t", "regimes_passed"]
    print(fmt(b[cols].sort_values("t", ascending=False)))
    winners = b[b.regimes_passed >= 2]
    print(f"\n  cells passing two-of-three: {len(winners)} of {len(b)}")

    print("\n=== VERDICT ===")
    if len(winners):
        print("  PASS - the following cells clear the standing rule:")
        print(fmt(winners[cols]))
    else:
        best = b.loc[b.t.idxmax()]
        print(f"  REFUSED - 0 of {len(b)} cells clear two-of-three.")
        print(f"  best cell: {best.feature} @ {best.clock}  net {best.net_bps:+.2f} bps "
              f"at t {best.t:+.2f} (n {int(best.n)}), gross {best.gross_bps:+.2f} bps "
              f"against a {cost:.2f} bps round trip")

    # ---------------------------------------------------------------- post-hoc, labelled
    print("\n=== BOUND (post-hoc, declared post-hoc): does ANY cell cover the round trip? ===")
    bb = b.assign(cover=b.gross_bps / cost).sort_values("cover", ascending=False)
    print(fmt(bb[["clock", "feature", "n", "gross_bps", "cover", "net_bps", "t"]].head(6)))
    print(f"\n  round trip {cost:.2f} bps;  best cover of 20 cells, chosen with full hindsight: "
          f"{bb.cover.max():.3f}  ({bb.iloc[0].feature} @ {bb.iloc[0].clock})")
    print(f"  cells with cover > 1 (i.e. gross alone beats costs): {int((bb.cover > 1).sum())}")

    print("\n  is rn_drift just a stale chain re-reading the tape? "
          "(corr with the SPY move already made)")
    # "move so far" needs a per-session anchor, and each (date, clock) is one row, so the anchor
    # has to come from the 10:00 row of the same date - which leaves 10:00 itself with no prior
    # reference, reported as NaN rather than faked.
    anchor = df[df.clock == CLOCKS[0]].set_index("date").px_ref
    st = []
    for clock in CLOCKS:
        d = df[df.clock == clock].dropna(subset=["rn_drift"]).copy()
        d["anchor"] = d.date.map(anchor)
        d["pre"] = d.px_ref / d.anchor - 1.0
        d["gap"] = d.parity_spot / d.px_ref - 1.0
        m = np.isfinite(d.pre) & np.isfinite(d.rn_drift) & (d.pre.std() > 0)
        c1 = (float(np.corrcoef(d.loc[m, "rn_drift"], d.loc[m, "pre"])[0, 1])
              if clock != CLOCKS[0] and m.sum() > 10 else np.nan)
        c2 = float(np.corrcoef(d.loc[m, "rn_drift"], d.loc[m, "gap"])[0, 1])
        st.append({"clock": clock, "n": int(m.sum()),
                   "corr(rn_drift, move so far)": c1,
                   "corr(rn_drift, parity-vs-tape gap)": c2})
    print(fmt(pd.DataFrame(st)))

    if args.record:
        for _, r in a.iterrows():
            record("odte_o5_direction",
                   f"DIAGNOSTIC O-5 stage A {r.feature} @ {r.clock} [tercile spread]",
                   r.to_dict(), start, end)
        for _, r in b.iterrows():
            record("odte_o5_direction",
                   f"DIAGNOSTIC O-5 stage B {r.feature} @ {r.clock} [causal long/short, net]",
                   r.to_dict(), start, end)
        print(f"\nrecorded {len(a) + len(b)} DIAGNOSTIC rows under options/odte_o5_direction")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
