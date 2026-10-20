from __future__ import annotations

from collections.abc import Iterable
import re

from craft.core.model import AtomSite


_ASCII_CAPTION = str.maketrans("₀₁₂₃₄₅₆₇₈₉·—–", "0123456789---")
_FORMULA = re.compile(r"(?<![A-Za-z0-9])(?:[A-Z][a-z]?\d*(?:\.\d+)?|[()]\d*)+(?![A-Za-z0-9])")


def compass_viewport(viewer):
    size = getattr(viewer, "axes_size", .3)
    extent = size - .01
    position = getattr(viewer, "axes_position", None) or (.01, .01)
    left, bottom = (max(0., min(1. - extent, value)) for value in position)
    return (left, bottom, left + extent, bottom + extent)


def chemical_caption_runs(label: str) -> tuple[tuple[str, bool], ...]:
    """Use ordinary font digits, lowering counts only inside chemical formulas.

    A single symbol followed by a number is also a common site label (B3),
    so require at least two element symbols in a formula token.
    """
    text = label.translate(_ASCII_CAPTION)
    lowered = set()
    for match in _FORMULA.finditer(text):
        if len(re.findall(r"[A-Z][a-z]?", match.group())) < 2:
            continue
        lowered.update(match.start() + index for index, char in enumerate(match.group())
                       if char.isdigit() or char == ".")
    runs = []
    for index, char in enumerate(text):
        subscript = index in lowered
        if runs and runs[-1][1] == subscript:
            runs[-1] = (runs[-1][0] + char, subscript)
        else:
            runs.append((char, subscript))
    return tuple(runs)


def atom_legend_labels(
    sites: Iterable[AtomSite],
    *,
    split_occupancies: bool,
    show_vacancies: bool,
) -> tuple[str, ...]:
    """Return unique chemical legend labels; occupancy stays encoded in sphere sectors."""
    labels: set[str] = set()
    for site in sites:
        if split_occupancies and site.is_disordered:
            labels.update(component.element for component in site.components)
            if show_vacancies and site.vacancy_fraction > 1e-6:
                labels.add("Vacancy")
        else:
            labels.add(site.element)
    return tuple(sorted(labels))


def distinct_legend_entries(items: Iterable[tuple[str, str, str]]) -> tuple[tuple[str, str], ...]:
    """Merge identical styles, distinguishing equal labels with different colours."""
    grouped: dict[str, dict[str, list[str]]] = {}
    for label, color, identifier in items:
        identifiers = grouped.setdefault(label, {}).setdefault(color, [])
        if identifier not in identifiers:
            identifiers.append(identifier)
    return tuple(sorted(
        (label if len(colors) == 1 else f"{label} · {', '.join(identifiers)}", color)
        for label, colors in grouped.items()
        for color, identifiers in colors.items()
    ))
