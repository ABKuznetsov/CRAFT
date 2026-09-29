from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict

import networkx as nx

from craft.analysis.motif_graph import MotifEdge, MotifNode, build_motif_graph
from craft.knowledge.model import MotifFingerprint


_OCCUPANCY_SCALE = 1_000_000
_GEOMETRY_SCALE = 10_000


def _canonical_translation(values) -> tuple[int, int, int]:
    translation = tuple(int(value) for value in values)
    reverse = tuple(-value for value in translation)
    return min(translation, reverse)


def _quantized(value: float | None) -> int:
    if value is None or not math.isfinite(float(value)):
        return -1
    return int(round(float(value) * _GEOMETRY_SCALE))


def _node_signature(node: MotifNode) -> tuple[object, ...]:
    occupancies = tuple(
        (element, int(round(float(value) * _OCCUPANCY_SCALE)))
        for element, value in node.occupancies
    )
    ligand_composition = tuple(
        (element, int(round(float(value) * _OCCUPANCY_SCALE)))
        for element, value in node.ligand_composition
    )
    lengths = tuple(
        sorted(
            int(round(float(value) * _GEOMETRY_SCALE))
            for value in node.normalized_bond_lengths
        )
    )
    return (
        "node",
        node.kind,
        int(node.coordination_number),
        occupancies,
        ligand_composition,
        lengths,
        _quantized(node.distortion),
        _quantized(node.edge_angle_dispersion_deg),
        repr(node.face_signature),
    )


def _topology_hash(
    nodes: dict[str, MotifNode],
    edges: tuple[MotifEdge, ...],
) -> str:
    graph = nx.Graph()
    for node_id, node in nodes.items():
        graph.add_node(("vertex", node_id), label=repr(_node_signature(node)))
    for edge in edges:
        edge_node = ("edge", edge.id)
        graph.add_node(
            edge_node,
            label=f"E|{edge.kind}|{_canonical_translation(edge.translation)}",
        )
        graph.add_edge(edge_node, ("vertex", edge.first))
        graph.add_edge(edge_node, ("vertex", edge.second))
    return nx.weisfeiler_lehman_graph_hash(
        graph,
        node_attr="label",
        iterations=5,
    )


def build_motif_fingerprint(document, block_id: str) -> MotifFingerprint:
    """Build a stable motif fingerprint from installed CrIStMa results.

    ``block_id`` is a CrIStMa structural-block identity. CRAFT only projects
    immutable orbit results here; it does not reconstruct polyhedra,
    connections, periodic rank, or chemistry from its legacy hierarchy.
    """

    scientific = getattr(document, "scientific", None)
    if scientific is None:
        raise ValueError("CrIStMa scientific results are required")
    if getattr(scientific.polyhedra, "result", None) is None:
        raise ValueError("CrIStMa polyhedron results are not available")
    if getattr(scientific.blocks, "result", None) is None:
        raise ValueError("CrIStMa structural-block results are not available")

    presentation = document.inorganic_presentation()
    try:
        block = presentation.block(block_id)
    except KeyError as error:
        raise ValueError(f"unknown CrIStMa structural block: {block_id}") from error

    block_orbit_ids = frozenset(block.polyhedron_orbit_ids)
    representative_ids = {
        row.representative_polyhedron_id
        for row in presentation.polyhedron_orbits
        if row.polyhedron_orbit_id in block_orbit_ids
    }
    graph = build_motif_graph(document)
    nodes = {
        node_id: node
        for node_id, node in graph.nodes.items()
        if node_id in representative_ids
    }
    if not nodes:
        raise ValueError(
            f"CrIStMa structural block has no polyhedron motifs: {block_id}"
        )
    edges = tuple(
        edge
        for edge in graph.edges.values()
        if edge.first in nodes and edge.second in nodes
    )

    signatures = {node_id: _node_signature(node) for node_id, node in nodes.items()}
    node_signatures = tuple(sorted(signatures.values(), key=repr))
    edge_signatures = tuple(
        sorted(
            (
                min(repr(signatures[edge.first]), repr(signatures[edge.second])),
                max(repr(signatures[edge.first]), repr(signatures[edge.second])),
                str(edge.kind),
                _canonical_translation(edge.translation),
            )
            for edge in edges
        )
    )
    return MotifFingerprint(
        algorithm="cristma-motif-orbit-fingerprint-v2",
        periodic_rank=int(block.rank),
        nodes=node_signatures,
        edges=edge_signatures,
        topology_digest=_topology_hash(nodes, edges),
    )


def fingerprint_digest(fingerprint: MotifFingerprint) -> str:
    payload = json.dumps(
        asdict(fingerprint),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = ["build_motif_fingerprint", "fingerprint_digest"]
