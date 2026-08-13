"""Deterministic Festo CP Lab State Code model.

Carrier ID identifies which physical carrier is transporting the product.
State Code identifies the last successfully completed Festo process state.
This module contains no PLC or database access; it defines the backend domain
rules used by production tracking and OPC UA event handling.
"""

from dataclasses import dataclass
from enum import Enum


class FestoProcessState(str, Enum):
    INITIAL = "INITIAL"
    CAMERA_COMPLETED = "CAMERA_COMPLETED"
    DRILLING_COMPLETED = "DRILLING_COMPLETED"
    BLUE_STAGE_COMPLETED_RED_REQUIRED = "BLUE_STAGE_COMPLETED_RED_REQUIRED"
    BLUE_COVER_INSTALLED = "BLUE_COVER_INSTALLED"
    TOP_COVER_COMPLETED_BLUE = "TOP_COVER_COMPLETED_BLUE"
    TOP_COVER_COMPLETED_RED = "TOP_COVER_COMPLETED_RED"
    PRESS_COMPLETED_BLUE = "PRESS_COMPLETED_BLUE"
    PRESS_COMPLETED_RED = "PRESS_COMPLETED_RED"
    LABELING_COMPLETED_BLUE = "LABELING_COMPLETED_BLUE"
    LABELING_COMPLETED_RED = "LABELING_COMPLETED_RED"
    DISPATCH_COMPLETED_BLUE = "DISPATCH_COMPLETED_BLUE"
    DISPATCH_COMPLETED_RED = "DISPATCH_COMPLETED_RED"


@dataclass(frozen=True)
class StateCodeInfo:
    state_code: int
    process_state: FestoProcessState
    top_cover: str | None


STATE_CODES: dict[int, StateCodeInfo] = {
    0: StateCodeInfo(0, FestoProcessState.INITIAL, None),
    100: StateCodeInfo(100, FestoProcessState.CAMERA_COMPLETED, None),
    200: StateCodeInfo(200, FestoProcessState.DRILLING_COMPLETED, None),
    300: StateCodeInfo(
        300,
        FestoProcessState.BLUE_STAGE_COMPLETED_RED_REQUIRED,
        "red",
    ),
    301: StateCodeInfo(301, FestoProcessState.BLUE_COVER_INSTALLED, "blue"),
    401: StateCodeInfo(401, FestoProcessState.TOP_COVER_COMPLETED_BLUE, "blue"),
    402: StateCodeInfo(402, FestoProcessState.TOP_COVER_COMPLETED_RED, "red"),
    501: StateCodeInfo(501, FestoProcessState.PRESS_COMPLETED_BLUE, "blue"),
    502: StateCodeInfo(502, FestoProcessState.PRESS_COMPLETED_RED, "red"),
    601: StateCodeInfo(601, FestoProcessState.LABELING_COMPLETED_BLUE, "blue"),
    602: StateCodeInfo(602, FestoProcessState.LABELING_COMPLETED_RED, "red"),
    701: StateCodeInfo(701, FestoProcessState.DISPATCH_COMPLETED_BLUE, "blue"),
    702: StateCodeInfo(702, FestoProcessState.DISPATCH_COMPLETED_RED, "red"),
}


VALID_TRANSITIONS: frozenset[tuple[int, int]] = frozenset(
    {
        (0, 100),
        (100, 200),
        (200, 300),
        (200, 301),
        (300, 402),
        (301, 401),
        (401, 501),
        (402, 502),
        (501, 601),
        (502, 602),
        (601, 701),
        (602, 702),
    }
)


def get_state_info(state_code: int) -> StateCodeInfo:
    """Return canonical metadata for a known Festo State Code."""
    try:
        return STATE_CODES[int(state_code)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Unknown Festo State Code: {state_code}") from exc


def is_valid_transition(from_state: int, to_state: int) -> bool:
    """Return whether a product may progress directly between two states.

    Repeated reads of the same State Code are valid observations but are not
    process transitions. Carrier reset/reuse is intentionally handled outside
    this product progression model.
    """
    get_state_info(from_state)
    get_state_info(to_state)
    if from_state == to_state:
        return True
    return (from_state, to_state) in VALID_TRANSITIONS


def infer_top_cover(state_code: int) -> str | None:
    """Infer the confirmed top-cover branch encoded by a State Code."""
    return get_state_info(state_code).top_cover
