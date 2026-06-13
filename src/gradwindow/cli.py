from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .approvals import approve_window
from .deadlines import update_deadlines
from .coverage import generate_coverage
from .monitor import monitor_universities, print_summary
from .paths import APPLICATION_SOURCE_STATE_PATH, SITE_DIR
from .predictions import generate_predictions
from .source_monitor import monitor_application_sources
from .site import build_site
from .validation import validate_data
from .review import generate_review_outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="GradWindow data pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate", help="Validate public datasets")
    build = subparsers.add_parser("build-site", help="Build the deployable site")
    build.add_argument("--output", type=Path, default=SITE_DIR)
    monitor = subparsers.add_parser("monitor", help="Check university pages")
    monitor.add_argument("--workers", type=int, default=16)
    source_monitor = subparsers.add_parser(
        "monitor-sources", help="Check exact application-window source pages"
    )
    source_monitor.add_argument("--workers", type=int, default=8)
    deadlines = subparsers.add_parser(
        "update-deadlines", help="Run configured programme parsers"
    )
    deadlines.add_argument("--dry-run", action="store_true")
    pipeline = subparsers.add_parser("pipeline", help="Run the daily pipeline")
    pipeline.add_argument("--workers", type=int, default=16)
    pipeline.add_argument("--skip-monitor", action="store_true")
    subparsers.add_parser("coverage", help="Generate QS top-30 coverage metrics")
    subparsers.add_parser(
        "predictions", help="Generate non-official next-cycle estimates"
    )
    approve = subparsers.add_parser(
        "approve-window", help="Promote a reviewed exact-window candidate"
    )
    approve.add_argument("candidate_id")
    approve.add_argument("--reviewer", required=True)
    args = parser.parse_args()

    if args.command == "validate":
        _validate_or_exit()
    elif args.command == "build-site":
        generate_predictions()
        _validate_or_exit()
        generate_coverage()
        print(f"Wrote site: {build_site(args.output)}")
    elif args.command == "monitor":
        print_summary(monitor_universities(workers=args.workers))
    elif args.command == "monitor-sources":
        print_summary(monitor_application_sources(workers=args.workers))
    elif args.command == "update-deadlines":
        report = update_deadlines(dry_run=args.dry_run)
        print(json.dumps(report, ensure_ascii=False))
        if any(item["status"] == "error" for item in report["results"]):
            raise SystemExit(1)
    elif args.command == "coverage":
        generate_predictions()
        coverage = generate_coverage()
        print(json.dumps(coverage["summary"], ensure_ascii=False))
    elif args.command == "predictions":
        predictions = generate_predictions()
        print(
            f"Wrote {len(predictions['predictions'])} non-official predictions."
        )
    elif args.command == "approve-window":
        record = approve_window(args.candidate_id, args.reviewer)
        generate_predictions()
        coverage = generate_coverage()
        print(
            f"Approved {record['id']}; "
            f"{coverage['summary']['verifiedWindows']} top-30 windows tracked."
        )
    elif args.command == "pipeline":
        generate_predictions()
        _validate_or_exit()
        if not args.skip_monitor:
            print_summary(monitor_universities(workers=args.workers))
            print_summary(
                monitor_application_sources(workers=max(1, args.workers // 2))
            )
        report = update_deadlines()
        if any(item["status"] == "error" for item in report["results"]):
            raise SystemExit(1)
        generate_predictions()
        _validate_or_exit()
        coverage = generate_coverage()
        print(
            "Top-30 coverage: "
            f"{coverage['summary']['policiesVerified']}/30 policies, "
            f"{coverage['summary']['universitiesWithWindows']}/30 with windows"
        )
        review_report, review_summary = generate_review_outputs(
            source_state_path=APPLICATION_SOURCE_STATE_PATH
        )
        print(
            f"Wrote review report: {review_report} "
            f"({review_summary['pendingReview']} pending)"
        )
        print(f"Wrote site: {build_site()}")


def _validate_or_exit() -> dict[str, int]:
    errors, summary = validate_data()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(
        "Validated "
        f"{summary['universities']} universities, "
        f"{summary['admissionsCandidates']} admissions candidates "
        f"({summary['curatedAdmissions']} curated), and "
        f"{summary['verifiedWindows']} verified windows with "
        f"{summary['predictedWindows']} next-cycle predictions and "
        f"{summary['enabledParsers']} enabled parsers."
    )
    return summary


if __name__ == "__main__":
    main()
