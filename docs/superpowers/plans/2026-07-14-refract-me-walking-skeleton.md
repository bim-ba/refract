# refract — `me` Walking Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build refract's end-to-end generator pipeline — neutral YAML spec → typed IR → Python emitters (models · client · cli · mcp · tests) → committed source with a `--check` drift gate — and prove it by rendering ycli's real `tracker/me` resource **byte-identically** against golden copies of the real ycli source.

**Architecture:** Four strict downward layers: (1) **spec** = neutral YAML validated by a pydantic loader; (2) **IR** = frozen, language-neutral dataclasses (the product); (3) **emitters** = `emit(res) -> str` per (language, surface), reading ONLY the IR; (4) **output** = committed generated files + a `--check` gate. refract stays **self-contained**: fidelity is proven against real ycli source copied in as opaque **golden text** — refract never imports ycli. `ruff format` runs as a post-emit pass with a ruff config **identical** to ycli's, which is what makes output byte-identical.

**Tech Stack:** Python ≥3.12, `uv`-managed, `hatchling` build. Runtime deps: `pydantic` (loader), `pyyaml` (spec parse), `ruff` (post-emit formatter, invoked as a subprocess). Dev: `pytest`, `pytest-cov`, `ruff`, `ty`. No uplink/typer/fastmcp in refract itself — those only appear as strings in emitted output.

## Global Constraints

- **License:** MIT. Author: `Sava Znatnov <careless.sava@gmail.com>`.
- **Python:** `requires-python = ">=3.12"`; CI matrix `["3.12", "3.13"]`.
- **Byte-identity is the acceptance oracle.** Every emitter task passes iff `emit(ir) == read(golden_file)` exactly, where the golden file is a verbatim copy of real ycli source. No "close enough."
- **Self-contained.** refract must not import `ycli`. Golden files are opaque text fixtures under `examples/ycli-tracker/golden/`. `uv run pytest` in refract needs no ycli checkout.
- **ruff config identical to ycli** (embedded verbatim in Task 1) — this is load-bearing for byte-identity. The emitter's post-format pass shells out to `ruff format -` (stdin→stdout) using refract's own `pyproject.toml` config.
- **100% coverage** on refract's own code: `--cov-fail-under=100`. New code ships with tests that keep it green.
- **Full self-documenting names** — never abbreviate identifiers (`organization_id`, not `org_id`; `timeout_seconds`, not `timeout_s`). Matches the ycli house style the emitted code must reproduce.
- **Emitted output must satisfy ARCH-1/ARCH-3 by construction:** HTTP (`uplink`/`requests`) appears ONLY in `client.py`; `fastmcp` ONLY in `mcp.py`; MCP tools carry honest annotation classes (`RO`/`WRITE`/`WRITE_IDEMPOTENT`/`DESTRUCTIVE`). The `me` golden already obeys this; do not deviate from it.
- **Spec format is v2** (owner-ratified): full-word keys (`name`/`method`/`documentation`), explicit `responses: {200: {model: …}}` map (no `returns:` shorthand), unified `mcp:`/`cli:` facets as `{name, documentation, …}`, strategy names in PascalCase. The `me` resource is simple enough that no pagination/body/error registries appear yet — those arrive in later milestones as op-shapes demand them.
- **YAGNI-for-coverage (load-bearing on the 100% gate):** each emitter implements **only the code paths the current milestone's resource exercises.** Porting from the prototype means copying **only** the `me`-relevant branches — `_simple` GET client, `object`/`root_list` models, an RO `mcp` tool, the five `test_me.py` blocks. Do **not** port the prototype's offset-drain, bodyless-write, or typed-body branches now: they would be dead code under `me` and break `--cov-fail-under=100`. Those shapes arrive with the milestone that first needs them (`priorities`, `comments`, …). No `# pragma: no cover` escape hatches — if a branch exists, a test exercises it.

## Reference Material (read as needed; NOT part of refract)

- **Proven prototype emitters** (scratchpad, produce ycli-idiomatic output for the shapes they cover — use as the porting reference):
  - `…/scratchpad/sac-prototype/apigen/emitters/python/_common.py`
  - `…/scratchpad/sac-prototype/apigen/emitters/python/models.py`
  - `…/scratchpad/sac-prototype/apigen/emitters/python/client.py`
  - `…/scratchpad/sac-prototype/apigen/emitters/python/{cli,mcp,tests}.py`
  - `…/scratchpad/sac-prototype/apigen/{ir/model.py, loader.py, generate.py}`
  - (`…` = `/tmp/claude-1000/-home-sava-dev-dev-ycli/80802223-5853-4c72-8da8-868e6f65a5f8/scratchpad`)
- **Golden byte-targets** (real ycli source; copy verbatim into `examples/ycli-tracker/golden/` — see Task 7):
  - `/home/sava/dev/dev/ycli/src/ycli/yandex/tracker/me/{__init__,models,client,cli,mcp}.py`
  - `/home/sava/dev/dev/ycli/tests/yandex/tracker/test_me.py`
- **Design spec (commit as `docs/design.md` in Task 1):** `…/scratchpad/sac-research/17-refract-spec-v2-FINAL.md`

---

## File Structure

```
refract/                                    # repo root (already git-cloned, empty)
  pyproject.toml                            # Task 1 — deps, ruff (≡ ycli), pytest, ty, hatch
  LICENSE                                   # Task 1 — MIT
  README.md                                 # Task 1 — stub
  .gitignore                                # Task 1
  .github/workflows/ci.yml                  # Task 1 — 3.12/3.13 matrix; ruff/ty/pytest
  docs/
    design.md                               # Task 1 — the v2 blueprint, committed
    superpowers/plans/…                     # this file
  refract/
    __init__.py                             # Task 1
    ir/
      __init__.py                           # Task 2 — re-exports the IR names
      model.py                              # Task 2 — frozen dataclasses (the product)
    loader.py                               # Task 3 — pydantic spec → IR; SpecError
    format.py                               # Task 4 — ruff-format subprocess post-pass
    emitters/
      __init__.py                           # Task 4
      python/
        __init__.py                         # Task 4
        _common.py                          # Task 4 — naming/doc/wrap helpers
        models.py                           # Task 4 — pydantic models emitter
        client.py                           # Task 4 — uplink transport emitter
        cli.py                              # Task 5 — typer CLI emitter
        mcp.py                              # Task 5 — fastmcp MCP emitter (+ require_found)
        tests.py                            # Task 6 — responses-stubbed test-suite emitter
    generate.py                             # Task 7 — render/plan/--write/--check driver
    cli.py                                  # Task 7 — `refract generate` argparse entry
  examples/
    ycli-tracker/
      _auth.yaml                            # Task 3 — HeaderToken(oauth_token) registry
      tracker/me/resource.yaml              # Task 3 — the me spec (v2)
      golden/tracker/me/{__init__,models,client,cli,mcp}.py   # Task 7 — copied real ycli
      golden/tests/tracker/test_me.py       # Task 7 — copied real ycli
      out/                                  # Task 7 — generated tree (committed; --check'd)
  tests/
    test_ir.py                              # Task 2
    test_loader.py                          # Task 3
    test_emit_models.py                     # Task 4
    test_emit_client.py                     # Task 4
    test_emit_cli.py                        # Task 5
    test_emit_mcp.py                        # Task 5
    test_emit_tests.py                      # Task 6
    test_generate.py                        # Task 7 — fidelity + --check drift gate
    conftest.py                             # Task 3 — a `me_resource()` IR/spec fixture
```

---

### Task 1: Scaffold the refract repo

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `README.md`, `.gitignore`, `refract/__init__.py`, `.github/workflows/ci.yml`, `docs/design.md`, `tests/test_smoke.py`

**Interfaces:**
- Produces: an installable `refract` package (`uv sync` works); a green CI baseline; the exact `[tool.ruff]` config every later task's byte-identity depends on.

- [ ] **Step 1: Write `pyproject.toml`.** Embed the ruff block **verbatim from ycli** (do not paraphrase — byte-identity depends on it):

```toml
[project]
name = "refract"
version = "0.0.0"
description = "Language-agnostic, spec-driven generator: one neutral API spec → typed IR → per-(language×surface) emitters (client/CLI/MCP/models/tests) + OpenAPI."
readme = "README.md"
license = "MIT"
license-files = ["LICENSE"]
requires-python = ">=3.12"
authors = [{ name = "Sava Znatnov", email = "careless.sava@gmail.com" }]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Code Generators",
    "Typing :: Typed",
]
dependencies = [
    "pydantic>=2.13.4",
    "pyyaml>=6.0.3",
    "ruff>=0.15.20",
]

[project.scripts]
refract = "refract.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["refract"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--strict-markers --cov=refract --cov-report=term-missing --cov-fail-under=100"

[tool.coverage.run]
source = ["refract"]

[tool.coverage.report]
show_missing = true
exclude_also = [
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "\\.\\.\\.",
]

[tool.ruff]
target-version = "py312"
line-length = 100
src = ["refract", "tests"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
line-ending = "auto"
skip-magic-trailing-comma = false
docstring-code-format = true

[tool.ruff.lint]
select = ["E", "W", "F", "I", "N", "UP", "B", "A", "C4", "SIM", "PTH", "RUF", "ANN", "TC"]
ignore = ["ANN401"]

[tool.ruff.lint.isort]
known-first-party = ["refract"]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["N802", "ANN"]

[tool.ty.environment]
python-version = "3.12"

[tool.ty.terminal]
error-on-warning = true

[tool.ty.rules]
possibly-unresolved-reference = "error"
unused-ignore-comment = "warn"

[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "pytest-cov>=7.1.0",
    "ruff>=0.15.20",
    "ty>=0.0.55",
]
```

- [ ] **Step 2: Write `LICENSE`** — the standard MIT License text, `Copyright (c) 2026 Sava Znatnov`.
- [ ] **Step 3: Write `README.md`** — a short stub: what refract is (2–3 sentences from the Goal), status "alpha — walking skeleton", and a `uv run refract generate --check` usage line. Link `docs/design.md`.
- [ ] **Step 4: Write `.gitignore`** — Python standard: `__pycache__/`, `*.pyc`, `.venv/`, `.ruff_cache/`, `.pytest_cache/`, `dist/`, `*.egg-info/`, `.coverage`.
- [ ] **Step 5: Write `refract/__init__.py`:**

```python
"""refract — a language-agnostic, spec-driven multi-surface code generator."""

__version__ = "0.0.0"
```

- [ ] **Step 6: Copy the design spec** `…/scratchpad/sac-research/17-refract-spec-v2-FINAL.md` verbatim into `docs/design.md`.
- [ ] **Step 7: Write `.github/workflows/ci.yml`** — mirror ycli's structure: a `test` job, matrix `python-version: ["3.12", "3.13"]`, `astral-sh/setup-uv`, then steps (lint steps guarded `if: matrix.python-version == '3.12'`): `uv run ruff format --check .` · `uv run ruff check .` · `uv run ty check` · `uv run pytest` (every leg). Trigger on `push` and `pull_request`.
- [ ] **Step 8: Write the smoke test** `tests/test_smoke.py`:

```python
import refract


def test_version_is_exposed():
    assert refract.__version__ == "0.0.0"
```

- [ ] **Step 9: Verify the toolchain is green.**

Run: `cd refract && uv sync && uv run pytest && uv run ruff format --check . && uv run ruff check . && uv run ty check`
Expected: pytest 1 passed at 100% coverage; ruff format/check clean; ty clean.

- [ ] **Step 10: Commit.**

```bash
git add -A
git commit -m "chore: scaffold refract (MIT, uv, ruff≡ycli, CI matrix, design.md)"
```

---

### Task 2: The IR — frozen dataclasses

**Files:**
- Create: `refract/ir/model.py`, `refract/ir/__init__.py`
- Test: `tests/test_ir.py`

**Interfaces:**
- Produces (consumed by the loader and every emitter):
  - `Field(name, type, optional=False, default=None, alias=None, description=None)`
  - `Model(name, fields=(), kind="object", item=None, documentation=None, config=())` — `kind ∈ {"object","root_list","envelope"}`
  - `Param(name, loc, type="str", alias=None, default=None, help=None)` — `loc ∈ {"path","query","body"}`
  - `RequireFound(sentinel: str, message: str)` — the MCP empty-result guard, authored as data
  - `McpMeta(name, safety, title, documentation, require_found=None)` — `safety ∈ {"RO","WRITE","WRITE_IDEMPOTENT","DESTRUCTIVE"}`
  - `CliMeta(name, documentation)`
  - `TestCase(...)` — see Task 6; declare the dataclass here with fields `(name, kind, http_method, path, status, response_json, has_json, asserts, call)` where `kind ∈ {"client","cli","mcp","mcp_guard"}`
  - `Operation(name, method, path, operation_id, params=(), response_model=None, documentation=None, mcp=None, cli=None, tests=(), handler=None)`
  - `Resource(domain, resource, base_url, security, models, operations, documentation=None, module_docs=ModuleDocs())` with accessor `.model(name)->Model` and property `.domain_title`
  - `ModuleDocs(client=None, models=None, cli=None, mcp=None, cli_group_help=None, mcp_server=None, client_class=None)`
- All dataclasses `frozen=True`; all collections are **tuples** (so `Resource` is hashable). Field names spelled out in full.

**Design note (type system):** the v2 neutral types (`string|integer|boolean|list<T>|…` + `optional`) live in the **spec/loader** layer; the loader lowers them to the Python type-strings the emitters render (e.g. `integer` + `optional:true` → `"int | None"` with `default="None"`). The IR's `Field.type` is the already-lowered Python type-string, matching the prototype (keeps emitters trivial). The neutral→python mapping is the loader's job (Task 3).

- [ ] **Step 1: Write the failing test** `tests/test_ir.py`:

```python
from refract import ir


def test_resource_is_hashable_and_accessor_works():
    me = ir.Model(name="Me", fields=(ir.Field(name="login", type="str | None", default="None"),))
    res = ir.Resource(
        domain="tracker", resource="me", base_url="https://api.tracker.yandex.net/v3",
        security="oauth_token", models=(me,), operations=(),
    )
    assert hash(res) == hash(res)                 # frozen + tuples => hashable
    assert res.model("Me") is me
    assert res.domain_title == "Tracker"


def test_unknown_model_raises_keyerror():
    res = ir.Resource(
        domain="tracker", resource="me", base_url="x", security="oauth_token",
        models=(), operations=(),
    )
    import pytest
    with pytest.raises(KeyError):
        res.model("Nope")
```

- [ ] **Step 2: Run it — fails** (`ModuleNotFoundError: refract.ir`). Run: `uv run pytest tests/test_ir.py -v`.
- [ ] **Step 3: Implement `refract/ir/model.py`.** Port the prototype's `apigen/ir/model.py` (read it) and adapt to the interfaces above: rename `verb→`(op)`name`, `http→method`, `returns→response_model`, add `operation_id`, fold `client_module_doc`/etc. into a `ModuleDocs` dataclass, add `RequireFound` and extend `McpMeta`/`TestCase`. Keep `frozen=True`, tuple collections, `.model()`/`.domain_title`. Write `refract/ir/__init__.py` re-exporting every public name (`from refract.ir.model import *` with an explicit `__all__` in `model.py`).
- [ ] **Step 4: Run — passes.** Run: `uv run pytest tests/test_ir.py -v`. Then `uv run ruff format --check . && uv run ruff check . && uv run ty check`.
- [ ] **Step 5: Commit.** `git commit -am "feat: add the frozen IR dataclasses (the language-neutral product)"`

---

### Task 3: The loader — spec YAML → IR

**Files:**
- Create: `refract/loader.py`, `examples/ycli-tracker/_auth.yaml`, `examples/ycli-tracker/tracker/me/resource.yaml`, `tests/conftest.py`
- Test: `tests/test_loader.py`

**Interfaces:**
- Consumes: `refract.ir`.
- Produces: `load(path: Path) -> ir.Resource`; `SpecError(Exception)` (carries file path + pydantic message). A pydantic validation layer with `extra="forbid"` on every node. A `conftest.py` fixture `me_spec_path` returning the me `resource.yaml` path, and `me_resource()` returning the loaded IR.

- [ ] **Step 1: Author the me spec** `examples/ycli-tracker/tracker/me/resource.yaml` (v2 format). This is the single source the whole skeleton renders from — it must carry every datum the 6 golden files contain (model fields, docstrings, the mcp `require_found` guard, and each authored test's fixtures/asserts):

```yaml
domain: tracker
resource: me
base_url: https://api.tracker.yandex.net/v3
security: oauth_token
module_docs:
  models: "Pydantic model for Tracker /myself (Me)."
  client: "Declarative Tracker /myself client (uplink) — transport ONLY."
  cli: "`tracker me` commands."
  mcp: "Tracker /myself FastMCP tool (reads-only) — Depends DI."
  cli_group_help: "Tracker authenticated user."
  mcp_server: "tracker-me"
  client_class: "Declarative HTTP for ``/myself``."
documentation: "Tracker /myself resource (the authenticated user)."
models:
  - name: Me
    documentation: "The authenticated Tracker user (``GET /v3/myself``) — a safe auth probe."
    fields:
      - {name: uid, type: integer, optional: true}
      - {name: login, type: string, optional: true}
      - {name: display, type: string, optional: true}
      - {name: email, type: string, optional: true}
operations:
  - name: get
    method: GET
    path: myself
    operationId: me_get
    documentation: "``GET /myself`` → the authenticated ``Me`` (a safe auth probe)."
    responses:
      200: {model: Me}
    mcp:
      name: me_get
      safety: RO
      title: "Get current Tracker user"
      documentation: "The authenticated Yandex Tracker user (a safe auth probe)."
      require_found:
        sentinel: "r.login is None"
        message: "auth probe failed — empty user (check YANDEX_ID_OAUTH_TOKEN)"
    cli:
      name: get
      documentation: "Print the authenticated user (a safe auth probe)."
    tests:
      - {name: me_client_get, kind: client, http_method: GET, path: myself, status: 200,
         response_json: {uid: 42, login: alice, display: "Alice A.", email: alice@example.com},
         call: "TrackerClient(oauth_token=\"t\", organization_id=\"o\").me.get()",
         asserts: ["isinstance(me, Me)", "me.login == \"alice\" and me.uid == 42"]}
      - {name: me_cli_get, kind: cli, http_method: GET, path: myself, status: 200,
         response_json: {uid: 42, login: alice, display: "Alice A.", email: alice@example.com},
         asserts: ["res.exit_code == 0", "json.loads(res.stdout)[\"login\"] == \"alice\""]}
      # …mcp + mcp_guard cases — author to reproduce test_me.py exactly (Task 6 owns the shape).
```

> **Implementer note:** the `tests:` block here is illustrative of the shape; in Task 6 you finalize it so the tests emitter reproduces `test_me.py` byte-for-byte. Treat the golden as authoritative and back-fill any datum the spec must carry. `base_url`/`security` reference `_auth.yaml` (below); the emitters derive the base class (`TrackerResource`) and DI module from `domain`, so `base_url` is metadata for now (OpenAPI later).

- [ ] **Step 2: Author `_auth.yaml`** — the `HeaderToken` registry entry (from blueprint §3), used later for OpenAPI + validated as loadable now:

```yaml
auth:
  oauth_token:
    strategy: HeaderToken
    headers: {Authorization: "OAuth {token}", X-Org-Id: "{organization_id}"}
    secrets: {token: env:YANDEX_ID_OAUTH_TOKEN, organization_id: env:YANDEX_ID_ORGANIZATION_ID}
```

- [ ] **Step 3: Write the failing test** `tests/test_loader.py`:

```python
from pathlib import Path

import pytest

from refract import ir
from refract.loader import SpecError, load


def test_loads_me_resource(me_spec_path):
    res = load(me_spec_path)
    assert isinstance(res, ir.Resource)
    assert res.domain == "tracker" and res.resource == "me"
    assert res.model("Me").fields[0].name == "uid"
    assert res.model("Me").fields[0].type == "int | None"      # neutral 'integer'+optional lowered
    op = res.operations[0]
    assert op.name == "get" and op.method == "GET" and op.response_model == "Me"
    assert op.mcp.require_found.sentinel == "r.login is None"


def test_malformed_spec_raises_located_specerror(tmp_path):
    bad = tmp_path / "resource.yaml"
    bad.write_text("domain: tracker\nunknown_key: 1\n", encoding="utf-8")
    with pytest.raises(SpecError) as excinfo:
        load(bad)
    assert str(bad) in str(excinfo.value)
```

- [ ] **Step 4: Write `tests/conftest.py`:**

```python
from pathlib import Path

import pytest

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker"


@pytest.fixture
def me_spec_path() -> Path:
    return _EXAMPLES / "tracker" / "me" / "resource.yaml"
```

- [ ] **Step 5: Run — fails** (`ModuleNotFoundError: refract.loader`). Run: `uv run pytest tests/test_loader.py -v`.
- [ ] **Step 6: Implement `refract/loader.py`.** Port the prototype's `apigen/loader.py` structure (pydantic nodes, `extra="forbid"`, lowering functions, `SpecError`) and adapt to v2:
  - Spec nodes mirror the v2 YAML: `ResourceSpec{domain, resource, base_url, security, module_docs, documentation, models, operations}`, `ModelSpec{name, documentation, kind, item, config, fields}`, `FieldSpec{name, type, optional, default, alias, description, enum, format, deprecated}`, `OperationSpec{name, method, path, operationId, documentation, params, responses: dict[int, {model}], mcp, cli, tests, handler}`, `McpSpec{name, safety, title, documentation, require_found?}`, `CliSpec{name, documentation}`, `TestSpec{...}`.
  - **Neutral-type lowering** (`_lower_type`): map `{string→str, integer→int, number→float, boolean→bool, any→Any}`, `list<T>→list[<lower T>]`, `map<K,V>→dict[<K>, <V>]`, `ref<M>→M`; if `optional: true`, append ` | None` and default the `Field.default` to `"None"` when no explicit default. This is the one place the neutral type system is realized for Python.
  - Parse YAML with `yaml.safe_load`; the `on:`/`off:`/`yes:`/`no:` YAML-1.1-boolean footgun does not appear in the me spec, but keep the prototype's guard pattern (validate types post-load) so a future `on:` key fails loudly rather than silently coercing.
  - `load(path)` wraps `yaml.YAMLError` and pydantic `ValidationError` into `SpecError(f"{path}: …")`.
- [ ] **Step 7: Run — passes.** Run: `uv run pytest tests/test_loader.py -v && uv run ruff format --check . && uv run ruff check . && uv run ty check`.
- [ ] **Step 8: Commit.** `git commit -am "feat: add the pydantic spec loader (neutral YAML → typed IR)"`

---

### Task 4: Emitters — `_common`, `models`, `client` (+ ruff-format post-pass)

**Files:**
- Create: `refract/format.py`, `refract/emitters/__init__.py`, `refract/emitters/python/__init__.py`, `refract/emitters/python/_common.py`, `refract/emitters/python/models.py`, `refract/emitters/python/client.py`
- Test: `tests/test_emit_models.py`, `tests/test_emit_client.py`

**Interfaces:**
- Consumes: `refract.ir`, the `me_resource()` fixture.
- Produces: `models.emit(res) -> str`, `client.emit(res) -> str`; `format.ruff_format(source: str) -> str` (subprocess `ruff format -` over stdin, using refract's pyproject config); `_common` helpers (`render_doc`, `wrap_call`, `pascal`, `domain_title`, `resource_client_class`, `domain_resource_base`, `safe_identifier`, `LINE_LIMIT`).

**Acceptance oracle:** `models.emit(me) == read(golden/tracker/me/models.py)` and `client.emit(me) == read(golden/tracker/me/client.py)`, byte-for-byte. (Golden files are copied in Task 7; for this task, copy the two you need locally first — Step 1.)

- [ ] **Step 1: Copy the two golden files** you validate against:
  - `examples/ycli-tracker/golden/tracker/me/models.py` ← `/home/sava/dev/dev/ycli/src/ycli/yandex/tracker/me/models.py`
  - `examples/ycli-tracker/golden/tracker/me/client.py` ← `/home/sava/dev/dev/ycli/src/ycli/yandex/tracker/me/client.py`
- [ ] **Step 2: Write the failing tests.** `tests/test_emit_models.py`:

```python
from pathlib import Path

from refract.emitters.python import models

_GOLDEN = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker" / "golden"


def test_models_emit_is_byte_identical_to_real_ycli(me_resource):
    golden = (_GOLDEN / "tracker" / "me" / "models.py").read_text(encoding="utf-8")
    assert models.emit(me_resource) == golden
```

`tests/test_emit_client.py` — identical shape against `client.py` and `client.emit`.

Add a `me_resource` fixture to `conftest.py`: `@pytest.fixture def me_resource(me_spec_path): return load(me_spec_path)`.

- [ ] **Step 3: Run — fails** (`ModuleNotFoundError`). Run: `uv run pytest tests/test_emit_models.py tests/test_emit_client.py -v`.
- [ ] **Step 4: Implement `refract/format.py`** — `ruff_format(source)`:

```python
"""Post-emit formatting: pipe emitted source through ``ruff format`` (refract's own config).

Emitters produce structurally-correct source; ruff is the single authority on wrapping and
spacing, so output matches any ruff-formatted codebase (here: ycli) exactly. Never hand-emulate.
"""

from __future__ import annotations

import subprocess


def ruff_format(source: str) -> str:
    """Return ``source`` formatted by ``ruff format`` (reads stdin, writes stdout)."""
    result = subprocess.run(
        ["ruff", "format", "-"],
        input=source,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
```

  > **Decision to validate during implementation:** the prototype emitters already produce byte-identical output *without* a ruff pass (they hand-wrap at `LINE_LIMIT`). Two viable strategies — (a) emitters emit exact final text, ruff pass is a no-op safety net; (b) emitters emit un-wrapped text, ruff does all wrapping. Prefer (b) where it *simplifies* the emitter (drop the hand-wrap logic in `_common.wrap_call`/`client._endpoint`) **only if** the ruff-formatted result still byte-equals golden; otherwise keep the prototype's proven hand-wrap and treat ruff as idempotent verification. The acceptance test (byte-equality) decides. Whichever you pick, `emit()` returns the final (post-`ruff_format`) string.
- [ ] **Step 5: Implement `_common.py` and `models.py`.** Port from the prototype's `_common.py` + `models.py` (read them — they already render ycli's `APIModel`/`RootModel` idioms and the `render_doc` docstring shaping). Adapt names to the v2 IR (`Model.documentation` not `.doc`; `ModuleDocs.models`). Have `models.emit` return `ruff_format(rendered)`.
- [ ] **Step 6: Implement `client.py`.** Port the prototype's `client.py` (read it — it renders the no-`__future__` header, the `@uplink.returns.json()/@uplink.<verb>(path)` stack, `import uplink`, the `from ycli.yandex.<domain>.base import <Domain>Resource` + model imports, and the `# ty: ignore[empty-body]` idiom). For `me`, only the `_simple` GET path is exercised. Derive `TrackerResource` from `res.domain`. Have `client.emit` return `ruff_format(rendered)`.
- [ ] **Step 7: Run — passes** (both byte-identical). Run: `uv run pytest tests/test_emit_models.py tests/test_emit_client.py -v`. If a diff appears, print `difflib.unified_diff(golden, emit)` to locate the exact divergence and fix the emitter (never the golden). Then `uv run ruff format --check . && uv run ruff check . && uv run ty check`.
- [ ] **Step 8: Commit.** `git commit -am "feat: python models+client emitters (byte-identical to ycli tracker/me)"`

---

### Task 5: Emitters — `cli`, `mcp` (with `require_found`)

**Files:**
- Create: `refract/emitters/python/cli.py`, `refract/emitters/python/mcp.py`
- Test: `tests/test_emit_cli.py`, `tests/test_emit_mcp.py`

**Interfaces:**
- Produces: `cli.emit(res) -> str`, `mcp.emit(res) -> str`.
- **Acceptance:** each `== read(golden/tracker/me/{cli,mcp}.py)` byte-for-byte.

**Golden shape reminders (do not deviate):**
- `cli.py`: `from __future__ import annotations`, `import typer`, `from ycli.cli.context import AppContext`, `from ycli.cli.output import Serializer`, `app = typer.Typer(name="me", help="Tracker authenticated user.", no_args_is_help=True)`, a `@app.callback() def _group()` anchor, and `@app.command() def get(ctx)` that does `app_ctx = AppContext.from_typer_context(ctx)` then `Serializer.serialize(app_ctx.tracker.me.get(), app_ctx.strategy, app_ctx.console)`. The `tracker`/`me`/`get` accessors derive from `res.domain`/`res.resource`/`op.cli.name`.
- `mcp.py`: `from fastmcp import FastMCP`, `from fastmcp.dependencies import Depends`, `from ycli.yandex.models import require_found`, `from ycli.yandex.tracker.client import TrackerClient`, `from ycli.yandex.tracker.dependencies import RO, TAGS, tracker_client`, model import, `mcp = FastMCP("tracker-me")`, and the tool: `@mcp.tool(name="me_get", annotations={**RO, "title": "Get current Tracker user"}, tags=TAGS)` → `def get(client: TrackerClient = Depends(tracker_client)) -> Me:` whose body calls `client.me.get()` and, because `op.mcp.require_found` is present, wraps it in `require_found(result, sentinel=lambda r: r.login is None, message="…")`. The `RO`/`WRITE`/… symbol comes from `op.mcp.safety`; `require_found` import is emitted only when some op declares it.

- [ ] **Step 1: Copy goldens** `examples/ycli-tracker/golden/tracker/me/{cli,mcp}.py` from the real ycli files.
- [ ] **Step 2: Write the failing tests** — `tests/test_emit_cli.py` / `tests/test_emit_mcp.py`, same byte-equality shape as Task 4.
- [ ] **Step 3: Run — fails.** Run: `uv run pytest tests/test_emit_cli.py tests/test_emit_mcp.py -v`.
- [ ] **Step 4: Implement `cli.py`.** Port the prototype's `cli.py` as the base (read it — it renders the typer group + `_group` callback + `AppContext`/`Serializer` command idiom). The `me` command is a plain passthrough (no params). Return `ruff_format(rendered)`.
- [ ] **Step 5: Implement `mcp.py`.** Port the prototype's `mcp.py` (read it — annotation-class spread `{**RO, "title": …}`, `tags=TAGS`, `Depends(tracker_client)` DI). **New logic:** when `op.mcp.require_found` is set, emit the `require_found(result, sentinel=lambda r: <sentinel>, message=<message>)` wrapper and its import; otherwise return the call directly. Derive `TrackerClient`/`tracker_client`/`RO`/`TAGS` from `res.domain`. Return `ruff_format(rendered)`.
- [ ] **Step 6: Run — passes.** Run: `uv run pytest tests/test_emit_cli.py tests/test_emit_mcp.py -v`. Diff-debug against golden on any mismatch. Then `ruff format --check`, `ruff check`, `ty check`.
- [ ] **Step 7: Commit.** `git commit -am "feat: python cli+mcp emitters (require_found guard as spec data)"`

---

### Task 6: Emitter — `tests` (the strategy-driven auto-suite)

**Files:**
- Create: `refract/emitters/python/tests.py`
- Test: `tests/test_emit_tests.py`

**Interfaces:**
- Produces: `tests.emit(res) -> str`.
- **Acceptance:** `tests.emit(me) == read(golden/tests/tracker/test_me.py)` byte-for-byte.

**Golden shape (`test_me.py`) — the emitter must reproduce all five tests:**
- Module docstring `"""Tracker /myself resource — client + CLI + MCP, HTTP stubbed."""`; `from __future__ import annotations`; imports `asyncio, json, pytest, responses`, `from fastmcp import Client`, `from fastmcp.exceptions import ToolError`, `from typer.testing import CliRunner`, `import ycli.cli.app as cli`, `from ycli.mcp import mcp as root_mcp`, `from ycli.yandex.tracker.client import TrackerClient`, `from ycli.yandex.tracker.me import mcp as me_mcp_module`, `from ycli.yandex.tracker.me.models import Me`.
- Module constants `_URL`, `_PAYLOAD`, `_runner = CliRunner()`.
- `test_me_client_get` (kind `client`) — `@responses.activate`, stub GET `_URL`→`_PAYLOAD`, call, asserts.
- `test_me_cli_get` (kind `cli`) — CliRunner invoke `["--format","json","tracker","me","get"]`, asserts.
- `test_me_mcp_tool` (kind `mcp`) — `async with Client(root_mcp)` call `"tracker_me_get"`, assert `.data.login`.
- `test_me_mcp_auth_guard` (kind `mcp_guard`, 401) — `async`, `pytest.raises(ToolError)` on `me_mcp_module.mcp` tool `"me_get"`.
- `test_me_mcp_empty_response_guard` (kind `mcp_guard`, 200 empty) — same, with the docstring about the login-is-None guard. Emitted only because `op.mcp.require_found` is present.

**Design:** the emitter selects test blocks from the op's declared surfaces + `require_found`. Each test's fixtures (`_PAYLOAD`, status, path) and asserts are **authored data** from the spec's `tests:` list (never emitter-computed — keeps them non-tautological). The two guard tests derive from `op.mcp.require_found` (empty-guard) and the always-present auth-guard for a read tool. This is the §11 strategy-driven auto-suite, thin-sliced to `me`'s shape.

- [ ] **Step 1: Copy golden** `examples/ycli-tracker/golden/tests/tracker/test_me.py` ← `/home/sava/dev/dev/ycli/tests/yandex/tracker/test_me.py`.
- [ ] **Step 2: Finalize the spec `tests:` block** in `resource.yaml` so it carries every datum the golden needs (payload, URL path, the five cases with their kinds/asserts/docstrings). Confirm `load()` still passes.
- [ ] **Step 3: Write the failing test** `tests/test_emit_tests.py` — byte-equality of `tests.emit(me_resource)` against the golden.
- [ ] **Step 4: Run — fails.** Run: `uv run pytest tests/test_emit_tests.py -v`.
- [ ] **Step 5: Implement `tests.py`.** Reference the prototype `tests.py` for the `responses`-stub idiom, then build the five-block selector against the golden. Derive `_URL` from `base_url` + op `path`; render `_PAYLOAD` from the client case's `response_json`; emit `import`s conditionally on which kinds are present. Return `ruff_format(rendered)`.
- [ ] **Step 6: Run — passes.** Diff-debug against golden. Then `ruff format --check`, `ruff check`, `ty check`, full `uv run pytest`.
- [ ] **Step 7: Commit.** `git commit -am "feat: python tests emitter (strategy-driven auto-suite, byte-identical test_me.py)"`

---

### Task 7: The `generate` driver, `--check` drift gate, and fidelity wiring

**Files:**
- Create: `refract/generate.py`, `refract/cli.py`, `examples/ycli-tracker/out/**` (generated, committed), all remaining `examples/ycli-tracker/golden/**`
- Test: `tests/test_generate.py`

**Interfaces:**
- Consumes: loader + all five emitters.
- Produces: `refract.generate.render_resource(res) -> dict[str, str]` (rel-path → content); `plan(specs_dir, out_dir) -> dict[Path, str]`; `write(plan)`; `check(plan) -> int`. `refract/cli.py:main()` = argparse `refract generate [--write|--check]` (mirrors the prototype `generate.py`).
- The generated tree layout under `out/`: `tracker/me/{__init__,models,client,cli,mcp}.py` + `tests/tracker/test_me.py` (note the flat combined test file, per ycli's real layout for `me`).

- [ ] **Step 1: Copy the remaining goldens** — `golden/tracker/me/__init__.py` and confirm all six goldens present (`__init__, models, client, cli, mcp` + `tests/tracker/test_me.py`).
- [ ] **Step 2: Write the failing test** `tests/test_generate.py`:

```python
from pathlib import Path

from refract.generate import check, plan, render_resource, write
from refract.loader import load

_EX = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker"


def test_generated_output_is_byte_identical_to_golden(me_resource):
    files = render_resource(me_resource)
    golden_dir = _EX / "golden"
    assert files["tracker/me/models.py"] == (golden_dir / "tracker/me/models.py").read_text("utf-8")
    assert files["tests/tracker/test_me.py"] == (golden_dir / "tests/tracker/test_me.py").read_text("utf-8")
    # …assert every one of the six files.


def test_check_passes_on_committed_tree():
    the_plan = plan(_EX, _EX / "out")
    assert check(the_plan) == 0          # committed out/ is up to date


def test_check_detects_drift(tmp_path):
    res = load(_EX / "tracker" / "me" / "resource.yaml")
    files = render_resource(res)
    stale = tmp_path / "out"
    (stale / "tracker" / "me").mkdir(parents=True)
    # write everything, then corrupt one file:
    ...
    # assert check(plan(_EX, stale)) == 1
```

- [ ] **Step 3: Run — fails.** Run: `uv run pytest tests/test_generate.py -v`.
- [ ] **Step 4: Implement `refract/generate.py` and `refract/cli.py`.** Port the prototype `generate.py` (read it — `render_resource`, `plan`, `write`, `check`, argparse driver). `render_resource` returns the six-file dict (note the test file path is `tests/tracker/test_<resource>.py`, not per-surface — matches ycli's real `me` layout; make the test path a per-resource choice with `tests/<domain>/test_<resource>.py` as the default). `refract/cli.py:main()` wraps it as `refract generate [--write|--check]`.
- [ ] **Step 5: Generate the committed `out/` tree.** Run: `uv run refract generate --write` (writes `examples/ycli-tracker/out/**`). Verify `out/` files equal the goldens (they must, since they render from the same spec).
- [ ] **Step 6: Run — passes.** Run: `uv run pytest tests/test_generate.py -v`, then the **full** suite `uv run pytest` (100% coverage), then `uv run refract generate --check` (exit 0), then `ruff format --check`, `ruff check`, `ty check`.
- [ ] **Step 7: Commit.** `git commit -am "feat: refract generate CLI + --check drift gate; me renders byte-identical end-to-end"`

---

## Self-Review

**1. Spec coverage.** Every layer of the blueprint's v1 walking-slice maps to a task: scaffold (T1) · IR (T2) · loader + neutral-type lowering + spec (T3) · models/client emitters + ruff post-pass (T4) · cli/mcp emitters + require_found-as-data (T5) · tests auto-suite emitter (T6) · generate/`--check`/fidelity (T7). Registries beyond what `me` needs (pagination, body, async, errors, unions) are **intentionally deferred** to follow-on milestones (`priorities` next) — the incremental-growth model the blueprint mandates; not a gap.

**2. Placeholder scan.** The only non-inlined code is emitter internals whose **exact output is pinned by a committed golden file + byte-equality test** — that is a complete specification, not a placeholder. The prototype files are named by exact path as the porting reference. The one genuinely-open implementation choice (ruff-pass strategy, T4 Step 4) is called out explicitly with the acceptance test as the decider.

**3. Type consistency.** IR names are fixed once in Task 2's Interfaces block and reused verbatim downstream (`response_model`, `op.mcp.require_found.sentinel`, `ModuleDocs.mcp_server`, `Resource.domain_title`). Emitter entry points are uniformly `emit(res) -> str`. The generated test-file path convention (`tests/<domain>/test_<resource>.py`) is stated in T7 to match ycli's real `me` layout.

**Acceptance for the whole plan:** `uv run pytest` green at 100% coverage, `uv run refract generate --check` exit 0, `ruff format --check`/`ruff check`/`ty check` clean — and the six generated files byte-identical to real ycli `tracker/me` source. That is a working generator proving fidelity on one real resource with a drift gate: the walking skeleton.
