from __future__ import annotations

import json

import pytest

from gradwindow.programme_adapters.anu import (
    APPLICATION_URL,
    INTERNATIONAL_DATES_URL,
    SEARCH_URL,
    ANUAdapter,
    catalogue_api_url,
)

SEARCH_HTML = """
<main>
  <div id="programsearchpage" data-searchviewmodel='{
    "AvailableYears": [
      {"Selected": false, "Text": "2026", "Value": "2026"},
      {"Selected": true, "Text": "2027", "Value": "2027"}
    ]
  }'></div>
</main>
"""

CATALOGUE_PAYLOAD = {
    "TotalCount": 7,
    "Items": [
        {
            "AcademicPlanCode": "7706XMCOMP",
            "ProgramName": "Master of Computing",
            "AcademicCareer": "Postgraduate",
            "ProgramAcademicYear": "2027",
            "ModeOfDelivery": "In Person",
        },
        {
            "AcademicPlanCode": "MCLIM",
            "ProgramName": "Master of Climate Change",
            "AcademicCareer": "Postgraduate",
            "ProgramAcademicYear": "2027",
            "ModeOfDelivery": "In Person",
        },
        {
            "AcademicPlanCode": "MCLIMO",
            "ProgramName": "Master of Climate Change",
            "AcademicCareer": "Postgraduate",
            "ProgramAcademicYear": "2027",
            "ModeOfDelivery": "Online",
        },
        {
            "AcademicPlanCode": "MEMPA",
            "ProgramName": "Executive Master of Public Administration",
            "AcademicCareer": "Postgraduate",
            "ProgramAcademicYear": "2027",
            "ModeOfDelivery": "Multi-Modal",
        },
        {
            "AcademicPlanCode": "MSTD",
            "ProgramName": "Master of Studies",
            "AcademicCareer": "Postgraduate",
            "ProgramAcademicYear": "2027",
            "ModeOfDelivery": "In Person",
        },
        {
            "AcademicPlanCode": "MPSC",
            "ProgramName": "Master of Preclinical Science",
            "AcademicCareer": "Postgraduate",
            "ProgramAcademicYear": "2027",
            "ModeOfDelivery": "In Person",
        },
        {
            "AcademicPlanCode": "GCLOUD",
            "ProgramName": "Graduate Certificate of Cloud Applications",
            "AcademicCareer": "Postgraduate",
            "ProgramAcademicYear": "2027",
            "ModeOfDelivery": "Online",
        },
    ],
}

DATES_HTML = """
<nav>Semester 2, 2026 Semester 1, 2027 Semester 2, 2027</nav>
<main>
  <h2>Semester 2, 2026</h2>
  <ul>
    <li>Applications are now open and will close on the 14 June 2026.</li>
    <li>Crawford School programs close on 15 April 2026.</li>
  </ul>
  <h2>Semester 1, 2027</h2>
  <ul>
    <li>Applications are now open and will close on the 15 December 2026.</li>
    <li>Applications deadline for programs offered by the Crawford School of
      Public Policy is 31 October 2026.</li>
    <li>Application deadline for programs with additional selection criteria
      may vary.</li>
  </ul>
  <h2>Semester 2, 2027</h2>
  <ul>
    <li>Applications are now open and will close on the 15 May 2027.</li>
    <li>Crawford School programs close on 15 April 2027.</li>
    <li>Application deadline for programs with additional selection criteria
      may vary.</li>
  </ul>
</main>
"""

CATALOGUE_XML = (
    '<SearchResult xmlns="urn:anu">'
    "<Items>"
    + "".join(
        "<ProgramSearchResultModel>"
        f"<AcademicPlanCode>{item['AcademicPlanCode']}</AcademicPlanCode>"
        f"<ProgramName>{item['ProgramName']}</ProgramName>"
        f"<AcademicCareer>{item['AcademicCareer']}</AcademicCareer>"
        f"<ProgramAcademicYear>{item['ProgramAcademicYear']}</ProgramAcademicYear>"
        f"<ModeOfDelivery>{item['ModeOfDelivery']}</ModeOfDelivery>"
        "</ProgramSearchResultModel>"
        for item in CATALOGUE_PAYLOAD["Items"]
    )
    + "</Items>"
    f"<TotalCount>{CATALOGUE_PAYLOAD['TotalCount']}</TotalCount>"
    "</SearchResult>"
)


def _fetcher(url: str) -> str:
    if url == SEARCH_URL:
        return SEARCH_HTML
    if url == catalogue_api_url(2027):
        return json.dumps(CATALOGUE_PAYLOAD)
    if url == INTERNATIONAL_DATES_URL:
        return DATES_HTML
    raise AssertionError(url)


def test_anu_adapter_discovers_current_master_catalogue_without_unsafe_windows() -> (
    None
):
    catalog = ANUAdapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(
        _fetcher
    )

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "anu-computing-master",
        "anu-mclim",
        "anu-mclimo",
        "anu-mempa",
    ]
    assert all(not programme.windows for programme in catalog.programmes)
    assert all(
        programme.parse_status == "no-deadline" for programme in catalog.programmes
    )


def test_anu_adapter_disambiguates_delivery_modes_and_preserves_official_urls() -> None:
    catalog = ANUAdapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(
        _fetcher
    )
    climate = [
        programme
        for programme in catalog.programmes
        if "Climate Change" in programme.name
    ]

    assert [programme.name for programme in climate] == [
        "Master of Climate Change",
        "Master of Climate Change (Online)",
    ]
    assert climate[0].source_url == (
        "https://programsandcourses.anu.edu.au/2027/program/mclim"
    )
    assert climate[0].application_url == APPLICATION_URL
    assert climate[0].faculty == "Australian National University"
    assert climate[0].department == "In Person delivery"


def test_anu_adapter_records_general_dates_as_guidance_not_programme_windows() -> None:
    catalog = ANUAdapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(
        _fetcher
    )
    programme = catalog.programmes[0]

    assert "2026-12-15" in programme.deadline_text
    assert "2026-10-31" in programme.deadline_text
    assert "2027-05-15" in programme.deadline_text
    assert "additional selection criteria" in programme.deadline_text
    assert "no exact opening date" in programme.deadline_text
    assert programme.retrieval_method == "official-api-and-page"
    assert programme.evidence_quality == "official-policy-guidance"


def test_anu_adapter_accepts_the_official_xml_content_negotiation_response() -> None:
    def fetcher(url: str) -> str:
        if url == catalogue_api_url(2027):
            return CATALOGUE_XML
        return _fetcher(url)

    catalog = ANUAdapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(
        fetcher
    )

    assert len(catalog.programmes) == 4


def test_anu_adapter_rejects_a_truncated_catalogue_response() -> None:
    def fetcher(url: str) -> str:
        if url == catalogue_api_url(2027):
            payload = dict(CATALOGUE_PAYLOAD)
            payload["TotalCount"] = 8
            return json.dumps(payload)
        return _fetcher(url)

    with pytest.raises(ValueError, match="returned 7 of 8"):
        ANUAdapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(fetcher)


def test_anu_adapter_rejects_a_truncated_masters_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 4 applicable master's"):
        ANUAdapter(minimum_expected_programmes=5).parse_catalog_from_fetcher(_fetcher)


def test_anu_adapter_requires_the_official_exception_warning() -> None:
    def fetcher(url: str) -> str:
        if url == INTERNATIONAL_DATES_URL:
            return DATES_HTML.replace(
                "Application deadline for programs with additional selection criteria\n"
                "      may vary.",
                "",
            )
        return _fetcher(url)

    with pytest.raises(ValueError, match="additional-selection exception"):
        ANUAdapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(fetcher)
