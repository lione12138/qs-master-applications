from __future__ import annotations

import json

import pytest

from gradwindow.programme_adapters.nus import API_URL, NUSAdapter


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
