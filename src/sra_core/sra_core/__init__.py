"""Shared deterministic state-machine primitives for SRA V2."""

from .fsm import (
    StateMachine,
    StateMachineDefinition,
    StateMachineError,
    Transition,
    TransitionNotAllowed,
)

__all__ = [
    "StateMachine",
    "StateMachineDefinition",
    "StateMachineError",
    "Transition",
    "TransitionNotAllowed",
]
