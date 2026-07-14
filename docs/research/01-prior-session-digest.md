# ycli Specification-as-Code research — prior-session digest

Faithfully reconstructed from the actual transcripts. Primary source of substance is
session `f8cba46e-7db1-4d1a-9a88-4375fc9395ca.jsonl` (2026-07-10, 394 lines) — this is
the ENTIRE research session including the real Fern spike (both happened in this one
session, contrary to what the roadmap distillation implies about "prior session (2026-07-10)"
being a single monolithic thing — it is, but it also contains a full hands-on spike, not
just the strategy synthesis). Session `a065ce3b-...` (2026-07-12, 1501 lines) is a much
later, much broader "improve ycli" orchestration session (ARCH-3 removal, MCP read/write,
coverage audit, live API testing, tech-debt audits) that only *touches* spec-as-code by
(a) dispatching one subagent that re-measured structural duplication and (b) writing the
final roadmap file `docs/superpowers/specs/2026-07-12-improvement-roadmap.md` §1, which
is the 1-page distillation the caller already has. Session `b82cde51-...` (97 lines,
interrupted) is a short-lived orchestrator predecessor to `a065`; it does not contain
spec-as-code substance itself, only the goal statement that led to the 5-agent wave.

All quoted numbers/code below are verbatim from the transcripts unless marked as paraphrase.

---

## 0. Session shape (research → act → validate → reflect, run twice)

The user's own instruction (from `f8cba46e` line ~9, Stop-hook condition) was to research
"массовое сжатие" (massive shrinkage) of the codebase via many small YAML files in a nested
directory structure (`issues/__id__/get.yaml`) generating CLI/SDK/MCP/tests, with strict
no-train-data guardrails. DoD: ≥3 workable strategies + a verdict on sanity.

**Cycle 1 (lines 1–246):** local ground-truth measurement → 4 parallel subagents (external
prior-art) → POC → `STRATEGIES.md` synthesis → `AskUserQuestion` to the user.
**User's choice (line 250 tool_result / line 252):** "спайк Fern сначала" (spike Fern first),
format: visual Artifact.
**Cycle 2 (lines 253–394), same session:** design + publish HTML Artifact → user pushback on
an X-Org-Id casing claim (retracted) → explicit `/goal` to do a REAL Fern spike, cycles again →
environment check → hands-on `fern generate --local` → verdict "Fern does not fit" → Artifact
updated → a second subagent cross-check resolves a docs-vs-empirics contradiction about
`FERN_TOKEN`.

---

## 1. Every strategy considered (full definitions)

Source: `STRATEGIES.md` written to
`/tmp/.../f8cba46e-7db1-4d1a-9a88-4375fc9395ca/scratchpad/STRATEGIES.md` (full text captured
below, this scratchpad file no longer exists on disk — recovered from the transcript's Write
tool_use at line 241) and the matching chat answer at line 246.

Six strategies were delivered: **3 core (S1/S2/S3) + 3 extras (S4/S5/S6)**. Two earlier,
looser strategy sketches (A–F) appear in the intermediate `local-findings.md` (line 138) and
were later collapsed/renamed into S1–S6 — see §8 for that discarded lettering.

### S1 — In-repo YAML→codegen ("grow new_endpoint.py into a real generator") ★ recommended core
> Own compact nested-YAML IR (directory-as-URL-template) → pydantic-validated spec model →
> Jinja templates emit the SAME committed `.py` (models/client/cli/mcp) + generated tests +
> regenerated domain wiring + snapshots.
- Add/change/remove a resource = touch ONE YAML file, run `regen`.
- Keeps: py.typed, 100% coverage, ALL ARCH invariants (real files satisfy them), uplink
  eager-annotation, IDE, debug.
- Reuse `datamodel-code-generator` for the models slice; keep the pagination strategy enum +
  a Python escape-hatch hook for the ~15% bespoke residue (computed props, body assembly,
  not-found guards).
- Cost: you own a generator (~a few hundred LOC + templates). Authored surface −85%; repo LOC
  ~flat (generated files are still committed .py).
- **Effort: medium. Risk: low.** "Best fit to the owner's vision + the repo's guarantees."

### S2 — Standard IR + off-the-shelf toolchain (OpenAPI-split or TypeSpec → existing generators)
> Author in OpenAPI multi-file (Redocly `split`, one file per endpoint) or TypeSpec (one `.tsp`
> per resource) → bundle → fan out: OpenAPI Generator/datamodel-code-generator (SDK+models) +
> `FastMCP.from_openapi` (MCP) + Schemathesis (contract tests) + a thin custom Typer emitter
> (CLI).
- Inherits validation/lint/docs/mock/contract-tests; least bespoke tooling long-term.
- Cost: generated SDK/MCP shapes are NOT ycli's uplink/APIModel/FastMCP-tool conventions →
  rip-and-replace of the hand-crafted stack + rework of ARCH invariants; OpenAPI verbosity or
  TypeSpec Node/compile step + preview-only Python emitter.
- **Effort: high. Risk: medium-high** (identity change). Reward: smallest owned tooling.

### S3 — Runtime interpretation / metaprogramming (botocore-style) — NOT recommended
> Delete per-resource files; a thin engine reads YAML at import, builds Typer commands +
> `pydantic.create_model` models + FastMCP tools dynamically.
- Achieves literal "few `.py` files." BUT kills py.typed (must ship generated `.pyi` anyway,
  same as boto3-stubs), makes 100% coverage semantically thin (you'd cover a generic engine,
  not per-resource behavior), opaque tracebacks, and REQUIRES rewriting ARCH-1/2/3 + snapshots
  + import-linter.
- **Effort: medium-high. Risk: HIGH.** "Only viable if those three guarantees are explicitly
  relaxed."

### S4 (extra) — Hybrid: nested-YAML authoring → compile to OpenAPI as canonical IR → fan out
> Best-of-both: keep the owner's one-file ergonomic; OpenAPI as internal IR unlocks
> `FastMCP.from_openapi` + Schemathesis for free while own Jinja templates keep the
> uplink/Typer/APIModel style + escape hatches. Slightly more moving parts.
This is explicitly framed as the **evolution target of S1**, not a standalone alternative —
"S1 → S4" is the recommended path, in that order.

### S5 (extra) — Declarative-in-Python (no YAML): a `Resource` descriptor / registry
> Collapse boilerplate with a declarative base class + metaclass that builds client/cli/mcp
> from Python attributes. Keeps types natively (it's real Python), less machinery than a
> generator — but doesn't deliver the "one YAML file" vision and stays Python-heavy.
"Good low-risk fallback." −~60% authored (lower than the other strategies' ~85%, because no
YAML/spec compiler is built).

### S6 (extra) — Codegen at build/release time, don't commit generated code
> Emit into a gitignored `_generated/` during build; ship generated `.pyi` + wheel. Satisfies
> literal "few files in repo" while keeping types.
Cost: packaging/reproducibility complexity; the 100%-coverage gate must run against generated
code in CI. Explicitly framed as "a variant of S1 for those who want a clean repo."

### Comparison matrix (verbatim, from STRATEGIES.md)
| Strategy | Authored −% | Repo LOC | py.typed | 100% cov | ARCH kept | Owner-tooling | Effort | Risk |
|---|---|---|---|---|---|---|---|---|
| S1 in-repo codegen | ~85% | ~flat | ✅ | ✅ | ✅ | own generator | med | low |
| S2 standard IR+tools | ~85% | shrinks-ish | ✅ | rework | rework | least | high | med-high |
| S3 runtime interp | ~85% authored, files ~gone | shrinks | ❌(stubs) | thin | rewrite | own engine+stubs | med-high | high |
| S4 hybrid | ~85% | ~flat | ✅ | ✅ | mostly | own templates | med-high | med |
| S5 py-descriptor | ~60% | shrinks some | ✅ | ✅ | ✅ | small base | low-med | low |
| S6 build-time gen | ~85% | shrinks | ✅(stubs) | CI-gen | ✅ | own gen+pkg | med-high | med |

### The reframing that drove the whole recommendation (this is the load-bearing argument)
"Minimal Python" has **two different meanings that point to different architectures**:
- **(a) Fewer lines to author/maintain** → codegen wins (~85% less authored surface) while
  keeping every guarantee. Generated `.py` still lives in the repo, so raw repo LOC does not
  shrink (it grows slightly by the generator + templates).
- **(b) Fewer `.py` files in the repo** → only runtime interpretation achieves this, and it
  breaks three load-bearing guarantees:
  1. `py.typed` static types — "botocore had to ship `boto3-stubs` separately — the runtime
     path does not even avoid codegen, it just produces worse artifacts."
  2. `--cov-fail-under=100` gate — "you'd cover a generic engine, not per-resource behavior."
  3. ARCH-1/2/3 + snapshots + import-linter — all built around physical per-resource files.

  **Verdict: "not worth it for a typed, 100%-coverage published library."**

**Bottom line (verbatim): "adopt spec-as-code via CODEGEN, not runtime metaprogramming. Shrink
the maintained surface, keep the generated files real."**

---

## 2. The Fern hands-on spike (lines 288–394, second cycle, same session)

Triggered by an explicit user `/goal`: *"Сделай реальный Fern спайк, работай по тем же циклам
которые я определял в начале, параллельно и повторяющеся (research -> validate -> reflect).
Не опирайся на train data свою, используй тулы."* (Do a real Fern spike, same
research→validate→reflect cycles, don't rely on your training data, use tools.)

**Environment check (line 302):** node v26.4.0, npm 11.18.0, global prefix
`/home/sava/.npm-global` (no sudo needed), Fern not yet installed, Docker present (checked
next).
**CLI confirmed live (line 311):** `fern init --openapi <spec>`, `fern add <generator>`,
`fern generate --local` (runs generators in Docker), `--group`.

**What was actually run (line 312 → 390), verbatim table from the final summary:**
| Step | Result |
|---|---|
| `npm i -g fern-api` | 5.67.1, no sudo; Docker 29.6.1 running |
| `fern init --openapi` (2 ycli resources) | ok; scaffolded `fern/generators.yml` |
| `fern add fern-python-sdk` | 5.17.1; `fern-cli`/`fern-mcp-server` → "Unrecognized" |
| `fern generate --local` | **exit 0, no login required**, 37 files / 4150 LOC, all compile; a clean re-run also succeeded without auth |

**The hand-authored OpenAPI spec used for the spike** (2 real ycli resources —
`tracker/priorities` list + `tracker/issues/{key}` get), written to
`.../scratchpad/fern-spike/openapi.yml`:
```yaml
openapi: 3.0.3
info:
  title: Yandex Tracker (ycli spike subset)
  version: "3"
servers:
  - url: https://api.tracker.yandex.net/v3
paths:
  /priorities:
    get:
      operationId: priorities_list
      summary: List all priorities
      description: All available issue priorities in the organisation.
      tags: [priorities]
      responses:
        "200":
          description: priority listing
          content:
            application/json:
              schema:
                type: array
                items: { $ref: "#/components/schemas/Priority" }
  /issues/{key}:
    get:
      operationId: issues_get
      summary: Get one issue by key
      description: A single Tracker issue by key (e.g. QUEUE-123).
      tags: [issues]
      parameters:
        - name: key
          in: path
          required: true
          schema: { type: string }
      responses:
        "200":
          description: one issue
          content:
            application/json:
              schema: { $ref: "#/components/schemas/Issue" }
components:
  schemas:
    Priority:
      type: object
      properties:
        key: { type: string, nullable: true }
        display: { type: string, nullable: true }
    Issue:
      type: object
      properties:
        key: { type: string }
        summary: { type: string }
        description: { type: string, nullable: true }
        status: { $ref: "#/components/schemas/StatusRef" }
    StatusRef:
      type: object
      properties:
        key: { type: string, nullable: true }
        display: { type: string, nullable: true }
```

**Why rejected — 3 disqualifying facts (verbatim from line 390's final summary):**
1. **"Covers 1 of 4 surfaces."** Free+local = SDK only. `fern-cli` and `fern-mcp-server`
   generator names both returned "Unrecognized generator." No Python CLI or MCP generator
   exists at all (confirmed both hands-on and by a cross-checking subagent with citations:
   `fernapi/fern-cli` exists but is a **Rust binary**, early-access/gated, CLI+MCP over
   stdio/HTTP — not Python).
2. **"Foreign SDK identity."** Fern output uses `httpx` (sync+async), `UniversalBaseModel`
   (`extra="allow"`, `frozen`), a raw/wrapped client split + `client_wrapper` +
   `RequestOptions`. ycli uses `requests` + declarative `uplink`, `APIModel` (`extra="ignore"`),
   thin `@uplink.get(...)` clients. Adopting Fern = rip-and-replace of the whole stack AND all
   ARCH invariants (no client/cli/mcp/models quartet, no read-only FastMCP annotations,
   snapshots/import-linter tied to ycli's own structure). Fern's own "tests" test its runtime
   (httpx auto-detection), not the API contract.
3. **"Inverted ownership model."** Fern owns the SDK; you hand it the shape. ycli's value is
   the hand-crafted, invariant-protected stack the owner wants to *keep*.

**Volume comparison table (verbatim):**
| Aspect | Fern (fact) | ycli (your style) |
|---|---|---|
| Coverage | SDK only — `fern-cli` and `fern-mcp-server` = "Unrecognized generator" | needs 4 surfaces |
| HTTP | httpx, sync+async | requests + uplink (declarative) |
| Models | `UniversalBaseModel`, `extra="allow"`, `frozen` | `APIModel` (`extra="ignore"`), `XList` RootModel |
| Client | raw/wrapped split + `client_wrapper` + `RequestOptions` | thin `@uplink.get(...)` |
| Volume | **4150 LOC for 2 endpoints** (core runtime alone 3168 LOC) | ~547 LOC shared substrate (whole project) |
| "Tests" | test Fern's own runtime (httpx auto-detect), not the API contract | `responses` stubs on CRUD |

**A resolved contradiction, worth keeping (docs-vs-empirics, line 380–386):** Fern's own docs
(self-hosted deep-dive + changelog v0.59.6) state `fern generate --local` requires
`FERN_TOKEN` via `fern login` for one-time org verification. The hands-on run succeeded with
exit 0 and **no login at all**. Investigation: `~/.fern/id` is an **anonymous analytics ID**
(from the `@scarf/scarf` npm postinstall script, visible in the install log) — not a token. No
`FERN_TOKEN` in env, no `~/.config/fern`, `fern token` never run. A clean re-run of
`fern generate --local` again exited 0 with zero mentions of token/login/auth/org-verify in
output. **Conclusion: "empirics over docs — Fern 5.67.1's free+local generation is actually
even freer than its own docs claim, but this does not change the rejection verdict."**

**Final path re-confirmed after the spike:** S1 → S4 ("grow `new_endpoint.py` into a
YAML→Jinja generator in ycli's own style; internally compile YAML→OpenAPI to plug in
`FastMCP.from_openapi` + Schemathesis later — these are the correct Python-native levers,
unlike Fern").

**Repo/environment hygiene:** repository itself was never touched — everything lived in the
session scratchpad. Left pending at session end: global npm package `fern-api` and the Docker
image `fernapi/fern-python-sdk` (offered for cleanup, not confirmed done in-transcript).

---

## 3. The POC ("23 YAML lines → 6 files, ~5.9× compression")

Source: lines 200–241 of `f8cba46e` (VALIDATE phase of cycle 1).

### The spec authored (verbatim), `.../scratchpad/poc/specs/tracker/priorities/resource.yaml`:
```yaml
# ONE small spec file -> generates models.py + client.py + cli.py + mcp.py + test_client.py
# for the tracker/priorities resource. Directory path (tracker/priorities) encodes domain+resource.
domain: tracker
resource: priorities
model:
  name: Priority
  list_type: PriorityList        # RootModel[list[Priority]]
  fields:
    - { name: key,     type: "str | None", default: "None" }
    - { name: display, type: "str | None", default: "None" }
operations:
  - verb: list
    http_method: get
    path: priorities
    returns: PriorityList
    pagination: none
    cli:  { command: list, help: "List all priorities." }
    mcp:
      expose: true
      name: priorities_list
      title: "List Tracker priorities"
      doc: "All available issue priorities in the organisation."
    test:
      fixture: '[{"key": "critical", "display": "Critical"}]'
      assert:  'out.root[0].key == "critical"'
```
This spec knowingly covers only **one operation** (`list`) of the `priorities` resource — it
is not a full-resource spec format proposal, just enough surface to prove the generation
mechanism end-to-end.

### The generator (verbatim, full file), `.../scratchpad/poc/generate.py`:
A ~100-line Python script using plain `str.format` templates (explicitly modeled on
`scripts/new_endpoint.py`'s existing templates and `docs/conventions/resources.md`'s rules,
NOT Jinja2 — the POC itself used simple string formatting even though the strategy write-up
recommends Jinja for the real generator). It defines five template strings (`MODELS`, `CLIENT`,
`CLI`, `MCP`, `TEST`) and a `render(spec: dict) -> dict[str, str]` function that fills them from
the parsed YAML, then `main()` writes `__init__.py` + the five files into
`out/<domain>/<resource>/`. Docstring: *"Proves feasibility of Strategy 1/4 (codegen) on a real
ycli resource (tracker/priorities)."* Full templates are reproduced in §1 of the earlier tool
dump; key structural notes preserved from the source:
- `CLIENT` template explicitly does **not** use `from __future__ import annotations` with a
  code comment explaining why: *"uplink reads annotations eagerly."*
- `CLI` template includes a `_group()` callback with comment: *"Group anchor — forces subcommand
  dispatch (no eager DI, so --help stays cred-free)."*
- `MCP` template wires `Depends({domain}_client)` and `annotations={{**RO, "title": ...}}`.
- `TEST` template hardcodes `BASE = "https://api.tracker.yandex.net/v3"` and uses
  `responses.add(responses.{METHOD}, f"{BASE}/{path}", json={fixture}, status=200)`.

### Run + validation steps (all with explicit evidence, per `verification-before-completion`):
1. First run failed: `yaml` not in the venv → re-ran via `uv run --with pyyaml` (line 223).
2. **Green result (line 230, verbatim):** "POC зелёный: **23 смысловые строки YAML → 97 LOC в 6
   файлах, все компилируются.**" (23 meaningful YAML lines → 97 LOC across 6 files, all
   compile — verified via `py_compile`.)
3. **Semantic validation, not just syntax (line 237):** the generated `PriorityList` model was
   imported at runtime and validated against the SAME fixture the real hand-written test uses
   (`root[0].key == "critical"`); JSON schema was correct.
4. **Dependency check:** `pyyaml>=6.0.3` was already in `pyproject.toml` (line 28) — no new
   dependency needed for the spec format itself.
5. **The headline compression number (verbatim):** "hand-written `priorities` = **136**
   непустых LOC в 6 файлах → spec-as-code = **23** смысловые строки YAML в **1** файле
   (**≈5.9×**, и 6 файлов → 1)." I.e. 136 non-blank LOC across 6 hand-written files compresses
   to 23 meaningful YAML lines in 1 authored file — a ~5.9× reduction in *authored* lines, and
   a 6-files→1-file reduction in *authored* file count (note: this is about files you *author*,
   not files that exist in the repo after generation — the 6 generated files still get
   committed under S1).

No other POCs were run in this session besides this one on `tracker/priorities`. The Fern spike
(§2) is a separate hands-on experiment, not a "POC" in the generator sense — it tests a
third-party tool, not ycli's own generator design.

---

## 4. All measurements recovered

### From the ORIGINAL session (`f8cba46e`, 2026-07-10) — `local-findings.md` (line 138) + `STRATEGIES.md` (line 241)
| Metric | Value | Source |
|---|---|---|
| src total | 223 Python files, 10,399 (~10.4k) LOC | line 54, local-findings.md |
| Resource layer (quartet × ~40 resources) | ~9,165 LOC = **~88% of src** | local-findings.md |
| client.py | 38 files / 2,351 LOC (~62/resource) | local-findings.md |
| cli.py | 39 files / 2,227 LOC (~57/resource) | local-findings.md |
| mcp.py | 40 files / 1,385 LOC (~35/resource) | local-findings.md |
| models.py | 37 files / 3,202 LOC (~87/resource, biggest chunk) | local-findings.md |
| tests | 9,418 LOC, 94 files following one `@responses.activate` pattern | local-findings.md |
| Shared engine (would REMAIN in a spec world) | base 33 + transport 143 + pagination 159 + models 40 + output 138 + mcp helpers 34 = **~547 LOC** | local-findings.md |
| Domain glue (tracker) | ~84 LOC | local-findings.md |
| Subagent variability analysis | **~85% of the resource layer, ~70–80% of tests, mechanically generatable** | STRATEGIES.md / line 246 chat answer |
| `priorities` ground truth | 91 LOC / 4 files, derivable from ~8 lines of spec data | line 121 |
| POC compression | 136 non-blank LOC (6 files) → 23 YAML lines (1 file) ≈ **5.9×**; 97 generated LOC across 6 files | line 237, 246 |

### From the LATER session (`a065`, 2026-07-12) — re-measurement feeding the roadmap
This is a **different, independent measurement** (numbers do not match the 2026-07-10 figures
1:1 — the codebase had grown between the two sessions, e.g. more resources added). Captured
directly in the roadmap file `docs/superpowers/specs/2026-07-12-improvement-roadmap.md` §1
(sourced from a subagent "Аудит техдолга: код и тесты", `a065` line 132 confirms the same
headline: *"количественное подтверждение кейса для кодогенерации (структурная дупликация
65–81% по слоям, ~89% src — пер-ресурсные файлы)"*):
| Layer | files | LOC | structural duplication |
|---|---|---|---|
| client.py | 54 | 3,757 | 75% |
| cli.py | 54 | 4,491 | 81% |
| mcp.py | 55 | 1,631 | 71% |
| models.py | 52 | 4,925 | 65% |
| tests | 213 | 13,415 | 79% |

Roadmap-stated summary figures: "~89% of `src/` is the mechanical per-resource quartet; a
generator could produce ~65–75% of src and ~75–80% of tests (31 of details 50 resources are
≤400-line pure get/list plumbing — near-100% generatable)." **Caveat: the exact per-resource
"31 of 50 ≤400 lines" breakdown was NOT found verbatim anywhere in the two mined transcripts
outside the roadmap file itself** — it appears to be a number computed/asserted directly in the
roadmap-writing turn (`a065` line 521, the `Write` of the roadmap file) rather than quoted from
an intermediate subagent report file that was independently inspected. Treat it as "stated in
the roadmap, provenance not independently traceable in the transcripts mined" rather than a
figure this digest can re-derive from a cited raw measurement.

---

## 5. Off-the-shelf tool findings (external-findings.md, line 182, + line 208 addendum)

All retrieved 2026-07-10 via context7/deepwiki/web by 4 parallel subagents, with the orchestrator
personally re-verifying the single most load-bearing fact (FastMCP.from_openapi signature) a
second time via context7 per the `researching-rigorously` skill's cross-validation rule.

| Tool | Verdict | Why |
|---|---|---|
| **botocore/boto3** (Apache-2.0, ~1.42/1.43) | Borrow the architecture, not the library | Runtime data-driven clients from JSON models (`service-2`/`paginators-1`/`waiters-2`/`endpoint-rule-set-1`); `Loader.load_service_model` + `ClientCreator.create_client` synthesize a client class lazily at creation. SDK-only (no CLI/tests). Models are pre-generated FROM Smithy. "Pure runtime-dynamic is awkward for 100% coverage + py.typed." |
| **Azure aaz + Knack** (MIT; aaz v4.6.0 2026-07-07, Knack 0.14.0 2026-05) | **Single most transferable idea** | aaz = spec (Swagger2/TypeSpec) → **command model (intermediate)** → **Jinja-render Python CLI command code**. Two-step, reviewable. CLI only; Azure-locked/unreusable. Knack offers nothing over ycli's Typer. |
| **Smithy** (Apache-2.0, CLI v1.72.0 2026-07-01) | Vocabulary reference only | Protocol-agnostic IDL; `smithy-python` is pre-alpha, async-only, restJson1-only, Java/Gradle toolchain, no CLI/tests — "wrong weight class." Borrow modeling discipline (shapes/operations/traits), not the tool. |
| **FastMCP 3.4.3** (PrefectHQ/fastmcp; context7 `/prefecthq/fastmcp`) | **Strongest lever, but runtime-only** | `FastMCP.from_openapi(openapi_spec: dict, client: httpx.AsyncClient, route_maps=[...], mcp_names=..., validate_output=True)`; `RouteMap`/`MCPType` now live in `fastmcp.server.providers.openapi`. Default since v2.8: everything→TOOL. Read-only filter pattern confirmed: `route_maps=[RouteMap(methods=["GET"], pattern=r".*", mcp_type=TOOL), RouteMap(mcp_type=EXCLUDE)]`. **Caveat: it's a runtime HTTP proxy, no emitted .py** — direct tension with ARCH-2/3 ("HTTP only in client.py") and the 100% gate. New default parser (v2.14+) had RouteMap bugs (#1941, #2153) — "TEST route maps against the real spec." Independently re-confirmed via context7 primary docs (`docs/integrations/openapi.mdx`) at line 223. |
| **Schemathesis 4.22.3** (2026-07-02, 4.0 rewrite) | Complement, not replacement | Loaders `schemathesis.openapi.from_url/from_path/from_dict/from_asgi/from_wsgi`; pytest `@schema.parametrize()` or `schemathesis.pytest.from_fixture`; auto-checks (schema conformance, undocumented status, headers, 5xx, negative_data_rejection, auth bypass); stateful `as_state_machine()` via OpenAPI links. Targets a live/ASGI app, not the offline `responses` layer ycli uses. Dredd = legacy, skip. |
| **OpenAPI Generator** (Java) | Partial component | `python` generator now emits pydantic v2; no CLI; empty test stubs. |
| **datamodel-code-generator** | ✅ **Recommended in-repo component** | pydantic v2 models from OpenAPI/JSON-Schema — directly reusable for the models slice (the biggest LOC chunk, 3.2k). |
| **openapi-python-client** | Rejected — stack mismatch | httpx + attrs (ycli uses requests+uplink, pydantic). |
| **Fern** (Apache-2.0, `fern generate --local` free) | Spiked hands-on, rejected — see §2 | Only external engine offering Python SDK+CLI+MCP at all (on paper) — CLI/MCP turned out to be a gated Rust binary, not Python. |
| **TypeSpec 1.13.0** (MIT, GA core) | Authoring-layer candidate only | Best modular "one file per resource" authoring; emits stable OpenAPI 3. Python emitter is preview and non-pydantic — "use as authoring → OpenAPI → own generator," not as the generator itself. |
| **⚠️ Stainless** | **Excluded — sunsetting** | "Joined Anthropic 2026-05-18" and is closing its hosted SDK generator. Flagged explicitly as "exactly what the guardrail against train-data warned about" — a fact any training-data-only answer would have missed. |
| **Speakeasy** | Rejected — wrong stack shape | Python SDK OK but CLI=Go, MCP=TypeScript, paid per language. |
| **Kiota** | Rejected | Non-pydantic Python output, .NET CLI. |
| **restish / openapi-cli-generator** | Rejected | Go, no Python codegen. |
| **smithy-python** | Rejected | Pre-alpha, async-only, Java toolchain, no CLI/tests. |
| **Dynamic Typer/Click** (idiom, not a tool) | Confirmed working pattern for S3 | `app.command(name=...)(factory(spec))` in a loop; build runtime `inspect.Signature` with `Annotated[T, typer.Option(...)]`; set `__signature__`, `__annotations__`, `__doc__`. Pitfalls: closure-over-loop-var (bind via default/partial/factory); Typer resolves annotations via `get_type_hints`; dynamic commands are invisible to mypy/pyright. |
| **`pydantic.create_model` (v2)** (idiom) | Confirmed stable | `create_model('M', foo=(str, ...), bar=(int, 123), baz=(str, Field(...)), __base__=..., __validators__=...)`. Feeds both validation and `model_json_schema()` (→ FastMCP tool schema) and Typer option derivation — "ideal single-source-of-truth object," though Typer can't take a whole model as one param (must map fields to individual Options). |
| **Directory-as-URL-template** (`issues/__id__/get.yaml`) | Validated pattern | Precedented by Next.js dynamic routes (`[id]`), Redocly OpenAPI `split`/`bundle`, Kubernetes/Terraform declarative directories. Recommendation: `__id__` token beats `[id]` (shell-safe). Rules distilled: ban catch-all segments, "literal beats placeholder," file deletion is authoritative (deleting the file removes the resource). |

**Convergence insight (verbatim, external-findings.md):** "one OpenAPI doc (compiled from small
YAML) + one pydantic layer → FastMCP consumes the OpenAPI dict; Schemathesis consumes the same
OpenAPI; Typer generated from pydantic models. The fork remains runtime-interpret (FastMCP
proxy, least code, no source/coverage) vs codegen (emit source, keep ARCH invariants + coverage,
maintain a generator)." This is the intellectual seed of S4.

---

## 6. Worked examples of specific operations in a proposed spec format

The ONLY spec-format example actually authored and run in this research is the POC spec in §3
(`tracker/priorities` `list` operation, GET, no pagination). **No other operation types
(create/delete/upload/paginated/bulk/action) were rendered as concrete YAML in either
transcript.** The `local-findings.md` "Candidate spec knobs" section (line 138, quoted in full
below) sketches the intended schema shape for a broader endpoint but was never instantiated for
non-GET verbs:

```
Per endpoint file (e.g. tracker/issues/__id__/get.yaml):
  domain, resource, http_method, path (+ path_params), query_params, body_schema,
  response_model (ref), list_item_model, pagination: {strategy, page_size?, id_field?, next_field?},
  output_format_default, mcp: {expose: bool, verb (read-verb allowlist), title},
  auth_header (X-Org-ID tracker vs X-Org-Id wiki/forms), api_host (tracker vs api.forms.yandex.net),
  cli: {command_name, args, options}, test_fixture (sample json) OR $ref to fixtures file.
Models spec: field name -> {type, optional, alias, default, nested_model_ref}.
```
(Note: this snippet's claim about differing `X-Org-ID`/`X-Org-Id` casing per service was later
retracted by the assistant after user pushback — RFC 9110 header names are case-insensitive; see
§9.)

**Bespoke/escape-hatch inventory (verbatim, local-findings.md)** — this is the closest the
session got to "diverse operations," as a list of what resists pure declaration rather than as
rendered YAML:
> TQL search (issues_search/count), binary upload/download (attachments), YFM body (wiki
> pages), discriminated MCP unions (status), per-service header casing, cursor drain edge
> cases. => need a named-strategy enum + a Python escape-hatch hook per endpoint
> (`handler: module:fn`).

So: **paginated** is covered only as a named-strategy reference (`pagination: relative_cursor,
page_size: 50` — mentioned as an example pattern at line 97, not written out as a full spec);
**upload/bulk/action/create/delete** are all named only as members of the "bespoke residue"
list needing an escape hatch, never worked through as concrete YAML. This is a real gap in the
prior research, not something this digest is omitting.

---

## 7. Final recommendation, open questions, owner decisions

### Recommendation (phased, verbatim from STRATEGIES.md / line 246)
1. **Spike Fern `--local`** (~1 day): confirm how much SDK+CLI+MCP is truly free+local and
   whether the output shape is acceptable. *(Done in cycle 2 — rejected, see §2.)*
2. Otherwise **build S1 → evolve toward S4**: grow `new_endpoint.py` into a spec-driven Jinja
   generator; adopt directory-as-URL-template; reuse `datamodel-code-generator`; add a
   pagination-enum + escape-hatch hooks; generate tests + snapshots. Compile YAML→OpenAPI
   internally so `FastMCP.from_openapi` + Schemathesis can be bolted on later.
3. Migrate 1 domain (tracker) first, keep the 100% suite green, then wiki/forms.
4. Keep ARCH invariants; update `ARCHITECTURE.md` + its checks in the same PR if the file
   layout changes.

### Risks / what breaks / mitigations (verbatim)
- **100% coverage is the biggest cost**: "generator MUST emit tests, else the gate blocks
  every change."
- py.typed + uplink's eager annotations: generate ahead-of-time, real `.py`. Don't go runtime.
- ARCH-1/2/3 + snapshots + import-linter assume files: codegen satisfies them for free; runtime
  requires rewriting them.
- **Solo-maintainer trap** (explicitly named): "a bespoke IR + generator is 'a second product.'
  Mitigate via S1's minimalism, or lean on Fern/OpenAPI toolchain (S2/S4) to keep owned tooling
  thin." (Fern was subsequently spiked and rejected, narrowing this mitigation to "S1's
  minimalism" alone.)

### Open decisions explicitly left to the owner (verbatim, never resolved in-transcript)
- Appetite for rip-and-replace of the hand-crafted uplink/Typer/FastMCP stack (S1/S4 keep it;
  S2 replaces it).
- Bespoke YAML IR vs standard IR (OpenAPI-split / TypeSpec).
- Tolerance for a Node/compile step (TypeSpec) or a Java toolchain (OpenAPI Generator).
- Whether "minimal Python" means fewer authored lines (codegen) or literally fewer repo files
  (runtime/build-time).

**No decision to actually implement S1 was recorded in either transcript.** The `AskUserQuestion`
at line 247 offered 4 direction options (S1→S4 / spike Fern first / S2 / not yet) and 3 format
options (commit report / visual Artifact / chat-only); the user picked "spike Fern first" +
"visual Artifact" (line 250/252) — a research-sequencing choice, not a build decision. After the
Fern spike concluded "S1 → S4" as the reconfirmed path (line 390), the session ended without an
explicit "go build it" instruction; the published Artifact and `STRATEGIES.md` were left as the
durable outputs. The follow-up work was picked up much later by the unrelated `a065` "improve
ycli" session, which folded the recommendation into roadmap §1 without adding new strategy
design — it explicitly deferred: *"Прошлая сессия: вердикт «codegen да, runtime нет», стратегия
S1→S4, Fern отвергнут спайком; дупликация подтверждена независимым замером" → "Войдёт в
итоговый roadmap с моей рекомендацией (не реализуем в этой сессии)"* (a065 line 370 — "will go
into the final roadmap as my recommendation; not implemented in this session").

### Artifacts produced
- Published (private-by-default) Claude Artifact: **"🧬 ycli → Specification-as-Code"** —
  `https://claude.ai/code/artifact/2fc7df20-8c07-418c-8d59-37c5df044266` (updated in place after
  the Fern spike with a new "Fern spike · hands-on" section).
- Nothing was committed to the ycli repo itself from this research (explicit, by design —
  the "commit report" AskUserQuestion option was NOT chosen).
- Scratchpad files (`STRATEGIES.md`, `local-findings.md`, `external-findings.md`,
  `poc/generate.py`, `poc/specs/...`, `fern-spike/openapi.yml`, `spec-as-code.html`) were all
  under `/tmp/claude-1000/-home-sava-dev-dev-ycli/f8cba46e-.../scratchpad/` — **this directory
  no longer exists on disk** (session scratchpads appear to be garbage-collected); every piece
  of content quoted in this digest was recovered from the JSONL transcript's `Write` tool_use
  `input.content` fields, not from the files themselves.

---

## 8. What the roadmap §1 distillation left out (nuances, dead-ends, caveats)

Comparing `docs/superpowers/specs/2026-07-12-improvement-roadmap.md` §1 against the full
transcript, the roadmap is a faithful but heavily compressed pointer. Specifically left out:

1. **The two-meanings reframing** ("fewer authored lines" vs "fewer repo files") — the actual
   *reasoning* for why S3/runtime is rejected and S1/codegen is recommended. The roadmap states
   the conclusion ("Do NOT adopt runtime metaprogramming") but not the argument (py.typed/
   boto3-stubs precedent, coverage-gate semantics, ARCH-file-coupling) that produced it.
2. **S5 and S6** (the declarative-Python-descriptor fallback and the build-time-non-committed
   variant) are dropped entirely — the roadmap only mentions S1→S4 vs "S2/Fern," never
   mentioning S3, S5, or S6 by name or content.
3. **The full comparison matrix** (py.typed / 100%-cov / ARCH-kept / owner-tooling / effort /
   risk per strategy) is not reproduced — the roadmap has no matrix at all.
4. **The Fern spike's specific disqualifying facts** (httpx vs requests+uplink,
   UniversalBaseModel vs APIModel, raw/wrapped client split, 4150 LOC/2 endpoints, the
   `fern-cli` Rust-binary/gated finding, the FERN_TOKEN docs-vs-empirics contradiction) are
   compressed to one clause: "Fern was spiked hands-on and rejected (SDK-only under free/local,
   foreign model identity, inverted ownership)." The volume/identity comparison table and the
   exact LOC number are omitted.
5. **The POC's actual authored spec and generator code** (§3 above) are not referenced at all —
   only the headline "23 authored YAML lines → 6 valid files (~5.9× compression)" survives.
6. **The bespoke/escape-hatch inventory** (TQL search, binary upload/download, YFM body,
   discriminated MCP unions, cursor drain edge cases → named-strategy enum + Python escape-hatch
   hook) is entirely absent from the roadmap — this is arguably the most important omission for
   anyone designing the actual spec schema, since it's the list of things that WON'T fit cleanly
   into declarative YAML.
7. **The candidate spec-knob schema sketch** (domain/resource/http_method/path/query_params/
   body_schema/response_model/pagination/mcp/cli/test_fixture) is not in the roadmap at all.
8. **The X-Org-Id casing false-positive and its retraction** (§9 below) — a good example of the
   session correcting itself under user pushback — is unrelated to spec-as-code substance but
   happened inside this same session and is worth knowing about for calibrating how much to
   trust unreviewed "drift" claims from that session.
9. **The provenance gap on "31 of 50 resources ≤400 lines"** (§4 above) — the roadmap presents
   this as a clean number, but it could not be traced to an intermediate, independently-quotable
   subagent report in the mined transcripts; it is asserted directly in the roadmap-authoring
   turn.
10. **The measurement discrepancy** between the two sessions (88% src / 9.2k of 10.4k LOC,
    2026-07-10 vs 89% src / duplication 65–81% by layer, 2026-07-12) is not flagged in the
    roadmap as being two independent measurements at two points in time on a growing codebase —
    it's presented as if it were one continuous fact.
11. **datamodel-code-generator's specific role** (pydantic v2 models from OpenAPI/JSON-Schema,
    slotted specifically into the *models.py* generation slice, "the biggest LOC chunk") is
    mentioned by name in the roadmap but without the reasoning for why it's the one reusable
    piece (vs. openapi-python-client's httpx/attrs mismatch, OpenAPI Generator's no-CLI/
    empty-test-stub gaps).
12. **"S1 → S4" is explicitly an evolution, not two alternatives** — the roadmap's phasing
    section actually preserves this correctly (step 4: "Evolve the bespoke YAML toward an
    OpenAPI-compatible IR (S4) only when a second consumer appears"), so this one nuance
    *is* retained, just worth confirming.

---

## 9. Aside: the X-Org-Id casing claim and its retraction (not spec-as-code substance, but same session)

At line 246/280 the assistant flagged, as a drive-by finding, that the code sends one canonical
`X-Org-Id` header for all three services (`transport.py:130`) while CLAUDE.md/ARCHITECTURE.md
allegedly claimed differing casing per service (Tracker `X-Org-ID` vs Wiki/Forms `X-Org-Id`).
At line 288 the user pushed back: *"Casing же не важен по стандарту, там хоть lowercase хоть
uppercase но для вебсервера одно и то же"* (casing doesn't matter per the HTTP standard). At
line 291 the assistant retracted: *"Имена HTTP-заголовков регистронезависимы (RFC 9110 §5.1)...
Я переоценил находку: это не баг и функционально ничего не значит... Убираю это из списка
находок."* This is the origin of the "X-Org-Id casing" note already present in this repo's own
CLAUDE.md ("RFC 9110... so there is no per-service casing to track") — i.e. that convention line
traces directly back to this correction inside the spec-as-code research session.
