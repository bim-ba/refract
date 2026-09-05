# CLAUDE.md - refract

refract compiles one neutral YAML API spec (`resource.yaml` + `client.yaml`) into a typed Python SDK, CLI, FastMCP server, models and tests. It is alpha: one target language (Python) and one proving ground, the `examples/ycli-tracker` golden oracle, whose checked-in `out/` the generator must reproduce byte for byte.

Baseline agent discipline comes from the `core` and `drifts` plugins of the `bim-ba` marketplace; voice, tooling, Git and research defaults come from the personal layer in `~/.claude/CLAUDE.md`. This file carries only what is specific to this repository.

## Layout

| Path | Role |
|---|---|
| `src/refract/cli.py`, `generation.py` | the `refract` Typer entry point and the render driver |
| `src/refract/spec/` | `resource.yaml` / `client.yaml` loading and validation |
| `src/refract/ir/` | the typed intermediate representation |
| `src/refract/emitters/` | `ports.py` backend seam, `registry.py`, and `python/`, the one implemented backend |
| `src/refract/runtime/` | what generated code imports at run time (auth, base, request, session) |
| `tests/` | mirrors `src/refract/`; `tests/behavioral/` imports and runs emitted code |
| `examples/ycli-tracker/` | the golden-oracle spec plus its checked-in `out/` |
| `docs/design.md`, `docs/roadmap.md` | the full design and roadmap, ahead of the code in places |

## Conventions

- Python >= 3.12; `uv` only (`uv sync`, `uv run`), with `uv.lock` and the `dev` dependency group in `pyproject.toml`.
- ruff is both linter and formatter (`line-length = 100`, an explicit `select` list); `ty` is the type checker, configured with `error-on-warning = true`.
- `examples/` is excluded from ruff and from ty on purpose: it is external source used as a byte-equality target, so linting or reformatting it defeats the test it exists for.
- pytest runs with `--cov-fail-under=100` and `-m 'not behavioral'`; run the slow tests explicitly with `uv run pytest -m behavioral`.
- Versioning and releases are automated by release-please (`release-please-config.json`, `.github/workflows/release-please.yml`) — do not hand-edit the version.

## Verification

```sh
uv run ruff format --check . && uv run ruff check . && uv run ty check && uv run pytest
```

The same four steps `.github/workflows/ci.yml` runs. `uv run refract generate --check` is the separate drift gate: it renders in memory and fails if `examples/ycli-tracker/out/` has gone stale.
