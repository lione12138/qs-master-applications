from __future__ import annotations

import concurrent.futures
import re
import unicodedata
from dataclasses import replace
from datetime import datetime
from urllib.parse import quote

from bs4 import BeautifulSoup

from .base import DiscoveredCatalog, DiscoveredProgramme, DiscoveredWindow

UNIVERSITY_ID = "the-university-of-hong-kong"
CATALOG_URL = "https://portal.hku.hk/tpg-admissions/programme-listing"
APPLICATION_URL = "https://portal.hku.hk/tpg-admissions/applying"
APPLICATION_OPENS_AT = "2025-09-01"
DETAIL_URL_TEMPLATE = (
    "https://portal.hku.hk/tpg-admissions/programme-details?"
    "programme={programme}&mode=FT"
)
API_ROOT = "https://portal.hku.hk/SavedQueryService/Execute"
FULL_TIME_MODE = "629270000"
PART_TIME_MODE = "629270001"

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
ROUND_DATE_RE = re.compile(
    rf"(?P<label>Round\s+\d+(?:\s*\([^)]+\))?|Main|Clearing|Final)"
    rf"\s*:\s*(?:12:00\s+noon\s+\(GMT\s*\+8\),\s*)?"
    rf"(?P<date>(?:{MONTHS})\s+\d{{1,2}},\s+20\d{{2}})",
    flags=re.IGNORECASE,
)
INTAKE_RE = re.compile(
    rf"Expected Programme Start Date\s+"
    rf"(?P<intake>(?:20\d{{2}}\s+)?(?:{MONTHS})(?:\s+20\d{{2}})?)",
    flags=re.IGNORECASE,
)


class HKUAdapter:
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    application_opens_at_basis = "inferred-cycle-default"
    intake = "September 2026"

    def __init__(
        self,
        minimum_expected_programmes: int = 80,
        *,
        detail_workers: int = 6,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.detail_workers = detail_workers

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        programmes = self._fetch_listing(fetcher)

        def parse_one(programme: DiscoveredProgramme) -> DiscoveredProgramme:
            try:
                return self._parse_detail(programme, fetcher(programme.source_url))
            except Exception as exc:
                return replace(
                    programme,
                    deadline_text=(
                        "Programme found in HKU's official taught postgraduate "
                        "listing, but its detail page could not be fetched during "
                        f"discovery: {type(exc).__name__}: {str(exc)[:180]}"
                    ),
                    parse_status="no-deadline",
                )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            detailed = list(executor.map(parse_one, programmes))
        return DiscoveredCatalog(application_opens_at=APPLICATION_OPENS_AT, programmes=detailed)

    def _fetch_listing(self, fetcher) -> list[DiscoveredProgramme]:
        programmes: dict[str, DiscoveredProgramme] = {}
        for mode in (FULL_TIME_MODE, PART_TIME_MODE):
            for endpoint in (
                f"any-faculty-programmes/%/{mode}/1/10/"
                "hkutgp_feefornonlocalstudent/0/1000000",
                f"any-faculty-programmes-without-fee/%/{mode}/1/10",
                f"any-faculty-closed-programmes/%/{mode}/1/10",
                f"any-faculty-opening-programmes/%/{mode}/1/10",
            ):
                data = _json_loads(fetcher(f"{API_ROOT}/{endpoint}"))
                for item in data.get("data", []):
                    programme = self._programme_from_api_item(item)
                    if programme is not None:
                        programmes.setdefault(programme.id, programme)
        values = sorted(programmes.values(), key=lambda item: item.id)
        if len(values) < self.minimum_expected_programmes:
            raise ValueError(
                f"HKU catalog only contained {len(values)} master's programmes; "
                f"expected at least {self.minimum_expected_programmes}"
            )
        return values

    def _programme_from_api_item(self, item: dict) -> DiscoveredProgramme | None:
        attrs = item.get("Attributes", {})
        name = _normalise_text(attrs.get("hkutgp_name") or "")
        degree_type = _degree_type(name)
        if not name or degree_type is None:
            return None
        slug = _detail_slug(attrs)
        if not slug:
            return None
        faculty = _normalise_text(
            (item.get("FormattedValues") or {}).get("hkutgp_facultyid") or ""
        )
        source_url = DETAIL_URL_TEMPLATE.format(programme=quote(slug, safe="-"))
        return DiscoveredProgramme(
            id=_programme_id(name, degree_type),
            name=name,
            degree_type=degree_type,
            faculty=faculty,
            department="",
            source_url=source_url,
            application_url=self.application_url,
            windows=[],
            deadline_text="Programme found in HKU's official taught postgraduate listing.",
            parse_status="no-deadline",
        )

    def _parse_detail(
        self,
        programme: DiscoveredProgramme,
        html: str,
    ) -> DiscoveredProgramme:
        text = _normalise_text(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
        lower = text.lower()
        if "programme not found" in lower:
            return programme

        deadline_pos = lower.find("application deadline")
        if deadline_pos < 0:
            return programme
        start = max(0, deadline_pos - 220)
        description_pos = lower.find(" description", deadline_pos)
        end = description_pos if description_pos > deadline_pos else deadline_pos + 1200
        excerpt = text[start:end]
        intake = _parse_intake(excerpt) or self.intake
        windows: list[DiscoveredWindow] = []
        seen: set[tuple[str, str]] = set()
        for match in ROUND_DATE_RE.finditer(excerpt):
            label = _normalise_round(match.group("label"))
            closes_at = _parse_date(match.group("date"))
            key = (label, closes_at)
            if key in seen:
                continue
            seen.add(key)
            windows.append(
                DiscoveredWindow(
                    round=label,
                    closes_at=closes_at,
                    opens_at=None,
                    intake=intake,
                )
            )
        if not windows:
            return programme
        return replace(
            programme,
            windows=windows,
            deadline_text=excerpt,
            parse_status="parsed",
        )


def _json_loads(value: str) -> dict:
    import json

    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("HKU API response was not a JSON object")
    return payload


def _detail_slug(attrs: dict) -> str | None:
    direct = attrs.get("hkutgp_seofriendlyname")
    if isinstance(direct, str) and direct:
        return direct
    aliased = attrs.get("rootprogramme.hkutgp_name")
    if isinstance(aliased, dict) and aliased.get("Value"):
        return str(aliased["Value"])
    return None


def _degree_type(title: str) -> str | None:
    if title.startswith(("Doctor of ", "Advanced Diploma")):
        return None
    for prefix, degree in (
        ("Master of Science", "MSc"),
        ("Master of Arts", "MA"),
        ("Master of Business Administration", "MBA"),
        ("Master of Laws", "LLM"),
        ("Master of Education", "MEd"),
        ("Master of Nursing", "Master"),
        ("Master of Public Health", "MPH"),
        ("Master of ", "Master"),
    ):
        if title.startswith(prefix):
            return degree
    return None


def _programme_id(title: str, degree_type: str) -> str:
    rules = (
        (r"^Master of Science in (.+)$", "msc"),
        (r"^Master of Arts in (.+)$", "ma"),
        (r"^Master of Business Administration(?: in (.+))?$", "mba"),
        (r"^Master of Laws(?: in (.+))?$", "llm"),
        (r"^Master of Education(?: in (.+))?$", "med"),
        (r"^Master of Public Health(?: in (.+))?$", "mph"),
        (r"^Master of (.+)$", "master"),
    )
    for pattern, suffix in rules:
        match = re.match(pattern, title, flags=re.IGNORECASE)
        if match:
            subject = match.group(1) or title
            subject = re.sub(r"\s*-\s*(.+?)\s+Stream$", r" \1", subject)
            subject = re.sub(
                rf"\s*\((?:{MONTHS})\s+20\d{{2}}\)\s*$",
                "",
                subject,
                flags=re.IGNORECASE,
            )
            return f"hku-{_slug(subject)}-{suffix}"
    return f"hku-{_slug(title)}-{_slug(degree_type)}"


def _normalise_round(value: str) -> str:
    value = _normalise_text(value)
    lowered = value.lower()
    if lowered == "main":
        return "Main"
    if lowered == "clearing":
        return "Clearing"
    if lowered == "final":
        return "Final"
    return value


def _parse_intake(value: str) -> str | None:
    match = INTAKE_RE.search(value)
    if match is None:
        return None
    intake = _normalise_text(match.group("intake"))
    year_match = re.search(r"\b20\d{2}\b", intake)
    month_match = re.search(MONTHS, intake, flags=re.IGNORECASE)
    if year_match is None or month_match is None:
        return None
    return f"{month_match.group(0).capitalize()} {year_match.group(0)}"


def _parse_date(value: str) -> str:
    normalised = re.sub(r"\s+", " ", value.strip())
    for pattern in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(normalised, pattern).date().isoformat()
        except ValueError:
            continue
    normalised = normalised.replace("Sept ", "Sep ")
    return datetime.strptime(normalised, "%b %d, %Y").date().isoformat()


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
