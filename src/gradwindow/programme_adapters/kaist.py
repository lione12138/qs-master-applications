from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

from ..http_client import DEFAULT_USER_AGENT, fetch_page
from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "kaist"
CATALOG_URL = "https://admission.kaist.ac.kr/intl-graduate/Admission/Notice"
NOTICE_API_URL = "https://admission.kaist.ac.kr/wz/api/board/44/notices"
TIMELINE_URL = "https://admission.kaist.ac.kr/intl-graduate/Admission/YearlyTimelines"
APPLICATION_URL = "https://admission.kaist.ac.kr/intl-graduate/Admission/Apply"

_NOTICE_TITLE = "Application Guide for Spring 2027 Admission"
_WINDOW_RE = re.compile(
    r"Online Application Period:\s*August 18,\s*10:00 A\.M\.\s*[–-]\s*"
    r"September 1,\s*5:00 P\.M\.\s*2026\s*\(KST\)",
    re.I,
)
_TIMELINE_RE = re.compile(
    r"Spring 2027\s*Entry:\s*August 18\s*[–-]\s*September 1,\s*2026",
    re.I,
)

NoticeFetcher = Callable[[str], str]


@dataclass(frozen=True, slots=True)
class _Cell:
    text: str
    href: str | None = None


class KAISTAdapter(BaseProgrammeAdapter):
    """Discover the M.S. programmes confirmed for KAIST's current cycle."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    intake = "Spring 2027"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 28,
        maximum_expected_programmes: int = 35,
        notice_fetcher: NoticeFetcher | None = None,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.notice_fetcher = notice_fetcher or _fetch_notice_json

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        timeline = _normalise(
            BeautifulSoup(fetcher(TIMELINE_URL), "html.parser").get_text(
                " ", strip=True
            )
        )
        if _TIMELINE_RE.search(timeline) is None:
            raise ValueError(
                "KAIST official timeline did not confirm the Spring 2027 window"
            )
        programmes, opens_at, closes_at = _notice_programmes(
            self.notice_fetcher(NOTICE_API_URL)
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "KAIST official notice only contained "
                f"{len(programmes)} Spring 2027 M.S. programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "KAIST official notice unexpectedly contained "
                f"{len(programmes)} Spring 2027 M.S. programmes; expected at most "
                f"{self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError(
                "KAIST Spring 2027 table generated duplicate programme IDs"
            )
        return DiscoveredCatalog(
            application_opens_at=opens_at,
            programmes=sorted(programmes, key=lambda item: item.id),
        )


def _notice_programmes(payload: str) -> tuple[list[DiscoveredProgramme], str, str]:
    data = json.loads(payload).get("data", [])
    notice = next(
        (item for item in data if _NOTICE_TITLE in str(item.get("pstTtl", ""))),
        None,
    )
    if notice is None:
        raise ValueError("KAIST notice API lacked the Spring 2027 application guide")
    text = _normalise(notice.get("pstTextCn", ""))
    if _WINDOW_RE.search(text) is None:
        raise ValueError("KAIST Spring 2027 notice lacked the exact online window")
    opens_at = "2026-08-18"
    closes_at = "2026-09-01"
    if date.fromisoformat(closes_at) <= date.fromisoformat(opens_at):
        raise ValueError("KAIST Spring 2027 notice published an invalid window")
    notice_url = f"{CATALOG_URL}#{notice['pstNo']}"
    table = BeautifulSoup(str(notice.get("pstCn", "")), "html.parser").select_one(
        "table"
    )
    if table is None:
        raise ValueError("KAIST Spring 2027 notice lacked its programme table")
    grid = _expand_table(table)
    if not grid or [cell.text for cell in grid[0]][:3] != [
        "College",
        "School/Department/Division",
        "M.S.",
    ]:
        raise ValueError("KAIST Spring 2027 programme table had unexpected columns")

    programmes = []
    for row in grid[1:]:
        if len(row) < 6 or row[2].text != "\u25cf":
            continue
        college = row[0].text
        name = re.sub(r"^-\s*", "", row[1].text).strip()
        if not college or not name:
            raise ValueError("KAIST Spring 2027 M.S. row lacked college or programme")
        source_url = _official_programme_url(row[5]) or notice_url
        programmes.append(
            DiscoveredProgramme(
                id=f"kaist-{_slug(name)}",
                name=name,
                degree_type="MBA" if "MBA" in name else "Master",
                faculty=college,
                department=name,
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=[
                    DiscoveredWindow(
                        round="International graduate admission",
                        opens_at=opens_at,
                        closes_at=closes_at,
                        intake="Spring 2027",
                        applicant_categories=["international-students"],
                        source_url=notice_url,
                    )
                ],
                deadline_text=(
                    "KAIST's official Spring 2027 application guide marks this "
                    "programme as offering the M.S. degree and publishes the online "
                    f"application period {opens_at} through {closes_at} (KST)."
                ),
                parse_status="parsed",
                retrieval_method="official-cycle-notice-api-table",
                evidence_quality="official-full-text",
            )
        )
    return programmes, opens_at, closes_at


def _expand_table(table) -> list[list[_Cell]]:
    width = 6
    pending: dict[int, tuple[_Cell, int]] = {}
    grid = []
    for html_row in table.select("tr"):
        html_cells = iter(html_row.find_all(["th", "td"], recursive=False))
        row = []
        column = 0
        while column < width:
            if column in pending:
                value, remaining = pending[column]
                row.append(value)
                if remaining == 1:
                    del pending[column]
                else:
                    pending[column] = (value, remaining - 1)
                column += 1
                continue
            try:
                html_cell = next(html_cells)
            except StopIteration:
                row.extend([_Cell("")] * (width - column))
                break
            link = html_cell.select_one("a[href]")
            value = _Cell(
                _normalise(html_cell.get_text(" ", strip=True)),
                str(link["href"]) if link is not None else None,
            )
            rowspan = int(html_cell.get("rowspan", 1))
            colspan = int(html_cell.get("colspan", 1))
            for _ in range(colspan):
                row.append(value)
                if rowspan > 1:
                    pending[column] = (value, rowspan - 1)
                column += 1
        grid.append(row)
    return grid


def _official_programme_url(cell: _Cell) -> str | None:
    value = cell.href or cell.text
    value = value.replace("\ufeff", "").strip()
    if not value:
        return None
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (
        host == "kaist.ac.kr"
        or host.endswith(".kaist.ac.kr")
        or host == "www.business.kaist.edu"
    ):
        raise ValueError(
            f"KAIST notice contained a non-official programme URL: {value}"
        )
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, "")
    )


def _fetch_notice_json(url: str) -> str:
    return fetch_page(
        url,
        user_agent=DEFAULT_USER_AGENT,
        timeout=30,
        max_bytes=3_000_000,
        accept="application/json,text/plain,*/*",
    ).body


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _normalise(value: object) -> str:
    return " ".join(
        str(value or "").replace("\xa0", " ").replace("\ufeff", " ").split()
    )
