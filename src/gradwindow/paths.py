from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
EVIDENCE_DIR = DATA_DIR / "evidence"
OPS_DIR = DATA_DIR / "ops"
REPORTS_DIR = OPS_DIR / "reports"
SCHEMA_DIR = ROOT / "docs" / "schemas"
SITE_DIR = ROOT / "site"

UNIVERSITIES_PATH = DATA_DIR / "universities.json"
APPLICATIONS_PATH = DATA_DIR / "applications.json"
PREDICTIONS_PATH = DATA_DIR / "predictions.json"
SOURCES_PATH = DATA_DIR / "sources.json"
MONITOR_STATE_PATH = OPS_DIR / "monitor-state.json"
MONITOR_REPORT_PATH = OPS_DIR / "monitor-report.json"
PROGRAMS_PATH = DATA_DIR / "programs.json"
PROGRAMME_GROUPS_PATH = DATA_DIR / "programme-groups.json"
APPLICANT_CATEGORIES_PATH = DATA_DIR / "applicant-categories.json"
WINDOW_POLICIES_PATH = DATA_DIR / "window-policies.json"
REVIEW_QUEUE_PATH = OPS_DIR / "review-queue.json"
COVERAGE_PATH = DATA_DIR / "coverage.json"
GLOBAL_RANKINGS_PATH = DATA_DIR / "global-rankings.json"
WINDOW_CANDIDATES_PATH = OPS_DIR / "window-candidates.json"
APPLICATION_SOURCE_STATE_PATH = OPS_DIR / "application-source-state.json"
PROGRAMME_CANDIDATES_PATH = OPS_DIR / "programme-candidates.json"
PROGRAMME_CATALOG_STATE_PATH = OPS_DIR / "programme-catalog-state.json"
