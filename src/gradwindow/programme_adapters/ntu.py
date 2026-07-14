from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "nanyang-technological-university-singapore-ntu-singapore"
CATALOG_ENDPOINT = (
    "https://www.ntu.edu.sg/admissions/graduate/programme-listing/GetProgrammes/"
)
APPLICATION_URL = (
    "https://www.ntu.edu.sg/admissions/graduate/cwadmissionguide/apply-now"
)
SITE_ROOT = "https://www.ntu.edu.sg"


def catalog_page_url(page: int) -> str:
    return (
        f"{CATALOG_ENDPOINT}?{urlencode({'programmelevels': 'master', 'page': page})}"
    )


CATALOG_URL = catalog_page_url(1)


class NTUAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Academic Year 2026-27"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(self, minimum_expected_programmes: int = 100) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        first = _catalog_payload(fetcher(catalog_page_url(1)))
        total_pages = _positive_int(first.get("totalPages"), "totalPages")
        total_items = _positive_int(first.get("totalItems"), "totalItems")
        items = list(first.get("items") or [])
        for page in range(2, total_pages + 1):
            payload = _catalog_payload(fetcher(catalog_page_url(page)))
            items.extend(payload.get("items") or [])

        programmes = {
            programme.id: programme
            for item in items
            if (programme := _programme_from_item(item)) is not None
        }
        if (
            len(items) != total_items
            or len(programmes) < self.minimum_expected_programmes
        ):
            raise ValueError(
                "NTU coursework catalogue only contained "
                f"{len(programmes)} unique master's programmes from {len(items)} "
                f"items; expected at least {self.minimum_expected_programmes} and "
                f"an API total of {total_items}"
            )

        windows_by_key, evidence_by_key = _application_windows(
            fetcher(self.application_url)
        )
        unmatched = set(windows_by_key).difference(
            _catalog_key(programme.name) for programme in programmes.values()
        )
        if unmatched:
            raise ValueError(
                "NTU live application table contained programmes missing from the "
                f"official coursework catalogue: {', '.join(sorted(unmatched))}"
            )

        discovered = []
        for programme in programmes.values():
            key = _catalog_key(programme.name)
            windows = windows_by_key.get(key, [])
            if windows:
                programme.windows = windows
                programme.parse_status = "parsed"
                programme.deadline_text = evidence_by_key[key]
            discovered.append(programme)
        discovered.sort(key=lambda item: item.id)
        return DiscoveredCatalog(application_opens_at=None, programmes=discovered)


def _catalog_payload(value: str) -> dict:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("NTU catalogue endpoint did not return JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("NTU catalogue endpoint returned an invalid payload")
    return payload


def _positive_int(value, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"NTU catalogue payload has invalid {label}") from exc
    if parsed < 1:
        raise ValueError(f"NTU catalogue payload has invalid {label}")
    return parsed


def _programme_from_item(item) -> DiscoveredProgramme | None:
    if not isinstance(item, dict):
        return None
    title = _normalise(str(item.get("title") or ""))
    path = str(item.get("url") or "").strip()
    if not title or not path:
        return None
    degree_type, core_title = _degree_and_core_title(title)
    programme_id = _programme_id(core_title, degree_type)
    if _catalog_key(core_title) == "applied ai":
        programme_id = "ntu-applied-artificial-intelligence-mcomp"
    faculty = _normalise(str(item.get("tag") or ""))
    department = faculty.split(" | ", 1)[0]
    return DiscoveredProgramme(
        id=programme_id,
        name=title,
        degree_type=degree_type,
        faculty=faculty,
        department=department,
        source_url=urljoin(SITE_ROOT, path),
        application_url=APPLICATION_URL,
        windows=[],
        deadline_text=(
            "Programme found in NTU's official coursework master's catalogue, "
            "but it is not listed in the current live application-window table."
        ),
        parse_status="no-deadline",
        retrieval_method="official-api",
        evidence_quality="official-full-text",
    )


def _application_windows(
    html: str,
) -> tuple[dict[str, list[DiscoveredWindow]], dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    windows: dict[str, list[DiscoveredWindow]] = {}
    evidence = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr")[1:]:
            cells = [
                _normalise(cell.get_text(" ", strip=True))
                for cell in row.find_all(["th", "td"])
            ]
            if len(cells) < 5:
                continue
            period, admission_date, programme_name, opens, closes = cells[:5]
            key = _catalog_key(programme_name)
            window = DiscoveredWindow(
                round=_round_name(period),
                intake=_intake(admission_date),
                opens_at=_date(opens),
                closes_at=_date(closes),
                applicant_categories=["all"],
                source_url=APPLICATION_URL,
            )
            windows.setdefault(key, []).append(window)
            evidence[key] = (
                "NTU's official live application table lists "
                f"{programme_name} for {window.intake}: applications open "
                f"{window.opens_at} and close {window.closes_at}."
            )
    return windows, evidence


def _round_name(period: str) -> str:
    parts = [part.strip() for part in period.split("/", 1)]
    return parts[-1] if parts[-1] else "Main intake"


def _intake(value: str) -> str:
    return _parse_date(value).strftime("%B %Y")


def _date(value: str) -> str:
    return _parse_date(value).date().isoformat()


def _parse_date(value: str) -> datetime:
    clean = re.sub(r"-Sept-", "-Sep-", value.strip(), flags=re.I)
    try:
        return datetime.strptime(clean, "%d-%b-%y")
    except ValueError as exc:
        raise ValueError(
            f"Invalid date in NTU live application table: {value}"
        ) from exc


def _degree_and_core_title(title: str) -> tuple[str, str]:
    rules = (
        (r"^.*?Master of Science(?:\s+in)?\s*", "MSc"),
        (r"^Master of Arts(?:\s+in)?\s*", "MA"),
        (r"^Master of Computing(?:\s+in)?\s*", "MComp"),
        (r"^Master of Education\s*", "MEd"),
        (r"^Master of Public Administration\s*", "MPA"),
        (r"^Master of Social Sciences(?:\s+in)?\s*", "MSocSci"),
        (r"^Master of Media and Communication\s*", "MMC"),
        (r"^Master of Teaching\s*", "MTeach"),
        (r"^Master in Management\s*", "MiM"),
    )
    for pattern, degree_type in rules:
        if re.search(pattern, title, re.I):
            return degree_type, re.sub(pattern, "", title, count=1, flags=re.I)
    if re.search(r"\bMBA\b", title, re.I):
        return "MBA", re.sub(r"\bMBA\b", "", title, flags=re.I)
    return "Master", title


def _programme_id(core_title: str, degree_type: str) -> str:
    return f"ntu-{_slug(core_title)}-{_slug(degree_type)}"


def _catalog_key(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore")
    clean = ascii_value.decode()
    clean = re.sub(r"^\s*\d+\s*-\s*", "", clean)
    clean = re.sub(
        r"\((?:MCAAI|MSDS|MSAI|MSBBB|MSCMED|MMC|IS|MSIS|KM|HOPE)\)",
        " ",
        clean,
        flags=re.I,
    )
    clean = clean.lower().replace("&", " and ")
    clean = re.sub(
        r"\b(?:executive\s+)?master(?: of)? "
        r"(?:science|arts|public administration|social sciences)\b",
        " ",
        clean,
    )
    clean = re.sub(r"\bmsc\b", " ", clean)
    clean = re.sub(r"\bmgt\b", "management", clean)
    clean = re.sub(r"\bprogramme\b", " ", clean)
    clean = re.sub(r"\b(?:in|the)\b", " ", clean)
    return " ".join(re.findall(r"[a-z0-9]+", clean))


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.decode().lower()).strip("-")


def _normalise(value: str) -> str:
    return re.sub(
        r"\s+", " ", value.replace("\u200b", "").replace("\ufeff", "")
    ).strip()
