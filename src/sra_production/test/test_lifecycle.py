import pytest

from sra_core import TransitionNotAllowed
from sra_production.lifecycle import (
    CarrierEvent,
    CarrierState,
    ProductLifecycleEvent,
    ProductLifecycleState,
    make_carrier_machine,
    make_product_machine,
)


def test_carrier_normal_lifecycle():
    machine = make_carrier_machine(CarrierState.AVAILABLE)
    assert machine.handle(CarrierEvent.ASSIGN_PRODUCT) == CarrierState.IN_USE
    assert machine.handle(CarrierEvent.DISPATCH_HANDOFF) == CarrierState.AVAILABLE


def test_carrier_cannot_be_assigned_twice():
    machine = make_carrier_machine(CarrierState.IN_USE)
    with pytest.raises(TransitionNotAllowed):
        machine.handle(CarrierEvent.ASSIGN_PRODUCT)


def test_product_store_lifecycle():
    machine = make_product_machine(ProductLifecycleState.IN_PRODUCTION)
    assert (
        machine.handle(ProductLifecycleEvent.DISPATCH_COMPLETE)
        == ProductLifecycleState.WAITING_PICKUP
    )
    assert (
        machine.handle(ProductLifecycleEvent.RESERVE_STORAGE)
        == ProductLifecycleState.STORAGE_RESERVED
    )
    assert (
        machine.handle(ProductLifecycleEvent.STORAGE_COMPLETE)
        == ProductLifecycleState.STORED
    )


def test_product_storage_failure_can_return_to_dispatch():
    machine = make_product_machine(ProductLifecycleState.STORAGE_RESERVED)
    assert (
        machine.handle(ProductLifecycleEvent.RELEASE_STORAGE)
        == ProductLifecycleState.WAITING_PICKUP
    )


def test_product_unknown_position_requires_explicit_recovery():
    machine = make_product_machine(ProductLifecycleState.STORAGE_RESERVED)
    assert (
        machine.handle(ProductLifecycleEvent.MARK_POSITION_UNKNOWN)
        == ProductLifecycleState.POSITION_UNKNOWN
    )
    with pytest.raises(TransitionNotAllowed):
        machine.handle(ProductLifecycleEvent.RESERVE_STORAGE)
    assert (
        machine.handle(ProductLifecycleEvent.RECOVER_STORED)
        == ProductLifecycleState.STORED
    )


def test_delivered_product_is_terminal():
    machine = make_product_machine(ProductLifecycleState.DELIVERY_RESERVED)
    assert (
        machine.handle(ProductLifecycleEvent.DELIVERY_COMPLETE)
        == ProductLifecycleState.DELIVERED
    )
    assert machine.is_terminal
