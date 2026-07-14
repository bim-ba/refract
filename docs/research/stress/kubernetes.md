# refract stress test — Kubernetes API (current, v1.34-ish)

Retrieved 2026-07-14 via WebSearch/WebFetch against kubernetes.io/docs/reference. Primary sources:
- API concepts (watch, pagination, patch content-types, selectors, Status, dry-run, SSA):
  https://kubernetes.io/docs/reference/using-api/api-concepts/
- Generated API reference (Pod `log` op query params, watch-list op description):
  https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.34/
- Authentication (client certs, bearer tokens): https://kubernetes.io/docs/reference/access-authn-authz/authentication/
- Server-Side Apply (fieldManager, `application/apply-patch+yaml`): https://kubernetes.io/docs/reference/using-api/server-side-apply/
- OpenAPI serving (`/openapi/v3/apis/<group>/<version>` split-by-group-version): kube-openapi repo + kubernetes.io blog "OpenAPI V3 field validation GA"

## Verdict

**Does not fit as-is.** Kubernetes is the sharpest adversarial case yet: it confirms all three
primed suspects as hard GAPs, and surfaces a fourth, arguably more damaging one — no
cross-resource shared-model mechanism, against an API whose every single object embeds
`ObjectMeta`/`TypeMeta`. refract's "assumed scope" carve-out (§0: sync HTTP req/resp,
JSON-first) is *honest* about excluding watch/streaming, which is good — but PATCH's four
content-types and mTLS both fall inside the assumed scope and still don't fit the current
strategy registries. This API would need at least 2 new spec concepts (multi-content-type body,
transport-level auth) before code-gen, plus a model-sharing story, before it's viable.

## Operations selected (12)

| # | Operation | Verified path |
|---|---|---|
| 1 | List pods (paginated) | `GET /api/v1/namespaces/{namespace}/pods?limit=&continue=` |
| 2 | Get pod | `GET /api/v1/namespaces/{namespace}/pods/{name}` |
| 3 | List pods w/ label+field selectors | `GET /api/v1/namespaces/{namespace}/pods?labelSelector=&fieldSelector=` |
| 4 | Watch pods | `GET /api/v1/namespaces/{namespace}/pods?watch=true` |
| 5 | Get pod logs (stream) | `GET /api/v1/namespaces/{namespace}/pods/{name}/log?follow=true` |
| 6 | Create deployment | `POST /apis/apps/v1/namespaces/{namespace}/deployments` |
| 7 | Patch deployment (3 content-types) | `PATCH /apis/apps/v1/namespaces/{namespace}/deployments/{name}` |
| 8 | Apply deployment (server-side apply) | `PATCH .../deployments/{name}?fieldManager=&force=` (`Content-Type: application/apply-patch+yaml`) |
| 9 | Delete pod | `DELETE /api/v1/namespaces/{namespace}/pods/{name}` (JSON `DeleteOptions` body, optional) |
| 10 | Exec into pod (bonus, bidirectional) | `POST /api/v1/namespaces/{namespace}/pods/{name}/exec` (SPDY/WebSocket upgrade) |
| 11 | Auth: bearer token vs. mTLS client-cert | cross-cutting |
| 12 | Errors: any non-2xx | cross-cutting `Status` object |

## Per-operation axis matrix

| Op | Auth | Pagination | Body/Patch | Streaming | Selectors | Errors | Path shape |
|---|---|---|---|---|---|---|---|
| 1 List pods | native (Bearer) | **custom** (nested cursor) | — | — | — | native | native |
| 2 Get pod | native | — | — | — | — | native | native |
| 3 List w/ selectors | native | custom | — | — | native | native | native |
| 4 Watch pods | native | n/a | — | **GAP** | native | native | native |
| 5 Get logs (follow) | native | — | — | **GAP** | — | native | native |
| 6 Create deployment | native | — | native (TypedModel) | — | — | native | native (diff API group) |
| 7 Patch deployment | native | — | **GAP** | — | — | native | native |
| 8 Apply deployment | native | — | **GAP** (extends #7) | — | — | native | native |
| 9 Delete pod | native | — | native/custom* | — | — | native | native |
| 10 Exec | **GAP** (bidirectional) | — | — | **GAP** (worse than #4) | — | — | native-ish |
| 11 Auth (mTLS) | **GAP** | — | — | — | — | — | — |
| 12 Errors (Status) | — | — | — | — | — | native (w/ caveat) | — |

\* DELETE with an optional typed `DeleteOptions` body is unusual for REST but not excluded by
the op-file schema — see below.

## Axis-by-axis findings

### Auth — Bearer: native; mTLS client-cert: GAP
Bearer fits `Bearer`/`HeaderToken` cleanly: `Authorization: Bearer <token>` per
kubernetes.io/docs/reference/access-authn-authz/authentication/. Client-cert auth is a different
kind of thing entirely: the client presents an X.509 cert+key **during the TLS handshake**, not
as request data ("requires a direct connection from the client to the API server... present that
certificate to the Kubernetes API" — same source). refract's auth registry (`HeaderToken`,
`Bearer`, `ApiKey`, `Basic`, `QueryToken`, `OAuth2`, `Custom(handler)`) models auth uniformly as
*decorating an outgoing request* (headers/query/cookie/signing). None of those strategies — not
even `Custom` as described — reach into transport/session construction (which cert file, which
key file, which CA bundle, TLS verify mode). `Custom(handler: mypkg.auth:sign)`'s contract reads
as "sign this request," not "build this session." Forcing mTLS through `Custom` works only if the
handler contract is silently redefined to mean "configure the client," which the spec doesn't
say. **GAP**: the auth registry has no transport-level strategy shape. (Real k8s clients also
juggle multi-context kubeconfig credential switching, itself out of scope for a single
`security: <name>` ref per resource — worth a footnote, not a separate gap.)

### Pagination — `limit`/`continue`: near-miss/custom, not clean native
The wire mechanics match `Cursor` conceptually (§6: "envelope next-cursor field") — but the real
envelope nests the cursor: `{metadata: {continue: "...", remainingItemCount: 1000}, items: [...]}`
(verified via api-concepts.md pagination example), not a top-level sibling of the items list the
way §5's own example (`links`/`result` siblings) implies. The frozen spec's only shown
`Cursor`/`Offset` config key is `items_field` (a single top-level field name) — no evidence of a
dotted/nested field-path for the cursor token itself. Until confirmed, this needs a `Custom`
pagination handler to reach `metadata.continue`, downgrading it from a one-line built-in
config to bespoke code. Classify **custom**, not native, pending a nested-cursor-path feature.

### WATCH — confirmed GAP (as primed)
`GET .../pods?watch=true` opens a long-lived chunked-transfer-encoding connection; each line is
a raw JSON `WatchEvent` (`{type: ADDED|MODIFIED|DELETED|BOOKMARK, object: {...}}`) — "String
encoding of watchEvent is expected per line" per the generated API reference. This is
functionally newline-delimited-JSON streaming, not SSE framing, but the same category of problem
the frozen spec already anticipates and explicitly disclaims in §0 ("Streaming... expected stress
points — report as gaps, not silently"). Confirmed: refract's `responses: {200: {model:X}}`
assumes one parse of one complete body; it has no notion of "keep reading lines from this same
response forever, re-decoding per line, with a `resourceVersion` resume token and best-effort
`BOOKMARK` heartbeats." **Hard GAP**, exactly as the spec predicted for itself.

### Log streaming (`follow=true`) — GAP, and worse: even non-streaming logs are non-JSON
`GET .../pods/{name}/log` returns `Content-Type: text/plain` even without `follow` — a bare log
body, not a JSON model. That alone doesn't fit refract's "structured bodies (JSON-first)" scope
(§0) — the non-follow case is already an edge the neutral type system doesn't really cover
(`ref<Model>` implies a schema; there's no "opaque text/plain passthrough" body kind called out).
`follow=true` compounds this into an open-ended byte stream identical in kind to watch. **GAP**
(two gaps riding together: non-JSON response media type, plus long-lived streaming).

### PATCH strategies — confirmed GAP (as primed), sharper than expected
Verified three PATCH content-types on the *same* `PATCH /apis/apps/v1/.../deployments/{name}`
path — `application/json-patch+json` (RFC 6902 op-list), `application/merge-patch+json` (RFC 7386,
whole-array replace), `application/strategic-merge-patch+json` (k8s-specific, merges lists by key
via Go struct tags) — plus a fourth, `application/apply-patch+yaml` for Server-Side Apply, which
additionally requires a `fieldManager` query param and behaves as a distinct verb ("Apply") with
field-ownership tracking (`managedFields`), not just another body encoding.

The frozen spec's `body:` block (§5, §7) is **singular per operation file**: one `strategy` +
optionally one `model`. There is no list-of-`{content_type, strategy, model}` shape. Because
refract's "one operation = one file = one path+method pair" (§1, "Add op = +1 file"), and OpenAPI
itself forbids two path-items for the same `(path, method)` tuple, you *cannot* work around this
by writing 4 operation files (`patch_json`, `patch_merge`, `patch_strategic`, `apply`) — OpenAPI
would only accept that as ONE operation with `requestBody.content` holding 4 media-type→schema
entries (which OpenAPI *can* express, just not refract's current per-op `body:` field). This is a
structural GAP in the operation-file schema, not just "needs a Custom handler" — a `Custom` body
handler can pick an encoding at runtime, but the spec's declared `responses:`/`body:`/test-shape
(`RoundtripsBody`, in particular) has nowhere to say "this op supports 4 alternate bodies, generate
4 roundtrip tests, gate #4 behind a required `fieldManager` param and a different HTTP semantics
(apply vs. update)." **Hard GAP** — needs a new `body:` list-form keyed by content-type, and an
`ack`/`responses` story for `fieldManager`+`force` as SSA-specific required params.

### Selectors — native (with a caveat)
`labelSelector`/`fieldSelector` are just opaque query-string params of type `string`
(`?labelSelector=app=nginx,tier=frontend`, verified in api-concepts.md) — trivially expressible
as `params: [{name: labelSelector, in: query, type: string}]`. **Native.** Caveat: refract has no
query-DSL *builder* (turning a label dict into `k in (a,b),!c` syntax with escaping) — callers
must hand-format the string themselves. Not a spec gap (transport-only per CLAUDE.md ARCH
philosophy), just a DX note.

### Responses & errors — native, with one precision loss
The `Status` object (`kind: Status, status: Failure, message, reason: NotFound|Conflict|...,
details, code`) maps cleanly onto `responses: {404: {model: Status}, 409: {model: Status}, ...}`
— **native**, and a good structural match for refract's "typed error hierarchy from status code."
Caveat: multiple distinct `reason`s share one HTTP status (`Conflict` and `AlreadyExists` both
surface as 409) — refract's status-code-keyed exception hierarchy is coarser than k8s's own
`reason` discriminator. Data isn't lost (`reason` is still a field on `Status`), just the
auto-generated exception *type* granularity is. Minor near-miss, not a gap.

### Operation/path shape — native, but with a model-sharing gap behind it
Core resources live under `/api/v1/...` (no group segment); everything else lives under
`/apis/<group>/<version>/...` (e.g. `apps/v1`) — each combination is independently versioned and
independently served (OpenAPI v3 is split "by group-version to reduce the size of the data
transported," served per-group at `/openapi/v3/apis/<group>/<version>`). This maps fine onto
refract's one-`base_url`-per-`_resource.yaml` model: **native**, just means one resource
directory per (group, version, kind) triple rather than per logical resource family.

The sharper problem sits one level down: **every** k8s object embeds `ObjectMeta` and `TypeMeta`
(name, namespace, labels, annotations, ownerReferences, resourceVersion, managedFields, ...), and
common sub-types (`LabelSelector`, `ObjectReference`, `Toleration`, `Affinity`) are shared across
dozens of resource kinds. The frozen spec's `models:` list (§4) is declared *inside* one
resource's `_resource.yaml`, and nothing in §1/§4 shows a cross-file/cross-resource model-import
or `$ref`-to-another-resource-dir mechanism (only `_auth.yaml` is shown as a shared, root-level,
name-referenced file). Without one, every one of the dozens of Kubernetes resource directories
would need to **redefine** `ObjectMeta` verbatim, or refract needs a new `_common.yaml` /
cross-resource `ref<pkg.Model>` capability. This is arguably the highest-leverage undiscovered
gap here — it isn't in a strategy registry at all, it's in the model layer, and it hits literally
every operation, not just the streaming/patch/mTLS edge cases.

### Tests — `RoundtripsBody`/`PropertyRoundtrip` become ambiguous under PATCH
Given the PATCH gap above: if/when a multi-content-type body strategy is added, the auto-suite's
`RoundtripsBody` (round-trips **the** body through **the** model) has no natural "which of the 4
encodings" default — generating it 4x (once per content-type) is probably right but isn't
specified. `DrainsPages` would need the nested-cursor-path fix (pagination gap above) to run at
all against a real `PodList`. `ParsesModel`/`PropertyParse` are fine (native) for the JSON list/get
ops. Tier-2 `schemathesis` off the emitted OpenAPI would at least exercise whichever
content-type ends up as the *primary* schema for a PATCH op — but would silently skip the other
3 unless the OpenAPI `requestBody.content` fan-out (noted above) is actually emitted.

### Bonus: exec (`POST .../pods/{name}/exec`) — confirms scope boundary, doesn't move the verdict
A WebSocket/SPDY upgrade multiplexing stdin/stdout/stderr/resize/error channels over one
connection — strictly worse than watch/logs (bidirectional, not just server-push). Not a new
finding beyond "confirms §0's own disclaimer was right to draw the line where it did"; included
for completeness, not counted as a headline gap.

## Summary table (asks vs. findings)

| Probe | Verdict | Note |
|---|---|---|
| auth: Bearer | native | `Authorization: Bearer <token>` |
| auth: mTLS client-cert | **GAP** | transport-level, not request-decoration; `Custom` handler contract doesn't reach session/TLS config |
| pagination: `continue`+`limit` | custom (near-miss) | cursor token nested in `metadata.continue`, not top-level sibling of items |
| WATCH | **GAP** | confirmed as primed; NDJSON-per-line long-lived stream, resourceVersion + BOOKMARK resume semantics |
| log streaming (`follow`) | **GAP** | text/plain (non-JSON) even unstreamed; `follow=true` adds open-ended stream |
| PATCH (3 content-types) | **GAP** | confirmed as primed; needs list-form `body:` keyed by content-type; OpenAPI path+method uniqueness blocks the multi-file workaround |
| Server-Side Apply (4th "patch") | **GAP** (extends PATCH gap) | distinct verb semantics (`fieldManager` required, `managedFields` ownership), `application/apply-patch+yaml` |
| selectors (label/field) | native | opaque query strings, caveat: no DSL builder |
| responses/errors (`Status`) | native (caveat) | reason-level discriminator finer than status-code-keyed hierarchy |
| operation/path shape | native | per-(group,version) base_url; fits one-dir-per-resource |
| models/types | **GAP (new finding)** | no visible cross-resource model-sharing mechanism; `ObjectMeta`/`TypeMeta` duplicated across every one of dozens of resource dirs otherwise |
| tests | native w/ open questions | `RoundtripsBody`/`DrainsPages` ambiguous once PATCH/pagination gaps are patched |
| exec (bonus) | **GAP** | bidirectional WebSocket; confirms scope line, not new |
