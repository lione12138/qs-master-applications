from __future__ import annotations

import json

import pytest

from gradwindow.programme_adapters.uva import (
    APPLY_URL,
    CATALOG_URL,
    UvAAdapter,
)

API_URL = "https://www.uva.nl/_restapi/list-json?uuid=current-list&mount=current-mount"

CATALOG_HTML = f"""
<main>
  <h1>All our Master's programmes</h1>
  <div id="root" data-urljson="{API_URL}" data-itemsperpage="500"></div>
</main>
"""

APPLY_HTML = """
<main>
  <p>Every programme at the University of Amsterdam has its own entry requirements, application procedure and deadlines.</p>
</main>
"""

PAYLOAD = json.dumps(
    {
        "title": "All our Master's programmes",
        "items": [
            {
                "id": "0fb7d08e-7f53-4959-b5e8-26a1c87ff755",
                "title": "Computer Science (joint degree UvA/VU)",
                "url": "https://www.uva.nl/en/programmes/masters/computer-science/computer-science.html?origin=test",
                "programmeLanguage": ["english"],
                "programmeType": ["masters"],
                "faculty": ["faculty-of-science"],
                "startsIn": ["september"],
                "studytitle": ["msc"],
            },
            {
                "id": "english-research",
                "title": "Social Sciences (research)",
                "url": "https://www.uva.nl/en/programmes/masters/social-sciences-research/social-sciences-research.html",
                "programmeLanguage": ["english"],
                "programmeType": ["research-masters"],
                "faculty": ["faculty-of-social-and-behavioural-sciences"],
                "startsIn": ["september"],
                "studytitle": ["research-ma"],
            },
            {
                "id": "english-llm",
                "title": "International Law",
                "url": "https://www.uva.nl/en/programmes/masters/international-law/international-law.html",
                "programmeLanguage": ["dutch", "english"],
                "programmeType": ["advanced-masters"],
                "faculty": ["amsterdam-law-school"],
                "startsIn": ["september"],
                "studytitle": ["llm"],
            },
            {
                "id": "english-minor",
                "title": "Science for Sustainability",
                "url": "https://www.uva.nl/en/programmes/minors/science-for-sustainability.html",
                "programmeLanguage": ["english"],
                "programmeType": ["minor"],
                "faculty": ["faculty-of-science"],
                "studytitle": [""],
            },
            {
                "id": "dutch-master",
                "title": "Arbeidsrecht",
                "url": "https://www.uva.nl/programmas/masters/arbeidsrecht/arbeidsrecht.html",
                "programmeLanguage": ["dutch"],
                "programmeType": ["masters"],
                "faculty": ["amsterdam-law-school"],
                "studytitle": ["llm"],
            },
        ],
    }
)


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return CATALOG_HTML
    if url == APPLY_URL:
        return APPLY_HTML
    raise AssertionError(url)


def _adapter(**kwargs) -> UvAAdapter:
    kwargs.setdefault("minimum_expected_programmes", 3)
    kwargs.setdefault("maximum_expected_programmes", 4)
    kwargs.setdefault("api_payload_fetcher", lambda url: PAYLOAD)
    return UvAAdapter(**kwargs)


def test_uva_adapter_discovers_only_english_masters_and_excludes_minors() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 3
    assert {item.name for item in catalog.programmes} == {
        "MSc Computer Science",
        "Social Sciences (research)",
        "International Law",
    }
    assert {item.degree_type for item in catalog.programmes} == {"MSc", "MA", "LLM"}


def test_uva_adapter_preserves_existing_joint_computer_science_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    computer_science = next(
        item for item in catalog.programmes if "Computer Science" in item.name
    )

    assert computer_science.id == "uva-vu-computer-science-msc"
    assert (
        computer_science.application_url
        == "https://vu.nl/en/education/more-about/apply-for-a-masters-programme"
    )
    assert computer_science.source_url.endswith("/computer-science.html")


def test_uva_adapter_keeps_programme_specific_deadlines_out_of_windows() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert catalog.application_opens_at is None
    assert all(item.windows == [] for item in catalog.programmes)
    assert all(item.parse_status == "no-deadline" for item in catalog.programmes)
    assert all(
        "programme-specific" in item.deadline_text for item in catalog.programmes
    )


def test_uva_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 3 English-taught master's"):
        _adapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(_fetcher)


def test_uva_adapter_rejects_a_non_official_api_url() -> None:
    def fetcher(url: str) -> str:
        if url == CATALOG_URL:
            return CATALOG_HTML.replace("https://www.uva.nl", "https://example.com")
        return _fetcher(url)

    with pytest.raises(ValueError, match="non-official catalogue API"):
        _adapter().parse_catalog_from_fetcher(fetcher)
