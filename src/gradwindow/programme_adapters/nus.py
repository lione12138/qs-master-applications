from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .base import DiscoveredCatalog, DiscoveredProgramme, DiscoveredWindow

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
CDE_DEADLINES_URL = (
    "https://cde.nus.edu.sg/graduate/graduate-programmes-by-coursework/"
    "application-period/"
)
FASS_DEADLINES_URL = (
    "https://fass.nus.edu.sg/graduate/coursework-programmes/"
    "information-on-application-to-graduate-coursework-programmes/"
)
SCIENCE_RESEARCH_DEADLINES_URL = (
    "https://www.science.nus.edu.sg/graduates/msc-by-research/application-information/"
)
MEDICINE_RESEARCH_DEADLINES_URL = (
    "https://medicine.nus.edu.sg/graduatestudies/application-procedures/"
)
LAW_DEADLINES_URL = "https://law1a.nus.edu.sg/admissions/app_periods_forms.html"
COMPUTING_DEADLINES_URL = "https://www.comp.nus.edu.sg/programmes/pg/misc/application/"
PUBLIC_HEALTH_MPH_URL = "https://sph.nus.edu.sg/education/mph/"
DSML_DEADLINES_URL = (
    "https://www.math.nus.edu.sg/cdsml/ms-dsml/dsml-prospective-students/"
)
GLOBAL_SOCIOLOGY_DEADLINES_URL = (
    "https://fass.nus.edu.sg/socanth/graduate-coursework-programme-"
    "master-of-arts-global-sociology-and-anthropology/"
)
BIOMEDICAL_INFORMATICS_DEADLINES_URL = (
    "https://medicine.nus.edu.sg/dbmi/education-3/"
    "msc-in-biomedical-informatics-coursework/"
)
PUBLIC_POLICY_DEADLINES_URL = (
    "https://lkyspp.nus.edu.sg/graduate-admissions/admission-guide/how-to-apply"
)
READER_PREFIX = "https://r.jina.ai/http://"
DATE_RANGE_RE = re.compile(
    r"(?P<opens>\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]{2}\s+20\d{2})\s*"
    r"-\s*(?P<closes>\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]{2}\s+20\d{2})"
)
DAY_MONTH_RE = re.compile(
    r"^(?P<day>\d{1,2})\s+"
    r"(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)$",
    re.I,
)


@dataclass(frozen=True, slots=True)
class DeadlineRule:
    windows: tuple[DiscoveredWindow, ...]
    excerpt: str
    retrieval_method: str
    complete: bool


class NUSAdapter:
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    application_opens_at_basis = "missing"
    intake = "Varies by programme"

    def __init__(
        self,
        minimum_expected_programmes: int = 150,
        *,
        target_intake_year: int | None = None,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.target_intake_year = target_intake_year or _target_intake_year(
            date.today()
        )

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
        programmes = _apply_deadline_sources(
            programmes,
            fetcher,
            target_intake_year=self.target_intake_year,
        )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _apply_deadline_sources(
    programmes: list[DiscoveredProgramme],
    fetcher: Callable[[str], str],
    *,
    target_intake_year: int,
) -> list[DiscoveredProgramme]:
    cde_text, cde_method = _load_official_text(fetcher, CDE_DEADLINES_URL)
    fass_text, fass_method = _load_official_text(fetcher, FASS_DEADLINES_URL)
    science_text, science_method = _load_official_text(
        fetcher, SCIENCE_RESEARCH_DEADLINES_URL
    )
    medicine_text, medicine_method = _load_official_text(
        fetcher, MEDICINE_RESEARCH_DEADLINES_URL
    )
    law_text, law_method = _load_official_text(fetcher, LAW_DEADLINES_URL)
    computing_text, computing_method = _load_official_text(
        fetcher, COMPUTING_DEADLINES_URL
    )
    mph_text, mph_method = _load_official_text(fetcher, PUBLIC_HEALTH_MPH_URL)
    dsml_text, dsml_method = _load_official_text(fetcher, DSML_DEADLINES_URL)
    global_sociology_text, global_sociology_method = _load_official_text(
        fetcher, GLOBAL_SOCIOLOGY_DEADLINES_URL
    )
    biomedical_informatics_text, biomedical_informatics_method = _load_official_text(
        fetcher, BIOMEDICAL_INFORMATICS_DEADLINES_URL
    )
    public_policy_text, public_policy_method = _load_official_text(
        fetcher, PUBLIC_POLICY_DEADLINES_URL
    )
    cde_rules = _parse_cde_rules(cde_text, cde_method)
    fass_rules = _parse_fass_rules(fass_text, fass_method, target_intake_year)
    science_rule = _parse_science_research_rule(
        science_text, science_method, target_intake_year
    )
    medicine_rule = _parse_medicine_research_rule(
        medicine_text, medicine_method, target_intake_year
    )
    law_rule = _parse_law_rule(law_text, law_method)
    computing_rule = _parse_computing_rule(computing_text, computing_method)
    mph_rule = _parse_mph_rule(mph_text, mph_method)
    named_rules = {
        _canonical_title("MSc (Data Science and Machine Learning)"): _parse_dsml_rule(
            dsml_text, dsml_method
        ),
        _canonical_title("MA (Global Sociology and Anthropology)"): (
            _parse_global_sociology_rule(global_sociology_text, global_sociology_method)
        ),
        _canonical_title("MSc (Biomedical Informatics)"): (
            _parse_biomedical_informatics_rule(
                biomedical_informatics_text, biomedical_informatics_method
            )
        ),
    }
    named_rules.update(
        _parse_public_policy_rules(
            public_policy_text,
            public_policy_method,
            target_intake_year,
        )
    )

    enriched = []
    for programme in programmes:
        rule = None
        if programme.id.endswith("-coursework"):
            key = _canonical_title(programme.name)
            rule = named_rules.get(key) or cde_rules.get(key) or fass_rules.get(key)
            if rule is None and programme.faculty == "LAW":
                rule = law_rule
            if rule is None and programme.name.startswith("Master of Computing"):
                rule = computing_rule
            if rule is None and programme.name == "Master of Public Health":
                rule = mph_rule
        elif programme.id.endswith("-research") and programme.faculty == "SCIENCE":
            rule = science_rule
        elif programme.id.endswith("-research") and programme.faculty == "MEDICINE":
            rule = medicine_rule
        if rule is None:
            enriched.append(programme)
            continue
        enriched.append(
            replace(
                programme,
                windows=list(rule.windows),
                deadline_text=rule.excerpt,
                parse_status="parsed" if rule.complete else "incomplete",
                retrieval_method=rule.retrieval_method,
                evidence_quality="official-full-text",
            )
        )
    return enriched


def _load_official_text(
    fetcher: Callable[[str], str], source_url: str
) -> tuple[str, str]:
    try:
        direct = fetcher(source_url)
    except Exception:
        direct = ""
    if direct and not _is_access_challenge(direct):
        return _document_text(direct), "official-page"
    try:
        proxied = fetcher(_reader_url(source_url))
    except Exception:
        return "", "unavailable"
    return proxied, "official-page-via-reader"


def _reader_url(source_url: str) -> str:
    return READER_PREFIX + re.sub(r"^https?://", "", source_url)


def _is_access_challenge(value: str) -> bool:
    lowered = value.lower()
    return "_incapsula_resource" in lowered or "request unsuccessful" in lowered


def _document_text(value: str) -> str:
    if "<html" not in value[:500].lower():
        return value
    return BeautifulSoup(value, "html.parser").get_text("\n", strip=True)


def _parse_cde_rules(text: str, retrieval_method: str) -> dict[str, DeadlineRule]:
    header = re.search(
        r"August\s+(?P<august>20\d{2})\s+intake.*?"
        r"January\s+(?P<january>20\d{2})\s+intake",
        text,
        re.I | re.S,
    )
    if header is None:
        return {}
    intake_labels = (
        f"August {header.group('august')}",
        f"January {header.group('january')}",
    )
    rules = {}
    for raw_line in text.splitlines():
        line = _text(raw_line)
        title_match = re.match(r"^\[(?P<title>[^]]*Master[^]]*)\]\([^)]+\)", line, re.I)
        if title_match is None:
            continue
        ranges = list(DATE_RANGE_RE.finditer(line))
        if not ranges:
            continue
        windows = []
        for index, match in enumerate(ranges[:2]):
            windows.append(
                DiscoveredWindow(
                    round="Main",
                    opens_at=_short_date(match.group("opens")),
                    closes_at=_short_date(match.group("closes")),
                    intake=intake_labels[index],
                    source_url=CDE_DEADLINES_URL,
                )
            )
        title = re.sub(r"\^$", "", title_match.group("title")).strip()
        rules[_canonical_title(title)] = DeadlineRule(
            windows=tuple(windows),
            excerpt=line,
            retrieval_method=retrieval_method,
            complete=True,
        )
    return rules


def _parse_fass_rules(
    text: str,
    retrieval_method: str,
    target_intake_year: int,
) -> dict[str, DeadlineRule]:
    start = text.find("APPLICATION CLOSING DATES")
    end = text.find("Applicants who had submitted", start)
    if start < 0:
        return {}
    section = text[start : end if end > start else len(text)]
    intake = ""
    deadline = ""
    rules: dict[str, list[DiscoveredWindow]] = {}
    for raw_line in section.splitlines():
        line = _text(raw_line)
        if not line:
            continue
        combined = re.match(r"^\((August|January)\)(\d{1,2}\s+[A-Za-z]+)$", line)
        if combined:
            intake, deadline = combined.groups()
            continue
        if line == "Semester I":
            intake = "August"
            continue
        if line == "Semester II":
            intake = "January"
            continue
        if DAY_MONTH_RE.match(line):
            deadline = line
            continue
        line = re.sub(r"^\(in the [^)]+\)", "", line, flags=re.I).strip()
        if not line.startswith("Master") or not intake or not deadline:
            continue
        closes_at = _relative_deadline(deadline, intake, target_intake_year)
        rules.setdefault(_canonical_title(line), []).append(
            DiscoveredWindow(
                round="Main deadline",
                opens_at=None,
                closes_at=closes_at,
                intake=f"{intake} {target_intake_year}",
                source_url=FASS_DEADLINES_URL,
            )
        )
    return {
        key: DeadlineRule(
            windows=tuple(windows),
            excerpt=(
                "The official FASS coursework admissions table publishes the "
                "application closing date, but not an exact opening date."
            ),
            retrieval_method=retrieval_method,
            complete=False,
        )
        for key, windows in rules.items()
    }


def _parse_science_research_rule(
    text: str, retrieval_method: str, target_intake_year: int
) -> DeadlineRule | None:
    if not re.search(
        r"15\s+November.*August intake", text, re.I | re.S
    ) or not re.search(r"15\s+May.*January intake", text, re.I | re.S):
        return None
    return DeadlineRule(
        windows=(
            _closing_only_window(
                "August", target_intake_year, 11, 15, SCIENCE_RESEARCH_DEADLINES_URL
            ),
            _closing_only_window(
                "January", target_intake_year, 5, 15, SCIENCE_RESEARCH_DEADLINES_URL
            ),
        ),
        excerpt=(
            "NUS Faculty of Science lists 15 November for the following August "
            "intake and 15 May for the following January intake; no exact "
            "opening date is published."
        ),
        retrieval_method=retrieval_method,
        complete=False,
    )


def _parse_medicine_research_rule(
    text: str, retrieval_method: str, target_intake_year: int
) -> DeadlineRule | None:
    if not re.search(r"31\s+December.*full-time", text, re.I | re.S) or not re.search(
        r"30\s+June.*full-time", text, re.I | re.S
    ):
        return None
    return DeadlineRule(
        windows=(
            _closing_only_window(
                "August",
                target_intake_year,
                12,
                31,
                MEDICINE_RESEARCH_DEADLINES_URL,
                round_label="Full-time",
            ),
            _closing_only_window(
                "January",
                target_intake_year,
                6,
                30,
                MEDICINE_RESEARCH_DEADLINES_URL,
                round_label="Full-time",
            ),
        ),
        excerpt=(
            "NUS Medicine lists the full-time research deadlines as 31 December "
            "for the following August intake and 30 June for the following "
            "January intake; no exact opening date is published."
        ),
        retrieval_method=retrieval_method,
        complete=False,
    )


def _parse_law_rule(text: str, retrieval_method: str) -> DeadlineRule | None:
    text = re.sub(r"\s+", " ", text)
    intake_match = re.search(
        r"Online Application Period for August\s+(20\d{2})\s+intake", text, re.I
    )
    if intake_match is None or not re.search(r"All\s+LLM\s+Coursework", text, re.I):
        return None
    match = re.search(
        r"1\s+September\s*(?:-|–|to)\s*15\s+October\s+(20\d{2})", text, re.I
    )
    if match is None:
        return None
    year = int(match.group(1))
    window = DiscoveredWindow(
        round="Main",
        opens_at=date(year, 9, 1).isoformat(),
        closes_at=date(year, 10, 15).isoformat(),
        intake=f"August {intake_match.group(1)}",
        source_url=LAW_DEADLINES_URL,
    )
    return DeadlineRule(
        windows=(window,),
        excerpt=(
            "NUS Law's official application table lists the online application "
            f"period for the {window.intake} LLM coursework intake as "
            "1 September to 15 October."
        ),
        retrieval_method=retrieval_method,
        complete=True,
    )


def _parse_computing_rule(text: str, retrieval_method: str) -> DeadlineRule | None:
    match = re.search(
        r"August intake\s*\|?\s*1\s+October\s+(20\d{2})\s*\|?\s*"
        r"31\s+January\s+(20\d{2})",
        text,
        re.I,
    )
    if match is None:
        return None
    open_year, close_year = map(int, match.groups())
    window = DiscoveredWindow(
        round="Main",
        opens_at=date(open_year, 10, 1).isoformat(),
        closes_at=date(close_year, 1, 31).isoformat(),
        intake=f"August {close_year}",
        source_url=COMPUTING_DEADLINES_URL,
    )
    return DeadlineRule(
        windows=(window,),
        excerpt=(
            "NUS Computing's official application table lists the Master of "
            f"Computing {window.intake} application period as 1 October "
            "to 31 January."
        ),
        retrieval_method=retrieval_method,
        complete=True,
    )


def _parse_mph_rule(text: str, retrieval_method: str) -> DeadlineRule | None:
    section = re.search(
        r"Applications are open from\s+"
        r"(?P<opens>\d{1,2}\s+[A-Z][a-z]{2}\s+20\d{2})\s+to\s+"
        r"(?P<closes>\d{1,2}\s+[A-Z][a-z]{2}\s+20\d{2})",
        text,
        re.I,
    )
    if section is None:
        return None
    opens_at = _short_date(section.group("opens"))
    closes_at = _short_date(section.group("closes"))
    intake_year = int(opens_at[:4]) + 1
    return DeadlineRule(
        windows=(
            DiscoveredWindow(
                round="Main",
                opens_at=opens_at,
                closes_at=closes_at,
                intake=f"August {intake_year}",
                source_url=PUBLIC_HEALTH_MPH_URL,
            ),
        ),
        excerpt=(
            "The official NUS Master of Public Health page lists applications "
            f"as open from {opens_at} to {closes_at}."
        ),
        retrieval_method=retrieval_method,
        complete=True,
    )


def _parse_dsml_rule(text: str, retrieval_method: str) -> DeadlineRule | None:
    intake_match = re.search(r"August\s+(20\d{2})", text, re.I)
    early = re.search(
        r"16\s+May\s+(20\d{2})\s+to\s+15\s+July\s+(20\d{2})",
        text,
        re.I,
    )
    regular = re.search(
        r"1\s+October\s+(20\d{2})\s+to\s+31\s+January\s+(20\d{2})",
        text,
        re.I,
    )
    if intake_match is None or early is None or regular is None:
        return None
    intake = f"August {intake_match.group(1)}"
    windows = (
        DiscoveredWindow(
            round="Early admission",
            opens_at=date(int(early.group(1)), 5, 16).isoformat(),
            closes_at=date(int(early.group(2)), 7, 15).isoformat(),
            intake=intake,
            source_url=DSML_DEADLINES_URL,
        ),
        DiscoveredWindow(
            round="Regular admission",
            opens_at=date(int(regular.group(1)), 10, 1).isoformat(),
            closes_at=date(int(regular.group(2)), 1, 31).isoformat(),
            intake=intake,
            source_url=DSML_DEADLINES_URL,
        ),
    )
    return DeadlineRule(
        windows=windows,
        excerpt=(
            f"The official NUS DSML page publishes early and regular "
            f"application periods for the {intake} intake."
        ),
        retrieval_method=retrieval_method,
        complete=True,
    )


def _parse_global_sociology_rule(
    text: str, retrieval_method: str
) -> DeadlineRule | None:
    match = re.search(
        r"August\s+(20\d{2})\s+1\s+September\s+(20\d{2})\s+"
        r"30\s+November\s+(20\d{2})",
        text,
        re.I,
    )
    if match is None:
        return None
    intake_year, open_year, close_year = map(int, match.groups())
    return _single_exact_rule(
        source_url=GLOBAL_SOCIOLOGY_DEADLINES_URL,
        retrieval_method=retrieval_method,
        intake=f"August {intake_year}",
        opens_at=date(open_year, 9, 1),
        closes_at=date(close_year, 11, 30),
        excerpt=(
            "The official FASS programme page publishes the complete application "
            f"period for the August {intake_year} intake."
        ),
    )


def _parse_biomedical_informatics_rule(
    text: str, retrieval_method: str
) -> DeadlineRule | None:
    match = re.search(
        r"August\s+(20\d{2}).{0,300}?1\s+October\s+(20\d{2})\s*"
        r"(?:-|–|to)\s*2\s+February\s+(20\d{2})",
        text,
        re.I | re.S,
    )
    if match is None:
        return None
    intake_year, open_year, close_year = map(int, match.groups())
    return _single_exact_rule(
        source_url=BIOMEDICAL_INFORMATICS_DEADLINES_URL,
        retrieval_method=retrieval_method,
        intake=f"August {intake_year}",
        opens_at=date(open_year, 10, 1),
        closes_at=date(close_year, 2, 2),
        excerpt=(
            "The official NUS Biomedical Informatics page publishes the complete "
            f"application period for the August {intake_year} intake."
        ),
    )


def _parse_public_policy_rules(
    text: str,
    retrieval_method: str,
    target_intake_year: int,
) -> dict[str, DeadlineRule]:
    text = re.sub(r"\s+", " ", text)
    programmes = (
        ("Master in Public Policy", r"Master in Public Policy \(MPP\)", 12, 15),
        (
            "Master in International Affairs",
            r"Master in International Affairs \(MIA\)",
            12,
            15,
        ),
        (
            "Master in Public Administration",
            r"Master in Public Administration \(MPA\)",
            12,
            31,
        ),
    )
    rules = {}
    for title, label_pattern, close_month, close_day in programmes:
        pattern = (
            label_pattern
            + r"\s*:\s*1 August\s*(?:-|–|to)\s*"
            + str(close_day)
            + r"\s+"
            + ("December" if close_month == 12 else "January")
            + r"\s+every year"
        )
        if re.search(pattern, text, re.I) is None:
            continue
        rules[_canonical_title(title)] = _single_exact_rule(
            source_url=PUBLIC_POLICY_DEADLINES_URL,
            retrieval_method=retrieval_method,
            intake=f"August {target_intake_year}",
            opens_at=date(target_intake_year - 1, 8, 1),
            closes_at=date(target_intake_year - 1, close_month, close_day),
            excerpt=(
                f"The official LKYSPP application guide states that {title} "
                f"applications run from 1 August to {close_day} December every year."
            ),
        )
    return rules


def _single_exact_rule(
    *,
    source_url: str,
    retrieval_method: str,
    intake: str,
    opens_at: date,
    closes_at: date,
    excerpt: str,
) -> DeadlineRule:
    return DeadlineRule(
        windows=(
            DiscoveredWindow(
                round="Main",
                opens_at=opens_at.isoformat(),
                closes_at=closes_at.isoformat(),
                intake=intake,
                source_url=source_url,
            ),
        ),
        excerpt=excerpt,
        retrieval_method=retrieval_method,
        complete=True,
    )


def _closing_only_window(
    intake_month: str,
    intake_year: int,
    close_month: int,
    close_day: int,
    source_url: str,
    *,
    round_label: str = "Main deadline",
) -> DiscoveredWindow:
    return DiscoveredWindow(
        round=round_label,
        opens_at=None,
        closes_at=date(intake_year - 1, close_month, close_day).isoformat(),
        intake=f"{intake_month} {intake_year}",
        source_url=source_url,
    )


def _relative_deadline(value: str, intake: str, intake_year: int) -> str:
    match = DAY_MONTH_RE.match(value)
    if match is None:
        raise ValueError(f"Unsupported NUS deadline: {value}")
    month = datetime.strptime(match.group("month"), "%B").month
    year = intake_year - 1 if intake == "January" or month >= 11 else intake_year
    return date(year, month, int(match.group("day"))).isoformat()


def _short_date(value: str) -> str:
    value = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", value)
    return datetime.strptime(value, "%d %b %Y").date().isoformat()


def _target_intake_year(today: date) -> int:
    return today.year + (today > date(today.year, 3, 31))


def _canonical_title(value: str) -> str:
    value = value.lower().replace("&", " and ")
    replacements = (
        (r"^msc\b", "master science"),
        (r"^ma\b", "master arts"),
        (r"^meng\b", "master engineering"),
        (r"^msocsc\b", "master social sciences"),
        (r"^masters?\s+of\s+science\b", "master science"),
        (r"^masters?\s+of\s+arts\b", "master arts"),
        (r"^masters?\s+of\s+engineering\b", "master engineering"),
        (r"^masters?\s+of\s+social\s+sciences\b", "master social sciences"),
        (r"^masters?\s+of\b", "master"),
    )
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value)
    value = re.sub(r"\bby research\b", "", value)
    value = re.sub(r"\b(?:of|in)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


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
