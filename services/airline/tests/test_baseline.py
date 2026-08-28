from dataclasses import replace
from uuid import UUID

import pytest

from airstrong_airline import baseline
from airstrong_airline.models import WorldSnapshot
from airstrong_airline.validation import WorldValidationError, validate_world


def baseline_snapshot() -> WorldSnapshot:
    return WorldSnapshot(
        world_id=UUID(int=0),
        revision=0,
        airports=baseline.AIRPORTS,
        aircraft=baseline.AIRCRAFT,
        flights=baseline.FLIGHTS,
        crew=baseline.CREW,
        crew_assignments=baseline.CREW_ASSIGNMENTS,
        passenger_parties=baseline.PASSENGER_PARTIES,
        itinerary_legs=baseline.ITINERARY_LEGS,
        disruptions=(),
    )


def test_versioned_baseline_is_internally_coherent() -> None:
    snapshot = baseline_snapshot()

    validate_world(snapshot)

    assert baseline.BASELINE_VERSION == "aliens-airline-2028-02-v1"
    assert all(flight.flight_id.startswith("ALN-") for flight in snapshot.flights)
    assert len({flight.flight_id for flight in snapshot.flights}) == len(snapshot.flights)


def test_validation_rejects_an_impossible_aircraft_turnaround() -> None:
    snapshot = baseline_snapshot()
    target_flight_id = "ALN-1003"
    flights = tuple(
        replace(flight, scheduled_departure=flight.scheduled_departure.replace(hour=6, minute=10))
        if flight.flight_id == target_flight_id
        else flight
        for flight in snapshot.flights
    )
    isolated = replace(
        snapshot,
        flights=flights,
        crew_assignments=tuple(
            assignment for assignment in snapshot.crew_assignments if assignment.flight_id != target_flight_id
        ),
        itinerary_legs=tuple(leg for leg in snapshot.itinerary_legs if leg.flight_id != target_flight_id),
    )

    with pytest.raises(WorldValidationError) as raised:
        validate_world(isolated)

    assert str(raised.value) == "ALN-A01: turnaround before ALN-1003 is too short"


def test_validation_rejects_insufficient_pre_duty_rest() -> None:
    snapshot = baseline_snapshot()
    first = snapshot.crew[0]
    crew = (replace(first, previous_duty_end=first.duty_start), *snapshot.crew[1:])

    with pytest.raises(WorldValidationError, match="insufficient pre-duty rest"):
        validate_world(replace(snapshot, crew=crew))
