from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup, Tag

from ..http_client import DEFAULT_USER_AGENT
from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "korea-university"
CATALOG_URL = "https://graduate2.korea.ac.kr/department/major.html"
CATALOG_API_URL = "https://graduate2.korea.ac.kr/main/ajax_board.html"
SCHEDULE_URL = "https://graduate2.korea.ac.kr/admission/schedule.html"
APPLICATION_URL = "https://graduate2.korea.ac.kr/admission/guide.html"
EXISTING_CSE_ID = "korea-university-computer-science-master"

_FALL_2026_RE = re.compile(
    r"March 3\s*\(Tue\)\s*10:00\s*-\s*March 13\s*\(Fri\)\s*17:00,\s*2026",
    re.IGNORECASE,
)


class KoreaUniversityAdapter(BaseProgrammeAdapter):
    """Discover Seoul-campus master's departments from Korea University."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Spring 2027 or latest officially published cycle"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 72,
        maximum_expected_programmes: int = 80,
        department_payload_fetcher: Callable[[], str] | None = None,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.department_payload_fetcher = (
            department_payload_fetcher or _fetch_seoul_department_payload
        )

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        schedule_evidence = _schedule_evidence(fetcher(SCHEDULE_URL))
        programmes = sorted(
            _programmes(
                self.department_payload_fetcher(),
                schedule_evidence=schedule_evidence,
            ),
            key=lambda item: item.id,
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Korea University's official directory only contained "
                f"{len(programmes)} Seoul-campus master's departments; expected at "
                f"least {self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "Korea University's official directory unexpectedly contained "
                f"{len(programmes)} Seoul-campus master's departments; expected at "
                f"most {self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("Korea University directory generated duplicate IDs")
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _fetch_seoul_department_payload() -> str:
    body = urlencode(
        [
            ("mkind", "sch_major_en"),
            ("keyfield", ""),
            ("key", ""),
            ("tab", "all"),
            ("tbl", "in_bbs_major_en"),
            ("ll[]", "1"),
        ]
    ).encode("utf-8")
    request = Request(
        CATALOG_API_URL,
        data=body,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": CATALOG_URL,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urlopen(request, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Korea University department API returned no HTML content")
    return content


def _programmes(html: str, *, schedule_evidence: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes = []
    for box in soup.select(".major_box"):
        title_node = box.select_one(".major_tit")
        name = _normalise(title_node.get_text(" ", strip=True) if title_node else "")
        master_values = _group_values(box, "Master's Program")
        if not name or not master_values:
            continue
        faculty_values = _group_values(box, "College")
        faculty = faculty_values[0] if faculty_values else "Graduate School"
        source_link = box.select_one("a.home[href]")
        source_url = (
            _canonical_url(str(source_link["href"])) if source_link else CATALOG_URL
        )
        programme_name = f"Master's in {_programme_subject(name)}"
        programmes.append(
            DiscoveredProgramme(
                id=(
                    EXISTING_CSE_ID
                    if name == "Department of Computer Science and Engineering"
                    else f"korea-university-{_slug(name)}-master"
                ),
                name=programme_name,
                degree_type="Master",
                faculty=faculty,
                department=name,
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=[],
                deadline_text=schedule_evidence,
                parse_status="no-deadline",
                retrieval_method="official-graduate-school-department-api-and-schedule-html",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _group_values(box: Tag, heading: str) -> list[str]:
    for group in box.select(".group"):
        title = group.select_one(".major_sub_tit")
        if (
            title is None
            or _ascii_apostrophe(title.get_text(" ", strip=True)) != heading
        ):
            continue
        return [
            value
            for node in group.select("ul li")
            if (value := _normalise(node.get_text(" ", strip=True)))
        ]
    return []


def _schedule_evidence(html: str) -> str:
    text = _normalise(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    if _FALL_2026_RE.search(text):
        return (
            "Korea University's official English admission schedule publishes the "
            "Fall 2026 online-application period March 3, 2026 10:00 through March "
            "13, 2026 17:00. That cycle has passed, while the next-cycle procedure "
            "gives only month-level guidance; no 2027 exact window is inferred."
        )
    return (
        "Korea University's official admission pages currently publish no exact "
        "opening and closing date pair for the next intake; no date is inferred."
    )


def _programme_subject(name: str) -> str:
    for prefix in ("Department of ", "Program in "):
        if name.startswith(prefix):
            return name.removeprefix(prefix)
    return name


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (
        hostname.endswith(".korea.edu") or hostname.endswith(".korea.ac.kr")
    ):
        raise ValueError(
            f"Korea University directory contained an invalid URL: {value}"
        )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _ascii_apostrophe(value: object) -> str:
    return _normalise(value).replace("’", "'")


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _slug(value: object) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", _normalise(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
