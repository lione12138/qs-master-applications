from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .approvals import (
    approve_official_adapter_window_candidates,
    approve_programme_candidates,
    approve_window,
)
from .coverage import generate_coverage
from .deadlines import update_deadlines
from .generic_discovery_batch import (
    refresh_generic_discovery_report,
    run_assisted_discovery_entry,
    run_generic_discovery_batch,
)
from .generic_seed_discovery import run_generic_seed_discovery
from .intakes import migrate_application_intakes
from .io import read_json
from .monitor import monitor_universities, print_summary
from .paths import (
    APPLICATION_SOURCE_STATE_PATH,
    GENERIC_PROGRAMME_DISCOVERY_CONFIG_PATH,
    PROGRAMME_CANDIDATES_PATH,
    SITE_DIR,
    UNIVERSITIES_PATH,
)
from .predictions import generate_predictions
from .programme_adapters.generic import GenericProgrammeAdapter, GenericProgrammeConfig
from .programme_adapters.registry import PROGRAMME_ADAPTERS
from .programme_discovery import discover_programmes
from .readme import generate_readmes
from .review import generate_review_outputs
from .schemas import export_schemas
from .site import build_site
from .source_monitor import monitor_application_sources
from .validation import validate_data


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
    programme_discovery = subparsers.add_parser(
        "discover-programmes",
        help="Discover new taught programmes from supported official catalogues",
    )
    programme_discovery.add_argument(
        "--university",
        choices=("all", *tuple(PROGRAMME_ADAPTERS)),
        default="cuhk",
    )
    programme_discovery.add_argument("--dry-run", action="store_true")
    generic_discovery = subparsers.add_parser(
        "discover-generic-programmes",
        help="Discover taught master's programmes from official seed pages",
    )
    generic_discovery.add_argument("--university", required=True)
    generic_discovery.add_argument(
        "--seed",
        action="append",
        help="Official catalogue or programme page URL. Can be repeated.",
    )
    generic_discovery.add_argument(
        "--prefix",
        help="Programme id prefix. Defaults to a slug derived from the university id.",
    )
    generic_discovery.add_argument("--default-intake", default="September 2026")
    generic_discovery.add_argument("--default-application-opens-at")
    generic_discovery.add_argument("--minimum-closes-at", default="2025-07-01")
    generic_discovery.add_argument("--min-programmes", type=int, default=1)
    generic_discovery.add_argument("--max-pages", type=int, default=25)
    generic_discovery.add_argument("--dry-run", action="store_true")
    generic_batch = subparsers.add_parser(
        "discover-generic-batch",
        help="Run configured generic programme discovery seed pages",
    )
    generic_batch.add_argument("--dry-run", action="store_true")
    generic_batch.add_argument(
        "--replace-existing",
        action="store_true",
        help="Remove pending candidates from this configured batch before rerunning.",
    )
    generic_batch.add_argument(
        "--only",
        action="append",
        help="Limit to a university id or configured name. Can be repeated.",
    )
    generic_seeds = subparsers.add_parser(
        "discover-generic-seeds",
        help="Audit configured generic discovery seeds and recommend replacements",
    )
    generic_seeds.add_argument(
        "--only",
        action="append",
        help="Limit to a university id or configured name. Can be repeated.",
    )
    generic_seeds.add_argument("--max-candidate-seeds", type=int, default=12)
    subparsers.add_parser(
        "refresh-generic-report",
        help="Refresh generic discovery review buckets without network requests",
    )
    assisted_discovery = subparsers.add_parser(
        "discover-assisted",
        help="Search official domains and use DeepSeek to extract review candidates",
    )
    assisted_discovery.add_argument("--university", required=True)
    assisted_discovery.add_argument("--dry-run", action="store_true")
    deadlines = subparsers.add_parser(
        "update-deadlines", help="Run configured programme parsers"
    )
    deadlines.add_argument("--dry-run", action="store_true")
    pipeline = subparsers.add_parser("pipeline", help="Run the daily pipeline")
    pipeline.add_argument("--workers", type=int, default=16)
    pipeline.add_argument("--skip-monitor", action="store_true")
    pipeline.add_argument("--skip-build", action="store_true")
    subparsers.add_parser("coverage", help="Generate QS top-200 coverage metrics")
    subparsers.add_parser(
        "predictions", help="Generate non-official next-cycle estimates"
    )
    subparsers.add_parser(
        "migrate-intakes", help="Add structured intake details to applications"
    )
    subparsers.add_parser(
        "export-schemas", help="Export Pydantic contracts as JSON Schema"
    )
    subparsers.add_parser(
        "readme", help="Generate English and Chinese result dashboards"
    )
    approve = subparsers.add_parser(
        "approve-window", help="Promote a reviewed exact-window candidate"
    )
    approve.add_argument("candidate_id")
    approve.add_argument("--reviewer", required=True)
    approve_programmes = subparsers.add_parser(
        "approve-programmes",
        help="Promote reviewed programme candidates with exact windows",
    )
    approve_programmes.add_argument("--university", required=True)
    approve_programmes.add_argument("--reviewer", required=True)
    approve_programmes.add_argument(
        "--include-unparsed",
        action="store_true",
        help="Also promote candidates whose parseStatus is not parsed",
    )
    approve_adapter_windows = subparsers.add_parser(
        "approve-adapter-windows",
        help="Promote all complete official exact-window candidates from adapters",
    )
    approve_adapter_windows.add_argument("--reviewer", required=True)
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
    elif args.command == "discover-programmes":
        if args.university == "all":
            report, _successful_ids = _run_dedicated_discovery(dry_run=args.dry_run)
        else:
            report = discover_programmes(
                PROGRAMME_ADAPTERS[args.university](),
                dry_run=args.dry_run,
            )
        print(json.dumps(report, ensure_ascii=False))
    elif args.command == "discover-generic-programmes":
        university = _university_by_id(args.university)
        seed_urls = tuple(
            args.seed
            or [
                university.get("admissionsUrl") or university.get("homepageUrl") or "",
            ]
        )
        adapter = GenericProgrammeAdapter(
            GenericProgrammeConfig(
                university_id=args.university,
                school_prefix=args.prefix or _generic_prefix(args.university),
                seed_urls=tuple(url for url in seed_urls if url),
                official_domains=tuple(university.get("officialDomains", [])),
                default_application_url=(
                    university.get("admissionsUrl")
                    or university.get("homepageUrl")
                    or ""
                ),
                default_intake=args.default_intake,
                default_application_opens_at=args.default_application_opens_at,
                minimum_closes_at=args.minimum_closes_at,
                minimum_expected_programmes=args.min_programmes,
                max_detail_pages=args.max_pages,
            )
        )
        print(
            json.dumps(
                discover_programmes(adapter, dry_run=args.dry_run),
                ensure_ascii=False,
            )
        )
    elif args.command == "discover-generic-batch":
        report = run_generic_discovery_batch(
            dry_run=args.dry_run,
            replace_existing=args.replace_existing,
            only=set(args.only) if args.only else None,
        )
        print(json.dumps(report["summary"], ensure_ascii=False))
    elif args.command == "discover-generic-seeds":
        report = run_generic_seed_discovery(
            only=set(args.only) if args.only else None,
            max_candidate_seeds=args.max_candidate_seeds,
        )
        print(json.dumps(report["summary"], ensure_ascii=False))
    elif args.command == "discover-assisted":
        config = read_json(GENERIC_PROGRAMME_DISCOVERY_CONFIG_PATH)
        entry = next(
            (
                item
                for item in config.get("schools", [])
                if args.university in {item.get("universityId"), item.get("name")}
            ),
            None,
        )
        if entry is None:
            raise SystemExit(
                f"No generic discovery entry configured for {args.university}"
            )
        report = run_assisted_discovery_entry(
            entry,
            _university_by_id(entry["universityId"]),
            dry_run=args.dry_run,
        )
        print(json.dumps(report, ensure_ascii=False))
        if report.get("status") == "error":
            raise SystemExit(1)
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
        print(f"Wrote {len(predictions['predictions'])} non-official predictions.")
    elif args.command == "migrate-intakes":
        payload = migrate_application_intakes()
        generate_predictions()
        print(f"Migrated {len(payload['applications'])} structured intake records.")
    elif args.command == "export-schemas":
        written = export_schemas()
        print(f"Wrote {len(written)} JSON Schema files.")
    elif args.command == "readme":
        written = generate_readmes()
        print(f"Wrote README dashboards: {written[0].name}, {written[1].name}.")
    elif args.command == "approve-window":
        record = approve_window(args.candidate_id, args.reviewer)
        generate_predictions()
        coverage = generate_coverage()
        generate_readmes()
        print(
            f"Approved {record['id']}; "
            f"{coverage['summary']['verifiedWindows']} verified windows tracked."
        )
    elif args.command == "approve-programmes":
        if args.university == "all":
            report = _approve_all_programmes(
                reviewer=args.reviewer,
                parsed_only=not args.include_unparsed,
            )
        else:
            report = approve_programme_candidates(
                university_id=args.university,
                reviewer=args.reviewer,
                parsed_only=not args.include_unparsed,
            )
        refresh_generic_discovery_report()
        generate_predictions()
        print(json.dumps(report, ensure_ascii=False))
    elif args.command == "approve-adapter-windows":
        report = approve_official_adapter_window_candidates(
            reviewer=args.reviewer,
        )
        generate_predictions()
        print(json.dumps(report, ensure_ascii=False))
    elif args.command == "refresh-generic-report":
        report = refresh_generic_discovery_report()
        print(json.dumps(report["summary"], ensure_ascii=False))
    elif args.command == "pipeline":
        generate_predictions()
        _validate_or_exit()
        if not args.skip_monitor:
            print_summary(monitor_universities(workers=args.workers))
            print_summary(
                monitor_application_sources(workers=max(1, args.workers // 2))
            )
            discovery_reports, successful_dedicated_ids = _run_dedicated_discovery()
            for discovery_report in discovery_reports:
                print(json.dumps(discovery_report, ensure_ascii=False))
            generic_report = run_generic_discovery_batch(
                successful_dedicated_university_ids=successful_dedicated_ids
            )
            print(json.dumps(generic_report["summary"], ensure_ascii=False))
            auto_programme_report = {
                university_id: approve_programme_candidates(
                    university_id=university_id,
                    reviewer="automated-official-source-policy",
                    parsed_only=False,
                )
                for university_id in sorted(successful_dedicated_ids)
            }
            auto_window_report = approve_official_adapter_window_candidates(
                reviewer="automated-official-source-policy",
                university_ids=successful_dedicated_ids,
            )
            print(
                json.dumps(
                    {
                        "autoPublishedProgrammes": auto_programme_report,
                        "autoPublishedAdapterWindows": auto_window_report,
                    },
                    ensure_ascii=False,
                )
            )
        report = update_deadlines()
        if any(item["status"] == "error" for item in report["results"]):
            raise SystemExit(1)
        generate_predictions()
        _validate_or_exit()
        coverage = generate_coverage()
        generate_readmes()
        print(
            "Top-200 coverage: "
            f"{coverage['summary']['policiesVerified']}/200 policies, "
            f"{coverage['summary']['universitiesWithWindows']}/200 with windows"
        )
        review_report, review_summary = generate_review_outputs(
            source_state_path=APPLICATION_SOURCE_STATE_PATH
        )
        print(
            f"Wrote review report: {review_report} "
            f"({review_summary['pendingReview']} pending)"
        )
        if not args.skip_build:
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
        f"{summary['evidenceSnapshots']} evidence snapshots; "
        f"{summary['enabledParsers']} enabled parsers; "
        f"{summary['legacyConfiguredOpeningWindows']} legacy configured openings."
    )
    return summary


def _pipeline_discovery_report(
    name: str,
    adapter_factory,
    *,
    dry_run: bool = False,
) -> dict:
    adapter = None
    try:
        adapter = adapter_factory()
        return discover_programmes(adapter, dry_run=dry_run)
    except Exception as exc:
        return {
            "status": "error",
            "adapter": name,
            "universityId": getattr(
                adapter,
                "university_id",
                getattr(adapter_factory, "university_id", None),
            ),
            "sourceUrl": getattr(
                adapter,
                "catalog_url",
                getattr(adapter_factory, "catalog_url", None),
            ),
            "errorType": type(exc).__name__,
            "message": str(exc),
            "dryRun": dry_run,
        }


def _run_dedicated_discovery(
    *,
    dry_run: bool = False,
) -> tuple[list[dict], set[str]]:
    reports = [
        _pipeline_discovery_report(name, adapter_factory, dry_run=dry_run)
        for name, adapter_factory in PROGRAMME_ADAPTERS.items()
    ]
    successful_university_ids = {
        report["universityId"]
        for report in reports
        if report.get("status") == "ok" and report.get("universityId")
    }
    return reports, successful_university_ids


def _approve_all_programmes(*, reviewer: str, parsed_only: bool) -> dict:
    report = {}
    for university_id in _pending_programme_candidate_university_ids():
        report[university_id] = approve_programme_candidates(
            university_id=university_id,
            reviewer=reviewer,
            parsed_only=parsed_only,
        )
    return report


def _pending_programme_candidate_university_ids() -> list[str]:
    candidates = read_json(PROGRAMME_CANDIDATES_PATH, {"items": []})
    return sorted(
        {
            item["universityId"]
            for item in candidates.get("items", [])
            if item.get("type") == "new-programme"
            and item.get("status", "pending") == "pending"
            and item.get("universityId")
        }
    )


def _university_by_id(university_id: str) -> dict:
    universities = read_json(UNIVERSITIES_PATH).get("universities", [])
    for university in universities:
        if university.get("id") == university_id:
            return university
    raise SystemExit(f"Unknown university id: {university_id}")


def _generic_prefix(university_id: str) -> str:
    ignored = {"the", "university", "of", "and", "college", "institute"}
    parts = [part for part in university_id.split("-") if part not in ignored]
    return "-".join(parts[:3]) if parts else university_id.split("-", 1)[0]


if __name__ == "__main__":
    main()
