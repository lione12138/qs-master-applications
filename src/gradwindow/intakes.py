from __future__ import annotations

import re
from pathlib import Path

from .io import read_json, write_json
from .paths import APPLICATIONS_PATH

TERM_ALIASES = {
    "autumn": "fall",
    "fall": "fall",
    "september": "fall",
    "michaelmas": "michaelmas",
    "spring": "spring",
    "summer": "summer",
    "winter": "winter",
}
TERM_START_MONTHS = {
    "fall": 9,
    "michaelmas": 10,
    "spring": 1,
    "summer": 6,
    "winter": 1,
}


def parse_intake_details(label: str) -> dict:
    year_match = re.search(
        r"\b(20\d{2})(?:([/-])(\d{2}|20\d{2}))?\b",
        label,
    )
    if not year_match:
        raise ValueError(f"intake has no supported cycle year: {label}")
    cycle_year = int(year_match.group(1))
    second = year_match.group(3)
    academic_year_end = None
    if second:
        academic_year_end = (
            int(second)
            if len(second) == 4
            else (cycle_year // 100) * 100 + int(second)
        )

    lowered = label.lower()
    term = next(
        (
            canonical
            for token, canonical in TERM_ALIASES.items()
            if re.search(rf"\b{re.escape(token)}\b", lowered)
        ),
        "other",
    )
    month_match = re.search(
        r"\b(january|february|march|april|may|june|july|august|"
        r"september|october|november|december)\b",
        lowered,
    )
    month_names = {
        name: index
        for index, name in enumerate(
            (
                "january",
                "february",
                "march",
                "april",
                "may",
                "june",
                "july",
                "august",
                "september",
                "october",
                "november",
                "december",
            ),
            start=1,
        )
    }
    start_month = (
        month_names[month_match.group(1)]
        if month_match
        else TERM_START_MONTHS.get(term)
    )
    return {
        "label": label,
        "cycleYear": cycle_year,
        "academicYearEnd": academic_year_end,
        "term": term,
        "startMonth": start_month,
    }


def intake_identity(item: dict) -> tuple[int, int | None, str, int | None]:
    details = item.get("intakeDetails") or parse_intake_details(item["intake"])
    return (
        details["cycleYear"],
        details.get("academicYearEnd"),
        details["term"],
        details.get("startMonth"),
    )


def with_intake_details(item: dict) -> dict:
    return {
        **item,
        "intakeDetails": parse_intake_details(item["intake"]),
    }


def migrate_application_intakes(
    applications_path: Path = APPLICATIONS_PATH,
) -> dict:
    payload = read_json(applications_path)
    payload["applications"] = [
        with_intake_details(item) for item in payload["applications"]
    ]
    write_json(applications_path, payload)
    return payload
