from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from .models import WorldSnapshot

SOLVER_PRIMITIVES_VERSION = "solver-primitives-1.0.0"
TWIN_VERSION = "digital-twin-1.0.0"
RANKING_VERSION = "ranking-1.0.0"


@dataclass(frozen=True, slots=True)
class StrategyParameters:
    strategy_id: str
    max_cancellations: int
    max_delay_minutes: int
    allow_aircraft_substitution: bool
    cancellation_weight: int
    passenger_preservation_weight: int
    delay_weight: int
    aircraft_reassignment_weight: int
    stabilization_weight: int

    def validate(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id is required")
        integer_values = (
            self.max_cancellations,
            self.max_delay_minutes,
            self.cancellation_weight,
            self.passenger_preservation_weight,
            self.delay_weight,
            self.aircraft_reassignment_weight,
            self.stabilization_weight,
        )
        if any(type(value) is not int for value in integer_values):
            raise ValueError("strategy counts, limits, and weights must be integers")
        if type(self.allow_aircraft_substitution) is not bool:
            raise ValueError("allow_aircraft_substitution must be a boolean")
        if self.max_cancellations < 0:
            raise ValueError("max_cancellations cannot be negative")
        if self.max_delay_minutes < 0 or self.max_delay_minutes % 15:
            raise ValueError("max_delay_minutes must be a non-negative multiple of 15")
        weights = (
            self.cancellation_weight,
            self.passenger_preservation_weight,
            self.delay_weight,
            self.aircraft_reassignment_weight,
            self.stabilization_weight,
        )
        if any(weight < 0 for weight in weights) or not any(weights):
            raise ValueError("strategy weights must be non-negative and not all zero")


@dataclass(frozen=True, slots=True)
class CancelFlight:
    action_type: Literal["cancel_flight"]
    flight_id: str


@dataclass(frozen=True, slots=True)
class RetimeFlight:
    action_type: Literal["retime_flight"]
    flight_id: str
    departure: datetime
    arrival: datetime


@dataclass(frozen=True, slots=True)
class ReassignAircraft:
    action_type: Literal["reassign_aircraft"]
    flight_id: str
    aircraft_id: str


RecoveryAction = CancelFlight | RetimeFlight | ReassignAircraft


@dataclass(frozen=True, slots=True)
class CandidatePlan:
    candidate_id: str
    strategy: StrategyParameters
    snapshot_hash: str
    artifact_hash: str
    solver_version: str
    scope_flight_ids: tuple[str, ...]
    actions: tuple[RecoveryAction, ...]
    solver_status: str
    objective_value: int


@dataclass(frozen=True, slots=True)
class Violation:
    code: str
    message: str
    entity_type: str
    entity_id: str
    facts: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CandidateMetrics:
    cancellations: int
    disrupted_passengers: int
    total_delay_minutes: int
    operational_reassignments: int
    stabilization_minutes: int


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    candidate_id: str
    snapshot_hash: str
    simulator_version: str
    valid: bool
    metrics: CandidateMetrics
    violations: tuple[Violation, ...]


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in sorted(value.items())}
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def snapshot_payload(snapshot: WorldSnapshot) -> dict[str, Any]:
    return _json_value(asdict(snapshot))


def snapshot_hash(snapshot: WorldSnapshot) -> str:
    return hashlib.sha256(canonical_json(snapshot_payload(snapshot)).encode()).hexdigest()


def action_payload(action: RecoveryAction) -> dict[str, Any]:
    return _json_value(asdict(action))


def candidate_content_hash(
    *,
    strategy: StrategyParameters,
    snapshot_digest: str,
    artifact_hash: str,
    actions: tuple[RecoveryAction, ...],
) -> str:
    body = {
        "strategy": asdict(strategy),
        "snapshotHash": snapshot_digest,
        "artifactHash": artifact_hash,
        "solverVersion": SOLVER_PRIMITIVES_VERSION,
        "actions": [action_payload(action) for action in actions],
    }
    return hashlib.sha256(canonical_json(body).encode()).hexdigest()
