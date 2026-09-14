# Configuration: secrets, settings, safety policy and the trading target

Describes the tree at 2026-09-14. Every claim here names the file that implements it, and
`tests/test_config_safety.py` enforces the parts that can be enforced, including the rule that
this document and the code cannot drift apart on which variables exist.

Read `python -m quant_brain config doctor` before reading this. It answers most of it for
your actual machine, and it prints no value ever.

---

## What was wrong

`.env.example` documented four safety flags:

```
DRY_RUN=true
LIVE_TRADING_ENABLED=false
EXECUTION_ENABLED=false
ORDER_TRANSMISSION_ENABLED=false
```

Measured on 2026-09-14, **not one of them was read by anything.** `EXECUTION_ENABLED` appeared
nowhere in the repository outside that file. `ORDER_TRANSMISSION_ENABLED` existed only as a
Python constant of the same name inside two runners, which is a different thing that happens
to share a spelling. `DRY_RUN` and `LIVE_TRADING_ENABLED` matched only an enum member and a
substring of `QB_LIVE_TRADING_ENABLED`.

Setting one of those flags changed nothing. Setting one and believing you had disabled
something was worse, because it was wrong in the dangerous direction. Documentation that
describes a control which does not exist is trusted, and that makes it worse than no
documentation.

All four are now read by `quant_brain/core/config.py`, and through it by both runners and the
ProjectX adapter.

---

## Four kinds of configuration, kept apart

| kind | examples | where it lives | why it is separate |
|---|---|---|---|
| **Secret** | `PROJECTX_API_KEY`, `ALPACA_API_KEY` | `live/secrets.env`, gitignored | a leak is permanent |
| **Runtime** | `PROJECTX_BASE_URL`, `QB_VENUE` | process environment | machine-dependent, not sensitive |
| **Safety policy** | the four flags | process environment | what this process may attempt |
| **Target** | `TOPSTEP_TARGET_ACCOUNT_ID` | process environment | *which account*, and guessing is a catastrophe |

They are kept apart because their failure modes differ. A missing secret is a setup problem
you notice immediately. A wrong target is a catastrophe that looks like success. A permissive
safety flag is a catastrophe that looks like a setup problem.

---

## Where secrets belong

**`live/secrets.env`.** One file, gitignored, `KEY=value` per line, `#` comments allowed,
surrounding quotes optional. It already held the data-vendor keys and now holds the ProjectX
credentials as well.

```
PROJECTX_USERNAME=...
PROJECTX_API_KEY=...
```

One file rather than two on purpose: a second credential file is a second thing to add to
`.gitignore`, a second thing to forget, and a second place for someone to look and not find
anything.

**Two parsers read it, and that is deliberate.** `scripts/apikeys.py` has parsed it since
before any of this and still does, unchanged. `quant_brain/core/config.py` parses it too,
because making `quant_brain` import from `scripts/` would invert the dependency the whole
package is arranged to avoid. They must agree, and
`test_the_two_parsers_of_the_secret_file_agree` checks that they do on the same file.

**Precedence: an exported environment variable wins over the file.** Both parsers use
`setdefault`. That is the right way round here, because it lets a scheduled task or a CI job
supply a credential without a file on disk, and it lets a shell override the file for one
command without editing it.

Credentials may also be set directly in the environment and never written to a file at all.
The adapter does not care which; it reads `os.environ` and nothing else.

---

## How ProjectX credentials are loaded

`quant_brain/brokers/projectx.py::Credentials.from_environment()`. Three properties worth
knowing:

- **Environment only.** Never an argument, never a repository file, never a config object.
  An object that holds a credential ends up in an exception, a log line or a debugger
  eventually, so the credential is not put in one.
- **No printable form.** `Credentials.__repr__` and `__str__` are overridden to emit
  `api_key=<redacted>`. The key is materialised in exactly one place, `payload()`, which is
  the login body.
- **A missing credential names itself and not the other one.** The error says which variable
  is unset. `test_the_adapter_names_which_credential_is_missing_and_shows_neither` asserts
  that a credential which *was* set does not appear in that message.

`Configuration` never holds a credential at all. It reduces each to a boolean at load, so
there is no field, property or method on it that could return one.

---

## How account selection works

`TOPSTEP_TARGET_ACCOUNT_ID`, read by `quant_brain/core/config.py`.

It is treated as configuration rather than as a secret, because an account identifier
identifies and does not authenticate. It is nonetheless **strictly required and never
guessed**. An unset target is an error, not an invitation to discover one, because the failure
mode of guessing is trading the wrong account, and no later check recovers from that.

Characters outside `[A-Za-z0-9-_]` are **refused rather than trimmed**. These values are
pasted from a dashboard and a trailing quote or comment is the usual accident; silently
trimming is how the wrong account gets traded.

Credentials without a target reach `READ_ONLY_CONFIGURED`, which is enough to authenticate and
to *list* accounts, and not enough to act on one. There is no "the" account until a person
names it.

---

## How the safety flags work

Read by `quant_brain/core/config.py`, composed by `transmission_allowed()`, and consulted by
`scripts/intraday_trader.py`, `scripts/paper_trade.py` on both its paths, and
`quant_brain/brokers/projectx.py`.

**Parsing is fail-closed and asymmetric.**

| flag | kind | true when | unset or unrecognised |
|---|---|---|---|
| `DRY_RUN` | protective | *not* `0`/`false`/`no` | **true**, stay in dry run |
| `LIVE_TRADING_ENABLED` | enabling | `1`/`true`/`yes` | false |
| `EXECUTION_ENABLED` | enabling | `1`/`true`/`yes` | false |
| `ORDER_TRANSMISSION_ENABLED` | enabling | `1`/`true`/`yes` | false |

Both rules point the same way: an unreadable configuration is a safe configuration. An
unrecognised value is *additionally* reported as `CONFIG_INVALID`, so a typo is visible rather
than merely survivable. Refusing to run on a typo is right; refusing while also guessing the
dangerous interpretation would not be.

**No single flag is sufficient, and neither are all four.** Transmission requires eight
conditions in four different media:

1. `DRY_RUN` false
2. `LIVE_TRADING_ENABLED` true
3. `EXECUTION_ENABLED` true
4. `ORDER_TRANSMISSION_ENABLED` true
5. ProjectX credentials present
6. `TOPSTEP_TARGET_ACCOUNT_ID` set
7. the runner's own **code-level** `ORDER_TRANSMISSION_ENABLED` constant, which is a literal
   `False` in the source of all three modules and which configuration cannot reach
8. an `Authority` at `EXECUTION_READY`, which `quant_brain/core/mode.py` will only produce
   from `Authority.for_live()` and its own three conditions: a typed
   `i_understand_this_is_real_money=True`, the separate `QB_LIVE_TRADING_ENABLED` variable,
   and a non-empty human-written approval file for that exact venue and account

The split between 7 and the rest is the design. A constant alone would mean an operator
cannot stop a running process without a deploy. Configuration alone would mean a stray
variable in a scheduled task is sufficient. An approval file alone goes stale. Requiring all
three means an accident has to happen three times, in three media, in the same direction.

`transmission_allowed()` returns **every** reason it refused rather than the first, so nobody
works through them one run at a time under the impression that the last one will be the last.

---

## What the states mean

`ConfigState`, in `quant_brain/core/config.py`.

| state | means | permits |
|---|---|---|
| `CONFIG_MISSING` | a required input is absent | nothing |
| `CONFIG_INVALID` | inputs present, at least one malformed | nothing |
| `READ_ONLY_CONFIGURED` | credentials, no target account | authenticate; list accounts |
| `READ_ONLY_READY` | credentials and an explicit target | read-only work on that account |
| `PRACTICE_READY` | the above, all four flags permissive, authority reaches `PRACTICE` | practice order flow, if a transmission path existed |
| `LIVE_EXECUTION_AUTHORIZED` | the above, authority reaches `EXECUTION_READY` | nothing today; see below |

`CONFIG_INVALID` ranks as worse than `CONFIG_MISSING` deliberately. A missing value is honest.
A malformed one means somebody believed they had configured something.

**Authentication is not authorization.** A working username and API key puts you at
`READ_ONLY_CONFIGURED`, three states below anything that can act on an account and four below
anything that could trade. The gap is the point: every prop-firm accident starts with a
process that could log in.

**`LIVE_EXECUTION_AUTHORIZED` is not reachable from configuration alone.**
`mode.from_environment()` refuses to produce `EXECUTION_READY` at all, so no combination of
environment variables gets there through the normal path.

---

## What is not authorized, and cannot be

**No order-transmission path exists.** This is not a flag that is currently off. It is the
absence of code:

- `ProjectXAdapter.submit()` has no live branch. Past the dry-run branch it raises, with a
  message saying the implementation is deliberately absent because "an implementation present
  but gated is one edit from an accident, whereas an implementation absent is not".
- `/api/Order/place` appears nowhere in any Python file. It is documented in
  `docs/topstep/API.md` and has never been called.
- `ProjectXAdapter.working()` and `reconcile()` also refuse rather than returning empty
  results, because an empty position set looks like agreement with any local state.

`test_no_configuration_makes_transmission_possible` forces every environment condition the
dangerous way, builds a genuine live `Authority`, and asserts the adapter still cannot send.
`test_live_submission_is_not_implemented_rather_than_gated` goes further and replaces the
entire configuration layer with a stub that permits everything, then asserts the raise still
happens.

---

## How to verify your configuration

```
python -m quant_brain config doctor
```

Reports each credential as `PRESENT` or `MISSING`, the target account, all four flags, whether
git is tracking any credential file, the resulting state, and every reason execution is not
permitted. It prints no value, and `test_the_doctor_subprocess_prints_no_credential` runs the
real command with a marker where a credential would be and asserts the marker never appears in
the output.

Exit codes, so it can be used in a script:

| code | meaning |
|---|---|
| 0 | configuration is usable for what it claims |
| 1 | `CONFIG_MISSING` or `CONFIG_INVALID` |
| 2 | a credential file is tracked by git, which is an incident rather than a setup step |

---

## How to avoid committing a secret

**Ignored** (verified with `git check-ignore`, not by reading the file):

```
.env          .env.*  (except .env.example)      *.key   *.pem
live/secrets.env      live/secrets*.json         live/*.env
live/approvals/
```

`.env` alone used to be the whole rule, which left `.env.local` and every other suffix
trackable. Measured on 2026-09-14: `git check-ignore .env.local` said *not ignored*.

**`.gitignore` is checked, not trusted.** `secret_files_tracked_by_git()` asks
`git ls-files`, because a file added before a rule was written stays tracked forever and
`.gitignore` will not say so. That is exactly how a secret gets committed by somebody who
checked the ignore file.

**Three tests stand behind this**, and they are separate questions:

- `test_no_credential_file_is_tracked_by_git` — what git is tracking now.
- `test_every_credential_shape_is_ignored` — what git would do with a new file.
- `test_no_secret_name_has_a_value_baked_into_source` — a sweep of every tracked `.py`,
  `.json`, `.md` and `.ps1` for a long opaque literal assigned to a name like `API_KEY` or
  `SECRET`. It cannot prove the absence of a secret and does not claim to; it catches the
  copy-paste every repository eventually receives. A literal that announces itself as a
  canary, such as the `DO-NOT-LEAK` fixture in `tests/test_qb_projectx.py`, is excluded by
  its marker. The test carries a **positive control** asserting the pattern still matches an
  obvious credential literal, because for a while an editing accident had turned its word
  boundaries into backspace characters and it silently matched nothing at all.

**`.env.example` is tracked on purpose** and is the canonical template. It may contain only
`<angle-bracket>` placeholders, the words `true`/`false`, or nothing, and
`test_the_tracked_template_contains_nothing_that_looks_like_a_real_value` enforces that.

---

## The template and the code cannot drift

Two tests, in both directions:

- `test_every_documented_variable_has_a_real_reader` — a variable in `.env.example` that no
  module reads fails the suite. This is the check that would have caught the original defect.
- `test_every_configuration_variable_this_module_reads_is_documented` — a variable
  `config.py` reads and the template omits fails it too.

---

## What this does not do

It does not make ProjectX usable. Populating credentials moves the state from
`CONFIG_MISSING` to `READ_ONLY_CONFIGURED`, and adding a target account moves it to
`READ_ONLY_READY`. Both are states about *configuration*. Whether the credentials actually
authenticate is unknown until something calls the endpoint, which nothing has.

It does not implement account discovery, contract discovery, historical data, positions,
orders or trades. Those are the next phase and all of them are read-only.

It does not change any existing Alpaca, FMP or Theta credential, or the code that reads them.
`scripts/apikeys.py` is byte-identical to what it was.
