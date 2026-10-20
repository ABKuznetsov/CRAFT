from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import chain
from pathlib import Path
from typing import Iterator

from cristma.structure import CrystalStructure as CanonicalCrystalStructure

from craft.analysis.cristma_inorganic import (
    NativeInorganicSettings,
    NativeInorganicSnapshot,
    iter_analyze_inorganic,
)
from craft.analysis.cristma_organic import (
    NativeOrganicSettings,
    NativeOrganicSnapshot,
    iter_analyze_organic,
)
from craft.analysis.structure_profile import RequestedProfile, ResolvedProfile, resolve_structure_profile
from craft.core.structure_source import LoadedStructure
from craft.core.structure_io import load_structure_files


class LoadStage(StrEnum):
    PARSED = "parsed"
    CHEMISTRY = "chemistry"
    CONTACTS = "contacts"
    POLYHEDRA = "polyhedra"
    UNITS = "units"
    BLOCKS = "blocks"
    RINGS = "rings"
    MOLECULAR = "molecular"
    INTERMOLECULAR = "intermolecular"
    PACKING = "packing"
    RETICULAR_PRECURSOR = "reticular_precursor"
    SBU = "sbu"
    RETICULAR_NET = "reticular_net"


@dataclass(frozen=True, slots=True)
class StructureLoadUpdate:
    stage: LoadStage
    source_path: Path
    structure_index: int
    structure_count: int
    loaded: LoadedStructure
    native_snapshot: NativeInorganicSnapshot | None = None
    native_organic_snapshot: NativeOrganicSnapshot | None = None


def _iter_analysis_updates(
    loaded: LoadedStructure,
    requested: RequestedProfile,
    native_settings: NativeInorganicSettings,
    organic_settings: NativeOrganicSettings,
    index: int = 0,
    count: int = 1,
) -> Iterator[StructureLoadUpdate]:
    # Historical entries with a cell but no usable coordinates retain a preview.
    if not isinstance(loaded.structure, CanonicalCrystalStructure) or not loaded.structure.sites:
        return
    snapshots = iter_analyze_inorganic(loaded.structure, native_settings)
    chemistry = next(snapshots)
    decision = resolve_structure_profile(chemistry.chemistry.classification, requested)
    use_inorganic = decision.resolved is ResolvedProfile.INORGANIC
    use_both = decision.resolved is ResolvedProfile.RETICULAR
    for snapshot in chain((chemistry,), snapshots):
        yield StructureLoadUpdate(
            LoadStage(snapshot.stage.value),
            loaded.source.source_path,
            index,
            count,
            loaded,
            native_snapshot=snapshot,
        )
        if not use_inorganic and not use_both and snapshot.contact_result is not None:
            # Organic tools consume this exact contact result, with the same
            # composition grammar and shell policy as inorganic analysis.
            for result in iter_analyze_organic(snapshot.contact_result, organic_settings):
                yield StructureLoadUpdate(
                    LoadStage(result.stage.value),
                    loaded.source.source_path,
                    index,
                    count,
                    loaded,
                    native_organic_snapshot=result,
                )
            return
    if use_both:
        # Finish both views of the same resolved contacts for mixed structures.
        for result in iter_analyze_organic(snapshot.contact_result, organic_settings):
            yield StructureLoadUpdate(
                LoadStage(result.stage.value), loaded.source.source_path,
                index, count, loaded, native_organic_snapshot=result,
            )


def iter_reanalysis_updates(
    document,
    requested: RequestedProfile,
) -> Iterator[StructureLoadUpdate]:
    """Capture immutable inputs now; calculate later without reparsing."""
    return _iter_analysis_updates(
        LoadedStructure(document.structure, document.source),
        requested,
        document.native_settings,
        document.native_organic_settings,
    )


def iter_load_updates(
    path: str | Path,
    *,
    settings: NativeOrganicSettings | None = None,
    requested: RequestedProfile = RequestedProfile.AUTO,
) -> Iterator[StructureLoadUpdate]:
    source = Path(path).expanduser().resolve()
    settings = settings or NativeOrganicSettings()
    loaded_structures = load_structure_files(source)
    total = len(loaded_structures)
    # Deliver every preview before starting any scientific analysis.
    for index, loaded in enumerate(loaded_structures):
        yield StructureLoadUpdate(LoadStage.PARSED, source, index, total, loaded)
    for index, loaded in enumerate(loaded_structures):
        yield from _iter_analysis_updates(
            loaded, requested, NativeInorganicSettings(), settings, index, total,
        )


__all__ = [
    "LoadStage",
    "StructureLoadUpdate",
    "iter_load_updates",
    "iter_reanalysis_updates",
]
