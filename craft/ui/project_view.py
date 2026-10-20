"""Restore project view controls without triggering selection or analysis actions."""

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QAbstractButton, QComboBox


_CONTROLS = (
    "render_style_combo", "radius_combo", "color_combo", "bond_style_combo",
    "cell_check", "periodic_grid_check", "axes_check", "cell_dimensions_check",
    "labels_check", "boundary_atoms_check", "split_occupancy_check", "vacancy_sector_check",
    "poly_edges_check", "spokes_check", "pivot_labels_check", "legend_check",
    "cell_line_slider", "axes_size_slider", "legend_scale_slider", "atom_scale", "bond_radius_slider",
    "poly_opacity", "poly_edge_slider",
)


def _controls(window):
    result = {name: getattr(window, name) for name in _CONTROLS if hasattr(window, name)}
    result.update({f"show:{key}": widget for key, widget in window.show_checks.items()})
    for axis, (minimum, maximum) in enumerate(zip(window.cell_min_spins, window.cell_max_spins)):
        result[f"min:{axis}"] = minimum
        result[f"max:{axis}"] = maximum
    return result


def capture_project_view(window):
    controls = {}
    for name, widget in _controls(window).items():
        if isinstance(widget, QAbstractButton):
            controls[name] = widget.isChecked()
        elif isinstance(widget, QComboBox):
            controls[name] = widget.currentText()
        else:
            controls[name] = widget.value()
    viewer = getattr(window, "viewer", None)
    camera = getattr(getattr(viewer, "plotter", None), "camera", None)
    result = {"controls": controls}
    if viewer is not None:
        result["layout"] = {name: getattr(viewer, name, None)
                            for name in ("axes_position", "legend_position")}
    if camera is not None:
        result["camera"] = {
            "position": list(camera.position), "focal_point": list(camera.focal_point),
            "up": list(camera.up), "parallel_projection": camera.parallel_projection,
            "parallel_scale": camera.parallel_scale, "view_angle": camera.view_angle,
        }
    return result


def restore_project_controls(window, settings):
    viewer = getattr(window, "viewer", None)
    if viewer is not None:
        for name in ("axes_position", "legend_position"):
            value = settings.get("layout", {}).get(name)
            setattr(viewer, name, tuple(value) if value is not None else None)
    available = _controls(window)
    for name, value in settings.get("controls", {}).items():
        widget = available.get(name)
        if widget is None:
            continue
        with QSignalBlocker(widget):
            if isinstance(widget, QAbstractButton):
                widget.setChecked(value)
            elif isinstance(widget, QComboBox):
                index = widget.findText(value)
                if index >= 0:
                    widget.setCurrentIndex(index)
            else:
                widget.setValue(value)


def restore_project_camera(window, settings):
    saved = settings.get("camera")
    if saved is None:
        return
    camera = window.viewer.plotter.camera
    for name in ("position", "focal_point", "up", "parallel_projection", "parallel_scale", "view_angle"):
        if name in saved:
            setattr(camera, name, saved[name])
    window.viewer.plotter.reset_camera_clipping_range()
    window.viewer.plotter.render()
