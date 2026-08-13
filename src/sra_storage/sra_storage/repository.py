"""Transactional storage-slot reservation and completion logic."""

from __future__ import annotations


class StorageReservationError(RuntimeError):
    """Raised when a physical storage operation cannot be reserved safely."""


class StorageRepository:
    """Manage physical 3 x 10 storage slots in the SRA V2 database."""

    def __init__(self, connection):
        self.connection = connection

    def reserve_slot_for_part(self, part_number: int) -> str:
        """Reserve the first available slot for one WAITING_PICKUP part.

        The selection and reservation occur in one transaction using row locks,
        so concurrent storage requests cannot receive the same slot.
        """
        part_number = int(part_number)

        try:
            with self.connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT status
                    FROM parts
                    WHERE part_number = %s
                    FOR UPDATE
                    """,
                    (part_number,),
                )
                row = cur.fetchone()
                if row is None:
                    raise StorageReservationError(
                        f"Unknown part number: {part_number}"
                    )

                part_status = row[0]
                if part_status == "STORAGE_RESERVED":
                    cur.execute(
                        """
                        SELECT slot_id
                        FROM storage_slots
                        WHERE part_number = %s
                          AND status = 'RESERVED'
                        """,
                        (part_number,),
                    )
                    existing = cur.fetchone()
                    if existing is None:
                        raise StorageReservationError(
                            f"Part {part_number} is STORAGE_RESERVED without a slot"
                        )
                    self.connection.commit()
                    return existing[0]

                if part_status != "WAITING_PICKUP":
                    raise StorageReservationError(
                        f"Part {part_number} is not waiting for storage; status={part_status}"
                    )

                cur.execute(
                    """
                    SELECT slot_id
                    FROM storage_slots
                    WHERE status = 'EMPTY'
                    ORDER BY row_index, column_index
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """
                )
                slot = cur.fetchone()
                if slot is None:
                    raise StorageReservationError("No empty storage slots available")

                slot_id = slot[0]
                cur.execute(
                    """
                    UPDATE storage_slots
                    SET status = 'RESERVED',
                        part_number = %s,
                        updated_at = NOW()
                    WHERE slot_id = %s
                    """,
                    (part_number, slot_id),
                )
                cur.execute(
                    """
                    UPDATE parts
                    SET status = 'STORAGE_RESERVED',
                        updated_at = NOW()
                    WHERE part_number = %s
                    """,
                    (part_number,),
                )

            self.connection.commit()
            return slot_id
        except Exception:
            self.connection.rollback()
            raise

    def complete_storage(self, part_number: int, slot_id: str) -> None:
        """Mark a successfully placed part and its reserved slot as stored."""
        part_number = int(part_number)
        slot_id = str(slot_id).strip().upper()

        try:
            with self.connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, part_number
                    FROM storage_slots
                    WHERE slot_id = %s
                    FOR UPDATE
                    """,
                    (slot_id,),
                )
                slot = cur.fetchone()
                if slot is None:
                    raise StorageReservationError(f"Unknown storage slot: {slot_id}")
                if slot[0] != "RESERVED" or slot[1] != part_number:
                    raise StorageReservationError(
                        f"Slot {slot_id} is not reserved for part {part_number}"
                    )

                cur.execute(
                    """
                    UPDATE storage_slots
                    SET status = 'OCCUPIED',
                        updated_at = NOW()
                    WHERE slot_id = %s
                    """,
                    (slot_id,),
                )
                cur.execute(
                    """
                    UPDATE parts
                    SET status = 'STORED',
                        stored_at = NOW(),
                        updated_at = NOW()
                    WHERE part_number = %s
                      AND status = 'STORAGE_RESERVED'
                    """,
                    (part_number,),
                )
                if cur.rowcount != 1:
                    raise StorageReservationError(
                        f"Part {part_number} is not in STORAGE_RESERVED state"
                    )

            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def release_reservation(self, part_number: int, slot_id: str) -> None:
        """Release a reservation only when the product is known to still be at Dispatch."""
        part_number = int(part_number)
        slot_id = str(slot_id).strip().upper()

        try:
            with self.connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, part_number
                    FROM storage_slots
                    WHERE slot_id = %s
                    FOR UPDATE
                    """,
                    (slot_id,),
                )
                slot = cur.fetchone()
                if slot is None:
                    raise StorageReservationError(f"Unknown storage slot: {slot_id}")
                if slot[0] != "RESERVED" or slot[1] != part_number:
                    raise StorageReservationError(
                        f"Slot {slot_id} is not reserved for part {part_number}"
                    )

                cur.execute(
                    """
                    UPDATE storage_slots
                    SET status = 'EMPTY',
                        part_number = NULL,
                        updated_at = NOW()
                    WHERE slot_id = %s
                    """,
                    (slot_id,),
                )
                cur.execute(
                    """
                    UPDATE parts
                    SET status = 'WAITING_PICKUP',
                        updated_at = NOW()
                    WHERE part_number = %s
                      AND status = 'STORAGE_RESERVED'
                    """,
                    (part_number,),
                )
                if cur.rowcount != 1:
                    raise StorageReservationError(
                        f"Part {part_number} is not in STORAGE_RESERVED state"
                    )

            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
