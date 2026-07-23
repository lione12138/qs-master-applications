from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "shanghai-jiao-tong-university"
CATALOG_URL = "https://isc.sjtu.edu.cn/cn/content.aspx?flag=64&info_lb=101"
CHINESE_CATALOG_URL = (
    "https://isc.sjtu.edu.cn/kindeditor/Upload/file/20251024/20251024150559_3530.pdf"
)
ENGLISH_CATALOG_URL = (
    "https://isc.sjtu.edu.cn/kindeditor/Upload/file/20251024/20251024150616_0035.pdf"
)
APPLICATION_URL = "https://apply.sjtu.edu.cn/"

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_SCHOOL_RE = re.compile(r"^(?P<code>\d{3})(?:\s+(?P<rest>.*))?$")
_MAJOR_CODE_PATTERN = r"(?:0[1-9]|1[0-4])\d[0-9A-Z]{3}"
_MAJOR_RE = re.compile(rf"^(?P<code>{_MAJOR_CODE_PATTERN})(?:\s+(?P<rest>.*))?$")
_MAJOR_ANYWHERE_RE = re.compile(rf"(?<!\d)(?P<code>{_MAJOR_CODE_PATTERN})(?![A-Z0-9])")
_PAGE_RE = re.compile(r"^\d+\s*/\s*\d+$")
_STOP_LINE_RE = re.compile(
    r"^(?:Minhang|Xuhui|Zhangjiang|Qibao|Huangpu|Tel[:：]?|Email[:：]?|"
    r"\+?\d|\d+(?:\.\d+)?\s*years?|RMB|In total)",
    re.IGNORECASE,
)
_GUIDE_YEAR_RE = re.compile(
    r"上海交通大学\s*(?P<year>20\d{2})\s*年\s*国际研究生招生简章"
)
_INTAKE_YEAR_RE = re.compile(r"入学时间为\s*(?P<year>20\d{2})\s*年\s*9\s*月")
_CATALOG_YEAR_RE = re.compile(
    r"上海交通大学\s*(?P<year>20\d{2})\s*年国际硕士研究生招生"
)
_DATE_RE = (
    r"(?P<year>20\d{2})\s*年\s*(?P<month>\d{1,2})\s*月\s*"
    r"(?P<day>\d{1,2})\s*日"
)


@dataclass(slots=True)
class _CatalogueRow:
    school_code: str
    faculty: str
    major_code: str
    name: str
    variant: str | None = None


class SJTUAdapter(BaseProgrammeAdapter):
    """Discover SJTU's official international master's catalogues and windows."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Fall 2027"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_chinese_programmes: int = 55,
        minimum_expected_english_programmes: int = 57,
        target_intake_year: int = 2027,
    ) -> None:
        self.minimum_expected_chinese_programmes = minimum_expected_chinese_programmes
        self.minimum_expected_english_programmes = minimum_expected_english_programmes
        self.target_intake_year = target_intake_year
        self.intake = f"Fall {target_intake_year}"

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        guide_html = fetcher(CATALOG_URL)
        guide_year, windows = _guide_windows(
            guide_html,
            target_intake_year=self.target_intake_year,
        )
        catalogue_urls = _catalogue_urls(guide_html, expected_year=guide_year)
        rows_by_language = {
            language: _catalogue_rows(
                fetcher(source_url),
                expected_year=guide_year,
            )
            for language, source_url in catalogue_urls.items()
        }
        _require_catalogue_size(
            "Chinese-taught",
            rows_by_language["chinese"],
            self.minimum_expected_chinese_programmes,
        )
        _require_catalogue_size(
            "English-taught",
            rows_by_language["english"],
            self.minimum_expected_english_programmes,
        )
        _complete_wrapped_names(rows_by_language)

        programmes = []
        for language, rows in rows_by_language.items():
            source_url = catalogue_urls[language]
            programmes.extend(
                _programmes(
                    rows,
                    language=language,
                    source_url=source_url,
                    guide_year=guide_year,
                    target_intake_year=self.target_intake_year,
                    windows=windows,
                )
            )
        programmes.sort(key=lambda item: item.id)
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("SJTU catalogue generated duplicate programme IDs")
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _catalogue_urls(html: str, *, expected_year: int) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: dict[str, str] = {}
    for link in soup.select("a[href]"):
        title = _normalise(link.get_text(" ", strip=True))
        if "硕士留学生招生" not in title or "专业目录" not in title:
            continue
        if str(expected_year) not in title:
            continue
        language = None
        if "中文授课" in title:
            language = "chinese"
        elif "英文授课" in title:
            language = "english"
        if language is None:
            continue
        source_url = urljoin(CATALOG_URL, str(link.get("href", "")))
        if _is_official_pdf(source_url):
            urls[language] = source_url
    if set(urls) != {"chinese", "english"}:
        raise ValueError(
            "SJTU admissions guide did not link both current master's catalogues"
        )
    return urls


def _guide_windows(
    html: str,
    *,
    target_intake_year: int,
) -> tuple[int, list[DiscoveredWindow]]:
    text = _html_text(html)
    guide_match = _GUIDE_YEAR_RE.search(text)
    intake_match = _INTAKE_YEAR_RE.search(text)
    if guide_match is None or intake_match is None:
        raise ValueError("SJTU guide did not identify its international intake year")
    guide_year = int(guide_match.group("year"))
    if int(intake_match.group("year")) != guide_year:
        raise ValueError("SJTU guide and stated September intake years differ")

    opening = _date_before(text, r"开放报名")
    closing_rules = [
        (
            "Chinese Government Scholarship first round",
            ["international", "chinese-government-scholarship"],
            r"中国政府奖学金第一轮\s*申请截止",
        ),
        (
            "Chinese Government Scholarship",
            ["international", "chinese-government-scholarship"],
            r"中国政府奖学金(?!第一轮)\s*申请截止",
        ),
        (
            "Shanghai Government/SJTU Scholarship",
            ["international", "shanghai-or-sjtu-scholarship"],
            r"上海市政府奖学金、学校奖学金\s*申请截止",
        ),
        (
            "Self-funded",
            ["international", "self-funded"],
            r"自费生\s*申请截止",
        ),
    ]
    exact_windows = [
        DiscoveredWindow(
            round=round_name,
            applicant_categories=categories,
            opens_at=opening,
            closes_at=_date_before(text, label_pattern),
            intake=f"Fall {guide_year}",
            source_url=CATALOG_URL,
        )
        for round_name, categories, label_pattern in closing_rules
    ]
    if guide_year != target_intake_year:
        return guide_year, []
    return guide_year, exact_windows


def _date_before(text: str, label_pattern: str) -> str:
    match = re.search(rf"{_DATE_RE}\s*{label_pattern}", text)
    if match is None:
        raise ValueError(f"SJTU guide did not contain exact date for {label_pattern}")
    return date(
        int(match.group("year")),
        int(match.group("month")),
        int(match.group("day")),
    ).isoformat()


def _catalogue_rows(text: str, *, expected_year: int) -> list[_CatalogueRow]:
    header = _CATALOG_YEAR_RE.search(_normalise(text))
    if header is None or int(header.group("year")) != expected_year:
        raise ValueError("SJTU master's catalogue year did not match the guide")

    lines = _catalogue_lines(text)
    rows: list[_CatalogueRow] = []
    school_code = ""
    faculty = "Shanghai Jiao Tong University"
    faculty_lines: list[str] = []
    collecting_faculty = False
    index = 0
    while index < len(lines):
        line = lines[index]
        school_match = _SCHOOL_RE.fullmatch(line)
        if school_match:
            school_code = school_match.group("code")
            rest = school_match.group("rest")
            faculty_lines = [rest] if rest else []
            collecting_faculty = True
            index += 1
            continue

        major_match = _MAJOR_RE.fullmatch(line)
        if major_match:
            if collecting_faculty:
                parsed_faculty = _faculty_name(faculty_lines)
                if parsed_faculty:
                    faculty = parsed_faculty
                collecting_faculty = False
            block = [major_match.group("rest") or ""]
            next_index = index + 1
            while next_index < len(lines):
                next_line = lines[next_index]
                if _SCHOOL_RE.fullmatch(next_line) or _MAJOR_RE.fullmatch(next_line):
                    break
                block.append(next_line)
                next_index += 1
            name = _programme_name(block)
            if not school_code or not name:
                raise ValueError(
                    f"SJTU catalogue could not parse major {major_match.group('code')}"
                )
            rows.append(
                _CatalogueRow(
                    school_code=school_code,
                    faculty=faculty,
                    major_code=major_match.group("code"),
                    name=name,
                    variant=_programme_variant(block),
                )
            )
            index = next_index
            continue

        if collecting_faculty:
            faculty_lines.append(line)
        index += 1
    return rows


def _catalogue_lines(text: str) -> list[str]:
    separated = _MAJOR_ANYWHERE_RE.sub(
        lambda match: f"\n{match.group('code')} ",
        text,
    )
    return [_normalise(line) for line in separated.splitlines() if _normalise(line)]


def _faculty_name(lines: list[str]) -> str:
    parts = [_english_fragment(line)[0] for line in lines]
    value = _normalise(" ".join(part for part in parts if part))
    value = value.replace(
        "School of Integrated Circuits School of",
        "School of Integrated Circuits (School of",
    )
    if "Programs in French)" in value and "(Programs in French)" not in value:
        value = value.replace("Programs in French)", "(Programs in French)")
    return value


def _programme_name(lines: list[str]) -> str:
    parts: list[str] = []
    for line in lines:
        if not line or _PAGE_RE.fullmatch(line):
            continue
        if _STOP_LINE_RE.match(line):
            break
        fragment, followed_by_cjk = _english_fragment(line)
        if not parts:
            if not fragment:
                continue
            parts.append(fragment)
            if followed_by_cjk:
                break
            continue
        if _CJK_RE.search(line):
            break
        if fragment:
            parts.append(fragment)
        if followed_by_cjk:
            break
    return _normalise(" ".join(parts)).strip(" ;")


def _english_fragment(line: str) -> tuple[str, bool]:
    match = re.search(r"[A-Za-z]", line)
    if match is None:
        return "", False
    prefix = line[: match.start()]
    tail = line if not _CJK_RE.search(prefix) else line[match.start() :]
    following_cjk = _CJK_RE.search(tail)
    if following_cjk:
        tail = tail[: following_cjk.start()]
    tail = tail.replace("（", "(").replace("）", ")")
    tail = re.sub(r"^\(?MBA\)\s*(?=Master\b)", "", tail)
    return _normalise(tail).strip(" ;"), following_cjk is not None


def _programme_variant(lines: list[str]) -> str | None:
    text = _normalise(" ".join(lines))
    if "CLGO Program" in text:
        return "CLGO Full-time"
    if "Part-time" in text:
        return "Part-time"
    return None


def _complete_wrapped_names(
    rows_by_language: dict[str, list[_CatalogueRow]],
) -> None:
    all_rows = [row for rows in rows_by_language.values() for row in rows]
    by_code: dict[str, list[str]] = {}
    for row in all_rows:
        by_code.setdefault(row.major_code, []).append(row.name)
    for row in all_rows:
        if not (row.name.endswith(" and") or row.name in {"Resources", "Energy and"}):
            continue
        candidates = [
            name
            for name in by_code[row.major_code]
            if len(name) > len(row.name) and name.startswith(row.name)
        ]
        if candidates:
            row.name = max(candidates, key=len)


def _programmes(
    rows: list[_CatalogueRow],
    *,
    language: str,
    source_url: str,
    guide_year: int,
    target_intake_year: int,
    windows: list[DiscoveredWindow],
) -> list[DiscoveredProgramme]:
    identities = Counter((row.school_code, row.major_code, row.name) for row in rows)
    seen: Counter[tuple[str, str, str]] = Counter()
    programmes = []
    for row in rows:
        identity = (row.school_code, row.major_code, row.name)
        seen[identity] += 1
        variant = row.variant
        if identities[identity] > 1 and variant is None:
            variant = f"variant {seen[identity]}"
        existing_cs = (
            language == "english"
            and row.school_code == "033"
            and row.major_code == "081200"
        )
        if existing_cs:
            programme_id = "sjtu-computer-science-technology-master"
            programme_name = "Master in Computer Science and Technology"
        else:
            suffix = f"-{_slug(variant)}" if variant else ""
            programme_id = (
                f"sjtu-{_slug(row.name)}-{row.school_code}-"
                f"{row.major_code.lower()}-{language}{suffix}-master"
            )
            label = "Chinese-taught" if language == "chinese" else "English-taught"
            if variant:
                label = f"{label}, {variant}"
            base_name = (
                row.name
                if row.name.lower().startswith("master ")
                else f"Master in {row.name}"
            )
            programme_name = f"{base_name} ({label})"
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=programme_name,
                degree_type="Master",
                faculty=row.faculty,
                department=row.name,
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=list(windows),
                deadline_text=_deadline_text(
                    language=language,
                    guide_year=guide_year,
                    target_intake_year=target_intake_year,
                    has_target_windows=bool(windows),
                ),
                parse_status="parsed" if windows else "no-deadline",
                retrieval_method="official-international-master-pdf-and-admissions-guide",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _deadline_text(
    *,
    language: str,
    guide_year: int,
    target_intake_year: int,
    has_target_windows: bool,
) -> str:
    label = "Chinese-taught" if language == "chinese" else "English-taught"
    if has_target_windows:
        return (
            f"SJTU's official {guide_year} intake guide publishes four exact "
            f"international application routes for this {label} catalogue entry."
        )
    return (
        f"SJTU's official {guide_year} intake guide and {label} catalogue were "
        f"checked, but that cycle is stale for Fall {target_intake_year}; no exact "
        "target-cycle application window has been published."
    )


def _require_catalogue_size(
    label: str,
    rows: list[_CatalogueRow],
    minimum: int,
) -> None:
    if len(rows) < minimum:
        raise ValueError(
            f"SJTU official {label} catalogue only contained {len(rows)} master's "
            f"programmes; expected at least {minimum}"
        )


def _html_text(html: str) -> str:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    text = _normalise(text)
    return re.sub(r"(?<=\d)\s+(?=\d)", "", text)


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _slug(value: object) -> str:
    text = (
        unicodedata.normalize("NFKD", _normalise(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "programme"


def _is_official_pdf(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.lower().endswith("sjtu.edu.cn")
        and parsed.path.lower().endswith(".pdf")
    )
