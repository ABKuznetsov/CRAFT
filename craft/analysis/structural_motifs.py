"""Calculation-free presentation records for CRiStMa structural motifs."""

from __future__ import annotations

from dataclasses import dataclass

from craft.analysis.hierarchy import PeriodicSiteRef


Translation = tuple[int, int, int]

RING_SCOPE_LABELS = {
    "local": "Local",
    "framework": "Framework",
}
RING_SCOPE_COLORS = {
    "local": "#d95f02",
    "framework": "#1f78b4",
}


@dataclass(frozen=True, slots=True)
class PeriodicPolyhedronRef:
    polyhedron_id: str
    cell_translation: Translation = (0, 0, 0)


@dataclass(frozen=True, slots=True)
class StructuralRingInstancePresentation:
    ring_id: str
    parent_block_id: str
    member_polyhedra: tuple[PeriodicPolyhedronRef, ...]
    connector_sites: tuple[PeriodicSiteRef, ...]
    formula: str
    size: int
    scope: str = "local"


@dataclass(frozen=True, slots=True)
class StructuralRingOrbitPresentation:
    orbit_id: str
    parent_block_id: str
    representative_ring_id: str
    instances: tuple[StructuralRingInstancePresentation, ...]
    formula: str
    size: int
    scope: str = "local"
    parent_block_orbit_id: str = ""
    symmetry_multiplicity: int = 1

    @property
    def multiplicity(self) -> int:
        return self.symmetry_multiplicity

    @property
    def polyhedron_ids(self) -> tuple[str, ...]:
        """Representative geometry IDs for compact legends and summaries."""
        representative = next(
            (
                item
                for item in self.instances
                if item.ring_id == self.representative_ring_id
            ),
            self.instances[0],
        )
        return tuple(dict.fromkeys(
            item.polyhedron_id for item in representative.member_polyhedra
        ))


@dataclass(frozen=True, slots=True)
class StructuralMotifPresentation:
    ring_orbits: tuple[StructuralRingOrbitPresentation, ...] = ()
    complete: bool = True
    warnings: tuple[str, ...] = ()


__all__ = [
    "PeriodicPolyhedronRef",
    "RING_SCOPE_COLORS",
    "RING_SCOPE_LABELS",
    "StructuralMotifPresentation",
    "StructuralRingInstancePresentation",
    "StructuralRingOrbitPresentation",
]
