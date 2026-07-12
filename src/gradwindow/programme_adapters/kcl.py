from __future__ import annotations

import concurrent.futures
import json
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import datetime
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from .base import DiscoveredCatalog, DiscoveredProgramme, DiscoveredWindow

UNIVERSITY_ID = "king-s-college-london-kcl"
SITEMAP_URL = "https://www.kcl.ac.uk/sitemap.xml"
CATALOG_URL = "https://www.kcl.ac.uk/study/postgraduate-taught/courses"
APPLICATION_URL = "https://www.kcl.ac.uk/study/postgraduate-taught/how-to-apply"
DEFAULT_INTAKE = "September 2026"
COURSE_PATH_RE = re.compile(
    r"^/study/postgraduate-taught/courses/(?P<slug>[^/]+?)/?$",
    flags=re.IGNORECASE,
)
MASTER_DEGREE_RE = re.compile(
    r"\b(?P<degree>MSc|MRes|MPhil|MLitt|LLM|MBA|MPH|MEd|MMus|MFA|MA)\b",
    flags=re.IGNORECASE,
)
DATE_PATTERN = r"\d{1,2}\s+[A-Z][a-z]+\s+20\d{2}"
APPLICANT_DEADLINE_RE = re.compile(
    rf"(?P<label>Overseas(?:\s*\(international\))?\s+fee\s+status|"
    rf"Home\s+fee\s+status|All\s+applicants)[^:]{{0,80}}:\s*"
    rf"(?P<date>{DATE_PATTERN})",
    flags=re.IGNORECASE,
)
FIRST_DEADLINE_RE = re.compile(
    rf"(?:first|initial)\s+application\s+deadline(?:\s+is)?(?:\s+on)?\s+"
    rf"(?P<date>{DATE_PATTERN})",
    flags=re.IGNORECASE,
)
ALL_FINAL_DEADLINE_RE = re.compile(
    rf"(?:final\s+application\s+deadline|applications?\s+(?:will\s+)?close)"
    rf"[^.\n:]{{0,100}}(?:is|on|:)\s*(?P<date>{DATE_PATTERN})",
    flags=re.IGNORECASE,
)
INTAKE_RE = re.compile(
    r"(?P<term>January|September)\s+(?P<year>20\d{2})\s+intake", re.I
)
STARTUP_SCRIPT_RE = re.compile(r"startup-[^/]+\.js$")
DELIVERY_TOKEN_RE = re.compile(r'accessToken:\s*"(?P<token>[^"]+)"')
DELIVERY_API_RE = re.compile(
    r'api:\s*"https://api-"\s*\+\s*alias\s*\+\s*"\.cloud\.contensis\.com"'
)


class KCLAdapter:
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = DEFAULT_INTAKE
    application_opens_at_basis = "missing"

    def __init__(
        self,
        minimum_expected_programmes: int = 140,
        detail_workers: int = 6,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.detail_workers = detail_workers
        self.sitemap_diagnostics = "not inspected"

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        course_urls = self._course_urls(fetcher)
        if len(course_urls) < self.minimum_expected_programmes:
            raise ValueError(
                "King's College London sitemap only contained "
                f"{len(course_urls)} postgraduate taught master's course URLs; "
                f"expected at least {self.minimum_expected_programmes}. "
                f"Sitemap diagnostics: {self.sitemap_diagnostics}"
            )

        def parse_one(course_url: str) -> DiscoveredProgramme | None:
            requirements_url = f"{course_url.rstrip('/')}/requirements"
            try:
                return _parse_programme(
                    course_url, requirements_url, fetcher(requirements_url)
                )
            except Exception as exc:
                fallback = _programme_from_slug(course_url)
                if fallback is None:
                    return None
                return replace(
                    fallback,
                    deadline_text=(
                        "Course found in the official KCL sitemap, but its "
                        "requirements page could not be fetched during discovery: "
                        f"{type(exc).__name__}: {str(exc)[:180]}"
                    ),
                )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            programmes = [
                programme
                for programme in executor.map(parse_one, course_urls)
                if programme is not None
            ]
        programmes = sorted(
            {programme.id: programme for programme in programmes}.values(),
            key=lambda item: item.id,
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "King's College London discovery only produced "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)

    def _course_urls(self, fetcher: Callable[[str], str]) -> list[str]:
        root_xml = fetcher(SITEMAP_URL)
        root_locations = _xml_locations(root_xml)
        root_name = _xml_root_name(root_xml)
        course_urls = _filter_course_urls(root_locations)
        postgraduate_samples = [
            url for url in root_locations if "postgraduate" in url.lower()
        ][:8]
        self.sitemap_diagnostics = (
            f"root={root_name}, rootLocations={len(root_locations)}, "
            f"sample={root_locations[:3]}, postgraduateSample={postgraduate_samples}"
        )
        if course_urls:
            return course_urls

        if root_name != "sitemapindex":
            return self._catalogue_page_urls(fetcher)
        sitemap_urls = root_locations
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            child_payloads = list(executor.map(fetcher, sitemap_urls))
        child_locations = [
            location
            for payload in child_payloads
            for location in _xml_locations(payload)
        ]
        self.sitemap_diagnostics = (
            f"root={root_name}, rootLocations={len(root_locations)}, "
            f"childDocuments={len(child_payloads)}, "
            f"childLocations={len(child_locations)}, sample={child_locations[:3]}"
        )
        return _filter_course_urls(child_locations)

    def _catalogue_page_urls(self, fetcher: Callable[[str], str]) -> list[str]:
        html = fetcher(self.catalog_url)
        soup = BeautifulSoup(html, "html.parser")
        page_urls = _filter_course_urls(
            link.get("href", "") for link in soup.find_all("a", href=True)
        )
        startup_src = next(
            (
                script.get("src", "")
                for script in soup.find_all("script", src=True)
                if STARTUP_SCRIPT_RE.search(script.get("src", ""))
            ),
            "",
        )
        if not startup_src:
            self.sitemap_diagnostics += (
                f"; catalogueLinks={len(page_urls)}, startupScript=missing"
            )
            return page_urls

        startup_url = urljoin(self.catalog_url, startup_src)
        startup_script = fetcher(startup_url)
        token_match = DELIVERY_TOKEN_RE.search(startup_script)
        if token_match is None or DELIVERY_API_RE.search(startup_script) is None:
            self.sitemap_diagnostics += (
                f"; catalogueLinks={len(page_urls)}, deliveryConfig=missing"
            )
            return page_urls

        api_url = "https://api-kcl.cloud.contensis.com/api/delivery/projects/website/"
        api_url += "contentTypes/postgraduateCourse/entries?"
        api_url += urlencode(
            {
                "pageSize": 500,
                "versionStatus": "published",
                "language": "en-GB",
                "fields": "sys,entryTitle",
                "accessToken": token_match.group("token"),
            }
        )
        payload = json.loads(fetcher(api_url))
        api_urls = _filter_course_urls(
            item.get("sys", {}).get("uri", "") for item in payload.get("items", [])
        )
        self.sitemap_diagnostics += (
            f"; catalogueLinks={len(page_urls)}, apiTotal={payload.get('totalCount')}, "
            f"apiCourseLinks={len(api_urls)}"
        )
        return api_urls or page_urls


def _xml_locations(payload: str) -> list[str]:
    root = ElementTree.fromstring(payload)
    return [
        _normalise_text(node.text or "")
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1].lower() == "loc" and (node.text or "").strip()
    ]


def _xml_root_name(payload: str) -> str:
    return ElementTree.fromstring(payload).tag.rsplit("}", 1)[-1].lower()


def _filter_course_urls(urls: Iterable[str]) -> list[str]:
    courses = set()
    for url in urls:
        parts = urlsplit(url)
        match = COURSE_PATH_RE.match(parts.path)
        if match is None or match.group("slug").lower() == "new":
            continue
        if MASTER_DEGREE_RE.search(match.group("slug").replace("-", " ")) is None:
            continue
        courses.add(
            urlunsplit(
                (
                    parts.scheme or "https",
                    parts.netloc or "www.kcl.ac.uk",
                    parts.path.rstrip("/"),
                    "",
                    "",
                )
            )
        )
    return sorted(courses)


def _parse_programme(
    course_url: str,
    requirements_url: str,
    html: str,
) -> DiscoveredProgramme | None:
    soup = BeautifulSoup(html, "html.parser")
    title = _programme_title(soup)
    degree_match = MASTER_DEGREE_RE.search(title)
    if degree_match is None:
        return _programme_from_slug(course_url)
    degree_type = _canonical_degree(degree_match.group("degree"))
    windows, excerpt = _parse_deadlines(soup, requirements_url)
    faculty, department = _taught_in(soup)
    return DiscoveredProgramme(
        id=f"kcl-{_slug(title)}",
        name=title,
        degree_type=degree_type,
        faculty=faculty,
        department=department,
        source_url=requirements_url,
        application_url=APPLICATION_URL,
        windows=windows,
        deadline_text=excerpt
        or "No exact application deadline was found on the requirements page.",
        parse_status="incomplete" if windows else "no-deadline",
    )


def _programme_from_slug(course_url: str) -> DiscoveredProgramme | None:
    slug = urlsplit(course_url).path.rstrip("/").rsplit("/", 1)[-1]
    degree_match = MASTER_DEGREE_RE.search(slug.replace("-", " "))
    if degree_match is None:
        return None
    words = slug.replace("-", " ")
    title = " ".join(
        word.upper() if MASTER_DEGREE_RE.fullmatch(word) else word.title()
        for word in words.split()
    )
    return DiscoveredProgramme(
        id=f"kcl-{_slug(title)}",
        name=title,
        degree_type=_canonical_degree(degree_match.group("degree")),
        faculty="",
        department="",
        source_url=f"{course_url.rstrip('/')}/requirements",
        application_url=APPLICATION_URL,
        windows=[],
        deadline_text="Course found in the official KCL sitemap.",
        parse_status="no-deadline",
    )


def _programme_title(soup: BeautifulSoup) -> str:
    title = _normalise_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    title = re.split(
        r"\s+-\s+Entry Requirements|\s+\|\s+King", title, maxsplit=1, flags=re.I
    )[0]
    if MASTER_DEGREE_RE.search(title):
        return title
    heading = soup.find("h1")
    return _normalise_text(heading.get_text(" ", strip=True) if heading else title)


def _parse_deadlines(
    soup: BeautifulSoup,
    source_url: str,
) -> tuple[list[DiscoveredWindow], str]:
    text = _normalise_text(soup.get_text(" ", strip=True))
    lower = text.lower()
    start = lower.find("application closing date guidance")
    if start < 0:
        return [], ""
    end_candidates = [
        position
        for label in ("key links", "taught in", "base campus")
        if (position := lower.find(label, start + 20)) >= 0
    ]
    end = min(end_candidates) if end_candidates else min(len(text), start + 3000)
    section = text[start:end]
    candidates: list[tuple[int, str, str, list[str]]] = []
    for match in APPLICANT_DEADLINE_RE.finditer(section):
        label = match.group("label").lower()
        categories = (
            ["international"]
            if label.startswith("overseas")
            else ["home"]
            if label.startswith("home")
            else ["all"]
        )
        candidates.append(
            (
                match.start(),
                "Final application deadline",
                match.group("date"),
                categories,
            )
        )
    for match in FIRST_DEADLINE_RE.finditer(section):
        candidates.append(
            (match.start(), "First application deadline", match.group("date"), ["all"])
        )
    for match in ALL_FINAL_DEADLINE_RE.finditer(section):
        candidates.append(
            (match.start(), "Final application deadline", match.group("date"), ["all"])
        )

    windows = []
    seen = set()
    for position, round_label, date_text, categories in sorted(candidates):
        closes_at = datetime.strptime(date_text, "%d %B %Y").date().isoformat()
        intake = _intake_before(section, position) or DEFAULT_INTAKE
        identity = (round_label, tuple(categories), closes_at, intake)
        if identity in seen:
            continue
        seen.add(identity)
        windows.append(
            DiscoveredWindow(
                round=round_label,
                applicant_categories=categories,
                opens_at=None,
                closes_at=closes_at,
                intake=intake,
                source_url=source_url,
            )
        )
    return windows, section[:1800]


def _intake_before(section: str, position: int) -> str | None:
    matches = list(INTAKE_RE.finditer(section[:position]))
    if not matches:
        return None
    match = matches[-1]
    return f"{match.group('term').title()} {match.group('year')}"


def _taught_in(soup: BeautifulSoup) -> tuple[str, str]:
    heading = next(
        (
            item
            for item in soup.find_all(["h2", "h3"])
            if _normalise_text(item.get_text(" ", strip=True)).lower() == "taught in"
        ),
        None,
    )
    if heading is None:
        return "", ""
    names = []
    for item in heading.find_all_next(["a", "h3"]):
        if (
            item.name in {"h2", "h3"}
            and item is not heading
            and not item.find_parent("a")
        ):
            break
        name = _normalise_text(item.get_text(" ", strip=True))
        if name and name not in names:
            names.append(name)
        if len(names) == 2:
            break
    return (names + ["", ""])[:2]


def _canonical_degree(value: str) -> str:
    mapping = {
        "msc": "MSc",
        "mres": "MRes",
        "mphil": "MPhil",
        "mlitt": "MLitt",
        "llm": "LLM",
        "mba": "MBA",
        "mph": "MPH",
        "med": "MEd",
        "mmus": "MMus",
        "mfa": "MFA",
        "ma": "MA",
    }
    return mapping[value.lower()]


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
