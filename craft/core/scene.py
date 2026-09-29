from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import ceil, floor

import numpy as np

from craft.adapters.cristma_contacts_presentation import ContactPresentation
from craft.core.model import AtomSite, CrystalStructure
from craft.core.site_orbits import site_orbit_key

@dataclass(frozen=True, slots=True)
class DisplayAtom:
    site_index: int
    site: AtomSite
    fractional: tuple[float, float, float]
    cartesian: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class Bond:
    first: int
    second: int
    distance: float
    contact_id: str = ""
    contact_orbit_id: str = ""


@dataclass(slots=True)
class SceneData:
    atoms: list[DisplayAtom]
    bonds: list[Bond]
    cell_corners: np.ndarray
    cell_edges: list[tuple[int, int]]
    translations: tuple[tuple[float, float, float], ...]
    fractional_translations: tuple[tuple[int, int, int], ...]
    repeat: tuple[int, int, int]
    bounds: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]


def _display_atoms(
    structure: CrystalStructure,
    bounds: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
) -> list[DisplayAtom]:
    atoms = []
    translation_ranges = tuple(
        range(floor(minimum), ceil(maximum))
        for minimum, maximum in bounds
    )
    for translation in product(*translation_ranges):
        for site_index, site in enumerate(structure.sites):
            fractional = tuple(site.fractional[i] + translation[i] for i in range(3))
            if not all(
                bounds[axis][0] - 1e-8 <= fractional[axis] < bounds[axis][1] - 1e-8
                for axis in range(3)
            ):
                continue
            cartesian = tuple(float(value) for value in structure.cell.frac_to_cart(fractional))
            atoms.append(DisplayAtom(site_index=site_index, site=site, fractional=fractional, cartesian=cartesian))
    return atoms


def _atom_translation(atom: DisplayAtom) -> tuple[int, int, int]:
    return tuple(
        int(round(atom.fractional[axis] - atom.site.fractional[axis]))
        for axis in range(3)
    )


def _contact_atom_key(atom: DisplayAtom) -> tuple[str, tuple[int, int, int]]:
    return atom.site.scientific_id, _atom_translation(atom)


def _complete_contact_boundary(
    structure: CrystalStructure,
    atoms: list[DisplayAtom],
    presentation: ContactPresentation,
) -> None:
    """Add only scientific contact endpoints just outside the requested bounds."""
    by_id = {
        site.scientific_id: (site_index, site)
        for site_index, site in enumerate(structure.sites)
        if site.scientific_id
    }
    requested: set[tuple[str, tuple[int, int, int]]] = set()
    for atom in atoms:
        atom_id, translation = _contact_atom_key(atom)
        for contact in presentation.instances:
            if atom_id == contact.first_atom_id:
                requested.add((
                    contact.second_atom_id,
                    tuple(translation[axis] + contact.cell_translation[axis] for axis in range(3)),
                ))
            if atom_id == contact.second_atom_id:
                requested.add((
                    contact.first_atom_id,
                    tuple(translation[axis] - contact.cell_translation[axis] for axis in range(3)),
                ))
    seen = {_contact_atom_key(atom) for atom in atoms}
    for atom_id, translation in sorted(requested):
        if (atom_id, translation) in seen or atom_id not in by_id:
            continue
        site_index, site = by_id[atom_id]
        fractional = tuple(site.fractional[axis] + translation[axis] for axis in range(3))
        atoms.append(DisplayAtom(
            site_index=site_index,
            site=site,
            fractional=fractional,
            cartesian=tuple(float(value) for value in structure.cell.frac_to_cart(fractional)),
        ))
        seen.add((atom_id, translation))


def _contact_bonds(atoms: list[DisplayAtom], presentation: ContactPresentation) -> list[Bond]:
    by_key: dict[tuple[str, tuple[int, int, int]], int] = {}
    for index, atom in enumerate(atoms):
        by_key[_contact_atom_key(atom)] = index
    bonds: list[Bond] = []
    for first_index, first_atom in enumerate(atoms):
        first_translation = _atom_translation(first_atom)
        for contact in presentation.instances:
            if first_atom.site.scientific_id != contact.first_atom_id:
                continue
            second_translation = tuple(
                first_translation[axis] + contact.cell_translation[axis]
                for axis in range(3)
            )
            second_index = by_key.get((contact.second_atom_id, second_translation))
            if second_index is not None:
                bonds.append(Bond(
                    first_index,
                    second_index,
                    contact.distance,
                    contact.contact_id,
                    contact.contact_orbit_id,
                ))
    return bonds


def _cell_geometry(
    structure: CrystalStructure,
    bounds: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
) -> tuple[np.ndarray, list[tuple[int, int]]]:
    (amin, amax), (bmin, bmax), (cmin, cmax) = bounds
    fractional_corners = (
        (amin, bmin, cmin), (amax, bmin, cmin),
        (amax, bmax, cmin), (amin, bmax, cmin),
        (amin, bmin, cmax), (amax, bmin, cmax),
        (amax, bmax, cmax), (amin, bmax, cmax),
    )
    corners = np.asarray(
        [structure.cell.frac_to_cart(point) for point in fractional_corners],
        dtype=float,
    )
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    return corners, edges


def build_scene(
    structure: CrystalStructure,
    repeat: tuple[int, int, int] = (1, 1, 1),
    bounds: tuple[tuple[float, float], tuple[float, float], tuple[float, float]] | None = None,
    include_bonds: bool = True,
    complete_boundary: bool = True,
    contact_presentation: ContactPresentation | None = None,
) -> SceneData:
    if any(value < 1 for value in repeat):
        raise ValueError("Supercell repeat values must be at least one.")
    if bounds is None:
        bounds = tuple((0.0, float(value)) for value in repeat)
    bounds = tuple((float(pair[0]), float(pair[1])) for pair in bounds)
    if len(bounds) != 3 or any(minimum >= maximum for minimum, maximum in bounds):
        raise ValueError("Each cell-bound minimum must be smaller than its maximum.")
    atoms = _display_atoms(structure, bounds)
    if complete_boundary and contact_presentation is not None:
        _complete_contact_boundary(structure, atoms, contact_presentation)
    corners, edges = _cell_geometry(structure, bounds)
    translation_ranges = tuple(
        range(floor(minimum), ceil(maximum))
        for minimum, maximum in bounds
    )
    fractional_translations = tuple(product(*translation_ranges))
    translations = tuple(
        tuple(float(value) for value in structure.cell.frac_to_cart(translation))
        for translation in fractional_translations
    )
    return SceneData(
        atoms=atoms,
        bonds=_contact_bonds(atoms, contact_presentation)
        if include_bonds and contact_presentation is not None
        else [],
        cell_corners=corners,
        cell_edges=edges,
        translations=translations,
        fractional_translations=fractional_translations,
        repeat=repeat,
        bounds=bounds,
    )


def build_asymmetric_scene(
    structure: CrystalStructure,
    *,
    site_indices: tuple[int, ...] | None = None,
    contact_presentation: ContactPresentation | None = None,
) -> SceneData:
    """Build the strict crystallographic asymmetric unit without symmetry copies."""
    requested_keys = (
        {
            site_orbit_key(structure.sites[index].label)
            for index in site_indices
            if 0 <= index < len(structure.sites)
        }
        if site_indices is not None
        else None
    )
    representatives: dict[str, int] = {}
    for index, site in enumerate(structure.sites):
        representatives.setdefault(site_orbit_key(site.label), index)

    atoms: list[DisplayAtom] = []
    for asymmetric in structure.asymmetric_sites:
        key = site_orbit_key(asymmetric.label)
        if requested_keys is not None and key not in requested_keys:
            continue
        index = representatives.get(key)
        if index is None:
            continue
        site = structure.sites[index]
        atoms.append(
            DisplayAtom(
                site_index=index,
                site=site,
                fractional=tuple(float(value) for value in site.fractional),
                cartesian=tuple(
                    float(value) for value in structure.cell.frac_to_cart(site.fractional)
                ),
            )
        )

    bounds = ((0.0, 1.0), (0.0, 1.0), (0.0, 1.0))
    corners, edges = _cell_geometry(structure, bounds)
    return SceneData(
        atoms=atoms,
        bonds=_contact_bonds(atoms, contact_presentation)
        if contact_presentation is not None
        else [],
        cell_corners=corners,
        cell_edges=edges,
        translations=((0.0, 0.0, 0.0),),
        fractional_translations=((0, 0, 0),),
        repeat=(1, 1, 1),
        bounds=bounds,
    )
