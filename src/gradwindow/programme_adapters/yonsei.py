from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
from io import BytesIO
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import pdfplumber
from bs4 import BeautifulSoup

from ..http_client import DEFAULT_USER_AGENT
from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "yonsei-university"
GUIDE_INDEX_URL = (
    "https://graduate.yonsei.ac.kr/graduate_en/admission/forein_schedule.do"
)
SCHEDULE_URL = "https://graduate.yonsei.ac.kr/graduate/admission/schedule.do"
APPLICATION_URL = "https://www.gradnet.co.kr/"
SEOUL_GUIDE_URL = (
    "https://graduate.yonsei.ac.kr/_res/graduate/etc/s_f_guide_2026-1_e.pdf"
)
MIRAE_GUIDE_URL = (
    "https://graduate.yonsei.ac.kr/_res/graduate/etc/m_f_guide_2026-1_e.pdf"
)

_GUIDE_RE = re.compile(
    r"/(?P<campus>[sm])_f_guide_(?P<year>20\d{2})-1_e\.pdf$",
    re.IGNORECASE,
)
_DATE_RANGE_RE = re.compile(
    r"(?P<open_year>20\d{2})\.\s*(?P<open_month>\d{1,2})\.\s*"
    r"(?P<open_day>\d{1,2})\..*?~\s*"
    r"(?P<close_month>\d{1,2})\.\s*(?P<close_day>\d{1,2})\.",
    re.DOTALL,
)

PdfPayloadFetcher = Callable[[str], str]


class YonseiAdapter(BaseProgrammeAdapter):
    """Discover international-track master's programmes from Yonsei guides."""

    university_id = UNIVERSITY_ID
    catalog_url = GUIDE_INDEX_URL
    application_url = APPLICATION_URL
    intake = "Spring (March) 2027"
    application_opens_at_basis = "official"
    replace_pending_candidates = True
    known_programme_window_scope_type = "programme-group"
    known_programme_window_scope_id = "yonsei-international-graduate-admissions"

    def __init__(
        self,
        minimum_expected_programmes: int = 105,
        target_intake_year: int = 2027,
        pdf_payload_fetcher: PdfPayloadFetcher | None = None,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.target_intake_year = target_intake_year
        self.intake = f"Spring (March) {target_intake_year}"
        self.pdf_payload_fetcher = pdf_payload_fetcher or _fetch_pdf_payload

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        guide_urls = _latest_guide_urls(fetcher(GUIDE_INDEX_URL))
        windows = _schedule_windows(
            fetcher(SCHEDULE_URL),
            target_intake_year=self.target_intake_year,
        )
        programmes = []
        for guide_url in guide_urls:
            payload = json.loads(self.pdf_payload_fetcher(guide_url))
            guide_year = int(payload.get("guideYear", 0))
            programmes.extend(
                _programmes(
                    payload.get("rows", []),
                    guide_url=guide_url,
                    guide_year=guide_year,
                    windows=windows,
                    target_intake_year=self.target_intake_year,
                )
            )
        programmes = sorted(programmes, key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Yonsei official guides only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("Yonsei official guides generated duplicate programme IDs")
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _latest_guide_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: dict[int, dict[str, str]] = {}
    for link in soup.select("a[href]"):
        url = urljoin(GUIDE_INDEX_URL, str(link.get("href", "")))
        parsed = urlparse(url)
        match = _GUIDE_RE.search(parsed.path)
        if (
            match
            and parsed.scheme == "https"
            and parsed.hostname == "graduate.yonsei.ac.kr"
        ):
            candidates.setdefault(int(match.group("year")), {})[
                match.group("campus").lower()
            ] = url
    complete = [
        (year, urls) for year, urls in candidates.items() if set(urls) == {"s", "m"}
    ]
    if not complete:
        raise ValueError(
            "Yonsei admissions page did not link both English campus guides"
        )
    _, urls = max(complete, key=lambda item: item[0])
    return [urls["s"], urls["m"]]


def _schedule_windows(
    html: str,
    *,
    target_intake_year: int,
) -> list[DiscoveredWindow]:
    soup = BeautifulSoup(html, "html.parser")
    current_year = None
    for row in soup.select("table tr"):
        cells = [
            _normalise(cell.get_text(" ", strip=True)) for cell in row.select("th,td")
        ]
        row_text = " ".join(cells)
        year_match = re.search(r"(20\d{2})년\s*전기", row_text)
        if year_match:
            current_year = int(year_match.group(1))
        if "외국인전형" not in row_text or current_year != target_intake_year:
            continue
        date_match = _DATE_RANGE_RE.search(row_text)
        if date_match is None:
            raise ValueError("Yonsei international schedule lacked an exact date range")
        application_year = int(date_match.group("open_year"))
        return [
            DiscoveredWindow(
                round="International student track",
                applicant_categories=["international-students"],
                opens_at=_iso_date(
                    application_year,
                    date_match.group("open_month"),
                    date_match.group("open_day"),
                ),
                closes_at=_iso_date(
                    application_year,
                    date_match.group("close_month"),
                    date_match.group("close_day"),
                ),
                intake=f"Spring (March) {target_intake_year}",
                source_url=SCHEDULE_URL,
            )
        ]
    return []


def _iso_date(year: int, month: str, day: str) -> str:
    return f"{year:04d}-{int(month):02d}-{int(day):02d}"


def _programmes(
    rows: list[dict],
    *,
    guide_url: str,
    guide_year: int,
    windows: list[DiscoveredWindow],
    target_intake_year: int,
) -> list[DiscoveredProgramme]:
    programmes = []
    for row in rows:
        if not row.get("master"):
            continue
        campus = _normalise(row.get("campus"))
        college = _normalise(row.get("college"))
        department = _normalise(row.get("department"))
        if not campus or not college or not department:
            raise ValueError("Yonsei guide contained a master's row without scope")
        existing_cs = campus == "Sinchon Campus" and department == "Computer Science"
        programme_id = (
            "yonsei-computer-science-master"
            if existing_cs
            else f"yonsei-{_slug(campus)}-{_slug(department)}-master"
        )
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=f"Master's in {department}",
                degree_type="Master",
                faculty=f"{campus} | {college}",
                department=department,
                source_url=guide_url,
                application_url=APPLICATION_URL,
                windows=list(windows),
                deadline_text=_deadline_text(
                    guide_year=guide_year,
                    target_intake_year=target_intake_year,
                    has_target_window=bool(windows),
                ),
                parse_status="parsed" if windows else "no-deadline",
                retrieval_method="official-international-guide-pdf-table-and-schedule-html",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _deadline_text(
    *,
    guide_year: int,
    target_intake_year: int,
    has_target_window: bool,
) -> str:
    if has_target_window:
        return (
            f"The latest English Spring {guide_year} international guide confirms "
            "master's eligibility, and Yonsei's official admissions schedule publishes "
            f"the exact Spring {target_intake_year} international application period."
        )
    return (
        f"The latest English Spring {guide_year} international guide confirms master's "
        f"eligibility, but the official schedule does not yet publish an exact Spring "
        f"{target_intake_year} international application period."
    )


def _fetch_pdf_payload(url: str) -> str:
    raw_bytes = _fetch_pdf_bytes(url)
    guide_match = _GUIDE_RE.search(urlparse(url).path)
    if guide_match is None:
        raise ValueError("Yonsei admissions guide URL did not identify its cycle")
    rows = _extract_pdf_rows(
        raw_bytes,
        mirae=guide_match.group("campus").lower() == "m",
    )
    return json.dumps(
        {"guideYear": int(guide_match.group("year")), "rows": rows},
        ensure_ascii=False,
    )


def _fetch_pdf_bytes(url: str) -> bytes:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "graduate.yonsei.ac.kr"
        or not parsed.path.lower().endswith(".pdf")
    ):
        raise ValueError(f"Yonsei guide URL is not an official PDF: {url}")
    request = Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/pdf,*/*;q=0.8",
        },
    )
    last_error = "incomplete response"
    for _ in range(3):
        try:
            with urlopen(request, timeout=90) as response:
                content_type = response.headers.get("Content-Type", "")
                expected_length = int(response.headers.get("Content-Length", "0") or 0)
                raw_bytes = response.read(8_000_001)
        except OSError as exc:
            last_error = str(exc)
            continue
        if len(raw_bytes) > 8_000_000:
            raise ValueError("Yonsei admissions PDF exceeded the download limit")
        if "application/pdf" not in content_type.lower() or not raw_bytes.startswith(
            b"%PDF"
        ):
            raise ValueError("Yonsei admissions guide did not return a PDF")
        if expected_length and len(raw_bytes) != expected_length:
            last_error = f"received {len(raw_bytes)} of {expected_length} bytes"
            continue
        if b"%%EOF" not in raw_bytes[-1024:]:
            last_error = "PDF response did not include its EOF marker"
            continue
        return raw_bytes
    raise ValueError(f"Yonsei admissions PDF download failed: {last_error}")


def _extract_pdf_rows(raw_bytes: bytes, *, mirae: bool) -> list[dict]:
    rows = []
    current_college = ""
    with pdfplumber.open(BytesIO(raw_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            compact_text = re.sub(r"\s+", "", page_text)
            if "CollegeDepartment" not in compact_text or "MDPhD" not in compact_text:
                continue
            campus = (
                "Mirae Campus"
                if mirae
                else (
                    "International Campus"
                    if "International Campus" in page_text
                    else "Sinchon Campus"
                )
            )
            for table in page.extract_tables():
                if len(table) < 3 or _normalise(table[0][0]) != "College":
                    continue
                master_column = next(
                    (
                        index
                        for index, value in enumerate(table[1])
                        if _normalise(value) == "MD"
                    ),
                    None,
                )
                if master_column is None:
                    continue
                for raw_row in table[2:]:
                    if len(raw_row) <= master_column:
                        continue
                    college = _clean_pdf_label(raw_row[0])
                    department = _clean_pdf_label(raw_row[1])
                    if college:
                        current_college = college
                    if not department:
                        continue
                    rows.append(
                        {
                            "campus": campus,
                            "college": current_college,
                            "department": department,
                            "master": _normalise(raw_row[master_column]) == "\u25cb",
                        }
                    )
    return rows


def _clean_pdf_label(value: object) -> str:
    text = str(value or "").replace("\x00", " ")
    text = re.sub(r"-\s+", "", text)
    return _normalise(text).strip("*").replace("Convertgence", "Convergence")


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _slug(value: object) -> str:
    text = (
        unicodedata.normalize("NFKD", _normalise(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "programme"
