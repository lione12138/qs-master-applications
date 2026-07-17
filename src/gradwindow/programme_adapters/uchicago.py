from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "university-of-chicago"
CATALOG_URL = "https://grad.uchicago.edu/admissions/programs/"
EXISTING_APPLIED_DATA_SCIENCE_ID = "uchicago-applied-data-science-ms"

_DEGREE_TYPES = (
    ("Master's Program in Computational and Applied Mathematics", "MS"),
    ("Master of Business Administration", "MBA"),
    ("Master of Science for Clinical Professionals", "MS"),
    ("Master of Arts in Social Work", "MASW"),
    ("Master of Arts Program in the Social Sciences", "MA"),
    ("Master of Arts Program in the Humanities", "MA"),
    ("Master of Arts in Religious Studies", "MA"),
    ("Master of Public Health", "MPH"),
    ("Master of Public Policy", "MPP"),
    ("Master of Legal Studies", "MLS"),
    ("Master of Liberal Arts", "MLA"),
    ("Master of Fine Arts", "MFA"),
    ("Master of Engineering", "MEng"),
    ("Master of Divinity", "MDiv"),
    ("Master of Management", "MiM"),
    ("Master of Finance", "MFin"),
    ("Master of Laws", "LLM"),
    ("Master of Science", "MS"),
    ("Master of Arts", "MA"),
)


class UChicagoAdapter(BaseProgrammeAdapter):
    """Discover unique master's programmes from UChicagoGRAD's directory."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = CATALOG_URL
    intake = "Varies by programme"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(self, minimum_expected_programmes: int = 35) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        records = _catalogue_records(html)
        programmes = [_programme(record) for record in records]
        ids = [programme.id for programme in programmes]
        if len(ids) != len(set(ids)):
            raise ValueError(
                "UChicago master directory produced duplicate programme IDs"
            )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "UChicago's official directory only contained "
                f"{len(programmes)} unique master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _catalogue_records(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    records: dict[str, dict[str, object]] = {}
    for card in soup.select("div.program"):
        if "masters" not in str(card.get("data-filter", "")).split():
            continue
        programme_link = card.select_one("a.program-name[href]")
        if programme_link is None:
            continue
        field = _normalise(programme_link.get_text(" ", strip=True))
        masters_detail = _detail_by_label(card, "Masters")
        unit_detail = _detail_by_label(card, "Unit")
        if masters_detail is None:
            continue
        units = (
            [
                _normalise(link.get_text(" ", strip=True))
                for link in unit_detail.select("a")
            ]
            if unit_detail is not None
            else []
        )
        for link in masters_detail.select("a[href]"):
            source_url = str(link.get("href", ""))
            if not _is_official_url(source_url):
                continue
            key = source_url.rstrip("/").casefold()
            degree_label = _normalise(link.get_text(" ", strip=True))
            record = records.setdefault(
                key,
                {
                    "degreeLabel": degree_label,
                    "fields": [],
                    "sourceUrl": source_url,
                    "units": [],
                },
            )
            _append_unique(record["fields"], field)
            for unit in units:
                _append_unique(record["units"], unit)
    if not records:
        raise ValueError("UChicagoGRAD directory did not contain master's links")
    return list(records.values())


def _detail_by_label(card, label: str):
    for detail in card.select(".program-detail"):
        header = detail.select_one(".inline-header")
        if header is None:
            continue
        if _normalise(header.get_text(" ", strip=True)).rstrip(":") == label:
            return detail
    return None


def _programme(record: dict[str, object]) -> DiscoveredProgramme:
    degree_label = str(record["degreeLabel"])
    fields = [str(value) for value in record["fields"]]
    source_url = str(record["sourceUrl"])
    name = _programme_name(degree_label, fields)
    programme_id = f"uchicago-{_slugify(name)}"
    if "ms-in-applied-data-science" in urlparse(source_url).path:
        programme_id = EXISTING_APPLIED_DATA_SCIENCE_ID
        name = "MS in Applied Data Science"
    units = [str(value) for value in record["units"]]
    faculty = " / ".join(units) or "University of Chicago"
    return DiscoveredProgramme(
        id=programme_id,
        name=name,
        degree_type=_degree_type(degree_label),
        faculty=faculty,
        department="",
        source_url=source_url,
        application_url=source_url,
        windows=[],
        deadline_text=(
            "The official UChicagoGRAD directory confirms this master's programme "
            "and its academic unit. UChicago's academic units set their own "
            "application windows, and the university directory does not publish an "
            "exact opening and closing date pair. The programme admissions page "
            "remains monitored and no dates are inferred."
        ),
        parse_status="no-deadline",
        retrieval_method="official-university-graduate-directory",
        evidence_quality="official-full-text",
    )


def _programme_name(degree_label: str, fields: list[str]) -> str:
    if len(fields) != 1:
        return degree_label
    field = fields[0]
    if field.casefold() in degree_label.casefold() or field.startswith("Master "):
        return degree_label
    return f"{field}, {degree_label}"


def _degree_type(value: str) -> str:
    for label, degree_type in _DEGREE_TYPES:
        if value.startswith(label):
            return degree_type
    return "Master"


def _append_unique(values: object, value: str) -> None:
    if isinstance(values, list) and value and value not in values:
        values.append(value)


def _is_official_url(value: str) -> bool:
    hostname = urlparse(value).hostname or ""
    return (
        hostname == "uchicago.edu"
        or hostname.endswith(".uchicago.edu")
        or hostname == "chicagobooth.edu"
        or hostname.endswith(".chicagobooth.edu")
    )


def _slugify(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u200b", "")).strip()
