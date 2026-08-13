from collections.abc import Iterable
from typing import Any

from .base import Skill


class SkillRegistry:
    """Registry of deterministic capabilities available to the agent."""

    def __init__(self, skills: Iterable[Skill] | None = None):
        self._skills: dict[str, Skill] = {}
        for skill in skills or []:
            self.register(skill)

    def register(self, skill: Skill) -> None:
        name = skill.definition.name
        if name in self._skills:
            raise ValueError(f"Skill already registered: {name}")
        self._skills[name] = skill

    def definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": skill.definition.name,
                "description": skill.definition.description,
                "parameters": dict(skill.definition.parameters),
                "read_only": skill.definition.read_only,
            }
            for skill in self._skills.values()
        ]

    def execute(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        skill = self._skills.get(name)
        if skill is None:
            return {
                "success": False,
                "error": "UNKNOWN_SKILL",
                "skill": name,
            }

        try:
            return skill.execute(arguments or {})
        except ValueError as exc:
            return {
                "success": False,
                "error": "INVALID_ARGUMENTS",
                "detail": str(exc),
                "skill": name,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": "SKILL_EXECUTION_FAILED",
                "detail": str(exc),
                "skill": name,
            }
