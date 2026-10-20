"""Native scene legend: actual figure outlines and portable chemical captions."""

from __future__ import annotations

import re

import numpy as np
import pyvista as pv
from vtkmodules.vtkRenderingCore import vtkActor2D, vtkPolyDataMapper2D, vtkTextActor, vtkTextProperty
from vtkmodules.vtkRenderingFreeType import vtkFreeTypeTools

from craft.ui.legend import chemical_caption_runs, compass_viewport, distinct_legend_entries


def polyhedron_legend_glyph(points, faces) -> pv.PolyData | None:
    """Project supplied face edges for an icon; never reconstruct a hull."""
    if not faces or len(points) < 3:
        return None
    vertices = np.asarray(points, dtype=float)
    vertices = vertices - vertices.mean(axis=0)
    _, singular, axes = np.linalg.svd(vertices, full_matrices=False)
    if singular[-1] < 1e-7 * max(singular[0], 1e-12):
        vertices = vertices @ axes.T
    else:
        # Look obliquely at an actual face. A fixed world-space direction can
        # superimpose vertices of a differently oriented tetrahedron.
        face = next(face for face in faces if len(face) >= 3)
        edge = vertices[face[1]] - vertices[face[0]]
        normal = np.cross(edge, vertices[face[2]] - vertices[face[0]])
        if np.linalg.norm(normal) > 1e-12:
            right = edge / np.linalg.norm(edge)
            normal /= np.linalg.norm(normal)
            up = np.cross(normal, right)
            direction = normal + .23 * right + .31 * up
            direction /= np.linalg.norm(direction)
            right -= np.dot(right, direction) * direction
            right /= np.linalg.norm(right)
            vertices = vertices @ np.asarray((right, np.cross(direction, right), direction)).T
        else:
            vertices = vertices @ axes.T
    vertices[:, 2] = 0
    extent = np.ptp(vertices[:, :2], axis=0).max()
    if extent < 1e-12:
        return None
    vertices *= 1.8 / extent
    edges = sorted({tuple(sorted((face[index - 1], vertex)))
                    for face in faces for index, vertex in enumerate(face)})
    wire = pv.PolyData(vertices, lines=np.asarray([(2, *edge) for edge in edges]).ravel())
    return wire.tube(radius=.045, n_sides=6)


def draw_chemical_legend(viewer, items, glyphs=None) -> None:
    """Draw fixed-size text runs beside native figure glyphs, wrapping captions."""
    items = tuple(items)
    entries = distinct_legend_entries(items)
    if not entries:
        return
    glyphs = glyphs or {}
    # Match the grouping used for colour-disambiguated captions.
    figures = []
    for caption, color in entries:
        candidates = (item for item in items if item[1] == color
                      and (caption == item[0] or caption.startswith(item[0] + " · ")))
        glyph = next((glyphs[item] for item in candidates if item in glyphs), None)
        figures.append((caption, color, glyph if glyph is not None else "circle"))
    plotter = viewer.plotter
    actor = plotter.add_legend(figures, bcolor="#ffffff", border=False,
                               loc="lower left", background_opacity=.76)
    # Reduced non-rendering plotters can still inspect semantic legend entries.
    if actor is None or not hasattr(plotter, "renderer"):
        return
    actor.SetVisibility(False)
    previous = getattr(viewer, "_chemical_legend_overlay", None)
    if previous is not None:
        previous.close()
    viewer._chemical_legend_overlay = _LegendOverlay(viewer, figures)


class _LegendOverlay:
    """Keep pixel geometry and font metrics in the same device coordinate space."""

    def __init__(self, viewer, figures):
        self.viewer = viewer
        self.figures = figures
        self.actors = []
        self.bounds = None
        self.window = viewer.plotter.renderer.GetRenderWindow()
        self.observer = None
        self.layout()
        if self.window is not None:
            self.observer = self.window.AddObserver("WindowResizeEvent", self.layout)

    def close(self):
        if self.window is not None and self.observer is not None:
            self.window.RemoveObserver(self.observer)
            self.observer = None
        self._clear()

    def _clear(self):
        labels = getattr(self.viewer, "_polyhedron_legend_labels", [])
        for actor in self.actors:
            self.viewer.plotter.renderer.RemoveViewProp(actor)
            if actor in labels:
                labels.remove(actor)
        self.actors.clear()
        self.bounds = None

    def _add(self, actor):
        actor.PickableOff()
        self.viewer.plotter.renderer.AddViewProp(actor)
        self.actors.append(actor)
        if not hasattr(self.viewer, "_polyhedron_legend_labels"):
            self.viewer._polyhedron_legend_labels = []
        self.viewer._polyhedron_legend_labels.append(actor)

    def _shape(self, mesh, color, x, y, size, opacity=1.):
        mesh = mesh.copy()
        mesh.points = np.asarray(mesh.points) * size
        mapper = vtkPolyDataMapper2D()
        mapper.SetInputData(mesh)
        mapper.ScalarVisibilityOff()
        actor = vtkActor2D()
        actor.SetMapper(mapper)
        actor.SetPosition(x, y)
        actor.GetProperty().SetColor(pv.Color(color).float_rgb)
        actor.GetProperty().SetOpacity(opacity)
        self._add(actor)

    def layout(self, *_event):
        self._clear()
        width, height = self.window.GetSize() if self.window is not None else self.viewer.plotter.window_size
        if width <= 0 or height <= 0:
            return
        dpi = max(72, self.window.GetDPI()) if self.window is not None else 72
        scale = dpi / 72
        requested = getattr(self.viewer, "legend_scale", 1.)
        margin = 12 * scale
        bottom = (height * compass_viewport(self.viewer)[3] + margin
                  if getattr(self.viewer, "show_axes", False) else margin)
        position = getattr(self.viewer, "legend_position", None)
        available_height = max(1., height - (bottom if position is None else margin) - margin)
        caption_width = min(420 * scale * requested, max(60 * scale, width * .42))
        metrics = vtkFreeTypeTools.GetInstance()
        measured = {}

        def measure(text, size):
            key = text, size
            if key not in measured:
                prop = vtkTextProperty()
                prop.SetFontFamilyToArial()
                prop.SetFontSize(size)
                bounds = [0, 0, 0, 0]
                metrics.GetBoundingBox(prop, text, dpi, bounds)
                measured[key] = bounds[1] - bounds[0] + 1
            return measured[key]

        def wrap(caption, font):
            lines, used = [[]], 0
            for text, subscript in chemical_caption_runs(caption):
                size = max(5, round(font * .72)) if subscript else font
                for word in re.findall(r"\s+|\S+", text):
                    if used and used + measure(word, size) > caption_width:
                        lines.append([])
                        used = 0
                        word = word.lstrip()
                    for char in word:
                        char_width = measure(char, size)
                        if used + char_width > caption_width and used:
                            lines.append([])
                            used = 0
                        if lines[-1] and lines[-1][-1][1] == subscript:
                            lines[-1][-1] = (lines[-1][-1][0] + char, subscript)
                        else:
                            lines[-1].append((char, subscript))
                        used += char_width
            return lines

        font = max(6, round(14 * requested))
        while True:
            captions = [wrap(caption, font) for caption, _color, _glyph in self.figures]
            effective = font / 14
            heights = [max(font + 14 * effective, len(lines) * (font + 5 * effective) + 8 * effective) * scale
                       for lines in captions]
            if sum(heights) <= available_height or font <= 6:
                break
            font -= 1
        glyph_width = 36 * scale * effective
        left = width * compass_viewport(self.viewer)[0] if getattr(self.viewer, "axes_position", None) else margin
        # One backing panel, rather than backgrounds interrupting formula runs.
        text_width = max(sum(measure(text, max(5, round(font * .72)) if subscript else font)
                             for text, subscript in line)
                         for lines in captions for line in lines)
        panel_width = min(width - 2 * margin, glyph_width + text_width + 8 * scale * effective)
        panel_height = sum(heights)
        if position is not None:
            left, bottom = position[0] * width, position[1] * height
        left = max(0., min(width - panel_width, left))
        bottom = max(0., min(height - panel_height, bottom))
        self.bounds = (left, bottom, left + panel_width, bottom + panel_height)
        panel = pv.PolyData(np.asarray(((0., 0., 0.), (panel_width, 0., 0.),
                                       (panel_width, sum(heights), 0.), (0., sum(heights), 0.))),
                            faces=[4, 0, 1, 2, 3])
        self._shape(panel, "white", left, bottom, 1., .76)
        top = bottom + sum(heights)
        for (_caption, color, glyph), lines, row_height in zip(self.figures, captions, heights):
            if isinstance(glyph, str):
                glyph = pv.Circle(radius=.48, resolution=24)
            self._shape(glyph, color, left + glyph_width / 2, top - row_height / 2,
                        min(12 * scale * effective, row_height / 3))
            for line_index, runs in enumerate(lines):
                x = left + glyph_width
                y = top - (6 * effective + font + line_index * (font + 5 * effective)) * scale
                for text, subscript in runs:
                    size = max(5, round(font * .72)) if subscript else font
                    label = vtkTextActor()
                    label.SetInput(text)
                    label.SetPosition(x, y - (font * .24 * scale if subscript else 0))
                    prop = label.GetTextProperty()
                    prop.SetFontFamilyToArial()
                    prop.SetFontSize(size)
                    prop.SetColor(*(np.asarray(pv.Color(color).float_rgb) * .72))
                    self._add(label)
                    x += measure(text, size)
            top -= row_height
