CREATE TABLE IF NOT EXISTS airline_generated_artifacts (
    artifact_hash text PRIMARY KEY CHECK (artifact_hash ~ '^[0-9a-f]{64}$'),
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    world_revision integer NOT NULL,
    trueforge_session_id text NOT NULL,
    trueforge_turn_id text NOT NULL,
    sandbox_id text NOT NULL,
    source text NOT NULL,
    sandbox_stdout jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (world_id, world_revision, trueforge_session_id, trueforge_turn_id)
);

CREATE INDEX IF NOT EXISTS airline_generated_artifacts_world_idx
    ON airline_generated_artifacts(world_id, world_revision, created_at);
