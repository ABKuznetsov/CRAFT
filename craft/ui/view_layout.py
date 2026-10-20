"""Mouse composition of a view, without changing crystal coordinates."""

import numpy as np
from PySide6.QtCore import QEvent, Qt

from craft.ui.legend import compass_viewport


def pan_camera(plotter, dx, dy):
    """Translate camera and focal point by a logical Qt pixel displacement."""
    camera = plotter.camera
    direction = np.asarray(camera.direction)
    right = np.cross(direction, camera.up)
    norm = np.linalg.norm(right)
    if norm < 1e-12:
        return
    right /= norm
    up = np.cross(right, direction)
    aspect = max(1, plotter.width()) / max(1, plotter.height())
    if camera.parallel_projection:
        height = 2 * camera.parallel_scale
    else:
        height = 2 * camera.distance * np.tan(np.radians(camera.view_angle) / 2)
        if camera.GetUseHorizontalViewAngle():
            height /= aspect
    shift = height / max(1, plotter.height()) * (-right * dx + up * dy)
    camera.position = tuple(np.asarray(camera.position) + shift)
    camera.focal_point = tuple(np.asarray(camera.focal_point) + shift)
    plotter.reset_camera_clipping_range()


class ViewLayoutDrag:
    """Double-click selects a layout item; its next drag consumes the selection.

    Holding the second press also works. Ordinary presses, zoom and edit-mode
    picking pass through to the existing interactor.
    """

    def __init__(self, viewer):
        self.viewer = viewer
        self.target = None
        self.active = False
        self.moved = False
        self.can_arm = False

    def cancel(self):
        self.target = None
        self.active = False
        self.viewer.plotter.unsetCursor()

    def _point(self, event):
        plotter = self.viewer.plotter
        return (event.position().x() / max(1, plotter.width()),
                1 - event.position().y() / max(1, plotter.height()))

    def _begin(self, event, *, double):
        self.active = True
        self.moved = False
        self.can_arm = double
        self.last = event.position()
        self.start = self.last
        x, y = self._point(event)
        viewer = self.viewer
        if self.target == "legend":
            bounds = viewer._chemical_legend_overlay.bounds
            width, height = viewer.plotter.window_size
            self.origin = (bounds[0] / width, bounds[1] / height)
            self.extent = ((bounds[2] - bounds[0]) / width, (bounds[3] - bounds[1]) / height)
        elif self.target == "axes":
            left, bottom, right, top = compass_viewport(viewer)
            self.origin = left, bottom
            self.extent = right - left, top - bottom
        self.anchor = x, y
        viewer.plotter.setCursor(Qt.CursorShape.ClosedHandCursor)

    def handle(self, event):
        kind = event.type()
        viewer = self.viewer
        if kind in (QEvent.Type.FocusOut, QEvent.Type.Hide):
            self.cancel()
            return False
        if kind == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape and self.target:
            self.cancel()
            return True
        if kind not in (QEvent.Type.MouseButtonDblClick, QEvent.Type.MouseButtonPress,
                        QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease):
            return False
        if viewer.edit_mode:
            if self.target:
                self.cancel()
            return False
        if kind == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
            x, y = self._point(event)
            self.target = "structure"
            overlay = getattr(viewer, "_chemical_legend_overlay", None)
            if getattr(viewer, "show_legend", True) and overlay is not None and overlay.bounds:
                width, height = viewer.plotter.window_size
                left, bottom, right, top = overlay.bounds
                if left <= x * width <= right and bottom <= y * height <= top:
                    self.target = "legend"
            if self.target == "structure" and viewer.show_axes:
                left, bottom, right, top = compass_viewport(viewer)
                if left <= x <= right and bottom <= y <= top:
                    self.target = "axes"
            self._begin(event, double=True)
            return True
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton and self.target:
            self._begin(event, double=False)
            return True
        if kind == QEvent.Type.MouseMove and self.active and event.buttons() & Qt.MouseButton.LeftButton:
            if not self.moved and (event.position() - self.start).manhattanLength() < 3:
                return True
            self.moved = True
            if self.target == "structure":
                delta = event.position() - self.last
                pan_camera(viewer.plotter, delta.x(), delta.y())
            else:
                x, y = self._point(event)
                position = tuple(max(0., min(1. - extent, origin + point - anchor))
                                 for origin, point, anchor, extent in zip(
                                     self.origin, (x, y), self.anchor, self.extent))
                if self.target == "legend":
                    viewer.legend_position = position
                    viewer._chemical_legend_overlay.layout()
                else:
                    viewer.axes_position = position
                    viewer.plotter.renderer.axes_widget.SetViewport(*compass_viewport(viewer))
                    # An automatically placed legend follows the compass.
                    overlay = getattr(viewer, "_chemical_legend_overlay", None)
                    if overlay is not None and viewer.legend_position is None:
                        overlay.layout()
            self.last = event.position()
            viewer.plotter.render()
            return True
        if kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton and self.active:
            self.active = False
            if self.moved or not self.can_arm:
                self.cancel()
            else:
                viewer.plotter.setCursor(Qt.CursorShape.OpenHandCursor)
            return True
        return False
