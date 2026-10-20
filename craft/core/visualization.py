"""Presentation state independent of structure analysis and UI widgets."""

from __future__ import annotations

from dataclasses import dataclass, field, fields

from craft.analysis.hierarchy import HierarchyLevel


def copy_visual_value(value: object) -> object:
    """Copy schema containers; their leaves are immutable IDs, colours or flags."""
    if isinstance(value, set):
        return value.copy()
    if isinstance(value, dict):
        return {
            key: item.copy() if isinstance(item, set) else item
            for key, item in value.items()
        }
    return value


@dataclass(slots=True)
class VisibilityState:
    hidden_atom_indices: set[int] = field(default_factory=set)
    hidden_atom_orbit_ids: set[str] = field(default_factory=set)
    hidden_atom_instance_keys: set[tuple[str, tuple[int, int, int]]] = field(default_factory=set)
    hidden_bond_orbits: set[str] = field(default_factory=set)
    hidden_bond_families: set[tuple[str, str]] = field(default_factory=set)
    hidden_contact_orbit_ids: set[str] = field(default_factory=set)
    hidden_polyhedron_ids: set[str] = field(default_factory=set)
    hidden_polyhedron_orbit_ids: set[str] = field(default_factory=set)
    hidden_unit_ids: set[str] = field(default_factory=set)
    hidden_block_ids: set[str] = field(default_factory=set)
    hidden_connector_ids: set[str] = field(default_factory=set)
    hidden_topology_family_ids: set[str] = field(default_factory=set)
    shown_unit_ids: set[str] = field(default_factory=set)
    shown_ring_ids: set[str] = field(default_factory=set)
    shown_block_ids: set[str] = field(default_factory=set)
    unit_auto_hidden_atoms: dict[str, set[int]] = field(default_factory=dict)
    unit_auto_hidden_polyhedra: dict[str, set[str]] = field(default_factory=dict)
    block_auto_hidden_atom_ids: dict[str, frozenset[str]] = field(default_factory=dict)
    block_auto_hidden_polyhedron_orbit_ids: dict[str, frozenset[str]] = field(default_factory=dict)

    def reset_visibility(self) -> None:
        """Restore all objects without changing colours or the selected view."""
        for name in VISIBILITY_FIELDS:
            getattr(self, name).clear()

    def copy_visibility_from(self, source: VisibilityState) -> None:
        """Copy visibility, including nested membership sets, without aliases."""
        for name in VISIBILITY_FIELDS:
            setattr(self, name, copy_visual_value(getattr(source, name)))


VISIBILITY_FIELDS = tuple(item.name for item in fields(VisibilityState))


@dataclass(frozen=True, slots=True)
class CrystalLayerStyle:
    """One independently styled level of a crystal-chemical illustration."""

    color: str
    representation: str = "edges"
    visible: bool = True
    display_offset: tuple[float, float, float] = (0., 0., 0.)
    hidden_member_orbit_ids: frozenset[str] = frozenset()


@dataclass(slots=True)
class VisualizationState(VisibilityState):
    level: HierarchyLevel = HierarchyLevel.SITES
    organic_active_view: str | None = None
    organic_active_object_id: str | None = None
    organic_view_user_selected: bool = False
    contact_defaults_applied: set[str] = field(default_factory=set)
    contact_orbit_colors: dict[str, str] = field(default_factory=dict)
    atom_orbit_colors: dict[str, str] = field(default_factory=dict)
    polyhedron_orbit_colors: dict[str, str] = field(default_factory=dict)
    unit_colors: dict[str, str] = field(default_factory=dict)
    block_colors: dict[str, str] = field(default_factory=dict)
    ring_scope_colors: dict[str, str] = field(default_factory=dict)
    crystal_layers: dict[str, CrystalLayerStyle] = field(default_factory=dict)
    crystal_layers_enabled: bool = False

    def discard_analysis_objects(self) -> None:
        """Release calculated memberships, retaining input visibility and colours."""
        for indices in self.unit_auto_hidden_atoms.values():
            self.hidden_atom_indices.difference_update(indices)
        for name in (
            "hidden_polyhedron_ids", "hidden_polyhedron_orbit_ids", "hidden_unit_ids",
            "hidden_block_ids", "hidden_connector_ids", "hidden_topology_family_ids",
            "shown_unit_ids", "shown_ring_ids", "shown_block_ids",
            "unit_auto_hidden_atoms", "unit_auto_hidden_polyhedra",
            "block_auto_hidden_atom_ids", "block_auto_hidden_polyhedron_orbit_ids",
        ):
            getattr(self, name).clear()
        self.organic_active_object_id = None
        self.crystal_layers_enabled = False
