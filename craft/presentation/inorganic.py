"""Immutable UI projections for CRiStMa inorganic results.

These records carry scientific identities and values but do not calculate
crystal chemistry or geometry.
"""

from __future__ import annotations

from dataclasses import dataclass

from craft.analysis.inorganic_classification import CompoundClass


Translation = tuple[int, int, int]
AtomInstanceKey = tuple[str, Translation]


def _require_id(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class AtomOrbitView:
    source_site_id: str
    label: str
    composition_label: str
    atom_ids: tuple[str, ...]
    default_color: str

    def __post_init__(self) -> None:
        _require_id(self.source_site_id, "source_site_id")


@dataclass(frozen=True, slots=True)
class ContactOrbitView:
    contact_orbit_id: str
    label: str
    classification: str
    interaction_layer: str
    instance_count: int
    distance_min: float
    distance_max: float
    initially_visible: bool
    pair_label: str = ""

    def __post_init__(self) -> None:
        _require_id(self.contact_orbit_id, "contact_orbit_id")


@dataclass(frozen=True, slots=True)
class PolyhedronOrbitView:
    polyhedron_orbit_id: str
    representative_polyhedron_id: str
    label: str
    polyhedron_ids: tuple[str, ...]
    coordination_number: int | None
    face_signature: object | None
    default_color: str
    source_site_id: str = ""
    source_shell_id: str = ""
    ligand_site_counts: tuple[tuple[str, int], ...] = ()
    geometry_label: str = ""
    interaction_role: str = ""
    coordination_boundary_key: str = ""

    def __post_init__(self) -> None:
        _require_id(self.polyhedron_orbit_id, "polyhedron_orbit_id")
        _require_id(self.representative_polyhedron_id, "representative_polyhedron_id")


@dataclass(frozen=True, slots=True)
class StructuralBlockView:
    block_id: str
    label: str
    classification: str
    rank: int
    unit_orbit_ids: tuple[str, ...]
    connection_orbit_ids: tuple[str, ...]
    internal_atom_ids: frozenset[str]
    connector_atom_ids: frozenset[str]
    polyhedron_orbit_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.block_id, "block_id")


@dataclass(frozen=True, slots=True)
class RingOrbitView:
    ring_orbit_id: str
    parent_block_id: str
    label: str
    size: int
    scope: str
    multiplicity: int

    def __post_init__(self) -> None:
        _require_id(self.ring_orbit_id, "ring_orbit_id")
        _require_id(self.parent_block_id, "parent_block_id")


@dataclass(frozen=True, slots=True)
class TopologyFamilyView:
    topology_id: str
    label: str
    rank: int
    block_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_id(self.topology_id, "topology_id")


@dataclass(frozen=True, slots=True)
class InorganicPresentation:
    structure_id: str
    structure_name: str
    atom_orbits: tuple[AtomOrbitView, ...]
    contact_orbits: tuple[ContactOrbitView, ...]
    polyhedron_orbits: tuple[PolyhedronOrbitView, ...]
    structural_blocks: tuple[StructuralBlockView, ...]
    rings: tuple[RingOrbitView, ...]
    topology_families: tuple[TopologyFamilyView, ...]
    diagnostics: tuple[object, ...]
    stage: str
    compound_classes: tuple[CompoundClass, ...] = ()
    cation_groups: tuple[CompoundClass, ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.structure_id, "structure_id")

    @staticmethod
    def _find(rows: tuple[object, ...], field_name: str, object_id: str):
        for row in rows:
            if getattr(row, field_name) == object_id:
                return row
        raise KeyError(object_id)

    def atom_orbit(self, source_site_id: str) -> AtomOrbitView:
        return self._find(self.atom_orbits, "source_site_id", source_site_id)

    def polyhedron_orbit(self, polyhedron_orbit_id: str) -> PolyhedronOrbitView:
        return self._find(
            self.polyhedron_orbits,
            "polyhedron_orbit_id",
            polyhedron_orbit_id,
        )

    def block(self, block_id: str) -> StructuralBlockView:
        return self._find(self.structural_blocks, "block_id", block_id)

    def ring(self, ring_orbit_id: str) -> RingOrbitView:
        return self._find(self.rings, "ring_orbit_id", ring_orbit_id)


__all__ = [
    "AtomInstanceKey",
    "AtomOrbitView",
    "ContactOrbitView",
    "InorganicPresentation",
    "PolyhedronOrbitView",
    "RingOrbitView",
    "StructuralBlockView",
    "TopologyFamilyView",
    "Translation",
]
