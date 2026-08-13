#!/usr/bin/env python3
"""Simulation source for normalized Festo CP Lab production events."""

from __future__ import annotations

import json
import os
from collections import deque
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class ProductionSimNode(Node):
    """Generate complete valid Blue/Red Festo paths for end-to-end V2 tests."""

    def __init__(self):
        super().__init__("sra_production_sim")

        self._requests: deque[list[dict[str, Any]]] = deque()
        self._active_events: deque[dict[str, Any]] | None = None
        self._step_seconds = float(os.getenv("SRA_PRODUCTION_SIM_STEP_SECONDS", "0.5"))

        self.create_subscription(
            String,
            "/sra/sim/production/request",
            self._request_callback,
            20,
        )
        self.input_pub = self.create_publisher(String, "/sra/production/input", 20)
        self.status_pub = self.create_publisher(String, "/sra/sim/production/status", 20)
        self.create_timer(self._step_seconds, self._advance)

        self.get_logger().info(
            f"Production simulator ready; normalized event step={self._step_seconds:.2f}s."
        )

    def _request_callback(self, msg: String) -> None:
        try:
            request = json.loads(msg.data)
            if not isinstance(request, dict):
                raise ValueError("Simulation request must be a JSON object")
            events = self._build_events(request)
            self._requests.append(events)
            self._publish_status(
                {
                    "status": "QUEUED",
                    "carrier_id": events[0]["carrier_id"],
                    "queue_length": len(self._requests),
                }
            )
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self.get_logger().warning(f"Production simulation request rejected: {exc}")
            self._publish_status({"status": "REJECTED", "error": str(exc)})

    def _advance(self) -> None:
        if self._active_events is None:
            if not self._requests:
                return
            self._active_events = deque(self._requests.popleft())
            first = self._active_events[0]
            self._publish_status(
                {"status": "RUNNING", "carrier_id": first["carrier_id"]}
            )

        event = self._active_events.popleft()
        msg = String()
        msg.data = json.dumps(event)
        self.input_pub.publish(msg)

        if not self._active_events:
            carrier_id = event["carrier_id"]
            self._publish_status({"status": "COMPLETED", "carrier_id": carrier_id})
            self._active_events = None

    @staticmethod
    def _build_events(request: dict[str, Any]) -> list[dict[str, Any]]:
        carrier_id = int(request["carrier_id"])
        if carrier_id < 0:
            raise ValueError("carrier_id must not be negative")

        bottom_cover = str(request["bottom_cover"]).strip().lower()
        if bottom_cover not in {"blue", "red", "black"}:
            raise ValueError(f"Invalid bottom_cover: {bottom_cover}")

        top_cover = str(request["top_cover"]).strip().lower()
        if top_cover not in {"blue", "red"}:
            raise ValueError(f"Invalid top_cover: {top_cover}")

        fuse_configuration = str(request["fuse_configuration"]).strip().lower()
        if fuse_configuration not in {"none", "upper", "lower", "both"}:
            raise ValueError(f"Invalid fuse_configuration: {fuse_configuration}")

        dispatch_position = int(request.get("dispatch_position", 1))
        if dispatch_position not in (1, 2):
            raise ValueError("dispatch_position must be 1 or 2")

        events: list[dict[str, Any]] = [
            {
                "type": "camera_inspection",
                "carrier_id": carrier_id,
                "passed": True,
                "bottom_cover": bottom_cover,
                "fuse_configuration": fuse_configuration,
                "details": {"source": "production_sim"},
            },
            {
                "type": "state_update",
                "carrier_id": carrier_id,
                "state_code": 200,
                "station": "drilling",
                "details": {"source": "production_sim"},
            },
        ]

        if top_cover == "blue":
            state_path = [
                (301, "blue_cover"),
                (401, "red_cover"),
                (501, "press"),
                (601, "labeling"),
            ]
            dispatch_state = 701
        else:
            state_path = [
                (300, "blue_cover"),
                (402, "red_cover"),
                (502, "press"),
                (602, "labeling"),
            ]
            dispatch_state = 702

        events.extend(
            {
                "type": "state_update",
                "carrier_id": carrier_id,
                "state_code": state_code,
                "station": station,
                "details": {"source": "production_sim"},
            }
            for state_code, station in state_path
        )
        events.append(
            {
                "type": "dispatch_handoff",
                "carrier_id": carrier_id,
                "state_code": dispatch_state,
                "dispatch_position": dispatch_position,
                "details": {"source": "production_sim"},
            }
        )
        return events

    def _publish_status(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload)
        self.status_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = ProductionSimNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
