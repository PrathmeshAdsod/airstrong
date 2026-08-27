from airstrong_airline.ranking import NoValidCandidateError, rank_valid_candidates
from airstrong_airline.recovery import CandidateEvaluation, CandidateMetrics, Violation


def evaluation(candidate_id: str, *, valid: bool, cancellations: int, passengers: int) -> CandidateEvaluation:
    violations = () if valid else (Violation("TEST", "factual rejection", "candidate", candidate_id, {}),)
    return CandidateEvaluation(
        candidate_id=candidate_id,
        snapshot_hash="1" * 64,
        simulator_version="test-twin",
        valid=valid,
        metrics=CandidateMetrics(cancellations, passengers, 0, 0, 0),
        violations=violations,
    )


def test_ranking_excludes_invalid_candidates_and_is_lexicographic() -> None:
    more_passengers = evaluation("b", valid=True, cancellations=0, passengers=5)
    fewer_passengers = evaluation("a", valid=True, cancellations=0, passengers=2)
    fewer_cancellations = evaluation("c", valid=True, cancellations=1, passengers=0)
    rejected = evaluation("d", valid=False, cancellations=0, passengers=0)

    ranked = rank_valid_candidates((more_passengers, rejected, fewer_cancellations, fewer_passengers))

    assert [item.candidate_id for item in ranked] == ["a", "b", "c"]


def test_ranking_reports_when_the_twin_finds_no_valid_candidate() -> None:
    rejected = evaluation("d", valid=False, cancellations=0, passengers=0)

    try:
        rank_valid_candidates((rejected,))
    except NoValidCandidateError as error:
        assert "no valid recovery candidate" in str(error)
    else:
        raise AssertionError("Expected factual no-valid-candidate outcome")
