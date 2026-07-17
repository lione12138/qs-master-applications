from __future__ import annotations

import pytest

from gradwindow.programme_adapters.nyu import CATALOG_URL, NYUAdapter

CATALOG_HTML = """
<header><a href="/">2026-2027 Bulletins</a></header>
<ul class="isotope">
  <li class="item">
    <a href="/graduate/engineering/programs/computer-science-tandon-ms/">
      <div class="item-container">
        <span class="title">Computer Science Tandon (MS)</span>
        <span class="keyword">MS</span><span class="keyword">Masters</span>
        <span class="keyword">In Person</span><span class="keyword">Graduate</span>
        <span class="keyword">Tandon</span>
      </div>
    </a>
  </li>
  <li class="item">
    <a href="/graduate/arts-science/programs/politics-ma/">
      <div class="item-container">
        <span class="title">Politics (MA)</span>
        <span class="keyword">MA</span><span class="keyword">Masters</span>
        <span class="keyword">In Person</span><span class="keyword">Graduate</span>
        <span class="keyword">Arts &amp; Science</span>
      </div>
    </a>
  </li>
  <li class="item">
    <a href="/graduate/professional-studies/programs/human-capital-dual-ms-ms/">
      <div class="item-container">
        <span class="title">Human Capital Management/Human Capital Analytics and Technology (MS/MS)</span>
        <span class="keyword">Masters</span><span class="keyword">In Person</span>
        <span class="keyword">Graduate</span><span class="keyword">SPS</span>
        <span class="keyword">MS/MS</span>
      </div>
    </a>
  </li>
  <li class="item">
    <a href="/graduate/arts-science/programs/politics-ma/">
      <div class="item-container">
        <span class="title">Politics (MA)</span>
        <span class="keyword">MA</span><span class="keyword">Masters</span>
        <span class="keyword">Graduate</span><span class="keyword">Arts &amp; Science</span>
      </div>
    </a>
  </li>
  <li class="item">
    <a href="/undergraduate/engineering/programs/computer-science-bs-ms/">
      <span class="title">Computer Science (BS/MS)</span>
      <span class="keyword">Bachelors</span><span class="keyword">Masters</span>
      <span class="keyword">Undergraduate</span><span class="keyword">Graduate</span>
      <span class="keyword">Tandon</span>
    </a>
  </li>
  <li class="item">
    <a href="/graduate/engineering/programs/computer-science-phd/">
      <span class="title">Computer Science (PhD)</span>
      <span class="keyword">PhD</span><span class="keyword">Doctoral</span>
      <span class="keyword">Graduate</span><span class="keyword">Tandon</span>
    </a>
  </li>
</ul>
"""


def _fetcher(url: str) -> str:
    assert url == CATALOG_URL
    return CATALOG_HTML


def _adapter(**kwargs) -> NYUAdapter:
    kwargs.setdefault("minimum_expected_programmes", 3)
    kwargs.setdefault("maximum_expected_programmes", 4)
    return NYUAdapter(**kwargs)


def test_nyu_adapter_discovers_unique_graduate_masters_programmes() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 3
    assert {item.name for item in catalog.programmes} == {
        "MS in Computer Science",
        "Politics (MA)",
        "Human Capital Management/Human Capital Analytics and Technology (MS/MS)",
    }
    assert {item.faculty for item in catalog.programmes} == {
        "Tandon",
        "Arts & Science",
        "SPS",
    }


def test_nyu_adapter_preserves_existing_tandon_computer_science_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    computer_science = next(
        item for item in catalog.programmes if item.name == "MS in Computer Science"
    )

    assert computer_science.id == "nyu-tandon-computer-science-ms"
    assert (
        computer_science.application_url == "https://apply.engineering.nyu.edu/apply/"
    )
    assert computer_science.source_url.endswith("/computer-science-tandon-ms/")


def test_nyu_adapter_keeps_bulletin_only_records_out_of_exact_windows() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert catalog.application_opens_at is None
    assert all(item.windows == [] for item in catalog.programmes)
    assert all(item.parse_status == "no-deadline" for item in catalog.programmes)
    assert all(
        "does not publish an exact application opening" in item.deadline_text
        for item in catalog.programmes
    )


def test_nyu_adapter_rejects_a_stale_bulletin() -> None:
    with pytest.raises(ValueError, match="expected 2027 or later"):
        _adapter(minimum_bulletin_year=2027).parse_catalog_from_fetcher(_fetcher)


def test_nyu_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 3 master's programmes"):
        _adapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(_fetcher)
