"""Build calculation-free CRAFT views from immutable CRiStMa results."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

from cristma.chemistry import InteractionLayer

from craft.adapters.cristma_contacts_presentation import project_contacts
from craft.core.chemistry import ELEMENT_COLORS
from craft.core.scientific_cache import INORGANIC_RESULT_SLOTS
from craft.presentation.inorganic import (
    AtomOrbitView,
    ContactOrbitView,
    InorganicPresentation,
    PolyhedronOrbitView,
    RingOrbitView,
    StructuralBlockView,
    TopologyFamilyView,
)

if TYPE_CHECKING:
    from cristma.structure import IndependentSite

    from craft.core.document import StructureDocument


def _slot_result(slot: object | None) -> object | None:
    return getattr(slot, "result", None)


def _component_symbol(component: object) -> str:
    species = getattr(component, "species", "")
    return str(getattr(species, "symbol", species))


def _component_occupancy(component: object) -> float:
    occupancy = getattr(component, "occupancy", 0.0)
    value = getattr(occupancy, "value", occupancy)
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if math.isfinite(result) and result > 0.0 else 0.0


def _composition_label(site: "IndependentSite") -> str:
    parts = tuple(
        (_component_symbol(component), _component_occupancy(component))
        for component in site.components
        if _component_occupancy(component) > 0.0
    )
    if not parts:
        return "Vacancy"
    if len(parts) == 1 and math.isclose(parts[0][1], 1.0):
        return parts[0][0]
    return "/".join(
        f"{symbol}{occupancy:g}" if not math.isclose(occupancy, 1.0) else symbol
        for symbol, occupancy in parts
    )


def _site_color(site: "IndependentSite") -> str:
    weighted = tuple(
        (
            ELEMENT_COLORS.get(_component_symbol(component), "#aab4c0"),
            _component_occupancy(component),
        )
        for component in site.components
        if _component_occupancy(component) > 0.0
    )
    total = math.fsum(weight for _color, weight in weighted)
    if total <= 0.0:
        return "#aab4c0"
    channels = tuple(
        round(
            math.fsum(int(color[offset : offset + 2], 16) * weight for color, weight in weighted)
            / total
        )
        for offset in (1, 3, 5)
    )
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def _build_atom_orbits(structure) -> tuple[AtomOrbitView, ...]:
    expanded_by_site: dict[str, list[str]] = defaultdict(list)
    for atom in structure.atomic_view().atoms:
        expanded_by_site[atom.source_site_id].append(atom.id)
    return tuple(
        AtomOrbitView(
            source_site_id=site.id,
            label=site.label,
            composition_label=_composition_label(site),
            atom_ids=tuple(expanded_by_site.get(site.id, ())),
            default_color=_site_color(site),
        )
        for site in structure.sites
    )


def _build_contact_orbits(structure, resolution, presentation) -> tuple[ContactOrbitView, ...]:
    if resolution is None:
        return ()
    if presentation is None or presentation.scientific_result is not resolution:
        presentation = project_contacts(resolution)
    pair_geometry = {
        item.geometry_orbit_id: item for item in resolution.pair_table.contact_orbits
    }
    geometry_by_id = {
        orbit.resolved_contact_orbit_id: pair_geometry[orbit.geometry_orbit_id]
        for orbit in resolution.contact_orbits
    }
    sites_by_id = {site.id: site for site in structure.sites}
    rows: list[ContactOrbitView] = []
    for row in presentation.rows:
        geometry = geometry_by_id[row.contact_orbit_id]
        first_site = sites_by_id.get(geometry.first_independent_site_id)
        second_site = sites_by_id.get(geometry.second_independent_site_id)
        first_label = _composition_label(first_site) if first_site is not None else "?"
        second_label = _composition_label(second_site) if second_site is not None else "?"
        rows.append(ContactOrbitView(
            contact_orbit_id=row.contact_orbit_id,
            label=row.interaction_type.value.replace("_", " "),
            classification=row.classification.value,
            interaction_layer=row.interaction_layer.value,
            instance_count=row.instance_count,
            distance_min=row.distance_min,
            distance_max=row.distance_max,
            initially_visible=row.initially_visible,
            pair_label=f"{first_label}–{second_label}",
        ))
    return tuple(rows)


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _build_polyhedron_orbits(structure, result, contacts=None, units=None) -> tuple[PolyhedronOrbitView, ...]:
    if result is None:
        return ()
    sites = {site.id: site for site in structure.sites}
    shells = {s.shell_orbit_id: s for s in getattr(contacts, "coordination_shell_orbits", ())}
    incidences = {i.incidence_orbit_id: i for i in getattr(contacts, "contact_incidence_orbits", ())}
    units_by_shell = {u.source_shell_orbit_id: u for u in getattr(units, "unit_orbits", ()) if u.source_shell_orbit_id}
    rows: list[PolyhedronOrbitView] = []
    for orbit in result.polyhedron_orbits:
        representative = next(
            item
            for item in orbit.polyhedra
            if item.polyhedron_id == orbit.representative_polyhedron_id
        )
        site = sites[representative.source_site_id]
        ligand_label = "".join(
            f"{symbol}{count:g}" for symbol, count in representative.ligand_composition
        )
        shell = shells.get(representative.source_shell_orbit_id)
        ligand_counts = Counter()
        if shell is not None and shell.selected is not None:
            for incidence_id in shell.selected.primary_incidence_ids:
                incidence = incidences[incidence_id]
                ligand_counts[incidence.ligand_independent_site_id] += incidence.incidence_multiplicity_per_center
        unit = units_by_shell.get(representative.source_shell_orbit_id)
        geometry = f"CN {representative.coordination_number}"
        if (representative.coordination_number == 4 and len(representative.faces) == 4
                and all(len(face) == 3 for face in representative.faces) and (representative.volume or 0) > 0):
            geometry = "tetrahedron"
        elif (representative.coordination_number == 3 and unit is not None
              and unit.representative_geometry.kind.value == "planar_polygon"):
            geometry = "triangle"
        rows.append(PolyhedronOrbitView(
            polyhedron_orbit_id=orbit.polyhedron_orbit_id,
            representative_polyhedron_id=orbit.representative_polyhedron_id,
            label=f"{site.label} — {_composition_label(site)}{ligand_label}",
            polyhedron_ids=tuple(item.polyhedron_id for item in orbit.polyhedra),
            coordination_number=representative.coordination_number,
            face_signature=representative.face_signature,
            default_color=_site_color(site),
            source_site_id=site.id,
            source_shell_id=representative.source_shell_orbit_id or "",
            ligand_site_counts=tuple(sorted(ligand_counts.items())),
            geometry_label=geometry,
            interaction_role=("interstitial" if unit is not None and InteractionLayer.INTERSTITIAL in unit.interaction_layers else ""),
        ))
    return tuple(rows)


def _build_structural_blocks(structure, representation, result) -> tuple[StructuralBlockView, ...]:
    if representation is None or result is None:
        return ()
    units = {item.unit_orbit_id: item for item in representation.unit_orbits}
    connections = {
        item.connection_orbit_id: item for item in representation.connection_orbits
    }
    rows: list[StructuralBlockView] = []
    for block in result.blocks:
        atom_ids = frozenset(
            ref.atom_id
            for unit_id in block.unit_orbit_ids
            for ref in units[unit_id].constituent_site_refs
        )
        # A StructuralConnectionOrbit names both scientific endpoints in
        # connector_site_refs.  For display, however, only explicit atomic
        # structural units are bridge atoms; the centre of the neighbouring
        # coordination unit remains internal to the block.
        connector_unit_ids = frozenset(
            unit_id
            for connection_id in block.connection_orbit_ids
            for unit_id in (
                connections[connection_id].first_unit_orbit_id,
                connections[connection_id].second_unit_orbit_id,
            )
            if int(block.rank) > 0
            and unit_id in units
            and _enum_value(units[unit_id].kind) == "atom"
        )
        connector_atoms = frozenset(
            ref.atom_id
            for unit_id in connector_unit_ids
            for ref in units[unit_id].constituent_site_refs
            if ref.atom_id in atom_ids
        )
        classification = _enum_value(block.classification)
        rows.append(StructuralBlockView(
            block_id=block.block_id,
            label=f"{classification.replace('_', ' ')} · {block.rank}D",
            classification=classification,
            rank=block.rank,
            unit_orbit_ids=tuple(block.unit_orbit_ids),
            connection_orbit_ids=tuple(block.connection_orbit_ids),
            internal_atom_ids=atom_ids - connector_atoms,
            connector_atom_ids=connector_atoms,
            polyhedron_orbit_ids=tuple(dict.fromkeys(
                units[unit_id].source_polyhedron_orbit_id
                for unit_id in block.unit_orbit_ids
                if units[unit_id].source_polyhedron_orbit_id is not None
            )),
        ))
    return tuple(rows)


def _build_rings(result) -> tuple[RingOrbitView, ...]:
    if result is None:
        return ()
    return tuple(
        RingOrbitView(
            ring_orbit_id=ring.ring_orbit_id,
            parent_block_id=ring.parent_block_id,
            label=f"{len(ring.unit_orbit_refs)}-membered graph cycle · opening unverified",
            size=len(ring.unit_orbit_refs),
            scope=_enum_value(ring.scope),
            multiplicity=ring.multiplicity_in_reference_cell,
        )
        for ring in result.ring_orbits
    )


def _build_topology_families(connectivity, blocks) -> tuple[TopologyFamilyView, ...]:
    if connectivity is None:
        return ()
    block_rows = tuple(blocks)
    return tuple(
        TopologyFamilyView(
            topology_id=component.component_id,
            label=f"Periodic component · {component.rank}D",
            rank=component.rank,
            block_ids=tuple(
                block.block_id
                for block in block_rows
                if frozenset(block.unit_orbit_ids) == frozenset(component.unit_orbit_ids)
            ),
        )
        for component in connectivity.components
    )


def build_inorganic_presentation(document: "StructureDocument") -> InorganicPresentation:
    """Project the currently installed native results without scientific inference."""

    structure = document.structure
    contacts = _slot_result(document.scientific.crystal_chemistry)
    polyhedra = _slot_result(document.scientific.polyhedra)
    representation = _slot_result(document.scientific.representation)
    blocks_result = _slot_result(document.scientific.blocks)
    connectivity = _slot_result(document.scientific.connectivity)
    rings = _slot_result(document.scientific.rings)
    classification = _slot_result(document.scientific.inorganic_classification)
    units = _slot_result(document.scientific.units)
    block_rows = _build_structural_blocks(structure, representation, blocks_result)
    return InorganicPresentation(
        structure_id=structure.id or document.id,
        structure_name=structure.name,
        atom_orbits=_build_atom_orbits(structure),
        contact_orbits=_build_contact_orbits(structure, contacts, document.contact_presentation),
        polyhedron_orbits=_build_polyhedron_orbits(structure, polyhedra, contacts, units),
        structural_blocks=block_rows,
        rings=_build_rings(rings),
        topology_families=_build_topology_families(connectivity, block_rows),
        diagnostics=document.scientific.diagnostics(INORGANIC_RESULT_SLOTS),
        stage=document.analysis_stage,
        compound_classes=classification.groups if classification is not None else (),
        cation_groups=classification.cation_groups if classification is not None else (),
    )


__all__ = ["build_inorganic_presentation"]
