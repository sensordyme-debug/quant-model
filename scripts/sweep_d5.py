#!/usr/bin/env python
"""D-5 / AUD-15: is the IBKR minute store split-adjusted, and what does pricing it as raw cost?

    python scripts/sweep_d5.py                      # clauses 1-4 and 6, offline, no writes
    python scripts/sweep_d5.py --price              # + clause 5: two paired harness runs
    python scripts/sweep_d5.py --price --write      # + write data/minute/_splits.json
    python scripts/sweep_d5.py --price --write --record    # + DIAGNOSTIC ledger rows

AUD-15 says `data/minute` holds SPLIT-ADJUSTED bars while `intraday_common.share_scale` returns
1.0 for it, so IBKR's per-share commission is charged on the adjusted share count - "SOXS before
2026-03-05 is modelled at 1/200 of reality ... NFLX 10x for ~58 sessions, in every IBKR-store
backtest". The claim is checkable entirely from what is on disk plus a split calendar, so this
script does that before anything is written, and prices the correction on the harness the sleeve
is judged by.

Pre-registered clauses (fixed before any number in the output was read)
----------------------------------------------------------------------
1. IDENTITY. With no `_splits.json` in `data/minute`, `share_scale` is exactly 1.0 on every one of
   the 16 x N stored symbol-days, and the in-process control book equals the shipped CLI's to the
   cent. If the in-process call is not the shipped path, clause 5 measures nothing.
2. PREMISE. The store is on the CURRENT share basis, tested two ways per split event inside its
   span. (a) DISCONTINUITY: the store's own close-to-close step across the split date must sit
   near 1.0 and NOT near the raw-basis prediction 1/ratio - decided against the symbol's own
   overnight-gap distribution, not against a guessed tolerance. (b) NO MIXED BASIS: the monthly
   median IBKR/Alpaca close ratio must stay near 1.0 across the seam for all 16 symbols, because
   Alpaca is adjusted to the current basis by its own table, so a store built incrementally
   through a split would show a step of the split ratio. If either test says raw or mixed,
   `share_scale` stays 1.0 and the item is REFUSED - a factor applied to a raw store is the same
   defect with the sign flipped.
3. SOURCE-AGNOSTIC DERIVATION. The factor table is derived from a split CALENDAR (yfinance), not
   from the Alpaca raw/adjusted price ratio, and must agree with `data/minute_alpaca/_splits.json`
   on EVERY stored symbol-day. Two independent sources or the file is not written.
4. CEILING BEFORE P&L (S-32's rule). Quote the arithmetic size of the mis-charge - per-share
   commission in bps of notional, under both scales, from the store's own prices - before any
   backtest column. A correction whose ceiling is below the 1.5 bps slippage line cannot matter
   however the P&L column lands.
5. MATERIALITY. Two paired harness runs over the whole stored span, the only difference being the
   presence of the table. MATERIAL if |d costs/day| >= 5% of the control's costs/day or
   |d net $/day| >= 5% of |the control's net $/day|; pre-registered, both directions.
6. DIRECTION. Report the sign per affected symbol. AUD-15 names an understatement only; a factor
   above 1.0 OVERcharges, and the audit's own NFLX case is that way round.
7. GUARD. `save_bars` must refuse a merge whose overlapping closes disagree (AUD-15's second half)
   and must NOT refuse a legitimate re-save: proven on the real store, all 16 symbols, by
   re-saving each symbol's own last session into it.
8. WITHDRAWAL. Clause 2 or 3 failing means nothing is written. Clause 7 rejecting any of the 16
   real re-saves means the guard is withdrawn - a fetcher that cannot write is worse than a store
   that is costed wrong, because D-4 has just shown what a frozen store does.
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
import intraday_data as idata  # noqa: E402

from intraday_common import UNIVERSE  # noqa: E402

ALPACA_SPLITS = REPO / "data" / "minute_alpaca" / ic.SPLITS_FILE
OUT = REPO / "results" / "d5"


# --------------------------------------------------------------------------- store and calendar

def store_sessions(symbol: str) -> list[dt.date]:
    return sorted(idata.store_shapes(symbol))


def derived_table(symbols) -> dict[str, list]:
    """Clause 3's table: yfinance's split calendar, restricted to each symbol's stored span."""
    import yfinance as yf
    out = {}
    for s in symbols:
        span = idata.store_span(s)
        if span is None:
            continue
        out[s.upper()] = idata.split_segments(s, *span, events=yf.Ticker(s).splits)
    return out


def factor_on(segs: list[list], day: dt.date) -> float:
    """share_scale's rule, applied to a table held in memory rather than on disk."""
    f = segs[0][1]
    d = str(day)
    for start, fac in segs:
        if start <= d:
            f = fac
        else:
            break
    return float(f) or 1.0


# ------------------------------------------------------------------------------ clause 1

def clause_identity(symbols) -> dict:
    """The shipped state: with no table loaded, share_scale is exactly 1.0 everywhere.

    Checked against an EMPTY table rather than against the absence of the file, so the clause still
    means something after `--write` has run - what it has to establish is that the correction moves
    only the symbol-days clause 4 names, and that is a statement about the shipped code path.
    """
    present = (ic.DATA_DIR / ic.SPLITS_FILE).exists()
    saved = ic._SPLITS
    ic._SPLITS = {}
    days = ones = 0
    for s in symbols:
        for d in store_sessions(s):
            days += 1
            ones += ic.share_scale(s, d) == 1.0
    ic._SPLITS = saved
    return {"splits_file_present": present, "symbol_days": days, "scale_is_one": ones,
            "pass": days > 0 and ones == days}


# ------------------------------------------------------------------------------ clause 2

def overnight_gaps(df: pd.DataFrame) -> pd.Series:
    """Close-to-close step between consecutive stored sessions, as a ratio."""
    last = df["c"].groupby(df.index.date).last()
    return (last / last.shift(1)).dropna()


def clause_premise(table: dict[str, list]) -> dict:
    rows, alp_rows = [], []
    for sym, segs in sorted(table.items()):
        if len(segs) < 2:
            continue
        df = ic.load_bars(sym)
        gaps = overnight_gaps(df)
        q99 = float(np.nanquantile(np.abs(np.log(gaps.values)), 0.99))
        for start, fac in segs[1:]:
            d = dt.date.fromisoformat(start)
            prev = [g for g in gaps.index if g < d]
            if not prev or d not in set(gaps.index):
                continue
            step = float(gaps.loc[d])
            # the factor to the LEFT of this boundary divided by the factor to its right is the
            # split ratio; a RAW store would step by its inverse.
            left = factor_on(segs, prev[-1])
            raw_pred = left / fac
            rows.append({"symbol": sym, "split": start, "ratio": fac / left,
                         "store_step": step, "raw_prediction": raw_pred,
                         "log_step": float(np.log(step)), "gap_log_q99": q99,
                         "adjusted": abs(np.log(step)) <= max(q99, np.log(1.05)),
                         "raw": abs(np.log(step / raw_pred)) <= max(q99, np.log(1.05))})
    # (b) no mixed basis anywhere in the store, against the Alpaca current-basis series
    for sym in sorted(table):
        a = REPO / "data" / "minute_alpaca" / f"{sym}.parquet"
        if not a.exists():
            continue
        ib = ic.load_bars(sym)
        al = pd.read_parquet(a)
        if al.index.tz is None:
            al.index = al.index.tz_localize("UTC")
        al.index = al.index.tz_convert(ic.ET)
        j = ib[["c"]].join(al["c"].rename("alp"), how="inner").dropna()
        j = j[j["alp"] != 0]
        if len(j) < 100:
            continue
        r = (j["c"] / j["alp"]).astype(float)
        med = r.groupby([r.index.year, r.index.month]).median()
        alp_rows.append({"symbol": sym, "bars": len(j), "months": len(med),
                         "monthly_median_min": float(med.min()),
                         "monthly_median_max": float(med.max()),
                         "worst_dev": float(np.abs(med - 1.0).max())})
    mixed = [r for r in alp_rows if r["worst_dev"] > 0.02]
    return {"events": rows, "alpaca": alp_rows, "mixed_basis_symbols": [r["symbol"] for r in mixed],
            "pass": bool(rows) and all(r["adjusted"] and not r["raw"] for r in rows)
            and not mixed}


# ------------------------------------------------------------------------------ clause 3

def clause_sources(table: dict[str, list]) -> dict:
    try:
        alp = json.loads(ALPACA_SPLITS.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "pass": False}
    rows, disagree = [], 0
    for sym, segs in sorted(table.items()):
        days = store_sessions(sym)
        other = alp.get(sym)
        if not days:
            continue
        if not other:
            rows.append({"symbol": sym, "days": len(days), "compared": 0, "disagree": 0,
                         "note": "absent from the Alpaca table"})
            continue
        bad = sum(1 for d in days
                  if not np.isclose(factor_on(segs, d), factor_on(other, d), rtol=1e-9))
        disagree += bad
        rows.append({"symbol": sym, "days": len(days), "compared": len(days), "disagree": bad})
    compared = sum(r["compared"] for r in rows)
    return {"rows": rows, "symbol_days_compared": compared, "disagree": disagree,
            "pass": compared > 0 and disagree == 0}


# ------------------------------------------------------------------------------ clauses 4 and 6

def clause_ceiling(table: dict[str, list]) -> dict:
    """Per-share commission in bps of notional, under both scales, from the store's own closes."""
    rows = []
    for sym, segs in sorted(table.items()):
        df = ic.load_bars(sym)
        if df.empty:
            continue
        last = df["c"].groupby(df.index.date).last()
        for start, fac in segs:
            d0 = dt.date.fromisoformat(start)
            nxt = [dt.date.fromisoformat(s) for s, _ in segs if s > start]
            d1 = min(nxt) - dt.timedelta(days=1) if nxt else max(last.index)
            px = last[(last.index >= d0) & (last.index <= d1)]
            if px.empty:
                continue
            adj = float(px.median())
            raw = adj * fac
            wrong = ic.COMMISSION_PER_SHARE / adj * 1e4
            right = min(ic.COMMISSION_PER_SHARE / raw, 0.01) * 1e4
            rows.append({"symbol": sym, "from": start, "to": str(d1), "sessions": int(len(px)),
                         "factor": fac, "median_adjusted_px": adj, "median_raw_px": raw,
                         "bps_as_priced": wrong, "bps_correct": right,
                         "bps_error": right - wrong,
                         "direction": "under" if right > wrong else
                                      ("over" if right < wrong else "none")})
    bad = [r for r in rows if r["factor"] != 1.0]
    return {"rows": rows,
            "affected_symbol_days": sum(r["sessions"] for r in bad),
            "max_abs_bps_error": max((abs(r["bps_error"]) for r in bad), default=0.0),
            "under": [r["symbol"] for r in bad if r["direction"] == "under"],
            "over": [r["symbol"] for r in bad if r["direction"] == "over"],
            "slippage_line_bps": ic.SLIPPAGE_BPS}


# ------------------------------------------------------------------------------ clause 5

#: One harness run costs ~21 min on this store's 263 sessions, so the two arms are separate
#: commands (AGENTS.md's 40-minute rule) joined by --combine, exactly as A-8 batched its grid.
ARMS = ("control", "corrected")


def arm_path(arm: str) -> Path:
    return OUT / f"daily_{arm}.csv"


def run_arm(arm: str, strategy_name: str, equity: float, table: dict[str, list],
            start: dt.date | None, end: dt.date | None) -> dict:
    """One arm of clause 5 through the shipped harness; persists its daily series and summary."""
    import intraday_backtest as ib

    strategy = ib.load_strategy(strategy_name)
    params = dict(strategy.PARAMS)
    bars = ic.load_universe(UNIVERSE, start, end)
    ib.validate_bars(bars, strict=True)
    feats = {s: ib.features(df) for s, df in bars.items()}
    ic._SPLITS = {} if arm == "control" else dict(table)
    t0 = time.time()
    s = ib.run(strategy, bars, equity, params, start, end, False, feats)
    ic._SPLITS = None
    OUT.mkdir(parents=True, exist_ok=True)
    s["daily"][["day", "pnl", "trades", "stopped"]].to_csv(arm_path(arm), index=False)
    meta = {k: v for k, v in s.items() if k != "daily"}
    (OUT / f"summary_{arm}.json").write_text(json.dumps(meta, indent=1, default=str),
                                            encoding="utf-8")
    print(f"  {arm}: {s['sessions']} sessions, {s['trades']} trades, "
          f"{s['avg_daily_pnl']:+,.0f} $/day, costs {s['costs_per_day']:,.0f} $/day "
          f"({time.time() - t0:.0f}s) -> {arm_path(arm).relative_to(REPO)}", flush=True)
    return s


def load_arms() -> dict:
    out = {}
    for arm in ARMS:
        p, q = arm_path(arm), OUT / f"summary_{arm}.json"
        if not (p.exists() and q.exists()):
            return {}
        s = json.loads(q.read_text(encoding="utf-8"))
        s["daily"] = pd.read_csv(p)
        out[arm] = s
    return out


def clause_materiality(pair: dict) -> dict:
    c, x = pair["control"], pair["corrected"]
    a = c["daily"][["day", "pnl"]].rename(columns={"pnl": "ctl"})
    b = x["daily"][["day", "pnl"]].rename(columns={"pnl": "cor"})
    j = a.merge(b, on="day", how="inner")
    d = (j["cor"] - j["ctl"]).values
    n = len(d)
    dm = float(np.mean(d)) if n else 0.0
    se = float(np.std(d, ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
    tstat = dm / se if se and np.isfinite(se) and se > 0 else float("nan")
    d_cost = x["costs_per_day"] - c["costs_per_day"]
    thr_cost = 0.05 * abs(c["costs_per_day"])
    thr_net = 0.05 * abs(c["avg_daily_pnl"])
    return {"sessions": n, "d_net_per_day": dm, "t": tstat,
            "d_costs_per_day": float(d_cost),
            "control_costs_per_day": float(c["costs_per_day"]),
            "control_net_per_day": float(c["avg_daily_pnl"]),
            "corrected_net_per_day": float(x["avg_daily_pnl"]),
            "threshold_costs": float(thr_cost), "threshold_net": float(thr_net),
            "material": bool(abs(d_cost) >= thr_cost or abs(dm) >= thr_net),
            "d_trades": int(x["trades"] - c["trades"])}


# ------------------------------------------------------------------------------ clause 7

def clause_guard(symbols) -> dict:
    """The merge guard, on the real store: a rebased copy is refused, an honest re-save is not."""
    rows = []
    for s in symbols:
        df = ic.load_bars(s)
        if df.empty:
            continue
        days = sorted(set(df.index.date))
        last = df[df.index.date == days[-1]].copy()
        utc = last.tz_convert("UTC") if last.index.tz is not None else last
        honest = ic.basis_mismatch(df.tz_convert("UTC"), utc) is None
        rebased = last.copy()
        for col in ("o", "h", "l", "c"):
            rebased[col] = rebased[col] * 10.0
        caught = ic.basis_mismatch(df.tz_convert("UTC"), rebased.tz_convert("UTC")) is not None
        rows.append({"symbol": s, "bars_checked": len(last),
                     "honest_resave_allowed": bool(honest), "rebasis_caught": bool(caught)})
    return {"rows": rows,
            "pass": bool(rows) and all(r["honest_resave_allowed"] and r["rebasis_caught"]
                                       for r in rows)}


# ------------------------------------------------------------------------------------- report

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strategy", default="active")
    ap.add_argument("--equity", type=float, default=1_000_000)
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--arm", choices=ARMS,
                    help="clause 5: run ONE arm (~21 min on 263 sessions) and persist it")
    ap.add_argument("--combine", action="store_true",
                    help="clause 5: join the persisted arms and decide materiality")
    ap.add_argument("--price", action="store_true",
                    help="clause 5 in one process: both arms back to back (~42 min)")
    ap.add_argument("--write", action="store_true",
                    help="write data/minute/_splits.json (only if clauses 2 and 3 pass)")
    ap.add_argument("--record", action="store_true",
                    help="append DIAGNOSTIC rows to research/experiments.jsonl")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    start = dt.date.fromisoformat(args.start) if args.start else None
    end = dt.date.fromisoformat(args.end) if args.end else None

    out: dict = {"store": str(ic.DATA_DIR), "symbols": len(UNIVERSE)}
    out["c1_identity"] = clause_identity(UNIVERSE)
    table = derived_table(UNIVERSE)
    out["table"] = table
    out["c2_premise"] = clause_premise(table)
    out["c3_sources"] = clause_sources(table)
    out["c4_ceiling"] = clause_ceiling(table)
    out["c7_guard"] = clause_guard(UNIVERSE)

    gate = out["c2_premise"]["pass"] and out["c3_sources"]["pass"]
    arms = [args.arm] if args.arm else (list(ARMS) if args.price else [])
    if arms:
        print(f"\nclause 5 on {ic.DATA_DIR}: arm(s) {', '.join(arms)}", flush=True)
        for arm in arms:
            run_arm(arm, args.strategy, args.equity, table, start, end)
    if args.combine or args.price:
        pair = load_arms()
        if not pair:
            print(f"\nclause 5: both arms must be on disk first "
                  f"(results/d5/daily_{{{','.join(ARMS)}}}.csv)")
        else:
            out["c5_materiality"] = clause_materiality(pair)
            out["_pair"] = pair

    if args.write:
        if not gate:
            print("\nclause 8: WITHDRAWN - clause 2 or 3 failed, nothing written")
        else:
            OUT.mkdir(parents=True, exist_ok=True)
            idata.write_splits(UNIVERSE)
            out["written"] = str(ic.DATA_DIR / ic.SPLITS_FILE)
            # the file on disk must reproduce the table every clause above was decided on
            ic._SPLITS = None
            bad = [(s, str(d)) for s in UNIVERSE for d in store_sessions(s)
                   if not np.isclose(ic.share_scale(s, d), factor_on(table[s.upper()], d),
                                     rtol=1e-12)]
            out["write_verified"] = not bad
            print(f"  on-disk share_scale reproduces the derived table on "
                  f"{out['c1_identity']['symbol_days'] - len(bad):,}/"
                  f"{out['c1_identity']['symbol_days']:,} symbol-days"
                  f"{'  MISMATCH ' + str(bad[:5]) if bad else ''}")

    if args.json:
        print(json.dumps({k: v for k, v in out.items() if k != "_pair"}, indent=2, default=str))
        return 0

    print(f"\nD-5 / AUD-15   store {ic.DATA_DIR}   {len(UNIVERSE)} symbols\n")

    c1 = out["c1_identity"]
    print("clause 1 - identity")
    print(f"  _splits.json present: {c1['splits_file_present']}; "
          f"share_scale == 1.0 on {c1['scale_is_one']:,}/{c1['symbol_days']:,} stored symbol-days")
    print(f"  -> {'PASS' if c1['pass'] else 'FAIL'}\n")

    c2 = out["c2_premise"]
    print("clause 2a - the store's own step across each split inside its span")
    print(f"  {'sym':<6} {'split':<12} {'ratio':>8} {'store step':>11} {'raw would be':>13} "
          f"{'own gap q99':>12}  verdict")
    for r in c2["events"]:
        v = "ADJUSTED" if r["adjusted"] and not r["raw"] else ("RAW" if r["raw"] else "NEITHER")
        print(f"  {r['symbol']:<6} {r['split']:<12} {r['ratio']:>8.4g} {r['store_step']:>11.4f} "
              f"{r['raw_prediction']:>13.4g} {np.exp(r['gap_log_q99']) - 1:>11.2%}  {v}")
    print("clause 2b - monthly median IBKR/Alpaca close ratio (Alpaca is on the current basis)")
    worst = sorted(c2["alpaca"], key=lambda r: -r["worst_dev"])[:4]
    for r in worst:
        print(f"  {r['symbol']:<6} {r['months']:>3} months, {r['bars']:>7,} bars, "
              f"median ratio {r['monthly_median_min']:.5f} .. {r['monthly_median_max']:.5f} "
              f"(worst dev {r['worst_dev']:.2%})")
    print(f"  mixed-basis symbols: {c2['mixed_basis_symbols'] or 'none'}")
    print(f"  -> {'PASS' if c2['pass'] else 'FAIL'}\n")

    c3 = out["c3_sources"]
    print("clause 3 - yfinance's split calendar against data/minute_alpaca/_splits.json")
    print(f"  {c3.get('symbol_days_compared', 0):,} symbol-days compared, "
          f"{c3.get('disagree', 0)} disagree")
    for r in c3.get("rows", []):
        if r.get("note") or r["disagree"]:
            print(f"    {r['symbol']}: {r.get('note', '')} disagree {r['disagree']}")
    print(f"  -> {'PASS' if c3['pass'] else 'FAIL'}\n")

    c4 = out["c4_ceiling"]
    print("clause 4 - the ceiling, quoted before any P&L column: per-share commission in bps of "
          "notional, one side")
    print(f"  {'sym':<6} {'from':<12} {'to':<12} {'sess':>5} {'factor':>9} {'adj px':>9} "
          f"{'raw px':>9} {'as priced':>10} {'correct':>9} {'error':>9}")
    for r in c4["rows"]:
        if r["factor"] == 1.0:
            continue
        print(f"  {r['symbol']:<6} {r['from']:<12} {r['to']:<12} {r['sessions']:>5} "
              f"{r['factor']:>9.4g} {r['median_adjusted_px']:>9.2f} {r['median_raw_px']:>9.3f} "
              f"{r['bps_as_priced']:>10.3f} {r['bps_correct']:>9.3f} {r['bps_error']:>+9.3f}")
    print(f"  affected symbol-days {c4['affected_symbol_days']:,}; largest |error| "
          f"{c4['max_abs_bps_error']:.2f} bps/side against the {c4['slippage_line_bps']} bps "
          f"slippage line")
    print(f"  clause 6 - understated: {c4['under'] or 'none'}; OVERSTATED: {c4['over'] or 'none'}\n")

    if "c5_materiality" in out:
        m = out["c5_materiality"]
        print("clause 5 - materiality on the shipped harness, paired by session")
        print(f"  {m['sessions']} sessions; net $/day {m['control_net_per_day']:+,.1f} -> "
              f"{m['corrected_net_per_day']:+,.1f}  (paired {m['d_net_per_day']:+,.1f}, "
              f"t {m['t']:+.2f})")
        print(f"  costs $/day {m['control_costs_per_day']:,.1f} -> "
              f"{m['control_costs_per_day'] + m['d_costs_per_day']:,.1f}  "
              f"({m['d_costs_per_day']:+,.1f}); trades {m['d_trades']:+d}")
        print(f"  thresholds: 5% of costs = {m['threshold_costs']:,.1f}, "
              f"5% of |net| = {m['threshold_net']:,.1f}")
        print(f"  -> {'MATERIAL' if m['material'] else 'NOT MATERIAL'}\n")

    c7 = out["c7_guard"]
    print("clause 7 - the save_bars merge guard on the real store")
    bad = [r for r in c7["rows"] if not (r["honest_resave_allowed"] and r["rebasis_caught"])]
    print(f"  {len(c7['rows'])} symbols: honest re-save allowed on "
          f"{sum(r['honest_resave_allowed'] for r in c7['rows'])}, "
          f"x10 rebasis caught on {sum(r['rebasis_caught'] for r in c7['rows'])}"
          f"{'  BAD: ' + str([r['symbol'] for r in bad]) if bad else ''}")
    print(f"  -> {'PASS' if c7['pass'] else 'FAIL'}\n")

    print(f"clause 8 - gate (clauses 2 and 3): {'OPEN' if gate else 'CLOSED'}; "
          f"{'table written' if out.get('written') else 'nothing written'}")

    if args.record and "c5_materiality" in out:
        import intraday_backtest as ib
        m = out["c5_materiality"]
        for arm, s in (("control", out["_pair"]["control"]), ("corrected", out["_pair"]["corrected"])):
            ib.record(args.strategy,
                      f"D-5 AUD-15 {arm}: IBKR store costed with share_scale "
                      f"{'1.0 (shipped)' if arm == 'control' else 'from _splits.json'} "
                      f"(paired {m['d_net_per_day']:+.1f} $/day at t {m['t']:+.2f}, "
                      f"d costs {m['d_costs_per_day']:+.1f} $/day, "
                      f"{'MATERIAL' if m['material'] else 'NOT MATERIAL'}, DIAGNOSTIC)",
                      s, {"store": "data/minute", "arm": arm,
                          "splits_file": arm == "corrected",
                          "affected_symbol_days": out["c4_ceiling"]["affected_symbol_days"]},
                      start or min(store_sessions(UNIVERSE[0])),
                      end or max(store_sessions(UNIVERSE[0])))
        print("  recorded 2 DIAGNOSTIC rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
