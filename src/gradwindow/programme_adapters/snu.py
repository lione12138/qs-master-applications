from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin, urlparse

import pdfplumber
from bs4 import BeautifulSoup
from pypdf import PdfReader

from ..http_client import DEFAULT_USER_AGENT, fetch_page
from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "seoul-national-university"
CATALOG_URL = "https://en.snu.ac.kr/admission/graduate/application"
APPLICATION_URL = "https://en.snu.ac.kr/admission"
GUIDE_URL = (
    "https://en.snu.ac.kr/webdata/uploads/eng/file/2026/06/2027Spring_graduate_eng.pdf"
)

_GUIDE_URL_RE = re.compile(r"(?P<year>20\d{2})Spring_graduate_eng\.pdf$")
_INTAKE_RE = re.compile(
    r"(?P<year>20\d{2})\s+Spring Graduate Admissions Guide",
    re.IGNORECASE,
)
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December"
)
_APPLICATION_RANGE_RE = re.compile(
    rf"Online Application.*?"
    rf"(?P<start_month>{_MONTHS})\s+(?P<start_day>\d{{1,2}}),\s*"
    rf"(?P<start_year>20\d{{2}}),\s*\d{{1,2}}:\d{{2}}\s*[-–]\s*"
    rf"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*"
    rf"(?P<end_month>{_MONTHS})\s+(?P<end_day>\d{{1,2}}),\s*"
    rf"(?P<end_year>20\d{{2}}),\s*\d{{1,2}}:\d{{2}}",
    re.IGNORECASE | re.DOTALL,
)

PdfPayloadFetcher = Callable[[str], str]


class SNUAdapter(BaseProgrammeAdapter):
    """Discover SNU master's offerings from its international admissions guide."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Spring (March) 2027"
    application_opens_at_basis = "official"
    replace_pending_candidates = True
    known_programme_window_scope_type = "programme-group"
    known_programme_window_scope_id = "snu-international-graduate-admissions"

    def __init__(
        self,
        minimum_expected_programmes: int = 200,
        target_intake_year: int = 2027,
        pdf_payload_fetcher: PdfPayloadFetcher | None = None,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.target_intake_year = target_intake_year
        self.intake = f"Spring (March) {target_intake_year}"
        self.pdf_payload_fetcher = pdf_payload_fetcher or _fetch_pdf_payload

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        guide_url = _latest_guide_url(fetcher(CATALOG_URL))
        payload = json.loads(self.pdf_payload_fetcher(guide_url))
        guide_text = str(payload.get("text", ""))
        guide_year, windows = _guide_windows(
            guide_text,
            source_url=guide_url,
            target_intake_year=self.target_intake_year,
        )
        rows = [row for row in payload.get("rows", []) if _normalise(row.get("m"))]
        programmes = _programmes(
            rows,
            source_url=guide_url,
            guide_year=guide_year,
            target_intake_year=self.target_intake_year,
            windows=windows,
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "SNU official guide only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("SNU official guide generated duplicate programme IDs")
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _latest_guide_url(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for link in soup.select("a[href]"):
        url = urljoin(CATALOG_URL, str(link.get("href", "")))
        match = _GUIDE_URL_RE.search(urlparse(url).path)
        if match and _is_official_pdf(url):
            candidates.append((int(match.group("year")), url))
    if not candidates:
        raise ValueError(
            "SNU application page did not link a graduate admissions guide"
        )
    return max(candidates, key=lambda item: item[0])[1]


def _guide_windows(
    text: str,
    *,
    source_url: str,
    target_intake_year: int,
) -> tuple[int, list[DiscoveredWindow]]:
    intake_match = _INTAKE_RE.search(text)
    range_match = _APPLICATION_RANGE_RE.search(text)
    if intake_match is None or range_match is None:
        raise ValueError("SNU guide did not contain its intake and application range")
    guide_year = int(intake_match.group("year"))
    opens_at = _month_date(
        range_match.group("start_month"),
        range_match.group("start_day"),
        range_match.group("start_year"),
    )
    closes_at = _month_date(
        range_match.group("end_month"),
        range_match.group("end_day"),
        range_match.group("end_year"),
    )
    if guide_year != target_intake_year:
        return guide_year, []
    return guide_year, [
        DiscoveredWindow(
            round="International graduate admissions",
            applicant_categories=["international-students"],
            opens_at=opens_at,
            closes_at=closes_at,
            intake=f"Spring (March) {guide_year}",
            source_url=source_url,
        )
    ]


def _month_date(month: str, day: str, year: str) -> str:
    return datetime.strptime(f"{month} {day} {year}", "%B %d %Y").date().isoformat()


def _programmes(
    rows: list[dict],
    *,
    source_url: str,
    guide_year: int,
    target_intake_year: int,
    windows: list[DiscoveredWindow],
) -> list[DiscoveredProgramme]:
    programmes = []
    for row in rows:
        college = _clean_label(row.get("college"))
        department = _clean_label(row.get("department"))
        major = _clean_label(row.get("major")) or department
        if not college or not department or not major:
            raise ValueError(
                "SNU guide contained a master's row without programme scope"
            )
        display_name = re.sub(r"\s+Major$", "", major, flags=re.IGNORECASE)
        existing_cs = (
            college == "College of Engineering"
            and department == "Computer Science and Engineering"
            and major == "Computer Science and Engineering"
        )
        if existing_cs:
            programme_id = "snu-computer-science-engineering-master"
            name = "Master's in Computer Science and Engineering"
        else:
            programme_id = (
                f"snu-{_slug(college)}-{_slug(department)}-{_slug(display_name)}-master"
            )
            name = f"Master's in {display_name}"
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=name,
                degree_type="Master",
                faculty=college,
                department=department,
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=list(windows),
                deadline_text=_deadline_text(
                    guide_year=guide_year,
                    target_intake_year=target_intake_year,
                    has_target_window=bool(windows),
                ),
                parse_status="parsed" if windows else "no-deadline",
                retrieval_method="official-international-admissions-guide-pdf-table",
                evidence_quality="official-full-text",
            )
        )
    return sorted(programmes, key=lambda item: item.id)


def _deadline_text(
    *,
    guide_year: int,
    target_intake_year: int,
    has_target_window: bool,
) -> str:
    if has_target_window:
        return (
            f"SNU's official Spring {guide_year} international graduate guide "
            "publishes one exact online application period for this programme."
        )
    return (
        f"SNU's official Spring {guide_year} guide was checked, but it is stale "
        f"for Spring {target_intake_year}; no exact target-cycle window is published."
    )


def _fetch_pdf_payload(url: str) -> str:
    page = fetch_page(
        url,
        user_agent=DEFAULT_USER_AGENT,
        timeout=45,
        max_bytes=8_000_000,
        accept="application/pdf,*/*;q=0.8",
    )
    if page.truncated:
        raise ValueError("SNU admissions PDF exceeded the download limit")
    if "application/pdf" not in page.content_type.lower():
        raise ValueError("SNU admissions guide did not return a PDF")
    reader = PdfReader(BytesIO(page.raw_bytes))
    text = "\n".join(
        value
        for pdf_page in reader.pages
        if (value := (pdf_page.extract_text() or "").strip())
    )
    rows = _extract_pdf_rows(page.raw_bytes)
    return json.dumps({"text": text, "rows": rows}, ensure_ascii=False)


def _extract_pdf_rows(raw_bytes: bytes) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current_college = ""
    current_department = ""
    in_programme_tables = False
    with pdfplumber.open(BytesIO(raw_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if "The following are the programs available for graduate" in page_text:
                in_programme_tables = True
            if in_programme_tables and "Appendix 1" in page_text:
                break
            if not in_programme_tables:
                continue
            geometry = _table_geometry(page)
            if geometry is None:
                continue
            columns, boundaries = geometry
            college_groups = _column_groups(
                page,
                columns[0],
                columns[1],
                boundaries[0],
                boundaries[-1],
            )
            group_index = 0
            for top, bottom in zip(boundaries, boundaries[1:], strict=False):
                midpoint = (top + bottom) / 2
                while (
                    group_index < len(college_groups)
                    and college_groups[group_index][0] <= midpoint
                ):
                    current_college = college_groups[group_index][1]
                    current_department = ""
                    group_index += 1
                department = _crop_text(page, columns[1], top, columns[2], bottom)
                major = _crop_text(page, columns[2], top, columns[3], bottom)
                if department:
                    current_department = department
                rows.append(
                    {
                        "college": current_college,
                        "department": current_department,
                        "major": major or current_department,
                        "m": _crop_text(page, columns[3], top, columns[4], bottom),
                        "c": _crop_text(page, columns[4], top, columns[5], bottom),
                        "d": _crop_text(page, columns[5], top, columns[6], bottom),
                    }
                )
    return rows


def _table_geometry(page) -> tuple[list[float], list[float]] | None:
    horizontal = [
        (line["top"], line["x0"], line["x1"])
        for line in page.lines
        if abs(line["top"] - line["bottom"]) < 0.5
    ]
    if not horizontal:
        return None
    _, left, right = max(horizontal, key=lambda item: item[2] - item[1])
    full_width = sorted(
        {
            round(top, 2)
            for top, x0, x1 in horizontal
            if abs(x0 - left) < 1 and abs(x1 - right) < 1
        }
    )
    if len(full_width) < 2:
        return None
    table_top, header_bottom = full_width[:2]
    raw_columns = []
    for rectangle in page.rects:
        if (
            rectangle["top"] >= table_top - 0.5
            and rectangle["bottom"] <= header_bottom + 0.5
        ):
            raw_columns.extend([rectangle["x0"], rectangle["x1"]])
    columns = _dedupe_coordinates(raw_columns)
    if len(columns) != 7:
        return None
    boundaries = sorted(
        {
            round(top, 2)
            for top, x0, x1 in horizontal
            if (top >= header_bottom - 0.5 and abs(x1 - right) < 1 and x0 >= left - 1)
        }
    )
    if len(boundaries) < 2:
        return None
    return columns, boundaries


def _column_groups(
    page,
    x0: float,
    x1: float,
    top: float,
    bottom: float,
) -> list[tuple[float, str]]:
    words = [
        word
        for word in page.extract_words()
        if x0 - 1 <= word["x0"] < x1 and top - 1 <= word["top"] < bottom + 1
    ]
    lines: list[list] = []
    for word in words:
        for line in lines:
            if abs(line[0] - word["top"]) < 2:
                line[1].append(word)
                break
        else:
            lines.append([word["top"], [word]])
    values = [
        (
            line_top,
            " ".join(
                word["text"] for word in sorted(line_words, key=lambda item: item["x0"])
            ),
        )
        for line_top, line_words in sorted(lines)
    ]
    groups: list[list] = []
    for line_top, text in values:
        if groups and line_top - groups[-1][1] <= 14.5:
            groups[-1][1] = line_top
            groups[-1][2] = f"{groups[-1][2]} {text}"
        else:
            groups.append([line_top, line_top, text])
    return [(group[0], _clean_label(group[2])) for group in groups]


def _crop_text(page, x0: float, top: float, x1: float, bottom: float) -> str:
    text = page.crop((x0 - 0.5, top, x1 + 0.5, bottom)).extract_text() or ""
    return _clean_label(text)


def _dedupe_coordinates(values: list[float]) -> list[float]:
    coordinates = []
    for value in sorted(values):
        if not coordinates or abs(value - coordinates[-1]) > 1:
            coordinates.append(value)
    return coordinates


def _clean_label(value: object) -> str:
    text = _normalise(value).lstrip("*#").strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    return text


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _slug(value: object) -> str:
    text = (
        unicodedata.normalize("NFKD", _normalise(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "programme"


def _is_official_pdf(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.lower().endswith("snu.ac.kr")
        and parsed.path.lower().endswith(".pdf")
    )
