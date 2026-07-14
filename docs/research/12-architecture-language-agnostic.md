# Language-agnostic generator — architecture (cycle 5, owner-reframed direction)

Owner's reframed goal: a professional, **language-agnostic** generator, likely a standalone PUBLIC
repo; ycli is the first consumer. This kills Python-descriptor (S5, Python-only) and makes the
**typed IR the product**. Below is the stable layered design (the runnable thin-slice prototype in
`../sac-prototype/` proves it; this doc is the vision the prototype instantiates).

## The four layers (strict dependency direction ↓)

```
1. SPEC   (authored, neutral)     specs/<domain>/<resource>/resource.yaml   — YAML, no language in it
        │  loader.py + a pydantic spec-validation schema (reject malformed specs early)
        ▼
2. IR     (the product, neutral)  apigen/ir/model.py — frozen typed dataclasses
        │  Resource · Operation · Param · Model · Field · Pagination · McpMeta · CliMeta · handler
        │  Language- AND surface-agnostic. The stable contract every emitter depends on.
        ▼
3. EMITTERS  (per language × surface)   apigen/emitters/<language>/<surface>.py   → emit(res: IR) -> str
        │  python/ { models · client · cli · mcp · tests }   ← built now
        │  (typescript/ , go/ , … are drop-ins later — same IR, new emitter dir)
        │  + openapi.py  (IR → OpenAPI 3.1 doc)  ← byproduct, NOT a target language
        ▼
4. OUTPUT  (committed source)     out/<domain>/<resource>/{__init__,models,client,cli,mcp}.py
                                  out/<domain>/<resource>/tests/test_client.py
```

Why this order is right for "universal + future": the **IR is the extension point**. A new op-shape
= one new IR field + a localized clause in each emitter (`ty` + `assert_never` force every emitter to
handle it — compile-time exhaustiveness). A new **language** = a new `emitters/<lang>/` dir over the
unchanged IR. A new **surface** = a new emitter file. Nothing upstream of the change moves.

## The OpenAPI byproduct (why it matters for a public tool)
`emitters/openapi.py` compiles the IR → an OpenAPI 3.1 doc. This is NOT a code target — it's the
interop + testing lever:
- **schemathesis (Tier-2 tests)** consumes it to run live/contract tests (validated: schemathesis
  needs an OpenAPI schema + a live/mock target — see `11-testgen-stack.md`).
- **Ecosystem interop** — a public "spec→wrappers in any language" tool that also speaks OpenAPI can
  both *emit* OpenAPI and (later) *ingest* existing OpenAPI specs as a second front-door. Big adoption lever.
- Keep it additive/opt-in (Axis C from `05`): build when the schemathesis tier or an external
  consumer actually needs it, not before — but the IR→OpenAPI mapping is cheap because the IR
  already carries paths/params/schemas.

## Escape hatch (the ~15% irregular ops)
Per-op `handler:` reference to a hand-written Python function (upload pipelines, TQL body assembly,
validator guards, the `set_permissions` dict exception). The generator WIRES the handler on each
surface; it never synthesizes the irregular logic. The long tail never blocks generation. (~2–3 of
~230 ops degrade fully to "pure registration" — the upload pipelines; measured in `10`.) In a YAML
world the handler is a `"module:fn"` string (unchecked → ImportError at build); mitigate with a
generator-side import-resolution check in `--check` so a bad handler ref fails the gate, not runtime.

## Test tiers (validated, `11-testgen-stack.md`)
- **Tier 1 — in-gate, every commit, deterministic** (the 100%-coverage backbone): generated
  `responses`-stubbed unit tests whose asserts are **authored DATA in the spec** (never emitter-computed
  — kills the code-vs-code tautology). Non-vacuous because models are generated from a *separate*
  source than ops, so an assert cross-checks two artifacts. Optionally enriched with seeded-`faker`
  fixtures + `@example`-pinned `hypothesis` property tests (`derandomize=True`, pinned seed) as
  additive checks — never the sole source of a covered line.
- **Tier 2 — opt-in / nightly, outside `uv run pytest`**: `schemathesis` against a mock (or the real
  API) built from the emitted OpenAPI doc — the only thing that catches spec-vs-reality path drift.

## `--check` drift gate (mirrors scripts/gen_coverage.py)
`generate.py --write` renders the tree; `--check` re-renders in memory and exits 1 on any diff (plus
resolves every `handler:` import). A test invokes `--check`, so generated files can never silently
drift from their specs. Same proven pattern as `gen_coverage.py --check` / `test_coverage_readme.py`.

## ARCH-1..11 satisfied BY CONSTRUCTION (free verification)
Committed real `.py` per resource → ARCH-1 four-surface + op-parity (the ARCH-1 test becomes a free
generator-correctness check), ARCH-2 HTTP confinement (only the client emitter imports uplink), ARCH-3
honest annotations (verb→class is spec DATA), ARCH-4 Serializer, ARCH-6 name snapshots (deterministic
from spec), ARCH-7/8 DI, py.typed (real source), 100% gate (Tier-1 tests emitted). This is exactly why
committed-source codegen wins and runtime loses.

## Standalone-repo extraction path (the public-tool ambition)
Design `apigen/` with ZERO ycli imports — it depends only on the IR + emitter plugins. Then:
- **In ycli now**: `apigen/` lives in-repo; ycli owns `specs/` + a small `emitters/python/` tuned to
  ycli's idioms (uplink/APIModel/fastmcp/typer). Migrate resource-by-resource, gate green throughout.
- **Graduation**: lift `apigen/` (IR + loader + emitter framework + the python emitters as a reference
  plugin) into its own public repo. ycli then depends on it and keeps only `specs/` + any ycli-specific
  emitter overrides. The emitter interface (`emit(res: IR) -> str`) is the plugin boundary; new
  languages ship as separate emitter packages.
- **Naming/packaging**: owner's call (a memorable name + a `pyproject` + a plugin-discovery mechanism
  for emitters). Not decided here.

## Open items the prototype/owner will settle
- Exact IR field set (the prototype's `ir/model.py` is the first cut; extend as real op-shapes demand).
- Whether the ycli migration keeps `entities` hand-written (owner: yes, last/separate) — the generator
  must tolerate a mix of generated + hand-written resources (it already will: it only touches `out/`
  for spec'd resources; hand-written ones stay untouched).
- When to build the OpenAPI emitter + schemathesis tier (Axis C) — defer until the contract tier is wanted.
- Spec authoring ergonomics: pure YAML now; a future front-door could ingest OpenAPI for adoption.
