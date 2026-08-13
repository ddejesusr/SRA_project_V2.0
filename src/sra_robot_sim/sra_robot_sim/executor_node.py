#!/usr/bin/env python3
"""Hierarchical simulator for SRA robot STORE and DELIVERY workflows."""

from __future__ import annotations

import json
import os
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from sra_robot_scheduler.lifecycle import (
    RobotJobEvent,
    RobotJobState,
    make_robot_job_machine,
)

from .operation_fsm import OperationEvent, OperationState, make_operation_machine


STEP_EVENTS = {
    OperationState.PREPARE: OperationEvent.READY,
    OperationState.MOVE_TO_PICKUP: OperationEvent.ARRIVED_PICKUP,
    OperationState.PICK: OperationEvent.PICKED,
    OperationState.VERIFY_PICK: OperationEvent.PICK_VERIFIED,
    OperationState.MOVE_TO_DESTINATION: OperationEvent.ARRIVED_DESTINATION,
    OperationState.PLACE: OperationEvent.PLACED,
    OperationState.VERIFY_PLACE: OperationEvent.PLACE_VERIFIED,
    OperationState.RETURN_HOME: OperationEvent.HOME_REACHED,
}


class RobotExecutorSimNode(Node):
    """Execute one scheduled job using nested job/operation state machines."""

    def __init__(self):
        super().__init__("sra_robot_executor_sim")

        self._active_job: dict[str, Any] | None = None
        self._job_machine = None
        self._operation_machine = None
        self._step_period = float(os.getenv("SRA_ROBOT_SIM_STEP_SECONDS", "0.5"))

        self.create_subscription(
            String,
            "/sra/robot/executor/command",
            self._command_callback,
            20,
        )
        self.status_pub = self.create_publisher(
            String,
            "/sra/robot/executor/status",
            20,
        )
        self.create_timer(self._step_period, self._advance_simulation)

        self.get_logger().info(
            f"Hierarchical robot executor simulator ready; step={self._step_period:.2f}s."
        )

    def _command_callback(self, msg: String) -> None:
        try:
            command = json.loads(msg.data)
            if not isinstance(command, dict):
                raise ValueError("Executor command must be a JSON object")

            command_name = str(command.get("command", "")).strip().upper()
            if command_name == "EXECUTE":
                self._start_job(command)
            elif command_name == "CANCEL":
                self._cancel_job(command)
            else:
                raise ValueError(f"Unsupported executor command: {command_name}")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.get_logger().warning(f"Executor command rejected: {exc}")

    def _start_job(self, job: dict[str, Any]) -> None:
        if self._active_job is not None:
            raise ValueError("Executor already has an active job")

        job_type = str(job.get("job_type", "")).strip().upper()
        if job_type not in {"STORE", "DELIVERY"}:
            raise ValueError(f"Unsupported robot job type: {job_type}")
        if not str(job.get("job_id", "")).strip():
            raise ValueError("Robot job is missing job_id")

        self._active_job = dict(job)
        self._job_machine = make_robot_job_machine(RobotJobState.DISPATCHED)
        self._operation_machine = make_operation_machine(OperationState.PREPARE)
        self._job_machine.handle(RobotJobEvent.START)
        self._publish_status()

    def _cancel_job(self, command: dict[str, Any]) -> None:
        if self._active_job is None or self._job_machine is None:
            return

        requested_job_id = str(command.get("job_id", "")).strip()
        active_job_id = str(self._active_job.get("job_id", "")).strip()
        if requested_job_id and requested_job_id != active_job_id:
            raise ValueError(
                f"Cancel job_id mismatch: active={active_job_id}, requested={requested_job_id}"
            )

        if self._job_machine.can_handle(RobotJobEvent.CANCEL):
            self._job_machine.handle(RobotJobEvent.CANCEL)
            self._publish_status(extra={"reason": command.get("reason", "CANCELLED")})
        self._clear_active_job()

    def _advance_simulation(self) -> None:
        if (
            self._active_job is None
            or self._job_machine is None
            or self._operation_machine is None
        ):
            return
        if self._job_machine.state is not RobotJobState.RUNNING:
            return

        current_step = self._operation_machine.state
        event = STEP_EVENTS.get(current_step)
        if event is None:
            return

        self._operation_machine.handle(event)
        if self._operation_machine.is_terminal:
            self._job_machine.handle(RobotJobEvent.COMPLETE)
            self._publish_status()
            self._clear_active_job()
            return

        self._publish_status()

    def _publish_status(self, *, extra: dict[str, Any] | None = None) -> None:
        if self._active_job is None or self._job_machine is None:
            return

        payload = {
            **self._active_job,
            "status": self._job_machine.state.value,
            "step": (
                self._operation_machine.state.value
                if self._operation_machine is not None
                else None
            ),
            **(extra or {}),
        }
        msg = String()
        msg.data = json.dumps(payload)
        self.status_pub.publish(msg)

    def _clear_active_job(self) -> None:
        self._active_job = None
        self._job_machine = None
        self._operation_machine = None


def main(args=None):
    rclpy.init(args=args)
    node = RobotExecutorSimNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
