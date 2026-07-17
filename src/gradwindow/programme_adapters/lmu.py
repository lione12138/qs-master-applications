from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "ludwig-maximilians-universit-t-m-nchen"
CATALOG_URL = (
    "https://www.lmu.de/en/study/all-degrees-and-programs/"
    "international-degree-programs/index.html"
)
APPLICATIONS_URL = (
    "https://www.lmu.de/en/study/degree-students/applications-for-admission/index.html"
)
APPLICATION_URL = APPLICATIONS_URL
MOVEIN_URL = "https://lmu.gomovein.com"
EXISTING_STATISTICS_ID = "lmu-statistics-data-science-msc"
EXISTING_STATISTICS_APPLICATION_URL = (
    "https://www.stat.lmu.de/en/studies/interested-master/"
)

_SECTION_NAMES = (
    "English-taught master's degree programs",
    "Double degree programs",
    "Erasmus Mundus",
)
_DATE_RANGE_RE = re.compile(
    r"portal is open from (?P<opens>\d{1,2}\s+[A-Za-z]+\s+20\d{2}) "
    r"until (?P<closes>\d{1,2}\s+[A-Za-z]+\s+20\d{2})",
    re.I,
)
_MOVEIN_PROGRAMMES = {
    "biochemistry": "Biochemistry",
    "epidemiology": "Epidemiology",
    "quantitative economics": "Quantitative Economics",
    "statistics and data science": "Statistics and Data Science",
}


class LMUAdapter(BaseProgrammeAdapter):
    """Discover LMU's international master's programmes and exact MoveIN window."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Winter semester 2026/27"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 46,
        maximum_expected_programmes: int = 53,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        movein_programmes, opens_at, closes_at = _movein_window(
            fetcher(APPLICATIONS_URL)
        )
        programmes = _programmes(
            fetcher(CATALOG_URL),
            movein_programmes=movein_programmes,
            opens_at=opens_at,
            closes_at=closes_at,
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "LMU's official international catalogue only contained "
                f"{len(programmes)} international master's programmes; expected at "
                f"least {self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "LMU's official international catalogue unexpectedly contained "
                f"{len(programmes)} international master's programmes; expected at "
                f"most {self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("LMU international catalogue generated duplicate IDs")
        return DiscoveredCatalog(
            application_opens_at=opens_at,
            programmes=sorted(programmes, key=lambda item: item.id),
        )


def _movein_window(html: str) -> tuple[set[str], str, str]:
    soup = BeautifulSoup(html, "html.parser")
    link = next(
        (
            item
            for item in soup.select("a[href]")
            if "MoveIN" in item.get_text(" ", strip=True)
        ),
        None,
    )
    container = link.find_parent("dd") if link else None
    if container is None or _canonical_url(str(link["href"])) != MOVEIN_URL:
        raise ValueError(
            "LMU application page lacked the official MoveIN programme list"
        )
    text = _normalise(container.get_text(" ", strip=True))
    match = _DATE_RANGE_RE.search(text)
    if match is None:
        raise ValueError(
            "LMU application page lacked exact MoveIN opening and closing dates"
        )
    opens_at = _parse_date(match.group("opens"))
    closes_at = _parse_date(match.group("closes"))
    if date.fromisoformat(closes_at) <= date.fromisoformat(opens_at):
        raise ValueError("LMU MoveIN window had an invalid date range")
    folded = _fold(text)
    present = {
        canonical
        for canonical, official_name in _MOVEIN_PROGRAMMES.items()
        if _fold(official_name) in folded
        or (
            canonical == "statistics and data science"
            and "statistics & data science" in text.lower()
        )
    }
    if present != set(_MOVEIN_PROGRAMMES):
        raise ValueError(
            "LMU MoveIN list lacked expected international master's programmes"
        )
    return present, opens_at, closes_at


def _programmes(
    html: str,
    *,
    movein_programmes: set[str],
    opens_at: str,
    closes_at: str,
) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for section_name in _SECTION_NAMES[:2]:
        heading = _heading(soup, section_name)
        container = heading.find_next_sibling("div", class_="link-list__container")
        if container is None:
            raise ValueError(f"LMU catalogue lacked the {section_name} list")
        entries.extend(
            (
                section_name,
                _normalise(link.get_text(" ", strip=True)),
                _canonical_url(str(link["href"])),
            )
            for link in container.select("a[href]")
        )
    erasmus_heading = _heading(soup, _SECTION_NAMES[2])
    erasmus_container = erasmus_heading.find_next_sibling(
        "div", class_="text-module__text"
    )
    if erasmus_container is None:
        raise ValueError("LMU catalogue lacked the Erasmus Mundus list")
    for item in erasmus_container.select("li"):
        programme_link = next(
            (
                link
                for link in item.select("a[href]")
                if not str(link["href"]).startswith("mailto:")
            ),
            None,
        )
        text = _normalise(item.get_text(" ", strip=True))
        name_match = re.match(r"(?P<name>Master(?:'s)? Program.*?)\s*\(", text)
        if programme_link is None or name_match is None:
            raise ValueError("LMU Erasmus Mundus list contained an invalid programme")
        entries.append(
            (
                _SECTION_NAMES[2],
                _normalise(name_match.group("name")),
                _canonical_url(str(programme_link["href"])),
            )
        )

    programmes = []
    seen = set()
    for section, raw_name, programme_url in entries:
        canonical = _programme_key(raw_name, programme_url)
        if canonical in seen:
            continue
        movein_key = _movein_key(raw_name)
        has_window = movein_key in movein_programmes
        is_statistics = movein_key == "statistics and data science"
        digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]
        windows = (
            [
                DiscoveredWindow(
                    round="International Office MoveIN application",
                    opens_at=opens_at,
                    closes_at=closes_at,
                    intake="Winter semester 2026/27",
                    applicant_categories=["international-students"],
                    source_url=APPLICATIONS_URL,
                )
            ]
            if has_window
            else []
        )
        display_name = "MSc Statistics and Data Science" if is_statistics else raw_name
        programmes.append(
            DiscoveredProgramme(
                id=(
                    EXISTING_STATISTICS_ID
                    if is_statistics
                    else f"lmu-international-master-{digest}"
                ),
                name=display_name,
                degree_type=_degree_type(raw_name),
                faculty="LMU Munich",
                department=section,
                source_url=CATALOG_URL,
                application_url=(
                    EXISTING_STATISTICS_APPLICATION_URL
                    if is_statistics
                    else (MOVEIN_URL if has_window else APPLICATION_URL)
                ),
                windows=windows,
                deadline_text=(
                    "LMU's official international catalogue lists this programme. "
                    + (
                        "The official International Office page publishes the exact "
                        f"MoveIN period {opens_at} through {closes_at}."
                        if has_window
                        else "Application procedures vary by programme and the central "
                        "catalogue does not publish an exact opening date for this entry."
                    )
                ),
                parse_status="parsed" if has_window else "no-deadline",
                retrieval_method="official-international-degree-programmes-html",
                evidence_quality="official-full-text",
            )
        )
        seen.add(canonical)
    return programmes


def _heading(soup: BeautifulSoup, label: str):
    heading = next(
        (
            item
            for item in soup.select("main h2")
            if _normalise(item.get_text(" ", strip=True)) == label
        ),
        None,
    )
    if heading is None:
        raise ValueError(f"LMU catalogue lacked the {label} section")
    return heading


def _movein_key(value: str) -> str:
    folded = _fold(value)
    folded = re.sub(r"\s*\(ws\)\s*$", "", folded)
    return folded


def _programme_key(name: str, url: str) -> str:
    folded = _fold(name)
    if "management" in folded and "international triple degree" in folded:
        return "management-international-triple-degree"
    if "journalism" in folded:
        return "journalism-media-globalisation"
    if "green finance" in folded or "greening energy market" in folded:
        return "grenfin-emjm"
    return f"{folded}|{url}"


def _degree_type(name: str) -> str:
    lowered = name.lower()
    if "ll.m" in lowered:
        return "LLM"
    if "executive master" in lowered:
        return "Executive Master"
    return "Master"


def _parse_date(value: str) -> str:
    for pattern in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"LMU application page contained an invalid date: {value}")


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"LMU catalogue contained an invalid programme URL: {value}")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _fold(value: object) -> str:
    return _normalise(value).replace("&", "and").replace("—", "-").lower()


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())
