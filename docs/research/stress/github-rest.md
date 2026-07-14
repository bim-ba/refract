# refract stress test — GitHub REST API (v3 / current)

**Spec under test:** `15-refract-spec-frozen.md` (frozen baseline v1).
**Retrieval date for all docs.github.com citations below: 2026-07-14** (WebFetch against live
docs.github.com pages, API version examples shown as `2026-03-10` in the fetched auth page —
i.e. current, not memorized — plus one WebSearch for the canonical error-body example).

Sources:
- https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api
- https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api
- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api
- https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api
- https://docs.github.com/en/rest/issues/issues (list + create)
- https://docs.github.com/en/rest/repos/contents (get repository content)
- https://docs.github.com/en/rest/releases/assets (upload a release asset)
- https://docs.github.com/en/rest/search/search (search issues and pull requests)

---

## Verdict

**GAP.** GitHub's REST API breaks refract on the three axes the spec itself flagged as suspects
— Link-header pagination, ETag/If-None-Match conditional GETs, and `X-RateLimit-*` response
headers — for the *same underlying reason*: **refract's model system can only describe response
BODIES; it has no concept of a response HEADER as a value the emitted code can read, and no
concept of an arbitrary CALLER-supplied request header outside the fixed `auth` strategy.**
That single missing primitive (call it `HeaderSpec` / response-header capture) is the root cause
of all three GAPs, plus two more found below (content-negotiation-by-Accept-header, per-operation
`base_url` override for uploads.github.com). It is not three unrelated gaps — it's one missing
concept surfacing three times.

## Operations picked (11)

| # | Operation | Method + path |
|---|---|---|
| 1 | Get a repository | `GET /repos/{owner}/{repo}` |
| 2 | List repositories for a user | `GET /users/{username}/repos` |
| 3 | List repository issues | `GET /repos/{owner}/{repo}/issues` |
| 4 | Create an issue | `POST /repos/{owner}/{repo}/issues` |
| 5 | Update an issue | `PATCH /repos/{owner}/{repo}/issues/{issue_number}` |
| 6 | Search issues and PRs | `GET /search/issues` |
| 7 | Get repository content | `GET /repos/{owner}/{repo}/contents/{path}` |
| 8 | Upload a release asset | `POST https://uploads.github.com/repos/{owner}/{repo}/releases/{release_id}/assets` |
| 9 | Conditional GET (repo) | `GET /repos/{owner}/{repo}` + `If-None-Match` → 304 |
| 10 | Delete a label | `DELETE /repos/{owner}/{repo}/issues/{issue_number}/labels/{name}` |
| 11 | Get rate limit status | `GET /rate_limit` |

## Axis-by-axis classification

| Axis | Class | Why |
|---|---|---|
| Auth (`Authorization: Bearer <token>`) | **native** | `Bearer` strategy is a direct match. GitHub docs: *"In most cases, you can use `Authorization: Bearer` or `Authorization: token`."* |
| `X-GitHub-Api-Version` static header | **custom (near-miss)** | Not a secret — a hardcoded literal every request must carry. `HeaderToken`'s `headers:` map can hold a literal string with no `{placeholder}`, so it's technically expressible bolted onto the auth strategy — but API *versioning* living inside the *auth* registry is a category error; there's no home for "static per-resource headers" outside auth. |
| Pagination (list issues/repos, bare-array body) | **GAP** | GitHub's `Link` response header (RFC 5988) is authoritative: `Link: <url>; rel="next", <url>; rel="last"`. None of `Offset\|Cursor\|RelativeCursor\|NextUrl` read headers — spec text confirms all four read the BODY. Worse: list-issues/list-repos return a **bare JSON array** as the whole body (no envelope), so `items_field` has no field to point at. Needs a new `LinkHeader` strategy that parses the `Link` header, is a no-op on `items_field` (items = response root), and a transport-level header-parser the current pagination contract doesn't have. |
| Pagination (search issues) | **GAP (partial near-miss)** | `/search/issues` DOES return an envelope (`total_count`, `incomplete_results`, `items`) — `items_field: items` is native for item extraction — but page *advancement* is still exclusively via the `Link` header, so the strategy is still unusable end-to-end without `LinkHeader`. Also: 30 req/min secondary rate limit specific to search is invisible to any strategy (see rate-limit row). |
| Request body (create/update issue) | **native** | `TypedModel` fits `POST`/`PATCH` issue bodies directly; `PATCH`'s all-optional-fields partial-update shape maps cleanly onto `optional: true` fields. |
| Request body (upload release asset) | **GAP** | Body is **raw binary octet-stream** (`Content-Type: application/zip` etc.), not JSON — the strategy named `Base64` implies base64-encoded-JSON-wrapped bytes (matches Wiki-attachment-style flows), not a literal raw-bytes POST. Metadata (`name`, `label`) travel as **query params**, not body fields — fine, `params:` handles that. The fatal part: this operation must hit **`uploads.github.com`**, not the resource's `base_url` (`api.github.com`) — `base_url` lives once in `_resource.yaml`, no per-operation override exists. A single mixed-host operation inside an otherwise-single-host resource has no expressible home short of `Custom(handler:)`, which the spec permits but doesn't advertise as the fix for "one operation, different host." |
| Responses & errors | **native** | Canonical shape is uniform: `{"message": "...", "documentation_url": "https://docs.github.com/rest"}`, with a `422` variant adding `errors: [{resource, field, code}]` (WebSearch, GitHub troubleshooting docs). Maps cleanly onto per-status `responses: {4xx: {model: ErrorBody}}`, with a richer `ValidationErrorBody` model for 422. |
| Conditional requests (ETag/If-None-Match → 304) | **GAP** | Two missing halves: (1) capturing the **response** `etag`/`last-modified` header from a prior call — no model field can ever hold a header value, only body JSON; (2) `304 Not Modified` has **no body at all**, and `responses:` requires `{model: ...}` per status — there's no documented "no-body / null-model" status entry. Even if `If-None-Match` can be sent as an `in: header` request param (ambiguous — spec only shows `in: query` examples), the caller can never *obtain* the ETag to send back without a `Custom` handler that drops to raw `httpx`/`requests` response objects, defeating the generator entirely. |
| Rate-limit headers (`X-RateLimit-*`) | **GAP** | Same root cause as conditional requests: response headers are invisible outside the body-model system. `GET /rate_limit` itself is a trivial **native** operation (its *body* has the counts) — but that endpoint doesn't help agents/CLI users see remaining quota on the request they actually just made, which is the real use case, and per-request header surfacing has zero mechanism. |
| Operation/path shape (owner/repo templating) | **native** | `path: repos/{owner}/{repo}/issues` templating is exactly what section 5 supports. |
| Content negotiation (get content: JSON-base64 vs raw vs HTML via `Accept`) | **GAP** | Same status code (200), three different wire *shapes* depending on `Accept: application/vnd.github.raw+json` / `.html+json` / default `+json` — `responses:` keys purely on status code, with no axis for "same status, different representation selected by a request header." Effectively three different operations sharing one URL; refract has no representation/variant concept, would need three synthetic `Custom` ops or one `Custom` handler that branches internally. |
| Models/types (nullable unions) | **custom / near-miss** | Several GitHub fields are true unions, not simple-nullable: `title: string \| integer`, `milestone: null \| string \| integer`. refract's type system is `string\|integer\|number\|boolean\|list<T>\|map<K,V>\|ref<Model>\|any` + `optional: true` — no multi-type union primitive. Workaround: widen to `any` (loses type safety) or pick the dominant type and drop the rest — either way it's a lossy fit, not a clean native match. |
| Delete-with-body vs delete-bodyless | **native (both, situationally)** | GitHub is inconsistent by design: `DELETE .../labels/{name}` returns **200 + the remaining label array** (use `responses: 200: {model: LabelList}`, no `ack:`), while other deletes (e.g. delete a comment) return **204 No Content** (use the `ack:` factory pattern as designed). Both fit refract's existing constructs — just illustrates GitHub doesn't have one canonical delete shape, which the spec already tolerates. |
| Tests | **native, downstream-blocked** | `ParsesModel`/`ReturnsError`/`RoundtripsBody` are fine for issue CRUD. `DrainsPages` cannot be generated for any GitHub list endpoint until `LinkHeader` pagination exists (it's gated by the pagination GAP, not an independent test-layer problem — once `LinkHeader` exists, Python's `responses` library *can* stub headers, so it's solvable). No test strategy exists (or could exist without the header-capture primitive) for ETag/304 round-trips or rate-limit-header assertions — again gated by the same root gap. |

## Top-line gap count

- **Confirmed GAPs (new spec concept needed): 5** — `LinkHeader` pagination strategy; response-header
  capture (blocks conditional requests AND rate-limit surfacing — one fix, two payoffs);
  per-operation `base_url` override; response representation/variant-by-`Accept`-header; bare-array
  (non-enveloped) list response bodies.
- **Near-misses (technically expressible, but ill-fitting or mis-named):** `X-GitHub-Api-Version`
  static header wedged into the auth registry; `Base64` body strategy name/semantics mismatch for
  literal raw-byte uploads; no union types for GitHub's `string|integer`/nullable-union fields.
- **Clean natives:** Bearer auth, TypedModel bodies for create/update, uniform error envelope,
  `{param}` path templating, `ack:` vs typed-body deletes.

## Top 3 gaps (for the ≤300-word summary)

1. **Link-header pagination (RFC 5988) is unsupported** — all 4 built-in strategies read the body;
   GitHub's `next`/`last` pointers live only in the `Link` response header, and list bodies are
   often bare arrays with no `items_field` to point at. Needs a new `LinkHeader` strategy plus a
   header-reading capability in the transport that today's pagination contract lacks.
2. **No response-header capture mechanism anywhere in the spec** — this single gap independently
   blocks both ETag/If-None-Match conditional GETs (304 has no body, and the ETag to send back can
   never be obtained from a prior response) and `X-RateLimit-*` surfacing (per-request quota is
   invisible even though `GET /rate_limit` itself is trivially native).
3. **No per-operation `base_url` override** — `POST .../releases/{id}/assets` must hit
   `uploads.github.com` while every sibling operation on the same resource hits `api.github.com`;
   `base_url` is fixed once per `_resource.yaml`, so a single cross-host operation has no clean
   home short of a full `Custom` handler.

File: `/tmp/claude-1000/-home-sava-dev-dev-ycli/80802223-5853-4c72-8da8-868e6f65a5f8/scratchpad/sac-research/stress/github-rest.md`
