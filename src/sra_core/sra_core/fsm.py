"""Small deterministic finite-state-machine implementation used by SRA V2.

The goal is explicit behavior, not framework magic. Domain modules define states,
events, and allowed transitions. ROS2 nodes remain adapters that translate
messages into events and publish the resulting state changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Hashable, Iterable, Mapping, TypeVar

StateT = TypeVar("StateT", bound=Hashable)
EventT = TypeVar("EventT", bound=Hashable)
Guard = Callable[[dict], bool]
Action = Callable[[dict], None]


class StateMachineError(RuntimeError):
    """Base class for deterministic state-machine failures."""


class TransitionNotAllowed(StateMachineError):
    """Raised when an event has no valid transition from the current state."""


@dataclass(frozen=True)
class Transition(Generic[StateT, EventT]):
    """One explicit state transition."""

    source: StateT
    event: EventT
    target: StateT
    guard: Guard | None = None
    action: Action | None = None


@dataclass(frozen=True)
class StateMachineDefinition(Generic[StateT, EventT]):
    """Immutable transition definition shared by machine instances."""

    transitions: tuple[Transition[StateT, EventT], ...]
    terminal_states: frozenset[StateT] = frozenset()

    @classmethod
    def from_iterable(
        cls,
        transitions: Iterable[Transition[StateT, EventT]],
        *,
        terminal_states: Iterable[StateT] = (),
    ) -> "StateMachineDefinition[StateT, EventT]":
        return cls(tuple(transitions), frozenset(terminal_states))


class StateMachine(Generic[StateT, EventT]):
    """Deterministic runtime state machine with optional guards/actions."""

    def __init__(
        self,
        definition: StateMachineDefinition[StateT, EventT],
        initial_state: StateT,
    ) -> None:
        self.definition = definition
        self.state = initial_state
        self._index = self._build_index(definition.transitions)

    @staticmethod
    def _build_index(
        transitions: Iterable[Transition[StateT, EventT]],
    ) -> Mapping[tuple[StateT, EventT], tuple[Transition[StateT, EventT], ...]]:
        index: dict[tuple[StateT, EventT], list[Transition[StateT, EventT]]] = {}
        for transition in transitions:
            index.setdefault((transition.source, transition.event), []).append(transition)
        return {key: tuple(value) for key, value in index.items()}

    @property
    def is_terminal(self) -> bool:
        return self.state in self.definition.terminal_states

    def can_handle(self, event: EventT, context: dict | None = None) -> bool:
        context = context or {}
        for transition in self._index.get((self.state, event), ()):
            if transition.guard is None or transition.guard(context):
                return True
        return False

    def handle(self, event: EventT, context: dict | None = None) -> StateT:
        """Apply one event and return the new state.

        Exactly one transition must be valid. Multiple valid guarded transitions
        are rejected because ambiguous physical automation behavior is unsafe.
        """
        context = context or {}
        candidates = [
            transition
            for transition in self._index.get((self.state, event), ())
            if transition.guard is None or transition.guard(context)
        ]

        if not candidates:
            raise TransitionNotAllowed(
                f"Event {event!r} is not allowed from state {self.state!r}"
            )
        if len(candidates) > 1:
            raise StateMachineError(
                f"Ambiguous transitions for event {event!r} from state {self.state!r}"
            )

        transition = candidates[0]
        if transition.action is not None:
            transition.action(context)
        self.state = transition.target
        return self.state
