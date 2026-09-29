"""Application-owned source context around canonical CRiStMa structures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cristma.diagnostics import Diagnostic, Severity
from cristma.structure import CrystalStructure, MolecularStructure, Structure


@dataclass(frozen=True, slots=True)
class StructureSourceContext:
    """Where a canonical structure came from, without duplicating its science."""

    source_path: Path
    source_identity: str
    source_format: str | None
    diagnostics: tuple[Diagnostic, ...]
    source_document: object | None
    display_name_override: str | None = None

    def __post_init__(self) -> None:
        path = Path(self.source_path)
        if not path.is_absolute():
            raise ValueError("structure source path must be absolute")
        if not self.source_identity.strip():
            raise ValueError("structure source identity must not be empty")
        object.__setattr__(self, "source_path", path)
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@dataclass(frozen=True, slots=True)
class LoadedStructure:
    """One canonical structure paired with its application source context."""

    structure: Structure
    source: StructureSourceContext

    def __post_init__(self) -> None:
        if not isinstance(self.structure, (CrystalStructure, MolecularStructure)):
            raise TypeError("loaded structure must be a canonical CRiStMa structure")
        fatal = tuple(
            item for item in self.source.diagnostics if item.severity is Severity.ERROR
        )
        if fatal:
            codes = ", ".join(item.code for item in fatal)
            raise ValueError(f"fatal source diagnostic: {codes}")

    @property
    def display_name(self) -> str:
        """Choose an application label without changing the canonical structure."""

        override = (self.source.display_name_override or "").strip()
        if override:
            return override
        for key in ("mineral_name", "common_name", "systematic_name"):
            value = self.structure.metadata.get(key)
            if isinstance(value, str) and value.strip() not in {"", ".", "?"}:
                return value.strip()
        if self.source.source_format not in {None, "cif"}:
            canonical_name = self.structure.name.strip()
            if canonical_name and canonical_name not in {".", "?"}:
                return canonical_name
        stem = self.source.source_path.stem.strip()
        if stem:
            return stem
        return self.structure.name


__all__ = ["LoadedStructure", "StructureSourceContext"]
