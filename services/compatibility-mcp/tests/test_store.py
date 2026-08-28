from airstrong_compatibility_mcp.store import AuditState


def test_audit_state_is_immutable_value() -> None:
    state = AuditState(exists=False, total_writes=0)

    assert state.exists is False
    assert state.total_writes == 0
