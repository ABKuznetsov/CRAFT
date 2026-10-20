"""Project a chosen native shell alternative without borrowing core geometry."""
from collections import Counter
from dataclasses import replace


def group_polyhedron_rows(document,group,view):
    if group.subsystem is None:
        return view.polyhedron_orbits
    changed = {e.shell_orbit_id:e for e in group.environments if e.coordination_partition}
    if not changed:
        return view.polyhedron_orbits
    units = {u.source_shell_orbit_id:u for u in group.subsystem.representation.unit_orbits
             if u.source_shell_orbit_id in changed}
    sites_by_atom = {atom_id: row.source_site_id
                     for row in view.atom_orbits for atom_id in row.atom_ids}
    rows = []
    for row in view.polyhedron_orbits:
        env = changed.get(row.source_shell_id)
        unit = units.get(row.source_shell_id)
        if env is not None and unit is not None:
            counts = Counter(sites_by_atom[ref.atom_id] for ref in unit.representative_geometry.vertex_atom_refs)
            partition = '+'.join(map(str,env.coordination_partition))
            row = replace(row,label=f'{env.site_label} — CN {partition}',
                coordination_number=env.coordination_number,face_signature=None,
                geometry_label=f'CN {partition} ({env.coordination_number})',
                ligand_site_counts=tuple(sorted(counts.items())),coordination_boundary_key=env.coordination_boundary_key)
        rows.append(row)
    return tuple(rows)
