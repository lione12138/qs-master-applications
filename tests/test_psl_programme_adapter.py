from __future__ import annotations

import pytest

from gradwindow.programme_adapters.psl import (
    APPLICATION_URL,
    CATALOG_URL,
    PSLAdapter,
)

COMPUTER_SCIENCE_URL = "https://psl.eu/formation/master-informatique"
SUSTAINABILITY_URL = "https://psl.eu/formation/master-science-de-la-durabilite"
MINES_URL = "https://psl.eu/formation/cycle-ingenieur-civil-mines-paris-psl"

CATALOG_PAGE_0 = """
<html><body>
  <a class="formation_row" href="/formation/master-informatique">
    <h2>Master Informatique</h2>
  </a>
  <a class="formation_row" href="/formation/master-science-de-la-durabilite">
    <h2>Master Science de la durabilité</h2>
  </a>
  <nav class="pager-nav"><a rel="last" href="?field_niveau%5B30%5D=30&page=1">
    Dernière page
  </a></nav>
</body></html>
"""

CATALOG_PAGE_1 = """
<html><body>
  <a class="formation_row" href="/formation/cycle-ingenieur-civil-mines-paris-psl">
    <h2>Cycle ingénieur civil MINES Paris - PSL</h2>
  </a>
</body></html>
"""


def _detail(
    title: str,
    admission_html: str,
    *operators: tuple[str, str],
) -> str:
    logos = "".join(
        f'<a class="etablissement_element" href="{href}"><img alt="{alt}"></a>'
        for href, alt in operators
    )
    return f"""
    <html><body><h1>{title}</h1>
      <div class="info_bl"><h3>Établissement PSL opérateur</h3>
        <div class="bloc_logos">{logos}</div>
      </div>
      <div class="field--item"><h3>Admissions</h3>
        {admission_html}
        <h3>Frais de scolarité</h3><p>Informations complémentaires.</p>
      </div>
    </body></html>
    """


DETAILS = {
    COMPUTER_SCIENCE_URL: _detail(
        "Informatique",
        "<p>Dépôt des candidatures du 17 février au 16 mars 2026.</p>",
        ("/dauphine-psl", "Logo Paris-Dauphine"),
        ("/ecole-normale-superieure-psl", "Logo ENS PSL"),
    ),
    SUSTAINABILITY_URL: _detail(
        "Science de la durabilité",
        "<p>Calendrier 2027 : session 1 du 15 janvier au 24 février 2027 ; "
        "session 2 du 18 mai au 22 juin 2027.</p>",
        ("/ecole-normale-superieure-psl", "Logo ENS PSL"),
    ),
    MINES_URL: _detail(
        "Cycle ingénieur civil MINES Paris - PSL",
        "<p>Le calendrier de la prochaine campagne sera publié ultérieurement.</p>",
        ("/universite/nos-etablissements/mines-paris-psl", "Logo Mines Paris PSL"),
    ),
}


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return CATALOG_PAGE_0
    if url == f"{CATALOG_URL}&page=1":
        return CATALOG_PAGE_1
    if url in DETAILS:
        return DETAILS[url]
    raise AssertionError(url)


def test_psl_adapter_discovers_paginated_master_and_grade_catalogue() -> None:
    catalog = PSLAdapter(
        minimum_expected_programmes=3,
        workers=2,
    ).parse_catalog_from_fetcher(_fetcher)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "psl-computer-science-master",
        "psl-cycle-ingenieur-civil-mines-paris-psl",
        "psl-master-science-de-la-durabilite",
    ]
    assert len(catalog.programmes) == 3


def test_psl_adapter_preserves_existing_computer_science_identity() -> None:
    catalog = PSLAdapter(
        minimum_expected_programmes=3,
        workers=2,
    ).parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item for item in catalog.programmes if item.id == "psl-computer-science-master"
    )

    assert programme.name == "Master Informatique"
    assert programme.degree_type == "Master"
    assert programme.faculty == "Dauphine-PSL, ENS-PSL and MINES Paris-PSL"
    assert programme.application_url == "https://www.monmaster.gouv.fr/"


def test_psl_adapter_parses_exact_2027_application_sessions() -> None:
    catalog = PSLAdapter(
        minimum_expected_programmes=3,
        workers=2,
    ).parse_catalog_from_fetcher(_fetcher)
    programme = next(item for item in catalog.programmes if "durabilite" in item.id)

    assert [
        (window.round, window.opens_at, window.closes_at)
        for window in programme.windows
    ] == [
        ("Fall 2027 session 1", "2027-01-15", "2027-02-24"),
        ("Fall 2027 session 2", "2027-05-18", "2027-06-22"),
    ]
    assert all(window.applicant_categories == ["all"] for window in programme.windows)
    assert all(window.source_url == SUSTAINABILITY_URL for window in programme.windows)
    assert programme.parse_status == "parsed"


def test_psl_adapter_filters_stale_application_cycles() -> None:
    catalog = PSLAdapter(
        minimum_expected_programmes=3,
        workers=2,
    ).parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item for item in catalog.programmes if item.id == "psl-computer-science-master"
    )

    assert programme.windows == []
    assert programme.parse_status == "no-deadline"
    assert "16 mars 2026" in programme.deadline_text


def test_psl_adapter_labels_master_grade_programmes_separately() -> None:
    catalog = PSLAdapter(
        minimum_expected_programmes=3,
        workers=2,
    ).parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item for item in catalog.programmes if "cycle-ingenieur" in item.id
    )

    assert programme.degree_type == "Grade de master"
    assert programme.name == "Cycle ingénieur civil MINES Paris - PSL"
    assert programme.faculty == "Mines Paris PSL"
    assert programme.application_url == APPLICATION_URL


def test_psl_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="expected at least 4"):
        PSLAdapter(
            minimum_expected_programmes=4,
            workers=2,
        ).parse_catalog_from_fetcher(_fetcher)


def test_psl_adapter_retries_a_transient_detail_failure() -> None:
    attempts = 0

    def fetcher(url: str) -> str:
        nonlocal attempts
        if url == SUSTAINABILITY_URL:
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary disconnect")
        return _fetcher(url)

    catalog = PSLAdapter(
        minimum_expected_programmes=3,
        workers=2,
    ).parse_catalog_from_fetcher(fetcher)

    assert len(catalog.programmes) == 3
    assert attempts == 2


def test_psl_adapter_propagates_a_persistent_detail_failure() -> None:
    def fetcher(url: str) -> str:
        if url == SUSTAINABILITY_URL:
            raise RuntimeError("still unavailable")
        return _fetcher(url)

    with pytest.raises(RuntimeError, match="still unavailable"):
        PSLAdapter(
            minimum_expected_programmes=3,
            workers=2,
        ).parse_catalog_from_fetcher(fetcher)
