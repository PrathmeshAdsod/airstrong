from __future__ import annotations

import os
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from airstrong_airline import baseline
from airstrong_airline.database import (
    create_world,
    events_after,
    load_snapshot,
    migrate,
    reset_world,
    trigger_hero_scenario,
)

DATABASE_URL = os.getenv("AIRSTRONG_TEST_DATABASE_URL")
pytestmark = pytest.mark.integration


@pytest.fixture()
def connection():
    if not DATABASE_URL:
        pytest.skip("AIRSTRONG_TEST_DATABASE_URL is not configured")
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as selected:
        migrate(selected)
        yield selected


def _cleanup(connection: psycopg.Connection, *world_ids: UUID) -> None:
    with connection.transaction():
        connection.execute("DELETE FROM airline_worlds WHERE world_id = ANY(%s)", (list(world_ids),))


def _logical_impacts(result) -> set[tuple[str, str, str, int]]:
    return {(item.entity_type, item.entity_id, item.reason, item.depth) for item in result.impacts}


def test_hero_mutation_is_real_idempotent_and_durable(connection: psycopg.Connection) -> None:
    world_id = create_world(connection)
    try:
        before = load_snapshot(connection, world_id)
        assert before.revision == 0
        assert not before.disruptions
        assert {flight.status for flight in before.flights} == {"scheduled"}

        result = trigger_hero_scenario(connection, world_id, idempotency_key="scenario-once")
        after = load_snapshot(connection, world_id)
        assert result.world_revision == 1
        assert len(result.disruption_ids) == 2
        assert {impact.entity_type for impact in result.impacts} == {"flight", "crew", "passenger_party"}
        assert max(impact.depth for impact in result.impacts) >= 2
        impacted_flights = {impact.entity_id for impact in result.impacts if impact.entity_type == "flight"}
        assert {
            flight.flight_id for flight in after.flights if flight.status == "at_risk"
        } == impacted_flights
        assert next(item for item in after.aircraft if item.aircraft_id == "ALN-A03").status == "unavailable"

        replay = trigger_hero_scenario(connection, world_id, idempotency_key="scenario-once")
        assert replay.replayed is True
        assert replay.world_revision == result.world_revision
        assert _logical_impacts(replay) == _logical_impacts(result)
        assert [event["sequence"] for event in events_after(connection, world_id)] == [1, 2, 3]
    finally:
        _cleanup(connection, world_id)


def test_calculation_changes_when_authoritative_database_state_changes(
    connection: psycopg.Connection,
) -> None:
    baseline_world = create_world(connection)
    changed_world = create_world(connection)
    try:
        with connection.transaction():
            connection.execute(
                "UPDATE airline_airports SET hourly_capacity = 10 WHERE world_id = %s AND code = 'BOM'",
                (changed_world,),
            )
        baseline_result = trigger_hero_scenario(connection, baseline_world, idempotency_key="baseline")
        changed_result = trigger_hero_scenario(connection, changed_world, idempotency_key="changed")

        assert _logical_impacts(baseline_result) != _logical_impacts(changed_result)
        assert len(changed_result.impacts) < len(baseline_result.impacts)
    finally:
        _cleanup(connection, baseline_world, changed_world)


def test_worlds_are_isolated_and_identical_baselines_are_deterministic(
    connection: psycopg.Connection,
) -> None:
    first_world = create_world(connection)
    second_world = create_world(connection)
    try:
        first_result = trigger_hero_scenario(connection, first_world, idempotency_key="first")
        second_before = load_snapshot(connection, second_world)
        assert second_before.revision == 0
        assert not second_before.disruptions

        second_result = trigger_hero_scenario(connection, second_world, idempotency_key="second")
        assert _logical_impacts(first_result) == _logical_impacts(second_result)
    finally:
        _cleanup(connection, first_world, second_world)


def test_reset_restores_the_versioned_baseline_without_duplicate_work(connection: psycopg.Connection) -> None:
    world_id = create_world(connection)
    try:
        original = trigger_hero_scenario(connection, world_id, idempotency_key="trigger")
        revision = reset_world(connection, world_id, idempotency_key="reset-once")
        reset_snapshot = load_snapshot(connection, world_id)
        assert revision == 2
        assert reset_snapshot.revision == 2
        assert not reset_snapshot.disruptions
        assert {flight.status for flight in reset_snapshot.flights} == {"scheduled"}
        assert tuple(flight.flight_id for flight in reset_snapshot.flights) == tuple(
            flight.flight_id
            for flight in sorted(
                baseline.FLIGHTS, key=lambda item: (item.scheduled_departure, item.flight_id)
            )
        )

        replay_revision = reset_world(connection, world_id, idempotency_key="reset-once")
        assert replay_revision == revision
        old_scenario_replay = trigger_hero_scenario(connection, world_id, idempotency_key="trigger")
        assert old_scenario_replay.replayed is True
        assert old_scenario_replay.world_revision == 1
        assert _logical_impacts(old_scenario_replay) == _logical_impacts(original)
        assert load_snapshot(connection, world_id).revision == 2
        assert not load_snapshot(connection, world_id).disruptions
        assert [event["eventType"] for event in events_after(connection, world_id)] == [
            "world.created",
            "scenario.triggered",
            "world.recalculated",
            "world.reset",
        ]
    finally:
        _cleanup(connection, world_id)
