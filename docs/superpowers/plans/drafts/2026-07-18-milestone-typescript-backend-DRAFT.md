# Milestone: TypeScript backend (Workstream C) - DRAFT

> Directional sketch, NOT a bite-sized TDD plan. Refined later via superpowers:writing-plans.
> Read-only research; no source touched.

## 1. Goal

Prove refract's backend abstraction is genuinely drop-in by shipping a real second
`LanguageBackend`: implement `refract.emitters.typescript`, register `@backend("typescript")`,
and regenerate the ycli-tracker corpus as a working TypeScript SDK from the SAME neutral IR that
already drives the Python backend - zero edits to `ir/`, `spec/`, `generation.py`, or
`registry.py`.

## 2. Why / value

This is Workstream C in the roadmap (`docs/superpowers/specs/2026-07-14-refract-architecture-
redesign-design.md` section 16: "TS-бэкенд - проверяет, что core действительно per-язык, а бэкенд
drop-in"). Decisions #6 (composition-over-mixins) and #18 (core hand-written once per language;
typed surface + glue generated) are architectural CLAIMS today, backed by exactly one instance
(Python). A second language is the only way to falsify them. TypeScript is also the highest-demand
second SDK language for API consumers (fetch-based clients are the default JS/TS expectation;
Fern/Stainless/Speakeasy all ship TS first or second per section 2's provenance sweep).
`docs/adding-a-language.md`'s checklist exists but has never been exercised end-to-end - this
milestone is also that checklist's first real test.

## 3. Scope IN

| Piece | Mirrors (Python reference) | Notes |
|---|---|---|
| `refract.emitters.typescript` package | `emitters/python/{backend,naming,types,format,docstrings,layout}.py` | same file layout |
| TS `Naming` | `python/naming.py` | camelCase/PascalCase, JS reserved-word guarding, safe param names |
| TS `TypeMapper` | `python/types.py` | `NeutralType -> TS` (string/number/boolean/unknown, `T[]`, `Record<K,V>`, ref-by-name); exhaustive `match`/`assert_never` mirrors `PythonTypeMapper._base` |
| TS `Formatter` | `python/format.py` (wraps `ruff` via subprocess) | wraps prettier or biome via subprocess (open question) |
| TS `Docstrings` | `python/docstrings.py` | TSDoc `/** ... */` block rendering |
| TS `Layout` | `python/layout.py` | same (resource, surface) -> path map, `.ts` extensions, `root_client` -> `{domain}/client.ts` |
| Per-resource surfaces: `models`, `requests`, `client`, `tests`, `package` | `surfaces/{models,requests,client,tests,package}.py` + `resolve.py` + `templates/*.jinja` | same resolver-then-Jinja-leaf split (decision #3) |
| Domain glue: `root_client` (`DomainEmitter`) | `surfaces/root_client.py` | aggregates resources, builds the TS client, selects the auth mechanism from `ir.ClientConfig`/`AuthScheme` |
| TS reference runtime | `runtime/{request,session,auth,base}.py` | `Request<T>` (sans-I/O), `Session.send` over `fetch`, `HeaderAuth`/`MultiHeaderAuth` as fetch-request mutators - hand-written ONCE per decision #18 |
| `@backend("typescript")` registration | `python/backend.py` | via the existing lazy-import registry (`emitters/registry.py`) - zero central-file edits |
| Regenerate ycli-tracker corpus in TS | `examples/ycli-tracker/{tracker,client.yaml}` | same fixture spec, second output language, into a parallel `out-ts/`-style dir |

`cli` and `mcp` surfaces (`surfaces/{cli,mcp}.py`) are read as reference but land only if scope
allows - see Scope OUT.

## 4. Scope OUT / defer

- TS `cli` and `mcp` surfaces - Typer has no direct TS analogue and an MCP TS SDK is a separate
  scoping question; land `models`/`requests`/`client`/`tests`/`root_client` first, add `cli`/`mcp`
  as a follow-up once the shape is confirmed, not speculatively.
- Rust backend (Workstream D+).
- npm publish / package.json versioning / registry publishing - packaging, not this milestone
  (mirrors the Python-side "Workstream C-public" scope-out in section 15).
- Growing any of the 6 diversity axes (auth/server/errors/body-encoding/pagination/collections)
  beyond what Python already carries - this milestone proves drop-in, not axis growth (that's
  Workstream B + backlog).
- A versioned/external IR artifact - still YAGNI per decision #8 (in-process backend only).

## 5. Key phases (dependency-ordered)

1. Audit the IR/surface-contract boundary for Python-specific leakage before writing any TS code
   (see Rough size/risk below - one concrete leak already found).
2. Implement the 5 strategies (Naming, TypeMapper, Formatter, Docstrings, Layout) against
   `emitters/api.py`'s ABCs - no surfaces yet, L0-unit-testable in isolation.
3. Hand-write the TS reference runtime over `fetch` (Request/Session/auth mechanisms/base
   Resource) - the one-time, per-language, hand-written core (decision #18).
4. Port `models` + `requests` per-resource surfaces (resolver + templates) - no cross-resource
   dependency; proves `NeutralType -> TS` lowering and the resolver-then-Jinja-leaf split in a
   second language.
5. Port `client` surface + `root_client` domain glue - wires `AuthScheme` selection into the TS
   runtime's fetch-mutator auth mechanisms.
6. Port `tests` surface - pick and wire the TS test runner (vitest vs `node:test`, open question).
7. Register `@backend("typescript")`; regenerate the ycli-tracker corpus end-to-end in TS.
8. Stand up an L3-equivalent oracle for TS: `tsc --noEmit` on the emitted output + run the emitted
   test suite against a stubbed HTTP layer, mirroring `tests/behavioral/test_d_core_runs.py`'s
   import-and-run pattern; then a conformance pass confirming Python and TS clients generated from
   the SAME fixture are behaviorally equivalent (the actual "drop-in" proof; section 12's
   conformance-тесткит parameterized by backend).

## 6. Dependencies

- Needs the neutral IR to carry no Python leakage. Spot-checked this session: `ir/types.py`
  (`NeutralType`), `ir/model.py`, `ir/auth.py` (`AuthScheme`), `ir/client.py` (`ClientConfig`) are
  frozen pydantic with no Python-specific strings baked in (decisions #5, #15, #17 already closed
  this class of gap).
- The per-resource surface SET this milestone ports mirrors what Python has TODAY; it is not
  gated on the axis-growth work (Workstream B / the type-foundation plan) - the walking-skeleton
  IR slice (fixed server, header/multi-header auth, JSON body, status-only errors) is sufficient
  to start and prove drop-in. Axis growth needs matching TS support later, but that is incremental
  once the backend exists, not a blocker to starting.
- `docs/adding-a-language.md` is the existing checklist this milestone should validate and correct
  as it executes.

## 7. Rough size + key risk

**Size: L** - a full second backend (5 strategies + ~5-7 surfaces + domain glue + a hand-written
runtime + a new oracle layer), comparable in scope to the original Python walking-skeleton
(Workstream A).

**Key risk - a concrete leak already found, not speculative:** `EmitContext.package_root`
(`emitters/api.py:34`) is a Python dotted-module-path convention (e.g. `"ycli.yandex.tracker"`),
and it is HARDCODED in the supposedly language-agnostic driver -
`generation.py:22-24`'s `_package_root()` returns `f"ycli.yandex.{res.domain}"` unconditionally,
not derived from `ClientConfig` or the target backend. Every Python surface resolver then splices
it directly into `from {package_root}.foo import Bar`-style strings (`python/resolve.py:195, 248,
269, 377, 705-710, 814-819`). TypeScript has no dotted-module-path import convention (relative file
paths or bare npm specifiers instead), so this cannot be reused as-is: `_package_root` needs to
either move out of the generic driver into a per-backend concern, or `EmitContext.package_root`
needs a second, TS-shaped meaning layered on top. This should be resolved in phase 1 (audit), before
any TS surface resolver is written, since every surface touches it. Secondary, unverified
candidates worth a quick look in the same audit: `RenderedType.imports`'s `Import(module, name)`
shape (does it generalize to TS named-vs-default exports cleanly?) and `Docstrings.render`'s
line-based tuple return (TSDoc's comment shape differs from Python's triple-quote block).

## 8. Open questions

| # | Fork | Options | Notes |
|---|---|---|---|
| 1 | TS test framework | vitest vs `node:test` (built-in) | vitest is the ecosystem default (fast, watch mode); `node:test` has zero extra deps. Affects the `tests` surface templates + the L3 oracle's runner invocation. |
| 2 | Formatter | prettier vs biome | biome is faster (Rust, single binary) and closer in spirit to `ruff` (one fast tool replacing a slower ecosystem standard); prettier is the incumbent most TS consumers already expect. Either way the `Formatter` ABC is one method (`format(source) -> str`). |
| 3 | CLI/MCP surfaces | emit in TS now vs defer | Scope-OUT defaults to defer; revisit only if a concrete consumer pulls for it. |
| 4 | Module format | ESM vs CJS (or dual-publish) | Affects `Layout` paths/extensions, the runtime's own import/export shape, and the generated root client. ESM-only is simplest and matches modern TS defaults; dual-publish adds build-step complexity this milestone likely shouldn't take on. |
