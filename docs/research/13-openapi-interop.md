# OpenAPI/Swagger interop for refract — bidirectional mapping, gaps, IR additions

Grounded in the settled refract design (`12-architecture-language-agnostic.md`: spec → typed IR →
per-language×surface emitters, `openapi.py` as a planned "byproduct, NOT a target language"
emitter) and the actual prototype IR (`sac-prototype/apigen/ir/model.py`: `Resource`, `Operation`,
`Param`, `Model`, `Field`, `Pagination`, `Ack`, `McpMeta`, `CliMeta`, `TestCase`). `09-bakeoff-
openapi-and-runtime.md` already rejected OpenAPI-as-**authoring-format** (S2) — this doc answers
the *deferred* question doc 12 flags: OpenAPI as an **interop byproduct** (emit) and **import
front-door** (ingest), not as the spec language itself.

All primary-spec claims below were fetched directly (WebFetch/curl) from the authoritative texts
on **2026-07-14**; each is marked **CONFIRMED** with its source. Secondary/aggregator-sourced
claims are marked accordingly. Nothing here relies on training-data recall alone for a load-bearing
claim.

**Primary sources fetched this session:**
- OpenAPI 3.1.1 full spec text (raw markdown), `https://raw.githubusercontent.com/OAI/OpenAPI-Specification/main/versions/3.1.1.md` — CONFIRMED, retrieved 2026-07-14. (3.1.1 is a patch release of 3.1.0 with no normative field changes relevant here; 3.1.0's own text at `spec.openapis.org/oas/v3.1.0` is identical in substance for every clause quoted.)
- OpenAPI 3.2.0, `https://spec.openapis.org/oas/v3.2.0.html` — CONFIRMED via WebFetch, retrieved 2026-07-14 (released 2025-09, backward-compatible with 3.1).
- OpenAPI 2.0 (Swagger), `https://github.com/OAI/OpenAPI-Specification/blob/main/versions/2.0.md` — CONFIRMED, retrieved 2026-07-14.
- JSON Schema draft 2020-12, `https://json-schema.org/draft/2020-12` — CONFIRMED, retrieved 2026-07-14.
- OpenAPI Extension Registry, `https://spec.openapis.org/registry/extension/` — CONFIRMED, retrieved 2026-07-14.
- AsyncAPI current version — CONFIRMED via WebSearch (asyncapi.com), retrieved 2026-07-14.
- Speakeasy `x-speakeasy-mcp`, Redocly `x-mcp`, APIMatic `x-pagination` — CONFIRMED via WebSearch (speakeasy.com, redocly.com, apimatic.io), retrieved 2026-07-14.
- TypeSpec / Smithy status — reuses `03-external-landscape.md`'s already-cited findings (retrieved 2026-07-14 in that session) plus one fresh corroborating WebSearch this session.

---

## 1. Concept mapping — refract ↔ OpenAPI 3.1

| refract concept (IR class/field) | OpenAPI 3.1 home | Fit |
|---|---|---|
| `Resource.domain` + `Resource.resource` | No single home — informally the path prefix + an implied `tags` grouping | Loose |
| `Operation.http` + `Operation.path` | **Path Item Object** keyed by path under `paths`, HTTP-method field (`get`/`post`/…) holding an **Operation Object** — CONFIRMED, OpenAPI Object `paths` field, §4.8.6/4.8.9 | Exact |
| `Param(loc=path)` | **Parameter Object**, `in: "path"`, `required: true` mandatory — CONFIRMED §4.8.12.1 "path — … part of the operation's URL" | Exact |
| `Param(loc=query)` | Parameter Object, `in: "query"` — CONFIRMED §4.8.12.1 | Exact |
| `Param(loc=header)` — **not yet in the IR** (docstring only declares `path\|query\|body`) | Parameter Object, `in: "header"` — CONFIRMED §4.8.12.1 | Gap in refract, not in OpenAPI (see §4) |
| `Param(loc=body)` / `Operation.body_mode="typed_model"` / `body_model` | **Request Body Object** → `content` map → Media Type Object → `schema: {$ref: '#/components/schemas/<body_model>'}` — CONFIRMED §4.8.14/4.8.15 | Exact, once wired through `content` |
| `Model(kind="object")` | `components/schemas/<name>` — a JSON Schema object — CONFIRMED §4.8.7 Components Object | Exact |
| `Model(kind="root_list")` | `components/schemas/<name>` with `type: array, items: {$ref: '#/components/schemas/<item>'}` | Exact (OpenAPI has no "RootModel" concept per se, but the resulting JSON Schema shape is identical) |
| `Model(kind="envelope")` (internal per-page parse type) | Also just a schema — but its *semantic role* ("this is the raw-page wire shape a pagination strategy reads, not a public return type") has no OpenAPI marker | Schema shape: exact. Semantic role: none — needs `x-refract-pagination` (§2) |
| `Field.name/type/description/default` | Schema Object property + `description` + `required` array (default has no direct OAS analogue — see §4) | Mostly exact |
| `Field.alias` (wire name ≠ language name) | JSON Schema property keys ARE the wire name — OpenAPI has no separate "language alias" concept; that's purely a codegen/emitter concern | None — stays emitter-internal, doesn't need to round-trip through OpenAPI at all |
| `Field` nullability (`"str \| None"`) | JSON Schema 2020-12 `type` **array** form, e.g. `type: ["string","null"]` — CONFIRMED: OpenAPI 3.1.1's full spec text has **zero** occurrences of the word "nullable" (grepped the fetched raw markdown) — the OAS-3.0-only boolean `nullable` keyword was removed outright in 3.1 in favor of JSON Schema's native type-array nullability | Exact, but a **breaking 3.0→3.1 difference** to encode correctly in the emitter |
| `Operation.returns` | Success **Response Object** (typically `"200"`/`"201"`), `content.application/json.schema: {$ref: ...}` — CONFIRMED §4.8.17 | Exact for the ONE code refract tracks (see gap in §4: only one status/one model today) |
| `Operation.ack` (`Ack` synthesis for bodyless writes) | `"204"` Response Object has **no `content`, no schema, by definition** — CONFIRMED §4.8.17 example shows 204-style empty responses | None — the "wrap void into a typed `Ack.deleted(...)`" rule is pure refract convention, needs `x-refract-ack` |
| `Operation.pagination` (`Pagination` — offset/cursor/relative_cursor strategy + page fields) | **None in core OAS**, confirmed absent through 3.2.0 (WebFetch of 3.2.0 spec text, 2026-07-14: "No first-class pagination feature exists… Pagination handling remains the responsibility of individual API implementations") | None — needs `x-refract-pagination`. Real prior art exists: APIMatic's `x-pagination` vendor extension (offset/page/cursor/link strategies) is production-used but explicitly **not** an OpenAPI-official convention (CONFIRMED via WebSearch, apimatic.io, retrieved 2026-07-14) |
| `Operation.mcp` (`McpMeta`: name, `cls` safety class, title, agent `doc`) | None in core OAS | None — needs `x-refract-mcp`. Real prior art: Speakeasy's `x-speakeasy-mcp` (tool name/description/scopes for MCP generation, LLM-optimized descriptions kept separate from `description`) and Redocly's `x-mcp` (documents an MCP server on the Root Object) both already exist as vendor extensions solving an adjacent problem — CONFIRMED via WebSearch, speakeasy.com / redocly.com, retrieved 2026-07-14 |
| `Operation.cli` (`CliMeta`: command, help) + the flag→body transform | None in core OAS | None — needs `x-refract-cli`. No known vendor-extension prior art was found for CLI-flag-from-schema generation specifically (searched; nothing surfaced) |
| Internal `_verb` / public wrapper split | None — "one operation = one endpoint," no concept of an internal-vs-public HTTP primitive (already established in `09-bakeoff-openapi-and-runtime.md` §2) | None — purely a refract/emitter-side convention, does not need to appear in the emitted OpenAPI at all (the emitted doc should describe the PUBLIC wire contract only) |
| `Operation.handler` (escape hatch, `module:fn`) | None | None — needs `x-refract-handler`, and per `09`'s finding (`attachments_upload`), some ops literally can't be expressed as ONE OpenAPI operation at all (multi-step session pipelines) — no extension fixes that, it's a structural mismatch (see §2 verdict) |
| `Operation.test` (`TestCase`: fixture + authored asserts) | Loosely: Media Type Object `example`/`examples`, Schema Object (deprecated) `example`, JSON Schema `examples` keyword — CONFIRMED §"Media Type Object" — but these are **documentation examples**, not executable assertions | Weak — could dual-purpose `TestCase.response_json` as a documented example, but the `asserts` tuple has no OAS analogue; needs `x-refract-test` if round-tripping matters at all (low priority — tests aren't part of "the API surface" an OpenAPI consumer needs) |
| `Resource.base_url_ref` (symbolic base-URL key) | **Server Object** / top-level `servers` array, `url` field — CONFIRMED §"Server Object" ("A URL to the target host") | Directionally exact, but refract currently stores only a *symbol* (`tracker`/`wiki`/`forms`), not an actual URL — needs the URL value added to the IR to round-trip (see §4) |
| `operationId` — **not in the IR at all** as a distinct field (name is implicit in `mcp.name`/`cli.command`) | Operation Object `operationId`, required to be globally unique, **case-sensitive** — CONFIRMED §"Operation Object" | Gap in refract (see §4) — trivially derivable as `f"{resource}_{verb}"`, which is already exactly `McpMeta.name`'s convention |
| `tags` (the task description names this as a refract MCP concept; **absent from the actual prototype `McpMeta` dataclass** — confirmed by reading `model.py` directly) | Operation Object `tags: [string]` + a top-level `tags: [Tag Object]` array for descriptions/ordering — CONFIRMED §"Operation Object" and §"OpenAPI Object" | Direct fit once added to the IR — see §4 |
| agent-facing `documentation` (distinct from API `description`) | No OAS field is agent-specific; the closest analogue is `description` (human/tooling-facing) — CONFIRMED Operation Object `description`: "A verbose explanation of the operation behavior" | Partial — `description` can carry it in the emitted doc, but semantically conflates human docs and agent instructions unless split via `x-refract-mcp.documentation` |
| `body_dump` (`exclude_none` / `by_alias,exclude_none` — client-side serialization behavior) | None — this is a wire-*production* rule (what the CLIENT omits when sending), not a schema statement; JSON Schema's `required` list is the closest but is a *validation*, not *serialization*, concept | None — purely emitter-internal |
| Auth (`YANDEX_ID_OAUTH_TOKEN` bearer + `X-Org-Id` header — **not represented anywhere in the IR today**, hardcoded in the composition root per `CLAUDE.md`) | **Security Scheme Object** (`type: "http", scheme: "bearer"` for the token; `type: "apiKey", in: "header", name: "X-Org-Id"` for the org header) + top-level/operation `security` — CONFIRMED §"Security Scheme Object" (5 valid `type` values: `apiKey`, `http`, `mutualTLS`, `oauth2`, `openIdConnect`) | Exact fit, but a **wholesale gap** in refract today (see §4, high priority) |
| `deprecated` — **not in the IR** | Operation Object `deprecated: boolean`, Schema Object also inherits JSON Schema's own `deprecated` keyword — CONFIRMED §"Operation Object" | Gap in refract (see §4) |
| `enum` — **not in the IR** (`Field.type` is a raw type string) | Schema Object `enum` keyword (native JSON Schema) | Gap in refract (see §4) |
| `format` — **not in the IR** | Schema Object `format` keyword; OAS defines `int32`/`int64`/`float`/`double`/`password` itself and hosts a Format Registry for the rest — CONFIRMED §"Data Type Format" | Gap in refract (see §4) |
| `examples` (curated API-doc examples, distinct from `TestCase` fixtures) — **not in the IR** | Media Type Object `example`/`examples`, Parameter Object `example`/`examples` — CONFIRMED §"Media Type Object" | Gap in refract (see §4, lower priority than security/multi-response) |
| `$ref` model reuse | `components/schemas/<Name>` + `$ref` pointers — CONFIRMED §"Components Object" | **Already a natural fit** — refract's `Resource.models` tuple is already name-keyed and `Operation.returns`/`body_model` already reference models *by name string*, which is structurally identical to an OpenAPI `$ref` — the openapi emitter can do this mapping almost mechanically |
| Multiple response codes / content-types per operation — **not in the IR** (`Operation.returns` is a single model, one implicit 200) | **Responses Object**: a full status-code → Response Object map, each with its own `content` map of media-type → schema — CONFIRMED §"Operation Object" (`responses` field) and §"Responses Object" | **Real gap, high priority** — see §4 |

**One structural strength worth naming up front**: refract's `Resource.models` + string-keyed
model references (`Operation.returns: "Issue"`, `body_model: "IssueCreate"`) is already shaped
like OpenAPI's `components/schemas` + `$ref` — this is the cleanest part of the whole mapping and
needs no new IR field, just a mechanical emitter.

---

## 2. Gap A — refract → OpenAPI (what needs `x-` extensions)

### The extension mechanism, confirmed from the actual 3.1.1 spec text (§"Specification Extensions")

> "The extensions properties are implemented as patterned fields that are always prefixed by `x-`."
>
> | Field Pattern | Type | Description |
> | ---- | :--: | ---- |
> | `^x-` | Any | Allows extensions to the OpenAPI Schema. The field name MUST begin with `x-`, for example, `x-internal-id`. **Field names beginning `x-oai-` and `x-oas-` are reserved** for uses defined by the OpenAPI Initiative. The value can be any valid JSON value (`null`, a primitive, an array, or an object.) |

CONFIRMED, `raw.githubusercontent.com/OAI/OpenAPI-Specification/main/versions/3.1.1.md`, retrieved
2026-07-14. Key implications for refract's design:

1. **The pattern is a bare regex `^x-`** applied as a *patterned field* wherever a Fixed Fields
   table says "This object MAY be extended with Specification Extensions" — which is essentially
   every object in the spec: OpenAPI Object, Info, Server, Components, Paths, Path Item,
   **Operation**, Parameter, Request Body, Media Type, Responses(implicitly via Response),
   Response, Example, Tag, **Schema** (with a caveat below), Security Scheme, and more —
   individually confirmed by grepping the fetched spec text for "This object MAY be extended
   with" (20+ hits across exactly these objects).
2. **`x-oai-`/`x-oas-` are reserved** — refract must not collide with that prefix (it won't; the
   task-proposed `x-refract-*` namespace is clean).
3. **The Schema Object is special**: its own section states it "MAY be extended with
   Specification Extensions, **though as noted, additional properties MAY omit the `x-` prefix
   within this object**" — because a Schema Object is itself a JSON Schema 2020-12 document, and
   "JSON Schema Draft 2020-12 does not require an `x-` prefix for extensions" (both quotes
   CONFIRMED, §"Schema Object"). refract should still always use `x-refract-*` inside schemas too,
   for consistency and to avoid an unregistered bare keyword silently colliding with a real
   JSON Schema vocabulary keyword some future draft defines.
4. **No registry collision risk today**: the OpenAPI Initiative's own Extension Registry
   (`spec.openapis.org/registry/extension/`) lists 26 entries as of this fetch — `x-jsonschema-*`,
   `x-oai-*` compat shims, `x-codeSamples`, `x-twitter`, `x-agent-trust` — **none** for MCP,
   pagination, or CLI generation (CONFIRMED via WebFetch, retrieved 2026-07-14). The `x-refract-*`
   namespace is uncontested at the registry level.
5. **But real-world convention already exists one level down**, at the vendor-tool level, for two
   of refract's exact problems — meaning `x-refract-mcp`/`x-refract-pagination` are not a novel
   invention, they're refract's *own* vocabulary within an already-validated pattern:
   - **MCP metadata**: Speakeasy's `x-speakeasy-mcp` (tool name/description/scopes,
     LLM-optimized description kept separate from the OAS `description`) and Redocly's `x-mcp`
     (documents an MCP server, applied at the Root Object) — CONFIRMED via WebSearch,
     speakeasy.com/mcp/tool-design/generate-mcp-tools-from-openapi and
     redocly.com/docs/realm/content/api-docs/openapi-extensions/x-mcp, retrieved 2026-07-14.
   - **Pagination**: APIMatic's `x-pagination` (offset/page/cursor/link strategies, referencing
     request/response fields via JSON-pointer-like paths) — explicitly confirmed by that same
     search to be "a tool-specific extension," **not** an official OpenAPI convention — CONFIRMED
     via WebSearch, apimatic.io, retrieved 2026-07-14.
   - Because `x-mcp` and `x-pagination` are **already claimed** by other vendors with different
     shapes, refract must NOT reuse those bare names — reinforces the task's own instinct to
     namespace as `x-refract-*`.

### Proposed `x-refract-*` namespace (placement per-field, matching where OAS already allows extensions)

| Extension | Placed on | Carries |
|---|---|---|
| `x-refract-mcp` | Operation Object | `{name, safety_class, title, documentation, tags}` — mirrors `McpMeta` 1:1 |
| `x-refract-cli` | Operation Object | `{command, help, flags: [{flag, maps_to, transform?}]}` — mirrors `CliMeta`; the *declarative* flag list round-trips, the imperative transform (`--type` → `{"key": ...}`) still needs `handler:` per `09`'s finding — extensions don't remove that need, only reduce it |
| `x-refract-pagination` | Operation Object | `{strategy, page_size, envelope, extract, id_field, next_field}` — mirrors `Pagination` 1:1 |
| `x-refract-ack` | Operation Object (present only when `Operation.ack` is set) | `{factory, kind, ident, on, from_}` — mirrors `Ack` 1:1 |
| `x-refract-handler` | Operation Object | `{module_fn: "module:fn"}` — a marker, not an implementation; a standard OpenAPI tool ignores it and (correctly) has no vocabulary for what it does |
| `x-refract-internal` | Operation Object, on the raw `_verb` HTTP primitive if it's ever separately emitted | `{public_operation_id: "..."}` — flags "don't surface this as a public tool," so a naive OpenAPI consumer/emitter doesn't double-expose internals |
| `x-refract-model-kind` | Schema Object (root of a `components/schemas` entry) | `"object" \| "root_list" \| "envelope"` — preserves `Model.kind` semantics that a plain JSON Schema shape alone loses (an envelope and a public list can look identical on the wire) |
| `x-refract-test` (optional, low priority) | Operation Object | `{http_method, path, call, asserts, status, response_json}` — mirrors `TestCase`; only worth adding if round-tripping the Tier-1 test spec through OpenAPI ever matters, which it doesn't for interop, only for a hypothetical export-everything mode |

### Verdict

**(a) Can refract emit a VALID OpenAPI 3.1 doc usable by standard tooling for the API surface?**
**Yes.** Every WIRE-LEVEL fact refract's IR carries — path, method, params, body schema, one
success response schema, model definitions, `$ref` reuse — maps onto core (non-`x-`) OpenAPI
fields with no extension needed, confirmed field-by-field in §1. A generic OpenAPI consumer
(Swagger UI, a linter, `datamodel-code-generator` reading the doc back for models, `schemathesis`
for the Tier-2 test tier already planned per `12`) gets a spec-compliant, usable document that
correctly describes the HTTP contract. The **caveat**, carried over unchanged from `09`'s
concrete finding: a handful of ops (the `attachments_upload` 4-step session pipeline) cannot be
expressed as ONE OpenAPI operation at all — no extension fixes a structural mismatch between
"one HTTP call" (OpenAPI's atomic unit) and "an orchestrated sequence of calls" (what the handler
does). For those, the emitted doc should describe the sub-calls that DO exist as their own
operations (ycli's `uploadsessions` resource already does this) and mark the composed op as
`x-refract-handler`-only with no directly corresponding path — an honest degradation, not a false
claim of coverage.

**(b) Does it round-trip its own extra metadata via `x-`?** **Yes, structurally** — every refract
IR field without a core-OpenAPI home (§1's "None" rows) has a clean `^x-refract-*` slot on an
object that the spec explicitly permits extending (Operation Object, confirmed for all of them).
Round-tripping is therefore an emitter/importer engineering task, not a spec-compliance problem.

**Overall: BUILDABLE.** refract can be a well-behaved OpenAPI 3.1 citizen (the doc validates,
tooling that ignores `x-` fields still works correctly per spec — "Support for any one extension
is OPTIONAL" is itself spec text) while carrying 100% of its own metadata for a round-trip back
into itself. This validates `12`'s framing of `openapi.py` as a safe "byproduct, not a target
language" — emit it once the schemathesis tier or an external consumer needs it.

---

## 3. Gap B — OpenAPI → refract (import feasibility)

### Directly derivable from a standard OpenAPI 3.1 (or 3.0/2.0) document, no human input needed

| refract IR field | Derivation |
|---|---|
| `Resource.domain`/`resource` | From the path prefix / `tags` grouping (heuristic, needs a naming convention decision, not human *judgment*) |
| `Operation.http`/`path` | Directly copied — 1:1 |
| `Param` (path/query/header) | Directly copied — `name`, `in`, `schema.type` → refract `type` string, `required` |
| `Operation.body_mode`/`body_model` | From `requestBody.content['application/json'].schema` — if it's a `$ref`, use the ref'd name; if inline, synthesize a `Model` and name it (needs a naming heuristic, e.g. `f"{OperationIdPascal}Body"`) |
| `Model`/`Field` (from `components/schemas`) | This is exactly what `datamodel-code-generator` already does today (confirmed reusable per `09`'s verdict and `03-external-landscape.md`'s re-validation) — feed it `components/schemas` and get pydantic-v2 models close to hand-written ones |
| `Operation.returns` | From the `2xx` Response Object's schema `$ref` |
| `operationId` → refract op name | Direct copy — this is EXACTLY the field OpenAPI defines for this purpose (CONFIRMED §"Operation Object": "Unique string used to identify the operation… RECOMMENDED to follow common programming naming conventions") |
| `Resource.base_url_ref` (as a real URL, once §4's gap is fixed) | From `servers[0].url` |
| `enum`/`format`/`deprecated`/`nullable`-as-type-array (once §4's gaps are fixed) | Direct copy from Schema Object keywords |
| Security scheme shape (once §4's gap is fixed) | From `components.securitySchemes` + `security` |

**This is a real, proven pattern, not speculation**: `03-external-landscape.md` (this research
series, retrieved 2026-07-14) already found two live tools doing almost exactly this class of
import — `FastMCP.from_openapi()` (route-map-based OpenAPI→MCP-tool derivation, already a ycli
dependency) and `cnoe-io/openapi-mcp-codegen` (Apache-2.0, Python-native, Jinja2-templated,
generates an MCP server + models + client directly from an OpenAPI spec, last push 2026-05-19).
Both prove the "derive the mechanical 80%" half of the pipeline is not a research risk — it's
already shipped elsewhere for the MCP-layer subset of what refract would derive.

### CANNOT be derived — needs human augmentation

| What's missing | Why OpenAPI can't supply it |
|---|---|
| **CLI ergonomics** (`CliMeta.command`/`help`, the flag→body transform, which fields become `-F key=value` free-form vs. named flags) | Zero OpenAPI vocabulary for CLI at all (§1); this is 100% human judgment about what's ergonomic for a terminal user, not inferable from a wire schema |
| **MCP safety class** (`McpMeta.cls`: RO/WRITE/WRITE_IDEMPOTENT/DESTRUCTIVE) | HTTP-verb heuristics exist (`GET`→read-only is a reasonable default — this is literally how `FastMCP.from_openapi()`'s route-mapping and generic OpenAPI-to-MCP tools bootstrap `readOnlyHint`), **but** the DESTRUCTIVE vs. plain WRITE distinction and the WRITE_IDEMPOTENT case for a `POST` that's actually idempotent (documented ARCH-3 fail-closed rule in ycli itself) is a judgment call OpenAPI's `deprecated`/`description` prose cannot encode reliably — a heuristic import gets you a *default*, not a *correct* answer, for every write op |
| **Agent-facing `documentation`** (distinct hand-tuned prose from the human-facing `description`) | OpenAPI has exactly one description field per operation; there is no "and here's what an LLM agent specifically needs to know" slot in the standard — this must be authored, possibly generated as a first draft by an LLM off of `description` + `summary`, but not "derived" in the reliable sense the rest of this table means |
| **Pagination strategy identification** (which ops paginate, and HOW — offset vs. cursor vs. relative-cursor, what the id/next fields are called) | No core vocabulary (§1); *some* signal exists if the source doc already carries a vendor `x-pagination` (APIMatic-style) — refract's importer should opportunistically read those if present — but a bare OpenAPI 3.1 doc with only `offset`/`limit` as plain integer query params gives no signal that they compose into a drain loop at all, let alone which of refract's 3+ strategies applies |
| **`handler:` escape-hatch identification** (which ops are actually multi-step orchestrations that can't be a single generated call) | Nothing in OpenAPI marks an operation as "part of a larger choreography" unless the source used Arazzo (a separate, barely-adopted workflow spec layered on OpenAPI, not consumed by mainstream tooling per `09`'s finding) — a human has to recognize "this one POST accepts a `session_id` that came from another call" from reading the docs/API behavior, not from the spec shape |
| **Internal `_verb`/public-wrapper split** | Not an OpenAPI concept at all (§1) — every imported operation starts as a single flat "public" op; deciding some should be internal-only primitives composed by a handler is again human judgment |
| **`Ack` synthesis rule** for bodyless writes | A `204` response gives you "this write returns nothing," but not "therefore synthesize `Ack.deleted(kind, ident, on=...)`" — the *convention itself* (never return bare `None` to an agent) is refract's own house rule, not inferable |
| **Auth wiring specifics** (that `YANDEX_ID_OAUTH_TOKEN` reads from an env var at a DI composition root, not per-request) | `securitySchemes` tells you the wire shape (`bearer`, `apiKey` header) but not ycli's DI convention for where the credential comes from — that's a target-codebase convention, not an API-description fact |

### Verdict: is `refract import openapi.json` a realistic "80% scaffold + human finishes surface metadata"?

**Yes, directionally, with one important caveat on where the 80/20 split actually falls.** The
"80%" that's mechanically derivable (§ directly-derivable table above) is the SAME 80% that
`09-bakeoff-openapi-and-runtime.md`'s `issues_create` line-count study already measured as "close
to free" — path/method/params/models/$ref reuse. But `09` also measured that this 80%-of-fields
is **not 80% of the authoring effort**: for `issues_create`, the pure-OpenAPI-derivable slice (76
lines) already roughly equals the FULL hand-written line count (77 lines) while expressing
*strictly less* (no MCP annotation, no CLI ergonomics, no internal/public split). Applied to
import: a generated refract spec scaffold from OpenAPI gives you correct skeletons for
`Resource`/`Operation`/`Param`/`Model`/`Field` and `operationId`-derived names for every op — a
genuinely large time savings on the boilerplate — but every op still needs a human (or an
LLM-assisted second pass, itself human-reviewed) to fill in `CliMeta`, `McpMeta.cls` +
`documentation`, `Pagination`, and flag any op needing a `handler:`. For a **~200-operation**
migration target (the scale `12`'s "50→200 resources" framing anticipates), that's a real,
valuable accelerant — turning "write 200 YAML specs from scratch by reading API docs" into "review
and fill in 200 mechanically-scaffolded YAML specs" — but it is a scaffold-then-finish workflow,
not a fire-and-forget importer. Concretely: `refract import openapi.json --scaffold` should emit
specs with the derivable fields populated and the non-derivable fields present as explicit
`TODO`/`null` placeholders (never silently defaulted to something plausible-looking, per the same
fail-closed philosophy ARCH-3 already applies to MCP annotations) so the gate that would run
`generate.py --check` fails loudly on an unfinished import rather than silently shipping a
wrong safety class.

---

## 4. Fields refract's IR is currently missing — prioritized

Ranked by (a) how much of §1's mapping table it unblocks and (b) how load-bearing it is for
ycli's *own* real op pool (not just hypothetical OpenAPI-interop completeness):

| # | Priority | Field to add | Where (IR class) | Why |
|---|---|---|---|---|
| 1 | **High** | `security` / auth scheme declaration | New `SecurityScheme` type on `Resource` (or a shared top-level spec construct, since ycli's 3 domains share 2 auth mechanisms: bearer token + `X-Org-Id` header) | Currently **zero** representation — hardcoded in the DI composition root per `CLAUDE.md`. This is the single biggest correctness gap for an emitted OpenAPI doc: without it, the doc is *silently wrong* about how to authenticate, which is worse than the doc being incomplete. Also blocks doc-consumers (Swagger UI "Try it out", schemathesis) from working at all. |
| 2 | **High** | Multiple response codes / per-status models | `Operation.responses: tuple[Response, ...]` replacing the single `returns` field (`Response = {status, model, content_type}`) | §1's biggest structural gap. ycli's real code already has error-shape knowledge (e.g. the `issues_get` empty-2xx-as-404 sentinel guard from `09`) that a single `returns` field can't express; OpenAPI's whole `Responses Object` model assumes multiple codes are normal. Needed for both directions: emit (a spec-compliant doc SHOULD document error responses) and import (real-world OpenAPI docs always have 4xx/5xx Response Objects that get silently dropped today). |
| 3 | **High** | `Field.nullable` as an explicit type-union vs. a first-class `format`/`enum`/`deprecated` triad | `Field` gains `enum: tuple[str,...] \| None`, `format: str \| None`, `deprecated: bool = False` | All three are common, well-defined JSON Schema/OAS keywords with no refract representation today; without them the openapi emitter either drops real constraints (bad for standard-tooling validation) or the importer silently discards them from a source doc (bad for import fidelity). Cheap to add — three optional dataclass fields, no structural change. |
| 4 | **Medium** | `operationId` as an explicit field (currently only implicit via `McpMeta.name`) | `Operation.operation_id: str` | Needed to emit spec-compliant OpenAPI (`operationId` is effectively required for a doc to be useful to codegen tooling) and to make import 1:1 reversible. Low cost — it's already computable as `f"{resource}_{verb}"`, matching the existing `McpMeta.name` convention, so this is mostly "promote an existing convention to a real field," not new design. |
| 5 | **Medium** | `tags` on `Operation.mcp`/`Operation` (the task brief names "free `tags`" as a refract MCP concept; confirmed absent from the actual `McpMeta` dataclass) | `McpMeta.tags: tuple[str, ...] = ()` | Already-planned per the task's own framing of refract's model; maps directly to OpenAPI's `Operation.tags` (§1) and is also how Speakeasy's `x-speakeasy-mcp` scopes reads/writes for selective MCP-server mounting (`--read-only` is ycli's own version of exactly this) — likely useful for a future `ycli mcp start --tags=...` filter, independent of OpenAPI interop. |
| 6 | **Medium** | `servers`/base URL as a real value, not just a symbolic ref | `Resource.base_url_ref` stays as the *selector key*, but add a small `BASE_URLS: dict[str, str]` (or a `Server` IR type) that the spec loader resolves | Needed to emit a `servers` block that's actually usable by standard tooling (currently the emitted doc would have no `servers` at all, defaulting per-spec to `url: "/"` — CONFIRMED §"OpenAPI Object" — which is wrong for a doc meant to be tried against the real API) |
| 7 | **Medium** | `examples` (curated request/response examples, distinct from `TestCase` fixtures) | `Field`/`Model`/`Operation` gain an optional `examples: tuple[Example,...]` | Improves emitted-doc usability for humans/agents reading it (Swagger UI renders these), and gives the import side something concrete to seed `TestCase.response_json` from when scaffolding tests for an imported spec — a nice compounding win with Gap B's scaffold workflow, not just OpenAPI-doc politeness |
| 8 | **Low** | `Param(loc=header)` | Extend `Param.loc` from `path\|query\|body` to include `header` (per the docstring's own comment, this is a declared-but-unimplemented gap already) | Small, mechanical; unblocks describing e.g. `X-Org-Id` as a per-operation override header cleanly rather than only at the security-scheme level |
| 9 | **Low** | Content-type explicitness (currently implicitly always `application/json`) | `Operation.request_content_type`/`response_content_type: str = "application/json"` | Not currently load-bearing for Yandex 360 (JSON-only in practice per the op pool), but blocks emitting a fully-general doc and blocks importing any non-JSON API cleanly; cheap default-valued field, low urgency |
| 10 | **Low** | `x-refract-model-kind` round-trip field itself | `Model.kind` already exists in the IR (§1) — this row is really "remember to emit/read the `x-refract-model-kind` extension," not a new IR field | Listed for completeness — without it, an OpenAPI round-trip (emit then re-import) would collapse `root_list`/`envelope`/`object` into indistinguishable plain schemas |

**Not prioritized / explicitly deferred**: `TestCase`→OpenAPI round-tripping (§1, §2) — tests are
an internal Tier-1 CI concern, not part of "the API surface" any external OpenAPI consumer needs;
`x-refract-handler`'s *contents* (only the marker is worth round-tripping, never the Python body);
full Arazzo-style multi-step orchestration modeling — correctly out of scope per `09`'s finding
that the handler escape hatch, not a new spec vocabulary, is the right tool for that ~2-3-op long
tail.

---

## 5. Other standards — quick verdict

| Standard | Verdict | Basis |
|---|---|---|
| **Swagger 2.0** | **Worth importing (read-only, convert-up), not worth targeting.** Structurally close enough to 3.1 that a `2.0 → normalize to 3.1-shaped internal representation → same importer as §3` pipeline is cheap: `in` gains `formData`/`body` variants 3.x collapsed into `requestBody` (CONFIRMED, github.com .../2.0.md: `in` is `"query"`, `"header"`, `"path"`, `"formData"` or `"body"`, and "There can only be *one* body parameter"); `definitions` replaces `components/schemas` (flat, no other component kinds); `consumes`/`produces` replace per-media-type `content` maps; vendor extensions already use the identical `x-` rule (CONFIRMED, same doc: "The field name MUST begin with `x-`"). Real-world relevance: plenty of older internal/enterprise APIs (a plausible future refract-import source beyond Yandex 360) still only publish Swagger 2.0. Not worth EMITTING 2.0 — 3.1's JSON-Schema alignment and `security` model are strictly better and every mainstream tool (including `datamodel-code-generator`, confirmed still pydantic-v2-first per `03-external-landscape.md`) targets 3.x. |
| **AsyncAPI** | **Not relevant to refract's current model; revisit only if Yandex 360 grows an event/webhook surface.** Current version 3.1.0 (CONFIRMED via WebSearch, asyncapi.com, retrieved 2026-07-14, released early 2026); explicitly "protocol-agnostic" for message-driven/pub-sub APIs over Kafka/MQTT/WebSockets/AMQP/etc, not synchronous request/response REST. refract's whole IR (`verb`/`http`/`path`/`returns`) assumes call-and-response; none of ycli's Tracker/Wiki/Forms surface is event-driven today. Worth a look only if/when a Yandex 360 webhook or streaming surface appears — OpenAPI 3.1's own `webhooks` root field (CONFIRMED §"OpenAPI Object": "The incoming webhooks that MAY be received as part of this API") may cover that case first without needing AsyncAPI at all. |
| **JSON Schema 2020-12** | **CONFIRMED — this is the dialect, no separate action needed beyond correctness in the emitter.** OpenAPI 3.1's Schema Object is explicitly "a superset of the JSON Schema Specification Draft 2020-12" (CONFIRMED §"Schema Object"), with the dialect identified by `https://spec.openapis.org/oas/3.1/dialect/base` layered atop the 2020-12 base vocabularies (dialect URI `https://json-schema.org/draft/2020-12/schema`, CONFIRMED via json-schema.org). Practical upshot for refract's emitter: use `type` arrays for nullability (not `nullable` — removed in 3.1, §1), `prefixItems` if refract ever needs fixed-length tuples (replaces `items`+`additionalItems` from 2019-09 and earlier), and know that `$ref` can now have sibling keywords (2020-12's `$dynamicRef`/`$dynamicAnchor` machinery) if refract ever wants annotated-`$ref` schemas. |
| **TypeSpec** (Microsoft, alternate authoring front-door) | **One line, reusing `03-external-landscape.md`'s already-current finding**: core spec-authoring layer reached 1.0 GA, but the Python client emitter is still preview-only and there's no server/CLI/MCP emitter — not viable as a refract front-door today; the DSL's own generated-OpenAPI-is-~10x-larger-than-source ratio (CONFIRMED via this session's WebSearch, speakeasy.com/openapi/frameworks/typespec) is a reasonable data point for why refract's own compact YAML is still worth owning rather than outsourcing authoring to TypeSpec. |
| **Smithy** (AWS, alternate authoring front-door) | **One line, reusing `03-external-landscape.md`'s already-current finding**: `smithy-python` remains "in development," single-protocol, no CLI/MCP output; separately, Smithy's own OpenAPI conversion is explicitly **lossy** ("various features in a Smithy model are not currently supported in the OpenAPI conversion" — CONFIRMED via this session's WebSearch, smithy.io/2.0/guides/model-translations/converting-to-openapi.html) — not a fit as an import source OR an authoring front-door. |

**Ranking of import-source worthiness**: OpenAPI 3.1 (native target) > OpenAPI 3.0.x / Swagger 2.0
(worth a normalize-up shim, real-world prevalence) > TypeSpec/Smithy (their own OpenAPI EXPORT,
if the source project already emits one, is a better import path than refract speaking either DSL
natively) > AsyncAPI (no current fit, revisit on-demand).

---

## Summary of CONFIRMED vs. COULDN'T-VERIFY

**CONFIRMED** (primary-spec text fetched and quoted this session, 2026-07-14): the `^x-` extension
pattern and `x-oai-`/`x-oas-` reservation; which objects allow extensions (Operation Object among
them); the Schema Object's x-prefix-optional carve-out; `nullable`'s removal in 3.1 (verified by
an actual grep of the full fetched spec text returning zero hits); the JSON Schema 2020-12 dialect
URIs and alignment statement; the complete absence of a core pagination vocabulary through 3.2.0;
Swagger 2.0's `in` values, single-body-param rule, and its own identical `x-` extension rule;
Security Scheme Object's 5 valid `type` values; the Responses/Response Object multi-status-code
shape; AsyncAPI's current version and pub/sub scope; the existence and shape of `x-speakeasy-mcp`,
Redocly's `x-mcp`, and APIMatic's `x-pagination` as real (non-standard) prior art.

**COULDN'T-VERIFY** (secondary-sourced or not independently re-checked this session): the Nordic
APIs claim that OpenAPI 3.2.0 added "structured tags" — a direct WebFetch of the 3.2.0 Tag Object
fixed-fields table this session found no `parent`/`kind` hierarchy field, so that claim is either
about a non-normative convention or was imprecise reporting; flagged rather than asserted.
Smithy-python's and TypeSpec's exact current release/version numbers reuse `03-external-
landscape.md`'s own already-flagged COULDN'T-VERIFY items from its prior session (not re-checked
here, since the task named these "already assessed elsewhere").
