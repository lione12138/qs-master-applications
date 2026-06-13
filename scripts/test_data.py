#!/usr/bin/env python3
"""Compatibility wrapper for `gradwindow validate`."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gradwindow.validation import validate_data


def main() -> int:
    errors, summary = validate_data()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"Validated {summary['universities']} universities, "
        f"{summary['admissionsCandidates']} admissions candidates "
        f"({summary['curatedAdmissions']} curated), and "
        f"{summary['verifiedWindows']} verified windows with "
        f"{summary['enabledParsers']} enabled parsers."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
