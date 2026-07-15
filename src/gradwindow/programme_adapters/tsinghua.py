from __future__ import annotations

import html
import json
import re
from collections.abc import Callable
from datetime import date
from urllib.parse import urlencode, urljoin, urlparse

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "tsinghua-university"
CATALOG_URL = "https://yz.tsinghua.edu.cn/en/Programs/Master_s_Degrees.htm"
QUERY_ENDPOINT = "https://yzbm.tsinghua.edu.cn/publish/s05/s0503/querydetail"
APPLICATION_URL = "https://yzbm.tsinghua.edu.cn/intlLogin"
ADVANCED_COMPUTING_ID = "tsinghua-advanced-computing-master"
ADVANCED_COMPUTING_SOURCE_URL = "https://ac.cs.tsinghua.edu.cn/application.html"

_FULL_RANGE = re.compile(
    r"(?P<sy>20\d{2})\s*年\s*(?P<sm>\d{1,2})\s*月\s*"
    r"(?P<sd>\d{1,2})\s*日(?:\s*\d{1,2}(?::\d{2})?)?\s*"
    r"(?:至|—|–|-)+\s*(?P<ey>20\d{2})\s*年\s*"
    r"(?P<em>\d{1,2})\s*月\s*(?P<ed>\d{1,2})\s*日"
)
_NOW_DEADLINE = re.compile(
    r"(?:即日起|现在)\s*(?:至|—|–|-)+\s*(?P<y>20\d{2})\s*年\s*"
    r"(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日"
)
_FINAL_DEADLINE = re.compile(r"20\d{2}-\d{2}-\d{2}")


class TsinghuaAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Latest published international intake"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 220,
        minimum_expected_schools: int = 30,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.minimum_expected_schools = minimum_expected_schools

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        catalog_year, catalog_id, detail_url = _latest_catalog(
            fetcher(self.catalog_url)
        )
        school_codes = _school_codes(fetcher(detail_url))
        if len(school_codes) < self.minimum_expected_schools:
            raise ValueError(
                "Tsinghua official master's catalogue only listed "
                f"{len(school_codes)} schools/departments; expected at least "
                f"{self.minimum_expected_schools}"
            )

        programmes = []
        for school_code in school_codes:
            payload = _catalog_payload(
                fetcher(catalog_query_url(catalog_id, school_code))
            )
            if str(payload.get("zsnd")) != str(catalog_year):
                raise ValueError(
                    "Tsinghua catalogue query returned an unexpected intake year"
                )
            for school in payload.get("zsmlYxs") or []:
                programmes.extend(
                    _school_programmes(
                        school,
                        catalog_year=catalog_year,
                        detail_url=detail_url,
                    )
                )

        programmes_by_id = {programme.id: programme for programme in programmes}
        programmes = sorted(programmes_by_id.values(), key=lambda item: item.name)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Tsinghua official international master's catalogue only contained "
                f"{len(programmes)} unique programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def catalog_query_url(catalog_id: str, school_code: str) -> str:
    params = {
        "gjz": "",
        "xxbm": catalog_id,
        "zslx": "1",
        "zsyx": "",
        "xxfs": "",
        "hysp": "",
        "yysp": "",
        "sfkfzs": "",
        "sfqywxm": "",
        "sflslpxm": "",
        "sfzsbkzb": "",
        "yxsdm": school_code,
        "showUsage": "false",
    }
    return f"{QUERY_ENDPOINT}?{urlencode(params)}"


def _latest_catalog(landing_html: str) -> tuple[int, str, str]:
    soup = BeautifulSoup(landing_html, "html.parser")
    candidates = []
    for link in soup.select("a[href]"):
        label = _normalise(link.get_text(" ", strip=True))
        if "master" not in label.lower() or "catalog" not in label.lower():
            continue
        match = re.search(r"\b(20\d{2})\b", label)
        if match is None:
            continue
        detail_url = urljoin(CATALOG_URL, link["href"])
        path_parts = urlparse(detail_url).path.rstrip("/").split("/")
        if len(path_parts) < 2 or path_parts[-2] == "detail":
            continue
        candidates.append((int(match.group(1)), path_parts[-2], detail_url))
    if not candidates:
        raise ValueError("Tsinghua master's catalogue landing page had no catalogues")
    return max(candidates, key=lambda item: item[0])


def _school_codes(detail_html: str) -> list[str]:
    soup = BeautifulSoup(detail_html, "html.parser")
    return list(
        dict.fromkeys(
            code
            for item in soup.select("#zsyx li[data-value]")
            if (code := _normalise(item.get("data-value")))
        )
    )


def _catalog_payload(value: str) -> dict:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("Tsinghua catalogue endpoint did not return JSON") from exc
    data = payload.get("datas") if isinstance(payload, dict) else None
    if payload.get("code") != 200 or not isinstance(data, dict):
        raise ValueError("Tsinghua catalogue endpoint returned an invalid payload")
    return data


def _school_programmes(
    school: dict,
    *,
    catalog_year: int,
    detail_url: str,
) -> list[DiscoveredProgramme]:
    school_code = _normalise(school.get("zsyxsdm"))
    school_name = _normalise(school.get("zsyxsywmc"))
    programmes = []
    for major in school.get("exportZsmlYxZys") or []:
        major_code = _normalise(major.get("zszydm"))
        for field in major.get("exportZsmlYxZyYjfxs") or []:
            field_code = _normalise(field.get("yjfxdm"))
            name = _programme_name(field)
            programme_id = (
                ADVANCED_COMPUTING_ID
                if "advanced computing" in name.lower()
                else f"tsinghua-{school_code}-{major_code}-{field_code}-master"
            )
            source_url = (
                ADVANCED_COMPUTING_SOURCE_URL
                if programme_id == ADVANCED_COMPUTING_ID
                else detail_url
            )
            windows = _windows(
                field,
                catalog_year,
                detail_url,
                advanced_computing=programme_id == ADVANCED_COMPUTING_ID,
            )
            programmes.append(
                DiscoveredProgramme(
                    id=programme_id,
                    name=name,
                    degree_type="Master",
                    faculty=school_name,
                    department="",
                    source_url=source_url,
                    application_url=APPLICATION_URL,
                    windows=windows,
                    deadline_text=_deadline_evidence(windows, catalog_year),
                    parse_status=(
                        "parsed"
                        if windows and all(window.opens_at for window in windows)
                        else "incomplete"
                    ),
                    retrieval_method="official-api",
                    evidence_quality="official-full-text",
                )
            )
    return programmes


def _programme_name(field: dict) -> str:
    name = _normalise(field.get("yjfxywmc"))
    if "advanced computing" in name.lower():
        return "Master's Program in Advanced Computing"
    if name.startswith("Mater of Architecture"):
        return name.replace("Mater of Architecture", "Master of Architecture", 1)
    mode = _normalise(field.get("xxfsywmc"))
    if mode == "Part-time" and "part-time" not in name.lower():
        return f"{name} (Part-time)"
    return name


def _windows(
    field: dict,
    catalog_year: int,
    source_url: str,
    *,
    advanced_computing: bool = False,
) -> list[DiscoveredWindow]:
    schedule = _normalise(field.get("bmsjms"))
    events: list[tuple[int, str | None, str]] = []
    for match in _NOW_DEADLINE.finditer(schedule):
        events.append((match.start(), None, _date_from_match(match, "")))
    for match in _FULL_RANGE.finditer(schedule):
        events.append(
            (
                match.start(),
                _date_from_match(match, "s"),
                _date_from_match(match, "e"),
            )
        )
    events.sort(key=lambda item: item[0])

    final_deadline = _deadline(field)
    if not events:
        events.append((0, None, final_deadline))
    elif final_deadline not in {event[2] for event in events}:
        events.append((len(schedule) + 1, None, final_deadline))

    def round_label(index: int) -> str:
        if len(events) == 1:
            return "Main deadline"
        if advanced_computing and index == 1:
            return "First application round"
        if advanced_computing and index == 2:
            return "Second application round"
        return f"Round {index}"

    return [
        DiscoveredWindow(
            round=round_label(index),
            intake=f"Autumn {catalog_year}",
            opens_at=opens_at,
            closes_at=closes_at,
            applicant_categories=["international-students"],
            source_url=source_url,
        )
        for index, (_, opens_at, closes_at) in enumerate(events, start=1)
    ]


def _deadline(field: dict) -> str:
    value = _normalise(field.get("bmjssjyw") or field.get("bmjssjzw"))
    match = _FINAL_DEADLINE.search(value)
    if match is None:
        raise ValueError("Tsinghua catalogue record had no exact final deadline")
    return match.group(0)


def _date_from_match(match: re.Match[str], prefix: str) -> str:
    return date(
        int(match.group(f"{prefix}y")),
        int(match.group(f"{prefix}m")),
        int(match.group(f"{prefix}d")),
    ).isoformat()


def _deadline_evidence(windows: list[DiscoveredWindow], catalog_year: int) -> str:
    periods = []
    for window in windows:
        if window.opens_at:
            periods.append(f"{window.round}: {window.opens_at} to {window.closes_at}")
        else:
            periods.append(
                f"{window.round}: closes {window.closes_at}; exact opening date "
                "not stated"
            )
    return (
        f"Tsinghua's official international master's catalogue for {catalog_year} "
        f"states: {'; '.join(periods)}. Missing opening dates are not inferred."
    )


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()
