from __future__ import annotations

from gradwindow.discovery import acceptable_page, same_official_domain, score_candidate


def test_undergraduate_page_is_not_scored_as_graduate() -> None:
    undergraduate = score_candidate(
        "https://example.edu/undergraduate/admissions",
        "Undergraduate admissions",
    )
    graduate = score_candidate(
        "https://example.edu/graduate/admissions",
        "Graduate admissions",
    )
    assert undergraduate < 0
    assert graduate > 20


def test_subdomain_is_accepted_as_official() -> None:
    assert same_official_domain("https://grad.example.edu/admissions", ["example.edu"])
    assert not same_official_domain(
        "https://example.edu.fake-site.test/admissions", ["example.edu"]
    )


def test_news_and_event_pages_are_rejected() -> None:
    assert not acceptable_page(
        "https://example.edu/news/graduate-admissions-open",
        "Graduate admissions open",
    )
    assert acceptable_page(
        "https://example.edu/graduate/admissions",
        "Graduate Admissions",
    )
