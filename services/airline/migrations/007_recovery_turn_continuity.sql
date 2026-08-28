ALTER TABLE airline_recovery_runs
    ADD COLUMN IF NOT EXISTS approval_continuation_turn_id text;
