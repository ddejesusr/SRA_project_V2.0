BEGIN;

ALTER TABLE parts
    DROP CONSTRAINT IF EXISTS parts_status_check;

ALTER TABLE parts
    ADD CONSTRAINT parts_status_check
    CHECK (status IN (
        'IN_PRODUCTION',
        'WAITING_PICKUP',
        'STORAGE_RESERVED',
        'STORED',
        'DELIVERY_RESERVED',
        'DELIVERED',
        'POSITION_UNKNOWN',
        'SCRAPPED'
    ));

COMMIT;
