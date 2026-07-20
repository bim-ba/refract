# Milestone: OpenAPI frontend (Workstream B) - DRAFT

> Directional sketch, NOT a bite-sized TDD plan. Refined later via superpowers:writing-plans once
> Workstream A's diversity-axis prerequisites (below) are closer to landing. Read-only research;
> no source touched.

## 1. Goal

Build a second `Frontend` (OpenAPI 3.1 document -> neutral IR) alongside the existing neutral-YAML
`SpecLoader`, plus a `refract scaffold <openapi.yaml>` command that turns an arbitrary real-world
OpenAPI doc into a reviewable, mechanically-derived spec scaffold.

## 2. Why / value

This is refract's stated USP: generate a typed SDK+CLI+MCP+tests bundle from an **arbitrary real
API**, not only from hand-authored neutral YAML. The redesign already names the seam explicitly -
"Frontends (input) - registry" in the hourglass diagram, with OpenAPI marked as Workstream B
(`docs/superpowers/specs/2026-07-14-refract-architecture-redesign-design.md` section 4, section 13
row "Шов `Frontend`", section 16 roadmap). `docs/design.md` section 12 and `artifacts/13-openapi-
interop.md` already did the concept-mapping legwork and reached a clear verdict: importing is
"directionally realistic" as an **80%-mechanical-scaffold + human-finishes-the-rest** workflow, not
a fire-and-forget importer (`artifacts/13-openapi-interop.md` section 3 verdict). Emitting refract's
own doc back out to OpenAPI is a separate, already-scoped byproduct (`design.md` section 12,
`artifacts/13` section 2) - this milestone is import/ingest only.

## 3. Scope IN

- An OpenAPI 3.1 parser + mapper living behind the `Frontend` seam (parallel to
  `src/refract/spec/loader.py` + `spec/schema.py`), producing the same `ir.Resource` /
  `ir.ClientConfig` the neutral-YAML frontend produces today.
- A `refract scaffold <openapi.yaml>` Typer command (sibling to today's `generate` command in
  `src/refract/cli.py`) that derives a spec scaffold from a real document.
- Mapping table (mechanically derivable slice, per `artifacts/13-openapi-interop.md` section 3):
  - `paths` + method -> `ir.Operation` (method/path/params already 1:1).
  - `parameters` (`in: path|query`) -> `ir.Param` directly; `in: header` needs a small IR gap closed
    first - `ParamSpec.loc` is `Literal["path", "query"]` only today (`spec/schema.py`, `ParamSpec.loc`), a gap
    `artifacts/13` already flags (its table, priority Low, #8).
  - `components/schemas` -> `ir.Model`/`ir.Field`, reusing `datamodel-code-generator` for the
    pure-data slice (`artifacts/03-external-landscape.md`'s "KEEP as the models emitter" verdict) -
    needs a translation layer since d-c-g's native output is pydantic source text, not refract's
    `NeutralType` grammar strings (`ref<>`/`list<>`/`map<>`, `spec/loader.py:37-54`).
  - `securitySchemes` + `security` -> `ir.AuthScheme`; `http:bearer` / `apiKey:header` map onto
    today's `HeaderAuth`/`MultiHeaderAuth` directly (`spec/loader.py:189-193`); other scheme types
    fall outside current coverage (see Dependencies).
  - `operationId` -> `Operation.operation_id` (already a real IR field, `spec/schema.py`, `OperationSpec.operation_id` -
    the gap `artifacts/13` flagged when it was written is already closed in current code).
- Validate the scaffold's mechanically-derivable output on 2-3 real OpenAPI docs end-to-end through
  `refract generate --check`.

## 4. Scope OUT / defer

- Swagger 2.0 import - worth a follow-up normalize-up shim later (`artifacts/13` section 5: "worth
  importing, not worth targeting"), not this milestone.
- Exotic OpenAPI surface: `webhooks`, Arazzo-style multi-step workflows, content negotiation
  (`Accept`-keyed multi-shape responses), anything already declared a non-goal at the architecture
  level (GraphQL, streaming/SSE - `redesign-design.md` section 15).
- Round-trip emit-back (refract IR -> OpenAPI 3.1 doc). `design.md` section 12 and
  `artifacts/13-openapi-interop.md` section 2 already scope this as a separate "byproduct"
  direction with its own `x-refract-*` extension design; this milestone is ingest-only.
- Auto-filling human-judgment fields: CLI ergonomics, MCP safety class beyond a `GET`-is-`RO`
  heuristic, agent-facing `documentation`, pagination-strategy identification. These land as loud
  placeholders, never silently defaulted - the same fail-closed principle the redesign already
  applies to MCP annotations (`artifacts/13` section 3 verdict).
- Non-JSON content types on import (XML, form-encoded) - depends on the body-encoding axis
  (`artifacts/17-milestone-design-input.md` section 2.1, phase P4), which likely isn't landed yet
  when this milestone starts.

## 5. Key phases

| # | Phase | Depends on |
|---|---|---|
| 1 | Parse + validate an OpenAPI 3.1 document into an in-memory model | - |
| 2 | `components/schemas` -> `NeutralType`/`ir.Model` mapping (reuse `datamodel-code-generator` for the pure-data slice; hand-bridge the type-string grammar) | 1; unions (Dependencies) |
| 3 | `paths`+operations -> `ir.Operation` (params, body, response); close the `Param.loc=header` gap | 2 |
| 4 | `securitySchemes` -> `ir.AuthScheme` (bearer/apiKey now; document unsupported scheme types as TODO) | 1 |
| 5 | `refract scaffold <openapi.yaml>` CLI command wiring phases 1-4 into a reviewable spec scaffold with loud placeholders for non-derivable fields | 2, 3, 4 |
| 6 | Register the OpenAPI frontend behind the `Frontend` seam (additive, no central-file edits per `redesign-design.md` decision on the registry pattern) | 5 |
| 7 | Validate end-to-end on 2-3 real OpenAPI docs (a representative path/operation subset, not the whole doc); confirm scaffold output passes `refract generate --check` | 6 |
| 8 | Write up the scaffold workflow + per-doc gaps hit (owner-facing note: derived vs. TODO) | 7 |

## 6. Dependencies

This milestone leans hard on the diversity-axis growth tracked in
`artifacts/17-milestone-design-input.md` - real OpenAPI docs will not represent faithfully in the
walking-skeleton IR without it:

| Axis needed | Why OpenAPI import hits it immediately | Source phase |
|---|---|---|
| **Multiple response codes / per-status models** | `ir.Operation.response_model` is single-valued today, first-2xx only (`spec/loader.py:133-138`); every real OpenAPI doc documents 4xx/5xx responses - importing today silently drops them. Listed HIGH priority in `artifacts/13-openapi-interop.md` section 4 (#2) independent of this milestone; likely the single biggest true prerequisite. | not yet phased in `artifacts/17`; recommend landing before or alongside phase 3 |
| **Discriminated/undiscriminated unions** | `oneOf` is the #1 universal schema-shape gap across the 15-API panel (Notion blocks, GitHub `string\|integer`, Stripe expandable) - most real `components/schemas` use it. | `artifacts/17` section 2.5, phase P1 |
| **Cross-file / shared model refs** | Real docs reuse schemas heavily (k8s-style `ObjectMeta` embedded everywhere); refract's `RefType` needs the shared-model resolution path. | `artifacts/17` section 2.5, phase P1 |
| **Error-model registry (`BodyFlag` etc.)** | Some real docs describe 200-wrapped errors; lower priority than the per-status-response gap above, but same family. | `artifacts/17` section 2.3, phase P3 |
| **Auth beyond header (`oauth2`, `mTLS`)** | `securitySchemes` in the wild aren't only bearer/apiKey; OAuth2/OIDC schemes map onto the token-provider axis, not yet built. | `artifacts/17` section 2.4, phase P6 |

External dependency: `datamodel-code-generator` (MIT, actively maintained - v0.68.1 as of
2026-07-08 per `artifacts/03-external-landscape.md`) is the one reusable external piece for models,
but it emits pydantic source text, not refract's `NeutralType` grammar - the integration depth
(direct library call vs. a one-time reference spike) is an open question below.

## 7. Rough size + anchor docs

| Phase | Size |
|---|---|
| 1. OpenAPI parse | S |
| 2. Schema -> NeutralType mapping | M (foundational; blocked on unions landing) |
| 3. Operation mapping | S-M |
| 4. Security scheme mapping | S-M |
| 5. `scaffold` CLI command | M |
| 6. Frontend registry wiring | S |
| 7. Validate on real docs | M |
| 8. Write-up | S |

**Anchor docs** (validate the mechanical slice against real, published OpenAPI descriptions):
GitHub's REST API description (`github/rest-api-description`) is a strong first anchor - already in
the 15-API sweep, exercises Link-header pagination, `oneOf` unions, and bearer auth on real
`components/schemas`. A second anchor with heavy discriminated unions (e.g. Notion, per
`artifacts/17` section 2.5's own anchor choice) would stress-test phase 2 specifically. Confirm each
candidate doc is actually published as OpenAPI 3.1 (not 3.0.x/2.0) before treating it as an anchor -
see open question Q4.

## 8. Open questions

| # | Question | Why it's genuinely open |
|---|---|---|
| Q1 | **Placeholder representation vs. the strict spec schema.** `schema.MCPToolSpec.safety` is a required `Literal["RO","WRITE","WRITE_IDEMPOTENT","DESTRUCTIVE"]` with no default and `extra="forbid"` on every node (`spec/schema.py`, `_Spec`). A scaffolded operation with no derivable safety class literally cannot produce a valid `schema.ResourceSpec` today. Does the scaffold (a) invent a conservative default (e.g. `RO` for `GET`, loudly flagged) and let strict validation pass, (b) introduce a separate, intentionally-partial "draft spec" representation distinct from `spec/schema.py`, or (c) omit unscaffoldable operations from the emitted YAML entirely and print a punch-list? This is in real tension with the redesign's own fail-loud philosophy and needs an owner call. |
| Q2 | **Scaffold output format.** Does `refract scaffold` emit human-editable neutral YAML (`resource.yaml`/`client.yaml`, immediately re-consumable by the existing `SpecLoader`, diffable and git-reviewable), or does the OpenAPI frontend build `ir.Resource` in-process and skip an intermediate spec file entirely? Recommend YAML output - matches the "review, then fill in" workflow `artifacts/13` describes, and keeps config visible/diffable rather than opaque in-process state. |
| Q3 | **`datamodel-code-generator` integration depth.** Wire it in as a real dependency call feeding refract's own type mapper from day one, or spike it standalone once (generate pydantic files, hand-port the field:type mapping) and only formalize the integration on a second real anchor doc (rule of three)? |
| Q4 | **Anchor-doc version compliance.** Some widely-cited "OpenAPI" docs from major vendors are still 3.0.x, not 3.1 (3.1's `nullable`-removal and JSON-Schema-2020-12 alignment are breaking per `artifacts/13-openapi-interop.md` section 1). Which 2-3 docs are confirmed 3.1 today, and does the importer need to accept 3.0.x too (a narrower normalize-up shim, distinct from the deferred Swagger-2.0 case)? |
