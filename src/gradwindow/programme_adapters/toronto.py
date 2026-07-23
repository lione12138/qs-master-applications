from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "university-of-toronto"
CATALOG_URL = "https://www.sgs.utoronto.ca/programs/"
APPLICATION_URL = "https://admissions.sgs.utoronto.ca/apply/"
EXISTING_COMPUTER_SCIENCE_ID = "toronto-computer-science-msc"

_DEGREE_LABEL_RE = re.compile(
    r"(?<!\w)(?P<label>[A-Z][A-Za-z0-9]*"
    r"(?:\s*\([^)]*\))?"
    r"(?:,\s*[A-Z][A-Za-z0-9]*(?:\s*\([^)]*\))?)*)\s*:"
)
_FALL_CYCLE_RE = re.compile(
    r"\bFall(?:\s+Session)?(?:\s+\(September start\))?\s+"
    r"(?P<year>20\d{2})(?:\s+entry)?\b",
    re.I,
)
_DATE_RE = re.compile(
    r"\b(?:"
    r"\d{4}-\d{2}-\d{2}|"
    r"\d{1,2}[-\s](?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)[-\s]\d{4}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}"
    r")\b",
    re.I,
)
_ROUND_RE = re.compile(
    r"\b(early|regular|priority|final|round\s+\d+)\s+deadline\b",
    re.I,
)


class TorontoAdapter(BaseProgrammeAdapter):
    """Discover U of T master's programmes and central SGS deadline guidance."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Fall 2027"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 150,
        workers: int = 8,
        intake_year: int = 2027,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.workers = workers
        self.intake_year = intake_year
        self.intake = f"Fall {intake_year}"

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        rows = _catalog_rows(_fetch_with_retry(fetcher, CATALOG_URL))
        detail_urls = list(dict.fromkeys(row["url"] for row in rows))
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            pages = list(executor.map(partial(_fetch_with_retry, fetcher), detail_urls))
        details = dict(zip(detail_urls, pages, strict=True))

        programmes = [
            _programme(
                row,
                degree_type,
                details[row["url"]],
                intake_year=self.intake_year,
            )
            for row in rows
            for degree_type in row["degrees"]
        ]
        programmes.sort(key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "U of T's official SGS directory only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _fetch_with_retry(
    fetcher: Callable[[str], str],
    url: str,
    attempts: int = 3,
) -> str:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return fetcher(url)
        except Exception as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(0.25 * (attempt + 1))
    if last_error is None:
        raise ValueError("attempts must be greater than zero")
    raise last_error


def _catalog_rows(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) != 3:
            continue
        link = cells[0].find("a", href=True)
        if link is None:
            continue
        degrees = [
            degree
            for value in _normalise(cells[2].get_text(" ", strip=True)).split("/")
            if (degree := value.strip()) and _is_master_degree(degree)
        ]
        if not degrees:
            continue
        url = link["href"]
        if not url.startswith("https://www.sgs.utoronto.ca/programs/"):
            continue
        rows.append(
            {
                "name": _normalise(link.get_text(" ", strip=True)),
                "unit": _normalise(cells[1].get_text(" ", strip=True)),
                "degrees": degrees,
                "url": url,
            }
        )
    return rows


def _is_master_degree(value: str) -> bool:
    compact = re.sub(r"[^A-Za-z]", "", value).upper()
    return compact.startswith("M") or compact.endswith("LLM")


def _programme(
    row: dict,
    degree_type: str,
    html: str,
    *,
    intake_year: int,
) -> DiscoveredProgramme:
    table = _deadline_table(html, row["url"])
    if table is None:
        windows = []
        deadline_text = (
            "The official SGS programme page does not publish a Quick Facts "
            "application deadline table."
        )
    else:
        windows, deadline_text = _deadline_windows(
            table,
            degree_type=degree_type,
            source_url=row["url"],
            intake_year=intake_year,
        )
    page_slug = urlparse(row["url"]).path.rstrip("/").rsplit("/", 1)[-1]
    degree_slug = _slug(degree_type)
    programme_id = f"toronto-{page_slug}-{degree_slug}"
    name = f"{row['name']} ({degree_type})"
    faculty = row["unit"] or "University of Toronto"
    if programme_id == EXISTING_COMPUTER_SCIENCE_ID:
        name = "MSc in Computer Science"
        faculty = "Department of Computer Science"

    return DiscoveredProgramme(
        id=programme_id,
        name=name,
        degree_type=degree_type,
        faculty=faculty,
        department="",
        source_url=row["url"],
        application_url=APPLICATION_URL,
        windows=windows,
        deadline_text=deadline_text,
        parse_status="incomplete" if windows else "no-deadline",
        retrieval_method="official-html",
        evidence_quality="official-full-text",
        evidence_document_hash=hashlib.sha256(html.encode("utf-8")).hexdigest(),
    )


def _deadline_table(html: str, source_url: str):
    soup = BeautifulSoup(html, "html.parser")
    if soup.find("h1") is None:
        raise ValueError(f"U of T programme page did not contain a title: {source_url}")
    for table in soup.find_all("table"):
        if _deadline_row(table) is not None:
            return table
    return None


def _deadline_row(table):
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if cells and _normalise(cells[0].get_text(" ", strip=True)).lower() == (
            "application deadline"
        ):
            return cells
    return None


def _deadline_windows(
    table,
    *,
    degree_type: str,
    source_url: str,
    intake_year: int,
) -> tuple[list[DiscoveredWindow], str]:
    cells = _deadline_row(table)
    if cells is None or len(cells) < 3:
        return [], "The official SGS Quick Facts table has no deadline cells."
    texts = {
        "domestic": _normalise(cells[1].get_text(" ", strip=True)),
        "international": _normalise(cells[2].get_text(" ", strip=True)),
    }
    windows = []
    for category, text in texts.items():
        dates = _deadline_dates(text, degree_type, intake_year)
        for round_label, closes_at in dates:
            round_name = f"Fall {intake_year} {category}"
            if round_label:
                round_name += f" {round_label}"
            round_name += " deadline"
            windows.append(
                DiscoveredWindow(
                    round=round_name,
                    opens_at=None,
                    closes_at=closes_at,
                    applicant_categories=[category],
                    intake=f"Fall {intake_year}",
                    source_url=source_url,
                )
            )
    deadline_text = (
        f"Domestic: {texts['domestic']} International: {texts['international']}"
    )
    return windows, deadline_text


def _deadline_dates(
    text: str,
    degree_type: str,
    intake_year: int,
) -> list[tuple[str, str]]:
    anchors = list(_DEGREE_LABEL_RE.finditer(text))
    aliases = _degree_aliases(degree_type)
    results = []
    for index, anchor in enumerate(anchors):
        labels = {
            _degree_key(value)
            for value in anchor.group("label").split(",")
            if value.strip()
        }
        if aliases.isdisjoint(labels):
            continue
        end = anchors[index + 1].start() if index + 1 < len(anchors) else len(text)
        body = text[anchor.end() : end]
        for date_match in _DATE_RE.finditer(body):
            prefix = body[: date_match.start()]
            cycle_matches = list(_FALL_CYCLE_RE.finditer(prefix))
            if not cycle_matches or int(cycle_matches[-1].group("year")) != intake_year:
                continue
            round_matches = list(_ROUND_RE.finditer(prefix))
            round_label = round_matches[-1].group(1).lower() if round_matches else ""
            result = (round_label, _iso_date(date_match.group(0)))
            if result not in results:
                results.append(result)
    return results


def _degree_aliases(degree_type: str) -> set[str]:
    aliases = {_degree_key(degree_type)}
    base = degree_type.split("(", 1)[0].strip()
    aliases.add(_degree_key(base))
    parenthetical = re.findall(r"\(([^()]*)\)", degree_type)
    aliases.update(_degree_key(value) for value in parenthetical)
    return aliases


def _degree_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _iso_date(value: str) -> str:
    normalised = re.sub(r"\s+", " ", value.strip())
    for date_format in (
        "%Y-%m-%d",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%b %d %Y",
        "%B %d %Y",
    ):
        try:
            return datetime.strptime(normalised, date_format).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported U of T deadline date: {value}")


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def _normalise(value: str) -> str:
    return " ".join(value.replace("\u200b", " ").split())
