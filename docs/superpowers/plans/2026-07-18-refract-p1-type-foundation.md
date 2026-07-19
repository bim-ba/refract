# refract P1 (type-foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay the type-system foundation every later axis depends on - discriminated + undiscriminated unions (Variant 2: ONE structured `oneof:` node for both kinds), cross-file / shared model refs, scalar formats (int64-as-string, RFC-2822 dates) - and fold in the P0-deferred M1 emitter finding (recursive body-model ref-walk) that only detonates on the shapes P1 introduces. It opens by paying the A3 debt (splitting the 1091-line `resolve.py` into a per-surface package) before P1 grows the file. (M2, whole-signature CLI option dedup, was already closed in P0 as finding I1 - commit `43203a5` - so it is NOT a P1 task.) Recursion (self-referential unions) is explicitly deferred per Q3.

**Architecture:** Pure additions to the redesign's neutral-IR pipeline, all four "the IR grows" shapes from the milestone spec section 5. A new `NeutralType` variant (`UnionType`, later `LiteralType`) + a `ScalarType.format` slot flow spec-frontend (`nodes`/`loader`) -> frozen IR (`ir/types.py`) -> `PythonTypeMapper._base` lowering -> `_model_field` assembly. A new shared spec node (`SharedModelsSpec`) + a new cross-file resolution path widen `Resource.model()` and add a THIRD emission surface (a `DomainEmitter`-shaped shared-models tier, analogous to `root_client`). No core redesign; the read/write split, the surface registry, and the 5 injected strategies are untouched.

**Tech Stack:** Python 3.12/3.13, pydantic v2 (frozen IR, discriminated unions), Jinja2 templates, Typer CLI, httpx runtime, pytest + responses, ruff + ty (pinned `==0.0.59`), uv.

## Global Constraints

Copied from the P1 design-input (`artifacts/18-p1-type-foundation-input.md`) and the project's post-P0 gate. Every task's requirements implicitly include this section.

- Coverage gate is `--cov-fail-under=100`, LINE AND BRANCH (`branch = true` is now enforced in `[tool.coverage.run]`); NO `# pragma: no cover`. A fail-loud guard that is genuinely reachable gets a unit test that triggers it; a genuinely unreachable one is refactored away, not pragma'd. `assert_never` / `case _:` fallthrough arms are already excluded via `exclude_also` - a NEW reachable match arm needs a test that exercises it.
- `uv run ruff format --check .` + `uv run ruff check .` + `uv run ty check` MUST be clean (ty pinned `==0.0.59`). Mechanical fixes go through `ruff --fix` / `ruff format`, never hand-applied.
- `uv run refract generate --check` MUST exit 0 (the committed `examples/ycli-tracker/out/` L1 snapshot is drift-free). When a task changes emitted output, regenerate with `uv run refract generate --write` IN THE SAME TASK and commit the `out/` delta.
- Behavioral tests are opt-in (`@pytest.mark.behavioral`, excluded by default via `-m 'not behavioral'`); run them explicitly with `uv run pytest -m behavioral`.
- Emitted code is ENGLISH-only: no Russian text, and no Cyrillic section-ref abbreviations in generated output or source comments.
- Fail loud: reject at the cause with `raise` (never `assert` for control flow; `-O` strips asserts). Free-text literals in emitted code go through `py_str` (moves to `resolve/_common.py` in Task 1's surface split).
- IR is frozen pydantic; illegal states unrepresentable (discriminated unions). Do not widen a type without a spec-shaped reason.
- Conventional Commits; end each commit message with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- File artifacts are ASCII (`->` not arrows, `-` not em-dash).

**Branch note (execution-time):** Executing on `feat/p1-type-foundation`, cut off the merged `origin/main` (P0's PR #2 `feat/axis-registries` HAS merged; the P0 gate is green on `main`). All `file:line` citations below were verified against the post-P0 tree; NOTE that Task 1 (the `resolve.py` surface split) relocates most `resolve.py:NNN` citations in Tasks 5/8/10/11 into the new `resolve/<surface>.py` submodules - those tasks cite the target module by name rather than a post-split line number.

## Adopted fork defaults (each OWNER-OVERRIDABLE)

These are the design-input's recommendations, adopted as the plan's defaults. Each is a genuine owner-level call, not a mechanical detail; the alternative is stated so the owner can override before execution.

| # | Fork | Adopted default | Alternative (override) | Where |
|---|---|---|---|---|
| **A** | Union spec syntax | **Variant 2 (owner-SELECTED 2026-07-18):** a SINGLE structured `oneof: {variants: {label: type-expr}, discriminator?}` node for BOTH discriminated and undiscriminated unions; NO compact `oneOf<A\|B>` string. Discriminated (`discriminator` set): every variant is a `ref<Model>` and the loader synthesizes each variant's `Literal["label"]` field. Undiscriminated (`discriminator` omitted): variants are arbitrary type-exprs (scalar/list/ref); the map labels are documentation only, with no wire meaning | Variant 1 (split: compact `oneOf<A\|B>` string for undiscriminated + structured `oneof:` for discriminated) | Task 4 |
| **D** | Shared/local model-name collision | FAIL LOUD (`SpecError`) when the same name is defined in BOTH a resource's `models:` and the shared `_models.yaml`; local-first lookup as the non-colliding default | "shared wins" (silent shadow), or "local wins" silently | Task 9 |
| **E** | Shared-models emission tier | A separate per-DOMAIN emission surface (a `DomainEmitter`-shaped step, analogous to `root_client`), emitting shared models ONCE into `<domain>/shared_models.py`; consuming resources import from it | Merge shared models into every consuming resource's `res.models` (copies `ObjectMeta` into every `models.py` - the k8s failure mode); or a NEW cross-domain tier above `DomainEmitter` (YC `Operation` style) | Tasks 9, 10 |

Secondary defaults carried from the design-input's open questions, also OWNER-OVERRIDABLE:

- **(B) Discriminator tag-value typing:** loader auto-synthesizes the `Literal["<tag>"]` field on each variant from the union's `variants:` map (option (b)); a `LiteralType` `_Node` exists as the synthetic field's internal type but is never author-written. Alternative: option (a), author hand-writes the literal field on every variant. (Task 6.)
- **(C) `RenderedType` extension:** narrow, named fields per concern (`discriminator: str | None`, `coercer: str | None`) rather than one general `field_extra` bag (YAGNI / rule-of-three). Alternative: a single `field_extra: tuple[tuple[str, str], ...]` bag. (Tasks 5, 8.)
- **(G) Scalar-format coercion ownership:** `_model_field`-level assembly (keeps `TypeMapper.render` a near-pure `NeutralType -> str`; the mapper only NAMES the coercer, `_model_field` splices the `Annotated[...]`). Alternative: `TypeMapper` renders a fully-coercing `Annotated[...]`. (Task 8.)

---

### Task 1: `resolve.py` surface split into a `resolve/` package (P0 finding A3 - pure refactor)

**Motivation:** P0's pre-merge review flagged (A3) that `src/refract/emitters/python/resolve.py` is a 1091-line multi-surface junk drawer, and P1's spec-growth routes most new axes (union lowering, format coercion, shared-model imports, the M1 walker) straight back into it. Pay this debt FIRST, before P1 grows the file. This is a PURE REFACTOR: move code verbatim, fix imports, ZERO behavior change. Right-sized as ONE task so a reviewer accepts/rejects the whole split.

**Files:**
- Create: `src/refract/emitters/python/resolve/__init__.py` (re-export shim - namespace only, no logic)
- Create: `src/refract/emitters/python/resolve/_common.py`, `resolve/requests.py`, `resolve/client.py`, `resolve/models.py`, `resolve/cli.py`, `resolve/mcp.py`, `resolve/tests.py`, `resolve/root_client.py`
- Delete: `src/refract/emitters/python/resolve.py` (its contents move verbatim into the package)
- Test: NONE. This task adds NO new test. The existing suite (`tests/emitters/**`, `tests/spec/**`, `tests/ir/**`, snapshots) is the safety net: it must pass UNCHANGED, and `refract generate --check` must stay byte-identical. State this explicitly in the PR.

**Import-surface preservation (the CHOICE, stated):** keep a re-export **shim** at `resolve/__init__.py` (brief's option a), NOT updating importers (option b). Rationale = LOWER CHURN: option a leaves all 7 `surfaces/*.py`, `backend.py`, and the 4 test files that reach the module through the `refract.emitters.python.resolve` namespace (`tests/emitters/python/test_resolve.py`, `tests/emitters/test_assembled_cli.py`, `tests/emitters/test_resolve_bodyless.py`, `tests/emitters/test_resolve_tests_multiop.py`) UNTOUCHED. Option b would have to rewrite `test_resolve.py`'s ~25 `resolve.<symbol>` references (which span every surface) plus `test_assembled_cli.py`'s - far more churn. The package path `refract.emitters.python.resolve` stays a valid import target; `from refract.emitters.python.resolve import resolve_client` and `from refract.emitters.python import resolve` then `resolve._model_field` both keep resolving against `__init__.py`.

- `resolve/__init__.py` is namespace-only (compatible with the "no logic in `__init__.py`" rule - it re-exports, nothing more): it imports and re-exports every symbol the current importers reach, and lists them in `__all__`. This includes the PRIVATE helpers the existing tests access through the namespace (`_model_field`, `_assembled_options`, `_cli_command`, `_request_function`, `_client_method`, `_mcp_tool`, `_body_test_imports`, `_cli_test`, `_mcp_test`, `_guard_test`, `_select_scheme`) alongside the public `resolve_*` + shared helpers (`render_imports`, `signature_params`, `indent_lines`, `py_str`). Re-exporting privates preserves the pre-existing (test-only) access with zero test churn - it does not sanction NEW reach-in.

**Helper placement (by cohesion - `_common.py` holds ONLY genuinely 2+-surface helpers; each surface module owns its private helpers):**

| Target module | Symbols moved (verbatim) |
|---|---|
| `resolve/_common.py` | `render_imports`, `signature_params`, `indent_lines`, `param_decl`, `py_str`, `signature_and_call`, `_shared_models_module` (each used by >= 2 surfaces) |
| `resolve/requests.py` | `path_expr`, `_request_doc`, `_request_function`, `resolve_requests` |
| `resolve/client.py` | `_client_method`, `resolve_client` |
| `resolve/models.py` | `_model_field`, `_model_class`, `resolve_models` |
| `resolve/cli.py` | `_GROUP_DOC`, `_remap_to_resource_models`, `_partition_by_default`, `_cli_write_parts`, `_cli_command`, `resolve_cli`, `_option_decl`, `_handler_hint`, `_require_object_model`, `_reject_duplicate_options`, `_assembled_options` |
| `resolve/mcp.py` | `_tags_symbol`, `_mcp_signature`, `_mcp_call_args`, `_mcp_tool`, `resolve_mcp` |
| `resolve/tests.py` | `_EMPTY_GUARD_DOC`, `_tests_module_doc`, `_body_test_imports`, `_tests_imports`, `_tests_constants`, `_stub`, `_asserts`, `_client_test`, `_cli_test`, `_mcp_test`, `_guard_test`, `_test_block`, `resolve_tests` |
| `resolve/root_client.py` | `_auth_value`, `_multi_header_call`, `_header_call`, `_select_scheme`, `resolve_root_client` |

`path_expr` and `_partition_by_default` are single-surface (requests, cli respectively), so - despite the brief's rough sketch listing them near `_common` - cohesion places them in their owning surface module. Each surface module imports the `_common` helpers it needs (`from refract.emitters.python.resolve._common import render_imports, signature_and_call, ...`) and its own `views` PageView; `_common.py` imports `Import` from `refract.emitters.api` and the shared `ir`/`spec` symbols.

**CRITICAL - move VERBATIM, do not rewrite:** several helpers were touched by P0's pre-merge fixes and MUST carry their exact current bodies: `_tests_constants` (C1 payload-case selection), `_cli_write_parts` + `_reject_duplicate_options` (I1 cross-source body/path/query dedup - this is the M2 work already done, see removed Task 12), `_handler_hint` (A1 message). Use `git mv`-style moves (cut the definition, paste it into the target module unchanged); run `git diff -M` after to confirm the split registers as pure moves.

- [ ] **Step 1: Baseline (confirm green BEFORE touching anything)**

Run: `uv run pytest -q && uv run ruff check . && uv run ty check && uv run refract generate --check`
Expected: ALL green (full suite passes, ruff/ty clean, `--check` exit 0). This is the oracle the split must preserve.

- [ ] **Step 2: Create the package + move code verbatim**

Create `src/refract/emitters/python/resolve/` and the 8 modules above. Cut each helper from the old `resolve.py` and paste it - unchanged - into its target module per the placement table. Add per-module imports (each module imports only what it uses: from `_common`, from `refract.emitters.api`, from `refract.ir`, from `refract.spec`, and its own `views` PageView). Delete the now-empty `resolve.py`.

- [ ] **Step 3: Add the re-export shim**

```python
# src/refract/emitters/python/resolve/__init__.py
from refract.emitters.python.resolve._common import (
    indent_lines,
    param_decl,
    py_str,
    render_imports,
    signature_and_call,
    signature_params,
)
from refract.emitters.python.resolve.cli import (
    _assembled_options,
    _cli_command,
    resolve_cli,
)
from refract.emitters.python.resolve.client import _client_method, resolve_client
from refract.emitters.python.resolve.mcp import _mcp_tool, resolve_mcp
from refract.emitters.python.resolve.models import _model_field, resolve_models
from refract.emitters.python.resolve.requests import _request_function, resolve_requests
from refract.emitters.python.resolve.root_client import _select_scheme, resolve_root_client
from refract.emitters.python.resolve.tests import (
    _body_test_imports,
    _cli_test,
    _guard_test,
    _mcp_test,
    resolve_tests,
)

__all__ = [
    "resolve_cli", "resolve_client", "resolve_mcp", "resolve_models",
    "resolve_requests", "resolve_root_client", "resolve_tests",
    "render_imports", "signature_params", "indent_lines", "param_decl",
    "py_str", "signature_and_call",
]
```

(Add any further private symbol a test reaches through `resolve.` that is not yet listed - grep `resolve\.[_a-z]` across `tests/` to enumerate; the `ruff` unused-import lint on `__init__.py` is silenced by the `__all__` re-export contract - confirm ruff stays clean.)

- [ ] **Step 4: Verify the refactor is behavior-preserving (the whole gate, unchanged)**

Run: `uv run pytest -q && uv run ruff check . && uv run ty check && uv run refract generate --check`
Expected: byte-for-byte the SAME green as Step 1 - same test count passing, ruff/ty clean, `--check` exit 0 (generated `out/` is byte-identical; this is a source-only refactor with no emitted-output change). If any test that imported from `resolve` now errors, the shim is missing a re-export - add it (do NOT edit the test). Confirm 100% line+branch coverage holds (moved code keeps its existing tests).

- [ ] **Step 5: Commit**

```bash
git add src/refract/emitters/python/resolve/ && git rm src/refract/emitters/python/resolve.py
git commit -m "refactor(emit): split resolve.py into a per-surface resolve/ package (A3)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `UnionType` IR node + `NeutralType` union widening

**Files:**
- Modify: `src/refract/ir/types.py` (new `UnionType` class; widen the `NeutralType` `Annotated[...]`; `UnionType.model_rebuild()`; export in `__all__`)
- Test: `tests/ir/test_types.py`

**Interfaces:**
- Consumes: nothing new - a frozen `_Node` sibling of `ScalarType`/`RefType`/`ListType`/`MapType` (`ir/types.py:23-41`).
- Produces:
  ```python
  class UnionType(_Node):
      kind: Literal["union"] = "union"
      variants: tuple[NeutralType, ...]     # >= 2, enforced at construction
      discriminator: str | None = None      # sibling tag FIELD NAME on each variant; None = undiscriminated
  ```
  Widen `NeutralType = Annotated[ScalarType | RefType | ListType | MapType | UnionType, Field(discriminator="kind")]` (`ir/types.py:44-47`) and add `UnionType.model_rebuild()` alongside `ListType`/`MapType` (`ir/types.py:49-50`). The `>= 2` rule is a `@model_validator(mode="after")` raising `ValueError` (a fail-loud guard; `-O`-safe).

- [ ] **Step 1: Write failing tests** (real code)

```python
# tests/ir/test_types.py (add)
import pytest
from pydantic import ValidationError
from refract.ir.types import ListType, RefType, ScalarType, UnionType


def test_union_type_round_trips_like_the_other_kinds():
    union = UnionType(variants=(ScalarType(scalar="string"), RefType(target="X")), discriminator=None)
    assert union.kind == "union"
    dumped = union.model_dump()
    assert UnionType.model_validate(dumped) == union


def test_union_type_discriminated_carries_the_tag_field_name():
    union = UnionType(variants=(RefType(target="Paragraph"), RefType(target="Heading1Block")), discriminator="type")
    assert union.discriminator == "type"


def test_union_type_nests_inside_list_and_stays_hashable():
    inner = UnionType(variants=(ScalarType(scalar="string"), ScalarType(scalar="integer")))
    listed = ListType(item=inner)
    assert listed.item == inner
    assert hash(listed)  # frozen -> hashable


def test_union_type_requires_at_least_two_variants():
    with pytest.raises(ValidationError):
        UnionType(variants=(ScalarType(scalar="string"),))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/ir/test_types.py -k union -q`
Expected: FAIL (`ImportError`: `UnionType` does not exist).

- [ ] **Step 3: Implement** - add the class + validator, widen the union, rebuild, export.

```python
# src/refract/ir/types.py
from pydantic import model_validator  # add to imports

class UnionType(_Node):
    kind: Literal["union"] = "union"
    variants: tuple[NeutralType, ...]
    discriminator: str | None = None

    @model_validator(mode="after")
    def _at_least_two_variants(self) -> UnionType:
        if len(self.variants) < 2:
            raise ValueError("a union needs >= 2 variants")
        return self


NeutralType = Annotated[
    ScalarType | RefType | ListType | MapType | UnionType,
    Field(discriminator="kind"),
]

ListType.model_rebuild()
MapType.model_rebuild()
UnionType.model_rebuild()
```

Add `"UnionType"` to `__all__` (`ir/types.py:14`).

- [ ] **Step 4: Run to verify pass + gate**

Run: `uv run pytest tests/ir/test_types.py -q && uv run ruff check . && uv run ty check`
Expected: PASS, clean. NOTE: `PythonTypeMapper._base` (`emitters/python/types.py:23-40`) does NOT yet have a `UnionType` arm - that is fine here (no `UnionType` reaches the mapper until Task 3's tests). ty's exhaustiveness check on `_base` may flag the new member: if so, that flag is resolved in Task 3 (the undiscriminated arm). If ty fails at THIS task, add a temporary `case UnionType(): raise NotImplementedError` (excluded from coverage via `raise NotImplementedError`) and replace it in Task 3 - prefer landing Task 3 immediately after so no placeholder lingers.

- [ ] **Step 5: Commit**

```bash
git add src/refract/ir/types.py tests/ir/test_types.py
git commit -m "feat(ir): UnionType neutral-type node (discriminated + undiscriminated)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Undiscriminated lowering in `PythonTypeMapper._base`

**Files:**
- Modify: `src/refract/emitters/python/types.py` (`_base` `:23-40` gains a `UnionType` arm; import `UnionType`)
- Test: `tests/emitters/python/test_types.py`

**Interfaces:**
- Consumes: `UnionType(discriminator=None)`.
- Produces: `PythonTypeMapper().render(UnionType(variants=(string, integer), discriminator=None), optional=False).text == "str | int"`; the arm unions each variant's imports; no `Annotated`/`Field` wrapping (that is the discriminated case, Task 5). A `RefType` variant renders bare (`Paragraph | Heading1Block`).

- [ ] **Step 1: Write failing tests** (real code)

```python
# tests/emitters/python/test_types.py (add)
from refract.emitters.python.types import PythonTypeMapper
from refract.ir.types import RefType, ScalarType, UnionType


def test_undiscriminated_scalar_union_renders_pep604():
    union = UnionType(variants=(ScalarType(scalar="string"), ScalarType(scalar="integer")), discriminator=None)
    assert PythonTypeMapper().render(union, optional=False).text == "str | int"


def test_undiscriminated_union_optional_wraps_whole():
    union = UnionType(variants=(ScalarType(scalar="string"), ScalarType(scalar="integer")), discriminator=None)
    assert PythonTypeMapper().render(union, optional=True).text == "str | int | None"


def test_undiscriminated_union_of_refs_renders_bare_names():
    union = UnionType(variants=(RefType(target="Paragraph"), RefType(target="Heading1Block")), discriminator=None)
    assert PythonTypeMapper().render(union, optional=False).text == "Paragraph | Heading1Block"


def test_union_with_any_variant_pulls_the_typing_import():
    union = UnionType(variants=(ScalarType(scalar="any"), ScalarType(scalar="integer")), discriminator=None)
    rendered = PythonTypeMapper().render(union, optional=False)
    assert any(imp.module == "typing" and imp.name == "Any" for imp in rendered.imports)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/emitters/python/test_types.py -k union -q`
Expected: FAIL (`_base` hits `assert_never` / `NotImplementedError` on `UnionType`).

- [ ] **Step 3: Implement** - add the arm to `_base` (`types.py:24-40`), BEFORE `case _:`:

```python
# src/refract/emitters/python/types.py
from itertools import chain  # add
from refract.ir.types import ..., UnionType  # add

            case UnionType(variants=variants, discriminator=None):
                rendered = [self._base(v) for v in variants]
                text = " | ".join(r.text for r in rendered)
                return RenderedType(text=text, imports=tuple(chain.from_iterable(r.imports for r in rendered)))
```

(Remove any temporary `NotImplementedError` placeholder from Task 2.) The discriminated arm - `discriminator is not None` - is Task 5; until then a discriminated `UnionType` reaching `_base` falls to `assert_never`, but none is rendered before Task 5.

- [ ] **Step 4: Run to verify pass + gate**

Run: `uv run pytest tests/emitters/python/test_types.py -q && uv run ruff check . && uv run ty check`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add src/refract/emitters/python/types.py tests/emitters/python/test_types.py
git commit -m "feat(emit): lower undiscriminated unions to PEP-604 A | B

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `OneOfSpec` - a SINGLE structured `oneof:` node for BOTH union kinds (Variant 2, mutually exclusive with `type:`)

**Files:**
- Modify: `src/refract/spec/nodes.py` (new `OneOfSpec`; `FieldSpec.type` gains a sentinel default; `FieldSpec.oneof: OneOfSpec | None = None`)
- Modify: `src/refract/spec/loader.py` (import `UnionType`; `_field` branches on `spec.oneof` vs `spec.type`, raising `SpecError` if both or neither; new `_oneof_type` helper)
- Test: `tests/spec/test_loader.py`

**Interfaces:**
- Consumes: a `FieldSpec` carrying either `type:` (existing) or `oneof:` (new), never both. This is the OWNER-SELECTED Variant 2 (row A): ONE structured node for discriminated AND undiscriminated unions - there is NO compact `oneOf<A|B>` string grammar.
- Produces:
  ```python
  # nodes.py
  class OneOfSpec(_Spec):
      variants: dict[str, str]          # label -> type-EXPRESSION ("ref<Paragraph>", "string", "list<ref<X>>")
      discriminator: str | None = None  # wire tag FIELD NAME; None => undiscriminated (labels are documentation only)

  class FieldSpec(_Spec):
      name: str
      type: str | None = None           # sentinel None: absent when `oneof:` is used instead
      # (optional, default, alias, description, enum, format, deprecated - existing fields, unchanged)
      oneof: OneOfSpec | None = None     # mutually exclusive with `type:`
  ```
  Each variant VALUE is a neutral type-EXPRESSION parsed by `parse_neutral_type` (NOT a bare model name). This lets an UNDISCRIMINATED union mix scalars/lists/refs (Stripe `oneof: {variants: {id: string, full: "ref<Customer>"}}`), while a DISCRIMINATED union (`discriminator` set) requires every variant to be a `ref<Model>` (pydantic discriminated unions need BaseModel arms) - enforced fail-loud in `_oneof_type`. Undiscriminated: `discriminator` omitted; the map KEYS are human labels with NO wire meaning. Because `FieldSpec.type` is non-optional today (`nodes.py:30`), it gains a sentinel `None` default so `oneof:`-only fields validate; the loader treats the sentinel as "no scalar type given". A field with a real `type:` AND `oneof:` raises `SpecError`; a field with NEITHER raises `SpecError`. A `oneof` with `< 2` variants is rejected by `UnionType`'s validator (re-wrapped `SpecError`). (Mutual-exclusion logic + the sentinel default are UNCHANGED from the draft; only the variant-VALUE semantics and the `str | None` discriminator are new for Variant 2.)

- [ ] **Step 1: Write failing tests** (real code)

```python
# tests/spec/test_loader.py (add)
import pytest
from refract.ir.types import RefType, ScalarType, UnionType
from refract.spec import nodes
from refract.spec.loader import SpecError, _field


def test_undiscriminated_oneof_lowers_to_union_of_mixed_type_exprs():
    """Variant 2: an undiscriminated `oneof` (no discriminator) mixes a scalar + a ref."""
    field = _field(
        nodes.FieldSpec(
            name="source",
            oneof=nodes.OneOfSpec(variants={"id": "string", "full": "ref<Customer>"}),
        )
    )
    assert field.type == UnionType(
        variants=(ScalarType(scalar="string"), RefType(target="Customer")), discriminator=None
    )


def test_discriminated_oneof_lowers_to_ref_union_with_discriminator():
    field = _field(
        nodes.FieldSpec(
            name="block",
            oneof=nodes.OneOfSpec(
                discriminator="type",
                variants={"paragraph": "ref<Paragraph>", "heading_1": "ref<Heading1Block>"},
            ),
        )
    )
    assert field.type == UnionType(
        variants=(RefType(target="Paragraph"), RefType(target="Heading1Block")), discriminator="type"
    )


def test_discriminated_oneof_with_non_ref_variant_raises():
    """A discriminated variant that is a scalar (not `ref<Model>`) is rejected fail-loud."""
    spec = nodes.FieldSpec(
        name="block",
        oneof=nodes.OneOfSpec(discriminator="type", variants={"a": "string", "b": "ref<B>"}),
    )
    with pytest.raises(SpecError, match="must be a ref"):
        _field(spec)


def test_single_variant_oneof_is_rejected():
    """The UnionType `>= 2` validator fires, re-wrapped as SpecError (covers the except arm)."""
    spec = nodes.FieldSpec(name="x", oneof=nodes.OneOfSpec(variants={"only": "string"}))
    with pytest.raises(SpecError, match="2 variants"):
        _field(spec)


def test_field_with_both_type_and_oneof_raises():
    spec = nodes.FieldSpec(
        name="block",
        type="string",
        oneof=nodes.OneOfSpec(discriminator="type", variants={"a": "ref<A>", "b": "ref<B>"}),
    )
    with pytest.raises(SpecError, match="exactly one of 'type' and 'oneof'"):
        _field(spec)


def test_field_with_neither_type_nor_oneof_raises():
    with pytest.raises(SpecError, match="needs 'type' or 'oneof'"):
        _field(nodes.FieldSpec(name="block"))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/spec/test_loader.py -k "oneof or variant" -q`
Expected: FAIL (`OneOfSpec`/`FieldSpec.oneof` do not exist; `_field` cannot branch).

- [ ] **Step 3: Implement** - add the node, make `type` sentinel-defaulted, branch `_field`, add `_oneof_type`.

```python
# src/refract/spec/nodes.py
class OneOfSpec(_Spec):
    variants: dict[str, str]          # label -> type-EXPRESSION
    discriminator: str | None = None  # None => undiscriminated

class FieldSpec(_Spec):
    name: str
    type: str | None = None           # sentinel None: absent when `oneof` is used instead
    optional: bool = False
    # (default, alias, description, enum, format, deprecated - existing fields, unchanged)
    oneof: OneOfSpec | None = None
```

```python
# src/refract/spec/loader.py
from refract.ir.types import ListType, MapType, NeutralType, RefType, ScalarType, UnionType  # + UnionType


def _field(spec: nodes.FieldSpec) -> ir.Field:
    if spec.type is not None and spec.oneof is not None:
        raise SpecError(f"field {spec.name!r}: set exactly one of 'type' and 'oneof', not both")
    if spec.oneof is not None:
        neutral_type: NeutralType = _oneof_type(spec.name, spec.oneof)
    elif spec.type is not None:
        neutral_type = parse_neutral_type(spec.type)
    else:
        raise SpecError(f"field {spec.name!r}: needs 'type' or 'oneof'")
    return ir.Field(name=spec.name, type=neutral_type, optional=spec.optional,
                    default=spec.default, alias=spec.alias, description=spec.description)


def _oneof_type(field_name: str, spec: nodes.OneOfSpec) -> UnionType:
    """Lower a structured `oneof:` node to a UnionType (Variant 2: one node, both union kinds).

    Variant VALUES are neutral type-EXPRESSIONS, so an undiscriminated union may mix
    scalars/lists/refs; a discriminated union (`discriminator` set) requires every variant to be a
    `ref<Model>` (pydantic discriminated unions need BaseModel arms). Map KEYS are wire tag values
    when discriminated, documentation-only labels when not.
    """
    variants = tuple(parse_neutral_type(expr) for expr in spec.variants.values())
    if spec.discriminator is not None:
        for label, expr, variant in zip(spec.variants, spec.variants.values(), variants, strict=True):
            if not isinstance(variant, RefType):
                raise SpecError(
                    f"field {field_name!r}: discriminated variant {label!r} must be a "
                    f"ref<Model>, got {expr!r}"
                )
    try:
        return UnionType(variants=variants, discriminator=spec.discriminator)
    except ValueError as error:  # the >= 2 validator
        raise SpecError(f"field {field_name!r}: {error}") from error
```

- [ ] **Step 4: Run to verify pass + gate**

Run: `uv run pytest tests/spec/ -q && uv run refract generate --check && uv run ruff check . && uv run ty check`
Expected: PASS; `--check` exit 0 (making `type` optional does not change any existing spec output). Confirm no existing `FieldSpec(type=...)` call site broke.

- [ ] **Step 5: Commit**

```bash
git add src/refract/spec/nodes.py src/refract/spec/loader.py tests/spec/
git commit -m "feat(spec): single structured oneof node for discriminated + undiscriminated unions (Variant 2)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `RenderedType.discriminator` + `_base` discriminated arm + `_model_field` unified `Field(...)` assembly

**Files:**
- Modify: `src/refract/emitters/api.py` (`RenderedType` `:22-27` gains `discriminator: str | None = None`)
- Modify: `src/refract/emitters/python/types.py` (`_base` gains the `discriminator is not None` arm)
- Modify: `src/refract/emitters/python/resolve/models.py` (post-Task-1 home of `_model_field`/`resolve_models`) - `_model_field` becomes the ONE place assembling `Annotated[Union, Field(discriminator=...)]`; widen `resolve_models` import-gating
- Test: `tests/emitters/python/test_types.py`, `tests/emitters/python/test_resolve.py`

**Interfaces:**
- Consumes: a discriminated `UnionType`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class RenderedType:
      text: str
      imports: tuple[Import, ...] = ()
      discriminator: str | None = None   # NEW - sibling tag field name, if this is a discriminated union
  ```
  `_base`'s discriminated arm returns `text` as the BARE `A | B` union (NO `Annotated` wrapper) plus `discriminator=disc`. `_model_field` is the single assembly point: it wraps the field in `Annotated[<text>, Field(discriminator=<repr>, ...merged with default/alias/description...)]`, ordering `discriminator` first. When `rendered.discriminator is not None` the field is ALWAYS wrapped in `Field(...)` even with no default/alias/description - so the `not field.description and not field.alias` early-return in `_model_field` MUST also require `rendered.discriminator is None`. `resolve_models` import-gating gains a condition: a field whose rendered type carries a `discriminator` also imports `Field` (pydantic) + `Annotated` (typing).

- [ ] **Step 1: Write failing tests** (real code)

```python
# tests/emitters/python/test_types.py (add)
from refract.ir.types import RefType, UnionType


def test_discriminated_union_base_is_bare_and_carries_discriminator():
    union = UnionType(variants=(RefType(target="Paragraph"), RefType(target="Heading1Block")), discriminator="type")
    rendered = PythonTypeMapper().render(union, optional=False)
    assert rendered.text == "Paragraph | Heading1Block"      # NO Annotated wrapper baked in
    assert rendered.discriminator == "type"
```

```python
# tests/emitters/python/test_resolve.py (add)
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.types import PythonTypeMapper
from refract.emitters.python.resolve import _model_field
from refract.ir import Field
from refract.ir.types import RefType, UnionType

_UNION = UnionType(variants=(RefType(target="Paragraph"), RefType(target="Heading1Block")), discriminator="type")


def test_discriminated_field_emits_single_annotated_field_call():
    line, imports = _model_field(Field(name="block", type=_UNION), PythonTypeMapper())
    assert line == '    block: Annotated[Paragraph | Heading1Block, Field(discriminator="type")]'
    assert {("typing", "Annotated"), ("pydantic", "Field")} <= {(i.module, i.name) for i in imports}


def test_discriminated_field_with_description_merges_one_field_call():
    line, _ = _model_field(Field(name="block", type=_UNION, description="A block."), PythonTypeMapper())
    assert line == '    block: Annotated[Paragraph | Heading1Block, Field(discriminator="type", description="A block.")]'
    assert line.count("Field(") == 1   # not two nested Field(...) calls
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/emitters/python -k "discriminat" -q`
Expected: FAIL (`RenderedType` has no `discriminator`; `_base` has no discriminated arm; `_model_field` bakes no `Annotated`).

- [ ] **Step 3: Implement**

`emitters/api.py` - add `discriminator: str | None = None` to `RenderedType`.

`emitters/python/types.py` - `render` must PRESERVE `discriminator` when it wraps optional (today it rebuilds `RenderedType(text=..., imports=base.imports)` at `:16-17`, dropping any new field). Add the arm and thread the field:

```python
    def render(self, neutral_type: NeutralType, *, optional: bool) -> RenderedType:
        base = self._base(neutral_type)
        if optional:
            return RenderedType(text=f"{base.text} | None", imports=base.imports, discriminator=base.discriminator)
        return base

    # in _base: EXTEND the existing SINGLE unguarded UnionType arm (Task 3 left it as
    # `case UnionType(variants=variants):` returning a bare `A | B` with no discriminator). Do NOT
    # add a second arm (it would shadow / be unreachable and break exhaustiveness). Just capture
    # `discriminator=disc` and thread it into RenderedType - for an undiscriminated union `disc` is
    # None (the RenderedType default), for a discriminated one it is the tag field name. One arm,
    # no internal branch, still ty-exhaustive:
            case UnionType(variants=variants, discriminator=disc):
                rendered = [self._base(v) for v in variants]
                text = " | ".join(r.text for r in rendered)
                return RenderedType(text=text, imports=tuple(chain.from_iterable(r.imports for r in rendered)), discriminator=disc)
```

`emitters/python/resolve/models.py` - `_model_field` assembly:

```python
def _model_field(field: ir.Field, type_mapper: TypeMapper) -> tuple[str, list[Import]]:
    rendered = type_mapper.render(field.type, optional=field.optional)
    imports = list(rendered.imports)
    default = field.default if field.default is not None else type_mapper.null_default(field.type, optional=field.optional)
    text = rendered.text
    if rendered.discriminator is not None:
        text = f"Annotated[{text}, __FIELD__]"      # placeholder replaced below with the merged Field(...)
        imports += [Import("typing", "Annotated"), Import("pydantic", "Field")]
    if rendered.discriminator is None and not field.description and not field.alias:
        return f"    {field.name}: {text} = {default}", imports
    arguments: list[str] = []
    if rendered.discriminator is not None:
        arguments.append(f"discriminator={py_str(rendered.discriminator)}")
    if default is not None and rendered.discriminator is None:
        arguments.append(f"default={default}")
    if field.alias is not None:
        arguments.append(f"alias={py_str(field.alias)}")
    if field.description is not None:
        arguments.append(f"description={py_str(field.description)}")
    field_call = f"Field({', '.join(arguments)})"
    if rendered.discriminator is not None:                       # Field lives INSIDE Annotated[...]
        return f"    {field.name}: {text.replace('__FIELD__', field_call)}", imports
    return f"    {field.name}: {text} = {field_call}", imports    # Field is the default value (existing shape)
```

Design note (implementer): a discriminated field has NO trailing `= default` - the `Field(...)` sits inside `Annotated[...]`, and pydantic requires a discriminated union to be non-optional-by-tag (optionality, if ever needed, becomes a `None`-tagged variant, out of scope for P1). Keep the `__FIELD__` splice or refactor to build `text` after `field_call` - either is fine; the test pins the exact output.

`resolve_models` import-gating (in `resolve/models.py`) - widen the `any(...)` that appends `Import("pydantic", "Field")` to also fire when any field's rendered type carries a discriminator, and separately append `Import("typing", "Annotated")` in that case. (Simplest: rely on the per-field `imports` returned by `_model_field` - they already include Annotated+Field - and drop the redundant module-level gate for the discriminator case; confirm `render_imports` de-dups so a doubled `Field` import collapses.)

- [ ] **Step 4: Run to verify pass + gate**

Run: `uv run pytest -q && uv run refract generate --check && uv run ruff check . && uv run ty check`
Expected: PASS; `--check` exit 0 (no existing model uses a union field yet). NOTE: `_model_field` restructure MUST keep every existing (non-union) field byte-identical - the priorities `LocalizedName`/`PriorityCreate` snapshot is the oracle.

- [ ] **Step 5: Commit**

```bash
git add src/refract/emitters/api.py src/refract/emitters/python/types.py src/refract/emitters/python/resolve.py tests/emitters/
git commit -m "feat(emit): discriminated-union field emits one Annotated[..., Field(discriminator=...)]

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `LiteralType` node + loader auto-synthesis of each variant's `Literal[tag]` field (default B)

**Files:**
- Modify: `src/refract/ir/types.py` (new `LiteralType`; widen `NeutralType` again; `model_rebuild()`; `__all__`)
- Modify: `src/refract/emitters/python/types.py` (`_base` renders `Literal["<value>"]` + `Import("typing", "Literal")`)
- Modify: `src/refract/spec/loader.py` (`_resource` / a new `_synthesize_discriminators` post-pass injects the synthetic tag field into each named variant `ObjectModel`)
- Test: `tests/ir/test_types.py`, `tests/emitters/python/test_types.py`, `tests/spec/test_loader.py`

**Interfaces:**
- Consumes: the built `tuple[ir.Model, ...]` for a resource + each `FieldSpec.oneof` (label -> variant type-EXPRESSION). Under Variant 2 the variant model NAME comes from parsing each DISCRIMINATED variant's `ref<...>` value and taking `.target` (ref-ness already enforced by Task 4's `_oneof_type`).
- Produces:
  ```python
  class LiteralType(_Node):
      kind: Literal["literal"] = "literal"
      value: str                 # exact string literal, e.g. "heading_1"
  ```
  `_base` lowers it to `Literal["heading_1"]` (import `from typing import Literal`). The loader post-pass, after building all models, for each DISCRIMINATED `oneof` field (discriminator set; an UNDISCRIMINATED `oneof` synthesizes NOTHING), parses each variant `ref<...>` value to a `RefType`, and injects `ir.Field(name=oneof.discriminator, type=LiteralType(value=label))` at the FRONT of that variant `ObjectModel`'s `fields`. A variant that already authors a field named `<discriminator>` raises `SpecError` (collision - the author must not hand-write the synthesized tag). A `oneof` naming a variant that is not a declared model raises `SpecError`; a variant that resolves to a non-object model (a `RootListModel`) raises `SpecError`.

- [ ] **Step 1: Write failing tests** (real code) - `LiteralType` node + mapper

```python
# tests/ir/test_types.py (add)
def test_literal_type_round_trips():
    from refract.ir.types import LiteralType
    lit = LiteralType(value="heading_1")
    assert LiteralType.model_validate(lit.model_dump()) == lit

# tests/emitters/python/test_types.py (add)
def test_literal_type_lowers_to_typing_literal():
    from refract.ir.types import LiteralType
    rendered = PythonTypeMapper().render(LiteralType(value="heading_1"), optional=False)
    assert rendered.text == 'Literal["heading_1"]'
    assert ("typing", "Literal") in {(i.module, i.name) for i in rendered.imports}
```

- [ ] **Step 2: Run to verify failure** - Run: `uv run pytest tests/ir/test_types.py tests/emitters/python/test_types.py -k literal -q` -> FAIL.

- [ ] **Step 3: Implement** - `LiteralType` in `ir/types.py` (widen `NeutralType` to include it, `LiteralType.model_rebuild()` not needed - no recursive field - but keep the union order stable), `_base` arm:

```python
            case LiteralType(value=value):
                return RenderedType(text=f"Literal[{py_str_literal(value)}]", imports=(Import("typing", "Literal"),))
```

(Use `json.dumps(value)`-style quoting so `"heading_1"` renders with double quotes matching ruff; reuse the `py_str` convention.)

- [ ] **Step 4: Write failing test** (real code) - loader synthesis

```python
# tests/spec/test_loader.py (add)
from refract.ir.types import LiteralType
from refract.spec.loader import _resource


def _minimal_op() -> nodes.OperationSpec:
    """A minimal spec op so a `ResourceSpec` validates (ResourceSpec.operations is required)."""
    return nodes.OperationSpec(
        name="list", method="GET", path="blocks", operationId="blocks_list",
        responses={200: nodes.ResponseSpec(model="Block")},
        mcp=nodes.McpSpec(name="blocks_list", safety="RO", title="List", documentation="List blocks."),
    )


def _paragraph() -> nodes.ModelSpec:
    return nodes.ModelSpec(name="Paragraph", fields=[nodes.FieldSpec(name="text", type="string", optional=True)])


def _heading() -> nodes.ModelSpec:
    return nodes.ModelSpec(name="Heading1Block", fields=[nodes.FieldSpec(name="text", type="string", optional=True)])


def _block_with(variants: dict[str, str]) -> nodes.ModelSpec:
    return nodes.ModelSpec(name="Block", fields=[
        nodes.FieldSpec(name="block", oneof=nodes.OneOfSpec(discriminator="type", variants=variants)),
    ])


def test_synthesizes_literal_tag_field_on_each_variant():
    spec = nodes.ResourceSpec(
        domain="notion", resource="blocks", security="tok",
        models=[_paragraph(), _heading(),
                _block_with({"paragraph": "ref<Paragraph>", "heading_1": "ref<Heading1Block>"})],
        operations=[_minimal_op()],
    )
    res = _resource(spec)
    paragraph = res.model("Paragraph")
    assert paragraph.fields[0].name == "type"
    assert paragraph.fields[0].type == LiteralType(value="paragraph")
    assert res.model("Heading1Block").fields[0].type == LiteralType(value="heading_1")


def test_variant_authoring_its_own_tag_field_raises():
    """A variant that hand-writes a field named `type` collides with the synthesized tag."""
    paragraph = nodes.ModelSpec(name="Paragraph", fields=[
        nodes.FieldSpec(name="type", type="string"),  # collides with the synthesized discriminator
        nodes.FieldSpec(name="text", type="string", optional=True),
    ])
    spec = nodes.ResourceSpec(
        domain="notion", resource="blocks", security="tok",
        models=[paragraph, _heading(),
                _block_with({"paragraph": "ref<Paragraph>", "heading_1": "ref<Heading1Block>"})],
        operations=[_minimal_op()],
    )
    with pytest.raises(SpecError, match="collides with the synthesized discriminator"):
        _resource(spec)


def test_oneof_naming_unknown_variant_raises():
    """A discriminated variant `ref<Nope>` where Nope is undeclared -> SpecError."""
    spec = nodes.ResourceSpec(
        domain="notion", resource="blocks", security="tok",
        models=[_paragraph(),
                _block_with({"paragraph": "ref<Paragraph>", "heading_1": "ref<Nope>"})],
        operations=[_minimal_op()],
    )
    with pytest.raises(SpecError, match="not a declared model"):
        _resource(spec)


def test_discriminated_variant_naming_non_object_model_raises():
    """A discriminated variant `ref<Rows>` where Rows is a root_list model -> SpecError (covers the
    ObjectModel guard: `_oneof_type` only checks ref-ness, not object-ness)."""
    rows = nodes.ModelSpec(name="Rows", kind="root_list", item="Paragraph")
    spec = nodes.ResourceSpec(
        domain="notion", resource="blocks", security="tok",
        models=[rows, _paragraph(),
                _block_with({"rows": "ref<Rows>", "paragraph": "ref<Paragraph>"})],
        operations=[_minimal_op()],
    )
    with pytest.raises(SpecError, match="must be an object model"):
        _resource(spec)
```

- [ ] **Step 5: Run to verify failure** -> FAIL (no synthesis).

- [ ] **Step 6: Implement** - a post-pass in `_resource` (before constructing `ir.Resource`), operating on the built model tuple + the spec's oneof declarations. Sketch:

```python
from typing import cast  # add to loader imports


def _synthesize_discriminators(
    models: tuple[ir.Model, ...], specs: list[nodes.ModelSpec]
) -> tuple[ir.Model, ...]:
    """Inject each discriminated-union variant's synthetic `Literal[label]` field (default B).

    Variant 2: for a DISCRIMINATED `oneof` (discriminator set) every variant VALUE is a `ref<Model>`
    - ref-ness is already enforced by `_oneof_type` upstream, so the parse is guaranteed a RefType
    (the `cast` narrows it without a dead isinstance branch). An UNDISCRIMINATED `oneof`
    (discriminator None) synthesizes nothing - its labels are documentation only.
    """
    by_name = {model.name: model for model in models}
    injected: dict[str, list[ir.Field]] = {}   # variant model name -> synthetic tag fields
    for model_spec in specs:
        for field_spec in model_spec.fields:
            oneof = field_spec.oneof
            if oneof is None or oneof.discriminator is None:
                continue
            for label, variant_expr in oneof.variants.items():
                target = cast(RefType, parse_neutral_type(variant_expr)).target  # ref enforced by _oneof_type
                if target not in by_name:
                    raise SpecError(
                        f"field {field_spec.name!r}: discriminated-union variant "
                        f"{target!r} is not a declared model"
                    )
                injected.setdefault(target, []).append(
                    ir.Field(name=oneof.discriminator, type=LiteralType(value=label))
                )
    result: list[ir.Model] = []
    for model in models:
        extra = injected.get(model.name)
        if extra is None:
            result.append(model)
            continue
        if not isinstance(model, ir.ObjectModel):
            raise SpecError(f"discriminated-union variant {model.name!r} must be an object model")
        existing = {field.name for field in model.fields}
        for synthetic in extra:
            if synthetic.name in existing:
                raise SpecError(
                    f"variant {model.name!r}: field {synthetic.name!r} collides with the "
                    "synthesized discriminator"
                )
        result.append(model.model_copy(update={"fields": (*extra, *model.fields)}))
    return tuple(result)
```

The "verify every named variant exists" check is the `if target not in by_name: raise` line above (folded into the first loop so the error keeps the `field_spec.name` context). Wire it in `_resource`: `models = _synthesize_discriminators(tuple(_model(m) for m in spec.models), spec.models)`.

- [ ] **Step 7: Run to verify pass + gate** - Run: `uv run pytest -q && uv run refract generate --check && uv run ruff check . && uv run ty check` -> PASS; `--check` exit 0 (no existing spec uses `oneof`).

- [ ] **Step 8: Behavioral proof** (opt-in) - author a tiny Notion-style block-union fixture (2-3 variants) in `tests/behavioral/`, generate its models module, import it, and assert pydantic actually discriminates: `Block.model_validate({"block": {"type": "heading_1", "text": "hi"}})` yields a `Heading1Block`, and an unknown tag raises `ValidationError`. Mark `@pytest.mark.behavioral`.

- [ ] **Step 9: Commit**

```bash
git add src/refract/ir/types.py src/refract/emitters/python/types.py src/refract/spec/loader.py tests/
git commit -m "feat(spec): synthesize Literal[tag] discriminator fields on union variants (no hand-authoring)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `ScalarType.format` + loader wiring

**Files:**
- Modify: `src/refract/ir/types.py` (`ScalarType` `:23-25` gains `format: str | None = None`)
- Modify: `src/refract/spec/loader.py` (`_field` combines `spec.format` onto a parsed `ScalarType`; `SpecError` on a non-scalar)
- Test: `tests/ir/test_types.py`, `tests/spec/test_loader.py`

**Interfaces:**
- Consumes: `nodes.FieldSpec.format` (`nodes.py:36`, currently parsed-then-dropped).
- Produces:
  ```python
  class ScalarType(_Node):
      kind: Literal["scalar"] = "scalar"
      scalar: Scalar
      format: str | None = None   # "int64" | "date-time" | "rfc2822" | ...; None = no coercion
  ```
  `_field(FieldSpec(name="cores", type="integer", format="int64"))` -> `ir.Field` whose `type == ScalarType(scalar="integer", format="int64")`. `format` on a non-scalar (`ref<...>`, `list<...>`, or a `oneof:` union) raises `SpecError`. `model_copy` is used to set `format` (the `_Node` is frozen).

- [ ] **Step 1: Write failing tests** (real code)

```python
# tests/spec/test_loader.py (add)
def test_format_lands_on_scalar_type():
    field = _field(nodes.FieldSpec(name="cores", type="integer", format="int64"))
    assert field.type == ScalarType(scalar="integer", format="int64")


def test_format_on_non_scalar_raises():
    with pytest.raises(SpecError, match="format is only valid on a scalar"):
        _field(nodes.FieldSpec(name="meta", type="ref<ObjectMeta>", format="int64"))
```

```python
# tests/ir/test_types.py (add)
def test_scalar_type_format_defaults_none_and_round_trips():
    from refract.ir.types import ScalarType
    st = ScalarType(scalar="integer", format="int64")
    assert st.format == "int64"
    assert ScalarType(scalar="integer").format is None
    assert ScalarType.model_validate(st.model_dump()) == st
```

- [ ] **Step 2: Run to verify failure** -> FAIL.

- [ ] **Step 3: Implement**

```python
# ir/types.py
class ScalarType(_Node):
    kind: Literal["scalar"] = "scalar"
    scalar: Scalar
    format: str | None = None
```

```python
# loader.py - _field, after computing neutral_type (Task 4's branch), before building ir.Field:
    if spec.format is not None:
        if not isinstance(neutral_type, ScalarType):
            raise SpecError(f"field {spec.name!r}: format is only valid on a scalar type")
        neutral_type = neutral_type.model_copy(update={"format": spec.format})
```

- [ ] **Step 4: Run to verify pass + gate** - Run: `uv run pytest -q && uv run refract generate --check && uv run ruff check . && uv run ty check` -> PASS; `--check` exit 0 (no existing field authors `format:`; adding a defaulted `format=None` slot leaves `model_dump` shape stable for existing scalars).

- [ ] **Step 5: Commit**

```bash
git add src/refract/ir/types.py src/refract/spec/loader.py tests/
git commit -m "feat(ir): ScalarType.format slot + loader wiring (format only on scalars)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Scalar-format coercion lowering (default G: `_model_field`-level)

**Files:**
- Modify: `src/refract/emitters/api.py` (`RenderedType` gains `coercer: str | None = None`)
- Modify: `src/refract/emitters/python/types.py` (`_base` scalar arm reads `.format`; a small `_FORMAT_COERCERS` registry maps format -> (base-type override, coercer name, type imports))
- Modify: `src/refract/emitters/python/resolve/models.py` (`_model_field` splices `Annotated[<base>, BeforeValidator(<coercer>)]`; `resolve_models` adds the coercer import from the shared base module)
- Test: `tests/emitters/python/test_types.py`, `tests/emitters/python/test_resolve.py`; behavioral in `tests/behavioral/`

**Interfaces:**
- Consumes: `ScalarType(scalar=..., format=...)`.
- Produces: a small registry keyed by format:
  ```python
  # types.py
  _FORMAT_COERCERS: dict[str, _Coercion] = {
      "int64":   _Coercion(base="int",      coercer="coerce_int64",     type_imports=()),
      "rfc2822": _Coercion(base="datetime", coercer="coerce_rfc2822",   type_imports=(Import("datetime", "datetime"),)),
  }
  ```
  For `format="int64"` the RENDERED TYPE STAYS `int`; `RenderedType.coercer = "coerce_int64"`. For `format="rfc2822"` the base becomes `datetime` (pulls `from datetime import datetime`) and `coercer = "coerce_rfc2822"`. An UNKNOWN format renders the bare scalar with `coercer=None` (a format refract does not coerce is a documented no-op, not an error - the wire type is unchanged). `_model_field`, when `rendered.coercer is not None`, wraps `Annotated[<base>, BeforeValidator(<coercer>)]` and adds `Import("pydantic", "BeforeValidator")` + `Import("typing", "Annotated")`. `resolve_models` (which has `ctx`) adds `Import(_shared_models_module(ctx), <coercer>)` for each coerced field - the coercer helpers (`coerce_int64`, `coerce_rfc2822`) are HAND-WRITTEN in the shared base module (`ycli.yandex.models`), mirroring the existing hand-written `APIModel`/`require_found` convention; refract emits only the wiring, not the coercion logic.

- [ ] **Step 1: Write failing tests** (real code)

```python
# tests/emitters/python/test_types.py (add)
def test_int64_format_keeps_int_and_names_a_coercer():
    from refract.ir.types import ScalarType
    rendered = PythonTypeMapper().render(ScalarType(scalar="integer", format="int64"), optional=False)
    assert rendered.text == "int"
    assert rendered.coercer == "coerce_int64"


def test_rfc2822_format_swaps_to_datetime():
    from refract.ir.types import ScalarType
    rendered = PythonTypeMapper().render(ScalarType(scalar="string", format="rfc2822"), optional=False)
    assert rendered.text == "datetime"
    assert ("datetime", "datetime") in {(i.module, i.name) for i in rendered.imports}


def test_unknown_format_is_a_noop():
    from refract.ir.types import ScalarType
    rendered = PythonTypeMapper().render(ScalarType(scalar="integer", format="weird"), optional=False)
    assert rendered.text == "int" and rendered.coercer is None
```

```python
# tests/emitters/python/test_resolve.py (add)
def test_int64_field_wraps_annotated_before_validator():
    from refract.ir import Field
    from refract.ir.types import ScalarType
    line, imports = _model_field(Field(name="cores", type=ScalarType(scalar="integer", format="int64")), PythonTypeMapper())
    assert line == "    cores: Annotated[int, BeforeValidator(coerce_int64)] = None"
    assert {("pydantic", "BeforeValidator"), ("typing", "Annotated")} <= {(i.module, i.name) for i in imports}
```

- [ ] **Step 2: Run to verify failure** -> FAIL (`RenderedType` has no `coercer`; `_base` ignores `.format`).

- [ ] **Step 3: Implement** - add `coercer` to `RenderedType`; thread it through `render`'s optional wrap (like `discriminator`); add the registry + scalar-arm lookup in `_base`; wrap in `_model_field`; add the shared-base import in `resolve_models` (walk `res.models` fields, render each, collect coercer names, `Import(_shared_models_module(ctx), name)`). Note that `_model_field`'s optional path renders `Annotated[int, BeforeValidator(coerce_int64)] | None = None` - the `| None` is applied by `render` OUTSIDE the coercer base text, which `_model_field` then wraps; verify ordering with a test on an optional int64 field.

Interaction with Task 5: `coercer` and `discriminator` never co-occur on one field (`format` is rejected on non-scalars, and a union is not a scalar), so `_model_field` handles them as independent branches - assert this in a comment, not code.

- [ ] **Step 4: Run to verify pass + gate** - Run: `uv run pytest -q && uv run refract generate --check && uv run ruff check . && uv run ty check` -> PASS; `--check` exit 0.

- [ ] **Step 5: Behavioral proof** (opt-in) - a fixture model with an `int64` field; supply a hand-written `coerce_int64` in the test's shared-base stub; generate + import the model; assert `Model.model_validate({"cores": "123"}).cores == 123` (JSON STRING -> Python `int`). Mark `@pytest.mark.behavioral`.

- [ ] **Step 6: Commit**

```bash
git add src/refract/emitters/api.py src/refract/emitters/python/types.py src/refract/emitters/python/resolve.py tests/
git commit -m "feat(emit): scalar-format coercion via Annotated[..., BeforeValidator(...)] (int64, rfc2822)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Shared-models spec file + loader entry point + `Resource.shared_models` + collision fail-loud (defaults D, E-load-side)

**Files:**
- Modify: `src/refract/spec/nodes.py` (new `SharedModelsSpec(models: list[ModelSpec])`)
- Modify: `src/refract/spec/loader.py` (new `SpecLoader.load_shared_models(path) -> tuple[ir.Model, ...]`)
- Modify: `src/refract/ir/model.py` (`Resource.shared_models: tuple[Model, ...] = ()`; `Resource.model()` `:147-151` local-first fallback to shared)
- Modify: `src/refract/generation.py` (`find_shared_models`; `Generator.plan` `:65-79` loads `_models.yaml`, attaches to every resource with a collision check)
- Test: `tests/spec/test_loader.py`, `tests/ir/test_model.py`, `tests/test_generation.py`

**Interfaces:**
- Consumes: a new top-level `_models.yaml` sibling to `client.yaml` (mirrors `find_client_config`, `generation.py:27-32`), reusing the EXACT `nodes.ModelSpec` shape.
- Produces:
  ```python
  # nodes.py
  class SharedModelsSpec(_Spec):
      models: list[ModelSpec] = Field(default_factory=list)

  # loader.py (mirrors load_client_config, loader.py:228-235)
  @staticmethod
  def load_shared_models(path: Path) -> tuple[ir.Model, ...]:
      raw = _read_mapping(path)
      spec = nodes.SharedModelsSpec.model_validate(raw)   # wrap ValidationError -> SpecError
      return _synthesize_discriminators(tuple(_model(m) for m in spec.models), spec.models)

  # ir/model.py
  class Resource(_IR):
      # (domain, resource, security, models, operations, documentation, module_docs - existing, unchanged)
      shared_models: tuple[Model, ...] = ()
      def model(self, name: str) -> Model:
          for candidate in self.models:
              if candidate.name == name:
                  return candidate
          for candidate in self.shared_models:
              if candidate.name == name:
                  return candidate
          raise KeyError(name)

  # generation.py - a fail-loud attach helper
  def _attach_shared(res: ir.Resource, shared: tuple[ir.Model, ...]) -> ir.Resource:
      collisions = {m.name for m in res.models} & {m.name for m in shared}
      if collisions:
          raise SpecError(f"{res.resource}: model name(s) {sorted(collisions)} defined both locally and in _models.yaml")
      return res.model_copy(update={"shared_models": shared})
  ```
  `Generator.plan` (`generation.py:65-79`) globs `_models.yaml` ONCE (optional - absent means `shared=()`), loads it, and wraps each `SpecLoader.load(spec_path)` in `_attach_shared(..., shared)`. Local-first lookup (D): a name in local `models:` wins; a name only in shared resolves via the fallback; a name in BOTH is rejected eagerly at plan time.

- [ ] **Step 1: Write failing tests** (real code)

```python
# tests/ir/test_model.py (add)
def test_model_falls_back_to_shared():
    from refract.ir import ObjectModel, Resource
    meta = ObjectModel(name="ObjectMeta")
    res = Resource(domain="k8s", resource="pods", security="tok", models=(), operations=(), shared_models=(meta,))
    assert res.model("ObjectMeta") is meta


def test_local_wins_over_shared_is_not_reached_because_collision_is_rejected():
    """`model()` is local-first: a name defined locally resolves to the LOCAL model; a name only in
    shared resolves via the fallback. A name in BOTH never reaches `model()` - it is rejected at
    plan time by `_attach_shared` (see `test_attach_shared_rejects_name_collision`), so there is no
    runtime "local wins" ambiguity to test - only these two non-colliding paths."""
    from refract.ir import ObjectModel, Resource
    local = ObjectModel(name="Priority")
    shared = ObjectModel(name="ObjectMeta")
    res = Resource(
        domain="k8s", resource="pods", security="tok",
        models=(local,), operations=(), shared_models=(shared,),
    )
    assert res.model("Priority") is local      # local-defined name resolves locally
    assert res.model("ObjectMeta") is shared    # shared-only name resolves via the fallback


# tests/test_generation.py (add)
def test_attach_shared_rejects_name_collision():
    import pytest

    from refract.generation import _attach_shared
    from refract.ir import ObjectModel, Resource
    from refract.spec import SpecError

    res = Resource(
        domain="k8s", resource="pods", security="tok",
        models=(ObjectModel(name="ObjectMeta"),), operations=(),
    )
    with pytest.raises(SpecError, match="defined both locally and in _models.yaml"):
        _attach_shared(res, (ObjectModel(name="ObjectMeta"),))

# tests/spec/test_loader.py (add)
def test_load_shared_models(tmp_path):
    p = tmp_path / "_models.yaml"
    p.write_text("models:\n  - name: ObjectMeta\n    fields:\n      - {name: name, type: string, optional: true}\n")
    from refract.spec.loader import SpecLoader
    shared = SpecLoader.load_shared_models(p)
    assert shared[0].name == "ObjectMeta"
```

- [ ] **Step 2: Run to verify failure** -> FAIL.

- [ ] **Step 3: Implement** the node, loader entry point, `Resource.shared_models` + fallback, `find_shared_models` (returns `Path | None`), `_attach_shared`, and `Generator.plan` threading. Keep `_synthesize_discriminators` (Task 6) reused in `load_shared_models` so a shared discriminated union is also synthesized.

- [ ] **Step 4: Run to verify pass + gate** - Run: `uv run pytest -q && uv run refract generate --check && uv run ruff check . && uv run ty check` -> PASS; `--check` exit 0 (ycli has no `_models.yaml`, so `shared=()` and every resource is byte-identical). Adding a defaulted `shared_models=()` slot to `Resource` must NOT change any `model_dump`-driven output.

- [ ] **Step 5: Commit**

```bash
git add src/refract/spec/nodes.py src/refract/spec/loader.py src/refract/ir/model.py src/refract/generation.py tests/
git commit -m "feat(spec): shared _models.yaml + cross-file ref resolution (local-first, fail-loud on collision)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Shared-models emission tier (default E: per-domain `DomainEmitter`)

**Files:**
- Modify: `src/refract/emitters/api.py` (`DomainEmitter` gains a non-abstract `applies(resources) -> bool` defaulting `True`)
- Modify: `src/refract/generation.py` (`render_domain` `:54-63` gates on `surface.applies(resources)`)
- Modify: `src/refract/emitters/python/layout.py` (`path` `:22-30` maps `"shared_models"` -> `{domain}/shared_models.py`)
- Create: `src/refract/emitters/python/surfaces/shared_models.py` (`SharedModelsSurface(DomainEmitter)`, `name = "shared_models"`, `applies = bool(resources[0].shared_models)`)
- Modify: `src/refract/emitters/python/resolve/models.py` (new `resolve_shared_models(...)`, reusing `_model_class`; `resolve_models` adds `Import(f"{ctx.package_root}.shared_models", target)` for a field whose ref target is a SHARED model). Re-export `resolve_shared_models` from `resolve/__init__.py`.
- Modify: `src/refract/emitters/python/backend.py` (`domain_surfaces` `:47` gains `SharedModelsSurface(*parts)`)
- Modify: `src/refract/emitters/python/templates/` (reuse `models.jinja` - `resolve_shared_models` returns a `ModelsPageView`)
- Test: `tests/emitters/python/surfaces/test_shared_models.py` (create), `tests/test_generation.py`

**Interfaces:**
- Consumes: `resources[0].shared_models` (identical across a domain, per Task 9's `_attach_shared`).
- Produces:
  ```python
  def resolve_shared_models(resources: tuple[ir.Resource, ...], ctx: EmitContext,
                            naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings) -> ModelsPageView:
      """Emit resources[0].shared_models ONCE (a DomainEmitter, run per-domain). Reuses _model_class."""
  ```
  Emitted to `{domain}/shared_models.py` (module `{ctx.package_root}.shared_models`). A consuming resource's `models.py` that has a field of type `ref<ObjectMeta>` (where `ObjectMeta` is shared, not local) imports it via `Import(f"{ctx.package_root}.shared_models", "ObjectMeta")` - `resolve_models` decides local-vs-shared by membership in `res.shared_models` (a same-file local ref needs NO import; a shared ref does). `applies` returns False when `shared_models` is empty, so no empty file is emitted.

- [ ] **Step 1: Write failing tests** (real code)

```python
# tests/emitters/python/surfaces/test_shared_models.py (create)
def test_shared_models_emitted_once_across_two_resources(python_backend, two_resources_sharing_objectmeta, client_config):
    from refract.generation import Generator
    plan = Generator(python_backend).plan(...)   # or render_domain directly
    shared_files = [p for p in plan if p.name == "shared_models.py"]
    assert len(shared_files) == 1                                  # ObjectMeta emitted ONCE
    assert "class ObjectMeta" in plan[shared_files[0]]
    for p, content in plan.items():
        if p.name == "models.py":
            assert "class ObjectMeta" not in content              # never re-defined per-resource


def test_shared_models_surface_omitted_when_no_shared_models(python_backend, priorities_resource, client_config):
    files = Generator(python_backend).render_domain((priorities_resource,), client_config)
    assert not any(p.endswith("shared_models.py") for p in files)  # applies() False arm


def test_resource_referencing_shared_model_imports_from_shared_module():
    """A resource whose field type is `ref<ObjectMeta>` (ObjectMeta shared, NOT local): its models.py
    imports ObjectMeta from `<package_root>.shared_models`, not from `.models`."""
    from refract.emitters.api import EmitContext
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.resolve import resolve_models
    from refract.emitters.python.types import PythonTypeMapper
    from refract.ir import Field, ObjectModel, Resource
    from refract.ir.types import RefType

    meta = ObjectModel(name="ObjectMeta")
    pod = ObjectModel(name="Pod", fields=(Field(name="metadata", type=RefType(target="ObjectMeta")),))
    res = Resource(domain="k8s", resource="pods", security="tok",
                   models=(pod,), operations=(), shared_models=(meta,))
    ctx = EmitContext(package_root="ycli.yandex.k8s")
    page = resolve_models(res, ctx, PythonNaming(), PythonTypeMapper(), PythonDocstrings())
    assert "from ycli.yandex.k8s.shared_models import ObjectMeta" in page.import_lines
```

- [ ] **Step 2: Run to verify failure** -> FAIL (`resolve_shared_models`/`SharedModelsSurface` do not exist).

- [ ] **Step 3: Implement** the `DomainEmitter.applies` default, `render_domain` gate, layout entry, surface class, `resolve_shared_models`, `resolve_models` shared-import logic, backend registration. `resolve_models` shared-import: after `_model_field` returns, for each field, walk its neutral type for `RefType` targets, and if `target in {m.name for m in res.shared_models}`, add `Import(f"{ctx.package_root}.shared_models", target)`. (Reuse Task 11's `_referenced_model_names` walker - which lives in `resolve/_common.py` after the Task 1 split - for this once it exists; if Task 11 lands first, prefer that; otherwise a local one-level scan suffices for the k8s embedded-`ObjectMeta` anchor and the walker adoption is a rule-of-three follow-up.)

- [ ] **Step 4: Run to verify pass + gate** - Run: `uv run pytest -q && uv run refract generate --check && uv run ruff check . && uv run ty check` -> PASS; `--check` exit 0 (ycli has no shared models; `render_domain` still emits only `root_client`). NOTE: adding `SharedModelsSurface` to `domain_surfaces` must NOT change ycli output - the `applies` gate keeps it silent.

- [ ] **Step 5: Commit**

```bash
git add src/refract/emitters/api.py src/refract/generation.py src/refract/emitters/python/ tests/
git commit -m "feat(emit): per-domain shared-models emission tier (ObjectMeta emitted once, imported cross-file)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

Scope note (deferred, OWNER-OVERRIDABLE E-alt): CROSS-domain sharing (YC `Operation` reused across compute/vpc/iam) would need a THIRD tier above `DomainEmitter`, run once per `Generator.plan`. Not built here (no committed cross-domain consumer this phase - YC is P1's anchor for scalar formats only). Shared BODY / RESPONSE models (a shared model named by `op.body`/`response_model`, vs. an embedded field ref) are likewise a follow-up: this task covers the embedded-field anchor only.

---

### Task 11: M1 - `_referenced_model_names` shared walker + `_body_test_imports` recursion fix

**Files:**
- Modify: `src/refract/emitters/python/resolve/_common.py` (new `_referenced_model_names` - a 2+-surface helper - re-exported from `resolve/__init__.py`)
- Modify: `src/refract/emitters/python/resolve/tests.py` (`_body_test_imports` uses the walker)
- Modify: `src/refract/emitters/python/resolve/cli.py` (`_assembled_options` adopts the walker for import assembly ONLY)
- Test: `tests/emitters/python/test_resolve.py`; behavioral in `tests/behavioral/`

**Interfaces:**
- Consumes: an `ObjectModel` + its `ir.Resource` (for `res.model(name)` target resolution, now shared-aware post-Task 9).
- Produces:
  ```python
  def _referenced_model_names(model: ObjectModel, res: ir.Resource) -> tuple[str, ...]:
      """Every model name transitively reachable from `model`'s fields via RefType - unwraps
      ListType/MapType/UnionType at any depth, recurses into each referenced ObjectModel's own
      fields. De-duplicated, first-seen order; a `seen` set guards a structural cycle
      (ObjectMeta-style) from infinite recursion. Recursive self-referential UNIONS are out of
      scope (Q3), but the cycle-guard ships defensively regardless (open question H)."""
  ```
  `_body_test_imports` becomes `[Import(models_module, body.model)] + [Import(models_module, name) for name in _referenced_model_names(model, res)]` when the body is an `ObjectModel` - the actual bug fix: a `list<ref<Item>>` (or a `oneof:` union) body field now imports `Item`/`A`/`B`, where today only a DIRECT `RefType` field is imported (`_body_test_imports` in `resolve/tests.py`). `_assembled_options` adopts the same walker purely for its import ASSEMBLY (NOT its flatten-or-reject decision, which stays as-is: a list/map/deep-ref body field still raises the `handler:` escape hatch).

- [ ] **Step 1: Write failing tests** (real code)

```python
# tests/emitters/python/test_resolve.py (add - the module already has `from refract import ir`,
# `from refract.emitters.api import ... Import`, and `from refract.emitters.python import resolve`)
def test_referenced_names_unwraps_list_of_ref():
    from refract.ir.types import ListType, RefType
    item = ir.ObjectModel(name="Item", fields=(ir.Field(name="v", type=RefType(target="Leaf")),))
    leaf = ir.ObjectModel(name="Leaf")
    widget = ir.ObjectModel(name="Widget", fields=(ir.Field(name="items", type=ListType(item=RefType(target="Item"))),))
    res = ir.Resource(domain="d", resource="r", security="t", models=(widget, item, leaf), operations=())
    assert resolve._referenced_model_names(widget, res) == ("Item", "Leaf")   # recurses INTO Item -> Leaf


def test_referenced_names_guards_a_cycle():
    """An A -> B -> A structural cycle resolves without infinite recursion, each named once."""
    from refract.ir.types import RefType
    a = ir.ObjectModel(name="A", fields=(ir.Field(name="b", type=RefType(target="B")),))
    b = ir.ObjectModel(name="B", fields=(ir.Field(name="a", type=RefType(target="A")),))
    res = ir.Resource(domain="d", resource="r", security="t", models=(a, b), operations=())
    assert resolve._referenced_model_names(a, res) == ("B", "A")   # each once; the `seen` guard stops the loop


def test_body_test_imports_includes_nested_list_ref():
    """A body model with a `list<ref<Item>>` field -> `_body_test_imports` now includes Item
    (today only a DIRECT `ref<...>` field is imported)."""
    from refract.ir.types import ListType, RefType
    item = ir.ObjectModel(name="Item")
    widget = ir.ObjectModel(name="Widget", fields=(ir.Field(name="items", type=ListType(item=RefType(target="Item"))),))
    res = ir.Resource(domain="d", resource="r", security="t", models=(widget, item), operations=())
    module = "ycli.yandex.d.r.models"
    imports = resolve._body_test_imports(res, ir.Body(model="Widget"), module)
    assert Import(module, "Item") in imports
    assert Import(module, "Widget") in imports
```

- [ ] **Step 2: Run to verify failure** -> FAIL (`_referenced_model_names` missing; `_body_test_imports` skips nested refs).

- [ ] **Step 3: Implement** the recursive walker in `resolve/_common.py` (a nested-type unwrapper over `RefType`/`ListType`/`MapType`/`UnionType`, resolving each `RefType.target` via `res.model(...)` and recursing into `ObjectModel` targets, with a `seen: set[str]` guard; DO NOT seed `seen` with the start model's name, so a cyclic self-reference is still listed once). Re-export `_referenced_model_names` from `resolve/__init__.py` (the tests reach it through the `resolve` namespace). Rewire `_body_test_imports` (`resolve/tests.py`) and adopt the walker in `_assembled_options`' (`resolve/cli.py`) import assembly. Keep `_assembled_options`' reject arms unchanged.

- [ ] **Step 4: Run to verify pass + gate** - Run: `uv run pytest -q && uv run refract generate --check && uv run ruff check . && uv run ty check` -> PASS; `--check` exit 0 (priorities' one-level `PriorityCreate` -> `LocalizedName` walk yields the same single import it does today).

- [ ] **Step 5: Behavioral proof** (opt-in) - a resource with a `list<ref<Item>>` body whose generated CLIENT test's `call` constructs `Widget(items=[Item(...)])`; `ast.parse` + a collection-only import of the generated test module raises NO `NameError` (today: latent `NameError`). Mark `@pytest.mark.behavioral`.

- [ ] **Step 6: Commit**

```bash
git add src/refract/emitters/python/resolve.py tests/
git commit -m "fix(emit): recursive body-model ref-walk for test imports (list/map/union at any depth)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage (artifacts/18 section 7 - its 12 type-foundation items mapped onto the renumbered tasks; Task 1 is P0 finding A3, NOT one of those 12):**

| artifacts/18 item | Plan task | Covered |
|---|---|---|
| (P0 finding A3: `resolve.py` surface split) | Task 1 | Yes - pre-P1 debt paid first (not an artifacts/18 item) |
| 1 `UnionType` node + `NeutralType` widen | Task 2 | Yes |
| 2 undiscriminated grammar (`oneOf<A\|B>`) | folded into the single `OneOfSpec` task (Variant 2) - Task 4 | Folded - NO compact string grammar; undiscriminated unions are authored via the same structured `oneof:` (discriminator omitted) |
| 3 undiscriminated lowering | Task 3 | Yes |
| 4 `OneOfSpec` + discriminated grammar | Task 4 | Yes |
| 5 `RenderedType.discriminator` + unified `Field(...)` | Task 5 | Yes |
| 6 loader `Literal[tag]` synthesis (default B) | Task 6 (folds in `LiteralType` - no consumer before synthesis, so YAGNI keeps them one task) | Yes |
| 7 `ScalarType.format` + loader | Task 7 | Yes |
| 8 format coercion lowering (default G) | Task 8 | Yes |
| 9 shared `_models.yaml` + `Resource.shared_models` + collision (defaults D, E-load) | Task 9 | Yes |
| 10 shared-models emission tier (default E) | Task 10 | Yes |
| 11 M1 recursive ref-walker | Task 11 | Yes |
| 12 M2 cross-identifier dedup | done in P0 (commit `43203a5`, finding I1) - no P1 work | Done in P0 |

Anchors requested by the brief all appear as concrete test cases: Notion-style discriminated block union (Task 6 synthesis tests + behavioral), a mixed-type undiscriminated union (Task 4 `string` + `ref<Customer>`), k8s `ObjectMeta` shared ref (Tasks 9-10), YC int64-as-string (Tasks 7-8), `list<ref<X>>` body for M1 (Task 11). The M2 anchor - `id`(body)+`id`(path) collision - is already CLOSED in P0 (commit `43203a5`, finding I1: `_cli_write_parts` rejects a body-option vs path/query name clash), so no P1 task re-does it.

**Dependency order:** Task 1 (the `resolve.py` surface split) lands FIRST - a pure refactor that pays the A3 debt before P1 grows the file, and Tasks 5/8/10/11 all touch the split modules. Then the union chain: 2 (`UnionType` node) -> 3 (undiscriminated lowering, IR-level) -> 4 (structured `oneof:` spec surface, BOTH kinds) -> 5 (discriminated lowering + `_model_field` assembly) -> 6 (`LiteralType` + tag synthesis + runtime proof). 7 -> 8 (scalar formats) and 9 -> 10 (cross-file) are each independent of the union chain and of each other - parallelizable after Task 1. Task 11 (M1) depends only on Task 1 (its walker lives in `resolve/_common.py`); the union tasks are its MOTIVATION, not a sequencing prereq. Task 10 optionally reuses Task 11's walker if 11 lands first (noted inline). M2 is already done in P0, so it is not a task.

**Placeholder scan:** every task step carries real code - NO bare `...`, no "TBD", no "similar to Task N". Task 1's split is pinned by an explicit helper-placement TABLE + a re-export-shim sketch; Tasks 6/9/10/11's previously-stubbed test bodies are now fully inlined (each fixture models the me/priorities `resource.yaml` shapes). The `__FIELD__` splice token in Task 5's `_model_field` sketch is an implementation aid, not a placeholder - the test pins the exact emitted string; the implementer may build the string without it. The `cast(RefType, ...)` in Task 6's synthesis is a deliberate narrowing (see open question J), not a stub.

**Type-consistency across tasks:**
- Task 1 turns `resolve.py` into a `resolve/` PACKAGE whose `__init__.py` re-exports the FULL prior public + test-reached surface, so no later task's `from refract.emitters.python.resolve import ...` (surfaces, backend, or tests) breaks. `py_str`/`render_imports`/`signature_and_call`/etc. move to `resolve/_common.py`; `_model_field` to `resolve/models.py`; the M1 walker (Task 11) is authored directly in `resolve/_common.py`.
- `RenderedType` is extended twice by design: `discriminator: str | None` (Task 5) then `coercer: str | None` (Task 8) - both narrow named fields (default C), both threaded through `render`'s optional-wrap so neither is dropped. Consistent, non-conflicting (a field is never both discriminated and format-coerced: format is scalar-only, a union is not scalar).
- `_model_field(field, type_mapper) -> tuple[str, list[Import]]` (in `resolve/models.py`) keeps its signature across Tasks 5 and 8; only its body grows two independent branches. Its callers (`_model_class`, `resolve_models`) are unaffected.
- `NeutralType` is widened twice: `+ UnionType` (Task 2), `+ LiteralType` (Task 6). `_base`'s match gains one arm per new member; `assert_never`/`case _:` stay excluded from coverage.
- `_assembled_options` return arity is UNCHANGED by P1: the M2 cross-source dedup (finding I1) already ships in P0 by parsing decl names inside `_cli_write_parts` (it did NOT switch `_assembled_options` to a 4-tuple), so P1 leaves the 3-tuple as-is; Task 11 changes only its import-assembly internals (walker adoption), not the return arity.
- `Resource.model(name) -> Model` keeps its signature (Task 9) and gains a shared fallback; every existing call site (in `resolve/cli.py` and `resolve/tests.py`, plus Task 11's walker) is unchanged - the reason default-mechanism A was chosen over threading a new `ctx` lookup.

**Gate consistency:** every task ends on `refract generate --check` exit 0 because P1 adds CAPABILITY without changing the ycli me/priorities snapshot (no ycli spec uses `oneof`/`format`/`_models.yaml`; Task 1 is a source-only refactor with byte-identical output); the only in-repo output changes would come from NEW fixtures, which live under `tests/` (behavioral) or a NEW example, not the committed `out/` L1 corpus. If any task's implementer finds ycli output drifting, that is a regression to investigate, not a snapshot to bless.

**Open questions still owner-facing at execution (flag before starting):** A, D, E (adopted defaults above - override here changes Task 4, 9, 10 respectively); B, C, G (secondary defaults - override changes Tasks 6, 5/8, 8); F (does the tests emitter need a minimal "don't generate an invalid mixed-variant fixture" guard now, or is "tests emitter stays naive about unions until P3" an accepted documented gap?); H (recursion boundary re-confirmation - the defensive cycle-guard in Task 11 ships regardless); J (Variant-2 reconciliation: Task 4's `_oneof_type` validates "discriminated variant must be a `ref<Model>`" AND Task 6's synthesis re-parses the same expr for `.target` - synthesis uses `cast(RefType, ...)`, NOT an isinstance branch, precisely because `_oneof_type` already rejected non-refs, so a re-check there would be a dead, uncoverable branch under the 100% branch gate; if the owner prefers a single validation point, move the ref-check wholly into synthesis and drop it from `_oneof_type`, then Task 4's "must be a ref" test moves to Task 6). F, H, J are not blocking any task as drafted.
