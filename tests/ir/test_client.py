import pytest
from pydantic import ValidationError

from refract.ir.auth import AuthInput, MultiHeaderAuth
from refract.ir.client import ClientConfig, Server


def _tracker_config():
    return ClientConfig(
        name="tracker",
        server=Server(base_url="https://api.tracker.yandex.net/v3"),
        auth=(
            (
                "oauth_token",
                MultiHeaderAuth(
                    headers=(("Authorization", "OAuth {token}"), ("X-Org-Id", "{organization_id}")),
                    inputs=(
                        AuthInput(name="token", env="YANDEX_ID_OAUTH_TOKEN"),
                        AuthInput(name="organization_id", env="YANDEX_ID_ORGANIZATION_ID"),
                    ),
                ),
            ),
        ),
    )


def test_client_config_holds_server_and_defaults():
    config = _tracker_config()
    assert config.server.base_url == "https://api.tracker.yandex.net/v3"
    assert config.default_headers == ()


def test_auth_tuple_map_roundtrips_and_keeps_variant():
    config = _tracker_config()
    by_name = dict(config.auth)  # tuple-of-pairs behaves as an ordered map
    scheme = by_name["oauth_token"]
    assert isinstance(scheme, MultiHeaderAuth)  # discriminated variant survived
    assert scheme.headers[0] == ("Authorization", "OAuth {token}")


def test_client_config_parses_auth_by_discriminator_from_dict():
    config = ClientConfig.model_validate(
        {
            "name": "tracker",
            "server": {"base_url": "https://api.tracker.yandex.net/v3"},
            "auth": [
                [
                    "oauth_token",
                    {
                        "kind": "multi_header",
                        "headers": [["Authorization", "OAuth {token}"]],
                        "inputs": [{"name": "token", "env": "YANDEX_ID_OAUTH_TOKEN"}],
                    },
                ]
            ],
        }
    )
    assert isinstance(dict(config.auth)["oauth_token"], MultiHeaderAuth)


def test_client_config_is_frozen():
    config = _tracker_config()
    with pytest.raises(ValidationError):
        config.name = "other"  # frozen
