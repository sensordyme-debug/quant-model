# Intrabar forensics — what one-minute OHLCV knows, and what it cannot

Written before the intrabar path was wired into the canonical runner, because a conservative
assumption applied without stating its logic is just a different unstated assumption.

Code: `quant_brain/research/canonical_ledger.py` (`session_marks`),
`quant_brain/research/intrabar_path.py` (the standalone bound),
`quant_brain/research/execution_modes.py` (the ladder).
Tests: `tests/test_canonical_pipeline.py`, `tests/test_topstep_twin_forensics.py` §D.

---

## 1. What is known from OHLCV

For each one-minute bar `i` the store gives exactly five numbers: `open[i]`, `high[i]`,
`low[i]`, `close[i]`, `volume[i]`. From those, and only those, the following are **facts**:

| Known | Why it is a fact |
|---|---|
| the price traded at `high[i]` at some instant inside bar `i` | that is the definition of the high |
| the price traded at `low[i]` at some instant inside bar `i` | likewise |
| every price in `[low[i], high[i]]` was touched at least once | a continuous path from open to close via both extremes must cross every level between them |
| no price outside `[low[i], high[i]]` traded during bar `i` | the extremes are extremes |
| the bar opened at `open[i]` and closed at `close[i]` | given |
| `volume[i]` contracts changed hands in total | given |

A position of size `q` and direction `d` held for the whole of bar `i` was therefore marked,
at some instant, at **every** equity value between `q·d·(low[i] − P)` and
`q·d·(high[i] − P)` relative to its entry price `P`. That is the entire information content
of a bar for a barrier problem, and it is enough to bound the account.

---

## 2. What is unknowable

| Unknowable | Consequence |
|---|---|
| **the order of the high and the low within the bar** | a path that would touch a limit on one and recover on the other cannot be resolved; both orderings are consistent with the data |
| **the number of times each level was touched** | no way to distinguish a single spike from sustained trade at the extreme |
| **the price at any instant other than open and close** | no sub-bar path, only its envelope |
| **where inside the bar a fill occurred** | so a position that changes during bar `i` may or may not have been on at the extreme |
| **size available at any price** | `volume[i]` is a total, not a book. Partial fills, queue position and impact are all unmodellable — and are declared `NOT MODELLED` in every execution mode rather than approximated |
| **whether a level was reached by trading *through* it or *to* it** | matters for resting-order fills; the engine assumes touch-fills |

Nothing below infers any of these. Where one is needed, the engine takes the reading that
hurts the account and says so.

---

## 3. Bounds on account equity

Let a position of signed size `s = q·d` be entered at price `P` and let `E₀` be the account
equity at entry. For any bar `i` held in full, the equity `E(t)` at any instant `t` inside
that bar satisfies:

```
E_lower(i)  =  E₀ + s·(low[i]  − P)·M      if s > 0        M = contract multiplier
               E₀ + s·(high[i] − P)·M      if s < 0

E_upper(i)  =  E₀ + s·(high[i] − P)·M      if s > 0
               E₀ + s·(low[i]  − P)·M      if s < 0

E_lower(i)  ≤  E(t)  ≤  E_upper(i)         for all t in bar i
```

Both bounds are **attained**: the extremes are real trades, so `E_lower` and `E_upper` are
the tightest bounds OHLCV supports. Nothing sharper is available without tick data.

Written the way the code does it, `E_lower` uses the *adverse* extreme — the low for a long,
the high for a short — which is `_adverse_price(direction, high, low)` in
`canonical_ledger.py`. The realised P&L uses `close[i]`, which lies inside the interval by
construction.

**The barrier test only needs the lower bound.** A maximum-loss limit is breached by equity
falling to a level; the upper bound cannot cause a breach and is not used. The account's
*profit* is never taken from `E_upper` — that would be marking a win the trader never
realised.

---

## 4. Long and short

Symmetric, and asserted rather than assumed
(`test_18_the_short_side_mirrors_the_long_side_exactly`):

| position | adverse extreme | favourable extreme |
|---|---|---|
| long (`s > 0`) | `low[i]` | `high[i]` |
| short (`s < 0`) | `high[i]` | `low[i]` |
| flat (`s = 0`) | `close[i]` — no exposure, so no excursion | same |

A mirrored price path with a mirrored position must produce an identical ledger, marks
included. Marking a short at the low would flatter it, which is the single most likely sign
error in this whole layer; the mutation `ledger__long_marked_at_the_high_instead_of_the_low`
exists to prove the suite catches it.

**The entry bar carries no excursion.** A position opens at `close[entry_bar]`, so anything
that happened earlier in that bar happened before the position existed. Marking the entry
bar's low would invent a loss the trader could not have taken.

---

## 5. Stops, targets and the forced flatten

The exit bar is the only place where the bound and the fill model interact, and the three
modes differ there and nowhere else.

| exit reason | `INTRABAR_CONSERVATIVE` marks the exit bar at | `STRESS` marks it at | why |
|---|---|---|---|
| **stop** / **trail** | the stop price | the bar's adverse extreme | the position was *closed* at the stop, so the account cannot be marked below it — unless the flatten had not registered when the worst tick printed, which is what STRESS assumes |
| **target** | the bar's adverse extreme | the bar's adverse extreme | the ordering of high and low is unknowable (§2), so the adverse one is assumed first |
| **time stop** | the bar's adverse extreme | the bar's adverse extreme | the exit is at the close; the whole bar was held |
| **signal invalidation** | the bar's adverse extreme | the bar's adverse extreme | same |
| **forced flatten** (the bell) | the bar's adverse extreme | the bar's adverse extreme | same |

An adverse mark is emitted only when it is **worse** than the exit value; otherwise it is
dropped, so a bar with no adverse excursion produces exactly the close-only path.

Two fill assumptions are declared and unchanged across all modes, because they are about
*price*, not about the path:

- **a stop fills at the stop price**, even when the bar gapped straight through it. On a
  bar that opened 100 points below a 3990 stop the modelled loss is $500, not the $5,250 a
  fill at the low would give. This is **optimistic** and it is stated in
  `stop_execution` for every mode, asserted by
  `test_15_a_gap_straight_through_the_stop_still_fills_at_the_stop`.
- **a target fills at the target price**, and only if the bar traded through it. The same
  rule that flatters the stop caps the winner, asserted by test 16.

The forced flatten fills at the last bar's close. No position survives the bell, so no
overnight gap ever reaches the account — a property of the strategies this engine runs, not
a modelling shortcut.

---

## 6. Ambiguous same-bar events

A bar on which both a stop and a target are reachable is genuinely ambiguous: OHLCV cannot
say which came first. The engine resolves it **as a stop, always**, and sets
`ambiguous_bar` on the trade so the flag reaches the trade ledger and a reader can count how
much of a result rests on the assumption.

The rule chain is fixed and pessimistic, in this order:

```
stop  →  target  →  trail  →  time stop  →  signal invalidation  →  forced flatten
```

Two distinct ambiguities, resolved separately:

| ambiguity | resolution |
|---|---|
| stop and target both reachable in one bar | STOP, flagged (`test_08`) |
| the account's daily limit and maximum-loss limit both crossed by one mark | the **higher level** fired, because equity fell through it first. Measured over 20,000 paths, the tie-break never changes survival — only the reason string and a dead account's reported balance (`docs/TOPSTEP_TWIN_AUDIT.md`) |

---

## 7. Is the conservative path pessimistic, optimistic, or bounded?

**It is a bound, and specifically a lower bound on equity — not a reconstruction.** Precisely:

- For a position **held through the whole bar**, the mark is **exact**: `E_lower(i)` is
  attained, so the account really was marked there.
- For a bar on which the position **changes**, the mark is **conservative**: the fill
  happened somewhere inside the bar and the trader may not have held through the extreme.
  OHLCV cannot say which, so the engine takes the worse reading.
- For **sub-bar ordering**, it is **conservative**: the adverse ordering is assumed.
- For **fill prices**, it remains **optimistic** — stops and targets fill at their levels
  (§5). This is deliberate and separate: the path model and the fill model answer different
  questions, and merging them would hide both.

So the honest one-line summary is: **the equity path is a tight lower bound where the
position is held and a conservative one where it changes; the fill prices are optimistic and
declared as such.** `INTRABAR_CONSERVATIVE` is never *more* optimistic than `CLOSE_ONLY` and
`STRESS` is never more optimistic than `INTRABAR_CONSERVATIVE`.

### Measured cost of the omission

Real futures store, always long one lot, 09:30–16:00 ET:

| | ES (310 sessions) | MES (249 sessions) |
|---|---|---|
| worst mark from closes, median | −$1,075 | −$119 |
| worst mark using the bar low, median | −$1,162 | −$132 |
| hidden depth, median / p90 / max | $75 / $175 / $725 | $9 / $19 / $76 |
| sessions surviving on closes but breaching on the bar low | **8 (2.6%)** | 0 (0.0%) |

The mini's omission is worth ~2.6% of sessions in the **optimistic** direction. The micro's
is immaterial — the same points are a tenth of the dollars.

---

## 8. The monotonic safety property, at the integrated runner level

The claim, restated as the acceptance criteria put it:

> Adding valid adverse intrabar excursion may leave survival unchanged, or cause a surviving
> account to breach — but must **never** rescue an already-breached account, increase account
> survival probability, or increase account-level profitability.

### Why it holds, structurally

`session_marks` can only **append** marks as the mode hardens; it never removes one and never
raises one. Formally, for the mark multisets `A ⊆ B ⊆ C` produced by CLOSE_ONLY,
INTRABAR_CONSERVATIVE and STRESS on the same fills:

```
min(A)  ≥  min(B)  ≥  min(C)          and          last(A) = last(B) = last(C)
```

The final mark is the settled P&L in all three, so settlement is untouched; the twin's breach
test is a monotone predicate on the marks (`any(equity ≤ level)`), so a larger mark set can
only ever add a breach.

### Proved, not argued

`test_adverse_excursion_can_only_endanger_an_account_never_rescue_it` runs 120 random
multi-session runs through all three modes and asserts, at every step of the ladder:

| invariant | violations |
|---|---|
| settled P&L unchanged | 0 |
| a liquidated account is never rescued | 0 |
| days survived never increases | 0 |
| resampled survival probability never increases | 0 |
| maximum intraday drawdown never improves | 0 |
| minimum buffer never improves while alive | 0 |

The test also requires that at least one run **did** flip from surviving to liquidated — a
monotonicity proof over a fuzz that never crosses the boundary proves nothing.

At the standalone-bound level the same property is checked again in
`test_restoring_the_excursion_can_only_make_the_twin_stricter`, and on the real ES store the
bound flips exactly the 8 of 310 sessions predicted, with the terminal value moved on 0 of
310 and the path shallower on 0 of 310.

### The one documented exception

None found. The property held on every path tested. If one is ever found, it belongs here
with its reason — the criteria allow an exception only when it is "clearly documented and
unrelated to the added adverse excursion", and no such case has arisen.

---

## What is still NOT MODELLED

Repeated here so it cannot be missed, and stated identically in every execution mode:

- **partial fills** — every order fills in full or not at all
- **queue position** — no resting orders, no priority, no through-versus-to distinction
- **market impact** — the account's own orders never move the price
- **sub-bar sequencing** — beyond assuming the adverse ordering
- **overnight gaps** — no position survives the bell
- **tick data** — the bound is as tight as one-minute OHLCV allows and no tighter

## Mode selection

| mode | path | when |
|---|---|---|
| `CLOSE_ONLY` | closes only | reproducing a historical number computed before this layer existed |
| `INTRABAR_CONSERVATIVE` | adverse extreme on every held bar; stops floor the exit bar | **the headline** |
| `STRESS` | as above, plus the exit bar's full extreme even on a stop | checking a result does not rest on the path model |

The mode is stamped on every trade row, every account result and every saved scenario. A
result that omits it cannot be produced — `test_the_execution_mode_is_stamped_on_every_ledger_record`.
