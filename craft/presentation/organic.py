"""Calculation-free CRAFT view records for CrIStMa organic/MOF results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrganicRepresentationDescriptor:
    kind: str
    label: str
    count: int


@dataclass(frozen=True, slots=True)
class MolecularComponentView:
    orbit_id: str
    label: str
    kind: object
    independent_site_ids: tuple[str, ...]
    bond_orbit_ids: tuple[str, ...]
    periodic_rank: int
    periodic_generators: tuple[object, ...]
    multiplicity: int
    status: object
    diagnostics: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class MolecularRingView:
    orbit_id: str
    label: str
    parent_component_orbit_id: str
    atom_refs: tuple[object, ...]
    bond_orbit_ids: tuple[str, ...]
    multiplicity: int
    status: object
    diagnostics: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class IntermolecularContactView:
    orbit_id: str
    label: str
    first_component_orbit_id: str
    second_component_orbit_id: str
    periodic_relation: object
    representative_distance: float
    evidence: tuple[object, ...]
    interpretations: tuple[object, ...]
    multiplicity: int
    initially_visible: bool
    status: object
    diagnostics: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class PackingConnectionView:
    orbit_id: str
    first_component_orbit_id: str
    second_component_orbit_id: str
    periodic_relation: object
    interaction_refs: tuple[object, ...]
    multiplicity: int
    status: object
    diagnostics: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class CoordinationNodeView:
    orbit_id: str
    center_site_id: str
    source_shell_orbit_ids: tuple[str, ...]
    source_contact_orbit_ids: tuple[str, ...]
    multiplicity: int
    status: object
    diagnostics: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class LinkerView:
    orbit_id: str
    source_component_orbit_id: str
    independent_site_ids: tuple[str, ...]
    bond_orbit_ids: tuple[str, ...]
    connection_orbit_ids: tuple[str, ...]
    role: object
    attachment_count: int
    multiplicity: int
    status: object
    diagnostics: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class SecondaryBuildingUnitView:
    orbit_id: str
    node_orbit_ids: tuple[str, ...]
    terminal_ligand_orbit_ids: tuple[str, ...]
    source_connection_orbit_ids: tuple[str, ...]
    source_contact_orbit_ids: tuple[str, ...]
    atom_members: tuple[object, ...]
    multiplicity: int
    status: object
    diagnostics: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class ReticularNetVertexView:
    orbit_id: str
    kind: object
    source_sbu_orbit_id: str | None
    source_ligand_orbit_id: str | None
    multiplicity: int
    status: object
    diagnostics: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class ReticularNetEdgeView:
    orbit_id: str
    first_vertex_orbit_id: str
    second_vertex_orbit_id: str
    periodic_relation: object
    linker_orbit_id: str
    source_attachments: tuple[object, ...]
    multiplicity: int
    status: object
    diagnostics: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class OrganicPresentation:
    stage: str
    components: tuple[MolecularComponentView, ...] = ()
    rings: tuple[MolecularRingView, ...] = ()
    contacts: tuple[IntermolecularContactView, ...] = ()
    packing_connections: tuple[PackingConnectionView, ...] = ()
    nodes: tuple[CoordinationNodeView, ...] = ()
    linkers: tuple[LinkerView, ...] = ()
    sbus: tuple[SecondaryBuildingUnitView, ...] = ()
    net_vertices: tuple[ReticularNetVertexView, ...] = ()
    net_edges: tuple[ReticularNetEdgeView, ...] = ()
    diagnostics: tuple[object, ...] = ()
    representations: tuple[OrganicRepresentationDescriptor, ...] = ()


__all__ = [
    "CoordinationNodeView",
    "IntermolecularContactView",
    "LinkerView",
    "MolecularComponentView",
    "MolecularRingView",
    "OrganicPresentation",
    "OrganicRepresentationDescriptor",
    "PackingConnectionView",
    "ReticularNetEdgeView",
    "ReticularNetVertexView",
    "SecondaryBuildingUnitView",
]
