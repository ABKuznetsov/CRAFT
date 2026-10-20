"""Export CRAFT class assignments with the native environment identities."""

from craft.analysis.reporting.model import (
    Availability, Provenance, ReportCell, ReportColumn, ReportRow, ReportTable, ReportWarning,
)


def _environment_subtype(group, environment):
    subtype = next((a for a in group.subtypes if environment.shell_orbit_id in a.source_shell_ids), None)
    if subtype is not None or group.subsystem is None:
        return subtype
    # One native shell represents a coincident average position in topology.
    # Keep each original component's environment row, but link it to the same
    # conditional component instead of claiming its topology is unassigned.
    alternatives = dict(group.subsystem.representation.provenance).get("positional_alternatives", ())
    primary = next((primary for primary, alternative in alternatives if alternative == environment.site_id), None)
    return next((a for a in group.subtypes if primary in a.centre_site_ids), None)


def build_classification_table(document) -> ReportTable:
    slot = document.scientific.inorganic_classification if document is not None else None
    result = slot.result if slot is not None else None
    columns = tuple(ReportColumn(key, title) for key, title in (
        ("class", "Compound class"), ("site", "Centre"), ("coordination", "O coordination"),
        ("geometry", "Geometry"), ("status", "Assignment status"),
        ("evidence", "Evidence"), ("reference", "Classification reference"),
        ("subtype", "Polymerization subtype (graph topology)"), ("subsystem_rank", "Observed subsystem rank"),
        ("subtype_status", "Subtype status"), ("subtype_evidence", "Subtype evidence"),
        ("ring_sizes", "Graph-cycle candidate centre counts"), ("subtype_reference", "Subtype reference"),
        ("ring_opening_status", "Geometric opening assessment"),
        ("ring_search_limit", "Ring search limit (graph vertices)"), ("ring_search_status", "Bounded ring search status"),
    ))
    rows = []
    if result is not None:
        for group in result.groups:
            for environment in group.environments:
                subtype = _environment_subtype(group, environment)
                values = {
                    "class": group.label, "site": environment.site_label,
                    "coordination": environment.coordination_number, "geometry": environment.geometry,
                    "status": environment.status, "evidence": " ".join(environment.evidence),
                    "reference": group.reference,
                    "subtype": subtype.label if subtype is not None else None,
                    "subsystem_rank": subtype.rank if subtype is not None else None,
                    "subtype_status": subtype.status if subtype is not None else "not assigned",
                    "subtype_evidence": " ".join(subtype.evidence) if subtype is not None else None,
                    "ring_sizes": ", ".join(map(str, subtype.ring_sizes)) if subtype is not None else None,
                    "subtype_reference": subtype.reference if subtype is not None else None,
                    "ring_search_limit": subtype.ring_search_max_vertices if subtype is not None else None,
                    "ring_search_status": subtype.ring_search_status if subtype is not None else None,
                    "ring_opening_status": ", ".join(sorted({m.opening_status for m in subtype.ring_motifs}))
                    if subtype is not None and subtype.ring_motifs else None,
                }
                warnings = (*environment.warnings, *(subtype.warnings if subtype is not None else ()))
                rows.append(ReportRow(
                    id=f"{group.family}:{environment.polyhedron_orbit_id}",
                    cells={key: ReportCell(
                        value, str(value) if value is not None else "—",
                        Provenance.UNAVAILABLE if value is None or key == "ring_opening_status" else
                        Provenance.CALCULATED if key == "subsystem_rank" and value is not None else Provenance.INFERRED,
                        method_id=f"{result.method_id}:{result.method_version}",
                        warning=" ".join(warnings),
                    ) for key, value in values.items()},
                    object_refs=(environment.site_id, environment.shell_orbit_id, environment.polyhedron_orbit_id)
                    + ((subtype.representation_id, subtype.component_id) if subtype is not None else ()),
                ))
    warnings = []
    if result is not None:
        warnings.extend(ReportWarning("craft.classification.model_scope", w) for w in result.warnings)
        if result.unassigned_site_ids:
            warnings.append(ReportWarning("craft.classification.unassigned_centres",
                "Unassigned class-forming sites: " + ", ".join(result.unassigned_site_ids)))
    return ReportTable(
        "inorganic_classification", "Inorganic compound classes", columns, tuple(rows),
        availability=Availability.AVAILABLE if rows else Availability.UNAVAILABLE,
        unavailable_reason=("" if rows else "No supported oxyanion-class assignments are available for this structure."
                            if result is not None else
                            "No atom coordinates are available for structural classification."
                            if document is not None and not document.structure.sites else
                            "Native coordination analysis is required."),
        warnings=tuple(warnings),
        method=f"{result.method_id}:{result.method_version}" if result is not None else "",
    )
