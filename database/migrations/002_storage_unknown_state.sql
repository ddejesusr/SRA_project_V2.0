BEGIN;

-- Physical automation must be able to represent an unresolved slot after an
-- ambiguous robot failure. UNKNOWN means software must not assume EMPTY or
-- OCCUPIED until an operator/recovery procedure reconciles the physical state.
ALTER TABLE storage_slots
    DROP CONSTRAINT IF EXISTS storage_slots_status_check;

ALTER TABLE storage_slots
    ADD CONSTRAINT storage_slots_status_check
    CHECK (status IN ('EMPTY', 'RESERVED', 'OCCUPIED', 'UNKNOWN'));

ALTER TABLE storage_slots
    DROP CONSTRAINT IF EXISTS storage_slots_check;

ALTER TABLE storage_slots
    ADD CONSTRAINT storage_slots_part_consistency_check
    CHECK (
        (status = 'EMPTY' AND part_number IS NULL)
        OR
        (status IN ('RESERVED', 'OCCUPIED', 'UNKNOWN') AND part_number IS NOT NULL)
    );

COMMIT;
