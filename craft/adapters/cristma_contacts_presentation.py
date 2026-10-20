"""Calculation-free CRAFT projection of CrIStMa contact-orbit results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cristma.chemistry import (
    GrammarOperation,
    InteractionLayer,
    InteractionPriority,
)
from cristma.crystal_chemistry import (
    ContactAnalysisResult,
    OrientationMode,
    ReferenceCell,
    ResolutionStatus,
    ShellRole,
)

Translation = tuple[int, int, int]
_ZERO: Translation = (0, 0, 0)


class ContactVisibilityClass(StrEnum):
    """Display grouping from selected shells or undirected-network priority."""

    PRIMARY = "primary"
    SECONDARY = "secondary"


@dataclass(frozen=True, slots=True)
class ContactOrbitRow:
    contact_orbit_id: str
    representative_contact_id: str
    interaction_type: GrammarOperation
    interaction_layer: InteractionLayer
    classification: ContactVisibilityClass
    distance_min: float
    distance_max: float
    instance_count: int
    initially_visible: bool
    evidence: object
    provenance: object


@dataclass(frozen=True, slots=True)
class ContactSceneInstance:
    contact_id: str
    contact_orbit_id: str
    first_atom_id: str
    second_atom_id: str
    cell_translation: Translation
    distance: float
    interaction_type: GrammarOperation
    interaction_layer: InteractionLayer
    classification: ContactVisibilityClass
    evidence: object
    provenance: object


@dataclass(frozen=True, slots=True)
class ContactPresentation:
    scientific_result: ContactAnalysisResult
    scientific_status: ResolutionStatus
    rows: tuple[ContactOrbitRow, ...]
    instances: tuple[ContactSceneInstance, ...]
    diagnostics: tuple[object, ...]


def _is_primary(contact, selected_alternatives) -> bool:
    # Materialized memberships include unselected shell alternatives. Grammar
    # priority identifies a candidate interaction, not a resolved shell bond.
    # Undirected networks have no coordination shells and retain their native
    # grammar priority instead.
    return any(
        item.role is ShellRole.PRIMARY
        and selected_alternatives.get(item.shell_orbit_id) == item.alternative_id
        for item in contact.shell_memberships
    ) or any(
        item.grammar_priority is InteractionPriority.PRIMARY
        and item.orientation_mode is OrientationMode.UNDIRECTED
        for item in contact.interpretations
    )


def project_contacts(resolution: ContactAnalysisResult) -> ContactPresentation:
    """Expose existing CrIStMa fields without discovering or classifying contacts."""

    rows: list[ContactOrbitRow] = []
    instances: list[ContactSceneInstance] = []
    geometry_by_id = {
        item.geometry_orbit_id: item
        for item in resolution.pair_table.contact_orbits
    }
    contacts_by_orbit: dict[str, list[object]] = {}
    selected_alternatives = {
        shell.shell_orbit_id: shell.selected_alternative
        for shell in resolution.coordination_shell_orbits if shell.selected is not None
    }
    materialized = resolution.materialize_contacts(ReferenceCell())
    for contact in materialized:
        contacts_by_orbit.setdefault(contact.resolved_contact_orbit_id, []).append(contact)
    for orbit in resolution.contact_orbits:
        orbit_contacts = tuple(contacts_by_orbit.get(orbit.resolved_contact_orbit_id, ()))
        if not orbit_contacts:
            continue
        representative = orbit_contacts[0]
        interpretation = representative.interpretations[0]
        geometry = geometry_by_id[orbit.geometry_orbit_id]
        classification = (
            ContactVisibilityClass.PRIMARY
            if any(_is_primary(item, selected_alternatives) for item in orbit_contacts)
            else ContactVisibilityClass.SECONDARY
        )
        rows.append(ContactOrbitRow(
            contact_orbit_id=orbit.resolved_contact_orbit_id,
            representative_contact_id=representative.contact_id,
            interaction_type=interpretation.interaction_type,
            interaction_layer=interpretation.interaction_layer,
            classification=classification,
            distance_min=geometry.representative_distance,
            distance_max=geometry.representative_distance,
            instance_count=len(orbit_contacts),
            initially_visible=classification is ContactVisibilityClass.PRIMARY,
            evidence=interpretation.evidence,
            provenance=orbit.provenance,
        ))
        for contact in orbit_contacts:
            first = contact.first_atom_ref
            second = contact.second_atom_ref
            cell_translation = tuple(
                second.cell_translation[axis] - first.cell_translation[axis]
                for axis in range(3)
            )
            instances.append(ContactSceneInstance(
                contact_id=contact.contact_id,
                contact_orbit_id=orbit.resolved_contact_orbit_id,
                first_atom_id=first.atom_id,
                second_atom_id=second.atom_id,
                cell_translation=cell_translation,
                distance=contact.distance,
                interaction_type=contact.interpretations[0].interaction_type,
                interaction_layer=contact.interpretations[0].interaction_layer,
                classification=classification,
                evidence=contact.interpretations[0].evidence,
                provenance=contact.provenance,
            ))
    return ContactPresentation(
        scientific_result=resolution,
        scientific_status=resolution.status,
        rows=tuple(rows),
        instances=tuple(instances),
        diagnostics=tuple(resolution.diagnostics),
    )


__all__ = [
    "ContactOrbitRow",
    "ContactPresentation",
    "ContactSceneInstance",
    "ContactVisibilityClass",
    "project_contacts",
]
