# Stress test: refract vs. GitHub GraphQL API

**Target:** GitHub GraphQL API (branded "v4" historically vs. REST "v3"; GitHub docs now just call
it "the GraphQL API"), as a representative of the GraphQL paradigm generally.
**Endpoint:** `POST https://api.github.com/graphql` (single endpoint for all queries/mutations).
**Spec read:** `15-refract-spec-frozen.md` (frozen baseline, this session).
**Retrieval date:** 2026-07-14, via WebSearch against docs.github.com/graphql (current docs).

---

## 0. Verdict up front

**GraphQL is fundamentally out of refract v1's scope — not a missing strategy, a missing paradigm.**
The spec itself flags this pre-emptively (§0: "pure-RPC paradigms (GraphQL, SOAP) are expected
stress points — report them as gaps, not silently"); this stress test confirms the call was
correct and shows *why* it's not a shallow gap. The deepest incompatibility (§3 below —
client-selected response shape) inverts refract's core premise (server-author defines one fixed
model per response, reused across callers). That premise is baked into `_resource.yaml` (models
defined once, referenced by `responses:`), the emitter (`OpenAPI 3.1` + typed models + hypothesis
tests all keyed to a schema *the resource author wrote*), and the whole "committed source"
philosophy. It cannot be patched with one more `Custom` strategy.

**Could refract support GraphQL as a separate mode?** Only as a near-total fork, not an extension.
A GraphQL mode would need: GraphQL SDL/introspection JSON as the schema source (not
`_resource.yaml` models), a corpus of hand-authored `.graphql` query/mutation *documents* as the
spec's primary unit (not `<operation>.yaml`), introspection-driven per-document codegen for
response types (à la `graphql-codegen`/Relay compiler, not `responses: {200: {model: X}}`), and
GraphQL SDL as the emitted contract artifact instead of OpenAPI 3.1. Realistically shared surface
with REST-mode refract: the `Bearer` auth strategy verbatim, the `Custom` handler escape-hatch
*pattern*, and the aspiration of one spec → 4 surfaces. Everything else — operation/path shape,
body registry, response registry, pagination's `items_field` addressing, OpenAPI interop — is
structurally incompatible, not just unimplemented.

---

## 1. Ten representative operations

| # | Operation | GraphQL shape | Why picked |
|---|---|---|---|
| 1 | `viewer` query, nested selection | `query { viewer { login name repositories(first:10){ nodes{ name } } } }` | client-chosen nested field tree |
| 2 | `repository.issues` paginated connection | `query($owner:String!,$name:String!,$after:String){ repository(owner:$owner,name:$name){ issues(first:50, after:$after, states:OPEN){ edges{ cursor node{ id title } } pageInfo{ hasNextPage endCursor } } } }` | Relay connection pagination |
| 3 | `createIssue` mutation | `mutation($input: CreateIssueInput!){ createIssue(input:$input){ issue{ id number title } clientMutationId } }` | Input/Payload mutation pattern |
| 4 | `addComment` mutation | `mutation($input: AddCommentInput!){ addComment(input:$input){ commentEdge{ node{ id } } clientMutationId } }` | write with `clientMutationId` idempotency token |
| 5 | `search` query, union type | `query($q:String!){ search(query:$q, type:ISSUE, first:20){ nodes{ ... on Issue{ title } ... on PullRequest{ title } } } }` | polymorphic response via inline fragments |
| 6 | `node(id:)` global object identification | `query($id:ID!){ node(id:$id){ id ... on Repository{ name } } }` | Relay `Node` interface, no REST-style path-per-resource |
| 7 | `rateLimit` meta field | `query { rateLimit{ limit cost remaining resetAt } viewer{ login } }` | side-channel metadata riding inside every response, not a status/header |
| 8 | `updatePullRequest` mutation | `mutation($input: UpdatePullRequestInput!){ updatePullRequest(input:$input){ pullRequest{ id title } } }` | partial-update mutation, variables-driven |
| 9 | `repository` query with scalar variables | `query($owner:String!,$name:String!){ repository(owner:$owner,name:$name){ id description } }` | baseline "query + variables" shape |
| 10 | Aliased multi-root batched query | `query { repoA: repository(owner:"a",name:"x"){ id } repoB: repository(owner:"b",name:"y"){ id } }` | one wire call = N logically distinct "operations" |

---

## 2. Axis-by-axis classification

| Axis | Verdict | Why |
|---|---|---|
| Auth | **native** | `Authorization: Bearer <token>` maps 1:1 to refract's built-in `Bearer` strategy. |
| Operation/path shape | **GAP** | Single endpoint, always `POST /graphql`; `method:`/`path:` fields are meaningless. Aliasing (op 10) lets one wire call carry N logical operations — the reverse of refract's 1 file = 1 operation = 1 wire call assumption. |
| Request body | **GAP** (variables sub-part near-miss) | Body is `{query: "<GraphQL document string>", variables: {...}}`. The `query` string is a *program*, not data — no analog in `TypedModel/Assembled/RawDict/Base64`. `variables` alone could map to `TypedModel` (GraphQL input types are already typed), but only for a hand-frozen query — i.e., effectively demoted to `Custom`. |
| Responses | **fundamental GAP** | `data`'s shape is defined by the *client's* selection set for that specific call, not a fixed server-authored model. refract's `responses: {200: {model: X}}` assumes one reusable model per operation, authored once in `_resource.yaml`. GraphQL needs a response type *per query document*, derived from schema introspection — a different codegen foundation entirely (see §3 below). |
| Pagination | **GAP** (near-miss on mechanics) | Relay `edges{node,cursor}` + `pageInfo{hasNextPage,endCursor}` (op 2) structurally *rhymes* with refract's `Cursor` strategy at the leaf (opaque cursor, boolic more-flag). But `items_field` assumes one flat top-level field; Relay connections nest at arbitrary depth and multiple connections can coexist in one query (e.g. `issues` and `pullRequests` both paginated in the same request) — `items_field` would need to become a path, and the "one pagination strategy per operation" assumption breaks. |
| Errors | **GAP** | Always HTTP 200; `errors[]` rides *alongside* `data` in the same 200 body, keyed by `path`/`locations`/`type`/`message`, with `data` possibly partially populated (nulls for the failed subtree, other siblings still returned). refract's `responses: {404: {model}}` keys errors to HTTP status — never fires here. Same family as the spec's pre-flagged Slack `ok:false` gap, but worse: per-field paths + partial success, not a single top-level flag. |
| Tests | **mostly GAP** | `ParsesModel`/`PropertyParse`/`PropertyRoundtrip` need a fixed model (blocked by the responses GAP). `ReturnsError` triggers on 4xx/5xx, which never happens; it would need to inspect `errors[]` inside a 200. `WrapsAck` assumes bodyless writes; GraphQL mutations always return a typed Payload. `DrainsPages`/`RespectsLimit` are portable *if* the pagination gap above is fixed first. |
| Models/type system | **GAP** (bonus axis) | Op 5's `SearchResultItem` union (`Issue \| PullRequest \| Repository \| User \| Organization`) resolved via inline fragments has no equivalent in refract's neutral type grammar (`string\|integer\|number\|boolean\|list<T>\|map<K,V>\|ref<Model>\|any`) — no union/interface/discriminated-oneof concept. |
| OpenAPI interop | **GAP** (bonus axis) | GitHub GraphQL's contract is an SDL/introspection schema, not `openapi.json`. `--scaffold` import has nothing to import from; the entire "emit OpenAPI 3.1 as canonical interop artifact" idea is inapplicable to this paradigm. |

---

## 3. The three deepest mismatches

1. **Responses are client-defined, not server-defined (fundamental).** refract's whole model —
   one `{status: {model}}` map authored once per operation, shared and reused — assumes the API
   author controls response shape. In GraphQL the *caller* controls it per call (op 1's nested
   `viewer{...repositories(first:10){nodes{name}}}` vs. a caller who asks only for `login` get
   different `data` shapes from the same field). A generator would need per-query-document codegen
   from schema introspection, not a spec-declared model registry.

2. **Errors live inside 200 responses, entangled with partial data.** GraphQL never uses HTTP
   status for API-level errors; `errors[]` sits next to `data` in the same 200 body (confirmed:
   `{"data":{"deleteIssue":null},"errors":[{"type":"NOT_FOUND","path":["deleteIssue"],...}]}`),
   and unrelated sibling fields in the same query can still return real data. refract's
   status-keyed error hierarchy (§9 of the spec) has no hook for this — it's a harder version of
   the Slack `ok:false` gap the spec already anticipated.

3. **The operation unit itself doesn't exist at the wire level.** There is no method+path per
   operation (always `POST /graphql`), and aliasing lets one HTTP call bundle arbitrarily many
   logically distinct queries (op 10) — the inverse of refract's "add op = +1 file = +1 wire call."
   Directory-per-resource, `operationId`, and the `_resource.yaml`/`<operation>.yaml` split are
   all derived from a URL-shaped API; there is no URL shape to derive them from here.

---

## 4. Sources (retrieved 2026-07-14)

- GitHub Docs, "Using pagination in the GraphQL API" — https://docs.github.com/en/graphql/guides/using-pagination-in-the-graphql-api
- GitHub Docs, "Mutations" — https://docs.github.com/en/graphql/reference/mutations
- GitHub Docs, "Rate limits and query limits for the GraphQL API" — https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api
- GitHub Docs, "Unions" — https://docs.github.com/en/graphql/reference/unions
- GitHub Docs, "Search" (SearchResultItem union) — https://docs.github.com/en/graphql/reference/search
- Error-shape example (`NOT_FOUND` with `type`/`path`/`locations`) cross-checked via `github/graphql-schema` community discussion and graphql-spec §7 (response format).
