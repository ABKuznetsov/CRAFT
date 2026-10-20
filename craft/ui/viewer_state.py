"""Transfer declared presentation state across the widget boundary."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import fields

from craft.analysis.hierarchy import HierarchyLevel
from craft.analysis.structural_motifs import RING_SCOPE_COLORS
from craft.core.visualization import VISIBILITY_FIELDS, VisualizationState, copy_visual_value


# These fields govern document workflows, not the renderer's current image.
_DOCUMENT_FIELDS = frozenset({
    "organic_active_view", "organic_active_object_id",
    "organic_view_user_selected", "contact_defaults_applied",
})
_VIEWER_FIELDS = tuple(item.name for item in fields(VisualizationState) if item.name not in _DOCUMENT_FIELDS)
_RENDER_OPTIONS = (
    "show_atoms", "show_bonds", "show_polyhedra", "show_cell", "show_axes",
    "show_legend", "show_labels", "color_by", "render_style", "polyhedron_opacity",
    "radius_model", "atom_scale", "bond_radius", "bond_style", "show_centers",
    "show_polyhedron_edges", "show_polyhedron_spokes", "polyhedron_edge_radius",
    "show_periodic_cell_grid", "show_cell_dimensions", "cell_line_width", "axes_size", "legend_scale",
    "split_mixed_occupancies", "show_vacancy_sectors", "show_connectors", "show_connector_labels",
    "axes_position", "legend_position",
)


def _freeze(value):
    if isinstance(value, dict):
        return ("mapping", tuple((key, _freeze(item)) for key, item in sorted(value.items(), key=lambda pair: repr(pair[0]))))
    if isinstance(value, set):
        return ("set", frozenset(value))
    return value


def _thaw(value):
    if isinstance(value, tuple) and len(value) == 2:
        if value[0] == "mapping":
            return {key: _thaw(item) for key, item in value[1]}
        if value[0] == "set":
            return set(value[1])
    return value


def frozen_viewer_state(viewer):
    """Detached, hashable presentation recipe; contains no geometry or widgets."""
    return tuple((name, _freeze(value)) for name, value in snapshot_viewer_state(viewer).items())


def restore_frozen_viewer_state(viewer, state):
    restore_viewer_state(viewer, {name: _thaw(value) for name, value in state})


def apply_viewer_state(viewer: object, state: VisualizationState) -> None:
    """Install a detached display copy; temporary edits must not change a document."""
    for name in _VIEWER_FIELDS:
        setattr(viewer, name, copy_visual_value(getattr(state, name)))
    setattr(viewer, "level", HierarchyLevel(state.level))
    setattr(viewer, "ring_scope_colors", {**RING_SCOPE_COLORS, **state.ring_scope_colors})


def read_viewer_state(viewer: object) -> VisualizationState:
    """Capture display state, supplying defaults for reduced renderer adapters."""
    state = VisualizationState()
    for name in _VIEWER_FIELDS:
        setattr(state, name, copy_visual_value(getattr(viewer, name, getattr(state, name))))
    state.level = HierarchyLevel(state.level)
    return state


def reset_viewer_visibility(viewer: object) -> None:
    for name in VISIBILITY_FIELDS:
        value = getattr(viewer, name, None)
        if value is not None:
            value.clear()


def clear_viewer_document(viewer: object) -> None:
    """Release document geometry and presentation while keeping render preferences."""
    for name in ("_document", "structure", "scene", "hierarchy", "native_scene",
                 "native_presentation", "ring_motifs", "selected_scene_object",
                 "selected_polyhedron_id", "comparison_highlight", "edit_target_kind"):
        setattr(viewer, name, None)
    for name in ("_polyhedron_surface_cache", "_unit_geometry_surface_cache"):
        cache = getattr(viewer, name, None)
        if cache is not None:
            cache.clear()
    apply_viewer_state(viewer, VisualizationState())
    viewer.redraw()


def snapshot_viewer_state(viewer: object) -> dict[str, object]:
    """Save presentation and render options before producing a report image."""
    return {
        name: deepcopy(getattr(viewer, name))
        for name in (*_VIEWER_FIELDS, *_RENDER_OPTIONS)
        if hasattr(viewer, name)
    }


def restore_viewer_state(viewer: object, snapshot: Mapping[str, object]) -> None:
    for name, value in snapshot.items():
        setattr(viewer, name, value)
