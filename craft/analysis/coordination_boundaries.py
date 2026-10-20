"""Retain larger, nested CrIStMa shell alternatives as explicit model choices."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

from cristma.crystal_chemistry import (
    PolyhedronOrbitBuilder, StructuralUnitBuilder, aggregate_contact_analysis_status,
    StructuralUnitGraph,
)


@dataclass(frozen=True, slots=True)
class CoordinationBoundary:
    key: str
    source_shell_id: str
    alternative_id: str
    coordination_partition: tuple[int, int]
    inner_distance_range: tuple[float, float]
    outer_distance_range: tuple[float, float]
    added_ligand_site_counts: tuple[tuple[str, int], ...]
    geometry_graph: StructuralUnitGraph
    conditional: bool

    @property
    def coordination_number(self) -> int:
        return sum(self.coordination_partition)


def native_boundary_variants(contacts, centre_unit_ids, polyhedra, units, analyzer):
    """Select existing native supersets; delegate all geometry and sharing.

    Each model changes one environment and keeps other selected shells fixed.
    Outer candidates are alternatives, not automatically new primary bonds.
    """
    if analyzer is None:
        return {}
    shells_by_unit = {u.unit_orbit_id:u.source_shell_orbit_id for u in units.unit_orbits}
    chosen_shells = {shells_by_unit[key] for key in centre_unit_ids}
    incidences = {i.incidence_orbit_id:i for i in contacts.contact_incidence_orbits}
    geometry = {g.geometry_orbit_id:g for g in contacts.pair_table.contact_orbits}
    resolved = {r.resolved_contact_orbit_id:r for r in contacts.contact_orbits}

    def distance_range(ids):
        values = [geometry[resolved[incidences[key].resolved_contact_orbit_id].geometry_orbit_id].representative_distance
                  for key in ids]
        return min(values), max(values)

    result = {}
    for shell in contacts.coordination_shell_orbits:
        if shell.shell_orbit_id not in chosen_shells or shell.selected is None:
            continue
        inner = set(shell.selected.primary_incidence_ids)
        variants = []
        for alternative in sorted(shell.alternatives,key=lambda a:(a.geometric_CN,a.alternative_id)):
            if not inner < set(alternative.primary_incidence_ids):
                continue
            outer = set(alternative.primary_incidence_ids) - inner
            model = replace(contacts, coordination_shell_orbits=tuple(
                replace(s,selected_alternative=alternative.alternative_id)
                if s.shell_orbit_id == shell.shell_orbit_id else s for s in contacts.coordination_shell_orbits))
            chosen_shell = next(s for s in model.coordination_shell_orbits if s.shell_orbit_id == shell.shell_orbit_id)
            local_model = replace(model,coordination_shell_orbits=(chosen_shell,),status=aggregate_contact_analysis_status(
                model.pair_table.status,(chosen_shell.status,)))
            local_polyhedra = PolyhedronOrbitBuilder().build(local_model)
            local_units = StructuralUnitBuilder().build(local_model,local_polyhedra)
            changed_unit = next(u for u in local_units.unit_orbits if u.source_shell_orbit_id == shell.shell_orbit_id)
            variant_polyhedra = replace(polyhedra,
                polyhedra=tuple(local_polyhedra.polyhedra[0] if p.source_shell_orbit_id == shell.shell_orbit_id else p
                                for p in polyhedra.polyhedra),
                polyhedron_orbits=tuple(local_polyhedra.polyhedron_orbits[0]
                    if p.representative.source_shell_orbit_id == shell.shell_orbit_id else p for p in polyhedra.polyhedron_orbits))
            native_units = replace(units,unit_orbits=tuple(changed_unit if u.source_shell_orbit_id == shell.shell_orbit_id
                                                         else u for u in units.unit_orbits))
            sharing = analyzer.analyze(model,variant_polyhedra,native_units,selected_unit_orbit_ids=centre_unit_ids)
            counts = Counter()
            for key in outer:
                i = incidences[key]
                counts[i.ligand_independent_site_id] += i.incidence_multiplicity_per_center
            variants.append(CoordinationBoundary(
                f'craft.coordination_boundary:{shell.shell_orbit_id}/{alternative.alternative_id}',
                shell.shell_orbit_id,alternative.alternative_id,
                (shell.selected.geometric_CN,alternative.geometric_CN-shell.selected.geometric_CN),
                distance_range(inner),distance_range(outer),tuple(sorted(counts.items())),sharing.graph,
                any(incidences[key].effective_neighbor_occupancy != 1 for key in alternative.primary_incidence_ids),
            ))
        result[shell.shell_orbit_id] = tuple(variants)
    return result
