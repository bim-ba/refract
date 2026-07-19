# Deferred / "D+" backlog (DRAFT sketch - refine later)

> A short backlog of demand-driven milestones beyond the named next ones (OpenAPI frontend,
> public packaging, TypeScript backend, ycli integration). These are NOT planned yet - each is
> additive (a registry member / a new frontend or backend) and pulled in only when a real consumer
> needs it. Source: design-spec sections 15-16 non-goals + artifacts/16-17. Untracked draft.

## Naming note (clean up when we formalize)

The letters collide across docs: design-spec "Workstream B" = OpenAPI frontend; roadmap.md
"Milestone B" = ycli integration. Recommend dropping letters and using content names. This backlog
is the "later / D+" bucket referenced loosely as "D and others".

## Backlog items (each additive, demand-driven)

| Item | What | Why deferred | Size |
|---|---|---|---|
| **Rust backend** | 3rd output language (`@backend("rust")`, core: reqwest) | After TypeScript proves the backend is genuinely drop-in; Rust is the natural 3rd | L |
| **protobuf frontend** | 3rd input adapter (protobuf/gRPC service defs -> neutral IR) | After OpenAPI proves the Frontend seam holds for a second input | M-L |
| **GraphQL** | A separate frontend+backend PAIR, not a strategy | Different paradigm (client-defined responses, no wire op unit, errors-in-200); a "mode", ratified out of v1 | XL |
| **Streaming / SSE / watch / log-follow** | Response shape flips on a request field | `handler:`-only or a v2 streaming mode; every downstream surface degrades. Ratified non-goal | L |
| **Inbound receivers / webhooks** | Generating a SERVER to receive push delivery | Categorically outside client-gen scope (direction-inverted) | out |
| **webhook-verify** | Signature-verification helpers for inbound payloads | Adjacent to receivers; small helper library, not codegen | S |
| **Advanced auth: runtime-resolved base-url / token-minting** | Jira 3LO host resolution, GitHub-App token minting | Beyond the auth axes in the current milestone; needs a real consumer | M |
| **Versioned IR artifact + migrations** | Persist/version the neutral IR (the Fern path) | Only matters once THIRD-PARTY backends consume the IR; premature now | M |
| **JSON-RPC single-endpoint dispatch** | N logical ops on one endpoint + body discriminator (Yandex Direct) | Single known consumer; breaks 1-op-per-(path,method) + OpenAPI validity. Document, don't build, until a 2nd consumer | M |
| **Cross-cutting leftovers** | content-negotiation, conditional-requests/ETag, per-op host beyond the axes | Partly covered by the current axes milestone's P8; the rest is demand-driven | S-M |

## Rough sequencing intuition (owner steers)

1. Prove the seams first: OpenAPI frontend (2nd input) + TypeScript backend (2nd output) - these
   validate the architecture's core claim (additive frontends/backends).
2. Then a 3rd of each on demand: protobuf frontend, Rust backend.
3. GraphQL + streaming are their own mode(s) - largest, last, only with a committed consumer.
4. The small helpers (webhook-verify, advanced auth, JSON-RPC note) ride along when their consumer arrives.

## Open questions

- Is Rust / protobuf actually wanted, or is Python + TypeScript + OpenAPI the realistic ceiling for v1-public?
- GraphQL: worth a separate mode at all, or a documented non-goal permanently?
- Versioned IR: only if we expect external backend authors - do we?
