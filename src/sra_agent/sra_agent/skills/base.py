from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SkillDefinition:
    """Metadata exposed to the agent for skill selection and argument extraction."""

    name: str
    description: str
    parameters: Mapping[str, Any]
    read_only: bool = True


class Skill(ABC):
    """Deterministic backend capability invoked by the conversational agent."""

    definition: SkillDefinition

    @abstractmethod
    def execute(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Execute validated backend logic and return a structured result."""
        raise NotImplementedError
