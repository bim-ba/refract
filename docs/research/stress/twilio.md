# Stress test: refract spec vs. Twilio REST API

Baseline: `15-refract-spec-frozen.md` (frozen v1). Target API: Twilio REST API (2010-04-01 Voice/Messaging +
Accounts). All claims below are pinned to live docs fetched **2026-07-14**; sources listed at the bottom.

## Operations sampled (12)

| # | Operation | Method + path |
|---|---|---|
| 1 | Send SMS (create Message) | `POST /2010-04-01/Accounts/{AccountSid}/Messages.json` |
| 2 | List Messages (paginated) | `GET /2010-04-01/Accounts/{AccountSid}/Messages.json` |
| 3 | Fetch a Message | `GET /2010-04-01/Accounts/{AccountSid}/Messages/{Sid}.json` |
| 4 | Delete a Message | `DELETE /2010-04-01/Accounts/{AccountSid}/Messages/{Sid}.json` |
| 5 | List Media (sub-resource of Message) | `GET /2010-04-01/Accounts/{AccountSid}/Messages/{MessageSid}/Media.json` |
| 6 | List Calls (paginated) | `GET /2010-04-01/Accounts/{AccountSid}/Calls.json` |
| 7 | Create a Call | `POST /2010-04-01/Accounts/{AccountSid}/Calls.json` |
| 8 | Update a live Call (redirect) | `POST /2010-04-01/Accounts/{AccountSid}/Calls/{Sid}.json` |
| 9 | Delete a Recording | `DELETE /2010-04-01/Accounts/{AccountSid}/Recordings/{Sid}.json` |
| 10 | Fetch Account Balance (sub-resource) | `GET /2010-04-01/Accounts/{AccountSid}/Balance.json` |
| 11 | List IncomingPhoneNumbers | `GET /2010-04-01/Accounts/{AccountSid}/IncomingPhoneNumbers.json` |
| 12 | Fetch the Account itself | `GET /2010-04-01/Accounts/{AccountSid}.json` |

## Summary table (per axis, worst-case across the 12 ops)

| Axis | Verdict | Why |
|---|---|---|
| Auth (Basic AccountSid:AuthToken, or ApiKey Sid:Secret) | **native** | Fits `Basic` strategy exactly; API-Key variant is the same strategy, different secret names. |
| Account-scoped path segment (`{AccountSid}` in every path) | **custom / near-miss** | Mechanically expressible as a normal path param, but semantically it's the *auth identity*, not a per-call argument — refract has no way to default a path/query param from a secret (it can default a **header**, per `_auth.yaml`'s `HeaderToken` example, but not a path segment). |
| Pagination (`page`/`page_size` + `next_page_uri` + envelope) | **custom / near-miss** | `NextUrl` is the right strategy in spirit, but Twilio's `next_page_uri` is **host-relative**, not absolute — breaks `NextUrl`'s implied "full URL" contract. The co-present `page`/`page_size` fields are a decoy: Twilio explicitly deprecated jumping pages via `Offset`-style page arithmetic. |
| Request body (form-urlencoded, flat Capitalized keys) | **GAP** | None of `TypedModel`/`Assembled`/`RawDict`/`Base64` specify wire encoding; all implicitly assume JSON. Confirmed as a spec-acknowledged probe target (§7). |
| Path shape (`.json` suffix, PascalCase segments, `{Sid}` templating) | **native** (mechanically) | Paths are opaque literal strings with `{param}` substitution, so `.json` and PascalCase segments cost nothing extra — just repetitive across every op file for one resource. |
| Responses/errors (`code`/`message`/`more_info`/`status`) | **native** | Clean fit for the explicit `responses:` map + typed error hierarchy — actually one of the *simple* cases the spec targets. Minor: refract's error typing is per-HTTP-status, Twilio's is finer-grained per-`code` within one status; not dispatched, just a field. |
| Models/types | **native**, but premise partly wrong | Response JSON is **snake_case** throughout (verified), not PascalCase — PascalCase/Capitalized only exists in *request form field names* (folds into the body-encoding gap, not a types gap). Separately: `date_created` etc. are **RFC 2822** strings, not RFC 3339/`date-time` — a real, distinct format GAP. |
| Tests | **native → GAP fallout** | `WrapsAck` is a clean native fit for 204-No-Content deletes. `DrainsPages` and `RoundtripsBody` would be **vacuous or failing** as auto-generated, because they inherit the pagination and body gaps above. |

## Detailed findings

### 1. Auth — native
Twilio's canonical credential pair is `AccountSid` (username) : `AuthToken` (password) sent as HTTP Basic
Auth, or the API-Key equivalent (`SKxxxxxxxx` : key secret) — same HTTP mechanism, different secret source
(docs recommend API Keys over the raw Auth Token for production). Both map 1:1 onto refract's `Basic`
strategy:
```yaml
auth:
  basic: {strategy: Basic, secrets: {username: env:TWILIO_ACCOUNT_SID, password: env:TWILIO_AUTH_TOKEN}}
  # or, API-Key variant — same strategy:
  api_key_basic: {strategy: Basic, secrets: {username: env:TWILIO_API_KEY_SID, password: env:TWILIO_API_KEY_SECRET}}
```
No gap. `curl -u ACxxxx:authtoken https://api.twilio.com/...` confirmed verbatim in docs.

### 2. The `{AccountSid}` path segment — the sleeper gap
Every one of the 12 sampled operations is nested `/Accounts/{AccountSid}/...`. `{AccountSid}` is not a
free caller-supplied argument in real usage — every Twilio SDK defaults it from the same credential used
for auth. refract's `_auth.yaml` *can* template a secret into a **header** (`X-Org-Id: "{organization_id}"`
in the spec's own worked example — this is literally ycli's own Yandex `X-Org-Id` pattern). But
`_resource.yaml`'s `base_url` is a static, non-templated string, and operation `params:` entries are
caller-supplied request-time values with no "default sourced from a secret" concept. Consequence: either
(a) hardcode the account SID into `base_url` per deployment — which fights the "secrets never in a
committed file" norm — or (b) declare `account_sid` as an ordinary path param that literally every one of
the 12 operations' callers must pass by hand, every call — workable but a real DX regression from what
every real Twilio client does. Classified **custom** (a `Custom` auth/handler could inject it), but it's a
structural near-miss worth a spec note: "secret → header" templating exists; "secret → path segment
default" does not.

### 3. Pagination — custom / near-miss, not native
List responses (Messages, Calls, IncomingPhoneNumbers all confirmed) share one envelope shape:
```json
{"calls": [...], "end": 1, "first_page_uri": "/2010-04-01/Accounts/ACxx/Calls.json?...",
 "next_page_uri": "/2010-04-01/Accounts/ACxx/Calls.json?PageToken=...&Page=1&PageSize=2",
 "page": 0, "page_size": 2, "previous_page_uri": null, "start": 0, "uri": "..."}
```
Two decoys, one real fit:
- `page` + `page_size` look like refract's `Offset` strategy, but Twilio's own engineering blog
  ("Replacing Absolute Paging and Related Properties") explicitly deprecated computing arbitrary
  `Page=N` jumps — pages are only reliably walked via the opaque `next_page_uri`/`PageToken`. A spec
  author picking `Offset` because the fields are *present* would generate a client that silently
  mis-paginates past page 1. This is exactly the kind of foot-gun the spec's probe list should flag.
- `next_page_uri` is the correct mechanic for refract's `NextUrl` ("full next-page URL in body") — except
  it is **host-relative** (`/2010-04-01/Accounts/...`), not the full absolute URL `NextUrl`'s description
  implies. A generated client needs a join-with-`base_url` step that isn't part of the strategy as
  specified. Downgrades this from native to **custom** (or requires extending `NextUrl` with a
  `relative: true` config knob).
- The envelope is also NOT the flat `meta`/`result` shape shown in the spec's own `_resource.yaml`
  example (§4) — items live under a resource-named key (`calls`, `messages`, `incoming_phone_numbers`),
  which the spec already supports via per-op `items_field`, so that part is fine.

### 4. Request body — GAP (spec-acknowledged)
Confirmed: `POST /Accounts/{Sid}/Messages.json` and `.../Calls.json` require
`Content-Type: application/x-www-form-urlencoded` with flat, Capitalized keys
(`Body=Hi+there&From=%2B1555...&To=%2B1555...`, `To=...&From=...&Url=...` for calls). §7 of the frozen
spec already names Twilio explicitly as a form-urlencoded probe target, and this confirms it: none of
`TypedModel`, `Assembled`, `RawDict`, `Base64` carry an encoding/`Content-Type` knob — all four
presumptively JSON-serialize. `Assembled` ("scalar params → dict") is the closest semantic fit since
Twilio's write bodies genuinely are flat scalars, but as specified it still needs a JSON→form-encoding
step bolted on. Deeper wrinkle beyond a simple `encoding: form` fix: MMS `MediaUrl` accepts *multiple*
values as a **repeated form key** (`MediaUrl=a&MediaUrl=b`), which is `list<T>` → repeated-key semantics
that no body strategy currently describes, form-aware or not.

### 5. Path shape — native (mechanically), but repetitive
`.json` suffixes and PascalCase segments (`Messages`, `Calls`, `Recordings`, `IncomingPhoneNumbers`) cost
nothing extra: `path:` is an explicit literal string with `{param}` substitution, independent of the
snake_case `resource:` name in `_resource.yaml` — e.g. `resource: messages` + `path: "Accounts/{account_sid}/Messages.json"`
coexist without conflict. `{Sid}` templating is exactly `{param}` templating. No new concept needed — just
verbose (the `.json` suffix and `Accounts/{account_sid}/` prefix must be repeated in every one of a
resource's per-operation files, since there's no resource-level path prefix hook in `_resource.yaml`).

### 6. Responses & errors — native
Verified error envelope (from docs + error-dictionary example for 21211):
```json
{"code": 21211, "message": "The 'To' number 5551234567 is not a valid phone number.",
 "more_info": "https://www.twilio.com/docs/errors/21211", "status": 400}
```
Maps cleanly onto an explicit `responses: {400: {model: ErrorBody}, 404: {model: ErrorBody}, ...}` map and
a typed error hierarchy per status — one of the *good* fits the spec is designed for. Minor, non-blocking
gap: Twilio's `code` is a fine-grained, Twilio-specific error taxonomy (hundreds of codes fold into one
HTTP status, e.g. many different `code`s all return 400) that refract's status-keyed `responses:` map
doesn't dispatch on — it's just a field on the one `ErrorBody` model per status, not a distinguishing type.

### 7. Models/types — mostly native; the task's own premise needs correcting
Verified Call-resource JSON is **snake_case throughout** (`account_sid`, `date_created`, `phone_number_sid`,
`from_formatted`, …) — an earlier WebFetch pass on this same page hallucinated camelCase (`dateCreated`,
`phoneNumberSid`); a follow-up fetch that demanded the raw JSON verbatim corrected this. So: the "PascalCase
fields" premise in the stress-test brief is **wrong for response bodies** — Twilio responses are snake_case,
a *native*, trivial fit for refract's Python emitter. Capitalized field names (`To`, `From`, `Body`, `Url`)
exist only on the **write side**, as form-parameter names — that's a restatement of the body-encoding gap
(§4), not a separate models/types problem.
A real, separate models/types GAP: timestamp fields (`date_created`, `date_updated`, `start_time`,
`end_time`, …) are emitted as **RFC 2822** strings (`"Fri, 18 Oct 2019 17:00:00 +0000"`), not RFC 3339. The
spec's `format: <s> (date-time/…)` (§2) aligns with JSON-Schema/OpenAPI `date-time` = RFC 3339. A
`date-time`-typed field validated/parsed against Twilio's actual RFC 2822 strings would fail or need a
non-standard parser — no per-field custom-parse hook exists in the neutral type system (§2 only lists
`optional`/`enum`/`format`/`deprecated`).

### 8. Tests — native for delete, GAP fallout elsewhere
- `WrapsAck`: verified `DELETE .../Messages/{Sid}.json` and `DELETE .../Recordings/{Sid}.json` both return
  bare `204 No Content`. Textbook fit for §5's `ack: {factory: deleted, ...}` → `Ack.deleted(...)`. Native,
  clean.
- `ParsesModel` / `ReturnsError`: native, given the snake_case bodies and flat error envelope above.
- `DrainsPages`: would **fail or need a Custom pagination handler** — it inherits the `next_page_uri`
  relative-URL mismatch from §3. An auto-generated `responses`-stubbed test asserting the client correctly
  requests page 2 either can't complete the request (no host to join against) or silently passes for the
  wrong reason if the mock matches on path only — a real "generated test is vacuous" case the spec asks to
  probe for (§8).
- `RoundtripsBody`: would be **vacuous** — it would serialize/compare a `TypedModel` as JSON while
  Twilio's real wire format is form-urlencoded; a green result wouldn't mean the client actually works
  against the real API.
- `PropertyParse`/`PropertyRoundtrip` (hypothesis): the RFC 2822 vs RFC 3339 date mismatch (§7) means
  hypothesis-generated `datetime` instances round-trip against an idealized ISO contract that doesn't match
  what Twilio actually returns — another vacuous-pass risk.
- Not a gap but out of scope worth noting: Twilio's SMS send is only nominally synchronous — real delivery
  status arrives via an inbound status-callback webhook, a pattern refract's outbound-REST-client model
  doesn't attempt to cover (consistent with the frozen spec's stated streaming/async exclusions, §0).

## Top gaps, ranked

1. **Form-urlencoded body** (§7, spec-acknowledged) — no body strategy specifies wire encoding; `Assembled`
   is the closest shape but needs an encoding knob, and MMS's repeated-key list semantics go beyond even that.
2. **Pagination `page`+`page_size`/`next_page_uri` hybrid** — `Offset` is a false-positive trap (Twilio
   deprecated it), and `NextUrl`'s implied absolute-URL contract breaks on Twilio's host-relative URIs;
   downgrades a seemingly clean fit to `custom`, with `DrainsPages` tests failing/vacuous as a result.
3. **Secret-templated path segment** (`{AccountSid}` in every path) — refract can template a secret into a
   header (proven pattern, ycli's own `X-Org-Id`) but not into a path/query param default, forcing either
   hardcoded SIDs in committed spec files or every caller passing `account_sid` by hand on all 12 ops.

Runner-up: RFC 2822 timestamps vs. the spec's RFC 3339-flavored `format: date-time`.

## Sources (retrieved 2026-07-14)

- [REST API: Auth Token](https://www.twilio.com/docs/iam/api/authtoken) — Basic Auth (AccountSid:AuthToken)
- [API keys overview](https://www.twilio.com/docs/iam/api-keys) — API Key/Secret Basic-auth variant
- [Twilio API responses](https://www.twilio.com/docs/usage/twilios-response) — error envelope fields
- [Messages resource](https://www.twilio.com/docs/messaging/api/message-resource) — create/list/fetch shapes, form body, Media sub-resource
- [Call resource](https://www.twilio.com/docs/voice/api/call-resource) — snake_case JSON verified verbatim, list envelope
- [Recording resource](https://www.twilio.com/docs/voice/api/recording) — DELETE → 204 No Content
- [Account resource / sub-resources](https://www.twilio.com/docs/usage/api/account) — `/Accounts/{Sid}/...` sub-resource map
- [Error and Warning Dictionary](https://www.twilio.com/docs/api/errors) + [21211](https://www.twilio.com/docs/api/errors/21211) — `code`/`message`/`more_info`/`status` example
- [Replacing Absolute Paging and Related Properties](https://www.twilio.com/en-us/blog/company/communications/replacing-absolute-paging-and-related-properties) — confirms `page`/`Page=N` jumping is deprecated in favor of relative `next_page_uri`
