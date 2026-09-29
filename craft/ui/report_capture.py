"""Capture a CRAFT scene as a semantic report figure.

The PNG is only a preview.  The manifest is the durable source: it records
stable scientific object references plus the presentation state needed to
recreate the view later.
"""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

import numpy as np

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
    native = _native_presentation(document)
    if native is not None:
        refs: list[str] = []
        if viewer.show_atoms:
            hidden_orbits = getattr(viewer, "hidden_atom_orbit_ids", set())
            auto_hidden = set().union(
                *getattr(viewer, "block_auto_hidden_atom_ids", {}).values()
            ) if getattr(viewer, "block_auto_hidden_atom_ids", {}) else set()
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
            auto_hidden = getattr(
                viewer, "block_auto_hidden_polyhedron_orbit_ids", {}
            )
            for values in auto_hidden.values():
                hidden_polyhedra.update(values)
            refs.extend(
                f"polyhedron-orbit:{row.polyhedron_orbit_id}"
                for row in native.polyhedron_orbits
                if row.polyhedron_orbit_id not in hidden_polyhedra
            )
        refs.extend(f"ring:{identifier}" for identifier in sorted(viewer.shown_ring_ids))
        refs.extend(f"block:{identifier}" for identifier in sorted(viewer.shown_block_ids))
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


def _selected_ref(document, viewer) -> tuple[str, ...]:
    selected = getattr(viewer, "selected_scene_object", None)
    if selected is None:
        return ()
    kind, identifier = selected
    if _native_presentation(document) is not None:
        prefix = {
            "atom": "atom-orbit",
            "bond": "contact-orbit",
            "contact": "contact-orbit",
            "polyhedron": "polyhedron-orbit",
            "unit": "unit",
            "ring": "ring",
            "block": "block",
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


def current_scene_manifest(document, viewer, *, label_mode: LabelMode) -> SceneManifest:
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
    return SceneManifest(
        document_id=str(document.id),
        structure_fingerprint=str(document.canonical_structure_identity()),
        content_identity=str(document.content_identity()),
        representation=str(level),
        camera=_camera_record(viewer.camera_state()),
        visible_object_refs=visible,
        selected_object_refs=_selected_ref(document, viewer),
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
    )


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
    attribute_names = (
        "show_atoms",
        "show_bonds",
        "show_polyhedra",
        "show_cell",
        "show_axes",
        "show_legend",
        "show_labels",
        "color_by",
        "render_style",
        "polyhedron_opacity",
        "hidden_atom_indices",
        "hidden_atom_orbit_ids",
        "hidden_atom_instance_keys",
        "hidden_contact_orbit_ids",
        "hidden_polyhedron_ids",
        "hidden_polyhedron_orbit_ids",
        "block_auto_hidden_atom_ids",
        "block_auto_hidden_polyhedron_orbit_ids",
        "shown_unit_ids",
        "shown_ring_ids",
        "shown_block_ids",
    )
    previous = {
        name: deepcopy(getattr(viewer, name))
        for name in attribute_names
        if hasattr(viewer, name)
    }
    previous_camera = viewer.camera_state()
    visible = set(manifest.visible_object_refs)
    try:
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
        for name, value in previous.items():
            setattr(viewer, name, value)
        viewer.redraw(reset_camera=False)
        viewer.apply_camera_state(previous_camera)
