# Spec-as-Code — synthesis + adversarial review (cycle 3, final)

Adversarial synthesis + validation pass over docs 00–09. Every claim is grounded in a doc
citation or a real source file read this pass (repo `/home/sava/dev/dev/ycli`, `main` @ 9f272a4).
Ground-truth counts measured this pass: **50 resource dirs** (tracker 32 / wiki 9 / forms 9),
**222 `@mcp.tool`s**, **228 uplink HTTP methods** (~228 real ops), `entities` god-resource
**3060 LOC across its 4 files, 30 MCP tools**, **52 `models.py` files / 310 `APIModel` classes**,
of which only **2 files carry a `model_validator/field_validator`**, **6 use `extra="allow"`**,
**7 have a `@property/@computed_field`**.

---

## Deliverable 1 — Comparison matrix

Rubric weights (doc 00): C1 extensibility ×3 (north star), C2 4-layer coverage ×3, C3 invariants
×3, C4 ergonomics ×2, C5 escape hatch ×2, C6 reviewability ×2, C7 migration ×2, C8 toolchain
risk ×1, C9 2nd consumer ×1. Σweights = 19; max weighted = 95. YAML is split into S1
(template-direct) and S4 (typed IR) on the two criteria where the bake-off proves they diverge
(C1, C9 — doc 07 §3.3).

| Criterion (weight) | S0 base | S1 yaml-tmpl | S4 yaml-IR | S5 py-descr | S2 openapi | S3 runtime |
|---|---|---|---|---|---|---|
| **C1 extensibility ×3** | 2 | 3 | 4 | **5** | 2 | 2 |
| **C2 4-layer coverage ×3** | 2 | 5 | 5 | 4 | 3 | 2 |
| **C3 invariants ×3** | 5 | 5 | 5 | 5 | 2 | 1 |
| **C4 ergonomics ×2** | 2 | 4 | 4 | 4 | 2 | 4 |
| **C5 escape hatch ×2** | 5 | 4 | 4 | **5** | 3 | 3 |
| **C6 reviewability ×2** | 5 | 4 | 4 | 4 | 3 | 1 |
| **C7 migration ×2** | 5 | 4 | 4 | 4 | 2 | 1 |
| **C8 toolchain risk ×1** | 5 | 3 | 3 | 3 | 3 | 2 |
| **C9 2nd consumer ×1** | 1 | 4 | 5 | 3 | 5 | 2 |
| **WEIGHTED TOTAL /95** | **67** | **78** | **82** | **82** | **49** | **37** |

**Score justifications (grounded):**

- **C1 (north star).** S4 typed-IR: an unforeseen shape = one `ty`-checked IR node + emitter
  clauses with `assert_never`-enforced exhaustiveness → 4 (doc 07 §3.3). S1 template-direct: 3
  untyped Jinja arms in shared files, no exhaustiveness guarantee, a typo fails only at emit time
  → 3. **S5 = 5**: the escape hatch is a *type-checked function object* (`handler=upload_pipeline`,
  resolved by `ty` at author time) and the spec itself is type-checked — an unforeseen op is
  *always expressible today with zero framework change* (doc 08 §Extensibility). S0/S2/S3 = 2
  (full hand-cost / foreign x-ext / guarantees already gone).
- **C2.** S1/S4 generate client+cli+mcp+tests+registration AND pair with datamodel-codegen for the
  models slice (~85% headline) → 5. S5 generates the same three surfaces + tests but **keeps
  models hand-written by design** (doc 08 §60-vs-85) → 4 (cedes the biggest LOC chunk, 8.1k, to
  hand-authoring). S2 = 3 (datamodel-codegen handles models, everything else still needs bespoke
  emitters — doc 09 §4). S0/S3 = 2.
- **C3.** All committed-source strategies satisfy ARCH-1..11 by construction, py.typed clean,
  ARCH-3 annotation-as-data (doc 07 §3.4, doc 08 §Invariant fit) → 5. S2 = 2 (rip-and-replace of
  the uplink/APIModel/FastMCP stack + x-ext annotations lose ARCH-3 fail-closed — doc 05 §0.2, doc
  09 §2). S3 = 1 (breaks py.typed, coverage granularity, ARCH-1/2/3/6 + import-linter, all
  file-coupled — doc 09 Part S3 §2).
- **C4.** S1/S4/S5 all ~4: YAML has clean `|` prose blocks but stringly-typed embedded Python; S5
  is `ty`-checked on structure but its prose-as-escaped-`\n`-string-literals is genuinely uglier
  than YAML block scalars (compare doc 07 op-1 vs doc 08 op-1) — they wash to 4 for *opposite*
  reasons. S2 = 2 (doc 09 §3: pure OpenAPI *ties* today's line count expressing less, 76 vs 77;
  +x-ext = 95, worse). S3 = 4 (its one appeal: literally fewer files). S0 = 2.
- **C5.** S5 = 5 (function-object handler, never blocks, type-checked — doc 08 §Escape-hatch). S1/S4
  = 4 (never blocks, but `handler: "module:fn"` is an *unchecked string* → typo = runtime
  ImportError; questions_move is the messiest, two hand locations — doc 07 §3.2). S0 = 5 (all hand).
- **C7.** All codegen strategies: resource-by-resource, `--check` gate (doc 07 §3.4). S5 docked
  nothing extra numerically but carries a real circular-import surface (spec.py→models+handlers,
  doc 08 §failure-mode-2). S2/S3 = 2/1 (rip-replace / all-or-nothing ARCH rewrite).
- **C9.** S4-IR: a new emitter over the IR is cheap and YAML is language-portable → 5. S1 = 4.
  **S5 = 3**: descriptors are surface-agnostic but *Python-coupled* — a future non-Python consumer
  must import Python to read specs (doc 05 §4.1). S2 = 5 (OpenAPI *is* the interchange format — its
  one real strength). S3 = 2.

**Eliminated (one line each):**
- **S2 (OpenAPI) — rejected:** OpenAPI 3.x has no native vocabulary for ycli's pagination drains,
  4-call upload orchestration, `Ack` synthesis, or the internal/public split; `x-` vendor
  extensions reinvent the whole generator in a *more verbose* foreign format (95 > 77 lines for
  `issues_create`, doc 09 §3) while forcing a rip-and-replace no real multi-surface generator
  actually wires this way (doc 05 §0.2).
- **S3 (runtime) — ruled OUT:** buys only "fewer repo files," and pays with py.typed, per-op
  coverage granularity, and all four *file-coupled* ARCH checks (`_resource_dirs()` walks
  `iterdir()` on disk — doc 09 Part S3 §2); even boto3, the mature precedent, ends up shipping a
  separate generated `boto3-stubs` project anyway.

**Reading the totals.** The two live contenders sit in a **genuine 82–82 tie** (S1 alone 78,
pre-IR). S5 *leads on the single highest-weighted axis* (C1, the owner's stated north star) via
its type-checked function-object escape hatch; S4 claws the total back on C2 (models automation)
and C9 (portability). The baseline S0 scores a respectable 67 — it aces every *safety* criterion
(C3/C5/C6/C7/C8) for free because it is just today's hand-written code, and fails only on the
*leverage* axes the owner actually cares about (C1/C4/C9). That is the honest shape of the
decision: **the fight is S4 vs S5, and the tie-breaker is the models-slice policy + portability
appetite — both owner calls, not research calls.**

---

## Deliverable 2 — Adversarial attack on the leaders

### 2.1 Test generation vs the 100% gate — is it a tautology? (the crux)

I read three real test files. The pattern (`responses`-stubbed, offline, no live network):

- **`tests/yandex/tracker/issues/test_client.py`** `test_get_deserializes_issue`: stubs `GET
  /issues/DE-1` → `{"key":"DE-1","summary":"S","type":{"key":"task"}}`, asserts `i.key == "DE-1"`
  **and `i.type == "task"`**. That second assert is load-bearing: the wire sends
  `type:{"key":"task"}` and the test asserts the model *flattens* it to `"task"` (the `KeyStr`
  ref-flattening annotation).
- **`tests/yandex/forms/surveys/test_client.py`** `test_list_drains_offset_pages`: stubs page 1 =
  **exactly 100 items** (== page_size, so "not last"), page 2 = `[{"id":"tail"}]`; asserts
  `len(out.root) == 101`, `len(responses.calls) == 2`, and **`calls[1].request.params["offset"]
  == "100"`** (the offset advanced by page_size).
- **`tests/yandex/tracker/comments/test_client.py`** `test_list_drains_pages_across_relative_cursor`:
  a 3-request `add_callback` drain asserting `id=2` then `id=3` cursors and a terminating empty
  page.

**Rendered generated test — `issues_get` (both contenders emit the same test source; the
difference is only where the fixture/assert come from):**

```python
# emit_test(issues_get)  → tests/yandex/tracker/issues/test_client.py::test_get
@responses.activate
def test_get_deserializes_issue():
    responses.add(responses.GET, f"{BASE}/issues/DE-1",
                  json={"key": "DE-1", "summary": "S", "type": {"key": "task"}}, status=200)
    i = _client().get("DE-1")
    assert isinstance(i, Issue)
    assert i.key == "DE-1" and i.type == "task"      # <-- authored expected, NOT computed
```
Under **YAML (S1/S4)** this comes from a `test: {fixture: '{"key":"DE-1",...}', assert: 'i.key ==
"DE-1" and i.type == "task"'}` block — the assert is an *unchecked string* eval'd into the test
(exactly the POC's `assert: 'out.root[0].key == "critical"'`, digest §3). Under **S5** it comes
from `Test(fixture={...}, check=lambda i: i.key == "DE-1" and i.type == "task")` — a **real Python
lambda `ty` type-checks**, so `i.typ` (typo) fails at author time.

**Rendered generated test — `surveys_list` (pagination drain):** emitted from the
`pagination:{strategy: offset, page_size: 100}` knob + a tiny `test.count` hint:

```python
# emit_test(surveys_list, strategy=offset) — the drain shape is parametric on the strategy
@responses.activate
def test_list_drains_offset_pages():
    responses.add(responses.GET, f"{BASE}/surveys",
                  json={"links": {"next": "x"}, "result": [{"id": str(i)} for i in range(100)]}, status=200)
    responses.add(responses.GET, f"{BASE}/surveys",
                  json={"links": {}, "result": [{"id": "tail"}]}, status=200)
    out = _client().list()
    assert len(out.root) == 101 and out.root[-1].id == "tail"
    assert len(responses.calls) == 2
    assert responses.calls[1].request.params["offset"] == "100"   # == page_size, from strategy semantics
```

**Verdict on the tautology (loud, as required): the risk is REAL but BOUNDED, and it is NOT a
blocker — because it decomposes into two very different things:**

1. **Tautology type A — code-vs-code (the fatal one): AVOIDABLE, and both contenders avoid it iff
   one rule is enforced.** If the test-emitter derived the *expected value* by running the
   generated code against the fixture, the test would assert "the code does what the code does" —
   vacuous, a defect per this repo's review rubric. **The mitigation is non-negotiable: the
   expected assertion MUST be authored DATA in the spec (`assert:` / `check=`), never computed.**
   The POC already does this (digest §3). So type-A is designed out — *provided the generator
   never auto-derives assertions.* Flag this as a hard generator invariant.

2. **Why the emitted tests are genuinely NON-VACUOUS (they catch real bugs):** the fixture+assert
   are authored independently of the mechanical code, **and — critically — `models.py` is
   generated from a *different* source than the ops** (datamodel-codegen from JSON-Schema, or
   hand-written; docs 05 §0.3 / 07 §0). So `assert i.type == "task"` cross-checks the
   *op-spec-driven client wiring* against the *independently-authored model* — two artifacts, not
   one. A dropped `KeyStr` flattener, a wrong `model_dump`, a broken uplink decorator stack all
   turn the test red. The pagination-drain test additionally cross-checks the op's wrapper against
   the **shared `PaginationStrategy`** (its own suite, `tests/yandex/test_pagination.py`): if the
   wrapper advanced `offset` by 1 instead of `page_size`, `assert offset == "100"` fails. **These
   are real integration assertions, not "it runs."**

3. **Tautology type B — spec-vs-reality (the residue that CANNOT be caught): pre-existing, not
   introduced by codegen.** The test stub URL (`f"{BASE}/issues/DE-1"`) is emitted from the *same*
   `path:` field as the client's `@uplink.get("issues/{key}")`. So no emitted test can catch "the
   path is actually `issue/{key}` on the real API" — both move together. **But the current
   hand-written suite has the identical blind spot:** its stubs are human-authored fixtures, not
   live captures; an offline `responses` test *structurally* cannot detect path/verb-vs-reality
   drift. Codegen is at most *marginally* worse (one string instead of two typed-twice), and
   arguably *better* (single source-of-truth path, reviewed once against the vendored API docs).
   **The correct fix for type-B is not "hand-write the test" — it is a contract test
   (Schemathesis) against the vendored API doc / live API, i.e. the Axis-C internal-OpenAPI lever
   the research already surfaced (doc 05 §Axis C).** That is the *only* thing that catches
   spec-vs-reality drift, and it is equally available to hand-written and generated code.

**Bottom line:** generated tests are non-vacuous for every layer that carries logic (models,
pagination, `Ack`, `require_found` guards, body-dump, internal/public split); the tautological
residue is confined to the HTTP path/verb strings and is a property of *offline stubbing*, not of
*codegen*. **S5 has a small, real edge**: type-checked `check=` assertions catch assert-typos at
author time that YAML's stringly-typed `assert:` catches only at test-run time. The escape-hatch
ops still need hand-written tests for their hand-written Python (doc 07 §3.4) — "`handler:` code
needs `handler:` tests" — but that is unchanged from today.

### 2.2 The models-slice decision

**Grounded reality:** of 310 `APIModel` classes across 52 files, only **2 files** carry a
`model_validator/field_validator` (`forms/questions`, `wiki/grids`), **6** use `extra="allow"`,
**7** have a `@property/@computed_field`. The logic-bearing surface is **small and localized** —
generously ~10-15 files (~20% of files, ~10% of classes). datamodel-codegen (v0.68.1, MIT, active
— doc 03) cleanly emits the pure-data ~80% including `Field(description=...)` → MCP schema text
(doc 09 §4 confirms it on `Issue`/`IssueCreate`).

**Recommendation: HYBRID, and it works — generate the plain ~80%, hand-write the ~20%.**
datamodel-codegen emits field skeletons; the ~10-15 validator/`extra=allow`/computed models keep a
hand-authored `# region` block the generator preserves (doc 07 op-7, doc 08 op-12) — or are simply
hand-written in full (only ~15 files). This is not a workaround; it is the natural split, because
the validator (`QuestionMove._require_target_for_position`) is *business logic*, and doc 02 §9
proves it must stay Python.

**But the split-brain caveat is the real decider, and it points at the authoring surface:**
- **YAML ops + JSON-Schema models = two formats, ONE family (both inert declarative data).**
  Acceptable. datamodel-codegen's 85% and the YAML op-spec coexist cleanly. → S1/S4 pairs
  *naturally* with datamodel-codegen.
- **Python-descriptor ops + JSON-Schema models = genuine split-brain** (Python + JSON-Schema, two
  languages) — doc 08 §60-vs-85 names this as "the real argument against S5." S5's *coherent*
  choice is to keep models hand-written Python (one language, ~55% cap). It *could* adopt
  datamodel-codegen too, but only by accepting the split-brain.

So the models-slice decision is *not independent* of the authoring-surface decision: **if you want
the datamodel-codegen 85%, author ops in YAML; if you want everything in one language (typed
Python end-to-end), author in Python and cap at ~55% with models hand-written.** Both are
internally coherent; neither is dominated.

### 2.3 Escape-hatch contagion — where does it stop paying?

**The break-even is per-op and sharp:** the escape hatch pays for itself as long as the generator
still emits the *majority* of an op. When ≥2 of the 3 surfaces (client/cli/mcp) need a hand-written
handler, the spec entry degrades to **pure registration** (doc 08 §Escape-hatch: "a type-safe
`add_typer`/`mcp.mount` list") — at that point you author the spec entry *and* all the handlers,
i.e. strictly *more* surface than just hand-writing the op outside the generator. **Op #9 (upload)
is exactly this pathology:** client `handler=`, CLI `cli=`, and effectively MCP too (doc 08 §Part-2
#9 flags the 3-surface contagion honestly).

**Counting against the real ~228 ops** (bespoke-residue inventory, digest §6 + doc 02, measured
this pass):
- Genuine hand-written **Python handlers on ≥1 surface**: ~15-30 ops (~7-13%) — matches the
  research's "~15% residue" (doc 05 §0.5). Sources: pagination drains are **declarative** (the
  strategy enum, ~15-20 list ops — NOT handlers); polling is **declarative** (`poll:` knob, ~4-5
  ops); `set_permissions` is a **declarative flag** (`raw_dict`, 1 op, the only ARCH-3 allowlist
  entry — `tests/test_architecture.py:457-463`). The true Python handlers are: upload pipelines
  (wiki attachments + likely forms file/image, ~2-3), model validators (2 files), and rich-flag
  CLI commands (issues_create/update, entities create, ~a handful).
- Ops degraded to **pure registration** (≥2 surfaces hand-written): only the **upload pipelines,
  ~2-3 ops (~1%)**. Everything else needs a handler on *exactly one* surface (a CLI rich-flag
  command, or a model validator that isn't even an op-layer handler).

**So the escape hatch pays for itself on ~98-99% of ops.** The ~1% pure-registration ops (uploads)
are the honest place to admit "this op is just hand-written, the spec entry is a formality" — and
that is fine; the design *degrades gracefully* rather than blocking (doc 07 §3.2, doc 09 Part-S2
#9: for #9 the escape hatch "is not optional, it is the entire implementation" — true under *every*
strategy, including OpenAPI). The contagion is real but rare.

### 2.4 The `entities` god-resource (3060 LOC, 30 tools, `set_permissions` exception)

**Generate it — but last.** It is big, not irregular: its 30 sub-ops
(`entities_comments_create`, `entities_checklists_edit_item`, …) each follow the *standard*
per-op shapes (doc 02 §17), mirroring would-be standalone resources, grouped by `# ---- comments
----` banners. Only one op (`set_permissions`) is the raw-dict exception, already handled by the
declarative `raw_dict`/`allowlisted` flag that auto-emits the `ARCH3_BODY_DICT_ALLOWLIST` entry
(doc 07 op-12, doc 08 op-12).

- **Cost of generating:** a ~600-700-line spec file that is itself hard to review (doc 07 §3.5),
  plus the `section:`/`group:` banner feature and the `<res>_<sub>_<verb>` flat-naming rule — both
  already designed. Payoff: it is the **single biggest LOC win** (3060 LOC → one spec), and
  ARCH-1 op-parity becomes a free generator-correctness check for it.
- **Cost of leaving it hand-written:** 3060 LOC stays unmanaged forever and becomes the one place
  drift accumulates; the "everything is generated" story gets a permanent asterisk. The escape
  hatch *permits* this (doc 05 §4.5), so it's a safe fallback if the 700-line spec proves
  unreviewable.

**Recommendation:** generate it, but sequence it **last** in the migration, after the generator is
proven on ~10 simple resources — so the god-resource is a *validation* of a mature generator, not
its first customer.

### 2.5 What breaks at 200 resources / an unforeseen op-shape (C1 pressure test)

- **S1 (yaml template-direct):** template branch-ladder rot — `mcp.py.jinja` becomes an untyped
  `{% if pagination %}{% elif raw_dict %}{% elif handler %}…` forest in *shared* files (a mistake
  in the #21 arm can regress the 85%), with **no exhaustiveness guarantee** (miss `cli.py.jinja`
  → silently emit a resource with no CLI command, caught only by ARCH-1 *if* wired). Plus
  stringly-typed embedded Python (`extract: page.reslut` typo → emit-time failure) and prose
  duplication wanting an include mechanism (doc 07 §3.3, §3.5). **C1 degrades → this is the reason
  to evolve to S4.**
- **S4 (yaml typed-IR):** an unforeseen shape = one `ty`-checked IR node + emitter clauses;
  `assert_never` **forces** every emitter to handle it *at type-check time* (doc 07 §3.3). Failure
  mode is benign: "the IR has 25 node types and the lowering step is the thing to learn" — typed,
  localized. **Best C1 story.**
- **S5 (py-descriptor):** the descriptor library becomes a *second framework* contributors must
  learn; **import-time coupling / circular-import risk** (spec.py→models→handlers→client) is S5's
  most likely *practical* scaling pain (doc 08 §failure-mode-2); escape-hatch creep means some
  ragged ops carry a descriptor *and* a handler (more surface than raw code). **But** the
  unforeseen shape is *always expressible today* via a type-checked handler, zero framework change
  — the strongest "never blocks" property (doc 08 §Extensibility).
- **S0:** uniform high cost (every op full hand-authoring); no cliff, no leverage.
- **S2/S3:** S2 needs a new `x-ext` + bespoke emitter per shape (no better than YAML, foreign
  format); S3 adds a dict entry but the guarantees are already forfeited.

**C1 verdict:** S4 and S5 both pass the pressure test (typed IR / typed handler); S1-alone
degrades past ~5 op-shapes (the 20-op pool already exceeds this); S0 is leverage-free.

---

## Deliverable 3 — Recommendation + genuine open decisions

### My reasoned recommendation

1. **Contender: author in YAML, build S1 and evolve to S4** (template-direct now, extract the typed
   IR at the first painful op-shape or the first 2nd-consumer) — with the explicit caveat that
   **S5 is a legitimate co-leader (82–82), not a fallback.** I lean YAML/S4 over S5 on three
   grounds, none decisive alone: (a) the models-slice hybrid (datamodel-codegen, ~85%, doc 03
   re-validated) pairs *naturally* with a data-family authoring surface and *split-brains* with a
   Python one (§2.2); (b) the owner's north star explicitly says "**universal, template-driven,
   portable to ALL resources and future**," and YAML is language-portable where a Python descriptor
   couples the spec to Python (C9); (c) the ~228-op pool is ragged (§2.3), and datamodel-codegen
   claiming the 8.1k-LOC models slice matters more at that scale than S5's type-checked-spec edge.
   **If the owner weights end-to-end type-safety and refactor-safety above portability + the
   models-85%, flip to S5 — its C1/C5 lead on the north-star axis is real and the total is tied.**
2. **Template-direct vs IR: start S1, extract S4 later.** The migration S1→S4 is *additive*, not a
   rewrite (doc 07 §3.3); don't pay for the IR before the template ladder actually hurts.
3. **Models-slice policy: HYBRID.** datamodel-codegen for the pure-data ~80%; hand-write the ~10-15
   validator/`extra=allow`/computed models in preserved regions (§2.2). The logic-bearing surface
   is small and localized (measured: 2 validator files, 6 `extra=allow`, 7 computed).
4. **Migration order:** **tracker first** (32 resources, largest win), **simplest shapes first**
   (get/list/delete), a **`--check` CI gate from commit #1** (regenerate → assert no-diff; this is
   mandatory or hand-edits to generated files rot — doc 07 §3.4), the **`entities` god-resource
   LAST** (§2.4), the 100% gate green throughout. Add the **Axis-C contract test (Schemathesis
   over compiled OpenAPI) opportunistically** — it is the only thing that closes the §2.1 type-B
   tautology residue.
5. **Hard generator invariant to write down now:** *the test-emitter never computes expected
   assertions; every `assert:`/`check=` is authored data* (§2.1). Without this rule the whole test
   tier is vacuous.

### Genuine open OWNER decisions (not settled by research — concrete either/or forks)

1. **Authoring surface — YAML (S1/S4) vs Python descriptor (S5).** THE headline fork, a real
   82–82 tie. YAML: portable, pairs with datamodel-codegen for ~85%, but stringly-typed embedded
   Python + needs a schema-validation layer. Python: `ty`-checked spec, IDE completion,
   refactor-safe, function-object escape hatch (best C1/C5), but Python-coupled and caps at ~55%
   (models hand-written). *Trade:* portability + models-automation (YAML) vs end-to-end type-safety
   (Python).
2. **Pay for the typed IR now (S4) or start template-direct (S1) and extract later.** *Trade:*
   time-to-first-value (S1, legible templates immediately) vs C1 future-proofing (S4, typed
   exhaustiveness) — bearing in mind the extraction is additive.
3. **Models source of truth — adopt datamodel-codegen (JSON-Schema → ~85%) or keep models
   hand-written (~55%).** *Trade:* the 8.1k-LOC automation win + a maintained JSON-Schema artifact
   that *can't host validators inline* (hybrid regions needed) vs native validators in one language
   at a lower compression. Coupled to #1.
4. **Internal OpenAPI compile (Axis C) now or YAGNI.** *Trade:* emitting OpenAPI as a byproduct
   unlocks `FastMCP.from_openapi` validation + Schemathesis contract tests (which *close the
   spec-vs-reality tautology residue*, §2.1) at the cost of a second internal artifact, vs defer
   until a 2nd consumer actually appears.
5. **`entities` god-resource — generate it (biggest LOC win, a ~700-line spec file) or leave it
   hand-written (escape hatch permits it, dents "everything is generated").** *Trade:* uniform
   coverage + ARCH-1 auto-check vs one reviewable-but-large spec file.
6. **Ratify the success metric.** The research assumes "fewer *authored* lines" (committed
   generated files stay; repo LOC ~flat/grows by the generator; authored surface −55-85%). Confirm
   the owner accepts committed generated files rather than expecting "fewer repo files" (which only
   the already-rejected runtime path delivers — doc 01 §1 reframing).
