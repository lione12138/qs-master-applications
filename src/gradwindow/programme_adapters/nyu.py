from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "new-york-university-nyu"
CATALOG_URL = "https://bulletins.nyu.edu/programs/"
APPLICATION_URL = "https://www.nyu.edu/admissions/graduate-admissions.html"
TANDON_APPLICATION_URL = "https://apply.engineering.nyu.edu/apply/"
EXISTING_TANDON_CS_ID = "nyu-tandon-computer-science-ms"

_BULLETIN_RE = re.compile(r"\b(?P<start>20\d{2})-20\d{2}\s+Bulletins\b", re.I)
_DEGREE_RE = re.compile(r"\((?P<degree>[^()]+)\)\s*$")


class NYUAdapter(BaseProgrammeAdapter):
    """Discover graduate master's programmes from NYU's central bulletin."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Varies by NYU school and programme"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 225,
        maximum_expected_programmes: int = 240,
        minimum_bulletin_year: int = 2026,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.minimum_bulletin_year = minimum_bulletin_year

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        bulletin_year = _bulletin_year(html)
        if bulletin_year < self.minimum_bulletin_year:
            raise ValueError(
                f"NYU's current bulletin begins in {bulletin_year}; expected "
                f"{self.minimum_bulletin_year} or later"
            )
        programmes = _programmes(html, bulletin_year=bulletin_year)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "NYU's official programme finder only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "NYU's official programme finder unexpectedly contained "
                f"{len(programmes)} master's programmes; expected at most "
                f"{self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("NYU programme finder generated duplicate IDs")
        return DiscoveredCatalog(
            application_opens_at=None,
            programmes=sorted(programmes, key=lambda item: item.id),
        )


def _bulletin_year(html: str) -> int:
    text = _normalise(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    match = _BULLETIN_RE.search(text)
    if match is None:
        raise ValueError("NYU programme finder lacked a current bulletin year")
    return int(match.group("start"))


def _programmes(html: str, *, bulletin_year: int) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes = []
    seen_urls = set()
    for item in soup.select("li.item"):
        title_node = item.select_one("span.title")
        link = item.select_one("a[href]")
        if title_node is None or link is None:
            continue
        keywords = [
            _normalise(node.get_text(" ", strip=True))
            for node in item.select("span.keyword")
        ]
        if (
            "Masters" not in keywords
            or "Graduate" not in keywords
            or "Undergraduate" in keywords
            or "Bachelors" in keywords
        ):
            continue
        source_url = urljoin(CATALOG_URL, str(link["href"]))
        if not _is_official_programme_url(source_url):
            raise ValueError(
                f"NYU programme finder linked an invalid URL: {source_url}"
            )
        if source_url in seen_urls:
            continue
        title = _normalise(title_node.get_text(" ", strip=True))
        degree_match = _DEGREE_RE.search(title)
        if degree_match is None:
            raise ValueError(f"NYU master's programme lacked a degree label: {title}")
        graduate_index = keywords.index("Graduate")
        if graduate_index + 1 >= len(keywords):
            raise ValueError(f"NYU master's programme lacked a school: {title}")
        faculty = keywords[graduate_index + 1]
        is_existing_cs = title == "Computer Science Tandon (MS)"
        digest = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:12]
        display_name = "MS in Computer Science" if is_existing_cs else title
        programmes.append(
            DiscoveredProgramme(
                id=(
                    EXISTING_TANDON_CS_ID if is_existing_cs else f"nyu-master-{digest}"
                ),
                name=display_name,
                degree_type=degree_match.group("degree"),
                faculty=faculty,
                department=_DEGREE_RE.sub("", title).strip(),
                source_url=source_url,
                application_url=(
                    TANDON_APPLICATION_URL if is_existing_cs else APPLICATION_URL
                ),
                windows=[],
                deadline_text=(
                    f"NYU's official {bulletin_year}-{bulletin_year + 1} bulletin "
                    "confirms this graduate master's programme, but the central "
                    "programme record does not publish an exact application opening "
                    "and closing date. School-level admissions review remains required."
                ),
                parse_status="no-deadline",
                retrieval_method="official-central-bulletin-programme-finder-html",
                evidence_quality="official-full-text",
            )
        )
        seen_urls.add(source_url)
    return programmes


def _is_official_programme_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "bulletins.nyu.edu"
        and parsed.path.startswith("/graduate/")
        and "/programs/" in parsed.path
    )


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())
