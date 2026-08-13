import pytest

from sra_core import TransitionNotAllowed
from sra_storage.lifecycle import (
    StorageSlotEvent,
    StorageSlotState,
    make_storage_slot_machine,
)


def test_slot_normal_storage_cycle():
    machine = make_storage_slot_machine(StorageSlotState.EMPTY)
    assert machine.handle(StorageSlotEvent.RESERVE) == StorageSlotState.RESERVED
    assert (
        machine.handle(StorageSlotEvent.PLACE_CONFIRMED)
        == StorageSlotState.OCCUPIED
    )
    assert (
        machine.handle(StorageSlotEvent.RETRIEVAL_CONFIRMED)
        == StorageSlotState.EMPTY
    )


def test_reserved_slot_can_be_released():
    machine = make_storage_slot_machine(StorageSlotState.RESERVED)
    assert (
        machine.handle(StorageSlotEvent.RELEASE_RESERVATION)
        == StorageSlotState.EMPTY
    )


def test_occupied_slot_cannot_be_reserved_again():
    machine = make_storage_slot_machine(StorageSlotState.OCCUPIED)
    with pytest.raises(TransitionNotAllowed):
        machine.handle(StorageSlotEvent.RESERVE)


def test_unknown_slot_requires_explicit_recovery():
    machine = make_storage_slot_machine(StorageSlotState.RESERVED)
    assert machine.handle(StorageSlotEvent.MARK_UNKNOWN) == StorageSlotState.UNKNOWN
    with pytest.raises(TransitionNotAllowed):
        machine.handle(StorageSlotEvent.RESERVE)
    assert (
        machine.handle(StorageSlotEvent.RECOVER_OCCUPIED)
        == StorageSlotState.OCCUPIED
    )
