from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "northwestern-university"
CATALOG_URL = "https://www.northwestern.edu/academics/graduate-a-to-z.html"
BIENEN_TIMELINE_URL = (
    "https://www.music.northwestern.edu/admission/graduate/application-timeline"
)
BIENEN_APPLICATION_URL = "https://apply.music.northwestern.edu/apply/"
EXISTING_CS_ID = "northwestern-computer-science-ms"

_OPEN_RE = re.compile(
    r"The (?P<intake>20\d{2}) MM & DMA application will be available "
    r"(?P<date>[A-Z][a-z]+ \d{1,2}, 20\d{2})\.",
    re.IGNORECASE,
)
_TIMELINE_RE = re.compile(
    r"Fall (?P<intake>20\d{2}) Graduate Application Timeline.*?"
    r"(?P<close>[A-Z][a-z]+ \d{1,2})\s+Graduate Application and "
    r"prescreening materials \(if applicable\) due",
    re.IGNORECASE | re.DOTALL,
)


class NorthwesternAdapter(BaseProgrammeAdapter):
    """Discover master's programmes from Northwestern's university directory."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = CATALOG_URL
    intake = "Fall 2027"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 105,
        maximum_expected_programmes: int = 120,
        target_intake_year: int = 2027,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.target_intake_year = target_intake_year
        self.intake = f"Fall {target_intake_year}"

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        bienen_window = _bienen_window(
            fetcher(BIENEN_TIMELINE_URL),
            target_intake_year=self.target_intake_year,
        )
        programmes = _programmes(
            fetcher(CATALOG_URL),
            bienen_window=bienen_window,
            target_intake_year=self.target_intake_year,
        )
        programmes = sorted(programmes, key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Northwestern's official directory only contained "
                f"{len(programmes)} unique master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "Northwestern's official directory unexpectedly contained "
                f"{len(programmes)} unique master's programmes; expected at most "
                f"{self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("Northwestern official directory generated duplicate IDs")
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _programmes(
    html: str,
    *,
    bienen_window: DiscoveredWindow | None,
    target_intake_year: int,
) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes = []
    seen_urls = set()
    for row in soup.select("table tr"):
        cells = [
            _normalise(cell.get_text(" ", strip=True)) for cell in row.select("td")
        ]
        if len(cells) < 6 or cells[3] != "Masters Degree":
            continue
        link = row.find("a", href=True)
        if link is None:
            raise ValueError("Northwestern master's directory row lacked a URL")
        source_url = _canonical_url(urljoin(CATALOG_URL, str(link["href"])))
        if source_url in seen_urls:
            continue
        title, school, degree = cells[:3]
        if not title or not school or not degree:
            raise ValueError("Northwestern master's directory row lacked metadata")
        programme_id = (
            EXISTING_CS_ID
            if title == "Computer Science MS"
            else f"northwestern-{_slug(title)}"
        )
        is_bienen_mm = school == "Bienen" and degree == "MM"
        windows = [bienen_window] if is_bienen_mm and bienen_window else []
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=title,
                degree_type=degree,
                faculty=school,
                department=title,
                source_url=source_url,
                application_url=(
                    BIENEN_APPLICATION_URL if is_bienen_mm else source_url
                ),
                windows=windows,
                deadline_text=_deadline_text(
                    is_bienen_mm=is_bienen_mm,
                    has_bienen_window=bool(bienen_window),
                    target_intake_year=target_intake_year,
                ),
                parse_status="parsed" if windows else "no-deadline",
                retrieval_method=(
                    "official-university-directory-and-bienen-timeline-html"
                    if is_bienen_mm
                    else "official-university-graduate-directory-html"
                ),
                evidence_quality="official-full-text",
            )
        )
        seen_urls.add(source_url)
    return programmes


def _bienen_window(
    html: str,
    *,
    target_intake_year: int,
) -> DiscoveredWindow | None:
    text = _normalise(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    open_match = _OPEN_RE.search(text)
    timeline_match = _TIMELINE_RE.search(text)
    if open_match is None or timeline_match is None:
        return None
    open_intake = int(open_match.group("intake"))
    close_intake = int(timeline_match.group("intake"))
    if open_intake != target_intake_year or close_intake != target_intake_year:
        return None
    opens_at = datetime.strptime(open_match.group("date"), "%B %d, %Y").date()
    closes_at = datetime.strptime(
        f"{timeline_match.group('close')}, {opens_at.year}", "%B %d, %Y"
    ).date()
    if closes_at <= opens_at:
        raise ValueError("Northwestern Bienen timeline had an invalid date range")
    return DiscoveredWindow(
        round="MM graduate application",
        opens_at=opens_at.isoformat(),
        closes_at=closes_at.isoformat(),
        intake=f"Fall {target_intake_year}",
        source_url=BIENEN_TIMELINE_URL,
    )


def _deadline_text(
    *,
    is_bienen_mm: bool,
    has_bienen_window: bool,
    target_intake_year: int,
) -> str:
    if is_bienen_mm and has_bienen_window:
        return (
            "Northwestern's official graduate directory confirms this MM programme, "
            f"and Bienen's official timeline publishes the exact Fall "
            f"{target_intake_year} application opening and closing dates."
        )
    if is_bienen_mm:
        return (
            "Northwestern's official graduate directory confirms this MM programme, "
            f"but Bienen does not yet publish an exact Fall {target_intake_year} "
            "opening and closing date pair."
        )
    return (
        "Northwestern's official university-wide graduate directory confirms this "
        "master's programme. TGS publishes only a mid-September opening description, "
        "while programme and professional-school deadlines vary; no exact opening "
        f"and closing pair for Fall {target_intake_year} is inferred."
    )


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Northwestern directory contained an invalid URL: {value}")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _slug(value: object) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", _normalise(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
