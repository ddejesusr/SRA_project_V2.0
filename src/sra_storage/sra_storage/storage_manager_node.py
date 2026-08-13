#!/usr/bin/env python3
"""ROS2 storage manager for physical fuse-box slot reservations."""

from __future__ import annotations

import json
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from .database import connect_database
from .repository import StorageRepository, StorageReservationError


class StorageManagerNode(Node):
    """Reserve storage slots and emit deterministic robot STORE job requests."""

    def __init__(self):
        super().__init__("sra_storage_manager")

        self._connection = connect_database()
        self._repository = StorageRepository(self._connection)

        self.create_subscription(
            String,
            "/sra/production/events",
            self._production_event_callback,
            20,
        )
        self.create_subscription(
            String,
            "/sra/robot/jobs/status",
            self._robot_status_callback,
            20,
        )

        self.job_pub = self.create_publisher(
            String,
            "/sra/robot/jobs/request",
            20,
        )
        self.storage_pub = self.create_publisher(
            String,
            "/sra/storage/events",
            20,
        )
        self.alert_pub = self.create_publisher(
            String,
            "/sra/alerts/events",
            20,
        )

        self.get_logger().info("Storage manager ready on SRA V2 database.")

    def _production_event_callback(self, msg: String) -> None:
        try:
            event = json.loads(msg.data)
            if not isinstance(event, dict):
                raise ValueError("Production event must be a JSON object")
            if event.get("type") != "part_ready_for_storage":
                return

            part_number = self._required_int(event, "part_number")
            dispatch_position = self._required_int(event, "dispatch_position")
            if dispatch_position not in (1, 2):
                raise ValueError(
                    f"Invalid dispatch position for part {part_number}: {dispatch_position}"
                )

            slot_id = self._repository.reserve_slot_for_part(part_number)
            self._publish_storage_event(
                {
                    "type": "storage_reserved",
                    "part_number": part_number,
                    "slot_id": slot_id,
                    "dispatch_position": dispatch_position,
                }
            )
            self._publish_store_job(
                part_number=part_number,
                dispatch_position=dispatch_position,
                slot_id=slot_id,
            )

        except (ValueError, TypeError, KeyError, StorageReservationError) as exc:
            self.get_logger().warning(f"Storage reservation rejected: {exc}")
            self._publish_storage_alert(str(exc))
        except Exception as exc:
            self.get_logger().error(f"Storage manager failure: {exc}")
            self._publish_storage_alert(
                str(exc),
                operator_message=(
                    "Se produjo un error interno al preparar el almacenamiento de una caja."
                ),
            )

    def _robot_status_callback(self, msg: String) -> None:
        """Finalize only STORE jobs owned by this storage manager."""
        try:
            status = json.loads(msg.data)
            if not isinstance(status, dict):
                raise ValueError("Robot job status must be a JSON object")
            if status.get("job_type") != "STORE":
                return

            part_number = self._required_int(status, "part_number")
            slot_id = str(status.get("slot_id", "")).strip().upper()
            state = str(status.get("status", "")).strip().upper()
            if not slot_id:
                raise ValueError("STORE job status is missing slot_id")

            if state == "COMPLETED":
                self._repository.complete_storage(part_number, slot_id)
                self._publish_storage_event(
                    {
                        "type": "part_stored",
                        "part_number": part_number,
                        "slot_id": slot_id,
                    }
                )
                self._clear_storage_alert()
                return

            if state == "FAILED_SAFE_AT_SOURCE":
                self._repository.release_reservation(part_number, slot_id)
                self._publish_storage_event(
                    {
                        "type": "storage_reservation_released",
                        "part_number": part_number,
                        "slot_id": slot_id,
                    }
                )
                return

            if state in {"FAILED", "POSITION_UNKNOWN"}:
                self._publish_storage_alert(
                    f"Store job for part {part_number} ended in {state}",
                    operator_message=(
                        "No se pudo confirmar la posición final de una caja durante el "
                        "almacenamiento. Revise el robot y la ubicación física antes de continuar."
                    ),
                )

        except (ValueError, TypeError, KeyError, StorageReservationError) as exc:
            self.get_logger().warning(f"Robot storage status rejected: {exc}")
            self._publish_storage_alert(str(exc))
        except Exception as exc:
            self.get_logger().error(f"Storage status failure: {exc}")
            self._publish_storage_alert(str(exc))

    def _publish_store_job(
        self,
        *,
        part_number: int,
        dispatch_position: int,
        slot_id: str,
    ) -> None:
        payload = {
            "job_type": "STORE",
            "part_number": part_number,
            "source": "DISPATCH_LEFT" if dispatch_position == 1 else "DISPATCH_RIGHT",
            "dispatch_position": dispatch_position,
            "slot_id": slot_id,
        }
        msg = String()
        msg.data = json.dumps(payload)
        self.job_pub.publish(msg)

    def _publish_storage_event(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload)
        self.storage_pub.publish(msg)

    def _publish_storage_alert(
        self,
        backend_error: str,
        *,
        operator_message: str | None = None,
    ) -> None:
        payload = {
            "key": "storage_operation",
            "level": "warning",
            "active": True,
            "message": operator_message
            or "No fue posible preparar una ubicación de almacenamiento para la caja.",
            "backend_error": backend_error,
        }
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self.alert_pub.publish(msg)

    def _clear_storage_alert(self) -> None:
        msg = String()
        msg.data = json.dumps(
            {
                "key": "storage_operation",
                "level": "warning",
                "active": False,
                "message": "",
            },
            ensure_ascii=False,
        )
        self.alert_pub.publish(msg)

    @staticmethod
    def _required_int(payload: dict[str, Any], key: str) -> int:
        if key not in payload:
            raise ValueError(f"Missing required field: {key}")
        try:
            return int(payload[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid integer field {key}: {payload[key]}") from exc

    def destroy_node(self):
        if self._connection is not None:
            self._connection.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = StorageManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
