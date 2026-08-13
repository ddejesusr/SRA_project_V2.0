"""Transactional persistence for concrete physical delivery reservations."""

from __future__ import annotations

import uuid

from sra_production.lifecycle import ProductLifecycleEvent, make_product_machine
from sra_storage.lifecycle import StorageSlotEvent, make_storage_slot_machine


class DeliveryReservationError(RuntimeError):
    """Raised when a delivery reservation or completion is physically unsafe."""


class DeliveryRepository:
    """Reserve and finalize delivery of exact stored parts and slots."""

    def __init__(self, connection):
        self.connection = connection

    def create_request(
        self,
        *,
        bottom_cover: str,
        top_cover: str,
        fuse_configuration: str,
        quantity: int,
        destination: str,
    ) -> dict:
        """Atomically reserve exact stored parts and assign all robot job IDs."""
        quantity = int(quantity)
        if quantity <= 0:
            raise DeliveryReservationError("Delivery quantity must be greater than zero")
        destination = str(destination).strip()
        if not destination:
            raise DeliveryReservationError("Delivery destination is required")

        try:
            with self.connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT p.part_number, ss.slot_id, p.status, ss.status
                    FROM parts p
                    JOIN storage_slots ss ON ss.part_number = p.part_number
                    WHERE p.bottom_cover = %s
                      AND p.top_cover = %s
                      AND p.fuse_configuration = %s
                      AND p.status = 'STORED'
                      AND ss.status = 'OCCUPIED'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM delivery_request_items dri
                          WHERE dri.part_number = p.part_number
                            AND dri.status IN ('RESERVED', 'QUEUED', 'RUNNING')
                      )
                    ORDER BY p.stored_at NULLS LAST, p.part_number
                    FOR UPDATE OF p, ss SKIP LOCKED
                    LIMIT %s
                    """,
                    (bottom_cover, top_cover, fuse_configuration, quantity),
                )
                rows = cur.fetchall()
                if len(rows) != quantity:
                    raise DeliveryReservationError(
                        f"Insufficient stored stock: requested={quantity}, available={len(rows)}"
                    )

                cur.execute(
                    """
                    INSERT INTO delivery_requests (
                        bottom_cover, top_cover, fuse_configuration,
                        quantity, destination, status
                    )
                    VALUES (%s, %s, %s, %s, %s, 'RESERVING')
                    RETURNING request_id
                    """,
                    (bottom_cover, top_cover, fuse_configuration, quantity, destination),
                )
                request_id = cur.fetchone()[0]

                items = []
                for part_number, slot_id, part_status, slot_status in rows:
                    part_machine = make_product_machine(part_status)
                    part_machine.handle(ProductLifecycleEvent.RESERVE_DELIVERY)
                    if slot_status != "OCCUPIED":
                        raise DeliveryReservationError(
                            f"Slot {slot_id} is not occupied during delivery reservation"
                        )

                    job_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        UPDATE parts
                        SET status = %s, updated_at = NOW()
                        WHERE part_number = %s
                        """,
                        (part_machine.state.value, part_number),
                    )
                    cur.execute(
                        """
                        INSERT INTO delivery_request_items (
                            request_id, part_number, slot_id, status, robot_job_id
                        )
                        VALUES (%s, %s, %s, 'QUEUED', %s)
                        """,
                        (request_id, part_number, slot_id, job_id),
                    )
                    items.append(
                        {
                            "part_number": part_number,
                            "slot_id": slot_id,
                            "job_id": job_id,
                        }
                    )

                cur.execute(
                    """
                    UPDATE delivery_requests
                    SET status = 'QUEUED', updated_at = NOW()
                    WHERE request_id = %s
                    """,
                    (request_id,),
                )

            self.connection.commit()
            return {
                "request_id": request_id,
                "destination": destination,
                "items": items,
            }
        except Exception:
            self.connection.rollback()
            raise

    def mark_running(self, job_id: str) -> None:
        self._set_item_status(job_id, from_states=("QUEUED",), to_state="RUNNING")

    def complete_delivery(self, job_id: str) -> dict:
        """Confirm retrieval and placement at destination, then free source slot."""
        try:
            with self.connection.cursor() as cur:
                item = self._get_item_for_update(cur, job_id)
                request_id, part_number, slot_id, item_status, part_status, slot_status = item
                if item_status not in {"QUEUED", "RUNNING"}:
                    raise DeliveryReservationError(
                        f"Delivery item for job {job_id} is not active; status={item_status}"
                    )

                part_machine = make_product_machine(part_status)
                part_machine.handle(ProductLifecycleEvent.DELIVERY_COMPLETE)
                slot_machine = make_storage_slot_machine(slot_status)
                slot_machine.handle(StorageSlotEvent.RETRIEVAL_CONFIRMED)

                cur.execute(
                    """
                    UPDATE parts
                    SET status = %s,
                        delivered_at = NOW(),
                        updated_at = NOW()
                    WHERE part_number = %s
                    """,
                    (part_machine.state.value, part_number),
                )
                cur.execute(
                    """
                    UPDATE storage_slots
                    SET status = %s,
                        part_number = NULL,
                        updated_at = NOW()
                    WHERE slot_id = %s
                    """,
                    (slot_machine.state.value, slot_id),
                )
                cur.execute(
                    """
                    UPDATE delivery_request_items
                    SET status = 'DELIVERED', updated_at = NOW()
                    WHERE robot_job_id = %s
                    """,
                    (job_id,),
                )
                self._refresh_request_status(cur, request_id)

            self.connection.commit()
            return {
                "request_id": request_id,
                "part_number": part_number,
                "slot_id": slot_id,
            }
        except Exception:
            self.connection.rollback()
            raise

    def release_before_pick(self, job_id: str) -> dict:
        """Release reservation only when the part is confirmed still in storage."""
        try:
            with self.connection.cursor() as cur:
                item = self._get_item_for_update(cur, job_id)
                request_id, part_number, slot_id, item_status, part_status, slot_status = item
                if item_status not in {"QUEUED", "RUNNING"}:
                    raise DeliveryReservationError(
                        f"Delivery item for job {job_id} is not active; status={item_status}"
                    )
                if slot_status != "OCCUPIED":
                    raise DeliveryReservationError(
                        f"Cannot safely release delivery: slot {slot_id} status={slot_status}"
                    )

                part_machine = make_product_machine(part_status)
                part_machine.handle(ProductLifecycleEvent.RELEASE_DELIVERY)
                cur.execute(
                    """
                    UPDATE parts
                    SET status = %s, updated_at = NOW()
                    WHERE part_number = %s
                    """,
                    (part_machine.state.value, part_number),
                )
                cur.execute(
                    """
                    UPDATE delivery_request_items
                    SET status = 'RELEASED', updated_at = NOW()
                    WHERE robot_job_id = %s
                    """,
                    (job_id,),
                )
                self._refresh_request_status(cur, request_id)

            self.connection.commit()
            return {"request_id": request_id, "part_number": part_number, "slot_id": slot_id}
        except Exception:
            self.connection.rollback()
            raise

    def mark_position_unknown(self, job_id: str) -> dict:
        try:
            with self.connection.cursor() as cur:
                item = self._get_item_for_update(cur, job_id)
                request_id, part_number, slot_id, item_status, part_status, slot_status = item
                if item_status not in {"QUEUED", "RUNNING"}:
                    raise DeliveryReservationError(
                        f"Delivery item for job {job_id} is not active; status={item_status}"
                    )

                part_machine = make_product_machine(part_status)
                part_machine.handle(ProductLifecycleEvent.MARK_POSITION_UNKNOWN)
                slot_machine = make_storage_slot_machine(slot_status)
                slot_machine.handle(StorageSlotEvent.MARK_UNKNOWN)

                cur.execute(
                    "UPDATE parts SET status = %s, updated_at = NOW() WHERE part_number = %s",
                    (part_machine.state.value, part_number),
                )
                cur.execute(
                    "UPDATE storage_slots SET status = %s, updated_at = NOW() WHERE slot_id = %s",
                    (slot_machine.state.value, slot_id),
                )
                cur.execute(
                    """
                    UPDATE delivery_request_items
                    SET status = 'POSITION_UNKNOWN', updated_at = NOW()
                    WHERE robot_job_id = %s
                    """,
                    (job_id,),
                )
                cur.execute(
                    """
                    UPDATE delivery_requests
                    SET status = 'POSITION_UNKNOWN', updated_at = NOW()
                    WHERE request_id = %s
                    """,
                    (request_id,),
                )

            self.connection.commit()
            return {"request_id": request_id, "part_number": part_number, "slot_id": slot_id}
        except Exception:
            self.connection.rollback()
            raise

    def _set_item_status(self, job_id: str, *, from_states: tuple[str, ...], to_state: str) -> None:
        try:
            with self.connection.cursor() as cur:
                cur.execute(
                    """
                    UPDATE delivery_request_items
                    SET status = %s, updated_at = NOW()
                    WHERE robot_job_id = %s
                      AND status = ANY(%s)
                    RETURNING request_id
                    """,
                    (to_state, job_id, list(from_states)),
                )
                row = cur.fetchone()
                if row is None:
                    raise DeliveryReservationError(f"No active delivery item for job {job_id}")
                cur.execute(
                    """
                    UPDATE delivery_requests
                    SET status = 'IN_PROGRESS', updated_at = NOW()
                    WHERE request_id = %s AND status = 'QUEUED'
                    """,
                    (row[0],),
                )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    @staticmethod
    def _get_item_for_update(cur, job_id: str):
        cur.execute(
            """
            SELECT
                dri.request_id,
                dri.part_number,
                dri.slot_id,
                dri.status,
                p.status,
                ss.status
            FROM delivery_request_items dri
            JOIN parts p ON p.part_number = dri.part_number
            JOIN storage_slots ss ON ss.slot_id = dri.slot_id
            WHERE dri.robot_job_id = %s
            FOR UPDATE OF dri, p, ss
            """,
            (job_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise DeliveryReservationError(f"Unknown delivery robot job: {job_id}")
        return row

    @staticmethod
    def _refresh_request_status(cur, request_id: int) -> None:
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'DELIVERED'),
                COUNT(*) FILTER (WHERE status IN ('RESERVED', 'QUEUED', 'RUNNING')),
                COUNT(*) FILTER (WHERE status = 'POSITION_UNKNOWN'),
                COUNT(*)
            FROM delivery_request_items
            WHERE request_id = %s
            """,
            (request_id,),
        )
        delivered, active, unknown, total = cur.fetchone()
        if unknown:
            request_status = "POSITION_UNKNOWN"
        elif total and delivered == total:
            request_status = "COMPLETED"
        elif active:
            request_status = "IN_PROGRESS"
        else:
            request_status = "FAILED"

        cur.execute(
            """
            UPDATE delivery_requests
            SET status = %s,
                updated_at = NOW(),
                completed_at = CASE WHEN %s = 'COMPLETED' THEN NOW() ELSE completed_at END
            WHERE request_id = %s
            """,
            (request_status, request_status, request_id),
        )
