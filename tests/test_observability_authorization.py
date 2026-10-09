import json

from observability.backend.handler import (
    _authorized_for_observability,
    _normalise_groups,
)


def _api_event(groups):
    return {
        "requestContext": {
            "http": {},
            "authorizer": {"jwt": {"claims": {"cognito:groups": groups}}},
        }
    }


def test_normalise_groups_accepts_list_and_json_string():
    assert _normalise_groups(["observability-readonly"]) == ["observability-readonly"]
    assert _normalise_groups(json.dumps(["observability-readonly"])) == [
        "observability-readonly"
    ]


def test_normalise_groups_accepts_delimited_and_bracketed_strings():
    assert _normalise_groups("us-east-1_Google,observability-readonly") == [
        "us-east-1_Google",
        "observability-readonly",
    ]
    assert _normalise_groups("['us-east-1_Google', 'observability-readonly']") == [
        "us-east-1_Google",
        "observability-readonly",
    ]


def test_authorization_accepts_required_group():
    assert _authorized_for_observability(
        _api_event(["us-east-1_Google", "observability-readonly"])
    )


def test_authorization_rejects_missing_required_group():
    assert not _authorized_for_observability(_api_event(["us-east-1_Google"]))
