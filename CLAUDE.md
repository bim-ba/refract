# refract

> **refract** is a language-agnostic, spec-driven code generator. Author each API operation once
> in a neutral YAML spec → a typed **IR** → pluggable emitters that produce, per (target language ×
> surface), a typed HTTP client + CLI + MCP server + models + tests (+ an OpenAPI doc). **ycli**
> (github.com/bim-ba/ycli — a Yandex 360 SDK/CLI/MCP) is the first consumer.

**License:** MIT. **Repo:** github.com/bim-ba/refract (public; currently unpushed — see below).

## Current status (read `docs/roadmap.md` for the full picture)

Two milestones are built on branch **`feat/me-walking-skeleton`** (`main` is intentionally
unborn; **nothing is pushed** — the first push to the public repo is **owner-approval-gated**):

- **Milestone A** — the `me` walking skeleton: renders ycli's `tracker/me` resource byte-identical
  across all 6 files (models/client/cli/mcp/`__init__` + a combined test file).
- **Milestone A.2** — `priorities` / the **body registry**: renders ycli's `tracker/priorities`
  byte-identical across 4 files (models/client/mcp/`__init__`); `cli.py` + tests deferred (see roadmap).

`uv run refract generate --check` renders **both** resources (10 files) byte-identical to real ycli
(`diff -r out golden` is empty). 55 tests, 100% line coverage, ruff/ty clean.

## Architecture — four layers, strict downward dependency

```
1. SPEC     examples/<consumer>/<domain>/<resource>/resource.yaml   — neutral YAML, no language
      │     refract/loader.py: a pydantic layer (extra="forbid") validates + LOWERS to the IR
2. IR       refract/ir/model.py — frozen, language- & surface-neutral dataclasses. THE PRODUCT.
      │     emitters read ONLY the IR (nothing here knows about Python/uplink/typer/fastmcp).
3. EMITTERS refract/emitters/python/{models,client,cli,mcp,tests}.py — each `emit(res) -> str`
      │     + refract/format.py (`ruff_format`, the post-emit pass) + _common.py (shared helpers)
4. OUTPUT   committed generated source (examples/.../out/**) + refract/generate.py driver + `--check`
```
A future `emitters/typescript/…` reads the identical IR. The emitter signature `emit(res) -> str`
is the plugin boundary.

## Core conventions & invariants (do not violate)

- **Byte-identity oracle.** Every emitter is proven by `emit(ir) == read(golden)` — exact
  byte-equality against a **verbatim copy of real consumer source** (`examples/.../golden/**`).
  When a test fails: `difflib.unified_diff` to locate it, then **fix the emitter, never the golden.**
- **Strategy-registry principle** (the design's north star). Every variable axis — auth · pagination
  · body · async/LRO · errors · tests — is a registry of built-in, parameterized strategies (PascalCase)
  **plus a `Custom` strategy delegating to a hand-written `handler:`**. New need = register a strategy;
  never special-case. A pattern that recurs across a whole platform earns a first-class registry, not
  a per-op handler. (Full taxonomy: `docs/design.md`.)
- **YAGNI-for-coverage.** Implement ONLY the code paths the current resources exercise. The gate is
  **100% LINE coverage** (`--cov-fail-under=100`, no `--cov-branch`, matching ycli) with **no
  `# pragma: no cover`**. A new op-shape/model-shape/registry-member arrives with the *resource that
  first needs it*, together with its byte-target golden — not speculatively.
- **Self-contained.** refract MUST NOT import the consumer (`ycli`). Goldens are opaque text
  fixtures; `examples/` is excluded from ruff/ty (it holds external source + generated output that
  references uplink/typer/fastmcp/ycli, none installed here).
- **ruff config is load-bearing.** `[tool.ruff]` MUST match the consumer's exactly (byte-identity
  depends on it). Emitters emit structurally-correct, **un-wrapped** text and return
  `ruff_format(rendered)`; ruff is the single authority on wrapping/spacing — never hand-emulate it.
- **`--check` drift gate.** `refract generate --write` renders; `--check` re-renders in memory and
  exits 1 on any diff. A test invokes it.
- **Data-presence surface-gating** (`render_resource`): a surface is emitted only when the resource
  has its data — `cli.py` iff any op has a `cli` facet; the test file iff any op has `tests`; `mcp.py`
  iff any op has an `mcp` facet. (So `me` → 6 files, `priorities` → 4.)

## Adding a resource (the proven workflow)

1. **Read the real consumer source** for the resource — it is your byte-target (do not invent shapes).
2. **Author the spec** `examples/<consumer>/<domain>/<resource>/resource.yaml` (neutral v2 YAML —
   full-word keys, explicit `responses: {200: {model}}`, PascalCase strategy names). While in
   development, stage it under `tests/fixtures/` so the `generate` glob doesn't render it before its
   emitters exist; graduate it into `examples/` when the emitters + surface-gating are ready.
3. **Copy the golden(s)** verbatim into `examples/<consumer>/golden/…`.
4. **Extend the emitter** for the new shape, guarded by a byte-equality test AND a regression anchor
   (existing resources stay byte-identical). Keep 100% line coverage honestly.
5. **Graduate + surface-gate**, regenerate `out/`, and confirm `refract generate --check` exit 0.

Use `superpowers:subagent-driven-development` (one implementer subagent per task, byte-identity as the
acceptance oracle, independent re-verification after each). Build plans live in `docs/superpowers/plans/`.

## Tooling & gates (mirror in CI — `.github/workflows/ci.yml`)

`uv` (Python ≥3.12). Runtime deps: `pydantic` + `pyyaml` + `ruff` (the format subprocess). Dev:
`pytest`/`pytest-cov`/`ruff`/`ty`. Before claiming green, run ALL of:
`uv run ruff format --check .` · `uv run ruff check .` · `uv run ty check` · `uv run pytest` (100%) ·
`uv run refract generate --check`.

## Safety

- **Branch → PR → explicit owner approval before merge/push.** No direct push to `main`; the first
  push to the public repo needs the owner's go-ahead. `main` is unborn until then.
- **Never** write a skip-CI token (`[skip ci]` / `[ci skip]` / `[no ci]` / `[skip actions]` /
  `[actions skip]` / a `skip-checks:` trailer) in any commit/PR message.
- **Never** hardcode secrets/tokens/org-ids. Auth secrets are `env:` references in the spec only.
- Commit messages use Conventional Commits; end with
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## Where things live

- `docs/design.md` — the frozen **v2 design blueprint** (the spec format, all registries [v1]/[roadmap],
  the IR, emitter framework, OpenAPI interop, scope non-goals). The authoritative design.
- `docs/roadmap.md` — **current build state + backlog + deferred debt + next milestones. Start here to resume.**
- `docs/research/` — the design rationale & the 14-API stress-test validation record (why this design;
  where public APIs do/don't fit). `docs/research/README.md` indexes it.
- `docs/superpowers/plans/` — the task-decomposed build plans (executed via subagent-driven-development).
- `.superpowers/sdd/` — the build progress ledger + per-task reports (git-ignored scratch).
- `examples/ycli-tracker/` — the first consumer's specs (`tracker/**/resource.yaml`), the byte-target
  `golden/**`, and the generated `out/**`.
