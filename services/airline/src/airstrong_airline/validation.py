from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from .models import WorldSnapshot

MINIMUM_PRE_DUTY_REST = timedelta(hours=10)
MAXIMUM_SIMPLIFIED_DUTY = timedelta(hours=13)


class WorldValidationError(ValueError):
    pass


def validate_world(snapshot: WorldSnapshot) -> None:
    errors: list[str] = []
    airports = {airport.code: airport for airport in snapshot.airports}
    aircraft = {item.aircraft_id: item for item in snapshot.aircraft}
    flights = {flight.flight_id: flight for flight in snapshot.flights}
    crew = {member.crew_id: member for member in snapshot.crew}
    parties = {party.party_id: party for party in snapshot.passenger_parties}

    rotations: dict[str, list] = defaultdict(list)
    for flight in snapshot.flights:
        item = aircraft.get(flight.aircraft_id)
        if item is None:
            errors.append(f"{flight.flight_id}: unknown aircraft {flight.aircraft_id}")
            continue
        if flight.aircraft_type != item.aircraft_type:
            errors.append(f"{flight.flight_id}: aircraft type mismatch")
        if flight.capacity > item.seats:
            errors.append(f"{flight.flight_id}: capacity exceeds aircraft seats")
        rotations[flight.aircraft_id].append(flight)

    for aircraft_id, rotation in rotations.items():
        ordered = sorted(rotation, key=lambda flight: flight.scheduled_departure)
        if ordered and ordered[0].origin != aircraft[aircraft_id].location_airport:
            errors.append(f"{aircraft_id}: first flight is not at aircraft location")
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if previous.destination != current.origin:
                errors.append(f"{aircraft_id}: location discontinuity before {current.flight_id}")
            turnaround = current.scheduled_departure - previous.scheduled_arrival
            minimum = timedelta(minutes=aircraft[aircraft_id].minimum_turnaround_minutes)
            if turnaround < minimum:
                errors.append(f"{aircraft_id}: turnaround before {current.flight_id} is too short")

    assignments_by_flight: dict[str, list] = defaultdict(list)
    assignments_by_crew: dict[str, list] = defaultdict(list)
    for assignment in snapshot.crew_assignments:
        member = crew.get(assignment.crew_id)
        assigned_flight = flights.get(assignment.flight_id)
        if member is None or assigned_flight is None:
            errors.append(f"invalid crew assignment {assignment.crew_id}/{assignment.flight_id}")
            continue
        if assignment.role != member.role:
            errors.append(f"{assignment.crew_id}: assignment role mismatch")
        if assigned_flight.aircraft_type not in member.qualifications:
            errors.append(f"{assignment.crew_id}: not qualified for {assigned_flight.aircraft_type}")
        if (
            assigned_flight.scheduled_departure < member.duty_start
            or assigned_flight.scheduled_arrival > member.duty_end
        ):
            errors.append(f"{assignment.crew_id}: {assigned_flight.flight_id} falls outside duty window")
        assignments_by_flight[assigned_flight.flight_id].append(assignment)
        assignments_by_crew[assignment.crew_id].append(assigned_flight)

    for flight_id, assignments in assignments_by_flight.items():
        roles = [assignment.role for assignment in assignments]
        if roles.count("captain") != 1 or roles.count("first_officer") != 1 or roles.count("cabin") < 2:
            errors.append(f"{flight_id}: incomplete operating crew")
    for member in snapshot.crew:
        if member.duty_end - member.duty_start > MAXIMUM_SIMPLIFIED_DUTY:
            errors.append(f"{member.crew_id}: duty exceeds configured limit")
        if member.duty_start - member.previous_duty_end < MINIMUM_PRE_DUTY_REST:
            errors.append(f"{member.crew_id}: insufficient pre-duty rest")
        ordered = sorted(assignments_by_crew[member.crew_id], key=lambda flight: flight.scheduled_departure)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if previous.scheduled_arrival > current.scheduled_departure:
                errors.append(f"{member.crew_id}: overlapping flight assignments")

    legs_by_party: dict[str, list] = defaultdict(list)
    passenger_load: dict[str, int] = defaultdict(int)
    for leg in snapshot.itinerary_legs:
        if leg.party_id not in parties or leg.flight_id not in flights:
            errors.append(f"invalid itinerary leg {leg.party_id}/{leg.flight_id}")
            continue
        legs_by_party[leg.party_id].append(leg)
        passenger_load[leg.flight_id] += parties[leg.party_id].party_size
    for flight_id, load in passenger_load.items():
        if load > flights[flight_id].capacity:
            errors.append(f"{flight_id}: passenger load exceeds capacity")
    for party_id, legs in legs_by_party.items():
        ordered = sorted(legs, key=lambda leg: leg.leg_order)
        if [leg.leg_order for leg in ordered] != list(range(1, len(ordered) + 1)):
            errors.append(f"{party_id}: itinerary leg order is not contiguous")
        for previous_leg, current_leg in zip(ordered, ordered[1:], strict=False):
            previous = flights[previous_leg.flight_id]
            current = flights[current_leg.flight_id]
            if previous.destination != current.origin:
                errors.append(f"{party_id}: itinerary airport discontinuity")
                continue
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
            if current.scheduled_departure - previous.scheduled_arrival < timedelta(minutes=minimum_minutes):
                errors.append(f"{party_id}: connection at {airport.code} is too short")

    if errors:
        raise WorldValidationError("; ".join(sorted(errors)))
