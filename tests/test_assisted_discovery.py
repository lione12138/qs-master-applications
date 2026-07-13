from __future__ import annotations

import httpx

import gradwindow.assisted_discovery as assisted_discovery
from gradwindow.assisted_discovery import (
    AssistedDiscoveryConfig,
    BraveSearcher,
    RetrievedDocument,
    SearchResult,
    _search_official_sources,
    _validated_catalog,
    run_assisted_discovery,
)


def _config() -> AssistedDiscoveryConfig:
    return AssistedDiscoveryConfig(
        university_id="example-university",
        university_name="Example University",
        school_prefix="example",
        seed_urls=("https://example.edu/postgraduate",),
        official_domains=("example.edu",),
        default_application_url="https://example.edu/apply",
        default_intake="Fall 2027",
        minimum_closes_at="2026-07-01",
    )


def test_validated_catalog_accepts_exact_dates_from_official_fulltext() -> None:
    document = RetrievedDocument(
        id="doc-programme",
        title="MSc Data Science",
        url="https://example.edu/programmes/msc-data-science",
        content=(
            "MSc Data Science. Applications open September 1, 2026. "
            "The application deadline is January 14, 2027."
        ),
        retrieval_method="cloudflare-browser-rendering",
        evidence_quality="official-fulltext",
    )
    payload = {
        "programmes": [
            {
                "name": "MSc Data Science",
                "degreeType": "MSc",
                "faculty": "Science",
                "department": "Computing",
                "sourceDocumentId": "doc-programme",
                "applicationUrl": "https://example.edu/apply",
                "programmeEvidenceQuote": "MSc Data Science",
                "windows": [
                    {
                        "intake": "Fall 2027",
                        "round": "Main deadline",
                        "applicantCategories": ["all"],
                        "opensAt": "2026-09-01",
                        "closesAt": "2027-01-14",
                        "sourceDocumentId": "doc-programme",
                        "evidenceQuote": (
                            "Applications open September 1, 2026. "
                            "The application deadline is January 14, 2027."
                        ),
                    }
                ],
            }
        ]
    }

    catalog, validation = _validated_catalog(_config(), [document], payload)

    assert validation == {
        "modelProgrammes": 1,
        "acceptedProgrammes": 1,
        "rejectedProgrammes": 0,
        "acceptedWindows": 1,
        "rejectedWindows": 0,
    }
    programme = catalog.programmes[0]
    assert programme.id == "example-msc-data-science"
    assert programme.parse_status == "parsed"
    assert programme.evidence_quality == "official-fulltext"
    assert [
        (window.opens_at, window.closes_at, window.source_url)
        for window in programme.windows
    ] == [
        (
            "2026-09-01",
            "2027-01-14",
            "https://example.edu/programmes/msc-data-science",
        )
    ]


def test_validated_catalog_never_accepts_dates_from_search_snippets() -> None:
    document = RetrievedDocument(
        id="doc-snippet",
        title="MSc Data Science",
        url="https://example.edu/programmes/msc-data-science",
        content=(
            "MSc Data Science applications open September 1, 2026 and close "
            "January 14, 2027."
        ),
        retrieval_method="search-snippet",
        evidence_quality="official-search-snippet",
    )
    payload = {
        "programmes": [
            {
                "name": "MSc Data Science",
                "degreeType": "MSc",
                "sourceDocumentId": "doc-snippet",
                "programmeEvidenceQuote": "MSc Data Science",
                "windows": [
                    {
                        "intake": "Fall 2027",
                        "round": "Main deadline",
                        "applicantCategories": ["all"],
                        "opensAt": "2026-09-01",
                        "closesAt": "2027-01-14",
                        "sourceDocumentId": "doc-snippet",
                        "evidenceQuote": document.content,
                    }
                ],
            }
        ]
    }

    catalog, validation = _validated_catalog(_config(), [document], payload)

    assert validation["acceptedProgrammes"] == 1
    assert validation["acceptedWindows"] == 0
    assert validation["rejectedWindows"] == 1
    assert catalog.programmes[0].windows == []
    assert catalog.programmes[0].parse_status == "no-deadline"
    assert catalog.programmes[0].evidence_quality == "official-search-snippet"


def test_validated_catalog_rejects_navigation_pages_as_programmes() -> None:
    document = RetrievedDocument(
        id="doc-catalogue",
        title="Master's Programs",
        url="https://example.edu/postgraduate",
        content="Master's Programs Find a taught graduate degree and learn how to apply.",
        retrieval_method="direct-http",
        evidence_quality="official-fulltext",
    )
    payload = {
        "programmes": [
            {
                "name": "Master's Programs",
                "degreeType": "Master",
                "sourceDocumentId": "doc-catalogue",
                "windows": [],
            }
        ]
    }

    catalog, validation = _validated_catalog(_config(), [document], payload)

    assert catalog.programmes == []
    assert validation["rejectedProgrammes"] == 1


def test_validated_catalog_treats_malformed_model_windows_as_rejected() -> None:
    document = RetrievedDocument(
        id="doc-programme",
        title="MSc Data Science",
        url="https://example.edu/programmes/data-science",
        content="MSc Data Science",
        retrieval_method="direct-http",
        evidence_quality="official-fulltext",
    )
    payload = {
        "programmes": [
            {
                "name": "MSc Data Science",
                "degreeType": "MSc",
                "sourceDocumentId": "doc-programme",
                "windows": {"closesAt": "2027-01-14"},
            }
        ]
    }

    catalog, validation = _validated_catalog(_config(), [document], payload)

    assert len(catalog.programmes) == 1
    assert catalog.programmes[0].windows == []
    assert validation["rejectedWindows"] == 1


def test_official_search_filters_third_party_results_and_deduplicates() -> None:
    calls = []

    def searcher(query: str, count: int) -> list[SearchResult]:
        calls.append((query, count))
        return [
            SearchResult(
                title="MSc Data Science",
                url="https://example.edu/programmes/msc-data-science",
                description="Official programme",
            ),
            SearchResult(
                title="MSc Data Science deadline",
                url="https://example.edu/programmes/msc-data-science#apply",
                description="Same official programme",
            ),
            SearchResult(
                title="Example deadline guide",
                url="https://rankings.example.com/example-deadlines",
                description="Third-party guide",
            ),
        ]

    results = _search_official_sources(_config(), searcher)

    assert len(calls) == 2
    assert calls[0][0].startswith("site:example.edu ")
    assert "(site:" not in calls[0][0]
    assert [result.url for result in results] == [
        "https://example.edu/postgraduate",
        "https://example.edu/programmes/msc-data-science",
    ]


def test_brave_search_retries_without_optional_extra_snippets(monkeypatch) -> None:
    calls = []

    def fake_get(url, *, headers, params, timeout):
        calls.append((url, headers, dict(params), timeout))
        request = httpx.Request("GET", url, params=params)
        if len(calls) == 1:
            return httpx.Response(422, request=request, json={"message": "invalid"})
        return httpx.Response(
            200,
            request=request,
            json={
                "web": {
                    "results": [
                        {
                            "title": "MSc Data Science",
                            "url": "https://example.edu/msc-data-science",
                            "description": "Official programme",
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr(assisted_discovery.httpx, "get", fake_get)

    results = BraveSearcher("secret").search("site:example.edu MSc", 20)

    assert [result.title for result in results] == ["MSc Data Science"]
    assert calls[0][2]["extra_snippets"] == "true"
    assert "extra_snippets" not in calls[1][2]
    assert calls[1][2]["count"] == 10


def test_assisted_discovery_only_requires_deepseek_credentials(
    monkeypatch,
) -> None:
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    report = run_assisted_discovery(_config(), dry_run=True)

    assert report["status"] == "skipped"
    assert report["missingCredentials"] == ["DEEPSEEK_API_KEY"]


def test_assisted_discovery_reports_search_errors_without_crashing_batch() -> None:
    def failing_searcher(_query: str, _count: int) -> list[SearchResult]:
        raise RuntimeError("search unavailable")

    report = run_assisted_discovery(
        _config(),
        dry_run=True,
        searcher=failing_searcher,
        extractor=lambda _config, _documents: {"programmes": []},
    )

    assert report["status"] == "error"
    assert report["stage"] == "search"
    assert report["errorType"] == "RuntimeError"


def test_assisted_discovery_runs_search_retrieval_extraction_and_candidate_flow() -> (
    None
):
    result = SearchResult(
        title="Data Science",
        url="https://example.edu/programmes/data-science",
        description="Official MSc programme",
    )
    document = RetrievedDocument(
        id="doc-data-science",
        title="Data Science",
        url=result.url,
        content=(
            "Data Science is an MSc programme. Applications open "
            "September 1, 2026. Application deadline January 14, 2027."
        ),
        retrieval_method="direct-http",
        evidence_quality="official-fulltext",
    )

    def searcher(_query: str, _count: int) -> list[SearchResult]:
        return [result]

    def loader(_result: SearchResult) -> RetrievedDocument:
        return document

    def extractor(
        _config: AssistedDiscoveryConfig,
        _documents: list[RetrievedDocument],
    ) -> dict:
        return {
            "programmes": [
                {
                    "name": "Data Science",
                    "degreeType": "MSc",
                    "sourceDocumentId": "doc-data-science",
                    "programmeEvidenceQuote": "Data Science is an MSc programme.",
                    "windows": [
                        {
                            "intake": "Fall 2027",
                            "round": "Main deadline",
                            "applicantCategories": ["all"],
                            "opensAt": "2026-09-01",
                            "closesAt": "2027-01-14",
                            "sourceDocumentId": "doc-data-science",
                            "evidenceQuote": (
                                "Applications open September 1, 2026. "
                                "Application deadline January 14, 2027."
                            ),
                        }
                    ],
                }
            ]
        }

    report = run_assisted_discovery(
        _config(),
        dry_run=True,
        searcher=searcher,
        page_loader=loader,
        extractor=extractor,
    )

    assert report["status"] == "ok"
    assert report["assistedDiscovery"] is True
    assert report["catalogProgrammes"] == 1
    assert report["newCandidates"] == 1
    assert report["validation"]["acceptedWindows"] == 1
    assert report["documents"][0]["evidenceQuality"] == "official-fulltext"
