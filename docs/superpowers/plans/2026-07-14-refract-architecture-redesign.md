# refract - редизайн архитектуры генератора (Workstream A) / план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: используй superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans для пошагового исполнения. Шаги помечены чекбоксами (`- [ ]`).

**Goal:** заменить процедурный код refract декларативной композиционной мультиязык-готовой архитектурой с формой вывода **D** (sans-I/O `Request` + общий `send()`), нейтральным IR, Jinja-рендерингом, **генерируемым glue** (root-client + auth из `client.yaml`) и 4-слойным оракулом - за один big-bang-план. refract - публичный генератор для произвольного API, а не ad-hoc-тул; me/priorities - walking skeleton, доказывающий сквозной генератор.

**Architecture:** нейтральная YAML-спека (`resource.yaml` + `client.yaml`) -> `SpecLoader` -> нейтральный frozen-pydantic IR (`NeutralType`-сумма + `Model`-union + `ClientConfig`/`AuthScheme`) -> `Generator` резолвит `LanguageBackend` из реестра `@backend` -> бэкенд композирует 5 внедряемых стратегий (`Naming`/`TypeMapper`/`Formatter`/`Docstrings`/`Layout`) + surface-эмиттеры -> `UnitRenderer` (view-model -> Jinja-`Fragment`; ветвление read/write локально по `op.body`) + `ResourceAssembler` (рамка модуля + сбор импортов) -> `RuffFormatter` -> committed source. Форма D: одна чистая функция-билдер `Request[T]` на операцию + один auth-agnostic `send()`-executor; плюс генерируемый glue - root-client (агрегатор ресурсов + сборка `httpx.Client(auth=...)` из библиотеки auth-механизмов core).

**Tech Stack:** Python 3.12 / pydantic v2.13.4 (frozen, discriminated union) / Jinja2 3.1.6 (`PackageLoader`+`StrictUndefined`) / Typer 0.26.8 (`Annotated`) / ruff 0.15.x (`ruff format -` subprocess) / hatchling (src-layout) / pytest.

---

## Global Constraints

Проектные инварианты - неявно входят в требования **каждой** задачи. Точные значения проверены против живых доков.

- **Python floor:** `requires-python = ">=3.12"` - `typing.assert_never` из stdlib (не `typing_extensions`); `match`/`case` доступны.
- **Layout:** `src/`-layout. Пакет переезжает `refract/` -> `src/refract/`; `tests/` зеркалит `src/refract/`. `pyproject`: `[tool.hatch.build.targets.wheel] packages = ["src/refract"]`, ruff `src = ["src", "tests"]`, coverage `source = ["src/refract"]`.
- **pydantic (IR + spec):**
  - frozen-модели: `model_config = ConfigDict(frozen=True)` -> инстансы hashable.
  - **все коллекции - `tuple[X, ...]`, никогда `list`** (иммутабельность + порядок рендера; `list` дал бы глубокую мутабельность). Дефолты - `()`, никогда `[]`. Hashability гарантируется только для `NeutralType`; большие узлы (`Resource`/`Operation`/`TestCase`) уже нехешируемы из-за `JsonValue`-фикстуры в `response_json` - это ок, их никто не хеширует. `tuple` держим ради иммутабельности, не хеша.
  - `NeutralType` - дискриминированная сумма: `Annotated[Union[...], Field(discriminator="kind")]`, каждый вариант несёт `kind: Literal[...]`.
  - рекурсивные варианты (`ListType.item`, `MapType.value`) - строковые forward-refs + `model_rebuild()` после определения алиаса.
  - `extra="forbid"` - **только** на spec-входных нодах, не на IR-вариантах.
- **Исчерпывающесть:** диспетчеризация по union'ам (`NeutralType`, `Model`, `AuthScheme`) - через `match` + `case _: assert_never(x)`. Ни одного «прочего» молчаливого случая. Ветвление read/write - локальный `if op.body is not None` (без отдельного `OpShape`-типа, см. Shared Contracts).
- **Jinja `Environment`** (единственная конфигурация, `src/refract/emitters/python/environment.py`):
  ```python
  Environment(
      loader=PackageLoader("refract.emitters.python", "templates"),
      autoescape=False, trim_blocks=True, lstrip_blocks=True,
      keep_trailing_newline=True, undefined=StrictUndefined,
  )
  ```
  Шаблоны - наследование (`_module.jinja` + блоки) + макросы. Единственные `{% if %}` в шаблонах - презентационные, не op-shape. `.jinja`-файлы должны быть **git-tracked** (иначе hatchling молча не положит их в wheel).
- **Форматтер:** только `subprocess.run(["ruff", "format", "--stdin-filename", "<file>.py", "-"], input=src, capture_output=True, text=True, check=True)`. Python-API у ruff нет. Обёрнут в `RuffFormatter` с обработкой `CalledProcessError`/`FileNotFoundError`.
- **Версия:** `src/refract/__init__.py` -> `__version__ = version("refract")` (`importlib.metadata`, guard `PackageNotFoundError`). Источник истины - `pyproject` `version`. Не хардкодить.
- **CLI:** Typer, `Annotated`-стиль опций; entry point `refract = "refract.cli:app"` (обёртка `main()` не нужна - `Typer()` callable).
- **Именование:** имена полей/идентификаторов - полностью, без аббревиатур (домовый стиль ycli). Идентификаторы кода - на английском; русский - только в prose плана/доках, НИКОГДА в эмитируемом/IR/тест-коде (docstring-и И комментарии - на английском).
- **Плановые кросс-рефы в код-блоках - НЕ переносить в код.** Комментарии внутри ```python-блоков контрактов/задач могут нести плановую бухгалтерию: `(разд. X)`, `(решение #N)`, русские пояснения. При транскрипции в файл: убрать `(разд. X)`/`(решение #N)`-ссылку (она указывает на этот план, в шипнутом коде бессмысленна) и оставить комментарий на английском. В `src/`/`tests/` не должно быть ни `разд.`, ни кириллицы.
- **"Дословно" из Shared Contracts = семантическая/структурная эквивалентность, не побуквенная.** Собственные ruff-правила проекта (`UP`, `I`), применяемые через `ruff --fix`, имеют приоритет над буквальным синтаксисом контракта: `UP007` перепишет `Union[X, Y]` -> `X | Y` и `Optional[X]` -> `X | None`, isort пересортирует импорты. Это ожидаемо и корректно - ревьюер не должен флагать `X | Y` как отклонение от контрактного `Union[...]`.
- **Оракул:** L0 (юниты, костяк покрытия) + L1 (регенерируемые снапшоты) держат быстрый гейт; L3 (поведенческий) - opt-in (`@pytest.mark.behavioral`). L2 (byte-identical vs ycli) - **отложен**: D-стиля ycli ещё не существует, стартовые goldens аннулированы (см. разд. Оракул). Гейт покрытия по refract-коду держат L0+L1.
- **Секретность:** ни хардкода токенов/id, ни воспроизведения кред из дампов/логов в коде или тестах (кроме уже существующих фикстурных `"t"`/`"o"`).

---

## Целевая структура `src/`

| Путь | Роль | Статус |
|---|---|---|
| `src/refract/__init__.py` | `__version__` из `importlib.metadata` | modify (move) |
| `src/refract/cli.py` | Typer-app: `generate` (`--write`/`--check`/`--out`/`--lang`) | rewrite |
| `src/refract/generation.py` | `Generator`: resolve backend -> plan -> write -> check | new (replaces `generate.py`) |
| `src/refract/spec/__init__.py` | реэкспорт `SpecError`, `load` | new |
| `src/refract/spec/nodes.py` | pydantic-схема входа (`extra="forbid"`) - декомпозиция god-file | new |
| `src/refract/spec/loader.py` | `SpecLoader.load(path) -> ir.Resource` (нейтральный) | new (replaces `loader.py`) |
| `src/refract/ir/__init__.py` | реэкспорт IR + `NeutralType` | modify |
| `src/refract/ir/types.py` | `NeutralType`-сумма (`ScalarType`/`RefType`/`ListType`/`MapType`) | new |
| `src/refract/ir/model.py` | frozen-**pydantic** IR, tuple-коллекции, `type: NeutralType`, `Model`-union | rewrite |
| `src/refract/ir/auth.py` | `AuthScheme`-union (`HeaderAuth`/`MultiHeaderAuth` built + named) + `AuthInput` | new |
| `src/refract/ir/client.py` | `ClientConfig` + `Server` (`base_url` переезжает сюда с `Resource`) | new |
| `src/refract/emitters/api.py` | контракт плагина: value-объекты + 5 стратегий-ABC + renderer/assembler/backend-ABC | new |
| `src/refract/emitters/registry.py` | `@backend` + `get_backend` (ленивый импорт) | new |
| `src/refract/emitters/python/backend.py` | `@backend("python")` - композиция частей | new |
| `src/refract/emitters/python/naming.py` | `PythonNaming` (заменяет `_common.py`) | new |
| `src/refract/emitters/python/types.py` | `PythonTypeMapper` (сюда уезжает `_lower_type`) | new |
| `src/refract/emitters/python/format.py` | `RuffFormatter` (заменяет `refract/format.py`) | new |
| `src/refract/emitters/python/docstrings.py` | `PythonDocstrings` (заменяет `render_doc`) | new |
| `src/refract/emitters/python/layout.py` | `PythonLayout` - `(resource, surface) -> путь` | new |
| `src/refract/emitters/python/views.py` | view-model (frozen pydantic, только резолвнутые примитивы) | new |
| `src/refract/emitters/python/resolve.py` | `IR -> view-model` (union-логика, `assert_never`) | new |
| `src/refract/emitters/python/environment.py` | Jinja `Environment` | new |
| `src/refract/emitters/python/surfaces/{requests,client,models,cli,mcp,tests,package,root_client}.py` | surface-эмиттеры (renderer+assembler) в форме D; `root_client` = glue (per-API) | new |
| `src/refract/emitters/python/templates/*.jinja` | шаблоны (наследование + макросы) | new |
| `src/refract/runtime/{request,session}.py` | **референс-рантайм** `Request[T]` + auth-agnostic `Session.send()` (для L3; эталон для ycli) | new |
| `src/refract/runtime/auth.py` | библиотека auth-механизмов (`httpx.Auth`): `HeaderAuth`/`MultiHeaderAuth` + hook | new |
| `tests/` | зеркалит `src/refract/`; `snapshots/` (L1) / `behavioral/` (L3) | rewrite |
| `artifacts/` | gitignored: перенос `docs/research/**` | move |
| `docs/adding-a-language.md` | чек-лист нового бэкенда (DX) | new |
| `examples/` | golden-корпус + `client.yaml` (миграция `_auth.yaml`; `base_url` уходит из `resource.yaml`); uplink-goldens **удаляются**, D-снапшоты генерируются | modify |

Удаляются в фазе очистки: `refract/emitters/python/{_common,client,cli,mcp,models,tests}.py`, `refract/{loader,generate,format}.py`, старые `tests/test_*.py`, uplink-goldens под `examples/ycli-tracker/golden/**`.

---

## PHASE MAP

Big-bang, снизу-вверх по зависимостям. Каждая задача заканчивается независимо тестируемым deliverable + коммитом. Полные контракты, пересекающие границы задач, зафиксированы в разделе **Shared Contracts** ниже - задачи ссылаются на них.

| Фаза | Что | Deliverable-гейт |
|---|---|---|
| **0** | src-layout переезд + tooling (версия из metadata, pyproject) | текущие тесты зелены после механического переезда |
| **1** | Нейтральный IR: `ir/types.py` (`NeutralType`) + `ir/model.py` (pydantic, `Model`-union) + `ir/auth.py` + `ir/client.py` | L0 юниты на IR: конструирование, frozen, discriminated-union парсинг (типы/`Model`/`AuthScheme`) |
| **2** | spec-декомпозиция: `spec/nodes.py` + `spec/loader.py` (`resource.yaml` + `client.yaml`) -> нейтральный IR | L0: loader даёт нейтральный IR + `ClientConfig` из `me`+`priorities`+`client.yaml` |
| **3** | Контракт плагина: `emitters/api.py` + `registry.py` | L0: value-объекты + реестр `@backend` round-trip |
| **4** | Python-стратегии: `naming`/`types`/`format`/`docstrings`/`layout` | L0 на каждую стратегию в изоляции |
| **5** | Рендеринг: `views.py` + `resolve.py` + `environment.py` + `templates/` | L0: `resolve` IR->view-model без рендера; smoke-рендер шаблона |
| **6** | Референс-рантайм: `runtime/{request,session}.py` (`Request[T]` + auth-agnostic `send()`) + `runtime/auth.py` (механизмы) | L0: `Request` конструируется; `send` шлёт через stubbed httpx; `MultiHeaderAuth` инжектит хедеры |
| **7** | Surface-эмиттеры D: `surfaces/{requests,models,client,cli,mcp,tests,package,root_client}.py` | L1 снапшоты каждого surface + root-client для `me`+`priorities` |
| **8** | Бэкенд+оркестратор+CLI: `backend.py` (+`root_client`) + `generation.py` (грузит `ClientConfig`) + Typer `cli.py` | интеграция: `refract generate` даёт D-дерево + root-client; snapshot round-trip |
| **9** | Оракул L3 + DX + очистка: behavioral-тесты, `--update-snapshots`, удаление старого, research->artifacts, `adding-a-language.md` | L3 opt-in зелёный; старый код удалён; гейт покрытия держится |

---

## Shared Contracts

Единый источник истины для типов/сигнатур/выходных таргетов, на которые ссылаются задачи. Задача, реализующая файл из этого раздела, воспроизводит код **дословно** (не «похоже на»), а TDD-шаги - в теле задачи.

### разд. A / `ir/types.py` - нейтральная сумма типов

```python
"""The neutral type system - a closed, frozen, hashable sum the IR carries verbatim.

Emitters lower a NeutralType to a language type via their TypeMapper; nothing here is
Python-specific (that was the loader's leak this replaces). Dispatch is exhaustive
(`match` + `assert_never`); recursive variants use string forward-refs + model_rebuild().
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ListType", "MapType", "NeutralType", "RefType", "ScalarType"]

Scalar = Literal["string", "integer", "number", "boolean", "any"]


class _Node(BaseModel):
    model_config = ConfigDict(frozen=True)


class ScalarType(_Node):
    kind: Literal["scalar"] = "scalar"
    scalar: Scalar


class RefType(_Node):
    kind: Literal["ref"] = "ref"
    target: str  # a declared Model name


class ListType(_Node):
    kind: Literal["list"] = "list"
    item: "NeutralType"


class MapType(_Node):
    kind: Literal["map"] = "map"
    key: "NeutralType"
    value: "NeutralType"


NeutralType = Annotated[
    Union[ScalarType, RefType, ListType, MapType],
    Field(discriminator="kind"),
]

ListType.model_rebuild()
MapType.model_rebuild()
```

Парсинг из спеки: строковый грамматический вид (`"string"`, `"ref<LocalizedName>"`, `"list<string>"`, `"map<string,integer>"`) разбирается в `spec/nodes.py` в `NeutralType` (см. разд. B-loader). `list`/`map` объявлены, но `me`/`priorities` их не используют (YAGNI-парсинг всё равно реализуется + юнит-тестируется, т.к. это ядро мультиязыка).

### разд. B / `ir/model.py` - frozen-pydantic IR

Дословный перенос текущих dataclass-ов в **frozen pydantic v2**, с двумя семантическими изменениями: `Field.type`/`Param.type` - теперь `NeutralType` (не Python-строка); все коллекции - `tuple[...]`. Никакого пролоуренного Python в IR.

```python
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, JsonValue
from pydantic import Field as PydanticField  # `Field` (below) is the IR model-field class

from refract.ir.types import NeutralType


class _IR(BaseModel):
    model_config = ConfigDict(frozen=True)


class Safety(StrEnum):
    RO = "RO"
    WRITE = "WRITE"
    WRITE_IDEMPOTENT = "WRITE_IDEMPOTENT"
    DESTRUCTIVE = "DESTRUCTIVE"


class TestKind(StrEnum):
    CLIENT = "client"
    CLI = "cli"
    MCP = "mcp"
    MCP_GUARD = "mcp_guard"


class Field(_IR):
    name: str
    type: NeutralType          # was: already-lowered Python string
    optional: bool = False
    default: str | None = None  # source text of an *explicit* spec default; else None
    alias: str | None = None
    description: str | None = None


class ObjectModel(_IR):
    """A pydantic ``APIModel`` subclass with typed fields."""
    kind: Literal["object"] = "object"
    name: str
    fields: tuple[Field, ...] = ()
    documentation: str | None = None


class RootListModel(_IR):
    """A ``RootModel[list[item]]`` public list."""
    kind: Literal["root_list"] = "root_list"
    name: str
    item: str
    documentation: str | None = None


# discriminated union: `item` only on root_list, `fields` only on object -> illegal states
# unrepresentable. envelope (paginated wrapper) is added WITH pagination, not speculatively.
# dead `config` field dropped (0 spec instances, 0 emitter readers).
Model = Annotated[Union[ObjectModel, RootListModel], PydanticField(discriminator="kind")]


class Param(_IR):
    name: str
    loc: Literal["path", "query"]
    type: NeutralType
    optional: bool = False
    default: str | None = None
    alias: str | None = None
    help: str | None = None


class Body(_IR):
    mode: Literal["typed_model"] = "typed_model"
    model: str
    by_alias: bool = True       # -> model_dump(by_alias=...) rendered by the Python backend
    omit_none: bool = True      # -> model_dump(exclude_none=...) rendered by the Python backend


class RequireFound(_IR):
    sentinel: str
    message: str


class McpMeta(_IR):
    name: str
    safety: Safety
    title: str
    documentation: str
    require_found: RequireFound | None = None


class CliMeta(_IR):
    name: str
    documentation: str


class TestCase(_IR):
    name: str
    kind: TestKind
    http_method: str
    path: str
    status: int
    response_json: JsonValue | None   # opaque JSON fixture; validated-at-boundary, repr()'d into tests
    has_json: bool
    asserts: tuple[str, ...]
    call: str


class Operation(_IR):
    name: str
    method: str
    path: str
    operation_id: str
    params: tuple[Param, ...] = ()
    body: Body | None = None
    response_model: str | None = None
    documentation: str | None = None
    mcp: McpMeta | None = None
    cli: CliMeta | None = None
    tests: tuple[TestCase, ...] = ()
    handler: str | None = None


class ModuleDocs(_IR):
    client: str | None = None
    models: str | None = None
    cli: str | None = None
    mcp: str | None = None
    cli_group_help: str | None = None
    mcp_server: str | None = None
    client_class: str | None = None
    requests: str | None = None  # NEW: docstring for the _requests module (D)


class Resource(_IR):
    domain: str
    resource: str
    security: str               # names an AuthScheme in ClientConfig.auth (base_url moved to ClientConfig)
    models: tuple[Model, ...]
    operations: tuple[Operation, ...]
    documentation: str | None = None
    module_docs: ModuleDocs = ModuleDocs()

    def model(self, name: str) -> Model:
        for candidate in self.models:
            if candidate.name == name:
                return candidate
        raise KeyError(name)

    @property
    def domain_title(self) -> str:
        return self.domain.capitalize()
```

> Замечания:
> - `Model` теперь дискриминированный union (`ObjectModel | RootListModel`); `Resource.model(name)` возвращает union, эмиттеры `match`-ят по нему (`case RootListModel()` / `case ObjectModel()` / `assert_never`). Мёртвое поле `config` удалено.
> - typed-множества: `Safety`/`TestKind` - `StrEnum` (импортируемый namespace, hashable, сериализуется по значению); `loc`/`Body.mode` - `Literal` (леанее). `Field`-как-IR-класс конфликтует с `pydantic.Field` -> алиас `PydanticField` только для дискриминатора.
> - `response_json: JsonValue | None` - валидируется на границе (parse-don't-validate), но `JsonValue` с dict/list нехешируем -> `TestCase`/`Operation`/`Resource` не hashable (ок, их не хешируют; `NeutralType` остаётся hashable).
> - `base_url` больше НЕ на `Resource` - переехал в `ClientConfig.server` (он per-API, а не per-resource). `security: str` остаётся ссылкой на схему по имени.
> - pydantic-инстанс с `model()`-методом и `@property` - норм (методы не мешают `frozen`). Дефолт `module_docs=ModuleDocs()` - единый frozen-синглтон, иммутабелен.

### разд. C / `emitters/api.py` - контракт плагина (весь на одной странице)

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from refract import ir
from refract.ir.types import NeutralType

# ---- value objects ----

@dataclass(frozen=True)
class Import:
    """One `from <module> import <name>` atom; the assembler groups + isort-sorts them."""
    module: str
    name: str

@dataclass(frozen=True)
class RenderedType:
    """A language type rendered from a NeutralType, plus the imports it pulls in."""
    text: str
    imports: tuple[Import, ...] = ()

@dataclass(frozen=True)
class Fragment:
    """The typed boundary between UnitRenderer (per-operation) and ResourceAssembler."""
    lines: tuple[str, ...]
    imports: tuple[Import, ...] = ()

@dataclass(frozen=True)
class EmitContext:
    """Per-generation config beyond the resource itself."""
    package_root: str        # where runtime/base/models live, e.g. "ycli.yandex.tracker"
    config: ir.ClientConfig | None = None  # per-API glue; ONLY tests (base_url) + root_client read it;
    # per-resource surfaces (requests/client/models/cli/mcp/package) ignore it, hence the None default.
    # In real generation the Generator always supplies it; tests that read it pass a ClientConfig fixture.

# ---- 5 injected strategies (ABCs) ----

class Naming(ABC):
    @abstractmethod
    def pascal(self, name: str) -> str: ...
    @abstractmethod
    def module_function(self, name: str) -> str: ...      # module-level def-safe: list -> list_
    @abstractmethod
    def class_name(self, base: str, suffix: str) -> str: ...  # merges the 3 *_class helpers

class TypeMapper(ABC):
    @abstractmethod
    def render(self, neutral_type: NeutralType, *, optional: bool) -> RenderedType: ...
    @abstractmethod
    def null_default(self, neutral_type: NeutralType, *, optional: bool) -> str | None: ...

class Formatter(ABC):
    @abstractmethod
    def format(self, source: str) -> str: ...

class Docstrings(ABC):
    @abstractmethod
    def render(self, text: str | None, indent: str) -> tuple[str, ...]: ...

class Layout(ABC):
    @abstractmethod
    def path(self, res: ir.Resource, surface: str) -> str: ...

# ---- renderer / assembler / surface / backend ----

class SurfaceEmitter(ABC):
    """One PER-RESOURCE surface plugin: gates on data presence, emits UNformatted source.

    `name` stays a plain str (NOT an enum): dispatch is registry + `applies()`, never name-compare;
    surface is the extension axis. A unit test enforces the name<->`Layout.path` coupling (decision #22).
    """
    name: str  # "requests" | "client" | "models" | "cli" | "mcp" | "tests" | "package"
    @abstractmethod
    def applies(self, res: ir.Resource) -> bool: ...
    @abstractmethod
    def emit(self, res: ir.Resource, ctx: EmitContext) -> str: ...

class DomainEmitter(ABC):
    """One PER-DOMAIN (per-API) surface = the generated glue. Runs ONCE over ALL resources.

    root_client aggregates resources + builds Session/`httpx.Client(auth=...)` from `ctx.config`.
    """
    name: str  # "root_client"
    @abstractmethod
    def emit(self, resources: tuple[ir.Resource, ...], ctx: EmitContext) -> str: ...

@dataclass(frozen=True)
class LanguageBackend:
    """Pure composition of the 5 strategies + surface emitters. Built by a @backend factory."""
    name: str
    naming: Naming
    type_mapper: TypeMapper
    formatter: Formatter
    docstrings: Docstrings
    layout: Layout
    surfaces: tuple[SurfaceEmitter, ...]              # per-resource
    domain_surfaces: tuple[DomainEmitter, ...] = ()   # per-API glue (root_client)
```

`UnitRenderer`/`ResourceAssembler` - внутренние помощники surface-эмиттера (per-operation -> `Fragment`; per-resource -> рамка + сбор импортов). Они не входят в кросс-задачный контракт (живут внутри `surfaces/`), поэтому определяются в своих задачах; единственная общая граница - `Fragment(lines, imports)`.

### разд. D / Форма операции (read vs write) - БЕЗ отдельного типа (решение #14)

`OpShape`/`classify`/`shapes.py` **УДАЛЕНЫ**. Различие read/write = один bool `op.body is not None` (было 2 потребителя, `TypedWrite.body` производный, 3 из 5 surface его игнорили). Резолверы, которым нужно тело, ветвятся локально и нарроувают тип через локальную переменную:

```python
body = op.body
if body is not None:            # write: body -> model_dump(...) по Body.by_alias / Body.omit_none
    ...                         # `body` здесь narrowed до ir.Body
else:                           # read: только path/query
    ...
```

Форму-сумму (`Cursor`/`OffsetPage`/... для пагинации; LRO/async) вводим, КОГДА придёт вторая реальная ось вариативности - под настоящие требования, с `assert_never`-исчерпываемостью тогда, а не спекулятивно сейчас (решение #20).

### разд. E / `runtime/` - референс-рантайм D (`Request[T]` + `send()`)

refract **ставит** этот рантайм (для L3 и как эталон, который ycli переписывает у себя). Сгенерированный код импортирует аналог из `{package_root}` (см. разд. G).

```python
# runtime/request.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")

@dataclass(frozen=True, slots=True)
class Request(Generic[T]):
    """A pure, transport-agnostic description of one HTTP call - no I/O."""
    method: str
    path: str
    response_model: type[T]
    query: dict[str, Any] | None = None
    json_body: Any = None
```

```python
# runtime/session.py
from __future__ import annotations
from typing import TypeVar
import httpx
from refract.runtime.request import Request

T = TypeVar("T")

class Session:
    """Executes any Request over a PRE-CONFIGURED httpx.Client. AUTH-AGNOSTIC: auth lives on the
    injected client (httpx.Auth), not here. Owns base_url + minimal error policy (the ONLY I/O)."""
    def __init__(self, base_url: str, *, client: httpx.Client) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    def send(self, request: Request[T]) -> T:
        params = {k: v for k, v in (request.query or {}).items() if v is not None}
        response = self._client.request(
            request.method,
            f"{self._base_url}/{request.path}",
            params=params or None,
            json=request.json_body,
        )
        response.raise_for_status()
        return request.response_model.model_validate(response.json())
```

```python
# runtime/auth.py - the auth MECHANISM library (hand-written; grows by rule-of-three)
from __future__ import annotations
from collections.abc import Iterator
import httpx


class HeaderAuth(httpx.Auth):
    """Single-header credential, e.g. ``Authorization: Bearer <token>``. No I/O -> sync+async."""
    def __init__(self, header: str, value: str) -> None:
        self._header = header
        self._value = value

    def auth_flow(self, request: httpx.Request) -> Iterator[httpx.Request]:
        request.headers[self._header] = self._value
        yield request


class MultiHeaderAuth(httpx.Auth):
    """>=1 constant headers (Cloudflare X-Auth-*; Yandex ``Authorization: OAuth ...`` + ``X-Org-Id``)."""
    def __init__(self, headers: dict[str, str]) -> None:
        self._headers = dict(headers)

    def auth_flow(self, request: httpx.Request) -> Iterator[httpx.Request]:
        request.headers.update(self._headers)
        yield request
```

```python
# runtime/base.py - generic per-resource base holding the shared Session (reference; ycli subclasses)
from __future__ import annotations
from refract.runtime.session import Session


class Resource:
    def __init__(self, session: Session) -> None:
        self._session = session
```

`httpx` добавляется в зависимости пакета. `raise_for_status` - минимальная error-политика для L3; полноценные ретраи / error-дискриминаторы / пагинация-итераторы / body-энкодеры растут в core по мере осей (вне scope walking skeleton). `query`-ключи с `None` отбрасываются. **Auth принадлежит инжектируемому `httpx.Client` (`httpx.Auth`), не `send()`** - `Request[T]` навсегда чист. Built-in механизмы под другие схемы (`BearerAuth` = sugar над `HeaderAuth`; `BasicAuth`; `SigV4Auth`, параметризуемый region/service, использует `requires_request_body`; `OAuth2RefreshAuth` - stateful) + custom-hook добавляются по rule-of-three (решение #19/#20).

### разд. F / D-выходные таргеты (полярная звезда surface-эмиттеров = L1-снапшоты)

Эти файлы surface-эмиттеры обязаны воспроизводить (ruff-форматированные). Под D+**F2** (см. разд. G) дельта минимальна: **новый** `_requests.py` на ресурс + **переписанный внутри** `client.py`; `models`/`cli`/`mcp`/`tests`/`__init__` поведенчески идентичны текущим goldens.

**`_requests.<op>`-докстринг** - детерминированный синтез (route-focused, без Example): read -> `` "``{METHOD} /{path}`` -> {response_model} request builder." ``; write -> `` "``{METHOD} /{path}`` - {op.name} request from a typed body." ``. Полная публичная prose (Example-блоки) остаётся на методах `client`.

> **Про перенос строк:** таргеты ниже показаны в «логической» форме; `ruff` (line-length 100) hug-переносит любую сигнатуру/вызов длиннее 100 колонок (напр. `def edit(...)` и его `Request(...)` рвутся на многострочные с trailing-comma). Поэтому снапшот-ассерты проверяют переживающие перенос фрагменты (params-строку, отдельные kwargs), а не одну длинную строку целиком.

#### me/_requests.py (новый)
```python
"""Request builders for Tracker /myself - the single HTTP contract (sans-I/O)."""

from ycli.yandex.tracker.runtime import Request

from .models import Me


def get() -> Request[Me]:
    """``GET /myself`` -> Me request builder."""
    return Request(method="GET", path="myself", response_model=Me)
```

#### me/client.py (переписан внутри; публичный API прежний)
```python
"""Declarative Tracker /myself client - transport ONLY (thin sugar over request builders)."""

from ycli.yandex.tracker.base import TrackerResource

from . import _requests
from .models import Me


class MeClient(TrackerResource):
    """Declarative HTTP for ``/myself``."""

    def get(self) -> Me:
        """``GET /myself`` -> the authenticated ``Me`` (a safe auth probe)."""
        return self._session.send(_requests.get())
```

#### priorities/_requests.py (новый)
```python
"""Request builders for Tracker priorities - the single HTTP contract (sans-I/O)."""

from ycli.yandex.tracker.runtime import Request

from .models import Priority, PriorityCreate, PriorityList, PriorityUpdate


def list_() -> Request[PriorityList]:
    """``GET /priorities`` -> PriorityList request builder."""
    return Request(method="GET", path="priorities", response_model=PriorityList)


def create(body: PriorityCreate) -> Request[Priority]:
    """``POST /priorities/`` - create request from a typed body."""
    return Request(
        method="POST",
        path="priorities/",
        json_body=body.model_dump(by_alias=True, exclude_none=True),
        response_model=Priority,
    )


def edit(priority_id: str, body: PriorityUpdate, *, version: int | None = None) -> Request[Priority]:
    """``PATCH /priorities/{priority_id}`` - edit request from a typed body."""
    return Request(
        method="PATCH",
        path=f"priorities/{priority_id}",
        query={"version": version},
        json_body=body.model_dump(by_alias=True, exclude_none=True),
        response_model=Priority,
    )
```

#### priorities/client.py (переписан внутри; `_verb`/`verb`-split удалён)
```python
"""Declarative Tracker priorities client - transport ONLY (thin sugar over request builders)."""

from ycli.yandex.tracker.base import TrackerResource

from . import _requests
from .models import Priority, PriorityCreate, PriorityList, PriorityUpdate


class PrioritiesClient(TrackerResource):
    """Declarative HTTP for ``/priorities`` (list + create + edit)."""

    def list(self) -> PriorityList:
        """``GET /priorities`` -> priority listing.

        Example:
            >>> client = TrackerClient(oauth_token="...", organization_id="...")  # doctest: +SKIP
            >>> client.priorities.list().root[0].key  # doctest: +SKIP
            'normal'
        """
        return self._session.send(_requests.list_())

    def create(self, body: PriorityCreate) -> Priority:
        """Create a priority from a typed ``PriorityCreate`` body. Returns the new ``Priority``.

        Example:
            >>> client = TrackerClient(oauth_token="...", organization_id="...")  # doctest: +SKIP
            >>> client.priorities.create(
            ...     PriorityCreate(key="one", name=LocalizedName(ru="Низкий"), order=60)
            ... ).key  # doctest: +SKIP
            'one'
        """
        return self._session.send(_requests.create(body))

    def edit(
        self, priority_id: str, body: PriorityUpdate, *, version: int | None = None
    ) -> Priority:
        """Edit priority ``priority_id`` from a typed ``PriorityUpdate`` body.

        ``version`` is the current priority version; when set it is sent as ``?version=`` for
        optimistic locking (the API rejects a stale version with 409).

        Example:
            >>> client = TrackerClient(oauth_token="...", organization_id="...")  # doctest: +SKIP
            >>> client.priorities.edit(
            ...     "one", PriorityUpdate(name=LocalizedName(ru="Низкий")), version=1
            ... ).key  # doctest: +SKIP
            'one'
        """
        return self._session.send(_requests.edit(priority_id, body, version=version))
```

#### tracker/client.py (root-client - GENERATED glue, НОВЫЙ таргет)
```python
"""Tracker client - the composition root (aggregates resources, owns transport + auth)."""

from __future__ import annotations

import os

import httpx

from .me.client import MeClient
from .priorities.client import PrioritiesClient
from .runtime.auth import MultiHeaderAuth
from .runtime.session import Session


class TrackerClient:
    """Root client for the Tracker API."""

    def __init__(self, *, oauth_token: str, organization_id: str) -> None:
        auth = MultiHeaderAuth(
            {"Authorization": f"OAuth {oauth_token}", "X-Org-Id": organization_id}
        )
        session = Session("https://api.tracker.yandex.net/v3", client=httpx.Client(auth=auth))
        self.me = MeClient(session)
        self.priorities = PrioritiesClient(session)

    @classmethod
    def from_env(cls) -> TrackerClient:
        """The single sanctioned env-read point (composition root); components never read env."""
        return cls(
            oauth_token=os.environ["YANDEX_ID_OAUTH_TOKEN"],
            organization_id=os.environ["YANDEX_ID_ORGANIZATION_ID"],
        )
```

Резолвится из `ClientConfig` (`client.yaml`, разд. J): `server.base_url` -> строка `Session(...)`; `auth.oauth_token` (kind=`multi_header`) -> тип механизма (`MultiHeaderAuth`) + рендер словаря headers из templates; `inputs` -> параметры конструктора + `from_env`. Список ресурсов (`.me`/`.priorities`) - из набора `Resource`, загруженных `Generator`'ом (не из `client.yaml`). Ruff hug-переносит длинные строки как обычно.

**Не меняются под D+F2** (surface-эмиттеры Jinja обязаны воспроизвести текущие goldens дословно; они и есть таргеты): `me/models.py`, `me/cli.py`, `me/mcp.py`, `me/__init__.py`, `tests/tracker/test_me.py`, `priorities/models.py`, `priorities/mcp.py`, `priorities/__init__.py` - файлы под `examples/ycli-tracker/golden/**` на момент старта.

**Правки prose в примерах-спеках** (миграция ycli-корпуса на D - часть задачи снапшот-таргетов): убрать uplink-упоминания из `module_docs.client`:
- me: `"Declarative Tracker /myself client (uplink) - transport ONLY."` -> `"Declarative Tracker /myself client - transport ONLY (thin sugar over request builders)."`
- priorities: `"Declarative Tracker priorities client (uplink) - transport ONLY.\n\nNOTE: no ``from __future__``..."` -> `"Declarative Tracker priorities client - transport ONLY (thin sugar over request builders)."`

### разд. G / Зафиксированные проектные решения плана (подтвердить на review-гейте)

**Решение G1 - форма cli/mcp: F2 «client-mediated» (принято по умолчанию).**

| | F2 / client-mediated (принято) | F1 / symmetric build-and-send (буквальная диаграмма разд. 4 спеки) |
|---|---|---|
| cli/mcp вызывают | `client.res.op(...)` (сахар) | `session.send(_requests.op(...))` напрямую |
| Эмитируемая дельта cli/mcp | **нулевая** (идентичны текущим goldens) | переписаны + нужен источник `session` через DI |
| HTTP-контракт | централизован в `_requests`, cli/mcp наследуют его через сахар | централизован в `_requests`, cli/mcp строят Request сами |
| Дрейф cli<->client | невозможен (одна кодовая тропа) | возможен (cli/mcp дублируют send-тропу) |
| Стоимость миграции ycli | минимальная | требует ycli-DI, отдающего sendable-session в cli/mcp |

**Почему F2 (вопреки буквальной диаграмме разд. 4):** достигает всех целей D (убирает `_verb`/`verb`-костыль, централизует HTTP-контракт в `_requests`, единый `send`-executor), но эмитирует строго меньше кода, не изобретает ycli-DI и структурно защищён от дрейфа cli<->client. Существенное свидетельство: под F2 дельта D = только новый `_requests.py` + внутренности `client.py`; 8 из 12 surface-файлов `me`+`priorities` не меняются. Диаграмма разд. 4 - это идея «один Request, много потребителей»; F2 сохраняет её суть, просто потребитель cli/mcp - сахар, а не прямой `send`. **Если хочешь буквальный F1 - переверни на review, задачи фазы 7 (cli/mcp) поменяются.**

**Решение G2 - import-root: `EmitContext.package_root` (дефолт `ycli.yandex.{domain}`).** Сгенерированный код тянет рантайм из `{package_root}.runtime` (`Request`) и базу-сессию из `{package_root}.base` (`{Domain}Resource`), модели - из `.models`. Дефолт воспроизводит текущую ycli-конвенцию (снапшоты `me`/`priorities` совпадают с ycli-миром); параметризация раз-хардкодит «ycli» и даёт L3 подставить `refract.runtime` + тестовую базу. Это де-вартит текущий хардкод `f"ycli.yandex.{domain}"` в эмиттерах.

**Решение G3 - L2 отложен.** D-стиля ycli-goldens не существует -> стартовый L2 (byte-identical vs ycli) пуст; корректность на старте держат L0 (юниты) + L1 (снапшоты собственного D-вывода) + L3 (поведенческий на фикстуре с `refract.runtime`). L2 пересобирается, когда ycli реально мигрирует на D.

**Замечание про гейт покрытия (big-bang-реальность):** при переписывании `refract generate` end-to-end сломан от фазы 0 до фазы 8 - это принятый трейдофф big-bang. Чтобы TDD-цикл не блокировался тавтологичным `--cov-fail-under=100`, он **временно ослаблен до `0`** на время перестройки (фаза 0) и **восстановлен до `100` в фазе 9** с явной проверкой полного покрытия нового `src/refract`. Каждая задача всё равно пишет тесты TDD-стилем, так что покрытие естественно растёт; фаза 9 ловит любой недотест.

**Новые решения ревизии (детали - спека разд. 3, #14-#23):**
- **G5 (#18/#19) - auth в core, glue генерим:** библиотека механизмов (`httpx.Auth`) руками в `runtime/auth.py`; root-client + auth-selection генерятся из `ClientConfig`. `AuthScheme`-union (разд. H). refract - публичный тул: для произвольного API glue нельзя писать руками.
- **G6 (#23) - единый `client.yaml`:** server + default_headers + auth; `base_url` уходит из `resource.yaml` (разд. I/разд. J). Парсинг - Phase 2.
- **G7 (#14) - `shapes.py` удалён:** нет Task 3.3-«classify»/`OpShape`; резолверы 7.1/7.2 ветвятся на `op.body` локально (разд. D).
- **G8 (#15/#16/#17) - typed IR:** `Model`-union, `Safety`/`TestKind` StrEnum, `loc`/`mode` Literal, `Body.dump`->`by_alias`/`omit_none`, `response_json`->`JsonValue` (разд. B). Ломает loader (`_model`/`_field`/`_body`) + models-resolver (union-`match`) - правки в Phase 2/7.
- **G9 (#20) - оси не спекулятивны:** строим срез walking skeleton; union'ы (`AuthScheme`/`Model`) растут аддитивно, каждый вариант - под реальный API + byte-target.
- **G10 (#18) - `DomainEmitter`:** root_client per-API (не per-resource), бежит один раз над всеми ресурсами (разд. C); `Generator` вызывает `backend.domain_surfaces` после per-resource surfaces (Phase 8).

### разд. H / `ir/auth.py` - `AuthScheme`-union

```python
from __future__ import annotations
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field


class _Auth(BaseModel):
    model_config = ConfigDict(frozen=True)


class AuthInput(_Auth):
    """One named credential input + its default source (env var)."""
    name: str
    env: str | None = None                 # env var name; None -> must be passed explicitly


class HeaderAuth(_Auth):
    """Single templated header, e.g. ``Authorization: Bearer {token}`` (most bearer APIs)."""
    kind: Literal["header"] = "header"
    header: str
    template: str                          # "{token}" placeholders resolved from `inputs`
    inputs: tuple[AuthInput, ...]


class MultiHeaderAuth(_Auth):
    """>=1 templated headers (Cloudflare X-Auth-*; Yandex ``OAuth {token}`` + ``X-Org-Id``)."""
    kind: Literal["multi_header"] = "multi_header"
    headers: tuple[tuple[str, str], ...]   # (header-name, template) pairs; hashable ordered map
    inputs: tuple[AuthInput, ...]


AuthScheme = Annotated[Union[HeaderAuth, MultiHeaderAuth], Field(discriminator="kind")]
```

Построены `HeaderAuth` (bearer-мажорити 15-API-свипа) + `MultiHeaderAuth` (Yandex). Названы, растут по rule-of-three: `BasicAuth`, `ApiKeyQueryAuth`, `SigV4Auth` (built-in механизм, params region/service), `OAuth2RefreshAuth` (stateful), `CustomAuth` (`impl`-import + hook). Механизм каждой - `httpx.Auth` в `runtime/auth.py` (разд. E); дескриптор описывает, КАК построить value.

### разд. I / `ir/client.py` - `ClientConfig` + `Server`

```python
from __future__ import annotations
from pydantic import BaseModel, ConfigDict

from refract.ir.auth import AuthScheme   # discriminated-union alias (разд. H)


class _Client(BaseModel):
    model_config = ConfigDict(frozen=True)


class Server(_Client):
    """Fixed base URL for the walking skeleton; a templated server (variables) grows later."""
    base_url: str


class ClientConfig(_Client):
    """Per-API glue config (from client.yaml): server + default headers + named auth schemes."""
    name: str                                        # API name, e.g. "tracker"
    server: Server
    default_headers: tuple[tuple[str, str], ...] = ()
    auth: tuple[tuple[str, AuthScheme], ...] = ()    # scheme-name -> scheme (ordered, hashable)
```

`Resource.security` (`str`) индексирует `ClientConfig.auth` по имени. `base_url` теперь ЗДЕСЬ, не на `Resource`. `default_headers` - const/optional не-auth хедеры (`Notion-Version` и т.п.; пусто у Tracker). `ir/__init__` реэкспортирует `ClientConfig`/`Server`/`AuthScheme`/`AuthInput`/`HeaderAuth`/`MultiHeaderAuth`.

### разд. J / `client.yaml` формат (per-API glue)

`examples/ycli-tracker/client.yaml` (миграция `_auth.yaml`; `base_url` уходит из `resource.yaml`):

```yaml
name: tracker
server:
  base_url: https://api.tracker.yandex.net/v3
default_headers: {}
auth:
  oauth_token:
    kind: multi_header
    headers:
      Authorization: "OAuth {oauth_token}"
      X-Org-Id: "{organization_id}"
    inputs:
      oauth_token: {env: YANDEX_ID_OAUTH_TOKEN}
      organization_id: {env: YANDEX_ID_ORGANIZATION_ID}
```

Парсится `spec/nodes.py` (нода `ClientConfigNode`, `extra="forbid"`) -> `ir.ClientConfig` (mapping `headers`/`inputs` -> tuple-of-pairs). `SpecLoader.load` теперь грузит И `resource.yaml`-ы домена, И `client.yaml` (ищет рядом/выше). `resource.yaml` теряет `base_url`, сохраняет `security: oauth_token`.

---

## PHASE 0 / src-layout + чистый старт

### Task 0.1: Переезд в src-layout

**Files:**
- Move: `refract/` -> `src/refract/` (git mv, сохраняя историю)
- Modify: `pyproject.toml` (packaging/ruff/coverage/ty пути)

**Interfaces:**
- Produces: пакет импортируется как `refract` из `src/`-layout; все последующие задачи создают файлы под `src/refract/`.

- [ ] **Step 1: Перенести дерево пакета**

```bash
git mv refract src/refract
```

- [ ] **Step 2: Обновить пути в `pyproject.toml`**

Заменить блоки на:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/refract"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--strict-markers --cov=refract --cov-report=term-missing --cov-fail-under=100"

[tool.coverage.run]
source = ["src/refract"]

[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src", "tests"]
extend-exclude = ["examples"]
```
(`--cov=refract` остаётся: пакет ставится editable и импортируется по имени. `ty` `exclude = ["examples"]` - без изменений.)

- [ ] **Step 3: Переустановить editable + прогнать текущую сюиту (должна остаться зелёной - это чистый перенос)**

Run: `uv pip install -e . && pytest -q`
Expected: PASS (все существующие тесты; байт-идентичность goldens не тронута переносом).

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "refactor: move package to src/ layout"
```

### Task 0.2: Чистый старт под перестройку

**Files:**
- Delete: `src/refract/emitters/python/{_common,client,cli,mcp,models,tests}.py`, `src/refract/{loader,generate,format}.py`, все `tests/test_*.py`
- Modify: `pyproject.toml` (ослабить гейт покрытия), `src/refract/cli.py` (минимальный Typer-стаб)
- Keep: `src/refract/ir/` (перепишется в фазе 1), `examples/**` (спеки + goldens - референс разд. F), `tests/conftest.py`

**Interfaces:**
- Produces: `refract` импортируется; `pytest` зелёный на почти-пустой сюите; entry point `refract.cli:app` существует (стаб).

- [ ] **Step 1: Удалить старый пайплайн и старые тесты**

```bash
git rm src/refract/emitters/python/_common.py src/refract/emitters/python/client.py \
  src/refract/emitters/python/cli.py src/refract/emitters/python/mcp.py \
  src/refract/emitters/python/models.py src/refract/emitters/python/tests.py \
  src/refract/loader.py src/refract/generate.py src/refract/format.py
git rm tests/test_*.py
```
(`examples/**` и `tests/conftest.py` НЕ трогаем - goldens нужны как референс разд. F; conftest перепишется в фазе 2.)

- [ ] **Step 2: Ослабить гейт покрытия на время перестройки + importlib-режим**

В `pyproject.toml` `[tool.pytest.ini_options]`:
```toml
addopts = "--strict-markers --import-mode=importlib --cov=refract --cov-report=term-missing --cov-fail-under=0"
```
(`--import-mode=importlib` обязателен: `tests/` зеркалит `src/`, и одинаковые basename - напр. `tests/ir/test_types.py` (NeutralType) и `tests/emitters/python/test_types.py` (PythonTypeMapper) - иначе конфликтуют в rootdir-режиме. Все зеркальные тест-директории получают `__init__.py`? Нет - с `importlib` они не нужны.)

- [ ] **Step 3: Заменить `src/refract/cli.py` минимальным Typer-стабом** (полноценно - в фазе 8)

```python
"""The ``refract`` console-script entry point (Typer). Full wiring lands in Phase 8."""

from __future__ import annotations

import typer

app = typer.Typer(name="refract", no_args_is_help=True, add_completion=False)


@app.command()
def generate() -> None:
    """Render every resource spec into its per-(surface) output (not yet wired)."""
    raise NotImplementedError("refract generate is being rebuilt (Workstream A, Phase 8)")
```

- [ ] **Step 4: Добавить `typer` в зависимости** (`pyproject.toml` `[project] dependencies`): `"typer>=0.26.8"`. Удалить `uplink`/`fastmcp` из зависимостей, если присутствуют (их не было - только `pydantic`/`pyyaml`/`ruff`; оставить). Добавить `"httpx>=0.28"` (для рантайма, фаза 6) и `"jinja2>=3.1.6"`.

- [ ] **Step 5: Прогнать - зелено на пустой сюите**

Run: `uv pip install -e . && pytest -q && python -c "import refract, refract.cli"`
Expected: PASS (0-few тестов), импорт чистый.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "refactor!: clear old procedural pipeline for the D rebuild"
```

### Task 0.3: `__version__` из метадаты

**Files:**
- Modify: `src/refract/__init__.py`
- Test: `tests/test_version.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_version.py
import refract


def test_version_is_read_from_metadata():
    # importlib.metadata.version("refract") for the installed dist; never the hardcoded "0.0.0".
    assert refract.__version__ != "0.0.0"
    assert refract.__version__  # non-empty string
```

- [ ] **Step 2: Прогнать - падает** (`__version__` пока `"0.0.0"`)

Run: `pytest tests/test_version.py -q` -> FAIL

- [ ] **Step 3: Реализовать**

```python
# src/refract/__init__.py
"""refract - a language-agnostic, spec-driven multi-surface code generator."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("refract")
except PackageNotFoundError:  # not installed (raw checkout on sys.path)
    __version__ = "0.0.0+unknown"
```

- [ ] **Step 4: Прогнать - зелено**

Run: `pytest tests/test_version.py -q` -> PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: read __version__ from installed package metadata"
```

---

## PHASE 1 / Нейтральный IR

**Deliverable:** типизированный frozen-pydantic IR целиком -> `ir/types` (NeutralType-сумма), `ir/model` (Model-union `ObjectModel | RootListModel` + `Safety`/`TestKind`), `ir/auth` (AuthScheme-union), `ir/client` (`ClientConfig` + `Server`), плюс `ir/__init__` - единая реэкспорт-поверхность. Ломающие правки loader'а (`_model`/`_field`/`_body`) и резолверов (union-`match`) откладываются в Phase 2/7 (решения G6/G8). Порядок сборки внутри фазы: 1.1 -> 1.2 -> 1.4 -> 1.5 -> 1.3 (реэкспорт тянет из `ir.auth`/`ir.client`, поэтому его зелёный гейт прогоняется последним).

### Task 1.1: `ir/types.py` - `NeutralType`-сумма

**Files:**
- Create: `src/refract/ir/types.py`
- Test: `tests/ir/test_types.py`

**Interfaces:**
- Produces: `ScalarType`, `RefType`, `ListType`, `MapType`, `NeutralType` (см. разд. A). Потребляется `ir/model.py`, `spec/`, `TypeMapper`, `shapes`.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/ir/test_types.py
import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from refract.ir.types import ListType, MapType, NeutralType, RefType, ScalarType

_adapter = TypeAdapter(NeutralType)


def test_scalar_parses_by_discriminator():
    assert _adapter.validate_python({"kind": "scalar", "scalar": "integer"}) == ScalarType(
        scalar="integer"
    )


def test_ref_parses():
    assert _adapter.validate_python({"kind": "ref", "target": "Me"}) == RefType(target="Me")


def test_recursive_list_of_ref():
    parsed = _adapter.validate_python(
        {"kind": "list", "item": {"kind": "ref", "target": "Priority"}}
    )
    assert parsed == ListType(item=RefType(target="Priority"))


def test_map_is_recursive_both_sides():
    parsed = _adapter.validate_python(
        {"kind": "map", "key": {"kind": "scalar", "scalar": "string"},
         "value": {"kind": "scalar", "scalar": "integer"}}
    )
    assert parsed == MapType(key=ScalarType(scalar="string"), value=ScalarType(scalar="integer"))


def test_variants_are_frozen_and_hashable():
    s = ScalarType(scalar="string")
    with pytest.raises(ValidationError):
        s.scalar = "integer"  # frozen
    assert hash(s) == hash(ScalarType(scalar="string"))
    assert {s, ScalarType(scalar="string")} == {s}  # dedups -> hashable


def test_unknown_kind_rejected():
    with pytest.raises(ValidationError):
        _adapter.validate_python({"kind": "bogus"})
```

- [ ] **Step 2: Прогнать - падает** (модуль отсутствует)

Run: `pytest tests/ir/test_types.py -q` -> FAIL (ImportError)

- [ ] **Step 3: Реализовать `src/refract/ir/types.py` дословно по разд. A**

(См. Shared Contracts разд. A - включая `ListType.model_rebuild()` / `MapType.model_rebuild()` после определения `NeutralType`.)

- [ ] **Step 4: Прогнать - зелено**

Run: `pytest tests/ir/test_types.py -q` -> PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(ir): add neutral discriminated type sum (NeutralType)"
```

### Task 1.2: `ir/model.py` - frozen-pydantic IR

**Files:**
- Modify (rewrite): `src/refract/ir/model.py`
- Test: `tests/ir/test_model.py`

**Interfaces:**
- Consumes: `NeutralType` (разд. A).
- Produces: `Field`, `ObjectModel`, `RootListModel`, `Model` (union), `Safety`, `TestKind`, `Param`, `Body`, `RequireFound`, `McpMeta`, `CliMeta`, `TestCase`, `Operation`, `ModuleDocs`, `Resource` - все frozen-pydantic, tuple-коллекции, `Field.type`/`Param.type: NeutralType` (см. разд. B). Потребляется `spec/loader`, эмиттерами, резолверами.
- Ключевые сдвиги vs старый dataclass-модуль (все из разд. B): `Model` -> дискриминированный union `ObjectModel | RootListModel` (мёртвое `config`-поле удалено, envelope НЕ добавляется спекулятивно); `Safety`/`TestKind` - `StrEnum`; `Param.loc: Literal["path","query"]`; `Body` несёт `by_alias`/`omit_none` (старое `dump` удалено); `McpMeta.safety: Safety`; `TestCase.kind: TestKind` + `response_json: JsonValue | None`; `Resource` теряет `base_url` (оставляет `security: str`). `pydantic.Field` импортируется как `PydanticField` (коллизия с IR-классом `Field`).

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/ir/test_model.py
import pytest
from pydantic import TypeAdapter, ValidationError

from refract import ir
from refract.ir.types import RefType, ScalarType


def _field(name="uid", type=ScalarType(scalar="integer"), **kw):
    return ir.Field(name=name, type=type, **kw)


def test_field_carries_neutral_type_not_python_string():
    f = _field(optional=True)
    assert f.type == ScalarType(scalar="integer")  # NOT "int | None"


def test_object_and_root_list_are_distinct_variants():
    me = ir.ObjectModel(name="Me", fields=(_field(),))
    priorities = ir.RootListModel(name="PriorityList", item="Priority")
    assert me.kind == "object"
    assert priorities.kind == "root_list"
    assert me.fields[0].name == "uid"
    assert priorities.item == "Priority"


def test_model_union_parses_by_discriminator():
    adapter = TypeAdapter(ir.Model)
    obj = adapter.validate_python(
        {"kind": "object", "name": "Me",
         "fields": [{"name": "uid", "type": {"kind": "scalar", "scalar": "integer"}}]}
    )
    lst = adapter.validate_python({"kind": "root_list", "name": "PriorityList", "item": "Priority"})
    assert isinstance(obj, ir.ObjectModel)
    assert isinstance(lst, ir.RootListModel)


def test_resource_is_frozen_and_hashable():
    res = ir.Resource(
        domain="tracker", resource="me", security="oauth_token",
        models=(ir.ObjectModel(name="Me", fields=(_field(),)),),
        operations=(ir.Operation(name="get", method="GET", path="myself", operation_id="me_get"),),
    )
    assert hash(res)  # tuple collections keep it hashable
    with pytest.raises(ValidationError):
        res.domain = "x"  # frozen


def test_list_input_is_coerced_to_tuple():
    m = ir.ObjectModel(name="Me", fields=[_field()])  # list input
    assert isinstance(m.fields, tuple)


def test_ref_field_type_roundtrips():
    f = _field(type=RefType(target="LocalizedName"))
    assert f.type == RefType(target="LocalizedName")


def test_resource_model_accessor_and_domain_title():
    me = ir.ObjectModel(name="Me", fields=(_field(),))
    plist = ir.RootListModel(name="PriorityList", item="Priority")
    res = ir.Resource(domain="tracker", resource="me",
                      security="oauth_token", models=(me, plist), operations=())
    assert res.model("Me") is me
    assert res.model("PriorityList") is plist
    resolved = res.model("Me")
    assert isinstance(resolved, ir.ObjectModel)  # Me is the ObjectModel branch
    assert resolved.fields[0].name == "uid"
    assert res.domain_title == "Tracker"
    with pytest.raises(KeyError):
        res.model("Nope")


def test_safety_and_test_kind_accept_string_values():
    assert ir.Safety("RO") is ir.Safety.RO
    assert ir.Safety("DESTRUCTIVE") is ir.Safety.DESTRUCTIVE
    assert ir.TestKind("client") is ir.TestKind.CLIENT
    assert ir.TestKind("mcp_guard") is ir.TestKind.MCP_GUARD


def test_body_carries_dump_flags_and_is_frozen():
    b = ir.Body(model="PriorityCreate", by_alias=False, omit_none=False)
    assert b.mode == "typed_model"
    assert (b.by_alias, b.omit_none) == (False, False)
    with pytest.raises(ValidationError):
        b.by_alias = True  # frozen
```

- [ ] **Step 2: Прогнать - падает**

Run: `pytest tests/ir/test_model.py -q` -> FAIL

- [ ] **Step 3: Реализовать `src/refract/ir/model.py` дословно по разд. B**

(Полностью заменить старый dataclass-модуль содержимым разд. B - воспроизведено дословно ниже.)

```python
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, JsonValue
from pydantic import Field as PydanticField  # `Field` (below) is the IR model-field class

from refract.ir.types import NeutralType


class _IR(BaseModel):
    model_config = ConfigDict(frozen=True)


class Safety(StrEnum):
    RO = "RO"
    WRITE = "WRITE"
    WRITE_IDEMPOTENT = "WRITE_IDEMPOTENT"
    DESTRUCTIVE = "DESTRUCTIVE"


class TestKind(StrEnum):
    CLIENT = "client"
    CLI = "cli"
    MCP = "mcp"
    MCP_GUARD = "mcp_guard"


class Field(_IR):
    name: str
    type: NeutralType          # was: already-lowered Python string
    optional: bool = False
    default: str | None = None  # source text of an *explicit* spec default; else None
    alias: str | None = None
    description: str | None = None


class ObjectModel(_IR):
    """A pydantic ``APIModel`` subclass with typed fields."""
    kind: Literal["object"] = "object"
    name: str
    fields: tuple[Field, ...] = ()
    documentation: str | None = None


class RootListModel(_IR):
    """A ``RootModel[list[item]]`` public list."""
    kind: Literal["root_list"] = "root_list"
    name: str
    item: str
    documentation: str | None = None


# discriminated union: `item` only on root_list, `fields` only on object -> illegal states
# unrepresentable. envelope (paginated wrapper) is added WITH pagination, not speculatively.
# dead `config` field dropped (0 spec instances, 0 emitter readers).
Model = Annotated[Union[ObjectModel, RootListModel], PydanticField(discriminator="kind")]


class Param(_IR):
    name: str
    loc: Literal["path", "query"]
    type: NeutralType
    optional: bool = False
    default: str | None = None
    alias: str | None = None
    help: str | None = None


class Body(_IR):
    mode: Literal["typed_model"] = "typed_model"
    model: str
    by_alias: bool = True       # -> model_dump(by_alias=...) rendered by the Python backend
    omit_none: bool = True      # -> model_dump(exclude_none=...) rendered by the Python backend


class RequireFound(_IR):
    sentinel: str
    message: str


class McpMeta(_IR):
    name: str
    safety: Safety
    title: str
    documentation: str
    require_found: RequireFound | None = None


class CliMeta(_IR):
    name: str
    documentation: str


class TestCase(_IR):
    name: str
    kind: TestKind
    http_method: str
    path: str
    status: int
    response_json: JsonValue | None   # opaque JSON fixture; validated-at-boundary, repr()'d into tests
    has_json: bool
    asserts: tuple[str, ...]
    call: str


class Operation(_IR):
    name: str
    method: str
    path: str
    operation_id: str
    params: tuple[Param, ...] = ()
    body: Body | None = None
    response_model: str | None = None
    documentation: str | None = None
    mcp: McpMeta | None = None
    cli: CliMeta | None = None
    tests: tuple[TestCase, ...] = ()
    handler: str | None = None


class ModuleDocs(_IR):
    client: str | None = None
    models: str | None = None
    cli: str | None = None
    mcp: str | None = None
    cli_group_help: str | None = None
    mcp_server: str | None = None
    client_class: str | None = None
    requests: str | None = None  # NEW: docstring for the _requests module (D)


class Resource(_IR):
    domain: str
    resource: str
    security: str               # names an AuthScheme in ClientConfig.auth (base_url moved to ClientConfig)
    models: tuple[Model, ...]
    operations: tuple[Operation, ...]
    documentation: str | None = None
    module_docs: ModuleDocs = ModuleDocs()

    def model(self, name: str) -> Model:
        for candidate in self.models:
            if candidate.name == name:
                return candidate
        raise KeyError(name)

    @property
    def domain_title(self) -> str:
        return self.domain.capitalize()
```

- [ ] **Step 4: Прогнать - зелено**

Run: `pytest tests/ir/test_model.py -q` -> PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor(ir): frozen pydantic IR carrying NeutralType (Model union, Safety/TestKind)"
```

### Task 1.3: `ir/__init__.py` - реэкспорты

**Files:**
- Modify: `src/refract/ir/__init__.py`
- Test: `tests/ir/test_init.py`

> Зависимость сборки: реэкспорт тянет из `ir.model`, `ir.types`, `ir.auth` (Task 1.4) и `ir.client` (Task 1.5) -> прогоняй зелёный гейт 1.3 ПОСЛЕ 1.4/1.5. Это единственная обратная зависимость внутри фазы.

- [ ] **Step 1: Тест**

```python
# tests/ir/test_init.py
from refract import ir
from refract.ir.types import NeutralType


def test_ir_reexports_public_surface():
    for name in (
        "Field", "Model", "ObjectModel", "RootListModel", "Param", "Operation",
        "Resource", "ModuleDocs", "Body", "McpMeta", "CliMeta", "TestCase",
        "RequireFound", "Safety", "TestKind",
        "AuthScheme", "AuthInput", "HeaderAuth", "MultiHeaderAuth",
        "ClientConfig", "Server",
    ):
        assert hasattr(ir, name)
    assert ir.NeutralType is NeutralType
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать**

```python
# src/refract/ir/__init__.py
"""The typed, language-neutral IR every emitter reads."""

from refract.ir.auth import AuthInput, AuthScheme, HeaderAuth, MultiHeaderAuth
from refract.ir.client import ClientConfig, Server
from refract.ir.model import (
    Body, CliMeta, Field, McpMeta, Model, ModuleDocs, ObjectModel, Operation,
    Param, RequireFound, Resource, RootListModel, Safety, TestCase, TestKind,
)
from refract.ir.types import ListType, MapType, NeutralType, RefType, ScalarType

__all__ = [
    "AuthInput", "AuthScheme", "Body", "CliMeta", "ClientConfig", "Field",
    "HeaderAuth", "ListType", "MapType", "McpMeta", "Model", "ModuleDocs",
    "MultiHeaderAuth", "NeutralType", "ObjectModel", "Operation", "Param",
    "RefType", "RequireFound", "Resource", "RootListModel", "Safety",
    "ScalarType", "Server", "TestCase", "TestKind",
]
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(ir): re-export IR (types + model + auth + client) from refract.ir`)

### Task 1.4: `ir/auth.py` - `AuthScheme`-union

**Files:**
- Create: `src/refract/ir/auth.py`
- Test: `tests/ir/test_auth.py`

**Interfaces:**
- Produces: `AuthInput`, `HeaderAuth`, `MultiHeaderAuth`, `AuthScheme` (дискриминированный union по `kind`; см. разд. H). Потребляется `ir/client.py` (`ClientConfig.auth`), `spec/nodes.py` (парсинг `client.yaml`, Phase 2), root_client-эмиттером (Phase 8). Дескриптор описывает, КАК построить value; сам механизм (`httpx.Auth`) живёт в `runtime/auth.py` (разд. E).

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/ir/test_auth.py
import pytest
from pydantic import TypeAdapter, ValidationError

from refract.ir.auth import AuthInput, AuthScheme, HeaderAuth, MultiHeaderAuth

_adapter = TypeAdapter(AuthScheme)


def test_header_auth_parses_by_discriminator():
    parsed = _adapter.validate_python(
        {"kind": "header", "header": "Authorization", "template": "Bearer {token}",
         "inputs": [{"name": "token", "env": "API_TOKEN"}]}
    )
    assert isinstance(parsed, HeaderAuth)
    assert parsed.header == "Authorization"
    assert parsed.inputs[0] == AuthInput(name="token", env="API_TOKEN")


def test_multi_header_auth_parses_by_discriminator():
    parsed = _adapter.validate_python(
        {"kind": "multi_header",
         "headers": [["Authorization", "OAuth {token}"], ["X-Org-Id", "{organization_id}"]],
         "inputs": [{"name": "token", "env": "YANDEX_ID_OAUTH_TOKEN"},
                    {"name": "organization_id", "env": "YANDEX_ID_ORGANIZATION_ID"}]}
    )
    assert isinstance(parsed, MultiHeaderAuth)
    assert parsed.headers == (("Authorization", "OAuth {token}"), ("X-Org-Id", "{organization_id}"))


def test_auth_input_env_defaults_to_none():
    assert AuthInput(name="token").env is None
    assert AuthInput(name="token", env="API_TOKEN").env == "API_TOKEN"


def test_auth_scheme_is_frozen():
    scheme = HeaderAuth(header="Authorization", template="Bearer {token}",
                        inputs=(AuthInput(name="token", env="API_TOKEN"),))
    with pytest.raises(ValidationError):
        scheme.header = "X"  # frozen
```

- [ ] **Step 2: Прогнать - падает** (модуль отсутствует)

Run: `pytest tests/ir/test_auth.py -q` -> FAIL (ImportError)

- [ ] **Step 3: Реализовать `src/refract/ir/auth.py` дословно по разд. H**

```python
from __future__ import annotations
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field


class _Auth(BaseModel):
    model_config = ConfigDict(frozen=True)


class AuthInput(_Auth):
    """One named credential input + its default source (env var)."""
    name: str
    env: str | None = None                 # env var name; None -> must be passed explicitly


class HeaderAuth(_Auth):
    """Single templated header, e.g. ``Authorization: Bearer {token}`` (most bearer APIs)."""
    kind: Literal["header"] = "header"
    header: str
    template: str                          # "{token}" placeholders resolved from `inputs`
    inputs: tuple[AuthInput, ...]


class MultiHeaderAuth(_Auth):
    """>=1 templated headers (Cloudflare X-Auth-*; Yandex ``OAuth {token}`` + ``X-Org-Id``)."""
    kind: Literal["multi_header"] = "multi_header"
    headers: tuple[tuple[str, str], ...]   # (header-name, template) pairs; hashable ordered map
    inputs: tuple[AuthInput, ...]


AuthScheme = Annotated[Union[HeaderAuth, MultiHeaderAuth], Field(discriminator="kind")]
```

- [ ] **Step 4: Прогнать - зелено**

Run: `pytest tests/ir/test_auth.py -q` -> PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(ir): AuthScheme union (header + multi_header)"
```

### Task 1.5: `ir/client.py` - `ClientConfig` + `Server`

**Files:**
- Create: `src/refract/ir/client.py`
- Test: `tests/ir/test_client.py`

**Interfaces:**
- Consumes: `AuthScheme` (разд. H).
- Produces: `Server` (fixed `base_url`), `ClientConfig` (per-API glue: `server` + `default_headers` + named `auth` tuple-map; см. разд. I). `Resource.security` (`str`) индексирует `ClientConfig.auth` по имени; `base_url` теперь ЗДЕСЬ, не на `Resource`. Потребляется `EmitContext.config` (разд. C), root_client-эмиттером (Phase 8), `spec/nodes.py` (`client.yaml`, Phase 2).

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/ir/test_client.py
import pytest
from pydantic import ValidationError

from refract.ir.auth import AuthInput, MultiHeaderAuth
from refract.ir.client import ClientConfig, Server


def _tracker_config():
    return ClientConfig(
        name="tracker",
        server=Server(base_url="https://api.tracker.yandex.net/v3"),
        auth=(
            ("oauth_token", MultiHeaderAuth(
                headers=(("Authorization", "OAuth {token}"), ("X-Org-Id", "{organization_id}")),
                inputs=(AuthInput(name="token", env="YANDEX_ID_OAUTH_TOKEN"),
                        AuthInput(name="organization_id", env="YANDEX_ID_ORGANIZATION_ID")),
            )),
        ),
    )


def test_client_config_holds_server_and_defaults():
    config = _tracker_config()
    assert config.server.base_url == "https://api.tracker.yandex.net/v3"
    assert config.default_headers == ()


def test_auth_tuple_map_roundtrips_and_keeps_variant():
    config = _tracker_config()
    by_name = dict(config.auth)               # tuple-of-pairs behaves as an ordered map
    scheme = by_name["oauth_token"]
    assert isinstance(scheme, MultiHeaderAuth)  # discriminated variant survived
    assert scheme.headers[0] == ("Authorization", "OAuth {token}")


def test_client_config_parses_auth_by_discriminator_from_dict():
    config = ClientConfig.model_validate({
        "name": "tracker",
        "server": {"base_url": "https://api.tracker.yandex.net/v3"},
        "auth": [["oauth_token", {
            "kind": "multi_header",
            "headers": [["Authorization", "OAuth {token}"]],
            "inputs": [{"name": "token", "env": "YANDEX_ID_OAUTH_TOKEN"}],
        }]],
    })
    assert isinstance(dict(config.auth)["oauth_token"], MultiHeaderAuth)


def test_client_config_is_frozen():
    config = _tracker_config()
    with pytest.raises(ValidationError):
        config.name = "other"  # frozen
```

- [ ] **Step 2: Прогнать - падает** (модуль отсутствует)

Run: `pytest tests/ir/test_client.py -q` -> FAIL (ImportError)

- [ ] **Step 3: Реализовать `src/refract/ir/client.py` дословно по разд. I**

```python
from __future__ import annotations
from pydantic import BaseModel, ConfigDict

from refract.ir.auth import AuthScheme   # discriminated-union alias (разд. H)


class _Client(BaseModel):
    model_config = ConfigDict(frozen=True)


class Server(_Client):
    """Fixed base URL for the walking skeleton; a templated server (variables) grows later."""
    base_url: str


class ClientConfig(_Client):
    """Per-API glue config (from client.yaml): server + default headers + named auth schemes."""
    name: str                                        # API name, e.g. "tracker"
    server: Server
    default_headers: tuple[tuple[str, str], ...] = ()
    auth: tuple[tuple[str, AuthScheme], ...] = ()    # scheme-name -> scheme (ordered, hashable)
```

- [ ] **Step 4: Прогнать - зелено**

Run: `pytest tests/ir/test_client.py -q` -> PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(ir): ClientConfig + Server"
```

---

## PHASE 2 / Декомпозиция loader -> `spec/` (нейтральный)

### Task 2.1: Парсер spec-строк -> `NeutralType`

**Files:**
- Create: `src/refract/spec/__init__.py` (пустой пакет-маркер пока), `src/refract/spec/loader.py` (начинаем с парсера + `SpecError`)
- Test: `tests/spec/test_neutral_parse.py`

**Interfaces:**
- Produces: `SpecError(Exception)`; `parse_neutral_type(text: str) -> NeutralType` - грамматика `string|integer|number|boolean|any`, `ref<Model>`, `list<T>`, `map<K,V>` (рекурсивно). Заменяет старый `_lower_type` (лоуринг в Python уезжает в `PythonTypeMapper`, фаза 4).

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/spec/test_neutral_parse.py
import pytest

from refract.ir.types import ListType, MapType, RefType, ScalarType
from refract.spec.loader import SpecError, parse_neutral_type


@pytest.mark.parametrize("text,expected", [
    ("string", ScalarType(scalar="string")),
    ("integer", ScalarType(scalar="integer")),
    (" boolean ", ScalarType(scalar="boolean")),
    ("ref<LocalizedName>", RefType(target="LocalizedName")),
    ("list<string>", ListType(item=ScalarType(scalar="string"))),
    ("map<string,integer>", MapType(key=ScalarType(scalar="string"),
                                    value=ScalarType(scalar="integer"))),
    ("list<ref<Priority>>", ListType(item=RefType(target="Priority"))),
    ("map<string,list<integer>>", MapType(key=ScalarType(scalar="string"),
                                          value=ListType(item=ScalarType(scalar="integer")))),
])
def test_parses(text, expected):
    assert parse_neutral_type(text) == expected


@pytest.mark.parametrize("bad", ["", "int", "ref<>", "list<>", "map<string>", "bogus<x>"])
def test_rejects_malformed(bad):
    with pytest.raises(SpecError):
        parse_neutral_type(bad)
```

- [ ] **Step 2: Прогнать - падает** (модуль отсутствует)

- [ ] **Step 3: Реализовать парсер**

```python
# src/refract/spec/loader.py  (парсер + SpecError; SpecLoader.load дописывается в Task 2.3)
from __future__ import annotations

from refract.ir.types import ListType, MapType, NeutralType, RefType, ScalarType

__all__ = ["SpecError", "parse_neutral_type"]

_SCALARS = frozenset({"string", "integer", "number", "boolean", "any"})


class SpecError(Exception):
    """A malformed spec - carries the file path and the underlying validation message."""


def _split_top_comma(inner: str) -> tuple[str, str]:
    """Split ``K,V`` on the FIRST top-level comma (bracket-depth aware)."""
    depth = 0
    for i, ch in enumerate(inner):
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif ch == "," and depth == 0:
            return inner[:i], inner[i + 1 :]
    raise SpecError(f"expected 'K,V' in map<...>, got {inner!r}")


def parse_neutral_type(text: str) -> NeutralType:
    """Parse one neutral spec type string into a NeutralType (see разд. A grammar)."""
    text = text.strip()
    if text in _SCALARS:
        return ScalarType(scalar=text)  # type: ignore[arg-type]
    for prefix, build in (
        ("ref<", lambda body: RefType(target=body.strip())),
        ("list<", lambda body: ListType(item=parse_neutral_type(body))),
    ):
        if text.startswith(prefix) and text.endswith(">"):
            body = text[len(prefix) : -1]
            if not body.strip():
                raise SpecError(f"empty type argument in {text!r}")
            return build(body)
    if text.startswith("map<") and text.endswith(">"):
        key, value = _split_top_comma(text[4:-1])
        return MapType(key=parse_neutral_type(key), value=parse_neutral_type(value))
    raise SpecError(f"unknown neutral type: {text!r}")
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(spec): neutral-type string parser (replaces _lower_type)`)

### Task 2.2: `spec/nodes.py` - pydantic-схема входа (resource.yaml + client.yaml)

**Files:**
- Create: `src/refract/spec/nodes.py`
- Test: `tests/spec/test_nodes.py`

**Interfaces:**
- Produces: `ResourceSpec` (resource.yaml) + `ClientConfigNode` (client.yaml), с вложенными `*Spec`/`*Node`, все с `model_config = ConfigDict(extra="forbid")`. Порт из старого `loader.py` (строки 48-180) БЕЗ лоуринга: `FieldSpec.type`/`ParamSpec.type` остаются `str` (сырая spec-строка; loader парсит их в `NeutralType`).
- Дельты против старого порта (следствия разд. B/разд. I/разд. J):
  - `ResourceSpec` ТЕРЯЕТ `base_url` -> он переезжает в `client.yaml` (разд. J); с `extra="forbid"` старый `base_url:` теперь отклоняется.
  - `ModelSpec` зеркалит разд. B: `kind: Literal["object","root_list"]` (envelope отложен - нет IR-варианта), мёртвое поле `config` удалено.
  - НОВЫЕ ноды `client.yaml` (разд. J): `ClientConfigNode`, `ServerNode`, auth-схемы `HeaderAuthNode`/`MultiHeaderAuthNode` (дискриминированы на `kind`), `AuthInputNode`.
  - `headers`/`inputs`/`default_headers` в YAML - МАППИНГИ (dict); нода принимает dict, loader (Task 2.3) конвертирует в tuple-of-pairs.
  - `BodySpec` порт дословно (`strategy`/`model`/`dump`): `dump`/`strategy` всё ещё принимаются на входе (авторская YAML), но в IR больше не лоурятся (Task 2.3 `_body`).
- Потребляется `SpecLoader`.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/spec/test_nodes.py
import pytest
from pydantic import ValidationError

from refract.spec.nodes import ClientConfigNode, ResourceSpec


def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        ResourceSpec.model_validate(
            {"domain": "t", "resource": "m", "security": "s", "operations": [], "bogus": 1}
        )


def test_base_url_now_rejected():  # base_url переехал в client.yaml (разд. J)
    with pytest.raises(ValidationError):
        ResourceSpec.model_validate(
            {"domain": "t", "resource": "m", "security": "s", "base_url": "u", "operations": []}
        )


def test_operation_id_aliased_from_camel():
    spec = ResourceSpec.model_validate({
        "domain": "t", "resource": "m", "security": "s",
        "operations": [{"name": "get", "method": "GET", "path": "myself",
                        "operationId": "me_get", "responses": {200: {"model": "Me"}},
                        "mcp": {"name": "me_get", "safety": "RO", "title": "x",
                                "documentation": "y"}}],
    })
    assert spec.operations[0].operation_id == "me_get"


def test_field_type_stays_raw_string():
    spec = ResourceSpec.model_validate({
        "domain": "t", "resource": "m", "security": "s",
        "models": [{"name": "Me", "fields": [{"name": "uid", "type": "integer"}]}],
        "operations": [],
    })
    assert spec.models[0].fields[0].type == "integer"  # NOT lowered here


def test_client_config_node_parses_multi_header_auth():
    node = ClientConfigNode.model_validate({
        "name": "tracker",
        "server": {"base_url": "https://api.tracker.yandex.net/v3"},
        "default_headers": {},
        "auth": {
            "oauth_token": {
                "kind": "multi_header",
                "headers": {"Authorization": "OAuth {oauth_token}", "X-Org-Id": "{organization_id}"},
                "inputs": {"oauth_token": {"env": "YANDEX_ID_OAUTH_TOKEN"},
                           "organization_id": {"env": "YANDEX_ID_ORGANIZATION_ID"}},
            }
        },
    })
    assert node.server.base_url.endswith("/v3")
    scheme = node.auth["oauth_token"]
    assert scheme.kind == "multi_header"                        # discriminated on `kind`
    assert scheme.headers["Authorization"] == "OAuth {oauth_token}"   # still a MAPPING at the node layer
    assert scheme.inputs["oauth_token"].env == "YANDEX_ID_OAUTH_TOKEN"


def test_client_config_rejects_unknown_auth_kind():
    with pytest.raises(ValidationError):
        ClientConfigNode.model_validate(
            {"name": "x", "server": {"base_url": "u"}, "auth": {"s": {"kind": "bogus"}}}
        )
```

- [ ] **Step 2: Прогнать - падает**

- [ ] **Step 3: Реализовать `src/refract/spec/nodes.py`**

Перенести из удалённого `loader.py` классы `_Spec, FieldSpec, ModelSpec, ResponseSpec, RequireFoundSpec, McpSpec, CliSpec, ParamSpec, BodySpec, TestSpec, OperationSpec, ModuleDocsSpec, ResourceSpec` **дословно** (`extra="forbid"`, `operationId`-alias, `Literal`-энумы уже корректны) с дельтами выше, и ДОБАВИТЬ ноды `client.yaml`. `list[...]` в spec-нодах (вход) - это не IR; коллекции станут `tuple` при лоуринге.

```python
# src/refract/spec/nodes.py
"""Input schema: pydantic nodes mirroring authored resource.yaml + client.yaml one-to-one.

Every node sets ``extra="forbid"`` so a typo or a missing required key is rejected with a
located error before any emitter runs. Types stay raw here (``FieldSpec.type: str``); the loader
parses them into the neutral ``NeutralType`` and lowers the nodes into frozen ``refract.ir``.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ClientConfigNode", "ResourceSpec"]


class _Spec(BaseModel):
    """Base for every spec node: reject unknown keys so a malformed spec fails loudly."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------- resource.yaml nodes


class FieldSpec(_Spec):
    """One neutral field of a model - mirrors a v2 ``fields:`` entry."""

    name: str
    type: str
    optional: bool = False
    default: str | None = None  # explicit spec default; None => let the TypeMapper decide
    alias: str | None = None
    description: str | None = None
    enum: list[str] | None = None
    format: str | None = None
    deprecated: bool = False


class ModelSpec(_Spec):
    name: str
    documentation: str | None = None
    kind: Literal["object", "root_list"] = "object"  # envelope deferred (разд. B: no IR variant yet)
    item: str | None = None                          # required for root_list; loader enforces
    fields: list[FieldSpec] = Field(default_factory=list)


class ResponseSpec(_Spec):
    model: str


class RequireFoundSpec(_Spec):
    sentinel: str
    message: str


class McpSpec(_Spec):
    name: str
    safety: Literal["RO", "WRITE", "WRITE_IDEMPOTENT", "DESTRUCTIVE"]
    title: str
    documentation: str
    require_found: RequireFoundSpec | None = None


class CliSpec(_Spec):
    name: str
    documentation: str


class ParamSpec(_Spec):
    """One neutral request parameter - mirrors a v2 ``params:`` entry (``loc`` is path|query)."""

    name: str
    loc: Literal["path", "query"]
    type: str = "string"
    optional: bool = False
    default: str | None = None
    alias: str | None = None
    help: str | None = None


class BodySpec(_Spec):
    """The write-body registry entry - only the ``TypedModel`` mode today.

    ``model`` names a hand-written body model declared in ``models:``. ``strategy``/``dump`` are
    still accepted on input (authored YAML), but the IR now carries ``by_alias``/``omit_none``
    booleans (default True/True) instead of a rendered dump string - the loader ignores ``dump``.
    """

    strategy: Literal["TypedModel"]
    model: str
    dump: str


class TestSpec(_Spec):
    """One authored test fixture - all nine ``ir.TestCase`` fields, each with a safe default."""

    name: str
    kind: Literal["client", "cli", "mcp", "mcp_guard"]
    http_method: Literal["GET", "POST", "PATCH", "DELETE"]
    path: str
    status: int = 200
    response_json: Any = None
    has_json: bool = True
    asserts: list[str] = Field(default_factory=list)
    call: str = ""


class OperationSpec(_Spec):
    name: str
    method: Literal["GET", "POST", "PATCH", "DELETE"]
    path: str
    operation_id: str = Field(alias="operationId")
    documentation: str | None = None
    params: list[ParamSpec] = Field(default_factory=list)
    body: BodySpec | None = None
    responses: dict[int, ResponseSpec]
    mcp: McpSpec
    cli: CliSpec | None = None
    tests: list[TestSpec] = Field(default_factory=list)
    handler: str | None = None


class ModuleDocsSpec(_Spec):
    client: str | None = None
    models: str | None = None
    cli: str | None = None
    mcp: str | None = None
    cli_group_help: str | None = None
    mcp_server: str | None = None
    client_class: str | None = None


class ResourceSpec(_Spec):
    domain: str
    resource: str
    security: str  # names an AuthScheme in client.yaml; base_url moved out to client.yaml (разд. J)
    module_docs: ModuleDocsSpec = Field(default_factory=ModuleDocsSpec)
    documentation: str | None = None
    models: list[ModelSpec] = Field(default_factory=list)
    operations: list[OperationSpec]


# ------------------------------------------------------------------------- client.yaml nodes


class AuthInputNode(_Spec):
    """One named credential input; the input NAME is the mapping key (loader threads it in)."""

    env: str | None = None  # env var name; None -> must be passed explicitly


class HeaderAuthNode(_Spec):
    """Single templated header, e.g. ``Authorization: Bearer {oauth_token}`` (bearer-majority APIs)."""

    kind: Literal["header"] = "header"
    header: str
    template: str
    inputs: dict[str, AuthInputNode]  # MAPPING; loader -> tuple[ir.AuthInput, ...]


class MultiHeaderAuthNode(_Spec):
    """>=1 templated headers (Yandex ``OAuth {oauth_token}`` + ``X-Org-Id``)."""

    kind: Literal["multi_header"] = "multi_header"
    headers: dict[str, str]           # MAPPING; loader -> tuple[(name, template), ...]
    inputs: dict[str, AuthInputNode]  # MAPPING; loader -> tuple[ir.AuthInput, ...]


AuthSchemeNode = Annotated[
    Union[HeaderAuthNode, MultiHeaderAuthNode], Field(discriminator="kind")
]


class ServerNode(_Spec):
    base_url: str


class ClientConfigNode(_Spec):
    """Mirrors client.yaml (разд. J): server + default headers + named auth schemes."""

    name: str
    server: ServerNode
    default_headers: dict[str, str] = Field(default_factory=dict)  # MAPPING -> tuple-of-pairs
    auth: dict[str, AuthSchemeNode] = Field(default_factory=dict)  # scheme-name -> scheme
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(spec): input schema nodes (resource.yaml + client.yaml) decomposed from loader god-file`)

### Task 2.3: `SpecLoader.load` + `load_client_config` -> нейтральный IR

**Files:**
- Modify: `src/refract/spec/loader.py` (дописать лоуринг spec->IR + `SpecLoader`)
- Migrate corpus: create `examples/ycli-tracker/client.yaml` (разд. J), strip `base_url:` из `examples/ycli-tracker/tracker/me/resource.yaml` и `.../priorities/resource.yaml`, rm устаревший `examples/ycli-tracker/_auth.yaml`
- Test: `tests/spec/test_loader.py`

**Interfaces:**
- Consumes: `ResourceSpec`/`ClientConfigNode` (разд. nodes), `parse_neutral_type` (2.1), `ir` (разд. B/разд. H/разд. I).
- Produces:
  - `SpecLoader.load(path: Path) -> ir.Resource` - нейтральный IR (минус `base_url`); `Field.type`/`Param.type` - `NeutralType`.
  - `SpecLoader.load_client_config(path: Path) -> ir.ClientConfig` - парсит `client.yaml` через `ClientConfigNode`, конвертит `headers`/`inputs`/`default_headers`-маппинги в tuple-of-pairs / `tuple[ir.AuthInput, ...]`.
- Лоуринг-дельты против старого `loader.py`:
  - (a) `_model` возвращает `ir.ObjectModel | ir.RootListModel` - строит нужный вариант по `spec.kind`; поле `config` больше не прокидывается (разд. B: мёртвое).
  - (b) `_body` -> `ir.Body(model=...)` с дефолтами `by_alias=True`/`omit_none=True` (разд. B); старая source-text-строка `dump` в IR НЕ едет.
  - (c) `_resource` ТЕРЯЕТ `base_url` (сохраняет `security`).
  - (d) `_field`/`_param` зовут `parse_neutral_type(spec.type)` (не `_lower_type`), `default` = только явный `spec.default` (implied-null-default уезжает в `TypeMapper`, фаза 4).
  - (e) `safety`->`ir.Safety`, test `kind`->`ir.TestKind`, `loc`->Literal - прокидываем сырые строки, pydantic коэрсит на границе IR.
- Потребляется `Generator` (ресурсы) + композиционным корнем root-client (config).

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/spec/test_loader.py
from pathlib import Path

from refract import ir
from refract.ir.model import ObjectModel, RootListModel
from refract.ir.types import RefType, ScalarType
from refract.spec.loader import SpecLoader

_EX = Path(__file__).resolve().parent.parent.parent / "examples" / "ycli-tracker"


def test_loads_me_as_neutral_ir():
    res = SpecLoader.load(_EX / "tracker" / "me" / "resource.yaml")
    assert res.domain == "tracker" and res.resource == "me"
    assert not hasattr(res, "base_url")  # base_url moved to client.yaml (разд. J)
    uid = res.model("Me").fields[0]
    assert uid.name == "uid"
    assert uid.type == ScalarType(scalar="integer")  # neutral, NOT "int | None"
    assert uid.optional is True
    assert uid.default is None  # implied null-default is the TypeMapper's job now


def test_me_model_is_object_variant():
    res = SpecLoader.load(_EX / "tracker" / "me" / "resource.yaml")
    assert isinstance(res.model("Me"), ObjectModel)


def test_priorities_model_variants_and_ref_field():
    res = SpecLoader.load(_EX / "tracker" / "priorities" / "resource.yaml")
    assert isinstance(res.model("PriorityList"), RootListModel)
    assert res.model("PriorityList").item == "Priority"
    assert isinstance(res.model("Priority"), ObjectModel)
    name = res.model("PriorityCreate").fields[1]
    assert name.type == RefType(target="LocalizedName")


def test_create_body_flags_default_true():
    res = SpecLoader.load(_EX / "tracker" / "priorities" / "resource.yaml")
    create = next(op for op in res.operations if op.name == "create")
    assert create.body is not None
    assert create.body.model == "PriorityCreate"
    assert create.body.by_alias is True and create.body.omit_none is True  # no `dump` text


def test_query_param_is_neutral():
    res = SpecLoader.load(_EX / "tracker" / "priorities" / "resource.yaml")
    edit = next(op for op in res.operations if op.name == "edit")
    version = next(p for p in edit.params if p.name == "version")
    assert version.type == ScalarType(scalar="integer") and version.optional is True


def test_loads_tracker_client_config():
    config = SpecLoader.load_client_config(_EX / "client.yaml")
    assert config.name == "tracker"
    assert config.server.base_url == "https://api.tracker.yandex.net/v3"
    assert len(config.auth) == 1
    name, scheme = config.auth[0]
    assert name == "oauth_token"
    assert isinstance(scheme, ir.MultiHeaderAuth)
    assert scheme.headers == (
        ("Authorization", "OAuth {oauth_token}"),
        ("X-Org-Id", "{organization_id}"),
    )
    assert tuple((i.name, i.env) for i in scheme.inputs) == (
        ("oauth_token", "YANDEX_ID_OAUTH_TOKEN"),
        ("organization_id", "YANDEX_ID_ORGANIZATION_ID"),
    )
```

- [ ] **Step 2: Прогнать - падает**

- [ ] **Step 3a: Мигрировать example-корпус**

Создать `examples/ycli-tracker/client.yaml` (разд. J дословно):

```yaml
name: tracker
server:
  base_url: https://api.tracker.yandex.net/v3
default_headers: {}
auth:
  oauth_token:
    kind: multi_header
    headers:
      Authorization: "OAuth {oauth_token}"
      X-Org-Id: "{organization_id}"
    inputs:
      oauth_token: {env: YANDEX_ID_OAUTH_TOKEN}
      organization_id: {env: YANDEX_ID_ORGANIZATION_ID}
```

Убрать строку `base_url: https://api.tracker.yandex.net/v3` из обоих `tracker/me/resource.yaml` и `tracker/priorities/resource.yaml` (иначе `ResourceSpec` с `extra="forbid"` отклонит её; `security: oauth_token` остаётся). `rm examples/ycli-tracker/_auth.yaml` - старый формат заменён на `client.yaml`. (Prose-правки `module_docs.client` («uplink») - НЕ здесь; они в задаче snapshot-таргетов, разд. F.)

- [ ] **Step 3b: Реализовать** - дописать в `src/refract/spec/loader.py`:

```python
# appended to src/refract/spec/loader.py
from pathlib import Path

import yaml
from pydantic import ValidationError

from refract import ir
from refract.spec import nodes


def _field(spec: nodes.FieldSpec) -> ir.Field:
    return ir.Field(
        name=spec.name, type=parse_neutral_type(spec.type), optional=spec.optional,
        default=spec.default, alias=spec.alias, description=spec.description,
    )


def _param(spec: nodes.ParamSpec) -> ir.Param:
    return ir.Param(
        name=spec.name, loc=spec.loc, type=parse_neutral_type(spec.type),
        optional=spec.optional, default=spec.default, alias=spec.alias, help=spec.help,
    )


def _model(spec: nodes.ModelSpec) -> ir.Model:
    """Build the Model variant `kind` selects (config dropped: dead - 0 spec/emitter uses)."""
    if spec.kind == "root_list":
        return ir.RootListModel(name=spec.name, item=spec.item, documentation=spec.documentation)
    return ir.ObjectModel(
        name=spec.name,
        fields=tuple(_field(field) for field in spec.fields),
        documentation=spec.documentation,
    )


def _body(spec: nodes.BodySpec | None) -> ir.Body | None:
    """by_alias/omit_none take their True/True defaults; the old `dump` text is no longer lowered."""
    return None if spec is None else ir.Body(model=spec.model)


def _require_found(spec: nodes.RequireFoundSpec | None) -> ir.RequireFound | None:
    return None if spec is None else ir.RequireFound(sentinel=spec.sentinel, message=spec.message)


def _mcp(spec: nodes.McpSpec) -> ir.McpMeta:
    return ir.McpMeta(
        name=spec.name,
        safety=spec.safety,  # str -> ir.Safety StrEnum (pydantic coerces at the IR boundary)
        title=spec.title,
        documentation=spec.documentation,
        require_found=_require_found(spec.require_found),
    )


def _cli(spec: nodes.CliSpec | None) -> ir.CliMeta | None:
    return None if spec is None else ir.CliMeta(name=spec.name, documentation=spec.documentation)


def _test(spec: nodes.TestSpec) -> ir.TestCase:
    return ir.TestCase(
        name=spec.name,
        kind=spec.kind,  # str -> ir.TestKind StrEnum (pydantic coerces)
        http_method=spec.http_method,
        path=spec.path,
        status=spec.status,
        response_json=spec.response_json,
        has_json=spec.has_json,
        asserts=tuple(spec.asserts),
        call=spec.call,
    )


def _response_model(responses: dict[int, nodes.ResponseSpec]) -> str:
    """The success response's model name (``responses[200].model``)."""
    return responses[200].model


def _operation(spec: nodes.OperationSpec) -> ir.Operation:
    return ir.Operation(
        name=spec.name,
        method=spec.method,
        path=spec.path,
        operation_id=spec.operation_id,
        params=tuple(_param(param) for param in spec.params),
        body=_body(spec.body),
        response_model=_response_model(spec.responses),
        documentation=spec.documentation,
        mcp=_mcp(spec.mcp),
        cli=_cli(spec.cli),
        tests=tuple(_test(test) for test in spec.tests),
        handler=spec.handler,
    )


def _module_docs(spec: nodes.ModuleDocsSpec) -> ir.ModuleDocs:
    return ir.ModuleDocs(
        client=spec.client,
        models=spec.models,
        cli=spec.cli,
        mcp=spec.mcp,
        cli_group_help=spec.cli_group_help,
        mcp_server=spec.mcp_server,
        client_class=spec.client_class,
    )


def _resource(spec: nodes.ResourceSpec) -> ir.Resource:
    return ir.Resource(
        domain=spec.domain,
        resource=spec.resource,
        security=spec.security,  # base_url dropped - now ir.ClientConfig.server.base_url (разд. I)
        models=tuple(_model(model) for model in spec.models),
        operations=tuple(_operation(operation) for operation in spec.operations),
        documentation=spec.documentation,
        module_docs=_module_docs(spec.module_docs),
    )


# ----------------------------------------------------------- client.yaml -> ir.ClientConfig (разд. I/разд. J)


def _auth_input(name: str, node: nodes.AuthInputNode) -> ir.AuthInput:
    return ir.AuthInput(name=name, env=node.env)


def _auth_scheme(node: nodes.AuthSchemeNode) -> ir.AuthScheme:
    inputs = tuple(_auth_input(name, inp) for name, inp in node.inputs.items())
    if isinstance(node, nodes.MultiHeaderAuthNode):
        return ir.MultiHeaderAuth(headers=tuple(node.headers.items()), inputs=inputs)
    return ir.HeaderAuth(header=node.header, template=node.template, inputs=inputs)


def _client_config(spec: nodes.ClientConfigNode) -> ir.ClientConfig:
    return ir.ClientConfig(
        name=spec.name,
        server=ir.Server(base_url=spec.server.base_url),
        default_headers=tuple(spec.default_headers.items()),
        auth=tuple((name, _auth_scheme(scheme)) for name, scheme in spec.auth.items()),
    )


def _read_mapping(path: Path) -> dict:
    """Read + YAML-parse `path`, asserting a mapping top level (shared by both load entry points)."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise SpecError(f"{path}: invalid YAML - {error}") from error
    if not isinstance(raw, dict):
        raise SpecError(f"{path}: top level must be a mapping, got {type(raw).__name__}")
    return raw


class SpecLoader:
    """Parse + validate resource.yaml / client.yaml into frozen, neutral ``refract.ir``."""

    @staticmethod
    def load(path: Path) -> ir.Resource:
        raw = _read_mapping(path)
        try:
            spec = nodes.ResourceSpec.model_validate(raw)
        except ValidationError as error:
            raise SpecError(f"{path}: spec failed validation -\n{error}") from error
        return _resource(spec)

    @staticmethod
    def load_client_config(path: Path) -> ir.ClientConfig:
        raw = _read_mapping(path)
        try:
            spec = nodes.ClientConfigNode.model_validate(raw)
        except ValidationError as error:
            raise SpecError(f"{path}: client config failed validation -\n{error}") from error
        return _client_config(spec)
```

(Лоуринг-хелперы `_require_found`/`_mcp`/`_cli`/`_test`/`_response_model`/`_operation`/`_module_docs`/`_resource` - дословный порт из удалённого `loader.py` строки 255-331, с единственной заменой на `nodes.*`-типы и дельтами (a)-(e) выше. `_lower_type` НЕ восстанавливать.)

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(spec): SpecLoader loads neutral IR + client config (base_url -> client.yaml)`)

### Task 2.4: `spec/__init__.py` реэкспорт + conftest

**Files:**
- Modify: `src/refract/spec/__init__.py`, `tests/conftest.py`
- Test: покрывается фикстурами (resource + client_config).

- [ ] **Step 1: `src/refract/spec/__init__.py`** - реэкспорт `SpecError` + `SpecLoader` (несёт обе точки входа `load`/`load_client_config`) + `parse_neutral_type`:

```python
"""Spec-validation layer: parse+validate resource.yaml / client.yaml -> frozen neutral refract.ir."""

from refract.spec.loader import SpecError, SpecLoader, parse_neutral_type

__all__ = ["SpecError", "SpecLoader", "parse_neutral_type"]
```

- [ ] **Step 2: Переписать `tests/conftest.py`** - заменить `from refract.loader import load` на `from refract.spec import SpecLoader`, `load(...)` на `SpecLoader.load(...)`, и ДОБАВИТЬ фикстуру `client_config` (грузит tracker `client.yaml`) рядом с ресурс-фикстурами:

```python
# tests/conftest.py
from pathlib import Path

import pytest

from refract import ir
from refract.spec import SpecLoader

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker"


@pytest.fixture
def me_spec_path() -> Path:
    return _EXAMPLES / "tracker" / "me" / "resource.yaml"


@pytest.fixture
def me_resource(me_spec_path: Path) -> ir.Resource:
    return SpecLoader.load(me_spec_path)


@pytest.fixture
def priorities_spec_path() -> Path:
    return _EXAMPLES / "tracker" / "priorities" / "resource.yaml"


@pytest.fixture
def priorities_resource(priorities_spec_path: Path) -> ir.Resource:
    return SpecLoader.load(priorities_spec_path)


@pytest.fixture
def client_config_path() -> Path:
    return _EXAMPLES / "client.yaml"


@pytest.fixture
def client_config(client_config_path: Path) -> ir.ClientConfig:
    return SpecLoader.load_client_config(client_config_path)
```

- [ ] **Step 3: Прогнать весь spec-слой - зелено**

Run: `pytest tests/spec tests/ir -q` -> PASS

- [ ] **Step 4: Commit** (`feat(spec): re-export SpecLoader; add client_config fixture`)

---

## PHASE 3 / Контракт плагина + реестр бэкендов

> `shapes.py`/`OpShape`/`classify` удалены (решение #14 / разд. D): различие read vs write - один локальный `op.body is not None`, резолверы 7.1/7.2 ветвятся на месте. Отдельной задачи-classify больше нет.

### Task 3.1: `emitters/api.py` - value-объекты + стратегии-ABC + surface/domain-эмиттеры

**Files:**
- Create: `src/refract/emitters/api.py`
- Test: `tests/emitters/test_api.py`

**Interfaces:**
- Consumes: `ir` (разд. B, включая `ClientConfig`/`Server` из разд. I), `NeutralType` (разд. A).
- Produces: `Import`, `RenderedType`, `Fragment`, `EmitContext`, `Naming`, `TypeMapper`, `Formatter`, `Docstrings`, `Layout`, `SurfaceEmitter`, `DomainEmitter`, `LanguageBackend` (см. разд. C). Потребляется всеми стратегиями/surface'ами/бэкендом; `EmitContext` несёт `package_root` + `ir.ClientConfig` (per-API glue), `DomainEmitter` - per-API surface (root_client), `LanguageBackend.domain_surfaces` - его слот.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/emitters/test_api.py
import dataclasses

import pytest

from refract import ir
from refract.emitters.api import (
    DomainEmitter, EmitContext, Fragment, Import, LanguageBackend, Naming,
    RenderedType, SurfaceEmitter,
)


def _config() -> ir.ClientConfig:
    return ir.ClientConfig(
        name="tracker", server=ir.Server(base_url="https://api.tracker.yandex.net/v3")
    )


def _resource() -> ir.Resource:
    return ir.Resource(
        domain="tracker", resource="myself", security="oauth_token", models=(), operations=()
    )


def test_value_objects_are_frozen():
    frag = Fragment(lines=("a", "b"), imports=(Import("m", "N"),))
    assert frag.lines == ("a", "b")
    with pytest.raises(dataclasses.FrozenInstanceError):
        frag.lines = ()  # frozen dataclass


def test_rendered_type_defaults_empty_imports():
    assert RenderedType(text="int").imports == ()


def test_emit_context_carries_package_root_and_config():
    ctx = EmitContext(package_root="ycli.yandex.tracker", config=_config())
    assert ctx.package_root == "ycli.yandex.tracker"
    assert ctx.config.server.base_url == "https://api.tracker.yandex.net/v3"


def test_strategy_abcs_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Naming()  # abstract


def test_surface_emitter_is_per_resource():
    # a concrete per-resource stub proves name + applies() + emit(res, ctx)
    class _Requests(SurfaceEmitter):
        name = "requests"
        def applies(self, res): return bool(res.operations)
        def emit(self, res, ctx): return f"# {res.resource} @ {ctx.package_root}"
    surface = _Requests()
    res = _resource()
    ctx = EmitContext(package_root="ycli.yandex.tracker", config=_config())
    assert surface.applies(res) is False                    # no operations -> gated off
    assert surface.emit(res, ctx) == "# myself @ ycli.yandex.tracker"


def test_domain_emitter_runs_once_over_all_resources():
    # a concrete per-API stub proves name + emit(resources, ctx)
    class _RootClient(DomainEmitter):
        name = "root_client"
        def emit(self, resources, ctx): return f"# {ctx.config.name}: {len(resources)}"
    root = _RootClient()
    ctx = EmitContext(package_root="ycli.yandex.tracker", config=_config())
    assert root.emit((_resource(),), ctx) == "# tracker: 1"


def test_domain_emitter_cannot_be_instantiated():
    with pytest.raises(TypeError):
        DomainEmitter()  # abstract emit(resources, ctx)


def test_language_backend_composes_strategies():
    # a minimal concrete stub proves the composition shape holds
    class _N(Naming):
        def pascal(self, name): return name.title()
        def module_function(self, name): return name
        def class_name(self, base, suffix): return base + suffix
    n = _N()
    assert n.class_name("Me", "Client") == "MeClient"


def test_language_backend_domain_surfaces_default_empty():
    field = {f.name: f for f in dataclasses.fields(LanguageBackend)}["domain_surfaces"]
    assert field.default == ()
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать `src/refract/emitters/api.py` дословно по разд. C** (весь контракт на одной странице - value-объекты + `EmitContext(package_root, config)` + 5 стратегий-ABC + `SurfaceEmitter`/`DomainEmitter` + `LanguageBackend`):

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from refract import ir
from refract.ir.types import NeutralType

# ---- value objects ----

@dataclass(frozen=True)
class Import:
    """One `from <module> import <name>` atom; the assembler groups + isort-sorts them."""
    module: str
    name: str

@dataclass(frozen=True)
class RenderedType:
    """A language type rendered from a NeutralType, plus the imports it pulls in."""
    text: str
    imports: tuple[Import, ...] = ()

@dataclass(frozen=True)
class Fragment:
    """The typed boundary between UnitRenderer (per-operation) and ResourceAssembler."""
    lines: tuple[str, ...]
    imports: tuple[Import, ...] = ()

@dataclass(frozen=True)
class EmitContext:
    """Per-generation config beyond the resource itself."""
    package_root: str        # where runtime/base/models live, e.g. "ycli.yandex.tracker"
    config: ir.ClientConfig | None = None  # per-API glue; ONLY tests (base_url) + root_client read it;
    # per-resource surfaces (requests/client/models/cli/mcp/package) ignore it, hence the None default.

# ---- 5 injected strategies (ABCs) ----

class Naming(ABC):
    @abstractmethod
    def pascal(self, name: str) -> str: ...
    @abstractmethod
    def module_function(self, name: str) -> str: ...      # module-level def-safe: list -> list_
    @abstractmethod
    def class_name(self, base: str, suffix: str) -> str: ...  # merges the 3 *_class helpers

class TypeMapper(ABC):
    @abstractmethod
    def render(self, neutral_type: NeutralType, *, optional: bool) -> RenderedType: ...
    @abstractmethod
    def null_default(self, neutral_type: NeutralType, *, optional: bool) -> str | None: ...

class Formatter(ABC):
    @abstractmethod
    def format(self, source: str) -> str: ...

class Docstrings(ABC):
    @abstractmethod
    def render(self, text: str | None, indent: str) -> tuple[str, ...]: ...

class Layout(ABC):
    @abstractmethod
    def path(self, res: ir.Resource, surface: str) -> str: ...

# ---- renderer / assembler / surface / backend ----

class SurfaceEmitter(ABC):
    """One PER-RESOURCE surface plugin: gates on data presence, emits UNformatted source.

    `name` stays a plain str (NOT an enum): dispatch is registry + `applies()`, never name-compare;
    surface is the extension axis. A unit test enforces the name<->`Layout.path` coupling (decision #22).
    """
    name: str  # "requests" | "client" | "models" | "cli" | "mcp" | "tests" | "package"
    @abstractmethod
    def applies(self, res: ir.Resource) -> bool: ...
    @abstractmethod
    def emit(self, res: ir.Resource, ctx: EmitContext) -> str: ...

class DomainEmitter(ABC):
    """One PER-DOMAIN (per-API) surface = the generated glue. Runs ONCE over ALL resources.

    root_client aggregates resources + builds Session/`httpx.Client(auth=...)` from `ctx.config`.
    """
    name: str  # "root_client"
    @abstractmethod
    def emit(self, resources: tuple[ir.Resource, ...], ctx: EmitContext) -> str: ...

@dataclass(frozen=True)
class LanguageBackend:
    """Pure composition of the 5 strategies + surface emitters. Built by a @backend factory."""
    name: str
    naming: Naming
    type_mapper: TypeMapper
    formatter: Formatter
    docstrings: Docstrings
    layout: Layout
    surfaces: tuple[SurfaceEmitter, ...]              # per-resource
    domain_surfaces: tuple[DomainEmitter, ...] = ()   # per-API glue (root_client)
```

-> **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(emitters): plugin contract - value objects + strategy ABCs + surface/domain emitters + backend`)

### Task 3.2: `emitters/registry.py` - `@backend` + `get_backend`

**Files:**
- Create: `src/refract/emitters/registry.py`
- Test: `tests/emitters/test_registry.py`

**Interfaces:**
- Produces: `backend(name)` (декоратор фабрики), `get_backend(name) -> LanguageBackend` (ленивый импорт `refract.emitters.<name>.backend`). Потребляется `Generator`; регистрируется `python/backend.py`.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/emitters/test_registry.py
import pytest

from refract.emitters import registry


def test_register_and_get(monkeypatch):
    monkeypatch.setattr(registry, "_BACKENDS", {})
    marker = object()

    @registry.backend("toy")
    def _factory():
        return marker

    assert registry.get_backend("toy") is marker


def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setattr(registry, "_BACKENDS", {})
    with pytest.raises(registry.UnknownBackendError):
        registry.get_backend("nope")  # lazy import of refract.emitters.nope.backend fails
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать**

```python
# src/refract/emitters/registry.py
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from refract.emitters.api import LanguageBackend

__all__ = ["UnknownBackendError", "backend", "get_backend"]

_BACKENDS: dict[str, Callable[[], LanguageBackend]] = {}


class UnknownBackendError(Exception):
    """No backend registered (and none importable) under this language name."""


def backend(name: str) -> Callable[[Callable[[], LanguageBackend]], Callable[[], LanguageBackend]]:
    """Register a LanguageBackend factory under ``name`` (used as ``@backend("python")``)."""
    def register(factory: Callable[[], LanguageBackend]) -> Callable[[], LanguageBackend]:
        _BACKENDS[name] = factory
        return factory
    return register


def get_backend(name: str) -> LanguageBackend:
    """Resolve a backend, lazily importing ``refract.emitters.<name>.backend`` on first use."""
    if name not in _BACKENDS:
        try:
            importlib.import_module(f"refract.emitters.{name}.backend")
        except ModuleNotFoundError as error:
            raise UnknownBackendError(f"no backend for language {name!r}") from error
    if name not in _BACKENDS:
        raise UnknownBackendError(f"module refract.emitters.{name}.backend did not register {name!r}")
    return _BACKENDS[name]()
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(emitters): lazy @backend registry`)

---

## PHASE 4 / Python-стратегии

Каждая стратегия - самостоятельный файл, реализует свой ABC из разд. C, тестируется в изоляции. Вместе заменяют `_common.py` (+ глобал `_SHADOWED_NAMES` -> константа модуля стратегии; три `*_class` -> один `class_name`), `loader._lower_type`, `render_doc`, `refract/format.py`.

### Task 4.1: `PythonNaming`

**Files:**
- Create: `src/refract/emitters/python/naming.py`, `src/refract/emitters/python/__init__.py` (если пуст - оставить)
- Test: `tests/emitters/python/test_naming.py`

**Interfaces:**
- Consumes: `Naming` (разд. C).
- Produces: `PythonNaming` - `pascal`, `module_function` (shadow-guard: `list` -> `list_`), `class_name(base, suffix)` (схлопывает `resource_client_class`/`domain_resource_base`/`domain_client_class`).

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/emitters/python/test_naming.py
from refract.emitters.python.naming import PythonNaming

n = PythonNaming()


def test_pascal():
    assert n.pascal("me") == "Me"
    assert n.pascal("localized_name") == "LocalizedName"


def test_module_function_guards_shadowed_names():
    assert n.module_function("list") == "list_"     # shadows builtin at module scope
    assert n.module_function("import") == "import_"  # keyword
    assert n.module_function("get") == "get"         # unchanged


def test_class_name_merges_the_three_helpers():
    assert n.class_name("me", "Client") == "MeClient"          # was resource_client_class
    assert n.class_name("tracker", "Resource") == "TrackerResource"  # was domain_resource_base
    assert n.class_name("tracker", "Client") == "TrackerClient"      # was domain_client_class
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать**

```python
# src/refract/emitters/python/naming.py
from __future__ import annotations

import builtins
import keyword

from refract.emitters.api import Naming

# Names a module-level ``def`` would shadow (builtins + keywords) - instance/module state now,
# not the old module-global _SHADOWED_NAMES in _common.py.
_SHADOWED = frozenset(dir(builtins)) | frozenset(keyword.kwlist)


class PythonNaming(Naming):
    """Python identifier casing + shadow-guarding + class naming."""

    def pascal(self, name: str) -> str:
        return "".join(part.capitalize() for part in name.split("_"))

    def module_function(self, name: str) -> str:
        return f"{name}_" if name in _SHADOWED else name

    def class_name(self, base: str, suffix: str) -> str:
        return f"{self.pascal(base)}{suffix}"
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(python): PythonNaming (kills _SHADOWED_NAMES global + merges 3 *_class helpers)`)

### Task 4.2: `PythonTypeMapper`

**Files:**
- Create: `src/refract/emitters/python/types.py`
- Test: `tests/emitters/python/test_types.py`

**Interfaces:**
- Consumes: `TypeMapper`, `RenderedType`, `Import` (разд. C); `NeutralType` (разд. A).
- Produces: `PythonTypeMapper` - `render(neutral_type, *, optional) -> RenderedType`, `null_default(neutral_type, *, optional) -> str | None`. Здесь живёт лоуринг (бывший `_lower_type`), `match` + `assert_never`.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/emitters/python/test_types.py
from refract.emitters.api import Import
from refract.emitters.python.types import PythonTypeMapper
from refract.ir.types import ListType, MapType, RefType, ScalarType

m = PythonTypeMapper()


def test_scalar_lowering():
    assert m.render(ScalarType(scalar="integer"), optional=False).text == "int"
    assert m.render(ScalarType(scalar="string"), optional=False).text == "str"
    assert m.render(ScalarType(scalar="number"), optional=False).text == "float"
    assert m.render(ScalarType(scalar="boolean"), optional=False).text == "bool"


def test_optional_appends_none_and_default():
    rt = m.render(ScalarType(scalar="integer"), optional=True)
    assert rt.text == "int | None"
    assert m.null_default(ScalarType(scalar="integer"), optional=True) == "None"
    assert m.null_default(ScalarType(scalar="integer"), optional=False) is None


def test_ref_is_bare_model_name():
    assert m.render(RefType(target="LocalizedName"), optional=False).text == "LocalizedName"


def test_any_pulls_typing_import():
    rt = m.render(ScalarType(scalar="any"), optional=False)
    assert rt.text == "Any" and Import("typing", "Any") in rt.imports


def test_containers():
    assert m.render(ListType(item=ScalarType(scalar="string")), optional=False).text == "list[str]"
    assert (
        m.render(MapType(key=ScalarType(scalar="string"), value=ScalarType(scalar="integer")),
                 optional=False).text
        == "dict[str, int]"
    )
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать**

```python
# src/refract/emitters/python/types.py
from __future__ import annotations

from typing import assert_never

from refract.emitters.api import Import, RenderedType, TypeMapper
from refract.ir.types import ListType, MapType, NeutralType, RefType, ScalarType

_SCALAR = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}


class PythonTypeMapper(TypeMapper):
    """Lower a NeutralType to a Python type string (+ the imports it needs)."""

    def render(self, neutral_type: NeutralType, *, optional: bool) -> RenderedType:
        base = self._base(neutral_type)
        if optional:
            return RenderedType(text=f"{base.text} | None", imports=base.imports)
        return base

    def null_default(self, neutral_type: NeutralType, *, optional: bool) -> str | None:
        return "None" if optional else None

    def _base(self, neutral_type: NeutralType) -> RenderedType:
        match neutral_type:
            case ScalarType(scalar="any"):
                return RenderedType(text="Any", imports=(Import("typing", "Any"),))
            case ScalarType(scalar=scalar):
                return RenderedType(text=_SCALAR[scalar])
            case RefType(target=target):
                return RenderedType(text=target)
            case ListType(item=item):
                inner = self._base(item)
                return RenderedType(text=f"list[{inner.text}]", imports=inner.imports)
            case MapType(key=key, value=value):
                kr, vr = self._base(key), self._base(value)
                return RenderedType(text=f"dict[{kr.text}, {vr.text}]",
                                    imports=kr.imports + vr.imports)
            case _:
                assert_never(neutral_type)
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(python): PythonTypeMapper (lowering leaves the loader, gains list/map + assert_never)`)

### Task 4.3: `RuffFormatter`

**Files:**
- Create: `src/refract/emitters/python/format.py`
- Test: `tests/emitters/python/test_format.py`

**Interfaces:**
- Consumes: `Formatter` (разд. C).
- Produces: `RuffFormatter.format(source) -> str` - **два прохода** stdin: `ruff check --select I --fix` (сортировка импортов; проверено - работает через stdin, exit 0) -> `ruff format`; ошибки -> `RuntimeError`. Это снимает с ассемблера обязанность реимплементить isort - он эмитит `from x import ...` в любом порядке, ruff упорядочивает.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/emitters/python/test_format.py
import pytest

from refract.emitters.python.format import RuffFormatter

f = RuffFormatter()


def test_formats_via_ruff():
    assert f.format("x=1\ny  =  2\n") == "x = 1\ny = 2\n"


def test_reformats_dict_spacing():
    assert f.format('d={ "a":1 }\n') == 'd = {"a": 1}\n'


def test_sorts_imports():
    src = "from .models import Me\nimport typer\n\n\ndef f():\n    return (typer, Me)\n"
    out = f.format(src)
    assert out.index("import typer") < out.index("from .models import Me")


def test_syntax_error_raises_runtime_error():
    with pytest.raises(RuntimeError):
        f.format("def (:\n")  # invalid syntax -> ruff exits non-zero
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать**

```python
# src/refract/emitters/python/format.py
from __future__ import annotations

import subprocess

from refract.emitters.api import Formatter

_STDIN_NAME = "generated.py"


class RuffFormatter(Formatter):
    """The ruff post-pass authority: sort imports (rule I), then format."""

    def format(self, source: str) -> str:
        sorted_imports = self._run(
            ["ruff", "check", "--select", "I", "--fix", "--stdin-filename", _STDIN_NAME, "-"],
            source,
        )
        return self._run(
            ["ruff", "format", "--stdin-filename", _STDIN_NAME, "-"], sorted_imports
        )

    @staticmethod
    def _run(cmd: list[str], source: str) -> str:
        try:
            result = subprocess.run(cmd, input=source, capture_output=True, text=True, check=True)
        except FileNotFoundError as error:  # ruff missing from PATH
            raise RuntimeError("ruff not found on PATH") from error
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"ruff failed ({' '.join(cmd)}):\n{error.stderr}") from error
        return result.stdout
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(python): RuffFormatter (import-sort + format, two stdin passes)`)

### Task 4.4: `PythonDocstrings`

**Files:**
- Create: `src/refract/emitters/python/docstrings.py`
- Test: `tests/emitters/python/test_docstrings.py`

**Interfaces:**
- Consumes: `Docstrings` (разд. C).
- Produces: `PythonDocstrings.render(text, indent) -> tuple[str, ...]` - порт `render_doc` (пусто -> `()`; одна строка -> одна тройная кавычка; многострочно -> open/тело/close с реиндентом).

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/emitters/python/test_docstrings.py
from refract.emitters.python.docstrings import PythonDocstrings

d = PythonDocstrings()


def test_absent_text_is_empty():
    assert d.render(None, "    ") == ()
    assert d.render("", "    ") == ()


def test_single_line():
    assert d.render("Hello.", "    ") == ('    """Hello."""',)


def test_multiline_reindents_and_closes_on_own_line():
    out = d.render("First.\n\n    Indented.", "    ")
    assert out == ('    """First.', "", "        Indented.", '    """')
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать**

```python
# src/refract/emitters/python/docstrings.py
from __future__ import annotations

from refract.emitters.api import Docstrings


class PythonDocstrings(Docstrings):
    """Render a triple-quoted docstring block (tuple of lines) at a given indent."""

    def render(self, text: str | None, indent: str) -> tuple[str, ...]:
        if not text:
            return ()
        lines = text.split("\n")
        if len(lines) == 1:
            return (f'{indent}"""{text}"""',)
        body = tuple(f"{indent}{line}" if line else "" for line in lines[1:])
        return (f'{indent}"""{lines[0]}', *body, f'{indent}"""')
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(python): PythonDocstrings (ports render_doc to a strategy)`)

### Task 4.5: `PythonLayout`

**Files:**
- Create: `src/refract/emitters/python/layout.py`
- Test: `tests/emitters/python/test_layout.py`

**Interfaces:**
- Consumes: `Layout` (разд. C); `ir` (разд. B).
- Produces: `PythonLayout.path(res, surface) -> str` - развязывает имя surface от имени файла (`requests` -> `_requests.py`, `package` -> `__init__.py`, `tests` -> `tests/<domain>/test_<resource>.py`).

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/emitters/python/test_layout.py
from refract import ir
from refract.emitters.python.layout import PythonLayout

lay = PythonLayout()
_res = ir.Resource(domain="tracker", resource="me", security="s",
                   models=(), operations=())


def test_surface_paths():
    assert lay.path(_res, "requests") == "tracker/me/_requests.py"
    assert lay.path(_res, "client") == "tracker/me/client.py"
    assert lay.path(_res, "models") == "tracker/me/models.py"
    assert lay.path(_res, "mcp") == "tracker/me/mcp.py"
    assert lay.path(_res, "package") == "tracker/me/__init__.py"
    assert lay.path(_res, "tests") == "tests/tracker/test_me.py"
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать**

```python
# src/refract/emitters/python/layout.py
from __future__ import annotations

from refract import ir
from refract.emitters.api import Layout

_FILENAME = {"requests": "_requests", "client": "client", "models": "models",
             "cli": "cli", "mcp": "mcp"}


class PythonLayout(Layout):
    """Map (resource, surface) -> emitted file path (decouples surface id from filename)."""

    def path(self, res: ir.Resource, surface: str) -> str:
        base = f"{res.domain}/{res.resource}"
        if surface == "tests":
            return f"tests/{res.domain}/test_{res.resource}.py"
        if surface == "package":
            return f"{base}/__init__.py"
        return f"{base}/{_FILENAME[surface]}.py"
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(python): PythonLayout (surface->path)`)

---

## PHASE 5 / Общая инфра рендеринга (view-model + Jinja + резолв-хелперы)

**Уточнение рендеринга (подтверждено против ruff 0.15.21, зафиксировано как решение G4):** `ruff format` сам нормализует вертикальные пробелы (2 строки между top-level `def`, 1 между методами, пустая после докстринга) и горизонтальные (перенос длинных сигнатур). Поэтому:
- шаблоны Jinja контролируют **только контент + семантический отступ**, не пустые строки;
- «мудрёная» логика (сигнатура, keyword-only `*`, докстринги, union-форма) резолвится в **типизированном Python** (резолвер + `op.body`-ветвление read/write + `assert_never` по union'ам `Model`/`NeutralType`/`AuthScheme`), а не в Jinja-макросах - это строго безопаснее и тестируется без рендера;
- Jinja получает **готовые листья** (методы как готовые многострочные строки) + раскладывает скелет модуля (докстринг -> импорты -> тело), давая USP «форма файла видна целиком».

### Task 5.1: `environment.py` - Jinja `Environment`

**Files:**
- Create: `src/refract/emitters/python/environment.py`
- Test: `tests/emitters/python/test_environment.py`

**Interfaces:**
- Produces: `make_environment() -> jinja2.Environment` (конфиг из Global Constraints). Потребляется surface-эмиттерами.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/emitters/python/test_environment.py
import jinja2
import pytest

from refract.emitters.python.environment import make_environment

env = make_environment()


def test_strict_undefined_raises_on_missing():
    with pytest.raises(jinja2.UndefinedError):
        env.from_string("{{ missing }}").render()


def test_trim_blocks_strips_newline_after_block_tag():
    out = env.from_string("{% for x in xs %}{{ x }}\n{% endfor %}").render(xs=["a", "b"])
    assert out == "a\nb\n"


def test_keeps_trailing_newline():
    assert env.from_string("x\n").render() == "x\n"
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать**

```python
# src/refract/emitters/python/environment.py
from __future__ import annotations

from jinja2 import Environment, PackageLoader, StrictUndefined


def make_environment() -> Environment:
    """The single Jinja Environment for the Python backend (see Global Constraints)."""
    return Environment(
        loader=PackageLoader("refract.emitters.python", "templates"),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(python): Jinja Environment (StrictUndefined, trim_blocks, PackageLoader)`)

### Task 5.2: `views.py` + `resolve.py` - общие атомы + резолв-хелперы

**Files:**
- Create: `src/refract/emitters/python/views.py`, `src/refract/emitters/python/resolve.py`
- Test: `tests/emitters/python/test_resolve.py`

**Interfaces:**
- Consumes: `Import` (разд. C), `TypeMapper`/`Naming`/`Docstrings` (разд. C).
- Produces:
  - `views._View` - frozen-pydantic база для всех view-model (per-surface page-views добавляются в фазе 7).
  - `resolve.render_imports(imports) -> tuple[str, ...]` - union -> group-by-module -> merge names -> `from m import a, b` (порядок неважен, ruff сортирует).
  - `resolve.signature_params(positional, keyword_only) -> tuple[str, ...]` - вставляет `*` перед первым keyword-only.
  - `resolve.indent_lines(lines, prefix) -> tuple[str, ...]` - префикс к непустым строкам.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/emitters/python/test_resolve.py
from refract.emitters.api import Import
from refract.emitters.python import resolve


def test_render_imports_groups_and_merges():
    out = resolve.render_imports((Import(".models", "Me"), Import(".models", "Priority"),
                                  Import("typing", "Any")))
    assert "from .models import Me, Priority" in out
    assert "from typing import Any" in out


def test_signature_params_inserts_star_for_keyword_only():
    assert resolve.signature_params(("self", "priority_id: str"),
                                    ("version: int | None = None",)) == (
        "self", "priority_id: str", "*", "version: int | None = None")


def test_signature_params_no_star_when_no_keyword_only():
    assert resolve.signature_params(("self",), ()) == ("self",)


def test_indent_lines_skips_blanks():
    assert resolve.indent_lines(("a", "", "b"), "    ") == ("    a", "", "    b")
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать**

```python
# src/refract/emitters/python/views.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _View(BaseModel):
    """Base for every view-model: frozen, and every field a resolved primitive (no ir/shape tags)."""
    model_config = ConfigDict(frozen=True)
```

```python
# src/refract/emitters/python/resolve.py
from __future__ import annotations

from collections import defaultdict

from refract.emitters.api import Import


def render_imports(imports: tuple[Import, ...]) -> tuple[str, ...]:
    """Union -> group-by-module -> merge names -> `from <module> import <names>` (ruff orders)."""
    by_module: dict[str, set[str]] = defaultdict(set)
    for imp in imports:
        by_module[imp.module].add(imp.name)
    return tuple(
        f"from {module} import {', '.join(sorted(names))}" for module, names in by_module.items()
    )


def signature_params(positional: tuple[str, ...], keyword_only: tuple[str, ...]) -> tuple[str, ...]:
    """Assemble a param list, inserting the `*` marker before the first keyword-only param."""
    if keyword_only:
        return (*positional, "*", *keyword_only)
    return positional


def indent_lines(lines: tuple[str, ...], prefix: str) -> tuple[str, ...]:
    """Prefix every non-blank line (blank lines stay empty)."""
    return tuple(f"{prefix}{line}" if line else "" for line in lines)
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(python): shared view base + resolve helpers (imports, signature, indent)`)

### Task 5.3: `templates/_module.jinja` - базовый скелет

**Files:**
- Create: `src/refract/emitters/python/templates/_module.jinja`
- Test: `tests/emitters/python/test_module_template.py`

**Interfaces:**
- Produces: базовый шаблон `_module.jinja` с блоком `body`; принимает `page` с полями `doc_block: tuple[str,...]`, `header_lines: tuple[str,...]`, `import_lines: tuple[str,...]`. Наследуется всеми surface-шаблонами (фаза 7). Шаблоны - git-tracked (иначе hatchling не положит в wheel).

- [ ] **Step 1: Написать падающий тест** (рендер через дочерний inline-шаблон)

```python
# tests/emitters/python/test_module_template.py
from refract.emitters.python.environment import make_environment


def test_module_skeleton_lays_out_doc_imports_body():
    env = make_environment()
    child = env.from_string(
        '{% extends "_module.jinja" %}{% block body %}CLASS_BODY\n{% endblock %}'
    )
    out = child.render(page={
        "doc_block": ('"""Doc."""',),
        "header_lines": (),
        "import_lines": ("from .models import Me",),
    })
    assert '"""Doc."""' in out
    assert "from .models import Me" in out
    assert "CLASS_BODY" in out
    assert out.index('"""Doc."""') < out.index("from .models import Me") < out.index("CLASS_BODY")
```

- [ ] **Step 2: Прогнать - падает** (шаблон отсутствует) -> **Step 3: Реализовать**

```jinja
{# src/refract/emitters/python/templates/_module.jinja #}
{% for line in page.doc_block %}{{ line }}
{% endfor %}
{% for line in page.header_lines %}{{ line }}
{% endfor %}
{% for line in page.import_lines %}{{ line }}
{% endfor %}
{% block body %}{% endblock %}
```

(С `trim_blocks`+`lstrip_blocks` теги `{% for %}` исчезают, оставляя только строки `{{ line }}`+`\n`; ruff нормализует пустые строки после форматирования surface-эмиттером.)

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(python): base _module.jinja skeleton template`)

---

## PHASE 6 / Референс-рантайм D + auth-механизмы

### Task 6.1: `runtime/` core - `Request[T]` + `Session.send` + `Resource` base

**Files:**
- Create: `src/refract/runtime/__init__.py`, `src/refract/runtime/request.py`, `src/refract/runtime/session.py`, `src/refract/runtime/base.py`
- Test: `tests/runtime/test_request.py`, `tests/runtime/test_session.py`

**Interfaces:**
- Produces: `Request` (разд. E, чистый sans-I/O дескриптор вызова), `Session` (разд. E, auth-agnostic executor над PRE-configured `httpx.Client`), `Resource` base (разд. E, держит общую `Session`). Импортируется L3-фикстурами; эталон для ycli-рантайма. (Auth-механизмы `HeaderAuth`/`MultiHeaderAuth` - Task 6.2.)

- [ ] **Step 1: Написать падающие тесты** (`Request` конструируется; `Session.send` через stubbed httpx `httpx.MockTransport`)

```python
# tests/runtime/test_request.py
import dataclasses

import pytest

from refract.runtime import Request


def test_request_constructs_frozen_with_empty_defaults():
    req = Request(method="GET", path="myself", response_model=dict)
    assert (req.method, req.path, req.response_model) == ("GET", "myself", dict)
    assert req.query is None and req.json_body is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.method = "POST"  # frozen + slots
```

```python
# tests/runtime/test_session.py
import httpx
from pydantic import BaseModel

from refract.runtime import Request, Session


class _Me(BaseModel):
    login: str


def _session(handler) -> Session:
    return Session("https://api.example/v3", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_send_builds_url_parses_response_model():
    def handler(req):
        assert req.url.path == "/v3/myself"
        return httpx.Response(200, json={"login": "alice"})
    me = _session(handler).send(Request(method="GET", path="myself", response_model=_Me))
    assert isinstance(me, _Me) and me.login == "alice"


def test_send_drops_none_query_and_sends_json():
    def handler(req):
        assert "version" not in req.url.params           # None dropped
        assert req.read() == b'{"name": "x"}'
        return httpx.Response(200, json={"login": "z"})
    _session(handler).send(Request(method="PATCH", path="p/1", response_model=_Me,
                                   query={"version": None}, json_body={"name": "x"}))


def test_send_raises_for_status():
    def handler(req):
        return httpx.Response(404, json={})
    import pytest
    with pytest.raises(httpx.HTTPStatusError):
        _session(handler).send(Request(method="GET", path="missing", response_model=_Me))
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать** `runtime/request.py` + `runtime/session.py` + `runtime/base.py` дословно по разд. E, плюс `runtime/__init__.py` (без auth - она в Task 6.2):

```python
# src/refract/runtime/request.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")

@dataclass(frozen=True, slots=True)
class Request(Generic[T]):
    """A pure, transport-agnostic description of one HTTP call - no I/O."""
    method: str
    path: str
    response_model: type[T]
    query: dict[str, Any] | None = None
    json_body: Any = None
```

```python
# src/refract/runtime/session.py
from __future__ import annotations
from typing import TypeVar
import httpx
from refract.runtime.request import Request

T = TypeVar("T")

class Session:
    """Executes any Request over a PRE-CONFIGURED httpx.Client. AUTH-AGNOSTIC: auth lives on the
    injected client (httpx.Auth), not here. Owns base_url + minimal error policy (the ONLY I/O)."""
    def __init__(self, base_url: str, *, client: httpx.Client) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    def send(self, request: Request[T]) -> T:
        params = {k: v for k, v in (request.query or {}).items() if v is not None}
        response = self._client.request(
            request.method,
            f"{self._base_url}/{request.path}",
            params=params or None,
            json=request.json_body,
        )
        response.raise_for_status()
        return request.response_model.model_validate(response.json())
```

```python
# src/refract/runtime/base.py - generic per-resource base holding the shared Session (reference; ycli subclasses)
from __future__ import annotations
from refract.runtime.session import Session


class Resource:
    def __init__(self, session: Session) -> None:
        self._session = session
```

```python
# src/refract/runtime/__init__.py
"""D reference runtime: a pure Request[T], a send() executor, and a Resource base.
ycli hand-writes its own copy; L3 fixtures import this one."""

from refract.runtime.base import Resource
from refract.runtime.request import Request
from refract.runtime.session import Session

__all__ = ["Request", "Resource", "Session"]
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(runtime): D reference runtime - Request[T] + Session.send + Resource base`)

### Task 6.2: `runtime/auth.py` - `httpx.Auth` механизмы (`HeaderAuth` + `MultiHeaderAuth`)

**Files:**
- Create: `src/refract/runtime/auth.py`
- Modify: `src/refract/runtime/__init__.py` (реэкспорт auth-механизмов)
- Test: `tests/runtime/test_auth.py`

**Interfaces:**
- Produces: `HeaderAuth`, `MultiHeaderAuth` (разд. E) - библиотека `httpx.Auth` механизмов (без I/O -> sync+async). Инжектируется в `httpx.Client(auth=...)` сгенерированным root-client'ом (разд. F); auth НЕ живёт в `send()` (`Request[T]` навсегда чист). Растёт по rule-of-three (разд. H): `BasicAuth`, `ApiKeyQueryAuth`, `SigV4Auth`, `OAuth2RefreshAuth`, `CustomAuth`.

- [ ] **Step 1: Написать падающие тесты** (`auth_flow` мутирует `request.headers`, ассерт на заголовках)

```python
# tests/runtime/test_auth.py
import httpx

from refract.runtime.auth import HeaderAuth, MultiHeaderAuth


def test_header_auth_injects_single_header():
    request = httpx.Request("GET", "https://api.example/v3/myself")
    signed = next(HeaderAuth("Authorization", "Bearer t").auth_flow(request))
    assert signed.headers["Authorization"] == "Bearer t"


def test_multi_header_auth_injects_both_headers():
    request = httpx.Request("GET", "https://api.example/v3/myself")
    auth = MultiHeaderAuth({"Authorization": "OAuth tok", "X-Org-Id": "42"})
    signed = next(auth.auth_flow(request))
    assert signed.headers["Authorization"] == "OAuth tok"
    assert signed.headers["X-Org-Id"] == "42"
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать** `runtime/auth.py` дословно по разд. E, плюс обновить `runtime/__init__.py` (добавить реэкспорт auth-механизмов):

```python
# src/refract/runtime/auth.py - the auth MECHANISM library (hand-written; grows by rule-of-three)
from __future__ import annotations
from collections.abc import Iterator
import httpx


class HeaderAuth(httpx.Auth):
    """Single-header credential, e.g. ``Authorization: Bearer <token>``. No I/O -> sync+async."""
    def __init__(self, header: str, value: str) -> None:
        self._header = header
        self._value = value

    def auth_flow(self, request: httpx.Request) -> Iterator[httpx.Request]:
        request.headers[self._header] = self._value
        yield request


class MultiHeaderAuth(httpx.Auth):
    """>=1 constant headers (Cloudflare X-Auth-*; Yandex ``Authorization: OAuth ...`` + ``X-Org-Id``)."""
    def __init__(self, headers: dict[str, str]) -> None:
        self._headers = dict(headers)

    def auth_flow(self, request: httpx.Request) -> Iterator[httpx.Request]:
        request.headers.update(self._headers)
        yield request
```

```python
# src/refract/runtime/__init__.py
"""D reference runtime: a pure Request[T], a send() executor, httpx.Auth mechanisms, and a
Resource base. ycli hand-writes its own copy; L3 fixtures import this one."""

from refract.runtime.auth import HeaderAuth, MultiHeaderAuth
from refract.runtime.base import Resource
from refract.runtime.request import Request
from refract.runtime.session import Session

__all__ = ["HeaderAuth", "MultiHeaderAuth", "Request", "Resource", "Session"]
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(runtime): httpx.Auth mechanisms - HeaderAuth + MultiHeaderAuth`)

---

## PHASE 7 / Surface-эмиттеры (форма D)

Каждый surface: per-surface page-view (в `views.py`) + резолвер (в `resolve.py`) + шаблон (наследует `_module.jinja`) + класс `SurfaceEmitter`. Резолвер строит **готовые листья** (методы/функции как многострочные строки, корректно отступленные), шаблон раскладывает, `Generator` форматит (`RuffFormatter`, фаза 8). Таргеты - разд. F; для F2-неизменных surface'ов таргет = текущий golden.

Общий хелпер (добавляется в `resolve.py` этой фазой, переиспользуется client/cli/mcp):

```python
# appended to src/refract/emitters/python/resolve.py
from refract.emitters.api import Import, TypeMapper
from refract import ir


def param_decl(param: ir.Param, type_mapper: TypeMapper) -> tuple[str, tuple[Import, ...]]:
    """Render one parameter declaration `name: Type` (+ ` = default`) and its imports."""
    rt = type_mapper.render(param.type, optional=param.optional)
    default = param.default if param.default is not None else type_mapper.null_default(
        param.type, optional=param.optional
    )
    decl = f"{param.name}: {rt.text}"
    if default is not None:
        decl = f"{decl} = {default}"
    return decl, rt.imports


def path_expr(path: str) -> str:
    """Emit an f-string when the path has `{placeholders}`, else a plain string literal."""
    return f'f"{path}"' if "{" in path else f'"{path}"'
```

### Task 7.1: `_requests` surface (D-ядро)

**Files:**
- Create: `src/refract/emitters/python/surfaces/__init__.py`, `src/refract/emitters/python/surfaces/requests.py`, `src/refract/emitters/python/templates/requests.jinja`
- Modify: `src/refract/emitters/python/views.py` (+`RequestsPageView`), `src/refract/emitters/python/resolve.py` (+`resolve_requests`)
- Test: `tests/emitters/python/surfaces/test_requests.py`

**Interfaces:**
- Consumes: read/write ветвление локально по `op.body is not None` (разд. D, БЕЗ `classify`/`shapes.py`), `Naming`/`TypeMapper`/`Docstrings` (разд. C), `param_decl`/`path_expr`/`signature_params`/`render_imports` (Phase 5/7). Write-путь рендерит `body.model_dump(...)` прямо из флагов `ir.Body` (`by_alias`/`omit_none`, разд. B) - `Body.dump` больше нет.
- Produces: `RequestsSurface(SurfaceEmitter)` - эмитит `_requests.py` (разд. F). `applies` = всегда (у ресурса всегда есть операции). Таргеты: me/_requests.py, priorities/_requests.py (разд. F).

- [ ] **Step 1: Написать падающий снапшот-тест**

```python
# tests/emitters/python/surfaces/test_requests.py
from refract.emitters.api import EmitContext

CTX = EmitContext(package_root="ycli.yandex.tracker")


def _emit(res):
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.types import PythonTypeMapper
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.format import RuffFormatter
    from refract.emitters.python.surfaces.requests import RequestsSurface
    surface = RequestsSurface(PythonNaming(), PythonTypeMapper(), PythonDocstrings(),
                              make_environment())
    return RuffFormatter().format(surface.emit(res, CTX))


def test_me_requests(me_resource):
    out = _emit(me_resource)
    assert "def get() -> Request[Me]:" in out
    assert 'return Request(method="GET", path="myself", response_model=Me)' in out
    assert "from ycli.yandex.tracker.runtime import Request" in out
    assert "from .models import Me" in out


def test_priorities_requests(priorities_resource):
    out = _emit(priorities_resource)
    assert "def list_() -> Request[PriorityList]:" in out            # module-level shadow guard
    assert "def create(body: PriorityCreate) -> Request[Priority]:" in out
    # edit's signature is >100 cols -> ruff hug-wraps it; assert the wrapped params line, not a
    # contiguous single-line `def edit(...)` (which ruff splits onto its own lines).
    assert "def edit(" in out
    assert "priority_id: str, body: PriorityUpdate, *, version: int | None = None" in out
    # write path renders model_dump flags straight off the ir.Body value object (by_alias/omit_none)
    assert 'json_body=body.model_dump(by_alias=True, exclude_none=True)' in out
    assert 'path=f"priorities/{priority_id}"' in out
    assert 'query={"version": version}' in out
```

- [ ] **Step 2: Прогнать - падает**

- [ ] **Step 3: Реализовать view + resolver + шаблон + surface**

```python
# appended to src/refract/emitters/python/views.py
class RequestsPageView(_View):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    functions: tuple[str, ...] = ()
```

```python
# appended to src/refract/emitters/python/resolve.py
from refract.emitters.python.views import RequestsPageView

# NB: no `classify`/`SimpleRead`/`TypedWrite` import - read/write is a local branch on
# `op.body is not None` (разд. D). `Import`, `TypeMapper`, `ir`, `param_decl`, `path_expr`,
# `signature_params`, `render_imports` are already in this module (Phase 5/7 helper block).


def _request_doc(op: ir.Operation, *, write: bool) -> str:
    if write:
        return f"``{op.method} /{op.path}`` - {op.name} request from a typed body."
    return f"``{op.method} /{op.path}`` -> {op.response_model} request builder."


def _request_function(op, naming, type_mapper, docstrings) -> tuple[str, list[Import]]:
    body = op.body                       # write iff not None (разд. D; narrowed to ir.Body below)
    imports: list[Import] = []
    positional: list[str] = []
    for p in op.params:
        if p.loc == "path":
            decl, imp = param_decl(p, type_mapper)
            positional.append(decl)
            imports += imp
    if body is not None:                 # write: typed body positional + `.models` import
        positional.append(f"body: {body.model}")
        imports.append(Import(".models", body.model))
    keyword_only: list[str] = []
    for p in op.params:
        if p.loc == "query":
            decl, imp = param_decl(p, type_mapper)
            keyword_only.append(decl)
            imports += imp
    params = signature_params(tuple(positional), tuple(keyword_only))
    imports.append(Import(".models", op.response_model))
    sig = f"def {naming.module_function(op.name)}({', '.join(params)}) -> Request[{op.response_model}]:"

    kwargs = [f'method="{op.method}"', f"path={path_expr(op.path)}"]
    query_items = [f'"{p.alias or p.name}": {p.name}' for p in op.params if p.loc == "query"]
    if query_items:
        kwargs.append("query={" + ", ".join(query_items) + "}")
    if body is not None:                 # render model_dump flags straight off ir.Body (no .dump)
        kwargs.append(
            f"json_body=body.model_dump(by_alias={body.by_alias}, exclude_none={body.omit_none})"
        )
    kwargs.append(f"response_model={op.response_model}")

    doc = docstrings.render(_request_doc(op, write=body is not None), "    ")
    lines = [sig, *doc, f"    return Request({', '.join(kwargs)})"]
    return "\n".join(lines), imports


def resolve_requests(res, ctx, naming, type_mapper, docstrings) -> RequestsPageView:
    imports: list[Import] = [Import(f"{ctx.package_root}.runtime", "Request")]
    functions: list[str] = []
    for op in res.operations:
        text, fimports = _request_function(op, naming, type_mapper, docstrings)
        functions.append(text)
        imports += fimports
    module_doc = res.module_docs.requests or (
        f"Request builders for {res.domain_title} {res.resource} - "
        "the single HTTP contract (sans-I/O)."
    )
    return RequestsPageView(
        doc_block=docstrings.render(module_doc, ""),
        import_lines=render_imports(tuple(imports)),
        functions=tuple(functions),
    )
```

```jinja
{# src/refract/emitters/python/templates/requests.jinja #}
{% extends "_module.jinja" %}
{% block body %}
{% for func in page.functions %}
{{ func }}
{% endfor %}
{% endblock %}
```

```python
# src/refract/emitters/python/surfaces/requests.py
from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.api import EmitContext, SurfaceEmitter
from refract.emitters.python.resolve import resolve_requests

if TYPE_CHECKING:
    from jinja2 import Environment
    from refract import ir
    from refract.emitters.api import Docstrings, Naming, TypeMapper


class RequestsSurface(SurfaceEmitter):
    name = "requests"

    def __init__(self, naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings,
                 env: Environment) -> None:
        self._naming, self._type_mapper, self._docstrings, self._env = (
            naming, type_mapper, docstrings, env)

    def applies(self, res: ir.Resource) -> bool:
        return bool(res.operations)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = resolve_requests(res, ctx, self._naming, self._type_mapper, self._docstrings)
        return self._env.get_template("requests.jinja").render(page=page)
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(python): _requests surface (D request builders)`)

### Task 7.2: `client` surface (D thin sugar, F2)

Клиент под D+**F2** - это тонкий сахар над `_requests`: один метод на операцию, тело метода = `return self._session.send(_requests.<fn>(<args>))`. Ни `@uplink`, ни `_verb`/`verb`-split, ни ручного `model_dump` - HTTP-контракт целиком лежит в `_requests` (Task 7.1), а богатая публичная prose (Example-блоки) остаётся на методах клиента. Резолвер строит **готовые листья** (методы как многострочные строки, отступленные внутрь класса), шаблон раскладывает скелет, `Generator` форматит (`RuffFormatter`, фаза 8). Таргеты - разд. F (`me/client.py`, `priorities/client.py`).

**Files:**
- Create: `src/refract/emitters/python/surfaces/client.py`, `src/refract/emitters/python/templates/client.jinja`
- Modify: `src/refract/emitters/python/views.py` (+`ClientPageView`), `src/refract/emitters/python/resolve.py` (+`resolve_client`)
- Test: `tests/emitters/python/surfaces/test_client.py`

**Interfaces:**
- Consumes: read/write ветвление локально по `op.body is not None` (разд. D, БЕЗ `classify`/`SimpleRead`/`TypedWrite`), `Naming`/`TypeMapper`/`Docstrings` (разд. C), `param_decl` (Phase 7) + `signature_params`/`indent_lines`/`render_imports` (Phase 5).
- Produces: `ClientSurface(SurfaceEmitter)` - эмитит `client.py` (разд. F). `applies` = `bool(res.operations)`. Таргеты: `me/client.py`, `priorities/client.py` (разд. F).

- [ ] **Step 1: Написать падающий снапшот-тест**

```python
# tests/emitters/python/surfaces/test_client.py
from refract.emitters.api import EmitContext

CTX = EmitContext(package_root="ycli.yandex.tracker")


def _emit(res):
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.format import RuffFormatter
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.client import ClientSurface
    from refract.emitters.python.types import PythonTypeMapper

    surface = ClientSurface(PythonNaming(), PythonTypeMapper(), PythonDocstrings(),
                            make_environment())
    return RuffFormatter().format(surface.emit(res, CTX))


def test_me_client(me_resource):
    out = _emit(me_resource)
    assert "class MeClient(TrackerResource):" in out
    assert "def get(self) -> Me:" in out
    assert "return self._session.send(_requests.get())" in out
    assert "from . import _requests" in out
    assert "from ycli.yandex.tracker.base import TrackerResource" in out
    # thin sugar only - no uplink decorators, no private _verb split
    assert "@uplink" not in out


def test_priorities_client(priorities_resource):
    out = _emit(priorities_resource)
    assert "class PrioritiesClient(TrackerResource):" in out
    # method name is verbatim (`list`), the builder call uses the shadow-guarded `list_`
    assert "def list(self) -> PriorityList:" in out
    assert "return self._session.send(_requests.list_())" in out
    # write op: `body: <model>` positional, call passes `body` through unchanged
    assert "def create(self, body: PriorityCreate) -> Priority:" in out
    assert "return self._session.send(_requests.create(body))" in out
    # edit: path positional + typed body + keyword-only query; ruff hug-wraps the >100-col def
    assert "def edit(" in out
    assert "self, priority_id: str, body: PriorityUpdate, *, version: int | None = None" in out
    assert "return self._session.send(_requests.edit(priority_id, body, version=version))" in out
    assert "from . import _requests" in out
    # F2: the uplink `_verb`/`verb` split is gone entirely
    assert "@uplink" not in out
    assert "def _create" not in out
    assert "def _edit" not in out
```

- [ ] **Step 2: Прогнать - падает** (surface/шаблон/view/resolver отсутствуют)

Run: `pytest tests/emitters/python/surfaces/test_client.py -q` -> FAIL (ImportError: `ClientSurface`)

- [ ] **Step 3: Реализовать view + resolver + шаблон + surface**

```python
# appended to src/refract/emitters/python/views.py
class ClientPageView(_View):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    class_header: str
    class_doc_lines: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
```

```python
# appended to src/refract/emitters/python/resolve.py
from refract.emitters.python.views import ClientPageView

# `Import`, `TypeMapper`, `ir`, `param_decl`, `path_expr` (Phase 7), `signature_params`,
# `indent_lines`, `render_imports` (Task 5.2) are already imported in this module.
# read/write is decided locally by `op.body is not None` (разд. D) - no classify/shape import.


def _client_method(op, naming, type_mapper, docstrings) -> tuple[str, list[Import]]:
    """One thin-sugar method leaf: `def <op.name>(...): return self._session.send(_requests.<fn>(...))`.

    Built at module nesting (docstring/body at 4 spaces), then indented one level to sit inside
    the class. Method name is verbatim `op.name`; the builder call uses `module_function(op.name)`
    (the shadow guard, so `list` -> `_requests.list_`). Docstring is the FULL `op.documentation`.
    """
    body = op.body                       # write iff not None (разд. D; narrowed to ir.Body below)
    imports: list[Import] = []
    positional: list[str] = ["self"]
    call_args: list[str] = []
    for p in op.params:
        if p.loc == "path":
            decl, imp = param_decl(p, type_mapper)
            positional.append(decl)
            call_args.append(p.name)
            imports += imp
    if body is not None:                 # write: typed body positional, forwarded through unchanged
        positional.append(f"body: {body.model}")
        call_args.append("body")
        imports.append(Import(".models", body.model))
    keyword_only: list[str] = []
    for p in op.params:
        if p.loc == "query":
            decl, imp = param_decl(p, type_mapper)
            keyword_only.append(decl)
            call_args.append(f"{p.name}={p.name}")
            imports += imp
    params = signature_params(tuple(positional), tuple(keyword_only))
    imports.append(Import(".models", op.response_model))
    sig = f"def {op.name}({', '.join(params)}) -> {op.response_model}:"
    call = f"_requests.{naming.module_function(op.name)}({', '.join(call_args)})"
    doc = docstrings.render(op.documentation, "    ")
    body_lines = (sig, *doc, f"    return self._session.send({call})")
    return "\n".join(indent_lines(body_lines, "    ")), imports


def resolve_client(res, ctx, naming, type_mapper, docstrings) -> ClientPageView:
    base_class = naming.class_name(res.domain, "Resource")
    imports: list[Import] = [
        Import(f"{ctx.package_root}.base", base_class),
        Import(".", "_requests"),
    ]
    methods: list[str] = []
    for op in res.operations:
        text, method_imports = _client_method(op, naming, type_mapper, docstrings)
        methods.append(text)
        imports += method_imports
    return ClientPageView(
        doc_block=docstrings.render(res.module_docs.client, ""),
        import_lines=render_imports(tuple(imports)),
        class_header=f"class {naming.class_name(res.resource, 'Client')}({base_class}):",
        class_doc_lines=docstrings.render(res.module_docs.client_class, "    "),
        methods=tuple(methods),
    )
```

```jinja
{# src/refract/emitters/python/templates/client.jinja #}
{% extends "_module.jinja" %}
{% block body %}
{{ page.class_header }}
{% for line in page.class_doc_lines %}
{{ line }}
{% endfor %}
{% for method in page.methods %}
{{ method }}
{% endfor %}
{% endblock %}
```

(С `trim_blocks`+`lstrip_blocks` теги `{% for %}` исчезают, оставляя `class_header` -> строки докстринга класса (уже отступлены на 4) -> каждый метод (готовый лист, отступлен внутрь класса). Пустые строки между методами/после докстринга нормализует `ruff format` - G4.)

```python
# src/refract/emitters/python/surfaces/client.py
from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.api import EmitContext, SurfaceEmitter
from refract.emitters.python.resolve import resolve_client

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir
    from refract.emitters.api import Docstrings, Naming, TypeMapper


class ClientSurface(SurfaceEmitter):
    name = "client"

    def __init__(self, naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings,
                 env: Environment) -> None:
        self._naming, self._type_mapper, self._docstrings, self._env = (
            naming, type_mapper, docstrings, env)

    def applies(self, res: ir.Resource) -> bool:
        return bool(res.operations)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = resolve_client(res, ctx, self._naming, self._type_mapper, self._docstrings)
        return self._env.get_template("client.jinja").render(page=page)
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(python): client surface (D thin sugar)`)

### Task 7.3: `package` surface (`__init__.py`)

Тривиальный surface: пакетный `__init__.py` - это ровно докстринг ресурса. Он не строит методы/импорты, поэтому не нуждается ни в Jinja, ни во внедрённых стратегиях - `emit` возвращает литерал `f'"""{res.documentation}"""\n'`. Путь развязывает `PythonLayout` (`"package"` -> `{domain}/{resource}/__init__.py`, Task 4.5), `Generator` прогоняет вывод через `RuffFormatter` (для этого литерала - no-op). Таргеты - текущие goldens `me/__init__.py`, `priorities/__init__.py` (не меняются под D+F2, разд. F).

**Files:**
- Create: `src/refract/emitters/python/surfaces/package.py`
- Test: `tests/emitters/python/surfaces/test_package.py`

**Interfaces:**
- Consumes: `SurfaceEmitter`/`EmitContext` (разд. C); `ir` (разд. B). Единственный surface без внедрённых стратегий - рендерит литерал, а не структуру.
- Produces: `PackageSurface(SurfaceEmitter)` - эмитит `__init__.py`. `name = "package"`, `applies` - всегда `True`. Таргеты: `me/__init__.py`, `priorities/__init__.py`.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/emitters/python/surfaces/test_package.py
from refract.emitters.api import EmitContext
from refract.emitters.python.surfaces.package import PackageSurface

CTX = EmitContext(package_root="ycli.yandex.tracker")


def test_me_package_is_the_resource_docstring(me_resource):
    out = PackageSurface().emit(me_resource, CTX)
    assert out == '"""Tracker /myself resource (the authenticated user)."""\n'


def test_package_always_applies(me_resource):
    assert PackageSurface().applies(me_resource) is True
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать surface**

```python
# src/refract/emitters/python/surfaces/package.py
from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.api import EmitContext, SurfaceEmitter

if TYPE_CHECKING:
    from refract import ir


class PackageSurface(SurfaceEmitter):
    """The `__init__.py` surface: a package marker whose whole body is the resource docstring."""

    name = "package"

    def applies(self, res: ir.Resource) -> bool:
        return True

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        return f'"""{res.documentation}"""\n'
```

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(python): package __init__ surface`)

### Task 7.4: `models` surface

Порт `refract/emitters/python/models.py` в форму D-surface. Таргеты (разд. F, не меняются под D+F2) - `examples/ycli-tracker/golden/tracker/me/models.py` и `.../priorities/models.py`: набор `APIModel`-подклассов + `RootModel`-листинг, поля вида `name: <тип> = <default | Field(...)>`, докстринги, `config` -> `model_config`. **Два неоднолинейных изменения порта:** (1) старый эмиттер брал `field.type`/`field.default` как уже-пролоуренные Python-строки; в нейтральном IR (разд. B) `field.type: NeutralType`, а `field.default` - только явный spec-дефолт. Поэтому тип рендерится через `type_mapper.render(field.type, optional=field.optional).text`, а дефолт - `field.default` или `type_mapper.null_default(...)`; собранные `RenderedType.imports` (например `Any` -> `from typing import Any`) добавляются в импорты модуля. (2) `Model` теперь дискриминированный union (разд. B): `_model_class` **сопоставляет** его через `match model: case RootListModel() / case ObjectModel() / case _: assert_never(model)` (вместо `model.kind == "root_list"`), а детекция root-list для `RootModel`-импорта идёт через `isinstance(model, RootListModel)`.

**Files:**
- Create: `src/refract/emitters/python/surfaces/models.py`, `src/refract/emitters/python/templates/models.jinja`
- Modify: `src/refract/emitters/python/views.py` (+`ModelsPageView`), `src/refract/emitters/python/resolve.py` (+`resolve_models`, `_model_class`, `_model_field`, `_shared_models_module`)
- Test: `tests/emitters/python/surfaces/test_models.py`

**Interfaces:**
- Consumes: `ir.Model` (union `ObjectModel`/`RootListModel`, разд. B), `ir.Field`, `Naming`/`TypeMapper`/`Docstrings`/`Import`/`RenderedType` (разд. C), `render_imports` (Phase 5), `EmitContext` (разд. C, `package_root`), `assert_never` (для исчерпываемости union).
- Produces: `ModelsSurface(SurfaceEmitter)` - эмитит `models.py` (unformatted; `Generator` форматит `RuffFormatter`-ом в фазе 8). `applies(res) = bool(res.models)`. Таргеты: me/models.py, priorities/models.py (разд. F). `_shared_models_module(ctx)` - база `APIModel`/`require_found` (переиспользуется mcp-surface в 7.6).

- [ ] **Step 1: Написать падающий снапшот-тест**

```python
# tests/emitters/python/surfaces/test_models.py
from refract.emitters.api import EmitContext

CTX = EmitContext(package_root="ycli.yandex.tracker")


def _emit(res):
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.format import RuffFormatter
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.models import ModelsSurface
    from refract.emitters.python.types import PythonTypeMapper

    surface = ModelsSurface(
        PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment()
    )
    return RuffFormatter().format(surface.emit(res, CTX))


def test_models_applies_gates_on_models(me_resource):
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.models import ModelsSurface
    from refract.emitters.python.types import PythonTypeMapper

    surface = ModelsSurface(
        PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment()
    )
    assert surface.applies(me_resource) is True


def test_me_models(me_resource):
    out = _emit(me_resource)
    assert '"""Pydantic model for Tracker /myself (Me)."""' in out
    assert "from __future__ import annotations" in out
    assert "from ycli.yandex.models import APIModel" in out
    assert "class Me(APIModel):" in out
    assert '"""The authenticated Tracker user (``GET /v3/myself``) - a safe auth probe."""' in out
    assert "uid: int | None = None" in out          # NeutralType lowered via TypeMapper
    assert "login: str | None = None" in out
    assert "from pydantic import" not in out         # me needs neither Field nor RootModel


def test_priorities_models(priorities_resource):
    out = _emit(priorities_resource)
    assert "from pydantic import Field, RootModel" in out
    assert "class PriorityList(RootModel[list[Priority]]):" in out      # RootListModel case
    assert "class Priority(APIModel):" in out
    assert "key: str = Field(description=\"Key of the new priority.\")" in out           # required
    assert "name: LocalizedName = Field(description=\"Localized display name of the priority.\")" in out  # ref type
    assert 'ru: str | None = Field(default=None, description="Name in Russian.")' in out  # optional + described
```

- [ ] **Step 2: Прогнать - падает** (surface/resolver/шаблон отсутствуют)

Run: `pytest tests/emitters/python/surfaces/test_models.py -q` -> FAIL (ImportError)

- [ ] **Step 3: Реализовать view + resolver + шаблон + surface**

```python
# appended to src/refract/emitters/python/views.py
class ModelsPageView(_View):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    classes: tuple[str, ...] = ()
```

```python
# appended to src/refract/emitters/python/resolve.py
#   (Import, TypeMapper, ir, render_imports уже импортированы в resolve.py из Phase 5/7)
from typing import assert_never

from refract.emitters.api import Docstrings, EmitContext, Naming
from refract.ir import ObjectModel, RootListModel
from refract.emitters.python.views import ModelsPageView


def _shared_models_module(ctx: EmitContext) -> str:
    """Модуль общей базы (``APIModel``/``require_found``) - уровнем выше домена.

    ``ycli.yandex.tracker`` -> ``ycli.yandex.models`` (де-вартит старый хардкод; см. разд. G2)."""
    return f"{ctx.package_root.rsplit('.', 1)[0]}.models"


def _model_field(field: ir.Field, type_mapper: TypeMapper) -> tuple[str, list[Import]]:
    """Одна строка поля модели: ``name: Type = default`` либо ``Field(...)`` для описанного поля.

    Тип рендерится из NeutralType через TypeMapper (ключевой сдвиг порта); дефолт - явный
    ``field.default`` или, при его отсутствии, ``type_mapper.null_default(...)`` (implied-null).
    Описанное поле -> ``Field(...)``: опциональное несёт ``default=<default>`` перед ``description=``,
    обязательное - только ``description=``. Длинные вызовы оставляем в одну строку - их дожмёт ruff.
    """
    rendered = type_mapper.render(field.type, optional=field.optional)
    imports = list(rendered.imports)
    default = (
        field.default
        if field.default is not None
        else type_mapper.null_default(field.type, optional=field.optional)
    )
    if not field.description:
        return f"    {field.name}: {rendered.text} = {default}", imports
    arguments: list[str] = []
    if default is not None:
        arguments.append(f"default={default}")
    arguments.append(f'description="{field.description}"')
    return f"    {field.name}: {rendered.text} = Field({', '.join(arguments)})", imports


def _model_class(
    model: ir.Model, type_mapper: TypeMapper, docstrings: Docstrings
) -> tuple[str, list[Import]]:
    """Готовый лист одного класса модели - сопоставление по ``Model``-union (разд. B).

    ``RootListModel`` -> ``RootModel[list[Item]]`` только с докстрингом; ``ObjectModel`` -> докстринг,
    пустая строка, затем поля. ``model.item`` - имя модели (str, не NeutralType), рендерится дословно.
    ``assert_never`` держит union исчерпываемым (новый вариант - ошибка типизации, не тихий пропуск)."""
    match model:
        case RootListModel():
            lines = [
                f"class {model.name}(RootModel[list[{model.item}]]):",
                *docstrings.render(model.documentation, "    "),
            ]
            return "\n".join(lines), []
        case ObjectModel():
            lines = [f"class {model.name}(APIModel):"]
            lines += docstrings.render(model.documentation, "    ")
            lines.append("")
            imports: list[Import] = []
            for field in model.fields:
                decl, field_imports = _model_field(field, type_mapper)
                lines.append(decl)
                imports += field_imports
            return "\n".join(lines), imports
        case _:
            assert_never(model)


def resolve_models(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> ModelsPageView:
    """IR -> ModelsPageView: докстринг модуля, импорты (APIModel + pydantic + собранные из типов),
    готовые классы. ``APIModel`` эмитится всегда (как в текущем эмиттере)."""
    imports: list[Import] = [Import(_shared_models_module(ctx), "APIModel")]
    if any(field.description for model in res.models for field in model.fields):
        imports.append(Import("pydantic", "Field"))
    if any(isinstance(model, RootListModel) for model in res.models):
        imports.append(Import("pydantic", "RootModel"))
    classes: list[str] = []
    for model in res.models:
        text, class_imports = _model_class(model, type_mapper, docstrings)
        classes.append(text)
        imports += class_imports
    return ModelsPageView(
        doc_block=docstrings.render(res.module_docs.models, ""),
        header_lines=("from __future__ import annotations",),
        import_lines=render_imports(tuple(imports)),
        classes=tuple(classes),
    )
```

```jinja
{# src/refract/emitters/python/templates/models.jinja #}
{% extends "_module.jinja" %}
{% block body %}
{% for cls in page.classes %}
{{ cls }}
{% endfor %}
{% endblock %}
```

```python
# src/refract/emitters/python/surfaces/models.py
from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.api import EmitContext, SurfaceEmitter
from refract.emitters.python.resolve import resolve_models

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir
    from refract.emitters.api import Docstrings, Naming, TypeMapper


class ModelsSurface(SurfaceEmitter):
    name = "models"

    def __init__(
        self, naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings, env: Environment
    ) -> None:
        self._naming, self._type_mapper, self._docstrings, self._env = (
            naming,
            type_mapper,
            docstrings,
            env,
        )

    def applies(self, res: ir.Resource) -> bool:
        return bool(res.models)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = resolve_models(res, ctx, self._naming, self._type_mapper, self._docstrings)
        return self._env.get_template("models.jinja").render(page=page)
```

- [ ] **Step 4: Прогнать - зелено**

Run: `pytest tests/emitters/python/surfaces/test_models.py -q` -> PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(python): models surface"
```

---

### Task 7.5: `cli` surface

Порт `refract/emitters/python/cli.py`. Таргет (разд. F, не меняется под F2) - `examples/ycli-tracker/golden/tracker/me/cli.py`: `typer.Typer`-группа, callback-якорь `_group()`, и по одной passthrough-команде на операцию, зовущей `app_ctx.<domain>.<resource>.<op>()` через `Serializer.serialize(...)`. Текущий эмиттер (и golden) - **параметр-less** (walking skeleton `me`): команды не рендерят аргументы. Порт остаётся параметр-less, чтобы точно воспроизвести байт-таргет; если операция принесёт path/query-параметры, они пройдут через `param_decl` (TypeMapper, Phase 7) - но текущий golden их не содержит, поэтому мёртвый код не эмитируем. `applies(res) = any(op.cli is not None for op in res.operations)` - у priorities cli-фасета нет, поэтому `priorities/cli.py` не генерируется (в golden его и нет).

**Files:**
- Create: `src/refract/emitters/python/surfaces/cli.py`, `src/refract/emitters/python/templates/cli.jinja`
- Modify: `src/refract/emitters/python/views.py` (+`CliPageView`), `src/refract/emitters/python/resolve.py` (+`resolve_cli`, `_cli_command`, `_GROUP_DOC`)
- Test: `tests/emitters/python/surfaces/test_cli.py`

**Interfaces:**
- Consumes: `ir.Operation`/`ir.CliMeta` (разд. B), `Docstrings`/`Naming`/`TypeMapper` (разд. C), `EmitContext` (разд. C).
- Produces: `CliSurface(SurfaceEmitter)` - эмитит `cli.py` (unformatted). Таргет: me/cli.py (разд. F). Импорты `ycli.cli.context`/`ycli.cli.output` - литеральные (это CLI-инфра ycli-приложения, вне `package_root`, как в текущем эмиттере).

- [ ] **Step 1: Написать падающий снапшот-тест**

```python
# tests/emitters/python/surfaces/test_cli.py
from refract.emitters.api import EmitContext

CTX = EmitContext(package_root="ycli.yandex.tracker")


def _surface():
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.cli import CliSurface
    from refract.emitters.python.types import PythonTypeMapper

    return CliSurface(
        PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment()
    )


def _emit(res):
    from refract.emitters.python.format import RuffFormatter

    return RuffFormatter().format(_surface().emit(res, CTX))


def test_cli_applies_only_when_a_cli_facet_exists(me_resource, priorities_resource):
    assert _surface().applies(me_resource) is True
    assert _surface().applies(priorities_resource) is False   # priorities has no cli facet


def test_me_cli(me_resource):
    out = _emit(me_resource)
    assert '"""`tracker me` commands."""' in out
    assert "from __future__ import annotations" in out
    assert "import typer" in out
    assert "from ycli.cli.context import AppContext" in out
    assert "from ycli.cli.output import Serializer" in out
    assert 'app = typer.Typer(name="me", help="Tracker authenticated user.", no_args_is_help=True)' in out
    assert "def _group() -> None:" in out
    assert '"""Group anchor - forces subcommand dispatch (no eager DI, so --help stays cred-free)."""' in out
    assert "def get(ctx: typer.Context) -> None:" in out
    assert '"""Print the authenticated user (a safe auth probe)."""' in out
    assert "    app_ctx = AppContext.from_typer_context(ctx)" in out
    assert "Serializer.serialize(app_ctx.tracker.me.get(), app_ctx.strategy, app_ctx.console)" in out
```

- [ ] **Step 2: Прогнать - падает**

Run: `pytest tests/emitters/python/surfaces/test_cli.py -q` -> FAIL

- [ ] **Step 3: Реализовать view + resolver + шаблон + surface**

```python
# appended to src/refract/emitters/python/views.py
class CliPageView(_View):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    blocks: tuple[str, ...] = ()
```

```python
# appended to src/refract/emitters/python/resolve.py
from refract.emitters.python.views import CliPageView

_GROUP_DOC = "Group anchor - forces subcommand dispatch (no eager DI, so --help stays cred-free)."


def _cli_command(res: ir.Resource, op: ir.Operation, docstrings: Docstrings) -> str:
    """Готовый лист одной ``@app.command()`` passthrough-команды.

    Команда параметр-less (как текущий эмиттер `me`): резолвит ``AppContext`` и сериализует
    вызов клиента ``app_ctx.<domain>.<resource>.<op>()``. Имя команды - авторское ``cli.name``."""
    meta = op.cli
    assert meta is not None  # отфильтровано в resolve_cli
    call = f"app_ctx.{res.domain}.{res.resource}.{op.name}()"
    lines = [
        "@app.command()",
        f"def {meta.name}(ctx: typer.Context) -> None:",
        *docstrings.render(meta.documentation, "    "),
        "    app_ctx = AppContext.from_typer_context(ctx)",
        f"    Serializer.serialize({call}, app_ctx.strategy, app_ctx.console)",
    ]
    return "\n".join(lines)


def resolve_cli(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> CliPageView:
    """IR -> CliPageView: докстринг модуля, фиксированные импорты, тело = группа+callback + команды."""
    group_block = "\n".join(
        [
            f'app = typer.Typer(name="{res.resource}", '
            f'help="{res.module_docs.cli_group_help}", no_args_is_help=True)',
            "",
            "",
            "@app.callback()",
            "def _group() -> None:",
            f'    """{_GROUP_DOC}"""',
        ]
    )
    blocks = [group_block]
    for op in res.operations:
        if op.cli is not None:
            blocks.append(_cli_command(res, op, docstrings))
    return CliPageView(
        doc_block=docstrings.render(res.module_docs.cli, ""),
        header_lines=("from __future__ import annotations",),
        import_lines=(
            "import typer",
            "from ycli.cli.context import AppContext",
            "from ycli.cli.output import Serializer",
        ),
        blocks=tuple(blocks),
    )
```

```jinja
{# src/refract/emitters/python/templates/cli.jinja #}
{% extends "_module.jinja" %}
{% block body %}
{% for block in page.blocks %}
{{ block }}
{% endfor %}
{% endblock %}
```

```python
# src/refract/emitters/python/surfaces/cli.py
from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.api import EmitContext, SurfaceEmitter
from refract.emitters.python.resolve import resolve_cli

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir
    from refract.emitters.api import Docstrings, Naming, TypeMapper


class CliSurface(SurfaceEmitter):
    name = "cli"

    def __init__(
        self, naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings, env: Environment
    ) -> None:
        self._naming, self._type_mapper, self._docstrings, self._env = (
            naming,
            type_mapper,
            docstrings,
            env,
        )

    def applies(self, res: ir.Resource) -> bool:
        return any(op.cli is not None for op in res.operations)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = resolve_cli(res, ctx, self._naming, self._type_mapper, self._docstrings)
        return self._env.get_template("cli.jinja").render(page=page)
```

- [ ] **Step 4: Прогнать - зелено**

Run: `pytest tests/emitters/python/surfaces/test_cli.py -q` -> PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(python): cli surface"
```

---

### Task 7.6: `mcp` surface

Порт `refract/emitters/python/mcp.py`. Таргеты (разд. F, не меняются под F2) - `me/mcp.py` + `priorities/mcp.py`: `mcp = FastMCP(...)` и по одному `@mcp.tool(...)`-декорированному def на операцию, с честными annotations (`{**<SAFETY>, "title": ...}` + `tags`), `Depends`-DI, `require_found`-гвардом (когда объявлен). Имя tool-функции - через `naming.module_function` (`list` -> `list_`), тело зовёт `client.<resource>.<op>(...)` (F2, не меняется). **Два изменения порта:** (1) сигнатурные path/query-параметры брали `param.type`/`param.default` пролоуренными - теперь через `param_decl` (TypeMapper, Phase 7); собранные импорты (`Any` и т.п.) добавляются в модульные. (2) `safety` - теперь `Safety` StrEnum (разд. B): диспетч tags через `meta.safety is Safety.RO` (identity, не `== "RO"`), а в сгенерированный код имя символа безопасности идёт как `meta.safety.value` (сырое ``"RO"``/``"WRITE"``/``"WRITE_IDEMPOTENT"``). Доменные модули (`.client`/`.dependencies`/`.<resource>.models`) - из `ctx.package_root` (разд. G2); общая база `require_found` - `_shared_models_module` (из 7.4). `applies(res) = any(op.mcp is not None for op in res.operations)`.

**Files:**
- Create: `src/refract/emitters/python/surfaces/mcp.py`, `src/refract/emitters/python/templates/mcp.jinja`
- Modify: `src/refract/emitters/python/views.py` (+`McpPageView`), `src/refract/emitters/python/resolve.py` (+`resolve_mcp`, `_mcp_tool`, `_mcp_signature`, `_mcp_call_args`, `_tags_symbol`)
- Test: `tests/emitters/python/surfaces/test_mcp.py`

**Interfaces:**
- Consumes: `ir.Operation`/`ir.McpMeta`/`ir.RequireFound`/`ir.Param`/`ir.Body`/`ir.Safety` (разд. B), `Naming`/`TypeMapper`/`Docstrings`/`Import` (разд. C), `param_decl` (Phase 7), `render_imports` (Phase 5), `_shared_models_module` (Task 7.4), `EmitContext` (разд. C).
- Produces: `McpSurface(SurfaceEmitter)` - эмитит `mcp.py` (unformatted). Таргеты: me/mcp.py, priorities/mcp.py (разд. F).

- [ ] **Step 1: Написать падающий снапшот-тест**

```python
# tests/emitters/python/surfaces/test_mcp.py
from refract.emitters.api import EmitContext

CTX = EmitContext(package_root="ycli.yandex.tracker")


def _surface():
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.mcp import McpSurface
    from refract.emitters.python.types import PythonTypeMapper

    return McpSurface(
        PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment()
    )


def _emit(res):
    from refract.emitters.python.format import RuffFormatter

    return RuffFormatter().format(_surface().emit(res, CTX))


def test_mcp_applies_on_mcp_facet(me_resource):
    assert _surface().applies(me_resource) is True


def test_me_mcp(me_resource):
    out = _emit(me_resource)
    assert '"""Tracker /myself FastMCP tool (reads-only) - Depends DI."""' in out
    assert "from fastmcp import FastMCP" in out
    assert "from fastmcp.dependencies import Depends" in out
    assert "from ycli.yandex.models import require_found" in out           # shared-base guard import
    assert "from ycli.yandex.tracker.client import TrackerClient" in out    # package_root-derived
    assert "from ycli.yandex.tracker.dependencies import RO, TAGS, tracker_client" in out
    assert "from ycli.yandex.tracker.me.models import Me" in out
    assert 'mcp = FastMCP("tracker-me")' in out
    assert '@mcp.tool(name="me_get", annotations={**RO, "title": "Get current Tracker user"}, tags=TAGS)' in out
    assert "def get(client: TrackerClient = Depends(tracker_client)) -> Me:" in out
    assert "result = client.me.get()" in out
    assert "require_found(" in out
    assert "sentinel=lambda r: r.login is None," in out


def test_priorities_mcp(priorities_resource):
    out = _emit(priorities_resource)
    assert 'mcp = FastMCP("tracker-priorities")' in out
    assert "def list_(client: TrackerClient = Depends(tracker_client)) -> PriorityList:" in out  # shadow guard
    assert "return client.priorities.list()" in out
    assert 'annotations={**WRITE, "title": "Create Tracker priority"}' in out
    assert "tags=WRITE_TAGS," in out
    assert 'annotations={**WRITE_IDEMPOTENT, "title": "Edit Tracker priority"}' in out
    assert "def edit(" in out
    assert "priority_id: str," in out
    assert "body: PriorityUpdate," in out
    assert "version: int | None = None," in out                            # query param via TypeMapper
    assert "client: TrackerClient = Depends(tracker_client)," in out
    assert "return client.priorities.edit(priority_id, body, version=version)" in out
    assert "require_found" not in out                                       # priorities declares no guard
```

- [ ] **Step 2: Прогнать - падает**

Run: `pytest tests/emitters/python/surfaces/test_mcp.py -q` -> FAIL

- [ ] **Step 3: Реализовать view + resolver + шаблон + surface**

```python
# appended to src/refract/emitters/python/views.py
class McpPageView(_View):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    server_line: str = ""
    tools: tuple[str, ...] = ()
```

```python
# appended to src/refract/emitters/python/resolve.py
from refract.ir import Safety
from refract.emitters.python.views import McpPageView


def _tags_symbol(safety: Safety) -> str:
    """Константа тегов для класса безопасности (reads: ``TAGS``; writes: ``WRITE_TAGS``)."""
    return "TAGS" if safety is Safety.RO else "WRITE_TAGS"


def _mcp_signature(
    res: ir.Resource, op: ir.Operation, naming: Naming, type_mapper: TypeMapper
) -> tuple[list[str], list[Import]]:
    """Параметры tool-функции по порядку: path, типизированный ``body``, query, затем DI-клиент.

    Path/query проходят через ``param_decl`` (TypeMapper) - раньше брали пролоуренный ``param.type``.
    Параметры плоские (не keyword-only): fastmcp читает их как обычные аргументы."""
    parameters: list[str] = []
    imports: list[Import] = []
    for param in op.params:
        if param.loc == "path":
            decl, param_imports = param_decl(param, type_mapper)
            parameters.append(decl)
            imports += param_imports
    if op.body is not None:
        parameters.append(f"body: {op.body.model}")
    for param in op.params:
        if param.loc == "query":
            decl, param_imports = param_decl(param, type_mapper)
            parameters.append(decl)
            imports += param_imports
    parameters.append(
        f"client: {naming.class_name(res.domain, 'Client')} = Depends({res.domain}_client)"
    )
    return parameters, imports


def _mcp_call_args(op: ir.Operation) -> str:
    """Аргументы, форвардящиеся в вызов клиента: path, ``body``, затем keyword-query."""
    arguments = [param.name for param in op.params if param.loc == "path"]
    if op.body is not None:
        arguments.append("body")
    arguments += [f"{param.name}={param.name}" for param in op.params if param.loc == "query"]
    return ", ".join(arguments)


def _mcp_tool(
    res: ir.Resource,
    op: ir.Operation,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> tuple[str, list[Import]]:
    """Готовый лист одной ``@mcp.tool``-функции, форвардящей в клиент (с гвардом при require_found).

    Имя def - ``naming.module_function`` (``list`` -> ``list_``). Символ безопасности в код идёт как
    ``meta.safety.value`` (сырое ``"RO"``/``"WRITE"``/...). Гвард форматируется как в текущем
    эмиттере (одна строка ``require_found(...)`` - её дожмёт ruff по golden)."""
    meta = op.mcp
    assert meta is not None  # отфильтровано в resolve_mcp
    annotations = f'{{**{meta.safety.value}, "title": "{meta.title}"}}'
    decorator = (
        f'@mcp.tool(name="{meta.name}", annotations={annotations}, '
        f"tags={_tags_symbol(meta.safety)})"
    )
    parameters, imports = _mcp_signature(res, op, naming, type_mapper)
    signature = (
        f"def {naming.module_function(op.name)}({', '.join(parameters)}) -> {op.response_model}:"
    )
    call = f"client.{res.resource}.{op.name}({_mcp_call_args(op)})"
    guard = meta.require_found
    if guard is None:
        body = [f"    return {call}"]
    else:
        body = [
            f"    result = {call}",
            "    return require_found("
            f"result, sentinel=lambda r: {guard.sentinel}, "
            f'message="{guard.message}")',
        ]
    lines = [decorator, signature, *docstrings.render(meta.documentation, "    "), *body]
    return "\n".join(lines), imports


def resolve_mcp(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> McpPageView:
    """IR -> McpPageView: докстринг модуля (single-line raw в текущем эмиттере - теперь через
    Docstrings, идентичный вывод), импорты (fastmcp + package_root-доменные + собранные из типов),
    ``mcp = FastMCP(...)`` + готовые tools. Итерируем только операции с mcp-фасетом.
    ``meta.safety.value`` - сырое имя символа безопасности (StrEnum -> str) для ``dependencies``-импорта."""
    dependencies_module = f"{ctx.package_root}.dependencies"
    models_module = f"{ctx.package_root}.{res.resource}.models"
    imports: list[Import] = [
        Import("fastmcp", "FastMCP"),
        Import("fastmcp.dependencies", "Depends"),
        Import(f"{ctx.package_root}.client", naming.class_name(res.domain, "Client")),
        Import(dependencies_module, f"{res.domain}_client"),
    ]
    tools: list[str] = []
    for op in res.operations:
        meta = op.mcp
        if meta is None:
            continue
        imports.append(Import(dependencies_module, meta.safety.value))
        imports.append(Import(dependencies_module, _tags_symbol(meta.safety)))
        if op.response_model:
            imports.append(Import(models_module, op.response_model))
        if op.body is not None:
            imports.append(Import(models_module, op.body.model))
        if meta.require_found is not None:
            imports.append(Import(_shared_models_module(ctx), "require_found"))
        text, tool_imports = _mcp_tool(res, op, naming, type_mapper, docstrings)
        tools.append(text)
        imports += tool_imports
    return McpPageView(
        doc_block=docstrings.render(res.module_docs.mcp, ""),
        import_lines=render_imports(tuple(imports)),
        server_line=f'mcp = FastMCP("{res.module_docs.mcp_server}")',
        tools=tuple(tools),
    )
```

```jinja
{# src/refract/emitters/python/templates/mcp.jinja #}
{% extends "_module.jinja" %}
{% block body %}
{{ page.server_line }}
{% for tool in page.tools %}
{{ tool }}
{% endfor %}
{% endblock %}
```

```python
# src/refract/emitters/python/surfaces/mcp.py
from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.api import EmitContext, SurfaceEmitter
from refract.emitters.python.resolve import resolve_mcp

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir
    from refract.emitters.api import Docstrings, Naming, TypeMapper


class McpSurface(SurfaceEmitter):
    name = "mcp"

    def __init__(
        self, naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings, env: Environment
    ) -> None:
        self._naming, self._type_mapper, self._docstrings, self._env = (
            naming,
            type_mapper,
            docstrings,
            env,
        )

    def applies(self, res: ir.Resource) -> bool:
        return any(op.mcp is not None for op in res.operations)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = resolve_mcp(res, ctx, self._naming, self._type_mapper, self._docstrings)
        return self._env.get_template("mcp.jinja").render(page=page)
```

- [ ] **Step 4: Прогнать - зелено**

Run: `pytest tests/emitters/python/surfaces/test_mcp.py -q` -> PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(python): mcp surface"
```

---

### Task 7.7: `tests` surface

Порт `refract/emitters/python/tests.py` (самый большой). Таргет (разд. F, не меняется под F2) - `examples/ycli-tracker/golden/tests/tracker/test_me.py`: авто-сюита, управляемая авторскими `TestCase`-данными спеки (`kind` in client/cli/mcp/mcp_guard), `@responses.activate`, застабленный HTTP. **Здесь лоуринг типов НЕ нужен** - все значения `TestCase` (fixtures, asserts, call, статусы) авторские и переносятся дословно; конструктор surface принимает единый набор стратегий (`naming`/`type_mapper`/`docstrings`/`env`) ради единообразия, но `type_mapper` не используется. **Три изменения порта под разд. B:** (1) `TestCase.kind` - теперь `TestKind` StrEnum: сравнения идут через identity (`case.kind is TestKind.CLIENT`, `TestKind.MCP_GUARD in kinds`), не строковым `== "client"`. (2) `res.base_url` больше НЕТ (переехал в `ClientConfig.server`, разд. B/разд. I) - `_URL` строится из `ctx.config.server.base_url` (`ctx` уже в сигнатуре `resolve_tests`). (3) `response_json` - теперь `JsonValue`, но `repr()`/`!r` над ним работают как прежде (никаких правок в стабах/константах). Импорты и модульные константы гейтятся на набор surface'ов (`kinds`), которые реально задействуют кейсы. `naming.class_name(res.domain, "Client")` заменяет старый `domain_client_class`; доменные модули - из `ctx.package_root` (разд. G2), а `ycli.cli.app`/`ycli.mcp` - литеральные (ycli-app-инфра). `applies(res) = any(op.tests for op in res.operations)` - только у `me` есть tests, поэтому `test_priorities.py` не генерируется.

**Files:**
- Create: `src/refract/emitters/python/surfaces/tests.py`, `src/refract/emitters/python/templates/tests.jinja`
- Modify: `src/refract/emitters/python/views.py` (+`TestsPageView`), `src/refract/emitters/python/resolve.py` (+`resolve_tests` и per-kind лист-рендереры)
- Test: `tests/emitters/python/surfaces/test_tests.py`

**Interfaces:**
- Consumes: `ir.Operation`/`ir.TestCase`/`ir.TestKind` (разд. B), `Docstrings` (разд. C), `EmitContext` (разд. C, `config.server.base_url`).
- Produces: `TestsSurface(SurfaceEmitter)` - эмитит `test_<resource>.py` (unformatted). Таргет: tests/tracker/test_me.py (разд. F).

- [ ] **Step 1: Написать падающий снапшот-тест**

```python
# tests/emitters/python/surfaces/test_tests.py
from refract import ir
from refract.emitters.api import EmitContext

# _URL is built from ctx.config.server.base_url now (base_url left Resource for ClientConfig, разд. I).
CTX = EmitContext(
    package_root="ycli.yandex.tracker",
    config=ir.ClientConfig(
        name="tracker",
        server=ir.Server(base_url="https://api.tracker.yandex.net/v3"),
    ),
)


def _surface():
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.tests import TestsSurface
    from refract.emitters.python.types import PythonTypeMapper

    return TestsSurface(
        PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment()
    )


def _emit(res):
    from refract.emitters.python.format import RuffFormatter

    return RuffFormatter().format(_surface().emit(res, CTX))


def test_tests_applies_only_when_cases_exist(me_resource, priorities_resource):
    assert _surface().applies(me_resource) is True
    assert _surface().applies(priorities_resource) is False   # priorities carries no test cases


def test_me_tests(me_resource):
    out = _emit(me_resource)
    assert '"""Tracker /myself resource - client + CLI + MCP, HTTP stubbed."""' in out
    assert "from __future__ import annotations" in out
    assert "import asyncio" in out
    assert "import json" in out
    assert "import pytest" in out
    assert "import responses" in out
    assert "from fastmcp import Client" in out
    assert "from fastmcp.exceptions import ToolError" in out
    assert "from typer.testing import CliRunner" in out
    assert "import ycli.cli.app as cli" in out
    assert "from ycli.mcp import mcp as root_mcp" in out
    assert "from ycli.yandex.tracker.client import TrackerClient" in out
    assert "from ycli.yandex.tracker.me import mcp as me_mcp_module" in out
    assert "from ycli.yandex.tracker.me.models import Me" in out
    assert '_URL = "https://api.tracker.yandex.net/v3/myself"' in out
    assert '_PAYLOAD = {"uid": 42, "login": "alice", "display": "Alice A.", "email": "alice@example.com"}' in out
    assert "_runner = CliRunner()" in out
    assert "@responses.activate" in out
    assert "def test_me_client_get(creds):" in out
    assert "responses.add(responses.GET, _URL, json=_PAYLOAD, status=200)" in out
    assert "me = TrackerClient(oauth_token=\"t\", organization_id=\"o\").me.get()" in out
    assert "assert isinstance(me, Me)" in out
    assert 'res = _runner.invoke(cli.app, ["--format", "json", "tracker", "me", "get"])' in out
    assert 'return await client.call_tool("tracker_me_get", {})' in out
    assert "async def test_me_mcp_auth_guard(creds):" in out
    assert "responses.add(responses.GET, _URL, json={}, status=401)" in out
    assert "async with Client(me_mcp_module.mcp) as client:" in out
    assert "with pytest.raises(ToolError):" in out
    assert '            await client.call_tool("me_get", {})' in out
    assert '"""200 with empty body hits the login-is-None guard (e.g. bad permissions -> blank object)."""' in out
```

- [ ] **Step 2: Прогнать - падает**

Run: `pytest tests/emitters/python/surfaces/test_tests.py -q` -> FAIL

- [ ] **Step 3: Реализовать view + resolver + шаблон + surface**

```python
# appended to src/refract/emitters/python/views.py
class TestsPageView(_View):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    constants: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
```

```python
# appended to src/refract/emitters/python/resolve.py
from refract.ir import TestKind
from refract.emitters.python.views import TestsPageView

# Докстринг require_found empty-response-гварда (структурный - только 200-empty случай,
# завязан на sentinel ``r.login is None``, объявленный read-tool'ом).
_EMPTY_GUARD_DOC = (
    "200 with empty body hits the login-is-None guard (e.g. bad permissions -> blank object)."
)


def _tests_module_doc(res: ir.Resource, op: ir.Operation, kinds: set[TestKind]) -> str:
    """Текст докстринга тест-модуля: ``<Domain> /<path> resource - <surfaces>, HTTP stubbed.``"""
    labels = []
    if TestKind.CLIENT in kinds:
        labels.append("client")
    if TestKind.CLI in kinds:
        labels.append("CLI")
    if kinds & {TestKind.MCP, TestKind.MCP_GUARD}:
        labels.append("MCP")
    surfaces = " + ".join(labels)
    return f"{res.domain_title} /{op.path} resource - {surfaces}, HTTP stubbed."


def _tests_imports(
    res: ir.Resource, op: ir.Operation, ctx: EmitContext, kinds: set[TestKind], client_class: str
) -> tuple[str, ...]:
    has_client = TestKind.CLIENT in kinds
    has_cli = TestKind.CLI in kinds
    has_mcp = TestKind.MCP in kinds
    has_mcp_guard = TestKind.MCP_GUARD in kinds

    stdlib: list[str] = []
    if has_mcp:
        stdlib.append("import asyncio")
    if has_cli:
        stdlib.append("import json")

    third_party: list[str] = []
    if has_mcp_guard:
        third_party.append("import pytest")
    third_party.append("import responses")
    if has_mcp or has_mcp_guard:
        third_party.append("from fastmcp import Client")
    if has_mcp_guard:
        third_party.append("from fastmcp.exceptions import ToolError")
    if has_cli:
        third_party.append("from typer.testing import CliRunner")

    first_party: list[str] = []
    if has_cli:
        first_party.append("import ycli.cli.app as cli")
    if has_mcp:
        first_party.append("from ycli.mcp import mcp as root_mcp")
    if has_client:
        first_party.append(f"from {ctx.package_root}.client import {client_class}")
    if has_mcp_guard:
        first_party.append(
            f"from {ctx.package_root}.{res.resource} import mcp as {res.resource}_mcp_module"
        )
    if has_client:
        first_party.append(f"from {ctx.package_root}.{res.resource}.models import {op.response_model}")
    return (*stdlib, *third_party, *first_party)


def _tests_constants(
    res: ir.Resource, op: ir.Operation, ctx: EmitContext, kinds: set[TestKind]
) -> tuple[str, ...]:
    """Модульные константы: ``_URL`` (всегда), ``_PAYLOAD`` (client-кейс), ``_runner`` (cli-кейс).

    ``_URL`` строится из ``ctx.config.server.base_url`` (``base_url`` ушёл с ``Resource``, разд. B/разд. I).
    ``response_json`` - авторские данные; ``!r`` даёт single-quote-repr, который ruff нормализует
    в double-quote (как в golden). Лоуринг типов не нужен."""
    lines = [f'_URL = "{ctx.config.server.base_url}/{op.path}"']
    if TestKind.CLIENT in kinds:
        client_case = next(case for case in op.tests if case.kind is TestKind.CLIENT)
        lines.append(f"_PAYLOAD = {client_case.response_json!r}")
    if TestKind.CLI in kinds:
        lines.append("_runner = CliRunner()")
    return tuple(lines)


def _stub(case: ir.TestCase) -> str:
    """Строка ``responses.add(...)`` (``_PAYLOAD`` для reads, inline ``{}`` для guard-кейсов)."""
    json_arg = repr(case.response_json) if case.kind is TestKind.MCP_GUARD else "_PAYLOAD"
    return (
        f"    responses.add(responses.{case.http_method}, _URL, "
        f"json={json_arg}, status={case.status})"
    )


def _asserts(case: ir.TestCase) -> list[str]:
    """По строке ``assert <expr>`` на каждый авторский assert."""
    return [f"    assert {expr}" for expr in case.asserts]


def _client_test(res: ir.Resource, case: ir.TestCase) -> str:
    """Client-кейс - связать chained-вызов клиента, затем авторские asserts."""
    lines = [
        "@responses.activate",
        f"def test_{case.name}(creds):",
        _stub(case),
        f"    {res.resource} = {case.call}",
        *_asserts(case),
    ]
    return "\n".join(lines)


def _cli_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """CLI-кейс - ``CliRunner`` json-invoke команды ``<domain> <resource> <command>``."""
    assert op.cli is not None
    argv = ", ".join(
        f'"{token}"' for token in ("--format", "json", res.domain, res.resource, op.cli.name)
    )
    lines = [
        "@responses.activate",
        f"def test_{case.name}(creds):",
        _stub(case),
        f"    res = _runner.invoke(cli.app, [{argv}])",
        *_asserts(case),
    ]
    return "\n".join(lines)


def _mcp_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """MCP-кейс - вызвать root-composed tool через ``root_mcp`` под ``asyncio.run``."""
    assert op.mcp is not None
    root_tool = f"{res.domain}_{op.mcp.name}"
    lines = [
        "@responses.activate",
        f"def test_{case.name}(creds):",
        _stub(case),
        "",
        "    async def go():",
        "        async with Client(root_mcp) as client:",
        f'            return await client.call_tool("{root_tool}", {{}})',
        "",
        "    result = asyncio.run(go())",
        *_asserts(case),
    ]
    return "\n".join(lines)


def _guard_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """MCP guard-кейс - resource-local tool обязан бросить ``ToolError`` (структурно, без asserts)."""
    assert op.mcp is not None
    lines = ["@responses.activate", f"async def test_{case.name}(creds):"]
    if case.status == 200:
        lines.append(f'    """{_EMPTY_GUARD_DOC}"""')
    lines += [
        _stub(case),
        f"    async with Client({res.resource}_mcp_module.mcp) as client:",
        "        with pytest.raises(ToolError):",
        f'            await client.call_tool("{op.mcp.name}", {{}})',
    ]
    return "\n".join(lines)


def _test_block(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """Диспетч одного авторского ``TestCase`` в per-kind рендерер (identity по ``TestKind``)."""
    if case.kind is TestKind.CLIENT:
        return _client_test(res, case)
    if case.kind is TestKind.CLI:
        return _cli_test(res, op, case)
    if case.kind is TestKind.MCP:
        return _mcp_test(res, op, case)
    return _guard_test(res, op, case)  # TestKind.MCP_GUARD


def resolve_tests(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> TestsPageView:
    """IR -> TestsPageView. Берём единственную операцию с tests (walking-skeleton `me`), гейтим
    импорты/константы на её ``kinds`` (набор ``TestKind``), рендерим по листу на кейс. ``type_mapper``
    здесь не нужен - все значения TestCase авторские."""
    op = next(operation for operation in res.operations if operation.tests)
    kinds = {case.kind for case in op.tests}
    client_class = naming.class_name(res.domain, "Client")
    return TestsPageView(
        doc_block=docstrings.render(_tests_module_doc(res, op, kinds), ""),
        header_lines=("from __future__ import annotations",),
        import_lines=_tests_imports(res, op, ctx, kinds, client_class),
        constants=_tests_constants(res, op, ctx, kinds),
        tests=tuple(_test_block(res, op, case) for case in op.tests),
    )
```

```jinja
{# src/refract/emitters/python/templates/tests.jinja #}
{% extends "_module.jinja" %}
{% block body %}
{% for line in page.constants %}
{{ line }}
{% endfor %}
{% for test in page.tests %}
{{ test }}
{% endfor %}
{% endblock %}
```

```python
# src/refract/emitters/python/surfaces/tests.py
from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.api import EmitContext, SurfaceEmitter
from refract.emitters.python.resolve import resolve_tests

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir
    from refract.emitters.api import Docstrings, Naming, TypeMapper


class TestsSurface(SurfaceEmitter):
    name = "tests"

    def __init__(
        self, naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings, env: Environment
    ) -> None:
        self._naming, self._type_mapper, self._docstrings, self._env = (
            naming,
            type_mapper,
            docstrings,
            env,
        )

    def applies(self, res: ir.Resource) -> bool:
        return any(op.tests for op in res.operations)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = resolve_tests(res, ctx, self._naming, self._type_mapper, self._docstrings)
        return self._env.get_template("tests.jinja").render(page=page)
```

- [ ] **Step 4: Прогнать - зелено**

Run: `pytest tests/emitters/python/surfaces/test_tests.py -q` -> PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(python): tests surface"
```

---

### Task 7.8: `root_client` surface (per-API glue, `DomainEmitter`)

Единственный per-домен surface (не per-resource): генерируемый glue-корень `tracker/client.py` (разд. F, НОВЫЙ таргет) - агрегатор ресурсов, владелец транспорта и auth. Это `DomainEmitter` (разд. C): бежит ОДИН раз над всеми ресурсами домена (`emit(resources, ctx)`), без `applies` (диспетч неявный - `Generator` зовёт `backend.domain_surfaces` один раз, Phase 8). Резолвер читает `ctx.config` (разд. I): `server.base_url` -> строка `Session(...)`; схема auth, названная `security` ресурсов, выбирается из `ctx.config.auth` и сопоставляется по `AuthScheme`-union (разд. H) `match`-ем - `case MultiHeaderAuth()` рендерит словарь заголовков из `(header, template)`-пар, `case HeaderAuth()` - один заголовок, `case _: assert_never(scheme)`; конструктор-параметры + `from_env` строятся из `scheme.inputs` (`AuthInput.name`/`.env`); ресурсы агрегируются (`self.<resource> = <ResourceClient>(session)`) по переданному кортежу `resources` через `Naming`. Рендер значения заголовка: чистый плейсхолдер `"{name}"` -> голая переменная `name`; шаблон с текстом `"OAuth {name}"` -> f-string `f"OAuth {name}"` (см. разд. F). refract - публичный тул: glue произвольного API нельзя писать руками, поэтому root-client генерится из `ClientConfig` (решение G5/G10). Таргет - разд. F `tracker/client.py`.

> **Про импорты root-client** (разд. F): относительные (`.me.client`, `.runtime.auth`, `.runtime.session`) - файл лежит В корне пакета, всё под ним доступно относительно, `package_root` для собственных импортов не нужен. `ruff check --select I --fix` (Task 5.1) сортирует `import os` / `import httpx` / relative по isort-группам; `from __future__ import annotations` (в `header_lines`) остаётся первым.
>
> **Про докстринги** (расхождение разд. F, зафиксировать на review): `ClientConfig` (разд. I) несёт только `name` (= "tracker") и не имеет vendor-title поля, поэтому детерминированный синтез из `domain_title` даёт `"Tracker client - ..."`, а не показанное в разд. F `"Yandex Tracker client - ..."`. Структурный байт-таргет (auth/session/aggregation/from_env/imports) L1-ассерты фиксируют точно; точную vendor-prose разд. F закрывает опциональный `display_title` на `ClientConfig` (отложено - не влияет на скелет).
>
> **Про `MultiHeaderAuth`-омонимы:** резолвер импортирует `MultiHeaderAuth`/`HeaderAuth` из `refract.ir` (дескрипторы `AuthScheme`, разд. H) для `match`; сгенерированный код тянет одноимённый httpx-механизм из `.runtime.auth` (разд. E) - это разные классы, в резолвере встречается только строковое имя механизма.

**Files:**
- Create: `src/refract/emitters/python/surfaces/root_client.py`, `src/refract/emitters/python/templates/root_client.jinja`
- Modify: `src/refract/emitters/python/views.py` (+`RootClientPageView`), `src/refract/emitters/python/resolve.py` (+`resolve_root_client`, `_auth_value`, `_multi_header_call`, `_header_call`, `_select_scheme`)
- Test: `tests/emitters/python/surfaces/test_root_client.py`

**Interfaces:**
- Consumes: `ir.Resource`/`ir.ClientConfig`/`ir.Server`/`ir.AuthScheme` (`HeaderAuth`/`MultiHeaderAuth`/`AuthInput`, разд. H/разд. I), `Naming`/`Docstrings`/`Import`/`DomainEmitter`/`EmitContext` (разд. C), `signature_params`/`indent_lines`/`render_imports` (Task 5.2), `assert_never` (исчерпываемость union). `type_mapper` не нужен (все креды - `str`), но surface хранит его ради единого конструктора (как tests-surface).
- Produces: `RootClientSurface(DomainEmitter)` - эмитит `tracker/client.py` (разд. F). `name = "root_client"`; `emit(resources, ctx)` бежит один раз над всеми ресурсами. Таргет: `tracker/client.py` (разд. F).

- [ ] **Step 1: Написать падающий снапшот-тест**

```python
# tests/emitters/python/surfaces/test_root_client.py
from refract import ir
from refract.emitters.api import EmitContext

# Root-client glue is resolved from ClientConfig (разд. I/разд. J): server + the auth scheme a resource's
# `security` names. The scheme's AuthInput.name values drive the ctor params + from_env, and the
# (header, template) pairs render the MultiHeaderAuth mechanism dict - authored here to hit разд. F.
CTX = EmitContext(
    package_root="ycli.yandex.tracker",
    config=ir.ClientConfig(
        name="tracker",
        server=ir.Server(base_url="https://api.tracker.yandex.net/v3"),
        auth=(
            (
                "oauth_token",
                ir.MultiHeaderAuth(
                    headers=(
                        ("Authorization", "OAuth {oauth_token}"),
                        ("X-Org-Id", "{organization_id}"),
                    ),
                    inputs=(
                        ir.AuthInput(name="oauth_token", env="YANDEX_ID_OAUTH_TOKEN"),
                        ir.AuthInput(name="organization_id", env="YANDEX_ID_ORGANIZATION_ID"),
                    ),
                ),
            ),
        ),
    ),
)


def _emit(resources):
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.format import RuffFormatter
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.root_client import RootClientSurface
    from refract.emitters.python.types import PythonTypeMapper

    surface = RootClientSurface(
        PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment()
    )
    return RuffFormatter().format(surface.emit(resources, CTX))


def test_tracker_root_client(me_resource, priorities_resource):
    out = _emit((me_resource, priorities_resource))
    # module + class framing (title synthesised from domain_title - see docstring note above)
    assert (
        '"""Tracker client - the composition root '
        '(aggregates resources, owns transport + auth)."""' in out
    )
    assert "from __future__ import annotations" in out
    assert "class TrackerClient:" in out
    assert '"""Root client for the Tracker API."""' in out
    # imports (ruff isort-sorted): stdlib os, third-party httpx, local relative
    assert "import os" in out
    assert "import httpx" in out
    assert "from .me.client import MeClient" in out
    assert "from .priorities.client import PrioritiesClient" in out
    assert "from .runtime.auth import MultiHeaderAuth" in out
    assert "from .runtime.session import Session" in out
    # constructor: keyword-only credential params from AuthScheme.inputs (AuthInput.name)
    assert "def __init__(self, *, oauth_token: str, organization_id: str) -> None:" in out
    # auth mechanism from (header, template) pairs - pure `{placeholder}` -> bare var, decorated
    # template -> f-string (ruff hug-wraps the >100-col MultiHeaderAuth(...) call, so assert frags)
    assert "auth = MultiHeaderAuth(" in out
    assert '"Authorization": f"OAuth {oauth_token}"' in out
    assert '"X-Org-Id": organization_id' in out
    # session from ctx.config.server.base_url
    assert (
        'session = Session("https://api.tracker.yandex.net/v3", '
        "client=httpx.Client(auth=auth))" in out
    )
    # resource aggregation over the passed resources tuple (order preserved)
    assert "self.me = MeClient(session)" in out
    assert "self.priorities = PrioritiesClient(session)" in out
    # from_env: single sanctioned env-read point, one kwarg per AuthInput.env
    assert "def from_env(cls) -> TrackerClient:" in out
    assert (
        '"""The single sanctioned env-read point (composition root); '
        'components never read env."""' in out
    )
    assert 'oauth_token=os.environ["YANDEX_ID_OAUTH_TOKEN"]' in out
    assert 'organization_id=os.environ["YANDEX_ID_ORGANIZATION_ID"]' in out
```

- [ ] **Step 2: Прогнать - падает**

Run: `pytest tests/emitters/python/surfaces/test_root_client.py -q` -> FAIL (ImportError: `RootClientSurface`)

- [ ] **Step 3: Реализовать view + resolver + шаблон + surface**

```python
# appended to src/refract/emitters/python/views.py
class RootClientPageView(_View):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    class_header: str
    class_doc_lines: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
```

```python
# appended to src/refract/emitters/python/resolve.py
from refract.ir import HeaderAuth, MultiHeaderAuth   # AuthScheme variants (разд. H) - match patterns
from refract.emitters.python.views import RootClientPageView

# `Import`, `ir`, `render_imports`, `signature_params`, `indent_lines` (Task 5.2/7) and
# `assert_never`, `EmitContext`, `Naming`, `Docstrings` (Task 7.4) are already in this module.
# NB: `MultiHeaderAuth`/`HeaderAuth` here are the ir.auth DESCRIPTORS; the generated code imports
# the same-named httpx mechanisms from `.runtime.auth` - the resolver only emits the mechanism name.


def _auth_value(template: str, inputs: tuple[ir.AuthInput, ...]) -> str:
    """One header value: a bare input var for a pure ``"{name}"`` placeholder, else an f-string.

    ``"{organization_id}"`` -> ``organization_id``; ``"OAuth {oauth_token}"`` -> ``f"OAuth {oauth_token}"``.
    """
    for auth_input in inputs:
        if template == f"{{{auth_input.name}}}":
            return auth_input.name
    return f'f"{template}"'


def _multi_header_call(scheme: MultiHeaderAuth) -> str:
    """``MultiHeaderAuth({...})`` mechanism call from the scheme's ``(header, template)`` pairs."""
    entries = ", ".join(
        f'"{header}": {_auth_value(template, scheme.inputs)}' for header, template in scheme.headers
    )
    return f"MultiHeaderAuth({{{entries}}})"


def _header_call(scheme: HeaderAuth) -> str:
    """``HeaderAuth("<header>", <value>)`` mechanism call (single templated header)."""
    return f'HeaderAuth("{scheme.header}", {_auth_value(scheme.template, scheme.inputs)})'


def _select_scheme(config: ir.ClientConfig, security: str) -> ir.AuthScheme:
    """Index ``ClientConfig.auth`` (tuple-of-pairs) by the scheme name a resource's ``security`` names."""
    for name, scheme in config.auth:
        if name == security:
            return scheme
    raise KeyError(security)


def resolve_root_client(
    resources: tuple[ir.Resource, ...],
    ctx: EmitContext,
    naming: Naming,
    docstrings: Docstrings,
) -> RootClientPageView:
    """IR + ClientConfig -> RootClientPageView: the composition root (разд. F). Runs once over ALL
    resources (per-API invariant: shared ``domain`` + ``security``, so read from ``resources[0]``)."""
    domain = resources[0].domain
    client_class = naming.class_name(domain, "Client")
    scheme = _select_scheme(ctx.config, resources[0].security)
    match scheme:
        case MultiHeaderAuth():
            mechanism, auth_expr = "MultiHeaderAuth", _multi_header_call(scheme)
        case HeaderAuth():
            mechanism, auth_expr = "HeaderAuth", _header_call(scheme)
        case _:
            assert_never(scheme)

    ctor_params = signature_params(
        ("self",), tuple(f"{auth_input.name}: str" for auth_input in scheme.inputs)
    )
    init_lines = (
        f"def __init__({', '.join(ctor_params)}) -> None:",
        f"    auth = {auth_expr}",
        f'    session = Session("{ctx.config.server.base_url}", client=httpx.Client(auth=auth))',
        *(
            f"    self.{res.resource} = {naming.class_name(res.resource, 'Client')}(session)"
            for res in resources
        ),
    )
    from_env_lines = (
        "@classmethod",
        f"def from_env(cls) -> {client_class}:",
        *docstrings.render(
            "The single sanctioned env-read point (composition root); components never read env.",
            "    ",
        ),
        "    return cls(",
        *(
            f'        {auth_input.name}=os.environ["{auth_input.env}"],'
            for auth_input in scheme.inputs
        ),
        "    )",
    )
    imports = (
        "import os",
        "import httpx",
        *render_imports(
            (
                Import(".runtime.session", "Session"),
                Import(".runtime.auth", mechanism),
                *(
                    Import(f".{res.resource}.client", naming.class_name(res.resource, "Client"))
                    for res in resources
                ),
            )
        ),
    )
    title = resources[0].domain_title
    return RootClientPageView(
        doc_block=docstrings.render(
            f"{title} client - the composition root (aggregates resources, owns transport + auth).",
            "",
        ),
        header_lines=("from __future__ import annotations",),
        import_lines=imports,
        class_header=f"class {client_class}:",
        class_doc_lines=docstrings.render(f"Root client for the {title} API.", "    "),
        methods=(
            "\n".join(indent_lines(init_lines, "    ")),
            "\n".join(indent_lines(from_env_lines, "    ")),
        ),
    )
```

```jinja
{# src/refract/emitters/python/templates/root_client.jinja #}
{% extends "_module.jinja" %}
{% block body %}
{{ page.class_header }}
{% for line in page.class_doc_lines %}
{{ line }}
{% endfor %}
{% for method in page.methods %}
{{ method }}
{% endfor %}
{% endblock %}
```

(Как в `client.jinja`: `class_header` -> строки докстринга класса (уже отступлены на 4) -> каждый метод (готовый лист, отступлен внутрь класса, `__init__` затем `from_env`). Пустые строки нормализует `ruff format` - G4.)

```python
# src/refract/emitters/python/surfaces/root_client.py
from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.api import DomainEmitter, EmitContext
from refract.emitters.python.resolve import resolve_root_client

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir
    from refract.emitters.api import Docstrings, Naming, TypeMapper


class RootClientSurface(DomainEmitter):
    """Per-API glue: the generated composition root aggregating all resources (разд. F, разд. C)."""

    name = "root_client"

    def __init__(
        self, naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings, env: Environment
    ) -> None:
        self._naming, self._type_mapper, self._docstrings, self._env = (
            naming,
            type_mapper,
            docstrings,
            env,
        )

    def emit(self, resources: tuple[ir.Resource, ...], ctx: EmitContext) -> str:
        page = resolve_root_client(resources, ctx, self._naming, self._docstrings)
        return self._env.get_template("root_client.jinja").render(page=page)
```

- [ ] **Step 4: Прогнать - зелено**

Run: `pytest tests/emitters/python/surfaces/test_root_client.py -q` -> PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(surfaces): root_client glue (DomainEmitter)"
```

---

## PHASE 8 / Бэкенд + оркестратор + CLI

### Task 8.1: `python/backend.py` - `@backend("python")`

**Files:**
- Create: `src/refract/emitters/python/backend.py`
- Test: `tests/emitters/python/test_backend.py`

**Interfaces:**
- Consumes: реестр `@backend` (разд. 3.2/registry), все 5 стратегий (фаза 4), env (5.1), все 7 per-resource surface'ов (`package`, `models`, `requests`, `client`, `cli`, `mcp`, `tests`) + domain surface `root_client` (Task 7.8, `DomainEmitter`, разд. C).
- Produces: `python_backend() -> LanguageBackend` (зарегистрирован под `"python"`; композиция, не наследование). `surfaces` = per-resource; `domain_surfaces=(RootClientEmitter(...),)` = per-API glue (root-client, разд. C/G10). Потребляется `Generator` через `get_backend("python")`.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/emitters/python/test_backend.py
from refract.emitters.api import LanguageBackend
from refract.emitters.python.backend import python_backend
from refract.emitters.registry import get_backend


def test_backend_composes_all_strategies_and_surfaces():
    b = python_backend()
    assert isinstance(b, LanguageBackend) and b.name == "python"
    assert {s.name for s in b.surfaces} == {
        "package", "models", "requests", "client", "cli", "mcp", "tests"}
    assert {s.name for s in b.domain_surfaces} == {"root_client"}  # per-API glue (разд. C/G10)


def test_registered_and_resolvable():
    assert get_backend("python").name == "python"  # lazy import wires the registry
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать**

```python
# src/refract/emitters/python/backend.py
from __future__ import annotations

from refract.emitters.api import LanguageBackend
from refract.emitters.python.docstrings import PythonDocstrings
from refract.emitters.python.environment import make_environment
from refract.emitters.python.format import RuffFormatter
from refract.emitters.python.layout import PythonLayout
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.surfaces.cli import CliSurface
from refract.emitters.python.surfaces.client import ClientSurface
from refract.emitters.python.surfaces.mcp import McpSurface
from refract.emitters.python.surfaces.models import ModelsSurface
from refract.emitters.python.surfaces.package import PackageSurface
from refract.emitters.python.surfaces.requests import RequestsSurface
from refract.emitters.python.surfaces.root_client import RootClientEmitter
from refract.emitters.python.surfaces.tests import TestsSurface
from refract.emitters.python.types import PythonTypeMapper
from refract.emitters.registry import backend


@backend("python")
def python_backend() -> LanguageBackend:
    """Compose the Python backend: 5 injected strategies + 7 per-resource surfaces + root_client glue."""
    naming = PythonNaming()
    type_mapper = PythonTypeMapper()
    docstrings = PythonDocstrings()
    env = make_environment()
    parts = (naming, type_mapper, docstrings, env)
    surfaces = (
        PackageSurface(),
        ModelsSurface(*parts),
        RequestsSurface(*parts),
        ClientSurface(*parts),
        CliSurface(*parts),
        McpSurface(*parts),
        TestsSurface(*parts),
    )
    return LanguageBackend(
        name="python", naming=naming, type_mapper=type_mapper, formatter=RuffFormatter(),
        docstrings=docstrings, layout=PythonLayout(), surfaces=surfaces,
        domain_surfaces=(RootClientEmitter(*parts),),
    )
```

(Все non-package per-resource surface'ы имеют единый конструктор `(naming, type_mapper, docstrings, env)`; `PackageSurface()` - без стратегий. `RootClientEmitter` (Task 7.8, `DomainEmitter`) делит тот же конструктор `*parts` и бежит ОДИН раз над всеми ресурсами домена, а не per-resource - разд. C/G10.)

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat(python): @backend('python') composition (+ root_client domain surface)`)

### Task 8.2: `generation.py` - `Generator`

**Files:**
- Create: `src/refract/generation.py`
- Modify: `src/refract/emitters/python/layout.py` (`PythonLayout.path` -> добавить ветку `root_client` -> `{domain}/client.py`)
- Test: `tests/test_generation.py`

**Interfaces:**
- Consumes: `get_backend` (registry), `SpecLoader.load` + `SpecLoader.load_client_config` (spec, разд. J), `EmitContext`/`LanguageBackend`/`DomainEmitter` (разд. C), `ir.ClientConfig` (разд. I), `SpecError` (spec).
- Produces: `Generator` - `for_language(lang)`, `render_resource(res, config) -> dict[str,str]` (per-resource surface-gating через `applies`, путь через `layout`, формат через `backend.formatter`), `render_domain(resources, config) -> dict[str,str]` (per-API glue: `backend.domain_surfaces` ОДИН раз над `tuple[Resource,...]` -> root-client), `plan(specs_dir, out_dir, client_config=None) -> dict[Path,str]`, `write(plan)`, `check(plan) -> int`; module-level `find_client_config(specs_dir) -> Path`. `package_root` = `ycli.yandex.{domain}` (G2). `plan` грузит домен-`ClientConfig` из `client.yaml` (рядом/выше resource-спек, разд. J), строит `EmitContext(package_root=..., config=...)`, прогоняет per-resource surfaces по КАЖДОМУ ресурсу, ЗАТЕМ `backend.domain_surfaces` один раз над полным набором ресурсов домена. Потребляется CLI + оракулом.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/test_generation.py
from pathlib import Path

from refract.generation import Generator
from refract.spec import SpecLoader

_EX = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker"


def _config():
    return SpecLoader.load_client_config(_EX / "client.yaml")


def test_render_resource_gates_surfaces(me_resource, priorities_resource):
    g = Generator.for_language("python")
    config = _config()
    me_files = set(g.render_resource(me_resource, config))
    assert me_files == {
        "tracker/me/__init__.py", "tracker/me/models.py", "tracker/me/_requests.py",
        "tracker/me/client.py", "tracker/me/cli.py", "tracker/me/mcp.py",
        "tests/tracker/test_me.py",
    }
    prio_files = set(g.render_resource(priorities_resource, config))
    assert prio_files == {  # no cli, no tests facets -> gated out; _requests added by D
        "tracker/priorities/__init__.py", "tracker/priorities/models.py",
        "tracker/priorities/_requests.py", "tracker/priorities/client.py",
        "tracker/priorities/mcp.py",
    }


def test_render_domain_emits_root_client(me_resource, priorities_resource):
    # domain_surfaces run ONCE over the FULL resource tuple -> the per-API root client (разд. C/G10)
    g = Generator.for_language("python")
    domain_files = g.render_domain((me_resource, priorities_resource), _config())
    assert set(domain_files) == {"tracker/client.py"}
    assert "class TrackerClient" in domain_files["tracker/client.py"]


def test_render_is_ruff_formatted(me_resource):
    out = Generator.for_language("python").render_resource(me_resource, _config())[
        "tracker/me/_requests.py"]
    assert out.endswith("\n") and "def get() -> Request[Me]:" in out


def test_plan_includes_root_client_and_resource_files(tmp_path):
    g = Generator.for_language("python")
    the_plan = g.plan(_EX, tmp_path / "out")
    rels = {p.relative_to(tmp_path / "out").as_posix() for p in the_plan}
    assert "tracker/client.py" in rels          # root client (domain surface, once per domain)
    assert "tracker/me/client.py" in rels        # per-resource
    assert "tracker/me/_requests.py" in rels
    assert "tracker/priorities/_requests.py" in rels


def test_write_then_check_roundtrips(tmp_path):
    g = Generator.for_language("python")
    the_plan = g.plan(_EX, tmp_path / "out")
    assert the_plan
    g.write(the_plan)
    assert g.check(the_plan) == 0


def test_check_detects_drift(tmp_path):
    g = Generator.for_language("python")
    the_plan = g.plan(_EX, tmp_path / "out")
    g.write(the_plan)
    next(iter(the_plan)).write_text("corrupted", encoding="utf-8")
    assert g.check(the_plan) == 1
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать**

Сначала - развязка пути domain-surface в `PythonLayout` (name<->path coupling, decision #22): `root_client` -> `{domain}/client.py` (отличен от per-resource `{domain}/{resource}/client.py`).

```python
# src/refract/emitters/python/layout.py  (PythonLayout.path - добавить ветку root_client)
    def path(self, res: ir.Resource, surface: str) -> str:
        base = f"{res.domain}/{res.resource}"
        if surface == "root_client":                 # per-API domain surface (разд. C DomainEmitter)
            return f"{res.domain}/client.py"
        if surface == "tests":
            return f"tests/{res.domain}/test_{res.resource}.py"
        if surface == "package":
            return f"{base}/__init__.py"
        return f"{base}/{_FILENAME[surface]}.py"
```

```python
# src/refract/generation.py
"""The language-agnostic driver: resolve a backend, render each resource's gated surfaces,
then the per-API domain glue (root client) once over all of the domain's resources."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from refract.emitters.api import EmitContext
from refract.emitters.registry import get_backend
from refract.spec import SpecError, SpecLoader

if TYPE_CHECKING:
    from refract import ir
    from refract.emitters.api import LanguageBackend

__all__ = ["Generator", "find_client_config"]


def _package_root(res: ir.Resource) -> str:
    """Where the generated code's runtime/base/models live (G2; ycli convention by default)."""
    return f"ycli.yandex.{res.domain}"


def find_client_config(specs_dir: Path) -> Path:
    """Locate the per-API client.yaml sibling of / above the resource specs (разд. J)."""
    matches = sorted(Path(specs_dir).glob("**/client.yaml"))
    if not matches:
        raise SpecError(f"no client.yaml found under {specs_dir}")
    return matches[0]


class Generator:
    """Orchestrates spec -> per-surface output for one backend. Never names a surface directly."""

    def __init__(self, backend: LanguageBackend) -> None:
        self._backend = backend

    @classmethod
    def for_language(cls, lang: str) -> Generator:
        return cls(get_backend(lang))

    def render_resource(self, res: ir.Resource, config: ir.ClientConfig) -> dict[str, str]:
        ctx = EmitContext(package_root=_package_root(res), config=config)
        files: dict[str, str] = {}
        for surface in self._backend.surfaces:
            if surface.applies(res):
                path = self._backend.layout.path(res, surface.name)
                files[path] = self._backend.formatter.format(surface.emit(res, ctx))
        return files

    def render_domain(
        self, resources: tuple[ir.Resource, ...], config: ir.ClientConfig
    ) -> dict[str, str]:
        """Run each domain surface ONCE over ALL of the domain's resources (root client, разд. C)."""
        ctx = EmitContext(package_root=_package_root(resources[0]), config=config)
        files: dict[str, str] = {}
        for surface in self._backend.domain_surfaces:
            path = self._backend.layout.path(resources[0], surface.name)
            files[path] = self._backend.formatter.format(surface.emit(resources, ctx))
        return files

    def plan(
        self, specs_dir: Path, out_dir: Path, client_config: Path | None = None
    ) -> dict[Path, str]:
        config = SpecLoader.load_client_config(client_config or find_client_config(specs_dir))
        by_domain: dict[str, list[ir.Resource]] = defaultdict(list)
        the_plan: dict[Path, str] = {}
        for spec_path in sorted(Path(specs_dir).glob("**/resource.yaml")):
            res = SpecLoader.load(spec_path)
            by_domain[res.domain].append(res)
            for rel, content in self.render_resource(res, config).items():
                the_plan[Path(out_dir) / rel] = content
        for resources in by_domain.values():   # per-API glue: root client, once per domain
            for rel, content in self.render_domain(tuple(resources), config).items():
                the_plan[Path(out_dir) / rel] = content
        return the_plan

    @staticmethod
    def write(the_plan: dict[Path, str]) -> None:
        for path, content in the_plan.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    @staticmethod
    def check(the_plan: dict[Path, str]) -> int:
        stale = [
            path for path, content in the_plan.items()
            if (path.read_text(encoding="utf-8") if path.exists() else None) != content
        ]
        if stale:
            print("out/ is stale; run: refract generate --write", file=sys.stderr)
            for path in stale:
                print(f"  drift: {path}", file=sys.stderr)
            return 1
        print(f"out/ is up to date ({len(the_plan)} files).", file=sys.stderr)
        return 0
```

(`plan` группирует ресурсы по `res.domain` -> per-resource surfaces прогоняются для каждого, затем `render_domain` один раз на домен пишет root-client `{domain}/client.py`. `client.yaml` резолвится `find_client_config` рядом/выше resource-спек и грузится `SpecLoader.load_client_config` в `ir.ClientConfig` (разд. I/разд. J; вводится в Phase 2, мигрируется в Task 9.1).)

- [ ] **Step 4: Прогнать - зелено** -> **Step 5: Commit** (`feat: backend-driven Generator (plan/render/write/check + root-client glue)`)

### Task 8.3: `cli.py` - полноценный Typer-app

**Files:**
- Modify: `src/refract/cli.py` (заменить стаб), `pyproject.toml` (`[project.scripts] refract = "refract.cli:app"`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `Generator` + `find_client_config` (8.2), `SpecError` (spec).
- Produces: `app` (Typer) с командой `generate` (`--write`/`--check`/`--out`/`--specs`/`--client`/`--lang`); entry point `refract.cli:app`. `generate` локейтит `client.yaml` для домена (рядом/выше resource-спек через `find_client_config`; переопределяется `--client`) и передаёт его `plan`.

- [ ] **Step 1: Написать падающие тесты** (Typer `CliRunner`)

```python
# tests/test_cli.py
from pathlib import Path

from typer.testing import CliRunner

from refract.cli import app

runner = CliRunner()
_EX = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker"


def test_no_flag_prints_plan_without_writing(tmp_path):
    out = tmp_path / "out"
    res = runner.invoke(app, ["generate", "--specs", str(_EX), "--out", str(out)])
    assert res.exit_code == 0 and "would render" in res.stdout
    assert not out.exists()


def test_write_then_check_roundtrips(tmp_path):
    out = tmp_path / "out"
    assert runner.invoke(app, ["generate", "--specs", str(_EX), "--out", str(out), "--write"]).exit_code == 0
    assert (out / "tracker" / "me" / "_requests.py").exists()
    assert (out / "tracker" / "client.py").exists()   # root-client glue written too
    assert runner.invoke(app, ["generate", "--specs", str(_EX), "--out", str(out), "--check"]).exit_code == 0


def test_spec_error_exits_2(tmp_path):
    root = tmp_path / "specs"
    bad = root / "tracker" / "me"
    bad.mkdir(parents=True)
    (bad / "resource.yaml").write_text("domain: t\nunknown_key: 1\n", encoding="utf-8")
    (root / "client.yaml").write_text(
        "name: t\nserver:\n  base_url: https://x/v1\nauth: {}\n", encoding="utf-8")
    res = runner.invoke(app, ["generate", "--specs", str(root), "--out", str(tmp_path / "out")])
    assert res.exit_code == 2


def test_missing_client_yaml_exits_2(tmp_path):
    bad = tmp_path / "specs" / "tracker" / "me"
    bad.mkdir(parents=True)
    (bad / "resource.yaml").write_text("domain: t\nsecurity: token\n", encoding="utf-8")
    res = runner.invoke(app, ["generate", "--specs", str(tmp_path / "specs"), "--out", str(tmp_path / "out")])
    assert res.exit_code == 2  # find_client_config raises SpecError -> exit 2


def test_requires_subcommand():
    assert runner.invoke(app, []).exit_code != 0
```

- [ ] **Step 2: Прогнать - падает** -> **Step 3: Реализовать**

```python
# src/refract/cli.py
"""The ``refract`` console-script entry point (Typer)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from refract.generation import Generator, find_client_config
from refract.spec import SpecError

app = typer.Typer(name="refract", no_args_is_help=True, add_completion=False)

_EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples" / "ycli-tracker"


@app.command()
def generate(
    write: Annotated[bool, typer.Option("--write", help="write rendered files to out/")] = False,
    check: Annotated[bool, typer.Option("--check", help="exit 1 if any out/ file is stale")] = False,
    out: Annotated[Path, typer.Option("--out", help="output root")] = _EXAMPLES / "out",
    specs: Annotated[Path, typer.Option("--specs", help="specs root")] = _EXAMPLES,
    client: Annotated[
        Path | None, typer.Option("--client", help="per-API client.yaml (default: located under --specs)")
    ] = None,
    lang: Annotated[str, typer.Option("--lang", help="target backend language")] = "python",
) -> None:
    """Render every resource.yaml under --specs (+ its client.yaml glue) into --out for --lang."""
    generator = Generator.for_language(lang)
    try:
        client_config = client or find_client_config(specs)
        the_plan = generator.plan(specs, out, client_config)
    except SpecError as error:
        typer.echo(f"spec error: {error}", err=True)
        raise typer.Exit(2) from error
    if write:
        generator.write(the_plan)
        typer.echo(f"wrote {len(the_plan)} files.")
        return
    if check:
        raise typer.Exit(generator.check(the_plan))
    for path in the_plan:
        typer.echo(f"would render {path}")
```

В `pyproject.toml`: `[project.scripts]` -> `refract = "refract.cli:app"`.

(`generate` локейтит `client.yaml` через `find_client_config(specs)` - sibling/ancestor resource-спек, разд. J - либо берёт явный `--client`; отсутствие `client.yaml` -> `SpecError` -> exit 2, как и любая spec-ошибка.)

- [ ] **Step 4: Прогнать - зелено** (`pytest tests/test_cli.py -q`; `refract generate --help`) -> **Step 5: Commit** (`feat: Typer CLI wired to Generator; locates client.yaml; entry point refract.cli:app`)

---

## PHASE 9 / Оракул (L1/L3) + DX + очистка

### Task 9.1: Мигрировать spec на `client.yaml` + перегенерировать D-вывод (с root-client) + L1 drift-нет; удалить uplink-goldens

**Files:** (spec-ВХОД уже мигрирован на `client.yaml` в Phase 2 / Task 2.3 - здесь ТОЛЬКО выход)
- Modify: `examples/ycli-tracker/tracker/{me,priorities}/resource.yaml` - prose: убрать uplink из `module_docs.client` (разд. F)
- Delete: `examples/ycli-tracker/golden/**` (uplink-goldens; L2 отложен - G3)
- Regenerate: `examples/ycli-tracker/out/**` (D-вывод - committed L1-корпус; ВКЛЮЧАЯ root-client golden `tracker/client.py`)
- Test: `tests/test_snapshot_out.py`

**Interfaces:**
- Produces: committed D-вывод под `out/` = L1-снапшот (per-resource surfaces + per-API root-client `tracker/client.py`); `refract generate --write` - механизм обновления (реализует DX-афорданс разд. 8 «--update-snapshots»: правка шаблона -> `refract generate --write`, ручного редактирования ожидаемых файлов нет).

- [ ] **Step 1: Spec-ВХОД уже мигрирован в Phase 2** (Task 2.3): `client.yaml` создан, `base_url:` убран из обоих `resource.yaml`, `_auth.yaml` удалён. Здесь остаётся ТОЛЬКО prose-правка `module_docs.client` (разд. F): `me` -> `"Declarative Tracker /myself client - transport ONLY (thin sugar over request builders)."`; `priorities` -> `"Declarative Tracker priorities client - transport ONLY (thin sugar over request builders)."` (убрать многострочный uplink-NOTE).

- [ ] **Step 2: Написать падающий L1 drift-тест**

```python
# tests/test_snapshot_out.py
from pathlib import Path

from refract.generation import Generator

_EX = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker"


def test_committed_out_matches_fresh_render():
    # The committed out/ tree IS the L1 snapshot: it must equal a fresh render (no drift).
    g = Generator.for_language("python")
    assert g.check(g.plan(_EX, _EX / "out")) == 0


def test_root_client_golden_committed():
    # the per-API root client is part of the committed L1 corpus (разд. C DomainEmitter / разд. F target)
    root = (_EX / "out" / "tracker" / "client.py").read_text(encoding="utf-8")
    assert "class TrackerClient" in root and "MultiHeaderAuth" in root
```

- [ ] **Step 3: Перегенерировать `out/` (с root-client) и удалить uplink-goldens**

```bash
refract generate --specs examples/ycli-tracker --out examples/ycli-tracker/out --write
git rm -r examples/ycli-tracker/golden
```

- [ ] **Step 4: Ревью diff `out/`** - сверить с разд. F:
  - me: +`_requests.py`, `client.py` -> thin-sugar; priorities: +`_requests.py`, `_verb`/`verb`-split удалён;
  - НОВЫЙ root-client `out/tracker/client.py` = разд. F-таргет: `TrackerClient` строит `MultiHeaderAuth({"Authorization": "OAuth {oauth_token}", "X-Org-Id": ...})` + `Session(base_url, client=httpx.Client(auth=...))` из `client.yaml` (`server.base_url` -> строка `Session`; `auth.oauth_token` kind=`multi_header` -> `MultiHeaderAuth` + headers; `inputs` -> параметры конструктора + `from_env`); `.me`/`.priorities` - из набора загруженных ресурсов;
  - models/mcp/cli/tests/`__init__` - как раньше.
  - Прогнать: `pytest tests/test_snapshot_out.py -q` -> PASS.

- [ ] **Step 5: Commit** (`feat!: regenerate example output as D (+ root-client glue); migrate _auth.yaml -> client.yaml; drop uplink goldens (L2 deferred)`)

### Task 9.2: L3 поведенческий оракул (D-ядро + root-client против `refract.runtime`)

**Files:**
- Create: `tests/behavioral/__init__.py`, `tests/behavioral/test_d_core_runs.py`
- Modify: `pyproject.toml` (регистрация маркера `behavioral`)
- Test: сам себе тест (opt-in, `-m behavioral`).

**Interfaces:**
- Consumes: `RequestsSurface` (7.1), `ClientSurface` (7.2), `RootClientEmitter` (7.8), `RuffFormatter` (4.3), `refract.runtime` (разд. E - auth-agnostic `Session` + `httpx.Auth`-механизмы), `EmitContext` + `ir.ClientConfig` (разд. C/разд. I), `ir` (разд. B).
- Produces: доказательство, что D-`_requests`/`client` **И генерируемый root-client glue** реально импортируются и исполняются: генерация -> валидный Python -> root-client строит auth-agnostic `Session` над `httpx.Client(auth=...)` из `ClientConfig` -> `send` парсит `response_model`. Auth сидит на инжектированном клиенте (`httpx.Auth`), не в `send()` (разд. E). `package_root` указывает на локальный `demopkg`, чьи `runtime`/`base`-модули реэкспортируют референс-рантайм `refract.runtime` (разд. E) - эмитированный код бежит против `refract.runtime`. Scope - D-ядро + glue; полный quartet (cli/mcp через ycli-рантайм) - интеграционный тест ycli (вне scope A, разд. 10). Маркирован `@pytest.mark.behavioral` (не в быстром гейте).

- [ ] **Step 1: Зарегистрировать маркер** в `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["behavioral: opt-in tests that import + run emitted code (slow; excluded by default)"]
addopts = "--strict-markers --import-mode=importlib --cov=refract --cov-report=term-missing --cov-fail-under=0 -m 'not behavioral'"
```
(`-m 'not behavioral'` - L3 opt-in; гоняется явно `pytest -m behavioral`.)

- [ ] **Step 2: Написать L3-тест** (генерит `_requests`+`client`+root-client в tmp-пакет с runtime/base-шимами над `refract.runtime` + plain-pydantic models; импортит; строит root-client из `ClientConfig`; шлёт через stubbed httpx)

```python
# tests/behavioral/test_d_core_runs.py
import importlib
import subprocess
import sys

import httpx
import pytest

from refract import ir
from refract.emitters.api import EmitContext
from refract.emitters.python.docstrings import PythonDocstrings
from refract.emitters.python.environment import make_environment
from refract.emitters.python.format import RuffFormatter
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.surfaces.client import ClientSurface
from refract.emitters.python.surfaces.requests import RequestsSurface
from refract.emitters.python.surfaces.root_client import RootClientEmitter
from refract.emitters.python.types import PythonTypeMapper
from refract.ir.types import ScalarType

pytestmark = pytest.mark.behavioral

_WIDGET = ir.Resource(
    domain="demo", resource="widget", security="token",
    models=(
        ir.ObjectModel(name="Widget", fields=(
            ir.Field(name="id", type=ScalarType(scalar="integer")),
            ir.Field(name="name", type=ScalarType(scalar="string")))),
        ir.ObjectModel(name="WidgetCreate", fields=(
            ir.Field(name="name", type=ScalarType(scalar="string")),)),
    ),
    operations=(
        ir.Operation(name="get", method="GET", path="widget", operation_id="widget_get",
                     response_model="Widget"),
        ir.Operation(name="create", method="POST", path="widget", operation_id="widget_create",
                     body=ir.Body(mode="typed_model", model="WidgetCreate"),  # by_alias/omit_none default
                     response_model="Widget"),
    ),
)

# base_url + auth are per-API glue now (разд. I): they live on ClientConfig, NOT on Resource.
_CONFIG = ir.ClientConfig(
    name="demo",
    server=ir.Server(base_url="https://api.demo/v1"),
    auth=(("token", ir.HeaderAuth(
        header="Authorization", template="Bearer {oauth_token}",
        inputs=(ir.AuthInput(name="token", env="DEMO_TOKEN"),))),),
)


def _write_pkg(tmp_path):
    parts = (PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment())
    fmt = RuffFormatter()
    ctx = EmitContext(package_root="demopkg", config=_CONFIG)

    pkg = tmp_path / "demopkg"
    (pkg / "widget").mkdir(parents=True)
    (pkg / "runtime").mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "widget" / "__init__.py").write_text("", encoding="utf-8")
    # runtime/base shims bridge refract's reference runtime (разд. E) into the ycli-flat layout (G2)
    (pkg / "runtime" / "__init__.py").write_text(
        "from refract.runtime.request import Request\n", encoding="utf-8")
    (pkg / "runtime" / "session.py").write_text(
        "from refract.runtime.session import Session\n", encoding="utf-8")
    (pkg / "runtime" / "auth.py").write_text(
        "from refract.runtime.auth import HeaderAuth, MultiHeaderAuth\n", encoding="utf-8")
    (pkg / "base.py").write_text(
        "from refract.runtime.base import Resource as DemoResource\n", encoding="utf-8")
    (pkg / "widget" / "models.py").write_text(
        "from pydantic import BaseModel\n\n\n"
        "class Widget(BaseModel):\n    id: int | None = None\n    name: str | None = None\n\n\n"
        "class WidgetCreate(BaseModel):\n    name: str\n", encoding="utf-8")

    (pkg / "widget" / "_requests.py").write_text(
        fmt.format(RequestsSurface(*parts).emit(_WIDGET, ctx)), encoding="utf-8")
    (pkg / "widget" / "client.py").write_text(
        fmt.format(ClientSurface(*parts).emit(_WIDGET, ctx)), encoding="utf-8")
    (pkg / "client.py").write_text(  # root-client glue: DomainEmitter runs over the resource tuple
        fmt.format(RootClientEmitter(*parts).emit((_WIDGET,), ctx)), encoding="utf-8")
    return pkg


def test_generated_sources_are_ruff_clean(tmp_path):
    pkg = _write_pkg(tmp_path)
    for rel in ("widget/_requests.py", "widget/client.py", "client.py"):
        r = subprocess.run(["ruff", "check", str(pkg / rel)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr


def test_generated_root_client_imports_and_sends(tmp_path, monkeypatch):
    _write_pkg(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    # stub every httpx.Client the generated root client builds with a MockTransport; the auth the
    # root client installs (httpx.Auth on the client, разд. E) must reach the transport's request.
    def handler(request):
        assert request.headers["Authorization"] == "Bearer x"  # auth-agnostic Session, auth on client
        return httpx.Response(200, json={"id": 1, "name": "x"})

    real_client = httpx.Client

    def stub_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", stub_client)
    try:
        # builders are pure - no I/O
        requests_mod = importlib.import_module("demopkg.widget._requests")
        from demopkg.widget.models import Widget, WidgetCreate  # noqa: E402
        assert requests_mod.get().path == "widget"
        assert requests_mod.create(WidgetCreate(name="x")).json_body == {"name": "x"}

        # the generated root client builds Session + httpx.Client(auth=HeaderAuth) from ClientConfig,
        # then client.res.op(...) sugars through the auth-agnostic Session.send
        root_mod = importlib.import_module("demopkg.client")
        client = root_mod.DemoClient(token="x")
        widget = client.widget.get()
        assert isinstance(widget, Widget) and widget.id == 1
    finally:
        for name in ("demopkg.client", "demopkg.widget.client", "demopkg.widget._requests",
                     "demopkg.widget.models", "demopkg.widget", "demopkg.runtime.session",
                     "demopkg.runtime.auth", "demopkg.runtime", "demopkg.base", "demopkg"):
            sys.modules.pop(name, None)
```

- [ ] **Step 3: Прогнать** `pytest -m behavioral -q` -> PASS. Убедиться, что дефолтный `pytest -q` их НЕ гоняет (`-m 'not behavioral'`).

- [ ] **Step 4: Commit** (`test(behavioral): L3 - D core + root-client generate, import, and send auth-agnostically (opt-in)`)

### Task 9.3: Восстановить гейт покрытия 100% + верификация всей сюиты

**Files:**
- Modify: `pyproject.toml` (гейт -> 100 + исключить `assert_never`)

- [ ] **Step 1: Восстановить гейт + исключить unreachable**

```toml
[tool.pytest.ini_options]
addopts = "--strict-markers --cov=refract --cov-report=term-missing --cov-fail-under=100 -m 'not behavioral'"

[tool.coverage.report]
show_missing = true
exclude_also = [
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "\\.\\.\\.",
    "assert_never",
]
```

- [ ] **Step 2: Прогнать полный быстрый гейт**

Run: `pytest -q` (100% покрытие `src/refract` или FAIL с указанием непокрытых строк)
Если что-то непокрыто - дописать L0-юниты (не понижать гейт). Ожидание: PASS, coverage 100%.

- [ ] **Step 3: Прогнать линтеры/тайпчек**

Run: `ruff check src tests && ruff format --check src tests && ty check`
Expected: чисто.

- [ ] **Step 4: Commit** (`test: restore 100% coverage gate; exclude assert_never from coverage`)

### Task 9.4: DX - `docs/adding-a-language.md`

**Files:**
- Create: `docs/adding-a-language.md`

- [ ] **Step 1: Написать чек-лист** нового бэкенда (без кода-заглушек - реальные шаги, ссылки на разд. -контракты):

```markdown
# Adding a language backend

refract's varying axes are all strategy registries - a new backend is additive (new directory +
`@backend` decorator), zero edits to central files.

1. **Create `src/refract/emitters/<lang>/`.** Mirror `emitters/python/` (the reference backend).
2. **Implement the 5 strategies** (contract: `src/refract/emitters/api.py`, разд. C):
   `Naming`, `TypeMapper` (`NeutralType` -> your language's types + null-default, `match`/`assert_never`),
   `Formatter` (wrap the language's formatter), `Docstrings`, `Layout` (incl. the `root_client`
   domain surface -> `{domain}/client.py`).
3. **Write the per-resource surface resolvers + templates** under `emitters/<lang>/{views,resolve}.py` +
   `templates/*.jinja`. Reuse the neutral core: `ir` (разд. A/разд. B), the local read/write branch on
   `op.body is not None` (разд. D - there is no `classify`/`OpShape`), `resolve.render_imports`/`signature_params`.
4. **Compose the per-API glue (`domain_surfaces`) + auth mechanism.** Implement a `DomainEmitter`
   (the root client, разд. C): aggregate the resources and build your language's HTTP client + auth from
   `ctx.config` (`ir.ClientConfig`, разд. I) - select the mechanism per `AuthScheme.kind` (разд. H) and reuse the
   `httpx.Auth` mechanism library in `runtime/auth.py` (разд. E), growing it by rule-of-three. It runs ONCE
   over all of a domain's resources (not per-resource).
5. **Register** `@backend("<lang>")` in `emitters/<lang>/backend.py`, composing your strategies +
   `surfaces` (per-resource) + `domain_surfaces` (root client) into a `LanguageBackend`.
6. **Run the conformance/L3 kit:** point a fixture's `package_root` at your runtime + a test
   `ClientConfig` and assert the emitted code imports + runs - builders are pure, the root client sends
   auth-agnostically (`tests/behavioral/`). Regenerate snapshots: `refract generate --write`.

You never touch `ir/`, `spec/`, `generation.py`, `registry.py`, or another backend.
```

- [ ] **Step 2: Commit** (`docs: adding-a-language checklist (DX)`)

### Task 9.5: `docs/research/` -> gitignored `artifacts/`

**Files:**
- Move: `docs/research/**` -> `artifacts/`
- Modify: `.gitignore` (+`artifacts/`)

- [ ] **Step 1: Перенести + разгитить**

```bash
mkdir -p artifacts && git mv docs/research/* artifacts/ 2>/dev/null || (mv docs/research/* artifacts/ && git rm -r --cached docs/research)
printf '\nartifacts/\n' >> .gitignore
git rm -r --cached artifacts 2>/dev/null || true
```
(Если `docs/research` был git-tracked - `git rm --cached` убирает из индекса, файлы остаются на диске в `artifacts/`.)

- [ ] **Step 2: Проверить** `git status` (artifacts/ untracked/ignored; docs/research удалён из индекса) -> **Step 3: Commit** (`chore: move research notes to gitignored artifacts/`)

---

## Self-Review (после ститча всех фаз)

Пройти по разд. -разделам спеки (`2026-07-14-refract-architecture-redesign-design.md`) и отметить задачу-реализатор для каждого решения разд. 2 и требования разд. 3-разд. 9. Прогнать placeholder-скан (нет «TODO»/«похоже на»/пустых шагов) и type-consistency (имена/сигнатуры из Shared Contracts совпадают во всех задачах). Отдельно проверить, что нейтральное ядро описано единообразно - `ir` (разд. A/разд. B) + локальное ветвление `op.body is not None` (разд. D); ни `classify`, ни `OpShape`, ни `shapes.py` нигде не остались (удалены, решение #14/G7). Проверить сквозную композицию glue: `DomainEmitter`/`root_client` (разд. C/G10) -> `Generator.render_domain` (Task 8.2) -> committed root-client golden (Task 9.1) -> L3 send (Task 9.2). Финальный full-suite прогон - Task 9.3.

---
