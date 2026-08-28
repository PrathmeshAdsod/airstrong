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


def _parse_action(payload: dict[str, Any]) -> CancelFlight | RetimeFlight | ReassignAircraft:
    action_type = payload.get("action_type")
    if action_type == "cancel_flight":
        return CancelFlight(action_type, str(payload["flight_id"]))
    if action_type == "retime_flight":
        return RetimeFlight(
            action_type,
            str(payload["flight_id"]),
            datetime.fromisoformat(str(payload["departure"]).replace("Z", "+00:00")),
            datetime.fromisoformat(str(payload["arrival"]).replace("Z", "+00:00")),
        )
    if action_type == "reassign_aircraft":
        return ReassignAircraft(
            action_type,
            str(payload["flight_id"]),
            str(payload["aircraft_id"]),
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
        strategy = StrategyParameters(**payload["strategy"])
        strategy.validate()
        actions = tuple(_parse_action(item) for item in payload["actions"])
        scope_flight_ids = tuple(sorted({str(item) for item in payload["scopeFlightIds"]}))
        if scope_flight_ids != authoritative_scope:
            raise ValueError("Candidate scope does not match the authoritative incident scope")
        candidate = CandidatePlan(
            candidate_id=str(payload["candidateId"]),
            strategy=strategy,
            snapshot_hash=str(payload["snapshotHash"]),
            artifact_hash=str(payload["artifactHash"]),
            solver_version=str(payload["solverVersion"]),
            scope_flight_ids=scope_flight_ids,
            actions=actions,
            solver_status=str(payload["solverStatus"]),
            objective_value=int(payload["objectiveValue"]),
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
