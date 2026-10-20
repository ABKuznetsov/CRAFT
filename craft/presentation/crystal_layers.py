"""Simultaneous presentation levels over native class components and ring images.

Coordinates, symmetry relations and faces come from CrIStMa. This module only
materializes those records for display; it does not search rings or build hulls.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
import hashlib

import numpy as np

from craft.core.visualization import CrystalLayerStyle
from craft.presentation.inorganic_scene import Edge, Point, _frac_to_cart
from craft.presentation.coordination_rows import group_polyhedron_rows


@dataclass(frozen=True, slots=True)
class CrystalLayerOption:
    key: str
    kind: str
    label: str
    polyhedron_orbit_ids: tuple[str, ...] = ()
    representation_id: str = ""
    ring_id: str = ""
    unit_orbit_id: str = ""
    site_id: str = ""
    component_id: str = ""
    boundary_key: str = ""
    individual: bool = False


@dataclass(frozen=True, slots=True)
class LayerPolyhedron:
    center: Point
    points: tuple[Point, ...]
    faces: tuple[tuple[int, ...], ...]
    polyhedron_orbit_id: str = ""
    center_site_id: str = ""
    point_site_ids: tuple[str, ...] = ()
    unit_orbit_id: str = ""


@dataclass(frozen=True, slots=True)
class CrystalLayerGeometry:
    key: str
    label: str
    priority: int
    segments: tuple[Edge, ...]
    polyhedra: tuple[LayerPolyhedron, ...]
    atoms: tuple[tuple[Point, str], ...] = ()


def layer_member_hidden(layer, style, polyhedron) -> bool:
    """Retain orbit-wide exclusions and exact native ring-image exclusions."""
    return (polyhedron.polyhedron_orbit_id in style.hidden_member_orbit_ids
            or (bool(polyhedron.unit_orbit_id)
                and ring_unit_key(layer.key, polyhedron.unit_orbit_id) in style.hidden_member_orbit_ids))


def displayed_crystal_layer(layer, styles, cell=None) -> CrystalLayerGeometry:
    """Apply a drawing-only shift, including a ring parent's shift for its units."""
    style = styles.get(layer.key)
    offset = np.asarray(style.display_offset if style is not None else (0., 0., 0.))
    if "/unit:" in layer.key:
        parent = styles.get(layer.key.rsplit("/unit:", 1)[0])
        if parent is not None:
            offset = offset + np.asarray(parent.display_offset)
    if not np.any(offset):
        return layer
    shift = offset @ np.asarray(cell.matrix, dtype=float)

    def point(value):
        return tuple(float(x) for x in np.asarray(value) + shift)

    return replace(layer,
                   segments=tuple((point(a), point(b)) for a, b in layer.segments),
                   polyhedra=tuple(replace(poly, center=point(poly.center),
                                           points=tuple(point(p) for p in poly.points))
                                   for poly in layer.polyhedra),
                   atoms=tuple((point(p), site) for p, site in layer.atoms))


def component_key(assignment) -> str:
    return f"{assignment.representation_id}/{assignment.component_id}"


def polyhedra_key(assignment, coordination: int) -> str:
    return f"{component_key(assignment)}/cn:{coordination}"


def component_polyhedron_key(assignment, polyhedron_orbit_id: str) -> str:
    return f"{component_key(assignment)}/polyhedron:{polyhedron_orbit_id}"


def ring_unit_key(ring_id: str, unit_id: str) -> str:
    return f"{ring_id}/unit:{unit_id}"


def coordination_group_label(family: str, coordination: int) -> str:
    from craft.analysis.native_group_rules import class_centre
    if family == 'cation':
        return f'CN {coordination}'
    return f"{'Si/Al' if family == 'silicate' else class_centre(family)}O{coordination}"


def ring_candidate_label(family: str, motif) -> str:
    from craft.analysis.native_group_rules import class_centre
    element = "M" if family == "cation" else "Si/Al" if family == "silicate" else class_centre(family)
    return f"{motif.centre_count} {element} centres · ring candidate · opening unverified"


def cation_centres_key(classification) -> str:
    identifiers = sorted({e.polyhedron_orbit_id for group in classification.cation_groups for e in group.environments})
    return 'craft.cation_centres:' + hashlib.sha256('\n'.join(identifiers).encode()).hexdigest()


def layer_options(document) -> tuple[CrystalLayerOption, ...]:
    classification = getattr(document.scientific.inorganic_classification, "result", None)
    if classification is None:
        return ()
    view = document.inorganic_presentation()
    rows = view.polyhedron_orbits
    options = []
    if classification.cation_groups:
        members = tuple(sorted({e.polyhedron_orbit_id for group in classification.cation_groups for e in group.environments}))
        options.append(CrystalLayerOption(cation_centres_key(classification), 'coordination_set',
                                         'All cation coordination centres', members))
    for group in (*classification.groups, *classification.cation_groups):
        rows = group_polyhedron_rows(document,group,view)
        for environment in group.environments:
            for boundary in environment.coordination_boundaries:
                partition = '+'.join(map(str,boundary.coordination_partition))
                options.append(CrystalLayerOption(boundary.key,'polyhedra',
                    f'{environment.site_label} · CN {partition} ({boundary.coordination_number})',
                    (environment.polyhedron_orbit_id,),boundary_key=boundary.key, individual=True))
        units = ({unit.unit_orbit_id: unit for unit in group.subsystem.representation.unit_orbits}
                 if group.subsystem is not None else {})
        rows_by_shell = {row.source_shell_id: row for row in rows}
        for assignment in group.subtypes:
            shells = set(assignment.source_shell_ids)
            members = tuple(row for row in rows if row.source_shell_id in shells)
            options.append(CrystalLayerOption(
                component_key(assignment), "component", assignment.label,
                tuple(row.polyhedron_orbit_id for row in members), assignment.representation_id,
                component_id=assignment.component_id,
            ))
            options.extend(CrystalLayerOption(
                component_polyhedron_key(assignment, row.polyhedron_orbit_id), "polyhedra", row.label,
                (row.polyhedron_orbit_id,), assignment.representation_id,
                component_id=assignment.component_id, individual=True,
            ) for row in members)
            for motif in assignment.ring_motifs:
                options.append(CrystalLayerOption(
                    motif.ring_orbit_id, "ring", ring_candidate_label(group.family, motif),
                    representation_id=assignment.representation_id,
                ))
                for unit_id, count in motif.unit_image_counts:
                    row = rows_by_shell.get(units[unit_id].source_shell_orbit_id)
                    if row is not None:
                        options.append(CrystalLayerOption(
                            ring_unit_key(motif.ring_orbit_id, unit_id), "polyhedra",
                            f"{row.label} · {count} images in {motif.centre_count}-centre candidate",
                            (row.polyhedron_orbit_id,), assignment.representation_id,
                            motif.ring_orbit_id, unit_id,
                            individual=True,
                        ))
            for cn in assignment.coordination_numbers:
                options.append(CrystalLayerOption(
                    polyhedra_key(assignment, cn), "polyhedra", coordination_group_label(group.family, cn),
                    tuple(row.polyhedron_orbit_id for row in members if row.coordination_number == cn),
                    assignment.representation_id,
                    component_id=assignment.component_id,
                ))
    rows = view.polyhedron_orbits
    options.extend(CrystalLayerOption(
        f"polyhedron:{row.polyhedron_orbit_id}", "polyhedra", row.label,
        (row.polyhedron_orbit_id,), individual=True,
    ) for row in rows)
    options.extend(CrystalLayerOption(
        f"atom:{row.source_site_id}", "atom", row.label, site_id=row.source_site_id,
    ) for row in document.inorganic_presentation().atom_orbits)
    # A native ring orbit may be shared by alternative descriptors.
    return tuple({option.key: option for option in options}.values())


def enable_crystal_layer(document, key: str) -> bool:
    """Add a level without replacing other levels or resetting its saved style."""
    options = layer_options(document)
    option = next((item for item in options if item.key == key), None)
    if option is None:
        return False
    document.visual.crystal_layers_enabled = True
    previous = document.visual.crystal_layers.get(key)
    if previous is not None:
        from dataclasses import replace
        document.visual.crystal_layers[key] = replace(previous, visible=True)
        return True
    document.visual.crystal_layers[key] = default_crystal_layer_style(document, option, options)
    return True


def default_crystal_layer_style(document, option, options=None) -> CrystalLayerStyle:
    """Preview an unselected layer's style without enabling or materializing it."""
    if options is None:
        options = layer_options(document)
    if option.kind == "component":
        color = "#2864c8"
    elif option.kind == 'coordination_set':
        color = '#8b5cb3'
    elif option.kind == "ring":
        rings = sorted((o for o in options if o.kind == "ring"),
                       key=lambda o: (-int(o.label.split()[0]), o.key))
        palette = ("#239b56", "#ed8b23", "#9b59b6", "#d64f70")
        color = palette[rings.index(option) % len(palette)]
    elif option.kind == "atom":
        row = document.inorganic_presentation().atom_orbit(option.site_id)
        color = row.default_color
    else:
        color = "#d4a52c"
    return CrystalLayerStyle(
        color,
        "atoms" if option.kind == "atom"
        else "polyhedra" if option.kind == "polyhedra"
        else "edges",
    )


def _fractional_image(atom_ref, relation, context, atoms):
    atom = atoms[atom_ref.atom_id]
    return relation.apply_fractional(tuple(
        Fraction(atom.fractional[i]) + atom_ref.cell_translation[i] for i in range(3)
    ), context)


def _unit_image_geometry(document, option, subsystem, refs, *, context, atoms,
                         closed_ring=False, display_relation=None) -> CrystalLayerGeometry:
    structure = document.structure
    units = {unit.unit_orbit_id: unit for unit in subsystem.representation.unit_orbits}
    centres = set(subsystem.centre_unit_ids)
    orbit_by_shell = {row.source_shell_id: row.polyhedron_orbit_id
                      for row in document.inorganic_presentation().polyhedron_orbits}

    def point(atom_ref, relation):
        return _frac_to_cart(structure, _fractional_image(atom_ref, relation, context, atoms))

    path, polyhedra = [], []
    for ref in refs:
        geometry = units[ref.unit_orbit_id].representative_geometry
        relation = (display_relation.compose(ref.periodic_relation, context)
                    if display_relation is not None else ref.periodic_relation)
        center = point(geometry.center_atom_ref, relation)
        path.append(center)
        orbit_id = orbit_by_shell.get(units[ref.unit_orbit_id].source_shell_orbit_id, "")
        if (ref.unit_orbit_id in centres and (not option.unit_orbit_id or ref.unit_orbit_id == option.unit_orbit_id)
                and (not option.polyhedron_orbit_ids or orbit_id in option.polyhedron_orbit_ids)):
            polyhedra.append(LayerPolyhedron(
                center,
                tuple(point(atom_ref, relation) for atom_ref in geometry.vertex_atom_refs),
                tuple(tuple(face) for face in geometry.faces),
                orbit_id,
                units[ref.unit_orbit_id].center_independent_site_id,
                tuple(atoms[atom_ref.atom_id].source_site_id for atom_ref in geometry.vertex_atom_refs),
                ref.unit_orbit_id,
            ))
    segments = (tuple((poly.center, vertex) for poly in polyhedra for vertex in poly.points)
                if option.unit_orbit_id or not closed_ring else tuple(zip(path, path[1:] + path[:1])))
    return CrystalLayerGeometry(option.key, option.label, 3 if option.individual else 2 if option.kind == 'polyhedra' else 1,
                                segments, tuple(polyhedra))


def _ring_display_relation(document, ring, subsystem, bounds, context, atoms):
    """Choose a whole symmetry-equivalent ring image near the displayed cell."""
    from cristma.crystallography import PeriodicSymmetryRelation

    units = {unit.unit_orbit_id: unit for unit in subsystem.representation.unit_orbits}
    centres = set(subsystem.centre_unit_ids)
    center_points, vertices = [], []
    for ref in ring.unit_orbit_refs:
        if ref.unit_orbit_id not in centres:
            continue
        geometry = units[ref.unit_orbit_id].representative_geometry
        center_points.append(_fractional_image(geometry.center_atom_ref, ref.periodic_relation, context, atoms))
        vertices.extend(_fractional_image(atom_ref, ref.periodic_relation, context, atoms)
                        for atom_ref in geometry.vertex_atom_refs)
    if not center_points:
        return PeriodicSymmetryRelation(context.identity_operation_key, (0, 0, 0))
    centers = np.asarray(center_points, dtype=float)
    vertices = np.asarray(vertices or center_points, dtype=float)
    # Keep the same image when the displayed supercell grows around the same
    # cell, rather than changing it whenever more neighbours become visible.
    focus_low = np.floor(np.asarray(bounds, dtype=float).mean(axis=1))
    bounds = np.column_stack((focus_low, focus_low + 1.))
    target = bounds.mean(axis=1)
    matrix = np.asarray(document.structure.cell.matrix, dtype=float)
    candidates = []
    explicit_images = dict(subsystem.representation.provenance).get('quotient') == 'translations_with_explicit_site_images'
    for key, operation in zip(context.operation_keys, context.operations):
        # These rings already distinguish the reference-cell symmetry images.
        # A second space-group action would fold separate rings onto one image.
        if explicit_images and key != context.identity_operation_key:
            continue
        rotation = np.asarray(operation.rotation, dtype=float)
        translation = np.asarray(operation.translation, dtype=float)
        image_centers = centers @ rotation.T + translation
        shift = np.floor(target - image_centers.mean(axis=0) + .5).astype(int)
        image_centers += shift
        image_vertices = vertices @ rotation.T + translation + shift

        def inside(points):
            return np.all((points >= bounds[:, 0] - 1e-7) & (points <= bounds[:, 1] + 1e-7), axis=1)

        overhang = (np.maximum(bounds[:, 0] - image_vertices, 0.)
                    + np.maximum(image_vertices - bounds[:, 1], 0.))
        score = (-int(inside(image_centers).sum()), -int(inside(image_vertices).sum()),
                 round(float(np.linalg.norm(overhang @ matrix, axis=1).sum()), 9),
                 round(float(np.linalg.norm((image_centers.mean(axis=0) - target) @ matrix)), 9),
                 key != context.identity_operation_key, key)
        candidates.append((score, PeriodicSymmetryRelation(key, tuple(int(x) for x in shift))))
    return min(candidates, key=lambda candidate: candidate[0])[1]


def _ring_centre_refs(ring, subsystem):
    centres = set(subsystem.centre_unit_ids)
    return tuple(ref for ref in ring.unit_orbit_refs if ref.unit_orbit_id in centres)


def _ring_group_relations(parent, child, subsystem, context):
    """Map a native smaller ring onto all of a larger ring's centre images."""
    parent_refs = _ring_centre_refs(parent, subsystem)
    child_refs = _ring_centre_refs(child, subsystem)
    child_by_unit = {ref.unit_orbit_id: ref for ref in child_refs}
    # A unique unit type at each position makes the native incidence mapping
    # unambiguous.  Other cases require an explicit relation from CrIStMa.
    if (len(child_refs) != 3 or len(child_by_unit) != len(child_refs)
            or not parent_refs
            or not {ref.unit_orbit_id for ref in parent_refs} <= set(child_by_unit)):
        return ()
    relations = []
    for target in parent_refs:
        source = child_by_unit[target.unit_orbit_id]
        relation = target.periodic_relation.compose(
            source.periodic_relation.inverse(context), context,
        )
        if relation not in relations:
            relations.append(relation)
    covered = {
        (ref.unit_orbit_id, relation.compose(ref.periodic_relation, context))
        for relation in relations for ref in child_refs
    }
    targets = {(ref.unit_orbit_id, ref.periodic_relation) for ref in parent_refs}
    if not targets <= covered or len(relations) * len(child_refs) <= len(parent_refs):
        return ()
    return tuple(relations)


def _ring_constituents(ring, subsystem, context):
    """Return a native three-centre building ring and its exact image relations."""
    parent_count = len(_ring_centre_refs(ring, subsystem))
    candidates = sorted(subsystem.rings.ring_orbits,
                        key=lambda item: (len(_ring_centre_refs(item, subsystem)), item.ring_orbit_id))
    for child in candidates:
        child_count = len(_ring_centre_refs(child, subsystem))
        if child.ring_orbit_id == ring.ring_orbit_id or child_count >= parent_count:
            continue
        relations = _ring_group_relations(ring, child, subsystem, context)
        if relations:
            return child, relations
    return None


def _ring_relation_score(document, ring, subsystem, bounds, context, atoms, relation):
    """Rank an already composed ring image against the central displayed cell."""
    units = {unit.unit_orbit_id: unit for unit in subsystem.representation.unit_orbits}
    centres, vertices = [], []
    for ref in _ring_centre_refs(ring, subsystem):
        geometry = units[ref.unit_orbit_id].representative_geometry
        image = relation.compose(ref.periodic_relation, context)
        centres.append(_fractional_image(geometry.center_atom_ref, image, context, atoms))
        vertices.extend(_fractional_image(atom_ref, image, context, atoms)
                        for atom_ref in geometry.vertex_atom_refs)
    centres = np.asarray(centres, dtype=float)
    vertices = np.asarray(vertices or centres, dtype=float)
    focus_low = np.floor(np.asarray(bounds, dtype=float).mean(axis=1))
    focus = np.column_stack((focus_low, focus_low + 1.))
    target = focus.mean(axis=1)
    matrix = np.asarray(document.structure.cell.matrix, dtype=float)

    def inside(points):
        return np.all((points >= focus[:, 0] - 1e-7) & (points <= focus[:, 1] + 1e-7), axis=1)

    overhang = (np.maximum(focus[:, 0] - vertices, 0.)
                + np.maximum(vertices - focus[:, 1], 0.))
    return (-int(inside(centres).sum()), -int(inside(vertices).sum()),
            round(float(np.linalg.norm(overhang @ matrix, axis=1).sum()), 9),
            round(float(np.linalg.norm((centres.mean(axis=0) - target) @ matrix)), 9),
            relation.operation_key, relation.lattice_translation)


def _ring_geometry(document, option, subsystem, *, context, atoms, bounds,
                   display_relation=None, constituents=None) -> CrystalLayerGeometry:
    ring = next(r for r in subsystem.rings.ring_orbits if r.ring_orbit_id == (option.ring_id or option.key))
    relation = display_relation or _ring_display_relation(document, ring, subsystem, bounds, context, atoms)
    if constituents is None:
        return _unit_image_geometry(document, option, subsystem, ring.unit_orbit_refs,
                                    context=context, atoms=atoms, closed_ring=True,
                                    display_relation=relation)
    child, group_relations = constituents
    parts = [
        _unit_image_geometry(
            document, option, subsystem, child.unit_orbit_refs,
            context=context, atoms=atoms, closed_ring=True,
            display_relation=relation.compose(group_relation, context),
        )
        for group_relation in group_relations
    ]
    segments, seen_segments = [], set()
    for part in parts:
        for start, end in part.segments:
            key = tuple(sorted((start, end)))
            if key not in seen_segments:
                seen_segments.add(key)
                segments.append((start, end))
    polyhedra = {}
    for part in parts:
        for polyhedron in part.polyhedra:
            polyhedra[(polyhedron.polyhedron_orbit_id, polyhedron.center)] = polyhedron
    return CrystalLayerGeometry(option.key, option.label, 1,
                                tuple(segments), tuple(polyhedra.values()))


def build_crystal_layers(document, scene) -> tuple[CrystalLayerGeometry, ...]:
    """Materialize chosen native objects; colours and visibility need no rebuild."""
    selected = document.visual.crystal_layers
    if not selected:
        return ()
    options = layer_options(document)
    atoms = {(atom.atom_id, atom.cell_translation): atom for atom in scene.atoms}
    classification = getattr(document.scientific.inorganic_classification, "result", None)
    if classification is None:
        return ()
    context = document.scientific.crystal_chemistry.result._symmetry_context
    source_atoms = {atom.id: atom for atom in document.structure.atomic_view().atoms}
    subsystems = {group.subsystem.representation.representation_id: group.subsystem
                  for group in (*classification.groups, *classification.cation_groups) if group.subsystem is not None}
    subsystem_families = {group.subsystem.representation.representation_id: group.family
                          for group in (*classification.groups, *classification.cation_groups)
                          if group.subsystem is not None}
    rows = document.inorganic_presentation().polyhedron_orbits
    graph = getattr(document.scientific.unit_graph, "result", None)
    faces_by_shell = {unit.source_shell_orbit_id: tuple(tuple(f) for f in unit.representative_geometry.faces)
                      for unit in graph.unit_orbits if unit.source_shell_orbit_id is not None
                      and unit.representative_geometry is not None} if graph is not None else {}
    native_faces = {row.polyhedron_orbit_id: faces_by_shell.get(row.source_shell_id, ()) for row in rows}
    native_rings = {
        (representation_id, ring.ring_orbit_id): ring
        for representation_id, subsystem in subsystems.items()
        for ring in subsystem.rings.ring_orbits
    }
    ring_relations = {}
    ring_constituents = {}
    selected_rings = [option for option in options if option.key in selected and option.kind == "ring"]
    for option in selected_rings:
        subsystem = subsystems[option.representation_id]
        ring = native_rings[(option.representation_id, option.key)]
        ring_relations[option.key] = _ring_display_relation(
            document, ring, subsystem, scene.bounds, context, source_atoms,
        )
        constituent = (_ring_constituents(ring, subsystem, context)
                       if subsystem_families.get(option.representation_id) == "borate" else None)
        if constituent is not None:
            ring_constituents[option.key] = constituent

    # When both levels are selected, show the smaller ring as one exact member
    # of the larger assembly.  It then recolours that member instead of floating
    # as an unrelated equivalent image elsewhere in the cell.
    for parent_option in sorted(selected_rings,
                                key=lambda item: len(_ring_centre_refs(
                                    native_rings[(item.representation_id, item.key)],
                                    subsystems[item.representation_id])), reverse=True):
        constituent = ring_constituents.get(parent_option.key)
        if constituent is None:
            continue
        child, group_relations = constituent
        if child.ring_orbit_id not in selected:
            continue
        subsystem = subsystems[parent_option.representation_id]
        parent_relation = ring_relations[parent_option.key]
        candidates = tuple(parent_relation.compose(item, context) for item in group_relations)
        ring_relations[child.ring_orbit_id] = min(
            candidates,
            key=lambda relation: _ring_relation_score(
                document, child, subsystem, scene.bounds, context, source_atoms, relation,
            ),
        )

    ring_geometry = {}
    for option in options:
        if option.key not in selected or (option.kind != "ring" and not option.ring_id):
            continue
        ring_id = option.ring_id or option.key
        subsystem = subsystems[option.representation_id]
        ring = native_rings[(option.representation_id, ring_id)]
        relation = ring_relations.get(ring_id) or _ring_display_relation(
            document, ring, subsystem, scene.bounds, context, source_atoms,
        )
        composition = ring_constituents.get(ring_id) if option.kind == "ring" else None
        ring_geometry[option.key] = _ring_geometry(
            document, option, subsystem, context=context, atoms=source_atoms,
            bounds=scene.bounds, display_relation=relation, constituents=composition,
        )
    witnesses = {(a.representation_id,a.component_id):a.component_witness
                 for group in (*classification.groups, *classification.cation_groups) for a in group.subtypes
                 if a.component_witness is not None}
    scoped_geometry = dict(ring_geometry)
    for option in options:
        witness = witnesses.get((option.representation_id,option.component_id))
        if option.key in selected and witness is not None:
            scoped_geometry[option.key] = _unit_image_geometry(document, option, subsystems[option.representation_id],
                                                               witness.unit_orbit_refs, context=context, atoms=source_atoms)
    from types import SimpleNamespace
    from cristma.crystal_chemistry import PeriodicUnitOrbitRef
    from cristma.crystallography import PeriodicSymmetryRelation
    boundaries = {b.key:b for group in classification.cation_groups for e in group.environments
                  for b in e.coordination_boundaries}

    def visible_native_geometry(option,representation,allowed_units,priority):
        by_center = {u.representative_geometry.center_atom_ref.atom_id:u for u in representation.unit_orbits
                     if u.unit_orbit_id in allowed_units and u.representative_geometry is not None}
        refs = tuple(PeriodicUnitOrbitRef(by_center[mesh.center_atom_id].unit_orbit_id,
                     PeriodicSymmetryRelation(context.identity_operation_key,mesh.center_translation))
                     for mesh in scene.polyhedra if mesh.center_atom_id in by_center)
        selection = SimpleNamespace(representation=representation,centre_unit_ids=tuple(allowed_units))
        geometry = _unit_image_geometry(document,option,selection,refs,context=context,atoms=source_atoms)
        # Retain selected ring images beyond the cell only when they belong to
        # this exact native component, rather than every copy of the same shell.
        members = set(option.polyhedron_orbit_ids)
        polyhedra = list(geometry.polyhedra)
        for scoped in scoped_geometry.values():
            polyhedra.extend(poly for poly in scoped.polyhedra
                             if poly.unit_orbit_id in allowed_units
                             and (not members or poly.polyhedron_orbit_id in members))
        polyhedra = tuple({(poly.center,poly.polyhedron_orbit_id):poly for poly in polyhedra}.values())
        geometry = replace(geometry,polyhedra=polyhedra,
                           segments=tuple((poly.center,point) for poly in polyhedra for point in poly.points))
        return replace(geometry,priority=priority)

    alternative_geometry = {}
    for option in options:
        if option.key not in selected:
            continue
        if option.boundary_key:
            boundary = boundaries[option.boundary_key]
            allowed = {u.unit_orbit_id for u in boundary.geometry_graph.unit_orbits
                       if u.source_shell_orbit_id == boundary.source_shell_id}
            alternative_geometry[option.key] = visible_native_geometry(option,boundary.geometry_graph,allowed,3)
        elif option.component_id and option.key not in scoped_geometry:
            subsystem = subsystems[option.representation_id]
            provenance = dict(subsystem.representation.provenance)
            if (provenance.get('coordination_boundary')
                    or provenance.get('quotient') == 'translations_with_explicit_site_images'):
                component = next(c for c in subsystem.connectivity.components if c.component_id == option.component_id)
                alternative_geometry[option.key] = visible_native_geometry(option,subsystem.representation,
                    set(component.unit_orbit_ids).intersection(subsystem.centre_unit_ids),
                    0 if option.kind == 'component' else 3 if option.individual else 2)
    layers = []
    for option in options:
        if option.key not in selected:
            continue
        if option.kind == "atom":
            points = {(atom.cartesian, atom.source_site_id) for atom in scene.atoms
                      if atom.source_site_id == option.site_id}
            for geometry in (*scoped_geometry.values(),*alternative_geometry.values()):
                for poly in geometry.polyhedra:
                    if poly.center_site_id == option.site_id:
                        points.add((poly.center, poly.center_site_id))
                    points.update((point, site) for point, site in zip(poly.points, poly.point_site_ids)
                                  if site == option.site_id)
            layers.append(CrystalLayerGeometry(option.key, option.label, 4, (), (), tuple(sorted(points))))
            continue
        if option.key in scoped_geometry:
            layers.append(scoped_geometry[option.key])
            continue
        if option.key in alternative_geometry:
            layers.append(alternative_geometry[option.key])
            continue
        members = set(option.polyhedron_orbit_ids)
        polyhedra, segments = [], []
        for mesh in scene.polyhedra:
            if mesh.polyhedron_orbit_id not in members:
                continue
            center = atoms[(mesh.center_atom_id, mesh.center_translation)].cartesian
            points = tuple(tuple(center[i] + v[i] for i in range(3)) for v in mesh.local_vertices)
            # Native planar BO3 units carry their face in the unit geometry,
            # while the native 3D hull record deliberately has no faces.
            faces = mesh.faces
            if not faces:
                faces = native_faces.get(mesh.polyhedron_orbit_id, ())
            polyhedra.append(LayerPolyhedron(center, points, faces, mesh.polyhedron_orbit_id,
                                             atoms[(mesh.center_atom_id, mesh.center_translation)].source_site_id,
                                             mesh.vertex_source_site_ids))
        # Selected witnesses may cross the display boundary. Keep their actual
        # native polyhedra in the parent context, so colour changes mark the
        # same objects rather than producing detached pieces of illustration.
        model_key = dict(subsystems[option.representation_id].representation.provenance).get('coordination_boundary') if option.representation_id else None
        for context_key,geometry in scoped_geometry.items():
            context_option = next(o for o in options if o.key == context_key)
            context_model = dict(subsystems[context_option.representation_id].representation.provenance).get('coordination_boundary')
            if context_model != model_key:
                continue
            polyhedra.extend(poly for poly in geometry.polyhedra if poly.polyhedron_orbit_id in members)
        polyhedra = list({(poly.center, poly.polyhedron_orbit_id): poly for poly in polyhedra}.values())
        segments.extend((poly.center, vertex) for poly in polyhedra for vertex in poly.points)
        layers.append(CrystalLayerGeometry(
            option.key, option.label, 0 if option.kind in {"component", 'coordination_set'} else 3 if option.individual else 2,
            tuple(segments), tuple(polyhedra),
        ))
    return tuple(layers)
