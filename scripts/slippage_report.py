#!/usr/bin/env python
"""A-5: measure the intraday sleeve's realized execution cost from the live paper log.

`intraday_common.SLIPPAGE_BPS = 1.5` is the only number in the intraday harness that is a guess.
It is charged on ~49 trades/day - about $1,025/day of modelled cost against a $610/day modelled
edge - so the sleeve's sign is a property of this constant. This script replaces the guess with
a measurement, using the one thing a backtest cannot produce: real fills.

    python scripts/slippage_report.py                     # every live log on disk
    python scripts/slippage_report.py --date 2026-09-10    # one session
    python scripts/slippage_report.py --json out.json      # machine-readable, for the journal
    python scripts/slippage_report.py --self-test          # prove the estimator on synthetic fills

Method. The backtester fills an order decided on the close of bar t at the OPEN of bar t+1, with
no impact, and charges SLIPPAGE_BPS on the notional. So for every live order this compares the
realized `avg_price` against that same next-bar open, taken from the shared minute store
(`data/minute`, the bars the harness itself runs on), signed so that **positive = the live fill
cost more than the backtest assumed**. That difference *is* the slippage the constant is trying
to model; nothing else needs estimating.

Reported per session and pooled: notional-weighted mean, unweighted mean, standard error,
per-symbol and per-side breakdown, fill rate, and fill latency. Two sessions is not a
sample - the pooled mean and its standard error are the output, and the constant should only move
when the standard error is small against the gap between measurement and 1.5 bps.

Two references, kept apart (A-5 part 2, 2026-09-10). When the store has no bar for the fill's
minute the script falls back to the price the strategy saw, the *close* of the decision bar. The
two are never pooled into one headline, and where both exist every fill is priced under both so
the choice is measured rather than assumed. On the first live session that measurement said the
choice barely matters: the same 17 fills scored +1.10 bps / sd 7.55 against the store and
+1.55 / sd 7.13 against the decision close. `--refresh` still pulls closed sessions into the
store, because the backtester fills at the next bar's open and that is the number to report.

This script never writes `SLIPPAGE_BPS`. Changing it means editing scripts/intraday_common.py,
which the live trader imports, and replaying a session first (AGENTS.md rule a).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from intraday_common import ET, LIVE, REPO, SLIPPAGE_BPS, load_bars  # noqa: E402

LOG_DIR = LIVE / "log"

#: The slippage at which the deployed mix earns nothing on the 260-session IBKR store. That, not
#: the shipped 1.5, is the number this measurement has to resolve before it can say anything about
#: the sleeve's sign, so the power calculation is quoted against it. A-5 part 1 put it at
#: 2.62-2.64 bps; A-5 part 2 charged the sell-side regulatory fees IBKR's commissionReport proves
#: are real, which costs $53/day on $5.46M/day of turnover, so at $546/day per bp (A-5 part 1) the
#: control's $557/day now runs out 1.02 bps above the shipped constant.
BREAKEVEN_BPS = 2.52


# --------------------------------------------------------------------------- parsing
def read_log(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def orders_and_fills(rows: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`order` and `fill` events, joined later on the IB order id.

    `decision` events carry the price the strategy saw (`ref`), which is the fallback reference
    when the minute store has no bar for the fill minute yet.
    """
    ref_at: dict[tuple[str, str], float] = {}
    for r in rows:
        if r.get("event") == "decision":
            for s, px in (r.get("ref") or {}).items():
                ref_at[(str(r.get("t")), s)] = float(px)
    orders, fills = [], []
    for r in rows:
        e = r.get("event")
        if e == "order":
            t = str(r.get("t")) if r.get("t") else None
            orders.append({"id": r.get("id"), "sym": r.get("symbol"), "qty": r.get("qty"),
                           "sent_ts": r.get("ts"), "decision_t": t,
                           "decision_px": ref_at.get((t, r.get("symbol")))})
        elif e == "fill":
            fills.append({"id": r.get("id"), "sym": r.get("symbol"), "filled_qty": r.get("qty"),
                          "avg_price": r.get("avg_price"), "commission": r.get("commission"),
                          "seen_ts": r.get("ts"), "filled_at": r.get("filled_at")})
    return pd.DataFrame(orders), pd.DataFrame(fills)


def next_bar_open(sym: str, decision_t: str, cache: dict) -> float | None:
    """The price the backtester would have filled at: the open of the bar after the decision bar."""
    try:
        t = pd.Timestamp(decision_t)
    except (ValueError, TypeError):
        return None
    if t.tzinfo is None:
        t = t.tz_localize(ET)
    day = t.date()
    key = (sym, day)
    if key not in cache:
        cache[key] = load_bars(sym, day, day)
    df = cache[key]
    if df is None or df.empty:
        return None
    later = df.index[df.index > t]
    return float(df.loc[later[0], "o"]) if len(later) else None


# --------------------------------------------------------------------------- one session
def measure(path: Path, cache: dict) -> dict:
    rows = read_log(path)
    o, f = orders_and_fills(rows)
    date = path.stem.split("-", 1)[1] if "-" in path.stem else path.stem
    res = {"date": date, "log": path.name, "orders": len(o), "fills": len(f)}
    if o.empty:
        res["note"] = "no orders in this log (dry run, replay-only or a session that never traded)"
        return res
    if f.empty:
        res["note"] = f"{len(o)} orders submitted but no fill events - nothing to measure"
        return res

    # ids are unique per session; match on them, and fall back to symbol order if a log predates
    # the id being written on the fill line
    if f["id"].isna().all():
        f = f.assign(id=[None] * len(f))
        d = o.merge(f.drop(columns=["id"]), on="sym", how="inner", suffixes=("", "_f"))
        res["match"] = "by symbol (log has no fill ids)"
    else:
        d = o.merge(f, on=["id", "sym"], how="inner")
        res["match"] = "by order id"

    d["ref_next_open"] = [next_bar_open(s, t, cache) for s, t in zip(d["sym"], d["decision_t"])]
    d["ref_source"] = np.where(d["ref_next_open"].notna(), "next bar open", "decision close")
    d["ref"] = d["ref_next_open"].fillna(d["decision_px"])
    d = d.dropna(subset=["ref", "avg_price"])
    if d.empty:
        res["note"] = "fills matched but no reference price available (store not updated for this date?)"
        return res
    d["side"] = np.where(d["filled_qty"].astype(float) > 0, "buy", "sell")
    sign = np.sign(d["filled_qty"].astype(float))
    d["slip_bps"] = (d["avg_price"].astype(float) - d["ref"].astype(float)) / d["ref"].astype(float) * 1e4 * sign
    d["notional"] = d["filled_qty"].abs().astype(float) * d["avg_price"].astype(float)
    d["comm_bps"] = d["commission"].astype(float) / d["notional"] * 1e4
    d["latency_s"] = fill_latency(d)
    # both references, wherever both exist, so the choice between them is measured and not modelled
    both = d["ref_next_open"].notna() & d["decision_px"].notna()
    d["slip_alt_bps"] = np.where(
        both,
        (d["avg_price"].astype(float) - d["decision_px"].astype(float))
        / d["decision_px"].astype(float) * 1e4 * sign,
        np.nan)
    d["gap_bps"] = np.where(
        both,
        (d["ref_next_open"].astype(float) - d["decision_px"].astype(float))
        / d["decision_px"].astype(float) * 1e4,
        np.nan)

    n = len(d)
    w = d["notional"]
    res.update({
        "matched": n,
        "fill_rate": round(len(f) / len(o), 4),
        "notional": float(w.sum()),
        "slip_bps_wmean": float((d["slip_bps"] * w).sum() / w.sum()),
        "slip_bps_mean": float(d["slip_bps"].mean()),
        "slip_bps_median": float(d["slip_bps"].median()),
        "slip_bps_se": float(d["slip_bps"].std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan"),
        "comm_bps_wmean": float((d["comm_bps"] * w).sum() / w.sum()),
        "ref_from_store_pct": float((d["ref_source"] == "next bar open").mean() * 100),
        "latency_s_median": float(d["latency_s"].median()) if d["latency_s"].notna().any() else float("nan"),
        "latency_s_max": float(d["latency_s"].max()) if d["latency_s"].notna().any() else float("nan"),
        "modelled_cost": float(w.sum() * SLIPPAGE_BPS / 1e4),
        "measured_cost": float((d["slip_bps"] * w / 1e4).sum()),
        "_rows": d,
    })
    return res


def fill_latency(d: pd.DataFrame) -> pd.Series:
    """Seconds between the moment the backtester fills and the moment the live order filled.

    Store bars are stamped by bar START, so a decision on bar `t` is filled by the backtester at
    the open of `t+1`, i.e. at `t + 60s`. Anything after that is drift the backtest never pays -
    it is mean-zero, not a cost, but it is the variance that makes this measurement expensive."""
    out = []
    for t, filled in zip(d["decision_t"], d["filled_at"]):
        try:
            a = pd.Timestamp(t)
            b = pd.Timestamp(filled)
            if a.tzinfo is None:
                a = a.tz_localize(ET)
            if b.tzinfo is None:
                b = b.tz_localize(dt.timezone.utc)
            out.append((b - a).total_seconds() - 60.0)
        except (ValueError, TypeError):
            out.append(float("nan"))
    return pd.Series(out, index=d.index, dtype=float)


def by_reference(d: pd.DataFrame) -> pd.DataFrame:
    """The headline, split by which reference priced the fill. Never pooled across the two."""
    rows = []
    for src, g in d.groupby("ref_source"):
        w = g["notional"] / g["notional"].sum()
        var = g["slip_bps"].var(ddof=1) if len(g) > 1 else float("nan")
        rows.append({"reference": src, "fills": len(g), "notional": g["notional"].sum(),
                     "wmean bps": float((g["slip_bps"] * w).sum()),
                     "median bps": float(g["slip_bps"].median()),
                     "sd bps": float(np.sqrt(var)) if len(g) > 1 else float("nan"),
                     "wse bps": float(np.sqrt((w ** 2 * var).sum())) if len(g) > 1 else float("nan")})
    return pd.DataFrame(rows)


def print_session(res: dict) -> None:
    print(f"\n=== {res['date']}  ({res['log']}) ===")
    if "matched" not in res:
        print(f"  {res.get('note', 'nothing to measure')}   orders={res['orders']} fills={res['fills']}")
        return
    print(f"  matched {res['matched']} of {res['orders']} orders {res['match']}, fill rate {res['fill_rate']:.0%}, "
          f"reference from the store on {res['ref_from_store_pct']:.0f}% of them")
    print(f"  traded notional               ${res['notional']:,.0f}")
    ref_label = ("next-bar open" if res["ref_from_store_pct"] == 100 else
                 "decision close" if res["ref_from_store_pct"] == 0 else "mixed reference")
    print(f"  slippage vs {ref_label:<17s} {res['slip_bps_wmean']:+.2f} bps notional-weighted"
          f"   {res['slip_bps_mean']:+.2f} unweighted   median {res['slip_bps_median']:+.2f}"
          f"   se {res['slip_bps_se']:.2f}")
    print(f"  shipped SLIPPAGE_BPS          {SLIPPAGE_BPS:+.2f} bps"
          f"   -> modelled ${res['modelled_cost']:,.0f} vs measured ${res['measured_cost']:,.0f}")
    print(f"  IBKR commission               {res['comm_bps_wmean']:.2f} bps of notional")
    print(f"  fill latency past the model   median {res['latency_s_median']:.0f}s   worst {res['latency_s_max']:.0f}s")
    d = res["_rows"]
    if d["ref_source"].nunique() > 1 or res["ref_from_store_pct"] < 100:
        print("\n  by reference (never pooled - the two price different things):")
        print(by_reference(d).round(2).to_string(index=False))
    by_side = d.groupby("side").apply(
        lambda g: pd.Series({"orders": len(g), "wmean bps": (g["slip_bps"] * g["notional"]).sum() / g["notional"].sum()}),
        include_groups=False)
    print("\n  by side:")
    print(by_side.round(2).to_string())
    by_sym = d.groupby("sym").apply(
        lambda g: pd.Series({"orders": len(g), "notional": g["notional"].sum(),
                             "wmean bps": (g["slip_bps"] * g["notional"]).sum() / g["notional"].sum(),
                             "worst bps": g["slip_bps"].max()}), include_groups=False)
    print("\n  by symbol:")
    print(by_sym.sort_values("notional", ascending=False).round(2).to_string())


def print_pooled(sessions: list[dict]) -> dict:
    good = [s for s in sessions if "matched" in s]
    if not good:
        print("\nNo session on disk has live fills yet - nothing to pool. The trader must run "
              "without --dry-run for A-5 to have any input.")
        return {}
    d = pd.concat([s["_rows"] for s in good], ignore_index=True)
    w = d["notional"]
    n = len(d)
    wmean = float((d["slip_bps"] * w).sum() / w.sum())
    mean = float(d["slip_bps"].mean())
    se = float(d["slip_bps"].std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
    # the standard error that matters is on the notional-weighted mean, i.e. per dollar traded
    wse = float(np.sqrt(((w / w.sum()) ** 2 * d["slip_bps"].var(ddof=1)).sum())) if n > 1 else float("nan")
    print(f"\n=== POOLED over {len(good)} session(s), {n} fills, ${w.sum():,.0f} traded ===")
    print(f"  realized slippage   {wmean:+.2f} bps notional-weighted (se {wse:.2f})"
          f"   {mean:+.2f} unweighted (se {se:.2f})")
    print(f"  shipped constant    {SLIPPAGE_BPS:+.2f} bps"
          f"   -> the harness is {'CONSERVATIVE' if wmean < SLIPPAGE_BPS else 'OPTIMISTIC'} by "
          f"{abs(wmean - SLIPPAGE_BPS):.2f} bps")
    if np.isfinite(wse) and wse > 0:
        z = abs(wmean - SLIPPAGE_BPS) / wse
        print(f"  |measured - shipped| / se = {z:.2f}"
              f"   ({'not yet distinguishable' if z < 2 else 'distinguishable'} at 2 se)")
    per_day = d.groupby(d["date"] if "date" in d else 0)
    print("\n  per session:")
    rows = [{"date": s["date"], "fills": s["matched"], "notional": round(s["notional"]),
             "wmean bps": round(s["slip_bps_wmean"], 2), "se": round(s["slip_bps_se"], 2)} for s in good]
    print(pd.DataFrame(rows).to_string(index=False))
    power = print_power(d, len(good))
    print(f"\n  Decision: move intraday_common.SLIPPAGE_BPS only when |measured - shipped| exceeds "
          f"2 standard errors\n  and the change is recorded in research/journal.md with a replay "
          f"(AGENTS.md rule a). Currently{'' if np.isfinite(wse) and abs(wmean - SLIPPAGE_BPS) > 2 * wse else ' NOT'} met.")
    out = {"sessions": len(good), "fills": n, "notional": float(w.sum()), "slip_bps_wmean": wmean,
           "slip_bps_wse": wse, "slip_bps_mean": mean, "slip_bps_se": se, "shipped_bps": SLIPPAGE_BPS,
           "ref_from_store_pct": float((d["ref_source"] == "next bar open").mean() * 100),
           "by_reference": by_reference(d).to_dict("records")}
    out.update(power)
    return out


def print_power(d: pd.DataFrame, n_sessions: int) -> dict:
    """How many more fills this measurement needs.

    The question A-5 exists to answer is not "what is the slippage" but "is the sleeve's shipped
    1.5 bps on the right side of its 2.62 bps breakeven". At 2 standard errors that needs
    `(2 * sd / (2.62 - 1.5))**2` fills, so the per-fill standard deviation is the whole cost of
    the study.

    That standard deviation is NOT the reference's fault, which is worth stating because the
    obvious model says it should be. Priced against the store, the same 17 fills of 2026-09-10
    scored sd 7.55 bps; priced against the decision close, 7.13 - the fallback is very slightly
    *quieter*, not noisier. The whole-store close-to-next-open gap has sd 6.20 bps on this
    symbol mix, which predicted a large penalty, but on the minutes the sleeve actually trades
    the realized gap had sd 2.16 and correlated -0.33 with the fill error. A population noise
    estimate does not transfer to the minutes a strategy selects. What is left is the ~10 seconds
    of detection latency, and that drift is mean-zero, so only fills buy precision."""
    n = len(d)
    sd_obs = float(d["slip_bps"].std(ddof=1)) if n > 1 else float("nan")
    per_session = n / max(n_sessions, 1)
    print("\n  Dispersion (what the precision costs):")
    print(f"    observed per-fill sd            {sd_obs:.2f} bps")
    both = d["slip_alt_bps"].notna()
    alt = {}
    if both.sum() > 1:
        g = d.loc[both]
        alt = {"n": int(both.sum()),
               "sd_this_ref": float(g["slip_bps"].std(ddof=1)),
               "sd_other_ref": float(g["slip_alt_bps"].std(ddof=1)),
               "mean_this_ref": float(g["slip_bps"].mean()),
               "mean_other_ref": float(g["slip_alt_bps"].mean()),
               "gap_sd": float(g["gap_bps"].std(ddof=1)),
               "gap_mean": float(g["gap_bps"].mean())}
        print(f"    the same {alt['n']} fills, other reference   mean {alt['mean_other_ref']:+.2f} bps, "
              f"sd {alt['sd_other_ref']:.2f}   (this reference {alt['mean_this_ref']:+.2f}, "
              f"sd {alt['sd_this_ref']:.2f})")
        print(f"    realized close->open gap        mean {alt['gap_mean']:+.2f} bps, sd {alt['gap_sd']:.2f}"
              f"  - the reference is not what makes this expensive")
    need = None
    if np.isfinite(sd_obs) and sd_obs > 0:
        need = (2 * sd_obs / (BREAKEVEN_BPS - SLIPPAGE_BPS)) ** 2
        print(f"\n  Power against the {BREAKEVEN_BPS:.2f} bps breakeven (A-5 part 1), at 2 se:")
        print(f"    {need:6.0f} fills  ~{need / max(per_session, 1e-9):5.1f} sessions at the "
              f"{per_session:.0f} fills/session seen so far")
    return {"sd_per_fill": sd_obs, "fills_per_session": per_session,
            "fills_needed": need, "breakeven_bps": BREAKEVEN_BPS, "both_references": alt}


# --------------------------------------------------------------------------- self-test
def self_test() -> int:
    """Synthesize a log whose fills sit a known number of bps past the next bar's open, then
    check the estimator recovers it. Without this the script's first real output would be
    unfalsifiable."""
    import tempfile
    sym = "AAPL"
    df = load_bars(sym)
    if df.empty:
        print("self-test needs data/minute; run scripts/intraday_data.py first")
        return 2
    day = df.index[-1].date()
    bars = load_bars(sym, day, day)
    if len(bars) < 20:
        print(f"self-test needs a full session; {day} has {len(bars)} bars")
        return 2
    truth_bps = 2.75
    rows = []
    for i in range(0, 10):
        t = bars.index[i]
        nxt = bars.index[i + 1]
        ref = float(bars.loc[nxt, "o"])
        qty = 100 if i % 2 == 0 else -100
        px = ref * (1 + np.sign(qty) * truth_bps / 1e4)
        rows.append({"ts": str(t), "event": "decision", "t": str(t), "minute": i, "targets": {},
                     "orders": {sym: qty}, "ref": {sym: float(bars.loc[t, "c"])}, "mode": "live"})
        rows.append({"ts": str(t), "event": "order", "symbol": sym, "qty": qty, "id": 1000 + i, "t": str(t)})
        rows.append({"ts": str(nxt), "event": "fill", "symbol": sym, "qty": qty, "avg_price": px,
                     "commission": abs(qty) * 0.005, "status": "Filled", "id": 1000 + i,
                     "filled_at": str(nxt)})
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / f"intraday-{day}.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        res = measure(p, {})
    got = res.get("slip_bps_wmean", float("nan"))
    ok = abs(got - truth_bps) < 0.01
    print(f"self-test: injected {truth_bps:+.2f} bps on {res.get('matched')} fills "
          f"(both sides), recovered {got:+.2f} bps -> {'PASS' if ok else 'FAIL'}")
    if ok:
        # and the sign convention: a buy filled BELOW the reference must read negative
        rows2 = [r for r in rows if not (r["event"] == "fill" and r["qty"] < 0)]
        for r in rows2:
            if r["event"] == "fill":
                r["avg_price"] = r["avg_price"] / (1 + 2 * truth_bps / 1e4)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / f"intraday-{day}.jsonl"
            p.write_text("\n".join(json.dumps(r) for r in rows2) + "\n", encoding="utf-8")
            res2 = measure(p, {})
        neg = res2.get("slip_bps_wmean", float("nan"))
        ok = neg < 0
        print(f"self-test: buys filled below the reference read {neg:+.2f} bps -> "
              f"{'PASS' if ok else 'FAIL'} (negative means better than the backtest assumed)")
    return 0 if ok else 1


# --------------------------------------------------------------------------- driver
#: The store must not be asked for a session that is still trading: IBKR truncates the session an
#: `endDateTime` lands in, which is the bug A-4 found and `snap_after_close` fixes. 16:05 ET is the
#: close plus a five-minute margin for the consolidated tape to settle.
REFRESH_AFTER = dt.time(16, 5)


def refresh_store(dates: list[str], symbols: list[str]) -> int:
    """Pull the traded sessions' minute bars into data/minute so the reference is the next bar's
    open rather than the decision close. Refuses any date whose session has not closed."""
    import subprocess

    now = dt.datetime.now(ET)
    todo = []
    for ds in dates:
        try:
            day = dt.date.fromisoformat(ds)
        except ValueError:
            continue
        if day > now.date() or (day == now.date() and now.time() < REFRESH_AFTER):
            print(f"  refusing to refresh {ds}: session has not closed "
                  f"(now {now:%H:%M} ET, need {REFRESH_AFTER:%H:%M})")
            continue
        todo.append(day)
    if not todo:
        print("  nothing to refresh")
        return 0
    months = max(1, (now.date() - min(todo)).days // 25 + 1)
    cmd = [sys.executable, str(HERE / "intraday_data.py"), "--symbols", *sorted(set(symbols)),
           "--months", str(months), "--force"]
    print(f"  refreshing store for {len(todo)} session(s): {' '.join(cmd[1:])}")
    return subprocess.call(cmd)


def traded_symbols_and_dates(paths: list[Path]) -> tuple[list[str], list[str]]:
    syms, dates = set(), []
    for p in paths:
        rows = read_log(p)
        s = {r.get("symbol") for r in rows if r.get("event") == "order" and r.get("symbol")}
        if s:
            syms |= s
            dates.append(p.stem.split("-", 1)[1])
    return sorted(syms), dates


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", action="append", help="YYYY-MM-DD; repeatable. Default: every live log on disk")
    ap.add_argument("--json", help="write the pooled result to this path")
    ap.add_argument("--refresh", action="store_true",
                    help="fetch the traded sessions into data/minute first, so the reference is "
                         "the next bar's open (refuses a session that has not closed)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    if args.date:
        paths = [LOG_DIR / f"intraday-{d}.jsonl" for d in args.date]
        missing = [p for p in paths if not p.exists()]
        if missing:
            print("no such log: " + ", ".join(str(p) for p in missing))
            return 2
    else:
        # live logs only; replays go to intraday-replay-<date>.jsonl by design
        paths = sorted(p for p in LOG_DIR.glob("intraday-*.jsonl") if "replay" not in p.name)
    if not paths:
        print(f"no live intraday logs in {LOG_DIR}")
        return 2

    if args.refresh:
        syms, dates = traded_symbols_and_dates(paths)
        if syms:
            refresh_store(dates, syms)
        else:
            print("  no traded symbols in these logs; nothing to refresh")

    cache: dict = {}
    sessions = []
    for p in paths:
        res = measure(p, cache)
        if "matched" in res:
            res["_rows"]["date"] = res["date"]
        print_session(res)
        sessions.append(res)
    pooled = print_pooled(sessions)
    if args.json and pooled:
        Path(args.json).write_text(json.dumps(pooled, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0 if pooled else 1


if __name__ == "__main__":
    sys.exit(main())
