from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from math import ceil, floor

from ortools.sat.python import cp_model

from .models import Flight, WorldSnapshot
from .recovery import (
    SOLVER_PRIMITIVES_VERSION,
    CancelFlight,
    CandidatePlan,
    ReassignAircraft,
    RecoveryAction,
    RetimeFlight,
    StrategyParameters,
    candidate_content_hash,
    snapshot_hash,
)


class RecoverySolverError(RuntimeError):
    pass


class CandidateDiversityError(RecoverySolverError):
    pass


def _minutes_from(origin: datetime, value: datetime) -> int:
    return int((value - origin).total_seconds() // 60)


def _party_load_by_flight(snapshot: WorldSnapshot) -> dict[str, int]:
    sizes = {party.party_id: party.party_size for party in snapshot.passenger_parties}
    result: dict[str, int] = defaultdict(int)
    for leg in snapshot.itinerary_legs:
        result[leg.flight_id] += sizes[leg.party_id]
    return result


def _eligible_rotation_aircraft(
    snapshot: WorldSnapshot,
    scoped_rotation: list[Flight],
    *,
    allow_substitution: bool,
) -> tuple[str, ...]:
    original_id = scoped_rotation[0].aircraft_id
    if not allow_substitution:
        return (original_id,)
    first = min(scoped_rotation, key=lambda flight: (flight.scheduled_departure, flight.flight_id))
    scoped_ids = {flight.flight_id for flight in scoped_rotation}
    eligible = [original_id]
    for aircraft in snapshot.aircraft:
        if aircraft.aircraft_id == original_id or aircraft.aircraft_type != first.aircraft_type:
            continue
        if aircraft.location_airport != first.origin:
            continue
        has_fixed_rotation = any(
            flight.aircraft_id == aircraft.aircraft_id and flight.flight_id not in scoped_ids
            for flight in snapshot.flights
        )
        if not has_fixed_rotation:
            eligible.append(aircraft.aircraft_id)
    return tuple(sorted(eligible))


def solve_candidate(
    snapshot: WorldSnapshot,
    scope_flight_ids: tuple[str, ...],
    strategy: StrategyParameters,
    *,
    artifact_hash: str,
) -> CandidatePlan:
    strategy.validate()
    if len(artifact_hash) != 64 or any(character not in "0123456789abcdef" for character in artifact_hash):
        raise ValueError("artifact_hash must be a lowercase SHA-256 digest")
    flight_by_id = {flight.flight_id: flight for flight in snapshot.flights}
    unknown = sorted(set(scope_flight_ids) - flight_by_id.keys())
    if unknown:
        raise ValueError(f"Unknown scope flights: {', '.join(unknown)}")
    scope = tuple(sorted(set(scope_flight_ids)))
    if not scope:
        raise ValueError("At least one scope flight is required")

    horizon_start = min(flight.scheduled_departure for flight in snapshot.flights)
    model = cp_model.CpModel()
    maximum_delay_slots = strategy.max_delay_minutes // 15
    cancellation: dict[str, cp_model.IntVar] = {}
    delay_slots: dict[str, cp_model.IntVar] = {}
    for flight_id in scope:
        cancellation[flight_id] = model.new_bool_var(f"cancel_{flight_id}")
        delay_slots[flight_id] = model.new_int_var(0, maximum_delay_slots, f"delay_{flight_id}")
        model.add(delay_slots[flight_id] == 0).only_enforce_if(cancellation[flight_id])
    model.add(sum(cancellation.values()) <= strategy.max_cancellations)

    scoped_by_rotation: dict[str, list[Flight]] = defaultdict(list)
    for flight_id in scope:
        scoped_by_rotation[flight_by_id[flight_id].aircraft_id].append(flight_by_id[flight_id])
    rotation_choice: dict[tuple[str, str], cp_model.IntVar] = {}
    aircraft_by_id = {aircraft.aircraft_id: aircraft for aircraft in snapshot.aircraft}
    for original_id, rotation in sorted(scoped_by_rotation.items()):
        eligible = _eligible_rotation_aircraft(
            snapshot,
            rotation,
            allow_substitution=strategy.allow_aircraft_substitution,
        )
        choices = []
        for aircraft_id in eligible:
            choice = model.new_bool_var(f"rotation_{original_id}_uses_{aircraft_id}")
            rotation_choice[(original_id, aircraft_id)] = choice
            choices.append(choice)
        model.add_exactly_one(choices)

        ordered = sorted(rotation, key=lambda flight: (flight.scheduled_departure, flight.flight_id))
        for previous, current in zip(ordered, ordered[1:], strict=False):
            required_gap = (
                _minutes_from(horizon_start, previous.scheduled_arrival)
                + aircraft_by_id[original_id].minimum_turnaround_minutes
            )
            current_departure = _minutes_from(horizon_start, current.scheduled_departure)
            model.add(
                current_departure + delay_slots[current.flight_id] * 15
                >= required_gap + delay_slots[previous.flight_id] * 15
            ).only_enforce_if(
                [cancellation[previous.flight_id].negated(), cancellation[current.flight_id].negated()]
            )

        for aircraft_id in eligible:
            available = aircraft_by_id[aircraft_id].available_from
            choice = rotation_choice[(original_id, aircraft_id)]
            for flight in ordered:
                required_delay = max(0, _minutes_from(flight.scheduled_departure, available))
                if required_delay:
                    model.add(delay_slots[flight.flight_id] * 15 >= required_delay).only_enforce_if(
                        [choice, cancellation[flight.flight_id].negated()]
                    )

    scoped_set = set(scope)
    airports = {airport.code: airport for airport in snapshot.airports}
    for disruption in snapshot.disruptions:
        if disruption.kind not in {"airport_capacity", "runway_closure"}:
            continue
        if disruption.airport_code is None or disruption.capacity_multiplier is None:
            continue
        permitted = max(
            1, floor(airports[disruption.airport_code].hourly_capacity * disruption.capacity_multiplier)
        )
        movements: dict[datetime, list[tuple[Flight, int]]] = defaultdict(list)
        fixed_counts: dict[datetime, int] = defaultdict(int)
        for flight in snapshot.flights:
            candidates = []
            if flight.origin == disruption.airport_code:
                candidates.append(flight.scheduled_departure)
            if flight.destination == disruption.airport_code:
                candidates.append(flight.scheduled_arrival)
            for movement_time in candidates:
                if not disruption.starts_at <= movement_time < disruption.ends_at:
                    continue
                bucket = movement_time.replace(minute=0, second=0, microsecond=0)
                if flight.flight_id in scoped_set:
                    threshold_slots = ceil((60 - movement_time.minute) / 15)
                    movements[bucket].append((flight, threshold_slots))
                else:
                    fixed_counts[bucket] += 1

        for bucket in sorted(set(fixed_counts) | set(movements)):
            stays: list[cp_model.IntVar] = []
            for flight, threshold_slots in movements[bucket]:
                stay = model.new_bool_var(f"capacity_{disruption.disruption_id}_{flight.flight_id}")
                moved_out = model.new_bool_var(f"moved_{disruption.disruption_id}_{flight.flight_id}")
                model.add(stay + moved_out + cancellation[flight.flight_id] == 1)
                model.add(delay_slots[flight.flight_id] <= threshold_slots - 1).only_enforce_if(stay)
                model.add(delay_slots[flight.flight_id] >= threshold_slots).only_enforce_if(moved_out)
                stays.append(stay)
            model.add(fixed_counts[bucket] + sum(stays) <= permitted)

    passenger_load = _party_load_by_flight(snapshot)
    max_delay = model.new_int_var(0, maximum_delay_slots, "maximum_delay")
    model.add_max_equality(max_delay, list(delay_slots.values()))
    substitution_terms: list[cp_model.LinearExpr] = []
    for original_id, rotation in scoped_by_rotation.items():
        for (selected_original, aircraft_id), choice in rotation_choice.items():
            if selected_original == original_id and aircraft_id != original_id:
                for flight in rotation:
                    reassigned_and_operated = model.new_bool_var(
                        f"substitution_{original_id}_{aircraft_id}_{flight.flight_id}"
                    )
                    model.add(reassigned_and_operated <= choice)
                    model.add(reassigned_and_operated + cancellation[flight.flight_id] <= 1)
                    model.add(reassigned_and_operated >= choice - cancellation[flight.flight_id])
                    substitution_terms.append(reassigned_and_operated)
    objective_terms: list[cp_model.LinearExpr] = []
    for flight_id in scope:
        objective_terms.append(
            cancellation[flight_id]
            * (
                strategy.cancellation_weight
                + passenger_load.get(flight_id, 0) * strategy.passenger_preservation_weight
            )
        )
        objective_terms.append(delay_slots[flight_id] * 15 * strategy.delay_weight)
    objective_terms.extend(term * strategy.aircraft_reassignment_weight for term in substitution_terms)
    objective_terms.append(max_delay * 15 * strategy.stabilization_weight)
    model.minimize(cp_model.LinearExpr.sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.max_time_in_seconds = 5.0
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RecoverySolverError(f"CP-SAT returned {solver.status_name(status)}")

    chosen_rotation: dict[str, str] = {}
    for (original_id, aircraft_id), choice in sorted(rotation_choice.items()):
        if solver.value(choice):
            chosen_rotation[original_id] = aircraft_id

    actions: list[RecoveryAction] = []
    for flight_id in scope:
        flight = flight_by_id[flight_id]
        if solver.value(cancellation[flight_id]):
            actions.append(CancelFlight("cancel_flight", flight_id))
            continue
        delay_minutes = solver.value(delay_slots[flight_id]) * 15
        if delay_minutes:
            actions.append(
                RetimeFlight(
                    "retime_flight",
                    flight_id,
                    flight.scheduled_departure + timedelta(minutes=delay_minutes),
                    flight.scheduled_arrival + timedelta(minutes=delay_minutes),
                )
            )
        assigned_aircraft = chosen_rotation[flight.aircraft_id]
        if assigned_aircraft != flight.aircraft_id:
            actions.append(ReassignAircraft("reassign_aircraft", flight_id, assigned_aircraft))
    ordered_actions = tuple(sorted(actions, key=lambda action: (action.flight_id, action.action_type)))
    digest = snapshot_hash(snapshot)
    candidate_id = candidate_content_hash(
        strategy=strategy,
        snapshot_digest=digest,
        artifact_hash=artifact_hash,
        scope_flight_ids=scope,
        actions=ordered_actions,
    )
    return CandidatePlan(
        candidate_id=candidate_id,
        strategy=strategy,
        snapshot_hash=digest,
        artifact_hash=artifact_hash,
        solver_version=SOLVER_PRIMITIVES_VERSION,
        scope_flight_ids=scope,
        actions=ordered_actions,
        solver_status=solver.status_name(status),
        objective_value=round(solver.objective_value),
    )


def generate_candidates(
    snapshot: WorldSnapshot,
    scope_flight_ids: tuple[str, ...],
    strategies: tuple[StrategyParameters, ...],
    *,
    artifact_hash: str,
) -> tuple[CandidatePlan, ...]:
    if not strategies:
        raise ValueError("At least one strategy proposal is required")
    candidates = tuple(
        solve_candidate(snapshot, scope_flight_ids, strategy, artifact_hash=artifact_hash)
        for strategy in strategies
    )
    action_sets = {
        tuple((action.action_type, action.flight_id, repr(action)) for action in candidate.actions)
        for candidate in candidates
    }
    if len(action_sets) != len(candidates):
        raise CandidateDiversityError("Strategy proposals produced duplicate candidate actions")
    return candidates
