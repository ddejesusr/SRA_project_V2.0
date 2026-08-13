from typing import Any, Mapping

from .base import Skill, SkillDefinition


BOTTOM_COVERS = {"blue", "red", "black"}
TOP_COVERS = {"blue", "red"}
FUSE_CONFIGURATIONS = {"none", "upper", "lower", "both"}


class GetTotalStockSkill(Skill):
    definition = SkillDefinition(
        name="inventory.get_total_stock",
        description=(
            "Return the total number of fuse boxes currently available for "
            "delivery across all configurations. Use this for overall/total stock "
            "questions when the operator does not request a specific configuration. "
            "Reserved stock is excluded."
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
            "physical configuration. Reserved stock is excluded."
        ),
        parameters={
            "bottom_cover": {
                "type": "string",
                "enum": ["blue", "red", "black"],
                "description": (
                    "Bottom/back cover color. Spanish: cubierta inferior/trasera "
                    "azul=blue, roja=red, negra=black."
                ),
                "required": True,
            },
            "top_cover": {
                "type": "string",
                "enum": ["blue", "red"],
                "description": (
                    "Top/front cover color. Spanish: tapa superior/frontal "
                    "azul=blue, roja=red."
                ),
                "required": True,
            },
            "fuse_configuration": {
                "type": "string",
                "enum": ["none", "upper", "lower", "both"],
                "description": (
                    "Fuse configuration. Spanish: sin fusibles=none, fusible "
                    "superior=upper, fusible inferior=lower, ambos fusibles=both."
                ),
                "required": True,
            },
        },
        read_only=True,
    )

    def __init__(self, repository):
        self._repository = repository

    def execute(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        bottom_cover = str(arguments.get("bottom_cover", "")).strip().lower()
        top_cover = str(arguments.get("top_cover", "")).strip().lower()
        fuse_configuration = str(arguments.get("fuse_configuration", "")).strip().lower()

        if bottom_cover not in BOTTOM_COVERS:
            raise ValueError(f"Invalid bottom_cover: {bottom_cover}")
        if top_cover not in TOP_COVERS:
            raise ValueError(f"Invalid top_cover: {top_cover}")
        if fuse_configuration not in FUSE_CONFIGURATIONS:
            raise ValueError(f"Invalid fuse_configuration: {fuse_configuration}")

        config_code = f"{bottom_cover}-{top_cover}-{fuse_configuration}"
        result = self._repository.get_available_by_config(config_code)
        if result is None:
            return {
                "success": False,
                "error": "CONFIGURATION_NOT_FOUND",
                "config_code": config_code,
            }

        return {"success": True, **result}
