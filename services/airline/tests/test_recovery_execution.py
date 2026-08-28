from __future__ import annotations

import hashlib
import os

import psycopg
import pytest
from psycopg.rows import dict_row

from airstrong_airline.database import (
    apply_approved_recovery,
    attach_recovery_batch_to_run,
    create_recovery_run,
    create_world,
    decide_recovery_approval,
    link_recovery_investigation_turn,
    load_snapshot,
    migrate,
    persist_recovery_batch,
    record_trueforge_approval_request,
    recovery_run,
    request_recovery_approval,
    reset_world,
    trigger_hero_scenario,
    verify_recovery_execution,
)
from airstrong_airline.ranking import rank_valid_candidates
from airstrong_airline.recovery import StrategyParameters
from airstrong_airline.solver_primitives import generate_candidates
from airstrong_airline.twin import evaluate_candidate

DATABASE_URL = os.getenv("AIRSTRONG_TEST_DATABASE_URL")
pytestmark = pytest.mark.integration
ARTIFACT_HASH = hashlib.sha256(b"recovery-execution-test-artifact").hexdigest()


def strategies() -> tuple[StrategyParameters, ...]:
    return (
        StrategyParameters("execution-01", 0, 120, True, 1_000, 100, 5, 1, 1),
        StrategyParameters("execution-02", 0, 540, False, 1_000, 100, 1, 100, 1),
        StrategyParameters("execution-03", 6, 120, False, 1, 0, 100, 100, 10),
    )


@pytest.fixture()
def prepared_recovery():
    if not DATABASE_URL:
        pytest.skip("AIRSTRONG_TEST_DATABASE_URL is not configured")
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        migrate(connection)
        world_id = create_world(connection)
        trigger_hero_scenario(connection, world_id, idempotency_key="execution-scenario")
        snapshot = load_snapshot(connection, world_id)
        run, replayed = create_recovery_run(
            connection,
            world_id,
            idempotency_key="execution-recovery-run",
        )
        assert replayed is False
        scope = tuple(
            row["entity_id"]
            for row in connection.execute(
                """
                SELECT DISTINCT entity_id FROM airline_operational_impacts
                WHERE world_id = %s AND world_revision = %s AND entity_type = 'flight'
                ORDER BY entity_id
                """,
                (world_id, snapshot.revision),
            ).fetchall()
        )
        candidates = generate_candidates(snapshot, scope, strategies(), artifact_hash=ARTIFACT_HASH)
        evaluations = tuple(evaluate_candidate(snapshot, candidate) for candidate in candidates)
        ranked = rank_valid_candidates(evaluations)
        batch_id = persist_recovery_batch(connection, snapshot, candidates, evaluations, ranked)
        link_recovery_investigation_turn(
            connection,
            run["run_id"],
            trueforge_session_id="test-session",
            investigation_turn_id="test-investigation-turn",
        )
        attach_recovery_batch_to_run(connection, run["run_id"], batch_id)
        try:
            yield connection, world_id, run["run_id"], snapshot.revision
        finally:
            with connection.transaction():
                connection.execute("DELETE FROM airline_worlds WHERE world_id = %s", (world_id,))


def test_approval_execution_and_verification_are_durable_and_idempotent(prepared_recovery) -> None:
    connection, world_id, run_id, starting_revision = prepared_recovery
    replay, replayed = create_recovery_run(
        connection,
        world_id,
        idempotency_key="execution-recovery-run",
    )
    assert replayed is True
    assert replay["run_id"] == run_id

    awaiting = request_recovery_approval(connection, run_id)
    assert awaiting["status"] == "awaiting_approval"
    assert awaiting["approval_actions"]
    assert awaiting["approval_summary"]["flightChanges"] == len(
        {action["flight_id"] for action in awaiting["approval_actions"]}
    )
    record_trueforge_approval_request(
        connection,
        run_id,
        execution_turn_id="test-execution-turn",
        thread_id="main",
        tool_call_id="test-tool-call",
        approval_event_id="test-approval-event",
    )

    apply_arguments = {
        "world_id": world_id,
        "run_id": run_id,
        "approval_id": awaiting["approval_id"],
        "candidate_id": awaiting["recommended_candidate_id"],
        "expected_world_revision": starting_revision,
        "idempotency_key": "execution-apply-once",
    }
    with pytest.raises(ValueError, match="has not been approved"):
        apply_approved_recovery(connection, **apply_arguments)

    approved = decide_recovery_approval(
        connection,
        run_id,
        decision="approved",
        idempotency_key="execution-decision-allow",
    )
    assert approved["status"] == "approved"
    assert approved["approval_status"] == "approved"

    execution = apply_approved_recovery(connection, **apply_arguments)
    assert execution["replayed"] is False
    assert execution["starting_world_revision"] == starting_revision
    assert execution["applied_world_revision"] == starting_revision + 1
    replayed_execution = apply_approved_recovery(connection, **apply_arguments)
    assert replayed_execution["execution_id"] == execution["execution_id"]
    assert replayed_execution["replayed"] is True

    verification = verify_recovery_execution(
        connection,
        world_id=world_id,
        run_id=run_id,
        execution_id=execution["execution_id"],
    )
    assert verification["valid"] is True
    assert all(fact["matches"] for fact in verification["facts"])
    replayed_verification = verify_recovery_execution(
        connection,
        world_id=world_id,
        run_id=run_id,
        execution_id=execution["execution_id"],
    )
    assert replayed_verification["verification_id"] == verification["verification_id"]
    assert replayed_verification["replayed"] is True
    assert recovery_run(connection, run_id)["status"] == "verified"


def test_stale_world_rejects_approved_recovery(prepared_recovery) -> None:
    connection, world_id, run_id, starting_revision = prepared_recovery
    awaiting = request_recovery_approval(connection, run_id)
    decide_recovery_approval(
        connection,
        run_id,
        decision="approved",
        idempotency_key="stale-decision-allow",
    )
    reset_world(connection, world_id, idempotency_key="stale-reset-world")

    with pytest.raises(ValueError, match="World revision changed after approval"):
        apply_approved_recovery(
            connection,
            world_id=world_id,
            run_id=run_id,
            approval_id=awaiting["approval_id"],
            candidate_id=awaiting["recommended_candidate_id"],
            expected_world_revision=starting_revision,
            idempotency_key="stale-apply-attempt",
        )

    assert (
        connection.execute(
            "SELECT count(*) AS count FROM airline_operational_executions WHERE run_id = %s",
            (run_id,),
        ).fetchone()["count"]
        == 0
    )
    assert recovery_run(connection, run_id)["status"] == "stale"
