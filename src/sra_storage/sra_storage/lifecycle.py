"""Storage-slot lifecycle state machine for the 3 x 10 SRA storage grid."""

from enum import Enum

from sra_core import StateMachine, StateMachineDefinition, Transition


class StorageSlotState(str, Enum):
    EMPTY = "EMPTY"
    RESERVED = "RESERVED"
    OCCUPIED = "OCCUPIED"
    UNKNOWN = "UNKNOWN"


class StorageSlotEvent(str, Enum):
    RESERVE = "RESERVE"
    PLACE_CONFIRMED = "PLACE_CONFIRMED"
    RELEASE_RESERVATION = "RELEASE_RESERVATION"
    RETRIEVAL_CONFIRMED = "RETRIEVAL_CONFIRMED"
    MARK_UNKNOWN = "MARK_UNKNOWN"
    RECOVER_EMPTY = "RECOVER_EMPTY"
    RECOVER_OCCUPIED = "RECOVER_OCCUPIED"


_DEFINITION = StateMachineDefinition.from_iterable(
    [
        Transition(StorageSlotState.EMPTY, StorageSlotEvent.RESERVE, StorageSlotState.RESERVED),
        Transition(
            StorageSlotState.RESERVED,
            StorageSlotEvent.PLACE_CONFIRMED,
            StorageSlotState.OCCUPIED,
        ),
        Transition(
            StorageSlotState.RESERVED,
            StorageSlotEvent.RELEASE_RESERVATION,
            StorageSlotState.EMPTY,
        ),
        Transition(
            StorageSlotState.OCCUPIED,
            StorageSlotEvent.RETRIEVAL_CONFIRMED,
            StorageSlotState.EMPTY,
        ),
        Transition(StorageSlotState.RESERVED, StorageSlotEvent.MARK_UNKNOWN, StorageSlotState.UNKNOWN),
        Transition(StorageSlotState.OCCUPIED, StorageSlotEvent.MARK_UNKNOWN, StorageSlotState.UNKNOWN),
        Transition(StorageSlotState.UNKNOWN, StorageSlotEvent.RECOVER_EMPTY, StorageSlotState.EMPTY),
        Transition(
            StorageSlotState.UNKNOWN,
            StorageSlotEvent.RECOVER_OCCUPIED,
            StorageSlotState.OCCUPIED,
        ),
    ]
)


def make_storage_slot_machine(
    state: str | StorageSlotState,
) -> StateMachine[StorageSlotState, StorageSlotEvent]:
    return StateMachine(_DEFINITION, StorageSlotState(state))
