from sra_robot_sim.operation_fsm import (
    OperationEvent,
    OperationState,
    make_operation_machine,
)


def test_store_or_delivery_operation_follows_physical_sequence():
    machine = make_operation_machine()
    sequence = [
        (OperationEvent.READY, OperationState.MOVE_TO_PICKUP),
        (OperationEvent.ARRIVED_PICKUP, OperationState.PICK),
        (OperationEvent.PICKED, OperationState.VERIFY_PICK),
        (OperationEvent.PICK_VERIFIED, OperationState.MOVE_TO_DESTINATION),
        (OperationEvent.ARRIVED_DESTINATION, OperationState.PLACE),
        (OperationEvent.PLACED, OperationState.VERIFY_PLACE),
        (OperationEvent.PLACE_VERIFIED, OperationState.RETURN_HOME),
        (OperationEvent.HOME_REACHED, OperationState.COMPLETE),
    ]

    for event, expected_state in sequence:
        assert machine.handle(event) is expected_state

    assert machine.is_terminal
