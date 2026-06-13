#!/usr/bin/env python3
"""Compatibility wrapper for `gradwindow update-deadlines`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gradwindow.deadlines import update_deadlines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = update_deadlines(dry_run=args.dry_run)
    print(
        f"Checked {report['checked']} source(s); "
        f"changed {report['changed']}; "
        f"errors {sum(item['status'] == 'error' for item in report['results'])}."
    )
    return int(any(item["status"] == "error" for item in report["results"]))


if __name__ == "__main__":
    raise SystemExit(main())
