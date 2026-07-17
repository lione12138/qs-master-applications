from gradwindow.candidate_review import (
    attach_programme_candidate_evidence_hash,
    programme_candidate_evidence_hash,
)
from gradwindow.programme_discovery import _merge_candidate_review_state


def _candidate() -> dict:
    return attach_programme_candidate_evidence_hash(
        {
            "id": "new-programme:example",
            "type": "new-programme",
            "status": "pending",
            "universityId": "example-university",
            "sourceUrl": "https://example.edu/programme",
            "programme": {"id": "example", "name": "Example"},
            "windows": [
                {
                    "opensAt": "2026-09-01",
                    "opensAtBasis": "official",
                    "closesAt": "2027-01-01",
                }
            ],
            "parseStatus": "parsed",
        }
    )


def test_evidence_hash_ignores_mutable_review_state() -> None:
    candidate = _candidate()
    evidence_hash = candidate["evidenceHash"]
    candidate["status"] = "approved"
    candidate["reviewedBy"] = "maintainer"
    candidate["reviewHistory"] = [{"evidenceHash": evidence_hash}]

    assert programme_candidate_evidence_hash(candidate) == evidence_hash


def test_changed_evidence_reopens_an_approved_candidate() -> None:
    previous = _candidate()
    previous["status"] = "approved"
    previous["reviewHistory"] = [{"evidenceHash": previous["evidenceHash"]}]
    current = _candidate()
    current["windows"][0]["closesAt"] = "2027-02-01"
    attach_programme_candidate_evidence_hash(current)

    _merge_candidate_review_state(
        current,
        previous,
        "2026-07-18T00:00:00+00:00",
    )

    assert current["status"] == "pending"
    assert current["evidenceChangedAt"] == "2026-07-18T00:00:00+00:00"
    assert current["reviewHistory"] == previous["reviewHistory"]
