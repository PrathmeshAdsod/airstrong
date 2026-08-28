from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .models import (
    Aircraft,
    Airport,
    CrewAssignment,
    CrewMember,
    CrewRole,
    Flight,
    ItineraryLeg,
    PassengerParty,
)

BASELINE_VERSION = "aliens-airline-2028-02-v1"
BASELINE_CLOCK = datetime(2028, 2, 12, 2, 0, tzinfo=UTC)


def _at(hour: int, minute: int = 0) -> datetime:
    return BASELINE_CLOCK.replace(hour=hour, minute=minute)


AIRPORTS = (
    Airport(
        "BOM",
        "Chhatrapati Shivaji Maharaj International",
        "Mumbai",
        "IN",
        "Asia/Kolkata",
        19.0896,
        72.8656,
        5,
        45,
        75,
    ),
    Airport("DEL", "Indira Gandhi International", "Delhi", "IN", "Asia/Kolkata", 28.5562, 77.1000, 5, 45, 75),
    Airport(
        "BLR", "Kempegowda International", "Bengaluru", "IN", "Asia/Kolkata", 13.1986, 77.7066, 4, 45, 75
    ),
    Airport(
        "CCU",
        "Netaji Subhas Chandra Bose International",
        "Kolkata",
        "IN",
        "Asia/Kolkata",
        22.6547,
        88.4467,
        4,
        45,
        75,
    ),
    Airport("DXB", "Dubai International", "Dubai", "AE", "Asia/Dubai", 25.2532, 55.3657, 6, 45, 75),
    Airport("SIN", "Singapore Changi", "Singapore", "SG", "Asia/Singapore", 1.3644, 103.9915, 6, 45, 75),
)

AIRCRAFT = (
    Aircraft("ALN-A01", "A320neo", 180, "DEL", "available", _at(0), 50),
    Aircraft("ALN-A02", "A320neo", 180, "BLR", "available", _at(0), 50),
    Aircraft("ALN-A03", "A321neo", 220, "BOM", "available", _at(0), 55),
    Aircraft("ALN-A04", "A321neo", 220, "SIN", "available", _at(0), 55),
    Aircraft("ALN-A05", "A320neo", 180, "DEL", "available", _at(0), 50),
    Aircraft("ALN-A06", "A321neo", 220, "BOM", "available", _at(0), 55),
)

FLIGHTS = (
    Flight("ALN-1001", "DEL", "BOM", _at(1, 0), _at(3, 10), "ALN-A01", "A320neo", 180),
    Flight("ALN-1002", "BOM", "BLR", _at(4, 20), _at(6, 0), "ALN-A01", "A320neo", 180),
    Flight("ALN-1003", "BLR", "BOM", _at(7, 0), _at(8, 40), "ALN-A01", "A320neo", 180),
    Flight("ALN-1004", "BOM", "DEL", _at(9, 40), _at(11, 50), "ALN-A01", "A320neo", 180),
    Flight("ALN-1011", "BLR", "BOM", _at(2, 0), _at(3, 40), "ALN-A02", "A320neo", 180),
    Flight("ALN-1012", "BOM", "CCU", _at(4, 40), _at(6, 50), "ALN-A02", "A320neo", 180),
    Flight("ALN-1013", "CCU", "BOM", _at(7, 50), _at(10, 10), "ALN-A02", "A320neo", 180),
    Flight("ALN-1014", "BOM", "BLR", _at(11, 10), _at(12, 50), "ALN-A02", "A320neo", 180),
    Flight("ALN-1021", "BOM", "DXB", _at(4, 15), _at(7, 20), "ALN-A03", "A321neo", 220),
    Flight("ALN-1022", "DXB", "BOM", _at(8, 30), _at(11, 35), "ALN-A03", "A321neo", 220),
    Flight("ALN-1023", "BOM", "DEL", _at(12, 50), _at(15, 0), "ALN-A03", "A321neo", 220),
    Flight("ALN-1031", "SIN", "BOM", _at(0, 0), _at(5, 20), "ALN-A04", "A321neo", 220),
    Flight("ALN-1032", "BOM", "SIN", _at(6, 30), _at(11, 50), "ALN-A04", "A321neo", 220),
    Flight("ALN-1041", "DEL", "CCU", _at(3, 0), _at(5, 10), "ALN-A05", "A320neo", 180),
    Flight("ALN-1042", "CCU", "BOM", _at(6, 0), _at(8, 20), "ALN-A05", "A320neo", 180),
    Flight("ALN-1043", "BOM", "DEL", _at(9, 20), _at(11, 30), "ALN-A05", "A320neo", 180),
)


def _crew() -> tuple[CrewMember, ...]:
    result: list[CrewMember] = []
    rotations = (
        ("R01", "DEL", "A320neo", _at(0, 20), _at(12, 20)),
        ("R02", "BLR", "A320neo", _at(1, 20), _at(13, 20)),
        ("R03", "BOM", "A321neo", _at(3, 35), _at(15, 25)),
        ("R04", "SIN", "A321neo", _at(0, 0) - timedelta(minutes=40), _at(12, 20)),
        ("R05", "DEL", "A320neo", _at(2, 20), _at(12, 0)),
    )
    roles: tuple[tuple[str, CrewRole], ...] = (
        ("C", "captain"),
        ("F", "first_officer"),
        ("A", "cabin"),
        ("B", "cabin"),
    )
    for prefix, base, qualification, duty_start, duty_end in rotations:
        for suffix, role in roles:
            result.append(
                CrewMember(
                    crew_id=f"ALN-{prefix}{suffix}",
                    role=role,
                    base_airport=base,
                    qualifications=(qualification,),
                    duty_start=duty_start,
                    duty_end=duty_end,
                    previous_duty_end=duty_start - timedelta(hours=12),
                )
            )
    return tuple(result)


CREW = _crew()


def _crew_assignments() -> tuple[CrewAssignment, ...]:
    by_aircraft = {
        "ALN-A01": "R01",
        "ALN-A02": "R02",
        "ALN-A03": "R03",
        "ALN-A04": "R04",
        "ALN-A05": "R05",
    }
    assignments: list[CrewAssignment] = []
    roles: tuple[tuple[str, CrewRole], ...] = (
        ("C", "captain"),
        ("F", "first_officer"),
        ("A", "cabin"),
        ("B", "cabin"),
    )
    for flight in FLIGHTS:
        prefix = by_aircraft[flight.aircraft_id]
        assignments.extend(
            CrewAssignment(f"ALN-{prefix}{suffix}", flight.flight_id, role) for suffix, role in roles
        )
    return tuple(assignments)


CREW_ASSIGNMENTS = _crew_assignments()


def _passenger_data() -> tuple[tuple[PassengerParty, ...], tuple[ItineraryLeg, ...]]:
    itineraries = (
        ("ALN-1001", "ALN-1002"),
        ("ALN-1001", "ALN-1032"),
        ("ALN-1011", "ALN-1012"),
        ("ALN-1011", "ALN-1032"),
        ("ALN-1021",),
        ("ALN-1022", "ALN-1023"),
        ("ALN-1031", "ALN-1004"),
        ("ALN-1031", "ALN-1014"),
        ("ALN-1041", "ALN-1042"),
        ("ALN-1042", "ALN-1043"),
        ("ALN-1002", "ALN-1003"),
        ("ALN-1012", "ALN-1013"),
        ("ALN-1032",),
        ("ALN-1004",),
        ("ALN-1014",),
        ("ALN-1023",),
    )
    parties: list[PassengerParty] = []
    legs: list[ItineraryLeg] = []
    for index, itinerary in enumerate(itineraries, start=1):
        party_id = f"ALN-PAX-{index:04d}"
        parties.append(PassengerParty(party_id, 1 + ((index * 7) % 4)))
        legs.extend(
            ItineraryLeg(party_id, flight_id, leg_order)
            for leg_order, flight_id in enumerate(itinerary, start=1)
        )
    return tuple(parties), tuple(legs)


PASSENGER_PARTIES, ITINERARY_LEGS = _passenger_data()
