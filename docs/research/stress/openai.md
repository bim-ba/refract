# refract stress test — OpenAI API (current, retrieved 2026-07-14)

Sources (all fetched 2026-07-14 via context7 `/websites/developers_openai_api_reference` + WebSearch/WebFetch
against `developers.openai.com/api/reference` and `developers.openai.com/api/docs`, OpenAI's current official
docs host — platform.openai.com/docs now redirects/mirrors here):

- Auth: https://developers.openai.com/api/reference (Authentication section) — headers `Authorization: Bearer`,
  `OpenAI-Organization`, `OpenAI-Project`
- Create chat completion: https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
- Streaming: https://developers.openai.com/api/docs/guides/streaming-responses ,
  https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events
- List files (pagination): https://developers.openai.com/api/reference/resources/files/methods/list
- Upload file (multipart): https://developers.openai.com/api/reference/resources/files/methods/create
- Create/retrieve batch: https://developers.openai.com/api/reference/resources/batches/methods/create ,
  .../batches/methods/retrieve
- Create fine-tuning job: https://developers.openai.com/api/reference/resources/fine_tuning/subresources/jobs/methods/create
- Create embedding: https://developers.openai.com/api/reference/resources/embeddings/methods/create
- Errors: https://developers.openai.com/api/docs/guides/error-codes , corroborated by
  https://github.com/openai/openai-python/issues/1968 (live 401 body)
- Responses API vs Chat Completions: https://developers.openai.com/api/docs/guides/migrate-to-responses

## 1. Operations picked (12)

| # | Operation | Method/path |
|---|---|---|
| 1 | Create chat completion (non-stream) | `POST /v1/chat/completions` |
| 2 | Create chat completion (`stream: true`) | `POST /v1/chat/completions` (same endpoint) |
| 3 | List models | `GET /v1/models` |
| 4 | Retrieve model | `GET /v1/models/{model}` |
| 5 | Create embedding | `POST /v1/embeddings` |
| 6 | Upload file | `POST /v1/files` (multipart) |
| 7 | List files | `GET /v1/files` (cursor pagination) |
| 8 | Create fine-tuning job | `POST /v1/fine_tuning/jobs` |
| 9 | Create batch | `POST /v1/batches` |
| 10 | Retrieve batch | `GET /v1/batches/{batch_id}` |
| 11 | Download batch output file content | `GET /v1/files/{file_id}/content` (raw bytes, not JSON) |
| 12 | Create response (Responses API, bonus) | `POST /v1/responses` — new recommended primary endpoint |

## 2. Axis-by-axis verdict summary

| Axis | Verdict | Representative ops | Why |
|---|---|---|---|
| Auth | **native** (near-miss noted) | all | `Authorization: Bearer` + optional `OpenAI-Organization`/`OpenAI-Project` maps to `HeaderToken`; but those two headers are *conditionally* sent (only if org/project configured) and `HeaderToken`'s spec shows no way to mark a header/secret optional-and-omit-if-unset |
| **Streaming (SSE)** | **GAP** | #2, #12 | see §3 — the headline finding |
| Pagination | **native** | #3 (None), #7/#9/#10-list (Cursor) | `after`/`has_more`/`first_id`/`last_id` = textbook `Cursor`; list models has zero pagination metadata = textbook `None` |
| Request body | **native** for JSON; **GAP** for multipart | #1/#5/#8/#9 native; #6 gap | `TypedModel` fits plain JSON bodies; OpenAI's file upload is true `multipart/form-data` (binary part + scalar fields, incl. bracket-notation nested `expires_after[seconds]`) — `Base64` in the registry implies base64-in-JSON, not raw multipart |
| Async/LRO | ops **native**, orchestration **GAP** | #9→#10→#11 | each Batch-API call individually fits (JSON POST, JSON GET); the poll-until-terminal *relationship* between them has no registry axis at all (unlike pagination/body) |
| Models/types | **GAP** | #1, #12 | `messages[].content` (string vs. discriminated content-part array) and `tool_calls[]` are tagged unions; refract's neutral type system has no `oneOf`/discriminated-union constructor |
| Errors | **native** | all | one flat `{error: {message, type, param, code}}` envelope reused everywhere — genuinely the easy case the spec is built for |
| Tests | **native** for flat models; **GAP** for unions/streaming | #1 (union parts), #2 (streaming) | `PropertyParse`/`RoundtripsBody` can't generate valid instances for a schema it can't express; streaming forces everything down to hand-written `Raw` |

## 3. Streaming — the headline finding

`stream: true` on `POST /v1/chat/completions` (same path, same method, same auth) switches the response
`Content-Type` from `application/json` to `text/event-stream`: a sequence of `data: {json chunk}\n\n` lines,
each chunk shaped `chat.completion.chunk` (a `delta` field instead of `message`), terminated by a literal
`data: [DONE]` line that is **not valid JSON**. The Responses API (`POST /v1/responses`, OpenAI's now-recommended
primary endpoint per the July-2026 migration guide) streams a *richer* union of ~20 named lifecycle events
(`response.created`, `response.output_text.delta`, `response.completed`, `error`, …) instead of one flat delta
shape.

This breaks refract at every layer that assumes "one status → one materialized model, fetched once":

1. **Response selection is keyed on a request-body field (`stream`), not on status code.** `responses:` (§9 of
   the spec) is `status → {model}`; there is no axis for "same 200, but the wire shape bifurcates on a request
   param." Nothing in `_resource.yaml`/operation-file schema lets one operation declare two response *modes*.
2. **The payload isn't one JSON value.** It's framed SSE text, unbounded until a sentinel, requiring incremental
   parse+accumulate (concat deltas into a message) that varies *per API* (chat completions accumulates a flat
   string; Responses API dispatches ~20 typed event kinds) — this is exactly the kind of per-API bespoke logic
   refract elsewhere pushes into strategy registries, but no `stream` strategy registry exists.
3. **Every downstream surface degrades.** MCP tool return = one structured JSON value (no streamed-partial-result
   concept modeled); CLI output goes through `output.Serializer.serialize` expecting a single object/list; OpenAPI
   3.1 has no clean way to say "if `stream=true` in the request, the response is `text/event-stream`" beyond
   prose — so a Tier-2 schemathesis run over the emitted spec would only ever exercise the non-streaming path.
4. **The escape hatch degrades too, not just routes around.** `handler: <module>:<fn>` is the sanctioned
   full-bypass, but taking it means losing derived response models, OpenAPI response schema, and every
   generated test except the hand-authored `Raw` strategy (exact recorded byte-fixture, no property generation).
   You don't get "streaming, but still refract-native" — you get "opt out of refract for this operation."

Given the spec's own framing (§0: streaming is "expected... report as gaps, not silently") this confirms the
prediction — but the severity is worth stating plainly: chat/agent streaming isn't a rare edge case for an API
like this, it's the dominant real-world call pattern (any chat UI streams by default), so an OpenAI refract spec
that only cleanly emits the non-streaming variant is missing the majority of the surface's actual usage.

**Recommendation, not "declare fully out of scope":** add a minimal `responses: {200: {model: X, stream: true}}`
flag purely as a *declaration* — enough for OpenAPI emission (mark `text/event-stream`, skip it in schemathesis)
and to tell the test generator "only `Raw`/`Custom` apply here, skip `ParsesModel`/`RoundtripsBody`/`PropertyParse`
for this op" — while still requiring `handler:` for the actual consume/accumulate logic. That's a bounded,
honest spec change, distinct from trying to fully model SSE accumulation semantics (which genuinely do vary
too much per API to generalize).

## 4. Multipart file upload — second finding

`POST /v1/files` is real `multipart/form-data`: a binary `file` part plus scalar form fields (`purpose`) plus
a *nested* bracket-notation field (`expires_after[anchor]`, `expires_after[seconds]`) — not JSON-with-a-base64-
field. refract's body registry names `Base64` as "(binary upload)" but §7's own probe line still lists
"multipart streaming" as an open gap even with `Base64` present — i.e., the spec authors already suspected
`Base64` means "one JSON field holds base64 bytes," which does not match this wire shape (different
content-type, different framing, several independently-named parts, one of them structured/nested). Verdict:
**at best `custom`, arguably GAP** — a literal `Multipart` body strategy (ordered list of named parts: scalar
fields + one-or-more binary fields) would be needed to call this native. The Batch API compounds this: the
*payload* a batch processes is itself a JSONL file where each line is a full typed request body for a
*different* operation (chat completions), tagged with `custom_id` — refract has no concept of "a bulk file
where each line validates against another operation's request schema" at all.

## 5. Polymorphic/union models — third finding

`messages[].content` is `string | array<content_part>` where `content_part` is a discriminated union
(`type: text|image_url|input_audio|file`, divergent sibling fields per variant); `tool_calls[]` is
`ChatCompletionMessageToolCallUnion` (currently one variant, `function`, but written as an extensible tagged
union); the Responses API's streaming events are an even larger discriminated union. refract's neutral type
system (§2: `string|integer|number|boolean|list<T>|map<K,V>|ref<Model>|any`) has **no `oneOf`/discriminated-union
constructor**. Options under the current spec are all lossy: erase to `any` (kills `TypedModel` validation,
`PropertyParse`/`PropertyRoundtrip` become vacuous since hypothesis can't generate meaningful instances from
`any`), or flatten to one model with every variant's fields `optional: true` (wrong — doesn't express
mutual exclusivity or the `type`-discriminator relationship, and hypothesis would generate invalid mixed-variant
instances). This is a deeper gap than a single strategy — it's a type-system gap that will recur for essentially
any chat/agent/tool-calling API, not an OpenAI quirk.

## 6. What fit cleanly (for balance)

- **Errors**: one flat `{error: {message, type, param, code}}` reused on every non-2xx — genuinely the
  textbook case, straight `responses: {4xx/5xx: {model: ErrorBody}}`, **native**, no union needed.
- **Retrieve model** (`GET /v1/models/{model}` → flat `{id, object, created, owned_by}`) and **list models**
  (flat `{object, data}`, zero pagination fields) are boring, clean **native** fits (`pagination: strategy: None`
  for the latter).
- Fine-tuning job's embedded `error: {code, message, param}` sub-field (populated on `status: failed`, but still
  HTTP 200) is a *soft* echo of Slack's 200-wrapped-error pattern the spec calls out — but it's just an ordinary
  nullable nested field on a normal resource, not a reinterpretation of the whole envelope. **native**, worth a
  passing mention only.

## 7. Async/Batch orchestration

Individually: create batch (`TypedModel`/JSON, **native**), retrieve batch (plain GET, **native**), download
result file (raw bytes response, not JSON — a minor "responses model isn't JSON at all" wrinkle, **custom** at
best). But the *relationship* — create → poll `status` until one of `completed|failed|expired|cancelled` →
then fetch `output_file_id`/`error_file_id` — has no registry axis in refract at all, unlike pagination and body
which are explicit first-class registries. §10 anticipates the write-side mirror of this ("upload =
create-session→PUT→finish→attach... → `Custom` handler + partial coverage") but an LRO/poll-until-terminal
convenience (terminal-status set, poll interval, "the real result lives in a field fetched via a different op")
isn't named anywhere. **GAP** at the orchestration layer specifically — not something `Custom` on any single
op's `body`/`pagination` can express, because there's no "Async" strategy registry slot to be `Custom` *of*.

## 8. Verdict

refract fits OpenAI well for the "boring 80%" — flat JSON CRUD-ish ops, uniform errors, standard cursor
pagination, retrieve/list/create with typed bodies. It breaks down exactly where the spec's own §0 predicted it
would (streaming) plus two more: real multipart (vs. its `Base64` binary strategy) and discriminated-union
request/response shapes (a type-system gap, not just a missing strategy). The Batch API's poll-until-terminal
shape is native at the per-call level but has no orchestration-level home.

**Top 3 gaps:**
1. **SSE streaming** (`stream: true` on chat completions / Responses API) — response shape keyed on a request
   field rather than status code; no `stream` response mode exists; full escape via `handler:` loses generated
   models/OpenAPI schema/property tests, not just routes around the issue.
2. **Multipart file upload** — `Base64` strategy implies base64-in-JSON, not true `multipart/form-data` with
   mixed binary+scalar(+nested) parts; needs a real `Multipart` strategy or is `custom` at best.
3. **Discriminated-union types** (`content` parts, `tool_calls`, Responses events) — the neutral type system has
   no `oneOf` constructor, so `PropertyParse`/`RoundtripsBody` are either vacuous or wrong for any op touching
   these shapes; this is a type-system-level gap that recurs across chat/agent/tool-calling APIs generally.

Full analysis: `/tmp/claude-1000/-home-sava-dev-dev-ycli/80802223-5853-4c72-8da8-868e6f65a5f8/scratchpad/sac-research/stress/openai.md`
