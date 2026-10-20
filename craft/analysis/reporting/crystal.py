from __future__ import annotations

import math

from craft.analysis.reporting.model import (
    Availability,
    Provenance,
    ReportCell,
    ReportColumn,
    ReportRow,
    ReportTable,
)
from craft.core.measurement import MeasuredValue, MissingState, parse_cif_number
from craft.core.model import CrystalStructure
from craft.analysis.reporting.experiment import build_refinement_table


def _reported_cell(value: MeasuredValue) -> ReportCell:
    return ReportCell(
        value=value,
        display=value.formatted(),
        provenance=Provenance.REPORTED,
        source_name=value.source_name,
    )


def _calculated_cell(value: float | int | str, display: str | None = None, method_id: str = "") -> ReportCell:
    return ReportCell(
        value=value,
        display=str(value) if display is None else display,
        provenance=Provenance.CALCULATED,
        method_id=method_id,
    )


def _source_scalar_cell(structure: CrystalStructure, tag: str) -> ReportCell | None:
    raw = structure.source_data.raw(tag)
    if raw is None:
        return None
    return ReportCell(raw, raw, Provenance.REPORTED, source_name=tag)


def build_crystal_data_table(structure: CrystalStructure) -> ReportTable:
    rows: list[ReportRow] = []

    scalar_rows = (
        ("formula", "Chemical formula", "_chemical_formula_sum"),
        ("space_group", "Space group", "_space_group_name_H-M_alt"),
        ("crystal_system", "Crystal system", "_space_group_crystal_system"),
        ("hall", "Hall symbol", "_space_group_name_Hall"),
        ("z", "Z", "_cell_formula_units_Z"),
        ("temperature", "Temperature", "_diffrn_ambient_temperature"),
        ("pressure", "Pressure", "_diffrn_ambient_pressure"),
    )
    for row_id, title, tag in scalar_rows:
        cell = _source_scalar_cell(structure, tag)
        if cell is None and row_id == "space_group":
            cell = _source_scalar_cell(structure, "_symmetry_space_group_name_H-M")
        if cell is not None:
            rows.append(
                ReportRow(
                    id=f"crystal:{row_id}",
                    cells={"parameter": _calculated_cell(title), "value": cell},
                )
            )

    cell_parameters = (
        ("a", "a", "_cell_length_a", "Å", structure.cell.a),
        ("b", "b", "_cell_length_b", "Å", structure.cell.b),
        ("c", "c", "_cell_length_c", "Å", structure.cell.c),
        ("alpha", "α", "_cell_angle_alpha", "°", structure.cell.alpha),
        ("beta", "β", "_cell_angle_beta", "°", structure.cell.beta),
        ("gamma", "γ", "_cell_angle_gamma", "°", structure.cell.gamma),
    )
    for row_id, title, tag, unit, fallback in cell_parameters:
        measured = structure.source_data.numeric(tag, unit=unit)
        value_cell = (
            _reported_cell(measured)
            if measured.state is MissingState.PRESENT
            else _calculated_cell(fallback, f"{fallback:g}")
        )
        rows.append(
            ReportRow(
                id=f"cell:{row_id}",
                cells={"parameter": _calculated_cell(title), "value": value_cell},
            )
        )

    rows.append(
        ReportRow(
            id="cell:volume",
            cells={
                "parameter": _calculated_cell("V"),
                "value": _calculated_cell(
                    structure.cell.volume,
                    f"{structure.cell.volume:.5f}",
                    method_id="unit-cell-determinant",
                ),
            },
        )
    )
    return ReportTable(
        id="crystal_data",
        title="Crystal data",
        columns=(ReportColumn("parameter", "Parameter"), ReportColumn("value", "Value")),
        rows=tuple(rows),
    )


def _site_value(site, key: str, fallback: float, precision: int = 6) -> ReportCell:
    measured = site.reported.get(key)
    if measured is not None and measured.state is MissingState.PRESENT:
        return _reported_cell(measured)
    return _calculated_cell(fallback, f"{fallback:.{precision}f}")


def _site_occupancy(site) -> ReportCell:
    measured = site.reported.get("occupancy")
    if measured is not None and measured.state is MissingState.PRESENT:
        return _reported_cell(measured)
    method_id = "site-component-occupancy-sum" if len(site.components) > 1 else ""
    return _calculated_cell(
        site.occupancy,
        f"{site.occupancy:.6f}",
        method_id=method_id,
    )


def build_atomic_sites_table(structure: CrystalStructure) -> ReportTable:
    rows: list[ReportRow] = []
    for site in structure.asymmetric_sites:
        cart = structure.cell.frac_to_cart(site.fractional)
        rows.append(
            ReportRow(
                id=f"atom:{site.label}",
                cells={
                    "label": ReportCell(site.label, site.label, Provenance.REPORTED),
                    "species": ReportCell(site.element, site.element, Provenance.REPORTED),
                    "x": _site_value(site, "fract_x", site.fractional[0]),
                    "y": _site_value(site, "fract_y", site.fractional[1]),
                    "z": _site_value(site, "fract_z", site.fractional[2]),
                    "occupancy": _site_occupancy(site),
                    "u_iso_or_equiv": _isotropic_displacement(site),
                    "cart_x": _calculated_cell(float(cart[0]), f"{cart[0]:.5f}"),
                    "cart_y": _calculated_cell(float(cart[1]), f"{cart[1]:.5f}"),
                    "cart_z": _calculated_cell(float(cart[2]), f"{cart[2]:.5f}"),
                },
                object_refs=(f"atom:{site.label}",),
            )
        )
    return ReportTable(
        id="atomic_sites",
        title="Atomic coordinates and Uiso/Ueq",
        columns=(
            ReportColumn("label", "Site"),
            ReportColumn("species", "Species"),
            ReportColumn("x", "x"),
            ReportColumn("y", "y"),
            ReportColumn("z", "z"),
            ReportColumn("occupancy", "Occupancy"),
            ReportColumn("u_iso_or_equiv", "Uiso/Ueq", "Å²"),
            ReportColumn("cart_x", "X", "Å", False),
            ReportColumn("cart_y", "Y", "Å", False),
            ReportColumn("cart_z", "Z", "Å", False),
        ),
        rows=tuple(rows),
    )


def _isotropic_displacement(site) -> ReportCell:
    reported_u = site.reported.get("U_iso_or_equiv")
    reported_b = site.reported.get("B_iso_or_equiv")
    if reported_u is not None and reported_u.state is MissingState.PRESENT:
        return _reported_cell(reported_u)
    if reported_b is not None and reported_b.state is MissingState.PRESENT:
        factor = 8.0 * math.pi**2
        value = float(reported_b.value) / factor
        su = reported_b.su / factor if reported_b.su is not None else None
        if su is not None and su > 0:
            precision = max(0, 1 - math.floor(math.log10(su)))
            display = f"{value:.{precision}f}({round(su * 10**precision)})"
        else:
            display = f"{value:.6f}"
        measured = MeasuredValue(display, value, su=su, unit="Å²", source_name=reported_b.source_name)
        return ReportCell(measured, display, Provenance.CALCULATED,
                          source_name=reported_b.source_name, method_id="B-to-U",
                          warning=f"Reported Biso/Beq: {reported_b.formatted()} Å²; U = B/(8π²).")
    if reported_u is not None or reported_b is not None:
        return _reported_cell(reported_u if reported_u is not None else reported_b)
    if site.u_iso is not None:
        return _calculated_cell(site.u_iso, f"{site.u_iso:.6f}")
    return ReportCell(None, "—", Provenance.UNAVAILABLE)


def build_anisotropic_table(structure: CrystalStructure) -> ReportTable:
    """Project CIF tensor components verbatim, retaining their U/B convention."""
    components = ("11", "22", "33", "12", "13", "23")
    rows: list[ReportRow] = []
    for loop in structure.source_data.loops:
        tags = {tag.casefold().replace(".", "_"): index for index, tag in enumerate(loop.tags)}
        label_index = tags.get("_atom_site_aniso_label")
        if label_index is None:
            continue
        convention = next((kind for kind in ("U", "B") if any(
            f"_atom_site_aniso_{kind.lower()}_{key}" in tags for key in components)), None)
        if convention is None:
            continue
        for values in loop.rows:
            label = values[label_index]
            cells = {"label": ReportCell(label, label, Provenance.REPORTED),
                     "tensor": ReportCell(convention, convention, Provenance.REPORTED)}
            for key in components:
                index = tags.get(f"_atom_site_aniso_{convention.lower()}_{key}")
                cells[key] = (_reported_cell(parse_cif_number(values[index], unit="Å²", source_name=loop.tags[index]))
                              if index is not None else ReportCell(None, "—", Provenance.UNAVAILABLE))
            rows.append(ReportRow(f"aniso:{label}:{convention}", cells, object_refs=(f"atom:{label}",)))
    conventions = {row.cells["tensor"].display for row in rows}
    return ReportTable(
        id="anisotropic_adp",
        title="Anisotropic displacement parameters",
        columns=(
            ReportColumn("label", "Site"),
            ReportColumn("tensor", "Tensor"),
            *(ReportColumn(key, f"{next(iter(conventions))}{key}" if len(conventions) == 1 else f"U{key}/B{key}", "Å²") for key in components),
        ),
        rows=tuple(rows),
        availability=Availability.AVAILABLE if rows else Availability.UNAVAILABLE,
        unavailable_reason="" if rows else "No anisotropic Uij or Bij parameters are reported in the source CIF.",
        method="Reported CIF tensor components in Å². Tensor specifies the original U or B convention; no tensor conversion is performed.",
    )
