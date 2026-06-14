from __future__ import annotations

from contextlib import nullcontext

import httpx
import pytest

from gradwindow import http_client


class FakeClient:
    response: httpx.Response

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *args) -> None:
        return None

    def stream(self, method: str, url: str):
        return nullcontext(self.response)


def test_fetch_page_classifies_blocked_response(monkeypatch) -> None:
    FakeClient.response = httpx.Response(
        403,
        request=httpx.Request("GET", "https://example.edu"),
    )
    monkeypatch.setattr(http_client.httpx, "Client", FakeClient)
    monkeypatch.setattr(http_client, "MIN_HOST_INTERVAL", 0)

    with pytest.raises(http_client.FetchFailure) as caught:
        http_client.fetch_page(
            "https://example.edu",
            user_agent="test",
            attempts=1,
        )
    assert caught.value.kind == "blocked"
    assert caught.value.status_code == 403


def test_fetch_page_returns_response_metadata(monkeypatch) -> None:
    FakeClient.response = httpx.Response(
        200,
        content=b"<main>Applications open</main>",
        headers={"content-type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", "https://example.edu"),
    )
    monkeypatch.setattr(http_client.httpx, "Client", FakeClient)
    monkeypatch.setattr(http_client, "MIN_HOST_INTERVAL", 0)

    page = http_client.fetch_page(
        "https://example.edu",
        user_agent="test",
        attempts=1,
    )
    assert page.status_code == 200
    assert page.body == "<main>Applications open</main>"
    assert page.content_type.startswith("text/html")
    assert page.truncated is False


def test_fetch_page_stops_at_byte_limit(monkeypatch) -> None:
    FakeClient.response = httpx.Response(
        200,
        content=b"0123456789",
        request=httpx.Request("GET", "https://example.edu"),
    )
    monkeypatch.setattr(http_client.httpx, "Client", FakeClient)
    monkeypatch.setattr(http_client, "MIN_HOST_INTERVAL", 0)

    page = http_client.fetch_page(
        "https://example.edu",
        user_agent="test",
        max_bytes=5,
        attempts=1,
    )
    assert page.body == "01234"
    assert page.bytes_read == 5
    assert page.truncated is True
