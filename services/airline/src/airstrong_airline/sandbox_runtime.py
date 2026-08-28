from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
from itertools import product
from typing import Any
from uuid import UUID

from .models import (
    Aircraft,
    Airport,
    CrewAssignment,
    CrewMember,
    Disruption,
    Flight,
    ItineraryLeg,
    PassengerParty,
    WorldSnapshot,
)
from .recovery import CandidatePlan, StrategyParameters, action_payload
from .solver_primitives import CandidateDiversityError, RecoverySolverError, solve_candidate


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def snapshot_from_public_payload(payload: dict[str, Any]) -> WorldSnapshot:
    return WorldSnapshot(
        world_id=UUID(payload["worldId"]),
        revision=int(payload["revision"]),
        airports=tuple(
            Airport(
                code=item["code"],
                name=item["name"],
                city=item["city"],
                country_code=item["countryCode"],
                timezone=item["timezone"],
                latitude=float(item["latitude"]),
                longitude=float(item["longitude"]),
                hourly_capacity=int(item["hourlyCapacity"]),
                domestic_connection_minutes=int(item["domesticConnectionMinutes"]),
                international_connection_minutes=int(item["internationalConnectionMinutes"]),
            )
            for item in payload["airports"]
        ),
        aircraft=tuple(
            Aircraft(
                aircraft_id=item["aircraftId"],
                aircraft_type=item["aircraftType"],
                seats=int(item["seats"]),
                location_airport=item["locationAirport"],
                status=item["status"],
                available_from=_datetime(item["availableFrom"]),
                minimum_turnaround_minutes=int(item["minimumTurnaroundMinutes"]),
            )
            for item in payload["aircraft"]
        ),
        flights=tuple(
            Flight(
                flight_id=item["flightId"],
                origin=item["origin"],
                destination=item["destination"],
                scheduled_departure=_datetime(item["scheduledDeparture"]),
                scheduled_arrival=_datetime(item["scheduledArrival"]),
                aircraft_id=item["aircraftId"],
                aircraft_type=item["aircraftType"],
                capacity=int(item["capacity"]),
                status=item["status"],
            )
            for item in payload["flights"]
        ),
        crew=tuple(
            CrewMember(
                crew_id=item["crewId"],
                role=item["role"],
                base_airport=item["baseAirport"],
                qualifications=tuple(item["qualifications"]),
                duty_start=_datetime(item["dutyStart"]),
                duty_end=_datetime(item["dutyEnd"]),
                previous_duty_end=_datetime(item["previousDutyEnd"]),
            )
            for item in payload["crew"]
        ),
        crew_assignments=tuple(
            CrewAssignment(
                crew_id=item["crewId"],
                flight_id=item["flightId"],
                role=item["role"],
            )
            for item in payload["crewAssignments"]
        ),
        passenger_parties=tuple(
            PassengerParty(party_id=item["partyId"], party_size=int(item["partySize"]))
            for item in payload["passengerParties"]
        ),
        itinerary_legs=tuple(
            ItineraryLeg(
                party_id=item["partyId"],
                flight_id=item["flightId"],
                leg_order=int(item["legOrder"]),
            )
            for item in payload["itineraryLegs"]
        ),
        disruptions=tuple(
            Disruption(
                disruption_id=UUID(item["disruptionId"]),
                kind=item["kind"],
                airport_code=item.get("airportCode"),
                starts_at=_datetime(item["startsAt"]),
                ends_at=_datetime(item["endsAt"]),
                capacity_multiplier=(
                    None if item.get("capacityMultiplier") is None else float(item["capacityMultiplier"])
                ),
                aircraft_id=item.get("aircraftId"),
            )
            for item in payload["disruptions"]
        ),
    )


def candidate_payload(candidate: CandidatePlan) -> dict[str, Any]:
    return {
        "candidateId": candidate.candidate_id,
        "strategy": asdict(candidate.strategy),
        "snapshotHash": candidate.snapshot_hash,
        "artifactHash": candidate.artifact_hash,
        "solverVersion": candidate.solver_version,
        "scopeFlightIds": list(candidate.scope_flight_ids),
        "actions": [action_payload(action) for action in candidate.actions],
        "solverStatus": candidate.solver_status,
        "objectiveValue": candidate.objective_value,
    }


def solve_recovery_problem(
    snapshot_payload: dict[str, Any],
    scope_flight_ids: list[str],
    strategy_payloads: list[dict[str, Any]],
    artifact_hash: str,
) -> dict[str, Any]:
    snapshot = snapshot_from_public_payload(snapshot_payload)
    if len(strategy_payloads) < 3:
        raise ValueError("At least three strategy proposals are required")
    proposals = [StrategyParameters(**item) for item in strategy_payloads]
    scope_size = len(set(scope_flight_ids))
    disruption_minutes = max(
        (int((item.ends_at - item.starts_at).total_seconds() // 60) for item in snapshot.disruptions),
        default=60,
    )
    delay_limits = sorted(
        {
            0,
            60,
            120,
            ((disruption_minutes + 14) // 15) * 15,
            ((disruption_minutes * 2 + 14) // 15) * 15,
            *(item.max_delay_minutes for item in proposals),
        }
    )
    cancellation_limits = sorted(
        {
            0,
            min(1, scope_size),
            scope_size // 2,
            scope_size,
            *(min(scope_size, item.max_cancellations) for item in proposals),
        }
    )
    variants = list(proposals)
    for variant_number, (
        proposal,
        max_cancellations,
        max_delay_minutes,
        substitution,
    ) in enumerate(
        product(
            proposals,
            cancellation_limits,
            delay_limits,
            (False, True),
        ),
        start=1,
    ):
        variants.append(
            replace(
                proposal,
                strategy_id=f"{proposal.strategy_id}-derived-{variant_number:03d}",
                max_cancellations=max_cancellations,
                max_delay_minutes=max_delay_minutes,
                allow_aircraft_substitution=substitution,
            )
        )

    candidates: list[CandidatePlan] = []
    action_sets: set[tuple[tuple[str, str, str], ...]] = set()
    for strategy in variants:
        try:
            candidate = solve_candidate(
                snapshot,
                tuple(scope_flight_ids),
                strategy,
                artifact_hash=artifact_hash,
            )
        except RecoverySolverError:
            continue
        action_key = tuple(
            (action.action_type, action.flight_id, repr(action)) for action in candidate.actions
        )
        if action_key in action_sets:
            continue
        action_sets.add(action_key)
        candidates.append(candidate)
        if len(candidates) == 3:
            break
    if len(candidates) != 3:
        raise CandidateDiversityError(
            "Incident-specific parameter exploration did not produce three distinct candidate actions"
        )
    return {"candidates": [candidate_payload(candidate) for candidate in candidates]}


__all__ = ["candidate_payload", "snapshot_from_public_payload", "solve_recovery_problem"]
