#!/usr/bin/env python3
"""ROS2 manager for deterministic delivery of concrete stored parts."""

from __future__ import annotations

import json
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from .database import connect_database
from .repository import DeliveryRepository, DeliveryReservationError


SAFE_BEFORE_PICK_STEPS = {None, "PREPARE", "MOVE_TO_PICKUP", "PICK"}


class DeliveryManagerNode(Node):
    """Reserve physical parts, enqueue DELIVERY jobs, and finalize outcomes."""

    def __init__(self):
        super().__init__("sra_delivery_manager")

        self._connection = connect_database()
        self._repository = DeliveryRepository(self._connection)

        self.create_subscription(String, "/sra/delivery/request", self._request_callback, 20)
        self.create_subscription(
            String,
            "/sra/robot/jobs/status",
            self._robot_status_callback,
            50,
        )

        self.job_pub = self.create_publisher(String, "/sra/robot/jobs/request", 50)
        self.delivery_pub = self.create_publisher(String, "/sra/delivery/events", 50)
        self.alert_pub = self.create_publisher(String, "/sra/alerts/events", 20)

        self.get_logger().info("V2 delivery manager ready on physical inventory.")

    def _request_callback(self, msg: String) -> None:
        try:
            request = json.loads(msg.data)
            if not isinstance(request, dict):
                raise ValueError("Delivery request must be a JSON object")

            bottom_cover = self._required_choice(
                request, "bottom_cover", {"blue", "red", "black"}
            )
            top_cover = self._required_choice(request, "top_cover", {"blue", "red"})
            fuse_configuration = self._required_choice(
                request, "fuse_configuration", {"none", "upper", "lower", "both"}
            )
            quantity = self._required_int(request, "quantity")
            destination = str(request.get("destination", "")).strip()
            if not destination:
                raise ValueError("Missing required field: destination")

            reserved = self._repository.create_request(
                bottom_cover=bottom_cover,
                top_cover=top_cover,
                fuse_configuration=fuse_configuration,
                quantity=quantity,
                destination=destination,
            )

            jobs = []
            for item in reserved["items"]:
                job = {
                    "job_id": item["job_id"],
                    "job_type": "DELIVERY",
                    "request_id": reserved["request_id"],
                    "part_number": item["part_number"],
                    "source": "STORAGE",
                    "slot_id": item["slot_id"],
                    "destination": destination,
                }
                self._publish_job(job)
                jobs.append(job)

            self._publish_delivery_event(
                {
                    "type": "delivery_queued",
                    "request_id": reserved["request_id"],
                    "quantity": quantity,
                    "destination": destination,
                    "parts": [job["part_number"] for job in jobs],
                    "jobs": [job["job_id"] for job in jobs],
                }
            )
            self._clear_delivery_alert()

        except (ValueError, TypeError, KeyError, DeliveryReservationError) as exc:
            self.get_logger().warning(f"Delivery request rejected: {exc}")
            self._publish_delivery_alert(str(exc))
        except Exception as exc:
            self.get_logger().error(f"Delivery request failure: {exc}")
            self._publish_delivery_alert(
                str(exc),
                operator_message="Se produjo un error interno al preparar la entrega.",
            )

    def _robot_status_callback(self, msg: String) -> None:
        try:
            status = json.loads(msg.data)
            if not isinstance(status, dict) or status.get("job_type") != "DELIVERY":
                return

            job_id = str(status.get("job_id", "")).strip()
            if not job_id:
                raise ValueError("DELIVERY status is missing job_id")

            state = str(status.get("status", "")).strip().upper()
            step = status.get("step")
            step = str(step).strip().upper() if step is not None else None

            if state == "RUNNING":
                try:
                    self._repository.mark_running(job_id)
                except DeliveryReservationError as exc:
                    if "No active delivery item" not in str(exc):
                        raise
                return

            if state == "COMPLETED":
                result = self._repository.complete_delivery(job_id)
                self._publish_delivery_event(
                    {"type": "part_delivered", "job_id": job_id, **result}
                )
                self._clear_delivery_alert()
                return

            if state == "FAILED_SAFE_AT_SOURCE":
                result = self._repository.release_before_pick(job_id)
                self._publish_delivery_event(
                    {
                        "type": "delivery_reservation_released",
                        "job_id": job_id,
                        **result,
                    }
                )
                return

            if state == "CANCELLED":
                if step in SAFE_BEFORE_PICK_STEPS:
                    result = self._repository.release_before_pick(job_id)
                    self._publish_delivery_event(
                        {"type": "delivery_cancelled_safe", "job_id": job_id, **result}
                    )
                else:
                    result = self._repository.mark_position_unknown(job_id)
                    self._publish_unknown_position_alert(result["part_number"])
                return

            if state in {"FAILED", "POSITION_UNKNOWN"}:
                result = self._repository.mark_position_unknown(job_id)
                self._publish_unknown_position_alert(result["part_number"])

        except (ValueError, TypeError, KeyError, DeliveryReservationError) as exc:
            self.get_logger().warning(f"Delivery robot status rejected: {exc}")
            self._publish_delivery_alert(str(exc))
        except Exception as exc:
            self.get_logger().error(f"Delivery status failure: {exc}")
            self._publish_delivery_alert(str(exc))

    def _publish_job(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload)
        self.job_pub.publish(msg)

    def _publish_delivery_event(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload)
        self.delivery_pub.publish(msg)

    def _publish_unknown_position_alert(self, part_number: int) -> None:
        self._publish_delivery_alert(
            f"Physical position unresolved for part {part_number}",
            operator_message=(
                "No se pudo confirmar la ubicación de una caja durante la entrega. "
                "Revise físicamente el robot y el almacenamiento antes de continuar."
            ),
        )

    def _publish_delivery_alert(
        self,
        backend_error: str,
        *,
        operator_message: str | None = None,
    ) -> None:
        msg = String()
        msg.data = json.dumps(
            {
                "key": "delivery_operation",
                "level": "warning",
                "active": True,
                "message": operator_message
                or "No fue posible preparar la entrega solicitada con el inventario disponible.",
                "backend_error": backend_error,
            },
            ensure_ascii=False,
        )
        self.alert_pub.publish(msg)

    def _clear_delivery_alert(self) -> None:
        msg = String()
        msg.data = json.dumps(
            {
                "key": "delivery_operation",
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
            value = int(payload[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid integer field {key}: {payload[key]}") from exc
        if value <= 0:
            raise ValueError(f"Field {key} must be greater than zero")
        return value

    @staticmethod
    def _required_choice(payload: dict[str, Any], key: str, allowed: set[str]) -> str:
        value = str(payload.get(key, "")).strip().lower()
        if value not in allowed:
            raise ValueError(f"Invalid {key}: {value}")
        return value

    def destroy_node(self):
        if self._connection is not None:
            self._connection.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = DeliveryManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
