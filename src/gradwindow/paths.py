from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"

UNIVERSITIES_PATH = DATA_DIR / "universities.json"
APPLICATIONS_PATH = DATA_DIR / "applications.json"
PREDICTIONS_PATH = DATA_DIR / "predictions.json"
SOURCES_PATH = DATA_DIR / "sources.json"
MONITOR_STATE_PATH = DATA_DIR / "monitor-state.json"
MONITOR_REPORT_PATH = DATA_DIR / "monitor-report.json"
PROGRAMS_PATH = DATA_DIR / "programs.json"
WINDOW_POLICIES_PATH = DATA_DIR / "window-policies.json"
REVIEW_QUEUE_PATH = DATA_DIR / "review-queue.json"
COVERAGE_PATH = DATA_DIR / "coverage.json"
WINDOW_CANDIDATES_PATH = DATA_DIR / "window-candidates.json"
APPLICATION_SOURCE_STATE_PATH = DATA_DIR / "application-source-state.json"
