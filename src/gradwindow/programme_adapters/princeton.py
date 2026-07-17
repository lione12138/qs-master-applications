from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "princeton-university"
CATALOG_URL = (
    "https://gradschool.princeton.edu/academics/degrees-requirements/fields-study"
)
DEADLINES_URL = (
    "https://gradschool.princeton.edu/admission-onboarding/prepare/deadlines-and-fees"
)
APPLICATION_URL = "https://gradschool.princeton.edu/admission-onboarding/apply"
READER_PREFIX = "https://r.jina.ai/http://"
EXISTING_COMPUTER_SCIENCE_ID = "princeton-computer-science-mse"

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December"
)
_DATE_RE = re.compile(
    rf"(?P<month>{_MONTHS})\s+(?P<day>\d{{1,2}})(?:,\s*(?P<year>20\d{{2}}))?",
    re.I,
)
_DEGREE_RE = re.compile(r"M\.Arch\.|M\.S\.E\.|M\.Eng\.|M\.Fin\.|M\.P\.A\.|M\.P\.P\.")
_MARKDOWN_ROW_RE = re.compile(
    r"^\|\s*\[(?P<name>[^]]+)\]\((?P<url>https?://[^)]+)\)\s*\|"
    r"\s*(?P<offerings>[^|]+)\|",
    re.M,
)
_OPENING_POLICY_RE = re.compile(
    rf"application for Fall (?P<intake>20\d{{2}}) will open in "
    rf"(?P<month>{_MONTHS})(?:\s+(?P<day>\d{{1,2}}),?)?\s+"
    rf"(?P<year>20\d{{2}})",
    re.I,
)
_DEGREE_TYPES = {
    "M.Arch.": "MARCH",
    "M.S.E.": "MSE",
    "M.Eng.": "MENG",
    "M.Fin.": "MFIN",
    "M.P.A.": "MPA",
    "M.P.P.": "MPP",
}


class PrincetonAdapter(BaseProgrammeAdapter):
    """Discover Princeton's terminal master's programmes and deadline evidence."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Fall admission"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(self, minimum_expected_programmes: int = 12) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        catalog_document, catalog_method = _load_official_document(fetcher, CATALOG_URL)
        policy_document, _ = _load_official_document(fetcher, DEADLINES_URL)
        opening_policy = _next_cycle_opening_policy(policy_document)
        records = _catalogue_records(catalog_document)

        programmes = []
        intake_years = set()
        for record in records:
            detail_document, detail_method = _load_official_document(
                fetcher, record["source_url"]
            )
            detail_text = _document_text(detail_document)
            intake_year, deadline_section = _deadline_section(detail_text)
            intake_years.add(intake_year)
            for degree_label in record["degrees"]:
                closes_at = _closing_date(
                    deadline_section,
                    degree_label=degree_label,
                    intake_year=intake_year,
                )
                programmes.append(
                    _programme(
                        department=record["name"],
                        degree_label=degree_label,
                        source_url=record["source_url"],
                        closes_at=closes_at,
                        intake_year=intake_year,
                        opening_policy=opening_policy,
                        retrieval_method=(
                            detail_method
                            if detail_method != "official-page"
                            else catalog_method
                        ),
                        evidence_document=detail_text,
                    )
                )

        programmes = sorted(
            {programme.id: programme for programme in programmes}.values(),
            key=lambda item: item.id,
        )
        if len(intake_years) != 1:
            raise ValueError(
                "Princeton programme pages contained inconsistent application cycles: "
                f"{sorted(intake_years)}"
            )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Princeton's official catalogue only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        intake_year = next(iter(intake_years))
        self.intake = f"Fall {intake_year}"
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def reader_url(source_url: str) -> str:
    return READER_PREFIX + re.sub(r"^https?://", "", source_url)


def _load_official_document(
    fetcher: Callable[[str], str], source_url: str
) -> tuple[str, str]:
    try:
        direct = fetcher(source_url)
    except Exception:
        direct = ""
    if direct and not _is_access_challenge(direct):
        return direct, "official-page"
    try:
        proxied = fetcher(reader_url(source_url))
    except Exception as exc:
        raise ValueError(
            f"Princeton official page was unavailable: {source_url}"
        ) from exc
    if not proxied or _is_access_challenge(proxied):
        raise ValueError(f"Princeton official page was unavailable: {source_url}")
    return proxied, "official-page-via-reader"


def _is_access_challenge(value: str) -> bool:
    lowered = value[:5000].lower()
    return (
        "just a moment" in lowered
        or "enable javascript and cookies to continue" in lowered
        or "cf-chl-" in lowered
    )


def _catalogue_records(document: str) -> list[dict[str, object]]:
    records = _markdown_catalogue_records(document)
    if not records and "<" in document[:1000]:
        records = _html_catalogue_records(document)
    if not records:
        raise ValueError("Princeton's official Fields of Study table was not found")
    return records


def _markdown_catalogue_records(document: str) -> list[dict[str, object]]:
    records = []
    for match in _MARKDOWN_ROW_RE.finditer(document):
        degrees = _master_degrees(match.group("offerings"))
        if not degrees:
            continue
        records.append(
            {
                "name": _normalise(match.group("name")),
                "source_url": _official_url(match.group("url")),
                "degrees": degrees,
            }
        )
    return records


def _html_catalogue_records(document: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(document, "html.parser")
    records = []
    for row in soup.select("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 2:
            continue
        link = cells[0].find("a", href=True)
        if link is None:
            continue
        degrees = _master_degrees(cells[1].get_text(" ", strip=True))
        if not degrees:
            continue
        records.append(
            {
                "name": _normalise(link.get_text(" ", strip=True)),
                "source_url": _official_url(urljoin(CATALOG_URL, link["href"])),
                "degrees": degrees,
            }
        )
    return records


def _official_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.hostname != "gradschool.princeton.edu":
        raise ValueError(f"Princeton catalogue contained a non-official URL: {value}")
    return parsed._replace(scheme="https", query="", fragment="").geturl()


def _master_degrees(value: str) -> list[str]:
    return list(dict.fromkeys(_DEGREE_RE.findall(value)))


def _document_text(document: str) -> str:
    if "<html" in document[:1000].lower() or "<main" in document[:1000].lower():
        document = BeautifulSoup(document, "html.parser").get_text("\n", strip=True)
    return _normalise(document)


def _next_cycle_opening_policy(document: str) -> dict[str, object]:
    text = _document_text(document)
    match = _OPENING_POLICY_RE.search(text)
    if match is None:
        raise ValueError("Princeton's official next application cycle was not found")
    exact_date = None
    if match.group("day"):
        exact_date = (
            datetime.strptime(
                f"{match.group('month')} {match.group('day')} {match.group('year')}",
                "%B %d %Y",
            )
            .date()
            .isoformat()
        )
    return {
        "intake_year": int(match.group("intake")),
        "text": _normalise(match.group(0)),
        "exact_date": exact_date,
    }


def _deadline_section(text: str) -> tuple[int, str]:
    match = re.search(
        r"Application deadline\s+(?P<section>.*?)\s+Program length",
        text,
        re.I,
    )
    if match is None:
        raise ValueError(
            "Princeton programme page did not contain its deadline section"
        )
    section = _normalise(match.group("section"))
    cycle = re.search(
        r"enrollment beginning in fall\s+(?P<year>20\d{2})",
        section,
        re.I,
    )
    if cycle is None:
        raise ValueError(
            "Princeton programme page did not identify the deadline intake cycle"
        )
    return int(cycle.group("year")), section


def _closing_date(section: str, *, degree_label: str, intake_year: int) -> str:
    degree_match = re.search(
        rf"{re.escape(degree_label)}\s*-\s*(?P<date>{_MONTHS}\s+\d{{1,2}}"
        r"(?:,\s*20\d{2})?)",
        section,
        re.I,
    )
    date_match = _DATE_RE.search(
        degree_match.group("date") if degree_match is not None else section
    )
    if date_match is None:
        raise ValueError(f"Princeton deadline was not found for degree {degree_label}")
    month = datetime.strptime(date_match.group("month"), "%B").month
    year = (
        int(date_match.group("year"))
        if date_match.group("year")
        else intake_year - 1
        if month >= 7
        else intake_year
    )
    return (
        datetime(
            year,
            month,
            int(date_match.group("day")),
        )
        .date()
        .isoformat()
    )


def _programme(
    *,
    department: str,
    degree_label: str,
    source_url: str,
    closes_at: str,
    intake_year: int,
    opening_policy: dict[str, object],
    retrieval_method: str,
    evidence_document: str,
) -> DiscoveredProgramme:
    degree_type = _DEGREE_TYPES[degree_label]
    department_slug = _slug(department)
    if department_slug.startswith("princeton-"):
        department_slug = department_slug.removeprefix("princeton-")
    programme_id = f"princeton-{department_slug}-{degree_type.lower()}"
    if department == "Computer Science" and degree_type == "MSE":
        programme_id = EXISTING_COMPUTER_SCIENCE_ID
    name = f"{degree_label} in {department}"
    if programme_id == EXISTING_COMPUTER_SCIENCE_ID:
        name = "MSE in Computer Science"
    policy_text = str(opening_policy["text"])
    return DiscoveredProgramme(
        id=programme_id,
        name=name,
        degree_type=degree_type,
        faculty="Princeton University Graduate School",
        department=department,
        source_url=source_url,
        application_url=APPLICATION_URL,
        windows=[
            DiscoveredWindow(
                round="Main deadline",
                closes_at=closes_at,
                opens_at=None,
                intake=f"Fall {intake_year}",
                source_url=source_url,
            )
        ],
        deadline_text=(
            f"Princeton lists the {degree_label} application deadline for Fall "
            f"{intake_year} as {closes_at}. The central admissions page says "
            f"'{policy_text}', so no exact opening date is currently published."
        ),
        parse_status="incomplete",
        retrieval_method=retrieval_method,
        evidence_quality="official-full-text",
        evidence_document_hash=hashlib.sha256(
            evidence_document.encode("utf-8")
        ).hexdigest(),
    )


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
