"""One chemistry-independent hierarchy over an explicit native representation."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from collections import defaultdict
from fractions import Fraction
import hashlib
import json

from cristma.crystal_chemistry import (
    PeriodicConnectivityAnalyzer, PeriodicConnectivityResult, RingAnalysisResult,
    RingFinder, RingSearchPolicy, StructuralBlockFinder, StructuralBlockResult,
    StructuralRepresentation,
    StructuralRepresentationBuilder, StructuralSelectionPolicy, StructuralUnitKind, ShellRole,
)


@dataclass(frozen=True, slots=True)
class ConnectivityHierarchy:
    representation: StructuralRepresentation
    connectivity: PeriodicConnectivityResult
    blocks: StructuralBlockResult
    rings: RingAnalysisResult
    component_witnesses: tuple = field(default=(), kw_only=True)


def analyze_connectivity_hierarchy(
    representation: StructuralRepresentation, ring_policy: RingSearchPolicy, *, component_analyzer=None,
) -> ConnectivityHierarchy:
    """Calculate identical connectivity descriptors for any selected node roles."""
    connectivity = PeriodicConnectivityAnalyzer().analyze(representation)
    blocks = StructuralBlockFinder().find(representation, connectivity)
    rings = RingFinder(ring_policy).find(representation, blocks)
    witnesses = component_analyzer.analyze(representation, connectivity) if component_analyzer is not None else ()
    return ConnectivityHierarchy(representation, connectivity, blocks, rings, component_witnesses=witnesses)


def select_primary_ligand_representation(graph, centre_unit_ids, *, identity, ligand_site_ids=None):
    """Select existing native contacts by centre features; calculate no geometry."""
    units = {unit.unit_orbit_id:unit for unit in graph.unit_orbits}
    centres = set(centre_unit_ids)
    layers = frozenset(layer for key in centres for layer in units[key].interaction_layers)
    if not layers:
        raise ValueError('selected centres have no native interaction layers')
    base = StructuralRepresentationBuilder(StructuralSelectionPolicy(layers, frozenset({ShellRole.PRIMARY}))).build(graph)
    ligands = {unit.unit_orbit_id for unit in base.unit_orbits
               if unit.kind is StructuralUnitKind.ATOM
               and (ligand_site_ids is None or unit.center_independent_site_id in ligand_site_ids)}
    edges = []
    for edge in base.connection_orbits:
        first, second = edge.first_unit_orbit_id, edge.second_unit_orbit_id
        centre = first if first in centres and second in ligands else second if second in centres and first in ligands else None
        if centre is not None and set(edge.source_resolved_contact_orbit_ids) <= set(units[centre].source_resolved_contact_orbit_ids):
            edges.append(edge)
    keep = centres | {key for edge in edges for key in (edge.first_unit_orbit_id,edge.second_unit_orbit_id)}
    fingerprint = hashlib.sha256(json.dumps((identity, sorted(keep), [e.connection_orbit_id for e in edges])).encode()).hexdigest()
    return replace(base, representation_id=f'{identity}:{fingerprint}',
                   unit_orbits=tuple(unit for unit in graph.unit_orbits if unit.unit_orbit_id in keep),
                   connection_orbits=tuple(edges),
                   excluded_unit_orbit_ids=tuple(unit.unit_orbit_id for unit in graph.unit_orbits if unit.unit_orbit_id not in keep),
                   excluded_connection_orbit_ids=tuple(sorted({e.connection_orbit_id for e in graph.connection_orbits}
                                                            - {e.connection_orbit_id for e in edges})),
                   provenance=graph.provenance + base.provenance
                   + (('selection_method','craft.feature_selected_primary_ligands:1'),))


def native_ligand_degrees(representation, centres):
    """Interpret exact native contact/site multiplicities without image recounts."""
    units = {unit.unit_orbit_id:unit for unit in representation.unit_orbits}
    explicit_images = dict(representation.provenance).get('quotient') == 'translations_with_explicit_site_images'
    contacts = defaultdict(dict)
    oriented = []
    for edge in representation.connection_orbits:
        first, second = edge.first_unit_orbit_id,edge.second_unit_orbit_id
        if (first in centres) == (second in centres):
            continue
        centre, ligand = (first,second) if first in centres else (second,first)
        contact_ids = (edge.connection_orbit_id,) if explicit_images else edge.source_resolved_contact_orbit_ids
        for contact_id in contact_ids:
            contacts[ligand][contact_id] = edge.multiplicity_in_reference_cell
        oriented.append((centre,ligand,edge))
    ligand_degree = {key:Fraction(sum(values.values()),units[key].multiplicity_in_reference_cell)
                     for key,values in contacts.items()}
    bridging_contacts = defaultdict(dict)
    for centre,ligand,edge in oriented:
        if ligand_degree[ligand] > 1:
            contact_ids = (edge.connection_orbit_id,) if explicit_images else edge.source_resolved_contact_orbit_ids
            for contact_id in contact_ids:
                bridging_contacts[centre][contact_id] = edge.multiplicity_in_reference_cell
    bridging_degree = {key:Fraction(sum(bridging_contacts[key].values()),units[key].multiplicity_in_reference_cell)
                       for key in centres}
    return ligand_degree,bridging_degree
