"""Pure projection from installed CrIStMa results to CRAFT view rows."""

from __future__ import annotations

from craft.core.scientific_cache import ORGANIC_RESULT_SLOTS
from craft.presentation.organic import (
    CoordinationNodeView,
    IntermolecularContactView,
    LinkerView,
    MolecularComponentView,
    MolecularRingView,
    OrganicPresentation,
    OrganicRepresentationDescriptor,
    PackingConnectionView,
    ReticularNetEdgeView,
    ReticularNetVertexView,
    SecondaryBuildingUnitView,
)


def _result(document, slot: str):
    wrapper = getattr(document.scientific, slot, None)
    return getattr(wrapper, "result", None)


def build_organic_presentation(document) -> OrganicPresentation:
    molecular = _result(document, "molecular")
    intermolecular = _result(document, "intermolecular")
    packing = _result(document, "packing")
    precursor = _result(document, "reticular_precursor")
    sbu = _result(document, "sbu")
    net = _result(document, "reticular_net")

    components = tuple(
        MolecularComponentView(
            item.component_orbit_id,
            (
                f"Molecule · {item.component_orbit_id}"
                if item.periodic_rank == 0
                else f"Periodic component · {item.periodic_rank}D"
            ),
            item.kind,
            item.independent_site_ids,
            item.bond_orbit_ids,
            item.periodic_rank,
            item.periodic_generators,
            item.multiplicity_in_reference_cell,
            item.status,
            item.diagnostics,
        )
        for item in getattr(molecular, "component_orbits", ())
    )
    rings = tuple(
        MolecularRingView(
            item.ring_orbit_id,
            f"Ring · {len(item.atom_refs)} atoms",
            item.parent_component_orbit_id,
            item.atom_refs,
            item.bond_orbit_ids,
            item.multiplicity_in_reference_cell,
            item.status,
            item.diagnostics,
        )
        for item in getattr(molecular, "ring_orbits", ())
    )
    contacts = tuple(
        IntermolecularContactView(
            item.intermolecular_contact_orbit_id,
            f"Contact · {item.representative_distance:.3f} Å",
            item.first_molecule_orbit_id,
            item.second_molecule_orbit_id,
            item.canonical_molecule_relation,
            item.representative_distance,
            item.component_pair_evidence,
            item.interpretations,
            item.multiplicity_in_reference_cell,
            False,
            item.status,
            item.diagnostics,
        )
        for item in getattr(intermolecular, "contact_orbits", ())
    )
    packing_connections = tuple(
        PackingConnectionView(
            item.packing_connection_orbit_id,
            item.first_molecule_orbit_id,
            item.second_molecule_orbit_id,
            item.canonical_molecule_relation,
            item.interaction_refs,
            item.multiplicity_in_reference_cell,
            item.status,
            item.diagnostics,
        )
        for item in getattr(packing, "connection_orbits", ())
    )
    nodes = tuple(
        CoordinationNodeView(
            item.node_orbit_id,
            item.center_independent_site_id,
            item.source_shell_orbit_ids,
            item.source_resolved_contact_orbit_ids,
            item.multiplicity_in_reference_cell,
            item.status,
            item.diagnostics,
        )
        for item in getattr(precursor, "node_orbits", ())
    )
    linkers = tuple(
        LinkerView(
            item.ligand_orbit_id,
            item.source_component_orbit_id,
            item.independent_site_ids,
            item.bond_orbit_ids,
            item.connection_orbit_ids,
            item.role,
            item.attachment_count_per_ligand_instance,
            item.multiplicity_in_reference_cell,
            item.status,
            item.diagnostics,
        )
        for item in getattr(precursor, "ligand_orbits", ())
    )
    sbus = tuple(
        SecondaryBuildingUnitView(
            item.sbu_orbit_id,
            item.node_orbit_ids,
            item.terminal_ligand_orbit_ids,
            item.source_connection_orbit_ids,
            item.source_contact_orbit_ids,
            item.atom_members,
            item.multiplicity_in_reference_cell,
            item.status,
            item.diagnostics,
        )
        for item in getattr(sbu, "sbu_orbits", ())
    )
    net_vertices = tuple(
        ReticularNetVertexView(
            item.net_vertex_orbit_id,
            item.kind,
            item.source_sbu_orbit_id,
            item.source_ligand_orbit_id,
            item.multiplicity_in_reference_cell,
            item.status,
            item.diagnostics,
        )
        for item in getattr(net, "vertex_orbits", ())
    )
    net_edges = tuple(
        ReticularNetEdgeView(
            item.net_edge_orbit_id,
            item.first_vertex_orbit_id,
            item.second_vertex_orbit_id,
            item.periodic_relation,
            item.linker_orbit_id,
            item.source_attachments,
            item.multiplicity_in_reference_cell,
            item.status,
            item.diagnostics,
        )
        for item in getattr(net, "edge_orbits", ())
    )

    representations: list[OrganicRepresentationDescriptor] = []
    if components:
        representations.append(
            OrganicRepresentationDescriptor("molecule", "Molecule", len(components))
        )
    if rings:
        representations.append(
            OrganicRepresentationDescriptor("rings", "Rings", len(rings))
        )
    if contacts:
        representations.append(
            OrganicRepresentationDescriptor(
                "intermolecular_contacts", "Intermolecular contacts", len(contacts)
            )
        )
    if packing is not None:
        representations.append(
            OrganicRepresentationDescriptor(
                "packing", "Crystal packing", len(packing_connections)
            )
        )
    if nodes:
        representations.append(
            OrganicRepresentationDescriptor("nodes", "Coordination nodes", len(nodes))
        )
    if linkers:
        representations.append(
            OrganicRepresentationDescriptor("linkers", "Linkers", len(linkers))
        )
    if sbus:
        representations.append(
            OrganicRepresentationDescriptor("sbus", "SBUs", len(sbus))
        )
    if net is not None and (net_vertices or net_edges):
        rank = max((getattr(item, "periodic_rank", 0) for item in net.components), default=0)
        representations.append(
            OrganicRepresentationDescriptor(
                "reticular_net", f"Underlying net · {rank}D", len(net_edges)
            )
        )

    return OrganicPresentation(
        stage=document.analysis_stage,
        components=components,
        rings=rings,
        contacts=contacts,
        packing_connections=packing_connections,
        nodes=nodes,
        linkers=linkers,
        sbus=sbus,
        net_vertices=net_vertices,
        net_edges=net_edges,
        diagnostics=document.scientific.diagnostics(ORGANIC_RESULT_SLOTS),
        representations=tuple(representations),
    )


__all__ = ["build_organic_presentation"]
