#!/usr/bin/env python
"""D-6 / AUD-07 [iterate half]: the Alpaca minute store has no exchange calendar, so 21 early
closes are stored as full sessions. What do the post-market bars do to the sleeve?

    python scripts/sweep_d6.py                 # clauses 1-4 and 7, offline, no harness run
    python scripts/sweep_d6.py --arm keep      # clause 5 arm A: post-close bars kept (control)
    python scripts/sweep_d6.py --arm trim      # clause 5 arm B: session trimmed to its own close
    python scripts/sweep_d6.py --report        # clauses 5-6 from the two persisted arms

AUD-07 names four sites and `eng` closed three of them on 2026-09-12 (`quant_brain.core.calendar`,
`quant_brain.markets.equity_us`, `intraday_trader.flatten_minute_for`,
`intraday_backtest.flatten_minute_for`). The fourth is `alpaca_data.py:100-102`, which filters
incoming bars on a literal 09:30-16:00 window, and with it the store half of the finding: "all 21
early closes 2016-2025 carry 13:00-15:59 after-hours bars, so `late_momo` opens at 15:00 in the
post-market tape and the flatten fills against it at 1.5 bp". That sentence was written before the
flatten minute became calendar-aware, so this script does not assume it is still true - it
measures what the store can still reach.

Pre-registered clauses (fixed before any number below was read)
--------------------------------------------------------------
1. IDENTITY. The in-process control arm equals the shipped CLI on the same pinned window to every
   printed digit. Without this, clause 5 measures this script and not the sleeve.
2. PREMISE. Count what the calendar says is not in a session, per store: rows at or after a 13:00
   early close, and rows on a full-day closure. The IBKR store must come back CLEAN, because that
   is what makes the `load_bars` patch a no-op for the live trader; if it does not, the patch is
   withdrawn and re-gated as a live change.
3. TAPE. Prove those rows are a post-market tape rather than an extended session, from the store's
   own volume: bars printed out of the 180 possible, and total volume against the same clock
   window on the five regular sessions before it. The harness charges 1.5 bps there; a tape at x%
   of normal makes that charge wrong by about 1/x.
4. REACHABILITY. In the control arm, count every fill stamped at or after the session's calendar
   close, and every "eod" forced fill on any session. This is the honest test of whether the
   defect can still move money after the `eng` flatten fix, and it is pre-registered to be
   reported whichever way it lands - a latent defect stated as latent is the result.
5. MATERIALITY. Paired arms over the same pinned windows, the only difference being the trim.
   MATERIAL if |d net $/day| >= 5% of |the control's net $/day| over the affected sessions, or if
   any fill in clause 4 lands in the post-close tape. Both directions, stated in advance.
6. CHANNEL. `active` is `orb` + `vwap_trend` + `late_momo` and none of them reads a cross-session
   feature, but `base.features` computes exactly one - `prev_close`, the previous session's last
   close - and `gap_fade` gates on it. Run `gap_fade` on the same windows: if its book moves while
   `active`'s does not, the defect is a live channel into any future strategy and the store fix is
   worth shipping on that ground alone, whatever clause 5 says about today's sleeve.
7. SUBSET. `calendar_trim` must be a pure subset of what it is given on all 16 symbols of both
   stores: same rows, same values, nothing filled, shifted or reindexed. A trim that eats a real
   RTH row is worse than a store with extra ones.
8. WITHDRAWAL. Clause 2 finding the IBKR store dirty, or clause 7 failing on any symbol, means
   nothing is shipped.
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

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import intraday_common as ic  # noqa: E402
from intraday_common import UNIVERSE  # noqa: E402
from quant_brain.markets.equity_us import CALENDAR  # noqa: E402

OUT = REPO / "results" / "d6"
ALPACA = REPO / "data" / "minute_alpaca"
IBKR = REPO / "data" / "minute"

#: Pinned measurement windows: every early close in the Alpaca store, plus the two sessions on
#: each side. Two sessions after, because the one cross-session feature (`prev_close`) reaches
#: exactly one session forward and the second is the control for it. Each window is its own book
#: at `EQUITY`, which is exact rather than approximate here: every feature in `base.features` is
#: session-scoped except `prev_close`, the sleeve is flat at every close, and so a session's P&L
#: depends only on its own bars and the equity it starts with.
PAD = 2
EQUITY = 1_000_000.0
ARMS = ("keep", "trim")


# --------------------------------------------------------------------------------- store shapes

def store_frame(store: Path, symbol: str) -> pd.DataFrame:
    p = store / f"{symbol.upper()}.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(ic.ET)
    return df.sort_index()


def out_of_session(df: pd.DataFrame) -> tuple[int, int, set]:
    """(rows past an early close, rows on a full closure, the sessions they fall on)."""
    if df.empty:
        return 0, 0, set()
    days = pd.Index(df.index.date)
    times = df.index.time
    uniq = set(days)
    late = 0
    hit = set()
    for d in uniq & CALENDAR.early_closes():
        sess = CALENDAR.session(d)
        m = (days == d) & (times >= sess.close_t)
        n = int(m.sum())
        if n:
            late += n
            hit.add(d)
    hol = uniq & CALENDAR.holidays()
    return late, int(days.isin(hol).sum()), hit


def clause_premise() -> dict:
    print("\n[2] PREMISE - rows the calendar says are not in a session")
    res = {}
    for name, store in (("alpaca", ALPACA), ("ibkr", IBKR)):
        tot = late = holi = 0
        days = set()
        per = {}
        for s in UNIVERSE:
            df = store_frame(store, s)
            if df.empty:
                continue
            a, b, d = out_of_session(df)
            tot += len(df)
            late += a
            holi += b
            days |= d
            per[s] = {"rows": len(df), "late": a, "holiday": b, "sessions": len(d)}
        res[name] = {"rows": tot, "late": late, "holiday": holi,
                     "sessions": sorted(str(x) for x in days), "per_symbol": per}
        pct = 100 * late / tot if tot else 0.0
        print(f"  {name:7s} {tot:>10,} rows  past-close {late:>7,} ({pct:.4f}%)  "
              f"on-holiday {holi:>5,}  sessions {len(days):>3}")
    clean = res["ibkr"]["late"] == 0 and res["ibkr"]["holiday"] == 0
    print(f"  IBKR store clean: {clean}  -> the load_bars patch is a no-op for the live trader"
          if clean else "  IBKR store DIRTY -> clause 8 withdrawal, re-gate as a live change")
    res["ibkr_clean"] = clean
    return res


def clause_tape(days: list[str]) -> dict:
    print("\n[3] TAPE - are the past-close rows a session or a post-market print?")
    ecs = CALENDAR.early_closes()
    rows = []
    for s in UNIVERSE:
        df = store_frame(ALPACA, s)
        if df.empty:
            continue
        d = np.array(df.index.date)
        mins = np.array([x.hour * 60 + x.minute for x in df.index.time])
        v = df["v"].to_numpy(dtype=float)
        allday = sorted(set(d))
        seen = set(allday)
        for ds in days:
            e = dt.date.fromisoformat(ds)
            if e not in seen:
                continue
            sess = CALENDAR.session(e)
            cut = sess.close_t.hour * 60 + sess.close_t.minute
            ref = [x for x in allday if x < e and x not in ecs][-5:]
            m_e = (d == e) & (mins >= cut)
            if not m_e.any() or not ref:
                continue
            m_r = np.isin(d, ref) & (mins >= cut)
            ref_v = v[m_r].sum() / len(ref) if m_r.any() else np.nan
            possible = 16 * 60 - cut
            rows.append({"sym": s, "day": ds, "bars": int(m_e.sum()), "possible": possible,
                         "vol": v[m_e].sum(), "ref_vol": ref_v,
                         "ratio": v[m_e].sum() / ref_v if ref_v and ref_v == ref_v else np.nan})
    t = pd.DataFrame(rows)
    if t.empty:
        return {}
    cov = (t["bars"] / t["possible"]).median()
    print(f"  {len(t)} (symbol, session) pairs over {t['day'].nunique()} early closes")
    print(f"  minutes that print at all:      median {100 * cov:.1f}% of the post-close window")
    print(f"  volume vs the same clock window on the 5 regular sessions before it:")
    print(f"    median {t['ratio'].median():.4f}  q25 {t['ratio'].quantile(.25):.4f}  "
          f"q75 {t['ratio'].quantile(.75):.4f}")
    print(f"  -> a 1.5 bps fill charge in that tape is wrong by about "
          f"{1 / t['ratio'].median():.1f}x")
    by = t.groupby("day").agg(bars=("bars", "median"), ratio=("ratio", "median"))
    print(by.round(4).to_string())
    return {"pairs": len(t), "minute_coverage": float(cov), "vol_ratio_median": float(t["ratio"].median()),
            "vol_ratio_q25": float(t["ratio"].quantile(.25)), "vol_ratio_q75": float(t["ratio"].quantile(.75)),
            "by_day": {k: {"bars": float(r.bars), "ratio": float(r.ratio)} for k, r in by.iterrows()}}


def clause_subset() -> dict:
    """Clause 7: the trim is a pure subset, on both real stores, all 16 symbols."""
    print("\n[7] SUBSET - calendar_trim never invents, shifts or drops an in-session row")
    bad = []
    checked = 0
    for name, store in (("alpaca", ALPACA), ("ibkr", IBKR)):
        for s in UNIVERSE:
            df = store_frame(store, s)
            if df.empty:
                continue
            t = df.index.time
            rth = df[(t >= ic.SESSION_OPEN) & (t < ic.SESSION_CLOSE)]
            cut = ic.calendar_trim(rth)
            checked += 1
            if not cut.index.isin(rth.index).all():
                bad.append(f"{name}/{s}: trim produced a row the store does not have")
            elif not cut.equals(rth.loc[cut.index]):
                bad.append(f"{name}/{s}: trim changed a value it kept")
            else:
                late, holi, _ = out_of_session(cut)
                if late or holi:
                    bad.append(f"{name}/{s}: {late} past-close / {holi} holiday rows survived")
    print(f"  {checked} symbol-stores checked, {len(bad)} violation(s)")
    for b in bad[:10]:
        print(f"    {b}")
    return {"checked": checked, "violations": bad}


# ----------------------------------------------------------------------------------- clause 1/5

def windows(days: list[str], bars: dict) -> list[tuple[dt.date, dt.date, dt.date]]:
    sess = ic.sessions(bars)
    idx = {d: i for i, d in enumerate(sess)}
    out = []
    for ds in days:
        e = dt.date.fromisoformat(ds)
        i = idx.get(e)
        if i is None:
            continue
        out.append((e, sess[max(0, i - PAD)], sess[min(len(sess) - 1, i + PAD)]))
    return out


def arm_path(arm: str, strategy: str) -> Path:
    return OUT / f"{strategy}_{arm}.json"


def run_arm(arm: str, strategy_name: str, days: list[str]) -> dict:
    """One arm of clause 5: every pinned window, own book, trades kept for clause 4."""
    import intraday_backtest as ib

    ic.CALENDAR_TRIM = (arm == "trim")
    strategy = ib.load_strategy(strategy_name)
    params = dict(strategy.PARAMS)
    t0 = time.time()
    bars = ic.load_universe(UNIVERSE)
    feats = {s: ib.features(df) for s, df in bars.items()}
    print(f"  loaded {sum(len(v) for v in bars.values()):,} rows, features in "
          f"{time.time() - t0:.0f}s (CALENDAR_TRIM={ic.CALENDAR_TRIM})", flush=True)
    out = {"arm": arm, "strategy": strategy_name, "calendar_trim": ic.CALENDAR_TRIM, "windows": {}}
    for e, lo, hi in windows(days, bars):
        s = ib.run(strategy, bars, EQUITY, params, lo, hi, False, feats, collect_trades=True)
        d = s["daily"]
        trades = [{"t": str(t["t"]), "sym": t["sym"], "qty": float(t["qty"]), "px": float(t["px"]),
                   "cost": float(t["cost"]), "why": t["why"]} for t in s["trades_log"]]
        out["windows"][str(e)] = {
            "start": str(lo), "end": str(hi),
            "daily": [{"day": str(r.day), "pnl": float(r.pnl), "trades": int(r.trades)}
                      for r in d.itertuples()],
            "costs_total": float(s["costs_total"]), "trades": int(s["trades"]),
            "forced_eod_orders": int(s["forced_eod_orders"]),
            "forced_eod_notional": float(s["forced_eod_notional"]),
            "forced_eod_days": s["forced_eod_days"],
            "trades_log": trades,
        }
        print(f"  {e}  {lo}..{hi}  trades {s['trades']:>5}  "
              f"eod {s['forced_eod_orders']:>2}  pnl {d['pnl'].sum():>+12,.0f}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    arm_path(arm, strategy_name).write_text(json.dumps(out, indent=1), encoding="utf-8")
    ic.CALENDAR_TRIM = True
    print(f"  -> {arm_path(arm, strategy_name).relative_to(REPO)} ({time.time() - t0:.0f}s)")
    return out


def clause_identity(days: list[str]) -> dict:
    """Clause 1: the in-process control window equals the shipped CLI on the same window."""
    import subprocess

    import intraday_backtest as ib

    ic.CALENDAR_TRIM = False
    bars = ic.load_universe(UNIVERSE)
    w = windows(days[-1:], bars)
    if not w:
        return {"ok": False, "why": "window not in store"}
    _e, lo, hi = w[0]
    strategy = ib.load_strategy("active")
    feats = {s: ib.features(df) for s, df in bars.items()}
    s = ib.run(strategy, bars, EQUITY, dict(strategy.PARAMS), lo, hi, False, feats)
    ic.CALENDAR_TRIM = True
    import os
    env = dict(os.environ, INTRADAY_DATA_DIR="data/minute_alpaca")
    cmd = [sys.executable, str(REPO / "scripts" / "intraday_backtest.py"), "--strategy", "active",
           "--start", str(lo), "--end", str(hi), "--equity", str(int(EQUITY)),
           "--no-calendar-trim", "--no-validate", "--no-record", "--tag", "D-6 clause 1"]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO), env=env)
    got = {}
    for line in p.stdout.splitlines():
        if line.strip().startswith(("net profit %", "avg daily P&L $", "trades ", "costs/day $")):
            k, _, v = line.strip().rpartition("  ")
            got[k.strip()] = v.strip()
    mine = {"net profit %": f"{s['net_profit_pct']:.2f}", "avg daily P&L $": f"{s['avg_daily_pnl']:,.0f}",
            "trades": f"{s['trades']}", "costs/day $": f"{s['costs_per_day']:,.0f}"}
    ok = all(got.get(k) == v for k, v in mine.items())
    print(f"\n[1] IDENTITY on {lo}..{hi}: in-process {mine}")
    print(f"                       shipped CLI {got}")
    print(f"  match: {ok}")
    return {"ok": ok, "window": [str(lo), str(hi)], "in_process": mine, "cli": got,
            "cli_rc": p.returncode}


# ------------------------------------------------------------------------------- clauses 4, 5, 6

def clause_reach(keep: dict) -> dict:
    print("\n[4] REACHABILITY - fills the post-close tape can still take")
    late, eod = [], []
    for ds, w in keep["windows"].items():
        sess = CALENDAR.session(dt.date.fromisoformat(ds))
        for t in w["trades_log"]:
            ts = pd.Timestamp(t["t"])
            if str(ts.date()) == ds and ts.time() >= sess.close_t:
                late.append({"day": ds, **t})
            if t["why"] == "eod":
                eod.append({"day": str(ts.date()), **t})
    notional = sum(abs(t["qty"]) * t["px"] for t in late)
    print(f"  fills at or after the calendar close: {len(late)}  (${notional:,.0f} notional)")
    print(f"  'eod' forced fills on any session:    {len(eod)}")
    for t in late[:10]:
        print(f"    {t['t']}  {t['sym']:6s} {t['qty']:+10.0f} @ {t['px']:>10.2f}  {t['why'] or 'signal'}")
    if not late and not eod:
        print("  -> LATENT in the trading path: the calendar-aware flatten minute already stops "
              "every decision before the close")
    return {"late_fills": len(late), "late_notional": notional, "eod_fills": len(eod),
            "examples": late[:20]}


def clause_material(keep: dict, trim: dict, strategy: str) -> dict:
    print(f"\n[5/6] MATERIALITY - {strategy}: post-close bars kept vs session trimmed")
    rows = []
    for ds in sorted(keep["windows"]):
        a, b = keep["windows"][ds], trim["windows"].get(ds)
        if b is None:
            continue
        pa = {r["day"]: r["pnl"] for r in a["daily"]}
        pb = {r["day"]: r["pnl"] for r in b["daily"]}
        for day in sorted(set(pa) | set(pb)):
            rows.append({"early_close": ds, "day": day, "keep": pa.get(day, 0.0),
                         "trim": pb.get(day, 0.0), "d": pb.get(day, 0.0) - pa.get(day, 0.0)})
    t = pd.DataFrame(rows)
    moved = t[t["d"].abs() > 1e-6]
    tr_k = sum(w["trades"] for w in keep["windows"].values())
    tr_t = sum(w["trades"] for w in trim["windows"].values())
    ck = sum(w["costs_total"] for w in keep["windows"].values())
    ct = sum(w["costs_total"] for w in trim["windows"].values())
    n = len(t)
    dsum = t["d"].sum()
    base = abs(t["keep"].sum() / n) if n else 0.0
    print(f"  {n} sessions in {len(keep['windows'])} pinned windows, equity ${EQUITY:,.0f}/window")
    print(f"  sessions whose P&L moves: {len(moved)}")
    print(f"  trades   keep {tr_k:>6}  trim {tr_t:>6}  d {tr_t - tr_k:>+6}")
    print(f"  costs $  keep {ck:>12,.0f}  trim {ct:>12,.0f}  d {ct - ck:>+12,.0f}")
    print(f"  net $    keep {t['keep'].sum():>12,.0f}  trim {t['trim'].sum():>12,.0f}  "
          f"d {dsum:>+12,.0f}  ({dsum / n:+,.2f} $/session)")
    if len(moved):
        print(moved.round(2).to_string(index=False))
    thr = 0.05 * base
    verdict = "MATERIAL" if n and abs(dsum / n) >= thr and thr > 0 else "NOT MATERIAL"
    print(f"  threshold 5% of |control $/session| = ${thr:,.2f}; |d| = ${abs(dsum / n):,.2f} "
          f"-> {verdict}")
    return {"strategy": strategy, "sessions": n, "moved": len(moved), "trades_keep": tr_k,
            "trades_trim": tr_t, "costs_keep": ck, "costs_trim": ct,
            "net_keep": float(t["keep"].sum()), "net_trim": float(t["trim"].sum()),
            "d_total": float(dsum), "d_per_session": float(dsum / n) if n else 0.0,
            "threshold": thr, "verdict": verdict,
            "moved_rows": moved.round(4).to_dict("records")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", choices=ARMS, help="run one clause-5 arm and persist it")
    ap.add_argument("--strategy", default="active")
    ap.add_argument("--identity", action="store_true", help="clause 1 (spawns the shipped CLI)")
    ap.add_argument("--report", action="store_true", help="clauses 4-6 from the persisted arms")
    args = ap.parse_args(argv)

    if Path(ic.DATA_DIR).resolve() != ALPACA.resolve():
        return int(print("set INTRADAY_DATA_DIR=data/minute_alpaca; this item is about that store")
                   or 2)
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}

    if args.arm:
        days = json.loads((OUT / "premise.json").read_text(encoding="utf-8"))["alpaca"]["sessions"]
        print(f"\n[5] arm '{args.arm}' - {len(days)} pinned windows, +/-{PAD} sessions")
        run_arm(args.arm, args.strategy, days)
        return 0

    if args.report:
        days = json.loads((OUT / "premise.json").read_text(encoding="utf-8"))["alpaca"]["sessions"]
        keep = json.loads(arm_path("keep", args.strategy).read_text(encoding="utf-8"))
        trim = json.loads(arm_path("trim", args.strategy).read_text(encoding="utf-8"))
        summary["reach"] = clause_reach(keep)
        summary["material"] = clause_material(keep, trim, args.strategy)
        (OUT / f"report_{args.strategy}.json").write_text(json.dumps(summary, indent=1),
                                                          encoding="utf-8")
        return 0

    prem = clause_premise()
    (OUT / "premise.json").write_text(json.dumps(prem, indent=1), encoding="utf-8")
    summary["premise"] = {k: v for k, v in prem.items() if k != "per_symbol"}
    summary["tape"] = clause_tape(prem["alpaca"]["sessions"])
    summary["subset"] = clause_subset()
    if args.identity:
        summary["identity"] = clause_identity(prem["alpaca"]["sessions"])
    (OUT / "offline.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    ok = prem["ibkr_clean"] and not summary["subset"]["violations"]
    print(f"\n[8] WITHDRAWAL: clause 2 clean={prem['ibkr_clean']}, "
          f"clause 7 violations={len(summary['subset']['violations'])} -> "
          f"{'ship' if ok else 'WITHDRAW'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
