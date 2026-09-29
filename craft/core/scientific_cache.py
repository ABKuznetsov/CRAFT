"""Small application-owned records for cached CRiStMa results."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Generic, Mapping, TypeVar


T = TypeVar("T")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return value


class ScientificExecutionState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class ScientificRequestKey:
    structure_fingerprint: str
    tool_id: str
    tool_version: str
    configuration: tuple[tuple[str, object], ...] = ()

    @classmethod
    def from_mapping(
        cls,
        *,
        structure_fingerprint: str,
        tool_id: str,
        tool_version: str,
        configuration: Mapping[str, object] | None = None,
    ) -> ScientificRequestKey:
        return cls(
            structure_fingerprint=structure_fingerprint,
            tool_id=tool_id,
            tool_version=tool_version,
            configuration=tuple(
                sorted(
                    (str(key), _freeze(value))
                    for key, value in (configuration or {}).items()
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ScientificResultSlot(Generic[T]):
    request_key: ScientificRequestKey
    execution: ScientificExecutionState = ScientificExecutionState.PENDING
    result: T | None = None
    error_message: str | None = None
    provenance: ScientificResultProvenance | None = None

    @property
    def value(self) -> T | None:
        """Compatibility view while upper scientific layers are migrated."""
        return self.result


@dataclass(frozen=True, slots=True)
class ScientificResultProvenance:
    structure_identity: str
    tool_id: str
    tool_version: str
    configuration: tuple[tuple[str, object], ...] = ()
    result_provenance: object | None = None

    @classmethod
    def from_mapping(
        cls,
        *,
        structure_identity: str,
        tool_id: str,
        tool_version: str,
        configuration: Mapping[str, object] | None = None,
        result_provenance: object | None = None,
    ) -> ScientificResultProvenance:
        normalized = tuple(
            sorted(
                (str(key), _freeze(value))
                for key, value in (configuration or {}).items()
            )
        )
        return cls(
            structure_identity=structure_identity,
            tool_id=tool_id,
            tool_version=tool_version,
            configuration=normalized,
            result_provenance=result_provenance,
        )


@dataclass(frozen=True, slots=True)
class CachedScientificResult(Generic[T]):
    value: T
    provenance: ScientificResultProvenance


@dataclass(frozen=True, slots=True)
class ScientificResultSlots:
    chemistry: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    crystal_chemistry: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    polyhedra: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    units: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    unit_graph: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    representation: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    connectivity: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    blocks: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    rings: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    molecular: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    intermolecular: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    pi_systems: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    pi_stacking: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    ch_pi: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    packing: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    reticular_precursor: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    sbu: CachedScientificResult[object] | ScientificResultSlot[object] | None = None
    reticular_net: CachedScientificResult[object] | ScientificResultSlot[object] | None = None

    def with_result(
        self,
        slot: str,
        result: CachedScientificResult[object] | ScientificResultSlot[object],
    ) -> ScientificResultSlots:
        if slot not in self.__dataclass_fields__:
            raise KeyError(f"unknown scientific result slot: {slot}")
        return replace(self, **{slot: result})

    def invalidate_all(self) -> ScientificResultSlots:
        return ScientificResultSlots()


__all__ = [
    "CachedScientificResult",
    "ScientificExecutionState",
    "ScientificRequestKey",
    "ScientificResultSlot",
    "ScientificResultProvenance",
    "ScientificResultSlots",
]
