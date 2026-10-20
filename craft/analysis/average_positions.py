"""Select existing native shells for coincident average-model positions.

This is independent of element names and coordination geometry. It neither
changes canonical sites nor constructs contacts, hulls or a local ordering.
"""
from collections import defaultdict
import math


def coincident_shell_alternatives(structure, polyhedra, shell_ids, *, preferred_shell_ids=()):
    """Return omitted shell -> (representative site, original alternative site).

    Exact coordinates and native ligand image sets must agree. Uncertain,
    overoccupied and explicitly incompatible groups are left separate. A
    preferred shell preserves a selected class's defining chemical component;
    otherwise the largest occupancy, then source identity, breaks ties.
    """
    sites = {site.id: site for site in structure.sites}
    preferred = set(preferred_shell_ids)
    positions = defaultdict(dict)
    for orbit in polyhedra.polyhedron_orbits:
        poly = orbit.representative
        shell = poly.source_shell_orbit_id
        if shell not in shell_ids or not poly.vertices:
            continue
        site = sites[poly.source_site_id]
        signature = (tuple(value.value % 1 for value in site.fractional),
                     frozenset(vertex.atom_ref for vertex in poly.vertices))
        positions[signature][shell] = site
    alternatives = {}
    for shells in positions.values():
        members = {site.id: site for site in shells.values()}
        if len(members) < 2:
            continue
        occupancies = [site.total_occupancy for site in members.values()]
        if not all(math.isfinite(value) and 0 < value < 1 for value in occupancies):
            continue
        if math.fsum(occupancies) > 1 + 1e-12:
            continue
        labels = {(site.disorder_assembly, site.disorder_group) for site in members.values()}
        if labels != {(None, None)}:
            # Same group means simultaneous occupation (coreCIF); different
            # assemblies describe independent disorder. Partial labels do not
            # supply enough evidence to identify alternatives conservatively.
            assemblies = {site.disorder_assembly for site in members.values()}
            groups = {site.disorder_group for site in members.values()}
            if (len(assemblies) != 1 or len(groups) != len(members)
                    or groups.intersection({None, ".", "?", "0"})
                    or assemblies.intersection({".", "?"})):
                continue
        primary_shell = min(shells, key=lambda shell: (shell not in preferred,
                            -shells[shell].total_occupancy, shells[shell].id, shell))
        primary = shells[primary_shell]
        for shell, site in shells.items():
            if site.id != primary.id:
                alternatives[shell] = (primary.id, site.id)
    return alternatives


def position_provenance(alternatives):
    if not alternatives:
        return ()
    return (("positional_alternatives", tuple(sorted(set(alternatives.values())))),
            ("position_selection", "one_native_shell_per_coincident_position"))


def average_position_evidence(structure, representation, selected_site_ids):
    sites = {site.id: site for site in structure.sites}
    pairs = [pair for pair in dict(representation.provenance).get("positional_alternatives", ())
             if pair[0] in selected_site_ids]
    if not pairs:
        return ()
    description = "; ".join(
        f"{sites[primary].label} / {sites[alternative].label} "
        f"({sites[primary].total_occupancy:g} / {sites[alternative].total_occupancy:g})"
        for primary, alternative in pairs)
    return ("Coincident average-model positions represented once in topology: " + description
            + ". Original site components are retained; local ordering is not inferred.",)
