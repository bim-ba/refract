# refract stress test — Elasticsearch REST API (current)

Spec under test: `15-refract-spec-frozen.md` (frozen baseline). Retrieved 2026-07-14 via WebSearch
against elastic.co/docs (primary) plus GitHub issues/community sources for edge-case confirmation.
Version scope: current Elasticsearch (8.x/9.x REST surface; `elastic.co/docs/api/doc/elasticsearch`,
no version pinned = latest docs tree as served 2026-07-14).

## Operations picked (12)

1. Index a document — `PUT /{index}/_doc/{id}` (or `POST /{index}/_doc`)
2. Get a document — `GET /{index}/_doc/{id}`
3. Delete a document — `DELETE /{index}/_doc/{id}`
4. Search — `POST /{index}/_search` (Query DSL body)
5. Bulk — `POST /_bulk` (NDJSON body)
6. Scroll: open — `POST /{index}/_search?scroll=1m`
7. Scroll: continue — `POST /_search/scroll`
8. Scroll: clear — `DELETE /_search/scroll`
9. PIT + search_after — `POST /_pit` (open) → `POST /{index}/_search` (body carries `pit`+`search_after`) → `DELETE /_pit` (close)
10. Delete by query — `POST /{index}/_delete_by_query`
11. Update by query — `POST /{index}/_update_by_query`
12. Update mapping — `PUT /{index}/_mapping`

Sources: [Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk),
[Open point in time](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-open-point-in-time),
[Paginate search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results),
[Clear a scrolling search](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-clear-scroll),
[Authentication](https://www.elastic.co/docs/api/doc/elasticsearch/authentication),
[Create/Index document](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index),
[Update field mappings](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-put-mapping),
[Delete by query](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete-by-query),
[Update by query](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update-by-query),
[Nested query / Query DSL](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-nested-query),
[Common options / error format](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/common-options).

## Per-axis classification

| Axis | Verdict | Notes |
|---|---|---|
| **auth** | **native** | `Basic` (`Authorization: Basic <b64 user:pass>`), `ApiKey` (`Authorization: ApiKey <b64 id:key>`, `in: header`), `Bearer` (service-account/JWT tokens) all map 1:1 onto refract's registry. No gap. |
| **request body — TypedModel ops** (index-doc, mapping PUT) | **custom → near-GAP** | The document/mapping body shape is caller-defined per index (ES mappings are dynamic unless declared), so `TypedModel` only works if the spec author hand-declares a model per index/use-case — fine for one index, but a generic "ES client" can't ship one canonical `Document` model. Workable but pushes real modeling burden onto every spec author, every index. |
| **request body — Search (Query DSL)** | **GAP (near-miss)** | Query DSL is a large, deeply recursive, open-ended grammar (bool/must/should/nested/range/terms/function_score/script_score/span_*/percolate/aggs…, unbounded nesting). Hand-maintaining a `TypedModel` pydantic schema covering it is intractable — real ES clients (elasticsearch-py, elasticsearch-js) model it as loosely-typed `TypedDict`/`dict` unions precisely because a closed schema doesn't exist. In practice this body is `RawDict`/`any`, not `TypedModel` — confirms the probe. Downstream cost: `PropertyParse`/`PropertyRoundtrip` (hypothesis-generate-from-schema) have nothing to generate from → vacuous, must be `skip`ped per spec §8's own escape hatch. |
| **request body — Bulk (NDJSON)** | **GAP** | `POST /_bulk` body is newline-delimited, alternating action-metadata-line + optional-source-line, `Content-Type: application/x-ndjson` (or `application/json`, but never *one* JSON value), compact-only (no pretty-print), must end in `\n`. refract's four body strategies (`TypedModel`/`Assembled`/`RawDict`/`Base64`) all assume exactly one structured value serialized as a single JSON payload. None expresses "N heterogeneous JSON objects glued by `\n`, non-JSON media type, order-significant line-pairs." `Custom(handler:)` *can* build the string manually — so it's expressible — but only by opting the whole operation out of typed generation: no `TypedModel`, no `RoundtripsBody`, no `PropertyRoundtrip`. **This is exactly the "new body strategy" case** — a `strategy: NDJSONLines` (list of `{action_model, source_model}` pairs, custom content-type, custom serializer) would recover the lost test/model value; without it, bulk becomes 100% hand-written. |
| **pagination — search_after + PIT** | **GAP** | Superficially close to `RelativeCursor` (cursor = last hit's sort values), but PIT is a **3-operation stateful session**: `POST /_pit` (open, returns `pit_id`, own `keep_alive` TTL) → repeated `POST /{index}/_search` where `pit` id (which **changes every response** — "always use the most recently received id") and `search_after` both live *inside the query-DSL body*, not as top-level cursor fields → `DELETE /_pit` (explicit close, or it leaks server-side resources until TTL). refract's `pagination:` block is scoped to ONE operation's mechanics (`items_field`, page size); it has no vocabulary for "open a resource in operation A, thread its rotating id through operation B in a loop, close it in operation C." |
| **pagination — scroll** | **GAP** (spec pre-flagged, confirmed real) | Same 3-operation shape as PIT but worse: the *continuation* call hits a **different path** (`POST /_search/scroll`, not `GET {path}?cursor=...`), and cleanup is a **different HTTP method** (`DELETE /_search/scroll`) that must be called explicitly or the scroll context lives until `scroll` TTL. None of `Cursor`/`RelativeCursor`/`NextUrl` model "continuation goes to another endpoint entirely." Real precedent inside ycli itself: Tracker's own scroll pagination needed a dedicated `tracker_issues_scroll_clear` op outside the pagination block — i.e. ycli already hand-solved this exact shape with a bespoke extra operation, not through `pagination:` config, which is independent field evidence for the gap. |
| **responses & errors — standard ops** | **native** | Non-2xx bodies are a uniform `{error:{root_cause:[...], type, reason}, status}` envelope across essentially the whole non-bulk surface — cleanly matches `responses: {200:{model:X}, 404:{model:ErrorBody}}`. Genuinely one of the *better*-behaved APIs on this axis; worth noting refract isn't gap-ridden everywhere. |
| **responses & errors — Bulk partial success** | **GAP** | Whole-request HTTP status is 200 even when individual items fail; failure signal is `errors:true` + per-item `items[].{status,error}` **inside** the 200 body — an array of independently succeeding/failing sub-operations in one envelope. This breaks `ReturnsError`'s premise (one test per 4xx/5xx→typed error): there is no non-2xx to hang item-level failure on. Structurally a harder case than the Slack `ok:false`-in-200 pattern §9 already flags (Slack: one flag; Bulk: N independent per-item results, some ok some not, in the same array) — same family, different (worse) shape. `TypedModel` can describe the response shape, but the auto error-hierarchy/test machinery has nothing to attach partial-failure assertions to; needs bespoke `tests: add:` authoring per bulk-using op, every time. |
| **operation/path shape** | **native** | Every op here (`_doc/{id}`, `_bulk`, `_search/scroll`, `_pit`, `_mapping`, `_delete_by_query`, `_update_by_query`) is a clean resource path with `{param}` templating — refract's explicit `path:` field handles all of it without strain. |
| **models/types** | **near-GAP** (real but not fatal) | A meaningful fraction of the chosen ops (Query DSL search body, indexed documents under dynamic mapping, mapping-PUT body) collapse to `any`/`RawDict` because ES mappings are dynamic by default. Not a hard gap (the neutral type system has `any`) but a large erosion of the "typed SDK" value prop for a central slice of a real ES client — and it silently degrades §8's rich auto-suite for those ops. |
| **tests** | **GAP for bulk, near-miss for DSL** | Bulk: `RoundtripsBody`/`PropertyRoundtrip` assume one-JSON-in-one-JSON-out; NDJSON breaks that mechanically, not just because of scale. Query DSL / dynamic docs: `PropertyParse`/`PropertyRoundtrip` need a model schema to generate `hypothesis` instances from — `RawDict`/`any` bodies give hypothesis nothing to generate, so those tests are either skipped (per spec's own `skip:` escape hatch) or vacuous no-ops if left enabled. `Raw` (uniform request+response+assert escape hatch) is really the only test strategy that survives contact with bulk and Query DSL intact. |
| **async / streaming** | **native, with a minor custom note** | ES REST is synchronous request/response throughout (no SSE/WS) — matches the frozen scope cleanly. Minor wrinkle: `delete_by_query`/`update_by_query` support `wait_for_completion=false`, returning a task id to poll via a separate `_tasks/{id}` resource — a fire-and-poll pattern outside pagination/body scope, but expressible as a plain extra `Custom`-free follow-up GET operation, not a hard gap. |

## Prime-suspect deep dives (as directed)

- **NDJSON bulk = GAP, needs a new body strategy.** Confirmed: `application/x-ndjson`, alternating
  action/source lines, no pretty-printing, trailing `\n` required — none of `TypedModel` /
  `Assembled` / `RawDict` / `Base64` fit a multi-line, mixed-media-type, order-significant payload.
  `Custom(handler:)` covers it functionally but forfeits typed models and body-shaped tests. Verdict:
  add a `NDJSONLines` strategy (or generalize `Custom` with declared media-type + line-schema hooks).
- **Query DSL = effectively `RawDict`/`any`, not `TypedModel`.** The grammar is too large and too
  recursive to maintain as a closed pydantic schema — matches how real ES SDKs model it. Not a hard
  GAP (spec has `any`) but a significant, silent tax on §8's "rich auto-suite" promise for the single
  most-used operation (search) in the whole API.
- **Stateful scroll/PIT pagination = GAP.** Confirmed worse than a near-miss: continuation and cleanup
  are *separate operations* (different path for scroll, different HTTP method for both), with a
  rotating/expiring session id threaded across all of them. `pagination:` strategies are single-operation
  mechanics; this needs either a new "session" pagination concept spanning 3 ops, or full `Custom`
  opt-out for all three legs — which is what ycli itself already did for Tracker's own scroll API
  (dedicated `tracker_issues_scroll_clear` op), independently corroborating the gap.
- **Bulk partial-success responses = GAP.** 200-status envelope with per-item embedded errors defeats
  `ReturnsError`'s "non-2xx → typed error" assumption; a structurally harder cousin of the
  Slack-`ok:false` case §9 already anticipates.

## Verdict

Elasticsearch is a strong stress case precisely because refract's "assumed scope" (sync HTTP,
JSON-first, one-body-per-request) mostly holds for **half** the surface (doc CRUD, delete/update-by-query,
mapping admin — all native/near-native) while the other half (bulk, search, scroll, PIT) breaks each of
the three axes the task named as prime suspects. None of the four found here are silent — the spec's own
§6/§7/§9 pre-flagged scroll, NDJSON, and 200-wrapped-errors as exactly the probes to run, and all three
came back positive, plus the Query DSL modeling tax as a bonus near-miss the spec didn't explicitly name.

Full detail: `/tmp/claude-1000/-home-sava-dev-dev-ycli/80802223-5853-4c72-8da8-868e6f65a5f8/scratchpad/sac-research/stress/elasticsearch.md`
