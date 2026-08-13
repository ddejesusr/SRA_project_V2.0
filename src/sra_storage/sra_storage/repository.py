"""Transactional storage-slot reservation and completion logic."""

from __future__ import annotations

from sra_core import TransitionNotAllowed
from sra_production.lifecycle import (
    ProductLifecycleEvent,
    make_product_machine,
)

from .lifecycle import StorageSlotEvent, make_storage_slot_machine


class StorageReservationError(RuntimeError):
    """Raised when a physical storage operation cannot be reserved safely."""


class StorageRepository:
    """Manage physical 3 x 10 storage slots in the SRA V2 database."""

    def __init__(self, connection):
        self.connection = connection

    def reserve_slot_for_part(self, part_number: int) -> str:
        part_number = int(part_number)

        try:
            with self.connection.cursor() as cur:
                cur.execute(
                    "SELECT status FROM parts WHERE part_number = %s FOR UPDATE",
                    (part_number,),
                )
                row = cur.fetchone()
                if row is None:
                    raise StorageReservationError(f"Unknown part number: {part_number}")

                part_status = row[0]
                if part_status == "STORAGE_RESERVED":
                    cur.execute(
                        """
                        SELECT slot_id
                        FROM storage_slots
                        WHERE part_number = %s AND status = 'RESERVED'
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

                part_machine = make_product_machine(part_status)
                try:
                    part_machine.handle(ProductLifecycleEvent.RESERVE_STORAGE)
                except TransitionNotAllowed as exc:
                    raise StorageReservationError(str(exc)) from exc

                cur.execute(
                    """
                    SELECT slot_id, status
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

                slot_id, slot_status = slot
                slot_machine = make_storage_slot_machine(slot_status)
                try:
                    slot_machine.handle(StorageSlotEvent.RESERVE)
                except TransitionNotAllowed as exc:
                    raise StorageReservationError(str(exc)) from exc

                cur.execute(
                    """
                    UPDATE storage_slots
                    SET status = %s, part_number = %s, updated_at = NOW()
                    WHERE slot_id = %s
                    """,
                    (slot_machine.state.value, part_number, slot_id),
                )
                cur.execute(
                    """
                    UPDATE parts
                    SET status = %s, updated_at = NOW()
                    WHERE part_number = %s
                    """,
                    (part_machine.state.value, part_number),
                )

            self.connection.commit()
            return slot_id
        except Exception:
            self.connection.rollback()
            raise

    def complete_storage(self, part_number: int, slot_id: str) -> None:
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
                if slot[1] != part_number:
                    raise StorageReservationError(
                        f"Slot {slot_id} is not assigned to part {part_number}"
                    )

                cur.execute(
                    "SELECT status FROM parts WHERE part_number = %s FOR UPDATE",
                    (part_number,),
                )
                part = cur.fetchone()
                if part is None:
                    raise StorageReservationError(f"Unknown part number: {part_number}")

                slot_machine = make_storage_slot_machine(slot[0])
                part_machine = make_product_machine(part[0])
                try:
                    slot_machine.handle(StorageSlotEvent.PLACE_CONFIRMED)
                    part_machine.handle(ProductLifecycleEvent.STORAGE_COMPLETE)
                except TransitionNotAllowed as exc:
                    raise StorageReservationError(str(exc)) from exc

                cur.execute(
                    "UPDATE storage_slots SET status = %s, updated_at = NOW() WHERE slot_id = %s",
                    (slot_machine.state.value, slot_id),
                )
                cur.execute(
                    """
                    UPDATE parts
                    SET status = %s, stored_at = NOW(), updated_at = NOW()
                    WHERE part_number = %s
                    """,
                    (part_machine.state.value, part_number),
                )

            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def release_reservation(self, part_number: int, slot_id: str) -> None:
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
                if slot[1] != part_number:
                    raise StorageReservationError(
                        f"Slot {slot_id} is not assigned to part {part_number}"
                    )

                cur.execute(
                    "SELECT status FROM parts WHERE part_number = %s FOR UPDATE",
                    (part_number,),
                )
                part = cur.fetchone()
                if part is None:
                    raise StorageReservationError(f"Unknown part number: {part_number}")

                slot_machine = make_storage_slot_machine(slot[0])
                part_machine = make_product_machine(part[0])
                try:
                    slot_machine.handle(StorageSlotEvent.RELEASE_RESERVATION)
                    part_machine.handle(ProductLifecycleEvent.RELEASE_STORAGE)
                except TransitionNotAllowed as exc:
                    raise StorageReservationError(str(exc)) from exc

                cur.execute(
                    """
                    UPDATE storage_slots
                    SET status = %s, part_number = NULL, updated_at = NOW()
                    WHERE slot_id = %s
                    """,
                    (slot_machine.state.value, slot_id),
                )
                cur.execute(
                    "UPDATE parts SET status = %s, updated_at = NOW() WHERE part_number = %s",
                    (part_machine.state.value, part_number),
                )

            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def mark_position_unknown(self, part_number: int, slot_id: str) -> None:
        """Persist physical uncertainty after an ambiguous robot failure."""
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
                if slot is None or slot[1] != part_number:
                    raise StorageReservationError(
                        f"Slot {slot_id} is not assigned to part {part_number}"
                    )

                cur.execute(
                    "SELECT status FROM parts WHERE part_number = %s FOR UPDATE",
                    (part_number,),
                )
                part = cur.fetchone()
                if part is None:
                    raise StorageReservationError(f"Unknown part number: {part_number}")

                slot_machine = make_storage_slot_machine(slot[0])
                part_machine = make_product_machine(part[0])
                try:
                    slot_machine.handle(StorageSlotEvent.MARK_UNKNOWN)
                    part_machine.handle(ProductLifecycleEvent.MARK_POSITION_UNKNOWN)
                except TransitionNotAllowed as exc:
                    raise StorageReservationError(str(exc)) from exc

                cur.execute(
                    "UPDATE storage_slots SET status = %s, updated_at = NOW() WHERE slot_id = %s",
                    (slot_machine.state.value, slot_id),
                )
                cur.execute(
                    "UPDATE parts SET status = %s, updated_at = NOW() WHERE part_number = %s",
                    (part_machine.state.value, part_number),
                )

            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
