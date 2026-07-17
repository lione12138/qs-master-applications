from __future__ import annotations

import json

import pytest

from gradwindow.programme_adapters.ku_leuven import (
    CATALOG_URL,
    HOW_TO_APPLY_URL,
    KULeuvenAdapter,
)

CATALOG_HTML = """
<div id="app">
  <home-search :year="2026" esindex="pg" locale="e"></home-search>
</div>
"""

HOW_TO_APPLY_HTML = """
<main>
  <p>Every programme at KU Leuven has its own entry requirements, application procedure and deadlines.</p>
  <p>Several English-taught programmes have a fixed application deadline — check yours via the application window tool.</p>
</main>
"""


def _hit(identifier: str, title: str, degree: str, faculty: str) -> dict:
    return {
        "_source": {
            "id": identifier,
            "qualificationOriginalLangu": "EN",
            "enQualificationDegreeLevel": degree,
            "qualificationLanguageSet": [
                {
                    "qualificationTitleSet": [
                        {
                            "qualificationLangu": "EN",
                            "description": title,
                        }
                    ]
                }
            ],
            "programSet": [
                {
                    "organizationSet": [
                        {
                            "organizationId": "faculty",
                            "organizationType": "8F",
                            "enOrganization": faculty,
                            "alsoOfferedBy": "False",
                        },
                        {
                            "organizationId": "50000050",
                            "organizationType": "80",
                            "enOrganization": "KU Leuven - University",
                            "alsoOfferedBy": "False",
                        },
                    ]
                }
            ],
        }
    }


PAYLOAD = json.dumps(
    {
        "hits": {
            "total": {"value": 3, "relation": "eq"},
            "hits": [
                _hit(
                    "50550147",
                    "Master of Statistics and Data Science (Leuven)",
                    "Master's",
                    "Faculty of Science",
                ),
                _hit(
                    "50268787",
                    "Master of Advanced Studies in Economics (Leuven)",
                    "Advanced Master's",
                    "Faculty of Economics and Business (FEB)",
                ),
                _hit(
                    "58830707",
                    "Erasmus Mundus Joint Master in Insects as Solutions for a Sustainable Future (Geel et al)",
                    "Master's",
                    "Faculty of Engineering Technology",
                ),
            ],
        }
    }
)


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return CATALOG_HTML
    if url == HOW_TO_APPLY_URL:
        return HOW_TO_APPLY_HTML
    raise AssertionError(url)


def _adapter(**kwargs) -> KULeuvenAdapter:
    kwargs.setdefault("minimum_expected_programmes", 3)
    kwargs.setdefault("maximum_expected_programmes", 4)
    kwargs.setdefault("api_payload_fetcher", lambda year, index: PAYLOAD)
    return KULeuvenAdapter(**kwargs)


def test_ku_leuven_adapter_discovers_initial_and_advanced_masters() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 3
    assert {item.degree_type for item in catalog.programmes} == {
        "Master",
        "Advanced Master",
    }
    assert {item.faculty for item in catalog.programmes} == {
        "Faculty of Science",
        "Faculty of Economics and Business (FEB)",
        "Faculty of Engineering Technology",
    }


def test_ku_leuven_adapter_preserves_existing_statistics_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    statistics = next(item for item in catalog.programmes if "Statistics" in item.name)

    assert statistics.id == "ku-leuven-statistics-data-science-master"
    assert statistics.name == "Master of Statistics and Data Science"
    assert statistics.source_url.endswith("/opleidingen/e/CQ_50550147")


def test_ku_leuven_adapter_does_not_infer_programme_windows() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert catalog.application_opens_at is None
    assert all(item.windows == [] for item in catalog.programmes)
    assert all(item.parse_status == "no-deadline" for item in catalog.programmes)
    assert all(
        "programme-specific" in item.deadline_text for item in catalog.programmes
    )


def test_ku_leuven_adapter_rejects_a_stale_programme_guide() -> None:
    with pytest.raises(ValueError, match="expected 2027 or later"):
        _adapter(minimum_catalog_year=2027).parse_catalog_from_fetcher(_fetcher)


def test_ku_leuven_adapter_rejects_a_truncated_api_result() -> None:
    with pytest.raises(ValueError, match="returned 3 of 4 records"):
        _adapter(
            api_payload_fetcher=lambda year, index: PAYLOAD.replace(
                '"value": 3', '"value": 4'
            )
        ).parse_catalog_from_fetcher(_fetcher)
