from __future__ import annotations

import json

import pytest

from gradwindow.programme_adapters.nus import (
    API_URL,
    BIOMEDICAL_INFORMATICS_DEADLINES_URL,
    CDE_DEADLINES_URL,
    COMPUTING_DEADLINES_URL,
    DSML_DEADLINES_URL,
    FASS_DEADLINES_URL,
    GLOBAL_SOCIOLOGY_DEADLINES_URL,
    LAW_DEADLINES_URL,
    MEDICINE_RESEARCH_DEADLINES_URL,
    PUBLIC_HEALTH_MPH_URL,
    PUBLIC_POLICY_DEADLINES_URL,
    SCIENCE_RESEARCH_DEADLINES_URL,
    NUSAdapter,
    _reader_url,
)


def _payload() -> str:
    return json.dumps(
        {
            "returnValue": [
                {
                    "facultyDisplay": "COMPUTING",
                    "programme": {
                        "Title__c": "Master of Computing",
                        "Type__c": "Master's by Coursework",
                        "Intake_Period__c": "Jan; Aug",
                        "Mode_of_Study__c": "Full-Time; Part-Time",
                        "Program_Page_Link__c": "https://www.comp.nus.edu.sg/programmes/pg/mcomp-gen/",
                        "Application_URL__c": "https://gradapp.nus.edu.sg/portal/app_manage",
                    },
                },
                {
                    "facultyDisplay": "SCIENCE",
                    "programme": {
                        "Title__c": "Master of Science",
                        "Type__c": "Master's by Research",
                        "Intake_Period__c": "Aug",
                        "Mode_of_Study__c": "Full-Time",
                        "Program_Page_Link__c": "https://www.science.nus.edu.sg/graduate/",
                    },
                },
                {
                    "facultyDisplay": "COMPUTING",
                    "programme": {
                        "Title__c": "Doctor of Philosophy",
                        "Type__c": "Doctorate by Research/ PhD",
                        "Program_Page_Link__c": "https://www.comp.nus.edu.sg/programmes/pg/phdcs/",
                    },
                },
            ]
        }
    )


def test_nus_adapter_reads_official_api_and_keeps_months_out_of_windows() -> None:
    adapter = NUSAdapter(minimum_expected_programmes=2)

    def fetcher(url: str) -> str:
        assert url == API_URL
        return _payload()

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "nus-master-of-computing-coursework",
        "nus-master-of-science-research",
    ]
    computing = catalog.programmes[0]
    assert computing.degree_type == "Master"
    assert computing.faculty == "COMPUTING"
    assert computing.windows == []
    assert computing.parse_status == "no-deadline"
    assert "intake: Jan; Aug" in computing.deadline_text
    assert computing.retrieval_method == "official-api"
    assert computing.evidence_quality == "official-full-text"
    science = catalog.programmes[1]
    assert science.degree_type == "MSc"
    assert science.application_url == "https://gradapp.nus.edu.sg/portal/app_manage"


def test_nus_adapter_rejects_implausibly_small_catalogue() -> None:
    adapter = NUSAdapter(minimum_expected_programmes=3)

    with pytest.raises(ValueError, match="only contained 2 master's programmes"):
        adapter.parse_catalog_from_fetcher(lambda url: _payload())


def test_nus_adapter_applies_faculty_deadlines_from_reader_fallback() -> None:
    payload = json.dumps(
        {
            "returnValue": [
                _item(
                    "DESIGN & ENGINEERING",
                    "MSc (Biomedical Engineering)",
                    "Coursework",
                ),
                _item(
                    "ARTS & SOCIAL SCIENCES",
                    "MA (Arts and Cultural Entrepreneurship)",
                    "Coursework",
                ),
                _item("SCIENCE", "MSc by Research (Physics)", "Research"),
                _item("MEDICINE", "MSc by Research (Medicine)", "Research"),
                _item("LAW", "LLM (Asian Legal Studies)", "Coursework"),
                _item("COMPUTING", "Master of Computing", "Coursework"),
                _item("PUBLIC HEALTH", "Master of Public Health", "Coursework"),
                _item(
                    "SCIENCE",
                    "MSc (Data Science and Machine Learning)",
                    "Coursework",
                ),
                _item(
                    "ARTS & SOCIAL SCIENCES",
                    "MA (Global Sociology and Anthropology)",
                    "Coursework",
                ),
                _item("MEDICINE", "MSc (Biomedical Informatics)", "Coursework"),
                _item("PUBLIC POLICY", "Master in Public Policy", "Coursework"),
                _item(
                    "PUBLIC POLICY",
                    "Master in International Affairs",
                    "Coursework",
                ),
                _item(
                    "PUBLIC POLICY",
                    "Master in Public Administration",
                    "Coursework",
                ),
            ]
        }
    )
    cde = """
    **Programmes****Application Period****(August 2026 intake)****Application Period****(January 2027 intake)**
    [Master of Science (Biomedical Engineering)](https://cde.nus.edu.sg/bme/)1 Oct 2025 - 28 Feb 2026 27 Jul 2026 - 31 Aug 2026
    """
    fass = """
    ### 5. APPLICATION CLOSING DATES AND NOTIFICATION OF APPLICATION OUTCOME
    Semester I
    (August)30 November
    (in the year preceding the intake)Master of Arts (Arts and Cultural Entrepreneurship)
    Applicants who had submitted their application online can check the status.
    """
    science = """
    Closing Date: 15 November of the previous year (for August intake)
    and 15 May of the previous year (for January intake).
    """
    medicine = """
    Semester 1 (August intake): 31 December - for full-time candidates.
    Semester 2 (January intake): 30 June - for full-time candidates.
    """
    law = """
    Online Application Period for August 2026 intake
    All LLM Coursework
    1 September - 15 October 2025
    """
    computing = """
    | Intake | Application opens | Application closes |
    | August intake | 1 October 2025 | 31 January 2026 |
    """
    public_health = """
    Applications are open from
    1 Aug 2026 to 15 Nov 2026
    """
    dsml = """
    August 2027 16 May 2026 to 15 July 2026 (Early Admission Cycle)
    1 October 2026 to 31 January 2027 (Regular Admission Cycle)
    """
    global_sociology = "August 2027 1 September 2026 30 November 2026"
    biomedical_informatics = """
    August 2027
    Application Period
    1 October 2026 - 2 February 2027
    """
    public_policy = """
    Master in Public Policy (MPP) : 1 August - 15 December every year
    Master in International Affairs (MIA) : 1 August - 15 December every year
    Master in Public Administration (MPA): 1 August - 31 December every year
    Master in Public Administration and Management (MPAM): 1 August - 9 January every year
    """
    reader_payloads = {
        _reader_url(CDE_DEADLINES_URL): cde,
        _reader_url(FASS_DEADLINES_URL): fass,
        _reader_url(SCIENCE_RESEARCH_DEADLINES_URL): science,
        _reader_url(MEDICINE_RESEARCH_DEADLINES_URL): medicine,
        _reader_url(LAW_DEADLINES_URL): law,
        _reader_url(COMPUTING_DEADLINES_URL): computing,
        _reader_url(PUBLIC_HEALTH_MPH_URL): public_health,
        _reader_url(DSML_DEADLINES_URL): dsml,
        _reader_url(GLOBAL_SOCIOLOGY_DEADLINES_URL): global_sociology,
        _reader_url(BIOMEDICAL_INFORMATICS_DEADLINES_URL): biomedical_informatics,
        _reader_url(PUBLIC_POLICY_DEADLINES_URL): public_policy,
    }

    def fetcher(url: str) -> str:
        if url == API_URL:
            return payload
        if url in reader_payloads:
            return reader_payloads[url]
        if url in {
            CDE_DEADLINES_URL,
            FASS_DEADLINES_URL,
            SCIENCE_RESEARCH_DEADLINES_URL,
            MEDICINE_RESEARCH_DEADLINES_URL,
            LAW_DEADLINES_URL,
            COMPUTING_DEADLINES_URL,
            PUBLIC_HEALTH_MPH_URL,
            DSML_DEADLINES_URL,
            GLOBAL_SOCIOLOGY_DEADLINES_URL,
            BIOMEDICAL_INFORMATICS_DEADLINES_URL,
            PUBLIC_POLICY_DEADLINES_URL,
        }:
            return '<script src="/_Incapsula_Resource"></script>'
        raise AssertionError(url)

    catalog = NUSAdapter(
        minimum_expected_programmes=13, target_intake_year=2027
    ).parse_catalog_from_fetcher(fetcher)
    programmes = {programme.name: programme for programme in catalog.programmes}

    cde_programme = programmes["MSc (Biomedical Engineering)"]
    assert cde_programme.parse_status == "parsed"
    assert cde_programme.retrieval_method == "official-page-via-reader"
    assert [
        (window.intake, window.opens_at, window.closes_at)
        for window in cde_programme.windows
    ] == [
        ("August 2026", "2025-10-01", "2026-02-28"),
        ("January 2027", "2026-07-27", "2026-08-31"),
    ]
    fass_programme = programmes["MA (Arts and Cultural Entrepreneurship)"]
    assert fass_programme.parse_status == "incomplete"
    assert [
        (window.intake, window.opens_at, window.closes_at)
        for window in fass_programme.windows
    ] == [("August 2027", None, "2026-11-30")]
    science_programme = programmes["MSc by Research (Physics)"]
    assert science_programme.parse_status == "incomplete"
    assert [window.closes_at for window in science_programme.windows] == [
        "2026-11-15",
        "2026-05-15",
    ]
    medicine_programme = programmes["MSc by Research (Medicine)"]
    assert [
        (window.round, window.closes_at) for window in medicine_programme.windows
    ] == [("Full-time", "2026-12-31"), ("Full-time", "2026-06-30")]
    law_programme = programmes["LLM (Asian Legal Studies)"]
    assert law_programme.parse_status == "parsed"
    assert [
        (window.intake, window.opens_at, window.closes_at)
        for window in law_programme.windows
    ] == [("August 2026", "2025-09-01", "2025-10-15")]
    computing_programme = programmes["Master of Computing"]
    assert computing_programme.parse_status == "parsed"
    assert [
        (window.intake, window.opens_at, window.closes_at)
        for window in computing_programme.windows
    ] == [("August 2026", "2025-10-01", "2026-01-31")]
    mph_programme = programmes["Master of Public Health"]
    assert mph_programme.parse_status == "parsed"
    assert [
        (window.intake, window.opens_at, window.closes_at)
        for window in mph_programme.windows
    ] == [("August 2027", "2026-08-01", "2026-11-15")]
    dsml_programme = programmes["MSc (Data Science and Machine Learning)"]
    assert [
        (window.round, window.opens_at, window.closes_at)
        for window in dsml_programme.windows
    ] == [
        ("Early admission", "2026-05-16", "2026-07-15"),
        ("Regular admission", "2026-10-01", "2027-01-31"),
    ]
    assert [
        (window.opens_at, window.closes_at)
        for window in programmes["MA (Global Sociology and Anthropology)"].windows
    ] == [("2026-09-01", "2026-11-30")]
    assert [
        (window.opens_at, window.closes_at)
        for window in programmes["MSc (Biomedical Informatics)"].windows
    ] == [("2026-10-01", "2027-02-02")]
    assert [
        (programme.name, programme.windows[0].opens_at, programme.windows[0].closes_at)
        for programme in catalog.programmes
        if programme.faculty == "PUBLIC POLICY" and programme.windows
    ] == [
        ("Master in International Affairs", "2026-08-01", "2026-12-15"),
        ("Master in Public Administration", "2026-08-01", "2026-12-31"),
        ("Master in Public Policy", "2026-08-01", "2026-12-15"),
    ]


def _item(faculty: str, title: str, track: str) -> dict:
    return {
        "facultyDisplay": faculty,
        "programme": {
            "Title__c": title,
            "Type__c": f"Master's by {track}",
            "Intake_Period__c": "Jan; Aug",
            "Mode_of_Study__c": "Full-Time",
            "Program_Page_Link__c": f"https://example.nus.edu.sg/{title}",
            "Application_URL__c": "https://gradapp.nus.edu.sg/portal/app_manage",
        },
    }
