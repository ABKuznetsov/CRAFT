from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from craft.analysis.hierarchy import HierarchyReport
from craft.core.model import CrystalStructure

if TYPE_CHECKING:
    from craft.core.document import StructureDocument


@dataclass(frozen=True, slots=True)
class StructuralPassport:
    atoms: int
    polyhedra: int | None
    structural_units: int | None
    rigid_blocks: int | None
    connectors: int | None
    complexity_score: float | None
    complexity_stars: int | None
    topology: str
    mean_rigidity_prior: float | None
    predicted_flexibility: str
    dominant_mechanism: str
    nte_mechanism: str


def build_structural_passport(
    structure: CrystalStructure | "StructureDocument",
    hierarchy: HierarchyReport | None = None,
) -> StructuralPassport:
    # Native documents are the production route.  Counts are presentation
    # projections of immutable CrIStMa results; no scientific objects are
    # reconstructed here.
    from craft.core.document import StructureDocument

    if isinstance(structure, StructureDocument):
        document = structure
        view = document.inorganic_presentation()

        def slot_result(name: str) -> object | None:
            return getattr(getattr(document.scientific, name), "result", None)

        units = slot_result("units")
        representation = slot_result("representation")
        polyhedra = (
            len(view.polyhedron_orbits)
            if slot_result("polyhedra") is not None
            else None
        )
        structural_units = (
            len(getattr(units, "unit_orbits", ())) if units is not None else None
        )
        blocks = (
            len(view.structural_blocks)
            if slot_result("blocks") is not None
            else None
        )
        connectors = (
            len(getattr(representation, "connection_orbits", ()))
            if representation is not None
            else None
        )
        known_counts = tuple(
            value
            for value in (
                len(view.atom_orbits),
                polyhedra,
                structural_units,
                blocks,
            )
            if value is not None
        )
        complexity = (
            min(
                1.0,
                sum(math.log1p(value) for value in known_counts)
                / max(7.0 * len(known_counts), 1.0),
            )
            if known_counts
            else None
        )
        topology = (
            ", ".join(sorted({f"{item.rank}D" for item in view.topology_families}))
            if view.topology_families
            else "Not calculated"
        )
        return StructuralPassport(
            atoms=len(view.atom_orbits),
            polyhedra=polyhedra,
            structural_units=structural_units,
            rigid_blocks=blocks,
            connectors=connectors,
            complexity_score=complexity,
            complexity_stars=(
                max(1, min(5, round(complexity * 5)))
                if complexity is not None
                else None
            ),
            topology=topology,
            mean_rigidity_prior=None,
            predicted_flexibility="Not calculated",
            dominant_mechanism="Not calculated",
            nte_mechanism="Not calculated",
        )

    hierarchy = hierarchy or HierarchyReport()
    counts = (
        len(structure.sites),
        len(hierarchy.polyhedra),
        len(hierarchy.structural_units),
        len(hierarchy.blocks),
        len(hierarchy.connectors),
    )
    complexity = min(
        1.0,
        (
            math.log1p(counts[0]) / 7.0
            + math.log1p(counts[1]) / 6.0
            + math.log1p(counts[2] + counts[3]) / 5.0
        )
        / 3.0,
    )
    topology = "Pending periodic-net analysis"
    return StructuralPassport(
        atoms=counts[0],
        polyhedra=counts[1],
        structural_units=counts[2],
        rigid_blocks=counts[3],
        connectors=counts[4],
        complexity_score=complexity,
        complexity_stars=max(1, min(5, round(complexity * 5))),
        topology=topology,
        mean_rigidity_prior=None,
        predicted_flexibility="Not calculated",
        dominant_mechanism="Not calculated",
        nte_mechanism="Not calculated",
    )
