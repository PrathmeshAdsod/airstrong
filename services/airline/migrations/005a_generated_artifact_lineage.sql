ALTER TABLE airline_generated_artifacts
    ADD COLUMN IF NOT EXISTS artifact_id uuid;

UPDATE airline_generated_artifacts
SET artifact_id = gen_random_uuid()
WHERE artifact_id IS NULL;

ALTER TABLE airline_generated_artifacts
    ALTER COLUMN artifact_id SET NOT NULL;

ALTER TABLE airline_generated_artifacts
    DROP CONSTRAINT IF EXISTS airline_generated_artifacts_pkey;

ALTER TABLE airline_generated_artifacts
    ADD CONSTRAINT airline_generated_artifacts_pkey PRIMARY KEY (artifact_id);

CREATE INDEX IF NOT EXISTS airline_generated_artifacts_hash_idx
    ON airline_generated_artifacts(artifact_hash, created_at);
