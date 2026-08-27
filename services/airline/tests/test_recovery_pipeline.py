from __future__ import annotations

import hashlib
import os
from dataclasses import replace

import psycopg
import pytest
from psycopg.rows import dict_row

from airstrong_airline.database import (
    create_world,
    events_after,
    load_snapshot,
    migrate,
    persist_recovery_batch,
    trigger_hero_scenario,
)
from airstrong_airline.ranking import rank_valid_candidates
from airstrong_airline.recovery import StrategyParameters
from airstrong_airline.solver_primitives import CandidateDiversityError, generate_candidates
from airstrong_airline.twin import evaluate_candidate, factual_replanning_feedback

DATABASE_URL = os.getenv("AIRSTRONG_TEST_DATABASE_URL")
pytestmark = pytest.mark.integration
ARTIFACT_HASH = hashlib.sha256(b"runtime-generated-recovery-fixture").hexdigest()


@pytest.fixture()
def recovery_world():
    if not DATABASE_URL:
        pytest.skip("AIRSTRONG_TEST_DATABASE_URL is not configured")
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        migrate(connection)
        world_id = create_world(connection)
        scenario = trigger_hero_scenario(connection, world_id, idempotency_key="recovery-scenario")
        snapshot = load_snapshot(connection, world_id)
        scope = tuple(sorted({item.entity_id for item in scenario.impacts if item.entity_type == "flight"}))
        try:
            yield connection, world_id, snapshot, scope
        finally:
            with connection.transaction():
                connection.execute("DELETE FROM airline_worlds WHERE world_id = %s", (world_id,))


def representative_strategies() -> tuple[StrategyParameters, ...]:
    return (
        StrategyParameters(
            strategy_id="parameter-set-01",
            max_cancellations=0,
            max_delay_minutes=120,
            allow_aircraft_substitution=True,
            cancellation_weight=1_000,
            passenger_preservation_weight=100,
            delay_weight=5,
            aircraft_reassignment_weight=1,
            stabilization_weight=1,
        ),
        StrategyParameters(
            strategy_id="parameter-set-02",
            max_cancellations=0,
            max_delay_minutes=540,
            allow_aircraft_substitution=False,
            cancellation_weight=1_000,
            passenger_preservation_weight=100,
            delay_weight=1,
            aircraft_reassignment_weight=100,
            stabilization_weight=1,
        ),
        StrategyParameters(
            strategy_id="parameter-set-03",
            max_cancellations=6,
            max_delay_minutes=120,
            allow_aircraft_substitution=False,
            cancellation_weight=1,
            passenger_preservation_weight=0,
            delay_weight=100,
            aircraft_reassignment_weight=100,
            stabilization_weight=10,
        ),
    )


def test_solver_twin_ranking_and_persistence_are_factual(recovery_world) -> None:
    connection, world_id, snapshot, scope = recovery_world
    candidates = generate_candidates(
        snapshot,
        scope,
        representative_strategies(),
        artifact_hash=ARTIFACT_HASH,
    )
    evaluations = tuple(evaluate_candidate(snapshot, candidate) for candidate in candidates)

    assert len(candidates) == 3
    assert len({candidate.candidate_id for candidate in candidates}) == 3
    assert len({repr(candidate.actions) for candidate in candidates}) == 3
    assert all(
        candidate.snapshot_hash == evaluations[index].snapshot_hash
        for index, candidate in enumerate(candidates)
    )
    assert any(evaluation.valid for evaluation in evaluations)
    assert any(not evaluation.valid and evaluation.violations for evaluation in evaluations)
    rejected = next(evaluation for evaluation in evaluations if not evaluation.valid)
    feedback = factual_replanning_feedback(rejected)
    assert feedback["valid"] is False
    assert feedback["violations"]
    assert all(item["facts"] for item in feedback["violations"])

    ranked = rank_valid_candidates(evaluations)
    assert all(evaluation.valid and not evaluation.violations for evaluation in ranked)
    assert [evaluation.metrics.cancellations for evaluation in ranked] == sorted(
        evaluation.metrics.cancellations for evaluation in ranked
    )

    event_count_before = len(events_after(connection, world_id))
    batch_id = persist_recovery_batch(connection, snapshot, candidates, evaluations, ranked)
    stored = connection.execute(
        """
        SELECT c.candidate_id, c.strategy_parameters, c.actions, c.snapshot_hash,
               c.artifact_hash, e.valid, e.rank, e.recommended, e.violations
        FROM airline_recovery_candidates c
        JOIN airline_candidate_evaluations e USING (candidate_id)
        WHERE c.batch_id = %s
        ORDER BY c.candidate_id
        """,
        (batch_id,),
    ).fetchall()
    assert len(stored) == 3
    assert sum(row["recommended"] for row in stored) == 1
    assert next(row for row in stored if row["recommended"])["valid"] is True
    assert all(row["snapshot_hash"] == candidates[0].snapshot_hash for row in stored)
    assert all(row["artifact_hash"] == ARTIFACT_HASH for row in stored)
    assert all(row["strategy_parameters"] and row["actions"] for row in stored)
    assert any(row["violations"] for row in stored if not row["valid"])

    replay_batch_id = persist_recovery_batch(connection, snapshot, candidates, evaluations, ranked)
    assert replay_batch_id == batch_id
    assert len(events_after(connection, world_id)) == event_count_before + 1


def test_twin_rejects_a_candidate_from_another_snapshot(recovery_world) -> None:
    _, _, snapshot, scope = recovery_world
    candidate = generate_candidates(
        snapshot,
        scope,
        (representative_strategies()[0],),
        artifact_hash=ARTIFACT_HASH,
    )[0]

    evaluation = evaluate_candidate(snapshot, replace(candidate, snapshot_hash="0" * 64))

    assert evaluation.valid is False
    assert any(violation.code == "STALE_SNAPSHOT" for violation in evaluation.violations)


def test_duplicate_strategy_outcomes_are_rejected_instead_of_relabelled(recovery_world) -> None:
    _, _, snapshot, scope = recovery_world
    first = representative_strategies()[0]
    duplicate = replace(first, strategy_id="different-label-same-parameters")

    with pytest.raises(CandidateDiversityError):
        generate_candidates(snapshot, scope, (first, duplicate), artifact_hash=ARTIFACT_HASH)
