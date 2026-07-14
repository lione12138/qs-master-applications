from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from gradwindow.programme_adapters.birmingham import (
    CATALOG_URL,
    BirminghamAdapter,
)

CATALOGUE = """
<html><body>
  <script src="/_assets/static/startup-3.0.1.js"></script>
</body></html>
"""

STARTUP = """
var alias = "uob";
var project = "website";
context.DELIVERY_API_CONFIG = Object({
  rootUrl: url().api,
  accessToken: "fixture-public-token",
  projectId: "website"
});
"""


def _reference(entry_id: str, title: str = "Reference") -> dict:
    return {
        "entryTitle": title,
        "sys": {"id": entry_id, "contentTypeId": "reference"},
    }


CATALOG_ITEMS = [
    {
        "entryTitle": "Advanced Computer Science MSc",
        "courseName": "Advanced Computer Science Masters/MSc",
        "sys": {
            "id": "course-1",
            "uri": (
                "/study/postgraduate/subjects/computer-science-and-data-science-"
                "courses/advanced-computer-science-msc"
            ),
        },
        "qualification": [_reference("masters", "Masters")],
        "courseStructure": [_reference("taught", "Taught")],
        "courseYearDetails": [_reference("year-1")],
        "academicStructure": [
            {"name": "Engineering and Physical Sciences"},
            {"name": "School of Computer Science"},
        ],
        "applyUrl": "//www.apply.bham.ac.uk",
        "startDate": "September / January",
    },
    {
        "entryTitle": "Bioinformatics (J-BJI) MSc",
        "sys": {
            "id": "course-2",
            "uri": "/study/postgraduate/subjects/biosciences-courses/bioinformatics-msc",
        },
        "qualification": [_reference("masters", "Masters")],
        "courseStructure": [_reference("taught", "Taught")],
        "courseYearDetails": [_reference("year-2")],
        "academicStructure": [{"name": "College of Medical and Dental Sciences"}],
    },
    {
        "entryTitle": "MBA Full-time",
        "sys": {
            "id": "course-3",
            "uri": "/study/postgraduate/subjects/business-and-management-courses/mba",
        },
        "qualification": [_reference("masters", "Masters")],
        "courseStructure": [_reference("taught", "Taught")],
        "courseYearDetails": [],
    },
    {
        "entryTitle": "No public course page MSc",
        "sys": {"id": "course-4", "uri": None},
        "qualification": [_reference("masters", "Masters")],
        "courseStructure": [_reference("taught", "Taught")],
    },
]

YEAR_ITEMS = [
    {
        "entryTitle": "Advanced Computer Science MSc 2026",
        "yearOfEntry": "2026",
        "startDate": "September / January",
        "sys": {"id": "year-1"},
        "homeApplicationProcessComposer": [
            {"type": "courseSharedContentEntry", "value": _reference("home-1")}
        ],
        "internationalApplicationProcessComposer": [
            {
                "type": "courseSharedContentEntry",
                "value": _reference("international-1"),
            }
        ],
    },
    {
        "entryTitle": "Bioinformatics MSc 2026",
        "yearOfEntry": "2026",
        "startDate": "September",
        "sys": {"id": "year-2"},
        "homeApplicationProcessComposer": [
            {"type": "courseSharedContentEntry", "value": _reference("special-1")}
        ],
        "internationalApplicationProcessComposer": [
            {"type": "courseSharedContentEntry", "value": _reference("special-1")}
        ],
    },
]


def _shared(entry_id: str, title: str, facts: list[tuple[str, str]]) -> dict:
    return {
        "entryTitle": title,
        "sys": {"id": entry_id},
        "components": [
            {
                "type": "factBoxes",
                "value": {
                    "factBoxes": [
                        {"stat": stat, "description": description}
                        for stat, description in facts
                    ]
                },
            }
        ],
    }


SHARED_ITEMS = [
    _shared(
        "home-1",
        "PGT - 2026 - Home application deadline inc January start",
        [
            (
                "28 August 2026",
                "Application deadline for UK applicants for September start.",
            ),
            (
                "18 December 2026",
                "Application deadline for UK applicants to start in January 2027.",
            ),
        ],
    ),
    _shared(
        "international-1",
        "PGT - 2026 - International application deadline inc January start",
        [
            (
                "3 July 2026",
                "Application deadline for international students requiring a visa "
                "for September start.",
            ),
            (
                "30 October 2026",
                "Application deadline for international students requiring a visa "
                "for January start.",
            ),
        ],
    ),
    _shared(
        "special-1",
        "PGT - 2026 - Bioinformatics MSc application deadline",
        [("Application deadline", "7th August 2026")],
    ),
]


def _search_payload(items: list[dict]) -> str:
    return json.dumps(
        {
            "pageIndex": 0,
            "pageSize": 500,
            "totalCount": len(items),
            "pageCount": 1,
            "items": items,
        }
    )


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return CATALOGUE
    if url.endswith("/static/startup-3.0.1.js"):
        return STARTUP
    fields = parse_qs(urlparse(url).query).get("fields", [""])[0]
    if "qualification" in fields:
        return _search_payload(CATALOG_ITEMS)
    if "homeApplicationProcessComposer" in fields:
        return _search_payload(YEAR_ITEMS)
    if "components" in fields:
        return _search_payload(SHARED_ITEMS)
    raise AssertionError(url)


def test_birmingham_adapter_reads_catalogue_and_both_applicant_deadlines() -> None:
    adapter = BirminghamAdapter(minimum_expected_programmes=3, batch_size=20)

    catalog = adapter.parse_catalog_from_fetcher(_fetcher)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "birmingham-advanced-computer-science-msc",
        "birmingham-bioinformatics-j-bji-msc",
        "birmingham-master-of-business-administration-full-time-uk",
    ]
    computer_science = catalog.programmes[0]
    assert computer_science.faculty == "Engineering and Physical Sciences"
    assert computer_science.department == "School of Computer Science"
    assert computer_science.application_url == "https://www.apply.bham.ac.uk"
    assert [
        (
            window.closes_at,
            window.intake,
            window.applicant_categories,
            window.opens_at,
        )
        for window in computer_science.windows
    ] == [
        ("2026-07-03", "September 2026", ["international"], None),
        ("2026-08-28", "September 2026", ["home"], None),
        ("2026-10-30", "January 2027", ["international"], None),
        ("2026-12-18", "January 2027", ["home"], None),
    ]


def test_birmingham_adapter_merges_same_deadline_for_both_audiences() -> None:
    catalog = BirminghamAdapter(
        minimum_expected_programmes=3,
        batch_size=20,
    ).parse_catalog_from_fetcher(_fetcher)

    bioinformatics = catalog.programmes[1]
    assert len(bioinformatics.windows) == 1
    assert bioinformatics.windows[0].closes_at == "2026-08-07"
    assert bioinformatics.windows[0].intake == "September 2026"
    assert bioinformatics.windows[0].applicant_categories == ["all"]


def test_birmingham_adapter_keeps_programmes_without_exact_deadlines() -> None:
    catalog = BirminghamAdapter(
        minimum_expected_programmes=3,
        batch_size=20,
    ).parse_catalog_from_fetcher(_fetcher)

    mba = catalog.programmes[2]
    assert mba.id == "birmingham-master-of-business-administration-full-time-uk"
    assert mba.windows == []
    assert mba.parse_status == "no-deadline"
    assert "does not expose an exact application closing date" in mba.deadline_text


def test_birmingham_adapter_rejects_implausibly_small_catalogue() -> None:
    adapter = BirminghamAdapter(minimum_expected_programmes=4, batch_size=20)

    try:
        adapter.parse_catalog_from_fetcher(_fetcher)
    except ValueError as exc:
        assert "only contained 3" in str(exc)
    else:
        raise AssertionError("Expected the incomplete catalogue to be rejected")
