from uuid import UUID, uuid5

from airstrong_airline import baseline
from airstrong_airline.engine import calculate_operational_impacts
from airstrong_airline.models import Disruption, WorldSnapshot


def disrupted_snapshot() -> WorldSnapshot:
    world_id = UUID("11111111-1111-1111-1111-111111111111")
    start = baseline.BASELINE_CLOCK.replace(hour=4, minute=0)
    disruptions = (
        Disruption(
            uuid5(world_id, "capacity"), "airport_capacity", "BOM", start, start.replace(hour=8), 0.4, None
        ),
        Disruption(
            uuid5(world_id, "aircraft"),
            "aircraft_unavailable",
            None,
            start,
            start.replace(hour=12),
            None,
            "ALN-A03",
        ),
    )
    return WorldSnapshot(
        world_id=world_id,
        revision=1,
        airports=baseline.AIRPORTS,
        aircraft=baseline.AIRCRAFT,
        flights=baseline.FLIGHTS,
        crew=baseline.CREW,
        crew_assignments=baseline.CREW_ASSIGNMENTS,
        passenger_parties=baseline.PASSENGER_PARTIES,
        itinerary_legs=baseline.ITINERARY_LEGS,
        disruptions=disruptions,
    )


def test_engine_discovers_roots_and_downstream_dependencies() -> None:
    impacts = calculate_operational_impacts(disrupted_snapshot())

    assert {impact.entity_type for impact in impacts} == {"flight", "crew", "passenger_party"}
    assert any(impact.reason == "direct_disruption" for impact in impacts)
    assert any(impact.reason == "downstream_aircraft_rotation" for impact in impacts)
    assert max(impact.depth for impact in impacts) >= 2


def test_engine_is_deterministic_for_an_identical_snapshot() -> None:
    snapshot = disrupted_snapshot()

    assert calculate_operational_impacts(snapshot) == calculate_operational_impacts(snapshot)
