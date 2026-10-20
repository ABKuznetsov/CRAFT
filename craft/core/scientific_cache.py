"""Small application-owned records for cached CRiStMa results."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Generic, Mapping, TypeVar


T = TypeVar("T")

INORGANIC_RESULT_SLOTS = (
    "chemistry", "crystal_chemistry", "polyhedra", "inorganic_classification",
    "units", "unit_graph", "representation", "connectivity", "blocks", "rings",
)
ORGANIC_RESULT_SLOTS = (
    "molecular", "intermolecular", "pi_systems", "pi_stacking", "ch_pi",
    "packing", "reticular_precursor", "sbu", "reticular_net",
)


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return value


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
    """One installed result; execution progress belongs to request managers."""

    request_key: ScientificRequestKey
    result: T
    provenance: ScientificResultProvenance | None = None


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
class ScientificResultSlots:
    chemistry: ScientificResultSlot[object] | None = None
    crystal_chemistry: ScientificResultSlot[object] | None = None
    polyhedra: ScientificResultSlot[object] | None = None
    inorganic_classification: ScientificResultSlot[object] | None = None
    units: ScientificResultSlot[object] | None = None
    unit_graph: ScientificResultSlot[object] | None = None
    representation: ScientificResultSlot[object] | None = None
    connectivity: ScientificResultSlot[object] | None = None
    blocks: ScientificResultSlot[object] | None = None
    rings: ScientificResultSlot[object] | None = None
    molecular: ScientificResultSlot[object] | None = None
    intermolecular: ScientificResultSlot[object] | None = None
    pi_systems: ScientificResultSlot[object] | None = None
    pi_stacking: ScientificResultSlot[object] | None = None
    ch_pi: ScientificResultSlot[object] | None = None
    packing: ScientificResultSlot[object] | None = None
    reticular_precursor: ScientificResultSlot[object] | None = None
    sbu: ScientificResultSlot[object] | None = None
    reticular_net: ScientificResultSlot[object] | None = None

    def with_result(
        self,
        slot: str,
        result: ScientificResultSlot[object],
    ) -> ScientificResultSlots:
        if slot not in self.__dataclass_fields__:
            raise KeyError(f"unknown scientific result slot: {slot}")
        return replace(self, **{slot: result})

    def invalidate_all(self) -> ScientificResultSlots:
        return ScientificResultSlots()

    def diagnostics(self, names: tuple[str, ...]) -> tuple[object, ...]:
        """Read native diagnostics only from the requested analysis branch."""
        answer: list[object] = []
        seen: set[tuple[str, str, str]] = set()
        for name in names:
            slot = getattr(self, name)
            if slot is None:
                continue
            for diagnostic in getattr(slot.result, "diagnostics", ()):
                key = (
                    str(getattr(diagnostic, "code", "")),
                    str(getattr(diagnostic, "message", diagnostic)),
                    str(getattr(diagnostic, "severity", "")),
                )
                if key not in seen:
                    seen.add(key)
                    answer.append(diagnostic)
        return tuple(answer)


__all__ = [
    "INORGANIC_RESULT_SLOTS",
    "ORGANIC_RESULT_SLOTS",
    "ScientificRequestKey",
    "ScientificResultSlot",
    "ScientificResultProvenance",
    "ScientificResultSlots",
]
