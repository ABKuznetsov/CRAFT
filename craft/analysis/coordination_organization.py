"""Select coordination roles, then use the same hierarchy for both subsystems.

This is CRAFT interpretation of native facts, not oxidation-state assignment.
Polyhedral sharing geometry is supplied by CrIStMa, never reconstructed here.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import json
import math

from cristma.chemistry import InteractionLayer
from cristma.crystal_chemistry import (
    ShellRole, StructuralRepresentationBuilder, StructuralSelectionPolicy,
)
from cristma.reference_data import ReferenceData

from craft.analysis.connectivity_hierarchy import (
    analyze_connectivity_hierarchy, select_primary_ligand_representation, native_ligand_degrees,
)
from craft.analysis.inorganic_classification import (
    ClassEnvironment, ClassSubsystem, CompoundClass, PolymerizationAssignment, RingMotif,
    RING_OPENING_WARNING, _symbol,
)
from craft.analysis.coordination_boundaries import native_boundary_variants
from craft.analysis.anion_attachment import analyze_anion_attachment
from craft.analysis.average_positions import (
    coincident_shell_alternatives, position_provenance, average_position_evidence,
)


@dataclass(frozen=True, slots=True)
class CentreFeatures:
    unit_orbit_id: str
    site_id: str
    elements: tuple[str, ...]
    ligand_elements: tuple[str, ...]
    coordination_number: int
    shell_orbit_id: str
    role: str
    status: str
    formal_charge: float | None = None


def _sharing_analyzer():
    try:
        from cristma.crystal_chemistry.polyhedron_sharing import PolyhedronSharingAnalyzer
    except ModuleNotFoundError as error:
        if error.name != 'cristma.crystal_chemistry.polyhedron_sharing':
            raise
        return None
    return PolyhedronSharingAnalyzer()


def sharing_capability() -> str:
    analyzer = _sharing_analyzer()
    return analyzer.get_config()['method'] if analyzer is not None else 'unavailable'


def _features(structure, polyhedra, units, classification):
    sites = {site.id:site for site in structure.sites}
    poly_by_shell = {orbit.representative.source_shell_orbit_id:orbit.representative
                     for orbit in polyhedra.polyhedron_orbits}
    anion_sites = {e.site_id for group in classification.groups for e in group.environments}
    anion_sites.update(site for group in classification.groups if group.subsystem is not None
                       for site in group.subsystem.supporting_site_ids)
    reference = ReferenceData.default()
    features = []
    for unit in units.unit_orbits:
        poly = poly_by_shell.get(unit.source_shell_orbit_id)
        if poly is None:
            continue
        site = sites[unit.center_independent_site_id]
        elements = tuple(sorted({_symbol(c) for c in site.components if c.occupancy.value > 0}))
        ligand_elements = tuple(sorted({symbol for symbol, _ in poly.ligand_composition}))
        if site.id in anion_sites:
            role = 'anion_subsystem'
        elif elements and all(reference.elements.by_symbol(symbol).is_metal for symbol in elements):
            role = 'cation_coordination'
        else:
            role = 'unassigned'
        conditional = (len(elements) > 1 or not math.isclose(site.total_occupancy, 1)
                       or any(not math.isclose(vertex.occupancy, 1) for vertex in poly.vertices))
        features.append(CentreFeatures(
            unit.unit_orbit_id, site.id, elements, ligand_elements, poly.coordination_number,
            unit.source_shell_orbit_id, role, 'conditional' if conditional else 'supported',
        ))
    return tuple(features)


def _assignments(structure, subsystem, features, boundary_shell_ids=frozenset()):
    by_unit = {f.unit_orbit_id:f for f in features}
    labels = {s.id:s.label for s in structure.sites}
    blocks = {frozenset(b.unit_orbit_ids):b for b in subsystem.blocks.blocks}
    _, bridging_degree = native_ligand_degrees(subsystem.representation,set(by_unit))
    witnesses = {w.component_id:w for w in subsystem.component_witnesses}
    equivalent_ids = {key for w in witnesses.values() for key in w.equivalent_component_ids if key != w.component_id}
    assignments = []
    for component in subsystem.connectivity.components:
        if component.component_id in equivalent_ids:
            continue
        witness = witnesses.get(component.component_id)
        members = tuple(by_unit[key] for key in component.unit_orbit_ids if key in by_unit)
        block = blocks[frozenset(component.unit_orbit_ids)]
        motifs = []
        for ring in subsystem.rings.ring_orbits:
            if ring.parent_block_id != block.block_id:
                continue
            counts = Counter(by_unit[ref.unit_orbit_id].coordination_number for ref in ring.unit_orbit_refs if ref.unit_orbit_id in by_unit)
            if sum(counts.values()) < 3:
                continue
            motifs.append(RingMotif(
                ring.ring_orbit_id, sum(counts.values()), ring.size, tuple(sorted(counts.items())),
                ring.multiplicity_in_reference_cell,
                tuple(sorted(Counter(ref.unit_orbit_id for ref in ring.unit_orbit_refs if ref.unit_orbit_id in by_unit).items())),
            ))
        rank = component.rank
        linked = (len(members) > 1 or any(bridging_degree[f.unit_orbit_id] > 0 for f in members)
                  or all(key in by_unit for key in component.unit_orbit_ids) and bool(component.connection_orbit_ids))
        subtype = {1:'chain',2:'layer',3:'framework'}.get(rank, 'finite_block' if linked else 'isolated')
        name = {0:'Finite cation block' if linked else 'No cation–cation sharing under this criterion',
                1:'Cation chain / ribbon',2:'Cation layer',3:'Cation framework'}[rank]
        site_counts = Counter(f.site_id for f in members)
        name += ' · ' + ', '.join(labels[site] + (f' × {count}' if count > 1 else '')
                                for site, count in sorted(site_counts.items()))
        if witness is not None and len(witness.path_unit_orbit_refs) > 1:
            path = tuple(labels[by_unit[ref.unit_orbit_id].site_id] for ref in witness.path_unit_orbit_refs
                         if ref.unit_orbit_id in by_unit)
            if len(path) > 1:
                name = 'Finite cation fragment · ' + '–'.join(min(path, tuple(reversed(path))))
        if witness is not None and witness.multiplicity_in_reference_cell > 1:
            name += f' · {witness.multiplicity_in_reference_cell} equivalent blocks/cell'
        warnings = ['Ring motifs are bounded native witnesses, not an exhaustive ring inventory.']
        if motifs:
            warnings.append(RING_OPENING_WARNING)
        conditional = any(f.status != 'supported' for f in members)
        if conditional:
            warnings.append('Mixed or partially occupied centres/ligands; connectivity describes the average model.')
        if subtype == 'isolated':
            warnings.append('This is isolation in the selected cation graph; attachment to anion units and spatial location are separate descriptors.')
        if any(f.shell_orbit_id in boundary_shell_ids for f in members):
            warnings.append('Connectivity uses selected inner shells. Larger native coordination boundaries are available.')
            if subtype == 'isolated':
                name += ' · selected inner shell'
        assignments.append(PolymerizationAssignment(
            component.component_id, subsystem.representation.representation_id, subtype, name, rank,
            'conditional' if conditional else 'supported',
            tuple(sorted({f.coordination_number for f in members})),
            tuple(sorted({m.centre_count for m in motifs})), tuple(f.unit_orbit_id for f in members),
            tuple(sorted({f.site_id for f in members})), tuple(sorted({f.shell_orbit_id for f in members})),
            (f'CrIStMa periodic rank: {rank}; connectivity of the explicitly selected native representation.',)
            + average_position_evidence(structure, subsystem.representation, {f.site_id for f in members}),
            tuple(warnings), 'https://pymatgen.org/pymatgen.analysis.chemenv.connectivity.html',
            tuple(motifs), 'within_policy' if subsystem.rings.status.value == 'complete' else 'incomplete',
            dict(subsystem.rings.provenance)['policy']['maximum_ring_size'],
            witness,
            connectivity_scope='cation_subsystem',
        ))
    return tuple(assignments)


def classify_coordination_organization(structure, contacts, polyhedra, units, graph, classification, ring_policy,
                                     *, subsystem_revision=4):
    features = _features(structure, polyhedra, units, classification)
    cations = tuple(f for f in features if f.role == 'cation_coordination')
    if not cations:
        return replace(classification, centre_features=features)
    alternatives = (coincident_shell_alternatives(structure, polyhedra, {f.shell_orbit_id for f in cations})
                    if subsystem_revision >= 4 else {})
    selected_cations = tuple(f for f in cations if f.shell_orbit_id not in alternatives)
    sites = {s.id:s for s in structure.sites}
    analyzer = _sharing_analyzer()
    attachment_analysis,attachments = analyze_anion_attachment(
        contacts,polyhedra,units,features,classification,analyzer,
    )
    boundaries = native_boundary_variants(contacts,tuple(f.unit_orbit_id for f in selected_cations),polyhedra,units,analyzer)
    boundary_shell_ids = frozenset(key for key,variants in boundaries.items() if variants)
    poly_by_shell = {o.representative.source_shell_orbit_id:o.representative for o in polyhedra.polyhedron_orbits}
    environments = tuple(ClassEnvironment(
        f.site_id, sites[f.site_id].label, f.shell_orbit_id, poly_by_shell[f.shell_orbit_id].polyhedron_orbit_id,
        f.coordination_number, 'native coordination polyhedron',
        sum(c.occupancy.value for c in sites[f.site_id].components), f.status,
        ('Selected native coordination environment; formal charge is not inferred.',),
        coordination_boundaries=boundaries.get(f.shell_orbit_id,()),
        anion_attachment=attachments.get(f.shell_orbit_id),
    ) for f in cations)
    sharing, component_analyzer = None, None
    primary_features = selected_cations
    if analyzer is None:
        representation = select_primary_ligand_representation(
            graph, tuple(f.unit_orbit_id for f in selected_cations), identity='craft.coordination:primary_ligands',
        )
    else:
        from cristma.crystal_chemistry.polyhedron_sharing import PolyhedralComponentAnalyzer
        sharing = analyzer.analyze(contacts, polyhedra, units,
                                  selected_unit_orbit_ids=tuple(f.unit_orbit_id for f in selected_cations))
        source_features = {f.unit_orbit_id:f for f in selected_cations}
        primary_features = tuple(replace(source_features[source_id], unit_orbit_id=image_id)
                                 for image_id, source_id in sharing.unit_sources)
        component_analyzer = PolyhedralComponentAnalyzer(contacts)
        native_graph = sharing.incidence_graph
        layers = frozenset(layer for c in native_graph.connection_orbits for layer in c.interaction_layers)
        representation = StructuralRepresentationBuilder(StructuralSelectionPolicy(
            layers or frozenset({InteractionLayer.INTERSTITIAL}), frozenset({ShellRole.PRIMARY}),
        )).build(native_graph)
        representation = replace(representation, representation_id='craft.coordination:primary_ligands:'
                                 + hashlib.sha256(representation.representation_id.encode()).hexdigest(),
                                 provenance=native_graph.provenance + representation.provenance)
    representation = replace(representation, provenance=representation.provenance + position_provenance(alternatives))
    hierarchy = analyze_connectivity_hierarchy(representation, ring_policy, component_analyzer=component_analyzer)
    subsystem = ClassSubsystem(representation,hierarchy.connectivity,hierarchy.blocks,hierarchy.rings,
                               tuple(f.unit_orbit_id for f in primary_features),
                               component_witnesses=hierarchy.component_witnesses)
    status = 'conditional' if any(f.status != 'supported' for f in cations) else 'supported'
    primary = CompoundClass('cation','Via primary ligand contacts',environments,status,'',
                             warnings=('Mixed or partially occupied centres/ligands; connectivity describes the average model.',)
                             if status == 'conditional' else (),
                             subtypes=_assignments(structure,subsystem,primary_features,boundary_shell_ids),subsystem=subsystem)
    if analyzer is None:
        group = replace(primary,warnings=primary.warnings + (
            'CrIStMa polyhedron-sharing calculator is unavailable; edge/face sharing is unresolved. '
            'The displayed hierarchy uses primary cation–ligand contacts.',))
        return replace(classification, centre_features=features, cation_groups=(group,))
    graph = sharing.graph
    sharing_features = primary_features
    layers = frozenset(layer for u in graph.unit_orbits for layer in u.interaction_layers)
    base = StructuralRepresentationBuilder(StructuralSelectionPolicy(
        layers or frozenset({InteractionLayer.INTERSTITIAL}), frozenset({ShellRole.PRIMARY}),
    )).build(graph)
    base = replace(base, provenance=graph.provenance + base.provenance + position_provenance(alternatives))
    groups = [primary]
    for mode, title, included in (
        ('faces','Shared faces', {'shared_face'}),
        ('edges_faces','Shared edges and faces', {'shared_edge','shared_face'}),
        ('all_sharing','Shared vertices, edges and faces', {'shared_vertex','shared_edge','shared_face'}),
    ):
        connections = tuple(c for c in graph.connection_orbits if c.relation_type.value in included)
        fingerprint = hashlib.sha256(json.dumps((mode, sorted(f.unit_orbit_id for f in sharing_features),
                                                 [c.connection_orbit_id for c in connections])).encode()).hexdigest()
        representation = replace(base, representation_id=f'craft.coordination:{mode}:{fingerprint}',
                                 unit_orbits=graph.unit_orbits, connection_orbits=connections,
                                 excluded_connection_orbit_ids=tuple(sorted(c.connection_orbit_id for c in graph.connection_orbits
                                                                          if c.relation_type.value not in included)),
                                 provenance=base.provenance + (('sharing_policy',mode),))
        hierarchy = analyze_connectivity_hierarchy(representation, ring_policy, component_analyzer=component_analyzer)
        subsystem = ClassSubsystem(representation, hierarchy.connectivity, hierarchy.blocks, hierarchy.rings,
                                   tuple(f.unit_orbit_id for f in sharing_features),
                                   component_witnesses=hierarchy.component_witnesses)
        groups.append(CompoundClass('cation', title, environments, status, '',
                                    subtypes=_assignments(structure,subsystem,sharing_features,boundary_shell_ids), subsystem=subsystem))
    for environment in environments:
        for boundary in environment.coordination_boundaries:
            graph = boundary.geometry_graph
            connections = tuple(c for c in graph.connection_orbits if c.relation_type.value == 'shared_face')
            representation = replace(base, representation_id='craft.coordination:boundary:' + boundary.key + '/faces',
                unit_orbits=graph.unit_orbits,connection_orbits=connections,
                excluded_connection_orbit_ids=tuple(c.connection_orbit_id for c in graph.connection_orbits
                                                    if c.relation_type.value != 'shared_face'),
                provenance=base.provenance + (('coordination_boundary',boundary.key),))
            variant_features = tuple(replace(f,coordination_number=boundary.coordination_number,
                                            status='conditional' if boundary.conditional else f.status)
                                     if f.shell_orbit_id == boundary.source_shell_id else f for f in sharing_features)
            hierarchy = analyze_connectivity_hierarchy(representation,ring_policy,component_analyzer=component_analyzer)
            subsystem = ClassSubsystem(representation,hierarchy.connectivity,hierarchy.blocks,hierarchy.rings,
                tuple(f.unit_orbit_id for f in variant_features),component_witnesses=hierarchy.component_witnesses)
            variant_environments = tuple(replace(e,coordination_boundaries=(),
                coordination_number=boundary.coordination_number,coordination_partition=boundary.coordination_partition,
                status='conditional' if boundary.conditional else e.status,
                coordination_boundary_key=boundary.key) if e.shell_orbit_id == boundary.source_shell_id
                else replace(e,coordination_boundaries=()) for e in environments)
            partition = '+'.join(map(str,boundary.coordination_partition))
            groups.append(CompoundClass('cation',f'Shared faces · {environment.site_label} CN {partition}',
                variant_environments,'conditional' if any(f.status != 'supported' for f in variant_features) else 'supported','',
                warnings=('One native outer-boundary alternative is selected; all other environments retain their inner shells.',),
                subtypes=_assignments(structure,subsystem,variant_features),subsystem=subsystem))
    return replace(classification, centre_features=features, cation_groups=tuple(groups),
                   polyhedron_sharing=sharing,anion_attachment_analysis=attachment_analysis)
