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
S_DATA = "tests/test_canonical_data.py"

DSCH = "quant_brain/data/schema.py"
DMAN = "quant_brain/data/manifest.py"
DROL = "quant_brain/data/rolls.py"
DQUA = "quant_brain/data/quality.py"
DADP = "quant_brain/data/adapters.py"
DCON = "quant_brain/data/contracts.py"

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

    # ======================================================================================
    # THE CANONICAL DATA LAYER
    # ======================================================================================
    # Every one of these is a way to get a dataset into research that should not be there.
    # None is visible to the engine or the twin suites: the arithmetic downstream stays
    # perfectly correct while operating on a series that is not what it claims to be.

    # ---- the representation must be declared, and the declaration must bind -------------
    ("data__adjusted_prices_accepted_as_an_execution_source", DSCH,
     "        return self in (DataForm.RAW, DataForm.CONTINUOUS_UNADJUSTED)",
     "        return True", S_DATA),

    ("data__data_form_defaults_instead_of_being_required", DMAN,
     "        if not isinstance(self.data_form, DataForm):",
     "        if False:", S_DATA),

    ("data__form_and_adjustment_allowed_to_contradict", DMAN,
     "        if self.data_form.is_adjusted and self.roll.adjustment "
     "is AdjustmentMethod.NONE:",
     "        if False:", S_DATA),

    ("data__a_continuous_series_may_claim_it_has_no_roll", DMAN,
     "        if self.data_form.is_continuous and self.roll.method is RollMethod.NONE:",
     "        if False:", S_DATA),

    ("data__non_reconstructible_no_longer_has_to_say_why", DMAN,
     "        if not self.reconstructible and not self.non_reconstructible_reason:",
     "        if False:", S_DATA),

    ("data__manifest_id_ignores_the_adjustment_method", DMAN,
     '                     "adjustment": self.roll.adjustment.value,',
     '                     "adjustment": "",', S_DATA),

    ("data__manifest_id_ignores_the_roll_parameter", DMAN,
     '                     "days_before_expiry": self.roll.days_before_expiry,',
     '                     "days_before_expiry": None,', S_DATA),

    # ---- the schema must refuse an ambiguous frame ---------------------------------------
    ("data__naive_timestamps_accepted", DSCH,
     '    if getattr(ts.dtype, "tz", None) is None:',
     "    if False:", S_DATA),

    ("data__a_frame_stored_in_a_venue_clock_accepted", DSCH,
     '    if str(ts.dtype.tz) != "UTC":',
     "    if False:", S_DATA),

    ("data__the_timezone_declaration_need_not_match_the_dtype", DSCH,
     '    if declared != {"UTC"}:',
     "    if False:", S_DATA),

    ("data__two_instruments_allowed_in_one_frame", DSCH,
     "        if n > 1:",
     "        if False:", S_DATA),

    ("data__fingerprint_ignores_the_prices", DSCH,
     "        if col not in df.columns:\n            continue",
     "        if col not in df.columns or col in PRICE_COLUMNS:\n            continue",
     S_DATA),

    # ---- rolls and adjustment ------------------------------------------------------------
    ("data__double_adjustment_permitted", DROL,
     "    if source_form is not DataForm.CONTINUOUS_UNADJUSTED:",
     "    if False:", S_DATA),

    ("data__back_adjustment_anchors_on_the_wrong_end", DROL,
     "            for k in range(len(spans) - 2, -1, -1):",
     "            for k in range(0, len(spans) - 1):", S_DATA),

    ("data__ratio_adjustment_applied_as_a_difference", DROL,
     "        if method is AdjustmentMethod.DIFFERENCE:\n            out[lo:hi] += f",
     "        if True:\n            out[lo:hi] += f", S_DATA),

    ("data__quotes_left_unadjusted_so_the_spread_grows_with_the_offset", DROL,
     'ADJUSTABLE_COLUMNS: tuple[str, ...] = (*PRICE_COLUMNS, "bid", "ask")',
     "ADJUSTABLE_COLUMNS: tuple[str, ...] = PRICE_COLUMNS", S_DATA),

    ("data__interleaved_contracts_adjusted_anyway", DROL,
     '    if not spans_df.empty and (spans_df["appears_n_times"] > 1).any():',
     "    if False:", S_DATA),

    ("data__roll_gap_measured_close_to_close_instead_of_to_the_new_open", DROL,
     "            gap_points=first_o - last_c,",
     "            gap_points=0.0,", S_DATA),

    # ---- the quality gate ------------------------------------------------------------------
    ("data__impossible_ohlc_no_longer_fails", DQUA,
     "    if bad_hl:",
     "    if False:", S_DATA),

    ("data__duplicate_bars_downgraded_to_a_warning", DQUA,
     "    if dup_exact:\n        rep.add(\"duplicates\", Level.FAIL,",
     "    if dup_exact:\n        rep.add(\"duplicates\", Level.WARN,", S_DATA),

    ("data__out_of_order_bars_no_longer_fail", DQUA,
     "    if unsorted:",
     "    if False:", S_DATA),

    ("data__a_zero_price_no_longer_fails", DQUA,
     "    if nonpos:",
     "    if False:", S_DATA),

    ("data__contract_interleaving_no_longer_fails", DQUA,
     "    if revisits > 0:",
     "    if False:", S_DATA),

    ("data__a_warning_no_longer_has_to_justify_itself", DQUA,
     "        if level is Level.WARN and not why_allowed:",
     "        if False:", S_DATA),

    ("data__a_fail_no_longer_blocks_entry_to_research", DQUA,
     "    if rep.failed:\n        lines = ",
     "    if False:\n        lines = ", S_DATA),

    ("data__every_gap_treated_as_a_scheduled_break", DQUA,
     "            if n_seen >= recurring_gap_min_count:",
     "            if True:", S_DATA),

    # ---- the adapters ------------------------------------------------------------------------
    ("data__the_ibkr_adapter_no_longer_needs_a_contract_column", DADP,
     '    expected = {"t", "o", "h", "l", "c", "v", "contract"}',
     '    expected = {"t", "o", "h", "l", "c", "v"}', S_DATA),

    ("data__the_adapter_trusts_the_caller_over_the_contracts", DADP,
     "    if family != instrument:",
     "    if False:", S_DATA),

    ("data__the_generic_adapter_guesses_a_missing_column_mapping", DADP,
     "    if unmapped:",
     "    if False:", S_DATA),

    ("data__the_generic_adapter_accepts_an_undeclared_data_form", DADP,
     "    if not isinstance(data_form, DataForm):",
     "    if False:", S_DATA),

    # ---- contract identity ---------------------------------------------------------------------
    ("data__an_unparseable_contract_symbol_is_waved_through", DCON,
     "    raise ContractSymbolError(\n        f\"{symbol!r} is not a futures contract",
     "    return ContractCode(year=1970, month=1, root=s, symbol=symbol)\n    raise "
     "ContractSymbolError(\n        f\"{symbol!r} is not a futures contract", S_DATA),

    ("data__the_year_window_moves_with_the_wall_clock", DCON,
     "YEAR_ANCHOR = 2026",
     "import datetime as _dt2\nYEAR_ANCHOR = _dt2.date.today().year + 7", S_DATA),

    ("data__chain_order_falls_back_to_string_sort", DCON,
     "    return sorted(parsed)",
     "    return sorted(parsed, key=lambda c: c.symbol)", S_DATA),
]
