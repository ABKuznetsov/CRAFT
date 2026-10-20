"""CRAFT nomenclature over resolved CrIStMa coordination environments.

These are structural class assignments, not mineral-species identification or
an oxidation-state calculation. No contacts, hulls or periodic ranks are rebuilt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cristma.crystal_chemistry import ContactAnalysisResult, PolyhedronOrbitBuildResult
from typing import TYPE_CHECKING
from cristma.structure import CrystalStructure
from craft.analysis.connectivity_hierarchy import ConnectivityHierarchy
from craft.analysis.native_group_rules import class_rules

if TYPE_CHECKING:
    from craft.analysis.coordination_organization import CentreFeatures
    from craft.analysis.coordination_boundaries import CoordinationBoundary
    from craft.analysis.anion_attachment import AnionAttachment


RULES = class_rules()

RING_OPENING_WARNING = (
    "Graph cycles are ring candidates; a geometric opening enclosed by the selected "
    "polyhedra has not been evaluated."
)


@dataclass(frozen=True, slots=True)
class ClassEnvironment:
    site_id: str
    site_label: str
    shell_orbit_id: str
    polyhedron_orbit_id: str
    coordination_number: int
    geometry: str
    centre_occupancy: float
    status: str
    evidence: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    coordination_boundaries: tuple[CoordinationBoundary, ...] = ()
    coordination_partition: tuple[int, ...] = ()
    coordination_boundary_key: str = ""
    anion_attachment: AnionAttachment | None = None


@dataclass(frozen=True, slots=True)
class RingMotif:
    """A native graph-cycle candidate, independent of an opening assessment."""

    ring_orbit_id: str
    centre_count: int
    vertex_count: int
    coordination_counts: tuple[tuple[int, int], ...]
    multiplicity: int
    unit_image_counts: tuple[tuple[str, int], ...] = ()
    opening_status: str = "not_evaluated"


@dataclass(frozen=True, slots=True)
class PolymerizationAssignment:
    component_id: str
    representation_id: str
    subtype_id: str
    label: str
    rank: int
    status: str
    coordination_numbers: tuple[int, ...]
    ring_sizes: tuple[int, ...]
    centre_unit_ids: tuple[str, ...]
    centre_site_ids: tuple[str, ...]
    source_shell_ids: tuple[str, ...]
    evidence: tuple[str, ...]
    warnings: tuple[str, ...]
    reference: str
    ring_motifs: tuple[RingMotif, ...] = ()
    ring_search_status: str = "not_run"
    ring_search_max_vertices: int = 0
    component_witness: object | None = None
    connectivity_scope: str = "selected_representation"


@dataclass(frozen=True, slots=True)
class ClassSubsystem(ConnectivityHierarchy):
    """Exact native results for the CRAFT-selected class representation."""

    centre_unit_ids: tuple[str, ...]
    supporting_site_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompoundClass:
    family: str
    label: str
    environments: tuple[ClassEnvironment, ...]
    status: str
    reference: str
    warnings: tuple[str, ...] = ()
    subtypes: tuple[PolymerizationAssignment, ...] = ()
    subsystem: ClassSubsystem | None = None

    @property
    def polyhedron_orbit_ids(self) -> frozenset[str]:
        return frozenset(e.polyhedron_orbit_id for e in self.environments)


@dataclass(frozen=True, slots=True)
class InorganicClassification:
    groups: tuple[CompoundClass, ...]
    unassigned_site_ids: tuple[str, ...]
    warnings: tuple[str, ...] = (
        "Assignments describe oxygen coordination in the selected structural model; "
        "formal charges, protonation and mineral species are not determined.",
    )
    method_id: str = "craft.inorganic_classification"
    method_version: str = "11"
    centre_features: tuple[CentreFeatures, ...] = ()
    cation_groups: tuple[CompoundClass, ...] = ()
    polyhedron_sharing: object | None = None
    anion_attachment_analysis: object | None = None


def _symbol(component) -> str:
    species = component.species
    return str(getattr(species, "symbol", getattr(species, "element_symbol", "")))


def needs_outer_shell_evidence(structure: CrystalStructure, contacts: ContactAnalysisResult) -> bool:
    """Request one wider native search only when an oxyanion boundary is unseen."""
    centres = {rule.centre for rule in RULES}
    oxygen_centres = {symbol for request in contacts.grammar.candidate_interactions
                      if request.ligand_elements == ("O",) for symbol in request.centre_elements}
    centres.intersection_update(oxygen_centres)
    eligible = {
        site.id for site in structure.sites
        if any(_symbol(c) in centres and c.occupancy.value > 0 for c in site.components)
    }
    missing_boundary = {
        "crystal_chemistry.shell.candidates_insufficient",
        "crystal_chemistry.shell.search_boundary_not_observed",
    }
    return any(
        shell.center_independent_site_id in eligible
        and any(d.code in missing_boundary for d in shell.diagnostics)
        for shell in contacts.coordination_shell_orbits
    )


def classify_inorganic(
    structure: CrystalStructure,
    contacts: ContactAnalysisResult,
    polyhedra: PolyhedronOrbitBuildResult,
) -> InorganicClassification:
    """Recognise oxygen groups using selected native shells and native faces.

    A four-coordinate centre alone does not establish tetrahedral geometry.
    BO3 is accepted as a three-vertex oxygen group: the native hull intentionally
    has no volume for planar groups, so its INCOMPLETE hull status is not a veto.
    """
    sites = {site.id: site for site in structure.sites}
    shells = {shell.shell_orbit_id: shell for shell in contacts.coordination_shell_orbits}
    incidences = {i.incidence_orbit_id: i for i in contacts.contact_incidence_orbits}
    matches: dict[str, list[ClassEnvironment]] = {rule.family: [] for rule in RULES}
    eligible = {
        site.id for site in structure.sites
        if any(_symbol(c) in {r.centre for r in RULES} and c.occupancy.value > 0 for c in site.components)
    }
    assigned: set[str] = set()
    polyoxo_centres = {rule.centre for rule in RULES if rule.generic}
    for orbit in polyhedra.polyhedron_orbits:
        poly = orbit.representative
        site = sites[poly.source_site_id]
        shell = shells.get(poly.source_shell_orbit_id)
        if shell is None or shell.selected is None or shell.status.value != "resolved":
            continue
        selected = shell.selected
        cn = selected.geometric_CN
        if cn != poly.coordination_number:
            continue
        ligand_ids = {incidences[i].ligand_independent_site_id for i in selected.primary_incidence_ids}
        if not ligand_ids or any(
            {_symbol(c) for c in sites[i].components if c.occupancy.value > 0} != {"O"}
            for i in ligand_ids
        ):
            continue
        tetrahedron = cn == 4 and len(poly.faces) == 4 and all(len(f) == 3 for f in poly.faces) and (poly.volume or 0) > 0
        for rule in RULES:
            components = [c for c in site.components if _symbol(c) == rule.centre and c.occupancy.value > 0]
            if not components or not rule.generic and cn not in rule.coordination_numbers:
                continue
            if rule.generic and not {
                _symbol(c) for c in site.components if c.occupancy.value > 0
            }.issubset(polyoxo_centres):
                # A variable polyoxo signature does not establish that an
                # arbitrary mixed-metal oxide position is a polyanion centre.
                continue
            if rule.generic and (cn < 4 or not poly.faces or not (poly.volume or 0) > 0):
                continue
            if rule.generic and any(r.centre == rule.centre and cn in r.coordination_numbers for r in RULES):
                continue
            if cn == 4 and not tetrahedron:
                continue
            occupancy = math.fsum(c.occupancy.value for c in components)
            warnings = []
            if rule.generic:
                warnings.append("Variable polyoxo signature: oxygen coordination is observed; charge and specific polyoxometalate identity are not established.")
            if len([c for c in site.components if c.occupancy.value > 0]) > 1 or not math.isclose(occupancy, 1):
                warnings.append("Mixed or partially occupied centre; assignment applies to this component.")
            if any(not math.isclose(math.fsum(c.occupancy.value for c in sites[i].components), 1) for i in ligand_ids):
                warnings.append("Partially occupied oxygen positions; connectivity is conditional on the average model.")
            geometry = "tetrahedron" if tetrahedron else "three-vertex group" if cn == 3 else f"CN {cn} polyhedron"
            evidence = (
                f"{site.label}: selected {rule.centre}O{cn} shell; oxygen-only ligand positions.",
                f"Native geometry: {geometry}; shell {shell.shell_orbit_id}.",
                f"Native group signature: {rule.reference}.",
            )
            matches[rule.family].append(ClassEnvironment(
                site.id, site.label, shell.shell_orbit_id, orbit.polyhedron_orbit_id,
                cn, geometry, occupancy, "conditional" if warnings else "supported",
                evidence, tuple(warnings),
            ))
            assigned.add(site.id)
    groups = tuple(
        CompoundClass(
            rule.family, rule.label, tuple(matches[rule.family]),
            "conditional" if any(e.warnings for e in matches[rule.family]) else "supported",
            rule.reference,
            tuple(dict.fromkeys(w for e in matches[rule.family] for w in e.warnings)),
        )
        for rule in RULES if matches[rule.family]
    )
    return InorganicClassification(groups, tuple(sorted(eligible - assigned)))
