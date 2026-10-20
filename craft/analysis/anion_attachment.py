"""Interpret native cross-subsystem sharing independently of cation topology.

These facts establish attachment to selected anion units. They do not locate
cations in cavities or channels and do not assign oxidation states.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnionAttachment:
    status: str
    anion_site_ids: tuple[str, ...]
    anion_families: tuple[str, ...]
    anion_ranks: tuple[int, ...]
    sharing_kinds: tuple[str, ...]
    connection_orbit_ids: tuple[str, ...]
    source_boundary: str = 'selected_inner_shell'


def analyze_anion_attachment(contacts,polyhedra,units,features,classification,analyzer):
    cations = {f.unit_orbit_id:f for f in features if f.role == 'cation_coordination'}
    anions = {f.unit_orbit_id:f for f in features if f.role == 'anion_subsystem'}
    if analyzer is None or not cations or not anions:
        return None, {}
    selected = {**cations,**anions}
    native = analyzer.analyze(contacts,polyhedra,units,selected_unit_orbit_ids=tuple(sorted(selected)))
    by_image = {image:selected[source] for image,source in native.unit_sources}
    families,ranks = defaultdict(set),defaultdict(set)
    for group in classification.groups:
        sites = {e.site_id for e in group.environments}
        if group.subsystem is not None:
            sites.update(group.subsystem.supporting_site_ids)
        for site in sites:
            families[site].add(group.family)
        for assignment in group.subtypes:
            for site in assignment.centre_site_ids:
                ranks[site].add(assignment.rank)
    links = defaultdict(list)
    for sharing in native.sharing_orbits:
        first,second = by_image[sharing.first_unit_orbit_id],by_image[sharing.second_unit_orbit_id]
        if first.role == 'anion_subsystem' and second.role == 'cation_coordination':
            first,second = second,first
        if first.role == 'cation_coordination' and second.role == 'anion_subsystem':
            links[first.shell_orbit_id].append((second.site_id,sharing))
    result = {}
    for feature in cations.values():
        facts = links[feature.shell_orbit_id]
        sites = {site for site,_ in facts}
        result[feature.shell_orbit_id] = AnionAttachment(
            'observed' if facts else 'not_observed_in_selected_model',tuple(sorted(sites)),
            tuple(sorted({family for site in sites for family in families[site]})),
            tuple(sorted({rank for site in sites for rank in ranks[site]})),
            tuple(sorted({fact.kind.value for _,fact in facts})),
            tuple(sorted({fact.connection_orbit_id for _,fact in facts})),
        )
    return native,result
