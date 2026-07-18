# Adding a language backend

refract's varying axes are all strategy registries - a new backend is additive (new directory +
`@backend` decorator), zero edits to central files.

1. **Create `src/refract/emitters/<lang>/`.** Mirror `emitters/python/` (the reference backend).
2. **Implement the 5 strategies** (contract: `src/refract/emitters/api.py`):
   `Naming`, `TypeMapper` (`NeutralType` -> your language's types + null-default, `match`/`assert_never`),
   `Formatter` (wrap the language's formatter), `Docstrings`, `Layout` (incl. the `root_client`
   domain surface -> `{domain}/client.py`).
3. **Write the per-resource surface resolvers + templates** under `emitters/<lang>/{views,resolve}.py` +
   `templates/*.jinja`. Reuse the neutral core: `ir` (`src/refract/ir/`), the local read/write branch on
   `op.body is not None` (there is no `classify`/`OpShape`), `resolve.render_imports`/`signature_params`.
4. **Compose the per-API glue (`domain_surfaces`) + auth mechanism.** Implement a `DomainEmitter`
   (the root client, `src/refract/emitters/api.py`): aggregate the resources and build your language's HTTP client + auth from
   `ctx.config` (`ir.ClientConfig`, `src/refract/ir/client.py`) - select the mechanism per `AuthScheme.kind` (`src/refract/ir/auth.py`) and reuse the
   `httpx.Auth` mechanism library in `runtime/auth.py` (`src/refract/runtime/`), growing it by rule-of-three. It runs ONCE
   over all of a domain's resources (not per-resource).
5. **Register** `@backend("<lang>")` in `emitters/<lang>/backend.py`, composing your strategies +
   `surfaces` (per-resource) + `domain_surfaces` (root client) into a `LanguageBackend`.
6. **Run the conformance/L3 kit:** point a fixture's `package_root` at your runtime + a test
   `ClientConfig` and assert the emitted code imports + runs - builders are pure, the root client sends
   auth-agnostically (`tests/behavioral/`). Regenerate snapshots: `refract generate --write`.

You never touch `ir/`, `spec/`, `generation.py`, `registry.py`, or another backend.
