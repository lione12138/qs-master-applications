from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from dataclasses import replace
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "the-hong-kong-university-of-science-and-technology"
CATALOG_URL = (
    "https://prog-crs.hkust.edu.hk/pgprog/print_result.php?"
    "is_s=Y&degree%5B%5D=MSC&degree%5B%5D=MA&degree%5B%5D=MPM&"
    "degree%5B%5D=MPP&year=2026-27"
)
APPLICATION_URL = "https://fytgs.hkust.edu.hk/apply"
APPLICATION_OPENS_AT = "2025-09-01"

MONTHS = (
    "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|"
    "January|February|March|April|June|July|August|September|October|"
    "November|December"
)
DATE_RE = re.compile(
    rf"(?P<date>\d{{1,2}}\s+(?:{MONTHS})\s+20\d{{2}})"
    rf"\s*(?:\((?P<round>Round\s+\d+)\))?",
    flags=re.IGNORECASE,
)


class HKUSTAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    application_opens_at_basis = "inferred-cycle-default"
    intake = "September 2026"

    def __init__(
        self,
        minimum_expected_programmes: int = 35,
        *,
        detail_workers: int = 6,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.detail_workers = detail_workers

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        programmes = self.parse_catalog(fetcher(self.catalog_url)).programmes

        def parse_one(programme: DiscoveredProgramme) -> DiscoveredProgramme:
            try:
                return self._parse_detail(programme, fetcher(programme.source_url))
            except Exception as exc:
                return replace(
                    programme,
                    deadline_text=(
                        "Programme found in HKUST's official program catalog, but "
                        f"the detail page could not be fetched: {type(exc).__name__}: "
                        f"{str(exc)[:180]}"
                    ),
                    parse_status="no-deadline",
                )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            detailed = list(executor.map(parse_one, programmes))
        return DiscoveredCatalog(
            application_opens_at=APPLICATION_OPENS_AT, programmes=detailed
        )

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        soup = BeautifulSoup(html, "html.parser")
        programmes: dict[str, DiscoveredProgramme] = {}
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/pgprog/2026-27/" not in href:
                continue
            text = _normalise_text(link.get_text(" ", strip=True))
            degree_type = _degree_type(text)
            if degree_type is None:
                continue
            source_url = urljoin("https://prog-crs.hkust.edu.hk", href)
            programme_id = f"hkust-{_slug(source_url.rstrip('/').split('/')[-1])}"
            programmes[programme_id] = DiscoveredProgramme(
                id=programme_id,
                name=_catalogue_name(text),
                degree_type=degree_type,
                faculty="",
                department="",
                source_url=source_url,
                application_url=self.application_url,
                windows=[],
                deadline_text="Programme found in HKUST's official program catalog.",
                parse_status="no-deadline",
            )
        values = sorted(programmes.values(), key=lambda item: item.id)
        if len(values) < self.minimum_expected_programmes:
            raise ValueError(
                f"HKUST catalog only contained {len(values)} taught master's "
                f"programmes; expected at least {self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=values)

    def _parse_detail(
        self,
        programme: DiscoveredProgramme,
        html: str,
    ) -> DiscoveredProgramme:
        text = _normalise_text(
            BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        )
        title = (
            _extract_between(text, "Award Title", "Award Title (Chinese)")
            or programme.name
        )
        degree_type = _degree_type(title) or programme.degree_type
        department = _extract_between(text, "Offering Unit", "Program Advisor") or ""
        website = _extract_between(text, "Website", "Enquiry")
        application_url = _normalise_url(website) or programme.application_url
        excerpt = _application_excerpt(text)
        windows = _parse_windows(excerpt)
        return replace(
            programme,
            id=_programme_id(title, programme.source_url),
            name=title,
            degree_type=degree_type,
            faculty=department,
            department=department,
            application_url=application_url,
            windows=windows,
            deadline_text=excerpt or programme.deadline_text,
            parse_status="parsed" if windows else "no-deadline",
        )


def _parse_windows(text: str) -> list[DiscoveredWindow]:
    if not text:
        return []
    fall_match = re.search(
        r"For\s+2026/27\s+Fall\s+Term\s+Intake.*?(?=For\s+20\d{2}/\d{2}\s+Spring|Admissions is|Back Privacy|$)",
        text,
        flags=re.IGNORECASE,
    )
    target = fall_match.group(0) if fall_match else text
    windows: list[DiscoveredWindow] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for label, categories in (
        ("Non-local Applicants", ["international-students"]),
        ("Local Applicants", ["domestic-students"]),
    ):
        block_match = re.search(
            rf"{re.escape(label)}\*?\s*(?P<block>.*?)(?=Non-local Applicants|Local Applicants|Admissions is|For\s+20\d{{2}}/\d{{2}}|$)",
            target,
            flags=re.IGNORECASE,
        )
        if block_match is None:
            continue
        block = block_match.group("block")
        for match in DATE_RE.finditer(block):
            closes_at = _parse_date(match.group("date"))
            round_label = match.group("round") or label
            key = (round_label, closes_at, tuple(categories))
            if key in seen:
                continue
            seen.add(key)
            windows.append(
                DiscoveredWindow(
                    round=round_label,
                    closes_at=closes_at,
                    applicant_categories=categories,
                    opens_at=None,
                    intake="September 2026",
                )
            )
    return windows


def _application_excerpt(text: str) -> str:
    start = text.find("APPLICATION")
    if start < 0:
        start = text.find("Application Deadlines")
    if start < 0:
        return ""
    end = text.find("Back Privacy", start)
    if end < 0:
        end = start + 1600
    return text[start:end]


def _extract_between(text: str, start_label: str, end_label: str) -> str | None:
    start = text.find(start_label)
    if start < 0:
        return None
    start += len(start_label)
    end = text.find(end_label, start)
    if end < 0:
        return None
    value = _normalise_text(text[start:end])
    return value or None


def _catalogue_name(text: str) -> str:
    match = re.search(r"(.+?)\s+(MSc|MA|MPM|MPP)(?:\s*/\s*PGD)?$", text)
    if match:
        return f"{match.group(2)} {match.group(1).split(' ', 1)[-1]}"
    return text


def _programme_id(title: str, source_url: str) -> str:
    slug_from_url = source_url.rstrip("/").split("/")[-1]
    rules = (
        (r"^Master of Science in (.+)$", "msc"),
        (r"^Master of Arts in (.+)$", "ma"),
        (r"^Master of Public Management$", "mpm"),
        (r"^Master of Public Policy$", "mpp"),
    )
    for pattern, suffix in rules:
        match = re.match(pattern, title, flags=re.IGNORECASE)
        if match:
            subject = match.group(1) if match.groups() else title
            return f"hkust-{_slug(subject)}-{suffix}"
    return f"hkust-{_slug(slug_from_url)}"


def _degree_type(title: str) -> str | None:
    if "MSc" in title or title.startswith("Master of Science"):
        return "MSc"
    if re.search(r"\bMA\b", title) or title.startswith("Master of Arts"):
        return "MA"
    if "MPM" in title or title.startswith("Master of Public Management"):
        return "MPM"
    if "MPP" in title or title.startswith("Master of Public Policy"):
        return "MPP"
    return None


def _parse_date(value: str) -> str:
    value = _normalise_text(value).replace("Sept ", "Sep ")
    for pattern in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported HKUST date: {value}")


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())


def _normalise_url(value: str | None) -> str | None:
    if not value:
        return None
    if re.match(r"^https?://", value, flags=re.IGNORECASE):
        return value
    if "." in value and not value.startswith("/"):
        return f"https://{value}"
    return None
