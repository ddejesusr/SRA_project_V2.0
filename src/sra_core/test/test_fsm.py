from enum import Enum

import pytest

from sra_core import (
    StateMachine,
    StateMachineDefinition,
    Transition,
    TransitionNotAllowed,
)


class State(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    DONE = "DONE"


class Event(str, Enum):
    START = "START"
    COMPLETE = "COMPLETE"


def make_machine():
    definition = StateMachineDefinition.from_iterable(
        [
            Transition(State.IDLE, Event.START, State.RUNNING),
            Transition(State.RUNNING, Event.COMPLETE, State.DONE),
        ],
        terminal_states={State.DONE},
    )
    return StateMachine(definition, State.IDLE)


def test_machine_applies_explicit_transitions():
    machine = make_machine()
    assert machine.handle(Event.START) is State.RUNNING
    assert machine.handle(Event.COMPLETE) is State.DONE
    assert machine.is_terminal


def test_machine_rejects_invalid_event():
    machine = make_machine()
    with pytest.raises(TransitionNotAllowed):
        machine.handle(Event.COMPLETE)
