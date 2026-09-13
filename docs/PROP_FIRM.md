# Prop firm: the generic profile, the Topstep rulebook, and what still needs the owner

Status of this document: describes `quant_brain/markets/futures_cme/{propfirm,topstep,
profiles}.py` at commit `2a7367f` (2026-09-13) against the human-readable rulebook in
`docs/topstep/` (version `2026.09.13`). No account exists; nothing here has been checked
against a live dashboard.

| claim | status | evidence |
|---|---|---|
| ENGINE VALIDATED | yes | `tests/test_qb_propfirm.py`, `tests/test_qb_topstep.py`, `tests/test_qb_twin.py`; the published consistency worked example reproduces (`test_the_published_worked_example_reproduces`) |
| STRATEGY VALIDATED | **no** | no strategy has passed the simulated Combine at a rate above the funnel's 10% floor; nothing reached that gate |
| LIVE EXECUTION VALIDATED | **no** | no Topstep account, no adapter that can send (`BLOCKERS.md` OWNER-4) |
| PROFITABILITY DEMONSTRATED | **no** | |

---

## Two layers, not two rulebooks

`propfirm.py` is firm-agnostic and contains no firm name. `topstep.py` is Topstep, and it
produces `PropFirmProfile`s. The second configures the first; `docs/ARCHITECTURE_AUDIT.md`
calls them layered, not duplicated, and that is the right reading.

### `PropFirmProfile` (generic)

A frozen dataclass of the parameters a rulebook can have:

| group | fields |
|---|---|
| the two limits that end accounts | `daily_loss_limit`, `daily_loss_ends_account`, `max_drawdown`, `trailing_mode`, `trailing_locks_at` |
| passing | `profit_target`, `min_trading_days`, `max_single_day_profit_share` |
| position | `max_total_contracts`, `max_contracts_per_symbol`, `max_notional`, `scaling` (a `(profit_above_start, contracts)` ladder) |
| session | `allow_overnight`, `allow_weekend` (separate on purpose), `flat_before_close_minutes`, `blackout_windows` |
| economics | `evaluation_fee`, `payout_on_pass`, `profit_split` |

`TrailingMode` has four values: `NONE`, `EOD`, `INTRADAY`, and `EOD_TRAIL_INTRADAY_BREACH` -
the last added because Topstep's rule fits neither of the first three (threshold advances on
end-of-day balance, breach tested intraday including unrealized P&L). Modelling it as EOD
understates breach risk; as INTRADAY overstates the trailing. Both errors are large and
opposite, so it is a distinct mode (`test_the_hybrid_is_not_intraday_the_unrealized_high_must_not_ratchet`,
`test_the_hybrid_is_not_eod_the_intraday_dip_must_be_tested`).

`from_dict` **rejects unknown keys**, so a typo'd rule name fails at load instead of silently
disabling a limit (`test_unknown_rule_key_is_refused_rather_than_ignored`).
`contracts_allowed_at(profit)` reads the ladder; with no ladder the flat cap applies.

`PropFirmRiskEngine` and `PropFirmSimulator` / `evaluate()` consume the profile;
`docs/RISK.md` and `docs/BACKTESTING.md` cover them.

### `profiles.py` (archetypes)

`EOD_TRAILING_50K`, `INTRADAY_TRAILING_50K`, `STATIC_DRAWDOWN_100K`, named by **rule shape,
never by firm**, because a `topstep_50k` frozen in source looks authoritative and becomes a
liability the first time the rulebook changes. The module's rule: before any real evaluation
is purchased, copy the closest archetype, set every field from the firm's current written
rules, save it under `live/propfirm/<firm>_<size>.json`, cite it in the journal. Referenced
by tests only (`docs/ARCHITECTURE_AUDIT.md`, "Dead code"). Their numbers are illustrative.

### `topstep.py` (the machine-readable rulebook)

Every parameter is a `Rule(value, quote, source, confidence, retrieved, note)`. `rulebook()`
prints all of them with citations; `python -m quant_brain topstep rules --raw` is the same
thing from a shell. `combine(size, ...)` and `express_funded(size, ...)` build profiles and
call `Rule.require(Confidence.DOC)` on the way, so a profile cannot be built out of an
unverified number without the caller opting in (`UnverifiedRule`). `TopstepAccount` is the
state machine (`TRADING_COMBINE -> COMBINE_PASSED -> EXPRESS_FUNDED <-> PAYOUT_ELIGIBLE`,
`LIVE_FUNDED` only by an external `promote_to_live()`, `LIQUIDATED` absorbing).

---

## The confidence tiers

| tier | value | meaning | consequence in code |
|---|---|---|---|
| `DOC` | 2 | quoted verbatim from a Topstep-owned page fetched on the retrieval date | usable by `combine()` / `express_funded()` by default |
| `SEARCH` | 1 | seen in a site search summary, not verified on the page | refused by default; `allow_unverified_target=True` accepts it knowingly |
| `OWNER` | 0 | published nowhere reachable; the account holder must supply it | refused; listed by `unresolved()` |

`docs/topstep/README.md` uses the same three tiers and adds a convention the code does not
encode: where a number decides whether money is spent, it is marked `DOC` only if seen on
two independent Topstep pages. The doc's quotes are automated transcriptions, not byte-exact
copies; `docs/topstep/VERSIONING.md` requires raw page snapshots to be archived so a future
reader can check them. No `docs/topstep/versions/` directory or `manifest.json` exists yet.

---

## The five corrections applied on 2026-09-13 (commit `b749cbb`)

`docs/topstep/README.md`'s "Corrections to prior work" table was written against the code as
of 2026-09-12 and says "none of them have been applied to the code". That sentence is now
stale in the reader's favour: five of its six rows are in `topstep.py`.

| # | before | now | direction of the old error |
|---|---|---|---|
| 1 | Combine profit target `SEARCH` tier; `combine()` refused unless `allow_unverified_target=True` | `$3,000 / $6,000 / $9,000` at `DOC`, sourced to `topstep.com/no-activation-fee` and corroborated by the consistency article's worked example and the LFA reserve-unlock figures; `combine()` builds without being told (`test_the_profit_target_is_verified_and_no_longer_has_to_be_supplied`) | blocked every pass-probability number |
| 2 | monthly cost absent; `TwinResult.net_capital` always `None` | `COMBINE_COST` `$49 / $99 / $199` (Standard) and `COMBINE_COST_NO_ACTIVATION` `$95 / $149 / $229`, both `DOC`; the help centre and `topstep.com` disagree on the no-activation row (`$85 / $129 / $199`) and both figures are recorded rather than reconciled (`test_the_monthly_cost_is_recorded_with_its_disagreement`) | no net figure at all |
| 3 | default consistency reading `strict` = 50% of total profit | `DEFAULT_READING = "doc_calc"` = **55% of total profit**, settled by the article's own example (`$1,600 / $3,000 = 53%`, `test_the_published_worked_example_reproduces`); the 50% owner figure stays available as `strict` and in `unresolved()` | stricter than reality; understated the pass rate |
| 4 | one `XFA_STANDARD_CAP = 5_000` / `XFA_CONSISTENCY_CAP = 6_000` for every size | `XFA_STANDARD_CAP_BY_SIZE` `$2,000 / $3,000 / $5,000`, `XFA_CONSISTENCY_CAP_BY_SIZE` `$3,000 / $4,000 / $6,000`; `express_funded` carries the per-size cap into `payout_on_pass` and `TopstepAccount.payout_cap` reads it (`test_the_payout_ceiling_is_per_account_size`) | **overstated the $50K payout ceiling 2.5x**, on the size most people trade |
| 5 | `take_payout` lowered the balance and left the MLL to the trailing arithmetic | `MLL_RESETS_ON_PAYOUT`: after a payout the MLL is pinned at the lock level permanently (`mll_reset_by_payout`, `test_a_payout_pins_the_mll_at_zero_permanently`) | risk budget after a payout was wrong in both directions depending on timing |

The sixth row of the doc's table - the DLL article moved from `8284207` to `10490293` - is
**not** applied; `topstep.py:95` still cites `8284207`. Link rot only.

Three places in `topstep.py` still describe the pre-correction state and should be read as
stale: the module docstring's "Default: **50% of total profit**" paragraph (line 53; the
`RESOLVED` note below it and `DEFAULT_READING` are current), `combine()`'s docstring about
"the SEARCH-tier figure" (line 486), and `combine_passed()`'s message "Topstep published none
on any page fetched" (line 801, reachable only if a caller passes `profit_target=None`
explicitly). `RETRIEVED` is `2026-09-12` and is the default `Rule.retrieved` for every rule,
including the payout rules whose comments say they were read on 2026-09-13.

`BLOCKERS.md` OWNER-1 predates this commit and still lists the profit target as `SEARCH` and
the cost as not found. The code is the current state; the blocker text is not.

---

## What remains OWNER-tier

`python -m quant_brain topstep unresolved` (exit code 1, 2026-09-13):

| rule | value in code | why it is still open |
|---|---|---|
| `combine_min_trading_days` | 0 | no minimum appeared on any Combine page fetched; the practical floor is two days because one day cannot satisfy 55% of total profit (`docs/topstep/COMBINE.md`) |
| `xfa_scaling_plan` | `()` | the ladder exists (8284215 quotes the rule) but its rungs are published only as an image on article 8284223. An empty ladder means simulated size is **too large at low balances - the direction that flatters results** |
| `combine_consistency_owner_figure` | 0.50 | the owner brief's figure; supported by no page reachable on 2026-09-13; retained on the record, not the default |

Two more things `docs/topstep/RULES.md` marks `OWNER` that `unresolved()` does **not** list:
the size of the profit-target increase when consistency is exceeded (`TS-CON-03`; the code
models the smallest increase that restores compliance, a lower bound on the real penalty), and
the LFA entry decision, which is a Risk Team judgement the code models as `promote_to_live()`
and never triggers from strategy behaviour (`test_going_live_is_an_external_decision_never_a_threshold`).
`unresolved()`'s docstring says what remains is "genuinely unpublished rather than merely
unfound"; those two are unpublished but are not in its return value.

`python -m quant_brain topstep readiness` (exit code 1):

```
yes  Combine profit target verified
NO   XFA scaling ladder known (published only as an image)
yes  futures price store present
yes  quote store present (spread measured, not assumed)
NO   a strategy has survived the funnel (0 so far)
NO   an approval directory exists
NO   a prop-firm adapter has been exercised against a real venue
NOT READY: 4 of 7 conditions unmet.
```

The last line is a constant `False` in `__main__.py`, not a probe; the function's docstring
("every line is checked, not asserted") overstates it by one line.

---

## Not implemented

- **An adapter that can place an order at Topstep.** `ProjectXAdapter.submit()` raises on any
  live path; the order, position and fill endpoints are `UNKNOWN` (`docs/topstep/API_UNKNOWNS.md`).
- **The XFA scaling ladder.** Empty; see above.
- **Payout mechanics beyond eligibility and the cap.** `docs/topstep/PAYOUTS.md` documents the
  4:00 PM CT day lock, the request-day exclusion, the `$125` minimum, processing fees, the
  positive-since-last-payout gate, and the limited-time doubled cap for a voluntary DLL. The
  twin models winning-day counts, the 50%-of-balance cap per size, the MLL reset and the
  day-count reset. It does not model the request-day exclusion, the minimum, fees, or the
  doubled cap.
- **Automatic use of the verified fee.** `TopstepTwin(combine_fee=None)` still reports gross
  only; the caller passes `COMBINE_COST[size].value` if a net figure is wanted.
- **Prohibited-conduct rules** (`docs/topstep/PROHIBITED.md`), hedging restrictions, the
  3:08 PM CT no-new-positions guidance, product-specific closes. The generic profile has
  `flat_before_close_minutes` and `blackout_windows`; nothing maps the Topstep trading-hours
  table onto them.
- **Rule versioning on disk.** `docs/topstep/VERSIONING.md` specifies `versions/<v>/` with
  `manifest.json` and raw snapshots; none exists. The code carries one version and a second
  has never been exercised (`docs/ARCHITECTURE_AUDIT.md`).
- **The LFA** beyond `promote_to_live()`: reserve release in 25% increments, the 20%
  tradeable share and the LFA DLL are recorded as `Rule`s (`LFA_*`) and consumed by nothing.
- **Back2Funded reactivation**, reset limits, the locked purchase path (`TS-CMB-04/07/08`).

## What this document does not claim

It does not claim the rulebook is complete or current beyond 2026-09-13; Topstep changes it
without notice and the retrieval dates are the only facts. It does not claim the numbers have
been confirmed on a dashboard; no account exists. It does not claim the twin's pass rates are
achievable; no strategy has produced one above the funnel's floor. It does not claim the
consistency penalty is modelled correctly; it is modelled as a lower bound because the size
is unpublished. It does not claim `BLOCKERS.md` OWNER-1 is current; the code has moved past it.
