from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from .engine import calculate_operational_impacts
from .models import WorldSnapshot
from .ranking import NoValidCandidateError, rank_valid_candidates
from .recovery import (
    SOLVER_PRIMITIVES_VERSION,
    CancelFlight,
    CandidatePlan,
    ReassignAircraft,
    RetimeFlight,
    StrategyParameters,
    candidate_content_hash,
    snapshot_hash,
)
from .twin import evaluate_candidate

SANDBOX_MODULES = (
    "models.py",
    "recovery.py",
    "solver_primitives.py",
    "sandbox_runtime.py",
)


def solver_bundle() -> dict[str, Any]:
    package_dir = Path(__file__).resolve().parent
    files = {
        f"airstrong_airline/{name}": (package_dir / name).read_text(encoding="utf-8")
        for name in SANDBOX_MODULES
    }
    files["airstrong_airline/__init__.py"] = "\n"
    digest = hashlib.sha256(
        "".join(f"{name}\0{files[name]}\0" for name in sorted(files)).encode()
    ).hexdigest()
    return {
        "bundleHash": digest,
        "files": files,
        "requirements": ["ortools==9.15.6755"],
        "solverVersion": SOLVER_PRIMITIVES_VERSION,
    }


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_integer(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer")
    return value


def _parse_strategy(payload: Any) -> StrategyParameters:
    if not isinstance(payload, dict):
        raise ValueError("Candidate strategy must be an object")
    expected_keys = {
        "strategy_id",
        "max_cancellations",
        "max_delay_minutes",
        "allow_aircraft_substitution",
        "cancellation_weight",
        "passenger_preservation_weight",
        "delay_weight",
        "aircraft_reassignment_weight",
        "stabilization_weight",
    }
    if set(payload) != expected_keys:
        raise ValueError("Candidate strategy fields do not match the trusted schema")
    substitution = payload["allow_aircraft_substitution"]
    if type(substitution) is not bool:
        raise ValueError("allow_aircraft_substitution must be a boolean")
    strategy = StrategyParameters(
        strategy_id=_required_string(payload, "strategy_id"),
        max_cancellations=_required_integer(payload, "max_cancellations"),
        max_delay_minutes=_required_integer(payload, "max_delay_minutes"),
        allow_aircraft_substitution=substitution,
        cancellation_weight=_required_integer(payload, "cancellation_weight"),
        passenger_preservation_weight=_required_integer(payload, "passenger_preservation_weight"),
        delay_weight=_required_integer(payload, "delay_weight"),
        aircraft_reassignment_weight=_required_integer(payload, "aircraft_reassignment_weight"),
        stabilization_weight=_required_integer(payload, "stabilization_weight"),
    )
    strategy.validate()
    return strategy


def _parse_action(payload: Any) -> CancelFlight | RetimeFlight | ReassignAircraft:
    if not isinstance(payload, dict):
        raise ValueError("Candidate action must be an object")
    action_type = _required_string(payload, "action_type")
    if action_type == "cancel_flight":
        if set(payload) != {"action_type", "flight_id"}:
            raise ValueError("Cancel action fields do not match the trusted schema")
        return CancelFlight("cancel_flight", _required_string(payload, "flight_id"))
    if action_type == "retime_flight":
        if set(payload) != {"action_type", "flight_id", "departure", "arrival"}:
            raise ValueError("Retime action fields do not match the trusted schema")
        departure = datetime.fromisoformat(_required_string(payload, "departure").replace("Z", "+00:00"))
        arrival = datetime.fromisoformat(_required_string(payload, "arrival").replace("Z", "+00:00"))
        if departure.tzinfo is None or arrival.tzinfo is None:
            raise ValueError("Retime action timestamps must include a timezone")
        return RetimeFlight(
            "retime_flight",
            _required_string(payload, "flight_id"),
            departure,
            arrival,
        )
    if action_type == "reassign_aircraft":
        if set(payload) != {"action_type", "flight_id", "aircraft_id"}:
            raise ValueError("Aircraft reassignment fields do not match the trusted schema")
        return ReassignAircraft(
            "reassign_aircraft",
            _required_string(payload, "flight_id"),
            _required_string(payload, "aircraft_id"),
        )
    raise ValueError(f"Unknown recovery action type {action_type!r}")


def validated_candidates(
    snapshot: WorldSnapshot,
    payloads: list[dict[str, Any]],
    *,
    artifact_hash: str,
) -> tuple[CandidatePlan, ...]:
    if len(payloads) != 3:
        raise ValueError("A recovery artifact must produce exactly three candidates")
    authoritative_scope = tuple(
        sorted(
            {
                impact.entity_id
                for impact in calculate_operational_impacts(snapshot)
                if impact.entity_type == "flight"
            }
        )
    )
    if not authoritative_scope:
        raise ValueError("The authoritative incident has no impacted flight scope")
    authoritative_snapshot_hash = snapshot_hash(snapshot)
    candidates: list[CandidatePlan] = []
    action_sets: set[tuple[tuple[str, str, str], ...]] = set()
    for payload in payloads:
        if not isinstance(payload, dict):
            raise ValueError("Candidate must be an object")
        if set(payload) != {
            "candidateId",
            "strategy",
            "snapshotHash",
            "artifactHash",
            "solverVersion",
            "scopeFlightIds",
            "actions",
            "solverStatus",
            "objectiveValue",
        }:
            raise ValueError("Candidate fields do not match the trusted schema")
        strategy = _parse_strategy(payload.get("strategy"))
        action_payloads = payload.get("actions")
        if not isinstance(action_payloads, list):
            raise ValueError("Candidate actions must be an array")
        actions = tuple(_parse_action(item) for item in action_payloads)
        scope_payload = payload.get("scopeFlightIds")
        if not isinstance(scope_payload, list) or not all(
            isinstance(item, str) and item for item in scope_payload
        ):
            raise ValueError("scopeFlightIds must be an array of non-empty strings")
        scope_flight_ids = tuple(scope_payload)
        if scope_flight_ids != authoritative_scope:
            raise ValueError("Candidate scope does not match the authoritative incident scope")
        candidate = CandidatePlan(
            candidate_id=_required_string(payload, "candidateId"),
            strategy=strategy,
            snapshot_hash=_required_string(payload, "snapshotHash"),
            artifact_hash=_required_string(payload, "artifactHash"),
            solver_version=_required_string(payload, "solverVersion"),
            scope_flight_ids=scope_flight_ids,
            actions=actions,
            solver_status=_required_string(payload, "solverStatus"),
            objective_value=_required_integer(payload, "objectiveValue"),
        )
        if candidate.artifact_hash != artifact_hash:
            raise ValueError("Candidate artifact hash does not match submitted source")
        if candidate.snapshot_hash != authoritative_snapshot_hash:
            raise ValueError("Candidate snapshot hash does not match the authoritative snapshot")
        if candidate.solver_version != SOLVER_PRIMITIVES_VERSION:
            raise ValueError("Candidate solver version is not trusted")
        expected_id = candidate_content_hash(
            strategy=strategy,
            snapshot_digest=authoritative_snapshot_hash,
            artifact_hash=artifact_hash,
            scope_flight_ids=candidate.scope_flight_ids,
            actions=actions,
        )
        if candidate.candidate_id != expected_id:
            raise ValueError("Candidate content hash is invalid")
        action_key = tuple((item.action_type, item.flight_id, repr(item)) for item in actions)
        if action_key in action_sets:
            raise ValueError("Candidate actions must be meaningfully distinct")
        action_sets.add(action_key)
        candidates.append(candidate)
    return tuple(candidates)


def evaluate_generated_candidates(
    snapshot: WorldSnapshot,
    candidates: tuple[CandidatePlan, ...],
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    evaluations = tuple(evaluate_candidate(snapshot, candidate) for candidate in candidates)
    try:
        ranked = rank_valid_candidates(evaluations)
    except NoValidCandidateError:
        ranked = ()
    return evaluations, ranked


def public_artifact_lineage(
    *,
    artifact_hash: str,
    trueforge_session_id: str,
    trueforge_turn_id: str,
    sandbox_id: str,
) -> dict[str, Any]:
    return {
        "artifactHash": artifact_hash,
        "trueforgeSessionId": trueforge_session_id,
        "trueforgeTurnId": trueforge_turn_id,
        "sandboxId": sandbox_id,
    }


__all__ = [
    "evaluate_generated_candidates",
    "public_artifact_lineage",
    "solver_bundle",
    "validated_candidates",
]
