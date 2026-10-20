"""Draw simultaneous crystal-chemical levels with independent materials."""

from __future__ import annotations

import numpy as np
import pyvista as pv

from craft.ui.render_batches import (
    CylinderInstance, SphereInstance, SurfaceInstance, build_cylinder_batch,
    build_sphere_batch, build_surface_batch,
)
from craft.presentation.crystal_layers import displayed_crystal_layer, layer_member_hidden


def draw_crystal_layers(viewer) -> None:
    from craft.ui.viewer import (
        PICK_CRYSTAL_LAYER, _tag_pick_kind, _composition_display_radius, _shade,
    )

    scene = viewer.native_scene
    styles = getattr(viewer, "crystal_layers", {})
    atom_rows = {row.source_site_id: row for row in viewer.native_presentation.atom_orbits}
    compositions = {atom.source_site_id: atom.composition for atom in scene.atoms}

    def add_mesh(mesh, index, color, **options):
        if mesh is not None:
            mesh.cell_data['source_index'] = np.full(mesh.n_cells, index, dtype=np.int64)
            _tag_pick_kind(mesh, PICK_CRYSTAL_LAYER)
            viewer.plotter.add_mesh(mesh, color=color, **options)
    # General levels first; smaller rings have thicker lines at shared edges.
    draw_layers = []
    for index, layer in sorted(enumerate(scene.crystal_layers),
                               key=lambda pair: (pair[1].priority, -len(pair[1].segments))):
        style = styles.get(layer.key)
        if style is None or not style.visible:
            continue
        layer = displayed_crystal_layer(layer, styles, getattr(getattr(viewer, "structure", None), "cell", None))
        draw_layers.append((index, layer, style))

    def polyhedron_key(polyhedron):
        return (polyhedron.polyhedron_orbit_id,
                tuple(round(value, 7) for value in polyhedron.center))

    def segment_key(segment):
        endpoints = tuple(tuple(round(value, 7) for value in point) for point in segment)
        return tuple(sorted(endpoints))

    # A more specific selected ring recolours the matching constituent of its
    # parent assembly.  Give the last (smallest) visible level ownership of a
    # coincident polyhedron so coplanar faces cannot intersect or flicker.
    polyhedron_owner = {}
    segment_owner = {}
    for index, layer, style in draw_layers:
        if style.representation in {"polyhedra", "edges"}:
            for polyhedron in layer.polyhedra:
                if layer_member_hidden(layer, style, polyhedron):
                    continue
                polyhedron_owner[polyhedron_key(polyhedron)] = index
        if layer.priority == 1:
            for segment in layer.segments:
                segment_owner[segment_key(segment)] = index

    from craft.ui.ring_layer_context import draw_ring_context
    draw_ring_context(viewer, draw_layers, add_mesh)

    for index, layer, style in draw_layers:
        radius = max(viewer.bond_radius * 1.2, viewer.polyhedron_edge_radius)
        if layer.priority == 1:
            radius *= 1.5 + 2 / max(len(layer.segments), 1)
        displayed_polyhedra = tuple(
            polyhedron for polyhedron in layer.polyhedra
            if polyhedron_owner.get(polyhedron_key(polyhedron), index) == index
            and not layer_member_hidden(layer, style, polyhedron)
            and polyhedron.polyhedron_orbit_id not in getattr(viewer, "hidden_polyhedron_orbit_ids", ())
        )
        displayed_segments = tuple(
            segment for segment in layer.segments
            if segment_owner.get(segment_key(segment), index) == index
        )
        if layer.atoms:
            atom_groups = {}
            for point, site in layer.atoms:
                if site in getattr(viewer, "hidden_atom_orbit_ids", ()):
                    continue
                color = viewer.atom_orbit_colors.get(site, style.color)
                atom_groups.setdefault(color, []).append(SphereInstance(point, .18 * viewer.atom_scale, index))
            for color, instances in atom_groups.items():
                add_mesh(build_sphere_batch(instances, "medium"), index, color, smooth_shading=True)
            continue
        elif style.representation in {"polyhedra", "edges"}:
            surfaces = []
            for polyhedron in displayed_polyhedra:
                if not polyhedron.faces:
                    continue
                encoded = [value for face in polyhedron.faces for value in (len(face), *face)]
                mesh = pv.PolyData(np.asarray(polyhedron.points), faces=np.asarray(encoded, dtype=np.int64))
                surfaces.append(SurfaceInstance(mesh, (0., 0., 0.), index))
            mesh = build_surface_batch(surfaces)
            if style.representation == "edges" and mesh is not None:
                mesh = mesh.extract_all_edges().tube(radius=radius, n_sides=9)
                options = dict(smooth_shading=True)
            else:
                if mesh is not None:
                    edges = mesh.extract_all_edges().tube(radius=radius, n_sides=9)
                    add_mesh(edges, index, _shade(style.color, .65), smooth_shading=True)
                options = dict(opacity=viewer.polyhedron_opacity, show_edges=False)
        else:
            mesh = build_cylinder_batch(
                [CylinderInstance(start, end, radius, index) for start, end in displayed_segments], "medium",
            )
            options = dict(smooth_shading=True)
        add_mesh(mesh, index, style.color, **options)
        # Filled polyhedra are complete coordination units.  Draw their native
        # central atoms as part of the same foreground layer, including units
        # whose ring image crosses the displayed cell boundary.
        if displayed_polyhedra and (layer.priority >= 2 or style.representation == "polyhedra"):
            groups = {}
            seen = set()
            for poly in displayed_polyhedra:
                key = (poly.center, poly.center_site_id)
                if (key in seen or poly.center_site_id not in compositions
                        or poly.center_site_id in getattr(viewer, "hidden_atom_orbit_ids", ())):
                    continue
                seen.add(key)
                row = atom_rows.get(poly.center_site_id)
                color = viewer.atom_orbit_colors.get(
                    poly.center_site_id, row.default_color if row is not None else style.color,
                )
                groups.setdefault(color, []).append(SphereInstance(
                    poly.center,
                    _composition_display_radius(compositions[poly.center_site_id], viewer.radius_model, len(poly.points))
                    * viewer.atom_scale,
                    index,
                ))
            for color, instances in groups.items():
                add_mesh(build_sphere_batch(instances, "medium"), index, color, smooth_shading=True)
