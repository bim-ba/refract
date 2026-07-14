# refract — spec v2 (FINAL · build blueprint)

**refract** (github.com/bim-ba/refract, MIT): a language-agnostic, spec-driven generator. Author each API
operation once in a neutral spec → a typed **IR** → pluggable emitters producing, per (target language ×
surface), a typed HTTP client + CLI + MCP server + models + tests, plus an OpenAPI 3.1 doc. **ycli is the
first consumer.** This v2 folds in the 14-API stress test (`16`). Tags: **[v1]** = build now (ycli needs
it); **[roadmap]** = add as real consumers arrive. Full research: `sac-research/00..16` + `sac-prototype/`.

## 0. Unifying principle
**Every variable axis is a strategy registry:** a set of built-in, parameterized strategies (PascalCase) +
a `Custom` strategy delegating to a hand-written `handler:`. The spec picks a strategy by name and
configures it explicitly; the emitter resolves it. New need = register a strategy; never special-case.
refract emits **committed source** (not runtime). The `Custom` handler is the release valve — but a pattern
that recurs across a whole platform (LRO, error-by-body) earns a first-class registry, not a per-op handler.

## 0.5 Scope (RATIFIED)
**In scope:** synchronous **HTTP request/response APIs** with structured bodies. **v1 non-goals (explicit,
by owner decision):** **GraphQL** (different paradigm — possible future separate mode), **streaming
responses** (SSE/watch/log-follow), **inbound receivers** (webhook/push delivery — server generation),
**interactive auth bootstrap** (OAuth2 consent, mTLS cert provisioning — refract wires a token/cert
*provider*, never does interactive consent). These are declared, not force-fit. [roadmap] may add bounded
modes later.

## 1. File layout
```
specs/
  _auth.yaml          # auth strategies (registry), referenced per resource
  _models.yaml        # [v1] shared/cross-referenced models (e.g. ObjectMeta, ErrorBody)
  <domain>/<resource>/
    _resource.yaml    # base_url, security ref, resource-local models, docs
    <operation>.yaml  # ONE operation (name + explicit path)
```
1-file-per-op; add op = +1 file. Cross-file model reuse via `ref<Name>` resolving `_models.yaml` then the
resource's own models. [v1]

## 2. Neutral type system (JSON-Schema-aligned; each emitter maps it)
`string | integer | number | boolean | list<T> | map<K,V> | ref<Model> | any` + per-field
`optional`/`enum`/`format`/`deprecated`/`default`. **Additions from stress test:**
- **`oneOf` / discriminated unions [v1]** — THE #1 universal gap (Notion blocks, OpenAI content/tool_calls,
  Stripe expandable, GitHub `string|integer`, YC oneof, Slack Block Kit, Yandex 12-union). Form:
  `type: oneOf, variants: [ref<A>, ref<B>], discriminator: type` (tagged) or variants without a discriminator
  (undiscriminated). fastmcp needs the discriminator (ycli's status-union precedent).
- **cross-file `ref<Model>`** to `_models.yaml` [v1] (k8s ObjectMeta hits every op).
- scalars/formats: int64-as-string [roadmap], raw-bytes, RFC-2822 vs RFC-3339 dates.
- **model-level `handler:` [v1]** — cross-field validators (`QuestionMove`, Event start/end) have no
  declarative home; without it a literal generator reproduces the silent-no-op bug and `PropertyParse`
  emits invalid fixtures. `handler:` extends from op-level to model-level.

## 3. Auth registry (`_auth.yaml`) — explicit config inside each object
Built-ins: **`HeaderToken`** [v1] (arbitrary headers + templates + `secrets`) · `Bearer` · `ApiKey`
(`in: header|query|cookie`) · `Basic` · `QueryToken` · **`Signer`** [roadmap] (signs over the WHOLE request
incl. body — SigV4; crosses auth/body boundary) · **`TokenProvider`** [roadmap] (exchange/refresh: OAuth2
refresh, YC IAM-JWT, Google service-account — wires a provider, no interactive consent) · **`Mtls`**
[roadmap] (transport-level cert/key/CA/verify) · **`Custom`**. Secrets inject into header/query/cookie AND
**path** [roadmap] (Twilio `{AccountSid}`, api360 org_id). Static mandatory header (`X-Org-Id`,
`Notion-Version`) = `HeaderToken` (validated).
```yaml
auth:
  oauth_token:
    strategy: HeaderToken
    headers: {Authorization: "OAuth {token}", X-Org-Id: "{organization_id}"}
    secrets: {token: env:YANDEX_ID_OAUTH_TOKEN, organization_id: env:YANDEX_ID_ORGANIZATION_ID}
```

## 4. `_resource.yaml`
```yaml
domain: forms
resource: surveys
base_url: https://api.forms.yandex.net/v1
security: oauth_token
documentation: |
  Declarative Forms /surveys client — transport ONLY.
models:
  - name: Survey
    fields: [{name: id, type: string, optional: true}, {name: language, type: string, optional: true, enum: [ru, en]}]
  - {name: SurveyList, kind: list_of, item: Survey}
  - {name: SurveysResponse, kind: envelope, fields: [{name: result, type: "list<Survey>", default: "[]"}]}
```

## 5. operation schema
```yaml
name: list
method: GET
path: surveys                       # explicit {param} templating
operationId: surveys_list
host: uploads                       # [roadmap] per-op base_url/host override (GitHub uploads, YC op-host)
documentation: |
  Every form the caller can see, auto-paginated over the API's offset pages.
params:
  - {name: offset, in: query, type: integer, default: 0}
responses:                          # EXPLICIT, status→{model}; multi-status
  200: {model: SurveysResponse}
pagination: {strategy: Offset, items_field: result, page_size: 100}
body: {strategy: TypedModel, model: IssueCreate, encoding: Json}   # writes; encoding default Json
async: {strategy: None}             # or Operation — see §8
errors: {strategy: Status}          # or BodyFlag/PartialSuccess — see §9
ack: {factory: deleted, kind: comment, ident: comment_id, on: key}
mcp: {name: surveys_list, documentation: "...", safety: read, tags: [forms]}
cli: {name: list, documentation: "List all forms (auto-paginated; --all for everything)."}
tests: {fixtures: {...}, add: [...], configure: {...}, skip: [...]}   # §11 — auto-suite by default
handler: <module>:<fn>              # escape hatch, any surface
```
Public return type is DERIVED (non-paginated = `responses.200.model`; paginated = `list<item>`).

## 6. Pagination registry
`None` [v1] · `Offset` [v1] · `Cursor` [v1] (envelope next-cursor; dotted `cursor_field` for nested —
Slack) · `RelativeCursor` [v1] (cursor = last item id) · `NextUrl` [v1] · **`LinkHeader`** [roadmap] (RFC
5988 — GitHub) · **`HeaderCursor`** [roadmap] (Tracker `X-Scroll-Id`) · **`Scroll`** [roadmap] (stateful
session open→loop→close, cross-path — ES/Tracker) · **`DeltaSync`** [roadmap] (Google `syncToken`) ·
`Custom`. Config: pure mechanics + `items_field` (dotted paths; bare-array = empty `items_field`; cursor may
live in the request body).

## 7. Body registry (mode × encoding)
**mode:** `TypedModel` [v1] · `Assembled` [v1] (scalar params → structure) · `RawDict` [v1] (allowlisted;
also free-form DSLs — TQL/ES-query, `any`) · `Base64` [v1] (base64-in-JSON) · **`FieldMask`** [roadmap] (YC
updateMask) · `Custom`.
**encoding:** `Json` [v1] (default) · **`FormEncoded`** [roadmap] (flat + nested-bracket + repeated-key —
Stripe/Twilio/Slack) · **`Multipart`** [roadmap] (OpenAI/Stripe/AWS) · **`Ndjson`** [roadmap] (ES bulk) ·
**`Xml`** [roadmap] (AWS) · **`RawBytes`** [roadmap] (≠ Base64). **content-type-keyed body list** [roadmap]
(k8s 3 PATCH types on one path+method). Serialization knob `exclude_unset|exclude_none` [v1] (Google
partial-PATCH over-sends nulls otherwise).

## 8. Async / Long-Running-Operation registry — NEW [v1]
`None` (default) · **`Operation`** [v1] — submit → poll a status resource (possibly different host/path)
until a terminal predicate → unwrap `response`/`error`. Config: `poll: {path, host?, terminal, result_field,
error_field}`. Confirmed across YC (~100% of writes), OpenAI Batch, Disk, Wiki-clone, ycli `bulk_*`. First-
class, not a `Custom` handler. CLI `--wait` drives it; MCP exposes trigger + status-read tools.

## 9. Error-model registry — NEW [v1]
`Status` (default: non-2xx → typed error hierarchy) · **`BodyFlag`** [v1] (200-wrapped: discriminate
success/error on a body field — Slack `ok`, ES `errors`, AWS `<Error>`, YC, Direct) · **`PartialSuccess`**
[roadmap] (per-item `items[].{status,error}` — ES/Slack/Direct/Google-batch) · **`CodeDiscriminator`**
[roadmap] (gRPC numeric `code` — YC) · `Custom`. **The test registry MUST read this** so `ReturnsError`
isn't wrong (Slack: stubs a 4xx the API never sends).

## 10. Cross-cutting mechanisms
- **Response-header capture** [roadmap] — cursors/ETag/rate-limit/scroll-id/multipart-ETag threading.
- **Per-op host override** [roadmap] (`host:` in §5).
- **Conditional requests / optimistic concurrency** [roadmap] (ETag/If-Match/304; ycli grids `revision`).
- **Per-call generated values** [roadmap] (Stripe `Idempotency-Key` = fresh UUID/call ≠ static secret).
- **Content negotiation** [roadmap] (Accept → different body at same status — GitHub).
- **JSON-RPC single-endpoint dispatch** [roadmap] (Direct — N logical ops on one path+method; needs a
  `dispatch` concept + a scope note that OpenAPI can't represent N ops on one (path,method)).

## 11. Test registry (rich auto-suite; DRIVEN by declared strategies)
By default the emitter applies every strategy matching the op's shape → many tests/op: `ParsesModel` ·
`ReturnsError` (per the op's **error strategy** — not a fixed 4xx) · `DrainsPages`/`RespectsLimit` (per the
op's **pagination strategy**) · `WrapsAck` · `RoundtripsBody` (per the op's **body strategy**; respects
`exclude_unset`) · `PropertyParse`/`PropertyRoundtrip` (union- and validator-aware — else vacuous) · `Raw`
(uniform escape hatch). Data via seeded `faker`. **Tiers:** Tier-1 in the 100% gate (deterministic
`responses`-stubbed; hypothesis pinned `@example`+`derandomize`); Tier-2 opt-in `schemathesis` = one global
harness off the emitted OpenAPI. The registry is per-language (Python: responses/pytest/hypothesis/faker;
TS: vitest/msw/fast-check); the spec's `strategies`/`fixtures` are neutral data. Free-form `RawDict` bodies
degrade the auto-suite — a documented, accepted tax.

## 12. OpenAPI interop
Emit valid OpenAPI 3.1; refract-only concepts round-trip under `x-refract-{auth,pagination,body,async,
errors,mcp,cli,handler}`. Import `openapi.json --scaffold` derives paths/methods/params/models(`$ref`)/
operationId/servers with loud TODO placeholders for non-derivable surface metadata. Multi-step
orchestrations and JSON-RPC dispatch can't be one OpenAPI operation → `Custom`/dispatch + partial coverage.

## 13. Emitter framework
`emit(res: Resource) -> str` per (language, surface) — the plugin boundary. Python emitters reproduce ycli
idioms (prototype: byte-identical for get/list-paginated/create/delete→Ack). Run `ruff format` (the
language's formatter) as a post-emit pass — never hand-emulate wrapping. Pure-data models may delegate to
`datamodel-code-generator`; validator-bearing models keep a hand-written region (hybrid — only ~2 ycli files).

## 14. `--check` drift gate
`refract generate --write` renders; `--check` re-renders in memory, exits 1 on any diff AND any unresolved
`handler:` import. A test invokes `--check` (mirrors ycli `gen_coverage.py --check`).

## 15. v1 BUILD SCOPE (the subset — build this first, in refract, ycli as consumer)
Neutral spec (1-file-per-op + `_resource.yaml` + `_auth.yaml` + `_models.yaml`) → typed IR → Python emitters
(models · client · cli · mcp · tests) + `--check`. Registries with the **[v1]** members only:
auth `HeaderToken`; pagination `None/Offset/Cursor/RelativeCursor/NextUrl`; body modes
`TypedModel/Assembled/RawDict/Base64` (encoding `Json`) + `exclude_unset`; **async `Operation`**;
**errors `Status`+`BodyFlag`**; type system **`oneOf`/unions + cross-file `ref` + model-level `handler`**;
`Custom` on every axis; the auto test-suite (strategy-driven). Everything **[roadmap]** is deferred backlog.

## 16. ycli migration (consumer)
Thin-slice: generator on the simplest read-ops of ONE tracker resource end-to-end, `--check` green from
commit #1; then expand op-shapes; then resource-by-resource (tracker → wiki → forms), 100% suite green
throughout. **`entities` god-resource LAST or kept hand-written.** Generator tolerates a mix (only touches
generated resources). Satisfies ARCH-1..11 by construction (ARCH-1/3/6 = free generator-correctness harness).

## 17. refract repo scaffolding (empty today; MIT)
```
refract/
  pyproject.toml   LICENSE(MIT)   README.md   .github/workflows/ci.yml
  refract/ __init__.py  ir/  loader.py  registries/{auth,pagination,body,async_,errors,tests}.py
           emitters/{python/{models,client,cli,mcp,tests}.py, openapi.py}  importer/openapi.py  cli.py
  examples/         # a sample multi-API spec set + generated output (the demo)
  tests/            # refract's own tests (loader, registries, emitters, --check, round-trip)
  docs/design.md    # THIS spec, committed here
```
ycli then: depend on refract (git dep initially), a `specs/` tree, `refract generate --check` in CI.
