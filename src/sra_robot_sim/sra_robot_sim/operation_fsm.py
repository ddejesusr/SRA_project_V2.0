"""Inner operation-step state machine for robot workflows."""

from enum import Enum

from sra_core import StateMachine, StateMachineDefinition, Transition


class OperationState(str, Enum):
    PREPARE = "PREPARE"
    MOVE_TO_PICKUP = "MOVE_TO_PICKUP"
    PICK = "PICK"
    VERIFY_PICK = "VERIFY_PICK"
    MOVE_TO_DESTINATION = "MOVE_TO_DESTINATION"
    PLACE = "PLACE"
    VERIFY_PLACE = "VERIFY_PLACE"
    RETURN_HOME = "RETURN_HOME"
    COMPLETE = "COMPLETE"


class OperationEvent(str, Enum):
    READY = "READY"
    ARRIVED_PICKUP = "ARRIVED_PICKUP"
    PICKED = "PICKED"
    PICK_VERIFIED = "PICK_VERIFIED"
    ARRIVED_DESTINATION = "ARRIVED_DESTINATION"
    PLACED = "PLACED"
    PLACE_VERIFIED = "PLACE_VERIFIED"
    HOME_REACHED = "HOME_REACHED"


_DEFINITION = StateMachineDefinition.from_iterable(
    [
        Transition(OperationState.PREPARE, OperationEvent.READY, OperationState.MOVE_TO_PICKUP),
        Transition(
            OperationState.MOVE_TO_PICKUP,
            OperationEvent.ARRIVED_PICKUP,
            OperationState.PICK,
        ),
        Transition(OperationState.PICK, OperationEvent.PICKED, OperationState.VERIFY_PICK),
        Transition(
            OperationState.VERIFY_PICK,
            OperationEvent.PICK_VERIFIED,
            OperationState.MOVE_TO_DESTINATION,
        ),
        Transition(
            OperationState.MOVE_TO_DESTINATION,
            OperationEvent.ARRIVED_DESTINATION,
            OperationState.PLACE,
        ),
        Transition(OperationState.PLACE, OperationEvent.PLACED, OperationState.VERIFY_PLACE),
        Transition(
            OperationState.VERIFY_PLACE,
            OperationEvent.PLACE_VERIFIED,
            OperationState.RETURN_HOME,
        ),
        Transition(
            OperationState.RETURN_HOME,
            OperationEvent.HOME_REACHED,
            OperationState.COMPLETE,
        ),
    ],
    terminal_states={OperationState.COMPLETE},
)


def make_operation_machine(
    state: str | OperationState = OperationState.PREPARE,
) -> StateMachine[OperationState, OperationEvent]:
    return StateMachine(_DEFINITION, OperationState(state))
