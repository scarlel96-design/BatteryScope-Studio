"""Emergency stop acknowledgement is distinct from verified safe state."""

from dataclasses import dataclass
from enum import StrEnum


class StopPhase(StrEnum):
    REQUESTED = "REQUESTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    VERIFIED_OFF = "VERIFIED_OFF"
    FAILED = "FAILED"


@dataclass(frozen=True)
class StopResult:
    phase: StopPhase
    already_safe: bool = False
    detail: str | None = None
