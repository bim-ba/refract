# refract — design research & validation record

These are the working research notes that produced refract's design (`../design.md`). They are the
**rationale** ("why this architecture, not Fern/runtime/…") and the **validation** ("does the spec
format hold against real public APIs?"). Kept as a record of the decision-making; not polished
end-user docs. The frozen design blueprint they converge on is **`../design.md`** (spec v2 FINAL).

## The chain

| Doc | What it establishes |
|---|---|
| `00-evaluation-rubric.md` | The 9 weighted criteria (C1 extensibility ×3 = north star) every option is scored against. |
| `01-prior-session-digest.md` | Recovered prior exploration: the S1–S6 strategy taxonomy, the Fern spike (4150 LOC/2 endpoints → rejected), the YAML→emitters POC. |
| `02-codebase-anatomy-and-op-pool.md` | ycli's real structure + a pool of 20 real operations (the byte-targets the generator must reproduce). |
| `03-external-landscape.md` | Prior art: Fern / Stainless (dead) / Speakeasy / TypeSpec / Smithy — why refract owns its generator; `datamodel-code-generator` = the one reusable external piece. |
| `04-multisurface-prior-art.md` | Runtime proxies (FastMCP.from_openapi) vs committed-source; why IR+templates→committed-source is the universal pattern. |
| `05-strategy-design-space.md` · `06-oppool-brief.md` | The strategy-registry design space + the operation-pool brief for the bake-off. |
| `07-bakeoff-yaml.md` · `08-bakeoff-python-descriptor.md` · `09-bakeoff-openapi-and-runtime.md` | Head-to-head bake-off of the candidate spec forms (S4 YAML→IR wins; S5 Python-descriptor eliminated by language-agnosticism; OpenAPI/runtime ruled out). |
| `10-synthesis-and-adversarial-review.md` | Synthesis + adversarial review: the test-tautology bound, the models-slice hybrid, S4 chosen. |
| `11-testgen-stack.md` | The test stack: `responses`+pytest (in-gate, deterministic) vs `schemathesis` (off emitted OpenAPI); `hypothesis`/`faker` as per-language realizations. |
| `12-architecture-language-agnostic.md` | The language-agnostic architecture (spec → IR → per-language×surface emitters). |
| `13-openapi-interop.md` | Bidirectional OpenAPI interop (emit valid 3.1 + `x-refract-*`; import `--scaffold`). |
| `14-refract-design-spec.md` · `15-refract-spec-frozen.md` | The first full design spec, then frozen v1 for stress-testing. |
| `16-stress-test-synthesis.md` | **Consolidated 14-API stress test** → the spec-v2 revisions (2 new registries Async/Error-model, unions, cross-file ref, model-handler, body-encoding family, scope non-goals). |
| `stress/*.md` (14) | Per-API stress reports: projecting the frozen spec onto Yandex 360 ×2, Yandex Cloud, GitHub REST + GraphQL, Stripe, AWS S3, OpenAI, Kubernetes, Slack, Twilio, Google Calendar, Elasticsearch, Notion — where each fits / near-misses / genuine gaps. **Verdict: the architecture HOLDS** (gaps = registry members, not redesign). |
| `_openapi_issues_create_*.yaml` | Worked OpenAPI-emit examples (pure-data vs `x-refract-*` extended) for the interop design. |

The stress test (`16` + `stress/`) is the load-bearing evidence that the strategy-registry design
scales: nearly every gap across 14 real APIs is "add a member to an existing registry" or "add one of
two new registries," not a redesign. That is why the [roadmap] backlog in `../roadmap.md` is purely
additive.
