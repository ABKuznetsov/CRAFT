"""Presentation model for structural domains calculated by CrIStMa."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StructuralDomain:
    id: str
    polyhedron_ids: tuple[str, ...]
    atom_indices: tuple[int, ...]
    periodic_rank: int
    classification: str
    role_confidence: float
    nested_ring_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


__all__ = ["StructuralDomain"]
