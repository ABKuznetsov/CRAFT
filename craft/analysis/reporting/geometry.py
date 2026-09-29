from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from craft.analysis.hierarchy import HierarchyReport
from craft.analysis.reporting.model import (
    Availability,
    Provenance,
    ReportCell,
    ReportColumn,
    ReportRow,
    ReportTable,
)
from craft.core.model import CrystalStructure
from craft.core.measurement import MissingState, parse_cif_number

if TYPE_CHECKING:
    from craft.core.document import StructureDocument


@dataclass(frozen=True, slots=True)
class GeometrySettings:
    distance_tolerance: float = 0.001
    angle_tolerance: float = 0.01


def _text(value: str, provenance: Provenance = Provenance.CALCULATED) -> ReportCell:
    return ReportCell(value, value, provenance)


def _number(value: float, digits: int, method_id: str) -> ReportCell:
    return ReportCell(value, f"{value:.{digits}f}", Provenance.CALCULATED, method_id=method_id)


def _loop_value(loop, row: tuple[str, ...], tag: str, default: str = "") -> str:
    try:
        return row[loop.tags.index(tag)]
    except ValueError:
        return default


def _reported_bond_rows(structure: CrystalStructure) -> tuple[list[ReportRow], set[tuple[str, ...]]]:
    rows: list[ReportRow] = []
    keys: set[tuple[str, ...]] = set()
    required = "_geom_bond_atom_site_label_1"
    for loop in structure.source_data.loops:
        if required not in loop.tags or "_geom_bond_distance" not in loop.tags:
            continue
        for index, source_row in enumerate(loop.rows, start=1):
            first = _loop_value(loop, source_row, required)
            second = _loop_value(loop, source_row, "_geom_bond_atom_site_label_2")
            sym_first = _loop_value(loop, source_row, "_geom_bond_site_symmetry_1", ".") or "."
            sym_second = _loop_value(loop, source_row, "_geom_bond_site_symmetry_2", ".") or "."
            token = _loop_value(loop, source_row, "_geom_bond_distance")
            measured = parse_cif_number(
                token,
                unit="Å",
                source_name="_geom_bond_distance",
            )
            if measured.state is not MissingState.PRESENT:
                continue
            publication = _loop_value(loop, source_row, "_geom_bond_publ_flag", "yes").lower()
            key = (first, second, sym_first, sym_second)
            keys.add(key)
            rows.append(
                ReportRow(
                    id=f"bond:reported:{index}:{first}:{second}",
                    cells={
                        "center": _text(first, Provenance.REPORTED),
                        "ligand": _text(second, Provenance.REPORTED),
                        "distance": ReportCell(
                            measured,
                            measured.formatted(),
                            Provenance.REPORTED,
                            source_name=measured.source_name,
                        ),
                        "multiplicity": ReportCell(1, "1", Provenance.REPORTED),
                        "symmetry": _text(
                            f"{sym_first} / {sym_second}", Provenance.REPORTED
                        ),
                        "polyhedron": _text("—", Provenance.UNAVAILABLE),
                    },
                    include_in_publication=publication in {"yes", "y", "1", "true"},
                    object_refs=(f"atom:{first}", f"atom:{second}"),
                )
            )
    return rows, keys


def build_bond_table(
    structure: CrystalStructure,
    hierarchy: HierarchyReport,
    settings: GeometrySettings,
) -> ReportTable:
    # Legacy hierarchy objects are presentation projections, not an
    # authoritative geometry source.  Without a native CrIStMa result this
    # table may only reproduce geometry explicitly reported by the input file.
    rows, _reported_keys = _reported_bond_rows(structure)
    return ReportTable(
        id="bond_lengths",
        title="Bond lengths",
        columns=(
            ReportColumn("center", "Centre"),
            ReportColumn("ligand", "Ligand"),
            ReportColumn("distance", "Distance", "Å"),
            ReportColumn("multiplicity", "Multiplicity"),
            ReportColumn("symmetry", "Symmetry"),
            ReportColumn("polyhedron", "Polyhedron"),
        ),
        rows=tuple(rows),
        availability=(
            Availability.AVAILABLE if rows else Availability.UNAVAILABLE
        ),
        unavailable_reason=(
            "No reported CIF bond geometry is available."
            if not rows
            else ""
        ),
        method="Bond geometry reproduced from the source file without inference.",
    )


def _native_symmetry_description(atom: object, translation: tuple[int, int, int]) -> str:
    image = getattr(atom, "representative_image", None)
    operation_id = str(getattr(image, "operation_id", "operation unavailable"))
    normalization = tuple(
        int(value)
        for value in getattr(image, "normalization_translation", (0, 0, 0))
    )
    total = tuple(
        normalization[index] + int(translation[index]) for index in range(3)
    )
    return f"{operation_id} + [{total[0]} {total[1]} {total[2]}]"


def build_native_bond_table(
    document: StructureDocument,
    settings: GeometrySettings,
) -> ReportTable:
    """Project exact CrIStMa polyhedron incidences into report rows.

    This function deliberately performs no neighbour search, distance
    calculation, symmetry grouping, or multiplicity inference.  It only
    formats immutable CrIStMa results for CRAFT's report workspace.
    """

    # A native report must remain a pure presentation of the immutable
    # CrIStMa result.  Reported CIF loops belong to the legacy projection and
    # are intentionally not merged here: doing so would reintroduce a second
    # scientific/source-data route beside the canonical structure.
    rows: list[ReportRow] = []
    slot = document.scientific.polyhedra
    result = getattr(slot, "result", None)
    if result is None:
        return ReportTable(
            id="bond_lengths",
            title="Bond lengths",
            columns=(
                ReportColumn("center", "Centre"),
                ReportColumn("ligand", "Ligand"),
                ReportColumn("distance", "Distance", "Å"),
                ReportColumn("multiplicity", "Multiplicity"),
                ReportColumn("symmetry", "Symmetry"),
                ReportColumn("polyhedron", "Polyhedron"),
            ),
            rows=tuple(rows),
            availability=(Availability.AVAILABLE if rows else Availability.UNAVAILABLE),
            unavailable_reason=(
                "CrIStMa polyhedron geometry is not available yet."
                if not rows
                else ""
            ),
            method="CrIStMa polyhedron geometry is unavailable.",
        )

    sites_by_id = {site.id: site for site in document.structure.sites}
    atoms_by_id = {atom.id: atom for atom in document.structure.atomic_view().atoms}
    for orbit in result.polyhedron_orbits:
        polyhedron = orbit.representative
        centre_site = sites_by_id.get(polyhedron.source_site_id)
        centre_label = (
            centre_site.label if centre_site is not None else polyhedron.source_site_id
        )
        for vertex in polyhedron.vertices:
            ligand_atom = atoms_by_id.get(vertex.atom_ref.atom_id)
            ligand_site = (
                sites_by_id.get(ligand_atom.source_site_id)
                if ligand_atom is not None
                else None
            )
            ligand_label = (
                ligand_site.label if ligand_site is not None else vertex.atom_ref.atom_id
            )
            symmetry = (
                _native_symmetry_description(
                    ligand_atom,
                    tuple(int(value) for value in vertex.atom_ref.cell_translation),
                )
                if ligand_atom is not None
                else "operation unavailable"
            )
            row_id = (
                f"bond:native:{orbit.polyhedron_orbit_id}:"
                f"{vertex.incidence_orbit_id}"
            )
            rows.append(
                ReportRow(
                    id=row_id,
                    cells={
                        "center": _text(centre_label),
                        "ligand": _text(ligand_label),
                        "distance": _number(
                            float(vertex.distance),
                            4,
                            "cristma.polyhedron-vertex-distance",
                        ),
                        "multiplicity": ReportCell(
                            None,
                            "—",
                            Provenance.UNAVAILABLE,
                            warning="Multiplicity is not published by this result contract.",
                        ),
                        "symmetry": _text(symmetry),
                        "polyhedron": _text(orbit.polyhedron_orbit_id),
                    },
                    object_refs=(
                        orbit.polyhedron_orbit_id,
                        vertex.incidence_orbit_id,
                        vertex.resolved_contact_orbit_id,
                        polyhedron.source_site_id,
                        vertex.atom_ref.atom_id,
                    ),
                )
            )

    return ReportTable(
        id="bond_lengths",
        title="Bond lengths",
        columns=(
            ReportColumn("center", "Centre"),
            ReportColumn("ligand", "Ligand"),
            ReportColumn("distance", "Distance", "Å"),
            ReportColumn("multiplicity", "Multiplicity"),
            ReportColumn("symmetry", "Symmetry"),
            ReportColumn("polyhedron", "Polyhedron"),
        ),
        rows=tuple(rows),
        availability=Availability.AVAILABLE if rows else Availability.UNAVAILABLE,
        unavailable_reason=(
            "No CrIStMa polyhedron bond geometry is available."
            if not rows
            else ""
        ),
        method=(
            "Calculated rows are direct projections of CrIStMa polyhedron "
            "vertex distances and exact symmetry identifiers."
        ),
    )


def build_native_angle_table() -> ReportTable:
    """Return an honest unavailable table until CrIStMa publishes angles."""

    return ReportTable(
        id="bond_angles",
        title="Bond angles",
        columns=(
            ReportColumn("first", "Atom 1"),
            ReportColumn("apex", "Apex"),
            ReportColumn("second", "Atom 2"),
            ReportColumn("angle", "Angle", "°"),
            ReportColumn("kind", "Kind"),
            ReportColumn("symmetry", "Symmetry"),
        ),
        rows=(),
        availability=Availability.UNAVAILABLE,
        unavailable_reason="CrIStMa does not publish bond-angle rows yet.",
        method="No CRAFT-side angle reconstruction is performed.",
    )


def build_angle_table(
    structure: CrystalStructure,
    hierarchy: HierarchyReport,
    settings: GeometrySettings,
) -> ReportTable:
    rows: list[ReportRow] = []
    for loop in structure.source_data.loops:
        if "_geom_angle_atom_site_label_1" not in loop.tags or "_geom_angle" not in loop.tags:
            continue
        for index, source_row in enumerate(loop.rows, start=1):
            labels = tuple(
                _loop_value(loop, source_row, f"_geom_angle_atom_site_label_{position}")
                for position in (1, 2, 3)
            )
            symmetries = tuple(
                _loop_value(loop, source_row, f"_geom_angle_site_symmetry_{position}", ".")
                or "."
                for position in (1, 2, 3)
            )
            measured = parse_cif_number(
                _loop_value(loop, source_row, "_geom_angle"),
                unit="°",
                source_name="_geom_angle",
            )
            if measured.state is not MissingState.PRESENT:
                continue
            publication = _loop_value(loop, source_row, "_geom_angle_publ_flag", "yes").lower()
            rows.append(
                ReportRow(
                    id=f"angle:reported:{index}:{':'.join(labels)}",
                    cells={
                        "first": _text(labels[0], Provenance.REPORTED),
                        "apex": _text(labels[1], Provenance.REPORTED),
                        "second": _text(labels[2], Provenance.REPORTED),
                        "angle": ReportCell(
                            measured,
                            measured.formatted(),
                            Provenance.REPORTED,
                            source_name=measured.source_name,
                        ),
                        "kind": _text("reported", Provenance.REPORTED),
                        "symmetry": _text(" / ".join(symmetries), Provenance.REPORTED),
                    },
                    include_in_publication=publication in {"yes", "y", "1", "true"},
                    object_refs=tuple(f"atom:{label}" for label in labels),
                )
            )
    return ReportTable(
        id="bond_angles",
        title="Bond angles",
        columns=(
            ReportColumn("first", "Atom 1"),
            ReportColumn("apex", "Apex"),
            ReportColumn("second", "Atom 2"),
            ReportColumn("angle", "Angle", "°"),
            ReportColumn("kind", "Kind"),
            ReportColumn("symmetry", "Symmetry"),
        ),
        rows=tuple(rows),
        availability=(
            Availability.AVAILABLE if rows else Availability.UNAVAILABLE
        ),
        unavailable_reason=(
            "No reported CIF angle geometry is available."
            if not rows
            else ""
        ),
        method="Angle geometry reproduced from the source file without inference.",
    )
