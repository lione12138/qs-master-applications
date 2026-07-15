from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def load_module():
    path = Path(__file__).parents[1] / "scripts" / "submit_indexnow.py"
    spec = importlib.util.spec_from_file_location("submit_indexnow", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_load_sitemap_urls_reads_and_deduplicates_urls(tmp_path: Path) -> None:
    sitemap = tmp_path / "sitemap.xml"
    sitemap.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://gradwindow.com/</loc></url>
          <url><loc>https://gradwindow.com/calendar.html</loc></url>
          <url><loc>https://gradwindow.com/</loc></url>
        </urlset>
        """,
        encoding="utf-8",
    )

    assert load_module().load_sitemap_urls(sitemap) == [
        "https://gradwindow.com/",
        "https://gradwindow.com/calendar.html",
    ]


def test_load_key_requires_root_key_filename_to_match_content(tmp_path: Path) -> None:
    key_file = tmp_path / "abc12345.txt"
    key_file.write_text("abc12345\n", encoding="utf-8")

    module = load_module()
    assert module.load_key(key_file) == "abc12345"

    key_file.write_text("different-key", encoding="utf-8")
    with pytest.raises(ValueError, match="filename"):
        module.load_key(key_file)


def test_build_payload_rejects_urls_outside_the_canonical_host() -> None:
    with pytest.raises(ValueError, match="same host"):
        load_module().build_payload(
            ["https://gradwindow.com/", "https://www.gradwindow.com/calendar.html"],
            key="abc12345",
            key_filename="abc12345.txt",
        )


def test_build_payload_includes_root_key_location() -> None:
    payload = load_module().build_payload(
        ["https://gradwindow.com/", "https://gradwindow.com/calendar.html"],
        key="abc12345",
        key_filename="abc12345.txt",
    )

    assert payload == {
        "host": "gradwindow.com",
        "key": "abc12345",
        "keyLocation": "https://gradwindow.com/abc12345.txt",
        "urlList": [
            "https://gradwindow.com/",
            "https://gradwindow.com/calendar.html",
        ],
    }


def test_submit_urls_accepts_indexnow_pending_validation(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["content_type"] = request.headers["Content-type"]
        captured["timeout"] = timeout
        return Response()

    module = load_module()
    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    payload = {
        "host": "gradwindow.com",
        "key": "abc12345",
        "keyLocation": "https://gradwindow.com/abc12345.txt",
        "urlList": ["https://gradwindow.com/"],
    }

    assert module.submit_urls(payload) == 202
    assert captured == {
        "url": "https://api.indexnow.org/indexnow",
        "body": payload,
        "content_type": "application/json; charset=utf-8",
        "timeout": 45,
    }
