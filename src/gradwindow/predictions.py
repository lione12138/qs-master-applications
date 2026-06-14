from __future__ import annotations

from calendar import monthrange
from datetime import date
from pathlib import Path
import re

from .intakes import intake_identity, parse_intake_details
from .io import read_json, write_json
from .paths import APPLICATIONS_PATH, PREDICTIONS_PATH

PREDICTION_METHOD = "calendar-date-shift-plus-one-year"
PREDICTION_DISCLAIMER = (
    "This is a non-official calendar-shift reference: the prior verified "
    "dates are moved forward exactly one calendar year. It is not a forecast "
    "of the university's actual dates; weekdays and policies may change."
)
def shift_date_one_year(value: str) -> str:
    original = date.fromisoformat(value)
    day = min(original.day, monthrange(original.year + 1, original.month)[1])
    return original.replace(year=original.year + 1, day=day).isoformat()


def shift_intake_one_year(value: str) -> str:
    def replace_year(match: re.Match[str]) -> str:
        first = int(match.group(1)) + 1
        separator = match.group(2)
        second = match.group(3)
        if not separator or not second:
            return str(first)
        shifted_second = int(second) + 1
        if len(second) == 2:
            return f"{first}{separator}{shifted_second % 100:02d}"
        return f"{first}{separator}{shifted_second}"

    return re.sub(r"\b(20\d{2})(?:([/-])(\d{2}|20\d{2}))?\b", replace_year, value)


def canonical_intake_key(value: str) -> tuple[tuple[int, ...], str]:
    details = parse_intake_details(value)
    return (
        tuple(
            year
            for year in (
                details["cycleYear"],
                details.get("academicYearEnd"),
            )
            if year is not None
        ),
        f"{details['term']}:{details.get('startMonth')}",
    )


def window_signature(item: dict) -> tuple:
    return (
        item["universityId"],
        item["scopeType"],
        item["scopeId"],
        item.get("round", ""),
        tuple(sorted(item.get("applicantCategories", []))),
    )


def official_cycle_key(item: dict) -> tuple:
    return (*window_signature(item), intake_identity(item))


def prediction_confidence(history: list[dict]) -> tuple[str, str]:
    if len(history) < 2:
        return "low", "Only one verified historical cycle is available."
    ordered = sorted(history, key=lambda item: (item["closesAt"], item["id"]))
    stable_pairs = 0
    for previous, current in zip(ordered, ordered[1:]):
        if (
            shift_date_one_year(previous["opensAt"]) == current["opensAt"]
            and shift_date_one_year(previous["closesAt"]) == current["closesAt"]
            and canonical_intake_key(shift_intake_one_year(previous["intake"]))
            == canonical_intake_key(current["intake"])
        ):
            stable_pairs += 1
    if stable_pairs != len(ordered) - 1:
        return "low", "Available historical cycles did not repeat exactly."
    if len(ordered) >= 3:
        return "high", "At least three verified cycles repeated exactly."
    return "medium", "Two verified cycles repeated exactly."


def generate_predictions(
    output_path: Path = PREDICTIONS_PATH,
    applications_path: Path = APPLICATIONS_PATH,
) -> dict:
    payload = read_json(applications_path)
    applications = payload["applications"]
    latest_by_signature: dict[tuple, dict] = {}
    history_by_signature: dict[tuple, list[dict]] = {}
    for item in applications:
        signature = window_signature(item)
        history_by_signature.setdefault(signature, []).append(item)
        current = latest_by_signature.get(signature)
        if current is None or (
            item["closesAt"],
            item["verifiedAt"],
            item["id"],
        ) > (
            current["closesAt"],
            current["verifiedAt"],
            current["id"],
        ):
            latest_by_signature[signature] = item

    official_keys = {official_cycle_key(item) for item in applications}
    predictions = []
    generated_from = payload.get("meta", {}).get("updatedAt", "")
    for source in latest_by_signature.values():
        confidence, confidence_reason = prediction_confidence(
            history_by_signature[window_signature(source)]
        )
        target_intake = shift_intake_one_year(source["intake"])
        target_key = (*window_signature(source), target_intake)
        if target_key in official_keys:
            continue
        prediction = {
            "id": f"prediction-{source['id']}-next-cycle",
            "basedOnRecordId": source["id"],
            "universityId": source["universityId"],
            "scopeType": source["scopeType"],
            "scopeId": source["scopeId"],
            "intake": target_intake,
            "intakeDetails": parse_intake_details(target_intake),
            "round": source.get("round", ""),
            "applicantCategories": source["applicantCategories"],
            "opensAt": shift_date_one_year(source["opensAt"]),
            "closesAt": shift_date_one_year(source["closesAt"]),
            "applicationUrl": source["applicationUrl"],
            "sourceUrl": source["sourceUrl"],
            "sourceCycle": source["intake"],
            "basedOnVerifiedAt": source["verifiedAt"],
            "confidence": confidence,
            "confidenceReason": confidence_reason,
            "evidenceCycleCount": len(
                history_by_signature[window_signature(source)]
            ),
            "methodology": PREDICTION_METHOD,
            "disclaimer": PREDICTION_DISCLAIMER,
        }
        predictions.append(prediction)

    predictions.sort(
        key=lambda item: (
            item["universityId"],
            item["closesAt"],
            item["scopeId"],
            item["id"],
        )
    )
    result = {
        "meta": {
            "title": "Estimated next-cycle application windows",
            "generatedFromApplicationsUpdatedAt": generated_from,
            "official": False,
            "methodology": PREDICTION_METHOD,
            "disclaimer": PREDICTION_DISCLAIMER,
        },
        "predictions": predictions,
    }
    write_json(output_path, result)
    return result
