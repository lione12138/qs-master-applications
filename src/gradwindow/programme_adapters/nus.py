from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
from urllib.parse import urlencode

from .base import DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "national-university-of-singapore-nus"
CATALOG_URL = "https://study.nus.edu.sg/programme"
APPLICATION_URL = "https://gradapp.nus.edu.sg/portal/app_manage"
APEX_CLASS = "ShopFrontController"
APEX_METHOD = "searchProgrammesWithActionOrder"
API_URL = "https://study.nus.edu.sg/webruntime/api/apex/execute?" + urlencode(
    {
        "language": "en-US",
        "asGuest": "true",
        "htmlEncode": "false",
        "namespace": "",
        "classname": APEX_CLASS,
        "method": APEX_METHOD,
        "isContinuation": "false",
        "cacheable": "true",
    }
)


class NUSAdapter:
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    application_opens_at_basis = "missing"
    intake = "Varies by programme"

    def __init__(self, minimum_expected_programmes: int = 150) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        payload = _read_payload(fetcher(API_URL))
        programmes = [
            programme
            for item in payload
            if (programme := _programme_from_item(item)) is not None
        ]
        programmes = sorted(
            {programme.id: programme for programme in programmes}.values(),
            key=lambda item: item.id,
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "NUS official catalogue only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _read_payload(raw: str) -> list[dict]:
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not isinstance(
        payload.get("returnValue"), list
    ):
        raise ValueError("NUS catalogue API response did not contain returnValue")
    return [item for item in payload["returnValue"] if isinstance(item, dict)]


def _programme_from_item(item: dict) -> DiscoveredProgramme | None:
    programme = item.get("programme")
    if not isinstance(programme, dict):
        return None
    programme_type = _text(programme.get("Type__c"))
    if not programme_type.startswith("Master's by "):
        return None
    title = _text(programme.get("Title__c"))
    source_url = _text(programme.get("Program_Page_Link__c"))
    if not title or not source_url:
        return None
    track = "research" if programme_type.endswith("Research") else "coursework"
    faculty = _text(item.get("facultyDisplay")) or _text(
        programme.get("Faculty_Reference__c")
    )
    intake = _text(programme.get("Intake_Period__c")) or "not stated"
    mode = _text(programme.get("Mode_of_Study__c")) or "not stated"
    return DiscoveredProgramme(
        id=f"nus-{_slug(title)}-{track}",
        name=title,
        degree_type=_degree_type(title),
        faculty=faculty,
        department="",
        source_url=source_url,
        application_url=(_text(programme.get("Application_URL__c")) or APPLICATION_URL),
        windows=[],
        deadline_text=(
            "NUS's official postgraduate catalogue confirms this programme "
            f"({programme_type}; intake: {intake}; mode: {mode}), but does not "
            "publish an exact application opening and closing date."
        ),
        parse_status="no-deadline",
        retrieval_method="official-api",
        evidence_quality="official-full-text",
    )


def _degree_type(title: str) -> str:
    lowered = title.lower()
    if re.search(r"\b(?:llm|master of laws?)\b", lowered):
        return "LLM"
    if re.search(r"\b(?:mba|master of business administration)\b", lowered):
        return "MBA"
    if re.search(r"\b(?:mph|master of public health)\b", lowered):
        return "MPH"
    if re.search(r"\b(?:msc|master of science)\b", lowered):
        return "MSc"
    if re.search(r"\b(?:ma|master of arts)\b", lowered):
        return "MA"
    return "Master"


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
