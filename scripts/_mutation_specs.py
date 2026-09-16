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
S_CERT = "tests/test_certification.py"
S_CONTRACT = "tests/test_strategy_contract.py"
S_VWAP_IND = "tests/test_vwap_indicators.py"
S_VWAP_STR = "tests/test_vwap_strategy.py"
S_VWAP_GOV = "tests/test_vwap_governor.py"

DSCH = "quant_brain/data/schema.py"
DMAN = "quant_brain/data/manifest.py"
DROL = "quant_brain/data/rolls.py"
DQUA = "quant_brain/data/quality.py"
DADP = "quant_brain/data/adapters.py"
DCON = "quant_brain/data/contracts.py"
SR = "quant_brain/research/strategy_report.py"
VS = "quant_brain/strategies/vwap_pullback/spec.py"
VI = "quant_brain/strategies/vwap_pullback/indicators.py"
VE = "quant_brain/strategies/vwap_pullback/engine.py"
VO = "quant_brain/strategies/vwap_pullback/orders.py"
VG = "quant_brain/strategies/vwap_pullback/governor.py"

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
    # The anchor moved when the reversal defect was fixed (`busy_until` -> `next_entry_at`),
    # and a stale anchor SKIPS rather than fails - which would have quietly retired the one
    # mutation defending "never two positions at once". Re-pointed, and the certification
    # suite defends it alongside the pipeline suite.
    ("builder__overlapping_positions_allowed", LB,
     "                next_entry_at = r.exit_bar + cooldown",
     "                next_entry_at = r.entry_bar + cooldown", S_PIPE),

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

    # ---- CERTIFICATION: the defects the pre-strategy audit actually found ----------------
    # Each of these was a live defect. They are mutations now so they cannot come back.

    ("cert__reversal_loses_its_second_leg__THE_P0", LB,
     "            if (p != 0 and p != prev and i >= next_entry_at and i <= last_entry",
     "            if (p != 0 and p != prev and i > next_entry_at and i <= last_entry",
     S_CERT),

    ("cert__cooldown_ignored_so_re_entry_is_immediate", LB,
     "                next_entry_at = r.exit_bar + cooldown",
     "                next_entry_at = r.exit_bar",
     S_CONTRACT),

    # Defended in the certification suite, not the contract suite: naming the wrong suite
    # scores a hole as a catch, which is the one way this harness can lie to itself.
    ("cert__warmup_off_by_one_admits_an_early_entry", LB,
     "        next_entry_at = spec.session.warmup_bars",
     "        next_entry_at = max(0, spec.session.warmup_bars - 1)",
     S_CERT),

    ("cert__per_session_trade_cap_ignored", LB,
     "                    and (cap is None or taken < cap)):",
     "                    and True):",
     S_CONTRACT),

    ("cert__forced_flat_bar_ignored", LB,
     "        flat_bar = bar_at(g, spec.session.flat_by_et, default=n - 1)",
     "        flat_bar = n - 1",
     S_CONTRACT),

    ("cert__monte_carlo_uses_a_kinder_payout_policy_than_the_account", SR,
     "                                  fraction=account.payout.policy_fraction,",
     "                                  fraction=0.0,",
     S_CERT),

    ("cert__lookahead_canary_disarmed", SR,
     "        lookahead_suspected=bool(ceiling and share > LOOKAHEAD_CEILING_SHARE),",
     "        lookahead_suspected=False,",
     S_CERT),

    ("cert__lookahead_canary_threshold_loosened_to_admit_an_oracle", SR,
     "LOOKAHEAD_CEILING_SHARE = 0.20",
     "LOOKAHEAD_CEILING_SHARE = 0.99",
     S_CERT),

    ("cert__a_suspected_lookahead_is_graded_instead_of_refused", SR,
     "    if integrity.lookahead_suspected:",
     "    if False:",
     S_CERT),

    ("cert__strategy_equity_printed_from_the_account_balance", SR,
     "    strategy_pnl = a.returns.net_pnl",
     "    strategy_pnl = a.final_equity",
     S_CERT),

    ("cert__oracle_ceiling_computed_on_the_wrong_scale", SR,
     "        ceiling += float(np.abs(np.diff(c)).sum()) * mult * ct",
     "        ceiling += float(np.abs(np.diff(c)).sum()) * mult * ct * 1000.0",
     S_CERT),

    ("cert__monthly_rows_drop_the_last_month", SR,
     "    for p in sorted(set(idx)):",
     "    for p in sorted(set(idx))[:-1]:",
     S_CERT),

    ("cert__monthly_win_rate_counts_losers_as_wins", SR,
     '        wins = int((sub["net_pnl"] > 0).sum()) if len(sub) else 0',
     '        wins = int((sub["net_pnl"] != 0).sum()) if len(sub) else 0',
     S_CERT),

    ("cert__monthly_pnl_uses_gross_instead_of_net", SR,
     "        net = float(vals.sum())",
     "        net = float(vals.sum()) * 1.05",
     S_CERT),

    ("cert__profit_factor_inverted", SR,
     "        profit_factor=(gp / gl) if gl > 0 else None,",
     "        profit_factor=(gl / gp) if gp > 0 else None,",
     S_CERT),

    ("cert__max_drawdown_reported_as_the_average", SR,
     "        max_drawdown=abs(account.max_drawdown),",
     "        max_drawdown=abs(account.max_drawdown) / 2.0,",
     S_CERT),

    ("cert__consecutive_losses_never_reset_so_a_run_becomes_a_total", SR,
     "        run = run + 1 if f else 0",
     "        run = run + 1 if f else run",
     S_CERT),

    ("cert__regime_volatility_read_from_equity_instead_of_price", SR,
     "    rng = {g[\"day\"].iloc[0]: session_atr(g) for g in sset.frames}",
     "    rng = {g[\"day\"].iloc[0]: 1.0 for g in sset.frames}",
     S_CERT),

    ("cert__robust_positive_reachable_on_a_short_sample", SR,
     "MIN_MONTHS_FOR_ROBUST = 24",
     "MIN_MONTHS_FOR_ROBUST = 1",
     S_CERT),

    ("cert__monte_carlo_resamples_a_shorter_path_than_the_sample", SR,
     "    sample = pa.moving_block(days, block=block, reps=paths, seed=seed)",
     "    sample = pa.moving_block(days[:len(days)//2], block=block, reps=paths, seed=seed)",
     S_CERT),

    ("cert__mae_basis_no_longer_declared", SR,
     "        mae_basis=MAE_BASIS,",
     '        mae_basis="",',
     S_CERT),

    ("cert__entry_fill_sensitivity_always_reports_zero", SR,
     "        sens = delta if ok else None",
     "        sens = 0.0",
     S_CERT),

    # ---- V1.0.0_FROZEN: the VWAP pullback strategy ---------------------------------------
    # The brief names each of these as a mutation the golden suite must kill.

    # -- the frozen constants ---------------------------------------------------------------
    ("vwap__stop_distance_shaved_by_a_cent", VS,
     "    stop_points: float = 15.0", "    stop_points: float = 14.99", S_VWAP_GOV),
    ("vwap__target_distance_shaved_by_a_cent", VS,
     "    target_points: float = 30.0", "    target_points: float = 29.99", S_VWAP_GOV),
    ("vwap__break_even_trigger_shaved_by_a_cent", VS,
     "    breakeven_trigger: float = 15.0", "    breakeven_trigger: float = 14.99",
     S_VWAP_GOV),
    ("vwap__stall_mfe_shaved_by_a_cent", VS,
     "    stall_mfe: float = 25.0", "    stall_mfe: float = 24.99", S_VWAP_GOV),
    ("vwap__stall_window_shortened_to_two_bars", VS,
     "    stall_window: int = 3", "    stall_window: int = 2", S_VWAP_GOV),
    ("vwap__killswitch_moved_to_minus_801", VS,
     "    daily_loss_killswitch: float = -800.0",
     "    daily_loss_killswitch: float = -801.0", S_VWAP_GOV),
    ("vwap__profit_cap_moved_to_1201", VS,
     "    daily_profit_cap: float = 1200.0", "    daily_profit_cap: float = 1201.0",
     S_VWAP_GOV),
    ("vwap__trade_cap_raised_to_five", VS,
     "    max_trades_per_day: int = 4", "    max_trades_per_day: int = 5", S_VWAP_GOV),
    ("vwap__loss_breaker_raised_to_three", VS,
     "    consecutive_losses_for_cooldown: int = 2",
     "    consecutive_losses_for_cooldown: int = 3", S_VWAP_GOV),
    ("vwap__cooldown_shortened_to_44_minutes", VS,
     "    cooldown_minutes: int = 45", "    cooldown_minutes: int = 44", S_VWAP_GOV),
    ("vwap__last_entry_cutoff_moved", VS,
     "    last_entry: tuple[int, int] = (15, 30)",
     "    last_entry: tuple[int, int] = (15, 31)", S_VWAP_GOV),
    ("vwap__hard_flatten_moved", VS,
     "    hard_flatten: tuple[int, int] = (15, 45)",
     "    hard_flatten: tuple[int, int] = (15, 46)", S_VWAP_GOV),
    ("vwap__session_anchor_moved_off_eighteen_hundred", VS,
     "    session_anchor: tuple[int, int] = (18, 0)",
     "    session_anchor: tuple[int, int] = (17, 0)", S_VWAP_GOV),
    ("vwap__commission_reverted_to_the_repository_rate", VS,
     "    commission_round_turn: float = 4.50",
     "    commission_round_turn: float = 3.78", S_VWAP_GOV),
    ("vwap__entry_slippage_removed_from_the_baseline_profile", VS,
     "    entry_ticks=1.0, stop_ticks=1.0, target_ticks=0.0, market_exit_ticks=0.0,\n"
     "    frozen_spec_exact=True)",
     "    entry_ticks=0.0, stop_ticks=1.0, target_ticks=0.0, market_exit_ticks=0.0,\n"
     "    frozen_spec_exact=True)",
     S_VWAP_GOV),
    ("vwap__nq_point_value_doubled", VS,
     "        return float(inst.get(self.instrument).spec.multiplier) * self.contracts",
     "        return float(inst.get(self.instrument).spec.multiplier) * self.contracts * 2",
     S_VWAP_GOV),

    # -- the clock ---------------------------------------------------------------------------
    ("vwap__wrong_timezone", VS,
     "TIMEZONE: ZoneInfo = ET", 'TIMEZONE: ZoneInfo = ZoneInfo("UTC")', S_VWAP_IND),
    ("vwap__vwap_never_resets_at_the_anchor", VI,
     "        elif day != self._day:", "        elif False:", S_VWAP_IND),

    # -- the indicators ----------------------------------------------------------------------
    ("vwap__typical_price_replaced_by_the_close", VI,
     "        return (self.high + self.low + self.close) / 3.0",
     "        return self.close", S_VWAP_IND),
    ("vwap__welford_variance_uses_the_stale_mean", VI,
     "        self._m2 += w * delta * (tp - self._mean)",
     "        self._m2 += w * delta * delta", S_VWAP_IND),
    ("vwap__volume_sma_excludes_the_current_bar", VI,
     "        return sum(self._window) / len(self._window) if self.ready else float(\"nan\")",
     "        return (sum(self._window[:-1]) / (len(self._window) - 1)) if self.ready "
     "else float(\"nan\")", S_VWAP_IND),
    ("vwap__the_forming_five_minute_bar_becomes_visible", VI,
     "        return self.completed[-1] if self.completed else None",
     "        if self._bucket is not None:\n"
     "            return FiveMinuteBar(start=self._start, end=self._end, open=self._o,\n"
     "                                 high=self._h, low=self._low, close=self._c,\n"
     "                                 volume=self._v, vwap_at_close=self._vwap_at_close)\n"
     "        return self.completed[-1] if self.completed else None", S_VWAP_IND),

    # -- break-even and the stall rule --------------------------------------------------------
    ("vwap__break_even_reads_the_close_instead_of_the_high", VE,
     "        if not p.breakeven_done and p.mfe_points >= self.spec.breakeven_trigger:",
     "        if not p.breakeven_done and (bar.close - p.fill_price) * d >= "
     "self.spec.breakeven_trigger:", S_VWAP_STR),
    ("vwap__stall_decides_at_t_plus_2_instead_of_t_plus_3", VE,
     "        if p.stall_bars_seen < self.spec.stall_window:",
     "        if p.stall_bars_seen < self.spec.stall_window - 1:", S_VWAP_STR),
    ("vwap__stall_ignores_a_break_of_the_mfe_bar", VE,
     "        if p.stall_broken:", "        if False:", S_VWAP_STR),
    ("vwap__mfe_bar_is_re_identified_by_every_later_high", VE,
     "        if p.mfe_bar_index is None:", "        if True:", S_VWAP_STR),

    # -- fill-price anchoring and slippage ----------------------------------------------------
    ("vwap__the_fill_is_the_signal_bar_close_so_the_bracket_anchors_to_it", VE,
     "        fill = bar.close + slip * d                    # adverse, by construction",
     "        fill = bar.close", S_VWAP_STR),
    ("vwap__entry_slippage_is_favourable_instead_of_adverse", VE,
     "        fill = bar.close + slip * d                    # adverse, by construction",
     "        fill = bar.close - slip * d", S_VWAP_STR),
    ("vwap__the_bracket_re_derives_the_signal_close_from_the_fill", VO,
     "        fill = float(entry.fill_price)",
     "        fill = float(entry.fill_price) - 0.25 * (1 if entry.side is Side.BUY else -1)",
     S_VWAP_STR),
    ("vwap__stop_slippage_is_favourable_instead_of_adverse", VE,
     "            self._close(bar, p, price=stop_px - slip * d, reason=EXIT_STOP,",
     "            self._close(bar, p, price=stop_px + slip * d, reason=EXIT_STOP,",
     S_VWAP_GOV),

    # -- the OCO -------------------------------------------------------------------------------
    ("vwap__the_filled_leg_no_longer_cancels_the_other", VO,
     '            self._cancel_leg(other, f"cancelled by the {which} (OCO)")',
     "            pass", S_VWAP_STR),
    ("vwap__break_even_can_be_applied_twice", VO,
     "        if self._once(token) is not None:\n            return self.bracket.stop",
     "        if False:\n            return self.bracket.stop", S_VWAP_STR),
    ("vwap__the_book_no_longer_refuses_a_second_position", VO,
     "        if self.position != 0:\n            raise BracketError(\n"
     '                f"refusing a second entry while {self.position:+d} is open.',
     "        if False:\n            raise BracketError(\n"
     '                f"refusing a second entry while {self.position:+d} is open.',
     S_VWAP_STR),

    # -- intrabar precedence ---------------------------------------------------------------------
    ("vwap__an_ambiguous_bar_resolves_as_the_target_instead_of_the_stop", VE,
     "        if stop_hit:", "        if stop_hit and not target_hit:", S_VWAP_STR),
    ("vwap__the_ambiguity_flag_is_never_set", VE,
     "        ambiguous = bool(stop_hit and target_hit)", "        ambiguous = False",
     S_VWAP_STR),

    # -- the governor ------------------------------------------------------------------------------
    ("vwap__governor_reads_realized_only_and_ignores_the_open_half", VG,
     "        return (self.realized + unrealized) <= self.spec.daily_loss_killswitch",
     "        return self.realized <= self.spec.daily_loss_killswitch", S_VWAP_GOV),
    ("vwap__killswitch_boundary_opened_so_exactly_minus_800_survives", VG,
     "        return (self.realized + unrealized) <= self.spec.daily_loss_killswitch",
     "        return (self.realized + unrealized) < self.spec.daily_loss_killswitch",
     S_VWAP_GOV),
    ("vwap__profit_cap_boundary_opened_so_exactly_1200_still_trades", VG,
     "        if self.realized >= self.spec.daily_profit_cap:",
     "        if self.realized > self.spec.daily_profit_cap:", S_VWAP_GOV),
    ("vwap__cooldown_boundary_closed_so_45_00_is_still_blocked", VG,
     "        if self.cooldown_until is not None and when < self.cooldown_until:",
     "        if self.cooldown_until is not None and when <= self.cooldown_until:",
     S_VWAP_GOV),
    ("vwap__hard_flatten_boundary_opened_so_15_45_still_trades", VG,
     '        return minute_of_day(when) >= self.spec.minute_of("hard_flatten")',
     '        return minute_of_day(when) > self.spec.minute_of("hard_flatten")', S_VWAP_GOV),
    ("vwap__entry_cutoff_reading_flipped", VG,
     "        if (m > cutoff) if self.spec.last_entry_inclusive else (m >= cutoff):",
     "        if (m >= cutoff) if self.spec.last_entry_inclusive else (m > cutoff):",
     S_VWAP_GOV),
    ("vwap__a_scratch_resets_the_consecutive_loss_streak", VG,
     "        elif net_pnl > 0:\n            self.consecutive_losses = 0",
     "        elif net_pnl >= 0:\n            self.consecutive_losses = 0", S_VWAP_GOV),
    ("vwap__the_trade_counter_never_increments", VG,
     "        self.trades_today += 1", "        self.trades_today += 0", S_VWAP_GOV),
    ("vwap__the_day_never_rolls_so_the_halt_is_permanent", VG,
     "        self.reset(day)\n        return True", "        return False", S_VWAP_GOV),

    # ---- DECISIONS 1-4: the execution ladder, the resolved register, the characteristics ---

    # THE P1 THE STRESS PROFILES FOUND. `_close` reconstructs the ideal exit as
    # `price + slippage * d`, so passing an unslipped price with a non-zero slippage cancels
    # the charge out exactly. Invisible under BASELINE (0 ticks); made the stress a no-op.
    ("vwap__market_exit_slippage_accounted_but_never_applied_to_the_price", VE,
     "            self._close(bar, p, price=bar.close - slip * d, reason=EXIT_HARD_FLATTEN,",
     "            self._close(bar, p, price=bar.close, reason=EXIT_HARD_FLATTEN,",
     S_VWAP_GOV),
    ("vwap__governor_flatten_slippage_not_applied_to_the_price", VE,
     "            self._close(bar, p, price=bar.close - slip * d, reason=EXIT_KILLSWITCH,",
     "            self._close(bar, p, price=bar.close, reason=EXIT_KILLSWITCH,",
     S_VWAP_GOV),
    ("vwap__stall_close_slippage_not_applied_to_the_price", VE,
     "            self._close(bar, p, price=bar.close - slip * d, reason=EXIT_STALL,",
     "            self._close(bar, p, price=bar.close, reason=EXIT_STALL,",
     S_VWAP_GOV),
    ("vwap__market_exit_slippage_is_favourable_instead_of_adverse", VE,
     "            self._close(bar, p, price=bar.close - slip * d, reason=EXIT_HARD_FLATTEN,",
     "            self._close(bar, p, price=bar.close + slip * d, reason=EXIT_HARD_FLATTEN,",
     S_VWAP_GOV),

    # the baseline must stay EXACTLY V1.0.0 - no invented market-exit tick
    ("vwap__the_baseline_profile_invents_a_market_exit_tick", VS,
     "    entry_ticks=1.0, stop_ticks=1.0, target_ticks=0.0, market_exit_ticks=0.0,\n"
     "    frozen_spec_exact=True)",
     "    entry_ticks=1.0, stop_ticks=1.0, target_ticks=0.0, market_exit_ticks=1.0,\n"
     "    frozen_spec_exact=True)",
     S_VWAP_GOV),
    ("vwap__the_baseline_profile_charges_the_limit_target", VS,
     "    entry_ticks=1.0, stop_ticks=1.0, target_ticks=0.0, market_exit_ticks=0.0,\n"
     "    frozen_spec_exact=True)",
     "    entry_ticks=1.0, stop_ticks=1.0, target_ticks=1.0, market_exit_ticks=0.0,\n"
     "    frozen_spec_exact=True)",
     S_VWAP_GOV),

    # a stress profile that measures nothing
    ("vwap__stress_1tick_collapses_onto_the_baseline", VS,
     "    entry_ticks=1.0, stop_ticks=2.0, target_ticks=0.0, market_exit_ticks=1.0)",
     "    entry_ticks=1.0, stop_ticks=1.0, target_ticks=0.0, market_exit_ticks=0.0)",
     S_VWAP_GOV),
    ("vwap__stress_2tick_is_no_worse_than_stress_1tick", VS,
     "    entry_ticks=1.0, stop_ticks=3.0, target_ticks=0.0, market_exit_ticks=2.0)",
     "    entry_ticks=1.0, stop_ticks=2.0, target_ticks=0.0, market_exit_ticks=1.0)",
     S_VWAP_GOV),

    # the break-even stop must be charged as a STOP-OUT, not as a market exit
    ("vwap__break_even_stop_charged_as_a_market_exit_rather_than_a_stop", VS,
     "        return self.execution.stop_ticks",
     "        return self.execution.market_exit_ticks",
     S_VWAP_GOV),

    # changing the profile must not change a strategy rule
    ("vwap__the_execution_profile_also_moves_a_strategy_rule", VS,
     "        return dataclasses.replace(self, execution=execution_profile(name))",
     "        return dataclasses.replace(self, execution=execution_profile(name),\n"
     "                                   stop_points=14.0)",
     S_VWAP_GOV),

    # DECISION 4: the proximity inequalities must stay literal
    ("vwap__c9_long_proximity_reinterpreted_with_an_absolute_value", VE,
     "        if five.close > v and (v - five.low) <= self.spec.context_max_distance:",
     "        if five.close > v and abs(v - five.low) <= self.spec.context_max_distance:",
     S_VWAP_STR),
    ("vwap__c10_short_proximity_reinterpreted_with_an_absolute_value", VE,
     "        if five.close < v and (five.high - v) <= self.spec.context_max_distance:",
     "        if five.close < v and abs(five.high - v) <= self.spec.context_max_distance:",
     S_VWAP_STR),
    ("vwap__the_six_point_proximity_limit_stops_binding", VE,
     "        if five.close > v and (v - five.low) <= self.spec.context_max_distance:",
     "        if five.close > v:",
     S_VWAP_STR),

    # DECISION 1: the ATR gate
    ("vwap__atr_gate_boundary_opened_so_exactly_eight_is_refused", VE,
     "        if self.atr.value < self.spec.atr_minimum:",
     "        if self.atr.value <= self.spec.atr_minimum:",
     S_VWAP_GOV),
    ("vwap__atr_gate_removed_entirely", VE,
     "        if self.atr.value < self.spec.atr_minimum:",
     "        if False:",
     S_VWAP_GOV),

    # the register itself: a resolution that records no authority, or a re-opened decision
    ("vwap__a_resolved_ambiguity_loses_its_authority", VS,
     '              authority="owner, V1.0.0_Frozen certification register, '
     "2026-09-16 - DECISION 1\"),",
     '              authority=""),',
     S_VWAP_GOV),
    ("vwap__needs_owner_stops_checking_the_resolution_status", VS,
     "        return self.material and self.status != RESOLVED",
     "        return False",
     S_VWAP_GOV),
]