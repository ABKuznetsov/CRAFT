"""CRAFT orchestration of the stateless CRiStMa inorganic tool chain."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Iterator

from cristma.chemistry import (
    ChemistryAnalyzer,
    ChemistryResult,
    Composition,
    InteractionLayer,
)
from cristma.crystal_chemistry import (
    ContactAnalysisResult,
    ContactAnalyzer,
    PeriodicConnectivityAnalyzer,
    PeriodicConnectivityResult,
    PolyhedronOrbitBuildResult,
    PolyhedronOrbitBuilder,
    RingAnalysisResult,
    RingFinder,
    RingSearchPolicy,
    ShellRole,
    ShellResolutionPolicy,
    StructuralBlockFinder,
    StructuralBlockResult,
    StructuralGraphBuilder,
    StructuralRepresentation,
    StructuralRepresentationBuilder,
    StructuralSelectionPolicy,
    StructuralUnitBuildResult,
    StructuralUnitBuilder,
    StructuralUnitGraph,
)
from cristma.crystallography import SymmetryContext
from cristma.structure import CrystalStructure


class NativeInorganicStage(StrEnum):
    """Progressive stages exposed to the CRAFT workflow."""

    CHEMISTRY = "chemistry"
    CONTACTS = "contacts"
    POLYHEDRA = "polyhedra"
    UNITS = "units"
    BLOCKS = "blocks"
    RINGS = "rings"


def _default_shell_policy() -> ShellResolutionPolicy:
    return ShellResolutionPolicy(1.60, 0.01, 0.08, 0.01, 2.0)


def _default_selection_policy() -> StructuralSelectionPolicy:
    return StructuralSelectionPolicy(
        included_layers=frozenset(
            {
                InteractionLayer.STRUCTURAL,
                InteractionLayer.COORDINATION,
                InteractionLayer.INTRA_SUBSYSTEM,
            }
        ),
        included_shell_roles=frozenset({ShellRole.PRIMARY}),
    )


@dataclass(frozen=True, slots=True)
class NativeInorganicSettings:
    """Explicit CRAFT policy for composing independent CRiStMa tools."""

    shell_policy: ShellResolutionPolicy = field(default_factory=_default_shell_policy)
    selection_policy: StructuralSelectionPolicy = field(
        default_factory=_default_selection_policy
    )
    ring_policy: RingSearchPolicy = field(default_factory=RingSearchPolicy)

    def get_config(self) -> dict[str, object]:
        representation = StructuralRepresentationBuilder(self.selection_policy)
        return {
            "shell_policy": self.shell_policy.get_config(),
            "selection_policy": representation.get_config(),
            "ring_policy": self.ring_policy.get_config(),
        }

    def clone(self, **changes: object) -> "NativeInorganicSettings":
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class NativeInorganicSnapshot:
    """One immutable progressive view over exact CRiStMa result objects."""

    stage: NativeInorganicStage
    settings: NativeInorganicSettings
    chemistry: ChemistryResult
    contact_result: ContactAnalysisResult | None = None
    polyhedra: PolyhedronOrbitBuildResult | None = None
    units: StructuralUnitBuildResult | None = None
    unit_graph: StructuralUnitGraph | None = None
    representation: StructuralRepresentation | None = None
    connectivity: PeriodicConnectivityResult | None = None
    blocks: StructuralBlockResult | None = None
    rings: RingAnalysisResult | None = None
    tool_id: str = "craft.cristma_inorganic"
    tool_version: str = "2"


def iter_analyze_inorganic(
    structure: CrystalStructure,
    settings: NativeInorganicSettings | None = None,
) -> Iterator[NativeInorganicSnapshot]:
    """Yield the native inorganic calculation without retaining hidden state."""

    if not isinstance(structure, CrystalStructure):
        raise TypeError("native inorganic analysis requires a CrystalStructure")
    settings = settings or NativeInorganicSettings()
    chemistry = ChemistryAnalyzer().analyze(Composition.from_structure(structure))
    yield NativeInorganicSnapshot(
        NativeInorganicStage.CHEMISTRY,
        settings,
        chemistry,
    )

    if structure.space_group is None:
        raise ValueError("orbit-first analysis requires explicit structure symmetry")
    symmetry_context = SymmetryContext.from_definition(
        structure.space_group,
        structure.cell,
    )
    contact_result = ContactAnalyzer(settings.shell_policy).analyze(
        structure,
        symmetry_context,
        chemistry.grammar,
    )
    yield NativeInorganicSnapshot(
        NativeInorganicStage.CONTACTS,
        settings,
        chemistry,
        contact_result=contact_result,
    )

    # Resolution owns the complete scientific polyhedron model, including
    # stable symmetry-orbit IDs and geometry descriptors.  CRAFT must retain
    # these exact immutable objects instead of rebuilding their hulls.
    polyhedra = PolyhedronOrbitBuilder().build(contact_result)
    yield NativeInorganicSnapshot(
        NativeInorganicStage.POLYHEDRA,
        settings,
        chemistry,
        contact_result=contact_result,
        polyhedra=polyhedra,
    )

    units = StructuralUnitBuilder().build(
        contact_result,
        polyhedra,
    )
    unit_graph = StructuralGraphBuilder().build(contact_result, polyhedra)
    yield NativeInorganicSnapshot(
        NativeInorganicStage.UNITS,
        settings,
        chemistry,
        contact_result=contact_result,
        polyhedra=polyhedra,
        units=units,
        unit_graph=unit_graph,
    )

    representation = StructuralRepresentationBuilder(
        settings.selection_policy
    ).build(unit_graph)
    connectivity = PeriodicConnectivityAnalyzer().analyze(representation)
    blocks = StructuralBlockFinder().find(
        representation,
        connectivity,
    )
    yield NativeInorganicSnapshot(
        NativeInorganicStage.BLOCKS,
        settings,
        chemistry,
        contact_result=contact_result,
        polyhedra=polyhedra,
        units=units,
        unit_graph=unit_graph,
        representation=representation,
        connectivity=connectivity,
        blocks=blocks,
    )

    rings = RingFinder(settings.ring_policy).find(
        representation,
        blocks,
    )
    yield NativeInorganicSnapshot(
        NativeInorganicStage.RINGS,
        settings,
        chemistry,
        contact_result=contact_result,
        polyhedra=polyhedra,
        units=units,
        unit_graph=unit_graph,
        representation=representation,
        connectivity=connectivity,
        blocks=blocks,
        rings=rings,
    )


__all__ = [
    "NativeInorganicSettings",
    "NativeInorganicSnapshot",
    "NativeInorganicStage",
    "iter_analyze_inorganic",
]
