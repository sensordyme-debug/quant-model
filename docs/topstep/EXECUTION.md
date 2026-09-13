# Execution: what can reach a venue, and why almost nothing can

Status of this document: describes code that exists and is tested. Nothing here enables live
trading, and the last section explains precisely what would still be required.

---

## The two axes

There are two independent questions, and conflating them is how prop-firm integrations fire
unintended orders.

| | question | lives in | values |
|---|---|---|---|
| **Authority** | what may this PROCESS do? | `quant_brain/core/mode.py` | RESEARCH · BACKTEST · VALIDATED · PAPER · PRACTICE · HUMAN_APPROVAL · EXECUTION_READY |
| **ConnectionState** | what can this SOCKET do? | `quant_brain/brokers/projectx.py` | DISCONNECTED · AUTHENTICATING · AUTHENTICATED · PRACTICE_READY · DRY_RUN · EXECUTION_READY · HALTED |

`AUTHENTICATED` means a token exists. It grants read access and **nothing else** —
`ConnectionState.AUTHENTICATED.can_send` is `False`, and a test asserts that
`EXECUTION_READY` is the only state for which it is `True`.

Both must permit an order. A fully authenticated session under a RESEARCH authority sends
nothing; a fully approved authority with an expired token sends nothing.

---

## The order path

```
Signal
  ↓
OrderIntent            unsigned quantity + Side; no broker vocabulary
  ↓
RiskChain              every engine must agree; the most restrictive answer wins
  ↓                    FLATTEN bypasses every engine (AUD-06 / AUD-08)
RoutedExecutor         checks Authority >= adapter.requires AT CONSTRUCTION
  ↓
ExecutionAdapter       the only layer that names a broker
  ↓
venue
```

Two properties are structural rather than conventional, and both are tested:

- **No module outside `quant_brain/brokers/` may import a broker SDK.**
  `tests/test_qb_adapter.py` walks the AST of every other module and fails on an import of
  `ib_async`, `ib_insync`, `ibapi`, `alpaca` or `polygon`.
- **There is one path to a venue and it runs through the risk chain.** A denied intent never
  reaches an adapter; a reduced one arrives at the reduced size; no ordering of engines lets a
  later one re-permit an earlier denial.

The authority check happens when the `RoutedExecutor` is **constructed**, not when an order is
sent. A process that could not legitimately trade cannot assemble the object that would.

---

## Adapters and what each requires

| adapter | `requires` | reaches |
|---|---|---|
| `SimulatedAdapter` | `BACKTEST` | nothing; in-memory |
| `IBKRAdapter` | `PAPER` | IB Gateway paper endpoint |
| `IBKRAdapter(live=True)` | `EXECUTION_READY` | IB Gateway live endpoint |
| `ProjectXAdapter(dry_run=True)` | `PRACTICE` | nothing; records what it would send |
| `ProjectXAdapter(dry_run=False)` | `EXECUTION_READY` | TopstepX |
| *base class default* | `EXECUTION_READY` | — an adapter author who forgets gets the safe answer |

IBKR's paper and live endpoints differ only by port. That is far too small a difference to
leave implicit, so the adapter assumes paper and `live=True` is the thing that has to be
written down.

---

## Reaching EXECUTION_READY

Three independent things must be true at once, and **no single edit can supply all three**:

1. **An explicit argument.** `Authority.for_live(..., i_understand_this_is_real_money=True)`.
   Spelled out so it has to be typed, cannot arrive via a `**kwargs` splat from a config file,
   and reads as an assertion in the diff that introduces it.
2. **An environment variable set outside the code.** `QB_LIVE_TRADING_ENABLED` must be
   `1`/`true`/`yes`. A checkout of this repository cannot trade by itself.
3. **An approval file on disk**, at `live/approvals/<venue>-<account>.md`, created by a person
   and naming what was approved. Empty files are refused.

Each alone is an accident waiting to happen: a default is an accident, a stray environment
variable is a stale-shell accident, a file alone is a stale-artefact accident. All three is
three accidents in three places in the same direction.

Approval files are **per venue and per account**, so a signature for a practice account cannot
authorise a funded one. Tested.

`QB_ACCOUNT_MODE` can select any mode up to `PRACTICE`. It **cannot** select
`HUMAN_APPROVAL` or `EXECUTION_READY` — configuration that could grant live execution makes
every deployment one typo away from trading.

This generalises a convention the repository already had and which has held: the equity sleeve
requires a human-created `live/APPROVED_PAPER.md`.

---

## Dry run is the absence of a code path

In `ProjectXAdapter` dry run does not mean "build the request and don't send it". The
transport is never reached; the request body is recorded in `would_send` and that is the whole
operation. A `send=False` parameter threaded through a live code path is one boolean away from
being wrong. Not having the code path is not.

`submit()` on a fully forced-open adapter — dry run off, state hand-set to `EXECUTION_READY` —
raises `NotPermitted("live order submission is not implemented")`. That is deliberate and
tested: an implementation present but gated is one edit from an accident, whereas an
implementation absent is not.

---

## Secrets

Credentials are read from `PROJECTX_USERNAME` / `PROJECTX_API_KEY` **only** — never an
argument, a repository file, or a config object that might be logged.

`Credentials` and `Session` override `__repr__` and `__str__`, because a dataclass ends up
inside an exception, a log line or a debugger sooner or later. Tests assert the secret is
absent from `repr`, `str`, f-strings, `format()`, event payloads, and the adapter's
`describe()`.

A transport failure is re-raised **without its cause chain**: a transport error can carry the
request body, and the request body carries the API key. `e.__cause__ is None` is asserted.

A standing test scans every `.py` file under `quant_brain/` for secret-shaped strings
(`sk-…`, JWT `eyJ…`, `Bearer …`) so nothing pasted in while debugging survives to a commit.

---

## Failure is terminal

`halt()` sets `HALTED` and nothing in the module clears it — a halt requires a person and a
restart. Every subsequent operation raises. Halts on: transport failure during authentication,
a venue rejection, and success reported with no token (a venue that says yes and sends nothing
is a venue we do not understand).

`reconcile()` **refuses** rather than returning an empty position set. An empty stub would look
like agreement with any local state, which is the most dangerous possible placeholder for a
reconciliation function.

---

## What is safe to point at a Topstep Practice account today

Nothing yet, and the honest reason is that the API surface is only partly verified.

Verified against
<https://gateway.docs.projectx.com/docs/getting-started/authenticate/authenticate-api-key/>
(retrieved 2026-09-13):

- `POST https://api.topstepx.com/api/Auth/loginKey`, body `{userName, apiKey}`
- returns `{token, success, errorCode, errorMessage}`
- token valid 24 hours, then HTTP 401; a Validate Session endpoint refreshes it

That is enough to authenticate and to keep a session alive. It is **not** enough to place,
query, modify or reconcile an order, and those endpoints are recorded as UNKNOWN in
`API_UNKNOWNS.md` rather than guessed at.

## What would still be required before any live execution

1. The order, position, contract, history and fill endpoints verified against official
   documentation, with request and response shapes.
2. The SignalR hub URLs and every event name, so fills are observed rather than polled.
3. `reconcile()` implemented against the real position endpoint, and exercised against a
   deliberately wrong local state to prove it halts.
4. Native protective orders (§22): a position is not "protected" until a stop has been
   **verified to exist at the venue**, not merely submitted.
5. Rate limits, so a reconnect storm cannot get the account throttled or flagged.
6. A prop-firm risk engine wired into the chain, enforcing the MLL, DLL and contract caps
   ahead of the venue rather than relying on it.
7. Sustained practice-account operation, reviewed by a person.
8. An approval file, an environment variable, and an explicit argument — the three conditions
   above.

None of those are close to done, and the architecture is deliberately shaped so that being
partway through them cannot accidentally become live trading.
