"""F-15: a DIFFERENT STORE. The gate first, the fit second - and only on what survives the gate.

F-14 closed the feature-set axis with a sentence and a rule. The sentence: every one of the seven
axes this track has priced ran on `sweep_f1.FEATURES`, 38 deterministic transforms of 5-minute
OHLCV, so *"this panel does not support a t = 2 book"*. The rule, F-14 (a): **check a candidate
column's univariate IC and its correlation against the incumbent set BEFORE fitting anything** - a
column that is >= 0.5 correlated with an incumbent and has a *smaller* |IC| is not a new signal, it
is a measurement error on an old one, and a tree will spend budget on it and lose.

F-15 is the first F iteration to go outside the trade-bar store, and the first to make the gate the
PRIMARY deliverable rather than a post-run diagnostic. Two channels, both of which exist without a
new subscription, and neither of which can be computed from 5-minute OHLCV at any width:

  A. THE AUCTION TAPE, per name.  `/v2/stocks/auctions` (Alpaca SIP, 2016+, one request per
     symbol) returns the official opening and closing CROSS - price, size and venue - which is a
     single batch print struck by an imbalance mechanism, not a trade bar. Two things live in it
     that the tape cannot say: the SIZE of the cross (how much stock the open/close actually
     had to clear, i.e. index/rebalance/MOC flow) and the GAP BETWEEN THE CROSS PRINT AND THE
     CONTINUOUS TAPE around it (how far the auction had to reach to clear, i.e. the direction of
     the imbalance it absorbed). F-14's proxies were all continuous-session; this is the one
     moment of the day when the whole book is visible at one price.

  B. THE 0DTE OPTION CHAIN, market-level.  `data/options/odte/SPY` - 1,891 same-day expirations
     2016-2026 at 5-minute bid/ask, both rights, +/-30 strikes, already local. The ATM straddle
     priced against spot IS the market's forecast of |move to today's close|, in bps, at the
     decision minute. No trade bar contains a forecast. It is SPY-level, so it has no
     cross-sectional variation and the F-14 gate cannot screen it (see clause 3b).

Not attempted, and why: **per-name implied skew, F-15's own pre-registered favourite, is BLOCKED.**
The Theta Terminal answers `listening: true` but every history and quote endpoint returns
HTTP 403 - *"Requesting an option endpoint requiring a value subscription, but you only have a
FREE subscription"*. The local 0DTE SPY store predates the lapse and still reads. This is ALREADY
an open item in `research/BLOCKERS.md` (O-3, re-diagnosed by O-4 on 2026-09-12); F-15 adds a second
track waiting on it and does not re-file it.

PRE-REGISTERED CLAUSES (written before a number was read; clause 0 is the prior).

0. THE PRIOR.  The auction family is the more likely of the two to carry, but not by much. I
   expect `auc_ojump` to be ~0.9 correlated with `gap` and to be DROPPED by the gate, which is the
   gate working. I expect the closing-cross drift `auc_cdrift` and the cross-size surprises to
   survive the gate (correlation < 0.3 against the 38) and to have univariate |IC| of 0.002-0.006 -
   real but a third of `vwap_atr`'s 0.0113. I expect the fitted `both` arm to land within +/-$120
   of base's $306/day with t between +1.3 and +1.7, and to be REFUSED on clause 5. I expect the
   0DTE straddle to correlate ~0.6-0.75 with trailing realised vol and to add nothing the realised
   regime split did not already have.

1. IDENTITY AND SAMPLE.  Alt columns are MERGED, never inner-joined; uncovered rows are kept
   carrying NaN (LightGBM handles NaN natively) so every arm is read at F-8's exact row set. The
   `base` arm must reproduce F-8/F-12/F-14's frozen numbers to the printed digit: mean rank IC
   +0.01030, gross 4.256 bps, cost 2.724 bps, net $305.7/day, t +1.474, 1,933 sessions.

2. CAUSALITY.  For a decision on the 5-minute bar STARTING at T, nothing may read past T+4 (the
   last minute of the decision bar), which is F-14's window exactly.
     - day D's OPENING cross is struck at 09:30 and the first decision is 09:55: known.
     - day D-1's CLOSING cross is struck at 16:00 the previous session: known.
     - trailing medians/scales use sessions <= D-1 only.
     - the 0DTE chain is read at the 5-minute bar STARTING at T-5, i.e. the bar that CLOSED at T.
       The chain bar labelled T is not read at all, because a 5-minute bid/ask bar carries the
       last quote in [T, T+5) and that is 1 minute past the allowance.

3. THE GATE, which is the primary deliverable and runs BEFORE any fit.
   (a) CROSS-SECTIONAL CHANNEL (family A).  Per-timestamp rank IC against `y_close` over the test
       window, and max |Spearman| against each of the 38 incumbents (median over timestamps).
       DROP any candidate that is >= 0.50 correlated with an incumbent whose |IC| is larger.
       This is F-14 (a), applied as a rule rather than as a lesson.
   (b) MARKET-LEVEL CHANNEL (family B).  A SPY-level column is constant across names at a
       timestamp, so its per-timestamp rank IC is 0 BY CONSTRUCTION and (a) cannot screen it. It
       is screened instead on the quantity it could actually move: the correlation of the column
       with the BOOK'S OWN daily net P&L (F-8's frozen book), and its correlation with the
       realised-vol regime already in use. A column that is >= 0.7 correlated with trailing
       realised vol is a slower copy of the regime split and is DROPPED.

4. THE FIT, on survivors only. Arms at constant everything else - same `GRID["mid"]` learner, same
   seed, same expanding walk-forward, same label `y_close`, same 8 test years, NO hyperparameter
   search: `base` (38), `alt` (survivors), `both` (38 + survivors), and `both_scrambled` - F-14 (b)
   is now standing procedure, so the added columns are permuted WITHIN each timestamp, preserving
   every marginal and the cross-sectional dispersion and destroying only the name attached.

5. THE HURDLE, unchanged since F-8: `both` is adopted only on net t > 2.0 pooled AND >= 5 of 8 test
   years positive AND a positive paired `both - base` at t > 2.0. Anything else is REFUSED.

6. TURNOVER CONTROL.  Every arm runs one decision, decile 0.10, in and out, so turnover must be
   equal across arms to the dollar; the bps columns are like-for-like only if it is, and the run
   prints the spread.

7. FEATURE-IMPORTANCE STABILITY, the brief's second criterion. Permutation importance on each
   retrain's validation year: the share of positive importance the alt family takes, the mean
   pairwise Spearman of the yearly rankings, and which columns are in every year's top 10.
   F-14's benchmark: the 38-feature return model is +0.434 and adding a redundant family took it
   to +0.036.

Usage:
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f15.py --fetch   # 57 requests, skips
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f15.py --build ab #   names already got
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f15.py --gate
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f15.py --fit --record
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f15.py --books --record
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f15.py --post     # post-run diagnostics
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f15.py --lean     # post-run, then --books
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
import intraday_common as ic  # noqa: E402
import sweep_f1 as f1  # noqa: E402
import ml_f8 as f8  # noqa: E402
import ml_f14 as f14  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
OUT = REPO / "data" / "f1"
AUCT = OUT / "f15_auctions"
ALT = OUT / "f15_alt.parquet"
PREDS = OUT / "f15_preds.parquet"
CELLS = OUT / "f15_arms.csv"
GATE = OUT / "f15_gate.csv"
IMP = OUT / "importance_f15.csv"
ODTE = REPO / "data" / "options" / "odte" / "SPY"

AUCT_URL = "https://data.alpaca.markets/v2/stocks/auctions"

LABEL = "close"
EQUITY = f8.EQUITY
N_SLOTS = f8.N_SLOTS
DECILE = f8.DECILE
EPS = 1e-12

#: family A - the auction tape, per name.
AUC_OWN = ["auc_osz_z", "auc_osz_adv", "auc_ofade", "auc_ojump", "auc_csz_z", "auc_cdrift"]
AUC_MKT = ["m_auc_osz_z", "m_auc_cdrift"]
AUC_RESID = ["x_auc_cdrift", "x_auc_ofade"]
AUC_RANK_OF = ["auc_osz_z", "auc_ofade", "auc_cdrift", "auc_csz_z"]
AUC_RANK = [f"cs_{c}" for c in AUC_RANK_OF]
FAM_A = AUC_OWN + AUC_MKT + AUC_RESID + AUC_RANK

#: family B - the 0DTE chain, market-level.
FAM_B = ["iv_strad", "iv_skew", "iv_rvgap", "iv_d30", "iv_qi"]

ALT_FEATS = FAM_A + FAM_B


# --------------------------------------------------------------- clause A: fetch the auction tape


def panel_symbols() -> list[str]:
    """The F-panel's OWN universe - 56 names, not the 16-name intraday sleeve.

    `sweep_f1` builds its panel from every symbol in the Alpaca store minus `f1.EXCLUDE`, so the
    cross-sectional book ranks over 56 names. An alt family built on `ic.UNIVERSE` would cover
    27% of the rows and, worse, its `cs_*` ranks would be computed over a different, narrower
    cross-section than the one the book trades.
    """
    return sorted(pd.read_parquet(f1.PANEL, columns=["sym"])["sym"].unique().tolist())


def fetch_auctions(start: str = "2015-12-01", end: str | None = None) -> None:
    """One request (plus pages) per tradable name. Reuses S-24's paging and cross picker read-only."""
    import sweep_s24 as s24                                            # noqa: PLC0415

    AUCT.mkdir(parents=True, exist_ok=True)
    # the free SIP entitlement refuses "recent" data, so stop where the minute store stops
    end = end or (dt.date.today() - dt.timedelta(days=2)).isoformat()
    h = s24.headers()
    for s in panel_symbols() + [f1.MARKET]:
        if (AUCT / f"{s}.parquet").exists():
            continue
        rows, token = [], None
        while True:
            q = {"symbols": s, "start": start, "end": end, "feed": "sip", "limit": 10000}
            if token:
                q["page_token"] = token
            data = s24.get(AUCT_URL, q, h)
            for d in data.get("auctions", {}).get(s, []):
                op, osz, _ = s24._pick(d.get("o"))
                cp, csz, _ = s24._pick(d.get("c"))
                rows.append({"date": d["d"], "open_px": op, "open_sz": osz,
                             "close_px": cp, "close_sz": csz})
            token = data.get("next_page_token")
            if not token:
                break
            time.sleep(0.35)
        if not rows:
            print(f"  {s}: no auctions returned", flush=True)
            continue
        df = pd.DataFrame(rows).drop_duplicates("date").set_index("date").sort_index()
        df.to_parquet(AUCT / f"{s}.parquet")
        print(f"  {s}: {len(df):,} auction days {df.index[0]} .. {df.index[-1]}", flush=True)
        time.sleep(0.2)


# ------------------------------------------------------------- clause 2: family A, per-name daily


def auction_daily(sym: str) -> pd.DataFrame:
    """Per-session auction features for `sym`, indexed by session date (a python date).

    Everything here is known by 09:35 of the session it is stamped on (clause 2): day D's opening
    cross (09:30), day D's 09:30-09:34 continuous tape, day D-1's closing cross (16:00) and day
    D-1's last continuous bar. Trailing medians use sessions <= D-1.
    """
    p = AUCT / f"{sym}.parquet"
    if not p.exists():
        return pd.DataFrame()
    a = pd.read_parquet(p)
    a.index = pd.to_datetime(a.index).date

    bars = ic.load_bars(sym)
    if bars.empty:
        return pd.DataFrame()
    day = pd.Index(bars.index.date)
    mins = (bars.index.hour - 9) * 60 + bars.index.minute - 30

    # session aggregates from the continuous tape
    dvol = bars["v"].groupby(day).sum()
    last_c = bars["c"].groupby(day).last()
    # the close of the 09:34 bar = the first five minutes of continuous trading
    early = bars["c"][(mins >= 0) & (mins <= 4)].groupby(day[(mins >= 0) & (mins <= 4)]).last()

    d = pd.DataFrame(index=last_c.index)
    d = d.join(a[["open_px", "open_sz", "close_px", "close_sz"]], how="left")
    d["dvol"] = dvol
    d["last_c"] = last_c
    d["early_c"] = early

    # trailing scale: 20-session close-to-close vol in bps, shifted so today reads yesterday
    r = np.log(d["last_c"] / d["last_c"].shift(1))
    scale = (r.rolling(20, min_periods=10).std().shift(1) * 1e4).replace(0.0, np.nan)

    osz_med = d["open_sz"].rolling(20, min_periods=10).median().shift(1)
    csz_med = d["close_sz"].rolling(20, min_periods=10).median().shift(1)
    dvol_med = d["dvol"].rolling(20, min_periods=10).median().shift(1)

    out = pd.DataFrame(index=d.index)
    # size surprise of today's opening cross, and its share of a normal day's volume
    out["auc_osz_z"] = np.log((d["open_sz"] + 1.0) / (osz_med + 1.0))
    out["auc_osz_adv"] = d["open_sz"] / dvol_med
    # how far the first five minutes of tape travelled away from the cross print, in vol units
    out["auc_ofade"] = 1e4 * (d["early_c"] / d["open_px"] - 1.0) / scale
    # auction-to-auction overnight jump, in vol units (expected >= 0.5 correlated with `gap`)
    out["auc_ojump"] = 1e4 * (d["open_px"] / d["close_px"].shift(1) - 1.0) / scale
    # yesterday's closing cross: how big it was, and how far it reached from the last tape print
    out["auc_csz_z"] = np.log((d["close_sz"].shift(1) + 1.0) / (csz_med.shift(1) + 1.0))
    out["auc_cdrift"] = 1e4 * (d["close_px"].shift(1) / d["last_c"].shift(1) - 1.0) / scale
    return out.replace([np.inf, -np.inf], np.nan)


def build_family_a() -> pd.DataFrame:
    """Family A at every (session, symbol); broadcast to the 11 decision slots at merge time."""
    syms = panel_symbols()
    mkt = auction_daily(f1.MARKET)
    if mkt.empty:
        raise SystemExit(f"no auction store for {f1.MARKET}; run --fetch first")
    m = mkt[["auc_osz_z", "auc_cdrift"]].copy()
    m.columns = AUC_MKT
    m["m_auc_ofade"] = mkt["auc_ofade"]

    rows = []
    for i, s in enumerate(syms, 1):
        d = auction_daily(s)
        if d.empty:
            print(f"  [{i:>2}/{len(syms)}] {s:<6} skipped (no auction store)")
            continue
        d = d.join(m, how="left")
        d["sym"] = s
        rows.append(d.reset_index().rename(columns={"index": "day"}))
        print(f"  [{i:>2}/{len(syms)}] {s:<6} {len(d):>6,} sessions, "
              f"cdrift coverage {100 * d['auc_cdrift'].notna().mean():.1f}%")
    fam = pd.concat(rows, ignore_index=True)
    fam["x_auc_cdrift"] = fam["auc_cdrift"] - fam["m_auc_cdrift"]
    fam["x_auc_ofade"] = fam["auc_ofade"] - fam["m_auc_ofade"]

    g = fam.groupby("day", sort=False)
    for c in AUC_RANK_OF:
        fam[f"cs_{c}"] = g[c].rank(pct=True)
    fam = fam.drop(columns=["m_auc_ofade"])
    return fam[["day", "sym"] + FAM_A]


# ------------------------------------------------------- clause 2: family B, the 0DTE chain, SPY


def _chain_features(path: Path, spot: pd.Series) -> pd.DataFrame:
    """ATM straddle, 1%-wing skew and quoted-size imbalance at every 5-minute chain bar.

    `spot` is SPY's 1-minute close indexed by ET minute for this session. The straddle is priced
    at the strike nearest spot; the wings at the strikes nearest spot*(1 -/+ 0.01). Every price is
    the bid/ask MID of the chain bar, and a bar with a zero bid on either leg is dropped rather
    than carried at half the ask.
    """
    ch = pd.read_parquet(path)
    if ch.empty:
        return pd.DataFrame()
    ch = ch[(ch["bid"] > 0) & (ch["ask"] > 0)]
    if ch.empty:
        return pd.DataFrame()
    ch["mid"] = 0.5 * (ch["bid"] + ch["ask"])
    ch["qsz"] = ch["bid_size"].astype("float64") + ch["ask_size"].astype("float64")
    ts = pd.to_datetime(ch["timestamp"])
    ch["ts"] = ts

    px = spot.reindex(ts.dt.floor("min").to_numpy()).to_numpy()
    ch["spot"] = px
    ch = ch[np.isfinite(ch["spot"])]
    if ch.empty:
        return pd.DataFrame()

    out = []
    for t, g in ch.groupby("ts", sort=True):
        s = float(g["spot"].iat[0])
        ks = np.unique(g["strike"].to_numpy())
        if len(ks) < 5:
            continue
        k_atm = ks[np.argmin(np.abs(ks - s))]
        k_dn = ks[np.argmin(np.abs(ks - s * 0.99))]
        k_up = ks[np.argmin(np.abs(ks - s * 1.01))]
        piv = g.pivot_table(index="strike", columns="right", values="mid", aggfunc="last")
        qz = g.pivot_table(index="strike", columns="right", values="qsz", aggfunc="last")
        if "C" not in piv.columns or "P" not in piv.columns:
            continue
        try:
            strad = float(piv.at[k_atm, "C"]) + float(piv.at[k_atm, "P"])
            p_dn = float(piv.at[k_dn, "P"])
            c_up = float(piv.at[k_up, "C"])
            qc = float(qz.at[k_up, "C"])
            qp = float(qz.at[k_dn, "P"])
        except (KeyError, TypeError):
            continue
        if not np.isfinite(strad) or strad <= 0:
            continue
        out.append({"ts": t, "iv_strad": 1e4 * strad / s,
                    "iv_skew": (p_dn - c_up) / strad,
                    "iv_qi": (qc - qp) / (qc + qp + 1.0)})
    return pd.DataFrame(out)


def build_family_b() -> pd.DataFrame:
    """Family B at the 11 decision slots, read one 5-minute bar BEHIND the decision (clause 2)."""
    files = sorted(ODTE.glob("*.parquet"))
    if not files:
        raise SystemExit(f"no 0DTE store at {ODTE}")
    mkt = ic.load_bars(f1.MARKET)
    spot_all = mkt["c"]
    spot_all.index = spot_all.index.tz_localize(None)
    by_day = {d: g for d, g in spot_all.groupby(spot_all.index.normalize())}

    # realised, time-of-day matched: SPY's trailing 20-session |close - price at T| in bps
    mins = (mkt.index.hour - 9) * 60 + mkt.index.minute - 30
    day = pd.Index(mkt.index.date)
    last_c = mkt["c"].groupby(day).last()
    wanted = [f1.FIRST_DECISION + f1.STEP * f1.BAR * k for k in range(f1.N_DECISIONS)]
    rv = {}
    for k, mo in enumerate(wanted):
        m = mins == mo
        px = mkt["c"][m].groupby(day[m]).last()
        mv = (1e4 * (last_c.reindex(px.index) / px - 1.0)).abs()
        rv[k] = mv.rolling(20, min_periods=10).mean().shift(1)

    rows = []
    for i, p in enumerate(files, 1):
        d = pd.Timestamp(p.stem)
        sp = by_day.get(d)
        if sp is None:
            continue
        f = _chain_features(p, sp)
        if f.empty:
            continue
        f = f.set_index("ts").sort_index()
        f["iv_d30"] = f["iv_strad"] - f["iv_strad"].shift(6)
        mo = (f.index.hour - 9) * 60 + f.index.minute - 30
        for k, want in enumerate(wanted):
            sel = f[mo == want - f1.BAR]              # the bar that CLOSED at the decision minute
            if sel.empty:
                continue
            r = sel.iloc[-1]
            base = rv[k].get(d.date(), np.nan)
            rows.append({"day": d.date(), "slot": k,
                         "iv_strad": float(r["iv_strad"]), "iv_skew": float(r["iv_skew"]),
                         "iv_qi": float(r["iv_qi"]), "iv_d30": float(r["iv_d30"]),
                         "iv_rvgap": float(np.log(max(r["iv_strad"], EPS) / base))
                         if np.isfinite(base) and base > 0 else np.nan})
        if i % 250 == 0:
            print(f"  [{i:>4}/{len(files)}] {p.stem}  {len(rows):,} slot-rows", flush=True)
    return pd.DataFrame(rows)


def build(fams: str = "ab") -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if "a" in fams:
        print("=== family A: the auction tape, per name")
        a = build_family_a()
        print(f"  {len(a):,} (session, symbol) rows over {a['sym'].nunique()} symbols")
        a.to_parquet(OUT / "f15_famA.parquet", index=False)
    if "b" in fams:
        print("=== family B: the SPY 0DTE chain, market-level")
        b = build_family_b()
        print(f"  {len(b):,} (session, slot) rows over {b['day'].nunique():,} sessions")
        b.to_parquet(OUT / "f15_famB.parquet", index=False)
    print("written: " + ", ".join(str(OUT / f"f15_fam{f.upper()}.parquet") for f in fams))


# ------------------------------------------------------------------------------ the merged panel


def load_panel(scramble: int | None = None, cols: list[str] | None = None) -> pd.DataFrame:
    """F-8's labelled panel with both alt families MERGED ON (clause 1: never inner-joined)."""
    f1.check_panel_fresh()          # F-19: a stale cache is invisible to an identity check
    panel = pd.read_parquet(f1.PANEL)
    p = f8.add_labels(panel)
    del panel
    a = pd.read_parquet(OUT / "f15_famA.parquet")
    b = pd.read_parquet(OUT / "f15_famB.parquet")
    p["_day"] = pd.to_datetime(p["ts"]).dt.date
    a["day"] = pd.to_datetime(a["day"]).dt.date
    b["day"] = pd.to_datetime(b["day"]).dt.date

    n0 = len(p)
    p = p.merge(a.rename(columns={"day": "_day"}), on=["_day", "sym"], how="left")
    p = p.merge(b.rename(columns={"day": "_day"}), on=["_day", "slot"], how="left")
    assert len(p) == n0, "the alt merge duplicated rows"
    for c in ALT_FEATS:
        p[c] = p[c].astype("float32")
    print(f"panel {len(p):,} rows; family A coverage "
          f"{100 * p['auc_cdrift'].notna().mean():.2f}%, family B coverage "
          f"{100 * p['iv_strad'].notna().mean():.2f}% "
          f"(uncovered rows carry NaN and are KEPT, clause 1)")
    if scramble is not None:
        rng = np.random.default_rng(scramble)
        tgt = cols or ALT_FEATS
        print(f"clause 4 control: permuting {len(tgt)} alt columns within each timestamp")
        for c in tgt:
            p[c] = (p.groupby("ts", sort=False)[c]
                    .transform(lambda s: rng.permutation(s.to_numpy())).astype("float32"))
    return p


# -------------------------------------------------------------------- clause 3: THE GATE, no fit


def _per_ts_spearman(df: pd.DataFrame, a: str, b: str) -> np.ndarray:
    """Per-timestamp Spearman of `a` against `b`, vectorised (no groupby.apply).

    Ranks within each timestamp, then forms the correlation from the demeaned rank products.
    Timestamps with fewer than 3 jointly non-null names are dropped, since a rank correlation
    on two points is +/-1 by construction and would dominate the mean.
    """
    s = df[["ts", a, b]].dropna()
    if s.empty:
        return np.empty(0)
    g = s.groupby("ts", sort=False)
    s = s.assign(ra=g[a].rank(), rb=g[b].rank())
    g = s.groupby("ts", sort=False)
    s = s[g["ra"].transform("size").to_numpy() >= 3]
    if s.empty:
        return np.empty(0)
    g = s.groupby("ts", sort=False)
    da = s["ra"] - g["ra"].transform("mean")
    db = s["rb"] - g["rb"].transform("mean")
    ts = s["ts"]
    num = (da * db).groupby(ts, sort=False).sum()
    den = np.sqrt((da * da).groupby(ts, sort=False).sum()
                  * (db * db).groupby(ts, sort=False).sum())
    r = (num / den).replace([np.inf, -np.inf], np.nan).dropna()
    return r.to_numpy()


def gate() -> pd.DataFrame:
    """Univariate IC and max |Spearman| against the 38, on the TEST window, before any fit."""
    p = load_panel()
    p = p.dropna(subset=["y_close"]).copy()
    p = p[p["year"] >= f8.FIRST_TEST_YEAR]
    print(f"gate sample: {len(p):,} rows, {p['day'].nunique():,} sessions, "
          f"{p['year'].min()}-{p['year'].max()}")

    inc = list(f1.FEATURES)

    def ic_of(col: str) -> tuple[float, float]:
        per = _per_ts_spearman(p, col, "y_close")
        if len(per) < 30:
            return float("nan"), float("nan")
        return float(per.mean()), f1.tstat(per)

    print("\n--- incumbent reference ICs (the bar a candidate has to clear)")
    inc_ic = {}
    for c in inc:
        m, t = ic_of(c)
        inc_ic[c] = m
        if abs(m) > 0.008:
            print(f"  {c:<14} IC {m:+.5f} (t {t:+.1f})", flush=True)

    # median per-timestamp |Spearman| of each candidate against each incumbent
    sample_ts = pd.Index(sorted(p["ts"].unique()))
    sample_ts = sample_ts[:: max(1, len(sample_ts) // 600)]
    q = p[p["ts"].isin(sample_ts)]

    # a column with no cross-sectional variation cannot be screened by clause 3a at all - its
    # per-timestamp rank IC is undefined, not zero. Route it to 3b with the rest of the
    # market-level channel rather than letting it pass 3a by default.
    xsec = p.groupby("ts", sort=False)[ALT_FEATS].std(numeric_only=True).mean()
    mkt_level = [c for c in ALT_FEATS if not np.isfinite(xsec.get(c, np.nan))
                 or xsec.get(c, 0.0) < 1e-9]
    print(f"\nmarket-level (no cross-sectional variation, screened under 3b): {mkt_level}")

    rows = []
    for c in ALT_FEATS:
        m, t = ic_of(c)
        fam = "A" if c in FAM_A else "B"
        if fam == "B" or c in mkt_level:
            rows.append({"feature": c, "family": "B" if fam == "B" else "A-mkt",
                         "ic": m, "ic_t": t,
                         "max_corr": np.nan, "vs": "", "verdict": "see clause 3b"})
            continue
        best_c, best_n = 0.0, ""
        for j in inc:
            cs = _per_ts_spearman(q, c, j)
            v = float(np.nanmedian(np.abs(cs))) if len(cs) else np.nan
            if np.isfinite(v) and v > best_c:
                best_c, best_n = v, j
        drop = bool(best_c >= 0.50 and abs(inc_ic.get(best_n, 0.0)) >= abs(m))
        rows.append({"feature": c, "family": fam, "ic": m, "ic_t": t,
                     "max_corr": best_c, "vs": best_n,
                     "verdict": "DROP" if drop else "keep"})
        print(f"  {c:<16} IC {m:+.5f} (t {t:+5.1f})  max|rho| {best_c:.3f} vs {best_n:<12} "
              f"(its IC {inc_ic.get(best_n, float('nan')):+.5f})  "
              f"[{'DROP' if drop else 'keep'}]", flush=True)

    g = pd.DataFrame(rows)

    # clause 3b: the market-level channel, screened on what it could actually move
    print("\n--- clause 3b: the market-level family, screened on the regime instead")
    reg = f14.market_regime()
    mkt = ic.load_bars(f1.MARKET)
    dayi = pd.Index(mkt.index.date)
    close = mkt["c"].groupby(dayi).last()
    rvol = np.log(close / close.shift(1)).rolling(20, min_periods=10).std().shift(1)
    rvol.index = pd.Index([str(d) for d in rvol.index])

    b = pd.read_parquet(OUT / "f15_famB.parquet")
    b["dstr"] = b["day"].astype(str)
    daily = b[b["slot"] == 5].set_index("dstr")
    spy = auction_daily(f1.MARKET)
    spy.index = pd.Index([str(d) for d in spy.index])
    daily = daily.join(spy[["auc_osz_z", "auc_cdrift"]]
                       .rename(columns={"auc_osz_z": "m_auc_osz_z",
                                        "auc_cdrift": "m_auc_cdrift"}), how="outer")
    for c in list(dict.fromkeys(FAM_B + mkt_level)):
        x = daily[c].astype(float)
        j = pd.concat([x, rvol.rename("rvol")], axis=1).dropna()
        r = float(j[c].corr(j["rvol"], method="spearman")) if len(j) > 50 else float("nan")
        drop = bool(np.isfinite(r) and abs(r) >= 0.70)
        g.loc[g["feature"] == c, "max_corr"] = abs(r)
        g.loc[g["feature"] == c, "vs"] = "rvol20(SPY)"
        g.loc[g["feature"] == c, "verdict"] = "DROP" if drop else "keep"
        print(f"  {c:<16} rho vs trailing realised vol {r:+.3f}  n {len(j):,} "
              f"[{'DROP' if drop else 'keep'}]")
    del reg

    GATE.parent.mkdir(parents=True, exist_ok=True)
    g.to_csv(GATE, index=False)
    keep = g[g["verdict"] == "keep"]["feature"].tolist()
    print(f"\n=== GATE RESULT: {len(keep)}/{len(ALT_FEATS)} survive -> {keep}")
    print(f"written: {GATE}")
    return g


def survivors() -> list[str]:
    if not GATE.exists():
        raise SystemExit("run --gate first")
    g = pd.read_csv(GATE)
    return g[g["verdict"] == "keep"]["feature"].tolist()


# ----------------------------------------------------------------------------- clause 4: the fit


def fit(record_rows: bool = False) -> None:
    keep = survivors()
    if not keep:
        print("no candidate survived the gate; nothing to fit (this IS the result)")
        return
    arms = {"base": list(f1.FEATURES), "alt": keep, "both": list(f1.FEATURES) + keep}
    params = dict(f1.GRID["mid"])

    frames, ics, models = [], [], {}
    for scr in (None, 0):
        p = load_panel(scramble=scr, cols=keep)
        p = p.dropna(subset=["y_close"]).copy()
        p["y"] = p["y_close"]
        years = [y for y in sorted(p["year"].unique()) if y >= f8.FIRST_TEST_YEAR]
        todo = list(arms) if scr is None else ["both"]
        saved = list(f1.FEATURES)
        try:
            for arm in todo:
                name = arm if scr is None else "both_scrambled"
                f1.FEATURES = arms[arm]
                print(f"\n--- arm {name}: {len(arms[arm])} features")
                for year in years:
                    trn, vld, tst = p[p.year <= year - 2], p[p.year == year - 1], p[p.year == year]
                    if not (len(trn) and len(vld) and len(tst)):
                        continue
                    t0 = time.time()
                    model, pt = f1.fit_predict(trn, vld, tst, dict(params))
                    icm, ict = f1.ic_stats(tst, pt)
                    ics.append({"arm": name, "year": int(year), "ic": icm, "ic_t": ict})
                    k = tst[["ts", "day", "year", "sym", "slot", "entry_px", "fwd"]].copy()
                    k["arm"] = name
                    k["pred"] = pt
                    frames.append(k)
                    if scr is None and arm == "both":
                        models[(name, int(year))] = (model, vld, arms[arm])
                    print(f"  {year}: train<={year-2} ({len(trn):,}) test ({len(tst):,}) "
                          f"iters {model.n_iter_:>4}  rank IC {icm:+.5f} (t {ict:+.1f})  "
                          f"({time.time()-t0:.0f}s)", flush=True)
        finally:
            f1.FEATURES = saved
        del p

    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(PREDS, index=False)
    icd = pd.DataFrame(ics)
    print("\n=== per-timestamp rank IC on y_close, by arm and test year ===")
    piv = icd.pivot(index="year", columns="arm", values="ic")
    print(piv.round(5).to_string())
    print("\nmean " + "  ".join(f"{a} {piv[a].mean():+.5f}" for a in piv.columns))
    if models:
        _importance(models, keep)
    print(f"\nwritten: {PREDS}")
    del record_rows


def _importance(models: dict, keep: list[str]) -> None:
    from sklearn.inspection import permutation_importance                # noqa: PLC0415
    print("\n=== clause 7: permutation importance on each retrain's validation year ===")
    rows = []
    for (arm, year), (model, vld, feats) in sorted(models.items()):
        s = vld.sample(min(120_000, len(vld)), random_state=0)
        r = permutation_importance(model, s[feats].to_numpy(dtype=np.float32),
                                   s["y"].to_numpy() * 1e4, n_repeats=3, random_state=0,
                                   scoring="neg_mean_squared_error", n_jobs=1)
        imp = pd.Series(r.importances_mean, index=feats)
        for k, v in imp.items():
            rows.append({"arm": arm, "year": year, "feature": k, "imp": float(v)})
        tot = imp.clip(lower=0).sum()
        al = imp.reindex(keep).clip(lower=0).sum()
        print(f"  {arm:<6} {year}: alt family carries "
              f"{100 * al / tot if tot > 0 else float('nan'):>5.1f}% of positive importance; "
              f"top 5 {', '.join(imp.sort_values(ascending=False).head(5).index)}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(IMP, index=False)
    for arm, sub in df.groupby("arm"):
        piv = sub.pivot(index="feature", columns="year", values="imp")
        ranks = piv.rank(ascending=False)
        cors = [ranks[a].corr(ranks[b], method="spearman")
                for i, a in enumerate(ranks.columns) for b in ranks.columns[i + 1:]]
        top = {c: set(ranks[c].nsmallest(10).index) for c in ranks.columns}
        allyr = set.intersection(*top.values())
        print(f"\n  {arm}: mean pairwise Spearman of yearly importance ranks "
              f"{np.mean(cors):+.3f} ({min(cors):+.3f}..{max(cors):+.3f}); "
              f"in every year's top 10: {sorted(allyr) if allyr else 'none'}")
        print("         most persistent: " + ", ".join(
            f"{k} ({v:.1f})" for k, v in ranks.mean(axis=1).nsmallest(6).items()))
    print(f"\nwritten: {IMP}")


# --------------------------------------------------------------------------- clauses 5-6: books


def record(tag: str, r: dict, sess: pd.DataFrame, params: dict, extra: dict) -> None:
    net = sess["net"].to_numpy()
    n = len(sess)
    ret = net / EQUITY
    sd = ret.std(ddof=1) if n > 1 else 0.0
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "intraday/f15_altstore", "class": "ml", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-15", "params": params,
           "start": str(sess["day"].min()), "end": str(sess["day"].max()),
           "stats": {"Sessions": str(n),
                     "Avg Daily PnL": f"{net.mean():.0f}",
                     "t": f"{f1.tstat(net):.2f}",
                     "Gross Per Day": f"{sess['gross'].mean():.0f}",
                     "Costs Per Day": f"{sess['cost'].mean():.0f}",
                     "Turnover Per Day": f"{sess['turnover'].mean():.0f}",
                     "Gross Bps Per Turnover": f"{r['gross_bps']:.3f}",
                     "Cost Bps Per Turnover": f"{r['cost_bps']:.3f}",
                     "Edge Bps Per Turnover": f"{r['edge_bps']:.3f}",
                     "Worst Day": f"{net.min():.0f}",
                     "Win Rate": f"{100 * (net > 0).mean():.0f}%",
                     "Sharpe Ratio": f"{(ret.mean() / sd * np.sqrt(252)) if sd else float('nan'):.3f}",
                     "Diagnostic": "true",
                     **{k: str(v) for k, v in extra.items()}}}
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def books(record_rows: bool = False) -> None:
    preds = pd.read_parquet(PREDS)
    preds["ts"] = pd.to_datetime(preds["ts"])
    reg = f14.market_regime()
    arms = [a for a in ["base", "alt", "both", "both_scrambled", "lean3", "lean1"]
            if a in set(preds["arm"])]

    print(f"costed against {ic.DATA_DIR}  (_splits.json present: "
          f"{(ic.DATA_DIR / 'splits.json').exists() or (ic.DATA_DIR / '_splits.json').exists()})")

    sess, rows = {}, []
    for arm in arms:
        sess[arm] = f8.simulate(f14.frame_for(preds, arm), "session", decile=DECILE)
        rows.append(f8.summarize(sess[arm], f"session/{arm}"))

    print("\n=== clause 5: F-8's session book, one decision per session, held to the flatten ===")
    f8.print_table(rows)

    tv = pd.Series({a: sess[a]["turnover"].mean() for a in arms})
    print(f"\nclause 6: turnover spread across arms ${tv.max() - tv.min():,.0f} "
          f"(mean ${tv.mean():,.0f})")

    print("\n=== net $/day by test year ===")
    yr = pd.DataFrame({a: f14.by_year(sess[a]) for a in arms})
    print(yr.to_string())
    print("years positive: " + "  ".join(f"{a} {int((yr[a] > 0).sum())}/{len(yr)}" for a in arms))

    print("\n=== paired per session against base, decomposed ===")
    pairs = {}
    for arm in arms:
        if arm != "base":
            pairs[arm] = f14.paired(sess["base"], sess[arm], f"{arm} - base")

    print("\n=== regimes: terciles of SPY trailing 20-session realised vol ===")
    print(f"{'cell':<16}" + "".join(f"{k:>12}" for k in ("low", "mid", "high")))
    for arm in arms:
        s = sess[arm].copy()
        s["reg"] = s["day"].astype(str).map(reg)
        m = s.groupby("reg")["net"].mean()
        print(f"{arm:<16}" + "".join(f"{m.get(k, float('nan')):>12,.0f}"
                                     for k in ("low", "mid", "high")))

    lut = {x["label"]: x for x in rows}
    r, b = lut["session/both"], lut["session/base"]
    n_pos = int((yr["both"] > 0).sum())
    dp = pairs.get("both", {})
    ok = (r["t"] > 2.0) and (n_pos >= 5) and (dp.get("d_net_t", -9) > 2.0)
    print("\n=== clause 5: the pre-registered pass rule ===")
    print(f"  net t > 2.0                : {r['t']:+.3f}   {'PASS' if r['t'] > 2 else 'FAIL'}")
    print(f"  >= 5 of {len(yr)} years positive   : {n_pos}/{len(yr)}      "
          f"{'PASS' if n_pos >= 5 else 'FAIL'}")
    print(f"  paired both-base t > 2.0   : {dp.get('d_net_t', float('nan')):+.3f}   "
          f"{'PASS' if dp.get('d_net_t', -9) > 2 else 'FAIL'}")
    print(f"\nDECISION: {'ACCEPT' if ok else 'REFUSE'}  "
          f"(base t {b['t']:+.3f} -> both t {r['t']:+.3f})")

    CELLS.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(CELLS, index=False)
    if record_rows:
        keep = survivors()
        for x in rows:
            arm = x["label"].split("/")[1]
            record(f"F-15 {x['label']}: a DIFFERENT store (auction tape + 0DTE chain), "
                   f"gate-screened, on F-8's book",
                   x, sess[arm],
                   {"arm": arm, "label": LABEL, "decile": DECILE, "learner": "mid",
                    "n_alt": len(keep)},
                   {"Survivors": ";".join(keep),
                    "Paired vs base": json.dumps(pairs.get(arm, {}))})
        print(f"\nrecorded {len(rows)} DIAGNOSTIC rows -> {LEDGER}")
    print(f"cells -> {CELLS}")


LEAN_ARMS = {
    # POST-RUN, test-set-selected and therefore barred from clause 5: it cannot ACCEPT anything.
    # It exists to separate two explanations of `both`'s loss that clause 5 cannot tell apart -
    # "the auction tape carries nothing" against "19 columns carrying one signal dilute 38".
    "lean3": ["auc_ofade", "x_auc_ofade", "cs_auc_ofade"],
    "lean1": ["auc_ofade"],
}


def lean(record_rows: bool = False) -> None:
    """POST-RUN parsimony arms: the same fit with only the column that cleared the floor."""
    p = load_panel()
    p = p.dropna(subset=["y_close"]).copy()
    p["y"] = p["y_close"]
    years = [y for y in sorted(p["year"].unique()) if y >= f8.FIRST_TEST_YEAR]
    params = dict(f1.GRID["mid"])

    frames, ics = [], []
    saved = list(f1.FEATURES)
    try:
        for name, extra in LEAN_ARMS.items():
            f1.FEATURES = list(saved) + extra
            print(f"\n--- arm {name}: {len(f1.FEATURES)} features (+{extra})")
            for year in years:
                trn, vld, tst = p[p.year <= year - 2], p[p.year == year - 1], p[p.year == year]
                if not (len(trn) and len(vld) and len(tst)):
                    continue
                model, pt = f1.fit_predict(trn, vld, tst, dict(params))
                icm, ict = f1.ic_stats(tst, pt)
                ics.append({"arm": name, "year": int(year), "ic": icm})
                k = tst[["ts", "day", "year", "sym", "slot", "entry_px", "fwd"]].copy()
                k["arm"], k["pred"] = name, pt
                frames.append(k)
                print(f"  {year}: iters {model.n_iter_:>4}  rank IC {icm:+.5f} (t {ict:+.1f})",
                      flush=True)
    finally:
        f1.FEATURES = saved

    old = pd.read_parquet(PREDS)
    old["ts"] = pd.to_datetime(old["ts"])
    out = pd.concat([old[~old["arm"].isin(LEAN_ARMS)]] + frames, ignore_index=True)
    out.to_parquet(PREDS, index=False)
    piv = pd.DataFrame(ics).pivot(index="year", columns="arm", values="ic")
    print("\nmean walk-forward IC  " + "  ".join(f"{a} {piv[a].mean():+.5f}" for a in piv.columns))
    del record_rows
    print(f"written: {PREDS} - now run --books")


def post() -> None:
    """POST-RUN, barred from clause 5. The gate said ORTHOGONAL, the fit still lost: why?

    F-14's refusal had a clean mechanism - the new columns were 0.65-correlated copies of an
    incumbent with a smaller IC. That mechanism is RULED OUT here by clause 3a: every survivor
    except `auc_ojump` reads max |rho| 0.30-0.35. So the loss has to come from somewhere else,
    and the only other place a pooled univariate IC can hide a untradeable column is TIME: a
    full-sample t of -4.9 and a walk-forward IC of +0.001 are both true when the sign flips
    inside the sample, which is exactly F-14 (6) measured on a different family.
    """
    p = load_panel()
    p = p.dropna(subset=["y_close"]).copy()
    p = p[p["year"] >= f8.FIRST_TEST_YEAR]
    keep = [c for c in survivors() if c in FAM_A]
    cols = keep + ["gap", "prev_ret", "vwap_atr", "r6"]

    print("=== univariate per-timestamp rank IC against y_close, BY TEST YEAR ===")
    print(f"{'column':<16}" + "".join(f"{y:>9}" for y in range(2019, 2027))
          + f"{'pooled':>9}{'sign+':>7}")
    rows = []
    for c in cols:
        per, yr = [], {}
        for y in range(2019, 2027):
            v = _per_ts_spearman(p[p["year"] == y], c, "y_close")
            yr[y] = float(v.mean()) if len(v) > 30 else np.nan
            per.append(v)
        got = [v for v in per if len(v)]
        if not got:                       # market-level: no cross-section, clause 3b's channel
            print(f"{c:<16}" + f"{'(market-level, no cross-sectional variation)':>80}")
            continue
        allv = np.concatenate(got)
        pooled = float(allv.mean())
        npos = int(sum(1 for v in yr.values() if np.isfinite(v) and v * pooled > 0))
        rows.append({"column": c, "pooled": pooled, "pooled_t": f1.tstat(allv),
                     "sign_agree": npos, **{str(k): v for k, v in yr.items()}})
        print(f"{c:<16}" + "".join(f"{yr[y]:>+9.4f}" if np.isfinite(yr[y]) else f"{'-':>9}"
                                   for y in range(2019, 2027))
              + f"{pooled:>+9.4f}{npos:>6}/8")
    pd.DataFrame(rows).to_csv(OUT / "f15_post.csv", index=False)
    print(f"\nwritten: {OUT / 'f15_post.csv'}")

    print("\n=== the one survivor the gate flagged: auction jump vs bar gap ===")
    j = p[["ts", "auc_ojump", "gap", "y_close"]].dropna()
    r = _per_ts_spearman(j, "auc_ojump", "gap")
    print(f"  median per-timestamp |rho| {np.nanmedian(np.abs(r)):.3f} on {len(r):,} timestamps")
    d = j["auc_ojump"] - j["gap"]
    jj = j.assign(resid=d)
    v = _per_ts_spearman(jj, "resid", "y_close")
    print(f"  the RESIDUAL (auction jump minus bar gap) has IC {v.mean():+.5f} "
          f"(t {f1.tstat(v):+.2f}) - i.e. the part of the cross print the tape does not have")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--build", nargs="?", const="ab", default=None,
                    help="which families to build: 'a', 'b' or 'ab' (default)")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--books", action="store_true")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--lean", action="store_true")
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args()
    if a.fetch:
        fetch_auctions()
    if a.build:
        build(a.build)
    if a.gate:
        gate()
    if a.fit:
        fit(a.record)
    if a.books:
        books(a.record)
    if a.lean:
        lean(a.record)
    if a.post:
        post()


if __name__ == "__main__":
    main()
