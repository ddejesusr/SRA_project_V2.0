#!/usr/bin/env python3
"""ROS2 node for normalized Festo CP Lab production tracking events."""

from __future__ import annotations

import json
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from .database import connect_database
from .repository import ProductionRepository, ProductionTrackingError
from .state_model import get_state_info


class ProductionTrackerNode(Node):
    """Persist normalized production events and publish digital-twin updates."""

    def __init__(self):
        super().__init__("sra_production_tracker")

        self._connection = connect_database()
        self._repository = ProductionRepository(self._connection)

        self.create_subscription(String, "/sra/production/input", self._event_callback, 20)

        self.production_pub = self.create_publisher(String, "/sra/production/events", 20)
        self.alert_pub = self.create_publisher(String, "/sra/alerts/events", 20)
        self.tts_alert_pub = self.create_publisher(String, "/sra/tts/alert", 10)

        self.get_logger().info("Production tracker ready on SRA V2 database.")

    def _event_callback(self, msg: String) -> None:
        try:
            event = json.loads(msg.data)
            if not isinstance(event, dict):
                raise ValueError("Production event must be a JSON object")

            event_type = event.get("type")
            if event_type == "camera_inspection":
                self._handle_camera_inspection(event)
            elif event_type == "state_update":
                self._handle_state_update(event)
            elif event_type == "dispatch_handoff":
                self._handle_dispatch_handoff(event)
            else:
                raise ValueError(f"Unsupported production event type: {event_type}")

        except (ValueError, TypeError, KeyError, ProductionTrackingError) as exc:
            self.get_logger().warning(f"Production event rejected: {exc}")
            self._publish_tracking_alert(str(exc))
        except Exception as exc:
            self.get_logger().error(f"Production tracker failure: {exc}")
            self._publish_tracking_alert(
                "Unexpected production tracking failure",
                operator_message=(
                    "Se produjo un error interno al actualizar el seguimiento de producción."
                ),
            )

    def _handle_camera_inspection(self, event: dict[str, Any]) -> None:
        carrier_id = self._required_int(event, "carrier_id")
        passed = self._required_bool(event, "passed")
        bottom_cover = self._optional_string(event, "bottom_cover")
        fuse_configuration = self._optional_string(event, "fuse_configuration")
        details = self._details(event)

        if not passed:
            self._repository.record_failed_inspection(
                carrier_id,
                bottom_cover=bottom_cover,
                fuse_configuration=fuse_configuration,
                details=details,
            )
            self._publish_production_event(
                {"type": "inspection_failed", "carrier_id": carrier_id}
            )
            self._publish_inspection_alert(carrier_id)
            return

        if bottom_cover is None or fuse_configuration is None:
            raise ValueError(
                "Successful camera inspection requires bottom_cover and fuse_configuration"
            )

        part_number = self._repository.accept_camera_inspection(
            carrier_id,
            bottom_cover=bottom_cover,
            fuse_configuration=fuse_configuration,
            details=details,
        )

        self._publish_production_event(
            {
                "type": "part_created",
                "part_number": part_number,
                "carrier_id": carrier_id,
                "state_code": 100,
                "process_state": get_state_info(100).process_state.value,
                "bottom_cover": bottom_cover,
                "fuse_configuration": fuse_configuration,
            }
        )
        self._clear_inspection_alert()

    def _handle_state_update(self, event: dict[str, Any]) -> None:
        carrier_id = self._required_int(event, "carrier_id")
        state_code = self._required_int(event, "state_code")
        station = self._optional_string(event, "station")

        if state_code in (701, 702):
            raise ValueError(
                "Dispatch State Codes 701/702 must use dispatch_handoff with position"
            )

        part_number = self._repository.apply_state_code(
            carrier_id,
            state_code,
            station=station,
            details=self._details(event),
        )
        state_info = get_state_info(state_code)

        self._publish_production_event(
            {
                "type": "part_state_updated",
                "part_number": part_number,
                "carrier_id": carrier_id,
                "state_code": state_code,
                "process_state": state_info.process_state.value,
                "top_cover": state_info.top_cover,
                "station": station,
            }
        )

    def _handle_dispatch_handoff(self, event: dict[str, Any]) -> None:
        carrier_id = self._required_int(event, "carrier_id")
        state_code = self._required_int(event, "state_code")
        dispatch_position = self._required_int(event, "dispatch_position")

        part_number = self._repository.complete_dispatch_handoff(
            carrier_id,
            state_code,
            dispatch_position,
            details=self._details(event),
        )
        state_info = get_state_info(state_code)

        self._publish_production_event(
            {
                "type": "part_ready_for_storage",
                "part_number": part_number,
                "source": "dispatch",
                "dispatch_position": dispatch_position,
                "state_code": state_code,
                "process_state": state_info.process_state.value,
                "top_cover": state_info.top_cover,
            }
        )

    def _publish_production_event(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self.production_pub.publish(msg)

    def _publish_inspection_alert(self, carrier_id: int) -> None:
        operator_message = (
            f"La inspección de la caja transportada por el portador {carrier_id} "
            "no fue satisfactoria. Revise la estación de cámara."
        )
        self._publish_alert(
            {
                "key": "camera_inspection",
                "level": "warning",
                "active": True,
                "message": operator_message,
                "carrier_id": carrier_id,
            }
        )
        self._publish_tts_alert(
            key="camera_inspection",
            active=True,
            text=operator_message,
        )

    def _clear_inspection_alert(self) -> None:
        self._publish_alert(
            {
                "key": "camera_inspection",
                "level": "warning",
                "active": False,
                "message": "",
            }
        )
        self._publish_tts_alert(
            key="camera_inspection",
            active=False,
            text="",
        )

    def _publish_tracking_alert(
        self,
        backend_error: str,
        *,
        operator_message: str | None = None,
    ) -> None:
        message = operator_message or (
            "Se detectó una inconsistencia en el seguimiento de una caja de fusibles."
        )
        self._publish_alert(
            {
                "key": "production_tracking",
                "level": "warning",
                "active": True,
                "message": message,
                "backend_error": backend_error,
            }
        )

    def _publish_alert(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self.alert_pub.publish(msg)

    def _publish_tts_alert(self, *, key: str, active: bool, text: str) -> None:
        msg = String()
        msg.data = json.dumps(
            {"key": key, "active": active, "text": text},
            ensure_ascii=False,
        )
        self.tts_alert_pub.publish(msg)

    @staticmethod
    def _required_int(event: dict[str, Any], key: str) -> int:
        if key not in event:
            raise ValueError(f"Missing required field: {key}")
        try:
            return int(event[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid integer field {key}: {event[key]}") from exc

    @staticmethod
    def _required_bool(event: dict[str, Any], key: str) -> bool:
        if key not in event:
            raise ValueError(f"Missing required field: {key}")
        value = event[key]
        if isinstance(value, bool):
            return value
        raise ValueError(f"Invalid boolean field {key}: {value}")

    @staticmethod
    def _optional_string(event: dict[str, Any], key: str) -> str | None:
        value = event.get(key)
        if value is None:
            return None
        value = str(value).strip().lower()
        return value or None

    @staticmethod
    def _details(event: dict[str, Any]) -> dict[str, Any]:
        details = event.get("details", {})
        if details is None:
            return {}
        if not isinstance(details, dict):
            raise ValueError("details must be a JSON object")
        return details

    def destroy_node(self):
        if self._connection is not None:
            self._connection.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = ProductionTrackerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
