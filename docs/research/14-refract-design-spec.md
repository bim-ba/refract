# refract — design spec (v1)

**refract** is a language-agnostic, spec-driven generator: author each API operation once in a neutral
spec → a typed **intermediate representation (IR)** → pluggable emitters that produce, per target
language and per surface, a typed HTTP client + CLI + MCP server + models + tests (+ an OpenAPI doc).
Standalone public repo `github.com/bim-ba/refract`; **ycli is the first consumer** (its ~230-op
tracker/wiki/forms wrapper). This spec is the validated design from a multi-cycle research effort
(session scratchpad `sac-research/00..13` + a runnable prototype in `sac-prototype/`).

## 1. Goals / non-goals
**Goals:** one authored spec → N surfaces × M languages, committed reviewable source, py.typed-grade
static types, a `--check` drift gate, an escape hatch so no operation is ever un-expressible, and
bidirectional OpenAPI interop. **Non-goals:** runtime metaprogramming (breaks static types / coverage
/ file-coupled invariants — see `01`§1, `10`); adopting an external SDK toolchain (Fern/Stainless —
foreign identity, rejected in `03`); a universal runtime — refract emits source, it is not a library
you call at runtime.

## 2. Architecture (four layers, strict downward dependency)
```
1. SPEC     specs/<domain>/<resource>/{_resource.yaml, <op>.yaml}   — neutral YAML, no language
      │  loader + a pydantic validation schema (reject malformed specs; extra=forbid)
2. IR       refract/ir/*.py — frozen typed dataclasses. Language- AND surface-neutral. The product.
      │  emitters read ONLY the IR.
3. EMITTERS refract/emitters/<language>/<surface>.py  →  emit(res: Resource) -> str
      │  python/{models,client,cli,mcp,tests}  (+ openapi.py byproduct)   typescript/… later
4. OUTPUT   generated committed source in the consumer repo (ycli)  +  emitted openapi.json
```
Extension points: new op-shape = one IR field + a localized emitter clause (`ty`+`assert_never` force
exhaustiveness); new language = a new `emitters/<lang>/` dir over the unchanged IR; new surface = a new
emitter file. The emitter signature `emit(res) -> str` is the plugin boundary.

## 3. Spec format
### 3.1 Granularity (decided): **1 file = 1 operation + explicit `path:` + a shared `_resource.yaml`**
```
specs/forms/surveys/
  _resource.yaml     # base_url, models, resource-level docs, security ref
  list.yaml          # one operation
  get.yaml
  create.yaml
  delete.yaml
```
Add op = +1 file; delete op = −1 file (file deletion is authoritative). Directory = domain/resource;
the URL lives in each op's explicit `path:` field (OpenAPI-compatible `{param}` templating — avoids
directory URL-encoding edge cases like `issues/{key}/transitions/{id}/_execute`).

### 3.2 Neutral type system (decided — required for language-agnosticism)
Types are JSON-Schema-aligned, NOT Python strings: `string | integer | number | boolean | list<T> |
map<K,V> | ref<Model> | any`, plus per-field `optional: true`, `enum: [...]`, `format: <s>` (e.g.
date-time/uuid), `deprecated: true`. Each language emitter maps them (Python: `string`+optional →
`str | None`; TS: `string?`). OpenAPI 3.1 schemas ARE JSON Schema, so this maps 1:1 (note: 3.1 dropped
`nullable`; use the neutral `optional`).

### 3.3 `_resource.yaml`
```yaml
domain: forms
resource: surveys
base_url: https://api.forms.yandex.net/v1     # real servers URL (was symbolic base_url_ref)
security: oauth_token                          # → a scheme defined once in specs/_security.yaml
documentation: |
  Declarative Forms /surveys client — transport ONLY.
models:
  - name: Survey
    documentation: "A form/survey."
    fields:
      - {name: id,           type: string,  optional: true}
      - {name: name,         type: string,  optional: true}
      - {name: language,     type: string,  optional: true, enum: [ru, en]}
      - {name: is_published, type: boolean, optional: true}
  - {name: SurveyList,      kind: list_of, item: Survey}          # RootModel[list[Survey]]
  - name: SurveysResponse
    kind: envelope                                                # internal per-page parse type
    fields:
      - {name: links,  type: "map<string, any>", default: "{}"}
      - {name: result, type: "list<Survey>",     default: "[]"}
```

### 3.4 operation file (full field set; simple ops stay tiny via defaults)
```yaml
name: list                       # operation name (was verb)
method: GET                      # (was http)
path: surveys                    # explicit; {param} templating
operationId: surveys_list        # explicit (OpenAPI); default = <resource>_<name>
documentation: |                 # multiline markdown, per operation
  Every form the caller can see, auto-paginated over the API's offset pages.
params:
  - {name: offset, in: query, type: integer, default: 0}
  - {name: limit,  in: query, type: integer, default: 100}
returns: SurveyList              # shorthand for responses:{200:{model: SurveyList}}
# responses:                     # full form when >1 status matters
#   200: {model: SurveyList}
#   404: {model: ErrorBody}
pagination:                      # ONLY pagination fields (return model is `returns`, not here)
  strategy: offset               # none|offset|cursor|relative_cursor|next_url
  page_size: 100
  envelope: SurveysResponse
  items_field: result
mcp:
  name: surveys_list
  documentation: |               # agent-facing, distinct from the API description
    Every form the caller can see, auto-paginated…
  safety: read                   # read|write|write_idempotent|destructive → honest ARCH-3 hints
  tags: [forms]                  # free fastmcp tags; the `write` tag auto-added for non-read
cli:
  name: list                     # unified {name, documentation} (was command/help)
  documentation: "List all forms (auto-paginated; --all for everything)."
tests:                           # an array
  - name: lists two surveys
    request:  {method: GET, path: surveys}
    response: {status: 200, json: {links: {}, result: [{id: a}, {id: b}]}}
    call: "list()"
    assert: {python: '[s.id for s in result.root] == ["a", "b"]'}   # per-language; → neutral DSL later
```
**Write op** adds `body: {mode: typed_model, model: IssueCreate}` (or `assembled` / `raw_dict` /
`base64`) and `mcp.safety: write|write_idempotent`. **Bodyless write** adds `ack: {factory: deleted,
kind: comment, ident: comment_id, on: key}` → `Ack.deleted("comment", comment_id, on=key)`.
**Escape hatch**: `handler: <module_path>:<fn>` (any surface) points at a hand-written function the
emitter WIRES but never synthesizes — for multi-step uploads, validator guards, the `set_permissions`
dict exception. `--check` resolves every handler import so a bad ref fails the gate, not runtime.

## 4. The IR (frozen dataclasses; extends the prototype with the OpenAPI-informed fields)
`Resource(domain, resource, base_url, security, documentation, models, operations)`;
`Model(name, kind, fields, item, documentation, config)` kind ∈ object|list_of|envelope;
`Field(name, type, optional, default, alias, enum, format, deprecated, documentation)`;
`Param(name, loc[path|query|header], type, default, documentation)`;
`Operation(name, method, path, operationId, params, responses{status→model}, pagination, body,
ack, mcp, cli, tests, handler, documentation)`;
`Pagination(strategy, page_size, envelope, items_field, cursor_field, id_field)`;
`Mcp(name, documentation, safety, tags)`; `Cli(name, documentation)`;
`Body(mode, model)`; `Ack(factory, kind, ident, on, from_)`; `SecurityScheme(name, kind, …)`;
`TestCase(name, request, response, call, asserts_by_language)`.

## 5. Emitters
`emit(res: Resource) -> str` per (language, surface). Python emitters reproduce ycli idioms exactly
(prototype proved byte-identical output for get/list-paginated/create/delete→Ack). **Formatting:** run
`ruff format` (or the language's formatter) as a post-emit pass — do NOT hand-emulate line-wrapping
(the prototype's one real tax). The Python `models` emitter may delegate to `datamodel-code-generator`
for pure-data models and hand-off validator-bearing models to a preserved hand-written region (hybrid,
`10`§models — only ~2 of ycli's model files carry validators).

## 6. OpenAPI interop (bidirectional; `13`)
- **Emit** (`emitters/openapi.py`): IR → a VALID OpenAPI 3.1 doc. Wire facts map to core fields; every
  refract-only concept round-trips under `x-refract-{mcp,cli,pagination,handler,ack}` (the `^x-`
  extension mechanism is confirmed-permitted on every object; namespace is uncontested in the official
  registry). Enables schemathesis (Tier-2 tests) + ecosystem interop. Honest limit: a multi-step
  orchestration (upload) can't be one OpenAPI operation → mark `x-refract-handler`, cover partially.
- **Import** (`refract import openapi.json --scaffold`): derive paths/methods/params/models(`$ref` via
  datamodel-codegen)/operationId/servers; emit explicit TODO placeholders (never silent defaults) for
  the non-derivable surface metadata (CLI ergonomics, MCP safety+docs, pagination, handlers) so
  `--check` fails loudly until a human finishes. Swagger 2.0 = import-only.

## 7. Tests (2 tiers; `11`)
- **Tier 1 — in the 100% gate, deterministic:** generated stubbed unit tests (Python: `responses`)
  whose asserts are **authored DATA** (never emitter-computed → not a tautology; non-vacuous because
  models are generated from a separate source than ops). Neutral fixtures (request/response) + a
  per-language assert block. Optionally enriched with seeded-faker fixtures + `@example`-pinned,
  `derandomize=True` property tests as ADDITIVE checks — never the sole cover of a line.
- **Tier 2 — opt-in / nightly, outside the gate:** schemathesis against a mock (or real API) built from
  the emitted OpenAPI — the only thing that catches spec-vs-reality path drift.
Language-agnostic: fixtures are data; hypothesis/faker are Python realizations of neutral intent
(`property: true`, `examples: [...]`), each language emitter maps to its own libs (TS: fast-check/faker.js).

## 8. `--check` drift gate
`refract generate --write` renders the tree; `--check` re-renders in memory, exits 1 on any diff AND on
any unresolved `handler:` import. A test invokes `--check` (same proven pattern as ycli's
`gen_coverage.py --check` / `test_coverage_readme.py`). Generated files can never silently drift.

## 9. ycli migration (consumer side)
Thin-slice-first: build the generator on the simplest read-ops of ONE tracker resource end-to-end with
`--check` green, then expand op-shapes, then resource-by-resource (tracker → wiki → forms), 100% suite
green at every step. **`entities` god-resource migrated LAST or kept hand-written** (pathological: flat
`<res>_<sub>_<verb>`, dict body). The generator tolerates a mix (it only touches `out/` for spec'd
resources; hand-written ones are untouched). Update `ARCHITECTURE.md` + its checks in the same PR if the
layout shifts. Generated output satisfies ARCH-1..11 by construction (the ARCH-1/3/6 tests become a free
generator-correctness harness).

## 10. refract repo structure (empty today — needs scaffolding)
```
refract/
  pyproject.toml   LICENSE(choose: MIT/Apache-2.0)   README.md   .github/workflows/ci.yml
  refract/ __init__.py  ir/  loader.py  emitters/{python/,openapi.py}  importer/openapi.py  cli.py(generate/import/check)
  examples/         # a tiny sample API spec + its generated output (the demo)
  tests/            # refract's own tests (loader, emitters, --check, round-trip)
  docs/design.md    # this spec, committed here once approved
```
ycli then: `uv add refract` (or a git dep initially), a `specs/` tree, `refract generate --check` in CI.

## 11. Open decisions (for owner)
1. **License** for the public repo (MIT vs Apache-2.0 — Apache-2.0 gives an explicit patent grant; MIT is
   simplest/most permissive).
2. **Neutral assert DSL now vs per-language assert snippets first** (I lean: snippets first, DSL when a 2nd
   language lands).
3. **How aggressively to seed the IR with the OpenAPI-informed fields** now (security/multi-response/
   examples) vs add them as the first real op that needs each (I lean: add `enum/format/optional/operationId`
   now — cheap; defer `security`/multi-response/examples until the first op needs them, but reserve the IR slots).
4. **First build milestone**: the thin-slice generator in refract emitting one tracker resource, wired back
   into ycli behind `--check` — confirm this as PR #1's scope.
