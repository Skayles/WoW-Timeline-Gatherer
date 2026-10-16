from typing import Any

import httpx
import pytest

from conftest import REPORT_CODE, FakeWcl, load_json
from wcl_notes.api.auth import TOKEN_URL
from wcl_notes.api.client import WclClient, load_query
from wcl_notes.api.credentials import Credentials
from wcl_notes.api.errors import (
    AuthenticationError,
    PrivateReportError,
    RateLimitError,
    ReportNotFoundError,
    WclApiError,
    WclNetworkError,
)
from wcl_notes.api.reports import fetch_report


def _graphql_error(message: str) -> httpx.Response:
    return httpx.Response(
        200, json={"errors": [{"message": message}], "data": {"reportData": {"report": None}}}
    )


def test_missing_report(fake_wcl: FakeWcl) -> None:
    fake_wcl.handlers["Report"] = lambda _: httpx.Response(
        200, json=load_json("report_not_found.json")
    )
    with fake_wcl.client() as client, pytest.raises(ReportNotFoundError):
        fetch_report(client, "AAAAAAAAAAAAAAAA")


def test_private_report(fake_wcl: FakeWcl) -> None:
    fake_wcl.handlers["Report"] = lambda _: _graphql_error(
        "You do not have permission to view this report."
    )
    with fake_wcl.client() as client, pytest.raises(PrivateReportError):
        fetch_report(client, REPORT_CODE)


def test_unknown_graphql_error_keeps_wcl_message(fake_wcl: FakeWcl) -> None:
    fake_wcl.handlers["Report"] = lambda _: _graphql_error("Something odd happened.")
    with fake_wcl.client() as client, pytest.raises(WclApiError, match="Something odd"):
        fetch_report(client, REPORT_CODE)


def test_rate_limit(fake_wcl: FakeWcl) -> None:
    fake_wcl.handlers["Report"] = lambda _: httpx.Response(429)
    with fake_wcl.client() as client, pytest.raises(RateLimitError):
        fetch_report(client, REPORT_CODE)


def test_token_is_reused_between_queries(fake_wcl: FakeWcl) -> None:
    with fake_wcl.client() as client:
        fetch_report(client, REPORT_CODE)
        fetch_report(client, REPORT_CODE)
    assert fake_wcl.token_requests == 1


def test_expired_token_is_refreshed_once(fake_wcl: FakeWcl) -> None:
    responses = [httpx.Response(401), httpx.Response(200, json=load_json("report_cmw7.json"))]
    fake_wcl.handlers["Report"] = lambda _: responses.pop(0)
    with fake_wcl.client() as client:
        fetch_report(client, REPORT_CODE)
    assert fake_wcl.token_requests == 2


def test_rejected_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == TOKEN_URL
        return httpx.Response(401, json={"error": "invalid_client"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with (
        WclClient(Credentials("bad", "bad"), http=http) as client,
        pytest.raises(AuthenticationError),
    ):
        client.execute("report", {"code": REPORT_CODE})


def test_network_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with (
        WclClient(Credentials("id", "secret"), http=http) as client,
        pytest.raises(WclNetworkError),
    ):
        client.execute("report", {"code": REPORT_CODE})


def test_secret_never_appears_in_repr() -> None:
    assert "s3cr3t" not in repr(Credentials("id", "s3cr3t"))


def test_queries_are_packaged() -> None:
    for name in ("report", "player_casts", "pet_casts"):
        assert load_query(name).lstrip().startswith("#")


def test_requests_send_bearer_token(fake_wcl: FakeWcl) -> None:
    seen: list[dict[str, Any]] = []
    original = fake_wcl.handle

    def spy(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.headers))
        return original(request)

    fake_wcl.handle = spy  # type: ignore[method-assign]
    with fake_wcl.client() as client:
        fetch_report(client, REPORT_CODE)
    assert seen[-1]["authorization"] == "Bearer test"
    assert seen[-1]["user-agent"].startswith("wcl-notes/")
