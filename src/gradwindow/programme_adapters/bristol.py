from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "university-of-bristol"
CATALOG_URL = "https://www.bristol.ac.uk/study/postgraduate/search/"
APPLICATION_URL = (
    "https://www.bristol.ac.uk/study/postgraduate/apply/start-application/"
)
DEFAULT_INTAKE = "September 2026"
CURRENT_TAUGHT_PATH_RE = re.compile(r"^/study/postgraduate/taught/[^/]+/?$", re.I)
MASTER_AWARD_RE = re.compile(
    r"\b(?:MSc|MA|MRes|MEd|LLM|MBA|MPH|MFA|MMus|MArch|MSci|Master)\b",
    re.I,
)
DEGREE_RE = re.compile(
    r"^(?P<degree>MSc|MA|MRes|MEd|LLM|MBA|MPH|MFA|MMus|MArch|MSci|Master)\b",
    re.I,
)
FULL_DATE_TEXT = r"\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+\s+20\d{2}"
INTAKE_DEADLINE_RE = re.compile(
    rf"For\s+(?P<intake>[A-Z][a-z]+\s+20\d{{2}})\s+start\s*:\s*"
    rf"(?P<date>{FULL_DATE_TEXT})",
    re.I,
)
OVERSEAS_DEADLINE_RE = re.compile(
    rf"\bOverseas(?:\s+applicants?)?\s*:\s*(?P<date>{FULL_DATE_TEXT})",
    re.I,
)
HOME_DEADLINE_RE = re.compile(
    rf"\bHome(?:\s+applicants?)?\s*:\s*(?P<date>{FULL_DATE_TEXT})",
    re.I,
)
DATE_RE = re.compile(FULL_DATE_TEXT)
INTAKE_RE = re.compile(r"\b(?P<month>[A-Z][a-z]+)\s+(?P<year>20\d{2})\b")
PROGRAMME_ID_ALIASES = {
    "MSc Computer Science (Conversion)": "bristol-computer-science-conversion-msc",
}


class BristolAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    application_opens_at_basis = "missing"
    replace_pending_candidates = True
    intake = DEFAULT_INTAKE

    def __init__(
        self,
        minimum_expected_programmes: int = 140,
        detail_workers: int = 12,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.detail_workers = detail_workers

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        programmes = _catalogue_programmes(fetcher(CATALOG_URL))
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "University of Bristol catalogue only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes} current taught programmes"
            )

        def parse_one(programme: DiscoveredProgramme) -> DiscoveredProgramme:
            try:
                return _parse_detail(programme, fetcher(programme.source_url))
            except Exception as exc:
                return replace(
                    programme,
                    deadline_text=(
                        "Official programme page could not be checked during "
                        f"discovery: {type(exc).__name__}: {str(exc)[:180]}"
                    ),
                )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            detailed = list(executor.map(parse_one, programmes))
        return DiscoveredCatalog(application_opens_at=None, programmes=detailed)


def _catalogue_programmes(html: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes: dict[str, DiscoveredProgramme] = {}
    for article in soup.select("article.search-result--course"):
        badge = article.select_one(".badge")
        if (
            badge is None
            or "taught postgraduate" not in badge.get_text(" ", strip=True).lower()
        ):
            continue
        link = article.find("a", href=True)
        heading = article.find("h1")
        awards = _definition_value(article, "Awards available")
        if link is None or heading is None or not MASTER_AWARD_RE.search(awards):
            continue
        source_url = _current_programme_url(link.get("href", ""))
        name = _normalise(heading.get_text(" ", strip=True))
        degree_type = _degree_type(name)
        if source_url is None or not name or degree_type is None:
            continue
        programme_id = PROGRAMME_ID_ALIASES.get(name, f"bristol-{_slug(name)}")
        programmes[programme_id] = DiscoveredProgramme(
            id=programme_id,
            name=name,
            degree_type=degree_type,
            faculty="",
            department="",
            source_url=source_url,
            application_url=APPLICATION_URL,
            windows=[],
            deadline_text=(
                "Programme found in the official University of Bristol "
                "postgraduate taught catalogue."
            ),
            parse_status="no-deadline",
            retrieval_method="official-page",
            evidence_quality="official-full-text",
        )
    return sorted(programmes.values(), key=lambda item: item.id)


def _parse_detail(
    programme: DiscoveredProgramme,
    html: str,
) -> DiscoveredProgramme:
    soup = BeautifulSoup(html, "html.parser")
    deadline_text = _definition_value(soup, "Application deadline")
    start_text = _definition_value(soup, "Start date")
    windows = _parse_windows(deadline_text, start_text, programme.source_url)
    faculty = _meta_content(soup, "faculty")
    department = _meta_content(soup, "schools")
    return replace(
        programme,
        faculty=faculty,
        department=department,
        windows=windows,
        deadline_text=deadline_text
        or (
            "The current official programme page does not publish an exact "
            "application deadline."
        ),
        parse_status="incomplete" if windows else "no-deadline",
    )


def _parse_windows(
    deadline_text: str,
    start_text: str,
    source_url: str,
) -> list[DiscoveredWindow]:
    if not deadline_text:
        return []

    intake_matches = list(INTAKE_DEADLINE_RE.finditer(deadline_text))
    if intake_matches:
        return [
            DiscoveredWindow(
                round="Final application deadline",
                closes_at=_iso_date(match.group("date")),
                applicant_categories=["all"],
                intake=_normalise(match.group("intake")),
                source_url=source_url,
            )
            for match in intake_matches
        ]

    intake = _single_intake(start_text) or DEFAULT_INTAKE
    windows = []
    overseas = OVERSEAS_DEADLINE_RE.search(deadline_text)
    home = HOME_DEADLINE_RE.search(deadline_text)
    if overseas:
        windows.append(
            DiscoveredWindow(
                round="Overseas applicants",
                closes_at=_iso_date(overseas.group("date")),
                applicant_categories=["international"],
                intake=intake,
                source_url=source_url,
            )
        )
    if home:
        windows.append(
            DiscoveredWindow(
                round="Home applicants",
                closes_at=_iso_date(home.group("date")),
                applicant_categories=["home"],
                intake=intake,
                source_url=source_url,
            )
        )
    if windows:
        return windows

    first_date = DATE_RE.search(deadline_text)
    if first_date:
        return [
            DiscoveredWindow(
                round="Final application deadline",
                closes_at=_iso_date(first_date.group(0)),
                applicant_categories=["all"],
                intake=intake,
                source_url=source_url,
            )
        ]
    return []


def _definition_value(node, label: str) -> str:
    for term in node.find_all("dt"):
        if _normalise(term.get_text(" ", strip=True)).lower() != label.lower():
            continue
        value = term.find_next_sibling("dd")
        if value is not None:
            return _normalise(value.get_text(" ", strip=True))
    return ""


def _meta_content(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"name": re.compile(rf"^{re.escape(name)}$", re.I)})
    return _normalise(tag.get("content", "")) if tag else ""


def _current_programme_url(href: str) -> str | None:
    url = urljoin(CATALOG_URL, href)
    split = urlsplit(url)
    if split.netloc.lower() not in {"bristol.ac.uk", "www.bristol.ac.uk"}:
        return None
    if not CURRENT_TAUGHT_PATH_RE.fullmatch(split.path):
        return None
    return urlunsplit(("https", "www.bristol.ac.uk", split.path, "", ""))


def _degree_type(name: str) -> str | None:
    match = DEGREE_RE.match(name)
    if not match:
        return None
    value = match.group("degree")
    if value.lower() == "master":
        return "Master"
    return value.upper() if value.lower() == "llm" else value


def _single_intake(value: str) -> str | None:
    matches = list(INTAKE_RE.finditer(value))
    if len(matches) != 1:
        return None
    return _normalise(matches[0].group(0))


def _iso_date(value: str) -> str:
    clean = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", value, flags=re.I)
    return datetime.strptime(clean, "%d %B %Y").date().isoformat()


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )
