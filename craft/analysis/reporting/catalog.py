from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TableDefinition:
    id: str
    title: str
    group: str
    stage: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class ReportPreset:
    id: str
    title: str
    table_ids: tuple[str, ...]


TABLE_DEFINITIONS = (
    TableDefinition("crystal_data", "Crystal data", "Crystal and refinement", "A"),
    TableDefinition("refinement", "Experiment and refinement", "Crystal and refinement", "A"),
    TableDefinition("atomic_sites", "Coordinates and Uiso/Ueq", "Atoms and displacement", "A"),
    TableDefinition("anisotropic_adp", "Anisotropic ADP (Uij/Bij)", "Atoms and displacement", "A"),
    TableDefinition("bond_lengths", "Bond lengths", "Geometry", "A"),
    TableDefinition("bond_angles", "Bond angles", "Geometry", "A"),
    TableDefinition("torsion_angles", "Torsion angles", "Geometry", "D"),
    TableDefinition("contacts", "Non-bonded contacts", "Geometry", "D"),
    TableDefinition("hydrogen_bonds", "Hydrogen bonds", "Geometry", "D"),
    TableDefinition("coordination", "Coordination environments", "Inorganic geometry", "B"),
    TableDefinition("inorganic_classification", "Inorganic compound classes", "Inorganic geometry", "B"),
    TableDefinition("polyhedra", "Polyhedral metrics", "Inorganic geometry", "B"),
    TableDefinition("connectivity", "Polyhedral connectivity", "Inorganic geometry", "B"),
    TableDefinition("bond_valence", "Bond-valence analysis", "Inorganic geometry", "B"),
    TableDefinition("structural_units", "Structural blocks", "Hierarchy and mechanics", "C"),
    TableDefinition("rigid_blocks", "Rigid blocks", "Hierarchy and mechanics", "C"),
    TableDefinition("connectors", "Connectors and pivot candidates", "Hierarchy and mechanics", "C"),
    TableDefinition("degrees_of_freedom", "Degrees of freedom", "Hierarchy and mechanics", "C"),
    TableDefinition("molecular_components", "Molecular components", "Molecular and reticular", "B"),
    TableDefinition("molecular_rings", "Molecular rings", "Molecular and reticular", "B"),
    TableDefinition("intermolecular_contacts", "Intermolecular contacts", "Molecular and reticular", "B"),
    TableDefinition("packing_interactions", "Packing interactions", "Molecular and reticular", "B"),
    TableDefinition("coordination_nodes", "Coordination nodes", "Molecular and reticular", "B"),
    TableDefinition("linkers", "Linkers", "Molecular and reticular", "B"),
    TableDefinition("sbus", "Secondary building units", "Molecular and reticular", "B"),
    TableDefinition("reticular_net", "Reticular net", "Molecular and reticular", "B"),
)

_TABLES_BY_ID = {definition.id: definition for definition in TABLE_DEFINITIONS}

STANDARD = (
    "crystal_data",
    "refinement",
    "atomic_sites",
    "anisotropic_adp",
    "bond_lengths",
    "bond_angles",
)
INORGANIC = STANDARD + ("inorganic_classification", "coordination", "polyhedra", "connectivity", "bond_valence")
ARTICLE_TABLE_IDS = frozenset(STANDARD + ("bond_valence", "polyhedra", "hydrogen_bonds"))
MECHANICS = ("structural_units", "rigid_blocks", "connectors", "degrees_of_freedom")
ORGANIC_MOF = (
    "crystal_data",
    "atomic_sites",
    "bond_lengths",
    "molecular_components",
    "molecular_rings",
    "intermolecular_contacts",
    "packing_interactions",
    "coordination_nodes",
    "linkers",
    "sbus",
    "reticular_net",
)
FULL = tuple(definition.id for definition in TABLE_DEFINITIONS)

REPORT_PRESETS = (
    ReportPreset("standard", "Standard Structure Paper", STANDARD),
    ReportPreset("inorganic", "Inorganic / Mineral Structure", INORGANIC),
    ReportPreset("mechanics", "CRAFT Mechanics", MECHANICS),
    ReportPreset("organic_mof", "Organic / MOF Structure", ORGANIC_MOF),
    ReportPreset("full", "Full Report", FULL),
    ReportPreset("custom", "Custom", ()),
)

_PRESETS_BY_ID = {preset.id: preset for preset in REPORT_PRESETS}


def table_definition(table_id: str) -> TableDefinition:
    try:
        return _TABLES_BY_ID[table_id]
    except KeyError as error:
        raise KeyError(f"Unknown report table: {table_id}") from error


def report_preset(preset_id: str) -> ReportPreset:
    try:
        return _PRESETS_BY_ID[preset_id]
    except KeyError as error:
        raise KeyError(f"Unknown report preset: {preset_id}") from error
