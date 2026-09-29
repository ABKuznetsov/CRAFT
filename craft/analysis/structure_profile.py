from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class RequestedProfile(StrEnum):
    AUTO = "auto"
    INORGANIC = "inorganic"
    ORGANIC_METAL_ORGANIC = "organic-metal-organic"


class ResolvedProfile(StrEnum):
    INORGANIC = "inorganic"
    MOLECULAR = "molecular"
    RETICULAR = "reticular"


class ProfileConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class ProfileSettings:
    requested: RequestedProfile = RequestedProfile.AUTO

    def validate(self) -> None:
        if not isinstance(self.requested, RequestedProfile):
            raise ValueError("requested profile must be a RequestedProfile")


@dataclass(frozen=True, slots=True)
class ProfileDecision:
    resolved: ResolvedProfile
    score: float
    reasons: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    method_version: str = "structure-profile-v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if not math.isfinite(self.score) or not 0.0 <= self.score <= 1.0:
            raise ValueError("profile score must be finite and between 0 and 1")
        if not self.reasons:
            raise ValueError("profile decision requires evidence")

    @property
    def confidence(self) -> ProfileConfidence:
        if self.score >= 0.8:
            return ProfileConfidence.HIGH
        if self.score >= 0.55:
            return ProfileConfidence.MEDIUM
        return ProfileConfidence.LOW


__all__ = [
    "ProfileConfidence",
    "ProfileDecision",
    "ProfileSettings",
    "RequestedProfile",
    "ResolvedProfile",
]
