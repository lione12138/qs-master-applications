from __future__ import annotations

from gradwindow.monitor import (
    content_fingerprint,
    evaluate_content_change,
    extract_fetched_text,
    previous_success_fields,
    summarize_monitor_results,
)
from gradwindow.content import (
    evidence_context,
    evidence_excerpt,
    evidence_matches_target_dates,
)
from gradwindow.http_client import FetchedPage


def test_fingerprint_ignores_scripts_comments_and_whitespace() -> None:
    first = """
    <html><body><h1>Graduate Admissions</h1>
    <script>window.timestamp = 1</script><!-- generated -->
    <p>Applications open.</p></body></html>
    """
    second = """
    <html>
      <body><h1>Graduate Admissions</h1>
      <script>window.timestamp = 999</script>
      <p>Applications   open.</p></body>
    </html>
    """
    assert content_fingerprint(first) == content_fingerprint(second)


def test_fingerprint_changes_when_visible_content_changes() -> None:
    assert content_fingerprint("<p>Open</p>") != content_fingerprint("<p>Closed</p>")


def test_fingerprint_ignores_navigation_and_cookie_banners() -> None:
    first = """
    <body><nav>Menu A</nav><main><p>Applications open.</p></main>
    <div class="cookie-banner">Accept cookies</div></body>
    """
    second = """
    <body><nav>Menu B</nav><main><p>Applications open.</p></main>
    <div class="cookie-banner">Different cookies</div></body>
    """
    assert content_fingerprint(first) == content_fingerprint(second)


def test_evidence_excerpt_prioritizes_deadline_content() -> None:
    html = """
    <body><nav>How to apply</nav><main>
    <p>General course description with application examples.</p>
    <p>The application deadline is 15 January 2027.</p>
    <p>Applications may close early.</p>
    </main></body>
    """
    excerpt = evidence_excerpt(html, ["2027-01-15"])
    assert "15 January 2027" in excerpt
    assert "How to apply" not in excerpt
    context = evidence_context(html, ["2027-01-15"])
    assert context["contentSelector"] == "main"
    assert context["matchedText"] == "The application deadline is 15 January 2027."
    assert context["matchedTextBefore"] == (
        "General course description with application examples."
    )


def test_evidence_matching_supports_chinese_dates() -> None:
    excerpt = "申请时间：2025年10月20日至2025年12月23日。"
    assert evidence_matches_target_dates(
        excerpt,
        ["2025-10-20", "2025-12-23"],
    )


def test_monitor_summary() -> None:
    summary = summarize_monitor_results(
        {
            "a": {"status": "ok", "changed": True},
            "b": {"status": "blocked", "changed": False},
            "c": {"status": "http-error", "changed": False},
        }
    )
    assert summary == {
        "total": 3,
        "ok": 1,
        "changed": 1,
        "blocked": 1,
        "errors": 1,
    }


def test_transient_errors_can_preserve_last_successful_baseline() -> None:
    previous = {
        "contentHash": "abc",
        "lastSuccessfulAt": "2026-06-13T10:00:00Z",
        "status": "ok",
    }
    assert previous_success_fields(previous) == {
        "contentHash": "abc",
        "lastSuccessfulAt": "2026-06-13T10:00:00Z",
    }


def test_change_requires_two_consecutive_identical_fingerprints() -> None:
    first = evaluate_content_change({"contentHash": "old"}, "new")
    assert first == {
        "contentHash": "old",
        "changed": False,
        "changeDetected": True,
        "pendingContentHash": "new",
        "pendingChangeCount": 1,
    }

    second = evaluate_content_change(
        {
            "contentHash": "old",
            "pendingContentHash": "new",
            "pendingChangeCount": 1,
        },
        "new",
    )
    assert second == {
        "contentHash": "new",
        "changed": True,
        "changeDetected": True,
        "pendingContentHash": None,
        "pendingChangeCount": 0,
    }


def test_a_different_second_fingerprint_restarts_confirmation() -> None:
    result = evaluate_content_change(
        {
            "contentHash": "old",
            "pendingContentHash": "candidate-a",
            "pendingChangeCount": 1,
        },
        "candidate-b",
    )
    assert result["changed"] is False
    assert result["pendingContentHash"] == "candidate-b"
    assert result["pendingChangeCount"] == 1


def test_fingerprint_version_change_rebuilds_the_baseline() -> None:
    result = evaluate_content_change(
        {
            "contentHash": "old",
            "fingerprintVersion": 1,
            "pendingContentHash": "new",
            "pendingChangeCount": 1,
        },
        "new",
        fingerprint_version=2,
    )
    assert result == {
        "contentHash": "new",
        "changed": False,
        "changeDetected": False,
        "pendingContentHash": None,
        "pendingChangeCount": 0,
        "fingerprintVersion": 2,
    }


def test_non_pdf_fetched_text_uses_decoded_body() -> None:
    page = FetchedPage(
        body="<main>Applications open.</main>",
        raw_bytes=b"<main>Applications open.</main>",
        final_url="https://example.edu",
        status_code=200,
        content_type="text/html",
        charset="utf-8",
        bytes_read=31,
        truncated=False,
    )
    assert extract_fetched_text(page) == "<main>Applications open.</main>"


def test_pdf_fetched_text_uses_pdf_reader(monkeypatch) -> None:
    class FakePdfPage:
        def extract_text(self):
            return "申请时间：2025年10月20日至2025年12月23日"

    class FakePdfReader:
        def __init__(self, stream):
            assert stream.read() == b"%PDF fixture"
            self.pages = [FakePdfPage()]

    monkeypatch.setattr("gradwindow.monitor.PdfReader", FakePdfReader)
    page = FetchedPage(
        body="%PDF decoded incorrectly",
        raw_bytes=b"%PDF fixture",
        final_url="https://example.edu/notice.pdf",
        status_code=200,
        content_type="application/pdf",
        charset="utf-8",
        bytes_read=12,
        truncated=False,
    )
    assert "2025年10月20日" in extract_fetched_text(page)
