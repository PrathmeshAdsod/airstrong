CREATE TABLE IF NOT EXISTS airline_recovery_runs (
    run_id uuid PRIMARY KEY,
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    started_world_revision integer NOT NULL,
    snapshot_hash text NOT NULL CHECK (snapshot_hash ~ '^[0-9a-f]{64}$'),
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 8 AND 128),
    status text NOT NULL CHECK (status IN (
        'investigating',
        'computing',
        'candidates_ranked',
        'no_valid_candidate',
        'awaiting_approval',
        'approved',
        'denied',
        'executing',
        'verifying',
        'verified',
        'failed',
        'stale'
    )),
    trueforge_session_id text,
    investigation_turn_id text,
    execution_turn_id text,
    batch_id uuid REFERENCES airline_recovery_batches(batch_id) ON DELETE RESTRICT,
    recommended_candidate_id text REFERENCES airline_recovery_candidates(candidate_id) ON DELETE RESTRICT,
    failure jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (world_id, idempotency_key),
    UNIQUE (world_id, started_world_revision)
);

CREATE INDEX IF NOT EXISTS airline_recovery_runs_world_idx
    ON airline_recovery_runs(world_id, created_at DESC);

CREATE TABLE IF NOT EXISTS airline_recovery_approvals (
    approval_id uuid PRIMARY KEY,
    run_id uuid NOT NULL UNIQUE REFERENCES airline_recovery_runs(run_id) ON DELETE CASCADE,
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    candidate_id text NOT NULL REFERENCES airline_recovery_candidates(candidate_id) ON DELETE RESTRICT,
    expected_world_revision integer NOT NULL,
    snapshot_hash text NOT NULL CHECK (snapshot_hash ~ '^[0-9a-f]{64}$'),
    plan_hash text NOT NULL CHECK (plan_hash ~ '^[0-9a-f]{64}$'),
    actions jsonb NOT NULL,
    summary jsonb NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied', 'consumed')),
    decision_idempotency_key text,
    trueforge_thread_id text,
    trueforge_tool_call_id text,
    trueforge_approval_event_id text,
    requested_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz,
    consumed_at timestamptz,
    UNIQUE (decision_idempotency_key)
);

CREATE TABLE IF NOT EXISTS airline_operational_executions (
    execution_id uuid PRIMARY KEY,
    run_id uuid NOT NULL UNIQUE REFERENCES airline_recovery_runs(run_id) ON DELETE CASCADE,
    approval_id uuid NOT NULL UNIQUE REFERENCES airline_recovery_approvals(approval_id) ON DELETE RESTRICT,
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    candidate_id text NOT NULL REFERENCES airline_recovery_candidates(candidate_id) ON DELETE RESTRICT,
    idempotency_key text NOT NULL UNIQUE CHECK (length(idempotency_key) BETWEEN 8 AND 128),
    starting_world_revision integer NOT NULL,
    applied_world_revision integer NOT NULL,
    actions jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS airline_recovery_verifications (
    verification_id uuid PRIMARY KEY,
    execution_id uuid NOT NULL UNIQUE REFERENCES airline_operational_executions(execution_id) ON DELETE CASCADE,
    run_id uuid NOT NULL UNIQUE REFERENCES airline_recovery_runs(run_id) ON DELETE CASCADE,
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    world_revision integer NOT NULL,
    valid boolean NOT NULL,
    facts jsonb NOT NULL,
    verified_at timestamptz NOT NULL DEFAULT now()
);
