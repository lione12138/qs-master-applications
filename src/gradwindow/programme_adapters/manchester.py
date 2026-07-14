from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "the-university-of-manchester"
CATALOG_URL = "https://www.manchester.ac.uk/study/masters/courses/list/basic/"
APPLICATION_URL = "https://www.manchester.ac.uk/study/masters/admissions/how-to-apply/"
AMBS_APPLICATION_URL = (
    "https://www.alliancembs.manchester.ac.uk/study/masters/how-to-apply/"
)
COURSE_PATH_RE = re.compile(
    r"^/study/masters/courses/list/(?P<code>\d{5})/(?P<slug>[^/]+)/?$",
    re.I,
)
DEGREE_RE = re.compile(
    r"\b(?P<degree>MSc|MA|MRes|MPhil|MEng|MEd|LLM|MBA|MPH|MPP|MPA|"
    r"MMus|MusM|MArch|MClin\s+Res|Master(?:'s)?(?:\s+of)?)\b",
    re.I,
)
DATE_TEXT = r"\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+\s+20\d{2}"
STAGE_DEADLINE_RE = re.compile(
    rf"(?:Stage|Round)\s*(?P<number>\d+)\s*:?.{{0,80}}?"
    rf"Application(?:s)?\s+received\s+by\s+(?P<date>{DATE_TEXT})",
    re.I,
)
NAMED_DEADLINE_RE = re.compile(
    rf"(?:the\s+)?application\s+(?:closing\s+)?deadline"
    rf"(?:\s+for\s+this\s+course)?\s*(?:is|:)?\s*(?P<date>{DATE_TEXT})",
    re.I,
)
CLOSES_RE = re.compile(
    rf"applications?\s+(?:close|closes|must\s+be\s+submitted)"
    rf"(?:\s+on|\s+by|\s*:)?\s*(?P<date>{DATE_TEXT})",
    re.I,
)
INTAKE_RE = re.compile(r"\b(20\d{2})\s+entry\b", re.I)


@dataclass(frozen=True, slots=True)
class SharedDeadlineRule:
    windows: tuple[DiscoveredWindow, ...]
    excerpt: str


class ManchesterAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    application_opens_at_basis = "missing"
    replace_pending_candidates = True
    intake = "September 2026"

    def __init__(
        self,
        minimum_expected_programmes: int = 260,
        detail_workers: int = 10,
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
                "University of Manchester catalogue only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )

        try:
            ambs_rule = _parse_ambs_rule(fetcher(AMBS_APPLICATION_URL))
        except Exception:
            ambs_rule = None

        def parse_one(programme: DiscoveredProgramme) -> DiscoveredProgramme:
            try:
                detailed = _parse_detail(programme, fetcher(programme.source_url))
                return _apply_ambs_rule(detailed, ambs_rule)
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
    programmes = {}
    for link in soup.find_all("a", href=True):
        title = _normalise(link.get_text(" ", strip=True))
        if not DEGREE_RE.search(title):
            continue
        source_url = _course_url(link["href"])
        if source_url is None:
            continue
        programme_id = f"manchester-{_slug(title)}"
        programmes[programme_id] = DiscoveredProgramme(
            id=programme_id,
            name=title,
            degree_type=_degree_type(title),
            faculty="",
            department="",
            source_url=source_url,
            application_url=APPLICATION_URL,
            windows=[],
            deadline_text=(
                "Programme found in the official University of Manchester "
                "master's catalogue; no exact application deadline was found."
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
    heading = soup.find("h1")
    heading_text = _normalise(heading.get_text(" ", strip=True)) if heading else ""
    title = heading_text if DEGREE_RE.search(heading_text) else programme.name
    page_text = _normalise(soup.get_text(" ", strip=True))
    intake_match = INTAKE_RE.search(page_text)
    intake = f"September {intake_match.group(1)}" if intake_match else "September 2026"
    application_text = _application_section_text(soup)
    windows = _application_windows(application_text, intake, programme.source_url)
    department = _definition_value(soup, "Department")
    faculty = _definition_value(soup, "School/Faculty") or department
    excerpt = _deadline_excerpt(application_text)
    return replace(
        programme,
        id=f"manchester-{_slug(title)}",
        name=title,
        degree_type=_degree_type(title),
        faculty=faculty,
        department=department,
        windows=windows,
        deadline_text=(
            excerpt
            if excerpt
            else (
                "The official course page does not publish an exact application "
                "closing date. Manchester states that many master's courses do "
                "not have official closing dates."
            )
        ),
        parse_status="incomplete" if windows else "no-deadline",
    )


def _parse_ambs_rule(html: str) -> SharedDeadlineRule | None:
    soup = BeautifulSoup(html, "html.parser")
    text = _normalise(soup.get_text(" ", strip=True))
    opening = re.search(
        rf"Applications for September\s+(?P<intake>20\d{{2}})\s+entry\s+"
        rf"will open on\s+(?P<opens>{DATE_TEXT})",
        text,
        re.I,
    )
    if opening is None:
        return None
    opens_at = _date(opening.group("opens"))
    windows = []
    for row in soup.select("tr"):
        cells = [
            _normalise(cell.get_text(" ", strip=True)) for cell in row.select("td")
        ]
        if len(cells) < 2 or not cells[0].isdigit():
            continue
        try:
            closes_at = _date(cells[1])
        except ValueError:
            continue
        windows.append(
            DiscoveredWindow(
                round=f"Stage {cells[0]}",
                opens_at=opens_at,
                closes_at=closes_at,
                intake=f"September {opening.group('intake')}",
                source_url=AMBS_APPLICATION_URL,
            )
        )
    if not windows:
        return None
    return SharedDeadlineRule(
        windows=tuple(windows),
        excerpt=(
            "Alliance Manchester Business School publishes a shared opening date "
            "and staged application deadlines for its September 2026 master's "
            "courses."
        ),
    )


def _apply_ambs_rule(
    programme: DiscoveredProgramme,
    rule: SharedDeadlineRule | None,
) -> DiscoveredProgramme:
    if (
        rule is None
        or programme.faculty != "Alliance Manchester Business School"
        or programme.degree_type not in {"MSc", "MA"}
    ):
        return programme
    return replace(
        programme,
        windows=list(rule.windows),
        deadline_text=rule.excerpt,
        parse_status="parsed",
    )


def _application_section_text(soup: BeautifulSoup) -> str:
    heading = next(
        (
            item
            for item in soup.find_all(["h2", "h3"])
            if _normalise(item.get_text(" ", strip=True)).lower()
            == "application and selection"
        ),
        None,
    )
    if heading is None:
        return ""
    parts = []
    for item in heading.find_all_next(["h2", "h3", "p", "li"]):
        if item.name == "h2" and item is not heading:
            break
        text = _normalise(item.get_text(" ", strip=True))
        if text:
            parts.append(text)
    return " ".join(parts)


def _application_windows(
    text: str,
    intake: str,
    source_url: str,
) -> list[DiscoveredWindow]:
    windows = []
    seen_dates = set()
    previous_stage_date = ""
    for match in STAGE_DEADLINE_RE.finditer(text):
        closes_at = _date(match.group("date"))
        if closes_at in seen_dates or (
            previous_stage_date and closes_at <= previous_stage_date
        ):
            continue
        seen_dates.add(closes_at)
        previous_stage_date = closes_at
        windows.append(
            DiscoveredWindow(
                round=f"Stage {match.group('number')}",
                opens_at=None,
                closes_at=closes_at,
                intake=intake,
                source_url=source_url,
            )
        )
    if windows:
        return windows
    for pattern in (NAMED_DEADLINE_RE, CLOSES_RE):
        for match in pattern.finditer(text):
            closes_at = _date(match.group("date"))
            if closes_at in seen_dates:
                continue
            seen_dates.add(closes_at)
            windows.append(
                DiscoveredWindow(
                    round="Application deadline",
                    opens_at=None,
                    closes_at=closes_at,
                    intake=intake,
                    source_url=source_url,
                )
            )
    return windows


def _deadline_excerpt(text: str) -> str:
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    relevant = [
        sentence
        for sentence in sentences
        if STAGE_DEADLINE_RE.search(sentence)
        or NAMED_DEADLINE_RE.search(sentence)
        or CLOSES_RE.search(sentence)
    ]
    return " ".join(relevant)[:1500]


def _definition_value(soup: BeautifulSoup, label: str) -> str:
    term = next(
        (
            item
            for item in soup.find_all("dt")
            if _normalise(item.get_text(" ", strip=True)).lower() == label.lower()
        ),
        None,
    )
    if term is None:
        return ""
    value = term.find_next_sibling("dd")
    return _normalise(value.get_text(" ", strip=True)) if value else ""


def _course_url(href: str) -> str | None:
    absolute = urljoin(CATALOG_URL, href)
    parts = urlsplit(absolute)
    if COURSE_PATH_RE.match(parts.path) is None:
        return None
    return urlunsplit(("https", "www.manchester.ac.uk", parts.path, "", ""))


def _degree_type(title: str) -> str:
    match = DEGREE_RE.search(title)
    if match is None:
        return "Master"
    degree = _normalise(match.group("degree"))
    return "Master" if degree.lower().startswith("master") else degree


def _date(value: str) -> str:
    cleaned = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", value, flags=re.I)
    for date_format in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(cleaned, date_format).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported Manchester application date: {value}")


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def _normalise(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())
