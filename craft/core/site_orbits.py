from __future__ import annotations

from collections import defaultdict

from craft.core.model import CrystalStructure


def site_orbit_key(label: str) -> str:
    """Return the asymmetric-site label used to generate a symmetry copy."""
    return str(label).split("·", 1)[0]


def site_orbits(structure: CrystalStructure) -> dict[str, tuple[int, ...]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for index, site in enumerate(structure.sites):
        groups[site_orbit_key(site.label)].append(index)
    return {key: tuple(indices) for key, indices in groups.items()}


def polyhedron_orbits(document) -> dict[str, tuple[str, ...]]:
    """Group polyhedra only by the exact orbit identity supplied by CRiStMa."""
    groups: dict[str, list[str]] = defaultdict(list)
    for polyhedron in document.hierarchy.polyhedra:
        # A missing scientific orbit ID is not evidence of equivalence.  Keep
        # such a presentation object independent instead of inferring an orbit
        # from labels or approximate coordinates inside CRAFT.
        key = polyhedron.polyhedron_orbit_id or polyhedron.id
        groups[key].append(polyhedron.id)
    return {key: tuple(ids) for key, ids in groups.items()}


def bond_families(document) -> tuple[tuple[str, str], ...]:
    """Return UI bond pairs without reconstructing contact chemistry.

    Native documents receive the exact primary contact-orbit projection from
    CrIStMa.  The hierarchy walk below exists only for pre-migration documents.
    """
    if hasattr(document.structure, "atomic_view"):
        pairs = {
            tuple(sorted(row.pair_label.split("–", 1)))
            for row in document.inorganic_presentation().contact_orbits
            if row.classification == "primary" and "–" in row.pair_label
        }
        return tuple(sorted(pairs))

    pairs: set[tuple[str, str]] = set()
    structure = getattr(document, "legacy_projection", document.structure)
    for polyhedron in document.hierarchy.polyhedra:
        first = structure.sites[polyhedron.center_index].element
        for ligand in polyhedron.ligands:
            second = structure.sites[ligand.site_index].element
            pairs.add(tuple(sorted((first, second))))
    return tuple(sorted(pairs))


def hierarchy_object_orbits(document, objects) -> tuple[tuple[str, ...], ...]:
    """Group objects only by an exact orbit identity supplied by CRiStMa.

    Missing IDs are deliberately kept independent.  CRAFT is a presentation
    consumer and must not reconstruct scientific equivalence from rounded
    coordinates or a second implementation of the space-group action.
    """
    values = tuple(objects)
    groups: dict[str, list[str]] = {}
    for item in values:
        key = getattr(item, "orbit_id", "") or item.id
        groups.setdefault(key, []).append(item.id)
    return tuple(tuple(identifiers) for identifiers in groups.values())


def connector_orbits(document) -> tuple[tuple[str, ...], ...]:
    """Group connectors only by an exact scientific orbit identity."""
    values = tuple(document.hierarchy.connectors)
    groups: dict[str, list[str]] = {}
    for item in values:
        key = getattr(item, "orbit_id", "") or item.id
        groups.setdefault(key, []).append(item.id)
    return tuple(tuple(identifiers) for identifiers in groups.values())
