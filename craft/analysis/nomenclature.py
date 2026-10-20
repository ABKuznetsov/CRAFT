"""CRAFT-owned mineralogical names layered over native scientific evidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NomenclatureAssignment:
    domain_id: str
    vocabulary: str
    descriptor: str
    evidence: tuple[str, ...]
    confidence: float
    warnings: tuple[str, ...] = ()


__all__ = ["NomenclatureAssignment"]
