from __future__ import annotations

import hashlib
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
from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "zhejiang-university"
CATALOG_URL = "https://iczu.zju.edu.cn/admissionsen/wasterwswwegreewwrograms/list.htm"
APPLICATION_URL = "https://isinfosys.zju.edu.cn/recruit/login.shtml"
EXISTING_CS_ID = "zju-computer-science-technology-master"

_CATALOG_TITLE_RE = re.compile(
    r"Catalog of (?P<language>Chinese|English)-taught Master's Degree "
    r"programs (?P<year>20\d{2})",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(r"\b\d(?:\.\d)?\s+years?\b", re.IGNORECASE)

PdfPayloadFetcher = Callable[[str], str]


class ZJUAdapter(BaseProgrammeAdapter):
    """Discover international master's programmes from ZJU's official PDFs."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Latest published autumn international intake"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_chinese_programmes: int = 220,
        minimum_expected_english_programmes: int = 55,
        minimum_catalog_year: int = 2026,
        pdf_payload_fetcher: PdfPayloadFetcher | None = None,
    ) -> None:
        self.minimum_expected_chinese_programmes = minimum_expected_chinese_programmes
        self.minimum_expected_english_programmes = minimum_expected_english_programmes
        self.minimum_catalog_year = minimum_catalog_year
        self.pdf_payload_fetcher = pdf_payload_fetcher or _fetch_pdf_payload

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        year, sources = _latest_catalogues(fetcher(CATALOG_URL))
        if year < self.minimum_catalog_year:
            raise ValueError(
                f"ZJU's latest matched master's catalogues are for {year}; expected "
                f"{self.minimum_catalog_year} or later"
            )
        chinese = _catalogue_programmes(
            self.pdf_payload_fetcher(sources["Chinese"]),
            language="Chinese",
            source_url=sources["Chinese"],
            catalog_year=year,
        )
        english = _catalogue_programmes(
            self.pdf_payload_fetcher(sources["English"]),
            language="English",
            source_url=sources["English"],
            catalog_year=year,
        )
        if len(chinese) < self.minimum_expected_chinese_programmes:
            raise ValueError(
                "ZJU's official Chinese-taught catalogue only contained "
                f"{len(chinese)} master's programmes; expected at least "
                f"{self.minimum_expected_chinese_programmes}"
            )
        if len(english) < self.minimum_expected_english_programmes:
            raise ValueError(
                "ZJU's official English-taught catalogue only contained "
                f"{len(english)} master's programmes; expected at least "
                f"{self.minimum_expected_english_programmes}"
            )
        programmes = sorted([*chinese, *english], key=lambda item: item.id)
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("ZJU official catalogues generated duplicate IDs")
        self.intake = f"Autumn {year}"
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _latest_catalogues(html: str) -> tuple[int, dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: dict[int, dict[str, str]] = {}
    for link in soup.select("a[href]"):
        title = _normalise(link.get_text(" ", strip=True))
        match = _CATALOG_TITLE_RE.fullmatch(title)
        if match is None:
            continue
        source_url = urljoin(CATALOG_URL, str(link["href"]))
        if not _is_official_pdf(source_url):
            raise ValueError(f"ZJU catalogue linked a non-official PDF: {source_url}")
        candidates.setdefault(int(match.group("year")), {})[
            match.group("language").title()
        ] = source_url
    complete = [
        (year, urls)
        for year, urls in candidates.items()
        if set(urls) == {"Chinese", "English"}
    ]
    if not complete:
        raise ValueError(
            "ZJU admissions guide did not link matched Chinese- and English-taught "
            "master's catalogues"
        )
    return max(complete, key=lambda item: item[0])


def _catalogue_programmes(
    value: str,
    *,
    language: str,
    source_url: str,
    catalog_year: int,
) -> list[DiscoveredProgramme]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("ZJU master's catalogue payload is invalid") from exc
    pages = payload.get("pages") if isinstance(payload, dict) else None
    if not isinstance(pages, list):
        raise ValueError("ZJU master's catalogue payload lacked PDF pages")
    expected_title = f"{language}-taught Master's Degree Programs {catalog_year}"
    if not any(
        expected_title in _normalise(cell)
        for page in pages
        for row in page.get("rows", [])
        for cell in row
    ):
        raise ValueError(f"ZJU {language}-taught PDF had an unexpected year or title")

    school = ""
    programmes = []
    seen = set()
    for page in pages:
        for row in page.get("rows", []):
            cells = [_normalise(cell) for cell in row]
            if len(cells) < 5 or not cells[1] or not _DURATION_RE.search(cells[2]):
                continue
            if cells[0]:
                school = _faculty_name(cells[0])
            if not school:
                raise ValueError("ZJU catalogue programme row lacked a school")
            name = cells[1]
            canonical = f"{language}|{school}|{name}"
            if canonical in seen:
                continue
            existing_cs = (
                language == "English" and name == "Computer Science and Technology"
            )
            digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]
            programme_id = (
                EXISTING_CS_ID
                if existing_cs
                else f"zju-{language.lower()}-master-{digest}"
            )
            programmes.append(
                DiscoveredProgramme(
                    id=programme_id,
                    name=f"{name} ({language}-taught)",
                    degree_type=(
                        "Professional Master" if "(Professional)" in name else "Master"
                    ),
                    faculty=school,
                    department=name,
                    source_url=source_url,
                    application_url=APPLICATION_URL,
                    windows=[],
                    deadline_text=(
                        f"ZJU's official {catalog_year} {language.lower()}-taught "
                        "catalogue confirms this programme and publishes a completed "
                        f"{catalog_year} closing-date policy, but neither the guide nor "
                        "catalogue gives an exact application opening date. No date is "
                        "carried forward to a later intake."
                    ),
                    parse_status="no-deadline",
                    retrieval_method="official-international-master-catalogue-pdf-table",
                    evidence_quality="official-full-text",
                )
            )
            seen.add(canonical)
    return programmes


def _fetch_pdf_payload(url: str) -> str:
    if not _is_official_pdf(url):
        raise ValueError(f"Refusing to fetch a non-official ZJU PDF: {url}")
    request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urlopen(request, timeout=45) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError("ZJU master's catalogue PDF exceeded the download limit")
    pages = []
    with pdfplumber.open(BytesIO(raw)) as pdf:
        for page in pdf.pages:
            rows = [
                [cell or "" for cell in row]
                for table in page.extract_tables()
                for row in table
            ]
            pages.append({"rows": rows})
    return json.dumps({"pages": pages}, ensure_ascii=False)


def _faculty_name(value: str) -> str:
    without_urls = re.sub(r"https?://\S+", " ", value, flags=re.IGNORECASE)
    without_url_fragments = re.sub(
        r"\S*(?:\.cn|\.edu|/)[^\s]*",
        " ",
        without_urls,
        flags=re.IGNORECASE,
    )
    return _normalise(without_url_fragments)


def _is_official_pdf(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "iczu.zju.edu.cn"
        and parsed.path.lower().endswith(".pdf")
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
