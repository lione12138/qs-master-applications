from __future__ import annotations

from gradwindow.monitor import (
    content_fingerprint,
    evaluate_content_change,
    previous_success_fields,
    summarize_monitor_results,
)
from gradwindow.content import evidence_context, evidence_excerpt


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
