from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from html import escape

from craft.core.document import StructureDocument
from craft.presentation.organic_scene import OrganicSceneMode


class OrganicViewKind(StrEnum):
    MOLECULAR_UNIT = "molecular_unit"
    COORDINATION_FRAGMENT = "coordination_fragment"
    ATOMS = "atoms"
    COVALENT_BONDS = "covalent_bonds"
    COORDINATION_BONDS = "coordination_bonds"
    CONTACTS = "contacts"
    RINGS = "molecular_rings"
    NODES_SBUS = "nodes_sbus"
    LINKERS = "linkers"
    PERIODIC_NETWORK = "periodic_network"
    PACKING = "crystal_packing"


@dataclass(frozen=True, slots=True)
class OrganicViewDescriptor:
    kind: OrganicViewKind
    label: str
    ready: bool
    object_count: int | None


def organic_scene_mode(category: str | None) -> OrganicSceneMode:
    """Use the same view mapping for a user command and a scene rebuild."""
    return {
        OrganicViewKind.CONTACTS: OrganicSceneMode.CONTACTS,
        OrganicViewKind.RINGS: OrganicSceneMode.RING,
        OrganicViewKind.COORDINATION_FRAGMENT: OrganicSceneMode.SBU,
        OrganicViewKind.NODES_SBUS: OrganicSceneMode.SBU,
        OrganicViewKind.LINKERS: OrganicSceneMode.LINKER,
        OrganicViewKind.PERIODIC_NETWORK: OrganicSceneMode.NET,
        OrganicViewKind.PACKING: OrganicSceneMode.PACKING,
    }.get(category, OrganicSceneMode.SINGLE_MOLECULE)


def default_organic_view(document: StructureDocument) -> OrganicViewKind:
    native_sbu = getattr(document.scientific.sbu, "result", None)
    if getattr(native_sbu, "sbu_orbits", ()):
        return OrganicViewKind.COORDINATION_FRAGMENT
    return OrganicViewKind.MOLECULAR_UNIT


def _descriptor(
    kind: OrganicViewKind,
    label: str,
    count: int | None,
) -> OrganicViewDescriptor:
    return OrganicViewDescriptor(kind, label, count is not None, count)


def organic_view_descriptors(
    document: StructureDocument,
) -> tuple[OrganicViewDescriptor, ...]:
    native = document.organic_presentation()
    if getattr(document.scientific.molecular, "result", None) is not None:
        descriptors: list[OrganicViewDescriptor] = []
        if native.sbus:
            descriptors.append(_descriptor(
                OrganicViewKind.COORDINATION_FRAGMENT,
                "Coordination fragment",
                len(native.sbus),
            ))
        elif native.components:
            descriptors.append(_descriptor(
                OrganicViewKind.MOLECULAR_UNIT,
                "Molecule",
                len(native.components),
            ))
        if native.rings:
            descriptors.append(_descriptor(
                OrganicViewKind.RINGS, "Rings", len(native.rings)
            ))
        if native.contacts:
            descriptors.append(_descriptor(
                OrganicViewKind.CONTACTS,
                "Intermolecular contacts",
                len(native.contacts),
            ))
        if native.nodes or native.sbus:
            descriptors.append(_descriptor(
                OrganicViewKind.NODES_SBUS,
                "Nodes / SBUs",
                len(native.sbus) or len(native.nodes),
            ))
        if native.linkers:
            descriptors.append(_descriptor(
                OrganicViewKind.LINKERS, "Linkers", len(native.linkers)
            ))
        if native.net_vertices or native.net_edges:
            descriptors.append(_descriptor(
                OrganicViewKind.PERIODIC_NETWORK,
                "Underlying net",
                len(native.net_edges),
            ))
        if getattr(document.scientific.packing, "result", None) is not None:
            descriptors.append(_descriptor(
                OrganicViewKind.PACKING,
                "Crystal packing",
                len(native.packing_connections),
            ))
        return tuple(descriptors)

    return ()


def organic_analysis_summary(document: StructureDocument) -> tuple[str, str]:
    """Return passive organic evidence for the inspector, not the view tree."""
    native = document.organic_presentation()
    if getattr(document.scientific.molecular, "result", None) is not None:
        net = getattr(document.scientific.reticular_net, "result", None)
        rank = max(
            (getattr(item, "periodic_rank", 0) for item in getattr(net, "components", ())),
            default=0,
        )
        rows = [
            ("Molecular component orbits", len(native.components)),
            ("Molecular ring orbits", len(native.rings)),
            ("Intermolecular contact orbits", len(native.contacts)),
            ("Packing connection orbits", len(native.packing_connections)),
            ("Coordination node orbits", len(native.nodes)),
            ("Linker orbits", len(native.linkers)),
            ("SBU orbits", len(native.sbus)),
            ("Network rank", rank),
        ]
        body = "".join(
            f"<b>{escape(str(label))}:</b> {escape(str(value))}<br>"
            for label, value in rows
        )
        if native.diagnostics:
            body += "<br><b>Diagnostics</b><br>" + "<br>".join(
                escape(str(getattr(item, "message", item)))
                for item in native.diagnostics
            )
        body += "<br><br><b>Method:</b> CrIStMa native orbit-first analysis"
        return "Organic structure analysis", body

    return "Organic structure analysis", "CrIStMa analysis is still calculating."


__all__ = [
    "OrganicViewDescriptor",
    "OrganicViewKind",
    "default_organic_view",
    "organic_analysis_summary",
    "organic_view_descriptors",
    "organic_scene_mode",
]
