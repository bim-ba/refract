"""Github /repos/{owner}/{repo} + repos/{owner}/{repo}/issues resource - client, HTTP stubbed."""

from __future__ import annotations

import responses
from ycli.yandex.github.client import GithubClient
from ycli.yandex.github.repos.models import Issue, IssueCreate, IssueList, Repo

_URL_get = "https://api.github.com/repos/octocat/Hello-World"
_PAYLOAD_get = {
    "id": 1296269,
    "name": "Hello-World",
    "full_name": "octocat/Hello-World",
    "private": False,
    "stargazers_count": 3785,
    "default_branch": "master",
}
_URL_issues = "https://api.github.com/repos/octocat/Hello-World/issues"
_PAYLOAD_issues = [{"number": 11054, "title": "This should fail", "state": "open"}]
_URL_create_issue = "https://api.github.com/repos/octocat/Hello-World/issues"
_PAYLOAD_create_issue = {"id": 5292951135, "number": 11054, "title": "Bug", "state": "open"}


@responses.activate
def test_repos_client_get(creds):
    responses.add(responses.GET, _URL_get, json=_PAYLOAD_get, status=200)
    repos = GithubClient(github_token="t").repos.get("octocat", "Hello-World")
    assert isinstance(repos, Repo)
    assert repos.full_name == "octocat/Hello-World"
    assert repos.default_branch == "master"


@responses.activate
def test_repos_client_issues(creds):
    responses.add(responses.GET, _URL_issues, json=_PAYLOAD_issues, status=200)
    repos = GithubClient(github_token="t").repos.issues("octocat", "Hello-World", state="all")
    assert isinstance(repos, IssueList)
    assert repos.root[0].number == 11054


@responses.activate
def test_repos_client_create_issue(creds):
    responses.add(responses.POST, _URL_create_issue, json=_PAYLOAD_create_issue, status=201)
    repos = GithubClient(github_token="t").repos.create_issue(
        "octocat", "Hello-World", IssueCreate(title="Bug")
    )
    assert isinstance(repos, Issue)
    assert repos.number == 11054
    assert repos.title == "Bug"
