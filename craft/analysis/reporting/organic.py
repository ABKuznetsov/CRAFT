"""Report-table projections of immutable CrIStMa organic/MOF results."""

from __future__ import annotations

from collections.abc import Iterable

from craft.analysis.reporting.model import (
    Provenance,
    ReportCell,
    ReportColumn,
    ReportRow,
    ReportTable,
)
from craft.presentation.organic import OrganicPresentation


def _text(value: object) -> str:
    return str(getattr(value, "value", value))


def _cell(value: object, *, method: str = "cristma") -> ReportCell:
    display = _text(value)
    return ReportCell(value=display, display=display, provenance=Provenance.CALCULATED, method_id=method)


def _joined(values: Iterable[object]) -> str:
    return ", ".join(_text(value) for value in values)


def _table(table_id: str, title: str, columns: tuple[tuple[str, str], ...], rows: list[ReportRow]) -> ReportTable:
    return ReportTable(
        id=table_id,
        title=title,
        columns=tuple(ReportColumn(column_id, label) for column_id, label in columns),
        rows=tuple(rows),
        method="CrIStMa native orbit results",
    )


def build_organic_table(table_id: str, presentation: OrganicPresentation) -> ReportTable:
    rows: list[ReportRow] = []
    if table_id == "molecular_components":
        columns = (("label", "Component"), ("kind", "Kind"), ("rank", "Rank"), ("multiplicity", "Multiplicity"), ("status", "Status"))
        for item in presentation.components:
            rows.append(ReportRow(item.orbit_id, {
                "label": _cell(item.label), "kind": _cell(item.kind), "rank": _cell(item.periodic_rank),
                "multiplicity": _cell(item.multiplicity), "status": _cell(item.status),
            }, object_refs=(item.orbit_id,)))
        return _table(table_id, "Molecular components", columns, rows)
    if table_id == "molecular_rings":
        columns = (("parent", "Component"), ("size", "Ring size"), ("multiplicity", "Multiplicity"), ("status", "Status"))
        for item in presentation.rings:
            rows.append(ReportRow(item.orbit_id, {
                "parent": _cell(item.parent_component_orbit_id), "size": _cell(len(item.atom_refs)),
                "multiplicity": _cell(item.multiplicity), "status": _cell(item.status),
            }, object_refs=(item.orbit_id, item.parent_component_orbit_id)))
        return _table(table_id, "Molecular rings", columns, rows)
    if table_id == "intermolecular_contacts":
        columns = (("components", "Components"), ("distance", "Distance"), ("multiplicity", "Multiplicity"), ("status", "Status"))
        for item in presentation.contacts:
            rows.append(ReportRow(item.orbit_id, {
                "components": _cell(f"{item.first_component_orbit_id} — {item.second_component_orbit_id}"),
                "distance": _cell(item.representative_distance), "multiplicity": _cell(item.multiplicity),
                "status": _cell(item.status),
            }, object_refs=(item.orbit_id, item.first_component_orbit_id, item.second_component_orbit_id)))
        return _table(table_id, "Intermolecular contacts", columns, rows)
    if table_id == "packing_interactions":
        columns = (("components", "Components"), ("interactions", "Interaction orbits"), ("multiplicity", "Multiplicity"), ("status", "Status"))
        for item in presentation.packing_connections:
            rows.append(ReportRow(item.orbit_id, {
                "components": _cell(f"{item.first_component_orbit_id} — {item.second_component_orbit_id}"),
                "interactions": _cell(_joined(item.interaction_refs)), "multiplicity": _cell(item.multiplicity),
                "status": _cell(item.status),
            }, object_refs=(item.orbit_id, item.first_component_orbit_id, item.second_component_orbit_id)))
        return _table(table_id, "Packing interactions", columns, rows)
    if table_id == "coordination_nodes":
        columns = (("center", "Center site"), ("contacts", "Contact orbits"), ("multiplicity", "Multiplicity"), ("status", "Status"))
        for item in presentation.nodes:
            rows.append(ReportRow(item.orbit_id, {
                "center": _cell(item.center_site_id), "contacts": _cell(_joined(item.source_contact_orbit_ids)),
                "multiplicity": _cell(item.multiplicity), "status": _cell(item.status),
            }, object_refs=(item.orbit_id, *item.source_contact_orbit_ids)))
        return _table(table_id, "Coordination nodes", columns, rows)
    if table_id == "linkers":
        columns = (("role", "Role"), ("attachments", "Attachments"), ("sites", "Sites"), ("multiplicity", "Multiplicity"), ("status", "Status"))
        for item in presentation.linkers:
            rows.append(ReportRow(item.orbit_id, {
                "role": _cell(item.role), "attachments": _cell(item.attachment_count),
                "sites": _cell(_joined(item.independent_site_ids)), "multiplicity": _cell(item.multiplicity),
                "status": _cell(item.status),
            }, object_refs=(item.orbit_id, item.source_component_orbit_id)))
        return _table(table_id, "Linkers", columns, rows)
    if table_id == "sbus":
        columns = (("nodes", "Node orbits"), ("terminal", "Terminal ligands"), ("members", "Atom members"), ("multiplicity", "Multiplicity"), ("status", "Status"))
        for item in presentation.sbus:
            rows.append(ReportRow(item.orbit_id, {
                "nodes": _cell(_joined(item.node_orbit_ids)), "terminal": _cell(_joined(item.terminal_ligand_orbit_ids)),
                "members": _cell(_joined(item.atom_members)), "multiplicity": _cell(item.multiplicity),
                "status": _cell(item.status),
            }, object_refs=(item.orbit_id, *item.node_orbit_ids)))
        return _table(table_id, "Secondary building units", columns, rows)
    if table_id == "reticular_net":
        columns = (("record", "Record"), ("kind", "Kind"), ("connections", "Connections"), ("multiplicity", "Multiplicity"), ("status", "Status"))
        for item in presentation.net_vertices:
            rows.append(ReportRow(item.orbit_id, {
                "record": _cell("vertex"), "kind": _cell(item.kind), "connections": _cell(item.source_sbu_orbit_id or item.source_ligand_orbit_id or ""),
                "multiplicity": _cell(item.multiplicity), "status": _cell(item.status),
            }, object_refs=(item.orbit_id,)))
        for item in presentation.net_edges:
            rows.append(ReportRow(item.orbit_id, {
                "record": _cell("edge"), "kind": _cell("linker"),
                "connections": _cell(f"{item.first_vertex_orbit_id} — {item.second_vertex_orbit_id}; {item.periodic_relation}"),
                "multiplicity": _cell(item.multiplicity), "status": _cell(item.status),
            }, object_refs=(item.orbit_id, item.first_vertex_orbit_id, item.second_vertex_orbit_id, item.linker_orbit_id)))
        return _table(table_id, "Reticular net", columns, rows)
    raise KeyError(f"Unknown organic report table: {table_id}")


ORGANIC_TABLE_IDS = frozenset({
    "molecular_components", "molecular_rings", "intermolecular_contacts",
    "packing_interactions", "coordination_nodes", "linkers", "sbus", "reticular_net",
})
