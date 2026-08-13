"""Action skills for deterministic physical delivery requests."""

from typing import Any, Callable, Mapping

from sra_delivery.repository import DeliveryReservationError
from sra_delivery.service import prepare_delivery

from .base import Skill, SkillDefinition


class RequestDeliverySkill(Skill):
    definition = SkillDefinition(
        name="delivery.request",
        description=(
            "Reserve and queue delivery of a specific quantity of physically stored "
            "fuse boxes matching an exact configuration to a destination."
        ),
        parameters={
            "bottom_cover": {
                "type": "string",
                "enum": ["blue", "red", "black"],
                "required": True,
            },
            "top_cover": {
                "type": "string",
                "enum": ["blue", "red"],
                "required": True,
            },
            "fuse_configuration": {
                "type": "string",
                "enum": ["none", "upper", "lower", "both"],
                "required": True,
            },
            "quantity": {
                "type": "integer",
                "minimum": 1,
                "required": True,
            },
            "destination": {
                "type": "string",
                "required": True,
            },
        },
        read_only=False,
    )

    def __init__(self, repository, publish_job: Callable[[dict[str, Any]], None]):
        self._repository = repository
        self._publish_job = publish_job

    def execute(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        required = (
            "bottom_cover",
            "top_cover",
            "fuse_configuration",
            "quantity",
            "destination",
        )
        missing = [key for key in required if arguments.get(key) in (None, "")]
        if missing:
            raise ValueError(f"Missing required delivery arguments: {', '.join(missing)}")

        try:
            prepared = prepare_delivery(
                self._repository,
                bottom_cover=arguments["bottom_cover"],
                top_cover=arguments["top_cover"],
                fuse_configuration=arguments["fuse_configuration"],
                quantity=arguments["quantity"],
                destination=arguments["destination"],
            )
        except DeliveryReservationError as exc:
            detail = str(exc)
            if detail.startswith("Insufficient stored stock:"):
                values = {}
                for fragment in detail.split(":", 1)[1].split(","):
                    key, value = fragment.strip().split("=", 1)
                    values[key] = int(value)
                return {
                    "success": False,
                    "error": "INSUFFICIENT_STOCK",
                    "requested": values.get("requested", 0),
                    "available": values.get("available", 0),
                    "bottom_cover": str(arguments["bottom_cover"]).lower(),
                    "top_cover": str(arguments["top_cover"]).lower(),
                    "fuse_configuration": str(arguments["fuse_configuration"]).lower(),
                }
            raise

        for job in prepared["jobs"]:
            self._publish_job(job)

        return {
            "success": True,
            "request_id": prepared["request_id"],
            "bottom_cover": prepared["bottom_cover"],
            "top_cover": prepared["top_cover"],
            "fuse_configuration": prepared["fuse_configuration"],
            "quantity": prepared["quantity"],
            "destination": prepared["destination"],
            "parts": prepared["parts"],
            "status": "queued",
        }
