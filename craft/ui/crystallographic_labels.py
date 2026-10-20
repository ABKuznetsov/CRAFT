"""Crystallographic typography for rendered faces and form annotations."""

# Register before a VTK text renderer is first instantiated: renderers cache
# whether the MathText backend is available when they are constructed.
import vtkmodules.vtkRenderingMatplotlib  # noqa: F401


def miller_label(hkl, *, form=False):
    values = tuple(int(value) for value in hkl)
    if not any(value < 0 for value in values):
        left, right = ('{', '}') if form else ('(', ')')
        return left + ' '.join(map(str, values)) + right
    # Register VTK's MathText backend explicitly. It renders an overbar over
    # the whole index, independently of combining-mark support in a font.
    indices = (rf'\overline{{{abs(value)}}}' if value < 0 else str(value) for value in values)
    left, right = (r'\{', r'\}') if form else ('(', ')')
    return '$' + left + r'\,'.join(indices) + right + '$'
