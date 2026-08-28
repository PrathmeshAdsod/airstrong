from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from airstrong_airline.models import Aircraft, Airport, Disruption, Flight, WorldSnapshot
from airstrong_airline.recovery import StrategyParameters
from airstrong_airline.solver_primitives import solve_candidate


def test_substitution_cost_excludes_cancelled_flights() -> None:
    start = datetime(2028, 2, 12, 10, tzinfo=UTC)
    airport = Airport("AAA", "Alpha", "Alpha", "ZZ", "UTC", 0.0, 0.0, 2, 30, 45)
    snapshot = WorldSnapshot(
        world_id=uuid4(),
        revision=1,
        airports=(
            airport,
            Airport("BBB", "Beta", "Beta", "ZZ", "UTC", 1.0, 1.0, 2, 30, 45),
            Airport("CCC", "Gamma", "Gamma", "ZZ", "UTC", 2.0, 2.0, 2, 30, 45),
        ),
        aircraft=(
            Aircraft("ORIGINAL", "TYPE", 100, "AAA", "unavailable", start + timedelta(hours=2), 5),
            Aircraft("SPARE", "TYPE", 100, "AAA", "available", start, 5),
        ),
        flights=(
            Flight("ALN-0001", "AAA", "BBB", start, start + timedelta(minutes=10), "ORIGINAL", "TYPE", 100),
            Flight(
                "ALN-0002",
                "AAA",
                "CCC",
                start + timedelta(minutes=30),
                start + timedelta(minutes=50),
                "ORIGINAL",
                "TYPE",
                100,
            ),
        ),
        crew=(),
        crew_assignments=(),
        passenger_parties=(),
        itinerary_legs=(),
        disruptions=(
            Disruption(uuid4(), "airport_capacity", "AAA", start, start + timedelta(hours=1), 0.5, None),
        ),
    )
    strategy = StrategyParameters(
        strategy_id="objective-accounting-regression",
        max_cancellations=1,
        max_delay_minutes=0,
        allow_aircraft_substitution=True,
        cancellation_weight=10,
        passenger_preservation_weight=0,
        delay_weight=0,
        aircraft_reassignment_weight=7,
        stabilization_weight=0,
    )

    candidate = solve_candidate(
        snapshot,
        ("ALN-0001", "ALN-0002"),
        strategy,
        artifact_hash=hashlib.sha256(b"objective-accounting-regression").hexdigest(),
    )

    assert sum(action.action_type == "cancel_flight" for action in candidate.actions) == 1
    assert sum(action.action_type == "reassign_aircraft" for action in candidate.actions) == 1
    assert candidate.objective_value == 17
