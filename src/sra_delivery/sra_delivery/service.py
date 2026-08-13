"""Reusable delivery application service shared by ROS adapters and skills."""

from __future__ import annotations

from typing import Any

from .repository import DeliveryRepository, DeliveryReservationError

BOTTOM_COVERS = {"blue", "red", "black"}
TOP_COVERS = {"blue", "red"}
FUSE_CONFIGURATIONS = {"none", "upper", "lower", "both"}


def prepare_delivery(
    repository: DeliveryRepository,
    *,
    bottom_cover: str,
    top_cover: str,
    fuse_configuration: str,
    quantity: int,
    destination: str,
) -> dict[str, Any]:
    """Validate a request, reserve exact parts, and build scheduler job payloads."""
    bottom_cover = str(bottom_cover).strip().lower()
    top_cover = str(top_cover).strip().lower()
    fuse_configuration = str(fuse_configuration).strip().lower()
    destination = str(destination).strip()

    if bottom_cover not in BOTTOM_COVERS:
        raise DeliveryReservationError(f"Invalid bottom cover: {bottom_cover}")
    if top_cover not in TOP_COVERS:
        raise DeliveryReservationError(f"Invalid top cover: {top_cover}")
    if fuse_configuration not in FUSE_CONFIGURATIONS:
        raise DeliveryReservationError(
            f"Invalid fuse configuration: {fuse_configuration}"
        )
    if not destination:
        raise DeliveryReservationError("Delivery destination is required")

    try:
        quantity = int(quantity)
    except (TypeError, ValueError) as exc:
        raise DeliveryReservationError(f"Invalid delivery quantity: {quantity}") from exc
    if quantity <= 0:
        raise DeliveryReservationError("Delivery quantity must be greater than zero")

    reserved = repository.create_request(
        bottom_cover=bottom_cover,
        top_cover=top_cover,
        fuse_configuration=fuse_configuration,
        quantity=quantity,
        destination=destination,
    )

    jobs = [
        {
            "job_id": item["job_id"],
            "job_type": "DELIVERY",
            "request_id": reserved["request_id"],
            "part_number": item["part_number"],
            "source": "STORAGE",
            "slot_id": item["slot_id"],
            "destination": destination,
        }
        for item in reserved["items"]
    ]

    return {
        "request_id": reserved["request_id"],
        "bottom_cover": bottom_cover,
        "top_cover": top_cover,
        "fuse_configuration": fuse_configuration,
        "quantity": quantity,
        "destination": destination,
        "parts": [job["part_number"] for job in jobs],
        "jobs": jobs,
    }
