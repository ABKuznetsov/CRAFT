"""Tabulate existing native environments and periodic components without recalculation."""
from craft.analysis.reporting.model import (
    Availability, Provenance, ReportCell, ReportColumn, ReportRow, ReportTable,
)


def _result(document):
    slot = document.scientific.inorganic_classification if document is not None else None
    return slot.result if slot is not None else None


def _cells(values, *, calculated=(), warning=""):
    return {key: ReportCell(value, str(value) if value is not None else "—",
        Provenance.UNAVAILABLE if value is None else
        Provenance.CALCULATED if key in calculated else Provenance.MODEL_DEPENDENT,
        method_id="cristma.native", warning=warning) for key, value in values.items()}


def build_coordination_table(document):
    result = _result(document)
    columns = tuple(ReportColumn(key, title) for key, title in (
        ("site", "Centre"), ("coordination", "Coordination number"),
        ("partition", "Shell partition"), ("geometry", "Geometry"),
        ("ligands", "Ligand site counts"), ("model", "Shell model"),
    ))
    rows = []
    if result is not None:
        presentation = document.inorganic_presentation()
        labels = {atom.source_site_id: atom.label for atom in presentation.atom_orbits}
        for orbit in presentation.polyhedron_orbits:
            values = {"site": labels.get(orbit.source_site_id, orbit.label),
                "coordination": orbit.coordination_number, "partition": str(orbit.coordination_number),
                "geometry": orbit.geometry_label,
                "ligands": ", ".join(f"{labels.get(site, site)}: {count}" for site, count in orbit.ligand_site_counts),
                "model": "Selected shell"}
            rows.append(ReportRow(orbit.polyhedron_orbit_id,
                _cells(values, calculated=("coordination",)),
                object_refs=(orbit.source_site_id, orbit.source_shell_id, orbit.polyhedron_orbit_id)))
        seen = set()
        for group in (*result.groups, *result.cation_groups):
            for environment in group.environments:
                for boundary in environment.coordination_boundaries:
                    if boundary.key in seen:
                        continue
                    seen.add(boundary.key)
                    rows.append(ReportRow(boundary.key, _cells({
                        "site": environment.site_label, "coordination": boundary.coordination_number,
                        "partition": "+".join(map(str, boundary.coordination_partition)),
                        "geometry": None, "ligands": ", ".join(
                            f"{labels.get(site, site)}: +{count}" for site, count in boundary.added_ligand_site_counts),
                        "model": "Alternative extended shell; ligand counts are additions",
                    }, calculated=("coordination",),
                        warning="Conditional average-site model" if boundary.conditional else ""),
                        object_refs=(environment.site_id, boundary.source_shell_id, boundary.alternative_id)))
    return ReportTable("coordination", "Coordination environments", columns, tuple(rows),
        availability=Availability.AVAILABLE if rows else Availability.UNAVAILABLE,
        unavailable_reason="" if rows else "No coordination environments are available for this structure.",
        method="CrIStMa selected coordination shells and explicit shell alternatives")


def build_connectivity_table(document):
    result = _result(document)
    columns = tuple(ReportColumn(key, title) for key, title in (
        ("model", "Selected graph / criterion"), ("component", "Component"),
        ("rank", "Periodic rank"), ("coordination", "Centre coordination numbers"),
        ("status", "Model status"), ("ring_sizes", "Graph-cycle candidate centre counts"),
        ("ring_search", "Bounded ring search status"),
    ))
    rows, seen = [], set()
    if result is not None:
        for group in (*result.groups, *result.cation_groups):
            for assignment in group.subtypes:
                key = (assignment.representation_id, assignment.component_id)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(ReportRow("/".join(key), _cells({
                    "model": group.label, "component": assignment.label,
                    "rank": assignment.rank,
                    "coordination": ", ".join(map(str, assignment.coordination_numbers)),
                    "status": assignment.status,
                    "ring_sizes": ", ".join(map(str, assignment.ring_sizes)),
                    "ring_search": assignment.ring_search_status,
                }, calculated=("rank",), warning=" ".join(assignment.warnings)),
                    object_refs=(*key, *assignment.source_shell_ids),
                    notes="Graph cycles do not establish a geometric opening. " + " ".join(assignment.evidence)))
    return ReportTable("connectivity", "Polyhedral connectivity", columns, tuple(rows),
        availability=Availability.AVAILABLE if rows else Availability.UNAVAILABLE,
        unavailable_reason="" if rows else "No polyhedral connectivity results are available for this structure.",
        method="CrIStMa periodic components in each selected representation; graph cycles are opening-unverified candidates")
