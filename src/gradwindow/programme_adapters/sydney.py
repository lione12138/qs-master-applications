from __future__ import annotations

import concurrent.futures
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime
from urllib.parse import urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from .base import DiscoveredCatalog, DiscoveredProgramme, DiscoveredWindow

UNIVERSITY_ID = "the-university-of-sydney"
CATALOG_URL = "https://www.sydney.edu.au/courses/sitemap.xml"
DATES_URL = "https://www.sydney.edu.au/study/applying/application-dates.html"
APPLICATION_URL = (
    "https://www.sydney.edu.au/study/applying/how-to-apply/postgraduate-coursework.html"
)
INTAKE_YEAR = 2027
COURSE_PATH_RE = re.compile(
    r"^/courses/courses/pc/(?P<slug>(?:executive-)?master-[^/]+)\.html$",
    re.I,
)
MONTH_DATE_RE = re.compile(
    r"(?P<day>\d{1,2})\s+(?P<month>January|February|March|April|May|June|July|"
    r"August|September|October|November|December)(?:\s+(?P<year>20\d{2}))?",
    re.I,
)
SPECIFIC_DEADLINE_RE = re.compile(
    r"(?P<intake>(?:20\d{2}\s+)?(?:Start\s+year|Mid[- ]year|Semester\s*[12]|"
    r"Summer|January|February|March|July|August)(?:\s*\([^)]*\))?)"
    r"[^.;]{0,100}?applications?\s+(?:are\s+)?"
    r"(?:due|close(?:s|d)?(?:\s+on)?)\s*:?[ \t]*"
    r"(?P<date>\d{1,2}\s+[A-Z][a-z]+(?:\s+20\d{2})?)",
    re.I,
)


class SydneyAdapter:
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    application_opens_at_basis = "missing"

    def __init__(
        self,
        minimum_expected_programmes: int = 120,
        *,
        detail_workers: int = 8,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.detail_workers = detail_workers

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        course_urls = _course_urls(fetcher(self.catalog_url))
        if len(course_urls) < self.minimum_expected_programmes:
            raise ValueError(
                "University of Sydney sitemap only contained "
                f"{len(course_urls)} master's course URLs; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        general_windows, general_excerpt = _general_deadlines(
            fetcher(DATES_URL), INTAKE_YEAR
        )

        def parse_one(course_url: str) -> DiscoveredProgramme:
            programme = _programme_from_url(
                course_url,
                general_windows=general_windows,
                general_excerpt=general_excerpt,
            )
            try:
                return _parse_detail(programme, fetcher(course_url))
            except Exception as exc:
                return replace(
                    programme,
                    deadline_text=(
                        f"{general_excerpt} Course page fetch failed during this "
                        f"run: {type(exc).__name__}: {str(exc)[:160]}"
                    ),
                )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            programmes = list(executor.map(parse_one, course_urls))
        return DiscoveredCatalog(
            application_opens_at=None,
            programmes=sorted(programmes, key=lambda item: item.id),
        )


def _course_urls(xml: str) -> list[str]:
    root = ElementTree.fromstring(xml)
    urls: set[str] = set()
    for node in root.iter():
        if (
            node.tag.rsplit("}", 1)[-1].lower() != "loc"
            or not (node.text or "").strip()
        ):
            continue
        url = (node.text or "").strip().split("?", 1)[0]
        if COURSE_PATH_RE.match(urlsplit(url).path):
            urls.add(url)
    return sorted(urls)


def _general_deadlines(
    html: str,
    intake_year: int,
) -> tuple[list[DiscoveredWindow], str]:
    soup = BeautifulSoup(html, "html.parser")
    table = next(
        (
            item
            for item in soup.find_all("table")
            if "Domestic students" in item.get_text(" ", strip=True)
            and "International students" in item.get_text(" ", strip=True)
            and "Semester 1" in item.get_text(" ", strip=True)
        ),
        None,
    )
    if table is None:
        raise ValueError(
            "Sydney application dates page did not contain postgraduate dates"
        )
    headers = [
        _normalise_text(cell.get_text(" ", strip=True))
        for cell in table.find_all(["th", "td"])
        if "Semester" in cell.get_text(" ", strip=True)
    ][:2]
    if len(headers) != 2:
        headers = ["Semester 1 (Feb)", "Semester 2 (Aug)"]
    windows: list[DiscoveredWindow] = []
    excerpts: list[str] = []
    for row in table.find_all("tr"):
        cells = [
            _normalise_text(cell.get_text(" ", strip=True))
            for cell in row.find_all(["th", "td"])
        ]
        if len(cells) < 3:
            continue
        category = _category(cells[0])
        if category is None:
            continue
        excerpts.append(" | ".join(cells[:3]))
        for index, value in enumerate(cells[1:3]):
            closes_at = _relative_date(value, headers[index], intake_year)
            windows.append(
                DiscoveredWindow(
                    round="General postgraduate deadline",
                    applicant_categories=[category],
                    opens_at=None,
                    closes_at=closes_at,
                    intake=_intake(headers[index], intake_year),
                    source_url=DATES_URL,
                )
            )
    if len(windows) != 4:
        raise ValueError(
            "Sydney application dates page did not yield all four standard "
            "postgraduate deadlines"
        )
    return windows, "General postgraduate dates: " + "; ".join(excerpts)


def _programme_from_url(
    course_url: str,
    *,
    general_windows: list[DiscoveredWindow],
    general_excerpt: str,
) -> DiscoveredProgramme:
    slug = COURSE_PATH_RE.match(urlsplit(course_url).path).group("slug")  # type: ignore[union-attr]
    title = " ".join(word.capitalize() for word in slug.split("-"))
    return DiscoveredProgramme(
        id=f"sydney-{slug.lower()}",
        name=title,
        degree_type="Master",
        faculty="",
        department="",
        source_url=course_url,
        application_url=APPLICATION_URL,
        windows=[replace(window) for window in general_windows],
        deadline_text=(
            f"{general_excerpt}. These are general dates; the official course "
            "page remains authoritative for exceptions."
        ),
        parse_status="incomplete",
    )


def _parse_detail(
    programme: DiscoveredProgramme,
    html: str,
) -> DiscoveredProgramme:
    soup = BeautifulSoup(html, "html.parser")
    title = _page_title(soup) or programme.name
    text = _normalise_text(soup.get_text(" ", strip=True))
    specific_windows = _specific_deadlines(text, programme.source_url)
    faculty = _meta_content(soup, "course:faculty")
    return replace(
        programme,
        name=title if "Master" in title else programme.name,
        faculty=faculty,
        windows=specific_windows or programme.windows,
        deadline_text=(
            _deadline_excerpt(text) if specific_windows else programme.deadline_text
        ),
        parse_status="incomplete",
    )


def _page_title(soup: BeautifulSoup) -> str | None:
    candidates: list[str] = []
    heading = soup.find("h1")
    if heading is not None:
        candidates.append(_normalise_text(heading.get_text(" ", strip=True)))
    meta = soup.find("meta", property="og:title")
    if meta and meta.get("content"):
        candidates.append(_normalise_text(str(meta["content"])))
    if soup.title:
        candidates.append(_normalise_text(soup.title.get_text(" ", strip=True)))
    for candidate in candidates:
        candidate = re.split(
            r"\s+[|–-]\s+(?:The )?University of Sydney",
            candidate,
            maxsplit=1,
            flags=re.I,
        )[0]
        if re.search(r"\b(?:Executive\s+)?Master\b", candidate, re.I):
            return candidate
    return None


def _specific_deadlines(text: str, source_url: str) -> list[DiscoveredWindow]:
    category = _page_category(text)
    windows: list[DiscoveredWindow] = []
    for match in SPECIFIC_DEADLINE_RE.finditer(text):
        intake = _intake(match.group("intake"), INTAKE_YEAR)
        closes_at = _absolute_or_intake_date(match.group("date"), intake)
        windows.append(
            DiscoveredWindow(
                round="Course-specific application deadline",
                applicant_categories=[category],
                opens_at=None,
                closes_at=closes_at,
                intake=intake,
                source_url=source_url,
            )
        )
    return _dedupe_windows(windows)


def _relative_date(value: str, intake: str, intake_year: int) -> str:
    match = MONTH_DATE_RE.search(value)
    if match is None:
        raise ValueError(f"Could not parse Sydney deadline: {value}")
    year = int(match.group("year")) if match.group("year") else intake_year
    if "prior" in value.lower():
        year = intake_year - 1
    month = datetime.strptime(match.group("month").capitalize(), "%B").month
    return date(year, month, int(match.group("day"))).isoformat()


def _absolute_or_intake_date(value: str, intake: str) -> str:
    match = MONTH_DATE_RE.search(value)
    if match is None:
        raise ValueError(value)
    intake_year = int(re.search(r"20\d{2}", intake).group())  # type: ignore[union-attr]
    year = int(match.group("year")) if match.group("year") else intake_year
    month = datetime.strptime(match.group("month").capitalize(), "%B").month
    return date(year, month, int(match.group("day"))).isoformat()


def _intake(value: str, year: int) -> str:
    value_lower = value.lower()
    explicit_year = re.search(r"20\d{2}", value)
    intake_year = int(explicit_year.group()) if explicit_year else year
    if (
        "semester 2" in value_lower
        or "mid" in value_lower
        or "july" in value_lower
        or "august" in value_lower
    ):
        return f"Semester 2 {intake_year}"
    if "summer" in value_lower or "january" in value_lower:
        return f"Summer {intake_year}"
    return f"Semester 1 {intake_year}"


def _category(value: str) -> str | None:
    value_lower = value.lower()
    if "domestic" in value_lower:
        return "domestic-students"
    if "international" in value_lower:
        return "international-students"
    return None


def _page_category(text: str) -> str:
    if "For international students" in text and "For domestic students" not in text:
        return "international-students"
    if "For domestic students" in text and "For international students" not in text:
        return "domestic-students"
    return "all"


def _meta_content(soup: BeautifulSoup, name: str) -> str:
    meta = soup.find("meta", attrs={"name": name})
    return _normalise_text(str(meta.get("content", ""))) if meta else ""


def _deadline_excerpt(text: str) -> str:
    match = re.search(
        r".{0,120}applications?\s+(?:are\s+)?(?:due|close).{0,220}", text, re.I
    )
    return match.group(0) if match else "Course-specific deadline found."


def _dedupe_windows(windows: list[DiscoveredWindow]) -> list[DiscoveredWindow]:
    unique: dict[tuple[str, str, tuple[str, ...]], DiscoveredWindow] = {}
    for window in windows:
        key = (
            window.intake or "",
            window.closes_at,
            tuple(window.applicant_categories),
        )
        unique[key] = window
    return sorted(unique.values(), key=lambda item: (item.intake or "", item.closes_at))


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
