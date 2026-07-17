import dataclasses

import pytest

from refract.runtime import Request


def test_request_constructs_frozen_with_empty_defaults():
    req = Request(method="GET", path="myself", response_model=dict)
    assert (req.method, req.path, req.response_model) == ("GET", "myself", dict)
    assert req.query is None and req.json_body is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.method = "POST"  # frozen + slots
