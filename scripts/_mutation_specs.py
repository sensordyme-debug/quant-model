"""The mutation catalogue, kept separate so the harness stays readable.

Each entry is a defect that could plausibly reach production in a backtester. Several of them
HAVE reached production in this repository and are described in its own module docstrings -
the dropped flatten leg, for instance, once caused 76% of scored hypotheses to record zero
trades and zero cost.

A mutation is expressed as an exact source substring and its replacement, applied to one file
at a time and reverted immediately. Keeping them as data rather than as patches means the
catalogue can be read and audited without running anything.
"""
from __future__ import annotations

FD = "scripts/futures_discover.py"
EX = "quant_brain/research/exits.py"
SL = "quant_brain/research/strategy_lab.py"
IN = "quant_brain/markets/futures_cme/instruments.py"
CL = "quant_brain/research/canonical_ledger.py"
AR = "quant_brain/research/account_result.py"
EM = "quant_brain/research/execution_modes.py"
LB = "quant_brain/research/ledger_builder.py"
TW = "quant_brain/markets/futures_cme/twin.py"

#: The suites, repeated here so a mutation can name the one that defends it. Running
#: the wrong suite scores a hole as a catch.
S_PIPE = "tests/test_canonical_pipeline.py"
S_TWIN = "tests/test_topstep_twin_forensics.py"

#: (name, file, find, replace) and optionally the suite that must catch it. Entries
#: without a suite are defended by `tests/test_engine_forensics.py`.
MUTATIONS: list[tuple] = [
    # ---- P&L core -----------------------------------------------------------------------
    ("lag_removed__position_earns_its_own_bar", FD,
     "    gross_path = np.cumsum(pos[:-1] * step[1:])",
     "    gross_path = np.cumsum(pos[1:] * step[1:])"),

    ("short_pnl_sign_flipped", FD,
     "    gross_path = np.cumsum(pos[:-1] * step[1:])",
     "    gross_path = np.cumsum(np.abs(pos[:-1]) * step[1:])"),

    ("price_diff_reversed", FD,
     "    step = np.diff(close, prepend=close[0]) * multiplier * contracts",
     "    step = -np.diff(close, prepend=close[0]) * multiplier * contracts"),

    # ---- cost ---------------------------------------------------------------------------
    ("flatten_leg_dropped__the_original_2026_defect", FD,
     "    legs = np.abs(np.diff(pos, prepend=0.0, append=0.0))",
     "    legs = np.abs(np.diff(pos, prepend=0.0))"),

    ("cost_halved", FD,
     "    paid = np.cumsum(legs) * (round_turn_cost / 2.0)",
     "    paid = np.cumsum(legs) * (round_turn_cost / 4.0)"),

    ("cost_removed_entirely", FD,
     "    paid = np.cumsum(legs) * (round_turn_cost / 2.0)",
     "    paid = np.cumsum(legs) * 0.0"),

    ("cost_charged_only_at_the_close_not_per_leg", FD,
     "    incurred = paid[1:n].copy()",
     "    incurred = np.zeros(n - 1); incurred[-1] = paid[-1]; incurred = incurred.copy()"),

    # ---- fills --------------------------------------------------------------------------
    ("ambiguous_bar_resolved_optimistically_as_target", EX,
     "        if hit_stop:\n            px = float(stop_px)",
     "        if hit_stop and not hit_target:\n            px = float(stop_px)"),

    ("target_fills_at_bar_close_not_target_price", EX,
     "        if hit_target:\n            return _result(entry_bar, i, direction, entry, "
     "float(target_px), TARGET,",
     "        if hit_target:\n            return _result(entry_bar, i, direction, entry, "
     "float(max(cl, target_px)), TARGET,"),

    ("stop_fill_improved_to_the_bar_close", EX,
     "            return _result(entry_bar, i, direction, entry, px, TRAIL if",
     "            px = max(px, cl) if direction > 0 else min(px, cl)\n"
     "            return _result(entry_bar, i, direction, entry, px, TRAIL if"),

    ("stop_trigger_uses_close_instead_of_low", EX,
     "        hit_stop = stop_px is not None and (lo <= stop_px if direction > 0\n"
     "                                            else hi >= stop_px)",
     "        hit_stop = stop_px is not None and (cl <= stop_px if direction > 0\n"
     "                                            else cl >= stop_px)"),

    ("target_trigger_uses_close_instead_of_high", EX,
     "        hit_target = target_px is not None and (hi >= target_px if direction > 0\n"
     "                                                else lo <= target_px)",
     "        hit_target = target_px is not None and (cl >= target_px if direction > 0\n"
     "                                                else cl <= target_px)"),

    # ---- trade ledger --------------------------------------------------------------------
    ("trade_extractor_drops_the_round_turn_cost", SL,
     "        net = gross - rt",
     "        net = gross"),

    ("trade_extractor_equity_ignores_cost", SL,
     "        equity[t.exit_bar:] -= rt",
     "        equity[t.exit_bar:] -= 0.0"),

    ("mae_recorded_as_zero", SL,
     "            mae=float(trough - open_equity), mfe=float(peak - open_equity),",
     "            mae=0.0, mfe=float(peak - open_equity),"),

    # ---- contract metadata -----------------------------------------------------------------
    ("micro_multiplier_wrong_by_10x", IN,
     '"MNQ": _fut("MNQ",  2.0,',
     '"MNQ": _fut("MNQ",  20.0,'),

    ("micro_tick_size_doubled", IN,
     '"MNQ": _fut("MNQ",  2.0,  0.25,',
     '"MNQ": _fut("MNQ",  2.0,  0.50,'),

    ("mnq_commission_silently_zeroed", IN,
     'parent="NQ",  rt=1.22',
     'parent="NQ",  rt=0.0'),

    # ======================================================================================
    # THE INTEGRATION LAYER
    # ======================================================================================
    # The P&L forensics suite cannot see any of these: the ledger can be wrong about the
    # intraday path, the account layer can be wrong about what the path means, and the
    # profit figure stays correct throughout. That is exactly why the integration needs its
    # own mutations rather than inheriting the engine's score.

    # ---- the canonical ledger --------------------------------------------------------
    ("ledger__forced_flatten_matched_against_the_wrong_constant", CL,
     "        return self.exit_reason == X.FLATTEN",
     '        return self.exit_reason == "flatten"', S_PIPE),

    ("ledger__long_marked_at_the_high_instead_of_the_low", CL,
     "    return low if direction > 0 else high",
     "    return high if direction > 0 else low", S_PIPE),

    ("ledger__close_only_silently_adds_the_adverse_marks", CL,
     "            if mode is not ExecutionPathMode.CLOSE_ONLY:\n"
     "                adverse = (_adverse_price(d, highs[i], lows[i]) - entry) * d * scale\n"
     "                marks.append(running + adverse)",
     "            if True:\n"
     "                adverse = (_adverse_price(d, highs[i], lows[i]) - entry) * d * scale\n"
     "                marks.append(running + adverse)", S_PIPE),

    ("ledger__stress_collapses_into_intrabar_conservative", CL,
     "            if mode is ExecutionPathMode.STRESS:",
     "            if False:", S_PIPE),

    ("ledger__whole_round_turn_charged_at_the_entry", CL,
     "        running -= half_cost                      # the entry leg pays here",
     "        running -= half_cost * 2.0                # the entry leg pays here", S_PIPE),

    ("ledger__snap_tolerance_wide_enough_to_hide_a_real_gap", CL,
     "_MARK_SNAP_TOLERANCE = 1e-6",
     "_MARK_SNAP_TOLERANCE = 1e9", S_PIPE),

    ("ledger__twin_gets_a_rebuilt_path_instead_of_the_ledgers_own", CL,
     "        return [TwinDay(day=s.day, pnl=s.realized_net, path=s.marks, "
     "traded=s.traded)\n                for s in self.sessions]",
     "        return [TwinDay(day=s.day, pnl=s.realized_net, path=tuple(float(m) for m in s.marks), "
     "traded=s.traded)\n                for s in self.sessions]", S_PIPE),

    ("ledger__exit_leg_cost_never_charged", CL,
     "        running += exit_value - half_cost         # the exit leg pays here",
     "        running += exit_value                     # the exit leg pays here", S_PIPE),

    # ---- the account layer ------------------------------------------------------------
    ("account__constrained_pnl_ignores_the_liquidation_floor", AR,
     "            under_constraints += d.mll - d.opening_balance",
     "            under_constraints += d.settled_pnl", S_PIPE),

    ("account__contract_ceiling_read_from_the_scaling_ladder", AR,
     "    profile = ts.combine(size)",
     "    profile = ts.express_funded(size)", S_PIPE),

    ("account__cross_check_compares_nothing", AR,
     "    out = ReferenceCrossCheck(fields_compared=len(checks))",
     "    checks = []\n    out = ReferenceCrossCheck(fields_compared=len(checks))", S_PIPE),

    ("account__intraday_buffer_reports_the_close_buffer", AR,
     "        min_mll_buffer_intraday=float(min((d.worst_buffer_mll for d in result.trace),",
     "        min_mll_buffer_intraday=float(min((d.buffer_mll for d in result.trace),",
     S_PIPE),

    ("account__probabilities_drop_the_daily_loss_limit", AR,
     "    p_survive, p_target, p_payout, note = _probabilities(\n"
     "        days, twin_obj, reps=reps, block=block, seed=seed)",
     "    p_survive, p_target, p_payout, note = _probabilities(\n"
     "        days, tw.TopstepTwin(account_size, payout_policy=policy), reps=reps,\n"
     "        block=block, seed=seed)", S_PIPE),

    # ---- the execution ladder ----------------------------------------------------------
    ("modes__the_headline_becomes_the_frictionless_one", EM,
     'HEADLINE = "CONSERVATIVE"',
     'HEADLINE = "IDEAL"', S_PIPE),

    ("modes__conservative_quietly_uses_the_close_only_path", EM,
     "    path_mode=ExecutionPathMode.INTRABAR_CONSERVATIVE,\n"
     "    stop_execution=_STOP, target_execution=_TARGET, flatten_execution=_FLAT,\n"
     "    partial_fills=_NO_PARTIAL, ambiguous_bar=_AMBIG,\n"
     '    intent=("A full tick of round-turn slippage',
     "    path_mode=ExecutionPathMode.CLOSE_ONLY,\n"
     "    stop_execution=_STOP, target_execution=_TARGET, flatten_execution=_FLAT,\n"
     "    partial_fills=_NO_PARTIAL, ambiguous_bar=_AMBIG,\n"
     '    intent=("A full tick of round-turn slippage', S_PIPE),

    ("modes__the_spread_stops_being_charged_anywhere", EM,
     "    name=\"CONSERVATIVE\", slippage_ticks=1.0, include_spread=True,",
     "    name=\"CONSERVATIVE\", slippage_ticks=1.0, include_spread=False,", S_PIPE),

    # ---- the builder --------------------------------------------------------------------
    ("builder__overlapping_positions_allowed", LB,
     "                busy_until = r.exit_bar",
     "                busy_until = i", S_PIPE),

    ("builder__spread_override_ignored_so_every_mode_costs_the_same", LB,
     "    charge_spread = spec.cost.include_spread if include_spread is None "
     "else include_spread",
     "    charge_spread = spec.cost.include_spread", S_PIPE),

    # ---- the twin trace ------------------------------------------------------------------
    ("twin__worst_equity_never_updated_so_the_buffer_looks_safe", TW,
     "            worst_equity = min(worst_equity, account.equity)",
     "            worst_equity = worst_equity", S_PIPE),

    ("twin__the_daily_limit_level_read_after_the_day_instead_of_before", TW,
     "        dll_level = (account.balance - dll) if dll is not None else -math.inf",
     "        dll_level = -math.inf", S_TWIN),
]
