from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import baseline
from .engine import calculate_operational_impacts
from .models import (
    Aircraft,
    Airport,
    CrewAssignment,
    CrewMember,
    Disruption,
    Flight,
    ItineraryLeg,
    OperationalImpact,
    PassengerParty,
    ScenarioResult,
    WorldSnapshot,
)
from .ranking import RANKING_VERSION
from .recovery import (
    CandidateEvaluation,
    CandidatePlan,
    action_payload,
    snapshot_hash,
    snapshot_payload,
)
from .validation import validate_world

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
HERO_SCENARIO_KEY = "cyclone-bom-aircraft-unavailable"
type DbRow = dict[str, Any]
type DbConnection = psycopg.Connection[DbRow]


def connect(database_url: str) -> DbConnection:
    return cast(DbConnection, psycopg.connect(database_url, row_factory=dict_row))


def migrate(connection: DbConnection) -> None:
    with connection.transaction():
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS airline_schema_migrations (
                version text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            exists = connection.execute(
                "SELECT 1 FROM airline_schema_migrations WHERE version = %s",
                (migration.name,),
            ).fetchone()
            if exists:
                continue
            connection.execute(migration.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO airline_schema_migrations(version) VALUES (%s)",
                (migration.name,),
            )


def _executemany(connection: DbConnection, query: str, rows: Iterable[tuple[Any, ...]]) -> None:
    with connection.cursor() as cursor:
        cursor.executemany(query, rows)


def _seed_world(connection: DbConnection, world_id: UUID) -> None:
    _executemany(
        connection,
        """
        INSERT INTO airline_airports(
            world_id, code, name, city, country_code, timezone, latitude, longitude,
            hourly_capacity, domestic_connection_minutes, international_connection_minutes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (world_id, code) DO UPDATE SET
            name = EXCLUDED.name,
            city = EXCLUDED.city,
            country_code = EXCLUDED.country_code,
            timezone = EXCLUDED.timezone,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            hourly_capacity = EXCLUDED.hourly_capacity,
            domestic_connection_minutes = EXCLUDED.domestic_connection_minutes,
            international_connection_minutes = EXCLUDED.international_connection_minutes
        """,
        [
            (
                world_id,
                item.code,
                item.name,
                item.city,
                item.country_code,
                item.timezone,
                item.latitude,
                item.longitude,
                item.hourly_capacity,
                item.domestic_connection_minutes,
                item.international_connection_minutes,
            )
            for item in baseline.AIRPORTS
        ],
    )
    _executemany(
        connection,
        """
        INSERT INTO airline_aircraft(
            world_id, aircraft_id, aircraft_type, seats, location_airport, status,
            available_from, minimum_turnaround_minutes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (world_id, aircraft_id) DO UPDATE SET
            aircraft_type = EXCLUDED.aircraft_type,
            seats = EXCLUDED.seats,
            location_airport = EXCLUDED.location_airport,
            status = EXCLUDED.status,
            available_from = EXCLUDED.available_from,
            minimum_turnaround_minutes = EXCLUDED.minimum_turnaround_minutes
        """,
        [
            (
                world_id,
                item.aircraft_id,
                item.aircraft_type,
                item.seats,
                item.location_airport,
                item.status,
                item.available_from,
                item.minimum_turnaround_minutes,
            )
            for item in baseline.AIRCRAFT
        ],
    )
    _executemany(
        connection,
        """
        INSERT INTO airline_flights(
            world_id, flight_id, origin, destination, scheduled_departure,
            scheduled_arrival, aircraft_id, aircraft_type, capacity, status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                world_id,
                item.flight_id,
                item.origin,
                item.destination,
                item.scheduled_departure,
                item.scheduled_arrival,
                item.aircraft_id,
                item.aircraft_type,
                item.capacity,
                item.status,
            )
            for item in baseline.FLIGHTS
        ],
    )
    _executemany(
        connection,
        """
        INSERT INTO airline_crew(
            world_id, crew_id, role, base_airport, qualifications, duty_start,
            duty_end, previous_duty_end
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                world_id,
                item.crew_id,
                item.role,
                item.base_airport,
                list(item.qualifications),
                item.duty_start,
                item.duty_end,
                item.previous_duty_end,
            )
            for item in baseline.CREW
        ],
    )
    _executemany(
        connection,
        """
        INSERT INTO airline_crew_assignments(world_id, crew_id, flight_id, role)
        VALUES (%s, %s, %s, %s)
        """,
        [(world_id, item.crew_id, item.flight_id, item.role) for item in baseline.CREW_ASSIGNMENTS],
    )
    _executemany(
        connection,
        """
        INSERT INTO airline_passenger_parties(world_id, party_id, party_size)
        VALUES (%s, %s, %s)
        """,
        [(world_id, item.party_id, item.party_size) for item in baseline.PASSENGER_PARTIES],
    )
    _executemany(
        connection,
        """
        INSERT INTO airline_itinerary_legs(world_id, party_id, flight_id, leg_order)
        VALUES (%s, %s, %s, %s)
        """,
        [(world_id, item.party_id, item.flight_id, item.leg_order) for item in baseline.ITINERARY_LEGS],
    )


def _append_event(
    connection: DbConnection,
    world_id: UUID,
    event_type: str,
    world_revision: int,
    payload: dict,
) -> int:
    row = connection.execute(
        """
        UPDATE airline_worlds
        SET next_event_sequence = next_event_sequence + 1
        WHERE world_id = %s
        RETURNING next_event_sequence - 1 AS sequence
        """,
        (world_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown world {world_id}")
    sequence = int(row["sequence"])
    connection.execute(
        """
        INSERT INTO airline_world_events(world_id, sequence, event_type, world_revision, payload)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (world_id, sequence, event_type, world_revision, Jsonb(payload)),
    )
    connection.execute(
        "SELECT pg_notify('airline_world_events', %s)",
        (json.dumps({"worldId": str(world_id), "sequence": sequence}, separators=(",", ":")),),
    )
    return sequence


def create_world(
    connection: DbConnection,
    *,
    display_name: str = "Aliens Airline",
    world_id: UUID | None = None,
    ttl: timedelta = timedelta(hours=24),
) -> UUID:
    selected_world_id = world_id or uuid4()
    with connection.transaction():
        connection.execute(
            """
            INSERT INTO airline_worlds(
                world_id, display_name, baseline_version, simulation_clock, expires_at
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                selected_world_id,
                display_name,
                baseline.BASELINE_VERSION,
                baseline.BASELINE_CLOCK,
                datetime.now(UTC) + ttl,
            ),
        )
        _seed_world(connection, selected_world_id)
        snapshot = load_snapshot(connection, selected_world_id)
        validate_world(snapshot)
        _append_event(
            connection,
            selected_world_id,
            "world.created",
            0,
            {"baselineVersion": baseline.BASELINE_VERSION},
        )
    return selected_world_id


def create_world_once(
    connection: DbConnection,
    *,
    idempotency_key: str,
    display_name: str = "Aliens Airline",
) -> tuple[UUID, bool]:
    normalized = idempotency_key.strip()
    if not 8 <= len(normalized) <= 128:
        raise ValueError("idempotency_key must contain 8 to 128 characters")
    world_id = uuid5(NAMESPACE_URL, f"https://airstrong.local/world/{normalized}")
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (normalized,))
        existing = connection.execute(
            "SELECT world_id FROM airline_world_requests WHERE idempotency_key = %s",
            (normalized,),
        ).fetchone()
        if existing is not None:
            return existing["world_id"], True
        create_world(connection, display_name=display_name, world_id=world_id)
        connection.execute(
            "INSERT INTO airline_world_requests(idempotency_key, world_id) VALUES (%s, %s)",
            (normalized, world_id),
        )
        return world_id, False


def default_world(connection: DbConnection) -> UUID:
    return create_world_once(connection, idempotency_key="airstrong-default-world")[0]


def _rows(connection: DbConnection, query: str, world_id: UUID) -> list[DbRow]:
    return list(connection.execute(query, (world_id,)).fetchall())


def load_snapshot(connection: DbConnection, world_id: UUID) -> WorldSnapshot:
    world = connection.execute(
        "SELECT revision FROM airline_worlds WHERE world_id = %s",
        (world_id,),
    ).fetchone()
    if world is None:
        raise KeyError(f"Unknown world {world_id}")
    airports = tuple(
        Airport(
            row["code"],
            row["name"],
            row["city"],
            row["country_code"],
            row["timezone"],
            row["latitude"],
            row["longitude"],
            row["hourly_capacity"],
            row["domestic_connection_minutes"],
            row["international_connection_minutes"],
        )
        for row in _rows(
            connection, "SELECT * FROM airline_airports WHERE world_id = %s ORDER BY code", world_id
        )
    )
    aircraft = tuple(
        Aircraft(
            row["aircraft_id"],
            row["aircraft_type"],
            row["seats"],
            row["location_airport"],
            row["status"],
            row["available_from"],
            row["minimum_turnaround_minutes"],
        )
        for row in _rows(
            connection, "SELECT * FROM airline_aircraft WHERE world_id = %s ORDER BY aircraft_id", world_id
        )
    )
    flights = tuple(
        Flight(
            row["flight_id"],
            row["origin"],
            row["destination"],
            row["scheduled_departure"],
            row["scheduled_arrival"],
            row["aircraft_id"],
            row["aircraft_type"],
            row["capacity"],
            row["status"],
        )
        for row in _rows(
            connection,
            "SELECT * FROM airline_flights WHERE world_id = %s ORDER BY scheduled_departure, flight_id",
            world_id,
        )
    )
    crew = tuple(
        CrewMember(
            row["crew_id"],
            row["role"],
            row["base_airport"],
            tuple(row["qualifications"]),
            row["duty_start"],
            row["duty_end"],
            row["previous_duty_end"],
        )
        for row in _rows(
            connection, "SELECT * FROM airline_crew WHERE world_id = %s ORDER BY crew_id", world_id
        )
    )
    crew_assignments = tuple(
        CrewAssignment(row["crew_id"], row["flight_id"], row["role"])
        for row in _rows(
            connection,
            "SELECT * FROM airline_crew_assignments WHERE world_id = %s ORDER BY crew_id, flight_id",
            world_id,
        )
    )
    passenger_parties = tuple(
        PassengerParty(row["party_id"], row["party_size"])
        for row in _rows(
            connection,
            "SELECT * FROM airline_passenger_parties WHERE world_id = %s ORDER BY party_id",
            world_id,
        )
    )
    itinerary_legs = tuple(
        ItineraryLeg(row["party_id"], row["flight_id"], row["leg_order"])
        for row in _rows(
            connection,
            "SELECT * FROM airline_itinerary_legs WHERE world_id = %s ORDER BY party_id, leg_order",
            world_id,
        )
    )
    disruptions = tuple(
        Disruption(
            row["disruption_id"],
            row["kind"],
            row["airport_code"],
            row["starts_at"],
            row["ends_at"],
            row["capacity_multiplier"],
            row["aircraft_id"],
        )
        for row in _rows(
            connection,
            "SELECT * FROM airline_disruptions WHERE world_id = %s AND active ORDER BY disruption_id",
            world_id,
        )
    )
    return WorldSnapshot(
        world_id=world_id,
        revision=world["revision"],
        airports=airports,
        aircraft=aircraft,
        flights=flights,
        crew=crew,
        crew_assignments=crew_assignments,
        passenger_parties=passenger_parties,
        itinerary_legs=itinerary_legs,
        disruptions=disruptions,
    )


def load_world(connection: DbConnection, world_id: UUID) -> DbRow:
    world = connection.execute(
        """
        SELECT world_id, display_name, baseline_version, simulation_clock, revision,
               state, created_at, expires_at
        FROM airline_worlds
        WHERE world_id = %s
        """,
        (world_id,),
    ).fetchone()
    if world is None:
        raise KeyError(f"Unknown world {world_id}")
    return world


def load_impacts(
    connection: DbConnection,
    world_id: UUID,
    *,
    revision: int | None = None,
) -> tuple[OperationalImpact, ...]:
    selected_revision = revision
    if selected_revision is None:
        selected_revision = int(load_world(connection, world_id)["revision"])
    rows = connection.execute(
        """
        SELECT entity_type, entity_id, reason, depth, root_disruption_id,
               source_entity_type, source_entity_id
        FROM airline_operational_impacts
        WHERE world_id = %s AND world_revision = %s
        ORDER BY root_disruption_id, depth, entity_type, entity_id, reason
        """,
        (world_id, selected_revision),
    ).fetchall()
    return tuple(
        OperationalImpact(
            row["entity_type"],
            row["entity_id"],
            row["reason"],
            row["depth"],
            row["root_disruption_id"],
            row["source_entity_type"],
            row["source_entity_id"],
        )
        for row in rows
    )


def latest_recovery_batch(connection: DbConnection, world_id: UUID) -> DbRow | None:
    batch = connection.execute(
        """
        SELECT batch_id, world_id, world_revision, snapshot_hash, artifact_hash,
               ranking_version, created_at
        FROM airline_recovery_batches
        WHERE world_id = %s
        ORDER BY created_at DESC, batch_id DESC
        LIMIT 1
        """,
        (world_id,),
    ).fetchone()
    if batch is None:
        return None
    candidates = connection.execute(
        """
        SELECT c.candidate_id, c.strategy_parameters, c.actions, c.solver_version,
               c.solver_status, c.objective_value, e.simulator_version, e.valid,
               e.metrics, e.violations, e.rank, e.recommended
        FROM airline_recovery_candidates c
        JOIN airline_candidate_evaluations e USING (candidate_id)
        WHERE c.batch_id = %s
        ORDER BY e.rank NULLS LAST, c.candidate_id
        """,
        (batch["batch_id"],),
    ).fetchall()
    return {**batch, "candidates": list(candidates)}


def _persist_impacts(
    connection: DbConnection,
    snapshot: WorldSnapshot,
    impacts: Iterable[OperationalImpact],
) -> None:
    _executemany(
        connection,
        """
        INSERT INTO airline_operational_impacts(
            impact_id, world_id, world_revision, entity_type, entity_id, reason,
            depth, root_disruption_id, source_entity_type, source_entity_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                uuid5(
                    snapshot.world_id,
                    f"{snapshot.revision}:{impact.entity_type}:{impact.entity_id}:"
                    f"{impact.root_disruption_id}:{impact.reason}",
                ),
                snapshot.world_id,
                snapshot.revision,
                impact.entity_type,
                impact.entity_id,
                impact.reason,
                impact.depth,
                impact.root_disruption_id,
                impact.source_entity_type,
                impact.source_entity_id,
            )
            for impact in impacts
        ],
    )


def _scenario_result(
    connection: DbConnection,
    invocation: DbRow,
    *,
    replayed: bool,
) -> ScenarioResult:
    disruption_rows = connection.execute(
        "SELECT disruption_id FROM airline_disruptions WHERE invocation_id = %s ORDER BY disruption_id",
        (invocation["invocation_id"],),
    ).fetchall()
    impact_rows = connection.execute(
        """
        SELECT entity_type, entity_id, reason, depth, root_disruption_id,
               source_entity_type, source_entity_id
        FROM airline_operational_impacts
        WHERE world_id = %s AND world_revision = %s
        ORDER BY root_disruption_id, depth, entity_type, entity_id, reason
        """,
        (invocation["world_id"], invocation["applied_revision"]),
    ).fetchall()
    return ScenarioResult(
        world_id=invocation["world_id"],
        world_revision=invocation["applied_revision"],
        scenario_key=invocation["scenario_key"],
        scenario_invocation_id=invocation["invocation_id"],
        disruption_ids=tuple(row["disruption_id"] for row in disruption_rows),
        impacts=tuple(
            OperationalImpact(
                row["entity_type"],
                row["entity_id"],
                row["reason"],
                row["depth"],
                row["root_disruption_id"],
                row["source_entity_type"],
                row["source_entity_id"],
            )
            for row in impact_rows
        ),
        replayed=replayed,
    )


def trigger_hero_scenario(
    connection: DbConnection,
    world_id: UUID,
    *,
    idempotency_key: str,
) -> ScenarioResult:
    if not idempotency_key.strip():
        raise ValueError("idempotency_key is required")
    with connection.transaction():
        existing = connection.execute(
            "SELECT * FROM airline_scenario_invocations WHERE world_id = %s AND idempotency_key = %s",
            (world_id, idempotency_key),
        ).fetchone()
        if existing is not None:
            if existing["scenario_key"] != HERO_SCENARIO_KEY or existing["applied_revision"] is None:
                raise ValueError("idempotency key is already in use")
            return _scenario_result(connection, existing, replayed=True)

        world = connection.execute(
            "SELECT * FROM airline_worlds WHERE world_id = %s FOR UPDATE",
            (world_id,),
        ).fetchone()
        if world is None:
            raise KeyError(f"Unknown world {world_id}")
        if world["state"] != "active" or world["expires_at"] <= datetime.now(UTC):
            raise ValueError("world is not active")

        invocation_id = uuid4()
        revision = int(world["revision"]) + 1
        connection.execute(
            """
            INSERT INTO airline_scenario_invocations(
                invocation_id, world_id, scenario_key, idempotency_key, applied_revision
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (invocation_id, world_id, HERO_SCENARIO_KEY, idempotency_key, revision),
        )
        scenario_start = baseline.BASELINE_CLOCK.replace(hour=4, minute=0)
        capacity_disruption_id = uuid5(invocation_id, "airport-capacity")
        aircraft_disruption_id = uuid5(invocation_id, "aircraft-unavailable")
        _executemany(
            connection,
            """
            INSERT INTO airline_disruptions(
                disruption_id, world_id, invocation_id, kind, airport_code,
                aircraft_id, starts_at, ends_at, capacity_multiplier
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    capacity_disruption_id,
                    world_id,
                    invocation_id,
                    "airport_capacity",
                    "BOM",
                    None,
                    scenario_start,
                    scenario_start + timedelta(hours=4),
                    0.4,
                ),
                (
                    aircraft_disruption_id,
                    world_id,
                    invocation_id,
                    "aircraft_unavailable",
                    None,
                    "ALN-A03",
                    scenario_start,
                    scenario_start + timedelta(hours=8),
                    None,
                ),
            ],
        )
        connection.execute(
            """
            UPDATE airline_aircraft
            SET status = 'unavailable', available_from = %s
            WHERE world_id = %s AND aircraft_id = 'ALN-A03'
            """,
            (scenario_start + timedelta(hours=8), world_id),
        )
        connection.execute(
            "UPDATE airline_worlds SET revision = %s, simulation_clock = %s WHERE world_id = %s",
            (revision, scenario_start, world_id),
        )
        snapshot = load_snapshot(connection, world_id)
        impacts = calculate_operational_impacts(snapshot)
        _persist_impacts(connection, snapshot, impacts)
        impacted_flights = sorted({impact.entity_id for impact in impacts if impact.entity_type == "flight"})
        if impacted_flights:
            connection.execute(
                "UPDATE airline_flights SET status = 'at_risk' WHERE world_id = %s AND flight_id = ANY(%s)",
                (world_id, impacted_flights),
            )
        passenger_sizes = {party.party_id: party.party_size for party in snapshot.passenger_parties}
        _append_event(
            connection,
            world_id,
            "scenario.triggered",
            revision,
            {
                "scenarioKey": HERO_SCENARIO_KEY,
                "invocationId": str(invocation_id),
                "disruptionIds": [str(capacity_disruption_id), str(aircraft_disruption_id)],
            },
        )
        _append_event(
            connection,
            world_id,
            "world.recalculated",
            revision,
            {
                "flightCount": len(impacted_flights),
                "crewCount": len({impact.entity_id for impact in impacts if impact.entity_type == "crew"}),
                "passengerCount": sum(
                    passenger_sizes[party_id]
                    for party_id in {
                        impact.entity_id for impact in impacts if impact.entity_type == "passenger_party"
                    }
                ),
                "maximumDependencyDepth": max((impact.depth for impact in impacts), default=0),
            },
        )
        invocation = connection.execute(
            "SELECT * FROM airline_scenario_invocations WHERE invocation_id = %s",
            (invocation_id,),
        ).fetchone()
        if invocation is None:
            raise RuntimeError("scenario invocation was not persisted")
        return _scenario_result(connection, invocation, replayed=False)


def reset_world(connection: DbConnection, world_id: UUID, *, idempotency_key: str) -> int:
    if not idempotency_key.strip():
        raise ValueError("idempotency_key is required")
    with connection.transaction():
        existing = connection.execute(
            "SELECT * FROM airline_scenario_invocations WHERE world_id = %s AND idempotency_key = %s",
            (world_id, idempotency_key),
        ).fetchone()
        if existing is not None:
            if existing["scenario_key"] != "reset" or existing["applied_revision"] is None:
                raise ValueError("idempotency key is already in use")
            return int(existing["applied_revision"])
        world = connection.execute(
            "SELECT * FROM airline_worlds WHERE world_id = %s FOR UPDATE",
            (world_id,),
        ).fetchone()
        if world is None:
            raise KeyError(f"Unknown world {world_id}")
        revision = int(world["revision"]) + 1
        connection.execute(
            "UPDATE airline_disruptions SET active = false WHERE world_id = %s AND active",
            (world_id,),
        )
        connection.execute("DELETE FROM airline_itinerary_legs WHERE world_id = %s", (world_id,))
        connection.execute("DELETE FROM airline_passenger_parties WHERE world_id = %s", (world_id,))
        connection.execute("DELETE FROM airline_crew_assignments WHERE world_id = %s", (world_id,))
        connection.execute("DELETE FROM airline_crew WHERE world_id = %s", (world_id,))
        connection.execute("DELETE FROM airline_flights WHERE world_id = %s", (world_id,))
        connection.execute(
            """
            UPDATE airline_worlds
            SET revision = %s, baseline_version = %s, simulation_clock = %s, state = 'active'
            WHERE world_id = %s
            """,
            (revision, baseline.BASELINE_VERSION, baseline.BASELINE_CLOCK, world_id),
        )
        _seed_world(connection, world_id)
        validate_world(load_snapshot(connection, world_id))
        invocation_id = uuid4()
        connection.execute(
            """
            INSERT INTO airline_scenario_invocations(
                invocation_id, world_id, scenario_key, idempotency_key, applied_revision
            ) VALUES (%s, %s, 'reset', %s, %s)
            """,
            (invocation_id, world_id, idempotency_key, revision),
        )
        _append_event(
            connection,
            world_id,
            "world.reset",
            revision,
            {"baselineVersion": baseline.BASELINE_VERSION, "invocationId": str(invocation_id)},
        )
        return revision


def events_after(connection: DbConnection, world_id: UUID, sequence: int = 0) -> list[DbRow]:
    rows = connection.execute(
        """
        SELECT sequence, event_type, world_revision, payload, created_at
        FROM airline_world_events
        WHERE world_id = %s AND sequence > %s
        ORDER BY sequence
        """,
        (world_id, sequence),
    ).fetchall()
    return [
        {
            "sequence": row["sequence"],
            "eventType": row["event_type"],
            "worldRevision": row["world_revision"],
            "payload": row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"]),
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


def persist_recovery_batch(
    connection: DbConnection,
    snapshot: WorldSnapshot,
    candidates: tuple[CandidatePlan, ...],
    evaluations: tuple[CandidateEvaluation, ...],
    ranked: tuple[CandidateEvaluation, ...],
) -> UUID:
    if not candidates:
        raise ValueError("Cannot persist an empty recovery batch")
    digest = snapshot_hash(snapshot)
    candidate_ids = {candidate.candidate_id for candidate in candidates}
    evaluation_ids = {evaluation.candidate_id for evaluation in evaluations}
    ranked_ids = [evaluation.candidate_id for evaluation in ranked]
    if evaluation_ids != candidate_ids:
        raise ValueError("Every candidate must have exactly one evaluation")
    if any(candidate.snapshot_hash != digest for candidate in candidates):
        raise ValueError("Candidate snapshot hash does not match the authoritative snapshot")
    if any(evaluation.snapshot_hash != digest for evaluation in evaluations):
        raise ValueError("Evaluation snapshot hash does not match the authoritative snapshot")
    if set(ranked_ids) != {evaluation.candidate_id for evaluation in evaluations if evaluation.valid}:
        raise ValueError("Ranked results must contain every valid candidate and no invalid candidate")
    artifact_hashes = {candidate.artifact_hash for candidate in candidates}
    if len(artifact_hashes) != 1:
        raise ValueError("A recovery batch must come from one generated artifact")
    artifact_hash = next(iter(artifact_hashes))
    batch_name = f"{snapshot.revision}:{artifact_hash}:{':'.join(sorted(candidate_ids))}"
    batch_id = uuid5(snapshot.world_id, batch_name)
    rank_by_candidate = {candidate_id: index for index, candidate_id in enumerate(ranked_ids, start=1)}
    evaluation_by_candidate = {evaluation.candidate_id: evaluation for evaluation in evaluations}

    with connection.transaction():
        existing_batch = connection.execute(
            "SELECT 1 FROM airline_recovery_batches WHERE batch_id = %s",
            (batch_id,),
        ).fetchone()
        if existing_batch is not None:
            return batch_id
        connection.execute(
            """
            INSERT INTO airline_recovery_snapshots(snapshot_hash, world_id, world_revision, payload)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (snapshot_hash) DO NOTHING
            """,
            (digest, snapshot.world_id, snapshot.revision, Jsonb(snapshot_payload(snapshot))),
        )
        connection.execute(
            """
            INSERT INTO airline_recovery_batches(
                batch_id, world_id, world_revision, snapshot_hash, artifact_hash, ranking_version
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (batch_id) DO NOTHING
            """,
            (
                batch_id,
                snapshot.world_id,
                snapshot.revision,
                digest,
                artifact_hash,
                RANKING_VERSION,
            ),
        )
        for candidate in candidates:
            connection.execute(
                """
                INSERT INTO airline_recovery_candidates(
                    candidate_id, batch_id, world_id, world_revision, snapshot_hash,
                    artifact_hash, strategy_parameters, actions, solver_version,
                    solver_status, objective_value
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (candidate_id) DO NOTHING
                """,
                (
                    candidate.candidate_id,
                    batch_id,
                    snapshot.world_id,
                    snapshot.revision,
                    digest,
                    candidate.artifact_hash,
                    Jsonb(asdict(candidate.strategy)),
                    Jsonb([action_payload(action) for action in candidate.actions]),
                    candidate.solver_version,
                    candidate.solver_status,
                    candidate.objective_value,
                ),
            )
            evaluation = evaluation_by_candidate[candidate.candidate_id]
            rank = rank_by_candidate.get(candidate.candidate_id)
            connection.execute(
                """
                INSERT INTO airline_candidate_evaluations(
                    candidate_id, simulator_version, valid, metrics, violations,
                    rank, recommended
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (candidate_id) DO UPDATE SET
                    simulator_version = EXCLUDED.simulator_version,
                    valid = EXCLUDED.valid,
                    metrics = EXCLUDED.metrics,
                    violations = EXCLUDED.violations,
                    rank = EXCLUDED.rank,
                    recommended = EXCLUDED.recommended,
                    evaluated_at = now()
                """,
                (
                    candidate.candidate_id,
                    evaluation.simulator_version,
                    evaluation.valid,
                    Jsonb(asdict(evaluation.metrics)),
                    Jsonb([asdict(violation) for violation in evaluation.violations]),
                    rank,
                    rank == 1,
                ),
            )
        _append_event(
            connection,
            snapshot.world_id,
            "recovery.candidates_evaluated",
            snapshot.revision,
            {
                "batchId": str(batch_id),
                "candidateCount": len(candidates),
                "validCandidateCount": len(ranked),
                "recommendedCandidateId": ranked[0].candidate_id if ranked else None,
                "snapshotHash": digest,
                "artifactHash": artifact_hash,
                "simulatorVersion": evaluations[0].simulator_version,
                "rankingVersion": RANKING_VERSION,
            },
        )
    return batch_id
