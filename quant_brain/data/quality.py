"""The data quality gate. Deterministic, three-valued, and it stops a FAIL from entering.

WHY THIS EXISTS ALONGSIDE `futures_cme.dataquality`
------------------------------------------------------
That module is good and stays. It is also *futures-specific*, *raises on FAIL and forgets a
WARN*, and has three defects pinned as strict xfails in `tests/test_golden_futures.py` -
missing interior bars, duplicate timestamps, and impossible OHLC are not seen on the futures
path at all. This gate is the canonical-layer counterpart: provider-agnostic, running on the
canonical schema, and producing a REPORT OBJECT that is hashed onto the manifest so a result
carries the verdict it ran under rather than whatever the checker says today.

THE THREE VALUES, AND WHY A WARN HAS TO ARGUE FOR ITSELF
-----------------------------------------------------------
    PASS   nothing found.
    WARN   something found, and research may still proceed - but the finding must carry a
           `why_allowed` sentence saying WHY. A warning with no argument is a finding
           somebody decided to ignore, and six months later nobody can tell which.
    FAIL   research may not proceed. `require_usable` raises.

There is deliberately no "INFO" level. A checker that can emit a level nobody has to act on
grows one, and then everything is an INFO.

DETERMINISM
-----------
Same bars in, same report out, byte for byte - the report hash is part of the manifest and
therefore part of provenance. No timestamps, no random sampling, no dict ordering leaking
into the output.
"""
from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_brain.data.schema import validate_frame


class Level(str, enum.Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


#: Ordered worst-first, so `max` over levels is the report's status.
_ORDER = {Level.PASS: 0, Level.WARN: 1, Level.FAIL: 2}


@dataclass(frozen=True)
class Finding:
    check: str
    level: Level
    detail: str
    #: Required on a WARN. A warning that cannot say why research is still allowed is a
    #: finding somebody shrugged at.
    why_allowed: str = ""
    count: int = 0

    def line(self) -> str:
        tail = f"  [allowed: {self.why_allowed}]" if self.why_allowed else ""
        return f"{self.level.value:4} {self.check:26} {self.detail}{tail}"


@dataclass
class QualityReport:
    dataset_id: str
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def add(self, check: str, level: Level, detail: str, *, why_allowed: str = "",
            count: int = 0) -> None:
        if level is Level.WARN and not why_allowed:
            raise ValueError(
                f"{check}: a WARN must state why research is still allowed. Either give a "
                f"reason or make it a FAIL.")
        self.findings.append(Finding(check, level, detail, why_allowed, count))

    @property
    def status(self) -> Level:
        if not self.findings:
            return Level.PASS
        return max((f.level for f in self.findings), key=lambda x: _ORDER[x])

    @property
    def failed(self) -> bool:
        return self.status is Level.FAIL

    def of(self, level: Level) -> list[Finding]:
        return [f for f in self.findings if f.level is level]

    @property
    def report_hash(self) -> str:
        """Deterministic over the findings and the stats, so provenance can pin it."""
        h = hashlib.sha256()
        for f in self.findings:
            h.update(f"{f.check}\x1f{f.level.value}\x1f{f.detail}\x1f{f.count}".encode())
        for k in sorted(self.stats):
            h.update(f"{k}\x1f{self.stats[k]}".encode())
        return h.hexdigest()[:16]

    def render(self) -> str:
        head = (f"{self.dataset_id}: {self.status.value}  "
                f"({len(self.findings)} finding(s), hash {self.report_hash})")
        body = "\n".join("  " + f.line() for f in self.findings) or "  (nothing found)"
        stats = "\n".join(f"  {k:26} {self.stats[k]}" for k in sorted(self.stats))
        return f"{head}\n{body}\n  --- stats ---\n{stats}"


class DataQualityError(RuntimeError):
    """A dataset that must not enter research."""


# ======================================================================================
# THE CHECKS
# ======================================================================================

def _interval_minutes(bar_interval: str) -> float:
    s = str(bar_interval).strip().lower()
    for suffix, mult in (("min", 1.0), ("m", 1.0), ("h", 60.0), ("hour", 60.0),
                         ("d", 1440.0), ("day", 1440.0), ("s", 1 / 60.0)):
        if s.endswith(suffix):
            head = s[: -len(suffix)].strip() or "1"
            try:
                return float(head) * mult
            except ValueError:
                break
    raise ValueError(f"cannot read a bar interval from {bar_interval!r}")


def check(df: pd.DataFrame, *, dataset_id: str, session_timezone: str,
          expect_single_contract_per_session: bool = True,
          stale_run_warn: int = 60,
          recurring_gap_min_count: int = 10) -> QualityReport:
    """Every check, on a canonical frame. Pure: no I/O, no clock, no randomness."""
    validate_frame(df, name=dataset_id)
    rep = QualityReport(dataset_id=dataset_id)

    n = len(df)
    rep.stats["bars"] = n
    if n == 0:
        rep.add("empty", Level.FAIL, "the dataset has no bars")
        return rep

    ts = df["timestamp"]
    sym = df["contract_symbol"].astype(str)
    sess = df["session_date"]
    rep.stats["sessions"] = int(pd.Series(sess).nunique())
    rep.stats["contracts"] = int(sym.nunique())
    rep.stats["coverage_start"] = str(ts.iloc[0])
    rep.stats["coverage_end"] = str(ts.iloc[-1])

    # -- ordering ------------------------------------------------------------------------
    unsorted = int((ts.diff().dropna() < pd.Timedelta(0)).sum())
    if unsorted:
        rep.add("ordering", Level.FAIL,
                f"{unsorted} bar(s) go backwards in time; every window function downstream "
                f"assumes monotonic time", count=unsorted)
    rep.stats["out_of_order"] = unsorted

    # -- duplicates ----------------------------------------------------------------------
    dup_exact = int(df.duplicated(subset=["timestamp", "contract_symbol"]).sum())
    dup_ts = int(ts.duplicated().sum())
    rep.stats["duplicate_timestamp_contract"] = dup_exact
    rep.stats["duplicate_timestamp"] = dup_ts
    if dup_exact:
        rep.add("duplicates", Level.FAIL,
                f"{dup_exact} bar(s) repeat the same (timestamp, contract). A duplicated "
                f"bar is double-counted by every sum and defeats the counting argument "
                f"session completeness relies on", count=dup_exact)
    elif dup_ts:
        rep.add("overlapping_contracts", Level.WARN,
                f"{dup_ts} timestamp(s) carry more than one contract",
                why_allowed="a genuine overlap window is legitimate raw data; it becomes a "
                            "FAIL only if a single session is built from two contracts",
                count=dup_ts)

    # -- interval / missing bars -----------------------------------------------------------
    step = _interval_minutes(str(df["bar_interval"].iloc[0]))
    deltas = ts.diff().dropna() / pd.Timedelta(minutes=1)
    on_grid = deltas[(deltas > 0) & (deltas <= step * 1.5)]
    off_grid = int(((deltas > 0) & (deltas % step != 0)).sum())
    rep.stats["bar_interval_minutes"] = step
    rep.stats["off_grid_intervals"] = off_grid
    if off_grid:
        rep.add("timestamp_grid", Level.FAIL,
                f"{off_grid} interval(s) are not whole multiples of the declared "
                f"{step:g}-minute bar; the frame mixes resolutions", count=off_grid)
    rep.stats["median_interval_minutes"] = (float(on_grid.median())
                                            if len(on_grid) else float("nan"))

    # -- gaps, SEPARATED into recurring venue breaks and unexplained holes ------------------
    #
    # Lumping them together makes the finding useless. Measured on this repository's own ES
    # store, 249 of 326 gaps are an identical 61-minute break beginning at exactly 16:59 ET:
    # that is the CME daily maintenance halt, and reporting it as "17,565 missing bars"
    # buries the two genuine holes underneath it.
    #
    # The gate has no trading calendar and must not pretend to one (`futures_discover`
    # refuses to guess a CME holiday table for the same reason). So instead of asserting
    # which breaks are scheduled, it MEASURES recurrence: a gap of the same length starting
    # at the same venue wall-clock time, seen `recurring_gap_min_count` times or more, is a
    # schedule. Anything else is unexplained and is what the finding reports.
    gap_idx = ts.diff() / pd.Timedelta(minutes=step)
    holes = gap_idx[gap_idx > 1]
    recurring_bars = unexplained_bars = 0
    recurring_groups: list[str] = []
    unexplained: list[str] = []
    if len(holes):
        try:
            local_all = ts.dt.tz_convert(session_timezone)
        except Exception:                                        # noqa: BLE001
            local_all = ts
        prev_pos = holes.index.map(lambda i: df.index.get_loc(i) - 1)
        start_hm = local_all.iloc[list(prev_pos)].dt.strftime("%H:%M").to_numpy()
        length = holes.to_numpy()
        key = pd.Series([f"{a}+{int(b)}m" for a, b in zip(start_hm, length, strict=True)])
        counts = key.value_counts()
        for k, n_seen in counts.items():
            bars = int((length[(key == k).to_numpy()] - 1).sum())
            if n_seen >= recurring_gap_min_count:
                recurring_bars += bars
                recurring_groups.append(f"{k} x{n_seen}")
            else:
                unexplained_bars += bars
                unexplained.append(f"{k} x{n_seen}")
    rep.stats["gaps_total"] = int(len(holes))
    rep.stats["recurring_break_patterns"] = "; ".join(sorted(recurring_groups)) or "none"
    rep.stats["bars_absent_in_recurring_breaks"] = recurring_bars
    rep.stats["bars_absent_unexplained"] = unexplained_bars
    if unexplained:
        rep.add("unexplained_gaps", Level.WARN,
                f"{unexplained_bars} bar(s) absent across {len(unexplained)} gap "
                f"pattern(s) that do not recur: {'; '.join(sorted(unexplained)[:6])}",
                why_allowed="a one-off hole is a feed or venue fact rather than corruption, "
                            "and session-completeness filtering downstream DROPS the "
                            "affected sessions rather than interpolating them - so a hole "
                            "removes data instead of inventing it",
                count=unexplained_bars)

    # per-session holes, kept as a stat because a session with a hole is the unit the
    # completeness filter actually acts on
    short_sessions = 0
    for _, g in df.groupby(sess, sort=True):
        if len(g) < 2:
            continue
        d = g["timestamp"].diff().dropna() / pd.Timedelta(minutes=step)
        if (d > 1).any():
            short_sessions += 1
    rep.stats["sessions_with_holes"] = short_sessions

    # -- OHLC validity ---------------------------------------------------------------------
    o, h, low, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    bad_hl = int(np.sum(h < low))
    bad_c = int(np.sum((c > h) | (c < low)))
    bad_o = int(np.sum((o > h) | (o < low)))
    nan_px = int(np.sum(~np.isfinite(np.column_stack([o, h, low, c])).all(axis=1)))
    nonpos = int(np.sum(np.nanmin(np.column_stack([o, h, low, c]), axis=1) <= 0))
    rep.stats["ohlc_high_below_low"] = bad_hl
    rep.stats["ohlc_close_outside_range"] = bad_c
    rep.stats["ohlc_open_outside_range"] = bad_o
    rep.stats["ohlc_non_finite"] = nan_px
    rep.stats["non_positive_price"] = nonpos
    if bad_hl:
        rep.add("ohlc_validity", Level.FAIL, f"{bad_hl} bar(s) have high < low", count=bad_hl)
    if bad_c or bad_o:
        rep.add("ohlc_containment", Level.FAIL,
                f"{bad_c} close(s) and {bad_o} open(s) fall outside their own high-low range",
                count=bad_c + bad_o)
    if nan_px:
        rep.add("price_finite", Level.FAIL,
                f"{nan_px} bar(s) carry a NaN or infinite price", count=nan_px)
    if nonpos:
        rep.add("non_positive_price", Level.FAIL,
                f"{nonpos} bar(s) have a price at or below zero. On an adjusted series this "
                f"is what a deep back-adjustment does; on a raw one it is corruption",
                count=nonpos)

    # -- volume ----------------------------------------------------------------------------
    v = df["volume"].to_numpy(dtype=float)
    neg_v = int(np.sum(v < 0))
    nan_v = int(np.sum(~np.isfinite(v)))
    zero_v = int(np.sum(v == 0))
    rep.stats["negative_volume"] = neg_v
    rep.stats["non_finite_volume"] = nan_v
    rep.stats["zero_volume_bars"] = zero_v
    if neg_v:
        rep.add("volume_sign", Level.FAIL, f"{neg_v} bar(s) have negative volume",
                count=neg_v)
    if nan_v:
        rep.add("volume_finite", Level.FAIL, f"{nan_v} bar(s) have non-finite volume",
                count=nan_v)
    if zero_v and zero_v > 0.10 * n:
        rep.add("zero_volume", Level.WARN,
                f"{zero_v} of {n} bars ({zero_v / n:.1%}) traded no contracts",
                why_allowed="a zero-volume minute is real in an illiquid hour; it is a "
                            "liquidity fact rather than a data error, and the execution "
                            "model's fill assumptions are declared separately",
                count=zero_v)

    # -- stale prices ------------------------------------------------------------------------
    same = np.flatnonzero(np.diff(c) != 0)
    longest = int(np.max(np.diff(np.concatenate([[-1], same, [len(c) - 1]])))) - 1 \
        if len(c) > 1 else 0
    rep.stats["longest_unchanged_close_run"] = longest
    if longest >= stale_run_warn:
        rep.add("stale_price", Level.WARN,
                f"the close is unchanged for {longest} consecutive bars",
                why_allowed="a long flat run is normal overnight and in holiday sessions; it "
                            "becomes a problem only if it spans an RTH window, which "
                            "session filtering downstream would surface as a dead session",
                count=longest)

    # -- contracts ----------------------------------------------------------------------------
    blocks = int((sym != sym.shift()).sum())
    revisits = int(blocks - sym.nunique())
    rep.stats["contract_blocks"] = blocks
    rep.stats["contract_revisits"] = revisits
    if revisits > 0:
        rep.add("contract_interleaving", Level.FAIL,
                f"{revisits} contract(s) appear in more than one block; this is interleaved "
                f"data, not a chain, and no roll ordering over it is meaningful",
                count=revisits)

    if expect_single_contract_per_session:
        per = df.groupby(sess)["contract_symbol"].nunique()
        mixed = per[per > 1]
        rep.stats["mixed_contract_sessions"] = int(len(mixed))
        if len(mixed):
            rep.add("mixed_contract_session", Level.WARN,
                    f"{len(mixed)} session(s) contain more than one contract "
                    f"(first: {list(mixed.index)[0]})",
                    why_allowed="the roll boundary is a fixed instant and lands inside a "
                                "session when the venue clock shifts under it; the loader "
                                "drops these sessions rather than splicing across them",
                    count=int(len(mixed)))

    # -- rolls -------------------------------------------------------------------------------
    changes = np.flatnonzero(sym.to_numpy()[1:] != sym.to_numpy()[:-1]) + 1
    gaps = [abs(float(o[i] - c[i - 1])) for i in changes]
    rep.stats["rolls"] = len(changes)
    rep.stats["max_roll_gap_points"] = float(max(gaps)) if gaps else 0.0

    # -- session / timezone -------------------------------------------------------------------
    try:
        local = ts.dt.tz_convert(session_timezone)
    except Exception as exc:                                    # noqa: BLE001
        rep.add("session_timezone", Level.FAIL,
                f"cannot convert to {session_timezone!r}: {exc}")
        local = None
    if local is not None:
        offsets = local.map(lambda x: x.utcoffset())
        distinct = sorted({str(v) for v in offsets.unique()})
        rep.stats["utc_offsets_seen"] = ",".join(distinct)
        rep.stats["dst_transitions_spanned"] = max(0, len(distinct) - 1)
        # A session that straddles a DST change would carry two offsets on one date.
        per_sess = pd.DataFrame({"session": sess.to_numpy(),
                                 "utc_offset": offsets.to_numpy()})
        straddle = per_sess.groupby("session")["utc_offset"].nunique()
        n_straddle = int((straddle > 1).sum())
        rep.stats["sessions_straddling_a_dst_change"] = n_straddle
        if n_straddle:
            rep.add("dst_within_session", Level.WARN,
                    f"{n_straddle} session(s) span a UTC-offset change",
                    why_allowed="the CME weekly session legitimately spans the Sunday DST "
                                "change; it matters only if a session's wall-clock window "
                                "is applied across it, which the loader does per side",
                    count=n_straddle)

    return rep


def require_usable(df: pd.DataFrame, *, dataset_id: str, session_timezone: str,
                   **kw) -> QualityReport:
    """Run the gate and REFUSE on FAIL. The only sanctioned way in for research."""
    rep = check(df, dataset_id=dataset_id, session_timezone=session_timezone, **kw)
    if rep.failed:
        lines = "\n".join("  " + f.line() for f in rep.of(Level.FAIL))
        raise DataQualityError(
            f"{dataset_id}: this dataset must not enter research.\n{lines}\n"
            f"Nothing here is repaired automatically. Fix the source, or declare a "
            f"different dataset.")
    return rep


__all__ = ["DataQualityError", "Finding", "Level", "QualityReport", "check",
           "require_usable"]
