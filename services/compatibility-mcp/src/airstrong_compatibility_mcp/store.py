from __future__ import annotations

import os
from dataclasses import dataclass

import psycopg


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sponsor_compatibility_audit (
    idempotency_key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


@dataclass(frozen=True)
class AuditState:
    exists: bool
    total_writes: int


def database_url() -> str:
    value = os.environ.get("AIRSTRONG_DATABASE_URL")
    if not value:
        raise RuntimeError("AIRSTRONG_DATABASE_URL is required")
    return value


def ensure_schema() -> None:
    with psycopg.connect(database_url()) as connection:
        connection.execute(SCHEMA_SQL)


def audit_state(idempotency_key: str) -> AuditState:
    ensure_schema()
    with psycopg.connect(database_url()) as connection:
        row = connection.execute(
            """
            SELECT
                EXISTS(
                    SELECT 1 FROM sponsor_compatibility_audit
                    WHERE idempotency_key = %s
                ),
                COUNT(*)
            FROM sponsor_compatibility_audit
            """,
            (idempotency_key,),
        ).fetchone()
    if row is None:
        raise RuntimeError("PostgreSQL returned no compatibility audit state")
    return AuditState(exists=bool(row[0]), total_writes=int(row[1]))


def commit_once(idempotency_key: str, payload: str) -> tuple[bool, AuditState]:
    ensure_schema()
    with psycopg.connect(database_url()) as connection:
        result = connection.execute(
            """
            INSERT INTO sponsor_compatibility_audit (idempotency_key, payload)
            VALUES (%s, %s)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING idempotency_key
            """,
            (idempotency_key, payload),
        ).fetchone()
    return result is not None, audit_state(idempotency_key)
