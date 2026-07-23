from __future__ import annotations

import pytest

from gradwindow.programme_adapters.ip_paris import CATALOG_URL, IPParisAdapter

CATALOG_HTML = """
<html><body><section>
  <div class="conteneur-enfant"><h3 class="titre-enfant">
    <a href="/en/education/masters/computer-science-program">Computer Science Program</a>
  </h3></div>
  <div class="conteneur-enfant"><h3 class="titre-enfant">
    <a href="/en/education/masters/economics-program">Economics Program</a>
  </h3></div>
  <div class="conteneur-enfant"><h3 class="titre-enfant">
    <a href="/en/education/graduate-programs/masters-science/physics-program">Physics Program</a>
  </h3></div>
</section></body></html>
"""


def _fetcher(url: str) -> str:
    assert url == CATALOG_URL
    return CATALOG_HTML


def test_ip_paris_adapter_discovers_central_master_programmes() -> None:
    catalog = IPParisAdapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(
        _fetcher
    )

    assert len(catalog.programmes) == 3
    assert {item.name for item in catalog.programmes} == {
        "Master in Computer Science",
        "Master in Economics",
        "Master in Physics",
    }
    assert len({item.id for item in catalog.programmes}) == 3


def test_ip_paris_adapter_preserves_existing_computer_science_identity() -> None:
    catalog = IPParisAdapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(
        _fetcher
    )
    programme = next(item for item in catalog.programmes if "Computer" in item.name)

    assert programme.id == "ip-paris-computer-science-master"


def test_ip_paris_adapter_keeps_programmes_in_window_monitoring() -> None:
    catalog = IPParisAdapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(
        _fetcher
    )

    assert all(item.windows == [] for item in catalog.programmes)
    assert all(item.parse_status == "no-deadline" for item in catalog.programmes)
    assert all("2027/28" in item.deadline_text for item in catalog.programmes)


def test_ip_paris_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 3 master's programmes"):
        IPParisAdapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(
            _fetcher
        )
