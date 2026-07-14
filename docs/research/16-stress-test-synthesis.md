# refract spec stress-test — consolidated gaps → revisions (14 APIs)

14 agents projected the frozen spec v1 (`15`) onto real APIs (Yandex 360 ×2, Yandex Cloud, GitHub REST,
GitHub GraphQL, Stripe, AWS S3, OpenAI, Kubernetes, Slack, Twilio, Google Calendar, Elasticsearch, Notion).
Per-API reports in `stress/*.md`. This aggregates the gaps and the spec revisions they imply.

## 0. Headline
**The architecture HOLDS.** Nearly every gap is either "add a member to an existing strategy registry,"
"add ONE of two new registries," or "extend the neutral type system" — NOT a redesign. The
strategy-registry principle is *validated* by being the natural home for the findings. Two things are
genuinely new: (1) a set of **scope boundaries** to declare as v1 non-goals; (2) two new registries
(**Async/LRO**, **Error-model**) + **union types** + **cross-file model refs**. Everything else is
registry members added as real consumers need them — exactly the intended growth model.

## A. Scope boundaries — DECLARE as explicit v1 non-goals (client-gen of synchronous REST/HTTP)
| Boundary | Evidence | Why out (for v1) |
|---|---|---|
| **GraphQL** | GitHub GraphQL | Different paradigm: client-defined responses, no wire op unit (`POST /graphql`), errors-in-200. A separate "mode," not a strategy. |
| **Streaming responses** (SSE, watch, log-follow) | OpenAI, k8s | Response shape flips on a request field, not status; model-per-response + tests don't fit. `handler:`-only or v2 streaming mode. |
| **Inbound receivers** (webhook/push delivery) | Google `watch`, Slack Events | Generating a SERVER to receive is categorically outside client-gen scope. |
| **Interactive auth bootstrap** (OAuth2 consent, mTLS cert provisioning) | Google, k8s | The generator wires a token/cert PROVIDER; it cannot do interactive consent. |
Ratifying these bounds the design and stops force-fitting. (Slack's RPC all-POST `domain.method` shape, by
contrast, maps CLEANLY — no boundary needed.)

## B. Strategy registries — extend existing + add two new
### B1. Body-encoding (v1 assumed JSON only — the single most common miss)
Add an `encoding` to `body:`: `Json`(default) · **`FormEncoded`** (flat + nested-bracket + repeated-key
lists — Stripe 250+ ops, Twilio, Slack) · **`Multipart`** (OpenAI, Stripe, AWS, Google-batch) ·
**`Ndjson`** (ES bulk, k8s watch) · **`Xml`** (AWS) · **`RawBytes`** (AWS PutObject — ≠ Base64) ·
**`FieldMask`** (YC updateMask) · **content-type-keyed body list** (k8s 3 patch types on one path+method) ·
serialization knob `exclude_unset` vs `exclude_none` (Google implicit-PATCH over-sends nulls otherwise).
### B2. Auth — beyond static-secret-in-header
Add: **token *provider*** (exchange/refresh: OAuth2-refresh, YC IAM-JWT-exchange, Google service-account) ·
**`Signer`** (SigV4 — signs over the whole request incl. body; chunked = body-transcoding) · **mTLS/
client-cert** (transport-level: cert/key/CA/verify — no current strategy reaches session construction) ·
**secret-into-path/query** (Twilio `{AccountSid}`, api360 `organization_id` in path). Static mandatory
header (`Notion-Version`, `X-Org-Id`) already fits `HeaderToken` — VALIDATED. Interactive bootstrap → §A.
### B3. Pagination — beyond body-cursor
Add: **`LinkHeader`** (RFC 5988 — GitHub) · **`HeaderCursor`** (Tracker `X-Scroll-Id`) · **`Scroll`/session**
(stateful open→loop→close, cross-op/cross-path — ES scroll/PIT, Tracker scroll, ycli's own `scroll_clear`) ·
**cursor-in-body** (Slack nested dotted `response_metadata.next_cursor`; Direct/Notion cursor in POST body →
breaks "pure mechanics, no model ref") · **page+relative-next-uri** (Twilio, host-relative ≠ NextUrl absolute) ·
**bare-array response** (GitHub, no `items_field`) · **response-type-conditional** (Notion) · **`DeltaSync`**
(Google `syncToken` — persisted cross-session). Support dotted field paths.
### B4. Async / Long-Running Operations — NEW REGISTRY (biggest structural add)
`strategy: Operation`: submit → poll a (often different-host, different-path) status resource until terminal
→ unwrap `response`/`error`. **Overwhelmingly confirmed:** YC (≈100% of writes), OpenAI Batch, Disk, Direct
Reports, Wiki clone, ycli `bulk_*`. Config: poll-target (path/host), terminal predicate, result/error unwrap.
NOT a per-op `Custom` — it is the mutating-call pattern for whole platforms.
### B5. Error-model — NEW REGISTRY (v1 assumed status→typed-error only)
`Status`(default) · **`BodyFlag`** (200-wrapped: discriminate success/error on a body field — Slack `ok`,
AWS `<Error>`, ES `errors`, YC, Direct) · **partial-success** (per-item `items[].{status,error}` — ES/Slack/
Direct/Google-batch) · **non-status discriminator** (gRPC numeric `code` — YC). CRITICAL: the test registry
must READ the op's error strategy (see §E).

## C. Type-system extensions (JSON-Schema-aligned)
- **Discriminated unions / tagged `oneOf`** — THE most universal gap (Notion ~32 block variants, OpenAI
  `messages[].content`/`tool_calls`, Stripe expandable, GitHub `string|integer`, YC oneof, Slack Block Kit,
  Yandex questions 12-union, Direct AddResults). Add `oneOf` + `discriminator` AND undiscriminated unions.
  **Non-negotiable** — nearly every API has it; without it `PropertyParse`/`RoundtripsBody` go vacuous/wrong.
- **Cross-resource model sharing / `$ref` import** — k8s `ObjectMeta`/`TypeMeta` embedded in every object;
  models are scoped in one `_resource.yaml` today. Add a shared-models file + cross-file `ref<...>` (like
  `_auth.yaml` is a shared root). Hits EVERY op, not an edge.
- **Scalars/formats**: int64-as-string (protobuf-JSON — YC), raw-bytes, RFC 2822 vs RFC 3339 dates (Twilio).
- **Model-level validators + model-level escape hatch** — `handler:` is op-level only; cross-field rules
  (`QuestionMove`, Event start/end) have no home → a literal generator reproduces the silent-no-op bug, and
  `PropertyParse` emits invalid fixtures. Extend `handler:` to models.

## D. Cross-cutting mechanisms
- **Response-header capture** (recurring: pagination cursors, ETag, rate-limit, scroll-id, multipart ETag) —
  GitHub/Tracker/AWS/Google. A first-class "capture header → usable value" mechanism. Unblocks D-items below.
- **Per-operation base_url / host override + host templating** — GitHub uploads host, YC operation host, AWS
  bucket-in-host, Twilio. `base_url` is fixed per resource today.
- **Conditional requests / optimistic concurrency** (ETag/If-Match/304 — GitHub/Google; ycli grids `revision`).
- **Per-call generated values** (Stripe `Idempotency-Key` = fresh UUID/call, ≠ static `env:` secret).
- **Content negotiation** (Accept → different body at same status — GitHub get-content).
- **JSON-RPC single-endpoint dispatch** (Yandex Direct: N logical ops on one `POST /json/v5/<svc>/`) — breaks
  1-op-per-(path,method) + valid-OpenAPI. Needs a `dispatch` concept (logical ops → one endpoint + body
  discriminator) OR a documented scope note.
- **Multi-op orchestration** (multipart Create→Part→Complete, upload pipeline, Notion version-migration
  discovery, Google batch) — mostly absorbed by the Async/LRO registry + `handler:`; note the recurring shape.
- **API-versioning axis** (Notion breaking `Notion-Version` migrations) — lower priority; a way to pin/flag.

## E. Test-registry implications (must adapt to declared strategies)
- Test strategies MUST be selected/configured from the op's DECLARED strategies (error-model, pagination,
  body) — not fixed defaults. Else `ReturnsError` stubs a 4xx an API never sends (Slack — actively WRONG, not
  just incomplete), `DrainsPages` fails on relative-next-uri (Twilio), `RoundtripsBody` misleads on partial
  PATCH (Google). The test registry is COUPLED to the other registries.
- `PropertyParse`/`PropertyRoundtrip` need union-aware + cross-field-validator-aware generation (YC/Notion/
  Google) else invalid/vacuous fixtures.
- Free-form bodies (ES Query DSL, TQL) → `RawDict`/`any` → auto-tests degrade — a documented, accepted tax.

## F. v1 subset (ycli + public MVP) vs roadmap (refract as a general tool)
The stress test doubles as a **prioritized backlog**. What ycli (first consumer) actually needs for v1:
- auth: `HeaderToken` (OAuth + X-Org-Id). pagination: `None/Offset/Cursor/RelativeCursor` (+ leave Tracker
  header-scroll un-auto-paginated, as ycli does today). body: `TypedModel/Assembled/RawDict/Base64`.
  error-model: `Status` + `BodyFlag` (bulk partial-success). **Async/LRO** (clone/bulk). type system:
  **unions** (status discriminated) + **cross-file refs** + **model-level handler** (QuestionMove). `Custom`
  on every axis. → This is the v1 build scope.
- **Roadmap (add registry members as real consumers arrive):** FormEncoded/Multipart/Ndjson/Xml/FieldMask ·
  Signer/mTLS/OAuth2-refresh/secret-into-path · LinkHeader/Scroll/HeaderCursor/DeltaSync · response-header
  capture · per-op host · conditional requests · content negotiation · JSON-RPC dispatch · streaming mode ·
  API-versioning. Each is additive — the registry grows, the core doesn't change. This is the public tool's
  differentiation roadmap AND proof the architecture scales.

## G. What this VALIDATES about the design
1. Strategy-registry principle is the right abstraction — every gap slotted into "a registry member."
2. Committed-source + typed-IR + neutral types hold; unions are the one type-system must-add.
3. The `Custom(handler:)` escape hatch is necessary but must NOT be the home for whole-platform patterns
   (LRO, error-by-body) — those earn first-class registries. Escape-hatch overuse = the anti-signal.
4. Scope boundaries make refract honest: a great REST/HTTP generator, explicitly not GraphQL/streaming/
   server-gen. Better to bound than to force-fit.
