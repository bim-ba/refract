# refract stress test — Yandex 360 "other" APIs (api360, Disk, Direct)

Projected 12 real operations across three Yandex 360 APIs that sit outside the
Tracker/Wiki/Forms trio ycli already wraps, specifically chosen because their
auth/pagination/shape diverge from the "OAuth + X-Org-Id + JSON body" pattern those
three share. Sources: local vendored docs under `references/yandex-360/{api360,disk,direct}/ru/`.

## Verdict

**refract fits api360 and Disk well (native/custom, no hard blockers) but Yandex Direct
breaks two of its structural promises outright.** Direct's `{method, params}` single-endpoint
shape collides with refract's "OpenAPI 3.1 doc, one operation per path+method" deliverable
(section 10) — not just an awkward custom handler, an actual invariant violation. Its
200-wrapped whole-request errors make the `ReturnsError` auto-test strategy silently emit
**zero** tests for the entire core Direct surface. Disk confirms the spec's own prediction
about multi-step orchestration (upload/download) and additionally surfaces a **completely
unaddressed axis**: refract's strategy registries cover auth/pagination/body/tests but have
**no "async/long-running operation" registry at all**, despite section 11 explicitly listing
async as an axis to probe. api360 is the "boring" one but still surfaces a real near-miss:
`organization_id` travels as a **path parameter**, not a header — the auth registry's
`HeaderToken`/`ApiKey` strategies only support injecting secrets into headers/query/cookie,
never into the path template.

## Axis roll-up

| Axis | api360 | Disk | Direct |
|---|---|---|---|
| auth | **near-miss** — OAuth token is a header (native), but `org_id` is a **path** param sourced from the same credential; auth registry has no `in: path` injection | native — `Authorization: OAuth <token>` header only, no org scoping at all (personal disk) | native for the bearer token (`Authorization: Bearer <token>`), but `Client-Login`/`Payment-Token`/`Use-Operator-Units` are per-call business headers layered on top, not resource-wide secrets — **custom** |
| pagination | native, but **3 incompatible flavors** in one API family: `limit/offset/total` (directory gateway), `pageSize/pageToken/nextPageToken` (OrganizationsService), `count/iteration_key` (audit log) | native — `limit/offset` query params, `Offset` strategy fits; `total` present on folder listings, absent on flat `all-files` | **GAP** — `Page.Limit`/`Page.Offset` live **inside the POST body** (nested under `params`), not as query/path params; the pagination registry assumes request-level params, not a body-field path |
| request body | native — plain JSON, `TypedModel` fits | native for JSON writes; `Base64`-style upload doesn't apply — the actual byte payload goes to a **second, dynamically-returned URL**, not the operation's own body | **GAP** — body is a JSON-RPC-ish `{"method": "add", "params": {...}}` envelope; the *operation identity* lives inside the body, which the spec's `body:` strategies (TypedModel/Assembled/RawDict/Base64/Custom) don't model — needs `Custom`, and even then collides with the path/method axis (see below) |
| responses & errors | native but verbose — uniform `{code, message, details[]}` gRPC-gateway envelope repeated across 400/401/403/404/500 on **every** op file (no shorthand allowed) | native but verbose — uniform `{message, description, error}` across up to 9 status codes (400/401/403/404/406/409/413/423/429/503/507) per op | **GAP** — whole-request failures return **HTTP 200** with `{"error": {...}}" in the body (status code carries no signal); *and* batch writes 200-wrap a **per-item union** of success/error inside one array (`AddResults: [{Id}, {Errors:[...]}]`) — the neutral type system has no `oneOf`/discriminated-union type to express that array element type |
| operation/path shape | native, modulo an internal split: the legacy `cloud-api.yandex.net/v1/directory/...` gateway and the newer `api360.yandex.net/directory/v1/org/...` gRPC-gateway describe the *same* User/Group entities with **different field casing** (`department_id` vs `departmentId`) — two resources, not one | native — one path+method per logical op, `{param}` templating works throughout | **hard GAP** — ~8 logical operations (add/get/update/delete/archive/unarchive/suspend/resume) per Direct "service" all share **one identical path+method** (`POST /json/v5/campaigns`); OpenAPI 3.1 permits exactly one Operation Object per (path,method) pair, so refract's "emit a valid OpenAPI 3.1 doc" promise (§10) cannot represent Direct without either faking distinct paths or collapsing 8 CLI/MCP/SDK operations into one `oneOf`-discriminated mega-operation |
| async / long-running | native — no long-running ops in the sampled set | **GAP** — copy/move/delete/restore on non-empty resources return `202 Accepted` + a `Link` to a *separate* `/v1/disk/operations/{id}` you must poll for `{status: success\|failed\|in-progress}`; upload/download are 2-step (get a `Link`/`Link-upload` object, then hit a **different host**, no auth header, with a **dynamically supplied** HTTP method) — refract has **no async/polling strategy registry at all** (only auth/pagination/body/tests are registries) despite §11 naming this as a probe axis | **GAP, a different flavor** — the Reports service polls by **resending the identical request** (200=ready, 201=queued, 202=still generating, real distinct status codes here, unlike core CRUD), and the eventual payload is **TSV, not JSON** — a non-JSON-Schema response body the neutral type system can't model as a `ref<Model>` |
| models/types | native — flat records, nested `ref<Model>` composition suffices | mostly native; `Resource._embedded` is self-referential (`ResourceList` contains `Resource[]`) — plausible via JSON-Schema `$ref` but untested by the spec's brief type list | **GAP** (same root cause as responses/errors) — `CampaignGetItem.{TextCampaign,MobileAppCampaign,CpmBannerCampaign,UnifiedCampaign}` is a `Type`-discriminated union where only one of four sibling fields is populated; no discriminator/oneOf concept exists to express "populated iff Type == X" |
| tests | native — `ParsesModel`/`ReturnsError`/`DrainsPages` all meaningful | **weak** — `WrapsAck` assumes one bodyless-or-not shape per op, but Disk deletes/restores are *conditionally* 204 (sync) or 202+Link (async); none of the 8 canned Tier-1 strategies is "poll until terminal," so the actually-meaningful test for every async Disk op falls through to hand-written `Raw` | **GAP, concretely demonstrated** — `ReturnsError` is keyed off HTTP status; since Direct's core CRUD never returns 4xx/5xx (errors are 200-wrapped), this canned strategy silently emits **zero** error tests for Ads/Campaigns/Keywords/etc., even though errors are common (see the `AddResults` per-item union above). `PropertyParse`/hypothesis generation would also produce **invalid** instances for `CampaignGetItem` (populating all four campaign-type sub-objects at once) because the type system has no way to encode the "only one populated" constraint |

## The 12 operations projected

**api360** (`cloud-api.yandex.net` + `api360.yandex.net`, OAuth token, org_id-in-path):
1. `GET /v1/directory/organizations/{org_id}/users` — list, Offset pagination (native)
2. `PATCH /v1/directory/organizations/{org_id}/users/{user_id}` — write, snake_case legacy model (native)
3. `POST https://api360.yandex.net/directory/v1/org/{orgId}/users/{userId}` (UserService.Update) — write, camelCase gRPC-gateway model, same conceptual entity as #2 but incompatible field names (near-miss)
4. `POST https://api360.yandex.net/directory/v1/org/{orgId}/groups/{groupId}/members` — write with polymorphic `type: user|group|department` (native)
5. `GET /v1/auditlog/organizations/{org_id}/events` — Cursor pagination via `count`+`iteration_key`, comma-joined multi-value filters (native, fiddly)
6. `GET https://api360.yandex.net/directory/v1/org` (OrganizationsService.List) — third pagination flavor, `pageSize`/`pageToken`/`nextPageToken` (native)

**Disk** (`cloud-api.yandex.net`, OAuth token, no org scoping):
7. `GET /v1/disk/resources/upload` → `PUT <returned href>` — two-phase upload; step 2 hits a dynamic host, no auth, dynamic method (GAP)
8. `GET /v1/disk/resources/download` → `GET <returned href>` (200 body or 302 redirect) — two-phase download, binary response (GAP)
9. `POST /v1/disk/resources/copy` — 201 (sync, `Link` to meta) vs 202 (async, `Link` to `/operations/{id}`) (GAP: async)
10. `GET /v1/disk/operations/{id}` — poll target for #9/trash-restore (native in isolation)
11. `GET /v1/disk/resources/files` — flat listing, Offset pagination, no `total` (native)

**Direct** (`api.direct.yandex.com`, Bearer token, `Client-Login`/`Payment-Token` headers, no org scoping):
12. `POST /json/v5/campaigns` `{"method":"get","params":{"SelectionCriteria":{...},"Page":{"Limit":..,"Offset":..}}}` — JSON-RPC shape, body-embedded pagination, discriminated-union response (GAP × 3)
13. `POST /json/v5/ads` `{"method":"add",...}` — batch write, 200-wrapped per-item success/error union (GAP)
14. `POST /json/v5/reports` — TSV body, resend-to-poll async, genuine distinct status codes unlike its siblings (GAP)

## Top gaps (ranked)

1. **Direct's `{method, params}` single-endpoint shape breaks refract's OpenAPI-emission
   invariant, not just its ergonomics.** ~8 logical operations per Direct service
   (add/get/update/delete/archive/unarchive/suspend/resume) share one identical
   `POST /json/v5/<service>/` path+method pair. OpenAPI 3.1 allows exactly one Operation
   Object per (path, method); refract's "one operation file = one path/method, emit a valid
   OpenAPI 3.1 doc" design (§1, §10) has no way to represent this without either fabricating
   fake distinct paths (dishonest OpenAPI) or collapsing N logically-distinct CLI/MCP/SDK
   operations into one `oneOf`-discriminated body — which additionally requires a union/
   discriminated-union type the neutral type system doesn't have (§2's list is
   `string|integer|number|boolean|list|map|ref|any`, no `oneOf`).
2. **No async/long-running strategy registry exists**, despite §11 naming it as a probe axis.
   Disk's copy/move/delete/restore-on-non-empty-resource (202 + poll a separate operations
   resource) and Direct's Reports service (resend-the-same-request-to-poll, non-JSON TSV body)
   are two *different* async flavors that both fall outside the four documented registries
   (auth/pagination/body/tests). Everything routes to `Custom`, but the spec has zero
   vocabulary for "issue this request, then poll a status resource/re-issue until terminal" —
   a common enough pattern (Google-style long-running operations) to deserve its own registry
   like pagination has.
3. **200-wrapped errors make `ReturnsError` silently vacuous for Direct's core CRUD**, while
   the same API's Reports sub-service uses real HTTP status codes — so the identical canned
   test strategy is meaningful for one Direct resource and empty for another, with no signal
   in the spec to tell which. Combined with the per-item `AddResults` success/error union
   (also un-typeable), Direct is where the "auto-generated test would be vacuous or wrong"
   probe (§8) lands hardest.

Runner-up near-misses worth a spec note: `organization_id` as a **path** parameter in api360
(the auth registry only injects secrets into headers/query/cookie); pagination params living
**inside the POST body** for Direct (registry assumes request-level `params:`); and three
mutually-incompatible pagination flavors coexisting inside one nominal "api360" API.

Full report: `/tmp/claude-1000/-home-sava-dev-dev-ycli/80802223-5853-4c72-8da8-868e6f65a5f8/scratchpad/sac-research/stress/yandex-360-other.md`
