from __future__ import annotations

from gradwindow.generic_seed_discovery import audit_generic_seed_entry


def test_seed_discovery_recommends_linked_basic_list() -> None:
    entry = {
        "name": "example-masters",
        "universityId": "example-university",
        "prefix": "example",
        "seedUrls": ["https://example.edu/study/masters/courses/list/"],
        "minimumExpected": 1,
        "maxDetailPages": 10,
        "enabled": True,
    }
    university = {
        "id": "example-university",
        "homepageUrl": "https://example.edu",
        "admissionsUrl": "https://example.edu/apply",
        "officialDomains": ["example.edu"],
    }
    pages = {
        "https://example.edu/study/masters/courses/list/": """
            <html><body>
              <h1>Master's courses</h1>
              <a href="/study/masters/courses/list/basic/">simple A-Z list</a>
            </body></html>
        """,
        "https://example.edu/study/masters/courses/list/basic/": """
            <html><body>
              <h1>A-Z list</h1>
              <a href="/study/masters/courses/list/12345/msc-data-science/">
                Data Science MSc
              </a>
            </body></html>
        """,
    }

    def fetcher(url: str) -> str:
        if url not in pages:
            raise RuntimeError("HTTP 404")
        return pages[url]

    result = audit_generic_seed_entry(
        entry,
        university,
        fetcher=fetcher,
        max_candidate_seeds=4,
    )

    assert result["recommendation"]["action"] == "replaceSeed"
    assert (
        result["recommendation"]["seedUrl"]
        == "https://example.edu/study/masters/courses/list/basic/"
    )
    assert result["recommendation"]["programmeLinkCount"] == 1


def test_seed_discovery_marks_access_blocked() -> None:
    entry = {
        "name": "blocked-masters",
        "universityId": "blocked-university",
        "prefix": "blocked",
        "seedUrls": ["https://blocked.example.edu/study/postgraduate"],
        "minimumExpected": 1,
        "enabled": True,
    }
    university = {
        "id": "blocked-university",
        "homepageUrl": "https://blocked.example.edu",
        "officialDomains": ["blocked.example.edu"],
    }

    def fetcher(url: str) -> str:
        raise RuntimeError("HTTP 403")

    result = audit_generic_seed_entry(
        entry,
        university,
        fetcher=fetcher,
        max_candidate_seeds=2,
    )

    assert result["recommendation"]["action"] == "markBlocked"
    assert result["recommendation"]["category"] == "blockedByAccess"
