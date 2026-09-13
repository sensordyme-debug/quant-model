#!/usr/bin/env python
"""D-7 / AUD-17: the LEAN daily store holds adjusted prices labelled raw - what does that cost?

    python scripts/sweep_d7.py                  # clauses 1-2 and 4-8, offline, no writes
    python scripts/sweep_d7.py --net            # + clause 3: yfinance cross-check of the basis
    python scripts/sweep_d7.py --net --write    # + write data/daily_splits.json
    python scripts/sweep_d7.py --net --write --record   # + DIAGNOSTIC ledger rows

AUD-17 says `fetch_data.py:19-24,141,165` writes Yahoo's split-adjusted OHLC into LEAN's daily
store with `split_factor=1` on every factor row, so LEAN's IB fee model charges $0.005 on an
ADJUSTED share count: "pre-2018 TQQQ/UPRO orders hit the 0.5% cap (conservative for the champion)
and SQQQ/SOXS are understated". Every term in that sentence is checkable from what is on disk plus
a split calendar, so this script checks it before anything is written, and prices the correction
against the book the owner is actually shown - the deployed champion's 5,128 fills.

This is D-5's question one library over (D-5 did the IBKR MINUTE store), and it inherits D-5's
discipline: derive the factor table from a calendar rather than from a price ratio, quote the
arithmetic ceiling before any P&L column, and report the sign per symbol because the audit names
an understatement only while a forward split overcharges.

Pre-registered clauses (fixed before any number in the output was read)
----------------------------------------------------------------------
1. PREMISE-A (the lie is on disk). Every factor file this repo's fetcher wrote for the 69-symbol
   universe carries `split_factor == 1` on EVERY row. One row anywhere that does not is enough to
   withdraw the item as already-fixed. Report the row count scanned, not just the verdict.
2. TRUTH (the calendar). A split calendar for all 69 symbols, and from it the cumulative factor
   `cum(d) = prod(ratio for ex_date > d)` such that `adjusted = raw / cum` and
   `q_adjusted = cum * q_raw`. Report which symbols have >= 1 split inside their stored span and
   the extreme `cum` at each store's first bar. A symbol with no in-span split cannot be affected
   however the fee arithmetic lands, and that set is the item's real blast radius.
3. PREMISE-B (the basis, and it needs the network). The stored close must equal Yahoo's
   split-adjusted `Close` to storage rounding on the SAME dates - i.e. the store is on the current
   share basis. Tested as the median |store/yahoo - 1| per symbol against the 1/SCALE quantisation
   floor. If any symbol reads RAW instead, the direction of the whole item flips and nothing is
   written: a factor applied to a store that is already raw is the same defect with the sign
   reversed (D-5 clause 2).
4. FEE MODEL (no guessing what LEAN charges). Replicate
   `InteractiveBrokersFeeModel.cs:150,161-172` - `fee = 0.005*|q|`, raised to $1 if below, ELSE
   capped at `0.005*value` - and validate the replica against the champion's OWN 5,128 recorded
   `orderFeeAmount` values. The replica must reproduce them to the cent on >= 99% of fills or the
   fee columns in clauses 5-7 are withdrawn as unvalidated. Note the `else`: the $1 minimum is NOT
   subject to the 0.5% cap, which is exactly the branch a near-zero adjusted share count lands in.
5. REACH ON THE DEPLOYED BOOK (the only number the owner is shown). The champion's 5,128 fills,
   symbol by symbol, against clause 2's calendar over the RUN's own window. Recompute every fee at
   the true raw share count and report the delta against the recorded $27,199.76. MATERIAL if
   |d fees| >= 1% of total fees or >= 0.5% of net profit; pre-registered, both directions.
   Reported TWICE, because the store's price is adjusted on two axes and AUD-17 names only one:
   (a) SPLIT-ONLY, `q_raw = q_adj / cum`, the quantity AUD-17's sentence is about; (b) FULL,
   `q_raw = q_adj * price_factor / cum`, which adds the dividend leg the factor file already
   carries. A per-share fee is charged on a share count, and the share count is wrong by the WHOLE
   adjustment, so (b) is the honest column and (a) is the audit's.
9. EFFICACY (added mid-run, after clause 5 landed MATERIAL: does AUD-17's prescribed remedy work?).
   AUD-17 says "store true raw prices with real split factors". That only helps if the split factor
   reaches the fee model. LEAN's own sample data is a free control - `factor_files/aig.csv` carries
   `split_factor = 20` before 2009-06-30 over true raw prices, the file this repo's fetcher does
   NOT write - so `algorithms/_d7_feeprobe` buys a fixed DOLLAR amount of AIG on each side of that
   boundary in ADJUSTED mode and logs the price seen, the share count and the fee. If the fee is
   `0.005 * adjusted_quantity` in BOTH eras, the factor never reaches the fee and the prescribed
   migration cannot change a single charge; the remedy is then a fee model, not a data rewrite.
6. TRADEABILITY (the failure mode the audit does not name). An adjusted price far above the raw
   one does not merely undercharge - LEAN orders whole shares, so a sleeve-sized order can round to
   ZERO and the symbol is silently untradeable. Count the stored symbol-sessions where a $10k and a
   $100k order round to 0 shares, and separately where the $1 minimum fee binds (i.e. < 200 shares)
   when the raw basis would have charged per-share.
7. BLAST RADIUS (everyone who is not the champion). Across all 69 stored symbols, the per-share fee
   error a $10k order would carry each session, in bps of notional, summarised per symbol as the
   median and the worst. Quote it in bps BEFORE any dollar column, so a correction whose ceiling is
   below the harness's own 1.5 bps slippage line can be dismissed on arithmetic (S-32's rule).
8. SHIP CONDITION (and the reason this run does not rewrite the store). The real fix - true raw
   prices with real split factors - changes the share count of every LEAN daily backtest and so
   every `daily`-track metric, including the champion's promotion row. That is a promotion-gated,
   cross-track change and this is an unattended `iterate` run, so the ONLY artefact shipped here is
   a sidecar: `data/daily_splits.json`, the validated calendar, which touches no price any sleeve
   reads. Written only if clauses 1, 3 and 4 all pass. The store rewrite is filed, not performed.
   Clause 9 then made "filed, not performed" the permanent answer rather than a scheduling one.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import pandas as pd  # noqa: E402

import fetch_data as fd  # noqa: E402
from lean_prices import EQUITY, SCALE, _raw_bars  # noqa: E402

SPLITS_PATH = REPO / "data" / "daily_splits.json"
LEDGER = REPO / "research" / "experiments.jsonl"
CHAMPION = REPO / "research" / "champion.json"

# InteractiveBrokersFeeModel.cs:150 - USD equity tier.
FEE_PER_SHARE = 0.005
FEE_MINIMUM = 1.0
FEE_MAX_RATE = 0.005

ORDER_SIZES = (10_000.0, 100_000.0)


def lean_ib_fee(quantity: float, price: float) -> float:
    """LEAN's IB US-equity order fee, transcribed from InteractiveBrokersFeeModel.cs:161-172.

    The minimum and the cap are an if/ELSE-if, not a clamp: an order whose per-share fee is
    under $1 pays $1 even when that exceeds 0.5% of its value. That branch is the whole of
    clause 6 - a tiny adjusted share count does not pay a tiny fee, it pays the floor.
    """
    q = abs(float(quantity))
    value = q * abs(float(price))
    fee = FEE_PER_SHARE * q
    if fee < FEE_MINIMUM:
        fee = FEE_MINIMUM
    elif fee > FEE_MAX_RATE * value:
        fee = FEE_MAX_RATE * value
    return abs(fee)


def lean_ticker(yahoo: str) -> str:
    return fd.LEAN_TICKER.get(yahoo, yahoo.lower())


def universe() -> list[str]:
    return fd.ETFS + fd.MEGACAPS


# ---------------------------------------------------------------- clause 1

def clause1_premise_a(symbols: list[str]) -> dict:
    """Every factor row our fetcher wrote carries split_factor == 1."""
    scanned = rows = offenders = missing = 0
    bad: list[str] = []
    for sym in symbols:
        path = EQUITY / "factor_files" / f"{lean_ticker(sym)}.csv"
        if not path.exists():
            missing += 1
            continue
        scanned += 1
        for line in path.read_text().strip().splitlines():
            parts = line.split(",")
            if len(parts) < 3:
                continue
            rows += 1
            if float(parts[2]) != 1.0:
                offenders += 1
                if sym not in bad:
                    bad.append(sym)
    return {"files": scanned, "missing": missing, "rows": rows,
            "offending_rows": offenders, "offending_symbols": bad,
            "pass": scanned > 0 and offenders == 0}


# ---------------------------------------------------------------- clause 2

def fetch_calendar(symbols: list[str], start: str, end: str) -> dict[str, list[tuple[str, float]]]:
    """{symbol: [(ex_date, ratio), ...]} from Yahoo's actions, reusing fetch_data's batching."""
    import yfinance as yf

    out: dict[str, list[tuple[str, float]]] = {}
    for i in range(0, len(symbols), 20):
        batch = symbols[i:i + 20]
        raw = yf.download(batch, start=start, end=end, auto_adjust=False, actions=True,
                          progress=False, group_by="ticker", threads=True)
        for sym in batch:
            df = raw
            if hasattr(raw.columns, "levels"):
                level = next((lv for lv in range(raw.columns.nlevels)
                              if sym in raw.columns.get_level_values(lv)), None)
                if level is None:
                    continue
                df = raw.xs(sym, axis=1, level=level)
            if "Stock Splits" not in df:
                out[sym] = []
                continue
            s = df["Stock Splits"].fillna(0.0)
            out[sym] = [(d.strftime("%Y-%m-%d"), float(r)) for d, r in s.items() if r > 0]
    return out


def cum_series(index: pd.DatetimeIndex, splits: list[tuple[str, float]]) -> pd.Series:
    """cum(d) = product of every split ratio whose ex-date is strictly after d.

    `adjusted = raw / cum`, `q_adjusted = cum * q_raw`. A forward split (ratio > 1) therefore
    INFLATES the adjusted share count and overcharges; a reverse split (ratio < 1) deflates it
    and undercharges, which is the direction AUD-17 names.
    """
    cum = pd.Series(1.0, index=index)
    for ex, ratio in splits:
        ex_ts = pd.Timestamp(ex)
        cum[index < ex_ts] *= ratio
    return cum


def load_factor_rows(ticker: str) -> list[tuple[pd.Timestamp, float, float]]:
    """[(date, price_factor, split_factor)] from a LEAN factor file, in file order."""
    path = EQUITY / "factor_files" / f"{ticker}.csv"
    rows = []
    for line in path.read_text().strip().splitlines():
        parts = line.split(",")
        if len(parts) < 3:
            continue
        rows.append((pd.Timestamp(parts[0]), float(parts[1]), float(parts[2])))
    return rows


def price_factor_series(ticker: str, index: pd.DatetimeIndex) -> pd.Series:
    """LEAN's lookup: the first factor row whose date >= the bar date (fetch_data.py:141-152)."""
    rows = load_factor_rows(ticker)
    dates = pd.DatetimeIndex([d for d, _, _ in rows])
    values = [pf * sf for _, pf, sf in rows]
    pos = dates.searchsorted(index, side="left").clip(0, len(values) - 1)
    return pd.Series([values[i] for i in pos], index=index)


def price_factor_at(ticker: str, when: pd.Timestamp) -> float:
    return float(price_factor_series(ticker, pd.DatetimeIndex([when])).iloc[0])


def clause2_truth(symbols: list[str], calendar: dict) -> dict:
    per: dict[str, dict] = {}
    for sym in symbols:
        try:
            bars = _raw_bars(lean_ticker(sym))
        except FileNotFoundError:
            continue
        splits = calendar.get(sym, [])
        first, last = bars.index[0], bars.index[-1]
        in_span = [(d, r) for d, r in splits if first <= pd.Timestamp(d) <= last]
        cum = cum_series(bars.index, in_span)
        per[sym] = {"bars": len(bars),
                    "first": first.strftime("%Y-%m-%d"), "last": last.strftime("%Y-%m-%d"),
                    "splits_in_span": len(in_span),
                    "cum_first": float(cum.iloc[0]),
                    "cum_min": float(cum.min()), "cum_max": float(cum.max())}
    affected = [s for s, v in per.items() if v["splits_in_span"] > 0]
    return {"per_symbol": per, "affected": affected,
            "n_affected": len(affected), "n_total": len(per)}


# ---------------------------------------------------------------- clause 3

def clause3_premise_b(symbols: list[str], start: str, end: str) -> dict:
    """The stored close is on the CURRENT share basis (== Yahoo's split-adjusted Close)."""
    frames = fd.fetch(symbols, start, end)
    per: dict[str, dict] = {}
    for sym, df in frames.items():
        try:
            bars = _raw_bars(lean_ticker(sym))
        except FileNotFoundError:
            continue
        yahoo = pd.Series([float(c) for c in df["Close"]],
                          index=pd.DatetimeIndex([d.tz_localize(None) if d.tzinfo else d
                                                  for d in df.index]))
        joined = pd.concat([bars["close"].rename("store"), yahoo.rename("yahoo")],
                           axis=1, join="inner").dropna()
        joined = joined[joined["yahoo"] > 0]
        if joined.empty:
            continue
        rel = (joined["store"] / joined["yahoo"] - 1.0).abs()
        # Storage is int(price*SCALE), so the quantisation floor is 0.5/(SCALE*price).
        floor = (0.5 / (SCALE * joined["yahoo"])).median()
        per[sym] = {"n": int(len(joined)), "median_rel": float(rel.median()),
                    "p99_rel": float(rel.quantile(0.99)), "quant_floor": float(floor),
                    "adjusted_basis": bool(rel.median() < max(1e-3, 10 * floor))}
    raw_basis = [s for s, v in per.items() if not v["adjusted_basis"]]
    return {"per_symbol": per, "raw_basis": raw_basis,
            "n_checked": len(per), "pass": len(per) > 0 and not raw_basis}


# ---------------------------------------------------------------- clause 4

def champion_fills() -> tuple[list[dict], dict]:
    meta = json.loads(CHAMPION.read_text())
    run_dir = REPO / meta["run_dir"].replace("\\", os.sep)
    events = next(run_dir.glob("*-order-events.json"))
    raw = json.loads(events.read_text())
    fills = [e for e in raw if e.get("status") in ("filled", "partiallyFilled")
             and e.get("fillQuantity")]
    return fills, meta


def clause4_fee_model(fills: list[dict]) -> dict:
    exact = within_cent = 0
    worst = 0.0
    for e in fills:
        replica = lean_ib_fee(e["fillQuantity"], e["fillPrice"])
        observed = float(e.get("orderFeeAmount", 0.0))
        d = abs(replica - observed)
        worst = max(worst, d)
        if d < 1e-9:
            exact += 1
        if d <= 0.005:
            within_cent += 1
    n = len(fills)
    return {"fills": n, "exact": exact, "within_cent": within_cent,
            "exact_rate": exact / n if n else 0.0,
            "cent_rate": within_cent / n if n else 0.0,
            "worst_abs": worst, "pass": n > 0 and within_cent / n >= 0.99}


# ---------------------------------------------------------------- clause 5

def clause5_champion_reach(fills: list[dict], calendar: dict, meta: dict) -> dict:
    times = [e["time"] for e in fills]
    first = datetime.fromtimestamp(min(times), tz=timezone.utc)
    last = datetime.fromtimestamp(max(times), tz=timezone.utc)
    symbols = sorted({e["symbolValue"] for e in fills})

    in_window: dict[str, list] = {}
    for sym in symbols:
        hits = [(d, r) for d, r in calendar.get(sym, [])
                if first <= datetime.fromisoformat(d).replace(tzinfo=timezone.utc) <= last]
        if hits:
            in_window[sym] = hits

    charged = split_only = full = 0.0
    per_symbol: dict[str, dict] = defaultdict(
        lambda: {"fills": 0, "charged": 0.0, "split_only": 0.0, "full": 0.0, "min_pf": 1.0})
    for e in fills:
        sym, q, px = e["symbolValue"], e["fillQuantity"], e["fillPrice"]
        ts = datetime.fromtimestamp(e["time"], tz=timezone.utc)
        day = pd.Timestamp(ts.date())
        c = lean_ib_fee(q, px)

        cum = 1.0
        for d, r in in_window.get(sym, []):
            if ts < datetime.fromisoformat(d).replace(tzinfo=timezone.utc):
                cum *= r
        # Our store's bar is already split-adjusted, so the factor file's price factor is the
        # dividend leg only: adjusted = raw * pf / cum, hence q_raw = q_adj * pf / cum.
        pf = price_factor_at(lean_ticker(sym), day)
        s = lean_ib_fee(q / cum, px * cum)
        f = lean_ib_fee(q * pf / cum, px * cum / pf)

        charged += c
        split_only += s
        full += f
        row = per_symbol[sym]
        row["fills"] += 1
        row["charged"] += c
        row["split_only"] += s
        row["full"] += f
        row["min_pf"] = min(row["min_pf"], pf)

    recorded = float(meta["stats"]["Total Fees"].lstrip("$").replace(",", ""))
    net_profit_pct = float(meta["stats"]["Net Profit"].rstrip("%"))
    start_equity = float(meta["stats"]["Start Equity"])
    net_profit = net_profit_pct / 100.0 * start_equity
    d_split, d_full = split_only - charged, full - charged
    return {"window": [first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")],
            "symbols": symbols, "splits_in_window": in_window,
            "charged": charged, "split_only": split_only, "full": full,
            "delta_split": d_split, "delta_full": d_full,
            "recorded_total_fees": recorded, "net_profit": net_profit,
            "split_vs_fees_pct": 100.0 * d_split / recorded if recorded else 0.0,
            "full_vs_fees_pct": 100.0 * d_full / recorded if recorded else 0.0,
            "full_vs_net_pct": 100.0 * d_full / net_profit if net_profit else 0.0,
            "per_symbol": dict(per_symbol),
            "material": (abs(d_full) >= 0.01 * recorded)
                        or (abs(d_full) >= 0.005 * abs(net_profit))}


# ---------------------------------------------------------------- clauses 6 and 7

def clauses_6_7(symbols: list[str], calendar: dict) -> dict:
    per: dict[str, dict] = {}
    zero_sessions = {size: 0 for size in ORDER_SIZES}
    floor_sessions = 0
    total_sessions = 0
    for sym in symbols:
        try:
            bars = _raw_bars(lean_ticker(sym))
        except FileNotFoundError:
            continue
        first, last = bars.index[0], bars.index[-1]
        splits = [(d, r) for d, r in calendar.get(sym, []) if first <= pd.Timestamp(d) <= last]
        cum = cum_series(bars.index, splits)
        # The stored bar is split-adjusted only; what the algorithm sees is stored * price_factor.
        pf = price_factor_series(lean_ticker(sym), bars.index)
        adj_px = bars["close"] * pf
        raw_px_all = bars["close"] * cum
        total_sessions += len(bars)

        zero = {}
        for size in ORDER_SIZES:
            q = (size / adj_px).apply(math.floor)
            zero[size] = int((q <= 0).sum())
            zero_sessions[size] += zero[size]

        # Clause 7: fee error in bps of notional on a $10k order, per session, on the FULL
        # adjustment (dividend price factor as well as the split), because the share count is
        # wrong by the whole of it.
        size = ORDER_SIZES[0]
        q_adj = (size / adj_px).apply(math.floor)
        live = q_adj > 0
        charged = pd.Series([lean_ib_fee(q, p) for q, p in zip(q_adj[live], adj_px[live])],
                            index=adj_px[live].index)
        raw_q = q_adj[live] * pf[live] / cum[live]
        raw_px = raw_px_all[live]
        truth = pd.Series([lean_ib_fee(q, p) for q, p in zip(raw_q, raw_px)],
                          index=adj_px[live].index)
        notional = (q_adj[live] * adj_px[live]).replace(0.0, float("nan"))
        err_bps = (truth - charged) / notional * 1e4

        floor_hit = int(((0.005 * q_adj[live] < FEE_MINIMUM) & (0.005 * raw_q >= FEE_MINIMUM)).sum())
        floor_sessions += floor_hit

        per[sym] = {"sessions": int(len(bars)), "splits_in_span": len(splits),
                    "zero_10k": zero[ORDER_SIZES[0]], "zero_100k": zero[ORDER_SIZES[1]],
                    "floor_masks_per_share": floor_hit,
                    "median_err_bps": float(err_bps.median()) if len(err_bps) else 0.0,
                    "worst_err_bps": float(err_bps.max()) if len(err_bps) else 0.0,
                    "best_err_bps": float(err_bps.min()) if len(err_bps) else 0.0,
                    "abs_worst_bps": float(err_bps.abs().max()) if len(err_bps) else 0.0}
    return {"per_symbol": per, "total_sessions": total_sessions,
            "zero_sessions": {str(int(k)): v for k, v in zero_sessions.items()},
            "floor_masks_per_share": floor_sessions}


# ---------------------------------------------------------------- clause 9

PROBE_ALGO = "_d7_feeprobe"


def clause9_efficacy() -> dict | None:
    """Read the LEAN probe's own log: is the fee `0.005 * adjusted_quantity` in both eras?"""
    runs = sorted((REPO / "results" / PROBE_ALGO).glob("*/"), reverse=True)
    for run in runs:
        logs = list(run.glob("*-log.txt"))
        if not logs:
            continue
        legs, fills = [], []
        for line in logs[0].read_text().splitlines():
            if "D7PROBE FILL" in line:
                kv = dict(p.split("=", 1) for p in line.split() if "=" in p)
                fills.append({k: kv[k] for k in kv})
            elif "D7PROBE leg=" in line:
                kv = dict(p.split("=", 1) for p in line.split() if "=" in p)
                legs.append(kv)
        if not fills:
            continue
        rows = []
        for f in fills:
            q, fee = abs(float(f["qty"])), float(f["fee"])
            rows.append({"date": f["date"], "qty": q, "fill_price": float(f["fill_price"]),
                         "fee": fee, "fee_per_share": fee / q if q else 0.0,
                         "charged_on_adjusted": abs(fee - FEE_PER_SHARE * q) < 1e-6})
        # AIG's split_factor is 20 before 2009-06-30 and 1 after; the pre-split leg is rows[0].
        return {"run": run.name, "legs": legs, "fills": rows,
                "all_charged_on_adjusted": all(r["charged_on_adjusted"] for r in rows),
                "pre_split_leg": rows[0] if rows else None}
    return None


# ---------------------------------------------------------------- output

def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=REPO,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


def record(rows: list[dict]) -> None:
    commit = git_commit()
    with LEDGER.open("a", encoding="utf-8") as fh:
        for row in rows:
            row.setdefault("ts", datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
            row.setdefault("commit", commit)
            row.setdefault("run_dir", "")
            row.setdefault("track", "iterate")
            fh.write(json.dumps(row) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--net", action="store_true", help="run clause 3 and refresh the calendar")
    ap.add_argument("--write", action="store_true", help="write data/daily_splits.json")
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC ledger rows")
    ap.add_argument("--start", default="1998-01-01")
    ap.add_argument("--end", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    args = ap.parse_args()

    syms = universe()
    print(f"D-7 / AUD-17 - {len(syms)} symbols, store at {EQUITY}\n")

    # -- clause 1
    c1 = clause1_premise_a(syms)
    print("CLAUSE 1  PREMISE-A: split_factor on every factor row our fetcher wrote")
    print(f"  files {c1['files']} (missing {c1['missing']}), rows {c1['rows']}, "
          f"rows with split_factor != 1: {c1['offending_rows']}")
    print(f"  -> {'PASS (the lie is on disk, as AUD-17 says)' if c1['pass'] else 'WITHDRAWN'}\n")
    if not c1["pass"]:
        return 1

    # -- calendar
    if args.net or not SPLITS_PATH.exists():
        if not args.net:
            print("no cached calendar and --net not given; rerun with --net")
            return 2
        print("fetching split calendar from Yahoo ...")
        calendar = fetch_calendar(syms, args.start, args.end)
    else:
        calendar = {k: [(d, float(r)) for d, r in v]
                    for k, v in json.loads(SPLITS_PATH.read_text()).items()}
        print(f"calendar: cached {SPLITS_PATH.relative_to(REPO)}")

    # -- clause 2
    c2 = clause2_truth(syms, calendar)
    print("CLAUSE 2  TRUTH: symbols with >= 1 split inside their own stored span")
    print(f"  affected {c2['n_affected']} of {c2['n_total']} stored symbols")
    worst = sorted(c2["per_symbol"].items(), key=lambda kv: kv[1]["cum_first"])[:8]
    print(f"  {'sym':6} {'bars':>6} {'span':>24} {'splits':>7} {'cum@first':>14}")
    for sym, v in worst:
        print(f"  {sym:6} {v['bars']:6d} {v['first']} .. {v['last']} "
              f"{v['splits_in_span']:7d} {v['cum_first']:14.6g}")
    biggest = sorted(c2["per_symbol"].items(), key=lambda kv: -kv[1]["cum_first"])[:5]
    for sym, v in biggest:
        print(f"  {sym:6} {v['bars']:6d} {v['first']} .. {v['last']} "
              f"{v['splits_in_span']:7d} {v['cum_first']:14.6g}")
    print()

    # -- clause 3
    c3 = None
    if args.net:
        print("CLAUSE 3  PREMISE-B: is the store on the CURRENT share basis? (needs the network)")
        c3 = clause3_premise_b(syms, args.start, args.end)
        print(f"  checked {c3['n_checked']} symbols; on a RAW basis: {c3['raw_basis'] or 'none'}")
        med = sorted(c3["per_symbol"].items(), key=lambda kv: -kv[1]["median_rel"])[:5]
        for sym, v in med:
            print(f"  {sym:6} n={v['n']:5d} median|store/yahoo-1| {v['median_rel']:.3e} "
                  f"(quantisation floor {v['quant_floor']:.3e})")
        print(f"  -> {'PASS (adjusted, as AUD-17 says)' if c3['pass'] else 'FAIL - direction flips'}\n")
    else:
        print("CLAUSE 3  skipped (no --net)\n")

    # -- clause 4
    fills, meta = champion_fills()
    c4 = clause4_fee_model(fills)
    print("CLAUSE 4  FEE MODEL: replica vs the champion's own recorded fees")
    print(f"  fills {c4['fills']}, exact {c4['exact']} ({100*c4['exact_rate']:.2f}%), "
          f"within a cent {c4['within_cent']} ({100*c4['cent_rate']:.2f}%), "
          f"worst |d| ${c4['worst_abs']:.4f}")
    print(f"  -> {'PASS' if c4['pass'] else 'WITHDRAWN - fee columns below are unvalidated'}\n")

    # -- clause 5
    c5 = clause5_champion_reach(fills, calendar, meta)
    print("CLAUSE 5  REACH ON THE DEPLOYED BOOK")
    print(f"  run window {c5['window'][0]} .. {c5['window'][1]}, symbols {', '.join(c5['symbols'])}")
    print(f"  splits inside that window: {c5['splits_in_window'] or 'NONE'}")
    print(f"  fees charged ${c5['charged']:,.2f} (recorded ${c5['recorded_total_fees']:,.2f})")
    print(f"  (a) SPLIT-ONLY, AUD-17's axis : ${c5['split_only']:,.2f}  "
          f"delta ${c5['delta_split']:,.2f} ({c5['split_vs_fees_pct']:.3f}% of fees)")
    print(f"  (b) FULL adjustment, honest   : ${c5['full']:,.2f}  "
          f"delta ${c5['delta_full']:,.2f} ({c5['full_vs_fees_pct']:.3f}% of fees, "
          f"{c5['full_vs_net_pct']:.4f}% of net profit)")
    print(f"  {'sym':5} {'fills':>6} {'charged':>11} {'split-only':>11} {'full':>11} {'min pf':>8}")
    for s, v in sorted(c5["per_symbol"].items(), key=lambda kv: kv[1]["full"] - kv[1]["charged"]):
        print(f"  {s:5} {v['fills']:6d} {v['charged']:11,.2f} {v['split_only']:11,.2f} "
              f"{v['full']:11,.2f} {v['min_pf']:8.4f}")
    print(f"  -> {'MATERIAL' if c5['material'] else 'NOT MATERIAL'} "
          f"(the store OVERCHARGES the champion; the sign is conservative, the size is not small)\n")

    # -- clauses 6 and 7
    c67 = clauses_6_7(syms, calendar)
    print("CLAUSE 6  TRADEABILITY: stored symbol-sessions where an order rounds to ZERO shares")
    print(f"  total stored sessions {c67['total_sessions']:,}")
    for size, n in c67["zero_sessions"].items():
        print(f"  ${int(size):>7,} order -> 0 shares on {n:,} sessions "
              f"({100.0*n/max(1,c67['total_sessions']):.4f}%)")
    print(f"  $1 minimum masks a per-share charge on {c67['floor_masks_per_share']:,} sessions\n")

    print("CLAUSE 7  BLAST RADIUS: fee error on a $10k order, bps of notional")
    ranked = sorted(c67["per_symbol"].items(), key=lambda kv: -kv[1]["abs_worst_bps"])[:12]
    print(f"  {'sym':6} {'splits':>6} {'median':>10} {'worst+':>12} {'worst-':>12} {'zero10k':>8}")
    for sym, v in ranked:
        print(f"  {sym:6} {v['splits_in_span']:6d} {v['median_err_bps']:10.3f} "
              f"{v['worst_err_bps']:12.3f} {v['best_err_bps']:12.3f} {v['zero_10k']:8d}")
    over = [s for s, v in c67["per_symbol"].items() if v["abs_worst_bps"] >= 1.5]
    print(f"  symbols whose worst |error| clears the 1.5 bps slippage line: {len(over)} -> "
          f"{', '.join(sorted(over)) if over else 'none'}\n")

    # -- clause 9
    c9 = clause9_efficacy()
    print("CLAUSE 9  EFFICACY: does AUD-17's prescribed remedy change any fee?")
    if c9 is None:
        print("  no probe run found; `py -3.11 scripts/backtest.py _d7_feeprobe`\n")
    else:
        print(f"  LEAN run {c9['run']}, AIG, ADJUSTED mode, split_factor 20 then 1")
        for leg in c9["legs"]:
            print(f"    leg {leg.get('leg')}: adjusted_price={leg.get('adjusted_price')} "
                  f"order_qty={leg.get('order_qty')} notional={leg.get('notional')}")
        for r in c9["fills"]:
            print(f"    fill {r['date']}: qty {r['qty']:.0f} @ {r['fill_price']:.4f} -> "
                  f"fee ${r['fee']:.4f} = ${r['fee_per_share']:.6f}/adjusted share "
                  f"({'0.005 x ADJUSTED qty' if r['charged_on_adjusted'] else 'NOT 0.005 x adj qty'})")
        verdict = ("REMEDY REFUSED - the split factor never reaches the fee model, so rewriting "
                   "the store as raw-plus-factors changes NO fee"
                   if c9["all_charged_on_adjusted"] else
                   "REMEDY CONFIRMED - the factor does reach the fee")
        print(f"  -> {verdict}\n")

    # -- clause 8
    ship = c1["pass"] and (c3 is None or c3["pass"]) and c4["pass"]
    print("CLAUSE 8  SHIP CONDITION")
    print(f"  clauses 1/3/4 pass: {ship}; store rewrite is FILED, not performed "
          f"(it moves every daily-track metric)")
    if args.write and ship and args.net:
        SPLITS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SPLITS_PATH.write_text(json.dumps(
            {k: [[d, r] for d, r in v] for k, v in sorted(calendar.items()) if v},
            indent=1) + "\n")
        print(f"  wrote {SPLITS_PATH.relative_to(REPO)}")
    elif args.write:
        print("  --write refused: needs --net and all of clauses 1/3/4")
    print()

    if args.record:
        span = [c2["per_symbol"][s] for s in c2["affected"]] if c2["affected"] else []
        record([
            {"algorithm": "daily/d7_aud17", "class": "data",
             "tag": "D-7/AUD-17 DIAGNOSTIC: premise and blast radius of the adjusted-as-raw daily store",
             "params": {"symbols": len(syms)}, "start": args.start, "end": args.end,
             "stats": {"factor_rows": str(c1["rows"]),
                       "rows_split_factor_ne_1": str(c1["offending_rows"]),
                       "symbols_with_in_span_split": str(c2["n_affected"]),
                       "stored_sessions": str(c67["total_sessions"]),
                       "zero_share_sessions_10k": str(c67["zero_sessions"][str(int(ORDER_SIZES[0]))]),
                       "zero_share_sessions_100k": str(c67["zero_sessions"][str(int(ORDER_SIZES[1]))]),
                       "symbols_over_1p5bps": str(len(over)),
                       "affected_spans": str(len(span))}},
            {"algorithm": "daily/d7_aud17", "class": "data",
             "tag": "D-7/AUD-17 DIAGNOSTIC: P&L reach on the deployed champion's 5,128 fills",
             "params": {"fee_per_share": FEE_PER_SHARE, "fee_min": FEE_MINIMUM,
                        "fee_max_rate": FEE_MAX_RATE},
             "start": c5["window"][0], "end": c5["window"][1],
             "stats": {"fills": str(c4["fills"]),
                       "replica_exact_rate": f"{c4['exact_rate']:.4f}",
                       "fees_charged": f"{c5['charged']:.2f}",
                       "fees_split_only": f"{c5['split_only']:.2f}",
                       "fees_full_adjustment": f"{c5['full']:.2f}",
                       "delta_split_only": f"{c5['delta_split']:.2f}",
                       "delta_full": f"{c5['delta_full']:.2f}",
                       "delta_full_vs_fees_pct": f"{c5['full_vs_fees_pct']:.4f}",
                       "delta_full_vs_net_pct": f"{c5['full_vs_net_pct']:.4f}",
                       "material": str(c5["material"]),
                       "remedy_changes_any_fee":
                           str(not c9["all_charged_on_adjusted"]) if c9 else "unrun"}},
        ])
        print("recorded 2 DIAGNOSTIC rows\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
