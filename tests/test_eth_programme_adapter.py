from __future__ import annotations

from gradwindow.programme_adapters.eth import DATES_URL, ETHAdapter

PROFILE_HTML = """
<html><body>
  <div class="linklist__wrapper">
    <h2>Engineering Sciences</h2>
    <ul>
      <li><a href="/content/dam/ethz/common/docs/master-profile/englisch/ingenieurwissenschaften/MSc-Computer-Science-Appendix.pdf">
        <span>Download</span> Computer Science MSc (PDF, 317 KB)
      </a></li>
      <li><a href="/content/dam/ethz/common/docs/master-profile/englisch/ingenieurwissenschaften/MSc-RSC-Appendix.pdf">
        <span>Download</span> Robotics, Systems and Control MSc (PDF, 180 KB)
      </a></li>
    </ul>
  </div>
  <div class="linklist__wrapper">
    <h2>Natural Sciences and Mathematics</h2>
    <ul>
      <li><a href="/content/dam/ethz/common/docs/master-profile/englisch/naturwissenschaften/MSc-Mathematics-Appendix.pdf">
        <span>Download</span> Mathematics MSc / Applied Mathematics MSc (PDF, 220 KB)
      </a></li>
      <li><a href="/content/dam/ethz/common/docs/master-profile/englisch/naturwissenschaften/MSc-QuantumEngineering-Appendix.pdf">
        <span>Download</span> Quantum Engineering MSc (PDF, 146 KB)
      </a></li>
    </ul>
  </div>
  <div class="linklist__wrapper">
    <h2>Engineering Sciences</h2>
    <ul>
      <li><a href="/content/dam/ethz/common/docs/master-profile/englisch/ingenieurwissenschaften/MSc-QuantumEngineering-Appendix.pdf">
        <span>Download</span> Quantum Engineering MSc (PDF, 191 KB)
      </a></li>
    </ul>
  </div>
</body></html>
"""

DATES_HTML = """
<html><head><title>Application Dates Autumn Semester 2026 | ETH Zurich</title></head>
<body>
  <h2>International Bachelor's degrees: 1 - 30 November 2025</h2>
  <h2>Swiss Bachelor's degrees: 1 April – 30 April 2026</h2>
</body></html>
"""


def test_eth_adapter_extracts_programmes_and_shared_windows() -> None:
    adapter = ETHAdapter(minimum_expected_programmes=1)

    def fetcher(url: str) -> str:
        return DATES_HTML if url == DATES_URL else PROFILE_HTML

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert catalog.application_opens_at is None
    assert [item.id for item in catalog.programmes] == [
        "eth-applied-mathematics-msc",
        "eth-computer-science-msc",
        "eth-mathematics-msc",
        "eth-quantum-engineering-msc",
        "eth-robotics-systems-control-msc",
    ]

    quantum = catalog.programmes[3]
    assert quantum.name == "MSc Quantum Engineering"
    assert quantum.faculty == "Natural Sciences and Mathematics | Engineering Sciences"
    assert "MSc-QuantumEngineering-Appendix.pdf" in quantum.source_url

    computer_science = catalog.programmes[1]
    assert computer_science.parse_status == "parsed"
    assert [
        (
            window.round,
            window.applicant_categories,
            window.opens_at,
            window.closes_at,
            window.intake,
        )
        for window in computer_science.windows
    ] == [
        (
            "International Bachelor's window",
            ["international-bachelors", "esop", "direct-doctorate"],
            "2025-11-01",
            "2025-11-30",
            "Autumn 2026",
        ),
        (
            "Swiss Bachelor's window",
            ["swiss-bachelors"],
            "2026-04-01",
            "2026-04-30",
            "Autumn 2026",
        ),
    ]
