from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import floor
from typing import Any

from .models import WorldSnapshot
from .recovery import (
    TWIN_VERSION,
    CancelFlight,
    CandidateEvaluation,
    CandidateMetrics,
    CandidatePlan,
    ReassignAircraft,
    RetimeFlight,
    Violation,
    snapshot_hash,
)
from .validation import MAXIMUM_SIMPLIFIED_DUTY, MINIMUM_PRE_DUTY_REST


@dataclass(slots=True)
class TwinFlight:
    flight_id: str
    origin: str
    destination: str
    departure: datetime
    arrival: datetime
    aircraft_id: str
    aircraft_type: str
    capacity: int
    cancelled: bool = False


def _violation(
    code: str,
    message: str,
    entity_type: str,
    entity_id: str,
    **facts: Any,
) -> Violation:
    return Violation(code, message, entity_type, entity_id, facts)


def _apply_candidate(
    snapshot: WorldSnapshot,
    candidate: CandidatePlan,
) -> tuple[dict[str, TwinFlight], list[Violation]]:
    flights = {
        flight.flight_id: TwinFlight(
            flight.flight_id,
            flight.origin,
            flight.destination,
            flight.scheduled_departure,
            flight.scheduled_arrival,
            flight.aircraft_id,
            flight.aircraft_type,
            flight.capacity,
        )
        for flight in snapshot.flights
    }
    aircraft = {item.aircraft_id: item for item in snapshot.aircraft}
    violations: list[Violation] = []
    action_types_by_flight: dict[str, set[str]] = defaultdict(set)
    for action in candidate.actions:
        flight = flights.get(action.flight_id)
        if flight is None:
            violations.append(
                _violation(
                    "UNKNOWN_FLIGHT",
                    "Candidate references a flight outside the snapshot.",
                    "flight",
                    action.flight_id,
                )
            )
            continue
        if action.action_type in action_types_by_flight[action.flight_id]:
            violations.append(
                _violation(
                    "DUPLICATE_ACTION",
                    "Candidate contains duplicate actions for a flight.",
                    "flight",
                    action.flight_id,
                    actionType=action.action_type,
                )
            )
            continue
        action_types_by_flight[action.flight_id].add(action.action_type)
        if isinstance(action, CancelFlight):
            flight.cancelled = True
        elif isinstance(action, RetimeFlight):
            if action.arrival <= action.departure:
                violations.append(
                    _violation(
                        "INVALID_FLIGHT_TIME",
                        "Retimed arrival must be after departure.",
                        "flight",
                        action.flight_id,
                    )
                )
            elif action.departure < flight.departure:
                violations.append(
                    _violation(
                        "EARLY_DEPARTURE",
                        "Recovery cannot move a flight earlier than its published schedule.",
                        "flight",
                        action.flight_id,
                    )
                )
            flight.departure = action.departure
            flight.arrival = action.arrival
        elif isinstance(action, ReassignAircraft):
            replacement = aircraft.get(action.aircraft_id)
            if replacement is None:
                violations.append(
                    _violation(
                        "UNKNOWN_AIRCRAFT",
                        "Candidate references an aircraft outside the snapshot.",
                        "aircraft",
                        action.aircraft_id,
                        flightId=action.flight_id,
                    )
                )
            else:
                flight.aircraft_id = replacement.aircraft_id
                flight.aircraft_type = replacement.aircraft_type
    for flight_id, action_types in action_types_by_flight.items():
        if "cancel_flight" in action_types and len(action_types) > 1:
            violations.append(
                _violation(
                    "CONFLICTING_ACTIONS",
                    "A cancelled flight cannot also be retimed or reassigned.",
                    "flight",
                    flight_id,
                    actionTypes=sorted(action_types),
                )
            )
    return flights, violations


def _aircraft_violations(snapshot: WorldSnapshot, flights: dict[str, TwinFlight]) -> list[Violation]:
    violations: list[Violation] = []
    aircraft = {item.aircraft_id: item for item in snapshot.aircraft}
    rotations: dict[str, list[TwinFlight]] = defaultdict(list)
    for flight in flights.values():
        if flight.cancelled:
            continue
        item = aircraft.get(flight.aircraft_id)
        if item is None:
            continue
        if item.aircraft_type != flight.aircraft_type:
            violations.append(
                _violation(
                    "AIRCRAFT_TYPE",
                    "Assigned aircraft type does not match the flight requirement.",
                    "flight",
                    flight.flight_id,
                    requiredType=flight.aircraft_type,
                    aircraftType=item.aircraft_type,
                )
            )
        if item.status == "unavailable" and flight.departure < item.available_from:
            violations.append(
                _violation(
                    "AIRCRAFT_UNAVAILABLE",
                    "Assigned aircraft is unavailable at departure.",
                    "flight",
                    flight.flight_id,
                    aircraftId=item.aircraft_id,
                    availableFrom=item.available_from.isoformat(),
                    departure=flight.departure.isoformat(),
                )
            )
        rotations[flight.aircraft_id].append(flight)

    for aircraft_id, rotation in rotations.items():
        item = aircraft[aircraft_id]
        ordered = sorted(rotation, key=lambda flight: (flight.departure, flight.flight_id))
        if ordered and ordered[0].origin != item.location_airport:
            violations.append(
                _violation(
                    "AIRCRAFT_LOCATION",
                    "Aircraft is not at the first departure airport.",
                    "flight",
                    ordered[0].flight_id,
                    aircraftId=aircraft_id,
                    expectedAirport=item.location_airport,
                    departureAirport=ordered[0].origin,
                )
            )
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if previous.destination != current.origin:
                violations.append(
                    _violation(
                        "DOWNSTREAM_ROTATION",
                        "Aircraft cannot reach the next departure airport.",
                        "flight",
                        current.flight_id,
                        aircraftId=aircraft_id,
                        previousFlightId=previous.flight_id,
                        previousDestination=previous.destination,
                        nextOrigin=current.origin,
                    )
                )
            minimum_departure = previous.arrival + timedelta(minutes=item.minimum_turnaround_minutes)
            if current.departure < minimum_departure:
                violations.append(
                    _violation(
                        "AIRCRAFT_TURNAROUND",
                        "Aircraft turnaround is shorter than its configured minimum.",
                        "flight",
                        current.flight_id,
                        aircraftId=aircraft_id,
                        minimumDeparture=minimum_departure.isoformat(),
                        departure=current.departure.isoformat(),
                    )
                )
    return violations


def _airport_violations(snapshot: WorldSnapshot, flights: dict[str, TwinFlight]) -> list[Violation]:
    violations: list[Violation] = []
    airports = {airport.code: airport for airport in snapshot.airports}
    for disruption in snapshot.disruptions:
        if disruption.kind not in {"airport_capacity", "runway_closure"}:
            continue
        if disruption.airport_code is None or disruption.capacity_multiplier is None:
            continue
        airport = airports[disruption.airport_code]
        permitted = max(1, floor(airport.hourly_capacity * disruption.capacity_multiplier))
        movements: dict[datetime, list[tuple[datetime, TwinFlight]]] = defaultdict(list)
        for flight in flights.values():
            if flight.cancelled:
                continue
            times = []
            if flight.origin == airport.code:
                times.append(flight.departure)
            if flight.destination == airport.code:
                times.append(flight.arrival)
            for movement_time in times:
                if disruption.starts_at <= movement_time < disruption.ends_at:
                    bucket = movement_time.replace(minute=0, second=0, microsecond=0)
                    movements[bucket].append((movement_time, flight))
        for bucket, bucket_movements in movements.items():
            ordered = sorted(bucket_movements, key=lambda item: (item[0], item[1].flight_id))
            for _, flight in ordered[permitted:]:
                violations.append(
                    _violation(
                        "AIRPORT_CAPACITY",
                        "Hourly airport movement capacity is exceeded.",
                        "flight",
                        flight.flight_id,
                        airportCode=airport.code,
                        bucket=bucket.isoformat(),
                        permittedMovements=permitted,
                        plannedMovements=len(ordered),
                    )
                )
    return violations


def _crew_violations(snapshot: WorldSnapshot, flights: dict[str, TwinFlight]) -> list[Violation]:
    violations: list[Violation] = []
    crew = {member.crew_id: member for member in snapshot.crew}
    aircraft = {item.aircraft_id: item for item in snapshot.aircraft}
    assignments: dict[str, list[TwinFlight]] = defaultdict(list)
    for assignment in snapshot.crew_assignments:
        flight = flights[assignment.flight_id]
        if flight.cancelled:
            continue
        member = crew[assignment.crew_id]
        assigned_type = aircraft[flight.aircraft_id].aircraft_type
        if assigned_type not in member.qualifications:
            violations.append(
                _violation(
                    "CREW_QUALIFICATION",
                    "Crew member is not qualified for the assigned aircraft type.",
                    "crew",
                    member.crew_id,
                    flightId=flight.flight_id,
                    aircraftType=assigned_type,
                )
            )
        if flight.departure < member.duty_start or flight.arrival > member.duty_end:
            violations.append(
                _violation(
                    "CREW_DUTY_WINDOW",
                    "Flight falls outside the stored crew duty window.",
                    "crew",
                    member.crew_id,
                    flightId=flight.flight_id,
                    dutyStart=member.duty_start.isoformat(),
                    dutyEnd=member.duty_end.isoformat(),
                    flightDeparture=flight.departure.isoformat(),
                    flightArrival=flight.arrival.isoformat(),
                )
            )
        assignments[member.crew_id].append(flight)

    for member in snapshot.crew:
        if member.duty_end - member.duty_start > MAXIMUM_SIMPLIFIED_DUTY:
            violations.append(
                _violation(
                    "CREW_DUTY_LIMIT",
                    "Stored duty exceeds the configured simplified duty limit.",
                    "crew",
                    member.crew_id,
                )
            )
        if member.duty_start - member.previous_duty_end < MINIMUM_PRE_DUTY_REST:
            violations.append(
                _violation(
                    "CREW_REST",
                    "Crew member has insufficient rest before duty.",
                    "crew",
                    member.crew_id,
                )
            )
        ordered = sorted(assignments[member.crew_id], key=lambda flight: (flight.departure, flight.flight_id))
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.departure < previous.arrival:
                violations.append(
                    _violation(
                        "CREW_OVERLAP",
                        "Crew member is assigned to overlapping flights.",
                        "crew",
                        member.crew_id,
                        previousFlightId=previous.flight_id,
                        nextFlightId=current.flight_id,
                    )
                )
    return violations


def _passenger_analysis(
    snapshot: WorldSnapshot,
    flights: dict[str, TwinFlight],
) -> tuple[list[Violation], set[str]]:
    violations: list[Violation] = []
    airports = {airport.code: airport for airport in snapshot.airports}
    parties = {party.party_id: party for party in snapshot.passenger_parties}
    load: dict[str, int] = defaultdict(int)
    legs_by_party: dict[str, list] = defaultdict(list)
    disrupted: set[str] = set()
    for leg in snapshot.itinerary_legs:
        legs_by_party[leg.party_id].append(leg)
        flight = flights[leg.flight_id]
        if flight.cancelled:
            disrupted.add(leg.party_id)
        else:
            load[leg.flight_id] += parties[leg.party_id].party_size
    for flight_id, passenger_count in load.items():
        flight = flights[flight_id]
        if passenger_count > flight.capacity:
            violations.append(
                _violation(
                    "PASSENGER_CAPACITY",
                    "Passenger load exceeds the assigned flight capacity.",
                    "flight",
                    flight_id,
                    passengerCount=passenger_count,
                    capacity=flight.capacity,
                )
            )
    for party_id, legs in legs_by_party.items():
        ordered = sorted(legs, key=lambda leg: leg.leg_order)
        if any(flights[leg.flight_id].cancelled for leg in ordered):
            continue
        for previous_leg, current_leg in zip(ordered, ordered[1:], strict=False):
            previous = flights[previous_leg.flight_id]
            current = flights[current_leg.flight_id]
            airport = airports[previous.destination]
            origin_country = airports[previous.origin].country_code
            destination_country = airports[current.destination].country_code
            international = (
                origin_country != airport.country_code or destination_country != airport.country_code
            )
            minimum_minutes = (
                airport.international_connection_minutes
                if international
                else airport.domestic_connection_minutes
            )
            available_minutes = int((current.departure - previous.arrival).total_seconds() // 60)
            if available_minutes < minimum_minutes:
                disrupted.add(party_id)
                violations.append(
                    _violation(
                        "PASSENGER_CONNECTION",
                        "Passenger connection is shorter than the configured minimum.",
                        "passenger_party",
                        party_id,
                        airportCode=airport.code,
                        previousFlightId=previous.flight_id,
                        nextFlightId=current.flight_id,
                        availableMinutes=available_minutes,
                        minimumMinutes=minimum_minutes,
                    )
                )
    return violations, disrupted


def evaluate_candidate(snapshot: WorldSnapshot, candidate: CandidatePlan) -> CandidateEvaluation:
    digest = snapshot_hash(snapshot)
    violations: list[Violation] = []
    if candidate.snapshot_hash != digest:
        violations.append(
            _violation(
                "STALE_SNAPSHOT",
                "Candidate was generated from a different authoritative snapshot.",
                "candidate",
                candidate.candidate_id,
                expectedSnapshotHash=digest,
                candidateSnapshotHash=candidate.snapshot_hash,
            )
        )
    flights, action_violations = _apply_candidate(snapshot, candidate)
    violations.extend(action_violations)
    violations.extend(_aircraft_violations(snapshot, flights))
    violations.extend(_airport_violations(snapshot, flights))
    violations.extend(_crew_violations(snapshot, flights))
    passenger_violations, disrupted_parties = _passenger_analysis(snapshot, flights)
    violations.extend(passenger_violations)

    original = {flight.flight_id: flight for flight in snapshot.flights}
    cancellations = {flight.flight_id for flight in flights.values() if flight.cancelled}
    party_sizes = {party.party_id: party.party_size for party in snapshot.passenger_parties}
    disrupted_passengers = sum(party_sizes[party_id] for party_id in disrupted_parties)
    total_delay = sum(
        max(0, int((flight.departure - original[flight.flight_id].scheduled_departure).total_seconds() // 60))
        for flight in flights.values()
        if not flight.cancelled
    )
    reassignments = sum(isinstance(action, ReassignAircraft) for action in candidate.actions)
    scope_arrivals = [
        flights[flight_id].arrival
        for flight_id in candidate.scope_flight_ids
        if not flights[flight_id].cancelled
    ]
    disruption_start = min((item.starts_at for item in snapshot.disruptions), default=min(scope_arrivals))
    stabilization = max(
        0,
        int((max(scope_arrivals, default=disruption_start) - disruption_start).total_seconds() // 60),
    )
    ordered_violations = tuple(
        sorted(
            violations,
            key=lambda item: (item.code, item.entity_type, item.entity_id, item.message),
        )
    )
    return CandidateEvaluation(
        candidate_id=candidate.candidate_id,
        snapshot_hash=digest,
        simulator_version=TWIN_VERSION,
        valid=not ordered_violations,
        metrics=CandidateMetrics(
            cancellations=len(cancellations),
            disrupted_passengers=disrupted_passengers,
            total_delay_minutes=total_delay,
            operational_reassignments=reassignments,
            stabilization_minutes=stabilization,
        ),
        violations=ordered_violations,
    )


def factual_replanning_feedback(evaluation: CandidateEvaluation) -> dict[str, Any]:
    return {
        "candidateId": evaluation.candidate_id,
        "valid": evaluation.valid,
        "simulatorVersion": evaluation.simulator_version,
        "violations": [
            {
                "code": violation.code,
                "entityType": violation.entity_type,
                "entityId": violation.entity_id,
                "message": violation.message,
                "facts": violation.facts,
            }
            for violation in evaluation.violations
        ],
    }
