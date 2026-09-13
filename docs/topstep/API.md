# ProjectX Gateway API — implementation reference (TopstepX)

**Retrieval date for every claim below: 2026-09-13.**

Every statement in this document is sourced. Where a source does not settle a question, the
answer is written as `UNKNOWN` and the page that was checked is named. Open questions are
collected in [`API_UNKNOWNS.md`](./API_UNKNOWNS.md).

> **No credentials appear in this file.** The official docs print a template username and a
> template API key in their cURL samples. Those literal values are deliberately replaced here
> with `<REDACTED>` / environment-variable names. Nothing in this repo should ever carry a real
> key; see the secrets rule in `CLAUDE.md`.

---

## 1. Sources

| # | Source | URL | Authority |
|---|---|---|---|
| S1 | ProjectX Gateway API docs (Docusaurus site) | https://gateway.docs.projectx.com/ | Primary / authoritative |
| S2 | ProjectX Gateway API OpenAPI (Swagger 2.0) spec | https://api.topstepx.com/swagger/v1/swagger.json | Primary machine-readable. Topstep's own help page (S3) links this as the "Full endpoint reference". Served publicly, no auth; no trading call was made. |
| S3 | Topstep help centre, "TopstepX™ API Access" | https://help.topstep.com/en/articles/11187768-topstepx-api-access | Topstep's statement of access, cost, restrictions |

The complete S1 page inventory was taken from https://gateway.docs.projectx.com/sitemap.xml
(retrieved 2026-09-13) and cross-checked against every `/docs/category/*` sidebar. **S1 has
exactly 23 pages**; there are no deep pages beyond those listed in §12.

Where S1 and S2 disagree, both readings are shown and the conflict is raised as an UNKNOWN.

---

## 2. Access, cost and restrictions (Topstep)

All of §2 is from **S3**, https://help.topstep.com/en/articles/11187768-topstepx-api-access.

- API access is "powered by ProjectX and billed separately from your Topstep subscription."
- **Cost:** verbatim — *"API Access is $29/month. Topstep Traders get 50% off with code topstep —
  that's $14.50/month, valid every month with no end date."* Billing appears on statements as
  "Sim2Funded Solutions".
- **Onboarding is four ordered parts**, and part 4 fails if part 3 is skipped:
  1. Create a ProjectX Dashboard account at `dashboard.projectx.com`.
  2. Subscribe: Dashboard → Subscriptions → ProjectX API Access (promo code `topstep`).
  3. **Link** the subscription to the TopstepX profile: TopstepX → Settings → API tab →
     ProjectX Linking → Add Link. Verbatim: *"Subscribing is not the same as linking … without
     it, Part 4 will fail with the error `User lacks subscription`."*
  4. Generate the key: TopstepX → Settings → API tab → Add API Key.
- **Key blast radius**, verbatim: *"Your API key grants full trading access to every eligible
  account under your profile."*
- **No sandbox.** Verbatim: *"Is there a sandbox environment for testing? No. There is currently
  no sandbox environment available. To test your strategy, use a Practice account instead — same
  endpoints and real-time hubs, no risk to an Evaluation account."*
- **One subscription covers all accounts.** Verbatim: *"One subscription and one API key cover
  every eligible account under your ProjectX Dashboard profile. A single authenticated session
  can manage all of them; you specify the target account Id on each order."*
- **VPS / VPN / remote servers are prohibited for order flow.** Verbatim: *"All trading activity
  must originate from your personal device. The use of VPS, VPNs, and remote servers is
  prohibited by Topstep's Terms of Use. Running automation on a VPS can result in account
  suspension or removal from the program."* S3 draws the line at order transmission:

  | Allowed on a private server | Not allowed on a private server |
  |---|---|
  | Historical data storage | Placing, modifying, or cancelling orders |
  | Research and backtesting | Any automated trigger that can reach the order endpoints |
  | Logging and analytics | Routing or relaying orders on your behalf |
  | A read-only dashboard | |
  | Receiving copies of your own fills, positions, and P&L | |

  Verbatim: *"The line is order transmission: your server can watch and record, but it cannot
  trade."*
- **Bots are allowed, HFT is not.** Verbatim: *"Custom automated strategies and bots are allowed
  via the TopstepX / ProjectX API, subject to standard platform rules and our prohibition on
  highfrequency trading (HFT)."* S3 gives no quantitative definition of HFT — see UNKNOWNS.
- **Orders are final.** Verbatim: *"Orders executed via the API are final — no review,
  adjustment, or reversal."*
- Topstep provides no technical support for API implementation.

---

## 3. Connection URLs

Source: **S1** https://gateway.docs.projectx.com/docs/getting-started/connection-urls
(retrieved 2026-09-13). The page is reproduced in full below — it contains nothing else.

```
API Endpoint: https://api.topstepx.com
User Hub:     https://rtc.topstepx.com/hubs/user
Market Hub:   https://rtc.topstepx.com/hubs/market
```

S2 confirms `host: api.topstepx.com`, `schemes: ["https"]`, and no `basePath` (paths are absolute
from the root, e.g. `/api/Order/place`).

These are the **TopstepX** URLs. S1 is a multi-firm document ("You will also need the connection
URLs for your firm"); other ProjectX firms use different hosts. Some search-engine snapshots of
S1 still show a stale demo host `https://gateway-api-demo.s2f.projectx.com` in example cURL
blocks — the live pages as retrieved on 2026-09-13 all use `https://api.topstepx.com`.

---

## 4. Conventions

Established across every S1 API-reference page and confirmed by S2.

- **Every endpoint is `POST`** with a JSON body — including all the read/search endpoints. The
  single exception is `GET /api/Status/ping` (S2 only; no S1 page).
- Request `Content-Type: application/json`. S2 `consumes` per operation:
  `["application/json", "text/json", "application/*+json"]`.
- S1's cURL samples send `-H 'accept: text/plain'`. S2 declares global
  `produces: ["text/plain", "application/json", "text/json"]`. Response bodies are JSON in every
  documented example.
- **Auth:** bearer token in the `Authorization` header. S1 (authenticate page) says verbatim:
  *"Send it as a bearer token on every other request."* Note: **S2 declares no
  `securityDefinitions` and no `security` block at all**, so the exact header spelling is not in
  the machine-readable spec; S1 is the only source. S1's cURL samples for the authenticated
  endpoints omit the `Authorization` header entirely (a docs defect — those samples would 401).
- **Response envelope.** Every response carries `success` (bool, required), `errorCode` (integer
  enum, required), `errorMessage` (string, nullable), plus one payload field. Each endpoint has
  its **own** `errorCode` enum — the integers are *not* comparable across endpoints. See §9.4.
- **HTTP status.** Business failures return **HTTP 200** with `success: false`. S1 authenticate
  page, verbatim: *"A failed login still returns HTTP 200."* Observed non-200s: `400` for a login
  body missing `userName`/`apiKey` (S1) and for `/api/Order/v2/query` validation (S2:
  `400 → ProblemDetails`); `401` for a missing/expired token (S1 error tabs on every reference
  page render as "Error: response status is 401"); `429` for rate limiting (S1).
- **Timestamps** are ISO-8601 with offset, e.g. `"2025-07-18T21:00:01.268009+00:00"` (S1 order
  search) or `"2025-01-20T15:47:39.882Z"` (S1 trade search). Both forms appear in official
  samples.
- **Prices** are decimals, serialised in samples with nine fractional digits
  (`6335.250000000`).

---

## 5. Authentication

### 5.1 Authenticate with API key — `POST /api/Auth/loginKey`

Source: **S1** https://gateway.docs.projectx.com/docs/getting-started/authenticate/authenticate-api-key
and **S2** (`Auth_LoginKey`, `LoginApiKeyRequest` → `LoginResponse`).

Full path: `POST https://api.topstepx.com/api/Auth/loginKey`

Request (`LoginApiKeyRequest`):

| Field | Type | Required | Meaning (S1, verbatim) |
|---|---|---|---|
| `userName` | string | **required** | "The username you use to sign in to your firm's trading platform. This is not your email address and not a trading account name or ID. Case does not matter." |
| `apiKey` | string | **required** | "An API key generated from your firm's trading platform. Keys are long random strings. Copy the whole value exactly as shown when you generate it." |

```bash
curl -X POST 'https://api.topstepx.com/api/Auth/loginKey' \
  -H 'accept: text/plain' \
  -H 'Content-Type: application/json' \
  -d "{\"userName\": \"$PROJECTX_USERNAME\", \"apiKey\": \"$PROJECTX_API_KEY\"}"
```

*(S1 prints literal template credential values here; they are replaced with env-var references.
The rest of the invocation is verbatim from S1.)*

Response (`LoginResponse`) — S1 success example verbatim except the token value:

```json
{
    "token": "<REDACTED>",
    "success": true,
    "errorCode": 0,
    "errorMessage": null
}
```

S2 field list: `success` bool (required), `errorCode` `LoginErrorCode` (required),
`errorMessage` string (nullable), `token` string (nullable).

Failure example (S1, verbatim):

```json
{
    "token": null,
    "success": false,
    "errorCode": 3,
    "errorMessage": null
}
```

**Only supported login.** S1 states verbatim: *"Logging in with an API key is the only supported
way to obtain a token."*

`LoginErrorCode` — S2 gives the **complete** enum (11 values); S1 documents only the 4 reachable
via key login. Merged, with S1's cause/remedy text:

| Code | Name (S2) | Documented on S1? | S1 `errorMessage` | S1 cause / remedy |
|---|---|---|---|---|
| 0 | `Success` | implicit | `null` | — |
| 1 | `UserNotFound` | no | UNKNOWN | UNKNOWN — S1 does not list it |
| 2 | `PasswordVerificationFailed` | no | UNKNOWN | UNKNOWN — password flow only |
| 3 | `InvalidCredentials` | **yes** | `null` | "The userName and apiKey pair did not match an active key … Confirm you are sending your platform login username. Generate a fresh key in the platform, copy it exactly, and retry." |
| 4 | `AppNotFound` | no | UNKNOWN | UNKNOWN — application flow only |
| 5 | `AppVerificationFailed` | no | UNKNOWN | UNKNOWN — application flow only |
| 6 | `InvalidDevice` | no | UNKNOWN | UNKNOWN — application flow only |
| 7 | `AgreementsNotSigned` | **yes** | `"Please log into the ProjectX platform and complete the required agreements"` | "Sign in to the trading platform, accept the pending agreements, then retry." |
| 8 | `UnknownError` | no | UNKNOWN | UNKNOWN |
| 9 | `ApiSubscriptionNotFound` | **yes** | `null` | "Your user does not have an active subscription, so API tokens cannot be issued. Confirm your subscription with your firm." |
| 10 | `ApiKeyAuthenticationDisabled` | **yes** | `null` | "Your firm has turned off API key login. Contact your firm." |

S1, verbatim on HTTP status: *"A failed login still returns HTTP 200. Read `success` and
`errorCode` from the body to find out what went wrong. The one exception is a request body
missing `userName` or `apiKey`, which is rejected with HTTP 400 before any login check runs."*

Key management on TopstepX (S1): Settings → API at `topstepx.com/settings?tab=api` — create,
reveal/copy, or revoke.

### 5.2 Authenticate as application — `POST /api/Auth/loginApp`

**The S1 documentation page for this flow has been withdrawn.**
`https://gateway.docs.projectx.com/docs/getting-started/authenticate/authenticate-as-application`
returns **HTTP 301** redirecting to `.../authenticate/authenticate-api-key/` (verified
2026-09-13 with a non-following `curl`). It is absent from the sitemap and from the
`/docs/category/authenticate` sidebar. The current S1 text says API key is "the only supported
way to obtain a token."

The endpoint nevertheless still exists in **S2**:

Full path: `POST https://api.topstepx.com/api/Auth/loginApp`
Summary (S2, verbatim): *"Login as the specified user using the specified application."*

Request (`LoginAppRequest`) — all five fields required, all strings:

| Field | Type | Required |
|---|---|---|
| `userName` | string | required |
| `password` | string | required |
| `deviceId` | string | required |
| `appId` | string | required |
| `verifyKey` | string | required |

Response: `LoginResponse`, same shape as §5.1.

**Semantics of `deviceId`, `appId` and `verifyKey`, how an application is registered, and
whether this flow is available to Topstep users at all: UNKNOWN.** No S1 page describes them
(the only page that could have — `authenticate-as-application` — now 301s), S2 carries no
property descriptions, and S3 does not mention it. Do not build on this endpoint.

### 5.3 Validate / refresh session — `POST /api/Auth/validate`

Source: **S1** https://gateway.docs.projectx.com/docs/getting-started/validate-session
and **S2** (`Auth_Validate` → `ValidateResponse`).

Full path: `POST https://api.topstepx.com/api/Auth/validate`
S2 summary, verbatim: *"Validates the current user's session."*

**Request body: none.** S2 declares zero parameters; S1's cURL sends no `-d`. The session is
identified by the bearer token alone.

S1 cURL, verbatim:

```bash
curl -X 'POST' \
  'https://api.topstepx.com/api/Auth/validate' \
  -H 'accept: text/plain' \
  -H 'Content-Type: application/json'
```

*(As printed, this sample omits the `Authorization` header — a docs defect. The token must be
sent for the call to identify a session.)*

Response (`ValidateResponse`) — S1 example verbatim except the token value:

```json
{
  "success": true,
  "errorCode": 0,
  "errorMessage": null,
  "newToken": "<REDACTED>"
}
```

`ValidateErrorCode` (S2, complete): `0 = Success`, `1 = InvalidSession`, `2 = SessionNotFound`,
`3 = ExpiredToken`, `4 = UnknownError`. None of these are described on S1.

Purpose (S1, verbatim): *"Once you have successfully authenticated, session tokens are only valid
for 24 hours. If your token has expired, you must re-validate it to receive a new token."*
Note the tension with the authenticate page, which says to refresh *before* expiry — see
UNKNOWNS.

### 5.4 Logout — `POST /api/Auth/logout`

**S2 only. There is no S1 page for this endpoint.**

Full path: `POST https://api.topstepx.com/api/Auth/logout`
S2 summary, verbatim: *"Logs out the current authenticated user."*
Request body: none (zero parameters). Response `LogoutResponse`:
`success` bool, `errorCode` `LogoutErrorCode`, `errorMessage` string.
`LogoutErrorCode` (S2): `0 = Success`, `1 = InvalidSession`, `2 = UnknownError`.

Whether logout invalidates only the calling token or every token for the user: UNKNOWN.

### 5.5 Token lifetime and reuse

All verbatim from **S1** https://gateway.docs.projectx.com/docs/getting-started/authenticate/authenticate-api-key:

- *"It is valid for 24 hours from the time it is issued. After that, requests fail with HTTP 401
  and you must log in again or refresh it with Validate Session before it expires."*
- *"One token works for every REST request and realtime hub connection you open. You do not need
  to log in per request or per connection."*
- *"Logging in again issues a new token and does not invalidate tokens that are already in use."*
- *"Login requests are rate limited like every other endpoint. See Rate Limits. Log in once and
  reuse the token rather than logging in before each request."*

---

## 6. Rate limits

Source: **S1** https://gateway.docs.projectx.com/docs/getting-started/rate-limits. The page is
short; §6 reproduces all of its substance.

| Endpoint(s) | Limit |
|---|---|
| `POST /api/History/retrieveBars` | **50 requests / 30 seconds** |
| All other Endpoints | **200 requests / 60 seconds** |

Verbatim: *"If you exceed the allowed rate limits, the API will respond with an HTTP 429 Too Many
Requests error. When this occurs, you should reduce your request frequency and try again after a
short delay."*

Verbatim intent: *"The Gateway API employs a rate limiting system for all authenticated requests.
Its goal is to promote fair usage, prevent abuse, and ensure the stability and reliability of the
service."*

Not stated anywhere in S1/S2/S3, therefore UNKNOWN: whether the window is fixed or sliding;
whether the limit is per token, per user, or per IP; whether `Retry-After` or any
`X-RateLimit-*` headers are returned; the body of a 429; whether SignalR hub invocations or
inbound event volume count against any limit.

---

## 7. Endpoint table

Full base: `https://api.topstepx.com`. Every row is `POST` except `Status/ping`.

| Method | Path | Purpose | Request model | Response model | S1 page |
|---|---|---|---|---|---|
| POST | `/api/Auth/loginKey` | API-key login | `LoginApiKeyRequest` | `LoginResponse` | getting-started/authenticate/authenticate-api-key |
| POST | `/api/Auth/loginApp` | Application login | `LoginAppRequest` | `LoginResponse` | **none (page 301s)** — S2 only |
| POST | `/api/Auth/validate` | Refresh/validate session | *(no body)* | `ValidateResponse` | getting-started/validate-session |
| POST | `/api/Auth/logout` | Log out | *(no body)* | `LogoutResponse` | **none** — S2 only |
| POST | `/api/Account/search` | Search accounts | `SearchAccountRequest` | `SearchAccountResponse` | api-reference/account/search-accounts |
| POST | `/api/Contract/search` | Search contracts by text | `SearchContractRequest` | `SearchContractResponse` | api-reference/market-data/search-contracts |
| POST | `/api/Contract/searchById` | Fetch one contract | `SearchContractByIdRequest` | `SearchContractByIdResponse` | api-reference/market-data/search-contracts-by-id |
| POST | `/api/Contract/available` | List available contracts | `ListAvailableContractRequest` | `ListAvailableContractResponse` | api-reference/market-data/available-contracts |
| POST | `/api/History/retrieveBars` | Historical bars | `RetrieveBarRequest` | `RetrieveBarResponse` | api-reference/market-data/retrieve-bars |
| POST | `/api/Order/place` | Place order | `PlaceOrderRequest` | `PlaceOrderResponse` | api-reference/order/order-place |
| POST | `/api/Order/modify` | Modify open order | `ModifyOrderRequest` | `ModifyOrderResponse` | api-reference/order/order-modify |
| POST | `/api/Order/cancel` | Cancel order | `CancelOrderRequest` | `CancelOrderResponse` | api-reference/order/order-cancel |
| POST | `/api/Order/search` | Orders in a time window | `SearchOrderRequest` | `SearchOrderResponse` | api-reference/order/order-search |
| POST | `/api/Order/searchOpen` | Open orders | `SearchOpenOrderRequest` | `SearchOrderResponse` | api-reference/order/order-search-open |
| POST | `/api/Order/searchById` | One order by id | `SearchOrderByIdRequest` | `SearchOrderByIdResponse` | **none** — S2 only |
| POST | `/api/Order/v2/query` | Paginated/filtered order query | `SearchOrdersQueryRequest` | `SearchOrdersQueryResponse` (`400 → ProblemDetails`) | **none** — S2 only |
| POST | `/api/Position/searchOpen` | Open positions | `SearchPositionRequest` | `SearchPositionResponse` | api-reference/positions/search-open-positions |
| POST | `/api/Position/closeContract` | Close whole position | `CloseContractPositionRequest` | `ClosePositionResponse` | api-reference/positions/close-positions |
| POST | `/api/Position/partialCloseContract` | Partial close | `PartialCloseContractPositionRequest` | `PartialClosePositionResponse` | api-reference/positions/close-positions-partial |
| POST | `/api/Trade/search` | Half-turn trade (fill) search | `SearchTradeRequest` | `SearchHalfTradeResponse` | api-reference/trade/trade-search |
| GET | `/api/Status/ping` | API status check | *(none)* | *(no schema in S2)* | **none** — S2 only |

Four endpoints (`loginApp`, `logout`, `Order/searchById`, `Order/v2/query`) plus `Status/ping`
exist in the official spec but have **no prose documentation page**. Treat their semantics as
UNKNOWN beyond the schema.

---

## 8. Endpoint reference

### 8.1 Search for Account — `POST /api/Account/search`

Source: **S1** https://gateway.docs.projectx.com/docs/api-reference/account/search-accounts,
**S2** `Account_SearchAccounts`.

Request (`SearchAccountRequest`):

| Name | Type | Description (S1 verbatim) | Required | Nullable |
|---|---|---|---|---|
| `onlyActiveAccounts` | boolean | "Whether to filter only active accounts." | Required | false |

Response (`SearchAccountResponse`): `accounts: TradingAccountModel[]`, `success`, `errorCode`
(`SearchAccountErrorCode`: **only** `0 = Success`), `errorMessage`.

`TradingAccountModel` (S2 — all six fields required):

| Field | Type |
|---|---|
| `id` | int32 |
| `name` | string |
| `balance` | decimal |
| `canTrade` | boolean |
| `isVisible` | boolean |
| `simulated` | boolean |

S1 success example (verbatim) — note it **omits `simulated`**, which S2 marks required:

```json
{
  "accounts": [
      {
          "id": 1,
          "name": "TEST_ACCOUNT_1",
          "balance": 50000,
          "canTrade": true,
          "isVisible": true
      }
  ],
  "success": true,
  "errorCode": 0,
  "errorMessage": null
}
```

The S1 cURL block for this page literally reads `curl -X 'undefined'` — a docs defect. The method
is `POST` per the page's own "API URL" line and per S2.

`simulated` is the field that distinguishes a Practice account from an Evaluation/funded account.
S3 tells you to test against a Practice account; this flag (plus the live-account restrictions in
§8.8 and §8.15) is how you assert that in code.

### 8.2 Search for Contracts — `POST /api/Contract/search`

Source: **S1** https://gateway.docs.projectx.com/docs/api-reference/market-data/search-contracts.

S1 verbatim: *"Search for contracts. Note: The response returns up to 20 contracts at a time."*

| Name | Type | Description (S1 verbatim) | Required | Nullable |
|---|---|---|---|---|
| `searchText` | string | "The name of the contract to search for." | Required | false |
| `live` | boolean | "Whether to search for contracts using the sim/live data subscription." | Required | false |

Response: `contracts: ContractModel[]` + envelope. `SearchContractErrorCode` has **only**
`0 = Success` (S2).

There is **no pagination parameter** — the 20-result cap cannot be paged past. Use
`/api/Contract/available` for a full list.

`ContractModel` (S2 — all seven fields required):

| Field | Type |
|---|---|
| `id` | string |
| `name` | string |
| `description` | string |
| `tickSize` | decimal |
| `tickValue` | decimal |
| `activeContract` | boolean |
| `symbolId` | string |

### 8.3 Search for Contract by Id — `POST /api/Contract/searchById`

Source: **S1** https://gateway.docs.projectx.com/docs/api-reference/market-data/search-contracts-by-id.

| Name | Type | Description (S1 verbatim) | Required | Nullable |
|---|---|---|---|---|
| `contractId` | string | "The id of the contract to search for." | Required | false |

Response: `contract: ContractModel` (singular) + envelope.
`SearchContractByIdErrorCode` (S2): `0 = Success`, `1 = ContractNotFound`.

S1 example response, verbatim — note `activeContract: false` for an expired March-2025 contract,
so this endpoint resolves historical/rolled contracts:

```json
{
  "contract": {
      "id": "CON.F.US.ENQ.H25",
      "name": "NQH5",
      "description": "E-mini NASDAQ-100: March 2025",
      "tickSize": 0.25,
      "tickValue": 5,
      "activeContract": false,
      "symbolId": "F.US.ENQ"
  },
  "success": true,
  "errorCode": 0,
  "errorMessage": null
}
```

This endpoint takes no `live` flag, unlike the other two contract endpoints.

### 8.4 List Available Contracts — `POST /api/Contract/available`

Source: **S1** https://gateway.docs.projectx.com/docs/api-reference/market-data/available-contracts.

S1 verbatim: *"Lists available contracts based on the provided request parameters."*

| Name | Type | Description (S1 verbatim) | Required | Nullable |
|---|---|---|---|---|
| `live` | boolean | "Whether to retrieve live contracts. This parameter is required and cannot be null." | Required | false |

Response: `contracts: ContractModel[]` + envelope. `ListAvailableContractErrorCode` has **only**
`0 = Success` (S2).

The S1 page prints a long sample list. An excerpt, verbatim, quoted only to fix the ID grammar
and the tick conventions:

| `id` | `name` | `description` | `tickSize` | `tickValue` | `symbolId` |
|---|---|---|---|---|---|
| `CON.F.US.BP6.U25` | `6BU5` | British Pound (Globex): September 2025 | 0.0001 | 6.25 | `F.US.BP6` |
| `CON.F.US.CA6.U25` | `6CU5` | Canadian Dollar (Globex): September 2025 | 0.00005 | 5 | `F.US.CA6` |
| `CON.F.US.DA6.U25` | `6AU5` | Australian Dollar (Globex): September 2025 | 0.00005 | 5 | `F.US.DA6` |
| `CON.F.US.EEU.U25` | `E7U5` | E-mini Euro FX: September 2025 | 0.0001 | 6.25 | `F.US.EEU` |
| `CON.F.US.EMD.U25` | `EMDU5` | E-mini MidCap 400: September 2025 | 0.1 | 10 | `F.US.EMD` |
| `CON.F.US.ENQ.U25` | `NQU5` | E-mini NASDAQ-100: September 2025 | 0.25 | 5 | `F.US.ENQ` |
| `CON.F.US.EP.U25` | `ESU5` | E-Mini S&P 500: September 2025 | 0.25 | 12.5 | `F.US.EP` |
| `CON.F.US.EU6.U25` | `6EU5` | Euro FX (Globex): September 2025 | 0.00005 | 6.25 | `F.US.EU6` |
| `CON.F.US.MNQ.U25` | `MNQU5` | Micro E-mini Nasdaq-100: September 2025 | 0.25 | 0.5 | `F.US.MNQ` |

The full authoritative list must come from the endpoint itself at runtime; the S1 sample is longer
than this excerpt and is a snapshot of one firm's entitlements.

**Contract ID grammar** (inferred from every ID in S1, not stated as a rule anywhere):
`CON.F.US.<root>.<monthCode><yearDigit>`, where `symbolId` is the same string without the `CON.`
prefix and without the expiry suffix (`F.US.ENQ`). The `F` segment presumably means "future".
This grammar is **not documented** — treat contract IDs as opaque strings and resolve them via
`/api/Contract/search` rather than constructing them.

Note also that `name` is an exchange-style short code with a **single-digit year** (`NQU5`),
which is ambiguous across decades.

### 8.5 Retrieve Bars — `POST /api/History/retrieveBars`

Source: **S1** https://gateway.docs.projectx.com/docs/api-reference/market-data/retrieve-bars,
**S2** `History_GetBars`.

S1 verbatim: *"Note: The maximum number of bars that can be retrieved in a single request is
20,000."*
Rate limit for this endpoint alone: **50 requests / 30 seconds** (§6).

Request (`RetrieveBarRequest`) — **every field is Required and non-nullable** in both S1 and S2:

| Name | Type (S1) | Type (S2) | Description (S1 verbatim) |
|---|---|---|---|
| `contractId` | **integer** | **string** | "The contract ID." |
| `live` | boolean | boolean | "Whether to retrieve bars using the sim or live data subscription." |
| `startTime` | datetime | date-time string | "The start time of the historical data." |
| `endTime` | datetime | date-time string | "The end time of the historical data." |
| `unit` | integer | `AggregateBarUnit` | "The unit of aggregation for the historical data." (see below) |
| `unitNumber` | integer | int32 | "The number of units to aggregate." |
| `limit` | integer | int32 | "The maximum number of bars to retrieve." |
| `includePartialBar` | boolean | boolean | "Whether to include a partial bar representing the current time unit." |

> **`contractId` type conflict.** S1's parameter table says `integer`; S1's own cURL example sends
> the string `"CON.F.US.RTY.Z24"`; S2 says `string`. **Send a string.** The `integer` in the S1
> table is a documentation error.

**Unit encoding.** S1 documents six values verbatim:

```
1 = Second
2 = Minute
3 = Hour
4 = Day
5 = Week
6 = Month
```

S2's `AggregateBarUnit` enum has **eight** values — two more than S1 documents:

| Value | Name (S2 `x-enumNames`) | On S1? |
|---|---|---|
| 0 | `Unspecified` | no |
| 1 | `Second` | yes |
| 2 | `Minute` | yes |
| 3 | `Hour` | yes |
| 4 | `Day` | yes |
| 5 | `Week` | yes |
| 6 | `Month` | yes |
| 7 | **`Tick`** | **no** |

A 5-minute bar is `unit: 2, unitNumber: 5`. A 1-hour bar is `unit: 3, unitNumber: 1` (S1's own
example). Whether `unit: 7` (Tick) is functional, and what `unitNumber` means for it, is UNKNOWN.

S1 example request, verbatim:

```json
{
    "contractId": "CON.F.US.RTY.Z24",
    "live": false,
    "startTime": "2024-12-01T00:00:00Z",
    "endTime": "2024-12-31T21:00:00Z",
    "unit": 3,
    "unitNumber": 1,
    "limit": 7,
    "includePartialBar": false
}
```

Response (`RetrieveBarResponse`): `bars: AggregateBarModel[]` + envelope.
`RetrieveBarErrorCode` (S2): `0 = Success`, `1 = ContractNotFound`, `2 = UnitInvalid`,
`3 = UnitNumberInvalid`, `4 = LimitInvalid`. None of these appear on S1.

`AggregateBarModel` (S2):

| Field | Type | Required | In S1 sample | Meaning |
|---|---|---|---|---|
| `t` | date-time string | required | yes | Bar timestamp |
| `o` | decimal | required | yes | Open |
| `h` | decimal | required | yes | High |
| `l` | decimal | required | yes | Low |
| `c` | decimal | required | yes | Close |
| `v` | int64 | required | yes | Volume |
| `d` | date string | optional | **no** | UNKNOWN — undocumented |
| `k` | int64 | optional | **no** | UNKNOWN — undocumented |

**Bars come back newest-first.** S1's example with `"limit": 7` and `unit: 3` returns
`14:00`, `13:00`, `12:00`, `11:00`, `10:00`, `09:00`, `08:00` — strictly descending. The
descending order is visible in the sample but is **never stated as a guarantee** in prose. Sort
defensively.

Also note: the requested window in S1's example is `2024-12-01` → `2024-12-31` with `limit: 7`,
and the returned bars are all from `2024-12-20` — i.e. `limit` truncates from the **end** of the
window, keeping the most recent bars. This too is only inferable from the sample.

Bar timestamps in the sample carry a `+00:00` offset. Whether bars are aligned to UTC or to an
exchange session timezone: UNKNOWN.

### 8.6 Place an Order — `POST /api/Order/place`

Source: **S1** https://gateway.docs.projectx.com/docs/api-reference/order/order-place,
**S2** `Order_PlaceOrder`.

Request (`PlaceOrderRequest`):

| Name | Type | Description (S1 verbatim) | Required | Nullable |
|---|---|---|---|---|
| `accountId` | integer (int32) | "The account ID." | Required | false |
| `contractId` | string | "The contract ID." | Required | false |
| `type` | integer (`OrderType`) | "The order type: 1 = Limit, 2 = Market, 4 = Stop, 5 = TrailingStop, 6 = JoinBid, 7 = JoinAsk" | Required | false |
| `side` | integer (`OrderSide`) | "The side of the order: 0 = Bid (buy), 1 = Ask (sell)" | Required | false |
| `size` | integer (int32) | "The size of the order." | Required | false |
| `limitPrice` | decimal | "The limit price for the order, if applicable." | Optional | true |
| `stopPrice` | decimal | "The stop price for the order, if applicable." | Optional | true |
| `trailPrice` | decimal | "TrailingStop (type 5) only, and required for that type. The absolute price level the trailing stop starts at, not a distance." | Optional | true |
| `customTag` | string | "An optional custom tag for the order. Must be unique across the account." | Optional | true |
| `stopLossBracket` | object (`PlaceOrderBracket`) | "Stop loss bracket configuration." | Optional | true |
| `takeProfitBracket` | object (`PlaceOrderBracket`) | "Take profit bracket configuration." | Optional | true |

> **The `type` list on this page omits `3 = StopLimit`.** S1 jumps 1, 2, 4, 5, 6, 7. S2's
> `OrderType` enum includes `3 = StopLimit` and `0 = Unknown`. S1 also says errorCode 2 covers
> "unsupported order type". Whether `StopLimit` is placeable through this endpoint: UNKNOWN.

`PlaceOrderBracket` (both `stopLossBracket` and `takeProfitBracket`):

| Name | Type | Description (S1 verbatim) | Required |
|---|---|---|---|
| `ticks` | integer | "Number of ticks for stop loss" / "Number of ticks for take profit" | Required |
| `type` | integer | "Uses same OrderType enum values: 1 = Limit, 2 = Market, 4 = Stop, 5 = TrailingStop, 6 = JoinBid, 7 = JoinAsk" | Required |

**Bracket mode — a hard precondition.** S1 verbatim:

> *"Each account has a bracket mode, set in the trading platform under Settings > Risk Settings:*
>
> - *Position Brackets (default). Brackets are managed at the position level by the platform.
>   `stopLossBracket` and `takeProfitBracket` are not accepted on this endpoint.*
> - *Auto OCO Brackets. Brackets attach to each order. `stopLossBracket` and `takeProfitBracket`
>   are accepted on this endpoint.*
>
> *Sending either bracket object while the account is in Position Brackets mode rejects the order
> with errorCode 2 and the message `Brackets cannot be used with Position Brackets. You must
> enable Auto OCO Brackets.` **The rejected order is still created and its ID is returned in
> `orderId`.** To fix this, switch the account to Auto OCO Brackets, or omit the bracket
> objects."*

The emphasised sentence is load-bearing: a *failed* place still returns a real `orderId`. Do not
treat a non-null `orderId` as success — check `success`/`errorCode`.

**`trailPrice` is an absolute price level, not a distance.** S1 verbatim:

> *"`trailPrice` applies only to order type 5 (TrailingStop) and is required for that type. It is
> an absolute price level, not a trail distance. When the request arrives, the server measures
> the gap between the contract's last traded price and `trailPrice` and converts it to a whole
> number of ticks:*
>
> `trailDistanceTicks = |lastTradedPrice - trailPrice| / tickSize`
>
> - *The last traded price is read on the server at the moment the order is received. In a
>   fast-moving market the same `trailPrice` can produce a different tick distance than you
>   expected.*
> - *Fractions of a tick are dropped.*
> - *Once accepted, the distance is fixed in ticks and the stop price trails the market by that
>   many ticks.*
> - *`trailPrice` must be aligned to the contract's tick size."*

S1's worked example, verbatim: *"A contract with a 0.01 tick size last traded at 70.50. For a
trailing stop 6 ticks away, send the price level 6 ticks from the market: 70.44 for a sell stop
(side 1), or 70.56 for a buy stop (side 0). Do not send the distance itself. A `trailPrice` of
0.06 is read as a price level near zero, which works out to a distance of 7044 ticks and is
rejected."*

`trailPrice` rejection messages (S1, all under `errorCode 2`):

| `errorMessage` (verbatim) | Cause (S1 verbatim) |
|---|---|
| `Trail Distance not set.` | "`type` is 5 but `trailPrice` is null." |
| `Invalid trail price. Price is not aligned to tick size.` | "`trailPrice` is not a multiple of the contract's tick size." |
| `Cannot trail without a last price` | "The contract has no last traded price yet, so there is nothing to measure the distance from." |
| `Invalid symbol` | "No quote is available for the contract." |
| `Trail Distance exceeds maximum (1000)` | "The computed distance is more than 1000 ticks. The usual cause is sending a distance instead of a price level." |

**Read-back asymmetry**, S1 verbatim: *"When a trailing stop is returned by the order search
endpoints, its `trailPrice` holds the trail distance expressed in price (ticks x tickSize), not
the price level that was submitted. Using the example above, the order reads back with
`trailPrice` 0.06."* You write a price level and read back a distance.

`PlaceOrderErrorCode` (S1 and S2 agree exactly):

| Code | Name | Meaning (S1 verbatim) |
|---|---|---|
| 0 | `Success` | "The order was accepted." |
| 1 | `AccountNotFound` | "The account does not exist or is not owned by the caller." |
| 2 | `OrderRejected` | "The order was rejected. errorMessage states the reason." |
| 3 | `InsufficientFunds` | "The account does not have enough funds for the order." |
| 4 | `AccountViolation` | "The account is in violation and cannot place orders." |
| 5 | `OutsideTradingHours` | "The market is not open for the contract." |
| 6 | `OrderPending` | "The order is still being processed." |
| 7 | `UnknownError` | "An unexpected error occurred." |
| 8 | `ContractNotFound` | "The contract ID is not recognized." |
| 9 | `ContractNotActive` | "The contract is not the currently active contract." |
| 10 | `AccountRejected` | "The account is not allowed to place orders." |

S1 verbatim: *"errorCode 2 covers every validation rejection, including unsupported order type,
invalid side or size, an invalid `trailPrice`, a duplicate `customTag`, and bracket rules. Always
read `errorMessage` to identify the specific cause."*

Response (`PlaceOrderResponse`): `orderId` (int64, nullable) + envelope.

S1 examples, verbatim:

```json
{
    "orderId": 9056,
    "success": true,
    "errorCode": 0,
    "errorMessage": null
}
```

```json
{
    "orderId": 9057,
    "success": false,
    "errorCode": 2,
    "errorMessage": "Brackets cannot be used with Position Brackets. You must enable Auto OCO Brackets."
}
```

### 8.7 Modify an Order — `POST /api/Order/modify`

Source: **S1** https://gateway.docs.projectx.com/docs/api-reference/order/order-modify.

S1 verbatim: *"Modify an open order."*

| Name | Type | Description (S1 verbatim) | Required | Nullable |
|---|---|---|---|---|
| `accountId` | integer (int32) | "The account ID." | Required | false |
| `orderId` | integer (int64) | "The order id." | Required | false |
| `size` | integer (int32) | "The size of the order." | Optional | true |
| `limitPrice` | decimal | "The limit price for the order, if applicable." | Optional | true |
| `stopPrice` | decimal | "The stop price for the order, if applicable." | Optional | true |
| `trailPrice` | decimal | "TrailingStop orders only. The new absolute price level for the trailing stop, not a distance." | Optional | true |

**Modify has no maximum-trail-distance guard.** S1 verbatim: *"Unlike Place an Order, a modify
has no maximum-distance check, so this mistake is accepted rather than rejected. Double-check the
value before sending."* Sending `0.06` instead of `70.44` on a 0.01-tick contract last traded at
70.50 silently sets a 7044-tick trail.

S1 verbatim: *"A `trailPrice` that is not aligned to the contract's tick size, or a contract with
no last traded price, is rejected with errorCode 3 (Rejected). The `errorMessage` values are the
same as on Place an Order."*

`ModifyOrderErrorCode` — **S2 only; S1 has no error-code table on this page**:
`0 = Success`, `1 = AccountNotFound`, `2 = OrderNotFound`, `3 = Rejected`, `4 = Pending`,
`5 = UnknownError`, `6 = AccountRejected`, `7 = ContractNotFound`.

Response (`ModifyOrderResponse`): envelope only, no payload field.

Whether omitting an optional field leaves it unchanged or clears it: not stated. UNKNOWN.

### 8.8 Cancel an Order — `POST /api/Order/cancel`

Source: **S1** https://gateway.docs.projectx.com/docs/api-reference/order/order-cancel.

| Name | Type | Description (S1 verbatim) | Required | Nullable |
|---|---|---|---|---|
| `accountId` | integer (int32) | "The account ID." | Required | false |
| `orderId` | integer (int64) | "The order id." | Required | false |

`CancelOrderErrorCode` (S1 and S2 agree):

| Code | Name | Meaning (S1 verbatim) |
|---|---|---|
| 0 | `Success` | "The cancellation was accepted." |
| 1 | `AccountNotFound` | "The account does not exist or is not owned by the caller." |
| 2 | `OrderNotFound` | "The order does not exist or does not belong to the account." |
| 3 | `Rejected` | "The trading engine rejected the cancellation." |
| 4 | `Pending` | "The cancellation is still being processed." |
| 5 | `UnknownError` | "An unexpected error occurred." |
| 6 | `AccountRejected` | "The account is not allowed to cancel orders. See below." |

**`errorCode 6` is overloaded and one of its causes is a hard platform limit.** S1 verbatim:

| `errorMessage` (verbatim) | Cause (S1 verbatim) |
|---|---|
| `Follower accounts cannot cancel orders` | "The account is a copy-trading follower. Follower accounts mirror a leader and cannot cancel orders directly." |
| `Live accounts not supported` | "The account is a live or brokerage account. This endpoint only supports simulated accounts." |

S1 verbatim: ***"Only simulated accounts that are not following another account can cancel orders
through this endpoint."***

This is the single most consequential restriction in the API for a live deployment: **cancel is
documented as simulated-accounts-only.** Whether `place` and `modify` carry the same restriction
is not stated on their pages, though both `PlaceOrderErrorCode` and `ModifyOrderErrorCode` also
define an `AccountRejected` value. See UNKNOWNS.

Response (`CancelOrderResponse`): envelope only. S1 examples, verbatim:

```json
{ "success": true, "errorCode": 0, "errorMessage": null }
```

```json
{ "success": false, "errorCode": 6, "errorMessage": "Follower accounts cannot cancel orders" }
```

### 8.9 Search for Orders — `POST /api/Order/search`

Source: **S1** https://gateway.docs.projectx.com/docs/api-reference/order/order-search.

| Name | Type | Description (S1 verbatim) | Required | Nullable |
|---|---|---|---|---|
| `accountId` | integer (int32) | "The account ID." | Required | false |
| `startTimestamp` | datetime | "The start of the timestamp filter." | Required | false |
| `endTimestamp` | datetime | "The end of the timestamp filter." | Optional | true |

Response (`SearchOrderResponse`): `orders: OrderModel[]` + envelope.
`SearchOrderErrorCode` (S2): `0 = Success`, `1 = AccountNotFound`.

S1 example, verbatim:

```json
{
  "orders": [
      {
          "id": 36598,
          "accountId": 704,
          "contractId": "CON.F.US.EP.U25",
          "symbolId": "F.US.EP",
          "creationTimestamp": "2025-07-18T21:00:01.268009+00:00",
          "updateTimestamp": "2025-07-18T21:00:01.268009+00:00",
          "status": 2,
          "type": 2,
          "side": 0,
          "size": 1,
          "limitPrice": null,
          "stopPrice": null,
          "fillVolume": 1,
          "filledPrice": 6335.250000000,
          "customTag": null
      }
  ],
  "success": true,
  "errorCode": 0,
  "errorMessage": null
}
```

`OrderModel` — **S2's field list is strictly larger than any S1 example.** Four fields never
appear in prose docs:

| Field | Type | Required (S2) | In S1 examples? |
|---|---|---|---|
| `id` | int64 | required | yes |
| `accountId` | int32 | required | yes |
| `contractId` | string | required | yes |
| `symbolId` | string | required | yes (order/search), **no** (order/searchOpen) |
| `creationTimestamp` | date-time | required | yes |
| `updateTimestamp` | date-time | required | yes |
| `status` | `OrderStatus` | required | yes |
| `type` | `OrderType` | required | yes |
| `side` | `OrderSide` | required | yes |
| `size` | int32 | required | yes |
| `limitPrice` | decimal | optional | yes |
| `stopPrice` | decimal | optional | yes |
| `fillVolume` | int32 | required | yes (order/search), **no** (order/searchOpen) |
| `filledPrice` | decimal | optional | yes |
| `customTag` | string | optional | yes (order/search), **no** (order/searchOpen) |
| **`trailDistance`** | **int32** | optional | **no** |
| **`trailPrice`** | **decimal** | optional | **no** |
| **`parentOrderId`** | **int64** | optional | **no** |
| **`linkedOrderId`** | **int64** | optional | **no** |

`parentOrderId` / `linkedOrderId` are how bracket children relate to their parent and to each
other (OCO). **Neither is described anywhere in prose** — their exact semantics are UNKNOWN, but
without them you cannot reliably associate an OCO pair.

Both `trailDistance` (int32, presumably ticks) and `trailPrice` (decimal) exist on the model.
S1's place-order page says the read-back `trailPrice` carries "the trail distance expressed in
price (ticks x tickSize)" — so `trailDistance` is most likely the same quantity in ticks, but
that is inference, not documentation.

### 8.10 Search for Open Orders — `POST /api/Order/searchOpen`

Source: **S1** https://gateway.docs.projectx.com/docs/api-reference/order/order-search-open,
**S2** `Order_SearchOpenOrders`.

| Name | Type | Description (S1 verbatim) | Required | Nullable |
|---|---|---|---|---|
| `accountId` | integer (int32) | "The account ID." | Required | false |

Response: `SearchOrderResponse` — same `OrderModel[]` as §8.9.

**Critical caveat, present only in S2's operation summary, verbatim:**

> *"Searches for orders with Open status on an account. Does not include Suspended bracket
> children — use `/v2/query` with `Statuses: [Open, Suspended]` to fetch those alongside open
> orders."*

S1's page does not mention this at all. If you use `searchOpen` to reconcile working orders you
will **silently miss suspended bracket children** (`OrderStatus 8 = Suspended`) and can conclude
a position is unprotected when its stop exists, or flatten into a live resting bracket.

### 8.11 Search for Order by Id — `POST /api/Order/searchById`

**S2 only — no S1 page exists.**
S2 summary, verbatim: *"Searches for a single order by its ID on an account owned by the
authenticated user."*

Request (`SearchOrderByIdRequest`): `accountId` int32 required, `orderId` int64 required.
Response (`SearchOrderByIdResponse`): `order: OrderModel` + envelope.
`SearchOrderByIdErrorCode`: `0 = Success`, `1 = OrderNotFound`.

### 8.12 Paginated order query — `POST /api/Order/v2/query`

**S2 only — no S1 page exists.** This is the only endpoint in the API with pagination, and the
only one for which S2 documents a `400`.

S2 summary, verbatim: *"Paginated order search with optional filtering by status, contract, and
creation timestamp."*

Request (`SearchOrdersQueryRequest`):

| Field | Type | Required |
|---|---|---|
| `filter` | `GatewayOrderFilter` | **required** |
| `pageSize` | int32 | optional |
| `pageOffset` | int32 | optional |
| `sortBy` | `OrderSortField` | optional |
| `sortDirection` | `SortDirection` | optional |
| `includeTotalCount` | boolean | optional |

`GatewayOrderFilter`:

| Field | Type | Required |
|---|---|---|
| `accountId` | int32 | **required** |
| `statuses` | `OrderStatus[]` | optional |
| `contractId` | string | optional |
| `createdAfter` | date-time | optional |
| `createdBefore` | date-time | optional |

`OrderSortField` (S2): `0 = CreatedAt`, `1 = Id`.
`SortDirection` (S2): `0 = Asc`, `1 = Desc`.

Response (`SearchOrdersQueryResponse`): `orders: OrderModel[]`, `totalCount` int32 (optional),
plus the envelope with `SearchOrderErrorCode`.
On `400`: `ProblemDetails` — `{ type, title, status, detail, instance }` (RFC 7807), **not** the
`success`/`errorCode` envelope. This is the one endpoint whose failure shape differs.

Default `pageSize`, maximum `pageSize`, whether `pageOffset` is 0- or 1-based, and the default
sort: all UNKNOWN.

Note the field-name casing conflict: the S2 summary for `searchOpen` writes the filter key as
`Statuses` (capital S) while the `GatewayOrderFilter` schema defines `statuses`. See UNKNOWNS.

### 8.13 Search for Positions — `POST /api/Position/searchOpen`

Source: **S1** https://gateway.docs.projectx.com/docs/api-reference/positions/search-open-positions.

| Name | Type | Description (S1 verbatim) | Required | Nullable |
|---|---|---|---|---|
| `accountId` | integer (int32) | "The account ID." | Required | false |

Response (`SearchPositionResponse`): `positions: PositionModel[]` + envelope.
`SearchPositionErrorCode` (S2): `0 = Success`, `1 = AccountNotFound`.

`PositionModel` (S2):

| Field | Type | Required | In S1 example? |
|---|---|---|---|
| `id` | int32 | required | yes |
| `accountId` | int32 | required | yes |
| `contractId` | string | required | yes |
| **`contractDisplayName`** | **string** | optional | **no** |
| `creationTimestamp` | date-time | required | yes |
| `type` | `PositionType` | required | yes |
| `size` | int32 | required | yes |
| `averagePrice` | decimal | required | yes |

S1 example, verbatim:

```json
{
    "positions": [
        {
            "id": 6124,
            "accountId": 536,
            "contractId": "CON.F.US.GMET.J25",
            "creationTimestamp": "2025-04-21T19:52:32.175721+00:00",
            "type": 1,
            "size": 2,
            "averagePrice": 1575.750000000
        }
    ],
    "success": true,
    "errorCode": 0,
    "errorMessage": null
}
```

Direction is carried by `type` (`PositionType`: `1 = Long`, `2 = Short`), **not** by the sign of
`size` — `size` is `2` for a 2-lot long. There is no unrealised-P&L field on the model.

### 8.14 Close Positions — `POST /api/Position/closeContract`

Source: **S1** https://gateway.docs.projectx.com/docs/api-reference/positions/close-positions.

| Name | Type | Description (S1 verbatim) | Required | Nullable |
|---|---|---|---|---|
| `accountId` | integer (int32) | "The account ID." | Required | false |
| `contractId` | string | "The contract ID." | Required | false |

Response (`ClosePositionResponse`): envelope only.

**S1's page carries no error-code table.** `ClosePositionErrorCode` from **S2** (9 values):
`0 = Success`, `1 = AccountNotFound`, `2 = PositionNotFound`, `3 = ContractNotFound`,
`4 = ContractNotActive`, `5 = OrderRejected`, `6 = OrderPending`, `7 = UnknownError`,
`8 = AccountRejected`.

> **Do not reuse the partial-close error table here.** The two enums have different arities (9 vs
> 10) and the codes are **shifted**: on `closeContract`, `5 = OrderRejected`; on
> `partialCloseContract`, `5 = InvalidCloseSize` and `6 = OrderRejected`.

### 8.15 Partially Close Positions — `POST /api/Position/partialCloseContract`

Source: **S1** https://gateway.docs.projectx.com/docs/api-reference/positions/close-positions-partial.

| Name | Type | Description (S1 verbatim) | Required | Nullable |
|---|---|---|---|---|
| `accountId` | integer (int32) | "The account ID." | Required | false |
| `contractId` | string | "The contract ID." | Required | false |
| `size` | integer (int32) | "The size to close." | Required | false |

`PartialClosePositionErrorCode` (S1 and S2 agree — 10 values):

| Code | Name | Meaning (S1 verbatim) |
|---|---|---|
| 0 | `Success` | "The closing order was executed." |
| 1 | `AccountNotFound` | "The account does not exist or is not owned by the caller." |
| 2 | `PositionNotFound` | "No open position exists for the account and contract." |
| 3 | `ContractNotFound` | "The contract ID is not recognized." |
| 4 | `ContractNotActive` | "The contract is not the currently active contract." |
| 5 | `InvalidCloseSize` | "The size is zero, negative, or larger than the open position." |
| 6 | `OrderRejected` | "The closing market order was rejected. See below." |
| 7 | `OrderPending` | "The closing order is still being processed." |
| 8 | `UnknownError` | "An unexpected error occurred." |
| 9 | `AccountRejected` | "The account is not allowed to close positions (live accounts)." |

Note `9 = AccountRejected` is glossed **"(live accounts)"** — a second place where the docs
indicate a live/funded account is refused.

**`errorCode 6` is ambiguous by design.** S1 verbatim:

> *"This code is returned for more than one reason:*
>
> - *Trading is not allowed for the symbol. The market is closed, halted, or otherwise not
>   tradable at the moment of the request. The closing order is recorded as rejected for being
>   outside trading hours.*
> - *No current price is available for the contract. The engine could not resolve a price to
>   execute the close. The closing order is recorded as rejected with an invalid price.*
>
> *In both cases `errorMessage` is null, so the response alone does not indicate which cause
> applied. Retry once the market is open and quoting."*

Also verbatim: the close is executed as a **market order** ("The closing market order was
rejected").

### 8.16 Search for Trades — `POST /api/Trade/search`

Source: **S1** https://gateway.docs.projectx.com/docs/api-reference/trade/trade-search,
**S2** `Trade_SearchHalfTurnTrades`.

S2 summary, verbatim: *"Searches for **half-turn** trades based on the provided request
parameters."* The response model is literally named `SearchHalfTradeResponse` carrying
`HalfTradeModel[]` — each row is one **fill**, not a round trip.

Request (`SearchTradeRequest`):

| Name | Type | Description (S1 verbatim) | Required (S1) | Required (S2) |
|---|---|---|---|---|
| `accountId` | integer (int32) | "The account ID." | Required | **required** |
| `startTimestamp` | datetime | "The start of the timestamp filter." | **Required** | *optional* |
| `endTimestamp` | datetime | "The end of the timestamp filter." | Optional | optional |

*(S1 marks `startTimestamp` Required; S2 does not list it in `required`. Send it.)*

`HalfTradeModel` (S2):

| Field | Type | Required | In S1 example? |
|---|---|---|---|
| `id` | int64 | required | yes |
| `accountId` | int32 | required | yes |
| `contractId` | string | required | yes |
| `creationTimestamp` | date-time | required | yes |
| `price` | decimal | required | yes |
| `profitAndLoss` | decimal | required (but S1 shows `null`) | yes |
| `fees` | decimal | required | yes |
| **`commissions`** | **decimal** | optional | **no** |
| `side` | `OrderSide` | required | yes |
| `size` | int32 | required | yes |
| `voided` | boolean | required | yes |
| `orderId` | int64 | required | yes |

S1 example, verbatim — **including the inline comment, which is the only place the half-turn
convention is stated**:

```json
{
    "trades": [
        {
            "id": 8604,
            "accountId": 203,
            "contractId": "CON.F.US.EP.H25",
            "creationTimestamp": "2025-01-21T16:13:52.523293+00:00",
            "price": 6065.250000000,
            "profitAndLoss": 50.000000000,
            "fees": 1.4000,
            "side": 1,
            "size": 1,
            "voided": false,
            "orderId": 14328
        },
        {
            "id": 8603,
            "accountId": 203,
            "contractId": "CON.F.US.EP.H25",
            "creationTimestamp": "2025-01-21T16:13:04.142302+00:00",
            "price": 6064.250000000,
            "profitAndLoss": null,    //a null value indicates a half-turn trade
            "fees": 1.4000,
            "side": 0,
            "size": 1,
            "voided": false,
            "orderId": 14326
        }
    ],
    "success": true,
    "errorCode": 0,
    "errorMessage": null
}
```

**`profitAndLoss: null` means the fill opened (or added to) a position; a number means the fill
closed one and realised that P&L.** S2 nonetheless marks the field required — trust the S1
example and treat it as nullable.

`fees` and `commissions` are separate fields; only `fees` is ever shown in an example. Whether
`fees` is inclusive of `commissions`: UNKNOWN.

`SearchTradeErrorCode` (S2): `0 = Success`, `1 = AccountNotFound`.

### 8.17 Ping — `GET /api/Status/ping`

**S2 only — no S1 page.** The only `GET` in the API. No parameters. S2 declares a `200` response
with **no schema**, so the body shape is UNKNOWN. Summary, verbatim: *"Handles the ping request
to check the status of the API."* Whether it requires authentication: UNKNOWN.

---

## 9. Enumerations

### 9.1 Order-related enums

Source for the C# blocks: **S1** https://gateway.docs.projectx.com/docs/realtime/, section
"Enum Definitions". Confirmed value-for-value by **S2**.

```csharp
public enum OrderSide
{
    Bid = 0,
    Ask = 1
}
```

`Bid` = buy, `Ask` = sell — per S1's order-place table: *"0 = Bid (buy), 1 = Ask (sell)"*.

```csharp
public enum OrderType
{
    Unknown      = 0,
    Limit        = 1,
    Market       = 2,
    StopLimit    = 3,
    Stop         = 4,
    TrailingStop = 5,
    JoinBid      = 6,
    JoinAsk      = 7,
}
```

Note `3 = StopLimit` is present here and in S2 but is **omitted from the order-place page's
`type` list**.

```csharp
public enum OrderStatus
{
    None      = 0,
    Open      = 1,
    Filled    = 2,
    Cancelled = 3,
    Expired   = 4,
    Rejected  = 5,
    Pending   = 6
}
```

> **S1's `OrderStatus` block is incomplete.** S2's `OrderStatus` enum has **nine** values — it
> adds `7 = PendingCancellation` and `8 = Suspended`. `Suspended` is exactly the status that
> `/api/Order/searchOpen` omits (§8.10). Use the S2 list:

| Value | Name | Source |
|---|---|---|
| 0 | `None` | S1 + S2 |
| 1 | `Open` | S1 + S2 |
| 2 | `Filled` | S1 + S2 |
| 3 | `Cancelled` | S1 + S2 |
| 4 | `Expired` | S1 + S2 |
| 5 | `Rejected` | S1 + S2 |
| 6 | `Pending` | S1 + S2 |
| 7 | **`PendingCancellation`** | **S2 only** |
| 8 | **`Suspended`** | **S2 only** |

```csharp
public enum PositionType
{
    Undefined = 0,
    Long      = 1,
    Short     = 2
}
```

### 9.2 Market-data enums

```csharp
public enum DomType
{
    Unknown    = 0,
    Ask        = 1,
    Bid        = 2,
    BestAsk    = 3,
    BestBid    = 4,
    Trade      = 5,
    Reset      = 6,
    Low        = 7,
    High       = 8,
    NewBestBid = 9,
    NewBestAsk = 10,
    Fill       = 11,
}
```

```csharp
public enum TradeLogType
{
    Buy  = 0,
    Sell = 1,
}
```

Both are S1 (`/docs/realtime/`) only — neither appears in S2, because neither crosses the REST
surface.

### 9.3 `AggregateBarUnit`

S2 only (S1 gives 1–6 inline on the retrieve-bars page): `0 = Unspecified`, `1 = Second`,
`2 = Minute`, `3 = Hour`, `4 = Day`, `5 = Week`, `6 = Month`, `7 = Tick`. See §8.5.

### 9.4 Per-endpoint error-code enums — the integers are not portable

Each endpoint has its own `errorCode` enum. **The same integer means different things on
different endpoints.** Complete list from S2:

| Enum | Endpoint(s) | Values |
|---|---|---|
| `LoginErrorCode` | `Auth/loginKey`, `Auth/loginApp` | 0 Success, 1 UserNotFound, 2 PasswordVerificationFailed, 3 InvalidCredentials, 4 AppNotFound, 5 AppVerificationFailed, 6 InvalidDevice, 7 AgreementsNotSigned, 8 UnknownError, 9 ApiSubscriptionNotFound, 10 ApiKeyAuthenticationDisabled |
| `ValidateErrorCode` | `Auth/validate` | 0 Success, 1 InvalidSession, 2 SessionNotFound, 3 ExpiredToken, 4 UnknownError |
| `LogoutErrorCode` | `Auth/logout` | 0 Success, 1 InvalidSession, 2 UnknownError |
| `SearchAccountErrorCode` | `Account/search` | 0 Success |
| `SearchContractErrorCode` | `Contract/search` | 0 Success |
| `SearchContractByIdErrorCode` | `Contract/searchById` | 0 Success, 1 ContractNotFound |
| `ListAvailableContractErrorCode` | `Contract/available` | 0 Success |
| `RetrieveBarErrorCode` | `History/retrieveBars` | 0 Success, 1 ContractNotFound, 2 UnitInvalid, 3 UnitNumberInvalid, 4 LimitInvalid |
| `PlaceOrderErrorCode` | `Order/place` | 0 Success, 1 AccountNotFound, 2 OrderRejected, 3 InsufficientFunds, 4 AccountViolation, 5 OutsideTradingHours, 6 OrderPending, 7 UnknownError, 8 ContractNotFound, 9 ContractNotActive, 10 AccountRejected |
| `ModifyOrderErrorCode` | `Order/modify` | 0 Success, 1 AccountNotFound, 2 OrderNotFound, 3 Rejected, 4 Pending, 5 UnknownError, 6 AccountRejected, 7 ContractNotFound |
| `CancelOrderErrorCode` | `Order/cancel` | 0 Success, 1 AccountNotFound, 2 OrderNotFound, 3 Rejected, 4 Pending, 5 UnknownError, 6 AccountRejected |
| `SearchOrderErrorCode` | `Order/search`, `Order/searchOpen`, `Order/v2/query` | 0 Success, 1 AccountNotFound |
| `SearchOrderByIdErrorCode` | `Order/searchById` | 0 Success, 1 OrderNotFound |
| `SearchPositionErrorCode` | `Position/searchOpen` | 0 Success, 1 AccountNotFound |
| `ClosePositionErrorCode` | `Position/closeContract` | 0 Success, 1 AccountNotFound, 2 PositionNotFound, 3 ContractNotFound, 4 ContractNotActive, 5 OrderRejected, 6 OrderPending, 7 UnknownError, 8 AccountRejected |
| `PartialClosePositionErrorCode` | `Position/partialCloseContract` | 0 Success, 1 AccountNotFound, 2 PositionNotFound, 3 ContractNotFound, 4 ContractNotActive, 5 InvalidCloseSize, 6 OrderRejected, 7 OrderPending, 8 UnknownError, 9 AccountRejected |
| `SearchTradeErrorCode` | `Trade/search` | 0 Success, 1 AccountNotFound |

Worked traps:

- `errorCode 2` = `OrderRejected` on place, `OrderNotFound` on modify/cancel,
  `PasswordVerificationFailed` on login, `PositionNotFound` on both close endpoints,
  `SessionNotFound` on validate.
- `errorCode 5` = `OutsideTradingHours` on place, `UnknownError` on modify/cancel,
  `OrderRejected` on `closeContract`, `InvalidCloseSize` on `partialCloseContract`.
- `errorCode 6` = `OrderPending` on place, `AccountRejected` on modify/cancel,
  `OrderPending` on `closeContract`, `OrderRejected` on `partialCloseContract`.

Map error codes per endpoint. A shared `if code == 2: retry` is a bug.

---

## 10. Realtime — SignalR hubs

Source for all of §10: **S1** https://gateway.docs.projectx.com/docs/realtime/ (retrieved
2026-09-13). This is the **only** realtime page — `/docs/category/realtime-updates` links to it
alone.

S1 verbatim: *"The ProjectX Real Time API utilizes SignalR library (via WebSocket) to provide
real-time access to data updates involving accounts, orders, positions, balances and quotes.
There are two hubs: user and market."*

- *"The user hub will provide real-time updates to a user's accounts, orders, and positions."*
- *"The market hub will provide market data such as market trade events, DOM events, etc."*

### 10.1 Hub URLs and connection

| Hub | URL |
|---|---|
| User | `https://rtc.topstepx.com/hubs/user` |
| Market | `https://rtc.topstepx.com/hubs/market` |

S1's samples append the token as a query parameter **and** supply an `accessTokenFactory`:

```js
const userHubUrl   = 'https://rtc.topstepx.com/hubs/user?access_token=<REDACTED>';
const marketHubUrl = 'https://rtc.topstepx.com/hubs/market?access_token=<REDACTED>';
```

Connection options used in both official samples, verbatim (token literals redacted):

```js
new HubConnectionBuilder()
    .withUrl(hubUrl, {
        skipNegotiation: true,
        transport: HttpTransportType.WebSockets,
        accessTokenFactory: () => JWT_TOKEN,
        timeout: 10000
    })
    .withAutomaticReconnect()
    .build();
```

`skipNegotiation: true` with `transport: WebSockets` means **no `/negotiate` round trip**; the
client must speak the SignalR WebSocket protocol directly. Note the token appears in **both** the
query string and `accessTokenFactory` — with `skipNegotiation`, the query parameter is what
actually carries it. Whether a standard `Authorization: Bearer` header works instead: UNKNOWN.

**Re-subscribe on reconnect.** Both samples wire `onreconnected` to re-invoke every subscription:

```js
rtcConnection.onreconnected((connectionId) => {
    console.log('RTC Connection Reconnected');
    subscribe();
});
```

Subscriptions do **not** survive a reconnect. This is shown in the sample but never stated in
prose.

### 10.2 User hub — `https://rtc.topstepx.com/hubs/user`

**Server methods to invoke** (verbatim from the S1 sample):

| Invoke | Argument |
|---|---|
| `SubscribeAccounts` | *(none)* |
| `SubscribeOrders` | `accountId` |
| `SubscribePositions` | `accountId` |
| `SubscribeTrades` | `accountId` |
| `UnsubscribeAccounts` | *(none)* |
| `UnsubscribeOrders` | `accountId` |
| `UnsubscribePositions` | `accountId` |
| `UnsubscribeTrades` | `accountId` |

The sample comments `accountId` as *"your currently selected/visible account ID"*. Whether you
may subscribe several accounts on one connection is not stated — see UNKNOWNS.

**Client events received.** Four, all with a single `data` argument
(`rtcConnection.on('GatewayUserOrder', (data) => …)`):

| Event | Payload |
|---|---|
| `GatewayUserAccount` | account snapshot |
| `GatewayUserOrder` | order snapshot |
| `GatewayUserPosition` | position snapshot |
| `GatewayUserTrade` | trade (fill) |

**`GatewayUserAccount`** — S1 example payload and field table, verbatim:

```js
{
  id: 123,
  name: "Main Trading Account",
  balance: 10000.50,
  canTrade: true,
  isVisible: true,
  simulated: false
}
```

| Field | Type | Description (verbatim) |
|---|---|---|
| `id` | int | The account ID |
| `name` | string | The name of the account |
| `balance` | number | The current balance of the account |
| `canTrade` | bool | Whether the account is eligible for trading |
| `isVisible` | bool | Whether the account should be visible |
| `simulated` | bool | Whether the account is simulated or live |

Matches `TradingAccountModel` (§8.1) exactly, including `simulated`.

**`GatewayUserPosition`**:

```js
{
  id: 456,
  accountId: 123,
  contractId: "CON.F.US.EP.U25",
  creationTimestamp: "2024-07-21T13:45:00Z",
  type: 1, // Long
  size: 2,
  averagePrice: 2100.25
}
```

| Field | Type | Description (verbatim) |
|---|---|---|
| `id` | int | The position ID |
| `accountId` | int | The account associated with the position |
| `contractId` | string | The contract ID associated with the position |
| `creationTimestamp` | string | The timestamp when the position was created or opened |
| `type` | int (`PositionType` enum) | The type of the position (long/short) |
| `size` | int | The size of the position |
| `averagePrice` | number | The average price of the position |

No `contractDisplayName` here, unlike REST `PositionModel`. **How a position *close* is signalled
is not documented** — whether a flat position arrives as `size: 0`, as `type: 0 (Undefined)`, or
as no event at all is UNKNOWN.

**`GatewayUserOrder`**:

```js
{
  id: 789,
  accountId: 123,
  contractId: "CON.F.US.EP.U25",
  symbolId: "F.US.EP",
  creationTimestamp: "2024-07-21T13:45:00Z",
  updateTimestamp: "2024-07-21T13:46:00Z",
  status: 1, // Open
  type: 1, // Limit
  side: 0, // Bid
  size: 1,
  limitPrice: 2100.50,
  stopPrice: null,
  fillVolume: 0,
  filledPrice: null,
  customTag: "strategy-1"
}
```

| Field | Type | Description (verbatim) |
|---|---|---|
| `id` | long | The order ID |
| `accountId` | int | The account associated with the order |
| `contractId` | string | The contract ID on which the order is placed |
| `symbolId` | string | The symbol ID corresponding to the contract |
| `creationTimestamp` | string | The timestamp when the order was created |
| `updateTimestamp` | string | The timestamp when the order was last updated |
| `status` | int (`OrderStatus` enum) | The current status of the order |
| `type` | int (`OrderType` enum) | The type of the order |
| `side` | int (`OrderSide` enum) | The side of the order (bid/ask) |
| `size` | int | The size of the order |
| `limitPrice` | number | The limit price for the order, if applicable |
| `stopPrice` | number | The stop price for the order, if applicable |
| `fillVolume` | int | The number of contracts filled on the order |
| `filledPrice` | number | The price at which the order was filled, if any |
| `customTag` | string | The custom tag associated with the order, if any |

**This list omits `trailDistance`, `trailPrice`, `parentOrderId` and `linkedOrderId`**, all of
which exist on the REST `OrderModel` (§8.9). Whether the hub emits them is UNKNOWN.

**`GatewayUserTrade`**:

```js
{
  id: 101112,
  accountId: 123,
  contractId: "CON.F.US.EP.U25",
  creationTimestamp: "2024-07-21T13:47:00Z",
  price: 2100.75,
  profitAndLoss: 50.25,
  fees: 2.50,
  side: 0, // Bid
  size: 1,
  voided: false,
  orderId: 789
}
```

| Field | Type | Description (verbatim) |
|---|---|---|
| `id` | long | The trade ID |
| `accountId` | int | The account ID associated with the trade |
| `contractId` | string | The contract ID on which the trade occurred |
| `creationTimestamp` | string | The timestamp when the trade was created |
| `price` | number | The price at which the trade was executed |
| `profitAndLoss` | number | The total profit and loss of the trade, if available |
| `fees` | number | The total fees associated with the trade |
| `side` | int (`OrderSide` enum) | The side of the trade (bid/ask) |
| `size` | int | The size of the trade |
| `voided` | bool | Whether the trade is voided |
| `orderId` | long | The order ID associated with the trade |

Matches `HalfTradeModel` minus `commissions`. The half-turn `profitAndLoss: null` convention
(§8.16) applies here too — "if available".

### 10.3 Market hub — `https://rtc.topstepx.com/hubs/market`

**Server methods to invoke** (verbatim from the S1 sample):

| Invoke | Argument |
|---|---|
| `SubscribeContractQuotes` | `contractId` |
| `SubscribeContractTrades` | `contractId` |
| `SubscribeContractMarketDepth` | `contractId` |
| `UnsubscribeContractQuotes` | `contractId` |
| `UnsubscribeContractTrades` | `contractId` |
| `UnsubscribeContractMarketDepth` | `contractId` |

Sample `contractId`: `'CON.F.US.RTY.H25'`.

**Client events received.** Three, each with **two** arguments — `(contractId, data)` — unlike
the user hub's single argument:

| Event | Handler signature (verbatim) |
|---|---|
| `GatewayQuote` | `rtcConnection.on('GatewayQuote', (contractId, data) => …)` |
| `GatewayTrade` | `rtcConnection.on('GatewayTrade', (contractId, data) => …)` |
| `GatewayDepth` | `rtcConnection.on('GatewayDepth', (contractId, data) => …)` |

**`GatewayQuote`**:

```js
{
  symbol: "F.US.EP",
  symbolName: "/ES",
  lastPrice: 2100.25,
  bestBid: 2100.00,
  bestAsk: 2100.50,
  change: 25.50,
  changePercent: 0.14,
  open: 2090.00,
  high: 2110.00,
  low: 2080.00,
  volume: 12000,
  lastUpdated: "2024-07-21T13:45:00Z",
  timestamp: "2024-07-21T13:45:00Z"
}
```

| Field | Type | Description (verbatim) |
|---|---|---|
| `symbol` | string | The symbol ID |
| `symbolName` | string | Friendly symbol name (**currently unused**) |
| `lastPrice` | number | The last traded price |
| `bestBid` | number | The current best bid price |
| `bestAsk` | number | The current best ask price |
| `change` | number | The price change since previous close |
| `changePercent` | number | The percent change since previous close |
| `open` | number | The opening price |
| `high` | number | The session high price |
| `low` | number | The session low price |
| `volume` | number | The total traded volume |
| `lastUpdated` | string | The last updated time |
| `timestamp` | string | The quote timestamp |

Note the payload's `symbol` is the **`symbolId`** form (`F.US.EP`), not the `contractId` — the
`contractId` arrives as the handler's first argument. There are **no bid/ask sizes** on the
quote; top-of-book size must come from `GatewayDepth`. `symbolName` is documented as
"currently unused" — do not depend on it.

**`GatewayDepth`**:

```js
{
  timestamp: "2024-07-21T13:45:00Z",
  type: 1, // Ask
  price: 2100.00,
  volume: 10,
  currentVolume: 5
}
```

| Field | Type | Description (verbatim) |
|---|---|---|
| `timestamp` | string | The timestamp of the DOM update |
| `type` | int (`DomType` Enum) | DOM type |
| `price` | number | The price level |
| `volume` | number | The total volume at this price level |
| `currentVolume` | int | The current volume at this price level |

`DomType` has 12 values (§9.2) including `Reset`, `Fill`, `NewBestBid`, `NewBestAsk`, `Low`,
`High` and `Trade` — so this one event multiplexes book updates, book resets, trade prints and
session extremes. **The distinction between `volume` and `currentVolume` is not explained**, nor
is the algorithm for maintaining a book from the stream (in particular what `Reset` clears). See
UNKNOWNS.

**`GatewayTrade`**:

```js
{
  symbolId: "F.US.EP",
  price: 2100.25,
  timestamp: "2024-07-21T13:45:00Z",
  type: 0, // Buy
  volume: 2
}
```

| Field | Type | Description (verbatim) |
|---|---|---|
| `symbolId` | string | The symbol ID |
| `price` | number | The trade price |
| `timestamp` | string | The trade timestamp |
| `type` | int (`TradeLogType` enum) | TradeLog type |
| `volume` | number | The trade volume |

`type` is `TradeLogType` (`0 = Buy`, `1 = Sell`) — aggressor side, a different enum from
`OrderSide`. Note the field is `symbolId` here but `symbol` on `GatewayQuote`, for the same kind
of value.

### 10.4 Complete hub event inventory

Everything S1 documents, exhaustively:

| Hub | Direction | Name | Args |
|---|---|---|---|
| user | client → server | `SubscribeAccounts` | — |
| user | client → server | `SubscribeOrders` | `accountId` |
| user | client → server | `SubscribePositions` | `accountId` |
| user | client → server | `SubscribeTrades` | `accountId` |
| user | client → server | `UnsubscribeAccounts` | — |
| user | client → server | `UnsubscribeOrders` | `accountId` |
| user | client → server | `UnsubscribePositions` | `accountId` |
| user | client → server | `UnsubscribeTrades` | `accountId` |
| user | server → client | **`GatewayUserAccount`** | `data` |
| user | server → client | **`GatewayUserOrder`** | `data` |
| user | server → client | **`GatewayUserPosition`** | `data` |
| user | server → client | **`GatewayUserTrade`** | `data` |
| market | client → server | `SubscribeContractQuotes` | `contractId` |
| market | client → server | `SubscribeContractTrades` | `contractId` |
| market | client → server | `SubscribeContractMarketDepth` | `contractId` |
| market | client → server | `UnsubscribeContractQuotes` | `contractId` |
| market | client → server | `UnsubscribeContractTrades` | `contractId` |
| market | client → server | `UnsubscribeContractMarketDepth` | `contractId` |
| market | server → client | **`GatewayQuote`** | `contractId, data` |
| market | server → client | **`GatewayTrade`** | `contractId, data` |
| market | server → client | **`GatewayDepth`** | `contractId, data` |

**No other event names appear anywhere in S1, S2 or S3.** In particular there is no documented
heartbeat, error, or subscription-acknowledgement event, and no user-hub equivalent of
`GatewayDepth`. If the hubs emit anything else, it is undocumented.

---

## 11. Error model summary

1. Read the HTTP status first: `429` → rate limited (§6); `401` → token missing/expired (§5.5);
   `400` → malformed login body, or `/api/Order/v2/query` validation (`ProblemDetails`);
   `200` → read the body.
2. On `200`, read `success`. If `false`, read `errorCode` **against that endpoint's own enum**
   (§9.4), then `errorMessage`.
3. `errorMessage` is `null` for most codes. The documented non-null messages are, exhaustively:
   - `Please log into the ProjectX platform and complete the required agreements` (login, code 7)
   - `Brackets cannot be used with Position Brackets. You must enable Auto OCO Brackets.`
     (place, code 2)
   - `Trail Distance not set.` (place, code 2)
   - `Invalid trail price. Price is not aligned to tick size.` (place, code 2; modify, code 3)
   - `Cannot trail without a last price` (place, code 2; modify, code 3)
   - `Invalid symbol` (place, code 2)
   - `Trail Distance exceeds maximum (1000)` (place, code 2)
   - `Follower accounts cannot cancel orders` (cancel, code 6)
   - `Live accounts not supported` (cancel, code 6)
4. Two documented cases where the response cannot distinguish causes:
   - `partialCloseContract` code 6 — market-closed vs no-price; `errorMessage` is `null` for both.
   - `cancel` code 6 — disambiguated only by `errorMessage`.
5. A failed `place` still returns a real `orderId`. Never infer success from `orderId != null`.

---

## 12. Source page inventory (S1, 2026-09-13)

Every page on `gateway.docs.projectx.com`, from `sitemap.xml`; all `HTTP 200` unless noted:

| Path | Content |
|---|---|
| `/` | SPA landing shell, no doc content |
| `/ConnectionURLs` | SPA shell, renders "Loading environment…" only — **no static content**; use `/docs/getting-started/connection-urls` |
| `/docs/intro` | Overview, "What you'll need" |
| `/docs/getting-started/authenticate/authenticate-api-key` | §5.1 |
| `/docs/getting-started/authenticate/authenticate-as-application` | **HTTP 301 → authenticate-api-key**; not in sitemap |
| `/docs/getting-started/validate-session` | §5.3 |
| `/docs/getting-started/placing-your-first-order` | 3-step walkthrough (`Account/search` → `Contract/available` → `Order/place`); adds no fields beyond §8 |
| `/docs/getting-started/connection-urls` | §3 |
| `/docs/getting-started/rate-limits` | §6 |
| `/docs/api-reference/account/search-accounts` | §8.1 |
| `/docs/api-reference/market-data/search-contracts` | §8.2 |
| `/docs/api-reference/market-data/search-contracts-by-id` | §8.3 |
| `/docs/api-reference/market-data/available-contracts` | §8.4 |
| `/docs/api-reference/market-data/retrieve-bars` | §8.5 |
| `/docs/api-reference/order/order-place` | §8.6 |
| `/docs/api-reference/order/order-modify` | §8.7 |
| `/docs/api-reference/order/order-cancel` | §8.8 |
| `/docs/api-reference/order/order-search` | §8.9 |
| `/docs/api-reference/order/order-search-open` | §8.10 |
| `/docs/api-reference/positions/search-open-positions` | §8.13 |
| `/docs/api-reference/positions/close-positions` | §8.14 |
| `/docs/api-reference/positions/close-positions-partial` | §8.15 |
| `/docs/api-reference/trade/trade-search` | §8.16 |
| `/docs/realtime/` | §10 + the §9 enums |
| `/docs/category/{getting-started,authenticate,api-reference,account,market-data,orders,positions,trades,realtime-updates}` | Navigation index cards only, no API content |

There is **no** S1 page for: `Auth/logout`, `Auth/loginApp` (withdrawn), `Order/searchById`,
`Order/v2/query`, `Status/ping`, SignalR protocol details, sandbox environments, account-level
risk rules, or symbol/session calendars.
