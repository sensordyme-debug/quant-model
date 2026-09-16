"""Compare two datasets that should describe the same economic exposure.

WHAT THIS IS FOR, AND WHAT IT REFUSES TO BE
---------------------------------------------
Two feeds for one underlying will not agree bar for bar and are not required to. They are
different books with different ticks, different fill populations and different outage
histories. What matters is whether they disagree in a way that could change a research
conclusion.

So this module measures agreement and says nothing about which feed is "better". There is
deliberately NO function that ranks sources by P&L, Sharpe, or any strategy outcome:
choosing a data source by which one makes a strategy look good is the purest form of the
thing this whole layer exists to prevent.

THE FINDING THAT MOTIVATED IT
-------------------------------
Run on this repository's own ES and MES stores, the comparison found 5,520 minutes -
2025-09-07 to 2025-09-11 - during which ES was on ESU5 (September) and MES was on MESZ5
(December). The mean price difference over that window is -54.7 points, which is not an
error in either feed: it is the September/December calendar spread, and the two stores are
simply on different contracts at the same instant because IBKR had already retired MESU5.

Any cross-instrument work spanning that window is comparing two different expiries. Nothing
in the old data path could have said so.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_brain.data.schema import validate_frame


@dataclass
class CrossSourceReport:
    """Agreement between two canonical frames. Descriptive; never prescriptive."""

    left_id: str
    right_id: str
    shared_bars: int
    left_only_bars: int
    right_only_bars: int
    #: Bars where both feeds are on the SAME contract expiry. The only ones where a price
    #: difference is a disagreement rather than a calendar spread.
    matched_expiry_bars: int
    mismatched_expiry_bars: int
    mismatched_windows: list[tuple[str, str, str, str, float]] = field(default_factory=list)
    return_correlation: float = float("nan")
    price_diff_p50: float = float("nan")
    price_diff_p99: float = float("nan")
    price_diff_max: float = float("nan")
    high_low_diff_max: float = float("nan")
    volume_ratio_median: float = float("nan")
    roll_date_differences: list[str] = field(default_factory=list)
    material_findings: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"{self.left_id} vs {self.right_id}",
                 f"  shared bars              {self.shared_bars:,}",
                 f"  left-only / right-only   {self.left_only_bars:,} / "
                 f"{self.right_only_bars:,}",
                 f"  same expiry              {self.matched_expiry_bars:,}",
                 f"  DIFFERENT expiry         {self.mismatched_expiry_bars:,}",
                 f"  return correlation       {self.return_correlation:.6f}",
                 f"  |price diff| p50/p99/max {self.price_diff_p50:.4f} / "
                 f"{self.price_diff_p99:.4f} / {self.price_diff_max:.4f}",
                 f"  |high-low| diff max      {self.high_low_diff_max:.4f}",
                 f"  volume ratio (median)    {self.volume_ratio_median:.4f}"]
        for a, b, ca, cb, mean in self.mismatched_windows:
            lines.append(f"  DIFFERENT CONTRACTS {a} .. {b}: {ca} vs {cb}, "
                         f"mean gap {mean:+.2f} pts")
        for d in self.roll_date_differences:
            lines.append(f"  roll-date difference     {d}")
        for m in self.material_findings:
            lines.append(f"  MATERIAL: {m}")
        return "\n".join(lines)


def _expiry_key(sym: pd.Series) -> pd.Series:
    """The month-code + year-digit tail, so `ESM6` and `MESM6` are recognisably the same
    expiry while `ESU5` and `MESZ5` are not. Deliberately crude and purely lexical: the
    parser is for identity, this is for pairing."""
    return sym.astype(str).str[-2:]


def compare(left: pd.DataFrame, right: pd.DataFrame, *, left_id: str, right_id: str,
            material_price_diff: float = 5.0,
            material_correlation: float = 0.98) -> CrossSourceReport:
    """Measure how two canonical frames agree. Neither is treated as the truth."""
    validate_frame(left, name=left_id)
    validate_frame(right, name=right_id)

    a = left.set_index("timestamp")
    b = right.set_index("timestamp")
    shared = a.index.intersection(b.index)
    rep = CrossSourceReport(
        left_id=left_id, right_id=right_id, shared_bars=len(shared),
        left_only_bars=len(a.index.difference(b.index)),
        right_only_bars=len(b.index.difference(a.index)),
        matched_expiry_bars=0, mismatched_expiry_bars=0)
    if not len(shared):
        rep.material_findings.append("no shared timestamps at all")
        return rep

    la, rb = a.loc[shared], b.loc[shared]
    ea, eb = _expiry_key(la["contract_symbol"]), _expiry_key(rb["contract_symbol"])
    same = (ea.to_numpy() == eb.to_numpy())
    rep.matched_expiry_bars = int(same.sum())
    rep.mismatched_expiry_bars = int((~same).sum())

    diff = (la["close"].to_numpy(float) - rb["close"].to_numpy(float))

    # windows where the two feeds are on different contracts, as contiguous blocks
    if rep.mismatched_expiry_bars:
        pair = pd.Series([f"{x}|{y}" for x, y in zip(la["contract_symbol"].astype(str),
                                                     rb["contract_symbol"].astype(str),
                                                     strict=True)], index=shared)
        bad = pair[~same]
        block = (bad != bad.shift()).cumsum()
        for _, sub in bad.groupby(block):
            ca, cb = sub.iloc[0].split("|")
            mask = shared.isin(sub.index)
            rep.mismatched_windows.append(
                (str(sub.index[0]), str(sub.index[-1]), ca, cb,
                 float(np.mean(diff[mask]))))
        rep.material_findings.append(
            f"{rep.mismatched_expiry_bars:,} shared bars have the two feeds on DIFFERENT "
            f"contract expiries. Prices there differ by the calendar spread, not by a feed "
            f"error, and any cross-instrument comparison over those bars is comparing two "
            f"different contracts.")

    # everything below is measured on the MATCHED bars only; mixing in the calendar spread
    # would make the disagreement statistics meaningless.
    if rep.matched_expiry_bars > 2:
        ca = la["close"].to_numpy(float)[same]
        cb = rb["close"].to_numpy(float)[same]
        d = np.abs(ca - cb)
        rep.price_diff_p50 = float(np.percentile(d, 50))
        rep.price_diff_p99 = float(np.percentile(d, 99))
        rep.price_diff_max = float(d.max())
        ra, rr = np.diff(ca) / ca[:-1], np.diff(cb) / cb[:-1]
        ok = np.isfinite(ra) & np.isfinite(rr)
        if ok.sum() > 2:
            rep.return_correlation = float(np.corrcoef(ra[ok], rr[ok])[0, 1])
        rep.high_low_diff_max = float(np.max(np.abs(
            (la["high"].to_numpy(float) - la["low"].to_numpy(float))[same]
            - (rb["high"].to_numpy(float) - rb["low"].to_numpy(float))[same])))
        va = la["volume"].to_numpy(float)[same]
        vb = rb["volume"].to_numpy(float)[same]
        live = (va > 0) & (vb > 0)
        if live.any():
            rep.volume_ratio_median = float(np.median(va[live] / vb[live]))

        n_big = int((d > material_price_diff).sum())
        if n_big:
            rep.material_findings.append(
                f"{n_big} matched-expiry bar(s) differ by more than "
                f"{material_price_diff} points (max {rep.price_diff_max:.2f}). On matched "
                f"contracts that is a feed disagreement, not a spread.")
        if np.isfinite(rep.return_correlation) \
                and rep.return_correlation < material_correlation:
            rep.material_findings.append(
                f"minute-return correlation is only {rep.return_correlation:.4f}; the two "
                f"feeds do not describe the same price process")

    # roll dates
    def roll_dates(f):
        s = f["contract_symbol"].astype(str)
        return {str(t.date()): v for t, v in
                zip(f.index[s.ne(s.shift()) & (np.arange(len(f)) > 0)],
                    s[s.ne(s.shift()) & (np.arange(len(f)) > 0)], strict=True)}

    ra_, rb_ = roll_dates(a), roll_dates(b)
    for day in sorted(set(ra_) | set(rb_)):
        if (day in ra_) != (day in rb_):
            who = left_id if day in ra_ else right_id
            rep.roll_date_differences.append(f"{day}: only {who} rolls")
    return rep


__all__ = ["CrossSourceReport", "compare"]
