"""Camera operations shared by structural and morphology views."""

import numpy as np


def view_lattice_axis(plotter, cell, axis: str) -> None:
    matrix = np.asarray(cell.matrix, dtype=float)
    index = {'a': 0, 'b': 1, 'c': 2}[axis]
    direction = matrix[index] / np.linalg.norm(matrix[index])
    up = matrix[2 if index < 2 else 1].copy()
    up -= np.dot(up, direction) * direction
    up /= np.linalg.norm(up)
    plotter.view_vector(direction, viewup=up, render=False)
    plotter.reset_camera()


def zoom_view(plotter, factor: float) -> None:
    plotter.camera.zoom(factor)
    plotter.render()
