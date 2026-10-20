"""Continue the ordinary atomic/polyhedral model beyond the cell for ring copies."""

from __future__ import annotations

import numpy as np
import pyvista as pv

from craft.presentation.inorganic_scene import visible_atoms, visible_polyhedra
from craft.presentation.crystal_layers import layer_member_hidden
from craft.ui.render_batches import (
    CylinderInstance, SphereInstance, SurfaceInstance,
    build_cylinder_batch, build_sphere_batch, build_surface_batch,
)


def draw_ring_context(viewer, layers, add_mesh):
    """Add only missing native geometry; selection colour belongs to the outline."""
    from craft.ui.viewer import _composition_display_radius, _shade

    scene = viewer.native_scene
    atom_rows = {row.source_site_id: row for row in viewer.native_presentation.atom_orbits}
    poly_rows = {row.polyhedron_orbit_id: row for row in viewer.native_presentation.polyhedron_orbits}
    compositions = {atom.source_site_id: atom.composition for atom in scene.atoms}
    atom_lookup = {(atom.atom_id, atom.cell_translation): atom for atom in scene.atoms}

    def point_key(point):
        return tuple(round(float(value), 6) for value in point)

    def poly_key(orbit, center):
        return orbit, point_key(center)

    existing_polyhedra, existing_atoms = set(), set()
    if viewer.show_atoms:
        existing_atoms.update((atom.source_site_id, point_key(atom.cartesian))
                              for atom in visible_atoms(scene, viewer, include_auto_hidden=False))
    if viewer.show_polyhedra:
        for poly in visible_polyhedra(scene, viewer, include_auto_hidden=False):
            atom = atom_lookup[(poly.center_atom_id, poly.center_translation)]
            existing_polyhedra.add(poly_key(poly.polyhedron_orbit_id, atom.cartesian))
            existing_atoms.add((atom.source_site_id, point_key(atom.cartesian)))
            for vertex, site in zip(poly.local_vertices, poly.vertex_source_site_ids):
                existing_atoms.add((site, point_key(np.asarray(atom.cartesian) + vertex)))

    def atom_color(site):
        row = atom_rows.get(site)
        return viewer.atom_orbit_colors.get(site, row.default_color if row else "#aab4c0")

    seen_polyhedra = set(existing_polyhedra)
    seen_atoms = set(existing_atoms)
    surfaces, spheres, bonds = {}, {}, {}
    for index, layer, style in layers:
        if layer.priority != 1 or style.representation != "edges":
            continue
        for poly in layer.polyhedra:
            key = poly_key(poly.polyhedron_orbit_id, poly.center)
            if (poly.polyhedron_orbit_id in viewer.hidden_polyhedron_orbit_ids
                    or layer_member_hidden(layer, style, poly)):
                continue
            missing_polyhedron = key not in seen_polyhedra
            seen_polyhedra.add(key)
            if missing_polyhedron and viewer.show_polyhedra and poly.faces:
                encoded = [value for face in poly.faces for value in (len(face), *face)]
                mesh = pv.PolyData(np.asarray(poly.points), faces=np.asarray(encoded, dtype=np.int64))
                row = poly_rows.get(poly.polyhedron_orbit_id)
                color = viewer.polyhedron_orbit_colors.get(
                    poly.polyhedron_orbit_id, row.default_color if row else "#4ea6a1",
                )
                surfaces.setdefault((index, color), []).append(SurfaceInstance(mesh, (0., 0., 0.), index))
                if viewer.show_polyhedron_edges:
                    add_mesh(mesh.extract_all_edges().tube(radius=viewer.polyhedron_edge_radius, n_sides=9),
                             index, "#000000", smooth_shading=True, opacity=.92 * .25)

            atoms = [(poly.center, poly.center_site_id, len(poly.points))]
            atoms.extend((point, site, None) for point, site in zip(poly.points, poly.point_site_ids))
            if viewer.show_atoms or viewer.show_polyhedra:
                for point, site, coordination in atoms:
                    atom_key = site, point_key(point)
                    if atom_key in seen_atoms or site in viewer.hidden_atom_orbit_ids:
                        continue
                    seen_atoms.add(atom_key)
                    radius = _composition_display_radius(
                        compositions.get(site, ()), viewer.radius_model, coordination,
                    ) * viewer.atom_scale
                    spheres.setdefault((index, atom_color(site)), []).append(SphereInstance(point, radius, index))

            if missing_polyhedron and (viewer.show_bonds or
                                      viewer.show_polyhedra and viewer.show_polyhedron_spokes):
                for point, site in zip(poly.points, poly.point_site_ids):
                    if site in viewer.hidden_atom_orbit_ids or poly.center_site_id in viewer.hidden_atom_orbit_ids:
                        continue
                    midpoint = tuple((np.asarray(poly.center) + point) / 2.)
                    radius = viewer.bond_radius if viewer.show_bonds else min(viewer.bond_radius, .015)
                    for start, end, color in ((poly.center, midpoint, atom_color(poly.center_site_id)),
                                              (midpoint, point, atom_color(site))):
                        bonds.setdefault((index, _shade(color, .82)), []).append(
                            CylinderInstance(start, end, radius, index),
                        )

    for (index, color), instances in surfaces.items():
        add_mesh(build_surface_batch(instances), index, color,
                 opacity=viewer.polyhedron_opacity * .25, show_edges=False)
    for (index, color), instances in spheres.items():
        add_mesh(build_sphere_batch(instances, "medium"), index, color,
                 smooth_shading=True, opacity=.25)
    for (index, color), instances in bonds.items():
        add_mesh(build_cylinder_batch(instances, "medium"), index, color,
                 smooth_shading=True, opacity=.96 * .25)
