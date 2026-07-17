import pytest
from pydantic import TypeAdapter, ValidationError

from refract.ir.auth import AuthInput, AuthScheme, HeaderAuth, MultiHeaderAuth

_adapter = TypeAdapter(AuthScheme)


def test_header_auth_parses_by_discriminator():
    parsed = _adapter.validate_python(
        {
            "kind": "header",
            "header": "Authorization",
            "template": "Bearer {token}",
            "inputs": [{"name": "token", "env": "API_TOKEN"}],
        }
    )
    assert isinstance(parsed, HeaderAuth)
    assert parsed.header == "Authorization"
    assert parsed.inputs[0] == AuthInput(name="token", env="API_TOKEN")


def test_multi_header_auth_parses_by_discriminator():
    parsed = _adapter.validate_python(
        {
            "kind": "multi_header",
            "headers": [["Authorization", "OAuth {token}"], ["X-Org-Id", "{organization_id}"]],
            "inputs": [
                {"name": "token", "env": "YANDEX_ID_OAUTH_TOKEN"},
                {"name": "organization_id", "env": "YANDEX_ID_ORGANIZATION_ID"},
            ],
        }
    )
    assert isinstance(parsed, MultiHeaderAuth)
    assert parsed.headers == (("Authorization", "OAuth {token}"), ("X-Org-Id", "{organization_id}"))


def test_auth_input_env_defaults_to_none():
    assert AuthInput(name="token").env is None
    assert AuthInput(name="token", env="API_TOKEN").env == "API_TOKEN"


def test_auth_scheme_is_frozen():
    scheme = HeaderAuth(
        header="Authorization",
        template="Bearer {token}",
        inputs=(AuthInput(name="token", env="API_TOKEN"),),
    )
    with pytest.raises(ValidationError):
        scheme.header = "X"  # frozen
