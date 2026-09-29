"""Immutable motif-graph projections of orbit-first CrIStMa results."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import math
from types import MappingProxyType
from typing import Mapping, Protocol

import networkx as nx

from craft.core.document import StructureDocument


OccupancyDistribution = tuple[tuple[str, float], ...]
Translation = tuple[int, int, int]


class LatticeImageSearchError(ValueError):
    """Retained for cached-error compatibility with older CRAFT documents."""


class MotifGraphBudget(Protocol):
    """Comparison-owned soft limits checked while projecting a graph."""

    def active(self) -> bool: ...

    def allow_graph_node(self, node_count: int) -> bool: ...


@dataclass(frozen=True, slots=True)
class MotifNode:
    id: str
    kind: str
    coordination_number: int
    center_element: str
    ligand_elements: tuple[str, ...]
    normalized_bond_lengths: tuple[float, ...]
    distortion: float
    angle_dispersion: float
    unit_ids: tuple[str, ...]
    ligand_composition: OccupancyDistribution = ()
    occupancies: OccupancyDistribution = ()
    site_index: int | None = None
    face_signature: object | None = None
    edge_angle_dispersion_deg: float | None = None


@dataclass(frozen=True, slots=True)
class MotifEdge:
    id: str
    first: str
    second: str
    kind: str
    shared_site_indices: tuple[int, ...]
    translation: Translation
    normalized_distance: float


@dataclass(frozen=True, slots=True)
class MotifGraph:
    nodes: Mapping[str, MotifNode]
    edges: Mapping[str, MotifEdge]
    graph: nx.MultiGraph
    complete: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", MappingProxyType(dict(self.nodes)))
        object.__setattr__(self, "edges", MappingProxyType(dict(self.edges)))
        object.__setattr__(self, "graph", nx.freeze(self.graph.copy()))


def _normalized_lengths(lengths: tuple[float, ...]) -> tuple[float, ...]:
    mean = math.fsum(lengths) / len(lengths) if lengths else 0.0
    if mean <= 0.0:
        return tuple(0.0 for _ in lengths)
    return tuple(float(length / mean) for length in lengths)


def _native_site_occupancies(site: object) -> OccupancyDistribution:
    values = []
    for component in site.components:
        species = getattr(component.species, "symbol", component.species)
        occupancy = getattr(component.occupancy, "value", component.occupancy)
        values.append((str(species), float(occupancy)))
    return tuple(sorted(values))


def _build_native_motif_graph(
    document: StructureDocument,
    budget: MotifGraphBudget | None,
) -> MotifGraph | None:
    """Project exact orbit-first CrIStMa results into a comparison graph."""

    result = getattr(document.scientific.polyhedra, "result", None)
    representation = getattr(document.scientific.representation, "result", None)
    if result is None or representation is None:
        return None

    sites = {site.id: site for site in document.structure.sites}
    unit_by_orbit: dict[str, list[str]] = {}
    unit_to_orbit: dict[str, str] = {}
    for unit in representation.unit_orbits:
        orbit_id = unit.source_polyhedron_orbit_id
        if orbit_id is not None:
            unit_by_orbit.setdefault(orbit_id, []).append(unit.unit_orbit_id)
            unit_to_orbit[unit.unit_orbit_id] = orbit_id

    nodes: dict[str, MotifNode] = {}
    orbit_to_node: dict[str, str] = {}
    network = nx.MultiGraph()
    complete = True
    for orbit in result.polyhedron_orbits:
        if budget is not None and not budget.allow_graph_node(len(nodes)):
            complete = False
            break
        representative = next(
            item
            for item in orbit.polyhedra
            if item.polyhedron_id == orbit.representative_polyhedron_id
        )
        site = sites[representative.source_site_id]
        components = _native_site_occupancies(site)
        center_element = max(components, key=lambda item: item[1])[0] if components else ""
        ligand_composition = tuple(
            (str(symbol), float(count))
            for symbol, count in representative.ligand_composition
            if math.isfinite(float(count)) and float(count) > 0.0
        )
        lengths = tuple(float(vertex.distance) for vertex in representative.vertices)
        node = MotifNode(
            id=representative.polyhedron_id,
            kind="polyhedron",
            coordination_number=int(representative.coordination_number),
            center_element=center_element,
            ligand_elements=tuple(symbol for symbol, _count in ligand_composition),
            normalized_bond_lengths=_normalized_lengths(lengths),
            distortion=(
                float(representative.bond_length_distortion)
                if representative.bond_length_distortion is not None
                else math.nan
            ),
            angle_dispersion=math.nan,
            unit_ids=tuple(sorted(unit_by_orbit.get(orbit.polyhedron_orbit_id, ()))),
            ligand_composition=ligand_composition,
            occupancies=components,
            site_index=None,
            face_signature=representative.face_signature,
            edge_angle_dispersion_deg=(
                float(representative.edge_angle_dispersion_deg)
                if representative.edge_angle_dispersion_deg is not None
                else None
            ),
        )
        nodes[node.id] = node
        orbit_to_node[orbit.polyhedron_orbit_id] = node.id
        network.add_node(node.id)

    edges: dict[str, MotifEdge] = {}
    if complete:
        incident: dict[str, list[tuple[str, object]]] = {}
        for connection in representation.connection_orbits:
            first_orbit = unit_to_orbit.get(connection.first_unit_orbit_id)
            second_orbit = unit_to_orbit.get(connection.second_unit_orbit_id)
            if first_orbit is not None and second_orbit is not None:
                _add_connection_edge(
                    edges,
                    network,
                    orbit_to_node,
                    connection.connection_orbit_id,
                    first_orbit,
                    second_orbit,
                    connection,
                )
            elif first_orbit is not None:
                incident.setdefault(connection.second_unit_orbit_id, []).append(
                    (first_orbit, connection)
                )
            elif second_orbit is not None:
                incident.setdefault(connection.first_unit_orbit_id, []).append(
                    (second_orbit, connection)
                )

        for bridge_id, connections in incident.items():
            for index, ((first_orbit, first), (second_orbit, second)) in enumerate(
                combinations(connections, 2)
            ):
                first_id = orbit_to_node.get(first_orbit)
                second_id = orbit_to_node.get(second_orbit)
                if first_id is None or second_id is None or first_id == second_id:
                    continue
                translation = tuple(
                    int(second.periodic_relation.lattice_translation[axis])
                    - int(first.periodic_relation.lattice_translation[axis])
                    for axis in range(3)
                )
                edge = MotifEdge(
                    id=f"{bridge_id}:{index}",
                    first=first_id,
                    second=second_id,
                    kind="shared_vertex",
                    shared_site_indices=(),
                    translation=translation,
                    normalized_distance=1.0,
                )
                edges[edge.id] = edge
                network.add_edge(edge.first, edge.second, key=edge.id)

    return MotifGraph(nodes, edges, network, complete=complete)


def _add_connection_edge(
    edges: dict[str, MotifEdge],
    network: nx.MultiGraph,
    orbit_to_node: Mapping[str, str],
    edge_id: str,
    first_orbit: str,
    second_orbit: str,
    source: object,
) -> None:
    first_id = orbit_to_node.get(first_orbit)
    second_id = orbit_to_node.get(second_orbit)
    if first_id is None or second_id is None:
        return
    translation = tuple(int(value) for value in source.periodic_relation.lattice_translation)
    edge = MotifEdge(
        id=edge_id,
        first=first_id,
        second=second_id,
        kind=str(getattr(source.relation_type, "value", source.relation_type)),
        shared_site_indices=(),
        translation=translation,
        normalized_distance=1.0,
    )
    edges[edge.id] = edge
    network.add_edge(edge.first, edge.second, key=edge.id)


def build_motif_graph(
    document: StructureDocument,
    *,
    budget: MotifGraphBudget | None = None,
) -> MotifGraph:
    """Project a motif graph; never reconstruct missing CrIStMa science."""

    native = _build_native_motif_graph(document, budget)
    if native is not None:
        return native
    return MotifGraph({}, {}, nx.MultiGraph(), complete=False)


__all__ = [
    "LatticeImageSearchError",
    "MotifEdge",
    "MotifGraph",
    "MotifGraphBudget",
    "MotifNode",
    "build_motif_graph",
]
