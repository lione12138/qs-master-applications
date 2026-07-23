from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from urllib.parse import parse_qs, urljoin, urlparse, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "university-of-california-los-angeles-ucla"
CATALOG_URL = "https://grad.ucla.edu/"
APPLICATION_URL = (
    "https://grad.ucla.edu/admissions/admission-application-for-graduate-admission/"
)
EXISTING_CS_ID = "ucla-computer-science-ms"


class UCLAAdapter(BaseProgrammeAdapter):
    """Discover independently-admitting master's programs from UCLA's A-Z list."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Fall 2027 or latest program-specific intake"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 100,
        maximum_expected_programmes: int = 115,
        detail_workers: int = 12,
        maximum_detail_failures: int = 5,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.detail_workers = detail_workers
        self.maximum_detail_failures = maximum_detail_failures

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        programmes = _catalogue_programmes(fetcher(CATALOG_URL))
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "UCLA's official A-Z directory only contained "
                f"{len(programmes)} independently-admitting master's programs; "
                f"expected at least {self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "UCLA's official A-Z directory unexpectedly contained "
                f"{len(programmes)} independently-admitting master's programs; "
                f"expected at most {self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("UCLA official A-Z directory generated duplicate IDs")

        failures = []

        def parse_one(programme: DiscoveredProgramme) -> DiscoveredProgramme:
            try:
                detail_html = fetcher(programme.source_url)
                requirements_url = _requirements_url(detail_html)
                if requirements_url is None:
                    return replace(
                        programme,
                        deadline_text=(
                            "UCLA's official program page does not expose a central "
                            "admission-requirements record. No exact application opening "
                            "and closing date pair is inferred."
                        ),
                    )
                return _parse_requirements(
                    programme,
                    fetcher(requirements_url),
                    requirements_url=requirements_url,
                )
            except Exception as exc:
                failures.append((programme.id, type(exc).__name__, str(exc)[:180]))
                return replace(
                    programme,
                    deadline_text=(
                        "Official UCLA program requirements could not be checked during "
                        f"discovery: {type(exc).__name__}: {str(exc)[:180]}"
                    ),
                )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            detailed = list(executor.map(parse_one, programmes))
        if len(failures) > self.maximum_detail_failures:
            sample = "; ".join(": ".join(item) for item in failures[:3])
            raise ValueError(
                f"UCLA detail discovery failed for {len(failures)} programs: {sample}"
            )
        return DiscoveredCatalog(
            application_opens_at=None,
            programmes=sorted(detailed, key=lambda item: item.id),
        )


def _catalogue_programmes(html: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes = []
    for container in soup.select(".major-container"):
        link = container.select_one('.title a[href*="/programs/"]')
        master_labels = [
            _normalise(node.get("title"))
            for node in container.select(
                '.degree-content .circle[title^="Masters offered:"]'
            )
        ]
        standalone_labels = [
            label for label in master_labels if "only on PhD-track" not in label
        ]
        if link is None or not standalone_labels:
            continue
        name = _normalise(link.get_text(" ", strip=True))
        source_url = _canonical_program_url(urljoin(CATALOG_URL, str(link["href"])))
        programme_id = (
            EXISTING_CS_ID if name == "Computer Science" else f"ucla-{_slug(name)}"
        )
        degree_type = " / ".join(
            label.removeprefix("Masters offered:").strip()
            for label in standalone_labels
        )
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=name,
                degree_type=degree_type,
                faculty=_faculty_from_url(source_url),
                department=name,
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=[],
                deadline_text=(
                    "Program found in UCLA's official A-Z graduate directory; its "
                    "program-specific admission requirements are pending inspection."
                ),
                parse_status="no-deadline",
                retrieval_method="official-graduate-a-z-and-requirements-html",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _requirements_url(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.select('a[href*="/requirements/"]'):
        url = urljoin(CATALOG_URL, str(link["href"]))
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if (
            parsed.scheme == "https"
            and parsed.hostname == "grad.ucla.edu"
            and parsed.path == "/requirements/"
            and query.get("app") == ["admission"]
            and query.get("major")
        ):
            return url
    return None


def _parse_requirements(
    programme: DiscoveredProgramme,
    html: str,
    *,
    requirements_url: str,
) -> DiscoveredProgramme:
    soup = BeautifulSoup(html, "html.parser")
    deadline = _section_value(soup, "Deadlines to apply")
    cycle = _requirements_cycle(soup)
    if deadline:
        evidence = (
            f"UCLA's official {cycle + ' ' if cycle else ''}program requirements "
            f"publish the closing deadline text '{deadline}' at {requirements_url}, "
            "but no exact application opening date. No opening date is inferred."
        )
    else:
        evidence = (
            "UCLA's official program requirements record currently leaves the "
            "deadline field empty and publishes no exact opening and closing date "
            f"pair. Requirements record: {requirements_url}"
        )
    return replace(programme, deadline_text=evidence)


def _section_value(soup: BeautifulSoup, heading: str) -> str:
    for node in soup.find_all("h3"):
        if _normalise(node.get_text(" ", strip=True)) != heading:
            continue
        row = node.find_parent("tr")
        value_row = row.find_next_sibling("tr") if row else None
        return _normalise(value_row.get_text(" ", strip=True)) if value_row else ""
    return ""


def _requirements_cycle(soup: BeautifulSoup) -> str:
    heading = soup.find(
        string=lambda value: (
            value and "Admission Requirements for the Graduate Major" in value
        )
    )
    text = _normalise(heading)
    match = re.search(r"(20\d{2}-20\d{2})", text)
    return match.group(1) if match else ""


def _canonical_program_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "grad.ucla.edu"
        or not parsed.path.startswith("/programs/")
    ):
        raise ValueError(f"UCLA A-Z directory contained a non-official URL: {value}")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _faculty_from_url(value: str) -> str:
    parts = [part for part in urlparse(value).path.split("/") if part]
    if len(parts) < 2:
        return "UCLA"
    return " ".join(
        word.upper() if word == "ucla" else word.title() for word in parts[1].split("-")
    )


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _slug(value: object) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", _normalise(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
