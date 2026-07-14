# Spec-as-Code — strategy design space (cycle 2, reconciled)

Reconciles the prior session's S1–S6 (digest §1) with this session's fresh anatomy (02),
external landscape (03), and multi-surface prior art (04). Goal: define the candidate
strategies precisely enough to render the 20-op pool under each (cycle 2 worked examples),
and isolate the **genuine open decisions** for the owner.

## 0. What the research has already SETTLED (not open anymore)

These are backed by ≥2 independent sources (prior session + this session's agents), so we do
NOT re-litigate them:

1. **Committed-source codegen, not runtime metaprogramming.** Runtime (prior-S3, botocore-style)
   is the ONLY way to get "fewer repo files," but it kills `py.typed` (must ship `.pyi` stubs
   anyway — the boto3-stubs precedent), makes the 100%-coverage gate cover a generic engine not
   per-resource behavior, and forces rewriting ARCH-1/2/3 + snapshots + import-linter (all
   file-coupled). Agent 4 independently confirmed *every* real multi-surface generator
   (Stainless/Speakeasy/liblab/cnoe/aaz/FastMCP-generate-cli) emits **committed source via an
   IR+template pipeline** — nobody wires runtime introspection into a second framework. → runtime is OUT.
2. **External/SaaS toolchains are OUT.** Fern empirically rejected (hands-on: 4150 LOC/2 endpoints,
   foreign `httpx`/`UniversalBaseModel` identity, CLI+MCP = gated Rust binary not Python).
   Stainless dead (Anthropic, 2026-05-18). Speakeasy = Go CLI / TS MCP, paid-per-language.
   TypeSpec/Smithy Python emitters are preview/pre-alpha & non-pydantic. → the hand-crafted
   uplink/APIModel/FastMCP stack STAYS; we own the generator.
3. **datamodel-code-generator is the one reusable off-the-shelf component** (pydantic-v2 models
   from JSON-Schema/OpenAPI, MIT, v0.68.1 2026-07-08) — for the `models.py` slice (the biggest
   LOC chunk). Everything else (client/cli/mcp/tests) is our own emitter.
4. **FastMCP.from_openapi is a runtime HTTP proxy, not a source generator** — direct tension with
   ARCH-2/3 ("HTTP only in client.py") and the coverage gate. Useful only as a *possible later*
   validation/quickstart lever, never as the mcp.py source. → MCP layer is templated/emitted.
5. **~15% of ops resist pure declaration** ("escape-hatch residue"): TQL search, binary
   upload/download pipelines, YFM raw-body, discriminated MCP unions, cursor-drain edge cases,
   god-resource sub-op grouping, the `set_permissions` dict exception, `questions_move`
   validator guard, CLI rich-flag write surfaces. Any strategy MUST provide a graceful
   escape hatch (named-strategy enum + a Python `handler: module:fn` hook), NOT force these
   through the template. This is the make-or-break design surface (see 02 §B and digest §6).

## 1. The remaining strategies, defined precisely

All live strategies below produce **committed source** and reuse **datamodel-codegen** for models.
They differ on three orthogonal axes → I name the axes, then the coherent combinations.

**Axis A — Authoring surface** (what a human writes to add an endpoint):
  - **A-yaml**: one concise YAML file per resource (ops as a list). Directory encodes domain/resource.
  - **A-py**: one concise **declarative-Python** descriptor per resource (typed objects, no YAML).
  - **A-openapi**: hand-authored OpenAPI 3.x (standard, verbose). [research-disfavored: verbosity + rip-replace]

**Axis B — Generator internals** (how the spec becomes source):
  - **B-tmpl**: spec → Jinja/str.format templates → source. Direct, no intermediate model.
  - **B-ir**: spec → **typed Python IR** (dataclasses: Resource/Operation/Param/Pagination/Body/
    McpMeta) → per-layer **emitters** walk the IR → source. The IR is the extension point
    (aaz's proven "command model" pattern). New op-shape = new IR field + emitter branch;
    new surface (docs, TS SDK) = new emitter over the same IR.

**Axis C — Internal OpenAPI compile** (optional): also compile the IR → OpenAPI dict, to *later*
  bolt on FastMCP.from_openapi (validation) / Schemathesis (contract tests) for free. Additive.

### The coherent candidates

| Name | = prior | Authoring | Internals | One-line identity |
|---|---|---|---|---|
| **S0** baseline | — | none (scaffold) | str.format | `new_endpoint.py` today: scaffold + fill FILL markers by hand |
| **S1** | S1 ★ | A-yaml | B-tmpl | YAML → Jinja → committed quartet. Simplest real generator. |
| **S4** | S4 | A-yaml | B-ir (+C opt) | YAML → typed IR → emitters. Future-proof; IR is the lever. |
| **S5** | S5 | A-py | B-ir or B-tmpl | Declarative-Python descriptor → codegen. Spec is type-checked Python. |
| **S2** | S2 | A-openapi | off-the-shelf + glue | OpenAPI → datamodel-codegen + custom emitters. Standard fmt, rip-replace risk. |
| **S3** | S3 | A-yaml/py | runtime | runtime metaprogramming. **Ruled OUT (§0.1)** — kept only to concretize the rejection. |
| **S6** | S6 | A-yaml | B-tmpl, non-committed | S1 but generated into gitignored `_generated/`. Repo-hygiene variant. |

### What actually differs for the *author* vs the *maintainer*
- **Author-visible fork = Axis A**: YAML (S1/S4) vs Python descriptor (S5) vs OpenAPI (S2). This is
  what the owner will *feel* every time they add an endpoint. THE headline decision.
- **Maintainer-visible fork = Axis B**: template-direct (S1) vs IR+emitters (S4/S5). This decides
  the C1 north-star ("cost of the N+1 op of an unforeseen shape") and whether a 2nd surface is cheap.
  S1 templates get gnarly as op-shape variety grows (Jinja conditionals for pagination/upload/poll/
  god-resource); an IR isolates that complexity in typed Python the `ty` checker guards.
- S1→S4 is an **evolution path**, not either/or: start template-direct, extract the IR when the
  template conditionals hurt or a 2nd consumer appears. The question is whether to pay for the IR now.

## 2. Invariant mapping (settled by research — same for all committed-source strategies)

| Invariant | How the generator satisfies it |
|---|---|
| ARCH-1 four-surface + op-parity | generator emits all 4 files per resource + registers on domain client/cli/mcp; parity holds by construction; the ARCH-1 test becomes a **free generator-correctness check** |
| ARCH-2 HTTP confinement | only the client.py emitter imports uplink; templates are static |
| ARCH-3 honest MCP annotations | spec carries the write-verb class (RO/WRITE/WRITE_IDEMPOTENT/DESTRUCTIVE) explicitly as DATA; emitter stamps the matching annotation set + `write` tag |
| ARCH-4 serialization confinement | cli emitter always ends commands with `Serializer.serialize(...)` |
| ARCH-6 name snapshots | generated names are deterministic from the spec; snapshot test still guards intentional change |
| ARCH-7/8 DI / config | emitters reuse `Depends(<domain>_client)` + `AppContext`; no env in client |
| 100% coverage gate | generator MUST emit tests too (the biggest cost — the prior session's #1 named risk) |
| py.typed | real committed `.py` — downstream type-checkers see everything |

Runtime (S3) breaks ARCH-1/2/3/6 + py.typed + coverage → that's *why* it's out.

## 3. The escape-hatch design (the crux for "universal + future")

The 20-op pool (02) proves the spec schema must express, as first-class DATA, all of:
- **verb + path + Path/Query/Body params** (all ops)
- **return model** OR **bare scalar** (`issues_count` → `int`, no model — op #15)
- **pagination**: one of `{none, offset, cursor, relative_cursor, next_url}` + page-size/id-field/
  next-field knobs → maps to the existing `PaginationStrategy` enum (ops #2/#3/#4)
- **body mode**: `{typed_model, scalar_params→assembled_dict, raw_dict(allowlisted), base64_upload}`
  — NOT "typed model everywhere" (ops #5 typed vs #19 scalar-assembled vs #18 dict vs #11 base64)
- **write response**: `{model, Ack(factory)}` for bodyless writes (op #7)
- **mcp annotation class** + **hand-tuned docstring** + **CLI help** (the one genuinely creative field)
- **async**: trigger→poll-target linkage (op #12: `pages_clone` → `operations_clone_get`) + CLI `--wait`
- **client internal/public split**: emit the raw `_verb` uplink stub AND the public wrapper that
  composes pagination/Ack/poll (02 §A.6 — many ops are two methods)
- **god-resource grouping**: `<resource>_<sub>_<verb>` flat namespace from one client class (op #17)
- **per-op `handler:` escape hatch**: when a body/computed-prop/guard can't be declared, point at a
  hand-written Python function; generator wires it, does not synthesize it (ops #9 validator,
  #16 body-assembly, #11 pipeline). THIS is what makes it universal — the long tail never blocks.

The strategy that wins is the one where the escape hatch is **cleanest** and the **easy 85%
collapses to near-zero authoring** while the hard 15% degrades to "write one Python function,
declare the rest."

## 4. The genuine OPEN decisions for the owner (cycle 4 brainstorm)

1. **Authoring surface (Axis A)** — YAML (S1/S4) vs declarative-Python descriptor (S5)?
   - YAML: language-agnostic, portable to a future non-Python consumer, classic "spec-as-code,"
     but stringly-typed (`type: "str | None"` as text) and needs a schema-validation layer.
   - Python descriptor: type-checked by the same `ty` that guards the repo, IDE completion, no
     YAML-parse/validate layer, escape-hatch is just a function reference — but couples the spec
     to Python and is "less of a spec." (~60% authored reduction vs ~85% for YAML per prior est.)
2. **Generator internals (Axis B)** — pay for the typed IR now (S4/aaz-style) or start
   template-direct (S1) and extract the IR later? (C1 future-proofing vs time-to-first-value.)
3. **Internal OpenAPI compile (Axis C)** — worth emitting OpenAPI as a byproduct now to unlock
   FastMCP.from_openapi/Schemathesis later, or YAGNI until a 2nd consumer appears?
4. **Success metric** — "fewer authored lines" (all codegen strategies, files stay committed) vs
   "fewer repo files" (only runtime — already ruled out). Confirm the owner accepts committed
   generated files (repo LOC ~flat/grows; authored surface −60..85%).
5. **Migration scope & order** — tracker first (largest win), resource-by-resource, gate green
   throughout, `--check` CI mode? And: do we regenerate the `entities` god-resource or leave it
   hand-written (it's the pathological case)?
