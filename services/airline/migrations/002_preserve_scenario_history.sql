ALTER TABLE airline_disruptions
    ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true;

CREATE INDEX IF NOT EXISTS airline_disruptions_active_world_idx
    ON airline_disruptions(world_id, active, starts_at, ends_at);
