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


def test_university_comments_schema_stores_public_comments() -> None:
    schema = (
        Path(__file__).parents[1] / "subscriptions" / "schema.sql"
    ).read_text(encoding="utf-8")
    connection = sqlite3.connect(":memory:")
    connection.executescript(schema)

    connection.execute(
        """INSERT INTO university_comments (
             id, university_id, visitor_hash, author, body, created_at
           ) VALUES (
             'comment-1', 'ucl-university-college-london',
             'visitor-hash', 'Applicant', 'Useful admissions note.',
             '2026-06-24T00:00:00Z'
           )"""
    )

    row = connection.execute(
        """SELECT author, body FROM university_comments
           WHERE university_id = 'ucl-university-college-london'
             AND hidden_at IS NULL"""
    ).fetchone()
    assert row == ("Applicant", "Useful admissions note.")


def test_user_favorites_are_owned_by_account() -> None:
    schema = (
        Path(__file__).parents[1] / "subscriptions" / "schema.sql"
    ).read_text(encoding="utf-8")
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(schema)

    connection.execute(
        """INSERT INTO users (
             id, email_hash, language, created_at, updated_at
           ) VALUES (
             'user-1', 'email-hash', 'en',
             '2026-06-26T00:00:00Z', '2026-06-26T00:00:00Z'
           )"""
    )
    connection.execute(
        """INSERT INTO user_favorites (user_id, item_key, created_at)
           VALUES ('user-1', 'window:ucl-advanced-materials', '2026-06-26T00:00:00Z')"""
    )
    connection.execute("DELETE FROM users WHERE id = 'user-1'")

    assert connection.execute("SELECT COUNT(*) FROM user_favorites").fetchone()[0] == 0


def test_auth_session_points_to_user() -> None:
    schema = (
        Path(__file__).parents[1] / "subscriptions" / "schema.sql"
    ).read_text(encoding="utf-8")
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(schema)

    connection.execute(
        """INSERT INTO users (
             id, email_hash, language, created_at, updated_at
           ) VALUES (
             'user-1', 'email-hash', 'en',
             '2026-06-26T00:00:00Z', '2026-06-26T00:00:00Z'
           )"""
    )
    connection.execute(
        """INSERT INTO auth_sessions (
             session_hash, user_id, created_at, expires_at
           ) VALUES (
             'session-hash', 'user-1',
             '2026-06-26T00:00:00Z', '2026-07-26T00:00:00Z'
           )"""
    )

    assert (
        connection.execute(
            """SELECT users.id FROM auth_sessions
               JOIN users ON users.id = auth_sessions.user_id
               WHERE auth_sessions.session_hash = 'session-hash'"""
        ).fetchone()[0]
        == "user-1"
    )
