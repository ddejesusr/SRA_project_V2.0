"""Natural Spanish presentation for operator-facing skill results.

Backend identifiers remain canonical English values. This module is the only
place where current skill results are converted into Spanish text for TTS or
frontend use. Internal configuration codes must not leak into normal operator
responses.
"""

from typing import Any


COLOR_ES = {
    "blue": "azul",
    "red": "roja",
    "black": "negra",
}

TOP_COLOR_ES = {
    "blue": "azul",
    "red": "roja",
}

FUSE_ES = {
    "none": "sin fusibles",
    "upper": "con el fusible superior",
    "lower": "con el fusible inferior",
    "both": "con ambos fusibles",
}


def describe_configuration(config_code: str) -> str:
    """Convert a canonical backend configuration code into natural Spanish."""
    try:
        bottom, top, fuse = config_code.split("-", 2)
    except ValueError:
        return "de la configuración solicitada"

    bottom_es = COLOR_ES.get(bottom)
    top_es = TOP_COLOR_ES.get(top)
    fuse_es = FUSE_ES.get(fuse)
    if not all((bottom_es, top_es, fuse_es)):
        return "de la configuración solicitada"

    return (
        f"con cubierta inferior {bottom_es}, "
        f"tapa superior {top_es} y {fuse_es}"
    )


def _box_count_phrase(quantity: int) -> str:
    if quantity == 1:
        return "una caja de fusibles disponible"
    return f"{quantity} cajas de fusibles disponibles"


def format_skill_response(skill_name: str, result: dict[str, Any]) -> str:
    """Return natural Spanish text without changing backend facts."""
    if result.get("success"):
        if skill_name == "inventory.get_total_stock":
            quantity = int(result["available"])
            return f"Actualmente tenemos {_box_count_phrase(quantity)}."

        if skill_name == "inventory.get_stock":
            quantity = int(result["available"])
            description = describe_configuration(result["config_code"])
            if quantity == 0:
                return f"Ahora mismo no tenemos cajas de fusibles {description}."
            if quantity == 1:
                return f"Actualmente tenemos una caja de fusibles disponible {description}."
            return (
                f"Actualmente tenemos {quantity} cajas de fusibles disponibles "
                f"{description}."
            )

    error = result.get("error")
    if error == "CONFIGURATION_NOT_FOUND":
        return "No encontré esa configuración de caja de fusibles en el sistema."
    if error == "INVALID_ARGUMENTS":
        return "Me faltan datos para completar esa solicitud."
    if error == "UNKNOWN_SKILL":
        return "Esa función todavía no está disponible."
    return "No pude completar la consulta solicitada."
