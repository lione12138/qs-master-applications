from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable
from datetime import date
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "fudan-university"
CATALOG_URL = "https://iso.fudan.edu.cn/isoenglish/EnglishwTaughtProgram/list.htm"
GRADUATE_LIST_URL = "https://iso.fudan.edu.cn/isoenglish/51328/list.htm"
CHINESE_CATALOG_LIST_URL = "https://iso.fudan.edu.cn/16063/list.htm"
APPLICATION_URL = "https://istudent.fudan.edu.cn/apply"

_ADMISSIONS_TITLE_RE = re.compile(
    r"(?P<year>20\d{2})\s+Admission Information on English-taught "
    r"Postgraduate Programs",
    re.IGNORECASE,
)
_CHINESE_CATALOG_TITLE_RE = re.compile(
    r"(?P<year>20\d{2})年复旦大学外国留学生中文授课硕士研究生招生专业目录"
)
_CHINESE_ADMISSIONS_TITLE_RE = re.compile(
    r"(?P<year>20\d{2})年.*外国留学生.*中文授课项目招生简章"
)
_CHINESE_DEGREE_RE = re.compile(r"^[（(](?P<type>学术学位|专业学位)[）)]")
_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_PATTERN = "|".join(month.title() for month in _MONTHS)
_PHASE_RE = re.compile(
    rf"Phase\s+(?P<phase>One|Two)\s*:\s*From\s+"
    rf"(?P<sm>{_MONTH_PATTERN})\s+(?P<sd>\d{{1,2}}),?\s+(?P<sy>20\d{{2}})"
    rf"\s+to\s+"
    rf"(?P<em>{_MONTH_PATTERN})\s+(?P<ed>\d{{1,2}}),?\s+(?P<ey>20\d{{2}})",
    re.IGNORECASE,
)
_CHINESE_PHASE_RE = re.compile(
    r"第\s*(?P<phase>一|二)\s*阶段\s*[：:]\s*"
    r"(?P<sy>20\d{2})\s*年\s*(?P<sm>\d{1,2})\s*月\s*"
    r"(?P<sd>\d{1,2})\s*日\s*至\s*"
    r"(?P<ey>20\d{2})\s*年\s*(?P<em>\d{1,2})\s*月\s*"
    r"(?P<ed>\d{1,2})\s*日"
)


class FudanAdapter(BaseProgrammeAdapter):
    """Discover Fudan's current English-taught international master's catalog."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Latest published autumn international intake"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_english_programmes: int = 24,
        minimum_expected_chinese_programmes: int = 130,
    ) -> None:
        self.minimum_expected_english_programmes = minimum_expected_english_programmes
        self.minimum_expected_chinese_programmes = minimum_expected_chinese_programmes

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        first_html = fetcher(CATALOG_URL)
        pages = [first_html]
        pages.extend(
            fetcher(catalog_page_url(page))
            for page in range(2, _page_count(first_html) + 1)
        )
        programmes_by_id = {
            programme.id: programme
            for page in pages
            for programme in _catalogue_programmes(page)
        }
        english_programmes = sorted(programmes_by_id.values(), key=lambda item: item.id)
        if len(english_programmes) < self.minimum_expected_english_programmes:
            raise ValueError(
                "Fudan official English-taught catalogue only contained "
                f"{len(english_programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_english_programmes}"
            )

        intake_year, admissions_page_url = _latest_admissions_page(
            fetcher(GRADUATE_LIST_URL)
        )
        admissions_pdf_url = _admissions_pdf_url(
            fetcher(admissions_page_url),
            expected_year=intake_year,
            taught_label="English-taught",
        )
        english_windows = _application_windows(
            fetcher(admissions_pdf_url),
            intake_year=intake_year,
            source_url=admissions_pdf_url,
        )
        english_evidence = "; ".join(
            f"{window.round}: {window.opens_at} to {window.closes_at}"
            for window in english_windows
        )
        for programme in english_programmes:
            programme.windows = list(english_windows)
            programme.deadline_text = (
                f"Fudan's official {intake_year} English-taught postgraduate "
                f"admissions brochure publishes {english_evidence}."
            )
            programme.parse_status = "parsed"

        (
            chinese_year,
            chinese_catalog_url,
            chinese_admissions_page_url,
        ) = _latest_chinese_sources(fetcher(CHINESE_CATALOG_LIST_URL))
        if chinese_year != intake_year:
            raise ValueError(
                "Fudan English- and Chinese-taught catalogues published different years"
            )
        chinese_programmes = _chinese_catalogue_programmes(
            fetcher(chinese_catalog_url),
            source_url=chinese_catalog_url,
            expected_year=chinese_year,
        )
        if len(chinese_programmes) < self.minimum_expected_chinese_programmes:
            raise ValueError(
                "Fudan official Chinese-taught catalogue only contained "
                f"{len(chinese_programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_chinese_programmes}"
            )
        chinese_pdf_url = _admissions_pdf_url(
            fetcher(chinese_admissions_page_url),
            expected_year=chinese_year,
            taught_label="Chinese-taught",
        )
        chinese_windows = _application_windows(
            fetcher(chinese_pdf_url),
            intake_year=chinese_year,
            source_url=chinese_pdf_url,
        )
        chinese_evidence = "; ".join(
            f"{window.round}: {window.opens_at} to {window.closes_at}"
            for window in chinese_windows
        )
        for programme in chinese_programmes:
            programme.windows = list(chinese_windows)
            programme.deadline_text = (
                f"Fudan's official {chinese_year} Chinese-taught postgraduate "
                f"admissions brochure publishes {chinese_evidence}."
            )
            programme.parse_status = "parsed"
        programmes = sorted(
            [*english_programmes, *chinese_programmes], key=lambda item: item.id
        )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def catalog_page_url(page: int) -> str:
    if page == 1:
        return CATALOG_URL
    return f"https://iso.fudan.edu.cn/isoenglish/EnglishwTaughtProgram/list{page}.htm"


def _page_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    value = soup.select_one(".all_pages")
    if value is None:
        return 1
    text = _normalise(value.get_text(" ", strip=True))
    return int(text) if text.isdigit() else 1


def _catalogue_programmes(html: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes = []
    for link in soup.select(".news_title a[href][title]"):
        title = _normalise(link.get("title"))
        if not _is_master_title(title):
            continue
        source_url = urljoin(CATALOG_URL, str(link.get("href", "")))
        if not _is_official_page(source_url):
            continue
        programmes.append(
            DiscoveredProgramme(
                id=f"fudan-{_slug(title)}",
                name=title,
                degree_type=_degree_type(title),
                faculty="Fudan University",
                department="",
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=[],
                deadline_text=(
                    "Programme found in Fudan International Students Office's "
                    "official English-taught programme index."
                ),
                parse_status="no-deadline",
                retrieval_method=(
                    "official-iso-programme-index-and-admissions-brochure"
                ),
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _latest_admissions_page(html: str) -> tuple[int, str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for link in soup.select("a[href][title]"):
        match = _ADMISSIONS_TITLE_RE.search(_normalise(link.get("title")))
        if match is None:
            continue
        page_url = urljoin(GRADUATE_LIST_URL, str(link.get("href", "")))
        if _is_official_page(page_url):
            candidates.append((int(match.group("year")), page_url))
    if not candidates:
        raise ValueError(
            "Fudan graduate list did not contain an English-taught admissions page"
        )
    return max(candidates, key=lambda item: item[0])


def _latest_chinese_sources(html: str) -> tuple[int, str, str]:
    soup = BeautifulSoup(html, "html.parser")
    catalogues: dict[int, str] = {}
    admissions: dict[int, str] = {}
    for link in soup.select("a[href][title]"):
        title = _normalise(link.get("title"))
        source_url = urljoin(CHINESE_CATALOG_LIST_URL, str(link.get("href", "")))
        catalog_match = _CHINESE_CATALOG_TITLE_RE.search(title)
        if catalog_match and _is_official_xlsx(source_url):
            catalogues[int(catalog_match.group("year"))] = source_url
        admissions_match = _CHINESE_ADMISSIONS_TITLE_RE.search(title)
        if admissions_match and _is_official_page(source_url):
            admissions[int(admissions_match.group("year"))] = source_url
    years = sorted(set(catalogues) & set(admissions))
    if not years:
        raise ValueError(
            "Fudan Chinese-taught list did not contain matching current catalogue "
            "and admissions sources"
        )
    year = years[-1]
    return year, catalogues[year], admissions[year]


def _chinese_catalogue_programmes(
    value: str,
    *,
    source_url: str,
    expected_year: int,
) -> list[DiscoveredProgramme]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Fudan Chinese-taught catalogue did not return XLSX rows"
        ) from exc
    sheets = payload.get("worksheets") if isinstance(payload, dict) else None
    if not isinstance(sheets, list):
        raise ValueError("Fudan Chinese-taught catalogue payload is invalid")
    sheet = next(
        (
            item
            for item in sheets
            if isinstance(item, dict) and "硕士中文招生专业" in str(item.get("name"))
        ),
        None,
    )
    rows = sheet.get("rows") if sheet else None
    if not isinstance(rows, list) or len(rows) < 3:
        raise ValueError("Fudan Chinese-taught catalogue worksheet is empty")
    if str(expected_year) not in _normalise(rows[0][0] if rows[0] else ""):
        raise ValueError("Fudan Chinese-taught catalogue has an unexpected year")

    faculty = ""
    major = ""
    programmes: dict[str, DiscoveredProgramme] = {}
    for row in rows[2:]:
        if not isinstance(row, list) or len(row) < 4:
            continue
        faculty = _normalise(row[1]) or faculty
        major = _normalise(row[2]) or major
        direction = _normalise(row[3])
        match = _CHINESE_DEGREE_RE.match(major)
        if not faculty or match is None or not direction:
            continue
        name = _CHINESE_DEGREE_RE.sub("", major).strip()
        canonical = f"{faculty}|{major}|Chinese"
        digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]
        programme_id = f"fudan-cn-master-{digest}"
        programmes.setdefault(
            programme_id,
            DiscoveredProgramme(
                id=programme_id,
                name=f"{name}（中文授课）",
                degree_type=(
                    "Academic Master"
                    if match.group("type") == "学术学位"
                    else "Professional Master"
                ),
                faculty=faculty,
                department="",
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=[],
                deadline_text=(
                    "Programme found in Fudan's official Chinese-taught "
                    "international master's XLSX catalogue."
                ),
                parse_status="no-deadline",
                retrieval_method="official-iso-xlsx-and-admissions-brochure",
                evidence_quality="official-full-text",
            ),
        )
    return sorted(programmes.values(), key=lambda item: item.id)


def _admissions_pdf_url(
    html: str,
    *,
    expected_year: int,
    taught_label: str,
) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for player in soup.select(".wp_pdf_player[pdfsrc]"):
        title = _normalise(player.get("sudyfile-attr"))
        pdf_url = urljoin(GRADUATE_LIST_URL, str(player.get("pdfsrc", "")))
        title_matches = f"{taught_label} Postgraduate Programs" in title
        if taught_label == "Chinese-taught":
            title_matches = title_matches or "中文授课" in title
        if str(expected_year) in title and title_matches and _is_official_pdf(pdf_url):
            return pdf_url
    raise ValueError(
        f"Fudan admissions page did not link its current {taught_label} brochure"
    )


def _application_windows(
    text: str,
    *,
    intake_year: int,
    source_url: str,
) -> list[DiscoveredWindow]:
    normalised = _normalise(text)
    events = [
        (
            match.group("phase").title(),
            _date_from_match(match, "s"),
            _date_from_match(match, "e"),
        )
        for match in _PHASE_RE.finditer(normalised)
    ]
    events.extend(
        (
            "One" if match.group("phase") == "一" else "Two",
            _numeric_date_from_match(match, "s"),
            _numeric_date_from_match(match, "e"),
        )
        for match in _CHINESE_PHASE_RE.finditer(normalised)
    )
    phases = {phase for phase, _, _ in events}
    if phases != {"One", "Two"} or len(events) != 2:
        raise ValueError(
            "Fudan admissions brochure did not contain two exact application phases"
        )
    windows = []
    for phase, opens_at, closes_at in events:
        windows.append(
            DiscoveredWindow(
                round=f"Phase {phase}",
                intake=f"Autumn {intake_year}",
                opens_at=opens_at,
                closes_at=closes_at,
                applicant_categories=["international-students"],
                source_url=source_url,
            )
        )
    if max(int(window.closes_at[:4]) for window in windows) != intake_year:
        raise ValueError(
            "Fudan admissions brochure dates did not match its published intake year"
        )
    return windows


def _date_from_match(match: re.Match[str], prefix: str) -> str:
    return date(
        int(match.group(f"{prefix}y")),
        _MONTHS[match.group(f"{prefix}m").lower()],
        int(match.group(f"{prefix}d")),
    ).isoformat()


def _numeric_date_from_match(match: re.Match[str], prefix: str) -> str:
    return date(
        int(match.group(f"{prefix}y")),
        int(match.group(f"{prefix}m")),
        int(match.group(f"{prefix}d")),
    ).isoformat()


def _is_master_title(title: str) -> bool:
    lowered = title.lower()
    excluded = ("doctoral", "phd", "bachelor", "undergraduate", "mbbs")
    if any(value in lowered for value in excluded):
        return False
    return any(value in lowered for value in ("master", "mba", "ll.m", "double degree"))


def _degree_type(title: str) -> str:
    lowered = title.lower()
    if "ll.m" in lowered:
        return "LLM"
    if "mba" in lowered:
        return "MBA"
    return "Master"


def _is_official_page(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname == "iso.fudan.edu.cn"


def _is_official_pdf(value: str) -> bool:
    return _is_official_page(value) and urlparse(value).path.lower().endswith(".pdf")


def _is_official_xlsx(value: str) -> bool:
    return _is_official_page(value) and urlparse(value).path.lower().endswith(".xlsx")


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.decode().lower()).strip("-")


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()
