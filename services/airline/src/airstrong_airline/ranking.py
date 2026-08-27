from __future__ import annotations

from .recovery import RANKING_VERSION, CandidateEvaluation


class NoValidCandidateError(RuntimeError):
    pass


def ranking_key(evaluation: CandidateEvaluation) -> tuple[int, int, int, int, int, str]:
    metrics = evaluation.metrics
    return (
        metrics.cancellations,
        metrics.disrupted_passengers,
        metrics.total_delay_minutes,
        metrics.operational_reassignments,
        metrics.stabilization_minutes,
        evaluation.candidate_id,
    )


def rank_valid_candidates(evaluations: tuple[CandidateEvaluation, ...]) -> tuple[CandidateEvaluation, ...]:
    valid = tuple(evaluation for evaluation in evaluations if evaluation.valid)
    if not valid:
        raise NoValidCandidateError("The authoritative twin found no valid recovery candidate")
    return tuple(sorted(valid, key=ranking_key))


__all__ = ["RANKING_VERSION", "NoValidCandidateError", "rank_valid_candidates", "ranking_key"]
