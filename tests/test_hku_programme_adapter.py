from __future__ import annotations

import json

from gradwindow.programme_adapters.hku import HKUAdapter

LISTING_PAYLOAD = {
    "data": [
        {
            "Attributes": {
                "hkutgp_name": "Master of Data Science",
                "hkutgp_programmenameabbreviation": "MDASC",
                "rootprogramme.hkutgp_name": {"Value": "master-of-data-science-cds"},
            },
            "FormattedValues": {
                "hkutgp_facultyid": "School of Computing and Data Science"
            },
        },
        {
            "Attributes": {
                "hkutgp_name": "Doctor of Education",
                "rootprogramme.hkutgp_name": {"Value": "doctor-of-education-edu"},
            },
            "FormattedValues": {"hkutgp_facultyid": "Faculty of Education"},
        },
    ],
    "total": 2,
}

DETAIL_HTML = """
<html><body>
  <h1>Master of Data Science</h1>
  <section>
    Programme Highlights: Full-time
    Expected Programme Start Date September 2026
    Application Deadline
    Round 1 (Main): 12:00 noon (GMT +8), December 01, 2025
    Round 2 (Clearing): 12:00 noon (GMT +8), March 31, 2026
    Description Full Time Closed to Applications
  </section>
</body></html>
"""


def test_hku_adapter_extracts_listing_and_deadline_rounds() -> None:
    adapter = HKUAdapter(minimum_expected_programmes=1, detail_workers=1)

    def fetcher(url: str) -> str:
        if "SavedQueryService" in url:
            return json.dumps(LISTING_PAYLOAD)
        assert "master-of-data-science-cds" in url
        return DETAIL_HTML

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert catalog.application_opens_at == "2025-09-01"
    assert [item.id for item in catalog.programmes] == ["hku-data-science-master"]
    programme = catalog.programmes[0]
    assert programme.degree_type == "Master"
    assert programme.faculty == "School of Computing and Data Science"
    assert programme.parse_status == "parsed"
    assert [
        (window.round, window.closes_at, window.opens_at)
        for window in programme.windows
    ] == [
        ("Round 1 (Main)", "2025-12-01", None),
        ("Round 2 (Clearing)", "2026-03-31", None),
    ]
    assert programme.windows[0].intake == "September 2026"


def test_hku_adapter_omits_intake_parenthetical_from_programme_id() -> None:
    payload = {
        "data": [
            {
                "Attributes": {
                    "hkutgp_name": "Master of Science in Advanced Architectural Design (September 2026)",
                    "rootprogramme.hkutgp_name": {
                        "Value": "master-of-science-in-advanced-architectural-design-september-2026-foa"
                    },
                },
                "FormattedValues": {"hkutgp_facultyid": "Faculty of Architecture"},
            }
        ],
        "total": 1,
    }
    adapter = HKUAdapter(minimum_expected_programmes=1, detail_workers=1)

    def fetcher(url: str) -> str:
        if "SavedQueryService" in url:
            return json.dumps(payload)
        return "<html><body>No deadline</body></html>"

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert catalog.programmes[0].id == "hku-advanced-architectural-design-msc"
