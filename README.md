# refract

A language-agnostic, spec-driven code generator. Author each API operation once in a neutral
YAML spec, lower it to a typed intermediate representation (IR), and emit — per (target
language × surface) — a typed HTTP client, CLI, MCP server, models, and tests, plus an OpenAPI
3.1 document. [`ycli`](https://github.com/bim-ba/ycli) is the first consumer.

**Status:** alpha — walking skeleton.

## Usage

```bash
uv run refract generate --check
```

See [`docs/design.md`](docs/design.md) for the full design spec.
