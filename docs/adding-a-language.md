# Adding a language backend

refract's varying axes are all strategy registries - a new backend is additive (new directory +
`@backend` decorator), zero edits to central files.

1. **Create `src/refract/emitters/<lang>/`.** Mirror `emitters/python/` (the reference backend).
2. **Implement the 5 strategies** (contract: `src/refract/emitters/ports.py`):
   `Naming`, `TypeMapper` (`NeutralType` -> your language's types + null-default, `match`/`assert_never`),
   `Formatter` (wrap the language's formatter), `DocComments`, `FileLayout` (incl. the `root_client`
   domain surface -> `{domain}/client.py`).
3. **Write the per-resource surface resolvers + templates** under `emitters/<lang>/{views,resolve}.py` +
   `templates/*.jinja`. A resolver takes `(res, ctx)` and returns a page view; it reads `Naming`,
   `TypeMapper` and `DocComments` off `ctx` (`EmitContext`), never as its own parameters. Reuse the
   neutral core: `ir` (`src/refract/ir/`), the local read/write branch on `op.body is not None` (there is
   no `classify`/`OpShape`), `resolve._common.render_imports`/`signature_params`.
4. **List your surfaces in a table.** A surface is four values - name, `applies` gate, resolver,
   template filename - so `emitters/python/surfaces.py` holds one `SurfaceSpec` row per surface and two
   generic emitters (`TemplateSurface`, `TemplateDomainSurface`) that read them; `PackageSurface` is the
   one surface outside the table (no view, no template). Mirror that shape, or write plain
   `SurfaceEmitter` classes - the driver only calls `applies()` + `emit()`.
5. **Compose the per-API glue (`domain_surfaces`) + auth mechanism.** Implement a `DomainEmitter`
   (the root client, `src/refract/emitters/ports.py`): aggregate the resources and build your language's HTTP client + auth from
   `ctx.config` (`ir.ClientConfig`, `src/refract/ir/client.py`) - select the mechanism per `AuthScheme.kind` (`src/refract/ir/auth.py`) and reuse the
   `httpx.Auth` mechanism library in `runtime/auth.py` (`src/refract/runtime/`), growing it by rule-of-three. It runs ONCE
   over all of a domain's resources (not per-resource).
6. **Register** `@backend("<lang>")` in `emitters/<lang>/backend.py`, composing your strategies +
   `surfaces` (per-resource) + `domain_surfaces` (root client) into a `LanguageBackend`. The driver builds
   each resolver's `EmitContext` through `LanguageBackend.context(...)`, which pairs the caller's
   `package_root`/`config` with YOUR strategies - so never construct an `EmitContext` by hand.
7. **Run the conformance/L3 kit:** point a fixture's `package_root` at your runtime + a test
   `ClientConfig` and assert the emitted code imports + runs - builders are pure, the root client sends
   auth-agnostically (`tests/behavioral/`). Regenerate snapshots: `refract generate --write`.

You never touch `ir/`, `spec/`, `generation.py`, `registry.py`, or another backend.
