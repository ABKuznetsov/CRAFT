"""CRAFT orchestration of the stateless CRiStMa inorganic tool chain."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Iterator

from cristma.chemistry import (
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

from craft.analysis.chemical_classification import CompositionAnalysis, analyze_composition
from craft.analysis.chemical_rules import chemical_rules_config
from craft.analysis.inorganic_classification import (
    InorganicClassification, classify_inorganic, needs_outer_shell_evidence,
)
from craft.analysis.inorganic_subtypes import classify_polymerization
from craft.analysis.coordination_organization import classify_coordination_organization, sharing_capability


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
                InteractionLayer.INTRAMOLECULAR,
                InteractionLayer.METALLIC,
            }
        ),
        included_shell_roles=frozenset({ShellRole.PRIMARY}),
    )


def _default_class_ring_policy() -> RingSearchPolicy:
    # Class motifs are counted in T centres. The native T–O incidence graph
    # alternates centres and oxygen, so a centre budget needs twice as many
    # graph vertices. This policy is independent of any compound or ring size.
    policy = RingSearchPolicy()
    return policy.clone(maximum_ring_size=2 * policy.maximum_ring_size)


@dataclass(frozen=True, slots=True)
class NativeInorganicSettings:
    """Explicit CRAFT policy for composing independent CRiStMa tools."""

    shell_policy: ShellResolutionPolicy = field(default_factory=_default_shell_policy)
    selection_policy: StructuralSelectionPolicy = field(
        default_factory=_default_selection_policy
    )
    ring_policy: RingSearchPolicy = field(default_factory=RingSearchPolicy)
    class_ring_policy: RingSearchPolicy = field(default_factory=_default_class_ring_policy)
    class_subsystem_revision: int = 5

    def __post_init__(self) -> None:
        if self.class_subsystem_revision not in {2, 3, 4, 5}:
            raise ValueError("Unsupported class-subsystem revision.")

    def get_config(self) -> dict[str, object]:
        representation = StructuralRepresentationBuilder(self.selection_policy)
        return {
            "chemical_rules": chemical_rules_config(),
            "shell_policy": self.shell_policy.get_config(),
            "selection_policy": representation.get_config(),
            "ring_policy": self.ring_policy.get_config(),
            "class_ring_policy": self.class_ring_policy.get_config(),
            "class_subsystem": f"craft.native_class_subsystems:{self.class_subsystem_revision}",
            "polyhedron_sharing": sharing_capability(),
            "coordination_boundaries": "craft.native_coordination_boundaries:1",
            "anion_attachment": "craft.native_anion_attachment:1",
        }

    def clone(self, **changes: object) -> "NativeInorganicSettings":
        return replace(self, **changes)

    def with_contact_limit(self, rho: float) -> "NativeInorganicSettings":
        """Keep the search beyond the candidate cutoff for shell resolution."""
        search_margin = 0.4
        policy = self.shell_policy.clone(
            candidate_rho_max=rho,
            search_rho_max=max(self.shell_policy.search_rho_max, rho + search_margin),
        )
        return self.clone(shell_policy=policy)


@dataclass(frozen=True, slots=True)
class NativeInorganicSnapshot:
    """One immutable progressive view over exact CRiStMa result objects."""

    stage: NativeInorganicStage
    settings: NativeInorganicSettings
    chemistry: CompositionAnalysis
    contact_result: ContactAnalysisResult | None = None
    polyhedra: PolyhedronOrbitBuildResult | None = None
    units: StructuralUnitBuildResult | None = None
    unit_graph: StructuralUnitGraph | None = None
    representation: StructuralRepresentation | None = None
    connectivity: PeriodicConnectivityResult | None = None
    blocks: StructuralBlockResult | None = None
    rings: RingAnalysisResult | None = None
    classification: InorganicClassification | None = None
    tool_id: str = "craft.cristma_inorganic"
    tool_version: str = "14"


def iter_analyze_inorganic(
    structure: CrystalStructure,
    settings: NativeInorganicSettings | None = None,
) -> Iterator[NativeInorganicSnapshot]:
    """Yield the native inorganic calculation without retaining hidden state."""

    if not isinstance(structure, CrystalStructure):
        raise TypeError("native inorganic analysis requires a CrystalStructure")
    settings = settings or NativeInorganicSettings()
    chemistry = analyze_composition(Composition.from_structure(structure))
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
    if (
        "O" in chemistry.composition.elements
        and settings.shell_policy.search_rho_max < 3.0
        and needs_outer_shell_evidence(structure, contact_result)
    ):
        # A bounded retry observes the outside of isolated oxyanion shells.
        # Already resolved models retain their original search and results.
        settings = settings.clone(shell_policy=settings.shell_policy.clone(search_rho_max=3.0))
        contact_result = ContactAnalyzer(settings.shell_policy).analyze(
            structure, symmetry_context, chemistry.grammar,
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
    classification = classify_inorganic(structure, contact_result, polyhedra)
    yield NativeInorganicSnapshot(
        NativeInorganicStage.POLYHEDRA,
        settings,
        chemistry,
        contact_result=contact_result,
        polyhedra=polyhedra,
        classification=classification,
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
        classification=classification,
    )

    representation = StructuralRepresentationBuilder(
        settings.selection_policy
    ).build(unit_graph)
    connectivity = PeriodicConnectivityAnalyzer().analyze(representation)
    blocks = StructuralBlockFinder().find(
        representation,
        connectivity,
    )
    classification = classify_polymerization(
        structure, polyhedra, unit_graph, classification, settings.class_ring_policy,
        contacts=contact_result, units=units,
        subsystem_revision=settings.class_subsystem_revision,
    )
    classification = classify_coordination_organization(
        structure, contact_result, polyhedra, units, unit_graph, classification, settings.ring_policy,
        subsystem_revision=settings.class_subsystem_revision,
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
        classification=classification,
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
        classification=classification,
    )


__all__ = [
    "NativeInorganicSettings",
    "NativeInorganicSnapshot",
    "NativeInorganicStage",
    "iter_analyze_inorganic",
]
