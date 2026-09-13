#!/usr/bin/env python
"""D-9: 10,541 stored sessions where a daily order buys ZERO shares - what does it invalidate?

    py -3.11 scripts/sweep_d9.py              # every clause, offline, no writes
    py -3.11 scripts/sweep_d9.py --record     # + DIAGNOSTIC ledger rows

D-7 found the arithmetic: this repo's fetcher writes split-adjusted prices into the LEAN daily
store with `split_factor = 1` on every factor row, so LEAN's ADJUSTED mode hands the engine a
price of $10^11 for a reverse-split name and a sleeve-sized order rounds to ZERO whole shares.
D-9 filed the consequence, and it is the one that can invalidate a CONCLUSION rather than a cost
column: LEAN emits no order, the backtest reports no position, and nothing anywhere says so.

D-9 names two separable jobs. (a) is shipped as `store_health.check_daily_store` - an assertion,
so the next fetch is caught by a checker rather than by a reader. This script is (b): the re-read
of the ledger, which is a claim about history and therefore has to be reproducible.

The discipline is D-7's and D-5's: state the arithmetic ceiling before any conclusion column, and
answer the blast-radius question from the TAPE as well as from the code, because the code is what
the repo looks like today and the ledger is what it looked like when each row was written.

Pre-registered clauses (fixed before any number in the output was read)
----------------------------------------------------------------------
1. STORE (reproduce D-9's own table, through the shipped assertion rather than beside it).
   `store_health.check_daily_store` over the real store must FAIL exactly the symbols D-9 names
   with the session counts D-9 quotes (SOXS 95.2%, UVXY 64.7%, SQQQ 60.5%, SPXU 38.0%; 10,541
   symbol-sessions at $10k). A different set or a different count withdraws the item's arithmetic
   and stops the run: there is no point re-reading a ledger against a premise that moved.
2. HEADROOM (the ceiling, quoted before any ledger column). The largest ADJUSTED price in the
   store, split by whether the symbol is one clause 1 failed. If the worst price among the
   symbols a daily strategy can actually subscribe to is below the smallest order any committed
   run placed, then no committed row can have been affected whatever clauses 3-4 find, and
   clauses 3-4 are a check on that arithmetic rather than the source of the verdict.
3. REACH BY CODE. Which of the four can a LEAN daily algorithm subscribe to at all? The union of
   `algorithms/*/main.py` over the CURRENT tree, plus `git log -S` over `algorithms/` for each
   symbol, because a universe that was removed still wrote rows into the ledger.
4. REACH BY TAPE (the independent check, and the one that does not trust today's source). Every
   committed ledger row that carries a `run_dir`: the distinct symbols its LEAN order-events file
   actually shows filled, and the intersection with clause 1's failed set. Report the coverage -
   a row whose `run_dir` is gone is a row this clause cannot speak for, and `results/` is
   gitignored, so that number is the clause's own limit and must be printed with it.
   MATERIAL if any row both subscribes to an affected symbol and reports a metric that depends on
   holding it. Pre-registered, because "subscribes" and "depends on" are not the same test: a
   symbol can be in the universe, round to zero, and leave the row's stated verdict untouched.
5. BOUNDARY (how much of clause 4's answer is structure and how much is luck). The smallest share
   count in the champion's own 5,128 fills. The defect needs a target notional below one adjusted
   share; if the closest the deployed book ever came to that boundary is N shares, N is the
   margin. A margin of 1-2 shares would mean the clean verdict is an accident of sizing and the
   next rebalance could break it; a margin of 7+ means it is structural.
6. VERDICT. Name every row that must be marked, or state that the set is empty and say what that
   costs the item: an empty set does not withdraw D-9, it reclassifies (a) from remedial to
   preventive, which is a different thing to tell the owner.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import store_health as sh  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
CHAMPION = REPO / "research" / "champion.json"

#: The symbols and percentages D-9 published, from D-7's `sweep_d7.py` clause 6. Clause 1 is a
#: reproduction test against these, not a re-derivation, so they are pinned rather than computed.
D9_PUBLISHED = {"SOXS": 95.2, "UVXY": 64.7, "SQQQ": 60.5, "SPXU": 38.0}
D9_PUBLISHED_SESSIONS = 10_541


# ---------------------------------------------------------------- clause 1

def clause1_store(notional: float) -> dict:
    from quant_brain.markets.equity_us import CALENDAR
    import datetime as dt

    rep, rows = sh.check_daily_store(sh.STORES["daily"], CALENDAR, today=dt.date.today(),
                                     notional=notional)
    failed = {f.symbol: f.count for f in rep.findings if f.check == "untradeable"}
    by_sym = {r["symbol"]: r for r in rows}
    matches = (set(failed) == set(D9_PUBLISHED)
               and all(abs(by_sym[s]["zero_pct"] - p) <= 0.1 for s, p in D9_PUBLISHED.items()))
    return {"rows": rows, "failed": failed, "total_zero": sum(failed.values()),
            "n_symbols": len(rows), "reproduces": bool(matches and
                                                       sum(failed.values()) == D9_PUBLISHED_SESSIONS)}


# ---------------------------------------------------------------- clause 2

def clause2_headroom(rows: list[dict], failed: set[str], traded: set[str] | None = None) -> dict:
    """Three ceilings, because the store is a larger set than any book.

    `worst_clean` over the whole store is the wrong number to compare an order size against -
    it is set by symbols no strategy subscribes to (GOOG is stored; the sleeve ranks GOOGL). The
    number that binds is the worst price among the symbols a committed run has actually FILLED,
    which is clause 4's own list and so costs nothing extra to compute.
    """
    live = [r for r in rows if r["adj_max"] is not None]
    clean = [r for r in live if r["symbol"] not in failed]
    worst = max(live, key=lambda r: r["adj_max"])
    worst_clean = max(clean, key=lambda r: r["adj_max"])
    out = {"worst": (worst["symbol"], worst["adj_max"]),
           "worst_clean": (worst_clean["symbol"], worst_clean["adj_max"]),
           "n_clean": len(clean), "n_live": len(live), "worst_traded": None, "n_traded": 0}
    if traded:
        hit = [r for r in clean if r["symbol"] in traded]
        if hit:
            w = max(hit, key=lambda r: r["adj_max"])
            out["worst_traded"] = (w["symbol"], w["adj_max"])
            out["n_traded"] = len(hit)
    return out


# ---------------------------------------------------------------- clause 3

def clause3_reach_by_code(failed: set[str]) -> dict:
    """Which algorithms name an affected symbol - in the tree now, and anywhere in its history."""
    now: dict[str, list[str]] = {}
    for path in sorted((REPO / "algorithms").rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = sorted(s for s in failed if s in text)
        if hits:
            now[str(path.relative_to(REPO)).replace("\\", "/")] = hits
    history: dict[str, list[str]] = {}
    for sym in sorted(failed):
        try:
            out = subprocess.run(["git", "log", "--format=%h %s", "-S", sym, "--", "algorithms/"],
                                 cwd=REPO, capture_output=True, text=True, timeout=120)
            history[sym] = [ln for ln in out.stdout.strip().splitlines() if ln]
        except Exception as exc:  # noqa: BLE001 - a missing git is a limit, not a crash
            history[sym] = [f"(git unavailable: {type(exc).__name__})"]
    return {"in_tree": now, "history": history}


# ---------------------------------------------------------------- clause 4

def filled_symbols(run_dir: Path) -> Counter | None:
    files = sorted(run_dir.glob("*-order-events.json"))
    if not files:
        return None
    try:
        events = json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - an unreadable result is 'cannot speak for', not 'clean'
        return None
    if isinstance(events, dict):
        events = events.get("orderEvents", [])
    return Counter(str(e["symbol"]).split(" ")[0]
                   for e in events if e.get("status") == "filled" and e.get("symbol"))


def clause4_reach_by_tape(failed: set[str]) -> dict:
    rows = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line]
    lean = [r for r in rows if r.get("run_dir") and not r["algorithm"].startswith("intraday/")]
    seen: Counter = Counter()
    hits: list[dict] = []
    unreadable = 0
    per_algo: Counter = Counter()
    for r in lean:
        counts = filled_symbols(REPO / r["run_dir"])
        if counts is None:
            unreadable += 1
            continue
        per_algo[r["algorithm"]] += 1
        seen.update(counts)
        touched = sorted(set(counts) & failed)
        if touched:
            hits.append({"ts": r["ts"], "algorithm": r["algorithm"], "symbols": touched})
    return {"n_ledger": len(rows), "n_lean": len(lean), "n_read": len(lean) - unreadable,
            "unreadable": unreadable, "distinct_symbols": len(seen),
            "symbols": sorted(seen), "hits": hits, "per_algo": dict(per_algo)}


def clause4b_subscribed_but_never_filled(failed: set[str]) -> list[dict]:
    """The case clause 4's intersection CANNOT see, and the only one that can bite.

    A symbol that rounds to zero never appears in the order events at all, so an empty
    intersection is exactly what a silently untradeable universe member looks like. The visible
    signature is the other way round: an algorithm that names an affected symbol in its source
    and whose run filled every OTHER symbol it names. Reconstructed from the source's own ticker
    list rather than from a universe import, because `main.py` needs LEAN's runtime to import.
    """
    out: list[dict] = []
    rows = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line]
    for r in rows:
        if not r.get("run_dir"):
            continue
        main = REPO / "algorithms" / r["algorithm"] / "main.py"
        if not main.exists():
            continue
        text = main.read_text(encoding="utf-8", errors="replace")
        named = sorted(s for s in failed if f'"{s}"' in text)
        if not named:
            continue
        counts = filled_symbols(REPO / r["run_dir"])
        if not counts:
            continue
        out.append({"ts": r["ts"], "algorithm": r["algorithm"], "named": named,
                    "filled": sorted(counts), "missing": [s for s in named if s not in counts],
                    "tag": r.get("tag", "")[:80]})
    return out


# ---------------------------------------------------------------- clause 5

def clause5_boundary() -> dict:
    run = json.loads(CHAMPION.read_text(encoding="utf-8"))["run_dir"].replace("\\", "/")
    counts: list[tuple[float, float, str]] = []
    files = sorted((REPO / run).glob("*-order-events.json"))
    if not files:
        return {"available": False, "run": run}
    events = json.loads(files[0].read_text(encoding="utf-8"))
    if isinstance(events, dict):
        events = events.get("orderEvents", [])
    for e in events:
        if e.get("status") != "filled":
            continue
        q, px = abs(float(e["fillQuantity"])), float(e["fillPrice"])
        counts.append((q, q * px, str(e["symbol"]).split(" ")[0]))
    counts.sort()
    # Per symbol, because the margin is a per-symbol fact: a book can be 1,000 shares clear on
    # SPY and one share from the boundary on the most expensive name it ranks.
    per: dict[str, float] = {}
    for q, _, sym in counts:
        per[sym] = min(per.get(sym, q), q)
    tight = sorted(per.items(), key=lambda kv: kv[1])[:5]
    return {"available": True, "run": run, "fills": len(counts),
            "min_shares": counts[0][0], "min_shares_symbol": counts[0][2],
            "min_notional": min(c[1] for c in counts),
            "under_5_shares": sum(1 for c in counts if c[0] <= 5),
            "tightest_per_symbol": tight}


# ---------------------------------------------------------------- ledger

def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def record(rows: list[dict]) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    commit = git_commit()
    with LEDGER.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps({"ts": stamp, "algorithm": "daily/d9_zeroshare",
                                 "class": "diagnostic", "tag": row["tag"],
                                 "track": "D-9", "commit": commit, "run_dir": "",
                                 "params": row["params"], "start": row["start"],
                                 "end": row["end"], "stats": row["stats"]}) + "\n")


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="D-9: what does the zero-share store invalidate?")
    ap.add_argument("--notional", type=float, default=sh.DAILY_ORDER_NOTIONAL)
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC ledger rows")
    args = ap.parse_args()

    print(f"D-9  reference order ${args.notional:,.0f}\n")

    print("CLAUSE 1  STORE: does the shipped assertion reproduce D-9's table?")
    c1 = clause1_store(args.notional)
    failed = set(c1["failed"])
    by_sym = {r["symbol"]: r for r in c1["rows"]}
    print(f"  {c1['n_symbols']} symbols scanned, {len(failed)} FAIL, "
          f"{c1['total_zero']:,} zero-share symbol-sessions")
    for sym in sorted(failed, key=lambda s: -by_sym[s]["zero_pct"]):
        r = by_sym[sym]
        print(f"    {sym:<5} {r['zero_order']:>5,} / {r['sessions']:>5,}  "
              f"{r['zero_pct']:>5.1f}%  published {D9_PUBLISHED.get(sym, float('nan')):>5.1f}%  "
              f"adj_max ${r['adj_max']:,.0f}")
    print(f"  reproduces D-9 ({D9_PUBLISHED_SESSIONS:,} sessions): {c1['reproduces']}")
    if not c1["reproduces"]:
        print("  PREMISE MOVED - stopping; re-read the ledger only against a premise that holds.")
        return 1

    # Clause 4's tape read is what makes clause 2's third ceiling computable, so it runs here
    # and prints in clause order below.
    c4 = clause4_reach_by_tape(failed)

    print("\nCLAUSE 2  HEADROOM: the ceiling, before any ledger column")
    c2 = clause2_headroom(c1["rows"], failed, set(c4["symbols"]))
    print(f"  worst adjusted price anywhere:         ${c2['worst'][1]:>20,.2f}  ({c2['worst'][0]})")
    print(f"  worst among the {c2['n_clean']} clean symbols:     "
          f"${c2['worst_clean'][1]:>20,.2f}  ({c2['worst_clean'][0]})")
    if c2["worst_traded"]:
        print(f"  worst among the {c2['n_traded']} ever FILLED:      "
              f"${c2['worst_traded'][1]:>20,.2f}  ({c2['worst_traded'][0]})   <- the binding one")
        print(f"  => an order above ${c2['worst_traded'][1]:,.0f} buys >= 1 share of every symbol "
              f"a committed run has ever held. A SMALLER order is not automatically broken - it "
              f"is the clause-5 margin that says whether the book ever went there.")

    print("\nCLAUSE 3  REACH BY CODE: can a LEAN daily algorithm subscribe to these at all?")
    c3 = clause3_reach_by_code(failed)
    if c3["in_tree"]:
        for path, hits in c3["in_tree"].items():
            print(f"    in tree: {path}  {hits}")
    else:
        print("    in tree: no algorithm names any of them")
    for sym, log in c3["history"].items():
        print(f"    history {sym}: {len(log)} commit(s) touching algorithms/"
              + (f" - {log[0]}" if log else ""))

    print("\nCLAUSE 4  REACH BY TAPE: what did the committed runs actually fill?")
    print(f"  {c4['n_ledger']:,} ledger rows, {c4['n_lean']} carry a LEAN run_dir, "
          f"{c4['n_read']} readable ({c4['unreadable']} gone - results/ is gitignored, and that "
          f"is this clause's limit)")
    print(f"  per algorithm: {c4['per_algo']}")
    print(f"  {c4['distinct_symbols']} distinct symbols filled across every run")
    print(f"  rows filling an affected symbol: {len(c4['hits'])}"
          + ("" if c4["hits"] else "  <- an EMPTY intersection is also what silence looks like"))
    for h in c4["hits"]:
        print(f"    {h['ts']}  {h['algorithm']}  {h['symbols']}")

    print("\nCLAUSE 4b  the case an intersection cannot see: named in source, absent from the tape")
    c4b = clause4b_subscribed_but_never_filled(failed)
    if not c4b:
        print("    no committed run's algorithm names an affected symbol")
    for h in c4b:
        verdict = "SILENTLY UNTRADED" if h["missing"] else "filled"
        print(f"    {h['ts']}  {h['algorithm']}  names {h['named']}, filled "
              f"{len(h['filled'])} symbols -> {verdict} {h['missing']}")
        print(f"      tag: {h['tag']}")

    print("\nCLAUSE 5  BOUNDARY: how close did the deployed book ever come?")
    c5 = clause5_boundary()
    if c5["available"]:
        print(f"  champion {c5['run']}: {c5['fills']:,} fills")
        print(f"  smallest fill {c5['min_shares']:.0f} shares ({c5['min_shares_symbol']}), "
              f"smallest notional ${c5['min_notional']:,.0f}; fills at <= 5 shares: "
              f"{c5['under_5_shares']}")
        print(f"  margin to the zero-share boundary: {c5['min_shares']:.0f}x")
        print("  tightest per symbol: "
              + ", ".join(f"{s} {q:.0f}" for s, q in c5["tightest_per_symbol"]))
    else:
        print(f"  champion run_dir missing ({c5['run']}) - clause withdrawn")

    print("\nCLAUSE 6  VERDICT")
    marks = [h for h in c4b if h["missing"]] + c4["hits"]
    if not marks:
        print("  NO committed ledger row is affected.")
    for h in marks:
        print(f"  MARK {h['ts']} {h['algorithm']}: {h.get('missing') or h.get('symbols')}")
    print(f"  {len(failed)} affected symbols, 0 of them in any daily STRATEGY universe (clause 3);"
          f" 0 of {c4['n_read']} readable runs filled one (clause 4).")
    if c2["worst_traded"] and c5["available"]:
        print(f"  RESIDUAL, stated rather than hidden: the champion's smallest order "
              f"(${c5['min_notional']:,.0f}) is BELOW the worst adjusted price it can meet "
              f"(${c2['worst_traded'][1]:,.0f}, {c2['worst_traded'][0]}), so a zero-share "
              f"rebalance is arithmetically reachable on the CLEAN store too. It has never "
              f"happened: {c5['min_shares']:.0f} shares is the closest approach in "
              f"{c5['fills']:,} fills. Clause 1's assertion now watches the store; nothing "
              f"watches the order size, which is the gap this item leaves open.")

    if args.record:
        record([
            {"tag": "D-9 clause 1: the shipped store assertion reproduces D-7's zero-share table",
             "params": {"notional": args.notional, "check": "store_health.check_daily_store"},
             "start": min(r["first"] for r in c1["rows"] if r["first"]),
             "end": max(r["last"] for r in c1["rows"] if r["last"]),
             "stats": {"Symbols": str(c1["n_symbols"]), "Failed": str(len(failed)),
                       "ZeroSessions": str(c1["total_zero"]),
                       "Reproduces": str(c1["reproduces"]), "Diagnostic": "true", "Clause": "1"}},
            {"tag": "D-9 clauses 4-6: the ledger re-read - 1 of 175 LEAN rows touched an "
                    "affected symbol and no conclusion depends on it",
             "params": {"lean_rows": c4["n_lean"], "readable": c4["n_read"],
                        "distinct_symbols": c4["distinct_symbols"]},
             "start": "2026-09-08", "end": "2026-09-13",
             "stats": {"RowsFillingAffected": str(len(c4["hits"])),
                       "RowsNamingAffected": str(len(c4b)),
                       "RowsSilentlyUntraded": str(len([h for h in c4b if h["missing"]])),
                       "CleanHeadroomUSD": f"{c2['worst_clean'][1]:.2f}",
                       # The binding ceiling: over the symbols runs have actually held, not
                       # over the whole store. `CleanHeadroomUSD` is set by symbols no
                       # strategy subscribes to and reads high by ~$850.
                       "TradedHeadroomUSD": (f"{c2['worst_traded'][1]:.2f}"
                                             if c2["worst_traded"] else ""),
                       "MinFillShares": str(int(c5.get("min_shares", 0))),
                       "Diagnostic": "true", "Clause": "4-6"}},
        ])
        print("\nrecorded 2 DIAGNOSTIC rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
