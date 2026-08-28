from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime
from typing import Any
from uuid import UUID

from .database import (
    DbConnection,
    latest_recovery_batch,
    load_impacts,
    load_snapshot,
    load_world,
    recovery_runs_for_world,
)

_SNAKE_PART = re.compile(r"_([a-z])")


def _camel_name(value: str) -> str:
    return _SNAKE_PART.sub(lambda match: match.group(1).upper(), value)


def public_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, tuple | list):
        return [public_value(item) for item in value]
    if isinstance(value, dict):
        return {_camel_name(str(key)): public_value(item) for key, item in value.items()}
    return value


def world_view(connection: DbConnection, world_id: UUID) -> dict[str, Any]:
    world = load_world(connection, world_id)
    snapshot = load_snapshot(connection, world_id)
    return public_value(
        {
            **world,
            "counts": {
                "flights": len(snapshot.flights),
                "aircraft": len(snapshot.aircraft),
                "crew": len(snapshot.crew),
                "passenger_parties": len(snapshot.passenger_parties),
                "passengers": sum(party.party_size for party in snapshot.passenger_parties),
                "airports": len(snapshot.airports),
                "disruptions": len(snapshot.disruptions),
            },
        }
    )


def snapshot_view(connection: DbConnection, world_id: UUID) -> dict[str, Any]:
    snapshot = load_snapshot(connection, world_id)
    impacts = load_impacts(connection, world_id, revision=snapshot.revision)
    return public_value({**asdict(snapshot), "operational_impacts": [asdict(item) for item in impacts]})


def data_view(connection: DbConnection, world_id: UUID, section: str) -> list[dict[str, Any]]:
    snapshot = load_snapshot(connection, world_id)
    values: tuple[Any, ...]
    if section == "flights":
        values = snapshot.flights
    elif section == "aircraft":
        values = snapshot.aircraft
    elif section == "crew":
        assignments: dict[str, list[str]] = {}
        for assignment in snapshot.crew_assignments:
            assignments.setdefault(assignment.crew_id, []).append(assignment.flight_id)
        return [
            public_value({**asdict(member), "flight_ids": sorted(assignments.get(member.crew_id, []))})
            for member in snapshot.crew
        ]
    elif section == "passengers":
        legs: dict[str, list[dict[str, Any]]] = {}
        for leg in snapshot.itinerary_legs:
            legs.setdefault(leg.party_id, []).append(asdict(leg))
        return [
            public_value(
                {
                    **asdict(party),
                    "itinerary": sorted(legs.get(party.party_id, []), key=lambda item: item["leg_order"]),
                }
            )
            for party in snapshot.passenger_parties
        ]
    elif section == "airports":
        values = snapshot.airports
    elif section == "disruptions":
        values = snapshot.disruptions
    else:
        raise ValueError(f"Unknown data section {section}")
    return [public_value(asdict(value)) for value in values]


def aircraft_investigation(connection: DbConnection, world_id: UUID) -> dict[str, Any]:
    snapshot = load_snapshot(connection, world_id)
    impacts = load_impacts(connection, world_id, revision=snapshot.revision)
    impacted_flights = {item.entity_id for item in impacts if item.entity_type == "flight"}
    flights_by_aircraft: dict[str, list[str]] = {}
    for flight in snapshot.flights:
        if flight.flight_id in impacted_flights:
            flights_by_aircraft.setdefault(flight.aircraft_id, []).append(flight.flight_id)
    scheduled_aircraft = {flight.aircraft_id for flight in snapshot.flights}
    return public_value(
        {
            "world_id": world_id,
            "world_revision": snapshot.revision,
            "unavailable_aircraft": [
                asdict(item) for item in snapshot.aircraft if item.status == "unavailable"
            ],
            "impacted_rotations": [
                {"aircraft_id": aircraft_id, "flight_ids": sorted(flight_ids)}
                for aircraft_id, flight_ids in sorted(flights_by_aircraft.items())
            ],
            "unscheduled_available_aircraft": [
                asdict(item)
                for item in snapshot.aircraft
                if item.status == "available" and item.aircraft_id not in scheduled_aircraft
            ],
        }
    )


def crew_investigation(connection: DbConnection, world_id: UUID) -> dict[str, Any]:
    world = load_world(connection, world_id)
    snapshot = load_snapshot(connection, world_id)
    impacts = load_impacts(connection, world_id, revision=snapshot.revision)
    impacted_ids = {item.entity_id for item in impacts if item.entity_type == "crew"}
    assignments: dict[str, list[str]] = {}
    for assignment in snapshot.crew_assignments:
        assignments.setdefault(assignment.crew_id, []).append(assignment.flight_id)
    return public_value(
        {
            "world_id": world_id,
            "world_revision": snapshot.revision,
            "crew": [
                {
                    **asdict(member),
                    "flight_ids": sorted(assignments.get(member.crew_id, [])),
                    "remaining_duty_minutes": max(
                        0,
                        int((member.duty_end - world["simulation_clock"]).total_seconds() // 60),
                    ),
                }
                for member in snapshot.crew
                if member.crew_id in impacted_ids
            ],
        }
    )


def passenger_investigation(connection: DbConnection, world_id: UUID) -> dict[str, Any]:
    snapshot = load_snapshot(connection, world_id)
    impacts = load_impacts(connection, world_id, revision=snapshot.revision)
    impacted_ids = {item.entity_id for item in impacts if item.entity_type == "passenger_party"}
    legs: dict[str, list[dict[str, Any]]] = {}
    for leg in snapshot.itinerary_legs:
        legs.setdefault(leg.party_id, []).append(asdict(leg))
    parties = [party for party in snapshot.passenger_parties if party.party_id in impacted_ids]
    return public_value(
        {
            "world_id": world_id,
            "world_revision": snapshot.revision,
            "passenger_count": sum(party.party_size for party in parties),
            "parties": [
                {
                    **asdict(party),
                    "itinerary": sorted(legs.get(party.party_id, []), key=lambda item: item["leg_order"]),
                }
                for party in parties
            ],
        }
    )


def recovery_batch_view(connection: DbConnection, world_id: UUID) -> dict[str, Any] | None:
    batch = latest_recovery_batch(connection, world_id)
    return None if batch is None else public_value(batch)


def recovery_runs_view(connection: DbConnection, world_id: UUID) -> list[dict[str, Any]]:
    return [public_value(run) for run in recovery_runs_for_world(connection, world_id)]
