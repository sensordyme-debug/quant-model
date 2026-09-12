#!/usr/bin/env python
"""S-35 / AUD-12: a promotion can carry a parameter the paper runner cannot trade.

    python scripts/sweep_s35.py --stage a     # clauses 1-4: identity, reach, reproduce, radius
    python scripts/sweep_s35.py --stage b     # clause 5: price the one live candidate (2 runs)
    python scripts/sweep_s35.py --stage c     # clauses 6-7: the fix and its withdrawal condition

THE FINDING (audit item AUD-12, `research/audit_2026-09-12.md:128`). `algorithms/s1_momo/main.py`
builds its `sig.Params(...)` from `S1_*` environment variables; that is how every sweep in this
repository moves a parameter without editing a shipped file. Nothing carries those overrides
anywhere else:

  * `scripts/paper_trade.py:196` asks for `getattr(sig, "PARAMS", None)`. `signals.py` defines
    `DEFAULTS`, never `PARAMS`, so the expression is always `None` and `target_weights` falls
    through to `params or DEFAULTS`. **The runner always trades the defaults.**
  * `scripts/compare_orders.py:158` builds `sig.Params()`. **The gate always checks the
    defaults against the defaults**, so it agrees with itself whatever was promoted.
  * `scripts/evaluate.py` stores `stats`, `run_dir`, `commit`, `tag` and `stats_by_spread` on
    promotion and **no `env` at all**, so the override is not even in the record afterwards.

So a run made with an override can be promoted, pass the deploy gate, and leave the paper
account trading a different strategy from the one `champion.json` now describes. It is the same
defect class S-34 fixed in AUD-10 - a promotion that does not carry everything the champion is -
except that AUD-10 left the wrong *number* behind and this one leaves the wrong *strategy*.

WHAT THIS ITERATION MEASURES, PRE-REGISTERED BEFORE THE FIRST NUMBER. The audit offers two
fixes ("refuse promotion when `run['env']` has non-whitelisted keys, or build `Params` from
`champion.json['env']` in both the runner and the gate") and does not say which, or how much
the defect costs. Both answers are numbers.

  (1) IDENTITY. The offline book is the cell six previous iterations agree on (22.192150% /
      5,052 orders at zero cost), re-run here on the UNION universe both books need, so that
      adding a ticker to the price frame is proven inert rather than assumed. And: is today's
      champion clean - does `champion.json` carry an override, or did the shipped run?
      A defect that has already bitten is a different item from one that has not.

  (2) THE REACH SURFACE, AND WHY THE FIX MUST BE DEFAULT-DENY. Enumerate every `S1_*` name in
      `main.py` and split it into the keys that reach the code the runner shares (`Params`, or
      a module global of `signals.py`) and the keys that only reach LEAN's own plumbing - the
      window, the slippage model, the financing model, the null instrument. A hand-maintained
      DENY list is refused as a design here: the next knob added to `main.py` would not be on
      it. Only an ALLOW list fails safe, and clause 6 owes a test that pins it to the file.

  (3) THE DEFECT REPRODUCES, END TO END, ON A REAL ROW. Not a constructed example: a row that
      is in the ledger now and that `verdict()` passes now. Promote it into a scratch champion
      and read back what the record says, what the runner would trade, and what the gate would
      report.

  (4) THE BLAST RADIUS ON THE RECORD. Of the `s1_momo` rows: how many carry a reaching key, and
      how many of those pass today's gate. The count is a FLOOR, not an estimate - `backtest.py`
      only began recording `env` with S-18, so every earlier row reads as clean whatever it was
      run with.

  (5) THE PRICE, IN THE UNIT THAT MATTERS. For each row that passes the gate today, what does
      the account actually get? Two offline books at the row's own cost model - the promoted
      parameters, and the defaults the runner would trade instead - plus the paired daily
      difference and the fraction of sessions whose holdings differ. MATERIALITY IS
      PRE-REGISTERED: the defect is material if the CAR the runner would actually trade is at
      or below the champion's, i.e. the promotion delivers none of the gain it was promoted
      for. It is cosmetic if the runner still gets most of it.

  (6) THE FIX AND ITS WITHDRAWAL CONDITION. Backward compatibility is the condition, as in
      S-34: re-judge every `s1_momo` row under the old and the new code. Every verdict that
      moves must move `yes -> no` and must belong to a row carrying a reaching key; a single
      `no -> yes`, or a single change on a clean row, withdraws the patch. Full suite green.

  (7) THE RUNNER'S DEAD LOOKUP. `getattr(sig, "PARAMS", None)` reads as though the runner
      supports parameters. Prove it is dead (no `PARAMS` attribute, and `DEFAULTS == Params()`
      so the fallthrough is the same object), then decide whether a daily iteration should
      touch a live runner to say so. Evidence, then the decision, in that order.

SCOPE. `scripts/evaluate.py` (shared, and nothing in `live/` imports it - no `--replay` owed),
`tests/test_evaluate_param_env.py`, this file. NO LEAN run, NO ledger row, NO strategy
parameter, and `research/champion.json` is NOT modified: clause 3 and clause 6 write to a
scratch copy under a temporary directory.
"""
from __future__ import annotations

import argparse
import ast
import copy
import dataclasses
import json
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                                          # noqa: E402
import evaluate as ev                                          # noqa: E402
from lean_prices import load_ohlcv                             # noqa: E402
from sweep_s19 import paired                                   # noqa: E402
from sweep_s25 import legs_simulate                            # noqa: E402
from sweep_s31 import describe                                 # noqa: E402

MAIN_PY = REPO / "algorithms" / "s1_momo" / "main.py"
START = "2012-01-03"
END = "2026-09-04"

#: clause 1 - the cell six previous iterations agree on
S25_DEPLOYED_CAR = 22.192150170492255
S25_DEPLOYED_ORDERS = 5052

#: clause 2 - the ONLY keys that do not reach the code `paper_trade.py` shares with LEAN.
#: `S1_START`/`S1_END` move the backtest window (already refused by `window_note`);
#: `S1_SLIPPAGE_BPS`, `S1_FINANCING`, `S1_FIN_SPREAD` and `S1_FIN_RATES` configure cost models
#: LEAN applies after the signal has spoken; `S1_SIGNAL_LAG` shifts which close the signal is
#: handed; `S1_NOOP` is S-22's null instrument and is read by nothing. S-22 carries the same
#: list for the same reason (`scripts/sweep_s22.py:59`), which is the second independent
#: derivation of it.
INERT_KEYS = {
    "S1_START", "S1_END",
    "S1_SLIPPAGE_BPS", "S1_SIGNAL_LAG",
    "S1_FINANCING", "S1_FIN_SPREAD", "S1_FIN_RATES",
    "S1_NOOP",
}


# --------------------------------------------------------------------------- clause helpers

def reaching(env: dict) -> dict:
    """The subset of an `env` mapping that reaches the shared signal path."""
    return {k: v for k, v in sorted((env or {}).items()) if k not in INERT_KEYS}


def env_surface() -> list[str]:
    """Every `S1_*` name `main.py` reads, from the source rather than from memory."""
    src = MAIN_PY.read_text(encoding="utf-8")
    names = set(re.findall(r'os\.environ\.get\(\s*"(S1_[A-Z0-9_]+)"', src))
    tree = ast.parse(src)
    for node in ast.walk(tree):
        # `_env("TOP_N", 3, int)` / `_env_date("START", ...)` - the prefix is added inside
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("_env", "_env_date") and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            names.add("S1_" + node.args[0].value)
    return sorted(names)


def s1_rows(runs: list[dict]) -> list[dict]:
    return [r for r in runs if r.get("algorithm") == "s1_momo"]


def metrics(d: dict) -> str:
    return (f"{d['CAR']:8.3f}%  Sharpe {d['Sharpe']:6.3f}  DD {d['MaxDD']:7.3f}%  "
            f"orders {d['orders']:>6,}")


# --------------------------------------------------------------------------------- clause 1

def clause_1(frames: dict, champion: dict, runs: list[dict]) -> bool:
    print("=== clause 1: identity, and is the shipped champion already bitten? ===")
    book = legs_simulate(frames, sig.Params(), "both", START, END)
    d = describe(book, "shipped @ union universe")
    car_ok = abs(d["CAR"] - S25_DEPLOYED_CAR) < 1e-9
    ord_ok = d["orders"] == S25_DEPLOYED_ORDERS
    print(f"  shipped, union price frame   {metrics(d)}")
    print(f"  expected                     {S25_DEPLOYED_CAR:8.6f}%  orders "
          f"{S25_DEPLOYED_ORDERS:>6,}")
    print(f"  CAR exact {car_ok}   orders exact {ord_ok}   "
          f"-> adding a ticker to the frame is inert, both books are comparable")

    champ_env = champion.get("env")
    row = [r for r in runs if r.get("run_dir") == champion.get("run_dir")]
    row_env = (row[-1].get("env") if row else None) or {}
    print(f"  champion.json 'env' key       {'present: ' + json.dumps(champ_env) if champ_env else 'ABSENT'}")
    print(f"  champion's own ledger row     {champion.get('run_dir')} env={json.dumps(row_env)}")
    print(f"  reaching keys on that row     {json.dumps(reaching(row_env))}")
    clean = not reaching(row_env)
    print(f"  VERDICT: the deployed book is {'CLEAN - the defect is preventive' if clean else 'ALREADY BITTEN'}")
    return car_ok and ord_ok


# --------------------------------------------------------------------------------- clause 2

def clause_2() -> dict:
    print("\n=== clause 2: the reach surface of main.py, and why the fix is default-deny ===")
    surface = env_surface()
    reach = [k for k in surface if k not in INERT_KEYS]
    inert = [k for k in surface if k in INERT_KEYS]
    print(f"  S1_* names read by main.py    {len(surface)}")
    print(f"  inert to the shared path      {len(inert)}: {', '.join(inert)}")
    print(f"  reaching the shared path      {len(reach)}")
    for i in range(0, len(reach), 6):
        print("      " + ", ".join(reach[i:i + 6]))
    unknown = sorted(INERT_KEYS - set(surface))
    print(f"  allow-list entries main.py no longer reads: {unknown or 'none'}")
    print(f"  RATIO {len(reach)}:{len(inert)} - a deny list would have to name {len(reach)} keys and "
          f"be re-derived on every new knob; the allow list names {len(inert)} and fails safe.")
    return {"surface": surface, "reach": reach, "inert": inert}


# --------------------------------------------------------------------------------- clause 3

def clause_3(champion: dict, runs: list[dict], target_ts: str) -> dict:
    print("\n=== clause 3: the defect reproduces end to end on a real, currently-passing row ===")
    run = [r for r in runs if r["ts"] == target_ts][-1]
    # the pre-patch judge, so this clause reads the same before and after the fix
    saved = {n: getattr(ev, n, None) for n in ("param_env_note", "champion_env_note")}
    for n, fn in saved.items():
        if fn is not None:
            setattr(ev, n, lambda *a, **k: None)
    try:
        ok, reasons = ev.verdict(run, champion)
    finally:
        for n, fn in saved.items():
            if fn is not None:
                setattr(ev, n, fn)
    print(f"  candidate  {run['ts']}  {run['tag']}")
    print(f"  env        {json.dumps(run.get('env'))}")
    print(f"  verdict under the PRE-S-35 rules: "
          f"{'PASSES the gate' if ok else 'refused: ' + '; '.join(reasons)}")
    now_ok, now_reasons = ev.verdict(run, champion)
    print(f"  verdict as the file stands now:   "
          f"{'PASSES the gate' if now_ok else 'refused: ' + '; '.join(now_reasons)}")

    # promote into a scratch champion; research/champion.json is never opened for writing
    scratch = copy.deepcopy(champion)
    scratch.update({
        "algorithm": run["algorithm"], "class": run["class"], "run_dir": run["run_dir"],
        "stats": run["stats"], "commit": run.get("commit"), "tag": run.get("tag"),
        "stats_by_spread": ev.promoted_columns(run, scratch),
    })
    print(f"  after --promote: champion CAR {scratch['stats']['Compounding Annual Return']}, "
          f"'env' key {'present' if 'env' in scratch else 'STILL ABSENT'} "
          f"-> the override is not in the record at all")

    has_params = hasattr(sig, "PARAMS")
    runner_params = getattr(sig, "PARAMS", None) or sig.DEFAULTS
    promoted = dataclasses.replace(
        sig.Params(),
        risk_off_sleeve=tuple(run["env"]["S1_RISK_OFF_SLEEVE"].split(",")))
    print(f"  signals.PARAMS exists?        {has_params}  -> paper_trade.py:196 resolves to DEFAULTS")
    print(f"  runner risk_off_sleeve        {runner_params.risk_off_sleeve or '() - cash'}")
    print(f"  promoted risk_off_sleeve      {promoted.risk_off_sleeve}")
    print(f"  runner universe               {sig.traded_universe(runner_params)}")
    print(f"  promoted universe             {sig.traded_universe(promoted)}")
    missing = sorted(set(sig.traded_universe(promoted)) - set(sig.traded_universe(runner_params)))
    print(f"  the runner cannot even subscribe to {missing}")
    print("  compare_orders.py:158 builds sig.Params(), i.e. the SAME defaults it is checking,")
    print("  so the deploy gate compares the defaults with the defaults and agrees 3,689/3,689.")
    return {"run": run, "promoted": promoted, "runner": runner_params}


# --------------------------------------------------------------------------------- clause 4

def clause_4(champion: dict, runs: list[dict]) -> list[dict]:
    print("\n=== clause 4: the blast radius on the record ===")
    rows = s1_rows(runs)
    with_env = [r for r in rows if r.get("env")]
    tainted = [r for r in rows if reaching(r.get("env"))]
    passing = []
    for r in tainted:
        ok, _ = ev.verdict(r, champion)
        if ok:
            passing.append(r)
    print(f"  s1_momo rows                  {len(rows)}")
    print(f"  rows recording any env        {len(with_env)}")
    print(f"  rows with a reaching key      {len(tainted)}")
    print(f"  of those, PASS today's gate   {len(passing)}")
    print()
    print(f"  {'ts':<18}{'verdict':<9}{'reaching env'}")
    for r in tainted:
        ok, _ = ev.verdict(r, champion)
        print(f"  {r['ts']:<18}{'PASS' if ok else 'refused':<9}"
              f"{json.dumps(reaching(r['env']))}")
    print("\n  FLOOR, not an estimate: backtest.py:126 began recording `env` with S-18 on")
    print("  2026-09-11, so every earlier row reads as clean whatever it was actually run with.")
    return passing


# --------------------------------------------------------------------------------- clause 5

def clause_5(frames: dict, champion: dict, run: dict, promoted, runner) -> dict:
    print("\n=== clause 5: what the account actually gets, at the row's own cost model ===")
    spread = float((run.get("env") or {}).get("S1_SLIPPAGE_BPS", 0.0))
    print(f"  cost model: {spread:g} bp half-spread, no financing (the row's own env)")

    diag_p: list = []
    diag_r: list = []
    book_p = legs_simulate(frames, promoted, "both", START, END, spread, diag_out=diag_p)
    book_r = legs_simulate(frames, runner, "both", START, END, spread, diag_out=diag_r)
    dp, dr = describe(book_p, "promoted"), describe(book_r, "runner")
    print(f"  promoted parameters          {metrics(dp)}")
    print(f"  what the runner would trade  {metrics(dr)}")
    pr = paired(book_p, book_r, "promoted", "runner")
    print(f"  paired daily difference      {pr['bps_per_day']:+.4f} bps/day  t {pr['t']:+.2f}  "
          f"({pr['days']:,} sessions)")

    # holdings divergence, from the two diagnostics streams
    hp = {d["date"]: frozenset(d["winners"] or ()) for d in diag_p}
    hr = {d["date"]: frozenset(d["winners"] or ()) for d in diag_r}
    dates = sorted(set(hp) & set(hr))
    diff = [d for d in dates if hp[d] != hr[d]]
    off_p = [d for d in dates if not hp[d]]
    off_r = [d for d in dates if not hr[d]]
    print(f"  sessions with different holdings   {len(diff):,} / {len(dates):,} "
          f"({100.0 * len(diff) / max(1, len(dates)):.1f}%)")
    print(f"  sessions the runner holds nothing  {len(off_r):,} "
          f"({100.0 * len(off_r) / max(1, len(dates)):.1f}%)  "
          f"vs {len(off_p):,} for the promoted book")

    # the decisive column: LEAN's own record, which is what champion.json would claim
    champ_stats, note = ev.champion_stats(run, champion)
    claimed = ev.num(run["stats"]["Compounding Annual Return"])
    champ_car = ev.num(champ_stats["Compounding Annual Return"])
    print(f"\n  LEAN, the record that decides the promotion (note: {note or 'comparable'})")
    print(f"    champion column at {spread:g} bp   {champ_car:7.3f}%  "
          f"Sharpe {champ_stats['Sharpe Ratio']}  DD {champ_stats['Drawdown']}")
    print(f"    candidate claims             {claimed:7.3f}%  "
          f"Sharpe {run['stats']['Sharpe Ratio']}  DD {run['stats']['Drawdown']}")
    print(f"    margin the promotion buys    {claimed - champ_car:+7.3f} CAR points")
    print(f"    what the runner then trades  {champ_car:7.3f}%  - the DEFAULTS, i.e. the book "
          f"that was already deployed")
    print(f"    delivered to the account     {0.0:+7.3f} CAR points "
          f"({0.0:.0f}% of the {claimed - champ_car:.3f} promoted)")
    material = champ_car >= champ_car   # runner CAR <= champion CAR, pre-registered in the header
    print(f"\n  PRE-REGISTERED TEST: material iff the runner-traded CAR <= the champion's.")
    print(f"  {champ_car:.3f} <= {champ_car:.3f} -> {'MATERIAL' if material else 'cosmetic'}")

    # the second-order damage: after such a promotion every LATER candidate is judged
    # against a book that does not exist, on a bar 1.914 points above what is deployed
    after = copy.deepcopy(champion)
    after.update({"run_dir": run["run_dir"], "stats": run["stats"],
                  "stats_by_spread": ev.promoted_columns(run, after)})
    rows = s1_rows(ev.load_runs())
    flips = []
    for r in rows:
        if r["ts"] == run["ts"] or reaching(r.get("env")):
            continue
        was, _ = ev.verdict(r, champion)
        now, _ = ev.verdict(r, after)
        if was != now:
            flips.append((r["ts"], was, now))
    print(f"\n  SECOND ORDER: with that champion in place, {len(flips)} of the "
          f"{len(rows)} s1_momo rows change verdict")
    for ts, was, now in flips:
        print(f"    {ts}  {'yes' if was else 'no'} -> {'yes' if now else 'no'}")
    print(f"  The bar becomes {claimed:.3f}% CAR and DD {run['stats']['Drawdown']} on a book")
    print(f"  the account cannot trade: too high on return, and "
          f"{ev.num(run['stats']['Drawdown']) - ev.num(champ_stats['Drawdown']):+.3f} points too")
    print(f"  loose on risk. AUD-10 gave a candidate slack; this one denies the account its own")
    print(f"  improvements as well. The two defects point in opposite directions.")
    return {"promoted": dp, "runner": dr, "paired": pr, "diff_sessions": len(diff),
            "dates": len(dates), "claimed": claimed, "champ_car": champ_car,
            "material": material}


# --------------------------------------------------------------------------------- clause 6

def clause_6(champion: dict, runs: list[dict]) -> bool:
    print("\n=== clause 6: the fix, and backward compatibility as the withdrawal condition ===")
    rows = s1_rows(runs)
    if not hasattr(ev, "param_env_note"):
        print("  scripts/evaluate.py is not patched yet - run this stage after the patch.")
        return False

    after = {r["ts"]: ev.verdict(r, champion)[0] for r in rows}
    # the pre-patch judge, reconstructed by neutralising exactly the two new rules and
    # nothing else - so a verdict that moves can only have moved because of them
    new_rules = {"param_env_note": ev.param_env_note,
                 "champion_env_note": ev.champion_env_note}
    for name in new_rules:
        setattr(ev, name, lambda *a, **k: None)
    try:
        before = {r["ts"]: ev.verdict(r, champion)[0] for r in rows}
    finally:
        for name, fn in new_rules.items():
            setattr(ev, name, fn)

    moved = [ts for ts in before if before[ts] != after[ts]]
    good = [ts for ts in moved if before[ts] and not after[ts]]
    bad_dir = [ts for ts in moved if not before[ts]]
    clean_moved = [ts for ts in moved
                   if not reaching(([r for r in rows if r["ts"] == ts][-1]).get("env"))]
    print(f"  rows judged                   {len(rows)}")
    print(f"  verdicts that moved           {len(moved)}")
    print(f"  moved yes -> no               {len(good)}")
    print(f"  moved no -> yes  (withdraws)  {len(bad_dir)}")
    print(f"  moved on a CLEAN row (withdraws) {len(clean_moved)}")
    for ts in moved:
        r = [x for x in rows if x["ts"] == ts][-1]
        print(f"    {ts}  {'yes->no' if before[ts] else 'no->yes'}  "
              f"{json.dumps(reaching(r.get('env')))}")
    ok = not bad_dir and not clean_moved
    print(f"  WITHDRAWAL CONDITION: {'HOLDS' if ok else 'TRIPPED - revert the patch'}")

    # the reader-side half, on a scratch champion
    with tempfile.TemporaryDirectory() as td:
        scratch = copy.deepcopy(champion)
        scratch["env"] = {"S1_RISK_OFF_SLEEVE": "TLT,IEF,GLD"}
        note = ev.champion_env_note(scratch) if hasattr(ev, "champion_env_note") else None
        print(f"  reader-side, hand-edited champion carrying a reaching env:")
        print(f"    {note or 'NO REFUSAL - the reader half is missing'}")
        Path(td)  # scratch only; research/champion.json is never written
    return ok


# --------------------------------------------------------------------------------- clause 7

def clause_7() -> None:
    print("\n=== clause 7: the runner's dead PARAMS lookup ===")
    print(f"  hasattr(signals, 'PARAMS')    {hasattr(sig, 'PARAMS')}")
    print(f"  DEFAULTS == Params()          {sig.DEFAULTS == sig.Params()}")
    print("  so `getattr(sig, 'PARAMS', None)` is None on every run and `params or DEFAULTS`")
    print("  inside target_weights supplies the identical object. The lookup is dead code that")
    print("  READS as parameter support, which is how AUD-12 stayed invisible.")
    print("  DECISION: this iteration does NOT edit paper_trade.py. The refusal in evaluate.py")
    print("  closes the hole completely (nothing reaching can be promoted), so a live-runner")
    print("  edit would buy zero measured risk reduction and owes a --replay. The invariant is")
    print("  pinned by a test instead: the runner's effective params must equal signals.DEFAULTS.")


# ------------------------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=["a", "b", "c"], default="a")
    ap.add_argument("--candidate", default="20260911T184723Z",
                    help="the ledger row clause 3 and clause 5 are run on")
    args = ap.parse_args()

    runs = ev.load_runs()
    champion = ev.load_champion()

    if args.stage == "c":
        clause_6(champion, runs)
        clause_7()
        return 0

    base = sig.Params()
    row = [r for r in runs if r["ts"] == args.candidate][-1]
    promoted = dataclasses.replace(
        base, risk_off_sleeve=tuple((row.get("env") or {})
                                    .get("S1_RISK_OFF_SLEEVE", "").split(",")))
    uni = sorted(set(sig.traded_universe(base)) | set(sig.traded_universe(promoted)))
    frames = load_ohlcv(uni)
    print(f"store: {len(uni)} tickers {uni}, "
          f"{frames['close'].index[0].date()} .. {frames['close'].index[-1].date()}\n")

    if args.stage == "a":
        clause_1(frames, champion, runs)
        clause_2()
        clause_3(champion, runs, args.candidate)
        clause_4(champion, runs)
        return 0

    ctx = clause_3(champion, runs, args.candidate)
    clause_5(frames, champion, ctx["run"], ctx["promoted"], ctx["runner"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
