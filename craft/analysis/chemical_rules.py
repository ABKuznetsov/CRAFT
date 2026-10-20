"""Fingerprint native classification data and CRAFT calculator requests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Any
from importlib.metadata import version

from cristma.reference_data import ReferenceData


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@lru_cache(maxsize=1)
def chemical_rules() -> Mapping[str, Any]:
    """Read the packaged, immutable CRAFT catalog once per process."""
    content = files("craft.analysis").joinpath("chemical_rules.json").read_bytes()
    payload = json.loads(content)
    payload["sha256"] = hashlib.sha256(content).hexdigest()
    return _freeze(payload)


def chemical_rules_config() -> dict[str, str]:
    rules = chemical_rules()
    reference = ReferenceData.default().chemical
    return {
        "rules_id": rules["id"],
        "rules_version": rules["version"],
        "rules_sha256": rules["sha256"],
        "classifier": "cristma.chemistry.ChemistryAnalyzer",
        "classifier_package_version": version("cristma"),
        "classifier_reference_version": reference.schema_version,
        "classifier_reference_sha256": reference.resource_sha256,
    }
