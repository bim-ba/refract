# refract — A.2 `priorities` (body registry) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Extend refract's proven emitters (Milestone A shipped `tracker/me` byte-identical) to render ycli's real `tracker/priorities` **body-carrying** surfaces byte-identically — proving the **body registry (TypedModel writes)**, rich models, path/query params, PATCH, and a multi-op MCP server with a WRITE safety mix.

**Architecture:** Same four layers (spec → IR → emitters → committed source + `--check`). A.2 *extends* the existing IR/loader/emitters; it does not restructure them. Every extension is guarded by a byte-equality test against a real-ycli golden.

**Tech Stack:** unchanged (pydantic + pyyaml + ruff; pytest/ruff/ty).

## Global Constraints

- **Byte-identity oracle:** each extended `emit(ir)` must equal its `priorities` golden byte-for-byte, AND the existing `me` byte-equality tests must stay green (no regression).
- **Scope = 4 per-resource surfaces:** `models.py`, `client.py`, `mcp.py`, `__init__.py` for `priorities`. **`cli.py` and the test files are OUT of A.2** (documented forks: bespoke CLI option→body assembly; ycli's test files are entangled across priorities+issuetypes+linktypes). Do not attempt them.
- **YAGNI-for-coverage stays honest:** implement only the code paths `priorities` (together with `me`) exercises; `--cov-fail-under=100` (line) must hold with no `# pragma: no cover`. When a Milestone-A deferral is now exercised by `priorities` (e.g. the mcp unguarded-tool path that A shipped as `raise NotImplementedError`), replace the deferral with the real implementation — don't leave dead arms.
- **Self-contained:** refract never imports ycli; goldens are opaque text.
- **Full self-documenting names**; ruff config unchanged (byte-identity depends on it).
- **`me` must keep rendering byte-identically** throughout — it's the regression anchor.

## Reference (read as needed)
- Existing refract emitters (the base you extend): `refract/emitters/python/{_common,models,client,cli,mcp,tests}.py`, `refract/{ir/model.py, loader.py, generate.py, format.py}`.
- Prototype (proven shapes for body-split/params — adapt to v2 IR): `/tmp/claude-1000/-home-sava-dev-dev-ycli/80802223-5853-4c72-8da8-868e6f65a5f8/scratchpad/sac-prototype/apigen/emitters/python/client.py` (has `_bodyless_write`; the TypedModel split is new — model it on the golden).
- **Golden byte-targets** (real ycli — copy into `examples/ycli-tracker/golden/tracker/priorities/`):
  - `/home/sava/dev/dev/ycli/src/ycli/yandex/tracker/priorities/{__init__,models,client,mcp}.py`

---

## The priorities golden shapes (what the emitters must newly produce)

**`models.py`** (5 models): `Priority` (object, 3 plain `x: str | None = None` — already supported); `PriorityList` = `class PriorityList(RootModel[list[Priority]]):` **with ONLY a docstring, NO `root:` field** (differs from the me-era prototype which added `root: list = []` — the A-era models emitter must be checked/fixed for this); `LocalizedName` (object, 2 optional `Field(default=None, description=…)` fields — **new: `Field(description=)` rendering**); `PriorityCreate` (object with a **required** `key: str = Field(description=…)`, a **model-ref required** `name: LocalizedName = Field(description=…)`, and two optional `Field(default=None, description=…)` — the `order` one wraps across lines, which **ruff** handles); `PriorityUpdate` (optional model-ref `name: LocalizedName | None = Field(…)` + optional `description`).

**`client.py`**: `list()` (simple GET → `PriorityList`, multi-line `Example:` docstring — already supported); the **TypedModel body split** for `create`: internal `@uplink.returns.json()` / `@uplink.json` / `@uplink.post("priorities/")` `def _create(self, body: uplink.Body) -> Priority:  # ty: ignore[empty-body]` + public `def create(self, body: PriorityCreate) -> Priority:` whose body is `return self._create(body=body.model_dump(by_alias=True, exclude_none=True))`; and for `edit`: `@uplink.patch("priorities/{priority_id}")` internal `_edit(self, priority_id: uplink.Path, body: uplink.Body, version: uplink.Query("version") = None,  # ty: ignore[invalid-type-form]) -> Priority:` + public `edit(self, priority_id: str, body: PriorityUpdate, *, version: int | None = None) -> Priority:` doing `return self._edit(priority_id=priority_id, body=body.model_dump(by_alias=True, exclude_none=True), version=version)`. (Read the golden for exact docstrings/wrapping.)

**`mcp.py`**: `mcp = FastMCP("tracker-priorities")`; imports `RO, TAGS, WRITE, WRITE_IDEMPOTENT, WRITE_TAGS, tracker_client` (subset actually used) + the models; `priorities_list` (RO, `tags=TAGS`, **no require_found** — `return client.priorities.list()`); `priorities_create` (`{**WRITE, "title": …}`, `tags=WRITE_TAGS`, signature `def create(body: PriorityCreate, client: TrackerClient = Depends(tracker_client)) -> Priority:`, `return client.priorities.create(body)`); `priorities_edit` (`{**WRITE_IDEMPOTENT, …}`, `tags=WRITE_TAGS`, `def edit(priority_id: str, body: PriorityUpdate, version: int | None = None, client: TrackerClient = Depends(tracker_client)) -> Priority:`, `return client.priorities.edit(priority_id, body, version=version)`).

**`__init__.py`**: `"""Tracker /priorities resource package."""` (= `res.documentation`).

---

### Task 1: Extend IR + loader for bodies, params, and model-refs

**Files:**
- Modify: `refract/ir/model.py`, `refract/loader.py`
- Create: `examples/ycli-tracker/tracker/priorities/resource.yaml`
- Test: `tests/test_loader_priorities.py`

**Interfaces (add to the IR):**
- `Body(mode: str, model: str, dump: str)` — `mode="TypedModel"`; `dump` = the model_dump kwargs source text, e.g. `"by_alias=True, exclude_none=True"`.
- `Operation` gains `body: Body | None = None` (the A-era IR dropped it per YAGNI — add it back now, exercised).
- `Operation.params` already exists (`tuple[Param, ...]`) but the loader's `OperationSpec` dropped `params` in Task 3 — re-add `params` to the loader.
- Loader `_lower_type` gains `ref<Model>` → the model name verbatim (e.g. `ref<LocalizedName>` → `"LocalizedName"`), and model-name bare types (a field `type: LocalizedName` may be authored directly — decide one form and use it consistently in the spec).

- [ ] **Step 1: Author `examples/ycli-tracker/tracker/priorities/resource.yaml`** — a complete v2 spec carrying every datum the 4 goldens encode: `documentation: "Tracker /priorities resource package."`, `module_docs` (models/client/mcp + `client_class: "Declarative HTTP for ``/priorities`` (list + create + edit)."` + `mcp_server: "tracker-priorities"`), the 5 models (with per-field `optional`/`default`/`description`/required + model-ref types + the `RootModel` list + the multi-line `Example:` docstrings verbatim), and 3 operations (`list` GET; `create` POST `priorities/` with `body: {strategy: TypedModel, model: PriorityCreate, dump: "by_alias=True, exclude_none=True"}` and `mcp.safety: WRITE`; `edit` PATCH `priorities/{priority_id}` with a `version` query param, `body` → `PriorityUpdate`, `mcp.safety: WRITE_IDEMPOTENT`). Read the goldens for the exact docstrings.
- [ ] **Step 2: Write the failing loader test** `tests/test_loader_priorities.py` — assert the loaded IR: 5 models (Priority object, PriorityList root_list, LocalizedName/PriorityCreate/PriorityUpdate objects); `PriorityCreate.key` is required (`optional=False`, `default=None`→ no default) with a `description`; `name` field type is `"LocalizedName"`; `create` op has `body.mode=="TypedModel"`, `body.model=="PriorityCreate"`, `body.dump=="by_alias=True, exclude_none=True"`; `edit` op has a `version` query `Param`; mcp safeties are `WRITE`/`WRITE_IDEMPOTENT`.
- [ ] **Step 3: Run — fails.** `uv run pytest tests/test_loader_priorities.py -v`.
- [ ] **Step 4: Implement the IR + loader extensions.** Add `Body` to `ir/model.py` + `Operation.body`; re-add `params` and add `body`/`ref<>` support to the loader. Keep all `me` loader tests green (the additions are optional fields, defaulting to the me behavior).
- [ ] **Step 5: Run — passes; full suite green** (`uv run pytest`, 100%); `ruff format --check`/`ruff check`/`ty check` clean.
- [ ] **Step 6: Commit.** `git commit -am "feat: IR+loader — body registry (TypedModel), params, model-ref types"`

---

### Task 2: Extend the models emitter (Field metadata, model-refs, RootModel-no-root)

**Files:** Modify `refract/emitters/python/models.py`; copy golden `examples/ycli-tracker/golden/tracker/priorities/models.py`; Test `tests/test_emit_priorities_models.py`.

**Acceptance:** `models.emit(priorities) == golden priorities/models.py` byte-for-byte AND `models.emit(me) == golden me/models.py` still holds.

- [ ] **Step 1: Copy the golden** from real ycli.
- [ ] **Step 2: Write the failing byte-equality test** (priorities) + confirm the me models test still exists.
- [ ] **Step 3: Run — fails.** `uv run pytest tests/test_emit_priorities_models.py -v`.
- [ ] **Step 4: Implement.** Extend `_render_field` for `Field(description=…)` on **required** fields (no `default=`, just `description=`) and optional fields (`default=None, description=…`); render model-ref field types verbatim; **fix the `root_list` branch to emit NO `root:` field** (just `class X(RootModel[list[Item]]):` + docstring) — verify this doesn't break any me/prior test (me has no root_list; check the `comments`-style prototype assumption isn't relied on elsewhere). Extend `_imports` to pull `Field` when any field uses it. Let ruff wrap the long `order` `Field(...)` call.
- [ ] **Step 5: Run — both byte-identical; full suite green.** Diff-debug against golden on mismatch. ruff/ty clean.
- [ ] **Step 6: Commit.** `git commit -am "feat: models emitter — Field metadata, model-ref fields, RootModel-no-root"`

---

### Task 3: Extend the client emitter (TypedModel body split, path/query params, PATCH)

**Files:** Modify `refract/emitters/python/client.py` (+ `_common` if needed); copy golden `priorities/client.py`; Test `tests/test_emit_priorities_client.py`.

**Acceptance:** `client.emit(priorities) == golden` byte-for-byte AND `client.emit(me)` still holds.

- [ ] **Step 1: Copy the golden.**
- [ ] **Step 2: Write the failing test** (+ me client test stays).
- [ ] **Step 3: Run — fails.**
- [ ] **Step 4: Implement the TypedModel body split.** For an op with `body.mode=="TypedModel"`: emit the internal `_<name>` (`@uplink.returns.json()` + `@uplink.json` + `@uplink.<method>("<path>")`, params rendered incl. `uplink.Path`/`uplink.Query(alias)=default` with the right `# ty: ignore[...]`, `body: uplink.Body`, return type, `# ty: ignore[empty-body]`) + the public `<name>` (typed signature with `body: <Body.model>` and `*, version: int | None = None` for the extra query, docstring, `return self._<name>(<path/query kwargs>, body=body.model_dump(<Body.dump>))`). Render the import block for the write-body models + `PriorityList`. Reuse the me `_simple` path for `list`. Reference the prototype's `_bodyless_write` for the internal/public split idiom; the TypedModel variant is new — match the golden exactly.
- [ ] **Step 5: Run — both byte-identical; full suite green.** ruff/ty clean.
- [ ] **Step 6: Commit.** `git commit -am "feat: client emitter — TypedModel body split, path/query params, PATCH"`

---

### Task 4: Extend the mcp emitter (multi-op, WRITE safety, typed-body param, unguarded path)

**Files:** Modify `refract/emitters/python/mcp.py`; copy golden `priorities/mcp.py`; Test `tests/test_emit_priorities_mcp.py`.

**Acceptance:** `mcp.emit(priorities) == golden` byte-for-byte AND `mcp.emit(me)` still holds.

- [ ] **Step 1: Copy the golden.**
- [ ] **Step 2: Write the failing test** (+ me mcp test stays).
- [ ] **Step 3: Run — fails.**
- [ ] **Step 4: Implement.** Loop over ops (already multi-op-capable — verify). Map `op.mcp.safety` → the imported annotation symbol (`RO`/`WRITE`/`WRITE_IDEMPOTENT`) and the tags (`TAGS` for RO, `WRITE_TAGS` for writes); import exactly the symbols used, sorted. **Pay down F3:** priorities tools have NO `require_found`, so replace the A-era `raise NotImplementedError` deferral with the real unguarded path — `return client.<resource>.<op>(<args>)` directly (and emit the `require_found` import only when some op needs it). For a write op, add the typed `body: <model>` (and `priority_id: str`, `version: int | None = None`) params before the `client` DI param, in the golden's order. Confirm `me`'s guarded tool still renders identically (the guarded arm is unchanged).
- [ ] **Step 5: Run — both byte-identical; full suite green.** ruff/ty clean. (Coverage: both the guarded `me` arm and the unguarded `priorities` arm are now exercised → the `require_found` conditional is fully covered honestly.)
- [ ] **Step 6: Commit.** `git commit -am "feat: mcp emitter — multi-op WRITE safety, typed-body params, unguarded tools (pays down F3)"`

---

### Task 5: Wire priorities into `generate` + `--check` (4 surfaces)

**Files:** Modify `refract/generate.py` (render only the 4 surfaces for a resource lacking cli/tests — OR keep 6 and mark cli/tests absent); copy golden `priorities/__init__.py`; generate `examples/ycli-tracker/out/tracker/priorities/**`; Test `tests/test_generate_priorities.py`.

**Design note:** `render_resource` currently returns 6 entries. `priorities` in A.2 has no generated `cli.py`/tests. Make `render_resource` emit the surfaces the resource supports: always `__init__/models/client/mcp`; include `cli`/tests only when the spec/scope calls for them. For A.2, gate `cli`/tests off for `priorities` (e.g. a resource-level `surfaces:` list, or detect `cli` facets/`tests` presence). Keep `me`'s 6-file output unchanged.

- [ ] **Step 1: Copy the `__init__` golden.**
- [ ] **Step 2: Write the failing test** `tests/test_generate_priorities.py` — assert `render_resource(priorities)` emits `__init__/models/client/mcp` byte-equal to the priorities goldens, and does NOT emit a priorities `cli.py`/test.
- [ ] **Step 3: Run — fails.**
- [ ] **Step 4: Implement** the surface-gating in `render_resource`/`plan`; keep me's 6 files.
- [ ] **Step 5: Regenerate + verify.** `uv run refract generate --write`; `diff -r examples/ycli-tracker/out examples/ycli-tracker/golden` for the priorities subtree (the 4 files) must be empty; `uv run refract generate --check` exit 0.
- [ ] **Step 6: Full suite + gates.** `uv run pytest` (100%), `ruff format --check`, `ruff check`, `ty check`, `refract generate --check`.
- [ ] **Step 7: Commit.** `git commit -am "feat: render+check priorities (models/client/mcp/__init__ byte-identical end-to-end)"`

---

## Self-Review

**Spec coverage:** the body registry (T1 IR/loader + T3 client), rich models (T2), multi-op WRITE mcp + F3 pay-down (T4), and end-to-end `--check` (T5) each map to a task. `cli.py` + tests are explicitly out (documented forks) — not gaps.

**Placeholder scan:** emitter internals are pinned by committed goldens + byte-equality tests (complete specs, not placeholders). The one open implementation choice — surface-gating in `render_resource` (T5) — is stated with its acceptance test.

**Type consistency:** new IR names (`Body(mode, model, dump)`, `Operation.body`) are fixed in T1 and consumed verbatim in T3. The `me` regression anchor is asserted in every emitter task.

**Acceptance for A.2:** `uv run pytest` green at 100%; `refract generate --check` exit 0; `me` (6 files) AND `priorities` (4 files) both byte-identical to real ycli; ruff/ty clean. Proves the generator scales from a trivial read-only resource to a body-carrying multi-op CRUD resource.
