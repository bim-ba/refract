# refract spec — FROZEN baseline v1 (for stress-testing)

This is the current agreed design of the **refract** spec format, frozen as the baseline that a
fan-out of agents will stress-test by projecting real public APIs onto it. Find where an API does
NOT map, where a generated test would fail, or where anything breaks.

## 0. Unifying principle
**Every variable axis is a strategy registry.** For each axis where operations differ —
authentication, pagination, request body, tests — refract ships a registry of built-in,
parameterized strategies **plus a `Custom` strategy that delegates to a hand-written `handler`.**
The spec picks a strategy by PascalCase name and configures it explicitly; the emitter resolves it.
New need = register a strategy; never special-case. refract emits **committed source** (not runtime),
per (target language × surface: models · client · CLI · MCP · tests) + an OpenAPI 3.1 doc.

**Assumed scope (part of what the stress-test probes):** synchronous **HTTP request/response APIs**
with structured bodies (JSON-first). Streaming (SSE/WebSocket/gRPC-stream), non-HTTP, and pure-RPC
paradigms (GraphQL, SOAP) are expected stress points — report them as gaps, not silently.

## 1. File layout
```
specs/
  _auth.yaml                         # auth strategies, defined once, referenced per resource
  <domain>/<resource>/
    _resource.yaml                   # base_url, security ref, models, resource docs
    <operation>.yaml                 # ONE operation each (name + explicit path)
```
Directory = domain/resource; the URL is an explicit `path:` field. Add op = +1 file.

## 2. Neutral type system (JSON-Schema-aligned; each language emitter maps it)
`string | integer | number | boolean | list<T> | map<K,V> | ref<Model> | any`, plus per field:
`optional: true`, `enum: [...]`, `format: <s>` (date-time/uuid/…), `deprecated: true`.
(OpenAPI 3.1 schemas ARE JSON Schema; note 3.1 dropped `nullable` → we use `optional`.)

## 3. `_auth.yaml` — auth strategy registry
Built-ins: **`HeaderToken`** (arbitrary header(s) + template), **`Bearer`**, **`ApiKey`**
(`in: header|query|cookie`), **`Basic`**, **`QueryToken`**, **`OAuth2`** (flows), **`Custom`** (`handler:`).
Config is EXPLICIT inside the object (no global default headers):
```yaml
auth:
  oauth_token:
    strategy: HeaderToken
    headers:
      Authorization: "OAuth {token}"
      X-Org-Id: "{organization_id}"
    secrets:
      token: env:YANDEX_ID_OAUTH_TOKEN
      organization_id: env:YANDEX_ID_ORGANIZATION_ID
  api_key: {strategy: ApiKey, in: header, name: X-API-Key, secrets: {key: env:MY_KEY}}
  basic:   {strategy: Basic, secrets: {username: env:USER, password: env:PASS}}
  sigv4:   {strategy: Custom, handler: mypkg.auth:sign}
```
On emit → OpenAPI `securitySchemes`. Each `_resource.yaml` has `security: <name>`.

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
    documentation: "A form/survey."
    fields:
      - {name: id,           type: string,  optional: true}
      - {name: language,     type: string,  optional: true, enum: [ru, en]}
      - {name: is_published, type: boolean, optional: true}
  - {name: SurveyList, kind: list_of, item: Survey}       # RootModel[list[Survey]]
  - name: SurveysResponse                                 # per-page envelope
    kind: envelope
    fields:
      - {name: links,  type: "map<string, any>", default: "{}"}
      - {name: result, type: "list<Survey>",     default: "[]"}
```

## 5. operation file — full schema
```yaml
name: list                          # operation name
method: GET
path: surveys                       # explicit; {param} templating
operationId: surveys_list           # explicit (OpenAPI); default <resource>_<name>
documentation: |                    # multiline markdown, per op
  Every form the caller can see, auto-paginated over the API's offset pages.
params:
  - {name: offset, in: query, type: integer, default: 0}
  - {name: limit,  in: query, type: integer, default: 100}
responses:                          # EXPLICIT, always (no shorthand); multi-status supported
  200: {model: SurveysResponse}     # the WIRE response (here: one page envelope)
  404: {model: ErrorBody}
pagination:                         # strategy registry — pure mechanics, no model ref
  strategy: Offset                  # None|Offset|Cursor|RelativeCursor|NextUrl|Custom
  items_field: result               # field on the 200 model holding the page's items
  page_size: 100
# public return type is DERIVED: list<Survey> (emitter → SurveyList RootModel)
body:                               # strategy registry (writes only)
  strategy: TypedModel              # TypedModel|Assembled|RawDict|Base64|Custom
  model: IssueCreate
ack: {factory: deleted, kind: comment, ident: comment_id, on: key}   # bodyless writes → Ack.deleted(...)
mcp:
  name: surveys_list
  documentation: |                  # agent-facing, distinct from API description
    Every form the caller can see…
  safety: read                      # read|write|write_idempotent|destructive → honest hints
  tags: [forms]
cli:
  name: list
  documentation: "List all forms (auto-paginated; --all for everything)."
tests:                              # OPTIONAL — a rich suite is auto-generated from op shape
  fixtures: {survey: {faker: Survey}}
  add:    [{strategy: Raw, request: {...}, response: {...}, assert: {python: "..."}}]
  configure: {DrainsPages: {pages: 3}}
  skip:   [PropertyParse]
handler: <module>:<fn>              # escape hatch (any surface) — wired, never synthesized
```

## 6. Pagination strategy registry
`None` · `Offset` (offset+page_size) · `Cursor` (envelope next-cursor field) · `RelativeCursor`
(cursor = last item's id) · `NextUrl` (full next-page URL in body) · `Custom(handler:)`. Each: pure
mechanics + `items_field`. **Known potential gaps to probe:** Link-**header** pagination (RFC 5988,
GitHub), page-number+total (Jira startAt/total), `search_after`/scroll (Elasticsearch), keyset,
GraphQL connections/edges, no-cursor "give me everything" streams.

## 7. Body strategy registry
`TypedModel` (a pydantic request model) · `Assembled` (scalar params → dict) · `RawDict` (allowlisted
exception) · `Base64` (binary upload) · `Custom(handler:)`. **Probe gaps:** form-urlencoded (Stripe/
Twilio), multipart streaming, NDJSON bulk (Elasticsearch), XML bodies (SOAP/AWS), GraphQL query+variables.

## 8. Test strategy registry (rich auto-suite per op; spec only tunes)
By default the emitter applies EVERY strategy matching the op's shape → many tests per op:
`ParsesModel` · `ReturnsError` (one per 4xx/5xx→typed error) · `DrainsPages` · `RespectsLimit` ·
`WrapsAck` · `RoundtripsBody` · `PropertyParse` / `PropertyRoundtrip` (hypothesis: many generated
instances from the model schema) · `Raw` (uniform escape hatch: request+response+assert). Data via
seeded `faker`. **Tiers:** Tier-1 in the 100% coverage gate (deterministic `responses`-stubbed,
authored/seeded data, hypothesis pinned with `@example`+`derandomize`); Tier-2 opt-in `schemathesis`
= ONE global harness off the emitted OpenAPI (catches spec-vs-reality). Language-agnostic: the strategy
REGISTRY is per-language (Python: responses/pytest/hypothesis/faker; TS: vitest/msw/fast-check); the
spec's `strategies`/`fixtures` are neutral data. **Probe:** where would an auto-generated test FAIL or
be vacuous for a given API's real shapes?

## 9. Responses & errors
`responses:` is an explicit `status → {model}` map (multi-status). Non-2xx → a typed error hierarchy
(refract's transport maps status→exception). **Probe:** APIs with 200-wrapped errors (`ok:false` in a
200 body — Slack), per-operation error schemas, RFC 7807 problem+json, HATEOAS links.

## 10. OpenAPI interop
Emit a valid OpenAPI 3.1 doc; refract-only concepts round-trip under `x-refract-{auth,pagination,body,
mcp,cli,handler}` (the `^x-` extension mechanism). Import `openapi.json --scaffold` derives paths/
methods/params/models(`$ref`)/operationId/servers, leaving loud TODO placeholders for non-derivable
surface metadata. Multi-step orchestrations (e.g. upload = create-session→PUT→finish→attach) cannot be
one OpenAPI operation → `Custom` handler + partial coverage.

## 11. What "doesn't match" means for the stress test
For each API, per axis (auth · pagination · body · responses/errors · operation/path shape · async/
streaming · models/types · tests), classify: **native** (a built-in strategy fits), **custom** (needs a
`Custom` handler but expressible), or **GAP** (refract cannot express it — needs a new spec concept).
Report the GAPs and the near-misses loudly — those drive the spec revisions before we build.
