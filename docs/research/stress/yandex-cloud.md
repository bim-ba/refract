# Stress test: refract spec vs. Yandex Cloud API

Source: local git submodule `references/yandex-cloud/` (CC BY 4.0), commit `c5b80b2`
("Release 13.07.2026"), docs under `en/compute/api-ref/`, `en/iam/api-ref/`,
`en/vpc/api-ref/`, and the platform's own `en/api-design-guide/concepts/*.md`
(operation.md, errors.md, pagination.md, idempotency.md, about-async.md,
custom-methods.md).

## Operations sampled (12)

| # | Operation | File |
|---|---|---|
| 1 | Compute `Instance.Create` (LRO) | `en/compute/api-ref/Instance/create.md` |
| 2 | Compute `Instance.List` (pageToken) | `en/compute/api-ref/Instance/list.md` |
| 3 | Compute `Instance.Get` | `en/compute/api-ref/Instance/get.md` |
| 4 | Compute `Instance.Delete` (LRO) | `en/compute/api-ref/Instance/delete.md` |
| 5 | Compute `Instance.Update` (LRO + `updateMask`) | `en/compute/api-ref/Instance/update.md` |
| 6 | Compute `Instance.AttachDisk` (LRO, custom `:` method) | `en/api-design-guide/concepts/about-async.md` (spec), `Instance/attachDisk.md` |
| 7 | Compute `Instance.ListOperations` (nested, paginated) | `en/compute/api-ref/Instance/listOperations.md` |
| 8 | Compute `Operation.Get` (cross-host poll) | `en/compute/api-ref/Operation/get.md` |
| 9 | Compute `Operation.Cancel` (`:cancel` custom method) | `en/api-design-guide/concepts/operation.md` |
| 10 | IAM `IamToken.Create` (OAuth-token→IAM-token, one-shot) | `en/iam/api-ref/IamToken/create.md` |
| 11 | IAM token via JWT exchange (service-account key → signed JWT → IAM token) | `en/iam/operations/iam-token/create-for-sa.md` |
| 12 | VPC `Subnet.Create` (flat collection, `networkId` FK in body, not path-nested) | `en/vpc/api-ref/Subnet/create.md` |

## Axis-by-axis verdict

| Axis | Verdict | Why |
|---|---|---|
| auth — IAM Bearer usage | **native** | Once you *have* an IAM token, `Authorization: Bearer {token}` is exactly refract's `Bearer` strategy. |
| auth — OAuth-token→IAM-token exchange (op 10) | **custom** | One HTTP POST, no local crypto. Expressible as `Custom(handler:)` that does `POST /iam/v1/tokens {yandexPassportOauthToken}` → cache `iamToken`/`expiresAt`, refresh on expiry. Not a built-in registry entry, but a single small handler covers it. |
| auth — service-account JWT exchange (op 11) | **GAP** | Requires generating a JWT locally (PS256/RSA-PSS signature over `{iss, aud, iat, exp}` using a private key from a downloaded service-account key file), THEN exchanging it via the same `/iam/v1/tokens` endpoint. This is a two-stage, stateful, crypto-bearing flow with its own token cache/refresh lifecycle sitting **in front of** the resource-level `Bearer` strategy. `Custom(handler:)` can technically hold the JWT-signing + exchange + cache logic, but `_auth.yaml`'s registry has no vocabulary for "compose two auth strategies" (token-exchange strategy feeding a Bearer strategy) or for declaring the JWT claims/signing algorithm as data. Every SDK docs the same PS256/JWT boilerplate in 8 languages — exactly the kind of repeated logic the registry principle says should be a strategy, not hand-rolled per project. |
| pagination — `pageToken`/`pageSize`→`nextPageToken` (op 2, 7) | **native** | Textbook fit for `Cursor`: `items_field: instances`, cursor field `nextPageToken`, request param `pageToken`. Confirms the strategy's reason for existing. |
| pagination — `ListOperations` nested under a resource (op 7) | **native** | Same Cursor mechanics, just scoped by a path param (`instanceId`) instead of a top-level list — no new concept needed. |
| request body — Create (op 1, 12) | **native** | `TypedModel` fits; deep `$ref` nesting is exactly what `ref<Model>` composition is for. |
| request body — Update `updateMask` (op 5) | **GAP** | PATCH body = target fields + a `updateMask` field-mask string that must equal the CSV of exactly the fields the caller set (unset fields are NOT left alone if omitted from the mask — service semantics differ by mask presence). None of `TypedModel`/`Assembled`/`RawDict`/`Base64` derive "which fields were explicitly set" from a Pydantic model; you'd need `model_fields_set` + CSV-join logic in a `Custom` handler, repeated once per Update op across **every** YC service (compute alone: Instance, Disk, Filesystem, InstanceGroup, Snapshot, GpuCluster… all use identical `updateMask` shape). This is precisely a "new need = register a strategy" case the spec's own principle argues against special-casing — refract needs a first-class `FieldMask` body strategy (auto-derive `updateMask` from set fields, or let the field-mask itself be a required top-level field). |
| responses & errors — sync (op 3, get 404 etc.) | **native** | `responses: {404: {model: ErrorBody}}` fits; body is `google.rpc.Status {code, message, details}`. |
| responses & errors — status/body-code mismatch | **near-miss** | `code` is a **gRPC enum int** (0–16), not the HTTP status; two different codes collide on one HTTP status (`ALREADY_EXISTS`=6 and `ABORTED`=10 both → HTTP 409). Spec section 9 says "refract's transport maps status→exception" — HTTP-status-keyed dispatch alone can't distinguish these; the typed-error hierarchy needs to branch on the *body's* `code`, not just the response's status. `responses:` can still declare the model per status, but the emitted exception hierarchy needs an extra discriminator refract doesn't currently define. |
| responses & errors — async (LRO `error` field) | **GAP** (part of the big one below) | The *same* `google.rpc.Status` shape reappears **inside a 200 OK** body's `operation.error` when a mutation ultimately fails. This is architecturally the same "200-wrapped error" class the spec explicitly flags as a probe (Slack `ok:false`) — except here it's the *universal* mutation-failure channel for the whole platform, not an exception. `responses:` (status→model, single HTTP call) has no way to say "the logical error surface is inside a polled sub-resource's body, once `done:true`." |
| **async/long-running Operations** (op 1,4,5,6,8,9) | **GAP — the headline finding** | Every mutating call (Create/Update/Delete/AttachDisk/Start/Stop/…) returns `200 {Operation}` immediately; the actual result is obtained by polling `GET https://operation.{{api-host}}/operations/{id}` — on a **different host** than the resource's own `base_url` (`operation.` vs `compute.`/`vpc.`/…) — until `done:true`, then unwrapping `response` as the *real* per-operation typed result (`ref<Instance>` for Create, `Empty` for Delete, none for Cancel's echo) or raising from `error`. There's also `POST /operations/{id}:cancel`, a per-resource paginated `ListOperations`, and an `Idempotency-Key` header contract layered on top. Nothing in refract's operation-file schema (`responses:`, `pagination:`, `body:`, `ack:`) can express "this op's declared 200 response is a transport envelope, not the real payload; poll a **different resource on a different host** until done; unwrap `response` as `ref<X>`." Section 10 itself concedes multi-step orchestrations "cannot be one OpenAPI operation → `Custom` handler + partial coverage" — but that escape hatch was scoped for rare bespoke flows (e.g. chunked upload), not for the primary write pattern of ~100% of mutating endpoints across dozens of services with one uniform, mechanical envelope. Hand-writing a `Custom` handler per Create/Update/Delete/AttachX (dozens of times per domain, hundreds platform-wide) is exactly the special-casing the spec's unifying principle disavows. refract needs a first-class `strategy: Operation`/`LRO` **response** concept: `poll: {host: operation, path: "operations/{id}"}` (or a platform-wide default), `result_model: ref<Instance>`, optional `metadata_model:`, wired once into client/CLI ("await by default, `--no-wait` returns the operation id")/MCP (`safety:` annotation still applies to the *initiating* call) generators. |
| operation/path shape — custom `:verb` methods (op 6, 9) | **native** | `path: instances/{instanceId}:attachDisk` / `operations/{id}:cancel` are just literal strings with `{param}` templating — refract's explicit `path:` field takes them as-is. No parsing conflict since `path` isn't tokenized on `/`+`:` specially. Worth noting only because it looks unusual, not because it breaks anything. |
| file layout — the `Operation` pseudo-resource | **near-miss / structural gap** | `Operation.Get`/`.Cancel` are byte-identical across every YC domain (same 3 fields, same `operation.{{api-host}}` host, same shape) yet refract's layout is `specs/<domain>/<resource>/` — forcing either N copy-pasted `specs/<domain>/operation/_resource.yaml` files (one per domain) or an implicit convention refract doesn't currently have for a single cross-domain shared resource. This is a direct structural consequence of gap #6, not independent. |
| models/types — deep `$ref` graphs, `map<string,string>` labels | **native** | `ref<Model>` composition and `map<K,V>` handle the 8-10-level-deep nesting (`AttachedDiskSpec→DiskSpec→DiskPlacementPolicy`, `NetworkInterfaceSpec→PrimaryAddressSpec→OneToOneNatSpec→DnsRecordSpec`) and label maps fine. Volume, not shape, is the only stress here. |
| models/types — `oneOf` mutually-exclusive field groups | **GAP (typing, best-effort degrade)** | `AttachedDiskSpec.{diskSpec\|diskId}`, `DiskSpec.{imageId\|snapshotId}`, `Application.{containerSolution}` etc. are real proto `oneof`s inlined into flat JSON objects. refract's type system (`string\|integer\|number\|boolean\|list<T>\|map<K,V>\|ref<Model>\|any` + `optional`/`enum`/`format`/`deprecated`) has no union-of-field-groups concept — best you can do is mark every member `optional` and silently lose the "exactly one of" constraint (both emitted Pydantic model AND OpenAPI schema lose it, since 3.1's `oneOf` support isn't referenced in section 2). Not fatal, but a real, systematic loss across nearly every request/response model in this API. |
| models/types — protobuf-JSON int64-as-string | **near-miss** | `resourcesSpec.memory`/`.cores`/disk `size`/`pageSize` are semantically `int64` but wire-transmitted as JSON **strings** (protobuf-JSON mapping convention, since JS can't hold int64 precisely). refract's type system doesn't have this scalar: `type: integer` implies JSON-native numbers, `type: string, format: int64` would be the honest wire type but downgrades the emitted language type to `str` unless the emitter special-cases `format: int64` → coerce to Python `int`. Not documented as a supported `format` value in section 2 (`date-time/uuid/…`). Affects a large fraction of numeric fields platform-wide. |
| tests | **GAP (paired with LRO)** | None of `ParsesModel`/`ReturnsError`/`DrainsPages`/`RespectsLimit`/`WrapsAck`/`RoundtripsBody`/`Property*`/`Raw` exercise "initiate call → poll a *different host* → unwrap typed `response`/raise typed `error`." `WrapsAck` assumes a synchronous bodyless ack; Delete here is asynchronous (LRO), so even the delete-ack test shape doesn't apply as-is. `RoundtripsBody` doesn't assert `updateMask` correctness for the field-mask gap. `PropertyParse`/`PropertyRoundtrip` (hypothesis-generated instances) will happily generate `AttachedDiskSpec` fixtures with both `diskSpec` and `diskId` set (or neither) since `oneOf` isn't in the type system — vacuous or invalid generated tests unless manually excluded via `skip:`. |

## Verdict

Yandex Cloud is the harshest stress test of the five so far because its **entire
write surface** (not an edge case) runs through one mechanical, cross-host,
poll-until-done envelope. Auth is a genuine two-stage crypto flow, not just a
header template. And the update path relies on a field-mask contract repeated
identically hundreds of times platform-wide. All three interact: an LRO's
`response`/`error` unwrap needs a typed result model exactly like a sync
response does, but delivered through a second endpoint on a second host —
refract's registries (auth/pagination/body/tests) don't have a slot for
"async response," and `Custom` handlers, while technically capable, would mean
reimplementing the identical poll loop hundreds of times — the exact
special-casing the spec's unifying principle exists to prevent.

**Top 3 gaps**
1. **Long-running Operations** (create/update/delete/attach*/start/stop all return
   an `Operation` envelope; real result comes from polling `operation.{{host}}/operations/{id}`
   on a *different host* until `done`, then unwrapping `response`/`error`) — no
   first-class async/LRO response concept in the operation-file schema.
2. **IAM JWT/token-exchange auth** (service-account key → locally-signed PS256 JWT
   → `POST /iam/v1/tokens` → cached, refreshing IAM Bearer token) — a stateful,
   crypto-bearing, two-stage flow the `_auth.yaml` registry has no vocabulary for
   beyond an opaque `Custom` handler.
3. **`updateMask` field-mask body** on every Update op — none of `TypedModel`/
   `Assembled`/`RawDict`/`Base64` derive "CSV of fields the caller actually set"
   from a partial model; needs a first-class `FieldMask` body strategy.

Full report: `/tmp/claude-1000/-home-sava-dev-dev-ycli/80802223-5853-4c72-8da8-868e6f65a5f8/scratchpad/sac-research/stress/yandex-cloud.md`
