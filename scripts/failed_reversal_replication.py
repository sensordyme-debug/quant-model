"""Phases 2-9: run the frozen rule everywhere it can be run, and try to break it.

THE HONEST STATEMENT OF WHAT IS AND IS NOT AVAILABLE
------------------------------------------------------
The brief asks for calendar-period replication from 2018 onward and for M2K/RTY/MYM/YM.

    NO M2K, RTY, MYM OR YM EXISTS in this repository. The futures store holds ES, NQ, MES and
    MNQ only. The `f1/*.dirty.parquet` hits for those tickers are equity panels from an
    unrelated archive with no minute bars.

    THE FUTURES STORE SPANS 2025-06-08 TO 2026-09-10. Periods 2018 through 2024 are not
    merely thin - they do not exist. Any 2018-2024 futures result would be fabricated.

    ES/MES ARE THE SAME INDEX and NQ/MNQ ARE THE SAME INDEX. "Four instruments" is two
    markets in two contract sizes. A replication on NQ is not independent of MNQ.

So the futures store can supply at most ONE genuinely independent cross-market test (the S&P
complex against the Nasdaq complex) and NO independent historical period.

WHERE A REAL FALSIFICATION TEST COMES FROM
--------------------------------------------
The ETF minute stores: SPY, QQQ, IWM and DIA, 2016-01 to 2026-09, roughly 2,600 sessions each.
The frozen rule needs only `opening_range_pos` and `minutes_from_open`, both computable from
OHLCV minute bars, so the identical rule runs on them unchanged.

That gives what the futures store cannot:

    - four more instruments, two of which (IWM small-cap, DIA mega-cap) track indices the
      futures store does not cover at all
    - eight calendar years, 2016-2023, that have NEVER been inspected for this rule
    - roughly 30x the session count

This is the strongest available attempt to disprove the effect, and it is the centre of this
phase. The futures results are reported alongside but they cannot settle the question.

CONTAMINATION, STATED PLAINLY
-------------------------------
2025-06 to 2026-09 on futures has been inspected across five prior research phases. It is NOT
untouched out-of-sample and is not treated as such. The ETF years 2016-2023 have never been
used for this mechanism and are the legitimate holdout; 2024-2026 on the ETFs has been touched
once (a single preregistered bucket test in an earlier phase) and is labelled accordingly.

WHAT WOULD CONSTITUTE REPLICATION
-----------------------------------
Declared before running. The mechanism claims a short-horizon effect at 1-5 bars decaying by
10. Replication requires the SIGN and the DECAY SHAPE, not the magnitude:

    REPLICATES          positive mean signed forward return at 1, 3 and 5 bars, beating a
                        matched control at the 95th percentile at 2+ of those horizons
    MARGINAL            correct sign at 1-5 bars but clearing the control at 0-1 horizons
    FAILS               wrong sign at a majority of short horizons, or clearly negative
    INSUFFICIENT        fewer than 100 entries
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import futures_discover as fd  # noqa: E402

fd.use_session(*fd.TOPSTEP_SESSION)

from quant_brain.markets.futures_cme import features as fe        # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst   # noqa: E402
from failed_reversal_spec import SPEC, failed_reversal, rule_hash  # noqa: E402

HORIZONS = (1, 3, 5, 10, 15, 30)
N_CONTROLS = 200
TRAIN_FRACTION = 0.50
MIN_ENTRIES = 100

#: Point value and tick value for the ETF proxies: 100 shares, $0.01 tick.
ETF_SPECS = {s: {"multiplier": 100.0, "tick_value": 1.0, "commission": 1.00}
             for s in ("SPY", "QQQ", "IWM", "DIA")}


def futures_sessions(symbol: str):
    df = fd.load(REPO / "data" / "futures" / f"{symbol}.parquet", symbol)
    return fd.session_frames(df)


def etf_sessions(symbol: str):
    """Session frames in the same shape the feature library expects."""
    d = pd.read_parquet(REPO / "data" / "minute_alpaca" / f"{symbol}.parquet")
    t = d.index
    if getattr(t, "tz", None) is None:
        t = t.tz_localize("UTC")
    t = t.tz_convert("America/New_York")
    d = d.assign(t=t, day=t.date, hm=t.strftime("%H:%M")).sort_index()
    out = []
    for _, g in d.groupby("day", sort=True):
        if len(g) < 380:
            continue
        out.append(g.reset_index(drop=True))
    return out


def build(sessions):
    return fd.build_features(sessions, fe.library())


def calibrate_thresholds(feats, train_n: int) -> tuple[float, float]:
    """The frozen calibration: quantiles of opening_range_pos on the train split."""
    v = pd.concat([f["opening_range_pos"] for f in feats[:train_n]], ignore_index=True)
    v = pd.to_numeric(v, errors="coerce").to_numpy(dtype=float)
    v = v[np.isfinite(v)]
    return float(np.percentile(v, 95)), float(np.percentile(v, 5))


def excursions(c, h, low, bar, d, n_ahead):
    end = min(bar + n_ahead, len(c) - 1)
    if end <= bar:
        return np.nan, np.nan, np.nan
    entry = c[bar]
    fwd = (c[end] - entry) * d
    hi_seg, lo_seg = h[bar + 1:end + 1], low[bar + 1:end + 1]
    if d > 0:
        return float(fwd), float(hi_seg.max() - entry), float(lo_seg.min() - entry)
    return float(fwd), float(entry - lo_seg.min()), float(entry - hi_seg.max())


def collect(sessions, feats, hi: float, lo: float, mult: float):
    """Every entry the frozen rule produces, with its forward excursions in dollars."""
    recs = []
    per_session = []
    for g, X in zip(sessions, feats, strict=True):
        orp = np.nan_to_num(np.asarray(X["opening_range_pos"], dtype=float), nan=0.0)
        mins = np.nan_to_num(np.asarray(X["minutes_from_open"], dtype=float), nan=0.0)
        pos = failed_reversal(orp, mins, hi, lo)
        c = g["c"].to_numpy(dtype=float)
        h = g["h"].to_numpy(dtype=float)
        low = g["l"].to_numpy(dtype=float)
        per_session.append((c, h, low))
        prev = 0.0
        day = g["day"].iloc[0] if "day" in g.columns else g["t"].iloc[0].date()
        for i, p in enumerate(pos):
            if p != 0 and p != prev:
                r = {"session": day, "bar": i, "direction": int(np.sign(p))}
                for n in HORIZONS:
                    f, mfe, mae = excursions(c, h, low, i, int(np.sign(p)), n)
                    r[f"fwd_{n}"] = f * mult if np.isfinite(f) else np.nan
                    r[f"mfe_{n}"] = mfe * mult if np.isfinite(mfe) else np.nan
                    r[f"mae_{n}"] = mae * mult if np.isfinite(mae) else np.nan
                recs.append(r)
            prev = p
    return pd.DataFrame(recs), per_session


def matched_control(recs: pd.DataFrame, per_session, mult: float, rng,
                    n_reps: int = N_CONTROLS, shuffle_direction: bool = False) -> dict:
    """Controls matched on bar-of-session and direction, exactly as in Phase 16.

    `shuffle_direction=True` is the negative control: the same bars with the direction label
    permuted, which must destroy any real effect.
    """
    if not len(recs):
        return {}
    bars = recs["bar"].to_numpy()
    dirs = recs["direction"].to_numpy()
    n_sess = len(per_session)
    out: dict[int, list] = {n: [] for n in HORIZONS}
    for _ in range(n_reps):
        idx = rng.integers(0, n_sess, len(bars))
        dd = rng.permutation(dirs) if shuffle_direction else dirs
        vals: dict[int, list] = {n: [] for n in HORIZONS}
        for k in range(len(bars)):
            c, h, low = per_session[idx[k]]
            b = int(bars[k])
            if b >= len(c) - 2:
                continue
            for n in HORIZONS:
                f, _, _ = excursions(c, h, low, b, int(dd[k]), n)
                if np.isfinite(f):
                    vals[n].append(f * mult)
        for n in HORIZONS:
            if vals[n]:
                out[n].append(float(np.mean(vals[n])))
    return out


def bootstrap_ci(x: np.ndarray, rng, reps: int = 2000) -> tuple[float, float]:
    x = x[np.isfinite(x)]
    if len(x) < 20:
        return np.nan, np.nan
    m = np.array([np.mean(rng.choice(x, len(x), replace=True)) for _ in range(reps)])
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def summarise(recs, ctrl, rng, label: str, symbol: str, panel: str) -> dict:
    row = {"panel": panel, "symbol": symbol, "period": label,
           "entries": len(recs),
           "sessions": int(recs["session"].nunique()) if len(recs) else 0,
           "long_share": float((recs.direction > 0).mean()) if len(recs) else np.nan}
    for n in HORIZONS:
        v = recs[f"fwd_{n}"].to_numpy(dtype=float) if len(recs) else np.array([])
        v = v[np.isfinite(v)]
        row[f"mean_{n}"] = float(v.mean()) if len(v) else np.nan
        row[f"median_{n}"] = float(np.median(v)) if len(v) else np.nan
        row[f"win_{n}"] = float((v > 0).mean()) if len(v) else np.nan
        row[f"t_{n}"] = (float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v))))
                         if len(v) > 1 and v.std(ddof=1) > 0 else np.nan)
        lo, hi = bootstrap_ci(v, rng)
        row[f"ci_lo_{n}"], row[f"ci_hi_{n}"] = lo, hi
        cm = np.array(ctrl.get(n, []), dtype=float) if ctrl else np.array([])
        row[f"ctrl_{n}"] = float(np.median(cm)) if len(cm) else np.nan
        row[f"ctrl_pctile_{n}"] = (float((cm < v.mean()).mean())
                                   if len(cm) and len(v) else np.nan)
        row[f"diff_{n}"] = (row[f"mean_{n}"] - row[f"ctrl_{n}"]
                            if np.isfinite(row.get(f"ctrl_{n}", np.nan)) else np.nan)
        if len(recs):
            mfe = recs[f"mfe_{n}"].mean()
            mae = recs[f"mae_{n}"].mean()
            row[f"mfe_{n}"], row[f"mae_{n}"] = float(mfe), float(mae)
            row[f"asym_{n}"] = float(abs(mfe / mae)) if mae else np.nan
    return row


def classify(row: dict) -> str:
    if row["entries"] < MIN_ENTRIES:
        return "INSUFFICIENT"
    short = [row.get(f"mean_{n}", np.nan) for n in (1, 3, 5)]
    beats = sum(1 for n in (1, 3, 5)
                if np.isfinite(row.get(f"ctrl_pctile_{n}", np.nan))
                and row[f"ctrl_pctile_{n}"] > 0.95)
    pos = sum(1 for x in short if np.isfinite(x) and x > 0)
    if pos >= 2 and beats >= 2:
        return "REPLICATES"
    if pos >= 2:
        return "MARGINAL"
    return "FAILS"


def main() -> int:
    rng = np.random.default_rng(20260914)
    h = rule_hash()
    print("=" * 112)
    print(f"FAILED-REVERSAL REPLICATION   rule hash {h}")
    print("=" * 112)
    print("\nDATA AVAILABILITY, stated before results:")
    print("  M2K / RTY / MYM / YM        : DO NOT EXIST in this repository")
    print("  futures store span          : 2025-06-08 .. 2026-09-10 only")
    print("  => 2018-2024 futures periods: IMPOSSIBLE, not merely thin")
    print("  ES/MES same index, NQ/MNQ same index => 2 markets, not 4")
    print("  ETF stores SPY/QQQ/IWM/DIA  : 2016-01 .. 2026-09, ~2,600 sessions each")
    print("  => the ETF panel is the only source of independent history\n")

    rows = []
    store: dict = {}

    for panel, syms, loader in (("futures", ("MNQ", "NQ", "MES", "ES"), futures_sessions),
                                ("etf", ("SPY", "QQQ", "IWM", "DIA"), etf_sessions)):
        for sym in syms:
            sess = loader(sym)
            if not sess:
                continue
            feats = build(sess)
            n_train = int(len(sess) * TRAIN_FRACTION)
            hi, lo = calibrate_thresholds(feats, n_train)
            mult = (inst.get(sym).spec.multiplier if panel == "futures"
                    else ETF_SPECS[sym]["multiplier"])
            recs, per_sess = collect(sess, feats, hi, lo, mult)
            store[(panel, sym)] = (recs, per_sess, sess, feats, hi, lo, mult)
            ctrl = matched_control(recs, per_sess, mult, rng)
            row = summarise(recs, ctrl, rng, "ALL", sym, panel)
            row["hi"], row["lo"] = hi, lo
            row["verdict"] = classify(row)
            rows.append(row)
            print(f"  {panel:8} {sym:5} {len(recs):6d} entries over "
                  f"{row['sessions']:5d} sessions   thresholds {hi:+.3f}/{lo:+.3f}   "
                  f"{row['verdict']}")

    df = pd.DataFrame(rows)
    df.to_csv(REPO / "research" / "fr_replication_instruments.csv", index=False)

    print("\n" + "=" * 112)
    print("PHASE 2 - CROSS-INSTRUMENT REPLICATION  (signed forward return, $ per unit)")
    print("=" * 112)
    print(f"  {'panel':8} {'sym':5} {'n':>6} " + "".join(f"{str(n) + 'b':>16}" for n in
                                                         (1, 3, 5, 10)) + "  verdict")
    for _, r in df.iterrows():
        cells = "".join(f"{r[f'mean_{n}']:+8.3f}({r[f't_{n}']:+4.1f})" for n in (1, 3, 5, 10))
        print(f"  {r['panel']:8} {r['symbol']:5} {int(r.entries):6d} {cells}  {r.verdict}")

    print(f"\n  {'panel':8} {'sym':5} " + "".join(f"{'ctl%' + str(n) + 'b':>10}"
                                                  for n in (1, 3, 5, 10))
          + f"{'boot CI @1b':>22}")
    for _, r in df.iterrows():
        cells = "".join(f"{r[f'ctrl_pctile_{n}']:10.1%}" for n in (1, 3, 5, 10))
        print(f"  {r['panel']:8} {r['symbol']:5} {cells}"
              f"    [{r['ci_lo_1']:+.3f}, {r['ci_hi_1']:+.3f}]")

    print("\n" + "=" * 112)
    print("PHASE 6 - SHORT-HORIZON DECAY: does the 1->3->5 rise and ~10 decay replicate?")
    print("=" * 112)
    print(f"  {'panel':8} {'sym':5} " + "".join(f"{str(n) + 'b':>9}" for n in HORIZONS)
          + "   shape")
    for _, r in df.iterrows():
        vals = [r[f"mean_{n}"] for n in HORIZONS]
        cells = "".join(f"{v:9.3f}" for v in vals)
        early = np.nanmean([r["mean_1"], r["mean_3"], r["mean_5"]])
        late = np.nanmean([r["mean_10"], r["mean_15"], r["mean_30"]])
        shape = ("early>late (consistent)" if np.isfinite(early) and np.isfinite(late)
                 and early > late else "NOT the claimed shape")
        print(f"  {r['panel']:8} {r['symbol']:5} {cells}   {shape}")

    print("\n" + "=" * 112)
    print("PHASE 5 - NEGATIVE CONTROL: shuffled direction labels")
    print("=" * 112)
    print("  The same entry bars with direction permuted. A real directional effect must die.")
    print(f"  {'panel':8} {'sym':5} {'real 1b':>10} {'shuffled median':>17} "
          f"{'real pctile':>12}")
    for (panel, sym), (recs, per_sess, *_rest) in store.items():
        if len(recs) < MIN_ENTRIES:
            continue
        mult = _rest[-1]
        sh = matched_control(recs, per_sess, mult, rng, n_reps=100, shuffle_direction=True)
        cm = np.array(sh.get(1, []), dtype=float)
        real = float(recs["fwd_1"].mean())
        pct = float((cm < real).mean()) if len(cm) else np.nan
        print(f"  {panel:8} {sym:5} {real:10.3f} {np.median(cm):17.3f} {pct:12.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
