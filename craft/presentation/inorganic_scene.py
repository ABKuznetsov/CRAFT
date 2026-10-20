"""Bounded display materialization of installed CRiStMa inorganic results."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import ceil, floor
from typing import TYPE_CHECKING

import numpy as np

from cristma.crystal_chemistry import CellRange

if TYPE_CHECKING:
    from craft.presentation.crystal_layers import CrystalLayerGeometry


Point = tuple[float, float, float]
Translation = tuple[int, int, int]
Edge = tuple[Point, Point]


@dataclass(frozen=True, slots=True)
class AtomSceneInstance:
    atom_id: str
    source_site_id: str
    cell_translation: Translation
    fractional: Point
    cartesian: Point
    composition: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class ContactSceneSegment:
    contact_id: str
    contact_orbit_id: str
    first_atom_id: str
    second_atom_id: str
    first_translation: Translation
    second_translation: Translation
    distance: float


@dataclass(frozen=True, slots=True)
class PolyhedronMesh:
    polyhedron_id: str
    polyhedron_orbit_id: str
    center_atom_id: str
    center_translation: Translation
    local_vertices: tuple[Point, ...]
    faces: tuple[tuple[int, ...], ...]
    triangles: tuple[tuple[int, int, int], ...]
    vertex_source_site_ids: tuple[str, ...]
    vertex_compositions: tuple[tuple[tuple[str, float], ...], ...]


@dataclass(frozen=True, slots=True)
class StructuralBlockFragmentMesh:
    """One finite display projection of an exact CRiStMa structural block."""

    block_id: str
    rank: int
    unit_instance_count: int
    unit_orbit_ids: tuple[str, ...]
    points: tuple[Point, ...]
    faces: tuple[tuple[int, ...], ...]
    isolated_points: tuple[Point, ...]
    isolated_point_source_site_ids: tuple[str, ...] = ()
    isolated_point_compositions: tuple[tuple[tuple[str, float], ...], ...] = ()


@dataclass(frozen=True, slots=True)
class StructuralUnitSceneInstance:
    """One symmetry-expanded structural unit in crystallographic space."""

    unit_instance_id: str
    unit_orbit_id: str
    kind: str
    center: Point
    points: tuple[Point, ...]
    faces: tuple[tuple[int, ...], ...]
    point_source_site_ids: tuple[str, ...] = ()
    point_compositions: tuple[tuple[tuple[str, float], ...], ...] = ()


@dataclass(frozen=True, slots=True)
class InorganicSceneData:
    atoms: tuple[AtomSceneInstance, ...]
    contacts: tuple[ContactSceneSegment, ...]
    polyhedra: tuple[PolyhedronMesh, ...]
    block_fragments: tuple[StructuralBlockFragmentMesh, ...]
    unit_cell_edges: tuple[Edge, ...]
    expanded_grid_edges: tuple[Edge, ...]
    bounds: tuple[tuple[float, float], ...]
    structural_units: tuple[StructuralUnitSceneInstance, ...] = ()
    crystal_layers: tuple[CrystalLayerGeometry, ...] = ()


def visible_atoms(scene: InorganicSceneData, state, *, include_auto_hidden: bool = True) -> tuple[AtomSceneInstance, ...]:
    from craft.presentation.block_state import auto_hidden_members
    hidden_orbits = getattr(state, "hidden_atom_orbit_ids", set())
    hidden_instances = getattr(state, "hidden_atom_instance_keys", set())
    auto_hidden = auto_hidden_members(state, "block_auto_hidden_atom_ids") if include_auto_hidden else ()
    return tuple(
        atom
        for atom in scene.atoms
        if atom.source_site_id not in hidden_orbits
        and (atom.atom_id, atom.cell_translation) not in hidden_instances
        and atom.atom_id not in auto_hidden
    )


def visible_polyhedra(scene: InorganicSceneData, state, *, include_auto_hidden: bool = True) -> tuple[PolyhedronMesh, ...]:
    from craft.presentation.block_state import auto_hidden_members
    hidden_orbits = getattr(state, "hidden_polyhedron_orbit_ids", set())
    hidden_instances = getattr(state, "hidden_polyhedron_ids", set())
    auto_hidden = auto_hidden_members(state, "block_auto_hidden_polyhedron_orbit_ids") if include_auto_hidden else ()
    return tuple(
        mesh
        for mesh in scene.polyhedra
        if mesh.polyhedron_orbit_id not in hidden_orbits
        and mesh.polyhedron_orbit_id not in auto_hidden
        and mesh.polyhedron_id not in hidden_instances
    )


def visible_block_fragments(
    scene: InorganicSceneData, state
) -> tuple[StructuralBlockFragmentMesh, ...]:
    shown = getattr(state, "shown_block_ids", set())
    hidden = getattr(state, "hidden_block_ids", set())
    return tuple(
        fragment
        for fragment in scene.block_fragments
        if fragment.block_id in shown and fragment.block_id not in hidden
    )


_EDGE_INDICES = (
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
)


def _point(values) -> Point:
    return tuple(float(value) for value in values)


def _composition(atom) -> tuple[tuple[str, float], ...]:
    result: list[tuple[str, float]] = []
    for component in getattr(atom, "components", ()):
        species = getattr(component, "species", "")
        symbol = str(getattr(species, "symbol", species))
        occupancy = getattr(component, "occupancy", 0.0)
        value = getattr(occupancy, "value", occupancy)
        try:
            weight = float(value)
        except (TypeError, ValueError):
            continue
        if symbol and np.isfinite(weight) and weight > 0.0:
            result.append((symbol, weight))
    return tuple(result)


def _frac_to_cart(structure, fractional) -> Point:
    matrix = structure.cell.matrix
    return tuple(
        float(sum(fractional[row] * matrix[row, column] for row in range(3)))
        for column in range(3)
    )


def _cell_edges(structure, minimum: Point, maximum: Point) -> tuple[Edge, ...]:
    amin, bmin, cmin = minimum
    amax, bmax, cmax = maximum
    fractional = (
        (amin, bmin, cmin), (amax, bmin, cmin),
        (amax, bmax, cmin), (amin, bmax, cmin),
        (amin, bmin, cmax), (amax, bmin, cmax),
        (amax, bmax, cmax), (amin, bmax, cmax),
    )
    corners = tuple(_frac_to_cart(structure, item) for item in fractional)
    return tuple((corners[first], corners[second]) for first, second in _EDGE_INDICES)


def _translation_range(bounds):
    return tuple(range(floor(low) - 1, ceil(high) + 1) for low, high in bounds)


def _contact_region(bounds) -> CellRange:
    limits = tuple(
        (floor(low), ceil(high) - 1)
        for low, high in bounds
    )
    return CellRange(
        limits[0][0], limits[0][1],
        limits[1][0], limits[1][1],
        limits[2][0], limits[2][1],
    )


def _operation_by_id(structure) -> dict[str, object]:
    space_group = getattr(structure, "space_group", None)
    return {
        str(operation.id): operation
        for operation in getattr(space_group, "operations", ())
        if getattr(operation, "id", None) is not None
    }


def _rotated_local_vertices(
    structure,
    vertices,
    source_operation,
    target_operation,
) -> tuple[Point, ...]:
    """Rotate scientific local vectors into a symmetry-related display copy."""

    cell = np.asarray(structure.cell.matrix, dtype=float)
    source = np.asarray(source_operation.rotation, dtype=float)
    target = np.asarray(target_operation.rotation, dtype=float)
    relative = target @ np.linalg.inv(source)
    inverse_cell_transpose = np.linalg.inv(cell.T)
    return tuple(
        _point(cell.T @ relative @ inverse_cell_transpose @ np.asarray(vertex, dtype=float))
        for vertex in vertices
    )


def _inside(fractional: Point, bounds) -> bool:
    return all(
        low - 1e-8 <= fractional[axis] < high - 1e-8
        for axis, (low, high) in enumerate(bounds)
    )


def _triangulate(faces) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        (face[0], face[index], face[index + 1])
        for face in faces
        for index in range(1, len(face) - 1)
    )


def representative_fragment_translations(
    periodic_generators,
) -> tuple[Translation, ...]:
    """Return a deterministic finite window over exact periodic generators."""

    generators = tuple(
        tuple(int(value) for value in generator)
        for generator in periodic_generators
    )
    if not generators:
        return ((0, 0, 0),)
    translations: dict[Translation, None] = {}
    for coefficients in product(range(-1, 2), repeat=len(generators)):
        translation = tuple(
            sum(coefficients[index] * generators[index][axis]
                for index in range(len(generators)))
            for axis in range(3)
        )
        translations.setdefault(translation, None)
    return tuple(translations)


def _unit_kind(value) -> str:
    return str(getattr(value, "value", value))


def _build_structural_unit_instances(
    document,
    structure,
    base_by_id,
    instances,
) -> tuple[StructuralUnitSceneInstance, ...]:
    representation = getattr(document.scientific.representation, "result", None)
    if representation is None:
        return ()
    operation_by_id = _operation_by_id(structure)
    result: list[StructuralUnitSceneInstance] = []
    for unit in representation.unit_orbits:
        geometry = getattr(unit, "representative_geometry", None)
        center_ref = getattr(geometry, "center_atom_ref", None)
        if geometry is None or center_ref is None:
            continue
        source_center = base_by_id.get(center_ref.atom_id)
        if source_center is None:
            continue
        source_fractional = tuple(
            source_center.fractional[axis] + center_ref.cell_translation[axis]
            for axis in range(3)
        )
        source_cartesian = np.asarray(_frac_to_cart(structure, source_fractional))
        local_vertices: list[Point] = []
        vertex_site_ids: list[str] = []
        vertex_compositions: list[tuple[tuple[str, float], ...]] = []
        for ref in geometry.vertex_atom_refs:
            atom = base_by_id.get(ref.atom_id)
            if atom is None:
                continue
            fractional = tuple(
                atom.fractional[axis] + ref.cell_translation[axis]
                for axis in range(3)
            )
            local_vertices.append(
                _point(np.asarray(_frac_to_cart(structure, fractional)) - source_cartesian)
            )
            vertex_site_ids.append(atom.source_site_id)
            vertex_compositions.append(_composition(atom))
        if not local_vertices:
            continue
        source_operation = operation_by_id.get(
            str(source_center.representative_image.operation_id)
        )
        faces = tuple(
            tuple(int(index) for index in face)
            for face in geometry.faces
            if len(face) >= 3 and max(face) < len(local_vertices)
        )
        for (atom_id, translation), center in instances.items():
            if center.source_site_id != unit.center_independent_site_id:
                continue
            target_atom = base_by_id[atom_id]
            target_operation = operation_by_id.get(
                str(target_atom.representative_image.operation_id)
            )
            rotated = (
                _rotated_local_vertices(
                    structure,
                    local_vertices,
                    source_operation,
                    target_operation,
                )
                if source_operation is not None and target_operation is not None
                else tuple(local_vertices)
            )
            center_point = np.asarray(center.cartesian, dtype=float)
            points = tuple(
                _point(center_point + np.asarray(vector, dtype=float))
                for vector in rotated
            )
            result.append(StructuralUnitSceneInstance(
                unit_instance_id=(
                    f"{unit.unit_orbit_id}@{atom_id}@"
                    f"{translation[0]},{translation[1]},{translation[2]}"
                ),
                unit_orbit_id=unit.unit_orbit_id,
                kind=_unit_kind(unit.kind),
                center=center.cartesian,
                points=points,
                faces=faces,
                point_source_site_ids=tuple(vertex_site_ids),
                point_compositions=tuple(vertex_compositions),
            ))
    return tuple(result)


def _build_block_fragments(document, structural_units):
    representation = getattr(document.scientific.representation, "result", None)
    blocks_result = getattr(document.scientific.blocks, "result", None)
    if representation is None or blocks_result is None:
        return ()
    unit_orbits = {
        unit.unit_orbit_id: unit for unit in representation.unit_orbits
    }
    connection_orbits = {
        connection.connection_orbit_id: connection
        for connection in representation.connection_orbits
    }
    fragments: list[StructuralBlockFragmentMesh] = []
    for block in blocks_result.blocks:
        points: list[Point] = []
        faces: list[tuple[int, ...]] = []
        isolated: list[Point] = []
        isolated_site_ids: list[str] = []
        isolated_compositions: list[tuple[tuple[str, float], ...]] = []
        instance_ids: list[str] = []
        allowed = set(block.unit_orbit_ids)
        connector_unit_ids = {
            unit_id
            for connection_id in block.connection_orbit_ids
            if connection_id in connection_orbits
            for unit_id in (
                connection_orbits[connection_id].first_unit_orbit_id,
                connection_orbits[connection_id].second_unit_orbit_id,
            )
            if int(block.rank) > 0
            and unit_id in allowed
            and unit_id in unit_orbits
            and _unit_kind(unit_orbits[unit_id].kind) == "atom"
        }
        for unit in structural_units:
            if unit.unit_orbit_id not in allowed:
                continue
            offset = len(points)
            points.extend(unit.points)
            faces.extend(
                tuple(offset + index for index in face) for face in unit.faces
            )
            if not unit.faces and unit.unit_orbit_id in connector_unit_ids:
                isolated.extend(unit.points)
                isolated_site_ids.extend(unit.point_source_site_ids)
                isolated_compositions.extend(unit.point_compositions)
            instance_ids.append(unit.unit_instance_id)
        fragments.append(StructuralBlockFragmentMesh(
            block_id=block.block_id,
            rank=int(block.rank),
            unit_instance_count=len(instance_ids),
            unit_orbit_ids=tuple(instance_ids),
            points=tuple(points),
            faces=tuple(faces),
            isolated_points=tuple(isolated),
            isolated_point_source_site_ids=tuple(isolated_site_ids),
            isolated_point_compositions=tuple(isolated_compositions),
        ))
    return tuple(fragments)


def build_inorganic_scene(
    document,
    bounds,
    include_contacts: bool,
    complete_boundary: bool,
    *,
    include_expanded_grid: bool = False,
) -> InorganicSceneData:
    """Translate native objects for display without neighbor or motif searches."""

    normalized_bounds = tuple((float(low), float(high)) for low, high in bounds)
    if len(normalized_bounds) != 3 or any(low >= high for low, high in normalized_bounds):
        raise ValueError("Each cell-bound minimum must be smaller than its maximum.")
    structure = document.structure
    expanded = tuple(structure.atomic_view().atoms)
    base_by_id = {atom.id: atom for atom in expanded}
    instances: dict[tuple[str, Translation], AtomSceneInstance] = {}

    def add_atom(atom_id: str, translation: Translation) -> None:
        atom = base_by_id.get(atom_id)
        if atom is None or (atom_id, translation) in instances:
            return
        fractional = tuple(atom.fractional[i] + translation[i] for i in range(3))
        instances[(atom_id, translation)] = AtomSceneInstance(
            atom_id=atom.id,
            source_site_id=atom.source_site_id,
            cell_translation=translation,
            fractional=_point(fractional),
            cartesian=_frac_to_cart(structure, fractional),
            composition=_composition(atom),
        )

    ranges = _translation_range(normalized_bounds)
    for translation in product(*ranges):
        for atom in expanded:
            fractional = tuple(atom.fractional[i] + translation[i] for i in range(3))
            if _inside(fractional, normalized_bounds):
                add_atom(atom.id, translation)
    interior_keys = frozenset(instances)

    contacts_result = getattr(document.scientific.crystal_chemistry, "result", None)
    native_contacts = (
        tuple(contacts_result.materialize_contacts(_contact_region(normalized_bounds)))
        if include_contacts and contacts_result is not None
        else ()
    )
    initially_visible_contacts = {
        row.contact_orbit_id
        for row in document.inorganic_presentation().contact_orbits
        if row.initially_visible
    }
    segments: list[ContactSceneSegment] = []
    for contact in native_contacts:
        first_ref = contact.first_atom_ref
        second_ref = contact.second_atom_ref
        first_translation = tuple(first_ref.cell_translation)
        second_translation = tuple(second_ref.cell_translation)
        first_key = (first_ref.atom_id, first_translation)
        second_key = (second_ref.atom_id, second_translation)
        if (
            complete_boundary
            and contact.resolved_contact_orbit_id in initially_visible_contacts
            and (first_key in interior_keys or second_key in interior_keys)
        ):
            add_atom(first_ref.atom_id, first_translation)
            add_atom(second_ref.atom_id, second_translation)
        if first_key in instances and second_key in instances:
            segments.append(ContactSceneSegment(
                contact_id=contact.contact_id,
                contact_orbit_id=contact.resolved_contact_orbit_id,
                first_atom_id=first_ref.atom_id,
                second_atom_id=second_ref.atom_id,
                first_translation=first_translation,
                second_translation=second_translation,
                distance=float(contact.distance),
            ))

    polyhedra_result = getattr(document.scientific.polyhedra, "result", None)
    operation_by_id = _operation_by_id(structure)
    polyhedra_list: list[PolyhedronMesh] = []
    for item in getattr(polyhedra_result, "polyhedra", ()):
        representative_center = base_by_id.get(item.center_atom_id)
        if representative_center is None:
            continue
        source_operation = operation_by_id.get(
            str(representative_center.representative_image.operation_id)
        )
        for (center_atom_id, center_translation), center in instances.items():
            if center.source_site_id != item.source_site_id:
                continue
            target_atom = base_by_id[center_atom_id]
            target_operation = operation_by_id.get(
                str(target_atom.representative_image.operation_id)
            )
            vertices = (
                _rotated_local_vertices(
                    structure,
                    item.local_vertices,
                    source_operation,
                    target_operation,
                )
                if source_operation is not None and target_operation is not None
                else tuple(_point(vertex) for vertex in item.local_vertices)
            )
            vertex_atoms = tuple(
                base_by_id.get(vertex.atom_ref.atom_id)
                for vertex in getattr(item, "vertices", ())
            )
            polyhedra_list.append(PolyhedronMesh(
                polyhedron_id=(
                    f"{item.polyhedron_id}@{center_atom_id}"
                    f"@{center_translation[0]},{center_translation[1]},{center_translation[2]}"
                ),
                polyhedron_orbit_id=item.polyhedron_orbit_id,
                center_atom_id=center_atom_id,
                center_translation=center_translation,
                local_vertices=vertices,
                faces=tuple(tuple(int(index) for index in face) for face in item.faces),
                triangles=_triangulate(item.faces),
                vertex_source_site_ids=tuple(
                    atom.source_site_id if atom is not None else ""
                    for atom in vertex_atoms
                ),
                vertex_compositions=tuple(
                    _composition(atom) if atom is not None else ()
                    for atom in vertex_atoms
                ),
            ))
    polyhedra = tuple(polyhedra_list)
    structural_units = _build_structural_unit_instances(
        document,
        structure,
        base_by_id,
        instances,
    )
    block_fragments = _build_block_fragments(document, structural_units)
    unit_cell_edges = _cell_edges(structure, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    grid_edges: tuple[Edge, ...] = ()
    if include_expanded_grid:
        edge_set: dict[tuple[Point, Point], None] = {}
        for translation in product(*ranges):
            low = _point(translation)
            high = _point(value + 1 for value in translation)
            for edge in _cell_edges(structure, low, high):
                edge_set.setdefault(tuple(sorted(edge)), None)
        grid_edges = tuple(edge_set)
    return InorganicSceneData(
        atoms=tuple(instances.values()),
        contacts=tuple(segments),
        polyhedra=polyhedra,
        block_fragments=block_fragments,
        unit_cell_edges=unit_cell_edges,
        expanded_grid_edges=grid_edges,
        bounds=normalized_bounds,
        structural_units=structural_units,
    )


__all__ = [
    "AtomSceneInstance",
    "ContactSceneSegment",
    "InorganicSceneData",
    "PolyhedronMesh",
    "StructuralBlockFragmentMesh",
    "StructuralUnitSceneInstance",
    "build_inorganic_scene",
    "representative_fragment_translations",
    "visible_atoms",
    "visible_block_fragments",
    "visible_polyhedra",
]
