from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from craft.analysis.nomenclature import NomenclatureAssignment
    from craft.analysis.structural_domains import StructuralDomain


class HierarchyLevel(StrEnum):
    SITES = "sites"
    ATOMS = "atoms"
    BONDS = "bonds"
    POLYHEDRA = "polyhedra"
    STRUCTURAL_UNITS = "structural_units"
    RIGID_BLOCKS = "rigid_blocks"
    FRAMEWORK = "framework"
    TOPOLOGY = "topology"


@dataclass(frozen=True, slots=True)
class PeriodicSiteRef:
    site_index: int
    image: tuple[int, int, int] = (0, 0, 0)


@dataclass(frozen=True, slots=True)
class CoordinationPolyhedron:
    id: str
    center_index: int
    center_element: str
    ligand_element: str
    ligands: tuple[PeriodicSiteRef, ...]
    bond_lengths: tuple[float, ...]
    vertex_coordinates: tuple[tuple[float, float, float], ...]
    distortion: float | None
    angle_dispersion: float | None
    faces: tuple[tuple[int, ...], ...] = ()
    polyhedron_orbit_id: str = ""
    face_signature: object | None = None
    edge_angle_dispersion_deg: float | None = None

    @property
    def coordination_number(self) -> int:
        return len(self.ligands)

    @property
    def type_name(self) -> str:
        center = f"({self.center_element})" if "/" in self.center_element else self.center_element
        return f"{center}{self.ligand_element}{self.coordination_number}"


@dataclass(frozen=True, slots=True)
class PolyhedronConnection:
    first: str
    second: str
    shared_ligands: tuple[PeriodicSiteRef, ...]
    kind: str
    flexible: bool
    translation: tuple[int, int, int] = (0, 0, 0)


@dataclass(frozen=True, slots=True)
class StructuralUnitGeometryPresentation:
    """Display projection of exact CrIStMa structural-unit geometry."""

    id: str
    kind: str
    affine_dimension: int
    vertex_coordinates: tuple[tuple[float, float, float], ...]
    faces: tuple[tuple[int, ...], ...]
    source_polyhedron_id: str | None = None


@dataclass(frozen=True, slots=True)
class StructuralUnit:
    id: str
    polyhedron_ids: tuple[str, ...]
    atom_indices: tuple[int, ...]
    classification: str
    periodic_rank: int = 0
    orbit_id: str = ""
    geometries: tuple[StructuralUnitGeometryPresentation, ...] = ()


@dataclass(frozen=True, slots=True)
class StructuralBlock:
    id: str
    polyhedron_ids: tuple[str, ...]
    atom_indices: tuple[int, ...]
    classification: str
    rigidity_score: float
    rigidity_index: float
    periodic_rank: int = 0
    orbit_id: str = ""


@dataclass(frozen=True, slots=True)
class FlexibleConnector:
    id: str
    first_block: str
    second_block: str
    first_polyhedron: str
    second_polyhedron: str
    kind: str
    ligand_indices: tuple[int, ...]
    pivot_coordinates: tuple[tuple[float, float, float], ...]
    orbit_id: str = ""


@dataclass(slots=True)
class HierarchyReport:
    """CRAFT projection of immutable scientific hierarchy results."""

    polyhedra: list[CoordinationPolyhedron] = field(default_factory=list)
    polyhedron_connections: list[PolyhedronConnection] = field(default_factory=list)
    structural_units: list[StructuralUnit] = field(default_factory=list)
    blocks: list[StructuralBlock] = field(default_factory=list)
    connectors: list[FlexibleConnector] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    structural_domains: list[StructuralDomain] = field(default_factory=list)
    nomenclature: list[NomenclatureAssignment] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        return {
            "polyhedra": len(self.polyhedra),
            "structural_units": len(self.structural_units),
            "structural_blocks": len(self.blocks),
            "flexible_connectors": len(self.connectors),
        }
