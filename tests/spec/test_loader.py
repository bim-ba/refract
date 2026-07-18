from pathlib import Path

import pytest

from refract import ir
from refract.ir.model import ObjectModel, RootListModel
from refract.ir.types import LiteralType, RefType, ScalarType, UnionType
from refract.spec import nodes
from refract.spec.loader import SpecError, SpecLoader, _field, _param, _resource, _response_model

_EX = Path(__file__).resolve().parent.parent.parent / "examples" / "ycli-tracker"


def test_loads_me_as_neutral_ir():
    res = SpecLoader.load(_EX / "tracker" / "me" / "resource.yaml")
    assert res.domain == "tracker" and res.resource == "me"
    assert not hasattr(res, "base_url")  # base_url moved to client.yaml
    me = res.model("Me")
    assert isinstance(me, ObjectModel)  # narrow the model union before field access
    uid = me.fields[0]
    assert uid.name == "uid"
    assert uid.type == ScalarType(scalar="integer")  # neutral, NOT "int | None"
    assert uid.optional is True
    assert uid.default is None  # implied null-default is the TypeMapper's job now


def test_me_model_is_object_variant():
    res = SpecLoader.load(_EX / "tracker" / "me" / "resource.yaml")
    assert isinstance(res.model("Me"), ObjectModel)


def test_priorities_model_variants_and_ref_field():
    res = SpecLoader.load(_EX / "tracker" / "priorities" / "resource.yaml")
    plist = res.model("PriorityList")
    assert isinstance(plist, RootListModel)
    assert plist.item == "Priority"
    assert isinstance(res.model("Priority"), ObjectModel)
    create = res.model("PriorityCreate")
    assert isinstance(create, ObjectModel)
    name = create.fields[1]
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


def test_load_missing_file_raises_spec_error():
    with pytest.raises(SpecError):
        SpecLoader.load(Path("/nonexistent/resource.yaml"))


def test_load_client_config_with_single_header_auth(tmp_path: Path):
    client_yaml = tmp_path / "client.yaml"
    client_yaml.write_text(
        """
name: widgets
server:
  base_url: https://api.widgets.example/v1
auth:
  bearer_token:
    kind: header
    header: Authorization
    template: "Bearer {token}"
    inputs:
      token: {env: WIDGETS_TOKEN}
""",
        encoding="utf-8",
    )
    config = SpecLoader.load_client_config(client_yaml)
    name, scheme = config.auth[0]
    assert name == "bearer_token"
    assert isinstance(scheme, ir.HeaderAuth)
    assert scheme.header == "Authorization"
    assert scheme.template == "Bearer {token}"
    assert tuple((i.name, i.env) for i in scheme.inputs) == (("token", "WIDGETS_TOKEN"),)


def test_load_non_mapping_top_level_raises_spec_error(tmp_path: Path):
    resource_yaml = tmp_path / "resource.yaml"
    resource_yaml.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(SpecError, match="top level must be a mapping"):
        SpecLoader.load(resource_yaml)


def test_load_client_config_validation_error_raises_spec_error(tmp_path: Path):
    client_yaml = tmp_path / "client.yaml"
    client_yaml.write_text(
        """
name: widgets
server:
  base_url: https://api.widgets.example/v1
auth:
  bearer_token:
    kind: header
    header: Authorization
    # missing required 'template' and 'inputs' keys -> pydantic ValidationError
""",
        encoding="utf-8",
    )
    with pytest.raises(SpecError, match="client config failed validation"):
        SpecLoader.load_client_config(client_yaml)


def test_operation_without_2xx_response_raises_spec_error(tmp_path: Path):
    resource_yaml = tmp_path / "resource.yaml"
    resource_yaml.write_text(
        """
domain: t
resource: m
security: s
operations:
  - name: get
    method: GET
    path: p
    operationId: get
    responses:
      404: {model: Error}
    mcp:
      name: get
      safety: RO
      title: t
      documentation: d
""",
        encoding="utf-8",
    )
    with pytest.raises(SpecError, match="'get' has no 2xx response"):
        SpecLoader.load(resource_yaml)


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


def test_optional_path_param_raises_spec_error():
    """I2: a path param is always required (it fills a `{...}` URL slot). Allowing `optional: true`
    on it is a representable illegal state: the non-CLI surfaces append `body: <model>` (no default)
    after the path decls, so a defaulted path param before the body renders a required-after-default
    `SyntaxError`. Reject it at the boundary instead."""
    with pytest.raises(SpecError, match=r"path param.*optional|optional.*path"):
        _param(nodes.ParamSpec(name="thing_id", loc="path", optional=True))


def test_defaulted_path_param_raises_spec_error():
    with pytest.raises(SpecError, match=r"path param.*default|default.*path"):
        _param(nodes.ParamSpec(name="thing_id", loc="path", default="x"))


def test_required_path_and_optional_query_param_load():
    """Positive control: a required path param and an optional query param are both fine."""
    path = _param(nodes.ParamSpec(name="thing_id", loc="path"))
    query = _param(nodes.ParamSpec(name="notify", loc="query", optional=True))
    assert path.loc == "path" and path.optional is False
    assert query.loc == "query" and query.optional is True


def test_undiscriminated_oneof_lowers_to_union_of_mixed_type_exprs():
    """Variant 2: an undiscriminated `oneof` (no discriminator) mixes a scalar + a ref."""
    field = _field(
        nodes.FieldSpec(
            name="source",
            oneof=nodes.OneOfSpec(variants={"id": "string", "full": "ref<Customer>"}),
        )
    )
    assert field.type == UnionType(
        variants=(ScalarType(scalar="string"), RefType(target="Customer")), discriminator=None
    )


def test_discriminated_oneof_lowers_to_ref_union_with_discriminator():
    field = _field(
        nodes.FieldSpec(
            name="block",
            oneof=nodes.OneOfSpec(
                discriminator="type",
                variants={"paragraph": "ref<Paragraph>", "heading_1": "ref<Heading1Block>"},
            ),
        )
    )
    assert field.type == UnionType(
        variants=(RefType(target="Paragraph"), RefType(target="Heading1Block")),
        discriminator="type",
    )


def test_discriminated_oneof_with_non_ref_variant_raises():
    """A discriminated variant that is a scalar (not `ref<Model>`) is rejected fail-loud."""
    spec = nodes.FieldSpec(
        name="block",
        oneof=nodes.OneOfSpec(discriminator="type", variants={"a": "string", "b": "ref<B>"}),
    )
    with pytest.raises(SpecError, match="must be a ref"):
        _field(spec)


def test_single_variant_oneof_is_rejected():
    """The UnionType `>= 2` validator fires, re-wrapped as SpecError (covers the except arm)."""
    spec = nodes.FieldSpec(name="x", oneof=nodes.OneOfSpec(variants={"only": "string"}))
    with pytest.raises(SpecError, match="2 variants"):
        _field(spec)


def test_field_with_both_type_and_oneof_raises():
    spec = nodes.FieldSpec(
        name="block",
        type="string",
        oneof=nodes.OneOfSpec(discriminator="type", variants={"a": "ref<A>", "b": "ref<B>"}),
    )
    with pytest.raises(SpecError, match="exactly one of 'type' and 'oneof'"):
        _field(spec)


def test_field_with_neither_type_nor_oneof_raises():
    with pytest.raises(SpecError, match="needs 'type' or 'oneof'"):
        _field(nodes.FieldSpec(name="block"))


def test_root_list_without_item_raises_spec_error(tmp_path: Path):
    resource_yaml = tmp_path / "resource.yaml"
    resource_yaml.write_text(
        """
domain: t
resource: m
security: s
operations: []
models:
  - name: X
    kind: root_list
""",
        encoding="utf-8",
    )
    with pytest.raises(SpecError, match="root_list requires 'item'"):
        SpecLoader.load(resource_yaml)


def _minimal_op() -> nodes.OperationSpec:
    """A minimal spec op so a `ResourceSpec` validates (ResourceSpec.operations is required)."""
    return nodes.OperationSpec(
        name="list",
        method="GET",
        path="blocks",
        operationId="blocks_list",
        responses={200: nodes.ResponseSpec(model="Block")},
        mcp=nodes.McpSpec(
            name="blocks_list", safety="RO", title="List", documentation="List blocks."
        ),
    )


def _paragraph() -> nodes.ModelSpec:
    return nodes.ModelSpec(
        name="Paragraph", fields=[nodes.FieldSpec(name="text", type="string", optional=True)]
    )


def _heading() -> nodes.ModelSpec:
    return nodes.ModelSpec(
        name="Heading1Block", fields=[nodes.FieldSpec(name="text", type="string", optional=True)]
    )


def _block_with(variants: dict[str, str]) -> nodes.ModelSpec:
    return nodes.ModelSpec(
        name="Block",
        fields=[
            nodes.FieldSpec(
                name="block", oneof=nodes.OneOfSpec(discriminator="type", variants=variants)
            )
        ],
    )


def test_synthesizes_literal_tag_field_on_each_variant():
    spec = nodes.ResourceSpec(
        domain="notion",
        resource="blocks",
        security="tok",
        models=[
            _paragraph(),
            _heading(),
            _block_with({"paragraph": "ref<Paragraph>", "heading_1": "ref<Heading1Block>"}),
        ],
        operations=[_minimal_op()],
    )
    res = _resource(spec)
    paragraph = res.model("Paragraph")
    heading = res.model("Heading1Block")
    assert isinstance(paragraph, ObjectModel)  # narrow the model union before field access
    assert isinstance(heading, ObjectModel)
    assert paragraph.fields[0].name == "type"
    assert paragraph.fields[0].type == LiteralType(value="paragraph")
    assert heading.fields[0].type == LiteralType(value="heading_1")


def test_variant_authoring_its_own_tag_field_raises():
    """A variant that hand-writes a field named `type` collides with the synthesized tag."""
    paragraph = nodes.ModelSpec(
        name="Paragraph",
        fields=[
            # collides with the synthesized discriminator
            nodes.FieldSpec(name="type", type="string"),
            nodes.FieldSpec(name="text", type="string", optional=True),
        ],
    )
    spec = nodes.ResourceSpec(
        domain="notion",
        resource="blocks",
        security="tok",
        models=[
            paragraph,
            _heading(),
            _block_with({"paragraph": "ref<Paragraph>", "heading_1": "ref<Heading1Block>"}),
        ],
        operations=[_minimal_op()],
    )
    with pytest.raises(SpecError, match="collides with the synthesized discriminator"):
        _resource(spec)


def test_oneof_naming_unknown_variant_raises():
    """A discriminated variant `ref<Nope>` where Nope is undeclared -> SpecError."""
    spec = nodes.ResourceSpec(
        domain="notion",
        resource="blocks",
        security="tok",
        models=[
            _paragraph(),
            _block_with({"paragraph": "ref<Paragraph>", "heading_1": "ref<Nope>"}),
        ],
        operations=[_minimal_op()],
    )
    with pytest.raises(SpecError, match="not a declared model"):
        _resource(spec)


def test_discriminated_variant_naming_non_object_model_raises():
    """A discriminated variant `ref<Rows>` where Rows is a root_list model -> SpecError (covers the
    ObjectModel guard: `_oneof_type` only checks ref-ness, not object-ness)."""
    rows = nodes.ModelSpec(name="Rows", kind="root_list", item="Paragraph")
    spec = nodes.ResourceSpec(
        domain="notion",
        resource="blocks",
        security="tok",
        models=[
            rows,
            _paragraph(),
            _block_with({"rows": "ref<Rows>", "paragraph": "ref<Paragraph>"}),
        ],
        operations=[_minimal_op()],
    )
    with pytest.raises(SpecError, match="must be an object model"):
        _resource(spec)
