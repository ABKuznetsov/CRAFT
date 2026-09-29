"""CRAFT presentation models for topology calculated by CrIStMa."""

from __future__ import annotations

from dataclasses import dataclass

from craft.analysis.periodic_graph import Translation


@dataclass(frozen=True, slots=True)
class TopologyComponent:
    id: str
    polyhedron_ids: tuple[str, ...]
    periodic_rank: int
    classification: str
    closure_translations: tuple[Translation, ...]
    directions: tuple[Translation, ...]
    plane_normal: Translation | None
    connection_counts: tuple[tuple[str, int], ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TopologyFamily:
    id: str
    component_ids: tuple[str, ...]
    classification: str
    periodic_rank: int
    directions: tuple[Translation, ...]
    plane_normal: Translation | None
    building_units: tuple[str, ...]
    connection_counts: tuple[tuple[str, int], ...]
    representation: str = "structural"
    distance_range: tuple[float, float] | None = None


@dataclass(frozen=True, slots=True)
class CationTopologyEdge:
    first: str
    second: str
    translation: Translation
    mode: str
    distance: float
    shared_sites: tuple[int, ...] = ()
    connection_kind: str = "nearest"


@dataclass(frozen=True, slots=True)
class InorganicTopologyReport:
    components: tuple[TopologyComponent, ...]
    families: tuple[TopologyFamily, ...]
    structural_polyhedron_ids: frozenset[str]
    warnings: tuple[str, ...]
    interpretable: bool
    cation_components: tuple[TopologyComponent, ...] = ()
    cation_families: tuple[TopologyFamily, ...] = ()
    cation_edges: tuple[CationTopologyEdge, ...] = ()
    cation_polyhedron_ids: frozenset[str] = frozenset()


__all__ = [
    "CationTopologyEdge",
    "InorganicTopologyReport",
    "TopologyComponent",
    "TopologyFamily",
]
