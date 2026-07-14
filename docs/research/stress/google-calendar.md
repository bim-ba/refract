# Stress test: refract spec vs Google Calendar API v3

Baseline: `/tmp/claude-1000/-home-sava-dev-dev-ycli/80802223-5853-4c72-8da8-868e6f65a5f8/scratchpad/sac-research/15-refract-spec-frozen.md`
(frozen v1). All facts below re-verified against `developers.google.com` via WebSearch/WebFetch on
**2026-07-14**; sources cited per claim. Do not trust prior training-data memory of this API — several
findings below *contradict* the plausible-sounding assumption in the task brief (see §3, `updateMask`).

## 1. Operations picked (12)

| # | Operation | Shape |
|---|---|---|
| 1 | `events.list` | GET, paginated read |
| 2 | `events.get` | GET, single resource |
| 3 | `events.insert` | POST, full-body write |
| 4 | `events.patch` | PATCH, partial-body write |
| 5 | `events.delete` | DELETE, bodyless write (204) |
| 6 | `calendarList.list` | GET, paginated read (list calendars) |
| 7 | `events.watch` | POST, registers a webhook channel |
| 8 | Batch request | POST `/batch/calendar/v3`, multipart/mixed compose-N-ops |
| 9 | `events.instances` | GET, paginated read, nested under `eventId` |
| 10 | `freeBusy.query` | POST, RPC-shaped "query" (not CRUD) |
| 11 | `acl.list` / `acl.insert` | GET/POST, secondary sub-resource with its own sync semantics |
| 12 | `colors.get` | GET, static/global singleton lookup |

## 2. Axis classification (summary)

| Axis | Verdict | Why |
|---|---|---|
| auth — OAuth2 authz-code + refresh | **GAP** (consent bootstrap) / **underspecified** (refresh) / **custom** (service-account JWT) | see §3 |
| pagination (page/cursor) | **native** | `pageToken`/`nextPageToken`+`maxResults` = textbook Cursor strategy |
| pagination — `syncToken` delta-sync | **GAP** | terminal cursor becomes *next pass's* start token; no such concept exists |
| field masks / partial response (`fields=`) | **GAP** | cross-cutting, shape-pruning, fights the typed-model system |
| `updateMask` on patch | **N/A — doesn't exist on this API** (see below); underlying partial-body semantics is a **near-miss/GAP** | Calendar's PATCH ≠ mask param |
| conditional requests (ETag/If-Match) | **native primitives suffice, but protocol semantics is a GAP** | see §3 |
| request body (JSON, full write) | **native** | `TypedModel` fits insert/watch/acl/freeBusy bodies cleanly |
| request body (JSON, partial write / patch) | **near-miss → GAP** | `TypedModel` over-serializes unset fields unless it supports exclude-unset |
| responses & errors (status→model) | **native for the envelope, GAP for the nested discriminator** | see §3 |
| push notifications / watch | **native (registration) / GAP (delivery)** | see §3 |
| batch (multipart/mixed compose) | **GAP** | no concept of bundling N ops into one wire call |
| models/types | **native** | nested objects, lists, maps, enums, optional all map cleanly |
| tests | **native but shallow/vacuous in 2 places** | see §3 (RoundtripsBody, PropertyRoundtrip) |

## 3. Prime suspects — deep dive

### 3a. Auth: OAuth2 authorization-code + refresh lifecycle

Verified via `developers.google.com/identity/protocols/oauth2/web-server` (fetched 2026-07-14,
page last-updated per search index 2026-05-26) and `.../oauth2/service-account`.

Google Calendar actually has **three** distinct auth modes, not one:

1. **API key** (public/read-only calendars, no user data) → `ApiKey` strategy, `in: query`. **Native.**
2. **OAuth 2.0 authorization-code flow** (per-user data — the mainstream case for every op above
   except `colors.get`): redirect user to Google's consent screen → user actively approves/denies
   (WebFetch: *"this step requires interactive user participation and cannot be automated"*) →
   Google redirects back with a code → app POSTs the code to `oauth2.googleapis.com/token` → gets
   `access_token` + `refresh_token` (only if `access_type=offline`) + `expires_in`. Silent refresh
   thereafter uses the `refresh_token` against the same token endpoint.
3. **Service-account JWT bearer + domain-wide delegation** (server-to-server, no per-user consent
   at all — a fundamentally different profile: *"no user consent step is required... the private
   key allows this profile to assert identity directly"*): sign a JWT (RS256) with the service
   account's private key, POST it to the token endpoint, get an access token back.

Judging honestly against the frozen spec's §3 `OAuth2` line (`strategy: OAuth2 (flows)`, no worked
example unlike `HeaderToken`/`Bearer`/`ApiKey`/`Basic`/`Custom` which all get a config block):

- The **interactive consent + first-code-exchange bootstrap (mode 2, steps 1–4) is a genuine GAP**,
  and an honest one — a generator cannot drive a browser redirect and a human "Allow" click. This
  is the *same category* of gap the spec already names for streaming (§0: "expected stress points
  — report them, not silently"). It deserves the identical explicit callout: refract's job stops at
  wiring a token *provider*, never performing the dance itself.
- The **ongoing refresh-token → access-token refresh** (mode 2, "silent refresh thereafter") is
  arguably in scope — it's a plain POST with client_id/secret/refresh_token as secrets, same shape
  as any other write op — but the frozen spec gives `OAuth2` no config example the way it does for
  every sibling strategy, so it is **unproven, not confirmed-native**. Until `_auth.yaml` shows an
  `OAuth2` block with `token_url`/`client_id`/`client_secret`/`refresh_token` secrets and a
  "refresh on 401" hook, this is aspirational, not demonstrated.
- **Mode 3 (service-account JWT bearer) is a third, structurally different strategy** (signs its
  own bearer credential, no refresh_token at all) that doesn't fit `OAuth2` as usually understood
  from mode 2 — it needs `Custom(handler:)`.

Net: don't grade refract on "does it support OAuth2" as a yes/no — it's three separable claims, one
GAP (by design, fair), one unproven (needs a worked `_auth.yaml` example), one Custom.

### 3b. Field masks / partial response

Verified via WebSearch on Google's cross-API "Performance Tips" pages (Docs/Sheets/Gmail/Classroom
all document the identical mechanism) plus `events.patch`/`events.update` reference pages.

Two *different* things got conflated in the probe brief, and disambiguating them is itself a finding:

- **`fields=` query param (partial response on reads)**: a generic, comma-separated, *nestable*
  selector (`fields=items(id,summary,start/dateTime)`) usable on **every** read/list op uniformly.
  It prunes the wire *shape* of the response at request time. refract's `responses: {200: {model:
  X}}` binds each status to one fixed, fully-typed model — there is no axis in the spec for a
  param that reshapes that model's instance at runtime. Modeling it honestly would require either
  (a) a dynamically-partial/Optional-everything variant of the response model (defeats the
  point of `optional:` being an explicit per-field author choice) or (b) falling back to an
  untyped dict, silently abandoning the type system for any op that uses it. **GAP** — no
  strategy registry entry, and it's cross-cutting (would touch every read op, not one).
- **`updateMask` on patch — verified NOT to exist on this API.** This is the one place the task
  brief's assumption doesn't survive contact with the docs: Calendar's `events.patch` reference
  (fetched via WebSearch, 2026-07-14) documents *implicit* partial semantics — "field values you
  specify replace the existing values... fields you don't specify remain unchanged... array
  fields, if specified, overwrite the existing arrays" — driven purely by **which JSON keys are
  present in the body**, no `updateMask=` param or field anywhere. (Other Google APIs, e.g. Admin
  SDK / many Cloud APIs, *do* use an explicit `updateMask`; Calendar doesn't — don't generalize.)
  This still produces a real near-miss for the `body:` axis: refract's `TypedModel` strategy is a
  plain pydantic model — serializing it normally emits every field (including `None`/defaults for
  ones the caller never touched), which would be sent as explicit nulls on PATCH and **wipe fields
  the caller didn't intend to touch**. Getting Calendar's real "send only what I explicitly set"
  behavior needs `TypedModel` to support `exclude_unset` serialization for PATCH-shaped ops — not
  documented as a variant in the frozen spec's §7. **Near-miss bordering on GAP.**

### 3c. Push notifications / watch

Verified via `developers.google.com/workspace/calendar/api/guides/push` (fetched 2026-07-14) and
the `events.watch` reference.

The **registration call itself** (`POST .../events/watch`, body = `Channel{id, type: "web_hook",
address, token, params.ttl}`, response = `Channel{resourceId, resourceUri, expiration, ...}`) is an
ordinary JSON write — `TypedModel` in, `TypedModel` out. **Native**, no issue.

But the actual **notification delivery is categorically outside what a generated HTTP *client* can
ever emit**: Google POSTs headers-only pings (confirmed: *"notification messages... do not include
a message body"* — `X-Goog-Channel-ID`, `X-Goog-Resource-State` ∈ {sync, exists, not_exists},
`X-Goog-Resource-URI`, etc.) to a caller-owned HTTPS endpoint that must (a) hold a
non-self-signed, hostname-matching TLS cert, and (b) itself be a **server**, not a client. refract's
scope per §0 is "synchronous HTTP request/response APIs" for a generated *client*; an inbound
webhook receiver is generation of the opposite thing — a server that reacts to unsolicited inbound
POSTs and then must make a *follow-up* `events.list` call to learn what changed (the notification
carries no payload). The frozen spec names streaming/non-HTTP/GraphQL/SOAP as expected stress
points (§0) but does **not** name "inbound webhook receiver" as a fourth out-of-scope shape — it
is meaningfully different from streaming (it's still discrete HTTP request/response, just
direction-inverted) and deserves its own explicit scope line. **GAP**, and one the spec doesn't yet
have vocabulary for even as an acknowledged exclusion.

(Side note, not a spec gap: watch also requires prior **Google Search Console domain verification**
of the webhook host — a manual, out-of-band, non-API step no generator of any kind could touch.)

## 4. Secondary findings (worth recording, lower severity)

- **`syncToken` delta-sync ≠ pagination cursor.** `events.list`/`acl.list` end a *full* paginated
  drain with a `nextSyncToken` (not `nextPageToken`); that value is fed back as `syncToken=` on a
  *future, separate* call to get only what changed since. This is a persisted, cross-session
  "changefeed" cursor layered on top of ordinary intra-request pagination — refract's `Cursor`
  strategy only models the latter. No concept for "the pagination-terminal token becomes tomorrow's
  incremental-query token," and no concept for the paired failure mode: a `410 fullSyncRequired` /
  `410 updatedMinTooLongAgo` error that means "your sync token is dead, restart from a full sync."
  **GAP.**
- **Nested error `reason` discriminator.** Verified error shape: `{"error": {"code", "message",
  "errors": [{"domain","reason","message","locationType","location"}]}}`. Multiple *distinct*,
  machine-actionable `reason`s (`userRateLimitExceeded`, `rateLimitExceeded`, `quotaExceeded`,
  `forbiddenForNonOrganizer`) all collapse to the **same** HTTP status (403). refract's
  `responses: {403: {model: ErrorBody}}` is keyed purely by status — the generated typed-exception
  hierarchy stops at `Forbidden(403)`, losing the reason that actually determines whether a caller
  should retry-with-backoff or give up. Model-able as a plain field (`.errors[0].reason: string`),
  not model-able as a *distinguishing* exception type. **Near-miss.**
- **Batch (`multipart/mixed`, up to 1000 sub-requests/response, `Content-ID` matching) has zero
  representation in the strategy registries.** It composes N *already-defined* operations into one
  wire call and demultiplexes N independent HTTP responses back out. refract's unit is "one file =
  one op" (§1); nothing lets a spec bundle ops 3+4+5 above into one physical request. **GAP** — and
  a reusable one: this exact "bulk compose N ops" shape recurs in ycli's own domain (Tracker
  `bulk_update`/`bulk_move`), so it's not a Calendar-only curiosity.
- **Cross-field model validation is absent from the type system.** `Event.start`/`Event.end` must
  be a matched pair (both `date` XOR both `dateTime`+`timeZone`) and `end >= start` — refract §2's
  type system is purely per-field (`optional`, `enum`, `format`), no cross-field constraint concept.
  Consequence for §8: a `PropertyRoundtrip` hypothesis-generated `Event` would happily generate
  mismatched/invalid instances the real API 400s on, making that auto-test **vacuous or flaky**
  without heavy `skip:`/`configure:` overrides per op — exactly the failure mode §8's last line asks
  to probe for.
- **`RoundtripsBody` on `events.patch` would be actively misleading**, not just weak: a naive
  roundtrip (serialize full model, assert it "comes back") tests full-body semantics while the real
  wire behavior is partial-with-array-clobber (§3b) — the test could stay green while the
  generated client silently nulls fields on every real PATCH call.
- **Non-findings worth recording (so this isn't cherry-picked):** no 200-wrapped `ok:false`
  pattern (unlike Slack) — status-coded errors are used consistently; no RFC 7807 problem+json
  either — Google's own legacy nested-`errors[]` shape is used uniformly across all ops checked,
  which maps cleanly to one shared `ErrorBody` model in `models:`. `events.delete`'s bodyless 204
  fits the `ack:` factory fine as long as `ident` can be sourced from a path param rather than a
  response field (the frozen spec's one worked `ack:` example conflates comment-echo with
  no-body-at-all delete, which is a documentation gap, not a functional one).

## 5. Verdict

The unglamorous 70% of this API — `events.get/insert/list/delete`, `calendarList.list`,
`events.instances`, `freeBusy.query`, `acl.insert` — maps onto refract's strategy registries
cleanly: `Cursor` pagination, `TypedModel` bodies, status-keyed `ErrorBody` models, and the neutral
type system all fit natively with no contortion. That's a genuine pass, not a strawman result.

But all three flagged prime suspects are real, and none is a false alarm:

1. **OAuth2** — the interactive consent bootstrap is an honest, by-design GAP (same class as
   streaming); the "just refresh a token" remainder of the OAuth2 strategy is *unproven* in the
   frozen spec (no worked config, unlike every sibling strategy); and service-account JWT-bearer is
   a structurally different third mode needing `Custom`.
2. **Field masks / partial response** — the generic `fields=` selector is a real, cross-cutting GAP
   against the typed-model system; `updateMask` turned out not to exist on this API at all (a
   training-data trap avoided by checking docs), but Calendar's real implicit-partial-PATCH
   semantics exposes an equally real near-miss in `TypedModel`'s serialization.
3. **Push notifications** — registration is native; delivery requires generating an inbound webhook
   *server*, a shape the frozen spec's scope section doesn't yet name alongside streaming/GraphQL/SOAP.

Top-3 gaps for spec revision, in priority order: (1) name "inbound webhook receiver" as an explicit
out-of-scope shape next to streaming in §0; (2) give `OAuth2` a worked `_auth.yaml` example
(refresh-only) and explicitly scope out the consent bootstrap; (3) add either a partial-response
axis or explicitly declare `fields=`-style generic response shaping out of scope, and add an
`exclude_unset`/partial variant to `TypedModel` for real PATCH semantics.

## Sources (all fetched/searched 2026-07-14)

- https://developers.google.com/workspace/calendar/api/v3/reference/events/list
- https://developers.google.com/workspace/calendar/api/v3/reference/events/patch
- https://developers.google.com/workspace/calendar/api/v3/reference/events/insert
- https://developers.google.com/workspace/calendar/api/v3/reference/events/watch
- https://developers.google.com/workspace/calendar/api/v3/reference/events/instances
- https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query
- https://developers.google.com/workspace/calendar/api/v3/reference/calendarList/list
- https://developers.google.com/workspace/calendar/api/guides/pagination
- https://developers.google.com/workspace/calendar/api/guides/sync
- https://developers.google.com/workspace/calendar/api/guides/push
- https://developers.google.com/workspace/calendar/api/guides/batch
- https://developers.google.com/workspace/calendar/api/guides/errors
- https://developers.google.com/calendar/api/guides/version-resources (ETag/If-Match/If-None-Match)
- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.google.com/identity/protocols/oauth2/service-account
- https://developers.google.com/custom-search/v1/performance (fields= partial-response syntax, cross-API)
