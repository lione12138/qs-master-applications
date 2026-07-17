from __future__ import annotations

import re
import unicodedata
from datetime import date
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "national-taiwan-university-ntu"
ADMISSIONS_URL = (
    "https://admissions.ntu.edu.tw/apply/degree-students/international-students/"
)
APPLICATION_URL = "https://oiasystem.ntu.edu.tw/globaladmission/foreign"
EXISTING_CSE_ID = "ntu-computer-science-information-engineering-master"

_ROUND_RE = re.compile(
    r"First Round\s*[:：]\s*(20\d{2}-\d{2}-\d{2})\s*~\s*(20\d{2}-\d{2}-\d{2})",
    re.IGNORECASE,
)


class NTUTaiwanAdapter(BaseProgrammeAdapter):
    """Discover NTU master's programs open to February international entry."""

    university_id = UNIVERSITY_ID
    catalog_url = ADMISSIONS_URL
    application_url = APPLICATION_URL
    intake = "February 2027"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 68,
        maximum_expected_programmes: int = 78,
        target_intake_year: int = 2027,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.target_intake_year = target_intake_year
        self.intake = f"February {target_intake_year}"

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        admissions_html = _fetch_admissions_page(fetcher)
        cycle_url = _cycle_catalog_url(
            admissions_html, target_intake_year=self.target_intake_year
        )
        catalog_html = fetcher(cycle_url)
        opens_at, closes_at = _round_dates(catalog_html)
        programmes = sorted(
            _programmes(
                catalog_html,
                catalog_url=cycle_url,
                opens_at=opens_at,
                closes_at=closes_at,
                target_intake_year=self.target_intake_year,
            ),
            key=lambda item: item.id,
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "NTU's official international-admission directory only contained "
                f"{len(programmes)} available master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "NTU's official international-admission directory unexpectedly "
                f"contained {len(programmes)} available master's programmes; "
                f"expected at most {self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("NTU international directory generated duplicate IDs")
        return DiscoveredCatalog(
            application_opens_at=opens_at,
            programmes=programmes,
        )


def _fetch_admissions_page(fetcher) -> str:
    last_error = None
    for url in (
        ADMISSIONS_URL,
        f"{ADMISSIONS_URL}?v=1",
        f"{ADMISSIONS_URL}?output=1",
        f"{ADMISSIONS_URL}?page_id=98",
    ):
        try:
            html = fetcher(url)
            if "2027" in html or "February Entry" in html:
                return html
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise ValueError("NTU international-admissions page contained no cycle links")


def _cycle_catalog_url(html: str, *, target_intake_year: int) -> str:
    soup = BeautifulSoup(html, "html.parser")
    expected_label = f"{target_intake_year} February Entry (Graduate programs only)"
    for link in soup.select("a[href]"):
        if _normalise(link.get_text(" ", strip=True)) != expected_label:
            continue
        return _canonical_catalog_url(urljoin(ADMISSIONS_URL, str(link["href"])))
    raise ValueError(f"NTU admissions page lacked the {expected_label} catalogue")


def _round_dates(html: str) -> tuple[str, str]:
    text = _normalise(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    match = _ROUND_RE.search(text)
    if match is None:
        raise ValueError("NTU catalogue lacked an exact First Round date range")
    opens_at, closes_at = match.groups()
    if date.fromisoformat(closes_at) <= date.fromisoformat(opens_at):
        raise ValueError("NTU catalogue contained an invalid application date range")
    return opens_at, closes_at


def _programmes(
    html: str,
    *,
    catalog_url: str,
    opens_at: str,
    closes_at: str,
    target_intake_year: int,
) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes = []
    for row in soup.select("tr.js-degreeTr"):
        name_node = row.select_one('td.js-deptName[data-degree="M"]')
        if name_node is None:
            continue
        availability = name_node.find_next_sibling("td")
        link = availability.select_one("a[href]") if availability else None
        if link is None:
            continue
        department = _clean_department(name_node.get_text(" ", strip=True))
        faculty_node = row.select_one("td.js-college")
        faculty = _normalise(
            faculty_node.get_text(" ", strip=True) if faculty_node else "NTU"
        )
        source_url = _canonical_catalog_url(urljoin(catalog_url, str(link["href"])))
        subject = _programme_subject(department)
        programme_id = (
            EXISTING_CSE_ID
            if department
            == "Department of Computer Science and Information Engineering"
            else f"ntu-{_slug(subject)}-master"
        )
        window = DiscoveredWindow(
            round="International admission first round",
            opens_at=opens_at,
            closes_at=closes_at,
            intake=f"February {target_intake_year}",
            applicant_categories=["international-students"],
            source_url=catalog_url,
        )
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=f"Master's in {subject}",
                degree_type="Master",
                faculty=faculty,
                department=department,
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=[window],
                deadline_text=(
                    "NTU's official international-admission catalogue marks this "
                    f"master's programme available for February {target_intake_year} "
                    f"and publishes the exact first-round period {opens_at} through "
                    f"{closes_at}."
                ),
                parse_status="parsed",
                retrieval_method="official-international-admission-cycle-directory-html",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _canonical_catalog_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "oiasystem.ntu.edu.tw"
        or not parsed.path.startswith("/globaladmission/foreign/requirement/")
    ):
        raise ValueError(f"NTU admissions page contained an invalid URL: {value}")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _clean_department(value: object) -> str:
    return re.sub(
        r"\s*\(Click for each division\)\s*$", "", _normalise(value), flags=re.I
    )


def _programme_subject(name: str) -> str:
    for prefix in ("Department of ", "Graduate Institute of ", "Institute of "):
        if name.startswith(prefix):
            return name.removeprefix(prefix)
    return name


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _slug(value: object) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", _normalise(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
