#!/usr/bin/env python3
"""Shared FIFO scheduler for all SRA robot jobs."""

from __future__ import annotations

import json
import uuid
from collections import deque
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


TERMINAL_STATUSES = {
    "COMPLETED",
    "FAILED",
    "FAILED_SAFE_AT_SOURCE",
    "POSITION_UNKNOWN",
    "CANCELLED",
}


class RobotSchedulerNode(Node):
    """Serialize STORE and DELIVERY workflows through one robot executor."""

    def __init__(self):
        super().__init__("sra_robot_scheduler")

        self._queue: deque[dict[str, Any]] = deque()
        self._active_job: dict[str, Any] | None = None
        self._emergency_stopped = False

        self.create_subscription(
            String,
            "/sra/robot/jobs/request",
            self._job_request_callback,
            50,
        )
        self.create_subscription(
            String,
            "/sra/robot/executor/status",
            self._executor_status_callback,
            50,
        )
        self.create_subscription(
            String,
            "/sra/system/emergency_stop",
            self._emergency_stop_callback,
            10,
        )
        self.create_subscription(
            String,
            "/sra/system/recovery",
            self._recovery_callback,
            10,
        )

        self.executor_pub = self.create_publisher(
            String,
            "/sra/robot/executor/command",
            20,
        )
        self.status_pub = self.create_publisher(
            String,
            "/sra/robot/jobs/status",
            50,
        )
        self.alert_pub = self.create_publisher(
            String,
            "/sra/alerts/events",
            20,
        )

        self.get_logger().info("Robot scheduler ready. Strict FIFO enabled.")

    def _job_request_callback(self, msg: String) -> None:
        try:
            job = json.loads(msg.data)
            if not isinstance(job, dict):
                raise ValueError("Robot job request must be a JSON object")

            job_type = str(job.get("job_type", "")).strip().upper()
            if job_type not in {"STORE", "DELIVERY"}:
                raise ValueError(f"Unsupported robot job type: {job_type}")

            if self._emergency_stopped:
                self._publish_job_status(
                    {
                        **job,
                        "job_type": job_type,
                        "status": "REJECTED",
                        "reason": "EMERGENCY_STOP_ACTIVE",
                    }
                )
                return

            queued_job = dict(job)
            queued_job["job_type"] = job_type
            queued_job.setdefault("job_id", str(uuid.uuid4()))

            self._queue.append(queued_job)
            self._publish_job_status(
                {
                    **queued_job,
                    "status": "QUEUED",
                    "queue_position": len(self._queue),
                }
            )
            self._dispatch_next_if_idle()

        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.get_logger().warning(f"Robot job request rejected: {exc}")
            self._publish_scheduler_alert(str(exc))

    def _dispatch_next_if_idle(self) -> None:
        if self._emergency_stopped or self._active_job is not None or not self._queue:
            return

        self._active_job = self._queue.popleft()
        command = {
            **self._active_job,
            "command": "EXECUTE",
        }
        msg = String()
        msg.data = json.dumps(command)
        self.executor_pub.publish(msg)
        self._publish_job_status({**self._active_job, "status": "DISPATCHED"})

    def _executor_status_callback(self, msg: String) -> None:
        try:
            status = json.loads(msg.data)
            if not isinstance(status, dict):
                raise ValueError("Executor status must be a JSON object")

            if self._active_job is None:
                self.get_logger().warning("Ignoring executor status with no active job.")
                return

            reported_job_id = str(status.get("job_id", "")).strip()
            active_job_id = str(self._active_job.get("job_id", "")).strip()
            if reported_job_id != active_job_id:
                raise ValueError(
                    f"Executor job_id mismatch: active={active_job_id}, reported={reported_job_id}"
                )

            state = str(status.get("status", "")).strip().upper()
            if not state:
                raise ValueError("Executor status is missing status")

            merged_status = {**self._active_job, **status, "status": state}
            self._publish_job_status(merged_status)

            if state in TERMINAL_STATUSES:
                self._active_job = None
                self._dispatch_next_if_idle()

        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.get_logger().warning(f"Executor status rejected: {exc}")
            self._publish_scheduler_alert(str(exc))

    def _emergency_stop_callback(self, msg: String) -> None:
        self._emergency_stopped = True

        while self._queue:
            queued_job = self._queue.popleft()
            self._publish_job_status(
                {
                    **queued_job,
                    "status": "CANCELLED",
                    "reason": "EMERGENCY_STOP",
                }
            )

        if self._active_job is not None:
            cancel = {
                **self._active_job,
                "command": "CANCEL",
                "reason": "EMERGENCY_STOP",
            }
            out = String()
            out.data = json.dumps(cancel)
            self.executor_pub.publish(out)

        self.get_logger().warning("Emergency stop active; robot queue cleared.")

    def _recovery_callback(self, msg: String) -> None:
        if self._active_job is not None:
            self.get_logger().warning(
                "Recovery received while an executor job is still active; scheduler remains stopped."
            )
            return

        self._emergency_stopped = False
        self.get_logger().info("Robot scheduler recovered and accepting jobs.")
        self._dispatch_next_if_idle()

    def _publish_job_status(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload)
        self.status_pub.publish(msg)

    def _publish_scheduler_alert(self, backend_error: str) -> None:
        msg = String()
        msg.data = json.dumps(
            {
                "key": "robot_scheduler",
                "level": "warning",
                "active": True,
                "message": "Se detectó un problema al gestionar la cola de movimientos del robot.",
                "backend_error": backend_error,
            },
            ensure_ascii=False,
        )
        self.alert_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = RobotSchedulerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
