# refract P0 (debt-zero) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every genuine open emitter debt (D1 multi-op tests, D2+D4 204/first-2xx, D3 no-facet surface-gate coverage, D5 Assembled-CLI write commands) so later axis phases build on a debt-free emitter.

**Architecture:** Pure additions to the redesign's neutral-IR pipeline: spec frontend (`nodes`/`loader`) gains optional response models + first-2xx selection; runtime `Session.send`/`Request` gain a bodyless return; the Python resolvers (`resolve.py`) gain a `-> None` branch and an Assembled-CLI write-command path. No core redesign; the read/write split on `op.body is not None` is untouched.

**Tech Stack:** Python 3.12/3.13, pydantic v2 (frozen IR), Jinja2 templates, Typer CLI, httpx runtime, pytest + responses, ruff + ty, uv.

## Global Constraints

Copied verbatim from the milestone spec and the project's established gates. Every task's requirements implicitly include this section.

- Coverage gate is `--cov-fail-under=100` (line AND branch); NO `# pragma: no cover`. A fail-loud guard that is genuinely reachable gets a unit test that triggers it; a genuinely unreachable one is refactored away, not pragma'd.
- `uv run ruff format --check .` + `uv run ruff check .` + `uv run ty check` MUST be clean (ty pinned `==0.0.59`). Mechanical fixes go through `ruff --fix` / `ruff format`, never hand-applied.
- `uv run refract generate --check` MUST exit 0 (the committed `examples/ycli-tracker/out/` L1 snapshot is drift-free). When a task changes emitted output, regenerate the snapshot with `uv run refract generate --write` IN THE SAME TASK and commit the `out/` delta.
- Behavioral tests are opt-in (`@pytest.mark.behavioral`, excluded by default via `-m 'not behavioral'`); run them explicitly with `uv run pytest -m behavioral`.
- Emitted code is ENGLISH-only: no Russian text, and no Cyrillic section-ref abbreviations (transliterated: "razd." / "razdel") in generated output or source comments.
- Fail loud: reject at the cause with `raise` (never `assert` for control flow; `-O` strips asserts). Free-text literals in emitted code go through `py_str` (resolve.py:70).
- IR is frozen pydantic; illegal states unrepresentable (discriminated unions). Do not widen a type without a spec-shaped reason.
- Conventional Commits; end each commit message with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Commit only on the `feat/axis-registries` branch.
- File artifacts are ASCII (`->` not arrows, `-` not em-dash).

---

### Task 1: D4+D2a - first-2xx response selection + optional response model (spec frontend)

**Files:**
- Modify: `src/refract/spec/nodes.py:48-49` (`ResponseSpec.model` -> optional)
- Modify: `src/refract/spec/loader.py:133-137` (`_response_model` -> first-2xx, returns `str | None`)
- Test: `tests/spec/test_loader.py`

**Interfaces:**
- Consumes: `nodes.ResponseSpec`, `nodes.OperationSpec.responses: dict[int, ResponseSpec]`.
- Produces: `_response_model(name: str, responses: dict[int, nodes.ResponseSpec]) -> str | None` - returns the model of the FIRST 2xx status (ascending), which may be `None` for a bodyless status; raises `SpecError` only when NO 2xx status exists. `ir.Operation.response_model` therefore becomes legitimately `None` for a 204/201-only op.

- [ ] **Step 1: Write failing tests**

```python
# tests/spec/test_loader.py (add)
import pytest
from refract.spec.loader import SpecError, _response_model
from refract.spec import nodes


def _resp(model: str | None) -> nodes.ResponseSpec:
    return nodes.ResponseSpec(model=model)


def test_response_model_prefers_first_2xx():
    responses = {201: _resp("Created"), 200: _resp("Ok")}
    assert _response_model("op", responses) == "Ok"  # 200 < 201


def test_response_model_none_for_bodyless_2xx():
    assert _response_model("delete", {204: _resp(None)}) is None


def test_response_model_no_2xx_raises_spec_error():
    with pytest.raises(SpecError, match="no 2xx response"):
        _response_model("op", {404: _resp("Error")})
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/spec/test_loader.py -k response_model -q`
Expected: FAIL (`ResponseSpec.model` required rejects `None`; `_response_model` still hardcodes 200).

- [ ] **Step 3: Implement**

```python
# src/refract/spec/nodes.py - ResponseSpec
class ResponseSpec(_Spec):
    model: str | None = None  # None => bodyless success (204/201-no-content)
```

```python
# src/refract/spec/loader.py - replace _response_model
def _response_model(name: str, responses: dict[int, nodes.ResponseSpec]) -> str | None:
    """The first-2xx success model name, or None for a bodyless success. SpecError if no 2xx."""
    success = [status for status in responses if 200 <= status < 300]
    if not success:
        raise SpecError(f"operation {name!r} has no 2xx response")
    return responses[min(success)].model
```

- [ ] **Step 4: Run to verify pass + full gate**

Run: `uv run pytest tests/spec/test_loader.py -q && uv run ruff check . && uv run ty check`
Expected: PASS, clean. NOTE: the existing `test_operation_without_200_response_raises_spec_error` matches `"'get' has no 200 response"` - update its `match=` to `"no 2xx response"` (the new message), and rename the test to `..._without_2xx_...` if desired. Its fixture (only a 404) still triggers the SpecError.

- [ ] **Step 5: Commit**

```bash
git add src/refract/spec/nodes.py src/refract/spec/loader.py tests/spec/test_loader.py
git commit -m "feat(spec): first-2xx response selection + optional bodyless response model

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: D2b - runtime `Request`/`Session.send` accept a bodyless (None) response model

**Files:**
- Modify: `src/refract/runtime/request.py:15` (`response_model: type[T] | None`)
- Modify: `src/refract/runtime/session.py:23-35` (`send` returns `T | None`; None + empty body -> None)
- Test: `tests/runtime/test_session.py` (create)

**Interfaces:**
- Consumes: `httpx.Client` (stubbed via `MockTransport`), `Request`.
- Produces: `Request(method, path, response_model: type[T] | None, ...)`; `Session.send(request: Request[T]) -> T | None` - when `response_model is None`, `send` still does `raise_for_status()` then returns `None` (the bodyless-op contract).

- [ ] **Step 1: Write failing test**

```python
# tests/runtime/test_session.py (create)
import httpx
from pydantic import BaseModel
from refract.runtime.request import Request
from refract.runtime.session import Session


class _Widget(BaseModel):
    id: int


def _session(handler) -> Session:
    return Session("https://api.demo/v1", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_send_parses_model():
    session = _session(lambda req: httpx.Response(200, json={"id": 1}))
    result = session.send(Request(method="GET", path="widget", response_model=_Widget))
    assert isinstance(result, _Widget) and result.id == 1


def test_send_returns_none_for_bodyless_op():
    session = _session(lambda req: httpx.Response(204))
    result = session.send(Request(method="DELETE", path="widget/1", response_model=None))
    assert result is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/runtime/test_session.py -q`
Expected: FAIL (`response_model=None` then `model.model_validate` -> AttributeError on None).

- [ ] **Step 3: Implement**

```python
# src/refract/runtime/request.py:15
    response_model: type[T] | None
```

```python
# src/refract/runtime/session.py - send
    def send(self, request: Request[T]) -> T | None:
        params = {k: v for k, v in (request.query or {}).items() if v is not None}
        response = self._client.request(
            request.method,
            f"{self._base_url}/{request.path}",
            params=params or None,
            json=request.json_body,
        )
        response.raise_for_status()
        model = request.response_model
        if model is None:  # bodyless success (204/201-no-content) -> no parse
            return None
        return model.model_validate(response.json())
```

- [ ] **Step 4: Run to verify pass + gate**

Run: `uv run pytest tests/runtime/test_session.py -q && uv run ty check`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add src/refract/runtime/request.py src/refract/runtime/session.py tests/runtime/test_session.py
git commit -m "feat(runtime): Session.send returns None for a bodyless (response_model=None) request

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: D2c - resolvers emit `-> None` for a bodyless op (requests / client / mcp)

**Files:**
- Modify: `src/refract/emitters/python/resolve.py` - `_request_function` (~121-150), `_client_method` (~177-201), `_mcp_tool` (~438), `resolve_mcp` import gate (~481 already conditional)
- Test: `tests/emitters/test_resolve_bodyless.py` (create)

**Interfaces:**
- Consumes: `ir.Operation` with `response_model=None`.
- Produces: for a bodyless op, `_request_function` emits `-> Request[None]` with `response_model=None` and NO `.models` response import; `_client_method` emits `-> None`; `_mcp_tool` signature ends `-> None`. Removes the two fail-loud `raise ValueError("... no response model ...")` guards (resolve.py:131-132, 194-195) - they are now reachable-legal, not errors.

- [ ] **Step 1: Write failing tests**

```python
# tests/emitters/test_resolve_bodyless.py (create)
from refract import ir
from refract.emitters.python.docstrings import PythonDocstrings
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.resolve import _client_method, _request_function
from refract.emitters.python.types import PythonTypeMapper

_PARTS = (PythonNaming(), PythonTypeMapper(), PythonDocstrings())
_DELETE = ir.Operation(name="delete", method="DELETE", path="widget/{id}",
                       operation_id="widget_delete", response_model=None,
                       params=(ir.Param(name="id", loc="path", type=ir.types.ScalarType(scalar="string")),))


def test_request_function_bodyless_returns_request_none():
    text, imports = _request_function(_DELETE, *_PARTS)
    assert "-> Request[None]:" in text
    assert "response_model=None" in text
    assert not any(imp.name == "None" for imp in imports)  # no `.models` import for None


def test_client_method_bodyless_returns_none():
    text, _ = _client_method(_DELETE, *_PARTS)
    assert "-> None:" in text
```

(Adjust the `ir.types` import to `from refract.ir.types import ScalarType` per the repo idiom.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/emitters/test_resolve_bodyless.py -q`
Expected: FAIL (current code raises `ValueError` when `response_model is None`).

- [ ] **Step 3: Implement** - in `_request_function`, replace the fail-loud guard:

```python
    response_model = op.response_model
    if response_model is None:  # bodyless op (204/201) -> Request[None], no response import
        return_type, response_kwarg = "None", "response_model=None"
    else:
        imports.append(Import(".models", response_model))
        return_type, response_kwarg = response_model, f"response_model={response_model}"
    function_name = naming.module_function(op.name)
    param_list = ", ".join(params)
    sig = f"def {function_name}({param_list}) -> Request[{return_type}]:"
    ...
    kwargs.append(response_kwarg)
```

In `_client_method`, replace its guard symmetrically (`return_type = response_model or "None"`; only append the `.models` import when non-None). In `_mcp_tool`, change `-> {op.response_model}` to `-> {op.response_model or 'None'}`. `resolve_mcp`'s response import is already conditional (`if op.response_model:` resolve.py:481) - no change.

- [ ] **Step 4: Run to verify pass + FULL gate + snapshot**

Run: `uv run pytest -q && uv run refract generate --check && uv run ruff check . && uv run ty check`
Expected: PASS; `--check` exit 0 (me/priorities unchanged - they have response models); clean. NOTE: this removes previously-covered `raise ValueError` lines; the guard-trigger tests added in the redesign for those raises must be DELETED in this task (they now assert removed behavior) - grep `no response model` in tests and remove those two cases.

- [ ] **Step 5: Commit**

```bash
git add src/refract/emitters/python/resolve.py tests/
git commit -m "feat(emit): resolvers emit -> None for a bodyless (response_model=None) op

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: D2 proof - a real bodyless op runs end-to-end (behavioral + resolver unit)

**Files:**
- Modify: `tests/behavioral/test_d_core_runs.py` (add a `delete` op returning 204 to the synthetic `_WIDGET`)
- Test: same file (behavioral)

**Interfaces:**
- Consumes: `RequestsSurface`/`ClientSurface`/`RootClientSurface`, `refract.runtime`, the Task 1-3 changes.
- Produces: behavioral proof that a generated `delete` builder + client method import and run, and that `client.widget.delete("1")` returns `None` while the DELETE reaches the stubbed transport with status 204.

Rationale: the committed `examples/ycli-tracker/out/` corpus has no real 204 endpoint (Tracker priorities documents "no delete endpoint"). The bodyless path is proven on the synthetic behavioral fixture; a committed `out/` consumer arrives when a real 204-returning resource is authored (a later phase).

- [ ] **Step 1: Extend the fixture + add a behavioral assertion**

```python
# in _WIDGET.operations, add:
    ir.Operation(name="delete", method="DELETE", path="widget/{id}", operation_id="widget_delete",
                 response_model=None,
                 params=(ir.Param(name="id", loc="path", type=ScalarType(scalar="string")),)),
# in test_generated_root_client_imports_and_sends, after the get/create asserts:
    assert client.widget.delete("1") is None  # bodyless -> None
```

Add a `MockTransport` handler branch: `if request.method == "DELETE": return httpx.Response(204)`.

- [ ] **Step 2: Run behavioral**

Run: `uv run pytest -m behavioral -q`
Expected: PASS (2 or 3 tests). Confirm default run still excludes them: `uv run pytest -q` (unchanged count).

- [ ] **Step 3: Commit**

```bash
git add tests/behavioral/test_d_core_runs.py
git commit -m "test(behavioral): a bodyless DELETE op generates, imports, and sends (returns None)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: D1 - tests emitter iterates ALL tests-bearing ops (multi-op)

**Files:**
- Modify: `src/refract/emitters/python/resolve.py:505-577,674-693` (`resolve_tests` + `_tests_module_doc`/`_tests_imports`/`_tests_constants` fold from single-op to per-op union)
- Test: `tests/emitters/test_resolve_tests_multiop.py` (create)

**Interfaces:**
- Consumes: `ir.Resource` whose MULTIPLE operations carry `tests`.
- Produces: `resolve_tests` renders one test block per case across ALL tests-bearing ops (not just the first). Module doc + imports + constants are the UNION over those ops. `_URL`/`_PAYLOAD` become per-op (name them `_URL_<op>` / `_PAYLOAD_<op>` to avoid collision when two ops have client tests).

- [ ] **Step 1: Write failing test**

```python
# tests/emitters/test_resolve_tests_multiop.py (create)
# Build a Resource with TWO ops each carrying a CLIENT TestCase; assert BOTH test blocks render
# and both _URL constants appear. (Use the me/priorities fixtures as a template for TestCase shape.)
def test_resolve_tests_renders_all_tests_bearing_ops(two_op_tested_resource, ctx, parts):
    page = resolve_tests(two_op_tested_resource, ctx, *parts)
    names = [t for t in page.tests]
    assert any("test_first" in t for t in names)
    assert any("test_second" in t for t in names)
    assert sum(c.startswith("_URL") for c in page.constants) == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/emitters/test_resolve_tests_multiop.py -q`
Expected: FAIL (only the first op's tests render).

- [ ] **Step 3: Implement** - `resolve_tests` loops:

```python
def resolve_tests(res, ctx, naming, type_mapper, docstrings) -> TestsPageView:
    tested = [op for op in res.operations if op.tests]  # ALL, not next(...)
    kinds = {case.kind for op in tested for case in op.tests}
    client_class = naming.class_name(res.domain, "Client")
    constants: list[str] = []
    tests: list[str] = []
    for op in tested:
        constants.extend(_tests_constants(res, op, ctx, {case.kind for case in op.tests}))
        tests.extend(_test_block(res, op, case) for case in op.tests)
    return TestsPageView(
        doc_block=docstrings.render(_tests_module_doc(res, tested, kinds), ""),
        header_lines=("from __future__ import annotations",),
        import_lines=_tests_imports(res, tested, ctx, kinds, client_class),
        constants=tuple(constants),
        tests=tuple(tests),
    )
```

Refactor `_tests_module_doc(res, ops, kinds)` and `_tests_imports(res, ops, ctx, kinds, cls)` to take the op LIST (module doc uses `res` + surfaces; imports union over ops' response models). Make `_tests_constants` name `_URL`/`_PAYLOAD` per op (`_URL_{op.name}`), and update `_stub`/`_client_test` to reference the per-op constant (thread `op` into `_stub`). Keep single-op output byte-identical when only one op has tests by special-casing the suffix only when `len(tested) > 1` OR always suffixing and regenerating the snapshot - CHOOSE always-suffix + regen (simpler, one rule); regenerate `out/tests/tracker/test_me.py` in Task 6.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/emitters/test_resolve_tests_multiop.py -q && uv run ty check`
Expected: PASS. (Snapshot drift is expected here; fixed in Task 6.)

- [ ] **Step 5: Commit**

```bash
git add src/refract/emitters/python/resolve.py tests/emitters/test_resolve_tests_multiop.py
git commit -m "feat(emit): tests emitter iterates all tests-bearing ops (multi-op, per-op constants)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: D1 consumer - author tests on two priorities ops + regenerate snapshot

**Files:**
- Modify: `examples/ycli-tracker/tracker/priorities/resource.yaml` (add `tests:` to `list` and `create`)
- Modify (regenerate): `examples/ycli-tracker/out/**` (new `out/tests/tracker/test_priorities.py`; possibly `test_me.py` if the constant-suffix rule changed it)
- Test: the drift gate (`refract generate --check`)

**Interfaces:**
- Consumes: the multi-op `resolve_tests` (Task 5).
- Produces: a committed `test_priorities.py` L1 snapshot exercising client tests on TWO ops - the byte-target proving multi-op tests.

- [ ] **Step 1: Author `tests:` on `list` and `create`** in priorities `resource.yaml` (client-kind cases, mirroring the `me` test shape: `name`, `kind: client`, `http_method`, `path`, `status: 200`, `response_json`, `asserts`, `call`).

- [ ] **Step 2: Regenerate + verify drift-free**

Run: `uv run refract generate --write && uv run refract generate --check`
Expected: `--check` exit 0; `git status` shows the new `out/tests/tracker/test_priorities.py` (and `test_me.py` if suffix rule changed it).

- [ ] **Step 3: Full gate**

Run: `uv run pytest -q && uv run ruff check examples/ycli-tracker/out && uv run ty check`
Expected: 100% coverage held; generated tests are ruff-clean.

- [ ] **Step 4: Commit**

```bash
git add examples/ycli-tracker/
git commit -m "test(example): multi-op tests on priorities list+create (D1 L1 snapshot)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: D3 - vacuous no-facet surface-gate coverage

**Files:**
- Test: `tests/emitters/test_surface_gating.py` (create)

**Interfaces:**
- Consumes: `Generator.render_resource` (generation.py:45-52), the surface `applies()` gates.
- Produces: a fixture resource with NO mcp / NO cli / NO tests / NO models, asserting the generated plan OMITS those files - covering every `applies()` False arm (`surfaces/{mcp,cli,tests,models}.py:29`).

- [ ] **Step 1: Write failing/covering test**

```python
# tests/emitters/test_surface_gating.py (create)
from pathlib import Path
from refract import ir
from refract.generation import Generator
from refract.ir.types import ScalarType

_BARE = ir.Resource(
    domain="demo", resource="ping", security="tok", models=(),  # no models
    operations=(ir.Operation(name="get", method="GET", path="ping", operation_id="ping_get",
                             response_model=None),),  # no mcp/cli/tests facets, bodyless
)
_CONFIG = ir.ClientConfig(name="demo", server=ir.Server(base_url="https://api.demo/v1"),
                          auth=(("tok", ir.HeaderAuth(header="Authorization", template="Bearer {t}",
                                 inputs=(ir.AuthInput(name="t", env="T"),))),))


def test_bare_resource_omits_facet_surfaces():
    files = Generator.for_language("python").render_resource(_BARE, _CONFIG)
    joined = " ".join(files)
    assert not any(p.endswith("mcp.py") for p in files)
    assert not any(p.endswith("cli.py") for p in files)
    assert not any(p.endswith("models.py") for p in files)
    assert not any("test_" in p for p in files)
```

(A bare op still emits `_requests`/`client`/`package`; those `applies()` return True. If `client`/`requests` require a response model, keep `response_model=None` valid per Task 3.)

- [ ] **Step 2: Run**

Run: `uv run pytest tests/emitters/test_surface_gating.py -q`
Expected: PASS (this is a coverage-closing test; the gates already return False for a bare resource - Task 3 makes a bodyless op valid so the resource loads/renders).

- [ ] **Step 3: Verify it closes the branch**

Run: `uv run pytest -q` (full suite with coverage)
Expected: 100% coverage; the previously-vacuous `applies()` False arms are now hit.

- [ ] **Step 4: Commit**

```bash
git add tests/emitters/test_surface_gating.py
git commit -m "test(emit): cover the no-facet surface-gate False arms (D3)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: D5a - Assembled-CLI option builder (walk a body model into typer options)

**Files:**
- Modify: `src/refract/emitters/python/naming.py` (add `cli_option(*parts: str) -> str`)
- Modify: `src/refract/emitters/api.py:43-51` (add `cli_option` to the `Naming` ABC)
- Modify: `src/refract/emitters/python/resolve.py` (add `_assembled_options(res, op, type_mapper, naming) -> tuple[list[str], str, list[Import]]`)
- Test: `tests/emitters/test_assembled_cli.py` (create)

**Interfaces:**
- Consumes: `res.model(op.body.model)` (an `ObjectModel`), its `Field`s (scalar or one-level `ref<Model>`), `TypeMapper.render`, `Naming`.
- Produces: `Naming.cli_option("name", "ru") -> "name_ru"` (snake for the param, `--name-ru` is typer's auto-flag). `_assembled_options` returns `(option_decls, reassembly_expr, imports)` where `option_decls` are typer parameter declarations (one per scalar leaf, dotted for one-level nested) and `reassembly_expr` reconstructs the body model call, e.g. `PriorityCreate(key=key, name=LocalizedName(ru=name_ru, en=name_en), order=order, description=description)`. A body field that is `map<...>`, a union, or nested deeper than one level raises `SpecError` naming the field + suggesting `handler:` (the Q1 escape hatch).

- [ ] **Step 1: Write failing tests**

```python
# tests/emitters/test_assembled_cli.py (create) - build a Resource with PriorityCreate-shaped body
def test_assembled_options_flatten_one_level_ref(priorities_like_resource, parts):
    decls, expr, _ = _assembled_options(res, create_op, type_mapper, naming)
    assert "key: str" in " ".join(decls)
    assert "name_ru: str | None" in " ".join(decls)  # one-level ref<LocalizedName> flattened
    assert expr == "PriorityCreate(key=key, name=LocalizedName(ru=name_ru, en=name_en), order=order, description=description)"


def test_assembled_options_rejects_map_body(map_bodied_resource, parts):
    with pytest.raises(SpecError, match="handler:"):
        _assembled_options(res, map_op, type_mapper, naming)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/emitters/test_assembled_cli.py -q`
Expected: FAIL (`_assembled_options`/`cli_option` do not exist).

- [ ] **Step 3: Implement** `cli_option` (snake-join parts) + `_assembled_options` (walk `ObjectModel.fields`: scalar -> one option; `RefType` one level -> recurse ONE level into `res.model(target).fields`, emit `<parent>_<child>` options, reassemble `Target(child=<parent>_<child>, ...)`; `MapType`/`ListType`-of-ref/deeper `RefType` -> `raise SpecError(f"{op.name}: body field {field.name!r} needs handler: (Assembled-CLI covers scalar + one-level ref)")`). Types via `type_mapper.render(field.type, optional=field.optional)`; defaults via `type_mapper.null_default`.

- [ ] **Step 4: Run to verify pass + gate**

Run: `uv run pytest tests/emitters/test_assembled_cli.py -q && uv run ty check`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add src/refract/emitters/python/naming.py src/refract/emitters/api.py src/refract/emitters/python/resolve.py tests/emitters/test_assembled_cli.py
git commit -m "feat(emit): Assembled-CLI option builder (flatten scalar + one-level ref body)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: D5b - `_cli_command` emits a write command for a body op

**Files:**
- Modify: `src/refract/emitters/python/resolve.py:332-350` (`_cli_command`), `resolve_cli` (thread `type_mapper`/`naming` in)
- Test: `tests/emitters/test_assembled_cli.py` (extend)

**Interfaces:**
- Consumes: `_assembled_options` (Task 8), `ir.Operation` with `op.body is not None` and `op.cli is not None`.
- Produces: for a write op, `_cli_command` emits a typer command whose signature carries the assembled options (+ path params + query), reassembles the body, and forwards `app_ctx.<domain>.<resource>.<op>(<path-args>, <body-expr>[, <query>])` through `Serializer.serialize`. A read op (no body) keeps the current param-less passthrough - branch on `op.body is not None`.

- [ ] **Step 1: Write failing test** - assert a write op's CLI block contains the flattened options and the reassembly forward:

```python
def test_cli_command_write_op_assembles_body(priorities_like_resource, parts):
    block = _cli_command(res, create_op, docstrings, type_mapper, naming)
    assert "def create(" in block and "key: str" in block and "name_ru: str | None" in block
    assert "app_ctx.tracker.priorities.create(PriorityCreate(key=key, name=LocalizedName(" in block
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/emitters/test_assembled_cli.py -k write_op -q`
Expected: FAIL (current `_cli_command` is param-less).

- [ ] **Step 3: Implement** - branch `_cli_command` on `op.body is not None`; for the write branch build the typer signature from `_assembled_options` + path/query params (reuse `signature_and_call`'s param decls where possible) and forward the reassembled body. Update `resolve_cli` (resolve.py:353-385) to pass `type_mapper`/`naming` into `_cli_command`. Keep read ops on the existing path.

- [ ] **Step 4: Run to verify pass + gate**

Run: `uv run pytest -q && uv run ty check && uv run ruff check .`
Expected: PASS, clean. (me/priorities snapshot unchanged until Task 10 authors a write cli facet.)

- [ ] **Step 5: Commit**

```bash
git add src/refract/emitters/python/resolve.py tests/emitters/test_assembled_cli.py
git commit -m "feat(emit): cli surface emits assembled write commands (body from flat options)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: D5 consumer - priorities create/edit gain cli facets + snapshot + behavioral

**Files:**
- Modify: `examples/ycli-tracker/tracker/priorities/resource.yaml` (add `cli:` to `create` and `edit`)
- Modify (regenerate): `examples/ycli-tracker/out/tracker/priorities/cli.py` (+ package `__init__` gating if needed)
- Modify: `tests/behavioral/test_d_core_runs.py` (assert a generated write CLI command builds the body + invokes)
- Test: drift gate + behavioral

**Interfaces:**
- Consumes: Task 8-9 Assembled-CLI, the real `PriorityCreate` (scalar `key` + one-level `ref<LocalizedName>` name + `order` + `description`) and `PriorityUpdate` bodies.
- Produces: a committed `cli.py` L1 snapshot with real `create`/`edit` write commands (the D5 byte-target), and a behavioral proof the generated CLI command assembles the body and reaches the stubbed transport.

- [ ] **Step 1: Author `cli:` on `create` and `edit`** in priorities `resource.yaml` (`name`, `documentation`).

- [ ] **Step 2: Regenerate + drift-free**

Run: `uv run refract generate --write && uv run refract generate --check`
Expected: `--check` exit 0; `out/tracker/priorities/cli.py` now carries `create`/`edit` commands with `--key`/`--name-ru`/`--name-en`/`--order`/`--description` options.

- [ ] **Step 3: Behavioral proof** - extend the behavioral test to invoke the generated CLI create via `CliRunner` (or assert the client path the command forwards to), confirming the body reassembles and the POST reaches the stubbed transport.

- [ ] **Step 4: Full gate**

Run: `uv run pytest -q && uv run pytest -m behavioral -q && uv run refract generate --check && uv run ruff check . && uv run ruff format --check . && uv run ty check`
Expected: 100% coverage; behavioral green; drift-free; lint/format/type clean.

- [ ] **Step 5: Commit**

```bash
git add examples/ycli-tracker/ tests/behavioral/test_d_core_runs.py
git commit -m "feat(example): priorities create/edit CLI write commands (D5 Assembled-CLI L1 + behavioral)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage (spec section 4 + P0 row):**
- D1 multi-op tests -> Tasks 5 (emitter) + 6 (consumer/snapshot). Covered.
- D2 204/no-response-model -> Tasks 1 (spec) + 2 (runtime) + 3 (resolvers) + 4 (proof). Covered.
- D4 first-2xx -> Task 1 (implemented WITH D2, as the spec requires). Covered.
- D3 no-facet gate -> Task 7. Covered.
- D5 Assembled-CLI (Q1: Assembled default + handler escape hatch) -> Tasks 8 (builder) + 9 (command) + 10 (consumer); `handler:` routing = the `SpecError` in Task 8 that names `handler:` (the escape hatch is "author a handler"; wiring the emitter to CALL a model/op handler is deferred to when a real polymorphic-body write op needs it, per Q1's rule-of-three gate). Covered, with the handler-CALL wiring explicitly deferred - FLAG for the reviewer.

**Placeholder scan:** test bodies in Tasks 5-10 reference fixtures ("priorities_like_resource", "two_op_tested_resource") described in-prose rather than fully inlined; the implementer builds them from the `me`/`priorities` `resource.yaml` shapes cited. This is a deliberate right-sizing (the fixture shape is large and already exists in the repo), not a blank placeholder - each names the exact model/op shape to construct.

**Type consistency:** `_response_model -> str | None` (T1) flows to `ir.Operation.response_model: str | None` (already so, model.py:119) -> `Request.response_model: type[T] | None` (T2) -> `Session.send -> T | None` (T2) -> resolver `-> None` branch (T3). `_assembled_options` return tuple `(list[str], str, list[Import])` is consumed identically in T8 (test) and T9 (`_cli_command`). `Naming.cli_option` added to the ABC (T8) before first use.

**Open item for the executor (flag to reviewer at P0 close):** Task 3 deletes the two redesign-era "no response model" guard-trigger tests; confirm no OTHER test imports those code paths. Task 5's "always-suffix `_URL`" rule changes `test_me.py` output - confirm the regenerated snapshot in Task 6 is reviewed as a real diff, not rubber-stamped.
