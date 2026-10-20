"""Visibility selections over installed native display records."""

from __future__ import annotations

from craft.core.visualization import VisibilityState
from craft.presentation.inorganic import InorganicPresentation
from craft.presentation.inorganic_scene import InorganicSceneData
from craft.presentation.organic_scene import OrganicSceneData


def native_isolation_state(
    scene: InorganicSceneData | OrganicSceneData,
    presentation: object,
    kind: str,
    object_id: str,
) -> VisibilityState | None:
    """Return a detached selection, or None for an unavailable object."""
    inorganic = isinstance(scene, InorganicSceneData)
    atom_sites = {atom.source_site_id for atom in scene.atoms}
    contacts = scene.contacts if inorganic else (
        *scene.covalent_bonds, *scene.intermolecular_contacts,
    )
    contact_ids = {contact.contact_orbit_id for contact in contacts}
    polyhedron_ids = set()
    block_ids = set()
    if inorganic and isinstance(presentation, InorganicPresentation):
        contact_ids.update(row.contact_orbit_id for row in presentation.contact_orbits)
        polyhedron_ids = {row.polyhedron_orbit_id for row in presentation.polyhedron_orbits}
        block_ids = {row.block_id for row in presentation.structural_blocks}

    state = VisibilityState()
    state.hidden_contact_orbit_ids = contact_ids
    state.hidden_polyhedron_orbit_ids = polyhedron_ids
    state.hidden_block_ids = block_ids
    if kind == "atom" and object_id in atom_sites:
        state.hidden_atom_orbit_ids = atom_sites - {object_id}
    elif kind in {"bond", "contact"} and object_id in contact_ids:
        state.hidden_contact_orbit_ids = contact_ids - {object_id}
    elif kind == "polyhedron" and object_id in polyhedron_ids:
        row = presentation.polyhedron_orbit(object_id)
        kept_sites = {row.source_site_id, *(site for site, _count in row.ligand_site_counts)}
        state.hidden_atom_orbit_ids = atom_sites - kept_sites
        state.hidden_polyhedron_orbit_ids = polyhedron_ids - {object_id}
    elif kind == "block" and object_id in block_ids:
        row = presentation.block(object_id)
        kept_atoms = row.internal_atom_ids | row.connector_atom_ids
        state.hidden_atom_instance_keys = {
            (atom.atom_id, atom.cell_translation)
            for atom in scene.atoms if atom.atom_id not in kept_atoms
        }
        state.hidden_block_ids = block_ids - {object_id}
        state.shown_block_ids = {object_id}
        state.block_auto_hidden_atom_ids[object_id] = row.internal_atom_ids
        state.block_auto_hidden_polyhedron_orbit_ids[object_id] = frozenset(row.polyhedron_orbit_ids)
    else:
        return None
    return state
