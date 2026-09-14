# Prop firm: the generic profile, the Topstep rulebook, the ten defects closed, and the one left open

Status of this document: describes `quant_brain/markets/futures_cme/{propfirm,topstep,
profiles,twin}.py` and `quant_brain/venues/propfirm.py` at `HEAD = 28fa331`
(2026-09-13 23:54 ET), against the human-readable rulebook in `docs/topstep/`. Every number
was re-read from the code or produced by the read-only command printed beside it on
2026-09-14. Other tracks are editing this tree concurrently; where an uncommitted change has
already moved a number below, it is said so (§3). **No Topstep account exists**; nothing here
has been checked against a live dashboard, and no order has ever been sent to a prop firm
from this repository.

| claim | status | evidence |
|---|---|---|
| ENGINE VALIDATED | yes | `tests/test_qb_propfirm.py` (39), `test_qb_topstep.py` (82), `test_qb_twin.py` (48), `test_qb_venues.py` (69), `test_propfirm_acceptance.py` (49) - 287 tests, all passing |
| **RULEBOOK MATCHES THE PUBLISHED RULES** | yes, as of 2026-09-13 | ten defects closed today; `test_propfirm_acceptance.py` drives hand-computed money paths through the shipped objects and no longer carries a single `xfail` |
| SIZING CONSUMES THE RULEBOOK CORRECTLY | **no** | `core/sizing.py` reads `TopstepAccount.contracts_allowed` as raw contracts; it is micro-equivalents. See §5 |
| STRATEGY VALIDATED | **no** | no strategy has passed the simulated Combine at a rate above the funnel's 10% floor; nothing reached that gate |
| LIVE EXECUTION VALIDATED | **no** | no Topstep account, no adapter that can send (`BLOCKERS.md` OWNER-4, `docs/RISK.md` §5) |
| PROFITABILITY DEMONSTRATED | **no** | |

---

## 1. Two layers, not two rulebooks

`propfirm.py` is firm-agnostic and contains no firm name. `topstep.py` is Topstep, and it
produces `PropFirmProfile`s. The second configures the first; `docs/ARCHITECTURE_AUDIT.md`
calls them layered, not duplicated, and that is the right reading.

### `PropFirmProfile` (generic)

A frozen dataclass of the parameters a rulebook can have. Four fields are new as of
2026-09-13 and are marked:

| group | fields |
|---|---|
| the two limits that end accounts | `daily_loss_limit`, `daily_loss_ends_account`, `max_drawdown`, `trailing_mode`, `trailing_locks_at` |
| passing | `profit_target`, `min_trading_days`, `max_single_day_profit_share`, **`max_single_day_share_boundary`** |
| position | `max_total_contracts`, `max_contracts_per_symbol`, **`contract_equivalence`**, **`permitted_products`**, `max_notional`, `scaling` |
| session | `allow_overnight`, `allow_weekend` (separate on purpose), `flat_before_close_minutes`, **`flat_at_local_time`** + `regular_close_local_time`, `blackout_windows` |
| economics | `evaluation_fee`, `payout_on_pass`, `profit_split` |

`TrailingMode` has four values: `NONE`, `EOD`, `INTRADAY`, and `EOD_TRAIL_INTRADAY_BREACH` -
the last added because Topstep's rule fits neither of the first three (threshold advances on
end-of-day balance, breach tested intraday including unrealized P&L). Modelling it as EOD
understates breach risk; as INTRADAY overstates the trailing. Both errors are large and
opposite, so it is a distinct mode (`test_the_hybrid_is_not_intraday_the_unrealized_high_must_not_ratchet`,
`test_the_hybrid_is_not_eod_the_intraday_dip_must_be_tested`).

`from_dict` **rejects unknown keys**, so a typo'd rule name fails at load instead of silently
disabling a limit (`test_unknown_rule_key_is_refused_rather_than_ignored`).
`__post_init__` (line 200) now fails closed at construction on two things: an unrecognised
`max_single_day_share_boundary`, and a `flat_at_local_time` with no
`regular_close_local_time` to anchor it - "a deadline nobody can anchor is a deadline nobody
enforces".

### `profiles.py` (archetypes)

`EOD_TRAILING_50K`, `INTRADAY_TRAILING_50K`, `STATIC_DRAWDOWN_100K`, named by **rule shape,
never by firm**, because a `topstep_50k` frozen in source looks authoritative and becomes a
liability the first time the rulebook changes. The module's rule: before any real evaluation
is purchased, copy the closest archetype, set every field from the firm's current written
rules, save it under `live/propfirm/<firm>_<size>.json`, cite it in the journal. Imported by
`tests/test_qb_propfirm.py` and `tests/test_qb_venues.py` and nothing else; the module is
unreachable from any entry point (`tests/test_production_reachability.py`). Their numbers are
illustrative.

### `topstep.py` (the machine-readable rulebook)

Every parameter is a `Rule(value, quote, source, confidence, retrieved, note)`. `rulebook()`
prints all of them with citations; `python -m quant_brain topstep rules --raw` is the same
thing from a shell. `combine(size, ...)` and `express_funded(size, ...)` build profiles and
call `Rule.require(Confidence.DOC)` on the way, so a profile cannot be built out of an
unverified number without the caller opting in (`UnverifiedRule`).

### `venues/propfirm.py` (the seam a registry can hold)

`PropFirmRules.check(strategy)` refuses a strategy against the rulebook **before an
evaluation is purchased**, across every stage of the progression, and `PropFirmObjective`
turns resampled session paths into one comparable `ObjectiveResult` carrying pass rate,
violation rate, ruin rate, days and value after fees rather than a single scalar. Ruin means
the account gone with nothing ever withdrawn, not "did not pass" - a path that runs out of
sessions inside the Combine is censored, not ruined. Nothing outside its tests constructs
either class.

---

## 2. The confidence tiers

| tier | value | meaning | consequence in code |
|---|---|---|---|
| `DOC` | 2 | quoted verbatim from a Topstep-owned page fetched on the retrieval date | usable by `combine()` / `express_funded()` by default |
| `SEARCH` | 1 | seen in a site search summary, not verified on the page | refused by default; `allow_unverified_target=True` accepts it knowingly |
| `OWNER` | 0 | published nowhere reachable; the account holder must supply it | refused; listed by `unresolved()` |

`docs/topstep/README.md` uses the same three tiers and adds a convention the code does not
encode: where a number decides whether money is spent, it is marked `DOC` only if seen on
two independent Topstep pages. The doc's quotes are automated transcriptions, not byte-exact
copies; `docs/topstep/VERSIONING.md` requires raw page snapshots to be archived so a future
reader can check them. **No `docs/topstep/versions/` directory or `manifest.json` exists**
(`ls docs/topstep/`).

`RETRIEVED = dt.date(2026, 9, 12)` is still the module default for `Rule.retrieved`. Rules
read on 2026-09-13 - `PAYOUT_MINIMUM`, `COMBINE_CONSISTENCY_BOUNDARY`, `XFA_SCALING_FALLBACK`
- carry an explicit `retrieved=` and are the exceptions.

---

## 3. The ten defects closed on 2026-09-13

`tests/test_propfirm_acceptance.py` was written as a ratchet: ten defects, each pinned with
`xfail(strict=True)` and each xfail reason carrying the help-page citation. All ten are now
fixed and **the file contains no `xfail` marker at all** (`python -m pytest
tests/test_propfirm_acceptance.py -rxX` -> `49 passed`). Its module docstring still describes
the pre-fix state and should be read as a record of what was wrong, not of what is.

| # | defect | fix | where |
|---|---|---|---|
| 1 | a $75 payout was recorded; the published minimum is $125 | `PAYOUT_MINIMUM = Rule(125.0, "Minimum Payout Request: $125", 8284233, DOC, retrieved 2026-09-13)`, enforced in `take_payout`: a request below it returns 0.0 and **nothing moves** - no count clears, the MLL stays put | `topstep.py:422`, `topstep.py:1094` |
| 2 | payout eligibility measured on total profit from inception | `balance_at_last_payout` + `net_profit_since_payout`; `payout_eligible` reads the second. Identical to `total_profit` until the first payout, permanently divergent after | `topstep.py:820, 948, 961` |
| 3 | the consistency route's 3-day count never restarted after a payout | `take_payout` clears `trading_days`, `winning_days` and `daily_pnl`. Leaving the trading-day count standing made an account eligible again the instant a payout settled, having traded nothing since | `topstep.py:1101-1104` |
| 4 | minis and micros counted raw, so 5 ES + 45 MES passed a 50-micro account holding 95 micro-equivalents (1.9x) | `contract_equivalence=True` on both Topstep profiles; `PropFirmProfile.contract_units(symbol)` reads the ratio off the published table (`max_total_contracts / max_contracts_per_symbol`), so one ES is 10 units and one MES is 1; the engine sums `total_equivalents` | `propfirm.py:148, 213, 459` |
| 5 | there was no product list; 50 BTC was accepted | `permitted_products`, checked in `PropFirmRiskEngine.evaluate` **before any sizing**. `_permitted_products()` calls `instruments.get(sym)` at **import** time and lets the `KeyError` escape, so a permitted root with no contract spec cannot exist | `topstep.py:579`, `propfirm.py:155, 229, 442` |
| 6 | a $0-balance Express Funded Account was simulated at the full Combine allowance - 5 ES against the same $2,000 MLL a funded $50K Combine has | `XFA_SCALING_FALLBACK = 0.10`: a stand-in ladder at a tenth of the account-wide allowance, in force whenever `scaling` is not supplied. Five micro-equivalents at $50K, so **no mini at all** | `topstep.py:441, 600, 718` |
| 7 | the mandatory flat was modelled as `flat_before_close_minutes=15` against a 16:00 CT close - 15:45 CT, 35 minutes late, so a position held 15:10-15:45 was a violation the model called compliant every session | `MANDATORY_FLAT = 15:10 CT` carried as `flat_at_local_time`; `flat_deadline_minutes(session_close)` takes the **larger** minutes-before-close of the clock and the offset, so 15:10 binds on a normal day and the offset still binds on a 13:00 early close (AUD-07) | `topstep.py:223`, `propfirm.py:233` |
| 8 | the consistency boundary (`<` vs `<=`) was a hard-coded operator in one property | the boundary is now the third element of a `CONSISTENCY_READINGS` entry and travels with the threshold and the denominator; `doc_calc_exclusive` / `doc_text_exclusive` exist so the cost of the other reading can be measured. `_reading()` normalises both shapes; `with_reading` switches all three | `topstep.py:307, 556`, `propfirm.py:126` |
| 9 | commissions modelled at $4.00 / $1.00 | the published all-in round turns: **ES $3.78, NQ $3.78, MES $1.22, MNQ $1.22** (8284197). The other eight roots stay at the $4.00 / $1.00 placeholder and that is stated as a default, not a measurement | `instruments.py:77, 100-106` |
| 10 | `TopstepStage.FAILED` was reachable in principle and meant nothing | declared, documented **RESERVED**, and unreachable: every way a Topstep account ends is a LIQUIDATION (8284204), a DLL hit is a forced break not a violation (8284207), and exceeding consistency raises the target rather than failing the account (8284208). `test_no_undeclared_state_appears_anywhere_in_the_exercised_lifecycle` asserts no exercised path produces it | `topstep.py:771-780` |

### The cost model that follows from #9

`CostModel.for_contract(symbol)` halves the round turn and **refuses a root with no recorded
commission** - a futures cost model with a zero commission is wrong rather than
conservative. At `28fa331` every root took the default one-tick spread:

| root | commission RT | spread at HEAD | model round turn at HEAD |
|---|---|---|---|
| ES | $3.78 | 1 tick, $12.50 | **$16.28** |
| NQ | $3.78 | 1 tick, $5.00 | **$8.78** |
| MES | $1.22 | 1 tick, $1.25 | **$2.47** |
| MNQ | $1.22 | 1 tick, $0.50 | **$1.72** |

```python
import sys; sys.path.insert(0, ".")
from quant_brain.markets.futures_cme import instruments as inst, execution_sim as ex
for s in ("ES", "NQ", "MES", "MNQ"):
    cm = ex.CostModel.for_contract(s)
    print(s, cm.spread_ticks,
          "$%.2f" % ex.ExecutionSimulator(cost=cm, symbol=s).round_turn_cost(1.0))
```

**One of these numbers moved while this document was being written.** An uncommitted change
in the working tree (`quant_brain/markets/futures_cme/execution_sim.py`, another track's
edit, `git status --porcelain` on 2026-09-14) adds `MEASURED_SPREAD_TICKS` and gives NQ a
measured **two** ticks, so the same command now prints **NQ $13.78** and marks MNQ
`spread_measured=False`. `docs/DATA.md` §3 had already measured NQ at two ticks against ES's
one, so the $8.78 above was a 36% undercharge on the contract with the largest point value in
the universe - an error the commission fix did not touch. Read the table as HEAD, and the
$13.78 as where the tree is going.

---

## 4. The five rulebook corrections of the earlier pass (`b749cbb`)

Still in force, and still not reflected in `docs/topstep/README.md`, whose "Corrections to
prior work" table says "none of them have been applied to the code" (line 11).

| # | before | now |
|---|---|---|
| 1 | Combine profit target at `SEARCH`; `combine()` refused unless told | `$3,000 / $6,000 / $9,000` at `DOC`, sourced to `topstep.com/no-activation-fee` and corroborated by the consistency article's worked example and the LFA reserve-unlock figures |
| 2 | monthly cost absent; `TwinResult.net_capital` always `None` | `COMBINE_COST` `$49 / $99 / $199` and `COMBINE_COST_NO_ACTIVATION` `$95 / $149 / $229`, both `DOC`; the help centre and `topstep.com` disagree on the second row (`$85 / $129 / $199`) and both are recorded rather than reconciled |
| 3 | default consistency reading `strict` = 50% of total profit | `DEFAULT_READING = "doc_calc"` = **55% of total profit**, settled by the article's own worked example (`$1,600 / $3,000 = 53%`). The 50% owner figure stays as `strict` and in `unresolved()` |
| 4 | one `XFA_STANDARD_CAP = 5_000` for every size | `XFA_STANDARD_CAP_BY_SIZE` `$2,000 / $3,000 / $5,000`, `XFA_CONSISTENCY_CAP_BY_SIZE` `$3,000 / $4,000 / $6,000`; the old constant **overstated the $50K ceiling 2.5x** |
| 5 | `take_payout` left the MLL to the trailing arithmetic | `MLL_RESETS_ON_PAYOUT`: after a payout the MLL is pinned at the lock level permanently (`mll_reset_by_payout`) |

The sixth row of the doc's table - the DLL article moved from `8284207` to `10490293` - is
**still not applied**; `topstep.py:96` cites `8284207`. Link rot only.

Three places in `topstep.py` still describe the pre-correction state and should be read as
stale: the module docstring's "Default: **50% of total profit**" paragraph (line 53; the
`RESOLVED` note at line 322 and `DEFAULT_READING` at 336 are current), `combine()`'s docstring about
"the SEARCH-tier figure" (line 624), and `combine_passed()`'s message "Topstep published none
on any page fetched" (line 1019, reachable only if a caller passes `profit_target=None`
explicitly).

---

## 5. What is still wrong: the contract-allowance unit mismatch

`TopstepAccount.contracts_allowed` returns the account-wide allowance in **micro-equivalents**
and says so in its docstring: "50 here means fifty micros or five minis, not fifty of whatever
a caller happens to be trading."

`core/sizing.py` reads it as raw contracts. `MllAccount` (line 93) declares
`contracts_allowed -> int | None` with no unit, and `enforce()` (line 357) does:

```python
caps.append((Binding.PROP_FIRM, int(allowed),
             f"prop firm allows {allowed} contracts at this balance"))
```

Measured:

```python
import sys; sys.path.insert(0, ".")
from quant_brain.markets.futures_cme import topstep as ts
a = ts.TopstepAccount(profile=ts.combine(50_000))
print(a.contracts_allowed, a.profile.max_contracts_per_symbol["ES"], a.profile.contract_units("ES"))
# 50 5 10.0
```

So the prop-firm ceiling never binds at its real value. Measured on a fresh $50K Combine
(equity $50,000, MLL $48,000, room $2,000), with `PropFirmSizer`'s default quarter-of-the-room
fraction, against the **published ceiling of five ES**:

```python
import sys; sys.path.insert(0, ".")
from quant_brain.markets.futures_cme import topstep as ts, instruments as inst
from quant_brain.core import sizing as sz
a = ts.TopstepAccount(profile=ts.combine(50_000))
for sd in (2.0, 1.0, 0.5, 0.25):
    ctx = sz.SizeContext(spec=inst.get("ES").spec, equity=50_000.0,
                         stop_distance=sd, prop_account=a)
    print(sd, sz.PropFirmSizer().size(ctx).contracts)
```

| ES stop | risk per contract | contracts permitted | legal |
|---|---|---|---|
| 2.00 pt | $100.00 | 5 | 5 |
| 1.00 pt | $50.00 | **10** | 5 |
| 0.50 pt | $25.00 | **20** | 5 |
| 0.25 pt (one tick) | $12.50 | **40** | 5 |

The two-point row agreeing is a coincidence of the 25% fraction, not a check working. The
`Binding` on every row is `strategy_signal`, never `prop_firm`, because the only prop-firm cap
that can bind is `distance_to_mll // risk_per_contract` - a dollar bound - and the contract
ceiling that should cut 40 down to 5 was compared against 50.

The two other consumers of the allowance get it right, which is what makes this a `sizing`
defect and not a `topstep` one: `PropFirmRiskEngine.evaluate` weights the live book through
`contract_units` (`propfirm.py:459`), and `venues/propfirm.py::_check_one` weights the
strategy's declared per-symbol peaks the same way before comparing them with the day-one cap
(`venues/propfirm.py:424`). `core/sizing.py` is the one that does not, and it is the one
`core/governor.py` reaches for. **Unfixed at `28fa331`.** No test covers it:
`tests/test_qb_sizing.py` exercises `PropFirmSizer` against a `FakeAccount` whose
`contracts_allowed` is a plain integer with no unit attached.

---

## 6. What remains OWNER-tier

`python -m quant_brain topstep unresolved` (exit code 1, run 2026-09-14) - **four** rules,
one more than before, because the stand-in ladder is listed separately from the ladder it
stands in for:

| rule | value in code | why it is still open |
|---|---|---|
| `combine_min_trading_days` | 0 | no minimum appeared on any Combine page fetched; the practical floor is two days because one day cannot satisfy 55% of total profit (`docs/topstep/COMBINE.md`) |
| `xfa_scaling_plan` | `()` | the ladder exists (8284215 quotes the rule) but its rungs are published only as an image on article 8284223 |
| `xfa_scaling_fallback` | 0.10 | **the number actually in force** while the rungs stay unpublished. Listed separately on purpose: "the ladder is unknown" and "here is what we size on instead" are two different things to read before spending money |
| `combine_consistency_owner_figure` | 0.50 | the owner brief's figure; supported by no page reachable on 2026-09-13; retained on the record, not the default |

Two more things `docs/topstep/RULES.md` marks `OWNER` that `unresolved()` does **not** list:
the size of the profit-target increase when consistency is exceeded (`TS-CON-03`; the code
models the smallest increase that restores compliance, a lower bound on the real penalty), and
the LFA entry decision, which is a Risk Team judgement the code models as `promote_to_live()`
and never triggers from strategy behaviour (`test_going_live_is_an_external_decision_never_a_threshold`).
`unresolved()`'s docstring says what remains is "genuinely unpublished rather than merely
unfound"; those two are unpublished but are not in its return value.

`python -m quant_brain topstep readiness` (exit code 1, run 2026-09-14):

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

The last line is a literal `False` in `__main__.py:125`, not a probe; the function's docstring
("every line is checked, not asserted") overstates it by one line.

`BLOCKERS.md` OWNER-1 still lists the profit target as `SEARCH`, the consistency default as
50% and the cost as not found. All three moved in `b749cbb`. The code is the current state;
the blocker text is not.

---

## 7. Not implemented

- **An adapter that can place an order at Topstep.** `ProjectXAdapter.submit()` raises on any
  live path; the order, position and fill endpoints are `UNKNOWN`
  (`docs/topstep/API_UNKNOWNS.md`). And nothing in this repository can transmit an order at
  all right now - `docs/RISK.md` §1.
- **The real XFA scaling ladder.** A conservative stand-in is in force; see §6.
- **Payout mechanics beyond eligibility, the cap and the minimum.** `docs/topstep/PAYOUTS.md`
  documents the 4:00 PM CT day lock, the request-day exclusion, the `$125` minimum,
  processing fees taken after the profit split, the positive-since-last-payout gate, and the
  limited-time doubled cap for a voluntary DLL. The twin now models the winning-day count,
  the 50%-of-balance cap per size, the per-size ceiling, the MLL reset, the day-count reset,
  the since-payout profit window and the $125 minimum. It does **not** model the request-day
  exclusion, processing fees, or the doubled cap (`grep -in "processing_fee\|request_day\|doubl"
  topstep.py twin.py` returns nothing).
- **Automatic use of the verified fee.** `TopstepTwin(combine_fee=None)` still reports gross
  only and labels it; the caller passes `COMBINE_COST[size].value` if a net figure is wanted.
- **Prohibited-conduct rules** (`docs/topstep/PROHIBITED.md`), hedging restrictions, the
  3:08 PM CT no-new-positions guidance, product-specific closes. `blackout_windows` is empty
  on every Topstep profile; nothing maps the Topstep trading-hours table onto it.
- **Rule versioning on disk.** `docs/topstep/VERSIONING.md` specifies `versions/<v>/` with
  `manifest.json` and raw snapshots; none exists. The code carries one version and a second
  has never been exercised.
- **The LFA** beyond `promote_to_live()`: reserve release in 25% increments, the 20%
  tradeable share and the LFA DLL are recorded as `Rule`s (`LFA_*`) and consumed by nothing.
- **Back2Funded reactivation**, reset limits, the locked purchase path (`TS-CMB-04/07/08`).
- **A correct unit on the contract allowance in `core/sizing.py`** (§5).

## 8. What this document does not claim

It does not claim the rulebook is complete or current beyond 2026-09-13; Topstep changes it
without notice and the retrieval dates are the only facts. It does not claim the numbers have
been confirmed on a dashboard; no account exists. It does not claim the twin's pass rates are
achievable; no strategy has produced one above the funnel's floor. It does not claim the
consistency penalty is modelled correctly; it is modelled as a lower bound because the size
is unpublished. It does not claim the XFA is sized correctly; the ladder is a stand-in chosen
to be conservative, not Topstep's. It does not claim a sizer built on this rulebook would
propose a legal position; `core/sizing.py` misreads the allowance by 10x on minis (§5). It
does not claim `docs/topstep/README.md` or `BLOCKERS.md` OWNER-1 are current; the code has
moved past both.
