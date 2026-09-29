"""CRAFT orchestration of the stateless CrIStMa organic/MOF tool chain."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Iterator

from cristma.crystal_chemistry import (
    CHPiAnalysisResult,
    CHPiAnalyzer,
    CHPiPolicy,
    ContactAnalysisResult,
    IntermolecularContactAnalysisResult,
    IntermolecularContactAnalyzer,
    IntermolecularContactPolicy,
    MolecularAnalysisPolicy,
    MolecularAnalysisResult,
    MolecularAnalyzer,
    MolecularPackingGraph,
    MolecularRingSearchPolicy,
    PackingAnalyzer,
    PiStackingAnalysisResult,
    PiStackingAnalyzer,
    PiStackingPolicy,
    PiSystemAnalysisResult,
    PiSystemAnalyzer,
    PiSystemPolicy,
    ReticularAnalyzer,
    ReticularNetAnalyzer,
    ReticularNetResult,
    ReticularPrecursorGraph,
    SecondaryBuildingUnitAnalyzer,
    SecondaryBuildingUnitResult,
)


class NativeOrganicStage(StrEnum):
    """Progressive CrIStMa result stages exposed to the CRAFT workflow."""

    MOLECULAR = "molecular"
    INTERMOLECULAR = "intermolecular"
    PACKING = "packing"
    RETICULAR_PRECURSOR = "reticular_precursor"
    SBU = "sbu"
    RETICULAR_NET = "reticular_net"


def _default_molecular_policy() -> MolecularAnalysisPolicy:
    return MolecularAnalysisPolicy(maximum_bond_rho=1.35)


@dataclass(frozen=True, slots=True)
class NativeOrganicSettings:
    """Explicit request policies passed unchanged to public CrIStMa analyzers."""

    molecular_policy: MolecularAnalysisPolicy = field(
        default_factory=_default_molecular_policy
    )
    ring_policy: MolecularRingSearchPolicy = field(
        default_factory=MolecularRingSearchPolicy
    )
    intermolecular_policy: IntermolecularContactPolicy = field(
        default_factory=IntermolecularContactPolicy
    )
    pi_system_policy: PiSystemPolicy = field(default_factory=PiSystemPolicy)
    pi_stacking_policy: PiStackingPolicy = field(default_factory=PiStackingPolicy)
    ch_pi_policy: CHPiPolicy = field(default_factory=CHPiPolicy)

    def get_config(self) -> dict[str, object]:
        return {
            "molecular_policy": self.molecular_policy.get_config(),
            "ring_policy": self.ring_policy.get_config(),
            "intermolecular_policy": self.intermolecular_policy.get_config(),
            "pi_system_policy": self.pi_system_policy.get_config(),
            "pi_stacking_policy": self.pi_stacking_policy.get_config(),
            "ch_pi_policy": self.ch_pi_policy.get_config(),
        }

    def clone(self, **changes: object) -> "NativeOrganicSettings":
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class NativeOrganicSnapshot:
    """One immutable progressive view over exact CrIStMa result objects."""

    stage: NativeOrganicStage
    settings: NativeOrganicSettings
    contact_result: ContactAnalysisResult
    molecular: MolecularAnalysisResult
    intermolecular: IntermolecularContactAnalysisResult | None = None
    pi_systems: PiSystemAnalysisResult | None = None
    pi_stacking: PiStackingAnalysisResult | None = None
    ch_pi: CHPiAnalysisResult | None = None
    packing: MolecularPackingGraph | None = None
    reticular_precursor: ReticularPrecursorGraph | None = None
    sbu: SecondaryBuildingUnitResult | None = None
    reticular_net: ReticularNetResult | None = None
    tool_id: str = "craft.cristma_organic"
    tool_version: str = "1"


def iter_analyze_organic(
    contact_result: ContactAnalysisResult,
    settings: NativeOrganicSettings | None = None,
) -> Iterator[NativeOrganicSnapshot]:
    """Compose public CrIStMa analyzers without creating CRAFT science models."""

    if not isinstance(contact_result, ContactAnalysisResult):
        raise TypeError("native organic analysis requires a ContactAnalysisResult")
    settings = settings or NativeOrganicSettings()

    molecular = MolecularAnalyzer(
        settings.molecular_policy,
        settings.ring_policy,
    ).analyze(contact_result)
    yield NativeOrganicSnapshot(
        NativeOrganicStage.MOLECULAR,
        settings,
        contact_result,
        molecular,
    )

    intermolecular = IntermolecularContactAnalyzer(
        settings.intermolecular_policy
    ).analyze(contact_result, molecular)
    pi_systems = PiSystemAnalyzer(settings.pi_system_policy).analyze(
        contact_result,
        molecular,
    )
    yield NativeOrganicSnapshot(
        NativeOrganicStage.INTERMOLECULAR,
        settings,
        contact_result,
        molecular,
        intermolecular=intermolecular,
        pi_systems=pi_systems,
    )

    pi_stacking = PiStackingAnalyzer(settings.pi_stacking_policy).analyze(
        contact_result,
        molecular,
        pi_systems,
    )
    ch_pi = CHPiAnalyzer(settings.ch_pi_policy).analyze(
        contact_result,
        molecular,
        pi_systems,
    )
    packing = PackingAnalyzer().analyze(intermolecular, pi_stacking, ch_pi)
    yield NativeOrganicSnapshot(
        NativeOrganicStage.PACKING,
        settings,
        contact_result,
        molecular,
        intermolecular=intermolecular,
        pi_systems=pi_systems,
        pi_stacking=pi_stacking,
        ch_pi=ch_pi,
        packing=packing,
    )

    reticular_precursor = ReticularAnalyzer().analyze(contact_result, molecular)
    yield NativeOrganicSnapshot(
        NativeOrganicStage.RETICULAR_PRECURSOR,
        settings,
        contact_result,
        molecular,
        intermolecular=intermolecular,
        pi_systems=pi_systems,
        pi_stacking=pi_stacking,
        ch_pi=ch_pi,
        packing=packing,
        reticular_precursor=reticular_precursor,
    )

    sbu = SecondaryBuildingUnitAnalyzer().analyze(reticular_precursor)
    yield NativeOrganicSnapshot(
        NativeOrganicStage.SBU,
        settings,
        contact_result,
        molecular,
        intermolecular=intermolecular,
        pi_systems=pi_systems,
        pi_stacking=pi_stacking,
        ch_pi=ch_pi,
        packing=packing,
        reticular_precursor=reticular_precursor,
        sbu=sbu,
    )

    reticular_net = ReticularNetAnalyzer().analyze(reticular_precursor, sbu)
    yield NativeOrganicSnapshot(
        NativeOrganicStage.RETICULAR_NET,
        settings,
        contact_result,
        molecular,
        intermolecular=intermolecular,
        pi_systems=pi_systems,
        pi_stacking=pi_stacking,
        ch_pi=ch_pi,
        packing=packing,
        reticular_precursor=reticular_precursor,
        sbu=sbu,
        reticular_net=reticular_net,
    )


__all__ = [
    "NativeOrganicSettings",
    "NativeOrganicSnapshot",
    "NativeOrganicStage",
    "iter_analyze_organic",
]
