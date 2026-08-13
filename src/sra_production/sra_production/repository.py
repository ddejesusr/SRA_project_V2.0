"""PostgreSQL persistence for Festo carrier and product digital twins."""

from __future__ import annotations

import json
from typing import Any

from .state_model import get_state_info, infer_top_cover, is_valid_transition


class ProductionTrackingError(RuntimeError):
    """Raised when production data would violate tracking rules."""


class ProductionRepository:
    """Persist carrier/product tracking with transactional consistency."""

    def __init__(self, connection):
        self.connection = connection

    def ensure_carrier(self, carrier_id: int) -> None:
        """Ensure that a physical Festo carrier exists in the backend."""
        carrier_id = self._validate_carrier_id(carrier_id)
        try:
            with self.connection.cursor() as cur:
                self._upsert_carrier(cur, carrier_id)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def record_failed_inspection(
        self,
        carrier_id: int,
        *,
        bottom_cover: str | None = None,
        fuse_configuration: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record a NOK camera attempt without allocating a permanent part."""
        carrier_id = self._validate_carrier_id(carrier_id)
        if bottom_cover is not None:
            self._validate_bottom_cover(bottom_cover)
        if fuse_configuration is not None:
            self._validate_fuse_configuration(fuse_configuration)

        try:
            with self.connection.cursor() as cur:
                self._upsert_carrier(cur, carrier_id)
                cur.execute(
                    """
                    INSERT INTO inspection_events (
                        carrier_id,
                        result,
                        bottom_cover,
                        fuse_configuration,
                        details
                    )
                    VALUES (%s, FALSE, %s, %s, %s::jsonb)
                    """,
                    (
                        carrier_id,
                        bottom_cover,
                        fuse_configuration,
                        json.dumps(details or {}),
                    ),
                )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def accept_camera_inspection(
        self,
        carrier_id: int,
        *,
        bottom_cover: str,
        fuse_configuration: str,
        details: dict[str, Any] | None = None,
    ) -> int:
        """Create the permanent digital twin after a successful camera result.

        State Code 100 is the first confirmed production state. Duplicate State
        100 observations for the same active carrier are idempotent.
        """
        carrier_id = self._validate_carrier_id(carrier_id)
        self._validate_bottom_cover(bottom_cover)
        self._validate_fuse_configuration(fuse_configuration)

        try:
            with self.connection.cursor() as cur:
                self._upsert_carrier(cur, carrier_id)
                active = self._get_active_part(cur, carrier_id, for_update=True)

                if active is not None:
                    part_number, state_code = active
                    if state_code != 100:
                        raise ProductionTrackingError(
                            f"Carrier {carrier_id} already has active part "
                            f"{part_number} at State Code {state_code}"
                        )
                    self.connection.commit()
                    return part_number

                cur.execute(
                    """
                    INSERT INTO parts (
                        source_carrier_id,
                        carrier_link_active,
                        inspection_result,
                        bottom_cover,
                        fuse_configuration,
                        state_code,
                        status,
                        updated_at
                    )
                    VALUES (%s, TRUE, TRUE, %s, %s, 100, 'IN_PRODUCTION', NOW())
                    RETURNING part_number
                    """,
                    (carrier_id, bottom_cover, fuse_configuration),
                )
                part_number = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO inspection_events (
                        carrier_id,
                        part_number,
                        result,
                        bottom_cover,
                        fuse_configuration,
                        details
                    )
                    VALUES (%s, %s, TRUE, %s, %s, %s::jsonb)
                    """,
                    (
                        carrier_id,
                        part_number,
                        bottom_cover,
                        fuse_configuration,
                        json.dumps(details or {}),
                    ),
                )

                self._insert_process_event(
                    cur,
                    part_number=part_number,
                    carrier_id=carrier_id,
                    station="camera",
                    event_type="STATE_TRANSITION",
                    old_state_code=0,
                    new_state_code=100,
                    details=details,
                )
                self._touch_carrier(cur, carrier_id, 100)

            self.connection.commit()
            return part_number
        except Exception:
            self.connection.rollback()
            raise

    def apply_state_code(
        self,
        carrier_id: int,
        state_code: int,
        *,
        station: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> int:
        """Apply a confirmed Festo State Code to the carrier's active product."""
        carrier_id = self._validate_carrier_id(carrier_id)
        state_code = int(state_code)
        get_state_info(state_code)

        if state_code == 100:
            raise ProductionTrackingError(
                "State Code 100 must be created through accept_camera_inspection()"
            )
        if state_code == 0:
            raise ProductionTrackingError(
                "Carrier reset is not a product-state transition"
            )

        try:
            with self.connection.cursor() as cur:
                active = self._get_active_part(cur, carrier_id, for_update=True)
                if active is None:
                    raise ProductionTrackingError(
                        f"Carrier {carrier_id} has no active product"
                    )

                part_number, current_state = active
                if current_state == state_code:
                    self._touch_carrier(cur, carrier_id, state_code)
                    self.connection.commit()
                    return part_number

                if not is_valid_transition(current_state, state_code):
                    raise ProductionTrackingError(
                        f"Invalid State Code transition for carrier {carrier_id}: "
                        f"{current_state} -> {state_code}"
                    )

                cur.execute(
                    """
                    UPDATE parts
                    SET state_code = %s,
                        top_cover = COALESCE(%s, top_cover),
                        updated_at = NOW()
                    WHERE part_number = %s
                    """,
                    (state_code, infer_top_cover(state_code), part_number),
                )
                self._touch_carrier(cur, carrier_id, state_code)
                self._insert_process_event(
                    cur,
                    part_number=part_number,
                    carrier_id=carrier_id,
                    station=station,
                    event_type="STATE_TRANSITION",
                    old_state_code=current_state,
                    new_state_code=state_code,
                    details=details,
                )

            self.connection.commit()
            return part_number
        except Exception:
            self.connection.rollback()
            raise

    def complete_dispatch_handoff(
        self,
        carrier_id: int,
        state_code: int,
        dispatch_position: int,
        *,
        details: dict[str, Any] | None = None,
    ) -> int:
        """Complete Dispatch and transfer identity from Carrier ID to Part Number."""
        carrier_id = self._validate_carrier_id(carrier_id)
        if state_code not in (701, 702):
            raise ProductionTrackingError(
                f"Dispatch handoff requires State Code 701 or 702, got {state_code}"
            )
        if dispatch_position not in (1, 2):
            raise ProductionTrackingError(
                f"Dispatch position must be 1 or 2, got {dispatch_position}"
            )

        try:
            with self.connection.cursor() as cur:
                active = self._get_active_part(cur, carrier_id, for_update=True)
                if active is None:
                    raise ProductionTrackingError(
                        f"Carrier {carrier_id} has no active product"
                    )

                part_number, current_state = active
                if current_state != state_code:
                    if not is_valid_transition(current_state, state_code):
                        raise ProductionTrackingError(
                            f"Invalid dispatch transition for carrier {carrier_id}: "
                            f"{current_state} -> {state_code}"
                        )
                    cur.execute(
                        """
                        UPDATE parts
                        SET state_code = %s,
                            top_cover = %s,
                            updated_at = NOW()
                        WHERE part_number = %s
                        """,
                        (state_code, infer_top_cover(state_code), part_number),
                    )
                    self._insert_process_event(
                        cur,
                        part_number=part_number,
                        carrier_id=carrier_id,
                        station="dispatch",
                        event_type="STATE_TRANSITION",
                        old_state_code=current_state,
                        new_state_code=state_code,
                        details=details,
                    )

                cur.execute(
                    """
                    UPDATE parts
                    SET carrier_link_active = FALSE,
                        dispatch_position = %s,
                        status = 'WAITING_PICKUP',
                        dispatched_at = NOW(),
                        updated_at = NOW()
                    WHERE part_number = %s
                    """,
                    (dispatch_position, part_number),
                )
                self._insert_process_event(
                    cur,
                    part_number=part_number,
                    carrier_id=carrier_id,
                    station="dispatch",
                    event_type="CARRIER_HANDOFF",
                    old_state_code=state_code,
                    new_state_code=state_code,
                    details={**(details or {}), "dispatch_position": dispatch_position},
                )
                cur.execute(
                    """
                    UPDATE carriers
                    SET current_state_code = %s,
                        status = 'AVAILABLE',
                        last_seen_at = NOW(),
                        updated_at = NOW()
                    WHERE carrier_id = %s
                    """,
                    (state_code, carrier_id),
                )

            self.connection.commit()
            return part_number
        except Exception:
            self.connection.rollback()
            raise

    @staticmethod
    def _get_active_part(cur, carrier_id: int, *, for_update: bool):
        query = """
            SELECT part_number, state_code
            FROM parts
            WHERE source_carrier_id = %s
              AND carrier_link_active = TRUE
        """
        if for_update:
            query += " FOR UPDATE"
        cur.execute(query, (carrier_id,))
        return cur.fetchone()

    @staticmethod
    def _upsert_carrier(cur, carrier_id: int) -> None:
        cur.execute(
            """
            INSERT INTO carriers (carrier_id, last_seen_at, updated_at)
            VALUES (%s, NOW(), NOW())
            ON CONFLICT (carrier_id) DO UPDATE SET
                last_seen_at = NOW(),
                updated_at = NOW()
            """,
            (carrier_id,),
        )

    @staticmethod
    def _touch_carrier(cur, carrier_id: int, state_code: int) -> None:
        cur.execute(
            """
            UPDATE carriers
            SET current_state_code = %s,
                status = 'IN_USE',
                last_seen_at = NOW(),
                updated_at = NOW()
            WHERE carrier_id = %s
            """,
            (state_code, carrier_id),
        )

    @staticmethod
    def _insert_process_event(
        cur,
        *,
        part_number: int,
        carrier_id: int,
        station: str | None,
        event_type: str,
        old_state_code: int,
        new_state_code: int,
        details: dict[str, Any] | None,
    ) -> None:
        cur.execute(
            """
            INSERT INTO part_process_events (
                part_number,
                carrier_id,
                station,
                event_type,
                old_state_code,
                new_state_code,
                details
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                part_number,
                carrier_id,
                station,
                event_type,
                old_state_code,
                new_state_code,
                json.dumps(details or {}),
            ),
        )

    @staticmethod
    def _validate_carrier_id(carrier_id: int) -> int:
        try:
            value = int(carrier_id)
        except (TypeError, ValueError) as exc:
            raise ProductionTrackingError(f"Invalid Carrier ID: {carrier_id}") from exc
        if value < 0:
            raise ProductionTrackingError(f"Invalid Carrier ID: {carrier_id}")
        return value

    @staticmethod
    def _validate_bottom_cover(value: str) -> None:
        if value not in {"blue", "red", "black"}:
            raise ProductionTrackingError(f"Invalid bottom cover: {value}")

    @staticmethod
    def _validate_fuse_configuration(value: str) -> None:
        if value not in {"none", "upper", "lower", "both"}:
            raise ProductionTrackingError(f"Invalid fuse configuration: {value}")
