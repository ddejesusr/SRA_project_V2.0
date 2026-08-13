"""Robot job lifecycle state machine shared by scheduler and executors."""

from enum import Enum

from sra_core import StateMachine, StateMachineDefinition, Transition


class RobotJobState(str, Enum):
    QUEUED = "QUEUED"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    FAILED_SAFE_AT_SOURCE = "FAILED_SAFE_AT_SOURCE"
    POSITION_UNKNOWN = "POSITION_UNKNOWN"
    CANCELLED = "CANCELLED"


class RobotJobEvent(str, Enum):
    DISPATCH = "DISPATCH"
    START = "START"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"
    FAIL_SAFE_AT_SOURCE = "FAIL_SAFE_AT_SOURCE"
    MARK_POSITION_UNKNOWN = "MARK_POSITION_UNKNOWN"
    CANCEL = "CANCEL"


_DEFINITION = StateMachineDefinition.from_iterable(
    [
        Transition(RobotJobState.QUEUED, RobotJobEvent.DISPATCH, RobotJobState.DISPATCHED),
        Transition(RobotJobState.DISPATCHED, RobotJobEvent.START, RobotJobState.RUNNING),
        Transition(RobotJobState.RUNNING, RobotJobEvent.COMPLETE, RobotJobState.COMPLETED),
        Transition(RobotJobState.RUNNING, RobotJobEvent.FAIL, RobotJobState.FAILED),
        Transition(
            RobotJobState.RUNNING,
            RobotJobEvent.FAIL_SAFE_AT_SOURCE,
            RobotJobState.FAILED_SAFE_AT_SOURCE,
        ),
        Transition(
            RobotJobState.RUNNING,
            RobotJobEvent.MARK_POSITION_UNKNOWN,
            RobotJobState.POSITION_UNKNOWN,
        ),
        Transition(RobotJobState.QUEUED, RobotJobEvent.CANCEL, RobotJobState.CANCELLED),
        Transition(RobotJobState.DISPATCHED, RobotJobEvent.CANCEL, RobotJobState.CANCELLED),
        Transition(RobotJobState.RUNNING, RobotJobEvent.CANCEL, RobotJobState.CANCELLED),
    ],
    terminal_states={
        RobotJobState.COMPLETED,
        RobotJobState.FAILED,
        RobotJobState.FAILED_SAFE_AT_SOURCE,
        RobotJobState.POSITION_UNKNOWN,
        RobotJobState.CANCELLED,
    },
)


def make_robot_job_machine(
    state: str | RobotJobState,
) -> StateMachine[RobotJobState, RobotJobEvent]:
    return StateMachine(_DEFINITION, RobotJobState(state))
