"""Hierarchical production lifecycle state machines for SRA V2."""

from __future__ import annotations

from enum import Enum

from sra_core import StateMachine, StateMachineDefinition, Transition


class CarrierState(str, Enum):
    AVAILABLE = "AVAILABLE"
    IN_USE = "IN_USE"
    UNKNOWN = "UNKNOWN"


class CarrierEvent(str, Enum):
    ASSIGN_PRODUCT = "ASSIGN_PRODUCT"
    DISPATCH_HANDOFF = "DISPATCH_HANDOFF"
    MARK_UNKNOWN = "MARK_UNKNOWN"
    RECOVER_AVAILABLE = "RECOVER_AVAILABLE"


CARRIER_DEFINITION = StateMachineDefinition.from_iterable(
    [
        Transition(CarrierState.AVAILABLE, CarrierEvent.ASSIGN_PRODUCT, CarrierState.IN_USE),
        Transition(CarrierState.IN_USE, CarrierEvent.DISPATCH_HANDOFF, CarrierState.AVAILABLE),
        Transition(CarrierState.AVAILABLE, CarrierEvent.MARK_UNKNOWN, CarrierState.UNKNOWN),
        Transition(CarrierState.IN_USE, CarrierEvent.MARK_UNKNOWN, CarrierState.UNKNOWN),
        Transition(CarrierState.UNKNOWN, CarrierEvent.RECOVER_AVAILABLE, CarrierState.AVAILABLE),
    ]
)


class ProductLifecycleState(str, Enum):
    IN_PRODUCTION = "IN_PRODUCTION"
    WAITING_PICKUP = "WAITING_PICKUP"
    STORAGE_RESERVED = "STORAGE_RESERVED"
    STORED = "STORED"
    DELIVERY_RESERVED = "DELIVERY_RESERVED"
    DELIVERED = "DELIVERED"
    POSITION_UNKNOWN = "POSITION_UNKNOWN"
    SCRAPPED = "SCRAPPED"


class ProductLifecycleEvent(str, Enum):
    DISPATCH_COMPLETE = "DISPATCH_COMPLETE"
    RESERVE_STORAGE = "RESERVE_STORAGE"
    STORAGE_COMPLETE = "STORAGE_COMPLETE"
    RELEASE_STORAGE = "RELEASE_STORAGE"
    RESERVE_DELIVERY = "RESERVE_DELIVERY"
    DELIVERY_COMPLETE = "DELIVERY_COMPLETE"
    RELEASE_DELIVERY = "RELEASE_DELIVERY"
    MARK_POSITION_UNKNOWN = "MARK_POSITION_UNKNOWN"
    RECOVER_WAITING_PICKUP = "RECOVER_WAITING_PICKUP"
    RECOVER_STORED = "RECOVER_STORED"
    RECOVER_DELIVERED = "RECOVER_DELIVERED"
    SCRAP = "SCRAP"


PRODUCT_DEFINITION = StateMachineDefinition.from_iterable(
    [
        Transition(
            ProductLifecycleState.IN_PRODUCTION,
            ProductLifecycleEvent.DISPATCH_COMPLETE,
            ProductLifecycleState.WAITING_PICKUP,
        ),
        Transition(
            ProductLifecycleState.WAITING_PICKUP,
            ProductLifecycleEvent.RESERVE_STORAGE,
            ProductLifecycleState.STORAGE_RESERVED,
        ),
        Transition(
            ProductLifecycleState.STORAGE_RESERVED,
            ProductLifecycleEvent.STORAGE_COMPLETE,
            ProductLifecycleState.STORED,
        ),
        Transition(
            ProductLifecycleState.STORAGE_RESERVED,
            ProductLifecycleEvent.RELEASE_STORAGE,
            ProductLifecycleState.WAITING_PICKUP,
        ),
        Transition(
            ProductLifecycleState.STORAGE_RESERVED,
            ProductLifecycleEvent.MARK_POSITION_UNKNOWN,
            ProductLifecycleState.POSITION_UNKNOWN,
        ),
        Transition(
            ProductLifecycleState.STORED,
            ProductLifecycleEvent.RESERVE_DELIVERY,
            ProductLifecycleState.DELIVERY_RESERVED,
        ),
        Transition(
            ProductLifecycleState.DELIVERY_RESERVED,
            ProductLifecycleEvent.DELIVERY_COMPLETE,
            ProductLifecycleState.DELIVERED,
        ),
        Transition(
            ProductLifecycleState.DELIVERY_RESERVED,
            ProductLifecycleEvent.RELEASE_DELIVERY,
            ProductLifecycleState.STORED,
        ),
        Transition(
            ProductLifecycleState.DELIVERY_RESERVED,
            ProductLifecycleEvent.MARK_POSITION_UNKNOWN,
            ProductLifecycleState.POSITION_UNKNOWN,
        ),
        Transition(
            ProductLifecycleState.POSITION_UNKNOWN,
            ProductLifecycleEvent.RECOVER_WAITING_PICKUP,
            ProductLifecycleState.WAITING_PICKUP,
        ),
        Transition(
            ProductLifecycleState.POSITION_UNKNOWN,
            ProductLifecycleEvent.RECOVER_STORED,
            ProductLifecycleState.STORED,
        ),
        Transition(
            ProductLifecycleState.POSITION_UNKNOWN,
            ProductLifecycleEvent.RECOVER_DELIVERED,
            ProductLifecycleState.DELIVERED,
        ),
        Transition(
            ProductLifecycleState.IN_PRODUCTION,
            ProductLifecycleEvent.SCRAP,
            ProductLifecycleState.SCRAPPED,
        ),
        Transition(
            ProductLifecycleState.WAITING_PICKUP,
            ProductLifecycleEvent.SCRAP,
            ProductLifecycleState.SCRAPPED,
        ),
        Transition(
            ProductLifecycleState.POSITION_UNKNOWN,
            ProductLifecycleEvent.SCRAP,
            ProductLifecycleState.SCRAPPED,
        ),
    ],
    terminal_states={ProductLifecycleState.DELIVERED, ProductLifecycleState.SCRAPPED},
)


def make_carrier_machine(state: str | CarrierState) -> StateMachine[CarrierState, CarrierEvent]:
    return StateMachine(CARRIER_DEFINITION, CarrierState(state))


def make_product_machine(
    state: str | ProductLifecycleState,
) -> StateMachine[ProductLifecycleState, ProductLifecycleEvent]:
    return StateMachine(PRODUCT_DEFINITION, ProductLifecycleState(state))
