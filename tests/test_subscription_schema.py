from pathlib import Path
import sqlite3

import pytest


def test_subscription_schema_and_delivery_cascades() -> None:
    schema = (
        Path(__file__).parents[1] / "subscriptions" / "schema.sql"
    ).read_text(encoding="utf-8")
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(schema)
    connection.execute(
        """INSERT INTO subscribers (
             email_hash, language, status, created_at
           ) VALUES ('subscriber', 'en', 'active', '2026-06-15T00:00:00Z')"""
    )
    connection.execute(
        """INSERT INTO notification_events (
             event_key, payload_json, discovered_at
           ) VALUES ('event', '{}', '2026-06-15T00:00:00Z')"""
    )
    connection.execute(
        """INSERT INTO deliveries (event_key, email_hash, sent_at)
           VALUES ('event', 'subscriber', '2026-06-15T00:00:00Z')"""
    )
    connection.execute(
        "DELETE FROM subscribers WHERE email_hash = 'subscriber'"
    )
    assert connection.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0] == 0


def test_roadmap_schema_enforces_one_vote_per_anonymous_visitor() -> None:
    schema = (
        Path(__file__).parents[1] / "subscriptions" / "schema.sql"
    ).read_text(encoding="utf-8")
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(schema)

    connection.execute(
        """INSERT INTO roadmap_votes (proposal_id, visitor_hash, created_at)
           VALUES ('account-login-and-favorites', 'visitor-hash', '2026-06-20T00:00:00Z')"""
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO roadmap_votes (proposal_id, visitor_hash, created_at)
               VALUES ('account-login-and-favorites', 'visitor-hash', '2026-06-20T00:01:00Z')"""
        )
