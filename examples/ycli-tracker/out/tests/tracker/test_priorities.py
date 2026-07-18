"""Tracker /priorities + priorities/ resource - client, HTTP stubbed."""

from __future__ import annotations

import responses
from ycli.yandex.tracker.client import TrackerClient
from ycli.yandex.tracker.priorities.models import (
    LocalizedName,
    Priority,
    PriorityCreate,
    PriorityList,
)

_URL_list = "https://api.tracker.yandex.net/v3/priorities"
_PAYLOAD_list = [{"key": "normal", "name": "Normal"}, {"key": "critical", "name": "Critical"}]
_URL_create = "https://api.tracker.yandex.net/v3/priorities/"
_PAYLOAD_create = {"key": "one", "name": "Nizkiy"}


@responses.activate
def test_priorities_client_list(creds):
    responses.add(responses.GET, _URL_list, json=_PAYLOAD_list, status=200)
    priorities = TrackerClient(oauth_token="t", organization_id="o").priorities.list()
    assert isinstance(priorities, PriorityList)
    assert priorities.root[0].key == "normal"


@responses.activate
def test_priorities_client_create(creds):
    responses.add(responses.POST, _URL_create, json=_PAYLOAD_create, status=200)
    priorities = TrackerClient(oauth_token="t", organization_id="o").priorities.create(
        PriorityCreate(key="one", name=LocalizedName(ru="Nizkiy"))
    )
    assert isinstance(priorities, Priority)
    assert priorities.key == "one"
    assert priorities.name == "Nizkiy"
