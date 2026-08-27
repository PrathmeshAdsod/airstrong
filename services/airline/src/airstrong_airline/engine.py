from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from math import floor

from .models import Disruption, Flight, OperationalImpact, WorldSnapshot


def _hour_bucket(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def _capacity_root_flights(snapshot: WorldSnapshot, disruption: Disruption) -> set[str]:
    if disruption.airport_code is None or disruption.capacity_multiplier is None:
        return set()
    airports = {airport.code: airport for airport in snapshot.airports}
    airport = airports[disruption.airport_code]
    permitted = max(1, floor(airport.hourly_capacity * disruption.capacity_multiplier))
    movements: dict[datetime, list[tuple[datetime, str]]] = defaultdict(list)
    for flight in snapshot.flights:
        if (
            flight.origin == disruption.airport_code
            and disruption.starts_at <= flight.scheduled_departure < disruption.ends_at
        ):
            movements[_hour_bucket(flight.scheduled_departure)].append(
                (flight.scheduled_departure, flight.flight_id)
            )
        if (
            flight.destination == disruption.airport_code
            and disruption.starts_at <= flight.scheduled_arrival < disruption.ends_at
        ):
            movements[_hour_bucket(flight.scheduled_arrival)].append(
                (flight.scheduled_arrival, flight.flight_id)
            )

    roots: set[str] = set()
    for bucket in sorted(movements):
        ordered = sorted(movements[bucket], key=lambda item: (item[0], item[1]))
        roots.update(flight_id for _, flight_id in ordered[permitted:])
    return roots


def _aircraft_root_flights(snapshot: WorldSnapshot, disruption: Disruption) -> set[str]:
    if disruption.aircraft_id is None:
        return set()
    return {
        flight.flight_id
        for flight in snapshot.flights
        if flight.aircraft_id == disruption.aircraft_id
        and disruption.starts_at <= flight.scheduled_departure < disruption.ends_at
    }


def _rotation_impacts(
    flights: Iterable[Flight],
    root_flight_ids: set[str],
    disruption: Disruption,
) -> list[OperationalImpact]:
    rotations: dict[str, list[Flight]] = defaultdict(list)
    for flight in flights:
        rotations[flight.aircraft_id].append(flight)
    impacts: dict[str, OperationalImpact] = {}
    for rotation in rotations.values():
        ordered = sorted(rotation, key=lambda flight: (flight.scheduled_departure, flight.flight_id))
        root_indexes = [index for index, flight in enumerate(ordered) if flight.flight_id in root_flight_ids]
        for root_index in root_indexes:
            for index in range(root_index, len(ordered)):
                flight = ordered[index]
                depth = index - root_index
                reason = "direct_disruption" if depth == 0 else "downstream_aircraft_rotation"
                candidate = OperationalImpact(
                    entity_type="flight",
                    entity_id=flight.flight_id,
                    reason=reason,
                    depth=depth,
                    root_disruption_id=disruption.disruption_id,
                    source_entity_type=None if depth == 0 else "flight",
                    source_entity_id=None if depth == 0 else ordered[index - 1].flight_id,
                )
                existing = impacts.get(flight.flight_id)
                if existing is None or (candidate.depth, candidate.reason) < (
                    existing.depth,
                    existing.reason,
                ):
                    impacts[flight.flight_id] = candidate
    return list(impacts.values())


def calculate_operational_impacts(snapshot: WorldSnapshot) -> tuple[OperationalImpact, ...]:
    impacts: list[OperationalImpact] = []
    for disruption in sorted(snapshot.disruptions, key=lambda item: str(item.disruption_id)):
        if disruption.kind in {"airport_capacity", "runway_closure"}:
            root_flights = _capacity_root_flights(snapshot, disruption)
        elif disruption.kind == "aircraft_unavailable":
            root_flights = _aircraft_root_flights(snapshot, disruption)
        else:
            root_flights = set()
        flight_impacts = _rotation_impacts(snapshot.flights, root_flights, disruption)
        impacts.extend(flight_impacts)

        by_flight = {impact.entity_id: impact for impact in flight_impacts}
        for assignment in snapshot.crew_assignments:
            source = by_flight.get(assignment.flight_id)
            if source is None:
                continue
            impacts.append(
                OperationalImpact(
                    entity_type="crew",
                    entity_id=assignment.crew_id,
                    reason="assigned_flight_impacted",
                    depth=source.depth + 1,
                    root_disruption_id=disruption.disruption_id,
                    source_entity_type="flight",
                    source_entity_id=assignment.flight_id,
                )
            )

        legs_by_party: dict[str, list] = defaultdict(list)
        for leg in snapshot.itinerary_legs:
            legs_by_party[leg.party_id].append(leg)
        for party_id, legs in legs_by_party.items():
            ordered_legs = sorted(legs, key=lambda leg: leg.leg_order)
            affected = [(leg, by_flight[leg.flight_id]) for leg in ordered_legs if leg.flight_id in by_flight]
            if not affected:
                continue
            first_leg, first_source = min(affected, key=lambda item: item[0].leg_order)
            impacts.append(
                OperationalImpact(
                    entity_type="passenger_party",
                    entity_id=party_id,
                    reason="itinerary_leg_impacted",
                    depth=first_source.depth + 1,
                    root_disruption_id=disruption.disruption_id,
                    source_entity_type="flight",
                    source_entity_id=first_leg.flight_id,
                )
            )

    unique: dict[tuple[str, str, str, str], OperationalImpact] = {}
    for impact in impacts:
        key = (impact.entity_type, impact.entity_id, str(impact.root_disruption_id), impact.reason)
        existing = unique.get(key)
        if existing is None or impact.depth < existing.depth:
            unique[key] = impact
    return tuple(
        sorted(
            unique.values(),
            key=lambda impact: (
                str(impact.root_disruption_id),
                impact.depth,
                impact.entity_type,
                impact.entity_id,
                impact.reason,
            ),
        )
    )
