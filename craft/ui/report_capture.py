"""Capture a CRAFT scene as a semantic report figure.

The PNG is only a preview.  The manifest is the durable source: it records
stable scientific object references plus the presentation state needed to
recreate the view later.
"""

from __future__ import annotations

from uuid import uuid4

import numpy as np

from craft.analysis.hierarchy import HierarchyLevel
from craft.ui.viewer_state import (
    snapshot_viewer_state, restore_viewer_state, frozen_viewer_state,
    restore_frozen_viewer_state, read_viewer_state,
)

from craft.analysis.reporting import (
    CameraStateRecord,
    FigureKind,
    LabelMode,
    ReportFigure,
    SceneManifest,
)
from craft.core.site_orbits import (
    polyhedron_orbits,
    site_orbit_key,
    site_orbits,
)
from craft.presentation.organic_scene import OrganicSceneData


def _organic_scene(viewer):
    scene = getattr(viewer, "native_scene", None)
    return scene if isinstance(scene, OrganicSceneData) else None


def _native_presentation(document):
    scientific = getattr(document, "scientific", None)
    if scientific is None or getattr(scientific, "crystal_chemistry", None) is None:
        return None
    return document.inorganic_presentation()


def _camera_record(state) -> CameraStateRecord:
    return CameraStateRecord(
        position=tuple(state.position),
        focal_offset=tuple(state.focal_offset),
        view_up=tuple(state.view_up),
        parallel_scale=float(state.parallel_scale),
        view_angle=float(state.view_angle),
        parallel_projection=bool(state.parallel_projection),
    )


def _available_refs(document) -> set[str]:
    native = _native_presentation(document)
    if native is not None:
        refs = {
            f"atom-orbit:{row.source_site_id}" for row in native.atom_orbits
        }
        refs.update(
            f"contact-orbit:{row.contact_orbit_id}" for row in native.contact_orbits
        )
        refs.update(
            f"polyhedron-orbit:{row.polyhedron_orbit_id}"
            for row in native.polyhedron_orbits
        )
        refs.update(f"ring:{row.ring_orbit_id}" for row in native.rings)
        refs.update(f"block:{row.block_id}" for row in native.structural_blocks)
        from craft.presentation.crystal_layers import layer_options
        refs.update(f"crystal-layer:{row.key}" for row in layer_options(document))
        return refs
    refs = {
        f"atom-orbit:{orbit_id}"
        for orbit_id in site_orbits(document.legacy_projection)
    }
    presentation = getattr(document, "contact_presentation", None)
    refs.update(
        f"contact-orbit:{row.contact_orbit_id}"
        for row in getattr(presentation, "rows", ())
    )
    refs.update(
        f"polyhedron-orbit:{orbit_id}"
        for orbit_id in polyhedron_orbits(document)
    )
    hierarchy = document.hierarchy
    refs.update(f"unit:{item.id}" for item in hierarchy.structural_units)
    refs.update(f"ring:{item.id}" for item in getattr(hierarchy, "rings", ()))
    refs.update(f"block:{item.id}" for item in hierarchy.blocks)
    return refs


def _visible_refs(document, viewer) -> tuple[str, ...]:
    organic = _organic_scene(viewer)
    if organic is not None:
        hidden = getattr(viewer, "hidden_atom_orbit_ids", set())
        hidden_instances = getattr(viewer, "hidden_atom_instance_keys", set())
        atoms = tuple(a for a in organic.atoms if a.source_site_id not in hidden
                      and (a.atom_id, a.cell_translation) not in hidden_instances)
        keys = {(a.atom_id, a.cell_translation) for a in atoms}
        refs = []
        if viewer.show_atoms:
            refs.extend(f"atom-orbit:{a.source_site_id}" for a in atoms)
        if viewer.show_bonds:
            refs.extend(f"contact-orbit:{bond.contact_orbit_id}" for bond in organic.covalent_bonds
                        if bond.contact_orbit_id not in viewer.hidden_contact_orbit_ids
                        and (bond.first_atom_id, bond.first_translation) in keys
                        and (bond.second_atom_id, bond.second_translation) in keys)
            refs.extend(f"contact-orbit:{contact.contact_orbit_id}" for contact in organic.intermolecular_contacts
                        if contact.contact_orbit_id not in viewer.hidden_contact_orbit_ids)
        if viewer.show_atoms or viewer.show_bonds:
            refs.extend(f"molecule-orbit:{m.molecule_orbit_id}" for m in organic.molecule_instances
                        if any(key in keys for key in m.atom_keys))
        refs.extend(f"net-vertex:{node.vertex_orbit_id}" for node in organic.net_nodes)
        refs.extend(f"net-edge:{edge.edge_orbit_id}" for edge in organic.net_edges)
        return tuple(dict.fromkeys(refs))
    native = _native_presentation(document)
    if native is not None:
        refs: list[str] = []
        hidden_blocks = getattr(viewer, "hidden_block_ids", set())
        if viewer.show_atoms:
            from craft.presentation.block_state import auto_hidden_members
            hidden_orbits = getattr(viewer, "hidden_atom_orbit_ids", set())
            auto_hidden = auto_hidden_members(viewer, "block_auto_hidden_atom_ids")
            refs.extend(
                f"atom-orbit:{row.source_site_id}"
                for row in native.atom_orbits
                if row.source_site_id not in hidden_orbits
                and any(atom_id not in auto_hidden for atom_id in row.atom_ids)
            )
        if viewer.show_bonds:
            hidden_contacts = getattr(viewer, "hidden_contact_orbit_ids", set())
            refs.extend(
                f"contact-orbit:{row.contact_orbit_id}"
                for row in native.contact_orbits
                if row.contact_orbit_id not in hidden_contacts
            )
        if viewer.show_polyhedra:
            hidden_polyhedra = set(getattr(viewer, "hidden_polyhedron_orbit_ids", set()))
            from craft.presentation.block_state import auto_hidden_members
            hidden_polyhedra.update(auto_hidden_members(viewer, "block_auto_hidden_polyhedron_orbit_ids"))
            refs.extend(
                f"polyhedron-orbit:{row.polyhedron_orbit_id}"
                for row in native.polyhedron_orbits
                if row.polyhedron_orbit_id not in hidden_polyhedra
            )
        refs.extend(f"ring:{identifier}" for identifier in sorted(viewer.shown_ring_ids))
        refs.extend(f"block:{identifier}" for identifier in sorted(viewer.shown_block_ids - hidden_blocks))
        scene = getattr(viewer, "native_scene", None)
        if scene is not None:
            from craft.presentation.inorganic_scene import visible_atoms, visible_polyhedra
            from craft.ui.viewer import _native_layer_plan
            plan = _native_layer_plan(viewer)
            styles = getattr(viewer, "crystal_layers", {})
            layer_mode = bool(getattr(viewer, "crystal_layers_enabled", False) and any(
                layer.key in styles and styles[layer.key].visible for layer in scene.crystal_layers))
            atoms = visible_atoms(scene, viewer, include_auto_hidden=plan.blocks and not layer_mode)
            atom_keys = {(a.atom_id, a.cell_translation) for a in atoms}
            refs = []
            if plan.atoms:
                refs.extend(f"atom-orbit:{a.source_site_id}" for a in atoms)
            if plan.contacts:
                refs.extend(f"contact-orbit:{c.contact_orbit_id}" for c in scene.contacts
                            if c.contact_orbit_id not in viewer.hidden_contact_orbit_ids
                            and (c.first_atom_id, c.first_translation) in atom_keys
                            and (c.second_atom_id, c.second_translation) in atom_keys)
            if plan.polyhedra:
                refs.extend(f"polyhedron-orbit:{p.polyhedron_orbit_id}"
                            for p in visible_polyhedra(scene, viewer, include_auto_hidden=plan.blocks and not layer_mode))
            if plan.blocks:
                refs.extend(f"ring:{key}" for key in sorted(viewer.shown_ring_ids))
                refs.extend(f"block:{key}" for key in sorted(viewer.shown_block_ids - hidden_blocks))
            if layer_mode:
                from craft.presentation.crystal_layers import layer_member_hidden
                styles = getattr(viewer, "crystal_layers", {})
                for layer in scene.crystal_layers:
                    style = styles.get(layer.key)
                    if style is None or not style.visible:
                        continue
                    polyhedra = tuple(p for p in layer.polyhedra
                                      if p.polyhedron_orbit_id not in viewer.hidden_polyhedron_orbit_ids
                                      and not layer_member_hidden(layer, style, p))
                    if (polyhedra or any(site not in viewer.hidden_atom_orbit_ids for _, site in layer.atoms)
                            or style.representation == "lines" and layer.segments):
                        refs.append(f"crystal-layer:{layer.key}")
        return tuple(dict.fromkeys(refs))
    refs: list[str] = []
    structure = document.legacy_projection
    if viewer.show_atoms:
        for orbit_id, indices in site_orbits(structure).items():
            if any(index not in viewer.hidden_atom_indices for index in indices):
                refs.append(f"atom-orbit:{orbit_id}")

    presentation = getattr(document, "contact_presentation", None)
    if viewer.show_bonds:
        refs.extend(
            f"contact-orbit:{row.contact_orbit_id}"
            for row in getattr(presentation, "rows", ())
            if row.contact_orbit_id not in viewer.hidden_contact_orbit_ids
        )

    if viewer.show_polyhedra:
        hidden = viewer.hidden_polyhedron_ids
        refs.extend(
            f"polyhedron-orbit:{orbit_id}"
            for orbit_id, identifiers in polyhedron_orbits(document).items()
            if any(identifier not in hidden for identifier in identifiers)
        )

    refs.extend(f"unit:{identifier}" for identifier in sorted(viewer.shown_unit_ids))
    refs.extend(f"ring:{identifier}" for identifier in sorted(viewer.shown_ring_ids))
    refs.extend(f"block:{identifier}" for identifier in sorted(viewer.shown_block_ids))
    return tuple(dict.fromkeys(refs))


def _selected_ref(document, viewer, selected=None) -> tuple[str, ...]:
    selected = selected if selected is not None else getattr(viewer, "selected_scene_object", None)
    if selected is None:
        return ()
    kind, identifier = selected
    if _organic_scene(viewer) is not None:
        ref = (f"atom-orbit:{identifier}" if kind == "atom" else
               f"contact-orbit:{identifier}" if kind in {"bond", "contact"} else "")
        return (ref,) if ref in _visible_refs(document, viewer) else ()
    if _native_presentation(document) is not None:
        if kind == "crystal_layer_group":
            available = _available_refs(document)
            return tuple(f"crystal-layer:{key}" for key in identifier if f"crystal-layer:{key}" in available)
        prefix = {
            "atom": "atom-orbit",
            "bond": "contact-orbit",
            "contact": "contact-orbit",
            "polyhedron": "polyhedron-orbit",
            "unit": "unit",
            "ring": "ring",
            "block": "block",
            "crystal_layer": "crystal-layer",
        }.get(kind)
        ref = f"{prefix}:{identifier}" if prefix is not None else ""
        return (ref,) if ref in _available_refs(document) else ()
    ref = ""
    if kind == "atom":
        try:
            label = document.legacy_projection.sites[int(identifier)].label
        except (IndexError, TypeError, ValueError):
            return ()
        ref = f"atom-orbit:{site_orbit_key(label)}"
    elif kind == "polyhedron":
        ref = next(
            (
                f"polyhedron-orbit:{orbit_id}"
                for orbit_id, identifiers in polyhedron_orbits(document).items()
                if str(identifier) in identifiers
            ),
            "",
        )
    elif kind in {"bond", "contact"}:
        ref = f"contact-orbit:{identifier}"
    elif kind in {"unit", "ring", "block"}:
        ref = f"{kind}:{identifier}"
    return (ref,) if ref and ref in _available_refs(document) else ()


def current_scene_manifest(document, viewer, *, label_mode: LabelMode, selected_object=None) -> SceneManifest:
    """Describe the current scene without redrawing or mutating it."""
    visible = _visible_refs(document, viewer)
    label_prefix = (
        "atom-orbit:"
        if label_mode is LabelMode.ATOM_ORBITS
        else "polyhedron-orbit:"
    )
    labelled = (
        tuple(ref for ref in visible if ref.startswith(label_prefix))
        if viewer.show_labels
        else ()
    )
    level = getattr(viewer.level, "value", viewer.level)
    scene = getattr(viewer, "native_scene", None)
    organic = _organic_scene(viewer)
    scene_key = next((key for key, value in getattr(document, "scene_cache", {}).items()
                      if value is scene and key[0] == "native-inorganic"), None)
    return SceneManifest(
        document_id=str(document.id),
        structure_fingerprint=str(document.canonical_structure_identity()),
        content_identity=str(document.content_identity()),
        representation=str(level),
        camera=_camera_record(viewer.camera_state()),
        visible_object_refs=visible,
        selected_object_refs=_selected_ref(document, viewer, selected_object),
        labelled_orbit_refs=labelled,
        label_mode=label_mode,
        show_cell=bool(viewer.show_cell),
        show_axes=bool(viewer.show_axes),
        show_legend=bool(viewer.show_legend),
        visual_settings=(
            ("color_by", str(viewer.color_by)),
            ("render_style", str(viewer.render_style)),
            ("polyhedron_opacity", float(viewer.polyhedron_opacity)),
            ("show_atoms", bool(viewer.show_atoms)),
            ("show_bonds", bool(viewer.show_bonds)),
            ("show_polyhedra", bool(viewer.show_polyhedra)),
        ),
        visual_state=frozen_viewer_state(viewer),
        scene_bounds=tuple(getattr(getattr(viewer, "native_scene", None), "bounds", ())),
        scene_settings=(("include_contacts", scene_key[2]), ("complete_boundary", scene_key[3]),
                        ("include_expanded_grid", scene_key[4])) if scene_key is not None else (),
        scene_kind="organic:" + organic.mode.value if organic is not None else "structure",
        scene_object_ref=str(document.visual.organic_active_object_id or "") if organic is not None else "",
    )


def capture_automatic_report_figure(document, viewer, *, selected_object=None) -> ReportFigure:
    from craft.analysis.reporting.figure_description import describe_view

    polyhedra = viewer.show_polyhedra
    if getattr(viewer, "native_scene", None) is not None:
        from craft.ui.viewer import _native_layer_plan
        polyhedra = _native_layer_plan(viewer).polyhedra
    if _organic_scene(viewer) is not None:
        polyhedra = False
    manifest = current_scene_manifest(document, viewer, label_mode=(
        LabelMode.POLYHEDRON_ORBITS if polyhedra else LabelMode.ATOM_ORBITS
    ), selected_object=selected_object)
    title, caption, narrative = describe_view(document, manifest)
    return ReportFigure(
        id=f"figure-{uuid4().hex}", kind=FigureKind.USER_SNAPSHOT,
        title=title, caption=caption, recommendation_reason="",
        manifest=manifest, preview_png=viewer.screenshot_bytes(), narrative=narrative,
        description=" ".join(narrative.statements),
    )


def capture_morphology_report_figure(document, workspace) -> ReportFigure:
    """Capture the active facet view and its already calculated model facts."""
    from hashlib import sha256
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from craft.analysis.reporting.composer import FigureNarrative

    model = workspace.current_model
    camera = workspace.viewer.plotter.camera
    calculation = getattr(workspace, "current_calculation", None)
    aggregate = getattr(calculation, "twin_aggregate", None)
    facets = model.facets if aggregate is None else aggregate.external_facets
    planes = tuple((plane.family.hkl, plane.family.equivalents, float(plane.rho), plane.enabled, plane.manual)
                   for plane in model.planes)
    geometry = tuple((facet.family_hkl, tuple(tuple(point) for point in facet.vertices)) for facet in facets)
    model_id = sha256(repr((planes, geometry)).encode()).hexdigest()
    refs = (f"morphology-model:{model_id}",)
    families = tuple(dict.fromkeys(facet.family_hkl for facet in facets))
    manual = any(plane.manual for plane in model.planes)
    title = "Manually adjusted morphology model" if manual else "BFDH geometric morphology model"
    text = ("The BFDH geometric morphology model is shown"
            + (" with manual adjustments" if manual else "")
            + f"; number of displayed faces: {len(facets)}. "
            + "Displayed forms: " + ", ".join("{" + " ".join(map(str, hkl)) + "}" for hkl in families) + ".")
    if aggregate is not None:
        text += " A model twin aggregate is shown."
    text += " This geometric model does not establish an equilibrium growth shape or cleavage."
    manifest = SceneManifest(document.id, document.canonical_structure_identity(), document.content_identity(),
        "morphology", CameraStateRecord(tuple(camera.position), tuple(camera.focal_point), tuple(camera.up),
             float(camera.parallel_scale), float(camera.view_angle), bool(camera.parallel_projection)),
        refs, (), (), LabelMode.POLYHEDRON_ORBITS, False, True, True,
        visual_state=(("morphology_planes", planes), ("morphology_geometry", geometry),
                      ("morphology_colors", tuple(sorted(getattr(calculation, "color_by_family", {}).items())))))
    with TemporaryDirectory(prefix="craft-report-morphology-") as folder:
        path = Path(folder) / "preview.png"
        workspace.viewer.export_png(path)
        png = path.read_bytes()
    return ReportFigure(f"figure-{uuid4().hex}", FigureKind.USER_SNAPSHOT, title, title + ".", "", manifest, png,
        narrative=FigureNarrative("morphology", refs, (text,), ("crystal_data",)), description=text)


def capture_report_figure(
    document,
    viewer,
    *,
    kind: FigureKind,
    title: str,
    caption: str,
    recommendation_reason: str = "",
    label_mode: LabelMode | None = None,
) -> ReportFigure:
    """Capture the current viewport and its semantic reconstruction recipe."""
    if label_mode is None:
        level = str(getattr(viewer.level, "value", viewer.level)).lower()
        label_mode = (
            LabelMode.POLYHEDRON_ORBITS
            if "polyhed" in level
            else LabelMode.ATOM_ORBITS
        )
    return ReportFigure(
        id=f"figure-{uuid4().hex}",
        kind=kind,
        title=str(title),
        caption=str(caption),
        recommendation_reason=str(recommendation_reason),
        manifest=current_scene_manifest(document, viewer, label_mode=label_mode),
        preview_png=viewer.screenshot_bytes(),
    )


def _normalized(vector: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(vector))
    if length <= 1e-12:
        raise ValueError("Cannot define a camera from a zero crystallographic axis.")
    return vector / length


def standard_overview_manifest(
    document,
    *,
    label_mode: LabelMode,
) -> SceneManifest:
    """Build the canonical overview recipe without changing coordinates."""
    native = _native_presentation(document)
    structure = document.structure if native is not None else document.legacy_projection
    basis = np.asarray(structure.cell.matrix, dtype=float)
    look = _normalized(np.sum(basis, axis=0))
    view_up = None
    for candidate in (basis[2], basis[1], basis[0]):
        projected = candidate - float(np.dot(candidate, look)) * look
        if float(np.linalg.norm(projected)) > 1e-10:
            view_up = _normalized(projected)
            break
    if view_up is None:  # A valid 3D cell should never reach this branch.
        view_up = np.array((0.0, 0.0, 1.0))

    if native is not None:
        atom_refs = tuple(
            f"atom-orbit:{row.source_site_id}" for row in native.atom_orbits
        )
        polyhedron_refs = tuple(
            f"polyhedron-orbit:{row.polyhedron_orbit_id}"
            for row in native.polyhedron_orbits
        )
    else:
        atom_refs = tuple(
            f"atom-orbit:{orbit_id}" for orbit_id in site_orbits(structure)
        )
        polyhedron_refs = tuple(
            f"polyhedron-orbit:{orbit_id}"
            for orbit_id in polyhedron_orbits(document)
        )
    diagnostics: tuple[str, ...] = ()
    if label_mode is LabelMode.POLYHEDRON_ORBITS and polyhedron_refs:
        visible = polyhedron_refs
    else:
        visible = atom_refs
        if label_mode is LabelMode.POLYHEDRON_ORBITS:
            label_mode = LabelMode.ATOM_ORBITS
            diagnostics = ("report.overview.polyhedra_unavailable",)

    extent = max(float(np.linalg.norm(axis)) for axis in basis)
    return SceneManifest(
        document_id=str(document.id),
        structure_fingerprint=str(document.canonical_structure_identity()),
        content_identity=str(document.content_identity()),
        representation=(
            "polyhedra"
            if label_mode is LabelMode.POLYHEDRON_ORBITS
            else "sites"
        ),
        camera=CameraStateRecord(
            position=tuple(float(value) for value in look * extent * 3.0),
            focal_offset=(0.0, 0.0, 0.0),
            view_up=tuple(float(value) for value in view_up),
            parallel_scale=extent,
            view_angle=30.0,
            parallel_projection=True,
        ),
        visible_object_refs=visible,
        selected_object_refs=(),
        labelled_orbit_refs=visible,
        label_mode=label_mode,
        show_cell=True,
        show_axes=True,
        show_legend=True,
        visual_settings=(
            ("render_style", "publication"),
            ("show_atoms", label_mode is LabelMode.ATOM_ORBITS),
            ("show_bonds", label_mode is LabelMode.ATOM_ORBITS),
            ("show_polyhedra", label_mode is LabelMode.POLYHEDRON_ORBITS),
        ),
        diagnostics=diagnostics,
    )


def _camera_state_from_record(record: CameraStateRecord):
    # Import here keeps the report model independent from Qt/VTK.
    from craft.ui.viewer import CameraState

    return CameraState(
        position=record.position,
        focal_offset=record.focal_offset,
        view_up=record.view_up,
        parallel_scale=record.parallel_scale,
        view_angle=record.view_angle,
        parallel_projection=record.parallel_projection,
    )


def render_manifest_preview(document, viewer, manifest: SceneManifest) -> bytes:
    """Temporarily render a manifest and restore the live scene in ``finally``."""
    previous = snapshot_viewer_state(viewer)
    previous_camera = viewer.camera_state()
    previous_scene = getattr(viewer, "native_scene", None)
    visible = set(manifest.visible_object_refs)
    try:
        if manifest.visual_state:
            if manifest.representation == "morphology":
                raise ValueError("A morphology view requires the morphology workspace; its saved PNG remains available in the report.")
            restore_frozen_viewer_state(viewer, manifest.visual_state)
            if manifest.scene_kind.startswith("organic:"):
                from craft.presentation.organic_scene import build_organic_scene, OrganicSceneMode
                viewer.native_scene = build_organic_scene(document,
                    OrganicSceneMode(manifest.scene_kind.split(":", 1)[1]),
                    selected_object_id=manifest.scene_object_ref or None)
            elif manifest.scene_bounds:
                from copy import copy
                detached = copy(document)
                detached.visual = read_viewer_state(viewer)
                detached.scene_cache = {}
                viewer.native_scene = detached.inorganic_scene_data(manifest.scene_bounds,
                    **(dict(manifest.scene_settings) or {"include_expanded_grid": getattr(viewer, "show_periodic_cell_grid", False)}))
            viewer.redraw(reset_camera=False)
            viewer.apply_camera_state(_camera_state_from_record(manifest.camera))
            return viewer.screenshot_bytes()
        viewer.level = HierarchyLevel(manifest.representation)
        viewer.show_cell = manifest.show_cell
        viewer.show_axes = manifest.show_axes
        viewer.show_legend = manifest.show_legend
        viewer.show_labels = bool(manifest.labelled_orbit_refs)
        for name, value in manifest.visual_settings:
            if hasattr(viewer, name):
                setattr(viewer, name, value)

        native = _native_presentation(document)
        if native is not None:
            viewer.hidden_atom_orbit_ids = {
                row.source_site_id
                for row in native.atom_orbits
                if f"atom-orbit:{row.source_site_id}" not in visible
            }
            viewer.hidden_atom_instance_keys = set()
            viewer.hidden_contact_orbit_ids = {
                row.contact_orbit_id
                for row in native.contact_orbits
                if f"contact-orbit:{row.contact_orbit_id}" not in visible
            }
            viewer.hidden_polyhedron_orbit_ids = {
                row.polyhedron_orbit_id
                for row in native.polyhedron_orbits
                if f"polyhedron-orbit:{row.polyhedron_orbit_id}" not in visible
            }
            viewer.hidden_polyhedron_ids = set()
        else:
            atom_groups = site_orbits(document.legacy_projection)
            viewer.hidden_atom_indices = {
                index
                for orbit_id, indices in atom_groups.items()
                if f"atom-orbit:{orbit_id}" not in visible
                for index in indices
            }
            presentation = getattr(document, "contact_presentation", None)
            viewer.hidden_contact_orbit_ids = {
                row.contact_orbit_id
                for row in getattr(presentation, "rows", ())
                if f"contact-orbit:{row.contact_orbit_id}" not in visible
            }
            viewer.hidden_polyhedron_ids = {
                identifier
                for orbit_id, identifiers in polyhedron_orbits(document).items()
                if f"polyhedron-orbit:{orbit_id}" not in visible
                for identifier in identifiers
            }
        viewer.shown_unit_ids = {
            ref.removeprefix("unit:") for ref in visible if ref.startswith("unit:")
        }
        viewer.shown_ring_ids = {
            ref.removeprefix("ring:") for ref in visible if ref.startswith("ring:")
        }
        viewer.shown_block_ids = {
            ref.removeprefix("block:") for ref in visible if ref.startswith("block:")
        }
        if native is not None:
            shown_blocks = {
                row.block_id: row
                for row in native.structural_blocks
                if row.block_id in viewer.shown_block_ids
            }
            viewer.block_auto_hidden_atom_ids = {
                block_id: row.internal_atom_ids
                for block_id, row in shown_blocks.items()
            }
            viewer.block_auto_hidden_polyhedron_orbit_ids = {
                block_id: frozenset(row.polyhedron_orbit_ids)
                for block_id, row in shown_blocks.items()
            }
        viewer.redraw(reset_camera=False)
        viewer.apply_camera_state(_camera_state_from_record(manifest.camera))
        return viewer.screenshot_bytes()
    finally:
        if hasattr(viewer, "native_scene"):
            viewer.native_scene = previous_scene
        restore_viewer_state(viewer, previous)
        viewer.redraw(reset_camera=False)
        viewer.apply_camera_state(previous_camera)
