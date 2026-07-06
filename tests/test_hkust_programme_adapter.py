from __future__ import annotations

from gradwindow.programme_adapters.hkust import HKUSTAdapter

CATALOG_HTML = """
<div>
  <a href="/pgprog/2026-27/msc-ai/">Computer Science and Engineering Artificial Intelligence MSc</a>
</div>
"""

DETAIL_HTML = """
<html><body>
GENERAL INFORMATION
Award Title Master of Science in Artificial Intelligence
Award Title (Chinese) 理學碩士 ( 人工智能 )
Program Short Name MSc(AI)
Offering Unit Department of Computer Science and Engineering
Program Advisor Program Director
Website https://seng.hkust.edu.hk/msc/ai
Enquiry mscai@ust.hk
APPLICATION
Apply online before the application deadlines.
Application Deadlines
For 2026/27 Fall Term Intake (commencing in Sep 2026):
Non-local Applicants* Full-time: 1 Nov 2025 (Round 1); 1 Jan 2026 (Round 2); 1 Mar 2026 (Round 3)
Local Applicants Full-time: 1 Nov 2025 (Round 1); 1 Jan 2026 (Round 2); 1 Mar 2026 (Round 3)
Admissions is on rolling basis.
Back Privacy
</body></html>
"""


def test_hkust_adapter_extracts_catalog_and_deadline_candidates() -> None:
    adapter = HKUSTAdapter(minimum_expected_programmes=1, detail_workers=1)

    def fetcher(url: str) -> str:
        if "print_result.php" in url:
            return CATALOG_HTML
        return DETAIL_HTML

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert catalog.application_opens_at == "2025-09-01"
    assert [item.id for item in catalog.programmes] == [
        "hkust-artificial-intelligence-msc"
    ]
    programme = catalog.programmes[0]
    assert programme.name == "Master of Science in Artificial Intelligence"
    assert programme.degree_type == "MSc"
    assert programme.faculty == "Department of Computer Science and Engineering"
    assert programme.application_url == "https://seng.hkust.edu.hk/msc/ai"
    assert programme.parse_status == "parsed"
    assert [
        (w.round, w.closes_at, w.applicant_categories, w.opens_at)
        for w in programme.windows
    ] == [
        ("Round 1", "2025-11-01", ["international-students"], None),
        ("Round 2", "2026-01-01", ["international-students"], None),
        ("Round 3", "2026-03-01", ["international-students"], None),
        ("Round 1", "2025-11-01", ["domestic-students"], None),
        ("Round 2", "2026-01-01", ["domestic-students"], None),
        ("Round 3", "2026-03-01", ["domestic-students"], None),
    ]
