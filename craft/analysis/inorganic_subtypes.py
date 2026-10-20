"""Select class subsystems and interpret their exact CrIStMa topology.

CRAFT selects existing native units and primary contacts. CrIStMa calculates
components, periodic rank and rings. Counts below interpret native orbit
multiplicities; no local graph traversal, rank or ring solver is used.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import replace

from cristma.crystal_chemistry import PeriodicConnectivityAnalyzer

from craft.analysis.average_positions import (
    coincident_shell_alternatives, position_provenance, average_position_evidence,
)
from craft.analysis.native_group_rules import class_centre, class_rules

from craft.analysis.inorganic_classification import (
    ClassSubsystem, PolymerizationAssignment, RingMotif, RING_OPENING_WARNING, _symbol,
)
from craft.analysis.connectivity_hierarchy import (
    analyze_connectivity_hierarchy, native_ligand_degrees, select_primary_ligand_representation,
)


SILICATE_REFERENCE = "https://doi.org/10.1180/mgm.2020.13"
BORATE_REFERENCE = "https://www.frankhawthorne.com/_files/ugd/70a3a9_e3ce93b00d864b3f8a504833a549e79c.pdf"

_LABELS = {
    "silicate": {
        "isolated": "Island silicates · isolated tetrahedra (nesosilicates)",
        "finite_cluster": "Finite-cluster silicates (sorosilicates)",
        "ring": "Cyclic silicate groups (cyclosilicates) · graph topology",
        "chain": "Chain / ribbon / tube silicates (inosilicates)",
        "layer": "Layer silicates (phyllosilicates)",
        "framework": "Framework silicates",
    },
    "borate": {
        "isolated": "Isolated borate groups",
        "finite_cluster": "Finite-cluster borates",
        "ring": "Cyclic borates · finite graph cycles",
        "chain": "Chain / ribbon borates",
        "layer": "Layer borates",
        "framework": "Framework borates",
    },
}


def _symbols(site):
    return {_symbol(c) for c in site.components if c.occupancy.value > 0}


def _supporting_aluminium(structure, polyhedra):
    """Only resolved tetrahedral AlO4 may extend the Si/Al–O representation."""
    sites = {site.id: site for site in structure.sites}
    supported = {}
    for orbit in polyhedra.polyhedron_orbits:
        poly = orbit.representative
        if (
            _symbols(sites[poly.source_site_id]) == {"Al"}
            and poly.coordination_number == 4
            and len(poly.faces) == 4
            and all(len(face) == 3 for face in poly.faces)
            and (poly.volume or 0) > 0
            and {symbol for symbol, _ in poly.ligand_composition} == {"O"}
        ):
            supported[poly.source_shell_orbit_id] = poly.source_site_id
    return supported


def _legacy_si_al_alternatives(group, structure, polyhedra, supporting):
    """Reproduce revision 3 when reopening projects with saved layer IDs.

    This selects an average-model topology; it does not merge input sites or
    infer a local ordering of the original components.
    """
    sites = {site.id: site for site in structure.sites}
    polys = {orbit.representative.source_shell_orbit_id: orbit.representative
             for orbit in polyhedra.polyhedron_orbits}

    def signature(shell):
        poly = polys[shell]
        site = sites[poly.source_site_id]
        return (tuple(value.value % 1 for value in site.fractional),
                frozenset(vertex.atom_ref for vertex in poly.vertices))

    defining = {signature(environment.shell_orbit_id): environment.site_id
                for environment in group.environments}
    alternatives = {}
    for shell, site_id in supporting.items():
        primary_id = defining.get(signature(shell))
        if primary_id is None:
            continue
        primary, alternative = sites[primary_id], sites[site_id]
        if (0 < primary.total_occupancy < 1 and 0 < alternative.total_occupancy < 1
                and primary.total_occupancy + alternative.total_occupancy <= 1 + 1e-12):
            alternatives[shell] = (primary_id, site_id)
    return alternatives


def _explicit_site_representation(group, graph, centres, oxygen_sites, contacts, polyhedra, units):
    """Use CrIStMa's native image graph where site stabilizers matter."""
    if contacts is None or units is None:
        return None
    selected = {unit.center_independent_site_id for unit in graph.unit_orbits}
    mapping = contacts._asymmetric_unit_mapping
    if not any(len(mapping.by_site_id[key].stabilizer_relations) > 1 for key in selected):
        return None
    from craft.analysis.coordination_organization import _sharing_analyzer
    analyzer = _sharing_analyzer()
    if analyzer is None:
        return None
    sharing = analyzer.analyze(contacts, polyhedra, units,
                              selected_unit_orbit_ids=tuple(sorted(centres)))
    image_centres = {image for image, _source in sharing.unit_sources}
    representation = select_primary_ligand_representation(
        sharing.incidence_graph, image_centres,
        identity=f"craft.class_subsystem:5:{group.family}:site_images", ligand_site_ids=oxygen_sites,
    )
    return representation, image_centres


def _representation_for(group, structure, polyhedra, graph, *, contacts=None, units=None, subsystem_revision=5):
    sites = {site.id: site for site in structure.sites}
    defining_shells = {e.shell_orbit_id for e in group.environments}
    shells = set(defining_shells)
    supporting = _supporting_aluminium(structure, polyhedra) if group.family == "silicate" else {}
    shells.update(supporting)
    if subsystem_revision >= 4:
        native_shells = {orbit.representative.source_shell_orbit_id: orbit.representative.source_site_id
                         for orbit in polyhedra.polyhedron_orbits}
        candidates = coincident_shell_alternatives(
            structure, polyhedra, set(native_shells), preferred_shell_ids=defining_shells,
        )
        selected_sites = {native_shells[shell] for shell in shells}
        primary_sites = {primary for primary, alternative in candidates.values()
                         if primary in selected_sites or alternative in selected_sites}
        alternatives = {shell: pair for shell, pair in candidates.items() if pair[0] in primary_sites}
        # Select the existing representative even when a more occupied
        # alternative was outside the original chemical class's support list.
        shells.update(shell for shell, site in native_shells.items() if site in primary_sites)
    else:
        alternatives = (_legacy_si_al_alternatives(group, structure, polyhedra, supporting)
                        if subsystem_revision == 3 else {})
    shells.difference_update(alternatives)
    if subsystem_revision >= 4:
        supporting = {shell: native_shells[shell] for shell in shells - defining_shells}
    else:
        supporting = {shell: site for shell, site in supporting.items() if shell not in alternatives}
    centres = {u.unit_orbit_id for u in graph.unit_orbits if u.source_shell_orbit_id in shells}
    oxygen_sites = {key for key, site in sites.items() if _symbols(site) == {"O"}}
    representation = select_primary_ligand_representation(
        graph, centres, identity=f"craft.class_subsystem:2:{group.family}", ligand_site_ids=oxygen_sites,
    )
    if supporting:
        defining = {u.unit_orbit_id for u in representation.unit_orbits
                    if u.source_shell_orbit_id in defining_shells}
        connectivity = PeriodicConnectivityAnalyzer().analyze(representation)
        connected = {key for component in connectivity.components
                     if defining.intersection(component.unit_orbit_ids)
                     for key in component.unit_orbit_ids}
        retained_centres = centres.intersection(connected)
        if retained_centres != centres:
            centres = retained_centres
            retained_shells = {u.source_shell_orbit_id for u in representation.unit_orbits
                               if u.unit_orbit_id in centres}
            supporting = {shell: site for shell, site in supporting.items() if shell in retained_shells}
            representation = select_primary_ligand_representation(
                graph, centres, identity=f"craft.class_subsystem:2:{group.family}", ligand_site_ids=oxygen_sites,
            )
    explicit = (_explicit_site_representation(group, representation, centres, oxygen_sites, contacts, polyhedra, units)
                if subsystem_revision >= 3 else None)
    if explicit is not None:
        representation, centres = explicit
    if subsystem_revision >= 4:
        retained_sites = {unit.center_independent_site_id for unit in representation.unit_orbits
                          if unit.unit_orbit_id in centres}
        alternatives = {shell: pair for shell, pair in alternatives.items() if pair[0] in retained_sites}
    if alternatives:
        provenance = (position_provenance(alternatives) if subsystem_revision >= 4 else (
            ("positional_alternatives", tuple(sorted(alternatives.values()))),
            ("position_selection", "one_native_shell_per_coincident_T_position"),
        ))
        representation = replace(representation, provenance=representation.provenance + provenance)
        supporting.update({shell: site for shell, (_primary, site) in alternatives.items()})
    return representation, centres, supporting


def _native_degrees(representation, centres):
    return native_ligand_degrees(representation, centres)


def _assignments(group, structure, polyhedra, subsystem):
    rep = subsystem.representation
    units = {u.unit_orbit_id: u for u in rep.unit_orbits}
    sites = {site.id: site for site in structure.sites}
    centres = set(subsystem.centre_unit_ids)
    oxygen_degree, bridging_degree = _native_degrees(rep, centres)
    environments = {e.shell_orbit_id: e for e in group.environments}
    poly_by_shell = {o.representative.source_shell_orbit_id: o.representative for o in polyhedra.polyhedron_orbits}
    element = class_centre(group.family)
    eligible = {site.id for site in structure.sites if element in _symbols(site)}
    missing = eligible - {e.site_id for e in group.environments}
    expected = {c: set(units[c].source_resolved_contact_orbit_ids) for c in centres}
    observed = defaultdict(set)
    for edge in rep.connection_orbits:
        for key in (edge.first_unit_orbit_id, edge.second_unit_orbit_id):
            if key in centres:
                observed[key].update(edge.source_resolved_contact_orbit_ids)
    alternative_sites = {alternative for _primary, alternative in dict(rep.provenance).get("positional_alternatives", ())}
    missing_shells = {shell for shell, environment in environments.items() if environment.site_id not in alternative_sites}
    missing_shells -= {units[key].source_shell_orbit_id for key in centres}
    blocks = {frozenset(b.unit_orbit_ids): b for b in subsystem.blocks.blocks}
    witnesses = {w.component_id: w for w in subsystem.component_witnesses}
    equivalent_ids = {key for witness in witnesses.values() for key in witness.equivalent_component_ids
                      if key != witness.component_id}
    assignments = []
    for component in subsystem.connectivity.components:
        if component.component_id in equivalent_ids:
            continue
        witness = witnesses.get(component.component_id)
        component_centres = tuple(key for key in component.unit_orbit_ids if key in centres)
        # Supporting Al-only components do not establish a silicate subtype.
        if not any(units[key].source_shell_orbit_id in environments for key in component_centres):
            continue
        component_oxygen = [key for key in component.unit_orbit_ids if key not in centres]
        block = blocks[frozenset(component.unit_orbit_ids)]
        component_rings = tuple(r for r in subsystem.rings.ring_orbits if r.parent_block_id == block.block_id)
        motifs = []
        for ring in component_rings:
            counts = Counter(
                poly_by_shell[units[ref.unit_orbit_id].source_shell_orbit_id].coordination_number
                for ref in ring.unit_orbit_refs if ref.unit_orbit_id in centres
            )
            if sum(counts.values()) >= 3:
                motifs.append(RingMotif(
                    ring.ring_orbit_id, sum(counts.values()), ring.size,
                    tuple(sorted(counts.items())), ring.multiplicity_in_reference_cell,
                    tuple(sorted(Counter(
                        ref.unit_orbit_id for ref in ring.unit_orbit_refs if ref.unit_orbit_id in centres
                    ).items())),
                ))
        ring_sizes = tuple(sorted({
            sum(ref.unit_orbit_id in centres for ref in ring.unit_orbit_refs)
            for ring in component_rings
            if sum(ref.unit_orbit_id in centres for ref in ring.unit_orbit_refs) >= 3
        }))
        warnings = [warning for key in component_centres
                    if units[key].source_shell_orbit_id in environments
                    for warning in environments[units[key].source_shell_orbit_id].warnings]
        for key in (*component_centres, *component_oxygen):
            site = sites[units[key].center_independent_site_id]
            if len([c for c in site.components if c.occupancy.value > 0]) > 1 or not math.isclose(
                site.total_occupancy, 1,
            ):
                warnings.append("Mixed or partially occupied component sites; topology belongs to the average model.")
        status = "conditional" if warnings else "supported"
        rank = component.rank
        is_cycle_degree = all(bridging_degree[key] == 2 for key in component_centres) and all(
            oxygen_degree.get(key, 0) <= 2 for key in component_oxygen
        )
        edge_sharing_pair = any(
            sum(ref.unit_orbit_id in centres for ref in ring.unit_orbit_refs) == 2
            for ring in component_rings
        )
        if rank:
            subtype = {1: "chain", 2: "layer", 3: "framework"}[rank]
        elif all(oxygen_degree.get(key, 0) <= 1 for key in component_oxygen):
            subtype = "isolated"
        elif subsystem.rings.status.value != "complete":
            subtype, status = "finite_group", "incomplete"
            warnings.append("Native ring search reached its bounds; finite-ring nomenclature is unresolved.")
        elif ring_sizes and is_cycle_degree:
            subtype = "ring"
        elif is_cycle_degree and not edge_sharing_pair:
            # COMPLETE means complete within the configured maximum size;
            # absence of a witness is not proof that a larger ring is absent.
            subtype, status = "finite_group", "incomplete"
            warnings.append("No ring witness within the configured native ring-size bound.")
        else:
            subtype = "finite_cluster"
        nonintegral = any(oxygen_degree[key].denominator != 1 for key in component_oxygen if key in oxygen_degree)
        if missing or any(expected[key] != observed[key] for key in component_centres) or missing_shells or nonintegral:
            subtype, status = "unresolved", "incomplete"
            warnings.append("Incomplete class subsystem; a fragment's rank does not establish the full subtype.")
            if missing:
                warnings.append("Unassigned centres: " + ", ".join(sites[key].label for key in sorted(missing)))
        coordination = tuple(sorted({
            poly_by_shell[units[key].source_shell_orbit_id].coordination_number
            for key in component_centres if units[key].source_shell_orbit_id in environments
        }))
        tetrahedral_silicate = group.family == "silicate" and coordination == (4,)
        nomenclature = group.family if group.family != "silicate" or tetrahedral_silicate else None
        labels = _LABELS.get(nomenclature, {
            "isolated": f"Isolated {group.label.lower()} groups",
            "finite_cluster": f"Finite {group.label.lower()} group",
            "ring": f"Cyclic {group.label.lower()} group · graph topology",
            "chain": f"Chain / ribbon {group.label.lower()}",
            "layer": f"Layer {group.label.lower()}",
            "framework": f"Framework {group.label.lower()}",
        })
        label = labels.get(subtype, {
            "unresolved": "Subtype unresolved · incomplete subsystem",
            "finite_group": "Finite group · ring assignment unresolved",
        }.get(subtype, subtype))
        if tetrahedral_silicate and subtype == "framework" and all(
            bridging_degree[key] == 4 for key in component_centres
        ):
            label += " (tectosilicates)"
        if group.family == "borate" and subtype == "isolated" and coordination == (3,):
            label = "Orthoborates · isolated BO3 groups"
        evidence = (
            "Selected primary " + ("Si/Al–O" if group.family == "silicate" else element + "–O") + " contacts only; interstitial cations excluded.",
            f"CrIStMa periodic rank: {rank}; generators: {component.periodic_generators}.",
            f"Native component: {component.component_id}; representation: {rep.representation_id}.",
        )
        evidence += average_position_evidence(structure, rep,
            {units[key].center_independent_site_id for key in component_centres})
        # COMPLETE describes the bounded shortest-return search, not an
        # exhaustive inventory of all possible cycles in an infinite net.
        warnings.append("Native ring motifs are not exhaustive: shortest-return chordless rings within the configured bounds.")
        if motifs:
            warnings.append(RING_OPENING_WARNING)
        search_policy = dict(subsystem.rings.provenance)["policy"]
        assignments.append(PolymerizationAssignment(
            component.component_id, rep.representation_id, subtype, label, rank, status,
            coordination, ring_sizes, component_centres,
            tuple(sorted({units[key].center_independent_site_id for key in component_centres})),
            tuple(sorted({units[key].source_shell_orbit_id for key in component_centres})),
            evidence, tuple(dict.fromkeys(warnings)),
            SILICATE_REFERENCE if tetrahedral_silicate else BORATE_REFERENCE if group.family == "borate" else group.reference,
            tuple(sorted(motifs, key=lambda m: (m.centre_count, m.ring_orbit_id))),
            "within_policy" if subsystem.rings.status.value == "complete" else "incomplete",
            search_policy["maximum_ring_size"],
            component_witness=witness,
        ))
    return tuple(assignments)


def classify_polymerization(structure, polyhedra, graph, classification, ring_policy, *, contacts=None, units=None,
                            subsystem_revision=5):
    """Enrich broad CRAFT classes once the native structural graph is available."""
    groups = []
    unassigned = set(classification.unassigned_site_ids)
    for group in classification.groups:
        representation, centres, supporting = _representation_for(
            group, structure, polyhedra, graph, contacts=contacts, units=units,
            subsystem_revision=subsystem_revision,
        )
        # Periodic frameworks also have ring motifs. Their presence does not
        # change the rank-based subtype into an isolated cyclic borate.
        component_analyzer = None
        if dict(representation.provenance).get("quotient") == "translations_with_explicit_site_images":
            from cristma.crystal_chemistry.polyhedron_sharing import PolyhedralComponentAnalyzer
            component_analyzer = PolyhedralComponentAnalyzer(contacts)
        hierarchy = analyze_connectivity_hierarchy(representation, ring_policy, component_analyzer=component_analyzer)
        subsystem = ClassSubsystem(representation, hierarchy.connectivity, hierarchy.blocks, hierarchy.rings,
                                   tuple(sorted(centres)), tuple(sorted(set(supporting.values()))),
                                   component_witnesses=hierarchy.component_witnesses)
        assignments = _assignments(group, structure, polyhedra, subsystem)
        if any(rule.family == group.family and rule.generic for rule in class_rules()):
            # Local octahedral coordination alone does not establish a polyoxo
            # cluster. Require native evidence of linkage between centres.
            assignments = tuple(a for a in assignments if a.subtype_id != "isolated")
            shells = {shell for a in assignments for shell in a.source_shell_ids}
            unassigned.update(e.site_id for e in group.environments if e.shell_orbit_id not in shells)
            group = replace(group, environments=tuple(e for e in group.environments if e.shell_orbit_id in shells))
            if not group.environments:
                continue
        groups.append(replace(group, subsystem=subsystem, subtypes=assignments))
    return replace(classification, groups=tuple(groups), unassigned_site_ids=tuple(sorted(unassigned)))
