from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import chain
from pathlib import Path
from typing import Iterator

from cristma.chemistry import ChemicalDomain
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
from craft.analysis.structure_profile import (
    RequestedProfile,
)
from craft.core.structure_source import LoadedStructure
from craft.core.structure_io import load_structure_files


class LoadStage(StrEnum):
    PARSED = "parsed"
    CHEMISTRY = "chemistry"
    BONDS = "bonds"
    POLYHEDRA = "polyhedra"
    UNITS = "units"
    TOPOLOGY = "topology"
    BONDS_PROFILE = "bonds/profile"
    COMPONENTS = "components"
    CONTACTS = "contacts"
    PACKING = "packing"
    RETICULAR = "reticular"
    MOLECULAR = "molecular"
    INTERMOLECULAR = "intermolecular"
    RETICULAR_PRECURSOR = "reticular_precursor"
    SBU = "sbu"
    RETICULAR_NET = "reticular_net"
    BLOCKS = "blocks"
    RINGS = "rings"


@dataclass(frozen=True, slots=True)
class StructureLoadUpdate:
    stage: LoadStage
    source_path: Path
    structure_index: int
    structure_count: int
    loaded: LoadedStructure
    native_snapshot: NativeInorganicSnapshot | None = None
    native_organic_snapshot: NativeOrganicSnapshot | None = None


def iter_reanalysis_updates(
    document,
    requested: RequestedProfile,
) -> Iterator[StructureLoadUpdate]:
    """Reanalyze an already parsed structure without blocking or reparsing it."""
    source = document.source.source_path
    loaded = LoadedStructure(document.structure, document.source)
    settings = document.native_organic_settings
    native_snapshots = None
    contact_snapshot = None
    if isinstance(document.structure, CanonicalCrystalStructure):
        native_snapshots = iter_analyze_inorganic(document.structure)
        chemistry_snapshot = next(native_snapshots, None)
        use_native = requested is RequestedProfile.INORGANIC or (
            requested is RequestedProfile.AUTO
            and chemistry_snapshot is not None
            and chemistry_snapshot.chemistry.classification.domain
            not in {ChemicalDomain.ORGANIC, ChemicalDomain.METAL_ORGANIC}
        )
        if use_native:
            for snapshot in chain((chemistry_snapshot,), native_snapshots):
                if snapshot is None:
                    continue
                yield StructureLoadUpdate(
                    LoadStage(snapshot.stage.value),
                    source,
                    0,
                    1,
                    loaded,
                    native_snapshot=snapshot,
                )
            return
        yield StructureLoadUpdate(
            LoadStage.CHEMISTRY,
            source,
            0,
            1,
            loaded,
            native_snapshot=chemistry_snapshot,
        )
        contact_snapshot = next(native_snapshots, None)
    if contact_snapshot is None or contact_snapshot.contact_result is None:
        return
    yield StructureLoadUpdate(
        LoadStage.CONTACTS,
        source,
        0,
        1,
        loaded,
        native_snapshot=contact_snapshot,
    )
    for result in iter_analyze_organic(
        contact_snapshot.contact_result,
        settings,
    ):
        yield StructureLoadUpdate(
            LoadStage(result.stage.value),
            source,
            0,
            1,
            loaded,
            native_organic_snapshot=result,
        )


def iter_native_reanalysis_updates(
    document,
    settings: NativeInorganicSettings,
) -> Iterator[StructureLoadUpdate]:
    """Recalculate the native CrIStMa chain without reparsing the structure."""
    source = document.source.source_path
    loaded = LoadedStructure(document.structure, document.source)
    for snapshot in iter_analyze_inorganic(document.structure, settings):
        yield StructureLoadUpdate(
            LoadStage(snapshot.stage.value),
            source,
            0,
            1,
            loaded,
            native_snapshot=snapshot,
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
    for index, loaded in enumerate(loaded_structures):
        yield StructureLoadUpdate(
            LoadStage.PARSED,
            source,
            index,
            total,
            loaded,
        )
    for index, loaded in enumerate(loaded_structures):
        # Some historical database entries contain a valid unit cell but no
        # usable atom coordinates.  The preview is still meaningful; there is
        # simply no composition or structural hierarchy to analyse.
        if not loaded.structure.sites:
            continue
        native_results = (
            iter_analyze_inorganic(loaded.structure)
            if isinstance(loaded.structure, CanonicalCrystalStructure)
            else None
        )
        first_native = next(native_results, None) if native_results is not None else None
        domain = (
            first_native.chemistry.classification.domain
            if first_native is not None
            else None
        )
        use_native = first_native is not None and (
            requested is RequestedProfile.INORGANIC
            or (
                requested is RequestedProfile.AUTO
                and domain not in {ChemicalDomain.ORGANIC, ChemicalDomain.METAL_ORGANIC}
            )
        )
        if use_native:
            for native_snapshot in chain((first_native,), native_results):
                yield StructureLoadUpdate(
                    LoadStage(native_snapshot.stage.value),
                    source,
                    index,
                    total,
                    loaded,
                    native_snapshot=native_snapshot,
                )
            continue
        if first_native is None or native_results is None:
            continue
        yield StructureLoadUpdate(
            LoadStage.CHEMISTRY,
            source,
            index,
            total,
            loaded,
            native_snapshot=first_native,
        )
        contact_snapshot = next(native_results, None)
        if contact_snapshot is None or contact_snapshot.contact_result is None:
            continue
        yield StructureLoadUpdate(
            LoadStage.CONTACTS,
            source,
            index,
            total,
            loaded,
            native_snapshot=contact_snapshot,
        )
        for result in iter_analyze_organic(
            contact_snapshot.contact_result,
            settings,
        ):
            yield StructureLoadUpdate(
                LoadStage(result.stage.value),
                source,
                index,
                total,
                loaded,
                native_organic_snapshot=result,
            )


__all__ = [
    "LoadStage",
    "StructureLoadUpdate",
    "iter_load_updates",
    "iter_reanalysis_updates",
    "iter_native_reanalysis_updates",
]
