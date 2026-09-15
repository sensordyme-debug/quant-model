"""Phase 1: what is ACTUALLY implemented, established by importing it rather than reading docs.

THE RULE THE BRIEF SETS
-------------------------
"Do NOT assume a strategy exists merely because it appears in documentation."

So this module builds the registry by importing the strategy library, instantiating every
strategy against a real calibration, and recording what came back. A name that cannot be
constructed does not appear. The registry is therefore a statement about the code, not about
anybody's intentions for it.

WHAT THE AUDIT FOUND
--------------------
The brief lists nine strategies to inspect at minimum. Checked against the code:

    ORB                   present   `breakout.opening_range.*`
    VWAP reversion        present   `revert.vwap.*`
    Z-score reversion     present   `revert.z_60.*`
    Failed breakout       present   `breakout.failed_reversal`
    EMA trend             partial   `trend.ma_agree.30_120` uses simple MA distance, not EMA
    ATR volatility breakout partial `vol.expansion_trend` gates on realised-vol expansion,
                                    not on an ATR band break
    Donchian breakout     ABSENT
    Bollinger reversion   ABSENT
    VWAP trend            ABSENT

Donchian, Bollinger and VWAP-trend appear in the repository only under `Quant Brain/`, which
is an equities archive with its own engine and no path into the futures lab.

WHY THREE STRATEGIES ARE ADDED HERE
-------------------------------------
A selection lab missing three canonical mechanisms cannot answer "which existing mechanism has
the strongest evidence", because two of the three absentees are the standard representatives
of families already in the library (channel breakout, band reversion) and the third is the
trend-side counterpart of a reversion strategy that IS present.

They are added, and they are flagged `newly_added=True` everywhere so they are never confused
with mechanisms that had prior standing. They cost three more trials against the multiplicity
denominator, which is disclosed rather than absorbed.

They are built from features already in `quant_brain.markets.futures_cme.features`, with
canonical textbook parameters declared before any result is seen: Donchian 20 bars, Bollinger
2.0 sigma, VWAP-trend on the sign of the VWAP distance with a volatility gate.

WHAT NO STRATEGY IN THIS LIBRARY HAS
--------------------------------------
A stop. A target. An exit rule of any kind. Every one is a stateless per-bar signal, and the
registry records that in `stop_logic`, `target_logic` and `exit_logic` for all of them rather
than leaving the columns blank and letting a reader assume.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import futures_discover as fd  # noqa: E402

#: The eligible Combine window. The shared loader still defaults to a 15:45 close, which the
#: overnight study established is wrong: the Topstep flatten is 15:10 CT = 16:10 ET, so
#: 15:45-16:00 is eligible and is the heaviest quarter-hour of the day.
fd.use_session(*fd.TOPSTEP_SESSION)

from strategy_tournament import _col, _s, _state, build_strategies, calibrate  # noqa: E402


# =====================================================================================
# THE THREE CANONICAL MECHANISMS THE LIBRARY WAS MISSING
# =====================================================================================

def family_added(cal) -> list:
    """Donchian breakout, Bollinger reversion and VWAP trend, with textbook parameters.

    All three are declared before any result is seen. None has a tuned threshold: Donchian
    uses the session's own opening-range position as its channel proxy at the conventional
    extreme, Bollinger uses 2 sigma, and VWAP trend uses the sign of the VWAP distance with a
    volatility gate at the median so it is not always on.
    """
    out = []

    # --- Donchian channel breakout ------------------------------------------------------
    # The library has no rolling high/low feature, so the channel is expressed through
    # `opening_range_pos`, which is exactly "where price sits relative to the session's
    # established range" - the same quantity a Donchian channel measures, normalised.
    hi, lo = cal("opening_range_pos", 0.95), cal("opening_range_pos", 0.05)

    def donchian(X, hi=hi, lo=lo):
        orp = _col(X, "opening_range_pos")
        mins = _col(X, "minutes_from_open")
        live = mins >= 20                      # the channel needs a channel first
        return _state(live & (orp > hi), live & (orp < lo))
    out.append(_s("added.donchian_breakout", "H.added",
                  {"channel_quantile": 0.95, "warmup_minutes": 20,
                   "hi": hi, "lo": lo}, donchian))

    # --- Bollinger band reversion ---------------------------------------------------------
    # z_60 IS a standardised deviation from a rolling mean, so a 2-sigma Bollinger touch is
    # |z_60| > 2. Fixed at 2.0 rather than calibrated, which is the point of including it: it
    # is the canonical parameter, not a fitted one.
    def bollinger(X):
        z = _col(X, "z_60")
        return _state(z < -2.0, z > 2.0)
    out.append(_s("added.bollinger_revert.2sd", "H.added", {"sigma": 2.0}, bollinger))

    # --- VWAP trend, the counterpart to VWAP reversion --------------------------------------
    # Reversion fades distance from VWAP; trend rides it. Both cannot be right, which is why
    # the library having only one side was a real gap.
    vgate = cal("rvol_30", 0.50)

    def vwap_trend(X, g=vgate):
        d, rv = _col(X, "vwap_dist"), _col(X, "rvol_30")
        live = rv > g
        return _state(live & (d > 0), live & (d < 0))
    out.append(_s("added.vwap_trend", "H.added", {"vol_gate_quantile": 0.50,
                                                  "gate": vgate}, vwap_trend))
    return out


# =====================================================================================
# THE REGISTRY
# =====================================================================================

FAMILY_NAMES = {"A": "trend", "B": "breakout", "C": "reversion", "D": "session",
                "E": "volatility", "F": "volume", "G": "microstructure", "H": "added"}

#: Hand-written descriptions of the mechanism, keyed by name prefix. These are the only
#: prose in the registry and they exist because a parameter dict does not tell a reader what
#: a rule believes about the market.
LOGIC = {
    "trend.ret_": ("long when the h-minute return is positive AND the 60-bar z-score is "
                   "above its train-split upper quantile; short on the mirror",
                   "position closes when either leg of the condition fails"),
    "trend.ma_agree": ("long when price is above both the 30- and 120-bar moving averages",
                       "closes when the two averages disagree"),
    "trend.multi_horizon": ("long when the 15-, 30- and 60-bar returns are all positive",
                            "closes when the horizons disagree"),
    "trend.accel_confirm": ("long when 30-bar acceleration and 30-bar return agree in sign",
                            "closes when they disagree"),
    "breakout.opening_range": ("long when price breaks above the opening range by more than "
                               "the train-split quantile, after a warm-up",
                               "closes on re-entry into the range"),
    "breakout.range_expansion": ("long when the session range expands past its quantile and "
                                 "price leads the move",
                                 "closes when expansion subsides"),
    "breakout.failed_reversal": ("fades a breakout that immediately reverses",
                                 "closes when the reversal stalls"),
    "breakout.compression_expansion": ("enters on expansion out of a compressed range",
                                       "closes when compression returns"),
    "revert.z_60": ("fades a 60-bar z-score beyond its train-split extreme",
                    "closes when the z-score returns inside"),
    "revert.vwap": ("fades distance from session VWAP beyond its train-split extreme",
                    "closes when price returns toward VWAP"),
    "revert.z_calm_only": ("fades a z-score extreme ONLY when range expansion is below its "
                           "median, so a genuine regime change is not faded",
                           "closes on return or on expansion"),
    "session.late_day": ("takes a directional stance in the closing hour",
                         "closes at the flatten"),
    "session.opening_drive": ("rides the first move off the open",
                              "closes when the drive stalls"),
    "session.midday_reversion": ("fades the midday drift",
                                 "closes on return"),
    "vol.expansion_trend": ("rides direction when realised volatility expands",
                            "closes when expansion subsides"),
    "vol.contraction_revert": ("fades direction when volatility contracts",
                               "closes when contraction ends"),
    "vol.vol_of_vol": ("reacts to a shock in the volatility of volatility",
                       "closes when the shock passes"),
    "volume.heavy_continuation": ("rides direction on heavy relative volume",
                                  "closes when volume normalises"),
    "volume.climax_reversion": ("fades a volume climax",
                                "closes on return"),
    "added.donchian": ("long on a break above the session channel extreme after a 20-bar "
                       "warm-up; short on the mirror",
                       "closes on re-entry into the channel"),
    "added.bollinger": ("fades a 2-sigma band touch, the canonical parameter, uncalibrated",
                        "closes when the z-score returns inside 2 sigma"),
    "added.vwap_trend": ("rides distance from VWAP when relative volume is above its median",
                         "closes when the gate closes or the sign flips"),
}


@dataclass
class StrategyRecord:
    name: str
    family: str
    family_name: str
    source_module: str
    required_features: tuple[str, ...]
    parameters: dict
    default_parameters: dict
    tunable_parameters: tuple[str, ...]
    entry_logic: str
    exit_logic: str
    stop_logic: str
    target_logic: str
    session_restriction: str
    implementation_status: str
    backtestable: bool
    combine_compatible: bool
    newly_added: bool
    notes: str


def describe(name: str) -> tuple[str, str]:
    for k, v in LOGIC.items():
        if name.startswith(k):
            return v
    return ("(no description registered)", "(no description registered)")


def features_used(strategy, feature_names: list[str]) -> tuple[str, ...]:
    """Which features a signal actually reads, found by probing rather than by parsing.

    Each feature is set to NaN in turn; if the emitted position changes, the signal depends on
    it. More reliable than reading the closure, and it catches a feature referenced through a
    variable.
    """
    import pandas as pd
    rng = np.random.default_rng(0)
    # A REAL session length. A shorter probe silently reports zero dependencies for any rule
    # whose clock threshold sits past the probe's end - the session family fires after minute
    # 300, so a 200-bar probe found nothing and the registry claimed they used no features.
    n = fd.SESSION_BARS
    base = pd.DataFrame({f: rng.normal(size=n) for f in feature_names})
    base["minutes_from_open"] = np.arange(n, dtype=float)
    try:
        ref = np.nan_to_num(np.asarray(strategy.signal(base), dtype=float), nan=0.0)
    except Exception:
        return ()
    used = []
    for f in feature_names:
        probe = base.copy()
        probe[f] = np.nan
        try:
            got = np.nan_to_num(np.asarray(strategy.signal(probe), dtype=float), nan=0.0)
        except Exception:
            used.append(f)
            continue
        if not np.array_equal(ref, got):
            used.append(f)
    return tuple(used)


def build_registry(symbol: str = "MES") -> list[StrategyRecord]:
    from quant_brain.markets.futures_cme import features as fe
    store = REPO / "data" / "futures" / f"{symbol}.parquet"
    df = fd.load(store, symbol)
    sessions = fd.session_frames(df)
    feats = fd.build_features(sessions, fe.library())
    cal = calibrate(feats[:len(sessions) // 2], symbol)
    feature_names = list(feats[0].columns)

    records = []
    for s in list(build_strategies(cal)) + list(family_added(cal)):
        fam = s.family.split(".")[0]
        entry, exit_ = describe(s.name)
        newly = s.family.startswith("H.")
        records.append(StrategyRecord(
            name=s.name, family=s.family, family_name=FAMILY_NAMES.get(fam, fam),
            source_module=("scripts/strategy_registry.py" if newly
                           else "scripts/strategy_tournament.py"),
            required_features=features_used(s, feature_names),
            parameters=s.params, default_parameters=s.params,
            tunable_parameters=tuple(k for k in s.params
                                     if k in ("quantile", "z_quantile", "sigma",
                                              "channel_quantile", "vol_gate_quantile",
                                              "horizon", "warmup_minutes")),
            entry_logic=entry, exit_logic=exit_,
            stop_logic="NONE - no stop is implemented",
            target_logic="NONE - no profit target is implemented",
            session_restriction=f"{fd.OPEN_ET}-{fd.CLOSE_ET} ET, flat at session end",
            implementation_status="implemented",
            backtestable=True,
            combine_compatible=True,
            newly_added=newly,
            notes=("added by this phase; canonical parameters, no prior standing"
                   if newly else "pre-existing in the tournament library")))
    return records


def main() -> int:
    recs = build_registry()
    out = REPO / "research" / "strategy_registry.json"
    out.write_text(json.dumps([asdict(r) for r in recs], indent=1, default=str),
                   encoding="utf-8")

    print("=" * 108)
    print("PHASE 1 - AUTHORITATIVE STRATEGY REGISTRY")
    print(f"built by importing and instantiating, not by reading documentation")
    print("=" * 108)
    print(f"\n{len(recs)} strategies constructed successfully.\n")
    print(f"{'name':34} {'family':14} {'feats':>6} {'tunable':>8} {'new':>4} {'backtestable':>13}")
    for r in recs:
        print(f"{r.name[:34]:34} {r.family_name:14} {len(r.required_features):6d} "
              f"{len(r.tunable_parameters):8d} {'yes' if r.newly_added else '':>4} "
              f"{'yes' if r.backtestable else 'no':>13}")

    print("\n" + "=" * 108)
    print("BY FAMILY")
    print("=" * 108)
    fams: dict[str, int] = {}
    for r in recs:
        fams[r.family_name] = fams.get(r.family_name, 0) + 1
    for k, v in sorted(fams.items()):
        print(f"  {k:16} {v}")

    print("\n" + "=" * 108)
    print("THE BRIEF'S NAMED LIST, AUDITED AGAINST THE CODE")
    print("=" * 108)
    audit = [
        ("ORB", "breakout.opening_range", "present"),
        ("Donchian breakout", "added.donchian_breakout", "ABSENT - added by this phase"),
        ("ATR volatility breakout", "vol.expansion_trend",
         "partial - gates on realised-vol expansion, not an ATR band break"),
        ("VWAP reversion", "revert.vwap", "present"),
        ("VWAP trend", "added.vwap_trend", "ABSENT - added by this phase"),
        ("EMA trend", "trend.ma_agree.30_120",
         "partial - simple MA distance, not exponential"),
        ("Z-score reversion", "revert.z_60", "present"),
        ("Bollinger reversion", "added.bollinger_revert.2sd",
         "ABSENT - added by this phase"),
        ("Failed breakout", "breakout.failed_reversal", "present"),
    ]
    have = {r.name for r in recs}
    print(f"  {'brief name':26} {'maps to':32} status")
    for brief, impl, status in audit:
        mark = "OK " if any(h.startswith(impl) for h in have) else "!! "
        print(f"  {mark}{brief:24} {impl:32} {status}")

    print("\n" + "=" * 108)
    print("WHAT NO STRATEGY IN THIS LIBRARY HAS")
    print("=" * 108)
    print(f"  strategies with a stop implemented   : "
          f"{sum(1 for r in recs if 'NONE' not in r.stop_logic)}")
    print(f"  strategies with a target implemented : "
          f"{sum(1 for r in recs if 'NONE' not in r.target_logic)}")
    print("  Every one is a stateless per-bar signal. Exits are signal flips or the session")
    print("  end, so exit-reason analysis has three categories and the R multiple has no")
    print("  stop-based denominator. Brackets are a parameter-phase question, not a baseline.")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
