from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from cristma.chemistry import ChemicalDomain, ChemicalClassification


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
    basis: Literal["composition", "structure"] = "structure"

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


def resolve_structure_profile(
    classification: ChemicalClassification,
    requested: RequestedProfile = RequestedProfile.AUTO,
) -> ProfileDecision:
    """Choose CRAFT's analysis route, retaining the basis of manual overrides."""
    if not isinstance(requested, RequestedProfile):
        raise ValueError("requested profile must be a RequestedProfile")
    automatic = {
        ChemicalDomain.ORGANIC: ResolvedProfile.MOLECULAR,
        ChemicalDomain.METAL_ORGANIC: ResolvedProfile.RETICULAR,
    }.get(classification.domain, ResolvedProfile.INORGANIC)
    resolved = automatic
    if requested is RequestedProfile.INORGANIC:
        resolved = ResolvedProfile.INORGANIC
    elif requested is RequestedProfile.ORGANIC_METAL_ORGANIC:
        resolved = automatic if automatic is ResolvedProfile.RETICULAR else ResolvedProfile.MOLECULAR
    reasons = tuple(item.message for item in classification.evidence)
    warnings = tuple(item.message for item in classification.diagnostics)
    if resolved is not automatic:
        reasons += (f"Manual {requested.value} profile overrides candidate {automatic.value} analysis.",)
    return ProfileDecision(
        resolved, classification.confidence, reasons, warnings,
        method_version=f"{classification.method_id}:{classification.method_version}",
        basis="composition",
    )


__all__ = [
    "ProfileConfidence",
    "ProfileDecision",
    "ProfileSettings",
    "RequestedProfile",
    "ResolvedProfile",
    "resolve_structure_profile",
]
