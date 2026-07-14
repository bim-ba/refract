# Spec-as-Code — evaluation rubric (orchestrator, cycle 1)

The owner's north star (verbatim intent): make it **maximally generalized, universal, template-driven,
easy to scale to ALL resources and operations — existing AND future**. So the deciding axis is not
"how few lines today" but "how cheaply does the Nth *new* operation of an *unforeseen shape* get added."

## Weighted criteria (each strategy scored 1-5)

| # | Criterion | Weight | Why it matters here |
|---|---|---|---|
| C1 | **Extensibility to novel op shapes** | ×3 | The explicit north star. A new pagination style / auth flow / multipart variant must be a small, local addition — not a generator rewrite. Measured by: what does adding op-shape N+1 cost? |
| C2 | **Coverage of the 4 layers** | ×3 | client + cli + mcp + models + tests. A strategy that only generates models (datamodel-codegen alone) leaves 3 layers hand-written. |
| C3 | **Invariant preservation (ARCH-1..11)** | ×3 | py.typed real source, ARCH-6 name snapshots, import-linter on real modules, 100% coverage gate, reviewable diffs, ARCH-3 honest annotations. Runtime metaprogramming fights ALL of these. |
| C4 | **Authoring ergonomics** | ×2 | One endpoint author should hold the whole spec in their head. Concise, DRY, obvious. The human-tuned MCP docstring must survive as a first-class field. |
| C5 | **Escape hatch for irregular ops** | ×2 | entities god-resource, set_permissions dict, TQL search, polling, multipart. The 10-20% that don't fit the template must degrade gracefully (hand-write one layer, generate the rest) — NEVER block the generator. |
| C6 | **Reviewability & debuggability** | ×2 | Can a reviewer read a PR diff? Can you set a breakpoint in the generated code? Generated-and-committed = yes; runtime magic = no. |
| C7 | **Migration cost / incrementality** | ×2 | Can we migrate one resource at a time with the gate green throughout, or is it all-or-nothing? `--check` mode parity with existing gen_coverage.py. |
| C8 | **Toolchain risk / ownership** | ×1 | External SaaS (Fern/Stainless/Speakeasy) = foreign model identity, inverted ownership, sunset risk. In-repo = we own it. |
| C9 | **Future 2nd consumer** | ×1 | Docs site, TypeScript SDK, a 5th surface. An IR-based design makes a new emitter cheap; a template-only design duplicates. |

## The op-diversity stress test (the owner's explicit ask)
Do NOT evaluate on 3 adjacent get/list ops. Take ~20 genuinely different shapes (agent 2 is selecting them)
and, for each candidate strategy, show BOTH: (a) the authored spec, and (b) the generated/produced output.
The winning strategy is the one where the *hard* ops (multipart upload, async polling, TQL search, god-resource
sub-op, questions_move page semantics, grids update_cells, set_permissions nested verbs) stay expressible and
the *easy* ops (get/list/delete) collapse to near-zero authoring.

## Candidate strategy families to compare (to be finalized after agent 1 recovers prior S1-S4)
- **S0 — status quo** (`new_endpoint.py` str.format scaffold; human fills FILL markers). Baseline.
- **S1 — bespoke YAML → Jinja → committed quartet.** Build-time, reviewable diffs, no IR.
- **S2 — OpenAPI 3.x → off-the-shelf emitters** (datamodel-codegen for models + custom templates/FastMCP.from_openapi).
- **S3 — runtime metaprogramming** (one spec, build client/cli/mcp dynamically at import; zero generated files).
- **S4 — DSL → typed IR → fan-out emitters.** The IR is the extension point; N emitters, one per surface.
- **S5 — Python-as-spec** (declarative Python objects; either a generic runtime engine OR a codegen materializer).
  (Distinct from S3: the spec is typed Python, not YAML — leverages the type system as the authoring surface.)

## Hard constraints (non-negotiable, from ARCHITECTURE.md + CLAUDE.md)
- Output MUST satisfy ARCH-1..11 by construction (the conformance harness then verifies for free).
- 100% coverage gate stays green (generated code needs generated-or-trivial tests).
- No new runtime dependency without justification; `uv add` only (never hand-edit pyproject).
- The human-tuned per-tool MCP docstring + honest verb→annotation class are DATA in the spec, not inferred.
- Incremental: migrate resource-by-resource, gate green throughout; a `--check` CI mode like gen_coverage.py.
