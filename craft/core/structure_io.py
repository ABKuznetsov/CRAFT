"""Structural input boundary: CRiStMa payloads plus CRAFT project containers."""

from __future__ import annotations

from pathlib import Path

import cristma
from cristma.diagnostics import Diagnostic
from cristma.io.result import ReadResult

from craft.core.reference_data_warmup import ensure_cristma_reference_data
from craft.core.structure_source import LoadedStructure, StructureSourceContext
from craft.core.xpff import load_xpff_structures


_FORMAT_DESCRIPTORS = cristma.structure_formats()
SUPPORTED_STRUCTURE_SUFFIXES = frozenset(
    {
        ".xpff",
        *(
            suffix.casefold()
            for descriptor in _FORMAT_DESCRIPTORS
            for suffix in descriptor.suffixes
        ),
    }
)
SUPPORTED_STRUCTURE_BASENAMES = frozenset(
    basename.casefold()
    for descriptor in _FORMAT_DESCRIPTORS
    for basename in descriptor.basenames
)


class StructureReadError(ValueError):
    """A structure source could not be mapped into canonical CRiStMa data."""

    def __init__(self, path: Path, diagnostics: tuple[Diagnostic, ...]) -> None:
        self.path = path
        self.diagnostics = tuple(diagnostics)
        details = "; ".join(
            f"{item.code}: {item.message}" for item in self.diagnostics
        ) or "no structure was produced"
        super().__init__(f"CRiStMa could not read {path.name}: {details}")


def is_supported_structure_path(path: str | Path) -> bool:
    source = Path(path)
    return (
        source.suffix.casefold() in SUPPORTED_STRUCTURE_SUFFIXES
        or source.name.casefold() in SUPPORTED_STRUCTURE_BASENAMES
    )


def loaded_structures_from_result(
    result: ReadResult,
    path: str | Path,
    *,
    display_name_override: str | None = None,
    source_identity_prefix: str | None = None,
) -> tuple[LoadedStructure, ...]:
    """Pair every canonical reader result with CRAFT-owned source context."""

    source = Path(path).expanduser().resolve()
    selected = result
    if not selected.ok or not selected.structures:
        raise StructureReadError(source, tuple(selected.diagnostics))
    structures = tuple(selected.structures)
    if not structures:
        raise StructureReadError(source, tuple(selected.diagnostics))
    source_format = selected.source_info.format if selected.source_info else None
    loaded: list[LoadedStructure] = []
    for index, structure in enumerate(structures, start=1):
        provenance_source = structure.provenance.source
        record_id = (
            provenance_source.record_id
            if provenance_source is not None and provenance_source.record_id
            else str(index)
        )
        prefix = source_identity_prefix or str(source)
        context = StructureSourceContext(
            source_path=source,
            source_identity=f"{prefix}#{record_id}",
            source_format=source_format,
            diagnostics=tuple(selected.diagnostics),
            source_document=selected.document,
            display_name_override=display_name_override,
        )
        loaded.append(LoadedStructure(structure, context))
    return tuple(loaded)


def load_structure_files(path: str | Path):
    """Read structural files through CRiStMa; delegate only project containers."""

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.casefold() == ".xpff":
        return tuple(load_xpff_structures(source))
    ensure_cristma_reference_data()
    return loaded_structures_from_result(cristma.read(source), source)


__all__ = [
    "SUPPORTED_STRUCTURE_BASENAMES",
    "SUPPORTED_STRUCTURE_SUFFIXES",
    "StructureReadError",
    "is_supported_structure_path",
    "load_structure_files",
    "loaded_structures_from_result",
]
