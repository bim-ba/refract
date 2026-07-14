import pytest

from refract import ir
from refract.loader import SpecError, load


def test_loads_me_resource(me_spec_path):
    res = load(me_spec_path)
    assert isinstance(res, ir.Resource)
    assert res.domain == "tracker" and res.resource == "me"
    assert res.model("Me").fields[0].name == "uid"
    assert res.model("Me").fields[0].type == "int | None"  # neutral 'integer'+optional lowered
    op = res.operations[0]
    assert op.name == "get" and op.method == "GET" and op.response_model == "Me"
    assert op.mcp is not None and op.mcp.require_found is not None
    assert op.mcp.require_found.sentinel == "r.login is None"


def test_malformed_spec_raises_located_specerror(tmp_path):
    bad = tmp_path / "resource.yaml"
    bad.write_text("domain: tracker\nunknown_key: 1\n", encoding="utf-8")
    with pytest.raises(SpecError) as excinfo:
        load(bad)
    assert str(bad) in str(excinfo.value)


def test_invalid_yaml_raises_located_specerror(tmp_path):
    bad = tmp_path / "resource.yaml"
    bad.write_text("domain: [tracker\n", encoding="utf-8")  # unclosed flow sequence
    with pytest.raises(SpecError) as excinfo:
        load(bad)
    assert str(bad) in str(excinfo.value)


def test_non_mapping_top_level_raises_located_specerror(tmp_path):
    bad = tmp_path / "resource.yaml"
    bad.write_text("- tracker\n- me\n", encoding="utf-8")  # a list, not a mapping
    with pytest.raises(SpecError) as excinfo:
        load(bad)
    assert str(bad) in str(excinfo.value)
