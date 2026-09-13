#!/usr/bin/env python
"""A-16: the live trader's own `--replay` path costed the split-adjusted minute store as raw.

    python scripts/sweep_a16.py                    # every stored session, both arms
    python scripts/sweep_a16.py --start 2026-01-02 # a slice
    python scripts/sweep_a16.py --clauses 1,2,7    # a subset

D-5 proved `data/minute` (the IBKR store) is split-adjusted and taught `intraday_backtest.py`
to divide an order's share count by `share_scale()` before charging IBKR's per-share
commission. It filed A-16 because ONE consumer was left behind: `SimExecutor.settle` in
`scripts/intraday_trader.py`, the executor the trader's `--replay` uses. That file is loaded
by the deployed 09:25 task, so the one-line fix needs a gate, and this script is it.

Two arms, one code path. Both call `intraday_trader.replay_book()` - the deployed loop, not a
copy of it. The `pre` arm forces `share_scale -> 1.0`, which is exactly what the code did
before A-16; the `fixed` arm leaves it alone. Anything that differs between them is the defect
and nothing else, because the bars, the features, the strategy and the order arithmetic are
shared by construction.

PRE-REGISTERED CLAUSES (written before the run; each one reports whatever it finds)

  1. PREMISE. On this store `share_scale` is not 1.0 for NFLX before 2025-11-17 and for SOXS
     before 2026-07-15. State the multiplier the old code was off by, per affected segment.
  2. DEPLOYED PATH. Replay `intraday_launch.last_session()` - the session the preflight
     actually picks - under both arms. If they agree, the scheduled task never met the defect
     and this is a latent fix, not a correction to anything that ran.
  3. REACH. Every stored session, both arms: how many sessions move, the total cost delta and
     what share of the sleeve's cost line it is.
  4. ATTRIBUTION. Per symbol: fills, pre-arm cost, fixed-arm cost, delta, and the delta in bps
     of that symbol's traded notional. A-16 predicted 14.63 bps/side on SOXS; check it.
  5. CAP. IBKR's commission is capped at 1% of notional. A 200x share count is exactly what
     lands on a cap, so count the corrected fills that bind and say whether the cap - not the
     per-share rate - is what sets the corrected cost.
  6. SECOND ORDER. Cost feeds the book, the book feeds `DAILY_LOSS_LIMIT`, and the loss limit
     flattens. Do any sessions change trade count, order list or `stopped` between arms? A
     pure cost re-label is a different (and smaller) claim than a changed order list.
  7. CONVERGENCE. For every fill of a pinned session, the replay's cost must equal the
     harness's own expression `commission(q, px, share_scale(sym, day)) + slippage(q, px)`.
     This is the property A-16 asks for: one convention, two implementations.
  8. P&L. The replayed sleeve's daily P&L under both arms over the full store - mean/day, t,
     worst day - so the journal quotes a level, not just a delta.

Writes DIAGNOSTIC rows to research/experiments.jsonl (`intraday/a16_replaycost`) unless
`--no-record`. It places no orders and touches nothing in `live/`.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import math
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import intraday_common as ic  # noqa: E402
import intraday_trader as it  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"


# ----------------------------------------------------------------------------- bar cache
_FULL: dict[str, pd.DataFrame] = {}


def _full(sym: str) -> pd.DataFrame:
    if sym not in _FULL:
        _FULL[sym] = ic.load_bars(sym)
    return _FULL[sym]


def cached_load_universe(symbols=None, start=None, end=None) -> dict[str, pd.DataFrame]:
    """`ic.load_universe` with the parquet read hoisted out of the session loop.

    The slice below reproduces `load_bars`'s own start/end rule exactly; everything else
    (tz, dedup, RTH filter, calendar trim) already happened in the cached full frame, and
    none of it depends on the window.
    """
    out = {}
    for s in (symbols or ic.UNIVERSE):
        df = _full(s)
        if start is not None:
            df = df[df.index >= pd.Timestamp(start, tz=ic.ET)]
        if end is not None:
            df = df[df.index < pd.Timestamp(end, tz=ic.ET) + pd.Timedelta(days=1)]
        if not df.empty:
            out[s] = df
    return out


# ----------------------------------------------------------------------------- arms
def run_day(day: dt.date, strategy, params, scaled: bool, equity_frac: float, nav: float):
    """One replay of `day` through the deployed loop. `scaled=False` is the pre-A-16 code."""
    fills: list[tuple] = []
    real_book_fill = _REAL_BOOK_FILL
    real_scale = ic.share_scale

    def spy_book_fill(book, sym, qty, price, cost):
        fills.append((sym, int(qty), float(price), float(cost)))
        return real_book_fill(book, sym, qty, price, cost)

    it.book_fill = spy_book_fill
    if not scaled:
        it.share_scale = lambda *a, **k: 1.0
    try:
        trader = it.replay_book(strategy, params, day, equity_frac, nav)
    finally:
        it.book_fill = real_book_fill
        it.share_scale = real_scale
    return {
        "pnl": float(trader.book.pnl({})),
        "trades": int(trader.book.trades),
        "costs": float(trader.book.costs),
        "stopped": bool(trader.stopped),
        "decisions": int(trader.decisions),
        "fills": fills,
    }


_REAL_BOOK_FILL = it.book_fill


# ----------------------------------------------------------------------------- workers
#: One replay is ~7.4 s and neither the bar load (0.18 s) nor the features (0.32 s) is the
#: reason - it is the minute loop inside the DEPLOYED trader, which is not this study's to
#: change. 263 sessions x 2 arms is therefore ~65 min in one process, past the point where a
#: job cap rather than the experiment decides when it ends (AGENTS.md, "Parallel tracks"), so
#: the sessions fan out over processes. Both arms of a day stay in the same worker: they must
#: see the same cached bars, and the pairing is the whole design.
_W: dict = {}


def _worker_init(strategy_name: str, params: dict, equity_frac: float, nav: float):
    _W["strategy"] = it.load_strategy(strategy_name)
    _W["params"] = params
    _W["equity_frac"] = equity_frac
    _W["nav"] = nav
    it.load_universe = cached_load_universe
    it.log = lambda *a, **k: None          # a study writes nothing under live/
    it.notify = lambda *a, **k: None


def _worker_day(day: dt.date):
    a = run_day(day, _W["strategy"], _W["params"], False, _W["equity_frac"], _W["nav"])
    b = run_day(day, _W["strategy"], _W["params"], True, _W["equity_frac"], _W["nav"])
    return day, a, b


def _worker_day_serial(day, strategy, params, equity_frac, nav):
    a = run_day(day, strategy, params, False, equity_frac, nav)
    b = run_day(day, strategy, params, True, equity_frac, nav)
    return day, a, b


def tstat(xs: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return m / (sd / math.sqrt(n)) if sd else float("nan")


# ----------------------------------------------------------------------------- clauses
def clause1() -> dict:
    print("\n=== clause 1: PREMISE - what the pre-A-16 replay was off by ===")
    segs = ic._splits()
    rows, worst = [], 1.0
    for sym in sorted(ic.UNIVERSE):
        for start, factor in segs.get(sym.upper(), []):
            if float(factor) != 1.0:
                mult = 1.0 / float(factor)
                worst = max(worst, mult)
                rows.append((sym, start, float(factor), mult))
    print(f"{'sym':6} {'from':12} {'factor':>12} {'real shares per adjusted share':>32}")
    for sym, start, f, mult in rows:
        print(f"{sym:6} {start:12} {f:12.6g} {mult:32.1f}x")
    if not rows:
        print("  (every factor is 1.0 - the defect is unreachable on this store)")
    return {"affected_segments": len(rows), "worst_multiplier": round(worst, 2),
            "symbols": sorted({r[0] for r in rows})}


def clause2(strategy, params, equity_frac, nav) -> dict:
    print("\n=== clause 2: DEPLOYED PATH - the session the preflight picks ===")
    sys.path.insert(0, str(REPO / "scripts"))
    import intraday_launch as il
    day = il.last_session()
    if day is None:
        print("  no complete session in the store")
        return {"day": None}
    a = run_day(day, strategy, params, False, equity_frac, nav)
    b = run_day(day, strategy, params, True, equity_frac, nav)
    same = (round(a["pnl"], 6), a["trades"], round(a["costs"], 6)) == \
           (round(b["pnl"], 6), b["trades"], round(b["costs"], 6))
    print(f"  preflight session {day}")
    print(f"  pre   : P&L {a['pnl']:+,.0f}  trades {a['trades']}  costs {a['costs']:,.2f}")
    print(f"  fixed : P&L {b['pnl']:+,.0f}  trades {b['trades']}  costs {b['costs']:,.2f}")
    print(f"  identical: {same}  -> the 09:25 task {'never met' if same else 'MET'} the defect")
    return {"day": str(day), "identical": same, "costs_pre": round(a["costs"], 2),
            "costs_fixed": round(b["costs"], 2)}


def clause7(day: dt.date, strategy, params, equity_frac, nav) -> dict:
    print(f"\n=== clause 7: CONVERGENCE - every fill on {day} priced the harness's way ===")
    b = run_day(day, strategy, params, True, equity_frac, nav)
    bad = 0
    for sym, q, px, cost in b["fills"]:
        want = ic.commission(q, px, ic.share_scale(sym, day)) + ic.slippage(q, px)
        if abs(want - cost) > 1e-9:
            bad += 1
    print(f"  {len(b['fills']) - bad}/{len(b['fills'])} fills reproduce the harness expression exactly")
    return {"fills": len(b["fills"]), "mismatches": bad}


# ----------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strategy", default=None, help="default: live/intraday_config.json")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--nav", type=float, default=1_000_000)
    ap.add_argument("--equity-frac", type=float, default=None)
    ap.add_argument("--clauses", default="1,2,3,4,5,6,7,8")
    ap.add_argument("--workers", type=int, default=4, help="processes for the session fan-out")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()
    want = {int(c) for c in args.clauses.split(",") if c.strip()}

    cfg = json.loads((REPO / "live" / "intraday_config.json").read_text(encoding="utf-8"))
    strategy = it.load_strategy(args.strategy or cfg.get("strategy", "active"))
    params = {**strategy.PARAMS, **cfg.get("params", {})}
    equity_frac = args.equity_frac if args.equity_frac is not None else float(cfg.get("equity_frac", 1.0))
    print(f"strategy={args.strategy or cfg.get('strategy')} equity_frac={equity_frac} nav={args.nav:,.0f} "
          f"store={ic.DATA_DIR.name}")

    # the cache is what makes 2 x N replays finish inside a job slot; the log is silenced
    # because a study must leave no trace under live/ (AGENTS.md red lines)
    it.load_universe = cached_load_universe
    it.log = lambda *a, **k: None
    it.notify = lambda *a, **k: None

    rows = []
    if 1 in want:
        rows.append(("clause1", clause1()))
    if 2 in want:
        rows.append(("clause2", clause2(strategy, params, equity_frac, args.nav)))

    days = sorted(set().union(*[set(_full(s).index.date) for s in ic.UNIVERSE]))
    if args.start:
        days = [d for d in days if str(d) >= args.start]
    if args.end:
        days = [d for d in days if str(d) <= args.end]

    if 7 in want:
        rows.append(("clause7", clause7(days[len(days) // 3], strategy, params, equity_frac, args.nav)))

    if want & {3, 4, 5, 6, 8}:
        print(f"\n=== clauses 3-6,8: replaying {len(days)} sessions x 2 arms ===")
        per_sym: dict[str, list[float]] = {}
        moved, order_diff, stop_diff = 0, 0, 0
        d_cost_tot, pre_cost_tot, fix_cost_tot = 0.0, 0.0, 0.0
        pnl_pre, pnl_fix, capped, total_fills = [], [], 0, 0
        if args.workers > 1:
            ctx = cf.ProcessPoolExecutor(
                max_workers=args.workers, initializer=_worker_init,
                initargs=(args.strategy or cfg.get("strategy", "active"), params, equity_frac, args.nav))
            with ctx as pool:
                done = []
                for k, res in enumerate(pool.map(_worker_day, days, chunksize=1), 1):
                    done.append(res)
                    if k % 25 == 0:
                        print(f"  ... {k}/{len(days)} sessions")
                done.sort(key=lambda r: r[0])
        else:
            done = [_worker_day_serial(d, strategy, params, equity_frac, args.nav) for d in days]
        for i, (day, a, b) in enumerate(done):
            pnl_pre.append(a["pnl"])
            pnl_fix.append(b["pnl"])
            pre_cost_tot += a["costs"]
            fix_cost_tot += b["costs"]
            d_cost_tot += b["costs"] - a["costs"]
            if abs(b["costs"] - a["costs"]) > 1e-6:
                moved += 1
            if [(s, q) for s, q, _, _ in a["fills"]] != [(s, q) for s, q, _, _ in b["fills"]]:
                order_diff += 1
            if a["stopped"] != b["stopped"]:
                stop_diff += 1
            pa = {}
            for sym, q, px, cost in a["fills"]:
                pa.setdefault(sym, [0, 0.0, 0.0, 0.0])
                pa[sym][0] += 1
                pa[sym][1] += cost
                pa[sym][3] += abs(q) * px
            for sym, q, px, cost in b["fills"]:
                pa.setdefault(sym, [0, 0.0, 0.0, 0.0])
                pa[sym][2] += cost
                total_fills += 1
                sc = ic.share_scale(sym, day)
                real = abs(q) / (sc or 1.0)
                if min(max(ic.COMMISSION_MIN, real * ic.COMMISSION_PER_SHARE),
                       0.01 * abs(q) * px) == 0.01 * abs(q) * px:
                    capped += 1
            for sym, v in pa.items():
                r = per_sym.setdefault(sym, [0, 0.0, 0.0, 0.0])
                for j in range(4):
                    r[j] += v[j]
        n = len(days)
        if 3 in want:
            print("\n=== clause 3: REACH ===")
            print(f"  sessions replayed            {n}")
            print(f"  sessions whose cost moved    {moved} ({moved / n:.1%})")
            print(f"  cost line, pre-A-16          ${pre_cost_tot:,.2f}  (${pre_cost_tot / n:,.0f}/day)")
            print(f"  cost line, corrected         ${fix_cost_tot:,.2f}  (${fix_cost_tot / n:,.0f}/day)")
            print(f"  delta                        ${d_cost_tot:+,.2f}  "
                  f"({d_cost_tot / pre_cost_tot:+.2%} of the pre line, ${d_cost_tot / n:+,.0f}/day)")
            rows.append(("clause3", {"sessions": n, "sessions_moved": moved,
                                     "costs_pre": round(pre_cost_tot, 2),
                                     "costs_fixed": round(fix_cost_tot, 2),
                                     "delta": round(d_cost_tot, 2),
                                     "delta_pct_of_pre": round(100 * d_cost_tot / pre_cost_tot, 3),
                                     "delta_per_day": round(d_cost_tot / n, 2)}))
        if 4 in want:
            print("\n=== clause 4: ATTRIBUTION ===")
            print(f"{'sym':6} {'fills':>6} {'pre $':>12} {'fixed $':>12} {'delta $':>12} "
                  f"{'notional $':>16} {'delta bps':>10}")
            att = {}
            for sym, (f, pre, fix, notl) in sorted(per_sym.items(), key=lambda kv: -abs(kv[1][2] - kv[1][1])):
                bps = 1e4 * (fix - pre) / notl if notl else 0.0
                print(f"{sym:6} {f:6d} {pre:12,.2f} {fix:12,.2f} {fix - pre:+12,.2f} {notl:16,.0f} {bps:+10.2f}")
                if abs(fix - pre) > 1e-6:
                    att[sym] = {"fills": f, "pre": round(pre, 2), "fixed": round(fix, 2),
                                "delta": round(fix - pre, 2), "delta_bps_of_side": round(bps, 3)}
            rows.append(("clause4", att))
        if 5 in want:
            print("\n=== clause 5: CAP ===")
            print(f"  corrected fills that bind the 1% notional cap: {capped}/{total_fills} "
                  f"({capped / total_fills:.1%})" if total_fills else "  no fills")
            rows.append(("clause5", {"fills": total_fills, "capped": capped,
                                     "capped_share": round(capped / total_fills, 4) if total_fills else 0.0}))
        if 6 in want:
            print("\n=== clause 6: SECOND ORDER ===")
            print(f"  sessions with a different order list : {order_diff}")
            print(f"  sessions with a different loss-limit stop: {stop_diff}")
            rows.append(("clause6", {"order_list_differs": order_diff, "stop_differs": stop_diff}))
        if 8 in want:
            print("\n=== clause 8: P&L ===")
            for name, xs in (("pre", pnl_pre), ("fixed", pnl_fix)):
                print(f"  {name:6} mean/day ${sum(xs) / n:+,.0f}  t {tstat(xs):+.2f}  "
                      f"worst ${min(xs):+,.0f}  total ${sum(xs):+,.0f}")
            d = [b - a for a, b in zip(pnl_pre, pnl_fix)]
            print(f"  paired delta mean/day ${sum(d) / n:+,.2f}  t {tstat(d):+.2f}")
            rows.append(("clause8", {
                "pnl_per_day_pre": round(sum(pnl_pre) / n, 2), "t_pre": round(tstat(pnl_pre), 3),
                "pnl_per_day_fixed": round(sum(pnl_fix) / n, 2), "t_fixed": round(tstat(pnl_fix), 3),
                "worst_pre": round(min(pnl_pre), 2), "worst_fixed": round(min(pnl_fix), 2)}))

    if not args.no_record:
        with LEDGER.open("a", encoding="utf-8") as fh:
            for name, payload in rows:
                fh.write(json.dumps({
                    "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                    "algorithm": "intraday/a16_replaycost", "class": "intraday",
                    "tag": f"A-16 DIAGNOSTIC {name}: replay executor costed the adjusted store as raw",
                    "track": "A-16", "start": str(days[0]) if days else None,
                    "end": str(days[-1]) if days else None,
                    "stats": {k: str(v) for k, v in payload.items()} if isinstance(payload, dict) else {},
                }, default=str) + "\n")
        print(f"\nrecorded {len(rows)} DIAGNOSTIC rows -> research/experiments.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
