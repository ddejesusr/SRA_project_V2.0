from typing import Any, Mapping

from .base import Skill, SkillDefinition


class GetTotalStockSkill(Skill):
    definition = SkillDefinition(
        name="inventory.get_total_stock",
        description=(
            "Return the total number of fuse boxes currently available for "
            "delivery. Reserved stock is excluded."
        ),
        parameters={},
        read_only=True,
    )

    def __init__(self, repository):
        self._repository = repository

    def execute(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if arguments:
            raise ValueError("This skill does not accept arguments")
        return {
            "success": True,
            "available": self._repository.get_total_available(),
        }


class GetStockSkill(Skill):
    definition = SkillDefinition(
        name="inventory.get_stock",
        description=(
            "Return the number of fuse boxes currently available for one exact "
            "configuration code. Reserved stock is excluded."
        ),
        parameters={
            "config_code": {
                "type": "string",
                "description": "Fuse-box configuration: back-top-fuses",
                "required": True,
            }
        },
        read_only=True,
    )

    def __init__(self, repository):
        self._repository = repository

    def execute(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        config_code = str(arguments.get("config_code", "")).strip().lower()
        if not config_code:
            raise ValueError("config_code is required")

        result = self._repository.get_available_by_config(config_code)
        if result is None:
            return {
                "success": False,
                "error": "CONFIGURATION_NOT_FOUND",
                "config_code": config_code,
            }

        return {"success": True, **result}
