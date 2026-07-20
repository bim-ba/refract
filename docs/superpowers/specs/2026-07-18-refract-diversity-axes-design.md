---
milestone:
  name: diversity-axes-and-debt-zero
  status: design-approved
  branch: feat/axis-registries
  supersedes_none: true
  builds_on: 2026-07-14-refract-architecture-redesign-design.md
goal: >-
  Close all genuine open emitter debt AND grow refract's diversity axes (body-encoding,
  pagination, error-model, auth, type-system unions, cross-file refs, async/LRO,
  cross-cutting) so refract is a general public API-client generator, not a ycli-only tool.
anchoring:
  principle: >-
    Every axis member is proven on a real endpoint from a diverse panel of technically-
    different public APIs BEFORE it is considered done (rule-of-three, incremental validation).
  panel_source: artifacts/stress/*.md + artifacts/16-stress-test-synthesis.md (14 APIs)
  design_input: artifacts/17-milestone-design-input.md (per-member evidence, file:line cited)
  local_docs: references/ (regenerate via scripts/fetch_docs.py; corpus gitignored)
locked_decisions:
  Q1_cli_write: assembled-cli default + handler escape hatch
  Q2_204_return: bare None now; Ack value object only on first echoed-identifier consumer
  Q3_unions: discriminated + undiscriminated now; recursion deferred to Forms/Notion consumer
  Q4_async_lro: in this milestone, sequenced LAST (P7); the clean cut line if scope must shrink
  Q5_per_op_host: named hosts in client.yaml; op references host by name
  Q6_jsonrpc: document as a scope note, do not build (single consumer = Yandex Direct)
  Q7_sigv4_body: keep auth and body registries orthogonal; SigV4 is a documented exception
  Q8_xml: defer (heaviest single L-item, no ycli-adjacent consumer)
---

# refract milestone: diversity axes + debt-zero (diverse-API-anchored)

> Design spec. The exhaustive per-member evidence (anchor endpoints, `file:line` for every
> current-code claim, the pre-redesign -> current-architecture vocabulary re-map) lives in
> `artifacts/17-milestone-design-input.md`. This document locks the decisions and the build
> order that `writing-plans` will turn into tasks. English; ASCII; one logical line per line.

## 1. Goal and framing

The architecture redesign (form D: neutral IR waist, `client.yaml`, `AuthScheme` union,
`httpx.Auth`, surface emitters, generated glue) merged to `main`. refract now generates a real
2-resource slice (me + priorities). This milestone makes refract *general*: it closes the
remaining emitter debt and grows every diversity axis a diverse panel of real APIs exercises.

The load-bearing constraint, ratified with the owner: refract is a PUBLIC tool, so its
abstractions must not be shaped by one API. Each axis member is anchored on a specific real
endpoint from the 14-API panel (GitHub REST + GraphQL, Stripe, AWS S3, OpenAI, Kubernetes,
Slack, Twilio, Google Calendar, Elasticsearch, Notion, Yandex 360 x2, Yandex Cloud). An axis
with NO real panel consumer is a declared non-goal, not a speculative build: a speculative
abstraction without a consumer costs more than the duplication it "saves".

## 2. Scope

In scope: the debt-zero items (section 4) and the axis members listed per phase (section 6),
each with a named anchor endpoint. Out of scope: section 7 non-goals.

The milestone is large (phases P0-P8, several L-items). Async/LRO (P7) is the single clean cut
line if scope must shrink. XML, JSON-RPC dispatch, and content negotiation are deferred now
(no committed consumer) and pulled in only when one materializes.

## 3. Locked decisions (owner-approved)

| # | Fork | Decision |
|---|---|---|
| Q1 | cli-write | Assembled-CLI default (walk the body model, one typer option per leaf, reassemble); `handler:` escape hatch for polymorphic / `map`-bodied ops. Gate the first cut to scalar + one-level `ref<Model>`; expand on the third real consumer. |
| Q2 | 204 return-shape | Return bare `None` for a bodyless op now. Add a first-class `Ack`/`Deleted` value object only when a resource needs the echoed identifier. |
| Q3 | union depth | Ship discriminated (tagged `oneOf`) + undiscriminated (`A \| B`) unions now. Defer recursive self-referential unions until Forms/Notion is the committed consumer. |
| Q4 | async/LRO | In this milestone, sequenced LAST (P7). Most-confirmed pattern (YC ~100% of writes) so not deferred, but it depends on P2+P3+D2 and is the clean scope-cut line. |
| Q5 | per-op host | Named hosts declared in `client.yaml`; an op references a host by name. Keeps the op file transport-config-free and supports templated hosts later. |
| Q6 | JSON-RPC dispatch | Document as a scope note; do not build. Only Yandex Direct needs it and it breaks the 1-op-per-(path,method) + valid-OpenAPI invariant. Revisit on a second consumer. |
| Q7 | SigV4 body-hash | Keep the auth and body registries orthogonal. SigV4 is the one panel case where auth reads body output; let its mechanism buffer the body (`requires_request_body=True`), documented as an exception rather than a general dependency mechanism. |
| Q8 | XML codec | Defer. A full second wire codec on request AND response, the heaviest single L-item, with no ycli-adjacent consumer. |

## 4. Debt-zero (P0)

Verified against current source; `roadmap.md` is stale (A2-2/A2-3/A2-5 are already fixed by the
redesign). Genuine OPEN debt:

| # | Item | Fix | Cx |
|---|---|---|---|
| D1 | tests emitter is single-op (`resolve/` binds one op via `next(... if op.tests)`) | Loop over every tests-bearing op; per-op imports/constants/blocks. Pure generalization. | M |
| D2 | 204 / no-response-model ops fail loud (`resolve/`) | Make `ResponseSpec.model` optional + allow status-only entries; requests/client/mcp emit `-> None` and skip the response `.models` import; `Session.send` returns `None` on empty body. | M-L |
| D3 | vacuous no-facet surface-gate coverage (every `applies()` False arm untested) | Add a fixture resource with no mcp / no cli / no tests / no models; assert those files are absent from the plan. | S |
| D4 | loader hardcodes `responses[200]` (`loader.py:133-137`) | First-2xx selection (`min` of 2xx statuses), `SpecError` if none. Implement WITH D2 (they are the same change: `ResponseSpec.model` becomes optional). | S |
| D5 | cli-write commands: `_cli_command` emits a param-less passthrough (`resolve/`); a write op's CLI leaf would call a `body:`-taking method with zero args | Assembled-CLI per Q1: walk the body model's fields, emit one typer option per leaf, reassemble the model, forward it. | L |

D2 and D4 are one change (a 204/201-only op has no `{200: {model}}` to read, and the spec node
cannot express a status entry without a model). D1 gates the entire tests-emitter coupling (2.8).

## 5. How the IR grows (architecture shape)

The redesign's neutral-IR waist absorbs every axis as one of four shapes. No axis requires a
core redesign; this is the strategy-registry growth model the stress test validated.

| Growth shape | Axes that use it | Touches |
|---|---|---|
| New optional field on `ir.Operation` | pagination, error-model, async/LRO, per-op host, conditional-requests | `ir/model.py`, `spec/schema.py`, `emitters/python/resolve/` |
| New discriminated field on `ir.Body` + a runtime encoder | body-encoding (Form/Multipart/Ndjson/RawBytes/FieldMask) | `ir/model.py`, `runtime/request.py`, `runtime/session.py`, `resolve/` |
| New `AuthScheme` union member + a new `httpx.Auth` mechanism | generated-key, secret-in-path, SigV4, token-provider; mTLS reaches transport | `ir/auth.py`, `runtime/auth.py`, `resolve/` |
| New `NeutralType` variant | discriminated + undiscriminated unions; scalar formats | `ir/types.py`, `spec/loader.py:37-54`, `emitters/python/types.py` |
| New shared spec node + cross-file resolution | cross-file / shared model refs | `spec/loader.py`, `spec/schema.py`, `emitters/python/resolve/` |
| New primitive in the transport return | response-header capture (the keystone) | `runtime/request.py`, `runtime/session.py`, every model-unwrapping caller |

Two foundations are front-loaded because they unblock the most downstream axes:
- Type-system unions + cross-file refs (P1): the #1 universal gap; body/error item models and
  fastmcp all depend on them.
- Response-header capture (P2): the keystone primitive that independently unblocks LinkHeader /
  HeaderCursor pagination, ETag conditional requests, rate-limit surfacing, and the LRO
  different-host poll. `Session.send` today returns only `model.model_validate(response.json())`
  with no header reach; it must expose captured headers alongside the parsed model.

## 6. Build order (dependency-ordered phases)

Each phase proves one axis on its anchor endpoint before the next. Within a phase, rule-of-three
governs: build a strategy only when a real anchor endpoint + its byte/behavioral target exists.

| Phase | Build | Anchor(s) | Prereq |
|---|---|---|---|
| P0 debt-zero | D1 multi-op tests; D2+D4 204/first-2xx; D3 no-facet gate; D5 Assembled-CLI writes | ycli me/priorities + a delete-bearing resource | - |
| P1 type foundation | discriminated + undiscriminated unions; cross-file / shared model refs; scalar formats (int64-as-string, RFC-2822 dates) | Notion blocks / GitHub `string\|integer`; k8s `ObjectMeta`; YC int64 / Twilio dates | P0 |
| P2 response plumbing | response-header capture (keystone); per-op named hosts | GitHub ETag/Link/X-RateLimit; GitHub uploads.github.com | P0 |
| P3 error-model | Status (done) + BodyFlag + PartialSuccess + non-status discriminator; wire tests emitter to READ the declared error strategy | Slack `{ok:false}`; ES `_bulk` items[]; YC gRPC `code` | P1, D1 |
| P4 body-encoding | FormEncoded -> Multipart -> RawBytes -> Ndjson -> FieldMask + `exclude_unset` | Stripe payment_intents; OpenAI files; AWS PutObject; ES `_bulk`; YC Instance.Update | P2, P1 |
| P5 pagination | page+relative-next-uri -> cursor-in-body -> LinkHeader -> HeaderCursor -> DeltaSync -> Scroll-session | Twilio; Slack; GitHub; Tracker; Google; ES scroll/PIT | P2, P3 |
| P6 auth-beyond-header | per-call generated-key -> secret-into-path/query -> SigV4 -> token-provider/refresh -> mTLS | Stripe Idempotency-Key; Twilio `{AccountSid}`; AWS S3; YC IAM / Google refresh; k8s cert | P4 |
| P7 async/LRO | submit -> poll -> unwrap (different-host poll, terminal predicate, result/error unwrap) | YC Instance.Create; OpenAI Batch | P2, P3, D2 |
| P8 remaining cross-cutting | conditional requests / ETag / 304; content negotiation (defer unless consumer); JSON-RPC scope note | GitHub If-None-Match -> 304 | P2, D2 |

## 7. Non-goals (declared, with panel evidence)

Building any of these blind is the wrong-abstraction anti-pattern. Each is out with its
evidence, consistent with the redesign's ratified scope.

| Non-goal | Panel evidence | Why out |
|---|---|---|
| GraphQL | GitHub GraphQL: single `POST /graphql`, client-defined response, `errors[]` in 200 | Inverts the server-authored-one-model-per-response premise; a fork, not a strategy. |
| Streaming / SSE / watch / log-follow | OpenAI `stream:true`; k8s `?watch`/`logs?follow` | Response shape flips on a request field, not status; every downstream surface degrades. `handler:`-only. |
| Inbound receivers / webhooks | Google `events.watch`; Slack Events; Twilio status-callback | Generating a server to receive is outside client-gen; direction-inverted. |
| Interactive auth bootstrap | Google OAuth2 consent; k8s cert provisioning | Cannot drive a browser "Allow". The refresh (P6 token-provider) is in; the bootstrap is out. |
| Presigned-URL generation | AWS S3 SigV4 query-string | Produces a URL, never sends a request, no `responses:` -- does not fit the operation model. |
| API-versioning-as-schema-fork | Notion `Notion-Version` path/shape changes | A maintenance axis, not a runtime one; no panel consumer needs generated multi-version output now. |
| XML codec (Q8) | AWS S3 DeleteObjects / CompleteMultipartUpload | Deferred: heaviest L, request+response codec, no ycli-adjacent consumer. |
| JSON-RPC dispatch (Q6) | Yandex Direct `/json/v5/` | Documented scope note; single consumer, breaks 1-op-per-(path,method). |

Also bounded / deferred (no current panel consumer for a full build): WebSocket/SPDY
bidirectional (k8s exec); query-DSL builders (ES Query DSL, k8s label selectors) -- the
free-form body degrades the auto-suite as an accepted, documented tax, not a feature.

## 8. Testing and oracle strategy

The redesign's oracle layers carry forward and each new axis extends them:

- L0 units: every new IR node, resolver branch, and runtime encoder gets direct unit tests;
  the 100% line+branch coverage gate holds (no `pragma: no cover`; fail-loud guards get a test
  that triggers them).
- L1 snapshots: each phase adds or enriches a committed `out/` fixture that exercises the new
  member; the `refract generate --check` drift gate stays green.
- L3 behavioral (opt-in `@pytest.mark.behavioral`): each runtime-visible axis (body encoders,
  pagination iterators, error policy, header capture, LRO poll, new auth mechanisms) proves the
  generated code + glue import and run against `refract.runtime` with a stubbed transport.
- Tests-emitter coupling (2.8): once pagination/error/body land, the generated auto-suite must
  select stubs from each op's DECLARED axes -- else it stubs a status the API never sends
  (Slack), drains a relative-next-uri wrong (Twilio), or misleads on a partial PATCH (Google).
  This coupling is gated behind D1 (multi-op tests) and each axis it reads.

Each axis member is additionally validated against its real anchor endpoint's documented shape
(from `references/` local docs or the `stress/*.md` analysis) -- the byte/behavioral target that
makes the abstraction real rather than speculative.

## 9. Execution model

Subagent-driven, per the standing goal: the main session orchestrates; each phase is a
research -> plan -> act -> validate -> reflect cycle with fresh implementer + reviewer subagents.
`writing-plans` turns this spec + `artifacts/17` into a per-phase task plan. Phases execute in
order; a phase is not started until its prereqs are green (100% coverage, drift-free, ruff+ty
clean). Findings are re-verified against source and the real API docs, never trusted from a
subagent's "done".
