# Stress test: refract spec vs. AWS S3 (Query/REST) API

Baseline: `15-refract-spec-frozen.md` (v1 frozen). Target API: Amazon S3 REST API. All claims
below are grounded in AWS docs fetched 2026-07-14 (see Sources); nothing here relies on training-data
memory of the S3 API.

## Sources (retrieved 2026-07-14)

- SigV4 canonical request / Authorization header: https://docs.aws.amazon.com/general/latest/gr/sigv4_signing.html ,
  https://docs.aws.amazon.com/AmazonS3/latest/API/sig-v4-authenticating-requests.html
- SigV4 presigned URL (query-string auth): https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-query-string-auth.html
- SigV4 chunked/streaming upload signing: https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-streaming.html
- ListObjectsV2 (full request/response XML + examples): https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html
- ListBuckets: https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListBuckets.html
- CompleteMultipartUpload (full request/response XML + "200 OK with embedded error" example):
  https://docs.aws.amazon.com/AmazonS3/latest/API/API_CompleteMultipartUpload.html
- CreateMultipartUpload / UploadPart: https://docs.aws.amazon.com/AmazonS3/latest/API/API_CreateMultipartUpload.html ,
  https://docs.aws.amazon.com/AmazonS3/latest/API/API_UploadPart.html
- DeleteObjects (batch XML): https://docs.aws.amazon.com/AmazonS3/latest/API/API_DeleteObjects.html
- Error response XML: https://docs.aws.amazon.com/AmazonS3/latest/API/ErrorResponses.html
- Virtual-hosted vs. path-style: https://docs.aws.amazon.com/AmazonS3/latest/userguide/VirtualHosting.html
- GetObject / Range / 206: https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html

## Operations picked (12)

1. `ListBuckets` — `GET /` (account-level, no bucket in host)
2. `ListObjectsV2` — `GET /{bucket}?list-type=2` (paginated)
3. `GetObject` — `GET /{bucket}/{key}` (Range → 200/206, raw-byte body)
4. `PutObject` — `PUT /{bucket}/{key}` (raw-byte body)
5. `DeleteObject` — `DELETE /{bucket}/{key}` (bodyless write)
6. `DeleteObjects` — `POST /{bucket}?delete` (batch XML request+response, per-key outcomes)
7. `CreateMultipartUpload` — `POST /{bucket}/{key}?uploads`
8. `UploadPart` — `PUT /{bucket}/{key}?partNumber=N&uploadId=X` (raw-byte body, ETag echoed as header)
9. `CompleteMultipartUpload` — `POST /{bucket}/{key}?uploadId=X` (XML body; **200-with-embedded-`<Error>`** quirk)
10. `AbortMultipartUpload` (implied 4th multipart step, for orchestration discussion)
11. Multipart upload **as a whole** (composite/orchestrated operation)
12. Presigned URL generation (SigV4 query-string variant — not an HTTP call at all)

## Per-operation, per-axis classification

| Op | auth | pagination | body | operation/path | responses/errors | models/types | tests |
|---|---|---|---|---|---|---|---|
| ListBuckets | GAP* | native (mechanics) | n/a | native | GAP (XML codec) | GAP (XML) | GAP (blocked on codec) |
| ListObjectsV2 | GAP* | native (mechanics; Cursor-shaped) | n/a | GAP (bucket-in-host) | GAP (XML codec) | GAP (XML, repeated-element arrays) | GAP (blocked on codec) |
| GetObject | custom (empty-body GET) | n/a | n/a | GAP (bucket-in-host) | **GAP (no raw-bytes response type; dynamic content-type)** | n/a | GAP (Raw escape hatch only) |
| PutObject | GAP (body hash / chunked signing couples auth↔body) | n/a | **near-miss** (raw bytes ≠ `Base64`) | GAP (bucket-in-host) | GAP (XML error codec) | n/a | mostly skip/Raw |
| DeleteObject | custom | n/a | native (bodyless) | GAP (bucket-in-host) | native-ish (204, Ack(ident=key) fits) | n/a | native (WrapsAck) once auth solved |
| DeleteObjects | GAP (body hash) | n/a | GAP (XML batch body) | GAP (bucket-in-host) | **GAP (200-wrapped per-key errors, Slack-shaped)** | GAP (XML) | GAP (ReturnsError vacuous/wrong) |
| CreateMultipartUpload | GAP (body hash) | n/a | native (bodyless) | GAP (bucket-in-host) | GAP (XML codec) | GAP (XML) | GAP (blocked) |
| UploadPart | GAP (chunked signing) | n/a | near-miss (raw bytes) | GAP (bucket-in-host) | GAP (ETag returned as **header**, not body) | n/a | skip/Raw |
| CompleteMultipartUpload | GAP (body hash over XML) | n/a | GAP (XML body) | GAP (bucket-in-host) | **GAP (200 OK can carry a failure `<Error>` body)** | GAP (XML) | **GAP (ReturnsError test would be wrong for this op)** |
| Multipart orchestration (create→N×part→complete) | — | — | — | **GAP (no multi-op composite concept)** | — | — | — |
| Presigned URL | **GAP (not header-mutation; not even an HTTP call)** | n/a | n/a | **GAP (no operation shape at all — no request sent)** | n/a | n/a | n/a |

\*GAP for SigV4 in general, elaborated below — even the "simple" no-body GET case depends on an
undefined `Custom` handler contract (does it see the full canonical request or only headers?).

## Deep dives on the three prime suspects

### 1. Auth — AWS SigV4 vs. "auth wires headers"

refract's registry (`HeaderToken`/`Bearer`/`ApiKey`/`Basic`/`QueryToken`/`OAuth2`/`Custom(handler:)`)
is built around the premise that an auth strategy computes **headers** from **secrets**, independent
of the rest of the request. SigV4 breaks that premise at three depths:

- **Depth 1 (mild — could be `Custom` if the contract were richer):** the canonical request is
  `Method\nCanonicalURI\nCanonicalQueryString\nCanonicalHeaders\nSignedHeaders\nHex(SHA256(payload))`.
  Signing needs the fully-assembled method, path, **and sorted query string**, not just a header
  dict. The frozen spec never defines what a `Custom` handler receives — if it's given the whole
  outgoing request object (method/url/headers/body) *before* send, SigV4 for bodyless/short-body
  requests is expressible. If (as "auth wires headers" implies) it only gets to contribute headers
  given static secrets, it is not.
- **Depth 2 (real GAP):** for `PutObject`/`UploadPart`/`CompleteMultipartUpload` the payload hash is
  part of the canonical request, so auth depends on the **body strategy's output**, cutting across
  the auth/body registry boundary the spec treats as orthogonal.
- **Depth 3 (unambiguous GAP):** chunked/streaming SigV4 (`x-amz-content-sha256:
  STREAMING-AWS4-HMAC-SHA256-PAYLOAD`, `Content-Encoding: aws-chunked`) embeds a **per-chunk
  signature inside the body stream itself** (`10000;chunk-signature=<sig>\r\n<data>\r\n...`), each
  chunk's signature derived from the previous chunk's. This is not "compute a header" — it's a
  stateful body *transcoder* that only auth logic can produce. No registry axis in the frozen spec
  models this.
- **Presigned URLs are a fourth, disjoint case:** query-string SigV4 doesn't sign a request the
  client is about to send — it signs a request *someone else* will send later, and the payload hash
  is replaced by the constant `UNSIGNED-PAYLOAD`. The "operation" here produces a **URL string**,
  never touches the transport, and has no `responses:`. It doesn't fit the operation.yaml shape at
  all (see below).

**Verdict: GAP**, not cleanly `Custom`. The spec needs (a) a defined `Custom` handler contract that
receives the full assembled request, and (b) an acknowledgment that some auth strategies must
co-transform the body (streaming SigV4), which means auth and body can't stay fully independent
registries for every API.

### 2. Responses — XML, not JSON

S3 returns `Content-Type: application/xml` bodies for essentially every read/list/error/batch
operation (`ListBucketResult`, `ListAllMyBucketsResult`, `CompleteMultipartUploadResult`, `<Error>`),
each with an XML namespace (`xmlns="http://s3.amazonaws.com/doc/2006-03-01/"`), and repeated
sibling elements as its array convention (`<Contents>...</Contents><Contents>...</Contents>`, not a
JSON array). The frozen spec's neutral type system is explicitly "JSON-Schema-aligned" and OpenAPI
3.1 (which IS JSON Schema) is the interop target — there is no `content-type`/codec concept anywhere
in the spec; the whole pipeline (models, `responses:`, `PropertyParse`/`PropertyRoundtrip` tests,
OpenAPI emission) implicitly assumes the wire format is JSON.

The neutral type system's *shape* vocabulary (`string|integer|list<T>|ref<Model>|optional|enum`) is
actually flexible enough to describe XML-shaped data structurally. What's missing is the **codec**:
nothing (de)serializes a `ref<Model>` to/from XML, nothing distinguishes XML attributes from child
elements, and nothing models "array = N repeated sibling tags with no wrapper" vs. JSON's `[...]`.
Two more GAPs discovered beyond what section 7 already flags for *bodies*:
- **Response side has no equivalent gap-list entry at all** — section 7 calls out XML *request*
  bodies as a probe item but responses (`200: {model: ...}`) has no codec escape valve either.
- `GetObject`'s 200/206 success response isn't XML *or* JSON — it's a raw byte stream with a
  dynamic, object-supplied `Content-Type`. `responses:` has no "raw passthrough, no model" option;
  every entry in the map is assumed to resolve to a parsed model.

**Verdict: confirmed GAP.** Needs a per-`_resource.yaml` or per-operation `content_type:`/codec
concept, XML-specific type annotations (attribute vs. element, namespace, unwrapped-array), and a
raw/binary response variant symmetric to the existing `Base64` body-write strategy.

### 3. Multipart upload — orchestration and a body/auth/response trifecta

`CreateMultipartUpload → N×UploadPart → CompleteMultipartUpload [→ AbortMultipartUpload on failure]`
is precisely the shape section 10 already predicts as a gap ("upload = create-session→PUT→
finish→attach cannot be one OpenAPI operation → `Custom` handler + partial coverage") — this
stress test **confirms** that prediction is correct and shows it's not hypothetical:
- Each step maps to *an* operation.yaml individually, but the ergonomic SDK/CLI method a user wants
  (`upload_file(path)`: split into parts, upload each, track `ETag`s, assemble, retry/abort on
  failure) spans three-plus operation files with response fields from step *N* becoming request
  fields of step *N+1* (`UploadPart`'s response `ETag` header feeds `CompleteMultipartUpload`'s XML
  `<Part><ETag>` list). refract has no "composite operation"/workflow concept above the single
  operation file — only a per-operation `handler:` escape hatch, which doesn't span files.
- `CompleteMultipartUpload` independently breaks the `responses:` status-code map: **AWS's own docs
  give a worked example of an HTTP `200 OK` whose XML body is a failure `<Error>`** ("a `200 OK`
  response can contain either a success or an error... make sure to design your application to
  parse the contents of the response"). This is S3's version of the exact "200-wrapped errors
  (Slack `ok:false`)" gap the spec already anticipates in section 9 — an auto-generated
  `ReturnsError` test keyed off 4xx/5xx status would be **vacuous for the real failure mode of this
  operation** and a `ParsesModel`-only 200 test would be **actively wrong** (asserts success on a
  body that says otherwise).
- `UploadPart`'s meaningful output (the part's `ETag`) comes back as an HTTP **header**, not a body
  field — fine per se (refract already supports `in: header` request params) but there's no
  equivalent "extract this from a response header into the derived return value" concept; today
  `responses:` only names a body `model`.

**Verdict: confirmed GAP**, exactly as the spec predicted for orchestration, plus two more specific
findings (200-wrapped failure, header-carried response data) the frozen spec doesn't yet name.

## Secondary findings (near-misses worth flagging)

- **Bucket-in-host breaks the path model.** Virtual-hosted-style (`{bucket}.s3.{region}.
  amazonaws.com`, now mandatory for directory buckets, recommended for all) puts a per-request
  dynamic value in the **hostname**, not the path. The frozen spec's `path:` templating (section 5)
  only shows `{param}` inside a path string under a fixed resource-level `base_url:`; there's no
  host-templating concept. Path-style (`s3.amazonaws.com/{bucket}/{key}`) still works for
  pre-Sept-2020 buckets and *would* fit refract's existing model natively — but it's the
  AWS-deprecated form, so "native" here only covers a shrinking, non-recommended subset of the API.
- **`Base64` body strategy is a near-miss for `PutObject`/`UploadPart`.** S3 sends raw bytes
  directly as the HTTP body (no JSON envelope, no base64 text-encoding) — semantically distinct
  from `Base64` (which implies encoding binary as a base64 *string field* inside a JSON body, the
  typical use case the name suggests). A `RawBytes`/`Binary` body strategy is a one-line registry
  addition, not a structural gap — but worth noting the existing name is misleading for this shape.
- **`DeleteObjects` batch semantics don't fit `Ack`.** The spec's `ack:` factory (single
  `ident`/`on: key` from one bodyless write) has no shape for "N keys in, N independent per-key
  success/error results out in one call" — `Raw` test strategy is the only real escape hatch.

## Verdict

Of 12 probed operations/axes, **auth (SigV4), responses (XML+raw-bytes), and multipart
(orchestration + 200-wrapped-error) are all confirmed GAPs**, not `Custom`-expressible with the
frozen spec's current contracts. Presigned URLs don't fit the operation model at all. The spec's own
section 7/10/9 predictions (XML bodies, multi-step orchestration, 200-wrapped errors) are each
independently **validated** by this stress test — S3 is close to a worst-case combination of all
three simultaneously. refract as frozen is JSON-body + simple-header-auth-centric; a "query/REST"
API family (AWS's own term for this style, shared by every non-JSON-protocol AWS service) is a
genuine second protocol family the spec would need to support as a first-class citizen, not a
one-off `Custom` handler.
