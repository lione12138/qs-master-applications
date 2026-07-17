from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
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

UNIVERSITY_ID = "universiti-malaya-um"
PROGRAMMES_URL = "https://study.um.edu.my/programmes"
HOW_TO_APPLY_URL = "https://study.um.edu.my/how-to-apply"
APPLICATION_URL = "https://apply.um.edu.my"
EXISTING_APPLIED_COMPUTING_ID = "um-computer-science-applied-computing-master"

_BROCHURE_RE = re.compile(r"brochure-postgraduate-(?P<year>20\d{2})\.pdf$", re.I)
_DATE_RE = re.compile(r"\b\d{1,2}\s+[A-Za-z]+\s+20\d{2}\b")
_MODES = {"CW", "MM", "RS", "CL", "RS/MM"}


class UMAdapter(BaseProgrammeAdapter):
    """Discover master's programmes and exact mode-level windows at UM."""

    university_id = UNIVERSITY_ID
    catalog_url = PROGRAMMES_URL
    application_url = APPLICATION_URL
    intake = "2026/27 postgraduate admissions"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 130,
        maximum_expected_programmes: int = 145,
        minimum_catalog_year: int = 2026,
        pdf_payload_fetcher=None,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.minimum_catalog_year = minimum_catalog_year
        self.pdf_payload_fetcher = pdf_payload_fetcher or _fetch_pdf_payload

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        brochure_url, brochure_year = _brochure_url(fetcher(PROGRAMMES_URL))
        if brochure_year < self.minimum_catalog_year:
            raise ValueError(
                f"UM's latest postgraduate brochure is for {brochure_year}; expected "
                f"{self.minimum_catalog_year} or later"
            )
        windows = _official_windows(fetcher(HOW_TO_APPLY_URL))
        programmes = _catalogue_programmes(
            self.pdf_payload_fetcher(brochure_url),
            brochure_url=brochure_url,
            brochure_year=brochure_year,
            windows=windows,
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "UM's official postgraduate brochure only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "UM's official postgraduate brochure unexpectedly contained "
                f"{len(programmes)} master's programmes; expected at most "
                f"{self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("UM postgraduate brochure generated duplicate IDs")
        return DiscoveredCatalog(
            application_opens_at=min(
                window.opens_at
                for programme in programmes
                for window in programme.windows
                if window.opens_at is not None
            ),
            programmes=sorted(programmes, key=lambda item: item.id),
        )


def _brochure_url(html: str) -> tuple[str, int]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for link in soup.select("a[href]"):
        url = urljoin(PROGRAMMES_URL, str(link["href"]))
        match = _BROCHURE_RE.search(urlparse(url).path)
        if match is None:
            continue
        if not _is_official_pdf(url):
            raise ValueError(
                f"UM programmes page linked a non-official brochure: {url}"
            )
        candidates.append((int(match.group("year")), url))
    if not candidates:
        raise ValueError("UM programmes page did not link a postgraduate brochure")
    year, url = max(candidates)
    return url, year


def _official_windows(html: str) -> dict[str, tuple[str, str, str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows = [
        row
        for table in soup.select("table")
        for row in _expanded_rows(table)
        if len(row) >= 5
        and _normalise(row[0]).upper()
        == "POSTGRADUATE - FOR MALAYSIAN AND INTERNATIONAL"
    ]
    definitions = {
        "coursework": ("coursework", "mixed mode"),
        "clinical": ("clinical",),
        "research": ("research",),
    }
    result = {}
    for key, markers in definitions.items():
        matches = [
            row
            for row in rows
            if all(marker in _normalise(row[4]).lower() for marker in markers)
        ]
        if len(matches) != 1:
            label = key.title()
            raise ValueError(
                f"UM how-to-apply page lacked one exact {label} application window"
            )
        row = matches[0]
        try:
            opens_at = _parse_date(row[2])
            closes_at = _parse_date(row[3])
        except ValueError as exc:
            label = key.title()
            raise ValueError(
                f"UM how-to-apply page lacked an exact {label} application window"
            ) from exc
        if date.fromisoformat(closes_at) <= date.fromisoformat(opens_at):
            raise ValueError(f"UM {key} application window had an invalid date range")
        intake_text = _normalise(row[1])
        year_match = re.search(
            r"Academic Session\s+(20\d{2})/20\d{2}", intake_text, re.I
        )
        if year_match is None:
            raise ValueError(f"UM {key} application window lacked an academic session")
        month = "June" if "june" in intake_text.lower() else "October"
        intake = f"{month} {year_match.group(1)}"
        result[key] = (opens_at, closes_at, intake, key)
    return result


def _expanded_rows(table) -> list[list[str]]:
    first = table.select_one("tr")
    if first is None:
        return []
    width = sum(
        int(cell.get("colspan", 1))
        for cell in first.find_all(["th", "td"], recursive=False)
    )
    active: dict[int, tuple[int, str]] = {}
    output = []
    for row in table.select("tr"):
        cells = iter(row.find_all(["th", "td"], recursive=False))
        values = []
        column = 0
        while column < width:
            if column in active:
                remaining, value = active[column]
                values.append(value)
                if remaining == 1:
                    del active[column]
                else:
                    active[column] = (remaining - 1, value)
                column += 1
                continue
            try:
                cell = next(cells)
            except StopIteration:
                values.append("")
                column += 1
                continue
            value = _normalise(cell.get_text(" ", strip=True))
            colspan = int(cell.get("colspan", 1))
            rowspan = int(cell.get("rowspan", 1))
            for offset in range(colspan):
                values.append(value)
                if rowspan > 1:
                    active[column + offset] = (rowspan - 1, value)
            column += colspan
        output.append(values[:width])
    return output


def _parse_date(value: object) -> str:
    match = _DATE_RE.search(_normalise(value))
    if match is None:
        raise ValueError("missing exact date")
    for pattern in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(match.group(), pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unsupported date: {match.group()}")


def _catalogue_programmes(
    value: str,
    *,
    brochure_url: str,
    brochure_year: int,
    windows: dict[str, tuple[str, str, str, str]],
) -> list[DiscoveredProgramme]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("UM postgraduate brochure payload is invalid") from exc
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError("UM postgraduate brochure payload lacked programme entries")
    programmes = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("UM postgraduate brochure contained an invalid entry")
        faculty = _faculty_name(entry.get("faculty"))
        name = _normalise(entry.get("name"))
        mode = _normalise(entry.get("mode")).upper()
        if not faculty or not name.lower().startswith("master") or mode not in _MODES:
            raise ValueError(
                "UM postgraduate brochure contained an invalid master's row"
            )
        canonical = f"{faculty}|{name}"
        if canonical in seen:
            continue
        digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]
        programme_id = (
            EXISTING_APPLIED_COMPUTING_ID
            if name == "Master of Computer Science (Applied Computing)"
            else f"um-master-{digest}"
        )
        window_keys = {
            "CW": ["coursework"],
            "MM": ["coursework"],
            "RS": ["research"],
            "CL": ["clinical"],
            "RS/MM": ["coursework", "research"],
        }[mode]
        discovered_windows = []
        for key in window_keys:
            opens_at, closes_at, intake, _ = windows[key]
            discovered_windows.append(
                DiscoveredWindow(
                    round=(
                        "Coursework and mixed-mode admission"
                        if key == "coursework"
                        else f"{key.title()} admission"
                    ),
                    opens_at=opens_at,
                    closes_at=closes_at,
                    intake=intake,
                    applicant_categories=["all"],
                    source_url=HOW_TO_APPLY_URL,
                )
            )
        ranges = ", ".join(
            f"{item.opens_at} through {item.closes_at}" for item in discovered_windows
        )
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=name,
                degree_type="Master",
                faculty=faculty,
                department=name,
                source_url=brochure_url,
                application_url=APPLICATION_URL,
                windows=discovered_windows,
                deadline_text=(
                    f"UM's official {brochure_year} postgraduate brochure lists this "
                    f"programme in {mode} mode. The official 2026/27 application "
                    f"table publishes the applicable exact period(s): {ranges}."
                ),
                parse_status="parsed",
                retrieval_method="official-postgraduate-brochure-pdf-layout",
                evidence_quality="official-full-text",
            )
        )
        seen.add(canonical)
    return programmes


def _fetch_pdf_payload(url: str) -> str:
    if not _is_official_pdf(url):
        raise ValueError(f"Refusing to fetch a non-official UM PDF: {url}")
    request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urlopen(request, timeout=60) as response:
        raw = response.read(25_000_001)
    if len(raw) > 25_000_000:
        raise ValueError("UM postgraduate brochure PDF exceeded the download limit")
    entries = []
    with pdfplumber.open(BytesIO(raw)) as pdf:
        for page in pdf.pages:
            entries.extend(_page_entries(page))
    return json.dumps({"entries": entries}, ensure_ascii=False)


def _page_entries(page) -> list[dict[str, str]]:
    words = page.extract_words(extra_attrs=["non_stroking_color"])
    entries = []
    columns = (
        (page.width * 0.08, page.width * 0.49, page.width * 0.42),
        (page.width * 0.51, page.width * 0.96, page.width * 0.84),
    )
    for x0, x1, mode_x in columns:
        column_words = [
            word
            for word in words
            if x0 <= word["x0"] < x1 and word["top"] < page.height * 0.90
        ]
        orange_lines = _word_lines(
            [
                word
                for word in column_words
                if _is_orange(word.get("non_stroking_color"))
            ]
        )
        headings = []
        index = 0
        while index < len(orange_lines):
            top, text = orange_lines[index]
            parts = [text]
            following = index + 1
            while (
                following < len(orange_lines)
                and orange_lines[following][0] - orange_lines[following - 1][0] < 12
            ):
                parts.append(orange_lines[following][1])
                following += 1
            heading = _normalise(" ".join(parts))
            if any(
                token in heading.upper()
                for token in ("FACULTY", "ACADEMY", "INSTITUTE")
            ):
                headings.append((top, heading))
            index = following
        dark_words = [
            word for word in column_words if _is_dark(word.get("non_stroking_color"))
        ]
        modes = sorted(
            [
                word
                for word in dark_words
                if _normalise(word["text"]).upper() in _MODES and word["x0"] >= mode_x
            ],
            key=lambda word: word["top"],
        )
        for mode_index, mode_word in enumerate(modes):
            top = mode_word["top"]
            lower = (modes[mode_index - 1]["top"] + top) / 2 if mode_index else top - 14
            upper = (
                (top + modes[mode_index + 1]["top"]) / 2
                if mode_index + 1 < len(modes)
                else top + 14
            )
            name = _normalise(
                " ".join(
                    text
                    for _, text in _word_lines(
                        [
                            word
                            for word in dark_words
                            if word["x1"] < mode_x and lower <= word["top"] < upper
                        ]
                    )
                )
            )
            if not name.lower().startswith("master"):
                continue
            faculty = next(
                (
                    heading
                    for heading_top, heading in reversed(headings)
                    if heading_top < top
                ),
                None,
            )
            if faculty is None:
                raise ValueError(f"UM brochure programme lacked a faculty: {name}")
            entries.append(
                {
                    "faculty": faculty,
                    "name": name,
                    "mode": _normalise(mode_word["text"]).upper(),
                }
            )
    return entries


def _word_lines(words: list[dict], tolerance: float = 2.0) -> list[tuple[float, str]]:
    lines: list[tuple[float, list[dict]]] = []
    for word in sorted(words, key=lambda item: (item["top"], item["x0"])):
        if not lines or abs(lines[-1][0] - word["top"]) > tolerance:
            lines.append((word["top"], [word]))
        else:
            lines[-1][1].append(word)
    return [
        (
            top,
            " ".join(
                str(word["text"]) for word in sorted(line, key=lambda item: item["x0"])
            ),
        )
        for top, line in lines
    ]


def _is_orange(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) == 3
        and value[0] > 0.8
        and value[1] > 0.5
        and value[2] < 0.35
    )


def _is_dark(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) == 3
        and value[0] < 0.3
        and value[1] < 0.3
        and value[2] < 0.35
    )


def _faculty_name(value: object) -> str:
    name = _normalise(value).title()
    name = re.sub(r"\b(Of|And|In|For)\b", lambda match: match.group().lower(), name)
    return name.replace("Informations Technology", "Information Technology")


def _is_official_pdf(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "study.um.edu.my"
        and parsed.path.lower().endswith(".pdf")
    )


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())
