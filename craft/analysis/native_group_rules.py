"""Read recognition evidence from the pinned CrIStMa chemical reference.

Only signatures with explicit local oxygen-coordination evidence are local
environment rules. A bulk formula such as SiO3 is not a Si coordination number.
Variable polyoxo signatures are candidates, never an oxidation-state assertion.
"""
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
import hashlib
import json
import re

from cristma.reference_data import ReferenceData


@dataclass(frozen=True, slots=True)
class ClassRule:
    family: str
    label: str
    centre: str
    coordination_numbers: tuple[int, ...]
    reference: str
    generic: bool = False


@lru_cache(maxsize=1)
def class_rules() -> tuple[ClassRule, ...]:
    reference = ReferenceData.default().chemical
    # The public reference exposes lookup by ID but no iterator. Use its bundled
    # source only after checking that it is precisely the loaded reference.
    raw = files("cristma.reference_data.resources").joinpath("chemical_reference_v3_1.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference.resource_sha256:
        raise ValueError("CrIStMa group catalog does not match the loaded chemical reference")
    records = json.loads(raw)["group_signatures"]
    local = {}
    for identifier in records:
        record = reference.group_signature(identifier)
        formula = str(record.get("canonical", ""))
        match = re.fullmatch(r"([A-Z][a-z]?)O(\d+)", formula)
        variable = re.fullmatch(r"([A-Z][a-z]?)nOm", formula)
        if variable and record.get("family_hint") == "inorganic.polyoxometalate":
            centre, numbers, generic = variable[1], (), True
        elif match and record.get("recognition_evidence"):
            centre, numbers, generic = match[1], (int(match[2]),), False
        else:
            continue
        family = identifier.removesuffix("_generic")
        for suffix in ("_trigonal", "_tetrahedral", "_octahedral"):
            family = family.removesuffix(suffix)
        key = (family, centre)
        old = local.get(key)
        ref = f"cristma:{reference.schema_version}#{identifier}"
        local[key] = ClassRule(family, family.replace("_", " ").capitalize() + "s", centre,
            tuple(sorted(set(numbers) | set(old.coordination_numbers if old else ()))),
            ref if old is None else old.reference + "; " + ref, generic)
    return tuple(local.values())


def class_centre(family: str) -> str:
    return next((rule.centre for rule in class_rules() if rule.family == family), "M")
