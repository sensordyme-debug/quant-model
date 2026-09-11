#!/usr/bin/env python
"""S-20: what the daily champion gives up by sitting in *cash* when the regime filter fires.

The mechanism, stated before anything is fitted
-----------------------------------------------
`signals.risk_on` switches the book off whenever SPY's trailing 20-day realized vol
exceeds 1.5x its own 1-year median. S-15 priced that switch: turning it off earns
+2.02 CAR and costs 6.3 points of drawdown, so it is a *drawdown* instrument and not a
return one, and it stays. But the switch has only ever had one off-state - hold nothing.

A volatility crisis is exactly the state in which Treasuries and gold have historically
been bid, and both are already in `RANK_UNIVERSE`, so the sleeve *can* hold them - it
just never does in this state, because the regime gate short-circuits before the
ranking runs. S-20 asks whether the off-state should be a defensive holding instead of
cash: same gate, same trigger, different thing held while it is pulled.

This is not a ranker lever (the backlog forbids those on the evidence of S-14/S-15) and
it is not a risk-posture parameter (the owner's questions in BLOCKERS.md are all about
size). It changes what the book *does* in a state it already recognises.

Stages
------
`--probe`   Pure measurement on the LEAN store, nothing fitted: how often the gate
            fires, how long its episodes last, and what each defensive candidate earned
            on exactly those sessions against cash and against the risk-on book.
`--report`  Read the LEAN cells written by `_s20_runs.sh` out of the ledger and print the
            comparison table plus paired daily statistics against the control.

Usage
-----
    py -3.11 scripts/sweep_s20.py --probe
    bash scripts/_s20_runs.sh
    python scripts/sweep_s20.py --report
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "algorithms" / "s1_momo"))

import lean_prices  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "research" / "experiments.jsonl"

START = "2012-01-03"
END = "2026-09-04"
TRADING_DAYS = 252

#: Everything the probe measures. The first three are the defensive sleeve S-20 proposes;
#: SPY is the do-nothing benchmark for the same sessions and SHV/BIL do not exist in the
#: store, so "cash" is literally 0.0.
CANDIDATES = ["TLT", "IEF", "GLD", "SLV", "HYG", "SPY"]


def regime_off(spy: pd.Series, vol_window=20, median_window=252, threshold=1.5) -> pd.Series:
    """`signals.risk_on` re-expressed as a vectorised series over the whole history.

    Reproduces the shipped rule exactly: the decision made on the close of D uses the
    trailing `vol_window` standard deviation of returns through D and the median of that
    same series over the trailing `median_window` rows, and the book it decides is held
    over D+1. `ddof=1` and `>=` both match `signals.risk_on`.
    """
    vol = spy.pct_change().rolling(vol_window).std(ddof=1) * np.sqrt(TRADING_DAYS)
    median = vol.rolling(median_window).median()
    off = vol >= threshold * median
    return off.where(vol.notna() & median.notna())


def episodes(flag: pd.Series) -> pd.DataFrame:
    """Contiguous runs of True in a boolean series, as (start, end, sessions)."""
    f = flag.fillna(False).astype(bool)
    grp = (f != f.shift()).cumsum()
    out = []
    for _, chunk in f[f].groupby(grp[f]):
        out.append((chunk.index[0].date(), chunk.index[-1].date(), len(chunk)))
    return pd.DataFrame(out, columns=["start", "end", "sessions"])


def tstat(x: pd.Series) -> float:
    x = x.dropna()
    if len(x) < 2 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def probe() -> None:
    px = lean_prices.load_closes(CANDIDATES)
    spy = px["SPY"].dropna()
    # SPY is the longest series in the store, but GLD/SLV/HYG list later, so `px` carries
    # rows SPY does not. Reindexing keeps the gate on SPY's own calendar.
    off = regime_off(spy).reindex(px.index)

    # The signal decided on the close of D is held over D+1, so the return that a
    # risk-off decision earns is the *next* session's.
    rets = px.pct_change(fill_method=None).shift(-1)
    window = (px.index >= START) & (px.index <= END)
    off_w = off[window].fillna(False)
    rets_w = rets[window]

    n = int(len(off_w))
    n_off = int(off_w.sum())
    print(f"S-20 probe  {px.index[window][0].date()} .. {px.index[window][-1].date()}")
    print(f"  sessions {n}, risk-off {n_off} ({100.0 * n_off / n:.1f}%), "
          f"risk-on {n - n_off}")

    eps = episodes(off_w)
    print(f"  episodes {len(eps)}  median length {eps.sessions.median():.0f} sessions  "
          f"longest {eps.sessions.max()}  total {eps.sessions.sum()}")
    print("  five longest:")
    for _, r in eps.sort_values("sessions", ascending=False).head(5).iterrows():
        print(f"    {r.start} .. {r.end}  {r.sessions:>3} sessions")

    print("\n  what each candidate earned on exactly the risk-off sessions "
          "(daily, bps, vs cash = 0):")
    print(f"    {'name':<6} {'bps/day':>9} {'t':>7} {'ann %':>8} {'hit':>7} "
          f"{'worst':>9} {'risk-on bps':>12}")
    rows = {}
    for t in CANDIDATES:
        r_off = rets_w[t][off_w].dropna()
        r_on = rets_w[t][~off_w].dropna()
        ann = (1.0 + r_off.mean()) ** TRADING_DAYS - 1.0
        rows[t] = r_off
        print(f"    {t:<6} {1e4 * r_off.mean():>9.2f} {tstat(r_off):>7.2f} "
              f"{100 * ann:>8.2f} {100 * (r_off > 0).mean():>6.1f}% "
              f"{100 * r_off.min():>8.2f}% {1e4 * r_on.mean():>12.2f}")

    print("\n  pairwise, on risk-off sessions only (row minus column, bps/day, t):")
    names = ["TLT", "IEF", "GLD", "SPY"]
    print("           " + "".join(f"{c:>16}" for c in names))
    for a in names:
        cells = []
        for b in names:
            if a == b:
                cells.append(f"{'-':>16}")
                continue
            d = (rows[a] - rows[b]).dropna()
            cells.append(f"{1e4 * d.mean():>9.1f}/{tstat(d):>5.2f}")
        print(f"    {a:<6} " + "".join(cells))

    # The honest question behind the whole item: is the defensive return *conditional* on
    # the crisis, or would the same asset have paid anyway? If the two columns match, the
    # mechanism is "hold bonds", not "hold bonds in a crisis", and it belongs in the
    # ranking rather than in the gate.
    print("\n  conditionality check (risk-off minus risk-on, bps/day, t):")
    for t in ["TLT", "IEF", "GLD"]:
        r_off, r_on = rets_w[t][off_w].dropna(), rets_w[t][~off_w].dropna()
        se = np.sqrt(r_off.var(ddof=1) / len(r_off) + r_on.var(ddof=1) / len(r_on))
        diff = r_off.mean() - r_on.mean()
        print(f"    {t:<6} {1e4 * diff:>9.2f} {diff / se:>7.2f}")

    # A crisis-conditional sleeve is worth nothing if it is only ever one asset, and it is
    # dangerous if the pick is unstable, so report how a momentum pick among the three
    # would have behaved. The score is the shipped blend, computed on the same closes.
    print("\n  momentum pick among TLT/IEF/GLD on risk-off sessions "
          "(shipped 20/60/120/252 blend, 5-session skip on the long horizons):")
    sleeve = ["TLT", "IEF", "GLD"]
    score = pd.DataFrame(index=px.index, columns=sleeve, dtype=float)
    for lb in (20, 60, 120, 252):
        skip = 5 if lb >= 120 else 0
        part = px[sleeve].shift(skip) / px[sleeve].shift(skip + lb) - 1.0
        score = score.add(part / 4.0, fill_value=0.0) if lb != 20 else part / 4.0
    pick = score.idxmax(axis=1).where(score.max(axis=1) > 0.0)
    picked_ret = pd.Series(
        [rets_w[t].get(d, np.nan) if isinstance(t, str) else 0.0
         for d, t in pick[window].items()], index=px.index[window])
    picked_ret = picked_ret.fillna(0.0)[off_w]
    counts = pick[window][off_w].value_counts(dropna=False)
    print("    pick counts: " + ", ".join(
        f"{('cash' if not isinstance(k, str) else k)}={v}" for k, v in counts.items()))
    print(f"    bps/day {1e4 * picked_ret.mean():>8.2f}  t {tstat(picked_ret):>6.2f}  "
          f"ann {100 * ((1 + picked_ret.mean()) ** TRADING_DAYS - 1):>7.2f}%  "
          f"worst {100 * picked_ret.min():>6.2f}%")


def ledger_rows(track: str) -> list[dict]:
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").strip().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("tag", "").startswith(track):
            rows.append(row)
    return rows


def _num(stats: dict, key: str) -> float:
    raw = str(stats.get(key, "")).replace("%", "").replace("$", "").replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return float("nan")


def daily_equity(run_dir: str) -> pd.Series:
    """LEAN's own daily equity curve for one run, as a date-indexed series.

    The two traps S-19 documented apply here unchanged: the `Strategy Equity` series
    carries several samples per session, so only the midnight stamps (04:00/05:00 UTC
    either side of the daylight-saving switch) are used, and a midnight point stamped D is
    the portfolio *after* the close of D-1, so the series is shifted back one session.
    """
    path = REPO / run_dir / "S1MomentumRotationAlgorithm.json"
    if not path.exists():
        raise FileNotFoundError(f"no LEAN result at {path}")
    blob = json.loads(path.read_text(encoding="utf-8"))
    vals = blob["charts"]["Strategy Equity"]["series"]["Equity"]["values"]
    s = pd.Series([v[4] for v in vals],
                  index=pd.to_datetime([v[0] for v in vals], unit="s"))
    s = s[s.index.hour.isin([4, 5])]
    s.index = s.index.normalize()
    return s.groupby(level=0).last().shift(-1).dropna()


def report() -> None:
    rows = ledger_rows("S-20")
    if not rows:
        print("no S-20 rows in the ledger yet; run scripts/_s20_runs.sh first")
        return
    print(f"{'cell':<44} {'orders':>7} {'CAR':>8} {'Sharpe':>7} {'MaxDD':>7} "
          f"{'std':>6} {'PSR':>7} {'fees':>10}")
    control = None
    for r in rows:
        s = r["stats"]
        label = r["tag"][len("S-20 "):] if r["tag"].startswith("S-20 ") else r["tag"]
        print(f"{label:<44} {s.get('Total Orders', ''):>7} "
              f"{_num(s, 'Compounding Annual Return'):>7.3f}% "
              f"{_num(s, 'Sharpe Ratio'):>7.3f} "
              f"{_num(s, 'Drawdown'):>6.1f}% {_num(s, 'Annual Standard Deviation'):>6.3f} "
              f"{_num(s, 'Probabilistic Sharpe Ratio'):>6.1f}% "
              f"${_num(s, 'Total Fees'):>9,.0f}")
        if label.startswith("control:"):
            control = r

    if control is None:
        return
    base = daily_equity(control["run_dir"])
    base_ret = base.pct_change().dropna()
    base_car = _num(control["stats"], "Compounding Annual Return")
    base_std = _num(control["stats"], "Annual Standard Deviation")

    # S-15's lesson, applied to this item before anything is claimed: on this sleeve most
    # levers that add return add it by carrying more risk. The control scaled to the cell's
    # own realized vol is the only fair return comparison, and a cell that does not beat
    # *that* has bought size, not edge.
    print("\nvol-matched: the control's own CAR scaled to each cell's realized vol")
    print(f"  {'cell':<44} {'std':>6} {'CAR':>8} {'matched':>9} {'excess':>8}")
    for r in rows:
        if r is control or "IS 2012" in r["tag"] or "OOS 2020" in r["tag"]:
            continue
        s = r["stats"]
        std, car = _num(s, "Annual Standard Deviation"), _num(s, "Compounding Annual Return")
        matched = base_car * std / base_std
        print(f"  {r['tag'][len('S-20 '):]:<44} {std:>6.3f} {car:>7.3f}% "
              f"{matched:>8.3f}% {car - matched:>+7.3f}")

    # The mechanism only touches the sessions the gate is off for. Splitting the paired
    # difference on that flag is the check that it does exactly what it says: the risk-on
    # column has to be zero, or something else changed.
    # LEAN's equity chart is sampled on *calendar* days (S-19), so it carries weekends and
    # holidays at an unchanged mark. Those are not sessions and they dilute every t-statistic
    # here; the paired statistics run on SPY's own trading calendar.
    spy = lean_prices.load_closes(["SPY"])["SPY"].dropna()
    cal = spy.index
    base_ret = base.reindex(base.index.intersection(cal)).pct_change(fill_method=None).dropna()
    off = regime_off(spy).reindex(base_ret.index).fillna(False).astype(bool)
    print("\npaired daily returns against the control (bps/day, t):")
    print(f"  {'cell':<44} {'all':>15} {'risk-off':>15} {'risk-on':>15}")
    for r in rows:
        if r is control:
            continue
        try:
            eq = daily_equity(r["run_dir"])
            other = eq.reindex(eq.index.intersection(cal)).pct_change(fill_method=None).dropna()
        except (FileNotFoundError, KeyError):
            continue
        common = base_ret.index.intersection(other.index)
        d = (other.reindex(common) - base_ret.reindex(common)).dropna()
        f = off.reindex(d.index).fillna(False)
        cells = []
        for sub in (d, d[f], d[~f]):
            cells.append(f"{1e4 * sub.mean():>8.2f}/{tstat(sub):>5.2f}" if len(sub) > 2
                         else f"{'-':>14}")
        print(f"  {r['tag'][len('S-20 '):]:<44} " + "".join(f"{c:>15}" for c in cells)
              + f"  n={len(d)}/{int(f.sum())}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true", help="measure the risk-off state")
    ap.add_argument("--report", action="store_true", help="read the LEAN cells back")
    args = ap.parse_args()
    if not (args.probe or args.report):
        ap.error("pick --probe or --report")
    if args.probe:
        probe()
    if args.report:
        report()


if __name__ == "__main__":
    main()
