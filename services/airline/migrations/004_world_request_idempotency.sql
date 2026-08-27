CREATE TABLE IF NOT EXISTS airline_world_requests (
    idempotency_key text PRIMARY KEY CHECK (length(idempotency_key) BETWEEN 8 AND 128),
    world_id uuid NOT NULL UNIQUE REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now()
);
