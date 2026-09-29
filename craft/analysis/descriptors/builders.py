"""Build publication-oriented crystallochemical descriptors."""

from __future__ import annotations

from collections import Counter
from typing import cast
from cristma.structure import CrystalStructure as CanonicalCrystalStructure

from craft.analysis.descriptors.model import (
    DescriptorKind,
    DescriptorValue,
    DistributionSummary,
)
from craft.core.document import StructureDocument


METHOD_ID = "crystal-blocks-descriptors-v1"


def _number(value: object) -> float:
    """Read a canonical measured value without projecting it into legacy data."""

    return float(getattr(value, "value", value))


def _cell_values(document: StructureDocument) -> tuple[float, ...]:
    structure = document.structure
    if isinstance(structure, CanonicalCrystalStructure):
        cell = structure.cell
        return (
            _number(cell.a),
            _number(cell.b),
            _number(cell.c),
            _number(cell.alpha),
            _number(cell.beta),
            _number(cell.gamma),
            float(cell.volume),
        )
    cell = document.legacy_projection.cell
    return (
        float(cell.a),
        float(cell.b),
        float(cell.c),
        float(cell.alpha),
        float(cell.beta),
        float(cell.gamma),
        float(cell.volume),
    )


def _space_group(document: StructureDocument) -> str:
    structure = document.structure
    if isinstance(structure, CanonicalCrystalStructure):
        definition = structure.space_group
        if definition is None:
            return ""
        return str(
            definition.hm_symbol
            or definition.hall_symbol
            or (f"No. {definition.number}" if definition.number else "")
        )
    return str(document.legacy_projection.space_group or "")


def _value(
    identifier: str,
    title: str,
    section: str,
    kind: DescriptorKind,
    value: object,
    unit: str = "",
    *,
    warning: str = "",
    object_refs: tuple[str, ...] = (),
) -> DescriptorValue:
    return DescriptorValue(
        id=identifier,
        title=title,
        section=section,
        kind=kind,
        value=cast(object, value),
        unit=unit,
        method_id=METHOD_ID,
        warning=warning,
        object_refs=object_refs,
    )


def build_descriptors(
    document: StructureDocument,
    strong_5_plus_1_gap: float = 0.25,
) -> dict[str, DescriptorValue]:
    cache_key = (
        METHOD_ID,
        f"strong-gap={float(strong_5_plus_1_gap):.8g}",
        document.content_identity(),
    )
    cached = document.descriptor_cache.get(cache_key)
    if isinstance(cached, dict):
        return cast(dict[str, DescriptorValue], cached)

    a, b, c, alpha, beta, gamma, volume = _cell_values(document)
    space_group = _space_group(document)
    descriptors = {
        "cell.a": _value("cell.a", "a", "Unit Cell", DescriptorKind.SCALAR, a, "Å"),
        "cell.b": _value("cell.b", "b", "Unit Cell", DescriptorKind.SCALAR, b, "Å"),
        "cell.c": _value("cell.c", "c", "Unit Cell", DescriptorKind.SCALAR, c, "Å"),
        "cell.alpha": _value(
            "cell.alpha", "α", "Unit Cell", DescriptorKind.SCALAR, alpha, "°"
        ),
        "cell.beta": _value(
            "cell.beta", "β", "Unit Cell", DescriptorKind.SCALAR, beta, "°"
        ),
        "cell.gamma": _value(
            "cell.gamma", "γ", "Unit Cell", DescriptorKind.SCALAR, gamma, "°"
        ),
        "cell.volume": _value(
            "cell.volume", "Cell volume", "Unit Cell", DescriptorKind.SCALAR, volume, "Å³"
        ),
        "cell.space_group": _value(
            "cell.space_group",
            "Space group",
            "Unit Cell",
            DescriptorKind.CATEGORICAL,
            space_group or "unknown",
            warning=("" if space_group else "Space group was not reported."),
        ),
        "cell.c_over_a": _value(
            "cell.c_over_a",
            "c/a ratio",
            "Unit Cell",
            DescriptorKind.SCALAR,
            c / a,
        ),
    }

    occupancy_messages = tuple(
        warning.message
        for warning in document.warnings
        if warning.code == "occupancy-out-of-range"
    )
    descriptors["occupancy.out_of_range"] = _value(
        "occupancy.out_of_range",
        "Occupancy warnings",
        "Warnings and Data Quality",
        DescriptorKind.CATEGORICAL,
        "; ".join(occupancy_messages) if occupancy_messages else "none",
        warning="; ".join(occupancy_messages),
    )

    canonical = isinstance(document.structure, CanonicalCrystalStructure)
    native_polyhedra = getattr(document.scientific.polyhedra, "result", None)
    if canonical and native_polyhedra is not None:
        site_by_id = {site.id: site for site in document.structure.sites}
        polyhedra = tuple(native_polyhedra.polyhedra)

        def center_symbol(item) -> str:
            site = site_by_id[item.source_site_id]
            component = max(
                site.components,
                key=lambda value: float(getattr(value.occupancy, "value", value.occupancy)),
            )
            return str(getattr(component.species, "symbol", component.species))

        def ligand_symbol(item) -> str:
            return "".join(
                f"{symbol}{count:g}" for symbol, count in item.ligand_composition
            )

        counts = dict(sorted(Counter(
            f"{center_symbol(item)}{ligand_symbol(item)}" for item in polyhedra
        ).items()))
        polyhedron_refs = tuple(item.polyhedron_id for item in polyhedra)
    else:
        polyhedra = ()
        counts = {}
        polyhedron_refs = ()
    polyhedra_available = canonical and native_polyhedra is not None
    descriptors["coordination.polyhedron_counts"] = _value(
        "coordination.polyhedron_counts",
        "Coordination polyhedra",
        "Polyhedra",
        DescriptorKind.CATEGORICAL if polyhedra_available else DescriptorKind.UNAVAILABLE,
        counts if polyhedra_available else None,
        warning=("" if polyhedra_available else "CrIStMa polyhedron result is not available."),
        object_refs=polyhedron_refs,
    )

    if polyhedra_available:
        mo_o6 = [
            item for item in polyhedra
            if center_symbol(item) == "Mo"
            and item.ligand_composition == (("O", 6.0),)
            and item.coordination_number == 6
        ]
        lengths = lambda item: tuple(vertex.distance for vertex in item.vertices)
        identifiers = lambda item: item.polyhedron_id
        distortions = (
            float(item.bond_length_distortion)
            for item in mo_o6
            if item.bond_length_distortion is not None
        )
        offsets = (
            float(item.center_offset)
            for item in mo_o6
            if item.center_offset is not None
        )
    else:
        mo_o6 = []
        lengths = lambda item: ()
        identifiers = lambda item: ""
        distortions = ()
        offsets = ()
    distortion = DistributionSummary.from_values(distortions)
    off_centering = DistributionSummary.from_values(offsets)
    gaps = DistributionSummary.from_values(
        sorted(lengths(item))[5] - sorted(lengths(item))[4]
        for item in mo_o6
    )
    references = tuple(identifiers(item) for item in mo_o6)
    descriptors["mo_o.distortion_index"] = _value(
        "mo_o.distortion_index", "Mo–O distortion index", "Polyhedra",
        DescriptorKind.DISTRIBUTION, distortion, object_refs=references,
    )
    descriptors["mo_o.off_centering"] = _value(
        "mo_o.off_centering", "Mo off-centering", "Polyhedra",
        DescriptorKind.DISTRIBUTION, off_centering, "Å", object_refs=references,
    )
    descriptors["mo_o.d6_minus_d5"] = _value(
        "mo_o.d6_minus_d5", "d6 − d5", "Polyhedra",
        DescriptorKind.DISTRIBUTION, gaps, "Å", object_refs=references,
    )
    strong_fraction = (
        sum(value > strong_5_plus_1_gap for value in gaps.values) / gaps.count
        if gaps.count
        else None
    )
    descriptors["mo_o.strong_5_plus_1_fraction"] = _value(
        "mo_o.strong_5_plus_1_fraction",
        "Strong [5+1] fraction",
        "Polyhedra",
        DescriptorKind.SCALAR if strong_fraction is not None else DescriptorKind.UNAVAILABLE,
        strong_fraction,
    )

    native_connectivity = getattr(document.scientific.connectivity, "result", None)
    if canonical and native_connectivity is not None:
        presentation = document.inorganic_presentation()
        components = tuple(native_connectivity.components)
        component_classes = dict(sorted(Counter(
            block.classification for block in presentation.structural_blocks
        ).items()))
        descriptors["topology.component_classes"] = _value(
            "topology.component_classes",
            "Periodic component classes",
            "Topology",
            DescriptorKind.GRAPH,
            {
                "classes": component_classes,
                "ranks": tuple(item.rank for item in components),
                "family_ids": tuple(item.topology_id for item in presentation.topology_families),
            },
        )
    else:
        descriptors["topology.component_classes"] = _value(
            "topology.component_classes",
            "Periodic component classes",
            "Topology",
            DescriptorKind.UNAVAILABLE,
            None,
            warning="CrIStMa topology result is not available.",
        )

    document.descriptor_cache[cache_key] = descriptors
    return descriptors
