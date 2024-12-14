BEGIN;

-- Drop foreign key constraint if exists
ALTER TABLE IF EXISTS transitions
DROP CONSTRAINT IF EXISTS fk_transitions_execution;

-- Drop indexes if they exist
DROP INDEX IF EXISTS idx_transitions_metadata;

DROP INDEX IF EXISTS idx_transitions_execution_id_sorted;

DROP INDEX IF EXISTS idx_transitions_transition_id_sorted;

DROP INDEX IF EXISTS idx_transitions_label;

DROP INDEX IF EXISTS idx_transitions_next;

DROP INDEX IF EXISTS idx_transitions_current;

-- Drop the transitions table (this will also remove it from hypertables)
DROP TABLE IF EXISTS transitions;

-- Drop custom types if they exist
DROP TYPE IF EXISTS transition_cursor;

DROP TYPE IF EXISTS transition_type;

-- Drop the trigger and function for transition validation
DROP TRIGGER IF EXISTS validate_transition ON transitions;

DROP FUNCTION IF EXISTS check_valid_transition ();

COMMIT;
