# Stress test: refract spec vs. Stripe API (current)

Frozen spec: `15-refract-spec-frozen.md`. Retrieved 2026-07-14 via Context7 (`/websites/stripe`,
135,633 snippets, High reputation) + WebFetch against live `docs.stripe.com/api/*` pages +
WebSearch for the error-envelope shape. All quotes below are from those live fetches, not memory.

## Operations projected (12)

| # | Operation | Method / path | Why picked |
|---|---|---|---|
| 1 | Create PaymentIntent | `POST /v1/payment_intents` | canonical write, nested body |
| 2 | Retrieve PaymentIntent | `GET /v1/payment_intents/:id` | simple read + expand |
| 3 | List Charges | `GET /v1/charges` | cursor pagination |
| 4 | Update Customer | `POST /v1/customers/:id` | partial update via POST, not PATCH |
| 5 | Search Customers | `GET /v1/customers/search` | **distinct** pagination scheme |
| 6 | Create Charge (idempotent) | `POST /v1/charges` + `Idempotency-Key` | idempotency probe |
| 7 | Create Subscription | `POST /v1/subscriptions` | array-of-objects nested body |
| 8 | Retrieve Charge w/ expand | `GET /v1/charges/:id?expand[]=customer` | id-or-object polymorphism |
| 9 | Delete Customer | `DELETE /v1/customers/:id` | bodyless write → ack shape |
| 10 | Upload File | `POST https://files.stripe.com/v1/files` | different host + multipart |
| 11 | List Events | `GET /v1/events` | cursor pagination, webhook feed |
| 12 | Error response (any 4xx) | e.g. 402 on charge create | wrapped error envelope |

## Per-axis classification

| Axis | Class | Verdict |
|---|---|---|
| auth | **native** | Basic (`-u sk_live_...:`, empty password) or documented Bearer alternative (`Authorization: Bearer sk_live_...`) both fit `Basic`/`Bearer` strategies directly. Edge case: Connect's `Stripe-Account` header varies *per call* (per connected account), not a static `env:` secret — doesn't belong in `_auth.yaml`'s secrets model, but is trivially expressible as a normal `{name: Stripe-Account, in: header}` op param. Not a gap, just a documented seam between "auth strategy" and "header param." |
| pagination | **native, with a trap** | List/Events use `has_more` + `data[]` + `starting_after`/`ending_before` (cursor = last item's id) → exact fit for `RelativeCursor`. **But** Search (`/v1/customers/search` etc.) returns `object: "search_result"` and paginates via an opaque `page`/`next_page` token in the envelope, with **no** `starting_after` support and no forward/backward symmetry → that's `Cursor` (envelope next-cursor field), a *different* strategy than List's, on the same resource family. Correctly expressible per-operation, but a naive "one pagination style per resource" assumption breaks. |
| **request body** | **GAP** | Confirmed: Stripe write bodies are `application/x-www-form-urlencoded`, not JSON, with recursive bracket nesting: flat objects (`automatic_payment_methods[enabled]=true`), open maps (`metadata[key]=value`), scalar arrays (`items[0][tax_rates][0]=txr_x`), and arrays-of-objects (`items[0][price]=price_x&items[0][quantity]=2`), up to 4+ levels (`payment_method_data[billing_details][address][city]`). None of `TypedModel`/`Assembled`/`RawDict`/`Base64` serialize a nested model into this form. `Assembled` only flattens scalar params; `RawDict` is an escape hatch that discards typing for what would be *every* write operation (250+ on Stripe), not a corner case. **Needs a new `FormEncoded` body strategy** with a defined dict→`a[b][c]=v` / list→`a[0][...]` serialization convention — buildable because the neutral type system already distinguishes `map<K,V>` (→ key-flatten) from `ref<Model>` (→ field-flatten), the disambiguating info exists, just no strategy consumes it. |
| **idempotency** | **near-miss** | `Idempotency-Key` header, optional, POST-only, value must be a *freshly generated* UUID/random string per call (not a static `env:` secret), 24h+ TTL, 409 `idempotency_error` if reused with different params. Expressible today only as a plain header `param` the *caller* must remember to generate each call — works but pushes the ergonomics Stripe's own SDKs auto-handle back onto the refract-generated client's user. No concept in the spec of "auto-generate a fresh value per invocation" (contrast with `secrets: env:VAR` which is static/config-time). Confirms the brief's prediction. Suggested fix: a lightweight `Generated` header strategy (`{header: Idempotency-Key, generator: uuid4}`) usable per-op. |
| **expandable fields** | **GAP** | `expand[]=customer` (repeatable, dot-nested up to 4 levels, on read/list/create/update) turns a field from `"cus_123"` (string id) into a full nested `Customer` object **based on a caller-supplied query param**, i.e. request-time polymorphism. Neutral type system (`string \| integer \| number \| boolean \| list<T> \| map<K,V> \| ref<Model> \| any`) has **no union/either type**, so the field can't be honestly typed for both states. Typing it `string` lies when expanded; `ref<Model>` lies when not; `any` is honest but untyped and defeats `TypedModel`/`ParsesModel`. Cascades into the test registry (below). |
| responses & errors | **native** | Verified: error bodies are `{"error": {"type": "card_error", "code": "card_declined", "message": "...", "param": ..., "decline_code": ..., "doc_url": ...}}` — a plain envelope with a nested `ref<ErrorDetail>`, exactly the pattern the spec's own `SurveysResponse` envelope example already uses. Status codes map 1:1 to `error.type` families (400/401/403/404→invalid_request_error, 402→card_error, 409→idempotency_error, 429/5xx→api_error), so `responses: {402: {model: ErrorBody}, ...}` fits directly. Unlike Slack's 200-wrapped `ok:false` (the spec's own probe case), Stripe uses correct HTTP status, so this axis is a clean win. Minor wrinkle only: multiple `error.type`s can share one status, so the typed-exception-by-status hierarchy is coarser than Stripe's own discriminant — not a gap, just imprecise. |
| operation/path shape | **native** | POST reused for both create *and* update (no PUT/PATCH) — trivial since `method:` is explicit per op file. Delete-customer's bodyless response `{"id": "cus_x", "object": "customer", "deleted": true}` is close to a perfect match for the spec's own `ack: {factory: deleted, ident: ..., on: key}` mechanism (section 5's Tracker-comment example). Positive control point. |
| models/types | **native, modulo expand** | `metadata` (open string map) → `map<string,string>`; `status` enums → `enum`; nested resources → `ref<Model>`. All clean except the expand-polymorphism gap above. |
| tests | **amplified failure** | Two direct casualties, not a new independent gap: (1) `RoundtripsBody`/`PropertyRoundtrip` need a typed schema to hypothesis-generate from; forcing body onto `RawDict`/`Custom` to dodge the form-encoding gap leaves nothing to generate from, so this tier goes silently **vacuous** for most Stripe writes — undermines the "100% coverage gate" intent without ever failing loud. (2) `ParsesModel`/`PropertyParse` on any expand-eligible read op is only correct for one of the two possible shapes (expanded vs. not) — a generated instance for the "wrong" state either fails to parse or never exercises expansion at all. Exactly the "generated test would fail or be vacuous" failure mode section 11 asks to probe. |
| extra finding | **secondary GAP** | File upload (`POST https://files.stripe.com/v1/files`, `multipart/form-data`, `-F purpose=... -F file=@...`) is neither JSON nor form-urlencoded nor `Base64` (which implies a base64-encoded binary *field* inside an otherwise-typed body, not a true multipart part alongside scalar fields). Needs its own `Multipart` body strategy, distinct from the `FormEncoded` gap above though related. The different host (`files.stripe.com` vs `api.stripe.com`) is fine — `base_url` is per-`_resource.yaml`, so a `files` resource just gets its own base_url — but worth flagging since ycli's own domains (Tracker/Wiki/Forms) are each single-host, so this pattern is untested by the home codebase. |

## Verdict

Stripe is a **strong stress case, not a clean fit**: auth, pagination (per-op), responses/errors,
and the delete-ack shape all map natively — the spec's core mechanics hold up. But the write path
(the majority of Stripe's surface) breaks the JSON-first body assumption outright, and two of the
three axes the brief called out as "prime GAP suspects" are confirmed real gaps requiring new spec
concepts (not just new strategy instances of existing kinds); the third (idempotency) is a
confirmed near-miss.

**Top 3 gaps:**
1. **Request body — GAP.** No body strategy serializes nested/array/map data into
   form-urlencoded bracket notation (`items[0][price]=x`, `metadata[key]=v`). Needs a new
   `FormEncoded` strategy + serialization convention; affects effectively every Stripe write op.
2. **Expandable fields — GAP.** `expand[]` makes a field polymorphic (id string OR full object)
   at request time; the 8-primitive neutral type system has no union type to express it honestly.
3. **Idempotency-Key — near-miss.** Expressible as a manual header param, but the spec has no
   "auto-generate a fresh value per call" transport concept, unlike its static `env:`-secret auth
   model — pushes Stripe-SDK-grade ergonomics back onto the generated client's caller.

Secondary: multipart file upload is a third, related but distinct body-encoding gap (`Multipart`
strategy); Search-vs-List pagination divergence and the test-registry vacuousness are real but
downstream of the two headline gaps above, not independent findings.

File: `/tmp/claude-1000/-home-sava-dev-dev-ycli/80802223-5853-4c72-8da8-868e6f65a5f8/scratchpad/sac-research/stress/stripe.md`
