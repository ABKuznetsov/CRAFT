"""Display-only materialization of native CrIStMa molecular results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from cristma.crystal_chemistry import (
    CellRange,
    ContactMaterializer,
    IntermolecularContactMaterializer,
    PackingMaterializer,
    ReferenceCell,
)
from cristma.crystallography import SymmetryContext

from craft.presentation.inorganic_scene import _cell_edges, _frac_to_cart


Point = tuple[float, float, float]
Translation = tuple[int, int, int]
Edge = tuple[Point, Point]


class OrganicSceneMode(str, Enum):
    SINGLE_MOLECULE = "single_molecule"
    RING = "ring"
    SBU = "sbu"
    LINKER = "linker"
    NET = "net"
    PACKING = "packing"
    CONTACTS = "contacts"


@dataclass(frozen=True, slots=True)
class MoleculeSceneInstance:
    molecule_id: str
    molecule_orbit_id: str
    atom_keys: tuple[tuple[str, Translation], ...]


@dataclass(frozen=True, slots=True)
class OrganicAtomSceneInstance:
    atom_id: str
    source_site_id: str
    element: str
    molecule_id: str
    molecule_orbit_id: str
    cell_translation: Translation
    fractional: Point
    cartesian: Point


@dataclass(frozen=True, slots=True)
class OrganicBondSceneSegment:
    contact_id: str
    contact_orbit_id: str
    molecular_bond_orbit_id: str
    molecule_id: str
    first_atom_id: str
    second_atom_id: str
    first_translation: Translation
    second_translation: Translation
    distance: float


@dataclass(frozen=True, slots=True)
class OrganicContactSceneSegment:
    contact_id: str
    contact_orbit_id: str
    first_atom_id: str
    second_atom_id: str
    start: Point
    end: Point
    distance: float
    interpretation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OrganicNetNodeSceneInstance:
    vertex_orbit_id: str
    kind: str
    fractional: Point
    cartesian: Point


@dataclass(frozen=True, slots=True)
class OrganicNetEdgeSceneSegment:
    edge_orbit_id: str
    first_vertex_orbit_id: str
    second_vertex_orbit_id: str
    start: Point
    end: Point


@dataclass(frozen=True, slots=True)
class OrganicSceneData:
    mode: OrganicSceneMode
    molecule_instances: tuple[MoleculeSceneInstance, ...]
    atoms: tuple[OrganicAtomSceneInstance, ...]
    covalent_bonds: tuple[OrganicBondSceneSegment, ...]
    intermolecular_contacts: tuple[OrganicContactSceneSegment, ...]
    highlighted_bond_orbit_ids: tuple[str, ...]
    net_nodes: tuple[OrganicNetNodeSceneInstance, ...]
    net_edges: tuple[OrganicNetEdgeSceneSegment, ...]
    unit_cell_edges: tuple[Edge, ...]
    selected_object_id: str | None = None


def _slot_result(document, name: str):
    return getattr(getattr(document.scientific, name), "result", None)


def _contact_region(molecules) -> CellRange:
    translations = tuple(
        ref.cell_translation
        for molecule in molecules
        for ref in molecule.atom_refs
    )
    minima = tuple(min(item[axis] for item in translations) - 1 for axis in range(3))
    maxima = tuple(max(item[axis] for item in translations) + 1 for axis in range(3))
    return CellRange(
        minima[0], maxima[0], minima[1], maxima[1], minima[2], maxima[2]
    )


def build_organic_scene(
    document,
    mode: OrganicSceneMode,
    *,
    selected_object_id: str | None = None,
) -> OrganicSceneData:
    """Build an explicit scene without performing scientific classification."""

    if not isinstance(mode, OrganicSceneMode):
        mode = OrganicSceneMode(mode)
    molecular = _slot_result(document, "molecular")
    packing = _slot_result(document, "packing")
    contacts = _slot_result(document, "crystal_chemistry")
    if molecular is None or packing is None or contacts is None:
        return OrganicSceneData(mode, (), (), (), (), (), (), (), ())

    materialized = PackingMaterializer().materialize(packing, ReferenceCell())
    molecules = materialized.molecules
    highlighted_bond_orbit_ids: tuple[str, ...] = ()
    selected_ligand = None
    resolved_object_id = None
    if mode is OrganicSceneMode.RING:
        rings = tuple(getattr(molecular, "ring_orbits", ()))
        ring = next(
            (item for item in rings if item.ring_orbit_id == selected_object_id),
            rings[0] if selected_object_id is None and rings else None,
        )
        if ring is None:
            return OrganicSceneData(mode, (), (), (), (), (), (), (), ())
        resolved_object_id = ring.ring_orbit_id
        parent_molecules = tuple(
            item
            for item in molecules
            if item.molecule_orbit_id == ring.parent_component_orbit_id
        )
        if not parent_molecules:
            return OrganicSceneData(mode, (), (), (), (), (), (), (), ())
        molecules = (min(parent_molecules, key=lambda item: item.molecule_id),)
        highlighted_bond_orbit_ids = tuple(ring.bond_orbit_ids)
    elif mode is OrganicSceneMode.LINKER:
        precursor = _slot_result(document, "reticular_precursor")
        ligands = tuple(getattr(precursor, "ligand_orbits", ()))
        selected_ligand = next(
            (
                item
                for item in ligands
                if item.ligand_orbit_id == selected_object_id
            ),
            ligands[0] if selected_object_id is None and ligands else None,
        )
        if selected_ligand is None:
            return OrganicSceneData(mode, (), (), (), (), (), (), (), ())
        resolved_object_id = selected_ligand.ligand_orbit_id
        matching = tuple(
            item
            for item in molecules
            if item.molecule_orbit_id == selected_ligand.source_component_orbit_id
        )
        molecules = (min(matching, key=lambda item: item.molecule_id),) if matching else ()
        highlighted_bond_orbit_ids = tuple(selected_ligand.bond_orbit_ids)
    elif mode in {OrganicSceneMode.SBU, OrganicSceneMode.NET}:
        molecules = ()
    elif mode is OrganicSceneMode.SINGLE_MOLECULE and molecules:
        matching = tuple(item for item in molecules if selected_object_id is None
                         or selected_object_id in {item.molecule_id, item.molecule_orbit_id})
        if not matching:
            return OrganicSceneData(mode, (), (), (), (), (), (), (), ())
        molecules = (min(matching, key=lambda item: item.molecule_id),)
        resolved_object_id = molecules[0].molecule_orbit_id

    structure = document.structure
    atoms_by_id = {atom.id: atom for atom in structure.atomic_view().atoms}
    molecule_records: list[MoleculeSceneInstance] = []
    atom_records: list[OrganicAtomSceneInstance] = []
    membership: dict[tuple[str, Translation], str] = {}
    molecule_orbit_by_id: dict[str, str] = {}
    for molecule in molecules:
        refs = tuple(
            ref
            for ref in molecule.atom_refs
            if selected_ligand is None
            or atoms_by_id.get(ref.atom_id) is not None
            and atoms_by_id[ref.atom_id].source_site_id
            in selected_ligand.independent_site_ids
        )
        keys = tuple((ref.atom_id, ref.cell_translation) for ref in refs)
        molecule_records.append(MoleculeSceneInstance(
            molecule.molecule_id,
            molecule.molecule_orbit_id,
            keys,
        ))
        molecule_orbit_by_id[molecule.molecule_id] = molecule.molecule_orbit_id
        for ref in refs:
            atom = atoms_by_id.get(ref.atom_id)
            if atom is None:
                continue
            fractional = tuple(
                float(atom.fractional[axis] + ref.cell_translation[axis])
                for axis in range(3)
            )
            membership[(ref.atom_id, ref.cell_translation)] = molecule.molecule_id
            element = (
                atom.components[0].species.symbol
                if atom.components
                else "X"
            )
            atom_records.append(OrganicAtomSceneInstance(
                atom.id,
                atom.source_site_id,
                element,
                molecule.molecule_id,
                molecule.molecule_orbit_id,
                ref.cell_translation,
                fractional,
                _frac_to_cart(structure, fractional),
            ))

    if mode is OrganicSceneMode.SBU:
        sbu_result = _slot_result(document, "sbu")
        sbus = tuple(getattr(sbu_result, "sbu_orbits", ()))
        selected_sbu = next(
            (
                item
                for item in sbus
                if item.sbu_orbit_id == selected_object_id
            ),
            sbus[0] if selected_object_id is None and sbus else None,
        )
        if selected_sbu is not None and structure.space_group is not None:
            resolved_object_id = selected_sbu.sbu_orbit_id
            context = SymmetryContext.from_definition(
                structure.space_group,
                structure.cell,
            )
            sites_by_id = {site.id: site for site in structure.sites}
            atom_keys: list[tuple[str, Translation]] = []
            for member in selected_sbu.atom_members:
                site = sites_by_id.get(member.independent_site_id)
                if site is None:
                    continue
                source = tuple(
                    Fraction(str(coordinate.value)) for coordinate in site.fractional
                )
                exact = member.periodic_relation.apply_fractional(source, context)
                fractional = tuple(float(value) for value in exact)
                translation = tuple(member.periodic_relation.lattice_translation)
                atom_id = (
                    f"{selected_sbu.sbu_orbit_id}:"
                    f"{member.independent_site_id}:"
                    f"{member.periodic_relation.operation_key}:"
                    f"{translation}"
                )
                atom_keys.append((atom_id, translation))
                element = (
                    member.components[0].species.symbol
                    if member.components
                    else "X"
                )
                atom_records.append(OrganicAtomSceneInstance(
                    atom_id,
                    member.independent_site_id,
                    element,
                    selected_sbu.sbu_orbit_id,
                    selected_sbu.sbu_orbit_id,
                    translation,
                    fractional,
                    _frac_to_cart(structure, fractional),
                ))
            if atom_keys:
                molecule_records.append(MoleculeSceneInstance(
                    selected_sbu.sbu_orbit_id,
                    selected_sbu.sbu_orbit_id,
                    tuple(atom_keys),
                ))

    bond_by_resolved_id = {
        item.resolved_contact_orbit_id: item
        for item in molecular.bond_orbits
    }
    resolved_ids = tuple(sorted(bond_by_resolved_id))
    native_contacts = (
        ContactMaterializer().materialize(
            contacts,
            _contact_region(molecules),
            contact_orbit_ids=resolved_ids,
        )
        if molecules and resolved_ids
        else ()
    )
    bond_records: list[OrganicBondSceneSegment] = []
    for contact in native_contacts:
        first_key = (
            contact.first_atom_ref.atom_id,
            contact.first_atom_ref.cell_translation,
        )
        second_key = (
            contact.second_atom_ref.atom_id,
            contact.second_atom_ref.cell_translation,
        )
        molecule_id = membership.get(first_key)
        if molecule_id is None or membership.get(second_key) != molecule_id:
            continue
        bond = bond_by_resolved_id[contact.resolved_contact_orbit_id]
        if (
            selected_ligand is not None
            and bond.bond_orbit_id not in selected_ligand.bond_orbit_ids
        ):
            continue
        bond_records.append(OrganicBondSceneSegment(
            contact.contact_id,
            contact.resolved_contact_orbit_id,
            bond.bond_orbit_id,
            molecule_id,
            contact.first_atom_ref.atom_id,
            contact.second_atom_ref.atom_id,
            contact.first_atom_ref.cell_translation,
            contact.second_atom_ref.cell_translation,
            float(contact.distance),
        ))

    cell_edges = (
        ()
        if mode in {
            OrganicSceneMode.SINGLE_MOLECULE,
            OrganicSceneMode.RING,
            OrganicSceneMode.SBU,
            OrganicSceneMode.LINKER,
        }
        else _cell_edges(structure, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    )
    contact_records: list[OrganicContactSceneSegment] = []
    intermolecular = _slot_result(document, "intermolecular")
    if mode is OrganicSceneMode.CONTACTS and intermolecular is not None:
        for contact in IntermolecularContactMaterializer().materialize(
            intermolecular,
            ReferenceCell(),
        ):
            first_atom = atoms_by_id.get(contact.first_atom_ref.atom_id)
            if first_atom is None:
                continue
            fractional = tuple(
                float(
                    first_atom.fractional[axis]
                    + contact.first_atom_ref.cell_translation[axis]
                )
                for axis in range(3)
            )
            start = _frac_to_cart(structure, fractional)
            end = tuple(
                float(start[axis] + contact.vector_cartesian[axis])
                for axis in range(3)
            )
            contact_records.append(OrganicContactSceneSegment(
                contact.contact_id,
                contact.intermolecular_contact_orbit_id,
                contact.first_atom_ref.atom_id,
                contact.second_atom_ref.atom_id,
                start,
                end,
                float(contact.distance),
                tuple(
                    item.interpretation_id for item in contact.interpretations
                ),
            ))

    net_node_records: list[OrganicNetNodeSceneInstance] = []
    net_edge_records: list[OrganicNetEdgeSceneSegment] = []
    if mode is OrganicSceneMode.NET and structure.space_group is not None:
        context = SymmetryContext.from_definition(
            structure.space_group,
            structure.cell,
        )
        sites_by_id = {site.id: site for site in structure.sites}
        sbu_result = _slot_result(document, "sbu")
        precursor = _slot_result(document, "reticular_precursor")
        net = _slot_result(document, "reticular_net")
        sbus = {
            item.sbu_orbit_id: item
            for item in getattr(sbu_result, "sbu_orbits", ())
        }
        ligands = {
            item.ligand_orbit_id: item
            for item in getattr(precursor, "ligand_orbits", ())
        }

        def sbu_point(sbu_orbit_id: str | None) -> Point | None:
            sbu = sbus.get(sbu_orbit_id or "")
            points: list[Point] = []
            for member in getattr(sbu, "atom_members", ()):
                site = sites_by_id.get(member.independent_site_id)
                if site is None:
                    continue
                exact = member.periodic_relation.apply_fractional(
                    tuple(
                        Fraction(str(coordinate.value))
                        for coordinate in site.fractional
                    ),
                    context,
                )
                points.append(tuple(float(value) for value in exact))
            if not points:
                return None
            return tuple(
                sum(point[axis] for point in points) / len(points)
                for axis in range(3)
            )

        def ligand_point(ligand_orbit_id: str | None) -> Point | None:
            ligand = ligands.get(ligand_orbit_id or "")
            if ligand is None:
                return None
            molecule = next(
                (
                    item
                    for item in materialized.molecules
                    if item.molecule_orbit_id == ligand.source_component_orbit_id
                ),
                None,
            )
            points: list[Point] = []
            for ref in getattr(molecule, "atom_refs", ()):
                atom = atoms_by_id.get(ref.atom_id)
                if (
                    atom is None
                    or atom.source_site_id not in ligand.independent_site_ids
                ):
                    continue
                points.append(tuple(
                    float(atom.fractional[axis] + ref.cell_translation[axis])
                    for axis in range(3)
                ))
            if not points:
                return None
            return tuple(
                sum(point[axis] for point in points) / len(points)
                for axis in range(3)
            )

        fractional_by_vertex: dict[str, Point] = {}
        for vertex in getattr(net, "vertex_orbits", ()):
            fractional = (
                sbu_point(vertex.source_sbu_orbit_id)
                if vertex.source_sbu_orbit_id is not None
                else ligand_point(vertex.source_ligand_orbit_id)
            )
            if fractional is None:
                continue
            kind = getattr(vertex.kind, "value", str(vertex.kind))
            fractional_by_vertex[vertex.net_vertex_orbit_id] = fractional
            net_node_records.append(OrganicNetNodeSceneInstance(
                vertex.net_vertex_orbit_id,
                kind,
                fractional,
                _frac_to_cart(structure, fractional),
            ))
        for edge in getattr(net, "edge_orbits", ()):
            first = fractional_by_vertex.get(edge.first_vertex_orbit_id)
            second = fractional_by_vertex.get(edge.second_vertex_orbit_id)
            if first is None or second is None:
                continue
            related = edge.periodic_relation.apply_fractional(
                tuple(Fraction(str(value)) for value in second),
                context,
            )
            end_fractional = tuple(float(value) for value in related)
            net_edge_records.append(OrganicNetEdgeSceneSegment(
                edge.net_edge_orbit_id,
                edge.first_vertex_orbit_id,
                edge.second_vertex_orbit_id,
                _frac_to_cart(structure, first),
                _frac_to_cart(structure, end_fractional),
            ))
    return OrganicSceneData(
        mode,
        tuple(molecule_records),
        tuple(atom_records),
        tuple(sorted(bond_records, key=lambda item: item.contact_id)),
        tuple(sorted(contact_records, key=lambda item: item.contact_id)),
        highlighted_bond_orbit_ids,
        tuple(net_node_records),
        tuple(net_edge_records),
        cell_edges,
        resolved_object_id,
    )


__all__ = [
    "MoleculeSceneInstance",
    "OrganicAtomSceneInstance",
    "OrganicBondSceneSegment",
    "OrganicContactSceneSegment",
    "OrganicNetEdgeSceneSegment",
    "OrganicNetNodeSceneInstance",
    "OrganicSceneData",
    "OrganicSceneMode",
    "build_organic_scene",
]
