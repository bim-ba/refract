# Stress-test: refract spec vs. Notion API (current)

Spec under test: `15-refract-spec-frozen.md` (frozen baseline v1).
Target API: Notion API, current docs at developers.notion.com. All facts below verified via
WebFetch/WebSearch against developers.notion.com on **retrieval date 2026-07-14**; each claim
is cited inline.

## 0. Critical context the probe should know up front

Notion shipped a **breaking versioning migration, API version `2025-09-03`** ("multi-source
databases"), and the header-pinned version has since moved again to `2026-03-11`
[Versioning](https://developers.notion.com/reference/versioning). This is not cosmetic: it
changed the *shape and path* of the query-a-database operation and introduced a mandatory
discovery step. It lands squarely on three of refract's own flagged probe points at once
(mandatory version header, cursor-in-body pagination, polymorphic models) plus a fourth refract
does not flag at all: **multi-step orchestration caused by API versioning, not by business
logic.**

## 1. Operations sampled (12)

| # | Operation | Method + path | Source |
|---|---|---|---|
| 1 | Retrieve a page | `GET /v1/pages/{page_id}` | [retrieve-a-page](https://developers.notion.com/reference/retrieve-a-page) |
| 2 | Retrieve a page property item | `GET /v1/pages/{page_id}/properties/{property_id}` | [retrieve-a-page-property](https://developers.notion.com/reference/retrieve-a-page-property) |
| 3 | Update page properties | `PATCH /v1/pages/{page_id}` | [patch-page](https://developers.notion.com/reference/patch-page) |
| 4 | Create a page | `POST /v1/pages` | [post-page](https://developers.notion.com/reference/post-page) |
| 5 | Retrieve a database (discovery step) | `GET /v1/databases/{database_id}` | [upgrade-guide-2025-09-03](https://developers.notion.com/docs/upgrade-guide-2025-09-03) |
| 6 | Query a data source (was "query a database") | `POST /v1/data_sources/{data_source_id}/query` | [query-a-data-source](https://developers.notion.com/reference/query-a-data-source) |
| 7 | Retrieve block children | `GET /v1/blocks/{block_id}/children` | [patch-block-children](https://developers.notion.com/reference/patch-block-children) (sibling GET) |
| 8 | Append block children | `PATCH /v1/blocks/{block_id}/children` | [patch-block-children](https://developers.notion.com/reference/patch-block-children) |
| 9 | Retrieve a block | `GET /v1/blocks/{block_id}` | [block](https://developers.notion.com/reference/block) |
| 10 | Delete (archive) a block | `DELETE /v1/blocks/{block_id}` | [block](https://developers.notion.com/reference/block) |
| 11 | Search | `POST /v1/search` | [post-search](https://developers.notion.com/reference/post-search) |
| 12 | List users | `GET /v1/users` | [Versioning](https://developers.notion.com/reference/intro) (pagination intro) |

## 2. Classification table

| Op | auth | pagination | models/types | body | responses/errors | op/path shape | tests |
|---|---|---|---|---|---|---|---|
| 1 Retrieve page | native | n/a | **GAP** (polymorphic properties) | n/a | native | native | GAP (cascades from models) |
| 2 Retrieve page property | native | **GAP** (conditional on property type) | **GAP** | n/a | native | native | GAP |
| 3 Update page properties | native | n/a | **GAP** | custom (RawDict) | native | native | GAP |
| 4 Create a page | native | n/a | **GAP** | custom (RawDict) | native | **custom** (parent resolution, see #5) | GAP |
| 5 Retrieve database (discovery) | native | n/a | native | n/a | native | **custom** (multi-step orchestration) | native |
| 6 Query a data source | native | **near-miss/GAP** (cursor-in-body) | **GAP** (filter tree is a union) | custom (nested filter tree) | native | custom (post-migration path + discovery dependency) | GAP |
| 7 Retrieve block children | native | native | **GAP** (Block union) | n/a | native | native | GAP |
| 8 Append block children | native | n/a | **GAP** (Block union, write side) | custom | native | native | GAP |
| 9 Retrieve a block | native | n/a | **GAP** | n/a | native | native | GAP |
| 10 Delete/archive block | native | n/a | native (bool flag) | n/a | native | native | native (near WrapsAck, but returns full resource not ack — near-miss) |
| 11 Search | native | **near-miss/GAP** (cursor-in-body + result-type union) | **GAP** (page\|data_source union) | native-ish | native | native | GAP |
| 12 List users | native | native | native (Person\|Bot union, smaller) | n/a | native | native | GAP (small-scale union) |

**Verdict up front: auth and responses/errors are solid `native` fits. Every operation that
touches a page property or a block body lands on the models/types GAP — that's 8 of 12 ops.**
Pagination is native for simple GET-cursor endpoints but breaks for POST-body cursor and,
worse, for the one endpoint whose pagination is itself conditional on runtime data.

## 3. Auth — `Notion-Version` mandatory static header

`Authorization: Bearer <token>` is a clean `HeaderToken`/`Bearer` fit. The
`Notion-Version` header is a different animal from ycli's `X-Org-Id`:

- It is **mandatory on literally every request** — omitting it is a distinct, named error:
  `400 missing_version` [errors](https://developers.notion.com/reference/errors).
- Unlike `X-Org-Id` (a per-caller runtime value sourced from `env:YANDEX_ID_ORGANIZATION_ID`),
  `Notion-Version` is a **spec-time literal constant**, not a secret — there's nothing to put
  in `secrets:`. Section 3's only worked example templates every header value from a secret
  (`"OAuth {token}"`, `"{organization_id}"`); the spec text never states whether `headers:` accepts
  a bare literal string with no `{}` placeholder. Almost certainly it does (nothing forbids it),
  so classify this sub-case **native**, but flag it as an **undocumented near-miss**: the spec
  should say explicitly that `HeaderToken` values may be literal, non-secret, non-templated
  strings — this is the common case for API-version pins (Notion, Stripe, GitHub all do it).
- The bigger issue is second-order: the *value* of this literal changed from `2022-06-28`
  (the probe's assumed value) → `2025-09-03` → `2026-03-11`
  [Versioning](https://developers.notion.com/reference/versioning), and each version bump
  changed response/request **shapes and paths**, not just headers (see §6). refract's
  `_resource.yaml`/operation files assume one frozen shape per spec-freeze. There is no concept
  of "this header value selects which of N wire shapes applies" — bumping `Notion-Version` in
  a refract spec is really a fork of the whole resource, not a one-line header edit, and the
  spec has no versioning-axis concept at all. **Near-miss / architectural gap**, not fatal, but
  real: a static-header-driven schema fork isn't expressible.

## 4. Pagination — cursor-in-body and conditional pagination

Confirmed: `start_cursor`/`page_size` go in the **query string for GET** endpoints, and in
the **request body for POST** endpoints
[intro/pagination](https://developers.notion.com/reference/intro),
[query-a-data-source](https://developers.notion.com/reference/query-a-data-source) (OpenAPI
schema puts `start_cursor` under `requestBody`, not `parameters`).

- **Retrieve block children / List users (GET):** `Cursor` strategy, native — cursor rides
  the same `params: [{in: query}]` mechanism §5 already shows for `Offset`.
- **Query a data source / Search (POST):** section 6 states pagination is "pure mechanics, no
  model ref" — but a body-cursor can only be sent by becoming a field *inside* the same
  `TypedModel` that carries `filter`/`sort`/`query`. That couples the pagination strategy to
  the body model after all, breaking the stated purity claim. There is no `in: body` analog to
  `ApiKey`'s `in: header|query|cookie` for pagination params. Classify **near-miss/GAP**: doable
  via `Custom`, but the built-in `Cursor` strategy as specified (no `in:` field) cannot express
  it cleanly — it needs a new field (`Cursor: {in: query|body, ...}`) to stay declarative.
- **Retrieve page property item is the sharpest finding:** pagination is **conditional on the
  runtime `type` of the specific property being fetched.** `title`/`rich_text`/`relation`/`people`
  return a paginated `has_more`/`next_cursor`/`results` envelope; `number`/`select`/`checkbox`/
  `date`/`formula`/`status` return a bare scalar value with no pagination envelope at all; and
  `rollup` is paginated *only when the underlying aggregation crosses many relations*
  [retrieve-a-page-property](https://developers.notion.com/reference/retrieve-a-page-property).
  One operation, one YAML file — but the correct `pagination:` strategy is **None for some data
  and Cursor for other data of the identical endpoint.** refract's `pagination:` key is a single
  static choice per operation. This is a genuine **GAP**: nothing in section 6's registry (not
  even `Custom`) is designed for "strategy chosen by the shape of the response body," and a
  generated `DrainsPages` test for this op is either vacuous or actively wrong depending which
  property the fixture happens to pick.

## 5. Models/types — the polymorphism is the headline finding

Both the block model and the page-property model are **tagged unions discriminated by a
sibling `type` field**, exactly the shape refract's neutral type system (§2:
`string | integer | number | boolean | list<T> | map<K,V> | ref<Model> | any`) has no primitive
for. There is no `oneOf`/discriminated-union type, and a model's `fields:` list is flat/nominal
— one type per field, authored once. This is not a "needs Custom but expressible" situation;
it's a **hard GAP**, because even a `Custom` handler still needs a declared return-type shape
for codegen to emit, and the spec gives no syntax for "this field is one of models {A,B,C}
selected by sibling key `type`."

Evidence of scale and depth:

- **Blocks:** ~32 distinct `type` variants (`paragraph`, `heading_1..3`, `image`, `to_do`,
  `child_database`, `synced_block`, `table`, …)
  [block](https://developers.notion.com/reference/block), each opening a *differently shaped*
  nested object under a key matching the type name.
- **Nested (second-level) unions:** `image`/`file`/`pdf`/`video` blocks carry their own inner
  discriminated union (`type: "external" | "file"`), each with a different payload shape
  (`external.url` vs. Notion-hosted file metadata) — a union nested inside a union.
- **`unsupported`** is an explicit escape-hatch variant Notion returns when a block type isn't
  exposed to the caller's pinned API version — i.e., the discriminant set itself is
  version-dependent, compounding the auth-axis versioning gap from §3.
- **Page properties:** ~20+ variants (`title`, `rich_text`, `number`, `select`, `status`,
  `people`, `relation`, `formula`, `rollup`, `files`, …), confirmed via
  [page-property-values](https://developers.notion.com/reference/page-property-values) and the
  retrieve-a-page example fetched directly (title vs. status shown side by side).
- **Compounding dynamism:** a page's `properties` map isn't even a fixed set of named fields —
  the *key set* is defined per-workspace by whoever configured that database/data source, and
  is only discoverable by a separate schema call. So it's `map<string, PropertyValue>` where
  both the key set AND the value's shape are runtime-determined; refract's `map<K,V>` primitive
  degrades this to `map<string, any>`, which compiles but throws away every bit of the type
  safety the spec exists to generate.
- **Search's result union** (`page | data_source`) and **`filter`'s recursive compound-filter
  tree** (`and`/`or` of property filters, arbitrarily nested) are smaller instances of the same
  gap on the request-body and response side respectively.

Workaround available today: model the properties/blocks payload as `RawDict` (the spec's
"allowlisted exception") and hand-roll everything past that boundary in a `Custom` handler.
That's honest **custom**, but it means 8 of 12 sampled operations — every one that touches page
content — fall out of the declarative fast path the spec is designed around, for the single most
central resource in the API.

## 6. Request body

- `Query a data source`'s `filter` field is a recursive union (`and: [Filter]` / `or: [Filter]` /
  leaf property-condition) — same "no `oneOf`" gap hits bodies too, not just responses.
- `Create a page` / `Update page properties`: the properties payload is the same
  `map<string,PropertyValue>` GAP from §5; realistically ships as `RawDict` (custom).
- `Append block children`: body is `list<Block>` — same Block-union GAP, write side.
- Non-polymorphic bodies (e.g. plain scalar fields) would be fine `TypedModel`/`Assembled` —
  but none of the 12 sampled operations actually have one; Notion's object model is polymorphic
  almost everywhere writes happen.

## 7. Responses & errors

Clean **native** fit — genuinely no complaints here. Confirmed shape:
```json
{"code": "validation_error", "message": "..."}
```
with a full status→code table (`400 invalid_json/invalid_request_url/invalid_request/
validation_error/missing_version`, `401 unauthorized`, `403 restricted_resource`,
`404 object_not_found`, `409 conflict_error`, `429 rate_limited`, `500 internal_server_error`,
`503 service_unavailable/database_connection_unavailable`, `504 gateway_timeout`,
`529 service_overload`) [errors](https://developers.notion.com/reference/errors) — maps 1:1 onto
refract's `responses: {status: {model}}` map plus a typed error hierarchy. No 200-wrapped
`ok:false` pattern here (unlike Slack); no RFC 7807. This axis validates cleanly.

## 8. Operation/path shape — versioning forces multi-step orchestration onto plain CRUD

This is the fourth prime suspect and the one the original probe list didn't name. Per the
2025-09-03 upgrade guide: `POST /v1/databases/{id}/query` is now **deprecated**, replaced by
`POST /v1/data_sources/{data_source_id}/query`
[query-a-data-source](https://developers.notion.com/reference/query-a-data-source). Getting a
`data_source_id` requires a **prerequisite `GET /v1/databases/{database_id}` call** to read the
`data_sources[]` array first
[upgrade-guide-2025-09-03](https://developers.notion.com/docs/upgrade-guide-2025-09-03).
Likewise `Create a page` under a database now expects `parent.data_source_id`, not
`parent.database_id`, for callers on the new API version. This is precisely the "upload =
create-session→PUT→finish→attach" multi-step case section 10 already anticipates and assigns to
`Custom` handler + partial OpenAPI coverage — so the *mechanism* to express it exists. The
finding is narrower but still real: **two of the most basic CRUD-shaped operations in the
sample (query, create-under-database) are no longer expressible as "one operation = one YAML
file with an explicit `path:`"** the moment an API does what Notion just did — a versioning
migration silently reclassified them into the orchestration/`Custom` bucket. refract's model
doesn't distinguish "genuinely multi-step business operation" from "single logical CRUD call
that a version bump turned into two HTTP calls" — worth naming as a distinct failure mode from
the upload example, since it will recur for any actively-evolving API, not just deliberately
multi-step ones.

## 9. Tests

Everything here cascades from §5. `PropertyRoundtrip`/`PropertyParse` (hypothesis, "many
generated instances from the model schema") has no schema to generate from once the model is
`RawDict`/`any` — a hand-rolled hypothesis strategy per block `type` (~32) or property `type`
(~20+) would need to be wired through `Custom`, which the Tier-1/Tier-2 split doesn't obviously
budget for (it assumes the model IS the generator source). `DrainsPages` is either vacuous or
wrong for `Retrieve a page property` depending which property the seeded fixture picks (§4).
`WrapsAck` doesn't apply anywhere in this sample — Notion writes return the full resource, never
a bare-ack stub. `Raw` (the uniform escape hatch) is realistically the workhorse strategy for
every block/property-touching op, which is honest but means the "auto-generated rich suite"
promise in section 8 mostly doesn't materialize for Notion's core resources.

## 10. Top gaps (ranked)

1. **No discriminated-union/`oneOf` primitive in the neutral type system (§5).** Hits 8 of 12
   sampled operations. This is the dominant, spec-breaking finding — bigger than the pagination
   or header probes the task nominated. Fix would need something like
   `kind: discriminated_union, discriminator: type, variants: {paragraph: ParagraphBody, ...}`
   added to §2's type system, plus emitter support in every target language.
2. **Pagination strategy is per-operation-static; Notion has at least one endpoint (retrieve a
   page property) where the correct strategy is chosen by the *response's* runtime type**, and
   at least two more (query a data source, search) needing a body-cursor variant the `Cursor`
   strategy's "pure mechanics, no model ref" purity claim doesn't actually support.
3. **API-versioning as a distinct axis is entirely unmodeled.** A mandatory, spec-time-literal
   version header (native, fine) is coupled — in the real world — to breaking path/shape
   migrations (`database_id`→`data_source_id`) that turn plain CRUD into multi-step
   `Custom`-handler orchestration overnight. The spec's `Custom` escape hatch covers the
   *mechanism*, but the spec has no way to flag "this operation is one call today, may become
   two tomorrow because of a version bump" — which is a maintenance/re-generation risk the
   `handler:` field alone doesn't surface.

Output file: `/tmp/claude-1000/-home-sava-dev-dev-ycli/80802223-5853-4c72-8da8-868e6f65a5f8/scratchpad/sac-research/stress/notion.md`
