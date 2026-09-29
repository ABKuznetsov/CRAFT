"""Compatibility projection from canonical CRiStMa structures into CRAFT."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from cristma.core.values import MeasuredValue as CristmaMeasuredValue
from cristma.diagnostics import Diagnostic
from cristma.io.cif.document import CifDocument
from cristma.structure import (
    CrystalStructure as CristmaCrystalStructure,
    DisplacementParameters,
    MolecularStructure as CristmaMolecularStructure,
    SiteComponent as CristmaSiteComponent,
)
from cristma.symmetry.affine import AffineOperation, format_xyz_operation

from craft.core.model import (
    AtomSite,
    CrystalStructure as CraftCrystalStructure,
    SiteComponent as CraftSiteComponent,
    UnitCell as CraftUnitCell,
)
from craft.core.measurement import MeasuredValue as CraftMeasuredValue
from craft.core.measurement import parse_cif_number
from craft.core.source_data import CifLoop as CraftCifLoop
from craft.core.source_data import CifSourceData
from craft.core.structure_source import LoadedStructure


def _reported_float(value: CristmaMeasuredValue) -> float:
    if value.value is None or not math.isfinite(value.value):
        raise ValueError("CRiStMa value required by CRAFT is missing.")
    return float(value.value)


def _components(
    values: tuple[CristmaSiteComponent, ...],
) -> tuple[CraftSiteComponent, ...]:
    return tuple(
        CraftSiteComponent(
            component.species.require_element(),
            _reported_float(component.occupancy),
        )
        for component in values
    )


def _element(values: tuple[CristmaSiteComponent, ...]) -> str:
    return "/".join(component.species.require_element() for component in values)


def _u_iso(displacement: DisplacementParameters | None) -> float | None:
    if displacement is None or displacement.isotropic is None:
        return None
    value = _reported_float(displacement.isotropic)
    if displacement.kind == "U_iso":
        return value
    if displacement.kind == "B_iso":
        return value / (8.0 * math.pi**2)
    return None


def _operation_text(operation: AffineOperation) -> str:
    return format_xyz_operation(operation)


def _display_name(
    structure: CristmaCrystalStructure,
    source_path: str | Path | None,
) -> str:
    for key in ("mineral_name", "common_name", "systematic_name"):
        value = structure.metadata.get(key)
        if isinstance(value, str) and value.strip() not in {"", ".", "?"}:
            return value.strip()
    if source_path is not None:
        return Path(source_path).expanduser().stem
    return structure.name


def source_data_from_cif_document(
    document: CifDocument | None,
    *,
    block_name: str | None = None,
) -> CifSourceData:
    """Project one already parsed CRiStMa CIF block for CRAFT reports."""

    if document is None:
        return CifSourceData()
    if block_name is not None:
        block = next(
            (
                candidate
                for candidate in document.blocks
                if candidate.name.casefold() == block_name.casefold()
            ),
            None,
        )
        if block is None:
            raise ValueError(f"CIF block {block_name!r} is absent from the source document.")
    elif len(document.blocks) == 1:
        block = document.blocks[0]
    else:
        raise ValueError("A CIF block name is required for a multi-block document.")
    return CifSourceData(
        scalars={item.tag: item.value for item in block.scalars},
        loops=tuple(
            CraftCifLoop(tags=item.tags, rows=item.rows)
            for item in block.loops
        ),
    )


_REPORTED_SITE_TAGS = {
    "_atom_site_fract_x": ("fract_x", ""),
    "_atom_site_fract_y": ("fract_y", ""),
    "_atom_site_fract_z": ("fract_z", ""),
    "_atom_site_occupancy": ("occupancy", ""),
    "_atom_site_U_iso_or_equiv": ("U_iso_or_equiv", "Å²"),
    "_atom_site_B_iso_or_equiv": ("B_iso_or_equiv", "Å²"),
}


def _reported_site_values(
    source_data: CifSourceData,
) -> dict[str, dict[str, CraftMeasuredValue]]:
    result: dict[str, dict[str, CraftMeasuredValue]] = {}
    for loop in source_data.loops:
        normalized = {tag.casefold(): index for index, tag in enumerate(loop.tags)}
        label_index = normalized.get("_atom_site_label")
        if label_index is None:
            continue
        for row in loop.rows:
            values = result.setdefault(row[label_index], {})
            for tag, (key, unit) in _REPORTED_SITE_TAGS.items():
                value_index = normalized.get(tag.casefold())
                if value_index is not None:
                    values[key] = parse_cif_number(
                        row[value_index], source_name=tag, unit=unit
                    )
    return result


def _reported_for_label(
    values: dict[str, dict[str, CraftMeasuredValue]],
    label: str,
) -> dict[str, CraftMeasuredValue]:
    direct = values.get(label)
    if direct is not None:
        return direct
    folded = {key.casefold(): item for key, item in values.items()}
    members = [folded.get(part.casefold()) for part in label.split("/")]
    if not members or any(member is None for member in members):
        return {}
    shared: dict[str, CraftMeasuredValue] = {}
    keys = set.intersection(*(set(member) for member in members if member is not None))
    for key in keys:
        candidates = [member[key] for member in members if member is not None]
        if key != "occupancy" and len({item.raw for item in candidates}) == 1:
            shared[key] = candidates[0]
    return shared


def from_cristma(
    structure: CristmaCrystalStructure,
    *,
    source_path: str | Path | None = None,
    diagnostics: tuple[Diagnostic, ...] = (),
    source_document: CifDocument | None = None,
) -> CraftCrystalStructure:
    """Project a canonical CRiStMa crystal into CRAFT's current display model."""

    source_data = source_data_from_cif_document(
        source_document,
        block_name=(
            str(structure.metadata["cif_block"])
            if "cif_block" in structure.metadata
            else None
        ),
    )
    reported_site_values = _reported_site_values(source_data)
    cell = CraftUnitCell(
        _reported_float(structure.cell.a),
        _reported_float(structure.cell.b),
        _reported_float(structure.cell.c),
        _reported_float(structure.cell.alpha),
        _reported_float(structure.cell.beta),
        _reported_float(structure.cell.gamma),
    )
    labels = {site.id: site.label for site in structure.sites}
    asymmetric_sites = [
        AtomSite(
            label=site.label,
            element=_element(site.components),
            fractional=tuple(_reported_float(value) for value in site.fractional),
            occupancy=site.total_occupancy,
            u_iso=_u_iso(site.displacement),
            reported=_reported_for_label(reported_site_values, site.label),
            components=_components(site.components),
            disorder_group=site.disorder_group or "",
            assembly=site.disorder_assembly or "",
            source_site_key=site.label,
            scientific_id=site.id,
            source_site_id=site.id,
        )
        for site in structure.sites
    ]
    source_sites = {site.id: site for site in structure.sites}
    expanded_sites = [
        AtomSite(
            label=labels[atom.source_site_id],
            element=_element(atom.components),
            fractional=tuple(float(value) for value in atom.fractional),
            occupancy=sum(
                _reported_float(component.occupancy) for component in atom.components
            ),
            u_iso=_u_iso(atom.displacement),
            reported=_reported_for_label(
                reported_site_values, labels[atom.source_site_id]
            ),
            components=_components(atom.components),
            disorder_group=source_sites[atom.source_site_id].disorder_group or "",
            assembly=source_sites[atom.source_site_id].disorder_assembly or "",
            source_site_key=labels[atom.source_site_id],
            scientific_id=atom.id,
            source_site_id=atom.source_site_id,
        )
        for atom in structure.atomic_view(expanded=True).atoms
    ]
    operations = (
        [_operation_text(operation) for operation in structure.space_group.operations]
        if structure.space_group is not None
        else ["x,y,z"]
    )
    space_group = structure.space_group
    return CraftCrystalStructure(
        name=_display_name(structure, source_path),
        cell=cell,
        asymmetric_sites=asymmetric_sites,
        sites=expanded_sites,
        symmetry_operations=operations,
        formula=structure.formula or "",
        space_group=(
            (space_group.hm_symbol or space_group.hall_symbol or "")
            if space_group is not None
            else ""
        ),
        source_path=Path(source_path).expanduser().resolve() if source_path else None,
        source_data=source_data,
        source_diagnostics=tuple(diagnostics),
    )


def build_legacy_projection(loaded: LoadedStructure) -> CraftCrystalStructure:
    """Build the temporary CRAFT model for consumers not yet migrated."""

    if isinstance(loaded.structure, CristmaMolecularStructure):
        points = np.asarray(
            [atom.cartesian for atom in loaded.structure.atoms],
            dtype=float,
        )
        low = points.min(axis=0) - 5.0
        lengths = np.maximum(points.max(axis=0) - points.min(axis=0) + 10.0, 10.0)
        fractional = (points - low) / lengths
        sites = [
            AtomSite(
                label=atom.label,
                element=_element(atom.components),
                fractional=tuple(float(value) for value in fractional[index]),
                occupancy=sum(
                    _reported_float(component.occupancy)
                    for component in atom.components
                ),
                components=_components(atom.components),
                source_site_key=atom.label,
                scientific_id=atom.id,
                source_site_id=atom.id,
            )
            for index, atom in enumerate(loaded.structure.atoms)
        ]
        return CraftCrystalStructure(
            name=loaded.display_name,
            cell=CraftUnitCell(*map(float, lengths)),
            asymmetric_sites=list(sites),
            sites=sites,
            symmetry_operations=["x,y,z"],
            formula="",
            space_group="molecule (display cell)",
            source_path=loaded.source.source_path,
            source_diagnostics=loaded.source.diagnostics,
        )
    if not isinstance(loaded.structure, CristmaCrystalStructure):
        raise TypeError("unsupported canonical structure type")
    projection = from_cristma(
        loaded.structure,
        source_path=loaded.source.source_path,
        diagnostics=loaded.source.diagnostics,
        source_document=(
            loaded.source.source_document
            if isinstance(loaded.source.source_document, CifDocument)
            else None
        ),
    )
    projection.name = loaded.display_name
    return projection


__all__ = [
    "build_legacy_projection",
    "from_cristma",
    "source_data_from_cif_document",
]
