CREATE TABLE IF NOT EXISTS airline_recovery_snapshots (
    snapshot_hash text PRIMARY KEY CHECK (snapshot_hash ~ '^[0-9a-f]{64}$'),
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    world_revision integer NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (world_id, world_revision, snapshot_hash)
);

CREATE TABLE IF NOT EXISTS airline_recovery_batches (
    batch_id uuid PRIMARY KEY,
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    world_revision integer NOT NULL,
    snapshot_hash text NOT NULL REFERENCES airline_recovery_snapshots(snapshot_hash) ON DELETE RESTRICT,
    artifact_hash text NOT NULL CHECK (artifact_hash ~ '^[0-9a-f]{64}$'),
    ranking_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS airline_recovery_candidates (
    candidate_id text PRIMARY KEY CHECK (candidate_id ~ '^[0-9a-f]{64}$'),
    batch_id uuid NOT NULL REFERENCES airline_recovery_batches(batch_id) ON DELETE CASCADE,
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    world_revision integer NOT NULL,
    snapshot_hash text NOT NULL REFERENCES airline_recovery_snapshots(snapshot_hash) ON DELETE RESTRICT,
    artifact_hash text NOT NULL CHECK (artifact_hash ~ '^[0-9a-f]{64}$'),
    strategy_parameters jsonb NOT NULL,
    actions jsonb NOT NULL,
    solver_version text NOT NULL,
    solver_status text NOT NULL,
    objective_value bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS airline_recovery_candidates_batch_idx
    ON airline_recovery_candidates(batch_id, candidate_id);

CREATE TABLE IF NOT EXISTS airline_candidate_evaluations (
    candidate_id text PRIMARY KEY REFERENCES airline_recovery_candidates(candidate_id) ON DELETE CASCADE,
    simulator_version text NOT NULL,
    valid boolean NOT NULL,
    metrics jsonb NOT NULL,
    violations jsonb NOT NULL,
    rank integer CHECK (rank > 0),
    recommended boolean NOT NULL DEFAULT false,
    evaluated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT recommended OR (valid AND rank = 1))
);
