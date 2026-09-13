# ProjectX Gateway API — what the documentation does not settle

Companion to [`API.md`](./API.md). **Retrieval date: 2026-09-13.**

Every question below was checked against all three sources and is genuinely unanswered by them.
Each entry names the page(s) actually read, so nobody re-reads them hoping for a different answer.

Sources, as in `API.md`:

- **S1** — https://gateway.docs.projectx.com/ (all 23 pages read; inventory in `API.md` §12)
- **S2** — https://api.topstepx.com/swagger/v1/swagger.json (full OpenAPI 2.0 spec)
- **S3** — https://help.topstep.com/en/articles/11187768-topstepx-api-access

Resolving these means an experiment against a **Practice account** (S3: there is no sandbox), or
asking in `#api-trading` on the Topstep Discord / `dashboardapi@topstep.com`. Nothing here should
be resolved by guessing.

---

## Tier 1 — blocking. An implementation cannot be correct without these.

### U1. Can a funded/live Topstep account place, modify or cancel orders through this API at all?

`/docs/api-reference/order/order-cancel` states verbatim: *"Live accounts not supported — The
account is a live or brokerage account. This endpoint only supports simulated accounts,"* and
*"Only simulated accounts that are not following another account can cancel orders through this
endpoint."* `/docs/api-reference/positions/close-positions-partial` independently glosses its
`errorCode 9 AccountRejected` as *"The account is not allowed to close positions (live
accounts)."*

- Does the same restriction apply to `POST /api/Order/place` and `POST /api/Order/modify`? Their
  pages do not say, but both define an `AccountRejected` error code.
- Does it apply to `POST /api/Position/closeContract`? Its page has no error table at all; S2
  gives it `8 = AccountRejected` with no gloss.
- In Topstep's own vocabulary, is an Express Funded Account "simulated" or "live" for this
  purpose? Is a Combine/Evaluation account "simulated"? S3 says to test on a Practice account and
  never maps its account tiers onto the API's simulated/live distinction.

**Why it blocks:** if cancel is unavailable on the account tier you intend to trade, an automated
strategy cannot manage resting orders and the whole design changes. Checked:
`/docs/api-reference/order/order-cancel`, `/order-place`, `/order-modify`,
`/positions/close-positions`, `/positions/close-positions-partial`, S2 error enums, S3 in full.

### U2. Exactly what does `POST /api/Order/searchOpen` omit, and is `/api/Order/v2/query` usable?

S2's summary for `searchOpen` says verbatim: *"Does not include Suspended bracket children — use
`/v2/query` with `Statuses: [Open, Suspended]` to fetch those alongside open orders."* S1's
`searchOpen` page does not mention this.

- Are `PendingCancellation (7)` and `Pending (6)` orders also excluded from `searchOpen`? S2 says
  only "orders with Open status", implying yes, but does not say so.
- `/api/Order/v2/query` has **no documentation page whatsoever**. What is the default `pageSize`?
  The maximum? Is `pageOffset` 0-based or 1-based? What is the default sort when `sortBy` is
  omitted?
- The S2 summary writes the filter key as `Statuses` (capital S) while the `GatewayOrderFilter`
  schema defines `statuses`. Which casing does the server accept? Is the JSON binding
  case-insensitive?
- Is `/v2/query` rate-limited as "all other endpoints" (200/60s), or does it have its own budget?

**Why it blocks:** reconciling working orders is the core safety loop of any live runner. Using
`searchOpen` and believing it is complete produces a false "position is unprotected" or a false
"nothing resting" — either of which can double a position. Checked:
`/docs/api-reference/order/order-search-open`, `/order-search`, the whole S2 `Order` tag,
`/docs/getting-started/rate-limits`.

### U3. How do bracket/OCO orders relate to each other, and what does `Suspended` mean?

S2's `OrderModel` carries `parentOrderId` (int64) and `linkedOrderId` (int64). **Neither field
appears in any S1 example, any S1 field table, or the `GatewayUserOrder` payload table**, and
S2 carries no property descriptions at all.

- Which of the two links a bracket child to its entry order, and which links the OCO siblings to
  each other?
- When one leg of an OCO fills, does the other arrive as `Cancelled (3)` on the user hub, or does
  it simply stop appearing?
- `OrderStatus 8 = Suspended` exists only in S2's enum (S1's C# block on `/docs/realtime/` stops
  at `6 = Pending`). What suspends a bracket child, and what un-suspends it? Presumably a bracket
  is Suspended until its parent fills — but that is inference.
- Does the user hub ever emit `status: 7` or `status: 8`? S1's realtime enum list does not contain
  them, so a client written from S1 alone will fail to decode them.

**Why it blocks:** you cannot tell "my stop is live" from "my stop is suspended" without this, and
you cannot pair an OCO to cancel the survivor. Checked: `/docs/api-reference/order/order-place`
(bracket section), `/order-search`, `/order-search-open`, `/docs/realtime/`, S2 `OrderModel` and
`OrderStatus`.

### U4. Does a `GatewayUserPosition` event announce a *flat* position, and how?

`/docs/realtime/` documents the payload but never the lifecycle. When a position is fully closed:

- Is an event emitted with `size: 0`?
- Is one emitted with `type: 0 (Undefined)`?
- Or is no event emitted at all, so the only signal is the absence of the contract from a later
  `POST /api/Position/searchOpen`?

Related and equally unanswered: is `GatewayUserPosition` a full snapshot of the position or a
delta? Does it fire on every fill that changes `averagePrice`, or only on open/close?

**Why it blocks:** a runner that tracks position state from the hub will hold a phantom position
forever if "flat" is signalled by silence. Checked: `/docs/realtime/` in full,
`/docs/api-reference/positions/search-open-positions`.

### U5. Is there any documented way to cancel all orders / flatten everything?

There is no `Order/cancelAll`, no `Position/closeAll`, and no account-level flatten in S1 or in
S2's complete path list (21 operations, all enumerated in `API.md` §7).

- Is flattening genuinely "iterate `searchOpen`, cancel each; iterate `searchOpen` positions,
  `closeContract` each"?
- If so, what happens to bracket children when their parent is cancelled — are they cancelled
  automatically, or do they need individual cancels?
- Is there a documented kill-switch of any kind, given S3's warning that *"Orders executed via
  the API are final — no review, adjustment, or reversal"*?

**Why it blocks:** the HALT path of any live runner depends on this, and iterating is racy against
new fills. Checked: full S2 path list, all S1 order and position pages.

---

## Tier 2 — significant. Wrong assumptions here cause silent data or execution errors.

### U6. Rate limiting mechanics

`/docs/getting-started/rate-limits` gives only the two budgets (50/30s for `retrieveBars`,
200/60s for everything else) and the 429 status.

- Fixed window or sliding window?
- Scoped per token, per user, per account, or per IP? S3 says one key covers every account under
  the profile — does that mean all accounts share one 200/60s budget?
- Is a `Retry-After` header returned? Any `X-RateLimit-*` headers?
- What is the response *body* of a 429 — the standard envelope, `ProblemDetails`, or plain text?
- Do SignalR hub `invoke` calls count against the REST budget? Does inbound event volume?
- Is there a separate connection limit on the hubs (concurrent connections, subscriptions per
  connection)?

Checked: `/docs/getting-started/rate-limits`, `/docs/realtime/`, S2 (no rate-limit metadata), S3
(mentions only "fair-use limits" and "If you're being rate limited, back off and retry").

### U7. Historical bars: alignment, ordering guarantee, and the two undocumented fields

From `/docs/api-reference/market-data/retrieve-bars` and S2's `AggregateBarModel`:

- The example returns bars **newest-first**, but no prose states this is guaranteed. Is descending
  order contractual?
- The example requests `2024-12-01`→`2024-12-31` with `limit: 7` and gets seven bars from
  `2024-12-20` — so `limit` truncates from the end of the window. Is that guaranteed, or is it an
  artefact of that dataset?
- `AggregateBarModel` has two fields absent from every example and from S1 entirely:
  **`d` (string, `date` format)** and **`k` (int64)**. What are they? Trading date? Bar key?
- Are daily/weekly/monthly bars aligned to UTC or to the exchange session? A CME equity-index
  "day" does not start at 00:00 UTC.
- What does `includePartialBar: true` return for `unit: 4 (Day)` mid-session?
- Is `unit: 7 (Tick)` (S2 only) actually implemented? If so, what does `unitNumber` mean — ticks
  per bar?
- What is the earliest available history, per contract or overall? Nothing in S1/S2/S3 says.
- Does `live: false` return a different price series (sim feed) from `live: true`, or the same
  data under a different entitlement?

Checked: `/docs/api-reference/market-data/retrieve-bars`, S2 `RetrieveBarRequest` /
`AggregateBarResponse` / `AggregateBarUnit`.

### U8. What does the `live` boolean actually select?

It appears on `Contract/search` ("using the sim/live data subscription"), `Contract/available`
("Whether to retrieve live contracts") and `History/retrieveBars` ("using the sim or live data
subscription") — three different glosses, and `Contract/searchById` has no such flag at all.

- Does `live` select a **data entitlement** (sim feed vs real-time feed) or a **contract set**?
- What happens if you request `live: true` without a real-time market-data subscription — an
  error, an empty list, or delayed data returned silently?
- Which value should a Practice account use? S3 says a Practice account uses the "same endpoints
  and real-time hubs" but never mentions this flag.
- Is a contract ID returned under `live: false` valid for order placement, and vice versa?

**Why it matters:** getting this wrong means backtesting on one price series and trading another.
Checked: all three market-data pages, `/docs/getting-started/placing-your-first-order` (which uses
`live: false` for `Contract/available` while the reference page's own example uses `live: true`),
S3.

### U9. Market depth: how do you actually build a book?

`/docs/realtime/` documents the `GatewayDepth` payload and the 12-value `DomType` enum, and then
stops.

- What is the difference between `volume` ("total volume at this price level") and
  `currentVolume` ("current volume at this price level")? The example has `volume: 10,
  currentVolume: 5` for a single level.
- Which field should be written into the book?
- What does `Reset (6)` clear — the whole book, or one side?
- `Trade (5)` and `Fill (11)` both appear in a *depth* enum. How do they differ from each other
  and from the separate `GatewayTrade` event?
- What do `Low (7)` and `High (8)` mean inside a DOM stream — session extremes delivered on the
  depth channel?
- How do `BestAsk (3)`/`BestBid (4)` relate to `NewBestBid (9)`/`NewBestAsk (10)`?
- Is a snapshot delivered on subscribe, or only deltas from that moment?
- How many levels deep? Is `GatewayDepth` one message per level, or can `data` be an array?
- Does the account's market-data entitlement (Level 1 vs Level 2 — S3 links a separate article)
  gate this event entirely?

Checked: `/docs/realtime/` in full. This is the least-documented surface in the API.

### U10. SignalR connection contract

Everything known comes from two JavaScript samples on `/docs/realtime/`; there is no protocol
section.

- The samples pass the token **both** as `?access_token=` and via `accessTokenFactory`. Is the
  query parameter mandatory given `skipNegotiation: true`? Does an `Authorization: Bearer` header
  work instead?
- What happens to an open hub connection when the 24h token expires — is it dropped, or does it
  survive? Can the token be refreshed on a live connection, or must you reconnect?
- Is `skipNegotiation: true` required, or merely what the samples chose? Do the LongPolling /
  SSE transports work?
- Which SignalR **protocol** — JSON or MessagePack? Which server/hub protocol version? This
  matters for any non-`@microsoft/signalr` client (Python `signalrcore`, for instance).
- Are there server-side keepalive / handshake timeouts to configure? The samples set only a
  client `timeout: 10000`.
- Can one user-hub connection subscribe to **multiple** `accountId`s? The sample uses a single
  "currently selected/visible account ID". Can one market-hub connection subscribe to multiple
  contracts?
- Is there a documented event for subscription success/failure, or for server-side errors? None is
  listed.
- On `onreconnected` the sample re-subscribes — but does the server replay missed events, or is
  the gap simply lost? (Assume lost; not stated.)

Checked: `/docs/realtime/` in full, `/docs/getting-started/connection-urls`,
`/docs/getting-started/authenticate/authenticate-api-key`.

### U11. Order modify semantics

`/docs/api-reference/order/order-modify` lists four optional fields and never says how they are
applied.

- Does omitting `size` (or sending `null`) leave the size unchanged, or clear it?
- Can a modify change an order's `type` or `side`? Neither field is in the request.
- Can a bracket child be modified directly, or only through its parent?
- What is the behaviour of a modify against an order that filled between your read and your write
  — `OrderNotFound (2)` or `Rejected (3)`?
- Is a modify atomic, or can a partial application occur (price accepted, size rejected)?

Checked: `/docs/api-reference/order/order-modify`, S2 `ModifyOrderRequest`.

### U12. `customTag` semantics

`/docs/api-reference/order/order-place` says only *"An optional custom tag for the order. Must be
unique across the account,"* and the place-order page notes a duplicate tag is one of the
`errorCode 2` rejections.

- Unique **forever**, or unique among open orders? If forever, a restart-safe idempotency key
  scheme must never reuse a value.
- Maximum length? Allowed character set? S2 gives a bare `string` with no `maxLength`.
- Can it be used as an idempotency key — i.e. does re-sending the same `customTag` return the
  original `orderId`, or reject?
- Is it echoed on bracket children created from `stopLossBracket` / `takeProfitBracket`?

Checked: `/docs/api-reference/order/order-place`, `/order-search`, S2 `PlaceOrderRequest`.

---

## Tier 3 — matters for a production runner, but has a safe conservative default.

### U13. Trailing stops: `trailPrice` vs `trailDistance` on read-back

`/docs/api-reference/order/order-place` states the read-back `trailPrice` holds *"the trail
distance expressed in price (ticks x tickSize), not the price level that was submitted."* S2's
`OrderModel` has **both** `trailPrice` (decimal) and `trailDistance` (int32).

- Is `trailDistance` the same quantity in ticks? Strongly implied, never stated.
- Neither field appears in any S1 order-search example, nor in the `GatewayUserOrder` payload
  table. Does the hub emit them?
- Does the modify endpoint's missing maximum-distance check (S1 says so explicitly) mean a
  >1000-tick trail set via modify actually functions, or does it fail later at the engine?

Safe default: read `trailDistance` if present, treat `trailPrice` on a read as a distance, never
round-trip a read `trailPrice` back into a write.

### U14. Is `OrderType 3 = StopLimit` placeable?

The `type` enum on `/docs/api-reference/order/order-place` lists 1, 2, 4, 5, 6, 7 — skipping 3.
S2's `OrderType` and S1's own C# block on `/docs/realtime/` both define `3 = StopLimit`. S1 says
`errorCode 2` covers "unsupported order type".

- Is the omission deliberate (StopLimit not accepted on this endpoint) or a docs oversight?
- If accepted, does it need both `limitPrice` and `stopPrice`?
- Same question for `6 = JoinBid` / `7 = JoinAsk`: they are listed as placeable but nothing
  anywhere describes their behaviour, or which price fields they require.

Safe default: use only `1 = Limit`, `2 = Market`, `4 = Stop`, `5 = TrailingStop`.

### U15. Account and contract metadata gaps

- `TradingAccountModel` has no currency, no equity/margin fields, and no account-type field
  beyond `simulated`. How do you tell a Practice account from an Evaluation account from an
  Express Funded account through the API? (`name` is the only candidate and it is free text.)
- `balance` — is it cash balance, net liquidation, or day-start balance? Not stated anywhere.
- Is there any API surface for account risk rules (daily loss limit, trailing drawdown, max
  position)? None exists in S2's 21 operations. Presumably enforced server-side and invisible.
- `ContractModel` has no expiry date, no exchange, no currency, no contract multiplier (only
  `tickSize` and `tickValue`), no trading-hours/session calendar, and no minimum/maximum order
  size. Is there any documented source for session hours?
- Is the `CON.F.US.<root>.<monthCode><yearDigit>` ID grammar contractual? Nothing states it. Is
  there a documented rollover signal beyond polling `activeContract`?

Checked: `/docs/api-reference/account/search-accounts`, all three contract pages, full S2
definitions list.

### U16. Fees, commissions and P&L conventions

`HalfTradeModel` (S2) has both `fees` (required) and `commissions` (optional). Every S1 example
shows only `fees`.

- Is `fees` inclusive of `commissions`, or are they disjoint components?
- Is `profitAndLoss` gross or net of `fees`?
- Is `profitAndLoss` in account currency? Which currency? Not stated.
- What sets `voided: true`, and does a voided trade reverse an earlier `profitAndLoss`?
- S2 marks `profitAndLoss` **required** while S1's example shows `null` with the comment *"a null
  value indicates a half-turn trade"*. Confirmed nullable in practice? (Treat as nullable.)
- Is `Trade/search` paginated or capped? No `limit` parameter and no stated maximum — what happens
  on a wide time window?

Checked: `/docs/api-reference/trade/trade-search`, S2 `HalfTradeModel` / `SearchTradeRequest`,
`/docs/realtime/` `GatewayUserTrade`.

### U17. Undocumented endpoints

Five operations exist in S2 with no prose page anywhere:

| Endpoint | What is unknown |
|---|---|
| `POST /api/Auth/logout` | Does it invalidate only the calling token, or every token for the user? Given tokens are shared across a runner's REST and hub connections, calling it could kill a live session. |
| `POST /api/Auth/loginApp` | `deviceId`, `appId`, `verifyKey` are undescribed. How is an application registered? Is the flow available to Topstep users at all, given S1's *"API key is the only supported way"* and the page's 301? |
| `POST /api/Order/searchById` | Behaves as expected? Any rate-limit distinction from `Order/search`? |
| `POST /api/Order/v2/query` | See U2. |
| `GET /api/Status/ping` | Response body has **no schema** in S2. Does it require authentication? Does it count against the rate limit? Is it a usable liveness probe? |

### U18. Session/token edge cases

- S1's authenticate page says refresh *"with Validate Session **before it expires**"*; the
  validate-session page says *"If your token has expired, you must re-validate it to receive a new
  token."* Which is right — does `/api/Auth/validate` work on an already-expired token, or does it
  return `3 = ExpiredToken`?
- Does calling `validate` extend the existing token's life, or does `newToken` start a fresh 24h?
- Does `newToken` invalidate the old one? (`loginKey` explicitly does not invalidate prior tokens;
  `validate` says nothing.)
- Is the returned JWT's `exp` claim reliable for scheduling a refresh? The token is a JWT (S1 says
  so) but nothing documents its claims.
- What is the difference between `ValidateErrorCode` `1 = InvalidSession` and `2 = SessionNotFound`?

Checked: `/docs/getting-started/authenticate/authenticate-api-key`,
`/docs/getting-started/validate-session`, S2 `ValidateResponse` / `ValidateErrorCode`.

### U19. Quote and trade stream semantics

- `GatewayQuote` carries `bestBid`/`bestAsk` but **no bid/ask sizes**. Is size only obtainable from
  `GatewayDepth`?
- Is `GatewayQuote` throttled/conflated, or is every book change delivered?
- It has both `lastUpdated` and `timestamp`, undifferentiated. Which is the exchange time and
  which is the server time?
- `open`/`high`/`low`/`volume` are "session" values — which session boundary, in which timezone?
- `change`/`changePercent` are "since previous close" — which close?
- Are `GatewayQuote` fields ever partial (only the changed ones populated), or always a full
  snapshot?
- `GatewayTrade`'s handler signature is `(contractId, data)` and the documented `data` is a single
  object. Can it be an array of prints under load?
- Does `GatewayTrade` include exchange trade conditions or aggressor confidence? Only
  `TradeLogType` (Buy/Sell) is present.
- Is there a documented data-entitlement gate (Level 1 vs Level 2, per S3's linked article) on
  quotes vs depth?

Checked: `/docs/realtime/` in full.

### U20. Topstep policy questions that gate deployment shape

All from S3:

- **HFT is prohibited** but never defined — no order-per-second threshold, no minimum holding
  period, no message-to-fill ratio. What rate of API activity is considered HFT?
- The VPS/VPN prohibition says trading *"must originate from your personal device"*. Does a
  desktop at home running unattended 24/7 while nobody is present count as "your personal device"?
  Is an always-on personal workstation acceptable where a rented VPS is not?
- The allowed/not-allowed table permits "receiving copies of your own fills, positions, and P&L"
  on a private server but forbids "any automated trigger that can reach the order endpoints".
  Where does a private server that *computes a signal* and hands it to the personal device for
  execution fall?
- Does the prohibition affect the user hub (read-only) as well as REST order calls? The table
  implies read-only is fine.
- S3 says API access is "governed by the ProjectX Terms of Use, including fair-use limits" —
  the fair-use limits are not quantified anywhere in S1, S2 or S3.

**These are policy, not protocol, and should be settled with Topstep in writing before any
unattended deployment** given S3's *"Running automation on a VPS can result in account suspension
or removal from the program."*

---

## Documentation defects observed (not questions — just wrong, and noted so nobody trusts them)

| Page | Defect |
|---|---|
| `/docs/api-reference/account/search-accounts` | cURL sample reads `curl -X 'undefined'`. Method is POST. |
| `/docs/api-reference/market-data/retrieve-bars` | Parameter table types `contractId` as `integer`; its own example and S2 both use a string. |
| `/docs/api-reference/order/order-place` | `type` enum list skips `3 = StopLimit`, which exists in S2 and in S1's own realtime enum block. |
| `/docs/realtime/` | `OrderStatus` C# block stops at `6 = Pending`; S2 defines `7 = PendingCancellation` and `8 = Suspended`. |
| `/docs/api-reference/account/search-accounts` | Response example omits `simulated`, which S2 marks required. |
| `/docs/api-reference/positions/search-open-positions` | Response example omits `contractDisplayName` (S2). |
| `/docs/api-reference/trade/trade-search` | Response example omits `commissions` (S2). |
| `/docs/api-reference/order/order-search`, `/order-search-open` | Examples omit `trailDistance`, `trailPrice`, `parentOrderId`, `linkedOrderId` (all in S2's `OrderModel`). |
| `/docs/api-reference/order/order-search-open` | Does not mention the Suspended-bracket-children exclusion that S2's own summary calls out. |
| Every authenticated reference page | cURL samples omit the `Authorization` header, so as printed they would return 401. |
| `/docs/api-reference/positions/close-positions` | No error-code table at all; the neighbouring partial-close table is **not** interchangeable (codes are shifted). |
| `/ConnectionURLs` | Listed in `sitemap.xml`, returns HTTP 200, but renders only "Loading environment…" with no content. |
| `/docs/getting-started/authenticate/authenticate-as-application` | Withdrawn (HTTP 301) while `POST /api/Auth/loginApp` still exists in the live spec. |
